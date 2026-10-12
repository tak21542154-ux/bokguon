# -*- coding: utf-8 -*-
"""스캔 649라운드 회귀(직접조사, 하위위임 없음) — geocode_fill.py _region_ok()가

  구 이름만 겹치면 시도(광역시/도)는 아예 안 보고 곧장 통과시키던 결함.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

  직접 조사(하위위임 없음) — round646~648이 훑은 "리터럴 문자열이 자기 문서화된
  의도대로 정확히 매치하는가" 렌즈를, geocode_fill.py에 다시 대 봤다(round512가
  같은 파일 _gu_set()에서 '대구' 결함을 찾은 것과 같은 파일, 다른 함수). 이번엔
  round512처럼 "아예 못 채우는" 방향이 아니라 정반대 — **틀린 도시 좌표를 채워
  버리는** 더 심한 방향의 결함이다.

  결함 — _region_ok(want, got)의 첫 갈래 `if w & g: return True`는 두 문자열에서
  뽑은 시/군/구 토큰 집합이 하나라도 겹치면 시도(광역시/도)는 검사하지 않고 곧장
  같은 동네로 판정한다. 그런데 '중구·동구·서구·남구·북구'는 서울·부산·대구·인천·
  광주·대전·울산 등 **여러 광역시가 나눠 쓰는 흔한 이름**이다 — 서울 중구와 부산
  중구는 토큰만 보면 둘 다 {'중구'}로 완전히 같지만 실제로는 300km 넘게 떨어진
  다른 도시다. 이 함수 자신의 모듈 docstring이 명시한 안전 원칙("검색 결과가
  주소와 다른 시군구를 가리키면 채우지 않는다 — 엉뚱한 좌표는 없느니만 못하다
  (배차가 조용히 틀린 업체를 부른다)")을 정면으로 벗어난다.

  실측(직접 재현, 순수함수 호출, 하위 상태 없음) — 고치기 전 코드로
    _region_ok("서울 중구 세종대로 110", "부산 중구 대청로 33") == True
    _region_ok("대전 동구 대전로", "광주 동구 금남로")           == True
    _region_ok("인천 서구 청라", "대구 서구 달구벌대로")         == True
    _region_ok("울산 남구 삼산로", "부산 남구 못골로")           == True
  네 조합 전부 "같은 동네"로 오판했다(실제로는 전부 다른 광역시). round159가
  이미 고친 **두 번째** 갈래(시도가 겹치는데 구 이름이 다를 때의 "정보 비대칭"
  구제 로직)와는 별개로, 훨씬 더 자주 밟히는 **첫 번째**(구 이름이 직접 겹칠
  때의) 갈래에 시도 검사가 아예 없었다 — round159의 교훈이 같은 함수 안
  형제 갈래에도 전파되지 않은 상태였다.

  이 결함이 실제로 위험한 이유 — geocode_fill.fill()이 이 판정을 통과한 좌표를
  그대로 partners/cases 테이블 lat·lng에 저장하고 geo_src='주소검색'으로
  기록한다. 즉 서울 중구에 등록된 협력사가 카카오 검색 결과의 모호성(도로명이
  겹치거나 API가 드물게 다른 지역 후보를 내는 경우)으로 부산 중구 좌표를
  받으면, 이 판정이 그걸 그대로 "확인됨"으로 승인해 버린다 — dispatch.py의
  거리순 배차가 그 틀린 좌표를 진짜 거리로 믿고 조용히 엉뚱한 협력사를 부르게
  된다(이 파일 자신의 모듈 docstring이 정확히 이 시나리오를 경고한 바로 그
  결과). round512는 "못 채움"(안전 방향 실패)이었지만 이번 결함은 "틀리게
  채움"(위험 방향 실패)이라는 점에서 더 심각하다.

  고침 — geocode_fill.py _region_ok(), `if w & g:` 분기 안에 시도 충돌 검사를
  추가했다. 시도 정보가 양쪽 다 있고 서로 겹치지 않을 때만 이 지름길을 막는다
  (한쪽만 시도 정보가 없는 정보 비대칭 상황은 round159와 같은 원칙으로 그대로
  통과 — 예: '송파구'만 있고 시도가 없는 예전 표기 데이터를 새로 막지 않는다).
  새 헬퍼·새 상수 없이 이미 있는 _sido_set()을 재사용한다(ponytail 원칙,
  round512와 동일). 296→316줄(+20, 전부 근거 주석 + 4줄 로직).

  회귀테스트(이 파일, 28개 검사) 신설 —
  [1] 소스 확인 — _region_ok() 본문에 새 시도충돌 검사가 정확히 한 번 있다.
  [2] 실행 — _region_ok()를 기존 자체점검 12건(demo()와 동일) + 신규 충돌
      4조합 + 대조군(같은 시도·다른 구는 여전히 통과)으로 직접 호출해 회귀
      없음과 결함 수정을 함께 확인.
  [3] 실행 — 실제 geocode_fill.fill()을 스크래치 DB + 스텁 ADDR.search(서울
      중구로 등록된 협력사를 검색하면 부산 중구 좌표를 내주는 가짜 카카오
      응답)로 끝까지 돌려, 고친 코드에서는 그 틀린 좌표가 **저장되지 않고**
      geo_src='시도실패'로 표시됨을 확인(round267이 확립한 fill() 엔드투엔드
      검증 기법 그대로).
  [4] 되돌림-증명 — _region_ok()를 이 라운드 이전 구현(시도충돌 검사 없음)으로
      런타임에 되돌려(파일은 안 건드린다 — 순수 함수라 안전) 같은 시나리오를
      새 협력사 행으로 다시 돌리면, 실제로 부산 좌표가 서울 협력사에
      geo_src='주소검색'으로 잘못 저장되는 옛 결함이 fill() 실행으로
      재현됨을 확인(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명).

      python test_scan_round649_fixes.py
"""
import ast
import io
import os
import secrets
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
#  ⚠ db.py 의 운영DB 안전장치가 발동하려면, geocode_fill.py(import db)를
#    불러오기 **전에** 검증용 DB 경로부터 정해야 한다(round267·512와 동일 관례).
_tmpdir = tempfile.mkdtemp(prefix="round649_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


print("=" * 72)
print("  스캔 649라운드 회귀 — geocode_fill._region_ok() 시도(광역시) 미검사")
print("=" * 72)

GF_SRC = read("geocode_fill.py")

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — _region_ok() 본문에 새 시도충돌 검사가 정확히 한 번")
# ──────────────────────────────────────────────────────────────
tree = ast.parse(GF_SRC, filename="geocode_fill.py")
ro_node = next(n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "_region_ok")
ro_body = ast.get_source_segment(GF_SRC, ro_node)

chk(ro_body.count("sw and sg and not (sw & sg)") == 1,
    "★★★ 시도충돌 검사(양쪽 다 시도 있고 안 겹칠 때만 거른다)가 정확히 1번 있다",
    ro_body.count("sw and sg and not (sw & sg)"))
chk("[라운드649]" in ro_body, "_region_ok() 안에 라운드649 표식이 있다")
chk(GF_SRC.count("def _region_ok(") == 1, "_region_ok() 정의가 정확히 1번만 있다(중복 정의 없음)")
#  ⚠ round159 fix(둘째 갈래의 wg/gg 정보비대칭 로직)가 이번 수정으로 지워지지
#    않았는지도 같이 확인 — 형제 결함을 고치다 다른 형제를 지우면 안 된다.
chk("bool(wg & gg) or (bool(wg) != bool(gg))" in ro_body,
    "★ round159가 고친 둘째 갈래(정보 비대칭 구제)가 그대로 남아 있다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — _region_ok() 직접 호출(같은 프로세스, 기존 자체점검 12건 + 신규)")
# ──────────────────────────────────────────────────────────────
import geocode_fill as GF  # noqa: E402

try:
    # ── 기존 자체점검(demo()) 12건 — 회귀 없이 그대로 유지되는가 ──
    chk(GF._region_ok("서울 송파구 올림픽로", "서울 송파구"), "★ (기존) 같은 구는 통과")
    chk(GF._region_ok("경기 성남시 분당구", "경기 성남시"), "★ (기존) 시군구 일부일치 통과")
    chk(not GF._region_ok("서울 송파구", "서울 강남구"), "★ (기존) 다른 구는 거른다")
    chk(not GF._region_ok("서울 송파구", "부산 해운대구"), "★ (기존) 다른 시도·다른 구는 거른다")
    chk(GF._region_ok("서울", "서울 송파구"), "★ (기존) 시군구 못 뽑으면 시도로 판정")
    chk(GF._region_ok("광주 (북구)", "전남광주통합특별시 북구"),
        "★★ (기존) 통합표기라도 구가 같으면 통과")
    chk(GF._region_ok("광주광역시", "전남광주통합특별시 남구"),
        "★★ (기존) 통합표기 정보비대칭 구제 — round159 로직, 이번 수정으로도 살아있어야 한다")
    chk(not GF._region_ok("광주 북구", "전남광주통합특별시 서구"),
        "★★ (기존) 통합표기라도 구가 다르면 여전히 거른다")
    chk(GF._region_ok("대구", "대구광역시 동구"),
        "★★ (기존, round512) 대구(구 정보 없음) vs 대구광역시 동구 — 통과")
    chk(GF._region_ok("대구", "대구광역시 중구"), "★★ (기존, round512) 대구 vs 대구광역시 중구 — 통과")
    chk(GF._region_ok("대구", "대구"), "★ (기존, round512) 대구 vs 대구 — 통과")
    chk(not GF._region_ok("대구 동구", "대구광역시 서구"),
        "★★ (기존, round512) 대구 안에서도 구가 다르면 여전히 거른다")

    # ── 신규 — 여러 광역시가 나눠 쓰는 구 이름 4조합(고치기 전엔 전부 True) ──
    chk(not GF._region_ok("서울 중구 세종대로 110", "부산 중구 대청로 33"),
        "★★★★★ 서울 중구 ≠ 부산 중구 — 구 이름이 같아도 시도가 다르면 다른 동네(고치기 전 True)")
    chk(not GF._region_ok("대전 동구 대전로", "광주 동구 금남로"),
        "★★★★ 대전 동구 ≠ 광주 동구(고치기 전 True)")
    chk(not GF._region_ok("인천 서구 청라", "대구 서구 달구벌대로"),
        "★★★★ 인천 서구 ≠ 대구 서구(고치기 전 True)")
    chk(not GF._region_ok("울산 남구 삼산로", "부산 남구 못골로"),
        "★★★★ 울산 남구 ≠ 부산 남구(고치기 전 True)")

    # ── 대조군 — 같은 시도 안에서 다른 구를 우연히 안 막는지(과잉거름 아님) ──
    chk(GF._region_ok("서울 중구 세종대로 110", "서울 중구 태평로"),
        "★ 대조군 — 같은 시도 · 같은 구는 여전히 통과(과잉거름 아님)")
    chk(GF._region_ok("경기 성남시 분당구 판교로", "경기 성남시 분당구 대왕판교로"),
        "★ 대조군 — 같은 시도 · 같은 구, 도로명만 다름은 여전히 통과")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] _region_ok 실행", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 실제 geocode_fill.fill() + 스텁 ADDR.search (round267·512와 같은 기법)")
