# -*- coding: utf-8 -*-
"""스캔 663라운드 회귀 — check_tx_paths.py(BEGIN IMMEDIATE 트랜잭션 commit/
   rollback 누락 점검 CLI, round124·291·574·620·621·640 이 이미 여러 번
   자기 사각지대를 고친 바로 그 도구)의 _may_precede() 가 라운드640 자신이
   "확인되지 않았다"고 명시적으로 남긴 두 사각지대 중 하나를 실제로 안고
   있던 결함(직접조사, 하위위임 없음).

   조사 각도 — round640의 코드 주석(check_tx_paths.py:218-227, 지금은
   앞줄이 밀렸지만 문구는 그대로)이 "①try/except 가지 사이의 사각지대,
   ②elif 가 아니라 두 개의 독립된 if 로 각각 조기 return 하는 가드절 형태
   — 이 두 모양이 실제 4개 대상 파일에 있는지, 있다면 진짜 결함을 감추는지는
   확인되지 않았다"고 명시적으로 남긴 것을 따라가, 이번 회차에 그 둘을
   직접 확인했다.

   ①(try/except 형제 가지)은 실제 109개 함수 전수 재확인 결과 지금은
   무해함을 확인했다(스캔 스크립트로 직접 검증 — 아래 [4]가 재확인하는
   109개·0건 클린 결과가 곧 그 증거이기도 하다). round640 자신의 주석이
   이미 이 항목을 "다음 라운드감"으로 남겨 둔 대로, 이 파일은 ②만 고치고
   ①은 다음 라운드를 위해 그대로 열어 둔다(check_tx_paths.py 의 관련 주석도
   그대로 유지).

   ②(독립 가드절)는 실제로 살아 있는 결함이었다 — `_may_precede()` 의
   `r_path.get(if_id, branch) == branch` 는 **r 이 그 if 안에 아예 없을 때도**
   (딕셔너리 기본값이 그대로 branch 와 같아 조건을 만족한 것으로 침) 통과
   시켰다. synthetic 함수로 직접 재현(실행 기반, 아래 [2]):
       if a:
           conn.commit(); return "x"
       if b:
           return "y"          # commit/rollback 전혀 없음, if a 에 else 없음
   "b" 가 True 인 실행에서는 if a 의 commit 이 전혀 안 도는데도, 고치기 전
   로직은 "may_precede == True"로 봐서 return "y" 를 안전하다고 오판해
   클린(0건)을 보고했다.

   그런데 이 결함을 "r 이 그 if 안에 없으면 무조건 False"로만 고치면 정반대의
   **새 오탐**이 생긴다는 것도 함께 확인했다 — 이 저장소에서 실제로 가장
   흔한 관용구(`if X: conn.commit() else: conn.rollback()` 뒤에 무조건
   return/close, 예: app.py sweep_review_reminders 6636행·api_defect_update
   15894행 둘 다 이 모양)는 if 몸통과 else 몸통이 **서로 다른** 가지에서
   각각 commit·rollback 을 부르고, 그 if/else **다음** 문장이 가지와 무관하게
   무조건 실행된다 — 그 return 은 어느 쪽 가지에도 안 속하지만 실제로는
   완전히 안전하다(실측: 위 두 함수에 "r 이 없으면 무조건 False"만 적용한
   시험판을 돌려보니 둘 다 거짓양성으로 새로 잡혔다).

   실제 저장소(app.py·dispatch.py·manage.py·seed_boq.py, 109개 함수) 재확인
   — 고치기 전/후 모두 위반 0건(클린, 오탐 없음) — 즉 이 사각지대는 지금까지
   실제 결함을 감춘 적은 없었지만, 다음에 추가되는 "독립된 두 개의 조기
   return 가드절" 하나가 조용히 이 방어를 무력화할 수 있는 상태였다.

   고침 — check_tx_paths.py 에 `_branch_has_commit()`(문장 목록 어딘가에
   commit/rollback 호출이 있는가)·`_if_guarantees_commit()`(if/else **양쪽
   가지 모두** commit/rollback 을 보장하는가, orelse 없으면 False) 두 헬퍼를
   신설. `_branch_path()` 는 이제 if 노드의 id 대신 **노드 자신**을 담아
   `_may_precede()` 가 그 노드를 직접 검사할 수 있게 했다. `_may_precede()`
   는 "r 이 그 if 의 같은 가지에 있는가"가 거짓이면, 그 if 가
   `_if_guarantees_commit()` 이 아닌 한(즉 순수 가드절처럼 else 가 없거나
   한쪽 가지만 commit/rollback 하면) False 로 판정한다.

   회귀테스트(이 파일) — [1] 소스: 새 헬퍼 두 개·`_may_precede()` 의 새
   6인자 시그니처·main() 호출부의 새 인자 배선이 정확히 한 번씩만 있음을
   확인. [2] 되돌림-증명 — `_branch_path()`·`_may_precede()` 를 라운드640
   시절 텍스트(id 기반, 가지 판정만)로, main() 호출부도 4인자 호출로 함께
   되돌린(그 외 round640까지의 판정은 그대로 둔) 옛 버전을 dict(vars(CTP))
   독립 사본 네임스페이스에 exec(check_tx_paths.py 파일 자체·실제 CTP
   모듈 어느 쪽도 안 건드림), 그 되돌린 main 을 독립 가드절 결함 합성
   파일 하나짜리 스크래치 디렉터리에 겨눠 실제로 클린(0건, 사각지대
   재현)을 보고함을 확인. [3] 지금(고쳐진) 실제 CTP.main() 을 같은 합성
   파일에 겨누면 위반 1건(함수명 포함)으로 정확히 잡히고, if/else 양쪽이
   각각 commit·rollback 을 부르는 정상 합성 파일(sweep_review_reminders·
   api_defect_update 와 같은 모양)은 과잉탐지 없이 통과함을 확인(HERE·
   TARGET_FILES 는 스크래치 값으로 임시 교체 후 되돌림). [4] 실제
   check_tx_paths.py 를 서브프로세스로 그대로 실행해 저장소 전체가 109개
   함수·위반 0건으로 끝남을 재확인(오탐 없음).

      python test_scan_round663_fixes.py
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
print("  스캔 663라운드 회귀 — check_tx_paths.py 독립 가드절 사각지대")
print("=" * 66)

CTP_PATH = os.path.join(HERE, "check_tx_paths.py")
CTP_SRC = io.open(CTP_PATH, encoding="utf-8").read()

# ── [1] 소스 확인 ────────────────────────────────────────────────
print("\n[1] 소스 확인")
chk(CTP_SRC.count("def _branch_has_commit(stmts, conn_names, inner):") == 1,
    "★★★ _branch_has_commit() 헬퍼가 정확히 한 번 신설됐다")
chk(CTP_SRC.count("def _if_guarantees_commit(if_node, conn_names, inner):") == 1,
    "★★★ _if_guarantees_commit() 헬퍼가 정확히 한 번 신설됐다")
chk(CTP_SRC.count("def _may_precede(commit_node, r, parents, fn, conn_names, inner):") == 1,
    "★★★ _may_precede() 가 conn_names·inner 를 받는 새 시그니처로 정확히 한 번 있다")
chk(CTP_SRC.count(
    "if any(head < c.lineno <= r.lineno and _may_precede(c, r, parents, fn, conn_names, inner)") == 1,
    "★★★ main() 호출부가 새 6인자로 정확히 한 번 배선됐다")
chk("path.append((parent, \"body\"))" in CTP_SRC and "path.append((parent, \"orelse\"))" in CTP_SRC,
    "_branch_path() 가 이제 id 대신 노드 자신을 담는다")

# ── [2] 되돌림-증명 — _branch_path·_may_precede·호출부를 라운드640 시절로 ──
print("\n[2] 되돌림-증명 — 독립 가드절 판정을 라운드640 시절(id 기반) 텍스트로 되돌려")
print("    dict(vars(CTP)) 독립 사본 네임스페이스에만 exec (파일·실제 모듈 불변)")

#  if a 는 commit 하고 return, **완전히 독립된** 다음 if b 는 아무 commit/
#  rollback 없이 곧장 return — elif 가 아니므로 라운드640 의 상호배타
#  판정만으로는 "같은 조상에서 갈라진 가지"조차 못 찾는다(둘은애초에
#  같은 if 의 가지가 아니다).
BAD_SRC = (
    "# -*- coding: utf-8 -*-\n"
    "import db as DB\n\n"
    "def api_synthetic_guard_leak(pid, a, b):\n"
    "    conn = DB.get_db()\n"
    '    conn.execute("BEGIN IMMEDIATE")\n'
    "    if a:\n"
    '        conn.execute("UPDATE t SET a=1")\n'
    "        conn.commit()\n"
    '        return "x"\n'
    "    if b:\n"
    '        return "y"\n'
    '    conn.execute("UPDATE t SET a=2")\n'
    "    conn.commit()\n"
    '    return "z"\n'
)
#  실제 저장소에서 가장 흔한 관용구 — if/else **양쪽**이 각각 commit·
#  rollback 을 부르고, 그 다음 문장(return)은 가지와 무관하게 무조건 실행된다
#  (app.py sweep_review_reminders·api_defect_update 와 같은 모양). 이 모양은
#  절대 거짓양성으로 잡히면 안 된다.
GOOD_SRC = (
    "# -*- coding: utf-8 -*-\n"
    "import db as DB\n\n"
    "def api_synthetic_ifelse_ok(pid, ok):\n"
    "    conn = DB.get_db()\n"
    '    conn.execute("BEGIN IMMEDIATE")\n'
    '    conn.execute("UPDATE t SET a=1")\n'
    "    if ok:\n"
    "        conn.commit()\n"
    "    else:\n"
    "        conn.rollback()\n"
    "    conn.close()\n"
    '    return "done"\n'
)

sys.path.insert(0, HERE)
import check_tx_paths as CTP        # noqa: E402

_REAL_HERE = CTP.HERE
_REAL_TARGET = CTP.TARGET_FILES

#  라운드640 시절(라운드663 이전) 텍스트 — id 기반 가지 판정만, if/else
#  전체보장 개념 자체가 없다.
OLD_BRANCH_PATH_SRC = (
    "def _branch_path(node, parents, fn):\n"
    '    """node 에서 fn 까지 조상을 타고 올라가며, 갈라지는 if 마다\n'
    "    (그 if 노드의 id, 어느 가지였는지 'body'/'orelse') 를 기록한다.\"\"\"\n"
    "    path = []\n"
    "    child = node\n"
    "    while True:\n"
    "        parent = parents.get(id(child))\n"
    "        if parent is None or parent is fn:\n"
    "            break\n"
    "        if isinstance(parent, ast.If):\n"
    "            if any(child is b for b in parent.body):\n"
    '                path.append((id(parent), "body"))\n'
    "            elif any(child is b for b in parent.orelse):\n"
    '                path.append((id(parent), "orelse"))\n'
    "        child = parent\n"
    "    return path\n"
    "\n\n"
    "def _may_precede(commit_node, r, parents, fn):\n"
    '    """commit_node 가 r 로 가는 실행 경로 위에 있을 수 있는가 — 공통 조상\n'
    '    if 에서 서로 다른 가지로 갈라지면(상호배타) False."""\n'
    "    c_path = dict(_branch_path(commit_node, parents, fn))\n"
    "    r_path = dict(_branch_path(r, parents, fn))\n"
    "    return all(r_path.get(if_id, branch) == branch for if_id, branch in c_path.items())\n"
)
OLD_MAIN_CALL = (
    "                if any(head < c.lineno <= r.lineno and _may_precede(c, r, parents, fn)\n")

