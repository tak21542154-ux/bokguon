# -*- coding: utf-8 -*-
"""스캔 144라운드 회귀 — 웹훅 재전송이 max_attempts 까지 소진돼 영구실패로
굳어도 사람에게 알리는 경로가 하나도 없던 결함.

  형제(dispatch.sweep_dispatches)는 출동수배 회차를 소진하면 ①전용 상태값
  (CS_FAILED) ②DB.log("사람 개입 필요") ③대시보드 카드, 3단계를 전부 갖췄는데
  웹훅 쪽(sweep_webhook_retries)은 조용히 status='실패'로 굳고 다음 스윕부터
  영원히 재조회 대상에서 빠질 뿐, notifications·activity_log 어디에도 남지
  않았다 — 보험사 전산에 그 이벤트가 다시는 안 들어간다는 사실을 아무도 몰랐다.

      python test_scan_round144_fixes.py
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
print("  스캔 144라운드 회귀 — 웹훅 재전송 영구실패(포기) 시 사람에게 알리지 않던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_sw = APP_SRC.index("def sweep_webhook_retries(")
i_sw_end = APP_SRC.index("\ndef ", i_sw + 1)
sw_body = APP_SRC[i_sw:i_sw_end]
#  ⚠⚠ [라운드412] 조건이 status='실패' 단독에서 status IN ('실패','대기')로
#    넓어졌다(write-back 실패로 '대기'에 박제되는 경로도 '포기'로 못박기
#    위함) — 이 라운드가 검증하려는 행동('포기'로 못박는다) 자체는 그대로라
#    실행기반 검사([2]) 는 안 바뀌었고, 이 문자열 검사만 새 조건에 맞춘다.
chk("status='포기' WHERE id=? " in sw_body and "AND status IN ('실패','대기')" in sw_body,
    "★★★ sweep_webhook_retries 가 재시도 소진 시 status 를 '포기'로 못박는다")
chk('DB.log(conn, "시스템", "웹훅 재전송 포기"' in sw_body,
    "★★★ 포기 시 DB.log 로 감사기록을 남긴다")
chk('notify(conn, "웹훅발송포기"' in sw_body and 'audience_type="admin"' in sw_body,
    "★★★ 포기 시 운영팀에게 notify() 로 알린다")

# ============================================================
print("\n[2] 실행 — 재시도 소진 시 상태·감사로그·알림이 전부 남는다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round144_")
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
    iid = conn.execute(
        "INSERT INTO insurers(name,status,webhook_url,webhook_secret,api_enabled) "
        "VALUES('R144보험','활성','https://real-insurer.example.com/hook','sec',1)").lastrowid
    conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
        "VALUES('R144-CASE','완료','가드레일','서울',?,0)", (iid,))
    conn.commit()

    def _fake_send_always_fail(delivery_id, url, secret, payload_str, count_attempt=True):
        c2 = DB.get_db()
        c2.execute(
            "UPDATE webhook_deliveries SET status=?, http_code=?, error=?, "
            + ("attempts=attempts+1, " if count_attempt else "")
            + "delivered_at=? WHERE id=?",
            ("실패", None, "연결거부(시뮬레이션)", DB.now(), delivery_id))
        c2.commit(); c2.close()

    real_send = A._webhook_send
    A._webhook_send = _fake_send_always_fail
    #  ⚠⚠ [라운드589] deliver_webhook()을 test_request_context() 안에서 부르면
    #    teardown(_flush_webhooks, app.py 2298행)이 실제 전송을 데몬 스레드로
    #    큐잉한다(2336행) — 그 스레드가 아래에서 이 행을 동기적으로 리셋·CAS
    #    하는 것과 진짜로 경합한다(스레드에 join()이 없어 절대 안 죽는다).
    #    이 자리는 원래 "이미 존재하는 배송 행을 실패 상태로 준비"하는 용도일
    #    뿐이라, 형제(round84의 _mk_delivery)가 이미 하듯 배송 행을 직접
    #    INSERT해 비동기 경로 자체를 타지 않는다 — 이 테스트의 대상은
    #    deliver_webhook()이 아니라 sweep_webhook_retries()다.
    #    (실측: round585 배터리 실패(attempts=6 vs 기대값5) 조사 중 스크래치
    #    재현으로, 이 패턴이 시스템이 바쁠 때 스레드의 쓰기가 동기 코드보다
    #    늦게 끼어들면 카운트가 어긋남을 확인 — 대조군 시나리오(아래 R144-OK)
    #    에서는 같은 스크립트를 그대로 재실행만 해도 최종 attempts 가 4 또는 5
    #    로 실제로 갈렸다.)
    did = conn.execute(
        "INSERT INTO webhook_deliveries(insurer_id,event,case_no,payload,target_url,"
        "status,attempts,created_at,delivered_at) "
        "VALUES(?,?,?,?,?,?,?,?,datetime('now','-1 hour'))",
        (iid, "case.completed", "R144-CASE", '{"amount": 5000000}',
         "https://real-insurer.example.com/hook", "실패", 0, DB.now())).lastrowid
    conn.commit()

    rounds = 0
    while True:
        n = A.sweep_webhook_retries(conn, limit=10, max_attempts=5)
        rounds += 1
        if n == 0 or rounds > 20:
            break
        conn.execute("UPDATE webhook_deliveries SET delivered_at=datetime('now','-1 hour') "
                     "WHERE id=?", (did,))
        conn.commit()

    row = conn.execute("SELECT attempts, status FROM webhook_deliveries WHERE id=?", (did,)).fetchone()
    chk(row["attempts"] == 5, "★ (사전조건) 5회 재시도를 실제로 전부 소진했다", dict(row))
    chk(row["status"] == "포기",
        "★★★ 소진 뒤 상태가 '포기'로 명시적으로 굳는다"
        "(고치기 전엔 '실패'로 남아 다음 스윕 대상에서만 조용히 빠졌다)", dict(row))

    n_more = A.sweep_webhook_retries(conn, limit=10, max_attempts=5)
    chk(n_more == 0, "★ 포기 뒤에는 스윕이 이 건을 더는 절대 집지 않는다(무한재발사 아님)", n_more)

    noti = conn.execute(
        "SELECT target, message, url FROM notifications "
        "WHERE ntype='웹훅발송포기' AND audience_type='admin'").fetchone()
    chk(noti is not None and "R144-CASE" in (noti["message"] or ""),
        "★★★ 운영팀 알림이 실제로 생성되고 사건번호를 담는다"
        "(고치기 전엔 notifications 행이 단 하나도 안 남았다)", dict(noti) if noti else None)

    log = conn.execute(
        "SELECT detail FROM activity_log WHERE action='웹훅 재전송 포기'").fetchone()
    chk(log is not None and "R144-CASE" in (log["detail"] or ""),
        "★★★ activity_log 에도 포기 사실과 사건번호가 감사기록으로 남는다", dict(log) if log else None)

    # ── 대조군: 마지막 시도에서 실제로 성공하면 '포기' 오탐이 없어야 한다 ──
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
        "VALUES('R144-OK','완료','가드레일','서울',?,0)", (iid,)).lastrowid
    conn.commit()

    _attempt_box = {"n": 0}

    def _fake_send_succeeds_last(delivery_id, url, secret, payload_str, count_attempt=True):
        _attempt_box["n"] += 1
        c2 = DB.get_db()
        ok = _attempt_box["n"] >= 5   # 5번째(마지막 허용 시도)에만 성공
        c2.execute(
            "UPDATE webhook_deliveries SET status=?, http_code=?, error=?, "
            + ("attempts=attempts+1, " if count_attempt else "")
            + "delivered_at=? WHERE id=?",
            ("성공" if ok else "실패", 200 if ok else None,
             None if ok else "연결거부(시뮬레이션)", DB.now(), delivery_id))
        c2.commit(); c2.close()

    A._webhook_send = _fake_send_succeeds_last
    #  ⚠⚠ [라운드589] 위와 같은 이유로 deliver_webhook()을 거치지 않는다 — 여기선
    #    경합이 attempts 컬럼이 아니라 더 미묘하게 샌다: deliver_webhook()의
    #    teardown이 큐잉한 초기 비동기 전송 1회가 _attempt_box["n"](파이썬
    #    프로세스 내부 카운터)을 조용히 선점하는데, 그 뒤 아무리 DB의 attempts
    #    컬럼을 0으로 되돌려도 이 카운터는 절대 못 되돌린다 — "5번째 시도에만
    #    성공한다"는 대조군의 전제 자체가 매 실행마다 스레드 타이밍에 따라
    #    4번째·5번째로 갈리며 깨져 있었다(성공 여부만 보는 약한 단언이라 겉으로만
    #    안 드러났다).
    did2 = conn.execute(
        "INSERT INTO webhook_deliveries(insurer_id,event,case_no,payload,target_url,"
        "status,attempts,created_at,delivered_at) "
        "VALUES(?,?,?,?,?,?,?,?,datetime('now','-1 hour'))",
        (iid, "case.completed", "R144-OK", '{"amount": 1000}',
         "https://real-insurer.example.com/hook", "실패", 0, DB.now())).lastrowid
    conn.commit()
    rounds = 0
    while True:
        n = A.sweep_webhook_retries(conn, limit=10, max_attempts=5)
        rounds += 1
        if n == 0 or rounds > 20:
            break
        conn.execute("UPDATE webhook_deliveries SET delivered_at=datetime('now','-1 hour') "
                     "WHERE id=?", (did2,))
        conn.commit()

    row2 = conn.execute("SELECT attempts, status FROM webhook_deliveries WHERE id=?", (did2,)).fetchone()
    chk(row2["status"] == "성공",
        "★ (대조군) 마지막 허용 시도에서 실제로 성공하면 status='성공'으로 남는다", dict(row2))
    chk(row2["attempts"] == 5,
        "★★ (대조군) 성공이 정확히 5번째 시도에서 일어난다 — 4번째에 조기 성공하면 "
        "'마지막 허용 시도'라는 이 대조군의 전제 자체가 깨진 것"
        "(고치기 전엔 deliver_webhook()의 초기 비동기 전송이 내부 카운터를 조용히 "
        "선점해 4번째에 성공하기도 했다)", dict(row2))
    noti2 = conn.execute(
        "SELECT COUNT(*) n FROM notifications WHERE ntype='웹훅발송포기' AND message LIKE '%R144-OK%'"
    ).fetchone()["n"]
    chk(noti2 == 0,
        "★★★ 마지막 시도에서 성공했으면 '포기' 알림이 오탐으로 뜨지 않는다", noti2)

    A._webhook_send = real_send
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드144 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
