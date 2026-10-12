# -*- coding: utf-8 -*-
"""스캔 517라운드 회귀 — collect_emails.py 가 partners.website 를 실제로
   fetch() 하면서 SSRF 방어가 전혀 없던 결함.

   조사 배경 — website 는 3개 진입로(api_partner_create·api_partner_update·
   api_contact_import) 전부 @require_admin(등급 무관, 라운드509 주석)로
   저장된다. 저장 시점 검증(valid_website, 라운드509·510)은 위험한 URL
   스킴(javascript: 등)만 막을 뿐 호스트는 전혀 안 본다 — http(s):// 라면
   127.0.0.1 이든 사설망 주소든 그대로 통과한다. app.py 는 이미 똑같은
   위험(웹훅 URL)을 _webhook_safe_ip() 로 막는데(라운드38·84·157), 형제인
   이 파일은 website 를 실제로 GET 하면서(수집 CLI 의 존재 목적) 그 방어가
   하나도 없었다 — 하위관리자 계정 하나만 있으면(또는 탈취되면) website 를
   내부 주소로 심어 두고 운영자가 나중에 이 배치를 돌리는 순간 서버가
   자기 내부망을 대신 두드리게 만들 수 있었다.

   고침: app.py 의 판정과 같은 기준(_host_is_internal)을 collect_emails.py
   에 옮기고, fetch() 뿐 아니라 robots.txt 를 따로 요청하는 robots_allows()
   에도 건다(실측: fetch() 만 막으면 robots.txt 요청은 그대로 내부 서버에
   도달했다 — 아래 [3]이 이 두 자리를 모두 실측으로 구분해 증명한다).
   테스트 하네스가 127.0.0.1 로컬 서버로 사이트를 흉내내는 기존 테스트
   3개(218·299)는 BOKGUON_COLLECT_ALLOW_LOCAL=1 로 이 방어만 예외 허용한다
   (운영에서는 이 환경변수를 켜지 않는다).

      python test_scan_round517_fixes.py
"""
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("═" * 72)
print("  스캔 517라운드 회귀 — collect_emails.py website fetch SSRF 방어 부재")
print("═" * 72)

#  이 프로세스가 실수로 운영 DB 를 열지 않도록 먼저 격리 경로를 지정해 둔다
#  (collect_emails 는 최상위에서 `import db as DB` 를 한다 — 이 테스트는
#  DB.get_db() 를 안 부르지만 습관적으로 항상 먼저 막아 둔다).
os.environ.setdefault("BOKGUON_DB_PATH", os.path.join(HERE, "_r517_unused.db"))
sys.path.insert(0, HERE)
import collect_emails as CE  # noqa: E402

CE.PAUSE = 0  # 로컬 서버 상대라 예의상 간격을 둘 필요가 없다 — 테스트만 빨라진다


def make_server():
    hits = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body>secret-internal-r517@should-not-leak.example</body></html>")

        def log_message(self, *a):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, hits


def stop_server(httpd):
    httpd.shutdown()
    httpd.server_close()


# ══════════════════════════════════════════════════════════════
print("\n[1] 실행 — _host_is_internal() 이 실제 주소 대역을 정확히 분류하는가")
# ──────────────────────────────────────────────────────────────
#  진짜 getaddrinfo 로 실행한다(app.py 라운드157 테스트와 같은 방식 — 목만
#  갈아끼우면 이 함수 자체의 판정 로직은 검증되지 않는다).
cases = [
    ("127.0.0.1", 80, True, "루프백"),
    ("169.254.169.254", 80, True, "클라우드 메타데이터(링크로컬)"),
    ("10.0.0.5", 80, True, "사설망(10/8)"),
    ("192.168.1.1", 443, True, "사설망(192.168/16)"),
    ("100.64.0.1", 80, True, "공유주소공간 CGNAT(100.64/10, 라운드84가 다듬은 대역)"),
    ("8.8.8.8", 443, False, "공인 IP(구글 DNS)"),
]
for host, port, expect_internal, label in cases:
    got = CE._host_is_internal(host, port)
    chk(got == expect_internal,
        f"★★★ {label}({host}) → internal={expect_internal}", got)

chk(CE._host_is_internal("no-such-host-r517.invalid.test", 80) is False,
    "★★ 해석 자체가 안 되는 주소는 '내부망 확인됨'으로 막지 않는다"
    "(그 판단은 fetch() 자신의 접속 실패 처리에 맡긴다 — 이중판단 금지)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — fetch() 가 실제 로컬 서버(127.0.0.1)에 도달하지 않는가")
