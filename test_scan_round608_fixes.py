# -*- coding: utf-8 -*-
"""스캔 608라운드 회귀 — round607이 인계한 마지막 배치(58곳·38개함수, 정확한
   목록은 세션 종료로 소멸)를 app.py 전체 재정규식스윕으로 다시 찾아 직접
   Read로 하나씩 실결함 여부를 확인했다.

   조사 배경 — 시작 전 wc -l app.py가 직전 라운드(607) 종료시점과 정확히
   22050줄로 일치해 동시편집은 없었다.

   round607이 지목한 우선 후보 3개는 위협모델이 다르다는 지시를 그대로
   따라 write경로부터 추적했다:
     · api_partner_dashboard(6곳: bank_account_enc·bank_holder·phone·region·
       biz_no·major) — 전부 partners 테이블 DB row(me) 재읽기. 6개 컬럼
       모두 db.py 선언이 TEXT(TEXT affinity)이고, sqlite3 자체 실험으로
       확인: TEXT affinity 컬럼은 저장 시점에 int/float/bool을 전부 TEXT로
       강제 변환하고(레코드에 남는 값 자체가 항상 str/None), dict/list는
       바인딩 자체가 ProgrammingError로 즉시 막혀 저장되지 않는다. 즉
       "쓰기가 성공했다"는 사실 자체가 "값이 str이거나 None"을 보증한다
       (파라미터화 쿼리 전제). 6곳 write경로(주로 api_partner_account_set·
       api_partner_create·api_partner_update)를 확인해 전부 `?` 파라미터
       바인딩만 쓰는 것도 재확인 — ★★★★★ 클린(결함 아님, 수정 불필요).
     · _payout_account_gate(4곳) — 3곳(bank_account_enc·bank_holder 재읽기
       2곳)은 같은 이유로 클린. 그런데 4번째 자리(reason = (override_reason
       or "").strip())는 DB row가 아니라 **함수 파라미터**였고, 호출부 2곳
       전부 body().get("no_account_reason")(순수 JSON 본문 원시값)을 그대로
       넘기고 있었다 — ★★★★★ 실결함(round601~ 형제결함군과 동일).
     · api_co_close_full(3곳) — insurer_ack 재읽기(co, DB row)는 클린,
       reason·insurer_instruction 2곳은 d=body() JSON 원시값 — ★★★★★ 실결함.

   나머지는 자체 재스윕(정규식 + request.args/os.environ 지역별칭 제외)으로
   찾아 함수별로 직접 확인했다. 이번 라운드가 처리한 실결함 25곳(25개
   함수 + 공유헬퍼 valid_biz_no 1곳, 일부 함수는 2~3곳) — api_settlement_undo
   의 reason은 round498/506 콜리전 조사 중 자체발견해 같은 패턴으로 즉시
   처리했다(round609 인계목록에서 제외):
     ① api_memo_create — body(메모 본문)
     ② valid_biz_no(공유헬퍼, 호출부 8곳 전체에 영향) — re.sub 3번째 인자
     ③ api_otp_confirm — code
     ④ api_partner_account_set — bank_account(re.sub)
     ⑤ api_partner_create — biz_no(re.sub, valid_biz_no와 별개로 저장값
       자체도 재사용)
     ⑥ api_partner_update — biz_no(re.sub, d[f] 재대입) / address(비교식) /
       status_reason — 3곳
     ⑦ api_insurer_update — status_reason(api_partner_update와 동일 리터럴)
     ⑧ api_co_withdraw — reason
     ⑨ api_co_withdraw_offer — reason
     ⑩ api_co_close_full — reason / insurer_instruction — 2곳
     ⑪ api_photo_reject — reason
     ⑫ api_settlement_paid — memo
     ⑬ api_settlements_paid_bulk — memo
     ⑭ api_settlement_transfer — defect_override_reason
     ⑮ api_settlement_void — reason
     ⑯ _payout_account_gate — override_reason(위 설명)
     ⑰ api_settlement_review — defect_override_reason
     ⑱ api_outbox_test_send — phone
     ⑲ api_outbox_handled — note
     ⑳ api_boq_update — price_src(삼항식이라 단순정규식엔 안 걸림) /
       price_date(같은 삼항식, "본문에 있을 때" 분기는 or "" 폴백조차
       없어 null만 보내도 슬라이스에서 TypeError) — 2곳
     ㉑ api_case_to_dispatch — reason
     ㉒ api_case_cancel_award — reason
     ㉓ api_case_close_offline — reason
     ㉔ api_case_undo_no_repair — reason
     ㉕ api_case_award — insurer_instruction(bid_id 검증보다도 앞, DB
       접근 전) / reason — 2곳
     ㉖ api_settlement_undo — reason(round498/506 콜리전 조사 중 자체발견,
       나머지 8개 reason 자리와 완전히 같은 패턴이라 즉시 처리)

   전부 형제 헬퍼 `_s(v, n=None)`(1503행)을 그대로 재사용했다 — 새 헬퍼·
   새 로직 없음.

   확인했지만 손대지 않은 자리(클린 판정, 근거):
     · api_partner_dashboard 6곳·_payout_account_gate의 DB row 3곳 — 위 설명.
     · _insurer_ack_ok·api_co_decision의 co.get("insurer_ack") — change_orders
       테이블 TEXT 컬럼, DB row.
     · api_partner_profile의 bank_account_masked — CRYPTO.mask_account()가
       항상 str을 반환(빈 문자열 포함), DB round-trip 자체가 없음.
     · api_defect_update의 cost_bearer — round604가 이미 "위에서 화이트리스트
       검증을 거쳐야만 도달"이라고 확정한 자리(주석 15561행 부근 그대로 존재).
     · api_partner_defect_dispute — round604가 이미 _s()로 고쳐 둠(재확인만).
     · _create_case/api_case_create의 est_price — str(d.get(...) or "")로
       이미 str() 강제가 걸려 있어 .strip() 이전에 항상 안전.
     · api_auction_set_deadline의 deadline — 위와 동일(str() 강제).
     · _partner_filter·_case_filter·_settle_filter·_activity_filter·
       _onboard_where/_onboard_rows — 전부 request.args 지역별칭(파라미터
       이름이 args여도 호출부 전수 확인 결과 request.args만 전달됨).
     · _victim_notice의 LD.INFO — 외부 입력이 아닌 정적 설정 딕셔너리.
     · api_outbox·api_partner_onboarding_export·api_boq·api_notice_delete·
       _notif_link·_bid_scores·_photo_visible_to — 전부 DB row(TEXT 컬럼).

   round609에 인계 — 이번에 재스윕으로 찾았으나 시간 관계상 개별 확인을
   못 한 나머지(정확한 현재 줄번호는 이 라운드 종료 시점 app.py 기준):
     api_admin_create(username·name)·api_admin_update(name)·
     api_me_update(name)·api_unlock_login(username)·
     api_create_application(address)·api_insurer_create(name)·
     api_insurer_credentials(login_id 2곳)·api_insurer_webhook_set
     (webhook_url)·api_contact_update(v=d.get(f) 루프)·
     _attach_defect_photos(item.get("note"))·
     api_notice_create(body)·api_boq_create(price_src·price_date)·
     api_case_open_auction(est_basis)·api_field_agreement_open(pattern)·
     api_happy_call_add(feedback·method, .strip() 없는 슬라이스만).
     _gate_alert의 res.get("reason")도 미확정 — res는 CP.record_gate()의
     내부 계산 결과라 외부 공격자 입력이 아니고 위협모델이 다르므로 낮은
     우선순위로 남긴다.

       python test_scan_round608_fixes.py
"""
import hashlib
import io
import os
import shutil
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


