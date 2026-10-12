# -*- coding: utf-8 -*-
"""스캔 512라운드 회귀 — geocode_fill.py _gu_set()가 '대구'를 구 단위 지명으로
   오판해, 구 정보 없이 등록된 대구 협력사·사건의 좌표를 영영 못 채우게(동네
   불일치로 오판 → geo_src='시도실패' 고정) 만들던 결함.

  직접 조사(하위위임 없음) — run_all_tests.py 전체를 정독해 포화된 축(형제
  엔드포인트 잠금 비대칭 504~507, 정책문서 불일치 289·317·508, website 저장형
  XSS 509·510, dispatch.py 지역열쇠 파싱 511)과 안 겹치는 각도를 찾다가,
  라운드511이 고친 dispatch.py _region_key()와 정확히 같은 클래스의 결함
  ("대구"는 시/도 이름 자체의 마지막 글자가 우연히 '구'다)이 이 파일과는
  아무 관계 없는 **별개의 재구현**인 geocode_fill.py _gu_set()/_region_ok()에도
  전파돼 있는지 직접 대조해 발견했다. geocode_fill.py는 geo.py도 dispatch.py도
  import하지 않는 독자 모듈이라(자체 정규식으로 시·군·구를 추출), 라운드511의
  수정이 이 파일에는 전혀 반영되지 않았다.

  결함 — _gu_set(s)는 문자열에서 `[가-힣]{1,5}[시군구]` 패턴을 전부 뽑아
  "그 문자열이 가리키는 구/시/군 이름 집합"으로 쓴다. 그런데 '대구'(광역시)는
  이름 자체가 '대'+'구' 두 글자라, 구 단위 접미어 판정에 그대로 걸려 마치
  '대'라는 한 글자 구가 있는 것처럼(정확히는 '대구' 전체가 구 단위 지명인
  것처럼) 오판된다. 등록 지역이 '대구'뿐이고 주소도 구 이름을 반복하지 않는
  협력사·사건은 _region_ok()의 "구 정보가 없으면 시/도로 판정한다"는 자신의
  폴백 원칙(데모 자체점검의 '서울'→'서울 송파구' 사례가 이미 보장하는 바로 그
  원칙)이 이 오판 때문에 막혀, 실제로는 같은 도시인 검색 결과("대구광역시
  동구" 등)까지 서로 다른 구("대구" vs "동구")로 보고 '동네 불일치'로 걸러
  버린다 — geocode_fill.py가 그러면 해당 행을 geo_src='시도실패'로 표시해
  버려서(FAILED_SRC) 재실행해도 다시는 시도조차 안 한다.

  실측(직접 재현, 순수함수 호출) — _region_ok("대구","대구광역시 동구") == False
  (다른 16개 시/도는 전부 구/시/군으로 안 끝나 이 함정에 안 걸린다 — 라운드511과
  동일한 유일 충돌 지점). 운영 DB 읽기전용 조회 결과, 이 저장소의 기존 데이터는
  '대구'만 적은 7곳 모두 주소 칸에 '대구광역시'가 함께 적혀 있어(_region_ok가
  region과 address를 이어붙여 판정하므로, 주소 쪽의 '대구광역시'·구 이름이
  직접일치를 만들어) 우연히 이 함정을 피해 갔을 뿐 — 주소가 도로명만 적고
  시/구를 반복하지 않는 최초의 대구 신규 등록(예: 지사만 '대구'로 적고 도로명
  주소만 넣는 경우, 실데이터에 이미 이런 지사표기 사례가 있다)부터 바로
  재현된다. 이 실행결과([3])는 그 상황을 실제 fill()로 재현한다.

  고침 — db.SIDO(라운드511이 dispatch.py에 쓴 것과 같은 기존 상수, 이 파일도
  이미 `import db as DB`로 참조 가능)에 정확히 일치하는 토큰은 _gu_set()의
  결과에서 제외한다. 새 헬퍼·새 상수를 만들지 않고 기존 상수를 재사용한다
  (ponytail 원칙 — round511과 동일). '대구' 외 16개 시/도는 애초에 구/시/군으로
  안 끝나 이 제외가 없어도 안전했으므로 회귀 없이 '대구' 한 곳만 고쳐진다.

  [1] 소스 확인 — 새 코드가 _gu_set() 본문에 정확히 한 번 있다.
  [2] 실행 — 같은 프로세스에서 _region_ok()를 대구 4variant + 기존 자체점검
      8건(demo()와 동일)으로 직접 호출해 대구만 고쳐지고 나머지는 회귀 없음을
      확인.
  [3] 실행 — 실제 geocode_fill.fill()을 스크래치 DB + 스텁 ADDR.search로 끝까지
      돌려, 구 정보 없이 '대구'만 등록된 협력사의 좌표가 실제로 채워지는지
      확인(round267이 확립한 fill() 엔드투엔드 검증 기법 그대로).
  [4] 되돌림-증명 — _gu_set()을 이 라운드 이전 구현(SIDO 제외 없음)으로 런타임에
      되돌려(파일은 안 건드린다 — DB·세션 등 외부상태가 없는 순수 함수라 안전,
      _region_ok()는 _gu_set을 모듈 전역 이름으로 호출하므로 교체가 그대로
      반영된다) 같은 시나리오를 새 협력사 행으로 다시 돌리면, 실제로
      geo_src='시도실패'로 잘못 낙인찍혀 좌표가 영영 안 채워지는 옛 결함이
      fill() 실행으로 재현됨을 확인.

      python test_scan_round512_fixes.py
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
#    불러오기 **전에** 검증용 DB 경로부터 정해야 한다(round267과 동일 관례).
_tmpdir = tempfile.mkdtemp(prefix="round512_")
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
print("  스캔 512라운드 회귀 — geocode_fill._gu_set() '대구' 오판(동네 불일치)")
print("=" * 72)

GF_SRC = read("geocode_fill.py")

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — _gu_set() 본문에 새 코드가 정확히 한 번")
# ──────────────────────────────────────────────────────────────
_start = GF_SRC.index("def _gu_set(")
_rest = GF_SRC[_start:]
_end_rel = _rest.index("\n\ndef ", 1)
gs_body = _rest[:_end_rel] if _end_rel > 0 else _rest

NEW_LINE = "if x not in DB.SIDO"
chk(gs_body.count(NEW_LINE) == 1,
    "★★★ SIDO 제외 처리가 _gu_set() 본문 안에 정확히 1번 있다", gs_body.count(NEW_LINE))
chk("[라운드512]" in gs_body, "_gu_set() 안에 라운드512 표식이 있다")
chk(GF_SRC.count("def _gu_set(") == 1, "_gu_set() 정의가 정확히 1번만 있다(중복 정의 없음)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — _region_ok() 직접 호출(같은 프로세스, 기존 자체점검 8건 + 신규)")
# ──────────────────────────────────────────────────────────────
import geocode_fill as GF  # noqa: E402

try:
    # ── 기존 자체점검(demo()) 8건 — 회귀 없이 그대로 유지되는가 ──
    chk(GF._region_ok("서울 송파구 올림픽로", "서울 송파구"), "★ (기존) 같은 구는 통과")
    chk(GF._region_ok("경기 성남시 분당구", "경기 성남시"), "★ (기존) 시군구 일부일치 통과")
    chk(not GF._region_ok("서울 송파구", "서울 강남구"), "★ (기존) 다른 구는 거른다")
    chk(not GF._region_ok("서울 송파구", "부산 해운대구"), "★ (기존) 다른 시도·다른 구는 거른다")
    chk(GF._region_ok("서울", "서울 송파구"), "★ (기존) 시군구 못 뽑으면 시도로 판정")
    chk(GF._region_ok("광주 (북구)", "전남광주통합특별시 북구"),
        "★★ (기존) 통합표기라도 구가 같으면 통과")
    chk(GF._region_ok("광주광역시", "전남광주통합특별시 남구"),
        "★★ (기존) 통합표기 정보비대칭 구제 — 이번 수정으로도 계속 살아있어야 한다")
    chk(not GF._region_ok("광주 북구", "전남광주통합특별시 서구"),
        "★★ (기존) 통합표기라도 구가 다르면 여전히 거른다")

    # ── 신규 — '대구'(구 정보 없음)도 같은 도시면 이제 통과(고치기 전엔 전부 거름) ──
    chk(GF._region_ok("대구", "대구광역시 동구"),
        "★★★★★ 대구(구 정보 없음) vs 대구광역시 동구 — 이제 통과(고치기 전엔 '동네 불일치')")
    chk(GF._region_ok("대구", "대구광역시 중구"),
        "★★★★ 대구(구 정보 없음) vs 대구광역시 중구 — 이제 통과")
    chk(GF._region_ok("대구", "대구"), "★★★ 대구 vs 대구(양쪽 다 구 정보 없음) — 통과")
    chk(GF._region_ok("대구(전국 출장)", "대구광역시 수성구"),
        "★★★ 실데이터 표기('대구(전국 출장)') 그대로도 통과")

    # ── 대조군 — 대구 안에서 구가 다르면 여전히 거른다(과잉통과 아님) ──
    chk(not GF._region_ok("대구 동구", "대구광역시 서구"),
        "★★★ 대구 안에서도 구가 다르면 여전히 거른다(과잉통과 아님)")
    chk(not GF._region_ok("대구 중구", "부산광역시 해운대구"),
        "★ 대조군 — 대구와 부산은 당연히 다른 동네다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] _region_ok 실행", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 실제 geocode_fill.fill() + 스텁 ADDR.search (round267과 같은 기법)")
# ──────────────────────────────────────────────────────────────
import importlib
import db as DB               # noqa: E402
import addr_search as ADDR    # noqa: E402

DB.init_db()
mark = "R512-" + secrets.token_hex(3)


def _fake_search_daegu(q):
    """실제 카카오 응답을 흉내낸다 — region은 구조화된 시도+구, road는 도로명뿐
    (등록 주소가 '대구'만 적고 구를 반복하지 않는 실데이터 패턴을 그대로 재현)."""
    return [{"lat": 35.8836796418659, "lng": 128.6318, "region": "대구광역시 동구",
             "road": "대구광역시 동구 팔공로 43"}]


try:
    conn0 = DB.get_db()
    a_id = conn0.execute(
        "INSERT INTO partners(name,partner_type,major,category,region,address,status) "
        "VALUES(?,'시공사','조경','조경식재공사업',?,?,'활성')",
        (f"{mark}-A", "대구", "대구 팔공로 43")).lastrowid
    conn0.commit()
    conn0.close()

    _orig_search = ADDR.search
    ADDR.search = _fake_search_daegu
    try:
        GF.fill("partners", 500, dry=False)
    finally:
        ADDR.search = _orig_search

    conn1 = DB.get_db()
    row_a = conn1.execute("SELECT lat, lng, geo_src FROM partners WHERE id=?", (a_id,)).fetchone()
    conn1.close()
    chk(row_a["lat"] is not None and row_a["lng"] is not None,
        "★★★★★ 구 정보 없이 '대구'만 등록된 협력사도 실제 fill()로 좌표가 채워진다"
        "(고치기 전엔 '동네 불일치'로 걸러져 영영 안 채워졌다)", dict(row_a))
    chk(row_a["geo_src"] == "주소검색",
        "geo_src가 '주소검색'으로 정상 기록된다(시도실패 아님)", dict(row_a))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] 실제 fill() 실행", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌림-증명 — _gu_set()을 라운드512 이전 구현으로 되돌리면")
# ──────────────────────────────────────────────────────────────


def _old_gu_set(s):
    """라운드512 이전 구현 그대로(SIDO 제외 없음) — 되돌림-증명 전용."""
    t = " " + re.sub(r"[^가-힣]+", " ", s or "")
    return set(re.findall(r"(?<=\s)([가-힣]{1,5}[시군구])", t))


try:
    # 되돌림 대상 함수 자체가 옛 결함을 실제로 재현하는지 먼저 자체 점검
    old_w = _old_gu_set("대구")
    chk(old_w == {"대구"},
        "★ 되돌림 대상 함수 자체가 '대구'를 구 단위 지명으로 오판한다(자체 점검)", old_w)

    _orig_gu_set = GF._gu_set
    GF._gu_set = _old_gu_set   # _region_ok()는 _gu_set을 모듈 전역 이름으로 호출하므로 교체가 그대로 반영된다
    try:
        chk(GF._region_ok("대구", "대구광역시 동구") is False,
            "★★★★★ 옛 코드(되돌림) — _region_ok()가 실제로 '동네 불일치'로 오판한다"
            "(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명)")

        # 실제 fill() 엔드투엔드로도 재현 — 새 협력사 행으로(A행은 이미 채워져 재대상이 아니다)
        conn2 = DB.get_db()
        b_id = conn2.execute(
            "INSERT INTO partners(name,partner_type,major,category,region,address,status) "
            "VALUES(?,'시공사','조경','조경식재공사업',?,?,'활성')",
            (f"{mark}-B", "대구", "대구 팔공로 44")).lastrowid
        conn2.commit()
        conn2.close()

        _orig_search2 = ADDR.search
        ADDR.search = _fake_search_daegu
        try:
            GF.fill("partners", 500, dry=False)
        finally:
            ADDR.search = _orig_search2

        conn3 = DB.get_db()
        row_b = conn3.execute(
            "SELECT lat, lng, geo_src FROM partners WHERE id=?", (b_id,)).fetchone()
        conn3.close()
        chk(row_b["lat"] is None and row_b["geo_src"] == "시도실패",
            "★★★★★ 옛 코드(되돌림) — 실제 fill() 실행에서도 같은 도시 협력사가 "
            "'시도실패'로 영구 낙인찍혀 좌표를 못 채운다(진짜 결함 재현)", dict(row_b))
    finally:
        GF._gu_set = _orig_gu_set
    chk(GF._region_ok("대구", "대구광역시 동구") is True,
        "★★★★★ 복원 확인 — GF._gu_set이 원래(고친) 구현으로 되돌아왔다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [4] 되돌림-증명", f"{type(e).__name__} {e}")
    try:
        GF._gu_set = _orig_gu_set
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
