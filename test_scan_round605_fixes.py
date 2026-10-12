# -*- coding: utf-8 -*-
"""스캔 605라운드 회귀 — 무인증 공개 로그인 4곳(api_login·api_partner_login·
   api_insurer_login·api_login_otp)의 username/login_id/code 필드가
   round601~604와 같은 형제결함군(raw `(d.get(...) or "").strip()`)이라,
   클라이언트가 JSON으로 숫자 등 비문자열 값을 보내면 AttributeError로
   500이 나던 결함.

   조사 배경 — round604가 인계한 이번 라운드 최우선 지시각도(①무인증 공개
   로그인 4곳)를 그대로 따라 각 함수를 직접 Read로 재확인했다. 시작 전
   wc -l app.py가 직전 라운드 종료시점과 정확히 21952줄로 일치해 동시편집은
   없었다. 4곳 전부 여전히 raw 패턴이었다:
     · api_login_otp() — code(구 2874행)
     · api_login() — username(구 3092행)
     · api_partner_login() — login_id(구 3185행)
     · api_insurer_login() — login_id(구 3424행)
   password 필드는 지시대로 손대지 않았다(DB.verify_pw()의 넓은 try/except가
   이미 안전 — round604가 이미 확인 완료).

   같은 grep(`\\.strip\\(\\)\\.lower\\(\\)\\[:60\\]` 등)을 app.py 전체로
   넓히던 중 같은 파일 안에서 5번째 형제를 우연히 발견했다:
   _sub_create_impl()(보험사·협력사 포털의 하위계정 생성 공용 함수 —
   /api/insurer/subaccounts·/api/partner/subaccounts 둘 다 이 함수를 호출)
   의 login_id도 똑같은 raw 패턴이었다. require_portal_owner로 인증은
   걸려 있지만(조직 원계정 로그인 상태 필요 — ②중간우선순위와 같은 성격의
   포털 세션경로) 원계정이 하위계정 login_id를 숫자로 보내면(클라이언트
   실수·연동 오류) 500이었다. 원래 지시(①)의 4곳과 기계적으로 동일한
   한 줄짜리 결함이라 함께 고쳤다.

   같은 raw 패턴이 app.py 전체에 5곳 더 있음을 확인했다(api_admin_create의
   username, api_unlock_login의 uname, api_otp_confirm의 code,
   api_insurer_credentials의 login_id 2곳) — 전부 require_role/require_admin/
   session.admin_role 게이트 뒤(로그인한 직원 전용)라 round604가 이미
   "어드민 콘솔 전용 더미"(③, ~85곳)로 분류해 둔 범위에 속한다. 이번
   라운드도 지시대로 의도적으로 손대지 않고 606 인계에 남긴다.

   고침 — 형제들이 이미 쓰는 _s(d.get(...), n)을 그대로 재사용했다(app.py):
     · api_login_otp(): code = _s(body().get("code"), 32)
     · api_login(): username = _s(d.get("username")).lower()[:60]
     · api_partner_login(): login_id = _s(d.get("login_id")).lower()[:60]
     · api_insurer_login(): login_id = _s(d.get("login_id")).lower()[:60]
     · _sub_create_impl(): login_id = _s(d.get("login_id")).lower()[:60]
   .lower()를 _s() 호출 뒤로 뺀 것 외에는 원본과 순서가 같다(strip→lower→
   slice) — _s(v, n)은 strip 후 바로 슬라이스하므로 n을 먼저 주면 slice가
   lower보다 먼저 실행돼 순서가 바뀐다. n 없이 _s(v)만 부르고 슬라이스는
   그 뒤에서 직접 하면 원래 순서가 그대로 보존된다(일반 문자·숫자에는
   차이가 없지만 원본 동작을 과잉수정 없이 정확히 재현하기 위함). OTP의
   code는 애초에 lower가 없어 _s(v, 32) 한 번으로 충분하다.

   [0] 소스 확인 — 5곳 전부 옛 raw 패턴이 사라지고 _s()로 바뀌었다.
   [1] 준비 — 스크래치 DB, 숫자 문자열 아이디의 관리자·보험사·협력사 계정 +
       TOTP 등록된 관리자 1명.
   [2] 실행 — 4개 로그인 엔드포인트 + 1개 하위계정생성에 각 필드를 JSON
       숫자로 보내도 500 대신 정상 응답(200/401)이고, 성공한 경우 세션·
       DB에 문자열로 저장/매칭됨을 확인(OTP는 실제 TOTP 코드로 끝까지
       로그인 완료까지 확인).
   [3] 회귀 안전 — 같은 계정에 문자열(원래 타입) 자격증명을 보내는 정상
       경로는 그대로 200(과잉교정 없음).
   [4] 되돌리기 — app.py 파일은 안 건드리고 공용 헬퍼 A._s만 '605 이전'
       (문자열 강제 없는 raw strip) 버전으로 몽키패치해, 같은 모양의
       요청들이 실제로 다시 500이 되는지 확인한 뒤 원복(app.py 해시
       불변도 확인) — 인과관계 직접증명.

   app.py 자신의 라우트/함수 5곳(api_login_otp·api_login·api_partner_login·
   api_insurer_login·_sub_create_impl)을 고쳤으므로 서버 재기동 필요.

      python test_scan_round605_fixes.py
"""
import hashlib
import io
import os
import shutil
import sys
import tempfile
import time

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
print("  스캔 605라운드 회귀 — 무인증 공개 로그인 4곳+하위계정생성 1곳,")
print("  username/login_id/code raw .strip() 형제결함군(round601~604와 같은 부류)")
print("=" * 72)

