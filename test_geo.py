# -*- coding: utf-8 -*-
"""좌표 해석기 검증 — **내장 좌표가 실제로 그 자리인가**를 자동으로 따진다.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

이 파일의 가장 위험한 실패는 **틀린 좌표를 그럴듯하게 넣는 것**이다.
지도만 이상해지는 게 아니라 거리순 자동배차가 엉뚱한 업체를 먼저 부른다.
그래서 값 하나하나를 다음 기준으로 검사한다:
  · 한반도 안에 있는가 (위경도 뒤바뀜·오타 검출)
  · **소속 시도 중심에서 그 시도가 가질 수 있는 거리 안에 있는가**
    (예: '김천'을 전남 어딘가에 찍어 두면 여기서 걸린다)
  · 이름이 겹치는 구(중구·동구…)가 소속 시도 없이 잘못 잡히지 않는가
"""
import io
import sys
import math

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import geo as GEO

OK = FAIL = 0


def chk(cond, label, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}   {detail}")


# 각 시군구가 속한 시도 — 좌표 타당성 검사의 기준점
BELONGS = {
    "부산": ["동래", "금정", "사상", "사하", "영도", "동구부산", "부산진", "북구부산",
             "남구부산", "서구부산", "중구부산", "기장", "해운대", "연제", "수영"],
    "대구": ["중구대구", "동구대구", "서구대구", "남구대구", "북구대구", "달서", "수성", "달성"],
    "인천": ["미추홀", "연수", "남동", "부평", "계양", "서구인천", "중구인천", "동구인천",
             "강화", "옹진"],
    "광주": ["동구광주", "서구광주", "남구광주", "북구광주", "광산"],
    "대전": ["동구대전", "중구대전", "서구대전", "유성", "대덕"],
    "울산": ["중구울산", "남구울산", "동구울산", "북구울산", "울주"],
    "경기": ["광명", "군포", "의왕", "하남", "오산", "이천", "안성", "여주", "양평",
             "포천", "동두천", "구리", "과천", "가평", "연천"],
    "강원": ["속초", "동해", "삼척", "태백", "홍천", "횡성", "영월", "평창", "정선",
             "철원", "화천", "양구", "인제", "고성강원", "양양"],
    "충북": ["증평", "진천", "괴산", "음성", "단양", "보은", "옥천", "영동"],
    "충남": ["공주", "보령", "논산", "계룡", "금산", "부여", "서천", "청양", "홍성",
             "예산", "태안"],
    "전북": ["정읍", "남원", "김제", "완주", "진안", "무주", "장수", "임실", "순창",
             "고창", "부안"],
    "전남": ["나주", "광양", "담양", "곡성", "구례", "고흥", "보성", "화순", "장흥",
             "강진", "해남", "영암", "무안", "함평", "영광", "장성", "완도", "진도", "신안"],
    "경북": ["김천", "영주", "영천", "상주", "문경", "경산", "의성", "청송", "영양",
             "영덕", "청도", "고령", "성주", "칠곡", "예천", "봉화", "울진", "군위"],
    "경남": ["통영", "사천", "밀양", "함안", "창녕", "고성경남", "남해", "하동", "산청",
             "함양", "거창", "합천", "의령"],
}
# 시도별로 중심에서 떨어질 수 있는 최대치(km) — 넉넉히 잡되 타 시도로는 못 가게
MAX_KM = {"부산": 45, "대구": 45, "인천": 70, "광주": 30, "대전": 30, "울산": 50,
          "경기": 90, "강원": 130, "충북": 100, "충남": 110, "전북": 90,
          "전남": 130, "경북": 130, "경남": 110}


