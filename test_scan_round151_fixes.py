# -*- coding: utf-8 -*-
"""스캔 151라운드 회귀 — 협력사 온보딩 화면의 "첫 입찰" 날짜가 재투찰(가격
인하) 뒤 틀어지던 결함.

  bids.created_at 은 재투찰마다 "마지막 제출 시각"으로 덮어써진다(db.py 의
  first_bid_at 마이그레이션 주석·app.py 재투찰 UPDATE 가 이미 명시하는 사실).
  그런데 온보딩 목록 조회(ONBOARD_COLS)는 이미 존재하는 전용 컬럼
  bids.first_bid_at 을 무시하고 MIN(created_at) 을 다시 계산해, 재투찰이
  있었던 업체의 "첫 입찰" 표시가 최초 투찰일이 아니라 최근 재투찰일로 나왔다.
  (단계 배지 stage_of() 는 truthy 만 보므로 이 값이 틀려도 안 바뀐다 —
  영향은 표시되는 날짜값 한 가지뿐이었다.)

      python test_scan_round151_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 151라운드 회귀 — 온보딩 화면 '첫 입찰' 날짜가 재투찰로 틀어지던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk("(SELECT MIN(COALESCE(first_bid_at, created_at)) FROM bids b" in APP_SRC,
    "★★★ ONBOARD_COLS 가 이제 bids.first_bid_at(진짜 최초 투찰 시각)을 쓴다")
chk("(SELECT MIN(created_at) FROM bids b WHERE b.partner_id=partners.id)" not in APP_SRC,
    "★ 옛 MIN(created_at) 서브쿼리(재투찰로 틀어지는 원인)가 사라졌다")

# ============================================================
print("\n[2] 실행 — 실제 app.py(전체 임포트)로 최초투찰→재투찰 재현")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round151_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    admin = A.app.test_client()
    tok = "r151-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "하위관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = tok
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','하위관리자')")

    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,login_id) "
        "VALUES('R151업체','시공사','활성','가드레일','서울','r151p')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R151-CASE','입찰중','가드레일','서울',0)").lastrowid
    aid = conn.execute(
        "INSERT INTO auctions(case_id,status,deadline) "
        "VALUES(?,'진행',datetime('now','+9 hours','+1 hours'))", (cid,)).lastrowid
    #  최초 투찰(2026-08-01) — first_bid_at·created_at 둘 다 이 시각으로 남는다.
    bid_id = conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,"
        "                 created_at,first_bid_at,is_demo) "
        "VALUES(?,?,?,?,?,?,?,0)",
        (aid, pid, "R151업체", 9000000, 7, "2026-08-01 09:00:00", "2026-08-01 09:00:00")).lastrowid
    conn.commit()

    #  재투찰(인하) — created_at 만 최신으로 바뀌고, first_bid_at 은 그대로 보존된다
    #  (app.py 재투찰 UPDATE 와 정확히 같은 모양의 문장으로 재현).
    conn.execute(
        "UPDATE bids SET amount=?, created_at=?, "
        "                first_bid_at=COALESCE(first_bid_at, created_at) WHERE id=?",
        (8500000, "2026-08-15 09:00:00", bid_id))
    conn.commit()

    row = dict(conn.execute(
        "SELECT created_at, first_bid_at FROM bids WHERE id=?", (bid_id,)).fetchone())
    chk(row["created_at"] == "2026-08-15 09:00:00" and row["first_bid_at"] == "2026-08-01 09:00:00",
        "★ (사전조건) 재투찰 후 created_at 은 최신, first_bid_at 은 최초 그대로다", row)

    r = admin.get("/api/partner-onboarding")
    chk(r.status_code == 200, "STEP 온보딩 API 호출 200", r.status_code)
    data = r.get_json()
    prow = next((p for p in data["rows"] if p["id"] == pid), None)
    chk(prow is not None, "★ (사전조건) 응답에 해당 업체가 포함된다")
    chk(prow["first_bid_at"] == "2026-08-01 09:00:00",
        "★★★ 온보딩 화면의 first_bid_at 이 최초 투찰일(08-01)을 가리킨다"
        "(고치기 전엔 재투찰일 08-15가 나왔다)", prow.get("first_bid_at"))
    chk(prow["stage"] == "입찰 경험 있음",
        "★ 단계 배지는 이 수정과 무관하게 여전히 정확하다(truthy 판정 보존)", prow.get("stage"))

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드151 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