APP_SRC = read("app.py")

# ==================================================================
print("\n[0] 소스 확인 — 5곳 전부 옛 raw 패턴이 사라지고 _s()로 바뀌었다")
# ------------------------------------------------------------------
try:
    otp_code = _code_only(_py_fn_body(APP_SRC, "api_login_otp"))
    chk('(body().get("code") or "").strip()[:32]' not in otp_code,
        "★★★★★ api_login_otp()에 code의 raw strip이 더 이상 없다")
    chk('code = _s(body().get("code"), 32)' in otp_code,
        "★★★★★ api_login_otp()가 code = _s(body().get(\"code\"), 32)를 쓴다")

    login_code = _code_only(_py_fn_body(APP_SRC, "api_login"))
    chk('(d.get("username") or "").strip().lower()[:60]' not in login_code,
        "★★★★★ api_login()에 username의 raw strip이 더 이상 없다")
    chk('username = _s(d.get("username")).lower()[:60]' in login_code,
        "★★★★★ api_login()이 username = _s(d.get(\"username\")).lower()[:60]을 쓴다")

    partner_code = _code_only(_py_fn_body(APP_SRC, "api_partner_login"))
    chk('(d.get("login_id") or "").strip().lower()[:60]' not in partner_code,
        "★★★★★ api_partner_login()에 login_id의 raw strip이 더 이상 없다")
    chk('login_id = _s(d.get("login_id")).lower()[:60]' in partner_code,
        "★★★★★ api_partner_login()이 login_id = _s(d.get(\"login_id\")).lower()[:60]을 쓴다")

    insurer_code = _code_only(_py_fn_body(APP_SRC, "api_insurer_login"))
    chk('(d.get("login_id") or "").strip().lower()[:60]' not in insurer_code,
        "★★★★★ api_insurer_login()에 login_id의 raw strip이 더 이상 없다")
    chk('login_id = _s(d.get("login_id")).lower()[:60]' in insurer_code,
        "★★★★★ api_insurer_login()이 login_id = _s(d.get(\"login_id\")).lower()[:60]을 쓴다")

    sub_code = _code_only(_py_fn_body(APP_SRC, "_sub_create_impl"))
    chk('(d.get("login_id") or "").strip().lower()[:60]' not in sub_code,
        "★★★★★ _sub_create_impl()에 login_id의 raw strip이 더 이상 없다")
    chk('login_id = _s(d.get("login_id")).lower()[:60]' in sub_code,
        "★★★★★ _sub_create_impl()이 login_id = _s(d.get(\"login_id\")).lower()[:60]을 쓴다")

    # password 필드는 이번 라운드도 그대로(DB.verify_pw가 이미 안전 — round604 확인)
    chk('password = d.get("password") or ""' in login_code
        and 'password = d.get("password") or ""' in partner_code
        and 'password = d.get("password") or ""' in insurer_code,
        "STEP password 필드는 지시대로 손대지 않았다(3곳 모두 원래 형태 그대로)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드605 [0] 소스 확인", f"{type(e).__name__} {e}")

APP_HASH_BEFORE = hashlib.sha256(APP_SRC.encode("utf-8")).hexdigest()

# ==================================================================
print("\n[1] 준비 — 스크래치 DB, 숫자 문자열 아이디의 관리자·보험사·협력사 "
      "계정 + TOTP 등록된 관리자 1명")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round605_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "bokguon.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r605-csrf"
