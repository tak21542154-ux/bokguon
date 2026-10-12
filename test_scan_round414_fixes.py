# -*- coding: utf-8 -*-
"""스캔 414라운드 회귀 — api_change_password()(app.py:1300-)와 api_otp_disable()
   (app.py:2700-)의 "현재 비밀번호" 재확인이, 로그인·OTP검증(라운드413)과 달리
   무차별대입 방어(_recent_fails/_log_attempt)가 전혀 없던 결함. 세션만 탈취한
   공격자(예: 임시비밀번호 강제변경 세션 — PW_CHANGE_ALLOW 가 열어 둔 유일한
   API가 바로 이 change-password 자신이다)가 GET /api/csrf 로 스스로 CSRF
   토큰까지 발급받아, current 필드를 무제한으로 추측해 진짜 비밀번호를 알아낸
   뒤 같은 요청의 new 필드로 계정을 완전히 탈취할 수 있었다(정밀조사 Agent 발견,
   411~413과 같은 클래스: "형제는 이미 쓰는 관례를 한 곳만 안 따름").

   고침: 로그인이 이미 쓰는 _recent_fails/_log_attempt/MAX_LOGIN_FAILS/
   LOCKOUT_MINUTES 인프라를 그대로 이식(새 정책 없음). 잠금키는 "PW:"+label
   (label 은 로그인 때 입력한 아이디 그 자체 — 하위계정도 자기 로그인아이디)과
   otp_disable 은 "PWX:"+관리자아이디.

   이걸 고치며 부수적으로 드러난 세 번째 문제: 수동잠금해제(api_unlock_login,
   app.py:2396-)가 이미 "새 창구가 생기면 이 목록만 늘린다"(라운드175)고 스스로
   적어 둔 확장 지점인데, 새 창구 두 개("PW:"·"PWX:")를 그 목록에 안 넣으면
   운영자가 잠금을 풀었다는 200 응답을 받고도 change-password 잠금은 그대로
   남는 "거짓 성공"이 재발한다 — 그 목록과 SQL 자리수(?,?,?,?)를 함께 늘렸다.

       python test_scan_round414_fixes.py
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


APP_SRC = read("app.py")

#  각 수정의 정확한 전/후 텍스트 — Edit 로 실제 적용했던 그 문자열 그대로라
#  .replace() 되돌리기가 진짜 원래 코드를 복원한다(짐작으로 다시 만들지 않는다).
#  ⚠⚠ [라운드609] current/new 추출 줄은 이 라운드(414)의 diff 밖(잠금 인프라만
#    이식했을 뿐 이 줄 자체는 손대지 않았었다)인데, round609가 이 줄을 raw
#    (d.get(...) or "") 에서 _s(d.get(...)) 로 고쳤다(형제결함군 — 숫자 등을
#    보내면 password_policy_error() 내부 re.search 가 TypeError). OLD_1·NEW_1
#    양쪽 다 이 줄만 갱신해 동기화한다 — 이 라운드가 증명하려는 것(잠금 유무)과
#    무관한 줄이므로 되돌림-증명의 논리는 그대로다.
OLD_1 = '''    d = body()
    #  ⚠⚠ [라운드609] round601~608 형제결함군과 같은 결함 — current/new 가 raw
    #    (d.get(...) or "") 라, 비밀번호를 숫자 등으로 보내면(자동화 스크립트·
    #    연동 오류) password_policy_error() 내부 re.search(pattern, pw) 가
    #    TypeError 로 500이 된다. 형제 헬퍼 `_s()` 를 그대로 재사용한다.
    current, new = _s(d.get("current")), _s(d.get("new"))

    conn = DB.get_db()
    row = one(conn.execute(f"SELECT id, password_hash FROM {table} WHERE {col}=?", (ident,)))
    if not row or not DB.verify_pw(current, row["password_hash"]):
        DB.log(conn, label or "-", "비밀번호 변경 실패", "현재 비밀번호 불일치")
        conn.commit(); conn.close()
        return jsonify({"ok": False, "error": "현재 비밀번호가 올바르지 않습니다."}), 401'''
NEW_1 = '''    d = body()
    #  ⚠⚠ [라운드609] round601~608 형제결함군과 같은 결함 — current/new 가 raw
    #    (d.get(...) or "") 라, 비밀번호를 숫자 등으로 보내면(자동화 스크립트·
    #    연동 오류) password_policy_error() 내부 re.search(pattern, pw) 가
    #    TypeError 로 500이 된다. 형제 헬퍼 `_s()` 를 그대로 재사용한다.
    current, new = _s(d.get("current")), _s(d.get("new"))

    conn = DB.get_db()
    #  [보안] 계정 잠금 — 무차별 대입 방어. 로그인·OTP 와 같은 인프라를 그대로
    #    쓴다 — 세션만 탈취한 공격자가 현재 비밀번호를 무제한 추측 못 하게
    #    한다(라운드414). label 은 로그인 때 입력한 아이디 그대로라(하위계정도
    #    자기 아이디) 수동잠금해제(api_unlock_login)가 그대로 풀 수 있다.
    pw_key = "PW:" + (label or "")
    fails = _recent_fails(conn, pw_key)
    if fails >= MAX_LOGIN_FAILS:
        DB.log(conn, label or "-", "비밀번호 변경 차단(잠금)", client_ip())
        conn.commit(); conn.close()
        return jsonify({
            "ok": False,
            "error": f"현재 비밀번호 확인이 {MAX_LOGIN_FAILS}회 실패해 {LOCKOUT_MINUTES}분간 잠겼습니다.",
        }), 429
    row = one(conn.execute(f"SELECT id, password_hash FROM {table} WHERE {col}=?", (ident,)))
    pw_ok = bool(row) and DB.verify_pw(current, row["password_hash"])
    _log_attempt(conn, pw_key, pw_ok)
    if not pw_ok:
        DB.log(conn, label or "-", "비밀번호 변경 실패", "현재 비밀번호 불일치")
        conn.commit(); conn.close()
        return jsonify({"ok": False, "error": "현재 비밀번호가 올바르지 않습니다."}), 401'''

OLD_2 = '''    pw = body().get("password") or ""
    conn = DB.get_db()
    u = one(conn.execute("SELECT * FROM admins WHERE username=?", (session.get("admin"),)))
    if not u or not DB.verify_pw(pw, u["password_hash"]):
        conn.close(); return jsonify({"ok": False, "error": "비밀번호가 올바르지 않습니다."}), 401
    conn.execute("BEGIN IMMEDIATE")'''
NEW_2 = '''    pw = body().get("password") or ""
    conn = DB.get_db()
    #  [보안] 계정 잠금 — 무차별 대입 방어(라운드414, change-password 와 같은
    #    인프라). 실패해도 흔적이 전혀 안 남았던 것도 함께 고친다(DB.log 추가).
    uname = session.get("admin") or ""
    pw_key = "PWX:" + uname
    fails = _recent_fails(conn, pw_key)
    if fails >= MAX_LOGIN_FAILS:
        DB.log(conn, uname or "-", "2단계 인증 해제 차단(잠금)", client_ip())
        conn.commit(); conn.close()
        return jsonify({
            "ok": False,
            "error": f"비밀번호 확인이 {MAX_LOGIN_FAILS}회 실패해 {LOCKOUT_MINUTES}분간 잠겼습니다.",
        }), 429
    u = one(conn.execute("SELECT * FROM admins WHERE username=?", (session.get("admin"),)))
    pw_ok = bool(u) and DB.verify_pw(pw, u["password_hash"])
    _log_attempt(conn, pw_key, pw_ok)
    if not pw_ok:
        DB.log(conn, uname or "-", "2단계 인증 해제 실패", client_ip())
        conn.commit(); conn.close()
        return jsonify({"ok": False, "error": "비밀번호가 올바르지 않습니다."}), 401
    conn.execute("BEGIN IMMEDIATE")'''

#  ⚠⚠ [라운드554] 이 상수는 "지금 코드"의 리터럴 텍스트를 문자열로 그대로 들고
#    있다가 .replace(NEW_3, OLD_3)로 되돌리는 방식이라, 라운드554가 같은 함수에
#    "OTPSETUP:" 창구를 추가하며 이 주석·keys 튜플·SQL 자리수를 바꾸자 NEW_3 가
#    더 이상 실제 텍스트와 안 맞아 replace()가 조용히 no-op 되고(찾는 문자열이
#    없으니 아무것도 안 바뀜), "되돌린" 파일이 사실은 지금(수정된) 코드 그대로라
#    STILL_LOCKED 가 기대와 반대로 False 로 나와 이 스텝만 실패했다(실측 —
#    라운드554의 전체 배터리 1회차 실행에서 재현). OLD_3(이 라운드가 증명하려는
#    "PW:"·"PWX: 조차 없던 원래 결함")는 이번 변경과 무관해 그대로 두고, NEW_3만
#    라운드554 수정 후 실제 app.py 문구로 갱신한다 — round417을 round553이 갱신한
#    것과 같은 대응(자기 자신이 고친 코드가 아니라 다른 라운드가 나중에 그 자리를
#    다시 고쳐 리터럴 앵커가 낡은 경우, 증명하려는 인과관계 자체는 그대로 두고
#    앵커 문자열만 최신화한다).
OLD_3 = '''    keys = (uname, "P:" + uname, "I:" + uname, "OTP:" + uname)
    n = conn.execute(
        "DELETE FROM login_attempts WHERE success=0 AND username IN (?,?,?,?)", keys).rowcount'''
NEW_3 = '''    #  ⚠⚠ [라운드414] change-password·2단계인증해제 두 새 창구("PW:"·"PWX:")를
    #    추가하며 위 주석 규칙대로 여기 목록만 늘린다 — 자리수(?,?,?,?,?,?)도
    #    같이 늘려야 한다(안 늘리면 sqlite3 가 파라미터 개수 불일치로 즉시 예외).
    #  ⚠⚠ [라운드554] 라운드488이 2단계 인증 **등록확인**(api_otp_confirm, 형제
    #    api_otp_disable의 "PWX:" 관례를 그대로 옮김)에 "OTPSETUP:" 창구를 새로
    #    추가하면서, 바로 위 두 주석이 이미 명시한 "새 창구가 생기면 이 목록만
    #    늘린다"는 규칙을 놓쳤다 — 여기 keys 에는 추가되지 않았다. 실측: 등록확인
    #    코드를 5회 틀려 그 창구만 잠긴 상태에서 이 API를 불러도 "OTPSETUP:"
    #    행만 그대로 남아(다른 창구는 애초에 안 잠겼으니 cleared=0), 화면은
    #    {"ok":true,"cleared":0}로 "잠겨 있지 않았다"고 말하지만 실제로는 여전히
    #    잠겨 있다 — 바로 위 두 라운드가 이미 두 번 겪은 것과 같은 거짓 확인
    #    사고. 자리수(?,?,?,?,?,?,?)도 6→7로 함께 늘린다.
    keys = (uname, "P:" + uname, "I:" + uname, "OTP:" + uname, "PW:" + uname, "PWX:" + uname,
            "OTPSETUP:" + uname)
    n = conn.execute(
        "DELETE FROM login_attempts WHERE success=0 AND username IN (?,?,?,?,?,?,?)", keys).rowcount'''

print("=" * 72)
print("  스캔 414라운드 회귀 — change-password·2단계인증해제 무차별대입 방어 부재")
print("  + 수동잠금해제 누락창구(PW:/PWX:)")
print("=" * 72)

print("\n[1] 소스 확인")
chk(APP_SRC.count(NEW_1) == 1, "★★★★★ api_change_password() 수정이 정확히 1곳, 되돌리기 가능한 형태로 있다")
chk(APP_SRC.count(NEW_2) == 1, "★★★★★ api_otp_disable() 수정이 정확히 1곳, 되돌리기 가능한 형태로 있다")
chk(APP_SRC.count(NEW_3) == 1, "★★★★★ api_unlock_login() 수정이 정확히 1곳, 되돌리기 가능한 형태로 있다")
chk('pw_key = "PW:" + (label or "")' in NEW_1 and NEW_1.index('pw_key = "PW:"')
    < NEW_1.index('row = one(conn.execute(f"SELECT id, password_hash'),
    "  change-password: 잠금검사가 DB 조회보다 먼저 실행된다")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round414_")
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

    ADM_PW = "R414Adm!2468"
    conn.execute(
        "INSERT INTO admins(username,password_hash,name,role,created_at) VALUES(?,?,?,?,?)",
        ("r414adm", DB.hash_pw(ADM_PW), "R414관리자", "중간관리자", DB.now()))
    conn.commit()

    def _admin_session(uname):
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["admin"] = uname; sess["admin_role"] = "중간관리자"
            sess["pw_role"] = "admin"; sess["_csrf"] = "r414-csrf"
        return c

    def _brute(client, path, wrong_body, n):
        codes = []
        for _ in range(n):
            r = client.post(path, json=wrong_body, headers={"X-CSRF-Token": "r414-csrf"})
            codes.append(r.status_code)
        return codes

    print("\n[3] 실행 — change-password 브루트포스(관리자)")
    c1 = _admin_session("r414adm")
    codes = _brute(c1, "/api/change-password",
                    {"current": "틀린비번", "new": "AnyNewPw!99"}, A.MAX_LOGIN_FAILS + 2)
    chk(429 in codes,
        "★★★★★ 현재비밀번호를 반복 오답해도 결국 429(잠김)가 뜬다"
        "(고치기 전엔 무제한 401만 반복됐다)", codes)
    n_before_lock = codes.index(429) if 429 in codes else len(codes)
    chk(n_before_lock <= A.MAX_LOGIN_FAILS,
        f"  실제 통과되는 시도 횟수가 MAX_LOGIN_FAILS({A.MAX_LOGIN_FAILS})를 안 넘는다",
        n_before_lock)

    print("\n[4] 대조군 — 정상 사용자는 회귀 없이 즉시 성공")
    conn.execute("DELETE FROM login_attempts WHERE username LIKE 'PW:%'")
    conn.commit()
    c2 = _admin_session("r414adm")
    r_ok = c2.post("/api/change-password", json={"current": ADM_PW, "new": "AnyNewPw!99"},
                   headers={"X-CSRF-Token": "r414-csrf"})
    chk(r_ok.status_code == 200, "  올바른 현재 비밀번호는 즉시 200(회귀없음)", r_ok.status_code)

    print("\n[5] 실행 — 협력사 하위계정도 같은 방어 + 수동잠금해제가 실제로 푼다")
    #  ⚠ /api/change-password 는 PW: 계정잠금과 **별개로** app.py:838 의 IP기준
    #    레이트리밋(10회/300초)도 걸려 있다 — 앞 [3][4]에서 이미 이 IP로 8건을
    #    썼으므로 그대로 두면 여기 브루트포스 도중에 "PW:" 잠금이 아니라 그
    #    레이트리밋이 먼저 429 를 뱉어 무엇을 증명했는지 흐려진다. 이 라운드가
    #    고친 대상이 아니므로(기존 코드, 손 안 댐) 카운터만 초기화해 분리한다.
    A._rate_buckets.clear()
    conn.execute("INSERT INTO partners(name, login_id, password_hash, status, partner_type) "
                 "VALUES('R414원청사','r414org', ?, '활성','시공사')", (DB.hash_pw("orgpw123456"),))
    org_pid = conn.execute("SELECT id FROM partners WHERE login_id='r414org'").fetchone()["id"]
    SUB_PW = "R414Sub!1357"
    conn.execute(
        "INSERT INTO portal_users(org_type,org_id,login_id,password_hash,name,role,status,"
        "must_change_pw,created_at) VALUES('partner',?,?,?,?,?,?,0,?)",
        (org_pid, "r414sub", DB.hash_pw(SUB_PW), "R414하위", "하위관리자", "활성", DB.now()))
    sub_id = conn.execute("SELECT id FROM portal_users WHERE login_id='r414sub'").fetchone()["id"]
    conn.commit()

    def _sub_session():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            #  ⚠ 하위계정 로그인 성공 시 partner_login 에는 "자기" 로그인아이디가
            #    들어간다(app.py:2818·2862, _portal_authenticate 가 posted login_id
            #    로 portal_users 를 찾으므로) — 조직 원계정 아이디가 아니다.
            sess["partner_id"] = org_pid; sess["partner_login"] = "r414sub"
            sess["partner_name"] = "R414원청사"; sess["partner_type"] = "시공사"
            sess["portal_sub_id"] = sub_id; sess["pw_role"] = "partner"; sess["_csrf"] = "r414-csrf"
        return c

    c3 = _sub_session()
    codes_sub = _brute(c3, "/api/change-password",
                        {"current": "틀린비번", "new": "AnyNewPw!99"}, A.MAX_LOGIN_FAILS + 2)
    chk(429 in codes_sub,
        "★★★ 하위계정도 자기 로그인아이디 기준으로 잠긴다(조직 원계정 아이디 아님)",
        codes_sub)

    adm_unlock = _admin_session("r414adm")
    r_unlock = adm_unlock.post("/api/login-attempts/unlock", json={"username": "r414sub"},
                                headers={"X-CSRF-Token": "r414-csrf"})
    chk(r_unlock.status_code == 200, "  수동잠금해제 호출 자체는 성공", r_unlock.status_code)
    c4 = _sub_session()
    r_after_unlock = c4.post("/api/change-password", json={"current": SUB_PW, "new": "AnyNewPw!99"},
                              headers={"X-CSRF-Token": "r414-csrf"})
    chk(r_after_unlock.status_code == 200,
        "★★★★★ 잠금해제 뒤 정상 비밀번호로는 실제로 풀려서 200이 뜬다"
        "(수동해제가 PW: 창구를 몰랐다면 여기서도 429 로 막혔을 것)",
        r_after_unlock.status_code)

    print("\n[6] 실행 — 2단계인증 해제(otp/disable) 브루트포스 + 실패기록 남김")
    OTP_ADM_PW = "R414Otp!8642"
    conn.execute(
        "INSERT INTO admins(username,password_hash,name,role,totp_secret,totp_enabled,created_at) "
        "VALUES(?,?,?,?,?,1,?)",
        ("r414otp", DB.hash_pw(OTP_ADM_PW), "R414OTP관리자", "중간관리자",
         CRYPTO.encrypt("JBSWY3DPEHPK3PXP"), DB.now()))
    conn.commit()

    c5 = _admin_session("r414otp")
    codes_otp = _brute(c5, "/api/me/otp/disable", {"password": "틀린비번"}, A.MAX_LOGIN_FAILS + 2)
    chk(429 in codes_otp,
        "★★★★★ 2단계인증 해제도 반복 오답하면 결국 429(잠김)가 뜬다"
        "(고치기 전엔 무제한 401만 반복됐고 흔적도 안 남았다)", codes_otp)
    n_log = conn.execute(
        "SELECT COUNT(*) c FROM activity_log WHERE action='2단계 인증 해제 실패'"
    ).fetchone()["c"]
    chk(n_log > 0,
        "  실패 시도가 활동로그에 실제로 남는다(고치기 전엔 실패 흔적이 0건)", n_log)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[7] 되돌리기 — 옛 코드로 되돌리면 세 결함이 각각 재현되는가")
# ------------------------------------------------------------


try:
    #  ⚠⚠ [라운드611] 스텝 7-1·7-2는 원래 이 파일이 round591 이전에 스텝 7-3도
    #    썼던 옛 세대(round409~515대) 기법 — reverted 를 실제 on-disk app.py 에
    #    잠깐 써넣고(_run_repro) 하위 프로세스로 재현한 뒤 finally 에서 복원 —
    #    을 썼다. round591 은 스텝 7-3만 이 위험(write→subprocess.run→write 사이
    #    창을 동시 폴러가 관측 가능)에서 옮기고 스텝 7-1·7-2는 '같은 부류 위험은
    #    남아 있음, 별도 판단 필요'로 명시적으로 남겨 뒀다 — 이 라운드가 그 뒤를
    #    잇는다. 같은 형제 기법(exec 로 함수 본문만 네임스페이스 사본에 재구성)을
    #    그대로 적용하되, 스텝 7-1·7-2는 스텝 7-3과 달리 이미 있는 _brute()/
    #    test_client() 로 여러 번 두드려야 하므로 A.app.view_functions 딕셔너리
    #    항목만 잠깐 치환한다(round604~610 이 라우트 함수에 확립한 안전패턴과
    #    동일 발상) — 실제 파일은 전혀 안 쓴다. 증명하려는 인과관계(옛 코드는
    #    잠금 없이 무제한 401만 반복)는 그대로다.
    print("\n  [7-1] change-password 만 되돌리기(실제 파일은 안 건드림)")
    _fn1_start = APP_SRC.index("\ndef api_change_password(")
    _fn1_end = APP_SRC.index("\n\n\n", _fn1_start)
    _cur_fn1_src = APP_SRC[_fn1_start:_fn1_end]
    chk(NEW_1 in _cur_fn1_src, "  [7-1] 준비: NEW_1 조각이 지금 함수 본문 안에 있다")
    _old_fn1_src = (_cur_fn1_src
                    .replace("def api_change_password():", "def _api_change_password_pre414():", 1)
                    .replace(NEW_1, OLD_1))
    chk(_old_fn1_src.count(OLD_1) == 1 and "_api_change_password_pre414" in _old_fn1_src,
        "  [7-1] 준비: 함수 리네임 + 잠금로직 되돌리기가 정확히 적용됐다(실제 파일은 안 건드림)")
    _ns1 = dict(vars(A))
    exec(compile(_old_fn1_src, "<round414_pre414_change_password>", "exec"), _ns1)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_change_password_fn = _ns1["_api_change_password_pre414"]

    #  round591의 스텝 7-3과 같은 이유 — IP 레이트리밋(_rate_buckets, app.py:838
    #  인근)이 앞선 [3]/[6] 섹션의 브루트포스로 이미 일부 차 있으면 이 되돌리기
    #  결과를 오염시킨다.
    A._rate_buckets.clear()
    _orig_view1 = A.app.view_functions["api_change_password"]
    A.app.view_functions["api_change_password"] = old_change_password_fn
    try:
        c7a = _admin_session("r414adm")
        #  ⚠ /api/change-password 자체 레이트리밋(app.py:838)이 10회/300초라, 이
        #    라운드가 손대지 않은 그 리밋과 헷갈리지 않도록 그 밑으로 돈다.
        codes1 = _brute(c7a, "/api/change-password",
                         {"current": "틀린비번", "new": "X!99bbbb"}, A.MAX_LOGIN_FAILS + 4)
    finally:
        A.app.view_functions["api_change_password"] = _orig_view1
    chk(429 not in codes1,
        "★★★★★ 옛 코드(재구성, 실제 파일은 안 건드림)로 되돌리면 change-password "
        "브루트포스가 9번(자체 레이트리밋 10회/300초 밑) 내내 401만 받고 429가 "
        "한 번도 안 뜬다(인과관계 직접증명)", codes1)

    print("\n  [7-2] otp/disable 만 되돌리기(같은 기법, 실제 파일은 안 건드림)")
    _fn2_start = APP_SRC.index("\ndef api_otp_disable(")
    _fn2_end = APP_SRC.index("\n\n\n", _fn2_start)
    _cur_fn2_src = APP_SRC[_fn2_start:_fn2_end]
    chk(NEW_2 in _cur_fn2_src, "  [7-2] 준비: NEW_2 조각이 지금 함수 본문 안에 있다")
    _old_fn2_src = (_cur_fn2_src
                    .replace("def api_otp_disable():", "def _api_otp_disable_pre414():", 1)
                    .replace(NEW_2, OLD_2))
    chk(_old_fn2_src.count(OLD_2) == 1 and "_api_otp_disable_pre414" in _old_fn2_src,
        "  [7-2] 준비: 함수 리네임 + 잠금로직 되돌리기가 정확히 적용됐다(실제 파일은 안 건드림)")
    _ns2 = dict(vars(A))
    exec(compile(_old_fn2_src, "<round414_pre414_otp_disable>", "exec"), _ns2)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    #  실제 라우트는 @require_admin 으로 감싸여 있다 — view_functions 치환도 같은
    #  데코레이터를 다시 입혀야 인증 게이트를 우회하지 않는 정직한 대조가 된다.
    old_otp_disable_fn = A.require_admin(_ns2["_api_otp_disable_pre414"])

    A._rate_buckets.clear()
    _orig_view2 = A.app.view_functions["api_otp_disable"]
    A.app.view_functions["api_otp_disable"] = old_otp_disable_fn
    try:
        c7b = _admin_session("r414otp")
        codes2 = _brute(c7b, "/api/me/otp/disable", {"password": "틀린비번"}, 12)
    finally:
        A.app.view_functions["api_otp_disable"] = _orig_view2
    chk(429 not in codes2,
        "★★★★★ 옛 코드(재구성, 실제 파일은 안 건드림)로 되돌리면 otp/disable 브루트포스도 "
        "12번 내내 401만 받고 429가 한 번도 안 뜬다(인과관계 직접증명)", codes2)

    print("\n  [7-3] api_unlock_login 만 되돌리기(잠금은 최신 코드로 걸고, 해제만 옛 코드)")
    #  ⚠⚠ [라운드591] 이 스텝은 원래 reverted_3 를 실제 on-disk app.py 에 잠깐 써넣고
    #    (_run_repro) 하위 프로세스로 돌린 뒤 되돌리는 방식이었다 — round590이 전체배터리
    #    재실행 도중 이 함수의 keys 가 잠깐 옛 4개짜리(uname·P:·I:·OTP:)로 보이는 것을
    #    실측했다. 원인을 스크래치 재현(더미 파일, 실제 app.py 는 손대지 않음)으로 추적한
    #    결과: 복원 로직 자체는 항상 정확했다(APP_SRC 는 매 실행 새로 읽고, NEW_3 하드코딩
    #    리터럴도 지금 app.py 문구와 바이트 단위로 일치) — 문제는 write(reverted)→
    #    subprocess.run→write(restore) 사이에 실제 파일이 옛 코드 상태로 열려 있는 창
    #    자체였다(재현: 900회+ 폴링 중 대부분에서 되돌린 내용이 그대로 관측됨). 그 창이
    #    열려 있는 동안 이 저장소를 읽는 어떤 창구든(동시 세션·이 세션 자신의 병렬 Read 등)
    #    옛 코드를 보게 된다 — 같은 함수를 다루는 형제 round554([4])가 이미 쓰던, 실제
    #    파일은 전혀 건드리지 않는 기법(exec 로 네임스페이스 사본에 얹어 직접 호출)으로
    #    옮겨 창 자체를 없앤다. 증명하는 인과관계(옛 코드는 200을 주고도 PW: 잠금을
    #    남긴다)는 그대로다 — 7-1·7-2(change-password·otp-disable)는 이 라운드가 관측한
    #    증상과 무관해 손대지 않았다(같은 부류 위험은 남아 있음, 별도 판단 필요).
    #    [라운드611] 그 별도 판단을 마무리 — 7-1·7-2도 바로 위 7-3과 같은 이유로 같은
    #    기법(exec 재구성)으로 옮겼다(단, 여러 번 두드려야 해 A.app.view_functions
    #    딕셔너리 항목 치환 방식을 씀 — round604~610 이 라우트 함수에 확립한 패턴).
    _fn_start = APP_SRC.index("\ndef api_unlock_login(")
    _fn_end = APP_SRC.index("\n\n\n", _fn_start)
    _cur_fn_src = APP_SRC[_fn_start:_fn_end]
    chk(NEW_3 in _cur_fn_src, "  [7-3] 준비: NEW_3 조각이 지금 함수 본문 안에 있다")
    _old_fn_src = (_cur_fn_src
                   .replace("def api_unlock_login():", "def _api_unlock_login_pre414():", 1)
                   .replace(NEW_3, OLD_3))
    chk(_old_fn_src.count(OLD_3) == 1 and "_api_unlock_login_pre414" in _old_fn_src,
        "  [7-3] 준비: 함수 리네임 + keys 되돌리기가 정확히 적용됐다(실제 파일은 안 건드림)")

    conn3 = DB.get_db()
    conn3.execute("INSERT INTO partners(name, login_id, password_hash, status, partner_type) "
                  "VALUES('R414원청사2','r414org2', ?, '활성','시공사')", (DB.hash_pw("orgpw123456"),))
    org_pid2 = conn3.execute("SELECT id FROM partners WHERE login_id='r414org2'").fetchone()["id"]
    conn3.execute(
        "INSERT INTO portal_users(org_type,org_id,login_id,password_hash,name,role,status,"
        "must_change_pw,created_at) VALUES('partner',?,?,?,?,?,?,0,?)",
        (org_pid2, "r414sub2", DB.hash_pw("R414Sub2!1357"), "R414하위2", "하위관리자", "활성", DB.now()))
    conn3.commit()
    conn3.close()

    A._rate_buckets.clear()
    sub_c3 = A.app.test_client()
    with sub_c3.session_transaction() as sess:
        sess["partner_id"] = org_pid2; sess["partner_login"] = "r414sub2"
        sess["partner_name"] = "R414원청사2"; sess["partner_type"] = "시공사"
        sess["pw_role"] = "partner"; sess["_csrf"] = "r414-csrf"
    for _ in range(A.MAX_LOGIN_FAILS + 1):
        sub_c3.post("/api/change-password", json={"current": "틀린비번", "new": "X!99aaaa"},
                    headers={"X-CSRF-Token": "r414-csrf"})

    def _n_pw2_locked():
        c = DB.get_db()
        n = c.execute(
            "SELECT COUNT(*) c FROM login_attempts WHERE username=? AND success=0",
            ("PW:r414sub2",)).fetchone()["c"]
        c.close()
        return n

    n_before3 = _n_pw2_locked()
    chk(n_before3 >= A.MAX_LOGIN_FAILS, "  [7-3] 준비: PW:r414sub2 잠금 확인", n_before3)

    _ns3 = dict(vars(A))
    exec(compile(_old_fn_src, "<round414_pre414_reconstructed>", "exec"), _ns3)
    old_unlock_fn = _ns3["_api_unlock_login_pre414"]
    with A.app.test_request_context("/api/login-attempts/unlock", method="POST",
                                     json={"username": "r414sub2"}):
        from flask import session as _s3
        _s3["admin"] = "r414adm"; _s3["admin_role"] = "중간관리자"; _s3["pw_role"] = "admin"
        _s3["_csrf"] = "r414-csrf"
        resp3 = old_unlock_fn()
    code3 = resp3[1] if isinstance(resp3, tuple) else 200
    n_after3 = _n_pw2_locked()
    chk(code3 == 200 and n_after3 >= A.MAX_LOGIN_FAILS,
        "★★★★★ 옛 수동잠금해제 코드(재구성, 실제 파일은 안 건드림)는 200(성공)을 "
        "돌려주고도 PW: 잠금은 그대로 남긴다(\"지웠다는데 안 지워지는\" 거짓성공 재현, "
        "인과관계 직접증명)", (code3, n_after3))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기 실행", f"{type(e).__name__} {e}")
#  [라운드611] 7-1·7-2까지 exec 재구성으로 옮겨 [7] 전체가 이제 실제 app.py를 전혀
#  안 쓰므로, 그 공유 안전망(디스크 복원 finally)도 함께 걷어냈다 — 더 이상 쓰는 곳이
#  없다(round591이 [7-3]만 옮기며 "[7] 전체의 공유 안전망이라 그대로 둔다"고 남긴
#  자리, 이제 정말로 안 써서 지운다).

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
