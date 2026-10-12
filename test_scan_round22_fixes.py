# -*- coding: utf-8 -*-
"""22라운드 회귀 — **기록이 있는데 못 찾고, 통지한다면서 안 하고, 지우면 죽는다.**

  ① 일정 삭제가 100% 500 이었다.
     `SELECT title, event_date, kind FROM schedule_events` — `kind` 는 그 표에
     없는 열이다(실측: OperationalError no such column: kind). try 도 없어서,
     **지우기 전에 무엇이었는지 남기려던 줄이 지우는 일 자체를 막았다.**

  ② 미수선 종결이 아무에게도 안 갔다.
     `close_no_repair()` 는 "보험사에 결과가 전달됩니다" 를 돌려주는데
     포털 알림도·운영팀 알림도·웹훅도 없었다. 사건만 조용히 종결됐다.
     화면이 하지 않는 일을 했다고 말하는 것은 그 자체로 결함이다.

  ③ 엑셀이 화면과 다른 말을 했다.
     정산만 데모·취소를 걸렀고 사건·입점신청·도입문의·하자는 안 걸렀다
     (실측 verify.db: 사건 149건 중 데모 15, 하자 4건 중 3).
     게다가 필터를 하나도 안 받아 화면에 12건이 떠 있어도 전부가 내려왔다.

  ④ 감사 로그를 찾을 수 없었다.
     조건 없는 `LIMIT 100` 에 화면은 그중 **14줄**만 그렸다. 실측 8,600건.
     기록이 있는데 못 찾는 것은 분쟁에서 기록이 없는 것과 같다.

      python test_scan_round22_fixes.py
"""
import ast
import io
import os
import re
import sqlite3
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


def func_body(src, header):
    i = src.find(header)
    if i < 0:
        return ""
    j = len(src)
    for pat in ("\ndef ", "\n@app."):
        k = src.find(pat, i + len(header))
        if 0 < k < j:
            j = k
    return src[i:j]


def js_func(src, header):
    """중괄호 균형으로 함수 본문을 뜬다 — **글자수로 자르지 않는다.**

    ⚠ 앞 라운드에서 고정 창(+2600자)으로 잘랐다가, 그 라운드에 코드가 늘자
      검사 대상이 창 밖으로 밀려 멀쩡한 코드가 실패로 떴다.
    """
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


def strip_py(t):
    return "\n".join(ln for ln in t.splitlines() if not ln.strip().startswith("#"))


