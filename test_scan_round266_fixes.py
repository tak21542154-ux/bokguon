# -*- coding: utf-8 -*-
"""스캔 266라운드 회귀 — 주소검색(addr_search.py) 결함 2건
   (geocode_fill.py 감사 라운드265가 남긴 미검증 관찰의 정밀조사 Agent가 발견,
   독립 재검증 후 수정).

  [1] search() 의 광범위 except 가 아무 로그도 없이 빈 목록으로 삼켰다.
      실행으로 확인: HTTP 429·500·타임아웃·깨진JSON 을 각각 주입해도
      "진짜로 검색결과가 없음"과 완전히 똑같은 값([])·완전히 똑같은
      침묵(로그 0바이트)이 나왔다 — 호출부(geocode_fill.py 배치 집계,
      app.py:17133 의 실시간 /api/address/search 라우트 둘 다) 입장에서
      "이 주소는 없다"와 "카카오 쪽이 막혔다"를 원리적으로 구분할 수
      없었다. 형제(crypto_util.decrypt, 라운드120)처럼 반환값은 그대로
      두고(호출부를 안 건드린다) 실패 사실만 로그에 남긴다. 응답이 아예
      dict 모양이 아닐 때(d.get 이 AttributeError)도 이 자리에서 잡아야
      해서 except 튜플에 AttributeError 를 추가했다.

  [2] 후보 목록을 만드는 for 문 안에서 후보 1건이 파싱에 실패하면
      (좌표가 숫자가 아님 등) 그 예외가 함수 밖으로 새 나가 search() 의
      광범위 except 에 잡히면서 **같은 응답에 있던 멀쩡한 후보들까지
      통째로 사라졌다**(실행으로 확인: 정상 2건+불량 1건을 섞으면 0건
      반환). _official() 1곳 + _open_map() 의 address·place 두 루프,
      총 3곳이 같은 구조였다 — 각각 후보 단위로 try/except 를 둘러
      불량 후보 1건만 건너뛰게 했다.

      python test_scan_round266_fixes.py
"""
import io
import json
import logging
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


SRC = read("addr_search.py")

print("=" * 72)
print("  스캔 266라운드 회귀 — addr_search.py 실패침묵·후보1건 전체오염")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk("_log = logging.getLogger(__name__)" in SRC,
    "★★★★ 모듈 로거가 생겼다(형제 crypto_util.py 와 같은 관용구)")

i_search = SRC.index("def search(q):")
i_search_end = SRC.index("\n\n\ndef ", i_search)
search_body = SRC[i_search:i_search_end]
#  ⚠ [라운드294] "AttributeError) as e:" 로 끝자리 고정 검사였다 — 294라운드가
#    같은 except 튜플 끝에 http.client.HTTPException 을 하나 더 추가하면서
#    AttributeError 가 더는 튜플의 마지막 항목이 아니게 됐다. 순서가 아니라
#    "AttributeError 가 이 except 튜플 안에 들어있는가"만 본다.
_except_i = search_body.index("except (")
_except_end = search_body.index(") as e:", _except_i)
_except_tuple_src = search_body[_except_i:_except_end]
chk("AttributeError" in _except_tuple_src,
    "★★★★★ 바깥쪽 except 가 AttributeError 도 잡는다(응답이 dict 모양이 아닐 때)")
chk('_log.warning("주소검색 실패' in search_body,
    "★★★★★ 바깥쪽 except 가 실패 사실을 로그에 남긴다(예전엔 완전 침묵)")

i_off = SRC.index("def _official(q):")
i_off_end = SRC.index("\n\n\ndef ", i_off)
off_body = SRC[i_off:i_off_end]
chk(off_body.count("try:") == 1 and "주소검색 후보 1건 파싱 실패" in off_body,
    "★★★★ _official() 의 후보 조립이 후보 단위 try/except 로 감싸졌다")

i_om = SRC.index("def _open_map(q):")
i_om_end = SRC.index("\n\n\ndef ", i_om)
om_body = SRC[i_om:i_om_end]
chk(om_body.count("try:") == 2 and om_body.count("주소검색 후보 1건 파싱 실패") == 2,
    "★★★★ _open_map() 의 address·place 두 루프 모두 후보 단위로 감싸졌다")

# ============================================================
print("\n[2] 실행 준비 — urlopen 몽키패치 + 로그 캡처")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
os.environ.pop("KAKAO_REST_KEY", None)          # 실운영과 동일: 무인증 경로
import addr_search as ADDR                       # noqa: E402


class _FakeResp:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


_next = {"kind": "json", "value": {}}


def _fake_urlopen(req, timeout=None):
    kind, value = _next["kind"], _next["value"]
    if kind == "raise":
        raise value
    return _FakeResp(json.dumps(value).encode("utf-8"))


urllib.request.urlopen = _fake_urlopen


def set_json(v):
    _next["kind"], _next["value"] = "json", v


def set_raise(exc):
    _next["kind"], _next["value"] = "raise", exc


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(self.format(record))


cap = _Capture()
_addr_logger = logging.getLogger("addr_search")
_addr_logger.setLevel(logging.DEBUG)
_addr_logger.addHandler(cap)