# ──────────────────────────────────────────────────────────────
import db as DB               # noqa: E402
import addr_search as ADDR    # noqa: E402

DB.init_db()
mark = "R649-" + secrets.token_hex(3)


def _fake_search_busan_for_seoul(q):
    """실제 카카오 응답을 흉내낸다 — 서울 중구 주소로 검색했는데 부산 중구
    좌표를 내주는 상황(도로명 모호성 등으로 드물게 일어날 수 있는 오검색)."""
    return [{"lat": 35.1000, "lng": 129.0403, "region": "부산광역시 중구",
             "road": "부산광역시 중구 대청로 33"}]


try:
    conn0 = DB.get_db()
    a_id = conn0.execute(
        "INSERT INTO partners(name,partner_type,major,category,region,address,status) "
        "VALUES(?,'시공사','조경','조경식재공사업',?,?,'활성')",
        (f"{mark}-A", "서울", "서울 중구 을지로 12")).lastrowid
    conn0.commit()
    conn0.close()

    _orig_search = ADDR.search
    ADDR.search = _fake_search_busan_for_seoul
    try:
        GF.fill("partners", 500, dry=False)
    finally:
        ADDR.search = _orig_search

    conn1 = DB.get_db()
    row_a = conn1.execute("SELECT lat, lng, geo_src FROM partners WHERE id=?", (a_id,)).fetchone()
    conn1.close()
    chk(row_a["lat"] is None and row_a["lng"] is None,
        "★★★★★ 서울 중구 협력사에 부산 중구 좌표가 저장되지 않는다"
        "(고치기 전엔 '동네 일치'로 오판해 그대로 저장됐다)", dict(row_a))
    chk(row_a["geo_src"] == GF.FAILED_SRC,
        f"geo_src가 '{GF.FAILED_SRC}'로 정상 기록된다(틀린 좌표로 '주소검색' 아님)", dict(row_a))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] 실제 fill() 실행", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌림-증명 — _region_ok()를 라운드649 이전 구현으로 되돌리면")
