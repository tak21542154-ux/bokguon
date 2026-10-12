# -*- coding: utf-8 -*-
"""등록된 주소를 좌표로 채운다 — 거리순 배차가 진짜 거리를 쓰게 만드는 일회성 정비.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

■ 왜 필요한가
  협력사에는 좌표 칸이 없었다. 그래서 '가까운 순'은 시군구 중심좌표 + 업체번호 해시로
  만든 가짜 좌표를 잰 값이었다. 실데이터에서 활성 399곳이 서로 다른 **140개 점**에
  뭉쳐 있었으니, 같은 구 안에서의 순서는 사실상 sha256 순서였다.
  주소를 좌표로 한 번 훑어 두면 그날부터 거리는 거리다.

■ 안전 원칙
  · **주소는 건드리지 않는다.** 좌표(lat/lng/geo_src)만 채운다.
  · 이미 좌표가 있는 곳은 **건너뛴다**(사람이 손으로 잡아 둔 값이 우선).
  · 검색 결과가 **주소와 다른 시군구**를 가리키면 채우지 않는다 —
    엉뚱한 좌표는 없느니만 못하다(배차가 조용히 틀린 업체를 부른다).
  · 먼저 `--dry` 로 무엇이 바뀔지 보고, 그다음에 실행한다.

■ 쓰는 법
    python geocode_fill.py --dry              # 무엇이 바뀔지만 본다
    python geocode_fill.py                    # 협력사 좌표 채우기
    python geocode_fill.py --target cases     # 사건도 채우기
    python geocode_fill.py --limit 50         # 조금씩 나눠서
"""
import os
import re
import sys
import time
import argparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("BOKGUON_LOG_FILE",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "logs", "geocode_fill.log"))
import db as DB
import addr_search as ADDR

PAUSE = 0.35          # 조회 사이 간격 — 상대 서버를 몰아치지 않는다

#  ⚠ 좌표가 한반도 밖이면 없느니만 못하다 — 수동 좌표 입력(app.py _picked_coords)과
#    **같은 판정**을 여기서도 쓴다. 안 그러면 검색 API 가 드물게 내는 이상값이
#    그대로 저장되고, 그 업체가 "여의도 앞바다"에 있는 것처럼 거리 계산에 잡혀
#    엉뚱하게 최우선 후보가 될 수 있다(실측: 현재 데이터엔 없지만 방어선이 없었다).
_KOREA_LAT = (33.0, 39.5)
_KOREA_LNG = (124.0, 132.0)


def _in_korea(lat, lng):
    return _KOREA_LAT[0] <= lat <= _KOREA_LAT[1] and _KOREA_LNG[0] <= lng <= _KOREA_LNG[1]
#  ⚠⚠ [라운드650] 시도 이름을 **경계 없이** 부분일치로 찾았다 — '세종로'·'세종대로'
#    (서울 도로명, 세종로는 광화문 앞, 세종대로는 서울시청 앞) 안의 '세종'이 그대로
#    잡혀 '세종특별자치시'와 같은 시도로 오판됐다. 실측: 구/시/군을 못 뽑는 쪽이
#    하나라도 있으면(_region_ok 맨 아래 "시군구를 못 뽑으면 시도라도 맞아야 한다"
#    분기 — 세종시는 애초에 '구' 자체가 없는 특별자치시라 항상 이 분기를 탄다)
#    _region_ok("서울 중구 세종대로 110", "세종특별자치시 반곡동 108") 이 True 로
#    나왔다(약 120km 떨어진 완전히 다른 도시인데도). 이 함수 자신의 존재 이유인
#    모듈 docstring의 "엉뚱한 좌표는 없느니만 못하다"를 정면으로 벗어난다.
#    이름 뒤에 공백/문자열 끝이거나 실제 행정단위 접미('시'·'도'·'특별'·'광역'·
#    '통합') 또는 또 다른 시도 이름('전남광주통합…' 같은 결합 표기 지원, 아래
#    _sido_set docstring 참고)이 이어질 때만 인정한다 — '세종대로'의 '대',
#    '경기장길'의 '장'은 이 목록 어디에도 없어 더 이상 안 잡힌다.
_SIDO = re.compile(r"(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|"
                   r"전북|전남|경북|경남|제주)"
                   r"(?=$|[^가-힣]|시|도|특별|광역|통합|"
                   r"서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|"
                   r"전북|전남|경북|경남|제주)")


