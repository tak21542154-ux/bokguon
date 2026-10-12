# -*- coding: utf-8 -*-
"""스캔 316라운드 회귀 — geo.py 결함 2건, 이 세션 사상 첫 정밀조사한 정밀조사
   Agent가 발견(totp.py·addr_search.py 는 같은 라운드가 전담 재조사했으나 실결함
   없음 — 클린).

   ① [심각] 2022년부터 수원·고양·용인·창원 4개 시가 '특례시' 행정명칭을 쓰는데
      (예: '용인특례시'), resolve() 가 시군구 매칭에 쓰는 _word_in() 의 오른쪽
      경계검사(_ADMIN_SUFFIX)는 지명 뒤 **한 글자**만 보고, '특'은 그 문자
      클래스에 없다 — 시군구 단위로 정확히 찾을 수 있는 주소가 훨씬 부정확한
      도(道) 단위 폴백까지 밀려났다(실측: 운영DB 협력사 #211 하우건설(주)의
      실주소 '경기도 용인특례시 처인구...'가 정확히 이 표기, 좌표오차가 정상
      '용인시' 대비 약 5배(6.35km→31.4km) 벌어짐). resolve() 진입 시 '특례시'를
      '시'로 미리 바꿔 4개 시 전부(향후 추가되는 특례시도) 해결.
   ② [경미, 현재는 도달불가] case_coords(None) 이 형제(partner_coords)와 달리
      region/address 조회를 _has() 로 안 감싸 AttributeError 로 죽는다 — 지금
      호출부 4곳은 전부 사전에 None 을 걸러내거나 예외로 감싸 실제로는 안
      터지지만, 형제와 다른 패턴을 유지할 이유가 없어 통일.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import geo as GEO  # noqa: E402

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
print("  스캔 316라운드 회귀 — geo.py 특례시 매칭실패 + case_coords(None) 크래시")
print("=" * 74)

print("\n[1] 실행 — 4개 특례시 전부 도(道) 단위 아니라 시군구 단위로 정확히 잡힌다")
CASES = [
    ("경기", "경기도 용인특례시 처인구 신송로131번길 20-10", "경기", "경기도 용인시 처인구 신송로131번길 20-10"),
    ("경기", "경기도 수원특례시 영통구 청명남로 111", "경기", "경기도 수원시 영통구 청명남로 111"),
    ("경기", "경기도 고양특례시 일산동구 중앙로 1275", "경기", "경기도 고양시 일산동구 중앙로 1275"),
    ("경남", "경상남도 창원특례시 의창구 창이대로 542", "경남", "경상남도 창원시 의창구 창이대로 542"),
]
for region, addr_special, region2, addr_plain in CASES:
    lat_s, lng_s, src_s = GEO.resolve(region, addr_special)
    lat_p, lng_p, src_p = GEO.resolve(region2, addr_plain)
    city = src_p.replace(" 지역중심", "")
    chk(src_s == src_p and (lat_s, lng_s) == (lat_p, lng_p),
        f"★★★★★ '{addr_special[:12]}...' 이 '{city}'로 '{addr_plain[:12]}...'과 동일하게 잡힌다"
        "(고치기 전엔 도 단위 광역중심으로 밀려났다)",
        (src_s, src_p))
    chk("지역중심" in src_s and "광역중심" not in src_s,
        f"  {city} — 시군구 단위(지역중심)이지 광역중심 폴백이 아니다", src_s)

print("\n[2] 실행 — 운영DB 실사례 재현(협력사 #211 하우건설(주) 실주소)")
lat, lng, src = GEO.resolve("경기", "경기도 용인특례시 처인구 신송로131번길 20-10")
lat0, lng0 = GEO.GU["용인"]
dist = GEO.haversine_km(lat, lng, lat0, lng0)
chk(dist is not None and dist < 1.0,
    "★★★★ 실주소 재현 결과가 GU['용인'] 중심좌표와 사실상 같다(지역중심 매칭 확인)",
    dist)

print("\n[3] 실행 — 회귀 없음: 특례시 아닌 기존 시군구는 그대로 정상 매칭")
lat, lng, src = GEO.resolve("경기", "경기도 안산시 단원구 화랑로 260")
chk(src == "안산 지역중심", "  안산시(특례시 아님)는 여전히 정상 매칭", src)
lat, lng, src = GEO.resolve("인천", "인천광역시 남동구 청능대로 289")
chk(src == "남동 지역중심", "  남동구(라운드196 형제 지명 판정)도 회귀 없음", src)

print("\n[4] 실행 — case_coords(None) 이 더는 크래시하지 않는다")
try:
    r = GEO.case_coords(None)
    chk(r == (None, None, ""), "★★★ case_coords(None) 이 예외 없이 빈 값을 돌려준다"
        "(형제 partner_coords(None) 과 동일한 안전 반환)", r)
except Exception as ex:
    chk(False, "★★★ case_coords(None) 이 예외 없이 빈 값을 돌려준다", repr(ex))

print("\n[5] 실행 — 회귀 없음: case_coords() 의 기존 정상 경로(수동좌표·주소해석) 그대로")
r = GEO.case_coords({"id": 1, "lat": 37.5, "lng": 127.0, "geo_src": "주소검색"})
chk(r == (37.5, 127.0, "주소검색"), "  수동/기존 좌표 경로 회귀 없음", r)
r = GEO.case_coords({"id": 2, "region": "경기", "address": "경기도 안산시 단원구", "lat": None, "lng": None})
chk(r[2] == "안산 지역중심", "  주소해석 폴백 경로도 회귀 없음", r)
chk(GEO.partner_coords(None) == (None, None, ""),
    "  형제 partner_coords(None) 은 원래도 안전했다(대조군, 회귀 없음)")

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
