# -*- coding: utf-8 -*-
"""스캔 580라운드 회귀 — 현장 출동 보고서(dispatch_report, GET /report/dispatch/<cid>)의
   사진 정렬이 죽은 컬럼(photos.sort_order)에 기대고 있어, 뒤늦게 추가된 '착공전' 사진이
   '완료' 사진보다 뒤에 실리던 결함(직접조사, 하위위임 없음).

   조사 각도 — "읽는 자리 vs 쓰는 자리"(자식표 플래그를 아무도 안 채우면 그 필터/정렬은
   죽어 있다)를 정렬 컬럼에 적용했다. db.py 의 photos.sort_order(INTEGER DEFAULT 0)는
   이 파일 두 곳(api_case_photos·dispatch_report)의 SQL이 `ORDER BY sort_order, id` 로
   읽는데, 이 저장소 전체(app.py·모든 모듈·기존 회귀테스트 전부)에 이 컬럼에 값을
   **쓰는** 코드는 단 한 곳도 없다(전수 grep, 아래 [1]에서 재확인) — 항상 스키마
   기본값 0으로 묶여 있어 그 ORDER BY 는 사실상 `ORDER BY id`(업로드 순)와 같다.

   실제 영향 — photos.kind 는 착공전/시공중/완료 세 공정을 나타내고(photo_ai.py
   CONSTRUCTION_KINDS), 정상 흐름에서는 업로드 순서가 곧 공정 순서라 우연히
   맞아떨어진다. 그런데 _upload_damage_photos()(가견적 근거 사진, 항상 kind='착공전'
   으로 넣는다 — app.py 12612행 자신의 docstring)는 보험사·운영자 양쪽에서 **사건
   상태와 무관하게 아무 때나** 호출된다(호출부 두 곳 다 사건 존재만 확인하고 status
   는 안 본다). 이미 '완료' 사진까지 올라온 사건에 뒤늦게 피해사진을 추가하면, 그
   착공전 사진이 가장 큰 id 로 들어와 raw id 순에서는 맨 뒤로 밀린다 — 보험사에
   넘기는 "현장 사진" 보고서가 완료 사진 뒤에 착공전 사진을 보여주는 뒤바뀐 순서가
   된다.

   형제 대조 — api_case_photos()(관리자 사진검수 화면이 쓰는 API)는 이미 이 문제를
   비켜 가고 있었다 — SQL 은 똑같이 죽은 sort_order 를 읽지만, 그 뒤 Python 에서
   PHOTO.CONSTRUCTION_KINDS 순서로 다시 정렬해 반환한다(12837행 부근, 이 라운드
   이전). dispatch_report() 만 그 재정렬 없이 raw SQL 순서를 템플릿에 그대로
   넘기고 있었다 — "이미 있는 형제 방어를 안 쓴 한 곳"이었다.

   고침 — app.py: api_case_photos() 바로 앞에 그 재정렬 로직을 `_sort_construction_phase()`
   로 이름 붙여 뽑고, api_case_photos() 는 그 함수를 호출하도록 바꾸고(동작 동일),
   dispatch_report() 도 SQL 조회 직후 같은 함수를 호출하게 했다. 새 컬럼·새 판정을
   만들지 않고 이미 검증된 규칙 하나를 공유한다.

   이 회귀테스트는 [1] 소스 확인(sort_order 를 쓰는 코드가 여전히 없다 + 헬퍼가 두
   호출부 모두에서 실제로 쓰인다), [2] 단위 실행(_sort_construction_phase 자체),
   [3] 종단 실행(스크래치 DB + 실제 Flask 라우트로 문제 시나리오 재현: 완료→착공전
   순으로 사진을 넣고 실제 보고서 HTML의 이미지 순서를 확인), [4] 되돌리기 —
   dispatch_report 의 SQL 원문을 소스에서 그대로 뽑아 같은 DB에 직접 실행해 "고치기
   전이었다면" 나왔을 순서(=raw id 순, 착공전이 맨 뒤)를 실측 대조한다(on-disk 파일은
   전혀 건드리지 않는다 — 이미 있는 SQL 문자열을 다시 실행할 뿐이다).

       python test_scan_round580_fixes.py
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
print("  스캔 580라운드 회귀 — dispatch_report 사진순서(죽은 sort_order 컬럼) 결함")
print("=" * 72)

APP_SRC = read("app.py")

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk(APP_SRC.count("def _sort_construction_phase(photo_rows):") == 1,
    "★★★★★ _sort_construction_phase() 헬퍼가 정확히 한 곳에 정의됐다")

_helper_i = APP_SRC.index("def _sort_construction_phase(photo_rows):")
_apicp_i = APP_SRC.index("def api_case_photos(cid):")
_dr_i = APP_SRC.index("def dispatch_report(cid):")
chk(_helper_i < _apicp_i < _dr_i,
    "  헬퍼가 두 호출부보다 앞서 정의된다(정의 순서상 안전)",
    (_helper_i, _apicp_i, _dr_i))

_apicp_end = APP_SRC.index("\ndef ", _apicp_i + 10)
APICP_SRC = APP_SRC[_apicp_i:_apicp_end]
chk("_sort_construction_phase([p for p in rs if p[\"kind\"] in PHOTO.CONSTRUCTION_KINDS])"
    in APICP_SRC,
    "★★★★ api_case_photos() 가 새 헬퍼를 호출한다(기존 인라인 정렬을 대체)")
chk("order = {k: i for i, k in enumerate(PHOTO.CONSTRUCTION_KINDS)}" not in APICP_SRC,
    "  회귀 없음 — api_case_photos() 자신에는 이제 인라인 정렬 로직이 안 남아 있다"
    "(헬퍼로만 존재)")

_dr_end = APP_SRC.index("\ndef ", _dr_i + 10)
DR_SRC = APP_SRC[_dr_i:_dr_end]
chk('ph = rows(conn.execute(\n            "SELECT id, kind, created_at FROM photos "\n'
    '            " WHERE case_id=? AND review_status=\'승인\' ORDER BY sort_order, id LIMIT 16", (cid,)))'
    in DR_SRC,
    "  (전제) dispatch_report() 의 원본 SQL 문자열이 그대로 남아 있다(아래 [4]가 "
    "이 문자열을 그대로 재사용한다)")
chk("ph = _sort_construction_phase(ph)" in DR_SRC,
    "★★★★★ dispatch_report() 가 SQL 조회 직후 새 헬퍼로 재정렬한다(이번 수정의 핵심)")
chk(DR_SRC.index("ph = rows(conn.execute(") < DR_SRC.index("ph = _sort_construction_phase(ph)")
    < DR_SRC.index("render_template(\"dispatch_report.html\""),
    "  순서 확인 — SQL 조회 → 재정렬 → 템플릿 렌더 순으로 실제 배치됐다")

# 헬퍼 함수 몸체만 슬라이스 — 로직 자체(순위표 + 정렬 키)를 직접 확인
_helper_end = APP_SRC.index("\n@app.get(\"/api/cases/<int:cid>/photos\")", _helper_i)
HELPER_SRC = APP_SRC[_helper_i:_helper_end]
chk('order = {k: i for i, k in enumerate(PHOTO.CONSTRUCTION_KINDS)}' in HELPER_SRC
    and 'key=lambda p: (order.get(p["kind"], 9), p["id"])' in HELPER_SRC,
    "★★★★ 헬퍼 로직이 예전 api_case_photos 인라인 코드와 동일한 정렬 키를 쓴다"
    "(동작을 그대로 옮긴 것이지 새 판정이 아니다)")

# sort_order 를 실제로 "쓰는" 코드가 여전히 없는가 — 이 결함의 근본 원인
_assign_hits = [ln for ln in APP_SRC.splitlines()
                if ("sort_order=" in ln or "sort_order =" in ln) and "ORDER BY" not in ln]
chk(_assign_hits == [],
    "★★★★★ app.py 어디에도 sort_order 에 값을 대입하는 코드가 없다(여전히 죽은 컬럼 — "
    "이번 수정은 그 사실 자체를 지우지 않고, 그 사실에 안전하게 대응하는 재정렬을 추가했을 뿐)",
    _assign_hits)
#  ⚠ run_all_tests.py 는 제외한다 — 이 테스트를 UNIT 목록에 등록하면서 쓴 설명문 자체가
#    'sort_order'라는 단어를 산문으로 인용한다(등록 직후 재실행하면 실제로 이 파일 하나만
#    걸린다 — 자기 자신을 등록한 결과일 뿐, 컬럼에 값을 쓰는 코드가 아니다).
_other_files_with_col = [
    fn for fn in os.listdir(HERE)
    if fn.endswith(".py") and fn != os.path.basename(__file__)
    and fn not in ("app.py", "db.py", "run_all_tests.py")
    and "sort_order" in read(fn)]
chk(_other_files_with_col == [],
    "  repo 전수 — app.py·db.py(스키마)·run_all_tests.py(이 테스트 등록 설명문)·이 테스트 "
    "외에는 sort_order 를 아는 파일이 없다",
    _other_files_with_col)

# ============================================================
print("\n[2] 단위 실행 — _sort_construction_phase() 자체")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round580_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB  # noqa: E402
DB.init_db()
import app as A  # noqa: E402

# id 순서(업로드 순)와 공정 순서가 정반대로 섞인 입력 — 실제 버그 시나리오의 축소판
_sample = [
    {"id": 10, "kind": "완료"},
    {"id": 11, "kind": "영수증"},      # 알 수 없는(비-공정) kind — 뒤로 밀려야 한다
    {"id": 5,  "kind": "시공중"},
    {"id": 20, "kind": "착공전"},      # 가장 큰 id 인데도 공정상 맨 앞이어야 한다
    {"id": 21, "kind": None},         # kind 미분류 — 크래시 없이 뒤로 밀려야 한다
]
_out = A._sort_construction_phase(_sample)
_out_kinds = [p["kind"] for p in _out]
chk(_out_kinds == ["착공전", "시공중", "완료", "영수증", None],
    "★★★★★ 공정 순(착공전→시공중→완료)으로 정렬되고, 그 외 kind는 뒤로 밀린다 "
    "(id 순이 아니다)", _out_kinds)
chk(_out[3]["id"] == 11 and _out[4]["id"] == 21,
    "  동순위(영수증·None 모두 순위 9)는 id 오름차순으로 안정 정렬된다", _out)
chk(A._sort_construction_phase([]) == [], "  빈 목록도 예외 없이 빈 목록을 낸다")

# ============================================================
print("\n[3] 종단 실행 — 실제 Flask 라우트로 문제 시나리오 재현")
# ------------------------------------------------------------
conn = DB.get_db()
conn.execute("INSERT INTO admins(username,password_hash,name,role) "
             "VALUES('r580admin','x','검증','최고관리자')")
conn.execute(
    "INSERT INTO cases(case_no, insurer, category, region, status, est_price, "
    "urgent, is_demo, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
    ("R580-CASE-01", "테스트보험사", "가드레일", "서울", "완료", 2000000, 0, 0, DB.now()))
cid = conn.execute("SELECT id FROM cases WHERE case_no='R580-CASE-01'").fetchone()["id"]

#  실제 버그 재현 순서 — 공사가 이미 끝난 뒤(시공중→완료가 먼저 존재) 보험사가
#  뒤늦게 '착공전'(피해) 사진을 추가한다(_upload_damage_photos 의 실제 동작:
#  kind='착공전'을 사건 상태와 무관하게 아무 때나 넣는다).
for kind in ("시공중", "완료", "착공전"):
    conn.execute(
        "INSERT INTO photos(case_id, uploader_role, rel_path, kind, review_status, created_at) "
        "VALUES(?,?,?,?,?,?)",
        (cid, "협력사" if kind != "착공전" else "보험사",
         f"/tmp/r580_{kind}.jpg", kind, "승인", DB.now()))
conn.commit()
_ids = {r["kind"]: r["id"] for r in conn.execute(
    "SELECT id, kind FROM photos WHERE case_id=?", (cid,)).fetchall()}
chk(_ids["착공전"] > _ids["완료"] > _ids["시공중"],
    "  (전제) 착공전 사진이 실제로 가장 큰 id로 가장 늦게 들어왔다(현실적 재현)", _ids)

client = A.app.test_client()
with client.session_transaction() as sess:
    sess["admin"] = "r580admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"

resp = client.get(f"/report/dispatch/{cid}")
html = resp.get_data(as_text=True)
chk(resp.status_code == 200, "  GET /report/dispatch/<cid> 가 200을 낸다(전제 조건)", resp.status_code)

_pos = {kind: html.find(f"/api/photos/{_ids[kind]}/file") for kind in ("착공전", "시공중", "완료")}
chk(all(p >= 0 for p in _pos.values()),
    "  세 사진(착공전·시공중·완료) 전부 보고서 HTML에 실제로 나타난다", _pos)
chk(_pos["착공전"] < _pos["시공중"] < _pos["완료"],
    "★★★★★★ (핵심 증거) 실제 라이브 라우트가 이제 공정 순(착공전→시공중→완료)으로 "
    "렌더한다 — 뒤늦게 들어온 착공전 사진이 더는 맨 뒤로 밀리지 않는다", _pos)

# 형제 API(관리자 사진검수 화면)도 회귀 없이 여전히 같은 순서를 낸다 — 헬퍼로 옮긴
# 뒤에도 api_case_photos() 자신의 동작은 바뀌지 않아야 한다
r2 = client.get(f"/api/cases/{cid}/photos")
j2 = r2.get_json() or {}
_constr_ids = [p["id"] for p in j2.get("construction", [])]
chk(_constr_ids == [_ids["착공전"], _ids["시공중"], _ids["완료"]],
    "  회귀 없음 — api_case_photos() 의 construction 배열도 여전히 공정 순(헬퍼로 "
    "옮기기 전과 동일한 결과)", _constr_ids)

# ============================================================
print("\n[4] 되돌리기 — dispatch_report 의 SQL 원문만 그대로 다시 실행하면")
print("    (고치기 전이었다면 나왔을 순서) 착공전이 실제로 맨 뒤로 밀리는가")
# ------------------------------------------------------------
#  ⚠ on-disk app.py 는 건드리지 않는다. [1]에서 이미 확인한, dispatch_report()
#    안에 실제로 있는 그 SQL 문자열을 그대로(문자 그대로) 재실행할 뿐이다 —
#    이 결과가 바로 "재정렬 호출이 없었다면" 템플릿이 받았을 raw 값이다.
_old_order_rows = [dict(r) for r in conn.execute(
    "SELECT id, kind, created_at FROM photos "
    " WHERE case_id=? AND review_status='승인' ORDER BY sort_order, id LIMIT 16", (cid,))]
_old_kinds = [r["kind"] for r in _old_order_rows]
chk(_old_kinds == ["시공중", "완료", "착공전"],
    "★★★★★★ (인과관계 실측) 고치기 전 SQL 그대로라면 착공전이 맨 뒤였다 — "
    "위 [3]의 실제 렌더 순서(착공전이 맨 앞)와 정반대", _old_kinds)
chk(A._sort_construction_phase(_old_order_rows)[0]["kind"] == "착공전",
    "  같은 raw 결과에 헬퍼를 통과시키면(=지금 dispatch_report 가 실제로 하는 일) "
    "착공전이 맨 앞으로 온다 — 헬퍼가 정확히 그 차이를 만든다")

# ── 정리 ──────────────────────────────────────────────────────
conn.execute("DELETE FROM photos WHERE case_id=?", (cid,))
conn.execute("DELETE FROM cases WHERE id=?", (cid,))
conn.execute("DELETE FROM admins WHERE username='r580admin'")
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
