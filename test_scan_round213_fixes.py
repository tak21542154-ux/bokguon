# -*- coding: utf-8 -*-
"""스캔 213라운드 회귀 — "한 함수/한 묶음 안 형제 쿼리 대조" 로 찾은 세 구멍.

  (a) api_insurer_dashboard() 의 "진행중 사건"(kpi.active)이 status<>'완료'
      만 써서, 보험사가 취소하거나 미수선종결로 닫은 사건이 자기 포털의
      진행중 건수에 영원히 남았다. CASE_OPEN_SQL(완료·취소·미수선종결을
      전부 제외) 자신의 정의 주석이 정확히 이 실수를 경고하는데, 관리자
      콘솔은 이미 그걸 쓰고 보험사 포털만 옛 공식이었다.

  (b) sweep_approval_overdue() 의 "최장 N일" 계산이 중지된 보험사 건까지
      포함한다. 형제(_sweep_award_approval, 137라운드에서 이미 고침)는
      활성 보험사만 걸러 계산하는데, 원조인 이 함수만 못 받았다 — 대상이
      오래된 순 정렬이라 최장 대기 건이 하필 중지 보험사 것이면, 실제
      발송분과 무관한 일수가 "발송했습니다" 문장에 붙는다.

  (c) TODAY_WAITING 의 "업체가 지급을 기다립니다" 항목만 데모 필터가
      없었다. 같은 목록의 형제(TODAY_QUEUE) 항목들과 그 목록 위 주석이
      "화면(#settle)과 같은 모집단을 세야 한다"고 이미 명시했는데 이
      항목만 못 받았다.

  셋 다 현재 운영 데이터로는 영향 0건(취소/미수선종결 사건 없음·전 보험사
  활성·해당 조건 만족 데모 정산 없음)이지만 코드 자체는 확정적으로
  틀려 있었다 — 정상적인 운영 과정에서 바로 재현되는 잠재 결함이다.

      python test_scan_round213_fixes.py
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
print("  스캔 213라운드 회귀 — 보험사포털KPI·독촉스윕 문구·오늘할일 데모누출 3건")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_insurer_dashboard():")
i1 = APP_SRC.index("\ndef ", i0 + 1)
ins_body = APP_SRC[i0:i1]
chk("SUM(CASE WHEN {CASE_OPEN_SQL} THEN 1 ELSE 0 END) active" in ins_body,
    "★★★★★ (a) 보험사 포털 KPI가 CASE_OPEN_SQL(완료·취소·미수선종결 제외)을 쓴다")

i2 = APP_SRC.index("def sweep_approval_overdue(conn):")
i3 = APP_SRC.index("\ndef ", i2 + 1)
sao_body = APP_SRC[i2:i3]
chk('oldest = max((t.get("days") or 0) for t in targets\n                         if (t.get("insurer_status") or "활성") == "활성")'
    in sao_body,
    "★★★★★ (b) 완료승인독촉의 '최장 N일'이 활성 보험사 대상만으로 계산된다")

i4 = APP_SRC.index("TODAY_WAITING = [")
i5 = APP_SRC.index("\nTODAY_AGING = [", i4)
waiting_body = APP_SRC[i4:i5]
chk("업체가 지급을 기다립니다" in waiting_body and "COALESCE(is_demo,0)=0" in waiting_body.split(
    "업체가 지급을 기다립니다", 1)[1].split("),", 1)[0],
    "★★★★ (c) '업체가 지급을 기다립니다' 항목이 데모 정산을 제외한다")

# ============================================================
print("\n[2] 실행 — 실제 서버(Flask test_client)·직접 함수호출로 검증")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round213_")
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
    now = DB.now()

    # ── (a) 보험사 포털 진행중 건수 ──────────────────────────────
    iid_a = conn.execute(
        "INSERT INTO insurers(name,login_id,password_hash,status) "
        "VALUES('R213보험A','r213insa','x','활성')").lastrowid
    conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo,created_at) "
        "VALUES('R213-OPEN','접수','유리','서울',?,0,?)", (iid_a, now))
    conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo,created_at) "
        "VALUES('R213-CANCEL','취소','유리','서울',?,0,?)", (iid_a, now))
    conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo,created_at) "
        "VALUES('R213-NOREPAIR','미수선종결','유리','서울',?,0,?)", (iid_a, now))
    conn.commit()

    insurer_c = A.app.test_client()
    with insurer_c.session_transaction() as sess:
        sess["insurer_id"] = iid_a; sess["insurer_name"] = "R213보험A"
    r_ins = insurer_c.get("/api/insurer/dashboard")
    chk(r_ins.status_code == 200, "STEP /api/insurer/dashboard 가 200 이다", r_ins.status_code)
    j_ins = r_ins.get_json()
    active_n = (j_ins.get("kpi") or {}).get("active")
    chk(active_n == 1,
        "★★★★★ 핵심 — 취소 1건·미수선종결 1건·접수 1건 중 '진행중'은 1건만 "
        "잡힌다(고치기 전엔 3건 전부 진행중으로 잡혔다)", (active_n, j_ins.get("kpi")))

    # ── (b) 완료승인독촉 스윕의 '최장 N일' ──────────────────────
    iid_active = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('R213보험B(활성)','활성')").lastrowid
    iid_suspended = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('R213보험C(중지)','중지')").lastrowid
    cid_active = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo,created_at) "
        "VALUES('R213-SETL-A','검수대기','유리','서울',?,0,?)", (iid_active, now)).lastrowid
    cid_susp = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo,created_at) "
        "VALUES('R213-SETL-B','검수대기','유리','서울',?,0,?)", (iid_suspended, now)).lastrowid
    #  중지 보험사 건을 더 오래된 것으로 심는다 — ORDER BY created_at ASC 라
    #  targets[0](=현재 결함의 max() 가 잡는 자리)이 되게.
    conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,insurer_id,partner_name,amount,fee,"
        "                        payout,transfer_status,insurer_approved,is_demo,created_at) "
        "VALUES(?,?,?,?,?,1000000,100000,900000,'대기',0,0,"
        "       datetime('now','+9 hours','-10 days'))",
        (cid_susp, "R213-SETL-B", "R213보험C(중지)", iid_suspended, "R213업체"))
    conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,insurer_id,partner_name,amount,fee,"
        "                        payout,transfer_status,insurer_approved,is_demo,created_at) "
        "VALUES(?,?,?,?,?,1000000,100000,900000,'대기',0,0,"
        "       datetime('now','+9 hours','-5 days'))",
        (cid_active, "R213-SETL-A", "R213보험B(활성)", iid_active, "R213업체"))
    conn.commit()

    out = A.sweep_approval_overdue(conn)
    chk(out.get("sent") == 1 and out.get("insurer_suspended") == 1,
        "★ (사전조건) 활성 보험사 1건 발송·중지 보험사 1건은 운영팀 알림으로만",
        out)
    admin_notice = conn.execute(
        "SELECT message FROM notifications WHERE ntype='완료승인독촉' "
        "  AND audience_type='admin' ORDER BY id DESC LIMIT 1").fetchone()
    chk(admin_notice is not None and "5일" in admin_notice["message"]
        and "10일" not in admin_notice["message"],
        "★★★★★ 핵심 — 운영팀 알림의 '최장 N일'이 실제 발송된 활성 보험사 건"
        "(5일)을 가리킨다(고치기 전엔 발송도 안 된 중지 보험사 건의 10일이 "
        "찍혔다)", dict(admin_notice) if admin_notice else None)

    # ── (c) 오늘 할 일 — 업체가 지급을 기다립니다 ──────────────
    cid_pay1 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo,created_at) "
        "VALUES('R213-PAY-DEMO','완료','유리','서울',1,?)", (now,)).lastrowid
    cid_pay2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo,created_at) "
        "VALUES('R213-PAY-REAL','완료','유리','서울',0,?)", (now,)).lastrowid
    conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_name,amount,fee,payout,"
        "                        transfer_status,review_status,is_demo,created_at) "
        "VALUES(?,?,?,?,1000000,100000,900000,'대기','승인',1,?)",
        (cid_pay1, "R213-PAY-DEMO", "R213보험A", "R213업체", now))
    conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_name,amount,fee,payout,"
        "                        transfer_status,review_status,is_demo,created_at) "
        "VALUES(?,?,?,?,1000000,100000,900000,'대기','승인',0,?)",
        (cid_pay2, "R213-PAY-REAL", "R213보험A", "R213업체", now))
    conn.commit()

    admin_c = A.app.test_client()
    with admin_c.session_transaction() as sess:
        sess["admin"] = "r213admin"; sess["admin_role"] = "최고관리자"
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r213admin','x','검증','최고관리자')")
    conn.commit()
    r_today = admin_c.get("/api/ops-today")
    chk(r_today.status_code == 200, "STEP /api/ops-today 가 200 이다", r_today.status_code)
    j_today = r_today.get_json()
    waiting_group = next((g for g in j_today.get("groups", []) if g.get("key") == "waiting"), None)
    pay_item = next((i for i in (waiting_group or {}).get("items", [])
                     if i.get("label") == "업체가 지급을 기다립니다"), None)
    chk(pay_item is not None and pay_item.get("n") == 1,
        "★★★★ 핵심 — 데모 1건·실제 1건 중 '업체가 지급을 기다립니다' 는 1건만 "
        "잡힌다(고치기 전엔 데모까지 세어 2건이었다)", pay_item)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드213 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
