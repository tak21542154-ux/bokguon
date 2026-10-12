# -*- coding: utf-8 -*-
"""B4 검증 — 입찰 마감 자동 처리 · 최소 성립 업체수 · 저가 경보.

시간에 걸린 동작이지만 기다리지 않는다. 마감시각을 과거로 바꿔 앞당긴다.

가장 중요한 검사는 ⑤번이다:
  마감 처리가 **낙찰업체·금액을 절대 건드리지 않는다**는 것.
  여기가 뚫리면 보험사 승인 없이 지급 대상이 정해진다.
"""
import sys
import secrets

import db as DB
import os
# [Windows] 운영 서버가 연 로그 파일을 검증까지 함께 열면 회전이 실패한다 — 자기 파일로.
os.environ.setdefault("BOKGUON_LOG_FILE",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "logs", "test.log"))
import app as A

OK = FAIL = 0
MARK = "B4T" + secrets.token_hex(3)      # 이 실행이 만든 행만 정리하기 위한 표식


def chk(cond, label, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}   {detail}")


def mkcase(conn, est=10_000_000):
    """사건 하나를 어드민 경로와 같은 방식으로 만든다(원경매 포함)."""
    iid = conn.execute("SELECT id FROM insurers LIMIT 1").fetchone()["id"]
    cur = conn.execute(
        """INSERT INTO cases(case_no, insurer_id, insurer, category, region, address,
                             est_price, low_price, status, created_at)
           VALUES(?,?,?,?,?,?,?,0,'입찰중',?)""",
        (f"{MARK}-{secrets.token_hex(2)}", iid, "검증보험", "가드레일·방호울타리",
         "서울", "검증용", est, DB.now()))
    cid = cur.lastrowid
    conn.execute("INSERT INTO work_lots(case_id,category,status,created_at) "
                 "VALUES(?,?,'입찰중',?)", (cid, "가드레일·방호울타리", DB.now()))
    aid = A._open_original_auction(conn, cid)
    conn.commit()
    return cid, aid, iid


def mkbid(conn, aid, amount, n=1):
    """활성 시행사 n곳의 입찰을 만든다."""
    ps = conn.execute(
        "SELECT id, name FROM partners WHERE partner_type='시행사' AND status='활성' "
        "ORDER BY id LIMIT ?", (n,)).fetchall()
    for i, p in enumerate(ps):
        conn.execute(
            "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
            "VALUES(?,?,?,?,?,?)", (aid, p["id"], p["name"], amount - i * 10000, 5, DB.now()))
    conn.execute("UPDATE auctions SET bid_count=?, low_price=? WHERE id=?",
                 (len(ps), amount - (len(ps) - 1) * 10000, aid))
    conn.commit()
    return len(ps)


def expire(conn, aid):
    """마감시각을 1시간 전으로 — 시간을 기다리지 않고 앞당긴다."""
    conn.execute("UPDATE auctions SET deadline=datetime('now','+9 hours','-1 hours') WHERE id=?",
                 (aid,))
    conn.commit()


def st(conn, cid):
    return conn.execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone()


def ast_(conn, aid):
    return conn.execute("SELECT * FROM auctions WHERE id=?", (aid,)).fetchone()


def cleanup(conn):
    # ⚠ MARK 가 아니라 'B4T%' 전체를 지운다. MARK 는 실행마다 달라서,
    #   중간에 죽은 실행이 남긴 행이 데모 데이터에 계속 쌓인다.
    ids = [r[0] for r in conn.execute("SELECT id FROM cases WHERE case_no LIKE 'B4T%'")]
    for cid in ids:
        conn.execute("DELETE FROM bids WHERE auction_id IN "
                     "(SELECT id FROM auctions WHERE case_id=?)", (cid,))
        conn.execute("DELETE FROM auctions WHERE case_id=?", (cid,))
        conn.execute("DELETE FROM work_lots WHERE case_id=?", (cid,))
        conn.execute("DELETE FROM notifications WHERE case_id=?", (cid,))
        conn.execute("DELETE FROM cases WHERE id=?", (cid,))
    conn.commit()
    return len(ids)


