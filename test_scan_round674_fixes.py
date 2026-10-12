# -*- coding: utf-8 -*-
"""스캔 674라운드 회귀(직접조사, 하위위임 없음) — billing_guide()(GET /report/billing)가
   관리자·발주처·협력사 세 주체 공용 화면인데, 미인증 방문과 계정사망(퇴출·해지 등) 두
   갈래 모두 무조건 /admin/login 으로 돌려보내던 결함.

   조사 배경 — round673가 남긴 "테스트 파일에서 파일명 언급이 적은 순" 기법을 이어
   templates/billing_guide.html(언급 2건 — round161은 상태코드만·round222는 IP
   화이트리스트만 확인, 화면 자체는 round295가 "클린"으로 결론)을 다시 열었다. 이번엔
   화면(html)이 아니라 그 화면을 감싸는 app.py billing_guide()의 **리다이렉트 목적지**
   를 봤다 — 화면 자체는 실제로 손댈 게 없었다.

   실측 —
     · 이 화면의 실제 진입로는 insurer_portal.html(1637행)·partner_portal.html
       (2123행) 두 곳뿐이다(둘 다 target="_blank" 새 탭 링크) — admin.html 에는
       이 화면 링크가 아예 없다. 즉 실사용자는 사실상 전부 발주처·협력사다.
     · billing_guide()(app.py, 세 주체 공용 — docstring: "발주처·협력사도 볼 수
       있어야 한다")는 그런데도 인증이 없거나(session 전부 비어 있음) 있던 계정이
       죽으면(_account_alive()==False, 예: 협력사 '퇴출'·보험사 '해지') 두 경우
       모두 조건 없이 redirect("/admin/login") 였다. 그 화면은 관리자 아이디·
       비밀번호 입력창이라 발주처·협력사 사용자는 애초에 로그인할 수단이 없다 —
       오래 열어 둔 포털 탭에서 나중에 새 탭 링크를 클릭했는데 그 사이 세션이
       끊겨 있으면(만료·다른 기기 로그아웃 등) 자기 계정으로 못 들어가는 화면에
       갇힌다.
     · round161(test_scan_round161_fixes.py:120~122)이 정확히 "협력사 퇴출 뒤
       같은 세션 재요청" 케이스를 회귀로 이미 남겼지만 **상태코드(302)만**
       확인했다 — 그 테스트를 그대로 다시 읽어도 Location 값을 검사하는 줄이
       없다. round222도 IP 화이트리스트 403만 봤다. 그래서 이 결함은 여러 라운드
       동안 "302면 통과"로 계속 초록불이었다.
     · 형제 insurer_api_guide()(admin+insurer 두 주체 전용 화면)는 처음부터
       옳았다 — 비인증이면 언제나 /insurer/login 하나뿐이라 헷갈릴 목적지가
       없었다(실측: 그 함수 소스에 "/admin/login" 문자열 자체가 없음, 아래 [1]).
       billing_guide() 만 세 주체라 "역할을 모르는 방문"이 실제로 생기는데,
       그 경우조차 구분 없이 관리자용 하나로 뭉뚱그렸던 것이 이번 결함.
     · _account_alive() 는 _dead_account_response() 와 달리 session 을 지우지
       않는다(그 함수만 session.clear() 를 부른다) — 즉 "계정사망" 분기에 들어온
       시점에도 session["partner_id"]/["insurer_id"] 는 여전히 남아 있어 정확한
       역할을 그 자리에서 알 수 있었다(실측: 아래 [2](b)(c)).

   고침 — app.py billing_guide() 두 갈래를 각각 고친다: (a) 세션이 전혀 없는
   분기는 역할을 알 방법이 없으므로 세 포털 링크를 모두 가진 랜딩(/)으로 보낸다.
   (b) 계정사망 분기는 세션에 남은 값으로 역할을 그대로 안다 — partner_id 면
   /partner/login, insurer_id 면 /insurer/login, 그 외(admin)는 원래대로
   /admin/login. partner_portal()·insurer_portal() 이 미인증일 때 이미 쓰는 것과
   같은 두 목적지를 그대로 재사용했다(새 화면·새 상수 없음). 서버 검증 로직
   (_account_alive·_admin_ip_denied·compute_fee·split_vat)은 전부 무변경 — 바뀐
   것은 리다이렉트 문자열뿐이다. 템플릿 무변경(billing_guide.html 자체는 손대지
   않음) — build_pages.py·test_template_js.py 재실행 대상 아님(app.py만 수정).

   회귀테스트(이 파일) —
   [1] 소스 — billing_guide() 함수 경계 안에서 무조건적 redirect("/admin/login")가
       (admin 전용 최종 폴백 한 곳만 남고) 사라졌는지, 두 분기에 랜딩·역할별
       목적지가 실제로 있는지, 세 리다이렉트가 partner→insurer→admin 순서로
       나타나는지 확인. 형제 insurer_api_guide()는 무변경(회귀 없음)인지도 확인.
   [2] 단위+종단 — 스크래치 DB에 협력사·보험사·관리자 세 계정을 만들어 실제 로그인
       (POST /api/{partner,insurer}/login, /api/login) 후, 각 status를 죽은 값으로
       바꿔 **같은 세션**으로 GET /report/billing 재요청 — Location이 각자 자기
       역할의 로그인 화면인지 실측(admin은 계정 행 자체를 지워 재현). 완전
       비로그인(쿠키 없는 새 클라이언트)의 GET도 Location이 "/"(랜딩)인지 확인.
       활성 상태에서는 그대로 200(과잉차단 아님)도 함께 확인. 이 화면은 순수
       리다이렉트 판정이라 별도 API 계층이 없으므로, 실제 Flask 라우트 왕복인
       이 단계가 곧 종단 검증이기도 하다.
   [3] (위 [2]에 통합 — 이 화면에는 [2]와 구분되는 별도의 '단위 vs 종단' 계층이
       없다: 판정 로직 자체가 라우트 함수 안의 조건문 몇 줄이라, 실제 HTTP 왕복
       없이는 의미 있게 단위 분리할 대상이 없다.)
   [4] 되돌리기-증명 — Flask의 app.view_functions["billing_guide"]를, 고치기 전
       두 분기(둘 다 무조건 /admin/login)만 재현하고 나머지는 지금(고친) 실제
       함수에 위임하는 함수로 **일시 교체**해 같은 세 시나리오를 재요청하면
       퇴출된 협력사·해지된 보험사·비로그인 방문자 모두 /admin/login으로 떨어짐을
       재현하고, finally에서 원래 함수로 되돌린 뒤 복원을 재확인한다. 실제 파일은
       전혀 건드리지 않는다.

       python test_scan_round674_fixes.py
"""
import io
import os
import re
import sys
import tempfile
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def func_src(src, header):
    """round253이 확립한 함수경계 슬라이스 — header부터 다음 '@app.'나
    최상위 'def ' 직전까지(app.py 라우트/헬퍼 함수용)."""
    i = src.find(header)
    if i < 0:
        return ""
    m = re.search(r"\n(?:@app\.|def )", src[i + len(header):])
    return src[i:i + len(header) + m.start()] if m else src[i:]


