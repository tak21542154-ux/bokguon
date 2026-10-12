# -*- coding: utf-8 -*-
"""스캔 275라운드 회귀 — 로컬 TLS 리허설 프록시(dev_tls_proxy.py) 결함 2건
   (같은 deploy_z.py 주석에서 "개발 전용"으로 언급된, 이 세션 사상 첫
   주조사 파일 — 정밀조사 Agent가 발견, 독립 재검증 후 수정).

  [1] Windows 는 SO_REUSEADDR 를 걸어도 같은 host:port 이중 바인딩을
      막지 않는다(firstday_server.py 274라운드가 먼저 발견한 것과 같은
      패턴). 실측: 같은 리슨포트로 두 인스턴스를 띄우면 둘 다 bind
      성공하고, 첫 프로세스를 죽여도 둘째가 조용히 이어받아 응답한다 —
      "재시작했다"고 믿기 쉬운데 실제로는 옛 프로세스가 계속 떠 있을 수
      있다. bind 전에 포트 선점 여부를 직접 확인하도록 수정.

  [2] TLS 핸드셰이크 실패가 완전히 무로그로 삼켜졌다(실측: 평문 바이트를
      HTTPS 포트로 보내면 로그 0줄) — 같은 파일의 형제(handle() 의
      백엔드 연결 실패)는 이미 print 로 남기는데 이 자리만 침묵했다.
      형제와 같은 형식으로 로그를 남기도록 수정.

  ⚠ 이 테스트는 격리 포트(18781 근방)만 쓴다 — 운영 포트(8771)는 절대
    건드리지 않는다(백엔드로 열어야 할 때도 존재하지 않는 포트만 쓴다).

      python test_scan_round275_fixes.py
"""
import io
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


SRC = read("dev_tls_proxy.py")

print("=" * 72)
print("  스캔 275라운드 회귀 — dev_tls_proxy.py 이중바인딩·핸드셰이크침묵")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_main = SRC.index("def main():")
main_body = SRC[i_main:]
chk("connect_ex" in main_body and "raise SystemExit" in main_body,
    "★★★★★ bind 전에 포트 선점 여부를 직접 확인한다"
    "(고치기 전엔 Windows 이중 바인딩을 그대로 허용했다)")
chk('TLS 핸드셰이크 실패' in SRC,
    "★★★★★ TLS 핸드셰이크 실패가 로그로 남는다(고치기 전엔 완전 침묵)")

# ============================================================
print("\n[2] 실행 준비")
# ------------------------------------------------------------
def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_tls_up(port, timeout=8):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1) as raw:
                with ctx.wrap_socket(raw, server_hostname="127.0.0.1"):
                    return True
        except (OSError, ssl.SSLError):
            time.sleep(0.2)
    return False


_tmpdir = tempfile.mkdtemp(prefix="round275_")
#  존재하지 않는 backend 포트 — 이 테스트는 프록시 자체의 동작만 보면 되고,
#  실제 백엔드(운영 8771 포함)에는 절대 연결을 시도할 필요가 없다.
_fake_backend_port = _free_port()

# ============================================================
print("\n[3] 실행 — 이미 쓰이는 포트면 이중바인딩 대신 명확히 거부하는가")
# ------------------------------------------------------------
try:
    listen_port = _free_port()
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", listen_port))
    blocker.listen(1)
    try:
        r = subprocess.run(
            [PY, "dev_tls_proxy.py", str(listen_port), str(_fake_backend_port)],
            cwd=HERE, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=15)
    finally:
        blocker.close()
    chk(r.returncode != 0, "STEP 포트 충돌 시 0이 아닌 종료코드로 끝난다")
    chk(f"포트 {listen_port}에 이미" in r.stderr,
        "★★★★★ 포트 충돌을 명확한 한국어 메시지로 거부한다"
        "(고치기 전엔 예외·메시지 없이 두 프로세스가 같은 포트를 나눠 썼다)",
        r.stderr[-300:])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드275 [3] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[4] 실행 — TLS 핸드셰이크 실패가 실제로 로그에 남는가")
# ------------------------------------------------------------
try:
    listen_port2 = _free_port()
    proc = subprocess.Popen(
        [PY, "dev_tls_proxy.py", str(listen_port2), str(_fake_backend_port)],
        cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1)
    try:
        up = _wait_tls_up(listen_port2)
        chk(up, "STEP 프록시가 정상 기동해 TLS 핸드셰이크를 받는다")

        #  평문 쓰레기 바이트를 HTTPS 포트로 — TLS 핸드셰이크 자체가 깨진다.
        with socket.create_connection(("127.0.0.1", listen_port2), timeout=3) as s:
            s.sendall(b"NOT-TLS-AT-ALL\r\n\r\n")
            try:
                s.recv(100)
            except OSError:
                pass
        time.sleep(0.5)
    finally:
        proc.kill()
        try:
            out, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            out = ""
    chk("TLS 핸드셰이크 실패" in (out or ""),
        "★★★★★ 평문 쓰레기를 보내면 핸드셰이크 실패가 로그에 남는다"
        "(고치기 전엔 로그 0줄이었다)", out)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드275 [4] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 실행 — 정상 기동·릴레이는 여전히 되는가(회귀 없음)")
# ------------------------------------------------------------
try:
    #  진짜 평문 echo 백엔드를 하나 띄워, 프록시가 TLS→평문 왕복 릴레이를
    #  여전히 정상 수행하는지까지 검증한다(운영 8771 은 전혀 안 건드림).
    echo_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    echo_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    echo_srv.bind(("127.0.0.1", 0))
    echo_port = echo_srv.getsockname()[1]
    echo_srv.listen(1)

    import threading

    #  ⚠ 단발성(accept 한 번)으로 짜면, _wait_tls_up() 자신의 실제 TLS
    #    핸드셰이크 프로브가 먼저 프록시→백엔드 연결을 한 번 소비해버려
    #    (핸드셰이크가 성공하면 프록시는 즉시 handle() 을 태워 backend 에
    #    붙는다) 정작 이 테스트의 진짜 페이로드가 accept 할 자리를 못
    #    찾고 멈춘다(실측으로 겪음). 여러 번 받아도 되게 루프로 돌린다.
    def _echo_forever():
        while True:
            try:
                conn, _ = echo_srv.accept()
            except OSError:
                return
            try:
                data = conn.recv(1024)
                if data:
                    conn.sendall(data)
            except OSError:
                pass
            finally:
                conn.close()

    threading.Thread(target=_echo_forever, daemon=True).start()

    listen_port3 = _free_port()
    proc3 = subprocess.Popen([PY, "dev_tls_proxy.py", str(listen_port3), str(echo_port)],
                             cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        up3 = _wait_tls_up(listen_port3)
        chk(up3, "STEP 정상 상황에서는 그대로 기동한다(회귀 없음)")

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection(("127.0.0.1", listen_port3), timeout=5) as raw:
            with ctx.wrap_socket(raw, server_hostname="127.0.0.1") as tls:
                tls.sendall(b"ROUND275-ECHO")
                back = tls.recv(1024)
        chk(back == b"ROUND275-ECHO",
            "★★★★ TLS→평문→TLS 왕복 릴레이가 바이트 그대로 정상 동작한다(회귀 없음)", back)
    finally:
        proc3.kill()
        proc3.wait(timeout=10)
        echo_srv.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드275 [5] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