def _code_only(body):
    """주석 줄(이번 수정 설명 안에 옛 raw 패턴 문자열이 그대로 인용돼 있어,
       주석까지 검색하면 '옛 패턴이 아직 있다'는 오탐이 난다)을 빼고
       실제 코드 줄만 이어붙인다."""
    return "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("#"))


print("=" * 72)
print("  스캔 608라운드 회귀 — round607 인계 배치 재스윕 25곳(25개함수+공유헬퍼),")
print("  raw .strip()/re.sub/슬라이스 형제결함군(round601~607과 같은 부류)")
print("=" * 72)

APP_SRC = read("app.py")

# ==================================================================
print("\n[0] 소스 확인 — 25곳 전부 옛 raw 패턴이 사라지고 _s()로 바뀌었다")
# ------------------------------------------------------------------
try:
    chk('d = re.sub(r"[^0-9]", "", s or "")' not in APP_SRC
        and 'd = re.sub(r"[^0-9]", "", _s(s))' in APP_SRC,
        "★★★★★ valid_biz_no(공유헬퍼, 호출부 8곳 전체 영향) — re.sub 3번째 인자")

    amc = _code_only(_py_fn_body(APP_SRC, "api_memo_create"))
    chk('b = (d.get("body") or "").strip()' not in amc and 'b = _s(d.get("body"))' in amc,
        "★★★★★ api_memo_create — body")

    aoc = _code_only(_py_fn_body(APP_SRC, "api_otp_confirm"))
    chk('code = (body().get("code") or "").strip()[:16]' not in aoc
        and 'code = _s(body().get("code"), 16)' in aoc,
        "★★★★★ api_otp_confirm — code")

    apas = _code_only(_py_fn_body(APP_SRC, "api_partner_account_set"))
    chk('re.sub(r"[^0-9]", "", (d.get("bank_account") or ""))' not in apas
        and 're.sub(r"[^0-9]", "", _s(d.get("bank_account")))' in apas,
        "★★★★★ api_partner_account_set — bank_account(re.sub)")

    apc = _code_only(_py_fn_body(APP_SRC, "api_partner_create"))
    chk('_biz = re.sub(r"[^0-9]", "", d.get("biz_no") or "")' not in apc
        and '_biz = re.sub(r"[^0-9]", "", _s(d.get("biz_no")))' in apc,
        "★★★★★ api_partner_create — biz_no(re.sub)")

    apu = _code_only(_py_fn_body(APP_SRC, "api_partner_update"))
    chk('d[f] = re.sub(r"[^0-9]", "", d[f])' not in apu
        and 'd[f] = re.sub(r"[^0-9]", "", _s(d[f]))' in apu,
        "★★★★★ api_partner_update — biz_no(re.sub, d[f] 재대입)")
    chk('(d.get("address") or "").strip() != (prev["address"] or "")' not in apu
        and '_s(d.get("address")) != (prev["address"] or "")' in apu,
        "★★★★★ api_partner_update — address(비교식)")
    chk('reason = (d.get("status_reason") or "").strip()[:300]' not in apu
        and 'reason = _s(d.get("status_reason"), 300)' in apu,
        "★★★★★ api_partner_update — status_reason")

    aiu = _code_only(_py_fn_body(APP_SRC, "api_insurer_update"))
    chk('reason = (d.get("status_reason") or "").strip()[:300]' not in aiu
        and 'reason = _s(d.get("status_reason"), 300)' in aiu,
        "★★★★★ api_insurer_update — status_reason")

    acw = _code_only(_py_fn_body(APP_SRC, "api_co_withdraw"))
    chk('reason = (body().get("reason") or "").strip()[:200]' not in acw
        and 'reason = _s(body().get("reason"), 200)' in acw,
        "★★★★★ api_co_withdraw — reason")

    acwo = _code_only(_py_fn_body(APP_SRC, "api_co_withdraw_offer"))
    chk('reason = (body().get("reason") or "").strip()[:200]' not in acwo
        and 'reason = _s(body().get("reason"), 200)' in acwo,
        "★★★★★ api_co_withdraw_offer — reason")

    accf = _code_only(_py_fn_body(APP_SRC, "api_co_close_full"))
    chk('reason = (d.get("reason") or "").strip()' not in accf
        and "reason = _s(d.get(\"reason\"))" in accf,
        "★★★★★ api_co_close_full — reason")
    chk('_inst = (d.get("insurer_instruction") or "").strip()[:300]' not in accf
        and '_inst = _s(d.get("insurer_instruction"), 300)' in accf,
        "★★★★★ api_co_close_full — insurer_instruction")

    apr = _code_only(_py_fn_body(APP_SRC, "api_photo_reject"))
    chk('reason = (body().get("reason") or "").strip()[:200]' not in apr
        and 'reason = _s(body().get("reason"), 200)' in apr,
        "★★★★★ api_photo_reject — reason")

    asp = _code_only(_py_fn_body(APP_SRC, "api_settlement_paid"))
    chk('memo = (body().get("memo") or "").strip()[:100]' not in asp
        and 'memo = _s(body().get("memo"), 100)' in asp,
        "★★★★★ api_settlement_paid — memo")

    aspb = _code_only(_py_fn_body(APP_SRC, "api_settlements_paid_bulk"))
    chk('memo = (body().get("memo") or "").strip()[:100]' not in aspb
        and 'memo = _s(body().get("memo"), 100)' in aspb,
        "★★★★★ api_settlements_paid_bulk — memo")

    ast_ = _code_only(_py_fn_body(APP_SRC, "api_settlement_transfer"))
    chk('_dov = (body().get("defect_override_reason") or "").strip()[:200]' not in ast_
        and '_dov = _s(body().get("defect_override_reason"), 200)' in ast_,
        "★★★★★ api_settlement_transfer — defect_override_reason")

    asv = _code_only(_py_fn_body(APP_SRC, "api_settlement_void"))
    chk('reason = (body().get("reason") or "").strip()' not in asv
        and "reason = _s(body().get(\"reason\"))" in asv,
        "★★★★★ api_settlement_void — reason")

    asu = _code_only(_py_fn_body(APP_SRC, "api_settlement_undo"))
    chk('reason = (d.get("reason") or "").strip()' not in asu
        and "reason = _s(d.get(\"reason\"))" in asu,
        "★★★★★ api_settlement_undo — reason(자체발견, round609 인계목록에서 "
        "즉시 처리 — 이미 고친 8개 reason 자리와 동일 패턴)")

    pag = _code_only(_py_fn_body(APP_SRC, "_payout_account_gate"))
    chk('reason = (override_reason or "").strip()' not in pag
        and "reason = _s(override_reason)" in pag,
        "★★★★★ _payout_account_gate — override_reason(함수 파라미터, "
        "호출부 2곳 전부 body().get('no_account_reason') 원시값)")

    asr = _code_only(_py_fn_body(APP_SRC, "api_settlement_review"))
    chk('_dov = (body().get("defect_override_reason") or "").strip()[:200]' not in asr
        and '_dov = _s(body().get("defect_override_reason"), 200)' in asr,
        "★★★★★ api_settlement_review — defect_override_reason")

    aots = _code_only(_py_fn_body(APP_SRC, "api_outbox_test_send"))
    chk('POPBILL.normalize_phone((body().get("phone") or "").strip())' not in aots
        and 'POPBILL.normalize_phone(_s(body().get("phone")))' in aots,
        "★★★★★ api_outbox_test_send — phone")

    aoh = _code_only(_py_fn_body(APP_SRC, "api_outbox_handled"))
    chk('note = (body().get("note") or "").strip()[:200]' not in aoh
        and 'note = _s(body().get("note"), 200)' in aoh,
        "★★★★★ api_outbox_handled — note")

    abu = _code_only(_py_fn_body(APP_SRC, "api_boq_update"))
    chk('src = (d.get("price_src") if "price_src" in d else cur_row.get("price_src")) or ""' not in abu
        and 'src = _s(d.get("price_src") if "price_src" in d else cur_row.get("price_src"))' in abu,
        "★★★★★ api_boq_update — price_src(삼항식이라 단순정규식엔 안 걸림)")
    chk('else cur_row.get("price_date") or "")[:20]' not in abu
        and 'else cur_row.get("price_date"), 20)' in abu,
        "★★★★★ api_boq_update — price_date(같은 삼항식, or \"\" 폴백조차 없던 "
        "\"본문에 있음\" 분기 — null만 보내도 슬라이스에서 TypeError였다)")

    actd = _code_only(_py_fn_body(APP_SRC, "api_case_to_dispatch"))
    chk('reason = (body().get("reason") or "").strip()[:200]' not in actd
        and 'reason = _s(body().get("reason"), 200)' in actd,
        "★★★★★ api_case_to_dispatch — reason")

    acca = _code_only(_py_fn_body(APP_SRC, "api_case_cancel_award"))
    chk('reason = (body().get("reason") or "").strip()' not in acca
        and "reason = _s(body().get(\"reason\"))" in acca,
        "★★★★★ api_case_cancel_award — reason")

    acco = _code_only(_py_fn_body(APP_SRC, "api_case_close_offline"))
    chk('reason = (body().get("reason") or "").strip()[:200]' not in acco
        and 'reason = _s(body().get("reason"), 200)' in acco,
        "★★★★★ api_case_close_offline — reason")

    acun = _code_only(_py_fn_body(APP_SRC, "api_case_undo_no_repair"))
    chk('reason = (body().get("reason") or "").strip()[:200]' not in acun
        and 'reason = _s(body().get("reason"), 200)' in acun,
        "★★★★★ api_case_undo_no_repair — reason")

    aca = _code_only(_py_fn_body(APP_SRC, "api_case_award"))
    chk('_inst = (d.get("insurer_instruction") or "").strip()[:300]' not in aca
        and '_inst = _s(d.get("insurer_instruction"), 300)' in aca,
        "★★★★★ api_case_award — insurer_instruction(bid_id 검증보다도 앞)")
    chk('reason = (d.get("reason") or "").strip()[:300]' not in aca
        and 'reason = _s(d.get("reason"), 300)' in aca,
        "★★★★★ api_case_award — reason")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드608 [0] 소스 확인", f"{type(e).__name__} {e}")

