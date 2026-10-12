# -*- coding: utf-8 -*-
"""스캔 257라운드 회귀 — 출동배차(dispatch.py) 데모오염 결함 1건
   (출동배차 모듈 Agent 조사로 발견, 독립 재검증 후 수정).

  sweep_dispatches() 가 데모 사건의 수배도 실제로 시간초과 처리하고
  재수배(open_dispatch)까지 열어, 그 지역·공종의 **실제 활성 협력사**에게
  실제 문자/알림톡이 나갔다 — claim()·decline()·arrive()·close_no_repair()
  는 전부 COALESCE(is_demo,0)=0 을 CAS 조건에 거는데, 자동순회의 유일한
  진입점인 이 스윕 자신만 그 필터가 없었다. 개발 DB엔 데모 수배가 늘 몇
  건 존재하는 게 정상 상태이고, 데모 수배는 claim() 이 항상 거부하므로
  시간초과로만 끝난다 — 그 시간초과를 처리하는 게 바로 이 스윕이다.

  ⚠ 수정 자체에서 SQL 함정에 한 번 걸렸다: `WHERE (A) OR (B) AND is_demo=0`
    로 처음 썼더니 AND 가 OR 보다 결합력이 세서 is_demo 조건이 B 가지에만
    걸리고 A(제한시간 초과 가지)는 여전히 샜다 — 코드 리뷰 중 자체 발견해
    `WHERE ((A) OR (B)) AND is_demo=0` 로 고쳤다. 이 테스트는 OR 의 두
    가지(제한시간 초과=ST_CLAIMED·무응답=ST_OPEN) 를 **각각** 데모로 만들어
    이 정확한 함정을 재현·검증한다 — 한 가지만 테스트했다면 이 버그를
    놓쳤을 것이다.

      python test_scan_round257_fixes.py
"""
import io
import os
import secrets
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


DISPATCH_SRC = read("dispatch.py")

print("=" * 72)
print("  스캔 257라운드 회귀 — sweep_dispatches() 데모오염 차단")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — OR 를 감싼 괄호까지 정확히 있는지")
# ------------------------------------------------------------
i0 = DISPATCH_SRC.index("def sweep_dispatches(")
i1 = DISPATCH_SRC.index("\ndef ", i0 + 10)
sweep_body = DISPATCH_SRC[i0:i1]
chk(sweep_body.count("AND COALESCE(is_demo,0)=0") == 2,
    "★★★★ 카운트·대상조회 두 쿼리 모두 데모 제외 조건이 생겼다")
#  ⚠ 두 쿼리는 들여쓰기 깊이가 다르다(하나는 try: 밖, 하나는 안) — 공백을
#    지우고 "))"+AND 순서로만 판정해 그 차이에 흔들리지 않게 한다.
_squeezed = "".join(sweep_body.split())
chk(_squeezed.count("))ANDCOALESCE(is_demo,0)=0") == 2,
    "★★★★★ 두 쿼리 모두 OR 전체를 괄호로 감싼 바로 뒤에 AND 를 붙였다"
    "(괄호 없이 이어 붙이면 AND 가 OR 보다 세게 묶여 절반만 걸러진다)")

# ============================================================
print("\n[2] 실행(Flask/직접호출) — OR 의 두 가지를 각각 데모로 만들어 실측")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round257_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import dispatch as DP

    conn = DB.get_db()
    mark = "R257-" + secrets.token_hex(3)
    mins = DP.dispatch_minutes(conn)

    def mkcase(tag, is_demo):
        cur = conn.execute(
            "INSERT INTO cases(case_no,category,region,address,status,"
            "dispatch_status,is_demo,created_at) "
            "VALUES(?,?,?,?,'접수','수배중',?,?)",
            (f"{mark}-{tag}", "가드레일·방호울타리", "서울", "검증용",
             1 if is_demo else 0, DB.now()))
        return cur.lastrowid

    def mkdispatch(cid, status, is_demo, due_past=False, created_old=False):
        due = "datetime('now','+9 hours','-1 hours')" if due_past else "NULL"
        created = "datetime('now','+9 hours','-2 hours')" if created_old else "datetime('now','+9 hours')"
        cur = conn.execute(
            f"INSERT INTO dispatches(case_id,round,status,due_at,is_demo,created_at) "
            f"VALUES(?,3,?,{due},?,{created})",
            (cid, status, 1 if is_demo else 0))
        return cur.lastrowid

    #  ── OR 의 가지 ① — 제한시간 초과(ST_CLAIMED, due_at 지남) ──
    cid_demo_a = mkcase("demoA", True)
    did_demo_a = mkdispatch(cid_demo_a, DP.ST_CLAIMED, is_demo=True, due_past=True)
    cid_real_a = mkcase("realA", False)
    did_real_a = mkdispatch(cid_real_a, DP.ST_CLAIMED, is_demo=False, due_past=True)

    #  ── OR 의 가지 ② — 무응답(ST_OPEN, due_at 없음 + created_at 오래됨) ──
    cid_demo_b = mkcase("demoB", True)
    did_demo_b = mkdispatch(cid_demo_b, DP.ST_OPEN, is_demo=True, created_old=True)
    cid_real_b = mkcase("realB", False)
    did_real_b = mkdispatch(cid_real_b, DP.ST_OPEN, is_demo=False, created_old=True)
    conn.commit()

    n_log_before = conn.execute(
        "SELECT COUNT(*) c FROM activity_log WHERE action='출동 실패'").fetchone()["c"]
    r = DP.sweep_dispatches(conn, force=True)
    n_log_after = conn.execute(
        "SELECT COUNT(*) c FROM activity_log WHERE action='출동 실패'").fetchone()["c"]

    def dstatus(did):
        return conn.execute("SELECT status FROM dispatches WHERE id=?", (did,)).fetchone()["status"]

    chk(dstatus(did_demo_a) == DP.ST_CLAIMED,
        "★★★★★ 가지①(제한시간 초과) 데모 수배는 그대로 남는다"
        "(수정 전엔 AND 결합력 함정으로 바로 이 가지가 새고 있었다)", dstatus(did_demo_a))
    chk(dstatus(did_demo_b) == DP.ST_OPEN,
        "★★★★ 가지②(무응답) 데모 수배도 그대로 남는다", dstatus(did_demo_b))
    chk(dstatus(did_real_a) == DP.ST_FAILED,
        "STEP 대조군 — 가지① 실제 수배는 정상적으로 실패 처리된다(과잉차단 아님)",
        dstatus(did_real_a))
    chk(dstatus(did_real_b) == DP.ST_FAILED,
        "STEP 대조군 — 가지② 실제 수배도 정상적으로 실패 처리된다", dstatus(did_real_b))
    chk(n_log_after - n_log_before == 2,
        "★★★★★ 감사로그(\"출동 실패\")는 실제 수배 2건 분량만 남는다(데모 0건)",
        f"{n_log_before}→{n_log_after}")
    chk(r["expired"] == 2, "STEP 스윕 자신도 실제 2건만 처리했다고 집계한다", r)

    for did in (did_demo_a, did_demo_b, did_real_a, did_real_b):
        conn.execute("DELETE FROM dispatches WHERE id=?", (did,))
    for cid in (cid_demo_a, cid_demo_b, cid_real_a, cid_real_b):
        conn.execute("DELETE FROM cases WHERE id=?", (cid,))
    conn.commit()
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드257 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
