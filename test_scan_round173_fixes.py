# -*- coding: utf-8 -*-
"""스캔 173라운드 회귀 — 전체재경매 유찰 처리가 탈락 업체에게 결과를 알리지도,
반려된 입찰을 무효화하지도 않던 결함.

  같은 함수(api_co_close_full)의 낙찰 분기(9819행 부근)는 notify_bid_losers 를
  부르는데 유찰 분기만 빠져 있었다. 형제 두 경로(추가분 유찰·원경매 유찰)는
  111·114라운드에서 이미 "탈락자 통지 + 입찰 무효화" 를 갖췄는데, 이 경로만
  전수감사에서 빠졌다 — 실측(운영DB): change_orders 0건이라 현재 피해자는
  없지만, 다음 회차(전체재경매)가 반려된 옛 입찰을 그대로 재사용하는 구조라
  첫 실사용 시 그대로 재현된다.

      python test_scan_round173_fixes.py
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
print("  스캔 173라운드 회귀 — 전체재경매 유찰의 탈락자 통지·입찰무효화 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_co_close_full(coid):")
i1 = APP_SRC.index("\n@app.", i0 + 1)
body = APP_SRC[i0:i1]
i_notify = body.find("notify_bid_losers(conn, au[\"id\"]")
i_void = body.find("void_reason='전체재경매 유찰'")
chk(i_notify > 0, "★★★ api_co_close_full 유찰 분기가 notify_bid_losers 를 부른다")
chk(i_void > 0, "★★★ api_co_close_full 유찰 분기가 반려된 입찰을 무효화한다")
chk(0 < i_notify < i_void,
    "★★★ 통지가 무효화보다 먼저다(notify_bid_losers 는 voided_at IS NULL 만 본다)",
    (i_notify, i_void))
chk('msg=f"[{_c[\'case_no\']}] 전체 재경매가 유찰 처리되어' in body,
    "★★★ 유찰 전용 문구를 넘긴다(msg 생략 시 '다른 업체로 확정' 거짓통지가 된다)")

# ============================================================
print("\n[2] 실행 — 입찰자 2곳이 있는 전체재경매를 유찰 처리")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round173_")
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
        "INSERT INTO insurers(name,status,login_id,created_at) "
        "VALUES('R173보험사','활성','r173i',?)", (DB.now(),)).lastrowid
    p1 = conn.execute(  # 원업체(incumbent) — 낙찰과 무관, 사건 배정용
        "INSERT INTO partners(name,partner_type,status,category,region,login_id,created_at) "
        "VALUES('R173원업체','시공사','활성','가드레일','서울','r173p1',?)", (DB.now(),)).lastrowid
    p2 = conn.execute(  # 전체재경매 입찰자 1 — 탈락해야 함
        "INSERT INTO partners(name,partner_type,status,category,region,login_id,created_at) "
        "VALUES('R173입찰A','시공사','활성','가드레일','서울','r173p2',?)", (DB.now(),)).lastrowid
    p3 = conn.execute(  # 전체재경매 입찰자 2 — 탈락해야 함
        "INSERT INTO partners(name,partner_type,status,category,region,login_id,created_at) "
        "VALUES('R173입찰B','시공사','활성','가드레일','서울','r173p3',?)", (DB.now(),)).lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,partner_id,is_demo,created_at) "
        "VALUES('R173-CASE','시공중','가드레일','서울',?,?,0,?)", (iid, p1, DB.now())).lastrowid
    coid = conn.execute(
        "INSERT INTO change_orders(case_id,round,incumbent_partner_id,incumbent_amount,"
        "                          reason,status,created_at) "
        "VALUES(?,1,?,1000000,'실사재현','전체재경매중',?)", (cid, p1, DB.now())).lastrowid
    aid = conn.execute(
        "INSERT INTO auctions(change_order_id,kind,status,deadline,created_at) "
        "VALUES(?,'전체재경매','진행',?,?)",
        (coid, DB.now(), DB.now())).lastrowid
    conn.execute("INSERT INTO bids(auction_id,partner_id,partner_name,amount,created_at) "
                 "VALUES(?,?,'R173입찰A',900000,?)", (aid, p2, DB.now()))
    conn.execute("INSERT INTO bids(auction_id,partner_id,partner_name,amount,created_at) "
                 "VALUES(?,?,'R173입찰B',950000,?)", (aid, p3, DB.now()))
    conn.commit(); conn.close()

    admin = A.app.test_client()
    atok = "r173-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = atok
    ahdr = {"X-CSRF-Token": atok}

    r = admin.post(f"/api/change-orders/{coid}/close-full",
                    json={"failed": True, "force": True}, headers=ahdr)
    j = r.get_json() or {}
    chk(r.status_code == 200 and j.get("ok") and j.get("failed") is True,
        "★★★ 유찰 처리 요청이 성공한다", (r.status_code, j))

    conn = DB.get_db()
    co_row = conn.execute("SELECT status FROM change_orders WHERE id=?", (coid,)).fetchone()
    chk(co_row["status"] == "유찰", "변경건 상태가 '유찰'", co_row["status"] if co_row else None)

    au_row = conn.execute("SELECT status FROM auctions WHERE id=?", (aid,)).fetchone()
    chk(au_row["status"] == "유찰", "경매 상태가 '유찰'", au_row["status"] if au_row else None)

    bid_rows = conn.execute(
        "SELECT partner_id, voided_at, void_reason FROM bids WHERE auction_id=? ORDER BY partner_id",
        (aid,)).fetchall()
    chk(len(bid_rows) == 2 and all(b["voided_at"] for b in bid_rows),
        "★★★ 두 입찰 모두 무효화됨(고치기 전엔 살아남아 다음 회차에 재사용될 수 있었다)",
        [dict(b) for b in bid_rows])
    chk(all(b["void_reason"] == "전체재경매 유찰" for b in bid_rows),
        "무효 사유가 정확히 남음", [b["void_reason"] for b in bid_rows])

    notifs = conn.execute(
        "SELECT partner_id, message FROM notifications "
        " WHERE ntype='입찰결과' AND partner_id IN (?,?)", (p2, p3)).fetchall()
    got_pids = {n["partner_id"] for n in notifs}
    chk(got_pids == {p2, p3},
        "★★★ 탈락 업체 둘 다 결과 통지를 받음(고치기 전엔 통지가 아예 없었다)",
        got_pids)
    chk(all("성립되지 않았습니다" in n["message"] for n in notifs),
        "★★★ 통지 문구가 '유찰'을 말한다(msg 생략 시 나오는 기본문구가 아님)",
        [n["message"] for n in notifs])
    chk(all("다른 업체로 확정" not in n["message"] for n in notifs),
        "★★★★ 아무도 안 낙찰됐는데 '다른 업체로 확정'이라는 거짓 통지를 하지 않는다"
        "(111라운드가 명시적으로 경고한 위험 — msg 생략 시 정확히 이 문구가 나간다)",
        [n["message"] for n in notifs])
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드173 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
