# -*- coding: utf-8 -*-
"""스캔 155라운드 회귀 — partner_applications → partners 좌표 배관 공백.

  db.py 마이그레이션 주석이 이미 "신청 때 받아 승인 시 그대로 넘긴다"고 선언한
  lat/lng 인데, 실제로는 세 지점 모두 빠져 있었다.
    ① 공개 입점신청(POST /api/applications, 가장 흔한 유입 경로) — 게다가
       FIELD_LIMITS 에 lat/lng 이 없어 d=clean 재대입 때 값 자체가 통째로
       사라졌다(바로 위에 있는 address 결함과 완전히 같은 함정).
    ② 담당자 직접접수(POST /api/applications/manual)
    ③ 승인 처리(PATCH /api/applications/<id>) — app_row 에 좌표가 있어도
       partners INSERT 가 안 옮겼다.
  프런트도 함께 손봤다 — 공개 폼(apply_partner.html)과 담당자 직접접수 모달
  (admin.js appIntakeForm) 둘 다 주소만 받고 AddrPick 좌표선택 자체가 안
  붙어 있어, 백엔드만 고치면 죽은 배관으로 남을 뻔했다.

      python test_scan_round155_fixes.py
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
HTML_SRC = read("templates/apply_partner.html")
JS_SRC = read("static/admin.js")

print("=" * 72)
print("  스캔 155라운드 회귀 — 입점신청 접수·승인 파이프라인의 좌표 공백")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk('"lat": 20, "lng": 20' in APP_SRC,
    "★★★ FIELD_LIMITS 에 lat/lng 이 등록돼 clean_public_form 을 살아서 통과한다"
    "(address 와 같은 함정 — 표에 없으면 d=clean 재대입 때 조용히 사라진다)")

i1 = APP_SRC.index("def api_create_application(")
i1_end = APP_SRC.index("\ndef ", i1 + 1)
b1 = APP_SRC[i1:i1_end]
chk("_alat, _alng = _picked_coords(d)" in b1,
    "★★★ api_create_application(공개 폼) 이 _picked_coords() 로 좌표를 받는다")
chk("lat,lng,agree_privacy" in b1,
    "★★★ 공개 폼 INSERT 열 목록에 lat,lng 이 들어갔다")

i2 = APP_SRC.index("def api_application_create(")
i2_end = APP_SRC.index("\ndef ", i2 + 1)
b2 = APP_SRC[i2:i2_end]
chk("_alat, _alng = _picked_coords(d)" in b2,
    "★★★ api_application_create(담당자 직접접수) 도 _picked_coords() 로 좌표를 받는다")
chk("lat,lng)" in b2,
    "★★★ 직접접수 INSERT 열 목록에 lat,lng 이 들어갔다")

i3 = APP_SRC.index("def api_application_update(")
i3_end = APP_SRC.index("\ndef ", i3 + 1)
b3 = APP_SRC[i3:i3_end]
chk('_alat, _alng = app_row.get("lat"), app_row.get("lng")' in b3,
    "★★★ api_application_update(승인) 이 신청서에 저장된 좌표를 읽는다")
chk("lat,lng,geo_src)" in b3,
    "★★★ 승인이 만드는 partners INSERT 열 목록에 lat,lng,geo_src 가 들어갔다")
chk('"주소검색" if _alat is not None else None' in b3,
    "★★★ 좌표가 있을 때만 geo_src='주소검색' 을 남긴다(없으면 NULL, 조작하지 않는다)")

chk("asset('addrpick.js')" in HTML_SRC,
    "★★★ 공개 입점신청 폼이 addrpick.js 를 로드한다")
chk("AddrPick.attach({input:'#address', region:'#region'})" in HTML_SRC,
    "★★★ 공개 폼의 주소 입력에 AddrPick 좌표선택이 붙었다")
chk("Object.assign(body, AddrPick.coords('#address'))" in HTML_SRC,
    "★★★ 공개 폼 제출 시 고른 좌표를 함께 보낸다")

chk("AddrPick.attach({input:'#q_addr', region:'#q_region'})" in JS_SRC,
    "★★★ 담당자 직접접수 모달의 주소 입력에도 AddrPick 이 붙었다")
chk("...(window.AddrPick ? AddrPick.coords('#q_addr') : {})" in JS_SRC,
    "★★★ 직접접수 저장 시에도 고른 좌표를 함께 보낸다")

# ============================================================
print("\n[2] 실행 — 공개 입점신청(POST /api/applications)에 좌표가 실제로 저장되는가")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round155_")
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
    conn.commit()

    pub = A.app.test_client()
    r1 = pub.post("/api/applications", json={
        "company": "R155공개업체", "phone": "010-1111-2222", "major": "누수·배관·설비",
        "address": "서울 강남구 테스트로 1", "agree_privacy": True, "agree_marketing": False,
        "lat": 37.55, "lng": 127.03,
        #  ⚠ [라운드288] 공개 접수가 이제 상시 인력 수(staff_count)를 필수로 본다
        #    (미입력·0·음수는 1인 사업자로 거부) — 이 테스트는 좌표 저장만
        #    검증하는 게 목적이라 그 관문을 그냥 통과할 값만 채운다.
        "staff_count": "5",
    })
    chk(r1.status_code == 200 and r1.get_json().get("ok"),
        "STEP 공개 폼 접수가 200/ok 다", (r1.status_code, r1.get_json()))
    aid1 = r1.get_json().get("id")
    row1 = dict(conn.execute(
        "SELECT lat, lng FROM partner_applications WHERE id=?", (aid1,)).fetchone())
    chk(row1["lat"] is not None and abs(row1["lat"] - 37.55) < 1e-6
        and abs(row1["lng"] - 127.03) < 1e-6,
        "★★★ 공개 폼으로 보낸 좌표가 partner_applications 에 그대로 저장된다"
        "(FIELD_LIMITS 에 없었다면 여기서 NULL 이 나왔을 것이다)", row1)

    # 대조군 — 좌표를 안 보내면(주소만 문자 입력) 조용히 NULL, 조작 안 함
    r1b = pub.post("/api/applications", json={
        "company": "R155공개업체B", "phone": "010-1111-3333", "major": "누수·배관·설비",
        "address": "부산 해운대구 아무데나 1", "agree_privacy": True,
        "staff_count": "5",   # ⚠ [라운드288] 위와 같은 이유
    })
    chk(r1b.status_code == 200, "STEP 좌표 없는 공개 폼 접수도 200 이다", r1b.status_code)
    row1b = dict(conn.execute(
        "SELECT lat, lng FROM partner_applications WHERE id=?", (r1b.get_json()["id"],)).fetchone())
    chk(row1b["lat"] is None and row1b["lng"] is None,
        "★ 좌표를 안 보내면 NULL 로 남는다(좌표 조작 없음)", row1b)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드155 [2] 공개 폼 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — 담당자 직접접수(POST /api/applications/manual)에도 좌표가 저장되는가")
# ------------------------------------------------------------
try:
    admin = A.app.test_client()
    tok = "r155-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    r2 = admin.post("/api/applications/manual", json={
        "company": "R155직접접수업체", "phone": "010-2222-3333", "major": "누수·배관·설비",
        "address": "대전 서구 둔산로 1", "lat": 36.35, "lng": 127.38,
    }, headers=hdr)
    chk(r2.status_code == 200 and r2.get_json().get("ok"),
        "STEP 직접접수가 200/ok 다", (r2.status_code, r2.get_json()))
    aid2 = r2.get_json().get("id")
    row2 = dict(conn.execute(
        "SELECT lat, lng FROM partner_applications WHERE id=?", (aid2,)).fetchone())
    chk(row2["lat"] is not None and abs(row2["lat"] - 36.35) < 1e-6
        and abs(row2["lng"] - 127.38) < 1e-6,
        "★★★ 담당자가 직접접수 때 고른 좌표도 그대로 저장된다", row2)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드155 [3] 직접접수 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[4] 실행 — 승인(PATCH /api/applications/<id>)이 좌표를 partners 로 옮기는가")
# ------------------------------------------------------------
try:
    aid3 = conn.execute(
        "INSERT INTO partner_applications(company,major,phone,address,status,partner_type,"
        "                                 staff_count,created_at,lat,lng) "
        "VALUES('R155승인대상업체','누수·배관·설비','01044445555','인천 남동구 1','서류검토',"
        "       '시공사',2,?,35.2,126.8)", (DB.now(),)).lastrowid
    conn.commit()

    r3 = admin.patch(f"/api/applications/{aid3}", json={"status": "승인"}, headers=hdr)
    chk(r3.status_code == 200, "STEP 좌표 있는 신청서 승인이 200 이다", (r3.status_code, r3.get_json()))
    pid3 = dict(conn.execute(
        "SELECT partner_id FROM partner_applications WHERE id=?", (aid3,)).fetchone())["partner_id"]
    chk(bool(pid3), "★ 승인이 partner_id 를 채운다", pid3)
    prow3 = dict(conn.execute(
        "SELECT lat, lng, geo_src FROM partners WHERE id=?", (pid3,)).fetchone())
    chk(prow3["lat"] is not None and abs(prow3["lat"] - 35.2) < 1e-6
        and abs(prow3["lng"] - 126.8) < 1e-6 and prow3["geo_src"] == "주소검색",
        "★★★ 신청서의 좌표가 승인으로 만들어진 partners 행에 그대로 옮겨진다"
        "(고치기 전엔 이 값이 전부 NULL 이었다)", prow3)

    # ── 대조군 — 좌표 없는(주소만 있는) 옛 신청서를 승인해도 조작하지 않는다 ──
    aid4 = conn.execute(
        "INSERT INTO partner_applications(company,major,phone,address,status,partner_type,"
        "                                 staff_count,created_at) "
        "VALUES('R155승인대상업체무좌표','누수·배관·설비','01055556666','광주 서구 1','서류검토',"
        "       '시공사',2,?)", (DB.now(),)).lastrowid
    conn.commit()
    r4 = admin.patch(f"/api/applications/{aid4}", json={"status": "승인"}, headers=hdr)
    chk(r4.status_code == 200, "STEP 좌표 없는 신청서 승인도 200 이다(에러 없음)", r4.status_code)
    pid4 = dict(conn.execute(
        "SELECT partner_id FROM partner_applications WHERE id=?", (aid4,)).fetchone())["partner_id"]
    prow4 = dict(conn.execute(
        "SELECT lat, lng, geo_src FROM partners WHERE id=?", (pid4,)).fetchone())
    chk(prow4["lat"] is None and prow4["lng"] is None and prow4["geo_src"] is None,
        "★★★ 신청서에 좌표가 없으면 승인된 업체도 좌표 NULL — 없는 값을 지어내지 않는다", prow4)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드155 [4] 승인 경로 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
