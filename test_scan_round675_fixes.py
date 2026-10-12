# -*- coding: utf-8 -*-
"""스캔 675라운드 회귀(직접조사, 하위위임 없음) — 변경견적 재경매(추가분·전체재경매)
   입찰자에게 사건 사진·상세를 볼 방법이 전혀 없었던 결함.

   조사 각도 — round674 핸드오프의 "언급수 낮은 파일" 기법을 먼저 다시 계산해 보니
   templates/version.html(0건)·error.html·insurer_login.html·partner_login.html(각 1건) 등은
   전부 이미 여러 라운드가 결론 낸 클린 화면이라 이 기법 자체는 마른 상태였다. 대신
   partner_portal.html 의 11개 RENDER 패널 중 round674 핸드오프가 "이미 감사됨"으로
   분류하지 않은 reauction 패널을 직접 열어, 그 패널이 부르는 백엔드 게이트를 끝까지
   따라갔다.

   실측 경위
     1) templates/partner_portal.html 의 RENDER.reauction(변경견적 재경매 입찰 화면)은
        접수번호·공종·지역·증액사유(co_reason)·입찰 상한만 보여주고 **사진을 보여줄
        방법이 전혀 없다** — loadPhotos()·caseDetail() 어느 쪽도 호출하지 않는다.
     2) 그런데 이 흐름 자신의 설계 문서(app.py 11169행 "①...추가사진", 11172행
        "④...거절 → 추가사진 붙여 '전체 재경매'")는 재경매를 열 때 "추가사진"을
        붙인다고 명시한다 — 사진이 있는데 볼 방법이 없는 상태.
     3) 원인은 app.py _is_biddable(conn, case_id)다. 이 헬퍼는 사진 열람의
        단일 판정 지점인데(round565가 이미 api_partner_case_detail 을 여기로 통일),
        원경매(a.change_order_id IS NULL, cases.status='입찰중')만 본다. 변경견적
        재경매는 이미 낙찰된 뒤(cases.status='시공중' 등)라 이 조건이 항상 거짓이라,
        재경매 입찰 자격이 있는(= /api/reauctions 목록에 뜨는) 제3의 업체조차
        ① _photo_visible_to() 의 시공사진 파일 열람 ② api_case_photos() 의
        bidder_only 판정(GET /api/cases/<cid>/photos) ③ api_partner_case_detail() 의
        '남의 사건' 상세 열람(GET /api/partner/cases/<cid>/detail) 세 곳 모두에서
        403 을 받는다 — 확대된 공사범위에 사진 한 장 없이 총액을 적으라는 것과
        같다(이 코드베이스가 2차입찰 설계에서 반복해 경계하는 바로 그 상황).

   고침
     · app.py _is_biddable(): 기존 원경매 조건이 거짓일 때, /api/reauctions(22415행
       근처)이 이미 쓰는 것과 같은 조건(진행 상태·마감 전·change_order 존재·
       co.status IN ('추가경매중','전체재경매중'))으로 한 번 더 확인해 True 를 반환한다.
       단일 지점 수정 — 이 함수를 부르는 세 소비처는 전부 무변경으로 함께 고쳐진다.
     · templates/partner_portal.html RENDER.reauction: 원경매 목록(1057행)이 이미 쓰는
       data-act="caseDetail" 액션(전역 ACT.caseDetail, 새 함수 아님)을 재사용해 "현장
       사진·상세" 버튼 한 줄을 추가 — 서버가 이제 허용하는 열람을 실제로 쓸 수 있는
       진입점을 만든다. /api/reauctions 응답에는 case_id 가 이미 내려오고 있어(22409행)
       프런트 응답 스키마 변경은 없다.

   이 회귀테스트는 ONLY 안전한 기법만 쓴다 — on-disk app.py 는 조회만 하고,
   "되돌리기" 증명은 고치기 전 _is_biddable() 전체를 문자열로 재현해 모듈 속성
   (A._is_biddable)을 그 함수로 잠깐 바꿔치기한 뒤 finally 로 원상복구한다(라운드565가
   쓴 "실제 라우트에 옛 버전을 갈아끼운다" 기법과 같은 결, 대상만 라우트 전체 대신
   공유 헬퍼 하나라 더 작다).

      python test_scan_round675_fixes.py
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
print("  스캔 675라운드 회귀 — 변경견적 재경매 입찰자가 사건 사진·상세를 볼 길이 없던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — app.py 의 _is_biddable() 이 실제로 고쳐졌는가")
# ------------------------------------------------------------
APP_SRC = read("app.py")
_ib_start = APP_SRC.index("\ndef _is_biddable(")
_ib_end = APP_SRC.index("\ndef ", _ib_start + 10)
IB_SRC = APP_SRC[_ib_start:_ib_end]

chk("status='입찰중'" in IB_SRC and "a.change_order_id IS NULL" in IB_SRC,
    "★★★★★ 원경매 조건(원본 쿼리)이 그대로 남아 있다(회귀 없음)")
chk("change_orders co ON co.id = au.change_order_id" in IB_SRC,
    "★★★★★ 새 조건 — change_orders 를 조인해 재경매 상태를 본다")
chk("co.status IN ('추가경매중','전체재경매중')" in IB_SRC,
    "★★★★★ /api/reauctions(22415행 근처)과 같은 상태 집합을 그대로 재사용한다")
chk("au.status='진행'" in IB_SRC and "au.deadline IS NULL OR au.deadline > datetime('now'" in IB_SRC,
    "★★★★ 재경매도 '진행 상태 + 마감 전'을 함께 요구한다(무조건 열지 않는다)")

REAU_SRC = APP_SRC[APP_SRC.index('"""SELECT au.id AS auction_id'):]
REAU_SRC = REAU_SRC[:REAU_SRC.index("return jsonify(reau)")]
chk("co.status IN ('추가경매중','전체재경매중')" in REAU_SRC,
    "  (대조군) /api/reauctions 자신도 정확히 같은 상태 집합을 쓴다 — 새로 베낀 조건이 아니다")

