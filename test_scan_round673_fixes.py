# -*- coding: utf-8 -*-
"""스캔 673라운드 회귀(직접조사, 하위위임 없음) — 비밀번호 변경 화면의 실시간
   규칙 체크리스트가 서버 정책의 네 규칙 중 하나를 통째로 빠뜨리고 있던 결함.

   조사 배경 — 이 세션 사상 한 번도 정밀조사되지 않은 파일을 찾다가(round295가
   "미조사 템플릿 7종"을 훑을 때도 change_password.html은 딱 한 건, 죽은 계정의
   _account_alive() 누락만 고쳤을 뿐 이 체크리스트 자체는 손대지 않았다) 발견.

   실측 —
     · app.py password_policy_error(pw, ident)(1393행)는 규칙을 네 개 강제한다:
        ① 영문·숫자·특수문자 중 2종 이상
        ② 2종이면 10자리·3종이면 8자리 이상
        ③ **로그인 아이디를 비밀번호에 포함할 수 없음**(ident.lower() in pw.lower())
        ④ 같은 문자 4회 이상 연속 금지
       이 함수는 /api/change-password(1489행)에서 실제 로그인 아이디(label)를
       ident로 넘겨 **모든 비밀번호 변경에 실제로 강제**된다(임시 비밀번호
       강제변경·자발적 변경 모두 이 라우트 하나를 공유).
     · templates/change_password.html의 실시간 체크리스트(checkRule())는 딱
       세 개(①②④)만 보여주고 ③이 아예 없었다 — 화면 요소 자체가 없어 사용자는
       "규칙 3/3 초록불"을 보고 제출해도, 새 비밀번호에 자기 로그인 아이디가
       들어 있으면(회사명 축약형을 아이디로 쓰는 실사용자가 비밀번호에도 같은
       조각을 넣는 것은 흔한 습관이다) 그제서야 서버가 "아이디를 비밀번호에
       포함할 수 없습니다"로 거부한다 — 화면이 "다 됐다"고 말한 뒤 실제
       제출에서만 뒤통수를 치는 구조였다(round670~672와 같은 "한쪽엔 있는 규칙이
       짝에는 없다" 계열 결함이지만, 이번 짝은 색상 매핑이 아니라 **서버 검증
       규칙 대 화면 실시간 체크리스트**라는 새 쌍이다).
     · 강제변경 화면(forced=True, 임시 비밀번호 첫 로그인)에서 특히 더 아프다
       — 이 경로가 아니면 다른 화면을 아예 못 쓴다.

   고침 — (a) app.py change_password_page()(1427행)가 세션의 실제 로그인
   아이디(admins.username/partners.login_id/insurers.login_id — 원계정·하위
   계정 모두 password_policy_error 호출부와 동일한 session 키 조합:
   session["admin"] or session["partner_login"] or session["insurer_login"])를
   login_id로 템플릿에 함께 내려준다. (b) change_password.html이 그 값을
   const MY_ID로 받아, checkRule()에 서버와 같은 대소문자 무시 부분일치 검사를
   더해 네 번째 규칙 칸(#r_id "아이디 포함 금지")을 실시간으로 보여준다.
   단일 지점(change_password_page() + change_password.html) 수정 — 서버
   검증 규칙(password_policy_error) 자체는 무변경. templates 변경이라
   build_pages.py 재실행 + test_scan_round306_fixes.py(11/11)·
   test_template_js.py(9/9) 표준 재검증 완료.

   회귀테스트(이 파일, node 필요) —
   [1] 소스 — change_password_page()가 login_id를 실제로 내려주는지, 서버
       정책 함수(password_policy_error)의 ③ 규칙이 그대로인지(무변경 확인),
       템플릿에 #r_id·MY_ID·checkRule() 안의 set('r_id',...) 가 실제로
       있는지를 파일에서 직접 정규식으로 확인한다.
   [2] 단위 — 실제 Flask 라우트(GET /change-password, 로그인 세션 포함)가
       내려주는 **진짜 렌더 결과**에서 JS 블록을 그대로 잘라내(손으로 다시
       타이핑하지 않음) Node.js로 실행, 비밀번호 조합별 r_id 판정을 같은
       모듈에서 직접 호출한 password_policy_error()의 판정과 대조한다.
   [3] 종단 — (a) 협력사·보험사·관리자 세 역할 각각 실제 로그인 후
       GET /change-password로 화면에 박히는 아이디가 세 역할 모두 올바른지
       확인(단일 or-체인이 세 역할 전부를 커버하는가). (b) 협력사로 실제
       POST /api/change-password — 규칙 ①②④를 만족하지만 자기 아이디를 포함한
       새 비밀번호는 실제로 400 거부(에러문구에 "아이디"), 같은 조건에서 아이디만
       뺀 비밀번호는 실제로 200 성공함을 실측.
   [4] 되돌리기-증명 — [2]에서 잘라낸 (지금 고친) JS 블록에서 MY_ID 선언과
       set('r_id',...) 호출만 제거한 옛 버전을 독립 Node 스크립트로 만들어(실제
       파일은 전혀 건드리지 않음), 그 옛 버전은 "규칙①②④를 만족하지만 아이디를
       포함한" 바로 그 비밀번호에 대해 r_id 칸 자체가 존재하지 않았음(=화면이
       3/3 초록불을 보여줬을 것)을 재현하고, 그 사이에도 서버는 (당시부터 계속)
       거부했을 것임을 같은 케이스로 대조한다.

       python test_scan_round673_fixes.py
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

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


print("=" * 72)
print("  스캔 673라운드 회귀 — 비밀번호 변경 체크리스트에 '아이디 포함 금지' 규칙 누락")
print("=" * 72)

APP_SRC = read("app.py")
TPL_SRC = read("templates/change_password.html")

# ============================================================
print("\n[1] 소스 확인 — app.py가 login_id를 내려주는가 + 템플릿에 4번째 규칙칸이 있는가")
# ------------------------------------------------------------
PAGE_FN = func_src(APP_SRC, "def change_password_page():")
chk(PAGE_FN != "", "  change_password_page() 함수를 실제로 찾았다")
chk('login_id=(session.get("admin") or session.get("partner_login")' in PAGE_FN
    and 'or session.get("insurer_login") or "")' in PAGE_FN,
    "★★★★★ change_password_page()가 login_id를 password_policy_error 호출부와 "
    "같은 session 키 조합으로 템플릿에 내려준다", PAGE_FN[:400])

POLICY_FN = func_src(APP_SRC, "def password_policy_error(pw, ident=\"\"):")
chk(POLICY_FN != "", "  (전제) password_policy_error() 함수를 실제로 찾았다")
chk("ident.lower() in pw.lower()" in POLICY_FN,
    "  (무변경 확인) 서버의 ③ 규칙(아이디 포함 금지)은 그대로다 — "
    "이번 수정은 화면에 이 규칙을 보여주는 것이지 서버 규칙을 바꾼 게 아니다")

chk('id="r_id"' in TPL_SRC, "★★★★ change_password.html에 4번째 규칙칸(#r_id)이 실제로 있다")
chk("const MY_ID" in TPL_SRC, "  change_password.html에 MY_ID 상수 선언이 있다")
chk(re.search(r"set\('r_id',\s*p\.length\s*>\s*0", TPL_SRC) is not None,
    "★★★★ checkRule() 안에서 실제로 set('r_id', ...)를 호출한다")
chk("{{ login_id | default('') | tojson }}" in TPL_SRC,
    "  MY_ID가 서버가 내려준 login_id를 tojson으로 안전하게 받는다(수동 이스케이프 아님) — "
    "default('')는 이 변수를 안 주는 호출(예: test_template_js.py의 범용 렌더 검사)에서도 "
    "Undefined가 그대로 tojson에 들어가 TypeError로 죽지 않게 한다(아래 [3](c)가 이 자리를 직접 재현)")

# ============================================================
print("\n[2]+[3] 단위·종단 — 실제 Flask 라우트로 세 역할 로그인 + 렌더 + Node 실행 + 실제 제출")
# ------------------------------------------------------------
NODE = shutil.which("node")
if not NODE:
    chk(False, "node 실행파일을 찾을 수 없다 — 이 구간은 건너뛰지 않고 실패로 답한다")
    NODE = None

_tmpdir = tempfile.mkdtemp(prefix="round673_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "app.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB  # noqa: E402
DB.init_db()
import app as A  # noqa: E402

PW0 = "Init9900!!"          # 초기 비밀번호(정책 만족, 아이디 미포함)
LOGIN_ID = "r673partner"    # 짧은 편이라 우연 매치 가능성을 줄이려 접두어를 특이하게 잡음

conn = DB.get_db()
conn.execute(
    "INSERT INTO partners(name, partner_type, status, category, region, login_id, "
    "password_hash, must_change_pw) VALUES('R673업체','시공사','활성','가드레일','서울', ?, ?, 0)",
    (LOGIN_ID, DB.hash_pw(PW0)))
iid = conn.execute(
    "INSERT INTO insurers(name, login_id, password_hash, status) "
    "VALUES('R673보험사','r673insurer', ?, '활성')", (DB.hash_pw(PW0),)).lastrowid
conn.execute(
    "INSERT INTO admins(username, password_hash, name, role) "
    "VALUES('r673admin', ?, 'R673관리자','최고관리자')", (DB.hash_pw(PW0),))
conn.commit()
conn.close()


def extract_js_block(html):
    i = html.index("function kinds(p){")
    j = html.index("\nlet CSRF", i)
    return html[i:j]


def my_id_from(html):
    m = re.search(r"const MY_ID = \((.*?)\)\.toLowerCase\(\);", html)
    return json.loads(m.group(1).split("||")[0].strip()) if m else None


# -- [3](a) 세 역할 각각 실제 로그인 → 실제 GET /change-password --
partner_c = A.app.test_client()
r = partner_c.post("/api/partner/login", json={"login_id": LOGIN_ID, "password": PW0})
chk(r.status_code == 200, "  (준비) 협력사 실제 로그인 — 200", r.status_code)
html_partner = partner_c.get("/change-password").get_data(as_text=True)
chk(my_id_from(html_partner) == LOGIN_ID,
    "★★★★★ (a) 협력사로 렌더한 화면의 MY_ID가 실제 로그인 아이디와 일치한다",
    my_id_from(html_partner))

insurer_c = A.app.test_client()
r = insurer_c.post("/api/insurer/login", json={"login_id": "r673insurer", "password": PW0})
chk(r.status_code == 200, "  (준비) 보험사 실제 로그인 — 200", r.status_code)
html_insurer = insurer_c.get("/change-password").get_data(as_text=True)
chk(my_id_from(html_insurer) == "r673insurer",
    "★★★★★ (a) 보험사로 렌더한 화면의 MY_ID가 실제 로그인 아이디와 일치한다",
    my_id_from(html_insurer))

admin_c = A.app.test_client()
r = admin_c.post("/api/login", json={"username": "r673admin", "password": PW0})
chk(r.status_code == 200, "  (준비) 관리자 실제 로그인 — 200", r.status_code)
html_admin = admin_c.get("/change-password").get_data(as_text=True)
chk(my_id_from(html_admin) == "r673admin",
    "★★★★★ (a) 관리자로 렌더한 화면의 MY_ID가 실제 로그인 아이디와 일치한다",
    my_id_from(html_admin))

# -- (c) login_id를 아예 안 주는 범용 렌더(test_template_js.py가 모든 템플릿에 쓰는 것과
#    똑같은 호출 서명)도 죽지 않는가 — 이 라운드 작업 중 실제로 한 번 걸렸던 자리다:
#    처음엔 {{ login_id | tojson }}만 썼더니 이 범용 렌더에서 Undefined가 그대로
#    tojson에 들어가 TypeError로 죽었다(실측: test_template_js.py 8/9 → FAIL). default('')로
#    감싸 고쳤다 — 그 되돌아간 상태가 실제로 재현되는지까지 이 회귀에 넣어 둔다.
from flask import render_template as _render_template  # noqa: E402
with A.app.test_request_context("/change-password"):
    try:
        _html_generic = _render_template("change_password.html", nonce="testnonce",
                                          build="t", ver="t")
        _generic_err = None
    except Exception as _e:
        _html_generic, _generic_err = None, _e
chk(_generic_err is None,
    "★★★★★ (c) login_id를 안 주는 범용 렌더(test_template_js.py와 같은 호출)도 죽지 않는다 "
    "— default('') 방어가 실제로 이 경로를 막는다", repr(_generic_err))
if _html_generic:
    chk(my_id_from(_html_generic) == "",
        "  (c) login_id 없이 렌더하면 MY_ID는 빈 문자열로 안전하게 떨어진다", my_id_from(_html_generic))

CURRENT_JS = extract_js_block(html_partner)
chk("const MY_ID" in CURRENT_JS and "function checkRule" in CURRENT_JS and "function set" in CURRENT_JS,
    "  (준비) 협력사 렌더 결과에서 JS 블록(kinds~set)을 실제로 잘라냈다", f"len={len(CURRENT_JS)}")

# -- 이 라운드의 핵심 케이스 — 규칙 ①②④는 만족하지만 아이디를 포함한 비밀번호 --
PW_WITH_ID = LOGIN_ID + "9900!!"        # 3종·길이 충분·연속문자 없음, 그러나 아이디 포함
PW_WITH_ID_UPPER = LOGIN_ID.upper() + "9900!!"   # 대소문자 무시 검사 확인
PW_CLEAN = "Zq88Nope!!"                  # 규칙 다 만족 + 아이디 미포함(대조군)
PW_SHORT = "Ab9!"                        # 길이 부족(대조군 — r_id와 무관하게 항상 실패해야 함)


def run_node(js_body, passwords, label):
    if not NODE:
        return None
    script = (
        js_body + "\n\n"
        "const _els = {};\n"
        "function getEl(id){ if(!(id in _els)) _els[id] = {value:'', className:'__unset__'}; "
        "return _els[id]; }\n"
        "const document = { getElementById: getEl };\n"
        "const PWLIST = " + json.dumps(passwords, ensure_ascii=False) + ";\n"
        "const out = [];\n"
        "for (const pw of PWLIST) {\n"
        "  getEl('np').value = pw;\n"
        "  checkRule();\n"
        "  out.push({pw: pw, r_kind: getEl('r_kind').className, r_len: getEl('r_len').className,\n"
        "            r_rep: getEl('r_rep').className,\n"
        "            r_id: ('r_id' in _els) ? _els['r_id'].className : null});\n"
        "}\n"
        "console.log(JSON.stringify(out));\n"
    )
    p = os.path.join(_tmpdir, f"probe_{label}.js")
    io.open(p, "w", encoding="utf-8").write(script)
    r = subprocess.run([NODE, p], capture_output=True, text=True, encoding="utf-8", timeout=15)
    if r.returncode != 0:
        chk(False, f"  {label} Node 실행 실패", (r.stderr or "")[:400])
        return None
    try:
        return {row["pw"]: row for row in json.loads(r.stdout.strip())}
    except Exception as e:
        chk(False, f"  {label} Node 출력 파싱 실패", f"{e}: {r.stdout[:200]}")
        return None


PWLIST = [PW_WITH_ID, PW_WITH_ID_UPPER, PW_CLEAN, PW_SHORT]

if NODE:
    cur = run_node(CURRENT_JS, PWLIST, "current")
    chk(cur is not None, "  Node로 지금(고친) 체크리스트 로직을 실제 실행했다", str(cur))
    if cur:
        chk(cur[PW_WITH_ID]["r_kind"] == "chk on" and cur[PW_WITH_ID]["r_len"] == "chk on"
            and cur[PW_WITH_ID]["r_rep"] == "chk on",
            "  (전제) PW_WITH_ID는 규칙①②④를 이미 만족한다(그래야 ③만의 효과를 본다)",
            cur[PW_WITH_ID])
        chk(cur[PW_WITH_ID]["r_id"] == "chk off",
            "★★★★★★ (지금) 아이디를 포함한 비밀번호는 r_id 칸이 꺼져 있다(고치기 전엔 "
            "이 칸 자체가 없었다)", cur[PW_WITH_ID]["r_id"])
        chk(cur[PW_WITH_ID_UPPER]["r_id"] == "chk off",
            "★★★★ 대소문자를 바꿔 넣어도(서버와 같은 대소문자 무시) 여전히 꺼진다",
            cur[PW_WITH_ID_UPPER]["r_id"])
        chk(cur[PW_CLEAN]["r_id"] == "chk on" and cur[PW_CLEAN]["r_kind"] == "chk on"
            and cur[PW_CLEAN]["r_len"] == "chk on" and cur[PW_CLEAN]["r_rep"] == "chk on",
            "  (과잉차단 아님) 아이디 없는 정상 비밀번호는 네 규칙 모두 켜진다", cur[PW_CLEAN])
        chk(cur[PW_SHORT]["r_id"] == "chk on" and cur[PW_SHORT]["r_len"] == "chk off",
            "  (독립성) 길이부족 케이스는 r_len만 꺼지고 r_id는 무관하게 켜진다(아이디 관련 "
            "없음 — 두 규칙이 서로를 오염시키지 않음)", cur[PW_SHORT])

    # -- 서버의 진짜 판정(같은 모듈에서 직접 호출)과 대조 --
    print("\n  (교차검증) 같은 케이스를 서버 실제 함수 password_policy_error()로도 직접 호출")
    err_with_id = A.password_policy_error(PW_WITH_ID, LOGIN_ID)
    err_clean = A.password_policy_error(PW_CLEAN, LOGIN_ID)
    chk(bool(err_with_id) and "아이디" in err_with_id,
        "★★★★★★ 서버 password_policy_error()도 같은 비밀번호를 아이디 포함으로 실제 거부한다",
        err_with_id)
    chk(err_clean is None,
        "  대조군(아이디 없는 비밀번호)은 서버도 통과시킨다(과잉차단 아님)", err_clean)

    # -- [3](b) 실제 HTTP 왕복 — POST /api/change-password --
    print("\n[3](b) 종단 — 실제 POST /api/change-password 왕복")
    _csrf_r = partner_c.get("/api/csrf")
    csrf = _csrf_r.get_json()["token"]
    r_bad = partner_c.post("/api/change-password",
                            json={"current": PW0, "new": PW_WITH_ID},
                            headers={"X-CSRF-Token": csrf})
    chk(r_bad.status_code == 400, "★★★★★★ 아이디 포함 비밀번호로 실제 제출 — 400 거부", r_bad.status_code)
    chk("아이디" in (r_bad.get_json() or {}).get("error", ""),
        "★★★★★★ 에러 문구가 실제로 '아이디'를 언급한다(화면이 이제 미리 보여주는 바로 그 이유)",
        (r_bad.get_json() or {}).get("error"))

    r_ok = partner_c.post("/api/change-password",
                           json={"current": PW0, "new": PW_CLEAN},
                           headers={"X-CSRF-Token": csrf})
    chk(r_ok.status_code == 200 and (r_ok.get_json() or {}).get("ok") is True,
        "★★★★★ 아이디 없는 비밀번호는 실제로 200 성공(과잉차단 아님 — 실제 변경까지 확인)",
        (r_ok.status_code, r_ok.get_json()))

    # ============================================================
    print("\n[4] 되돌리기-증명 — 잘라낸 (고친) JS에서 MY_ID·r_id만 제거한 옛 버전 재현")
    #      ⚠ 실제 파일은 전혀 건드리지 않는다 — 메모리 문자열만 다룬다.
    # ------------------------------------------------------------
    OLD_JS = re.sub(r"\nconst MY_ID = [^\n]*;\n", "\n", CURRENT_JS, count=1)
    OLD_JS = re.sub(r"\n\s*set\('r_id',[^\n]*\);\n", "\n", OLD_JS, count=1)
    chk(OLD_JS != CURRENT_JS and "MY_ID" not in OLD_JS and "r_id" not in OLD_JS,
        "  (전제) 되돌린 사본에서 MY_ID·r_id가 실제로 사라졌다(실제 파일은 무변경)")

    old = run_node(OLD_JS, PWLIST, "old")
    chk(old is not None, "  Node로 옛 버전(고치기 전 재현)을 실제 실행했다", str(old))
    if old:
        chk(old[PW_WITH_ID]["r_kind"] == "chk on" and old[PW_WITH_ID]["r_len"] == "chk on"
            and old[PW_WITH_ID]["r_rep"] == "chk on",
            "★★★★★★ (인과관계 실측) 옛 화면이라면 아이디를 포함한 바로 그 비밀번호도 "
            "규칙①②④ 세 칸이 전부 켜진다(=화면은 '3/3 초록불, 문제없음'으로 보였을 것)",
            old[PW_WITH_ID])
        chk(old[PW_WITH_ID]["r_id"] is None,
            "★★★★★★ (인과관계 실측) 옛 화면엔 r_id 칸 자체가 없다(만들어진 적도 없음) — "
            "그런데 바로 위에서 실측했듯 서버는 그 순간에도 이미 거부한다. 이 화면과 서버가 "
            "'다 됐다' vs '거부'로 갈렸던 바로 그 간극이 이번 수정 전 실제 사용자 경험이었다",
            old[PW_WITH_ID]["r_id"])
        # 회귀 없음 확인 — 옛 버전이라도 나머지 세 규칙 자체의 판정은 지금과 같아야 한다
        chk(old[PW_SHORT]["r_len"] == "chk off" and old[PW_CLEAN]["r_kind"] == "chk on",
            "  (회귀 없음) 옛 버전도 규칙①②④ 자체의 판정 로직은 지금과 동일하다 "
            "(이번 수정이 건드린 건 ③ 규칙의 유무뿐)", old[PW_SHORT])
else:
    chk(False, "  [2]~[4] node가 없어 건너뛸 수밖에 없었다")

# 실제 파일이 여전히 고친 상태 그대로인지 마지막으로 재확인(회귀 없음).
chk('id="r_id"' in read("templates/change_password.html"),
    "  (sanity) 실제 파일(디스크)은 여전히 고친 상태 그대로다(위 [4]는 메모리 문자열만 다뤘다)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
