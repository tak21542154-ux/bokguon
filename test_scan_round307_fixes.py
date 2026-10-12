# -*- coding: utf-8 -*-
"""스캔 307라운드 회귀 — test_firstday.py 가 firstday_server.py 의 사본을
   손으로 다시 써서, 274라운드가 원본에 세운 안전장치 2개(운영DB 오발방지·
   포트 이중바인딩 방지)를 하나도 못 물려받던 결함[심각], 이 세션 사상
   첫 정밀조사한 정밀조사 Agent가 발견 — Agent 자신이 조사프롬프트의
   "한번도 조사 안 됨" 전제를 재확인 과정에서 스스로 검증(run_all_tests.py
   전체 등록 상태 268개 전수대조는 완벽히 1:1 — 별도 결함 없음, app.py의
   확신에 찬 주석 여러 건도 재검증해 전부 클린, admin.js 등 금액서식
   형제드리프트도 78라운드 이후 새 사례 없음. scratch_r171_repro.py 는
   아무 데서도 안 쓰이는 죽은 파일이라고 확인만 하고 삭제는 이번 라운드
   범위 밖으로 둠 — 조사가 코드 삭제까지 권한을 갖지 않음).

  [1][심각] Windows 의 Werkzeug 개발서버는 같은 host:port 이중 바인딩을
      예외 없이 허용한다(274라운드가 이미 netstat 으로 실측). 그래서
      firstday_server.py(수동 리허설 도구)는 app.run() 전에 포트를 직접
      probe 해 이미 점유돼 있으면 SystemExit 하는 가드를 갖고 있는데,
      test_firstday.py 는 **같은 부트스트랩 코드를 문자열로 다시 써서**
      임시 firstday_server.py 사본을 만들었다 — 그 사본에는 이 가드도,
      운영DB 오발방지 가드도 둘 다 없다. 즉 이전 실행이 비정상 종료(세션
      강제종료·크래시)해 포트 8790 에 스테일 프로세스가 남아 있으면,
      다음 test_firstday.py 실행은 그 사실을 전혀 모른 채 새 프로세스를
      또 띄우고, 헬스체크 폴링이 어느 쪽이 응답하는지 구분 못 해 **옛
      코드를 대상으로 60단계 전부를 돌리고도 "통과"를 보고**할 수 있었다
      (실측: 격리 임시포트에서 스테일 리스너를 만든 뒤 사본 방식 그대로
      재현 — 예외 없이 계속 공존).
      근본 수정: 사본을 없앴다 — test_firstday.py 가 이제 firstday_server.py
      **원본을 그대로** 서브프로세스로 불러 BOKGUON_DB_PATH·
      BOKGUON_FIRSTDAY_PORT 두 값만 환경변수로 오버라이드한다(firstday_
      server.py 쪽은 이 두 값을 os.environ.setdefault() 로 받도록 수정 —
      호출자가 이미 정했으면 존중, 손으로 직접 실행할 때는 기존 기본값
      그대로). 이제 원본이 앞으로 더 강화돼도 이 테스트가 자동으로 그
      보호를 물려받는다(사본을 또 안 쓰므로 이번 결함 자체가 구조적으로
      재발할 수 없다).

  ⚠ 이 테스트는 진짜 firstday_server.py 를 격리 임시포트·임시DB 로 실제
    서브프로세스 실행해 포트충돌 가드가 실제로 작동함을 검증한다(운영
    포트 8771·리허설 포트 8790 은 전혀 안 건드림). 회귀 전체(60+단계)는
    이 라운드 수정 직후 `python test_firstday.py` 를 실제로 완주시켜
    "첫날 완주 62/62 — 막힌 지점 없음"을 이미 별도로 확인했다(이 파일은
    그 무거운 전체 리허설을 반복하지 않고 이번 결함의 핵심 메커니즘만
    빠르게 격리 검증한다).

      python test_scan_round307_fixes.py
"""
import io
import os
import socket
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


TEST_FIRSTDAY_SRC = read("test_firstday.py")
FIRSTDAY_SERVER_SRC = read("firstday_server.py")

