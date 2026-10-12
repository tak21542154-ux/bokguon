# -*- coding: utf-8 -*-
"""16라운드 회귀 — **폰에서 실제로 눌러 보고** 나온 것.

  협력사는 현장에서 폰으로 쓴다. 375px 에서 탭바는 856px 라 뒤쪽 6개가 화면 밖인데,
  탭을 눌러도 탭바가 따라오지 않아 **본문은 바뀌고 탭바는 엉뚱한 곳을 가리켰다** —
  기사는 지금 어디인지도, 돌아가는 길도 몰랐다.
  하필 현장에서 제일 많이 쓰는 '시공 현장·사진'과 '정산'이 화면 밖이다.

  ⚠ 이건 코드를 읽어서는 안 나온다. 뷰포트를 375 로 놓고 **실제로 눌러 봐야**
    보인다(브라우저에서 탭 11개를 다 눌러 확인했다).

      python test_scan_round16_fixes.py
"""
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


def js_show(src):
    """`function show(v){` 부터 닫는 중괄호까지 — 창을 글자수로 자르지 않는다."""
    i = src.find("function show(v){")
    if i < 0:
        return ""
    depth, j = 0, src.find("{", i)
    k = j
    while k < len(src):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
        k += 1
    return src[i:i + 2000]


print("═" * 70)
print("  16라운드 회귀 — 폰에서 탭바가 따라오는가")
print("═" * 70)

print("\n[1] 탭을 누르면 탭바가 그 탭까지 따라온다")
for tpl, label, n_tab in (("templates/partner_portal.html", "협력사 포털", 11),
                          ("templates/insurer_portal.html", "발주처 포털", 8)):
    body = js_show(read(tpl))
    chk(bool(body), f"{label} — show() 를 찾았다")
    chk("scrollIntoView" in body,
        f"★ {label} — 활성 탭을 탭바 안으로 끌어온다",
        f"폰(375px)에서 탭 {n_tab}개가 화면보다 넓다. 활성 표시만 바꾸면 "
        f"본문은 바뀌는데 탭바는 엉뚱한 곳을 가리켜, 지금 어디인지 알 수 없다")
    chk("inline:'center'" in body.replace(" ", "") or "inline: 'center'" in body,
        f"★ {label} — 가운데로 끌어온다(끝에 붙이면 다음 탭이 안 보인다)")
    chk("block:'nearest'" in body.replace(" ", "") or "block: 'nearest'" in body,
        f"★ {label} — 세로 스크롤은 건드리지 않는다(block:nearest)",
        "block 기본값(start)이면 페이지가 위아래로 튄다")

print("\n[2] 탭바가 가로 스크롤 컨테이너 안에 있다")
for tpl, label in (("templates/partner_portal.html", "협력사 포털"),
                   ("templates/insurer_portal.html", "발주처 포털")):
    src = read(tpl)
    #  ⚠ 규칙은 `.pnav .tabs{…}` 로 **미디어쿼리 안**에 있다. `\.tabs\s*\{` 로
    #    첫 매치만 보면 데스크톱용 `display:flex` 규칙이 잡혀 "overflow 없다"고
    #    말한다 — 멀쩡한 CSS 를 결함으로 읽는다(실제로 그랬다).
    #    `.tabs` 를 포함하는 **모든** 규칙 중 하나라도 가로 스크롤이면 통과다.
    rules = re.findall(r"[^{}]*\.tabs[^{}]*\{[^}]*\}", src, re.S)
    hit = [r for r in rules if "overflow-x" in r.replace(" ", "")]
    chk(bool(hit),
        f"★ {label} — .tabs 에 가로 스크롤 규칙이 있다({len(rules)}개 규칙 중 {len(hit)}개)",
        "없으면 화면 밖 탭은 아예 못 누른다(있는데 없는 메뉴가 된다)")

print("\n[3] 업로드 큐가 계정별로 갈린다(폰 한 대를 두 업체가 쓴다)")
UPQ = read("static/upqueue.js")
chk("who" in UPQ and "setWho" in UPQ,
    "★ 큐에 '누가 넣었는지'가 함께 저장된다")
chk("who: UPQ.who" in UPQ,
    "★ 넣을 때 그 값을 실제로 기록한다",
    "setWho 만 있고 기록을 안 하면 격리가 되지 않는다")

APP = read("app.py")
ADM = read("static/admin.js")
PAR = read("templates/partner_portal.html")


def strip_py(t):
    return "\n".join(ln for ln in t.splitlines() if not ln.strip().startswith("#"))


def strip_js(t):
    import re as _re
    t = _re.sub(r"(?<![A-Za-z0-9_\"'])/\*.*?\*/", " ", t, flags=_re.S)
    return "\n".join(ln for ln in t.splitlines() if not ln.strip().startswith("//"))


print("\n[4] 0행 UPDATE 가 트랜잭션을 열어 둔 채 남지 않는다")
_i = APP.find("def sweep_report_overdue")
_j = APP.find("\ndef ", _i + 1)
seg = strip_py(APP[_i:_j if _j > 0 else len(APP)])
chk("conn.rollback()" in seg,
    "★ 한 일이 없으면 명시적으로 되돌린다",
    "실측(Python 3.14.6·SQLite 3.50.4): rowcount=0 인 UPDATE 도 in_transaction=True 가 "
    "되고, 다른 연결이 'database is locked' 로 막힌다. 조건부 커밋만 두면 "
    "같은 conn 으로 이어 도는 스윕이 그 트랜잭션 안에서 돌고 쓰기가 막힌다")

