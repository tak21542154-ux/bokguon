# -*- coding: utf-8 -*-
"""스캔 162라운드 회귀 — 발주처 사건취소가 '도착' 상태 출동수배를 안 닫던 결함.

  close_live_dispatches() 는 "이미 다른 길로 간 사건에 협력사가 계속
  불려간다"는 결함(라운드117)을 고치며 '도착' 상태까지 닫도록 만들어졌고,
  2차 경매 개시 경로는 이 함수로 옮겨졌다. 그런데 이 함수가 원래 뽑혀
  나온 자리인 api_insurer_case_cancel() 자신은 옛 인라인 코드(모집중·
  수배됨만 닫는다)를 그대로 갖고 있었다 — 함수로 뽑아 고친 뒤 원래 자리를
  그 함수로 바꿔치기하는 마지막 단계가 빠진 것이다.

  그 결과 발주처가 사건을 취소해도, 이미 현장에 도착한 협력사의 dispatch
  행은 '도착'으로 영원히 남아 사진 업로드 게이트(api_partner_upload_photos
  의 출동모드 허용조건)가 계속 열려 있었다 — 취소된 사건에 사진을 계속
  올릴 수 있었다는 뜻이다.

      python test_scan_round162_fixes.py
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
print("  스캔 162라운드 회귀 — 사건취소가 '도착' 수배를 안 닫던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_insurer_case_cancel(")
i1 = APP_SRC.index("\n@app.", i0 + 1)
body = APP_SRC[i0:i1]
chk("close_live_dispatches(" in body,
    "★★★ api_insurer_case_cancel 이 이제 close_live_dispatches() 를 쓴다")
chk("status IN ('모집중','수배됨')" not in body,
    "★★★ '도착'을 빠뜨리던 옛 인라인 상태목록이 사라졌다")

# ============================================================
print("\n[2] 실행 — 취소가 '도착' 수배를 실제로 닫고, 사진업로드 게이트도 닫히는가")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round162_")
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
    iid = conn.execute(
        "INSERT INTO insurers(name,status,login_id,created_at) "
        "VALUES('R162보험사','활성','r162i',?)", (DB.now(),)).lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,login_id,created_at) "
        "VALUES('R162업체','시공사','활성','가드레일','서울','r162p',?)", (DB.now(),)).lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,category,region,created_at) "
        "VALUES('R162-CANCEL','접수','R162보험사',?,?,?,?)",
        (iid, "가드레일", "서울", DB.now())).lastrowid
    did = conn.execute(
        "INSERT INTO dispatches(case_id,status,claimed_partner_id,claimed_name,created_at) "
        "VALUES(?,?,?,?,?)", (cid, "도착", pid, "R162업체", DB.now())).lastrowid
    conn.commit(); conn.close()

    insurer = A.app.test_client()
    itok = "r162-insurer-csrf"
    with insurer.session_transaction() as sess:
        sess["insurer_id"] = iid; sess["insurer_name"] = "R162보험사"; sess["_csrf"] = itok
    r1 = insurer.post(f"/api/insurer/cases/{cid}/cancel",
                       json={"reason": "테스트를 위한 취소 사유입니다"},
                       headers={"X-CSRF-Token": itok})
    chk(r1.status_code == 200 and r1.get_json().get("ok"),
        "STEP 사건취소 요청이 200/ok 다", (r1.status_code, r1.get_json()))

    conn = DB.get_db()
    crow = dict(conn.execute("SELECT status FROM cases WHERE id=?", (cid,)).fetchone())
    drow = dict(conn.execute("SELECT status, fail_reason FROM dispatches WHERE id=?", (did,)).fetchone())
    conn.close()
    chk(crow["status"] == "취소", "★ (사전조건) 사건 자체는 취소됐다", crow)
    chk(drow["status"] == "취소",
        "★★★ '도착' 이었던 dispatch 행도 함께 취소된다"
        "(고치기 전엔 '도착'으로 영원히 남았다)", drow)

    #  ★★★ 실제 사진 업로드 게이트로 직접 확인 — 취소된 사건에 사진을 못 올려야 한다
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(buf, format="JPEG")
    buf.seek(0)

    partner = A.app.test_client()
    ptok = "r162-partner-csrf"
    with partner.session_transaction() as sess:
        sess["partner_id"] = pid; sess["partner_name"] = "R162업체"; sess["_csrf"] = ptok
    r2 = partner.post(f"/api/partner/cases/{cid}/photos",
                       data={"photos": (buf, "site.jpg")},
                       content_type="multipart/form-data",
                       headers={"X-CSRF-Token": ptok})
    chk(r2.status_code == 404,
        "★★★ 취소된 사건에는 이제 사진을 못 올린다(고치기 전엔 200 으로 실제 저장됐다)",
        (r2.status_code, r2.get_json() if r2.is_json else r2.data[:200]))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드162 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
