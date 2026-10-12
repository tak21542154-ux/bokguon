# -*- coding: utf-8 -*-
"""스캔 293라운드 회귀 — geo.py 미조사 함수 결함 2건, resolve()의 _AMBIG·
   SIDO_ALIAS(235·264라운드)와 case_coords()(235라운드)만 다뤄지고 나머지
   7개 함수(_norm·_word_in·jitter·haversine_km·partner_coords·_has·
   is_precise)는 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 —
   haversine_km·is_precise·partner_coords·_has·_norm 은 실측(실 DB·시드
   데이터·기존 회귀 143건 재실행) 결과 전부 클린.

  ① jitter() — 사건이 몰린 지도에서 안 겹치게 흩뿌리는 결정적 오프셋인데,
     dx·dy 를 각각 -1~1 로 뽑아 그대로 더해 반경이 meters 가 아니라
     **정사각형**(대각선 최대 meters*√2)이었다. 실측: meters=350 기준
     실제 최악거리 447m(1.28배 초과), 10만 개 case_id 표본의 12.5%가
     초과. 게다가 경도에도 위도와 같은 배율을 그대로 써서 위선이 극에
     가까울수록 실거리가 짧아진다는 걸 안 봐(서울 위도 기준 동서:남북
     = 0.79:1) 동서 방향이 실제보다 덜 벌어졌다. 각도+반경(넓이 기준
     고른 분포)으로 뽑고 경도는 cos(위도)로 나눠 보정 — 심각도는 낮다
     (jitter 는 프라이버시가 아니라 지도 마커 겹침 방지용일 뿐이고, 구
     단위 지도에서 수백 미터 오차는 실제로 다른 구·바다로 넘어가지
     않음을 실측 확인).
  ② _word_in()의 오른쪽 경계 판정이 방위+구(서구·중구·동구·남구·북구)를
     공백 없이 바로 뒤에 다른 지명이 붙으면(예: "서구청라동") 놓쳤다 —
     "구"가 실제로 그 이름 자체의 행정단위 접미어인데, 뒤 글자가 시군구
     읍면동리 중 하나가 아니면 무조건 거부해 인천 서구(지역중심) 대신
     인천 광역중심(도시 전체)까지 밀려났다("서구 청라동"처럼 공백이
     있으면 이미 정상 매치됐다 — 오직 붙여 쓴 경우만 놓쳤다). 실측: 실
     DB 96건·partners 399건·시드데이터 398건 전수에 이 패턴이 0건이라
     현재 오작동 사례는 없음(잠재 결함) — 그러나 강동·구리·성동·안동·
     양구·영동·정읍·하동처럼 **우연히** 같은 글자로 끝나는 무관한
     지명(라운드120이 막은 함정과 같은 종류, 예: "강동원")까지 함께
     풀어주면 그 보호가 깨지므로, _AMBIG 의 실제 키를 전수 확인해 진짜
     복합 행정명 5개(중구·동구·서구·남구·북구)만 좁혀서 예외로 뒀다.
  부수적으로 GU 딕셔너리의 23개 키가 뒤(보강분) 섹션에서 그대로 다시
  선언돼 앞쪽 값이 파이썬 딕셔너리 특성상 절대 안 읽히는 죽은 코드였다
  (차이는 대부분 0~45m, 최대 472m — 실사고 없음). 앞뒤 값이 여러 쌍
  완전히 동일해 텍스트만으로 안전하게 "첫 번째만" 골라 지울 수 없어
  이번엔 제거 대신 그 사실을 코드에 명시만 해 뒀다(다음 기회로 미룸).

      python test_scan_round293_fixes.py
"""
import hashlib
import io
import math
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
print("  스캔 293라운드 회귀 — geo.py jitter()·_word_in() 결함 2건")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk("radius = meters * math.sqrt(h[1] / 255.0)" in GEO_SRC,
    "★★★ jitter() 가 각도+반경(넓이 기준)으로 원 안에 고르게 뽑는다")
chk("math.cos(math.radians(lat))" in GEO_SRC,
    "★★★ jitter() 가 경도를 cos(위도)로 보정한다")
chk('_COMPOUND_ADMIN = {"중구", "동구", "서구", "남구", "북구"}' in GEO_SRC,
    "★★★ _word_in() 이 복합 행정명 5개만 좁혀서 오른쪽 경계 예외를 둔다")

