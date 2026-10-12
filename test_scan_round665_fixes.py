# -*- coding: utf-8 -*-
"""스캔 665라운드 회귀(직접조사, 하위위임 없음) — check_tx_paths.py(BEGIN
   IMMEDIATE 트랜잭션 commit/rollback 누락 점검 CLI)의 _may_precede() 가
   round640 이 범위 밖으로 명시적으로 남기고 round663 이 "다음 라운드감"으로
   재확인한 두 사각지대 중 나머지 하나 — "①try/except 가지 사이의 사각지대"를
   실제로 안고 있던 결함.

   조사 배경 — round663 은 "서로 다른 if 로 각각 조기 return 하는 가드절"
   사각지대(②)는 고쳤지만, "try 본문의 commit 이 형제 except 가지의 return 을
   못 지키는데 안전 처리되는" 사각지대(①)는 "실제 109개 함수 전수 재확인
   결과 지금은 무해함을 확인했다"면서 다음 라운드로 명시적으로 미뤘다.
   check_tx_paths.py 의 `_branch_path()`는 If 조상만 가지로 기록하고 Try 조상은
   그냥 지나쳐 올라간다 — 그 결과 try 본문의 commit() 과 형제 except 안의
   return 이 서로 배타적인데도(예외가 나면 그 지점 이후 try 본문은 실행되지
   않는다) "가지 구분 없음" 취급되어 `_may_precede()`의 기본값(증명 못 하면
   안전 쪽)에 그대로 넘어갔다.

   실측(이 라운드) — synthetic 함수로 직접 재현:
       try:
           conn.execute(...); conn.commit(); return "ok"
       except sqlite3.Error:
           return "boom"        # commit/rollback 전혀 없음
   "boom" 가지로 가려면 애초에 try 본문에서 예외가 나야 하므로 그 commit() 이
   "boom" 가지에서 실행됐다는 보장이 전혀 없는데도, 고치기 전 로직은
   "may_precede == True"로 봐서 클린(0건)으로 오판했다(아래 [4]의 되돌림-증명이
   이 정확한 모양으로 재확인한다). 서로 다른 except handler 끼리도 같은
   문제였다(한쪽만 commit+return, 다른 쪽은 무방비 return — 아래 [2]의
   bad_handler_vs_handler).

   고침(check_tx_paths.py) — `_branch_path()`가 Try 조상도 기록하도록 확장
   (본문/orelse → "try", 각 handler → 서로 다른 ("except", id(handler)) — 즉
   handler 끼리도 서로 배타적인 별개 가지). `_try_guarantees_commit()`을
   `_if_guarantees_commit()`과 같은 역할로 신설(정상경로 + try 다음으로
   이어지는 모든 handler 가 commit 을 거치는가). `_may_precede()`는 r 이 그
   조상의 "가지 밖"(다음 코드)에 있을 때만 guarantee 우회를 쓰고, r 이 이미
   그 조상의 **다른** 가지 안에 있으면 곧장 위험으로 판정하도록 손봤다(이
   구분이 없으면 r **자신**이 속한 handler 가 "return 으로 끝난다"는 이유로
   스스로 커밋 요구에서 면제되어 정작 잡으려던 결함을 다시 놓친다 — 조사
   중 synthetic 재현으로 직접 확인).

   ⚠ 일반화 도중 실제 4개 대상 파일에 적용해 보니 오탐 5건이 새로 잡혔다 —
   전부 이미 안전한 두 관용구였다(둘 다 [2]의 good_* 케이스로 회귀 확인):
     · app.py 4곳(sweep_no_bid_alert:6335·sweep_warranty_expiry:6725·
       sweep_approval_overdue:6830·_sweep_award_approval:6933) —
       `except Exception: ...; try: conn.rollback() except sqlite3.Error:
       pass; return X`. try 본문이 rollback 시도 자체 한 줄뿐인 방어용 try를
       진짜 갈림길로 잘못 봤다 — `_is_bare_rollback_guard()`로 투명 처리.
     · dispatch.py:1020 sweep_dispatches() — 바깥 try 의 유일한 handler가
       `_release_lease(conn, "오류"); raise`로 항상 다시 던진다. 다시 던지는
       handler 는 절대 try 다음 코드로 안 이어지므로 그 handler 의 커밋 여부는
       무관한데 무조건 요구했다 — `_handler_falls_through()`로 그런 handler 를
       "모든 handler 가 커밋해야 한다" 요구에서 제외.

   실제 저장소(app.py·dispatch.py·manage.py·seed_boq.py, 109개 함수) 재확인 —
   고치기 전/후 모두 위반 0건(클린, 오탐 없음) — 이 사각지대는 지금까지 실제
   결함을 감춘 적은 없었지만, 다음에 추가되는 "try 본문 commit + 형제 except
   무방비 return" 하나가 조용히 이 방어를 무력화할 수 있는 상태였다.

   회귀테스트(이 파일) — [1] 소스: 새 헬퍼(_is_bare_rollback_guard·
   _handler_falls_through)·확장된 _branch_path/_try_guarantees_commit·손본
   _may_precede 가 정확히 한 번씩 있음을 확인. [2] 실행 — 5개 synthetic
   케이스(진짜 결함 2개는 반드시 잡히고, 이미 안전한 관용구 3개는 절대
   오탐 없이 통과)를 실제 CTP.main() 으로 확인. [3] 실행 — 실제
   check_tx_paths.py 를 서브프로세스로 그대로 실행해 저장소 전체가 109개
   함수·위반 0건으로 끝남을 재확인(오탐 없음). [4] 되돌리기 — `_branch_path`·
   `_may_precede`만 round663 시절(Try 미인식) 텍스트로 독립 사본 네임스페이스에
   되돌리면(check_tx_paths.py 파일도 실제 CTP 모듈도 전혀 안 건드림)
   bad_try_except_sibling 합성 파일이 클린(0건)으로 오판됨을 확인해 인과관계를
   증명한다.

      python test_scan_round665_fixes.py
"""
import ast
import contextlib
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 665라운드 회귀 — check_tx_paths.py try/except 가지 사이 사각지대")
print("=" * 72)

