# -*- coding: utf-8 -*-
"""스캔 297라운드 회귀 — 표준단가 시드 도구(seed_boq.py·seed_boq_led.py) 결함 3건,
   이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 재실행 안전성(멱등성)·
   active/is_demo 플래그·price_src/price_date 출처컬럼은 실측 결과 전부 클린.

   ①[심각] seed_boq.load() 가 적재한 행에 sku_key 를 한 번도 채우지 않았다.
      standard_boq.sku_key 는 견적엔진이 DB 단가를 읽는 유일한 통로
      (app.py _load_price_book() 이 COALESCE(sku_key,'')<>'' 인 행만 내린다)인데,
      그걸 채우는 유일한 함수(db._backfill_sku_keys())는 db.migrate() 안에서만
      불린다 — 서버 재기동이나 manage.py migrate 를 하기 전까지, 방금 적재한
      실측단가(예: 가드레일 판(2W) 110,000원, 엔진 내장값과 이름·가격이 완전히
      같다)가 견적에 전혀 반영되지 않는다. 화면·도구 출력 어디에도 이 사실이
      안 보인다(적재 성공 메시지만 뜬다). _backfill_sku_keys() 는 NULL 인 행만
      채우고(운영자가 손으로 넣은 값은 안 건드림) 스스로 커밋하는 멱등 함수라
      load() 커밋 직후에 그대로 재사용해 고쳤다.
   ② seed_boq.load() 가 값이 하나도 안 바뀐 재실행에도 매번 '수정'(old==new)
      이력을 boq_price_history 에 남겼다 — 이력의 존재 이유(나중에 개정을
      추적하는 소명 자료)를 재실행 소음이 덮어버린다. 이미 있던 가격-변경
      여부 판정(print 문 조건)을 이력 기록에도 그대로 적용해, 값이 실제로
      바뀐 경우에만 남기도록 고쳤다.
   ③ seed_boq_led.py 의 2017년 값 사용중지 로직이 active 조건 없이 매번
      다시 걸렸다 — 이미 비활성인 행도 재실행마다 다시 '비활성' 이력을
      남기고, 안 바뀐 재실행에도 "N건 사용중지"가 매번 그대로 찍혔다.
      SELECT·UPDATE 양쪽에 COALESCE(active,1)=1 조건을 더해 이미 비활성인
      행은 건드리지 않게 했다.

      python test_scan_round297_fixes.py
"""
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


SEED_SRC = read("seed_boq.py")
LED_SRC = read("seed_boq_led.py")

print("=" * 72)
print("  스캔 297라운드 회귀 — 표준단가 시드도구 sku_key 미백필·이력 소음 2건")
print("=" * 72)


def _section(src, start_marker, end_marker):
    i0 = src.index(start_marker)
    i1 = src.index(end_marker, i0 + len(start_marker))
    return src[i0:i1]


LOAD_BODY = _section(SEED_SRC, "\ndef load(", "\ndef main(")

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
#  ⚠ .index() 는 앵커가 아예 없으면 예외로 죽어 뒤 검사·[2]~[4] 실행 단계를
#    통째로 막는다(결함을 되살긴 잡아도 진단정보가 줄어든다) — in 으로 먼저
#    있는지 보고, 있을 때만 순서를 비교한다.
_has_backfill = "DB._backfill_sku_keys(conn)" in LOAD_BODY
chk(_has_backfill, "★★★ load() 가 커밋 뒤 sku_key 백필을 부른다")
if _has_backfill and "conn.commit()" in LOAD_BODY:
    _commit_idx = LOAD_BODY.index("conn.commit()")
    _backfill_idx = LOAD_BODY.index("DB._backfill_sku_keys(conn)")
    chk(_backfill_idx > _commit_idx,
        "★★★ 백필 호출이 실제 커밋 **뒤**에 있다(dry-run 오염 방지)",
        (_commit_idx, _backfill_idx))
else:
    chk(False, "★★★ 백필 호출이 실제 커밋 **뒤**에 있다(dry-run 오염 방지)",
        "백필 호출 자체가 없어 순서를 비교할 수 없음")

