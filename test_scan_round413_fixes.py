# -*- coding: utf-8 -*-
"""스캔 413라운드 회귀 — api_login_otp()(2단계 인증 코드 대조)의 무차별대입
   방어가 session["otp_tries"] 하나에만 의존해, 클라이언트가 최신 쿠키를
   반영하지 않고 같은 쿠키를 계속 재전송하면 시도 횟수가 영원히 "1번째"로
   보이던 결함.

  배경: 이 앱은 서버측 세션저장소 없이 Flask 기본 서명쿠키를 쓴다(app.py:
  103-115, SESSION_TYPE 없음) — session 값은 클라이언트가 보낸 쿠키 그
  자체다. /api/login(2747-60행)은 새 대기세션을 발급하기 **전**에 이미
  _recent_fails(login_attempts 테이블 기반, (계정,IP) 스코프)로 재로그인을
  통한 "시도예산 리필"을 막아 두고 있는데, 실제로 코드를 대조하는 자리인
  api_login_otp() 자신에는 이 DB기반 체크가 없어 세션쿠키 재전송만으로
  그 방어를 완전히 우회할 수 있었다 — 411·412와 같은 클래스("형제는 이미
  쓰는 관례를 한 곳만 안 따름").

  고침: api_login_otp() 진입부에도 /api/login과 똑같은 _recent_fails/
  MAX_LOGIN_FAILS/LOCKOUT_MINUTES 조합을 그대로 적용한다(새 정책·새 테이블
  불필요 — 이미 있는 인프라를 다른 진입점에도 적용하는 것뿐).

      python test_scan_round413_fixes.py
"""
import io
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

NEW_GUARD = (
    '    otp_fails = _recent_fails(conn, "OTP:" + u["username"])\n'
    '    if otp_fails >= MAX_LOGIN_FAILS:'
)

print("=" * 72)
print("  스캔 413라운드 회귀 — OTP 코드대조 무차별대입 방어가 세션쿠키 재전송에 우회됨")
print("=" * 72)

print("\n[1] 소스 확인")
_i0 = APP_SRC.index("def api_login_otp(")
_i1 = APP_SRC.index("\ndef ", _i0 + 1)
_body = APP_SRC[_i0:_i1]
chk(NEW_GUARD in _body,
    "★★★★★ api_login_otp() 가 /api/login과 같은 _recent_fails 잠금을 이제 쓴다")
chk(_body.index(NEW_GUARD) < _body.index('tries = int(session.get("otp_tries")'),
    "  이 잠금검사가 session 기반 카운터보다 먼저 실행된다(재전송으로 못 건너뜀)")