print("=" * 72)
print("  스캔 307라운드 회귀 — firstday 리허설 사본의 안전장치 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk('io.open(srv' not in TEST_FIRSTDAY_SRC and "import io" not in TEST_FIRSTDAY_SRC,
    "★★★★★ test_firstday.py 가 더는 firstday_server.py 의 사본을 문자열로 다시 쓰지 않는다"
    "(고치기 전엔 274라운드의 두 가드를 하나도 못 물려받는 사본이 있었다)")
chk('subprocess.Popen([PY, os.path.join(SRC, "firstday_server.py")]' in TEST_FIRSTDAY_SRC,
    "★★★★★ 대신 firstday_server.py 원본을 그대로 서브프로세스로 부른다")
chk('"BOKGUON_DB_PATH": DB, "BOKGUON_FIRSTDAY_PORT": str(PORT)' in TEST_FIRSTDAY_SRC,
    "STEP DB 경로·포트 두 값만 환경변수로 오버라이드한다(원본 코드 자체는 안 건드림)")
chk('PORT = int(os.environ.get("BOKGUON_FIRSTDAY_PORT", "8790"))' in FIRSTDAY_SERVER_SRC,
    "★★★★ firstday_server.py 의 포트가 이제 환경변수로 오버라이드 가능하다"
    "(고치기 전엔 8790 고정이라 사본을 안 쓰고는 test_firstday.py 가 원본을 그대로 못 불렀다)")
chk('os.environ.setdefault("BOKGUON_DB_PATH"' in FIRSTDAY_SERVER_SRC,
    "STEP BOKGUON_DB_PATH 도 setdefault 라 호출자가 이미 정한 값을 그대로 존중한다"
    "(손으로 직접 실행할 때는 여전히 레포 안 firstday.db 로 기본 동작 — 회귀 없음)")
chk("raise SystemExit" in FIRSTDAY_SERVER_SRC and FIRSTDAY_SERVER_SRC.count("raise SystemExit") == 2,
    "STEP 274라운드의 두 가드(운영DB·포트충돌)가 원본에 그대로 남아 있다(이번 라운드가 안 건드림)")

# ============================================================
print("\n[2] 실행 — 포트가 이미 점유돼 있으면(스테일 프로세스 가정) 새 실행이 조용히 공존하지 않는가")
# ------------------------------------------------------------


def _find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    return s, port


