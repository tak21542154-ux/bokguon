# -*- coding: utf-8 -*-
"""스캔 532라운드 회귀 — run_all_tests.py 의 유일한 자식 스포너 run() 이
   PYTHONIOENCODING 을 자식에게 안 넘겨, 배터리를 부르는 셸이 그 값을 우연히
   갖고 있지 않으면(예: 이 저장소의 Bash 도구 호출) UNIT 400여 개 중 자체
   방어(sys.stdout.reconfigure) 없는 다수가 **전부 실제 결함과 무관하게**
   UnicodeEncodeError 로 FAIL 처리되던 결함.

   직접 조사(하위위임 없음) — 지시받은 6개 후보(알림 재시도 큐·파일 정리·
   타임존 경계·페이지네이션 상한·관리자 등급 경계·협력사 탈퇴 정합성)를
   전부 실측 대조했으나 전부 클린이었다(알림 SMS/웹훅 재시도는 round84·144·
   200·232·262·412 로 이미 CAS+request_id+최종알림까지 촘촘, 사진 파일
   정리는 case 취소 두 경로 다 photo가 생기기 전 단계에서만 취소 가능해
   원천적으로 무관하고 명시적 사진삭제(api_photo_delete)는 이미 트랜잭션
   안에서 판정→커밋 후 휴지통 이동, 타임존은 round68·419 가 app.py·db.py
   전체의 naive datetime.now()를 이미 KST-aware로 통일했고 다른 8개 모듈도
   date.today() 포함 전수 재확인 결과 잔여 없음, 활동로그·사건목록·엑셀 6곳+
   CSV 1곳 전부 상한 있고 수식주입 방어(_xl_safe/_csv_safe)도 통일, 최고관리자
   경계는 데코레이터 21곳+인라인 체크(api_insurer_credentials 등) 전부
   일관되고 정산 undo도 이체완료는 구조적으로 되돌릴 수 없게 막혀 있음,
   협력사·보험사 exit gate(_partner_demote_gate·_insurer_exit_load)도
   round136·437·476·505 로 이미 촘촘). 그래서 각도를 "app.py 안의 새 결함"
   에서 "이 라운드들의 결과를 실제로 증명하는 배터리 자체가 믿을 만한가"로
   옮겨, --quick 배터리를 실제로 동기 실행해 봤다.

   실측 — `python run_all_tests.py --quick` 을 이 세션의 Bash 도구로 그대로
   실행하니 report() 의 최종 "실패" 목록에 round166 부터 round526 대까지
   (기능 회귀 8개 포함) 거의 전부가 찍혔다. round166 을 단독으로
   `python -u test_scan_round166_fixes.py` 로 직접 실행해 원인을 좁혔더니
   4번째 줄 print() 에서 바로 `UnicodeEncodeError: 'cp949' codec can't
   encode character '\\u2014'`로 죽었다(em dash 하나). round250·300·500 도
   동일 지점에서 동일 예외로 재현 — round 번호와 무관한 공통 원인임을 확인.

   근본원인 — run_all_tests.py:run()(자식을 스폰하는 유일한 지점, UNIT·HTTP·
   STANDALONE 세 목록이 전부 이 함수 하나를 공유)이 `_env = dict(os.environ)`
   로 **현재 프로세스의 환경을 그대로만** 물려준다. 자식은
   `subprocess.run(..., capture_output=True)`로 뜨므로 콘솔이 전혀 없는
   순수 파이프 stdout 을 받는데, PYTHONIOENCODING 이 없으면 파이썬은 이
   서비스가 도는 한국어 윈도의 OS 로케일(cp949)로 그 파이프를 연다 — 회귀
   파일 대부분(round166·250·300·500 등, 자체 reconfigure 방어가 없는 다수)은
   첫 print() 부터 "—"(em dash)를 쓰므로 그 자리에서 즉사한다. 이 배터리를
   부르는 셸이 **우연히** PYTHONIOENCODING 을 이미 갖고 있으면(이 PC의
   PowerShell $PROFILE 이 실측: `utf-8:surrogateescape`) 자식도 물려받아
   안 죽지만, 그 프로필을 안 읽는 셸(Bash 도구·예약작업·CI·새 사용자 프로필
   등)로 실행하는 순간 이 실행기 자신은 몰래 무해해 보여도(부모 프로세스는
   Bash 도구 쪽 pty 유사 채널 덕에 별문제 없이 진행되는 것으로 실측) 자식
   전부가 이 이유 하나로 대량 거짓 FAIL 을 낸다 — round518·519 가 이미
   "이 저장소의 단독 실행 CLI 27개+6개가 cp949 콘솔에서 죽는다"를 파고들어
   각 파일에 개별 방어를 심었지만, 그 조사 범위는 독립 CLI 도구였지 이
   실행기 자신의 자식-스포너는 다루지 않았다 — 지금까지 남아 있던 사각지대.

   형제 방어 그대로 이식 — 이 저장소는 이미 이 정확한 상황("내가 띄우는
   하위 프로세스의 stdout 이 파이프라 cp949 로 죽을 수 있다")에 대한 관례가
   있다: test_scan_round6·7·31·34·49_fixes.py·test_fresh_db.py·
   test_firstday.py 전부 **자기가 여는** 하위 프로세스의 env 딕셔너리에
   `PYTHONIOENCODING="utf-8"` 를 넣는다. run_all_tests.py:run() 은 그 관례를
   따라 하지 않던 이 저장소의 유일한 "모든 회귀 파일을 실제로 실행하는"
   지점이었다 — 새 정책·새 헬퍼 없이, 이미 있는 그 관례를 이 한 지점에만
   추가했다(_env.setdefault("PYTHONIOENCODING", "utf-8"), run_all_tests.py
   516행 부근). setdefault 라서 호출 셸이 이미 다른 값을 정해 뒀으면(예:
   round518·519 자신의 cp949 강제 재현 테스트가 **자기 하위**에 여는 별도
   env 딕셔너리 — 이 실행기의 run() 을 거치지 않으므로 애초에 이 변경과
   무관) 그대로 존중한다.

   회귀 검사 — [1] 소스: run() 함수 본문에 setdefault 줄이 subprocess.run
   호출보다 앞에 정확히 있다. [2] 실행(모킹) — run_all_tests 를 import 해
   subprocess.run 을 스텁으로 바꿔치기하고 run() 을 호출, 실제로 전달되는
   env 딕셔너리에 PYTHONIOENCODING=utf-8 이 들어 있음을 확인 — 이미 다른
   값이 설정된 경우엔 안 덮어씀(setdefault 의미)도 함께 확인. [3] 실행
   (진짜 서브프로세스, end-to-end) — PYTHONIOENCODING 을 없앤 환경에서 이
   실행기의 진짜 run() 함수로 round166 회귀를 실제로 스폰해 성공함을 확인
   (그 파일 자신은 손대지 않고, 이 실행기의 실제 fixed 코드로 실제 크래시
   시나리오를 재현·해소). [4] 되돌림-증명 — run_all_tests.py 파일 자체는
   건드리지 않고(동시편집 세션이 이 파일도 같이 건드릴 수 있는 환경, 기존
   라운드들의 표준 관례) 이 라운드 수정 **이전**의 원래 run() 본문(수정 전
   Read 로 확인한 그대로: `_env = dict(os.environ)` 뒤에 setdefault 줄이
   없는 버전)을 테스트 안에서 메모리 문자열로만 재구성해 같은 PYTHONIOENCODING
   없는 환경·같은 round166 파일로 실행 — 옛 코드는 UnicodeEncodeError 로
   즉사하고 지금 코드는 통과함을 대조해 이 회귀가 실제로 결함을 잡아낼
   능력이 있음을 증명한다.

       python test_scan_round532_fixes.py
"""
import ast
import io
import os
import subprocess
import sys
import tempfile

