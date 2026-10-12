# -*- coding: utf-8 -*-
"""도급 적법성 관문 — 이 건을 우리가 도급받아도 되는가.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

■ 왜 이 파일이 사업의 생명선인가
  복구온은 보험사에게 공사비를 직접 받아 시공사에 내려주는 구조(소액 도급)를 택했다.
  이때 **우리는 건설공사의 수급인이 된다.** 대법원은 직접 시공하지 않고 하도급만 해도
  '건설업을 한 것'으로 본다.

      대법원 2017. 7. 11. 선고 2017도1539
      "도급받은 건설공사 중 일부 또는 전부를 직접 시공하여 완성한 경우뿐만 아니라
       **하도급의 방식으로 시공하여 완성한 경우에도 건설업을 하였다**고 보아야 한다"

  무등록 건설업은 **5년 이하 징역 또는 5천만원 이하 벌금**(건설산업기본법 제95조의2 제1호).
  우리가 등록 없이 도급받을 수 있는 유일한 근거는 **'경미한 건설공사' 예외**뿐이다.

      건설산업기본법 제9조 제1항 단서 + 시행령 제8조 제1항
      · 종합공사: 1건 공사예정금액 5천만원 미만
      · 전문공사: 1건 공사예정금액 1천5백만원 미만

  즉 **이 관문이 뚫리면 형사 리스크가 그대로 열린다.** 그래서 금액·업종·분할을
  사람 판단이 아니라 코드로 막는다.

■ 이 관문이 막는 네 가지
  ① 금액 초과      — 경미 기준을 넘는 건은 우리가 도급받지 않는다(중개로 돌리거나 거절).
  ② 배제 업종      — 금액과 무관하게 경미 예외에서 빠지는 업종(강구조물 계열 등).
  ③ 분할 회피      — 같은 공사를 쪼개 기준을 피하는 것은 통하지 않는다.
                     대법원 2022. 2. 24. 선고 2018도3821 — 당사자·목적물·기간·내용·방법·
                     분할 경위를 종합해 실질적 동일성이 인정되면 **합산**한다.
                     우리 거래(동일 보험사·동일 유형·반복 수주)는 이 판단에 가장 취약하다.
  ④ 하수급인 자격  — 수급인은 시공자격을 갖춘 건설사업자에게 하도급해야 한다
                     (건설산업기본법 제25조 제2항). 무등록 영세업체에 내려주면 그 순간 위반이다.

■ 판정은 보수적으로 한다
  · 애매하면 '도급 불가'로 낸다. 통과시켜서 얻는 이익보다 뚫렸을 때 손실이 압도적으로 크다.
  · 업종 매핑이 확정되지 않은 공종은 통과시키지 않는다(미확인을 안전으로 취급하지 않는다).

■ 아직 확정하지 못한 것 (2026-07-28 기준)
  · 경미 예외 배제업종의 **현행 대업종 명칭 매핑**이 게시본마다 달라 확정하지 못했다
    (2020-02-18 전문건설업 대업종화 개정). 그래서 의심 공종은 전부 보수적으로 막는다.
  · 무등록자가 체결한 도급계약의 사법상 효력에 관한 확립 판례를 확인하지 못했다.
  · 최종 시행 전 시행령 원문과 국토교통부 질의로 확정할 것.
"""
import re
import sqlite3       # record_gate 가 기록 실패를 삼킬 때 잡는 예외 유형
import db as DB       # 지역 표기 정규화(norm_regions) — related_sum() 의 지역 판정용

# ── 경미한 건설공사 기준 (건설산업기본법 시행령 제8조 제1항) ──────────
#  ⚠ 금액은 '공사예정금액'이며 부가가치세 포함 여부는 시행령 원문·질의로 확정할 것.
#    현재는 보수적으로 **부가세 포함 총액**을 기준으로 본다(더 빨리 걸리는 쪽).
LIMIT_GENERAL = 50_000_000      # 종합공사 5천만원 미만
LIMIT_SPECIAL = 15_000_000      # 전문공사 1천5백만원 미만

# 우리가 실제로 쓰는 안전 여유 — 기준에 딱 붙이면 물량 변동·증액에서 바로 넘는다.
#  200만원대 소액이 주력이므로 여유를 크게 잡아도 사업에 지장이 없다.
SAFE_MARGIN = 0.8               # 기준의 80% 까지만 자동 통과