def _region_ok(want, got):
    """검색 결과가 등록 주소와 **같은 동네**인가.

    시군구 이름이 하나라도 겹치면 통과로 본다. 시도만 같고 시군구가 다르면
    (예: '서울 송파' 로 등록됐는데 '서울 강남' 이 잡힘) 채우지 않는다.
    """
    w, g = _gu_set(want), _gu_set(got)
    if w and g:
        if w & g:
            #  ⚠⚠ [라운드649] 구 이름만 겹치면 시도는 안 보고 곧장 통과시켰다 —
            #    '중구·동구·서구·남구·북구' 는 서울·부산·대구·인천·광주·대전·울산이
            #    나눠 쓰는 흔한 이름이라(예: 서울 중구 ≠ 부산 중구), 구 이름이
            #    같아도 시도가 서로 다르면 실제로는 완전히 다른 도시다(실측:
            #    이 지름길만 있던 상태에서 _region_ok("서울 중구 세종대로 110",
            #    "부산 중구 대청로 33") 등 4개 광역시 조합이 전부 True로 나왔다
            #    — 이 함수 자신의 존재 이유, 모듈 docstring의 "엉뚱한 좌표는
            #    없느니만 못하다"를 정면으로 벗어난다). 시도 정보가 양쪽 다 있고
            #    서로 겹치지 않을 때만 이 지름길을 막는다 — 한쪽만 시도 정보가
            #    없는 경우(정보 비대칭)는 round159와 같은 원칙으로 그대로 통과시킨다.
            sw, sg = _sido_set(want), _sido_set(got)
            if sw and sg and not (sw & sg):
                return False
            return True
        #  ⚠ 검색 쪽이 '전남광주통합특별시 북구' 처럼 **통합 행정구역 이름**을 줄 때가 있다.
        #    등록은 그냥 '광주 북구' 라서 토큰이 안 겹치는데, 실제로는 같은 곳이다.
        #    (실데이터에서 광주 업체 14곳이 이 이유로 통째로 걸렀다)
        #    시도 이름이 하나라도 겹치고 구 이름이 같으면 같은 곳으로 본다.
        if _sido_set(want) & _sido_set(got):
            wg = {x for x in w if x.endswith("구")}
            gg = {x for x in g if x.endswith("구")}
            #  ⚠⚠ [라운드159] `not (wg and gg)` 는 "둘 다 구 정보가 없을 때"도
            #    통과시켰다 — '광역시 이름'처럼 한쪽만 구 정보가 없는 통합표기
            #    구제와, '김해시' vs '진주시'처럼 애초에 구가 없는 시/군끼리
            #    이름 자체가 다른 경우를 구분하지 못했다(전국 대부분의 시·군이
            #    이 경로로 새어나가 "같은 도(道)면 무조건 같은 동네"가 됐다).
            #    한쪽만 구 정보가 있을 때(정보 비대칭)만 구제한다.
            return bool(wg & gg) or (bool(wg) != bool(gg))
        return False
    # 시군구를 못 뽑으면 시도라도 맞아야 한다
    return bool(_sido_set(want) & _sido_set(got))


def _sido_set(s):
    """문자열 안의 **모든** 시도 이름. 통합 표기('전남광주통합…')는 둘 다 잡힌다.

    앞에서 하나만 찾으면 '전남광주…' 에서 '전남'만 잡혀 '광주'와 못 만난다.

    ⚠⚠ [라운드653] _SIDO 정규식은 축약형(전남·전북·충남·충북·경남·경북)만 담는다 —
      이 여섯 도는 '전라남도'처럼 **정식 명칭**으로도 흔히 적힌다(사업자등록증·
      보험사 주소 DB 등에서 실제로 쓰는 표기). db.REGION_LONG(정확히 이 문제를
      풀려고 이미 있는 표 — 이 파일은 순환임포트 걱정 없이 db 를 이미 import
      하고 있다, _gu_set() 의 DB.SIDO 참고)으로 먼저 축약하지 않으면, 정식
      명칭 쪽은 시도가 빈 집합으로 나와 바로 위 _region_ok() 의 "구 이름이
      같아도 시도가 다르면 다른 동네"([라운드649]) 검사가 그냥 건너뛰어진다.
      실측: _region_ok("경상북도 포항시 남구 대잠동", "부산광역시 남구 대연동")
      이 True 였다 — 100km 넘게 떨어진 두 도시(포항·부산)가 같은 '남구'라는
      이유만으로 같은 동네로 통과했다(둘 다 광역시가 아니라 남구를 쓰는 흔한
      이름이라 실제로 부딪힌다). 정식 명칭을 먼저 축약형으로 바꾼 뒤 기존
      정규식은 그대로 쓴다 — 이미 축약형인 문자열은 REGION_LONG 의 어느 long_
      과도 안 겹쳐(부분일치 없음, 직접 대조 확인) 회귀 없이 그대로 통과한다.
    """
    s = s or ""
    for long_, short in DB.REGION_LONG:
        if long_ in s:
            s = s.replace(long_, short)
    return set(_SIDO.findall(s))


