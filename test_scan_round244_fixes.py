# -*- coding: utf-8 -*-
"""스캔 244라운드 회귀 — api_partner_defect_resolve() 가 재시도 방어 없이
   '확인중' 자신도 허용 소스 상태에 포함시켜 중복 알림·감사로그를 쌓던 결함
   (admin.js 하자화면 Agent 병렬조사가 부수적으로 발견한 인접 결함 — 이
   라우트 자체는 partner_portal.html 이 부른다).

  DEFECT_OPEN_STATES(접수·확인중·재시공배정)를 그대로 허용 소스로 쓰면 그
  목표 상태인 '확인중' 자신도 포함된다 — 그런데 DEFECT_NEXT 상 '확인중'에서
  협력사가 다시 완료보고를 낼 정상 경로는 없다(다음은 관리자가 재시공배정·
  완료·반려 중 하나로 넘긴다). 이 조건이 열려 있어서 같은 요청을 재시도하면
  (방금 그 요청으로 이미 확인중이 된 건도) rowcount>0 으로 또 통과해
  재시공보고 알림·감사로그가 매번 중복으로 쌓였다 — 형제(api_defect_create,
  228라운드)가 이미 고친 것과 같은 재시도 결함 계열.

  '확인중'을 뺀 진짜 시작 상태(접수·재시공배정)만 허용하고, 이미 확인중이면
  진짜 오류(완료·반려로 닫힘)와 구분해 조용히 성공(duplicate)으로 돌린다.

      python test_scan_round244_fixes.py
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
print("  스캔 244라운드 회귀 — 하자 완료보고의 재시도 중복 알림·로그")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_partner_defect_resolve(")
i1 = APP_SRC.index("\n@app.", i0 + 1)
body = APP_SRC[i0:i1]
chk('_resolve_from = tuple(s for s in DEFECT_OPEN_STATES if s != "확인중")' in body,
    "★★★★ 허용 시작 상태에서 목표 상태('확인중') 자신을 뺐다")
chk('if row["status"] == "확인중":' in body and '"duplicate": True' in body,
    "★★★ 이미 확인중이면 오류가 아니라 조용한 성공(duplicate)으로 돌린다")

# ============================================================
print("\n[2] 실행 — Flask 실서버로 실제 재시도 시나리오 검증")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round244_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R244업체','시행사','활성')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,partner_id,category,region) "
        "VALUES('R244-C','시공중',?,'금속','서울')", (pid,)).lastrowid
    did = conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,partner_id,title,status) "
        "VALUES('R244-DF1',?,'R244-C',?,'테스트 하자','접수')", (cid, pid)).lastrowid
    did_closed = conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,partner_id,title,status) "
        "VALUES('R244-DF2',?,'R244-C',?,'테스트 하자2','완료')", (cid, pid)).lastrowid
    conn.commit(); conn.close()

    c = A.app.test_client()
    tok = "r244-csrf"
    with c.session_transaction() as sess:
        sess["partner_id"] = pid; sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    def count_notify():
        cc = DB.get_db()
        n = cc.execute("SELECT COUNT(*) c FROM notifications WHERE ntype='재시공보고'").fetchone()["c"]
        cc.close(); return n

    def count_log():
        cc = DB.get_db()
        n = cc.execute("SELECT COUNT(*) c FROM activity_log WHERE action='재시공 완료 보고'").fetchone()["c"]
        cc.close(); return n

    #  ── (a) 최초 완료보고 — 정상 성공, 상태가 확인중으로 바뀐다 ──
    ra = c.post(f"/api/partner/defects/{did}/resolve", headers=hdr,
                json={"resolution": "재시공 완료"})
    chk(ra.status_code == 200 and ra.get_json().get("ok") and not ra.get_json().get("duplicate"),
        "★★★ 최초 완료보고는 정상 성공(duplicate 아님)", ra.get_json())
    n_after_1 = count_notify()
    l_after_1 = count_log()
    chk(n_after_1 == 1 and l_after_1 == 1,
        "STEP 알림·감사로그가 각각 1건씩만 생겼다", (n_after_1, l_after_1))

    #  ── (b) 같은 요청을 그대로 재시도(네트워크 재시도·더블클릭 재현) ──
    rb = c.post(f"/api/partner/defects/{did}/resolve", headers=hdr,
                json={"resolution": "재시공 완료"})
    chk(rb.status_code == 200 and rb.get_json().get("ok") and rb.get_json().get("duplicate"),
        "★★★★ 재시도는 오류가 아니라 조용한 성공(duplicate:true)으로 처리된다"
        "(고치기 전엔 매번 새 알림·로그를 또 쌓았다)", rb.get_json())
    chk(count_notify() == 1 and count_log() == 1,
        "★★★★ 재시도 뒤에도 알림·감사로그는 여전히 1건씩뿐이다"
        "(고치기 전엔 재시도마다 하나씩 더 쌓였다)", (count_notify(), count_log()))

    #  ── (c) 대조군 — 이미 완료·반려로 닫힌 하자는 여전히 진짜 오류로 막힌다 ──
    rc = c.post(f"/api/partner/defects/{did_closed}/resolve", headers=hdr,
                json={"resolution": "재시공 완료"})
    chk(rc.status_code == 409 and rc.get_json().get("code") == "DEFECT_CLOSED",
        "★★★ 대조군 — 이미 완료된 하자에 대한 보고는 여전히 409 로 막힌다"
        "(회귀로 이 보호가 풀리지 않았다)", rc.get_json())
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드244 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
