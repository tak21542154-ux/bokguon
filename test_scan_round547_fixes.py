# -*- coding: utf-8 -*-
"""스캔 547라운드 회귀 — dispatch.py _region_key()가 '구/시/군' 접미어 없는
   구어체 동네이름(예: '인천 남동'·'서울 강서')을 시/도 수준으로 뭉개던 결함.

  직접 조사(하위위임 없음) — 이 세션이 이미 포화 상태로 확인한 각도(라운드
  감사흔적없는함수·서버측vs클라측검증비대칭·형제재구현불일치·형제락비대칭
  ·형제후처리누락 등 다수, 오케스트레이터 지시문 참고)와 겹치지 않는 새
  각도를 찾다가, region_matches()/norm_regions()(db.py, 시/도 수준 정규화 —
  round61·165·186·196·333이 이미 여러 번 감사)와는 별개로 dispatch.py 가
  **자기만의 구/시/군 단위 지역 열쇠 추출 함수**(_region_key(), round511이
  '대구' 한 건만 고쳤다)를 갖고 있는 것을 확인, 그 함수 자체를 함수 단위로
  재감사했다.

  결함 — _region_key()는 시/도 접두어를 뗀 토큰 중 '구'·'시'·'군'으로
  끝나는 첫 토큰을 찾아 그 접미어를 잘라 돌려주고, 그런 토큰이 하나도
  없으면 parts[0](대개 시/도 자기 자신)으로 폴백한다. 그런데 한국어
  구어체는 구/시/군 단위 지명에서 그 접미어 자체를 흔히 생략한다
  ('인천 남동구'→'인천 남동', '서울 강서구'→'서울 강서', '경기 용인시'→
  '경기 용인') — 이 경우 두 번째 토큰이 구/시/군으로 끝나지 않으므로
  반복문이 그냥 지나치고, 결국 parts[0]인 '인천'/'서울'/'경기'로 뭉개진다.
  **사건등록 화면 자신의 안내문구가 바로 이 구어체를 예로 든다**
  (templates/insurer_portal.html #c_region, placeholder="예: 인천 남동") —
  이 화면의 안내를 그대로 따라 입력하면 매번 이 결함에 걸린다.

  영향 — candidates()는 이 rkey 로 partners.region/address 를 LIKE 검색해
  "같은 지역"(1·2순위)을 정한다. rkey 가 '인천'으로 뭉개지면 실제로는
  '남동구'만 부를 생각이었던 사건이 인천 전역(강화군·옹진군 등 남동구와
  거리가 먼 지역 포함)의 협력사를 전부 "같은 지역"으로 우선 호출 대상에
  넣는다 — 30분 내 도착이 관건인 출동 배차에서 지역 필터가 사실상
  시/도 단위로 무력화된다.

  실측(운영 DB, 읽기전용 SELECT — 쓰기 없음): region 이 채워진 사건 96건
  중 28건(29%)이 이 모양이었다 — '서울 강서'→'서울', '경기 용인'→'경기'
  (14건, 반복 접수), '인천 남동'→'인천'(placeholder 예시와 정확히 일치),
  '부산 사상'→'부산', '충남 천안'→'충남', '전남 나주'→'전남',
  '경기 수원'→'경기', '경기 성남'→'경기', '서울 송파'→'서울' 등.

  고침 — db.SIDO 에 없는(=시/도 자체가 아닌) 토큰 중 **마지막 것**을
  최종 폴백으로 쓴다. 시/도만 적었을 때(예: '대구' 단독, round511의
  대조군)는 non_sido 가 비어 기존 parts[0] 폴백을 그대로 유지한다 —
  새 정책·새 헬퍼 없이 이 함수가 이미 참조하는 DB.SIDO 를 그대로
  재사용한다(round511과 같은 ponytail 원칙).

  [1] 소스 확인 — 새 코드가 _region_key() 본문에 정확히 한 번, round511의
      SIDO 예외 처리는 그대로 남아 있음(회귀 없음).
  [2] 실행 — _region_key() 직접 호출 — 접미어 생략 구어체(실측 사례 기반)
      + round511 UNIT_CASES 전부 재확인(회귀 없음).
  [3] 실행 — 실제 sqlite3(:memory:) + 실제 dispatch.candidates() — '인천
      남동' 사건에 진짜 남동구 협력사와 인천 강화군(가짜매칭 유발) 협력사를
      함께 넣어 "같은 지역" 분류가 정확한지 확인(round130·511과 같은
      격리 기법).
  [4] 되돌림-증명 — _region_key()를 이 라운드 이전 구현(non_sido 폴백 없음,
      즉 round511 시점 그대로)으로 런타임에 되돌려(파일은 안 건드린다 —
      순수 함수라 안전) 같은 시나리오를 다시 돌리면, 강화군 협력사가 실제로
      "같은 지역"으로 잘못 섞여 들어옴을 재현.
  [5] 운영 DB 대조(읽기전용) — 실제 region 있는 사건 중 옛 로직으로
      시/도까지 뭉개졌을 건수와 새 로직 적용 후 남는 건수를 대조(정보성,
      mode=ro, 쓰기 없음).

      python test_scan_round547_fixes.py
"""
import io
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("BOKGUON_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="round547_"), "verify.db"))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


print("=" * 72)
print("  스캔 547라운드 회귀 — dispatch._region_key() 접미어 생략 구어체 지명 뭉개짐")
print("=" * 72)

DP_SRC = read("dispatch.py")

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — _region_key() 본문에 새 코드가 정확히 한 번")
# ──────────────────────────────────────────────────────────────
_start = DP_SRC.index("def _region_key(")
_rest = DP_SRC[_start:]
_end_rel = _rest.index("\n\ndef ", 1)
rk_body = _rest[:_end_rel] if _end_rel > 0 else _rest

chk(rk_body.count("non_sido = [p for p in parts if p not in DB.SIDO]") == 1,
    "★★★ 접미어 없는 마지막 토큰 폴백이 _region_key() 본문 안에 정확히 1번 있다")
chk("[라운드547]" in rk_body, "_region_key() 안에 라운드547 표식이 있다")
chk("[라운드511]" in rk_body, "round511의 SIDO 예외 처리 표식도 그대로 남아있다(회귀 없음)")
chk(rk_body.count("if p in DB.SIDO:") == 1,
    "round511의 SIDO 예외 처리 코드 자체도 정확히 1번(중복/삭제 없음)")
chk(DP_SRC.count("def _region_key(") == 1, "_region_key() 정의가 정확히 1번만 있다(중복 정의 없음)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — _region_key() 직접 호출(같은 프로세스)")
# ──────────────────────────────────────────────────────────────
import dispatch as DP  # noqa: E402
import db as DB  # noqa: E402

#  실측(운영 DB, 읽기전용)에서 그대로 가져온 접미어 생략 사례 — 전부
#  '뭉개지지 않고' 세부지역이 그대로 나와야 한다.
NEW_CASES = [
    ("서울 강서", "", "강서", "★★★★★ 서울+강서(접미어 없음) — '강서'(고치기 전엔 '서울')"),
    ("인천 남동", "", "남동", "★★★★★ 인천+남동(사건등록 화면 placeholder 예시 그대로) — '남동'"),
    ("경기 용인", "", "용인", "★★★★ 경기+용인(접미어 없음, 실측 14건) — '용인'"),
    ("경기 수원", "", "수원", "경기+수원(접미어 없음) — '수원'"),
    ("경기 성남", "", "성남", "경기+성남(접미어 없음) — '성남'"),
    ("충남 천안", "", "천안", "충남+천안(접미어 없음) — '천안'"),
    ("전남 나주", "", "나주", "전남+나주(접미어 없음) — '나주'"),
    ("부산 사상", "", "사상", "부산+사상(접미어 없음) — '사상'"),
    ("서울 송파", "", "송파", "서울+송파(접미어 없음, round511 대조군과 달리 '구' 없음) — '송파'"),
]
for region, addr, expect, label in NEW_CASES:
    got = DP._region_key(region, addr)
    chk(got == expect, label, f"_region_key({region!r},{addr!r}) = {got!r}, expected {expect!r}")

#  round511 UNIT_CASES 전부 재확인 — 접미어가 '있는' 경로는 이번 라운드가
#  손대지 않은 이른 return 분기라 전혀 안 바뀌어야 한다.
OLD_UNIT_CASES = [
    ("대구광역시 동구", "", "동", "회귀없음 — 대구+동구(round511) — '동'"),
    ("대구", "", "대구", "회귀없음 — 대구 단독(non_sido 비어 옛 폴백 유지) — '대구'"),
    ("대구광역시 수성구", "", "수성", "회귀없음 — 대구+수성구(round511) — '수성'"),
    ("대구 동구", "", "동", "회귀없음 — 대구+동구(광역시 접미어 없이) — '동'"),
    ("대전광역시 동구", "", "동", "회귀없음 — 대전+동구(대조군)"),
    ("서울특별시 송파구", "", "송파", "회귀없음 — 서울+송파구(접미어 있음, 이른 return)"),
    ("부산광역시 해운대구", "", "해운대", "회귀없음 — 부산+해운대구"),
    ("경기도 수원시 팔달구", "", "수원", "회귀없음 — 경기+수원시(시 단위에서 멈추는 기존 동작)"),
    ("전북특별자치도 전주시", "", "전주", "회귀없음 — 특별자치도 접두어"),
]
for region, addr, expect, label in OLD_UNIT_CASES:
    got = DP._region_key(region, addr)
    chk(got == expect, label, f"_region_key({region!r},{addr!r}) = {got!r}, expected {expect!r}")

chk(DP._region_key("", "") == "", "빈 입력은 빈 문자열(회귀 없음)")
chk(DP._region_key("", "경기도 성남시 분당구") in ("성남", "분당"),
    "주소로도 지역 추출(test_dispatch.py와 같은 허용값, 회귀 없음)",
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


#  round130·511과 같은 격리 — 사건/파트너 공종을 절대 안 겹치는 값으로 둬
#  1·3순위(공종 필요)는 항상 0건, 2순위("같은 지역", 공종 무관)만 남긴다.
CASE_CAT = "사건전용공종-547(매칭안됨)"
PARTNER_CAT = "업체전용공종-547(매칭안됨)"


def _build():
    conn = _mkdb()
    #  실측 사건(26-07142)과 정확히 같은 표기 — placeholder 예시 그대로.
    conn.execute("INSERT INTO cases(id,category,region,address) VALUES (1,?,?,'')",
                 (CASE_CAT, "인천 남동"))
    partners = [
        ("남동방수(진짜남동구)", "인천광역시 남동구", ""),
        ("강화방수(가짜매칭유발)", "인천광역시 강화군", ""),
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
    chk("남동방수(진짜남동구)" in by_name,
        "★★★★★ 진짜 남동구 협력사는 '같은 지역'으로 잡힌다", list(by_name))
    if "남동방수(진짜남동구)" in by_name:
        chk(by_name["남동방수(진짜남동구)"]["why"] == "같은 지역",
            "그 협력사의 매칭 사유가 '같은 지역'이다(공종은 고의로 안 겹치게 했다)",
            by_name["남동방수(진짜남동구)"]["why"])
    chk("강화방수(가짜매칭유발)" not in by_name,
        "★★★★★ 인천 강화군 협력사는 '인천 남동'(=남동구) 사건의 '같은 지역'에 섞이지 않는다(고친 뒤)",
        list(by_name))
    chk("대구방수(무관대조군)" not in by_name,
        "대구 협력사는 애초에 무관해 안 섞인다(대조군, 옛/새 코드 공통)",
        list(by_name))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] 실제 sqlite3 실행 준비/실행", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌림-증명 — _region_key()를 이 라운드 이전(round511 시점) 구현으로 되돌리면")
# ──────────────────────────────────────────────────────────────


def _old_region_key(region, address):
    """이 라운드(547) 이전 구현 그대로(non_sido 마지막 토큰 폴백 없음) — 되돌림-증명 전용.

    round511이 남긴 SIDO 예외 처리는 그대로 두고, 547이 추가한 폴백만 뺀 것 —
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
    return parts[0] if parts else ""


try:
    chk(_old_region_key("인천 남동", "") == "인천",
        "★ 되돌림 대상 함수 자체가 옛 결함('남동'을 잃고 '인천'만 남김)을 실제로 재현한다(자체 점검)",
        _old_region_key("인천 남동", ""))

    _orig = DP._region_key
    DP._region_key = _old_region_key      # candidates() 는 모듈 전역 이름으로 호출하므로 이 교체가 그대로 반영된다
    try:
        conn = _build()
        broken = DP.candidates(conn, 1)
        broken_by_name = {x["name"]: x for x in broken}
        chk("강화방수(가짜매칭유발)" in broken_by_name,
            "★★★★★ 옛 코드(되돌림) — 인천 강화군 협력사가 '인천 남동' 사건의 '같은 지역'으로 잘못 섞인다"
            "(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명)",
            list(broken_by_name))
        if "강화방수(가짜매칭유발)" in broken_by_name:
            chk(broken_by_name["강화방수(가짜매칭유발)"]["why"] == "같은 지역",
                "★★★★★ 그 오매칭의 사유까지 '같은 지역'으로 잘못 찍힌다",
                broken_by_name["강화방수(가짜매칭유발)"]["why"])
        chk("남동방수(진짜남동구)" in broken_by_name,
            "대조 — 옛 코드에서도 진짜 남동구 협력사는 여전히 잡힌다(우연히 '인천'을 포함하므로)")
        conn.close()
    finally:
        DP._region_key = _orig
    chk(DP._region_key("인천 남동", "") == "남동",
        "★★★★★ 복원 확인 — DP._region_key가 원래(고친) 구현으로 되돌아왔다",
        DP._region_key("인천 남동", ""))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [4] 되돌림-증명", f"{type(e).__name__} {e}")
    DP._region_key = _orig if "_orig" in dir() else DP._region_key

# ══════════════════════════════════════════════════════════════
print("\n[5] 운영 DB 대조(읽기전용) — 뭉개짐 규모 실측")
# ──────────────────────────────────────────────────────────────
try:
    prod_path = os.path.join(HERE, "bokguon.db")
    if os.path.exists(prod_path):
        uri = f"file:{prod_path.replace(os.sep, '/')}?mode=ro"
        pconn = sqlite3.connect(uri, uri=True)
        pconn.row_factory = sqlite3.Row
        rows = pconn.execute(
            "SELECT region, address FROM cases WHERE COALESCE(region,'')<>''").fetchall()
        total = len(rows)

        def _tokens(region):
            return region.replace("특별시", " ").replace("광역시", " ").replace("특별자치시", " ") \
                          .replace("특별자치도", " ").replace("자치시", " ").split()

        old_collapsed = sum(
            1 for r in rows
            if len(_tokens(r["region"] or "")) >= 2
            and _old_region_key(r["region"], r["address"] or "") in DB.SIDO)
        new_collapsed = sum(
            1 for r in rows
            if len(_tokens(r["region"] or "")) >= 2
            and DP._region_key(r["region"], r["address"] or "") in DB.SIDO)
        chk(True,
            f"참고 — region 있는 사건 {total}건 중, 세부지역을 적었는데도(토큰 2개 이상) "
            f"시/도로 뭉개진 건수: 옛 로직 {old_collapsed}건 → 새 로직 {new_collapsed}건 "
            f"(정보성 기록, pass/fail 아님)")
        pconn.close()
    else:
        chk(True, "운영 DB 파일이 없어 [5]는 건너뜀(스크래치 환경 — 정상)")
except Exception as e:                                              # noqa: BLE001
    chk(True, f"[5] 운영 DB 대조는 정보성 확인이라 실패해도 배터리를 막지 않음: {type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