def loc_path(resp):
    return urlsplit(resp.headers.get("Location", "")).path


print("=" * 72)
print("  스캔 674라운드 회귀 — billing_guide() 미인증/계정사망 리다이렉트가 항상 /admin/login")
print("=" * 72)

APP_SRC = read("app.py")

# ============================================================
print("\n[1] 소스 확인 — billing_guide() 두 분기의 목적지 + 형제 insurer_api_guide() 무변경")
# ------------------------------------------------------------
FN = func_src(APP_SRC, "def billing_guide():")
chk(FN != "", "  billing_guide() 함수를 실제로 찾았다")

chk('return redirect("/")' in FN,
    "★★★★★ 세션이 전혀 없는 분기가 이제 랜딩(/)으로 보낸다(고치기 전엔 /admin/login)")
chk('return redirect("/partner/login")' in FN,
    "★★★★★ 계정사망 분기에 협력사 전용 목적지(/partner/login)가 생겼다")
chk('return redirect("/insurer/login")' in FN,
    "★★★★★ 계정사망 분기에 보험사 전용 목적지(/insurer/login)가 생겼다")
chk(FN.count('redirect("/admin/login")') == 1,
    "★★★★ 함수 안의 무조건적 /admin/login 은 이제 admin 자신을 위한 최종 폴백 "
    "한 곳뿐이다(고치기 전엔 두 분기 모두 이 문자열이라 2곳)",
    FN.count('redirect("/admin/login")'))

_i_partner = FN.find('redirect("/partner/login")')
_i_insurer = FN.find('redirect("/insurer/login")')
_i_admin = FN.rfind('redirect("/admin/login")')
chk(0 < _i_partner < _i_insurer < _i_admin,
    "  세 리다이렉트가 partner → insurer → admin(최종 폴백) 순서로 나타난다",
    (_i_partner, _i_insurer, _i_admin))

