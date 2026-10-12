# -*- coding: utf-8 -*-
"""스캔 180라운드 회귀 — 표준단가 대량적재 CLI(seed_boq.py·seed_boq_led.py)가
개정 이력(boq_price_history)을 전혀 남기지 않던 결함.

  관리자 콘솔 3개 라우트(추가·수정·비활성)는 _boq_history() 로 이력을 남기는데,
  실제로 가장 자주 쓰이는 적재 경로인 이 CLI(반복 실행하면 기존 항목을 그
  자리에서 UPDATE 한다)는 app.py 를 import 하지 않아 그 함수에 닿지 못했다.
  실측(운영DB): 표준단가 적재 CLI 실행 이력이 activity_log 에 4회 있고 그중
  한 번이 42개 항목의 단가를 그 자리에서 덮어썼는데, boq_price_history 는
  0행이었다 — "그때 그 단가 대비 낙찰가"를 되짚을 근거가 전부 사라진 상태.

      python test_scan_round180_fixes.py
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


DB_SRC = read("db.py")
APP_SRC = read("app.py")
SEED_SRC = read("seed_boq.py")
LED_SRC = read("seed_boq_led.py")

print("=" * 72)
print("  스캔 180라운드 회귀 — 표준단가 적재 CLI 의 개정이력 미기록")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk('def boq_history(conn, boq_id, row, action, old_price=None, actor="시스템"):' in DB_SRC,
    "★★★ db.py 에 공유 boq_history() 가 있다(app.py·CLI 양쪽이 이미 신뢰하는 모듈)")

i0 = APP_SRC.index("def _boq_history(conn, boq_id, row, action, old_price=None):")
i1 = APP_SRC.index("\n@app.", i0 + 1)
chk("DB.boq_history(conn, boq_id, row, action, old_price, actor=actor())" in APP_SRC[i0:i1],
    "★★★ app.py 의 _boq_history 가 db.py 공유함수에 위임한다")

i2 = SEED_SRC.index("def load(rows")
i3 = SEED_SRC.index("\ndef main", i2)
seed_body = SEED_SRC[i2:i3]
chk('DB.boq_history(conn, ex["id"], _hrow, action="수정",' in seed_body,
    "★★★ seed_boq.py 의 갱신(기존 항목 UPDATE) 경로가 이력을 남긴다")
chk('DB.boq_history(conn, cur.lastrowid, _hrow, action="추가",' in seed_body,
    "★★★ seed_boq.py 의 신규추가(INSERT) 경로가 이력을 남긴다")
chk('DB.boq_history(conn, dr["id"], {**dict(dr), "major": m}, action="비활성",' in seed_body,
    "★★★ seed_boq.py 의 데모값 사용중지 경로도 이력을 남긴다")

chk('DB.boq_history(conn, _r["id"], {**dict(_r), "major": M}, action="비활성",' in LED_SRC,
    "★★★ seed_boq_led.py 의 2017년값 사용중지도 이력을 남긴다")

# ============================================================
print("\n[2] 실행 — 반복 적재(신규→갱신→데모비활성) 전 과정이 이력에 남는가")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round180_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import seed_boq as SB

    MAJOR = "R180공종"

    def history_of(item):
        row = DB.get_db().execute(
            "SELECT id FROM standard_boq WHERE major=? AND item=?", (MAJOR, item)).fetchone()
        if not row:
            return None, []
        conn = DB.get_db()
        hs = conn.execute(
            "SELECT action, old_price, new_price FROM boq_price_history "
            " WHERE boq_id=? ORDER BY id", (row["id"],)).fetchall()
        conn.close()
        return row["id"], [dict(h) for h in hs]

    # ① 신규 추가
    a1, s1, r1 = SB.load([(MAJOR, "R180항목", "규격A", "개", 1500, "R180검증근거", "2020-01")],
                          dry=False, deactivate_demo=False)
    bid, hist1 = history_of("R180항목")
    chk(a1 == 1 and len(hist1) == 1 and hist1[0]["action"] == "추가"
        and hist1[0]["old_price"] is None and hist1[0]["new_price"] == 1500,
        "★★★ 신규 추가가 이력 1건(추가·old=None·new=1500)을 남긴다", hist1)

    # ② 같은 항목을 다른 값으로 재적재 — 실사용과 동일(반복 실행 시 그 자리에서 갱신)
    a2, s2, r2 = SB.load([(MAJOR, "R180항목", "규격A", "개", 9900, "R180검증근거 개정", "2026-08")],
                          dry=False, deactivate_demo=False)
    _, hist2 = history_of("R180항목")
    chk(a2 == 1 and len(hist2) == 2 and hist2[1]["action"] == "수정"
        and hist2[1]["old_price"] == 1500 and hist2[1]["new_price"] == 9900,
        "★★★★ 반복 적재(1,500→9,900원 개정)가 이력에 남는다"
        "(고치기 전엔 이 CLI 경로가 이력을 아예 안 남겼다)", hist2)

    # ③ 데모값 사용중지도 이력에 남는가
    conn = DB.get_db()
    demo_bid = conn.execute(
        "INSERT INTO standard_boq(major,item,spec,unit,ref_price,price_src,active,is_demo,"
        "                         created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,1,1,?,?)",
        (MAJOR, "R180데모항목", "", "개", 500, "데모", DB.now(), DB.now())).lastrowid
    conn.commit(); conn.close()
    SB.load([(MAJOR, "R180항목2", "규격B", "개", 2000, "R180검증근거2", "2026-08")],
            dry=False, deactivate_demo=True)
    conn = DB.get_db()
    demo_row = conn.execute("SELECT active FROM standard_boq WHERE id=?", (demo_bid,)).fetchone()
    demo_hist = conn.execute(
        "SELECT action FROM boq_price_history WHERE boq_id=?", (demo_bid,)).fetchall()
    conn.close()
    chk(demo_row["active"] == 0 and len(demo_hist) == 1 and demo_hist[0]["action"] == "비활성",
        "★★★ 데모값 사용중지도 이력(비활성)을 남긴다", (demo_row["active"], demo_hist))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드180 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
