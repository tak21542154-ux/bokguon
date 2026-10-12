# -*- coding: utf-8 -*-
"""스캔 662라운드 회귀 — 인라인 마감 스윕(_sweep_if_due, app.py)에 완료·낙찰
   승인 독촉(sweep_approval_overdue)과 출동 수배 시한 점검(dispatch.sweep_dispatches)이
   처음부터 빠져 있던 결함.

   직접 조사(하위위임 없음) — round661의 인계 각도(PWA 서비스워커 캐시버스팅,
   dispatch_calls 스케줄링)를 먼저 훑었으나 둘 다 이미 극도로 두껍게 방어돼
   있었다(서비스워커 install/fetch 핸들러와 asset() 캐시버스팅 경로 전수 대조 —
   클린. dispatch.py 의 open_dispatch·sweep_dispatches·candidates·claim·decline·
   arrive·close_no_repair·open_agreement·settle_agreement 전 함수를 처음부터
   끝까지 정독 — round95·117·136·152·182·257·279·411·482·524·541·558 등으로
   이미 촘촘히 굳어 있어 새 결함이 없었다). 각도를 "이 두 함수 자체의 로직"에서
   "이 두 함수가 **불리는 경로**가 형제들과 같은가"로 옮겨 app.py 의 sweep_*
   전수(sweep_auctions·sweep_no_bid_alert·sweep_report_overdue·
   sweep_review_reminders·sweep_warranty_expiry·sweep_approval_overdue·
   sweep_send_notifications·sweep_webhook_retries)와 dispatch.sweep_dispatches
   를 인라인 백스톱(_sweep_if_due, 조회 화면을 열 때마다 곁들여 도는 함수)에
   누가 들어있고 누가 빠졌는지 실측 대조했다.

   결함 — _sweep_if_due() 는 정확히 5개(sweep_auctions·sweep_no_bid_alert·
   sweep_report_overdue·sweep_review_reminders·sweep_warranty_expiry)만 부르고
   있었다. 그런데 sweep_approval_overdue() 자신의 독스트링이 이미 이렇게
   못박아 뒀다 — "지금까지는 사람이 어드민을 열고 '승인 독촉'을 눌러야만
   알림이 갔다. 아무도 안 열면 영원히 아무 일도 일어나지 않는다"(app.py
   6748행 부근). grep 으로 실제 호출부를 전수 확인하니 manage.py cmd_sweep()
   (예약 실행 크론, 10분 주기) 단 한 곳뿐이었다 — 크론이 실제로 멈춘 적이
   있다는 사실은 이 저장소 자신의 기록에 있다(deploy/복구온_예약실행_등록.ps1
   머리말 — "실제로 이 PC에 등록이 없었고, 그 상태로는 팝빌 키를 넣어도
   문자가 안 나간다"). 형제 5개는 전부 크론이 죽어도 **아무 페이지나 열면**
   되살아나는데, "대시보드에서 가장 큰 대기열"·"돈이 실제로 멈추는 곳"이라고
   이 함수 스스로 부르는 완료·낙찰 승인 독촉만 크론 하나에 전부를 걸고
   있었다. dispatch.sweep_dispatches() 도 같은 처지다 — 모듈 자신의 독스트링이
   "이것이 없으면 한 업체가 수락만 하고 안 가는 순간 사건이 영원히 멈춘다"고
   말하는데, manage.py cmd_sweep() 자신의 주석("★ 출동 기한 점검 — 이게
   빠져 있었다")이 증언하듯 크론에 추가된 뒤로도 인라인 백스톱은 받은 적이
   없었다(grep 재확인 — app.py 안에 DP.sweep_dispatches 호출은 관리자 수동
   버튼 api_admin_dispatch_sweep 하나뿐이었다).

   왜 안전하게 추가할 수 있는가 — 이 둘은 sweep_send_notifications·
   sweep_webhook_retries(외부 API 실호출·5초 타임아웃·최대 50건이라 페이지
   요청 스레드에 물리면 안 돼 의도적으로 크론 전용으로 남겨 둔 것들, 이번
   조사로 재확인)와 다르다 — DB 트랜잭션만 쓰고, notify() 는 알림 레코드를
   'notifications' 테이블에 적어 둘 뿐(실제 문자·알림톡 발송은 여전히
   sweep_send_notifications 가 나중에 크론에서만 한다). 동시 실행(크론과
   겹침) 방어도 이미 자체적으로 있다 — dispatch_sweep은 job_locks 리스
   (_claim_lease, round482·524가 이미 잠금경합까지 방어), 승인독촉은 알림
   자체의 24시간 쿨다운(notifications 조회, 형제 sweep_review_reminders 등과
   동일한 CAS 패턴). 그래서 형제 5개와 완전히 같은 자격으로 추가한다.

   고침 — app.py:_sweep_if_due() 의 try 블록 끝(sweep_warranty_expiry(conn)
   다음, except 이전)에 sweep_approval_overdue(conn) 과
   DP.sweep_dispatches(conn, notify=_dispatch_notify(conn)) 두 줄을 추가했다.
   기존 5개 호출·순서·주석은 전혀 건드리지 않았다(round536·round30 회귀가
   지키는 불변조건 유지 확인 — 아래 [1]).

      python test_scan_round662_fixes.py
"""
import io
import os
import shutil
import sqlite3
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")
MANAGE_SRC = read("manage.py")

