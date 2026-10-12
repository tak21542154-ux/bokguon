# -*- coding: utf-8 -*-
"""스캔 218라운드 회귀 — collect_emails.py 의 collect_one() 이 첫 페이지의
   robots.txt 만 검사하고, 첫 페이지에 이메일이 없어 더 보는 하위 경로 4곳은
   robots.txt 를 전혀 재검사하지 않던 결함(형제인 refuses_collection() 은
   이 루프 안에서도 매번 재검사되는데 정확히 이것만 빠졌다). 부수적으로
   SUB_PATHS 6개 중 하드코딩된 [:4] 슬라이스가 뒤 2개(/company, /inquiry)를
   영구히 시도조차 못 하게 막던 것도 함께 수정(218라운드 조사 에이전트가
   실제 로컬 HTTP 서버로 재현).

   이 모듈은 217라운드까지 한 번도 감사·테스트되지 않았다.

      python test_scan_round218_fixes.py
"""
import io
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("═" * 72)
print("  스캔 218라운드 회귀 — collect_emails 하위경로 루프의 robots.txt 미검사")
print("═" * 72)

#  collect_emails 가 최상위에서 `import db as DB` 를 하므로, 이 프로세스가
#  실수로 운영 DB 를 열지 않도록 먼저 격리 경로를 지정해 둔다(이 테스트는
#  DB.get_db() 를 아예 안 부르지만, 습관적으로 항상 먼저 막아 둔다).
os.environ.setdefault("BOKGUON_DB_PATH",
                       os.path.join(HERE, "_r218_unused.db"))
#  [라운드517] fetch()·robots_allows() 가 이제 내부/사설 주소(127.0.0.1 포함)로의
#  접속을 SSRF 방어로 막는다 — 이 테스트는 그 방어 자체가 아니라 robots.txt
#  캐스케이드를 검증하는 것이 목적이라, 실제 사이트를 흉내내는 로컬 서버만
#  예외로 허용한다(운영에서는 이 환경변수를 절대 켜지 않는다).
os.environ["BOKGUON_COLLECT_ALLOW_LOCAL"] = "1"
sys.path.insert(0, HERE)
import collect_emails as CE  # noqa: E402

CE.PAUSE = 0  # 로컬 서버 상대라 예의상 간격을 둘 필요가 없다 — 테스트만 빨라진다


def make_server(routes):
    """routes: {경로: (status, content_type, body)}. 없는 경로는 404."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hit = routes.get(self.path)
            if hit is None:
                self.send_response(404)
                self.end_headers()
                return
            status, ctype, body = hit
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


def stop_server(httpd):
    httpd.shutdown()
    httpd.server_close()


# ══════════════════════════════════════════════════════════════
print("\n[1] robots.txt 가 /contact 만 막을 때 — 그 페이지 메일은 수집하면 안 된다")
# ──────────────────────────────────────────────────────────────
#  ⚠ robots.txt 의 Disallow 는 접두어 매칭이다 — "Disallow: /contact" 는
#    "/contact.html"·"/contactus" 까지 함께 막는다(robotparser 표준 동작,
#    버그 아님). 그래서 "막힘→허용" 대조는 접두어가 겹치지 않는 /about 에
#    허용 메일을 두고, 금지 메일은 /contact 에 둔다(둘 다 옛 [:4] 범위 안 —
#    이 시나리오는 아래 [3]의 슬라이스 수정과 독립적으로 증명된다).
routes1 = {
    "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /contact\n"),
    "/": (200, "text/html", "<html><body>연락처 페이지를 참고하세요</body></html>"),
    "/contact": (200, "text/html", "<html><body>금지된 메일 forbidden-r218@example-corp.co.kr</body></html>"),
    "/contact.html": (200, "text/html", "<html><body>메일 없음(이 페이지도 /contact 접두어라 함께 막힘)</body></html>"),
    "/contactus": (200, "text/html", "<html><body>메일 없음(이 페이지도 /contact 접두어라 함께 막힘)</body></html>"),
    "/about": (200, "text/html", "<html><body>허용된 메일 allowed-r218@example-corp.co.kr</body></html>"),
}
srv1 = make_server(routes1)
try:
    base_url = f"http://127.0.0.1:{srv1.server_port}"
    emails, note = CE.collect_one(base_url)
    chk("forbidden-r218@example-corp.co.kr" not in emails,
        "★★★★ robots.txt 가 막은 /contact 의 메일은 하위경로 루프에서도 "
        "수집되지 않는다(예전엔 진입 URL 한 번만 검사해 이 페이지가 그대로 뚫렸다)",
        (emails, note))
    chk(emails == ["allowed-r218@example-corp.co.kr"] and note == "하위 /about",
        "★★★ 대신 robots.txt 가 막지 않은 뒤쪽 경로(/about, 옛 [:4] 범위 안)의 "
        "메일은 정상적으로 수집된다(과잉차단 아님)", (emails, note))
finally:
    stop_server(srv1)

# ══════════════════════════════════════════════════════════════
print("\n[2] robots.txt 가 진입 경로 자체를 막을 때 — 기존 동작(사이트 전체 차단) 유지")
# ──────────────────────────────────────────────────────────────
routes2 = {
    "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /\n"),
    "/": (200, "text/html", "<html><body>never-seen-r218@example-corp.co.kr</body></html>"),
}
srv2 = make_server(routes2)
try:
    base_url = f"http://127.0.0.1:{srv2.server_port}"
    emails, note = CE.collect_one(base_url)
    chk(emails == [] and note == "robots.txt 차단",
        "STEP 진입 경로 자체가 막히면 여전히 그 자리에서 즉시 멈춘다(회귀 아님)",
        (emails, note))
finally:
    stop_server(srv2)

# ══════════════════════════════════════════════════════════════
print("\n[3] SUB_PATHS 뒤쪽 항목(/company, /inquiry) — [:4] 삭제로 이제 도달 가능")
# ──────────────────────────────────────────────────────────────
chk(len(CE.SUB_PATHS) == 6 and CE.SUB_PATHS[4:] == ["/company", "/inquiry"],
    "STEP SUB_PATHS 목록 자체는 6개 그대로다(참고용 확인)", CE.SUB_PATHS)
routes3 = {
    "/robots.txt": (200, "text/plain", "User-agent: *\nAllow: /\n"),
    "/": (200, "text/html", "<html><body>메일 없음</body></html>"),
    "/contact": (200, "text/html", "<html><body>메일 없음</body></html>"),
    "/contact.html": (200, "text/html", "<html><body>메일 없음</body></html>"),
    "/contactus": (200, "text/html", "<html><body>메일 없음</body></html>"),
    "/about": (200, "text/html", "<html><body>메일 없음</body></html>"),
    # 5번째 후보(/company)에만 메일을 둔다 — 예전 [:4] 라면 절대 못 본다.
    "/company": (200, "text/html", "<html><body>다섯번째 found-r218@example-corp.co.kr</body></html>"),
}
srv3 = make_server(routes3)
try:
    base_url = f"http://127.0.0.1:{srv3.server_port}"
    emails, note = CE.collect_one(base_url)
    chk(emails == ["found-r218@example-corp.co.kr"] and note == "하위 /company",
        "★★★ 다섯 번째 후보 경로(/company)까지 실제로 시도해 메일을 찾는다"
        "(예전엔 [:4] 슬라이스 때문에 앞 4개만 보고 '이메일 없음'으로 끝났다)",
        (emails, note))
finally:
    stop_server(srv3)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
