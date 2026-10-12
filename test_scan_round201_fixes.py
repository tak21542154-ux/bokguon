# -*- coding: utf-8 -*-
"""스캔 201라운드 회귀 — repair_estimate.py의 window_pair 레시피가 sash_ins
단가의 검증범위(3.0~6.0㎡)보다 넓은 입력범위(1.0~6.0)를 허용해, 흔한 소형창
(예: 1.2㎡ 욕실창)도 검증 안 된 단가로 "원격확정가능"이 되던 결함.

  sash_ins(알루미늄창호 설치비, 116,351원/개소)는 seed_boq.py 원본에 "창호면적
  3.0~6.0㎡" 전용이라고 명시돼 있다. _gate() 는 recipe["complete"] 와
  REMOTE_MAX 만 봤지 라인별 단가 검증범위는 전혀 보지 않아, A=1.2 처럼 범위
  밖 입력도 그대로 통과시켰다 — 그 값이 그대로 2차 입찰 하한선이 된다.

  min 을 3.0 으로 올려 입력 자체를 막는 방식은 쓰지 않았다 — 두 소비처
  (app.py api_field_agreement_open·api_repair_estimate) 가 EstimateError 를
  "근거 없이 진행"/400 으로 처리해 구간 견적 자체를 못 받는 더 나쁜 결과가
  되기 때문이다(직접 확인함). 그래서 입력은 그대로 받고, 검증범위 밖일 때만
  게이트를 "실측필요"로 내리는 recipe 훅(needs_calibration_if)을 추가했다.

      python test_scan_round201_fixes.py
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


RE_SRC = read("repair_estimate.py")

print("=" * 72)
print("  스캔 201라운드 회귀 — window_pair 소형창 단가 검증범위 밖 무단통과")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
#  ⚠ [라운드314] 원래는 "def _gate(recipe, high, low, v=None):" 를 그대로 찾았다 —
#    314라운드가 안 쓰이던 low 매개변수를 시그니처에서 제거해(함수 본문 어디서도
#    참조 안 됨) 그 리터럴이 사라졌다. 이 검사 본연의 의도(v 를 받는지)는 그대로
#    살아 있으므로 low 없는 새 시그니처로 문자열만 좁힌다 — 새 수정을 되돌리지 않는다.
chk("def _gate(recipe, high, v=None):" in RE_SRC,
    "★★★ _gate() 가 검증된 입력값(v)을 받도록 확장됐다")
chk('_extra = recipe.get("needs_calibration_if")' in RE_SRC,
    "★★★ _gate() 가 recipe 별 추가 검증훅(needs_calibration_if)을 확인한다")
chk('"needs_calibration_if": lambda v: v["A"] < 3.0,' in RE_SRC,
    "★★★ window_pair 레시피에 sash_ins 검증범위(3.0㎡ 미만) 훅이 걸렸다")
chk("gate, reason = _gate(recipe, high, v)" in RE_SRC,
    "★ estimate() 가 검증된 입력값을 _gate() 로 넘긴다")

# ============================================================
print("\n[2] 실행 — 검증범위 밖 소형창은 실측필요, 안은 원격확정가능")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
try:
    import importlib
    import repair_estimate as RE
    importlib.reload(RE)

    small = RE.estimate("window_pair", {"n": 1, "A": 1.2})
    chk(small["gate"] == "실측필요",
        "★★★★ 1.2㎡(흔한 욕실창) 입력은 실측필요로 내려간다"
        "(고치기 전엔 원격확정가능이었다)", small["gate"])
    chk(small["range_low"] > 0 and small["range_high"] > 0 and len(small["lines"]) == 2,
        "★★★ 실측필요로 내려가도 구간·근거 라인은 그대로 나온다"
        "(EstimateError 로 막지 않아 소비처가 '근거 없이 진행'하지 않는다)",
        {"low": small["range_low"], "high": small["range_high"], "lines": len(small["lines"])})

    boundary_lo = RE.estimate("window_pair", {"n": 1, "A": 2.99})
    chk(boundary_lo["gate"] == "실측필요",
        "★ 경계 바로 아래(2.99㎡)도 실측필요", boundary_lo["gate"])

    boundary_hi = RE.estimate("window_pair", {"n": 1, "A": 3.0})
    chk(boundary_hi["gate"] == "원격확정가능",
        "★★★ 경계값(정확히 3.0㎡, seed_boq 검증범위 하한)은 그대로 원격확정가능"
        "(과잉차단 아님)", boundary_hi["gate"])

    default_ok = RE.estimate("window_pair", {"n": 2})
    chk(default_ok["gate"] == "원격확정가능" and default_ok["inputs"]["A"] == 3.0,
        "★ 기본값(A=3.0, n=2)도 기존과 동일하게 원격확정가능", default_ok)

    # ── 회귀: needs_calibration_if 없는 다른 완비 레시피는 영향받지 않는다 ──
    gr = RE.estimate("guardrail_section", {"L": 8, "s": 4})
    chk(gr["gate"] == "원격확정가능",
        "★ needs_calibration_if 없는 형제 레시피(가드레일)는 그대로 동작", gr["gate"])
    pipe = RE.estimate("pipe_leak", {"m": 6, "kind": "PB"})
    chk(pipe["gate"] == "원격확정가능",
        "★ needs_calibration_if 없는 형제 레시피(배관누수)도 그대로 동작", pipe["gate"])
    comp = sum(1 for r in RE.RECIPES.values() if r["complete"])
    chk(comp == 4, "★ complete=True 레시피 개수는 그대로 4개(이번 수정은 complete 를 안 건드림)", comp)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드201 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