API_GUIDE_FN = func_src(APP_SRC, "def insurer_api_guide():")
chk(API_GUIDE_FN != "", "  (전제) 형제 insurer_api_guide() 함수를 실제로 찾았다")
chk('redirect("/admin/login")' not in API_GUIDE_FN,
    "  (회귀 없음) 형제 insurer_api_guide()는 원래부터 /admin/login을 쓰지 않는다 — 무변경")
chk('redirect("/insurer/login")' in API_GUIDE_FN,
    "  (회귀 없음) 형제는 원래부터 자기 역할(insurer) 로그인으로 보낸다 — 무변경 확인")

# ============================================================
print("\n[2] 단위+종단 — 스크래치 DB + 실제 Flask 라우트 왕복 (별도 API 계층이 없어 [3] 통합)")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round674_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "app.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB  # noqa: E402
DB.init_db()
import app as A  # noqa: E402

PW0 = "Init9900!!"
conn = DB.get_db()
conn.execute(
    "INSERT INTO partners(name, partner_type, status, category, region, login_id, "
    "password_hash, must_change_pw) VALUES('R674업체','시공사','활성','가드레일','서울', ?, ?, 0)",
    ("r674partner", DB.hash_pw(PW0)))
conn.execute(
    "INSERT INTO insurers(name, login_id, password_hash, status) "
    "VALUES('R674보험사','r674insurer', ?, '활성')", (DB.hash_pw(PW0),))
conn.execute(
    "INSERT INTO admins(username, password_hash, name, role) "
    "VALUES('r674admin', ?, 'R674관리자','최고관리자')", (DB.hash_pw(PW0),))
conn.commit()
conn.close()

# -- (a) 완전 비로그인 방문자(쿠키조차 없는 새 클라이언트) --
anon_c = A.app.test_client()
r_anon = anon_c.get("/report/billing", follow_redirects=False)
chk(r_anon.status_code == 302, "  (준비) 비로그인 GET /report/billing — 302", r_anon.status_code)
chk(loc_path(r_anon) == "/",
    "★★★★★★ 비로그인 방문자는 이제 랜딩(/)으로 간다(고치기 전엔 /admin/login)",
    r_anon.headers.get("Location"))

# -- (b) 협력사: 로그인 → 정상 200 → '퇴출' → 같은 세션 재요청 --
partner_c = A.app.test_client()
r = partner_c.post("/api/partner/login", json={"login_id": "r674partner", "password": PW0})
chk(r.status_code == 200, "  (준비) 협력사 실제 로그인 — 200", r.status_code)
r_p_ok = partner_c.get("/report/billing", follow_redirects=False)
chk(r_p_ok.status_code == 200,
    "  활성 협력사는 /report/billing 을 그대로 200으로 본다(과잉차단 아님)", r_p_ok.status_code)
conn = DB.get_db()
conn.execute("UPDATE partners SET status='퇴출' WHERE login_id='r674partner'")
conn.commit(); conn.close()
r_p_dead = partner_c.get("/report/billing", follow_redirects=False)
chk(r_p_dead.status_code == 302, "  퇴출 뒤 같은 세션 재요청 — 302", r_p_dead.status_code)
chk(loc_path(r_p_dead) == "/partner/login",
    "★★★★★★ 퇴출된 협력사는 이제 자기 로그인 화면(/partner/login)으로 간다"
    "(고치기 전엔 /admin/login — 협력사는 그 화면에 쓸 아이디가 없다)",
    r_p_dead.headers.get("Location"))

# -- (c) 보험사: 로그인 → 정상 200 → '해지' → 같은 세션 재요청 --
insurer_c = A.app.test_client()
r = insurer_c.post("/api/insurer/login", json={"login_id": "r674insurer", "password": PW0})
chk(r.status_code == 200, "  (준비) 보험사 실제 로그인 — 200", r.status_code)
r_i_ok = insurer_c.get("/report/billing", follow_redirects=False)
chk(r_i_ok.status_code == 200,
    "  활성 보험사는 /report/billing 을 그대로 200으로 본다(과잉차단 아님)", r_i_ok.status_code)
conn = DB.get_db()
conn.execute("UPDATE insurers SET status='해지' WHERE login_id='r674insurer'")
conn.commit(); conn.close()
r_i_dead = insurer_c.get("/report/billing", follow_redirects=False)
chk(r_i_dead.status_code == 302, "  해지 뒤 같은 세션 재요청 — 302", r_i_dead.status_code)
chk(loc_path(r_i_dead) == "/insurer/login",
    "★★★★★★ 해지된 보험사는 이제 자기 로그인 화면(/insurer/login)으로 간다"
    "(고치기 전엔 /admin/login)", r_i_dead.headers.get("Location"))

