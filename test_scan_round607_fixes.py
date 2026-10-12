# -*- coding: utf-8 -*-
"""스캔 607라운드 회귀 — round606이 인계한 마지막 배치(어드민콘솔 전용 raw
   strip 결함군, 78곳·39개함수) 중 이름이 지목된 6개 함수 + 조사 중 발견한
   밀접한 형제 2곳(_campaign_recipients·api_campaign_preview) 전수 확인.

   조사 배경 — 시작 전 wc -l app.py가 직전 라운드(606) 종료시점과 정확히
   22009줄로 일치해 동시편집은 없었다. round606이 이름만 지목해 둔(정확한
   줄번호·전수 목록은 남기지 않음) 6개 함수를 app.py 전체 재정규식스윕
   (raw `X.get(...) or DEFAULT).strip()/.lower()/.upper()` 직결, 또는
   `re.sub`/슬라이스 문자열 인자 자리)으로 하나씩 직접 Read 해 실제 결함
   여부를 확인했다:

     · api_application_create — ★11곳(9개 필드): company·biz_no·phone·email·
       ceo·category·region·address·message. phone·email은 위에서 이미
       `_phone`/`_email`(RE_PHONE/RE_EMAIL 검사 전용)로 읽어 놓고도 INSERT
       자리에서 raw d.get(...)을 또 읽는 "재읽기"였다 — 처음엔 형제 `biz`
       (같은 함수, 검증 후 로컬변수를 그대로 재사용 중)를 본떠 `_phone`/
       `_email`을 재사용하도록 고쳤으나, round484의 되돌림-증명 테스트
       (test_scan_round484_fixes.py)가 RE_PHONE/RE_EMAIL 검사 블록만 잘라
       내 "그 검사를 없애면 옛 버그가 재현되는가"를 확인하는 방식이라 —
       `_phone`/`_email` 재사용 시 그 블록을 자르면 INSERT가 정의되지 않은
       변수를 참조해 NameError(500)가 나 버렸다(전체배터리 첫 실행에서
       발견). round484 테스트의 검증 취지(RE_PHONE 제거 시 옛 동작 재현)를
       지키기 위해, phone·email도 형제 필드들과 같은 방식 — 각자 독립적으로
       `_s(d.get(...), N)` — 으로 되돌렸다(round604 결론 "필드별 _s() 적용"
       과도 일치, INSERT 시점의 재읽기 자체는 크래시 관점에서 무해함 — d가
       불변이라 첫 읽기가 이미 안전하면 재읽기도 항상 안전하다).
     · api_campaign_create — ★6곳: title·subject·body(text)·audience·
       filter_json.major·filter_json.region.
     · api_case_edit — ★7곳(지시는 "3곳"이었으나 직접 세어 보니 실결함은
       7곳): category 필수값 검사, victim_name/victim_phone 루프의
       비교식+nv 2곳, address_changed 비교식, category/region/address/
       manager 루프의 비교식+nv 2곳, 공종 동기화 블록의 _nc — category
       필드 하나가 이 함수 안에서 raw로 3번(순차 실행이라 서로 가리지
       않고 전부 실행된다) 읽혔다.
     · api_est_band_set — ★3곳: major·severity·src.
     · api_schedule_event_add — ★3곳: title·event_date·event_time.
     · api_partner_license — ★5곳: license_status·license_no(사전 존재
       확인)·biz_no·license_no(실제 UPDATE, 재읽기)·license_trades.

   지시각도 밖에서 "신선한 각도" 두 갈래를 추가로 발견해 함께 고쳤다(전부
   같은 근본원인 — 어드민 JSON 본문이 비문자열을 보내면 문자열 전용
   메서드가 AttributeError/TypeError로 500):
     ① `.strip()`이 아니라 `_like_escape()`(1651행, 내부에서
        `(s or "").replace(...)`)를 통한 크래시 — api_campaign_create가
        호출하는 _campaign_recipients()의 `f['major']`(LIKE 절 인자) 및
        `_rg = (f.get("region") or "").strip()`. 이 헬퍼의 다른 호출부
        8곳을 전수 점검했으나 나머지는 전부 이미 안전한 값(request.args로
        이미 .strip() 된 문자열, 또는 DB row 값)만 넘겨 이 자리가 유일한
        실결함이었다.
     ② `.strip()`도 없이 `(v or "")[:N]` 슬라이스만 있는 자리 —
        api_schedule_event_add의 memo(리스트면 슬라이스가 되지만 int/bool
        이면 안 됨, 그리고 설령 슬라이스를 통과해도 sqlite3 바인딩이
        list/dict를 못 받아 결국 TypeError/InterfaceError로 500). 같은
        함수의 title·event_date·event_time과 나란히 있어 함께 고쳤다.
     ③ (같은 종류지만 별도 라우트) api_campaign_preview —
        `_fill_template(d.get("body") or "", s)`(내부 `.replace()`)와
        `AD_PREFIX + (d.get("subject") or "")`(문자열 결합). 캠페인
        생성과 같은 요청 모양을 공유하는 형제 화면이라 함께 고쳤다.

   합쳐서 이번 라운드가 고친 자리는 총 40곳(6개 지시 함수 36곳 + 자체발견
   헬퍼/형제함수 2곳·4자리)이다. 전부 형제 헬퍼 `_s(v, n=None)`(1503행)를
   그대로 재사용했다 — 새 헬퍼·새 로직 없음.

   round606이 인계한 78곳 중 이번에 다룬 것은 6개 지시함수뿐이다(자체발견
   2곳은 그 함수들의 호출 경로 안이라 별도 카운트하지 않음) — 나머지
   33개 함수는 정확한 목록이 없으므로 608 라운드가 같은 방법(app.py 전체
   재정규식스윕)으로 이어받는다.

      python test_scan_round607_fixes.py
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
print("  스캔 607라운드 회귀 — round606 인계 6개 함수 + 자체발견 2곳(형제함수),")
print("  raw .strip()/.replace()/슬라이스 형제결함군(round601~606과 같은 부류)")
print("=" * 72)

APP_SRC = read("app.py")

# ==================================================================
print("\n[0] 소스 확인 — 40곳 전부 옛 raw 패턴이 사라지고 _s()로 바뀌었다")
# ------------------------------------------------------------------
try:
    aac = _code_only(_py_fn_body(APP_SRC, "api_application_create"))
    chk('company = (d.get("company") or "").strip()' not in aac
        and 'company = _s(d.get("company"))' in aac,
        "★★★★★ api_application_create — company")
    chk('biz = (d.get("biz_no") or "").strip()[:20]' not in aac
        and 'biz = _s(d.get("biz_no"), 20)' in aac,
        "★★★★★ api_application_create — biz_no")
    chk('_phone = (d.get("phone") or "").strip()' not in aac
        and '_phone = _s(d.get("phone"))' in aac,
        "★★★★★ api_application_create — phone(사전검사)")
    chk('_email = (d.get("email") or "").strip()' not in aac
        and '_email = _s(d.get("email"))' in aac,
        "★★★★★ api_application_create — email(사전검사)")
    chk('(d.get("ceo") or "").strip()[:40]' not in aac and '_s(d.get("ceo"), 40)' in aac,
        "★★★★★ api_application_create — ceo(INSERT)")
    chk('(d.get("category") or "").strip()[:120]' not in aac
        and '_s(d.get("category"), 120)' in aac,
        "★★★★★ api_application_create — category(INSERT)")
    chk('(d.get("region") or "").strip()[:40]' not in aac and '_s(d.get("region"), 40)' in aac,
        "★★★★★ api_application_create — region(INSERT)")
    chk('(d.get("address") or "").strip()[:200]' not in aac
        and '_s(d.get("address"), 200)' in aac,
        "★★★★★ api_application_create — address(INSERT)")
    chk('(d.get("phone") or "").strip()[:20], (d.get("email") or "").strip()[:80]' not in aac
        and '_s(d.get("phone"), 20), _s(d.get("email"), 80)' in aac,
        "★★★★★ api_application_create — phone/email(INSERT, 형제 필드와 같은 "
        "방식으로 각자 독립적으로 _s() — round484 되돌림-증명과의 콜리전 이후 "
        "_phone/_email 재사용안에서 되돌림)")
    chk('(d.get("message") or "").strip()[:500]' not in aac and '_s(d.get("message"), 500)' in aac,
        "★★★★★ api_application_create — message(INSERT)")

    #  ⚠⚠ [라운드623] 이 자리를 round623이 다시 손봤다 — _like_escape(_s(...))
    #    직접호출을(round607의 기여) 같은 컬럼조합(name/region/major)에 이미 쓰이는
    #    공용 헬퍼 _kw_like_clause(_s(...), ["major"])로 교체해, 그 헬퍼가 이미
    #    막아 둔 가운뎃점 표기(ㆍ/･) 정규화까지 받게 했다(round499·_kw_like_clause
    #    docstring이 증언하는 사각지대 — 공식 업종표기 협력사 10곳이 이 화면에서만
    #    다시 새고 있었다). _s() 경유(존재 자체)는 그대로 유지되므로 이 검사의
    #    본래 취지(raw f['major'] 직결이 아니라 안전하게 감싼 값을 쓰는가)는
    #    안 바뀐다 — 리터럴만 갱신(round607 자신이 61·63·135와 겪은 것과 같은
    #    콜리전 처리 방식).
    cr = _code_only(_py_fn_body(APP_SRC, "_campaign_recipients"))
    chk("_like_escape(f['major'])" not in cr
        and ("_like_escape(_s(f.get('major')))" in cr
             or '_kw_like_clause(_s(f.get("major")), ["major"])' in cr),
        "★★★★★ _campaign_recipients — major(LIKE 절, _like_escape/_kw_like_clause "
        "경유 — _s() 로 안전하게 감쌈, round623이 공용헬퍼로 교체)")
    chk('_rg = (f.get("region") or "").strip()' not in cr and '_rg = _s(f.get("region"))' in cr,
        "★★★★★ _campaign_recipients — region")

    cp = _code_only(_py_fn_body(APP_SRC, "api_campaign_preview"))
    chk('_fill_template(d.get("body") or "", s)' not in cp
        and '_fill_template(_s(d.get("body")), s)' in cp,
        "★★★★★ api_campaign_preview — body(미리보기, .replace() 경유 결함/자체발견)")
    chk('AD_PREFIX + (d.get("subject") or "")' not in cp
        and 'AD_PREFIX + _s(d.get("subject"))' in cp,
        "★★★★★ api_campaign_preview — subject_preview(문자열결합 경유 결함/자체발견)")

    cc = _code_only(_py_fn_body(APP_SRC, "api_campaign_create"))
    chk('title = (d.get("title") or "").strip()[:120]' not in cc
        and 'title = _s(d.get("title"), 120)' in cc,
        "★★★★★ api_campaign_create — title")
    chk('subject = (d.get("subject") or "").strip()[:200]' not in cc
        and 'subject = _s(d.get("subject"), 200)' in cc,
        "★★★★★ api_campaign_create — subject")
    chk('text = (d.get("body") or "").strip()[:2000]' not in cc
        and 'text = _s(d.get("body"), 2000)' in cc,
        "★★★★★ api_campaign_create — body(text)")
    chk('audience = (d.get("audience") or "").strip()[:200]' not in cc
        and 'audience = _s(d.get("audience"), 200)' in cc,
        "★★★★★ api_campaign_create — audience")
    chk('"major": (d.get("major") or "").strip()[:120]' not in cc
        and '"major": _s(d.get("major"), 120)' in cc,
        "★★★★★ api_campaign_create — filter_json.major")
    chk('"region": (d.get("region") or "").strip()[:120]' not in cc
        and '"region": _s(d.get("region"), 120)' in cc,
        "★★★★★ api_campaign_create — filter_json.region")

    ced = _code_only(_py_fn_body(APP_SRC, "api_case_edit"))
    chk('not (d.get("category") or "").strip()' not in ced and 'not _s(d.get("category"))' in ced,
        "★★★★★ api_case_edit — category(필수값 검사)")
    chk('(d.get(f) or "").strip() != (c[f] or "")' not in ced
        and '_s(d.get(f)) != (c[f] or "")' in ced,
        "★★★★★ api_case_edit — 루프 비교식(victim_name/victim_phone, "
        "category/region/address/manager 두 루프 공통)")
    chk('nv = (d.get(f) or "").strip()[:40]' not in ced and 'nv = _s(d.get(f), 40)' in ced,
        "★★★★★ api_case_edit — victim 루프 nv")
    chk('nv = (d.get(f) or "").strip()[:120]' not in ced and 'nv = _s(d.get(f), 120)' in ced,
        "★★★★★ api_case_edit — category/region/address/manager 루프 nv")
    chk('(d.get("address") or "").strip() != (c["address"] or "")' not in ced
        and '_s(d.get("address")) != (c["address"] or "")' in ced,
        "★★★★★ api_case_edit — address_changed 비교식")
    chk('_nc = (d.get("category") or "").strip()[:120]' not in ced
        and '_nc = _s(d.get("category"), 120)' in ced,
        "★★★★★ api_case_edit — 공종(work_lots) 동기화 _nc(category 3번째 raw 재읽기)")

    ebs = _code_only(_py_fn_body(APP_SRC, "api_est_band_set"))
    chk('major = (d.get("major") or "").strip()[:60]' not in ebs
        and 'major = _s(d.get("major"), 60)' in ebs,
        "★★★★★ api_est_band_set — major")
    chk('sev = (d.get("severity") or "").strip()' not in ebs and 'sev = _s(d.get("severity"))' in ebs,
        "★★★★★ api_est_band_set — severity")
    chk('src = (d.get("src") or "").strip()[:200]' not in ebs and 'src = _s(d.get("src"), 200)' in ebs,
        "★★★★★ api_est_band_set — src")

    sea = _code_only(_py_fn_body(APP_SRC, "api_schedule_event_add"))
    chk('title = (d.get("title") or "").strip()' not in sea and 'title = _s(d.get("title"))' in sea,
        "★★★★★ api_schedule_event_add — title")
    chk('date_s = (d.get("event_date") or "").strip()' not in sea
        and 'date_s = _s(d.get("event_date"))' in sea,
        "★★★★★ api_schedule_event_add — event_date")
    chk('time_s = (d.get("event_time") or "").strip()' not in sea
        and 'time_s = _s(d.get("event_time"))' in sea,
        "★★★★★ api_schedule_event_add — event_time")
    chk('(d.get("memo") or "")[:500]' not in sea and '_s(d.get("memo"), 500)' in sea,
        "★★★★★ api_schedule_event_add — memo(.strip() 없는 슬라이스 결함/자체발견)")

    apl = _code_only(_py_fn_body(APP_SRC, "api_partner_license"))
    chk('st = (d.get("license_status") or "").strip()' not in apl
        and 'st = _s(d.get("license_status"))' in apl,
        "★★★★★ api_partner_license — license_status")
    chk('not (d.get("license_no") or "").strip()' not in apl
        and 'not _s(d.get("license_no"))' in apl,
        "★★★★★ api_partner_license — license_no(사전 존재확인)")
    chk('_bz = (d.get("biz_no") or "").strip()[:20]' not in apl
        and '_bz = _s(d.get("biz_no"), 20)' in apl,
        "★★★★★ api_partner_license — biz_no")
    chk('(d.get("license_no") or "").strip()[:60]' not in apl
        and '_s(d.get("license_no"), 60)' in apl,
        "★★★★★ api_partner_license — license_no(실제 UPDATE, 재읽기)")
    chk('(d.get("license_trades") or "").strip()[:200]' not in apl
        and '_s(d.get("license_trades"), 200)' in apl,
        "★★★★★ api_partner_license — license_trades")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드607 [0] 소스 확인", f"{type(e).__name__} {e}")

APP_HASH_BEFORE = hashlib.sha256(APP_SRC.encode("utf-8")).hexdigest()

# ==================================================================
print("\n[1] 준비 — 스크래치 DB, 관리자(최고관리자) 1명 + 사건 1건 + 협력사 1곳")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round607_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "bokguon.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r607-csrf"
H = {"X-CSRF-Token": CSRF}
A = DB = None
cid_edit = pid_partner = pid_license = None

try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    conn0.execute(
        "INSERT INTO admins(username,password_hash,name,role) "
        "VALUES('r607admin','x','검증','최고관리자')")
    cid_edit = conn0.execute(
        "INSERT INTO cases(case_no,status,category,region,address,manager,"
        "victim_name,victim_phone) VALUES('R607CASE','접수','금속','서울',"
        "'서울 강남구 1','기존담당자','기존피해자','01011112222')").lastrowid
    # 캠페인 수신자 산출(_campaign_recipients)이 실제로 1곳을 찾아 200 성공
    # 경로까지 가도록, 메일 동의·수신거부 아님·연락처 있음 조건을 만족하는
    # 활성 협력사를 심는다. major/region은 캠페인 생성 테스트가 보낼 정수
    # 필터값(607105/607106)의 문자열화와 그대로 맞춘다(LIKE·region_matches
    # 양쪽 다 매칭되게) — _campaign_recipients가 읽는 필터 컬럼은 partners.
    # major(공종)이지 category가 아니다.
    pid_partner = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,major,region,email,"
        "email_consent,email_opt_out) VALUES('R607캠페인업체','시공사','활성',"
        "'607105','607106','r607@test.invalid',1,0)").lastrowid
    pid_license = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,category,region) "
        "VALUES('R607면허업체','시공사','활성','금속','서울')").lastrowid
    conn0.commit()
    conn0.close()
    chk(bool(cid_edit and pid_partner and pid_license),
        "STEP 사건·협력사(캠페인용/면허조사용) 픽스처 생성",
        (cid_edit, pid_partner, pid_license))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드607 [1] 준비", f"{type(e).__name__} {e}")


def _admin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "r607admin"; sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = CSRF
    return c


# ==================================================================
print("\n[2] 실행 — 6개 함수 + 형제 2곳 전부에 비문자열(JSON 정수) 값을 "
      "보내도 500이 아니다")
# ------------------------------------------------------------------
try:
    r1 = _admin_client().post(
        "/api/applications/manual", headers=H,
        json={"company": 607001, "major": "전기", "ceo": 607002, "category": 607003,
              "region": 607004, "address": 607005, "message": 607008})
    rb1 = r1.get_json() or {}
    chk(r1.status_code == 200 and rb1.get("ok") is True,
        "★★★★★ api_application_create — company/ceo/category/region/address/"
        "message를 JSON 정수로 보내도 500 대신 200", (r1.status_code, rb1))
    if rb1.get("ok"):
        arow = DB.get_db().execute(
            "SELECT company,ceo,category,region,address,message FROM "
            "partner_applications WHERE id=?", (rb1["id"],)).fetchone()
        chk(arow and (arow["company"], arow["ceo"], arow["category"], arow["region"],
                      arow["address"], arow["message"])
            == ("607001", "607002", "607003", "607004", "607005", "607008"),
            "STEP partner_applications에 전부 문자열로 저장됐다",
            dict(arow) if arow else None)

    r1b = _admin_client().post(
        "/api/applications/manual", headers=H,
        json={"company": "R607전화확인", "major": "전기", "phone": 607006})
    chk(r1b.status_code != 500,
        "★★★★★ api_application_create — phone을 JSON 정수로 보내도 500이 "
        "아니다(형식은 어차피 안 맞아 400 — 크래시 여부만 확인)",
        (r1b.status_code, r1b.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드607 [2] api_application_create", f"{type(e).__name__} {e}")

try:
    r2 = _admin_client().post(
        "/api/campaigns", headers=H,
        json={"title": 607101, "subject": 607102, "body": 607103, "channel": "메일",
              "audience": 607104, "major": 607105, "region": 607106})
    rb2 = r2.get_json() or {}
    chk(r2.status_code == 200 and rb2.get("ok") is True,
        "★★★★★ api_campaign_create(+_campaign_recipients) — title/subject/body/"
        "audience/major/region을 전부 JSON 정수로 보내도 500 대신 200"
        "(수신자 1곳 매칭까지 확인)", (r2.status_code, rb2))
    if rb2.get("ok"):
        crow = DB.get_db().execute(
            "SELECT title, audience FROM campaigns WHERE id=?", (rb2["id"],)).fetchone()
        chk(crow and crow["title"] == "607101" and crow["audience"] == "607104",
            "STEP campaigns에 title/audience가 문자열로 저장됐다",
            dict(crow) if crow else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드607 [2] api_campaign_create", f"{type(e).__name__} {e}")

try:
    r2p = _admin_client().post(
        "/api/campaigns/preview", headers=H,
        json={"body": 607107, "subject": 607108, "channel": "메일", "major": 607105})
    chk(r2p.status_code == 200 and (r2p.get_json() or {}).get("ok") is True,
        "★★★★★ api_campaign_preview — body/subject를 JSON 정수로 보내도 500 "
        "대신 200", (r2p.status_code, r2p.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드607 [2] api_campaign_preview", f"{type(e).__name__} {e}")

try:
    r3 = _admin_client().patch(
        f"/api/cases/{cid_edit}", headers=H,
        json={"category": 607010, "region": 607011, "address": 607012, "manager": 607013})
    rb3 = r3.get_json() or {}
    chk(r3.status_code == 200 and rb3.get("ok") is True,
        "★★★★★ api_case_edit — category/region/address/manager를 JSON 정수로 "
        "보내도 500 대신 200(category 필수검사·루프·work_lots 동기화 _nc까지 "
        "한 요청으로 커버)", (r3.status_code, rb3))
    if rb3.get("ok"):
        crow2 = DB.get_db().execute(
            "SELECT category,region,address,manager FROM cases WHERE id=?",
            (cid_edit,)).fetchone()
        chk(dict(crow2) == {"category": "607010", "region": "607011",
                             "address": "607012", "manager": "607013"},
            "STEP cases에 전부 문자열로 저장됐다", dict(crow2) if crow2 else None)

    r3b = _admin_client().patch(
        f"/api/cases/{cid_edit}", headers=H, json={"victim_name": 607014})
    rb3b = r3b.get_json() or {}
    chk(r3b.status_code == 200 and rb3b.get("ok") is True,
        "★★★★★ api_case_edit — victim_name을 JSON 정수로 보내도 500 대신 200",
        (r3b.status_code, rb3b))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드607 [2] api_case_edit", f"{type(e).__name__} {e}")

try:
    r4 = _admin_client().post(
        "/api/est-bands", headers=H,
        json={"major": 607020, "severity": "경미", "src": 607021, "min_price": 1000})
    rb4 = r4.get_json() or {}
    chk(r4.status_code == 200 and rb4.get("ok") is True,
        "★★★★★ api_est_band_set — major/src를 JSON 정수로 보내도 500 대신 200",
        (r4.status_code, rb4))
    if rb4.get("ok"):
        erow = DB.get_db().execute(
            "SELECT major, src FROM est_check_band WHERE major=? AND severity='경미'",
            ("607020",)).fetchone()
        chk(erow and erow["major"] == "607020" and erow["src"] == "607021",
            "STEP est_check_band에 major/src가 문자열로 저장됐다",
            dict(erow) if erow else None)

    r4b = _admin_client().post(
        "/api/est-bands", headers=H, json={"major": "금속", "severity": 607022, "src": "근거"})
    chk(r4b.status_code != 500,
        "★★★★★ api_est_band_set — severity를 JSON 정수로 보내도 500이 아니다"
        "(SEVERITY_VALUES 밖이라 400 — 크래시 여부만 확인)",
        (r4b.status_code, r4b.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드607 [2] api_est_band_set", f"{type(e).__name__} {e}")

try:
    r5 = _admin_client().post(
        "/api/schedule-events", headers=H,
        json={"title": 607030, "event_date": "2026-09-20", "memo": 607031})
    rb5 = r5.get_json() or {}
    chk(r5.status_code == 200 and rb5.get("ok") is True,
        "★★★★★ api_schedule_event_add — title/memo를 JSON 정수로 보내도 500 "
        "대신 200", (r5.status_code, rb5))
    if rb5.get("ok"):
        srow = DB.get_db().execute(
            "SELECT title, memo FROM schedule_events WHERE id=?", (rb5["id"],)).fetchone()
        chk(srow and srow["title"] == "607030" and srow["memo"] == "607031",
            "STEP schedule_events에 title/memo가 문자열로 저장됐다",
            dict(srow) if srow else None)

    r5b = _admin_client().post(
        "/api/schedule-events", headers=H,
        json={"title": "정상제목", "event_date": 20260920})
    chk(r5b.status_code != 500,
        "★★★★★ api_schedule_event_add — event_date를 JSON 정수로 보내도 500이 "
        "아니다(포맷이 안 맞아 400 — 크래시 여부만 확인)",
        (r5b.status_code, r5b.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드607 [2] api_schedule_event_add", f"{type(e).__name__} {e}")

try:
    r6 = _admin_client().post(
        f"/api/partners/{pid_license}/license", headers=H,
        json={"license_status": "미확인", "license_no": 607040, "license_trades": 607041})
    rb6 = r6.get_json() or {}
    chk(r6.status_code == 200 and rb6.get("ok") is True,
        "★★★★★ api_partner_license — license_no/license_trades를 JSON 정수로 "
        "보내도 500 대신 200", (r6.status_code, rb6))
    if rb6.get("ok"):
        lrow = DB.get_db().execute(
            "SELECT license_no, license_trades FROM partners WHERE id=?",
            (pid_license,)).fetchone()
        chk(lrow and lrow["license_no"] == "607040" and lrow["license_trades"] == "607041",
            "STEP partners에 license_no/license_trades가 문자열로 저장됐다",
            dict(lrow) if lrow else None)

    r6b = _admin_client().post(
        f"/api/partners/{pid_license}/license", headers=H,
        json={"license_status": "미확인", "biz_no": 1234567890})
    chk(r6b.status_code != 500,
        "★★★★★ api_partner_license — biz_no를 JSON 정수로 보내도 500이 아니다"
        "(체크섬 통과 여부는 이 결함과 무관 — 크래시 여부만 확인)",
        (r6b.status_code, r6b.get_json()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드607 [2] api_partner_license", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[3] 회귀 안전 — 같은 요청에 원래 타입(문자열) 값을 보내는 정상 경로는 "
      "그대로 동작한다")
# ------------------------------------------------------------------
try:
    s1 = _admin_client().patch(
        f"/api/cases/{cid_edit}", headers=H, json={"manager": "새담당자"})
    sb1 = s1.get_json() or {}
    chk(s1.status_code == 200 and sb1.get("ok") is True,
        "STEP api_case_edit — 문자열 manager는 지금도 200", (s1.status_code, sb1))

    s2 = _admin_client().post(
        "/api/schedule-events", headers=H,
        json={"title": "문자열 제목", "event_date": "2026-09-21", "memo": "메모"})
    sb2 = s2.get_json() or {}
    chk(s2.status_code == 200 and sb2.get("ok") is True,
        "STEP api_schedule_event_add — 문자열 title/event_date/memo는 지금도 200",
        (s2.status_code, sb2))

    s3 = _admin_client().post(
        f"/api/partners/{pid_license}/license", headers=H,
        json={"license_status": "미확인", "license_trades": "가드레일,울타리"})
    sb3 = s3.get_json() or {}
    chk(s3.status_code == 200 and sb3.get("ok") is True,
        "STEP api_partner_license — 문자열 license_trades는 지금도 200",
        (s3.status_code, sb3))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드607 [3] 회귀 안전", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[4] 되돌리기 — app.py 파일은 안 건드리고 공용 헬퍼 A._s만 '607 이전'"
      "(문자열 강제 없는 raw strip) 버전으로 몽키패치해, [2]의 대표 요청들이 "
      "실제로 다시 500이 되는지 확인 후 즉시 원복")
# ------------------------------------------------------------------
_real_s = A._s


def _s_pre607(v, n=None):
    """607 수정 직전의 _s() 호출부 부재 상황을 재현하는 몽키패치 전용 함수 —
       진짜 _s()와의 유일한 차이는 str() 강제(isinstance 분기)가 없다는 것."""
    t = (v or "").strip()
    return t[:n] if n else t


try:
    A._s = _s_pre607

    rr1 = _admin_client().post(
        "/api/applications/manual", headers=H,
        json={"company": 707001, "major": "전기"})
    chk(rr1.status_code == 500,
        "★★★★★ 되돌리면 api_application_create(company)이 다시 500", rr1.status_code)

    rr2 = _admin_client().post(
        "/api/campaigns", headers=H,
        json={"title": 707002, "channel": "메일", "subject": "제목", "body": "본문"})
    chk(rr2.status_code == 500,
        "★★★★★ 되돌리면 api_campaign_create(title)이 다시 500", rr2.status_code)

    rr2b = _admin_client().post(
        "/api/campaigns/preview", headers=H,
        json={"body": "정상본문", "channel": "메일", "major": 707003})
    chk(rr2b.status_code == 500,
        "★★★★★ 되돌리면 _campaign_recipients(major, _like_escape 경유)가 다시 "
        "500(api_campaign_preview 호출 경로로 재현)", rr2b.status_code)

    rr3 = _admin_client().patch(
        f"/api/cases/{cid_edit}", headers=H, json={"category": 707004})
    chk(rr3.status_code == 500,
        "★★★★★ 되돌리면 api_case_edit(category)이 다시 500", rr3.status_code)

    rr4 = _admin_client().post(
        "/api/est-bands", headers=H,
        json={"major": 707005, "severity": "경미", "src": "근거", "min_price": 1000})
    chk(rr4.status_code == 500,
        "★★★★★ 되돌리면 api_est_band_set(major)이 다시 500", rr4.status_code)

    rr5 = _admin_client().post(
        "/api/schedule-events", headers=H,
        json={"title": 707006, "event_date": "2026-09-22"})
    chk(rr5.status_code == 500,
        "★★★★★ 되돌리면 api_schedule_event_add(title)이 다시 500", rr5.status_code)

    rr6 = _admin_client().post(
        f"/api/partners/{pid_license}/license", headers=H,
        json={"license_status": "미확인", "license_trades": 707007})
    chk(rr6.status_code == 500,
        "★★★★★ 되돌리면 api_partner_license(license_trades)가 다시 500", rr6.status_code)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드607 [4] 되돌리기", f"{type(e).__name__} {e}")
finally:
    A._s = _real_s

# 되돌리기 절차 동안 진짜 app.py 파일은 전혀 건드리지 않았음을 해시로 확인
APP_HASH_AFTER = hashlib.sha256(read("app.py").encode("utf-8")).hexdigest()
chk(APP_HASH_BEFORE == APP_HASH_AFTER,
    "★★★★★ 되돌리기 절차 동안 app.py 파일 내용이 전혀 안 바뀌었다"
    "(몽키패치만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

# 원복 확인 — 같은 모양의 요청이 다시 정상으로 돌아오는지(대표 2개)
try:
    rz1 = _admin_client().post(
        "/api/applications/manual", headers=H, json={"company": 808001, "major": "전기"})
    chk(rz1.status_code == 200,
        "★★★★★ A._s 원복 후 api_application_create의 숫자 company가 다시 정상(200)",
        rz1.status_code)

    rz2 = _admin_client().patch(
        f"/api/cases/{cid_edit}", headers=H, json={"category": 808002})
    chk(rz2.status_code == 200,
        "★★★★★ A._s 원복 후 api_case_edit도 다시 정상(200)", rz2.status_code)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드607 원복 확인", f"{type(e).__name__} {e}")


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
