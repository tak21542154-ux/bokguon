# -*- coding: utf-8 -*-
"""스캔 653라운드 회귀(직접조사, 하위위임 없음) — geocode_fill.py _sido_set()이

  전남·전북·충남·충북·경남·경북 여섯 도의 **정식 명칭**('경상북도' 등)을 못 알아봐,
  [라운드649]가 막았던 "구 이름이 같아도 시도가 다르면 다른 동네" 검사를
  건너뛰게 만들던 결함.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

■ 배경 — round649/650이 이미 두 번 고친 바로 그 함수(_region_ok/_sido_set)에서
  세 번째 독립된 구멍을 찾았다. round649는 "구 이름만 같으면 시도를 안 본다",
  round650은 "시도 이름이 도로명 속에 경계 없이 부분일치한다"를 고쳤다. 이번은
  또 다른 원인 — _SIDO 정규식 자체가 축약형(전남·전북·충남·충북·경남·경북)만
  담고 **정식 명칭**('전라남도' 등)은 아예 인식하지 못한다.

  왜 이게 실제로 위험한가 — _region_ok()는 두 주소의 '구' 이름이 겹치면([라운드649]
  이후) 시도까지 서로 다른지 확인해야만 "같은 동네"로 본다. 그런데 정식 명칭 쪽
  문자열에서 _sido_set()이 빈 집합을 돌려주면(_SIDO가 못 알아보므로) 그 확인
  자체가 `if sw and sg and not (sw & sg)`에서 `sw`가 falsy라 건너뛰어지고
  그냥 True(같은 동네)로 떨어진다. '중구·동구·서구·남구·북구'는 서울·부산·
  대구·인천·광주·대전·울산·포항·창원·전주 등 전국 여러 도시가 나눠 쓰는 흔한
  이름이라, 정식 명칭으로 등록된 주소는 전부 이 구멍에 걸린다.

  실측(직접 재현, 순수함수 호출, 하위 상태 없음) — 고치기 전 코드로
    _region_ok("경상북도 포항시 남구 대잠동", "부산광역시 남구 대연동") == True
    _region_ok("전라남도 여수시 중앙동", "서울특별시 중구 태평로")       == True
    _region_ok("충청남도 천안시 동남구", "광주광역시 동구 금남로")       == True
    _region_ok("경상남도 창원시 성산구", "대구광역시 중구 동성로")       == True
  네 조합 전부 100km 넘게 떨어진 완전히 다른 도시를 "같은 동네"로 오판했다.
  이 모듈 docstring의 안전 원칙("엉뚱한 좌표는 없느니만 못하다")을 정면으로
  벗어난다. 실데이터 확인(운영 DB, 읽기전용 SELECT) — partners.address 73건이
  이미 이 여섯 도의 정식 명칭을 쓰고 있고(경상북도 15·경상남도 12·전라북도 10·
  전라남도 13·충청북도 9·충청남도 14), cases 테이블엔 region이 비어 있는데
  address만 있는 행도 실제로 존재한다(비-데모 78건 중 1건) — region 칸이
  공백이면 fill()의 want 문자열은 address 하나에만 의존하므로 이 구멍이
  그대로 열린다.

  왜 처음 두 라운드가 못 봤나 — 이 저장소의 기존 partners 행은 전부 region
  칸에 축약형('경북' 등)이 사람 손으로 이미 채워져 있어(운영 확인), want
  문자열이 "경북 경상북도 포항시…"처럼 region의 축약형과 address의 정식
  명칭이 겹쳐 있다 — region 쪽 축약형이 이미 우연히 정규식에 잡히므로 이
  구멍이 기존 데이터로는 재현되지 않는다. region이 비어 있거나(신규 등록·
  2트랙 접수) 아직 정리되지 않은 새 행에서만 실제로 터진다.

  고침(geocode_fill.py _sido_set(), 111~127행 부근) — db.REGION_LONG(정확히
  이 문제를 풀려고 이미 있는 표 — norm_regions()가 쓰는 것과 같다. 이 파일은
  순환임포트 걱정 없이 db를 이미 import한다, _gu_set()의 DB.SIDO 참고)으로
  정식 명칭을 먼저 축약형으로 바꾼 뒤, 기존 _SIDO 정규식은 그대로 쓴다.
  새 헬퍼·새 정규식 없음(ponytail 원칙, round512·649·650과 동일).
  geocode_fill.py 자신의 demo()에도 이 4케이스+대조군 2건을 추가했다.

  회귀테스트(이 파일) 신설 —
  [1] 소스 확인 — _sido_set()이 DB.REGION_LONG을 쓰고 라운드653 표식이 있다.
  [2] 실행 — demo()의 기존 자체점검 전부(회귀 없음 확인) + 신규 discriminating
      4케이스(포항·여수·천안·창원)를 _region_ok() 직접 호출로 확인.
  [3] 실행 — 실제 geocode_fill.fill()을 스크래치 DB + 스텁 ADDR.search(경상북도
      포항 협력사를 검색하면 부산 좌표를 내주는 가짜 카카오 응답, region 칸은
      비워 둔다 — 실데이터에서 실제로 일어나는 조건)로 끝까지 돌려, 고친
      코드에서는 그 틀린 좌표가 저장되지 않고 geo_src='시도실패'로 표시됨을
      확인(round267·512·649·650과 같은 기법).
  [4] 되돌림-증명 — GF._sido_set을 이 라운드 이전 구현(DB.REGION_LONG 정규화
      없음)으로 런타임에 되돌려(파일은 안 건드린다 — 함수 객체 교체라 안전)
      같은 시나리오를 새 협력사 행으로 다시 돌리면, 실제로 부산 좌표가 경북
      협력사에 geo_src='주소검색'으로 잘못 저장되는 옛 결함이 fill() 실행으로
      재현됨을 확인(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명).

      python test_scan_round653_fixes.py
"""
import io
import os
import sys
import secrets
import tempfile

