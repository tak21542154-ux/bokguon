# -*- coding: utf-8 -*-
"""스캔 620라운드 회귀 — check_tx_paths.py(BEGIN IMMEDIATE 트랜잭션 commit/
   rollback 누락 점검 CLI, round124·291·574가 이미 여러 번 자기 사각지대를
   고친 바로 그 도구)가 지금까지 **return 문만** 보고 있었고, 반복문 안에서
   `continue`/`break` 로 그 회차를 빠져나가는 경로는 한 번도 검사 대상이
   아니었던 결함(직접조사, 하위위임 없음).

   조사 각도 — round618까지 app.py 요청 경로(§50·XSS·SSRF·권한·경합 등)가
   포화 상태라, 이 저장소 스스로 만든 점검 도구들(check_*.py) 자신의
   **소스 코드**를 다시 읽는 각도로 돌렸다(round518이 "실행해 보는" 각도를
   이미 썼으므로, 이번엔 "그 로직 자체가 자기 docstring 이 약속한 범위를
   실제로 구현했는가"를 되짚었다). check_tx_paths.py 의 main() 은
   `for r in ast.walk(fn): if not isinstance(r, ast.Return) ...` 로 ast.Return
   노드만 걸러 검사한다 — 그런데 이 파일이 실제로 검사하는 함수 중
   sweep_dispatches·sweep_webhook_retries·sweep_send_notifications·
   sweep_auctions 넷은 전부 "반복문 한 회차마다 BEGIN IMMEDIATE 를 열고 그
   회차 안에서 commit/rollback 한다"는 같은 패턴을 쓰고, 그 안의 조기 이탈은
   return 이 아니라 continue(4곳 전수 실측: dispatch.py:sweep_dispatches
   901·931행, app.py:sweep_webhook_retries 6962·6975·6979행 등)로 이뤄진다.
   이 도구 자신의 모듈 docstring 1행("어떤 경로로든 나갈 때는 반드시 commit
   이나 rollback 을 거쳐야 한다")이 이미 약속한 범위를 실제 구현이 못
   지키고 있었다 — round291이 "conn" 하나만 보다가 c2 등도 보게 넓힌 것과
   같은 성격의, 이름이 아니라 **노드 종류** 축의 사각지대.

   합성 함수(`for it in items: conn.execute("BEGIN IMMEDIATE"); ...;
   if not row: continue`, commit/rollback 없이)로 실제 재현 — 고치기 전
   로직은 이 합성 결함을 검사대상 함수로 세지도 못했다(continue 가
   ast.Return 이 아니므로 애초에 후보에도 안 들어감) — "클린(0건)"을
   보고했다. 실측 4개 함수 전수 재확인 결과 지금까지 이 사각지대가 실제
   운영 결함을 감춘 적은 없었다(전부 continue/break 앞에 이미
   commit()/rollback() 이 있다) — round574의 seed_boq.py 확장과 같은
   "지금 클린한 것은 코드가 우연히 안전해서일 뿐, 검사 자체가 이 경로를
   보고 있지 않았다"는 유형.

   고침 — check_tx_paths.py 에 `_own_loop_exits(loop)` 를 신설: 어떤
   반복문의 **몸통에 직접 속한** continue/break 만 뽑는다(중첩 반복문·중첩
   함수 안의 것은 그쪽 소관이라 안 내려간다 — return 과 달리 continue/
   break 는 자신을 감싼 가장 가까운 반복문에만 영향을 주므로, 그 반복문
   자체가 BEGIN IMMEDIATE 를 담고 있을 때만 검사 대상으로 삼아 무관한
   계산용 중첩 루프의 continue 까지 잡는 오탐을 피한다). main() 은 이제
   return 목록에 "BEGIN IMMEDIATE 를 담은 반복문의 own-exit" 를 더해 같은
   commit/rollback/finally 텍스트창 검사를 적용한다. safe_lock_failure_
   returns()·safe_finally_protected_returns() 도 (Return,Continue,Break)
   3종을 함께 보도록 넓혔다(그 두 헬퍼가 이미 문서화한 "잠금 자체가
   실패한 경우"·"finally 로 닫히는 경우"라는 면제 규칙은 return 이든
   continue/break 든 똑같이 적용돼야 하므로).

   실제 저장소 재확인 — 고친 뒤에도 4개 파일·109개 함수 전부 여전히
   클린(위반 0건, 오탐 없음) — sweep 4형제는 실측대로 전부 이미 정상이었다.

   회귀테스트(이 파일) — [1] 소스: _own_loop_exits 신설과 main() 의
   exit_nodes 배선이 정확히 한 번씩만 있음을 확인. [2] 되돌림-증명 —
   main() 함수 본문만 AST로 되돌려(continue/break 사각지대가 있던 옛
   텍스트) dict(vars(CTP)) 독립 사본 네임스페이스에 exec(check_tx_paths.py
   파일 자체·실제 CTP 모듈 어느 쪽도 안 건드림), 그 되돌린 main 을 합성
   결함 파일 하나짜리 스크래치 디렉터리에 겨눠 실제로 클린(0건, 사각지대
   재현)을 보고함을 확인. [3] 지금(고쳐진) 실제 CTP.main() 을 같은 합성
   파일에 겨누면 위반 1건(함수명 포함)으로 정확히 잡히고, 같은 성격이지만
   continue 앞에 rollback() 이 있는 정상 합성 파일은 과잉탐지 없이
   통과함을 확인(HERE·TARGET_FILES 는 스크래치 값으로 임시 교체 후 되돌림).
   [4] 실제 check_tx_paths.py 를 서브프로세스로 그대로 실행해 저장소
   전체가 109개 함수·위반 0건으로 끝남을 재확인.

      python test_scan_round620_fixes.py
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
print("  스캔 620라운드 회귀 — check_tx_paths.py continue/break 사각지대")
print("=" * 66)

CTP_PATH = os.path.join(HERE, "check_tx_paths.py")
CTP_SRC = io.open(CTP_PATH, encoding="utf-8").read()

# ── [1] 소스 확인 ────────────────────────────────────────────────
print("\n[1] 소스 확인")
chk(CTP_SRC.count("def _own_loop_exits(loop):") == 1,
    "★★★ _own_loop_exits() 헬퍼가 정확히 한 번 신설됐다")
chk("ast.Continue" in CTP_SRC and "ast.Break" in CTP_SRC,
    "소스에 ast.Continue·ast.Break 참조가 실제로 있다")

NEW_MAIN_BLOCK = (
    '            # return 외에, "이 함수 안에서 BEGIN IMMEDIATE 를 담은 반복문"의\n'
    "            # continue/break 도 같은 사각지대다(위 _own_loop_exits 주석 참고).\n"
    "            exit_nodes = [r for r in ast.walk(fn) if isinstance(r, ast.Return) and id(r) not in inner]\n"
    "            for loopnode in ast.walk(fn):\n"
    "                if (id(loopnode) in inner\n"
    "                        or not isinstance(loopnode, (ast.For, ast.AsyncFor, ast.While))\n"
    "                        or begins_immediate(loopnode, conn_names) is None):\n"
    "                    continue\n"
    "                exit_nodes.extend(_own_loop_exits(loopnode))\n"
    "\n"
    "            # 이 함수 안의 모든 return/continue/break 마다, 그 앞에 commit/rollback 이 있었는지 본다.\n"
    "            for r in exit_nodes:\n"
)
OLD_MAIN_BLOCK = (
    "            # 이 함수 안의 모든 return 문마다, 그 앞에 commit/rollback 이 있었는지 본다.\n"
    "            for r in ast.walk(fn):\n"
    "                if not isinstance(r, ast.Return) or id(r) in inner:\n"
    "                    continue\n"
)
chk(CTP_SRC.count(NEW_MAIN_BLOCK) == 1,
    "★★★ main() 의 exit_nodes 배선 블록이 소스에 정확히 한 번만 있다(되돌림 대상 특정 가능)",
    CTP_SRC.count(NEW_MAIN_BLOCK))

# ── [2] 되돌림-증명 — main() 본문만 되돌려 독립 사본에 exec ──────────────
print("\n[2] 되돌림-증명 — main() 을 옛(continue/break 사각지대) 텍스트로 되돌려")
print("    dict(vars(CTP)) 독립 사본 네임스페이스에만 exec (파일·실제 모듈 불변)")

BAD_SRC = (
    "# -*- coding: utf-8 -*-\n"
    "import db as DB\n\n"
    "def sweep_synthetic_leak(conn, items):\n"
    "    for it in items:\n"
    '        conn.execute("BEGIN IMMEDIATE")\n'
    '        row = conn.execute("SELECT 1").fetchone()\n'
    "        if not row:\n"
    "            continue\n"           # BUG: commit/rollback 없이 이 회차를 빠져나감
    '        conn.execute("UPDATE t SET a=1")\n'
    "        conn.commit()\n"
    "    return True\n"
)
GOOD_SRC = (
    "# -*- coding: utf-8 -*-\n"
    "import db as DB\n\n"
    "def sweep_synthetic_ok(conn, items):\n"
    "    for it in items:\n"
    '        conn.execute("BEGIN IMMEDIATE")\n'
    '        row = conn.execute("SELECT 1").fetchone()\n'
    "        if not row:\n"
    "            conn.rollback()\n"
    "            continue\n"
    '        conn.execute("UPDATE t SET a=1")\n'
    "        conn.commit()\n"
    "    return True\n"
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
    chk("exit_nodes" not in _main_src and "_own_loop_exits" not in _main_src,
        "  (준비) 되돌린 main() 소스에 continue/break 배선이 없다(되돌림 확인)")

    #  독립 사본 네임스페이스 — check_tx_paths.py 파일도, 실제 import 된 CTP
    #  모듈도 이 과정에서 전혀 안 바뀐다(round618·round432 와 같은 기법).
    _ns = dict(vars(CTP))
    exec(compile(_main_src, "<round620-reverted:main>", "exec"), _ns)

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
        "★★★★★ 옛 로직(되돌림)은 continue 누락 결함이 있는 합성 파일도 클린(0건)으로 오판한다"
        " — 이 사각지대가 진짜였음을 증명", out_reverted[-300:])
    chk("sweep_synthetic_leak" not in out_reverted,
        "★★★★★ 옛 로직(되돌림)의 보고에는 결함 함수 이름이 아예 등장하지 않는다"
        "(검사 후보에도 못 들어갔다는 뜻)", out_reverted[-300:])

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
            chk("sweep_synthetic_leak" in out_bad,
                "★★★★★ 위반 함수 이름이 실제로 보고된다", out_bad[-300:])

            CTP.TARGET_FILES = ("fake_good.py",)
            buf_good = io.StringIO()
            with contextlib.redirect_stdout(buf_good):
                rc_good = CTP.main()
            chk(rc_good == 0,
                "회귀없음 — continue 앞에 rollback() 이 있는 정상 합성 파일은 과잉탐지 없이 통과한다",
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
    chk(n == 109, "검사대상 함수 수가 이전(round574 시점 109개)과 동일하다(오탐으로 늘지 않음)",
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
