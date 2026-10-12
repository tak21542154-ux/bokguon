# -*- coding: utf-8 -*-
"""수선패턴 카탈로그 + 원격 자동견적 엔진 (착수본).

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

■ 무엇인가
  표준단가표(seed_boq)는 '단가 사전'일 뿐 수량이 없어 스스로 견적을 못 낸다.
  이 모듈은 그 위에 **'수량·조립 계층(수선 레시피)'**을 얹어,
  입력 몇 개(연장·개수·면적…)만으로 소액 공사의 **개산 시공비 구간**을 자동 산출한다.
  소액 다빈도(견적가 100만원 이하 70~80%)를 사람 없이 견적하기 위한 뼈대다.

■ 반드시 지키는 선 (손해사정 경계 — 06_법률검토 참조)
  · 이 엔진이 내는 값은 **'시공 개산가(제안 상한)'**이지 보험금·손해액이 아니다.
  · 그래서 **단일 확정가를 만들지 않는다.** 항상 '구간(낮음~높음) + 산출 근거'로 낸다.
  · est_price 를 자동 확정하지 않는다(그건 사람·보험사 몫).
  · 파손 정도를 판정하지 않는다.

■ 값의 출처 (출처검증)
  단가는 전부 기존 seed_boq.py / seed_boq_led.py 의 **실측·검증된 값**을 그대로 쓴다.
  카탈로그에 없어 아직 못 채운 구성요소는 지어내지 않고 'needs_calibration' 으로 표시해
  자동발행에서 빼고 실측으로 보낸다. (근거 없는 값을 활성 상태로 두지 않는다)

■ 원가구성(직접공사비→총액) 할증은 아직 '가정'이다
  간접비·이윤·부가세 합성요율은 실낙찰 데이터로 보정하기 전까지 보수적 밴드로 둔다.
  그래서 결과가 '점'이 아니라 '구간'으로 나온다(불확실성을 숨기지 않는다).

실행(데모):  python repair_estimate.py
"""
import io
import sys
import math

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── 설정 ─────────────────────────────────────────────────────────
# 정률 10% 수수료로 현장 실측을 감당하려면 견적가가 실측원가의 약 10배는 돼야 한다.
# 실측원가(교통+시간)를 약 10만원으로 보면 손익분기 = 약 100만원.
# → 예상 상한이 이 값을 넘으면 원격확정하지 않고 실측으로 보낸다.
# (영진건설 인터뷰에서 실측 1회 실제 원가를 받으면 이 값을 실측으로 대체한다.)
REMOTE_MAX = 1_000_000

# 직접공사비 → 총액 할증(간접노무비·경비·일반관리비·이윤) + 부가세.
#  ⚠ 합성요율은 '가정'이다(국가계약 원가계산 기준 범위). 실낙찰로 보정 필요.
#     그래서 낮음~높음 밴드로 두고, 결과를 구간으로 낸다.
MARKUP_LO = 1.25
MARKUP_HI = 1.50
VAT = 1.10
MARKUP_SRC = "가정 — 직접공사비 대비 간접비·이윤 1.25~1.50배 + 부가세 10%. 실낙찰 데이터로 보정 필요"

# 엔진 버전 — **단가·MARKUP·KFACTOR·수선패턴을 고치면 반드시 올린다.**
#  저장된 합의 근거가 어느 시점 기준으로 계산된 값인지 알 수 있어야, 단가 개정 뒤에도
#  과거 건을 소명할 수 있다(같은 입력이라도 버전이 다르면 결과가 다르다).
ENGINE_VER = "2026.08-2"

# 공종별 실거래 보정계수 k. 자체 낙찰가가 쌓이면 (낙찰가÷base)의 중앙값으로 갱신한다.
#  아직 데이터가 없으므로 전부 1.0(보정 없음)에서 출발한다.
KFACTOR = {}          # 예: {'가드레일·방호울타리': 0.95}
KFACTOR_DEFAULT = 1.0


