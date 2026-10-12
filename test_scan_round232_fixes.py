# -*- coding: utf-8 -*-
"""스캔 232라운드 회귀 — sweep_send_notifications() 의 "번호없음 즉시실패"
분기가 동시 실행 경쟁을 대비하지 않던 결함.

  바로 아래 CAS 분기("선점: 내가 읽은 시도 횟수 그대로일 때만 +1")는 rowcount
  를 확인해 경쟁자가 이미 처리한 건이면 조용히 건너뛰는데(out["skipped"]),
  6줄 위 "번호없음" 분기는 UPDATE 의 rowcount 를 전혀 보지 않고 무조건
  _alert_send_failure()를 불러 운영팀에게 "발송실패"를 알리고 DB.log 도
  남겼다. 이 함수는 크론(manage.py sweep, 5분마다) 과 관리자 수동 버튼
  (/api/outbox/send-now, /api/outbox/send-selected) 세 곳에서 겹쳐 불릴 수
  있다(문서 자체가 "동시 실행(스케줄러+수동 버튼) 대비"를 CAS 도입 이유로
  명시한다) — 번호 없는 같은 건을 두 실행이 동시에 pend 로 집어 오면, 먼저
  커밋한 쪽만 실제로 상태를 바꾸는데 나중 실행도 rowcount=0 인 UPDATE 를
  성공한 것처럼 넘겨 같은 건을 또 알린다(중복 "발송실패" 알림 + 중복 로그).

      python test_scan_round232_fixes.py
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


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 232라운드 회귀 — 번호없음 즉시실패 분기의 동시실행 중복알림")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def sweep_send_notifications(")
i1 = APP_SRC.index("\ndef ", i0 + 1)
body = APP_SRC[i0:i1]
i_nophone = body.index("if not phone:")
i_cas = body.index("# 선점(CAS): 내가 읽은 시도 횟수 그대로일 때만 +1")
nophone_block = body[i_nophone:i_cas]
chk("cur = conn.execute(" in nophone_block and "if not cur.rowcount:" in nophone_block,
    "★★★★ '번호없음' 분기도 이제 CAS 분기와 같은 rowcount 확인을 한다"
    "(경쟁자가 먼저 처리한 건이면 조용히 건너뛴다)")
chk('out["skipped"] += 1' in nophone_block,
    "★★★ rowcount=0 이면 out[\"skipped\"] 로 집계한다(out[\"failed\"] 아님 —"
    " 이 실행이 실제로 실패시킨 게 아니므로)")

# ============================================================
print("\n[2] 실행 — 경쟁자가 먼저 처리한 '번호없음' 건을 또 알리지 않는다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round232_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A
    import notify_popbill as NP

    conn = DB.get_db()
    now = DB.now()
    #  partner_id·insurer_id·case_id 모두 NULL — _notify_phone() 이 반드시 None 을
    #  돌려주게 만들어(지어낼 수 없음) '번호없음' 분기를 확실히 태운다.
    target = conn.execute(
        "INSERT INTO notifications(ntype,channel,target,message,status,is_demo,created_at) "
        "VALUES('정산','문자','R232대상','검증 메시지','발송대기',0,?)", (now,)).lastrowid
    conn.commit()

    _before_alerts = conn.execute(
        "SELECT COUNT(*) c FROM notifications WHERE ntype='발송실패'").fetchone()["c"]

    class _RaceConn:
        """target 의 '번호없음' UPDATE 직전에 '경쟁자'가 같은 행을 이미
           처리해 둔 것처럼 만든다(같은 트랜잭션 안에서 선-갱신) — 그 UPDATE
           의 rowcount 가 실제 동시실행 경쟁과 똑같이 0 이 되게 재현한다."""
        def __init__(self, real, target_id):
            self._real = real
            self._target_id = target_id
            self._raced = False

        def execute(self, sql, params=()):
            if (not self._raced and "수신자 휴대전화 없음" in sql
                    and params and params[0] == self._target_id):
                self._raced = True
                #  진짜 동시성처럼 재현한다 — '경쟁자'의 처리를 먼저 커밋으로
                #  확정한다(실제 코드가 뒤에서 자기 트랜잭션을 롤백해도 이미
                #  커밋된 이 갱신은 영향받지 않는다). 그런 다음 호출자가 계속
                #  같은 트랜잭션 안에 있다고 여기고 쓸 수 있게 다시 열어 준다.
                self._real.commit()
                self._real.execute(
                    "UPDATE notifications SET status='실패', "
                    "send_detail='경쟁자가 먼저 처리함(검증용)' WHERE id=?",
                    (self._target_id,))
                self._real.commit()
                self._real.execute("BEGIN IMMEDIATE")
            return self._real.execute(sql, params)

        def __getattr__(self, name):
            return getattr(self._real, name)

    real_ready, real_notify_on = NP.ready, A.NOTIFY_ENABLED
    try:
        NP.ready = lambda: True
        A.NOTIFY_ENABLED = True
        raced = _RaceConn(conn, target)
        out = A.sweep_send_notifications(raced, only_ids=[target])
    finally:
        NP.ready, A.NOTIFY_ENABLED = real_ready, real_notify_on

    _after_alerts = conn.execute(
        "SELECT COUNT(*) c FROM notifications WHERE ntype='발송실패'").fetchone()["c"]

    chk(_after_alerts == _before_alerts,
        "★★★★ 경쟁자가 이미 처리한 건에 대해 이 실행은 '발송실패' 알림을 "
        "추가로 만들지 않는다(고치기 전엔 rowcount 를 안 봐서 매번 하나씩 "
        "더 생겼다)", f"before={_before_alerts} after={_after_alerts}")
    chk(out.get("skipped", 0) >= 1,
        "★★★ 요약 집계도 '건너뜀'으로 잡힌다(경쟁자에게 이미 넘어간 건을 "
        "이 실행의 '실패'로 잘못 세지 않는다)", out)
    st = conn.execute(
        "SELECT status, send_detail FROM notifications WHERE id=?", (target,)).fetchone()
    chk(st["status"] == "실패" and "경쟁자" in (st["send_detail"] or ""),
        "★★★ 행 자체는 경쟁자가 먼저 남긴 상태 그대로 유지된다"
        "(이 실행이 자신의 문구로 덮어쓰지 않는다)", dict(st))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드232 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
