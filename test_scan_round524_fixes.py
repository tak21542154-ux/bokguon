# -*- coding: utf-8 -*-
"""스캔 524라운드 회귀 — dispatch.py:_claim_lease()(742행, 출동수배 스윕의
   리스 확보)가 "BEGIN IMMEDIATE" 문 자체는 여전히 try 밖에 남겨 둔 결함.

  직접 조사(하위위임 없음) — round523이 남긴 리드를 그대로 따랐다: "app.py에는
  이 두 스윕(auction_sweep·dispatch_sweep) 외에도 sweep_* 함수가 총 8종
  있다 — 이들 중 _sweep_claim/_sweep_release처럼 자기만의 리스(job_locks)
  기전을 따로 갖고 있는 게 있는지 확인하라." app.py의 sweep_no_bid_alert·
  sweep_report_overdue·sweep_review_reminders·sweep_warranty_expiry·
  sweep_approval_overdue·_sweep_award_approval·sweep_webhook_retries·
  sweep_send_notifications 8종을 전부 직접 Read로 대조한 결과 전부 자기
  도메인 테이블(notifications 등)에 BEGIN IMMEDIATE로 직접 dedup을 거는
  방식이지 job_locks 기반의 별도 리스는 없었다 — job_locks grep 전수로도
  auction_sweep·dispatch_sweep 두 벌뿐임을 재확인, 이 리드 자체는 막다른
  길로 확인됨.

  그런데 그 확인 과정에서 dispatch.py의 _claim_lease()(app.py _sweep_claim의
  형제, round482가 최초로 고치고 round523이 "이미 방어됨"으로 인용한 바로 그
  함수)를 다시 읽다가, round523 자신의 회귀테스트(test_scan_round523_fixes.py
  132행)가 이미 "dispatch.py 형제(_claim_lease)는 BEGIN IMMEDIATE 가 try
  밖이라 이 지점은 더 얕게 방어된다"고 스스로 적어 뒀으면서도 그 잔여 결함은
  이 파일(app.py) 범위 밖이라며 넘기지 않기로 한 것을 발견했다. 실제 코드를
  보면 round482의 수정은 UPDATE·commit·rollback 은 try/except sqlite3.Error
  로 감쌌지만 그 앞의 conn.execute("BEGIN IMMEDIATE") 한 줄은 try 블록
  **이전**에 그대로 남아 있었다(round482 자신의 회귀테스트도 job_locks
  테이블을 DROP해 UPDATE만 실패시켰을 뿐 BEGIN IMMEDIATE 자체를 실패시키는
  경우는 검증하지 않아 이 구멍을 못 잡았다).

  영향 — db.py가 모든 커넥션에 PRAGMA busy_timeout(BUSY_TIMEOUT_MS)을 걸어
  두므로, 다른 커넥션이 이미 RESERVED/EXCLUSIVE 락을 쥔 채 시간을 넘기면
  BEGIN IMMEDIATE 문 자체가 UPDATE보다 먼저 sqlite3.OperationalError
  ("database is locked")를 던진다 — 바로 이 자리가 "겹친 예약실행을 막는"
  리스 기전이 스스로 가장 경합을 부르는 지점이라고 두 형제 함수의 주석이
  이미 공통으로 지목해 온 곳이다. 이 예외는 호출부 sweep_dispatches()
  (force 인자 없이 부르는 유일한 실경로 — manage.py:1019 cmd_sweep)의 try
  블록 밖에서 일어나므로 그대로 새어나가고, cmd_sweep()의 유일한 try(989-
  1032행)에도 except가 없어(finally만 있음) 그 회차의 sweep_send_notifications
  ·sweep_webhook_retries·생존신호(job_locks cli_sweep 갱신)까지 통째로
  건너뛴다 — 이 경로는 실제 Windows 작업 스케줄러가 주기적으로 pythonw.exe
  로 도는 cmd_sweep() 그 자체다(app.py의 관리자 수동버튼 api_admin_sweep은
  force=True라 sweep_dispatches 호출 시 _claim_lease가 아예 안 걸림 — 그
  경로는 영향 밖).

  고침 — dispatch.py:_claim_lease()의 conn.execute("BEGIN IMMEDIATE")를
  try 블록 **안**으로 옮겨 형제 app.py:_sweep_claim()(round523)과 정확히
  같은 모양으로 맞췄다. except 블록의 rollback도 형제처럼 자신만의
  try/except sqlite3.Error로 한 번 더 감쌌다(BEGIN IMMEDIATE 자체가
  실패했을 때는 열린 트랜잭션이 없어 rollback이 무의미하거나 추가 예외를
  낼 수 있기 때문 — round523과 동일한 방어). 새 헬퍼·새 상수 없음.

  [1] 소스 확인 — _claim_lease() 본문에서 try: 가 BEGIN IMMEDIATE 보다
      먼저 오고, except sqlite3.Error: 가 두 번(본체 + rollback 자신을
      감싸는 안쪽), rollback 두 번, [라운드524] 표식이 정확히 1번.
  [2] 실행(순수 단위) — 가짜 conn 으로 ① BEGIN IMMEDIATE 실패 ② UPDATE
      실패 각각 예외 없이 False 반환 + rollback 1회 + commit 0회 확인,
      대조군으로 ③ rowcount=0(락 경합 없음) ④ 정상성공(rowcount=1) 모두
      회귀 없음 확인.
  [3] 실행(경로 통합) — 실제 스크래치 DB(DB.init_db())의 진짜 job_locks
      dispatch_sweep 행 위에서, 진짜 커넥션을 감싸되 BEGIN IMMEDIATE
      호출만 락 경합처럼 실패시키는 프록시를 (a) DP._claim_lease(proxy)
      에 직접 넣어 예외 없이 False + rollback이 실제로 되어 바로 다음
      진짜 시도가 "cannot start a transaction" 없이 성공함을 확인,
      (b) 기한 지난 수배(dispatches) 행을 실제로 심고 그 프록시를
      DP.sweep_dispatches(proxy)(=cmd_sweep 이 실제로 쓰는 force 생략
      호출 모양)에 넣어 claimed=False로 물러나며 그 수배 행이 전혀
      안 건드려짐을 확인.
  [4] 되돌림-증명 — dispatch.py 자체는 건드리지 않고(동시 세션이 이
      파일을 같이 건드릴 수 있는 환경 — round520-523과 같은 원칙) 이
      라운드 이전 실제 코드(BEGIN IMMEDIATE가 try 밖)를 테스트 안에만
      재구성해 같은 가짜 conn 에 돌려 sqlite3.OperationalError가 그대로
      새는 것을 확인 — 새 코드([2]-①)와 대조해 이 회귀가 진짜 그
      차이를 잡아낼 능력이 있음을 증명한다.

      python test_scan_round524_fixes.py
"""
import os
import shutil
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


