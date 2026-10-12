# -*- coding: utf-8 -*-
"""주소 검색 — 자유 입력 대신 **고른 주소**를 받기 위한 조회기.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

왜 필요한가
  지금까지 사건 주소는 사람이 그대로 타이핑했다. 그래서
   · 같은 자리가 "송파구 올림픽로300", "서울 송파 올림픽로 300", "잠실 롯데타워 앞"
     으로 제각각 저장되고,
   · 좌표는 geo.py 가 **시군구 중심**으로만 잡아 줘서(지도 안내문에도 그렇게 적혀 있다)
     현장이 어디인지 지도에서 알 수 없으며,
   · 거리순 배차가 "같은 구인가"보다 정밀해질 수 없었다.
  주소를 **골라서** 넣으면 도로명·지번·우편번호·좌표가 한 번에 확정된다.

CSP 를 건드리지 않는다
  브라우저가 외부 도메인을 직접 부르면 script-src/connect-src 를 열어야 한다.
  이 모듈은 **서버가 대신 물어보고** 결과만 돌려준다. 화면은 자기 도메인만 부른다.

제공자 우선순위
  1) KAKAO_REST_KEY 가 있으면 카카오 로컬 API(공식·안정)
  2) 없으면 카카오 지도 검색의 공개 엔드포인트(무인증). 키 없이도 오늘 당장 동작한다.
     ⚠ 공식 문서가 있는 API 가 아니다 — 언제든 바뀔 수 있으므로 키를 넣는 편이 낫다.
     바뀌면 검색만 멈추고, 주소를 직접 입력하는 길은 그대로 열려 있다.
"""
import http.client
import logging
import os
import json
import urllib.parse
import urllib.request
import urllib.error

_log = logging.getLogger(__name__)

TIMEOUT = 6
UA = "Mozilla/5.0 (compatible; BokguonAddr/1.0)"
MAX_RESULTS = 12


def _key():
    return (os.environ.get("KAKAO_REST_KEY") or "").strip()


def provider():
    """지금 어떤 경로로 찾는지 — 화면에 그대로 보여 주기 위해."""
    return "카카오 로컬 API" if _key() else "카카오 지도 검색(무인증)"


def _get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _sigungu(sido, gu):
    """geo.py 가 알아듣는 지역 표기로 맞춘다(시군구 중심좌표 매칭에 쓰인다)."""
    return " ".join(x for x in ((sido or "").strip(), (gu or "").strip()) if x)


def _admin_region(addr):
    """주소 문자열 맨 앞의 행정구역만 뽑는다.

    ⚠⚠ [라운드516] _open_map() 의 place(장소) 결과는 d1_name/d2_name 같은
      구조화된 필드가 없어(카카오가 문자열 주소 하나만 준다) 예전엔 앞 두
      토큰(parts[0], parts[1])을 그대로 썼다 — '서울 송파구'처럼 시/도 뒤에
      구가 바로 오는 2단계는 맞지만, 성남·수원·용인·고양·안양·부천·안산·
      청주·전주·포항·창원처럼 '시' 아래 '구'가 또 있는 3단계 도시는 그
      구가 통째로 잘렸다(실측, 실제 카카오 응답: '경기 성남시 분당구
      판교역로 166' → 예전 값 '경기 성남시', '분당구'가 사라짐 — '용인
      에버랜드'·'광교호수공원' 등 이 파일 자신의 존재 이유인 장소이름
      검색으로 재현). 이 region 값은 addrpick.js 가 화면 지역 칸에 그대로
      채우고(#c_region 등), dispatch.py _region_key() 가 그 칸을 주소보다
      **우선** 읽어 자동 출동 후보의 '같은 지역' 판정 열쇠로 쓴다 — 구가
      빠지면 실제로는 시 전체(다른 구 포함)가 '같은 지역'으로 뭉뚱그려져
      동네 단위 정밀 배차라는 이 파일의 목적이 하필 장소이름 검색에서만
      무력화된다. 시/군/구로 끝나는 토큰을 계속 이어붙이면 2단계·3단계
      양쪽 다 자연스럽게 맞는다(동·읍·면 이름은 이 접미어로 안 끝나
      여기서 멈춘다).
    """
    parts = (addr or "").split()
    if not parts:
        return ""
    admin = parts[:1]
    for p in parts[1:]:
        if not p.endswith(("시", "군", "구")):
            break
        admin.append(p)
    return " ".join(admin)