# ============================================================
print("\n[3] 실행 — '진짜 못찾음' vs 'API 실패', 반환값은 같아도 로그로 구분되는지")
# ------------------------------------------------------------
try:
    cap.records.clear()
    set_json({"address": [], "place": []})
    r_empty = ADDR.search("존재하지않는주소이름 zzz9999")
    chk(r_empty == [], "STEP 진짜 못찾음 — 빈 목록 반환(기준선)")
    chk(cap.records == [], "★★★★ 진짜 못찾음일 때는 경고 로그가 없다(정상 상황이라 조용해야 정상)",
        cap.records)

    cap.records.clear()
    set_raise(urllib.error.HTTPError("http://x", 429, "Too Many Requests", {}, None))
    r_429 = ADDR.search("서울 송파구 올림픽로 300")
    chk(r_429 == [], "STEP HTTP 429 — 반환값은 위 '진짜 못찾음'과 완전히 동일하다([])")
    chk(any("주소검색 실패" in rec and "HTTPError" in rec for rec in cap.records),
        "★★★★★ 그러나 429는 경고 로그를 남긴다 — 반환값이 같아도 로그로 원인을 구분할 수 있다"
        "(고치기 전엔 이 경우도 로그 0건이라 둘을 원리적으로 구분할 방법이 없었다)",
        cap.records)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드266 [3] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[4] 실행 — 응답이 dict 모양이 아니면(바깥쪽 AttributeError) 크래시 대신 안전 반환")
# ------------------------------------------------------------
try:
    cap.records.clear()
    set_json([])                      # 최상위가 dict 가 아니라 리스트 — d.get() 이 없다
    r_shape = ADDR.search("아무 주소")
    chk(r_shape == [], "★★★★★ 응답이 dict 모양이 아니어도 크래시하지 않고 빈 목록을 돌려준다"
        "(고치기 전엔 AttributeError 가 밖으로 새 search() 호출부가 그대로 죽었다)")
    chk(any("AttributeError" in rec for rec in cap.records),
        "STEP 이 경우도 경고 로그에 정확한 예외종류(AttributeError)가 남는다", cap.records)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드266 [4] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 실행 — 후보 1건 결함이 같은 응답의 나머지 후보까지 끌고 사라지는가(3곳)")
# ------------------------------------------------------------
try:
    #  5a) _official() 직접 호출 — 정상 2건 + 좌표가 숫자가 아닌 1건
    cap.records.clear()
    docs = [
        {"road_address": {"address_name": "서울 송파구 올림픽로 300"},
         "address": {"address_name": "서울 송파구 신천동 300"},
         "y": "37.51", "x": "127.10"},
        {"road_address": {"address_name": "서울 강남구 테헤란로 999"},
         "address": {"address_name": "서울 강남구 역삼동 999"},
         "y": "NOT-A-NUMBER", "x": "127.05"},          # 불량 후보
        {"road_address": {"address_name": "부산 해운대구 우동 1"},
         "address": {"address_name": "부산 해운대구 우동 1"},
         "y": "35.16", "x": "129.16"},
    ]
    set_json({"documents": docs})
    r_off = ADDR._official("아무 주소")
    chk(len(r_off) == 2,
        "★★★★★ _official() — 불량 후보 1건은 건너뛰고 나머지 2건은 살아남는다"
        "(고치기 전엔 0건 — 멀쩡한 후보까지 통째로 사라졌다)",
        [d["road"] for d in r_off])
    chk(any("후보 1건 파싱 실패" in rec for rec in cap.records),
        "STEP _official() 도 건너뛴 후보를 경고 로그로 남긴다", cap.records)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드266 [5a] 준비/실행", f"{type(e).__name__} {e}")

try:
    #  5b) _open_map() address 루프 — 정상 2건 + 좌표가 숫자가 아닌 1건
    cap.records.clear()
    addr_items = [
        {"d1_name": "서울", "d2_name": "송파구", "d3_bname": "신천동",
         "addr": "서울 송파구 올림픽로 300", "lat": "37.51", "lon": "127.10"},
        {"d1_name": "서울", "d2_name": "강남구", "d3_bname": "역삼동",
         "addr": "서울 강남구 테헤란로 999", "lat": "BROKEN", "lon": "127.05"},
        {"d1_name": "부산", "d2_name": "해운대구", "d3_bname": "우동",
         "addr": "부산 해운대구 우동", "lat": "35.16", "lon": "129.16"},
    ]
    set_json({"address": addr_items, "place": []})
    r_om_a = ADDR._open_map("아무 주소")
    chk(len(r_om_a) == 2,
        "★★★★★ _open_map() address 루프 — 불량 후보 1건은 건너뛰고 2건 살아남는다"
        "(고치기 전엔 0건)",
        [d["road"] for d in r_om_a])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드266 [5b] 준비/실행", f"{type(e).__name__} {e}")

try:
    #  5c) _open_map() place 루프 — 정상 2건 + dict 가 아닌 항목 1건(AttributeError 유발)
    cap.records.clear()
    place_items = [
        {"new_address": "서울 송파구 올림픽로 300", "name": "롯데타워", "lat": "37.51", "lon": "127.10"},
        "이건 dict 가 아니라 문자열이다 — .get() 이 없다",     # 불량 후보(형태 이상)
        {"new_address": "부산 해운대구 우동", "name": "센텀시티", "lat": "35.16", "lon": "129.16"},
    ]
    set_json({"address": [], "place": place_items})
    r_om_p = ADDR._open_map("아무 주소")
    chk(len(r_om_p) == 2,
        "★★★★★ _open_map() place 루프 — dict 가 아닌 불량 항목 1건은 건너뛰고 2건 살아남는다"
        "(고치기 전엔 AttributeError 가 그대로 새서 함수 전체가 죽었다)",
        [d["road"] for d in r_om_p])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드266 [5c] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
