# -*- coding: utf-8 -*-
"""스캔 482라운드 회귀 — dispatch.py의 _claim_lease()가 이 파일의 다른
BEGIN IMMEDIATE 10곳과 달리 try/except 없이 벌거벗어 있던 결함, 1건
(정밀조사 Agent가 11개 BEGIN IMMEDIATE 전수 대조로 발견).

  호출부(sweep_dispatches(), dispatch.py:766)도 이 호출을 자기 자신의
  try 블록(770행) **밖**에서 하므로, UPDATE가 예외를 던지면(락 경합으로
  busy-timeout 초과 등 — 이 리스 자체가 "겹친 예약실행을 막는" 용도라
  락 경합이 바로 이 자리에서 가장 일어나기 쉽다) sweep_dispatches() 밖
  까지 그대로 터진다. manage.py cmd_sweep()의 유일한 try(989-1032행)에도
  except가 없어(finally만 있음) 그 회차의 sweep_send_notifications·
  sweep_webhook_retries·생존신호(job_locks cli_sweep 갱신)까지 통째로
  건너뛴다 — main()(2725-2734행)도 COMMANDS[cmd] 호출을 try로 안 감싸
  예외가 프로세스를 그대로 죽인다. 이 경로는 실제 Windows 작업 스케줄러가
  5분마다 pythonw.exe로 도는 그 경로다(app.py의 관리자 수동버튼은
  force=True라 _claim_lease를 아예 안 부름 — 이 경로는 안 걸림).

  고침: 형제 _release_lease()(dispatch.py:720-731, 리스 확보 실패는
  120초/5분 뒤 자연회복되는 문제라 예외를 삼키고 로그만 남기는 원칙)와
  같은 원칙 — 예외를 삼켜 호출부의 기존 정상 경로("다른 워커가 리스를
  쥐고 있음", claimed=False)로 합류시킨다. rollback은 이 함수가 BEGIN
  IMMEDIATE를 직접 여는 유일한 자리라 커밋 안 된 트랜잭션을 반드시
  닫아야 다음 BEGIN IMMEDIATE가 "cannot start a transaction"으로 안
  터진다(411라운드가 이미 겪은 것과 같은 클래스).

  [1] 소스 확인 — _claim_lease()가 이제 try/except/rollback을 가짐.
  [2] 실제 실행 — job_locks 테이블을 일부러 지워 UPDATE 자체가 예외를
      던지게 만든 뒤, (a) False를 반환하고 예외가 안 새는지 (b) 같은
      커넥션의 다음 BEGIN IMMEDIATE가 "cannot start a transaction" 없이
      정상 진행되는지(rollback이 실제로 됐다는 증거) 확인.
  [3] 되돌림-증명 — 옛(벌거벗은) 코드로 임시 되돌려 같은 시나리오에서
      예외가 실제로 새 나가는지 대조.

⚠⚠ [라운드616] 되돌림-증명 기법을 옛 세대(dispatch.py를 실제로 디스크에
  써넣고 재현한 뒤 복원)에서 round488/round414가 확립한 안전패턴으로
  이관한다 — _claim_lease()는 다른 함수가 바깥에서 이 라운드가 다루는
  범위 안에서 이름으로 부르지 않는 평범한 모듈 함수라, OLD_BLOCK을 실제
  dispatch 모듈의 독립 사본 네임스페이스(dict(vars(DP)))에 exec해 얻은
  함수 객체를 직접 호출한다 — 진짜 dispatch.py 파일은 전혀 안 쓴다.
"""
import hashlib
import io
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 482라운드 회귀 — dispatch._claim_lease() 무방비 BEGIN IMMEDIATE")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
DP_PATH = os.path.join(HERE, "dispatch.py")
DP_SRC = io.open(DP_PATH, encoding="utf-8").read()
DP_HASH_BEFORE = hashlib.sha256(DP_SRC.encode("utf-8")).hexdigest()

OLD_BLOCK = '''def _claim_lease(conn):
    conn.execute("BEGIN IMMEDIATE")
    cur = conn.execute(
        "UPDATE job_locks SET lease_until = datetime('now','+9 hours', ?) "
        " WHERE name='dispatch_sweep' AND lease_until <= datetime('now','+9 hours')",
        (f"+{SWEEP_LEASE_SEC} seconds",))
    if not cur.rowcount:
        conn.rollback()
        return False
    conn.commit()
    return True'''

