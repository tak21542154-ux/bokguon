# -*- coding: utf-8 -*-
"""스캔 196라운드 회귀 — 두 결함.

  ① compliance.py related_sum(): 도급 적법성 관문의 분할회피(살라미 슬라이싱)
    의심 합산 판정이 region 원문 문자열 완전일치로 "같은 지역"을 판정했다.
    cases.region 은 정규화 안 된 자유텍스트라 "인천 남동"과 "인천광역시
    남동구"처럼 같은 지역을 다르게 적으면 합산을 놓친다 — 개별 건이 전문공사
    안전선 아래면 조용히 통과되고, _gate_alert() 는 ok=True 일 때 알림조차
    안 보내 사람이 검토할 기회 자체가 없다. norm_regions() 를 db.py 로
    옮겨(compliance.py 는 순환임포트 때문에 app.py 를 못 본다) 양쪽에서
    같은 정규화를 쓴다.

  ② app.py api_insurer_award(): 보험사가 보내는 낙찰승인 사유(reason)가
    길이제한 없이 activity_log 에 그대로 저장됐다 — 형제 경로(정산 취소 등)
    는 이미 잘라서 저장하는데 이 경로만 빠져 있었다.

      python test_scan_round196_fixes.py
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


CP_SRC = read("compliance.py")
APP_SRC = read("app.py")
DB_SRC = read("db.py")

print("=" * 72)
print("  스캔 196라운드 회귀 — 분할회피 합산의 지역판정 완전일치 · 낙찰사유 무제한저장")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = CP_SRC.index("def related_sum(")
i1 = CP_SRC.index("\ndef ", i0 + 1)
rs_body = CP_SRC[i0:i1]
chk("DB.norm_regions" in rs_body,
    "★★★★ related_sum 이 지역 판정에 DB.norm_regions() 를 쓴다"
    "(고치기 전엔 region 원문 문자열 완전일치였다)")
chk("COALESCE(region,'') = COALESCE(?,'')" not in rs_body,
    "★★★★ 옛 지역 완전일치 SQL 조건이 사라졌다")
chk("def norm_regions(" in DB_SRC and "def region_matches(" in DB_SRC,
    "★★★ norm_regions()/region_matches() 가 db.py 로 옮겨졌다"
    "(compliance.py 는 순환임포트 때문에 app.py 를 못 본다)")
chk("norm_regions = DB.norm_regions" in APP_SRC,
    "★★★ app.py 의 기존 호출부(입찰채점·배차)는 재수출로 그대로 유지된다")

i2 = APP_SRC.index("def api_insurer_award(cid):")
i3 = APP_SRC.index("\ndef ", i2 + 1)
aw_body = APP_SRC[i2:i3]
chk("reason[:300]" in aw_body,
    "★★★ 낙찰승인 사유가 형제(정산 취소 등)와 같이 300자로 잘려 저장된다"
    "(고치기 전엔 길이제한이 전혀 없었다)")

# ============================================================
print("\n[2] 실행 — ① 표기만 다른 같은 지역(인천 남동 vs 인천광역시 남동구)이 "
      "합산에 잡히고, 진짜 다른 지역(서울 vs 부산)은 안 잡힌다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round196_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import compliance as CP

    conn = DB.get_db()
    now = DB.now()
    iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R196보험','활성')").lastrowid

    def mk_case(no, region, amount=8_000_000):
        return conn.execute(
            "INSERT INTO cases(case_no,status,category,region,insurer_id,est_price,"
            "                  is_demo,created_at) "
            "VALUES(?,'접수','유리',?,?,?,0,?)", (no, region, iid, amount, now)).lastrowid

    # ① 표기만 다른 같은 지역 — 지금까지는 완전일치라 서로 안 보였다
    c1a = mk_case("R196-1A", "인천 남동")
    c1b = mk_case("R196-1B", "인천광역시 남동구")
    # ② 진짜 다른 지역 — 회귀 없음 확인용
    c2a = mk_case("R196-2A", "서울")
    c2b = mk_case("R196-2B", "부산")
    # ③ 정규화가 안 되는 표기 — 보수적으로 합산 쪽에 포함돼야 한다
    c3a = mk_case("R196-3A", "전국")
    c3b = mk_case("R196-3B", "경기")
    conn.commit()

    total1, related1 = CP.related_sum(conn, c1a)
    total2, related2 = CP.related_sum(conn, c2a)
    total3, related3 = CP.related_sum(conn, c3a)

    chk(any(r["id"] == c1b for r in related1) and total1 >= 8_000_000,
        "★★★★ '인천 남동'과 '인천광역시 남동구'가 같은 지역으로 합산된다"
        "(고치기 전엔 문자열이 달라 서로 안 보였다)", (total1, related1))
    chk(not any(r["id"] == c2b for r in related2),
        "★★★ '서울'과 '부산'처럼 진짜 다른 지역은 합산되지 않는다(회귀 없음)",
        (total2, related2))
    chk(any(r["id"] == c3b for r in related3),
        "★★★ 정규화가 안 되는 표기('전국')는 다른 지역이라 단정하지 않고 "
        "보수적으로 합산에 포함된다('애매하면 도급불가' 원칙)", (total3, related3))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드196 [2] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — ② 보험사가 보낸 낙찰승인 사유가 300자로 잘려 저장된다")
# ------------------------------------------------------------
try:
    import app as A

    conn = DB.get_db()
    now2 = DB.now()
    iid2 = conn.execute(
        "INSERT INTO insurers(name,status,login_id) VALUES('R196보험2','활성','r196ins')"
    ).lastrowid
    p_hi = conn.execute(
        "INSERT INTO partners(name,status,license_status) VALUES('R196고가업체','활성','확인됨')"
    ).lastrowid
    p_lo = conn.execute(
        "INSERT INTO partners(name,status,license_status) VALUES('R196저가업체','활성','확인됨')"
    ).lastrowid
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,est_price,is_demo,created_at) "
        "VALUES('R196-AWARD','입찰중','유리','서울',?,8000000,0,?)", (iid2, now2)).lastrowid
    aid2 = conn.execute(
        "INSERT INTO auctions(case_id,status,low_price,bid_count,created_at) "
        "VALUES(?,'진행',5000000,2,?)", (cid2, now2)).lastrowid
    conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,5000000,10,?)", (aid2, p_lo, "R196저가업체", now2))
    bid_hi = conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,6000000,10,?)", (aid2, p_hi, "R196고가업체", now2)).lastrowid
    conn.commit()

    insurer_c = A.app.test_client()
    tok = "r196-insurer-csrf"
    with insurer_c.session_transaction() as sess:
        sess["insurer_id"] = iid2; sess["insurer_name"] = "R196보험2"; sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    long_reason = "가" * 2000
    resp = insurer_c.post(f"/api/insurer/cases/{cid2}/award",
                           json={"bid_id": bid_hi, "reason": long_reason}, headers=hdr)
    j = resp.get_json() or {}

    log_row = conn.execute(
        "SELECT detail FROM activity_log WHERE action='낙찰 승인' AND detail LIKE ? "
        " ORDER BY id DESC LIMIT 1", (f"%{cid2}%",)).fetchone()
    if not log_row:
        log_row = conn.execute(
            "SELECT detail FROM activity_log WHERE action='낙찰 승인' "
            " ORDER BY id DESC LIMIT 1").fetchone()

    chk(resp.status_code == 200 and j.get("ok") is True,
        "최저가 아닌 업체 낙찰승인 자체는 사유가 있으면 정상 성공한다(회귀 없음)",
        (resp.status_code, j))
    chk(log_row is not None and "가" * 2000 not in log_row["detail"],
        "★★★★ 감사로그에 2000자 사유 원문이 그대로 안 들어간다"
        "(고치기 전엔 길이제한이 없어 그대로 들어갔다)",
        (log_row["detail"][:50] + "..." if log_row else None))
    chk(log_row is not None and "가" * 300 in log_row["detail"],
        "★★★ 잘린 사유(300자)는 여전히 감사로그에 남는다(완전 소실 아님)",
        (log_row["detail"][:50] + "..." if log_row else None))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드196 [3] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
