# -*- coding: utf-8 -*-
"""스캔 141라운드 회귀 — round140(1차합의 승인자 하위계정 미구분)과 같은 계열의
형제 자리 8곳. 전부 session.get("insurer_name")/session.get("partner_name")
(조직명, 하위계정 전원 동일)을 감사기록·전용 컬럼에 직접 썼다 — portal_actor()
(조직명+로그인아이디)로 통일한다.

  A. api_insurer_set_severity        → cases.human_severity_by
  B. api_insurer_est_ack             → cases.est_ack_by
  C. api_defect_create               → defects.reporter / activity_log.actor
                                        (보험사 포털: portal_actor, 어드민: actor() 그대로)
  D. api_insurer_upload_damage_photos → photos.uploader (보험사)
  E. api_defect_photos_upload        → photos.uploader (보험사·협력사 공용)
  F. _create_case(포털 호출부)        → activity_log.actor("사건 등록…")
                                        (v1 API 호출부는 actor_name 생략 시 그대로 iname)
  G. api_insurer_co_ack              → change_orders.insurer_ack_by
  H. api_partner_upload_photos       → photos.uploader (협력사)

      python test_scan_round141_fixes.py
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
print("  스캔 141라운드 회귀 — 승인자 하위계정 미구분 형제 자리 8곳(round140과 같은 계열)")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — 8개 자리 모두 portal_actor() 로 통일됐다")
# ------------------------------------------------------------


def _fn_body(marker):
    i = APP_SRC.index(marker)
    i_end = min(x for x in (APP_SRC.find("\ndef ", i + 1), APP_SRC.find("\n@app.", i + 1)) if x != -1)
    return APP_SRC[i:i_end]


A_body = _fn_body("def api_insurer_set_severity(")
chk('(sev, portal_actor() or "보험사", DB.now(), cid))' in A_body,
    "A ★★★ api_insurer_set_severity 가 human_severity_by 를 portal_actor()로 남긴다")

B_body = _fn_body("def api_insurer_est_ack(")
chk('(b["code"], b["est_price"], portal_actor() or "보험사", DB.now(), cid))' in B_body,
    "B ★★★ api_insurer_est_ack 가 est_ack_by 를 portal_actor()로 남긴다")

C_body = _fn_body("def api_defect_create(")
chk("reporter = portal_actor(actor())" in C_body,
    "C ★★★ api_defect_create 가 reporter 를 portal_actor(actor())로 남긴다"
    "(보험사 포털은 개인까지, 어드민은 admin_name 그대로)")

D_body = _fn_body("def api_insurer_upload_damage_photos(")
chk('return _upload_damage_photos(cid, c, conn, portal_actor(), "보험사")' in D_body,
    "D ★★★ api_insurer_upload_damage_photos 가 uploader 로 portal_actor()를 넘긴다")

E_body = _fn_body("def api_defect_photos_upload(")
chk('uploader = session.get("admin_name") or portal_actor() or "-"' in E_body,
    "E ★★★ api_defect_photos_upload 가 admin_name 다음으로 portal_actor()를 쓴다")

chk("def _create_case(conn, iid, iname, d, source, actor_name=None):" in APP_SRC,
    "F ★★★ _create_case 가 actor_name(기본값 None→iname) 파라미터를 받는다")
chk('DB.log(conn, actor_name, f"사건 등록({source}·사진없음)"' in APP_SRC,
    "F ★★★ _create_case 의 사진없음 분기 DB.log 가 actor_name 을 쓴다")
chk('DB.log(conn, actor_name, f"사건 등록({source})"' in APP_SRC,
    "F ★★★ _create_case 의 공고오픈 분기 DB.log 가 actor_name 을 쓴다")
chk('res = _create_case(conn, iid, me["name"], d, "포털", actor_name=portal_actor())' in APP_SRC,
    "F ★★★ api_insurer_case_create(포털) 가 actor_name=portal_actor() 로 넘긴다")
chk('res = _create_case(conn, ins["id"], ins["name"], d, "API")' in APP_SRC,
    "F ★ v1 API-key 호출부는 그대로다(actor_name 생략 — 세션이 없어 개인 특정 불가)")

G_body = _fn_body("def api_insurer_co_ack(")
chk("(ack, portal_actor() or \"보험사\", note," in G_body,
    "G ★★★ api_insurer_co_ack 가 insurer_ack_by 를 portal_actor()로 남긴다")

H_body = _fn_body("def api_partner_upload_photos(")
chk("(cid, pid, portal_actor(), \"협력사\", info[\"rel_path\"], info[\"orig_name\"]," in H_body,
    "H ★★★ api_partner_upload_photos 가 uploader 로 portal_actor()를 넘긴다")

# ============================================================
print("\n[2] 실행 준비 — 실제 app.py(전체 임포트) + 보험사/협력사 각 하위계정 2명")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round141_")
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
                 "VALUES('admin','x','검증관리자','최고관리자')")
    iid = conn.execute(
        "INSERT INTO insurers(name,org_type,status,fee_rate_bp) "
        "VALUES('R141보험','손해보험','활성',900)").lastrowid
    i_sub1 = conn.execute(
        "INSERT INTO portal_users(org_type,org_id,login_id,password_hash,name,role,status) "
        "VALUES('insurer',?,?,'x','김대리','중간관리자','활성')", (iid, "r141i_kim")).lastrowid
    i_sub2 = conn.execute(
        "INSERT INTO portal_users(org_type,org_id,login_id,password_hash,name,role,status) "
        "VALUES('insurer',?,?,'x','박대리','중간관리자','활성')", (iid, "r141i_park")).lastrowid

    pid_org = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,phone,login_id) "
        "VALUES('R141업체','시공사','활성','가드레일','서울','01099990000','r141p_org')").lastrowid
    p_sub1 = conn.execute(
        "INSERT INTO portal_users(org_type,org_id,login_id,password_hash,name,role,status) "
        "VALUES('partner',?,?,'x','이과장','중간관리자','활성')", (pid_org, "r141p_lee")).lastrowid
    p_sub2 = conn.execute(
        "INSERT INTO portal_users(org_type,org_id,login_id,password_hash,name,role,status) "
        "VALUES('partner',?,?,'x','최과장','중간관리자','활성')", (pid_org, "r141p_choi")).lastrowid
    conn.commit()

    def _jpeg_bytes(color):
        """진짜로 디코드 가능한 최소 JPEG — photo_ai._strip_exif 의 Image.load()가
        엉성한 매직바이트 문자열은 OSError로 거부한다(EXIF 제거가 실제 픽셀
        디코드까지 강제한다). 실측: round117류 테스트의 가짜 바이트는 그 라우트
        에서도 저장 실패(errors)였는데 status_code만 확인해 조용히 넘어갔다."""
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (4, 4), color).save(buf, format="JPEG")
        return buf.getvalue()

    client = A.app.test_client()

    def _as_insurer(sub_id, login_id):
        tok = f"r141i-csrf-{sub_id}"
        with client.session_transaction() as sess:
            sess.clear()
            sess["insurer_id"] = iid
            sess["insurer_name"] = "R141보험"          # 하위계정 전원 동일(조직명) — 고의로 재현
            sess["insurer_login"] = login_id
            sess["portal_sub_id"] = sub_id
            sess["portal_role"] = "중간관리자"
            sess["pw_role"] = "insurer"
            sess["_csrf"] = tok
        return {"X-CSRF-Token": tok}

    def _as_partner(sub_id, login_id):
        tok = f"r141p-csrf-{sub_id}"
        with client.session_transaction() as sess:
            sess.clear()
            sess["partner_id"] = pid_org
            sess["partner_name"] = "R141업체"          # 하위계정 전원 동일(조직명)
            sess["partner_login"] = login_id
            sess["portal_sub_id"] = sub_id
            sess["portal_role"] = "중간관리자"
            sess["pw_role"] = "partner"
            sess["_csrf"] = tok
        return {"X-CSRF-Token": tok}

    def _as_admin():
        tok = "r141-admin-csrf"
        with client.session_transaction() as sess:
            sess.clear()
            sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증관리자"
            sess["_csrf"] = tok
        return {"X-CSRF-Token": tok}

    EXP_KIM = "R141보험(r141i_kim)"
    EXP_PARK = "R141보험(r141i_park)"
    EXP_LEE = "R141업체(r141p_lee)"
    EXP_CHOI = "R141업체(r141p_choi)"

    # ── A/B: 사건 하나로 두 하위계정이 순차 확정 — human_severity_by/est_ack_by 비교 ──
    cid_ab = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
        "VALUES('R141-AB','입찰중','가드레일','서울',?,0)", (iid,)).lastrowid
    conn.commit()

    hdr = _as_insurer(i_sub1, "r141i_kim")
    r = client.post(f"/api/insurer/cases/{cid_ab}/severity", json={"severity": "경미"}, headers=hdr)
    chk(r.status_code == 200, "A STEP 하위계정1(김대리) 파손정도 확정 200", (r.status_code, r.get_data(as_text=True)))
    by1 = conn.execute("SELECT human_severity_by FROM cases WHERE id=?", (cid_ab,)).fetchone()["human_severity_by"]

    hdr = _as_insurer(i_sub2, "r141i_park")
    r = client.post(f"/api/insurer/cases/{cid_ab}/severity", json={"severity": "보통"}, headers=hdr)
    chk(r.status_code == 200, "A STEP 하위계정2(박대리) 파손정도 확정 200", (r.status_code, r.get_data(as_text=True)))
    by2 = conn.execute("SELECT human_severity_by FROM cases WHERE id=?", (cid_ab,)).fetchone()["human_severity_by"]
    chk(by1 == EXP_KIM and by2 == EXP_PARK and by1 != by2,
        "A ★★★ human_severity_by 가 하위계정별로 로그인아이디까지 구분된다", (by1, by2))

    #  photo_count=0 이라 _est_basis 는 항상 "사진없음"(≠정상) — est-ack 전제조건이 자동 충족된다
    hdr = _as_insurer(i_sub1, "r141i_kim")
    r = client.post(f"/api/insurer/cases/{cid_ab}/est-ack", json={"reason": "확인"}, headers=hdr)
    chk(r.status_code == 200, "B STEP 하위계정1(김대리) 가견적 확인 200", (r.status_code, r.get_data(as_text=True)))
    eby1 = conn.execute("SELECT est_ack_by FROM cases WHERE id=?", (cid_ab,)).fetchone()["est_ack_by"]

    hdr = _as_insurer(i_sub2, "r141i_park")
    r = client.post(f"/api/insurer/cases/{cid_ab}/est-ack", json={"reason": "재확인"}, headers=hdr)
    chk(r.status_code == 200, "B STEP 하위계정2(박대리) 가견적 확인 200", (r.status_code, r.get_data(as_text=True)))
    eby2 = conn.execute("SELECT est_ack_by FROM cases WHERE id=?", (cid_ab,)).fetchone()["est_ack_by"]
    chk(eby1 == EXP_KIM and eby2 == EXP_PARK and eby1 != eby2,
        "B ★★★ est_ack_by 가 하위계정별로 로그인아이디까지 구분된다", (eby1, eby2))

    # ── G: change_order 하나로 두 하위계정이 순차 확인 — insurer_ack_by 비교 ──
    coid = conn.execute(
        "INSERT INTO change_orders(case_id,status,combined_amount,created_at) "
        "VALUES(?,?,?,?)", (cid_ab, "실사요청", 5000000, DB.now())).lastrowid
    conn.commit()

    hdr = _as_insurer(i_sub1, "r141i_kim")
    r = client.post(f"/api/insurer/change-orders/{coid}/ack", json={"ack": True}, headers=hdr)
    chk(r.status_code == 200, "G STEP 하위계정1(김대리) 추가공사 확인 200", (r.status_code, r.get_data(as_text=True)))
    cby1 = conn.execute("SELECT insurer_ack_by FROM change_orders WHERE id=?", (coid,)).fetchone()["insurer_ack_by"]

    hdr = _as_insurer(i_sub2, "r141i_park")
    r = client.post(f"/api/insurer/change-orders/{coid}/ack", json={"ack": True}, headers=hdr)
    chk(r.status_code == 200, "G STEP 하위계정2(박대리) 추가공사 확인 200", (r.status_code, r.get_data(as_text=True)))
    cby2 = conn.execute("SELECT insurer_ack_by FROM change_orders WHERE id=?", (coid,)).fetchone()["insurer_ack_by"]
    chk(cby1 == EXP_KIM and cby2 == EXP_PARK and cby1 != cby2,
        "G ★★★ insurer_ack_by 가 하위계정별로 로그인아이디까지 구분된다", (cby1, cby2))

    # ── D: 보험사 피해사진 업로드 — 사건 하나에 두 하위계정이 순차 업로드 ──
    cid_d = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
        "VALUES('R141-D','입찰중','가드레일','서울',?,0)", (iid,)).lastrowid
    conn.commit()
    hdr = _as_insurer(i_sub1, "r141i_kim")
    img1 = (io.BytesIO(_jpeg_bytes((200, 30, 30))), "d1.jpg")
    r = client.post(f"/api/insurer/cases/{cid_d}/photos", headers=hdr,
                     data={"photos": [img1]}, content_type="multipart/form-data")
    chk(r.status_code == 200 and r.get_json().get("count") == 1,
        "D STEP 하위계정1(김대리) 피해사진 업로드 성공(count=1)", (r.status_code, r.get_data(as_text=True)))
    hdr = _as_insurer(i_sub2, "r141i_park")
    img2 = (io.BytesIO(_jpeg_bytes((30, 200, 30))), "d2.jpg")
    r = client.post(f"/api/insurer/cases/{cid_d}/photos", headers=hdr,
                     data={"photos": [img2]}, content_type="multipart/form-data")
    chk(r.status_code == 200 and r.get_json().get("count") == 1,
        "D STEP 하위계정2(박대리) 피해사진 업로드 성공(count=1)", (r.status_code, r.get_data(as_text=True)))
    uploaders_d = [r["uploader"] for r in conn.execute(
        "SELECT uploader FROM photos WHERE case_id=? ORDER BY id", (cid_d,)).fetchall()]
    chk(uploaders_d == [EXP_KIM, EXP_PARK],
        "D ★★★ 보험사 피해사진 photos.uploader 가 하위계정별로 구분된다", uploaders_d)

    # ── H: 협력사 시공사진 업로드 — 사건 하나에 두 하위계정이 순차 업로드 ──
    cid_h = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,is_demo) "
        "VALUES('R141-H','시공중','가드레일','서울',?,0)", (pid_org,)).lastrowid
    conn.commit()
    hdr = _as_partner(p_sub1, "r141p_lee")
    img3 = (io.BytesIO(_jpeg_bytes((30, 30, 200))), "h1.jpg")
    r = client.post(f"/api/partner/cases/{cid_h}/photos", headers=hdr,
                     data={"photos": [img3]}, content_type="multipart/form-data")
    chk(r.status_code == 200 and r.get_json().get("count") == 1,
        "H STEP 하위계정1(이과장) 시공사진 업로드 성공(count=1)", (r.status_code, r.get_data(as_text=True)))
    hdr = _as_partner(p_sub2, "r141p_choi")
    img4 = (io.BytesIO(_jpeg_bytes((200, 200, 30))), "h2.jpg")
    r = client.post(f"/api/partner/cases/{cid_h}/photos", headers=hdr,
                     data={"photos": [img4]}, content_type="multipart/form-data")
    chk(r.status_code == 200 and r.get_json().get("count") == 1,
        "H STEP 하위계정2(최과장) 시공사진 업로드 성공(count=1)", (r.status_code, r.get_data(as_text=True)))
    uploaders_h = [r["uploader"] for r in conn.execute(
        "SELECT uploader FROM photos WHERE case_id=? ORDER BY id", (cid_h,)).fetchall()]
    chk(uploaders_h == [EXP_LEE, EXP_CHOI],
        "H ★★★ 협력사 시공사진 photos.uploader 가 하위계정별로 구분된다", uploaders_h)

    # ── C: 하자 접수 — 보험사 하위계정 2명 + 어드민(회귀안전) ──
    cid_c = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
        "VALUES('R141-C','완료','가드레일','서울',?,0)", (iid,)).lastrowid
    conn.commit()
    hdr = _as_insurer(i_sub1, "r141i_kim")
    r = client.post("/api/defects", json={"case_id": cid_c, "title": "김대리 접수"}, headers=hdr)
    chk(r.status_code == 200, "C STEP 하위계정1(김대리) 하자 접수 200", (r.status_code, r.get_data(as_text=True)))
    did1 = r.get_json()["id"]
    hdr = _as_insurer(i_sub2, "r141i_park")
    r = client.post("/api/defects", json={"case_id": cid_c, "title": "박대리 접수"}, headers=hdr)
    chk(r.status_code == 200, "C STEP 하위계정2(박대리) 하자 접수 200", (r.status_code, r.get_data(as_text=True)))
    did2 = r.get_json()["id"]
    rep1 = conn.execute("SELECT reporter FROM defects WHERE id=?", (did1,)).fetchone()["reporter"]
    rep2 = conn.execute("SELECT reporter FROM defects WHERE id=?", (did2,)).fetchone()["reporter"]
    chk(rep1 == EXP_KIM and rep2 == EXP_PARK and rep1 != rep2,
        "C ★★★ defects.reporter 가 보험사 하위계정별로 구분된다", (rep1, rep2))

    hdr = _as_admin()
    r = client.post("/api/defects", json={"case_id": cid_c, "title": "어드민 접수"}, headers=hdr)
    chk(r.status_code == 200, "C STEP 어드민 하자 접수 200(회귀 안전)", (r.status_code, r.get_data(as_text=True)))
    did3 = r.get_json()["id"]
    rep3 = conn.execute("SELECT reporter FROM defects WHERE id=?", (did3,)).fetchone()["reporter"]
    #  [라운드170] actor() 자체가 admin_name 뒤에 로그인 계정을 덧붙이도록 바뀌었다
    #  (admins.name 은 유일성 제약이 없어 감사로그 행위자를 위조할 수 있었다) —
    #  portal_actor(actor()) 의 admin 폴백 경로는 그 값을 그대로 받아쓸 뿐이라
    #  형태만 바뀌었고, "포털 로그인ID를 안 붙인다"는 이 체크의 취지는 그대로다.
    chk(rep3 == "검증관리자(admin)",
        "C ★ 어드민 경로는 그대로 actor() 를 쓴다(portal_actor 폴백이 admin 경로를 안 건드린다)", rep3)

    # ── E: 하자 사진 첨부 — 보험사·협력사 하위계정이 같은 하자에 순차 업로드 ──
    did_e = conn.execute(
        "INSERT INTO defects(defect_no,case_id,insurer_id,partner_id,title,status,is_demo) "
        "VALUES('D26-R141E',?,?,?,'검증용',?,0)", (cid_h, iid, pid_org, "접수")).lastrowid
    conn.commit()
    hdr = _as_insurer(i_sub1, "r141i_kim")
    imge1 = (io.BytesIO(_jpeg_bytes((10, 10, 10))), "e1.jpg")
    r = client.post(f"/api/defects/{did_e}/photos", headers=hdr,
                     data={"photos": [imge1]}, content_type="multipart/form-data")
    chk(r.status_code == 200 and r.get_json().get("count") == 1,
        "E STEP 보험사 하위계정(김대리) 하자사진 첨부 성공(count=1)",
        (r.status_code, r.get_data(as_text=True)))
    hdr = _as_partner(p_sub1, "r141p_lee")
    imge2 = (io.BytesIO(_jpeg_bytes((20, 20, 20))), "e2.jpg")
    r = client.post(f"/api/defects/{did_e}/photos", headers=hdr,
                     data={"photos": [imge2]}, content_type="multipart/form-data")
    chk(r.status_code == 200 and r.get_json().get("count") == 1,
        "E STEP 협력사 하위계정(이과장) 하자사진 첨부 성공(count=1)",
        (r.status_code, r.get_data(as_text=True)))
    uploaders_e = [r["uploader"] for r in conn.execute(
        "SELECT uploader FROM photos WHERE defect_id=? ORDER BY id", (did_e,)).fetchall()]
    chk(uploaders_e == [EXP_KIM, EXP_LEE],
        "E ★★★ 하자사진 photos.uploader 가 보험사·협력사 하위계정 모두 구분된다", uploaders_e)

    # ── F: 사건 등록(포털) — 하위계정 2명이 각각 등록 ──
    hdr = _as_insurer(i_sub1, "r141i_kim")
    r = client.post("/api/insurer/cases", json={"category": "가드레일·방호울타리", "no_photo": True}, headers=hdr)
    chk(r.status_code == 200, "F STEP 하위계정1(김대리) 사건 등록 200", (r.status_code, r.get_data(as_text=True)))
    case_no1 = r.get_json()["case_no"]
    hdr = _as_insurer(i_sub2, "r141i_park")
    r = client.post("/api/insurer/cases", json={"category": "가드레일·방호울타리", "no_photo": True}, headers=hdr)
    chk(r.status_code == 200, "F STEP 하위계정2(박대리) 사건 등록 200", (r.status_code, r.get_data(as_text=True)))
    case_no2 = r.get_json()["case_no"]
    log1 = conn.execute(
        "SELECT actor FROM activity_log WHERE action LIKE '사건 등록%' AND detail LIKE ? ",
        (f"{case_no1}%",)).fetchone()["actor"]
    log2 = conn.execute(
        "SELECT actor FROM activity_log WHERE action LIKE '사건 등록%' AND detail LIKE ? ",
        (f"{case_no2}%",)).fetchone()["actor"]
    chk(log1 == EXP_KIM and log2 == EXP_PARK and log1 != log2,
        "F ★★★ 사건 등록(포털) activity_log.actor 가 하위계정별로 구분된다", (log1, log2))

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드141 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
