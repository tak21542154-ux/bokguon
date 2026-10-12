# -*- coding: utf-8 -*-
"""스캔 160라운드 회귀 — geocode_fill.py 의 fill() 이 "결과가 아예 없을 때"만
정제주소로 재시도해, 좌표 없는 후보가 섞인(그러나 비어있진 않은) 검색결과를
그대로 포기하던 결함.

  addr_search.py 의 검색기는 좌표 없는 "place"류 후보를 섞어 낼 수 있다
  (그 파일 자체 self-check 가 이미 "blind"(좌표없음) 후보를 전제한다).
  주소 칸에 '본사: … / 공장: …' 처럼 여러 주소가 섞인 행(이 스크립트가
  존재하는 핵심 이유)이 하필 그런 좌표없는 후보 하나로 걸리면, 재시도 자체가
  안 열려 정제주소로는 분명히 찾을 수 있는 좌표를 통째로 포기했다.

      python test_scan_round160_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


SRC = read("geocode_fill.py")

print("=" * 72)
print("  스캔 160라운드 회귀 — 좌표없는 후보가 섞이면 재시도를 포기하던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = SRC.index("def fill(")
i1 = SRC.index("\ndef ", i0 + 1)
body = SRC[i0:i1]
chk(body.count('best = next((h for h in hits if h.get("lat") and h.get("lng")), None)') == 2,
    "★★★ 재시도 전·후 둘 다 best(좌표있는 후보)를 다시 계산한다")
chk(body.count("if not best:") == 2,
    "★★★ 재시도 가드가 not hits 가 아니라 not best 로 바뀌었다(재시도 앞뒤 둘 다)")

# ============================================================
print("\n[2] 실행 — 좌표없는 후보만 있는 응답에서 실제로 재시도해 찾는가")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round160_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import addr_search as ADDR
    import geocode_fill as GF

    MESSY = "본사: 부산 사하구 동매로 120 한신혜성상가 203호 / 공장: 김해시 한림면"
    CLEAN = GF._first_address(MESSY)
    chk(CLEAN and CLEAN != MESSY,
        "★ (사전조건) _first_address 가 실제로 다른(정제된) 문자열을 낸다", CLEAN)

    calls = []

    def _fake_search(q):
        calls.append(q)
        if q == MESSY:
            #  카카오가 실제로 내는 모양 — 좌표 없는 place 후보가 섞여 있다
            #  (addr_search.py 자체 self-check 의 "blind" 케이스와 같은 모양).
            return [{"road": "부산 사하구 어딘가", "region": "부산 사하", "lat": None, "lng": None}]
        if q == CLEAN:
            return [{"road": "부산 사하구 동매로 120", "region": "부산 사하", "lat": 35.10, "lng": 128.97}]
        return []

    _orig_search = ADDR.search
    ADDR.search = _fake_search
    try:
        conn = DB.get_db()
        pid = conn.execute(
            "INSERT INTO partners(name,partner_type,status,category,region,address,created_at) "
            "VALUES('R160업체','시공사','활성','가드레일','부산',?,?)",
            (MESSY, DB.now())).lastrowid
        conn.commit(); conn.close()

        done = GF.fill("partners", 10, dry=False)

        chk(calls == [MESSY, CLEAN],
            "★★★ 좌표없는 후보로 끝나지 않고 정제주소로 실제 재시도한다"
            "(고치기 전엔 MESSY 한 번만 부르고 포기했다)", calls)
        chk(done == 1, "★★★ 재시도로 찾은 좌표가 실제로 채워진다(done=1)", done)

        conn = DB.get_db()
        row = dict(conn.execute(
            "SELECT lat, lng, geo_src FROM partners WHERE id=?", (pid,)).fetchone())
        conn.close()
        chk(row["lat"] == 35.10 and row["lng"] == 128.97 and row["geo_src"] == "주소검색",
            "★★★ 재시도 히트의 좌표가 DB 에 그대로 저장된다", row)
    finally:
        ADDR.search = _orig_search
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드160 [2] fill() 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