# ── 단가(SKU) — 전부 기존 seed 실측값. (이름, 규격, 단위, 단가, 성격, 근거요약) ──
SKU = {
    # 가드레일
    "gr_panel":       ("가드레일 판(2W)", "4t×350×4330", "개", 110000, "자재", "건자재114 2026-04 자재비"),
    "gr_post":        ("가드레일 매립지주", "Ø139.8×4.5t×2200", "개", 62400, "자재", "건자재114 2026-04 자재비"),
    "gr_cap":         ("가드레일 캡", "Ø139.8", "개", 1500, "자재", "건자재114 2026-04 자재비"),
    "gr_bolt_c":      ("취부볼트", "Ø19×180", "개", 1100, "자재", "건자재114 2026-04 자재비"),
    "gr_bolt_y":      ("연결볼트", "Ø16×33", "개", 400, "자재", "건자재114 2026-04 자재비"),
    "gr_panel_ins4":  ("가드레일 판 설치비", "지주간격 4m", "m", 2356, "시공", "국토부 2026하 표준시장단가 LH311.22400(재료비 제외)"),
    "gr_panel_ins2":  ("가드레일 판 설치비", "지주간격 2m", "m", 3083, "시공", "국토부 2026하 표준시장단가 LH311.22400(재료비 제외)"),
    "gr_post_ins4":   ("가드레일 지주 설치비", "지주간격 4m·항타", "m", 2164, "시공", "국토부 2026하 표준시장단가 LH311.10400(재료비 제외)"),
    "gr_post_ins2":   ("가드레일 지주 설치비", "지주간격 2m·항타", "m", 4329, "시공", "국토부 2026하 표준시장단가 LH311.10400(재료비 제외)"),
    # 유리·창호
    "glass_temp12":   ("강화유리 12mm", "투명 12mm", "㎡", 39250, "자재", "한국물가정보 2026 자재비"),
    "glass_pair24":   ("복층유리 24mm", "투명 24mm 복층", "㎡", 35721, "자재", "한국물가정보 2026 자재비"),
    "glass_ins":      ("창호유리 설치비", "유리두께 12mm 이하", "㎡", 34363, "시공", "국토부 2026하 표준시장단가(재료비 제외)"),
    "sash_ins":       ("알루미늄창호 설치비", "창호면적 3.0~6.0㎡", "개소", 116351, "시공", "국토부 2026하 표준시장단가(재료비 제외)"),
    # 차단기
    "bar_plain":      ("주차차단기 바(직선형)", "4M", "개", 132000, "자재", "현대파킹 2026-07 공개판매가"),
    "bar_led":        ("주차차단기 바(LED)", "사각 LED 3~4M", "개", 250000, "자재", "현대파킹 2026-07 공개판매가"),
    "worker_special": ("특별인부 노임", "1일 8시간", "인", 226122, "노무", "대한건설협회 2026상반기 임금실태 직종1003"),
    # 등기구
    "led_fixture150": ("LED 가로등기구 자재", "150W 일체형 일반형", "등", 299000, "자재", "오렌지라이팅 2026-07 공개판매가"),
    "led_sec_ins_p":  ("LED 보안등기구 설치비", "50W 이하·전용등주 부착", "개", 50083, "시공", "대한전기협회 2026 표준품셈 5-26-3(내선전공 0.183인)"),
    "led_sec_ins_k":  ("LED 보안등기구 설치비", "50W 이하·한전주 부착", "개", 75939, "시공", "대한전기협회 2026 표준품셈 5-26-3(배전전공 0.183인)"),
    # 배관
    "pipe_pb":        ("폴리부틸렌관 자재", "20A", "m", 1320, "자재", "천지배관자재몰 2026-07 공개판매가"),
    "pipe_sus":       ("스테인리스 주름관 자재", "15A 비열처리", "m", 1900, "자재", "유성몰 2026-07 공개판매가"),
    "pipe_pb_ins":    ("폴리부틸렌관 시공비", "20A 옥내 급수·급탕", "m", 13337, "시공", "2026 기계설비 적용품셈 1-6-1(재료비 제외)"),
    "pipe_sus_ins":   ("스테인리스 주름관 시공비", "15A 옥내 일반배관", "m", 13357, "시공", "2026 기계설비 적용품셈(재료비 제외)"),
    # 담장·조적 (시공비만 — 자재비는 카탈로그 미보유)
    "brick_05b":      ("시멘트벽돌 쌓기 0.5B", "높이 3.6m 이하", "㎡", 27221, "시공", "국토부 2026하 표준시장단가(재료비 제외)"),
    "brick_10b":      ("시멘트벽돌 쌓기 1.0B", "높이 3.6m 이하", "㎡", 48023, "시공", "국토부 2026하 표준시장단가(재료비 제외)"),
    # 교통안전 (시공비만 — 표지·지주 자재 미보유)
    "delineator_ins": ("시선유도표지 설치비", "흙속매설용", "개소", 6091, "시공", "국토부 2026하 표준시장단가 LH231.10000(재료비 제외)"),
    # 캐노피 (자재만 — 프레임·시공 미보유)
    "poly_2t":        ("폴리카보네이트 채광판", "단층 2T", "㎡", 16300, "자재", "비드앤비 2026-07 공개판매가"),
    "poly_3t":        ("폴리카보네이트 채광판", "단층 3T", "㎡", 24400, "자재", "비드앤비 2026-07 공개판매가(환산)"),
    # 방수 (시공비만 — 방수재 자재·바탕처리 미보유)
    "wp_membrane":    ("도막방수 도막바름(1회)", "바닥", "㎡", 3985, "시공", "국토부 2026하 표준시장단가(재료비 제외)"),
    "wp_sheet":       ("시트방수(1겹)", "바닥 자착식", "㎡", 6629, "시공", "국토부 2026하 표준시장단가(재료비 제외)"),
}