def main():
    print("=" * 70)
    print("  좌표 해석기 검증")
    print("=" * 70)

    # ── 1. 모든 내장 좌표가 한반도 안인가 ─────────────────────────
    print("\n[1] 좌표 범위 — 위경도 뒤바뀜·오타")
    bad = []
    for name, (lat, lng) in {**GEO.GU, **GEO.SIDO, **GEO.KWON}.items():
        if not (33.0 <= lat <= 38.7 and 124.5 <= lng <= 132.0):
            bad.append((name, lat, lng))
    chk(not bad, f"★ 내장 좌표 {len(GEO.GU)+len(GEO.SIDO)+len(GEO.KWON)}개 전부 한반도 범위 안", bad[:5])

    # ── 2. 시군구가 소속 시도 안에 있는가 (가장 중요) ─────────────
    print("\n[2] 소속 시도 대조 — 엉뚱한 도에 찍힌 좌표 색출")
    off = []
    for sido, names in BELONGS.items():
        slat, slng = GEO.SIDO[sido]
        for n in names:
            if n not in GEO.GU:
                off.append((n, "GU 에 없음"))
                continue
            lat, lng = GEO.GU[n]
            d = GEO.haversine_km(slat, slng, lat, lng)
            if d > MAX_KM[sido]:
                off.append((n, f"{sido} 중심에서 {d:.0f}km (허용 {MAX_KM[sido]})"))
    chk(not off, f"★★ 시군구 {sum(len(v) for v in BELONGS.values())}곳이 모두 소속 시도 안에 있음", off[:6])

    # ── 3. 시도 정식명 폴백 (실제로 사라졌던 버그) ────────────────
    print("\n[3] 시도 정식명 — '경상북도' 같은 표기가 해석되는가")
    for full, short in [("경상북도", "경북"), ("충청남도", "충남"), ("전라북도", "전북"),
                        ("강원특별자치도", "강원"), ("제주특별자치도", "제주")]:
        lat, lng, src = GEO.resolve(full, "")
        chk(lat is not None and short in src, f"  {full} → {short}", src)

    # ── 4. 이름이 겹치는 구 — 소속 없이 잘못 잡히지 않는가 ────────
    print("\n[4] 동명 구 판정")
    for full, key in [("부산광역시 중구", "중구부산"), ("대구광역시 중구", "중구대구"),
                      ("인천광역시 서구", "서구인천"), ("광주광역시 북구", "북구광주"),
                      ("울산광역시 남구", "남구울산")]:
        la, ln, sr = GEO.resolve(full, "")
        near = (la is not None
                and GEO.haversine_km(la, ln, *GEO.GU[key]) < 3)
        chk(near, f"★ '{full}' → {key}", sr)
    # 같은 '중구'라도 소속 시도가 다르면 다른 자리여야 한다
    a = GEO.resolve("부산광역시 중구", "")[:2]
    b = GEO.resolve("대구광역시 중구", "")[:2]
    chk(a != b and GEO.haversine_km(*a, *b) > 50,
        "  부산 중구 ≠ 대구 중구 (같은 점으로 뭉개지지 않음)",
        f"{GEO.haversine_km(*a, *b):.0f}km")

    # ── 5. 실제 데이터에서 좋아졌는가 ─────────────────────────────
    print("\n[5] 등록 협력사 전수 — 해석률")
    try:
        import os
        os.environ.setdefault("BOKGUON_ENV", "prod")
        import db as DB
        conn = DB.get_db()
        rs = conn.execute("SELECT region, address FROM partners WHERE status='활성'").fetchall()
        conn.close()
        kinds = {"지역중심": 0, "광역중심": 0, "권역": 0, "미해석": 0}
        for x in rs:
            lat, lng, src = GEO.resolve(x["region"], x["address"])
            if lat is None:
                kinds["미해석"] += 1
            elif "지역중심" in src:
                kinds["지역중심"] += 1
            elif "광역중심" in src:
                kinds["광역중심"] += 1
            else:
                kinds["권역"] += 1
        tot = len(rs)
        print(f"       전체 {tot}곳 → {kinds}")
        chk(kinds["미해석"] <= 3, "★ 위치를 못 잡는 업체가 3곳 이하(정보 자체가 없는 곳만)",
            kinds["미해석"])
        chk(kinds["지역중심"] / max(tot, 1) >= 0.85,
            "★ 85% 이상이 시군구 수준으로 해석됨",
            f"{kinds['지역중심']}/{tot} = {kinds['지역중심']/max(tot,1)*100:.0f}%")
    except Exception as ex:
        print(f"  [건너뜀] 운영 DB 조회 불가: {ex}")

    print("-" * 70)
    print(f"  통과 {OK} · 실패 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
