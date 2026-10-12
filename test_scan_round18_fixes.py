# -*- coding: utf-8 -*-
"""18라운드 회귀 — **시스템이 시키는 일을 할 문이 있는가.**

  이번 판의 주제: 화면·알림이 "이렇게 하세요" 라고 말하는데 그 코드가 없다.
    · "출동 수배로 전환하세요" 라고 세 곳에서 알리는데 전환 라우트가 없었다
    · "사진을 붙이면 입찰, 없으면 출동" 이라 적어 놓고 폼이 그 값을 안 보냈다
    · '실사요청' 을 되돌리는 유일한 코드가 자기 가드에 막혀 도달 불가였다(catch-22)
    · [처리함] 을 잘못 누르면 되돌리는 코드가 어디에도 없었다
  그리고 **돈 숫자가 화면마다 다른 말을 하는 자리** 6곳.

      python test_scan_round18_fixes.py
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


def strip_js(t):
    t = re.sub(r"(?<![A-Za-z0-9_\"'])/\*.*?\*/", " ", t, flags=re.S)
    return "\n".join(ln for ln in t.splitlines() if not ln.strip().startswith("//"))


APP = read("app.py")
ADM = read("static/admin.js")
PAR = read("templates/partner_portal.html")
MAN = read("manage.py")
PA = read("partner_accounts.py")
LD = read("legal_docs.py")

print("═" * 70)
print("  18라운드 회귀 — 시키는 일을 할 문이 있는가")
print("═" * 70)

# ── [1] 출동 수배로 전환 ──────────────────────────────────────────
print("\n[1] '출동 수배로 전환하세요' 를 실제로 할 수 있다")
_n_ad = APP.count("출동 수배로 전환")
chk("/api/cases/<int:cid>/to-dispatch" in APP,
    f"★ 전환 라우트가 있다 (그렇게 알리는 곳 {_n_ad}군데)",
    "출동 수배 개시는 status='접수' 에서만 열리는데 공고를 연 사건은 '입찰중'·'유찰' 이다. "
    "첫 주는 포털 계정이 1곳뿐이라 투찰 0건이 기본값에 가깝다 — 바로 여기서 막힌다")
_b = strip_py(func_body(APP, "def api_case_to_dispatch"))
chk("HAS_BIDS" in _b,
    "★ 이미 들어온 입찰이 있으면 막는다",
    "협력사가 시간을 들여 낸 금액을 말없이 버리면 안 된다(그 경우는 유찰·재공고 절차다)")
chk("ALREADY_AWARDED" in _b, "★ 낙찰된 사건은 손대지 않는다")
chk("status='취소'" in _b and "auctions" in _b, "★ 진행 중이던 경매를 명시적으로 닫는다")
chk("work_lots" in _b,
    "★ 공종 항목도 함께 되돌린다",
    "실측: 전환 뒤 사건은 '접수' 인데 work_lots 만 '입찰중' 으로 남았다 — 한 사건이 "
    "두 상태를 말한다. 재공고 경로는 '유찰→입찰중' 만 뒤집으므로 영영 안 고쳐진다")
chk("BEGIN IMMEDIATE" in _b, "쓰기 잠금 안에서 상태를 바꾼다")

# ── [2] 사진 없는 접수 ────────────────────────────────────────────
print("\n[2] 관리자 콘솔도 '사진 없음' 으로 접수할 수 있다")
def js_func(src, header):
    """`async function 이름(){` 부터 **닫는 중괄호까지** — 창을 글자수로 자르지 않는다.

    ⚠ 종전에는 `find(header) + 2000` 으로 잘랐다. 그 함수에 코드를 조금만 더해도
      검사 대상이 창 밖으로 밀려 **멀쩡한 코드가 실패로 뜬다**(실제로 그랬다 —
      공종 경고 확인창을 넣자 `r.no_photo` 가 창 밖으로 나갔다).
    """
    i = src.find(header)
    if i < 0:
        return ""
    depth, k = 0, src.find("{", i)
    if k < 0:
        return ""
    j = k
    while j < len(src):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
        j += 1
    return src[i:]


_cc = strip_js(js_func(ADM, "async function createCase"))
chk("no_photo" in _cc,
    "★ 등록 폼이 사진 유무를 서버에 보낸다",
    "안내문은 '사진을 붙이면 입찰 공고, 없으면 인근 업체 출동' 이라고 말하는데 "
    "이 키를 안 보내서 서버가 항상 '입찰중' 으로 열었다(서버는 읽을 준비가 돼 있었다)")
chk("c_photos" in _cc, "실제 업로드에 쓰는 그 입력(#c_photos)을 본다")
#  ⚠ 아래 셋은 **18라운드 수정이 만든 부작용**을 되돌린 것이다.
#    no_photo 를 보내기 시작하자, 종전에는 아무도 안 밟던 서버 분기가
#    관리자 콘솔의 기본 경로가 되면서 세 가지가 한꺼번에 드러났다.
_ac = strip_py(func_body(APP, "def api_case_create"))
chk('if str(d.get("est_price") or "").strip():' in _ac,
    "★ 사진 없이 접수해도 입력한 가견적을 버리지 않는다",
    "형제 경로(_create_case)는 같은 이유로 이미 보존하게 고쳐 놨는데 관리자 경로만 "
    "옛 코드였다. 이 값은 상한이 아니라 **2차 경매의 하한**이라 버리면 규칙이 죽고, "
    "가견적 수정은 '입찰중' 전용이라 되돌릴 문도 없다")
chk('"no_photo": bool(no_photo)' in _ac,
    "★ 응답이 어느 트랙으로 앉았는지 알려 준다")
chk("r.no_photo" in _cc,
    "★ 화면이 나가지도 않은 공고를 '발송했다' 고 말하지 않는다",
    "no_photo 면 경매를 열지도 알림을 보내지도 않는데 토스트는 무조건 "
    "'입찰 공고가 발송되었습니다' 였다")
chk("coWithdrawReq" in ADM and ADM.count("ACT.coWithdrawReq") == 1,
    "★ 새 철회 핸들러가 옛 핸들러와 이름이 겹치지 않는다",
    "처음엔 둘 다 ACT.coWithdraw 였다 — 더 아래의 옛 대입이 덮어써서 새 [철회] 가 "
    "/withdraw-offer 를 부르고 409 를 받았다. 즉 18라운드 수정이 화면에서 도달 불가였다")

# ── [3] '실사요청' 을 닫는 문 ─────────────────────────────────────
print("\n[3] 접수된 실사 증액 요청을 철회할 수 있다")
chk('"/api/change-orders/<int:coid>/withdraw"' in APP,
    "★ 철회 라우트가 있다",
    "종전에는 나가는 문이 '추가분 경매 오픈' 하나뿐이라, 자릿수 오타 하나를 정리하려고 "
    "협력사 399곳에 실제 공고를 띄운 뒤 유찰까지 밟아야 했다(낙찰취소 안의 철회 UPDATE 는 "
    "같은 함수의 앞선 가드에 막혀 영원히 도달하지 못하는 죽은 조건이었다)")
_w = strip_py(func_body(APP, "def api_co_withdraw"))
#  ⚠⚠ **문자열이 아니라 불변식을 잠근다.**
#    원래 이 검사는 `status='실사요청'` 이라는 리터럴을 봤다. 그런데 24라운드에
#    허용 상태가 ('실사요청','거절','유찰')로 **의도적으로 넓어졌다** —
#    '거절'·'유찰' 은 나가는 문이 전체재경매 하나뿐인데 그 라우트가 사건 상태를
#    제한해서, 사건이 '검수대기' 로 넘어가면 변경건이 영원히 갇혔기 때문이다.
#    이 검사가 지키려던 성질은 라벨에 이미 적혀 있다 —
#    **경매가 열린 뒤(추가경매중·전체재경매중)에는 여기서 닫지 않는다.**
#  ⚠ **WHERE 절만 본다.** 그냥 `status\s*(=|IN)` 로 찾으면 같은 UPDATE 의
#    `SET status='철회'` 를 먼저 집어 허용 목록이 아니라 **바꿀 값**을 읽는다
#    (실제로 그렇게 헛돌아 통과·실패가 뒤섞였다).
_m_st = re.search(r"WHERE\s+id=\?\s+AND\s+status\s*(?:=|IN)\s*\(?([^)\n]*)\)?", _w)
_allow = _m_st.group(1) if _m_st else ""
chk("'실사요청'" in _allow,
    "★ 접수 직후('실사요청') 건을 철회할 수 있다")
chk("'추가경매중'" not in _allow and "'전체재경매중'" not in _allow,
    "★ 경매가 열린 뒤에는 여기서 닫지 않는다(협력사가 이미 투찰했을 수 있다)",
    f"허용 목록: {_allow}")
chk("coWithdraw" in ADM, "화면에 철회 버튼이 있다")

# ── [4] 발송대기함 되돌리기 ───────────────────────────────────────
print("\n[4] 발송 대기함 [처리함] 을 되돌릴 수 있다")
chk('"/api/outbox/<int:nid>/reopen"' in APP,
    "★ 되돌리기 라우트가 있다",
    "실발송 큐는 status='발송대기' 만 집는다 — 오클릭 한 번이면 팝빌 키를 넣은 뒤에도 "
    "자동 스윕으로도 [지금 보내기] 로도 영영 안 나갔다(복구는 DB 직접 수정뿐)")
_r = strip_py(func_body(APP, "def api_outbox_reopen"))
chk("status='수동처리'" in _r, "★ '수동처리' 만 되돌린다(이미 나간 '도달' 은 아니다)")
chk("obReopen" in ADM, "화면에 되돌리기 버튼이 있다")

# ── [5] 하한 없는 2차 경매 ────────────────────────────────────────
print("\n[5] 하한을 만들 근거가 없으면 2차 공고를 열지 않는다")
_oa = strip_py(func_body(APP, "def api_case_open_auction"))
chk("NO_FLOOR" in _oa,
    "★ 가견적도 개산 하단도 없으면 막는다",
    "개산 레시피가 없는 공종(조경·수목/종합 원상복구/방음벽)은 engine_low 가 0으로 남는다. "
    "가견적까지 0이면 하한 0인 채로 공고가 열려, 화면은 '이 아래로는 못 들어옵니다' 라고 "
    "말하는데 실제로는 아무 바닥도 없다 — 철칙 3·6 정면")
chk("engine_low" in _oa, "★ 2단 폴백(가견적 → 표준단가 개산 하단)을 그대로 본다")

# ── [6] 계정 발급 구분 ────────────────────────────────────────────
print("\n[6] 계정 일괄 발급이 시행사/시공사를 가린다")
chk("partner_type" in PA,
    "★ 구분으로 거른다",
    "통값 입찰은 시행사만 가능하다. 시공사만 뽑히면 경매를 열어도 투찰 자격자가 0곳이라 "
    "공고가 그대로 유찰된다 — 첫 주에 아무도 원인을 모른 채 멈춘다")
chk('"시행사"' in PA and "choices=" in PA, "★ 기본값이 시행사이고 골라 쓸 수 있다")
chk('"구분"' in PA, "★ 출력·CSV 에 구분이 찍힌다(시공사만 발급된 걸 눈치챌 수 있게)")

# ── [7] 돈 표시 ──────────────────────────────────────────────────
print("\n[7] 돈 숫자가 화면마다 같은 말을 한다")
_S = strip_js(ADM)
chk("fee_rate_bp||1000" not in _S.replace(" ", ""),
    "★ 0% 계약을 10% 로 인쇄하지 않는다",
    "`|| 1000` 은 0 이 falsy 라 0% 계약을 10% 로 만든다. 같은 파일이 이 함정을 "
    "두 번 고쳐 놓고 한 줄만 남아 있었다")
chk("s.fee_vat_included === false" not in _S,
    "★ 있지도 않은 키로 부가세 기준을 판정하지 않는다",
    "settlements 표에 fee_vat_included 컬럼이 없다 — undefined === false 는 늘 거짓이라 "
    "'부가세 별도' 분해 줄은 한 번도 렌더된 적이 없다")
chk("_vatInc" in _S and "tax.vat_included" in _S,
    "★ 상세 API 가 실제로 내려 주는 자리(tax.vat_included)를 읽는다")
chk("/1.1" not in _S.replace(" ", ""),
    "부가세 분해에 1.1 을 박아 두지 않는다(세율은 서버 값)")
#  ⚠ **주석을 지우고 본다.** 고친 자리에 "종전 문구는 「사건 등록 시점의 요율」이었다"
#    라고 적어 두면, 원문을 찾는 검사가 그 주석을 위반으로 읽는다(실제로 그랬다).
chk("사건 등록 시점의 요율" not in _S,
    "★ 요율 확정 시점을 코드와 같게 말한다",
    "코드에는 '사건 등록 시점' 이라는 규칙이 없다 — cases 에 요율 컬럼조차 없고, "
    "요율은 정산 행이 만들어지는 검수 승인 시점에 얼어붙는다")
_p = strip_js(PAR)
#  ⚠ **퍼센트를 화면에 찍는 줄**만 본다. 값을 계산만 하는 줄(중복 제거·정렬)에는
#    기준을 붙일 자리가 없다 — 그런 줄까지 잡으면 검사가 늑대소년이 된다.
_bad = [ln.strip()[:70] for ln in _p.splitlines()
        if "feePct(" in ln and "%" in ln and "vatNote()" not in ln]
chk(not _bad,
    f"★ 협력사 화면의 요율 표시에 부가세 기준이 함께 붙는다 ({PAR.count('vatNote()')}곳)",
    "'별도' 기준이면 실제 공제 총액은 요율×대금이 아니다 — 같은 줄에서 10%와 11%가 "
    "부딪힌다. " + (f"빠진 곳: {_bad[0]}" if _bad else ""))
chk('ws.append(["합계", _n_t' in APP,
    "★ 절감 리포트 합계의 건수와 금액이 같은 모집단에서 온다",
    "건수만 넓은 집계를, 금액 3칸은 좁은 집계를 써서 한 줄 안에서 서로 다른 사건 묶음을 "
    "말했다 — 보험사에 나가는 표다")

# ── [8] 잠금·반환값·파일 ─────────────────────────────────────────
print("\n[8] 잠금·반환값·파일")
_d = strip_py(func_body(APP, "def api_defect_create"))
chk("BEGIN IMMEDIATE" in _d,
    "★ 하자 채번을 쓰기 잠금 안에서 한다",
    "MAX 조회도 빈 번호 탐색도 자동커밋 읽기라 아무것도 예약하지 않았다 — 두 요청이 같은 "
    "번호를 보면 defect_no UNIQUE 에 걸려 한쪽 접수가 500 으로 사라진다")
chk("if not DP.decline(conn" in strip_py(APP),
    "★ 출동 거절의 반환값을 검사한다",
    "dispatch.py 는 '갱신된 행이 없으면 False' 를 돌려주도록 고쳐 놨는데 유일한 호출부가 "
    "통째로 버렸다 — 아무것도 안 써졌어도 200 ok:true 가 나가고 화면은 카드를 지운다")
_po = strip_py(func_body(MAN, "def cmd_prune_orphans"))
chk("_photo_rel" in _po and "shutil.move" in _po,
    "★ 고아 사진 행을 지울 때 파일도 함께 치운다",
    "주석은 '지우기 전에 경로를 확보해 둔다' 고 적혀 있었지만 실제로는 행만 지우고 파일은 "
    "영구히 남았다 — 어느 화면에도 안 뜨는데 디스크와 매일 백업에는 계속 쌓인다")
chk("_trash" in _po, "지우지 않고 휴지통으로 옮긴다(사진은 분쟁 자료다)")
_pp = strip_py(func_body(MAN, "def cmd_prune_personal"))
chk("os.walk(_tdir)" in _pp,
    "★ 휴지통 파기가 하위 폴더까지 본다",
    "삭제·정리는 rel_path 를 살려 `_trash/<사건id>/<파일>` 로 옮긴다 — 바로 아래 "
    "파일만 훑으면 그 중첩분이 영구히 안 지워진다(공개 처리방침의 파기 미이행)")
_of = strip_py(func_body(MAN, "def _orphan_photo_files"))
chk('os.path.join(root, "_trash")' in _of,
    "★ 고아 집계가 휴지통을 고아로 세지 않는다",
    "우리가 직접 옮겨 둔 것이라 DB 에 짝이 없는 게 당연한데 그걸 경고로 세면 "
    "**정리를 할수록 경고가 커진다**(실측 673 → 464)")

# ── [9] 약관·점검 ────────────────────────────────────────────────
print("\n[9] 약관·점검이 실제와 같은 말을 한다")
chk("발주처와의 계약에 따라 달리 정해질 수 있습니다" in LD,
    "★ 약관이 요율을 10% 로만 못 박지 않는다",
    "실제 공제율은 발주처별 계약값이고 '별도' 기준이면 총액이 11% 가 된다 — "
    "약관이 10% 고정이면 그 차액을 공제할 근거가 없다")
chk("부가가치세" in LD, "★ 약관에 부가세 기준이 언급된다")
chk("공종 커버리지" in MAN,
    "★ 점검이 공종 자료 누락을 알린다",
    "화면에서 고를 수 있는 공종이 판정표·표준단가·개산레시피에 다 있어야 한다")
chk("type(_e).__name__" in MAN,
    "★ 건너뛸 때 이유를 말한다",
    "이유 없는 '건너뜀' 은 통과처럼 읽힌다 — 실제로 이 검사가 두 번(RECIPES 형·표 이름) "
    "조용히 꺼진 채 지나갔다")

# ── 구문 ──────────────────────────────────────────────────────────
print("")
for f in ("app.py", "manage.py", "dispatch.py", "partner_accounts.py", "legal_docs.py"):
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
