# -*- coding: utf-8 -*-
"""스캔 120라운드 회귀 — 지오코더 오른쪽 경계 누락(도로명 오매칭), 현장지도가
   저장좌표를 버리고 재추측, 계좌 복호화 실패 완전침묵.

  [1] geo.py _word_in() 이 왼쪽 경계만 봐서, '동해대로'처럼 실제로는 무관한
      도로명이 그 앞부분('동해')만으로 강원도 동해시로 오인됐다 — 실측
      경북 영덕·삼척이 각각 최대 125km·9.5km 벗어남(주소에 정답 지명이
      그대로 있어도 무시됐다).
  [2] api_map_cases 가 partners.lat/lng(geocode_fill.py 가 검증해 채운
      실주소 좌표, 활성업체 91% 보유)를 SELECT 만 하고 쓰지 않아, 형제인
      api_case_nearby 와 다른 좌표 소스로 지도를 그렸다 — 결함1에도
      그대로 노출됐다.
  [3] crypto_util.decrypt() 가 실패를 로그 없이 통째로 삼켜, 키 교체
      누락 같은 사고가 나도 알아챌 방법이 없었다.

      python test_scan_round120_fixes.py
"""
import io
import logging
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


GEO_SRC = read("geo.py")
APP_SRC = read("app.py")

print("═" * 72)
print("  스캔 120라운드 회귀 — 지오코더 오른쪽경계·지도 저장좌표 무시·복호화 침묵")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
chk("_ADMIN_SUFFIX" in GEO_SRC, "★★★ geo.py 가 행정단위 접미어 화이트리스트를 쓴다")
wi_body = _py_fn_body(GEO_SRC, "_word_in")
chk("left_ok" in wi_body and "right_ok" in wi_body,
    "★★★ _word_in 이 왼쪽·오른쪽 경계를 모두 본다")

mc_body = _py_fn_body(APP_SRC, "api_map_cases")
chk("GEO.partner_coords(x)" in mc_body,
    "★★★ api_map_cases 가 GEO.resolve() 대신 GEO.partner_coords() 를 쓴다"
    "(형제인 api_case_nearby 와 같은 좌표소스)")
chk("GEO.resolve(x[\"region\"], x[\"address\"])" not in mc_body,
    "★★ api_map_cases 에 예전의 직접 resolve() 호출이 남아있지 않다")

CRYPTO_SRC = read("crypto_util.py")
dec_body = _py_fn_body(CRYPTO_SRC, "decrypt")
chk("_log.warning" in dec_body,
    "★★ crypto_util.decrypt 가 실패 시 경고 로그를 남긴다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 지오코더 경계 (geo.py, 서버 기동 없이)")
# ──────────────────────────────────────────────────────────────
sys.path.insert(0, HERE)
import geo as GEO  # noqa: E402

r1 = GEO.resolve("경상북도 영덕군", "동해대로 123")
chk(r1[:2] == GEO.GU["영덕"],
    "★★★ '동해대로'가 있어도 주소에 명시된 영덕이 정확히 잡힌다"
    "(예전엔 '동해'로 오인 — 125km 벗어남)", r1)

r2 = GEO.resolve("삼척시 근덕면", "동해대로 5966")
chk(r2[:2] == GEO.GU["삼척"],
    "★★★ 삼척도 마찬가지로 정확히 잡힌다(예전엔 '동해'로 오인 — 9.5km 벗어남)", r2)

r3 = GEO.resolve("강원도 동해시", "")
chk(r3[:2] == GEO.GU["동해"],
    "STEP 실제 동해시 주소는 여전히 동해로 정상 해석된다(과잉차단 아님)", r3)

r4 = GEO.resolve("인천광역시 남동구", "")
chk(r4[:2] == GEO.GU["남동"],
    "STEP 기존 수정(긴 지명 꼬리 오매칭 차단: 남동구→동구)은 그대로 살아있다", r4)

r5 = GEO.resolve("부산광역시 강서구", "")
chk(r5[:2] == GEO.GU["강서부산"],
    "STEP 기존 수정(강서구→서구 오매칭 차단)도 그대로 살아있다", r5)

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 현장지도가 저장좌표를 우선 쓰는가")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round120_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"

