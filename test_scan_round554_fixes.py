# -*- coding: utf-8 -*-
"""스캔 554라운드 회귀 — 수동잠금해제(api_unlock_login, app.py:2565-)가 라운드488이
   새로 만든 "OTPSETUP:" 창구(2단계 인증 **등록확인**, api_otp_confirm 의 무차별대입
   방어)를 누락한 결함.

   배경 — 이 함수의 keys 튜플은 라운드175 자신의 주석("새 창구가 생기면 이 목록만
   늘린다")이 이미 명시한 확장 지점이다. 라운드414가 "PW:"·"PWX:" 두 창구를 추가할 때
   바로 그 규칙을 따라 목록과 SQL 자리수(?,?,?,?→?,?,?,?,?,?)를 함께 늘렸다. 그런데
   라운드488이 그 뒤에 api_otp_confirm()(형제 api_otp_disable의 "PWX:" 관례를 그대로
   옮김)에 "OTPSETUP:" 창구를 새로 추가하면서, 이 규칙을 놓쳤다 — api_unlock_login()
   자신은 전혀 건드리지 않았다(run_all_tests.py 의 라운드488 등록 문구에도 이 함수를
   손댔다는 언급이 없다). 직접 조사(하위위임 없음)로 이 저장소의 모든 _recent_fails/
   _log_attempt 호출부를 전수 grep 해 실제 접두사 7종(무접두 admin·"P:"·"I:"·"OTP:"·
   "PW:"·"PWX:"·"OTPSETUP:")을 확인한 뒤, api_unlock_login() 의 keys 튜플과 하나씩
   대조해 "OTPSETUP:" 하나만 빠져 있음을 확정했다.

   영향 — 등록확인 코드를 5회 틀려 그 창구만 잠긴 계정에 대해 운영자가 수동잠금해제를
   불러도, 응답은 {"ok":true,"cleared":N}(다른 창구가 안 잠겨 있었다면 N=0)으로
   "잠겨 있지 않았다"고 말하지만 OTPSETUP: 행은 그대로 남아 실제로는 여전히 잠겨
   있다 — 이 함수 자신의 독스트링이 막으려던 바로 그 "거짓 확인" 사고(라운드175가
   대소문자로, 라운드414가 PW:/PWX: 로 이미 두 번 겪은 것과 같은 클래스)가 세
   번째로 재발한 것.

   고침 — app.py:api_unlock_login() 의 keys 튜플에 "OTPSETUP:" + uname 하나를
   추가하고, SQL IN 자리수를 6개(?,?,?,?,?,?)에서 7개(?,?,?,?,?,?,?)로 늘렸다
   (라운드414가 PW:/PWX: 두 개를 추가할 때 쓴 것과 정확히 같은 방식 — 새 정책·
   새 헬퍼 없음).

   테스트 기법 — [0]은 실제 app.py 소스에서 고친 지점을 정확한 문자열로 대조한다.
   [1]~[3]은 실제 Flask 라우트(A.app.test_client())를 스크래치 DB 위에서 그대로
   호출해, 등록확인 브루트포스로 OTPSETUP: 창구를 실제로 잠근 뒤 지금 코드의
   수동잠금해제가 그 창구까지 실제로 지우는지 실측한다. [4]는 되돌림-증명 —
   **실제 on-disk app.py 파일은 전혀 건드리지 않는다.** 이 세션이 고치기 직전
   Read 로 확인한 원문 그대로를 별도 함수 문자열로 재구성해(exec) app 모듈
   네임스페이스의 사본(dict(vars(A)))에 얹어 직접 호출한다(round543·547·549·550·
   553 과 같은 기법) — 옛 코드는 200(성공)을 돌려주면서도 OTPSETUP: 실패기록을
   그대로 남겨 두는지 실측 대조해, 이 회귀가 실제로 결함을 잡아낼 능력이 있음을
   증명한다.

       python test_scan_round554_fixes.py
"""
import io
import os
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


