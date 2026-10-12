# -*- coding: utf-8 -*-
"""동시성·안정성 확정 결함 회귀 검사.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

  #15-A 웹훅 배송 이력이 커밋 없이 롤백된다 (보험사엔 갔는데 우리 기록엔 없다)
  #20   AI 사진 분류가 담당자의 재분류를 덮어쓴다 (기계가 사람을 이긴다)
  #22   로그 회전 경합 — 다른 프로세스가 파일을 열면 로그 줄이 사라진다

각 검사는 '고치기 전이라면 반드시 실패하는' 형태로 쓴다.
그렇지 않으면 나중에 누가 되돌려놔도 초록불이 유지된다.
"""
import os
import sys
import logging
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# [Windows] 운영 서버가 연 로그 파일을 검증까지 함께 열면 회전이 실패한다 — 자기 파일로.
os.environ.setdefault("BOKGUON_LOG_FILE",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "logs", "test.log"))
import db as DB
import app as A

OK = FAIL = 0
MARK = "CONCTEST"


def chk(cond, label, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}   {detail}")


def cleanup(conn):
    for cid in [r[0] for r in conn.execute(
            "SELECT id FROM cases WHERE case_no LIKE ?", (f"{MARK}%",))]:
        for t in ("photos", "ai_reviews", "notifications", "webhook_deliveries"):
            try:
                conn.execute(f"DELETE FROM {t} WHERE case_id=?", (cid,))
            except Exception:
                pass
        conn.execute("DELETE FROM cases WHERE id=?", (cid,))
    conn.execute("DELETE FROM webhook_deliveries WHERE case_no LIKE ?", (f"{MARK}%",))
    conn.execute("DELETE FROM insurers WHERE name LIKE ?", (f"{MARK}%",))
    conn.commit()


