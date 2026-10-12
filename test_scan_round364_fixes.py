# -*- coding: utf-8 -*-
"""스캔 364라운드 회귀 — app.py:_resync_partner_stats()/api_recount_partner_stats()
   의 win_rate 분모(경매 입찰 사건 수)가 무효화된 입찰(voided_at IS NOT NULL)을
   걸러내지 않던 결함[중간, 데이터정합성 — 승률 캐시가 실측보다 낮게 나옴].

  배경: 전체재경매 유찰(app.py:10153)·추가분 유찰(19342)·낙찰취소(19483~87)·
  유찰확정(19633) 네 자리 모두 그 순간 "더는 유효하지 않은" 입찰을 지우지
  않고 voided_at 만 찍어 남긴다(입찰 이력은 소명 자료라 지우지 않는다 — 위
  낙찰취소 블록 자신의 주석). 그래서 이후 화면·집계가 "지금 유효한 입찰"을
  가릴 때는 어디나 `voided_at IS NULL` 을 붙인다 — app.py 안에 이 조건이
  33곳 있다(4141·4193·4300·9806 등). 그런데 win_rate 의 분모(경매에 입찰한
  사건 수)를 세는 이 두 함수의 SQL만 그 조건이 없어, 한번 무효화된 입찰의
  경매까지 "경쟁한 경매"로 계속 세었다 — 실제로 이긴 적도 진 적도 없는
  (재공고로 사라진) 경매가 분모를 부풀려 승률이 실제보다 낮게 나온다.

  ⚠ 조사 에이전트의 최초 보고는 이 결함을 app.py:10530 의 하자율 점수식
    (s_def = 1 - dcnt/jobs)과 엮어 "낙찰 순위에 영향"이라 했으나, 직접 코드를
    읽어 확인한 결과 그 식의 분모는 win_rate 가 아니라 jobs_done(cases 테이블
    만으로 계산 — bids/auctions 를 전혀 참조하지 않는다)이라 이번 결함과는
    무관했다. 게다가 win_rate 자체는 app.py·static/*.js·templates/* 어디서도
    읽히지 않는다(grep 전수 확인) — 즉 이 결함의 실제 영향범위는 "낙찰 순위"가
    아니라 partners.win_rate 라는 캐시값 자체의 정확도에 한정된다(메커니즘은
    진짜였으나 파급범위는 과장됐던 사례 — 그래도 캐시값이 틀린 채로 저장되는
    것 자체는 독립적으로 고칠 가치가 있다).

  고침: 두 함수의 win_rate 분모 서브쿼리에 `AND b.voided_at IS NULL` 을
  추가해, 이 코드베이스가 이미 33곳에서 쓰는 "지금 유효한 입찰만" 관례와
  맞춘다. 131·132라운드가 세운 "한쪽 공식을 고치면 다른 쪽도 같이 고쳐라"
  원칙대로 두 함수를 동일하게 수정했다.

      python test_scan_round364_fixes.py
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
print("  스캔 364라운드 회귀 — win_rate 분모가 무효화된 입찰을 계속 세던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — 두 함수 모두 같은 방식으로 고쳐졌는가")
# ------------------------------------------------------------
i_resync = APP_SRC.index("def _resync_partner_stats(conn, pid):")
i_recount_deco = APP_SRC.index('@app.post("/api/admin/recount-partner-stats")')
i_recount_end = APP_SRC.index("\n\n\n", i_recount_deco)
resync_sql = APP_SRC[APP_SRC.index('conn.execute("""', i_resync):i_recount_deco]
recount_sql = APP_SRC[APP_SRC.index('conn.execute("""', i_recount_deco):i_recount_end]

