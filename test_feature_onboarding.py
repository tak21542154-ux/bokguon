# -*- coding: utf-8 -*-
"""[기능] 협력사 온보딩 — 회귀.

  왜 만들었나 —
    실데이터에서 **활성 협력사 399곳 중 포털 계정은 1곳**이었다. 공고를 열어도
    누를 사람이 없는데, 화면 어디에도 그 사실이 드러나지 않았다. 운영자는
    수배 알림을 20곳에 보냈으니 20곳이 대기 중이라 믿고 기다린다 — 현실에선
    아무도 오지 않는다. 이 기능의 목적은 그 거짓 안심을 깨는 것이다.

  지켜야 할 성질 —
    ① **발급 규칙이 한 곳에만 있다.** 예전엔 API(`/credentials`)와 CLI
       (`partner_accounts.py`)가 규칙을 따로 갖고 있었고, CLI 쪽은 아이디 중복을
       `partners` 한 표에서만 봤다. 로그인은 네 표를 훑으므로 서로 다른 표의
       계정끼리 아이디가 겹칠 수 있었다. 이제 `issue_partner_login()` 하나뿐이다.
    ② **이미 있는 계정을 갈아엎지 않는다.** 일괄 발급을 두 번 누르면 안내받고
       로그인해 둔 업체가 갑자기 못 들어온다.
    ③ **발송이 꺼져 있어도 '안내함' 기록은 남는다.** 전화·카톡으로 직접 알린
       경우가 실제로 더 많다. 그걸 못 남기면 이 화면이 거짓말을 한다.
    ④ **업체를 미는 표시·정렬을 두지 않는다** (하도급법 §18의8 3호).
    ⑤ **임시 비밀번호는 저장하지 않는다.** 발급 응답이 유일한 기회다.

  실측(별도) —
    계정을 진짜로 만들고 **그 계정으로 협력사 포털에 로그인**해 확인했다 33/33.
    소스 문자열만 보는 검사는 동작을 보증하지 않는다 — 오늘 그것 때문에
    「오늘 할 일」 항목 하나가 운영에서 조용히 사라져 있었다.

      python test_feature_onboarding.py
"""
import ast
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    try:
        return io.open(os.path.join(HERE, rel), encoding="utf-8").read()
    except OSError as e:
        return f"<<읽기실패 {e}>>"


def func_src(src, header):
    i = src.find(header)
    if i < 0:
        return ""
    m = re.search(r"\n(?:@app\.|def )", src[i + len(header):])
    return src[i:i + len(header) + m.start()] if m else src[i:]


def js_func(src, header):
    i = src.find(header)
    if i < 0:
        return ""
    depth, j = 0, src.find("{", i)
    if j < 0:
        return ""
    while j < len(src):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
        j += 1
    return src[i:]


APP, ADM = read("app.py"), read("static/admin.js")
AH, DBP = read("templates/admin.html"), read("db.py")
PP = read("templates/partner_portal.html")

print("═" * 70)
print("  기능 회귀 — 협력사 온보딩")
print("═" * 70)

print("\n[1] 발급 규칙이 한 곳에만 있다")
chk(APP.count("def issue_partner_login") == 1, "★ 발급 함수가 하나뿐이다")
_core = func_src(APP, "def issue_partner_login")
_one = func_src(APP, "def api_partner_credentials")
_bulk = func_src(APP, "def api_partner_bulk_credentials")
chk("issue_partner_login(conn" in _one, "★★ 단건 발급이 그 함수를 쓴다")
chk("issue_partner_login(conn" in _bulk, "★★ 일괄 발급도 **같은 함수**를 쓴다",
    "규칙을 두 벌 쓰면 언젠가 갈린다 — CLI 가 아이디 중복을 한 표에서만 보던 것이 그랬다")
chk("DB.hash_pw" not in _one and "DB.hash_pw" not in _bulk,
    "★ 라우트가 직접 비밀번호를 만들지 않는다(핵심 로직 중복 없음)")