TPL_SRC = read("templates/partner_portal.html")
_rr_start = TPL_SRC.index("RENDER.reauction = async () => {")
_rr_end = TPL_SRC.index("\nfunction reBidForm(")
RR_SRC = TPL_SRC[_rr_start:_rr_end]
chk('data-act="caseDetail" data-arg="${r.case_id}"' in RR_SRC,
    "★★★★★ RENDER.reauction 이 이제 기존 caseDetail 액션으로 사진·상세를 열어 준다")
chk("ACT.caseDetail = (a, el, ev, b) => caseDetail(_n(a), _n(b), el, ev);" in TPL_SRC,
    "  (전제) caseDetail 은 이미 전역 액션으로 등록돼 있다 — 새 JS 함수를 만들지 않았다")

# ============================================================
print("\n[2] 준비 — 스크래치 DB/업로드 디렉터리 + app 모듈 로드")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round675_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB
DB.init_db()
import app as A
import photo_ai as PHOTO

conn = DB.get_db()


def mkpartner(login_id, name):
    conn.execute(
        "INSERT INTO partners(name, partner_type, login_id, password_hash, ceo, phone, "
        "email, address, region, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (name, "시공사", login_id, "x", "김대표", "010-1111-2222",
         f"{login_id}@test.com", "서울시 강남구", "서울", "활성", DB.now()))
    return conn.execute("SELECT id FROM partners WHERE login_id=?", (login_id,)).fetchone()["id"]


p1 = mkpartner("r675partner1", "R675원낙찰업체")   # 원 낙찰업체(incumbent)
p2 = mkpartner("r675partner2", "R675경쟁업체")     # 재경매 입찰 자격이 있는 제3의 업체 — 이 테스트의 주인공


