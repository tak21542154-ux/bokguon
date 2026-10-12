# -*- coding: utf-8 -*-
"""스캔 73라운드 회귀 — 2차 경매 개시 시 미분류 사진 일괄분류가 uploader_role='운영자'
   (전화·팩스 접수 대신 등록) 사진을 화이트리스트에서 빠뜨리고, 로그도 실제
   반영 건수가 아니라 후보 전체 수를 그대로 찍었다.

  api_case_open_auction 의 일괄 분류 UPDATE 가
  COALESCE(uploader_role,'') IN ('협력사','보험사','관리자') 로만 걸렀는데,
  전화·팩스 접수를 대신 올리는 관리자 경로(api_admin_upload_damage_photos →
  _upload_damage_photos)는 uploader_role='운영자'로 적는다. AI 미연동
  배포에서는 담당자가 사진을 손으로 재분류하는 게 정상 경로이고, 그 재분류가
  '기타'를 고르면 이 사진은 이 일괄분류에서 영영 안 걸린다 — 입찰자에게는
  계속 닫힌 채로 남는데(_photo_visible_to 는 CONSTRUCTION_KINDS 만 연다) 활동
  로그는 "{후보 전체 수}장 → 착공전"이라고 실제와 다르게 남겼다(실제 반영
  건수가 아니라 후보 전체 수를 그대로 씀).

      python test_scan_round73_fixes.py
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

print("═" * 72)
print("  스캔 73라운드 회귀 — 2차 경매 개시 미분류사진 일괄분류 화이트리스트 누락·로그부정확")
print("═" * 72)


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
body = _body(APP_SRC, "api_case_open_auction")
chk("IN ('협력사','보험사','관리자','운영자')" in body,
    "★★ 일괄분류 화이트리스트에 '운영자'(전화·팩스 대신접수 경로)가 추가됐다")
chk("nphoto = _cur.rowcount" in body,
    "★★ 로그 건수가 후보 전체 수가 아니라 실제 UPDATE 반영 건수(rowcount)다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 서버 호출로 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round73_")
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
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,est_price) "
        "VALUES('R73-01','접수','가드레일','서울',1000000)").lastrowid
    #  전화접수 대신등록(uploader_role='운영자') 뒤 담당자가 '기타'로 재분류한 사진
    p_admin = conn.execute(
        "INSERT INTO photos(case_id,uploader,uploader_role,rel_path,mime,ext,size,sha256,kind,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (cid, "김운영", "운영자", "a.jpg", "image/jpeg", "jpg", 100, "sha-a", "기타", DB.now())).lastrowid
    #  협력사가 올린 정상 미분류 사진(대조군 — 이미 화이트리스트에 있던 값)
    p_partner = conn.execute(
        "INSERT INTO photos(case_id,uploader,uploader_role,rel_path,mime,ext,size,sha256,kind,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,NULL,?)",
        (cid, "라운드73업체", "협력사", "b.jpg", "image/jpeg", "jpg", 100, "sha-b", DB.now())).lastrowid
    conn.commit()
    conn.close()

    client = A.app.test_client()
    _tok = "regress-round73-csrf"
    with client.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    r = client.post(f"/api/cases/{cid}/open-auction",
                     json={"est_basis": "출동 사진으로 2차 경매를 엽니다(회귀테스트)"},
                     headers=_hdr)
    body_r = r.get_json() or {}
    chk(r.status_code == 200 and body_r.get("ok"),
        "STEP 2차 경매 개시 자체는 정상 처리된다", body_r)

    conn = DB.get_db()
    _kinds = {r2["id"]: r2["kind"] for r2 in
              conn.execute("SELECT id, kind FROM photos WHERE case_id=?", (cid,))}
    conn.close()
    chk(_kinds.get(p_admin) == "착공전",
        "★★★ 전화·팩스 대신접수(uploader_role='운영자') 사진도 착공전으로 분류되어"
        " 입찰자에게 열린다(고치기 전엔 화이트리스트에 안 걸려 '기타'로 영영 남았다)",
        _kinds)
    chk(_kinds.get(p_partner) == "착공전",
        "★ 대조군 — 원래도 되던 협력사 사진 경로는 여전히 정상 분류된다(회귀 없음)",
        _kinds)

    conn = DB.get_db()
    _log_row = conn.execute(
        "SELECT detail FROM activity_log WHERE action IN ('경매 개시(사진 확보)','2차 경매 개시') "
        "ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    chk(_log_row is not None and "2장" in _log_row["detail"],
        "★★ 활동로그가 실제로 분류된 장수(2장 — 운영자+협력사 사진 둘 다)를 정확히 남긴다"
        "(고치기 전엔 화이트리스트에 안 걸린 사진도 '분류됐다'고 후보 전체 수를 그대로 찍었다)",
        dict(_log_row) if _log_row else None)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드73 실측 준비/실행", f"{type(e).__name__} {e}")
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
