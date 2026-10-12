# -*- coding: utf-8 -*-
"""스캔 153라운드 회귀 — 사건 주소를 수정해도 지도 좌표(lat/lng/geo_src)가
옛 자리에 그대로 남아있던 결함.

  api_case_edit() 자신의 주석이 "주소만 바뀌고 좌표가 옛 자리에 남으면 지도가
  조용히 틀린 곳을 가리킨다"고 이미 경고하는데, 실제로는 요청에 lat/lng 키가
  없으면(기존 사건수정 모달 #e_addr 은 AddrPick 없이 순수 텍스트라 그 키를
  절대 안 보낸다) 좌표 갱신 블록 전체가 조용히 건너뛰어져 옛 주소의 좌표가
  새 주소에 그대로 남았다 — 지도 핀·근접업체 거리계산(dispatch.py)이 전부
  이 값을 쓴다. 주소가 바뀌었는데 새 좌표를 못 받았으면 틀린 정밀좌표보다
  "지역 중심 폴백"이 낫다고 보고 좌표를 비운다(기존 수동 "좌표 해제" 버튼과
  같은 결과 — /api/cases/<cid>/coords 의 clear 동작과 동일).

      python test_scan_round153_fixes.py
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
print("  스캔 153라운드 회귀 — 사건 주소 수정 시 지도 좌표가 안 갱신되던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_ce = APP_SRC.index("def api_case_edit(")
i_ce_end = APP_SRC.index("\ndef ", i_ce + 1)
ce_body = APP_SRC[i_ce:i_ce_end]
chk("address_changed = (" in ce_body,
    "★★★ api_case_edit 가 주소 변경 여부를 명시적으로 판정한다")
chk('sets += ["lat=NULL", "lng=NULL", "geo_src=NULL"]' in ce_body,
    "★★★ 주소만 바뀌고 새 좌표가 없으면 옛 좌표를 비운다(과거엔 그대로 남았다)")
chk("got_fresh_coords = True" in ce_body,
    "★ 새 좌표가 실제로 왔을 때는 좌표를 비우지 않는 분기가 있다")

# ============================================================
print("\n[2] 실행 — 실제 라우트(PATCH /api/cases/<cid>)로 재현")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round153_")
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
                 "VALUES('admin','x','검증','중간관리자')")
    conn.commit()
    admin = A.app.test_client()
    tok = "r153-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    def _mk_case(tag):
        return conn.execute(
            "INSERT INTO cases(case_no,status,category,region,address,lat,lng,geo_src,is_demo) "
            f"VALUES('R153-{tag}','접수','가드레일','서울','서울 강남구 테헤란로 1',"
            "        37.5,127.03,'주소검색',0)").lastrowid

    # ── ① 주소만 바꾸고 좌표를 안 보내면 — 옛 좌표가 비워진다 ──
    cid1 = _mk_case("A")
    conn.commit()
    r1 = admin.patch(f"/api/cases/{cid1}", json={"address": "부산 해운대구 우동 1"}, headers=hdr)
    chk(r1.status_code == 200, "STEP 주소만 보낸 PATCH 가 200 이다", r1.status_code)
    row1 = dict(conn.execute(
        "SELECT address, lat, lng, geo_src FROM cases WHERE id=?", (cid1,)).fetchone())
    chk(row1["address"] == "부산 해운대구 우동 1", "★ (사전조건) 주소는 실제로 바뀐다", row1)
    chk(row1["lat"] is None and row1["lng"] is None and row1["geo_src"] is None,
        "★★★ 새 좌표를 못 받았으니 옛(강남) 좌표는 비워진다"
        "(고치기 전엔 부산으로 바뀐 뒤에도 강남 좌표가 그대로 남았다)", row1)

    # ── ② 주소와 함께 새 좌표(부산)를 보내면 — 그 좌표로 정확히 갱신된다 ──
    cid2 = _mk_case("B")
    conn.commit()
    r2 = admin.patch(f"/api/cases/{cid2}",
                     json={"address": "부산 해운대구 우동 2", "lat": 35.16, "lng": 129.16},
                     headers=hdr)
    chk(r2.status_code == 200, "STEP 주소+좌표를 함께 보낸 PATCH 가 200 이다", r2.status_code)
    row2 = dict(conn.execute(
        "SELECT address, lat, lng, geo_src FROM cases WHERE id=?", (cid2,)).fetchone())
    chk(abs((row2["lat"] or 0) - 35.16) < 1e-6 and abs((row2["lng"] or 0) - 129.16) < 1e-6,
        "★★★ 새 좌표가 실제로 왔으면 그 값으로 정확히 갱신된다(비워지지 않는다)", row2)

    # ── ③ 주소를 안 건드리면 — 기존 좌표는 그대로 보존된다(과잉소거 아님) ──
    cid3 = _mk_case("C")
    conn.commit()
    r3 = admin.patch(f"/api/cases/{cid3}", json={"manager": "홍길동"}, headers=hdr)
    chk(r3.status_code == 200, "STEP 담당자만 바꾸는 PATCH 가 200 이다", r3.status_code)
    row3 = dict(conn.execute(
        "SELECT manager, lat, lng FROM cases WHERE id=?", (cid3,)).fetchone())
    chk(row3["manager"] == "홍길동" and row3["lat"] == 37.5 and row3["lng"] == 127.03,
        "★★★ 주소를 안 건드린 수정은 기존 좌표를 그대로 둔다(과잉 소거 아님)", row3)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드153 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
