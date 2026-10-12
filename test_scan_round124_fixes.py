# -*- coding: utf-8 -*-
"""스캔 124라운드 회귀 — check_orphan_chars.py 가 실제 배포되는 docs/ 를
   통째로 건너뛰고 'ㆍ'(정부 공식 업종 표기) 오탐이 진짜 신호를 덮었던 문제,
   check_tx_paths.py 가 app.py 만 보고(dispatch.py 10개·manage.py 2개
   함수 사각지대) 고정 6줄 룩백 창이 실전 코드에서 오탐을 냈던 문제.
   (123라운드 조사에서 발견, 124라운드에서 수정)

  [1] SKIP_DIRS 의 'docs' 는 이름만 보고 걸러 실제 GitHub Pages 공개
      사이트(개인정보처리방침 등 포함) 전체가 점검 대상에서 빠졌다.
  [2] 'ㆍ'(U+318D 아래아) 오탐이 app.py·compliance.py·여러 테스트에서
      반복 발화해, 같은 실행에서 진짜 깨진 문자(test_scan_round101_fixes.py
      의 U+FFFD, 이번에 같이 수정됨)가 오탐 더미에 묻혔다.
  [3] check_tx_paths.py 가 app.py 만 하드코딩해서 봐 dispatch.py·manage.py
      의 BEGIN IMMEDIATE 함수 12개가 사각지대였다.
  [4] 고정 6줄 룩백 창이 (a) 커밋 후 후처리 코드, (b) BEGIN IMMEDIATE 자체가
      실패한 except 안의 return, (c) return 이 자신을 감싼 try/finally 보다
      소스상 앞에 있는 경우를 오탐으로 잡았다.

      python test_scan_round124_fixes.py
"""
import ast
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


print("═" * 72)
print("  스캔 124라운드 회귀 — check_orphan_chars docs스킵·ㆍ오탐 / check_tx_paths 범위·오탐")
print("═" * 72)

sys.path.insert(0, HERE)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
COC_SRC = read("check_orphan_chars.py")
chk('"docs"' not in COC_SRC.split("SKIP_DIRS = {", 1)[1].split("}", 1)[0],
    "★★★ check_orphan_chars.py 의 SKIP_DIRS 에서 'docs' 가 빠졌다")
chk("_JAMO_OK" in COC_SRC, "★★ check_orphan_chars.py 가 'ㆍ' 예외를 둔다")
chk("입찰과" in read("test_scan_round101_fixes.py")
    and "�" not in read("test_scan_round101_fixes.py"),
    "★ test_scan_round101_fixes.py 의 진짜 깨진 문자(U+FFFD)가 고쳐졌다")

CTP_SRC = read("check_tx_paths.py")
#  ⚠⚠ [라운드574] 예전엔 옛(3파일) 튜플 리터럴 전체를 그대로 문자열 대조했다 —
#    round574 가 이 상수에 "seed_boq.py" 를 정당하게 더 추가하자(자기 자신도
#    같은 이유로 app.py 만 보다 dispatch.py·manage.py 를 놓쳤던 이 라운드와
#    똑같은 사각지대) 그 정확한 리터럴이 더는 소스에 없어 오탐(회귀 아닌데
#    실패)이 났다. 이 검사의 진짜 의도는 "dispatch.py·manage.py 가 여전히
#    포함되는가"이지 "정확히 이 세 파일뿐인가"가 아니므로, TARGET_FILES 튜플
#    본문만 도려내 그 안에 세 이름이 다 있는지로 판정한다 — 앞으로 파일이
#    더 늘어도(이미 한 번 늘었듯) 안 깨지고, 셋 중 하나라도 빠지면 여전히 잡는다.
_ctp_target_body = CTP_SRC.split("TARGET_FILES = (", 1)[1].split(")", 1)[0]
chk(all(f'"{_f}"' in _ctp_target_body for _f in ("app.py", "dispatch.py", "manage.py")),
    "★★★ check_tx_paths.py 가 dispatch.py·manage.py 도 검사한다"
    "(round574가 seed_boq.py 를 추가해도 이 셋은 계속 포함되는지만 본다)",
    _ctp_target_body)