_if_ex_idx = LOAD_BODY.index("if ex:")
_else_idx = LOAD_BODY.index("\n            else:", _if_ex_idx)
EX_BRANCH = LOAD_BODY[_if_ex_idx:_else_idx]
#  ⚠ [라운드312] EX_BRANCH 에 이제 DB.boq_history(conn, ex["id"] 호출이 두 개다
#    (관리자가 비활성한 항목을 되살릴 때 남기는 action="재활성" 호출이 새로
#    추가돼, "수정" 호출보다 텍스트상 앞에 온다) — 접두어만 보던 예전 검색은
#    항상 앞쪽(재활성)을 찾아버려 "수정 호출이 가격판정 안쪽에 있다"는 이
#    검사 본연의 의도(안 바뀐 재실행엔 안 찍힌다)와 무관하게 깨진다. "수정"
#    액션 호출로 문자열을 좁혀 원래 의도 그대로 검사한다.
_has_price_check = 'if ex["ref_price"] != price:' in EX_BRANCH
_has_history_call = 'DB.boq_history(conn, ex["id"], _hrow, action="수정"' in EX_BRANCH
if _has_price_check and _has_history_call:
    _price_check_idx = EX_BRANCH.index('if ex["ref_price"] != price:')
    _history_idx = EX_BRANCH.index('DB.boq_history(conn, ex["id"], _hrow, action="수정"')
    chk(_history_idx > _price_check_idx,
        "★★★ '수정' 이력 기록이 가격변경 판정 **안쪽**으로 들어갔다"
        "(안 바뀐 재실행에서 더는 안 찍힘)", (_price_check_idx, _history_idx))
else:
    chk(False,
        "★★★ '수정' 이력 기록이 가격변경 판정 **안쪽**으로 들어갔다"
        "(안 바뀐 재실행에서 더는 안 찍힘)",
        "가격변경 판정 또는 이력기록 호출 자체를 못 찾음")

chk('WHERE major=? AND price_date=\'2017\' AND COALESCE(active,1)=1' in LED_SRC,
    "★★ seed_boq_led.py SELECT 가 이미 비활성인 행은 다시 안 본다")
chk("WHERE major=? AND price_date='2017' AND COALESCE(active,1)=1" in LED_SRC,
    "★★ seed_boq_led.py UPDATE 도 이미 비활성인 행은 다시 안 건드린다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — sku_key 자동백필이 재기동 없이 바로 먹는가(격리 DB, 실제 load())")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round297_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import seed_boq as SB
    import repair_estimate as RE

    added, skipped, retired = SB.load(SB.ROWS, dry=False)
    chk(added > 0 and skipped == 0,
        "STEP 실제 ROWS 적재 성공(전제 확인)", (added, skipped, retired))

    conn = DB.get_db()
    null_after_load = conn.execute(
        "SELECT COUNT(*) FROM standard_boq WHERE sku_key IS NULL").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM standard_boq").fetchone()[0]
    chk(null_after_load < total,
        "★★★ load() 직후(재기동 전) 일부 행이 이미 sku_key 를 갖고 있다"
        "(고치기 전엔 전부 NULL — 엔진 내장값과 이름·가격이 같은 항목도 전부 안 잡혔다)",
        (null_after_load, total))

    #  가드레일 판(2W) — 조사 에이전트가 확인한 실제 SKU 일치 사례를 그대로 재확인
    row = conn.execute(
        "SELECT sku_key FROM standard_boq WHERE item='가드레일 판(2W)' "
        " AND ref_price=110000").fetchone()
    chk(row is not None and row["sku_key"],
        "★★★ '가드레일 판(2W)' 행이 재기동 없이 엔진 SKU 와 실제로 연결됐다",
        row["sku_key"] if row else None)

    #  _load_price_book() 과 정확히 같은 조건으로 직접 재현 — 엔진이 실제로 보는가
    book_rows = conn.execute(
        "SELECT sku_key, ref_price FROM standard_boq "
        " WHERE COALESCE(active,1)=1 AND COALESCE(sku_key,'') <> ''").fetchall()
    book = {r["sku_key"]: r["ref_price"] for r in book_rows}
    matched_skus = [k for k in RE.SKU if k in book]
    chk(len(matched_skus) > 0,
        "★★★ _load_price_book() 과 동일 조건의 조회가 재기동 없이 SKU 를 찾아낸다"
        "(고치기 전엔 이 목록이 항상 빈 채였다 — db.migrate() 를 불러야만 채워졌다)",
        matched_skus[:5])
    conn.close()

    # ══════════════════════════════════════════════════════════
    print("\n[3] 실행 — 값이 안 바뀐 재실행은 '수정' 이력을 안 남기는가(실제 load() 재호출)")
    # ──────────────────────────────────────────────────────────
    conn = DB.get_db()
    before_mod = conn.execute(
        "SELECT COUNT(*) FROM boq_price_history WHERE action='수정'").fetchone()[0]
    conn.close()
    chk(before_mod == 0, "STEP 첫 적재는 전부 '추가'라 '수정' 이력이 0건이다(전제 확인)", before_mod)

    added2, _, _ = SB.load(SB.ROWS, dry=False)
    conn = DB.get_db()
    after_same = conn.execute(
        "SELECT COUNT(*) FROM boq_price_history WHERE action='수정'").fetchone()[0]
    conn.close()
    chk(after_same == 0,
        "★★★ 값이 하나도 안 바뀐 재실행 뒤에도 '수정' 이력이 여전히 0건이다"
        f"(고치기 전엔 이 재실행 한 번으로 '수정' {added2}건이 새로 쌓였다)", after_same)

    #  이번엔 실제로 한 행의 가격을 바꿔 재적재 — 정상적인 '수정'은 여전히 남아야 한다
    changed_rows = [list(r) for r in SB.ROWS]
    changed_rows[0][4] = changed_rows[0][4] + 1000
    SB.load(changed_rows, dry=False)
    conn = DB.get_db()
    after_change = conn.execute(
        "SELECT COUNT(*) FROM boq_price_history WHERE action='수정'").fetchone()[0]
    conn.close()
    chk(after_change == 1,
        "★★ 실제로 가격이 바뀐 재적재는 정확히 1건의 '수정' 이력을 남긴다(회귀 없음)",
        after_change)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드297 [2][3] 실측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

