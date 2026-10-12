# -*- coding: utf-8 -*-
"""스캔 264라운드 회귀 — geo.py 좌표 해석기 결함 2건
   (좌표계산 모듈 전체 감사 Agent 조사로 발견, 독립 재검증 후 수정).

  [1] _AMBIG 판정("이 구 이름이 어느 광역시/도 소속인지")이 매치 지점
      근처가 아니라 src 문자열 **전체 어디든** 있으면 통과시켰다. 실측
      (data/partners_seed.json, "(주)KAD(KAD한국자동문)"): region="경기(본사)
      + 부산·대구·광주 지사" 는 부산·대구와 함께 열거된 "광주"(지사)를
      "경기도 광주시"로 오판정해, 실주소(경기도 **화성시**)에서 45.4km
      벗어났다 — 이 문자열의 "경기"는 두 번(맨 앞 본사 설명, 뒤쪽 주소)
      다 "광주"를 실제로 수식하지 않는 무관한 언급인데, 문자열 전체를
      보면 둘 중 하나는 항상 걸린다. 매치 **바로 앞 10자**만 보도록
      좁혔다 — 이 폭은 실 시드데이터 397곳 전수와 대조해(4~30 사이 여러
      값 실측) 회귀 0건이 되는 구간(6~12) 안에서 고른 값이다.

  [2] `SIDO_ALIAS["광주시"]="광주"`(광역시 광주)가 영원히 도달 불가능한
      죽은 코드였다 — "광주시"라는 문자열 자체가 [1]의 _AMBIG["광주경기"]
      트리거 키워드이기도 해서, GU 판정 단계가 항상 먼저 가로채 경기도
      광주시로 확정해 버렸다("광주시"는 자기 자신을 포함하므로 need 검사가
      전체 문자열 기준으로는 항상 통과). [1]을 고치자 "그 앞에 경기라는
      단서가 없으면" 이 가로채기가 더 이상 안 일어나 SIDO_ALIAS 단계까지
      정상 도달한다 — 별도 코드 변경 없이 [1]의 직접적인 결과로 해결됨
      (실측으로 확인).

      python test_scan_round264_fixes.py
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


GEO_SRC = read("geo.py")

print("=" * 72)
print("  스캔 264라운드 회귀 — geo.py _AMBIG 원거리 오판정·죽은 SIDO_ALIAS")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk("_AMBIG_WINDOW = 10" in GEO_SRC, "★★★★ 근접판정 창(10자)이 상수로 생겼다")
i0 = GEO_SRC.index("def _word_in(")
i1 = GEO_SRC.index("\n\n\n#", i0)
wi_body = GEO_SRC[i0:i1]
chk("return -1" in wi_body and "return i" in wi_body,
    "★★★★ _word_in() 이 참/거짓 대신 매치 위치(없으면 -1)를 돌려준다")

i2 = GEO_SRC.index("def resolve(")
i3 = GEO_SRC.index("\n\n", GEO_SRC.index("return None, None, \"\"", i2))
resolve_body = GEO_SRC[i2:i3]
chk("pos = _word_in(disp, src)" in resolve_body and "pos >= 0" in resolve_body,
    "★★★★ resolve() 가 매치 위치를 받아 판정한다(참/거짓만 보지 않는다)")
chk("near = src[max(0, pos - _AMBIG_WINDOW):pos]" in resolve_body,
    "★★★★★ _AMBIG 근거는 src 전체가 아니라 매치 바로 앞 구간에서만 찾는다"
    "(고치기 전엔 문자열 전체 어디든 있으면 통과했다)")

# ============================================================
print("\n[2] 실행 — 실제 geo.resolve() 로 핵심 시나리오 전부 실측")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
try:
    import importlib
    import geo as GEO
    importlib.reload(GEO)

    r_kad = GEO.resolve("경기(본사) + 부산·대구·광주 지사",
                         "경기도 화성시 팔탄면 3.1만세로 625-49")
    chk(r_kad[2] == "화성 지역중심",
        "★★★★★ KAD 실사례 — 무관한 '경기' 언급에 더는 안 낚이고 "
        "실주소(화성)로 정확히 해석된다(고치기 전엔 45.4km 떨어진 '광주'였다)",
        r_kad)

    r_bare_si = GEO.resolve("광주시", "")
    chk(r_bare_si[2] == "광주 광역중심",
        "★★★★ 맨입 '광주시'는 이제 죽어있던 SIDO_ALIAS 매핑을 타고 "
        "광역시 좌표로 정상 해석된다(고치기 전엔 GU단계가 가로채 "
        "경기도 광주시로 잘못 확정했다)", r_bare_si)

    r_bare = GEO.resolve("광주", "")
    chk(r_bare[2] == "광주 광역중심", "STEP '광주'(시 없이)도 같은 광역시로 해석된다", r_bare)

    #  ── 대조군 — 진짜로 경기도 광주시를 가리키는 입력은 여전히 정확히 구분된다 ──
    r_real_gg = GEO.resolve("경기도 광주시", "")
    chk(r_real_gg[2] == "광주 지역중심" and r_real_gg[:2] != r_bare[:2],
        "★★★★ 대조군 — '경기'가 실제로 바로 앞에 있으면 여전히 경기도 "
        "광주시로 정확히 구분된다(과잉수정 아님, 광역시 좌표와 다른 좌표)",
        {"경기도광주시": r_real_gg, "광역시광주": r_bare})

    #  ── 대조군 — 기존에 이미 맞던 모호지역 판정들은 전부 그대로 ──
    chk(GEO.resolve("서울특별시 중구", "을지로 30")[2] == "중구 지역중심",
        "STEP 대조군 — 서울 중구는 그대로 정확하다")
    chk(GEO.resolve("부산광역시", "강서구 명지오션시티")[2] == "강서 지역중심",
        "STEP 대조군 — 부산 강서구는 그대로 정확하다")
    chk(GEO.resolve("경상남도", "고성군 어딘가")[2] == "고성 지역중심",
        "STEP 대조군 — 235라운드가 고친 경남 고성은 그대로 정확하다")

    #  ── 실 시드데이터 중 "창을 너무 좁히면 깨지는" 사례들 — _AMBIG_WINDOW 를
    #     10이 아니라 5 이하로 되돌리면 정확히 이 넷이 회귀한다(조사 중 실측).
    #     상수를 너무 타이트하게 "최적화"하는 미래 수정을 여기서 잡는다.
    seed = json.load(io.open(os.path.join(HERE, "data", "partners_seed.json"), encoding="utf-8"))
    by_name = {p.get("name"): p for p in seed}
    _margin_cases = [
        ("하늘방수", "남구 지역중심"),
        ("청아페인트 (청아방수)", "동구 지역중심"),
        ("조이자동문수리 (자동문수리서광 대리점)", "강서 지역중심"),
        ("오늘의 창호", "북구 지역중심"),
    ]
    for nm, expected in _margin_cases:
        p = by_name.get(nm)
        if p is None:
            chk(False, f"STEP 시드데이터에 '{nm}' 이 있어야 한다(대조 사례 유지 확인)")
            continue
        r = GEO.resolve(p.get("region") or "", p.get("address") or "")
        chk(r[2] == expected,
            f"STEP 대조군 — {nm} 는 창(10자)이 정상 접미어(광역시·특별시 등)를 "
            f"담기에 충분해 여전히 정확하다(창을 5 이하로 좁히면 이 사례가 깨진다)",
            r)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드264 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