# ── 공종 → 소관 법률·업종 매핑 ────────────────────────────────────
#  건설산업기본법 제2조 제4호는 전기공사·정보통신공사·소방시설공사·국가유산수리공사를
#  '건설공사'에서 제외한다. 각각 다른 법률(전기공사업법 등)의 등록·예외 체계를 따르므로
#  건산법 경미 기준을 그대로 적용하면 안 된다.
LAW_CONSTRUCTION = "건설산업기본법"
LAW_ELECTRIC = "전기공사업법"
LAW_INFO = "정보통신공사업법"
LAW_FIRE = "소방시설공사업법"

# 판정표 버전 — **판정표를 고치면 반드시 올린다.**
#  과거 판정이 어떤 표로 내려진 것인지 재현할 수 있어야 소명이 된다.
#  (표가 바뀐 뒤 옛 사건을 다시 판정하면 다른 답이 나오는데, 그때 무엇이 맞았는지
#   가릴 근거가 이 값이다)
RULES_VERSION = "2026.09-1"

# 공종별 판정표
#   kind: general(종합) / special(전문) / excluded(경미예외 배제) / other_law(다른 법률 소관)
#   note: 왜 그렇게 보는지
WORK_RULES = {
    "가드레일·방호울타리": {
        "kind": "excluded", "law": LAW_CONSTRUCTION,
        "note": "강구조물 계열로 분류되면 금액과 무관하게 경미 예외에서 배제될 수 있다. "
                "현행 대업종 매핑 미확정 → 보수적으로 도급 불가로 본다.",
    },
    "유리·샷시·자동문": {
        "kind": "special", "law": LAW_CONSTRUCTION,
        "note": "창호·유리 공사(전문). 자동문의 제어·전기 부분이 크면 전기공사업법 소관이 섞인다.",
    },
    "셔터·차단기·게이트": {
        "kind": "other_law", "law": LAW_ELECTRIC,
        "note": "차단기·게이트는 전기·제어 비중이 커 전기공사업법 소관일 수 있다. "
                "건산법 경미 기준을 그대로 쓰면 안 된다 → 개별 확인 필요.",
    },
    "누수·배관·설비": {
        "kind": "special", "law": LAW_CONSTRUCTION,
        "note": "기계설비·배관 공사(전문).",
    },
    "외벽·석재·담장·조적": {
        "kind": "special", "law": LAW_CONSTRUCTION,
        "note": "조적·미장 공사(전문).",
    },
    "도장·방수·미장": {
        "kind": "special", "law": LAW_CONSTRUCTION,
        "note": "도장·방수 공사(전문).",
    },
    "교통안전시설": {
        "kind": "excluded", "law": LAW_CONSTRUCTION,
        "note": "표지·방호 구조물이 강구조물 계열에 걸릴 수 있다 → 보수적으로 도급 불가.",
    },
    "지붕·판넬·캐노피": {
        "kind": "excluded", "law": LAW_CONSTRUCTION,
        "note": "판넬·캐노피 구조물이 강구조물 계열에 걸릴 수 있다 → 보수적으로 도급 불가.",
    },
    "간판·전기·가로등": {
        "kind": "other_law", "law": LAW_ELECTRIC,
        "note": "가로등·보안등·간판 전기공사는 전기공사업법 소관. 건산법 경미 기준 적용 불가.",
    },
    "조경·수목": {
        "kind": "special", "law": LAW_CONSTRUCTION,
        "note": "조경식재 공사(전문).",
    },
    "종합 원상복구": {
        "kind": "general", "law": LAW_CONSTRUCTION,
        "note": "여러 공종이 섞이면 종합공사로 본다(기준 5천만원).",
    },
    "기타": {
        "kind": "unknown", "law": LAW_CONSTRUCTION,
        "note": "업종이 특정되지 않았다 → 판정 불가. 사람이 분류해야 한다.",
    },
}

# 판정 코드
OK_DIRECT = "도급가능"          # 우리가 도급받아도 되는 건
NO_AMOUNT = "금액초과"          # 경미 기준 초과 → 도급 불가
NO_TRADE = "배제업종"           # 금액 무관 배제 업종
NO_LAW = "타법소관"             # 전기·정보통신·소방 등 다른 법률
NO_SPLIT = "분할의심"           # 같은 공사 쪼개기 의심 → 합산 시 초과
NO_UNKNOWN = "판정불가"         # 업종 미확정


