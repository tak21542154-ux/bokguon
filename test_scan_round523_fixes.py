# -*- coding: utf-8 -*-
"""스캔 523라운드 회귀 — app.py:_sweep_claim()(경매마감 스윕의 리스 확보)이
   sqlite3.Error 를 전혀 잡지 않던 결함.

  직접 조사(하위위임 없음) — 이미 포화된 축(형제 엔드포인트 잠금 비대칭 504-507,
  지역문자열 독자구현 511·512·516, 정책문서-실제설정 불일치, partners.website
  XSS/SSRF, cp949 콘솔인코딩 518·519, "형제 함수가 보안/알림 사후처리를 못
  물려받는다" 520·521·522(포화 처리됨 — 재조사 금지), 독촉/재알림 쿨다운,
  change_orders 생애주기, DUP_BIZNO, 개인정보파기 6버킷, activity_log 마스킹,
  가운뎃점 정규화, 출동수배 버튼 등급게이트, catch분기 화면정리, 입점신청
  상태역전, 권한데코레이터 260개 라우트 전수)과 겹치지 않는 완전히 새 각도로
  "예약실행/스윕 스크립트의 동시성·멱등성"을 지시받아 조사했다.

  먼저 후보 ①manage.py CLI 서브커맨드(backup·restore·prune-personal·
  prune-logs·set-fee·reset-pw)를 감사했으나 round292·342·446·109·142·179·
  188·263·495 등으로 이미 극도로 두껍게 방어돼 있었다(트랜잭션 경계·부분실행
  복구·--yes/--force 게이트 전부 촘촘함). 후보 ②repair_estimate.py(공종 개산
  계산식)도 round69·201·247·314·462 로 이미 손을 댄 상태라 경계값·검증로직이
  전부 클린했다. 후보 ③(스윕 동시성)으로 넘어가 app.py 의 sweep_* 8종과
  dispatch.py 의 sweep_dispatches 를 나란히 대조하다가, "겹친 스윕을 막는"
  리스(job_locks) 기전이 두 벌 — app.py 의 _sweep_claim/_sweep_release
  (job_locks.name='auction_sweep') 와 dispatch.py 의 _claim_lease/
  _release_lease(name='dispatch_sweep') — 로 나란히 존재하는 것을 발견했다.

  결함 — app.py:_sweep_claim()(5765행)은 conn.execute("BEGIN IMMEDIATE") 와
  뒤이은 UPDATE 를 어떤 예외 처리도 없이 그대로 실행했다. 정확히 같은 목적·
  같은 모양을 가진 두 형제 — 같은 파일의 _sweep_release()(5779행, 이미
  try/except sqlite3.Error 로 감쌈)와 dispatch.py 의 _claim_lease()(742행,
  round482 가 "이 파일의 다른 BEGIN IMMEDIATE 10곳은 전부 try/except로
  감싸는데 여기만 없었다"며 이미 고친 바로 그 결함 클래스) — 는 둘 다 이미
  방어돼 있는데, 원조격인 이 함수만 무방비로 남아 있었다. 이 리스 자체가
  "겹친 스윕 실행을 막는" 용도라 락 경합(다른 커넥션이 이미 BEGIN IMMEDIATE
  로 RESERVED 락을 쥐고 있어 busy_timeout 초과 — db.py BUSY_TIMEOUT_MS=8초)이
  바로 이 자리에서 가장 일어나기 쉽다.

  영향 경로 확인 — sweep_auctions() 를 부르는 곳은 셋인데, manage.py
  cmd_sweep()·api_admin_sweep() 은 둘 다 force=True 를 넘겨 단락평가로
  _sweep_claim() 자체가 아예 호출되지 않는다(예약 실행·관리자 수동 버튼은
  이 결함의 영향 밖). 이 함수를 실제로 호출하는 유일한 경로는
  _sweep_if_due()(6850행, force 인자 없이 기본값 False 로 호출)인데, 이건
  관리자 대시보드·보험사 포털·협력사 공고 목록을 열 때마다 곁들여 도는
  인라인 스윕이다(3535·6888·20997·21025행 네 곳에서 트리거). 거기서 이
  예외가 새면, _sweep_if_due() 의 바깥 try 블록이 sweep_auctions() 다음에
  잇달아 부르는 나머지 네 스윕(sweep_no_bid_alert·sweep_report_overdue·
  sweep_review_reminders·sweep_warranty_expiry)까지 그 호출 전체가 통째로
  건너뛰는데, _LAST_INLINE_SWEEP 타임스탬프는 이미 갱신돼 있어 다음 60초
  (INLINE_SWEEP_GAP_SEC) 동안 재시도조차 안 열리고, _sweep_if_due() 의
  바깥 except 는 로그 한 줄 없이 삼켜 아무도 이 사실을 못 알아챈다.

  고침 — app.py:_sweep_claim() 을 형제 두 곳과 같은 원칙으로 try/except
  sqlite3.Error 로 감쌌다. BEGIN IMMEDIATE 문 자체까지 try 안에 넣어
  dispatch.py 형제보다 한 겹 더 방어한다(그 형제는 BEGIN IMMEDIATE 이
  try 밖에 있어 그 문장 자체에서 나는 예외는 여전히 샌다 — 이 파일은 그
  잔여 결함까지 옮기지 않는다). 실패하면 app.logger.exception() 으로
  남기고(형제 스윕들의 "~점검 잠금 실패" 관례를 그대로 따름) rollback 도
  자신만의 try/except 로 한 번 더 감싸(sweep_report_overdue 등 이 파일의
  지배적 관례) False 를 반환한다 — 이 함수 자신의 독스트링이 이미 약속한
  계약("실패는 예외가 아니라 False") 그대로다. 새 헬퍼·새 상수 없음.

  [1] 소스 확인 — _sweep_claim() 본문이 try: 로 시작해 BEGIN IMMEDIATE 와
      UPDATE 를 모두 그 try 안에서 실행하고, except sqlite3.Error: 가
      app.logger.exception 뒤에 rollback 을 자신만의 try/except 로 한 번
      더 감싸 False 를 반환함을 소스에서 직접 확인.
  [2] 실행(순수 단위) — sqlite3.Connection 을 흉내 낸 가짜 conn 으로
      ① BEGIN IMMEDIATE 자체가 락 경합으로 실패하는 경우 ② UPDATE 가
      락 경합으로 실패하는 경우를 각각 A._sweep_claim() 에 직접 넣어,
      예외가 새지 않고 False 가 돌아오며 rollback 은 정확히 1번 불리고
      commit 은 전혀 안 불림을 확인. 대조군으로 ③ 락 경합이 없어도
      rowcount=0(다른 워커가 이미 리스 보유)이면 여전히 예외 없는 False,
      ④ 아무 문제 없으면 여전히 True+commit(둘 다 회귀 없음)까지 확인.
  [3] 실행(경로 통합) — 실제 스크래치 sqlite3 DB + DB.init_db() 로 만든
      진짜 job_locks 행 위에서, 진짜 커넥션을 감싸되 "BEGIN IMMEDIATE"
      호출만 락 경합처럼 실패시키는 얇은 프록시를
      A.sweep_auctions(proxy)(=_sweep_if_due() 가 실제로 쓰는 그 호출
      모양, force 생략=False) 에 넣어, 마감 지난 경매가 실제로 있어도
      (n>0) 예외가 새지 않고 res["claimed"] is False 로 깔끔히 물러나며
      그 경매 행은 전혀 안 건드려짐을 확인.
  [4] 되돌림-증명 — 이 라운드 이전 코드 그대로(try/except 없이 BEGIN
      IMMEDIATE + UPDATE 를 바로 실행)를 이 테스트 안에만 재구성해
      (app.py 자체는 건드리지 않음 — 동시 세션이 app.py 를 같이 건드릴
      수 있는 환경이라 round520-522 와 같은 원칙) 같은 가짜 conn 에
      돌려, 그 옛 코드는 예외를 그대로 밖으로 새게 함을 확인 — [2]의
      새 코드와 대조해 이 회귀가 진짜 그 차이(try/except 유무)를
      잡아낼 능력이 있음을 증명한다.

      python test_scan_round523_fixes.py
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


APP_SRC = open(os.path.join(HERE, "app.py"), encoding="utf-8").read()

print("=" * 72)
print("  스캔 523라운드 회귀 — _sweep_claim() 락 경합 예외 미처리")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
fn_body = _py_fn_body(APP_SRC, "_sweep_claim")
chk("[라운드523]" in fn_body, "★★★ 새 코드가 _sweep_claim() 본문 안에 있다")
chk(APP_SRC.count("[라운드523]") == 1, "라운드523 표식이 전체 소스에 정확히 1번뿐(중복 삽입 아님)")
chk(APP_SRC.count("def _sweep_claim(") == 1, "함수 정의가 정확히 1번(중복 정의 없음)")

_try_idx = fn_body.find("try:")
_begin_idx = fn_body.find('conn.execute("BEGIN IMMEDIATE")')
_update_idx = fn_body.find("UPDATE job_locks SET lease_until")
_except_idx = fn_body.find("except sqlite3.Error:")
chk(-1 not in (_try_idx, _begin_idx, _update_idx, _except_idx),
    "함수 안에 try:·BEGIN IMMEDIATE·UPDATE·except sqlite3.Error: 가 전부 있다",
    (_try_idx, _begin_idx, _update_idx, _except_idx))
chk(0 <= _try_idx < _begin_idx < _update_idx < _except_idx,
    "★★★ try: 가 BEGIN IMMEDIATE 보다 먼저 온다(그 문장 자체도 보호 대상) — "
    "dispatch.py 형제(_claim_lease)는 BEGIN IMMEDIATE 가 try 밖이라 이 지점은 더 얕게 방어된다",
    (_try_idx, _begin_idx, _update_idx, _except_idx))
chk("app.logger.exception(" in fn_body,
    "실패를 app.logger.exception 으로 남긴다(형제 스윕들의 '~점검 잠금 실패' 관례)")
chk(fn_body.count("conn.rollback()") == 2,
    "★★★ rollback 이 두 자리(정상 실패 분기·예외 분기)에서 불린다")
chk(fn_body.count("except sqlite3.Error:") == 2,
    "★★★ except sqlite3.Error: 가 두 번(함수 본체 + rollback 자신을 감싸는 안쪽) 나온다 — "
    "sweep_report_overdue 등 이 파일의 지배적 관례와 같다")
chk(fn_body.rstrip().endswith("return False"),
    "실패 경로(except)는 여전히 False 로 끝난다(예외를 밖으로 던지지 않음)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행(순수 단위) — 가짜 conn 으로 BEGIN IMMEDIATE·UPDATE 각각의 실패를 재현")
# ──────────────────────────────────────────────────────────────
sys.path.insert(0, HERE)
_tmpdir = tempfile.mkdtemp(prefix="round523_")
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
        self.calls = []
        self.rollback_calls = 0
        self.commit_calls = 0

    def execute(self, sql, params=()):
        s = sql.strip()
        self.calls.append(s)
        if self.fail_on and self.fail_on in sql:
            raise sqlite3.OperationalError("database is locked")
        return _FakeCursor(self.update_rowcount if s.startswith("UPDATE") else 1)

    def rollback(self):
        self.rollback_calls += 1

    def commit(self):
        self.commit_calls += 1


try:
    import app as A

    # ① BEGIN IMMEDIATE 자체가 락 경합으로 실패
    fc1 = _FakeConn(fail_on="BEGIN IMMEDIATE")
    r1 = A._sweep_claim(fc1)
    chk(r1 is False,
        "★★★★★ BEGIN IMMEDIATE 락 경합 — 예외가 새지 않고 False 를 반환한다"
        "(고치기 전엔 sqlite3.OperationalError 가 그대로 새어나갔다)", r1)
    chk(fc1.rollback_calls == 1, "  BEGIN IMMEDIATE 실패 후 rollback 이 정확히 1번 불린다", fc1.rollback_calls)
    chk(fc1.commit_calls == 0, "  commit 은 불리지 않는다", fc1.commit_calls)

    # ② BEGIN IMMEDIATE는 성공하지만 UPDATE가 락 경합으로 실패
    fc2 = _FakeConn(fail_on="UPDATE job_locks")
    r2 = A._sweep_claim(fc2)
    chk(r2 is False, "★★★ UPDATE 락 경합 — 예외가 새지 않고 False 를 반환한다", r2)
    chk(fc2.rollback_calls == 1, "  UPDATE 실패 후 rollback 이 정확히 1번 불린다", fc2.rollback_calls)
    chk(fc2.commit_calls == 0, "  commit 은 불리지 않는다", fc2.commit_calls)

    # ③ 대조군 — 락 경합이 전혀 없어도 rowcount=0(다른 워커가 리스 보유중)이면
    #    여전히 예외 없는 False 다(이 라운드 이전에도 있던 계약 — 회귀 없음).
    fc3 = _FakeConn(fail_on=None, update_rowcount=0)
    r3 = A._sweep_claim(fc3)
    chk(r3 is False,
        "대조 — 락 경합 없이 rowcount=0(다른 워커가 리스 보유중)이어도 "
        "여전히 예외 없는 False (회귀 없음)", r3)
    chk(fc3.rollback_calls == 1 and fc3.commit_calls == 0,
        "  이 경우도 rollback 만 불리고 commit 은 없다", (fc3.rollback_calls, fc3.commit_calls))

    # ④ 대조군 — 아무 문제 없으면(rowcount=1) 여전히 True + commit(회귀 없음).
    fc4 = _FakeConn(fail_on=None, update_rowcount=1)
    r4 = A._sweep_claim(fc4)
    chk(r4 is True, "대조 — 정상 상황(락 경합 없음·rowcount=1)은 여전히 True (회귀 없음)", r4)
    chk(fc4.commit_calls == 1 and fc4.rollback_calls == 0,
        "  정상 성공 경로는 commit 만 1번, rollback 은 없음", (fc4.commit_calls, fc4.rollback_calls))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] 순수 단위 실행", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행(경로 통합) — 실제 스크래치 DB + sweep_auctions(force=False)")
# ──────────────────────────────────────────────────────────────
try:
    import db as DB
    DB.init_db()

    class _LockFailProxy:
        """진짜 sqlite3 커넥션을 감싸 BEGIN IMMEDIATE 호출만 락 경합처럼 실패시킨다.
           그 외(SELECT·commit·rollback·close 등)는 전부 진짜 커넥션에 위임한다 —
           _sweep_if_due() 가 실제로 마주치는 상황(다른 커넥션이 이미 RESERVED
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
    # 마감 지난 경매를 하나 심는다(n>0 이어야 _sweep_claim 이 실제로 불린다).
    aid = real_conn.execute(
        "INSERT INTO auctions(case_id,status,deadline,created_at,low_price,bid_count) "
        "VALUES(?,'진행',?,?,0,0)",
        (999999, "2020-01-01 00:00:00", DB.now())).lastrowid
    real_conn.commit()

    proxy = _LockFailProxy(real_conn)
    # _sweep_if_due() 가 실제로 쓰는 그 호출 모양(force 생략=False)과 동일.
    res = A.sweep_auctions(proxy)
    chk(res.get("claimed") is False,
        "★★★★★ 실제 DB 위에서도 BEGIN IMMEDIATE 락 경합 시 예외 없이 "
        "claimed=False 로 물러난다(_sweep_if_due 가 이 신호를 받아 나머지 "
        "네 스윕을 계속 돌릴 수 있다)", res)
    chk(proxy.begin_immediate_calls == 1,
        "  BEGIN IMMEDIATE 시도는 1번뿐(실패 후 재시도하지 않고 바로 물러난다)",
        proxy.begin_immediate_calls)
    row = real_conn.execute("SELECT status FROM auctions WHERE id=?", (aid,)).fetchone()
    chk(row["status"] == "진행",
        "  리스를 못 잡았으니 그 경매 행은 전혀 안 건드려졌다(상태 그대로)", dict(row))
    real_conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] 경로 통합 실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌림-증명 — 라운드523 이전 코드 그대로면 예외가 정말 샜는가")
# ──────────────────────────────────────────────────────────────


def _old_sweep_claim(conn, lease_sec=120):
    """라운드523 이전 실제 코드 그대로(try/except 없음) — 비교용으로 이 테스트
       안에만 재구성한다(app.py 자체는 건드리지 않는다 — 동시 세션이 app.py 를
       같이 건드릴 수 있는 환경이라 round520-522 와 같은 원칙으로 전체 소스
       스왑 대신 여기서만 옛 로직을 재현한다)."""
    conn.execute("BEGIN IMMEDIATE")
    cur = conn.execute(
        "UPDATE job_locks SET lease_until = datetime('now','+9 hours', ?) "
        " WHERE name='auction_sweep' AND lease_until <= datetime('now','+9 hours')",
        (f"+{lease_sec} seconds",))
    if not cur.rowcount:
        conn.rollback()
        return False
    conn.commit()
    return True


try:
    fc_old = _FakeConn(fail_on="BEGIN IMMEDIATE")
    raised = False
    try:
        _old_sweep_claim(fc_old)
    except sqlite3.OperationalError:
        raised = True
    chk(raised,
        "★★★★★ 옛 코드(try/except 없음)는 같은 락 경합 상황에서 "
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