H = {"X-CSRF-Token": CSRF}
A = DB = CRYPTO = TOTP = None
iid = pid = None
ADMIN_USER, ADMIN_PW = "20260912", "R605Admin!234"
PARTNER_LOGIN, PARTNER_PW = "20260905", "R605Partner!234"
INSURER_LOGIN, INSURER_PW = "20260908", "R605Insurer!234"
OTP_USER, OTP_PW = "otpuser605", "R605Otp!5678"
OTP_SECRET = OTP_GOOD_CODE = None


def _fresh_secret_with_nonzero_code(totp_mod):
    """현재 구간 코드가 '0'으로 시작하지 않는 비밀키를 고른다 — JSON 정수로
       보낼 때 앞자리 0이 소실되는 것은 이 라운드가 고치는 결함과 무관한
       별개의 사전 조건이므로, 테스트 결정성을 위해 그 경우를 피한다."""
    for _ in range(50):
        s = totp_mod.new_secret()
        c = totp_mod.code_now(s)
        if c and not c.startswith("0"):
            return s, c
    raise RuntimeError("0으로 시작 안 하는 코드를 가진 비밀키를 못 찾음(극히 낮은 확률)")


try:
    import db as DB
    DB.init_db()
    import app as A
    import crypto_util as CRYPTO
    import totp as TOTP

    OTP_SECRET, OTP_GOOD_CODE = _fresh_secret_with_nonzero_code(TOTP)

    conn0 = DB.get_db()
    conn0.execute(
        "INSERT INTO admins(username,password_hash,name,role,created_at) "
        "VALUES(?,?,?,?,?)",
        (ADMIN_USER, DB.hash_pw(ADMIN_PW), "숫자아이디관리자605", "중간관리자", DB.now()))
    conn0.execute(
        "INSERT INTO admins(username,password_hash,name,role,totp_secret,totp_enabled,"
        "                   created_at) VALUES(?,?,?,?,?,1,?)",
        (OTP_USER, DB.hash_pw(OTP_PW), "검증605", "중간관리자",
         CRYPTO.encrypt(OTP_SECRET), DB.now()))
    conn0.execute(
        "INSERT INTO insurers(name,login_id,password_hash,status,created_at) "
        "VALUES('R605보험사',?,?,'활성',?)",
        (INSURER_LOGIN, DB.hash_pw(INSURER_PW), DB.now()))
    iid = conn0.execute("SELECT id FROM insurers WHERE login_id=?",
                         (INSURER_LOGIN,)).fetchone()["id"]
    conn0.execute(
        "INSERT INTO partners(name,partner_type,login_id,password_hash,status,category,"
        "                     region,created_at) "
        "VALUES('R605업체','시공사',?,?,'활성','가드레일','서울',?)",
        (PARTNER_LOGIN, DB.hash_pw(PARTNER_PW), DB.now()))
    pid = conn0.execute("SELECT id FROM partners WHERE login_id=?",
                         (PARTNER_LOGIN,)).fetchone()["id"]
    conn0.commit()
    conn0.close()
    chk(bool(iid and pid), "STEP 관리자(숫자아이디·OTP)·보험사·협력사 픽스처 생성", (iid, pid))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드605 [1] 준비", f"{type(e).__name__} {e}")


def _otp_pending_client(username):
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["otp_pending"] = username
        sess["otp_since"] = int(time.time())
    return c


def _insurer_owner_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["insurer_id"] = iid
        sess["insurer_name"] = "R605보험사"
        sess["_csrf"] = CSRF
    return c


# ==================================================================
print("\n[2] 실행 — 4개 로그인 엔드포인트 + 1개 하위계정생성에 필드를 "
      "JSON 숫자로 보내도 500 대신 정상 응답")
# ------------------------------------------------------------------
try:
    r1 = A.app.test_client().post("/api/login",
                                   json={"username": int(ADMIN_USER), "password": ADMIN_PW})
    rb1 = r1.get_json() or {}
    chk(r1.status_code == 200 and rb1.get("ok") is True and rb1.get("name") == "숫자아이디관리자605",
        "★★★★★ api_login — username을 JSON 정수로 보내도 500 대신 200, 정상 로그인 완료",
        (r1.status_code, rb1))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드605 [2] api_login(숫자 username)", f"{type(e).__name__} {e}")