def limit_for(kind):
    """이 업종 구분의 경미 기준 금액(원). 판정 불가면 None."""
    if kind == "general":
        return LIMIT_GENERAL
    if kind == "special":
        return LIMIT_SPECIAL
    return None


def _norm(s):
    return re.sub(r"\s+", "", (s or "")).replace("ㆍ", "·").replace("･", "·")


def _fuzzy_hits(token):
    t = _norm(token)
    return [(k, v) for k, v in WORK_RULES.items()
            if t and (_norm(k) in t or t in _norm(k))]


def rule_for(category):
    """공종 문자열로 판정 규칙을 찾는다. 못 찾으면 '기타'.

    ⚠ 여러 업종이 '·'로 이어붙은 복합공종 문자열(예: 유리·샷시·자동문·교통안전시설)에서는
      **가장 보수적인(막는) 규칙이 이긴다.** 부분일치를 사전 등록 순서로만 찾으면, 배제업종
      (교통안전시설)이 그보다 먼저 등록된 특별공사(유리·샷시·자동문) 뒤에 붙었다는 이유만으로
      전체가 도급가능으로 새는 사고가 실측됐다 — check_direct_contract('유리·샷시·자동문·
      교통안전시설', ...) 가 배제업종을 건너뛰고 특별공사(금액 기준 통과)로 판정했다.
      '애매하면 도급 불가로 낸다'는 이 파일의 원칙과 정면으로 어긋난다 — 막는 쪽(kind 가
      unknown·excluded·other_law)이 하나라도 걸리면 그걸 우선한다.

    ⚠⚠ [라운드278] 위 수정은 "여러 업종이 다 판정표에 있는데 그중 뭐가 이기는가"만
      다룬다 — 업종 하나가 **판정표에 아예 없는 경우**(예: WORK_MAJORS 12개 중
      '방음벽·휀스·펜스'가 WORK_RULES 에 빠져 있음, manage.py selfcheck 가 이미
      실측 기록)는 못 잡는다. app.py 는 복합공종을 "복합(A · B · C)" 로 이어붙이는데
      (각 원소엔 " · " 가 안 들어간다 — 그대로 쪼개면 원래 업종 목록이 복원된다),
      기존 로직은 이 전체 문자열에 부분일치를 걸어 **하나라도 걸리면 그걸로 전체를
      판정**했다. 실측: '복합(방음벽·휀스·펜스 · 누수·배관·설비)' 가 누수·배관·설비의
      규칙(전문공사, 1500만원)만으로 판정돼, 판정표에 없는 방음벽·휀스·펜스 몫은
      위험도 평가 자체를 안 거친 채 800만원짜리 건이 그대로 '도급가능'으로 통과했다
      (직접 실행으로 재현). 토큰별로 쪼개 **하나라도 부분일치조차 없으면** 전체를
      '기타'(판정불가)로 낸다 — 37행의 원칙을 복합공종에도 실제로 적용한다. 개별
      업종(방음벽·휀스·펜스 등)을 판정표에 어떤 kind로 넣을지는 법률 판단이라
      이 수정 범위가 아니다(파일 상단 "아직 확정하지 못한 것" 참고) — 여기서 하는
      일은 "빠진 업종이 조용히 무시되지 않게" 만드는 것뿐이다.
    """
    c = _norm(category)
    for k, v in WORK_RULES.items():
        if _norm(k) == c:
            return k, v

    m = re.match(r"^복합\((.*)\)$", category or "")
    if m:
        tokens = [t.strip() for t in m.group(1).split(" · ") if t.strip()]
        if tokens:
            #  ⚠⚠ [라운드315] 토큰이 전부 판정표에 있으면(아래) 바로 밑의 부분일치
            #    폴백(hits = _fuzzy_hits(category))으로 넘어갔는데, 그건 복합문자열
            #    전체에 부분일치를 걸어 **WORK_RULES 딕셔너리 등록순서상 먼저 오는
            #    트레이드 하나**만 그대로 썼다 — 나머지 트레이드는 판정에서 완전히
            #    사라졌다. 실측: '복합(유리·샷시·자동문 · 조경·수목)'처럼 배제업종이
            #    안 섞인 special 트레이드 2개가 결합해도, 상단 120~122행이 이미
            #    "여러 공종이 섞이면 종합공사로 본다"고 명시한 원칙이 실제로는 한
            #    번도 적용된 적 없이 그냥 15,000,000원(전문공사 단일 한도)으로
            #    고정 판정됐다(딕셔너리 순서라는 우연에 의존 — 표에 항목을 추가·
            #    재배열하면 어떤 조합이 통과하는지 조용히 바뀐다). 토큰별로
            #    재귀 판정해 막는 kind 우선순위(기존과 동일)는 유지하고, 그 외엔
            #    서로 다른 트레이드가 몇 개 섞였는지로 종합/전문을 가른다.
            resolved = [rule_for(t) for t in tokens]
            if any(name == "기타" for name, _ in resolved):
                return "기타", WORK_RULES["기타"]
            for name, rule in resolved:
                if rule["kind"] in ("unknown", "excluded", "other_law"):
                    return name, rule
            distinct = {name for name, _ in resolved}
            if len(distinct) >= 2:
                return "종합 원상복구", WORK_RULES["종합 원상복구"]
            return resolved[0]

    # 부분 일치도 허용(공종명이 조금씩 다르게 들어오는 현실 대응)
    hits = _fuzzy_hits(category)
    for k, v in hits:
        if v["kind"] in ("unknown", "excluded", "other_law"):
            return k, v
    if hits:
        return hits[0]
    return "기타", WORK_RULES["기타"]


