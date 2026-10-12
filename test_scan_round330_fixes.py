# -*- coding: utf-8 -*-
"""스캔 330라운드 회귀 — api_case_award()(app.py:10615, POST
   /api/cases/<cid>/award, 관리자 대행 낙찰승인) 가 낙찰 사유(reason)를
   무제한 길이로 감사로그에 저장하던 결함[중간], 이 세션 사상 첫
   정밀조사한 정밀조사 Agent가 발견(app.py 감사밀도 기법으로 481개 최상위
   함수 중 "라운드" 언급 0회에 137줄로 최대 크기인 이 함수를 포착 —
   geo.py·legal_docs.py+build_pages.py 배선(실측 재빌드 diff 0건)·
   compliance.py·crypto_util.py·check_tx_paths.py·partner_accounts.py·
   notify_popbill.py 도 함께 조사했으나 이미 견고해 결함 없음, 정당한
   결과).

   같은 함수 안 형제 필드 insurer_instruction(_inst, 10629행)은 이미
   `[:300]`으로 잘리는데(대행 근거를 남기는 필수 입력), 몇 줄 뒤 reason
   (10688행, "최저가 아닌 입찰을 고를 때"만 요구되는 선택 입력)만 그
   관례를 못 받아 그대로 감사로그(10744행)에 들어갔다 — 사실상 무제한
   (MAX_CONTENT_LENGTH 260MB, 사진업로드용). 더 구체적으로는, 형제
   **라우트** `api_insurer_award()`(4269행, 보험사가 직접 승인하는 경로)
   가 바로 이 문제로 196라운드에 `reason[:300]`(4401행)을 이미 받았고,
   그 수정 옆의 주석(4396행)이 "이 낙찰승인 경로만 빠져 있었다"고 적어
   뒀는데 — 그 표현이 가리키던 "빠진 경로"가 관리자 대행 경로
   (api_case_award, 발주처가 전화로 지시했을 때 운영자가 대신 누르는
   창구)에는 애초에 적용된 적이 없었다(같은 결함이 형제 **함수**에서
   그대로 재발, 이 코드베이스 전체에 reason[:300] 관례가 최소 4곳
   (4177·4401·13232·19386행)에 더 있음을 grep으로 확인). 형제와 같은
   `[:300]`을 적용.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_scratch = tempfile.mkdtemp(prefix="bokguon_r330_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_scratch, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"

PASS = FAIL = 0
FAILED = []


def chk(cond, msg, detail=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {msg}")
    else:
        FAIL += 1
        FAILED.append(msg)
        print(f"  [FAIL] {msg}" + (f"   {detail}" if detail else ""))


print("=" * 74)
print("  스캔 330라운드 회귀 — api_case_award() 낙찰사유 무제한 저장")
print("=" * 74)

import db as DB  # noqa: E402
DB.init_db(seed_demo=True)
import app as A  # noqa: E402

print("\n[1] 준비 — 실제 사건 + 입찰중 경매 + 저가·고가 입찰 2건")
conn = DB.get_db()
now = DB.now()
iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R330보험','활성')").lastrowid
p_hi = conn.execute(
    "INSERT INTO partners(name,status,license_status) VALUES('R330고가업체','활성','확인됨')").lastrowid
p_lo = conn.execute(
    "INSERT INTO partners(name,status,license_status) VALUES('R330저가업체','활성','확인됨')").lastrowid
cid = conn.execute(
    "INSERT INTO cases(case_no,status,category,region,insurer_id,est_price,is_demo,created_at) "
    "VALUES('R330-AWARD','입찰중','유리','서울',?,8000000,0,?)", (iid, now)).lastrowid
aid = conn.execute(
    "INSERT INTO auctions(case_id,status,low_price,bid_count,created_at) "
    "VALUES(?,'진행',5000000,2,?)", (cid, now)).lastrowid
conn.execute(
    "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
    "VALUES(?,?,?,5000000,10,?)", (aid, p_lo, "R330저가업체", now))
bid_hi = conn.execute(
    "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
    "VALUES(?,?,?,6000000,10,?)", (aid, p_hi, "R330고가업체", now)).lastrowid
conn.commit()

app_client = A.app.test_client()
_tok = "r330-admin-csrf"
with app_client.session_transaction() as sess:
    sess["admin"] = "admin"
    sess["admin_role"] = "중간관리자"
    sess["_csrf"] = _tok
_hdr = {"X-CSRF-Token": _tok}

print("\n[2] 실행 — 관리자 대행으로 최저가 아닌 업체를 2000자 사유로 낙찰승인")
long_reason = "가" * 2000
resp = app_client.post(
    f"/api/cases/{cid}/award", headers=_hdr,
    json={"bid_id": bid_hi, "reason": long_reason,
          "insurer_instruction": "2026-09-04 유선 지시 — 고가업체로 진행(테스트)"})
j = resp.get_json() or {}
chk(resp.status_code == 200 and j.get("ok") is True,
    "  최저가 아닌 업체 낙찰승인 자체는 근거+사유가 있으면 정상 성공(회귀 없음)",
    (resp.status_code, j))

log_row = conn.execute(
    "SELECT detail FROM activity_log WHERE action='낙찰 승인' ORDER BY id DESC LIMIT 1").fetchone()
chk(log_row is not None, "  '낙찰 승인' 감사로그가 실제로 남는다")
if log_row:
    chk(("가" * 2000) not in log_row["detail"],
        "★★★★★ 감사로그에 2000자 사유 원문이 그대로 안 들어간다"
        "(고치기 전엔 길이제한이 없어 그대로 들어갔다)",
        log_row["detail"][:60] + "...")
    chk(("가" * 300) in log_row["detail"],
        "  잘린 사유(300자)는 여전히 감사로그에 남는다(완전 소실 아님)",
        log_row["detail"][:60] + "...")

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
