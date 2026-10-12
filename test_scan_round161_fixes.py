# -*- coding: utf-8 -*-
"""스캔 161라운드 회귀 — 4개 혼합주체 라우트가 계정 생사 확인을 안 하던 결함.

  api_notices·api_address_search(JSON API)와 billing_guide·insurer_api_guide
  (화면)는 전부 "session.get(...) 존재"만 보고, 형제 라우트 6곳이 이미 쓰는
  계정 생사 확인(_account_alive, JSON API 쪽은 _mixed_actor_guard 로 감싸져
  있다)을 부르지 않았다. Flask 세션 쿠키는 클라이언트 서명 쿠키라 DB 상태와
  무관하게 계속 유효하므로, 퇴출·정지된 협력사/해지된 보험사가 로그아웃
  전까지는 내부 공지·주소검색 대행·청구설명서·연동안내서(발급키 포함)를
  계속 받을 수 있었다.

      python test_scan_round161_fixes.py
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
print("  스캔 161라운드 회귀 — 4개 혼합주체 라우트의 계정 생사 확인 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
for fn, marker in (
    ("def api_notices(", "_g = _mixed_actor_guard()"),
    ("def api_address_search(", "_g = _mixed_actor_guard()"),
    ("def billing_guide(", 'alive, _msg = _account_alive()'),
    ("def insurer_api_guide(", 'alive, _msg = _account_alive()'),
):
    i0 = APP_SRC.index(fn)
    i1 = APP_SRC.index("\n@app.", i0 + 1)
    body = APP_SRC[i0:i1]
    chk(marker in body, f"★★★ {fn.split('(')[0][4:]} 이 계정 생사 확인을 부른다")

# ============================================================
print("\n[2] 실행 — 퇴출·해지된 계정이 세션을 유지한 채 재요청하면 이제 막히는가")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round161_")
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
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,login_id,created_at) "
        "VALUES('R161업체','시공사','활성','가드레일','서울','r161p',?)", (DB.now(),)).lastrowid
    iid = conn.execute(
        "INSERT INTO insurers(name,status,login_id,created_at) "
        "VALUES('R161보험사','활성','r161i',?)", (DB.now(),)).lastrowid
    conn.commit(); conn.close()

    def _fresh_partner_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["partner_id"] = pid; sess["partner_name"] = "R161업체"
        return c

    def _fresh_insurer_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["insurer_id"] = iid; sess["insurer_name"] = "R161보험사"
        return c

    def _set_status(table, rid, status):
        c = DB.get_db()
        c.execute(f"UPDATE {table} SET status=? WHERE id=?", (status, rid))
        c.commit(); c.close()

    #  ── ① api_notices — 협력사 세션 ──
    _set_status("partners", pid, "활성")
    c1 = _fresh_partner_client()
    r1a = c1.get("/api/notices")
    chk(r1a.status_code == 200, "STEP api_notices — 활성 협력사는 200", r1a.status_code)
    _set_status("partners", pid, "퇴출")
    r1b = c1.get("/api/notices")
    chk(r1b.status_code == 401,
        "★★★ api_notices — 퇴출 뒤 같은 세션 재요청이 이제 401 로 막힌다"
        "(고치기 전엔 200 으로 공지가 계속 나갔다)", r1b.status_code)

    #  ── ② api_address_search — 보험사 세션 ──
    _set_status("insurers", iid, "활성")
    c2 = _fresh_insurer_client()
    r2a = c2.get("/api/address/search?q=서울시청")
    chk(r2a.status_code == 200, "STEP api_address_search — 활성 보험사는 200", r2a.status_code)
    _set_status("insurers", iid, "해지")
    r2b = c2.get("/api/address/search?q=서울시청")
    chk(r2b.status_code == 401,
        "★★★ api_address_search — 해지 뒤 같은 세션 재요청이 이제 401 로 막힌다"
        "(고치기 전엔 200 으로 대행 검색이 계속 됐다)", r2b.status_code)

    #  ── ③ billing_guide(화면) — 협력사 세션 ──
    _set_status("partners", pid, "활성")
    c3 = _fresh_partner_client()
    r3a = c3.get("/report/billing")
    chk(r3a.status_code == 200, "STEP billing_guide — 활성 협력사는 200", r3a.status_code)
    _set_status("partners", pid, "퇴출")
    r3b = c3.get("/report/billing", follow_redirects=False)
    chk(r3b.status_code == 302,
        "★★★ billing_guide — 퇴출 뒤 같은 세션 재요청이 이제 로그인화면으로 돌아간다"
        "(고치기 전엔 200 으로 청구설명서가 계속 보였다)", r3b.status_code)

    #  ── ④ insurer_api_guide(화면) — 보험사 세션 ──
    _set_status("insurers", iid, "활성")
    c4 = _fresh_insurer_client()
    r4a = c4.get("/docs/insurer-api")
    chk(r4a.status_code == 200, "STEP insurer_api_guide — 활성 보험사는 200", r4a.status_code)
    _set_status("insurers", iid, "해지")
    r4b = c4.get("/docs/insurer-api", follow_redirects=False)
    chk(r4b.status_code == 302,
        "★★★ insurer_api_guide — 해지 뒤 같은 세션 재요청이 이제 로그인화면으로 돌아간다"
        "(고치기 전엔 200 으로 발급키 안내서가 계속 보였다)", r4b.status_code)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드161 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
