# -*- coding: utf-8 -*-
"""스캔 285라운드 회귀 — smoke_test.py 가 go-live 이후 데모 계정 소실을
   "그 검사만 건너뜀"으로 오판, 핵심 회귀검사 대부분이 빠진 채 exit 0(전부
   통과)을 내던 결함(smoke_test.py 사상 첫 정밀조사, 정밀조사 Agent가 발견 후
   독립 재검증).

  [심각] admin/partner/insurer/insurer2 로그인 계정명이 smoke_test.py 에
      하드코딩돼 있는데, manage.py go-live(모든 실운영 배포의 필수·문서화된
      단계 — DEPLOY.md 자신이 "다음 단계 go-live 가 그 이름을 지운다"고 미리
      경고한다)가 admins.admin/staff 를 DELETE, partners/insurers.login_id=
      'partner'|'insurer'|'insurer2' 를 NULL 로 만든다. 그 순간부터 이 세
      로그인은 어떤 비밀번호를 넣어도 영원히 실패하는데, test_csrf·
      test_bidding·test_blockers·test_photos 는 전부 그 결과를 물려받는
      `if not m`/`if not (m and p and i)` 게이트가 있어 CSRF·입찰·
      이중지급방지·IDOR·정산·사진권한 등 ~90개 검사 중 ~53개가 통째로
      건너뛰어진다 — bootstrap.sh 자신의 주석은 "그 검사만 건너뛰고 나머지는
      계속 돈다"고 믿고 있었는데 실측은 그렇지 않다. FAIL 이 0건이라 exit
      0(전부 통과)이 그대로 나가 이 사실이 숨겨졌다.
      로그인 실패가 '데모 계정 소실' 때문인지 별도로 기록(DEMO_LOGIN_GONE)해
      요약에 굵게 경고하고, 새 종료코드 4(검사는 돌았지만 핵심 회귀검사
      대부분을 건너뜀)로 exit 0 과 구분한다 — 무엇을 검사했는지는 안 바꾸고
      정직하게 보고만 하도록 수정.

  ⚠ 이 테스트는 smoke_test.py 의 Client.req() 를 몽키패치해 가짜 응답만
    쓴다 — 실제 네트워크·운영 서버는 전혀 건드리지 않는다. 이 라운드가 손댄
    test_auth_isolation()·test_admin()·main() 은 실제 함수 그대로 실행하고,
    이번에 안 건드린 나머지 9개 검사함수(test_public 등)만 무해한 스텁으로
    바꿔 넣어 가짜서버 전체를 새로 만드는 부담 없이 종단간(main()) 검증한다.

      python test_scan_round285_fixes.py
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


ST_SRC = read("smoke_test.py")
BOOT_SRC = read(os.path.join("deploy", "bootstrap.sh"))
DEPLOY_SRC = read(os.path.join("deploy", "DEPLOY.md"))

print("=" * 72)
print("  스캔 285라운드 회귀 — smoke_test.py 데모계정소실 오판(거짓 초록)")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
#  ⚠⚠ [라운드303] round303 이 넷째 자리(test_photos() 의 insurer2 IDOR 검사)를
#    이 라운드가 세운 것과 똑같은 패턴(skip()+DEMO_LOGIN_GONE.append())으로
#    추가해 이 개수가 3→4로 늘었다 — round285 의 원래 취지("데모 로그인
#    실패는 전부 기록돼야 한다")를 정확히 지킨 확장이라 3에 고정하지 않고
#    "적어도 3(이 라운드가 다룬 협력사·보험사·관리자)"으로 완화한다.
chk("DEMO_LOGIN_GONE" in ST_SRC and ST_SRC.count("DEMO_LOGIN_GONE.append(") >= 3,
    "★★★★★ 관리자·협력사·보험사 로그인 실패 3곳 모두 '데모계정 소실'로 기록된다")
chk("if DEMO_LOGIN_GONE:\n        return 4" in ST_SRC,
    "★★★★★ 데모계정 소실로 핵심검사가 빠지면 exit 0 이 아니라 별도 종료코드(4)를 낸다")
chk('$SMOKE_RC" -eq 4' in BOOT_SRC,
    "★★★★ bootstrap.sh 가 새 종료코드 4를 인식해 경고한다")
chk("go-live 는 admins" in BOOT_SRC and "**틀렸다**" in BOOT_SRC,
    "STEP bootstrap.sh의 잘못된 옛 주석('그 검사만 건너뛰고 나머지는 계속 돈다')이 정정됐다")
chk(DEPLOY_SRC.count('export BOKGUON_TEST_ADMIN_PW="bokguon2026"') >= 3,
    "★★★★ DEPLOY.md 의 smoke_test.py 호출 3곳(원래 비밀번호가 전혀 안 실려 있던 곳) "
    "전부 비밀번호 환경변수를 실어 보낸다(고치기 전엔 매번 검사 0건·exit 2)",
    DEPLOY_SRC.count('export BOKGUON_TEST_ADMIN_PW="bokguon2026"'))

# ============================================================
print("\n[2] 실행 준비 — Client.req() 몽치패치, 관련 없는 9개 함수는 무해한 스텁")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
os.environ["BOKGUON_TEST_ADMIN_PW"] = "x"
os.environ["BOKGUON_TEST_INSURER_PW"] = "x"
os.environ["BOKGUON_TEST_PARTNER_PW"] = "x"
import smoke_test as ST                                              # noqa: E402

_orig_req = ST.Client.req


def _fake_req_all_logins_fail(self, method, path, body=None):
    """비로그인 접근 차단 검사는 그대로 만족시키고(401/302), 로그인 POST 3곳만
    전부 401 실패로 응답 — test_auth_isolation()/test_admin() 자신의 기존
    검사(이번 라운드가 안 건드린 부분)까지 덩달아 깨지지 않게 한다."""
    if method == "GET" and path in ("/api/dashboard", "/api/partner/dashboard", "/api/insurer/dashboard"):
        return 401, "{}", ST.CIHeaders({})
    if method == "GET" and path == "/admin":
        return 302, "", ST.CIHeaders({"Location": "/login"})
    if method == "POST" and path in ("/api/login", "/api/partner/login", "/api/insurer/login"):
        return 401, '{"ok": false}', ST.CIHeaders({})
    return 200, "", ST.CIHeaders({})


def _noop(*a, **kw):
    return None


# ============================================================
print("\n[3] 실행 — 데모 로그인 3곳이 전부 실패하면 DEMO_LOGIN_GONE 이 정확히 기록되는가")
# ------------------------------------------------------------
try:
    ST.Client.req = _fake_req_all_logins_fail
    ST.DEMO_LOGIN_GONE.clear()
    ST.PASS.clear()
    ST.FAIL.clear()
    ST.SKIP.clear()
    ST.SECURE_COOKIE_BLOCK = False

    p, i = ST.test_auth_isolation()
    m = ST.test_admin()

    chk(p is None and i is None and m is None,
        "STEP 세 로그인 모두 실패 시 p/i/m 이 전부 None 이다(회귀 없음)")
    #  ⚠ test_auth_isolation() 은 협력사 로그인이 실패하면 그 자리에서 바로
    #    return 하므로(283-286행, 이번 라운드가 안 건드린 기존 구조) 보험사
    #    로그인은 시도조차 안 된다 — 이 시나리오에서는 '협력사'만 기록되는 게
    #    맞다(다운스트림 영향은 i=None 으로 이미 동일하게 반영됨).
    chk(sorted(ST.DEMO_LOGIN_GONE) == sorted(["협력사", "관리자"]),
        "★★★★★★ 로그인 실패가 '데모계정 소실'로 정확히 기록된다"
        "(고치기 전엔 이 기록 자체가 없어 exit 0 과 구분할 방법이 없었다)",
        ST.DEMO_LOGIN_GONE)
finally:
    ST.Client.req = _orig_req

# ============================================================
print("\n[4] 실행 — 종단간(main()): 데모계정 소실 시 exit 0 이 아니라 4를 내는가")
# ------------------------------------------------------------
_orig_funcs = {}
_STUBBED = ("test_public", "test_csrf", "test_consent", "test_bidding", "test_blockers",
            "test_rate_limit", "test_frontend", "test_photos", "test_bruteforce")
try:
    for fn in _STUBBED:
        _orig_funcs[fn] = getattr(ST, fn)
        setattr(ST, fn, _noop)
    ST.Client.req = _fake_req_all_logins_fail
    ST.DEMO_LOGIN_GONE.clear()
    ST.PASS.clear()
    ST.FAIL.clear()
    ST.SKIP.clear()
    ST.SECURE_COOKIE_BLOCK = False
    _orig_argv = sys.argv
    sys.argv = ["smoke_test.py"]

    import contextlib
    _out = io.StringIO()
    with contextlib.redirect_stdout(_out):
        rc = ST.main()

    chk(not ST.FAIL, "STEP 관련 없는 9개 함수를 무해한 스텁으로 바꿨으니 진짜 실패는 0건이어야 한다",
        ST.FAIL)
    chk(rc == 4,
        "★★★★★★ 데모계정 3곳이 전부 없으면 main() 이 exit 0(전부통과)이 아니라 "
        "종료코드 4를 낸다(고치기 전엔 FAIL=0 이면 무조건 0 — 이 상황과 진짜 "
        "전부통과를 구분할 방법이 없었다)", rc)
    chk(all(w in _out.getvalue() for w in ("협력사", "관리자")),
        "★★★★ 요약 화면에 어느 계정이 없어서 무엇을 못 검증했는지 굵게 경고한다"
        "(고치기 전엔 스크롤 위쪽 skip 문구 하나에만 조용히 남았다)",
        _out.getvalue()[-400:])
finally:
    for fn, orig in _orig_funcs.items():
        setattr(ST, fn, orig)
    ST.Client.req = _orig_req
    sys.argv = _orig_argv

# ============================================================
print("\n[5] 실행 — 회귀 없음: 로그인이 전부 성공하면 DEMO_LOGIN_GONE 이 비어 있는가")
# ------------------------------------------------------------
def _fake_req_all_logins_ok(self, method, path, body=None):
    if method == "GET" and path in ("/api/dashboard", "/api/partner/dashboard",
                                     "/api/insurer/dashboard", "/api/traffic",
                                     "/api/partners", "/api/cases", "/api/settlements",
                                     "/api/defects", "/api/leads", "/api/applications"):
        return 401, '{}', ST.CIHeaders({})    # 교차접근 차단 검사가 기대하는 값(401/403)
    if method == "GET" and path == "/admin":
        return 302, "", ST.CIHeaders({"Location": "/login"})
    if method == "POST" and path == "/api/login":
        return 200, '{"ok": true, "csrf": "t", "name": "관리자", "role": "최고관리자"}', ST.CIHeaders({})
    if method == "POST" and path == "/api/partner/login":
        return 200, '{"ok": true}', ST.CIHeaders({})
    if method == "POST" and path == "/api/insurer/login":
        return 200, '{"ok": true}', ST.CIHeaders({})
    return 200, "", ST.CIHeaders({})


_orig_has_cookie = ST.Client.has_session_cookie
try:
    ST.Client.req = _fake_req_all_logins_ok
    #  이 몽키패치는 req() 자체를 대체해 실제 소켓·쿠키jar 처리(self.opener.open)를
    #  안 거친다 — has_session_cookie() 는 그 쿠키jar 를 보므로 항상 False 가
    #  되어 SECURE_COOKIE_BLOCK 오탐이 난다. 이 라운드가 손대지 않은 그 분기를
    #  테스트에서만 피해 가려고 True 로 고정한다(실제 서버 대상 실행에서는
    #  원래 로직 그대로 동작 — 이 patch 는 이 테스트 프로세스 안에서만 유효).
    ST.Client.has_session_cookie = lambda self: True
    ST.DEMO_LOGIN_GONE.clear()
    ST.SECURE_COOKIE_BLOCK = False
    p, i = ST.test_auth_isolation()
    chk(p is not None and i is not None and not ST.DEMO_LOGIN_GONE,
        "★★★★ 데모계정이 살아있으면(정상 상황) DEMO_LOGIN_GONE 이 비어 있다(과잉경보 아님)",
        (p is not None, i is not None, ST.DEMO_LOGIN_GONE))
finally:
    ST.Client.req = _orig_req
    ST.Client.has_session_cookie = _orig_has_cookie

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