CTP_PATH = os.path.join(HERE, "check_tx_paths.py")
CTP_SRC = io.open(CTP_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
chk(ast.parse(CTP_SRC) is not None, "STEP check_tx_paths.py 전체 ast.parse 성공")
chk(CTP_SRC.count("def _is_bare_rollback_guard(try_node, conn_names):") == 1,
    "★★★ _is_bare_rollback_guard() 헬퍼가 정확히 한 번 신설됐다")
chk(CTP_SRC.count("def _branch_path(node, parents, fn, conn_names):") == 1,
    "★★★ _branch_path() 가 conn_names 를 받는 새 시그니처로 정확히 한 번 있다")
chk('elif (isinstance(parent, ast.Try) and parent.handlers\n'
    '                and not _is_bare_rollback_guard(parent, conn_names)):' in CTP_SRC,
    "★★★★★ _branch_path() 가 Try 조상도 기록한다(방어용 rollback 래퍼는 투명 처리)")
chk(CTP_SRC.count('path.append((parent, ("except", id(child))))') == 1,
    "★★★ handler 마다 서로 다른 배타적 가지로 기록한다")
chk(CTP_SRC.count("_NO_FALLTHROUGH = (ast.Raise, ast.Return, ast.Continue, ast.Break)") == 1,
    "_NO_FALLTHROUGH 튜플이 정확히 한 번 정의됐다")
chk(CTP_SRC.count("def _handler_falls_through(handler):") == 1,
    "★★★ _handler_falls_through() 헬퍼가 정확히 한 번 신설됐다")
chk(CTP_SRC.count("def _try_guarantees_commit(try_node, conn_names, inner):") == 1,
    "★★★ _try_guarantees_commit() 헬퍼가 정확히 한 번 신설됐다")
chk("falling = [h for h in try_node.handlers if _handler_falls_through(h)]" in CTP_SRC,
    "_try_guarantees_commit() 이 다음으로 안 이어지는 handler 를 커밋 요구에서 뺀다")
chk(CTP_SRC.count("if r_branch is not None:\n            return False") == 1,
    "★★★★★ _may_precede() 가 'r 이 다른 가지 안'과 'r 이 가지 밖'을 구분한다"
    "(안 그러면 r 자신의 handler 가 스스로 면제돼 버린다)")
chk(CTP_SRC.count(
    "if isinstance(anc, ast.Try) and _try_guarantees_commit(anc, conn_names, inner):") == 1,
    "★★★ _may_precede() 가 Try 조상에도 guarantee 우회를 쓴다")

sys.path.insert(0, HERE)
import check_tx_paths as CTP        # noqa: E402

_REAL_HERE = CTP.HERE
_REAL_TARGET = CTP.TARGET_FILES

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — synthetic 5종(진짜 결함 2개 + 이미 안전한 관용구 3개)")
# ──────────────────────────────────────────────────────────────
#  진짜 결함 ① — try 본문 commit, 형제 except 는 무방비 return(이 라운드의
#  핵심 사각지대 그 자체).
BAD_TRY_EXCEPT_SIBLING = '''# -*- coding: utf-8 -*-
import db as DB
def api_bad_try_except_sibling(pid, mode):
    conn = DB.get_db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("UPDATE t SET a=1")
        conn.commit()
        return "ok"
    except sqlite3.Error:
        return "boom"
'''
#  진짜 결함 ② — handler 끼리도 서로 배타적: ValueError 는 commit+return,
#  TypeError 는 무방비 return.
BAD_HANDLER_VS_HANDLER = '''# -*- coding: utf-8 -*-
import db as DB
def api_bad_handler_vs_handler(pid, mode):
    conn = DB.get_db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("UPDATE t SET a=1")
    except ValueError:
        conn.commit()
        return "v"
    except TypeError:
        return "t"
    conn.commit()
    return "ok"
'''
#  안전 관용구 ① — round665 실측 4곳(app.py)과 같은 모양: try 본문은 그대로
#  commit 하고 return, except 는 "정리 시도 자체"(rollback)만 방어적으로
#  감싸고 그 다음 같은 가지에서 return 한다.
GOOD_BARE_ROLLBACK_GUARD = '''# -*- coding: utf-8 -*-
import db as DB
def api_good_bare_rollback_guard(pid, mode):
    conn = DB.get_db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("UPDATE t SET a=1")
        conn.commit()
        return "ok"
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        return "boom"
'''
#  안전 관용구 ② — round665 실측 dispatch.py:1020 과 같은 모양: 바깥 try 의
#  유일한 handler 가 항상 다시 던져(raise) 그 다음 코드로는 결코 안 이어진다.
GOOD_RERAISE_OUTER = '''# -*- coding: utf-8 -*-
import db as DB
def api_good_reraise_outer(pid, items):
    conn = DB.get_db()
    try:
        for it in items:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("UPDATE t SET a=1")
                conn.commit()
            except Exception:
                conn.rollback()
                continue
    except Exception:
        raise
    return "done"
'''
#  안전 관용구 ③ — 서로 다른 handler 라도 **각자** commit/rollback 을 부르면
#  (한쪽만 방치되는 게 아니라) 정상 — 오탐이면 안 된다.
GOOD_BOTH_HANDLERS_COMMIT = '''# -*- coding: utf-8 -*-
import db as DB
def api_good_both_handlers_commit(pid, mode):
    conn = DB.get_db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("UPDATE t SET a=1")
    except ValueError:
        conn.commit()
        return "v"
    except TypeError:
        conn.rollback()
        return "t"
    conn.commit()
    return "ok"
'''

CASES = [
    ("bad_try_except_sibling", BAD_TRY_EXCEPT_SIBLING, True, "api_bad_try_except_sibling"),
    ("bad_handler_vs_handler", BAD_HANDLER_VS_HANDLER, True, "api_bad_handler_vs_handler"),
    ("good_bare_rollback_guard", GOOD_BARE_ROLLBACK_GUARD, False, None),
    ("good_reraise_outer", GOOD_RERAISE_OUTER, False, None),
    ("good_both_handlers_commit", GOOD_BOTH_HANDLERS_COMMIT, False, None),
]

try:
    for name, src, expect_flagged, fn_name in CASES:
        ast.parse(src)      # 문법 드라이런
        with tempfile.TemporaryDirectory() as td:
            io.open(os.path.join(td, "f.py"), "w", encoding="utf-8").write(src)
            CTP.HERE = td
            CTP.TARGET_FILES = ("f.py",)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = CTP.main()
            out = buf.getvalue()
        got_flagged = (rc == 1)
        chk(got_flagged == expect_flagged,
            f"★★★★★ {name}: {'위반으로 잡혀야' if expect_flagged else '클린으로 통과해야'} 한다"
            f"(rc={rc})", out[-300:])
        if expect_flagged and got_flagged:
            chk(fn_name in out, f"  {name}: 위반 함수 이름({fn_name})이 실제로 보고된다", out[-300:])
finally:
    CTP.HERE = _REAL_HERE
    CTP.TARGET_FILES = _REAL_TARGET

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 실제 check_tx_paths.py 를 서브프로세스로 그대로 실행")
# ──────────────────────────────────────────────────────────────
try:
    r = subprocess.run([sys.executable, "-u", "check_tx_paths.py"], cwd=HERE,
                        capture_output=True, text=True, encoding="utf-8", timeout=60)
    out = r.stdout + r.stderr
    chk(r.returncode == 0, "★★★★★ 실제 저장소 전체 — 고친 뒤에도 클린(위반 0건, 오탐 없음)",
        out[-400:])
    chk("함수 109개" in out,
        "검사대상 함수 수가 이전(round663 시점 109개)과 동일하다(오탐으로 늘지 않음)", out[:200])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] check_tx_paths.py 실제 실행", f"{type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌리기 — _branch_path·_may_precede 만 round663 시절(Try 미인식) "
      "텍스트로 되돌리면(인과관계 직접증명)")