def mkcase(case_no, status, partner_id=None):
    conn.execute(
        "INSERT INTO cases(case_no, insurer, category, region, status, est_price, award_amount, "
        "urgent, is_demo, partner_id, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (case_no, "테스트보험사", "방수공사", "서울", status, 3000000,
         (3000000 if partner_id else None), 0, 0, partner_id, DB.now()))
    return conn.execute("SELECT id FROM cases WHERE case_no=?", (case_no,)).fetchone()["id"]


def mkco(case_id, status, incumbent_id):
    cur = conn.execute(
        "INSERT INTO change_orders(case_id, round, incumbent_partner_id, incumbent_amount, "
        "reason, requested_amount, status, created_at) VALUES(?,?,?,?,?,?,?,?)",
        (case_id, 1, incumbent_id, 3000000, "실측 결과 파손 범위 확대", 500000, status, DB.now()))
    return cur.lastrowid


def mkauction(case_id, status, deadline, co_id=None):
    conn.execute(
        "INSERT INTO auctions(case_id, change_order_id, deadline, status, created_at) "
        "VALUES(?,?,?,?,?)", (case_id, co_id, deadline, status, DB.now()))


# 사건A — 살아 있는 전체재경매(이 결함의 핵심 재현 대상)
cid_live = mkcase("R675-LIVE", "시공중", partner_id=p1)
co_live = mkco(cid_live, "전체재경매중", p1)
mkauction(cid_live, "진행", "2099-01-01 00:00:00", co_live)
conn.execute(
    "INSERT INTO photos(case_id, rel_path, orig_name, mime, kind, review_status, created_at) "
    "VALUES(?,?,?,?,?,?,?)",
    (cid_live, "r675/site.jpg", "site.jpg", "image/jpeg", "시공중", "승인", DB.now()))
_photo_id = conn.execute("SELECT id FROM photos WHERE case_id=?", (cid_live,)).fetchone()["id"]
os.makedirs(os.path.join(PHOTO.UPLOAD_ROOT, "r675"), exist_ok=True)
with open(os.path.join(PHOTO.UPLOAD_ROOT, "r675", "site.jpg"), "wb") as f:
    f.write(b"\xff\xd8\xff\xe0fakejpegdata")

# 사건B — 대조군: 마감이 지난 전체재경매(마감을 넘겨서까지 열리면 안 된다)
cid_expired = mkcase("R675-EXPIRED", "시공중", partner_id=p1)
co_expired = mkco(cid_expired, "전체재경매중", p1)
mkauction(cid_expired, "진행", "2020-01-01 00:00:00", co_expired)

# 사건C — 대조군: 변경견적이 아직 '실사요청' 단계(관리자가 재경매를 열기 전)
cid_pending = mkcase("R675-PENDING", "시공중", partner_id=p1)
co_pending = mkco(cid_pending, "실사요청", p1)

# 사건D — 대조군: 변경견적 자체가 없는 평범한 시공중 사건(과잉차단 방지 확인용 반대편)
cid_noauc = mkcase("R675-NOAUC", "시공중", partner_id=p1)

# 사건E — 대조군: 원경매가 그대로 열려 있는 사건(이 라운드와 무관 — 회귀 없어야 한다)
cid_orig = mkcase("R675-ORIG", "입찰중")
conn.execute("INSERT INTO auctions(case_id, deadline, status, created_at) VALUES(?,?,?,?)",
             (cid_orig, "2099-01-01 00:00:00", "진행", DB.now()))

conn.commit()

partner2_c = A.app.test_client()
with partner2_c.session_transaction() as sess:
    sess["partner_id"] = p2
    sess["partner_name"] = "R675경쟁업체"
    sess["_csrf"] = "r675-csrf"

# ============================================================
print("\n[3] 단위 — _is_biddable() 직접 호출로 다섯 사건을 대조한다")
# ------------------------------------------------------------
chk(A._is_biddable(conn, cid_live) is True,
    "★★★★★★ 사건A(살아있는 전체재경매) = True — 고치기 전엔 status!='입찰중' 이라 False였다")
