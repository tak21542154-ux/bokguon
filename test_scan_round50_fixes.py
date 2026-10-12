# -*- coding: utf-8 -*-
"""스캔 50라운드 회귀 — 알림 스윕 5곳의 "확인~삽입" 사이 동시성 구멍.

  조사 에이전트(+직접 코드 추적)가 실측(2-연결 동시 실행, 인위적 지연으로
  레이스 창을 넓힘)으로 증명한 결함: sweep_no_bid_alert / sweep_review_reminders /
  sweep_warranty_expiry / sweep_approval_overdue / _sweep_award_approval
  다섯 함수 모두 "이미 보냈나"를 SELECT 로 확인만 하고 나중에 notify() 로
  삽입한다 — 그 사이에 화면 열람이 트리거하는 인라인 스윕(_sweep_if_due)과
  예약작업(manage.py sweep, **별도 OS 프로세스** — 서로의 존재를 전혀 모른다)이
  겹치면 같은 독촉·경보가 중복 적립된다.

  sweep_report_overdue(행 상태를 원자적 UPDATE 로 잠그는 기존 정상 형제)를
  참고해, 다섯 곳 모두 BEGIN IMMEDIATE 로 확인~삽입을 한 트랜잭션으로 묶었다
  (이 다섯은 상태 컬럼이 아니라 notifications 이력으로 중복을 막으므로,
  행 상태 대신 트랜잭션 자체로 두 번째 실행을 막는다).

      python test_scan_round50_fixes.py
"""
import io
import os
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("═" * 72)
print("  스캔 50라운드 회귀 — 알림 스윕 5곳 동시성(확인~삽입 원자화)")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 다섯 함수 모두 BEGIN IMMEDIATE 로 감쌌는가(함수 경계 안에서)")
# ──────────────────────────────────────────────────────────────
#  ⚠ 파일 전체에서 찾으면 다른 함수의 BEGIN IMMEDIATE 를 잘못 집는다(라운드49의
#    교훈) — 반드시 각 함수 **몸통 안**으로 좁혀서 본다.
FUNCS = ["sweep_no_bid_alert", "sweep_review_reminders", "sweep_warranty_expiry",
         "sweep_approval_overdue", "_sweep_award_approval"]


def _body(fn_name):
    start = APP_SRC.index(f"\ndef {fn_name}(conn")
    end = APP_SRC.find("\ndef ", start + 1)
    return APP_SRC[start:end if end != -1 else None]


for fn in FUNCS:
    body = _body(fn)
    chk("BEGIN IMMEDIATE" in body,
        f"★ {fn} — 확인~삽입을 BEGIN IMMEDIATE 로 한 트랜잭션에 묶었다")
    chk("conn.rollback()" in body,
        f"{fn} — 빈 결과일 때도 연 트랜잭션을 명시적으로 되돌린다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 2-연결 동시 실행으로도 중복이 안 생기는가")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="sweeprace50_")
db_path = os.path.join(_tmpdir, "verify.db")
upload_dir = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_DB_PATH"] = db_path
os.environ["BOKGUON_UPLOAD_DIR"] = upload_dir
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

_seq = [0]


def _no(prefix):
    _seq[0] += 1
    return f"{prefix}{_seq[0]:04d}"