print("\n[2] 아이디는 전역에서 유일하다")
_taken = func_src(APP, "def _login_id_taken")
for tbl in ("partners", "insurers", "portal_users", "admins"):
    chk(tbl in _taken, f"★ '{tbl}' 표까지 대조한다",
        "로그인이 네 표를 훑으므로 한 표만 보면 서로 다른 표끼리 겹칠 수 있다")
chk("_login_id_taken" in func_src(APP, "def _auto_login_id"),
    "★★ 자동 생성 아이디도 같은 대조를 거친다")
chk("n > 200" in func_src(APP, "def _auto_login_id"),
    "★ 후보 탐색이 무한루프로 서버를 세우지 않는다")
chk("PARTNER_ID_RESERVED" in APP and '"partner", "p2", "p3", "admin", "staff"' in APP,
    "★ 예약어를 막는다(go-live 가 그 이름들을 정리한다)")

print("\n[3] 이미 있는 계정을 갈아엎지 않는다")
chk('if p["login_id"]:' in _bulk and "이미 계정이 있습니다" in _bulk,
    "★★ 일괄 발급은 계정 있는 업체를 건너뛴다",
    "두 번 누르면 안내받고 로그인해 둔 업체가 갑자기 못 들어온다")
chk("아이디는 여기서" in _core, "★ 아이디를 바꾸려는 요청은 막고 이유를 알려 준다")
chk("must_change_pw=1" in _core, "★ 임시 비밀번호는 첫 로그인에 바꾸게 한다")

print("\n[4] 첫 접속을 한 번만 기록한다")
_login = func_src(APP, "def api_partner_login")
chk("first_login_at" in _login, "★ 로그인이 첫 접속 시각을 남긴다")
chk("COALESCE(first_login_at,'')=''" in _login,
    "★★ **비어 있을 때만** 쓴다(두 번째 로그인이 덮어쓰면 안 된다)")
chk("except sqlite3.Error" in _login,
    "★ 집계 실패가 로그인을 막지 않는다(통계 때문에 업무가 멈추면 안 된다)")
chk(APP.count('session["partner_id"] = auth["org_id"]') == 1,
    "★ 협력사 로그인 경로가 하나뿐이다(형제 경로 누락 방지)")

print("\n[5] 발송이 꺼져 있어도 기록은 남는다")
_inv = func_src(APP, "def api_partner_invite")
chk("NOTIFY_ENABLED and POPBILL.ready()" in _inv,
    "★ 실발송 판정은 기존과 같은 한 곳의 규칙을 쓴다")
chk("UPDATE partners SET invited_at" in _inv, "★ 안내 표시를 남긴다")
_i_live = _inv.find("if live and")
_i_mark = _inv.find("UPDATE partners SET invited_at")
chk(0 < _i_live < _i_mark,
    "★★ 발송 여부와 **무관하게** 표시가 남는다(발송 분기 밖에 있다)",
    "전화·카톡으로 직접 알린 경우가 더 많다 — 못 남기면 화면이 거짓말을 한다")
chk("계정이 아직 없습니다" in _inv, "★ 계정 없는 업체엔 표시하지 않는다")

print("\n[6] 업체를 미는 표시·정렬이 없다 (하도급법 §18의8 3호)")
_onb = func_src(APP, "def api_partner_onboarding")
#  ⚠ 정렬·조회는 `_onboard_rows()` 한 곳으로 모았다(화면·엑셀 공용).
#    라우트 본문에서 찾으면 리팩터 뒤 멀쩡한 코드를 놓고 테스트만 빨개진다.
_rows_fn = func_src(APP, "def _onboard_rows")
chk("ORDER BY COALESCE(region,''), name" in _rows_fn,
    "★★ 정렬이 중립 기준이다(지역·이름)")


def _no_comment_js(t):
    """JS 주석을 지운다 — 안전장치 주석이 금칙어로 걸리지 않게."""
    t = re.sub(r"/\*[\s\S]*?\*/", " ", t)
    return "\n".join(l for l in t.splitlines() if not l.strip().startswith("//"))