def _span(L):
    """경간 수 — 판 하나가 4.33m 이므로 연장 L 을 덮는 데 필요한 판 수."""
    return max(1, math.ceil(L / 4.33))


def _posts(L, s):
    """지주 수 — 경간마다 하나 + 끝 하나 = ceil(L/s)+1.

    ⚠ floor 였다. 필요 경간 수는 바로 위 _span() 처럼 ceil(L/s) 인데(마지막 자투리
      구간도 지주가 있어야 한다), 여기만 floor 를 써서 **L 이 s 의 배수가 아닐 때마다
      지주가 1개씩 부족했다**(실측: 60개 조합 중 34개). 그 값이 그대로 engine_low/high
      (2차 입찰 하한·절감 기준선)에 들어간다.
    """
    return max(2, math.ceil(L / s) + 1)


# ── 수선 레시피 10종 ──────────────────────────────────────────────
#   각 레시피: major(공종), name, inputs(입력변수 정의), lines(단가키·수량식),
#              complete(카탈로그 완비 여부), notes(별도 계상 안내)
#   line = (sku_key 또는 inputs→sku_key 함수, inputs→수량 함수)
RECIPES = {
    # 1. 가드레일 구간 교체 — 완비
    "guardrail_section": {
        "major": "가드레일·방호울타리",
        "name": "가드레일 구간 교체",
        "inputs": [
            {"key": "L", "label": "파손 연장(m)", "type": "num", "min": 1, "max": 100, "required": True},
            {"key": "s", "label": "지주 간격(m)", "type": "choice", "choices": [2, 4], "default": 4, "required": True},
        ],
        "lines": [
            ("gr_panel", lambda v: _span(v["L"])),
            ("gr_post",  lambda v: _posts(v["L"], v["s"])),
            ("gr_cap",   lambda v: _posts(v["L"], v["s"])),
            ("gr_bolt_c", lambda v: _span(v["L"])),
            ("gr_bolt_y", lambda v: _span(v["L"]) * 8),
            (lambda v: "gr_panel_ins2" if v["s"] == 2 else "gr_panel_ins4", lambda v: v["L"]),
            (lambda v: "gr_post_ins2" if v["s"] == 2 else "gr_post_ins4", lambda v: v["L"]),
        ],
        "complete": True,
        "notes": ["포장면 앵커지주·앵커볼트는 별도", "기존 방호책 철거·폐기는 별도"],
    },
    # 2. 강화유리 1매 교체 — 완비
    "glass_tempered": {
        "major": "유리·샷시·자동문",
        "name": "강화유리 1매 교체",
        "inputs": [
            {"key": "W", "label": "유리 폭(m)", "type": "num", "min": 0.3, "max": 3.0, "required": True},
            {"key": "H", "label": "유리 높이(m)", "type": "num", "min": 0.3, "max": 3.0, "required": True},
        ],
        "lines": [
            ("glass_temp12", lambda v: round(v["W"] * v["H"], 2)),
            ("glass_ins",    lambda v: round(v["W"] * v["H"], 2)),
        ],
        "complete": True,
        "notes": ["12mm 초과·강화복층·특수유리는 별도", "기존 유리 철거·처리는 별도"],
    },
    # 3. 복층유리 창호 교체 — 완비
    "window_pair": {
        "major": "유리·샷시·자동문",
        "name": "복층유리 창호 교체",
        "inputs": [
            {"key": "n", "label": "창호 개소", "type": "num", "min": 1, "max": 10, "required": True},
            {"key": "A", "label": "개소당 면적(㎡)", "type": "num", "min": 1.0, "max": 6.0, "default": 3.0, "required": True},
        ],
        "lines": [
            ("glass_pair24", lambda v: round(v["n"] * v["A"], 2)),
            ("sash_ins",     lambda v: v["n"]),
        ],
        "complete": True,
        "notes": ["창틀(샷시) 자재 교체 시 창호 자재비 별도",
                  "개소당 면적 3.0㎡ 미만은 알루미늄창호 설치비(sash_ins) 단가의 검증범위"
                  "(seed_boq.py \"창호면적 3.0~6.0㎡\") 밖이라 실측으로 확인한다"],
        #  ⚠⚠ [라운드201] sash_ins 단가(116,351원/개소)는 국토부 표준시장단가 원본에
        #    "창호면적 3.0~6.0㎡" 전용이라고 명시돼 있는데, 이 레시피의 입력 범위(A:
        #    1.0~6.0)는 그보다 넓다. complete=True 라 _gate() 는 REMOTE_MAX 만
        #    보고 통과시켜, 흔한 소형창(예: 1.2㎡ 욕실창)도 검증 안 된 단가로 그대로
        #    "원격확정가능"이 됐다 — 그 값이 그대로 2차 입찰 하한선이 된다. min 을
        #    3.0 으로 올려 입력 자체를 막으면 두 소비처(app.py api_field_agreement_open
        #    ·api_repair_estimate) 가 EstimateError 를 "근거 없이 진행"/400 으로 처리해
        #    구간 견적 자체를 못 받는 더 나쁜 결과가 된다 — 그래서 입력은 그대로 받고
        #    게이트만 실측필요로 내린다.
        "needs_calibration_if": lambda v: v["A"] < 3.0,
    },
    # 4. 주차차단기 바 교체 — 미완비(설치 노무 품셈 미확정)
    "barrier_bar": {
        "major": "셔터·차단기·게이트",
        "name": "주차차단기 바 교체",
        "inputs": [
            {"key": "n", "label": "교체 개수", "type": "num", "min": 1, "max": 10, "required": True},
            {"key": "led", "label": "LED 바 여부", "type": "choice", "choices": ["일반", "LED"], "default": "일반", "required": True},
        ],
        "lines": [
            (lambda v: "bar_led" if v["led"] == "LED" else "bar_plain", lambda v: v["n"]),
            # 설치 노무 — 표준품셈 미확보라 특별인부 0.3인/개로 '가정'(needs_calibration)
            ("worker_special", lambda v: round(v["n"] * 0.3, 2)),
        ],
        "complete": False,
        "notes": ["설치 노무는 표준품셈 미확보 → 특별인부 0.3인/개 '가정'", "차단기 본체 교체는 별도"],
    },
    # 5. LED 보안등기구 교체 — 미완비(자재 SKU 불일치, needs_calibration)
    "led_security_light": {
        "major": "간판·전기·가로등",
        "name": "LED 보안등기구 교체",
        "inputs": [
            {"key": "n", "label": "교체 개수", "type": "num", "min": 1, "max": 10, "required": True},
            {"key": "mount", "label": "부착 방식", "type": "choice", "choices": ["등주", "한전주"], "default": "등주", "required": True},
        ],
        "lines": [
            #  ⚠⚠ [라운드69] led_fixture150 은 seed_boq_led.py 61행 "LED 가로등기구
            #    자재"·"150W 일체형·일반형"이다 — 이 레시피가 요구하는 건 설치비
            #    SKU(led_sec_ins_*)가 이미 "50W 이하"로 정확히 명시한 **보안등**인데,
            #    자재만 엉뚱한 카테고리(가로등·150W)를 쓰고 있다. 실제로 맞는
            #    자재+설치 일체 SKU는 같은 파일 77행 "보안등 신설·교체(일체)"
            #    (₩1,000,000)로 이미 존재하지만 이 카탈로그(SKU dict)에는 아직
            #    안 옮겨져 있다. 지어낸 값을 쓰지 않는다는 이 모듈 자신의 원칙
            #    (docstring 18~21행)대로, 옆 레시피 barrier_bar 와 같은 처방—
            #    complete=False 로 내려 자동확정에서 빼고 실측으로 보낸다.
            ("led_fixture150", lambda v: v["n"]),
            (lambda v: "led_sec_ins_k" if v["mount"] == "한전주" else "led_sec_ins_p", lambda v: v["n"]),
        ],
        "complete": False,
        "notes": ["자재 SKU(led_fixture150)가 150W 가로등용이라 보안등(50W 이하) 자재비로 "
                  "쓰기엔 카테고리가 안 맞음 — 실측으로 자재비 보완 필요",
                  "100W 초과·투광등은 별도", "등주 신설·기초는 별도"],
    },
    # 6. 담장 벽돌 부분 재축조 — 미완비(벽돌·모르타르 자재 미보유)
    "brick_wall": {
        "major": "외벽·석재·담장·조적",
        "name": "담장 벽돌 부분 재축조",
        "inputs": [
            {"key": "A", "label": "면적(㎡)", "type": "num", "min": 1, "max": 20, "required": True},
            {"key": "thick", "label": "벽 두께", "type": "choice", "choices": ["0.5B", "1.0B"], "default": "0.5B", "required": True},
        ],
        "lines": [
            (lambda v: "brick_10b" if v["thick"] == "1.0B" else "brick_05b", lambda v: v["A"]),
        ],
        "complete": False,
        "notes": ["벽돌·모르타르 자재비 별도(카탈로그 미보유)", "기존 담장 철거·폐기 별도"],
    },
    # 7. 누수 배관 보수 — 완비
    "pipe_leak": {
        "major": "누수·배관·설비",
        "name": "누수 배관 보수",
        "inputs": [
            {"key": "m", "label": "보수 길이(m)", "type": "num", "min": 1, "max": 50, "required": True},
            {"key": "kind", "label": "관 종류", "type": "choice", "choices": ["PB", "SUS"], "default": "PB", "required": True},
        ],
        "lines": [
            (lambda v: "pipe_sus" if v["kind"] == "SUS" else "pipe_pb", lambda v: v["m"]),
            (lambda v: "pipe_sus_ins" if v["kind"] == "SUS" else "pipe_pb_ins", lambda v: v["m"]),
        ],
        "complete": True,
        "notes": ["관경 15~20A 기준", "벽체·바닥 해체·복구는 별도"],
    },
    # 8. 시선유도표지 교체 — 미완비(표지·지주 자재 미보유)
    "delineator": {
        "major": "교통안전시설",
        "name": "시선유도표지 교체",
        "inputs": [
            {"key": "n", "label": "교체 개소", "type": "num", "min": 1, "max": 20, "required": True},
        ],
        "lines": [
            ("delineator_ins", lambda v: v["n"]),
        ],
        "complete": False,
        "notes": ["표지·지주 자재비 별도(카탈로그 미보유)"],
    },
    # 9. 캐노피 채광판 교체 — 미완비(프레임·시공 미보유)
    "canopy_panel": {
        "major": "지붕·판넬·캐노피",
        "name": "캐노피 채광판 교체",
        "inputs": [
            {"key": "A", "label": "면적(㎡)", "type": "num", "min": 1, "max": 30, "required": True},
            {"key": "thick", "label": "판 두께", "type": "choice", "choices": ["2T", "3T"], "default": "2T", "required": True},
        ],
        "lines": [
            (lambda v: "poly_3t" if v["thick"] == "3T" else "poly_2t", lambda v: v["A"]),
        ],
        "complete": False,
        "notes": ["프레임·부자재·설치 시공비 별도(카탈로그 미보유)"],
    },
    # 10. 바닥 방수 국소 보수 — 미완비(방수재 자재·바탕처리 미보유)
    "floor_waterproof": {
        "major": "도장·방수·미장",
        "name": "바닥 방수 국소 보수",
        "inputs": [
            {"key": "A", "label": "면적(㎡)", "type": "num", "min": 1, "max": 50, "required": True},
            {"key": "method", "label": "공법", "type": "choice", "choices": ["도막", "시트"], "default": "도막", "required": True},
        ],
        "lines": [
            (lambda v: "wp_sheet" if v["method"] == "시트" else "wp_membrane", lambda v: v["A"]),
        ],
        "complete": False,
        "notes": ["방수재 자재비·바탕처리·프라이머 별도(카탈로그 미보유)"],
    },
}