# ============================================================
print("\n[2] 실행 — jitter() 가 실제로 meters 안에 들어가는가")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
try:
    import geo as GEO

    def _haversine_km(lat1, lng1, lat2, lng2):
        R = 6371.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlmb = math.radians(lng2 - lng1)
        a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
        return R * 2 * math.asin(min(1.0, math.sqrt(a)))

    SEOUL = (37.5665, 126.9780)
    worst = 0.0
    for i in range(20000):
        lat2, lng2 = GEO.jitter(f"case-{i}", *SEOUL, meters=350)
        worst = max(worst, _haversine_km(*SEOUL, lat2, lng2) * 1000)
    chk(worst <= 351.0,
        "★★★ jitter(meters=350) 의 실제 최대거리가 350m 안에 든다"
        "(고치기 전엔 대각선 최대 495m, 실측 최악 447m)", f"{worst:.1f}m")

    # 결정적(같은 case_id → 항상 같은 결과) 성질은 유지돼야 한다(docstring 의 핵심 약속)
    a1 = GEO.jitter("고정사건77", *SEOUL, meters=350)
    a2 = GEO.jitter("고정사건77", *SEOUL, meters=350)
    chk(a1 == a2, "jitter() 는 여전히 결정적이다(같은 case_id → 같은 결과, 회귀 없음)")

    # lat=None 이면 그대로 통과(회귀 없음)
    chk(GEO.jitter("x", None, None) == (None, None),
        "jitter() 는 lat=None 이면 그대로 (None, None) 을 돌려준다(회귀 없음)")

    # 동서(경도)·남북(위도) 로 각각 순수하게 치우치는 case_id 를 찾아
    # 위도 보정이 실제로 걸리는지 확인(치우침이 없으면 비율이 1:1 이어야 정상인
    # 옛 코드와 달리, 고친 코드는 각도가 있어 순수 동서만 뽑는 case_id 를
    # 직접 찾기보단, 위도 자체가 다른 두 지점에서 "같은 각도"의 거리 차이로 검증한다.
    lat_seoul, lat_busan = 37.5665, 35.1796
    d_seoul = GEO.jitter("교차검증", lat_seoul, 126.9780, meters=300)
    d_busan = GEO.jitter("교차검증", lat_busan, 129.0756, meters=300)
    dist_seoul = _haversine_km(lat_seoul, 126.9780, *d_seoul) * 1000
    dist_busan = _haversine_km(lat_busan, 129.0756, *d_busan) * 1000
    chk(dist_seoul <= 301.0 and dist_busan <= 301.0,
        "서로 다른 위도(서울·부산) 에서도 실제 이동거리가 meters 안에 든다",
        (dist_seoul, dist_busan))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드293 [2] jitter() 검증", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — _word_in()/resolve() 가 붙여 쓴 구 이름을 정확히 잡는가")
# ------------------------------------------------------------
try:
    # 3-a: 핵심 재현 — 공백 없이 붙은 구 이름
    pos1 = GEO._word_in("서구", "서구청라동 123")
    chk(pos1 >= 0,
        "★★★ _word_in('서구','서구청라동 123') 이 이제 매치된다(고치기 전엔 -1)", pos1)

    lat_a, lng_a, why_a = GEO.resolve("인천", "서구청라동 123")
    lat_b, lng_b, why_b = GEO.resolve("인천", "서구 청라동 123")   # 공백 있음 — 원래도 정상
    chk(why_a == why_b == "서구 지역중심" and (lat_a, lng_a) == (lat_b, lng_b),
        "★★★ resolve() 가 공백 유무와 무관하게 인천 서구로 동일하게 잡는다"
        "(고치기 전엔 붙여 쓴 쪽만 '인천 광역중심'으로 밀려남)",
        ((lat_a, lng_a, why_a), (lat_b, lng_b, why_b)))

    # 3-b: 회귀 없음 — 라운드120 이 막은 함정(동해대로의 동해)은 여전히 안 잡힘
    pos2 = GEO._word_in("동해", "동해대로 123")
    chk(pos2 < 0,
        "★★★ _word_in('동해','동해대로 123') 은 여전히 안 잡힌다"
        "(라운드120 보호 유지 — '동해'는 복합행정명이 아니므로 이번 수정과 무관)", pos2)
    lat_c, lng_c, why_c = GEO.resolve("강원", "동해대로 123")
    chk(why_c == "강원 광역중심",
        "★★★ resolve('강원','동해대로 123') 은 여전히 도 중심으로만 떨어진다"
        "(동해시 특정 좌표로 오판정되지 않음)", why_c)

    # 3-c: 회귀 없음 — 새 예외 목록에 없는, 우연히 같은 글자로 끝나는 지명은
    #     여전히 엄격하게 걸러진다(예외를 넓게 주면 이 보호가 깨진다)
    pos3 = GEO._word_in("강동", "강동원 주연 영화")
    chk(pos3 < 0,
        "★★★ _word_in('강동','강동원 주연 영화') 은 여전히 안 잡힌다"
        "('강동'은 우연히 '동'으로 끝날 뿐 복합행정명이 아니므로 예외 대상 아님)", pos3)

    # 3-d: 예외 목록 5개 전부 같은 패턴으로 통과하는지
    cases = [("서구", "서구인천사업소"), ("중구", "중구본점"),
             ("동구", "동구지점"), ("남구", "남구창고"), ("북구", "북구영업소")]
    all_ok = all(GEO._word_in(nm, txt) >= 0 for nm, txt in cases)
    chk(all_ok, "★★★ 복합행정명 5개(서구·중구·동구·남구·북구) 전부 붙여써도 매치된다", cases)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드293 [3] _word_in()/resolve() 검증", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
