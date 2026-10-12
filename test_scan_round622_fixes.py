# -*- coding: utf-8 -*-
"""스캔 622라운드 회귀 — dispatch.py _region_key()가 '특례시'(2022년부터
   수원·고양·용인·창원 4개 시가 쓰는 공식 행정 명칭, 예: '용인특례시')를
   도시명 3글자 + 접미어 '시'로 착각해 도시명을 "용인특례" 처럼 통째로
   뭉개던 결함.

  직접 조사(하위위임 없음) — Part A(레거시 온디스크 되돌림-복원 마이그레이션)를
  계속하며 round490/491/493/437/441의 되돌림-증명 템플릿을 옮기던 중,
  geo.py resolve()(round316)가 이미 "2022년부터 수원·고양·용인·창원 4개 시가
  '특례시'라는 공식 행정 명칭을 쓴다"며 `src.replace("특례시", "시")`로
  미리 정규화해 두고, 그 실측 근거로 "운영DB 협력사 #211 하우건설(주)의
  실주소가 정확히 '용인특례시' 표기"라고 명시한 것을 다시 읽다가, dispatch.py
  가 지역 문자열을 각자 재구현하는 구조(round511·512·516이 이미 지적한
  바로 그 패턴 — "짧은 지명이 다른 토큰의 접미어와 우연히 겹치는 문제"를
  파일마다 따로 풀고 있다)라는 점에서 dispatch.py _region_key()에도 이
  같은 "특례시" 정규화가 물려받아졌는지 직접 대조 — grep으로 이 저장소
  전체에서 "특례시" 문자열을 검색한 결과 geo.py 단 한 곳(round316)에만
  있고, dispatch.py에는 전혀 없음을 확인했다.

  결함 — _region_key()는 시/도 접두어를 뗀 토큰 중 '구'·'시'·'군'으로
  끝나는 첫 토큰을 찾아 그 마지막 한 글자만 잘라 돌려준다. '용인특례시'는
  이 접미어 판정에서 "시"로 끝나는 토큰으로 걸리는데, 마지막 한 글자만
  자르면 "용인특례"가 남는다 — 실제 도시명 "용인"이 아니라 "용인" +
  "특례"(2글자 잉여)가 rkey 가 된다. 실행으로 직접 재현:
      _region_key("경기도 용인특례시 기흥구", "") == "용인특례"  (정상값 "용인")
  같은 클래스가 수원·고양·창원 3곳에도 그대로 적용된다(전부 확인).

  영향 — candidates()는 이 rkey 를 앞뒤에 %를 붙인 LIKE 패턴으로 그대로
  SQL에 쓴다("%용인특례%"). "용인특례시"로 등록된 사건은 "용인시"로만
  표기된(가장 흔한 표기) 실제 같은 지역 협력사와 전혀 매칭되지 않는다 —
  round511의 "대구"(우연한 접미어 충돌)와는 원인이 다르지만(이번엔 신설
  행정명칭 자체가 접미어를 셋이나 더 얹은 것) 같은 증상(자동 출동 후보의
  "같은 지역" 우선순위가 조용히 무력화됨)을 낸다.

  고침 — geo.py가 round316에서 이미 검증해 둔 것과 정확히 같은 정규화
  (`src.replace("특례시", "시")`)를 시/도 접두어 제거 단계 바로 앞에
  추가했다. 새 헬퍼·새 상수 없음 — round511·512와 같은 ponytail 원칙
  (이미 있는 교훈을 형제 파일로 그대로 옮긴다).

  [1] 소스 확인 — 새 치환이 _region_key() 본문에 정확히 한 번, round511·
      547의 기존 처리는 그대로 남아 있음(회귀 없음).
  [2] 실행 — _region_key() 직접 호출 — 특례시 4개 도시(구 있음/단독) +
      round511·547 UNIT_CASES 전부 재확인(회귀 없음).
  [3] 실행 — 실제 sqlite3(:memory:) + 실제 dispatch.candidates() — "경기도
      용인특례시 기흥구" 사건에 "용인시 기흥구"(진짜 같은 지역, 정상표기)
      협력사와 "안양시 동안구"(가짜매칭 유발, 무관지역) 협력사를 함께 넣어
      "같은 지역" 분류가 정확한지 확인(round130·511·547과 같은 격리 기법).
  [4] 되돌림-증명 — _region_key()를 이 라운드 이전(round547 시점, 특례시
      정규화 없음) 구현으로 런타임에 되돌려(파일은 안 건드린다 — 순수
      함수라 안전, candidates()는 모듈 전역 이름으로 호출하므로 교체가
      그대로 반영됨) 같은 시나리오를 다시 돌리면, 진짜 같은 지역 협력사
      ("용인시 기흥구")가 "같은 지역"에서 실제로 빠짐을 재현.

      python test_scan_round622_fixes.py
"""
import io
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("BOKGUON_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="round622_"), "verify.db"))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


print("=" * 72)
print("  스캔 622라운드 회귀 — dispatch._region_key() '특례시' 도시명 오절단")
print("=" * 72)

DP_SRC = read("dispatch.py")

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — _region_key() 본문에 새 치환이 정확히 한 번")
# ──────────────────────────────────────────────────────────────
_start = DP_SRC.index("def _region_key(")
_rest = DP_SRC[_start:]
_end_rel = _rest.index("\n\ndef ", 1)
rk_body = _rest[:_end_rel] if _end_rel > 0 else _rest

chk(rk_body.count('src = src.replace("특례시", "시")') == 1,
    "★★★ '특례시'→'시' 정규화가 _region_key() 본문 안에 정확히 1번 있다")
chk("[라운드622]" in rk_body, "_region_key() 안에 라운드622 표식이 있다")
chk("[라운드511]" in rk_body and "[라운드547]" in rk_body,
    "round511·547의 기존 표식도 그대로 남아있다(회귀 없음)")
chk(rk_body.count("if p in DB.SIDO:") == 1,
    "round511의 SIDO 예외 처리 코드도 정확히 1번(중복/삭제 없음)")
chk(rk_body.count("non_sido = [p for p in parts if p not in DB.SIDO]") == 1,
    "round547의 non_sido 폴백 코드도 정확히 1번(중복/삭제 없음)")
chk(DP_SRC.count("def _region_key(") == 1, "_region_key() 정의가 정확히 1번만 있다(중복 정의 없음)")
#  치환이 시/도 접두어 제거보다 앞서야 한다(순서 자체는 독립적 치환이라
#  결과에 영향 없지만, 코드 위치로 "먼저 정규화"라는 의도를 확인해 둔다).
chk(rk_body.index('src = src.replace("특례시", "시")')
    < rk_body.index('parts = src.replace("특별시"'),
    "★★ '특례시' 정규화가 시/도 접두어 제거보다 앞선 줄에 있다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — _region_key() 직접 호출(같은 프로세스)")
# ──────────────────────────────────────────────────────────────
import dispatch as DP  # noqa: E402
import db as DB  # noqa: E402

#  특례시 4개 도시 — 구 있음(3단계)·단독(2단계) 양쪽 다 정상표기와 같은 결과여야 한다.
NEW_CASES = [
    ("경기도 용인특례시 기흥구", "", "용인", "★★★★★ 경기+용인특례시+기흥구 — '용인'(고치기 전엔 '용인특례')"),
    ("경기도 용인시 기흥구", "", "용인", "대조 — 정상표기 경기+용인시+기흥구도 그대로 '용인'(회귀 없음)"),
    ("경기도 수원특례시 영통구", "", "수원", "★★★★ 경기+수원특례시+영통구 — '수원'"),
    ("경기도 고양특례시 일산동구", "", "고양", "★★★★ 경기+고양특례시+일산동구 — '고양'"),
    ("경상남도 창원특례시 성산구", "", "창원", "★★★★ 경남+창원특례시+성산구 — '창원'"),
    ("용인특례시", "", "용인", "특례시 단독(구 없이) — '용인'"),
    ("수원특례시", "", "수원", "특례시 단독(구 없이) — '수원'"),
]
for region, addr, expect, label in NEW_CASES:
    got = DP._region_key(region, addr)
    chk(got == expect, label, f"_region_key({region!r},{addr!r}) = {got!r}, expected {expect!r}")

#  round511·547 UNIT_CASES 전부 재확인 — '특례시'가 없는 경로는 이번
#  라운드가 손대지 않은 분기라 전혀 안 바뀌어야 한다.
OLD_UNIT_CASES = [
    ("대구광역시 동구", "", "동", "회귀없음(round511) — 대구+동구 — '동'"),
    ("대구", "", "대구", "회귀없음(round511) — 대구 단독 — '대구'"),
    ("대구광역시 수성구", "", "수성", "회귀없음(round511) — 대구+수성구 — '수성'"),
    ("서울특별시 송파구", "", "송파", "회귀없음 — 서울+송파구(접미어 있음, 이른 return)"),
    ("경기도 수원시 팔달구", "", "수원", "회귀없음 — 경기+수원시(특례시 아닌 정상표기)"),
    ("전북특별자치도 전주시", "", "전주", "회귀없음 — 특별자치도 접두어"),
    ("서울 강서", "", "강서", "회귀없음(round547) — 서울+강서(접미어 없음) — '강서'"),
    ("인천 남동", "", "남동", "회귀없음(round547) — 인천+남동(접미어 없음) — '남동'"),
    ("경기 용인", "", "용인", "회귀없음(round547) — 경기+용인(접미어 없음, '특례' 아님) — '용인'"),
]
for region, addr, expect, label in OLD_UNIT_CASES:
    got = DP._region_key(region, addr)
    chk(got == expect, label, f"_region_key({region!r},{addr!r}) = {got!r}, expected {expect!r}")

chk(DP._region_key("", "") == "", "빈 입력은 빈 문자열(회귀 없음)")
chk(DP._region_key("", "경기도 성남시 분당구") in ("성남", "분당"),
    "주소로도 지역 추출(기존 허용값, 회귀 없음)",
    DP._region_key("", "경기도 성남시 분당구"))

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 실제 sqlite3(:memory:) + 실제 dispatch.candidates()")
# ──────────────────────────────────────────────────────────────


def _mkdb():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE cases(id INTEGER PRIMARY KEY, category TEXT, region TEXT, address TEXT,
                            lat REAL, lng REAL);
        CREATE TABLE work_lots(id INTEGER PRIMARY KEY, case_id INTEGER, category TEXT);
        CREATE TABLE partners(id INTEGER PRIMARY KEY, name TEXT, status TEXT, license_status TEXT,
                               region TEXT, address TEXT, category TEXT, major TEXT,
                               lat REAL, lng REAL, login_id TEXT, phone TEXT);
    """)
    return conn


#  round130·511·547과 같은 격리 — 사건/파트너 공종을 절대 안 겹치는 값으로
#  둬 1·3순위(공종 필요)는 항상 0건, 2순위("같은 지역", 공종 무관)만 남긴다.
CASE_CAT = "사건전용공종-622(매칭안됨)"
PARTNER_CAT = "업체전용공종-622(매칭안됨)"


def _build():
    conn = _mkdb()
    #  실제 카카오 응답·round316 실측 표기와 같은 형태("OO특례시").
    conn.execute("INSERT INTO cases(id,category,region,address) VALUES (1,?,?,'')",
                 (CASE_CAT, "경기도 용인특례시 기흥구"))
    partners = [
        ("기흥방수(진짜용인시,정상표기)", "경기도 용인시 기흥구", ""),
        ("안양방수(가짜매칭유발,무관지역)", "경기도 안양시 동안구", ""),
        ("대구방수(무관대조군)", "대구광역시 동구", ""),
    ]
    for i, (name, region, address) in enumerate(partners, start=1):
        conn.execute(
            "INSERT INTO partners(id,name,status,license_status,region,address,category,major,"
            "login_id,phone) VALUES (?,?,'활성','일반',?,?,?, '', '', ?)",
            (i, name, region, address, PARTNER_CAT, f"0100000000{i}"))
    conn.commit()
    return conn


try:
    conn = _build()
    got = DP.candidates(conn, 1)
    by_name = {x["name"]: x for x in got}
    chk("기흥방수(진짜용인시,정상표기)" in by_name,
        "★★★★★ 새 코드 — '용인시'(정상표기) 협력사가 '용인특례시' 사건의 '같은 지역'으로 잡힌다",
        list(by_name))
    if "기흥방수(진짜용인시,정상표기)" in by_name:
        chk(by_name["기흥방수(진짜용인시,정상표기)"]["why"] == "같은 지역",
            "그 협력사의 매칭 사유가 '같은 지역'이다(공종은 고의로 안 겹치게 했다)",
            by_name["기흥방수(진짜용인시,정상표기)"]["why"])
    chk("안양방수(가짜매칭유발,무관지역)" not in by_name,
        "안양(무관 지역) 협력사는 섞이지 않는다(대조군)", list(by_name))
    chk("대구방수(무관대조군)" not in by_name,
        "대구 협력사는 애초에 무관해 안 섞인다(대조군, 옛/새 코드 공통)", list(by_name))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] 실제 sqlite3 실행 준비/실행", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌림-증명 — _region_key()를 이 라운드 이전(round547 시점) 구현으로 되돌리면")
# ──────────────────────────────────────────────────────────────


def _old_region_key(region, address):
    """이 라운드(622) 이전 구현 그대로('특례시' 정규화 없음) — 되돌림-증명 전용.

    round511·547이 남긴 처리는 그대로 두고, 622가 추가한 치환 한 줄만 뺀 것 —
    즉 이 세션이 손대기 직전 dispatch.py 의 실제 원문과 동일하다.
    """
    src = (region or "") or (address or "")
    src = src.strip()
    if not src:
        return ""
    parts = src.replace("특별시", " ").replace("광역시", " ").replace("특별자치시", " ") \
               .replace("특별자치도", " ").replace("자치시", " ").split()
    for p in parts:
        if p in DB.SIDO:
            continue
        if p.endswith(("구", "시", "군")):
            return p[:-1] if len(p) > 1 else p
    non_sido = [p for p in parts if p not in DB.SIDO]
    if non_sido:
        return non_sido[-1]
    return parts[0] if parts else ""


try:
    chk(_old_region_key("경기도 용인특례시 기흥구", "") == "용인특례",
        "★ 되돌림 대상 함수 자체가 옛 결함('용인'이 아니라 '용인특례')을 실제로 재현한다(자체 점검)",
        _old_region_key("경기도 용인특례시 기흥구", ""))

    _orig = DP._region_key
    DP._region_key = _old_region_key      # candidates() 는 모듈 전역 이름으로 호출하므로 이 교체가 그대로 반영된다
    try:
        conn = _build()
        broken = DP.candidates(conn, 1)
        broken_by_name = {x["name"]: x for x in broken}
        chk("기흥방수(진짜용인시,정상표기)" not in broken_by_name,
            "★★★★★ 옛 코드(되돌림) — '용인시'(정상표기) 협력사가 '용인특례시' 사건의 '같은 지역'에서"
            " 실제로 빠진다(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명)",
            list(broken_by_name))
        chk("안양방수(가짜매칭유발,무관지역)" not in broken_by_name,
            "대조 — 옛 코드에서도 무관 지역 협력사는 여전히 안 섞인다", list(broken_by_name))
        conn.close()
    finally:
        DP._region_key = _orig
    chk(DP._region_key("경기도 용인특례시 기흥구", "") == "용인",
        "★★★★★ 복원 확인 — DP._region_key가 원래(고친) 구현으로 되돌아왔다",
        DP._region_key("경기도 용인특례시 기흥구", ""))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [4] 되돌림-증명", f"{type(e).__name__} {e}")
    DP._region_key = _orig if "_orig" in dir() else DP._region_key

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
