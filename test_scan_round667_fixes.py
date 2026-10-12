# -*- coding: utf-8 -*-
"""스캔 667라운드 회귀(직접조사, 하위위임 없음) — 보험사 월 정산 명세서 화면(관리자
콘솔·보험사 포털 둘 다)의 기본 선택 월이 여태 '이번 달'이었던 결함.

  왜 결함인가 —
    서버 _stmt_period_args()(app.py, round564)는 자기 문서에 "?year=&month= 파싱 —
    없으면 지난달"이라 적어 두고 실제로도 그렇게 계산한다(정산은 마감 다음 달에
    뽑는 것이 정상 업무 흐름이라는 뜻 — 진행 중인 달은 아직 정산이 안 끝나 미완성
    숫자다). 그런데 round564 자신의 회귀설명이 이미 "어드민·보험사 포털 화면은
    <select> 로 매번 year·month 를 명시적으로 붙여 보내 평소엔 이 기본값 경로를
    안 탄다"고 못박아 뒀다 — 즉 그 서버 기본값은 두 화면의 실제 사람 클릭 경로에서는
    "단 한 번도" 실행되지 않는다(오직 파라미터 없이 호출하는 회귀테스트·raw API
    호출자만 혜택을 본다). 실제로 화면을 열면:
      · static/admin.js STMT 초기값 = new Date().getFullYear()/getMonth()+1 (이번 달)
      · templates/insurer_portal.html 의 두 <select> 도 같은 이유로 이번 달을 기본
        선택(연도 select 는 심지어 selected 속성 자체가 없어 "목록 첫 값 = 오늘 연도"
        라는 암묵적 가정에만 기댔다 — 1월에 열면 월은 지난달 12월을 정확히 계산해도
        연도 select 는 여전히 올해를 보여줄 뻔한 별도의 잠재 결함)
      · stmtExport()/stmtRead()/ACT.insStmtExport() 는 그 값을 그대로 읽어 항상
        명시 파라미터로 보낸다 — 서버의 "없으면 지난달" 폴백은 절대 안 걸린다.
    결과: 담당자·보험사 둘 다 이 화면을 열 때마다 아직 안 끝난 이번 달의 미완성
    숫자를 먼저 보고(값 0 또는 소량), 수동으로 달을 한 칸 내려야만 round564 가
    의도한 "지난달" 명세를 본다 — round564 가 고치려던 바로 그 문제(미완성 숫자를
    '월 정산 명세서'라는 이름으로 내보냄)가 실제 사용 경로에서는 여전히 매번
    재현된다.

  고침 — 단일 근본원인 수정 두 곳(공유 프론트엔드 모듈이 따로 없어 화면마다 이미
    자기 몫의 todayKST() 를 복제해 갖고 있는 이 저장소 관례를 그대로 따른다 —
    admin.js·partner_portal.html 이미 각자 todayKST() 를 갖고 있던 것과 같은 패턴):
      · static/admin.js: STMT 초기값·stmtRead() 폴백을 todayKST() 기반 지난달
        계산(_lastY/_lastM)으로 교체.
      · templates/insurer_portal.html: RENDER.settle() 안에서 같은 계산(lastY/lastM)을
        하고, 두 <select> 모두 그 값을 selected 기준으로 삼도록 교체(연도 select 에
        처음으로 명시적 selected 부여 — 위 잠재 결함도 함께 닫힘). ACT.insStmtExport()
        의 방어적 폴백(select 를 못 찾을 때만 쓰는 값)도 같은 계산으로 교체.
    서버 _stmt_period_args() 자체는 건드리지 않는다 — 명시 ?year=&month= 우선순위는
    그대로이므로 사용자가 직접 달을 바꾸는 기존 동작은 회귀 없음.

  회귀테스트(26개 검사) —
    [1] 소스: 두 파일에서 옛(이번 달 기준) 패턴이 사라지고 todayKST() 기반 지난달
        계산이 정확히 그 자리에 있음을 실제 파일 텍스트로 확인. app.py 의
        _stmt_period_args() 는 이번 라운드가 손대지 않았음도 함께 확인.
    [2] 실행 — admin.js 에서 그대로 뽑은 실제 코드를 node 로 실행해, 평범한 달·
        연도경계(1월) 두 시나리오에서 정확히 '지난달'을 계산함을 확인.
    [3] 실행 — insurer_portal.html RENDER.settle() 에서 그대로 뽑은 실제 <select>
        템플릿 식을 node 로 실행해, 렌더된 HTML 문자열에서 실제로 지난달·해당 연도
        옵션에만 selected 가 붙고 이번 달/이번 해에는 안 붙음을 확인.
    [4] 되돌리기-증명 — round667 이전 원문(브라우저 로컬시각 그대로 쓰는 옛 코드)을
        실제 파일은 전혀 건드리지 않고 독립 문자열로 재구성해 같은 시나리오에
        돌려보면, 옛 코드는 '이번 달'(1월 시나리오면 연도 select 는 selected 자체가
        없음)을 기본값으로 골라 실제 증상이 재현됨을 확인 — 지금(고친) 코드와의
        인과관계 대조.

  admin.js·insurer_portal.html(templates/*.html) 변경이므로 test_template_js.py 를
  표준대로 별도 재실행해 인라인 JS 파싱을 확인한다(이 파일 자체는 그 표준 검사를
  대신하지 않는다 — 이 파일은 '기본값 계산이 실제로 맞는가'만 본다).
  API 라우트·DB 스키마·app.py 무변경 — 서버 재기동은 정적 자산만 반영하면 되므로
  선택사항이지만(BUILD_HASH 는 static/templates 를 해시하므로 로테이션은 예상됨),
  이 회귀 자체는 재기동 여부와 무관하게 파일 텍스트만으로 검증된다.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 66)
print("  스캔 667라운드 회귀 — 월 정산 명세서 기본 선택월(지난달) 검사")
print("=" * 66)

with open(os.path.join(HERE, "static", "admin.js"), encoding="utf-8") as f:
    ADMIN_JS = f.read()
with open(os.path.join(HERE, "templates", "insurer_portal.html"), encoding="utf-8") as f:
    INS_HTML = f.read()
with open(os.path.join(HERE, "app.py"), encoding="utf-8") as f:
    APP_PY = f.read()

# ── [1] 소스 검사 ────────────────────────────────────────────────
# admin.js 의 실제 새 코드 — 이 정확한 문자열이 파일에 있어야 하고,
# 뒤에서 이 그대로 뽑아 node 로 실행한다([2]).
ADMIN_NEW_INIT = (
    "const [_ty, _tm] = todayKST().split('-').map(Number);\n"
    "const _lastY = _tm === 1 ? _ty - 1 : _ty, _lastM = _tm === 1 ? 12 : _tm - 1;\n"
    "let STMT = {insurer_id:'', year:_lastY, month:_lastM};"
)
chk(ADMIN_NEW_INIT in ADMIN_JS,
    "admin.js: STMT 초기값이 todayKST() 기반 지난달 계산을 쓴다")
chk("STMT.year = ($('#st_year')||{}).value || _lastY;" in ADMIN_JS
    and "STMT.month = ($('#st_month')||{}).value || _lastM;" in ADMIN_JS,
    "admin.js: stmtRead() 폴백도 같은 지난달 값을 쓴다")
chk("_now.getFullYear(), month:_now.getMonth()+1" not in ADMIN_JS,
    "admin.js: STMT 초기값이 더는 '이번 달'(브라우저 로컬시각)을 안 쓴다")
chk("const _now = new Date();" not in ADMIN_JS,
    "admin.js: 옛 _now(브라우저 로컬시각) 선언 자체가 사라졌다")
chk("new Date().getFullYear()" not in ADMIN_JS and "new Date().getMonth()" not in ADMIN_JS,
    "admin.js: 이 화면 어디에도 브라우저 로컬시각 기반 연/월 계산이 안 남았다")

# insurer_portal.html 의 실제 새 코드(RENDER.settle() 안, 2칸 들여쓰기 그대로)
INS_NEW_CALC = (
    "  const [_ty, _tm] = todayKST().split('-').map(Number);\n"
    "  const lastY = _tm === 1 ? _ty - 1 : _ty, lastM = _tm === 1 ? 12 : _tm - 1;"
)
chk(INS_NEW_CALC in INS_HTML,
    "insurer_portal.html: RENDER.settle() 이 todayKST() 기반 지난달 계산을 한다")
INS_YEAR_SELECT = ('${[0,1,2].map(k=>{const y=_ty-k;return `<option value="${y}" '
                    "${y===lastY?'selected':''}>${y}년</option>`;}).join('')}")
INS_MONTH_SELECT = ("${Array.from({length:12},(_,i)=>i+1).map(m=>`<option value=\"${m}\" "
                     "${m===lastM?'selected':''}>${m}월</option>`).join('')}")
chk(INS_YEAR_SELECT in INS_HTML,
    "insurer_portal.html: 연도 <select> 가 lastY 를 selected 기준으로 쓴다(옛 코드엔 selected 자체가 없었다)")
chk(INS_MONTH_SELECT in INS_HTML,
    "insurer_portal.html: 월 <select> 가 lastM 을 selected 기준으로 쓴다")
chk("(new Date().getMonth()+1)===m)?'selected'" not in INS_HTML,
    "insurer_portal.html: 월 select 가 더는 '이번 달'(브라우저 로컬시각) 기준이 아니다")
chk("const y=new Date().getFullYear()-k;" not in INS_HTML,
    "insurer_portal.html: 연도 select 옵션 목록도 더는 브라우저 로컬시각 기준이 아니다")
INS_EXPORT_FALLBACK = (
    "const [_fy, _fm] = todayKST().split('-').map(Number);\n"
    "    const _flastY = _fm === 1 ? _fy - 1 : _fy, _flastM = _fm === 1 ? 12 : _fm - 1;\n"
    "    var y = (document.getElementById('ins_st_year') || {}).value || _flastY;\n"
    "    var m = (document.getElementById('ins_st_month') || {}).value || _flastM;"
)
chk(INS_EXPORT_FALLBACK in INS_HTML,
    "insurer_portal.html: ACT.insStmtExport() 의 방어적 폴백도 같은 지난달 계산을 쓴다")
chk("new Date().getFullYear()" not in INS_HTML and "new Date().getMonth()" not in INS_HTML,
    "insurer_portal.html: 이 화면 어디에도 브라우저 로컬시각 기반 연/월 계산이 안 남았다")

# 서버 쪽(round564) 은 이번 라운드가 손대지 않았다 — 그대로 남아 있어야 프런트가
# 그 계약(명시 파라미터 우선·생략 시 지난달)을 정확히 재사용하는 것이 된다.
chk("last = now.replace(day=1) - timedelta(days=1)" in APP_PY,
    "app.py: _stmt_period_args() 의 round564 '없으면 지난달' 로직은 이번 라운드가 안 건드렸다(그대로 재사용 대상)")
chk("def _stmt_period_args():" in APP_PY,
    "app.py: _stmt_period_args() 자체는 여전히 존재한다(삭제·개명 없음)")

NODE = shutil.which("node")
if not NODE:
    print("\n  node 를 찾을 수 없어 [2]~[4](실행·되돌리기 검사)를 건너뜁니다 — 실패로 답합니다"
          "(test_template_js.py 와 같은 원칙: '검사 안 함'과 '통과'는 다르다).")
    FAIL.append(("node 실행 파일 없음", "node --version 확인 필요"))
else:
    # ── JS 실행 하네스 — [2][3][4] 를 전부 이 안에서 한다 ──────────
    #  ⚠ ADMIN_NEW_INIT·INS_NEW_CALC·INS_YEAR_SELECT·INS_MONTH_SELECT·
    #    INS_EXPORT_FALLBACK 는 방금 위에서 "실제 파일 안에 이 문자열 그대로 있다"를
    #    확인한 바로 그 문자열이다 — 그대로 이어 붙여 node 로 돌리므로 재구현이 아니라
    #    실제 배포 코드를 실행하는 것이다. [4]의 '옛' 버전만 이 스크립트 안의 독립
    #    문자열로 손으로 재구성한다(실제 파일은 전혀 안 건드린다).
    harness = r"""