APP_HASH_BEFORE = hashlib.sha256(APP_SRC.encode("utf-8")).hexdigest()

# ==================================================================
print("\n[1] 준비 — 스크래치 DB, 관리자(최고관리자) 1명 + 사건 1건(원경매+"
      "전체재경매 각각 입찰 1건) + 협력사 2곳(계좌있음/계좌없음) + 정산 2건 + "
      "표준내역 1건")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round608_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "bokguon.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r608-csrf"
H = {"X-CSRF-Token": CSRF}
A = DB = None
cid = pid_ok = pid_nobank = iid = bid_id_orig = coid = bid_id_co = sid_paid = sid_transfer = boq_id = None
sid_paid2 = sid_transfer2 = None

try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    conn0.execute(
        "INSERT INTO admins(username,password_hash,name,role) "
        "VALUES('r608admin','x','검증','최고관리자')")
    cid = conn0.execute(
        "INSERT INTO cases(case_no,status,category,region,address,manager) "
        "VALUES('R608CASE','입찰중','금속','서울','서울 강남구 1','담당자')").lastrowid
    pid_ok = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,major,region,"
        "bank_name,bank_holder,bank_account_enc) VALUES('R608계좌있음업체',"
        "'시공사','활성','금속','서울','국민','홍길동','ENCDUMMY')").lastrowid
    pid_nobank = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,major,region) "
        "VALUES('R608계좌없음업체','시공사','활성','금속','서울')").lastrowid
    iid = conn0.execute(
        "INSERT INTO insurers(name,status) VALUES('R608보험사','활성')").lastrowid

    #  원경매 + 입찰 1건 (api_case_award용 — 유일한 입찰이라 항상 최저가)
    aid_orig = conn0.execute(
        "INSERT INTO auctions(case_id,status) VALUES(?, '진행')", (cid,)).lastrowid
    bid_id_orig = conn0.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days) "
        "VALUES(?,?,?,?,?)", (aid_orig, pid_ok, "R608계좌있음업체", 5000000, 3)).lastrowid

    #  전체재경매(change_orders) + 그 경매(이미 마감시각 지남) + 입찰 1건
    #  (api_co_close_full용) — 사건 상태는 '시공중'으로 바꿔야 UPDATE가 먹는다
    conn0.execute("UPDATE cases SET status='시공중' WHERE id=?", (cid,))
    coid = conn0.execute(
        "INSERT INTO change_orders(case_id,round,status) VALUES(?,1,'전체재경매중')",
        (cid,)).lastrowid
    aid_co = conn0.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,status,deadline) "
        "VALUES(?,?,'전체재경매','진행','2020-01-01 00:00:00')", (cid, coid)).lastrowid
    bid_id_co = conn0.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days) "
        "VALUES(?,?,?,?,?)", (aid_co, pid_ok, "R608계좌있음업체", 4000000, 3)).lastrowid

    #  정산 1건(insurer_approved=1) — api_settlement_paid/paid_bulk용
    sid_paid = conn0.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_name,partner_id,"
        "amount,fee,payout,insurer_approved,insurer_paid,review_status,transfer_status) "
        "VALUES(?,'R608CASE','R608보험사','R608계좌있음업체',?,5000000,500000,4500000,"
        "1,'대기','대기','대기')", (cid, pid_ok)).lastrowid

    #  정산 1건(review_status='승인', insurer_paid='입금완료', 계좌없는 업체) —
    #  api_settlement_transfer → _payout_account_gate(override_reason)용
    sid_transfer = conn0.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_name,partner_id,"
        "amount,fee,payout,insurer_paid,review_status,transfer_status) "
        "VALUES(?,'R608CASE','R608보험사','R608계좌없음업체',?,4000000,400000,3600000,"
        "'입금완료','승인','대기')", (cid, pid_nobank)).lastrowid

    boq_id = conn0.execute(
        "INSERT INTO standard_boq(major,item,spec,unit,ref_price) "
        "VALUES('금속','가드레일','표준형','m',50000)").lastrowid

    #  [4] 되돌리기 절에서 쓸 여분 — sid_paid/sid_transfer는 [2] 실행절에서
    #  실제로 상태가 전이될 수 있어(200 완주), 되돌리기 재현이 "이미 처리된
    #  건이라 409"로 오염되지 않도록 손대지 않은 짝을 하나씩 더 심는다.
    sid_paid2 = conn0.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_name,partner_id,"
        "amount,fee,payout,insurer_approved,insurer_paid,review_status,transfer_status) "
        "VALUES(?,'R608CASE','R608보험사','R608계좌있음업체',?,5000000,500000,4500000,"
        "1,'대기','대기','대기')", (cid, pid_ok)).lastrowid
    sid_transfer2 = conn0.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_name,partner_id,"
        "amount,fee,payout,insurer_paid,review_status,transfer_status) "
        "VALUES(?,'R608CASE','R608보험사','R608계좌없음업체',?,4000000,400000,3600000,"
        "'입금완료','승인','대기')", (cid, pid_nobank)).lastrowid

    conn0.commit()
    conn0.close()
    chk(all([cid, pid_ok, pid_nobank, iid, bid_id_orig, coid, bid_id_co,
              sid_paid, sid_transfer, boq_id, sid_paid2, sid_transfer2]),
        "STEP 사건·협력사 2곳·보험사·원경매+입찰·전체재경매+입찰·정산 4건·표준내역 픽스처 생성",
        dict(cid=cid, pid_ok=pid_ok, pid_nobank=pid_nobank, iid=iid,
             bid_id_orig=bid_id_orig, coid=coid, bid_id_co=bid_id_co,
             sid_paid=sid_paid, sid_transfer=sid_transfer, boq_id=boq_id,
             sid_paid2=sid_paid2, sid_transfer2=sid_transfer2))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드608 [1] 준비", f"{type(e).__name__} {e}")


