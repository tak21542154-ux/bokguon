# -*- coding: utf-8 -*-
"""수수료(fee) 입금 확인 라우트 — 정산구조 변경(2026-10-18, 토니 결정) 신규 기능.

   전자금융거래법상 PG 등록 리스크를 없애려고 "보험사→복구온→시행사"(복구온이
   전액을 경유)를 "보험사→시행사 직접 지급 + 보험사→복구온 수수료 별도 지급"
   으로 바꿨다. api_settlement_fee_collected()(app.py)가 그 수수료 입금을
   기존 insurer_paid/transfer_status 와 독립적으로 추적한다 — 검증 대상:

   1) review_status='승인' 전에는 거부(선행 관문)
   2) 정상 경로: review 승인된 건은 성공 → fee_collect_status='완료' 기록
   3) 중복 확인은 거부(멱등)
   4) 취소(void_status='취소')된 건은 review 승인 상태여도 거부

   python test_fee_collected.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  수수료(fee) 입금 확인 라우트 — 신규 기능 검증")
print("=" * 72)

_tmpdir = tempfile.mkdtemp(prefix="feecollect_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)


def _seed(conn, tag, review="승인", void=None):
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,bank_name,bank_holder,bank_account_enc) "
        f"VALUES('FC업체{tag}','시행사','활성','국민','FC업체{tag}','enc:1234')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,is_demo) "
        f"VALUES('FC-C{tag}','정산진행','가드레일','서울',?,0)", (pid,)).lastrowid
    sid = conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_id,partner_name,amount,fee,"
        "                        payout,review_status,transfer_status,void_status,created_at) "
        f"VALUES(?,'FC-C{tag}','FC보험',?,'FC업체{tag}',3000000,300000,2700000,"
        "?,'대기',?,?)", (cid, pid, review, void, __import__("db").now())).lastrowid
    return sid


try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','최고관리자')")
    conn.commit()

    admin = A.app.test_client()
    _tok = "fc-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    hdr = {"X-CSRF-Token": _tok}

    print("\n[1] 검수 미승인 건은 거부")
    sid_pending = _seed(conn, "P", review="대기")
    conn.commit()
    r = admin.post(f"/api/settlements/{sid_pending}/fee-collected", headers=hdr, json={})
    chk(r.status_code == 409, "review_status='대기'면 409", (r.status_code, r.get_json()))

    print("\n[2] 정상 경로 — 검수 승인된 건은 성공")
    sid_ok = _seed(conn, "O", review="승인")
    conn.commit()
    r = admin.post(f"/api/settlements/{sid_ok}/fee-collected", headers=hdr,
                    json={"memo": "테스트 확인"})
    chk(r.status_code == 200, "검수 승인 건은 200", (r.status_code, r.get_json()))
    st = conn.execute(
        "SELECT fee_collect_status, fee_collected_by, fee_collected_at FROM settlements WHERE id=?",
        (sid_ok,)).fetchone()
    chk(st["fee_collect_status"] == "완료", "fee_collect_status가 '완료'로 바뀜", dict(st))
    chk(bool(st["fee_collected_by"]) and "admin" in st["fee_collected_by"],
        "fee_collected_by에 처리자가 기록됨", dict(st))
    chk(bool(st["fee_collected_at"]), "fee_collected_at에 시각이 기록됨", dict(st))
    # 기존 상태(insurer_paid/transfer_status)는 전혀 안 건드렸는지 확인 — 독립성 검증
    st2 = conn.execute(
        "SELECT insurer_paid, transfer_status FROM settlements WHERE id=?", (sid_ok,)).fetchone()
    chk(st2["insurer_paid"] == "대기" and st2["transfer_status"] == "대기",
        "★★★★★ 기존 insurer_paid/transfer_status는 안 건드림(독립 컬럼 확인)", dict(st2))

    print("\n[3] 중복 확인은 거부(멱등)")
    r = admin.post(f"/api/settlements/{sid_ok}/fee-collected", headers=hdr, json={})
    chk(r.status_code == 409, "이미 완료된 건 재확인은 409", (r.status_code, r.get_json()))

    print("\n[4] 취소된 건은 검수 승인 상태여도 거부")
    sid_void = _seed(conn, "V", review="승인", void="취소")
    conn.commit()
    r = admin.post(f"/api/settlements/{sid_void}/fee-collected", headers=hdr, json={})
    chk(r.status_code == 409, "취소(void_status='취소') 건은 409", (r.status_code, r.get_json()))

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  결과: {len(PASS)} 통과 / {len(FAIL)} 실패")
print("=" * 72)
if FAIL:
    sys.exit(1)
