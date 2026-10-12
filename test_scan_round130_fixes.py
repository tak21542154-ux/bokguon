# -*- coding: utf-8 -*-
"""스캔 130라운드 회귀 — 출동 수배 후보 선정(dispatch.py:candidates())과
   관리자 "현장 근처 업체"(app.py:api_case_nearby())의 공종·지역 LIKE 매칭이
   보험사가 자유텍스트로 보낸 category/region 값을 이스케이프 없이 그대로
   써서, '%' 하나만 있어도 필터가 전체매칭으로 무력화됐다(실측: 130라운드
   조사가 sqlite3 실행으로 확인 — category='%' 하나로 활성 파트너 전원이
   매칭됨). 결과: 전혀 무관한 공종·지역의 업체 최대 20곳에 사건 현장정보가
   담긴 출동 알림이 나갈 수 있었다.

  이미 있는 검색 LIKE 들(app.py 의 search_filters 등, 라운드31)은
  `_like_escape()` + `ESCAPE '\\'` 를 쓰는데, 이 트레이드/지역 매칭 두 곳만
  빠져 있었다.

      python test_scan_round130_fixes.py
"""
import io
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
#  dispatch.py 를 import 하면 db.py 가 물려 임포트되고, db.py 는 자신이 열
#  DB_PATH 가 운영본이면 스스로 멈춘다(안전장치) — 이 테스트는 아래에서
#  독립된 sqlite3(:memory:) 커넥션만 candidates() 에 직접 넘기므로 이 값
#  자체는 실제로 안 쓰이지만, import 시점 검사를 통과하려면 운영이 아닌
#  경로를 미리 지정해 둬야 한다.
os.environ.setdefault("BOKGUON_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="round130_"), "verify.db"))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


print("=" * 72)
print("  스캔 130라운드 회귀 — dispatch.candidates()·api_case_nearby() 공종/지역 LIKE 와일드카드 무력화")
print("=" * 72)

APP_SRC = read("app.py")
DP_SRC = read("dispatch.py")

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
_start = DP_SRC.index("def candidates(")
_rest = DP_SRC[_start:]
_end_rel = _rest.index("\n\ndef ", 1)
dp_body = _rest[:_end_rel] if _end_rel > 0 else _rest

#  ⚠⚠ [라운드499] _t 는 이제 _norm_dot() 도 거친다(가운뎃점 표기 정규화) —
#    _like_escape 자체는 여전히 거치므로 이 검사의 취지(와일드카드 이스케이프)는
#    그대로 유지된다.
chk("_like_escape(_norm_dot(_t))" in dp_body,
    "★★★ candidates() 의 트레이드 파라미터가 _like_escape 를 거친다")
chk(dp_body.count("ESCAPE '\\\\'") >= 4,
    "★★★ candidates() 의 LIKE 4곳(트레이드2 + 지역 region/address) 전부 ESCAPE 절이 붙었다",
    f"실제 {dp_body.count(chr(39)+'ESCAPE'+chr(39))}")
chk("rkey_like = f\"%{_like_escape(rkey)}%\"" in dp_body,
    "★★★ 지역 매칭도 rkey_like(이스케이프된 값)로 한다")
chk("def _like_escape(s):" in DP_SRC,
    "★★ dispatch.py 자체 _like_escape 헬퍼가 추가됐다(app.py 와 순환임포트 회피)")

#  ⚠⚠ [라운드499] 이 함수 앞부분에 새 정규화 주석·코드가 붙으면서 고정
#    2500자 창이 실제 LIKE 절보다 앞에서 끝나버렸다 — dp_body(위)와 같은
#    "다음 def 전까지" 방식으로 바꿔 함수 크기 변화에 흔들리지 않게 한다.
_anb_start = APP_SRC.index("def api_case_nearby(cid):")
_anb_rest = APP_SRC[_anb_start:]
_anb_end_rel = _anb_rest.index("\n\ndef ", 1)
anb_body = _anb_rest[:_anb_end_rel] if _anb_end_rel > 0 else _anb_rest
chk("_like_escape(_norm_dot(_t))" in anb_body,
    "★★★ api_case_nearby() 도 트레이드 값을 _like_escape 로 이스케이프한다")
chk("ESCAPE '\\\\'" in anb_body,
    "★★★ api_case_nearby() 의 LIKE 에도 ESCAPE 절이 붙었다")

# ============================================================
print("\n[2] 실행 — 실제 sqlite3 + 실제 dispatch.candidates() 로 두 시나리오 재현")
# ------------------------------------------------------------
import dispatch as DP  # noqa: E402


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


try:
    # ── 시나리오 A: 공종(category)='%' 하나 — 지역은 비워서 트레이드 매칭만 단독 관찰 ──
    conn = _mkdb()
    conn.execute("INSERT INTO cases(id,category,region,address) VALUES (1,'%','','')")
    partners_a = [("가드레일", "서울 송파"), ("유리", "서울 송파"), ("지붕", "서울 송파"),
                  ("전기", "서울 송파"), ("누수", "서울 송파")]
    for i, (cat, region) in enumerate(partners_a, start=1):
        conn.execute(
            "INSERT INTO partners(id,name,status,license_status,region,address,category,major,login_id,phone) "
            "VALUES (?,?,'활성','일반',?,?,?,?,'','')",
            (i, f"업체{i}", region, region, cat, cat))
    conn.commit()
    got_a = DP.candidates(conn, 1)
    chk(len(got_a) == 0,
        "★★★ 시나리오A: category='%' 는 실제 공종과 리터럴로 안 겹치므로 후보 0곳이어야 한다"
        "(고치기 전엔 활성 파트너 전원=5곳이 매칭됐다 — 실측)",
        [x["category"] for x in got_a])
    conn.close()

    # ── 시나리오 B: 지역(주소)이 '%구' → _region_key 가 '%' 하나만 반환 ──
    conn = _mkdb()
    #  category 는 실제 어떤 파트너와도 안 겹치는 값으로 둬 트레이드 매칭 기여를 0으로 고정
    conn.execute("INSERT INTO cases(id,category,region,address) VALUES (2,'사건측공종','','%구')")
    partners_b = ["서울 송파구", "부산 해운대구", "대구 수성구", "인천 남동구", "광주 광산구"]
    for i, region in enumerate(partners_b, start=1):
        #  ⚠ 파트너의 공종은 사건 공종과 절대 안 겹치는 값으로 둔다 — 안 그러면
        #    지역과 무관한 3순위(공종 일치·지역 밖)가 항상 전원을 반환해,
        #    이 시나리오가 증명하려는 "지역 열쇠 이스케이프"와 무관하게 통과/
        #    실패해 버린다(실제로 한 번 이 실수로 거짓 FAIL 이 났다).
        conn.execute(
            "INSERT INTO partners(id,name,status,license_status,region,address,category,major,login_id,phone) "
            "VALUES (?,?,'활성','일반',?,?,'업체측공종','',?,'')",
            (i, f"업체{i}", region, region, "01000000000"))
    conn.commit()
    got_b = DP.candidates(conn, 2)
    chk(len(got_b) == 0,
        "★★★ 시나리오B: address='%구' 로 만든 지역열쇠 '%' 는 실제 지역과 리터럴로 안 겹치므로 "
        "후보 0곳이어야 한다(고치기 전엔 지역 무관 전원이 매칭됐다)",
        [x["region"] for x in got_b])
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드130 준비/실행(sqlite3 재현)", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
