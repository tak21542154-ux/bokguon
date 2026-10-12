# -*- coding: utf-8 -*-
"""스캔 212라운드 회귀 — 대시보드·지도 API의 두 가지 구멍.

  (a) app.py api_dashboard() 의 "이상 저가 입찰" 경보(risky)가 이 함수의
      다른 모든 집계(파이프라인·거래대금·오늘의 액션·지연경보·발주처별·
      공종별 — 전부 COALESCE(is_demo,0)=0 을 붙인다, 관련 주석 5회 반복)와
      달리 데모 사건을 걸러내지 않았다. 실측(2026-08-29): is_demo=1 인
      사건 #90(26-80037, 10.0% 하락)이 이 쿼리 조건을 그대로 만족한다 —
      기본 경보기준(20%) 밑이라 지금은 안 뜨지만, 기준을 낮추거나 낙폭이
      더 큰 데모 사건이 하나만 더 생겨도 "부정 저가입찰 의심" 경보에
      가짜 데이터가 섞여 나온다.

  (b) app.py api_map_cases() 의 사건 목록(LIMIT 500)이, 같은 함수의 형제인
      협력사 목록(LIMIT 3000)과 달리 잘렸는지 알 수 있는 총계가 없었다.
      협력사 쪽은 이미 "상한을 두면 '전체'라고 하면서 일부만 보여주게
      된다"며 partner_total 을 내려보내는데, 사건 쪽만 없었다 — 사건은
      완료돼도 행이 안 없어져 계속 누적되는 데이터라 이 상한에 먼저
      닿을 가능성이 더 크다(현재는 77건이라 잠재적 결함).

      python test_scan_round212_fixes.py
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
print("  스캔 212라운드 회귀 — 대시보드 저가경보 데모누출 · 지도 사건목록 총계 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("# [B4] 이상 저가 입찰")
i1 = APP_SRC.index("\n    # 발주처별 거래", i0)
risky_body = APP_SRC[i0:i1]
chk("AND COALESCE(c.is_demo,0)=0" in risky_body,
    "★★★★★ 핵심 — 이상 저가 입찰 경보 쿼리가 데모 사건을 제외한다"
    "(형제 집계 전부와 동일한 필터, 고치기 전엔 이 함수에서 유일하게 빠져 있었다)")

i2 = APP_SRC.index("def api_map_cases():")
i3 = APP_SRC.index("\n@app.post(\"/api/cases/<int:cid>/coords\")")
map_body = APP_SRC[i2:i3]
chk('case_total = one(conn.execute(' in map_body,
    "★★★★ 지도 API가 사건 총계(case_total)를 계산한다")
chk('"case_total": case_total,' in map_body,
    "★★★★ 그 총계를 응답에 포함한다(형제 partner_total 과 대칭)")
_i_total = map_body.find("case_total = one(conn.execute(")
_i_limit = map_body.find("ORDER BY id DESC LIMIT 500")
chk(_i_total != -1 and _i_limit != -1 and _i_total < _i_limit,
    "★ 총계 계산이 같은 WHERE 절을 쓰고, LIMIT 500 조회보다 먼저 온다")

# ============================================================
print("\n[2] 실행 — 실제 서버(Flask test_client)로 두 API 응답 확인")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round212_")
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
                 "VALUES('r212admin','x','검증','최고관리자')")
    now = DB.now()

    def mk_case_with_auction(case_no, is_demo, est_price, low_price):
        cid = conn.execute(
            "INSERT INTO cases(case_no,status,category,region,is_demo,est_price,created_at) "
            "VALUES(?,'승인대기','유리','서울',?,?,?)",
            (case_no, is_demo, est_price, now)).lastrowid
        conn.execute(
            "INSERT INTO auctions(case_id,status,low_price,bid_count,created_at) "
            "VALUES(?,'마감',?,1,?)", (cid, low_price, now))
        return cid

    # 50% 하락 — 기본 경보기준(20%)을 확실히 넘는 낙폭으로 심는다.
    cid_demo = mk_case_with_auction("R212-DEMO", 1, 10_000_000, 5_000_000)
    cid_real = mk_case_with_auction("R212-REAL", 0, 10_000_000, 5_000_000)
    conn.commit()

    admin_c = A.app.test_client()
    tok = "r212-admin-csrf"
    with admin_c.session_transaction() as sess:
        sess["admin"] = "r212admin"; sess["admin_role"] = "최고관리자"; sess["_csrf"] = tok

    r_dash = admin_c.get("/api/dashboard")
    chk(r_dash.status_code == 200, "STEP /api/dashboard 가 200 이다", r_dash.status_code)
    j_dash = r_dash.get_json()
    risky_nos = [x["case_no"] for x in j_dash.get("risky", [])]
    chk("R212-DEMO" not in risky_nos,
        "★★★★★ 핵심 — 데모 사건(R212-DEMO)은 저가경보 목록에 안 뜬다"
        "(고치기 전엔 떴다)", risky_nos)
    chk("R212-REAL" in risky_nos,
        "★ 실제 사건(R212-REAL, 똑같이 50%% 하락)은 그대로 뜬다(과잉차단 아님)",
        risky_nos)

    r_map = admin_c.get("/api/map/cases")
    chk(r_map.status_code == 200, "STEP /api/map/cases 가 200 이다", r_map.status_code)
    j_map = r_map.get_json()
    chk("case_total" in j_map, "★★★★ 지도 API 응답에 case_total 이 실제로 들어 있다", j_map.keys())
    expected_total = conn.execute(
        "SELECT COUNT(*) n FROM cases WHERE COALESCE(is_demo,0)=0").fetchone()["n"]
    chk(j_map.get("case_total") == expected_total,
        "★★★★ case_total 값이 실제 사건 수(데모 제외)와 정확히 일치한다",
        (j_map.get("case_total"), expected_total))

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드212 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
