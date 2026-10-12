# -*- coding: utf-8 -*-
"""스캔 565라운드 회귀 — 협력사 사건상세(api_partner_case_detail, GET
   /api/partner/cases/<cid>/detail)의 "남의 사건" 열람 게이트가 status 만 보고,
   형제(사진 열람 게이트 _is_biddable)가 함께 보는 "마감 전"은 보지 않던 결함.

   조사 각도 — 라운드563이 이 라우트의 mine=False 분기에 남겨 둔 "낮은 우선순위"
   메모를 그대로 따라갔다. api_partner_case_detail 의 남의 사건 열람 게이트는
       if not mine and c["status"] != "입찰중":
   로, cases.status 문자열 하나만 본다. 그런데 **같은 라운드가 방금 열어 준 사진
   보기 버튼**이 실제로 사진을 받아 오는 하위 라우트(GET /api/cases/<cid>/photos)의
   허용 판정은 _is_biddable() 이다(app.py 12292행 근처) —

       status='입찰중' AND (a.deadline IS NULL OR a.deadline > 지금)

   즉 "입찰중" 에 더해 "마감 전"까지 함께 봐야 한다. 마감이 지났는데 정기
   스윕(_sweep_if_due)이 아직 그 사건의 status 를 정리하지 않은 짧은 구간에는
   두 게이트가 갈린다 — 상세 API 는 그 사건을 여전히 "입찰중"으로 보고 열어
   주면서, 심지어 판단자료(damage_photos·human_severity·ai_severity, 라운드563이
   추가)까지 내려주고 "사진 N장 보기" 버튼을 그리게 하는데, 정작 그 버튼을
   누르면 사진 라우트는 _is_biddable() 이 False 라 열어주지 않는다 — 화면에
   "사진이 있다"고 말해 놓고 정작 열리지 않는 죽은 버튼이 생긴다.

   왜 이 헬퍼로 통일하는가 — _is_biddable() 은 이미 이 파일이 "지금 입찰이 열려
   있는 공고인가"를 판정하는 단일 지점으로 쓰고 있다(사진 열람 게이트가 그
   대표 호출부). 상세 열람 게이트도 같은 질문("이 사람이 아직 입찰 판단
   대상으로 이 공고를 볼 수 있는가")을 던지므로, 같은 헬퍼를 재사용하는 것이
   판정을 새로 베끼는 것보다 작고 안전한 수정이다.

   고침 — app.py: api_partner_case_detail() 의 게이트를
       if not mine and c["status"] != "입찰중":
   에서
       if not mine and not _is_biddable(conn, cid):
   로 교체(단일 지점, 새 쿼리·새 로직 없이 기존 헬퍼 재사용).

   이 회귀테스트는 ONLY 안전한 기법만 쓴다 — on-disk app.py 는 조회만 하고,
   "되돌리기" 증명은 현재 함수 전체를 그대로 옮긴 문자열에서 이 게이트 한 줄만
   옛 버전으로 되돌려 exec() 한 뒤, **실제 Flask 라우트(app.view_functions)에
   잠깐 갈아끼워** 같은 실제 URL로 증상을 재현하고 바로 원상복구한다(라운드564와
   같은 기법 — 대상이 헬퍼 함수 하나가 아니라 라우트 자체라 view_functions 를
   바꾼다는 점만 다르다).

      python test_scan_round565_fixes.py
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
print("  스캔 565라운드 회귀 — 협력사 사건상세 열람 게이트가 마감 지난 공고를 계속 연다")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — app.py 가 실제로 고쳐졌는가")
# ------------------------------------------------------------
APP_SRC = read("app.py")
_pd_start = APP_SRC.index("\ndef api_partner_case_detail(cid):")
_pd_end = APP_SRC.index("\ndef ", _pd_start + 10)
PD_SRC = APP_SRC[_pd_start:_pd_end]

chk("if not mine and not _is_biddable(conn, cid):" in PD_SRC,
    "★★★★★ '남의 사건' 열람 게이트가 이제 _is_biddable() 을 쓴다"
    "(형제 사진 게이트와 같은 판정을 공유한다)")
chk('if not mine and c["status"] != "입찰중":' not in PD_SRC,
    "★★★★★ 옛 게이트(status 문자열만 보는 조건)가 더 이상 없다")

_ib_start = APP_SRC.index("\ndef _is_biddable(")
_ib_end = APP_SRC.index("\ndef ", _ib_start + 10)
IB_SRC = APP_SRC[_ib_start:_ib_end]
chk("status='입찰중'" in IB_SRC and "a.deadline > datetime('now'" in IB_SRC,
    "  (대조군) _is_biddable() 은 실제로 '상태' + '마감 전' 두 조건을 함께 본다"
    "(이 두 조건 중 하나만 보던 옛 상세 게이트와 대조된다)")

# 회귀 방지 — 라운드563이 채운 판단자료 3종·mine=True 분기 구조는 이 라운드와 무관하다
chk('"damage_photos": (dp["n"] if dp else 0)' in PD_SRC,
    "  회귀 방지: 라운드563의 damage_photos 응답은 그대로 남아 있다")
chk("if mine:" in PD_SRC and "if not mine and not _is_biddable" in PD_SRC,
    "  회귀 방지: mine=True/False 두 분기 구조 자체는 그대로다")

# ============================================================
print("\n[2] 준비 — 스크래치 DB + app 모듈 로드")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round565_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB
DB.init_db()
import app as A

conn = DB.get_db()


def mkpartner(login_id, name):
    conn.execute(
        "INSERT INTO partners(name, partner_type, login_id, password_hash, ceo, phone, "
        "email, address, region, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (name, "시공사", login_id, "x", "김대표", "010-1111-2222",
         f"{login_id}@test.com", "서울시 강남구", "서울", "활성", DB.now()))
    return conn.execute("SELECT id FROM partners WHERE login_id=?", (login_id,)).fetchone()["id"]


p1 = mkpartner("r565partner1", "R565업체1")   # 사건 소유주가 될 업체
p2 = mkpartner("r565partner2", "R565업체2")   # 남(비낙찰) 시점 — 이 테스트의 주인공


def mkcase(case_no, status, partner_id=None):
    conn.execute(
        "INSERT INTO cases(case_no, insurer, category, region, status, est_price, "
        "urgent, is_demo, partner_id, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (case_no, "테스트보험사", "방수공사", "서울", status, 3000000, 0, 0,
         partner_id, DB.now()))
    return conn.execute("SELECT id FROM cases WHERE case_no=?", (case_no,)).fetchone()["id"]


# 사건A — 입찰중이라고 찍혀 있지만 경매 마감은 이미 한참 지났다(스윕 전 짧은 구간 재현)
cid_expired = mkcase("R565-EXPIRED", "입찰중")
conn.execute("INSERT INTO auctions(case_id, deadline, status, created_at) VALUES(?,?,?,?)",
             (cid_expired, "2020-01-01 00:00:00", "진행", DB.now()))

# 사건B — 입찰중 + 마감이 한참 남음(대조군: 여전히 열려야 정상, 과잉차단 방지)
cid_open = mkcase("R565-OPEN", "입찰중")
conn.execute("INSERT INTO auctions(case_id, deadline, status, created_at) VALUES(?,?,?,?)",
             (cid_open, "2099-01-01 00:00:00", "진행", DB.now()))

# 사건C — 아예 다른 상태(시공중, 남의 낙찰 건). round435 성격의 대조군 — 이 라운드와 무관하게 계속 차단돼야 한다
cid_inprog = mkcase("R565-INPROG", "시공중", partner_id=p1)

conn.commit()

partner2_c = A.app.test_client()
with partner2_c.session_transaction() as sess:
    sess["partner_id"] = p2
    sess["partner_name"] = "R565업체2"
    sess["_csrf"] = "r565-csrf"

chk("api_partner_case_detail" in A.app.view_functions,
    "  (전제) 라우트가 등록된 엔드포인트 이름을 확인했다")

# ============================================================
print("\n[3] 대조군 — _is_biddable() 자신은 마감 지난 '입찰중' 사건을 이미 False 로 본다")
# ------------------------------------------------------------
chk(A._is_biddable(conn, cid_expired) is False,
    "  _is_biddable(사건A) = False — 상태는 '입찰중'인데 마감이 지나 입찰은 불가능하다")
chk(A._is_biddable(conn, cid_open) is True,
    "  _is_biddable(사건B) = True — 마감이 안 지났으니 정상적으로 입찰 가능하다")
#  옛 게이트(status 문자열만 비교)라면 사건A 도 '입찰중'이라 그대로 통과시켰을 것 —
#  즉 옛 조건과 _is_biddable() 이 사건A 에서 갈린다는 전제 확인.
chk((conn.execute("SELECT status FROM cases WHERE id=?", (cid_expired,)).fetchone()["status"]
     == "입찰중"),
    "  (전제) 사건A 의 status 컬럼 자체는 여전히 '입찰중'이다 — 옛 조건은 이 값만 본다")

# ============================================================
print("\n[4] 되돌리기 증명 — 옛(status 만 보는) 버전을 실제 라이브 라우트에 잠깐 갈아끼운다")
# ------------------------------------------------------------
#  ⚠ on-disk app.py 는 건드리지 않는다. 현재 함수 전체를 그대로 옮긴 문자열에서
#    게이트 한 줄만 옛 버전으로 되돌려 exec() 하고, Flask 의 view_functions 를
#    통해 **같은 실제 URL**로 재현한다(라운드564가 헬퍼 함수 하나를 바꿔치기한
#    것과 같은 기법을, 대상이 라우트 자체이므로 view_functions 수준에서 적용).
OLD_ROUTE_SRC = '''
def api_partner_case_detail(cid):
    """협력사 포털 — 사건 행 클릭 상세.

    · 내 낙찰 건: 전체(주소·진행율·사진·내 정산·변경견적)
    · 입찰중 공고(내 낙찰 아님): 제한 뷰(상세주소·경쟁 입찰가·담당자 성명 비공개)
    """
    pid = session["partner_id"]
    conn = DB.get_db()
    c = one(conn.execute("SELECT * FROM cases WHERE id=?", (cid,)))
    if not c or int(c["is_demo"] or 0):
        conn.close(); return jsonify({"ok": False, "error": "사건을 찾을 수 없습니다."}), 404
    _fl, _cap, _ref, _rnd = bid_cap_of(conn, c)
    c["auction_round"], c["bid_floor"] = _rnd, _fl
    c["field_ref"] = _ref if _rnd == 2 else None
    mine = (c["partner_id"] == pid)
    if not mine and c["status"] != "입찰중":
        conn.close(); return jsonify({"ok": False, "error": "열람 권한이 없습니다."}), 403
    my_bid = one(conn.execute(
        "SELECT b.amount, b.days, b.created_at FROM bids b "
        "JOIN auctions a ON a.id=b.auction_id "
        " WHERE a.case_id=? AND b.partner_id=? AND b.voided_at IS NULL "
        "   AND a.change_order_id IS NULL "
        "ORDER BY b.id DESC", (cid, pid)))
    if mine:
        progress = _case_progress(conn, cid, c["status"])
        photos = _case_photos_stat(conn, cid, pid)
        sett = one(conn.execute(
            "SELECT amount,fee,payout,fee_rate_bp,insurer_paid,review_status,transfer_status,created_at "
            "FROM settlements WHERE case_id=? AND COALESCE(void_status,\\'\\') <> \\'취소\\' ORDER BY id DESC", (cid,)))
        defects = _case_defects(conn, cid)
        co = one(conn.execute(
            "SELECT id, round, status, combined_amount, add_low, incumbent_partner_id "
            "  FROM change_orders WHERE case_id=? ORDER BY id DESC", (cid,)))
        if co and co.get("incumbent_partner_id") != pid:
            co["add_low"] = None
        if co:
            co.pop("incumbent_partner_id", None)
        case_view = {
            "id": c["id"], "case_no": c["case_no"], "insurer": c["insurer"],
            "category": c["category"], "region": c["region"], "address": c["address"],
            "status": c["status"], "note": c["note"],
            "award_amount": c["award_amount"] or c["low_price"], "low_price": c["low_price"],
            "awarded_at": c["awarded_at"], "completed_at": c["completed_at"],
            "warranty_months": c["warranty_months"],
            "auction_round": c["auction_round"], "bid_floor": c["bid_floor"],
        }
        conn.close()
        return jsonify({"case": case_view, "mine": True, "my_bid": my_bid,
                        "progress": progress, "photos": photos,
                        "settlement": sett, "defects": defects, "change_order": co})
    else:
        bc = one(conn.execute(
            "SELECT COUNT(*) n FROM bids b JOIN auctions a ON a.id=b.auction_id "
            "WHERE a.case_id=? AND b.voided_at IS NULL", (cid,)))
        dp = one(conn.execute(
            "SELECT COUNT(*) n FROM photos WHERE case_id=? "
            "  AND COALESCE(kind,\\'\\') NOT IN (\\'\\', \\'영수증\\', \\'기타\\')", (cid,)))
        case_view = {
            "id": c["id"], "case_no": c["case_no"], "insurer": c["insurer"],
            "category": c["category"], "region": c["region"], "status": c["status"],
            "est_price": c["est_price"], "bid_count": (bc["n"] if bc else 0),
            "urgent": c["urgent"], "created_at": c["created_at"],
            "auction_round": c["auction_round"], "bid_floor": c["bid_floor"],
            "damage_photos": (dp["n"] if dp else 0),
            "human_severity": c["human_severity"], "ai_severity": c["ai_severity"],
        }
        conn.close()
        return jsonify({"case": case_view, "mine": False, "my_bid": my_bid})
'''
_ns = {}
exec(compile(OLD_ROUTE_SRC, "<round565-reverted:api_partner_case_detail>", "exec"), A.__dict__, _ns)
OLD_RAW_FN = _ns["api_partner_case_detail"]
OLD_VIEW = A.require_partner(OLD_RAW_FN)          # 실제 라우트와 같은 인증 데코레이터를 씌운다
NEW_VIEW = A.app.view_functions["api_partner_case_detail"]   # 고친 현재 버전(원상복구용으로 미리 쥔다)

try:
    A.app.view_functions["api_partner_case_detail"] = OLD_VIEW
    r_old = partner2_c.get(f"/api/partner/cases/{cid_expired}/detail")
    j_old = r_old.get_json() or {}
    chk(r_old.status_code == 200 and j_old.get("mine") is False,
        "★★★★★★ 되돌린(옛) 버전은 실제로 재현된다 — 마감이 지났는데도 status 만 보고 "
        "200/mine:false 로 열어 준다(사진 버튼은 뜨지만 실제 사진은 안 열리는 상태)",
        (r_old.status_code, j_old))
finally:
    A.app.view_functions["api_partner_case_detail"] = NEW_VIEW   # 실험 직후 즉시 원상복구

# ============================================================
print("\n[5] 실행 — 원상복구한 실제 라이브 라우트로 같은 사건A를 다시 조회하면 차단된다")
# ------------------------------------------------------------
r_fixed = partner2_c.get(f"/api/partner/cases/{cid_expired}/detail")
chk(r_fixed.status_code == 403,
    "★★★★★★ 고친 현재 버전은 같은 사건A(마감 지난 '입찰중')를 403 으로 막는다",
    r_fixed.status_code)

# ── 회귀 방지 — 과잉차단이 아니다 ──────────────────────────────
r_open = partner2_c.get(f"/api/partner/cases/{cid_open}/detail")
j_open = r_open.get_json() or {}
chk(r_open.status_code == 200 and j_open.get("mine") is False,
    "  회귀 방지: 마감이 안 지난 사건B(입찰중)는 여전히 200/mine:false 로 정상 열람된다",
    (r_open.status_code, j_open))
chk("damage_photos" in (j_open.get("case") or {}),
    "  회귀 방지: 라운드563의 damage_photos 응답도 사건B에서 그대로 살아 있다")

r_inprog = partner2_c.get(f"/api/partner/cases/{cid_inprog}/detail")
chk(r_inprog.status_code == 403,
    "  회귀 방지: 아예 다른 상태(시공중·남의 낙찰 건)는 이 라운드 이전처럼 그대로 403이다",
    r_inprog.status_code)

# 소유주 시점(mine=True)은 이 게이트 자체를 타지 않는다 — 마감과 무관하게 항상 열려야 한다
partner1_c = A.app.test_client()
with partner1_c.session_transaction() as sess:
    sess["partner_id"] = p1
    sess["partner_name"] = "R565업체1"
    sess["_csrf"] = "r565-csrf-1"
cid_mine_expired = mkcase("R565-MINE-EXPIRED", "입찰중", partner_id=p1)
conn.execute("INSERT INTO auctions(case_id, deadline, status, created_at) VALUES(?,?,?,?)",
             (cid_mine_expired, "2020-01-01 00:00:00", "진행", DB.now()))
conn.commit()
r_mine = partner1_c.get(f"/api/partner/cases/{cid_mine_expired}/detail")
j_mine = r_mine.get_json() or {}
chk(r_mine.status_code == 200 and j_mine.get("mine") is True,
    "  회귀 방지: mine=True(소유주 본인)는 마감이 지나도 이 게이트와 무관하게 그대로 열린다",
    (r_mine.status_code, j_mine))

# ── 정리 ──────────────────────────────────────────────────────
conn.execute("DELETE FROM auctions WHERE case_id IN (?,?,?)",
             (cid_expired, cid_open, cid_mine_expired))
conn.execute("DELETE FROM cases WHERE id IN (?,?,?,?)",
             (cid_expired, cid_open, cid_inprog, cid_mine_expired))
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