chk("def safe_lock_failure_returns(fn, conn_names):" in CTP_SRC,
    #  ⚠ [라운드291] conn_names 인자가 추가됐다(커넥션 이름을 conn 하나로
    #    하드코딩하던 결함을 고치면서) — 함수가 실존하는지만 보던 이 검사도
    #    새 시그니처에 맞춘다.
    "★★ BEGIN IMMEDIATE 자체 실패 시의 return 을 구조적으로 안전 처리한다")
chk("def safe_finally_protected_returns(fn):" in CTP_SRC,
    "★★ try/finally 로 보호된 return(소스상 finally 보다 앞이어도)을 안전 처리한다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — check_orphan_chars.py 가 docs/ 안의 깨진 문자를 실제로 찾는가")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round124_")
try:
    import check_orphan_chars as COC

    # (a) 'docs' 라는 이름의 폴더 안 파일도 이제 훑긴다(디렉터리 순회 로직 재사용)
    os.makedirs(os.path.join(_tmpdir, "docs", "legal"))
    broken = os.path.join(_tmpdir, "docs", "legal", "privacy.html")
    io.open(broken, "w", encoding="utf-8").write("<p>\ufffd 손상됨</p>")
    files = []
    for root, dirs, names in os.walk(_tmpdir):
        rel = os.path.relpath(root, _tmpdir).replace("\\", "/")
        dirs[:] = [d for d in dirs
                   if d not in COC.SKIP_DIRS and f"{rel}/{d}".lstrip("./") not in COC.SKIP_DIRS]
        for n in names:
            if n.endswith(COC.TARGET_EXT):
                files.append(os.path.join(root, n))
    chk(broken in files,
        "★★★ 'docs' 이름의 폴더 안 파일도 이제 순회 대상에 들어온다"
        "(예전엔 이름만 보고 통째로 건너뛰었다)", files)
    hits = COC.scan_file(broken)
    chk(any("FFFD" in why for _, why, _ in hits),
        "STEP scan_file() 자체는 원래도 정상 작동했다(순회에서만 빠졌었다)", hits)

    # (b) 'ㆍ' 는 더 이상 오탐, 진짜 깨진 자모는 여전히 잡힌다
    ok_file = os.path.join(_tmpdir, "ok.py")
    io.open(ok_file, "w", encoding="utf-8").write('CATEGORY = "금속ㆍ창호ㆍ지붕"\n')
    chk(COC.scan_file(ok_file) == [],
        "★★★ 'ㆍ'(정부 공식 업종 표기)는 더 이상 깨진 문자로 오탐되지 않는다",
        COC.scan_file(ok_file))

    bad_jamo_file = os.path.join(_tmpdir, "bad.py")
    io.open(bad_jamo_file, "w", encoding="utf-8").write('REGION = "ㅇㄴㅁㄹㄴㅁㅎㄹ"\n')
    hits2 = COC.scan_file(bad_jamo_file)
    chk(any("자모" in why for _, why, _ in hits2),
        "STEP 진짜 홀로 남은 자모(ㅇㄴㅁㄹ 류)는 여전히 잡힌다(과잉관용 아님)", hits2)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드124 준비/실행(check_orphan_chars)", f"{type(e).__name__} {e}")