try:
    import db as DB
    DB.init_db()
    import app as APP

    _orig_notify = APP.notify

    def _slow_notify(conn, *a, **k):
        #  ⚠ 조사 에이전트와 같은 방법 — 정상 속도로는 두 실행이 겹칠 확률이
        #    낮아 회귀가 놓치기 쉽다. "확인 끝~삽입 시작" 사이를 인위적으로
        #    늘려 레이스 창을 확실히 연다.
        time.sleep(0.2)
        return _orig_notify(conn, *a, **k)

    def race(fn, seed, ntype, expect, label):
        """seed(conn) 로 대상을 심고, 두 실제 스레드(각자 실제 연결)가 동시에
        fn(conn) 을 부른다. 정상 직렬 실행 1회와 같은 결과(expect건)만 남아야
        한다 — 안 막히면 2배(또는 그 이상)로 불어난다."""
        conn0 = DB.get_db()
        seed(conn0)
        conn0.commit()
        conn0.close()

        errs = []

        def worker():
            c = DB.get_db()
            try:
                fn(c)
            except Exception as e:                                    # noqa: BLE001
                errs.append(e)
            finally:
                c.close()

        APP.notify = _slow_notify
        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        time.sleep(0.05)
        t2.start()
        t1.join(10)
        t2.join(10)
        APP.notify = _orig_notify

        chk(not errs, f"{label} — 동시 실행 중 예외 없음", errs)
        c = DB.get_db()
        n = c.execute("SELECT COUNT(*) FROM notifications WHERE ntype=?", (ntype,)).fetchone()[0]
        c.close()
        chk(n == expect,
            f"★★★ {label} — 동시 실행 2회에도 {ntype} 이(가) 정상 1회 실행과 같은 "
            f"{expect}건(중복 없음)", n)

    # ── ① sweep_no_bid_alert : 항목마다 1건, 요약 알림 없음 → 기대 1건 ──
    def _seed_no_bid(conn):
        cid = conn.execute(
            "INSERT INTO cases(case_no,insurer,insurer_id,category,region,status,is_demo) "
            "VALUES(?,?,?,?,?,?,0)",
            (_no("50NB-"), "테스트보험", 1, "누수", "서울", "입찰중")).lastrowid
        conn.execute(
            "INSERT INTO auctions(case_id,deadline,status,created_at) "
            "VALUES(?, datetime('now','+9 hours','+20 minutes'), '진행', "
            "       datetime('now','+9 hours','-5 hours'))", (cid,))

    race(APP.sweep_no_bid_alert, _seed_no_bid, "무입찰경보", 1, "① sweep_no_bid_alert")

    # ── ② sweep_review_reminders : 사진검수 1건 → 알림 1건 ──
    def _seed_review(conn):
        cid = conn.execute(
            "INSERT INTO cases(case_no,status,is_demo) VALUES(?,?,0)",
            (_no("50RV-"), "시공중")).lastrowid
        conn.execute(
            "INSERT INTO photos(case_id,rel_path,uploader_role,uploader,review_status,"
            "                   sha256,created_at) "
            "VALUES(?,?,?,?,?,?, datetime('now','+9 hours','-2 hours'))",
            (cid, f"{cid}/race.jpg", "협력사", "검증50", "대기", f"sha-{cid}"))

    race(APP.sweep_review_reminders, _seed_review, "사진검수리마인드", 1, "② sweep_review_reminders")

    # ── ③ sweep_warranty_expiry : 오늘 만료(0일 문턱) 1건 → 알림 1건 ──
    def _seed_warranty(conn):
        conn.execute(
            "INSERT INTO cases(case_no,status,is_demo,warranty_months,completed_at) "
            "VALUES(?,?,0,0, datetime('now','+9 hours'))",
            (_no("50WR-"), "완료"))

    race(APP.sweep_warranty_expiry, _seed_warranty, "보증만료당일", 1, "③ sweep_warranty_expiry")

    # ── ④ sweep_approval_overdue : 보험사 독촉 1 + 운영팀 요약 1 = 정상 2건 ──
    #     (막히지 않으면 두 스레드가 각자 2건씩 넣어 4건이 된다)
    def _seed_settle(conn):
        cid = conn.execute(
            "INSERT INTO cases(case_no,status,is_demo) VALUES(?,?,0)",
            (_no("50AP-"), "시공완료")).lastrowid
        conn.execute(
            "INSERT INTO settlements(case_id,case_no,insurer,insurer_id,insurer_approved,"
            "                        transfer_status,void_status,is_demo,created_at) "
            "VALUES(?,?,?,?,0,?,?,0, datetime('now','+9 hours','-4 days'))",
            (cid, _no("50AP-"), "테스트보험", 1, "대기", ""))

    race(APP.sweep_approval_overdue, _seed_settle, "완료승인독촉", 2, "④ sweep_approval_overdue")

    # ── ⑤ _sweep_award_approval : 위와 같은 구조, cases.status='승인대기' ──
    def _seed_award(conn):
        conn.execute(
            "INSERT INTO cases(case_no,status,is_demo,insurer,insurer_id,status_at) "
            "VALUES(?,?,0,?,?, datetime('now','+9 hours','-4 days'))",
            (_no("50AW-"), "승인대기", "테스트보험", 1))

    race(APP._sweep_award_approval, _seed_award, "낙찰승인독촉", 2, "⑤ _sweep_award_approval")

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 동시성 실측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
