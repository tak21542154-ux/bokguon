# -*- coding: utf-8 -*-
"""socket 전역 기본 타임아웃 회귀 — [420라운드 대조각도1][사용자결정 2026-09-10]

  420라운드가 발견하고 "제품판단 필요"로 기록만 해 둔 결함: 팝빌 SDK(및 그 내부
  linkhub)가 소켓에 타임아웃을 전혀 안 걸어(벤더 공식소스 직접 확인 — popbill/
  base.py PopbillBase._getConn()·linkhub/linkhub.py 둘 다 http.client.HTTPS/
  HTTPConnection(host) 을 timeout 인자 없이 만든다), 팝빌이 응답 없이 멈추면
  serve_waitress.py 의 스레드 풀(기본 8개)이 /api/outbox/send-now 등 동기호출
  경로에서 그 호출 몇 번만으로 전부 무한대기에 빠질 수 있었다. 후보 3개(SDK
  비공개속성 몽키패치 — 262라운드 기각·스레드+join 강제종료·전역
  socket.setdefaulttimeout) 중 사용자가 마지막(추천 후보)을 승인해 app.py
  모듈 최상위(app.py, "app = Flask(" 바로 앞)에 socket.setdefaulttimeout(N)
  을 걸었다 — 기본 30초, BOKGUON_SOCKET_TIMEOUT_SEC 로 조정 가능.

  이 파일은 그 인과관계를 실제로 증명한다(짐작이 아니라 실측):
    [1] app.py 소스에 실제로 그 줄이 있고, Flask 앱 생성보다 앞선다.
    [2] app.py 를 실제로 import 하면 프로세스 기본 소켓 타임아웃이 실제로
        바뀐다(기본값 30.0 확인 + 환경변수로 조정되는지 별도 프로세스로 확인).
    [3] 응답 없는 진짜 소켓 서버에 연결 — 전역 타임아웃 적용 전에는 안 걸리고,
        적용 후에는 정확히 그 시간 근처에서 socket.timeout/TimeoutError 가
        실제로 발생한다(30초를 그대로 기다리지 않고 같은 메커니즘을 짧은 값
        으로 재현 — 인과관계 증명력은 동일하고, 운영값 30.0 은 [2]에서 이미
        실측했다).
    [4] 메인 스레드에서 건 값이 나중에 만든 별도 워커 스레드의 새 소켓에도
        그대로 적용된다(waitress 워커 스레드 모델과 동일 구조 — 짐작 금지,
        직접 스레드를 띄워 확인).
    [5] 이미 자기 timeout 을 주는 호출(addr_search.py 6초·photo_ai.py 20초·
        app.py _webhook_send() 5초 등)은 더 짧은 전역 기본값이 걸려 있어도
        영향을 받지 않는다(explicit timeout 이 항상 우선).

      python test_socket_timeout.py
"""
import io
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  socket 전역 기본 타임아웃 회귀 — app.py: socket.setdefaulttimeout()")
print("=" * 72)

_ORIG_DEFAULT = socket.getdefaulttimeout()  # 끝나면 반드시 원상복구(이 프로세스 한정이라도)