print("=" * 72)
print("  스캔 554라운드 회귀 — 수동잠금해제가 OTPSETUP: 창구를 누락한 결함")
print("=" * 72)

APP_SRC = read("app.py")

# ==================================================================
print("\n[0] 소스 — 고친 지점이 실제로 app.py 에 있는가"
      "(동시편집 세션이 되돌렸다면 여기서부터 정직하게 실패해야 한다)")
# ------------------------------------------------------------------
try:
    import ast as _ast
    chk(_ast.parse(APP_SRC) is not None, "STEP app.py 전체 ast.parse 성공")

    start = APP_SRC.index("\ndef api_unlock_login(")
    end = APP_SRC.index("\n\n\n", start)
    fn_body = APP_SRC[start:end]

    chk('"OTPSETUP:" + uname' in fn_body,
        "★★★★★ api_unlock_login() 의 keys 튜플에 OTPSETUP: 이 있다"
        "(고치기 전엔 이 토큰이 없었다)")
    #  ⚠ 이 함수 위의 설명 주석 자신도 "OTPSETUP:" 이라는 글자를 그대로 인용하므로,
    #    맨 앞부분만 찾으면 주석 쪽이 먼저 걸려 순서 판정이 항상 거짓으로 나온다
    #    (실측: 이 테스트를 처음 작성했을 때 바로 이 이유로 오탐이 났다). " + uname"
    #    까지 붙은 정확한 코드 표현으로 찾아야 주석이 아니라 실제 튜플 줄이 잡힌다.
    _i_keys = fn_body.index("keys = (")
    _i_otpsetup = fn_body.index('"OTPSETUP:" + uname')
    _i_sql = fn_body.index("DELETE FROM login_attempts")
    chk(_i_keys < _i_otpsetup < _i_sql,
        "STEP OTPSETUP: 이 keys 튜플 대입문과 SQL 문 사이(같은 튜플 안)에 있다",
        (_i_keys, _i_otpsetup, _i_sql))
    chk("IN (?,?,?,?,?,?,?)" in fn_body,
        "★★★★ SQL 자리수가 7개로 늘었다(6개로 남아 있었다면 파라미터 개수 불일치로 "
        "sqlite3 가 즉시 예외를 낸다)")
    # 기존 6개 창구(무접두 admin·P·I·OTP·PW·PWX)는 이번 수정과 무관하게 그대로인가
    for _prefix in ('"P:" + uname', '"I:" + uname', '"OTP:" + uname',
                    '"PW:" + uname', '"PWX:" + uname'):
        chk(_prefix in fn_body, f"STEP 기존 창구 {_prefix} 그대로 유지(회귀 없음)")
    chk(fn_body.count("+ uname") == 6,
        "STEP uname 접두 조합이 정확히 6개(P/I/OTP/PW/PWX/OTPSETUP) — 중복 추가·오타 아님",
        fn_body.count("+ uname"))

    # 이 저장소 전체에서 _recent_fails/_log_attempt 가 실제로 쓰는 접두사가
    # 정확히 이 7종(무접두 포함)뿐인지 — 새 창구가 이 테스트 이후 또 늘면
    # 여기서 먼저 실패해 "테스트 자신이 낡았다"를 알려준다.
    import re as _re
    _found = set(_re.findall(r'_recent_fails\(conn,\s*"([A-Za-z]+):"', APP_SRC))
    _found |= set(_re.findall(r'_key\s*=\s*"([A-Za-z]+):"\s*\+', APP_SRC))
    chk(_found == {"P", "I", "OTP", "PW", "PWX", "OTPSETUP"},
        "STEP 저장소 전체의 접두사 집합이 이 튜플이 아는 것과 정확히 일치(새 창구 누락 감시)",
        _found)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드554 [0] 소스 확인", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[1] 준비 — 격리 스크래치 DB · TOTP 등록 진행중인 관리자 계정")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round554_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r554-csrf"
