# -*- coding: utf-8 -*-
"""스캔 516라운드 회귀 — addr_search.py _open_map() 의 place(장소) 검색 결과가
   구(區)가 있는 시(성남·수원·용인·고양·안양·부천·안산·청주·전주·포항·창원 등)에서
   그 구를 통째로 잘라 region 을 "도+시"까지만 돌려주던 결함.

  직접 조사(하위위임 없음) — run_all_tests.py 전체를 먼저 정독해 이미 포화된 축
  (형제 엔드포인트 잠금 비대칭 504~507, 정책문서 불일치 289·317·508, website 저장형
  XSS 509·510, "대구가 구로 끝나서 오판" 지역판정 버그클래스 511·512, 재경매 재개
  상한 513, collect_emails.py 죽은블록리스트 514, 낙찰경로 피해자안내 누락 515)와
  겹치지 않는 각도를 찾다가, addr_search.py 의 감사 이력(266·294·302·316·489)이
  전부 "예외 처리·실패 침묵·입력 길이 상한" 같은 견고성(robustness) 축이었을 뿐,
  예외 없이 **정상 실행되지만 값 자체가 틀린** 논리 결함은 한 번도 다뤄지지 않았다는
  점(294라운드는 _sigungu() 를 함수 단위로 감사해 "클린"이라고 결론지었으나, 이는
  _sigungu(sido, gu) 자신 — 두 인자를 그대로 합치는 함수 — 이 맞다는 뜻일 뿐,
  _open_map() 의 place 루프가 그 두 인자를 잘못 뽑아 넘기는지는 별개로 확인된 적이
  없었다)을 확인한 뒤, round511·512 가 이미 "짧은 지명이 다른 토큰과 우연히
  겹친다"는 클래스를 두 파일(dispatch.py·geocode_fill.py)에서 잡아낸 것과 같은
  "지역 문자열을 각 파일이 독자적으로 재구현한다"는 구조적 패턴을 addr_search.py에도
  적용해 _sigungu() 의 실제 호출부 3곳(주소 루프 1곳 + 장소 루프 1곳 + _official 1곳)을
  나란히 대조해 발견했다.

  결함 — _open_map() 의 place(장소) 루프는 place 항목에 d1_name/d2_name 같은
  구조화된 행정구역 필드가 없어(카카오가 new_address 문자열 하나만 준다),
  region 을 "공백으로 나눈 뒤 앞 두 토큰"(parts[0], parts[1])으로 고정 추출했다.
  '서울 송파구'처럼 시/도 바로 뒤에 구가 오는 2단계 도시는 맞지만, 성남·수원·
  용인·고양·안양·부천·안산·청주·전주·포항·창원처럼 '시' 아래 '구'가 하나 더
  있는 3단계 도시는 그 구가 통째로 잘린다.

  실측(라이브 카카오 무인증 엔드포인트 직접 호출, 2026-09-09) — 이 파일의 존재
  이유 그 자체인 "장소 이름으로 찾기"(주석: "○○아파트 정문·△△사거리처럼
  장소 이름으로 불리는 경우가 많아서") 질의로 재현:
    · "용인 에버랜드"  → 12건 전부 region="경기 용인시"(처인구 소실)
    · "광교호수공원"   → 12건 전부 region="경기 수원시"(영통구 소실)
    · "카카오판교아지트" → 12건 전부 region="경기 성남시"(분당구 소실)
  같은 질의의 "주소"(address) 결과 1건은 카카오 자신의 d1_name/d2_name 구조화
  필드를 쓰므로 "경기 성남시 분당구"로 정확했다 — place 루프만의 결함이다.

  영향 — 이 region 값은 addrpick.js 가 화면의 지역 입력칸(#c_region·#q_region·
  #mp_region·apply_partner.html 의 #region)에 **그대로** 채우고, 그 칸의 값이
  사건 등록(관리자 직접등록·보험사 포털)·협력사 입점신청·협력사 프로필수정
  4개 경로에서 그대로 저장된다. dispatch.py candidates() 의 _region_key() 는
  `(region or "") or (address or "")` 로 **region 을 address 보다 우선** 읽어
  자동 출동 후보의 "같은 지역"(1·2순위) 판정 열쇠로 쓴다 — 정작 같은 폼의
  주소(road) 칸에는 구가 포함된 온전한 문자열이 들어가는데도, region 칸이
  구 없이 채워지면 그 온전한 정보가 무시되고 시 전체(다른 구 포함)가
  "같은 지역"으로 뭉뚱그려진다. 동네 단위 정밀 배차라는 이 모듈 자신의 설계
  목적(주석: "거리순 배차가 '같은 구인가'보다 정밀해질 수 없었다")이 하필
  장소이름으로 찾는 대도시(성남·수원·용인 등, 인구밀집 지역이라 실제 사건도
  많다)에서만 조용히 무력화된다.

  고침 — 새 헬퍼 _admin_region(addr) 을 추가: 첫 토큰(시/도)은 그대로 두고,
  이어지는 토큰이 "시"·"군"·"구" 로 끝나는 동안 계속 담아 region 으로 합친다
  (동·읍·면 이름은 이 접미어로 안 끝나 자연스럽게 멈춘다). 2단계·3단계 주소
  양쪽을 하나의 규칙으로 다뤄 회귀 없이 3단계만 교정한다. 기존 _sigungu() 는
  구조화된 필드가 있는 주소(address) 루프·_official() 에는 그대로 남긴다
  (그 두 곳은 이미 정답이다 — round294 가 확인한 대로).

      python test_scan_round516_fixes.py
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


SRC = read("addr_search.py")

print("=" * 72)
print("  스캔 516라운드 회귀 — addr_search.py place 검색의 구(區) 소실")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk("def _admin_region(addr):" in SRC,
    "★★★★ 새 헬퍼 _admin_region() 이 생겼다")

i_om = SRC.index("def _open_map(q):")
i_om_end = SRC.index("\n\n\ndef ", i_om)
om_body = SRC[i_om:i_om_end]

i_place = om_body.index('d.get("place")')
place_body = om_body[i_place:]
chk('"region": _admin_region(addr)' in place_body,
    "★★★★★ place 루프가 이제 _admin_region(addr) 을 쓴다")
chk("parts[1] if len(parts) > 1 else" not in place_body,
    "★★★★★ place 루프에서 앞-두-토큰 고정 추출(parts[0]/parts[1])이 사라졌다")

i_addr_loop = om_body.index('d.get("address")')
addr_loop_body = om_body[i_addr_loop:i_place]
chk('_sigungu(it.get("d1_name"), it.get("d2_name"))' in addr_loop_body,
    "STEP 주소(address) 루프는 회귀 없이 구조화 필드(d1_name/d2_name)를 그대로 쓴다")

# ============================================================
print("\n[2] 실행 — _admin_region() 직접 호출(2단계·3단계·경계값)")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
import addr_search as ADDR                       # noqa: E402

_CASES = [
    ("경기 성남시 분당구 판교역로 166", "경기 성남시 분당구", "3단계(성남시+분당구) — 이 라운드의 핵심 재현"),
    ("경기 용인시 처인구 포곡읍 에버랜드로 199", "경기 용인시 처인구", "3단계 + 읍 단위까지 있는 주소"),
    ("경기 수원시 영통구 하동 1020", "경기 수원시 영통구", "3단계(수원시+영통구)"),
    ("서울 송파구 올림픽로 300", "서울 송파구", "2단계 — 회귀 없음 확인"),
    ("부산 해운대구 우동 1420", "부산 해운대구", "2단계(광역시+구) — 회귀 없음 확인"),
    ("세종특별자치시 반곡동 191", "세종특별자치시", "구가 없는 특별자치시 — 1단계에서 멈춤"),
    ("", "", "빈 문자열"),
]
for addr, want, label in _CASES:
    got = ADDR._admin_region(addr)
    chk(got == want, f"★★★ _admin_region({label}) == {want!r}", f"got={got!r}")

# ============================================================
print("\n[3] 실행 — 되돌림 증명: 옛(고치기 전) 앞-두-토큰 로직으로는 이 결함이 실제로 재현되는가")
# ------------------------------------------------------------
#  ⚠ 옛 코드를 그대로 재현해 "이 테스트가 진짜 결함을 잡아낼 능력이 있는지"를
#    증명한다(가짜 초록 방지) — round489 등 이 세션의 표준 관행과 동일한 취지.
def _old_buggy_region(addr):
    parts = (addr or "").split()
    return ADDR._sigungu(parts[0] if parts else "", parts[1] if len(parts) > 1 else "")


_old_gu_dropped = _old_buggy_region("경기 성남시 분당구 판교역로 166")
chk(_old_gu_dropped == "경기 성남시",
    "★★★★★ 옛(되돌림) 로직 — 구가 사라진 틀린 값이 실제로 재현된다(고치기 전 결함 증명)",
    _old_gu_dropped)
chk(_old_gu_dropped != ADDR._admin_region("경기 성남시 분당구 판교역로 166"),
    "★★★★★ 새 구현은 옛(되돌림) 값과 달리 구를 보존한다")

# ============================================================
print("\n[4] 실행 — _open_map() 을 실제로 돌려 place/address 두 루프를 한 응답에서 대조")
# ------------------------------------------------------------


class _FakeResp:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


_FAKE_PAYLOAD = {
    "address": [{
        "d1_name": "경기", "d2_name": "성남시 분당구", "d3_name": "백현동",
        "d3_roadname": "판교역로", "addr": "경기 성남시 분당구 판교역로 166",
        "main_bunji": "166", "sub_bunji": "0",
        "zone_no": "13529", "building_info_list": "1^카카오판교아지트",
        "lat": "37.4020", "lon": "127.1088",
    }],
    "place": [{
        "new_address": "경기 성남시 분당구 판교역로 166",
        "address": "경기 성남시 분당구 백현동 532",
        "new_zipcode": "13529", "name": "카카오판교아지트",
        "lat": "37.4020", "lon": "127.1088",
    }],
}


def _fake_urlopen(req, timeout=None):
    return _FakeResp(json.dumps(_FAKE_PAYLOAD).encode("utf-8"))


import urllib.request  # noqa: E402
_real_urlopen = urllib.request.urlopen
urllib.request.urlopen = _fake_urlopen
try:
    rows = ADDR._open_map("카카오판교아지트")
    by_road = {r["jibun"]: r for r in rows}
    addr_row = next((r for r in rows if r["road"] == "경기 성남시 분당구 판교역로 166"
                      and r["jibun"] != "경기 성남시 분당구 백현동 532"), None)
    place_row = next((r for r in rows if r["jibun"] == "경기 성남시 분당구 백현동 532"), None)

    chk(addr_row is not None and place_row is not None,
        "STEP 같은 가짜 응답에서 address·place 두 후보가 모두 만들어졌다",
        [dict(r) for r in rows])
    if addr_row is not None:
        chk(addr_row["region"] == "경기 성남시 분당구",
            "★★★ address 루프 결과 — 회귀 없이 구까지 정확하다", addr_row["region"])
    if place_row is not None:
        chk(place_row["region"] == "경기 성남시 분당구",
            "★★★★★ place 루프 결과 — 이제 구까지 정확하다(고치기 전엔 '경기 성남시'로 분당구가 사라졌다)",
            place_row["region"])
finally:
    urllib.request.urlopen = _real_urlopen

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
