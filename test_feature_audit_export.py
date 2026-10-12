# -*- coding: utf-8 -*-
"""[기능] 감사 로그 엑셀 + 사건 전체 이력 리포트 — 회귀.

  왜 만들었나 —
    감사 로그는 분쟁 때 근거다. 22라운드에 **찾을 수 있게** 만들었지만 화면 조회뿐이라
    상대에게 건네거나 결재에 붙일 수 없었다. 그리고 "이 사건 어떻게 흘러갔나" 를
    한 장으로 뽑을 수단이 없어, 사건 상세·타임라인·감사 로그 세 곳을 오가며
    사람이 짜맞춰야 했다 — 분쟁이 났을 때 가장 급한 일인데.

  지켜야 할 성질 —
    ① **화면과 파일이 같은 조건을 쓴다.** 22라운드에 사건 엑셀이 필터를 하나도
       안 받아 화면과 다른 모집단을 주는 결함을 고쳤다. 판정을 `_activity_filter()`
       한 곳에 두고 둘이 공유한다 — 규칙을 두 벌 쓰면 언젠가 반드시 갈린다.
       실측: 5가지 조건에서 화면 건수 = 엑셀 행수(10,063 / 1,386 / 484 / 6,835 / 0).
    ② **잘렸으면 파일 안에 적는다.** 파일만 받은 사람은 화면을 못 본다 —
       잘린 파일을 전부로 읽는 것이 가장 위험하다.
    ③ **내보낸 사실도 감사 로그에 남긴다.** 누가 언제 무엇을 뽑아 갔는지가
       개인정보 취급 이력이다.
    ④ **이력 리포트에 경쟁 입찰가를 넣지 않는다**(철칙 4). 이 문서는 발주처나
       상대방에게 그대로 건네질 수 있다.

      python test_feature_audit_export.py
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
TPL = read("templates/case_history.html")

print("═" * 70)
print("  기능 회귀 — 감사 로그 엑셀 · 사건 전체 이력")
print("═" * 70)

print("\n[1] 화면과 파일이 같은 조건을 쓴다")
chk(APP.count("def _activity_filter") == 1, "★ 필터 판정이 한 곳에만 있다")
_v = func_src(APP, "def api_activity()")
_x = func_src(APP, "def api_activity_export")
chk("_activity_filter(request.args)" in _v, "★★ 화면이 그 함수를 쓴다")
chk("_activity_filter(request.args)" in _x, "★★ 엑셀도 **같은 함수**를 쓴다",
    "22라운드에 사건 엑셀이 필터를 안 받아 화면과 다른 모집단을 줬다 — 같은 실수를 "
    "반복하지 않으려고 판정을 한 곳에 뒀다")
#  ★ 화면 쪽에 옛 필터 코드가 남아 있지 않은지(두 벌이 되면 갈린다)
chk('actor_q = (request.args.get("actor")' not in _v,
    "★ 화면 쪽에 옛 필터 코드가 남지 않았다")
_e = js_func(ADM, "ACT.auditExport =")
for k in ("q", "action", "from", "to"):
    chk(f"qs.set('{k}'" in _e, f"★ 화면이 '{k}' 조건을 실어 보낸다")
chk("limit" not in _e,
    "★ limit 은 안 싣는다(파일은 화면보다 넉넉히 담는다)")

print("\n[2] 잘렸으면 파일 안에 적는다")
chk("상한에 걸려 잘렸습니다" in _x,
    "★★ 잘린 사실을 **파일 안에** 쓴다",
    "파일만 받은 사람은 화면을 못 본다 — 잘린 파일을 전부로 읽는 것이 가장 위험하다")
chk("total > len(data)" in _x, "★ 잘렸을 때만 그 문구를 넣는다")
chk("조건에 맞는" in _x, "★ 전체 건수와 담긴 건수를 함께 적는다")
chk("min(int(request.args.get(\"max\")" in _x, "★ 상한이 있다(무한이 아니다)")
chk("except (TypeError, ValueError)" in _x, "★ max 가 숫자가 아니어도 죽지 않는다")

print("\n[3] 내보낸 사실이 남는다")
chk('DB.log(conn, actor(), "감사로그 내보내기"' in _x,
    "★★ 누가 언제 무엇을 뽑아 갔는지 남는다",
    "감사 로그를 통째로 받아 가는 것은 개인정보 취급 행위다")
chk("conn.commit()" in _x, "★ 그 기록이 확정된다")
chk("_xl_safe(" in _x,
    "★ 셀 정제를 거친다(제어문자 하나로 500 이 나지 않게)")
chk('filename="bokguon_audit_' in _x,
    "★ 파일명이 ASCII 다(한글 파일명은 브라우저마다 깨진다)")
chk("freeze_panes" in _x, "★ 머리글이 고정된다(수천 행을 훑는 문서다)")

print("\n[4] 사건 전체 이력 리포트")
chk('"/report/case/<int:cid>"' in APP, "★ 라우트가 있다")
_r = func_src(APP, "def case_history_report")
chk("require_role" in APP[APP.find('"/report/case/<int:cid>"'):
                          APP.find("def case_history_report")],
    "★ 권한 게이트가 있다(공개 문서가 아니다)")
chk("abort(404)" in _r, "★ 없는 사건은 404")
chk("detail LIKE ?" in _r and "case_no" in _r,
    "★ 그 사건의 감사 로그를 모은다(접수번호가 detail 에 들어간다)")
chk("ORDER BY id" in _r and "DESC" not in _r.split("activity_log")[1][:120],
    "★★ **시간순**으로 준다(이력은 흐름이다)")
chk('DB.log(conn, actor(), "사건 이력 리포트"' in _r,
    "★ 이 문서를 뽑은 사실도 남는다")
chk("COALESCE(void_status,'') <> '취소'" in _r,
    "★ 취소된 정산을 현재 정산으로 보여 주지 않는다")

print("\n[5] 그 문서에 넣으면 안 되는 것 (철칙 4)")


def _no_comment_py(t):
    """`#` 주석과 docstring 을 지운다.

    ⚠ 안 지우면 **"경쟁 입찰가는 넣지 않는다" 는 안전장치 주석 자체**가
      금칙어로 걸린다. 이 프로젝트에서 이미 세 번 겪은 실수다.
    """
    t = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', " ", t)
    return "\n".join(l for l in t.splitlines() if not l.strip().startswith("#"))


def _no_comment_jinja(t):
    """Jinja 주석 `{# … #}` 과 CSS 주석 `/* … */` 을 지운다."""
    t = re.sub(r"\{#[\s\S]*?#\}", " ", t)
    return re.sub(r"/\*[\s\S]*?\*/", " ", t)


_rc = _no_comment_py(_r)
for bad in ("bids", "입찰가", "경쟁"):
    chk(bad not in _rc, f"★ 서버가 경쟁 정보를 안 모은다 — '{bad}' 없음")
_tc = _no_comment_jinja(TPL)
for bad in ("입찰가", "경쟁사", "최저가"):
    chk(bad not in _tc, f"★ 문서 서식에 없다 — '{bad}'")
chk("보험금 지급액이나 손해액이 아니며" in TPL,
    "★★ 금액의 성격을 문서가 스스로 밝힌다 (철칙 1·2)",
    "이 문서는 발주처·상대방에게 건네진다 — 시공 도급 금액임을 명시해야 한다")
chk("복구온은 금액을 확정·협상하지 않습니다" in TPL, "★ 우리 역할도 적는다")
chk("사후 편집 기능이 없습니다" in TPL,
    "★ 기록의 성격을 밝힌다(분쟁 문서의 신뢰 근거)")

print("\n[6] 화면에 손잡이가 있다")
chk('data-act="auditExport"' in ADM, "★ 감사 로그 엑셀 버튼")
chk(ADM.count("ACT.auditExport =") == 1, "★ 핸들러가 하나만 등록된다")
chk('href="/report/case/${id}"' in ADM, "★ 사건 상세에 이력 리포트 링크")
chk('rel="noopener"' in ADM, "★ 새 탭에 opener 를 안 넘긴다")

print("")
try:
    ast.parse(APP); _ok, _why = True, ""
except SyntaxError as e:
    _ok, _why = False, f"{e.lineno}행: {e.msg}"
chk(_ok, "app.py 구문", _why)
chk(TPL.count("{%") == TPL.count("%}"),
    "case_history.html 태그 균형", f"{TPL.count('{%')} / {TPL.count('%}')}")
chk("{{ csp_nonce }}" in TPL, "★ 인라인 style 에 nonce 가 있다(CSP)")

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