_view = _no_comment_js(js_func(ADM, "VIEWS.onboard ="))
for bad in ("추천", "우선순위", "등수", "점수", "rating", "win_rate"):
    chk(bad not in _view, f"★ 화면에 '{bad}' 표시가 없다")
chk("rating" not in _onb and "win_rate" not in _onb,
    "★ 서버도 성과 지표를 이 화면에 싣지 않는다")

print("\n[7] 임시 비밀번호를 저장하지 않는다")
chk("temp_password" not in DBP, "★ 스키마에 비밀번호 원문 칸이 없다")
chk("INSERT INTO activity_log" not in _core or "temp_pw" not in _core.split("DB.log")[1][:200],
    "★ 감사 로그에 비밀번호를 남기지 않는다")
chk("temp_pw" not in _core[_core.find("DB.log"):_core.find("return True")],
    "★★ 로그·알림 문구에 비밀번호가 섞이지 않는다")
_csv = js_func(ADM, "ACT.onbCredCsv =")
chk("console.log" not in _csv and "console.log" not in _view,
    "★ 화면이 비밀번호를 콘솔에 찍지 않는다")
chk("한 번만 표시" in ADM, "★ 한 번만 보인다는 사실을 사용자에게 알린다")
chk("\\ufeff" in _csv or "﻿" in _csv,
    "★ 내려받는 파일에 BOM 을 붙인다(엑셀 한글 깨짐 방지)")
chk('replace(/"/g' in _csv, "★ CSV 값의 큰따옴표를 이스케이프한다")

print("\n[8] 온보딩 단계 정의")
chk(APP.count("ONBOARD_STAGES") >= 2, "★ 단계 정의가 있다")
chk("_onboard_rows(conn" in _onb, "★ 목록 조회가 공용 함수를 쓴다")
chk("_onboard_where(args)" in _rows_fn, "★ 그 함수가 공용 조건을 쓴다")
for st in ("계정 없음", "안내 전", "안내함 · 미접속", "접속함 · 미입찰", "입찰 경험 있음"):
    chk(f'"{st}"' in APP, f"★ 단계 '{st}' 가 있다")
chk("def stage_of" in _onb, "★ 업체마다 단계를 하나로 정한다(중복 표시 방지)")
chk('"reachable"' in _onb,
    "★★ 연락 수단이 없는 업체를 표시한다(안내 자체가 불가능한 업체다)")

print("\n[9] DB 칸")
for col in ("cred_issued_at", "invited_at", "first_login_at"):
    chk(f'("partners", "{col}"' in DBP, f"★ partners.{col} 마이그레이션")

print("\n[10] 화면 손잡이")
chk('data-v="onboard"' in AH, "★ 메뉴가 있다")
chk('id="bdg-onboard"' in AH, "★ 배지가 있다")
for act in ("onbStage", "onbSearch", "onbAll", "onbIssue", "onbInvite", "onbCredCsv", "onbPtype"):
    #  ⚠ `=` 앞 공백 수로 세지 않는다. 핸들러를 세로로 맞추려고 두 칸을 넣는 일이
    #    흔한데, 그러면 멀쩡한 코드를 놓고 테스트만 빨개진다.
    chk(len(re.findall(rf"ACT\.{act}\s*=", ADM)) == 1, f"★ 핸들러 {act} 가 한 번 등록된다")
    chk(f'"{act}"' in ADM, f"★ {act} 를 부르는 자리가 있다")
chk("class=\"pipe\"" in _view and "pstep" in _view,
    "★ 기존 깔때기 컴포넌트를 재사용한다(새 CSS 를 만들지 않았다)")
chk("tbl-wrap" in _view, "★ 기존 표 서식을 쓴다")

print("\n[11] 온보딩 대상 엑셀 — 화면과 같은 조건")
_ex = func_src(APP, "def api_partner_onboarding_export")
chk(bool(_ex), "★ 엑셀 라우트가 있다")
chk("_onboard_rows(conn" in _ex,
    "★★ 화면과 **같은 조회 함수**를 쓴다",
    "규칙을 두 벌 쓰면 엑셀과 화면의 모집단이 갈리고, 그건 눈에 잘 안 띈다")
