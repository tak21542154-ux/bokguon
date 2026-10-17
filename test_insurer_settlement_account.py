# -*- coding: utf-8 -*-
"""보험사 대시보드 — 시행사 계좌번호 노출 (정산구조 변경, 2026-10-18) 신규 기능 검증.

   보험사가 공사대금을 시행사에게 직접 송금해야 하므로, api_insurer_dashboard()가
   이제 settlements 행마다 partner_bank_name/holder/account(복호화된 전체 번호)를
   붙여 돌려준다. 검증 대상:

   1) 정상 경로 — 자기 정산 건의 계좌가 올바르게 복호화되어 내려온다
   2) IDOR — 다른 보험사 계정으로는 그 계좌 자체가 안 보인다(정산 행 자체가 안 보임)
   3) 계좌 미등록 시 None으로 내려오지, 깨지지 않는다

   python test_insurer_settlement_account.py
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
print("  보험사 대시보드 — 시행사 계좌번호 노출 검증")
print("=" * 72)

_tmpdir = tempfile.mkdtemp(prefix="insacct_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A
    import crypto_util as CRYPTO

    conn = DB.get_db()
    iid1 = conn.execute(
        "INSERT INTO insurers(name,org_type,status,login_id,password_hash) "
        "VALUES('IA보험','손해보험사','활성','ia','x')").lastrowid
    iid2 = conn.execute(
        "INSERT INTO insurers(name,org_type,status,login_id,password_hash) "
        "VALUES('IB보험','손해보험사','활성','ib','x')").lastrowid
    pid_ok = conn.execute(
        "INSERT INTO partners(name,partner_type,status,bank_name,bank_holder,bank_account_enc) "
        f"VALUES('계좌있음시행사','시행사','활성','국민','홍길동',?)",
        (CRYPTO.encrypt("110-123-456789"),)).lastrowid
    pid_noacct = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('계좌없음시행사','시행사','활성')").lastrowid
    cid1 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,insurer_id,insurer,is_demo) "
        f"VALUES('IA-C1','정산진행','가드레일','서울',?,?,'IA보험',0)", (pid_ok, iid1)).lastrowid
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,insurer_id,insurer,is_demo) "
        f"VALUES('IA-C2','정산진행','가드레일','서울',?,?,'IA보험',0)", (pid_noacct, iid1)).lastrowid
    conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,insurer_id,partner_id,partner_name,"
        "                        amount,fee,payout,insurer_approved,created_at) "
        f"VALUES(?,'IA-C1','IA보험',?,?,'계좌있음시행사',3000000,300000,2700000,1,?)",
        (cid1, iid1, pid_ok, DB.now()))
    conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,insurer_id,partner_id,partner_name,"
        "                        amount,fee,payout,insurer_approved,created_at) "
        f"VALUES(?,'IA-C2','IA보험',?,?,'계좌없음시행사',1000000,100000,900000,1,?)",
        (cid2, iid1, pid_noacct, DB.now()))
    conn.commit()

    ca = A.app.test_client()
    with ca.session_transaction() as sess:
        sess["insurer"] = "ia"; sess["insurer_id"] = iid1; sess["insurer_name"] = "IA보험"

    print("\n[1] 정상 경로 — 내 정산 건의 계좌가 복호화되어 내려온다")
    r = ca.get("/api/insurer/dashboard")
    chk(r.status_code == 200, "200 응답", r.status_code)
    d = r.get_json()
    s1 = next((s for s in d["settlements"] if s["case_no"] == "IA-C1"), None)
    chk(s1 is not None, "IA-C1 정산 행이 보인다")
    if s1:
        chk(s1.get("partner_bank_account") == "110-123-456789",
            "★★★★★ 계좌번호가 올바르게 복호화되어 내려온다", s1.get("partner_bank_account"))
        chk(s1.get("partner_bank_name") == "국민", "은행명도 함께 내려온다", s1.get("partner_bank_name"))
        chk(s1.get("partner_bank_holder") == "홍길동", "예금주도 함께 내려온다", s1.get("partner_bank_holder"))

    print("\n[2] 계좌 미등록 시행사는 None으로 내려오지, 서버가 죽지 않는다")
    s2 = next((s for s in d["settlements"] if s["case_no"] == "IA-C2"), None)
    chk(s2 is not None, "IA-C2 정산 행이 보인다")
    if s2:
        chk(s2.get("partner_bank_account") is None,
            "계좌 미등록 건은 partner_bank_account가 None", s2.get("partner_bank_account"))

    print("\n[3] IDOR — 다른 보험사(IB)는 IA의 정산·계좌를 전혀 못 본다")
    cb = A.app.test_client()
    with cb.session_transaction() as sess:
        sess["insurer"] = "ib"; sess["insurer_id"] = iid2; sess["insurer_name"] = "IB보험"
    rb = cb.get("/api/insurer/dashboard")
    chk(rb.status_code == 200, "IB도 200 (자기 대시보드는 열림)")
    db_ = rb.get_json()
    leaked = [s for s in db_["settlements"] if s["case_no"] in ("IA-C1", "IA-C2")]
    chk(len(leaked) == 0,
        "★★★★★ IB 응답에 IA의 정산 건이 전혀 없다(계좌 유출 경로 자체가 없음)", leaked)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  결과: {len(PASS)} 통과 / {len(FAIL)} 실패")
print("=" * 72)
if FAIL:
    sys.exit(1)