for label, body in (("_resync_partner_stats", resync_sql), ("api_recount_partner_stats", recount_sql)):
    chk("FROM bids b JOIN auctions a ON a.id = b.auction_id" in body
        and "b.voided_at IS NULL" in body,
        f"★★★★★ {label}: win_rate 분모가 무효화된 입찰(voided_at)을 제외한다")

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
        CREATE TABLE bids(id INTEGER PRIMARY KEY, auction_id INTEGER, partner_id INTEGER,
                           is_demo INTEGER, voided_at TEXT);
    """)
    return conn


try:
    ns = {}
    exec(compile(fn_src, "<resync_partner_stats>", "exec"), ns)  # noqa: S102 -- 우리 소스, 실제 함수를 그대로 실행
    _resync = ns["_resync_partner_stats"]

    #  실측 재현 시나리오 — 업체1: 승(경매100/사건10) 1건 + 패(경매200/사건20) 1건
    #  + 재공고로 무효화된 옛 입찰(경매300/사건30) 1건. 정답은 1승/2유효경매=50%
    #  (경매300은 이기지도 지지도 않은 채 사라졌으니 분모에서 아예 빠져야 한다).
    conn = _mkdb()
    conn.execute("INSERT INTO partners(id,jobs_done,win_rate) VALUES (1,0,0)")

    conn.execute("INSERT INTO cases(id,partner_id,status,is_demo,award_amount,award_route) "
                 "VALUES (10,1,'완료',0,900000,'경매')")
    conn.execute("INSERT INTO auctions(id,case_id) VALUES (100,10)")
    conn.execute("INSERT INTO bids(auction_id,partner_id,is_demo,voided_at) "
                 "VALUES (100,1,0,NULL)")

    conn.execute("INSERT INTO cases(id,partner_id,status,is_demo,award_amount,award_route) "
                 "VALUES (20,2,'완료',0,700000,'경매')")   # 사건20은 업체2가 낙찰
    conn.execute("INSERT INTO auctions(id,case_id) VALUES (200,20)")
    conn.execute("INSERT INTO bids(auction_id,partner_id,is_demo,voided_at) "
                 "VALUES (200,1,0,NULL)")                  # 업체1은 입찰만 하고 패

    conn.execute("INSERT INTO cases(id,partner_id,status,is_demo,award_amount,award_route) "
                 "VALUES (30,NULL,'입찰중',0,NULL,NULL)")   # 재공고돼 아직 미낙찰
    conn.execute("INSERT INTO auctions(id,case_id) VALUES (300,30)")
    conn.execute("INSERT INTO bids(auction_id,partner_id,is_demo,voided_at) "
                 "VALUES (300,1,0,'2026-01-01 00:00:00')")  # 전체재경매로 무효화된 옛 입찰

    conn.commit()
    _resync(conn, 1)
    row = conn.execute("SELECT jobs_done, win_rate FROM partners WHERE id=1").fetchone()
    chk(row["win_rate"] == 50.0,
        "★★★★★ 무효화된 입찰(경매300)은 분모에서 빠져 1승/2유효경매=50%가 나와야 한다"
        "(고치기 전엔 1승/3경매=33.3으로, 실제보다 승률이 낮게 나왔다)", dict(row))
    conn.close()

    #  회귀 없음 확인 — 무효화된 입찰이 아예 없는 업체는 종전과 동일하게 계산된다
    conn = _mkdb()
    conn.execute("INSERT INTO partners(id,jobs_done,win_rate) VALUES (2,0,0)")
    conn.execute("INSERT INTO cases(id,partner_id,status,is_demo,award_amount,award_route) "
                 "VALUES (11,2,'완료',0,900000,'경매')")
    conn.execute("INSERT INTO auctions(id,case_id) VALUES (101,11)")
    conn.execute("INSERT INTO bids(auction_id,partner_id,is_demo,voided_at) VALUES (101,2,0,NULL)")
    conn.commit()
    _resync(conn, 2)
    row2 = conn.execute("SELECT jobs_done, win_rate FROM partners WHERE id=2").fetchone()
    chk(row2["win_rate"] == 100.0,
        "★ 회귀없음 — 무효화된 입찰이 없으면 종전과 동일하게 1승/1경매=100%", dict(row2))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행(_resync_partner_stats 격리실행)", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 회귀 확인 — 131·132·139라운드의 기존 win_rate 테스트가 여전히 통과하는가")
# ------------------------------------------------------------
import subprocess  # noqa: E402
for rn in (131, 132, 139):
    fn = f"test_scan_round{rn}_fixes.py"
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, fn)],
                            capture_output=True, text=True, encoding="utf-8",
                            cwd=HERE, timeout=60)
        chk(r.returncode == 0, f"  {fn} 단독 재실행 통과",
            (r.returncode, (r.stdout or "")[-300:], (r.stderr or "")[-200:]))
    except Exception as e:                                          # noqa: BLE001
        chk(False, f"  {fn} 재실행 준비", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