try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r120admin','x','검증','중간관리자')")
    #  region/address 만 보면 '강남'(서울)으로 잡힐 주소지만, 저장좌표는
    #  일부러 전혀 다른 곳(부산 임의좌표)으로 넣는다 — 두 소스가 다르면
    #  자리도 달라야 '저장좌표를 실제로 썼다'고 말할 수 있다.
    STORED_LAT, STORED_LNG = 35.111111, 129.111111
    #  ⚠⚠ [라운드216] geo_src 를 반드시 채운다 — 안 채우면(NULL) partner_coords()
    #    가 "gs or 수동" 의 폴백만 타서, 216라운드가 고친 "실제 컬럼값을
    #    읽는다"는 핵심 동작 자체는 한 번도 검증하지 못한 채 우연히 통과한다
    #    (실측: 운영DB 활성 협력사 365곳 전부 이 값이 '주소검색'이다 — 폴백이
    #    아니라 이쪽이 실제 다수 케이스).
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,region,address,lat,lng,geo_src) "
        "VALUES('R120업체','시행사','활성','서울','강남대로 1',?,?,'주소검색')",
        (STORED_LAT, STORED_LNG)).lastrowid
    conn.commit()

    admin = A.app.test_client()
    with admin.session_transaction() as sess:
        sess["admin"] = "r120admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"

    r = admin.get("/api/map/cases")
    j = r.get_json() or {}
    chk(r.status_code == 200, "STEP 현장지도 조회 자체는 정상 처리된다(과잉차단 아님)",
        (r.status_code, j))
    mine = next((p for p in j.get("partners", []) if p.get("id") == pid), None)
    chk(mine is not None,
        "STEP 등록한 업체가 지도 응답에 실제로 나온다", j.get("partners"))
    if mine:
        chk(abs(mine["lat"] - STORED_LAT) < 1e-6 and abs(mine["lng"] - STORED_LNG) < 1e-6,
            "★★★ 지도가 저장된 lat/lng 를 그대로 쓴다"
            "(예전엔 region/address 로 재추측해 '강남'으로 잘못 이동시켰다)",
            (mine["lat"], mine["lng"], STORED_LAT, STORED_LNG))
        #  ⚠⚠ [라운드216] 예전엔 partner_coords() 가 geo_src 컬럼을 안 읽고
        #    무조건 "수동"을 박아 넣어, 이 자리는 실제로는 아무것도 증명하지
        #    못하는 우연의 일치였다(형제 case_coords 는 이미 실제값을 읽는데
        #    이 함수만 안 그랬다) — 이제 저장된 실제값('주소검색')이 그대로
        #    나오는지 확인한다.
        chk(mine["geo_src"] == "주소검색",
            "★★★★ 저장좌표를 쓴 업체의 출처 표기가 실제 geo_src 컬럼값"
            "('주소검색')을 그대로 반영한다(고치기 전엔 무조건 '수동'이라고 "
            "거짓 표시했다 — 실측: 운영DB 활성 협력사 365곳 전부 이 오표시를 겪었다)",
            mine["geo_src"])

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드120 서버측 준비/실행(지도)", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

# ══════════════════════════════════════════════════════════════
print("\n[4] 실행 — 복호화 실패가 이제 로그로 남는가")
# ──────────────────────────────────────────────────────────────
try:
    import crypto_util as CU

    class _CapHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []

        def emit(self, record):
            self.records.append(record)

    cap = _CapHandler()
    _logger = logging.getLogger("crypto_util")
    _prev_level = _logger.level
    _logger.addHandler(cap)
    _logger.setLevel(logging.WARNING)
    try:
        good = CU.encrypt("110-234-567890")
        #  마지막 글자 하나를 바꿔 GCM 태그(무결성)를 깨뜨린다 — 실제 변조·손상과
        #  같은 모양의 실패다(부분 base64 오류가 아니라 진짜 AEAD 검증 실패).
        last = good[-1]
        swap = "A" if last != "A" else "B"
        tampered = good[:-1] + swap
        result = CU.decrypt(tampered)
        chk(result == "",
            "STEP 변조된 암호문은 여전히 빈 문자열을 반환한다"
            "(호출부 6곳의 기존 분기를 그대로 둔다)", result)
        chk(any("복호화 실패" in r.getMessage() for r in cap.records),
            "★★ 복호화 실패가 이제 경고 로그로 남는다(예전엔 완전 침묵)",
            [r.getMessage() for r in cap.records])
    finally:
        _logger.removeHandler(cap)
        _logger.setLevel(_prev_level)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드120 서버측 준비/실행(복호화)", f"{type(e).__name__} {e}")

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