#  ⚠⚠ 윈도 기본 콘솔은 cp949 라 '—'·'★' 같은 문자를 print 하면 UnicodeEncodeError
#    로 죽는다(check_orphan_chars.py 자신의 라운드124 교훈과 동일 — 점검 도구가
#    결과를 내기 직전에 죽으면 통과/실패를 전혀 알 수 없다).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
#  ⚠ db.py 의 운영DB 안전장치가 발동하려면, geocode_fill.py(import db)를
#    불러오기 **전에** 검증용 DB 경로부터 정해야 한다(round267·512·649·650과 동일 관례).
_tmpdir = tempfile.mkdtemp(prefix="round653_")
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
print("  스캔 653라운드 회귀 — geocode_fill._sido_set() 정식 명칭(전라남도 등) 미인식")
print("=" * 72)

GF_SRC = read("geocode_fill.py")

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — _sido_set()이 DB.REGION_LONG을 쓰고 라운드653 표식이 있다")
# ──────────────────────────────────────────────────────────────
_fn_start = GF_SRC.index("\ndef _sido_set(")
_fn_end = GF_SRC.index("\n\n\n", _fn_start)
_fn_block = GF_SRC[_fn_start:_fn_end]

chk("DB.REGION_LONG" in _fn_block, "★★★★★ _sido_set()이 DB.REGION_LONG으로 정식 명칭을 축약한다")
chk("[라운드653]" in _fn_block, "_sido_set() 안에 라운드653 표식이 있다")
chk(GF_SRC.count("\ndef _sido_set(") == 1, "_sido_set() 정의가 정확히 1번만 있다(중복 정의 없음)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — _region_ok() 직접 호출(같은 프로세스, 기존 demo() 전부 + 신규)")
# ──────────────────────────────────────────────────────────────
import geocode_fill as GF  # noqa: E402

