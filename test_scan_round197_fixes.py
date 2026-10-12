# -*- coding: utf-8 -*-
"""스캔 197라운드 회귀 — 두 결함.

  ① app.py api_partner_create(): 활성 협력사를 만드는 다른 모든 경로(입점신청
    승인·업체 상태변경)는 이미 중간관리자 이상만 허용하는데, 직접등록만
    @require_admin(등급 무관)이었다 — 하위관리자가 이름 하나만 보내도(status
    기본값이 '활성') 즉시 활성 협력사가 생겨 실사건 출동수배 대상이 됐다.

  ② app.py api_photo_reject()/api_photo_unreject(): 형제(api_photos_approve)
    는 이미 중간관리자로 올렸는데(승인은 정산의 필수 관문이라서), 승인을
    뒤집는 이 두 액션은 여전히 등급 무관이라 하위관리자가 중간관리자의
    검수 판단을 일방적으로 무효화할 수 있었다.

      python test_scan_round197_fixes.py
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
print("  스캔 197라운드 회귀 — 협력사 직접등록·사진반려의 등급 우회")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_partner_create():")
i1 = APP_SRC.index("\ndef ", i0 + 1)
create_body = APP_SRC[i0:i1]
chk('ROLE_RANK["중간관리자"]' in create_body,
    "★★★★ 협력사 직접등록이 활성화 시 중간관리자 이상을 요구한다"
    "(고치기 전엔 @require_admin — 등급 무관이었다)")
chk('"심사중"' in create_body,
    "★★★ 상태 미지정 시 기본값이 '심사중'이다(고치기 전엔 '활성'이 기본값이었다)")

i2 = APP_SRC.index('@app.post("/api/photos/<int:pid>/unreject")')
i3 = APP_SRC.index("\n@app.post(", i2 + 1)
unreject_seg = APP_SRC[i2:i3]
chk('@require_role("중간관리자")' in unreject_seg,
    "★★★★ 사진 반려취소가 중간관리자 이상을 요구한다(고치기 전엔 등급 무관)")

i4 = APP_SRC.index('@app.post("/api/photos/<int:pid>/reject")')
i5 = APP_SRC.index("\n@app.post(", i4 + 1)
reject_seg = APP_SRC[i4:i5]
chk('@require_role("중간관리자")' in reject_seg,
    "★★★★ 사진 반려가 중간관리자 이상을 요구한다(고치기 전엔 등급 무관)")

# ============================================================
print("\n[2] 실행 — ① 하위관리자는 협력사를 '활성'으로 못 만들고, "
      "중간관리자는 그대로 만들 수 있다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round197_")
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
                 "VALUES('r197junior','x','검증하위','하위관리자')")
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r197mid','x','검증중간','중간관리자')")
    conn.commit()

    junior = A.app.test_client()
    jtok = "r197-junior-csrf"
    with junior.session_transaction() as sess:
        sess["admin"] = "r197junior"; sess["admin_role"] = "하위관리자"
        sess["admin_name"] = "검증하위"; sess["_csrf"] = jtok
    jhdr = {"X-CSRF-Token": jtok}

    mid = A.app.test_client()
    mtok = "r197-mid-csrf"
    with mid.session_transaction() as sess:
        sess["admin"] = "r197mid"; sess["admin_role"] = "중간관리자"
        sess["admin_name"] = "검증중간"; sess["_csrf"] = mtok
    mhdr = {"X-CSRF-Token": mtok}

    # ①-1 하위관리자가 상태 지정 없이 등록 — 성공하되 '심사중'으로 떨어져야 한다
    r1 = junior.post("/api/partners", json={"name": "R197업체A"}, headers=jhdr)
    j1 = r1.get_json() or {}
    st1 = conn.execute("SELECT status FROM partners WHERE id=?", (j1.get("id"),)).fetchone() \
        if j1.get("ok") else None
    chk(r1.status_code == 200 and j1.get("ok") is True,
        "하위관리자의 협력사 등록 자체는 여전히 성공한다(접수 보조 업무, 회귀 없음)",
        (r1.status_code, j1))
    chk(st1 is not None and st1["status"] == "심사중",
        "★★★★ 상태를 안 정하면 '심사중'으로 등록된다(고치기 전엔 '활성'이었다)",
        dict(st1) if st1 else None)

    # ①-2 하위관리자가 '활성'을 명시적으로 요청 — 거부돼야 한다
    r2 = junior.post("/api/partners", json={"name": "R197업체B", "status": "활성"}, headers=jhdr)
    j2 = r2.get_json() or {}
    chk(r2.status_code == 403 and j2.get("code") == "FORBIDDEN",
        "★★★★ 하위관리자가 '활성'으로 직접 등록하려 하면 거부된다"
        "(고치기 전엔 그대로 성공해 실사건 출동수배 대상이 됐다)", (r2.status_code, j2))

    # ①-3 중간관리자는 '활성'으로 그대로 등록할 수 있다(회귀 없음)
    r3 = mid.post("/api/partners", json={"name": "R197업체C", "status": "활성"}, headers=mhdr)
    j3 = r3.get_json() or {}
    st3 = conn.execute("SELECT status FROM partners WHERE id=?", (j3.get("id"),)).fetchone() \
        if j3.get("ok") else None
    chk(r3.status_code == 200 and j3.get("ok") is True and st3 and st3["status"] == "활성",
        "★★★ 중간관리자는 '활성'으로 바로 등록할 수 있다(정당한 업무, 회귀 없음)",
        (r3.status_code, j3, dict(st3) if st3 else None))

    # ============================================================
    print("\n[3] 실행 — ② 하위관리자는 승인된 사진을 반려·취소할 수 없고, "
          "중간관리자는 할 수 있다")
    # ------------------------------------------------------------
    now = DB.now()
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo,created_at) "
        "VALUES('R197-CASE','시공중','유리','서울',0,?)", (now,)).lastrowid
    pid_a = conn.execute(
        "INSERT INTO photos(case_id,uploader,uploader_role,rel_path,kind,review_status,created_at) "
        "VALUES(?,'R197업체','협력사','r197a.jpg','완료','승인',?)", (cid, now)).lastrowid
    pid_b = conn.execute(
        "INSERT INTO photos(case_id,uploader,uploader_role,rel_path,kind,review_status,"
        "                   reject_reason,created_at) "
        "VALUES(?,'R197업체','협력사','r197b.jpg','완료','반려','최초반려사유',?)",
        (cid, now)).lastrowid
    conn.commit()

    r4 = junior.post(f"/api/photos/{pid_a}/reject", json={"reason": "재촬영 요청"}, headers=jhdr)
    r5 = junior.post(f"/api/photos/{pid_b}/unreject", json={}, headers=jhdr)
    chk(r4.status_code == 403,
        "★★★★ 하위관리자는 승인된 사진을 반려할 수 없다(고치기 전엔 200으로 통과됐다)",
        (r4.status_code, r4.get_json()))
    chk(r5.status_code == 403,
        "★★★★ 하위관리자는 반려된 사진의 반려취소도 할 수 없다"
        "(고치기 전엔 200으로 통과됐다)", (r5.status_code, r5.get_json()))

    r6 = mid.post(f"/api/photos/{pid_a}/reject", json={"reason": "재촬영 요청"}, headers=mhdr)
    r7 = mid.post(f"/api/photos/{pid_b}/unreject", json={}, headers=mhdr)
    chk(r6.status_code == 200 and (r6.get_json() or {}).get("ok") is True,
        "★★★ 중간관리자는 정상적으로 사진을 반려할 수 있다(정당한 업무, 회귀 없음)",
        (r6.status_code, r6.get_json()))
    chk(r7.status_code == 200 and (r7.get_json() or {}).get("ok") is True,
        "★★★ 중간관리자는 정상적으로 반려취소도 할 수 있다(정당한 업무, 회귀 없음)",
        (r7.status_code, r7.get_json()))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드197 [2]~[3] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
