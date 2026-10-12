# -*- coding: utf-8 -*-
"""스캔 42라운드 회귀 — 낙찰 확정 3개 라우트의 금액 이중 방어.

  조사 에이전트가 찾은 결함: 입찰 제출 라우트는 이미 0원·음수를 전부
  막지만(parse_money), **낙찰을 확정하는 자리(보험사 낙찰·어드민 원경매
  낙찰·어드민 전체재경매 마감)는 그 bids.amount 값을 그대로 계약금액으로
  굳히면서 다시 확인하지 않았다**. 제출 관문을 실제로 우회할 방법은 지금
  없지만(제출 라우트 2곳 다 parse_money 로 막혀 있음 — 실측 확인됨), 관문이
  하나뿐이라 그 하나가 뚫리면 바로 계약금액이 오염된다. 웹훅 URL 검사가
  "쓸 때 + 보낼 때" 이중으로 보는 것과 같은 원칙으로, 낙찰 확정 시점에도
  한 번 더 본다.

  이 회귀는 정상 제출 경로가 아니라 **직접 SQL로 음수 입찰 행을 심어**
  (조사 에이전트가 결함을 증명한 것과 같은 방법 — "만약 다른 경로로 나쁜
  값이 들어온다면"의 시뮬레이션) 낙찰 라우트 자체가 스스로 막는지를 본다.

      python test_scan_round42_fixes.py
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("═" * 72)
print("  스캔 42라운드 회귀 — 낙찰 확정 금액 이중 방어(0원·음수 낙찰 차단)")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 3개 라우트 모두 방어가 있는가")
# ──────────────────────────────────────────────────────────────
GUARD_COUNT = APP_SRC.count(
    '        return jsonify({"ok": False, "error": "입찰 금액이 올바르지 않아 낙찰할 수 없습니다."}), 409')
chk(GUARD_COUNT == 3, "★★★ 낙찰 금액<=0 방어가 정확히 3곳(보험사·어드민 원경매·어드민 전체재경매)",
    f"{GUARD_COUNT}곳 발견")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 음수 입찰을 직접 심고, 3개 라우트가 전부 낙찰을 거부하는가")
# ──────────────────────────────────────────────────────────────
import tempfile
_tmpdir = tempfile.mkdtemp(prefix="award42_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin42','x','검증','최고관리자')")
    iid = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('검증보험사42','활성')").lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('검증업체42','시공사','활성')"
    ).lastrowid
    conn.commit()
    conn.close()

    import app as A
    client = A.app.test_client()
    _tok = "regress-round42-csrf-token"

    def _admin_sess(sess):
        sess["admin"] = "admin42"; sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = _tok

    def _insurer_sess(sess):
        sess["insurer_id"] = iid; sess["insurer_name"] = "검증보험사42"
        sess["_csrf"] = _tok

    _hdr = {"X-CSRF-Token": _tok}

    # ── ① 보험사 낙찰 ────────────────────────────────────────
    conn = DB.get_db()
    cid1 = conn.execute(
        "INSERT INTO cases(case_no,status,insurer_id,category,region) "
        "VALUES('검증42-A','입찰중',?,'금속','서울')", (iid,)).lastrowid
    auid1 = conn.execute(
        "INSERT INTO auctions(case_id,status) VALUES(?,'진행')", (cid1,)).lastrowid
    bid1 = conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount) VALUES(?,?,?,-777000)",
        (auid1, pid, "검증업체42")).lastrowid
    conn.commit(); conn.close()

    with client.session_transaction() as sess:
        _insurer_sess(sess)
    r = client.post(f"/api/insurer/cases/{cid1}/award", json={"bid_id": bid1}, headers=_hdr)
    d = r.get_json()
    chk(r.status_code == 409, "★★★ ① 보험사 낙찰 — 음수 입찰을 거부한다(고치기 전엔 200)",
        (r.status_code, d))
    conn = DB.get_db()
    row1 = conn.execute("SELECT status, award_amount FROM cases WHERE id=?", (cid1,)).fetchone()
    conn.close()
    chk(row1["status"] == "입찰중" and row1["award_amount"] is None,
        "① 사건 상태·낙찰금액이 오염되지 않았다", dict(row1))

    # ── ② 어드민 원경매 낙찰 ──────────────────────────────────
    conn = DB.get_db()
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,insurer_id,category,region) "
        "VALUES('검증42-B','입찰중',?,'금속','서울')", (iid,)).lastrowid
    auid2 = conn.execute(
        "INSERT INTO auctions(case_id,status) VALUES(?,'진행')", (cid2,)).lastrowid
    bid2 = conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount) VALUES(?,?,?,-555000)",
        (auid2, pid, "검증업체42")).lastrowid
    conn.commit(); conn.close()

    with client.session_transaction() as sess:
        _admin_sess(sess)
    r2 = client.post(f"/api/cases/{cid2}/award",
                      json={"bid_id": bid2, "insurer_instruction": "회귀검증용 유선지시 근거"},
                      headers=_hdr)
    d2 = r2.get_json()
    chk(r2.status_code == 409, "★★★ ② 어드민 원경매 낙찰 — 음수 입찰을 거부한다", (r2.status_code, d2))
    conn = DB.get_db()
    row2 = conn.execute("SELECT status, award_amount FROM cases WHERE id=?", (cid2,)).fetchone()
    conn.close()
    chk(row2["status"] == "입찰중" and row2["award_amount"] is None,
        "② 사건 상태·낙찰금액이 오염되지 않았다", dict(row2))

    # ── ③ 어드민 전체재경매 마감 ──────────────────────────────
    conn = DB.get_db()
    cid3 = conn.execute(
        "INSERT INTO cases(case_no,status,insurer_id,category,region) "
        "VALUES('검증42-C','시공중',?,'금속','서울')", (iid,)).lastrowid
    coid3 = conn.execute(
        "INSERT INTO change_orders(case_id,round,status) VALUES(?,1,'전체재경매중')", (cid3,)
    ).lastrowid
    auid3 = conn.execute(
        "INSERT INTO auctions(case_id,status,change_order_id,kind) "
        "VALUES(?,'진행',?,'전체재경매')", (cid3, coid3)).lastrowid
    bid3 = conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount) VALUES(?,?,?,-333000)",
        (auid3, pid, "검증업체42")).lastrowid
    conn.commit(); conn.close()

    r3 = client.post(f"/api/change-orders/{coid3}/close-full",
                      json={"bid_id": bid3, "force": True}, headers=_hdr)
    d3 = r3.get_json()
    chk(r3.status_code == 409, "★★★ ③ 어드민 전체재경매 마감 — 음수 입찰을 거부한다", (r3.status_code, d3))
    conn = DB.get_db()
    row3 = conn.execute("SELECT status FROM change_orders WHERE id=?", (coid3,)).fetchone()
    conn.close()
    chk(row3["status"] == "전체재경매중", "③ 변경건 상태가 오염되지 않았다", dict(row3))

    # ── 대조군 — 정상(양수) 입찰은 그대로 낙찰되는가(과잉차단 아님) ──
    conn = DB.get_db()
    cid4 = conn.execute(
        "INSERT INTO cases(case_no,status,insurer_id,category,region) "
        "VALUES('검증42-D','입찰중',?,'금속','서울')", (iid,)).lastrowid
    auid4 = conn.execute(
        "INSERT INTO auctions(case_id,status) VALUES(?,'진행')", (cid4,)).lastrowid
    bid4 = conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount) VALUES(?,?,?,1500000)",
        (auid4, pid, "검증업체42")).lastrowid
    conn.commit(); conn.close()

    with client.session_transaction() as sess:
        _insurer_sess(sess)
    r4 = client.post(f"/api/insurer/cases/{cid4}/award", json={"bid_id": bid4}, headers=_hdr)
    chk(r4.status_code == 200, "★ 정상 양수 입찰은 그대로 낙찰된다(과잉차단 아님)",
        (r4.status_code, r4.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 낙찰 이중 방어 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