print("=" * 72)
print("  스캔 662라운드 회귀 — _sweep_if_due() 에 빠져 있던 완료승인독촉·출동수배 스윕")
print("=" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ==================================================================
print("\n[1] 소스 확인 — 새 스윕 2개가 추가됐고, 기존 5개는 그대로다")
# ------------------------------------------------------------------
import ast as _ast
chk(_ast.parse(APP_SRC) is not None, "STEP app.py 전체 ast.parse 성공")

sd_body = _py_fn_body(APP_SRC, "_sweep_if_due")
_except_idx = sd_body.index("except Exception:")
_before_except = sd_body[:_except_idx]

chk("sweep_approval_overdue(conn)" in _before_except,
    "★★★★★ 완료·낙찰 승인 독촉 스윕이 인라인 백스톱에 추가됐다"
    "(전엔 manage.py cmd_sweep 크론에만 있었다)")
chk("DP.sweep_dispatches(conn, notify=_dispatch_notify(conn))" in _before_except,
    "★★★★★ 출동 수배 시한 점검 스윕도 추가됐다(전엔 크론에만 있었다)")

_sweep_calls = ["sweep_auctions(conn)", "sweep_no_bid_alert(conn)",
                "sweep_report_overdue(conn)", "sweep_review_reminders(conn)",
                "sweep_warranty_expiry(conn)", "sweep_approval_overdue(conn)",
                "DP.sweep_dispatches(conn, notify=_dispatch_notify(conn))"]
_positions = [sd_body.index(c) for c in _sweep_calls]
chk(_positions == sorted(_positions),
    "★★★ 기존 5개 스윕이 순서·형태 그대로 남아 있고, 새 2개는 그 뒤에 있다"
    "(round536·round30 회귀가 지키는 불변조건 유지)", _positions)
chk(all(p < _except_idx for p in _positions),
    "STEP 7개 스윕 호출이 전부 try 블록 안(except 이전)에 있다 — 예외 삼킴 규칙 그대로")

chk("A.sweep_approval_overdue" in MANAGE_SRC
    and "dsp = DP.sweep_dispatches(conn, notify=A._dispatch_notify(conn))" in MANAGE_SRC,
    "STEP 크론 경로(manage.py cmd_sweep)는 원래 이 둘을 부르고 있었고, "
    "이번 수정이 크론 쪽을 건드리지 않았다(인라인 쪽에만 추가)")

# ==================================================================
# 실행 준비 — 이번 세션만의 완전 격리 스크래치 DB(운영 bokguon.db 절대 미접촉)
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round662_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "verify.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

A = None
DB = None
DP = None
try:
    import db as DB
    DB.init_db()
    import app as A
    import dispatch as DP
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드662 실행 준비(DB.init_db·app import)", f"{type(e).__name__} {e}")


def _seed_insurer(conn, mark):
    cur = conn.execute(
        "INSERT INTO insurers(name, status, is_demo) VALUES (?, '활성', 0)",
        (f"{mark}보험사",))
    conn.commit()
    return cur.lastrowid


def _seed_overdue_settlement(conn, mark, iid):
    """APPROVAL_REMIND_DAYS 를 넘겨 완료 승인이 멈춘 정산 1건 — sweep_approval_overdue 표적."""
    case_no = f"{mark}-A-{os.urandom(3).hex()}"
    cid = conn.execute(
        """INSERT INTO cases(case_no, insurer_id, insurer, category, region, address,
                             status, is_demo, created_at)
           VALUES(?,?,?,?,?,?,'시공중',0,datetime('now','+9 hours'))""",
        (case_no, iid, f"{mark}보험사", "가드레일·방호울타리", "서울 송파구", "검증주소")
    ).lastrowid
    days = A.APPROVAL_REMIND_DAYS + 1
    sid = conn.execute(
        f"""INSERT INTO settlements(case_id, case_no, insurer, insurer_id, amount,
                                    insurer_approved, transfer_status, void_status,
                                    is_demo, created_at)
           VALUES(?,?,?,?,500000,0,'대기',NULL,0,
                  datetime('now','+9 hours','-{days} days'))""",
        (cid, case_no, f"{mark}보험사", iid)
    ).lastrowid
    conn.commit()
    return cid, sid, case_no


def _seed_overdue_dispatch(conn, mark, iid):
    """dispatch_minutes 를 넘겨 아무도 수락하지 않은 '모집중' 수배 1건 — sweep_dispatches 표적."""
    case_no = f"{mark}-D-{os.urandom(3).hex()}"
    cid = conn.execute(
        """INSERT INTO cases(case_no, insurer_id, insurer, category, region, address,
                             status, is_demo, intake_type, dispatch_status, created_at)
           VALUES(?,?,?,?,?,?,'접수',0,'사진없음','수배중',datetime('now','+9 hours'))""",
        (case_no, iid, f"{mark}보험사", "가드레일·방호울타리", "서울 송파구", "검증주소")
    ).lastrowid
    mins = DP.dispatch_minutes(conn) + 15
    did = conn.execute(
        f"""INSERT INTO dispatches(case_id, round, status, created_at, is_demo)
           VALUES(?,1,'모집중',datetime('now','+9 hours','-{mins} minutes'),0)""",
        (cid,)
    ).lastrowid
    conn.commit()
    return cid, did, case_no


# ==================================================================
print("\n[2] 실행(모킹) — 새 스윕 2개가 실제로 호출부 안에서 실행되는가")
# ------------------------------------------------------------------
try:
    _calls = {"appr": 0, "dsp": 0}
    _orig_appr = A.sweep_approval_overdue
    _orig_dsp = A.DP.sweep_dispatches

    def _stub_appr(conn):
        _calls["appr"] += 1
        return {"sent": 0, "skipped": 0, "insurer_suspended": 0, "award": 0}

    def _stub_dsp(conn, **kw):
        _calls["dsp"] += 1
        return {"claimed": True, "expired": 0, "reopened": 0, "gaveup": 0}

    A.sweep_approval_overdue = _stub_appr
    A.DP.sweep_dispatches = _stub_dsp
    try:
        A._LAST_INLINE_SWEEP[0] = 0.0
        _boom = None
        try:
            A._sweep_if_due()
        except Exception as e:                                      # noqa: BLE001
            _boom = e
        chk(_boom is None,
            "★★★ 정상 경로에서 _sweep_if_due() 는 예외를 올리지 않는다", repr(_boom))
        chk(_calls["appr"] == 1,
            "★★★★★ sweep_approval_overdue 가 실제로 인라인 스윕 안에서 호출된다"
            "(소스에 문자열만 있고 안 불리는 죽은 코드가 아니다)", _calls)
        chk(_calls["dsp"] == 1,
            "★★★★★ DP.sweep_dispatches 도 실제로 인라인 스윕 안에서 호출된다", _calls)
    finally:
        A.sweep_approval_overdue = _orig_appr
        A.DP.sweep_dispatches = _orig_dsp
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드662 [2] 모킹 직접호출", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[3] 실행(진짜 DB, 진짜 스윕) — 실제로 방치된 승인 독촉·출동 수배가 살아나는가")
# ------------------------------------------------------------------
MARK3 = "R662E2E"
try:
    conn = DB.get_db()
    iid = _seed_insurer(conn, MARK3)
    cid_a, sid_a, case_no_a = _seed_overdue_settlement(conn, MARK3, iid)
    cid_d, did_d, case_no_d = _seed_overdue_dispatch(conn, MARK3, iid)
    conn.close()

    A._LAST_INLINE_SWEEP[0] = 0.0
    _boom = None
    try:
        A._sweep_if_due()
    except Exception as e:                                          # noqa: BLE001
        _boom = e
    chk(_boom is None,
        "★★★ 실데이터 경로에서도 _sweep_if_due() 는 예외를 올리지 않는다", repr(_boom))

    conn = DB.get_db()
    n_notif = conn.execute(
        "SELECT COUNT(*) FROM notifications WHERE ntype='완료승인독촉' AND case_id=?",
        (cid_a,)).fetchone()[0]
    chk(n_notif >= 1,
        "★★★★★ 방치된 완료 승인 건에 실제로 독촉 알림이 생성됐다"
        "(admin 이 화면을 한 번도 안 열어도, cmd_sweep 없이도)", n_notif)

    dsp_status = conn.execute(
        "SELECT status, fail_reason FROM dispatches WHERE id=?", (did_d,)).fetchone()
    chk(dsp_status is not None and dsp_status["status"] == DP.ST_FAILED,
        "★★★★★ 시한이 지난 '모집중' 수배가 실제로 '실패'로 정리됐다"
        "(admin 이 화면을 한 번도 안 열어도, cmd_sweep 없이도)",
        dict(dsp_status) if dsp_status else None)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드662 [3] 실데이터 E2E", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[4] 되돌리기 — 옛 5개짜리 _sweep_if_due() 로는 같은 방치 건이 정말 안 풀리는가"
      "(인과관계 직접증명)")