_ADDR_LABEL = re.compile(r"^\s*(본사|본점|주소|소재지|사무실|공장|지사|사업장)\s*[:：]\s*")
_SIDO_HEAD = re.compile(r"(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충청?[북남]|"
                        r"전라?[북남]|경상?[북남]|제주)")


def _first_address(raw):
    """여러 주소·설명이 섞인 칸에서 **첫 번째 실제 주소**만 추린다.

    실데이터에 이런 것들이 들어 있다 —
      "본사: 부산 사하구 동매로 120 한신혜성상가 203호 / 공장: …"
      "경남 김해시 한림면 용덕로302번길 102 / 경남 김해시 한림면 …"
      "페이지에 본사 주소 미표기 (서울사업본부 등 9개 사업본부만 …"
    그대로 검색하면 통째로 실패한다. 구분자에서 자르고 라벨을 떼고,
    시도 이름이 처음 나오는 자리부터를 주소로 본다.
    """
    s = (raw or "").strip()
    if not s:
        return ""
    s = re.split(r"\s*[/·|]\s*|\s{2,}", s)[0]        # 첫 덩어리만
    s = _ADDR_LABEL.sub("", s)                        # '본사:' 같은 라벨 제거
    m = _SIDO_HEAD.search(s)
    if m:
        s = s[m.start():]
    s = re.sub(r"\([^)]*\)", " ", s)                  # 괄호 주석 제거
    s = re.sub(r"\s+", " ", s).strip()
    #  '…호', '…층' 같은 상세는 검색을 방해할 때가 많다 — 도로명+건물번호까지만 남긴다
    m2 = re.search(r"^(.*?\d+(?:-\d+)?)\s", s + " ")
    return (m2.group(1) if m2 else s)[:80]


def _gu_set(s):
    """문자열 안의 시·군·구 이름.

    ⚠ '북구·서구·남구·동구·중구' 는 **두 글자**다. 최소 3글자를 요구하면
      광역시 구 상당수가 통째로 안 잡혀, 서로 다른 구를 같은 곳으로 통과시킨다
      (자체 점검이 '광주 북구' vs '…서구' 를 잡아냈다).
      괄호·기호는 공백으로 바꾼 뒤, **낱말 앞이 공백인 것**만 센다
      ('올림픽로' 안의 '픽로구' 같은 조각을 배제).

    ⚠⚠ [라운드512] '대구'는 시/도 이름 자체가 우연히 '구'로 끝난다 — dispatch.py
      _region_key() 가 라운드511에서 고친 것과 정확히 같은 함정인데, 이 함수는
      그 교훈을 못 물려받은 별개의 재구현이었다(geocode_fill.py 는 geo.py 도
      dispatch.py 도 import 하지 않는 독자 모듈). 등록 지역이 '대구'(광역시명뿐,
      구 정보 없음)인 협력사·사건은 이 정규식이 '대구' 자신을 구 단위 지명으로
      오판해 결과 집합에 넣는다 — 그러면 _region_ok() 의 "구 정보가 없으면
      시도로 판정한다"는 자신의 원칙(위 데모의 '서울'→'서울 송파구' 사례가 이미
      보장하는 그 폴백)이 막혀, 실제로는 같은 도시인 검색 결과(예: '대구광역시
      동구')까지 서로 다른 구('대구' vs '동구')로 보고 '동네 불일치'로 걸러
      좌표를 영영 못 채운다(geo_src='시도실패' 로 재시도도 막힘). 실측:
      _region_ok("대구","대구광역시 동구") == False(대구·경북 지사를 둔 업체처럼
      주소가 도로명만 적고 구를 반복하지 않으면 이 경로를 탄다 — 현재 이
      저장소의 기존 데이터는 주소에 '대구광역시'가 함께 적혀 있어 우연히
      피해 갔을 뿐, 그 중복이 없으면 바로 재현된다). db.SIDO(dispatch.py
      511라운드가 쓴 것과 같은 기존 상수, 이 파일이 이미 DB 로 참조한다)에
      있는 토큰은 제외한다 — '대구' 외 16개 시/도는 원래 구/시/군으로 안
      끝나 이 제외가 없어도 안전했으므로 회귀 없이 '대구' 한 곳만 고쳐진다.
    """
    t = " " + re.sub(r"[^가-힣]+", " ", s or "")
    return {x for x in re.findall(r"(?<=\s)([가-힣]{1,5}[시군구])", t) if x not in DB.SIDO}