chk("temp_password" not in _ex and "password" not in _ex,
    "★★ 비밀번호가 담기지 않는다(누구를 부를지 정하는 문서다)")
chk("상한에 걸려 잘렸습니다" in _ex, "★ 잘렸으면 파일 안에 적는다")
chk("연락 가능" in _ex, "★ 안내 불가 업체를 식별할 수 있다")
chk('DB.log(conn, actor(), "온보딩 대상 내보내기"' in _ex, "★ 뽑아 간 사실이 남는다")
chk("ORDER BY COALESCE(region,''), name" in _rows_fn,
    "★ 정렬이 중립 기준이다 (§18의8 3호)")
chk("_xl_safe(" in _ex, "★ 셀 정제를 거친다")
#  ⚠ 주석을 지우고 본다 — 'limit 만 뺀다' 는 **설명 문구 자체**가 금칙어로 걸린다.
#    이 프로젝트에서 다섯 번째 겪는 실수다(reference: 회귀가 자기 주석을 코드로 오독).
_exj = _no_comment_js(js_func(ADM, "ACT.onbExport ="))
chk(bool(_exj), "★ 화면에 버튼 핸들러가 있다")
for k in ("stage", "q", "region", "ptype"):
    chk(f"qs.set('{k}'" in _exj, f"★★ 화면 조건 '{k}' 를 그대로 싣는다")
chk("limit" not in _exj, "★ limit 은 안 싣는다(파일은 화면보다 넉넉히)")
chk('data-act="onbExport"' in ADM, "★ 버튼이 있다")
chk('filename="bokguon_onboarding_' in _ex, "★ 파일명이 ASCII 다")

print("\n[12] 첫 로그인 — 채워야 할 것을 알려 준다")
chk("def valid_biz_no" in APP, "★ 사업자번호 검증 함수가 있다")
_vb = func_src(APP, "def valid_biz_no")
chk("(1, 3, 7, 1, 3, 7, 1, 3, 5)" in _vb,
    "★★ 자릿수만 세지 않고 **검사숫자**까지 본다",
    "오타 하나면 건설업 등록 조회가 빈손으로 오고 '무등록' 으로 오판한다")
_pu = func_src(APP, "def api_partner_profile_update")
chk("valid_biz_no" in _pu, "★ 저장 경로가 그 검증을 거친다")
chk("이미 등록되어 있어 여기서 바꿀 수 없습니다" in _pu,
    "★★ 한 번 들어간 번호는 본인이 못 바꾼다",
    "확인한 업체가 조용히 다른 번호로 갈아타면 등록 조사 결과가 통째로 거짓이 된다")
chk('session["partner_id"]' in _pu, "★ 언제나 **자기 것만** 고친다(남의 id 를 안 받는다)")
_db_ = func_src(APP, "def api_partner_dashboard")
chk('"ready"' in _db_, "★ 준비 상태를 내려준다")
for k in ("acct", "phone", "region", "biz_no", "major", "license"):
    chk(f'"{k}":' in _db_[_db_.find('"ready"'):], f"★ ready.{k}")
_todo = js_func(PP, "function todoPanel()")
chk("R.biz_no === false" in _todo, "★ 사업자번호가 비면 알려 준다")
chk("R.major" not in _todo and "R.license" not in _todo,
    "★★ **본인이 못 고치는 것**은 재촉하지 않는다(화면이 잔소리가 되면 안 온다)")
_sp = js_func(PP, "function startPanel()")
chk(bool(_sp), "★ 처음 온 업체용 안내가 있다")
chk("지금은 열린 공고가 없습니다" in _sp,
    "★★ 공고가 0건일 때 빈 화면을 그대로 두지 않는다")
chk("담당자가 확인할 항목" in _sp, "★ 못 고치는 것은 담당자 몫이라고 말한다")
chk("if(!first) return ''" in _sp.replace(" ", "").replace("if(!first)return''", "if(!first) return ''")
    or "if(!first)" in _sp,
    "★ 이미 거래해 본 업체에겐 안 뜬다")