A = DB = CRYPTO = None
UNAME = "r554adm"

try:
    import db as DB
    DB.init_db()
    import app as A
    import crypto_util as CRYPTO

    conn0 = DB.get_db()
    #  ⚠ totp_enabled=0(아직 등록확정 전) — api_otp_confirm() 은 등록 1단계에서
    #    발급된 비밀키를 대조하는 자리라, 등록이 이미 끝난(enabled=1) 계정이
    #    아니라 이 상태를 전제로 한다(형제 api_otp_setup 참고).
    conn0.execute(
        "INSERT INTO admins(username,password_hash,name,role,totp_secret,totp_enabled,created_at) "
        "VALUES(?,?,?,?,?,0,?)",
        (UNAME, DB.hash_pw("R554Adm!2468"), "R554관리자", "중간관리자",
         CRYPTO.encrypt("JBSWY3DPEHPK3PXP"), DB.now()))
    conn0.commit(); conn0.close()
    chk(True, "STEP 스크래치 DB·관리자 계정 준비 완료")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드554 [1] 준비", f"{type(e).__name__} {e}")


def _session_for(client):
    with client.session_transaction() as sess:
        sess["admin"] = UNAME
        sess["admin_name"] = "R554관리자"
        sess["admin_role"] = "중간관리자"
        sess["pw_role"] = "admin"
        sess["_csrf"] = CSRF


def _n_locked():
    conn = DB.get_db()
    n = conn.execute(
        "SELECT COUNT(*) c FROM login_attempts WHERE username=? AND success=0",
        ("OTPSETUP:" + UNAME,)).fetchone()["c"]
    conn.close()
    return n


def _brute_otp_confirm(n):
    c = A.app.test_client()
    _session_for(c)
    codes = []
    for _ in range(n):
        r = c.post("/api/me/otp/confirm", json={"code": "000000"},
                   headers={"X-CSRF-Token": CSRF})
        codes.append(r.status_code)
    return codes


# ==================================================================
print("\n[2] 실행 — 등록확인(otp/confirm) 브루트포스로 OTPSETUP: 창구를 실제로 잠근다"
      "(라운드488 방어 자체의 회귀는 없는지도 함께 확인)")
# ------------------------------------------------------------------
try:
    codes = _brute_otp_confirm(A.MAX_LOGIN_FAILS + 2)
    chk(429 in codes,
        "STEP 등록확인 코드를 반복 오답하면 결국 429(잠김)가 뜬다(라운드488 방어, 회귀없음)",
        codes)
    n_locked = _n_locked()
    chk(n_locked >= A.MAX_LOGIN_FAILS,
        f"STEP OTPSETUP: 창구에 실패기록이 실제로 {A.MAX_LOGIN_FAILS}건 이상 쌓였다", n_locked)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드554 [2] 등록확인 브루트포스", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[3] 실행 — 지금 코드(실제 라우트)로 수동잠금해제를 부르면 "
      "OTPSETUP: 도 실제로 풀리는가")
# ------------------------------------------------------------------
try:
    c_unlock = A.app.test_client()
    _session_for(c_unlock)
    r_unlock = c_unlock.post("/api/login-attempts/unlock", json={"username": UNAME},
                             headers={"X-CSRF-Token": CSRF})
    chk(r_unlock.status_code == 200, "STEP 수동잠금해제 호출 자체는 성공", r_unlock.status_code)
    body_json = r_unlock.get_json()
    n_after = _n_locked()
    chk(n_after == 0,
        "★★★★★ 지금 코드: 잠금해제 뒤 OTPSETUP: 실패기록이 실제로 0건이 된다"
        "(고치기 전엔 이 창구만 그대로 남았다 — 아래 [4]에서 대조 실측)",
        (body_json, n_after))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드554 [3] 지금 코드 잠금해제", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[4] 되돌림-증명 — 수정 직전 원문(재구성)으로 같은 잠금해제를 부르면 "
      "OTPSETUP: 이 그대로 남는가"
      "(app.py 파일 자체는 전혀 건드리지 않는다 — exec() 로 별도 네임스페이스에서만 실행)")