# ------------------------------------------------------------------
#  ⚠ app.py 자체는 건드리지 않는다(round520 이후 표준 관례) — 이 라운드가 고치기
#    직전의 실제 본문(기존 5개 호출 + round536 의 로그 except, 새 2줄 없음)을
#    테스트 안에서만 문자열로 재구성해 같은 시나리오에 직접 실행한다.
_PRE662_SRC = '''
def _sweep_if_due():
    """조회 화면을 열 때 곁들여 도는 마감 점검."""
    now = time.time()
    if now - _LAST_INLINE_SWEEP[0] < INLINE_SWEEP_GAP_SEC:
        return
    _LAST_INLINE_SWEEP[0] = now
    conn = None
    try:
        conn = DB.get_db()
        sweep_auctions(conn)
        sweep_no_bid_alert(conn)
        sweep_report_overdue(conn)
        sweep_review_reminders(conn)
        sweep_warranty_expiry(conn)
    except Exception:
        app.logger.exception("인라인 마감 스윕 실패 — 다음 회차까지 재시도 없음")
        try:
            if conn:
                conn.rollback()
        except sqlite3.Error:
            pass
    finally:
        if conn:
            conn.close()
'''
MARK4 = "R662OLD"
try:
    conn = DB.get_db()
    iid4 = _seed_insurer(conn, MARK4)
    cid_a4, sid_a4, case_no_a4 = _seed_overdue_settlement(conn, MARK4, iid4)
    cid_d4, did_d4, case_no_d4 = _seed_overdue_dispatch(conn, MARK4, iid4)
    conn.close()

    _ns = dict(vars(A))                 # app 모듈 네임스페이스 복사(진짜 모듈은 안 건드림)
    _ns["_LAST_INLINE_SWEEP"] = [0.0]   # 실제 스윕과 완전히 독립된 조절창
    _ns["INLINE_SWEEP_GAP_SEC"] = 60
    exec(compile(_PRE662_SRC, "<round662_pre_reconstructed>", "exec"), _ns)
    _old_sweep_if_due = _ns["_sweep_if_due"]

    _boom_old = None
    try:
        _old_sweep_if_due()
    except Exception as e:                                          # noqa: BLE001
        _boom_old = e
    chk(_boom_old is None,
        "★★★ 옛 코드(재구성)도 예외 없이 조용히 끝난다(겉보기 동작은 지금과 "
        "똑같다 — 그래서 아무도 눈치 못 챘다)", repr(_boom_old))

    conn = DB.get_db()
    n_notif_old = conn.execute(
        "SELECT COUNT(*) FROM notifications WHERE ntype='완료승인독촉' AND case_id=?",
        (cid_a4,)).fetchone()[0]
    chk(n_notif_old == 0,
        "★★★★★ 옛 코드(5개짜리)는 같은 방치 건에 독촉 알림을 만들지 않는다"
        " — 방금 [3]의 새 코드는 만들었다. 이 차이가 이 회귀의 인과관계 증명이다",
        n_notif_old)

    dsp_status_old = conn.execute(
        "SELECT status FROM dispatches WHERE id=?", (did_d4,)).fetchone()
    chk(dsp_status_old is not None and dsp_status_old["status"] == DP.ST_OPEN,
        "★★★★★ 옛 코드는 시한 지난 수배를 그대로 '모집중'에 방치한다"
        " — 방금 [3]의 새 코드는 '실패'로 정리했다", dict(dsp_status_old) if dsp_status_old else None)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드662 [4] 되돌림-증명", f"{type(e).__name__} {e}")

# ==================================================================
# 정리
# ------------------------------------------------------------------
try:
    if DB is not None:
        conn = DB.get_db()
        for m in (MARK3, MARK4):
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM cases WHERE case_no LIKE ?", (m + "%",))]
            for cid in ids:
                conn.execute("DELETE FROM dispatches WHERE case_id=?", (cid,))
                conn.execute("DELETE FROM settlements WHERE case_id=?", (cid,))
                conn.execute("DELETE FROM notifications WHERE case_id=?", (cid,))
                conn.execute("DELETE FROM cases WHERE id=?", (cid,))
            conn.execute("DELETE FROM insurers WHERE name LIKE ?", (m + "%",))
        conn.commit()
        conn.close()
except Exception:
    pass
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_LOG_FILE", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
