# -*- coding: utf-8 -*-
"""23라운드 회귀 — **형제 중 하나만 빠져 있던 자리들.**

  다각도 스캔 22건 중 반증을 견딘 14건에서 11건을 고쳤다. 공통점이 뚜렷하다 —
  같은 판단을 하는 자리가 여럿인데 **그중 하나만** 옛 규칙을 쓰고 있었다.

  ① 다른 업체 실견적(field_ref) — 형제 세 곳은 지우는데 '내 낙찰 건' 만 열려 있었다.
     추가분 최저가(add_low)도 같은 응답에서 원업체가 아닌 낙찰자에게 나갔다. (철칙 4)
  ② 전체재경매 낙찰이 **완료 보고까지 끝난** 사건('검수대기')의 시공사를 갈아치웠다.
     시공한 업체는 자기 사건을 404 로 못 찾고, 정산은 새 업체 이름·계좌로 나간다.
  ③ 발주처 절감 리포트 **화면**만 '가견적' 이라고 인쇄했다. 엑셀·월명세서는 이미
     '비교 기준' 으로 고쳐져 있었다. 2차 건의 그 값은 우리가 만든 개산가다. (철칙 2·6)
  ④ 어드민 벨 알림이 `/admin#settle` 을 못 읽어 **클릭이 전부 죽었다.**
     운영 DB 실측: 어드민 알림 1,302건 중 123건(정산 77 · 사건 46).
  ⑤ 발주처 목록의 '낙찰가' 열이 **최저 입찰가**를 인쇄했다(실측 37건 전부 승인대기).
  ⑥ 감사 로그 필터가 화면과 어긋난 채 남았다 — **22라운드에 내가 만든 것**.
  ⑦ 어드민 절감률이 확정가가 없으면 최저가로 폴백했다 — 바로 위 주석이 정반대를 선언.
  ⑧ '완료보고지연'(자동으로 붙는 흔한 상태)에서 증액 요청 창구만 닫혀 있었다.
  ⑨ 사진 열람 게이트가 금지 목록이라 불확실 버킷('기타')을 입찰자에게 열었다.
  ⑩ 하자 재시공 토스트가 나가지도 않은 알림톡을 '발송' 이라고 단정했다.
  ⑪ 승인 대기 패널의 절감이 **항상 −0%** — 승인을 판단하는 유일한 화면이었다.

      python test_scan_round23_fixes.py
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
    """중괄호 균형으로 함수 본문을 뜬다 — 글자수로 자르지 않는다."""
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


def strip_js(t):
    t = re.sub(r"(?<![A-Za-z0-9_\"'])/\*.*?\*/", " ", t, flags=re.S)
    return "\n".join(ln for ln in t.splitlines() if not ln.strip().startswith("//"))


APP, ADM = read("app.py"), read("static/admin.js")
INS = read("templates/insurer_portal.html")
_ADMS = strip_js(ADM)

print("═" * 70)
print("  23라운드 회귀 — 형제 중 하나만 빠져 있던 자리")
print("═" * 70)

# ── ① ────────────────────────────────────────────────────────
print("\n[1] 남의 금액이 협력사 응답에 실리지 않는다 (철칙 4)")
_pd = strip_py(func_body(APP, "def api_partner_case_detail"))
if not _pd:                     # 이름이 다르면 라우트로 찾는다
    _i = APP.find('"/api/partner/cases/<int:cid>/detail"')
    _pd = strip_py(APP[_i:_i + 4200]) if _i > 0 else ""
chk(bool(_pd), "협력사 사건 상세 라우트를 찾았다")
_mine = _pd[:_pd.find("else:")] if "else:" in _pd else _pd
chk('"field_ref": c["field_ref"]' not in _mine,
    "★★ '내 낙찰 건' 응답에서 field_ref 를 뺐다",
    "field_ref 는 2차 경매의 근거가 된 **출동 업체(남)** 의 실견적이다. "
    "bid_cap_of 는 '결렬' 합의행이 있는 한 낙찰 뒤에도 계속 그 값을 준다. "
    "형제 세 곳(대시보드·비낙찰 분기·open-auctions)은 모두 지우고 있었다")
chk('co["add_low"] = None' in _pd and "incumbent_partner_id" in _pd,
    "★★ 추가분 최저가는 원업체에게만 준다",
    "add_low 는 제3의 업체가 낸 입찰가다. 전체재경매로 낙찰자가 바뀌어도 "
    "change_orders 에 그대로 남아, 새 낙찰자가 그 금액을 본다")
chk("field_ref" not in read("templates/partner_portal.html"),
    "협력사 화면은 이 값을 쓰지 않는다(빼도 화면이 안 깨진다)")
#  ★ 형제들이 여전히 막고 있는지도 함께 본다 — 한쪽만 고치면 또 갈린다
for _sig, _what in (('oc["field_ref"], oc["auction_round"] = None, _rnd', "협력사 대시보드"),
                    ('r["field_ref"] = None', "/api/open-auctions")):
    chk(_sig in APP, f"형제도 그대로 막고 있다 — {_what}")

# ── ② ────────────────────────────────────────────────────────
print("\n[2] 완료 보고가 끝난 사건의 시공사를 갈아치우지 않는다")
_cf = strip_py(func_body(APP, "def api_co_close_full"))
if not _cf:
    _i = APP.find("close-full")
    _cf = strip_py(APP[_i:_i + 5000]) if _i > 0 else APP
_seg = _cf[_cf.find("UPDATE cases SET partner_id"):][:400]
chk("'검수대기'" not in _seg and _seg,
    "★★ allow-list 에서 '검수대기' 를 뺐다",
    "'검수대기' 는 원업체가 완료 보고를 **이미 올린** 상태다(completed_at 확정). "
    "거기서 업체를 바꾸면 시공한 업체는 자기 사건을 404 로 못 찾고, "
    "정산은 현장에 간 적 없는 새 업체 이름·계좌로 만들어진다")
chk("'시공중'" in _seg and "'완료보고지연'" in _seg,
    "완료 보고 전 상태는 그대로 교체할 수 있다(재경매의 정상 용도)")
chk("기존 시공사가 완료 보고를 올렸거나" in _cf,
    "★ 막힐 때 **무엇을 해야 하는지** 말한다",
    "409 만 던지면 운영자는 왜 막혔는지 모른다")

# ── ③ ────────────────────────────────────────────────────────
print("\n[3] 우리 개산가를 발주처 명의로 인쇄하지 않는다 (철칙 2)")
for _bad, _where in (("가견적 합계", "표 머리글"),
                     ("가견적 대비 확정 공사대금", "패널 부제")):
    chk(_bad not in INS, f"★ 절감 리포트에 '{_bad}' 가 없다 — {_where}")
chk("비교 기준 합계" in INS and "비교 기준 대비" in INS,
    "★ 엑셀·월명세서와 **같은 이름**을 쓴다",
    "같은 데이터를 화면과 파일에서 다른 명의로 받으면 어느 쪽이 맞는지 알 수 없다")
_rep = strip_py(func_body(APP, "def api_insurer_report"))
chk("가견적(상한) 대비" not in _rep,
    "★★ 기준 문장이 회차를 뒤집어 말하지 않는다 (철칙 6)",
    "2차는 가견적이 **하한**이다. '가견적(상한) 대비' 는 그 건에서 거짓말이다")
chk("1차는 가견적" in _rep and "2차는 표준단가 개산" in _rep,
    "★ 두 회차를 모두 정확히 설명한다")
#  ★ 자매 산출물이 되돌아가지 않았는지 함께 잠근다
chk("가견적 합계(원)" not in APP and "비교 기준 합계(원)" in APP,
    "리포트 엑셀도 그대로다")
chk("비교 기준(원)" in APP, "월 정산 명세서도 그대로다")

#  ★★ **형제를 전수로 잠근다.** 23라운드에 리포트 화면만 고치고 같은 값을 쓰는
#     카드 3개를 그대로 뒀다가 바로 다시 잡았다 — 이번 라운드에서 고친 결함의
#     정확히 그 유형이다. 주석은 빼고 **사람에게 보이는 문자열만** 센다.
def _strip_c(t, js):
    """설명글을 지운다 — **사람에게 보이는 문자열만** 남긴다.

    ⚠⚠ 파이썬은 `#` 뿐 아니라 **docstring 까지** 지워야 한다. 안 그러면
      "'가견적 − 확정가' 가 아니다" 같은 **안전장치 문장 자체**가 위반으로 잡힌다.
      이 파일에서 실제로 그렇게 두 번 헛돌았다.
    """
    if js:
        t = re.sub(r'\$\{/\*.*?\*/["\']{2}\}', " ", t, flags=re.S)
        t = re.sub(r"(?<![A-Za-z0-9_\"'])/\*.*?\*/", " ", t, flags=re.S)
        return "\n".join(l for l in t.splitlines() if not l.strip().startswith("//"))
    t = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', " ", t)
    return "\n".join(l for l in t.splitlines() if not l.strip().startswith("#"))


#  ⚠ 남아도 되는 두 곳 — 여기는 '가견적 대비' 가 **정확하다.**
#    · 투찰 경고·알림   : `cap`(bid_cap_of 의 상한)을 나눈다. 2차는 상한이 0 이라
#                        `if pct and cap` 가드에 걸려 1차에서만 뜬다.
#    · 이상 저가 경보   : `c.est_price` 를 직접 나눈다.
#    '일관성' 이라며 이것까지 바꾸면 정확한 문구를 부정확하게 만든다.
#  ⚠ 처음엔 '가견적 대비' 만 찾았다가 운영 KPI 의 **'가견적 − 낙찰/합의가'** 를
#    놓쳤다(브라우저에서 발견). 패턴을 좁게 잡으면 형제를 또 남긴다 —
#    '가견적' 이 **절감·대비·뺄셈** 과 같은 줄에 있으면 전부 후보로 올린다.
_OKAY = (
    "(기준 {pct}%)",           # 투찰 알림 — cap 기반, 2차는 cap=0 이라 1차만
    "low_price_alert_pct",     # 이상 저가 경보 — est_price 를 직접 나눈다
    "산출 근거 소명",           # 투찰 경고 — 같은 cap 기반
    "보상담당자 가견적",         # 회차별로 풀어 쓴 안내문(정확한 설명)
)
_PAT = re.compile(r"가견적\s*(대비|[−-]\s*(낙찰|확정|합의))")
_left = []
for _rel, _js in (("app.py", 0), ("static/admin.js", 1), ("static/app.js", 1),
                  ("templates/insurer_portal.html", 1),
                  ("templates/partner_portal.html", 1)):
    _t = read(_rel)
    if _t.startswith("<<읽기실패"):
        continue
    for _ln in _strip_c(_t, _js).splitlines():
        if _PAT.search(_ln) and not any(k in _ln for k in _OKAY):
            _left.append(f"{_rel}: {_ln.strip()[:80]}")
chk(not _left,
    "★★ 절감 표시 어디에도 '가견적 대비/가견적 −' 가 남지 않았다",
    f"{_left} — 그 값(saved·avg_rate)은 SAVE_BASE_SQL 기반이라 2차 건에서는 "
    f"**우리가 계산한 표준단가 개산**이다(철칙 2)")
chk("비교 기준 − 낙찰/합의가" in ADM,
    "★ 운영 KPI '누적 절감액' 설명도 같은 이름을 쓴다")
chk("비교 기준 대비" in INS and "비교 기준 대비" in ADM,
    "★ 발주처·어드민 카드가 같은 이름을 쓴다")

# ── ④ ────────────────────────────────────────────────────────
print("\n[4] 벨 알림 클릭이 죽지 않는다")
_no = js_func(ADM, "async function notiOpen")
_noS = strip_js(_no)
chk("link.indexOf('#')" in _noS or "link.includes('#')" in _noS,
    "★★ `/admin#settle` 처럼 경로가 붙은 링크에서 해시를 뽑는다",
    "서버는 알림톡·푸시와 같은 값을 쓰려고 절대경로로 저장한다. 화면이 '#' 로 "
    "시작하는 것만 알아봐 **운영 DB 1,302건 중 123건**의 클릭이 죽었다")
chk("hash.startsWith('#cases/')" in _noS,
    "★ 사건 알림은 사건 상세로 간다")
chk("location.href = link" in _noS,
    "★ 해시 없는 절대경로는 진짜로 이동한다(다른 포털 링크)")
chk("이 알림은 열어 볼 화면이 따로 없습니다" in _noS,
    "정말 갈 곳이 없을 때만 그렇게 말한다")
#  ★ 서버가 실제로 어떤 모양을 저장하는지 — 코드에서 확인
chk('url="/admin#' in APP,
    "서버가 `/admin#…` 형태로 저장하는 것이 맞다(가정이 아니라 근거)")

# ── ⑤ ⑪ ─────────────────────────────────────────────────────
print("\n[5] 확정가와 '현재 최저가' 를 같은 이름으로 찍지 않는다")
chk("${c.low_price?won(c.low_price):'-'}" not in INS,
    "★★ '낙찰가' 열이 low_price 를 그대로 찍지 않는다",
    "low_price 는 투찰이 들어올 때마다 바뀌는 현재 최저가다. 청구는 "
    "award_amount 로 나간다 — 실측 37건이 전부 승인 전인데 낙찰가가 찍혔다")
chk(INS.count("c.award_amount ? won(c.award_amount)") == 2,
    "★ 두 표(대시보드·사건 탭) 모두 고쳤다",
    "한쪽만 고치면 같은 화면 안에서 두 표가 다른 말을 한다")
chk("최저 ${won(c.low_price)}" in INS,
    "★ 확정 전에는 '최저' 라고 분명히 적는다")
chk("<th class=\"r\">예상 절감</th>" in INS,
    "★★ 승인 대기 패널의 절감은 '예상' 이다",
    "서버 c.saving 은 확정가 기준이라 승인 전에는 반드시 0 — 그 표의 모든 행이 "
    "녹색 −0% 였다(실측 37건). 승인 여부를 판단하는 유일한 화면이다")
chk("if(!b || !lo) return" in INS,
    "★ 비교 기준이 없으면 0 으로 나누지 않고 '-' 로 둔다")

# ── ⑥ ────────────────────────────────────────────────────────
print("\n[6] 감사 로그 필터가 화면과 어긋나지 않는다 (22라운드 자책)")
chk('id="au_q" value="${esc(AUDIT.q)}"' in ADM,
    "★★ 화면을 다시 그릴 때 검색어를 되살린다",
    "안 되살리면 조건을 걸고 다른 메뉴에 갔다 오면 **검색창은 비었는데 "
    "목록·총건수는 필터된 값** 그대로다(실측 재현: '' / 총 143건)")
for _id in ("au_from", "au_to"):
    chk(f'id="{_id}" type="date" value="${{esc(AUDIT.' in ADM,
        f"★ 기간도 되살린다 — {_id}")
_ra = js_func(ADM, "async function renderAudit")
chk("if(AUDIT.action) sel.value = AUDIT.action" in _ra,
    "★ 고른 행위도 되살린다(옵션을 **채운 뒤에** 넣는다)",
    "채우기 전에 넣으면 그 값이 없는 select 라 조용히 무시된다")

# ── ⑦ ────────────────────────────────────────────────────────
print("\n[7] 절감률이 확정 안 된 금액으로 헛돌지 않는다")
_ac = strip_py(func_body(APP, "def api_cases"))
chk('c.get("award_amount") or c.get("low_price")' not in _ac,
    "★★ 최저 입찰가로 폴백하지 않는다",
    "바로 위 주석이 '최저 입찰가는 아직 확정이 아니다' 라고 적어 놓고 코드는 "
    "그걸 썼다. 실측 37건이 낙찰 전인데 절감률을 갖고, 투찰 하나에 또 바뀐다. "
    "'절감률 높은순' 정렬의 키도 이 값이다")
chk('fixed = c.get("award_amount") or 0' in _ac,
    "★ 확정가만 센다(형제 세 곳과 같은 규칙)")

# ── ⑧ ────────────────────────────────────────────────────────
print("\n[8] 자동으로 붙는 상태가 창구를 닫지 않는다")
_co = strip_py(func_body(APP, "def api_change_order_create"))
if not _co:
    _i = APP.find("실사 증액 요청은 시공 단계에서만")
    _co = strip_py(APP[max(0, _i - 1200):_i + 300]) if _i > 0 else ""
chk('"완료보고지연"' in _co,
    "★ '완료보고지연' 에서도 증액 요청을 받는다",
    "낙찰 후 24시간이면 자동으로 붙는 상태다(지방·주말 공사에서는 정상). "
    "같은 흐름의 다른 라우트는 모두 이 상태를 받는데 여기만 빠져 있었다")

# ── ⑨ ────────────────────────────────────────────────────────
print("\n[9] 사진 열람은 허용 목록으로 판정한다")
_pv = strip_py(func_body(APP, "def _photo_visible_to"))
chk("_kind in PHOTO.CONSTRUCTION_KINDS" in _pv,
    "★★ 금지 목록이 아니라 허용 목록이다",
    "`not in DOCUMENT_KINDS(=['영수증'])` 는 '기타' 를 통과시키는데, photo_ai 의 "
    "'기타' 는 **불확실 버킷**이라 분류 실패한 영수증이 거기 들어간다 — "
    "그 순간 직전 시공사 상호와 공사금액이 경쟁사에 열린다")
chk("_kind not in PHOTO.DOCUMENT_KINDS" not in _pv,
    "★ 옛 금지 목록 판정이 남아 있지 않다")
try:
    sys.path.insert(0, HERE)
    import photo_ai as _PA
    chk(set(_PA.CONSTRUCTION_KINDS) == {"착공전", "시공중", "완료"},
        f"★ 허용 목록이 시공 사진 3종이다 — {_PA.CONSTRUCTION_KINDS}")
    chk("기타" not in _PA.CONSTRUCTION_KINDS and "영수증" not in _PA.CONSTRUCTION_KINDS,
        "★ 불확실 버킷·서류는 그 목록에 없다")
except Exception as _e:
    chk(False, "photo_ai 상수 확인", f"{type(_e).__name__}: {_e}")

# ── ⑩ ────────────────────────────────────────────────────────
print("\n[10] 나가지 않은 발송을 '발송' 이라고 하지 않는다")
chk("시행사에 알림톡 발송'" not in ADM,
    "★ 하자 재시공 토스트가 발송을 단정하지 않는다",
    "실발송 스위치가 꺼진 지금은 발송대기 큐에만 쌓인다. 하자 재시공은 기한이 "
    "걸린 작업이라, 운영자가 '나갔다' 고 믿으면 연락을 안 한다")
chk("발송사 연동 후" in _ADMS,
    "★ 같은 콘솔의 다른 안내문과 같은 말을 쓴다")

print("")
for f in ("app.py",):
    try:
        ast.parse(read(f)); ok_, why = True, ""
    except SyntaxError as e:
        ok_, why = False, f"{e.lineno}행: {e.msg}"
    chk(ok_, f"{f} 구문", why)
for f in ("templates/insurer_portal.html", "templates/partner_portal.html"):
    _t = read(f)
    chk(_t.count("<div") == _t.count("</div>"),
        f"{f} div 균형", f"{_t.count('<div')} / {_t.count('</div>')}")

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
