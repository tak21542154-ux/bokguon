# -*- coding: utf-8 -*-
"""스캔 90라운드 회귀 — 업체 응답이력 데모오염·보험사 공지사항 화면 부재/개수제한.

  [F1] api_partner_reliability(업체별 출동 호출·응답 집계)가 dispatch_calls 를
    is_demo 거르지 않고 그대로 세었다. dispatch_calls 자신은 is_demo 컬럼이
    없고(demo 표식은 dispatches 에만 있다) 형제 화면(api_dispatch_list)이 이미
    "데모 수배를 그대로 보여주면 실제 활동 0건을 실패 몇 건으로 지어낸다"는
    똑같은 사고를 겪고 고쳤는데, 여기는 그 join+필터를 안 물려받았다 —
    데모 수배가 부른 **실제 업체**의 응답률이 오염됐다.

  [F2] 보험사 포털엔 "공지" 탭 자체가 없었다 — /api/notices 는 진작부터
    audience='보험사' 공지를 골라내는데 부를 화면이 없어 한 번도 안 보였다.

  [F3] 협력사 포털의 "공지" 탭은 대시보드용 LIMIT 5 스냅샷(D.notices)을
    재사용해 5건을 넘는 공지·핀은 영원히 안 보였다.

      python test_scan_round90_fixes.py
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
INSURER_HTML = read(os.path.join("templates", "insurer_portal.html"))
PARTNER_HTML = read(os.path.join("templates", "partner_portal.html"))

print("═" * 72)
print("  스캔 90라운드 회귀 — 업체 응답이력 데모오염·보험사 공지 부재/개수제한")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


def _js_fn_body(src, header):
    start = src.index(header)
    depth = 0
    i = src.index("{", start)
    j = i
    while True:
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
        j += 1


# ══════════════════════════════════════════════════════════════
print("\n[1] F1 — 소스: api_partner_reliability 가 dispatches 를 조인해 is_demo 를 거른다")
# ──────────────────────────────────────────────────────────────
rel_body = _py_fn_body(APP_SRC, "api_partner_reliability")
chk("JOIN dispatches dd ON dd.id = dc.dispatch_id" in rel_body,
    "★★★ dispatch_calls 에 없는 is_demo 를 dispatches 조인으로 끌어온다")
chk("COALESCE(dd.is_demo,0)=0" in rel_body,
    "★★★ 데모 수배의 호출 이력을 집계에서 뺀다")

# ══════════════════════════════════════════════════════════════
print("\n[2] F2 — 소스: 보험사 포털에 공지 탭과 렌더 함수가 있다")
# ──────────────────────────────────────────────────────────────
chk('data-v="notice">공지<' in INSURER_HTML,
    "★★★ 보험사 포털 탭바에 '공지' 탭이 있다(예전엔 아예 없었다)")
ins_notice_fn = _js_fn_body(INSURER_HTML, "RENDER.notice = async () => {")
chk("api('GET','/api/notices')" in ins_notice_fn,
    "★★ RENDER.notice 가 /api/notices 를 직접 호출한다")

# ══════════════════════════════════════════════════════════════
print("\n[3] F3 — 소스: 협력사 공지 탭이 D.notices(5건 제한) 대신 새로 불러온다")
# ──────────────────────────────────────────────────────────────
par_notice_fn = _js_fn_body(PARTNER_HTML, "RENDER.notice = async () => {")
chk("api('GET','/api/notices')" in par_notice_fn,
    "★★★ 협력사 공지 탭이 개수 제한 없는 /api/notices 를 직접 호출한다")
chk("D.notices" not in par_notice_fn,
    "★★ 더 이상 대시보드의 5건짜리 스냅샷(D.notices)을 재사용하지 않는다")

# ══════════════════════════════════════════════════════════════
print("\n[4] F1 — 실행: 데모 수배가 부른 실제 업체는 집계에서 빠진다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round90_")
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
    p_real = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R90실제업체','시행사','활성')"
    ).lastrowid
    p_ctrl = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R90대조업체','시행사','활성')"
    ).lastrowid
    c_demo = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R90-DEMO','접수','가드레일','서울',1)").lastrowid
    c_real = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R90-REAL','접수','가드레일','서울',0)").lastrowid
    d_demo = conn.execute(
        "INSERT INTO dispatches(case_id,status,is_demo) VALUES(?,'실패',1)", (c_demo,)).lastrowid
    d_real = conn.execute(
        "INSERT INTO dispatches(case_id,status,is_demo) VALUES(?,'도착',0)", (c_real,)).lastrowid
    now = DB.now()
    # 실제 업체가 데모 수배에 불려 '무응답'으로 쌓인 이력 — 이게 오염원이다.
    conn.execute(
        "INSERT INTO dispatch_calls(dispatch_id,partner_id,partner_name,notified_at,response) "
        "VALUES(?,?,?,?,'무응답')", (d_demo, p_real, "R90실제업체", now))
    # 대조 업체는 진짜(비데모) 수배에서 정상 수락 — 계속 보여야 한다.
    conn.execute(
        "INSERT INTO dispatch_calls(dispatch_id,partner_id,partner_name,notified_at,"
        "                           responded_at,response) VALUES(?,?,?,?,?,'수락')",
        (d_real, p_ctrl, "R90대조업체", now, now))
    conn.commit(); conn.close()

    admin = A.app.test_client()
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"

    j = admin.get("/api/partner-reliability").get_json()
    names = {r["name"]: r for r in j.get("items", [])}
    chk("R90실제업체" not in names,
        "★★★ 데모 수배가 부른 실제 업체는 응답이력 집계에 아예 안 나온다"
        "(예전엔 무응답 1건이 그대로 잡혀 응답률을 깎았다)", list(names))
    chk("R90대조업체" in names and names["R90대조업체"]["호출"] == 1
        and names["R90대조업체"]["수락"] == 1,
        "★★ 진짜(비데모) 수배의 정상 이력은 그대로 집계된다(과잉차단 아님)",
        names.get("R90대조업체"))

    # ══════════════════════════════════════════════════════════
    print("\n[5] F2 — 실행: /api/notices 가 보험사 세션에 audience='보험사' 공지를 준다")
    # ──────────────────────────────────────────────────────────
    conn = DB.get_db()
    iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R90보험','활성')").lastrowid
    conn.execute(
        "INSERT INTO notices(title,body,audience,pinned,created_at) "
        "VALUES('보험사 전용 공지','내용','보험사',0,?)", (DB.now(),))
    conn.execute(
        "INSERT INTO notices(title,body,audience,pinned,created_at) "
        "VALUES('협력사 전용 공지','내용','협력업체',0,?)", (DB.now(),))
    conn.commit(); conn.close()

    insurer_c = A.app.test_client()
    with insurer_c.session_transaction() as sess:
        sess["insurer_id"] = iid; sess["insurer_name"] = "R90보험"
    jn = insurer_c.get("/api/notices").get_json()
    titles = [n["title"] for n in jn]
    chk("보험사 전용 공지" in titles and "협력사 전용 공지" not in titles,
        "★★★ 보험사로 로그인하면 보험사 대상 공지만 보인다(협력사 대상은 안 섞인다)",
        titles)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드90 서버측 준비/실행", f"{type(e).__name__} {e}")
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
