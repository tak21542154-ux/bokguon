# -*- coding: utf-8 -*-
"""스캔 640라운드 회귀 — check_tx_paths.py(BEGIN IMMEDIATE 트랜잭션 commit/
   rollback 누락 점검 CLI, round124·291·574·620·621 이 이미 여러 번 자기
   사각지대를 고친 바로 그 도구)의 main() 이 "이 commit/rollback 호출이
   잠금~반환 구간 **줄 번호 사이**에 있는가"만 보고, 그 호출이 실제로 이
   return 과 **같은 실행 경로 위**에 있는지는 안 보던 결함(직접조사,
   하위위임 없음).

   조사 각도 — round639 가 다음 후보로 남긴 "check_tx_paths.py 자신의 소스는
   round620 이후 한 번도 다시 안 봤다"를 따라가 round621 이 새로 만든
   `_commit_rollback_linenos()` 의 소비부(main() 의 head~r.lineno 창 검사)를
   다시 읽었다. round621 은 "그 창 안에 있는 게 진짜 AST 호출인가, 주석 속
   글자인가"는 고쳤지만, "그 창 안에 있는 진짜 호출이 **이 return 과 같은
   가지에서 실행되는가**"는 여전히 안 보고 있었다 — if/elif 로 갈라진 서로
   다른 가지에 각각 commit() 과 (아무 처리 없는) return 이 있어도, 앞가지의
   commit() 줄이 그냥 뒷가지 return 보다 앞줄이기만 하면 통과됐다.

   synthetic 함수로 직접 재현(실행 기반, 아래 [2]):
       if flag_a:
           conn.commit(); return "a"
       elif not flag_a:
           return "b"          # commit/rollback 전혀 없음
   "b" 가지를 타면 잠금이 열린 채 나가는데도, "a" 가지의 commit() 줄이
   같은 (head, r.lineno] 구간에 있다는 이유만으로 고치기 전 로직은 클린(0건)
   을 보고했다(실측 — 아래 되돌림-증명).

   실제 저장소(app.py·dispatch.py·manage.py·seed_boq.py, 109개 함수) 재확인
   — 고치기 전/후 모두 위반 0건(클린, 오탐 없음). round124·574·620·621 과
   같은 "점검 도구 자신의 사각지대" 유형 — 지금까지 이 틈이 실제 결함을
   감춘 적은 없었지만, 다음에 추가되는 if/elif 분기 하나가 조용히 이 방어를
   무력화할 수 있는 상태였다.

   고침 — check_tx_paths.py 에 `_parent_map()`(노드→부모)·`_branch_path()`
   (node 에서 fn 까지 조상 if 를 타고 올라가며 어느 가지였는지 기록)·
   `_may_precede()`(commit 호출과 return 이 공통 조상 if 에서 서로 다른
   가지로 갈라지면 False) 세 헬퍼를 신설. 기존 `_commit_rollback_linenos()`
   는 `_commit_rollback_calls()` 로 개명해 줄번호 대신 실제 Call 노드를
   돌려주게 바꿨다(어느 가지에 있는지 판정하려면 노드 자체가 필요해서).
   main() 의 판정부는 이제 "줄 구간 안" 과 "상호배타가 아님"을 함께 확인한다.

   범위 밖(다루지 않음, check_tx_paths.py 의 round640 주석에도 명시) —
   ①try/except 가지 사이의 같은 성격 사각지대, ②elif 가 아니라 독립된 두
   if 로 각각 조기 return 하는 "가드절" 형태. 이 두 모양이 실제 4개 대상
   파일에 있는지, 있다면 진짜 결함을 감추는지는 **확인되지 않았다** — 이번
   고침으로 새 위반도 새 오탐도 안 생겼다는 사실만 아래 [4]가 재확인한다.

   회귀테스트(이 파일) — [1] 소스: 새 헬퍼 네 개(_parent_map·_branch_path·
   _may_precede·개명된 _commit_rollback_calls)가 정확히 한 번씩 있음과
   main() 의 새 판정부 블록이 정확히 한 번 있음을 확인. [2] 되돌림-증명 —
   main() 판정부에서 `_may_precede(...)` 가지 검사만 제거한(그 외 round621
   까지의 AST 기반 판정은 그대로 둔) 옛 버전을 dict(vars(CTP)) 독립 사본
   네임스페이스에 exec(check_tx_paths.py 파일 자체·실제 CTP 모듈 어느
   쪽도 안 건드림), 그 되돌린 main 을 if/elif 분기 결함 합성 파일 하나짜리
   스크래치 디렉터리에 겨눠 실제로 클린(0건, 사각지대 재현)을 보고함을
   확인. [3] 지금(고쳐진) 실제 CTP.main() 을 같은 합성 파일에 겨누면
   위반 1건(함수명 포함)으로 정확히 잡히고, 같은 모양이지만 elif 가지에
   rollback() 이 있는 정상 합성 파일은 과잉탐지 없이 통과함을 확인(HERE·
   TARGET_FILES 는 스크래치 값으로 임시 교체 후 되돌림). [4] 실제
   check_tx_paths.py 를 서브프로세스로 그대로 실행해 저장소 전체가 109개
   함수·위반 0건으로 끝남을 재확인.

      python test_scan_round640_fixes.py
"""
import ast
import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def _checked_n(out):
    m = re.search(r"함수\s+(\d+)개", out)
    return int(m.group(1)) if m else None


