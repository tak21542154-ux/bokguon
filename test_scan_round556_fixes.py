# -*- coding: utf-8 -*-
"""스캔 556라운드 회귀 — 관리자 콘솔 사건등록 vs 보험사 포털·API 공용 경로의
   필드 정합성(과제가 제시한 신규 각도) 조사에서 발견한 결함 1건.

   발견 — cases.source 컬럼은 db.py 스키마 주석에서부터 이미 세 갈래
   ("포털/ API/ 관리자 수동" · 통계·감사용, ALTER 기본값 '포털')를 문서화해
   두고 있다. 형제 경로 _create_case(보험사 포털·v1 API 공용, app.py 4078행)는
   이미 "포털"/"API"를 명시로 채우는데(4268행·4404행 호출부), api_case_create
   (관리자 콘솔 전용, POST /api/cases, @require_admin, app.py 11268행)만 이
   컬럼 자체가 INSERT 문에 없어 ALTER TABLE 기본값('포털')으로 조용히
   떨어졌다 — **관리자가 등록한 사건이 전부 "포털 접수"로 잘못 집계된다.**
   에러도 없고 화면도 정상으로 보여서, source 로 실제 통계·감사 질의를 돌리기
   전에는 아무도 못 본다.

   이 정확한 유형(관리자 콘솔 경로가 스키마 마이그레이션으로 나중에 추가된
   컬럼을 못 따라와 형제 _create_case 와 갈라짐)은 이 세션에서 이미 여러 번
   잡힌 패턴이다(라운드68 — UNIQUE 락 없음, 라운드198 — Idempotency-Key 없음,
   라운드416 — WORK_MAJORS 화이트리스트·자모 지역값 없음, 라운드484 —
   RE_PHONE 형식검증 없음). 매번 "형제 경로와 같은 처방을 그대로 쓴다"로
   고쳐 왔고, 이번도 같은 처방 — api_case_create 의 INSERT 문에 source 컬럼과
   '관리자수동' 값을 추가했다.

   같이 검토했으나 손대지 않은 것: note 컬럼은 관리자 콘솔 화면(admin.js
   createCase())에 애초에 입력 칸이 없다 — 사용자가 적은 값이 사라지는 게
   아니라 처음부터 받지 않는 것이라 이번 결함과 다른 종류(기능 없음, 새
   정책 판단)다. warranty_months 는 컬럼 자체에 DEFAULT 24 가 있어(db.py)
   _create_case 가 넣는 값(24)과 이미 일치해 실질적 드리프트가 없다.

   이 회귀테스트(8개 검사)는 ONLY 안전한 기법만 쓴다 — 실제 on-disk app.py는
   조회만 하고, "되돌리기" 증명은 옛(결함이 있던) INSERT 문을 별도 문자열로
   재구성해 exec()으로 스크래치 DB에 직접 실행해 인과관계를 실측한다.

       python test_scan_round556_fixes.py
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


print("=" * 72)
print("  스캔 556라운드 회귀 — 관리자 사건등록(api_case_create)의 source 컬럼 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — app.py 가 실제로 고쳐졌는가")
# ------------------------------------------------------------
APP_SRC = read("app.py")
#  ⚠⚠ [라운드625] 끝에 ')'를 요구하던 원래 리터럴이 round625(같은 INSERT에 is_demo
#    컬럼을 추가)와 충돌했다 — status_at 뒤에 컬럼이 하나 더 붙어 그 줄이 더는
#    ')'로 안 끝난다. 이 검사의 취지(source가 그 자리에 있다)는 안 바뀌므로 끝의
#    ')' 요구만 뺀다 — 앞으로 컬럼이 또 늘어나도 이 자리 자체는 그대로 남는다.
chk("status,est_price,low_price,manager,source,lat,lng,geo_src,created_at,status_at" in APP_SRC,
    "★★★★★ api_case_create의 INSERT 컬럼 목록에 source가 추가됐다")
chk('d.get("manager", "자동"), "관리자수동",' in APP_SRC,
    "★★★★★ 값 튜플에 '관리자수동' 리터럴이 채워졌다")
chk('_create_case(conn, iid, me["name"], d, "포털", actor_name=portal_actor())' in APP_SRC
    and '_create_case(conn, ins["id"], ins["name"], d, "API")' in APP_SRC,
    "  회귀 방지: 형제 경로(포털·API 호출부)는 이번 수정과 무관하게 그대로다")

# ============================================================
print("\n[2] 준비 — 스크래치 DB(오늘자 실제 스키마) + 관리자 계정")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round556_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB
DB.init_db()
import app as A

conn = DB.get_db()
conn.execute("INSERT INTO admins(username,password_hash,name,role) "
             "VALUES('admin','x','검증','중간관리자')")
conn.commit()

_src_col = None
for _r in conn.execute("PRAGMA table_info(cases)"):
    if _r["name"] == "source":
        _src_col = _r
        break
chk(_src_col is not None and (_src_col["dflt_value"] or "").strip("'") == "포털",
    "★★★ 전제조건: cases.source 컬럼의 스키마 기본값이 지금도 '포털'이다"
    "(그래서 컬럼을 빼먹으면 조용히 이 값으로 떨어진다)",
    dict(_src_col) if _src_col else None)


def _mkinsurer(tag):
    conn.execute("INSERT INTO insurers(name,status) VALUES(?,'활성')", (f"{tag}보험사",))
    conn.commit()
    return conn.execute("SELECT id, name FROM insurers WHERE name=?",
                         (f"{tag}보험사",)).fetchone()


# ============================================================
print("\n[3] 되돌리기 — api_case_create의 옛(source 누락) INSERT를 오늘자 스키마에")
print("    그대로 실행하면 실제로 '포털'로 잘못 떨어지는가 (인과관계 실측)")
# ------------------------------------------------------------
ins_old = _mkinsurer("R556OLD")
#  ⚠ api_case_create 에 실제로 있었던 옛(이번 라운드 이전) 코드를 문자열로만
#    재구성한다 — on-disk 파일은 전혀 건드리지 않는다(안전 규칙: in-memory
#    재구성 + exec 만 쓴다).
OLD_INSERT_SRC = (
    "cur = conn.execute(\n"
    "    \"\"\"INSERT INTO cases(case_no,insurer,insurer_id,category,region,address,urgent,"
    "is_composite,\n"
    "                         status,est_price,low_price,manager,lat,lng,geo_src,created_at,"
    "status_at)\n"
    "       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)\"\"\",\n"
    "    (case_no, insurer_name, insurer_id, category, '', '', 0, 0,\n"
    "     '입찰중', 0, 0, '자동', None, None, None, DB.now(), DB.now()),\n"
    ")\n"
    "result['id'] = cur.lastrowid\n"
)
_ns = {"conn": conn, "DB": DB, "case_no": "R556OLD-1", "insurer_name": ins_old["name"],
       "insurer_id": ins_old["id"], "category": "유리·샷시·자동문", "result": {}}
exec(OLD_INSERT_SRC, {}, _ns)
conn.commit()
row_old = A.one(conn.execute("SELECT source FROM cases WHERE id=?", (_ns["result"]["id"],)))
chk(row_old is not None and row_old["source"] == "포털",
    "★★★★★ source 컬럼을 뺀 옛 INSERT는 관리자가 만든 사건도 '포털'로 "
    "조용히 오기록한다(수정 전 실제 상태를 인과관계로 증명)",
    row_old)

# ============================================================
print("\n[4] 실행 — 실제 라이브 라우트(POST /api/cases, api_case_create)로 지금")
print("    관리자 등록 사건이 '관리자수동'으로 정확히 남는가")
# ------------------------------------------------------------
ins_new = _mkinsurer("R556NEW")
client = A.app.test_client()
_tok = "r556-admin-csrf"
with client.session_transaction() as sess:
    sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
    sess["_csrf"] = _tok

r = client.post("/api/cases", headers={"X-CSRF-Token": _tok}, json={
    "case_no": "R556NEW-1", "category": "유리·샷시·자동문",
    "insurer_id": ins_new["id"], "insurer": ins_new["name"],
    "no_photo": True,
})
rd = r.get_json() or {}
chk(r.status_code == 200 and rd.get("ok"),
    "실제 라우트가 200으로 사건을 만든다", (r.status_code, rd))
cid_new = rd.get("id")
row_new = A.one(conn.execute("SELECT source, status, intake_type FROM cases WHERE id=?",
                              (cid_new,))) if cid_new else None
chk(row_new is not None and row_new["source"] == "관리자수동",
    "★★★★★ 관리자 콘솔로 만든 사건은 이제 source='관리자수동'으로 정확히 남는다"
    "([3]과 달리 더는 '포털'로 잘못 찍히지 않는다)",
    row_new)

# ============================================================
print("\n[5] 정합성 — 형제 경로(포털·API)는 지금도 자기 값대로 정확히 남는가")
print("    (세 갈래 '관리자수동/포털/API'가 동시에 성립해야 진짜 정합이다)")
# ------------------------------------------------------------
ins_por = _mkinsurer("R556POR")
ins_api = _mkinsurer("R556API")
conn.execute("BEGIN IMMEDIATE")
res_por = A._create_case(conn, ins_por["id"], ins_por["name"],
                          {"case_no": "R556POR-1", "category": "유리·샷시·자동문",
                           "no_photo": True}, "포털")
conn.commit()
conn.execute("BEGIN IMMEDIATE")
res_api = A._create_case(conn, ins_api["id"], ins_api["name"],
                          {"case_no": "R556API-1", "category": "유리·샷시·자동문",
                           "no_photo": True}, "API")
conn.commit()
src_por = (A.one(conn.execute("SELECT source FROM cases WHERE id=?", (res_por["id"],))) or {}).get("source")
src_api = (A.one(conn.execute("SELECT source FROM cases WHERE id=?", (res_api["id"],))) or {}).get("source")
chk(src_por == "포털" and src_api == "API",
    "  형제 경로(_create_case)는 이번 수정과 무관하게 여전히 '포털'/'API'를 정확히 남긴다",
    (src_por, src_api))
chk({(row_new or {}).get("source"), src_por, src_api} == {"관리자수동", "포털", "API"},
    "★★★★ 세 갈래(관리자수동/포털/API) 전부 스키마 주석이 문서화한 그대로 동시에 성립한다",
    ((row_new or {}).get("source"), src_por, src_api))

# ── 정리 ──────────────────────────────────────────────────────
for _no in ("R556OLD-1", "R556NEW-1", "R556POR-1", "R556API-1"):
    _row = conn.execute("SELECT id FROM cases WHERE case_no=?", (_no,)).fetchone()
    if _row:
        conn.execute("DELETE FROM work_lots WHERE case_id=?", (_row["id"],))
        conn.execute("DELETE FROM notifications WHERE case_id=?", (_row["id"],))
        conn.execute("DELETE FROM cases WHERE id=?", (_row["id"],))
for _tag in ("R556OLD", "R556NEW", "R556POR", "R556API"):
    conn.execute("DELETE FROM insurers WHERE name=?", (f"{_tag}보험사",))
conn.execute("DELETE FROM admins WHERE username='admin'")
conn.commit()
conn.close()

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