# ------------------------------------------------------------------
#  ⚠ 이 세션이 수정하기 **직전**(위 [0]의 대상이 되기 전) Read 로 확인한 원문을
#    그대로 옮긴 것 — 실제 on-disk .py 파일은 이 문자열 재구성에 전혀 관여하지
#    않는다(round543·547·549·550·553 과 같은 안전 기법).
_PRE554_SRC = '''
def _api_unlock_login_pre554():
    d = body()
    uname = (d.get("username") or "").strip().lower()[:40]
    if not uname:
        return jsonify({"error": "아이디를 입력해 주세요."}), 400
    conn = DB.get_db()
    keys = (uname, "P:" + uname, "I:" + uname, "OTP:" + uname, "PW:" + uname, "PWX:" + uname)
    n = conn.execute(
        "DELETE FROM login_attempts WHERE success=0 AND username IN (?,?,?,?,?,?)", keys).rowcount
    DB.log(conn, actor(), "로그인 잠금 해제", f"{uname} (실패기록 {n}건 삭제)")
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "cleared": n})
'''

try:
    #  -- 위 [3]에서 이미 풀렸으므로, 되돌림-증명을 위해 새로 잠근다 --
    codes2 = _brute_otp_confirm(A.MAX_LOGIN_FAILS + 2)
    n_before = _n_locked()
    chk(n_before >= A.MAX_LOGIN_FAILS,
        "STEP 되돌림-증명 준비 — OTPSETUP: 다시 잠금 확인", (codes2, n_before))

    _ns = dict(vars(A))           # app 모듈 네임스페이스 복사(진짜 모듈은 안 건드림)
    exec(compile(_PRE554_SRC, "<round554_pre_reconstructed>", "exec"), _ns)
    old_fn = _ns["_api_unlock_login_pre554"]

    with A.app.test_request_context("/api/login-attempts/unlock", method="POST",
                                     json={"username": UNAME}):
        from flask import session as _s
        _s["admin"] = UNAME
        _s["admin_name"] = "R554관리자"
        _s["admin_role"] = "중간관리자"
        _s["pw_role"] = "admin"
        _s["_csrf"] = CSRF
        resp = old_fn()
    if isinstance(resp, tuple):
        resp_obj, code = resp[0], resp[1]
    else:
        resp_obj, code = resp, 200
    old_json = resp_obj.get_json()
    chk(code == 200 and old_json.get("ok") is True,
        "STEP 옛 코드(재구성) 호출 자체는 200·ok:true 를 돌려준다"
        "(바로 이 겉모습이 '거짓 확인'의 정체다)", (code, old_json))

    n_after_old = _n_locked()
    chk(n_after_old >= A.MAX_LOGIN_FAILS,
        "★★★★★ 옛 코드(재구성): 200·ok:true 를 돌려주고도 OTPSETUP: 실패기록은 "
        "그대로 남는다(지금 코드는 바로 위 [3]에서 0건으로 지웠다) — 이 차이가 "
        "이 회귀가 실제로 결함을 잡아낼 능력이 있다는 인과관계 증명이다",
        n_after_old)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드554 [4] 되돌림-증명", f"{type(e).__name__} {e}")


# ==================================================================
# 정리
# ------------------------------------------------------------------
os.environ.pop("BOKGUON_DB_PATH", None)
os.environ.pop("BOKGUON_UPLOAD_DIR", None)
os.environ.pop("BOKGUON_ENV", None)
os.environ.pop("BOKGUON_SEED_DEMO", None)
try:
    import shutil as _shutil
    _shutil.rmtree(_tmpdir, ignore_errors=True)
except Exception:
    pass

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