def check_direct_contract(category, amount, related_amount=0):
    """이 건을 우리가 도급받아도 되는가.

    category       공종
    amount         이 건의 공사예정금액(원)
    related_amount 같은 공사로 합산될 수 있는 관련 건들의 합(원) — 분할 회피 방지

    반환 dict: code / ok / limit / reason / law / note
    """
    name, rule = rule_for(category)
    kind, law = rule["kind"], rule["law"]
    #  ⚠⚠ [라운드651] int(amount or 0) 는 amount 가 float('inf')/float('-inf')/
    #    float('nan') 이면 ValueError 가 아니라 OverflowError(inf) 또는
    #    ValueError(nan, "cannot convert float NaN to integer")를 던진다 —
    #    형제(app.py _setting_int 라운드485, _ai_threshold 라운드631)가 이미
    #    겪고 고친 것과 같은 함정이다(실측: 직접 호출로 재현). 지금 이 함수의
    #    실제 호출부(app.py record_gate 5곳)는 전부 parse_money() 로 이미
    #    걸러진 금액만 넘기므로 오늘 당장 이 경로로 도달하지는 않지만, 이
    #    함수는 db·app 을 모르는 **공용 순수함수**로 문서화돼 있어 호출부의
    #    사전 검증에 기대지 않는 것이 이 파일 자신의 "애매하면 도급 불가로
    #    낸다" 원칙과 맞다 — amount 를 못 읽으면 통과(0원 취급)시키지 않고
    #    형제 분기(kind=="unknown")와 같은 모양으로 막는다.
    try:
        amt = int(amount or 0)
        rel = int(related_amount or 0)
    except (TypeError, ValueError, OverflowError):
        return {"category": name, "law": law, "note": rule["note"],
                "amount": None, "related": None, "code": NO_UNKNOWN, "ok": False,
                "limit": None,
                "reason": "공사예정금액(또는 관련 건 합산액)을 숫자로 읽을 수 없습니다. "
                          "값을 다시 확인한 뒤 판정하세요."}

    base = {"category": name, "law": law, "note": rule["note"],
            "amount": amt, "related": rel}

    if kind == "unknown":
        raw = (category or "").strip()
        #  ⚠⚠ [라운드278] "공종이 특정되지 않아"는 진짜 미입력일 때만 맞는 말이다.
        #    rule_for() 가 '기타'로 떨어지는 두 번째 경로(공종은 있는데 판정표에 없음,
        #    또는 복합공종 중 하나가 판정표에 없음)에도 같은 문구를 썼더니, 실제로는
        #    체크박스로 '방음벽·휀스·펜스'를 정확히 골랐는데도 "특정되지 않아"라고
        #    나와 운영자가 접수 자체가 잘못됐다고 오인하기 쉬웠다 — 진짜 원인(판정표
        #    누락)을 감춰 manage.py check 의 기존 경고로 이어지지 못했다.
        reason = (f"공종 '{raw}'이(가) 아직 도급판정표에 없어 적용 법률과 기준을 정할 수 "
                  f"없습니다. manage.py check 로 누락 공종을 확인해 판정표(WORK_RULES)에 "
                  f"추가한 뒤 다시 판정하세요." if raw else
                  "공종이 특정되지 않아 적용 법률과 기준을 정할 수 없습니다. "
                  "사람이 공종을 분류한 뒤 다시 판정하세요.")
        return {**base, "code": NO_UNKNOWN, "ok": False, "limit": None, "reason": reason}
    if kind == "other_law":
        return {**base, "code": NO_LAW, "ok": False, "limit": None,
                "reason": f"{law} 소관 공사로 보입니다. 건설산업기본법의 경미한 건설공사 "
                          f"기준을 그대로 적용할 수 없어 우리가 도급받지 않습니다."}
    if kind == "excluded":
        return {**base, "code": NO_TRADE, "ok": False, "limit": None,
                "reason": "경미한 건설공사 예외에서 배제될 수 있는 업종입니다"
                          "(금액과 무관). 우리가 도급받지 않고 중개로 처리하세요."}

    lim = limit_for(kind)
    safe = int(lim * SAFE_MARGIN)
    total = amt + rel

    # ★ 분할 회피 방지 — 관련 건을 합쳐 판단한다(대법원 2018도3821)
    if rel and total >= safe:
        return {**base, "code": NO_SPLIT, "ok": False, "limit": lim,
                "reason": f"같은 공사로 합산될 수 있는 관련 건을 더하면 {total:,}원으로 "
                          f"안전선({safe:,}원)을 넘습니다. 쪼개서 기준을 피하는 것은 "
                          f"판례상 인정되지 않습니다(대법원 2018도3821). 중개로 처리하세요."}
    if amt >= safe:
        return {**base, "code": NO_AMOUNT, "ok": False, "limit": lim,
                "reason": f"공사예정금액 {amt:,}원이 안전선({safe:,}원, 경미 기준 {lim:,}원의 "
                          f"{int(SAFE_MARGIN*100)}%)을 넘습니다. 우리가 도급받으면 무등록 "
                          f"건설업 위험이 생기므로 중개로 처리하세요."}

    return {**base, "code": OK_DIRECT, "ok": True, "limit": lim,
            "reason": f"경미한 건설공사 기준({lim:,}원 미만) 안입니다. "
                      f"안전선 {safe:,}원 이내로 도급 가능합니다."}


