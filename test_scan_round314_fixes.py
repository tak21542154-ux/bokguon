# -*- coding: utf-8 -*-
"""스캔 314라운드 회귀 — repair_estimate.py 전담 재조사(58라운드 이후 방치),
   이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견. 핵심 계산 로직(_span/_posts/
   _validate/estimate/_gate) 자체는 58·69·201라운드가 이미 다져 놔서 새 런타임
   결함은 없었다(클린) — 대신 "코드는 맞는데 주변 장치가 흐트러진" 3건.

   ① _gate() 가 안 쓰는 low 매개변수를 계속 받고 있었다(SPREAD_MAX 게이트를
      지우며 함수 본문 정리는 됐지만 시그니처 정리가 빠짐) — 제거.
   ② test_repair_estimate.py 의 지주수(_posts) 손계산 대조가 전부 L 이 s 의
      배수인 조합(8/4, 8/2, 20/2)이라 floor/ceil 이 우연히 같은 값을 내 round58
      회귀를 이 파일 자신은 못 잡았다(round58 자신의 테스트는 비배수 조합으로
      실제로 잡고 있어 안전망 자체는 있었다). 게다가 기존 검산 라벨·수식이
      "내림(floor)"으로 적혀 있어 틀린 공식을 정답인 것처럼 보여줬다 —
      올림(ceil)으로 정정 + 비배수 조합(9,2) 회귀 이중화 추가.
   ③ repair_estimate_설계.md 가 세 군데 드리프트됐다 — 검증 건수(53→65),
      LED 보안등기구 교체 상태(69라운드가 이미 complete=False 로 내렸는데 문서는
      아직 완비로 표기), 게이팅 규칙 3번째 조건(실제론 이미 삭제된 "구간폭
      ≤1.6배"를 계속 서술하고, 실제로 동작 중인 needs_calibration_if 는 언급이
      아예 없었음). 코드가 아니라 문서만 갱신.
"""
import importlib
import inspect
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PASS = FAIL = 0
FAILED = []


def chk(cond, msg, detail=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {msg}")
    else:
        FAIL += 1
        FAILED.append(msg)
        print(f"  [FAIL] {msg}" + (f"   {detail}" if detail else ""))


print("=" * 74)
print("  스캔 314라운드 회귀 — repair_estimate.py 죽은 인자·엔진문서 드리프트")
print("=" * 74)

import repair_estimate as RE  # noqa: E402
importlib.reload(RE)

print("\n[1] 실행 — _gate() 가 더는 안 쓰는 low 인자를 안 받는다(실제 시그니처 확인)")
params = list(inspect.signature(RE._gate).parameters)
chk(params == ["recipe", "high", "v"],
    "★★★ _gate(recipe, high, v=None) — low 매개변수 제거됨", params)

print("\n[2] 실행 — estimate() 는 여전히 정상 동작한다(시그니처 변경 회귀 없음)")
try:
    r = RE.estimate("guardrail_section", {"L": 8, "s": 4})
    chk(r["gate"] in ("원격확정가능", "실측필요") and r["range_high"] > 0,
        "★★ estimate() 가 예외 없이 정상 결과를 낸다", r.get("gate"))
except Exception as ex:
    chk(False, "★★ estimate() 가 예외 없이 정상 결과를 낸다", repr(ex))

print("\n[3] 실행 — RECIPES 의 실제 complete 개수가 문서가 말하는 '완비 4 / 보완필요 6' 과 일치")
n_complete = sum(1 for r in RE.RECIPES.values() if r.get("complete"))
n_incomplete = len(RE.RECIPES) - n_complete
chk((n_complete, n_incomplete) == (4, 6),
    "★★★★ RECIPES 완비/보완필요 개수 = (4, 6)"
    "(달라졌으면 repair_estimate_설계.md 표도 함께 갱신해야 한다)",
    (n_complete, n_incomplete))

print("\n[4] 실행 — LED 보안등기구 교체는 여전히 미완비(라운드69 판정 유지)")
chk(RE.RECIPES["led_security_light"]["complete"] is False,
    "★★★ led_security_light 는 complete=False (SKU 카테고리 불일치, 69라운드)")

print("\n[5] 소스 확인 — 설계문서가 더는 죽은 '구간 폭 ≤ 1.6배' 게이트를 현재형으로 서술 안 함")
DOC = io.open(os.path.join(HERE, "repair_estimate_설계.md"), encoding="utf-8").read()
chk("구간 폭 ≤ 1.6배" not in DOC.split("## 게이팅 규칙")[1].split("## 아직")[0]
    if "## 게이팅 규칙" in DOC and "## 아직" in DOC else False,
    "★★★ 게이팅 규칙 절에 더는 죽은 '구간 폭 ≤ 1.6배' 조건이 현재형으로 없다")
chk("needs_calibration_if" in DOC,
    "★★★ 설계문서가 실제로 동작 중인 needs_calibration_if 훅을 언급한다")
chk("완비 5 / 보완필요 5" not in DOC,
    "★★ 문서에 옛 카운트(완비 5/보완필요 5)가 더는 안 남아있다")

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