'use strict';
const RESULTS = [];
function chk(cond, name) { RESULTS.push([name, !!cond]); }
function mockTodayKST(dateStr) { return () => dateStr; }

// ══════ [2] admin.js 실제 코드 그대로 실행 ══════
function newAdminStmtDefault(todayKST) {
""" + ADMIN_NEW_INIT + r"""
  return STMT;
}
let r;
r = newAdminStmtDefault(mockTodayKST('2026-09-16'));
chk(r.year === 2026 && r.month === 8, "[2] admin.js 실제코드: 2026-09-16(KST) -> 지난달 2026년 8월");
r = newAdminStmtDefault(mockTodayKST('2026-01-05'));
chk(r.year === 2025 && r.month === 12, "[2] admin.js 실제코드: 2026-01-05(KST, 연도경계) -> 지난달 2025년 12월");
r = newAdminStmtDefault(mockTodayKST('2026-12-31'));
chk(r.year === 2026 && r.month === 11, "[2] admin.js 실제코드: 2026-12-31(KST) -> 지난달 2026년 11월");

// ══════ [3] insurer_portal.html 실제 <select> 템플릿 식 그대로 실행 ══════
function newInsurerSelectHtml(todayKST) {
""" + INS_NEW_CALC + r"""
  const yearSelect = `""" + INS_YEAR_SELECT + r"""`;
  const monthSelect = `""" + INS_MONTH_SELECT + r"""`;
  return {yearSelect, monthSelect};
}
let s;
s = newInsurerSelectHtml(mockTodayKST('2026-09-16'));
chk(s.yearSelect.includes('<option value="2026" selected>2026년</option>'),
    "[3] insurer_portal.html 실제 select: 2026-09-16 -> 연도 select 가 2026년을 selected");
