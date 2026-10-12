# -*- coding: utf-8 -*-
"""스캔 171라운드 회귀 — 데모 사건 격리가 협력사 사건액션·변경견적 관련
8개 지점에서 전부 빠져 있던 결함.

  partners 표에는 is_demo 컬럼 자체가 없다(insurers 는 있다) — 그래서 데모
  사건이 실제 협력사 계정을 partner_id 로 그대로 빌려 쓸 수 있고, 실측
  (운영DB 읽기전용 조회)으로 실제 이런 사건이 5건 있음을 확인했다. 형제
  라우트(api_partner_bid 등)는 이미 "목록에서 뺐어도 링크·앱 캐시로 그
  화면에 닿을 수 있다"며 int(c["is_demo"] or 0) 로 막는데, 사건상세·사진
  업로드·완료보고·변경견적 생성/수락/보험사확인 6개 라우트와 관리자 대시보드
  배지·목록 2곳은 이 방어가 없었다 — 실제 로그인 계정을 가진 협력사가 데모
  사건 ID로 직접 접근하면 상세를 보고 사진을 올리고 완료보고·증액요청까지
  낼 수 있는 상태였다(정산은 settlements.is_demo 가 이미 막아 실제 지급으로
  이어지진 않는다).

      python test_scan_round171_fixes.py
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
print("  스캔 171라운드 회귀 — 협력사 사건액션·변경견적의 데모 격리 누락(8곳)")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
for fn, marker in (
    ("def api_partner_case_detail(", 'int(c["is_demo"] or 0)'),
    ("def api_partner_upload_photos(", "COALESCE(is_demo,0)=0"),
    ("def api_partner_complete(", "COALESCE(is_demo,0)=0"),
    ("def api_change_order_create(", "COALESCE(is_demo,0)=0"),
    ("def api_co_decision(", 'int(c["is_demo"] or 0)'),
    ("def api_insurer_co_ack(", 'int(co["is_demo"] or 0)'),
):
    i0 = APP_SRC.index(fn)
    i1 = APP_SRC.index("\n@app.", i0 + 1)
    body = APP_SRC[i0:i1]
    chk(marker in body, f"★★★ {fn.split('(')[0][4:]} 이 데모 사건을 막는다")

chk("EXISTS (SELECT 1 FROM cases c WHERE c.id=co.case_id AND COALESCE(c.is_demo,0)=0)" in APP_SRC,
    "★★★ co_active 배지가 change_orders→cases EXISTS 로 데모를 거른다")
i2 = APP_SRC.index("def api_change_orders():")
i3 = APP_SRC.index("\n@app.", i2 + 1)
chk("COALESCE(c.is_demo,0)=0" in APP_SRC[i2:i3],
    "★★★ api_change_orders(관리자 목록) 이 데모를 거른다")

# ============================================================
print("\n[2] 실행 — 실제 협력사 계정이 데모 사건에 배정된 시나리오를 그대로 재현")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round171_")
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
        "VALUES('R171보험사','활성','r171i',?)", (DB.now(),)).lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,login_id,created_at) "
        #  ⚠ partners 는 is_demo 컬럼 자체가 없다 — 실제(비데모) 협력사다.
        "VALUES('R171업체','시공사','활성','가드레일','서울','r171p',?)", (DB.now(),)).lastrowid
    #  실측대로: 데모 사건이 이 "실제" 협력사의 partner_id 를 그대로 빌려 쓴다.
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,partner_id,is_demo,created_at) "
        "VALUES('R171-DEMO','시공중','가드레일','서울',?,?,1,?)", (iid, pid, DB.now())).lastrowid
    coid = conn.execute(
        "INSERT INTO change_orders(case_id,incumbent_partner_id,incumbent_amount,"
        "                          reason,requested_amount,status,created_at) "
        "VALUES(?,?,1000000,'실측재현',1200000,'원업체제안',?)",
        (cid, pid, DB.now())).lastrowid
    #  ⚠ 출동모드 경로(사진업로드의 두 번째 쿼리)는 partner_id 가 아직 NULL 인
    #    별도 시나리오라야 실제로 그 코드를 통과한다 — 위 cid 와는 독립된 사건.
    cid_dispatch = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,partner_id,is_demo,created_at) "
        "VALUES('R171-DEMO-DP','접수','가드레일','서울',?,NULL,1,?)", (iid, DB.now())).lastrowid
    conn.execute(
        "INSERT INTO dispatches(case_id,status,claimed_partner_id,claimed_name,created_at) "
        "VALUES(?,'도착',?,'R171업체',?)", (cid_dispatch, pid, DB.now()))
    conn.commit(); conn.close()

    partner = A.app.test_client()
    ptok = "r171-partner-csrf"
    with partner.session_transaction() as sess:
        sess["partner_id"] = pid; sess["partner_name"] = "R171업체"; sess["_csrf"] = ptok
    phdr = {"X-CSRF-Token": ptok}

    insurer = A.app.test_client()
    itok = "r171-insurer-csrf"
    with insurer.session_transaction() as sess:
        sess["insurer_id"] = iid; sess["insurer_name"] = "R171보험사"; sess["_csrf"] = itok
    ihdr = {"X-CSRF-Token": itok}

    admin = A.app.test_client()
    atok = "r171-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = atok
    ahdr = {"X-CSRF-Token": atok}

    r1 = partner.get(f"/api/partner/cases/{cid}/detail", headers=phdr)
    chk(r1.status_code == 404,
        "★★★ 사건상세 — 실 협력사가 데모 사건 상세를 못 본다(고치기 전엔 200 이었다)",
        r1.status_code)

    r2 = partner.post(f"/api/partner/cases/{cid}/photos", data={}, headers=phdr)
    chk(r2.status_code == 404,
        "★★★ 사진업로드(주경로) — 데모 사건에는 못 올린다(고치기 전엔 게이트를 통과했다)",
        r2.status_code)

    #  출동모드 경로 — partner_id 가 아직 NULL 이고 claimed_partner_id 로만 걸리는
    #  별도 분기(코드상 두 번째 쿼리)를 정확히 통과시켜 그쪽 is_demo 도 검증한다.
    r2b = partner.post(f"/api/partner/cases/{cid_dispatch}/photos", data={}, headers=phdr)
    chk(r2b.status_code == 404,
        "★★★ 사진업로드(출동모드) — 데모 사건에는 못 올린다(고치기 전엔 게이트를 통과했다)",
        r2b.status_code)

    r3 = partner.post(f"/api/partner/cases/{cid}/complete", headers=phdr)
    chk(r3.status_code == 404,
        "★★★ 완료보고 — 데모 사건은 완료보고 대상이 아니다(고치기 전엔 통과했다)",
        r3.status_code)

    r4 = partner.post(f"/api/cases/{cid}/change-order",
                       json={"reason": "실측재현 사유입니다", "requested_amount": 500000},
                       headers=phdr)
    chk(r4.status_code == 404,
        "★★★ 변경견적 생성 — 데모 사건에는 증액 요청을 못 낸다(고치기 전엔 통과했다)",
        r4.status_code)

    r5 = partner.post(f"/api/change-orders/{coid}/decision", json={"accept": True}, headers=phdr)
    chk(r5.status_code == 403,
        "★★★ 변경견적 수락 — 데모 변경건은 수락할 수 없다(고치기 전엔 통과했다)",
        r5.status_code)

    r6 = insurer.post(f"/api/insurer/change-orders/{coid}/ack", json={"ack": True}, headers=ihdr)
    chk(r6.status_code == 404,
        "★★★ 보험사 증액확인 — 데모 변경건은 확인할 수 없다(고치기 전엔 통과했다)",
        r6.status_code)

    r7 = admin.get("/api/stats", headers=ahdr)
    chk(r7.status_code == 200 and r7.get_json().get("co_active") == 0,
        "★★★ 관리자 대시보드 co_active 배지가 데모 변경건을 안 센다"
        "(고치기 전엔 1로 잡혔다)", r7.get_json().get("co_active"))

    r8 = admin.get("/api/change-orders", headers=ahdr)
    ids = [x["id"] for x in r8.get_json()]
    chk(r8.status_code == 200 and coid not in ids,
        "★★★ 관리자 변경견적 목록이 데모 변경건을 안 보여준다"
        "(고치기 전엔 목록에 나왔다)", (r8.status_code, ids))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드171 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