def check_subcontractor(partner_row):
    """하수급인(시공사)이 건설업 등록을 갖췄는가 — 건설산업기본법 제25조 제2항.

    우리가 수급인이 되면 **등록 건설사업자에게만** 하도급할 수 있다.
    무등록 업체에 내려주면 그 자체로 위반이다(제96조 제4호 · 제82조 영업정지·과징금).

    partner_row 는 partners 테이블 행(dict 또는 sqlite3.Row).
    """
    def _g(k):
        try:
            v = partner_row[k]
        except (KeyError, IndexError, TypeError):
            v = None
        return (v or "") if isinstance(v, str) else v

    #  ⚠⚠ [라운드106] 예전엔 partners.license(입점신청 때 업체가 스스로 적은
    #    자유텍스트, api_partner_license 조사 라우트는 아예 안 건드리는 컬럼)
    #    를 봤다 — 실제 조사 결과가 쌓이는 곳은 license_status 인데, 정본
    #    강제규칙(dispatch.py license_block_reason)은 이미 그 컬럼을 본다.
    #    실측(운영 399곳): license_status='등록확인'은 단 1곳뿐인데 그 업체의
    #    옛 license 텍스트가 비어 있어 이 함수는 "등록미확인"으로 오판했고,
    #    반대로 license_status 가 미확인/무등록인 146곳은 옛 license 텍스트가
    #    남아 있다는 이유만으로 "등록확인"(하도급 가능)으로 오판했다 — 방향이
    #    반대다. '미확인'(아직 조사 안 함)은 license_block_reason 과 달리
    #    여기서는 통과시키지 않는다 — 이 함수의 목적 자체가 "지금 하도급해도
    #    되는가"에 대한 사전 답이므로, 확인 안 된 상태를 안전으로 보지 않는다.
    status = _g("license_status") or "미확인"
    name = _g("name") or ""
    if status == "무등록":
        return {"ok": False, "code": "무등록", "partner": name,
                "reason": "건설업 미등록으로 확인된 업체입니다. "
                          "우리가 도급받은 공사를 이 업체에 하도급할 수 없습니다"
                          "(건설산업기본법 제25조 제2항)."}
    if status != "등록확인":
        return {"ok": False, "code": "등록미확인", "partner": name,
                "reason": "건설업 등록 여부가 아직 조사되지 않았습니다. 등록 조사를 마치기 "
                          "전에는 우리가 도급받은 공사를 이 업체에 하도급할 수 없습니다"
                          "(건설산업기본법 제25조 제2항)."}
    return {"ok": True, "code": "등록확인", "partner": name,
            "license": _g("license_no") or "",
            "reason": "건설업 등록이 확인된 업체입니다. 업종 적합성은 공종별로 "
                      "추가 확인하세요."}