class EstimateError(ValueError):
    """입력이 레시피 정의에 맞지 않을 때."""


def _validate(recipe, inputs):
    """입력을 레시피 정의에 맞춰 검사하고 기본값을 채운다.

    ⚠⚠ [라운드613] inputs 가 dict 가 아니면(정수·실수·bool 등 — JSON 본문의
      "inputs" 값을 클라이언트가 dict 아닌 값으로 보내는 경우) 바로 아래
      `k in inputs` 가 `TypeError: argument of type 'int' is not iterable`
      로 죽었다 — EstimateError(ValueError) 가 아니라 이 모듈이 안 잡는
      예외라 두 호출부 중 가드가 없는 api_repair_estimate(app.py)에서 그대로
      새어 전역 핸들러가 SERVER_ERROR(500)로 돌렸다(클라이언트 입력 오류인데
      회원가입·사건등록 등 이 코드베이스 전역이 지키는 400 관례를 못 따름).
      다른 호출부(api_field_agreement_open)는 자기 쪽에서
      `isinstance(..., dict)` 로 이미 막고 있었지만, 그건 그 호출부 하나만
      지킬 뿐 이 함수(estimate() 를 부르는 진짜 합류점)를 직접 부르는 다른
      경로는 여전히 무방비였다 — 호출부마다 개별로 막는 대신 여기 한 곳에서
      막는다."""
    if not isinstance(inputs, dict):
        raise EstimateError("입력값(inputs)은 객체(JSON object) 형식이어야 합니다")
    clean = {}
    for spec in recipe["inputs"]:
        k = spec["key"]
        if k in inputs and inputs[k] is not None:
            val = inputs[k]
        elif "default" in spec:
            val = spec["default"]
        elif spec.get("required"):
            raise EstimateError(f"'{spec['label']}' 값이 필요합니다")
        else:
            continue
        if spec["type"] == "num":
            try:
                val = float(val)
            except (TypeError, ValueError):
                raise EstimateError(f"'{spec['label']}' 는 숫자여야 합니다")
            #  ⚠ float("nan")/float("inf") 는 예외 없이 통과한다 — NaN 은 min/max 비교가
            #    항상 거짓이라(IEEE 754) 바로 아래 두 검사도 그냥 통과해 버린다.
            #    그대로 두면 나중에 round(price*qty) 에서 ValueError 로 500 이 난다.
            if not math.isfinite(val):
                raise EstimateError(f"'{spec['label']}' 값이 올바르지 않습니다")
            if "min" in spec and val < spec["min"]:
                raise EstimateError(f"'{spec['label']}' 는 {spec['min']} 이상이어야 합니다")
            if "max" in spec and val > spec["max"]:
                raise EstimateError(f"'{spec['label']}' 는 {spec['max']} 이하여야 합니다")
            if float(val).is_integer():
                val = int(val)
        elif spec["type"] == "choice":
            #  ⚠ 화면은 값을 **항상 문자열**로 보낸다(admin.js agCalc: el.value.trim()).
            #    choices 가 숫자인 항목(guardrail_section.s = [2,4])은 "4" not in [2,4]
            #    가 참이라 **허용값을 둘 다 400 으로 거부했다** — 실측: 지주간격을 뭘
            #    적어도 막히고, 빈칸으로 둬야만 통과해 기본값(4m)이 조용히 박혔다
            #    (실제 2m 현장에서 26.5% 과소산출 — 그 값이 2차 경매 입찰 하한이 된다).
            for _c in spec["choices"]:
                if val == _c or str(val) == str(_c):
                    val = _c
                    break
            else:
                raise EstimateError(f"'{spec['label']}' 는 {spec['choices']} 중 하나여야 합니다")
        clean[k] = val
    return clean


