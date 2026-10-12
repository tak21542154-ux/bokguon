# -*- coding: utf-8 -*-
"""스캔 650라운드 회귀(직접조사, 하위위임 없음) — geocode_fill.py _sido_set()의

  경계 없는 부분일치가 '세종로'·'세종대로'(서울 도로명) 안의 '세종'을
  세종특별자치시로 오판하던 결함.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

  직접 조사(하위위임 없음) — round649가 남긴 후속 후보 중 하나(오케스트레이팅
  세션이 round649 검증 중 직접 짚은 것)를 확인했다: _SIDO 정규식
  `(서울|부산|...|세종|...)`가 문자열 경계 없이 부분일치(findall)한다.
  '세종대로'(서울시청 앞 도로명)·'세종로'(광화문 앞 도로명)는 '세종'으로
  시작하지만 세종특별자치시와 무관한데, 경계 검사가 없어 그대로 '세종'으로
  잡힌다.

  왜 이게 실제로 위험한가 — _region_ok() 맨 아래 갈래("시군구를 못 뽑으면
  시도라도 맞아야 한다")는 두 문자열 중 하나라도 _gu_set()이 빈 집합일 때
  실행된다. 세종특별자치시는 애초에 '구' 자체가 없는 단일 행정단위라
  실주소(예: '세종특별자치시 반곡동 108')는 거의 항상 _gu_set()이 비어 이
  갈래를 탄다. 그 상태에서 '세종대로'의 가짜 '세종'이 진짜 세종시의 '세종'과
  겹쳐 완전히 다른 도시(서울 중구 vs 세종시, 약 120km)를 "같은 동네"로 통과
  시킨다.

  실측(직접 재현, 순수함수 호출, 하위 상태 없음) — 고치기 전 코드로
    _region_ok("서울 중구 세종대로 110", "세종특별자치시 반곡동 108") == True
    _region_ok("서울 종로구 세종로 1", "세종특별자치시 나성동 1")     == True
    _region_ok("서울 송파구 경기장길 10", "경기도")                  == True
  세 조합 전부 "같은 동네"로 오판했다(첫 두 개는 세종/서울, 세 번째는
  '경기장길'의 '경기'가 경기도로 오판되는 같은 함정의 다른 사례).
  이 모듈 docstring의 안전 원칙("엉뚱한 좌표는 없느니만 못하다")을 정면으로
  벗어난다 — round649와 같은 종류(위험 방향 실패: 못 채우는 게 아니라
  틀리게 채운다)지만 원인은 다른 함수(_region_ok 자체가 아니라 그 하위
  의존인 _sido_set/_SIDO)다.

  고침 — _SIDO 정규식에 lookahead 경계를 추가했다. 시도 이름 뒤에 문자열
  끝 · 비한글 문자 · 실제 행정단위 접미('시'·'도'·'특별'·'광역'·'통합') ·
  또 다른 시도 이름(기존 '전남광주통합…' 결합 표기 지원 유지)이 이어질
  때만 인정한다. 새 헬퍼·새 상수 없이 기존 _SIDO 컴파일 정규식 자체를
  넓혔다(ponytail 원칙, round512·649와 동일). 361→392줄(+31, 대부분
  근거 주석 + demo() 회귀 케이스 3건 추가).

  회귀테스트(이 파일) 신설 —
  [1] 소스 확인 — _SIDO 정의에 lookahead(`(?=`)와 라운드650 표식이 있다.
  [2] 실행 — demo()의 기존 자체점검 전부(회귀 없음 확인) + 신규 discriminating
      3케이스(세종대로·세종로·경기장길)를 _region_ok() 직접 호출로 확인.
  [3] 실행 — 실제 geocode_fill.fill()을 스크래치 DB + 스텁 ADDR.search(서울
      중구 '세종대로' 협력사를 검색하면 진짜 세종시 좌표를 내주는 가짜
      카카오 응답)로 끝까지 돌려, 고친 코드에서는 그 틀린 좌표가 저장되지
      않고 geo_src='시도실패'로 표시됨을 확인(round267·512·649와 같은 기법).
  [4] 되돌림-증명 — GF._SIDO를 이 라운드 이전 정규식(경계 없음)으로 런타임에
      되돌려(파일은 안 건드린다 — 컴파일된 패턴 객체 교체라 안전) 같은
      시나리오를 새 협력사 행으로 다시 돌리면, 실제로 세종시 좌표가 서울
      협력사에 geo_src='주소검색'으로 잘못 저장되는 옛 결함이 fill() 실행으로
      재현됨을 확인(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명).

      python test_scan_round650_fixes.py
"""
import io
import os
import re
import secrets
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
#  ⚠ db.py 의 운영DB 안전장치가 발동하려면, geocode_fill.py(import db)를
#    불러오기 **전에** 검증용 DB 경로부터 정해야 한다(round267·512·649와 동일 관례).
_tmpdir = tempfile.mkdtemp(prefix="round650_")
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
print("  스캔 650라운드 회귀 — geocode_fill._sido_set() 도로명 부분일치 오판")
print("=" * 72)