chk(A._is_biddable(conn, cid_expired) is False,
    "  사건B(마감 지난 재경매) = False — 재경매도 마감은 여전히 지킨다")
chk(A._is_biddable(conn, cid_pending) is False,
    "  사건C(아직 '실사요청', 경매 미개설) = False — co.status 게이트가 조기 개방을 막는다")
chk(A._is_biddable(conn, cid_noauc) is False,
    "  사건D(변경견적 자체가 없음) = False — 과잉차단 반대편 회귀 없음(무관한 시공중 사건까지 열리지 않는다)")
chk(A._is_biddable(conn, cid_orig) is True,
    "  사건E(평범한 원경매 입찰중) = True — 원경매 판정 자체는 완전히 그대로다(핵심 회귀 방지)")

# ============================================================
print("\n[4] 종단 — 실제 HTTP 로 재경매 입찰자격 업체(p2)가 사건A를 실제로 볼 수 있는가")
# ------------------------------------------------------------
r_detail = partner2_c.get(f"/api/partner/cases/{cid_live}/detail")
j_detail = r_detail.get_json() or {}
chk(r_detail.status_code == 200 and j_detail.get("mine") is False,
    "★★★★★★ GET /api/partner/cases/<cid>/detail — 고치기 전 403이던 재경매 대상 사건이 "
    "이제 200/mine:false 로 열린다", (r_detail.status_code, j_detail))
chk((j_detail.get("case") or {}).get("damage_photos") == 1,
    "  상세 응답의 damage_photos 가 실제로 심어 둔 시공중 사진 1장을 정확히 센다",
    j_detail.get("case"))

r_list = partner2_c.get(f"/api/cases/{cid_live}/photos")
j_list = r_list.get_json() or {}
chk(r_list.status_code == 200,
    "★★★★★★ GET /api/cases/<cid>/photos — 고치기 전 403이던 목록 조회가 이제 200이다",
    (r_list.status_code, j_list))
_constr = (j_list or {}).get("construction") or []
chk(len(_constr) == 1 and _constr[0].get("id") == _photo_id,
    "  목록에 심어 둔 시공중 사진이 그대로 담겨 온다", _constr)
chk("uploader" not in _constr[0] if _constr else False,
    "  회귀 없음 — 경쟁 입찰자에게는 여전히 redact 되어 uploader 같은 민감 필드는 빠진다")

r_file = partner2_c.get(f"/api/photos/{_photo_id}/file")
chk(r_file.status_code == 200,
    "★★★★★★ GET /api/photos/<id>/file — 파일 바이트 자체도 이제 실제로 내려온다"
    "(목록엔 있는데 눌러도 안 열리는 죽은 링크가 아니다)", r_file.status_code)

# ── 대조군 — 마감 지난 사건B는 여전히 세 경로 모두 막힌다 ──
r_detail_b = partner2_c.get(f"/api/partner/cases/{cid_expired}/detail")
chk(r_detail_b.status_code == 403,
    "  회귀 방지: 마감 지난 재경매(사건B)는 상세 조회가 여전히 403이다", r_detail_b.status_code)
r_list_b = partner2_c.get(f"/api/cases/{cid_expired}/photos")
chk(r_list_b.status_code == 403,
    "  회귀 방지: 마감 지난 재경매(사건B)는 사진 목록도 여전히 403이다", r_list_b.status_code)

# ── 대조군 — 변경견적 자체가 없는 사건D는 여전히 막힌다(제3자에게 아무 사건이나 열리는 게 아니다) ──
r_detail_d = partner2_c.get(f"/api/partner/cases/{cid_noauc}/detail")
chk(r_detail_d.status_code == 403,
    "  회귀 방지: 변경견적이 없는 평범한 시공중 사건(D)은 그대로 403이다 — "
    "재경매 자격이 있는 사건만 새로 열린다", r_detail_d.status_code)