# -- (d) 관리자: 로그인 → 정상 200 → 계정 행 삭제 → 같은 세션 재요청(admin은 그대로가 정답) --
admin_c = A.app.test_client()
r = admin_c.post("/api/login", json={"username": "r674admin", "password": PW0})
chk(r.status_code == 200, "  (준비) 관리자 실제 로그인 — 200", r.status_code)
r_a_ok = admin_c.get("/report/billing", follow_redirects=False)
chk(r_a_ok.status_code == 200,
    "  활성 관리자는 /report/billing 을 그대로 200으로 본다(과잉차단 아님)", r_a_ok.status_code)
conn = DB.get_db()
conn.execute("DELETE FROM admins WHERE username='r674admin'")
conn.commit(); conn.close()
r_a_dead = admin_c.get("/report/billing", follow_redirects=False)
chk(r_a_dead.status_code == 302, "  계정삭제 뒤 같은 세션 재요청 — 302", r_a_dead.status_code)
chk(loc_path(r_a_dead) == "/admin/login",
    "  관리자는 원래부터 옳았던 목적지(/admin/login) 그대로다(회귀 없음)",
    r_a_dead.headers.get("Location"))

# ============================================================
print("\n[4] 되돌리기-증명 — view_functions 일시 교체로 옛(두 분기 모두 /admin/login) 동작 재현")
#      ⚠ 실제 파일은 전혀 건드리지 않는다 — Flask 라우팅 테이블의 함수 객체만
#        테스트 프로세스 메모리 안에서 잠깐 바꿨다가 finally 에서 되돌린다.
# ------------------------------------------------------------
_ORIGINAL_FN = A.app.view_functions["billing_guide"]


def _old_billing_guide():
    """고치기 전 재현 — 두 분기 모두 무조건 /admin/login. 그 외 로직(정상 경로)은
    전부 지금(고친) 실제 함수에 그대로 위임한다 — 이번 수정이 건드린 두 줄만 되돌린다."""
    if not (A.session.get("admin") or A.session.get("insurer_id") or A.session.get("partner_id")):
        return A.redirect("/admin/login")
    alive, _msg = A._account_alive()
    if not alive:
        return A.redirect("/admin/login")
    return _ORIGINAL_FN()


try:
    A.app.view_functions["billing_guide"] = _old_billing_guide

    r_anon_old = anon_c.get("/report/billing", follow_redirects=False)
    chk(loc_path(r_anon_old) == "/admin/login",
        "★★★★★★ (인과관계 실측) 옛 버전이라면 비로그인 방문자도 /admin/login 으로 갔다",
        r_anon_old.headers.get("Location"))

    #  협력사·보험사는 이미 위에서 죽은 상태 그대로(같은 세션) 재요청
    r_p_old = partner_c.get("/report/billing", follow_redirects=False)
    chk(loc_path(r_p_old) == "/admin/login",
        "★★★★★★ (인과관계 실측) 옛 버전이라면 퇴출된 협력사도 /admin/login 으로 갔다"
        "(자기 아이디가 없는 화면인데도)", r_p_old.headers.get("Location"))

    r_i_old = insurer_c.get("/report/billing", follow_redirects=False)
    chk(loc_path(r_i_old) == "/admin/login",
        "★★★★★★ (인과관계 실측) 옛 버전이라면 해지된 보험사도 /admin/login 으로 갔다",
        r_i_old.headers.get("Location"))
finally:
    A.app.view_functions["billing_guide"] = _ORIGINAL_FN

#  복원 확인 — 지금(고친) 동작이 실제로 돌아왔는지 마지막으로 재확인
r_p_restored = partner_c.get("/report/billing", follow_redirects=False)
chk(loc_path(r_p_restored) == "/partner/login",
    "  (복원 확인) view_functions를 되돌린 뒤 협력사는 다시 /partner/login 을 받는다"
    "(finally가 실제로 원래 함수를 되돌렸다)", r_p_restored.headers.get("Location"))

#  실제 파일이 여전히 고친 상태 그대로인지 마지막으로 재확인(sanity).
chk('return redirect("/")' in func_src(read("app.py"), "def billing_guide():"),
    "  (sanity) 실제 app.py 파일(디스크)은 여전히 고친 상태 그대로다(위 [4]는 메모리 함수만 다뤘다)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