chk(s.monthSelect.includes('<option value="8" selected>8월</option>'),
    "[3] insurer_portal.html 실제 select: 2026-09-16 -> 월 select 가 8월을 selected");
chk(!s.monthSelect.includes('<option value="9" selected>9월</option>'),
    "[3] insurer_portal.html 실제 select: 9월(이번달)은 selected 아님");

s = newInsurerSelectHtml(mockTodayKST('2026-01-05'));
chk(s.yearSelect.includes('<option value="2025" selected>2025년</option>'),
    "[3] insurer_portal.html 실제 select: 2026-01-05(연도경계) -> 연도 select 가 2025년을 selected");
chk(s.monthSelect.includes('<option value="12" selected>12월</option>'),
    "[3] insurer_portal.html 실제 select: 2026-01-05(연도경계) -> 월 select 가 12월을 selected");
chk(!s.yearSelect.includes('<option value="2026" selected>2026년</option>'),
    "[3] insurer_portal.html 실제 select: 연도경계에서 이번해(2026)는 selected 아님");

// ══════ [4] 되돌리기-증명 — round667 이전 원문을 독립 문자열로만 재구성 ══════
//  실제 static/admin.js · templates/insurer_portal.html 파일은 이 블록에서 전혀
//  건드리지 않는다 — 옛 `_now`(브라우저 로컬시각 Date) 자리만 인자로 흉내낸다.
function oldAdminStmtDefault(fakeLocalYear, fakeLocalMonth0based) {
  const _now = { getFullYear: () => fakeLocalYear, getMonth: () => fakeLocalMonth0based };
  let STMT = {insurer_id:'', year:_now.getFullYear(), month:_now.getMonth()+1};
  return STMT;
}
function oldInsurerSelectHtml(fakeLocalYear, fakeLocalMonth0based) {
  const _now = { getFullYear: () => fakeLocalYear, getMonth: () => fakeLocalMonth0based };
  const yearSelect = [0,1,2].map(k=>{const y=_now.getFullYear()-k;return `<option value="${y}">${y}년</option>`;}).join('');
  const monthSelect = Array.from({length:12},(_,i)=>i+1).map(m=>`<option value="${m}" ${((_now.getMonth()+1)===m)?'selected':''}>${m}월</option>`).join('');
  return {yearSelect, monthSelect};
}
// 시나리오: 브라우저 로컬시각이 2026년 1월(0-based getMonth()=0) — [2]/[3]의
// '2026-01-05' 시나리오와 같은 순간을 가리킨다. 지금(고친) 코드는 그 순간
// {year:2025, month:12} 를 골랐다(위 확인) — 옛 코드가 정말 다른 값을 고르는지 대조한다.
const oldR = oldAdminStmtDefault(2026, 0);
chk(oldR.year === 2026 && oldR.month === 1,
    "[4] 되돌리기 대조: 옛(수정 전) admin.js 로직은 같은 순간에 '이번 달'(2026년 1월)을 기본값으로 골랐다 (실제 증상 재현, 신규 코드=2025년 12월과 대조)");