def _gate(recipe, high, v=None):
    """원격확정 가능 여부. 하나라도 걸리면 실측으로 보낸다.

    ⚠ [라운드314] 예전엔 low 도 받았다 — high/low 비율로 판정하던 SPREAD_MAX
      게이트(아래 주석)를 지우면서 그 게이트만 없앴을 뿐 이 매개변수 정리는
      안 됐다. 실제로 함수 본문 어디서도 안 쓰여 죽은 인자로 남아 있었다 —
      나중에 구간폭 게이팅을 다시 살리려는 사람이 "이미 low 가 들어오고
      있으니 그냥 쓰면 된다"고 착각하지 않도록 시그니처에서 제거한다
      (range_low 계산 자체는 estimate() 쪽에 그대로 남아 있다).
    """
    if not recipe["complete"]:
        return "실측필요", "카탈로그 미완성(일부 자재·시공 단가 없음) — 실측으로 보완"
    _extra = recipe.get("needs_calibration_if")
    if _extra and v is not None and _extra(v):
        return "실측필요", "입력값이 적용 단가의 검증범위를 벗어남(카탈로그 미검증 구간) — 실측으로 보완"
    if high > REMOTE_MAX:
        return "실측필요", f"예상 상한 {high:,}원 > 원격 한도 {REMOTE_MAX:,}원 (실측이 수수료로 감당됨)"
    #  ⚠ 예전엔 여기 high/low > SPREAD_MAX(1.6) 불확실성 게이트가 있었다 — 그런데
    #    high·low 는 늘 같은 direct*k*VAT 에 MARKUP_HI/MARKUP_LO 를 곱한 값이라
    #    비율이 항상 정확히 1.5/1.25=1.2 로 고정된다. 1.2 > 1.6 은 절대 참이 될 수
    #    없는 죽은 코드였다(라인별 불확실성을 반영해 MARKUP 자체가 흔들리게 만들지
    #    않는 한 살릴 수 없다) — 그래서 지웠다.
    return "원격확정가능", "단일공종·필수변수 충족·한도 이내"