print("\n[2] 실행 — 같은 세션쿠키를 반복 재전송하는 비협조적 클라이언트를 재현")
_tmpdir = tempfile.mkdtemp(prefix="round413_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A
    import crypto_util as CRYPTO

    conn = DB.get_db()
    uname = "r413otp"
    conn.execute(
        "INSERT INTO admins(username,password_hash,name,role,totp_secret,totp_enabled,created_at) "
        "VALUES(?,?,?,?,?,1,?)",
        (uname, DB.hash_pw("R413!pw12345"), "검증", "중간관리자",
         CRYPTO.encrypt("JBSWY3DPEHPK3PXP"), DB.now()))
    conn.commit()

    def _replay_attack(n_attempts):
        """otp_pending 세션은 한 번만 세우고, 매 시도 전 otp_tries 를 강제로
           0(또는 부재)으로 되돌려 '항상 최초 쿠키만 재전송하는' 공격자를
           흉내낸다 — 원시 쿠키 헤더를 직접 다루는 것보다 이식성 있게
           같은 효과를 낸다(세션쿠키가 곧 그 값이라는 사실 자체가 결함의
           본질이므로, session_transaction 으로 그 값을 고정하는 것이
           정확히 그 위협모델의 재현이다)."""
        client = A.app.test_client()
        with client.session_transaction() as sess:
            sess["otp_pending"] = uname
            sess["otp_since"] = int(time.time())
        results = []
        for _ in range(n_attempts):
            with client.session_transaction() as sess:
                sess.pop("otp_tries", None)   # 재전송 — attempts 카운터가 절대 안 오름
            r = client.post("/api/login/otp", json={"code": "000000"})
            results.append(r.status_code)
        return results

    codes = _replay_attack(12)
    chk(all(c in (401, 429) for c in codes), "  전부 401 또는 429 응답(예외 없음)", codes)
    chk(429 in codes,
        "★★★★★ 세션쿠키를 12번 재전송해도 DB 누적 실패로 결국 429(잠김)가 뜬다"
        "(고치기 전엔 세션 카운터가 매번 '1번째'로 보여 12번 전부 401이었다)",
        codes)
    n_401_before_lock = codes.index(429) if 429 in codes else len(codes)
    chk(n_401_before_lock <= A.MAX_LOGIN_FAILS,
        f"  실제 통과되는 추측 횟수가 MAX_LOGIN_FAILS({A.MAX_LOGIN_FAILS})를 안 넘는다",
        n_401_before_lock)

    n_fails_db = conn.execute(
        "SELECT COUNT(*) c FROM login_attempts WHERE username=? AND success=0",
        ("OTP:" + uname,)).fetchone()["c"]
    chk(n_fails_db >= A.MAX_LOGIN_FAILS,
        "  DB login_attempts 에는 처음부터 실패가 정상적으로 누적돼 있었다"
        "(잠금 인프라 자체는 멀쩡 — 이 라운드 전에도 그랬다)", n_fails_db)

    print("\n[3] 대조군 — 정상(협조적) 클라이언트는 회귀 없이 기존 동작 그대로")
    conn.execute("DELETE FROM login_attempts WHERE username=?", ("OTP:" + uname,))
    conn.commit()
    client2 = A.app.test_client()
    with client2.session_transaction() as sess:
        sess["otp_pending"] = uname
        sess["otp_since"] = int(time.time())
    coop_codes = []
    for _ in range(A.OTP_MAX_TRIES + 1):
        r = client2.post("/api/login/otp", json={"code": "000000"})
        coop_codes.append(r.status_code)
    chk(coop_codes[:-1] == [401] * A.OTP_MAX_TRIES and coop_codes[-1] == 429,
        f"  협조적 클라이언트는 정확히 {A.OTP_MAX_TRIES}번의 401 뒤 429(회귀없음)",
        coop_codes)

    print("\n[4] 되돌리기 — 옛 코드(세션카운터만)로 되돌리면 재전송 공격이 재현되는가")
    #  ⚠⚠ [라운드612] round412·414가 확립한 안전패턴으로 이관 — 원래는 되돌린
    #    전체 app.py 소스를 실제 on-disk APP_PATH 에 잠깐 써넣고 subprocess로
    #    재현한 뒤 finally에서 복원했다(round409~515대 옛 세대 기법 — write→
    #    subprocess.run→write 사이의 창을 다른 세션이 관측하면 충돌한다,
    #    round590이 실제로 겪음). 함수 본문 문자열만 옛 형태(잠금검사 없음)로
    #    되돌려 exec(compile(...))로 네임스페이스 사본에 재구성하고, A.app.
    #    view_functions["api_login_otp"] 를 잠깐 치환해 같은 test_client() 로
    #    직접 호출한다(실제 파일은 전혀 안 건드림, 이 라우트엔 @require_admin
    #    같은 데코레이터가 없어 재구성 함수를 그대로 꽂으면 된다).
    #  ⚠ 다음 라우트(api_otp_status)가 @app.get(...)+@require_admin 두 데코레이터를
    #    달고 있어, 경계를 "\ndef "(다음 def 줄)로 잡으면 그 데코레이터 두 줄만
    #    뒤에 딸려와 컴파일이 SyntaxError 로 깨진다(실측) — 이 파일 사이는 빈 줄이
    #    두 줄이라(round409 의 api_contact_import 와 같은 관례) "\n\n\n" 로 자른다.
    _fn_start = APP_SRC.index("\ndef api_login_otp(")
    _fn_end = APP_SRC.index("\n\n\n", _fn_start)
    _cur_fn_src = APP_SRC[_fn_start:_fn_end]
    chk(NEW_GUARD in _cur_fn_src, "  되돌리기 준비 — 현재 함수 본문이 고친 형태임을 확인")

    #  NEW_GUARD(if 문 헤더 2줄)부터 그 다음 실행문(tries=...) 바로 앞까지를
    #  통째로 잘라내 if 블록 전체(본문 포함)를 제거한다.
    _old_block_start = _cur_fn_src.index(NEW_GUARD)
    _old_block_end = _cur_fn_src.index("    tries = int(session.get(\"otp_tries\")", _old_block_start)
    reverted_fn = _cur_fn_src[:_old_block_start] + _cur_fn_src[_old_block_end:]
    reverted_fn = reverted_fn.replace(
        "def api_login_otp():", "def _api_login_otp_pre413():", 1)
    chk(NEW_GUARD not in reverted_fn and "_api_login_otp_pre413" in reverted_fn,
        "  되돌리기 준비 — 되돌린 함수본문에 새 코드 흔적이 안 남는다(실제 파일은 안 건드림)")

    _ns = dict(vars(A))
    exec(compile(reverted_fn, "<round413_pre413_login_otp>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_login_otp_fn = _ns["_api_login_otp_pre413"]

    conn.execute("DELETE FROM login_attempts WHERE username=?", ("OTP:" + uname,))
    conn.commit()
    #  ⚠ [2]·[3]에서 이미 이 IP로 /api/login/otp 를 18회(12+6) 두드렸다 — 이
    #    되돌리기가 증명하려는 OTP: 잠금과는 별개인 IP기준 전역 레이트리밋
    #    (check_rate_limit(), app.py:976 부근, RATE_RULES 매칭)이 같은 프로세스를
    #    재사용하는 이 이관 방식에서는 그대로 누적돼 있다 — round414 가 이미
    #    같은 이유로 A._rate_buckets.clear() 를 썼던 것과 동일한 조치.
    A._rate_buckets.clear()
    client3 = A.app.test_client()
    with client3.session_transaction() as sess:
        sess["otp_pending"] = uname
        sess["otp_since"] = int(time.time())

    _orig_view = A.app.view_functions["api_login_otp"]
    A.app.view_functions["api_login_otp"] = old_login_otp_fn
    try:
        codes_old = []
        for _ in range(12):
            with client3.session_transaction() as sess:
                sess.pop("otp_tries", None)
            r = client3.post("/api/login/otp", json={"code": "000000"})
            codes_old.append(r.status_code)
    finally:
        A.app.view_functions["api_login_otp"] = _orig_view
    chk(429 not in codes_old,
        "★★★★★ 옛 코드(재구성, 실제 파일은 안 건드림)로 되돌리면 같은 재전송 공격이 "
        "12번 내내 401만 받고 429는 한 번도 안 뜬다(인과관계 직접증명)", codes_old)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")
#  [라운드612] 실제 app.py를 이제 전혀 안 쓰므로(위 [4]를 exec 재구성으로 이관) 이
#  안전망(디스크 복원 finally)도 함께 걷어냈다 — 더 이상 쓰는 곳이 없다.

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
