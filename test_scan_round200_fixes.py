# -*- coding: utf-8 -*-
"""스캔 200라운드 회귀 — sweep_send_notifications() 의 2단계 커밋 사이(팝빌
실발송 직후 마무리기록) 구간에 예외 방어가 없던 결함.

  형제(sweep_webhook_retries)는 똑같은 구조(선-CAS 커밋 → 트랜잭션 밖 동기호출
  → 사후 마무리기록)의 BEGIN IMMEDIATE 구간을 전부 try/except sqlite3.Error:
  rollback 으로 감싸는데(84·144라운드), 이 함수는 그 하드닝을 못 받았다.
  동시 쓰기 경합("database is locked")이 마무리기록 도중 나면 send_attempts는
  이미 커밋됐는데 status만 '발송대기'로 남아 — 성공 건은 다음 스윕이 이미
  보낸 문자를 또 보내려 들고, 무엇보다 예외가 함수 전체를 뚫고 나가 **같은
  배치의 나머지 대기열까지 통째로 처리를 멈춘다.**

      python test_scan_round200_fixes.py
"""
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


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 200라운드 회귀 — 알림 실발송 2단계 마무리기록 무방비")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def sweep_send_notifications(")
i1 = APP_SRC.index("\ndef ", i0 + 1)
body = APP_SRC[i0:i1]
chk(body.count("except sqlite3.Error:") >= 2,
    "★★★★ 반복문 안에 sqlite3.Error 방어가 최소 2곳(선-CAS·사후마무리) 생겼다"
    "(고치기 전엔 이 함수 전체의 반복문 안에 try/except 가 0건이었다)")
#  ⚠ [라운드262] 이 호출에 request_id=n["id"](팝빌 멱등키) 인자가 새로 붙었다 —
#    형식만 갱신, 이 라운드가 확인하려는 지점(실발송 호출이 여기 있다는 사실)은 그대로다.
chk("POPBILL.send(phone, n[\"message\"], n[\"channel\"], request_id=n[\"id\"])" in body,
    "(참고) 팝빌 실발송 호출 위치 확인")

# ============================================================
print("\n[2] 실행 — 한 건의 2단계 마무리기록에서 DB 오류가 나도 배치 전체가 "
      "멈추지 않고, 그 건만 안전하게 건너뛴다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round200_")
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
    p1 = conn.execute(
        "INSERT INTO partners(name,partner_type,status,phone) "
        "VALUES('R200업체1','시공사','활성','01011112222')").lastrowid
    p2 = conn.execute(
        "INSERT INTO partners(name,partner_type,status,phone) "
        "VALUES('R200업체2','시공사','활성','01033334444')").lastrowid
    nid_boom = conn.execute(
        "INSERT INTO notifications(ntype,channel,target,message,status,partner_id,"
        "                          is_demo,created_at) "
        "VALUES('정산','문자','R200업체1','검증 메시지1','발송대기',?,0,?)",
        (p1, now)).lastrowid
    nid_ok = conn.execute(
        "INSERT INTO notifications(ntype,channel,target,message,status,partner_id,"
        "                          is_demo,created_at) "
        "VALUES('정산','문자','R200업체2','검증 메시지2','발송대기',?,0,?)",
        (p2, now)).lastrowid
    conn.commit()

    class _FlakyConn:
        """nid_boom 의 2단계 마무리 UPDATE(status='도달')만 표적으로 실패시킨다."""
        def __init__(self, real, boom_id):
            self._real = real
            self._boom_id = boom_id

        def execute(self, sql, params=()):
            if "status='도달'" in sql and params and params[-1] == self._boom_id:
                raise sqlite3.OperationalError("R200 검증용 강제 실패(2단계 마무리기록)")
            return self._real.execute(sql, params)

        def __getattr__(self, name):
            return getattr(self._real, name)

    real_ready, real_notify_on = NP.ready, A.NOTIFY_ENABLED
    real_send = NP.send
    try:
        NP.ready = lambda: True
        A.NOTIFY_ENABLED = True
        NP.send = lambda phone, msg, ch, **_: (True, "검증용 정상 발송")

        flaky = _FlakyConn(conn, nid_boom)
        out = A.sweep_send_notifications(flaky, only_ids=[nid_boom, nid_ok])

        st_boom = conn.execute(
            "SELECT status, send_attempts FROM notifications WHERE id=?", (nid_boom,)).fetchone()
        st_ok = conn.execute(
            "SELECT status, send_attempts FROM notifications WHERE id=?", (nid_ok,)).fetchone()

        chk(st_ok["status"] == "도달",
            "★★★★ 문제 건(nid_boom) 처리 중 DB 오류가 나도, 같은 배치의 다른 건"
            "(nid_ok)은 정상적으로 끝까지 처리된다(고치기 전엔 예외가 함수 전체를 "
            "뚫고 나가 이 건 자체가 처리되지 않았다)", dict(st_ok))
        chk(st_boom["status"] == "발송대기" and (st_boom["send_attempts"] or 0) >= 1,
            "★★★ 문제 건은 send_attempts 는 커밋됐지만(1단계) status는 안전하게 "
            "'발송대기'로 남는다(2단계가 롤백돼 반쪽 상태로 굳지 않는다)",
            dict(st_boom))
        chk(isinstance(out, dict) and "sent" in out,
            "★★★ sweep 함수 자체가 예외 없이 정상적으로 끝까지 실행되어 요약을 "
            "돌려준다(고치기 전엔 이 지점에 도달하기 전에 예외로 죽었다)", out)
    finally:
        NP.ready, A.NOTIFY_ENABLED, NP.send = real_ready, real_notify_on, real_send
        conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드200 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