def estimate(pattern_id, inputs, price_book=None):
    """수선 레시피 한 건을 개산한다.

    반환은 **구간(낮음~높음) + 근거 라인**이다. 단일 확정가·보험금을 만들지 않는다.

    price_book — 표준단가표(DB)에서 읽어 온 단가 주입: {sku_key: {"price": int, "src": str}}.
      ⚠ 이 모듈은 끝까지 **순수 함수**로 남는다(db 미import). DB 를 읽는 것은 호출자다.
        예전에는 어드민에서 표준단가를 고쳐도 엔진이 이 파일의 상수만 봐서 값이 안 바뀌었다
        ('고쳤는데 왜 그대로냐'의 원인). 이제 주입된 단가가 있으면 그것을 **우선** 쓴다.
      · 근거(src) 없거나 단가 0 이하인 항목은 **무시하고 내장값으로 폴백**한다
        — 근거 없는 단가는 활성 금지가 이 사업의 철칙이다.
      · 어느 단가를 썼는지는 라인마다 price_from 으로 남는다(스냅샷 재현용).
    """
    if pattern_id not in RECIPES:
        raise EstimateError(f"알 수 없는 수선패턴: {pattern_id}")
    recipe = RECIPES[pattern_id]
    v = _validate(recipe, inputs)
    book = price_book or {}

    lines, direct, db_used = [], 0, 0
    for sku_sel, qty_fn in recipe["lines"]:
        key = sku_sel(v) if callable(sku_sel) else sku_sel
        name, spec, unit, price, ctype, src = SKU[key]
        price_from = "내장 기본값"
        ov = book.get(key)
        if ov:
            try:
                p2 = int(ov.get("price") or 0)
                s2 = (ov.get("src") or "").strip()
            except (TypeError, ValueError, AttributeError):
                p2, s2 = 0, ""
            if p2 > 0 and s2:
                price, src = p2, s2
                price_from = "표준단가표(DB)"
                db_used += 1
        qty = qty_fn(v)
        amount = round(price * qty)
        direct += amount
        lines.append({
            "sku": key, "name": name, "spec": spec, "unit": unit,
            "unit_price": price, "qty": qty, "amount": amount,
            "cost_type": ctype, "src": src, "price_from": price_from,
        })

    k = KFACTOR.get(recipe["major"], KFACTOR_DEFAULT)
    low = round(direct * k * MARKUP_LO * VAT)
    high = round(direct * k * MARKUP_HI * VAT)
    gate, reason = _gate(recipe, high, v)

    return {
        "pattern": pattern_id,
        "major": recipe["major"],
        "name": recipe["name"],
        "inputs": v,
        "lines": lines,
        "direct_cost": direct,          # 직접공사비 합(할증 전)
        "k": k,
        "markup": [MARKUP_LO, MARKUP_HI],
        "markup_src": MARKUP_SRC,
        "range_low": low,               # 제안 상한 구간 — 낮음
        "range_high": high,             # 제안 상한 구간 — 높음
        "gate": gate,                   # 원격확정가능 | 실측필요
        "reason": reason,
        "complete": recipe["complete"],
        "notes": recipe["notes"],
        "engine_ver": ENGINE_VER,       # 이 값이 어느 단가·할증 기준인지
        "db_prices_used": db_used,      # 몇 줄이 표준단가표(DB) 단가로 계산됐는가
        "line_count": len(lines),
        "disclaimer": ("본 값은 표준단가 기반 '시공 개산가(제안 상한)'이며 "
                       "보험금·손해액을 산정·확정하지 않습니다. 최종 확정은 보험사가 합니다."),
    }