DP_PATH = os.path.join(HERE, "dispatch.py")
DP_SRC = open(DP_PATH, encoding="utf-8").read()

print("=" * 72)
print("  스캔 524라운드 회귀 — dispatch._claim_lease() BEGIN IMMEDIATE 무방비 잔여분")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
fn_body = _py_fn_body(DP_SRC, "_claim_lease")
chk("[라운드524]" in fn_body, "★★★ 새 코드가 _claim_lease() 본문 안에 있다")
chk(DP_SRC.count("[라운드524]") == 1, "라운드524 표식이 전체 소스에 정확히 1번뿐(중복 삽입 아님)")
chk(DP_SRC.count("def _claim_lease(") == 1, "함수 정의가 정확히 1번(중복 정의 없음)")

_try_idx = fn_body.find("try:")
_begin_idx = fn_body.find('conn.execute("BEGIN IMMEDIATE")')
_update_idx = fn_body.find("UPDATE job_locks SET lease_until")
_except_idx = fn_body.find("except sqlite3.Error:")
chk(-1 not in (_try_idx, _begin_idx, _update_idx, _except_idx),
    "함수 안에 try:·BEGIN IMMEDIATE·UPDATE·except sqlite3.Error: 가 전부 있다",
    (_try_idx, _begin_idx, _update_idx, _except_idx))
chk(0 <= _try_idx < _begin_idx < _update_idx < _except_idx,
    "★★★ try: 가 BEGIN IMMEDIATE 보다 먼저 온다(그 문장 자체도 이제 보호 대상) — "
    "형제 app.py _sweep_claim()(round523)과 이제 같은 모양",
    (_try_idx, _begin_idx, _update_idx, _except_idx))
chk(fn_body.count("conn.rollback()") == 2,
    "★★★ rollback 이 두 자리(정상 실패 분기·예외 분기)에서 불린다")
chk(fn_body.count("except sqlite3.Error:") == 2,
    "★★★ except sqlite3.Error: 가 두 번(함수 본체 + rollback 자신을 감싸는 안쪽) 나온다 — "
    "형제 app.py _sweep_claim()과 같은 관례")
chk(fn_body.rstrip().endswith("return False"),
    "실패 경로(except)는 여전히 False 로 끝난다(예외를 밖으로 던지지 않음)")