# ──────────────────────────────────────────────────────────────
#  ⚠ check_tx_paths.py 파일도, 실제 import 된 CTP 모듈도 이 과정에서 전혀 안
#    바뀐다(round640·663 과 같은 기법) — 독립 사본 네임스페이스에만 심는다.
#    main() 자신의 텍스트는 round663 이후 이번 라운드까지 한 글자도 안
#    바뀌었으므로(호출부는 이미 6인자 _may_precede(c, r, parents, fn,
#    conn_names, inner) 그대로) 그 현재 소스를 그대로 뽑아 같은 독립 사본에
#    심기만 하면 된다 — main() 자체를 되돌릴 필요가 없다.
OLD_BRANCH_PATH_SRC = (
    "def _branch_path(node, parents, fn):\n"
    '    """node 에서 fn 까지 조상을 타고 올라가며, 갈라지는 if 마다\n'
    "    (그 if 노드 자신, 어느 가지였는지 'body'/'orelse') 를 기록한다.\"\"\"\n"
    "    path = []\n"
    "    child = node\n"
    "    while True:\n"
    "        parent = parents.get(id(child))\n"
    "        if parent is None or parent is fn:\n"
    "            break\n"
    "        if isinstance(parent, ast.If):\n"
    "            if any(child is b for b in parent.body):\n"
    '                path.append((parent, "body"))\n'
    "            elif any(child is b for b in parent.orelse):\n"
    '                path.append((parent, "orelse"))\n'
    "        child = parent\n"
    "    return path\n"
    "\n\n"
    "def _may_precede(commit_node, r, parents, fn, conn_names, inner):\n"
    '    """commit_node 가 r 에 이르는 모든 실행 경로에서 실제로 실행됐다고\n'
    '    볼 수 있는가(휴리스틱)."""\n'
    "    c_path = _branch_path(commit_node, parents, fn)\n"
    "    r_path = dict((id(node), branch) for node, branch in _branch_path(r, parents, fn))\n"
    "    for if_node, branch in c_path:\n"
    "        if r_path.get(id(if_node)) == branch:\n"
    "            continue\n"
    "        if _if_guarantees_commit(if_node, conn_names, inner):\n"
    "            continue\n"
    "        return False\n"
    "    return True\n"
)

