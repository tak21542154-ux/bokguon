# -*- coding: utf-8 -*-
"""스캔 101라운드 회귀 — 업체 상태 3건.

  [1] 협력사 상태 드롭다운(활성·심사중·경고·퇴출) 중 '심사중'만 강등 관문
      (PARTNER_DEMOTED)에 없었다. 그런데 로그인 허용집합은 ("활성","경고")뿐이라
      '심사중'으로 내리면 다음 로그인부터 '퇴출'과 똑같이 401 이 뜬다 — 경고도
      없이 시공중 사건의 완료 보고 창구가 사라진다. 상태값 자체에 대한 검증도
      없어 오타로 죽은 상태를 만들 수 있었다.
  [2] 보험사 포털 사건상세의 입찰목록이 변경견적 '추가분' 입찰과 퇴출 업체
      입찰을 걸러내지 못했다 — 형제(api_case_bids)는 이 정확한 사고("추가분
      80만이 500만 전체공사 최저가로 잡혀 실제로 낙찰까지 갔다")를 주석으로
      남겨 뒀는데 이 함수만 두 필터가 다 없었다.
  [3] 변경견적 추가분 경매 마감(api_co_offer)의 최저가 선정이 취소된 입찰과
      퇴출·정지 업체 입찰을 걸러내지 못했다 — 100라운드가 통일한 원경매 세
      낙찰경로와 달리 이 값은 그대로 combined_amount(정산 기준액)로 굳는다.

      python test_scan_round101_fixes.py
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
print("  스캔 101라운드 회귀 — 심사중 강등관문 우회·보험사 입찰목록 필터누락·추가분 최저가 필터누락")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 세 지점 모두 확인")
# ──────────────────────────────────────────────────────────────
chk('PARTNER_DEMOTED = ("퇴출", "경고", "심사중")' in APP_SRC,
    "★★★ PARTNER_DEMOTED 에 '심사중'이 추가됐다")
chk('PARTNER_STATUSES = ("활성", "심사중", "경고", "퇴출")' in APP_SRC,
    "★★ 업체 상태 허용값 목록이 정의됐다")
pu_body = _py_fn_body(APP_SRC, "api_partner_update")
chk('d[f] not in PARTNER_STATUSES' in pu_body,
    "★★★ api_partner_update 가 상태값을 검증한다(예전엔 아무 문자열이나 그대로 기록)")

icd_body = _py_fn_body(APP_SRC, "api_insurer_case_detail")
chk("a.change_order_id IS NULL" in icd_body,
    "★★★ api_insurer_case_detail 이 원경매만 입찰 후보로 본다(추가분 배제)")
chk("COALESCE(p.status,'활성') = '활성'" in icd_body,
    "★★★ api_insurer_case_detail 이 활성 업체만 입찰 후보로 본다")

co_body = _py_fn_body(APP_SRC, "api_co_offer")
chk("COALESCE(p.status,'활성')='활성'" in co_body,
    "★★★ api_co_offer 의 최저가 선정이 활성 업체만 본다")
chk(co_body.count("voided_at IS NULL") >= 2,
    "★★ api_co_offer 의 최저가·입찰수 집계 둘 다 취소된 입찰을 뺀다")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[4] 실행 — 세 시나리오를 실제로 돌린다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round101_")
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

    # ── [2] '심사중' 강등도 관문에 걸린다 ────────────────────────────
    pid1 = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R101업체1','시행사','활성')"
    ).lastrowid
    conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,is_demo) "
        "VALUES('R101-C1','시공중','가드레일','서울',?,0)", (pid1,))
    conn.commit()

    with A.app.test_request_context():
        blocked = A._partner_demote_gate(conn, pid1, "심사중", False)
    chk(blocked is not None,
        "★★★ '심사중'으로 내릴 때도 진행 사건이 있으면 확인관문이 뜬다"
        "(예전엔 그냥 통과 — 다음 로그인부터 조용히 퇴출과 같은 401)")
    if blocked:
        j, code = blocked
        chk(code == 409 and j.get_json().get("code") == "PARTNER_HAS_WORK",
            "STEP 관문 응답이 PARTNER_HAS_WORK 409 형식이다", (code, j.get_json()))

    admin = A.app.test_client()
    _tok = "r101-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}
    r = admin.patch(f"/api/partners/{pid1}", headers=_hdr, json={"status": "존재안함"})
    chk(r.status_code == 400,
        "★★ 정의되지 않은 상태값은 저장 자체가 거부된다(예전엔 그대로 기록됨)",
        (r.status_code, r.get_json()))

    # ── [3] 보험사 사건상세 — 추가분·퇴출업체 입찰이 후보에서 빠진다 ────
    iid = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('R101보험','활성')").lastrowid
    p_ok = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R101정상','시행사','활성')").lastrowid
    p_retired = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R101퇴출','시행사','퇴출')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
        "VALUES('R101-C2','시공중','가드레일','서울',?,0)", (iid,)).lastrowid
    a_orig = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,NULL,'원경매',0,'마감',5000000,2,0,?,?)", (cid, DB.now(), DB.now())).lastrowid
    a_co = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,999,'추가분',0,'마감',800000,1,0,?,?)", (cid, DB.now(), DB.now())).lastrowid
    conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,5000000,10,?)", (a_orig, p_ok, "R101정상", DB.now()))
    conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,4000000,10,?)", (a_orig, p_retired, "R101퇴출", DB.now()))
    conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,800000,5,?)", (a_co, p_ok, "R101정상", DB.now()))
    conn.commit()

    insurer_c = A.app.test_client()
    with insurer_c.session_transaction() as sess:
        sess["insurer_id"] = iid; sess["insurer_name"] = "R101보험"
    r2 = insurer_c.get(f"/api/insurer/cases/{cid}/detail")
    chk(r2.status_code == 200, "STEP 사건상세 조회 자체는 200 이다", (r2.status_code, r2.get_data(as_text=True)[:300]))
    if r2.status_code == 200:
        j2 = r2.get_json()
        amounts = sorted(b["amount"] for b in j2.get("bids", []))
        chk(amounts == [5000000],
            "★★★ 입찰 후보에 원경매·활성업체 입찰(500만) 하나만 남는다"
            "(예전엔 추가분 80만·퇴출업체 400만까지 섞여 80만이 '최저가'로 보였다)",
            amounts)

    # ── [4] 추가분 마감 — 취소·퇴출업체 입찰을 최저가에서 뺀다 ──────────
    p_active2 = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R101활성2','시행사','활성')").lastrowid
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,award_amount,is_demo) "
        "VALUES('R101-C3','시공중','가드레일','서울',?,3000000,0)", (p_ok,)).lastrowid
    coid = conn.execute(
        "INSERT INTO change_orders(case_id,incumbent_partner_id,incumbent_amount,status,created_at) "
        "VALUES(?,?,3000000,'추가경매중',?)", (cid2, p_ok, DB.now())).lastrowid
    a_co2 = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,?,'추가분',0,'진행',0,3,0,?,?)", (cid2, coid, DB.now(), DB.now())).lastrowid
    conn.execute(  # 가장 싸지만 취소됨 — 후보에서 빠져야 한다
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at,voided_at) "
        "VALUES(?,?,?,100000,5,?,?)", (a_co2, p_active2, "R101활성2", DB.now(), DB.now()))
    conn.execute(  # 두 번째로 싸지만 퇴출업체 — 후보에서 빠져야 한다
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,500000,5,?)", (a_co2, p_retired, "R101퇴출", DB.now()))
    conn.execute(  # 유일한 유효 후보
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,700000,5,?)", (a_co2, p_active2, "R101활성2", DB.now()))
    conn.commit()

    r3 = admin.post(f"/api/change-orders/{coid}/offer", headers=_hdr, json={"force": True})
    chk(r3.status_code == 200, "STEP 추가분 마감 요청 자체는 200 이다", (r3.status_code, r3.get_data(as_text=True)[:300]))
    if r3.status_code == 200:
        j3 = r3.get_json()
        chk(j3.get("add_low") == 700000,
            "★★★ 취소·퇴출업체 입찰을 제외한 진짜 최저가(70만원)가 뽑힌다"
            "(예전엔 취소된 10만원이 최저가로 combined_amount 정산기준액에 그대로 굳었다)",
            j3)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드101 서버측 준비/실행", f"{type(e).__name__} {e}")
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
