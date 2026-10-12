# -*- coding: utf-8 -*-
"""스캔 320라운드 회귀 — run_all_tests.py(검증 오케스트레이터 자신) 결함 3건,
   이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견(자체 재구성 기법으로
   "이 캠페인이 다음 라운드를 좌우하는 이 파일 자신은 정작 전담조사된 적이
   없다"는 사실을 확인).

   ① [중간] preflight() 가 서버 채널이 '개발'이 아님을 이미 감지하고도
      멈추지 않고 그 아래 실제 로그인 POST 까지 그 서버로 보냈다 —
      BOKGUON_TEST_BASE 가 실수로 운영을 가리키면(이 파일 독스트링이 이미
      인용하는 2026-08-06 사고와 같은 부류), 이 검증 스크립트 자신이 운영
      감사로그에 로그인 실패 기록을 남기고 계정 잠금 문턱에 기여할 뻔했다.
      채널 문제를 감지하면 그 자리에서 즉시 반환하도록 수정.
   ② [경미] HTTP 리스트가 라운드248에서 10→11개로 늘었는데, 중단 안내
      문자열 두 곳은 "HTTP 10개"로 그대로 남아 있었다 — len(HTTP) 참조로 교체.
   ③ [경미·구조적] local_build_hash() 가 app.py 의 _build_hash() 를 손으로
      그대로 베낀 사본인데(의도적 설계 — 검증기가 app.py 를 import 하면 안
      됨), 둘이 실제로 계속 같은 값을 내는지 확인하는 테스트가 없었다.
"""
import http.server
import json
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_scratch = tempfile.mkdtemp(prefix="bokguon_r320_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_scratch, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"

import run_all_tests as RAT  # noqa: E402

PASS = FAIL = 0
FAILED = []


def chk(cond, msg, detail=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {msg}")
    else:
        FAIL += 1
        FAILED.append(msg)
        print(f"  [FAIL] {msg}" + (f"   {detail}" if detail else ""))


print("=" * 74)
print("  스캔 320라운드 회귀 — run_all_tests.py 자기 자신의 결함 3건")
print("=" * 74)

print("\n[1] 실행 — preflight() 가 운영채널 감지 후 실제로 로그인 POST 를 안 보낸다")
_hits = []


class _StubHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # 콘솔 소음 방지

    def do_GET(self):
        _hits.append(("GET", self.path))
        if self.path == "/api/version":
            body = json.dumps({"channel": "운영", "build": "deadbeef"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        _hits.append(("POST", self.path))
        self.send_response(401)
        self.end_headers()


srv = http.server.HTTPServer(("127.0.0.1", 0), _StubHandler)
port = srv.server_address[1]
th = threading.Thread(target=srv.serve_forever, daemon=True)
th.start()
try:
    base = f"http://127.0.0.1:{port}"
    problems = RAT.preflight(base)
    login_calls = [h for h in _hits if h == ("POST", "/api/login")]
    chk(any("채널이 '운영'" in p for p in problems),
        "★★★★★ preflight() 가 운영채널을 실제로 감지한다(가짜 서버로 실측)", problems)
    chk(len(login_calls) == 0,
        "★★★★★ 운영채널 감지 후에는 실제 /api/login POST 를 절대 안 보낸다"
        "(고치기 전엔 감지하고도 그대로 로그인을 시도해 실제 요청이 나갔다)",
        _hits)
finally:
    srv.shutdown()
    th.join(timeout=3)

print("\n[2] 실행 — 빌드해시 문제(개발서버·낡은 코드)만 있으면 로그인은 여전히 시도한다"
      "(채널 문제와 달리 이건 막을 이유가 없다 — 회귀 없음 확인)")
_hits2 = []


class _StubHandler2(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        _hits2.append(("GET", self.path))
        body = json.dumps({"channel": "개발", "build": "deadbeef"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        _hits2.append(("POST", self.path))
        self.send_response(401)
        self.end_headers()


srv2 = http.server.HTTPServer(("127.0.0.1", 0), _StubHandler2)
port2 = srv2.server_address[1]
th2 = threading.Thread(target=srv2.serve_forever, daemon=True)
th2.start()
try:
    base2 = f"http://127.0.0.1:{port2}"
    problems2 = RAT.preflight(base2)
    login_calls2 = [h for h in _hits2 if h == ("POST", "/api/login")]
    chk(any("옛 코드" in p for p in problems2),
        "  개발채널인데 빌드해시가 다르면 그 문제는 정상적으로 잡힌다", problems2)
    chk(len(login_calls2) == 1,
        "★★★ 채널 문제가 없으면(개발서버) 빌드해시만 낡아도 로그인 시도는 그대로 한다"
        "(회귀 없음 — 채널 문제일 때만 조기반환해야 한다)", _hits2)
finally:
    srv2.shutdown()
    th2.join(timeout=3)

print("\n[3] 실행 — HTTP 리스트 개수 표기가 실제 len(HTTP) 와 일치한다")
chk(len(RAT.HTTP) == 11, "  HTTP 리스트는 현재 11개(라운드248이 test_otp.py 를 옮긴 뒤 기준)", len(RAT.HTTP))
RAT_SRC = open(os.path.join(HERE, "run_all_tests.py"), encoding="utf-8").read()
chk('f"[2] HTTP {len(HTTP)}개' in RAT_SRC,
    "★★★★ 중단 안내 문자열이 이제 len(HTTP) 를 참조한다(하드코딩된 '10개' 아님)")
chk('"[2] HTTP 10개' not in RAT_SRC,
    "★★★ 일반 안내문(현재 상태를 나타내는 자리)에는 더는 옛 고정 개수가 없다"
    "(과거 사고를 그대로 인용하는 report() 안 역사적 주석은 의도적으로 그대로 둠)")

print("\n[4] 실행 — local_build_hash() 가 app.py 의 _build_hash() 와 실제로 같은 값을 낸다")
import app as A  # noqa: E402
h_local = RAT.local_build_hash()
h_app = A._build_hash()
chk(h_local == h_app,
    "★★★★★ 검증기의 사본(local_build_hash)과 app.py 원본(_build_hash)이 "
    "지금 이 저장소 상태에서 실제로 같은 해시를 낸다(실측 — 둘 중 하나가 "
    "나중에 어긋나면 이 검사가 잡는다)", (h_local, h_app))

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
