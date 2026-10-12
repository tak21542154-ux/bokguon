# -*- coding: utf-8 -*-
"""스캔 60라운드 회귀 — 하자 사진 열람 IDOR 비대칭(MEDIUM) + 업체 강등 관문에
   열린 하자가 안 걸리는 사각지대(MEDIUM).

  조사 에이전트가 정적 추적(직접 실행 없이 SQL·컬럼 목록 전수 대조)으로 짚고,
  이번 라운드에서 실측(실제 test_client + 실제 DB)으로 재확인한 결함:

  ① _photo_visible_to() 와 _defect_visible_to() 가 같은 하자에 대해 서로 다른
     컬럼으로 권한을 판정했다 — 하자 자체(목록·업로드)는 defects.partner_id 로
     열어 주는데, 정작 그 사진의 원본 바이트 조회(api_photo_file)는
     cases.partner_id 로만 열었다(+ defect_photos 조인은 접수 시점에 '지목'한
     사진만 잡고, 그 뒤 api_defect_photos_upload 로 직접 올린 사진은 못 잡는다).
     전체재경매로 cases.partner_id 만 바뀌고 defects.partner_id 는 그대로 남는
     정상 절차가 있어(원업체가 완료보고 전 교체되는 경우), 그 직후엔 원업체가
     자기가 방금 올린 하자보수 증빙사진조차 못 본다.
  ② 업체를 '퇴출'/'경고'로 내릴 때 걸리는 것을 미리 보여주는 관문
     (_partner_exit_load/_partner_demote_gate)이 진행 사건·미지급 정산만 보고
     열린 하자는 아예 안 봤다. 하자는 사건 status 를 안 건드리는 설계라 애초에
     active_cases 조건에 걸리지 않고, 정산도 하자가 나기 전에 이미 완료됐을 수
     있어 unpaid_count 도 0 이 된다 — 그러면 관문이 조용히 통과되어, 담당 바꿀
     방법이 없는(admin 하자수정은 partner_id 를 못 바꾼다) 하자가 잠긴 계정
     뒤에 방치된다.

      python test_scan_round60_fixes.py
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
JS_SRC = read(os.path.join("static", "admin.js"))

print("═" * 72)
print("  스캔 60라운드 회귀 — 하자사진 열람 IDOR 비대칭 + 업체강등 하자 사각지대")
print("═" * 72)


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
photo_vis_body = _body(APP_SRC, "_photo_visible_to")
chk('photo.get("defect_id")' in photo_vis_body
    and 'SELECT 1 x FROM defects WHERE id=? AND partner_id=?' in photo_vis_body,
    "★★★ ① _photo_visible_to — 하자에 직접 달린 사진(defect_id)도 하자 담당자에게 열린다"
    "(고치기 전엔 defect_photos 조인 하나뿐이라 새로 올린 사진은 못 잡았다)")

exit_load_body = _body(APP_SRC, "_partner_exit_load")
chk("FROM defects" in exit_load_body and '"open_defect_count"' in exit_load_body,
    "★★★ ② _partner_exit_load — 열린 하자도 함께 센다(고치기 전엔 아예 안 봤다)")

demote_gate_body = _body(APP_SRC, "_partner_demote_gate")
chk('not info["open_defect_count"]' in demote_gate_body,
    "★★★ ② _partner_demote_gate — 열린 하자가 있으면 관문이 막는다")

chk("open_defect_count" in JS_SRC and "open_defects" in JS_SRC,
    "★ ② admin.js — 강등 확인창이 열린 하자를 보여준다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 서버(test_client)로 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round60_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    client = A.app.test_client()
    _tok = "regress-round60-csrf-token"
    _hdr = {"X-CSRF-Token": _tok}

    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('검증보험사60','활성')").lastrowid
    p_x = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('원업체X60','시공사','활성')"
    ).lastrowid
    p_y = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('교체업체Y60','시공사','활성')"
    ).lastrowid
    p_z = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('무관업체Z60','시공사','활성')"
    ).lastrowid
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                "VALUES('admin60','x','검증','중간관리자')")
    conn.commit(); conn.close()

    def _admin_sess(sess):
        sess["admin"] = "admin60"; sess["admin_role"] = "중간관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = _tok

    # ══════════════════════════════════════════════════════════
    print("\n  ① 하자 사진 열람 IDOR 비대칭")
    # ──────────────────────────────────────────────────────────
    conn = DB.get_db()
    #  원업체 X 가 시공중이던 사건 — 완료보고 전이라 전체재경매로 교체가 정상 절차다
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,partner_id,partner_name,category,region) "
        "VALUES(?,'시공중',?,?,?,?,?,'서울')",
        ("60P-0001", "검증보험사60", iid, p_x, "원업체X60", "누수·배관·설비")).lastrowid
    did = conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,insurer,insurer_id,partner_id,partner_name,"
        "                    title,status,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,datetime('now','+9 hours'))",
        ("D26-6001", cid, "60P-0001", "검증보험사60", iid, p_x, "원업체X60",
         "누수 재발", "접수")).lastrowid
    #  X 가 api_defect_photos_upload 로 직접 올린 하자보수 증빙사진과 같은 모양으로 심는다
    #  (partner_id 컬럼은 실제 업로드 라우트도 안 채운다 — 그대로 재현)
    _relname = "round60_evidence.jpg"
    _updir = os.environ["BOKGUON_UPLOAD_DIR"]
    os.makedirs(_updir, exist_ok=True)
    with open(os.path.join(_updir, _relname), "wb") as _f:
        _f.write(b"\xff\xd8\xff\xe0" + b"0" * 100)     # JPEG 시그니처 + 더미 바이트
    pid_photo = conn.execute(
        "INSERT INTO photos(case_id,defect_id,fix_for,uploader,uploader_role,rel_path,orig_name,"
        "                   mime,ext,size,sha256,kind,review_status,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now','+9 hours'))",
        (cid, did, None, "원업체X60", "협력사", _relname, "evidence.jpg",
         "image/jpeg", "jpg", 104, "deadbeef60", "하자보수", "승인")).lastrowid
    #  전체재경매로 원업체 교체 — defects.partner_id 는 그대로, cases.partner_id 만 바뀐다
    conn.execute("UPDATE cases SET partner_id=?, partner_name=? WHERE id=?",
                 (p_y, "교체업체Y60", cid))
    conn.commit(); conn.close()

    with client.session_transaction() as sess:
        sess["partner_id"] = p_x; sess["_csrf"] = _tok
    r_x = client.get(f"/api/photos/{pid_photo}/file")
    chk(r_x.status_code == 200,
        "★★★ ① 교체된 원업체 X 가 자기가 올린 하자보수 증빙사진을 여전히 볼 수 있다"
        "(고치기 전엔 403 — cases.partner_id 가 이미 Y 로 바뀌어 있었다)",
        (r_x.status_code, r_x.get_json() if r_x.status_code != 200 else None))

    with client.session_transaction() as sess:
        sess["partner_id"] = p_z; sess["_csrf"] = _tok
    r_z = client.get(f"/api/photos/{pid_photo}/file")
    chk(r_z.status_code == 403,
        "★ 대조군 — 이 하자·사건과 무관한 업체 Z 는 여전히 403 이다(과잉허용 아님)",
        r_z.status_code)

    # ══════════════════════════════════════════════════════════
    print("\n  ② 업체 강등 관문 — 열린 하자 사각지대")
    # ──────────────────────────────────────────────────────────
    conn = DB.get_db()
    p_w = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('하자보유업체W60','시공사','활성')"
    ).lastrowid
    #  진행 사건도 없고(이미 완료), 미지급 정산도 없는(이미 이체완료) 상태에서
    #  하자만 열려 있는 경우 — 옛 관문은 두 조건 다 통과해 조용히 강등을 허용했다.
    cid_w = conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,partner_id,partner_name,category,region) "
        "VALUES(?,'완료',?,?,?,?,?,'서울')",
        ("60W-0001", "검증보험사60", iid, p_w, "하자보유업체W60", "누수·배관·설비")).lastrowid
    conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,insurer,insurer_id,partner_id,partner_name,"
        "                    title,status,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,datetime('now','+9 hours'))",
        ("D26-6002", cid_w, "60W-0001", "검증보험사60", iid, p_w, "하자보유업체W60",
         "타일 들뜸", "접수"))
    #  대조군 — 아무 것도 안 걸린 진짜 깨끗한 업체
    p_v = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('깨끗한업체V60','시공사','활성')"
    ).lastrowid
    conn.commit(); conn.close()

    with client.session_transaction() as sess:
        _admin_sess(sess)

    rw1 = client.patch(f"/api/partners/{p_w}",
                       json={"status": "경고", "status_reason": "검증용 사유 오십자"},
                       headers=_hdr)
    chk(rw1.status_code == 409,
        "★★★ ② 진행사건·미지급 둘 다 없어도 열린 하자가 있으면 강등이 막힌다"
        "(고치기 전엔 두 조건만 보고 조용히 통과시켰다)",
        (rw1.status_code, rw1.get_json()))
    dw1 = rw1.get_json() or {}
    chk(dw1.get("code") == "PARTNER_HAS_WORK" and dw1.get("open_defect_count", 0) >= 1,
        "★★ ② 막힌 응답이 open_defect_count 를 실제로 담아 온다", dw1)

    rw2 = client.patch(f"/api/partners/{p_w}",
                       json={"status": "경고", "status_reason": "검증용 사유 오십자",
                             "confirm_demote": True},
                       headers=_hdr)
    chk(rw2.status_code == 200,
        "★ confirm_demote=True 로 다시 보내면 그래도 진행된다(강제 차단이 아니라 확인 관문)",
        (rw2.status_code, rw2.get_json()))

    rv1 = client.patch(f"/api/partners/{p_v}",
                       json={"status": "경고", "status_reason": "검증용 사유 오십자"},
                       headers=_hdr)
    chk(rv1.status_code == 200,
        "★ 대조군 — 진행사건·미지급·열린하자 전부 없는 업체는 확인 없이 바로 강등된다"
        "(과잉차단 아님)", (rv1.status_code, rv1.get_json()))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드60 실측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