try:
    GF.demo()   # 파일 자신의 자체점검 — round159·512·649·650 회귀 케이스 전부 포함
    chk(True, "★ (기존) geocode_fill.demo() 전체 자체점검 회귀 없음")
except AssertionError as e:
    chk(False, "★★★ (기존) geocode_fill.demo() 회귀", str(e))

try:
    # ── 신규 — 정식 명칭 4케이스(고치기 전엔 전부 True) ──
    chk(not GF._region_ok("경상북도 포항시 남구 대잠동", "부산광역시 남구 대연동"),
        "★★★★★ '경상북도'(정식 명칭) 포항이 '부산광역시' 남구와 같은 동네로 새면 안 된다"
        "(고치기 전 True, 두 도시는 100km 이상 떨어져 있다)")
    chk(not GF._region_ok("전라남도 여수시 중앙동", "서울특별시 중구 태평로"),
        "★★★★ '전라남도' 여수가 서울 중구로 새면 안 된다(고치기 전 True)")
    chk(not GF._region_ok("충청남도 천안시 동남구", "광주광역시 동구 금남로"),
        "★★★★ '충청남도' 천안이 광주 동구로 새면 안 된다(고치기 전 True)")
    chk(not GF._region_ok("경상남도 창원시 성산구", "대구광역시 중구 동성로"),
        "★★★★ '경상남도' 창원이 대구 중구로 새면 안 된다(고치기 전 True)")
    # ── 대조군 — 정식 명칭과 축약형이 같은 도를 가리키면 여전히 통과(과잉거름 아님) ──
    chk(GF._region_ok("경상북도 포항시 남구 대잠동", "경북 포항시 남구"),
        "★ 대조군 — 정식 명칭 vs 축약형, 같은 도(경북)는 여전히 통과")
    chk(GF._region_ok("전라남도 목포시 용해동", "전남 목포시"),
        "★ 대조군 — 정식 명칭 vs 축약형, 같은 도(전남)는 여전히 통과")
    chk(GF._region_ok("서울 중구 세종대로 110", "세종특별자치시 반곡동 108") is False,
        "★ 회귀없음 — round650의 '세종대로' 방어는 그대로 살아 있다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] _region_ok 실행", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 실제 geocode_fill.fill() + 스텁 ADDR.search (round267·512·649·650과 같은 기법)")
# ──────────────────────────────────────────────────────────────
import db as DB               # noqa: E402
import addr_search as ADDR    # noqa: E402

DB.init_db()
mark = "R653-" + secrets.token_hex(3)


def _fake_search_busan_for_pohang(q):
    """실제 카카오 응답을 흉내낸다 — 경북 포항 '남구' 주소로 검색했는데
    부산 '남구' 좌표를 내주는 상황(구 이름이 흔해 드물게 일어날 수 있는
    오검색). 두 도시는 100km 이상 떨어져 있다."""
    return [{"lat": 35.1359, "lng": 129.0996, "region": "부산광역시",
             "road": "부산광역시 남구 대연동"}]


try:
    conn0 = DB.get_db()
    #  ⚠ region 칸은 일부러 비워 둔다 — 실데이터 확인 결과 이 저장소의 기존
    #    행은 전부 region에 축약형이 이미 채워져 있어(운영 SELECT로 확인)
    #    이 구멍이 우연히 안 터진다. region이 비어 있는 신규/2트랙 행에서
    #    실제로 터지므로, 재현도 그 조건 그대로 맞춘다(cases 테이블 실측:
    #    비-데모 78건 중 1건이 이미 이 모양 — region 공백 + address만 있음).
    a_id = conn0.execute(
        "INSERT INTO partners(name,partner_type,major,category,region,address,status) "
        "VALUES(?,'시공사','조경','조경식재공사업','','경상북도 포항시 남구 대잠동','활성')",
        (f"{mark}-A",)).lastrowid
    conn0.commit()
    conn0.close()

    _orig_search = ADDR.search
    ADDR.search = _fake_search_busan_for_pohang
    try:
        GF.fill("partners", 500, dry=False)
    finally:
        ADDR.search = _orig_search

    conn1 = DB.get_db()
    row_a = conn1.execute("SELECT lat, lng, geo_src FROM partners WHERE id=?", (a_id,)).fetchone()
    conn1.close()
    chk(row_a["lat"] is None and row_a["lng"] is None,
        "★★★★★ 경북 포항 협력사(region 공백)에 부산 좌표가 저장되지 않는다"
        "(고치기 전엔 '동네 일치'로 오판해 그대로 저장됐다)", dict(row_a))
    chk(row_a["geo_src"] == GF.FAILED_SRC,
        f"geo_src가 '{GF.FAILED_SRC}'로 정상 기록된다(틀린 좌표로 '주소검색' 아님)", dict(row_a))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] 실제 fill() 실행", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌림-증명 — GF._sido_set을 라운드653 이전 구현(정식 명칭 정규화 없음)으로 되돌리면")
