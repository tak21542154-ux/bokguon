# -*- coding: utf-8 -*-
"""스캔 229라운드 회귀 — EXIF(GPS) 제거에 실패한 사진이 낙찰 전 입찰자
   전원에게 그대로 열리던 결함.

  photo_ai.save_upload() 는 재인코딩(EXIF 제거)이 실패하면 "사진을 잃는
  것보다 낫다"며 원본을 그대로 저장하고 그 사실을 exif_error 로 돌려준다
  (자기 문서에 "그 사진은 입찰 업체에게 열립니다" 라고 이미 경고까지
  적어 뒀다). 그런데 이 값이 photos 테이블에 저장되지 않아, 열람 게이트
  (_photo_visible_to)가 이 사실 자체를 알 방법이 없었다 — 상세주소를
  시군구까지만 자르는 철칙이 GPS 박힌 사진 한 장으로 무효가 됐다.

  photos.exif_error 컬럼을 추가해 세 업로드 경로(협력사·피해사진·하자)
  전부 저장하고, "낙찰 전 입찰자 전원에게 연다" 분기에서만 이 값을
  확인한다 — 낙찰된 시행사·발주 보험사·관리자는 증거 보존 원칙대로
  그대로 볼 수 있다.

      python test_scan_round229_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("═" * 72)
print("  스캔 229라운드 회귀 — EXIF 제거 실패 사진이 낙찰 전 입찰자에게 노출")
print("═" * 72)

_tmpdir = tempfile.mkdtemp(prefix="round229_")
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
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(photos)")]
    conn.close()
    chk("exif_error" in cols,
        "★★★ 새 DB 스키마에 photos.exif_error 컬럼이 생긴다", cols)

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r229admin','x','검증','중간관리자')")
    iid = conn.execute(
        "INSERT INTO insurers(name,status,login_id,password_hash) "
        "VALUES('R229보험사','활성','r229insurer','x')").lastrowid
    bidder_a = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R229입찰사A','시공사','활성')").lastrowid
    bidder_b = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R229입찰사B','시공사','활성')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
        "VALUES('R229-001','입찰중','유리','서울',?,0)", (iid,)).lastrowid
    tainted_rel, clean_rel = f"{cid}/tainted.jpg", f"{cid}/clean.jpg"
    tainted_id = conn.execute(
        "INSERT INTO photos(case_id,kind,review_status,exif_error,rel_path,mime,ext,size,sha256,created_at) "
        "VALUES(?,'착공전','승인','해상도 과대(7000x6000) — 위치정보를 지우지 못했습니다',"
        "       ?,'image/jpeg','jpg',1,'a',?)", (cid, tainted_rel, DB.now())).lastrowid
    clean_id = conn.execute(
        "INSERT INTO photos(case_id,kind,review_status,exif_error,rel_path,mime,ext,size,sha256,created_at) "
        "VALUES(?,'착공전','승인',NULL,?,'image/jpeg','jpg',1,'b',?)", (cid, clean_rel, DB.now())).lastrowid
    conn.commit()
    conn.close()
    #  _photo_visible_to 통과 뒤 실제 파일서빙(send_file)까지 가므로, 디스크에도
    #  실제 파일이 있어야 한다(경로 자체를 테스트하는 게 아니라 열람권한이 목적).
    for _rel in (tainted_rel, clean_rel):
        _full = A.PHOTO.abs_path(_rel)
        os.makedirs(os.path.dirname(_full), exist_ok=True)
        with open(_full, "wb") as _f:
            _f.write(b"\xff\xd8\xff\xe0fake-jpeg-bytes")

    def as_partner(pid_):
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["partner_id"] = pid_; sess["partner_name"] = "검증업체"
        return c

    bidder = as_partner(bidder_a)

    # ══════════════════════════════════════════════════════════
    print("\n[1] 낙찰 전 — 입찰자(아직 낙찰 안 됨)")
    # ──────────────────────────────────────────────────────────
    r_tainted = bidder.get(f"/api/photos/{tainted_id}/file")
    chk(r_tainted.status_code == 403,
        "★★★★ GPS 제거에 실패한 사진은 낙찰 전 입찰자에게 이제 403 이다"
        "(고치기 전엔 '착공전' 종류의 입찰중 사건 사진은 무조건 열렸다)",
        r_tainted.status_code)

    r_clean = bidder.get(f"/api/photos/{clean_id}/file")
    chk(r_clean.status_code == 200,
        "STEP GPS 가 정상 제거된 사진은 그대로 열린다(과잉차단 아님)",
        r_clean.status_code)

    # ══════════════════════════════════════════════════════════
    print("\n[2] 낙찰 후 — 그 업체는 증거 보존 원칙대로 그대로 본다")
    # ──────────────────────────────────────────────────────────
    conn = DB.get_db()
    conn.execute("UPDATE cases SET partner_id=? WHERE id=?", (bidder_a, cid))
    conn.commit()
    conn.close()
    r_awarded = bidder.get(f"/api/photos/{tainted_id}/file")
    chk(r_awarded.status_code == 200,
        "★★★ 낙찰받은 시행사는 GPS 미제거 사진도 그대로 볼 수 있다"
        "(과잉차단 아님 — 실제 시공에 그 증거가 필요하다)", r_awarded.status_code)

    other_bidder = as_partner(bidder_b)
    r_other = other_bidder.get(f"/api/photos/{tainted_id}/file")
    chk(r_other.status_code == 403,
        "STEP 낙찰 못 받은 다른 입찰사는 이미 낙찰이 끝났으니 애초에 못 본다"
        "(_is_biddable 이 아니게 됨 — 이 라운드와 무관한 기존 동작)",
        r_other.status_code)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 발주 보험사·관리자 — 증거 보존 원칙대로 항상 그대로 본다")
    # ──────────────────────────────────────────────────────────
    insurer_c = A.app.test_client()
    with insurer_c.session_transaction() as sess:
        sess["insurer_id"] = iid; sess["insurer_login"] = "r229insurer"
    r_insurer = insurer_c.get(f"/api/photos/{tainted_id}/file")
    chk(r_insurer.status_code == 200,
        "STEP 발주 보험사는 GPS 미제거 사진도 항상 볼 수 있다(과잉차단 아님)",
        r_insurer.status_code)

    admin_c = A.app.test_client()
    with admin_c.session_transaction() as sess:
        sess["admin"] = "r229admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
    r_admin = admin_c.get(f"/api/photos/{tainted_id}/file")
    chk(r_admin.status_code == 200,
        "STEP 관리자는 GPS 미제거 사진도 항상 볼 수 있다(과잉차단 아님)",
        r_admin.status_code)

    # ══════════════════════════════════════════════════════════
    print("\n[4] 실행 — 업로드 경로가 exif_error 를 실제로 저장하는가")
    # ──────────────────────────────────────────────────────────
    _real_save = A.PHOTO.save_upload

    def _fake_save_upload(fs, case_id):
        info = _real_save(fs, case_id)
        info["exif_error"] = "테스트로 강제한 EXIF 제거 실패"
        return info

    conn = DB.get_db()
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
        "VALUES('R229-002','입찰중','유리','서울',?,0)", (iid,)).lastrowid
    conn.commit()
    conn.close()

    A.PHOTO.save_upload = _fake_save_upload
    try:
        insurer_c2 = A.app.test_client()
        _tok = "r229-insurer-csrf"
        with insurer_c2.session_transaction() as sess:
            sess["insurer_id"] = iid; sess["insurer_login"] = "r229insurer"; sess["_csrf"] = _tok
        #  진짜로 디코딩되는 최소 JPEG 이어야 한다 — save_upload() 내부의
        #  _strip_exif() 가 Image.open() 으로 실제 디코딩을 시도한다.
        from PIL import Image as _Img
        _buf = io.BytesIO()
        _Img.new("RGB", (10, 10), (255, 0, 0)).save(_buf, format="JPEG")
        img = (io.BytesIO(_buf.getvalue()), "photo.jpg")
        r_up = insurer_c2.post(f"/api/insurer/cases/{cid2}/photos",
                                headers={"X-CSRF-Token": _tok},
                                data={"photos": img}, content_type="multipart/form-data")
        chk(r_up.status_code == 200 and r_up.get_json().get("count") == 1,
            "STEP 업로드 자체는 정상 처리된다(과잉차단 아님)", (r_up.status_code, r_up.get_json()))
    finally:
        A.PHOTO.save_upload = _real_save

    conn = DB.get_db()
    up_row = conn.execute("SELECT exif_error FROM photos WHERE case_id=? ORDER BY id DESC LIMIT 1",
                           (cid2,)).fetchone()
    conn.close()
    chk(up_row is not None and up_row["exif_error"] == "테스트로 강제한 EXIF 제거 실패",
        "★★★★ 피해사진 업로드 경로(_upload_damage_photos)가 save_upload() 의 "
        "exif_error 를 실제로 photos 테이블에 저장한다(고치기 전엔 이 값이 "
        "그 자리에서 버려졌다)", dict(up_row) if up_row else None)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드229 서버측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
