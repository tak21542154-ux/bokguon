# -*- coding: utf-8 -*-
"""스캔 609라운드 회귀 — round608이 인계한 잔여 15곳(①) + round608이 발견해
   분리요청한 새 결함군(② RE_PHONE.match()/RE_EMAIL.match()/valid_website()가
   비문자열 JSON에 TypeError)의 app.py 전체 전수스윕.

   조사 배경 — 시작 전 wc -l app.py가 직전 라운드(608) 종료시점과 정확히
   22062줄로 일치해 동시편집은 없었다.

   ① round608 인계 15곳 — 하나씩 직접 Read로 확인, 14곳 실결함·1곳 클린:
     · api_admin_create — username·name (2곳)
     · api_admin_update — name
     · api_me_update — name
     · api_unlock_login — username
     · api_create_application(address) — ★★★★★ 클린(결함 아님). clean_public_form()의
       FIELD_LIMITS["address"]=200이 이미 있고(라운드 미상 시점에 이미 추가돼
       있었다), clean_public_form 내부가 `str(v)`로 먼저 강제한 뒤 저장하므로
       d=clean 이후 읽는 (d.get("address") or "").strip() 은 항상 str에서만
       동작한다 — 수정 불필요.
     · api_insurer_create — name (② email·phone 매치도 이 함수에서 함께 발견)
     · api_insurer_credentials — login_id 2곳
     · api_insurer_webhook_set — webhook_url
     · api_contact_update — v=d.get(f) 루프(5개 필드 공용 한 줄)
     · _attach_defect_photos — item.get("note")
     · api_notice_create — title·body (2곳, title은 truthy검사만 통과하면
       숫자 등도 통과해 raw .strip()이 크래시)
     · api_boq_create — price_src·price_date(INSERT 튜플). ★자체발견 3중구조:
       이 한 곳만 고치고 실행검증했더니 여전히 500 — _boq_history(conn, bid,
       {**d, ...}, ...) 가 원본 raw d를 그대로 넘겨, db.py:boq_history() 안의
       `(row.get("price_src") or "")[:200]` 라는 **세 번째** raw 슬라이스가
       또 있었다(호출부 3곳 중 이 함수만 raw d를 넘긴다 — 다른 둘은 이미
       안전). 공유 래퍼 _boq_history() 안에서 한 번 더 강제해 호출부 3곳
       전체를 한 번에 닫았다(seed_boq.py 등 CLI 직접호출 2곳은 위협모델이
       달라 범위 밖으로 남김).
     · api_case_open_auction — est_basis
     · api_field_agreement_open — pattern
     · api_happy_call_add — feedback·method(.strip() 없는 슬라이스 변종)

   ② RE_PHONE.match()/RE_EMAIL.match()/valid_website() 전수스윕 — 컴파일된
     정규식 객체(RE_PHONE·RE_EMAIL·_RE_URL_SCHEME·_BARE_JAMO_RE)의 모든
     .match()/.search() 호출과, re.fullmatch()/re.search() 모듈함수 호출까지
     app.py 전체에서 재확인했다:
     실결함 발견(8곳 함수):
       · api_insurer_create — email·phone(name 수정과 같은 함수, ①과 통합)
       · api_partner_create — phone·email·website(valid_website도 내부에
         raw re.sub라 같은 결함군)
       · api_partner_update(루프) — phone·email·website
       · api_insurer_update(루프) — email·phone
       · api_contact_update(루프) — v를 ①에서 _s()로 감싸면 같은 줄의
         RE_PHONE/RE_EMAIL 매치도 함께 안전해진다(추가 수정 불필요, ①에 포함)
       · api_defect_update — due_date(re.fullmatch, 컴파일 객체는 아니지만
         같은 결함 모양이라 포함)
       · issue_partner_login(공유헬퍼, api_partner_credentials 유일 호출부가
         raw 값을 그대로 넘긴다) — want(내부에 re.fullmatch도 있어 함께 안전해짐)
       · api_change_password — password_policy_error() 내부 re.search 3곳이
         raw pw를 받는다(current/new)
     클린 확인(재검증, 수정 안 함) — 전부 호출 전에 이미 `_s()`로 강제되거나
     DB row(TEXT 컬럼)·Flask URL 파라미터(항상 str)·str() 강제 표현식이라
     비문자열이 애초에 도달할 수 없다:
       · api_partner_profile_update·api_insurer_profile_update(v=_s(d.get(f),..))
       · _create_case·api_case_create의 victim_phone(_vp=_s(...))
       · clean_public_form()의 out["phone"]/out["email"](str(v) 강제)
       · api_application_create류의 _phone/_email(_s(...))
       · 엑셀 일괄등록(api_contact_import)의 cell()이 항상 str(...) 반환
       · api_admin_update/api_unlock_login 수정 후의 username(re.fullmatch)
       · _has_bare_jamo() 호출 3곳 전부(_s() 선행)
       · api_schedule_event_add의 time_s(_s() 선행, 게다가 try/except로 이미
         AssertionError까지 잡고 있어 이중 안전)
       · track_page(token) — Flask 라우트 파라미터는 항상 str, JSON 아님
       · api_auction_set_deadline(dl) — str(X or "")로 이미 올바른 순서
       · _case_no_in_detail(case_no, detail) — 둘 다 DB row TEXT 컬럼

   전부 형제 헬퍼 `_s(v, n=None)`(app.py 1507행)을 그대로 재사용했다 — 새
   헬퍼·새 로직 없음. round601부터 이어진 raw-strip 결함군(①)은 이번
   라운드로 사실상 완결— 9개 라운드(601~609) 누적 165곳+.

   실행:  python test_scan_round609_fixes.py
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
    """주석 줄(이번 수정 설명 안에 옛 raw 패턴을 그대로 인용한 곳이 있어,
       주석까지 검색하면 '옛 패턴이 아직 있다'는 오탐이 난다)을 빼고
       실제 코드 줄만 이어붙인다."""
    return "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("#"))


print("=" * 72)
print("  스캔 609라운드 회귀 — round608 인계 15곳(①) + RE_PHONE/RE_EMAIL/")
print("  valid_website 전수스윕(②), raw .strip()/regex-TypeError 형제결함군")
print("=" * 72)

APP_SRC = read("app.py")

# ==================================================================
print("\n[0] 소스 확인 — 전부 옛 raw 패턴이 사라지고 _s()로 바뀌었다")
# ------------------------------------------------------------------
try:
    apc_ = _code_only(_py_fn_body(APP_SRC, "api_change_password"))
    chk('current, new = d.get("current") or "", d.get("new") or ""' not in apc_
        and 'current, new = _s(d.get("current")), _s(d.get("new"))' in apc_,
        "★★★★★ api_change_password — current/new")

    aac = _code_only(_py_fn_body(APP_SRC, "api_admin_create"))
    chk('username = (d.get("username") or "").strip().lower()' not in aac
        and 'username = _s(d.get("username")).lower()' in aac,
        "★★★★★ api_admin_create — username")
    chk('name = (d.get("name") or "").strip()[:40]' not in aac
        and 'name = _s(d.get("name"), 40)' in aac,
        "★★★★★ api_admin_create — name")

    aau = _code_only(_py_fn_body(APP_SRC, "api_admin_update"))
    chk('if "name" in d and (d.get("name") or "").strip():' not in aau
        and 'if "name" in d and _s(d.get("name")):' in aau,
        "★★★★★ api_admin_update — name(존재검사)")
    chk('new_name = (d["name"] or "").strip()[:40]' not in aau
        and 'new_name = _s(d["name"], 40)' in aau,
        "★★★★★ api_admin_update — name(대입)")

    amu = _code_only(_py_fn_body(APP_SRC, "api_me_update"))
    chk('name = (d.get("name") or "").strip()[:40]' not in amu
        and 'name = _s(d.get("name"), 40)' in amu,
        "★★★★★ api_me_update — name")

    aul = _code_only(_py_fn_body(APP_SRC, "api_unlock_login"))
    chk('uname = (d.get("username") or "").strip().lower()[:40]' not in aul
        and 'uname = _s(d.get("username")).lower()[:40]' in aul,
        "★★★★★ api_unlock_login — username")

    ipl = _code_only(_py_fn_body(APP_SRC, "issue_partner_login"))
    chk('want = (login_id or "").strip().lower()' not in ipl
        and "want = _s(login_id).lower()" in ipl,
        "★★★★★ issue_partner_login(공유헬퍼) — want(호출부 api_partner_"
        "credentials가 body().get('login_id') 원시값을 그대로 넘긴다)")

    apcr = _code_only(_py_fn_body(APP_SRC, "api_partner_create"))
    chk('if d.get("phone") and not RE_PHONE.match(d["phone"]):' not in apcr
        and "_phone = _s(d.get(\"phone\"))" in apcr
        and "RE_PHONE.match(_phone)" in apcr,
        "★★★★★ api_partner_create — phone(RE_PHONE.match)")
    chk('if d.get("email") and not RE_EMAIL.match(d["email"]):' not in apcr
        and "_email = _s(d.get(\"email\"))" in apcr
        and "RE_EMAIL.match(_email)" in apcr,
        "★★★★★ api_partner_create — email(RE_EMAIL.match)")
    chk('if d.get("website") and not valid_website(d["website"]):' not in apcr
        and 'valid_website(_s(d.get("website")))' in apcr,
        "★★★★★ api_partner_create — website(valid_website)")

    apup = _code_only(_py_fn_body(APP_SRC, "api_partner_update"))
    chk('if f == "phone" and d[f] and not RE_PHONE.match(d[f]):' not in apup
        and "RE_PHONE.match(_s(d[f]))" in apup,
        "★★★★★ api_partner_update(루프) — phone")
    chk('if f == "email" and d[f] and not RE_EMAIL.match(d[f]):' not in apup
        and "RE_EMAIL.match(_s(d[f]))" in apup,
        "★★★★★ api_partner_update(루프) — email")
    chk('if f == "website" and d[f] and not valid_website(d[f]):' not in apup
        and "valid_website(_s(d[f]))" in apup,
        "★★★★★ api_partner_update(루프) — website")

    aic = _code_only(_py_fn_body(APP_SRC, "api_insurer_create"))
    chk('name = (d.get("name") or "").strip()' not in aic
        and "name = _s(d.get(\"name\"))" in aic,
        "★★★★★ api_insurer_create — name")
    chk('if d.get("email") and not RE_EMAIL.match(d["email"]):' not in aic
        and "_email = _s(d.get(\"email\"))" in aic
        and "RE_EMAIL.match(_email)" in aic,
        "★★★★★ api_insurer_create — email(RE_EMAIL.match)")
    chk('if d.get("phone") and not RE_PHONE.match(d["phone"]):' not in aic
        and "_phone = _s(d.get(\"phone\"))" in aic
        and "RE_PHONE.match(_phone)" in aic,
        "★★★★★ api_insurer_create — phone(RE_PHONE.match)")

    aiu = _code_only(_py_fn_body(APP_SRC, "api_insurer_update"))
    chk('if f == "email" and d[f] and not RE_EMAIL.match(d[f]):' not in aiu
        and "RE_EMAIL.match(_s(d[f]))" in aiu,
        "★★★★★ api_insurer_update(루프) — email")
    chk('if f == "phone" and d[f] and not RE_PHONE.match(d[f]):' not in aiu
        and "RE_PHONE.match(_s(d[f]))" in aiu,
        "★★★★★ api_insurer_update(루프) — phone")

    aicr = _code_only(_py_fn_body(APP_SRC, "api_insurer_credentials"))
    chk('login_id = (d.get("login_id") or "").strip().lower()' not in aicr
        and 'login_id = _s(d.get("login_id")).lower()' in aicr,
        "★★★★★ api_insurer_credentials — login_id(신규발급)")
    chk('d["login_id"].strip().lower() != login_id' not in aicr
        and "_s(d.get(\"login_id\")).lower() != login_id" in aicr,
        "★★★★★ api_insurer_credentials — login_id(기존대조)")

    aiws = _code_only(_py_fn_body(APP_SRC, "api_insurer_webhook_set"))
    chk('url = (d.get("webhook_url") or "").strip()[:300]' not in aiws
        and 'url = _s(d.get("webhook_url"), 300)' in aiws,
        "★★★★★ api_insurer_webhook_set — webhook_url")

    acu = _code_only(_py_fn_body(APP_SRC, "api_contact_update"))
    chk('v = (d.get(f) or "").strip()[:120]' not in acu
        and "v = _s(d.get(f), 120)" in acu,
        "★★★★★ api_contact_update(루프) — v(RE_PHONE/RE_EMAIL 매치도 동반 안전화)")

    adp = _code_only(_py_fn_body(APP_SRC, "_attach_defect_photos"))
    chk('(item.get("note") or "").strip()[:300]' not in adp
        and '_s(item.get("note"), 300)' in adp,
        "★★★★★ _attach_defect_photos — item.get(note)")

    anc = _code_only(_py_fn_body(APP_SRC, "api_notice_create"))
    chk('title = d["title"].strip()[:100]' not in anc
        and 'title = _s(d["title"], 100)' in anc,
        "★★★★★ api_notice_create — title")
    chk('notice_body = (d.get("body") or "").strip()[:2000]' not in anc
        and 'notice_body = _s(d.get("body"), 2000)' in anc,
        "★★★★★ api_notice_create — body")

    abc = _code_only(_py_fn_body(APP_SRC, "api_boq_create"))
    chk('(d.get("price_src") or "").strip()[:200], (d.get("price_date") or "").strip()[:20]' not in abc
        and '_s(d.get("price_src"), 200), _s(d.get("price_date"), 20)' in abc,
        "★★★★★ api_boq_create — price_src·price_date(INSERT 튜플)")

    #  ⚠⚠ [라운드609 자체발견] 위 INSERT 튜플만 고치고 끝냈다면 여기서 다시
    #    500이 났을 것 — api_boq_create가 _boq_history()에 원본 raw d를 그대로
    #    넘기고, db.py:boq_history() 안의 raw 슬라이스가 TypeError를 낸다
    #    (실측 재현, 아래 [2] 실행절에서 최초 시도 시 실제로 500이 떴다).
    #    호출부 3곳이 공유하는 _boq_history() 래퍼 안에서 한 번 더 강제한다.
    bh = _code_only(_py_fn_body(APP_SRC, "_boq_history"))
    chk('row = {**row, "price_src": _s(row.get("price_src")), '
        '"price_date": _s(row.get("price_date"))}' in bh,
        "★★★★★ _boq_history(공유래퍼, 3개 호출부 전체 적용) — row의 "
        "price_src/price_date를 DB.boq_history() 넘기기 전에 재강제")

    acoa = _code_only(_py_fn_body(APP_SRC, "api_case_open_auction"))
    chk('basis = (d.get("est_basis") or "").strip()[:300]' not in acoa
        and 'basis = _s(d.get("est_basis"), 300)' in acoa,
        "★★★★★ api_case_open_auction — est_basis")

    afao = _code_only(_py_fn_body(APP_SRC, "api_field_agreement_open"))
    chk('pattern = (d.get("pattern") or "").strip()' not in afao
        and "pattern = _s(d.get(\"pattern\"))" in afao,
        "★★★★★ api_field_agreement_open — pattern")

    ahca = _code_only(_py_fn_body(APP_SRC, "api_happy_call_add"))
    chk('(d.get("feedback") or "")[:500]' not in ahca
        and '_s(d.get("feedback"), 500)' in ahca,
        "★★★★★ api_happy_call_add — feedback")
    chk('(d.get("method") or "전화")[:10]' not in ahca
        and '(_s(d.get("method")) or "전화")[:10]' in ahca,
        "★★★★★ api_happy_call_add — method(기본값 유지)")

    adu = _code_only(_py_fn_body(APP_SRC, "api_defect_update"))
    chk('d["due_date"] = _s(d.get("due_date"))' in adu,
        "★★★★★ api_defect_update — due_date(제자리 재대입)")

    chk('FIELD_LIMITS = {"company": 100' in APP_SRC and '"address": 200' in APP_SRC,
        "STEP api_create_application(address) — ★ 클린 재확인: FIELD_LIMITS에 "
        "이미 address:200이 있고 clean_public_form()이 str(v) 강제라 수정 불필요")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드609 [0] 소스 확인", f"{type(e).__name__} {e}")

APP_HASH_BEFORE = hashlib.sha256(APP_SRC.encode("utf-8")).hexdigest()

# ==================================================================
print("\n[1] 준비 — 스크래치 DB, 관리자 2명(최고+하위) + 협력사 2곳 + "
      "보험사 2곳(기존아이디 有/無) + 사건 3건(경매용·완료×2)")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round609_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "bokguon.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r609-csrf"
H = {"X-CSRF-Token": CSRF}
A = DB = None
ADMIN_PW = "OldPassw0rd!1"
(admin2_id, pid_upd, pid_cred1, pid_cred2, iid_upd, iid_cred1, iid_cred2,
 cid_case, cid_done1, cid_done2) = (None,) * 10

try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    conn0.execute(
        "INSERT INTO admins(username,password_hash,name,role,must_change_pw) "
        "VALUES('r609admin',?,'검증','최고관리자',0)", (DB.hash_pw(ADMIN_PW),))
    admin2_id = conn0.execute(
        "INSERT INTO admins(username,password_hash,name,role) "
        "VALUES('r609admin2','x','부계정','하위관리자')").lastrowid
    pid_upd = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,major,region) "
        "VALUES('R609업체수정용','시공사','활성','금속','서울')").lastrowid
    pid_cred1 = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,major,region) "
        "VALUES('R609업체계정1','시공사','활성','금속','서울')").lastrowid
    pid_cred2 = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,major,region) "
        "VALUES('R609업체계정2','시공사','활성','금속','서울')").lastrowid
    iid_upd = conn0.execute(
        "INSERT INTO insurers(name,status) VALUES('R609보험사수정용','활성')").lastrowid
    iid_cred1 = conn0.execute(
        "INSERT INTO insurers(name,status) VALUES('R609보험사계정1','활성')").lastrowid
    iid_cred2 = conn0.execute(
        "INSERT INTO insurers(name,status) VALUES('R609보험사계정2','활성')").lastrowid
    cid_case = conn0.execute(
        "INSERT INTO cases(case_no,status,category,region,address,manager) "
        "VALUES('R609CASE','입찰중','금속','서울','서울 강남구 1','담당자')").lastrowid
    cid_done1 = conn0.execute(
        "INSERT INTO cases(case_no,status,category,region,address,manager,partner_id,partner_name) "
        "VALUES('R609DONE1','완료','금속','서울','서울 강남구 2','담당자',?,'R609업체수정용')",
        (pid_upd,)).lastrowid
    cid_done2 = conn0.execute(
        "INSERT INTO cases(case_no,status,category,region,address,manager,partner_id,partner_name) "
        "VALUES('R609DONE2','완료','금속','서울','서울 강남구 3','담당자',?,'R609업체수정용')",
        (pid_upd,)).lastrowid
    conn0.commit()
    conn0.close()
    chk(all([admin2_id, pid_upd, pid_cred1, pid_cred2, iid_upd, iid_cred1, iid_cred2,
              cid_case, cid_done1, cid_done2]),
        "STEP 관리자 2명·협력사 3곳·보험사 3곳·사건 3건 픽스처 생성",
        dict(admin2_id=admin2_id, pid_upd=pid_upd, pid_cred1=pid_cred1, pid_cred2=pid_cred2,
             iid_upd=iid_upd, iid_cred1=iid_cred1, iid_cred2=iid_cred2,
             cid_case=cid_case, cid_done1=cid_done1, cid_done2=cid_done2))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드609 [1] 준비", f"{type(e).__name__} {e}")


def _admin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "r609admin"; sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = CSRF
        sess["pw_role"] = "admin"          # api_change_password 전용, 다른 라우트엔 무해
    return c


def _post(path, **kw):
    return _admin_client().post(path, headers=H, **kw)


def _patch(path, **kw):
    return _admin_client().patch(path, headers=H, **kw)


# ==================================================================
print("\n[2] 실행 — 각 라우트에 비문자열(JSON 정수) 값을 보내도 500이 아니다")
# ------------------------------------------------------------------
try:
    r = _post("/api/change-password", json={"current": ADMIN_PW, "new": 609001})
    chk(r.status_code != 500,
        "★★★★★ api_change_password — new를 JSON 정수로 보내도 500이 아니다"
        "(숫자만이라 정책위반 400일 수 있다 — 크래시 여부만 확인)",
        (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_change_password", f"{type(e).__name__} {e}")

try:
    r = _post("/api/admins", json={"username": 609002, "name": 609003})
    rb = r.get_json() or {}
    chk(r.status_code == 200 and rb.get("ok") is True,
        "★★★★★ api_admin_create — username/name을 JSON 정수로 보내도 500 대신 "
        "200(둘 다 숫자만이라 아이디 정규식도 통과)", (r.status_code, rb))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_admin_create", f"{type(e).__name__} {e}")

try:
    r = _patch(f"/api/admins/{admin2_id}", json={"name": 609004})
    rb = r.get_json() or {}
    chk(r.status_code == 200 and rb.get("ok") is True,
        "★★★★★ api_admin_update — name을 JSON 정수로 보내도 500 대신 200",
        (r.status_code, rb))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_admin_update", f"{type(e).__name__} {e}")

try:
    r = _patch("/api/me", json={"name": 609005})
    rb = r.get_json() or {}
    chk(r.status_code == 200 and rb.get("name") == "609005",
        "★★★★★ api_me_update — name을 JSON 정수로 보내도 500 대신 200",
        (r.status_code, rb))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_me_update", f"{type(e).__name__} {e}")

try:
    r = _post("/api/login-attempts/unlock", json={"username": 609006})
    chk(r.status_code != 500,
        "★★★★★ api_unlock_login — username을 JSON 정수로 보내도 500이 아니다",
        (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_unlock_login", f"{type(e).__name__} {e}")

try:
    r = _post(f"/api/partners/{pid_cred1}/credentials", json={"login_id": 609007})
    rb = r.get_json() or {}
    chk(r.status_code == 200 and rb.get("ok") is True,
        "★★★★★ issue_partner_login(api_partner_credentials 경유) — login_id를 "
        "JSON 정수로 보내도 500 대신 200(신규발급, 숫자만이라 아이디 정규식도 통과)",
        (r.status_code, rb))
    r2 = _post(f"/api/partners/{pid_cred1}/credentials", json={"login_id": 609008})
    chk(r2.status_code != 500,
        "★★★★★ issue_partner_login — 이미 아이디가 있는 상태에서 다른 login_id를 "
        "JSON 정수로 보내도 500이 아니다(기존대조 분기, 409 예상)",
        (r2.status_code, r2.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_partner_credentials", f"{type(e).__name__} {e}")

try:
    r1 = _post("/api/partners", json={"name": "R609업체A", "phone": 609010})
    chk(r1.status_code != 500,
        "★★★★★ api_partner_create — phone을 JSON 정수로 보내도 500이 아니다"
        "(형식이 안 맞아 400일 수 있다 — 크래시 여부만 확인)",
        (r1.status_code, r1.get_json()))
    r2 = _post("/api/partners", json={"name": "R609업체B", "email": 609011})
    chk(r2.status_code != 500,
        "★★★★★ api_partner_create — email을 JSON 정수로 보내도 500이 아니다",
        (r2.status_code, r2.get_json()))
    r3 = _post("/api/partners", json={"name": "R609업체C", "website": 609012})
    chk(r3.status_code != 500,
        "★★★★★ api_partner_create — website를 JSON 정수로 보내도 500이 아니다"
        "(스킴이 없는 값이라 통과할 수도 있다 — 크래시 여부만 확인)",
        (r3.status_code, r3.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_partner_create", f"{type(e).__name__} {e}")

try:
    r1 = _patch(f"/api/partners/{pid_upd}", json={"phone": 609020})
    chk(r1.status_code != 500,
        "★★★★★ api_partner_update — phone을 JSON 정수로 보내도 500이 아니다",
        (r1.status_code, r1.get_json()))
    r2 = _patch(f"/api/partners/{pid_upd}", json={"email": 609021})
    chk(r2.status_code != 500,
        "★★★★★ api_partner_update — email을 JSON 정수로 보내도 500이 아니다",
        (r2.status_code, r2.get_json()))
    r3 = _patch(f"/api/partners/{pid_upd}", json={"website": 609022})
    chk(r3.status_code != 500,
        "★★★★★ api_partner_update — website를 JSON 정수로 보내도 500이 아니다",
        (r3.status_code, r3.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_partner_update", f"{type(e).__name__} {e}")

try:
    r1 = _post("/api/insurers", json={"name": 609030})
    rb1 = r1.get_json() or {}
    chk(r1.status_code == 200 and rb1.get("ok") is True,
        "★★★★★ api_insurer_create — name을 JSON 정수로 보내도 500 대신 200",
        (r1.status_code, rb1))
    r2 = _post("/api/insurers", json={"name": "R609보험사비교1", "email": 609031})
    chk(r2.status_code != 500,
        "★★★★★ api_insurer_create — email을 JSON 정수로 보내도 500이 아니다",
        (r2.status_code, r2.get_json()))
    r3 = _post("/api/insurers", json={"name": "R609보험사비교2", "phone": 609032})
    chk(r3.status_code != 500,
        "★★★★★ api_insurer_create — phone을 JSON 정수로 보내도 500이 아니다",
        (r3.status_code, r3.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_insurer_create", f"{type(e).__name__} {e}")

try:
    r1 = _patch(f"/api/insurers/{iid_upd}", json={"email": 609040})
    chk(r1.status_code != 500,
        "★★★★★ api_insurer_update — email을 JSON 정수로 보내도 500이 아니다",
        (r1.status_code, r1.get_json()))
    r2 = _patch(f"/api/insurers/{iid_upd}", json={"phone": 609041})
    chk(r2.status_code != 500,
        "★★★★★ api_insurer_update — phone을 JSON 정수로 보내도 500이 아니다",
        (r2.status_code, r2.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_insurer_update", f"{type(e).__name__} {e}")

try:
    r1 = _post(f"/api/insurers/{iid_cred1}/credentials", json={"login_id": 609050})
    rb1 = r1.get_json() or {}
    chk(r1.status_code == 200 and rb1.get("ok") is True,
        "★★★★★ api_insurer_credentials — login_id를 JSON 정수로 보내도 500 대신 "
        "200(신규발급)", (r1.status_code, rb1))
    r2 = _post(f"/api/insurers/{iid_cred1}/credentials", json={"login_id": 609051})
    chk(r2.status_code != 500,
        "★★★★★ api_insurer_credentials — 이미 아이디가 있는 상태에서 다른 "
        "login_id를 JSON 정수로 보내도 500이 아니다(기존대조 분기, 409 예상)",
        (r2.status_code, r2.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_insurer_credentials", f"{type(e).__name__} {e}")

try:
    r = _patch(f"/api/insurers/{iid_upd}/webhook", json={"webhook_url": 609060})
    chk(r.status_code != 500,
        "★★★★★ api_insurer_webhook_set — webhook_url을 JSON 정수로 보내도 "
        "500이 아니다(https:// 로 시작 안 해 400 예상)",
        (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_insurer_webhook_set", f"{type(e).__name__} {e}")

try:
    r1 = _patch(f"/api/contacts/{pid_upd}", json={"phone": 609070})
    chk(r1.status_code != 500,
        "★★★★★ api_contact_update — phone을 JSON 정수로 보내도 500이 아니다",
        (r1.status_code, r1.get_json()))
    r2 = _patch(f"/api/contacts/{pid_upd}", json={"email": 609071})
    chk(r2.status_code != 500,
        "★★★★★ api_contact_update — email을 JSON 정수로 보내도 500이 아니다",
        (r2.status_code, r2.get_json()))
    r3 = _patch(f"/api/contacts/{pid_upd}", json={"manager": 609072})
    rb3 = r3.get_json() or {}
    chk(r3.status_code == 200 and rb3.get("ok") is True,
        "★★★★★ api_contact_update — manager(형식검사 없는 필드)를 JSON 정수로 "
        "보내도 500 대신 200", (r3.status_code, rb3))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_contact_update", f"{type(e).__name__} {e}")

_defect_id_1 = None
try:
    r = _post("/api/defects", json={"case_id": cid_case, "title": "R609하자1",
                                     "photos": [{"photo_id": 1, "note": 609080}]})
    rb = r.get_json() or {}
    chk(r.status_code == 200 and rb.get("ok") is True,
        "★★★★★ _attach_defect_photos(api_defect_create 경유) — photos[].note를 "
        "JSON 정수로 보내도 500 대신 200", (r.status_code, rb))
    _defect_id_1 = rb.get("id")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_defect_create(note)", f"{type(e).__name__} {e}")

try:
    if _defect_id_1:
        r = _patch(f"/api/defects/{_defect_id_1}", json={"due_date": 609090})
        chk(r.status_code != 500,
            "★★★★★ api_defect_update — due_date를 JSON 정수로 보내도 500이 "
            "아니다(형식이 안 맞아 400 예상)", (r.status_code, r.get_json()))
    else:
        chk(False, "★★★ [2] api_defect_update 선행조건", "_defect_id_1 없음")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_defect_update", f"{type(e).__name__} {e}")

try:
    r1 = _post("/api/notices", json={"title": 609100})
    rb1 = r1.get_json() or {}
    chk(r1.status_code == 200 and rb1.get("ok") is True,
        "★★★★★ api_notice_create — title을 JSON 정수로 보내도 500 대신 200"
        "(truthy 검사는 통과하고 raw .strip()에서나 죽던 자리)", (r1.status_code, rb1))
    r2 = _post("/api/notices", json={"title": "R609공지", "body": 609101})
    rb2 = r2.get_json() or {}
    chk(r2.status_code == 200 and rb2.get("ok") is True,
        "★★★★★ api_notice_create — body를 JSON 정수로 보내도 500 대신 200",
        (r2.status_code, rb2))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_notice_create", f"{type(e).__name__} {e}")

try:
    r = _post("/api/boq", json={"major": "금속", "item": "R609항목1",
                                 "price_src": 609110, "price_date": 609111})
    rb = r.get_json() or {}
    chk(r.status_code == 200 and rb.get("ok") is True,
        "★★★★★ api_boq_create — price_src/price_date를 JSON 정수로 보내도 "
        "500 대신 200", (r.status_code, rb))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_boq_create", f"{type(e).__name__} {e}")

try:
    r = _post("/api/cases/999999/open-auction", json={"est_basis": 609120})
    chk(r.status_code != 500,
        "★★★★★ api_case_open_auction — est_basis를 JSON 정수로 보내도 500이 "
        "아니다(사건이 없어 404 예상 — est_basis 파싱은 그보다도 앞이라 "
        "404 자체가 이 결함과 무관하게 안전함을 보여준다)",
        (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_case_open_auction", f"{type(e).__name__} {e}")

try:
    r = _post(f"/api/cases/{cid_case}/field-agreement", json={"pattern": 609121})
    chk(r.status_code != 500,
        "★★★★★ api_field_agreement_open — pattern을 JSON 정수로 보내도 500이 "
        "아니다", (r.status_code, r.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_field_agreement_open", f"{type(e).__name__} {e}")

try:
    r = _post(f"/api/cases/{cid_done1}/happy-call",
              json={"score": 4, "feedback": 609130, "method": 609131})
    rb = r.get_json() or {}
    chk(r.status_code == 200 and rb.get("ok") is True,
        "★★★★★ api_happy_call_add — feedback/method를 JSON 정수로 보내도 "
        "500 대신 200(완주)", (r.status_code, rb))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] api_happy_call_add", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[3] 회귀 안전 — 같은 라우트에 원래 타입(문자열) 값을 보내는 정상 "
      "경로는 그대로 동작한다")
# ------------------------------------------------------------------
try:
    s1 = _patch("/api/me", json={"name": "문자열이름"})
    sb1 = s1.get_json() or {}
    chk(s1.status_code == 200 and sb1.get("name") == "문자열이름",
        "STEP api_me_update — 문자열 name은 지금도 200", (s1.status_code, sb1))

    s2 = _patch(f"/api/partners/{pid_upd}", json={"phone": "02-123-4567"})
    sb2 = s2.get_json() or {}
    chk(s2.status_code == 200 and sb2.get("ok") is True,
        "STEP api_partner_update — 형식이 맞는 문자열 phone은 지금도 200",
        (s2.status_code, sb2))

    s3 = _post("/api/boq", json={"major": "금속", "item": "R609항목문자열",
                                  "price_src": "표준단가표 2026", "price_date": "2026-09-01"})
    sb3 = s3.get_json() or {}
    chk(s3.status_code == 200 and sb3.get("ok") is True,
        "STEP api_boq_create — 문자열 price_src/price_date는 지금도 200",
        (s3.status_code, sb3))

    s4 = _patch(f"/api/defects/{_defect_id_1}", json={"due_date": "2026-12-31"})
    chk(s4.status_code == 200,
        "STEP api_defect_update — 형식이 맞는 문자열 due_date는 지금도 200",
        (s4.status_code, s4.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] 회귀 안전", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[4] 되돌리기 — app.py 파일은 안 건드리고 공용 헬퍼 A._s만 '609 "
      "이전'(문자열 강제 없는 raw strip) 버전으로 몽키패치해, 대표 요청들이 "
      "실제로 다시 500이 되는지 확인 후 즉시 원복")
# ------------------------------------------------------------------
_real_s = A._s


def _s_pre609(v, n=None):
    """609 수정 직전 상황을 재현하는 몽키패치 전용 함수 — 진짜 _s()와의
       유일한 차이는 str() 강제(isinstance 분기)가 없다는 것."""
    t = (v or "").strip()
    return t[:n] if n else t


try:
    A._s = _s_pre609

    rr1 = _post("/api/admins", json={"username": 709002, "name": 709003})
    chk(rr1.status_code == 500,
        "★★★★★ 되돌리면 api_admin_create(username)이 다시 500", rr1.status_code)

    rr2 = _patch(f"/api/admins/{admin2_id}", json={"name": 709004})
    chk(rr2.status_code == 500,
        "★★★★★ 되돌리면 api_admin_update(name)이 다시 500", rr2.status_code)

    rr3 = _patch("/api/me", json={"name": 709005})
    chk(rr3.status_code == 500,
        "★★★★★ 되돌리면 api_me_update(name)이 다시 500", rr3.status_code)

    rr4 = _post("/api/login-attempts/unlock", json={"username": 709006})
    chk(rr4.status_code == 500,
        "★★★★★ 되돌리면 api_unlock_login(username)이 다시 500", rr4.status_code)

    rr5 = _post(f"/api/partners/{pid_cred2}/credentials", json={"login_id": 709007})
    chk(rr5.status_code == 500,
        "★★★★★ 되돌리면 issue_partner_login(신규발급)이 다시 500", rr5.status_code)

    rr6 = _post("/api/partners", json={"name": "R709업체", "phone": 709010})
    chk(rr6.status_code == 500,
        "★★★★★ 되돌리면 api_partner_create(phone, RE_PHONE.match 경유)이 "
        "다시 500", rr6.status_code)

    rr7 = _patch(f"/api/partners/{pid_upd}", json={"website": 709022})
    chk(rr7.status_code == 500,
        "★★★★★ 되돌리면 api_partner_update(website, valid_website 경유)이 "
        "다시 500", rr7.status_code)

    rr8 = _post("/api/insurers", json={"name": "R709보험사", "email": 709031})
    chk(rr8.status_code == 500,
        "★★★★★ 되돌리면 api_insurer_create(email, RE_EMAIL.match 경유)이 "
        "다시 500", rr8.status_code)

    rr9 = _patch(f"/api/insurers/{iid_upd}", json={"phone": 709041})
    chk(rr9.status_code == 500,
        "★★★★★ 되돌리면 api_insurer_update(phone, RE_PHONE.match 경유)이 "
        "다시 500", rr9.status_code)

    rr10 = _post(f"/api/insurers/{iid_cred2}/credentials", json={"login_id": 709050})
    chk(rr10.status_code == 500,
        "★★★★★ 되돌리면 api_insurer_credentials(신규발급)이 다시 500",
        rr10.status_code)

    rr11 = _patch(f"/api/insurers/{iid_upd}/webhook", json={"webhook_url": 709060})
    chk(rr11.status_code == 500,
        "★★★★★ 되돌리면 api_insurer_webhook_set(webhook_url)이 다시 500",
        rr11.status_code)

    rr12 = _patch(f"/api/contacts/{pid_upd}", json={"phone": 709070})
    chk(rr12.status_code == 500,
        "★★★★★ 되돌리면 api_contact_update(phone)이 다시 500", rr12.status_code)

    rr13 = _post("/api/defects", json={"case_id": cid_case, "title": "R709하자되돌리기",
                                        "photos": [{"photo_id": 1, "note": 709080}]})
    chk(rr13.status_code == 500,
        "★★★★★ 되돌리면 _attach_defect_photos(note)이 다시 500 — 제목을 [2]와 "
        "다르게 써서 10초 중복접수 가드(같은 요청이면 200 duplicate로 스킵)를 "
        "피하고 실제로 크래시 지점을 다시 통과하게 했다", rr13.status_code)

    if _defect_id_1:
        rr14 = _patch(f"/api/defects/{_defect_id_1}", json={"due_date": 709090})
        chk(rr14.status_code == 500,
            "★★★★★ 되돌리면 api_defect_update(due_date)이 다시 500", rr14.status_code)

    rr15 = _post("/api/notices", json={"title": 709100})
    chk(rr15.status_code == 500,
        "★★★★★ 되돌리면 api_notice_create(title)이 다시 500", rr15.status_code)

    rr16 = _post("/api/boq", json={"major": "금속", "item": "R709항목",
                                    "price_src": 709110, "price_date": 709111})
    chk(rr16.status_code == 500,
        "★★★★★ 되돌리면 api_boq_create(price_src/price_date)이 다시 500",
        rr16.status_code)

    rr17 = _post(f"/api/cases/{cid_case}/field-agreement", json={"pattern": 709121})
    chk(rr17.status_code == 500,
        "★★★★★ 되돌리면 api_field_agreement_open(pattern)이 다시 500",
        rr17.status_code)

    rr18 = _post(f"/api/cases/{cid_done2}/happy-call",
                 json={"score": 5, "feedback": 709130, "method": 709131})
    chk(rr18.status_code == 500,
        "★★★★★ 되돌리면 api_happy_call_add(feedback/method, .strip() 없는 "
        "슬라이스 변종)이 다시 500 — happy_calls INSERT는 일어나지 않은 채 "
        "(값 파싱이 SQL 실행보다 먼저) 크래시만 재현됨을 함께 확인", rr18.status_code)
    if rr18.status_code == 500:
        hrow = DB.get_db().execute(
            "SELECT COUNT(*) n FROM happy_calls WHERE case_id=?", (cid_done2,)).fetchone()
        chk(hrow and hrow["n"] == 0,
            "STEP 되돌리기 중 크래시가 나도 happy_calls에는 행이 생기지 않았다"
            "(부분 INSERT 없음)", dict(hrow) if hrow else None)

    rr19 = _post("/api/change-password", json={"current": ADMIN_PW, "new": 709001})
    chk(rr19.status_code == 500,
        "★★★★★ 되돌리면 api_change_password(new, password_policy_error 내부 "
        "re.search 경유)이 다시 500", rr19.status_code)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드609 [4] 되돌리기", f"{type(e).__name__} {e}")
finally:
    A._s = _real_s

# 되돌리기 절차 동안 진짜 app.py 파일은 전혀 건드리지 않았음을 해시로 확인
APP_HASH_AFTER = hashlib.sha256(read("app.py").encode("utf-8")).hexdigest()
chk(APP_HASH_BEFORE == APP_HASH_AFTER,
    "★★★★★ 되돌리기 절차 동안 app.py 파일 내용이 전혀 안 바뀌었다"
    "(몽키패치만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

# 원복 확인 — 같은 모양의 요청이 다시 정상으로 돌아오는지(대표 3개)
try:
    rz1 = _patch("/api/me", json={"name": 809001})
    chk(rz1.status_code == 200,
        "★★★★★ A._s 원복 후 api_me_update의 숫자 name이 다시 정상(200)",
        rz1.status_code)

    rz2 = _patch(f"/api/insurers/{iid_upd}/webhook", json={"webhook_url": 809002})
    chk(rz2.status_code != 500,
        "★★★★★ A._s 원복 후 api_insurer_webhook_set도 다시 정상(500 아님)",
        rz2.status_code)

    rz3 = _post("/api/boq", json={"major": "금속", "item": "R809항목",
                                   "price_src": 809003, "price_date": 809004})
    rzb3 = rz3.get_json() or {}
    chk(rz3.status_code == 200 and rzb3.get("ok") is True,
        "★★★★★ A._s 원복 후 api_boq_create도 다시 정상(200)", rz3.status_code)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드609 원복 확인", f"{type(e).__name__} {e}")


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
