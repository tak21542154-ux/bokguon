# -*- coding: utf-8 -*-
"""스캔 113라운드 회귀 — 변경견적 발주처 확인(insurer_ack)의 생애주기 결함 3건.

  [1] (치명·컴플라이언스/금전기록) 전체재경매 낙찰(api_co_close_full)이 다른
      금액에 대한 옛 '확인'을 새 낙찰가에 그대로 옮겨 붙였다 — 발주처가
      확인한 적 없는 금액 옆에 '확인' 배지(담당자 실명·시각까지)가 뜬다.
      withdraw-offer 형제는 이미 금액이 바뀌면 확인 전체를 비운다.
  [2] (중간·기록 무결성) 발주처 확인 라우트(api_insurer_co_ack)에 변경견적
      상태 가드가 없어, 이미 종결(수락확정·낙찰확정·철회·최종유찰)된 건의
      유일한 승인 기록을 사후에 확인↔부동의로 뒤집을 수 있었다.
  [3] (중간·교착) 보험사 화면이 "부동의 뒤 마음이 바뀌면 아래에서 다시
      회신하실 수 있습니다"라고 말하는 바로 그 상태(부동의+금액일치)에서
      회신 폼 조건이 배지 조건과 정확히 반대라 폼이 절대 안 뜬다. 서버는
      재회신을 받아 주는데 화면에 입구가 없었다.

      python test_scan_round113_fixes.py
"""
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


APP_SRC = read("app.py")
PORTAL_SRC = read("templates/insurer_portal.html")

print("═" * 72)
print("  스캔 113라운드 회귀 — 변경견적 발주처 확인(insurer_ack) 생애주기 결함 3건")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
ccf_body = _py_fn_body(APP_SRC, "api_co_close_full")
chk('if _insurer_ack_ok(co, b["amount"]):' in ccf_body,
    "★★★ api_co_close_full 이 낙찰 확정 전 이 금액에 대한 진짜 확인인지 가른다")
chk("insurer_ack=NULL, insurer_ack_amount=NULL" in ccf_body,
    "★★★ 진짜 확인이 아니면(대행 통과) 없던 확인을 지어내지 않고 비운다")

iack_body = _py_fn_body(APP_SRC, "api_insurer_co_ack")
chk('if co["status"] in ("수락확정", "최종유찰", "낙찰확정", "철회"):' in iack_body
    and '"code": "CO_CLOSED"' in iack_body,
    "★★★ 발주처 확인 라우트가 종결된 변경건은 막는다")

chk("|| o.insurer_ack === '부동의'" in PORTAL_SRC,
    "★★ 보험사 화면 — 부동의는 금액이 그대로여도 재회신 폼이 다시 열린다")
