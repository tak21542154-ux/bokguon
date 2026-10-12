# -*- coding: utf-8 -*-
"""스캔 182라운드 회귀 — sweep_dispatches() 의 자동 재수배 실패 처리기가
t.get("case_id") 를 써서, 정작 예외가 나면 **로그하고 다음 건으로 넘어가야
할 자리**가 반대로 전체를 끊는 자리가 되던 결함.

  targets 는 sqlite3.Row(710행 fetchall, conn.row_factory=Row) 인데 Row 는
  .get() 이 없다 — open_dispatch() 가 예외를 던지면(운영에서 실제로 나는
  "database is locked" 등) 이 except 블록 자신이 AttributeError 로 죽어
  원래 예외를 덮어쓰고, 이 함수 바깥의 try(776행)까지 뚫고 나가 **남은
  대상 전부**의 재수배 점검을 통째로 멈춘다.

      python test_scan_round182_fixes.py
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


DP_SRC = read("dispatch.py")

print("=" * 72)
print("  스캔 182라운드 회귀 — 자동 재수배 실패처리기의 Row.get() 오용")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = DP_SRC.index("def sweep_dispatches(")
i1 = DP_SRC.index("\ndef ", i0 + 1)
body = DP_SRC[i0:i1]
chk('_log.exception("자동 재수배 실패 case=%s", t["case_id"])' in body,
    "★★★ sweep_dispatches 가 대괄호로 접근한다"
    "(고치기 전엔 .get() 이 Row 에 없어 예외처리기 자신이 죽었다)")
chk('t.get("case_id")' not in body,
    "★ .get() 오용이 이 함수에서 완전히 사라졌다")

# ============================================================
print("\n[2] 실행 — open_dispatch 가 실패해도 나머지 대상을 계속 처리하는가")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round182_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import dispatch as DP

    conn = DB.get_db()

    def mk_overdue(tag):
        cid = conn.execute(
            "INSERT INTO cases(case_no,status,category,region,is_demo,created_at) "
            "VALUES(?,?,'가드레일','서울',0,?)",
            (f"R182-{tag}", "접수", DB.now())).lastrowid
        did = conn.execute(
            "INSERT INTO dispatches(case_id,status,round,due_at,claimed_partner_id,created_at) "
            "VALUES(?,?,1,'2020-01-01 00:00:00',999,?)",
            (cid, DP.ST_CLAIMED, DB.now())).lastrowid
        return cid, did

    cid1, did1 = mk_overdue("A")
    cid2, did2 = mk_overdue("B")
    conn.commit()

    real_open_dispatch = DP.open_dispatch

    def _boom(conn_, case_id, **kw):
        raise OSError("database is locked (검증용 강제 재현)")

    DP.open_dispatch = _boom
    try:
        res = DP.sweep_dispatches(conn, force=True)
    except Exception as e:                                          # noqa: BLE001
        chk(False, "★★★★ open_dispatch 가 실패해도 sweep_dispatches 자체는 죽지 않는다"
                   "(고치기 전엔 AttributeError 로 통째로 죽었다)",
            f"{type(e).__name__}: {e}")
        res = None
    finally:
        DP.open_dispatch = real_open_dispatch

    if res is not None:
        chk(True, "★★★★ open_dispatch 가 실패해도 sweep_dispatches 자체는 죽지 않는다"
                  "(고치기 전엔 AttributeError 로 통째로 죽었다)")
        chk(res.get("expired") == 2,
            "★★★ 두 대상 모두 '만료' 처리까지는 진행된다(고치기 전엔 1건에서 멈췄다)",
            res)

        st1 = conn.execute("SELECT status FROM dispatches WHERE id=?", (did1,)).fetchone()["status"]
        st2 = conn.execute("SELECT status FROM dispatches WHERE id=?", (did2,)).fetchone()["status"]
        chk(st1 == DP.ST_FAILED, "첫 번째 대상이 '실패' 처리됨", st1)
        chk(st2 == DP.ST_FAILED,
            "★★★★ 두 번째 대상도 '실패' 처리까지 도달한다"
            "(고치기 전엔 첫 대상에서 예외처리기 자체가 죽어 두 번째는 아예 안 건드려졌다)",
            st2)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드182 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
