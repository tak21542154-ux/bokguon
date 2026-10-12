# -*- coding: utf-8 -*-
"""스캔 451라운드 회귀 — waitress 요청 본문 크기 상한 미설정, 1건.

app.py 의 MAX_CONTENT_LENGTH(BOKGUON_MAX_UPLOAD_MB, 기본 260MB)는 Flask
계층의 검사라 요청 스트림을 실제로 읽기 시작할 때만 발동한다. 그런데
serve_waitress.py 의 serve() 호출이 waitress 자신의
max_request_body_size 를 한 번도 지정하지 않아 waitress 기본값
1GB(waitress/adjustments.py)가 그대로 살아 있었다 — waitress 는 헤더를
다 읽은 뒤 본문 전체를 자기 버퍼(512KB 넘으면 디스크 tempfile 로 스풀)
에 다 받아야만 WSGI 앱(Flask)에 요청을 넘기므로, 260MB~1GB 사이 크기의
요청은 인증 없이도 디스크를 소모시키며 끝까지 받아들여진 뒤에야
거부됐다. serve_waitress.py 에 형제 상수(BOKGUON_MAX_UPLOAD_MB)와 같은
값(+여유)을 waitress 자신의 max_request_body_size 로도 넘기면, 헤더의
Content-Length 만 보고 본문을 한 바이트도 받기 전에 즉시 거부한다.

[1] 소스 확인 — serve_waitress.py 가 실제로 max_request_body_size 를
    지정하고, 그 값이 BOKGUON_MAX_UPLOAD_MB 에서 계산됨.
[2] 실제 메커니즘 재현(값은 테스트 속도를 위해 축소, 매커니즘은 동일) —
    같은 tiny WSGI 앱을 waitress 로 두 번 띄워, max_request_body_size 를
    준 쪽은 그 상한을 넘는 요청이 WSGI 앱에 전혀 도달하지 않고 거부됨을,
    (이 프로젝트의 옛 코드처럼) 안 준 쪽은 같은 요청이 WSGI 앱까지
    도달함을 실제 소켓 통신으로 실측 — 되돌림-증명.
"""
import io
import os
import socket
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 451라운드 회귀 — waitress 요청 본문 크기 상한 미설정")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
SRC = io.open(os.path.join(HERE, "serve_waitress.py"), encoding="utf-8").read()

chk("max_request_body_size=MAX_BODY_BYTES" in SRC,
    "★★★★★ serve() 호출이 max_request_body_size 를 실제로 넘긴다")
chk('MAX_BODY_BYTES = (int(os.environ.get("BOKGUON_MAX_UPLOAD_MB", "260")) + 10) * 1024 * 1024'
    in SRC,
    "★★★★★ 그 값이 app.py 와 같은 BOKGUON_MAX_UPLOAD_MB 에서 계산된다"
    "(형제 상수와 어긋나지 않음)")

APP_SRC = io.open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
chk('MAX_CONTENT_LENGTH=int(env("BOKGUON_MAX_UPLOAD_MB", "260")) * 1024 * 1024' in APP_SRC,
    "app.py 쪽 MAX_CONTENT_LENGTH 도 같은 환경변수를 씀(형제 확인용 대조군)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 waitress 메커니즘 재현 — 되돌림-증명(값은 축소, 메커니즘 동일)")
# ══════════════════════════════════════════════════════════════
try:
    from waitress import serve as waitress_serve

    LIMIT = 2 * 1024 * 1024      # 테스트용 2MB 상한(실제 배포는 270MB)
    OVERSIZED = 5 * 1024 * 1024  # 상한을 넘는 5MB 요청

    reached = {"limited": False, "unlimited": False}

    def _app_factory(key):
        def _app(environ, start_response):
            reached[key] = True
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"ok"]
        return _app

    def _free_port():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
        s.close()
        return p

    port_limited = _free_port()
    port_unlimited = _free_port()

    t1 = threading.Thread(
        target=lambda: waitress_serve(
            _app_factory("limited"), host="127.0.0.1", port=port_limited,
            max_request_body_size=LIMIT, ident="r451-limited"),
        daemon=True)
    #  ⚠ max_request_body_size 를 아예 안 준다 — 이 프로젝트의 450라운드
    #    이전 serve_waitress.py 와 정확히 같은(취약) 호출 형태다.
    t2 = threading.Thread(
        target=lambda: waitress_serve(
            _app_factory("unlimited"), host="127.0.0.1", port=port_unlimited,
            ident="r451-unlimited"),
        daemon=True)
    t1.start()
    t2.start()
    time.sleep(0.8)  # 두 서버가 accept 루프를 시작할 시간

    def _send_oversized(port):
        body = b"x" * OVERSIZED
        req = (
            f"POST / HTTP/1.1\r\nHost: 127.0.0.1\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
        ).encode("ascii") + body
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect(("127.0.0.1", port))
        try:
            s.sendall(req)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # 상한을 넘겨 서버가 먼저 연결을 끊어도 정상 시나리오
        resp = b""
        try:
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                resp += chunk
        except (socket.timeout, ConnectionResetError, OSError):
            pass
        s.close()
        return resp

    resp_limited = _send_oversized(port_limited)
    resp_unlimited = _send_oversized(port_unlimited)

    chk(not reached["limited"],
        "★★★★★ max_request_body_size 를 준 서버는 WSGI 앱에 전혀 도달 안 함"
        "(본문을 다 안 받고 거부)")
    chk(b"413" in resp_limited or b"Request Entity Too Large" in resp_limited
        or resp_limited == b"",
        "상한초과 요청이 413류 응답 또는 조기 연결종료로 처리됨", resp_limited[:200])

    chk(reached["unlimited"],
        "★★★★★ 상한 미설정(구코드와 동일) 서버는 같은 크기 요청이 실제로 "
        "WSGI 앱까지 도달한다(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명)")
    chk(b"200" in resp_unlimited,
        "상한 미설정 서버는 정상 200 응답을 돌려준다(수신 완료 증거)", resp_unlimited[:200])

except Exception as e:                                              # noqa: BLE001
    chk(False, "[2] 실제 waitress 재현 준비/실행", f"{type(e).__name__}: {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