#  ⚠⚠ [라운드302] 좌표가 못 채워진 이유(주소가 애초에 안 잡힘·한반도 밖·동네
#    불일치)를 어디에도 안 남겨, "아직 안 해 봄"과 "해 봤는데 안 됨"이 lat
#    IS NULL 하나로 구별이 안 됐다. cases 는 계속 새로 쌓이는 표라 이 도구가
#    반복 실행될 수 있는데(--limit 기본 500), 실측: 낮은 id 쪽에 영구히
#    못 찾는 주소가 --limit 이상 쌓이면 매 실행이 그 오래된 실패건만 다시
#    뽑아 정작 새로 생긴 사건은 한 번도 시도조차 못 받는다. 시도해서 못
#    채운 행은 geo_src 에 이 표식을 남겨 다음 실행이 건너뛰게 한다(그래도
#    사람이 필요하면 그 행의 geo_src 를 손으로 지워 다시 대상에 넣을 수
#    있다 — 영구 봉인은 아니다).
FAILED_SRC = "시도실패"


def rows_to_fill(conn, table, limit):
    return conn.execute(
        f"""SELECT id, name, region, address FROM {table}
             WHERE (lat IS NULL OR lng IS NULL)
               AND TRIM(COALESCE(address,'')) <> ''
               AND COALESCE(geo_src,'') <> ?
             ORDER BY id LIMIT ?""", (FAILED_SRC, limit)).fetchall() if table == "partners" else \
        conn.execute(
        f"""SELECT id, case_no AS name, region, address FROM {table}
             WHERE (lat IS NULL OR lng IS NULL)
               AND TRIM(COALESCE(address,'')) <> ''
               AND COALESCE(is_demo,0)=0
               AND COALESCE(geo_src,'') <> ?
             ORDER BY id DESC LIMIT ?""", (FAILED_SRC, limit)).fetchall()