def _case_trades(conn, cid, category):
    """이 사건의 공종 목록 — work_lots 에서 읽는다.

    ⚠⚠ [라운드122] dispatch.py:_case_trades() 와 반드시 같은 규칙을 유지한다 — 이 파일
      자신의 상단 docstring이 "당사자·동일유형·반복수주가 이 판단에 가장 취약하다"고
      말하는 바로 그 판정(related_sum, 형사책임 직결)이 정작 cases.category **표시용
      문자열**을 완전일치로만 비교했다. 복합사건은 '복합(가드레일 · 유리)' 라는 문자열이라
      단독 '가드레일'·'유리' 사건과도, 트레이드 순서만 달라도 다른 복합사건과도 절대
      매칭되지 않는다 — 정확히 dispatch.py/app.py 에서 이미 3번 고쳐진 것과 같은 결함이다.
    """
    lots = [r["category"] for r in conn.execute(
        "SELECT category FROM work_lots WHERE case_id=? ORDER BY id", (cid,)).fetchall()
        if r["category"]]
    if lots:
        return lots
    cat = (category or "").strip()
    return [cat] if cat and "복합(" not in cat else []


def related_sum(conn, case_id):
    """이 사건과 '같은 공사'로 합산될 수 있는 관련 건들의 금액 합.

    판례 기준(당사자·목적물·기간·내용·방법·분할 경위)을 코드로 완전히 재현할 수는 없다.
    그래서 **가장 위험한 조합**만 보수적으로 잡는다 —
    같은 보험사 + 같은 공종 + 같은 지역 + 최근 30일.
    이 조합이면 '실질적으로 하나의 공사'로 볼 여지가 있으므로 합산해서 경고한다.

    ⚠⚠ [라운드122] "같은 공종" 은 이제 work_lots 기준 실제 트레이드가 하나라도
      겹치는지로 본다(둘 다 쪼개져 있을 때). 어느 한쪽이라도 아직 안 쪼개졌으면
      (2트랙 사진없는 접수 등, 289행 주석 참조) 예전 방식(category 문자열 완전일치)
      으로 안전하게 되돌아간다 — "애매하면 도급불가"(이 파일의 원칙)를 따라, 정보가
      부족하다고 판정을 느슨하게 풀지 않는다.
    ⚠ 이 함수는 "같은 공종" 하나만 넓힌 것이다 — 트레이드가 전혀 다른 두 건(예: 같은
      사고현장의 가드레일 손상과 유리 손상을 공종별로 나눠 접수)을 같은 공사로 볼지는
      별개의 법률 판단(실질적 동일성의 "내용" 요건을 어디까지 볼 것인가)이라 이번
      수정 범위가 아니다 — 필요하면 법률 검토 후 별도로 넓혀야 한다.

    ⚠⚠ [라운드196] "같은 지역"은 예전에 SQL 에서 region 원문 문자열 완전일치로
      걸렀다 — cases.region 은 정규화 안 된 자유텍스트라(app.py 지역정규화 주석이
      말하는 그 149가지 문제와 같은 표기 불일치가 여기도 그대로 있다), "인천 남동"과
      "인천광역시 남동구"처럼 같은 지역을 다르게 적으면 "다른 지역"으로 오판해
      합산을 놓쳤다 — 개별 건이 전문공사 안전선 아래면 check_direct_contract() 가
      조용히 통과시키고, _gate_alert() 는 ok=True 일 때 알림조차 안 보내 사람이
      검토할 기회 자체가 없었다. DB.norm_regions() 로 양쪽을 정규화해 교집합으로
      본다(입찰채점 등 다른 소비처와 같은 판단 기준) — 정규화가 안 되는 표기는
      "다른 지역"이라고 단정하지 않고 이 파일의 원칙("애매하면 도급불가")대로
      합산 쪽으로 기운다.
    """
    c = conn.execute(
        "SELECT insurer_id, category, region, created_at FROM cases WHERE id=?",
        (case_id,)).fetchone()
    if not c:
        return 0, []
    my_trades = set(_case_trades(conn, case_id, c["category"]))
    my_regions = set(DB.norm_regions(c["region"]))
    rs = conn.execute(
        """SELECT id, case_no, category, region, created_at,
                  -- ⚠ 관련 건의 금액은 **확정가 우선**이다. est_price 만 더하면,
                  --   사진 없이 접수돼 제시금액이 비어 있는 건(2트랙의 상시 상태)이
                  --   전부 0원으로 세어져 분할 회피 판정이 통째로 죽는다.
                  --   현재 사건 쪽은 이미 낙찰가로 판정하고 있어 기준도 어긋났다.
                  COALESCE(NULLIF(award_amount,0), NULLIF(low_price,0),
                           est_price, 0) AS est_price
             FROM cases
            WHERE id <> ?
              AND COALESCE(insurer_id,0) = COALESCE(?,0)
              AND COALESCE(is_demo,0) = 0
              AND datetime(created_at) >= datetime(?, '-30 days')
              AND datetime(created_at) <= datetime(?, '+30 days')""",
        (case_id, c["insurer_id"],
         c["created_at"], c["created_at"])).fetchall()
    related = []
    for r in rs:
        other_trades = set(_case_trades(conn, r["id"], r["category"]))
        if my_trades and other_trades:
            same_trade = bool(my_trades & other_trades)
        else:
            same_trade = bool(c["category"]) and c["category"] == r["category"]
        other_regions = set(DB.norm_regions(r["region"]))
        if my_regions and other_regions:
            same_region = bool(my_regions & other_regions)
        else:
            same_region = True
        if same_trade and same_region:
            related.append(r)
    total = sum(int(r["est_price"] or 0) for r in related)
    return total, [{"id": r["id"], "case_no": r["case_no"],
                    "amount": int(r["est_price"] or 0)} for r in related]