chk("이전에 <b>부동의</b>로 회신하셨습니다" in PORTAL_SRC,
    "★★ 재회신 폼에 '부동의 재고려' 전용 안내문이 있다(금액변경 안내와 안 섞인다)")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[4] 실행 — 실제 시나리오를 돌린다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round113_")
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
                 "VALUES('r113admin','x','검증','중간관리자')")
    conn.commit()

    admin = A.app.test_client()
    _tok = "r113-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r113admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    def _mk_co(case_no, ack_amount, bid_amount):
        """확인=5,100,000원짜리 CO 를 만들고 실제 낙찰금액(bid_amount)으로 마감 준비."""
        iid = conn.execute(
            "INSERT INTO insurers(name,status) VALUES('R113보험','활성')").lastrowid
        p1 = conn.execute(
            "INSERT INTO partners(name,partner_type,status) VALUES('R113업체',"
            "'시행사','활성')").lastrowid
        cid = conn.execute(
            "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
            f"VALUES('{case_no}','시공중','가드레일','서울',?,0)", (iid,)).lastrowid
        coid = conn.execute(
            "INSERT INTO change_orders(case_id,round,incumbent_partner_id,incumbent_amount,"
            "                          reason,requested_amount,status,combined_amount,"
            "                          insurer_ack,insurer_ack_by,insurer_ack_at,"
            "                          insurer_ack_amount,created_at) "
            "VALUES(?,1,?,1000000,'실사 증액','추가 공사','전체재경매중',?,"
            "       '확인','검증손보(보상팀 김확인)','2026-08-01 10:00:00',?,?)",
            (cid, p1, ack_amount, ack_amount, DB.now())).lastrowid
        aid = conn.execute(
            "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
            "                     bid_count,extend_count,deadline,created_at) "
            "VALUES(?,?,'전체재경매',1,'마감',0,1,0,"
            "       datetime('now','+9 hours','-1 hour'),?)", (cid, coid, DB.now())).lastrowid
        bid = conn.execute(
            "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
            "VALUES(?,?,?,?,10,?)", (aid, p1, "R113업체", bid_amount, DB.now())).lastrowid
        conn.commit()
        return coid, bid

    # ── [2] 낙찰가가 확인 금액과 다르면(대행 통과) — 옛 확인이 안 살아난다 ──
    coid1, bid1 = _mk_co("R113-C1", 5100000, 4800000)
    r1 = admin.post(f"/api/change-orders/{coid1}/close-full", headers=_hdr,
                     json={"bid_id": bid1, "insurer_instruction": "보상팀장 유선 지시 262708"})
    chk(r1.status_code == 200, "STEP 낙찰(대행 통과) 요청이 성공한다",
        (r1.status_code, r1.get_data(as_text=True)[:300]))
    co1 = conn.execute(
        "SELECT insurer_ack, insurer_ack_amount, insurer_ack_by, combined_amount "
        "FROM change_orders WHERE id=?", (coid1,)).fetchone()
    chk(co1["insurer_ack"] is None and co1["insurer_ack_amount"] is None,
        "★★★ 확인한 적 없는 4,800,000원에 '확인' 배지가 안 뜬다"
        "(예전엔 5,100,000원 확인이 그대로 옮겨 붙어 없던 승인이 생겼다)",
        dict(co1))
    chk(co1["combined_amount"] == 4800000, "STEP 계약금액 자체는 정상 반영된다", dict(co1))

    # ── [3] 낙찰가가 확인 금액과 정확히 같으면 — 진짜 확인은 그대로 보존된다 ──
    coid2, bid2 = _mk_co("R113-C2", 4800000, 4800000)
    r2 = admin.post(f"/api/change-orders/{coid2}/close-full", headers=_hdr,
                     json={"bid_id": bid2})
    chk(r2.status_code == 200, "STEP 확인 금액과 낙찰가가 같으면 사유 없이도 낙찰된다",
        (r2.status_code, r2.get_data(as_text=True)[:300]))
    co2 = conn.execute(
        "SELECT insurer_ack, insurer_ack_amount, insurer_ack_by "
        "FROM change_orders WHERE id=?", (coid2,)).fetchone()
    chk(co2["insurer_ack"] == "확인" and co2["insurer_ack_amount"] == 4800000
        and co2["insurer_ack_by"] == "검증손보(보상팀 김확인)",
        "★★ 진짜 확인(같은 금액)은 낙찰 뒤에도 그대로 남는다(과잉삭제 아님)",
        dict(co2))

    # ── [4] 종결된 변경건은 발주처 확인 라우트 자체가 막는다 ──────────────
    insurer_c = A.app.test_client()
    with insurer_c.session_transaction() as isess:
        isess["insurer_id"] = conn.execute(
            "SELECT insurer_id FROM cases c JOIN change_orders o ON o.case_id=c.id "
            "WHERE o.id=?", (coid1,)).fetchone()[0]
        isess["_csrf"] = "r113-insurer-csrf"
    _ihdr = {"X-CSRF-Token": "r113-insurer-csrf"}

    r3 = insurer_c.post(f"/api/insurer/change-orders/{coid1}/ack", headers=_ihdr,
                         json={"ack": True, "note": "뒤늦게 확인"})
    chk(r3.status_code == 409 and r3.get_json().get("code") == "CO_CLOSED",
        "★★★ 이미 낙찰확정된 변경건은 사후 확인·부동의를 못 남긴다"
        "(예전엔 여기 상태가드가 없어 종결 뒤에도 승인 기록을 뒤집을 수 있었다)",
        (r3.status_code, r3.get_json()))
    co1_after = conn.execute(
        "SELECT insurer_ack, insurer_ack_by FROM change_orders WHERE id=?", (coid1,)).fetchone()
    chk(co1_after["insurer_ack"] is None,
        "STEP 막힌 요청이 실제로 기록을 안 바꿨다(F1 이 만든 NULL 상태 유지)",
        dict(co1_after))

    # 진행 중(원업체제안)인 변경건은 여전히 정상적으로 확인할 수 있다 — 과잉차단 아님
    iid3 = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('R113보험2','활성')").lastrowid
    cid3 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
        "VALUES('R113-C3','시공중','가드레일','서울',?,0)", (iid3,)).lastrowid
    coid3 = conn.execute(
        "INSERT INTO change_orders(case_id,round,reason,requested_amount,status,"
        "                          combined_amount,created_at) "
        "VALUES(?,1,'실사 증액','추가 공사','원업체제안',3000000,?)",
        (cid3, DB.now())).lastrowid
    conn.commit()
    with insurer_c.session_transaction() as isess:
        isess["insurer_id"] = iid3
    r4 = insurer_c.post(f"/api/insurer/change-orders/{coid3}/ack", headers=_ihdr,
                         json={"ack": True, "note": "확인함"})
    chk(r4.status_code == 200,
        "STEP 진행 중인 변경건은 여전히 정상적으로 확인할 수 있다(과잉차단 아님)",
        (r4.status_code, r4.get_data(as_text=True)[:200]))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드113 서버측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
