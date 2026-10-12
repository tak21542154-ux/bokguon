# -*- coding: utf-8 -*-
"""스캔 47라운드 회귀 — LIMIT 없는 목록 쿼리 5곳.

  조사 에이전트가 실측(응답 크기 60~74배, 응답시간 2.6~4.8배, 1,200~1,500행
  기준)으로 증명한 결함 5곳: 보험사 대시보드 사건·정산, 협력사 대시보드
  정산·내 사건, 어드민 사진검수 큐. 전부 "목록엔 LIMIT, 합계는 SQL 집계로"
  같은 원칙으로 고쳤다 — 이 회귀는 **LIMIT 이 실제로 걸리는지**와 **집계값이
  잘린 목록이 아니라 전체를 정확히 반영하는지**를 함께 본다(캡을 씌우다가
  숫자가 틀려지면 더 나쁘다).

      python test_scan_round47_fixes.py
"""
import io
import itertools
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []
_seq = itertools.count()


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("═" * 72)
print("  스캔 47라운드 회귀 — LIMIT 없는 목록 쿼리 5곳")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 배선이 실제로 있는가")
# ──────────────────────────────────────────────────────────────
chk("ORDER BY c.id DESC LIMIT 200" in APP_SRC, "① 보험사 대시보드 사건 목록에 LIMIT 200")
chk('_case_kpi = one(conn.execute(' in APP_SRC, "① 사건 합계가 별도 SQL 집계로 바뀌었다")
chk("ORDER BY id DESC LIMIT 200" in APP_SRC, "② 정산 목록에 LIMIT 200(공용 문구, 협력사와 공유)")
chk('_sett_kpi = one(conn.execute(' in APP_SRC, "② 보험사 정산 합계가 SQL SUM 으로 바뀌었다")
chk('_payout_kpi = one(conn.execute(' in APP_SRC, "③ 협력사 정산 합계가 SQL SUM 으로 바뀌었다")
chk("LIMIT 100" in APP_SRC and "my_cases = rows(conn.execute(" in APP_SRC,
    "④ 협력사 내 사건 목록에 LIMIT 100")