# ══════════════════════════════════════════════════════════════
print("\n[4] 실행 — seed_boq_led.py 를 실제로 두 번 돌려 재실행 안전성 확인(격리 DB, 실제 서브프로세스)")
# ──────────────────────────────────────────────────────────────
_tmpdir2 = tempfile.mkdtemp(prefix="round297_led_")
_dbpath = os.path.join(_tmpdir2, "verify.db")
try:
    _env = dict(os.environ)
    _env["BOKGUON_DB_PATH"] = _dbpath
    _env["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir2, "uploads")
    _env["BOKGUON_ENV"] = "dev"
    _env["BOKGUON_SEED_DEMO"] = "0"

    #  ⚠ db.DB_PATH 는 모듈 import 시점에 한 번 고정되는 상수라(db.py 17행),
    #    [2][3] 에서 이미 import 된 뒤 환경변수만 바꿔선 다음 DB 로 안 옮겨간다
    #    — round292 의 선례(DB.DB_PATH = missing_path 직접 대입)와 같은 방식으로
    #    모듈 속성을 직접 바꾼다(재import·reload 보다 부작용이 적다).
    import db as DB2
    DB2.DB_PATH = _dbpath
    DB2.init_db()
    conn = DB2.get_db()
    cur = conn.execute(
        "INSERT INTO standard_boq(major,item,spec,unit,ref_price,price_src,price_date,"
        "                         active,is_demo,created_at,updated_at) "
        "VALUES('간판·전기·가로등','297라운드 검증용 2017년 항목','','개',568400,"
        "       '회귀검증 픽스처',  '2017',1,0,?,?)",
        (DB2.now(), DB2.now()))
    fixture_id = cur.lastrowid
    conn.commit()
    conn.close()

    def run_led():
        r = subprocess.run([PY, "-u", "seed_boq_led.py"], cwd=HERE, env=_env,
                            capture_output=True, text=True, encoding="utf-8", timeout=60)
        return r.returncode, r.stdout + r.stderr

    rc1, out1 = run_led()
    chk(rc1 == 0, "STEP seed_boq_led.py 1차 실행 성공", (rc1, out1[-500:]))
    chk("2017년 값 사용중지: 1건" in out1,
        "STEP 1차 실행이 픽스처 1건을 정확히 사용중지시켰다(전제 확인)", out1)

    rc2, out2 = run_led()
    chk(rc2 == 0, "STEP seed_boq_led.py 2차(재실행) 성공", (rc2, out2[-500:]))
    chk("2017년 값 사용중지: 0건" in out2,
        "★★ 이미 비활성인 행은 재실행에서 더는 다시 안 걸린다"
        "(고치기 전엔 재실행마다 '사용중지: 1건'이 그대로 반복 출력됐다)", out2)

    import sqlite3
    conn = sqlite3.connect(_dbpath)
    conn.row_factory = sqlite3.Row
    hist_count = conn.execute(
        "SELECT COUNT(*) FROM boq_price_history WHERE boq_id=? AND action='비활성'",
        (fixture_id,)).fetchone()[0]
    active_now = conn.execute(
        "SELECT active FROM standard_boq WHERE id=?", (fixture_id,)).fetchone()[0]
    conn.close()
    chk(active_now == 0, "STEP 픽스처 행은 실제로 비활성 상태다(회귀 없음)", active_now)
    chk(hist_count == 1,
        "★★★ 두 번 실행했는데도 '비활성' 이력은 정확히 1건뿐이다"
        f"(고치기 전엔 실행마다 하나씩 쌓여 2건이 됐다 — 실측: {hist_count}건)", hist_count)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드297 [4] seed_boq_led.py 재실행 검증", f"{type(e).__name__} {e}")
finally:
    for k in ("BOKGUON_DB_PATH", "BOKGUON_UPLOAD_DIR", "BOKGUON_ENV", "BOKGUON_SEED_DEMO"):
        os.environ.pop(k, None)
    import shutil
    shutil.rmtree(_tmpdir2, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
