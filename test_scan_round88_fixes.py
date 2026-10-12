# -*- coding: utf-8 -*-
"""스캔 88라운드 회귀 — AI 정확도 통계 자기일치 오염·달력 출동기한 데모누락.

  [F1] api_ai_review_stats 의 accuracy/bands 가 route='자동승인' 행까지 합쳐 셌다.
    자동승인 행은 _record_ai_review 가 human_kind 자리에 ai_kind 자신을 넣어
    만들기 때문에 agreed 가 **항상 1**(ai_kind==ai_kind) — 사람 판단이 실제로는
    없었다. 자동승인 물량이 많을수록 "정확도"가 저절로 100%에 가까워지고,
    화면 라벨("사람 판단과 일치한 비율")과 반대로 사람이 실제 확인한 적 없는
    건이 정확도를 부풀린다. route='사람검수'(사람이 실제로 확인·확정한 건)만
    모집단으로 삼아야 한다.

  [F2] /api/calendar 의 출동기한 하위쿼리만 형제 넷(입찰마감·시공완료일·보증만료·
    수동일정)과 달리 is_demo 를 거르지 않았다 — 데모 출동 건이 실제 사건과
    구분 안 되는 빨간 카드로 달력에 노출된다.

      python test_scan_round88_fixes.py
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
print("  스캔 88라운드 회귀 — AI 정확도 자기일치 오염·달력 출동기한 데모누락")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] F1 — 소스: 정확도 집계가 route='사람검수' 만 본다")
# ──────────────────────────────────────────────────────────────
stats_body = _py_fn_body(APP_SRC, "api_ai_review_stats")
chk("route='사람검수' AND COALESCE(ai_kind,'') <> ''" in stats_body,
    "★★★ 정확도 합계(tot) 쿼리가 route='사람검수' 로 좁혀져 있다")
chk("SELECT SUM(CASE WHEN route='자동승인'" in stats_body
    and "WHERE COALESCE(ai_kind,'') <> ''\"\"\"))" in stats_body.replace("\n", " "),
    "STEP 자동/사람 물량 집계(counts)는 별도 쿼리로 두 route 를 그대로 센다")
chk("WHERE route='사람검수' AND ai_confidence>0" in stats_body,
    "★★ 구간별(band) 집계도 같은 기준으로 좁혀져 있다")

# ══════════════════════════════════════════════════════════════
print("\n[2] F2 — 소스: /api/calendar 출동기한 쿼리가 is_demo 를 거른다")
# ──────────────────────────────────────────────────────────────
cal_body = _py_fn_body(APP_SRC, "api_calendar")
_dispatch_q = cal_body[cal_body.index("FROM dispatches"):cal_body.index("FROM dispatches") + 300]
chk("COALESCE(d.is_demo,0)=0" in _dispatch_q and "COALESCE(c.is_demo,0)=0" in _dispatch_q,
    "★★★ 출동기한 하위쿼리가 dispatches·cases 양쪽 is_demo 를 모두 거른다")

# ══════════════════════════════════════════════════════════════
print("\n[3] F1 — 실행: 자동승인만 있고 사람 검수가 없으면 정확도는 집계되지 않는다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round88_")
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
    import secrets

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','최고관리자')")
    iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R88보험','활성')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id) "
        "VALUES('R88-1','시공중','가드레일','서울',?)", (iid,)).lastrowid

    def _mkphoto(kind, conf):
        cur = conn.execute(
            """INSERT INTO photos(case_id, partner_id, uploader, uploader_role, rel_path,
                                  orig_name, mime, ext, size, sha256,
                                  kind, ai_kind, ai_confidence, ai_model, review_status, created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (cid, 1, "검증", "관리자", f"t/{kind}{conf}.jpg", "t.jpg", "image/jpeg", ".jpg",
             100, "r88_" + secrets.token_hex(8), kind, kind, conf, "검증", "대기", DB.now()))
        conn.commit()
        return cur.lastrowid

    th = A._ai_threshold(conn)
    p1 = _mkphoto("착공전", th + 5)
    route1 = A._apply_ai_routing(p1)
    chk(route1 == "auto", "STEP 준비: 고신뢰도 사진이 자동승인 경로를 탄다", route1)

    admin = A.app.test_client()
    _tok = "r88-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok, "Content-Type": "application/json"}

    j = admin.get("/api/ai/review-stats").get_json()
    chk(j.get("total") == 0 and j.get("accuracy") is None,
        "★★★ 자동승인뿐이면(사람 검수 0건) 정확도 모집단이 0건 — 100%로 부풀지 않는다",
        f"total={j.get('total')} accuracy={j.get('accuracy')}")
    chk(j.get("auto_approved") == 1,
        "★★ 그래도 자동승인 물량(auto_approved)은 정상적으로 1건 잡힌다", j.get("auto_approved"))

    # 사람이 이 자동승인 건을 나중에 다른 분류로 정정 — 진짜 사람 검수 발생
    r_fix = admin.post(f"/api/photos/{p1}/kind", json={"kind": "시공중"}, headers=_hdr)
    chk(r_fix.status_code == 200, "STEP 준비: 담당자가 자동승인 건을 재분류한다", r_fix.status_code)

    j2 = admin.get("/api/ai/review-stats").get_json()
    chk(j2.get("total") == 1 and j2.get("accuracy") == 0.0,
        "★★★ 사람이 실제로 확인·정정한 뒤에야 정확도 모집단(1건, 불일치)에 잡힌다",
        f"total={j2.get('total')} accuracy={j2.get('accuracy')}")
    chk(j2.get("auto_approved") == 1 and j2.get("human_reviewed") == 1,
        "★★ 자동/사람 물량 통계는 여전히 둘 다 정확히 센다(정확도 계산과 별개)",
        f"auto={j2.get('auto_approved')} human={j2.get('human_reviewed')}")

    # ══════════════════════════════════════════════════════════
    print("\n[4] F2 — 실행: 데모 출동 건은 달력에 안 뜨고, 실제 건은 그대로 뜬다")
    # ──────────────────────────────────────────────────────────
    cid_real = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
        "VALUES('R88-REAL','접수','가드레일','서울',?,0)", (iid,)).lastrowid
    cid_demo = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
        "VALUES('R88-DEMO','접수','가드레일','서울',?,1)", (iid,)).lastrowid
    due = "2027-03-15 10:00:00"
    conn.execute(
        "INSERT INTO dispatches(case_id,status,due_at,claimed_name,is_demo) "
        "VALUES(?,'수배됨',?,'실제업체',0)", (cid_real, due))
    conn.execute(
        "INSERT INTO dispatches(case_id,status,due_at,claimed_name,is_demo) "
        "VALUES(?,'수배됨',?,'데모업체',1)", (cid_demo, due))
    conn.commit()

    with admin.session_transaction() as sess:
        sess["admin_role"] = "하위관리자"
    jc = admin.get("/api/calendar?year=2027&month=3").get_json()
    titles = [e["title"] for e in jc.get("events", []) if e.get("kind") == "출동기한"]
    chk(any("R88-REAL" in t for t in titles),
        "★★ 실제 사건의 출동기한은 정상적으로 달력에 뜬다(과잉차단 아님)", titles)
    chk(not any("R88-DEMO" in t for t in titles),
        "★★★ 데모 사건의 출동기한은 달력에서 빠진다(예전엔 그대로 노출됐다)", titles)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드88 서버측 준비/실행", f"{type(e).__name__} {e}")
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