chk("_having = \"\" if _w else (" in APP_SRC,
    "⑤ 사진검수 큐 — 검색 없을 때만 처리완료 사건을 HAVING 으로 뺀다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — LIMIT 이 실제로 걸리고, 집계는 전체를 정확히 반영하는가")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="cap47_")
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
                 "VALUES('admin47','x','검증','최고관리자')")
    iid = conn.execute("INSERT INTO insurers(name,status) VALUES('검증보험47','활성')").lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,jobs_done) "
        "VALUES('검증업체47','시공사','활성',0)").lastrowid
    conn.commit()
    conn.close()

    import app as A
    client = A.app.test_client()

    # ── ①② 보험사 대시보드 — 사건 250건(200 초과), 정산 250건 ──
    with client.session_transaction() as sess:
        sess.clear(); sess["insurer_id"] = iid; sess["insurer_name"] = "검증보험47"
    client.get("/api/insurer/dashboard")   # _sweep_if_due() 1회성 비용 예열

    conn = DB.get_db()
    N_CASE = 250
    for i in range(N_CASE):
        status = "승인대기" if i < 30 else "입찰중"   # 활성판정용 소량 섞기
        conn.execute(
            "INSERT INTO cases(case_no,status,insurer_id,est_price) VALUES(?,?,?,?)",
            (f"47I-{next(_seq)}", status, iid, 1000000))
    N_SETT = 250
    for i in range(N_SETT):
        paid = "입금완료" if i % 2 == 0 else "대기"
        conn.execute(
            "INSERT INTO settlements(case_no,insurer_id,insurer,partner_name,amount,"
            "insurer_paid,void_status) VALUES(?,?,?,?,?,?,?)",
            (f"47S-{next(_seq)}", iid, "검증보험47", "검증업체47", 1000000, paid, ""))
    conn.commit(); conn.close()

    r = client.get("/api/insurer/dashboard")
    d = r.get_json()
    chk(len(d["cases"]) <= 200, "① 사건 목록이 200건 이하로 잘렸다", len(d["cases"]))
    chk(d["kpi"]["total"] == N_CASE, "★★★ ① 총 사건수는 잘리지 않고 250 정확히 나온다",
        (d["kpi"]["total"], N_CASE))
    chk(d["kpi"]["approve_wait"] == 30, "★★★ ① 승인대기 수도 SQL 집계라 정확하다(30)",
        d["kpi"]["approve_wait"])
    chk(len(d["settlements"]) <= 200, "② 정산 목록이 200건 이하로 잘렸다", len(d["settlements"]))
    chk(d["kpi"]["paid"] == 125 * 1000000,
        "★★★ ② 입금완료 합계는 잘리지 않고 전체(125건×100만)를 정확히 반영한다",
        (d["kpi"]["paid"], 125 * 1000000))
    chk(d["kpi"]["pending_pay"] == 125 * 1000000,
        "★★★ ② 입금대기 합계도 정확하다", d["kpi"]["pending_pay"])

    # ── ③④ 협력사 대시보드 — 정산 250건 + 사건 120건(시공중 5 + 완료 115) ──
    with client.session_transaction() as sess:
        sess.clear(); sess["partner_id"] = pid; sess["partner_name"] = "검증업체47"

    conn = DB.get_db()
    for i in range(250):
        xfer = "이체완료" if i % 2 == 0 else "대기"
        conn.execute(
            "INSERT INTO settlements(case_no,partner_id,partner_name,amount,payout,"
            "transfer_status,void_status,created_at,insurer_approved,review_status) "
            "VALUES(?,?,?,?,?,?,?,?,1,'완료')",
            (f"47PS-{next(_seq)}", pid, "검증업체47", 1000000, 900000, xfer, "",
             "2026-08-01 00:00:00"))
    ACTIVE_N = 5
    for i in range(ACTIVE_N):
        conn.execute(
            "INSERT INTO cases(case_no,status,insurer_id,partner_id) VALUES(?,?,?,?)",
            (f"47PC-active-{next(_seq)}", "시공중", iid, pid))
    for i in range(115):
        conn.execute(
            "INSERT INTO cases(case_no,status,insurer_id,partner_id,completed_at) "
            "VALUES(?,?,?,?,?)",
            (f"47PC-done-{next(_seq)}", "완료", iid, pid, "2026-01-01 00:00:00"))
    conn.commit(); conn.close()

    r2 = client.get("/api/partner/dashboard")
    d2 = r2.get_json()
    chk(len(d2["settlements"]) <= 200, "③ 정산 목록이 200건 이하로 잘렸다", len(d2["settlements"]))
    chk(d2["payout_paid"] == 125 * 900000,
        "★★★ ③ 이체완료 합계는 잘리지 않고 전체(125건×90만)를 정확히 반영한다",
        (d2["payout_paid"], 125 * 900000))
    chk(d2["payout_pending"] == 125 * 900000, "★★★ ③ 이체대기 합계도 정확하다",
        d2["payout_pending"])
    my_cases = d2["my_cases"]
    chk(len(my_cases) <= 100, "④ 내 사건 목록이 100건 이하로 잘렸다", len(my_cases))
    active_shown = [mc for mc in my_cases if mc["status"] == "시공중"]
    chk(len(active_shown) == ACTIVE_N,
        "★★★ ④ 시공중(활성) 사건 5건은 100건 캡에도 전부 살아남는다(정렬이 먼저 보장)",
        len(active_shown))

    # ── ⑤ 어드민 사진검수 큐 — 처리완료 사건은 기본 화면에서 빠지는가 ──
    with client.session_transaction() as sess:
        sess.clear(); sess["admin"] = "admin47"; sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"
    conn = DB.get_db()
    cid_done = conn.execute(
        "INSERT INTO cases(case_no,status,insurer_id) VALUES(?,?,?)",
        ("47PHOTO-DONE", "완료", iid)).lastrowid
    conn.execute("INSERT INTO photos(case_id,rel_path,review_status) VALUES(?,?,?)",
                 (cid_done, "47/done.jpg", "승인"))   # 대기·반려 0건 = 처리완료
    cid_pending = conn.execute(
        "INSERT INTO cases(case_no,status,insurer_id) VALUES(?,?,?)",
        ("47PHOTO-PENDING", "접수", iid)).lastrowid
    conn.execute("INSERT INTO photos(case_id,rel_path,review_status) VALUES(?,?,?)",
                 (cid_pending, "47/pending.jpg", "대기"))
    conn.commit(); conn.close()

    r3 = client.get("/api/photos")
    items = r3.get_json()["items"]
    ids_default = {x["case_id"] for x in items}
    chk(cid_pending in ids_default, "⑤ 대기 중인 사건은 기본 화면에 보인다", ids_default)
    chk(cid_done not in ids_default,
        "★★★ ⑤ 처리완료(대기0·반려0) 사건은 기본 화면에서 빠진다", ids_default)

    r4 = client.get("/api/photos?q=47PHOTO-DONE")
    items4 = r4.get_json()["items"]
    ids_search = {x["case_id"] for x in items4}
    chk(cid_done in ids_search,
        "★★★ ⑤ 검색으로는 처리완료 사건도 그대로 찾아진다(과잉차단 아님)", ids_search)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ LIMIT·집계 실측", f"{type(e).__name__} {e}")
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