print("\n[5] 무효·재경매 입찰이 '내 입찰'로 보이지 않는다")
_k = APP.find("my_bid = one(conn.execute")
seg = strip_py(APP[_k:_k + 900]) if _k > 0 else ""
chk("b.voided_at IS NULL" in seg,
    "★ 무효 처리된 입찰을 뺀다",
    "낙찰취소로 재공고되면 그 입찰은 voided 된다. 상세만 그걸 현재 입찰로 보여 줘, "
    "협력사가 '인하만 가능'이라 믿고 실제보다 불리한 금액을 냈다")
chk("a.change_order_id IS NULL" in seg,
    "★ 원경매만 본다(변경견적 재경매 입찰이 섞이지 않는다)")

print("\n[6] 관리자 낙찰이 변경견적 경매까지 뒤집지 않는다")
_a = APP.find("def api_case_award")
seg = strip_py(APP[_a:_a + 3000]) if _a > 0 else ""
chk("change_order_id IS NULL" in seg,
    "★ 원경매 행만 '낙찰' 로 닫는다",
    "형제인 보험사 낙찰 라우트에는 이 필터가 있다 — 없으면 진행 중이던 증액 경매가 "
    "화면에서 사라지고 마감 스윕도 그 행을 다시 안 본다")

print("\n[7] 돈 숫자는 서버 집계 한 곳에서 온다")
_s = ADM.find("VIEWS.stats")
seg = strip_js(ADM[_s:_s + 2600]) if _s > 0 else ""
chk("/api/settlements/summary" in seg,
    "★ 누적 수수료가 서버 집계다",
    "종전에는 /api/settlements(LIMIT 1000·취소 포함)를 화면에서 더했다 — "
    "실측 1,295만 vs 실제 475만")
chk("ops-kpi" in seg,
    "★ 평균 절감률도 서버가 확정건만 센 값을 쓴다")
chk("api('GET','/api/cases')" in seg,
    "★ 발주처별 건수 표가 쓰는 목록 조회는 남아 있다",
    "돈 카드만 옮기고 이 fetch 를 지우면 화면이 통째로 죽는다(ReferenceError)")

print("\n[8] 취소된 정산이 '입금 확인 대기' 에 남지 않는다")
chk("s.insurer_paid!=='입금완료' && s.void_status!=='취소'" in strip_js(ADM).replace(" ", "").replace(
        "s.insurer_paid!=='입금완료'&&s.void_status!=='취소'", "s.insurer_paid!=='입금완료' && s.void_status!=='취소'")
    or "void_status!=='취소'" in strip_js(ADM)[strip_js(ADM).find("입금 확인 대기") - 400:
                                              strip_js(ADM).find("입금 확인 대기") + 400],
    "★ 입금 확인 대기 집계가 취소를 제외한다",
    "같은 화면의 형제 지표는 전부 보고 있었다")

print("\n[9] 실패를 삼키지 않는다")
_p = ADM.find("async function appAct")
seg = ADM[_p:_p + 900] if _p > 0 else ""
chk("catch" in seg and "toast" in seg,
    "★ 입점 심사 실패가 화면에 뜬다",
    "위임 실행기는 반환값을 catch 하지 않는다 — 403/409/500 이 unhandled rejection 으로 "
    "끝나고 담당자는 '눌렀는데 반응이 없다' 만 본다")

print("\n[10] 협력사 화면이 서버 문턱과 같은 말을 한다")
_pp = strip_js(PAR)
_c = _pp.find('data-complete="${c.id}"')
chk("canAct()" in _pp[max(0, _c - 500):_c],
    "★ 완료 보고 버튼이 등급으로 가려진다")
_r = _pp.find('data-reestimate="${c.id}"')
chk("canAct()" in _pp[max(0, _r - 300):_r],
    "★ 실사 증액 요청 버튼이 등급으로 가려진다")

print("\n[11] 2차 경매에서도 자릿수 방어가 산다")
chk("const _base = cap || floorC" in _pp,
    "★ 상한이 없으면 하한·직전 입찰가를 기준으로 본다",
    "종전 `cap && n < cap*0.5` 는 2차에서 cap=0 이라 통째로 꺼졌다. 상·하한이 둘 다 "
    "없는 건(사진없이 접수+개산 미매칭)에서는 저가경보까지 꺼져 무경고로 확정된다")

print("\n[12] 낙찰가 정렬이 화면과 같은 금액을 쓴다")
chk("award_amount || x.low_price" in strip_js(ADM),
    "★ 확정 낙찰가를 먼저 본다",
    "표는 award_amount||low_price 를 그리는데 정렬은 low_price 만 봤다 — "
    "경매 없이 확정된 1차합의 건이 '높은순' 맨 아래로 밀렸다")


# ── 구문 ──────────────────────────────────────────────────────────
import ast  # noqa: E402
for f in ("app.py", "dispatch.py"):
    try:
        ast.parse(read(f)); ok, why = True, ""
    except SyntaxError as e:
        ok, why = False, f"{e.lineno}행: {e.msg}"
    chk(ok, f"{f} 구문", why)

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
