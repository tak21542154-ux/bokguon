# -*- coding: utf-8 -*-
"""스캔 91라운드 회귀 — 사진재사용 탐지 데모오염·낙찰취소 변경견적 가드 열거누락.

  [F1] /api/photo-reuse(사진 재사용 의심 탐지)가 is_demo 를 전혀 안 걸렀다.
    photos 자신엔 is_demo 컬럼이 없고(cases 에만 있다) 형제(api_dispatch_list·
    90라운드의 api_partner_reliability)가 이미 같은 사고를 겪었다 — 데모
    사건은 실제 보험사명(메리츠화재·DB손보 등)으로 들어가 있어, 영업 데모 중
    같은 샘플 사진을 두 데모 사건에 올린 것까지 진짜 사건과 구분 없이
    "재사용 의심"으로 뜬다.

  [F2] api_case_cancel_award 의 "변경견적 진행중" 차단 목록이 4개만 손으로
    나열해 '거절'·'유찰'이 빠졌다. 정작 같은 함수 40줄 아래의 정리 코드는
    '거절'·'유찰'을 포함한 6개 상태를 강제로 '철회' 처리하고, 형제
    (api_change_order_create 의 중복생성 방지)는 이미 종결 4개(수락확정·
    최종유찰·낙찰확정·철회) 의 NOT IN 으로 정확히 판정한다 — '거절'·'유찰'로
    끝난(=아직 결정 대기 중인) 변경견적이 있어도 낙찰취소·재공고가 그냥
    통과해, 결정되지 않은 변경견적이 사유·시각 없이 조용히 '철회' 처리됐다.

      python test_scan_round91_fixes.py
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
print("  스캔 91라운드 회귀 — 사진재사용 데모오염·낙찰취소 변경견적 가드 누락")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] F1 — 소스: api_photo_reuse 가 두 쿼리 모두 is_demo 를 거른다")
# ──────────────────────────────────────────────────────────────
reuse_body = _py_fn_body(APP_SRC, "api_photo_reuse")
chk(reuse_body.count("COALESCE(c.is_demo,0)=0") == 2,
    "★★★ 그룹집계·상세조회 두 쿼리 모두 is_demo 를 거른다", reuse_body.count("COALESCE(c.is_demo,0)=0"))

# ══════════════════════════════════════════════════════════════
print("\n[2] F2 — 소스: cancel-award 가드가 형제와 같은 NOT IN(종결4개) 를 쓴다")
# ──────────────────────────────────────────────────────────────
cancel_body = _py_fn_body(APP_SRC, "api_case_cancel_award")
chk("status NOT IN ('수락확정','최종유찰','낙찰확정','철회')" in cancel_body,
    "★★★ 차단 조건이 손으로 나열한 4개 대신 종결상태 NOT IN 을 쓴다")
chk("'실사요청','추가경매중','원업체제안','전체재경매중'" not in cancel_body
    or cancel_body.count("'실사요청'") == 1,
    "STEP 옛 손열거(4개 진행중 상태) 목록이 차단 조건에서 빠졌다"
    "(정리 코드의 6개 목록에는 여전히 남아 있어야 한다)")
chk("'거절','유찰','실사요청','추가경매중'" in cancel_body.replace("\n", "").replace(" ", ""),
    "STEP 정리 코드(강제 철회)의 6개 상태 목록은 그대로 남아 있다(회귀 아님)")

# ══════════════════════════════════════════════════════════════
print("\n[3] F1 — 실행: 데모 사건 간 사진 재사용은 안 뜨고, 실제 재사용은 그대로 뜬다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round91_")
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

    def _mkcase(no, is_demo, status="시공중", pid=None, pname=None):
        return conn.execute(
            "INSERT INTO cases(case_no,status,category,region,is_demo,partner_id,partner_name) "
            "VALUES(?,?,?,?,?,?,?)", (no, status, "가드레일", "서울", is_demo, pid, pname)
        ).lastrowid

    def _mkphoto(cid, sha):
        conn.execute(
            """INSERT INTO photos(case_id,partner_id,uploader,uploader_role,rel_path,orig_name,
                                  mime,ext,size,sha256,kind,review_status,created_at)
               VALUES(?,0,'검증','내부',?,?,?,?,100,?,'착공전','승인',?)""",
            (cid, f"t/{sha}.jpg", "t.jpg", "image/jpeg", ".jpg", sha, DB.now()))

    c_demo1 = _mkcase("R91-DEMO1", 1)
    c_demo2 = _mkcase("R91-DEMO2", 1)
    c_real1 = _mkcase("R91-REAL1", 0)
    c_real2 = _mkcase("R91-REAL2", 0)
    _mkphoto(c_demo1, "sha_demo_shared")
    _mkphoto(c_demo2, "sha_demo_shared")
    _mkphoto(c_real1, "sha_real_shared")
    _mkphoto(c_real2, "sha_real_shared")
    conn.commit(); conn.close()

    admin = A.app.test_client()
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"

    jr = admin.get("/api/photo-reuse").get_json()
    all_case_nos = {p["case_no"] for g in jr.get("groups", []) for p in g.get("photos", [])}
    chk("R91-DEMO1" not in all_case_nos and "R91-DEMO2" not in all_case_nos,
        "★★★ 데모 사건끼리의 사진 재사용은 탐지 결과에 안 나온다", all_case_nos)
    chk("R91-REAL1" in all_case_nos and "R91-REAL2" in all_case_nos,
        "★★ 실제 사건 간 사진 재사용은 그대로 탐지된다(과잉차단 아님)", all_case_nos)

    # ══════════════════════════════════════════════════════════
    print("\n[4] F2 — 실행: '거절'/'유찰' 변경견적이 있으면 낙찰취소가 막힌다")
    # ──────────────────────────────────────────────────────────
    conn = DB.get_db()
    _tok = "r91-admin-csrf"
    with admin.session_transaction() as sess:
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok, "Content-Type": "application/json"}

    for st in ("거절", "유찰"):
        cid = conn.execute(
            "INSERT INTO cases(case_no,status,category,region,partner_id,partner_name,"
            "                  award_amount) VALUES(?,'시공중','가드레일','서울',1,'R91업체',5000000)",
            (f"R91-{st}",)).lastrowid
        conn.execute(
            "INSERT INTO change_orders(case_id,status,incumbent_partner_id,incumbent_amount,"
            "                          created_at) VALUES(?,?,1,5000000,?)", (cid, st, DB.now()))
        conn.commit()
        r = admin.post(f"/api/cases/{cid}/cancel-award", json={"reason": "라운드91 검증 사유"}, headers=_hdr)
        j = r.get_json()
        chk(r.status_code == 409 and j.get("code") == "CHANGE_ORDER_ACTIVE",
            f"★★★ 변경견적이 '{st}' 상태면 낙찰취소가 막힌다"
            "(예전엔 이 상태가 목록에서 빠져 그냥 통과했다)",
            f"status={r.status_code} body={j}")
        # 막혔으니 사건 상태·변경견적 상태 모두 그대로여야 한다.
        row = conn.execute("SELECT status, partner_id FROM cases WHERE id=?", (cid,)).fetchone()
        co_row = conn.execute(
            "SELECT status FROM change_orders WHERE case_id=?", (cid,)).fetchone()
        chk(row["status"] == "시공중" and row["partner_id"] == 1,
            f"★★ ('{st}') 막힌 요청은 사건 상태를 실제로 바꾸지 않는다", dict(row))
        chk(co_row["status"] == st,
            f"★★ ('{st}') 변경견적도 조용히 '철회' 처리되지 않고 원래 상태를 유지한다",
            co_row["status"])

    # 회귀 방지: 이미 종결된 변경견적(철회)이 있는 경우는 여전히 통과해야 한다.
    cid_ok = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,partner_name,"
        "                  award_amount) VALUES('R91-OK','시공중','가드레일','서울',1,'R91업체',5000000)"
    ).lastrowid
    conn.execute(
        "INSERT INTO change_orders(case_id,status,incumbent_partner_id,incumbent_amount,"
        "                          created_at) VALUES(?,'철회',1,5000000,?)", (cid_ok, DB.now()))
    conn.commit(); conn.close()
    r_ok = admin.post(f"/api/cases/{cid_ok}/cancel-award", json={"reason": "라운드91 검증 사유"}, headers=_hdr)
    chk(r_ok.status_code == 200,
        "★★ 변경견적이 이미 종결(철회)이면 낙찰취소는 그대로 통과한다(과잉차단 아님)",
        f"status={r_ok.status_code} body={r_ok.get_json()}")

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드91 서버측 준비/실행", f"{type(e).__name__} {e}")
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
