# -*- coding: utf-8 -*-
"""스캔 159라운드 회귀 — geocode_fill.py 의 동네일치 판정(_region_ok)이
"구" 단위가 없는 시/군 대부분에서 사실상 무력화돼 있던 결함.

  "전남광주통합특별시 북구"처럼 **한쪽만** 구 정보가 없는 통합표기를
  구제하려는 예외(`not (wg and gg)`)가, **양쪽 다** 구 정보가 없는 경우
  (김해시·진주시·고양시·안산시·군산시·익산시 등 "구"가 없는 전국 대부분의
  시·군)까지 통과시켰다. 그 결과 이미 이름 자체가 다르다고 판정된(w&g 불일치)
  두 도시가 "같은 시도"라는 이유만으로 같은 동네로 통과됐다 — 파일 자신의
  안전원칙("검색 결과가 다른 시군구를 가리키면 채우지 않는다")이 광역시·
  일부 경기 대도시를 벗어나면 사실상 무력화돼 있었다는 뜻이다.

  이 좌표는 dispatch.py 의 거리순 배차 정렬에 그대로 쓰이므로, 틀린 도시
  좌표가 '정밀 주소'라는 신뢰도 딱지까지 붙은 채 저장될 수 있었다.

      python test_scan_round159_fixes.py
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


SRC = read("geocode_fill.py")

print("=" * 72)
print("  스캔 159라운드 회귀 — 구 없는 시/군에서 동네일치 판정이 무력화되던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = SRC.index("def _region_ok(")
i1 = SRC.index("\ndef ", i0 + 1)
body = SRC[i0:i1]
chk("return bool(wg & gg) or not (wg and gg)" not in body,
    "★★★ 양쪽 다 구 정보가 없으면 무조건 통과시키던 옛 조건이 사라졌다")
chk("bool(wg) != bool(gg)" in body,
    "★★★ 한쪽만 구 정보가 있을 때(정보 비대칭)만 구제하도록 바뀌었다")

# ============================================================
print("\n[2] 실행 — 실제 _region_ok() 호출")
# ------------------------------------------------------------
import tempfile
#  ⚠ _region_ok() 자체는 DB 를 안 쓰지만, geocode_fill.py 최상단이 무조건
#    db 를 import 한다 — 그 import 가 운영 DB 기본경로 안전장치에 걸린다.
os.environ["BOKGUON_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="round159_"), "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
sys.path.insert(0, HERE)
try:
    import geocode_fill as GF

    # ── 기존 자체점검 8건 — 회귀 없이 그대로 유지되는가 ──
    chk(GF._region_ok("서울 송파구 올림픽로", "서울 송파구"), "★ (기존) 같은 구는 통과")
    chk(GF._region_ok("경기 성남시 분당구", "경기 성남시"), "★ (기존) 시군구 일부일치 통과")
    chk(not GF._region_ok("서울 송파구", "서울 강남구"), "★ (기존) 다른 구는 거른다")
    chk(not GF._region_ok("서울 송파구", "부산 해운대구"), "★ (기존) 다른 시도·다른 구는 거른다")
    chk(GF._region_ok("서울", "서울 송파구"), "★ (기존) 시군구 못 뽑으면 시도로 판정")
    chk(GF._region_ok("광주 (북구)", "전남광주통합특별시 북구"),
        "★★ (기존) 통합표기라도 구가 같으면 통과")
    chk(GF._region_ok("광주광역시", "전남광주통합특별시 남구"),
        "★★★ (기존) 통합표기 정보비대칭 구제 — 이번 수정으로도 계속 살아있어야 한다")
    chk(not GF._region_ok("광주 북구", "전남광주통합특별시 서구"),
        "★★ (기존) 통합표기라도 구가 다르면 여전히 거른다")

    # ── 신규 — 구가 없는 시/군끼리 이름이 다르면 이제 거른다(고치기 전엔 전부 통과) ──
    chk(not GF._region_ok("경남 김해시 삼계로 100", "경남 진주시 동부로 20"),
        "★★★ 김해시 vs 진주시(80km+ 이격) — 이제 거른다")
    chk(not GF._region_ok("경기 고양시 어딘가", "경기 안산시 어딘가"),
        "★★★ 고양시 vs 안산시 — 이제 거른다")
    chk(not GF._region_ok("전북 군산시 조촌동", "전북 익산시 어양동"),
        "★★★ 군산시 vs 익산시 — 이제 거른다")

    # ── 대조군 — 구가 없는 시/군이라도 이름이 같으면 여전히 통과(과잉차단 아님) ──
    chk(GF._region_ok("경남 김해시 삼계로 100", "경남 김해시 어딘가"),
        "★ 같은 시(김해시)면 여전히 통과 — 과잉차단 아님")
    chk(not GF._region_ok("경남 김해시", "전남 진주시"),
        "★ 시도까지 다르면 당연히 거른다(대조군)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드159 [2] _region_ok 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
