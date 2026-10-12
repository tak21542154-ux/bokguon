# -*- coding: utf-8 -*-
"""[기능] 운영 점검(집계 자기점검·사고 대응 안내) + 발주처 연동 안내서 — 회귀.

  왜 만들었나 —
    「오늘 할 일」의 한 항목이 운영에서 **조용히 사라져 있었다.** 자식 표
    (`change_orders`)에 없는 컬럼(`is_demo`)으로 걸러 SQL 이 죽었는데, 화면 코드가
    `except sqlite3.Error` 로 삼키는 바람에 0건도 아니고 항목 자체가 없어졌다.
    없는 일과 못 센 일이 화면에서 똑같이 보였다.
    그 기능의 회귀 31개는 전부 소스 **문자열**만 확인해서 전부 통과했고,
    전체 배터리 52/52 초록으로 운영까지 나갔다.

  지켜야 할 성질 —
    ① **정의를 실제로 실행해 본다.** 문자열이 맞는 것과 질의가 도는 것은 다르다.
    ② **실패를 숨기지 않는다.** 집계가 죽으면 화면이 그렇다고 말해야 한다.
    ③ 안내서의 주소·사건 목록을 **손으로 적지 않는다** — 코드가 바뀌면 문서만
       옛말이 되고 아무도 모른다.
    ④ 안내서는 공개 문서가 아니다(관리자 또는 발주처 세션).
    ⑤ 개발 인스턴스가 운영 공개 주소를 안내서에 싣지 않는다.

      python test_feature_selfcheck.py
"""
import ast
import io
import os
import re
import sqlite3
import shutil
import sys
import tempfile

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
AH, TPL = read("templates/admin.html"), read("templates/insurer_api_guide.html")

print("═" * 70)
print("  기능 회귀 — 운영 점검 · 발주처 연동 안내서")
print("═" * 70)

print("\n[1] 정의를 **실제로 실행**한다")
_sc = func_src(APP, "def api_self_check")
chk("def _probe" in APP, "★ 질의를 실행해 보는 함수가 있다")
_pr = func_src(APP, "def _probe")
chk("conn.execute(sql)" in _pr, "★★ 문자열을 보는 게 아니라 진짜로 실행한다")
chk('"ok": False' in _pr and '"why"' in _pr, "★ 실패하면 이유를 담아 돌려준다")
for g in ("TODAY_BLOCKED", "TODAY_WAITING", "TODAY_AGING", "TODAY_QUEUE",
          "TODAY_PREP", "ONBOARD_STAGES"):
    chk(g in _sc, f"★ '{g}' 정의를 점검 대상에 넣는다")
chk("it[4]" in _sc, "★ 질의가 둘인 항목(PREP)도 둘 다 본다")