_i = DP_SRC.find("def _claim_lease(conn):")
_j = DP_SRC.find("\n\n\ndef _release_lease(conn, note):", _i)
NEW_BLOCK = DP_SRC[_i:_j] if _i > 0 and _j > 0 else ""

chk(_i > 0, "_claim_lease() 함수를 소스에서 찾았다")
chk("except sqlite3.Error" in NEW_BLOCK and "conn.rollback()" in NEW_BLOCK
    and "return False" in NEW_BLOCK,
    "★★★★★ try/except로 감싸 예외를 삼키고 rollback 후 False를 반환한다",
    NEW_BLOCK[-300:] if NEW_BLOCK else "블록을 못 뽑음")
chk(DP_SRC.count(NEW_BLOCK) == 1 and len(NEW_BLOCK) > 0,
    "되돌림-증명에 쓸 새 블록이 소스에 정확히 1번만 있다(대체 지점 특정 가능)",
    DP_SRC.count(NEW_BLOCK) if NEW_BLOCK else "블록을 못 뽑음")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 실행 — job_locks 를 지워 UPDATE 자체가 예외를 던지게 함")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="r482_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
import db as DB               # noqa: E402
import dispatch as DP         # noqa: E402


def _run_scenario(claim_fn):
    """job_locks 를 지운 새 스크래치 DB에서 claim_fn(conn) 을 실제로 부른다.
    claim_fn 은 실제 DP._claim_lease 이거나, OLD_BLOCK을 독립 사본
    네임스페이스에 exec해 얻은 되돌림판 함수 객체다(dispatch.py 자체는
    안 건드림). 반환: (raised_exception_or_None, claim_result_or_None,
    next_begin_immediate_ok)."""
    DB.init_db()
    conn = DB.get_db()
    conn.execute("DROP TABLE job_locks")
    conn.commit()

    raised = None
    result = None
    try:
        result = claim_fn(conn)
    except Exception as e:                                          # noqa: BLE001
        raised = e

    next_ok = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.rollback()
        next_ok = True
    except sqlite3.OperationalError as e:
        next_ok = False if "transaction" in str(e) else None
    conn.close()
    return raised, result, next_ok


try:
    raised, result, next_ok = _run_scenario(DP._claim_lease)
    chk(raised is None,
        "★★★★★ 새 코드: UPDATE가 예외를 던져도 _claim_lease() 밖으로 안 샌다",
        f"{type(raised).__name__}: {raised}" if raised else "")
    chk(result is False,
        "★★★★★ 새 코드: 예외 상황에서 False를 반환한다(호출부의 기존 "
        "'다른 워커가 리스를 쥐고 있음' 경로로 합류)", result)
    chk(next_ok is True,
        "★★★★★ 새 코드: rollback이 실제로 됐다 — 같은 커넥션의 다음 "
        "BEGIN IMMEDIATE가 'cannot start a transaction' 없이 정상 진행된다",
        next_ok)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2] 실행 준비/실행", f"{type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 되돌림-증명 — OLD_BLOCK을 독립 사본 네임스페이스에 exec해 직접 호출(실제 파일은 안 건드림)")
# ──────────────────────────────────────────────────────────────
try:
    _ns = dict(vars(DP))
    exec(compile(OLD_BLOCK, "<round482_reverted_claim_lease>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_claim_lease = _ns["_claim_lease"]
    raised2, result2, next_ok2 = _run_scenario(old_claim_lease)
    chk(raised2 is not None and isinstance(raised2, sqlite3.OperationalError),
        "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림)는 UPDATE의 예외가 "
        "_claim_lease() 밖으로 그대로 샌다 — 이 테스트가 진짜 결함을 잡아낼 "
        "능력이 있음을 증명",
        f"{type(raised2).__name__}: {raised2}" if raised2 else "예외 없음(반환값 " + repr(result2) + ")")
    chk(DP._claim_lease is not old_claim_lease,
        "  (준비) 실제 dispatch.DP._claim_lease는 되돌림판과 다른 객체다(스왑 아님, 독립 사본 호출)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "[3] 되돌림-증명 준비/실행", f"{type(e).__name__}: {e}")

DP_HASH_AFTER = hashlib.sha256(io.open(DP_PATH, encoding="utf-8").read().encode("utf-8")).hexdigest()
chk(DP_HASH_AFTER == DP_HASH_BEFORE,
    "★★★★★ dispatch.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(독립 사본 네임스페이스 exec만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