GF_SRC = read("geocode_fill.py")

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — _SIDO 정의에 경계 lookahead와 라운드650 표식")
# ──────────────────────────────────────────────────────────────
_sido_start = GF_SRC.index("_SIDO = re.compile(")
_sido_block = GF_SRC[_sido_start:GF_SRC.index("\n\n\n", _sido_start)]

chk("(?=" in _sido_block, "★★★ _SIDO 정규식에 lookahead 경계가 추가됐다")
chk("[라운드650]" in GF_SRC[:_sido_start], "_SIDO 위 주석에 라운드650 표식이 있다")
chk(GF_SRC.count("_SIDO = re.compile(") == 1, "_SIDO 정의가 정확히 1번만 있다(중복 정의 없음)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — _region_ok() 직접 호출(같은 프로세스, 기존 demo() 전부 + 신규)")
# ──────────────────────────────────────────────────────────────
import geocode_fill as GF  # noqa: E402

try:
    GF.demo()   # 파일 자신의 자체점검 — round159·512·649 회귀 케이스 전부 포함
    chk(True, "★ (기존) geocode_fill.demo() 전체 자체점검 회귀 없음")
except AssertionError as e:
    chk(False, "★★★ (기존) geocode_fill.demo() 회귀", str(e))

try:
    # ── 신규 — 도로명 속 가짜 시도명 3케이스(고치기 전엔 전부 True) ──
    chk(not GF._region_ok("서울 중구 세종대로 110", "세종특별자치시 반곡동 108"),
        "★★★★★ '세종대로'의 '세종'이 진짜 세종시로 오판되면 안 된다(고치기 전 True)")
    chk(not GF._region_ok("서울 종로구 세종로 1", "세종특별자치시 나성동 1"),
        "★★★★ '세종로'도 마찬가지 — 서울 도로명일 뿐 세종시가 아니다(고치기 전 True)")
    chk(not GF._region_ok("서울 송파구 경기장길 10", "경기도"),
        "★★★★ '경기장길'의 '경기'가 경기도로 오판되면 안 된다(고치기 전 True)")
    # ── 대조군 — 진짜 세종시끼리, 진짜 서울끼리는 여전히 통과(과잉거름 아님) ──
    chk(GF._region_ok("세종특별자치시 반곡동", "세종시 반곡동 123"),
        "★ 대조군 — 진짜 세종시 vs 세종시는 여전히 통과")
    chk(GF._region_ok("서울 중구 세종대로 110", "서울특별시 중구 세종대로"),
        "★ 대조군 — 같은 '세종대로'끼리(둘 다 서울)는 여전히 통과")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] _region_ok 실행", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 실제 geocode_fill.fill() + 스텁 ADDR.search (round267·512·649와 같은 기법)")
# ──────────────────────────────────────────────────────────────
import db as DB               # noqa: E402
import addr_search as ADDR    # noqa: E402

DB.init_db()
mark = "R650-" + secrets.token_hex(3)


def _fake_search_sejong_for_seoul(q):
    """실제 카카오 응답을 흉내낸다 — 서울 '세종대로' 주소로 검색했는데
    진짜 세종시 좌표를 내주는 상황(도로명 모호성 등으로 드물게 일어날 수
    있는 오검색). 세종시는 구가 없어 region/road 어디에도 '구'가 안 잡힌다."""
    return [{"lat": 36.4800, "lng": 127.2890, "region": "세종특별자치시",
             "road": "세종특별자치시 반곡동 108"}]


