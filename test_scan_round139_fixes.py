# -*- coding: utf-8 -*-
"""스캔 139라운드 회귀 — 2건.

  [1] sweep_auctions()의 무입찰 자동유찰 분기가 cases.low_price·
      auctions.low_price·bid_count 를 리셋하지 않는다. 투찰 후 그 업체가
      경고·퇴출로 강등되면(활성 재확인은 이미 잘 되어 있어 nb=0으로 정확히
      '무입찰'로 판정하지만) 옛 입찰 캐시가 남아, 실제로는 낙찰자가 없는
      유찰 사건의 금액이 "진행중 총 공사금액" 집계에 계속 얹힌다. 수동
      관리자 경로(api_case_fail_bidding)는 이미 이 값들을 지운다 — 같은
      값으로 맞춘다.
  [2] 낙찰업체 재배정 경로 2곳(api_case_cancel_award, api_co_close_full)이
      밀려난(옛) 업체의 실적 캐시(win_rate/jobs_done)를 재계산하지 않는다
      — 부도·잠적으로 낙찰이 취소된 바로 그 업체가 실제보다 좋아 보이는
      실적을 영구히 달고 있게 된다.

      python test_scan_round139_fixes.py
"""
import io
import os
import sqlite3
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
print("  스캔 139라운드 회귀 — 무입찰유찰 low_price 미리셋 · 낙찰재배정 실적재계산 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_sw = APP_SRC.index("def sweep_auctions(")
i_sw_end = APP_SRC.index("\ndef ", i_sw + 1)
sw_body = APP_SRC[i_sw:i_sw_end]
chk("status='유찰', low_price=0, bid_count=0" in sw_body,
    "★★★ sweep_auctions 무입찰 분기가 auctions.low_price·bid_count 를 리셋한다")
chk("UPDATE cases SET low_price=NULL WHERE id=?" in sw_body,
    "★★★ sweep_auctions 무입찰 분기가 cases.low_price 도 리셋한다")

i_ca = APP_SRC.index("def api_case_cancel_award(cid):")
i_ca_end = APP_SRC.index("\ndef ", i_ca + 1)
ca_body = APP_SRC[i_ca:i_ca_end]
chk("_resync_partner_stats(conn, old_partner)" in ca_body,
    "★★★ api_case_cancel_award 가 밀려난 업체의 실적을 재계산한다")

i_cf = APP_SRC.index("def api_co_close_full(coid):")
i_cf_end = APP_SRC.index("\ndef ", i_cf + 1)
cf_body = APP_SRC[i_cf:i_cf_end]
chk('_resync_partner_stats(conn, c["partner_id"])' in cf_body,
    "★★★ api_co_close_full 가 밀려난 옛 업체의 실적을 재계산한다")

# ============================================================
print("\n[2] 실행 — 실제 app.py(전체 임포트) + sqlite3 로 재현")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round139_")
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
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','최고관리자')")
    iid = conn.execute(
        "INSERT INTO insurers(name,org_type,status,fee_rate_bp) "
        "VALUES('R139보험','손해보험','활성',900)").lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region) "
        "VALUES('R139업체','시공사','활성','가드레일','서울')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
        "VALUES('R139-AUC','입찰중','가드레일','서울',?,0)", (iid,)).lastrowid
    aid = conn.execute(
        "INSERT INTO auctions(case_id,status,deadline) "
        "VALUES(?,'진행',datetime('now','+9 hours','-1 hours'))", (cid,)).lastrowid
    conn.execute("INSERT INTO bids(auction_id,partner_id,amount) VALUES(?,?,9000000)", (aid, pid))
    conn.execute("UPDATE cases SET low_price=9000000 WHERE id=?", (cid,))
    conn.execute("UPDATE auctions SET low_price=9000000, bid_count=1 WHERE id=?", (aid,))
    #  투찰 뒤 이 업체가 강등됨(사유 무관 — 마감시각과 별개로 언제든 가능한 정상 동작)
    conn.execute("UPDATE partners SET status='경고' WHERE id=?", (pid,))
    conn.commit()

    res = A.sweep_auctions(conn, force=True)
    row = conn.execute("SELECT status, low_price FROM cases WHERE id=?", (cid,)).fetchone()
    arow = conn.execute("SELECT status, low_price, bid_count FROM auctions WHERE id=?", (aid,)).fetchone()
    chk(row["status"] == "유찰" and row["low_price"] is None,
        "★★★ 강등된 업체의 옛 입찰로 무입찰 유찰된 사건 — cases.low_price가 NULL로 지워진다"
        "(고치기 전엔 9,000,000원이 그대로 남아 진행중 공사금액 집계에 얹혔다)", dict(row))
    chk(arow["low_price"] == 0 and arow["bid_count"] == 0,
        "★★★ auctions.low_price·bid_count 도 0으로 지워진다", dict(arow))
    conn.close()

    # ── 시나리오 2: 낙찰취소 시 밀려난 업체 실적 재계산 ──────────────
    #  ⚠ win_rate 분모(_resync_partner_stats)는 bids 를 auctions 에 조인해 세고
    #    voided_at 은 안 본다(131라운드 확정 사양) — 그래서 cid2 를 취소해도
    #    분모는 그대로 2(cid2+cid3 둘 다 입찰), 분자만 1(cid2 는 award_amount
    #    가 NULL이 됨)로 줄어 100%→50%가 돼야 정상(재계산 안 되면 100% 그대로).
    conn = DB.get_db()
    #  ⚠ 시나리오1(pid)과 완전히 다른 업체를 쓴다 — 같은 업체를 재사용하면
    #    시나리오1이 남긴 입찰(무효화 안 됨, voided_at 은 이 계산식이 안 봄)이
    #    분모에 섞여 기대값이 어긋난다(실제로 처음엔 이 실수로 66.7%가 나왔다).
    pid2 = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region) "
        "VALUES('R139업체2','시공사','활성','가드레일','서울')").lastrowid
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,partner_name,"
        "                  award_amount,award_route,awarded_at,is_demo) "
        "VALUES('R139-CANCEL','시공중',?,?,?,'R139업체2',900000,'경매',datetime('now','+9 hours'),0)",
        ("가드레일", "서울", pid2)).lastrowid
    a1 = conn.execute("INSERT INTO auctions(case_id,status) VALUES(?,'낙찰')", (cid2,)).lastrowid
    conn.execute("INSERT INTO bids(auction_id,partner_id,amount) VALUES(?,?,900000)", (a1, pid2))
    #  이 업체의 다른 사건은 이미 완료·낙찰 — 취소 대상과 무관하게 그대로 남아야 한다
    cid3 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,award_amount,"
        "                  award_route,is_demo) "
        "VALUES('R139-DONE','완료',?,?,?,700000,'경매',0)", ("가드레일", "서울", pid2)).lastrowid
    a2 = conn.execute("INSERT INTO auctions(case_id,status) VALUES(?,'낙찰')", (cid3,)).lastrowid
    conn.execute("INSERT INTO bids(auction_id,partner_id,amount) VALUES(?,?,700000)", (a2, pid2))
    conn.commit()
    A._resync_partner_stats(conn, pid2)
    conn.commit()
    before = dict(conn.execute("SELECT jobs_done, win_rate FROM partners WHERE id=?", (pid2,)).fetchone())
    chk(before["jobs_done"] == 1 and before["win_rate"] == 100.0,
        "★ (사전조건) 낙찰취소 전 — 낙찰 2건(진행중+완료) 모두 반영돼 승률 100%로 캐시돼 있다", before)

    admin = A.app.test_client()
    _tok = "r139-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}
    r = admin.post(f"/api/cases/{cid2}/cancel-award", json={"reason": "부도로 인한 낙찰 취소"}, headers=_hdr)
    chk(r.status_code == 200, "STEP 낙찰취소 요청이 200으로 처리된다", (r.status_code, r.get_data(as_text=True)))

    after = dict(conn.execute("SELECT jobs_done, win_rate FROM partners WHERE id=?", (pid2,)).fetchone())
    chk(after["jobs_done"] == 1 and after["win_rate"] == 50.0,
        "★★★ 낙찰취소 직후 실적 캐시가 실측으로 다시 계산된다 — 분모(입찰 2건)는 그대로인데"
        " 분자(유효 낙찰)가 1건으로 줄어 승률이 100%→50%로 즉시 반영된다"
        "(고치기 전엔 재계산 호출 자체가 없어 100%로 그대로 굳어 있었다)", after)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드139 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