def gate(conn, case_id, amount=None):
    """사건 하나에 대한 최종 판정 — 라우트·화면이 쓰는 입구.

    반환에 관련 건 목록까지 담아, 왜 막혔는지가 화면에서 바로 보이게 한다.
    """
    c = conn.execute(
        "SELECT id, case_no, category, est_price, award_amount, low_price "
        "  FROM cases WHERE id=?", (case_id,)).fetchone()
    if not c:
        return {"ok": False, "code": NO_UNKNOWN, "reason": "없는 사건입니다."}
    #  ⚠ 확정가가 있으면 그것이 공사예정금액이다 — related_sum() 이 이미 쓰는 식
    #    (COALESCE(award_amount, low_price, est_price))과 맞춘다. est_price 만 보면
    #    ①낙찰 뒤 금액이 오른 사건도 옛(가견적) 기준으로 판정되고
    #    ②사진 없이 접수된 2트랙 건(est_price 가 늘 비어 있음)은 판정금액이 상시
    #    0원이 되어 어떤 계약금액이든 항상 '도급가능'이 뜬다(화면·API 실측 확인됨).
    #  ⚠⚠ [라운드651] 이 int() 도 check_direct_contract() 와 같은 함정이다 —
    #    amount 오버라이드(호출부가 명시적으로 넘긴 값)가 inf/nan 이면 여기서
    #    바로 크래시해, 아래 check_direct_contract() 자체 가드(막 고친 부분)에
    #    닿기도 전에 이 함수(라우트가 실제로 쓰는 입구)가 죽는다. 같은 방식으로 막는다.
    try:
        amt = int(amount if amount is not None
                  else (c["award_amount"] or c["low_price"] or c["est_price"] or 0))
    except (TypeError, ValueError, OverflowError):
        return {"ok": False, "code": NO_UNKNOWN, "case_no": c["case_no"], "related_cases": [],
                "reason": "공사예정금액을 숫자로 읽을 수 없습니다. 값을 다시 확인한 뒤 판정하세요.",
                "fallback": "중개(우리가 도급받지 않고 보험사↔시공사 직접 계약)"}
    rel, rel_list = related_sum(conn, case_id)
    res = check_direct_contract(c["category"], amt, related_amount=rel)
    res["case_no"] = c["case_no"]
    res["related_cases"] = rel_list
    # 막힌 건은 무엇으로 처리해야 하는지까지 알려준다(막고 끝내면 운영이 멈춘다)
    res["fallback"] = ("중개(우리가 도급받지 않고 보험사↔시공사 직접 계약)"
                       if not res["ok"] else "")
    return res


