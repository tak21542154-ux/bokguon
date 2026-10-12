# -*- coding: utf-8 -*-
"""스캔 181라운드 회귀 — 입찰 이력(bid_events.low_flag)이 실제 저가경보 발생
여부를 반영하지 않던 결함.

  ① 재경매 투찰(api_partner_reauction_bid)은 저가경보 조건을 계산해 운영팀에
     통지까지 하고서 bid_events 에는 low_flag=False 를 그대로 고정해 넣었다
     (계산 결과를 완전히 버림).
  ② 원경매 투찰(api_partner_bid)은 두 번째 경보(직전 최저가 대비 — 경쟁가
     유출 방지로 협력사에는 안 보이는 운영팀 전용 경보)가 단독으로 뜬 경우
     low_flag 가 bool(warn)(협력사에게 보이는 문구 유무) 기준이라 거짓으로
     남았다. 이 컬럼의 존재 이유(db.py) 자체가 "그 저가경보가 걸렸던 금액을
     나중에 되짚는 것"이라 두 경우 모두 근거가 사라진다.

      python test_scan_round181_fixes.py
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

print("=" * 72)
print("  스캔 181라운드 회귀 — 입찰이력 low_flag 가 실제 경보와 따로 놀던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_partner_reauction_bid():")
i1 = APP_SRC.index("\n@app.", i0 + 1)
chk("low_flag=low)" in APP_SRC[i0:i1] and "low_flag=False)" not in APP_SRC[i0:i1],
    "★★★ 재경매 투찰이 계산한 저가경보 값을 그대로 이력에 남긴다"
    "(고치기 전엔 False 로 고정돼 계산 결과가 버려졌다)")

i2 = APP_SRC.index("def api_partner_bid():")
i3 = APP_SRC.index("\n@app.", i2 + 1)
body_a = APP_SRC[i2:i3]
chk("low_flag=low)" in body_a and "low_flag=bool(warn))" not in body_a,
    "★★★ 원경매 투찰도 두 경보(가견적·직전최저가) 중 하나라도 뜨면"
    " low_flag 가 참이 된다(고치기 전엔 협력사에 보이는 문구 유무만 봤다)")

# ============================================================
print("\n[2] 실행 — 실제 저가경보가 뜨는 투찰이 이력에도 남는가")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round181_")
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
    iid = conn.execute(
        "INSERT INTO insurers(name,status,login_id,created_at) "
        "VALUES('R181보험사','활성','r181i',?)", (DB.now(),)).lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,login_id,"
        "                     license_status,created_at) "
        "VALUES('R181업체','시행사','활성','가드레일','서울','r181p','확인',?)",
        (DB.now(),)).lastrowid

    # ── ① 재경매 투찰: 저가경보 조건을 확실히 만족시킨다(추가분·상한=1,000,000) ──
    cid_a = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,partner_id,"
        "                  est_price,is_demo,created_at) "
        "VALUES('R181-CO','시공중','가드레일','서울',?,?,1000000,0,?)",
        (iid, pid, DB.now())).lastrowid
    coid = conn.execute(
        "INSERT INTO change_orders(case_id,round,incumbent_partner_id,incumbent_amount,"
        "                          reason,requested_amount,status,created_at) "
        "VALUES(?,1,?,1000000,'실사재현',1000000,'추가경매중',?)",
        (cid_a, pid + 1, DB.now())).lastrowid
    aid_a = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,status,deadline,created_at) "
        "VALUES(?,?,'추가분','진행','2035-01-01 00:00:00',?)",
        (cid_a, coid, DB.now())).lastrowid
    conn.commit()

    partner = A.app.test_client()
    ptok = "r181-partner-csrf"
    with partner.session_transaction() as sess:
        sess["partner_id"] = pid; sess["partner_name"] = "R181업체"; sess["_csrf"] = ptok
    phdr = {"X-CSRF-Token": ptok}

    # 상한(1,000,000원) 대비 20% 넘게 낮은 700,000원 — 저가경보 확실히 발동
    r1 = partner.post("/api/partner/reauction-bids",
                       json={"auction_id": aid_a, "amount": 700000, "days": 10}, headers=phdr)
    j1 = r1.get_json() or {}
    chk(r1.status_code == 200 and j1.get("ok") is True,
        "재경매 투찰 자체는 정상 접수된다", (r1.status_code, j1))

    conn = DB.get_db()
    ev1 = conn.execute(
        "SELECT low_flag FROM bid_events WHERE auction_id=? AND partner_id=? "
        " ORDER BY id DESC LIMIT 1", (aid_a, pid)).fetchone()
    chk(ev1 is not None and ev1["low_flag"] == 1,
        "★★★★ 재경매 투찰의 저가경보가 이력에 남는다"
        "(고치기 전엔 경보가 실제로 떴는데도 low_flag=0 으로 고정됐다)",
        dict(ev1) if ev1 else None)
    conn.close()

    # ── ② 원경매 투찰: '직전 최저가' 경보만 단독으로 뜨는 상황을 구성한다 ──
    #    다른 업체가 이미 큰 폭으로 낮춰(200,000원) low_price 를 눌러 둔 뒤,
    #    이 업체가 그보다는 안 낮지만(750,000원) 직전 최저가 대비로는 낮은
    #    금액을 내면 — 가견적(1,000,000) 대비 20% 기준(800,000)은 안 걸리고
    #    직전 최저가(200,000) 대비 20% 기준(160,000)도 사실 안 걸린다 — 그래서
    #    직접 사건의 low_price 를 조작해 "가견적 기준은 안 걸리는데 직전
    #    최저가 기준만 걸리는" 상황을 재현한다(2차 경매 등에서 실제로 생길 수
    #    있는, 두 기준이 서로 다른 근거를 쓰는 상황의 축소판).
    pid2 = conn = None
    conn = DB.get_db()
    pid2 = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,login_id,"
        "                     license_status,created_at) "
        "VALUES('R181업체2','시행사','활성','가드레일','서울','r181p2','확인',?)",
        (DB.now(),)).lastrowid
    cid_b = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,partner_id,"
        "                  est_price,low_price,is_demo,created_at) "
        "VALUES('R181-ORIG','입찰중','가드레일','서울',?,NULL,1000000,2000000,0,?)",
        (iid, DB.now())).lastrowid
    aid_b = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,status,deadline,created_at) "
        "VALUES(?,NULL,'진행','2035-01-01 00:00:00',?)", (cid_b, DB.now())).lastrowid
    conn.commit()

    partner2 = A.app.test_client()
    ptok2 = "r181-partner2-csrf"
    with partner2.session_transaction() as sess:
        sess["partner_id"] = pid2; sess["partner_name"] = "R181업체2"; sess["_csrf"] = ptok2
    phdr2 = {"X-CSRF-Token": ptok2}

    # 가견적(1,000,000) 기준 20%(800,000)엔 안 걸리지만, low_price(2,000,000)
    # 기준 20%(1,600,000)엔 걸리는 900,000원을 투찰한다.
    r2 = partner2.post("/api/partner/bids",
                        json={"case_id": cid_b, "amount": 900000, "days": 10}, headers=phdr2)
    j2 = r2.get_json() or {}
    if r2.status_code == 200 and j2.get("ok") is True:
        conn = DB.get_db()
        ev2 = conn.execute(
            "SELECT low_flag FROM bid_events WHERE auction_id=? AND partner_id=? "
            " ORDER BY id DESC LIMIT 1", (aid_b, pid2)).fetchone()
        chk(ev2 is not None and ev2["low_flag"] == 1,
            "★★★ 원경매 투찰 — '직전 최저가' 경보만 단독으로 떠도 이력에 남는다"
            "(고치기 전엔 협력사에 안 보이는 이 경보는 warn 에 안 잡혀 놓쳤다)",
            dict(ev2) if ev2 else None)
        conn.close()
    else:
        chk(False, "★ 원경매 투찰(②) 준비 조건이 안 맞음 — 상한/하한 재검토 필요",
            (r2.status_code, j2))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드181 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