try:
    ast.parse(BAD_SRC); ast.parse(GOOD_SRC)    # 문법 드라이런
    ast.parse(OLD_BRANCH_PATH_SRC)             # 되돌릴 헬퍼 텍스트 자체도 유효한 파이썬인지

    #  ── 되돌린 헬퍼 두 개를 exec 해 독립 사본에 심는다 ──
    _ns = dict(vars(CTP))
    exec(compile(OLD_BRANCH_PATH_SRC, "<round663-reverted:helpers>", "exec"), _ns)  # noqa: S102
    chk(callable(_ns.get("_may_precede")) and _ns["_may_precede"].__code__.co_argcount == 4,
        "  (준비) 되돌린 _may_precede 는 옛 4인자 시그니처다")

    #  ── main() 소스도 호출부만 4인자로 되돌려 같은 독립 사본에 심는다 ──
    assert CTP_SRC.count(
        "if any(head < c.lineno <= r.lineno and _may_precede(c, r, parents, fn, conn_names, inner)"
    ) == 1, "되돌리기 대상 호출부 텍스트가 유일하게 식별돼야 한다"
    reverted_main_src_full = CTP_SRC.replace(
        "                if any(head < c.lineno <= r.lineno and "
        "_may_precede(c, r, parents, fn, conn_names, inner)\n",
        OLD_MAIN_CALL)
    chk(reverted_main_src_full != CTP_SRC, "  (준비) main() 호출부 되돌림 치환이 실제로 달라졌다")

    _tree = ast.parse(reverted_main_src_full)
    _lines = reverted_main_src_full.splitlines(keepends=True)
    _main_src = None
    for _node in ast.walk(_tree):
        if isinstance(_node, ast.FunctionDef) and _node.name == "main":
            _main_src = "".join(_lines[_node.lineno - 1:_node.end_lineno])
            break
    assert _main_src, "되돌린 main() 함수 소스를 AST로 못 뽑음"
    chk("_may_precede(c, r, parents, fn)" in _main_src and "conn_names, inner)" not in _main_src.split(
        "_may_precede(c, r, parents, fn)")[1].split("\n")[0],
        "  (준비) 되돌린 main() 소스가 옛 4인자 호출을 쓴다(되돌림 확인)")
    exec(compile(_main_src, "<round663-reverted:main>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록

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
        "★★★★★ 옛 로직(되돌림)은 독립 가드절 잠금누수 결함이 있는 합성 파일도 클린(0건)으로"
        " 오판한다 — 사각지대가 진짜였음을 증명", out_reverted[-300:])
    chk("api_synthetic_guard_leak" not in out_reverted,
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
                "★★★★★ 고쳐진 실제 코드는 독립 가드절 합성 결함을 위반(exit 1)으로 잡는다",
                out_bad[-300:])
            chk("api_synthetic_guard_leak" in out_bad,
                "★★★★★ 위반 함수 이름이 실제로 보고된다", out_bad[-300:])

            CTP.TARGET_FILES = ("fake_good.py",)
            buf_good = io.StringIO()
            with contextlib.redirect_stdout(buf_good):
                rc_good = CTP.main()
            chk(rc_good == 0,
                "★★★★★ 회귀없음 — if/else 양쪽이 각각 commit·rollback 하는 정상 합성 파일은"
                " (독립 가드절이 아닌데도) 과잉탐지 없이 통과한다", buf_good.getvalue()[-300:])
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
