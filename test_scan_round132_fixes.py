# -*- coding: utf-8 -*-
"""스캔 132라운드 회귀 — app.py:_resync_partner_stats()/api_recount_partner_stats()
   의 win_rate 계산이 131라운드 수정 이후에도 여전히 100%를 넘을 수 있었다.

  분자(낙찰 사건 수)는 경로를 안 가리는데 분모(경매 입찰 사건 수)는 경매에
  입찰한 사건만 센다. dispatch.py:settle_agreement() 의 "1차합의"(현장
  실견적을 보험사가 그대로 승인 — 경매를 열지 않는다)로 낙찰된 사건은
  bids/auctions 에 아무 행도 안 남아 분모에 절대 못 들어가면서 분자에는
  들어간다 — 1차합의로만 여러 건을 낙찰한 업체는 승률이 한도 없이
  부풀려진다(실측 재현: 300%).

  수정: 분자도 award_route='1차합의' 인 사건은 제외해 분모(경매 입찰)와
  모집단을 맞춘다. award_route가 NULL(이 컬럼이 생기기 전의 옛 데이터)이면
  이 코드베이스의 기존 관례대로 경매로 간주한다(제외하지 않는다).

      python test_scan_round132_fixes.py
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
print("  스캔 132라운드 회귀 — win_rate 가 1차합의(무경매) 낙찰까지 분자에 섞여 100%를 넘던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — 두 함수 모두 같은 방식으로 고쳐졌는가")
# ------------------------------------------------------------
i_resync = APP_SRC.index("def _resync_partner_stats(conn, pid):")
i_recount_deco = APP_SRC.index('@app.post("/api/admin/recount-partner-stats")')
i_recount_end = APP_SRC.index("\n\n\n", i_recount_deco)
#  ⚠ [라운드131 교훈 재적용] 독스트링이 아니라 실제 SQL부터만 본다 —
#    독스트링이 옛 버그를 문장으로 설명하면 부정 검사가 그 문장에 걸린다.
resync_sql = APP_SRC[APP_SRC.index('conn.execute("""', i_resync):i_recount_deco]
recount_sql = APP_SRC[APP_SRC.index('conn.execute("""', i_recount_deco):i_recount_end]

for label, body in (("_resync_partner_stats", resync_sql), ("api_recount_partner_stats", recount_sql)):
    chk("COALESCE(c2.award_route,'경매')<>'1차합의'" in body,
        f"★★★ {label}: 분자(낙찰 사건)에서 1차합의 낙찰을 제외한다")

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

    # ── 시나리오A(실측 재현): 1차합의 낙찰 3건 + 경매는 1건 입찰·낙찰실패 ──
    #    분자가 안 고쳐졌으면 3건(1차합의 포함)/분모 1건 = 300%.
    conn = _mkdb()
    conn.execute("INSERT INTO partners(id,jobs_done,win_rate) VALUES (1,0,0)")
    for cid in (30, 31, 32):
        conn.execute(
            "INSERT INTO cases(id,partner_id,status,is_demo,award_amount,award_route) "
            "VALUES (?,1,'완료',0,500000,'1차합의')", (cid,))
    #  경쟁 경매 1건 — 이 업체는 입찰만 하고 낙찰은 다른 업체가 받는다
    conn.execute("INSERT INTO cases(id,partner_id,status,is_demo,award_amount,award_route) "
                 "VALUES (40,2,'완료',0,900000,'경매')")
    conn.execute("INSERT INTO auctions(id,case_id) VALUES (400,40)")
    conn.execute("INSERT INTO bids(auction_id,partner_id,is_demo) VALUES (400,1,0)")
    conn.commit()
    _resync(conn, 1)
    row = conn.execute("SELECT jobs_done, win_rate FROM partners WHERE id=1").fetchone()
    chk(row["win_rate"] == 0.0,
        "★★★ 시나리오A: 1차합의 3건은 낙찰(jobs_done)엔 들어가되 '경매 승률'에선 빠져야 한다"
        "(경매는 1건 입찰·낙찰실패이므로 정답은 0% — 고치기 전엔 300.0이 나왔다)", dict(row))
    chk(row["jobs_done"] == 3,
        "★ jobs_done(완료 사건 수)은 경로 불문 그대로 3건 — 이번 수정이 승률에만 영향줬다", dict(row))
    conn.close()

    # ── 시나리오B(회귀 없음): award_route가 NULL(옛 데이터)인 경매 낙찰은 여전히 승률에 들어간다 ──
    conn = _mkdb()
    conn.execute("INSERT INTO partners(id,jobs_done,win_rate) VALUES (2,0,0)")
    conn.execute("INSERT INTO cases(id,partner_id,status,is_demo,award_amount,award_route) "
                 "VALUES (50,2,'완료',0,700000,NULL)")   # award_route 컬럼 생기기 전의 옛 낙찰
    conn.execute("INSERT INTO auctions(id,case_id) VALUES (500,50)")
    conn.execute("INSERT INTO bids(auction_id,partner_id,is_demo) VALUES (500,2,0)")
    conn.commit()
    _resync(conn, 2)
    row2 = conn.execute("SELECT jobs_done, win_rate FROM partners WHERE id=2").fetchone()
    chk(row2["win_rate"] == 100.0,
        "★ 시나리오B(회귀없음): award_route가 NULL(옛 데이터)인 경매 낙찰은 그대로 승률에 잡힌다"
        "(1차합의만 콕 집어 빼야지, NULL까지 같이 빠지면 옛 업체 전원이 0%가 된다)", dict(row2))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드132 준비/실행(_resync_partner_stats 격리실행)", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
