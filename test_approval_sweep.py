# -*- coding: utf-8 -*-
"""완료승인 자동 독촉 회귀 검사.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

돈이 실제로 멈추는 곳은 '보험사 공사 완료 승인'이다. 그 승인이 없으면
수수료 수납도 협력사 지급도 함께 멈춘다. 그런데 지금까지 이 구간은
**사람이 어드민을 열고 버튼을 눌러야만** 알림이 갔다 — 아무도 안 열면
영원히 아무 일도 일어나지 않는다(운영 DB 에서 최장 62일 대기).

검사의 초점은 '보내는가'보다 **'스팸이 되지 않는가'** 다.
잘못 만들면 밀린 100건에 100통이 한꺼번에 나가고, 다음 5분 뒤에 또 나간다.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("BOKGUON_LOG_FILE",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "logs", "test.log"))
import db as DB
import app as A

OK = FAIL = 0
MARK = "APPRSWEEP"


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
        conn.execute("DELETE FROM notifications WHERE case_id=?", (cid,))
        conn.execute("DELETE FROM settlements WHERE case_id=?", (cid,))
        conn.execute("DELETE FROM cases WHERE id=?", (cid,))
    conn.execute("DELETE FROM notifications WHERE ntype='완료승인독촉' AND target='운영팀' "
                 " AND message LIKE '%자동 발송%' AND julianday('now','+9 hours')"
                 " - julianday(created_at) < 0.01")
    conn.commit()


def mk(conn, iid, no, days, approved=0, transfer="대기", demo=0, void=None):
    """N일 전에 생긴 정산 1건."""
    conn.execute(
        "INSERT INTO cases(case_no, insurer_id, category, region, status) "
        "VALUES(?,?,?,?,'정산진행')", (no, iid, "가드레일·방호울타리", "서울"))
    cid = conn.execute("SELECT last_insert_rowid() r").fetchone()[0]
    conn.execute(
        "INSERT INTO settlements(case_id, case_no, insurer, insurer_id, partner_name, "
        "  amount, fee, payout, insurer_paid, review_status, transfer_status, "
        "  insurer_approved, is_demo, void_status, created_at) "
        "VALUES(?,?,(SELECT name FROM insurers WHERE id=?),?, '검증업체', "
        "  1000000,100000,900000,'대기','대기',?,?,?,?, "
        "  datetime('now','+9 hours', ?))",
        (cid, no, iid, iid, transfer, approved, demo, void, f"-{days} days"))
    return cid


def main():
    conn = DB.get_db()
    cleanup(conn)
    print("=" * 70)
    print("  완료승인 자동 독촉")
    print("=" * 70)
    iid = conn.execute("SELECT id FROM insurers LIMIT 1").fetchone()[0]

    # 대상 2건(5일·10일) + 대상 아닌 4건
    c_old = mk(conn, iid, f"{MARK}-10일", 10)
    c_mid = mk(conn, iid, f"{MARK}-5일", 5)
    mk(conn, iid, f"{MARK}-1일", 1)                        # 아직 기한 전
    mk(conn, iid, f"{MARK}-승인됨", 20, approved=1)         # 이미 승인
    mk(conn, iid, f"{MARK}-이체완료", 20, transfer="이체완료")  # 이미 끝남
    mk(conn, iid, f"{MARK}-데모", 20, demo=1)               # 데모 데이터
    mk(conn, iid, f"{MARK}-취소", 20, void="취소")           # 취소된 정산
    conn.commit()

    def sent_for(cid):
        return conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE case_id=? AND ntype='완료승인독촉'",
            (cid,)).fetchone()[0]

    #  ⚠ 운영 DB 에는 이미 정체된 정산이 여럿 있다(그게 이 기능을 만든 이유다).
    #    스윕의 전역 반환값을 단언하면 남의 데이터에 따라 결과가 흔들린다
    #    — **내가 만든 행만** 센다.
    def mine_sent():
        return conn.execute(
            """SELECT COUNT(*) FROM notifications n JOIN cases c ON c.id = n.case_id
                WHERE n.ntype='완료승인독촉' AND c.case_no LIKE ?""",
            (f"{MARK}%",)).fetchone()[0]

    print("\n[1] 대상 선별")
    A.sweep_approval_overdue(conn)
    chk(mine_sent() == 2, "★ 내 검증 건 중 기한 넘긴 2건만 발송", f"{mine_sent()}통")
    chk(sent_for(c_old) == 1 and sent_for(c_mid) == 1, "10일·5일 건에 각각 1통")
    for no in ("1일", "승인됨", "이체완료", "데모", "취소"):
        cid = conn.execute("SELECT id FROM cases WHERE case_no=?",
                           (f"{MARK}-{no}",)).fetchone()[0]
        chk(sent_for(cid) == 0, f"★ '{no}' 건에는 안 보낸다")

    print("\n[2] 스팸 방지 — 여기가 핵심")
    before = mine_sent()
    A.sweep_approval_overdue(conn)
    chk(mine_sent() == before,
        "★★ 바로 다시 돌려도 한 통도 더 안 나간다(24h 쿨다운)", f"{before}→{mine_sent()}")
    chk(sent_for(c_old) == 1, "★★ 5분마다 도는 스윕이 같은 건을 반복 발송하지 않는다")

    # 수동 독촉과 쿨다운을 공유하는가 — 안 그러면 '어제 눌렀는데 오늘 또 갔다'가 된다
    print("\n[3] 수동 독촉과 같은 쿨다운을 쓰는가")
    conn.execute("DELETE FROM notifications WHERE case_id=?", (c_old,))
    conn.execute(
        "INSERT INTO notifications(ntype, channel, target, message, status, case_id, created_at) "
        "VALUES('완료승인독촉','웹','발주처','수동 독촉','발송대기',?,"
        "  datetime('now','+9 hours','-2 hours'))", (c_old,))
    conn.commit()
    A.sweep_approval_overdue(conn)
    chk(sent_for(c_old) == 1,
        "★ 2시간 전 수동 독촉이 있으면 자동은 안 보낸다", f"{sent_for(c_old)}통")

    print("\n[4] 하루 지나면 다시 알린다")
    conn.execute("UPDATE notifications SET created_at=datetime('now','+9 hours','-30 hours') "
                 " WHERE case_id=?", (c_old,))
    conn.commit()
    A.sweep_approval_overdue(conn)
    chk(sent_for(c_old) == 2, "★ 30시간 지나면 한 번 더 간다", f"{sent_for(c_old)}통")

    print("\n[5] 한 번에 몰아 보내지 않는가")
    chk(A.APPROVAL_REMIND_BATCH <= 50,
        f"★ 1회 발송 상한이 있다({A.APPROVAL_REMIND_BATCH}건) — 밀린 게 많아도 폭주하지 않는다")

    print("\n[6] 예약 실행에 실제로 연결됐는가")
    mg = open("manage.py", encoding="utf-8").read()
    chk("sweep_approval_overdue" in mg,
        "★ manage.py sweep 이 이 함수를 부른다(안 부르면 영원히 안 돈다)")

    cleanup(conn)
    conn.close()
    print("-" * 70)
    print(f"  통과 {OK} · 실패 {FAIL}   (검증 데이터 정리됨)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
