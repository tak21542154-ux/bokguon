# -*- coding: utf-8 -*-
"""협력사 공정성 5건 회귀 검사.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

이 다섯 가지는 결국 한 가지 문제였다 — **협력사가 자기 일의 결과를 알 수 없다.**
  ③ 입찰 결과 통보 — 떨어졌다는 말을 아무도 안 해줬다
  ④ 하자 귀책 — 판정에 대해 말할 창구가 없었다
  ⑤ 정산 지연 — '대기' 두 글자뿐, 이유도 내 차례인지도 몰랐다
  ⑰ 평점·강등 — 왜 깎였는지, 왜 내려갔는지 안 알려줬다
  ⑩ 출동 결렬 — 현장 다녀와 견적까지 냈는데 결과를 못 들었다

각 검사는 '고치기 전이라면 반드시 실패하는' 형태로 쓴다.
그렇지 않으면 나중에 누가 되돌려놔도 초록불이 유지된다.
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import db as DB
import os
# [Windows] 운영 서버가 연 로그 파일을 검증까지 함께 열면 회전이 실패한다 — 자기 파일로.
os.environ.setdefault("BOKGUON_LOG_FILE",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "logs", "test.log"))
import app as A

OK = FAIL = 0
MARK = "FAIRTEST"


def chk(cond, label, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}   {detail}")


def one(cur):
    r = cur.fetchone()
    return dict(r) if r else None


def main():
    conn = DB.get_db()
    print("=" * 70)
    print("  협력사 공정성 회귀 검사")
    print("=" * 70)

    # ── 준비: 검증용 보험사·업체 3곳·사건·경매·입찰 ──────────────
    iid = one(conn.execute("SELECT id FROM insurers LIMIT 1"))["id"]
    pids = []
    for i in range(3):
        conn.execute(
            "INSERT INTO partners(name, partner_type, major, region, status, login_id) "
            "VALUES(?,?,?,?,'활성',?)",
            (f"{MARK}업체{i}", "시행사", "가드레일·방호울타리", "서울", f"{MARK}-{i}"))
        pids.append(conn.execute("SELECT last_insert_rowid() r").fetchone()[0])
    conn.execute(
        "INSERT INTO cases(case_no, insurer_id, category, region, status, est_price) "
        "VALUES(?,?,?,?,'입찰중',10000000)",
        (f"{MARK}-C1", iid, "가드레일·방호울타리", "서울"))
    cid = conn.execute("SELECT last_insert_rowid() r").fetchone()[0]
    conn.execute("INSERT INTO auctions(case_id, status, deadline) "
                 "VALUES(?, '진행', datetime('now','+9 hours','+1 day'))", (cid,))
    aid = conn.execute("SELECT last_insert_rowid() r").fetchone()[0]
    for i, pid in enumerate(pids):
        conn.execute("INSERT INTO bids(auction_id, partner_id, partner_name, amount, days) "
                     "VALUES(?,?,?,?,5)", (aid, pid, f"{MARK}업체{i}", 9000000 - i * 100000))
    conn.commit()

    # ── ③ 입찰 결과 통보 — 떨어진 업체 전원에게 간다 ──────────────
    print("\n[3] 입찰 결과 통보")
    sent = A.notify_bid_losers(conn, aid, f"{MARK}-C1", cid, pids[2])
    conn.commit()
    chk(sent == 2, "★ 패자 2곳 모두 통보 대상", f"실제 {sent}곳")
    losers = A.rows(conn.execute(
        "SELECT partner_id, message FROM notifications "
        " WHERE ntype='입찰결과' AND case_id=?", (cid,)))
    chk({l["partner_id"] for l in losers} == {pids[0], pids[1]},
        "낙찰업체는 제외되고 패자만 수신")
    chk(all(l["partner_id"] for l in losers), "수신자(partner_id) 라우팅이 붙어 있음")
    # ★ 법률 철칙 — 경쟁가·낙찰가·낙찰업체는 절대 새어나가면 안 된다
    leak = [l for l in losers
            if any(t in (l["message"] or "")
                   for t in ("8,800,000", "8,900,000", "9,000,000", f"{MARK}업체2"))]
    chk(not leak, "★ 낙찰가·경쟁가·낙찰업체명이 새지 않음", str(leak[:1]))

    # ── ⑤ 정산 지연 사유 — 멈춘 지점을 사람 말로 ─────────────────
    print("\n[5] 정산 지연 사유")
    conn.execute(
        "INSERT INTO settlements(case_id, case_no, insurer_id, partner_id, partner_name, "
        "  amount, fee, payout, insurer_paid, review_status, transfer_status, created_at) "
        "VALUES(?,?,?,?,?,9000000,900000,8100000,'대기','대기','대기',"
        "  datetime('now','+9 hours','-9 days'))",
        (cid, f"{MARK}-C1", iid, pids[2], f"{MARK}업체2"))
    conn.commit()
    s = one(conn.execute("SELECT * FROM settlements WHERE case_no=?", (f"{MARK}-C1",)))
    st, rsn, mine = A.settlement_wait_info(conn, s, has_account=True)
    chk(st == "보험사 완료 승인 대기", "승인 전에는 '보험사 완료 승인 대기'", st)
    chk(len(rsn) > 5 and not mine, "사유 문장이 있고, 내 차례가 아님을 구분")

    conn.execute("UPDATE settlements SET insurer_approved=1 WHERE case_no=?", (f"{MARK}-C1",))
    conn.commit()
    s = one(conn.execute("SELECT * FROM settlements WHERE case_no=?", (f"{MARK}-C1",)))
    st, _, _ = A.settlement_wait_info(conn, s, has_account=True)
    chk(st == "보험사 입금 대기", "승인 후에는 '보험사 입금 대기'", st)

    conn.execute("UPDATE settlements SET insurer_paid='입금완료' WHERE case_no=?",
                 (f"{MARK}-C1",))
    conn.commit()
    s = one(conn.execute("SELECT * FROM settlements WHERE case_no=?", (f"{MARK}-C1",)))
    st, _, mine = A.settlement_wait_info(conn, s, has_account=False)
    chk(st == "계좌 등록 필요" and mine, "★ 계좌가 없으면 '내 조치 필요'로 구분", st)
    st, _, mine = A.settlement_wait_info(conn, s, has_account=True)
    chk(st == "복구온 검수 중" and not mine, "계좌가 있으면 '복구온 검수 중'", st)

    # 열린 하자는 지급을 막는다 — 그 사실이 사유로 나와야 한다
    conn.execute(
        "INSERT INTO defects(defect_no, case_id, case_no, partner_id, partner_name, "
        "  title, severity, status, cost_bearer) "
        "VALUES(?,?,?,?,?,'검증하자','보통','접수','시행사')",
        (f"{MARK}-D1", cid, f"{MARK}-C1", pids[2], f"{MARK}업체2"))
    conn.commit()
    st, rsn, mine = A.settlement_wait_info(conn, s, has_account=True)
    chk(st == "하자 처리 중" and mine, "★ 열린 하자가 지급을 막는 사실이 사유로 노출", st)
    chk(f"{MARK}-D1" in rsn, "어떤 하자인지 하자번호까지 알려줌", rsn)

    # ── ④ 하자 귀책 이의 ────────────────────────────────────────
    print("\n[4] 하자 귀책 이의")
    d = one(conn.execute("SELECT * FROM defects WHERE defect_no=?", (f"{MARK}-D1",)))
    chk("dispute_reason" in d and "disputed_at" in d, "이의 컬럼이 마이그레이션됨")
    chk(A.app.view_functions.get("api_partner_defect_dispute") is not None,
        "★ 이의 제기 경로가 등록돼 있음")

    # ── ⑰ 평점 — 산식이 하나로 통합됐는가 ────────────────────────
    print("\n[17] 평점 산식")
    pid = pids[2]
    val, basis = A.partner_rating(conn, pid)
    chk(val is None and basis["happy_calls"] == 0,
        "★ 해피콜이 없으면 평점을 지어내지 않음", f"{val}")
    # ⚠ happy_calls.case_id 는 UNIQUE — 사건 하나에 해피콜 하나다. 사건을 따로 만든다.
    hc_cids = []
    for i, sc in enumerate((5, 4)):
        conn.execute(
            "INSERT INTO cases(case_no, insurer_id, category, region, status) "
            "VALUES(?,?,?,?,'완료')",
            (f"{MARK}-H{i}", iid, "가드레일·방호울타리", "서울"))
        hcid = conn.execute("SELECT last_insert_rowid() r").fetchone()[0]
        hc_cids.append(hcid)
        conn.execute("INSERT INTO happy_calls(partner_id, case_id, score, created_at) "
                     "VALUES(?,?,?,datetime('now','+9 hours'))", (pid, hcid, sc))
    conn.commit()
    val, basis = A.partner_rating(conn, pid)
    chk(val == 4.5 and basis["penalty"] == 0, "해피콜 평균이 기본점", f"{val} {basis}")
    # 귀책 하자를 '완료'로 → 차감
    conn.execute("UPDATE defects SET status='완료' WHERE defect_no=?", (f"{MARK}-D1",))
    conn.commit()
    val2, basis2 = A.partner_rating(conn, pid)
    chk(val2 == 4.4 and basis2["penalty"] == 0.1, "귀책 하자(보통) 0.1점 차감",
        f"{val2} {basis2}")
    # ★ 새 해피콜이 들어와도 누적 차감이 사라지면 안 된다(통합 전 실제 버그)
    conn.execute("INSERT INTO cases(case_no, insurer_id, category, region, status) "
                 "VALUES(?,?,?,?,'완료')",
                 (f"{MARK}-H9", iid, "가드레일·방호울타리", "서울"))
    hcid = conn.execute("SELECT last_insert_rowid() r").fetchone()[0]
    hc_cids.append(hcid)
    conn.execute("INSERT INTO happy_calls(partner_id, case_id, score, created_at) "
                 "VALUES(?,?,5,datetime('now','+9 hours'))", (pid, hcid))
    conn.commit()
    val3, basis3 = A.partner_rating(conn, pid)
    chk(basis3["penalty"] == 0.1,
        "★ 새 해피콜이 하자 차감을 지우지 않음", f"{val3} {basis3}")
    A.refresh_partner_rating(conn, pid)
    conn.commit()
    cached = one(conn.execute("SELECT rating FROM partners WHERE id=?", (pid,)))["rating"]
    chk(abs((cached or 0) - val3) < 0.001, "목록용 캐시(partners.rating)도 같은 값", f"{cached}")
    # 비용 부담이 시행사가 아니면 차감하지 않는다(우리 귀책까지 업체에 물리지 않는다)
    conn.execute("UPDATE defects SET cost_bearer='보험사' WHERE defect_no=?", (f"{MARK}-D1",))
    conn.commit()
    _, basis4 = A.partner_rating(conn, pid)
    chk(basis4["penalty"] == 0, "★ 시행사 귀책이 아니면 차감 없음", f"{basis4}")

    # ── ⑰ 상태 변경 사유 컬럼 ────────────────────────────────────
    print("\n[17] 업체 상태 변경 사유")
    p = one(conn.execute("SELECT * FROM partners WHERE id=?", (pid,)))
    chk(all(k in p for k in ("status_reason", "status_changed_at", "status_changed_by")),
        "상태 변경 사유 컬럼이 마이그레이션됨")

    # ── 정리 ───────────────────────────────────────────────────
    conn.execute("DELETE FROM notifications WHERE case_id=?", (cid,))
    conn.execute("DELETE FROM happy_calls WHERE partner_id IN (%s)"
                 % ",".join("?" * len(pids)), tuple(pids))
    conn.execute("DELETE FROM cases WHERE case_no LIKE ?", (f"{MARK}-H%",))
    conn.execute("DELETE FROM defects WHERE case_id=?", (cid,))
    conn.execute("DELETE FROM settlements WHERE case_id=?", (cid,))
    conn.execute("DELETE FROM bids WHERE auction_id=?", (aid,))
    conn.execute("DELETE FROM auctions WHERE case_id=?", (cid,))
    conn.execute("DELETE FROM cases WHERE id=?", (cid,))
    conn.execute("DELETE FROM partners WHERE name LIKE ?", (f"{MARK}%",))
    conn.commit()
    conn.close()

    print("-" * 70)
    print(f"  통과 {OK} · 실패 {FAIL}   (검증 데이터 정리됨)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
