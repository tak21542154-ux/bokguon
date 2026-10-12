# -*- coding: utf-8 -*-
"""스캔 86라운드 회귀 — 가격 기준선(가견적) 표시·집행 불일치 2건.

  [F1] admin.js/insurer_portal.html 이 2차(하한) 사건에서 c.est_price 를
    "2차 하한"이라고 표시했다. 사진 없는 접수는 est_price 가 0으로 들어오고,
    실제 하한은 서버가 표준단가로 계산한 bid_floor(엔진 개산 하단)다 —
    화면은 "하한 0원"(=무제한)이라 말하는데 서버는 그 값 아래 입찰을 막는다.
    api_case_detail(app.py) 은 이미 c["bid_floor"] 를 응답에 실어 주는데
    admin.js 가 옆에 있는 그 필드를 안 쓰고 est_price 를 그대로 썼다.

  [F2] api_case_edit 의 1차(상한) 가드가 **최저가(low_price)** 를 봤다.
    상한을 내려서 소급 실격되는 입찰은 새 상한보다 "위"에 있던 입찰이고,
    그중 가장 위험한 건 최고가다 — 최저가만 지켜서는 그보다 높은 다른
    입찰이 새 상한 위에 방치된 채 그대로 낙찰까지 갈 수 있다.
    (2차/하한 방향은 반대로 최저가가 맞는 극값이라 그대로 둔다 — 하한을
     올려 소급 실격되는 입찰은 새 하한보다 "아래"에 있던 입찰이고, 최저가가
     지켜지면 그보다 높은 나머지는 자동으로 다 지켜진다.)

      python test_scan_round86_fixes.py
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
ADMIN_JS = read(os.path.join("static", "admin.js"))
INSURER_HTML = read(os.path.join("templates", "insurer_portal.html"))

print("═" * 72)
print("  스캔 86라운드 회귀 — 가격 기준선(가견적) 표시·집행 불일치")
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
print("\n[1] F1 — admin.js 는 2차 하한 표시에 est_price 대신 bid_floor 를 쓴다")
# ──────────────────────────────────────────────────────────────
_case_detail_fn = _js_fn_body(ADMIN_JS, "async function caseDetail(id){")
chk("c.auction_round===2?c.bid_floor:c.est_price" in _case_detail_fn.replace(" ", ""),
    "★★★ 케이스 상세 통계칸이 2차일 때 bid_floor 를 쓴다(1차는 그대로 est_price)")
chk("표준단가 개산 하한" in _case_detail_fn and "c.bid_floor" in _case_detail_fn,
    "★★ 가견적 수정 입력창 옆에 실제 적용 중인 하한(bid_floor) 안내가 붙는다")

# ══════════════════════════════════════════════════════════════
print("\n[2] F1 — insurer_portal.html 도 같은 자리에서 engine_low 폴백을 쓴다")
# ──────────────────────────────────────────────────────────────
chk("r.case.auction_round===2?(r.case.est_price||a.engine_low):r.case.est_price" in
    INSURER_HTML.replace(" ", ""),
    "★★ 현장견적 승인 모달의 '2차 최소금액' 표시가 est_price=0 일 때 "
    "같은 응답 안의 engine_low 로 폴백한다")

# ══════════════════════════════════════════════════════════════
print("\n[3] F2 — 소스: api_case_edit 1차 가드가 MAX(bid) 를 본다")
# ──────────────────────────────────────────────────────────────
edit_body = _py_fn_body(APP_SRC, "api_case_edit")
chk("MAX(b.amount)" in edit_body and "CAP_BELOW_BID" in edit_body,
    "★★★ 1차(상한) 가드가 최저가 대신 최고 입찰가를 조회해 비교한다")
chk('change_order_id IS NULL' in edit_body.split("MAX(b.amount)")[1][:200],
    "STEP 최고가 조회가 변경견적 재경매 행을 제외한 원경매로 좁혀져 있다")
chk("FLOOR_ABOVE_BID" in edit_body and 'c["low_price"] and est > c["low_price"]' in edit_body,
    "STEP 2차(하한) 가드는 기존 low_price 비교 그대로 남아 있다(회귀 아님)")

# ══════════════════════════════════════════════════════════════
print("\n[4] F2 — 실행: 상한 인하가 기존 고액 입찰을 소급 실격시키는지 서버로 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round86_")
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
    iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R86보험','활성')").lastrowid

    def _mk_case(no, est):
        return conn.execute(
            "INSERT INTO cases(case_no,status,category,region,insurer_id,est_price,low_price) "
            "VALUES(?,'입찰중','가드레일','서울',?,?,0)", (no, iid, est)).lastrowid

    def _mk_auction(cid):
        return conn.execute(
            "INSERT INTO auctions(case_id,change_order_id,kind,round,status,"
            "                     low_price,bid_count,extend_count,deadline,created_at) "
            "VALUES(?,NULL,'원경매',0,'진행',0,0,0,datetime('now','+9 hours','+1 day'),?)",
            (cid, DB.now())).lastrowid

    def _mk_bid(aid, amt, partner_id=0):
        #  ⚠ [424라운드] bids(auction_id,partner_id) 에 부분 UNIQUE 인덱스가
        #    생겨 같은 경매에 파트너당 활성입찰 1건만 허용된다 — "두 입찰"
        #    시나리오는 서로 다른(가짜) 협력사가 낸 것으로 표현해야 한다.
        conn.execute(
            "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,"
            "                 created_at,first_bid_at) VALUES(?,?,'검증업체',?,10,?,?)",
            (aid, partner_id, amt, DB.now(), DB.now()))

    # 시나리오: 상한 10,000,000 에 980만·700만 두 입찰(서로 다른 업체). low_price=700만.
    cid1 = _mk_case("R86-1", 10_000_000)
    aid1 = _mk_auction(cid1)
    _mk_bid(aid1, 9_800_000, partner_id=0)
    _mk_bid(aid1, 7_000_000, partner_id=1)
    conn.execute("UPDATE cases SET low_price=? WHERE id=?", (7_000_000, cid1))

    # 회귀 방지용 2차(하한) 케이스 — field_agreements 로 AG_BROKEN 을 만든다.
    cid2 = _mk_case("R86-2", 0)
    aid2 = _mk_auction(cid2)
    _mk_bid(aid2, 5_500_000)
    conn.execute("UPDATE cases SET low_price=? WHERE id=?", (5_500_000, cid2))
    conn.execute(
        "INSERT INTO field_agreements(case_id,partner_id,partner_name,field_amount,"
        "                             engine_low,engine_high,status,created_at) "
        "VALUES(?,0,'출동업체',5000000,3800000,6200000,?,?)",
        (cid2, A.DP.AG_BROKEN, DB.now()))
    conn.commit(); conn.close()

    admin = A.app.test_client()
    _tok = "r86-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok, "Content-Type": "application/json"}

    # (a) 980만 입찰을 남겨둔 채 750만으로 내리면 — 옛 가드(최저가 700만 기준)는
    #     통과시켰지만, 새 가드는 최고가(980만) 기준으로 막아야 한다.
    r1 = admin.patch(f"/api/cases/{cid1}", json={"est_price": 7_500_000}, headers=_hdr)
    j1 = r1.get_json()
    chk(r1.status_code == 409 and j1.get("code") == "CAP_BELOW_BID",
        "★★★ 최고 입찰(980만)보다 낮은 상한(750만)은 CAP_BELOW_BID 로 거부된다",
        f"status={r1.status_code} body={j1}")

    _c1 = DB.get_db()
    _est1 = _c1.execute("SELECT est_price FROM cases WHERE id=?", (cid1,)).fetchone()["est_price"]
    _c1.close()
    chk(_est1 == 10_000_000,
        "★★ 거부된 요청은 실제로 반영되지 않는다(est_price 그대로 1000만)", f"est_price={_est1}")

    # (b) 최고가(980만) 이상으로는 정상적으로 내릴 수 있어야 한다(과잉 차단 아님).
    r2 = admin.patch(f"/api/cases/{cid1}", json={"est_price": 9_900_000}, headers=_hdr)
    chk(r2.status_code == 200,
        "★★ 모든 입찰(최고 980만) 이상으로 내리는 정상 요청은 그대로 통과한다",
        f"status={r2.status_code} body={r2.get_json()}")

    # (c) 2차(하한) 케이스는 기존 low_price 기준 가드가 회귀 없이 그대로 동작한다.
    r3 = admin.patch(f"/api/cases/{cid2}", json={"est_price": 6_000_000}, headers=_hdr)
    j3 = r3.get_json()
    chk(r3.status_code == 409 and j3.get("code") == "FLOOR_ABOVE_BID",
        "★★ 2차 사건: 하한을 최저입찰(550만) 위로 올리는 시도는 여전히 막힌다(회귀 없음)",
        f"status={r3.status_code} body={j3}")

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드86 서버측 준비/실행", f"{type(e).__name__} {e}")
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