print("=" * 66)
print("  스캔 640라운드 회귀 — check_tx_paths.py if/elif 가지 오판 사각지대")
print("=" * 66)

CTP_PATH = os.path.join(HERE, "check_tx_paths.py")
CTP_SRC = io.open(CTP_PATH, encoding="utf-8").read()

# ── [1] 소스 확인 ────────────────────────────────────────────────
print("\n[1] 소스 확인")
chk(CTP_SRC.count("def _parent_map(fn):") == 1,
    "★★★ _parent_map() 헬퍼가 정확히 한 번 신설됐다")
#  ⚠ [라운드665] round665가 _branch_path()에 conn_names 인자를 더했다(같은
#    함수 안에서 "try: <conn>.rollback() except: ...” 처럼 rollback 시도
#    자체만 감싸는 방어용 try인지 판정하려면 필요 — check_tx_paths.py의
#    round665 주석 참고). 이 자리가 검증하려던 본뜻("이 헬퍼가 정확히 한 번
#    존재")은 그대로이므로 시그니처만 지금 모습으로 맞춘다.
chk(CTP_SRC.count("def _branch_path(node, parents, fn, conn_names):") == 1,
    "★★★ _branch_path() 헬퍼가 정확히 한 번 신설됐다(round665이 인자 1개 추가)")
#  ⚠ [라운드663] round663이 _may_precede()에 conn_names·inner 두 인자를
#    더했다(같은 함수 안의 if/else 양쪽이 함께 commit/rollback을 보장하는지
#    보려면 필요 — check_tx_paths.py의 round663 주석 참고). 이 자리가
#    검증하려던 본뜻("이 헬퍼가 정확히 한 번 존재")은 그대로이므로 시그니처만
#    지금 모습으로 맞춘다.
chk(CTP_SRC.count("def _may_precede(commit_node, r, parents, fn, conn_names, inner):") == 1,
    "★★★ _may_precede() 헬퍼가 정확히 한 번 신설됐다(round663이 인자 2개 추가)")
chk(CTP_SRC.count("def _commit_rollback_calls(fn, conn_names, inner):") == 1,
    "_commit_rollback_calls() (구 _commit_rollback_linenos) 헬퍼가 정확히 한 번 있다")
chk(CTP_SRC.count("parents = _parent_map(fn)") == 1,
    "main() 이 fn 당 한 번 parents 맵을 만든다")

NEW_MAIN_BLOCK = (
    "                head = bl\n"
    "                #  ⚠⚠ [라운드621] 예전엔 여기서 원문 텍스트 윈도(lines[head:r.lineno]를\n"
    '                #    join한 문자열)에 "conn.commit()"/"conn.rollback()"/"finally" 라는\n'
    "                #    글자가 있는지만 봤다 — 주석에 그 글자가 있어도 통과됐다(위 두 헬퍼\n"
    "                #    함수 docstring 참고). 이제 진짜 AST 호출·진짜 try/finally 구조만 본다.\n"
    '                #  ⚠⚠ [라운드640] 그 AST 호출도 "줄 구간 안"이기만 하면 인정됐다 — if/\n'
    "                #    elif/else 로 갈라진 서로 다른 가지의 commit 이 이 return 을 지켜주는\n"
    "                #    것으로 오판될 수 있었다(위 _may_precede 주석 참고). 공통 조상 if 에서\n"
    "                #    갈라지지 않는(상호배타가 아닌) 호출만 인정한다.\n"
    "                if any(head < c.lineno <= r.lineno and _may_precede(c, r, parents, fn, conn_names, inner)\n"
    "                       for c in _commit_rollback_calls(fn, conn_names, inner)):\n"
    "                    continue\n"
)
#  ⚠ [라운드663] round663이 _may_precede() 호출에 conn_names·inner 인자를
#    더했다(위 앵커 문자열도 이미 맞춰 뒀다) — round640 자신이 증명하려는
#    것(가지 판정 자체가 있는가/없는가)은 그대로이므로 이 회귀는 계속 유효하다.
#  round640 의 가지 검사만 제거한(round621 까지의 AST-노드 판정은 유지한)
#  버전 — round640 이 실제로 무엇을 더했는지만 되돌림으로 격리해서 본다.
OLD_MAIN_BLOCK = (
    "                head = bl\n"
    "                #  ⚠⚠ [라운드621] 예전엔 여기서 원문 텍스트 윈도(lines[head:r.lineno]를\n"
    '                #    join한 문자열)에 "conn.commit()"/"conn.rollback()"/"finally" 라는\n'
    "                #    글자가 있는지만 봤다 — 주석에 그 글자가 있어도 통과됐다(위 두 헬퍼\n"
    "                #    함수 docstring 참고). 이제 진짜 AST 호출·진짜 try/finally 구조만 본다.\n"
    "                if any(head < c.lineno <= r.lineno\n"
    "                       for c in _commit_rollback_calls(fn, conn_names, inner)):\n"
    "                    continue\n"
)
chk(CTP_SRC.count(NEW_MAIN_BLOCK) == 1,
    "★★★ main() 의 새 판정부 블록(_may_precede 가지검사 포함)이 소스에 정확히 한 번만 있다"
    "(되돌림 대상 특정 가능)", CTP_SRC.count(NEW_MAIN_BLOCK))