def _blackhole_server():
    """accept 는 하되 아무것도 안 보내는 서버 — 클라이언트를 무기한 붙든다."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def _accept_and_hold():
        try:
            conn, _ = srv.accept()
            time.sleep(5)
            conn.close()
        except OSError:
            pass

    threading.Thread(target=_accept_and_hold, daemon=True).start()
    time.sleep(0.1)
    return srv, port


# ────────────────────────────────────────────────────────────────
print("\n[1] 소스 확인 — app.py 가 실제로 이 줄을 갖고 있는가")
# ────────────────────────────────────────────────────────────────
SRC = io.open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
chk('socket.setdefaulttimeout(int(env("BOKGUON_SOCKET_TIMEOUT_SEC"' in SRC,
    "★★★★★ app.py 모듈 최상위에 socket.setdefaulttimeout(...) 호출이 있다")
chk(SRC.count("socket.setdefaulttimeout(") == 1,
    "  socket.setdefaulttimeout 호출이 정확히 1곳뿐이다(중복 적용 없음)",
    SRC.count("socket.setdefaulttimeout("))
_i_sdt = SRC.find("socket.setdefaulttimeout(")
_i_flask = SRC.find("app = Flask(")
chk(_i_sdt != -1 and _i_flask != -1 and _i_sdt < _i_flask,
    "★★★★ socket.setdefaulttimeout() 이 Flask 앱 생성보다 앞서 실행된다"
    "(요청을 받기 전에 이미 적용돼 있어야 한다)")

# ────────────────────────────────────────────────────────────────
print("\n[2] 실제 import — app.py 를 그대로 불러오면 프로세스 기본 타임아웃이 바뀌는가")
# ────────────────────────────────────────────────────────────────
#  ⚠ app.py 는 import 시 DB.init_db() 를 실행한다 — 반드시 스크래치 DB로 격리한다
#    (418라운드 표준 방어 — 이 세션이 운영 bokguon.db 를 절대 건드리지 않기 위해).
_tmpdir = tempfile.mkdtemp(prefix="socktimeout_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
os.environ.setdefault("BOKGUON_LOG_FILE", os.path.join(_tmpdir, "test_socktimeout.log"))
os.environ.pop("BOKGUON_SOCKET_TIMEOUT_SEC", None)  # 기본값(30)이 실제로 먹는지 보려고 일부러 안 줌
sys.path.insert(0, HERE)

import app as APP  # noqa: E402  — 이 import 자체가 이 회귀의 핵심 관찰 대상
_after_import = socket.getdefaulttimeout()

chk(_after_import == 30.0,
    "★★★★★ app.py 를 import 하면 프로세스 기본 소켓 타임아웃이 30.0 으로 바뀐다"
    "(BOKGUON_SOCKET_TIMEOUT_SEC 미지정 시 기본값)", _after_import)

#  이미 import 된 모듈이라 이 프로세스 안에서 값만 다시 계산할 수는 없다(재import 불가) —
#  환경변수 조정력은 별도 프로세스로 독립 확인한다.
_env2 = dict(os.environ)
_env2["BOKGUON_SOCKET_TIMEOUT_SEC"] = "45"
_env2.setdefault("PYTHONIOENCODING", "utf-8")
_probe = ("import socket, sys; sys.path.insert(0, %r); import app; "
          "print(socket.getdefaulttimeout())" % HERE)
rp = subprocess.run([sys.executable, "-c", _probe], cwd=HERE,
                     capture_output=True, text=True, encoding="utf-8",
                     errors="replace", env=_env2, timeout=60)
chk("45.0" in (rp.stdout or ""),
    "★★★★ BOKGUON_SOCKET_TIMEOUT_SEC=45 를 주면 실제로 45.0 이 적용된다"
    "(별도 프로세스로 재확인 — 코드 재배포 없이 조정 가능함을 실측)",
    ((rp.stdout or "") + (rp.stderr or ""))[-300:])

socket.setdefaulttimeout(_ORIG_DEFAULT)  # 이 프로세스의 나머지 검사에 영향 주지 않게 원상복구

# ────────────────────────────────────────────────────────────────
print("\n[3] 인과관계 실측 — 응답 없는 진짜 소켓 서버: 적용 전엔 안 걸리고, 후엔 정확히 걸린다")
# ────────────────────────────────────────────────────────────────
#  30초를 그대로 기다리지 않는다 — 같은 메커니즘을 작은 값으로 재현해도 증명력은
#  동일하고(운영값 30.0 은 [2]에서 이미 실측), 배터리 전체 실행시간을 지킨다.
TEST_TIMEOUT = 1.0

print(f"\n[3-a] 전역 기본이 blocking(None)일 때 — 새 소켓은 timeout=None 으로 만들어진다")
socket.setdefaulttimeout(None)
srv_a, port_a = _blackhole_server()
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
chk(s.gettimeout() is None,
    "★★★★★ setdefaulttimeout(None) 상태에서 새로 만든 소켓은 timeout=None(blocking)이다"
    "(팝빌 SDK 가 지금까지 이 상태였다 — 응답이 없으면 문자 그대로 무기한 대기)",
    s.gettimeout())
s.connect(("127.0.0.1", port_a))
t0 = time.perf_counter()
_fired_early = None
try:
    s.settimeout(TEST_TIMEOUT * 2)   # 테스트 자신이 무한정 멈추지 않기 위한 별도 안전장치
    s.recv(16)
    _fired_early = False
except socket.timeout:
    _fired_early = True
elapsed_a = time.perf_counter() - t0
s.close()
srv_a.close()
chk(_fired_early is True and elapsed_a >= TEST_TIMEOUT * 2 - 0.3,
    f"  이 안전장치 시간({TEST_TIMEOUT*2}s) 이전에는 응답이 없어도 예외가 안 난다"
    f"(=진짜 무기한 대기 성질 확인, 안전장치 자체가 {elapsed_a:.2f}s 에 발동)")

print(f"\n[3-b] socket.setdefaulttimeout({TEST_TIMEOUT}) 이후 — 정확히 그 근처에서 예외가 실제로 난다")
socket.setdefaulttimeout(TEST_TIMEOUT)
srv_b, port_b = _blackhole_server()
s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
chk(s2.gettimeout() == TEST_TIMEOUT,
    f"★★★★★ setdefaulttimeout({TEST_TIMEOUT}) 이후 새로 만든 소켓은 timeout 인자를 준 적이"
    f" 없는데도 자동으로 그 값을 갖는다(팝빌 SDK 의 HTTPSConnection(host) 이 이렇게 걸린다)",
    s2.gettimeout())
t0 = time.perf_counter()
_raised = None
try:
    s2.connect(("127.0.0.1", port_b))
    s2.recv(16)
except OSError as e:                 # socket.timeout 은 OSError 의 하위클래스(3.10+)
    _raised = e
elapsed_b = time.perf_counter() - t0
s2.close()
srv_b.close()
chk(isinstance(_raised, (socket.timeout, TimeoutError)),
    "★★★★★ timeout 인자를 안 준 소켓 호출이 실제로 socket.timeout/TimeoutError 로 끊긴다"
    "(notify_popbill.send() 의 except Exception 이 이미 이 예외를 받아 (False, 사유)로"
    " 돌려주므로 발송 흐름은 안 막힌다)", type(_raised).__name__ if _raised else None)
chk(abs(elapsed_b - TEST_TIMEOUT) < 1.0,
    f"★★★★★ 예외가 정확히 설정한 시간({TEST_TIMEOUT}s) 근처에서 발생했다(실측 {elapsed_b:.2f}s)"
    f" — 임의 시점이 아니라 이 설정값 자체가 원인임을 증명", f"{elapsed_b:.3f}s")

socket.setdefaulttimeout(_ORIG_DEFAULT)

# ────────────────────────────────────────────────────────────────
print("\n[4] 스레드 간 전파 — waitress 워커 스레드 모델과 동일한 구조로 확인(짐작 금지)")
# ────────────────────────────────────────────────────────────────
socket.setdefaulttimeout(TEST_TIMEOUT)
_result = {}


def _worker():
    ws = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _result["timeout"] = ws.gettimeout()
    ws.close()


th = threading.Thread(target=_worker)
th.start()
th.join(timeout=5)
chk(_result.get("timeout") == TEST_TIMEOUT,
    "★★★★★ 메인 스레드에서 건 setdefaulttimeout 값이, 그 뒤에 만든 별도 워커 스레드가"
    " 새로 만드는 소켓에도 그대로 적용된다(serve_waitress.py 가 메인 스레드에서 이 값을"
    " 걸고 그 뒤 waitress 가 요청마다 새 워커 스레드를 쓰는 것과 정확히 같은 구조 —"
    " 프로세스 전역 상태이지 스레드 로컬이 아님을 실제로 확인)", _result.get("timeout"))

socket.setdefaulttimeout(_ORIG_DEFAULT)

# ────────────────────────────────────────────────────────────────
print("\n[5] 이미 자기 timeout 을 주는 호출은 이 전역값의 영향을 안 받는다")
# ────────────────────────────────────────────────────────────────
SMALL_GLOBAL = 0.3
BIGGER_EXPLICIT = 1.3
socket.setdefaulttimeout(SMALL_GLOBAL)
srv_c, port_c = _blackhole_server()
s3 = socket.create_connection(("127.0.0.1", port_c), timeout=BIGGER_EXPLICIT)
t0 = time.perf_counter()
_raised2 = None
try:
    s3.recv(16)
except OSError as e:
    _raised2 = e
elapsed_c = time.perf_counter() - t0
s3.close()
srv_c.close()
chk(elapsed_c > SMALL_GLOBAL * 2,
    f"★★★★★ timeout={BIGGER_EXPLICIT}s 로 직접 연 연결은 더 짧은 전역 기본값"
    f"({SMALL_GLOBAL}s) 을 무시하고 자기 값을 쓴다 — addr_search.py(6초)·photo_ai.py"
    f"(20초)·_webhook_send()(5초) 는 이 전역설정 이후에도 회귀 없음을 증명",
    f"{elapsed_c:.3f}s")
chk(isinstance(_raised2, (socket.timeout, TimeoutError)),
    "  (그 explicit timeout 자체는 정상적으로 발동한다 — 무한대기가 된 게 아니라"
    " 자기 설정값대로 정상 동작)", type(_raised2).__name__ if _raised2 else None)

socket.setdefaulttimeout(_ORIG_DEFAULT)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
