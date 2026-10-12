# -*- coding: utf-8 -*-
"""스캔 291라운드 회귀 — 자기진단 도구 두 개(check_tx_paths.py·
   check_orphan_chars.py)의 사각지대 결함 4건, 이 세션 사상 첫 정밀조사로
   정밀조사 Agent가 발견(tray.js·lightbox.js 는 이미 290라운드에서 클린으로
   확인된 static/ 나머지 파일).

  이 두 파일은 "실제 결함을 잡는 도구"가 아니라 "결함을 잡아야 할 도구
  자신이 사각지대를 갖고 있는가"를 보는 자기진단 대상이다(round285
  smoke_test.py·round272 popbill_check.py 와 같은 계열).

  ① check_tx_paths.py — BEGIN IMMEDIATE 로 쓰기 잠금을 잡은 함수의 모든
     return 이 commit/rollback 을 거치는지 보는 정적분석 도구.
     (a)[심각] begins_immediate() 가 calls_of() 의 **첫 항목**을 잠금
        시작줄로 썼는데, calls_of() 는 ast.walk() 의 너비우선 순서를 쓴다 —
        소스상의 줄 순서가 아니다. app.py 의 api_login_otp() 처럼 BEGIN
        IMMEDIATE 가 두 번(하나는 if 안쪽 2475행, 하나는 그 뒤 최상위
        2493행) 나오면 더 얕은 뒤쪽(2493)이 먼저 나와, 진짜 첫 잠금(2475)
        직후의 return 두 개(2483·2487행)가 "잠금 이전"으로 오판돼 검사를
        완전히 건너뛰었다(지금은 둘 다 우연히 정상 커밋/롤백돼 있어 실제
        누락 사고는 없다 — 도구의 사각지대일 뿐). 가장 이른 줄번호를 쓰도록
        수정.
     (b) calls_of()·_is_begin_immediate_call() 이 커넥션 변수명을 "conn"
        하나로만 하드코딩했다 — app.py 의 _upload_damage_photos() 처럼
        두 번째 커넥션을 c2 라는 별도 이름으로 여는 함수의 그 임계구역은
        이름 매칭 자체를 못 지나쳐 존재 자체가 안 보였다. DB.get_db() 로
        대입받는 이름은 전부 커넥션으로 인식하도록 수정(하드코딩 목록을
        늘리는 대신 함수 안에서 실제로 쓰는 이름을 스스로 찾는다).
  ② check_orphan_chars.py — 인코딩이 깨진 문자(BOM·NBSP 등)를 찾는 도구.
     BOM·NBSP 를 코드가 "그 문자 자체"를 다루려고 일부러 리터럴로 쓴 자리
     (.lstrip("﻿") 로 BOM 을 벗기는 코드, CSV 응답 앞에 BOM 을 붙이는
     코드, widont 스크립트의 NBSP 상수, 그 둘을 검증하는 테스트)까지
     산문이 깨진 것처럼 잡았다 — 실측: 정밀조사가 돌린 실행에서 나온 38건
     전부가 이 두 글자 범주였고 전부 오탐, 진짜 조치 대상은 0건이었다.
     round124 가 'ㆍ' 하나로 이미 겪은 "자주 우는 늑대" 문제의 재발이다.
     그 문자를 다룬다는 뜻의 식별자(.lstrip(·BOM·NBSP·\\ufeff)가 바로 앞뒤
     줄 안에 있으면 코드가 그 문자를 의도적으로 다루는 것으로 보고
     건너뛰도록 수정(같은 줄이 아니라 여러 줄에 걸친 문장도 놓치지 않게
     앞뒤 한 줄씩 같이 본다). 부수적으로 deploy/*.ps1 배포 스크립트가
     TARGET_EXT 에서 빠져 있던 것도 채움(round124 가 docs/ 를 채운 것과
     같은 이유 — 현재 살아있는 결함은 아니라 낮은 확신으로 표시됨).

      python test_scan_round291_fixes.py
"""
import ast
import io
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


TXPATHS_SRC = read("check_tx_paths.py")
ORPHAN_SRC = read("check_orphan_chars.py")

print("=" * 72)
print("  스캔 291라운드 회귀 — 자기진단 도구 두 개의 사각지대 결함 4건")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk("def conn_names_of(fn):" in TXPATHS_SRC,
    "★★★ check_tx_paths.py 가 DB.get_db() 대입으로 커넥션 이름을 스스로 찾는다")
chk("return min(linenos) if linenos else None" in TXPATHS_SRC,
    "★★★ begins_immediate() 가 너비우선 첫 항목이 아니라 최소 줄번호를 쓴다")
