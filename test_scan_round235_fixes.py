# -*- coding: utf-8 -*-
"""스캔 235라운드 회귀 — geo.py 좌표 해석기의 두 결함(Agent 병렬조사로 발견).

  [1] _AMBIG["고성경남"] 판정이 SIDO_ALIAS 를 거치지 않은 원문에 대고 '경남'을
      찾는다 — '경남'은 정식명 '경상남도'의 부분문자열이 **아니다**(SIDO_ALIAS
      자체를 만든 이유와 정확히 같은 함정: '경'+'상'+'남'+'도'). 실측
      (data/partners_seed.json): region='경상남도' 협력사가 실존하는데, 이
      판정이 항상 실패해 고성경남(군) 좌표를 못 쓰고 경남 광역중심(시청)으로
      약 55km 벗어났다. 정식명 '경상남도'를 그대로 추가해 고친다.

  [2] case_coords() 가 좌표가 있으면 무조건 "수동"이라고 적어, 실제 geo_src
      컬럼(주소검색 등)을 무시했다 — 그 컬럼을 이미 올바르게 읽는 형제
      함수(partner_coords, 라운드216)와 대조해서 드러났다. 사건 상세 지도·
      관제 지도·인근업체 API·협력사 진행목록이 전부 이 잘못된 출처를 그대로
      화면에 보여준다.

      python test_scan_round235_fixes.py
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


GEO_SRC = read("geo.py")

print("=" * 72)
print("  스캔 235라운드 회귀 — geo.py 좌표 해석기 결함 2건")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk('"고성경남": ("경남", "경상남도", "통영", "사천")' in GEO_SRC,
    "★★★★ _AMBIG['고성경남'] 이 정식명 '경상남도'도 받아들인다")
i_cc = GEO_SRC.index("def case_coords(")
i_cc_end = GEO_SRC.index("\ndef ", i_cc + 1)
cc_body = GEO_SRC[i_cc:i_cc_end]
chk('row["geo_src"] if _has(row, "geo_src") else None' in cc_body,
    "★★★★ case_coords() 가 이제 partner_coords() 와 같은 방식으로 geo_src 를 읽는다")
chk('return float(mlat), float(mlng), (gs or "수동")' in cc_body,
    "★★★ geo_src 가 없는 옛 행은 여전히 '수동'으로 안전하게 폴백한다")

# ============================================================
print("\n[2] 실행 — 결함1: 고성경남 정식명 표기")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
try:
    import geo as GEO

    r_full = GEO.resolve("경상남도", "고성군 고성읍 수남리 123")
    r_short = GEO.resolve("경남", "고성군 고성읍 수남리 123")
    chk(r_full[0] is not None and r_full == r_short,
        "★★★★ '경상남도'(정식명)로도 '경남'(단축형)과 똑같이 고성 군 단위"
        "좌표를 잡는다(고치기 전엔 광역중심 시청 좌표로 약 55km 벗어났다)",
        {"경상남도": r_full, "경남": r_short})
    chk(r_full[2] == "고성 지역중심", "STEP 출처 문구도 군 단위(지역중심)로 뜬다", r_full)

    # 회귀 없음 — 이미 정상이던 강원도 고성은 그대로 정상이어야 한다
    r_gangwon = GEO.resolve("강원도", "고성군 간성읍")
    chk(r_gangwon[2] == "고성 지역중심",
        "STEP 강원도 고성(원래도 정상)에 회귀가 없다", r_gangwon)

    # 다른 동명 시도명(경상북도 등)에는 영향이 없어야 한다(범위 최소화 확인)
    r_gb = GEO.resolve("경상북도", "김천시")
    chk(r_gb[2] == "김천 지역중심", "STEP 무관한 지역(경상북도 김천)에 부작용 없음", r_gb)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드235 [2] 실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — 결함2: case_coords() 의 geo_src 반영")
# ------------------------------------------------------------
try:
    class _FakeRow(dict):
        def keys(self):
            return dict.keys(self)

    row_geocoded = _FakeRow(lat=37.111111, lng=127.111111, geo_src="주소검색",
                             region="", address="", id=1)
    lat, lng, src = GEO.case_coords(row_geocoded)
    chk(src == "주소검색",
        "★★★★ geo_src='주소검색'인 사건은 case_coords() 도 그 출처를 그대로 "
        "돌려준다(고치기 전엔 좌표만 있으면 무조건 '수동'이었다)",
        {"lat": lat, "lng": lng, "src": src})

    row_manual = _FakeRow(lat=37.2, lng=127.2, geo_src=None, region="", address="", id=2)
    _, _, src2 = GEO.case_coords(row_manual)
    chk(src2 == "수동",
        "STEP geo_src 가 없는 옛 행(진짜 수동입력)은 여전히 '수동'으로 표시된다", src2)

    row_no_geo_src_col = {"lat": 37.3, "lng": 127.3, "region": "", "address": "", "id": 3}
    _, _, src3 = GEO.case_coords(row_no_geo_src_col)
    chk(src3 == "수동",
        "STEP geo_src 컬럼 자체가 없는(구버전 스키마) 행 딕셔너리도 안전하게 "
        "'수동' 폴백(KeyError 로 안 죽는다)", src3)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드235 [3] 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