# ──────────────────────────────────────────────────────────────


def _old_region_ok(want, got):
    """라운드649 이전 구현 그대로(시도충돌 검사 없음) — 되돌림-증명 전용."""
    w, g = GF._gu_set(want), GF._gu_set(got)
    if w and g:
        if w & g:
            return True
        if GF._sido_set(want) & GF._sido_set(got):
            wg = {x for x in w if x.endswith("구")}
            gg = {x for x in g if x.endswith("구")}
            return bool(wg & gg) or (bool(wg) != bool(gg))
        return False
    return bool(GF._sido_set(want) & GF._sido_set(got))


try:
    # 되돌림 대상 함수 자체가 옛 결함을 실제로 재현하는지 먼저 자체 점검
    chk(_old_region_ok("서울 중구 세종대로 110", "부산 중구 대청로 33") is True,
        "★ 되돌림 대상 함수 자체가 서울 중구·부산 중구를 같은 동네로 오판한다(자체 점검)")

    _orig_region_ok = GF._region_ok
    GF._region_ok = _old_region_ok   # fill()은 _region_ok를 모듈 전역 이름으로 호출하므로 교체가 그대로 반영된다
    try:
        chk(GF._region_ok("서울 중구 세종대로 110", "부산 중구 대청로 33") is True,
            "★★★★★ 옛 코드(되돌림) — _region_ok()가 실제로 서울·부산 중구를 같은 동네로 오판한다"
            "(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명)")

        # 실제 fill() 엔드투엔드로도 재현 — 새 협력사 행으로(A행은 이미 시도실패로 낙인찍혀 재대상이 아니다)
        conn2 = DB.get_db()
        b_id = conn2.execute(
            "INSERT INTO partners(name,partner_type,major,category,region,address,status) "
            "VALUES(?,'시공사','조경','조경식재공사업',?,?,'활성')",
            (f"{mark}-B", "서울", "서울 중구 을지로 13")).lastrowid
        conn2.commit()
        conn2.close()

        _orig_search2 = ADDR.search
        ADDR.search = _fake_search_busan_for_seoul
        try:
            GF.fill("partners", 500, dry=False)
        finally:
            ADDR.search = _orig_search2

        conn3 = DB.get_db()
        row_b = conn3.execute(
            "SELECT lat, lng, geo_src FROM partners WHERE id=?", (b_id,)).fetchone()
        conn3.close()
        chk(row_b["lat"] == 35.1000 and row_b["geo_src"] == "주소검색",
            "★★★★★ 옛 코드(되돌림) — 실제 fill() 실행에서 서울 협력사에 부산 좌표가 "
            "'주소검색'(확인됨)으로 잘못 저장된다(진짜 결함 재현)", dict(row_b))
    finally:
        GF._region_ok = _orig_region_ok
    chk(GF._region_ok("서울 중구 세종대로 110", "부산 중구 대청로 33") is False,
        "★★★★★ 복원 확인 — GF._region_ok이 원래(고친) 구현으로 되돌아왔다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [4] 되돌림-증명", f"{type(e).__name__} {e}")
    try:
        GF._region_ok = _orig_region_ok
    except NameError:
        pass

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