def list_patterns():
    """카탈로그 요약 — 패턴 목록과 완비 여부."""
    out = []
    for pid, r in RECIPES.items():
        out.append({
            "pattern": pid, "major": r["major"], "name": r["name"],
            "complete": r["complete"],
            #  ⚠ key·label만 내려가면 화면은 모든 입력을 텍스트칸으로 그릴 수밖에
            #    없다 — choice 항목(간격·부착방식 등)에 어떤 값이 되는지 안 보이고,
            #    숫자칸엔 범위(min/max)도 안 붙는다. 검증이 요구하는 제약을 그대로 보낸다.
            "inputs": [{k: s[k] for k in
                        ("key", "label", "type", "choices", "default", "min", "max")
                        if k in s} for s in r["inputs"]],
        })
    return out


# ── 데모 ──────────────────────────────────────────────────────────
_DEMO = [
    ("guardrail_section", {"L": 8, "s": 4}),
    ("guardrail_section", {"L": 20, "s": 2}),
    ("glass_tempered", {"W": 1.5, "H": 2.0}),
    ("window_pair", {"n": 2, "A": 3.0}),
    ("barrier_bar", {"n": 1, "led": "LED"}),
    ("led_security_light", {"n": 2, "mount": "등주"}),
    ("brick_wall", {"A": 4, "thick": "0.5B"}),
    ("pipe_leak", {"m": 6, "kind": "PB"}),
    ("delineator", {"n": 5}),
    ("canopy_panel", {"A": 6, "thick": "2T"}),
    ("floor_waterproof", {"A": 10, "method": "도막"}),
]