print("\n[2] 그 점검이 정말로 결함을 잡는가 — 빈 스키마에서 전수 실행")
_tmp = tempfile.mkdtemp(prefix="selfchk_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmp, "probe.db")
sys.path.insert(0, HERE)
_n, _bad = 0, []
try:
    import db as _db
    _db.init_db()
    _i = APP.find('_LIVE = "COALESCE(is_demo,0)=0"')
    _j = APP.find("def _today_urgent_n")
    _ns = {}
    #  ⚠ CASE_OPEN_SQL 참조 추가(라운드59 — 종결상태 목록 드리프트 통합) — 정의
    #    줄만 실제 소스에서 먼저 떼어 실행해 둔다(하드코딩하면 또 드리프트한다).
    _co = APP.find("CASE_OPEN_SQL = ")
    exec(compile(APP[_co:APP.find("\n", _co)], "<case_open>", "exec"), _ns)  # noqa: S102
    exec(compile(APP[_i:_j], "<today>", "exec"), _ns)          # noqa: S102 — 우리 소스다
    #  ONBOARD_STAGES 도 같은 방식으로 떼어 온다
    _k = APP.find("ONBOARD_STAGES = [")
    _l = APP.find("def _onboard_where")
    exec(compile(APP[_k:_l], "<onb>", "exec"), _ns)            # noqa: S102
    _c = sqlite3.connect(os.environ["BOKGUON_DB_PATH"])
    for _g in ("TODAY_BLOCKED", "TODAY_WAITING", "TODAY_AGING", "TODAY_QUEUE", "TODAY_PREP"):
        for _it in _ns[_g]:
            for _sql in _it[3:]:
                _n += 1
                try:
                    _c.execute(_sql).fetchone()
                except sqlite3.Error as _e:
                    _bad.append(f"[{_g}] {_it[0]} → {_e}")
    for _lbl, _why, _cond in _ns["ONBOARD_STAGES"]:
        _n += 1
        try:
            _c.execute(
                f"SELECT COUNT(*) FROM partners WHERE status='활성' AND ({_cond})").fetchone()
        except sqlite3.Error as _e:
            _bad.append(f"[온보딩] {_lbl} → {_e}")
    _c.close()
except Exception as _e:                                        # noqa: BLE001
    _bad.append(f"검사 자체가 실패: {type(_e).__name__} {_e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    shutil.rmtree(_tmp, ignore_errors=True)

chk(_n >= 23, f"질의 {_n}개를 뽑아 실행했다",
    "0개면 앵커가 어긋난 것이다 — 아무것도 검사하지 않는다")
chk(not _bad, "★★ 모든 정의가 실제 스키마에서 돈다", " / ".join(_bad[:3]))

print("\n[3] 실패를 숨기지 않는다")
_v = js_func(ADM, "VIEWS.selfcheck =")
chk("아예 사라집니다" in _v,
    "★★ 실패가 '0건' 이 아니라 '사라짐' 이라는 것을 화면이 설명한다")
chk("n_failed" in _v and "d.failed" in _v, "★ 실패 목록을 보여 준다")
chk("bdg-selfcheck" in _v and "bdg-selfcheck" in AH, "★ 실패 수가 배지로 뜬다")
chk("모두 정상" in _v, "★ 이상 없을 때도 그렇다고 말한다(무소식이 아니라 확인)")

print("\n[4] 설정 현황이 실테스트에 필요한 것을 짚는다")
chk("NOTIFY_ENABLED and POPBILL.ready()" in _sc, "★ 발송 상태를 기존 규칙으로 판정한다")
chk("입찰 경험 있는 협력사" in _sc,
    "★★ 부를 수 있는 업체 수를 보여 준다(0곳이면 공고가 무의미하다)")
chk("실사건에 섞인 검증 데이터" in _sc, "★ 실사건에 섞인 검증 데이터를 짚는다")
chk("BUILD_HASH" in _sc, "★ 화면과 서버가 같은 코드인지 확인할 값을 준다")

print("\n[5] 사고 대응 안내")
chk("INCIDENT_PLAYBOOK" in APP, "★ 안내 표가 있다")
_pb = APP[APP.find("INCIDENT_PLAYBOOK = ["):APP.find("def _probe")]
for k in ("낙찰 취소", "정산", "재발급"):
    chk(k in _pb, f"★ '{k}' 상황이 들어 있다")
chk("일이 잘못됐을 때" in _v, "★ 화면에 그 표가 나온다")

print("\n[6] 연동 안내서 — 값을 손으로 적지 않는다")
_gd = func_src(APP, "def insurer_api_guide")
chk("WEBHOOK_EVENTS" in _gd, "★ 사건 목록을 코드 상수에서 가져온다")
chk("request.url_root" in _gd, "★ 주소를 실제 접속 주소에서 만든다")
chk("{{ base }}" in TPL, "★ 서식이 그 값을 쓴다")
chk("{{ events|join" in TPL, "★ 사건 목록도 서식이 받아 쓴다")
chk("X-API-Key" in TPL and "/api/v1/ping" in TPL, "★ 실제 인증 방식·점검 경로가 적혀 있다")

print("\n[7] 안내서는 공개 문서가 아니다")
chk('session.get("admin") or iid' in _gd, "★★ 관리자 또는 발주처 세션만 본다")
chk('redirect("/insurer/login")' in _gd, "★ 아니면 로그인으로 보낸다")
chk('if session.get("admin") and want' in _gd,
    "★★ 발주처는 남의 이름이 박힌 문서를 못 받는다(관리자만 지정 가능)")
chk("IS_PROD and os.path.exists" in _gd,
    "★★ 개발 인스턴스가 운영 공개 주소를 싣지 않는다",
    "받는 쪽은 그게 시험용인지 실서비스인지 구분할 방법이 없다")

print("\n[8] 법률 철칙이 문서에 적혀 있다")
chk("금액을 확정하거나 협상하지 않으며" in TPL, "★★ 금액을 확정·협상하지 않는다 (철칙 1)")
chk("손해액을 산정하지 않습니다" in TPL, "★★ 손해사정을 하지 않는다 (철칙 2)")
chk("낙찰 승인은 언제나 발주처가" in TPL, "★ 승인 주체가 발주처임을 밝힌다")
chk("시공 도급 금액" in TPL, "★ 금액의 성격을 밝힌다")


def _no_comment_jinja(t):
    t = re.sub(r"\{#[\s\S]*?#\}", " ", t)
    return re.sub(r"/\*[\s\S]*?\*/", " ", t)


_tc = _no_comment_jinja(TPL)
for bad in ("손해사정", "보험금 산정", "면책"):
    chk(bad not in _tc.replace("손해액을 산정하지 않습니다", ""),
        f"★ 보험의 언어를 쓰지 않는다 — '{bad}'")

print("\n[9] 화면 손잡이")
chk('data-v="selfcheck"' in AH, "★ 메뉴가 있다")
chk(len(re.findall(r"ACT\.selfRun\s*=", ADM)) == 1, "★ 다시 점검 핸들러가 한 번 등록된다")
chk('data-act="selfRun"' in _v, "★ 다시 점검 버튼")
chk('href="/docs/insurer-api"' in _v, "★ 안내서 링크")
chk('rel="noopener"' in _v, "★ 새 탭에 opener 를 안 넘긴다")
chk("tbl-wrap" in _v and "pill" in _v, "★ 기존 서식을 재사용한다(새 CSS 없음)")

print("")
try:
    ast.parse(APP); _ok, _why = True, ""
except SyntaxError as e:
    _ok, _why = False, f"{e.lineno}행: {e.msg}"
chk(_ok, "app.py 구문", _why)
chk(TPL.count("{%") == TPL.count("%}"),
    "insurer_api_guide.html 태그 균형", f"{TPL.count('{%')} / {TPL.count('%}')}")
chk("{{ csp_nonce }}" in TPL, "★ 인라인 style 에 nonce 가 있다(CSP)")

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