# ──────────────────────────────────────────────────────────────
httpd1, hits1 = make_server()
try:
    result = CE.fetch(f"http://127.0.0.1:{httpd1.server_port}/")
    chk(result is None, "★★★★★ fetch() 가 내부 주소를 막아 None 을 돌려준다", result)
    chk(hits1 == [], "★★★★★ 요청 자체가 서버에 전혀 도달하지 않았다(진짜 SSRF 차단)",
        hits1)
finally:
    stop_server(httpd1)

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — collect_one() 전체 경로에서도 이메일이 새지 않는가"
      "(robots_allows()·fetch() 두 접속 지점 모두)")
# ──────────────────────────────────────────────────────────────
#  ⚠ fetch() 만 막고 robots_allows() 를 안 막으면 robots.txt 요청 한 번은
#    그대로 내부 서버에 도달한다(수정 전 실측: hits == ['/robots.txt']).
#    이 절이 그 자리까지 포함해 0건임을 증명한다.
httpd2, hits2 = make_server()
try:
    emails, note = CE.collect_one(f"http://127.0.0.1:{httpd2.server_port}")
    chk(emails == [], "★★★★★ collect_one() 이 내부 서버의 이메일을 수집하지 않는다",
        emails)
    chk(hits2 == [],
        "★★★★★ robots.txt 요청까지 포함해 어떤 요청도 내부 서버에 도달하지 않는다"
        "(수정 전엔 이 목록에 '/robots.txt' 가 남았다)", hits2)
finally:
    stop_server(httpd2)

# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌리기 — 방어를 끄면(수정 전 상태 재현) 실제로 새는가(인과관계 직접증명)")
# ──────────────────────────────────────────────────────────────
httpd3, hits3 = make_server()
_orig_guard = CE._host_is_internal
try:
    CE._host_is_internal = lambda hostname, port: False   # 수정 전 동작(검사 없음) 재현
    emails_before, note_before = CE.collect_one(f"http://127.0.0.1:{httpd3.server_port}")
    chk(emails_before == ["secret-internal-r517@should-not-leak.example"],
        "★★★★★ 방어를 끄면 내부 서버의 '비밀' 이메일이 실제로 수집된다"
        "(고치기 전엔 이랬다 — 인과관계 확인)", (emails_before, note_before))
    chk(hits3 == ["/robots.txt", "/"],
        "★★★★★ 이때는 robots.txt·본문 요청이 둘 다 실제로 내부 서버에 도달한다",
        hits3)
finally:
    CE._host_is_internal = _orig_guard
    stop_server(httpd3)

# ══════════════════════════════════════════════════════════════
print("\n[5] 실행 — 테스트 하네스 전용 예외(BOKGUON_COLLECT_ALLOW_LOCAL)가 "
      "기존 회귀(라운드218·299)와 호환되는가")
# ──────────────────────────────────────────────────────────────
chk(os.environ.get("BOKGUON_COLLECT_ALLOW_LOCAL") != "1",
    "STEP 이 테스트 프로세스 자신은 그 예외를 켜지 않은 상태다(전제 확인 — "
    "위 [2]~[4]가 실제로 방어를 시험한 것이었음을 보장)")
httpd4, hits4 = make_server()
_env_before = os.environ.get("BOKGUON_COLLECT_ALLOW_LOCAL")
try:
    os.environ["BOKGUON_COLLECT_ALLOW_LOCAL"] = "1"
    CE._ALLOW_LOCAL_FETCH = True   # 모듈 상수는 import 시점에 이미 읽혔으므로 직접 맞춘다
    emails4, note4 = CE.collect_one(f"http://127.0.0.1:{httpd4.server_port}")
    chk(emails4 == ["secret-internal-r517@should-not-leak.example"],
        "★★★ 하네스 예외를 켜면 라운드218·299 처럼 로컬 서버 수집이 그대로 동작한다"
        "(그 두 회귀테스트가 실제로 무엇에 의존하는지 여기서도 재확인)",
        (emails4, note4))
finally:
    CE._ALLOW_LOCAL_FETCH = False
    if _env_before is None:
        os.environ.pop("BOKGUON_COLLECT_ALLOW_LOCAL", None)
    else:
        os.environ["BOKGUON_COLLECT_ALLOW_LOCAL"] = _env_before
    stop_server(httpd4)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
