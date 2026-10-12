# -*- coding: utf-8 -*-
"""스캔 145라운드 회귀 — 알림톡·문자 발송(sweep_send_notifications)이 영구
실패(번호없음 즉시실패 · 3회 재시도 소진)로 굳어도 사람에게 알리는 경로가
없던 결함. 형제(sweep_webhook_retries, 144라운드에서 수정)는 재시도 소진 시
notify(운영팀)를 반드시 남기는데, 이 함수만 상태만 '실패'로 바꾸고 끝의
배치 요약 로그("발송 N·실패 M") 한 줄만 남겨 어떤 건이 영구실패인지 특정할
수 없었다. _NTYPE_VIEW 에 이미 있던 "발송실패":"outbox" 매핑도 그 알림을
만드는 notify() 호출이 하나도 없어 죽어 있었다.

      python test_scan_round145_fixes.py
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
print("  스캔 145라운드 회귀 — 알림 발송 영구실패 시 사람에게 알리지 않던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_sn = APP_SRC.index("def sweep_send_notifications(")
i_sn_end = APP_SRC.index("\ndef ", i_sn + 1)
sn_body = APP_SRC[i_sn:i_sn_end]
chk("def _alert_send_failure(n, reason):" in sn_body,
    "★★★ sweep_send_notifications 안에 _alert_send_failure 헬퍼가 신설됐다")
chk('notify(conn, "발송실패", "웹", "운영팀"' in sn_body,
    "★★★ 그 헬퍼가 운영팀에 notify()를 보낸다(죽어있던 _NTYPE_VIEW 매핑을 실제로 채운다)")
chk('_alert_send_failure(n, "수신자 휴대전화 없음")' in sn_body,
    "★ 번호없음 즉시실패 분기도 알림을 부른다")
#  ⚠⚠ [라운드200] 정확한 들여쓰기 칸수를 그대로 박아 두면, 이 블록을 감싸는
#    바깥 구조(200라운드가 try/except 로 한 단 더 감쌌다)가 바뀔 때마다 실제
#    로직은 그대로인데 텍스트만 달라져 거짓 실패한다 — 들여쓰기 무관하게
#    "if final:" 바로 다음 줄이 _alert_send_failure 호출인지만 본다.
import re as _re200
chk(bool(_re200.search(r"if final:\s*\n\s*_alert_send_failure\(n,", sn_body)),
    "★ 3회 소진 분기도 final 일 때만 알림을 부른다(매 실패마다가 아니라)")

# ============================================================
print("\n[2] 실행 준비 — 실제 app.py(전체 임포트) + 팝빌 항상실패 시뮬레이션")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round145_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    pid = conn.execute(
        "INSERT INTO partners(name,phone,status,created_at) "
        "VALUES('R145업체','01099990001','활성',?)", (DB.now(),)).lastrowid
    pid_nophone = conn.execute(
        "INSERT INTO partners(name,phone,status,created_at) "
        "VALUES('R145업체무번호',NULL,'활성',?)", (DB.now(),)).lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R145-CASE','완료','가드레일','서울',0)").lastrowid
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R145-NOPHONE','완료','가드레일','서울',0)").lastrowid
    cid3 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R145-FIRSTFAIL','완료','가드레일','서울',0)").lastrowid
    #  이미 2회 실패한 상태로 심는다 — 이번 스윕이 3번째(마지막) 시도가 되게.
    nid_final = conn.execute(
        """INSERT INTO notifications(ntype,channel,target,message,status,
               partner_id,case_id,is_demo,send_attempts,created_at)
           VALUES('낙찰','문자','R145업체','[R145-CASE] 낙찰 안내','발송대기',
                  ?,?,0,2,?)""", (pid, cid, DB.now())).lastrowid
    #  번호 없는 업체 — 즉시(1회차에) '실패'로 확정되는 경로
    nid_nophone = conn.execute(
        """INSERT INTO notifications(ntype,channel,target,message,status,
               partner_id,case_id,is_demo,send_attempts,created_at)
           VALUES('낙찰','문자','R145업체무번호','[R145-NOPHONE] 낙찰 안내','발송대기',
                  ?,?,0,0,?)""", (pid_nophone, cid2, DB.now())).lastrowid
    #  대조군 — 아직 재시도 여지가 남은 첫 실패(1회차)는 알림이 뜨면 안 된다
    nid_first = conn.execute(
        """INSERT INTO notifications(ntype,channel,target,message,status,
               partner_id,case_id,is_demo,send_attempts,created_at)
           VALUES('낙찰','문자','R145업체','[R145-FIRSTFAIL] 낙찰 안내','발송대기',
                  ?,?,0,0,?)""", (pid, cid3, DB.now())).lastrowid
    conn.commit()

    real_ready, real_send, real_enabled = A.POPBILL.ready, A.POPBILL.send, A.NOTIFY_ENABLED
    A.POPBILL.ready = lambda: True
    A.NOTIFY_ENABLED = True
    A.POPBILL.send = lambda ph, m, ch="문자", **_: (False, "팝빌 오류(재현용 시뮬레이션)")
    try:
        A.sweep_send_notifications(conn, only_ids=[nid_final, nid_nophone, nid_first])
    finally:
        A.POPBILL.ready, A.POPBILL.send, A.NOTIFY_ENABLED = real_ready, real_send, real_enabled

    row_final = dict(conn.execute(
        "SELECT status, send_attempts FROM notifications WHERE id=?", (nid_final,)).fetchone())
    chk(row_final["status"] == "실패" and row_final["send_attempts"] == 3,
        "★ (사전조건) 3회 소진되어 실패로 확정됐다", row_final)
    row_first = dict(conn.execute(
        "SELECT status, send_attempts FROM notifications WHERE id=?", (nid_first,)).fetchone())
    chk(row_first["status"] == "발송대기" and row_first["send_attempts"] == 1,
        "★ (사전조건) 대조군은 1회만 실패해 아직 발송대기 상태다(재시도 예정)", row_first)

    admin_final = conn.execute(
        "SELECT COUNT(*) n FROM notifications WHERE ntype='발송실패' AND audience_type='admin' "
        "AND message LIKE '%R145-CASE%'").fetchone()["n"]
    chk(admin_final == 1,
        "★★★ 3회 소진 건은 운영팀 앞으로 '발송실패' 알림이 정확히 1건 생긴다"
        "(고치기 전엔 0건이었다)", admin_final)

    admin_nophone = conn.execute(
        "SELECT COUNT(*) n FROM notifications WHERE ntype='발송실패' AND audience_type='admin' "
        "AND message LIKE '%R145-NOPHONE%'").fetchone()["n"]
    chk(admin_nophone == 1,
        "★★★ 번호없음 즉시실패 건도 운영팀 알림이 생긴다", admin_nophone)

    admin_firstfail = conn.execute(
        "SELECT COUNT(*) n FROM notifications WHERE ntype='발송실패' "
        "AND message LIKE '%R145-FIRSTFAIL%'").fetchone()["n"]
    chk(admin_firstfail == 0,
        "★★★ 아직 재시도 여지가 있는 1회차 실패는 알림을 안 보낸다(매 실패마다 스팸 아님)",
        admin_firstfail)

    log_final = conn.execute(
        "SELECT COUNT(*) n FROM activity_log WHERE action='알림 발송 실패 확정' "
        "AND detail LIKE ?", (f"%#{nid_final}%",)).fetchone()["n"]
    chk(log_final == 1,
        "★★★ activity_log 에도 그 건 번호로 특정되는 감사기록이 남는다"
        "(고치기 전엔 배치 전체를 뭉뚱그린 한 줄뿐이었다)", log_final)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드145 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