chk(".ps1" in ORPHAN_SRC.split("TARGET_EXT")[1][:80],
    "check_orphan_chars.py 의 TARGET_EXT 에 .ps1 이 추가됨")
chk('if ch == "\\xa0" and "NBSP" in nearby:' in ORPHAN_SRC,
    "★★★ check_orphan_chars.py 가 NBSP 리터럴 코드를 앞뒤줄까지 보고 건너뛴다")

# ============================================================
print("\n[2] 실행 — check_tx_paths.py 의 실제 함수를 합성 함수로 검증")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
try:
    import importlib
    CTP = importlib.import_module("check_tx_paths")

    # ── 2-a: api_login_otp 와 같은 모양(깊이가 다른 BEGIN IMMEDIATE 2개) ──
    src_a = '''
def api_login_otp():
    conn = DB.get_db()
    if ok:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute("UPDATE x SET y=1")
        if not cur.rowcount:
            conn.rollback(); conn.close()
            return 1                      # 진짜 첫 잠금(위) 직후 — 반드시 검사돼야 한다
        conn.commit(); conn.close()
        return 2
    conn.execute("BEGIN IMMEDIATE")       # 최상위(얕음) — 너비우선이면 이게 먼저 걸린다
    conn.commit(); conn.close()
    return 3
'''
    fn_a = ast.parse(src_a).body[0]
    names_a = CTP.conn_names_of(fn_a)
    bl_a = CTP.begins_immediate(fn_a, names_a)
    true_first = src_a.splitlines().index('        conn.execute("BEGIN IMMEDIATE")') + 1
    chk(bl_a == true_first,
        "★★★ 깊이가 다른 BEGIN IMMEDIATE 2개 중 소스상 진짜 첫 줄을 찾는다"
        "(너비우선 순서의 첫 항목이 아니라)", (bl_a, true_first))

    # ── 2-b: "conn" 이 아닌 별도 이름(c2)만 쓰는 함수 ──
    src_b = '''
def _upload_damage_photos_like():
    c2 = DB.get_db()
    c2.execute("BEGIN IMMEDIATE")
    ok = c2.execute("UPDATE cases SET x=1")
    if not ok:
        return None                       # c2 잠금 이후 — 커밋도 롤백도 없음(진짜 결함)
    c2.commit(); c2.close()
    return True
'''
    fn_b = ast.parse(src_b).body[0]
    names_b_old = {"conn"}
    names_b_new = CTP.conn_names_of(fn_b)
    chk("c2" not in names_b_old and "c2" in names_b_new,
        "★★★ conn_names_of() 가 c2 = DB.get_db() 대입을 커넥션으로 인식한다",
        names_b_new)
    chk(CTP.begins_immediate(fn_b, names_b_old) is None,
        "(대조군) 옛 방식대로 conn 만 보면 이 함수의 BEGIN IMMEDIATE 를 아예 못 찾는다")
    chk(CTP.begins_immediate(fn_b, names_b_new) is not None,
        "★★★ 고친 방식은 c2 기반 BEGIN IMMEDIATE 를 정확히 찾는다")

    # ── 2-c: 종단간 — 2-a·2-b 를 main() 과 같은 판정 루프로 직접 돌려
    #    "잠금 뒤 커밋/롤백 없는 return" 을 실제로 잡아내는지 증명 ──
    def check_fn(fn):
        conn_names = CTP.conn_names_of(fn)
        bl = CTP.begins_immediate(fn, conn_names)
        if not bl:
            return None, []
        safe_lock_fail = CTP.safe_lock_failure_returns(fn, conn_names)
        safe_finally = CTP.safe_finally_protected_returns(fn)
        src_lines = ast.unparse(fn).splitlines() if hasattr(ast, "unparse") else None
        bad = []
        for r in ast.walk(fn):
            if not isinstance(r, ast.Return):
                continue
            if id(r) in safe_lock_fail or id(r) in safe_finally:
                continue
            if r.lineno <= bl:
                continue
            bad.append(r.lineno)
        return bl, bad

    # src_a: 모든 return 이 실제로 안전(커밋/롤백 있음) — 이번 수정으로 새로
    #   검사대상이 된 return(1·2행)도 문제가 없어야 한다(회귀 없음 확인용).
    #   window 검사는 main() 안에만 있으므로 여기서는 대상 판별(bl·후보목록)만 검증한다.
    bl_a2, cand_a = check_fn(fn_a)
    chk(bl_a2 == true_first and set(cand_a) == {true_first + 4, true_first + 6, true_first + 9},
        "지점1 검증용 함수: 잠금 이후 return 세 개(전부 안전한 것들)가 후보로 잡힌다"
        "(고치기 전엔 1·2행의 return 이 '잠금 이전'으로 오판돼 후보에도 안 들어갔다)",
        (bl_a2, cand_a))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드291 [2] check_tx_paths.py 합성함수 검증", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — check_tx_paths.py 를 실제 app.py 에 대해 돌려 회귀 없음 확인")