def _demo():
    print("=" * 78)
    print("  수선패턴 자동견적 엔진 — 데모 (값은 전부 seed 실측단가 기반)")
    print("=" * 78)
    comp = sum(1 for r in RECIPES.values() if r["complete"])
    print(f"  카탈로그: 총 {len(RECIPES)}개 패턴 · 완비 {comp}개 · 보완필요 {len(RECIPES) - comp}개")
    print(f"  원격 한도 {REMOTE_MAX:,}원 · 할증 {MARKUP_LO}~{MARKUP_HI}배+부가세\n")
    for pid, inp in _DEMO:
        r = estimate(pid, inp)
        mark = "○" if r["gate"] == "원격확정가능" else "△"
        print(f"  {mark} [{r['name']}] {r['inputs']}")
        print(f"      직접공사비 {r['direct_cost']:,}원 → 제안 상한 "
              f"{r['range_low']:,} ~ {r['range_high']:,}원")
        print(f"      판정: {r['gate']} — {r['reason']}")
        if not r["complete"]:
            print(f"      ⚠ {r['notes'][0]}")
        print()
    print("-" * 78)
    print("  주의: 위 값은 '시공 개산가(제안 상한)'이며 보험금이 아니다. 최종 확정은 보험사.")
    return 0


if __name__ == "__main__":
    sys.exit(_demo())