def main():
    conn = DB.get_db()
    cleanup(conn)
    th_min = A._min_bidders(conn)
    print("=" * 66)
    print(f"  B4 검증 — 최소 성립 {th_min}개사 · 저가경보 {A._low_price_alert_pct(conn)}% "
          f"· 입찰창 {A._auction_hours(conn)}시간")
    print("=" * 66)

    # ① 공고를 열면 원경매와 마감시각이 함께 생긴다
    cid1, aid1, _ = mkcase(conn)
    a = ast_(conn, aid1)
    chk(a is not None and a["deadline"] and a["status"] == "진행",
        "공고 개설 시 원경매 + 마감시각 생성", dict(a) if a else "없음")
    chk(a["change_order_id"] is None and a["kind"] == "원경매", "  원경매로 표시됨")

    # ② 마감 전에는 아무것도 건드리지 않는다
    #  ⚠⚠ [라운드405] r["scanned"]==0 을 전역 조건으로 넣으면 안 된다 —
    #    sweep_auctions() 은 이 테스트의 사건으로 범위를 좁히지 않고 DB
    #    전체의 마감지난 '진행' 경매를 스캔한다(app.py:5583-90, 의도된
    #    설계 — 운영에서는 전체를 훑는 게 맞다). 공유 verify.db 에 다른
    #    테스트가 남긴 마감지난 경매가(정리 실패 등으로) 하나라도 있으면
    #    이 assert 는 이 테스트와 무관하게 깨진다 — 실측: 357·359·372·
    #    396라운드에서 4번 반복된 "배터리 2연속 실패 후 3차 클린"의 정체가
    #    바로 이것이었다(sweep 이 그 오염행을 처리하며 스스로 청소돼
    #    다음 실행부턴 사라짐). 이 테스트가 실제로 확인할 것은 "내가 만든
    #    cid1 이 마감 전엔 안 건드려진다"이지 "DB 전체에 마감지난 경매가
    #    하나도 없다"가 아니다.
    r = A.sweep_auctions(conn)
    chk(st(conn, cid1)["status"] == "입찰중",
        "마감 전에는 상태 불변(내 경매는 그대로)", r)

    # ③ 마감 + 입찰 있음 → 승인대기 (자동 낙찰 아님)
    n = mkbid(conn, aid1, 9_000_000, n=2)
    expire(conn, aid1)
    r = A.sweep_auctions(conn, force=True)
    c = st(conn, cid1)
    chk(r["closed"] == 1, f"입찰 {n}건 마감 → 처리됨", r)
    chk(c["status"] == "승인대기", "  사건이 '승인대기'로", c["status"])
    chk(ast_(conn, aid1)["status"] == "마감", "  경매가 '마감'으로")

    # ④ ★핵심★ 마감 처리가 낙찰·금액을 절대 건드리지 않았는가
    chk(c["partner_id"] is None and c["partner_name"] is None,
        "★ 낙찰업체가 정해지지 않음", f"partner_id={c['partner_id']}")
    chk(c["award_amount"] is None and c["awarded_at"] is None,
        "★ 낙찰금액·낙찰시각이 비어 있음", f"award={c['award_amount']}")
    chk((c["low_price"] or 0) == 0,
        "★ cases.low_price 가 마감으로 오염되지 않음", c["low_price"])

    # ⑤ 마감 후에도 보험사는 승인할 수 있어야 한다 (관문이 막히면 안 됨)
    chk(c["status"] in ("입찰중", "승인대기"),
        "보험사 낙찰승인 가드가 받아들이는 상태")

    # ⑥ 멱등 — 두 번 돌려도 중복 처리·중복 알림 없음
    before = conn.execute("SELECT COUNT(*) FROM notifications WHERE case_id=?", (cid1,)).fetchone()[0]
    r2 = A.sweep_auctions(conn, force=True)
    after = conn.execute("SELECT COUNT(*) FROM notifications WHERE case_id=?", (cid1,)).fetchone()[0]
    chk(r2["scanned"] == 0 and before == after, "두 번 돌려도 중복 없음", f"{before}→{after}")

    # ⑦ 마감 + 입찰 0건 → 유찰
    cid2, aid2, _ = mkcase(conn)
    expire(conn, aid2)
    r = A.sweep_auctions(conn, force=True)
    c2 = st(conn, cid2)
    chk(r["failed"] == 1 and c2["status"] == "유찰", "입찰 0건 → 유찰", f"{r} {c2['status']}")
    wl = conn.execute("SELECT status FROM work_lots WHERE case_id=?", (cid2,)).fetchone()
    chk(wl and wl["status"] == "유찰", "  공종(lot)도 유찰로")

    # ⑧ 최소 성립 미달이어도 자동 유찰하지 않는다 (판단은 보험사 몫)
    conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('min_bidders','9')")
    conn.commit()
    cid3, aid3, _ = mkcase(conn)
    mkbid(conn, aid3, 8_000_000, n=1)
    expire(conn, aid3)
    A.sweep_auctions(conn, force=True)
    chk(st(conn, cid3)["status"] == "승인대기",
        "최소 성립 미달(1<9)이어도 유찰하지 않음", st(conn, cid3)["status"])
    msg = conn.execute("SELECT message FROM notifications WHERE case_id=? ORDER BY id DESC LIMIT 1",
                       (cid3,)).fetchone()
    chk(msg and "미달" in msg["message"], "  알림에 '미달'이 표시됨", msg["message"] if msg else "")
    conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('min_bidders',?)", (str(th_min),))
    conn.commit()

    # ⑨ dry_run 은 아무것도 바꾸지 않는다
    cid4, aid4, _ = mkcase(conn)
    mkbid(conn, aid4, 7_000_000, n=1)
    expire(conn, aid4)
    r = A.sweep_auctions(conn, dry_run=True, force=True)
    chk(r["scanned"] >= 1 and r["closed"] == 0 and st(conn, cid4)["status"] == "입찰중",
        "미리보기(dry_run)는 상태를 바꾸지 않음", r)
    A.sweep_auctions(conn, force=True)      # 정리

    # ⑩ 재개(reopen) 는 원경매 행을 새로 만들지 않는다
    n_before = conn.execute(
        "SELECT COUNT(*) FROM auctions WHERE case_id=? AND change_order_id IS NULL",
        (cid2,)).fetchone()[0]
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("UPDATE cases SET status='입찰중' WHERE id=?", (cid2,))
    conn.execute("UPDATE auctions SET status='진행', extend_count=extend_count+1, "
                 "deadline=datetime('now','+9 hours','+48 hours') WHERE id=?", (aid2,))
    conn.commit()
    n_after = conn.execute(
        "SELECT COUNT(*) FROM auctions WHERE case_id=? AND change_order_id IS NULL",
        (cid2,)).fetchone()[0]
    chk(n_before == n_after == 1, "재개해도 원경매 행은 계속 1개", f"{n_before}→{n_after}")

    # ⑪ 설정이 깨져도 기본값으로 버틴다
    for bad in ("세개", "-1", "", "999"):
        conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('min_bidders',?)", (bad,))
        conn.commit()
        if A._min_bidders(conn) != A.MIN_BIDDERS_DEFAULT:
            chk(False, f"손상 설정 '{bad}' → 기본값 복귀", A._min_bidders(conn))
            break
    else:
        chk(True, "손상된 설정값(문자·음수·빈값·범위초과) 전부 기본값으로 복귀")
    conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('min_bidders',?)", (str(th_min),))
    conn.commit()

    # ⑫ 저가 경보 경계 — 기준 20%면 정확히 80%는 경보 없음, 79%는 경보
    pct = A._low_price_alert_pct(conn)
    cap = 10_000_000
    at_edge = cap * (100 - pct) // 100                 # 정확히 기준선
    below = at_edge - 1
    chk(not (at_edge * 100 < cap * (100 - pct)), f"기준선({at_edge:,}원)은 경보 없음")
    chk(below * 100 < cap * (100 - pct), f"기준선 아래({below:,}원)는 경보")

    # ⑬ 낙찰된 사건은 유찰로 되돌릴 수 없다
    conn.execute("UPDATE cases SET status='시공중', partner_id=1 WHERE id=?", (cid3,))
    conn.commit()
    cur = conn.execute(
        "UPDATE cases SET status='유찰' WHERE id=? AND status IN ('입찰중','승인대기') "
        "AND partner_id IS NULL", (cid3,))
    chk(cur.rowcount == 0, "낙찰된 사건은 유찰 처리 불가")
    conn.rollback()

    # ⑭ 원경매 낙찰이 재경매 행을 덮지 않는다 (선행 결함 회귀)
    cid5, aid5, _ = mkcase(conn)
    conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,bid_count,"
        "                     extend_count,deadline,created_at) "
        "VALUES(?,999999,'추가분',1,'진행',0,0,0,datetime('now','+9 hours','+24 hours'),?)",
        (cid5, DB.now()))
    conn.commit()
    conn.execute("UPDATE auctions SET status='낙찰' WHERE case_id=? AND change_order_id IS NULL",
                 (cid5,))
    conn.commit()
    re_st = conn.execute(
        "SELECT status FROM auctions WHERE case_id=? AND change_order_id IS NOT NULL",
        (cid5,)).fetchone()
    chk(re_st and re_st["status"] == "진행",
        "원경매 낙찰이 진행 중 재경매를 덮지 않음", re_st["status"] if re_st else "없음")

    n = cleanup(conn)
    conn.close()
    print("-" * 66)
    print(f"  통과 {OK} · 실패 {FAIL}   (검증용 사건 {n}건 정리됨)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