def fill(table, limit, dry):
    conn = DB.get_db()
    rows = rows_to_fill(conn, table, limit)
    print(f"\n[{table}] 좌표 없는 행 {len(rows)}건 (주소가 있는 것만)")
    print(f"  검색 경로: {ADDR.provider()}")
    def _mark_failed(row_id):
        #  ⚠ dry 에선 아무것도 남기지 않는다(이 함수 자체를 dry 일 때 안 부른다).
        conn.execute(f"UPDATE {table} SET geo_src=? WHERE id=?", (FAILED_SRC, row_id))
        conn.commit()

    done = skip_far = skip_none = skip_bad = skip_err = skip_search_err = 0
    for r in rows:
        q = (r["address"] or "").strip()
        used_q = q
        #  ⚠⚠ [라운드302] 이 검색 두 번(원문·정제문) 이 이제껏 아무 보호도 없었다
        #    — addr_search.search() 자신의 "실패하면 빈 목록" 계약이 유일한
        #    방어선이었는데, 그 계약은 이미 한 번 깨진 적이 있다(라운드294,
        #    IncompleteRead 누출 — 지금은 고쳐져 있지만 그 하위 계층이 다시
        #    회귀하지 않는다는 가정에만 기대면 안 된다). 여기서 하나 더 막아
        #    한 행의 검색 실패가 나머지 행 전부(최대 --limit)를 죽이지 않게 한다.
        try:
            hits = ADDR.search(q)
            time.sleep(PAUSE)
            best = next((h for h in hits if h.get("lat") and h.get("lng")), None)
            #  주소 칸에 '본사: … / 공장: …' 처럼 여러 주소와 설명이 섞여 들어온 곳이 많다.
            #  그대로 넣으면 검색이 통째로 실패한다 — 첫 주소만 추려 한 번 더 물어본다.
            #  ⚠⚠ [라운드160] "결과가 아예 없을 때"(not hits)만 재시도했다 — 카카오가
            #    좌표 없는 place 후보를 섞어 내면(비어있진 않다) best 는 그대로 None
            #    인데 재시도 자체가 안 열려, 정제 주소로는 분명히 찾을 후보를 포기했다.
            #    "찾았는가"(not best) 로 봐야 한다.
            if not best:
                q2 = _first_address(q)
                if q2 and q2 != q:
                    hits = ADDR.search(q2)
                    time.sleep(PAUSE)
                    best = next((h for h in hits if h.get("lat") and h.get("lng")), None)
                    if best:
                        used_q = q2
        except Exception as ex:
            skip_search_err += 1
            print(f"  ⚠ {r['name'][:18]:18} 검색 실패({type(ex).__name__}) — 건너뜀")
            continue
        if not best:
            skip_none += 1
            print(f"  · {r['name'][:18]:18} 못 찾음   {q[:34]}")
            if not dry:
                _mark_failed(r["id"])
            continue
        if not _in_korea(best["lat"], best["lng"]):
            skip_bad += 1
            print(f"  ⚠ {r['name'][:18]:18} 좌표가 한반도 밖"
                  f"({best['lat']:.3f},{best['lng']:.3f}) — 건너뜀")
            if not dry:
                _mark_failed(r["id"])
            continue
        #  ⚠⚠ [라운드302] 검색에 실제로 쓴 문자열(정제된 q2 로 찾았으면 q2)이
        #    아니라 항상 원문 q 로 이 판정을 했다 — '본사: 서울 강남구… / 공장:
        #    경기 김포시…' 처럼 원문에 다른 동네 이름이 섞여 있으면, 그 무관한
        #    조각이 검색 결과의 동네와 우연히 겹쳐 완전히 다른 도시 좌표를
        #    "동네 일치"로 잘못 통과시킬 수 있었다(실측: 위 예시로 재현 —
        #    원문 기준이면 통과, 실제 검색문 기준이면 정확히 거름). 실제로
        #    이 좌표를 있게 만든 문자열을 기준으로 판정한다.
        want = f"{r['region'] or ''} {used_q}"
        if not _region_ok(want, best.get("region", "") + " " + best.get("road", "")):
            skip_far += 1
            print(f"  ⚠ {r['name'][:18]:18} 동네 불일치 — 건너뜀"
                  f"   등록[{(r['region'] or '')[:12]}] ≠ 검색[{best.get('region','')[:12]}]")
            if not dry:
                _mark_failed(r["id"])
            continue
        if not dry:
            try:
                conn.execute(f"UPDATE {table} SET lat=?, lng=?, geo_src='주소검색' WHERE id=?",
                             (best["lat"], best["lng"], r["id"]))
                conn.commit()
            except Exception as ex:
                #  ⚠⚠ [라운드267] collect_emails.py 감사에서 드러난 것과 같은
                #    구조 — 이 UPDATE·commit 이 실패해도(락 경합 등) 이미 찾은
                #    나머지 좌표까지 배치 전체가 죽으면 안 된다. 이 행만
                #    건너뛴다(재실행하면 좌표가 여전히 비어 있어 다시 뽑힌다).
                conn.rollback()
                skip_err += 1
                print(f"  ⚠ {r['name'][:18]:18} 저장 실패({type(ex).__name__}) — 건너뜀")
                continue
        done += 1
        print(f"  ✔ {r['name'][:18]:18} {best['lat']:.5f},{best['lng']:.5f}  {best.get('road','')[:30]}")
    if not dry and done:
        DB.log(conn, "정비도구", "좌표 일괄 채움", f"{table} {done}건")
        conn.commit()
    conn.close()
    print(f"  → 채움 {done} · 동네 불일치 {skip_far} · 한반도 밖 {skip_bad} "
          f"· 못 찾음 {skip_none} · 검색 실패 {skip_search_err} · 저장 실패 {skip_err}"
          + ("   (미리보기 — 저장하지 않음)" if dry else ""))
    return done