try:
    ast.parse(OLD_BRANCH_PATH_SRC)     # 되돌릴 텍스트 자체도 유효한 파이썬인지 드라이런

    _ns = dict(vars(CTP))               # 실제 모듈 사본 — 이 dict 만 바뀐다
    exec(compile(OLD_BRANCH_PATH_SRC, "<round665-reverted:helpers>", "exec"), _ns)  # noqa: S102
    chk(_ns["_branch_path"].__code__.co_argcount == 3,
        "  (준비) 되돌린 _branch_path 는 옛 3인자(conn_names 없음) 시그니처다")
    chk(_ns["_may_precede"].__code__.co_argcount == 6,
        "  (준비) 되돌린 _may_precede 는 round663 시절 6인자 시그니처 그대로다")

    #  main() 은 이번 라운드에서 한 글자도 안 바뀌었다 — 그래도 "새 _branch_path/
    #  _may_precede 를 globals 로 참조하게" 만들려면 같은 _ns 에 다시 심어야
    #  한다(함수 객체를 그냥 복사만 하면 __globals__ 는 여전히 진짜 모듈을
    #  가리켜 되돌림이 적용되지 않는다 — round640·663 이 main() 까지 다시
    #  exec 하는 이유와 같다).
    _tree = ast.parse(CTP_SRC)
    _lines = CTP_SRC.splitlines(keepends=True)
    _main_src = None
    for _node in ast.walk(_tree):
        if isinstance(_node, ast.FunctionDef) and _node.name == "main":
            _main_src = "".join(_lines[_node.lineno - 1:_node.end_lineno])
            break
    assert _main_src, "main() 함수 소스를 AST로 못 뽑음"
    exec(compile(_main_src, "<round665-reverted:main>", "exec"), _ns)  # noqa: S102

    with tempfile.TemporaryDirectory() as td:
        io.open(os.path.join(td, "fake_bad.py"), "w", encoding="utf-8").write(
            BAD_TRY_EXCEPT_SIBLING)
        _ns["HERE"] = td
        _ns["TARGET_FILES"] = ("fake_bad.py",)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc_reverted = _ns["main"]()
        out_reverted = buf.getvalue()

    chk(rc_reverted == 0,
        "★★★★★ 옛 로직(되돌림)은 try/except 가지 사이 사각지대가 있는 합성 파일도 "
        "클린(0건)으로 오판한다 — 사각지대가 진짜였음을 증명", out_reverted[-300:])
    chk("api_bad_try_except_sibling" not in out_reverted,
        "★★★★★ 옛 로직(되돌림)의 보고에는 결함 함수 이름이 아예 등장하지 않는다",
        out_reverted[-300:])
    chk(io.open(CTP_PATH, encoding="utf-8").read() == CTP_SRC,
        "★★★★★ check_tx_paths.py 는 되돌림-증명 내내 디스크에서 전혀 건드려지지 않았다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [4] 되돌림-증명", f"{type(e).__name__}: {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