# ──────────────────────────────────────────────────────────────
def _old_sido_set(s):
    return set(GF._SIDO.findall(s or ""))


try:
    # 되돌림 대상 함수 자체가 옛 결함을 실제로 재현하는지 먼저 자체 점검
    chk(_old_sido_set("경상북도 포항시 남구 대잠동") == set(),
        "★ 되돌림 대상 함수 자체가 '경상북도'(정식 명칭)에서 시도를 못 뽑는다(자체 점검)")

    _orig_sido_set = GF._sido_set
    GF._sido_set = _old_sido_set  # _region_ok()는 _sido_set을 모듈 전역 이름으로 참조하므로 교체가 그대로 반영된다
    try:
        chk(GF._region_ok("경상북도 포항시 남구 대잠동", "부산광역시 남구 대연동") is True,
            "★★★★★ 옛 코드(되돌림) — _region_ok()가 실제로 포항·부산을 같은 동네로 오판한다"
            "(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명)")

        # 실제 fill() 엔드투엔드로도 재현 — 새 협력사 행으로(A행은 이미 시도실패로 낙인찍혀 재대상이 아니다)
        conn2 = DB.get_db()
        b_id = conn2.execute(
            "INSERT INTO partners(name,partner_type,major,category,region,address,status) "
            "VALUES(?,'시공사','조경','조경식재공사업','','경상북도 포항시 남구 대잠동2','활성')",
            (f"{mark}-B",)).lastrowid
        conn2.commit()
        conn2.close()

        _orig_search2 = ADDR.search
        ADDR.search = _fake_search_busan_for_pohang
        try:
            GF.fill("partners", 500, dry=False)
        finally:
            ADDR.search = _orig_search2

        conn3 = DB.get_db()
        row_b = conn3.execute(
            "SELECT lat, lng, geo_src FROM partners WHERE id=?", (b_id,)).fetchone()
        conn3.close()
        chk(row_b["lat"] == 35.1359 and row_b["geo_src"] == "주소검색",
            "★★★★★ 옛 코드(되돌림) — 실제 fill() 실행에서 경북 협력사에 부산 좌표가 "
            "'주소검색'(확인됨)으로 잘못 저장된다(진짜 결함 재현)", dict(row_b))
    finally:
        GF._sido_set = _orig_sido_set
    chk(GF._region_ok("경상북도 포항시 남구 대잠동", "부산광역시 남구 대연동") is False,
        "★★★★★ 복원 확인 — GF._sido_set이 원래(고친) 구현으로 되돌아왔다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [4] 되돌림-증명", f"{type(e).__name__} {e}")
    try:
        GF._sido_set = _orig_sido_set
    except NameError:
        pass

APP_HASH_AFTER = read("geocode_fill.py")
chk(APP_HASH_AFTER == GF_SRC,
    "★★★★★ geocode_fill.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(모듈 함수 속성 직접치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