# ------------------------------------------------------------
try:
    import subprocess
    r = subprocess.run([sys.executable, "-u", "check_tx_paths.py"], cwd=HERE,
                        capture_output=True, text=True, encoding="utf-8", timeout=30)
    out = r.stdout + r.stderr
    chk(r.returncode == 0 and "모든 반환 경로가 commit 또는 rollback" in out,
        "실제 app.py/dispatch.py/manage.py 에 대해서는 여전히 클린(회귀 없음)"
        "(고친 뒤에도 진짜 결함이 새로 생기지 않았다는 뜻)", out[-300:])
    m_cnt = re.search(r"BEGIN IMMEDIATE 쓰는 함수 (\d+)개", out)
    chk(bool(m_cnt) and int(m_cnt.group(1)) >= 94,
        "검사대상 함수 94개 이상 유지(라운드291 당시 94개가 바닥값 — "
        "_upload_damage_photos 는 이미 conn 기반으로도 검사되고 있었으므로 "
        "이 수정 자체는 개수를 늘리지도 줄이지도 않았다. 정확히 94로 고정하면 "
        "그 뒤 정당하게 새로 생기는 BEGIN IMMEDIATE 함수마다 이 낡은 스냅샷과 "
        "충돌하므로, '그때 잡히던 함수들이 지금도 여전히 하나도 안 빠지고 "
        "잡히는지'라는 원래 의도만 하한으로 검사 — 예: 434라운드가 "
        "api_photo_unreject 에 BEGIN IMMEDIATE 를 새로 추가해 95개가 됐지만 "
        "이는 정당한 증가이자 이 하한을 여전히 만족)",
        (m_cnt.group(1) if m_cnt else None, out[:200]))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드291 [3] check_tx_paths.py 실제 실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[4] 실행 — check_orphan_chars.py 실제 오탐 소멸 + 진짜 결함은 여전히 잡힘")
# ------------------------------------------------------------
try:
    ORPHAN = importlib.import_module("check_orphan_chars")

    # 4-a: 실제 파일들의 이전 오탐 지점이 이제 안 잡힌다
    for relpath, must_not_flag_line in [
        ("envload.py", None), ("manage.py", None),
        (os.path.join("templates", "landing.html"), None),
    ]:
        hits = ORPHAN.scan_file(os.path.join(HERE, relpath))
        bad_hits = [h for h in hits if "BOM" in h[1] or "공백(U+00A0)" in h[1]]
        chk(not bad_hits, f"★★★ {relpath} — BOM/NBSP 오탐이 더는 없다", bad_hits)

    # app.py 는 파일이 커서 크게 하나만 콕 집어 확인(12617행의 BOM 리터럴)
    app_hits = ORPHAN.scan_file(os.path.join(HERE, "app.py"))
    app_bom_hits = [h for h in app_hits if "BOM" in h[1]]
    chk(not app_bom_hits, "★★★ app.py — CSV 응답의 의도된 BOM 리터럴이 더는 안 잡힌다",
        app_bom_hits)

    # 4-b: 합성 파일로 대조군 — 진짜 산문 오염은 여전히 잡혀야 한다(과잉관용 아님)
    _tmpdir = tempfile.mkdtemp(prefix="round291_")
    good_py = os.path.join(_tmpdir, "good_example.py")
    io.open(good_py, "w", encoding="utf-8").write(
        'line = line.strip().lstrip("﻿")  # BOM 제거\n'
        'var_like = "\xa0"  # NBSP 상수\n'
    )
    bad_py = os.path.join(_tmpdir, "bad_corrupted.py")
    io.open(bad_py, "w", encoding="utf-8").write(
        '안내문 = "정상﻿접수되었습니다"\n'      # 마커 없는 진짜 오염 흉내(BOM)
        '안내문2 = "정상\xa0접수되었습니다"\n'        # 마커 없는 진짜 오염 흉내(NBSP)
    )
    chk(not ORPHAN.scan_file(good_py),
        "합성 파일: BOM·NBSP 를 의도적으로 다루는 코드는 안 잡힌다")
    bad_hits2 = ORPHAN.scan_file(bad_py)
    chk(len(bad_hits2) == 2,
        "★★★ 합성 파일: 마커 없이 산문 속에 섞인 진짜 BOM/NBSP 오염은 여전히 둘 다 잡힌다"
        "(과잉관용으로 진짜 결함을 놓치지 않는다는 대조군)", bad_hits2)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드291 [4] check_orphan_chars.py 실제/합성 검증", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