try:
    conn0 = DB.get_db()
    a_id = conn0.execute(
        "INSERT INTO partners(name,partner_type,major,category,region,address,status) "
        "VALUES(?,'시공사','조경','조경식재공사업',?,?,'활성')",
        (f"{mark}-A", "서울", "서울 중구 세종대로 110")).lastrowid
    conn0.commit()
    conn0.close()

    _orig_search = ADDR.search
    ADDR.search = _fake_search_sejong_for_seoul
    try:
        GF.fill("partners", 500, dry=False)
    finally:
        ADDR.search = _orig_search

    conn1 = DB.get_db()
    row_a = conn1.execute("SELECT lat, lng, geo_src FROM partners WHERE id=?", (a_id,)).fetchone()
    conn1.close()
    chk(row_a["lat"] is None and row_a["lng"] is None,
        "★★★★★ 서울 '세종대로' 협력사에 세종시 좌표가 저장되지 않는다"
        "(고치기 전엔 '동네 일치'로 오판해 그대로 저장됐다)", dict(row_a))
    chk(row_a["geo_src"] == GF.FAILED_SRC,
        f"geo_src가 '{GF.FAILED_SRC}'로 정상 기록된다(틀린 좌표로 '주소검색' 아님)", dict(row_a))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] 실제 fill() 실행", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌림-증명 — GF._SIDO를 라운드650 이전 정규식(경계 없음)으로 되돌리면")
# ──────────────────────────────────────────────────────────────
_OLD_SIDO = re.compile(r"(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|"
                       r"전북|전남|경북|경남|제주)")

try:
    # 되돌림 대상 정규식 자체가 옛 결함을 실제로 재현하는지 먼저 자체 점검
    chk(set(_OLD_SIDO.findall("서울 중구 세종대로 110")) == {"서울", "세종"},
        "★ 되돌림 대상 정규식 자체가 '세종대로'에서 가짜 '세종'을 뽑는다(자체 점검)")

    _orig_sido = GF._SIDO
    GF._SIDO = _OLD_SIDO   # _sido_set()은 _SIDO를 모듈 전역 이름으로 참조하므로 교체가 그대로 반영된다
    try:
        chk(GF._region_ok("서울 중구 세종대로 110", "세종특별자치시 반곡동 108") is True,
            "★★★★★ 옛 코드(되돌림) — _region_ok()가 실제로 서울·세종시를 같은 동네로 오판한다"
            "(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명)")

        # 실제 fill() 엔드투엔드로도 재현 — 새 협력사 행으로(A행은 이미 시도실패로 낙인찍혀 재대상이 아니다)
        conn2 = DB.get_db()
        b_id = conn2.execute(
            "INSERT INTO partners(name,partner_type,major,category,region,address,status) "
            "VALUES(?,'시공사','조경','조경식재공사업',?,?,'활성')",
            (f"{mark}-B", "서울", "서울 중구 세종대로 111")).lastrowid
        conn2.commit()
        conn2.close()

        _orig_search2 = ADDR.search
        ADDR.search = _fake_search_sejong_for_seoul
        try:
            GF.fill("partners", 500, dry=False)
        finally:
            ADDR.search = _orig_search2

        conn3 = DB.get_db()
        row_b = conn3.execute(
            "SELECT lat, lng, geo_src FROM partners WHERE id=?", (b_id,)).fetchone()
        conn3.close()
        chk(row_b["lat"] == 36.4800 and row_b["geo_src"] == "주소검색",
            "★★★★★ 옛 코드(되돌림) — 실제 fill() 실행에서 서울 협력사에 세종시 좌표가 "
            "'주소검색'(확인됨)으로 잘못 저장된다(진짜 결함 재현)", dict(row_b))
    finally:
        GF._SIDO = _orig_sido
    chk(GF._region_ok("서울 중구 세종대로 110", "세종특별자치시 반곡동 108") is False,
        "★★★★★ 복원 확인 — GF._SIDO가 원래(고친) 정규식으로 되돌아왔다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [4] 되돌림-증명", f"{type(e).__name__} {e}")
    try:
        GF._SIDO = _orig_sido
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