chk("_log.exception(" in fn_body, "실패를 _log.exception 으로 남긴다(형제 _release_lease()의 관례)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행(순수 단위) — 가짜 conn 으로 BEGIN IMMEDIATE·UPDATE 각각의 실패를 재현")
# ──────────────────────────────────────────────────────────────
sys.path.insert(0, HERE)
_tmpdir = tempfile.mkdtemp(prefix="round524_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"


class _FakeCursor:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount


class _FakeConn:
    """execute() 는 sql 종류별로 원하는 결과/예외를 낸다.
       fail_on : 이 부분문자열을 포함한 sql 이 오면 sqlite3.OperationalError.
       update_rowcount : UPDATE 문에 대해 돌려줄 cur.rowcount.
    """

    def __init__(self, fail_on=None, update_rowcount=1):
        self.fail_on = fail_on
        self.update_rowcount = update_rowcount
        self.rollback_calls = 0
        self.commit_calls = 0

    def execute(self, sql, params=()):
        s = sql.strip()
        if self.fail_on and self.fail_on in sql:
            raise sqlite3.OperationalError("database is locked")
        return _FakeCursor(self.update_rowcount if s.startswith("UPDATE") else 1)

    def rollback(self):
        self.rollback_calls += 1

    def commit(self):
        self.commit_calls += 1


try:
    import dispatch as DP

    # ① BEGIN IMMEDIATE 자체가 락 경합으로 실패
    fc1 = _FakeConn(fail_on="BEGIN IMMEDIATE")
    r1 = DP._claim_lease(fc1)
    chk(r1 is False,
        "★★★★★ BEGIN IMMEDIATE 락 경합 — 예외가 새지 않고 False 를 반환한다"
        "(고치기 전엔 sqlite3.OperationalError 가 그대로 새어나갔다)", r1)
    chk(fc1.rollback_calls == 1, "  BEGIN IMMEDIATE 실패 후 rollback 이 정확히 1번 불린다", fc1.rollback_calls)
    chk(fc1.commit_calls == 0, "  commit 은 불리지 않는다", fc1.commit_calls)

    # ② BEGIN IMMEDIATE는 성공하지만 UPDATE가 락 경합으로 실패
    fc2 = _FakeConn(fail_on="UPDATE job_locks")
    r2 = DP._claim_lease(fc2)
    chk(r2 is False,
        "★★★ UPDATE 락 경합 — 예외가 새지 않고 False 를 반환한다"
        "(round482가 이미 지킨 계약, 회귀 없음)", r2)
    chk(fc2.rollback_calls == 1, "  UPDATE 실패 후 rollback 이 정확히 1번 불린다", fc2.rollback_calls)
    chk(fc2.commit_calls == 0, "  commit 은 불리지 않는다", fc2.commit_calls)

    # ③ 대조군 — 락 경합이 전혀 없어도 rowcount=0(다른 워커가 리스 보유중)이면
    #    여전히 예외 없는 False 다(회귀 없음).
    fc3 = _FakeConn(fail_on=None, update_rowcount=0)
    r3 = DP._claim_lease(fc3)
    chk(r3 is False,
        "대조 — 락 경합 없이 rowcount=0(다른 워커가 리스 보유중)이어도 "
        "여전히 예외 없는 False (회귀 없음)", r3)
    chk(fc3.rollback_calls == 1 and fc3.commit_calls == 0,
        "  이 경우도 rollback 만 불리고 commit 은 없다", (fc3.rollback_calls, fc3.commit_calls))

    # ④ 대조군 — 아무 문제 없으면(rowcount=1) 여전히 True + commit(회귀 없음).
    fc4 = _FakeConn(fail_on=None, update_rowcount=1)
    r4 = DP._claim_lease(fc4)
    chk(r4 is True, "대조 — 정상 상황(락 경합 없음·rowcount=1)은 여전히 True (회귀 없음)", r4)
    chk(fc4.commit_calls == 1 and fc4.rollback_calls == 0,
        "  정상 성공 경로는 commit 만 1번, rollback 은 없음", (fc4.commit_calls, fc4.rollback_calls))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] 순수 단위 실행", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행(경로 통합) — 실제 스크래치 DB + sweep_dispatches(force 생략)")
