# -*- coding: utf-8 -*-
"""스캔 557라운드 회귀 — manage.py:cmd_sweep()(예약 실행의 진짜 진입점)의
   유일한 try 블록에 except가 없던 결함.

   이 사실 자체는 새 발견이 아니다 — round411·415·482·523·524가 전부
   독립적으로 이 정확한 문장("cmd_sweep()의 유일한 try(989-1032행)에도
   except가 없어(finally만 있음)")을 남겼다. 다섯 라운드 모두 이걸 근거로
   삼아 **더 안쪽**(app.py의 개별 스윕 함수 6종 — 411·415, dispatch.py의
   _claim_lease() — 482·524)만 고치고, 정작 그 안쪽 방어들이 전부 모이는
   이 바깥 경계 자체는 5라운드·140+ 라운드에 걸쳐 그대로 남겨 뒀다.

   지금도 여전히 뚫려 있는 구체적 경로 하나 — dispatch.sweep_dispatches()는
   처리 실패 시 자기 리스를 놓아준 뒤 **의도적으로 다시 던진다**
   (dispatch.py 961행 `except Exception: _release_lease(conn, "오류"); raise`).
   이 예외는 cmd_sweep()의 무방비 try를 그대로 뚫고 main()(COMMANDS[cmd]
   호출도 try 없음, manage.py 2760행)까지 나가 프로세스를 죽인다. 실제
   예약 실행(복구온_예약실행_등록.ps1)은 콘솔 없는 pythonw.exe 를 표준출력
   리다이렉트 없이 부르므로 그 트레이스백은 **어디에도 남지 않는다.**
   cli_sweep job_locks 마커도 이번 회차엔 못 쓰여 대시보드 배지는 30분 뒤
   결국 적색이 되지만(그 자체는 의도된 설계, app.py 7241행 근처 주석 —
   "예약 실행이 실제로 돌았다는 별도 표식"), '멈췄다'는 사실만 보일 뿐
   **왜** 멈췄는지는 bokguon.log 를 아무리 grep 해도 0건이었다.

   고침 — 형제(_sweep_if_due, app.py 라운드536)와 같은 처방을 이 바깥
   경계에도 그대로 적용: 배치 전체를 try/except Exception 으로 감싸
   A.app.logger.exception() 으로 남기고(이미 커밋된 이전 스윕은 되돌리지
   않는다), 종료코드도 실패(1)로 보고한다 — 예약실행_등록.ps1 의 -RunNow
   가 LastTaskResult(종료코드)를 그대로 신뢰하므로 실패를 0으로 보고하면
   그 확인 절차 자체가 무의미해진다.

   이 회귀테스트는 ONLY 안전한 기법만 쓴다 — 실제 on-disk manage.py는
   monkeypatch 대상 함수만 가짜로 바꿔 실제 M.cmd_sweep()을 그대로 부르고,
   '되돌리기' 증명은 옛(결함 있던) 함수 모양을 별도 문자열로 재구성해
   exec()로 돌려 인과관계를 실측한다.

       python test_scan_round557_fixes.py
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


print("=" * 72)
print("  스캔 557라운드 회귀 — manage.py cmd_sweep() 배치의 무방비 try")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — manage.py 가 실제로 고쳐졌는가")
# ------------------------------------------------------------
MANAGE_SRC = read("manage.py")
i0 = MANAGE_SRC.index("def cmd_sweep(argv):")
i1 = MANAGE_SRC.index("\ndef ", i0 + 1)
SWEEP_BODY = MANAGE_SRC[i0:i1]

chk("except Exception as e:" in SWEEP_BODY,
    "★★★★★ cmd_sweep() 의 배치 try 에 except Exception 이 생겼다"
    "(전에는 finally 뿐이었다 — round411·415·482·523·524가 매번 지적만 함)")
chk("sweep_err = e" in SWEEP_BODY and 'A.app.logger.exception(' in SWEEP_BODY,
    "★★★★ 실패를 sweep_err 에 담고 A.app.logger.exception() 으로 남긴다"
    "(형제 _sweep_if_due, app.py 라운드536 과 같은 처방)")
chk(SWEEP_BODY.count("conn.rollback()") >= 1
    and "except sqlite3.Error:\n            pass" in SWEEP_BODY,
    "  except 안에서 rollback 도 자기 자신의 실패에 안전하게 감싸져 있다")
chk("if sweep_err is not None:\n        return 1" in SWEEP_BODY,
    "★★★★ 실패하면 종료코드를 1로 보고한다(작업 스케줄러 LastTaskResult 가 "
    "이 값을 그대로 신뢰하므로 0을 보고하면 안 된다)")
chk('res = {"scanned": 0, "closed": 0, "failed": 0, "reauction_closed": 0, "skipped": 0}'
    in SWEEP_BODY,
    "  res 도 실패 대비 기본값을 갖는다(A.sweep_auctions 자신이 실패해도 "
    "맨 아래 res['scanned'] 참조가 UnboundLocalError 로 죽지 않는다)")

# ============================================================
print("\n[2] 준비 — 스크래치 DB(오늘자 실제 스키마)")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round557_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB
DB.init_db()
import app as A
import dispatch as DP
import manage as M

_row0 = A.one(DB.get_db().execute(
    "SELECT last_run_at FROM job_locks WHERE name='cli_sweep'"))
chk(_row0 is not None and _row0["last_run_at"] is None,
    "★★★ 전제조건: 새 스크래치 DB의 cli_sweep 은 아직 '한 번도 안 돎'(NULL)이다",
    dict(_row0) if _row0 else None)

_orig_review = A.sweep_review_reminders
_orig_log_exc = A.app.logger.exception
_log_calls = []


def _raiser(conn):
    raise RuntimeError("R557_INJECTED — 리마인드 스윕 인위 실패")


def _recording_exception(msg, *a, **k):
    _log_calls.append(str(msg))
    return _orig_log_exc(msg, *a, **k)


# ============================================================
print("\n[3] 되돌리기 — 옛(except 없는) cmd_sweep 모양을 재구성해 같은 실패가")
print("    실제로 프로세스 밖까지 새는지 인과관계로 실측")
# ------------------------------------------------------------
OLD_CMD_SWEEP_SRC = (
    "def _old_cmd_sweep(conn, A, DP, DBmod):\n"
    "    nobid, overdue, rem, snd, appr, dsp, whr, war = 0, 0, {}, {}, {}, {}, 0, 0\n"
    "    try:\n"
    "        res = A.sweep_auctions(conn, dry_run=False, force=True)\n"
    "        nobid = A.sweep_no_bid_alert(conn)\n"
    "        overdue = A.sweep_report_overdue(conn)\n"
    "        rem = A.sweep_review_reminders(conn)\n"          # 여기서 인위 실패
    "        war = A.sweep_warranty_expiry(conn)\n"
    "        appr = A.sweep_approval_overdue(conn)\n"
    "        dsp = DP.sweep_dispatches(conn, notify=A._dispatch_notify(conn))\n"
    "        snd = A.sweep_send_notifications(conn)\n"
    "        whr = A.sweep_webhook_retries(conn)\n"
    "        conn.execute(\n"
    "            \"INSERT INTO job_locks(name, last_run_at) VALUES('cli_sweep', ?) \"\n"
    "            \" ON CONFLICT(name) DO UPDATE SET last_run_at=excluded.last_run_at\",\n"
    "            (DBmod.now(),))\n"
    "        conn.commit()\n"
    "    finally:\n"
    "        conn.close()\n"
    "    return 0\n"
)
_ns = {}
exec(OLD_CMD_SWEEP_SRC, {}, _ns)

A.sweep_review_reminders = _raiser
conn_old = DB.get_db()
_old_raised = None
try:
    _ns["_old_cmd_sweep"](conn_old, A, DP, DB)
except RuntimeError as e:
    _old_raised = e
except Exception as e:  # 혹시 다른 예외 모양이면 실패로 보이게 잡아 둔다
    _old_raised = e
chk(_old_raised is not None and "R557_INJECTED" in str(_old_raised),
    "★★★★★ 옛 모양(except 없음)은 리마인드 스윕의 예외가 그대로 밖으로 샌다"
    "(수정 전 실제 상태를 인과관계로 증명 — 이게 새면 이후 웹훅재전송·"
    "cli_sweep 기록까지 전부 건너뛴 채 프로세스가 죽는다)",
    repr(_old_raised))

# ============================================================
print("\n[4] 실행 — 실제 M.cmd_sweep()은 같은 인위 실패에서도 죽지 않는가")
# ------------------------------------------------------------
A.app.logger.exception = _recording_exception
_new_raised = None
_rc = None
try:
    _rc = M.cmd_sweep([])
except Exception as e:
    _new_raised = e
finally:
    A.app.logger.exception = _orig_log_exc

chk(_new_raised is None,
    "★★★★★ 실제 M.cmd_sweep() 은 같은 인위 실패에서 더는 예외를 밖으로 "
    "던지지 않는다([3]과 정반대 결과 — 이 회귀가 진짜 차이를 잡아낼 능력이 있음)",
    repr(_new_raised))
chk(_rc == 1,
    "★★★★ 실패한 회차는 종료코드 1을 반환한다(0을 보고해 조용히 성공으로 "
    "보이는 사고를 막는다)", _rc)
chk(any("cmd_sweep" in m for m in _log_calls),
    "★★★★ A.app.logger.exception() 이 실제로 호출됐다(bokguon.log 에 "
    "왜 멈췄는지가 이제 남는다 — 전에는 grep 0건이었다)", _log_calls)

_row1 = A.one(DB.get_db().execute(
    "SELECT last_run_at FROM job_locks WHERE name='cli_sweep'"))
chk(_row1 is not None and _row1["last_run_at"] is None,
    "★★★ 실패한 회차는 cli_sweep 마커를 쓰지 않는다(대시보드 배지가 "
    "'멈췄다'를 계속 정확히 가리켜야 한다 — round B4 의도 그대로 보존)",
    dict(_row1) if _row1 else None)

A.sweep_review_reminders = _orig_review

# ============================================================
print("\n[5] 회귀 없음 — 실패가 없으면 여전히 정상 동작한다")
# ------------------------------------------------------------
rc_dry = M.cmd_sweep(["--dry-run"])
chk(rc_dry == 0, "  --dry-run 은 여전히 0을 반환한다(회귀 없음)", rc_dry)

rc_clean = M.cmd_sweep([])
chk(rc_clean == 0, "★★★ 실패 없는 정상 회차는 여전히 종료코드 0을 반환한다", rc_clean)
_row2 = A.one(DB.get_db().execute(
    "SELECT last_run_at FROM job_locks WHERE name='cli_sweep'"))
chk(_row2 is not None and _row2["last_run_at"] is not None,
    "★★★ 정상 회차는 cli_sweep 마커를 실제로 남긴다(성공 경로도 그대로 산다)",
    dict(_row2) if _row2 else None)

# ── 정리 ──────────────────────────────────────────────────────
A.sweep_review_reminders = _orig_review
A.app.logger.exception = _orig_log_exc

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
