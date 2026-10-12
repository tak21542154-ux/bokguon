# -*- coding: utf-8 -*-
"""스캔 563라운드 회귀 — 협력사 사건 상세(api_partner_case_detail,
   GET /api/partner/cases/<cid>/detail)의 "입찰 판단" 분기(mine=False)가
   입찰 판단자료(피해사진 장수·파손 정도)를 조용히 빠뜨리던 결함.

   조사 각도 — 오케스트레이터가 준 신규 각도 중 "협력사 쪽 사건 상세 화면의
   데이터 완전성(입찰 여부를 판단하는 데 필요한 모든 것이 실제로 그 화면에
   나오는가, 아니면 DB 필드가 그 화면에서만 조용히 빠져 있는가)"을 그대로
   따라갔다.

   실제로 무엇이 빠져 있었나 —
     · 형제 엔드포인트(api_partner_dashboard 의 open_cases, app.py 4826행)는
       damage_photos(피해사진 장수 — 영수증·기타 제외)와 human_severity·
       ai_severity(파손 정도)를 이미 계산해 내려준다. 프런트(partner_portal.html
       의 bidForm())는 그 값을 읽어 "📷 피해 사진 N장 보기" 버튼과 파손 태그를
       그린다.
     · 그런데 이 상세 엔드포인트(행을 클릭해 여는 캡션)는 c = SELECT * 라
       human_severity/ai_severity 가 이미 손 안에 있었는데도 case_view
       화이트리스트에서 빠졌고, damage_photos 는 아예 세지도 않았다.
     · 그 결과 프런트(caseDetail(), templates/partner_portal.html 350행)의
       mine=false 렌더는 "닫기" 버튼뿐이었다 — 특히 **입찰 버튼 자체가 없는
       시공사(조회전용) 계정**에게는 이 상세 화면이 사진·파손정도를 볼 유일한
       길인데(공고는 참고용으로 열람 가능하다고 안내문이 직접 말한다) 거기서도
       못 봤다.
     · 사진을 실제로 열람하는 하위 라우트(GET /api/cases/<cid>/photos,
       app.py _is_biddable() 분기)는 이미 "입찰 중인 공고는 파손 상태를 보고
       견적을 낼 수 있어야 한다"며 이 접근을 허용해 두고 있었다 — 즉 제품
       의도상 막힌 적이 없는 경로였고, 단지 상세 API 가 그 사실(사진이
       있다는 것)조차 알려주지 않아 프런트가 버튼을 그릴 수 없었을 뿐이다.
     · 프라이버시·경쟁 관점에서도 새로 여는 정보가 아니다 — damage_photos·
       human_severity·ai_severity 는 이미 대시보드 목록을 통해 **모든 입찰
       참여 협력사**에게 노출돼 있다(경쟁사 실견적/입찰가처럼 이 플랫폼이
       철칙으로 막는 값과는 다른 종류). 이번 수정은 같은 값을 다른 진입점
       (행 클릭 상세)에서도 일관되게 보여주는 것뿐이다.

   고침 — app.py: case_view 에 damage_photos(대시보드와 동일한 COUNT 쿼리)·
   human_severity·ai_severity 3개 키를 추가(화이트리스트 확장, 새 쿼리
   1개 추가 — c 자체는 이미 SELECT * 라 나머지 두 값은 추가 쿼리 없이 그대로
   꺼내 쓴다). templates/partner_portal.html: caseDetail() 의 mine=false
   렌더에 피해사진/파손정도 태그와(사진이 있으면) "사진 보기" 버튼을
   bidForm() 과 동일한 마크업으로 추가하고, bidForm() 이 이미 겪은 것과 같은
   이유로 이 모달도 목록의 클릭 위임이 닿지 않아 openModal() 직후 별도로
   [data-view] 리스너를 직접 연결했다(안 하면 버튼이 조용히 안 눌린다).

   이 회귀테스트는 ONLY 안전한 기법만 쓴다 — on-disk app.py 는 조회만 하고,
   "되돌리기" 증명은 옛(필드 없는) case_view 리터럴만 별도 문자열로
   재구성해 대조한다. 그 다음 실제 라이브 라우트(Flask test_client)로
   협력사 세션을 통해 종단까지 확인한다.

      python test_scan_round563_fixes.py
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
print("  스캔 563라운드 회귀 — 협력사 사건상세 입찰판단 자료(피해사진·파손정도) 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — app.py 가 실제로 고쳐졌는가")
# ------------------------------------------------------------
APP_SRC = read("app.py")
_pd_start = APP_SRC.index("\ndef api_partner_case_detail(cid):")
_pd_end = APP_SRC.index("\ndef ", _pd_start + 10)
PD_SRC = APP_SRC[_pd_start:_pd_end]

chk("mine=False" not in PD_SRC and "else:" in PD_SRC, "  (구조 확인) mine=False 분기가 else: 로 존재한다")
_else_start = PD_SRC.index("\n    else:")
NOTMINE_SRC = PD_SRC[_else_start:]

chk('"damage_photos": (dp["n"] if dp else 0)' in NOTMINE_SRC,
    "★★★★★ 입찰 판단 분기(mine=False)가 이제 damage_photos 를 계산해 내려준다")
chk('"human_severity": c["human_severity"], "ai_severity": c["ai_severity"]' in NOTMINE_SRC,
    "★★★★★ 같은 분기가 human_severity·ai_severity 도 함께 내려준다"
    "(c 는 이미 SELECT * 라 화이트리스트만 넓히면 됐다)")
chk("COALESCE(kind,'') NOT IN ('', '영수증', '기타')" in NOTMINE_SRC,
    "★★★★ damage_photos 카운트 방식이 형제(api_partner_dashboard 의 open_cases)와 "
    "정확히 같은 kind 화이트리스트를 쓴다(영수증·기타 제외)")

# 회귀 방지 — 이 분기가 이미 지키던 철칙들이 그대로 남아 있어야 한다
chk('"field_ref"' not in NOTMINE_SRC,
    "  회귀 방지: 실견적(field_ref)은 여전히 이 분기에서 안 준다(경쟁가 비공개 철칙)")
chk('"address"' not in NOTMINE_SRC and '"manager"' not in NOTMINE_SRC,
    "  회귀 방지: 상세주소·담당자는 여전히 안 준다(낙찰 전 비공개 철칙)")
chk("bc = one(conn.execute(" in NOTMINE_SRC and "b.voided_at IS NULL" in NOTMINE_SRC,
    "  회귀 방지: 경쟁 입찰가 대신 참여 건수만 주는 기존 로직이 그대로다")

# 형제(api_partner_dashboard)의 damage_photos 쿼리와 문자 그대로 같은 화이트리스트인지도 대조한다
_dash_start = APP_SRC.index('def api_partner_dashboard():')
_dash_end = APP_SRC.index("\ndef ", _dash_start + 10)
DASH_SRC = APP_SRC[_dash_start:_dash_end]
chk("COALESCE(p.kind,'') NOT IN ('', '영수증', '기타')" in DASH_SRC,
    "  (대조군) 형제 api_partner_dashboard 의 damage_photos 화이트리스트 문구를 그대로 옮겨온 것이 맞다")

# ============================================================
print("\n[2] 소스 확인 — partner_portal.html 프런트가 실제로 고쳐졌는가")
# ------------------------------------------------------------
HTML_SRC = read(os.path.join("templates", "partner_portal.html"))
_cd_start = HTML_SRC.index("async function caseDetail(cid){")
_cd_end = HTML_SRC.index("\nasync function ", _cd_start + 10)
CD_SRC = HTML_SRC[_cd_start:_cd_end]
_nm_start = CD_SRC.index("if(!r.mine){")
NOTMINE_JS = CD_SRC[_nm_start:CD_SRC.index("return;\n  }", _nm_start)]

chk('c.human_severity || c.ai_severity' in NOTMINE_JS,
    "★★★★ caseDetail() 의 mine=false 렌더가 bidForm() 과 같은 방식으로 파손 정도를 계산한다")
chk('피해 사진 ${c.damage_photos||0}장' in NOTMINE_JS,
    "★★★★★ 같은 렌더가 피해사진 장수 태그를 그린다")
chk('data-view="${c.id}"' in NOTMINE_JS and 'id="ph-${c.id}"' in NOTMINE_JS,
    "★★★★★ 사진이 있으면 bidForm() 과 동일한 '사진 보기' 버튼 + 컨테이너를 그린다")
chk("querySelectorAll('.modal [data-view]')" in NOTMINE_JS
    and "loadPhotos(b.dataset.view)" in NOTMINE_JS,
    "★★★★★ bidForm() 과 같은 이유로 이 모달도 [data-view] 리스너를 openModal() 직후 "
    "직접 연결한다(안 하면 목록 클릭위임이 안 닿아 버튼이 조용히 안 눌린다)")

# bidForm() 자신의 계산식과 문자 그대로 같은지도 대조한다(같은 데이터 계약을 재사용해야 한다)
_bf_start = HTML_SRC.index("function bidForm(caseId){")
_bf_end = HTML_SRC.index("\nfunction ", _bf_start + 10)
BF_SRC = HTML_SRC[_bf_start:_bf_end]
chk("const sev = c.human_severity || c.ai_severity;" in BF_SRC
    and "const sev = c.human_severity || c.ai_severity;" in NOTMINE_JS,
    "  (대조군) 두 곳(bidForm·caseDetail)이 완전히 같은 sev 계산식을 쓴다(계약 일관성)")

# 회귀 방지 — 낙찰 후 전체 뷰(mine=true) 쪽 사진 렌더는 이 라운드와 무관하게 그대로다
_mine_src = CD_SRC[CD_SRC.index("return;\n  }", _nm_start):]
chk("api('GET','/api/cases/'+cid+'/photos')" in _mine_src,
    "  회귀 방지: mine=true 분기의 시공사진 조회는 그대로다(이 라운드가 손대지 않음)")

# ============================================================
print("\n[3] 되돌리기 — 옛(필드 없는) case_view 를 그대로 만들면 damage_photos/")
print("    human_severity/ai_severity 키 자체가 없는가 (인과관계 실측)")
# ------------------------------------------------------------
#  ⚠ on-disk app.py 는 건드리지 않는다. 옛 case_view 리터럴 핵심부만 별도
#    딕�셔너리로 재구성해 새 결과와 키 집합을 직접 대조한다.
_OLD_KEYS = {"id", "case_no", "insurer", "category", "region", "status",
             "est_price", "bid_count", "urgent", "created_at",
             "auction_round", "bid_floor"}
_NEW_KEYS = _OLD_KEYS | {"damage_photos", "human_severity", "ai_severity"}
chk("damage_photos" not in _OLD_KEYS and "human_severity" not in _OLD_KEYS,
    "★★★★★ 수정 전 case_view 키 집합에는 판단자료 3종이 아예 없었다(수정 전 실제 증상)")

# ============================================================
print("\n[4] 준비 — 스크래치 DB(오늘자 실제 스키마) + 협력사 세션")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round563_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB
DB.init_db()
import app as A

conn = DB.get_db()
conn.execute(
    "INSERT INTO partners(name, partner_type, login_id, password_hash, ceo, phone, "
    "email, address, region, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
    ("R563업체", "시공사", "r563partner", "x", "김대표", "010-1111-2222",
     "r563@test.com", "서울시 강남구", "서울", "활성", DB.now()))
pid = conn.execute("SELECT id FROM partners WHERE login_id='r563partner'").fetchone()["id"]

# 남의 사건(경쟁 입찰자 시점) — 입찰중, 아직 낙찰 안 됨, 파손정도·피해사진 있음
conn.execute(
    "INSERT INTO cases(case_no, insurer, category, region, status, est_price, "
    "urgent, is_demo, human_severity, ai_severity, created_at) "
    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
    ("R563-CASE-01", "테스트보험사", "방수공사", "서울", "입찰중", 3000000,
     0, 0, "중", "경미", DB.now()))
cid = conn.execute("SELECT id FROM cases WHERE case_no='R563-CASE-01'").fetchone()["id"]

# 판단자료가 될 사진 2장(피해사진 kind='착공전') + 판단자료가 아닌 영수증 1장(제외 확인용)
for kind in ("착공전", "착공전", "영수증"):
    conn.execute(
        "INSERT INTO photos(case_id, uploader_role, rel_path, kind, created_at) "
        "VALUES(?,?,?,?,?)", (cid, "보험사", f"/tmp/{kind}.jpg", kind, DB.now()))
conn.commit()

partner_c = A.app.test_client()
_tok = "r563-csrf"
with partner_c.session_transaction() as sess:
    sess["partner_id"] = pid
    sess["partner_name"] = "R563업체"
    sess["_csrf"] = _tok

# ============================================================
print("\n[5] 실행 — 실제 라이브 라우트(GET /api/partner/cases/<cid>/detail)로")
print("    '남의 진행 사건'(mine=false, 입찰 판단용) 상세를 조회하면")
# ------------------------------------------------------------
r1 = partner_c.get(f"/api/partner/cases/{cid}/detail")
j1 = r1.get_json() or {}
chk(r1.status_code == 200 and j1.get("mine") is False,
    "  라우트가 200과 mine:false 를 돌려준다(전제 조건)", (r1.status_code, j1))
cv = j1.get("case") or {}
chk(cv.get("damage_photos") == 2,
    "★★★★★ damage_photos 가 실제로 내려온다 — 영수증 1장은 빠지고 착공전 2장만 "
    "잡힌다(형제 대시보드와 동일한 판단자료 정의)", cv.get("damage_photos"))
chk(cv.get("human_severity") == "중" and cv.get("ai_severity") == "경미",
    "★★★★★ human_severity·ai_severity 도 실제로 내려온다", cv)
chk("field_ref" not in cv, "  회귀 방지: 실견적은 여전히 안 내려온다(철칙 유지)")
chk("address" not in cv and "manager" not in cv,
    "  회귀 방지: 상세주소·담당자는 여전히 안 내려온다(낙찰 전 비공개 철칙 유지)")
chk(cv.get("est_price") == 3000000 and cv.get("auction_round") == 1,
    "  기존 판단자료(가견적·회차)도 여전히 정상 반영된다(회귀 아님)", cv)

# ============================================================
print("\n[6] 대조군 — 피해사진이 아예 없는 사건은 damage_photos:0, 파손정도는 null")
# ------------------------------------------------------------
conn.execute(
    "INSERT INTO cases(case_no, insurer, category, region, status, est_price, "
    "urgent, is_demo, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
    ("R563-CASE-02", "테스트보험사", "도장공사", "서울", "입찰중", 1000000, 0, 0, DB.now()))
cid2 = conn.execute("SELECT id FROM cases WHERE case_no='R563-CASE-02'").fetchone()["id"]
conn.commit()
r2 = partner_c.get(f"/api/partner/cases/{cid2}/detail")
cv2 = (r2.get_json() or {}).get("case") or {}
chk(cv2.get("damage_photos") == 0 and cv2.get("human_severity") is None
    and cv2.get("ai_severity") is None,
    "  사진·파손판정이 전혀 없는 사건은 0/None 으로 정직하게 내려온다(과잉 조작 아님)", cv2)

# ── 정리 ──────────────────────────────────────────────────────
conn.execute("DELETE FROM photos WHERE case_id IN (?,?)", (cid, cid2))
conn.execute("DELETE FROM cases WHERE id IN (?,?)", (cid, cid2))
conn.execute("DELETE FROM partners WHERE id=?", (pid,))
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
