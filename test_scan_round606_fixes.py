# -*- coding: utf-8 -*-
"""스캔 606라운드 회귀 — round605가 인계한 우선순위② 10개 함수(11개 이름,
   api_partner_profile_update 는 두 자리를 겸함) 전수 확인 + 형제결함군
   (raw `(d.get(...) or "").strip()`/`re.sub(...,d.get(...) or "")`, 보험사·
   협력사 전산이 JSON 숫자 등 비문자열 값을 보내면 AttributeError/TypeError로
   500이 나던 패턴)의 다음 배치.

   조사 배경 — 시작 전 wc -l app.py가 직전 라운드 종료시점과 정확히
   21973줄로 일치해 동시편집은 없었다. round605가 인계한 10개 함수(줄번호는
   함수 시작줄만 확인된 상태)를 하나씩 직접 Read로 열어 실제로 이 결함군에
   해당하는지 확인했다:

     · api_partner_profile_update — ★2곳: ceo/phone/email/address/region
       루프의 v(구 3339행), biz_no의 re.sub(구 3400행, `.strip()`은 아니지만
       raw d.get() 를 re.sub 문자열 인자에 그대로 넘기는 같은 근본원인)
     · api_insurer_profile_update — ★1곳: manager/dept/phone/email 루프의 v
     · api_insurer_case_create — **클린**: idempotency_key 는 이미
       `str(d.get(...) or "")` 로 먼저 문자열을 강제한 뒤 .strip() 하므로
       비문자열이 와도 안전하다(형제 api_v1_case_create 도 동일 관례).
     · api_insurer_case_cancel — ★1곳: reason
     · api_insurer_reject_bids — ★1곳: reason
     · api_insurer_award — ★1곳: reason(사건·입찰 조회 뒤라 실제로는 낙관적
       잠금 UPDATE 직전 — 그래도 같은 함수 안의 raw 재읽기다)
     · api_change_order_create — ★1곳: reason
     · api_insurer_co_ack — ★1곳: note
     · api_insurer_set_severity — ★1곳: severity
     · api_insurer_est_ack — ★1곳: reason
     · api_insurer_field_agreement_decision — ★1곳: reason

   10/11 함수(11자리)에서 실결함을 확인했고 api_insurer_case_create만
   클린이었다. 지시각도를 벗어나 "신선한 각도"로 두 갈래를 더 찾았다:

     ① round605가 login_id 만 고치고 지시범위 밖이라 남겨 둔 같은 함수의
        형제 필드 2곳 — _sub_create_impl() 의 name(구 3592행),
        _sub_update_impl() 의 name(구 3654행). round605 자신의 주석이
        "원래 지시각도 밖이라 그대로 남아 있다"고 명시해 둔 바로 그 자리다.
     ② api_partner_profile_update 자체를 소스검사([0]) 스크립트로 다시
        정규식 스윕하다 발견한 **이번 라운드가 처음 손댄 함수 안의 놓친
        3번째 자리** — 주소검색으로 좌표를 못 찾았을 때(AddrPick 미사용)
        옛 좌표를 지우는 elif 분기: `(d.get("address") or "").strip() !=
        ((prev or {}).get("address") or "")`(구 3419행). 루프 안의 v는
        고쳤지만 바로 아래 이 비교식이 "address"를 독립적으로 다시 raw
        재읽기 하고 있었다 — 1차 검토에서 "비교뿐이라 안전"이라고 잘못
        판단했다가, [0] 소스검사를 정규식으로 다시 돌리며 스스로 잡았다.

   합쳐서 이번 라운드가 고친 자리는 총 14곳(11개 지시 자리 중 11곳 실결함
   + 3곳 자체발견)이다. 전부 형제 헬퍼 `_s(v, n=None)`(1503행)를 그대로
   재사용했다 — 새 헬퍼·새 로직 없음.

   app.py 전체를 다시 정규식으로 스윕한 결과 같은 raw 패턴이 78곳 더
   남아 있음을 확인했다(대표: api_application_create 9곳·api_campaign_create
   6곳·api_partner_license 5곳·api_case_edit 3곳·api_est_band_set 3곳 등) —
   전부 require_admin/require_role 뒤(로그인한 직원 전용 어드민 콘솔)라
   round604가 "③ 어드민 콘솔 전용 더미(~85곳)"로 분류해 둔 범위에 속한다.
   이번 라운드도 지시대로 의도적으로 손대지 않고 607 인계에 남긴다(상세는
   run_all_tests.py 관례상 이 파일 마지막 인계 섹션 대신 라운드 최종 보고에
   남긴다).

   고침 — 14곳 전부 `_s()` 로 교체(원본과 strip→slice 순서 동일, 과잉수정 없음):
     · api_partner_profile_update: v = _s(d.get(f), 120) [루프] ·
       _bz = re.sub(r"[^0-9]", "", _s(d.get("biz_no"))) ·
       elif ("address" in d and _s(d.get("address")) != (...))
     · api_insurer_profile_update: v = _s(d.get(f), 80) [루프]
     · _sub_create_impl: name = _s(d.get("name"), 40)
     · _sub_update_impl: _new_name = _s(d.get("name"), 40)
     · api_insurer_case_cancel: reason = _s(body().get("reason"))
     · api_insurer_reject_bids: reason = _s(body().get("reason"))
     · api_insurer_award: reason = _s(d.get("reason"))
     · api_change_order_create: reason = _s(d.get("reason"))
     · api_insurer_co_ack: note = _s(d.get("note"), 300)
     · api_insurer_set_severity: sev = _s(body().get("severity"))
     · api_insurer_est_ack: reason = _s(body().get("reason"), 200)
     · api_insurer_field_agreement_decision: reason = _s(d.get("reason"), 500)

   [0] 소스 확인 — 14곳 전부 옛 raw 패턴이 사라지고 _s()로 바뀌었다.
       api_insurer_case_create의 이미 안전한 str() 래핑도 그대로다(회귀 없음).
   [1] 준비 — 스크래치 DB, 보험사·협력사 각 1곳(둘 다 상태='활성').
       api_insurer_award 전용으로 사건+경매+입찰을 2벌(고침 증명용 1·
       되돌리기 증명용 1 — 같은 사건을 재사용하면 첫 낙찰로 상태가
       '시공중'이 되어 두 번째 호출이 재현하려는 reason 줄 대신 앞단
       ALREADY_AWARDED(409)에서 먼저 막힌다는 것을 실제로 확인하고 분리했다).
   [2] 실행 — 14곳 전부에 비문자열(JSON 정수) 값을 보내도 500이 아니라
       정상 응답(200 성공, 또는 사건 미존재/형식오류 등 원래의 4xx)임을 확인.
   [3] 회귀 안전 — 같은 요청에 원래 타입(문자열) 값을 보내는 정상 경로는
       그대로 동작한다(과잉교정 없음).
   [4] 되돌리기 — app.py 파일은 안 건드리고 공용 헬퍼 A._s만 '606 이전'
       (문자열 강제 없는 raw strip) 버전으로 몽키패치해, [2]의 14개 요청이
       실제로 다시 500이 되는지 확인한 뒤 원복(app.py 해시 불변도 확인) —
       인과관계 직접증명. (api_insurer_award는 앞서 확인한 이유로 별도
       사건을 다시 써서 재현한다.)

   app.py 자신의 함수 6곳(api_partner_profile_update·api_insurer_profile_update·
   _sub_create_impl·_sub_update_impl·api_insurer_case_cancel·api_insurer_
   reject_bids·api_insurer_award·api_change_order_create·api_insurer_co_ack·
   api_insurer_set_severity·api_insurer_est_ack·api_insurer_field_agreement_
   decision — 실제로는 12곳)를 고쳤으므로 서버 재기동 필요.

      python test_scan_round606_fixes.py
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
print("  스캔 606라운드 회귀 — round605 인계 10개 함수(11자리) 전수 확인 +")
print("  자체발견 3곳, raw .strip()/re.sub 형제결함군(round601~605와 같은 부류)")
print("=" * 72)

APP_SRC = read("app.py")

# ==================================================================
print("\n[0] 소스 확인 — 14곳 전부 옛 raw 패턴이 사라지고 _s()로 바뀌었다")
# ------------------------------------------------------------------
try:
    ppu = _code_only(_py_fn_body(APP_SRC, "api_partner_profile_update"))
    chk('(d.get(f) or "").strip()[:120]' not in ppu,
        "★★★★★ api_partner_profile_update()의 루프에 raw strip이 더 이상 없다")
    chk('v = _s(d.get(f), 120)' in ppu,
        "★★★★★ api_partner_profile_update()가 v = _s(d.get(f), 120)을 쓴다")
    chk('re.sub(r"[^0-9]", "", d.get("biz_no") or "")' not in ppu,
        "★★★★★ api_partner_profile_update()의 biz_no에 raw re.sub이 더 이상 없다")
    chk('re.sub(r"[^0-9]", "", _s(d.get("biz_no")))' in ppu,
        "★★★★★ api_partner_profile_update()가 re.sub(...,_s(d.get(\"biz_no\")))을 쓴다")
    chk('(d.get("address") or "").strip() != ((prev or {}).get("address") or "")' not in ppu,
        "★★★★★ api_partner_profile_update()의 좌표초기화 elif에 raw strip이 없다"
        "(1차 검토에서 놓쳤다가 [0] 재점검에서 자체발견)")
    chk('_s(d.get("address")) != ((prev or {}).get("address") or "")' in ppu,
        "★★★★★ api_partner_profile_update()가 그 자리에 _s(d.get(\"address\"))를 쓴다")

    piu = _code_only(_py_fn_body(APP_SRC, "api_insurer_profile_update"))
    chk('(d.get(f) or "").strip()[:80]' not in piu,
        "★★★★★ api_insurer_profile_update()의 루프에 raw strip이 더 이상 없다")
    chk('v = _s(d.get(f), 80)' in piu,
        "★★★★★ api_insurer_profile_update()가 v = _s(d.get(f), 80)을 쓴다")

    icc = _code_only(_py_fn_body(APP_SRC, "api_insurer_case_create"))
    chk('str(d.get("idempotency_key") or "")).strip()[:80] or None' in icc,
        "STEP api_insurer_case_create()는 클린 판정 그대로 — idempotency_key의 "
        "str() 선先강제가 여전히 있다(회귀 없음, 이번 라운드가 손대지 않음)")

    sub_c = _code_only(_py_fn_body(APP_SRC, "_sub_create_impl"))
    chk('name = (d.get("name") or "").strip()[:40]' not in sub_c,
        "★★★★★ _sub_create_impl()의 name에 raw strip이 더 이상 없다"
        "(round605가 남긴 login_id 형제 자리 — 자체발견)")
    chk('name = _s(d.get("name"), 40)' in sub_c,
        "★★★★★ _sub_create_impl()이 name = _s(d.get(\"name\"), 40)을 쓴다")
    chk('login_id = _s(d.get("login_id")).lower()[:60]' in sub_c,
        "STEP _sub_create_impl()의 login_id(605가 이미 고침)는 그대로다(회귀 없음)")

    sub_u = _code_only(_py_fn_body(APP_SRC, "_sub_update_impl"))
    chk('_new_name = (d.get("name") or "").strip()[:40]' not in sub_u,
        "★★★★★ _sub_update_impl()의 name에 raw strip이 더 이상 없다(자체발견)")
    chk('_new_name = _s(d.get("name"), 40)' in sub_u,
        "★★★★★ _sub_update_impl()이 _new_name = _s(d.get(\"name\"), 40)을 쓴다")

    icx = _code_only(_py_fn_body(APP_SRC, "api_insurer_case_cancel"))
    chk('reason = (body().get("reason") or "").strip()' not in icx,
        "★★★★★ api_insurer_case_cancel()에 raw strip이 더 이상 없다")
    chk('reason = _s(body().get("reason"))' in icx,
        "★★★★★ api_insurer_case_cancel()이 reason = _s(body().get(\"reason\"))을 쓴다")

    irb = _code_only(_py_fn_body(APP_SRC, "api_insurer_reject_bids"))
    chk('reason = (body().get("reason") or "").strip()' not in irb,
        "★★★★★ api_insurer_reject_bids()에 raw strip이 더 이상 없다")
    chk('reason = _s(body().get("reason"))' in irb,
        "★★★★★ api_insurer_reject_bids()가 reason = _s(body().get(\"reason\"))을 쓴다")

    iaw = _code_only(_py_fn_body(APP_SRC, "api_insurer_award"))
    chk('reason = (d.get("reason") or "").strip()' not in iaw,
        "★★★★★ api_insurer_award()에 raw strip이 더 이상 없다")
    chk('reason = _s(d.get("reason"))' in iaw,
        "★★★★★ api_insurer_award()가 reason = _s(d.get(\"reason\"))을 쓴다")

    cocr = _code_only(_py_fn_body(APP_SRC, "api_change_order_create"))
    chk('reason = (d.get("reason") or "").strip()' not in cocr,
        "★★★★★ api_change_order_create()에 raw strip이 더 이상 없다")
    chk('reason = _s(d.get("reason"))' in cocr,
        "★★★★★ api_change_order_create()가 reason = _s(d.get(\"reason\"))을 쓴다")

    coack = _code_only(_py_fn_body(APP_SRC, "api_insurer_co_ack"))
    chk('note = (d.get("note") or "").strip()[:300]' not in coack,
        "★★★★★ api_insurer_co_ack()에 raw strip이 더 이상 없다")
    chk('note = _s(d.get("note"), 300)' in coack,
        "★★★★★ api_insurer_co_ack()가 note = _s(d.get(\"note\"), 300)을 쓴다")

    isev = _code_only(_py_fn_body(APP_SRC, "api_insurer_set_severity"))
    chk('sev = (body().get("severity") or "").strip()' not in isev,
        "★★★★★ api_insurer_set_severity()에 raw strip이 더 이상 없다")
    chk('sev = _s(body().get("severity"))' in isev,
        "★★★★★ api_insurer_set_severity()가 sev = _s(body().get(\"severity\"))을 쓴다")

    iea = _code_only(_py_fn_body(APP_SRC, "api_insurer_est_ack"))
    chk('reason = (body().get("reason") or "").strip()[:200]' not in iea,
        "★★★★★ api_insurer_est_ack()에 raw strip이 더 이상 없다")
    chk('reason = _s(body().get("reason"), 200)' in iea,
        "★★★★★ api_insurer_est_ack()가 reason = _s(body().get(\"reason\"), 200)을 쓴다")

    ifad = _code_only(_py_fn_body(APP_SRC, "api_insurer_field_agreement_decision"))
    chk('reason = (d.get("reason") or "").strip()[:500]' not in ifad,
        "★★★★★ api_insurer_field_agreement_decision()에 raw strip이 더 이상 없다")
    chk('reason = _s(d.get("reason"), 500)' in ifad,
        "★★★★★ api_insurer_field_agreement_decision()이 reason = _s(d.get(\"reason\"), 500)을 쓴다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드606 [0] 소스 확인", f"{type(e).__name__} {e}")

APP_HASH_BEFORE = hashlib.sha256(APP_SRC.encode("utf-8")).hexdigest()

# ==================================================================
print("\n[1] 준비 — 스크래치 DB, 보험사·협력사 각 1곳 + 낙찰용 사건 2벌")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round606_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "bokguon.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r606-csrf"
H = {"X-CSRF-Token": CSRF}
A = DB = None
iid = pid = None
cid_aw_fix = bid_aw_fix = cid_aw_revert = bid_aw_revert = None


def _mk_award_case(conn, tag, insurer_id, partner_id):
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,insurer_id,category,region) "
        "VALUES(?,'입찰중',?,'금속','서울')", (f"R606-{tag}", insurer_id)).lastrowid
    auid = conn.execute("INSERT INTO auctions(case_id,status) VALUES(?,'진행')", (cid,)).lastrowid
    bid = conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days) "
        "VALUES(?,?,?,500000,3)", (auid, partner_id, "R606업체")).lastrowid
    return cid, bid


try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    iid = conn0.execute(
        "INSERT INTO insurers(name,status) VALUES('R606보험사','활성')").lastrowid
    pid = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,category,region) "
        "VALUES('R606업체','시공사','활성','가드레일','서울')").lastrowid
    cid_aw_fix, bid_aw_fix = _mk_award_case(conn0, "AW1", iid, pid)
    cid_aw_revert, bid_aw_revert = _mk_award_case(conn0, "AW2", iid, pid)
    conn0.commit()
    conn0.close()
    chk(bool(iid and pid and cid_aw_fix and cid_aw_revert),
        "STEP 보험사·협력사·낙찰용 사건 2벌 픽스처 생성",
        (iid, pid, cid_aw_fix, cid_aw_revert))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드606 [1] 준비", f"{type(e).__name__} {e}")


def _insurer_owner_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["insurer_id"] = iid
        sess["insurer_name"] = "R606보험사"
        sess["_csrf"] = CSRF
    return c


def _partner_owner_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["partner_id"] = pid
        sess["partner_name"] = "R606업체"
        sess["_csrf"] = CSRF
    return c


NEW_UID = None  # _sub_create_impl로 만든 하위계정 id — _sub_update_impl 실행 대상

# ==================================================================
print("\n[2] 실행 — 14곳 전부에 비문자열(JSON 정수) 값을 보내도 500이 아니다")
# ------------------------------------------------------------------
try:
    r1 = _partner_owner_client().patch(
        "/api/partner/profile", headers=H, json={"region": 20260913, "address": 20260913})
    rb1 = r1.get_json() or {}
    chk(r1.status_code == 200 and rb1.get("ok") is True,
        "★★★★★ api_partner_profile_update — region·address를 JSON 정수로 보내도 "
        "500 대신 200(루프의 v 두 곳 + 좌표초기화 elif 세 자리를 한 요청으로 커버)",
        (r1.status_code, rb1))
    if rb1.get("ok"):
        prow = DB.get_db().execute(
            "SELECT region, address FROM partners WHERE id=?", (pid,)).fetchone()
        chk(prow["region"] == "20260913" and prow["address"] == "20260913",
            "STEP DB(partners)에 region·address가 문자열로 저장됐다", dict(prow))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드606 [2] api_partner_profile_update(region/address)",
        f"{type(e).__name__} {e}")

try:
    r2 = _partner_owner_client().patch(
        "/api/partner/profile", headers=H, json={"biz_no": 1234567890})
    chk(r2.status_code != 500,
        "★★★★★ api_partner_profile_update — biz_no를 JSON 정수로 보내도 500이 "
        "아니다(형식 통과 여부는 이 결함과 무관 — 200 또는 400만 확인)",
        (r2.status_code, r2.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드606 [2] api_partner_profile_update(biz_no)", f"{type(e).__name__} {e}")

try:
    r3 = _insurer_owner_client().patch(
        "/api/insurer/profile", headers=H, json={"dept": 20260913})
    rb3 = r3.get_json() or {}
    chk(r3.status_code == 200 and rb3.get("ok") is True,
        "★★★★★ api_insurer_profile_update — dept를 JSON 정수로 보내도 500 대신 200",
        (r3.status_code, rb3))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드606 [2] api_insurer_profile_update(dept)", f"{type(e).__name__} {e}")

try:
    r4 = _insurer_owner_client().post(
        "/api/insurer/subaccounts", headers=H,
        json={"login_id": "r606sub1", "name": 20260913})
    rb4 = r4.get_json() or {}
    chk(r4.status_code == 200 and rb4.get("ok") is True,
        "★★★★★ _sub_create_impl — name을 JSON 정수로 보내도 500 대신 200",
        (r4.status_code, rb4))
    if rb4.get("ok"):
        row4 = DB.get_db().execute(
            "SELECT id, name FROM portal_users WHERE login_id='r606sub1'").fetchone()
        NEW_UID = row4["id"] if row4 else None
        chk(row4 and row4["name"] == "20260913",
            "STEP DB(portal_users)에 name이 문자열 '20260913'으로 저장됐다",
            dict(row4) if row4 else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드606 [2] _sub_create_impl(name)", f"{type(e).__name__} {e}")

try:
    chk(bool(NEW_UID), "STEP _sub_update_impl 실행을 위한 대상 uid 확보", NEW_UID)
    r5 = _insurer_owner_client().patch(
        f"/api/insurer/subaccounts/{NEW_UID}", headers=H, json={"name": 887766})
    rb5 = r5.get_json() or {}
    chk(r5.status_code == 200 and rb5.get("ok") is True,
        "★★★★★ _sub_update_impl — name을 JSON 정수로 보내도 500 대신 200",
        (r5.status_code, rb5))
    if rb5.get("ok"):
        row5 = DB.get_db().execute(
            "SELECT name FROM portal_users WHERE id=?", (NEW_UID,)).fetchone()
        chk(row5 and row5["name"] == "887766",
            "STEP DB(portal_users)에 name이 문자열 '887766'으로 갱신됐다",
            dict(row5) if row5 else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드606 [2] _sub_update_impl(name)", f"{type(e).__name__} {e}")

try:
    r6 = _insurer_owner_client().post(
        "/api/insurer/cases/999999/cancel", headers=H, json={"reason": 123456})
    chk(r6.status_code == 404,
        "★★★★★ api_insurer_case_cancel — reason을 JSON 정수로 보내도 500 대신 "
        "404(원래의 사건없음 응답)", (r6.status_code, r6.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드606 [2] api_insurer_case_cancel(reason)", f"{type(e).__name__} {e}")

try:
    r7 = _insurer_owner_client().post(
        "/api/insurer/cases/999999/reject-bids", headers=H, json={"reason": 123456})
    chk(r7.status_code == 404,
        "★★★★★ api_insurer_reject_bids — reason을 JSON 정수로 보내도 500 대신 404",
        (r7.status_code, r7.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드606 [2] api_insurer_reject_bids(reason)", f"{type(e).__name__} {e}")

try:
    r8 = _insurer_owner_client().post(
        f"/api/insurer/cases/{cid_aw_fix}/award", headers=H,
        json={"bid_id": bid_aw_fix, "reason": 12345})
    rb8 = r8.get_json() or {}
    chk(r8.status_code == 200 and rb8.get("ok") is True,
        "★★★★★ api_insurer_award — reason을 JSON 정수로 보내도 500 대신 200, "
        "실제 낙찰 완료", (r8.status_code, rb8))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드606 [2] api_insurer_award(reason)", f"{type(e).__name__} {e}")

try:
    r9 = _partner_owner_client().post(
        "/api/cases/999999/change-order", headers=H,
        json={"reason": 123456, "requested_amount": 500000})
    chk(r9.status_code == 404,
        "★★★★★ api_change_order_create — reason을 JSON 정수로 보내도 500 대신 404",
        (r9.status_code, r9.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드606 [2] api_change_order_create(reason)", f"{type(e).__name__} {e}")

try:
    r10 = _insurer_owner_client().post(
        "/api/insurer/change-orders/999999/ack", headers=H,
        json={"ack": True, "note": 123456})
    chk(r10.status_code == 404,
        "★★★★★ api_insurer_co_ack — note를 JSON 정수로 보내도 500 대신 404",
        (r10.status_code, r10.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드606 [2] api_insurer_co_ack(note)", f"{type(e).__name__} {e}")

try:
    r11 = _insurer_owner_client().post(
        "/api/insurer/cases/999999/severity", headers=H, json={"severity": 123456})
    chk(r11.status_code == 400,
        "★★★★★ api_insurer_set_severity — severity를 JSON 정수로 보내도 500 대신 "
        "400(원래의 '파손 정도 값 오류' 응답)", (r11.status_code, r11.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드606 [2] api_insurer_set_severity(severity)", f"{type(e).__name__} {e}")

try:
    r12 = _insurer_owner_client().post(
        "/api/insurer/cases/999999/est-ack", headers=H, json={"reason": 123456})
    chk(r12.status_code == 404,
        "★★★★★ api_insurer_est_ack — reason을 JSON 정수로 보내도 500 대신 404",
        (r12.status_code, r12.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드606 [2] api_insurer_est_ack(reason)", f"{type(e).__name__} {e}")

try:
    r13 = _insurer_owner_client().post(
        "/api/insurer/cases/999999/field-agreement/decision", headers=H,
        json={"approve": False, "reason": 123456})
    chk(r13.status_code == 404,
        "★★★★★ api_insurer_field_agreement_decision — reason을 JSON 정수로 "
        "보내도 500 대신 404", (r13.status_code, r13.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드606 [2] api_insurer_field_agreement_decision(reason)",
        f"{type(e).__name__} {e}")


# ==================================================================
print("\n[3] 회귀 안전 — 같은 요청에 원래 타입(문자열) 값을 보내는 정상 경로는 "
      "그대로 동작한다")
# ------------------------------------------------------------------
try:
    s1 = _partner_owner_client().patch(
        "/api/partner/profile", headers=H, json={"region": "부산", "address": "부산 해운대"})
    sb1 = s1.get_json() or {}
    chk(s1.status_code == 200 and sb1.get("ok") is True,
        "STEP api_partner_profile_update — 문자열 region/address는 지금도 200",
        (s1.status_code, sb1))

    s2 = _insurer_owner_client().patch(
        "/api/insurer/profile", headers=H, json={"dept": "손해사정팀"})
    sb2 = s2.get_json() or {}
    chk(s2.status_code == 200 and sb2.get("ok") is True,
        "STEP api_insurer_profile_update — 문자열 dept는 지금도 200", (s2.status_code, sb2))

    s3 = _insurer_owner_client().post(
        "/api/insurer/cases/999999/severity", headers=H, json={"severity": "보통"})
    sb3 = s3.get_json() or {}
    chk(s3.status_code == 404,
        "STEP api_insurer_set_severity — 유효한 문자열 severity는 형식검사를 "
        "통과해 사건조회(404)까지 간다(500·400 아님)", (s3.status_code, sb3))

    s4 = _insurer_owner_client().post(
        "/api/insurer/cases/999999/cancel", headers=H, json={"reason": "테스트 취소 사유"})
    sb4 = s4.get_json() or {}
    chk(s4.status_code == 404,
        "STEP api_insurer_case_cancel — 문자열 reason은 지금도 사건조회(404)까지 간다",
        (s4.status_code, sb4))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드606 [3] 회귀 안전", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[4] 되돌리기 — app.py 파일은 안 건드리고 공용 헬퍼 A._s만 '606 이전'"
      "(문자열 강제 없는 raw strip) 버전으로 몽키패치해, [2]의 14개 요청이 "
      "실제로 다시 500이 되는지 확인 후 즉시 원복")
# ------------------------------------------------------------------
_real_s = A._s


def _s_pre606(v, n=None):
    """606 수정 직전의 _s() 호출부 부재 상황을 재현하는 몽키패치 전용 함수 —
       진짜 _s()와의 유일한 차이는 str() 강제(isinstance 분기)가 없다는 것."""
    t = (v or "").strip()
    return t[:n] if n else t


try:
    A._s = _s_pre606

    rr1 = _partner_owner_client().patch(
        "/api/partner/profile", headers=H, json={"region": 555111})
    chk(rr1.status_code == 500,
        "★★★★★ 되돌리면 api_partner_profile_update(루프 region)이 다시 500", rr1.status_code)

    rr1b = _partner_owner_client().patch(
        "/api/partner/profile", headers=H, json={"address": 555112})
    chk(rr1b.status_code == 500,
        "★★★★★ 되돌리면 api_partner_profile_update(좌표초기화 elif, address)이 "
        "다시 500(자체발견 자리)", rr1b.status_code)

    rr2 = _partner_owner_client().patch(
        "/api/partner/profile", headers=H, json={"biz_no": 555113})
    chk(rr2.status_code == 500,
        "★★★★★ 되돌리면 api_partner_profile_update(biz_no)도 다시 500(re.sub TypeError)",
        rr2.status_code)

    rr3 = _insurer_owner_client().patch(
        "/api/insurer/profile", headers=H, json={"dept": 555114})
    chk(rr3.status_code == 500,
        "★★★★★ 되돌리면 api_insurer_profile_update(루프 dept)도 다시 500", rr3.status_code)

    rr4 = _insurer_owner_client().post(
        "/api/insurer/subaccounts", headers=H, json={"login_id": "r606sub2", "name": 555115})
    chk(rr4.status_code == 500,
        "★★★★★ 되돌리면 _sub_create_impl(name)도 다시 500", rr4.status_code)

    rr5 = _insurer_owner_client().patch(
        f"/api/insurer/subaccounts/{NEW_UID}", headers=H, json={"name": 555116})
    chk(rr5.status_code == 500,
        "★★★★★ 되돌리면 _sub_update_impl(name)도 다시 500", rr5.status_code)

    rr6 = _insurer_owner_client().post(
        "/api/insurer/cases/999999/cancel", headers=H, json={"reason": 555117})
    chk(rr6.status_code == 500,
        "★★★★★ 되돌리면 api_insurer_case_cancel(reason)도 다시 500", rr6.status_code)

    rr7 = _insurer_owner_client().post(
        "/api/insurer/cases/999999/reject-bids", headers=H, json={"reason": 555118})
    chk(rr7.status_code == 500,
        "★★★★★ 되돌리면 api_insurer_reject_bids(reason)도 다시 500", rr7.status_code)

    # award는 같은 사건을 재사용하면 [2]에서 이미 낙찰 확정(시공중)되어 있어
    # ALREADY_AWARDED(409)로 앞단에서 먼저 막힌다 — 별도 사건(cid_aw_revert)을 쓴다.
    rr8 = _insurer_owner_client().post(
        f"/api/insurer/cases/{cid_aw_revert}/award", headers=H,
        json={"bid_id": bid_aw_revert, "reason": 555119})
    chk(rr8.status_code == 500,
        "★★★★★ 되돌리면 api_insurer_award(reason)도 다시 500(별도 사건으로 재현)",
        rr8.status_code)

    rr9 = _partner_owner_client().post(
        "/api/cases/999999/change-order", headers=H,
        json={"reason": 555120, "requested_amount": 500000})
    chk(rr9.status_code == 500,
        "★★★★★ 되돌리면 api_change_order_create(reason)도 다시 500", rr9.status_code)

    rr10 = _insurer_owner_client().post(
        "/api/insurer/change-orders/999999/ack", headers=H,
        json={"ack": True, "note": 555121})
    chk(rr10.status_code == 500,
        "★★★★★ 되돌리면 api_insurer_co_ack(note)도 다시 500", rr10.status_code)

    rr11 = _insurer_owner_client().post(
        "/api/insurer/cases/999999/severity", headers=H, json={"severity": 555122})
    chk(rr11.status_code == 500,
        "★★★★★ 되돌리면 api_insurer_set_severity(severity)도 다시 500", rr11.status_code)

    rr12 = _insurer_owner_client().post(
        "/api/insurer/cases/999999/est-ack", headers=H, json={"reason": 555123})
    chk(rr12.status_code == 500,
        "★★★★★ 되돌리면 api_insurer_est_ack(reason)도 다시 500", rr12.status_code)

    rr13 = _insurer_owner_client().post(
        "/api/insurer/cases/999999/field-agreement/decision", headers=H,
        json={"approve": False, "reason": 555124})
    chk(rr13.status_code == 500,
        "★★★★★ 되돌리면 api_insurer_field_agreement_decision(reason)도 다시 500",
        rr13.status_code)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드606 [4] 되돌리기", f"{type(e).__name__} {e}")
finally:
    A._s = _real_s

# 되돌리기 절차 동안 진짜 app.py 파일은 전혀 건드리지 않았음을 해시로 확인
APP_HASH_AFTER = hashlib.sha256(read("app.py").encode("utf-8")).hexdigest()
chk(APP_HASH_BEFORE == APP_HASH_AFTER,
    "★★★★★ 되돌리기 절차 동안 app.py 파일 내용이 전혀 안 바뀌었다"
    "(몽키패치만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

# 원복 확인 — 같은 모양의 요청이 다시 정상으로 돌아오는지(대표 3개)
try:
    rz1 = _partner_owner_client().patch(
        "/api/partner/profile", headers=H, json={"region": 666111})
    chk(rz1.status_code == 200,
        "★★★★★ A._s 원복 후 api_partner_profile_update의 숫자 region이 다시 정상(200)",
        rz1.status_code)

    rz2 = _insurer_owner_client().post(
        "/api/insurer/cases/999999/severity", headers=H, json={"severity": 666112})
    chk(rz2.status_code == 400,
        "★★★★★ A._s 원복 후 api_insurer_set_severity도 다시 정상(400)", rz2.status_code)

    rz3 = _insurer_owner_client().post(
        f"/api/insurer/cases/{cid_aw_revert}/award", headers=H,
        json={"bid_id": bid_aw_revert, "reason": 666113})
    chk(rz3.status_code == 200,
        "★★★★★ A._s 원복 후 api_insurer_award도 다시 정상(200) — reason 줄은 "
        "UPDATE(낙찰 확정) **이전**이라 [4]의 크래시가 쓰기 전에 멈췄고, 이 "
        "사건은 그때도 지금도 아직 '입찰중'이었음을 함께 방증한다", rz3.status_code)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드606 원복 확인", f"{type(e).__name__} {e}")


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
