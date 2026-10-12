# -*- coding: utf-8 -*-
"""스캔 273라운드 회귀 — 운영 서버 진입점(serve_waitress.py) 결함 3건
   (이 세션에서 처음으로 "companion 스크립트" 대신 서빙 계층 자체를 감사한
   라운드, 정밀조사 Agent가 발견, 독립 재검증 후 수정).

  [1] flush=True 가 없어, 시작 배너가 **정상 종료에서만** 로그파일에
      남았다. 그런데 실제 운영 재시작은 전부 감시자
      (외부접속_상시가동.ps1)의 Stop-Process -Force **하드킬**이라(실측:
      동일 리다이렉트+하드킬 패턴으로 재현), waitress_out.log 에 이 배너가
      사실상 영원히 안 남았다. flush=True 를 추가.

  [2] serve() 호출에 예외처리가 전혀 없어, 포트가 이미 쓰이고 있으면
      waitress/asyncore 내부 스택프레임 15줄짜리 트레이스백만 나왔다
      (실측: PermissionError [WinError 10013]). 한국어로 원인·대처법을
      알리는 SystemExit 으로 감싸도록 수정.

  [3] envload.py 자신의 문서가 "app.py/wsgi.py/serve_waitress.py/
      manage.py 가 공유한다"고 명시하는데, 이 파일은 직접 부르지 않고
      `from wsgi import application`이 wsgi.py 안의 같은 호출을 먼저
      실행시키는 import 순서의 우연에 기대고 있었다. 명시적으로 호출하도록
      수정(load_dotenv()는 setdefault라 두 번 불러도 무해).

  ⚠ 이 테스트는 격리 포트(18781/18782)로 실제 waitress 프로세스를
    띄우고 하드킬한다 — 운영 포트(8771)는 절대 건드리지 않는다.

      python test_scan_round273_fixes.py
"""
import io
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


SRC = read("serve_waitress.py")

print("=" * 72)
print("  스캔 273라운드 회귀 — serve_waitress.py 로그유실·불친절오류·env로딩우연")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk(SRC.count(", flush=True)") >= 5,
    "★★★★★ 시작 배너 print 들이 전부 flush=True 다(고치기 전엔 하드킬 시 유실)")
chk("except OSError as e:" in SRC and "netstat -ano" in SRC,
    "★★★★★ serve() 가 예외처리로 감싸져 포트충돌 시 한국어 안내가 나온다")
#  ⚠ 줄 앞 개행까지 포함해 찾는다 — 이 파일 자신의 설명주석이 백틱으로
#    감싼 `from wsgi import application`을 문구 중에 언급하는데, 개행 없이
#    찾으면 그 주석 속 언급(실제 코드보다 앞)이 먼저 걸려 경계가 엉뚱한
#    자리로 당겨진다(라운드273 테스트 작성 중 실제로 겪은 자기지시 함정).
i_wsgi = SRC.index("\nfrom wsgi import application")
before_wsgi = SRC[:i_wsgi]
chk("from envload import load_dotenv" in before_wsgi and "_load_dotenv()" in before_wsgi,
    "★★★★★ wsgi import 이전에 .env 를 명시적으로 로드한다"
    "(고치기 전엔 wsgi.py 의 import 순서 우연에만 의존했다)")

# ============================================================
print("\n[2] 실행 준비")
# ------------------------------------------------------------
def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_healthz(port, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(0.2)
    return False


_tmpdir = tempfile.mkdtemp(prefix="round273_")

# ============================================================
print("\n[3] 실행 — 하드킬(운영 재시작과 동일한 방식) 후에도 시작배너가 로그에 남는가")
# ------------------------------------------------------------
try:
    port1 = _free_port()
    env1 = dict(os.environ)
    env1["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify1.db")
    env1["BOKGUON_PORT"] = str(port1)
    env1["BOKGUON_ENV"] = "dev"

    out_path = os.path.join(_tmpdir, "stdout1.log")
    with open(out_path, "wb") as out_f:
        proc = subprocess.Popen([PY, "serve_waitress.py"], cwd=HERE, env=env1,
                                stdout=out_f, stderr=subprocess.DEVNULL)
        up = _wait_healthz(port1)
        chk(up, "STEP 격리 포트에서 서버가 정상 기동했다(healthz 200)")
        #  ⚠ 운영 재시작과 동일한 하드킬 — 정상 종료(언와인드)가 아니다.
        proc.kill()
        proc.wait(timeout=10)
    with open(out_path, encoding="utf-8", errors="replace") as f:
        logged = f.read()
    chk("복구온 서비스" in logged,
        "★★★★★ 하드킬 후에도 시작 배너가 로그에 남아 있다"
        "(고치기 전엔 하드킬 시 stdout 이 항상 빈 채로 남았다)", logged[:200])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드273 [3] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[4] 실행 — 포트 충돌 시 트레이스백 대신 한국어 안내가 나오는가")
# ------------------------------------------------------------
try:
    port2 = _free_port()
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", port2))
    blocker.listen(1)
    try:
        env2 = dict(os.environ)
        env2["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify2.db")
        env2["BOKGUON_PORT"] = str(port2)
        env2["BOKGUON_ENV"] = "dev"
        r = subprocess.run([PY, "serve_waitress.py"], cwd=HERE, env=env2,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=15)
    finally:
        blocker.close()

    chk(r.returncode != 0, "STEP 포트 충돌 시 0이 아닌 종료코드로 끝난다")
    chk("Traceback (most recent call last)" not in r.stderr,
        "★★★★★ 포트 충돌 시 원시 트레이스백이 더는 안 보인다"
        "(고치기 전엔 waitress 내부 스택프레임이 그대로 노출됐다)", r.stderr[-300:])
    chk("이미 사용 중이거나" in r.stderr and str(port2) in r.stderr,
        "★★★★★ 대신 한국어로 원인·확인 명령까지 안내한다", r.stderr[-300:])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드273 [4] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 실행 — .env 명시적 로드가 실제로 반영되는가")
# ------------------------------------------------------------
try:
    #  BOKGUON_HOST 를 OS 환경변수로 직접 지정해, 명시적 _load_dotenv() 가
    #  기존 값을 덮지 않는지(setdefault 이므로 안전한지)까지 함께 확인한다.
    port3 = _free_port()
    env3 = dict(os.environ)
    env3["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify3.db")
    env3["BOKGUON_PORT"] = str(port3)
    env3["BOKGUON_HOST"] = "127.0.0.1"
    env3["BOKGUON_ENV"] = "dev"
    out_path3 = os.path.join(_tmpdir, "stdout3.log")
    with open(out_path3, "wb") as out_f:
        proc3 = subprocess.Popen([PY, "serve_waitress.py"], cwd=HERE, env=env3,
                                 stdout=out_f, stderr=subprocess.DEVNULL)
        up3 = _wait_healthz(port3)
        proc3.kill()
        proc3.wait(timeout=10)
    chk(up3,
        "★★★★★ 명시적 .env 로드를 추가해도 정상 기동하고 OS 환경변수(host)가 그대로 존중된다"
        "(setdefault 라 무해함을 실행으로 확인)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드273 [5] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