def _official(q):
    """카카오 로컬 API — REST 키가 있을 때."""
    url = ("https://dapi.kakao.com/v2/local/search/address.json?size=%d&query=%s"
           % (MAX_RESULTS, urllib.parse.quote(q)))
    d = _get(url, {"Authorization": "KakaoAK " + _key()})
    out = []
    for it in d.get("documents") or []:
        try:
            road = it.get("road_address") or {}
            jib = it.get("address") or {}
            out.append({
                "road": road.get("address_name") or "",
                "jibun": jib.get("address_name") or it.get("address_name") or "",
                "zipcode": road.get("zone_no") or "",
                "building": road.get("building_name") or "",
                "region": _sigungu(jib.get("region_1depth_name") or road.get("region_1depth_name"),
                                   jib.get("region_2depth_name") or road.get("region_2depth_name")),
                "lat": float(it["y"]) if it.get("y") else None,
                "lng": float(it["x"]) if it.get("x") else None,
            })
        except (ValueError, TypeError, AttributeError) as e:
            #  ⚠ [라운드266] 후보 하나가 이상해도(예: 좌표가 숫자가 아님) 이 자리에서
            #    막아야 한다 — 밖으로 새면 search() 의 광범위 except 가 통째로 빈
            #    목록으로 되돌려, 같은 응답에 있던 멀쩡한 후보들까지 함께 사라진다.
            _log.warning("주소검색 후보 1건 파싱 실패 — 건너뜀 (%s: %s)", type(e).__name__, e)
    return out


def _open_map(q):
    """카카오 지도 검색 공개 엔드포인트 — 키가 없을 때.

    주소(address)와 장소(place)를 둘 다 받는다. 현장은 "○○아파트 정문",
    "△△사거리"처럼 **장소 이름으로 불리는 경우가 많아서**, 장소도 주소로 바꿔 준다.
    """
    url = ("https://search.map.kakao.com/mapsearch/map.daum?callback=&msFlag=A&sort=0&q="
           + urllib.parse.quote(q))
    d = _get(url, {"Referer": "https://map.kakao.com/"})
    out = []
    for it in (d.get("address") or [])[:MAX_RESULTS]:
        try:
            road_name = (it.get("d3_roadname") or "").strip()
            prefix = " ".join(x for x in ((it.get("d1_name") or ""), (it.get("d2_name") or "")) if x)
            #  번지가 없는 결과(동 단위 검색 등)에 "0"이 붙어 "우동 0" 같은 가짜 지번이 됐다
            bunji = str(it.get("main_bunji") or "").strip()
            sub = str(it.get("sub_bunji") or "").strip()
            if bunji in ("", "0"):
                num = ""
            else:
                num = bunji + ("-" + sub if sub and sub != "0" else "")
            jibun = " ".join(x for x in (prefix, (it.get("d3_bname") or ""), num) if x).strip()
            out.append({
                "road": (it.get("addr") or "").strip(),
                "jibun": jibun,
                "zipcode": (it.get("zone_no") or "").strip(),
                "building": _building_of(it),
                "region": _sigungu(it.get("d1_name"), it.get("d2_name")),
                "lat": float(it["lat"]) if it.get("lat") else None,
                "lng": float(it["lon"]) if it.get("lon") else None,
                "_road_only": bool(road_name),
            })
        except (ValueError, TypeError, AttributeError) as e:
            #  ⚠ [라운드266] _official() 과 같은 이유 — 후보 1건의 결함이
            #    같은 응답의 다른 멀쩡한 후보까지 끌고 사라지면 안 된다.
            _log.warning("주소검색 후보 1건 파싱 실패 — 건너뜀 (%s: %s)", type(e).__name__, e)
    for it in (d.get("place") or [])[:MAX_RESULTS]:
        try:
            addr = (it.get("new_address") or it.get("address") or "").strip()
            if not addr:
                continue
            out.append({
                "road": addr,
                "jibun": (it.get("address") or "").strip(),
                #  ⚠ 좌표 키가 lat/**lon** 이다(lng 이 아니다). lng 으로 읽어 전부 None 이 됐고,
                #    좌표 없는 주소는 지도에도 못 찍히고 거리 계산에도 못 쓴다.
                "zipcode": (it.get("new_zipcode") or "").strip(),
                "building": (it.get("name") or "").strip(),
                "region": _admin_region(addr),
                "lat": float(it["lat"]) if it.get("lat") else None,
                "lng": float(it["lon"]) if it.get("lon") else None,
            })
        except (ValueError, TypeError, AttributeError) as e:
            _log.warning("주소검색 후보 1건 파싱 실패 — 건너뜀 (%s: %s)", type(e).__name__, e)
    return out


def _building_of(it):
    """건물명 — 있으면 골랐을 때 사람이 알아보기 쉽다."""
    raw = (it.get("building_info_list") or "").split("^")
    return raw[1].strip() if len(raw) > 1 else ""


