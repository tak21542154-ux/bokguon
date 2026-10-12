# -*- coding: utf-8 -*-
"""20라운드 회귀 — **되돌리는 문을 만들었더니 행이 늘어났다.**

  19라운드에서 `to-dispatch`(공고를 접고 출동 수배로 전환)를 만들었다. 그런데
  그 경로는 경매 **행을 지우지 않고 status 만 바꾼다.** 그 뒤 [경매 열기]는
  조건 없이 INSERT 했으므로 한 사건에 원경매가 **2행**이 됐다.
  투찰 라우트는 `ORDER BY id LIMIT 1` 로 **가장 오래된**(죽은) 행을 집고,
  그 행의 지난 마감시각이 마감 가드에 걸려 **그 사건의 투찰이 전부 400 으로
  막혔다** — 투찰을 받으려고 연 공고가 투찰을 막는 상태.
  걸러 낼 방법도 없었다: 그 행에 붙는 '취소' 를 **읽는 쿼리가 하나도 없었다.**

  실측(고치기 전): 사건 3116 전환 후 auctions 974행이 status='취소' 로 살아남음.
  실측(고친 뒤):   대조군 1행 / 실험군 1행(extend_count=1 — 되살림) · 중복 0건.

      python test_scan_round20_fixes.py
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


def strip_py(t):
    return "\n".join(ln for ln in t.splitlines() if not ln.strip().startswith("#"))


APP = read("app.py")
PAR = read("templates/partner_portal.html")

print("═" * 70)
print("  20라운드 회귀 — 한 사건에 원경매는 하나")
print("═" * 70)

print("\n[1] 공고를 다시 열어도 원경매 행이 늘지 않는다")
_oa = strip_py(func_body(APP, "def _open_original_auction"))
chk("UPDATE auctions" in _oa,
    "★ 이미 있으면 **되살린다**",
    "조건 없이 INSERT 하면 전환→재개 경로에서 원경매가 2행이 되고, 투찰은 "
    "ORDER BY id LIMIT 1 로 죽은 옛 행을 집어 400 CLOSED 로 막힌다")
chk("if cur.rowcount:" in _oa and "INSERT INTO auctions" in _oa,
    "★ 없을 때만 새로 만든다(형제인 낙찰취소와 같은 규칙)")
_upd = _oa.find("UPDATE auctions")
_ins = _oa.find("INSERT INTO auctions")
chk(0 < _upd < _ins,
    "★ 순서가 UPDATE → (없으면) INSERT 다",
    "반대면 늘 새로 만들어 아무것도 고쳐지지 않는다")
chk("change_order_id IS NULL" in _oa,
    "원경매만 손댄다(변경견적 재경매 행을 건드리지 않는다)")

print("\n[2] 죽은 경매 행이 남지 않는다 — 걸러 읽는 곳이 없기 때문")
#  ⚠ '취소' 는 쓰기만 하고 읽는 쿼리가 하나도 없다(실측). 그래서 '남기고 거른다' 는
#    선택지가 애초에 없었고, **행을 늘리지 않는 것**만이 답이다.
_cancel_lines = re.findall(r"[^\n]*auctions[^\n]*'취소'[^\n]*", strip_py(APP))
chk(len(_cancel_lines) <= 1,
    f"★ auctions 의 '취소' 를 쓰는 곳이 {len(_cancel_lines)}곳뿐이다(읽는 곳은 0)",
    "읽는 쿼리가 없으므로 그 상태로 걸러낼 수 없다 — 행 자체를 늘리지 않아야 한다")

print("\n[3] 상한이 없으면 '상한 없음' 이라고 말한다")
chk("상한 없음" in PAR,
    "★ cap=0 을 '상한 0원' 으로 인쇄하지 않는다",
    "서버는 `if cap and amount > cap:` 이라 cap=0 이면 상한 검사를 건너뛴다 — "
    "어떤 금액도 받는데 화면은 '0원보다 높게는 넣을 수 없습니다' 라고 말했다. "
    "첫 주 단 하나뿐인 시행사 계정이 그걸 규칙으로 읽으면 공고가 그대로 유찰된다")
chk("이 공고에는 <b>상한이 없습니다.</b>" in PAR,
    "★ 안내 문구도 함께 갈린다(있지도 않은 제한을 말하지 않는다)")
#  ⚠ **한 줄만 보면 안 된다.** 이 조건은 여러 줄에 걸쳐 있다 —
#    `: (cap` 이 앞줄에 있고 문구는 다음 줄이라, 한 줄 검사는 멀쩡한 코드를
#    실패로 읽는다(실제로 그랬다). 그 문구 **앞쪽 200자**를 함께 본다.
_i = PAR.find("가견적 ${won(cap)}원이 상한")
chk(_i > 0 and "cap" in PAR[max(0, _i - 200):_i],
    "★ 상한 문구가 cap 조건 안에서만 렌더된다",
    "cap=0 인 공고에서 '가견적 0원이 상한' 이 나오면 안 된다")

print("\n[4] 전환한 사건이 '수배를 열어야 하는 사건' 에 실제로 뜬다")
_td = strip_py(func_body(APP, "def api_case_to_dispatch"))
chk("dispatch_status=NULL" in _td,
    "★ 출동 이력(dispatch_status)을 비운다",
    "그 목록 조건에 `COALESCE(dispatch_status,'')=''` 가 있다 — 한 번 출동을 "
    "다녀온 사건은 이 값이 남아 목록에서 빠진다(발주처 취소 경로는 이미 비운다)")
chk("intake_type='사진없음'" not in _td,
    "★ intake_type(이력)을 덮어쓰지 않는다",
    "그 값은 '어떻게 들어왔나' 라는 이력이고 타임라인이 그것으로 가견적 표시를 "
    "가른다 — 덮어쓰면 2차 하한이 될 값이 타임라인에서 사라진다")
_nd = APP[APP.find("--  ⚠ **intake_type 을 묻지 않는다.**"):]
chk(_nd.startswith("--  ⚠"),
    "★ 목록 조건이 '어떻게 들어왔나' 대신 '지금 수배가 필요한가' 를 묻는다",
    "실측: 두 DB 모두 '접수'+'사진있음' 조합은 0건 — 이 전환으로만 생긴다")
_dash = APP[APP.find('"출동수배_필요"'):APP.find('"출동수배_필요"') + 320]
chk("intake_type" not in _dash,
    "★ 대시보드 카드도 같은 술어를 쓴다",
    "한쪽만 intake_type 을 물으면 카드 숫자와 목록 길이가 갈린다")

print("\n[5] 감사로그의 '행위자' 를 상대방이 정하지 않는다")
DSP = read("dispatch.py")
_nr = strip_py(DSP[DSP.find("미수선 종결") - 900:DSP.find("미수선 종결") + 400])
chk('DB.log(conn, f"협력사{partner_id}", "미수선 종결"' in strip_py(DSP),
    "★ actor 는 시스템이 아는 주체로 고정한다",
    "`by` 는 세션이 아니라 요청 본문(화면 prompt)에서 온다. 되돌리기 어려운 종결 "
    "행위의 기록에 '운영팀 OOO' 같은 아무 문자열이나 남길 수 있었다 — 분쟁 때 "
    "로그가 근거가 아니라 반증거가 된다")
chk("현장 확인자(자기신고)" in DSP,
    "★ 사람이 적어 준 이름은 이름표를 붙여 detail 에 남긴다(버리지 않는다)")
chk('(by or "").strip()[:60]' in DSP, "길이도 자른다(감사로그에 원문 그대로 넣지 않는다)")

print("\n[6] 같은 사실을 두 화면이 다르게 말하지 않는다")
chk('p["bank_ready"]' in APP,
    "★ 계좌 준비 여부를 **돈이 막히는 기준**으로 내려준다",
    "이체 판정은 계좌+예금주를 둘 다 요구하는데 마이페이지는 계좌만 보고 '등록됨' "
    "이라 했다 — 예금주만 비면 홈은 '미등록', 내 정보는 '등록됨' 이 동시에 뜬다")
chk("p.bank_ready" in PAR, "★ 화면이 그 값을 쓴다")
chk("예금주</u>가 비어 있어" in PAR,
    "★ 무엇이 모자란지 정확히 말한다(다시 서류를 보내라고 하지 않는다)")
chk("open_cases_total" in PAR and "최신순 20건까지" in PAR,
    "★ 공고 목록이 잘렸으면 잘렸다고 말한다",
    "서버는 LIMIT 20 인데 헤더가 그 길이를 총계처럼 찍었다 — 58건이 열려 있어도 "
    "20건으로 보인다(같은 파일의 홈 카드·「내 입찰」 탭은 이미 총계를 쓴다)")
chk("handled_note=NULL" in APP,
    "★ 발송 되돌리기가 처리메모까지 지운다",
    "안 지우면 되돌린 뒤에도 '처리메모: 전화 완료' 가 남아 아직 처리된 건처럼 보인다")

print("\n[7] 보험사 연동 API 가 확정 전 숫자를 확정 이름으로 주지 않는다")
_v1 = strip_py(func_body(APP, "def _v1_case_view"))
chk('c.get("award_amount") or c.get("low_price")' not in _v1,
    "★ award_amount 에 최저 입찰가를 폴백하지 않는다",
    "이건 서버-서버 API 다. 아직 낙찰도 안 된 사건의 **현재 최저 입찰가**가 "
    "'낙찰금액' 이라는 이름으로 보험사 전산에 들어가면, 받는 쪽은 계약금액으로 "
    "기록한다 — 우리가 금액을 확정해 준 꼴이 된다(철칙 1). 화면 쪽은 앞 라운드에 "
    "고쳤는데 이 API 만 형제로 남아 있었다")
chk('"low_price"' in _v1 and '"is_awarded"' in _v1,
    "★ 최저가는 제 이름으로 따로 준다(정보를 잃지 않는다)",
    "실측: 미낙찰 45건에도 low_price 가 그대로 실린다")
chk("_fixed / _base" in _v1 or "_fixed/_base" in _v1.replace(" ", ""),
    "★ 절감률도 확정가로만 낸다",
    "low_price 는 투찰마다 바뀐다 — 그걸로 절감률을 내면 숫자가 계속 흔들린다")

print("\n[8] 같은 웹훅 event 는 경로마다 같은 키를 준다")
#  ⚠ 보험사 전산은 event 이름으로 파서를 고른다. 같은 event 인데 경로마다 키가
#    다르면 어느 경로로 낙찰됐느냐에 따라 상대 파서가 깨진다. 규격이 문서에도
#    없어 **코드가 유일한 계약**이다 — 그래서 코드가 일관되어야 한다.
#    실측(고치기 전): case.awarded 3경로가 금액 키(award_amount/amount)·
#    업체 키(partner/partner_name)·status 유무를 전부 다르게 썼다.
import collections  # noqa: E402
_ev = collections.defaultdict(set)
for _m in re.finditer(r"(?:deliver_webhook|safe_webhook)\(\s*conn\s*,[^,]+,\s*"
                      r"[\"']([^\"']+)[\"']\s*,[^,]+,\s*(\{.*?\})\s*\)", APP, re.S):
    _ev[_m.group(1)].add(tuple(sorted(set(re.findall(r"[\"'](\w+)[\"']\s*:", _m.group(2))))))
_mixed = {k: v for k, v in _ev.items() if len(v) > 1}
chk(not _mixed,
    f"★ 웹훅 이벤트 {len(_ev)}종 전부 경로별 키가 같다",
    f"키가 갈리는 이벤트: {sorted(_mixed)}" if _mixed else "")
chk(("amount", "partner_name", "route", "status") in _ev.get("case.awarded", set()),
    "★ case.awarded 는 amount·partner_name·route·status 로 고정")

print("\n[9] 연동 규격 문서가 코드와 같은 말을 한다")
#  ⚠ 규격이 코드에만 있으면 인수인계가 안 되고, 문서만 있으면 낡는다.
#    **문서에 적은 키를 코드에서 다시 확인**해 둘이 갈리면 여기서 터지게 한다.
DOC = read("deploy/DEPLOY.md")
chk("## 9. 보험사 연동 규격" in DOC, "★ 연동 규격이 문서에 있다")
for _k in ("award_amount", "low_price", "is_awarded", "saving_rate"):
    chk(_k in DOC and _k in _v1,
        f"문서·코드가 같은 필드를 말한다 — {_k}")
for _ev_name, _keys in (("case.awarded", ("amount", "partner_name", "status", "route")),
                        ("case.reviewed", ("amount", "fee", "payout", "status")),
                        ("settlement.paid", ("amount", "fee", "payout", "status"))):
    _doc_ok = _ev_name in DOC
    _code_ok = tuple(sorted(_keys)) in _ev.get(_ev_name, set())
    chk(_doc_ok and _code_ok,
        f"문서의 웹훅 규격이 코드와 일치 — {_ev_name}",
        f"문서에 있음={_doc_ok} · 코드 키 일치={_code_ok}")
chk("Idempotency-Key" in DOC and "Idempotency-Key" in APP,
    "★ 재시도 안전장치가 문서에도 적혀 있다")

print("")
for f in ("app.py", "dispatch.py"):
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
