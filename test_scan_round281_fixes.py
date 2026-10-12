# -*- coding: utf-8 -*-
"""스캔 281라운드 회귀 — dispatch.py 출동배차 모듈 결함 2건
   (dispatch.py 비-스윕 함수군 정밀조사 — round257 은 sweep_dispatches() 만
   감사했고 claim/decline/arrive/close_no_repair 는 이번이 처음. 정밀조사
   Agent가 발견, 독립 재검증 후 수정).

  [1] decline() 만 감사로그(DB.log)가 없었다 — 같은 파일의 형제(claim·arrive·
      close_no_repair 등)는 상태를 바꾸는 자리마다 전부 남긴다. 그 결과 사건
      상세의 감사이력(activity_log.detail LIKE '%사건번호%' — 라운드94·117·190이
      지켜 온 바로 그 조회)·관리자 감사로그 화면·운영 대시보드 최근활동 어디에도
      "누가 언제 거절했는지"가 안 남았다(dispatch_calls.response='거절' 자체는
      남지만 사건번호로는 못 찾는다). 형제와 같은 자리(성공 시, commit 직전)에
      DB.log() 를 추가.

  [2] _release_lease() 의 `except sqlite3.Error: pass` 가 완전 침묵했다 — 같은
      파일의 형제 3곳(수배 알림 실패·밀려난 협력사 통지 실패·자동 재수배 실패)은
      전부 _log.exception 으로 남긴다. 리스 해제 실패는 120초 뒤 자연만료로
      복구되니 급하지 않지만, 반복 실패해도 아무 신호가 안 남는 건 형제와
      기준이 다르다. _log.exception 추가(동작 자체는 안 바뀜, 가시성만 추가).

  ⚠ 이 테스트는 임시 디렉터리의 격리 DB만 쓴다 — 운영 bokguon.db 는 전혀
    건드리지 않는다.

      python test_scan_round281_fixes.py
"""
import io
import logging
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []

_tmpdir = tempfile.mkdtemp(prefix="round281_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


DP_SRC = read("dispatch.py")

print("=" * 72)
print("  스캔 281라운드 회귀 — dispatch.py decline()·_release_lease() 침묵결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_dec = DP_SRC.index("def decline(conn")
i_dec_end = DP_SRC.index("\n\n\ndef arrive(")
dec_body = DP_SRC[i_dec:i_dec_end]
chk("DB.log(" in dec_body,
    "★★★★★ decline() 이 감사로그를 남긴다(고치기 전엔 이 함수만 형제 중 유일하게 침묵)")

i_rl = DP_SRC.index("def _release_lease(")
i_rl_end = DP_SRC.index("\n\n\ndef sweep_dispatches(")
rl_body = DP_SRC[i_rl:i_rl_end]
chk("_log.exception(" in rl_body,
    "★★★★ _release_lease() 가 실패를 로그로 남긴다(고치기 전엔 완전 침묵)")

# ============================================================
print("\n[2] 실행 준비")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
import db as DB                                                     # noqa: E402
import dispatch as DP                                                # noqa: E402

DB.init_db()
conn = DB.get_db()


def _mk_case(case_no):
    conn.execute(
        "INSERT INTO cases(case_no, category, est_price, is_demo, status) "
        "VALUES(?,'누수·배관·설비',1000000,0,'접수')", (case_no,))
    return conn.execute("SELECT id FROM cases WHERE case_no=?", (case_no,)).fetchone()["id"]


def _mk_dispatch(cid, is_demo=0):
    conn.execute(
        "INSERT INTO dispatches(case_id, round, status, is_demo, created_at) "
        "VALUES(?,1,'모집중',?,datetime('now'))", (cid, is_demo))
    did = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    return did


def _mk_call(did, pid):
    conn.execute(
        "INSERT INTO dispatch_calls(dispatch_id, partner_id, partner_name, notified_at) "
        "VALUES(?,?,?,datetime('now'))", (did, pid, f"업체{pid}"))


def _log_count():
    return conn.execute("SELECT COUNT(*) n FROM activity_log").fetchone()["n"]


def _case_history_hits(case_no):
    return conn.execute(
        "SELECT COUNT(*) n FROM activity_log WHERE detail LIKE ?",
        (f"%{case_no}%",)).fetchone()["n"]

# ============================================================
print("\n[3] 실행 — decline() 이 성공하면 사건번호로 찾아지는 감사로그를 남기는가")
# ------------------------------------------------------------
try:
    cid1 = _mk_case("R281-DECLINE")
    did1 = _mk_dispatch(cid1)
    _mk_call(did1, 9001)
    conn.commit()

    before = _log_count()
    ok = DP.decline(conn, did1, 9001)
    after = _log_count()
    chk(ok is True, "STEP decline() 이 True 를 돌려준다(정상 거절)")
    chk(after == before + 1,
        "★★★★★ decline() 성공 시 activity_log 에 정확히 1건이 새로 남는다"
        "(고치기 전엔 0건)", f"before={before} after={after}")
    chk(_case_history_hits("R281-DECLINE") >= 1,
        "★★★★★ 사건상세 감사이력(사건번호 LIKE 조회)에서 이 거절이 실제로 찾아진다"
        "(고치기 전엔 dispatch_calls.response='거절'만 남고 이 조회엔 0건이었다)")
    row = conn.execute(
        "SELECT response FROM dispatch_calls WHERE dispatch_id=? AND partner_id=9001",
        (did1,)).fetchone()
    chk(row["response"] == "거절", "STEP dispatch_calls 자체도 정상적으로 거절로 남는다(회귀 없음)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드281 [3] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[4] 실행 — 회귀 없음: claim() 은 그대로 정상 로그를 남기는가")
# ------------------------------------------------------------
try:
    cid2 = _mk_case("R281-CLAIM")
    did2 = _mk_dispatch(cid2)
    _mk_call(did2, 9002)
    conn.commit()

    before2 = _log_count()
    ok2, msg2, due2 = DP.claim(conn, did2, 9002, "업체9002")
    after2 = _log_count()
    chk(ok2 is True, "STEP claim() 은 여전히 정상 동작한다(회귀 없음)", msg2)
    chk(after2 == before2 + 1,
        "STEP claim() 은 원래대로 성공 시 1건을 남긴다(decline() 수정이 이걸 안 건드림)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드281 [4] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 실행 — 대조군: 실패하는 decline() 은 로그를 남기지 않는가(과잉로깅 아님)")
# ------------------------------------------------------------
try:
    #  5-1) 이미 응답한 수배 재거절 시도 — rowcount=0
    cid3 = _mk_case("R281-NOOP")
    did3 = _mk_dispatch(cid3)
    _mk_call(did3, 9003)
    conn.commit()
    DP.decline(conn, did3, 9003)                                     # 첫 거절(성공, 로그 1건)
    before3 = _log_count()
    ok3 = DP.decline(conn, did3, 9003)                                # 재거절 — 이미 응답함
    after3 = _log_count()
    chk(ok3 is False, "STEP 이미 응답한 수배는 재거절이 False 를 돌려준다(회귀 없음)")
    chk(after3 == before3,
        "★★★ 아무것도 안 바뀐 시도는 로그를 새로 남기지 않는다(과잉로깅 방지)",
        f"before={before3} after={after3}")

    #  5-2) 데모 수배 — 원래도 거부, 로그도 없어야 정상
    cid4 = _mk_case("R281-DEMO")
    did4 = _mk_dispatch(cid4, is_demo=1)
    _mk_call(did4, 9004)
    conn.commit()
    before4 = _log_count()
    ok4 = DP.decline(conn, did4, 9004)
    after4 = _log_count()
    chk(ok4 is False, "STEP 데모 수배는 여전히 거부된다(회귀 없음)")
    chk(after4 == before4, "STEP 데모 수배 거부 시에도 로그가 안 남는다(회귀 없음)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드281 [5] 준비/실행", f"{type(e).__name__} {e}")

conn.close()

# ============================================================
print("\n[6] 실행 — _release_lease() 실패가 실제로 로그에 남는가")
# ------------------------------------------------------------
try:
    class _Capture(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []

        def emit(self, record):
            self.records.append(self.format(record))

    cap = _Capture()
    logging.getLogger("bokguon.dispatch").setLevel(logging.DEBUG)
    logging.getLogger("bokguon.dispatch").addHandler(cap)

    conn2 = DB.get_db()
    conn2.execute("DROP TABLE IF EXISTS job_locks")
    conn2.commit()

    cap.records.clear()
    DP._release_lease(conn2, "테스트 노트")                            # noqa: SLF001
    chk(any("리스 해제 실패" in rec for rec in cap.records),
        "★★★★ job_locks 표가 없어도 예외 없이 넘어가고, 실패가 로그에 남는다"
        "(고치기 전엔 로그 0건)", cap.records)
    conn2.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드281 [6] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