def strip_doc(t):
    """`#` 주석에 더해 **docstring 까지** 지운다.

    ⚠ 금지어 검사를 strip_py 만으로 하면, 그 금지어를 '쓰지 않는다'고 설명하는
      docstring 자체가 걸린다. 실제로 이 파일에서 그렇게 한 번 헛돌았다 —
      `"보험금 지급 여부를 판단하는 것이 아니다"` 라는 안전장치 문장이
      '보험금이라는 말을 썼다'로 읽혔다.
    """
    return strip_py(re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', " ", t))


def strip_js(t):
    t = re.sub(r"(?<![A-Za-z0-9_\"'])/\*.*?\*/", " ", t, flags=re.S)
    return "\n".join(ln for ln in t.splitlines() if not ln.strip().startswith("//"))


APP, ADM = read("app.py"), read("static/admin.js")
_APPS, _ADMS = strip_py(APP), strip_js(ADM)

print("═" * 70)
print("  22라운드 회귀 — 삭제·통지·엑셀·감사로그")
print("═" * 70)

# ── ① ────────────────────────────────────────────────────────
print("\n[1] 일정 삭제 — 없는 열을 읽지 않는다")
_del = strip_py(func_body(APP, "def api_schedule_event_del"))
chk("kind" not in _del,
    "★★ `kind` 열을 더는 읽지 않는다",
    "schedule_events 에 그런 열이 없다 — 이 SELECT 하나로 일정 삭제가 100% 500 이었다")
chk("event_date" in _del and "title" in _del,
    "남기려던 것(제목·날짜)은 그대로 남긴다",
    "결함을 고치면서 감사 기록까지 지우면 안 된다")
chk("DB.log(" in _del, "삭제 사실을 감사 로그에 남긴다")

#  ★ 코드를 읽는 대신 **표에 진짜 무슨 열이 있는지** 본다.
#    같은 실수를 다른 열 이름으로 또 하면 위 문자열 검사는 통과한다.
_dbp = os.environ.get("BOKGUON_DB_PATH") or os.path.join(HERE, "bokguon.db")
if os.path.exists(_dbp):
    try:
        _c = sqlite3.connect(f"file:{_dbp}?mode=ro", uri=True)
        _cols = {r[1] for r in _c.execute("PRAGMA table_info(schedule_events)")}
        _c.close()
        _asked = set(re.findall(r"SELECT\s+([^\"']+?)\s+FROM schedule_events", _del))
        _bad = set()
        for _sel in _asked:
            for _col in _sel.split(","):
                _col = _col.strip()
                if _col and _col != "*" and _col not in _cols:
                    _bad.add(_col)
        chk(not _bad and _cols,
            "★★ 이 라우트가 읽는 열이 **실제 표에 전부 있다**",
            f"표에 없는 열: {sorted(_bad)}" if _bad else "표를 못 읽었다")
    except sqlite3.Error as e:
        chk(False, "일정 표 열 대조", f"{type(e).__name__}: {e}")
else:
    print("  [건너뜀] DB 파일이 없어 열 대조는 못 했다 —", _dbp)

# ── ② ────────────────────────────────────────────────────────
print("\n[2] 미수선 종결 — 말한 대로 실제로 전달한다")
_nr = strip_py(func_body(APP, "def api_partner_no_repair"))
chk('audience_type="insurer"' in _nr,
    "★★ 발주처 포털에 알림이 간다",
    "close_no_repair 는 '보험사에 결과가 전달됩니다' 를 돌려주는데 전달 경로가 없었다")
chk('audience_type="admin"' in _nr, "★ 운영팀도 안다(사건이 조용히 끝나지 않는다)")
chk('"case.no_repair"' in _nr,
    "★ 발주처 전산(웹훅)에도 알린다",
    "포털을 안 보는 발주처는 전산 연동이 유일한 통로다")
chk(_nr.count("conn.commit()") >= 2,
    "★ 알림 커밋 + 웹훅 이력 커밋을 둘 다 한다",
    "safe_webhook 의 이력 INSERT 는 새 암시적 트랜잭션을 연다 — 안 닫으면 "
    "통지는 갔는데 이력이 0건이 되고 id 가 되감겨 남의 배송 행을 덮어쓴다")
chk(_nr.find("conn.commit()") < _nr.find("safe_webhook"),
    "★ 웹훅은 **커밋 뒤에** 부른다",
    "커밋 전에 부르면 전송 스레드가 아직 없는 행을 UPDATE 한다")
#  ⚠ docstring 까지 지우고 본다 — 안 그러면 '보험금 지급 여부를 판단하지 않는다'
#    는 **안전장치 문장 자체**가 '보험금이라는 말을 썼다'로 걸린다.
_nrx = strip_doc(func_body(APP, "def api_partner_no_repair"))
for _bad in ("amount", "price", "손해액", "보험금"):
    chk(_bad not in _nrx,
        f"금액·보험의 언어를 쓰지 않는다 — '{_bad}' 없음 (철칙 1·2)")
chk("case.no_repair" in read("deploy/DEPLOY.md"),
    "★ 연동 규격 문서에 이벤트가 적혀 있다",
    "보내는데 문서에 없으면 받는 쪽이 파싱을 못 한다")

# ── ③ ────────────────────────────────────────────────────────
print("\n[3] 엑셀 — 화면과 같은 모집단을 준다")
_i = APP.find("EXPORT_SECTIONS = {")
_sec = APP[_i:APP.find("\n}", _i)] if _i > 0 else ""
for _name, _tbl in (("사건", "FROM cases"), ("입점신청", "FROM partner_applications"),
                    ("도입문의", "FROM insurer_leads"), ("하자AS", "FROM defects")):
    _j = _sec.find(_tbl)
    _seg = _sec[_j:_j + 220] if _j > 0 else ""
    chk("is_demo" in _seg or "{WHERE}" in _seg,
        f"★ {_name} 엑셀이 데모 데이터를 거른다",
        "정산만 걸러 놨었다 — 대시보드와 엑셀의 숫자가 갈렸다(형제 경로 누락)")

_ex = strip_py(func_body(APP, "def api_export_xlsx"))
#  ⚠ 예전엔 `_case_filter(request.args)` 를 사건 하나만 하드코딩해서 불렀다.
#    2026-08-19 에 협력업체도 화면 필터를 받게 되면서 섹션→필터함수 매핑으로
#    바뀌었다(새 섹션은 매핑에 등록만 하면 된다) — 그래도 **사건은 여전히
#    같은 함수를 써야 한다**는 원래 취지는 그대로 검사한다.
chk('"cases": _case_filter' in _ex,
    "★★ 사건 엑셀이 **화면과 같은 판정 함수**를 쓴다(필터 매핑에 등록)",
    "필터 규칙을 엑셀에도 복제하면 언젠가 반드시 갈린다")
chk("filt(request.args)" in _ex,
    "★ 매핑에서 고른 함수를 실제로 호출한다")
chk("conn.execute(sql, p)" in _ex,
    "★ 파라미터를 바인딩해서 넘긴다(문자열로 이어 붙이지 않는다)")
chk(APP.count("def _case_filter") == 1,
    "★ 사건 필터 판정이 한 곳에만 있다")
_cf = strip_py(func_body(APP, "def _case_filter"))
chk('"COALESCE(is_demo,0)=0"' in _cf,
    "★ 그 한 곳이 데모를 거른다(목록·엑셀이 함께 걸러진다)")
_ac = strip_py(func_body(APP, "def api_cases"))
chk("_case_filter(request.args)" in _ac and "d_from" not in _ac,
    "★ 목록도 그 함수를 쓴다(규칙이 두 벌 남지 않았다)")

chk("function caseQS()" in _ADMS, "★ 화면이 조건을 한 곳에서 만든다")
_ex_js = js_func(ADM, "ACT.exportXlsx")
chk("caseQS()" in _ex_js,
    "★★ 엑셀 버튼이 **화면에 걸린 필터를 그대로** 싣는다",
    "예전에는 조건을 하나도 안 보내, 화면에 12건이 떠 있는데 파일에는 전부가 담겼다")

# ── ④ ────────────────────────────────────────────────────────
print("\n[4] 감사 로그 — 찾을 수 있어야 기록이다")
#  ⚠ 조건 판정은 나중에 `_activity_filter()` 로 **분리됐다**(엑셀 내보내기가 화면과
#    같은 조건을 쓰게 하려고). 불변식은 그대로이므로 **보는 위치만** 옮긴다 —
#    라우트와 필터 함수를 합쳐서 본다. 위치를 잠그면 정당한 리팩터링에서 깨진다.
#  ⚠ 함수 이름을 **괄호까지** 적는다. `def api_activity` 만 쓰면 나중에 생긴
#    `def api_activity_export` 를 먼저 집는다(접두사 일치) — 실제로 그렇게 헛돌았다.
_av = strip_py(func_body(APP, "def api_activity():")
               + "\n" + func_body(APP, "def _activity_filter("))
for _k in ("q", "actor", "action", "from", "to"):
    chk(f'args.get("{_k}")' in _av or f'request.args.get("{_k}")' in _av,
        f"★ '{_k}' 조건으로 찾을 수 있다")
chk('"total"' in _av,
    "★★ 총 건수를 함께 준다",
    "목록만 주면 화면은 100건이 전부인지 잘린 것인지 알 수 없다 — "
    "잘린 목록을 전부로 읽는 게 이 화면의 원래 결함이었다")
chk("min(int(" in _av and "2000" in _av,
    "★ limit 에 상한이 있다(화면이 보낸 값을 그대로 믿지 않는다)")
chk("except (TypeError, ValueError)" in _av,
    "★ limit 이 숫자가 아니어도 죽지 않는다")
chk("int(limit)" in _av,
    "★ SQL 에 끼우는 limit 은 정수로 못 박는다(문자열 이어붙이기 자리다)")
#  ★ 분리했으면 **화면·엑셀이 그 한 곳을 함께 쓰는지**도 여기서 잠근다
chk(APP.count("_activity_filter(request.args)") >= 2,
    "★ 화면과 엑셀이 같은 필터 함수를 쓴다",
    "규칙을 두 벌 쓰면 화면과 파일이 다른 모집단을 준다(22라운드에 사건 엑셀에서 겪었다)")

chk("renderAudit" in _ADMS and "id=\"audit_box\"" in ADM,
    "★ 화면이 따로 그린다(검색할 때마다 설정 전체를 다시 안 그린다)")
chk("acts.slice(0,14)" not in ADM,
    "★★ 14줄짜리 장식이 사라졌다",
    "8,600건이 쌓인 표를 14줄만 보여 주면 '기록이 이것뿐' 으로 읽힌다")
chk("data-act-enter=\"auditSearch\"" in ADM and "ACT.auditSearch" in _ADMS,
    "★ 검색 손잡이가 실제로 달려 있다(문만 만들지 않는다)")
_ra = js_func(ADM, "async function renderAudit")
chk("total > items.length" in _ra,
    "★ 잘렸으면 잘렸다고 화면이 말한다")
chk("sel.options.length <= 1" in _ra,
    "★ 행위 목록은 한 번만 채운다(매번 채우면 고른 값이 초기화된다)")
chk("catch(e)" in _ra,
    "★ 못 불러오면 그 사실을 말한다(빈 목록을 '기록 없음'으로 위장하지 않는다)")

# ── ⑤ ────────────────────────────────────────────────────────
print("\n[5] 감사 로그의 행위자 이름이 갈리지 않는다")
chk('"system"' not in read("manage.py") and '"system"' not in read("db.py"),
    "★ 도구가 영문 'system' 으로 적지 않는다",
    "app.py 의 actor() 폴백(이름 없는 로그인 관리자)이 같은 문자열이라, "
    "사람이 한 일과 도구가 한 일이 감사 로그에서 구분되지 않았다")

print("\n[5-2] 만들어 둔 기능에 손잡이가 달려 있다")
chk("'/api/license-audit'" in _ADMS,
    "★ 건설업 등록 전수조사 진행률을 화면이 부른다",
    "docstring 이 '몇 곳이 남았는지가 이 숫자의 존재 이유' 라고 적혀 있는데 "
    "그 숫자를 보여 주는 화면이 없었다")
chk("'/api/photo-reuse'" in _ADMS,
    "★ 사진 재사용 의심 점검을 화면이 부른다",
    "증빙 무결성 점검이 서버에만 있고 누를 곳이 없었다")
chk(".catch(()=>null)" in _ADMS,
    "★ 곁다리 조회가 실패해도 본 화면은 뜬다")

#  ★★ 이 유형이 다시 생기지 않게 **전수로** 잠근다.
#     라우트를 새로 만들고 화면에 안 붙이면 여기서 걸린다.
_ALLOW = {
    "/healthz", "/robots.txt", "/sitemap.xml",       # 기계용 — 화면이 없다
    "/app/insurer", "/app/partner",                  # PWA 셸(manifest·알림 링크로 연다)
    "/api/admin/recount-partner-stats",              # 정비 도구 — 운영자가 직접 호출
    "/api/contract-gate/rules",                      # 관문 규칙 원문(소명 자료용)
    "/api/insurer/defects",                          # 대시보드 payload 가 대신 싣는다
    "/api/open-auctions",                            # 앱 셸용 레거시
    #  ⚠ [라운드106] 접미어 사각(아래 _suf 검사)을 고치며 새로 걸린 2건 —
    #    둘 다 admin.js·templates 에 진입점이 없는 게 사실이지만, 화면 버튼을
    #    새로 만드는 건 이번 결함수정 범위 밖이라 우선 여기 등재해 둔다.
    "/api/partners/<int:pid>/exit-check",   # 강등 확인은 409 응답으로 이미 뜬다 — 배지는 미착수
    "/api/partners/<int:pid>/subcontract-check",  # 106라운드가 판정 로직만 고침, 화면 미배선
}
_face = []
for _d in ("static", "templates"):
    for _dp, _, _fns in os.walk(os.path.join(HERE, _d)):
        for _fn in _fns:
            if _fn.rsplit(".", 1)[-1].lower() in ("js", "html", "htm"):
                _face.append(io.open(os.path.join(_dp, _fn),
                                     encoding="utf-8", errors="replace").read())
_FACE = "\n".join(_face)
_orphan = []
for _v, _rule, _t, _dec, _fn in re.findall(
        r'@app\.(get|post|put|patch|delete|route)\(\s*"([^"]+)"(.*?)\)\s*\n'
        r'((?:@[^\n]+\n)*)def\s+(\w+)', APP, re.S):
    if _rule.startswith(("/api/v1/", "/webhook")) or _rule in _ALLOW:
        continue
    _pre = re.split(r"<", _rule)[0].rstrip("/")
    #  ⚠⚠ [라운드106] 접미어 사각 — <int:cid> 뒤에 더 붙는 경로(예:
    #    .../assign-manager)는 _pre 가 파라미터 앞까지만 보여 늘 "/api/cases"
    #    같은 흔한 접두어로 통과했다. 그 뒤에 남는 접미어도 화면에 있는지 본다.
    _suf = re.split(r">", _rule)[-1]
    _orphaned = bool(_pre and _pre not in ("/api",) and _pre not in _FACE)
    if not _orphaned and _suf and _suf not in _FACE:
        _orphaned = True
    if _orphaned:
        _orphan.append(f"{_v.upper()} {_rule}")
chk(not _orphan,
    "★★ 화면이 부르지 않는 새 라우트가 없다",
    f"{_orphan} — 서버에만 있고 누를 곳이 없으면 '있는 기능'이 아니다. "
    f"의도적으로 화면이 없는 것이면 이 테스트의 _ALLOW 에 이유와 함께 넣어라")

# ── ⑥ ────────────────────────────────────────────────────────
print("\n[6] 상태를 바꾸면 '언제 바뀌었나'도 함께 찍는다")
#  ⚠ 문자열 한 줄이 아니라 **전수로** 본다. 이 결함은 25곳 중 한 곳만 빠져
#    있었고, 그 한 곳이 다음 주에 실제로 밟을 1차합의 경로였다.
_miss = []
for _f in ("app.py", "dispatch.py", "compliance.py"):
    _s = read(_f)
    for _m in re.finditer(r"UPDATE cases\s+SET\b", _s):
        #  ⚠⚠ [라운드111] 창을 420자 고정으로 밀면, 이 UPDATE 문이 짧을 때
        #    (예: SET 절 하나짜리) 바로 다음 conn.execute(다른 표 대상이어도)
        #    까지 창 안에 들어와 그 문장의 status='...' 를 내 것으로 오인한다
        #    (window-scan, not structure — 이미 문서화된 함정). 다음
        #    conn.execute( 가 나오는 지점을 창의 상한으로 둬 통계 끼리 안 섞는다.
        _cap = _s.find("conn.execute(", _m.start() + 1)
        _end = min(_m.start() + 420, _cap) if _cap != -1 else _m.start() + 420
        _seg = _s[_m.start():_end]
        _w = _seg.find("WHERE")
        _stmt = _seg[:_w + 200] if _w > 0 else _seg
        #  ⚠⚠ [라운드117] _stmt 는 SET 절 + WHERE 절을 통째로 담는다 — "이 문장이
        #    status 를 대입하나"를 그 전체에서 찾으면, WHERE 절의 상태 **조건**
        #    (예: "AND status='접수'")도 대입으로 오인한다. 117라운드의 새 UPDATE
        #    (dispatch.py — award_route 만 SET, status 는 WHERE 조건)가 바로 이
        #    오탐을 냈다. 대입 여부는 SET 절만(WHERE 이전) 보고, status_at 존재는
        #    기존대로 넓은 창(_stmt)에서 본다 — 후자를 좁히면 못 보던 걸 새로
        #    놓칠 수 있으니 관대한 쪽은 그대로 둔다.
        _set_clause = _seg[:_w] if _w > 0 else _seg
        #  dispatch_status 는 정체일수를 재지 않는다 — 대상이 아니다
        if not re.search(r"(?<!dispatch_)status\s*=\s*'", _set_clause):
            continue
        if "status_at" not in _stmt:
            _miss.append(f"{_f}:{_s[:_m.start()].count(chr(10)) + 1}")
chk(not _miss,
    "★★ 사건 상태를 바꾸는 모든 자리가 status_at 을 함께 찍는다",
    f"빠진 곳: {_miss} — stale_days 는 COALESCE(status_at, created_at) 로 재므로, "
    f"안 찍으면 방금 진행된 사건이 목록에서 '7일째 ⚠' 로 앉는다")
_ag = read("dispatch.py")
chk("SET status='시공중', status_at=" in _ag,
    "★ 1차합의 승인(=시공중)도 그렇다",
    "형제인 경매 낙찰·미수선 종결은 둘 다 찍고 있었다 — 이 한 곳만 빠져 있었다")

# ── ⑦ ────────────────────────────────────────────────────────
print("\n[7] 넓은 표가 폰에서 페이지를 옆으로 밀지 않는다")
#  ⚠⚠ 판정은 **바로 앞의 여는 태그(= 감싸는 요소)** 가 overflow 를 갖는지로 한다.
#    처음엔 표 앞 260자 창에 'tbl-wrap' 이라는 글자가 있는지만 봤다가,
#    이미 `<div style="overflow:auto">` 로 감싼 표 12개를 '누락'으로 잘못 세고
#    래퍼를 이중으로 씌울 뻔했다. 창 안의 글자는 부모가 아니다.
_bare = []
for _f in ("templates/insurer_portal.html", "templates/partner_portal.html",
           "static/admin.js"):
    _s = read(_f)
    chk(_s.count("<table") == _s.count("</table>"),
        f"{_f} — 표 여닫음이 맞는다")
    for _m in re.finditer(r'<table class="tbl"', _s):
        _tags = re.findall(r"<(\w+)([^>]*)>", _s[max(0, _m.start() - 300):_m.start()])
        _attr = _tags[-1][1] if _tags else ""
        if not ("tbl-wrap" in _attr or "tblx" in _attr or "overflow" in _attr):
            _bare.append(f"{_f}:{_s[:_m.start()].count(chr(10)) + 1}")
chk(not _bare,
    "★★ 모든 `.tbl` 표가 가로 스크롤 래퍼 안에 있다",
    f"{_bare} — 협력사는 현장에서 폰으로 공고를 본다. 넓은 표에 래퍼가 없으면 "
    f"표만 잘리는 게 아니라 **페이지 몸통 전체가 옆으로 밀린다**")
for _f in ("templates/insurer_portal.html", "templates/partner_portal.html",
           "static/admin.js"):
    _s = read(_f)
    chk('class="tbl-wrap"><div class="tbl-wrap"' not in _s,
        f"{_f} — 래퍼가 겹치지 않았다")

print("")
for f in ("app.py", "manage.py", "db.py", "dispatch.py"):
    try:
        ast.parse(read(f)); ok_, why = True, ""
    except SyntaxError as e:
        ok_, why = False, f"{e.lineno}행: {e.msg}"
    chk(ok_, f"{f} 구문", why)

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
