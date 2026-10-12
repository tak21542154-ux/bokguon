# -*- coding: utf-8 -*-
"""스캔 131라운드 회귀 — app.py:_resync_partner_stats()/api_recount_partner_stats()
   의 win_rate 계산이 두 가지로 틀려 있었다(두 함수는 자기 주석이 "같이
   고쳐라"고 명시할 만큼 SQL이 그대로 복제돼 있다).

  [1] 분자는 "낙찰한 사건 수"인데 분모는 COUNT(DISTINCT b.auction_id)(입찰한
      경매 "행" 수)였다 — 유찰·거절로 같은 사건이 재경매(_open_reauction)에
      걸리고 같은 업체가 두 라운드 모두 입찰하면, 사건 1건 낙찰인데도
      분모가 2로 잡혀 승률이 반토막 난다.
  [2] 분모 쪽 bids 서브쿼리에 is_demo 제외가 없었다(분자 cases 쪽엔 있었다)
      — 실측: 업체#94(주식회사 무촌)의 저장된 값이 이미 데모입찰을 분모에
      섞은 채였다.

  수정: bids 를 auctions 에 조인해 **사건 단위**(a.case_id)로 세고, bids.is_demo
  도 함께 거른다.

      python test_scan_round131_fixes.py
"""
import io
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 131라운드 회귀 — win_rate 분모 단위불일치(재경매)·is_demo 미필터 2건")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — 두 함수(재계산 단건/전체) 모두 같은 방식으로 고쳐졌는가")
# ------------------------------------------------------------
i_resync = APP_SRC.index("def _resync_partner_stats(conn, pid):")
i_recount_deco = APP_SRC.index('@app.post("/api/admin/recount-partner-stats")')
i_recount_end = APP_SRC.index("\n\n\n", i_recount_deco)
#  ⚠ 함수 전체(독스트링 포함)가 아니라 실제 SQL부터만 본다 — 독스트링이
#    "예전엔 COUNT(DISTINCT b.auction_id) 였다" 처럼 옛 버그를 문장으로
#    설명하고 있어서, 함수 전체를 대상으로 "그 문자열이 없어야 한다"고
#    검사하면 코드가 아니라 그 설명글에 걸려 거짓 FAIL 이 난다(실측).
resync_body = APP_SRC[APP_SRC.index('conn.execute("""', i_resync):i_recount_deco]
recount_body = APP_SRC[APP_SRC.index('conn.execute("""', i_recount_deco):i_recount_end]

for label, body in (("_resync_partner_stats", resync_body), ("api_recount_partner_stats", recount_body)):
    chk("COUNT(DISTINCT a.case_id)" in body and "COUNT(DISTINCT b.auction_id)" not in body,
        f"★★★ {label}: 분모가 auction_id(행)가 아니라 case_id(사건)로 센다")
    chk("JOIN auctions a ON a.id = b.auction_id" in body,
        f"★★★ {label}: bids를 auctions에 조인해 case_id를 얻는다")
    chk("COALESCE(b.is_demo,0)=0" in body,
        f"★★★ {label}: bids 쪽도 is_demo=0 을 거른다(분자 cases 와 대칭)")

# ============================================================
print("\n[2] 실행 — 실제 _resync_partner_stats() 함수를 그대로 실행(exec 격리)")
# ------------------------------------------------------------
fn_src = APP_SRC[i_resync:i_recount_deco].rstrip()


def _mkdb():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE partners(id INTEGER PRIMARY KEY, jobs_done INTEGER, win_rate REAL);
        CREATE TABLE cases(id INTEGER PRIMARY KEY, partner_id INTEGER, status TEXT,
                            is_demo INTEGER, award_amount INTEGER, award_route TEXT,
                            low_price INTEGER);
        CREATE TABLE auctions(id INTEGER PRIMARY KEY, case_id INTEGER);
        CREATE TABLE bids(id INTEGER PRIMARY KEY, auction_id INTEGER, partner_id INTEGER, is_demo INTEGER, voided_at TEXT);
    """)
    return conn


try:
    ns = {}
    exec(compile(fn_src, "<resync_partner_stats>", "exec"), ns)  # noqa: S102 -- 우리 소스, 실제 함수를 그대로 실행
    _resync = ns["_resync_partner_stats"]

    # ── 시나리오A: 유찰로 재경매가 걸려 같은 업체가 두 라운드에 입찰(사건은 1건, 낙찰 1건) ──
    conn = _mkdb()
    conn.execute("INSERT INTO partners(id,jobs_done,win_rate) VALUES (1,0,0)")
    conn.execute("INSERT INTO cases(id,partner_id,status,is_demo,award_amount) VALUES (10,1,'완료',0,1000000)")
    conn.execute("INSERT INTO auctions(id,case_id) VALUES (100,10)")   # 원경매
    conn.execute("INSERT INTO auctions(id,case_id) VALUES (101,10)")   # 재경매(같은 사건)
    conn.execute("INSERT INTO bids(auction_id,partner_id,is_demo) VALUES (100,1,0)")
    conn.execute("INSERT INTO bids(auction_id,partner_id,is_demo) VALUES (101,1,0)")
    conn.commit()
    _resync(conn, 1)
    row = conn.execute("SELECT jobs_done, win_rate FROM partners WHERE id=1").fetchone()
    chk(row["win_rate"] == 100.0,
        "★★★ 시나리오A: 사건 1건 낙찰(재경매로 2라운드 입찰)이면 승률은 100%여야 한다"
        "(고치기 전엔 분모가 입찰행 수 2로 잡혀 50.0이 나왔다)", dict(row))
    conn.close()

    # ── 시나리오B: 실사건 1건(낙찰) + 데모사건 1건, 같은 업체가 둘 다 입찰 ──
    conn = _mkdb()
    conn.execute("INSERT INTO partners(id,jobs_done,win_rate) VALUES (2,0,0)")
    conn.execute("INSERT INTO cases(id,partner_id,status,is_demo,award_amount) VALUES (20,2,'완료',0,1000000)")
    conn.execute("INSERT INTO cases(id,partner_id,status,is_demo,award_amount) VALUES (21,2,'완료',1,1000000)")
    conn.execute("INSERT INTO auctions(id,case_id) VALUES (200,20)")   # 실경매
    conn.execute("INSERT INTO auctions(id,case_id) VALUES (201,21)")   # 데모경매
    conn.execute("INSERT INTO bids(auction_id,partner_id,is_demo) VALUES (200,2,0)")
    conn.execute("INSERT INTO bids(auction_id,partner_id,is_demo) VALUES (201,2,1)")
    conn.commit()
    _resync(conn, 2)
    row2 = conn.execute("SELECT jobs_done, win_rate FROM partners WHERE id=2").fetchone()
    chk(row2["win_rate"] == 100.0,
        "★★★ 시나리오B: 데모 사건·데모 입찰은 분모에서도 빠져야 승률 100%가 된다"
        "(고치기 전엔 데모입찰까지 분모에 섞여 50.0이 나왔다 — 실측: 업체#94와 같은 패턴)", dict(row2))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드131 준비/실행(_resync_partner_stats 격리실행)", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
