# -*- coding: utf-8 -*-
"""스캔 315라운드 회귀 — compliance.py 복합공종 판정이 딕셔너리 등록순서에 기대던 결함,
   이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견(dispatch.py 는 같은 라운드가 전담
   재조사했으나 이미 촘촘히 검증돼 있어 클린).

   app.py 가 사건을 접수할 때 여러 공종을 고르면 category="복합(A · B · ...)" 형태로
   합친다(app.py 3763~3764행). rule_for() 는 그 안의 토큰이 전부 판정표(WORK_RULES)에
   있으면 배제업종(excluded)·타법소관(other_law)·판정불가(unknown)가 하나라도 섞였는지는
   정확히 가렸지만(라운드278), 전부 special(또는 special+general)인 경우엔 복합문자열
   전체에 부분일치를 걸어 **WORK_RULES 딕셔너리에 먼저 등록된 트레이드 하나**만 그대로
   썼다 — 그 파일 자신의 주석(120~122행)이 이미 "여러 공종이 섞이면 종합공사로 본다
   (기준 5천만원)"고 명시하는데, 실제로는 서로 다른 special 트레이드가 몇 개가 섞이든
   전문공사 단일 한도(1,500만원)로 고정 판정되고 있었다 — 딕셔너리 순서라는 우연에
   의존하는 구조라, 표에 항목을 추가·재배열하면 조용히 결과가 바뀔 수 있었다.

   토큰별 재귀판정으로 고쳤다 — 막는 kind 우선순위(기존 로직)는 그대로 유지하고,
   전부 special/general인데 서로 다른 트레이드가 2개 이상이면 종합공사(5천만원)로,
   실질적으로 1개뿐이면 그 트레이드 자신의 규칙 그대로 반환한다.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import compliance as CP  # noqa: E402

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
print("  스캔 315라운드 회귀 — compliance.py 복합공종 딕셔너리순서 의존 결함")
print("=" * 74)

print("\n[1] 실행 — 배제업종 안 섞인 special 트레이드 2개 결합은 종합공사(5천만원) 기준")
r = CP.check_direct_contract("복합(유리·샷시·자동문 · 조경·수목)", 20_000_000)
chk(r["ok"] and r["code"] == CP.OK_DIRECT and r["limit"] == CP.LIMIT_GENERAL,
    "★★★★★ 2,000만원 결합건이 종합공사 기준(5천만원)으로 도급가능"
    "(고치기 전엔 전문공사 1,500만원 고정판정으로 '금액초과'였다)",
    (r["code"], r["limit"]))
chk(r["category"] == "종합 원상복구",
    "★★★★ 감사기록(contract_gate_log)에 남을 category 도 '종합 원상복구'로 정확히 남는다"
    "(고치기 전엔 우연히 먼저 등록된 트레이드 하나의 이름만 남았다)", r["category"])

print("\n[2] 실행 — 전문공사 단일 한도(1,500만원)는 넘지만 종합 한도(5천만원)는 안 넘는 전 구간 확인")
for amt in (13_000_000, 20_000_000, 30_000_000, 39_000_000):
    r = CP.check_direct_contract("복합(외벽·석재·담장·조적 · 도장·방수·미장)", amt)
    chk(r["ok"] and r["code"] == CP.OK_DIRECT,
        f"  {amt:,}원 — 종합 안전선(4천만원) 이내라 도급가능", r["code"])
# 종합 안전선(5천만원의 80% = 4천만원)을 넘으면 여전히 금액초과여야 한다(과잉완화 아님)
r = CP.check_direct_contract("복합(외벽·석재·담장·조적 · 도장·방수·미장)", 45_000_000)
chk(not r["ok"] and r["code"] == CP.NO_AMOUNT,
    "★★★ 종합 안전선(4천만원)을 넘으면 여전히 금액초과(과잉완화로 새지 않는다)", r["code"])

print("\n[3] 실행 — 서로 다른 5개 special 트레이드 전수 10가지 조합, 전부 종합공사 기준")
SPECIALS = ["유리·샷시·자동문", "누수·배관·설비", "외벽·석재·담장·조적",
            "도장·방수·미장", "조경·수목"]
import itertools
all_general = True
for a, b in itertools.combinations(SPECIALS, 2):
    r = CP.check_direct_contract(f"복합({a} · {b})", 25_000_000)
    if r["limit"] != CP.LIMIT_GENERAL:
        all_general = False
        print(f"    ✖ {a} · {b} → limit={r['limit']}")
chk(all_general,
    "★★★★ special 5종 전수 10가지 조합 모두 종합공사(5천만원) 기준으로 판정된다"
    "(딕셔너리 등록순서와 무관 — 고치기 전엔 순서상 먼저 오는 쪽에 따라 결과가 갈렸다)")

print("\n[4] 실행 — 회귀 없음: 막는 kind(배제업종·타법소관·판정불가)는 여전히 우선한다")
r = CP.check_direct_contract("복합(가드레일·방호울타리 · 유리·샷시·자동문)", 5_000_000)
chk(not r["ok"] and r["code"] == CP.NO_TRADE,
    "★★★ 배제업종이 하나라도 섞이면 여전히 배제업종이 이긴다(금액 무관 차단)", r["code"])
r = CP.check_direct_contract("복합(셔터·차단기·게이트 · 조경·수목)", 500_000)
chk(not r["ok"] and r["code"] == CP.NO_LAW,
    "★★ 타법소관이 섞여도 여전히 타법소관이 이긴다", r["code"])
r = CP.check_direct_contract("복합(방음벽·휀스·펜스 · 누수·배관·설비)", 8_000_000)
chk(not r["ok"] and r["code"] == CP.NO_UNKNOWN,
    "★★★ 라운드278 원본 재현 — 판정표에 없는 업종이 섞이면 여전히 판정불가"
    "(고치기 전 라운드278이 막은 '한쪽만 보고 통과' 사고가 재발하지 않았다)", r["code"])

print("\n[5] 실행 — 회귀 없음: 실질적으로 트레이드가 1개뿐이면 그 트레이드 규칙 그대로")
r = CP.check_direct_contract("복합(유리·샷시·자동문)", 10_000_000)
chk(r["category"] == "유리·샷시·자동문" and r["limit"] == CP.LIMIT_SPECIAL,
    "★★ 단일 트레이드만 담긴 복합문자열은 종합공사로 승격되지 않는다"
    "(서로 다른 트레이드가 2개 이상일 때만 종합 적용)", (r["category"], r["limit"]))

print("\n[6] 실행 — 회귀 없음: 복합(...) 아닌 기존 형식(round278 원본 테스트 형식)은 그대로")
r = CP.check_direct_contract("유리·샷시·자동문·교통안전시설", 5_000_000)
chk(not r["ok"] and r["code"] == CP.NO_TRADE,
    "★★ '복합(' 접두어 없는 기존 결합형식도 배제업종이 여전히 이긴다(경로 미변경)", r["code"])

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
