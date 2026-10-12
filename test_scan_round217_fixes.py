# -*- coding: utf-8 -*-
"""스캔 217라운드 회귀 — ingest_partners.py 의 load_journal() 이 저널의 최종
   "result" 가 dict 가 아니라 문자열(에이전트 CLI 의 실제 산출물 모양)이면
   AttributeError 로 적재 전체가 죽고, companies 키가 없는 dict 는 조용히
   버리던 결함(217라운드 조사 에이전트가 실행으로 재현).

   이 모듈은 지금까지 216라운드 동안 한 번도 감사되지 않았고 테스트도
   전혀 없었다 — deploy/bootstrap.sh 에서만 참조된다.

      python test_scan_round217_fixes.py
"""
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("═" * 72)
print("  스캔 217라운드 회귀 — ingest_partners.load_journal 의 result 모양 처리")
print("═" * 72)

sys.path.insert(0, HERE)
import ingest_partners as IP  # noqa: E402


def write_journal(lines):
    fd, path = tempfile.mkstemp(prefix="round217_journal_", suffix=".jsonl")
    with io.open(fd, "w", encoding="utf-8") as f:
        for ln in lines:
            f.write(ln + "\n")
    return path


# ══════════════════════════════════════════════════════════════
print("\n[1] 정상 케이스 — result 가 dict 인 기존 동작(회귀 아님, 안 깨졌는지만)")
# ──────────────────────────────────────────────────────────────
p1 = write_journal([
    json.dumps({"type": "progress", "text": "검색 중"}, ensure_ascii=False),
    json.dumps({"type": "result", "result": {"companies": [
        {"name": "정상업체A", "source_url": "https://a.example"},
        {"name": "정상업체B", "source_url": "https://b.example"},
    ]}}, ensure_ascii=False),
])
try:
    out1 = IP.load_journal(p1)
    chk(len(out1) == 2 and {c["name"] for c in out1} == {"정상업체A", "정상업체B"},
        "STEP result 가 정상 dict 일 때는 여전히 그대로 수집된다(과잉차단 아님)", out1)
finally:
    os.remove(p1)

# ══════════════════════════════════════════════════════════════
print("\n[2] result 가 순수 텍스트(JSON 아님) — 죽지 않고 그 줄만 건너뛰어야 한다")
# ──────────────────────────────────────────────────────────────
p2 = write_journal([
    json.dumps({"type": "result", "result": "조사를 마쳤습니다. 총 3곳을 찾았고 보고서는 위와 같습니다."},
               ensure_ascii=False),
])
try:
    out2 = IP.load_journal(p2)
    chk(out2 == [],
        "★★★★ result 가 에이전트의 평범한 최종 답변 텍스트여도 예외 없이 "
        "빈 목록으로 넘어간다(예전엔 AttributeError 로 적재 전체가 죽었다)", out2)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★ result 가 순수 텍스트일 때 죽지 않아야 한다", f"{type(e).__name__} {e}")
finally:
    os.remove(p2)

# ══════════════════════════════════════════════════════════════
print("\n[3] result 가 'JSON 을 담은 문자열' — 그 안의 companies 까지 복구해야 한다")
# ──────────────────────────────────────────────────────────────
inner = json.dumps({"companies": [{"name": "문자열속업체", "source_url": "https://c.example"}]},
                    ensure_ascii=False)
p3 = write_journal([
    json.dumps({"type": "result", "result": inner}, ensure_ascii=False),
])
try:
    out3 = IP.load_journal(p3)
    chk(len(out3) == 1 and out3[0]["name"] == "문자열속업체",
        "★★★ result 가 JSON 을 그대로 텍스트로 감싼 경우, 그 안의 companies 를 "
        "복구해 수집한다(파일 자신의 주석이 원래 의도했던 '흡수'를 실제로 구현)", out3)
finally:
    os.remove(p3)

# ══════════════════════════════════════════════════════════════
print("\n[4] result 가 dict 이지만 companies 키가 없음 — 조용히 안 버리고 건너뛰기만")
# ──────────────────────────────────────────────────────────────
p4 = write_journal([
    json.dumps({"type": "result", "result": {"summary": "3곳 발견", "count": 3}},
               ensure_ascii=False),
])
try:
    out4 = IP.load_journal(p4)
    chk(out4 == [],
        "STEP result dict 에 companies 키가 없으면 예외 없이 건너뛴다(데이터 손실은 "
        "그대로지만 최소한 죽지는 않는다)", out4)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ companies 키 없는 dict 도 죽지 않아야 한다", f"{type(e).__name__} {e}")
finally:
    os.remove(p4)

# ══════════════════════════════════════════════════════════════
print("\n[5] 혼합 저널 — 한 줄이 깨져도 나머지 정상 줄은 살아남아야 한다")
# ──────────────────────────────────────────────────────────────
p5 = write_journal([
    "이건 JSON 도 아닌 완전히 깨진 줄입니다 {{{",
    json.dumps({"type": "progress"}, ensure_ascii=False),
    json.dumps({"type": "result", "result": "그냥 텍스트 답변"}, ensure_ascii=False),
    json.dumps({"type": "result", "result": {"companies": [
        {"name": "살아남은업체", "source_url": "https://d.example"}]}}, ensure_ascii=False),
])
try:
    out5 = IP.load_journal(p5)
    chk(len(out5) == 1 and out5[0]["name"] == "살아남은업체",
        "★★★ 저널 앞쪽 줄들이 깨지거나 텍스트여도, 뒤쪽 정상 줄의 companies 는 "
        "끝까지 수집된다(한 줄의 예외가 전체 적재를 막지 않는다)", out5)
finally:
    os.remove(p5)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