try:
    r2 = A.app.test_client().post("/api/partner/login",
                                   json={"login_id": int(PARTNER_LOGIN), "password": PARTNER_PW})
    rb2 = r2.get_json() or {}
    chk(r2.status_code == 200 and rb2.get("ok") is True and rb2.get("name") == "R605업체",
        "★★★★★ api_partner_login — login_id를 JSON 정수로 보내도 500 대신 200, "
        "정상 로그인 완료", (r2.status_code, rb2))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드605 [2] api_partner_login(숫자 login_id)", f"{type(e).__name__} {e}")

try:
    r3 = A.app.test_client().post("/api/insurer/login",
                                   json={"login_id": int(INSURER_LOGIN), "password": INSURER_PW})
    rb3 = r3.get_json() or {}
    chk(r3.status_code == 200 and rb3.get("ok") is True and rb3.get("name") == "R605보험사",
        "★★★★★ api_insurer_login — login_id를 JSON 정수로 보내도 500 대신 200, "
        "정상 로그인 완료", (r3.status_code, rb3))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드605 [2] api_insurer_login(숫자 login_id)", f"{type(e).__name__} {e}")

try:
    # 대기 세션이 아예 없어도 code 파싱 자체는 크래시하지 않아야 한다 — 이 줄은
    # _otp_pending_user() 조회보다도 먼저 실행되므로 대기 세션 유무와 무관하다.
    r4a = A.app.test_client().post("/api/login/otp", json={"code": 999111})
    rb4a = r4a.get_json() or {}
    chk(r4a.status_code == 401 and "인증 시간이 지났습니다" in (rb4a.get("error") or ""),
        "★★★★★ api_login_otp — 대기 세션 없이 숫자 code를 보내도 500이 아니라 "
        "원래의 401(대기 세션 없음)", (r4a.status_code, rb4a))

    # 실제 대기 세션 + 진짜 유효한 TOTP 코드를 정수로 보내 끝까지 로그인되는지 확인
    otp_c = _otp_pending_client(OTP_USER)
    r4b = otp_c.post("/api/login/otp", json={"code": int(OTP_GOOD_CODE)})
    rb4b = r4b.get_json() or {}
    chk(r4b.status_code == 200 and rb4b.get("ok") is True and rb4b.get("name") == "검증605",
        "★★★★★ api_login_otp — 유효한 TOTP 코드를 JSON 정수로 보내도 500이 "
        "아니라 200, 실제 로그인 완료", (r4b.status_code, rb4b))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드605 [2] api_login_otp(숫자 code)", f"{type(e).__name__} {e}")

try:
    sub_c = _insurer_owner_client()
    r5 = sub_c.post("/api/insurer/subaccounts", headers=H,
                     json={"login_id": 20260930, "name": "하위담당605"})
    rb5 = r5.get_json() or {}
    chk(r5.status_code == 200 and rb5.get("ok") is True and rb5.get("login_id") == "20260930",
        "★★★★★ _sub_create_impl(보험사 하위계정생성) — login_id를 JSON 정수로 "
        "보내도 500 대신 200, 문자열 '20260930'으로 응답", (r5.status_code, rb5))
    if rb5.get("ok"):
        row5 = DB.get_db().execute(
            "SELECT login_id FROM portal_users WHERE org_type='insurer' AND org_id=?",
            (iid,)).fetchone()
        chk(row5["login_id"] == "20260930",
            "STEP DB(portal_users)에 login_id가 문자열 '20260930'으로 저장됐다",
            row5["login_id"] if row5 else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드605 [2] _sub_create_impl(숫자 login_id)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[3] 회귀 안전 — 같은 계정에 원래 타입(문자열) 자격증명을 보내는 "
      "정상 경로는 그대로 200(과잉교정 없음)")