def record_gate(conn, case_id, route, actor, amount=None, override_reason=None):
    """확정 시점의 도급 적법성 판정을 **스냅샷으로 저장**한다.

    ⚠ 판정을 막는 함수가 아니다(막는 것은 운영 판단이다). 여기서 하는 일은
      '그때 이 표로, 이 금액으로, 이 관련 건들을 합산해 이렇게 판정했다'를 남기는 것뿐이다.
      그 기록이 없으면 나중에 왜 직접 도급했는지 증명할 방법이 없다.

    gate() 는 순수 조회로 유지하고, 쓰기는 이 함수만 한다.
    반환은 저장한 판정 dict(호출부가 로그·응답에 쓸 수 있게).

    ⚠⚠ [라운드315, 미해결·제품판단 필요] override_reason 은 실제로는 아무 호출부도
      값을 안 넘긴다(app.py 의 5개 호출부 전수 확인 — 전부 키워드 인자 자체가 없음)
      — contract_gate_log.override_reason 컬럼은 스키마상으로만 존재하고 실제로는
      항상 NULL 이다. 판정이 ok=False 로 나와도 낙찰·1차합의 승인 자체는 안 막으므로
      (바로 위 설계원칙), 운영자가 경고를 보고도 의식적으로 강행하는 경우가 있을 수
      있는데 그 "왜 넘겼는지" 사유가 하나도 안 남는다는 뜻 — 이 함수의 존재 이유
      (나중에 소명 가능해야 한다)와 어긋난다. 다만 이 값을 누가·언제 입력할지는
      "강행 확인 UI를 새로 만들 것인가"라는 제품 판단이 필요해(현재 화면엔 그런
      확인 동선 자체가 없다), 이번 라운드는 배선 문제를 발견만 하고 임의로
      새 UI/API 계약을 만들지 않는다 — 다음 라운드도 이 사실만으로 재조사하지
      말 것(이미 파악됨), 강행 확인 흐름을 만들라는 지시가 오면 그때 배선한다.
    """
    res = gate(conn, case_id, amount=amount)
    try:
        rel_nos = ", ".join(
            str(x.get("case_no") or x.get("id") or "") for x in (res.get("related_cases") or [])
        )[:500]
        conn.execute(
            """INSERT INTO contract_gate_log
                   (case_id, case_no, code, ok, category, law, amount, related_amount,
                    related_case_nos, limit_amount, reason, rules_version, route,
                    decided_at, decided_by, override_reason)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now','+9 hours'),?,?)""",
            (case_id, res.get("case_no"), res.get("code"), 1 if res.get("ok") else 0,
             res.get("category"), res.get("law"), int(res.get("amount") or 0),
             int(res.get("related") or 0), rel_nos, int(res.get("limit") or 0),
             (res.get("reason") or "")[:500], RULES_VERSION, route,
             actor or "시스템", (override_reason or None)))
    except sqlite3.Error:
        # 기록 실패가 낙찰·승인 자체를 되돌리지 않게 한다(본 처리가 우선).
        #  다만 조용히 지나가지 않도록 호출부가 알 수 있게 표시를 남긴다.
        res["_log_failed"] = True
    return res
