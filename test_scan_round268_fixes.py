# -*- coding: utf-8 -*-
"""스캔 268라운드 회귀 — 표준단가 대량적재(seed_boq.py/seed_boq_led.py) +
   공유함수(db.py boq_history()) 결함 5건
   (직전 세 라운드가 반복 발견한 "배치루프 DB write가 항목별 예외처리 밖"·
   "침묵 except" 두 패턴을 렌즈로 삼은 정밀조사 Agent가 발견, 독립 재검증 후
   수정. 두 스크립트 다 이 세션에서 사상 처음 주조사대상).

  [1] db.py boq_history() — 이력 INSERT 실패를 `except sqlite3.Error: pass`
      로 완전 침묵. 이 함수 자체가 라운드180에서 "단가 바뀌었는데 이력 0행"을
      막으려 만든 통로인데, 스키마 드리프트로 이 INSERT 자체가 실패하면
      호출부는 성공만 보고하고 이력누락은 어디에도 안 남았다. 형제
      (crypto_util.decrypt 라운드120)처럼 로그만 남기도록 수정.

  [2] seed_boq_led.py — 2017년 값 정리 루프의 DB.boq_history() 호출에
      예외처리가 없어, 이력 기록 하나가 실패하면 뒤이은 commit()과 **이
      스크립트의 진짜 목적인 24개 2026년 실측단가 적재(seed_boq.load() 호출)
      까지 통째로 막혔다. 행단위로 감싸 실패해도 계속 진행하도록 수정.

  [3] seed_boq.py — 기존 항목 재적재 시 무조건 덮어쓴다. 관리자가 콘솔에서
      손으로 고친 값이 재적재 한 번에 조용히 하드코딩 값으로 되돌아가도
      화면엔 아무 표시가 없었다(이력엔 남지만 그 순간엔 안 보임). 실제 값이
      바뀔 때만 눈에 띄는 경고를 찍도록 수정(과거 값을 존중하도록 동작 자체를
      바꾸지는 않음 — 가시성만 추가).

  [4] seed_boq.py — `conn.execute("BEGIN IMMEDIATE")` 가 try 블록 **밖**에
      있어, 이 문장 자체가 락 경합으로 실패하면 finally 의 conn.close() 를
      건너뛰어 커넥션이 샜다. try 안으로 옮김(데이터는 아직 안 건드린
      시점이라 훼손 위험은 없음 — 자원누수만 막는 수정).

  [5] seed_boq.py — 근거문구(price_src)를 200자에서 안 잘라, boq_history()·
      app.py의 등록·수정 라우트가 이미 자르는 것과 달리 standard_boq 실운영
      값이 이력 사본보다 길어질 수 있는 유일한 통로였다(현재 데이터는 최대
      102자라 미발현). 형제와 통일해 200자로 자름.

      python test_scan_round268_fixes.py
"""
import contextlib
import io
import logging
import os
import runpy
import secrets
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []

#  ⚠ db.py/seed_boq.py 를 불러오기 전에 검증용 DB 경로부터 정한다
#    (라운드267에서 순서를 잘못해 운영DB 안전장치에 걸린 적 있음).
_tmpdir = tempfile.mkdtemp(prefix="round268_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


DB_SRC = read("db.py")
SB_SRC = read("seed_boq.py")
SBL_SRC = read("seed_boq_led.py")

print("=" * 72)
print("  스캔 268라운드 회귀 — 표준단가 적재 CLI + boq_history() 결함 5건")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_bh = DB_SRC.index("def boq_history(")
i_bh_end = DB_SRC.index("\n\n\n", i_bh)
bh_body = DB_SRC[i_bh:i_bh_end]
chk("except sqlite3.Error as e:" in bh_body and "_log.warning(" in bh_body,
    "★★★★★ db.py boq_history() 가 이력기록 실패를 로그에 남긴다(고치기 전엔 완전 침묵)")

i_load = SB_SRC.index("def load(rows")
i_load_end = SB_SRC.index("\n\n\ndef ", i_load)
load_body = SB_SRC[i_load:i_load_end]
_try_pos = load_body.index("\n    try:")
chk('conn.execute("BEGIN IMMEDIATE")' in load_body[_try_pos:],
    "★★★★★ BEGIN IMMEDIATE 가 try 블록 안으로 옮겨졌다(고치기 전엔 밖이라 실패 시 close 누락)")
chk("src = src[:200]" in load_body,
    "★★★★ price_src 가 200자로 잘린다(형제 boq_history()·app.py 라우트와 통일)")
chk('ex["ref_price"] != price' in load_body and "값 변경" in load_body,
    "★★★★★ 기존 값과 다른 값으로 덮어쓸 때 눈에 띄는 경고를 찍는다(고치기 전엔 무표시)")

i_sbl_loop = SBL_SRC.index("_retiring = conn.execute(")
sbl_tail = SBL_SRC[i_sbl_loop:]
chk("except Exception as _ex:" in sbl_tail and "_hist_failed" in sbl_tail,
    "★★★★★ seed_boq_led.py 의 이력기록 루프가 행단위로 감싸졌다(고치기 전엔 무방비)")

# ============================================================
print("\n[2] 실행 — boq_history() 스키마 드리프트 시 로그로 남는가")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
try:
    import importlib
    import db as DB
    DB.init_db()

    class _Capture(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []

        def emit(self, record):
            self.records.append(self.format(record))

    cap = _Capture()
    logging.getLogger("db").setLevel(logging.DEBUG)
    logging.getLogger("db").addHandler(cap)

    conn = DB.get_db()
    conn.execute("DROP TABLE IF EXISTS boq_price_history")
    conn.commit()

    cap.records.clear()
    #  이 호출이 예외를 던지지 않아야 한다(형태는 그대로 유지 — 이번 수정은
    #  로깅만 추가하고 "계속 진행"이라는 계약 자체는 안 바꾼다).
    DB.boq_history(conn, 1, {"major": "R268", "item": "테스트", "spec": "", "unit": "개",
                              "ref_price": 100}, action="추가", old_price=None, actor="test")
    chk(any("boq_history 기록 실패" in rec and "OperationalError" in rec for rec in cap.records),
        "★★★★★ 표가 없어도 예외 없이 넘어가고, 경고 로그엔 정확한 예외종류가 남는다"
        "(고치기 전엔 로그 0건)", cap.records)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드268 [2] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — seed_boq.py 재적재 시 값 변경이 눈에 띄는가(대조군 포함)")
# ------------------------------------------------------------
try:
    import seed_boq

    mark = "R268SB-" + secrets.token_hex(3)
    row_100 = (mark, "테스트항목", "", "개", 100000, "테스트 근거", "2026-01")
    row_200 = (mark, "테스트항목", "", "개", 200000, "테스트 근거", "2026-01")

    seed_boq.load([row_100], dry=False)

    _out1 = io.StringIO()
    with contextlib.redirect_stdout(_out1):
        seed_boq.load([row_100], dry=False)          # 같은 값으로 재적재 — 대조군
    chk("값 변경" not in _out1.getvalue(),
        "STEP 대조군 — 같은 값으로 재적재하면 경고가 안 뜬다(과잉경고 아님)")

    conn2 = DB.get_db()
    conn2.execute("UPDATE standard_boq SET ref_price=999999999 WHERE major=? AND item=?",
                  (mark, "테스트항목"))
    conn2.commit()
    conn2.close()

    _out2 = io.StringIO()
    with contextlib.redirect_stdout(_out2):
        seed_boq.load([row_200], dry=False)           # 관리자가 999999999로 고친 뒤 재적재
    printed2 = _out2.getvalue()
    chk("값 변경" in printed2 and "999,999,999" in printed2 and "200,000" in printed2,
        "★★★★★ 콘솔에서 고친 값과 다른 값으로 재적재하면 old→new 가 눈에 띄게 찍힌다"
        "(고치기 전엔 [적재] 한 줄만 찍혀 구분이 안 됐다)", printed2[-300:])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드268 [3] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[4] 실행 — BEGIN IMMEDIATE 실패해도 커넥션이 close() 되는가")
# ------------------------------------------------------------
try:
    class _CloseTrackingConn:
        def __init__(self, real):
            self._real = real
            self.closed = False

        def execute(self, sql, *a, **kw):
            if sql.strip() == "BEGIN IMMEDIATE":
                raise sqlite3.OperationalError("SIMULATED-LOCK-R268")
            return self._real.execute(sql, *a, **kw)

        def close(self):
            self.closed = True
            self._real.close()

        def __getattr__(self, name):
            return getattr(self._real, name)

    _wrapped = _CloseTrackingConn(DB.get_db())
    _orig_get_db = seed_boq.DB.get_db
    seed_boq.DB.get_db = lambda: _wrapped
    raised_ok = False
    try:
        seed_boq.load([row_100], dry=True)
    except sqlite3.OperationalError as e:
        raised_ok = "SIMULATED-LOCK-R268" in str(e)
    finally:
        seed_boq.DB.get_db = _orig_get_db

    chk(raised_ok, "STEP 시뮬레이션대로 BEGIN IMMEDIATE 단계에서 실패함")
    chk(_wrapped.closed,
        "★★★★★ BEGIN IMMEDIATE 가 실패해도 커넥션이 close() 된다"
        "(고치기 전엔 try 블록 밖이라 close 가 누락됐다)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드268 [4] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 실행 — price_src 200자 초과가 잘리는가")
# ------------------------------------------------------------
try:
    mark5 = "R268SRC-" + secrets.token_hex(3)
    long_src = "가" * 250
    seed_boq.load([(mark5, "긴근거항목", "", "개", 1000, long_src, "2026-01")], dry=False)
    conn3 = DB.get_db()
    saved = conn3.execute("SELECT price_src FROM standard_boq WHERE major=? AND item=?",
                          (mark5, "긴근거항목")).fetchone()
    conn3.close()
    chk(len(saved["price_src"]) == 200,
        "★★★★ 250자 근거가 저장 시 200자로 잘린다(고치기 전엔 그대로 250자 저장)",
        len(saved["price_src"]))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드268 [5] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[6] 실행 — seed_boq_led.py: 이력기록 1건 실패해도 본작업(24개 적재)이 계속되는가")
# ------------------------------------------------------------
try:
    mark6 = "간판·전기·가로등"
    conn4 = DB.get_db()
    old2017_id = conn4.execute(
        "INSERT INTO standard_boq(major,item,spec,unit,ref_price,price_src,price_date,"
        "                         active,is_demo,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,1,0,?,?)",
        (mark6, "2017년구값", "", "개", 1000, "2017년 관급 근거", "2017",
         DB.now(), DB.now())).lastrowid
    conn4.commit()
    conn4.close()

    _orig_boq_history = DB.boq_history
    _calls = []

    def _flaky_boq_history(conn, boq_id, row, action, old_price=None, actor="시스템"):
        _calls.append(boq_id)
        if len(_calls) == 1:
            raise RuntimeError("SIMULATED-HISTORY-FAIL-R268")
        return _orig_boq_history(conn, boq_id, row, action, old_price=old_price, actor=actor)

    DB.boq_history = _flaky_boq_history
    _sbl_out = io.StringIO()
    sbl_crashed = False
    try:
        with contextlib.redirect_stdout(_sbl_out):
            runpy.run_path(os.path.join(HERE, "seed_boq_led.py"))
    except Exception:
        sbl_crashed = True
    finally:
        DB.boq_history = _orig_boq_history

    chk(not sbl_crashed,
        "★★★★★ 이력기록 1건이 실패해도 seed_boq_led.py 전체가 죽지 않는다"
        "(고치기 전엔 여기서 그대로 죽어 아래 24개 적재가 전혀 안 됐다)")
    chk("이력 기록 실패" in _sbl_out.getvalue(),
        "STEP 실패 사실이 콘솔에 보인다")

    conn5 = DB.get_db()
    old_row = conn5.execute("SELECT active FROM standard_boq WHERE id=?",
                            (old2017_id,)).fetchone()
    led_count = conn5.execute(
        "SELECT COUNT(*) n FROM standard_boq WHERE major=? AND COALESCE(is_demo,0)=0 "
        " AND COALESCE(active,1)=1", (mark6,)).fetchone()["n"]
    conn5.close()
    chk(old_row["active"] == 0,
        "STEP 이력기록이 실패한 2017년 구값도 비활성 처리 자체는 됐다(UPDATE는 별개로 이미 커밋됨)")
    chk(led_count == 24,
        "★★★★★ 진짜 목적인 2026년 24개 실측단가 적재가 실제로 끝까지 실행됐다"
        "(고치기 전엔 이력기록 실패 시점에서 스크립트가 죽어 이 호출 자체가 안 됐다)",
        led_count)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드268 [6] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
