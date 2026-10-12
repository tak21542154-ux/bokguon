# -*- coding: utf-8 -*-
"""스캔 574라운드 회귀 — check_tx_paths.py(BEGIN IMMEDIATE 트랜잭션 commit/rollback
   누락 점검 CLI)의 TARGET_FILES 가 여전히 "app.py 가 import 하는가" 기준으로 뽑힌
   3개(app.py·dispatch.py·manage.py)뿐이라, 그 기준 밖의 독립 CLI인 seed_boq.py가
   BEGIN IMMEDIATE 로 쓰기 잠금을 잡는데도(load(), 200행) 이 점검을 완전히 벗어나
   있던 결함(직접조사, 하위위임 없음).

   조사 각도 — round124("app.py 만 하드코딩해서 봤다" → dispatch.py·manage.py 추가)와
   정확히 같은 각도를, round124 이후에도 다시 어긋난 적이 없는지 재확인하려고
   저장소 전체를 "BEGIN IMMEDIATE" 리터럴로 대소문자 무시 grep 했다(test_*.py·
   run_all_tests.py 는 제외 — 이 도구가 막는 증상 "잠금이 열린 채 커넥션이
   사라져 다음 쓰기가 busy_timeout 을 다 기다린 뒤 실패한다"는 서버 프로세스가
   오래 사는 것을 전제로 하는데, 테스트는 단명 프로세스라 원래부터 무관하다).
   실제로 이 문장을 쓰는 프로덕션 파일은 app.py·dispatch.py·manage.py·
   seed_boq.py 정확히 4개였다(db.py 는 주석 2곳뿐이라 round124 가 이미 정확히
   판단해 제외했다 — 재확인해도 여전히 맞다).

   실제 영향 — seed_boq.py 는 manage.py 와 같은 성격의 CLI 다: app.py 는 이
   파일을 import 하지 않고(순수 운영자 수동 실행), DB.get_db() 로 실제 운영
   DB(BOKGUON_DB_PATH 를 안 주면 bokguon.db)에 직접 붙어 표준단가표를 적재한다
   (round180/268/297/312 주석이 이미 "activity_log 실측상 가장 자주 쓰이는
   실제 적재 경로"라고 기록해 둔 그 도구). load() 는 지금은 유일한 return 이
   try/finally(conn.close()) 블록 **밖**의 함수 끝 한 곳뿐이라 이번 확장으로도
   위반 0건(클린)이지만 — round124·round571 이 이미 겪은 것과 같은 "점검 도구
   자신의 사각지대" 유형이다: 지금 클린한 것은 코드가 우연히 안전해서일 뿐,
   검사 자체가 이 함수를 보고 있지 않았다. 앞으로 이 함수에 새 return 이
   생기는 순간부터는 이 검사가 그것을 잡을 방법이 없었다.

   고침 — check_tx_paths.py:TARGET_FILES 단일 지점(이 상수의 유일한 정의처,
   다른 caller 없음)에 "seed_boq.py" 를 추가했다.

   이 회귀테스트는 [1] 소스 확인, [2] 되돌리기 — TARGET_FILES 를 옛(3파일) 값으로
   monkeypatch 해(on-disk 파일은 그대로) seed_boq.py:load() 가 실제로 검사대상
   에서 빠짐을 실측, [3] 지금(4파일) 값으로는 다시 잡히고 검사대상 함수 수가
   정확히 1개 늘며 위반은 여전히 0건임을 확인, [4] 이 검사가 진짜 이빨이 있는지
   — BEGIN IMMEDIATE 뒤 커밋/롤백/finally 없이 바로 return 하는 합성 파일을
   스크래치 디렉터리에 심고 CTP.HERE 를 잠깐 그쪽으로 돌려 실제로 위반 1건을
   잡아내는지(및 형제 정상 파일은 과잉탐지 없이 통과하는지) 확인, [5] 실제
   check_tx_paths.py 를 서브프로세스로 그대로 실행해 저장소 전체가 109개 함수·
   위반 0건으로 끝남을 재확인한다.

      python test_scan_round574_fixes.py
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
print("  스캔 574라운드 회귀 — check_tx_paths.py TARGET_FILES 에 seed_boq.py 추가")
print("=" * 66)

# ── [1] 소스 확인 ────────────────────────────────────────────────
print("\n[1] 소스 확인")
try:
    with open(os.path.join(HERE, "check_tx_paths.py"), encoding="utf-8") as f:
        CTP_SRC = f.read()
    chk('TARGET_FILES = ("app.py", "dispatch.py", "manage.py", "seed_boq.py")' in CTP_SRC,
        "★★★ check_tx_paths.py 가 seed_boq.py 도 검사 대상에 넣는다")

    with open(os.path.join(HERE, "seed_boq.py"), encoding="utf-8") as f:
        SEED_SRC = f.read()
    chk('conn.execute("BEGIN IMMEDIATE")' in SEED_SRC,
        "전제 확인 — seed_boq.py 자신이 실제로 BEGIN IMMEDIATE 를 쓴다")
    ast.parse(SEED_SRC)   # 문법 확인(드라이런)
except Exception as e:
    chk(False, "★★★ 라운드574 [1] 소스 확인", f"{type(e).__name__} {e}")

# ── [2]~[3] 실행 — 되돌리기와 재확인을 같은 프로세스의 실제 함수로 ──────
print("\n[2] 되돌리기 — TARGET_FILES 를 옛(3파일) 값으로 되돌리면 seed_boq.py 가 빠진다")
out_old = out_new = ""
n_old = n_new = None
try:
    sys.path.insert(0, HERE)
    import check_tx_paths as CTP
    _REAL_TARGET = CTP.TARGET_FILES
    chk("seed_boq.py" in _REAL_TARGET, "전제 확인 — 지금 실제 TARGET_FILES 에 seed_boq.py 가 있다")

    CTP.TARGET_FILES = ("app.py", "dispatch.py", "manage.py")
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc_old = CTP.main()
        out_old = buf.getvalue()
    finally:
        CTP.TARGET_FILES = _REAL_TARGET     # 다음 단계 전에 반드시 원복
    chk(rc_old == 0, "옛 3파일 범위에서도 이 저장소는 클린(회귀 없음)", out_old[-200:])
    chk("seed_boq.py" not in out_old,
        "★★★ 옛 3파일 범위의 배너에는 seed_boq.py 가 없다(=검사 안 됐다)")

    print("\n[3] 지금(4파일) 값 — seed_boq.py 가 검사 대상에 들어오고 여전히 클린이다")
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc_new = CTP.main()
    out_new = buf2.getvalue()
    chk(rc_new == 0, "확장 후에도 클린(위반 0건)", out_new[-200:])
    chk("seed_boq.py" in out_new, "★★★ 확장 후 배너에 seed_boq.py 가 들어간다")

    n_old, n_new = _checked_n(out_old), _checked_n(out_new)
    chk(n_old is not None and n_new is not None and n_new == n_old + 1,
        "★★★ 검사대상 함수 수가 정확히 1개(seed_boq.load) 늘었다",
        f"old={n_old} new={n_new}")
except Exception as e:
    chk(False, "★★★ 라운드574 [2]/[3] 되돌리기·재확인", f"{type(e).__name__} {e}")

# ── [4] 이빨이 있는가 — 합성 위반 파일을 실제로 잡아내는지 ──────────────
print("\n[4] 실행 — 합성 파일로 이 검사의 탐지력(과소·과잉 둘 다) 확인")
BAD_SRC = (
    "# -*- coding: utf-8 -*-\n"
    "import db as DB\n\n"
    "def broken_loader(x):\n"
    "    conn = DB.get_db()\n"
    '    conn.execute("BEGIN IMMEDIATE")\n'
    "    if x:\n"
    "        return 1\n"                       # commit/rollback/finally 없이 그냥 나감 — 위반
    '    conn.execute("UPDATE t SET a=1")\n'
    "    conn.commit()\n"
    "    conn.close()\n"
    "    return 0\n"
)
GOOD_SRC = (
    "# -*- coding: utf-8 -*-\n"
    "import db as DB\n\n"
    "def safe_loader(x):\n"
    "    conn = DB.get_db()\n"
    "    try:\n"
    '        conn.execute("BEGIN IMMEDIATE")\n'
    "        if x:\n"
    "            conn.rollback()\n"
    "            return 1\n"
    '        conn.execute("UPDATE t SET a=1")\n'
    "        conn.commit()\n"
    "        return 0\n"
    "    finally:\n"
    "        conn.close()\n"
)
try:
    ast.parse(BAD_SRC); ast.parse(GOOD_SRC)     # 둘 다 문법이 맞는지 먼저 확인
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, "fake_bad.py"), "w", encoding="utf-8") as f:
            f.write(BAD_SRC)
        with open(os.path.join(td, "fake_good.py"), "w", encoding="utf-8") as f:
            f.write(GOOD_SRC)
        _real_here = CTP.HERE
        try:
            CTP.HERE = td
            CTP.TARGET_FILES = ("fake_bad.py",)
            buf3 = io.StringIO()
            with contextlib.redirect_stdout(buf3):
                rc_bad = CTP.main()
            out_bad = buf3.getvalue()
            chk(rc_bad == 1, "합성 위반 파일은 실패(exit 1)로 잡힌다", out_bad[-200:])
            chk("broken_loader" in out_bad, "★★★ 위반 함수 이름이 실제로 보고된다")

            CTP.TARGET_FILES = ("fake_good.py",)
            buf4 = io.StringIO()
            with contextlib.redirect_stdout(buf4):
                rc_good = CTP.main()
            chk(rc_good == 0, "합성 정상 파일(try/finally)은 클린 통과한다(과잉탐지 아님)")
        finally:
            CTP.HERE = _real_here
            CTP.TARGET_FILES = _REAL_TARGET
except Exception as e:
    chk(False, "★★★ 라운드574 [4] 합성 파일 탐지력 확인", f"{type(e).__name__} {e}")

# ── [5] 실제 파일 그대로 서브프로세스 실행 — 저장소 전체 재확인 ─────────
print("\n[5] 실행 — 실제 check_tx_paths.py 를 서브프로세스로 그대로 실행")
try:
    #  ⚠ text=True 만 쓰면 자식 stdout 디코딩이 로케일 기본값(이 저장소가 도는
    #    한국어 윈도에선 cp949)을 따라, check_tx_paths.py 자신이 UTF-8 로
    #    reconfigure 해 내보내는 '—' 같은 문자에서 UnicodeDecodeError 로 죽는다
    #    (round518/519 가 이미 겪은 것과 같은 cp949 콘솔 계열 함정 — 자식 쪽이
    #    아니라 이 테스트가 읽는 쪽의 인코딩을 명시해야 한다).
    r = subprocess.run([sys.executable, "-u", "check_tx_paths.py"], cwd=HERE,
                        capture_output=True, text=True, encoding="utf-8", timeout=60)
    chk(r.returncode == 0, "실제 저장소 전체 — 클린(위반 0건)",
        (r.stdout[-300:] + r.stderr[-300:]))
    chk("seed_boq.py" in r.stdout, "★★★ 실제 실행 배너에도 seed_boq.py 가 보인다")
except Exception as e:
    chk(False, "★★★ 라운드574 [5] check_tx_paths.py 실제 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 66)
print(f"  {len(PASS)} / {len(PASS) + len(FAIL)} 통과")
if FAIL:
    print("  실패:")
    for n, d in FAIL:
        print(f"    · {n}  {d}")
print("=" * 66)
sys.exit(1 if FAIL else 0)