def search(q):
    """주소 문자열 → 후보 목록. 실패하면 빈 목록(화면은 직접 입력으로 넘어간다).

    돌려주는 항목: road, jibun, zipcode, building, region, lat, lng
    """
    q = (q or "").strip()
    #  ⚠⚠ [라운드489] 하한(2자)만 있고 상한이 없어, 로그인한 저신뢰 계정(협력사)이
    #    수만 자를 보내면 그대로 urllib.parse.quote() 를 거쳐 외부(_open_map, 비공식
    #    무인증 엔드포인트)로 그 크기 그대로 전달됐다(실측: 한글 5만자 → 450,076바이트
    #    URL). 같은 성격의 자유입력(주소)은 이미 FIELD_LIMITS["address"]·_create_case()
    #    양쪽 모두 200자로 자르는 관례가 있다 — 이 함수가 실시간 라우트와
    #    geocode_fill.py 배치 양쪽의 유일한 공용 관문이므로 여기 한 곳만 맞추면 된다.
    if len(q) < 2 or len(q) > 200:
        return []
    try:
        rows = _official(q) if _key() else _open_map(q)
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError, AttributeError,
            http.client.HTTPException) as e:
        #  ⚠⚠ [라운드266] 예전엔 여기서 전부 조용히 빈 목록으로 삼켰다 — "주소가
        #    진짜 없음"과 "카카오 쪽이 429·타임아웃 등으로 막힘"이 호출부
        #    (geocode_fill.py 배치·app.py 실시간 검색 둘 다) 입장에서 완전히 똑같이
        #    보였다. 형제(crypto_util.decrypt, 라운드120)처럼 반환값(빈 목록)은
        #    그대로 두되(호출부를 안 건드린다) 실패했다는 사실만 로그에 남긴다.
        #    AttributeError 는 응답이 아예 dict 모양이 아닐 때(d.get 실패) 필요.
        #  ⚠⚠ [라운드294] http.client.HTTPException 이 빠져 있었다 — 이 파일이
        #    쓰는 무인증 엔드포인트(_open_map, 이 파일 자신의 docstring이 "언제든
        #    바뀔 수 있다"고 경고하는 그 API)가 Content-Length 보다 적게 보내고
        #    연결을 끊으면 _get() 의 r.read() 가 IncompleteRead 를 낸다 — 이건
        #    HTTPException 의 하위클래스라 OSError 계열이 아니어서 위 튜플 어디에도
        #    안 걸린다(실측: 가짜 TCP 서버로 재현, MRO 로 확인). "실패하면 빈
        #    목록"이라는 이 함수 자신의 계약을 깨고 그대로 새 나가 geocode_fill.py
        #    의 무방비 배치 루프(rows_to_fill 이후 for 문, UPDATE/commit 만
        #    267라운드가 감쌌지 이 검색 호출 자체는 안 감쌌다)를 통째로 죽였을
        #    것이다.
        _log.warning("주소검색 실패 — 빈 목록으로 대체 (%s: %s)", type(e).__name__, e)
        return []
    seen, out = set(), []
    for r in rows:
        r.pop("_road_only", None)
        if not (r.get("road") or r.get("jibun")):
            continue
        k = (r.get("road"), r.get("jibun"), r.get("building"))
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
        if len(out) >= MAX_RESULTS:
            break
    return out


def demo():
    """python addr_search.py — 실제로 찾아지는지 한 번에 확인."""
    for q in ("송파구 올림픽로 300", "부산 해운대구 우동", "없는주소zzz9999"):
        rows = search(q)
        print(f"\n[{q}] {len(rows)}건  ({provider()})")
        for r in rows[:3]:
            print("   ", r["road"], "|", r["jibun"], "|", r["zipcode"],
                  "|", r["region"], "|", r["lat"], r["lng"])
    ok = search("송파구 올림픽로 300")
    assert ok, "주소 검색이 한 건도 못 찾았습니다"
    assert ok[0]["lat"] and ok[0]["lng"], "좌표가 비었습니다"
    assert ok[0]["region"].startswith("서울"), ok[0]["region"]
    assert search("z") == [], "너무 짧은 검색어는 빈 목록이어야 합니다"
    #  ★ 좌표 없는 후보가 섞이면 지도에 못 찍히고 거리 배차에도 못 쓴다
    blind = [r for r in ok if not (r["lat"] and r["lng"])]
    assert not blind, f"좌표 없는 후보 {len(blind)}건: {blind[:1]}"
    #  ★ 번지가 없는데 '0' 이 붙은 가짜 지번이 나오면 안 된다
    dong = search("부산 해운대구 우동")
    assert not [r for r in dong if r["jibun"].endswith(" 0")], "가짜 지번 '0' 이 남았습니다"
    print("\n자체 점검 통과")


if __name__ == "__main__":
    demo()
