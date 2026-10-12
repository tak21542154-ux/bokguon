# -*- coding: utf-8 -*-
"""스캔 621라운드 회귀 — check_tx_paths.py(BEGIN IMMEDIATE 트랜잭션 commit/
   rollback 누락 점검 CLI, round124·291·574·620이 이미 여러 번 자기
   사각지대를 고친 바로 그 도구)의 main()이 "잠금~반환 구간에 commit/
   rollback이 있었는가"를 그 구간의 **원문 텍스트**에서 "conn.commit()"/
   "conn.rollback()"/"finally"라는 글자가 있는지만으로 판정하던 결함
   (직접조사, 하위위임 없음).

   조사 각도 — Part A(레거시 온디스크 되돌림-복원 마이그레이션)를 계속하다,
   이 세션 자신이 방금 쓴 되돌림-증명 코드의 문체("옛 코드는 conn.rollback()
   을 안 불렀다"류 설명 주석)가 이 저장소 전역에 매우 흔함을 재확인하는
   과정에서, check_tx_paths.py의 핵심 판정부(main() 291행대)가 AST가 아니라
   `window = "\\n".join(lines[head:r.lineno])`로 만든 **원문 텍스트 조각**에
   대해 `"conn.rollback()" in window` 같은 부분문자열 검사를 한다는 것을
   발견 — 텍스트 검사는 그 글자가 **주석 안**에 있어도 구분하지 못한다.
   synthetic 함수로 직접 재현(실행 기반) — BEGIN IMMEDIATE 뒤 이른 return
   바로 앞줄에 "# ...상위 호출자가 conn.rollback()을 대신 처리..." 라는
   설명 주석만 있고 실제 rollback() 호출은 전혀 없어도, 옛 로직은 그 return
   을 "안전"으로 오판해 클린(0건)을 보고했다. "finally" 글자 검사도 같은
   결함 — "옛 버전은 finally 블록에서 정리했다"류 설명 주석만 있어도 진짜
   try/finally 구조가 없는데 안전 처리됐다. 두 판정 다 같은 근본원인(원문
   텍스트 부분문자열 검사)의 한 몸이라 한 곳(main()의 판정부)에서 함께
   고친다.

   실제 저장소(app.py·dispatch.py·manage.py·seed_boq.py, 109개 함수) 재확인
   — 고치기 전/후 모두 위반 0건(클린, 오탐 없음). round124·574·620과 같은
   "점검 도구 자신의 사각지대" 유형 — 지금까지 이 틈이 실제 결함을 감춘
   적은 없었지만, 다음에 추가되는 설명 주석 한 줄이 조용히 이 방어를
   무력화할 수 있는 상태였다.

   고침 — check_tx_paths.py에 `_is_commit_or_rollback_call()`·
   `_commit_rollback_linenos()`·`_finally_protecting_ends()` 세 헬퍼를
   신설: 원문 텍스트가 아니라 **진짜 AST Call 노드**(<conn>.commit()/
   <conn>.rollback())와 **진짜 try/finally 구조**(finally 안에 실제
   commit/rollback 호출이 있는 경우만)만 본다. 중첩 헬퍼 함수 안의 호출은
   (그 함수가 지금 당장 불렸다는 보장이 없으므로) main()이 이미
   exit_nodes에 쓰는 것과 같은 inner 집합으로 제외해, 새 판정 자신이
   "중첩 함수 속 커밋도 바깥을 지켜준다"는 새 오판을 내지 않게 했다.

   회귀테스트(이 파일) — [1] 소스: 세 헬퍼 신설과 main() 판정부의 새 배선이
   정확히 한 번씩만 있음을 확인. [2] 되돌림-증명 — main() 판정부만 옛(원문
   텍스트 부분문자열 검사) 텍스트로 되돌려 dict(vars(CTP)) 독립 사본
   네임스페이스에 exec(check_tx_paths.py 파일 자체·실제 CTP 모듈 어느 쪽도
   안 건드림), 그 되돌린 main을 "설명 주석만 있고 진짜 commit/rollback은
   없는" 합성 결함 파일 하나짜리 스크래치 디렉터리에 겨눠 실제로
   클린(0건, 사각지대 재현)을 보고함을 확인. [3] 지금(고쳐진) 실제
   CTP.main()을 같은 합성 파일에 겨누면 위반 1건(함수명 포함)으로 정확히
   잡히고, 같은 성격이지만 실제 rollback() 호출이 있는 정상 합성 파일은
   과잉탐지 없이 통과함을 확인(HERE·TARGET_FILES는 스크래치 값으로 임시
   교체 후 되돌림). [4] 실제 check_tx_paths.py를 서브프로세스로 그대로
   실행해 저장소 전체가 109개 함수·위반 0건으로 끝남을 재확인.

      python test_scan_round621_fixes.py
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
print("  스캔 621라운드 회귀 — check_tx_paths.py 주석 텍스트 오판 사각지대")
print("=" * 66)

CTP_PATH = os.path.join(HERE, "check_tx_paths.py")
CTP_SRC = io.open(CTP_PATH, encoding="utf-8").read()

# ── [1] 소스 확인 ────────────────────────────────────────────────
print("\n[1] 소스 확인")
#  ⚠ [라운드640] round640이 이 헬퍼를 _commit_rollback_calls() 로 개명했다
#    (줄번호 집합 대신 실제 Call 노드를 돌려줘야 그 호출이 어느 if 가지에
#    있는지 구조로 판정할 수 있어서 — check_tx_paths.py 의 round640 주석
#    참고). 이 자리가 검증하려던 본뜻("텍스트가 아니라 진짜 AST 호출만 보는
#    헬퍼가 정확히 한 번 존재")은 그대로이므로 이름만 새 이름으로 맞춘다.
chk(CTP_SRC.count("def _commit_rollback_calls(fn, conn_names, inner):") == 1,
    "★★★ _commit_rollback_calls() 헬퍼(구 _commit_rollback_linenos, round640이 개명)가 정확히 한 번 있다")
chk(CTP_SRC.count("def _finally_protecting_ends(fn, conn_names, inner):") == 1,
    "★★★ _finally_protecting_ends() 헬퍼가 정확히 한 번 신설됐다")
chk(CTP_SRC.count("def _is_commit_or_rollback_call(n, conn_names):") == 1,
    "_is_commit_or_rollback_call() 헬퍼가 정확히 한 번 신설됐다")

#  ⚠ [라운드640] 아래 NEW_MAIN_BLOCK 은 round621 이 만든 모습 그대로가 아니라
#    round640 이 그 위에 _may_precede() 가지 판정을 더 얹은 **지금** 모습이다
#    (헬퍼 개명 포함). round621 자신이 증명하려는 것(텍스트 부분문자열 검사가
#    아니라 진짜 AST 호출·진짜 try/finally 구조를 본다는 사실)은 이 블록에
#    여전히 그대로 있으므로, 이 앵커를 지금 소스와 다시 맞춰 되돌림-증명이
#    계속 유효하게 만든다 — round640 자신의 회귀테스트는 별도로
#    test_scan_round640_fixes.py 에 있다.
#  ⚠ [라운드663] round663이 _may_precede() 호출에 conn_names·inner 인자를
#    더했다(if/else 양쪽이 함께 commit/rollback을 보장하는지 보려면 필요 —
#    check_tx_paths.py의 round663 주석 참고) — 아래 앵커도 그 시그니처로
#    맞춘다. round621 이 증명하려는 것(텍스트가 아니라 AST를 본다)은 그대로다.
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
    "                # try/finally 로 닫는 형태(그 finally 가 실제로 commit/rollback 을\n"
    "                # 부르는 진짜 구조)면 정상 — 구간 안에서 그 try/finally 전체가 이미\n"
    "                # 끝나 있어야(그래야 이 return 에 닿기 전 finally 실행이 보장된다).\n"
    "                if any(head < end <= r.lineno\n"
    "                       for end in _finally_protecting_ends(fn, conn_names, inner)):\n"
    "                    continue\n"
    '                bad.append((relname, fn.name, r.lineno, lines[r.lineno - 1].strip()[:70]))\n'
)
OLD_MAIN_BLOCK = (
    "                head = bl\n"
    '                window = "\\n".join(lines[head:r.lineno])\n'
    '                if any(f"{name}.rollback()" in window or f"{name}.commit()" in window\n'
    "                       for name in conn_names):\n"
    "                    continue\n"
    "                # finally 블록으로 닫는 형태(try/finally)면 정상\n"
    '                if "finally" in window:\n'
    "                    continue\n"
    '                bad.append((relname, fn.name, r.lineno, lines[r.lineno - 1].strip()[:70]))\n'
)
chk(CTP_SRC.count(NEW_MAIN_BLOCK) == 1,
    "★★★ main() 의 새 판정부 블록이 소스에 정확히 한 번만 있다(되돌림 대상 특정 가능)",
    CTP_SRC.count(NEW_MAIN_BLOCK))

# ── [2] 되돌림-증명 — main() 판정부만 되돌려 독립 사본에 exec ──────────────
print("\n[2] 되돌림-증명 — main() 을 옛(원문 텍스트 부분문자열 검사) 텍스트로 되돌려")
print("    dict(vars(CTP)) 독립 사본 네임스페이스에만 exec (파일·실제 모듈 불변)")

#  BEGIN IMMEDIATE 뒤 이른 return 바로 앞줄에 "설명 주석"만 있고 진짜
#  commit()/rollback() 호출은 전혀 없다 — 실제로는 잠금이 열린 채 나간다.
BAD_SRC = (
    "# -*- coding: utf-8 -*-\n"
    "import db as DB\n\n"
    "def api_synthetic_leak(pid):\n"
    "    conn = DB.get_db()\n"
    '    conn.execute("BEGIN IMMEDIATE")\n'
    '    row = conn.execute("SELECT 1").fetchone()\n'
    "    if not row:\n"
    "        # 실패해도 상위 호출자가 conn.rollback() 을 대신 처리해 준다는 낡은 가정\n"
    "        return None, 404\n"
    '    conn.execute("UPDATE t SET a=1")\n'
    "    conn.commit()\n"
    "    return None, 200\n"
)
#  같은 모양이지만 진짜 rollback() 호출이 있다 — 정상.
GOOD_SRC = (
    "# -*- coding: utf-8 -*-\n"
    "import db as DB\n\n"
    "def api_synthetic_ok(pid):\n"
    "    conn = DB.get_db()\n"
    '    conn.execute("BEGIN IMMEDIATE")\n'
    '    row = conn.execute("SELECT 1").fetchone()\n'
    "    if not row:\n"
    "        conn.rollback()\n"
    "        return None, 404\n"
    '    conn.execute("UPDATE t SET a=1")\n'
    "    conn.commit()\n"
    "    return None, 200\n"
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
    chk("_commit_rollback_linenos" not in _main_src and "_finally_protecting_ends" not in _main_src,
        "  (준비) 되돌린 main() 소스에 새 AST 판정 배선이 없다(되돌림 확인)")
    chk('"finally" in window' in _main_src,
        "  (준비) 되돌린 main() 소스가 옛 원문 텍스트 부분문자열 검사를 쓴다(되돌림 확인)")

    #  독립 사본 네임스페이스 — check_tx_paths.py 파일도, 실제 import 된 CTP
    #  모듈도 이 과정에서 전혀 안 바뀐다(round618·620·432 와 같은 기법).
    _ns = dict(vars(CTP))
    exec(compile(_main_src, "<round621-reverted:main>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록

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
        "★★★★★ 옛 로직(되돌림)은 잠금누수 결함이 있는 합성 파일도 클린(0건)으로 오판한다"
        " — 주석 텍스트에 속아 넘어감을 증명", out_reverted[-300:])
    chk("api_synthetic_leak" not in out_reverted,
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
            chk("api_synthetic_leak" in out_bad,
                "★★★★★ 위반 함수 이름이 실제로 보고된다", out_bad[-300:])

            CTP.TARGET_FILES = ("fake_good.py",)
            buf_good = io.StringIO()
            with contextlib.redirect_stdout(buf_good):
                rc_good = CTP.main()
            chk(rc_good == 0,
                "회귀없음 — 진짜 rollback() 호출이 있는 정상 합성 파일은 과잉탐지 없이 통과한다",
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