def _launch_real_firstday_server(port, db_path):
    """이번 라운드가 고친 실제 방식 — 원본을 그대로, 환경변수 두 개만 오버라이드."""
    env = dict(os.environ)
    env["BOKGUON_DB_PATH"] = db_path
    env["BOKGUON_FIRSTDAY_PORT"] = str(port)
    return subprocess.Popen([PY, os.path.join(HERE, "firstday_server.py")], cwd=HERE, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")


def _old_style_stub_bootstrap(port, db_path):
    """★ 참고용 — 이번 라운드가 지운 옛 방식을 그대로 재현한다(실제 파일은 이제
    이렇게 안 쓴다). test_firstday.py 105~113행에 실제로 있던 문자열 그대로 —
    가드가 전혀 없다는 걸 보여주기 위한 대조군일 뿐, 실제 코드에서 가져온 게
    아니라 이 테스트 파일 안에서만 재현한다(실제 파일을 되돌리지 않는다)."""
    stub_dir = tempfile.mkdtemp(prefix="round307_oldstyle_")
    stub = os.path.join(stub_dir, "firstday_server_oldstyle.py")
    io.open(stub, "w", encoding="utf-8").write(
        "# -*- coding: utf-8 -*-\nimport os, sys\n"
        f"os.environ['BOKGUON_DB_PATH'] = r'{db_path}'\n"
        "os.environ['BOKGUON_ENV'] = 'dev'\n"
        "os.environ['BOKGUON_OTP_POLICY'] = 'off'\n"
        "os.environ['BOKGUON_SEED_DEMO'] = '0'\n"
        f"sys.path.insert(0, r'{HERE}')\nos.chdir(r'{HERE}')\nimport app\n"
        f"app.app.run(host='127.0.0.1', port={port}, threaded=True, debug=False, use_reloader=False)\n")
    return subprocess.Popen([PY, stub], cwd=stub_dir,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")


def _stop(proc, timeout=5):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except Exception:
            proc.kill()
    try:
        return proc.communicate(timeout=3)
    except Exception:
        return "", ""


_dummy_sock, _collision_port = _find_free_port()
_dummy_sock.listen(1)   # 스테일 프로세스 대역 — 이 포트를 이미 누가 점유 중인 상태를 흉내낸다
try:
    _tmp1 = tempfile.mkdtemp(prefix="round307_new_")
    proc_new = _launch_real_firstday_server(_collision_port, os.path.join(_tmp1, "firstday.db"))
    time.sleep(2.0)
    rc_new = proc_new.poll()
    out_new, err_new = _stop(proc_new)
    chk(rc_new is not None and rc_new != 0,
        "★★★★★ 이번 라운드가 고친 방식(원본을 그대로 부름)은 포트 충돌 시 조용히 "
        "공존하지 않고 즉시 비정상 종료한다(exit code 확인)", (rc_new, out_new[-300:], err_new[-300:]))
    chk("포트" in (out_new + err_new) and "이미" in (out_new + err_new),
        "STEP 종료 사유가 포트 충돌임을 명확한 한글 문구로 알린다(무기명 크래시 아님)",
        (out_new, err_new))
finally:
    _dummy_sock.close()

# ============================================================
print("\n[3] 대조군 — 옛 방식(Werkzeug 프로세스 두 개)은 정확히 같은 상황에서 공존했는가")
# ------------------------------------------------------------
#  ⚠ [2]의 대조엔 일반 소켓을 스테일 프로세스로 썼는데, 실제 결함은
#    Werkzeug 서버끼리(둘 다 allow_reuse_address 를 켬)일 때만 재현된다 —
#    한쪽이 일반 소켓이면 Windows 가 WSAEACCES 로 그냥 막아 버려(실측: 이
#    조합에서 실제로 그렇게 됨) 옛 방식도 우연히 안전해 보인다. 274라운드
#    자신의 실측·정밀조사 Agent의 재현 둘 다 "Werkzeug 대 Werkzeug"였다 —
#    같은 조건으로 맞춰야 옛 결함이 정확히 재현된다.
_free_sock, _collision_port2 = _find_free_port()
_free_sock.close()  # 포트 번호만 빌리고 바로 놓는다 — 이번엔 진짜 Werkzeug 가 그 번호를 잡는다
_tmp_a = tempfile.mkdtemp(prefix="round307_stale_")
proc_stale = _old_style_stub_bootstrap(_collision_port2, os.path.join(_tmp_a, "firstday.db"))
try:
    _up = False
    for _ in range(20):
        time.sleep(0.3)
        _probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _probe.settimeout(0.3)
        try:
            _up = _probe.connect_ex(("127.0.0.1", _collision_port2)) == 0
        finally:
            _probe.close()
        if _up:
            break
    chk(_up, "STEP (사전조건) 스테일 역의 Werkzeug 프로세스가 실제로 그 포트에서 응답한다", _up)

    _tmp_b = tempfile.mkdtemp(prefix="round307_new2_")
    proc_dupe = _old_style_stub_bootstrap(_collision_port2, os.path.join(_tmp_b, "firstday.db"))
    time.sleep(2.0)
    rc_dupe = proc_dupe.poll()
    out_dupe, err_dupe = _stop(proc_dupe)
    chk(rc_dupe is None,
        "★★★★★ 대조군 — 이번 라운드가 지운 옛 방식(사본을 손으로 다시 씀)은 이미 "
        "떠 있는 같은 방식의 프로세스와 포트가 겹쳐도 예외·종료 없이 계속 함께 "
        "살아있었다(고쳐야 했던 바로 그 결함 — Windows 의 Werkzeug 대 Werkzeug 이중"
        "바인딩 허용, 274라운드가 이미 실측한 것과 같은 메커니즘). 이 상태로는 "
        "test_firstday.py 의 헬스체크가 스테일 프로세스와 새 프로세스를 구분할 "
        "방법이 없다", (rc_dupe, out_dupe[-300:], err_dupe[-300:]))
finally:
    _stop(proc_stale)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