# ──────────────────────────────────────────────────────────────
try:
    import db as DB
    DB.init_db()

    class _LockFailProxy:
        """진짜 sqlite3 커넥션을 감싸 BEGIN IMMEDIATE 호출만 락 경합처럼 실패시킨다.
           그 외(SELECT·commit·rollback·close 등)는 전부 진짜 커넥션에 위임한다 —
           sweep_dispatches() 가 실제로 마주치는 상황(다른 커넥션이 이미 RESERVED
           락을 쥐고 있어 busy_timeout 초과)을 재현한다."""

        def __init__(self, real):
            self._real = real
            self.begin_immediate_calls = 0

        def execute(self, sql, *a, **kw):
            if sql.strip() == "BEGIN IMMEDIATE":
                self.begin_immediate_calls += 1
                raise sqlite3.OperationalError("database is locked")
            return self._real.execute(sql, *a, **kw)

        def __getattr__(self, name):
            return getattr(self._real, name)

    real_conn = DB.get_db()

    # (a) _claim_lease() 를 직접 프록시로 불러 예외 없이 False + rollback 증명
    proxy1 = _LockFailProxy(real_conn)
    r_direct = DP._claim_lease(proxy1)
    chk(r_direct is False,
        "★★★★★ 실제 job_locks(dispatch_sweep) 행 위에서도 BEGIN IMMEDIATE 락 경합 시 "
        "예외 없이 False 를 반환한다", r_direct)
    chk(proxy1.begin_immediate_calls == 1, "  BEGIN IMMEDIATE 시도는 1번뿐", proxy1.begin_immediate_calls)

    # rollback이 실제로 됐다는 증거 — 같은 커넥션으로 바로 다음 진짜 시도가
    # "cannot start a transaction" 없이 정상 성공한다(411라운드가 겪은 것과 같은 클래스).
    r_real_followup = DP._claim_lease(real_conn)
    chk(r_real_followup is True,
        "★★★★★ 직후 같은 커넥션의 진짜 _claim_lease() 시도가 정상 성공한다 — "
        "실패한 BEGIN IMMEDIATE 뒤 rollback이 실제로 커넥션을 깨끗하게 되돌렸다는 증거",
        r_real_followup)
    DP._release_lease(real_conn, "r524-테스트-해제")  # 다음 단계를 위해 리스를 다시 비운다

    # (b) 기한 지난 수배를 실제로 심고, sweep_dispatches(proxy)(=cmd_sweep 이 실제로
    #     쓰는 force 생략 호출 모양)로 전체 경로를 통합 검증한다.
    did = real_conn.execute(
        "INSERT INTO dispatches(case_id,status,due_at,created_at) VALUES(?,?,?,?)",
        (999999, DP.ST_CLAIMED, "2020-01-01 00:00:00", DB.now())).lastrowid
    real_conn.commit()

    proxy2 = _LockFailProxy(real_conn)
    res = DP.sweep_dispatches(proxy2)
    chk(res.get("claimed") is False,
        "★★★★★ 실제 sweep_dispatches() 경로에서도 BEGIN IMMEDIATE 락 경합 시 예외 없이 "
        "claimed=False 로 물러난다(cmd_sweep 이 이 신호를 받아 나머지 스윕을 계속 돌릴 수 있다)",
        res)
    chk(proxy2.begin_immediate_calls == 1,
        "  BEGIN IMMEDIATE 시도는 1번뿐(실패 후 재시도하지 않고 바로 물러난다)",
        proxy2.begin_immediate_calls)
    row = real_conn.execute("SELECT status FROM dispatches WHERE id=?", (did,)).fetchone()
    chk(row["status"] == DP.ST_CLAIMED,
        "  리스를 못 잡았으니 그 수배 행은 전혀 안 건드려졌다(상태 그대로)", dict(row))
    real_conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] 경로 통합 실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌림-증명 — 라운드524 이전 실제 코드 그대로면 예외가 정말 샜는가")
# ──────────────────────────────────────────────────────────────


def _old_claim_lease(conn, lease_sec=120):
    """라운드524 이전 실제 코드 그대로(BEGIN IMMEDIATE 가 try 밖) — 비교용으로
       이 테스트 안에만 재구성한다(dispatch.py 자체는 건드리지 않는다 — 동시
       세션이 이 파일을 같이 건드릴 수 있는 환경이라 round520-523 과 같은
       원칙으로 전체 소스 스왑 대신 여기서만 옛 로직을 재현한다)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        cur = conn.execute(
            "UPDATE job_locks SET lease_until = datetime('now','+9 hours', ?) "
            " WHERE name='dispatch_sweep' AND lease_until <= datetime('now','+9 hours')",
            (f"+{lease_sec} seconds",))
        if not cur.rowcount:
            conn.rollback()
            return False
        conn.commit()
        return True
    except sqlite3.Error:
        conn.rollback()
        return False


try:
    fc_old = _FakeConn(fail_on="BEGIN IMMEDIATE")
    raised = False
    try:
        _old_claim_lease(fc_old)
    except sqlite3.OperationalError:
        raised = True
    chk(raised,
        "★★★★★ 옛 코드(BEGIN IMMEDIATE 가 try 밖)는 같은 락 경합 상황에서 "
        "sqlite3.OperationalError 를 그대로 밖으로 던진다 — 이 회귀가 실제로 "
        "막던 결함을 재현(새 코드[2]-①은 똑같은 입력에 False 를 반환했다)", raised)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [4] 되돌림-증명", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