def _admin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "r608admin"; sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = CSRF
    return c


# ==================================================================
print("\n[2] 실행 — 각 라우트에 비문자열(JSON 정수/불리언/null) 값을 보내도 "
      "500이 아니다")
# ------------------------------------------------------------------
def _post(path, **kw):
    return _admin_client().post(path, headers=H, **kw)


def _patch(path, **kw):
    return _admin_client().patch(path, headers=H, **kw)


try:
    r = _post("/api/memos", json={"target_type": "case", "target_id": cid, "body": 608001})
    rb = r.get_json() or {}
    chk(r.status_code == 200 and rb.get("ok") is True,
        "★★★★★ api_memo_create — body를 JSON 정수로 보내도 500 대신 200", (r.status_code, rb))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_memo_create", f"{type(e).__name__} {e}")

try:
    r = _post("/api/me/otp/confirm", json={"code": 608002})
    chk(r.status_code != 500,
        "★★★★★ api_otp_confirm — code를 JSON 정수로 보내도 500이 아니다"
        "(_is_internal_ip 게이트가 403을 줄 수도 있다 — 크래시 여부만 확인)",
        (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_otp_confirm", f"{type(e).__name__} {e}")

try:
    r = _post("/api/partners", json={"name": "R608신규업체", "biz_no": 6080030001})
    chk(r.status_code != 500,
        "★★★★★ api_partner_create(valid_biz_no 경유) — biz_no를 JSON 정수로 "
        "보내도 500이 아니다(체크섬 통과 여부는 무관 — 크래시 여부만 확인)",
        (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_partner_create", f"{type(e).__name__} {e}")

try:
    r = _patch(f"/api/partners/{pid_ok}/account", json={"bank_account": 608004})
    chk(r.status_code != 500,
        "★★★★★ api_partner_account_set — bank_account를 JSON 정수로 보내도 "
        "500이 아니다", (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_partner_account_set", f"{type(e).__name__} {e}")

try:
    r = _patch(f"/api/partners/{pid_ok}", json={"biz_no": 6080050001})
    chk(r.status_code != 500,
        "★★★★★ api_partner_update — biz_no를 JSON 정수로 보내도 500이 아니다"
        "(re.sub 3번째 인자, d[f] 재대입)", (r.status_code, r.get_json()))

    r2 = _patch(f"/api/partners/{pid_ok}", json={"address": 608006})
    rb2 = r2.get_json() or {}
    chk(r2.status_code == 200 and rb2.get("ok") is True,
        "★★★★★ api_partner_update — address를 JSON 정수로 보내도 500 대신 200",
        (r2.status_code, rb2))
    if rb2.get("ok"):
        prow = DB.get_db().execute(
            "SELECT address FROM partners WHERE id=?", (pid_ok,)).fetchone()
        chk(prow and prow["address"] == "608006",
            "STEP partners.address가 문자열로 저장됐다", dict(prow) if prow else None)

    r3 = _patch(f"/api/partners/{pid_ok}", json={"status": "경고", "status_reason": 608007})
    chk(r3.status_code != 500,
        "★★★★★ api_partner_update — status_reason을 JSON 정수로 보내도 500이 "
        "아니다", (r3.status_code, r3.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_partner_update", f"{type(e).__name__} {e}")

try:
    r = _patch(f"/api/insurers/{iid}", json={"status": "중지", "status_reason": 608008})
    chk(r.status_code != 500,
        "★★★★★ api_insurer_update — status_reason을 JSON 정수로 보내도 500이 "
        "아니다", (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_insurer_update", f"{type(e).__name__} {e}")

try:
    r = _post(f"/api/change-orders/{coid}/withdraw", json={"reason": 608009})
    chk(r.status_code != 500,
        "★★★★★ api_co_withdraw — reason을 JSON 정수로 보내도 500이 아니다"
        "(상태가 안 맞아 409일 수 있다 — 크래시 여부만 확인)",
        (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_co_withdraw", f"{type(e).__name__} {e}")

try:
    r = _post(f"/api/change-orders/{coid}/withdraw-offer", json={"reason": 608010})
    chk(r.status_code != 500,
        "★★★★★ api_co_withdraw_offer — reason을 JSON 정수로 보내도 500이 "
        "아니다", (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_co_withdraw_offer", f"{type(e).__name__} {e}")

try:
    r = _post(f"/api/change-orders/{coid}/close-full",
              json={"bid_id": bid_id_co, "reason": 608011, "insurer_instruction": 608012})
    rb = r.get_json() or {}
    chk(r.status_code == 200 and rb.get("ok") is True,
        "★★★★★ api_co_close_full — reason/insurer_instruction을 JSON 정수로 "
        "보내도 500 대신 200(전체재경매 낙찰 확정까지 완주)", (r.status_code, rb))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_co_close_full", f"{type(e).__name__} {e}")

try:
    r = _post("/api/photos/999999/reject", json={"reason": 608013})
    chk(r.status_code != 500,
        "★★★★★ api_photo_reject — reason을 JSON 정수로 보내도 500이 아니다"
        "(사진이 없어 404일 수 있다 — 크래시 여부만 확인)",
        (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_photo_reject", f"{type(e).__name__} {e}")

try:
    r = _post(f"/api/settlements/{sid_paid}/paid", json={"memo": 608014})
    rb = r.get_json() or {}
    chk(r.status_code == 200 and rb.get("ok") is True,
        "★★★★★ api_settlement_paid — memo를 JSON 정수로 보내도 500 대신 200",
        (r.status_code, rb))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_settlement_paid", f"{type(e).__name__} {e}")

try:
    r = _post("/api/settlements/paid-bulk", json={"ids": [999999], "memo": 608015})
    chk(r.status_code != 500,
        "★★★★★ api_settlements_paid_bulk — memo를 JSON 정수로 보내도 500이 "
        "아니다", (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_settlements_paid_bulk", f"{type(e).__name__} {e}")

try:
    r = _post(f"/api/settlements/{sid_transfer}/transfer",
              json={"no_account_reason": 608016, "defect_override_reason": 608017})
    chk(r.status_code != 500,
        "★★★★★ api_settlement_transfer(+_payout_account_gate) — "
        "no_account_reason/defect_override_reason을 JSON 정수로 보내도 500이 "
        "아니다(계좌없는 업체라 이 경로를 실제로 통과한다)",
        (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_settlement_transfer", f"{type(e).__name__} {e}")

try:
    r = _post("/api/settlements/999999/void", json={"reason": 608018})
    chk(r.status_code != 500,
        "★★★★★ api_settlement_void — reason을 JSON 정수로 보내도 500이 아니다"
        "(정산이 없어 404일 수 있다 — 크래시 여부만 확인, reason은 DB조회보다도 "
        "앞이라 404 자체가 이 결함과 무관하게 안전함을 보여준다)",
        (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_settlement_void", f"{type(e).__name__} {e}")

try:
    r = _post("/api/settlements/999999/undo", json={"reason": 608019})
    chk(r.status_code != 500,
        "★★★★★ api_settlement_undo — reason을 JSON 정수로 보내도 500이 아니다"
        "(정산이 없어 404일 수 있다 — 크래시 여부만 확인)",
        (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_settlement_undo", f"{type(e).__name__} {e}")

try:
    r = _post("/api/outbox/999999/handled", json={"note": 608019})
    chk(r.status_code != 500,
        "★★★★★ api_outbox_handled — note를 JSON 정수로 보내도 500이 아니다",
        (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_outbox_handled", f"{type(e).__name__} {e}")

try:
    r = _post("/api/outbox/test-send", json={"phone": 608020})
    chk(r.status_code != 500,
        "★★★★★ api_outbox_test_send — phone을 JSON 정수로 보내도 500이 아니다"
        "(형식이 안 맞아 400일 수 있다 — 크래시 여부만 확인)",
        (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_outbox_test_send", f"{type(e).__name__} {e}")

try:
    r = _patch(f"/api/boq/{boq_id}", json={"price_src": 608021, "price_date": 608022})
    rb = r.get_json() or {}
    chk(r.status_code == 200 and rb.get("ok") is True,
        "★★★★★ api_boq_update — price_src/price_date를 JSON 정수로 보내도 "
        "500 대신 200", (r.status_code, rb))

    r2 = _patch(f"/api/boq/{boq_id}", json={"price_date": None})
    chk(r2.status_code != 500,
        "★★★★★ api_boq_update — price_date를 명시적 null로 보내도 500이 "
        "아니다(옛 코드는 or \"\" 폴백조차 없어 null도 크래시였다)",
        (r2.status_code, r2.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_boq_update", f"{type(e).__name__} {e}")

try:
    r = _post(f"/api/cases/{cid}/to-dispatch", json={"reason": 608023})
    chk(r.status_code != 500,
        "★★★★★ api_case_to_dispatch — reason을 JSON 정수로 보내도 500이 "
        "아니다", (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_case_to_dispatch", f"{type(e).__name__} {e}")

try:
    r = _post(f"/api/cases/{cid}/cancel-award", json={"reason": 608024})
    chk(r.status_code != 500,
        "★★★★★ api_case_cancel_award — reason을 JSON 정수로 보내도 500이 "
        "아니다", (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_case_cancel_award", f"{type(e).__name__} {e}")

try:
    r = _post(f"/api/cases/{cid}/close-offline", json={"reason": 608025})
    chk(r.status_code != 500,
        "★★★★★ api_case_close_offline — reason을 JSON 정수로 보내도 500이 "
        "아니다", (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_case_close_offline", f"{type(e).__name__} {e}")

try:
    r = _post(f"/api/cases/{cid}/undo-no-repair", json={"reason": 608026})
    chk(r.status_code != 500,
        "★★★★★ api_case_undo_no_repair — reason을 JSON 정수로 보내도 500이 "
        "아니다", (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_case_undo_no_repair", f"{type(e).__name__} {e}")

try:
    #  insurer_instruction은 bid_id 검증보다도 앞이라 사건이 이미 '시공중'으로
    #  옮겨져 있어도(위 co_close_full 이후) 크래시 여부는 그대로 확인된다.
    r = _post(f"/api/cases/{cid}/award", json={"insurer_instruction": 608027})
    chk(r.status_code != 500,
        "★★★★★ api_case_award — insurer_instruction을 JSON 정수로 보내도 "
        "500이 아니다(bid_id 검증보다도 앞의 첫 실행문)",
        (r.status_code, r.get_json()))

    r2 = _post(f"/api/cases/{cid}/award",
               json={"insurer_instruction": "2026-09-12 유선지시", "bid_id": bid_id_orig,
                     "reason": 608028})
    chk(r2.status_code != 500,
        "★★★★★ api_case_award — reason을 JSON 정수로 보내도 500이 아니다"
        "(사건이 이미 '시공중'이라 NOT_BIDDING 409일 수 있다 — 크래시 여부만 확인)",
        (r2.status_code, r2.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_case_award", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[3] 회귀 안전 — 같은 라우트에 원래 타입(문자열) 값을 보내는 정상 "
      "경로는 그대로 동작한다")
# ------------------------------------------------------------------
try:
    s1 = _post("/api/memos", json={"target_type": "case", "target_id": cid, "body": "문자열 메모"})
    sb1 = s1.get_json() or {}
    chk(s1.status_code == 200 and sb1.get("ok") is True,
        "STEP api_memo_create — 문자열 body는 지금도 200", (s1.status_code, sb1))

    s2 = _patch(f"/api/partners/{pid_ok}", json={"address": "서울 서초구 2"})
    sb2 = s2.get_json() or {}
    chk(s2.status_code == 200 and sb2.get("ok") is True,
        "STEP api_partner_update — 문자열 address는 지금도 200", (s2.status_code, sb2))

    s3 = _patch(f"/api/boq/{boq_id}", json={"price_src": "표준단가표 2026", "price_date": "2026-09-01"})
    sb3 = s3.get_json() or {}
    chk(s3.status_code == 200 and sb3.get("ok") is True,
        "STEP api_boq_update — 문자열 price_src/price_date는 지금도 200",
        (s3.status_code, sb3))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] 회귀 안전", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[4] 되돌리기 — app.py 파일은 안 건드리고 공용 헬퍼 A._s만 '608 "
      "이전'(문자열 강제 없는 raw strip) 버전으로 몽키패치해, [2]의 대표 "
      "요청들이 실제로 다시 500이 되는지 확인 후 즉시 원복")
# ------------------------------------------------------------------
_real_s = A._s


def _s_pre608(v, n=None):
    """608 수정 직전 상황을 재현하는 몽키패치 전용 함수 — 진짜 _s()와의
       유일한 차이는 str() 강제(isinstance 분기)가 없다는 것."""
    t = (v or "").strip()
    return t[:n] if n else t


try:
    A._s = _s_pre608

    rr1 = _post("/api/memos", json={"target_type": "case", "target_id": cid, "body": 708001})
    chk(rr1.status_code == 500,
        "★★★★★ 되돌리면 api_memo_create(body)이 다시 500", rr1.status_code)

    rr2 = _patch(f"/api/partners/{pid_ok}", json={"biz_no": 7080020001})
    chk(rr2.status_code == 500,
        "★★★★★ 되돌리면 api_partner_update(biz_no, re.sub 경유)이 다시 500",
        rr2.status_code)

    rr3 = _patch(f"/api/partners/{pid_ok}", json={"address": 708003})
    chk(rr3.status_code == 500,
        "★★★★★ 되돌리면 api_partner_update(address)이 다시 500", rr3.status_code)

    rr4 = _post(f"/api/change-orders/{coid}/withdraw-offer", json={"reason": 708004})
    chk(rr4.status_code == 500,
        "★★★★★ 되돌리면 api_co_withdraw_offer(reason)이 다시 500", rr4.status_code)

    #  sid_transfer/sid_paid는 [2]에서 이미 실제로 처리 완료(200)됐을 수 있어
    #  ("이미 처리된 건" 409로 오염) [1]에서 미리 심어 둔 손대지 않은 짝을 쓴다.
    rr5 = _post(f"/api/settlements/{sid_transfer2}/transfer", json={"no_account_reason": 708005})
    chk(rr5.status_code == 500,
        "★★★★★ 되돌리면 _payout_account_gate(override_reason, "
        "api_settlement_transfer 경유)이 다시 500", rr5.status_code)

    rr6 = _post(f"/api/settlements/{sid_paid2}/paid", json={"memo": 708006})
    chk(rr6.status_code == 500,
        "★★★★★ 되돌리면 api_settlement_paid(memo)이 다시 500 — 이체는 "
        "일어나지 않은 채(memo 파싱이 UPDATE 이전) 크래시만 재현됨을 함께 확인",
        rr6.status_code)
    if rr6.status_code == 500:
        srow = DB.get_db().execute(
            "SELECT insurer_paid FROM settlements WHERE id=?", (sid_paid2,)).fetchone()
        chk(srow and srow["insurer_paid"] == "대기",
            "STEP 되돌리기 중 크래시가 나도 settlements.insurer_paid는 그대로 "
            "'대기'(부분 UPDATE 없음)", dict(srow) if srow else None)

    rr7 = _patch(f"/api/boq/{boq_id}", json={"price_src": 708007})
    chk(rr7.status_code == 500,
        "★★★★★ 되돌리면 api_boq_update(price_src, 삼항식 경유)이 다시 500",
        rr7.status_code)

    rr8 = _post(f"/api/cases/{cid}/cancel-award", json={"reason": 708008})
    chk(rr8.status_code == 500,
        "★★★★★ 되돌리면 api_case_cancel_award(reason)이 다시 500", rr8.status_code)

    rr8b = _post("/api/settlements/999999/undo", json={"reason": 708010})
    chk(rr8b.status_code == 500,
        "★★★★★ 되돌리면 api_settlement_undo(reason)이 다시 500", rr8b.status_code)

    rr9 = _post(f"/api/cases/{cid}/award", json={"insurer_instruction": 708009})
    chk(rr9.status_code == 500,
        "★★★★★ 되돌리면 api_case_award(insurer_instruction)이 다시 500",
        rr9.status_code)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드608 [4] 되돌리기", f"{type(e).__name__} {e}")
finally:
    A._s = _real_s

# 되돌리기 절차 동안 진짜 app.py 파일은 전혀 건드리지 않았음을 해시로 확인
APP_HASH_AFTER = hashlib.sha256(read("app.py").encode("utf-8")).hexdigest()
chk(APP_HASH_BEFORE == APP_HASH_AFTER,
    "★★★★★ 되돌리기 절차 동안 app.py 파일 내용이 전혀 안 바뀌었다"
    "(몽키패치만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

# 원복 확인 — 같은 모양의 요청이 다시 정상으로 돌아오는지(대표 3개)
try:
    rz1 = _post("/api/memos", json={"target_type": "case", "target_id": cid, "body": 808001})
    chk(rz1.status_code == 200,
        "★★★★★ A._s 원복 후 api_memo_create의 숫자 body가 다시 정상(200)",
        rz1.status_code)

    rz2 = _patch(f"/api/partners/{pid_ok}", json={"address": 808002})
    chk(rz2.status_code == 200,
        "★★★★★ A._s 원복 후 api_partner_update도 다시 정상(200)", rz2.status_code)

    rz3 = _post(f"/api/settlements/{sid_transfer}/transfer", json={"no_account_reason": 808003})
    chk(rz3.status_code != 500,
        "★★★★★ A._s 원복 후 api_settlement_transfer도 다시 정상(500 아님)",
        rz3.status_code)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드608 원복 확인", f"{type(e).__name__} {e}")


# ==================================================================
# 정리
# ------------------------------------------------------------------
os.environ.pop("BOKGUON_DB_PATH", None)
os.environ.pop("BOKGUON_UPLOAD_DIR", None)
os.environ.pop("BOKGUON_LOG_FILE", None)
os.environ.pop("BOKGUON_ENV", None)
os.environ.pop("BOKGUON_SEED_DEMO", None)
shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