def main():
    conn = DB.get_db()
    cleanup(conn)
    print("=" * 70)
    print("  동시성·안정성 회귀 검사")
    print("=" * 70)

    # ── #15-A 웹훅 배송 이력이 살아남는가 ────────────────────────
    print("\n[15-A] 웹훅 배송 이력")
    conn.execute(
        "INSERT INTO insurers(name, api_enabled, webhook_url, webhook_secret) "
        "VALUES(?,1,'http://127.0.0.1:9/nowhere','s3cr3t')", (f"{MARK}보험",))
    iid = conn.execute("SELECT last_insert_rowid() r").fetchone()[0]
    conn.commit()

    before = conn.execute("SELECT COUNT(*) FROM webhook_deliveries").fetchone()[0]
    #  실제 라우트와 같은 순서를 재현한다: 업무 커밋 → safe_webhook → close
    c2 = DB.get_db()
    c2.execute("BEGIN IMMEDIATE")
    c2.execute("INSERT INTO cases(case_no, insurer_id, category, region, status) "
               "VALUES(?,?,?,?,'시공중')",
               (f"{MARK}-W1", iid, "가드레일·방호울타리", "서울"))
    c2.commit()                                   # ← 업무 확정
    with A.app.test_request_context("/"):         # deliver_webhook 이 g 를 쓴다
        A.safe_webhook(c2, iid, "case.awarded", f"{MARK}-W1", {"amount": 1000})
        c2.commit()                               # ★ 이 한 줄이 이번 수정의 전부다
    c2.close()                                    # 예전에는 여기서 이력이 롤백됐다

    after = conn.execute("SELECT COUNT(*) FROM webhook_deliveries").fetchone()[0]
    chk(after == before + 1,
        "★ 배송 이력이 close() 후에도 남는다(예전엔 롤백돼 0건)", f"{before}→{after}")
    row = conn.execute(
        "SELECT event, case_no, status FROM webhook_deliveries WHERE case_no=?",
        (f"{MARK}-W1",)).fetchone()
    chk(row and row["event"] == "case.awarded", "이벤트·사건번호가 그대로 남음")

    # id 재사용이 없는가 — 롤백되면 AUTOINCREMENT 가 되감겨 다음 배송이 같은 id 를 받는다
    c3 = DB.get_db()
    with A.app.test_request_context("/"):
        A.deliver_webhook(c3, iid, "case.completed", f"{MARK}-W1", {"x": 1})
        c3.commit()
    c3.close()
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM webhook_deliveries WHERE case_no=? ORDER BY id", (f"{MARK}-W1",))]
    chk(len(ids) == 2 and ids[0] != ids[1],
        "★ 연속 배송이 서로 다른 id 를 받는다(id 재사용 시 남의 행을 덮어쓴다)", f"{ids}")

    # ── #20 AI 가 사람 판단을 덮지 못하는가 ──────────────────────
    print("\n[20] AI 분류 vs 담당자 재분류")
    conn.execute("INSERT INTO cases(case_no, insurer_id, category, region, status) "
                 "VALUES(?,?,?,?,'시공중')",
                 (f"{MARK}-P1", iid, "가드레일·방호울타리", "서울"))
    cid = conn.execute("SELECT last_insert_rowid() r").fetchone()[0]

    def mkphoto(kind=None, review="대기"):
        conn.execute(
            "INSERT INTO photos(case_id, rel_path, orig_name, kind, review_status, created_at) "
            "VALUES(?,?,?,?,?,datetime('now','+9 hours'))",
            (cid, f"{MARK}/x.jpg", "x.jpg", kind, review))
        return conn.execute("SELECT last_insert_rowid() r").fetchone()[0]

    #  ① 아직 아무도 안 건드린 사진 — AI 가 분류해도 된다
    p_free = mkphoto()
    conn.commit()
    n = conn.execute(
        "UPDATE photos SET kind=?, ai_kind=?, ai_confidence=88 "
        " WHERE id=? AND kind IS NULL AND review_status='대기'",
        ("시공중", "시공중", p_free)).rowcount
    conn.commit()
    chk(n == 1, "미분류 사진은 AI 가 분류한다", f"rowcount={n}")

    #  ② 담당자가 이미 분류한 사진 — AI 가 **덮으면 안 된다**
    p_human = mkphoto(kind="착공전")
    conn.commit()
    n2 = conn.execute(
        "UPDATE photos SET kind=?, ai_kind=? "
        " WHERE id=? AND kind IS NULL AND review_status='대기'",
        ("완료", "완료", p_human)).rowcount
    conn.commit()
    chk(n2 == 0, "★ 사람이 분류한 사진은 AI 가 못 덮는다", f"rowcount={n2}")
    got = conn.execute("SELECT kind FROM photos WHERE id=?", (p_human,)).fetchone()[0]
    chk(got == "착공전", "★ 사람 값이 그대로 유지된다", got)

    #  ③ 검수까지 끝난 사진도 마찬가지
    p_done = mkphoto(kind=None, review="승인")
    conn.commit()
    n3 = conn.execute(
        "UPDATE photos SET kind=? WHERE id=? AND kind IS NULL AND review_status='대기'",
        ("완료", p_done)).rowcount
    conn.commit()
    chk(n3 == 0, "★ 검수 끝난 사진도 AI 가 못 건드린다", f"rowcount={n3}")

    #  ④ 실제 코드가 그 조건을 쓰고 있는가 (조건을 지우면 여기서 걸린다)
    src = open(A.__file__, encoding="utf-8").read()
    chk("WHERE id=? AND kind IS NULL AND review_status='대기'" in src,
        "★ 업로드 경로가 조건부 UPDATE 를 실제로 쓴다")

    #  ⑤ AI 판정 전에 사람이 분류한 건도 검수 이력에 남는가
    chk('if not photo.get("ai_kind") and route != "사람검수":' in src,
        "★ 사람검수는 ai_kind 없이도 이력에 남는다")
    chk("FROM ai_reviews WHERE COALESCE(ai_kind,'') <> ''" in src,
        "AI 정확도 통계는 사람전용 행을 모집단에서 뺀다")

    # ── #22 로그 회전 경합에서 줄을 잃지 않는가 ──────────────────
    print("\n[22] 로그 회전 경합")
    d = tempfile.mkdtemp()
    lf = os.path.join(d, "rot.log")
    h = A._WinSafeRotatingFileHandler(lf, maxBytes=2000, backupCount=5,
                                      encoding="utf-8", delay=True)
    lg = logging.getLogger(MARK)
    lg.setLevel(logging.INFO)
    lg.handlers = [h]
    lg.propagate = False
    for i in range(40):
        lg.info("warmup " + "x" * 60)
    h.flush()
    blocker = open(lf, "rb")            # 다른 프로세스가 파일을 연 상태 재현
    for i in range(40):
        lg.info("MARK-%03d %s" % (i, "y" * 50))
    h.flush()
    blocker.close()
    body = ""
    for f in sorted(os.listdir(d)):
        body += open(os.path.join(d, f), encoding="utf-8", errors="replace").read()
    found = sum(1 for i in range(40) if ("MARK-%03d" % i) in body)
    chk(found == 40, "★ 회전이 막혀도 로그 줄을 한 줄도 안 잃는다", f"{found}/40")
    h.close()

    #  예약 실행 프로세스가 운영 로그와 분리됐는가
    mg = open("manage.py", encoding="utf-8").read()
    chk('os.environ.setdefault("BOKGUON_LOG_FILE"' in mg,
        "★ manage.py 가 자기 로그 파일을 쓴다(경합원 제거)")

    cleanup(conn)
    conn.close()
    print("-" * 70)
    print(f"  통과 {OK} · 실패 {FAIL}   (검증 데이터 정리됨)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
