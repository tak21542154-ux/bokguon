# -*- coding: utf-8 -*-
"""스캔 274라운드 회귀 — 첫날재현 도구(firstday_server.py) 결함 3건
   (이 세션에서 사상 첫 주조사 — "자동화 파이프라인에서는 죽은 코드지만
   사람이 손으로 반복 실행해 온 도구"로 판정된 파일. 정밀조사 Agent가
   발견, 독립 재검증 후 수정).

  [1] db.py 의 운영DB 안전장치는 진입점 파일명이 "test_"로 시작할 때만
      발동한다 — 이 파일은 해당 안 돼 가드의 보호를 못 받는다. 오늘은
      BOKGUON_DB_PATH 를 먼저 정하는 줄이 항상 먼저 실행돼 문제가 없지만,
      그건 "내용이 우연히 안 틀렸다"는 것일 뿐이다(실측: 이 이름 그대로
      에서 그 줄을 생략하면 가드가 전혀 안 걸리고 운영 DB 경로를 그대로
      문다). import app 직전에 실제 환경값을 마지막으로 한 번 더 확인해
      운영 DB 파일과 같은 경로면 확실히 막도록 수정.

  [2] Werkzeug 개발서버가 Windows 에서 같은 host:port 이중 바인딩을
      막지 않는다 — 예외도 트레이스백도 없이 두 프로세스가 같은 포트를
      나눠 쓴다(실측: 동일 스크립트를 두 번 실행 → netstat 으로 두 PID가
      동시에 LISTENING, 첫 프로세스를 죽여도 healthz 가 계속 200이라
      두 번째가 실제로 요청을 처리하고 있었음을 확인). app.run() 전에
      포트가 이미 쓰이고 있는지 직접 확인하도록 수정.

  [3] 특정 사용자 계정 절대경로가 3곳에 하드코딩돼 있었다(형제
      test_firstday.py 는 이미 self-path 계산으로 이 문제를 피해 간다).
      HERE = os.path.dirname(os.path.abspath(__file__)) 로 통일.

  ⚠ 이 테스트는 이 파일 자신의 고정 포트(8790)와 격리 DB 를 쓴다 —
    운영 포트(8771)·운영 DB 는 절대 건드리지 않는다.

      python test_scan_round274_fixes.py
"""
import io
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PORT = 8790
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


SRC = read("firstday_server.py")

print("=" * 72)
print("  스캔 274라운드 회귀 — firstday_server.py DB가드사각·이중바인딩")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk(SRC.count(r"C:\Users\개발자3") == 0,
    "★★★★ 특정 사용자 절대경로 하드코딩이 사라졌다(고치기 전엔 3곳)")
chk("HERE = os.path.dirname(os.path.abspath(__file__))" in SRC,
    "STEP 형제 test_firstday.py 와 같은 self-path 계산을 쓴다")
chk("_actual_db_path" in SRC and "_prod_db_path" in SRC and "raise SystemExit" in SRC,
    "★★★★★ import app 직전에 실제 DB 경로가 운영 파일과 같은지 마지막으로 확인한다")
chk("connect_ex" in SRC,
    "★★★★★ app.run() 전에 포트 선점 여부를 직접 확인한다"
    "(고치기 전엔 Windows 이중 바인딩을 그대로 허용했다)")

i_check = SRC.index("_actual_db_path = ")
i_port_check = SRC.index("#  ⚠⚠ [라운드274] Werkzeug")
check_snippet = SRC[i_check:i_port_check]

# ============================================================
print("\n[2] 실행 — DB 경로 안전장치가 실제로 막는가(추출한 실제 검사코드 그대로 실행)")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round274_")


def _run_check(env_setup_lines):
    """추출한 실제 검사코드를 서로 다른 사전조건으로 서브프로세스에서 실행."""
    script = (
        "import os, socket, sys\n"
        f"HERE = {HERE!r}\n"
        + env_setup_lines + "\n"
        + check_snippet + "\n"
        "print('CHECK_PASSED_THROUGH')\n"
    )
    path = os.path.join(_tmpdir, "probe.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(script)
    #  ⚠ run_all_tests.py 가 배터리 전체에 BOKGUON_DB_PATH 를 미리 정해 두므로,
    #    이 자식 프로세스가 그 값을 그대로 물려받으면 "아예 안 정한 상황"을
    #    재현하려 해도 실제로는 물려받은 값이 있어 재현이 안 된다(실측:
    #    독립 실행 땐 통과하다가 run_all_tests.py 하위에서만 이 특정 검사가
    #    깨졌다). 이 환경만은 명시적으로 비운 사본을 써서 배터리 컨텍스트와
    #    무관하게 항상 같은 조건으로 검증한다.
    env = dict(os.environ)
    env.pop("BOKGUON_DB_PATH", None)
    r = subprocess.run([PY, path], capture_output=True, text=True, encoding="utf-8",
                       timeout=15, env=env)
    return r.returncode, r.stdout, r.stderr


try:
    rc1, out1, err1 = _run_check("# BOKGUON_DB_PATH 를 아예 안 정함(실수로 줄이 빠진 상황 재현)")
    chk(rc1 != 0 and "CHECK_PASSED_THROUGH" not in out1 and "운영 데이터를 열 수는 없습니다" in err1,
        "★★★★★ BOKGUON_DB_PATH 가 안 정해져 있으면 막는다(고치기 전엔 이 경로가 무방비였다)",
        (rc1, out1, err1))

    rc2, out2, err2 = _run_check(
        "os.environ['BOKGUON_DB_PATH'] = os.path.join(HERE, 'bokguon.db')  "
        "# 실수로 운영 파일 경로를 그대로 넣은 상황 재현")
    chk(rc2 != 0 and "CHECK_PASSED_THROUGH" not in out2,
        "★★★★★ 운영 DB 파일과 같은 경로를 가리키면 막는다", (rc2, out2, err2))

    rc3, out3, err3 = _run_check(
        f"os.environ['BOKGUON_DB_PATH'] = {os.path.join(_tmpdir, 'firstday_probe.db')!r}"
        "  # 정상 상황(대조군) — 진짜 격리 DB 경로")
    chk(rc3 == 0 and "CHECK_PASSED_THROUGH" in out3,
        "STEP 대조군 — 정상적인 격리 DB 경로면 그대로 통과한다(과잉차단 아님)", (rc3, out3, err3))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드274 [2] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — 포트가 이미 쓰이고 있으면 이중바인딩 대신 명확히 거부하는가")
# ------------------------------------------------------------
try:
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", PORT))
    blocker.listen(1)
    try:
        r = subprocess.run([PY, "firstday_server.py"], cwd=HERE,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=15)
    finally:
        blocker.close()
    chk(r.returncode != 0, "STEP 포트 충돌 시 0이 아닌 종료코드로 끝난다")
    chk(f"포트 {PORT}에 이미" in r.stderr,
        "★★★★★ 포트 충돌을 명확한 한국어 메시지로 거부한다"
        "(고치기 전엔 예외·메시지 없이 두 프로세스가 같은 포트를 나눠 썼다)",
        r.stderr[-300:])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드274 [3] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[4] 실행 — 정상 기동은 여전히 되는가(회귀 없음)")
# ------------------------------------------------------------
try:
    proc = subprocess.Popen([PY, "firstday_server.py"], cwd=HERE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    up = False
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/healthz", timeout=1) as resp:
                up = resp.status == 200
                break
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.2)
    proc.kill()
    proc.wait(timeout=10)
    chk(up, "★★★★ 정상 상황에서는 그대로 기동하고 healthz 가 응답한다(회귀 없음)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드274 [4] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