print("\n[13] 지역 표기 정규화")
#  ⚠ 실데이터에서 활성 399곳의 region 이 **149가지 표기**였다. SQL LIKE 로는
#    '충청남도' 를 '충남' 으로 못 잡아 충남이 14곳만 걸렸다(실제 24곳).
#    ⚠ 컬럼을 만들지 않는다 — region 을 쓰는 자리가 넷이라 저장하면 갈린다.
#  ⚠⚠ [라운드196] 정의 자체는 db.py 로 옮겼다 — compliance.py(도급 적법성
#    관문의 분할회피 합산판정)도 같은 정규화가 필요한데 app.py 를 가리킬 수
#    없어(순환 임포트) db.py 가 유일한 공유 지점이 됐다. app.py 는 이제
#    `norm_regions = DB.norm_regions` 로 재수출만 한다.
chk(DBP.count("def norm_regions") == 1, "★ 정규화 함수가 하나뿐이다")
chk(DBP.count("def region_matches") == 1, "★ 판정 함수가 하나뿐이다")
chk("norm_regions = DB.norm_regions" in APP and "region_matches = DB.region_matches" in APP,
    "★ app.py 의 기존 호출부는 재수출로 이름이 그대로 유지된다")
chk("region_norm" not in DBP,
    "★★ 스키마에 저장하지 않는다(쓰기 경로가 넷이라 갈린다)",
    "본인 수정·입점승인·관리자등록·관리자수정 — 한 곳만 빠져도 조용히 어긋난다")
_nr = func_src(DBP, "def norm_regions")
chk("_REGION_PAREN" in _nr, "★ 괄호 안(시·군·메모)은 버린다")
chk("추측" in _nr or "추측하지 않는다" in DBP[DBP.find("def norm_regions"):][:1200],
    "★★ 못 읽은 값을 추측해 채우지 않는다",
    "틀린 지역으로 업체를 부르게 된다")
_rm = func_src(DBP, "def region_matches")
chk("in got" in _rm, "★★ 다지역 업체는 어느 하나라도 맞으면 해당")
_ow = func_src(APP, "def _onboard_where")
#  ⚠ 검색어(q)는 region 을 LIKE 로 훑어도 된다 — 그건 '찾기' 이지 '거르기' 가 아니다.
#    막아야 하는 것은 **지역 필터**가 SQL LIKE 로 도는 것이다.
chk('args.get("region")' not in _ow,
    "★★ SQL 조건 함수가 지역 필터를 만들지 않는다(LIKE 로는 긴 이름을 못 잡는다)")
_or_ = func_src(APP, "def _onboard_rows")
chk("region_matches(" in _or_, "★ 지역 판정은 파이썬에서 한다")
chk("len(rs)" in _or_,
    "★★ 총건수도 **거른 뒤에** 센다",
    "SQL 로 세고 파이썬으로 거르면 '398곳 중 24곳' 처럼 숫자가 갈린다")
_exp = func_src(APP, "def api_partner_onboarding_export")
chk("_onboard_rows(conn" in _exp,
    "★★ 엑셀도 **같은 조회 함수**를 쓴다(모집단이 갈리지 않게)")
chk('"sido": list(SIDO)' in APP, "★ 광역 목록을 서버가 준다")
_vw = _no_comment_js(js_func(ADM, "VIEWS.onboard ="))
chk("ONB_SIDO" in _vw, "★ 화면이 그 목록을 쓴다(목록을 따로 적지 않는다)")
chk("<select id=\"onb_rg\"" in _vw, "★★ 지역은 자유 입력이 아니라 고른 값이다")
chk("지역 확인 필요" in ADM,
    "★★ 지역을 못 읽은 업체를 드러낸다(조용히 빠지면 영영 안 불린다)")

print("")
try:
    ast.parse(APP); _ok, _why = True, ""
except SyntaxError as e:
    _ok, _why = False, f"{e.lineno}행: {e.msg}"
chk(_ok, "app.py 구문", _why)
chk(AH.count("<div") == AH.count("</div>"),
    "admin.html div 균형", f"{AH.count('<div')} / {AH.count('</div>')}")

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
