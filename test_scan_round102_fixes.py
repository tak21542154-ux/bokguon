# -*- coding: utf-8 -*-
"""스캔 102라운드 회귀 — 협력사 증거사진 없이 완료보고·정산이 통과하던 결함.

  [1] (치명) 보험사·운영자가 사건 등록 시 첨부하는 피해사진(_upload_damage_photos)은
      kind='착공전'·review_status='승인'으로 들어간다(참고자료라 검수게이트를
      막지 않도록 하는 **의도된** 설계). 그런데 완료보고 관문(api_partner_complete,
      "사진 한 장 없이 완료 보고가 되면 안 된다")과 정산 관문(api_case_approve,
      "사진 검수 = 정산의 필수 관문")이 이 사진의 **출처(uploader_role)를 안 보고
      그대로 세어**, 협력사 자신의 시공 증거가 0장이어도 두 관문을 다 통과했다.
      하자보증 기산점이 박히고 돈이 나가는데 시공 증거가 없다.
  [2] 정산 CSV 내보내기(api_settlements_export)에 WHERE 절이 아예 없어 화면
      검색·기간 필터와 무관하게 항상 전체 이력을 뽑았다. 이 정확한 SELECT(별칭
      s./c.)를 위해 이미 만들어져 있던 _settle_filter 를 그저 아무도 부르지
      않고 있었다 — 연결만 이었다.

      python test_scan_round102_fixes.py
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


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("═" * 72)
print("  스캔 102라운드 회귀 — 협력사 증거사진 무시된 완료보고·정산 관문, 정산CSV 필터누락")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 두 관문·CSV 필터 모두 확인")
# ──────────────────────────────────────────────────────────────
comp_body = _py_fn_body(APP_SRC, "api_partner_complete")
chk("AND uploader_role='협력사'" in comp_body,
    "★★★ 완료보고 관문의 사진 카운트가 협력사 업로드만 본다")
appr_body = _py_fn_body(APP_SRC, "api_case_approve")
chk("AND uploader_role='협력사'" in appr_body,
    "★★★ 정산 관문의 사진 카운트가 협력사 업로드만 본다")
exp_body = _py_fn_body(APP_SRC, "api_settlements_export")
chk("_settle_filter(request.args)" in exp_body,
    "★★ 정산 CSV 내보내기가 _settle_filter 로 조건을 건다")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[3] 실행 — 실제 시나리오를 돌린다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round102_")
_dbpath = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_DB_PATH"] = _dbpath
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
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R102업체','시행사','활성')").lastrowid
    iid = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('R102보험','활성')").lastrowid

    # ── [2] 완료보고 — 보험사 피해사진만 있으면 막히고, 협력사 사진이 있으면 통과 ──
    cid1 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,insurer_id,is_demo) "
        "VALUES('R102-C1','시공중','가드레일','서울',?,?,0)", (pid, iid)).lastrowid
    conn.execute(  # _upload_damage_photos 와 정확히 같은 모양(보험사 피해사진)
        "INSERT INTO photos(case_id,partner_id,uploader,uploader_role,rel_path,orig_name,"
        "                   mime,ext,size,sha256,kind,review_status,reviewed_by,reviewed_at,created_at) "
        "VALUES(?,NULL,'R102보험','보험사','x.jpg','x.jpg','image/jpeg','jpg',1,'sha1',"
        "       '착공전','승인','보험사 등록',?,?)", (cid1, DB.now(), DB.now()))
    conn.commit()

    partner_c = A.app.test_client()
    _tok = "r102-partner-csrf"
    with partner_c.session_transaction() as sess:
        sess["partner_id"] = pid; sess["partner_name"] = "R102업체"; sess["_csrf"] = _tok
    _phdr = {"X-CSRF-Token": _tok}

    r1 = partner_c.post(f"/api/partner/cases/{cid1}/complete", headers=_phdr, json={})
    chk(r1.status_code == 409 and r1.get_json().get("code") == "NO_PHOTO",
        "★★★ 협력사 사진이 0장이면 보험사 피해사진만 있어도 완료보고가 막힌다"
        "(예전엔 이 사진 1장으로 통과 — 하자보증 기산점이 증거 없이 박혔다)",
        (r1.status_code, r1.get_json()))

    conn.execute(  # 이제 진짜 협력사 시공사진을 올린다
        "INSERT INTO photos(case_id,partner_id,uploader,uploader_role,rel_path,orig_name,"
        "                   mime,ext,size,sha256,kind,review_status,created_at) "
        "VALUES(?,?,'R102업체','협력사','y.jpg','y.jpg','image/jpeg','jpg',1,'sha2',"
        "       '시공중','대기',?)", (cid1, pid, DB.now()))
    conn.commit()
    r1b = partner_c.post(f"/api/partner/cases/{cid1}/complete", headers=_phdr, json={})
    chk(r1b.status_code == 200,
        "STEP 협력사 사진이 생기면 정상적으로 완료보고가 통과한다(과잉차단 아님)",
        (r1b.status_code, r1b.get_data(as_text=True)[:200]))

    # ── [3] 정산 승인 — 보험사 피해사진만 있으면 막히고, 협력사 사진이 있으면 통과 ──
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,insurer_id,"
        "                  award_amount,completed_at,is_demo) "
        "VALUES('R102-C2','검수대기','가드레일','서울',?,?,3000000,?,0)",
        (pid, iid, DB.now())).lastrowid
    conn.execute(
        "INSERT INTO photos(case_id,partner_id,uploader,uploader_role,rel_path,orig_name,"
        "                   mime,ext,size,sha256,kind,review_status,reviewed_by,reviewed_at,created_at) "
        "VALUES(?,NULL,'R102보험','보험사','z.jpg','z.jpg','image/jpeg','jpg',1,'sha3',"
        "       '착공전','승인','보험사 등록',?,?)", (cid2, DB.now(), DB.now()))
    conn.commit()

    admin = A.app.test_client()
    _atok = "r102-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _atok
    _ahdr = {"X-CSRF-Token": _atok}

    r2 = admin.post(f"/api/cases/{cid2}/approve", headers=_ahdr, json={})
    chk(r2.status_code == 409 and r2.get_json().get("code") == "NO_PHOTO",
        "★★★ 협력사 사진이 0장이면 보험사 피해사진만 있어도 정산 승인이 막힌다"
        "(예전엔 이 사진 1장으로 total=1·approved=1 이 되어 그대로 정산이 생성됐다)",
        (r2.status_code, r2.get_json()))

    conn.execute(
        "INSERT INTO photos(case_id,partner_id,uploader,uploader_role,rel_path,orig_name,"
        "                   mime,ext,size,sha256,kind,review_status,created_at) "
        "VALUES(?,?,'R102업체','협력사','w.jpg','w.jpg','image/jpeg','jpg',1,'sha4',"
        "       '완료','승인',?)", (cid2, pid, DB.now()))
    conn.commit()
    r2b = admin.post(f"/api/cases/{cid2}/approve", headers=_ahdr, json={})
    chk(r2b.status_code == 200,
        "STEP 협력사 사진이(검수승인) 있으면 정상적으로 정산 승인이 통과한다(과잉차단 아님)",
        (r2b.status_code, r2b.get_data(as_text=True)[:200]))

    # ── [4] 정산 CSV — 검색어로 좁힌 조건이 CSV 에도 그대로 걸린다 ──────────
    iid2 = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('R102다른보험',   '활성')").lastrowid
    conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_name,amount,fee,payout,"
        "                        created_at) VALUES(?,?,?,?,3000000,300000,2700000,?)",
        (cid2, "R102-C2", "R102보험", "R102업체", DB.now()))
    cid3 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
        "VALUES('R102-C3','완료','가드레일','서울',?,0)", (iid2,)).lastrowid
    conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_name,amount,fee,payout,"
        "                        created_at) VALUES(?,?,?,?,1000000,100000,900000,?)",
        (cid3, "R102-C3", "R102다른보험", "다른업체", DB.now()))
    conn.commit()

    r3 = admin.get("/api/settlements/export?q=R102-C2", headers=_ahdr)
    chk(r3.status_code == 200, "STEP CSV 내보내기 자체는 200 이다", r3.status_code)
    if r3.status_code == 200:
        body_txt = r3.get_data(as_text=True)
        chk("R102-C2" in body_txt and "R102-C3" not in body_txt,
            "★★★ 검색어(q=R102-C2)로 좁힌 조건이 CSV 에도 그대로 걸린다"
            "(예전엔 WHERE 절 자체가 없어 조건과 무관하게 전체가 나갔다)",
            body_txt[:300])

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드102 서버측 준비/실행", f"{type(e).__name__} {e}")
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