#  ⚠ 윈도 기본 콘솔은 cp949 라 em dash(—) 같은 문자를 print 하면
#    UnicodeEncodeError 로 죽는다 — 바로 이 라운드가 고치는 결함과 같은
#    부류라 이 테스트 자신부터 형제(round528~530 등)의 방어를 그대로 쓴다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 532라운드 회귀 — run_all_tests.py run() 이 자식에게 PYTHONIOENCODING 을")
print("  안 넘겨 콘솔 없는 셸에서 회귀 배터리 대다수가 거짓 FAIL 되던 결함")
print("=" * 72)

RAT_SRC_PATH = os.path.join(HERE, "run_all_tests.py")
RAT_SRC = open(RAT_SRC_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — run() 안에 PYTHONIOENCODING setdefault 가 subprocess.run 보다 앞에 있다")
# ══════════════════════════════════════════════════════════════════
_tree = ast.parse(RAT_SRC)
_run_fn = next((n for n in ast.walk(_tree)
                if isinstance(n, ast.FunctionDef) and n.name == "run"), None)
chk(_run_fn is not None, "run_all_tests.py 에 run() 함수가 있다")

_run_body_src = ast.get_source_segment(RAT_SRC, _run_fn) if _run_fn else ""
_idx_setdefault = _run_body_src.find('_env.setdefault("PYTHONIOENCODING"')
_idx_subproc = _run_body_src.find("subprocess.run(")
chk(_idx_setdefault != -1,
    "★★★★★ run() 본문에 _env.setdefault(\"PYTHONIOENCODING\", ...) 가 있다")
chk(_idx_subproc != -1, "run() 본문에 subprocess.run(...) 호출이 있다")
chk(_idx_setdefault != -1 and _idx_subproc != -1 and _idx_setdefault < _idx_subproc,
    "★★★★ setdefault 가 실제 자식을 띄우는 subprocess.run 보다 코드상 앞에 있다"
    "(자식이 뜨기 전에 env 에 반영돼야 의미가 있다)")
chk('_env.setdefault("PYTHONIOENCODING", "utf-8")' in _run_body_src,
    "  값 자체가 \"utf-8\"이다(형제 6곳과 같은 값)")

# ══════════════════════════════════════════════════════════════════
print("\n[2] 실행(모킹) — 실제 run() 을 호출해 subprocess.run 에 전달되는 env 를 가로채 확인")
# ══════════════════════════════════════════════════════════════════
sys.path.insert(0, HERE)
import importlib
import run_all_tests as RAT  # noqa: E402  (경로 등록 후 import)
importlib.reload(RAT)        # 혹시 이전 테스트가 이미 import 해 뒀어도 최신 소스로

_captured = {}


def _fake_subprocess_run(args, **kwargs):
    _captured["args"] = args
    _captured["env"] = kwargs.get("env")

    class _FakeCompleted:
        returncode = 0
        stdout = "가짜 통과\n"
        stderr = ""
    return _FakeCompleted()


_orig_subprocess_run = RAT.subprocess.run
_orig_pioenc = os.environ.pop("PYTHONIOENCODING", None)
try:
    RAT.subprocess.run = _fake_subprocess_run
    RAT.run("존재하지않는_더미.py", "더미 라벨")
    chk(_captured.get("env", {}).get("PYTHONIOENCODING") == "utf-8",
        "★★★★★ PYTHONIOENCODING 이 없던 환경에서 호출해도, 자식에게 넘어가는 "
        "env 에는 utf-8 이 채워져 있다", _captured.get("env", {}).get("PYTHONIOENCODING"))

    # setdefault 의미 확인 — 호출 셸이 이미 다른 값을 정했으면 덮어쓰지 않는다
    # (round518·519 류 cp949 강제 재현 시나리오를 이 변경이 방해하지 않아야 한다)
    os.environ["PYTHONIOENCODING"] = "cp949"
    _captured.clear()
    RAT.run("존재하지않는_더미.py", "더미 라벨2")
    chk(_captured.get("env", {}).get("PYTHONIOENCODING") == "cp949",
        "  이미 다른 값(cp949)이 설정돼 있으면 setdefault 가 덮어쓰지 않는다",
        _captured.get("env", {}).get("PYTHONIOENCODING"))
finally:
    RAT.subprocess.run = _orig_subprocess_run
    if _orig_pioenc is None:
        os.environ.pop("PYTHONIOENCODING", None)
    else:
        os.environ["PYTHONIOENCODING"] = _orig_pioenc

# ══════════════════════════════════════════════════════════════════
print("\n[3] 실행(진짜 서브프로세스) — PYTHONIOENCODING 없는 환경에서 진짜 run() 으로")
print("    round166 회귀를 실제로 스폰 — 지금 코드는 성공해야 한다")
# ══════════════════════════════════════════════════════════════════
TARGET = "test_scan_round166_fixes.py"   # 자체 reconfigure 방어가 없는 실존 회귀(사전 확인됨)
chk(os.path.exists(os.path.join(HERE, TARGET)),
    f"대조용 실존 회귀 파일 {TARGET} 가 있다(자체 UTF-8 방어 없음, 사전 확인됨)")

_tmpdir = tempfile.mkdtemp(prefix="round532_")
_orig_env_snapshot = dict(os.environ)
try:
    os.environ.pop("PYTHONIOENCODING", None)   # ★ "PYTHONIOENCODING 을 우연히도 안 가진 셸" 재현
    os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "r166.db")
    os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
    os.environ["BOKGUON_ENV"] = "dev"

    ok_now = RAT.run(TARGET, "round166 (진짜 run(), PYTHONIOENCODING 없는 환경)")
    chk(ok_now is True,
        "★★★★★ 지금(수정된) run() 은 PYTHONIOENCODING 없는 환경에서도 "
        "round166 회귀를 성공(returncode 0)으로 스폰한다", ok_now)