finally:
    shutil.rmtree(_tmpdir, ignore_errors=True)

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — check_tx_paths.py 가 실전 오탐 3종은 피하고 진짜 누수는 잡는가")
# ──────────────────────────────────────────────────────────────
try:
    import check_tx_paths as CTP

    SYNTH = (
        'def leaky_function(conn, case_id):\n'
        '    conn.execute("BEGIN IMMEDIATE")\n'
        '    c = conn.execute("SELECT 1").fetchone()\n'
        '    if not c:\n'
        '        return None\n'
        '    conn.commit()\n'
        '    return c\n'
        '\n'
        '\n'
        'def safe_function(conn, case_id):\n'
        '    conn.execute("BEGIN IMMEDIATE")\n'
        '    c = conn.execute("SELECT 1").fetchone()\n'
        '    if not c:\n'
        '        conn.rollback()\n'
        '        return None\n'
        '    conn.commit()\n'
        '    return c\n'
        '\n'
        '\n'
        'def safe_lock_failure(conn, case_id):\n'
        '    try:\n'
        '        conn.execute("BEGIN IMMEDIATE")\n'
        '    except Exception:\n'
        '        return None\n'
        '    conn.commit()\n'
        '    return case_id\n'
        '\n'
        '\n'
        'def safe_finally_far(conn, case_id):\n'
        '    conn.execute("BEGIN IMMEDIATE")\n'
        '    try:\n'
        '        c = conn.execute("SELECT 1").fetchone()\n'
        '        pad1 = 1\n'
        '        pad2 = 2\n'
        '        pad3 = 3\n'
        '        pad4 = 4\n'
        '        pad5 = 5\n'
        '        pad6 = 6\n'
        '        pad7 = 7\n'
        '        pad8 = 8\n'
        '        if not c:\n'
        '            return None\n'
        '    finally:\n'
        '        conn.commit()\n'
        '    return c\n'
    )
    tree = ast.parse(SYNTH)
    lines = SYNTH.splitlines()
    found = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        #  ⚠ [라운드291] begins_immediate()·safe_lock_failure_returns() 가
        #    이제 conn_names 를 요구한다(conn 하드코딩을 없애면서) — 이 합성
        #    함수들은 전부 conn 이라는 이름을 그대로 쓰므로 conn_names_of() 가
        #    돌려주는 집합도 {"conn"}과 같아 동작은 그대로다.
        conn_names = CTP.conn_names_of(fn)
        bl = CTP.begins_immediate(fn, conn_names)
        if not bl:
            continue
        inner = set()
        for sub in ast.walk(fn):
            if sub is fn or not isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            for n in ast.walk(sub):
                inner.add(id(n))
        safe_lock_fail = CTP.safe_lock_failure_returns(fn, conn_names)
        safe_finally = CTP.safe_finally_protected_returns(fn)
        for r in ast.walk(fn):
            if not isinstance(r, ast.Return) or id(r) in inner:
                continue
            if id(r) in safe_lock_fail or id(r) in safe_finally:
                continue
            if r.lineno <= bl:
                continue
            window = "\n".join(lines[bl:r.lineno])
            if "conn.rollback()" in window or "conn.commit()" in window or "finally" in window:
                continue
            found.append(fn.name)

    chk(found == ["leaky_function"],
        "★★★ 진짜 잠금누수(leaky_function)는 잡고, 오탐 3종(safe_function·"
        "safe_lock_failure·safe_finally_far)은 안 잡는다", found)

    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = CTP.main()
    out = buf.getvalue()
    chk(rc == 0 and "모든 반환 경로가" in out,
        "★★★ 실제 코드베이스(app.py+dispatch.py+manage.py, 94개 함수)를 돌리면 "
        "깨끗하다(예전엔 dispatch.py:assign_dispatch·sweep_dispatches, "
        "manage.py:cmd_prune_orphans 가 오탐으로 찍혔다)", (rc, out[:300]))
    for _fn_name in ("assign_dispatch", "sweep_dispatches", "cmd_prune_orphans"):
        chk(_fn_name not in out,
            f"STEP 알려진 오탐 함수 {_fn_name}() 가 결과에 안 나온다", out[:500])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드124 준비/실행(check_tx_paths)", f"{type(e).__name__} {e}")

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
