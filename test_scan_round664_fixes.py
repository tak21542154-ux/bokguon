# -*- coding: utf-8 -*-
"""스캔 664라운드 회귀(직접조사, 하위위임 없음) — collect_emails.py 가 website 를
   실제로 GET 하면서 **리다이렉트는 전혀 막지 않은** 결함(SSRF, round517 이 놓친
   같은 계열의 새 우회로).

   조사 배경 — round517 이 이미 이 파일에 _host_is_internal() 을 두 접속 지점
   (fetch()·robots_allows())에 걸어 "website 를 127.0.0.1 등 내부주소로 직접
   적어 두는" SSRF 를 막았다. 그런데 그 검사는 **최초 접속 주소**만 본다 —
   website 가 공인 도메인(검사 통과)이라도, 그 서버가 301/302 로 내부 주소를
   가리키면 fetch() 의 urllib.request.urlopen() 도 robots_allows() 의
   RobotFileParser 도 **기본 오프너가 그대로 따라가** 검사를 완전히 우회한다.
   round517 자신의 ponytail 주석("DNS 리바인딩까지는 안 막는다")은 이 리다이렉트
   우회를 전혀 언급하지 않았다 — 그건 검사·접속 사이의 **경합조건**을 논의한
   것이고, 이건 정적인 301 응답 하나로 매번 재현되는 **별개의**, 훨씬 쉬운
   우회로다. app.py 의 웹훅 SSRF 방어는 정확히 이 경로를 "③ 리다이렉트를
   따라가지 않는다"(_NoRedirect)로 막는데, 형제인 이 파일에는 없었다.

   실측(이 라운드, 격리된 로컬 리다이렉터+내부 서버 두 개로 재현) — 고치기 전:
   urllib.request.urlopen() 도 urllib.robotparser.RobotFileParser.read() 도
   둘 다 301 을 그대로 따라가 내부 서버에 실제로 도달했고, 내부 서버의 '비밀'
   이메일이 그대로 수집됐다(아래 [4]가 이 인과관계를 직접 증명한다).

   고침(collect_emails.py) — app.py 와 같은 _NoRedirect(urllib.request.
   HTTPRedirectHandler 서브클래스, redirect_request 가 항상 None) 오프너를
   신설해 fetch() 가 그 오프너로 직접 열게 하고, robots_allows() 는
   RobotFileParser 가 오프너를 주입받을 방법이 없으므로(내부에서 직접
   urllib.request.urlopen() 을 부른다) rp.read() 를 부르는 동안만 전역
   기본 오프너를 바꿔치기한다(기존 [라운드639] 의 소켓 타임아웃 save/restore와
   같은 방식 — 호출이 끝나면 원래대로 되돌린다). 두 접속 지점 모두 같은
   _NO_REDIRECT_OPENER 하나를 공유하는 단일 근본원인 수정.

   회귀테스트(이 파일) — [1] 소스: _NoRedirect 클래스가 HTTPRedirectHandler
   서브클래스로 정의돼 있고, fetch() 소스에 옛 "urllib.request.urlopen(req"
   패턴이 더 이상 없이 "_NO_REDIRECT_OPENER.open(req" 로 바뀌었으며,
   robots_allows() 소스에 install_opener 바꿔치기가 있음을 확인. [2] 실행 —
   실제 로컬 리다이렉터(→내부 서버) 두 개로 fetch() 를 직접 호출해, 내부
   서버가 0건 요청받고 fetch() 가 None 을 돌려줌을 확인(★★★★★). [3] 실행 —
   collect_one() 전체 경로(robots_allows()·fetch() 두 접속 지점 모두)에서도
   이메일이 새지 않음을 확인. [4] 되돌리기 — _NO_REDIRECT_OPENER 하나만 옛
   기본(리다이렉트 추종) 오프너로 바꿔치기하면(fetch()·robots_allows() 코드는
   전혀 안 건드림) 내부 서버의 '비밀' 이메일이 실제로 수집됨을 확인해
   인과관계를 증명(고치기 전엔 이랬다). collect_emails.py 는 app.py 어디에도
   import 되지 않는 독립 CLI라 서버 재기동 불필요, templates/static 무변경.

      python test_scan_round664_fixes.py
"""
import inspect
import os
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("═" * 72)
print("  스캔 664라운드 회귀 — collect_emails.py fetch/robots_allows 리다이렉트 SSRF")
print("═" * 72)

#  이 프로세스가 실수로 운영 DB 를 열지 않도록 먼저 격리 경로를 지정해 둔다
#  (collect_emails 는 최상위에서 `import db as DB` 를 한다 — round517 테스트와
#  같은 습관: 이 테스트는 DB.get_db() 를 안 부르지만 항상 먼저 막아 둔다).
os.environ.setdefault("BOKGUON_DB_PATH", os.path.join(HERE, "_r664_unused.db"))
sys.path.insert(0, HERE)
import collect_emails as CE  # noqa: E402

CE.PAUSE = 0  # 로컬 서버 상대라 예의상 간격을 둘 필요가 없다 — 테스트만 빨라진다

SECRET_EMAIL = "secret-internal-r664@should-not-leak.example"


def make_internal_server():
    """진짜 '내부망' 대상 흉내 — 도달하면 안 되는 비밀을 들고 있다."""
    hits = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                f"<html><body>{SECRET_EMAIL}</body></html>".encode("utf-8"))

        def log_message(self, *a):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, hits