const oldS = oldInsurerSelectHtml(2026, 0);
chk(oldS.monthSelect.includes('<option value="1" selected>1월</option>'),
    "[4] 되돌리기 대조: 옛 insurer_portal.html select 도 같은 순간 1월(이번달)을 selected 로 골랐다 (실제 증상 재현)");
chk(!oldS.yearSelect.includes('selected'),
    "[4] 되돌리기 대조: 옛 연도 select 는 selected 속성 자체가 없었다(목록 첫 값=오늘 연도라는 암묵적 가정에만 의존 — 별도 잠재 결함)");

console.log(JSON.stringify(RESULTS));
process.exit(RESULTS.some(([, ok]) => !ok) ? 1 : 0);
"""
    tmpdir = tempfile.mkdtemp(prefix="bokguon_round667_")
    hpath = os.path.join(tmpdir, "harness.js")
    try:
        with open(hpath, "w", encoding="utf-8") as f:
            f.write(harness)
        proc = subprocess.run([NODE, hpath], capture_output=True, text=True, encoding="utf-8")
        out_lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        json_line = out_lines[-1] if out_lines else ""
        try:
            js_results = json.loads(json_line)
        except (json.JSONDecodeError, IndexError):
            js_results = None
        if js_results is None:
            chk(False, "node 하네스 실행 및 결과 파싱",
                f"returncode={proc.returncode} stdout={proc.stdout[:500]!r} stderr={proc.stderr[:500]!r}")
        else:
            for name, ok in js_results:
                chk(bool(ok), name)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

print(f"\n  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}  {dt}")
print("=" * 66)
sys.exit(1 if FAIL else 0)