# ------------------------------------------------------------------
try:
    s1 = A.app.test_client().post("/api/login", json={"username": ADMIN_USER, "password": ADMIN_PW})
    sb1 = s1.get_json() or {}
    chk(s1.status_code == 200 and sb1.get("ok") is True,
        "STEP api_login — 문자열 username은 지금 코드에서도 그대로 200", (s1.status_code, sb1))

    s2 = A.app.test_client().post("/api/partner/login",
                                   json={"login_id": PARTNER_LOGIN, "password": PARTNER_PW})
    sb2 = s2.get_json() or {}
    chk(s2.status_code == 200 and sb2.get("ok") is True,
        "STEP api_partner_login — 문자열 login_id는 지금 코드에서도 그대로 200",
        (s2.status_code, sb2))

    s3 = A.app.test_client().post("/api/insurer/login",
                                   json={"login_id": INSURER_LOGIN, "password": INSURER_PW})
    sb3 = s3.get_json() or {}
    chk(s3.status_code == 200 and sb3.get("ok") is True,
        "STEP api_insurer_login — 문자열 login_id는 지금 코드에서도 그대로 200",
        (s3.status_code, sb3))

    # 대소문자 섞인 정상 문자열도 여전히 소문자로 정규화되어 매칭된다(.lower() 위치를
    # 옮긴 것이 순서를 안 바꿨음을 확인 — round167 관례 유지)
    s4 = A.app.test_client().post("/api/partner/login",
                                   json={"login_id": PARTNER_LOGIN.upper() + "  ", "password": "x"})
    sb4 = s4.get_json() or {}
    # 계정은 못 찾아도(대문자+공백 조합은 원래 아이디와 다른 문자열이 아니라 트리밍+
    # 소문자화하면 같아진다) 500이 아니라 401만 나오면 된다 — 여기서는 크래시 여부만 본다.
    chk(s4.status_code in (200, 401),
        "STEP api_partner_login — 대문자·공백 섞인 문자열도 500 없이 처리된다",
        (s4.status_code, sb4))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드605 [3] 회귀 안전", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[4] 되돌리기 — app.py 파일은 안 건드리고 공용 헬퍼 A._s만 '605 이전'"
      "(문자열 강제 없는 raw strip) 버전으로 몽키패치해, 위와 같은 모양의 요청이 "
      "실제로 다시 500이 되는지 확인 후 즉시 원복")
# ------------------------------------------------------------------
_real_s = A._s


def _s_pre605(v, n=None):
    """605 수정 직전의 _s() 호출부 부재 상황을 재현하는 몽키패치 전용 함수 —
       진짜 _s()와의 유일한 차이는 str() 강제(isinstance 분기)가 없다는 것."""
    t = (v or "").strip()
    return t[:n] if n else t


try:
    A._s = _s_pre605

    rr1 = A.app.test_client().post("/api/login", json={"username": 555111, "password": "x"})
    chk(rr1.status_code == 500,
        "★★★★★ 되돌리면(_s 무력화) api_login의 숫자 username이 다시 500", rr1.status_code)

    rr2 = A.app.test_client().post("/api/partner/login",
                                    json={"login_id": 555222, "password": "x"})
    chk(rr2.status_code == 500,
        "★★★★★ 되돌리면 api_partner_login의 숫자 login_id도 다시 500", rr2.status_code)

    rr3 = A.app.test_client().post("/api/insurer/login",
                                    json={"login_id": 555333, "password": "x"})
    chk(rr3.status_code == 500,
        "★★★★★ 되돌리면 api_insurer_login의 숫자 login_id도 다시 500", rr3.status_code)

    rr4 = A.app.test_client().post("/api/login/otp", json={"code": 555444})
    chk(rr4.status_code == 500,
        "★★★★★ 되돌리면 api_login_otp의 숫자 code도 다시 500(대기 세션 유무와 무관)",
        rr4.status_code)

    sub_c2 = _insurer_owner_client()
    rr5 = sub_c2.post("/api/insurer/subaccounts", headers=H,
                       json={"login_id": 555555, "name": "되돌림확인"})
    chk(rr5.status_code == 500,
        "★★★★★ 되돌리면 _sub_create_impl의 숫자 login_id도 다시 500", rr5.status_code)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드605 [4] 되돌리기", f"{type(e).__name__} {e}")
finally:
    A._s = _real_s

# 되돌리기 절차 동안 진짜 app.py 파일은 전혀 건드리지 않았음을 해시로 확인
APP_HASH_AFTER = hashlib.sha256(read("app.py").encode("utf-8")).hexdigest()
chk(APP_HASH_BEFORE == APP_HASH_AFTER,
    "★★★★★ 되돌리기 절차 동안 app.py 파일 내용이 전혀 안 바뀌었다"
    "(몽키패치만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

# 원복 확인 — 같은 모양의 요청이 다시 정상으로 돌아오는지
try:
    rz1 = A.app.test_client().post("/api/login", json={"username": 666111, "password": "x"})
    chk(rz1.status_code == 401,
        "★★★★★ A._s 원복 후 api_login의 숫자 username이 다시 정상(401, 계정없음)",
        rz1.status_code)

    rz2 = A.app.test_client().post("/api/login/otp", json={"code": 666222})
    chk(rz2.status_code == 401,
        "★★★★★ A._s 원복 후 api_login_otp의 숫자 code도 다시 정상(401)", rz2.status_code)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드605 원복 확인", f"{type(e).__name__} {e}")


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