def report():
    """지금 좌표가 얼마나 채워져 있는지 — 정비 전후를 같은 잣대로 본다."""
    conn = DB.get_db()
    for t, cond in (("partners", "status='활성'"), ("cases", "COALESCE(is_demo,0)=0")):
        tot = conn.execute(f"SELECT COUNT(*) n FROM {t} WHERE {cond}").fetchone()["n"]
        has = conn.execute(
            f"SELECT COUNT(*) n FROM {t} WHERE {cond} AND lat IS NOT NULL").fetchone()["n"]
        adr = conn.execute(
            f"SELECT COUNT(*) n FROM {t} WHERE {cond} "
            f" AND TRIM(COALESCE(address,''))<>''").fetchone()["n"]
        pct = (has * 100 // tot) if tot else 0
        print(f"  {t:9} 전체 {tot:5} · 주소 있음 {adr:5} · 좌표 있음 {has:5} ({pct}%)")
    conn.close()


def demo():
    """python geocode_fill.py --self-check — 판정 로직이 맞는지 한 번에 확인."""
    assert _region_ok("서울 송파구 올림픽로", "서울 송파구")
    assert _region_ok("경기 성남시 분당구", "경기 성남시")
    assert not _region_ok("서울 송파구", "서울 강남구"), "다른 구를 통과시키면 안 된다"
    assert not _region_ok("서울 송파구", "부산 해운대구")
    assert _region_ok("서울", "서울 송파구"), "시군구를 못 뽑으면 시도로 판정"
    #  ★ 통합 행정구역 표기 — 실데이터에서 광주 업체 14곳이 이것 때문에 걸러졌다
    assert _region_ok("광주 (북구)", "전남광주통합특별시 북구"), "통합 표기를 같은 곳으로 봐야 한다"
    assert _region_ok("광주광역시", "전남광주통합특별시 남구")
    assert not _region_ok("광주 북구", "전남광주통합특별시 서구"), "구가 다르면 여전히 거른다"
    #  ★★ [라운드512] '대구'는 시/도 이름 자체가 '구'로 끝난다 — 구 정보 없이
    #    등록된 대구 업체가 실제로는 같은 도시인 검색 결과를 동네 불일치로
    #    오판하면 안 된다(dispatch.py _region_key 의 라운드511과 같은 함정).
    assert _region_ok("대구", "대구광역시 동구"), "대구(구 정보 없음)도 같은 도시면 통과해야 한다"
    assert _region_ok("대구", "대구광역시 중구")
    assert _region_ok("대구", "대구")
    assert not _region_ok("대구 동구", "대구광역시 서구"), "대구 안에서도 구가 다르면 여전히 거른다"
    #  ★★ [라운드649] '중구·동구·서구·남구·북구' 는 여러 광역시가 나눠 쓰는 이름이다 —
    #    구 이름만 겹쳐도 시도가 다르면 완전히 다른 도시다(고치기 전엔 전부 True였다).
    assert not _region_ok("서울 중구 세종대로 110", "부산 중구 대청로 33"), \
        "구 이름이 같아도 시도가 다르면 다른 동네다"
    assert not _region_ok("대전 동구 대전로", "광주 동구 금남로")
    assert not _region_ok("인천 서구 청라", "대구 서구 달구벌대로")
    assert not _region_ok("울산 남구 삼산로", "부산 남구 못골로")
    assert _region_ok("서울 중구 세종대로 110", "서울 중구 태평로"), "같은 시도 안 같은 구는 그대로 통과"
    #  ★★ [라운드650] '세종로'·'세종대로' 는 서울의 실제 도로명이다 — 시도 이름
    #    경계 없이 부분일치하면 '세종'(세종특별자치시)으로 오판된다. 세종시는
    #    구가 없어 got 쪽 _gu_set 이 늘 비고, _region_ok 맨 아래(시도만 비교)
    #    분기로 빠지므로 이 오판이 곧바로 "동네 일치"로 이어진다(고치기 전엔
    #    True — 약 120km 떨어진 서울시청 앞과 세종시가 같은 동네로 잡혔다).
    assert not _region_ok("서울 중구 세종대로 110", "세종특별자치시 반곡동 108"), \
        "'세종대로'의 '세종'이 진짜 세종시와 같은 시도로 오판되면 안 된다"
    assert not _region_ok("서울 종로구 세종로 1", "세종특별자치시 나성동 1"), \
        "'세종로'도 마찬가지 — 서울 도로명일 뿐 세종시가 아니다"
    assert _region_ok("서울 중구 세종대로 110", "서울특별시 중구 세종대로"), \
        "정작 서울-서울 비교(같은 '세종대로')는 여전히 통과해야 한다"
    #  ★ 덤 — '경기장길' 같은 도로명의 '경기'도 같은 함정이다. got 쪽이 '경기도'
    #    한 단어뿐이면(구를 못 뽑아 맨 아래 시도-only 분기를 탄다) 고치기 전엔
    #    서울 송파구 주소가 '경기도'와 같은 시도로 오판되어 True 가 나왔다.
    assert not _region_ok("서울 송파구 경기장길 10", "경기도"), \
        "'경기장길'의 '경기'가 경기도로 오판되면 안 된다"
    #  ★★ [라운드653] 전남·전북·충남·충북·경남·경북 여섯 도는 '경상북도'처럼
    #    정식 명칭으로도 흔히 적힌다(실데이터: partners.address 73건이 이
    #    정식 명칭을 쓴다). _SIDO 정규식이 축약형만 담아, 정식 명칭 쪽은 시도가
    #    빈 집합으로 나오면 바로 위([라운드649]) "구 이름이 같아도 시도가
    #    다르면 다른 동네" 검사가 건너뛰어진다(고치기 전엔 전부 True —
    #    포항·여수·천안·창원이 각각 100km 이상 떨어진 부산·서울·광주·대구와
    #    같은 동네로 통과했다).
    assert not _region_ok("경상북도 포항시 남구 대잠동", "부산광역시 남구 대연동"), \
        "정식 명칭 '경상북도'가 축약형 매칭을 피해가면 안 된다(포항≠부산)"
    assert not _region_ok("전라남도 여수시 중앙동", "서울특별시 중구 태평로")
    assert not _region_ok("충청남도 천안시 동남구", "광주광역시 동구 금남로")
    assert not _region_ok("경상남도 창원시 성산구", "대구광역시 중구 동성로")
    #  ★ 대조군 — 정식 명칭과 축약형이 같은 도를 가리키면 여전히 통과해야 한다
    assert _region_ok("경상북도 포항시 남구 대잠동", "경북 포항시 남구")
    assert _region_ok("전라남도 목포시 용해동", "전남 목포시")
    #  ★ 여러 주소가 섞인 칸에서 첫 주소만 추리는지 — 실데이터에서 19건이 이 모양이었다
    assert _first_address("본사: 부산 사하구 동매로 120 한신혜성상가 203호 / 공장: 김해")         == "부산 사하구 동매로 120", _first_address("본사: 부산 사하구 동매로 120 한신혜성상가 203호 / 공장: 김해")
    assert _first_address("경남 김해시 한림면 용덕로302번길 102 / 경남 김해시 한림면")         == "경남 김해시 한림면 용덕로302번길 102"
    assert _first_address("경기도 수원시 팔달구 연무동 6-4 1층 (푸터 표기: 경기도)")         == "경기도 수원시 팔달구 연무동 6-4"
    assert _first_address("") == ""
    print("자체 점검 통과 — 동네 불일치 판정 · 주소 추리기 정상")


def main():
    ap = argparse.ArgumentParser(description="등록 주소 → 좌표 채우기")
    ap.add_argument("--target", default="partners", choices=["partners", "cases", "both"])
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--dry", action="store_true", help="바뀔 내용만 보고 저장하지 않음")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args()
    if a.self_check:
        demo(); return 0
    print("=" * 62)
    print("  좌표 정비 — 주소는 그대로 두고 좌표만 채웁니다")
    print("=" * 62)
    print("\n[정비 전]")
    report()
    for t in (["partners", "cases"] if a.target == "both" else [a.target]):
        fill(t, a.limit, a.dry)
    if not a.dry:
        print("\n[정비 후]")
        report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
