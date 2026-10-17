# -*- coding: utf-8 -*-
"""정산 요약 KPI(fee_paid/fee_rate_avg) 집계 기준 — 정산구조 변경(2026-10-18) 수정.

   fee_paid(수수료 수납액)·fee_rate_avg(평균 수수료율)가 예전엔 transfer_status=
   '이체완료'(시행사가 지급받았는지)를 기준으로 삼았다 — 수수료가 복구온이
   payout 이체 시 자동 공제하던 몫이었을 때는 맞았지만, 지금은 시행사가 수수료를
   복구온에 **별도로** 납부하므로(fee_collect_status), 지급은 됐는데 수수료는
   아직 안 낸 건이 "수납 완료"로 잘못 집계될 수 있었다. 검증:

   1) transfer_status='이체완료' 지만 fee_collect_status≠'완료'인 건은
      fee_paid에 안 잡힌다(옛 코드였다면 잡혔을 상황)
   2) fee_collect_status='완료'면 transfer_status 와 무관하게 fee_paid에 잡힌다
   3) fee_rate_avg 분모(fee_amt_base)도 같은 모집단(fee_collect_status='완료')
      기준이라 비율이 수학적으로 맞다

   python test_fee_summary_basis.py
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
print("  정산 요약 KPI — 수수료 수납 집계 기준 검증")
print("=" * 72)

_tmpdir = tempfile.mkdtemp(prefix="feesum_")
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

    def _seed(tag, transfer, fee_collect, amount=3000000, fee=300000):
        pid = conn.execute(
            "INSERT INTO partners(name,partner_type,status) VALUES(?,'시행사','활성')",
            (f"FS업체{tag}",)).lastrowid
        cid = conn.execute(
            "INSERT INTO cases(case_no,status,category,region,partner_id,is_demo) "
            f"VALUES('FS-C{tag}','정산진행','가드레일','서울',?,0)", (pid,)).lastrowid
        conn.execute(
            "INSERT INTO settlements(case_id,case_no,insurer,partner_id,partner_name,amount,fee,"
            "                        payout,transfer_status,fee_collect_status,created_at) "
            f"VALUES(?,'FS-C{tag}','FS보험',?,'FS업체{tag}',{amount},{fee},{amount-fee},"
            "?,?,?)", (cid, pid, transfer, fee_collect, DB.now()))
        return cid

    # 지급은 됐지만 수수료는 아직 안 낸 건 — 이게 이번 수정의 핵심 케이스
    _seed("A", transfer="이체완료", fee_collect="대기", amount=3000000, fee=300000)
    # 수수료는 냈지만(독립 사건) 지급 상태는 아직 대기인 건
    _seed("B", transfer="대기", fee_collect="완료", amount=2000000, fee=200000)
    conn.commit()

    admin = A.app.test_client()
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"

    r = admin.get("/api/settlements/summary")
    chk(r.status_code == 200, "200 응답", r.status_code)
    d = r.get_json()

    print("\n[1] 지급완료·수수료미납 건은 fee_paid에 안 잡힌다")
    chk(d["fee_paid"] == 200000,
        "★★★★★ fee_paid = 200,000원(B건만) — A건(지급완료·수수료미납)은 제외됨",
        d.get("fee_paid"))

    print("\n[2] fee_rate_avg 분모도 같은 모집단 기준(수학적으로 정합)")
    # fee_amt_base = B건의 amount(2,000,000) 하나뿐 → 200,000/2,000,000 = 10.0%
    chk(d["fee_rate_avg"] == 10.0,
        "★★★★★ fee_rate_avg = 10.0%(B건 fee/amount 기준, A건 섞여 왜곡 안 됨)",
        d.get("fee_rate_avg"))

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  결과: {len(PASS)} 통과 / {len(FAIL)} 실패")
print("=" * 72)
if FAIL:
    sys.exit(1)