finally:
    os.environ.clear()
    os.environ.update(_orig_env_snapshot)

# ══════════════════════════════════════════════════════════════════
print("\n[4] 되돌림-증명 — run_all_tests.py 는 건드리지 않고, 수정 전 run() 본문을")
print("    메모리 문자열로만 재구성해 같은 환경에서 실행 — 옛 코드가 실제로 죽는지 확인")
# ══════════════════════════════════════════════════════════════════


def _old_run_before_round532(script, label, base=None):
    """이 라운드가 고치기 **전**의 run() 그대로(Read 로 확인한 원문 재구성).

    실제 파일에는 절대 쓰지 않는다 — 이 함수 안에서만, 메모리로만 재현한다.
    """
    _env = dict(os.environ)          # ← round532 이전: setdefault 줄이 없다
    if base:
        _env["BOKGUON_TEST_BASE"] = base
    r = subprocess.run([sys.executable, script], cwd=HERE,
                       capture_output=True, text=True, env=_env,
                       encoding="utf-8", errors="replace")
    return r


_tmpdir2 = tempfile.mkdtemp(prefix="round532_old_")
_orig_env_snapshot2 = dict(os.environ)
try:
    os.environ.pop("PYTHONIOENCODING", None)
    os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir2, "r166.db")
    os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir2, "uploads")
    os.environ["BOKGUON_ENV"] = "dev"

    r_old = _old_run_before_round532(TARGET, "round166 (옛 run() 재구성)")
    _old_out = (r_old.stdout or "") + (r_old.stderr or "")
    chk(r_old.returncode != 0,
        "★★★★★ round532 이전 run() 을 메모리로 재구성해 같은 환경(PYTHONIOENCODING "
        "없음)으로 돌리면 round166 이 실제로 실패한다(옛 결함 재현)", r_old.returncode)
    chk("UnicodeEncodeError" in _old_out and "cp949" in _old_out,
        "  실패 원인이 실제로 UnicodeEncodeError/cp949 다(엉뚱한 이유로 실패한 게 아님)",
        _old_out[-200:])

    # 대조군 — 지금(수정된) run() 은 같은 환경에서 성공한다(이미 [3]에서 확인했지만
    # 여기서 옛/새 코드를 나란히 다시 대조해 이 테스트가 진짜로 변별력이 있음을 보인다)
    r_new = RAT.run(TARGET, "round166 (대조: 지금 run())")
    chk(r_new is True,
        "★★★★ 바로 옆(같은 환경)에서 지금 run() 은 성공한다 — 옛/새 코드 차이가 "
        "PYTHONIOENCODING 유무 하나임을 대조로 확인", r_new)
finally:
    os.environ.clear()
    os.environ.update(_orig_env_snapshot2)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