# ── [2] 되돌림-증명 — main() 판정부에서 가지검사만 제거해 독립 사본에 exec ──
print("\n[2] 되돌림-증명 — _may_precede 가지검사만 제거한 옛 텍스트로 되돌려")
print("    dict(vars(CTP)) 독립 사본 네임스페이스에만 exec (파일·실제 모듈 불변)")

#  if 가지 하나(flag_a)는 commit 하고 return, elif 가지(not flag_a)는
#  아무 commit/rollback 없이 곧장 return — 실제로는 잠금이 열린 채 나간다.
BAD_SRC = (
    "# -*- coding: utf-8 -*-\n"
    "import db as DB\n\n"
    "def api_synthetic_elif_leak(pid, flag_a):\n"
    "    conn = DB.get_db()\n"
    '    conn.execute("BEGIN IMMEDIATE")\n'
    "    if flag_a:\n"
    '        conn.execute("UPDATE t SET a=1")\n'
    "        conn.commit()\n"
    '        return "a"\n'
    "    elif not flag_a:\n"
    '        return "b"\n'
    '    conn.execute("UPDATE t SET a=2")\n'
    "    conn.commit()\n"
    '    return "c"\n'
)
#  같은 모양이지만 elif 가지에도 진짜 rollback() 이 있다 — 정상.
GOOD_SRC = (
    "# -*- coding: utf-8 -*-\n"
    "import db as DB\n\n"
    "def api_synthetic_elif_ok(pid, flag_a):\n"
    "    conn = DB.get_db()\n"
    '    conn.execute("BEGIN IMMEDIATE")\n'
    "    if flag_a:\n"
    '        conn.execute("UPDATE t SET a=1")\n'
    "        conn.commit()\n"
    '        return "a"\n'
    "    elif not flag_a:\n"
    "        conn.rollback()\n"
    '        return "b"\n'
    '    conn.execute("UPDATE t SET a=2")\n'
    "    conn.commit()\n"
    '    return "c"\n'
)

sys.path.insert(0, HERE)
import check_tx_paths as CTP        # noqa: E402

_REAL_HERE = CTP.HERE
_REAL_TARGET = CTP.TARGET_FILES