# ============================================================
print("\n[5] 되돌리기 증명 — 고치기 전 _is_biddable() 을 잠깐 갈아끼워 증상을 재현한다")
# ------------------------------------------------------------
#  ⚠ on-disk app.py 는 건드리지 않는다. 고치기 전 원문 그대로를 별도 이름으로 정의해
#    A._is_biddable 모듈 속성만 잠깐 바꿔치기하고, 끝나면 finally 로 원상복구한다.
OLD_IS_BIDDABLE_SRC = '''
def _old_is_biddable(conn, case_id):
    """[라운드675 이전 원문] 원경매만 본다 — 변경견적 재경매는 판정하지 않는다."""
    return bool(A.one(conn.execute(
        """SELECT 1 x FROM cases c
             LEFT JOIN auctions a ON a.case_id = c.id AND a.change_order_id IS NULL
            WHERE c.id=? AND c.status=\\'입찰중\\'
              AND (a.deadline IS NULL OR a.deadline > datetime(\\'now\\',\\'+9 hours\\'))
            LIMIT 1""", (case_id,))))
'''
_ns = {"A": A}
exec(compile(OLD_IS_BIDDABLE_SRC, "<round675-reverted:_is_biddable>", "exec"), _ns)
OLD_FN = _ns["_old_is_biddable"]
NEW_FN = A._is_biddable    # 고친 현재 버전 — 원상복구용으로 미리 쥔다

try:
    A._is_biddable = OLD_FN
    chk(A._is_biddable(conn, cid_live) is False,
        "  (되돌린 버전) 사건A(살아있는 전체재경매) 조차 다시 False 로 돌아간다 — "
        "이것이 고치기 전 실제로 겪던 증상이다")
    r_old_detail = partner2_c.get(f"/api/partner/cases/{cid_live}/detail")
    r_old_list = partner2_c.get(f"/api/cases/{cid_live}/photos")
    chk(r_old_detail.status_code == 403 and r_old_list.status_code == 403,
        "★★★★★★ (되돌린 버전) 같은 실제 HTTP 요청이 상세·사진 목록 둘 다 403으로 재현된다 "
        "— 재경매 입찰 자격이 있는 업체가 사진을 볼 방법이 정말 없었다",
        (r_old_detail.status_code, r_old_list.status_code))
    #  대조군(원경매 사건E)은 되돌린 옛 버전에서도 여전히 True 다 — 이 결함이
    #  원경매 판정 자체를 건드린 적이 없다는 사실의 대조 확인.
    chk(A._is_biddable(conn, cid_orig) is True,
        "  (되돌린 버전) 원경매 사건E는 옛 버전에서도 그대로 True — 이 결함은 재경매 갈래에서만 났다")
finally:
    A._is_biddable = NEW_FN   # 실험 직후 즉시 원상복구

# 원상복구 확인 — 같은 요청을 다시 하면 정상(200)으로 돌아온다
r_restored = partner2_c.get(f"/api/partner/cases/{cid_live}/detail")
chk(r_restored.status_code == 200,
    "  원상복구 확인 — A._is_biddable 을 되돌리자 같은 요청이 다시 200이 된다",
    r_restored.status_code)

# ── 정리 ──────────────────────────────────────────────────────
conn.execute("DELETE FROM photos WHERE case_id IN (?)", (cid_live,))
conn.execute("DELETE FROM auctions WHERE case_id IN (?,?,?)", (cid_live, cid_expired, cid_orig))
conn.execute("DELETE FROM change_orders WHERE case_id IN (?,?,?)",
             (cid_live, cid_expired, cid_pending))
conn.execute("DELETE FROM cases WHERE id IN (?,?,?,?,?)",
             (cid_live, cid_expired, cid_pending, cid_noauc, cid_orig))
conn.execute("DELETE FROM partners WHERE id IN (?,?)", (p1, p2))
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
