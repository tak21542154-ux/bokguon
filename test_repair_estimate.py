# -*- coding: utf-8 -*-
"""수선패턴 자동견적 엔진 검증.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

이 엔진의 가장 위험한 실패는 **단일 확정가를 만들어 손해사정처럼 보이는 것**과
**근거 없는 값을 원격확정으로 내보내는 것**이다. 그 두 가지를 최우선으로 검사한다.
"""
import io
import sys
import math

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import repair_estimate as RE

OK = FAIL = 0


def chk(cond, label, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}   {detail}")


def main():
    print("=" * 70)
    print("  수선패턴 자동견적 엔진 검증")
    print("=" * 70)

    # ── 1. 손해사정 가드레일 (가장 중요) ─────────────────────────
    print("\n[1] 손해사정 경계 — 확정가·보험금을 만들지 않는가")
    r = RE.estimate("guardrail_section", {"L": 8, "s": 4})
    # 결과에 단일 확정가·보험금·손해액 필드가 없어야 한다
    banned = [k for k in r if any(b in k for b in ("확정", "보험금", "손해액", "est_price", "award"))]
    chk(not banned, "★ 결과에 확정가·보험금·손해액 필드가 없음", banned)
    chk("range_low" in r and "range_high" in r, "구간(낮음~높음)으로 낸다")
    chk(r["range_low"] <= r["range_high"], "낮음 ≤ 높음")
    chk("disclaimer" in r and "보험금" in r["disclaimer"] and "보험사가" in r["disclaimer"],
        "★ 보험금 아님·보험사 확정 문구를 함께 낸다")
    # 엔진이 db 를 import 하지 않아야(순수 함수 — est_price 를 건드릴 수 없다)
    src = io.open("repair_estimate.py", encoding="utf-8").read()
    chk("import db" not in src, "★ 엔진이 db 를 import 하지 않음(est_price 자동확정 불가)")

    # ── 2. 모든 패턴이 오류 없이 산출되는가 ───────────────────────
    print("\n[2] 10개 패턴 산출")
    demos = {
        "guardrail_section": {"L": 8, "s": 4},
        "glass_tempered": {"W": 1.5, "H": 2.0},
        "window_pair": {"n": 2, "A": 3.0},
        "barrier_bar": {"n": 1, "led": "LED"},
        "led_security_light": {"n": 1, "mount": "등주"},
        "brick_wall": {"A": 4, "thick": "0.5B"},
        "pipe_leak": {"m": 6, "kind": "PB"},
        "delineator": {"n": 5},
        "canopy_panel": {"A": 6, "thick": "2T"},
        "floor_waterproof": {"A": 10, "method": "도막"},
    }
    chk(len(RE.RECIPES) == 10, "패턴이 10개", len(RE.RECIPES))
    for pid in RE.RECIPES:
        chk(pid in demos, f"  데모 입력 존재: {pid}")
    for pid, inp in demos.items():
        try:
            e = RE.estimate(pid, inp)
            good = (e["range_low"] > 0 and e["range_high"] >= e["range_low"]
                    and e["lines"] and e["direct_cost"] > 0)
            chk(good, f"  {e['name']} 산출", e.get("range_high"))
        except Exception as ex:
            chk(False, f"  {pid} 산출 중 오류", repr(ex))

    # ── 3. 수량식 검산 (가드레일) ─────────────────────────────────
    print("\n[3] 수량식 손계산 대조 — 가드레일 8m·지주간격 4m")
    r = RE.estimate("guardrail_section", {"L": 8, "s": 4})
    q = {ln["sku"]: ln["qty"] for ln in r["lines"]}
    chk(q["gr_panel"] == math.ceil(8 / 4.33), "판 = 올림(8/4.33) = 2장", q["gr_panel"])
    #  ⚠⚠ [라운드314] 이 자리(L=8,s=4)는 8/4 가 나누어떨어져 올림(ceil)과
    #    내림(floor)의 결과가 우연히 같다(2.0) — round58 이 고친 게 "내림이면
    #    과소산출"이었는데, 정작 이 검산이 옛 잘못된 공식(math.floor)으로
    #    써 있어 "이게 정답 공식이다"처럼 보였다. 실제 정답은 올림(ceil)이므로
    #    라벨·수식 둘 다 정정하고, 배수가 아닌 조합(아래)을 추가해 floor 로
    #    되돌아가도 이 파일 자신이 잡도록 이중화한다(round58 테스트가 이미
    #    RE._posts(9,2) 로 잡고 있지만, 엔진 전담 스펙 파일도 자립 검증해 둔다).
    chk(q["gr_post"] == math.ceil(8 / 4) + 1, "지주 = 올림(8/4)+1 = 3본", q["gr_post"])
    chk(q["gr_bolt_c"] == 2, "취부볼트 = 경간수 = 2개", q["gr_bolt_c"])
    chk(q["gr_bolt_y"] == 16, "연결볼트 = 경간수×8 = 16개", q["gr_bolt_y"])

    # 배수 아닌 L/s 조합 — floor/ceil 이 실제로 갈리는 자리에서 올림공식을 확인
    r3 = RE.estimate("guardrail_section", {"L": 9, "s": 2})
    q3 = {ln["sku"]: ln["qty"] for ln in r3["lines"]}
    chk(q3["gr_post"] == math.ceil(9 / 2) + 1 == 6,
        "★ 지주 = 올림(9/2)+1 = 6본(내림이었다면 5본으로 과소산출 — round58)",
        q3["gr_post"])
    # 지주간격에 따라 설치비 단가가 갈리는가
    r2 = RE.estimate("guardrail_section", {"L": 8, "s": 2})
    p4 = next(l for l in r["lines"] if l["sku"].startswith("gr_panel_ins"))
    p2 = next(l for l in r2["lines"] if l["sku"].startswith("gr_panel_ins"))
    chk(p4["unit_price"] == 2356 and p2["unit_price"] == 3083,
        "★ 지주간격 2m/4m 로 설치비 단가가 갈림", f"{p4['unit_price']}/{p2['unit_price']}")

    # ── 4. 단가가 seed 실측값과 일치하는가 (출처검증) ─────────────
    print("\n[4] 단가 출처 대조 — 값을 지어내지 않았는가")
    chk(RE.SKU["gr_panel"][3] == 110000, "가드레일 판 = 110,000원(건자재114)")
    chk(RE.SKU["glass_temp12"][3] == 39250, "강화유리 12mm = 39,250원(한국물가정보)")
    chk(RE.SKU["led_sec_ins_p"][3] == 50083, "보안등 설치비 = 50,083원(전기 표준품셈)")
    for key, tup in RE.SKU.items():
        chk(bool((tup[5] or "").strip()), f"  근거 있음: {key}", "") if False else None
    no_src = [k for k, t in RE.SKU.items() if not (t[5] or "").strip()]
    chk(not no_src, "★ 모든 단가에 근거가 있음(근거 없는 값 없음)", no_src)

    # ── 5. 게이팅 규칙 ────────────────────────────────────────────
    print("\n[5] 원격확정 vs 실측 게이팅")
    # 완비 + 한도 이내 → 원격확정
    chk(RE.estimate("guardrail_section", {"L": 8, "s": 4})["gate"] == "원격확정가능",
        "완비·소액 → 원격확정가능")
    # 완비 + 한도 초과 → 실측
    big = RE.estimate("guardrail_section", {"L": 20, "s": 2})
    chk(big["gate"] == "실측필요" and big["range_high"] > RE.REMOTE_MAX,
        "★ 100만원 초과 → 실측필요", big["range_high"])
    # 미완비 → 무조건 실측 (근거 없는 값을 원격확정으로 안 내보냄)
    for pid in ("barrier_bar", "brick_wall", "delineator", "canopy_panel", "floor_waterproof"):
        e = RE.estimate(pid, demos[pid])
        chk(e["gate"] == "실측필요", f"★ 미완비 '{RE.RECIPES[pid]['name']}' → 실측필요", e["gate"])
    # 완비 패턴은 4개
    #  ⚠ [라운드69] led_security_light 가 5개→4개로 내려왔다 — 자재 SKU
    #    (led_fixture150, 150W 가로등용)가 이 레시피(50W 이하 보안등)와
    #    카테고리가 안 맞는 걸 확인해 complete=False 로 내렸다(실측으로 보냄).
    comp = sum(1 for r in RE.RECIPES.values() if r["complete"])
    chk(comp == 4, "완비 패턴 4개", comp)

    # ── 6. 입력 검증 ──────────────────────────────────────────────
    print("\n[6] 입력 검증")
    def err(pid, inp):
        try:
            RE.estimate(pid, inp); return False
        except RE.EstimateError:
            return True
    chk(err("guardrail_section", {"s": 4}), "필수값(L) 없으면 거절")
    chk(err("guardrail_section", {"L": 999, "s": 4}), "범위 초과(L>100) 거절")
    chk(err("guardrail_section", {"L": 8, "s": 3}), "잘못된 선택지(s=3) 거절")
    chk(err("glass_tempered", {"W": "abc", "H": 2}), "숫자 아닌 값 거절")
    chk(err("nonexistent", {}), "없는 패턴 거절")
    # 기본값 채움
    e = RE.estimate("window_pair", {"n": 2})
    chk(e["inputs"].get("A") == 3.0, "선택 안 한 값은 기본값으로 채움(A=3.0)")

    # ── 7. 결정성 ─────────────────────────────────────────────────
    print("\n[7] 결정성 — 같은 입력이면 같은 결과")
    a = RE.estimate("pipe_leak", {"m": 6, "kind": "PB"})
    b = RE.estimate("pipe_leak", {"m": 6, "kind": "PB"})
    chk(a == b, "같은 입력 → 같은 출력")

    # ── 8. 라인 근거가 함께 나오는가 ──────────────────────────────
    print("\n[8] 산출 근거 노출")
    r = RE.estimate("glass_tempered", {"W": 1.5, "H": 2.0})
    chk(all("src" in l and l["src"] for l in r["lines"]), "모든 라인에 근거가 붙어 있음")
    chk(all(k in r["lines"][0] for k in ("name", "qty", "unit_price", "amount", "cost_type")),
        "라인에 품명·수량·단가·금액·성격이 있음")
    chk(RE.list_patterns() and len(RE.list_patterns()) == 10, "패턴 목록 API 동작")

    # ── 9. DB 단가 주입 (price_book) ──────────────────────────────
    #  어드민 표준단가표에서 고친 값이 견적에 반영되는 경로.
    #  ⚠ 엔진은 순수함수로 남는다 — 여기서는 주입 규칙만 검증한다.
    print("\n[9] DB 단가 주입")
    base = RE.estimate("glass_tempered", {"W": 1.5, "H": 2.0})
    # (a) 주입 없으면 종전과 동일(하위호환)
    same = RE.estimate("glass_tempered", {"W": 1.5, "H": 2.0}, price_book=None)
    chk(base == same, "price_book 없으면 종전 결과와 동일(하위호환)")
    chk(base["db_prices_used"] == 0, "주입 0건이면 db_prices_used=0")
    # (b) 정상 주입 — 단가가 바뀌면 구간도 바뀐다
    book = {"glass_temp12": {"price": 50000, "src": "검증용 개정단가 2026-08"}}
    over = RE.estimate("glass_tempered", {"W": 1.5, "H": 2.0}, price_book=book)
    line = next(l for l in over["lines"] if l["sku"] == "glass_temp12")
    chk(line["unit_price"] == 50000, "★ 주입 단가가 라인에 적용", f"{line['unit_price']:,}원")
    chk(line["price_from"] == "표준단가표(DB)", "  적용 출처가 라인에 표시", line["price_from"])
    chk(line["src"] == "검증용 개정단가 2026-08", "  근거도 DB 값으로 교체")
    chk(over["range_high"] > base["range_high"], "★ 단가 인상 → 구간 상향",
        f"{base['range_high']:,} → {over['range_high']:,}")
    chk(over["db_prices_used"] == 1, "  적용 건수 집계", over["db_prices_used"])
    # (c) 철칙 — 근거 없는 단가·0원은 무시하고 내장값 폴백
    bad = RE.estimate("glass_tempered", {"W": 1.5, "H": 2.0},
                      price_book={"glass_temp12": {"price": 50000, "src": ""},
                                  "glass_ins": {"price": 0, "src": "근거는 있음"}})
    chk(bad["range_high"] == base["range_high"],
        "★★ 근거 없는 단가·0원 주입은 무시(내장값 폴백) — 철칙", f"{bad['range_high']:,}")
    chk(bad["db_prices_used"] == 0, "  무시된 주입은 집계 안 됨")
    chk(all(l["price_from"] == "내장 기본값" for l in bad["lines"]), "  전 라인 내장값 표시")
    # (d) 엔진에 없는 sku 키는 조용히 무시
    noop = RE.estimate("glass_tempered", {"W": 1.5, "H": 2.0},
                       price_book={"없는키": {"price": 1, "src": "x"}})
    chk(noop["range_high"] == base["range_high"], "모르는 sku 키는 무시")

    print("-" * 70)
    print(f"  통과 {OK} · 실패 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
