# -*- coding: utf-8 -*-
"""2차 경매 회귀 검사 — 가견적이 하한.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

실제 흐름:
  보상담당자가 사진 없이 가견적 300만으로 경매를 요청한다.
  → 사진이 없으니 1차 출동 업체가 현장에 가서 본다. 실제로는 500만이다.
  → 보험사가 그 500만에 부동의한다. 이제 공사에 필요한 사진은 다 확보됐다.
  → **2차 경매**가 열린다.

  1차와 2차는 방향이 반대다.
    · 1차 — 가견적이 **상한**. 인하만 가능(역경매).
    · 2차 — 가견적이 **하한**. 그 위에서 경쟁하고, 상한은 없다.
            하한을 두는 이유: 못 할 값으로 따내고 현장에서 포기하는 것을 막는다.
            낙찰은 그대로 **최저가** — 하한 위에서 가장 낮게 쓴 곳이 이긴다.

  절감 기준선도 2차만 다르다. 가견적이 하한이면 '가견적 − 낙찰가'가 늘 음수라,
  그 사건은 **표준단가 개산 상단**(engine_high)을 기준으로 센다.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("BOKGUON_LOG_FILE",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "logs", "test.log"))
import db as DB
import app as A
import dispatch as DP

OK = FAIL = 0
MARK = "R2TEST"


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


def cleanup(conn):
    for cid in [r[0] for r in conn.execute(
            "SELECT id FROM cases WHERE case_no LIKE ?", (f"{MARK}%",))]:
        for t in ("field_agreements", "photos", "auctions", "notifications", "work_lots"):
            try:
                conn.execute(f"DELETE FROM {t} WHERE case_id=?", (cid,))
            except Exception:
                pass
        conn.execute("DELETE FROM cases WHERE id=?", (cid,))
    conn.execute("DELETE FROM partners WHERE name LIKE ?", (f"{MARK}%",))
    conn.commit()


def main():
    conn = DB.get_db()
    cleanup(conn)
    print("=" * 70)
    print("  2차 경매 — 가견적이 하한")
    print("=" * 70)

    iid = conn.execute("SELECT id FROM insurers LIMIT 1").fetchone()[0]
    conn.execute("INSERT INTO partners(name, partner_type, major, region, status) "
                 "VALUES(?,'시행사','가드레일·방호울타리','서울','활성')", (f"{MARK}업체",))
    pid = conn.execute("SELECT last_insert_rowid() r").fetchone()[0]

    conn.execute("INSERT INTO cases(case_no, insurer_id, category, region, status, est_price) "
                 "VALUES(?,?,?,?,'입찰중',3000000)",
                 (f"{MARK}-C1", iid, "가드레일·방호울타리", "서울"))
    cid = conn.execute("SELECT last_insert_rowid() r").fetchone()[0]
    conn.commit()

    # ── 1차: 가견적이 상한, 하한 없음 ──
    print("\n[1차] 가견적이 상한 (인하만)")
    c = one(conn.execute("SELECT * FROM cases WHERE id=?", (cid,)))
    fl, cap, ref, rnd = A.bid_cap_of(conn, c)
    chk(rnd == 1 and cap == 3000000, "1차 — 상한 300만", f"회차{rnd} 상한{cap}")
    chk(fl == 0, "1차 — 하한 없음", f"하한{fl}")

    # ── 출동 실견적 500만 · 보험사 부동의 → 2차 ──
    print("\n[2차] 출동 실견적 500만 · 보험사 부동의")
    conn.execute(
        "INSERT INTO field_agreements(case_id, partner_id, partner_name, status, "
        "  field_amount, engine_low, engine_high, created_at) "
        "VALUES(?,?,?,?,5000000,4200000,5400000,datetime('now','+9 hours'))",
        (cid, pid, f"{MARK}업체", DP.AG_BROKEN))
    conn.commit()

    c = one(conn.execute("SELECT * FROM cases WHERE id=?", (cid,)))
    fl, cap, ref, rnd = A.bid_cap_of(conn, c)
    chk(rnd == 2, "2차로 판정된다(결렬된 현장합의가 있으므로)", f"회차{rnd}")
    chk(fl == 3000000, "★ 하한 = 보상담당자 가견적 300만", f"하한{fl}")
    chk(cap == 0, "★ 상한은 없다", f"상한{cap}")
    chk(ref == 5000000, "참고선 = 출동 업체 실견적 500만", f"{ref}")
    chk(c["est_price"] == 3000000,
        "★ 2차를 열어도 가견적을 덮어쓰지 않는다(하한이 사라지면 안 된다)",
        f"{c['est_price']}")

    # ── 핵심: 하한 위에서만 ──
    print("\n[핵심] 하한 위에서만 입찰")
    chk(4000000 >= fl, "★★ 400만은 하한을 통과한다")
    chk(cap == 0 or 4000000 <= cap, "★★ 400만은 상한에 막히지 않는다")
    chk(2500000 < fl, "★★ 250만은 하한에 막힌다(못 할 값으로 따내기 방지)")
    chk(cap == 0, "실견적보다 높아도 서버는 막지 않는다(승인은 보험사 몫)")

    # ── 절감 기준선 — 2차는 표준단가 개산 ──
    print("\n[절감] 기준선이 표준단가 개산으로 바뀌는가")
    conn.execute("UPDATE cases SET status='완료', award_amount=4000000 WHERE id=?", (cid,))
    conn.commit()
    base = conn.execute(
        f"SELECT {A.SAVE_BASE_SQL} b FROM cases WHERE id=?", (cid,)).fetchone()["b"]
    chk(base == 5400000, "★ 2차 사건의 절감 기준선 = 개산 상단 540만", f"{base}")
    chk(base - 4000000 == 1400000,
        "★ 절감이 양수로 나온다(140만) — 가견적 기준이면 −100만이었다",
        f"{base - 4000000}")

    # ── 회귀: 1차 사건은 그대로 ──
    print("\n[회귀] 1차 사건은 종전 그대로")
    conn.execute("INSERT INTO cases(case_no, insurer_id, category, region, status, "
                 "  est_price, award_amount) VALUES(?,?,?,?,'완료',3000000,2400000)",
                 (f"{MARK}-C2", iid, "가드레일·방호울타리", "서울"))
    cid2 = conn.execute("SELECT last_insert_rowid() r").fetchone()[0]
    conn.commit()
    c2 = one(conn.execute("SELECT * FROM cases WHERE id=?", (cid2,)))
    fl2, cap2, _, rnd2 = A.bid_cap_of(conn, c2)
    chk(cap2 == 3000000 and fl2 == 0 and rnd2 == 1,
        "★ 결렬 이력이 없으면 여전히 가견적이 상한", f"상한{cap2} 하한{fl2}")
    base2 = conn.execute(
        f"SELECT {A.SAVE_BASE_SQL} b FROM cases WHERE id=?", (cid2,)).fetchone()["b"]
    chk(base2 == 3000000, "★ 1차 사건의 절감 기준선은 그대로 가견적", f"{base2}")

    # '합의'로 끝난 현장합의는 2차가 아니다
    conn.execute(
        "INSERT INTO field_agreements(case_id, partner_id, partner_name, status, "
        "  field_amount, engine_high, created_at) "
        "VALUES(?,?,?,?,9000000,9500000,datetime('now','+9 hours'))",
        (cid2, pid, f"{MARK}업체", DP.AG_DONE))
    conn.commit()
    c2 = one(conn.execute("SELECT * FROM cases WHERE id=?", (cid2,)))
    fl2b, cap2b, _, rnd2b = A.bid_cap_of(conn, c2)
    chk(cap2b == 3000000 and fl2b == 0 and rnd2b == 1,
        "★ '합의'로 끝난 건은 2차가 아니다", f"상한{cap2b} 회차{rnd2b}")
    base2b = conn.execute(
        f"SELECT {A.SAVE_BASE_SQL} b FROM cases WHERE id=?", (cid2,)).fetchone()["b"]
    chk(base2b == 3000000,
        "★ '합의' 건의 개산값이 절감 기준선을 오염시키지 않는다(결렬만 본다)", f"{base2b}")

    # ── 보험사 승인 화면이 마이너스 절감을 보여주지 않는가 ──
    #   여기가 뚫려 있으면 정상적인 2차 낙찰을 담당자가 전부 반려한다.
    print("\n[승인화면] 2차 낙찰이 '절감 마이너스'로 보이지 않는가")
    conn.execute("UPDATE cases SET status='승인대기', award_amount=NULL, low_price=4000000 "
                 " WHERE id=?", (cid,))
    conn.commit()
    c = one(conn.execute("SELECT * FROM cases WHERE id=?", (cid,)))
    fl, cap, ref, rnd = A.bid_cap_of(conn, c)
    eh = one(conn.execute(
        "SELECT engine_high FROM field_agreements WHERE case_id=? AND status=? "
        "  AND COALESCE(engine_high,0)>0 ORDER BY id DESC LIMIT 1", (cid, DP.AG_BROKEN)))
    base = int((eh or {}).get("engine_high") or 0) or ref
    saving = round((1 - 4000000 / base) * 100, 1)
    chk(rnd == 2 and base == 5400000, "승인 화면 기준선 = 개산 상단 540만", f"{base}")
    chk(saving > 0, "★★ 절감이 양수(+)로 보인다 — 가견적 기준이면 −33% 였다", f"{saving}%")
    old_way = round((1 - 4000000 / (c["est_price"] or 1)) * 100, 1)
    chk(old_way < 0, "(대조) 옛 방식이었다면 마이너스였다", f"{old_way}%")

    cleanup(conn)
    conn.close()
    print("-" * 70)
    print(f"  통과 {OK} · 실패 {FAIL}   (검증 데이터 정리됨)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
