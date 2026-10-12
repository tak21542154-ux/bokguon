# -*- coding: utf-8 -*-
"""스캔 651라운드 회귀 — compliance.check_direct_contract()가 amount/related_amount에
float('inf')/float('-inf')/float('nan')를 받으면 int(amount or 0)에서 OverflowError
(inf) 또는 ValueError(nan, "cannot convert float NaN to integer")를 그대로 던지던 결함.

배경: 형제 함수(app.py _setting_int 라운드485, _ai_threshold 라운드631)는 이미
"int(float(x))/int(x)가 inf·nan에서 ValueError가 아니라 OverflowError/ValueError를
낸다"는 함정을 알고 있고, 두 함수 모두 그 예외까지 잡아 "설정이 깨져도 예외를 위로
던지지 않는다"는 자기 계약을 지킨다. compliance.py의 이 함수는 그 계약 문구는 없지만,
파일 최상단 docstring이 이미 "판정은 보수적으로 한다 · 애매하면 '도급 불가'로 낸다"고
명시하고, db·app을 모르는 **공용 순수함수**로 설계돼 호출부의 사전 검증에 기대지
않는 것이 원칙이다. 실제 호출부(app.py record_gate 5곳)는 전부 parse_money()가 이미
정제한 정수만 넘기므로(parse_money는 str(value)를 거쳐 int(str)로 파싱해 "inf"/"nan"
문자열 자체가 ValueError로 걸러진다 — 실측 확인, round651 조사 과정에서 이 함수의
실제 호출 경로 전체(bids.amount·cases.est_price/award_amount/low_price·
field_agreements.field_amount 전부 parse_money() 종착) 대조로 확인) 오늘 당장 이
경로로 도달하지는 않지만, 이 함수 자신의 방어가 없다는 사실은 그대로 남아 있었다.

직접조사(하위위임 없음) — repair_estimate.py/addr_search.py/photo_ai.py는 동적
퍼징(경계값 min/max/이상/이하 전수, choice 전수, None/int/list/nan/inf 등)으로 이미
탄탄함을 실측 확인했고, compliance.check_direct_contract()만 이 자리에서 실제로
크래시함을 직접 재현했다.

고침(compliance.py 226~256행 부근): amt/rel 변환을 try/except로 감싸 (TypeError,
ValueError, OverflowError)를 잡고, 이미 이 함수 안에 있는 kind=="unknown" 분기와
같은 모양(NO_UNKNOWN, ok=False)으로 되돌린다 — amount를 못 읽었다고 0원 취급해서
통과시키면(안전한 쪽과 반대 방향) 이 파일 자신의 "애매하면 도급 불가" 원칙에 정면
위배되므로, 실패를 "0원"이 아니라 "판정불가(막힘)"로 낸다.
"""
import io
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("BOKGUON_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="r651_"), "scratch.db"))
os.environ.setdefault("BOKGUON_ENV", "dev")

import compliance as CP

PASS = FAIL = 0


def chk(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  OK  {msg}")
    else:
        FAIL += 1
        print(f"  ✖✖✖ FAIL  {msg}")


print("=" * 70)
print("[1] 되돌림-증명 — 옛(가드 없는) 코드가 실제로 크래시하는지 먼저 확인")
print("=" * 70)
#  ★ 표준지침: 반드시 인메모리로만 되돌린다 — 실제 파일은 절대 건드리지 않는다.
import types

_old_src = """
def check_direct_contract_OLD(category, amount, related_amount=0):
    name, rule = CP.rule_for(category)
    kind, law = rule["kind"], rule["law"]
    amt = int(amount or 0)
    rel = int(related_amount or 0)
    return {"amt": amt, "rel": rel}
"""
_ns = {"CP": CP}
exec(compile(_old_src, "<round651_old_reverted>", "exec"), _ns)
_old_fn = _ns["check_direct_contract_OLD"]

try:
    _old_fn("종합 원상복구", float("inf"))
    chk(False, "옛 코드가 inf에서 크래시해야 하는데 안 함 (재현 실패)")
except OverflowError:
    chk(True, "되돌림-증명: 옛(가드 없는) 코드는 amount=inf에서 실제로 OverflowError를 던짐")
except Exception as e:
    chk(False, f"옛 코드가 예상과 다른 예외({type(e).__name__})를 던짐")

try:
    _old_fn("종합 원상복구", float("nan"))
    chk(False, "옛 코드가 nan에서 크래시해야 하는데 안 함 (재현 실패)")
except ValueError:
    chk(True, "되돌림-증명: 옛(가드 없는) 코드는 amount=nan에서 실제로 ValueError를 던짐")
except Exception as e:
    chk(False, f"옛 코드가 예상과 다른 예외({type(e).__name__})를 던짐")

print()
print("=" * 70)
print("[2] 실제 수정본 — 크래시하지 않고 '판정불가(막힘)'으로 안전하게 떨어지는지")
print("=" * 70)

for label, amt in (("amount=inf", float("inf")), ("amount=-inf", float("-inf")),
                   ("amount=nan", float("nan"))):
    try:
        res = CP.check_direct_contract("종합 원상복구", amt)
        chk(res["ok"] is False, f"{label}: 크래시 없이 dict 반환, ok=False (안전한 쪽) — 실값 {res['ok']!r}")
        chk(res["code"] == CP.NO_UNKNOWN, f"{label}: code=NO_UNKNOWN — 실값 {res['code']!r}")
        chk(res["amount"] is None, f"{label}: amount=None(파싱 실패를 0원으로 위장하지 않음) — 실값 {res['amount']!r}")
    except Exception as e:
        chk(False, f"{label}: 수정 후에도 크래시함! {type(e).__name__}: {e}")

# related_amount 쪽도 같은 가드를 타는지
for label, rel in (("related=inf", float("inf")), ("related=nan", float("nan"))):
    try:
        res = CP.check_direct_contract("종합 원상복구", 10_000_000, related_amount=rel)
        chk(res["ok"] is False, f"{label}: 크래시 없이 ok=False — 실값 {res['ok']!r}")
        chk(res["code"] == CP.NO_UNKNOWN, f"{label}: code=NO_UNKNOWN — 실값 {res['code']!r}")
    except Exception as e:
        chk(False, f"{label}: 수정 후에도 크래시함! {type(e).__name__}: {e}")

print()
print("=" * 70)
print("[3] 회귀 없음 — 정상적인 정수/문자열 금액은 그대로 기존처럼 동작하는가")
print("=" * 70)
r1 = CP.check_direct_contract("가드레일·방호울타리", 1_000_000)
chk(r1["code"] == CP.NO_TRADE and r1["ok"] is False, "정상 입력(배제업종): 기존과 동일하게 배제업종 판정")

r2 = CP.check_direct_contract("종합 원상복구", 10_000_000, related_amount=0)
chk(r2["ok"] is True and r2["code"] == CP.OK_DIRECT, "정상 입력(소액): 기존과 동일하게 도급가능 판정")

r3 = CP.check_direct_contract("종합 원상복구", "10000000", related_amount="0")
chk(r3["ok"] is True and r3["amount"] == 10_000_000, "숫자 문자열 입력: 기존과 동일하게 정수로 파싱되어 통과")

r4 = CP.check_direct_contract("종합 원상복구", 60_000_000, related_amount=0)
chk(r4["ok"] is False and r4["code"] == CP.NO_AMOUNT, "정상 입력(초과): 기존과 동일하게 금액초과 판정")

r5 = CP.check_direct_contract(None, 1_000_000)
chk(r5["code"] == CP.NO_UNKNOWN and r5["ok"] is False, "category=None(기존에도 있던 경로): 여전히 판정불가")

print()
print("=" * 70)
print(f"결과: {PASS} 통과, {FAIL} 실패")
print("=" * 70)
sys.exit(1 if FAIL else 0)
