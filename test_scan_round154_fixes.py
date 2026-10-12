# -*- coding: utf-8 -*-
"""스캔 154라운드 회귀 — round153이 cases 에 고친 것과 같은 결함이 partners
테이블의 두 수정 경로(관리자 콘솔 api_partner_update, 협력사 마이페이지
api_partner_profile_update)에도 그대로 있었다. 주소만 바뀌고 새 좌표를 못
받으면 옛 좌표가 그대로 남아, 근접업체 거리계산(api_case_nearby)·지도 핀이
엉뚱한 위치를 기준으로 계산됐다. partners 는 사건과 달리 수동 좌표 재입력
라우트도 없어 한 번 오염되면 회복 경로가 아예 없었다는 점에서 더 나빴다.

  ⚠ 두 함수 모두 "폼 전체를 매번 다시 보낸다" 방식이라(주소를 안 건드려도
    address 키는 항상 온다), 단순히 "address 키가 있으면 지운다"로 고치면
    관계없는 필드(전화번호 등)만 고쳐도 매번 좌표가 사라지는 더 나쁜 회귀가
    생긴다 — 반드시 저장된 값과 대조해 **실제로 바뀌었을 때만** 지운다.

      python test_scan_round154_fixes.py
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
print("  스캔 154라운드 회귀 — 협력사 주소 수정 시 좌표가 안 갱신되던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_pu = APP_SRC.index("def api_partner_update(")
i_pu_end = APP_SRC.index("\ndef ", i_pu + 1)
pu_body = APP_SRC[i_pu:i_pu_end]
#  ⚠ 라운드466이 같은 SELECT에 biz_no를 추가했다(사업자번호 중복재확인용) —
#    address/lat/lng 세 컬럼이 여전히 함께 있는지만 보고, 다른 컬럼이 몇 개
#    더 끼어도 안 깨지게 부분일치로 확인한다(고정 리터럴 전체일치는 이번처럼
#    무관한 컬럼 추가에도 매번 깨진다).
chk('"SELECT name, status, address, lat, lng' in pu_body and ' FROM partners WHERE id=?"' in pu_body,
    "★★★ api_partner_update 가 주소 대조를 위해 현재 address/lat/lng 을 함께 읽는다")
chk('sets += ["lat=NULL", "lng=NULL", "geo_src=NULL"]' in pu_body,
    "★★★ api_partner_update 가 주소만 바뀌고 새 좌표가 없으면 옛 좌표를 비운다")

i_pp = APP_SRC.index("def api_partner_profile_update(")
i_pp_end = APP_SRC.index("\ndef ", i_pp + 1)
pp_body = APP_SRC[i_pp:i_pp_end]
#  ⚠⚠ [라운드544] 형제(api_partner_update, 위 46~49행 주석 — round466이 같은
#    이유로 이미 부분일치로 바꿨다)와 같은 이유로 이 자리도 고친다 — 그 세션이
#    ceo/phone/email/region 을 "값이 안 바뀌면 UPDATE+로그를 안 쏜다"는 새
#    가드(스캔544)를 위해 대조용으로 이 SELECT에 추가하면서 고정 리터럴
#    전체일치가 깨졌다. address·lat·lng 세 컬럼이 여전히 함께 있는지만
#    부분일치로 확인한다(다른 컬럼이 몇 개 더 끼어도 안 깨지게).
chk('"SELECT ceo, phone, email, address, region, lat, lng ' in pp_body
    and '"FROM partners WHERE id=?"' in pp_body,
    "★★★ api_partner_profile_update 도 현재 address/lat/lng 을 먼저 읽는다")
chk('fields += ["lat=NULL", "lng=NULL", "geo_src=NULL"]' in pp_body,
    "★★★ api_partner_profile_update 도 주소만 바뀌면 옛 좌표를 비운다")

# ============================================================
print("\n[2] 실행 — 관리자 콘솔(api_partner_update)")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round154_")
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
    admin = A.app.test_client()
    tok = "r154-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    def _mk_partner(tag):
        return conn.execute(
            "INSERT INTO partners(name,partner_type,status,category,region,address,"
            "                     phone,lat,lng,geo_src) "
            f"VALUES('R154업체{tag}','시공사','활성','가드레일','서울',"
            "       '서울 강남구 테헤란로 1','01000000000',37.5,127.03,'주소검색')").lastrowid

    # ── ① 주소만 바꾸고 좌표를 안 보내면 — 옛 좌표가 비워진다 ──
    pid1 = _mk_partner("A")
    conn.commit()
    r1 = admin.patch(f"/api/partners/{pid1}", json={"address": "부산 해운대구 우동 1"}, headers=hdr)
    chk(r1.status_code == 200, "STEP 주소만 보낸 PATCH 가 200 이다", r1.status_code)
    row1 = dict(conn.execute(
        "SELECT address, lat, lng, geo_src FROM partners WHERE id=?", (pid1,)).fetchone())
    chk(row1["address"] == "부산 해운대구 우동 1", "★ (사전조건) 주소는 실제로 바뀐다", row1)
    chk(row1["lat"] is None and row1["lng"] is None and row1["geo_src"] is None,
        "★★★ 새 좌표를 못 받았으니 옛(서울) 좌표는 비워진다"
        "(고치기 전엔 부산으로 바뀐 뒤에도 서울 좌표가 그대로 남았다)", row1)

    # ── ② 주소와 함께 새 좌표를 보내면 — 그 좌표로 정확히 갱신된다 ──
    pid2 = _mk_partner("B")
    conn.commit()
    r2 = admin.patch(f"/api/partners/{pid2}",
                     json={"address": "부산 해운대구 우동 2", "lat": 35.16, "lng": 129.16},
                     headers=hdr)
    chk(r2.status_code == 200, "STEP 주소+좌표를 함께 보낸 PATCH 가 200 이다", r2.status_code)
    row2 = dict(conn.execute("SELECT lat, lng FROM partners WHERE id=?", (pid2,)).fetchone())
    chk(abs((row2["lat"] or 0) - 35.16) < 1e-6 and abs((row2["lng"] or 0) - 129.16) < 1e-6,
        "★★★ 새 좌표가 왔으면 그 값으로 정확히 갱신된다", row2)

    # ── ③ savePartner() 처럼 폼 전체를 재전송해도(주소는 동일값) — 좌표 보존 ──
    pid3 = _mk_partner("C")
    conn.commit()
    r3 = admin.patch(f"/api/partners/{pid3}", json={
        "name": f"R154업체C", "partner_type": "시공사", "phone": "01099998888",
        "address": "서울 강남구 테헤란로 1",   # 폼 전체 재전송 — 주소 값 자체는 안 바뀜
        "region": "서울", "category": "가드레일", "status": "활성",
    }, headers=hdr)
    chk(r3.status_code == 200, "STEP 폼 전체 재전송(주소는 동일) PATCH 가 200 이다", r3.status_code)
    row3 = dict(conn.execute(
        "SELECT phone, lat, lng FROM partners WHERE id=?", (pid3,)).fetchone())
    chk(row3["phone"] == "01099998888" and row3["lat"] == 37.5 and row3["lng"] == 127.03,
        "★★★ 주소값이 실제로는 안 바뀌었으면(폼 전체 재전송이라도) 좌표를 그대로 둔다"
        "(단순 'address 키 존재'만 보면 관계없는 필드 수정에도 매번 좌표가 지워진다)", row3)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드154 [1] api_partner_update 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — 협력사 마이페이지(api_partner_profile_update)")
# ------------------------------------------------------------
try:
    conn = DB.get_db()
    pid4 = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,address,"
        "                     phone,login_id,lat,lng,geo_src) "
        "VALUES('R154업체D','시공사','활성','가드레일','서울',"
        "       '서울 강남구 테헤란로 1','01000000001','r154d',37.5,127.03,'주소검색')").lastrowid
    conn.commit()

    partner = A.app.test_client()
    ptok = "r154-partner-csrf"
    with partner.session_transaction() as sess:
        sess["partner_id"] = pid4; sess["partner_name"] = "R154업체D"; sess["_csrf"] = ptok
    phdr = {"X-CSRF-Token": ptok}

    r4 = partner.patch("/api/partner/profile", json={"address": "대전 서구 둔산로 1"}, headers=phdr)
    chk(r4.status_code == 200, "STEP 마이페이지 주소만 보낸 PATCH 가 200 이다", r4.status_code)
    row4 = dict(conn.execute(
        "SELECT address, lat, lng, geo_src FROM partners WHERE id=?", (pid4,)).fetchone())
    chk(row4["address"] == "대전 서구 둔산로 1", "★ (사전조건) 주소는 실제로 바뀐다", row4)
    chk(row4["lat"] is None and row4["lng"] is None and row4["geo_src"] is None,
        "★★★ 마이페이지에서도 새 좌표를 못 받으면 옛(서울) 좌표가 비워진다", row4)

    # 대조군 — 주소를 안 건드리는 수정(전화번호만)은 좌표를 그대로 둔다
    pid5 = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,address,"
        "                     phone,login_id,lat,lng,geo_src) "
        "VALUES('R154업체E','시공사','활성','가드레일','서울',"
        "       '서울 강남구 테헤란로 1','01000000002','r154e',37.5,127.03,'주소검색')").lastrowid
    conn.commit()
    with partner.session_transaction() as sess:
        sess["partner_id"] = pid5; sess["partner_name"] = "R154업체E"; sess["_csrf"] = ptok
    r5 = partner.patch("/api/partner/profile", json={"phone": "01055556666"}, headers=phdr)
    chk(r5.status_code == 200, "STEP 전화번호만 바꾸는 마이페이지 PATCH 가 200 이다", r5.status_code)
    row5 = dict(conn.execute(
        "SELECT phone, lat, lng FROM partners WHERE id=?", (pid5,)).fetchone())
    chk(row5["phone"] == "01055556666" and row5["lat"] == 37.5 and row5["lng"] == 127.03,
        "★★★ 주소를 안 건드린 수정은 좌표를 그대로 둔다(과잉 소거 아님)", row5)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드154 [2] api_partner_profile_update 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