def make_redirector_server(target_base):
    """'공인 도메인처럼 통과하는' 외부 사이트 흉내 — 모든 경로를 내부로 302."""
    hits = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(302)
            self.send_header("Location", target_base + self.path)
            self.end_headers()

        def log_message(self, *a):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, hits


def stop(httpd):
    httpd.shutdown()
    httpd.server_close()


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — _NoRedirect 오프너가 fetch()·robots_allows() 양쪽에 실제로 걸려 있는가")
# ──────────────────────────────────────────────────────────────
chk(isinstance(CE._NoRedirect, type)
    and issubclass(CE._NoRedirect, urllib.request.HTTPRedirectHandler),
    "★★ _NoRedirect 가 HTTPRedirectHandler 서브클래스로 정의돼 있다")
#  redirect_request 자신의 실제 동작(항상 None → 리다이렉트 미추종)은 정적으로
#  보지 않고 아래 [2]가 실제 로컬 서버로 실행해 증명한다.

src_fetch = inspect.getsource(CE.fetch)
chk("_NO_REDIRECT_OPENER.open(req" in src_fetch,
    "★★★ fetch() 가 _NO_REDIRECT_OPENER 로 연다")
chk("urllib.request.urlopen(req" not in src_fetch,
    "★★ fetch() 에 옛(리다이렉트 추종) urlopen(req 패턴이 더 이상 없다")

src_robots = inspect.getsource(CE.robots_allows)
chk("install_opener(_NO_REDIRECT_OPENER)" in src_robots,
    "★★★ robots_allows() 가 rp.read() 동안 전역 오프너를 _NO_REDIRECT_OPENER 로 바꾼다")
chk("install_opener(_old_opener)" in src_robots,
    "★★ robots_allows() 가 호출이 끝나면 원래 오프너로 되돌린다(전역 상태 누출 방지)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — fetch() 가 '공인 도메인처럼 통과한' 외부 서버의 302 를 따라가지 않는가")
# ──────────────────────────────────────────────────────────────
#  _host_is_internal 은 이미 round517 이 검증했다(test_scan_round517_fixes.py) —
#  여기서는 "그 최초 검사를 통과한 뒤"의 리다이렉트 우회만 골라서 본다. 로컬
#  서버는 실제로는 127.0.0.1(내부)이라 최초 검사 자체가 먼저 걸리므로, 진짜
#  공인 도메인이 그 검사를 통과하는 상황을 흉내내려면 이 검사만 잠깐 늦춘다.
_orig_guard = CE._host_is_internal
CE._host_is_internal = lambda hostname, port: False
httpd1, hits1 = make_internal_server()
red1, redhits1 = make_redirector_server(f"http://127.0.0.1:{httpd1.server_port}")
try:
    result = CE.fetch(f"http://127.0.0.1:{red1.server_port}/")
    chk(redhits1 == ["/"], "STEP 리다이렉터 자신은 실제로 요청을 받았다(테스트 전제 확인)",
        redhits1)
    chk(hits1 == [], "★★★★★ 내부 서버는 어떤 요청도 받지 않았다(리다이렉트 미추종)",
        hits1)
    chk(result is None, "★★★★★ fetch() 가 None 을 돌려준다(내부 응답을 그대로 안 준다)",
        result)
finally:
    stop(httpd1); stop(red1)

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — collect_one() 전체 경로(robots_allows()·fetch() 두 지점 모두)도 안 새는가")
# ──────────────────────────────────────────────────────────────
httpd2, hits2 = make_internal_server()
red2, redhits2 = make_redirector_server(f"http://127.0.0.1:{httpd2.server_port}")
try:
    emails, note = CE.collect_one(f"http://127.0.0.1:{red2.server_port}")
    chk(emails == [], "★★★★★ collect_one() 이 내부 서버의 '비밀' 이메일을 수집하지 않는다",
        (emails, note))
    chk(hits2 == [],
        "★★★★★ robots.txt 요청까지 포함해 어떤 요청도 내부 서버에 도달하지 않는다",
        hits2)
finally:
    stop(httpd2); stop(red2)

# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌리기 — _NO_REDIRECT_OPENER 하나만 옛 기본(리다이렉트 추종) 오프너로 "
      "바꾸면(인과관계 직접증명)")
# ──────────────────────────────────────────────────────────────
#  ⚠ fetch()·robots_allows() 의 코드는 전혀 안 건드린다 — 두 함수가 공유하는
#    단일 지점(_NO_REDIRECT_OPENER)만 바꿔, 이 한 값이 실제 근본원인 수정의
#    전부임을 증명한다(단순 상수/속성 교체 — 실제 파일에는 절대 안 씀).
httpd3, hits3 = make_internal_server()
red3, redhits3 = make_redirector_server(f"http://127.0.0.1:{httpd3.server_port}")
_orig_opener = CE._NO_REDIRECT_OPENER
try:
    CE._NO_REDIRECT_OPENER = urllib.request.build_opener()   # 수정 전 동작(추종) 재현
    emails_before, note_before = CE.collect_one(f"http://127.0.0.1:{red3.server_port}")
    chk(emails_before == [SECRET_EMAIL],
        "★★★★★ 되돌리면 내부 서버의 '비밀' 이메일이 실제로 수집된다"
        "(고치기 전엔 이랬다 — 인과관계 확인)", (emails_before, note_before))
    chk(hits3 != [],
        "★★★★★ 이때는 내부 서버에도 실제로 요청이 도달한다(리다이렉트를 따라감)",
        hits3)
finally:
    CE._NO_REDIRECT_OPENER = _orig_opener
    CE._host_is_internal = _orig_guard
    stop(httpd3); stop(red3)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