try:
    ast.parse(BAD_SRC); ast.parse(GOOD_SRC)    # 문법 드라이런
    assert CTP_SRC.count(NEW_MAIN_BLOCK) == 1, "되돌리기 대상 텍스트가 유일하게 식별돼야 한다"
    reverted_src = CTP_SRC.replace(NEW_MAIN_BLOCK, OLD_MAIN_BLOCK)
    chk(reverted_src != CTP_SRC, "  (준비) 되돌림 치환이 실제로 달라졌다")

    _tree = ast.parse(reverted_src)
    _lines = reverted_src.splitlines(keepends=True)
    _main_src = None
    for _node in ast.walk(_tree):
        if isinstance(_node, ast.FunctionDef) and _node.name == "main":
            _main_src = "".join(_lines[_node.lineno - 1:_node.end_lineno])
            break
    assert _main_src, "되돌린 main() 함수 소스를 AST로 못 뽑음"
    chk("_may_precede" not in _main_src,
        "  (준비) 되돌린 main() 소스에 round640 가지검사 배선이 없다(되돌림 확인)")
    chk("_commit_rollback_calls(fn, conn_names, inner)" in _main_src,
        "  (준비) 되돌린 main() 소스는 round621 까지의 AST 노드 판정은 그대로 쓴다")

    #  독립 사본 네임스페이스 — check_tx_paths.py 파일도, 실제 import 된 CTP
    #  모듈도 이 과정에서 전혀 안 바뀐다(round618·620·621 과 같은 기법).
    _ns = dict(vars(CTP))
    exec(compile(_main_src, "<round640-reverted:main>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록

    with tempfile.TemporaryDirectory() as td:
        with io.open(os.path.join(td, "fake_bad.py"), "w", encoding="utf-8") as f:
            f.write(BAD_SRC)
        _ns["HERE"] = td
        _ns["TARGET_FILES"] = ("fake_bad.py",)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc_reverted = _ns["main"]()
        out_reverted = buf.getvalue()

    chk(rc_reverted == 0,
        "★★★★★ 옛 로직(되돌림)은 elif 가지 잠금누수 결함이 있는 합성 파일도 클린(0건)으로"
        " 오판한다 — 사각지대가 진짜였음을 증명", out_reverted[-300:])
    chk("api_synthetic_elif_leak" not in out_reverted,
        "★★★★★ 옛 로직(되돌림)의 보고에는 결함 함수 이름이 아예 등장하지 않는다", out_reverted[-300:])

    chk(io.open(CTP_PATH, encoding="utf-8").read() == CTP_SRC,
        "★★★★★ check_tx_paths.py 는 되돌림-증명 내내 디스크에서 전혀 건드려지지 않았다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] 되돌림-증명", f"{type(e).__name__}: {e}")

# ── [3] 지금(고쳐진) 실제 CTP.main() — 같은 합성 파일을 실제로 잡는지 ────
print("\n[3] 실행 — 지금(고쳐진) 실제 check_tx_paths.main() 으로 재확인")
try:
    with tempfile.TemporaryDirectory() as td:
        with io.open(os.path.join(td, "fake_bad.py"), "w", encoding="utf-8") as f:
            f.write(BAD_SRC)
        with io.open(os.path.join(td, "fake_good.py"), "w", encoding="utf-8") as f:
            f.write(GOOD_SRC)
        try:
            CTP.HERE = td
            CTP.TARGET_FILES = ("fake_bad.py",)
            buf_bad = io.StringIO()
            with contextlib.redirect_stdout(buf_bad):
                rc_bad = CTP.main()
            out_bad = buf_bad.getvalue()
            chk(rc_bad == 1,
                "★★★★★ 고쳐진 실제 코드는 같은 합성 결함을 위반(exit 1)으로 잡는다", out_bad[-300:])
            chk("api_synthetic_elif_leak" in out_bad,
                "★★★★★ 위반 함수 이름이 실제로 보고된다", out_bad[-300:])

            CTP.TARGET_FILES = ("fake_good.py",)
            buf_good = io.StringIO()
            with contextlib.redirect_stdout(buf_good):
                rc_good = CTP.main()
            chk(rc_good == 0,
                "회귀없음 — elif 가지에도 rollback() 이 있는 정상 합성 파일은 과잉탐지 없이 통과한다",
                buf_good.getvalue()[-300:])
        finally:
            CTP.HERE = _REAL_HERE
            CTP.TARGET_FILES = _REAL_TARGET
    chk(CTP.HERE == _REAL_HERE and CTP.TARGET_FILES == _REAL_TARGET,
        "  (정리) 실제 CTP 모듈의 HERE·TARGET_FILES 가 원래 값으로 복원됐다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] 실제 코드 재확인", f"{type(e).__name__}: {e}")
    CTP.HERE = _REAL_HERE
    CTP.TARGET_FILES = _REAL_TARGET

# ── [4] 실제 파일 그대로 서브프로세스 실행 — 저장소 전체 재확인 ─────────
print("\n[4] 실행 — 실제 check_tx_paths.py 를 서브프로세스로 그대로 실행")
try:
    #  ⚠ round518/519/574 가 이미 겪은 cp949 콘솔 함정 — 자식이 UTF-8 로 내보내는
    #    출력을 이 프로세스가 로케일 기본값으로 디코딩하면 죽는다. encoding 명시.
    r = subprocess.run([sys.executable, "-u", "check_tx_paths.py"], cwd=HERE,
                        capture_output=True, text=True, encoding="utf-8", timeout=60)
    out = r.stdout + r.stderr
    chk(r.returncode == 0, "★★★★★ 실제 저장소 전체 — 고친 뒤에도 클린(위반 0건)", out[-400:])
    n = _checked_n(out)
    chk(n == 109, "검사대상 함수 수가 이전(round620 시점 109개)과 동일하다(오탐으로 늘지 않음)",
        f"n={n}")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [4] check_tx_paths.py 실제 실행", f"{type(e).__name__}: {e}")

print("\n" + "=" * 66)
print(f"  {len(PASS)} / {len(PASS) + len(FAIL)} 통과")
if FAIL:
    print("  실패:")
    for n, d in FAIL:
        print(f"    · {n}  {d}")
print("=" * 66)
sys.exit(1 if FAIL else 0)
