# -*- coding: utf-8 -*-
"""스캔 133라운드 회귀 — 낙찰(재낙찰) 확정 시 cases.partner_id 를 바꾸는 4곳
   중 2곳(api_insurer_award, api_co_close_full)이 award_route·awarded_at 을
   빠뜨려 두 갈래로 결함이 번졌다.

  [1] api_insurer_award(보험사 포털 직접 낙찰승인, 이 플랫폼에서 가장 흔할
      낙찰 경로)가 award_route 를 안 채워 영원히 NULL 로 남는다. 승률
      계산(131·132라운드, COALESCE(...,'경매')<>'1차합의')은 NULL 을 관대하게
      봐줘 괜찮지만, /api/est-bands 의 표본수 집계는 award_route='경매' 정확
      일치라 NULL 인 행을 통째로 놓친다(실측: 4건 중 1건만 잡힘).
  [2] api_co_close_full(전체재경매 낙찰확정)이 award_route·awarded_at 을 아예
      안 건드려, 사건이 원래 1차합의로 낙찰됐던 이력이 있으면 그 옛 값이 새
      낙찰업체에게 그대로 상속된다 — ①award_route='1차합의'가 남아 승률
      분자에서 빠짐(실제로 입찰해 이겼는데 승률 0%) ②awarded_at 이 옛 시각
      그대로라 방금 낙찰받은 새 업체가 sweep_report_overdue() 에 즉시
      '완료보고지연'으로 오판정돼 거짓 지연 알림을 받는다.

  수정: 형제 경로(api_case_award, dispatch.py:settle_agreement)처럼 이 확정
  순간의 진짜 경로('경매')·시각으로 새로 찍는다.

      python test_scan_round133_fixes.py
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
print("  스캔 133라운드 회귀 — 낙찰확정 4곳 중 2곳(보험사직접승인·전체재경매)의 award_route·awarded_at 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
#  ⚠ [라운드12 교훈] 고정 글자수 창은 함수가 길면 목표 SQL 이 창 밖으로
#    밀려 ValueError 가 난다 — 다음 top-level def 까지(구조 기준)로 자른다.
i_ia = APP_SRC.index("def api_insurer_award(")
i_ia_end = APP_SRC.index("\ndef ", i_ia + 1)
ia_body = APP_SRC[i_ia:i_ia_end]
ia_sql_i = ia_body.index("UPDATE cases SET status='시공중'")
ia_sql = ia_body[ia_sql_i:ia_body.index('"""', ia_sql_i)]
chk("award_route='경매'" in ia_sql,
    "★★★ api_insurer_award: 낙찰 확정 UPDATE 가 award_route='경매' 를 찍는다", ia_sql)

i_cf = APP_SRC.index('UPDATE cases SET partner_id=?, partner_name=?, award_amount=?, low_price=?, co_extra=0')
cf_sql = APP_SRC[i_cf:APP_SRC.index('"""', i_cf)]
chk("award_route='경매'" in cf_sql and "awarded_at=datetime('now','+9 hours')" in cf_sql,
    "★★★ api_co_close_full: 낙찰 확정 UPDATE 가 award_route·awarded_at 을 새로 찍는다", cf_sql)

# ============================================================
print("\n[2] 실행 — api_insurer_award 의 UPDATE 를 그대로 돌려 est-bands 표본이 잡히는가")
# ------------------------------------------------------------


def _mk_cases_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE cases(id INTEGER PRIMARY KEY, status TEXT, status_at TEXT,
                            partner_id INTEGER, partner_name TEXT, low_price INTEGER,
                            award_amount INTEGER, awarded_at TEXT, award_route TEXT,
                            co_extra INTEGER, is_demo INTEGER DEFAULT 0);
    """)
    return conn


try:
    conn = _mk_cases_db()
    conn.execute("INSERT INTO cases(id,status,partner_id,award_amount) VALUES (1,'입찰중',NULL,0)")
    conn.commit()
    conn.execute(ia_sql, (7, "업체7", 900000, 900000, "2026-08-27 10:00:00", 1))
    conn.commit()
    row = conn.execute("SELECT award_route, award_amount, partner_id FROM cases WHERE id=1").fetchone()
    chk(row["award_route"] == "경매",
        "★★★ 실행: 보험사 직접승인 UPDATE 실행 후 award_route가 실제로 '경매'로 찍힌다", dict(row))
    n_est = conn.execute(
        "SELECT COUNT(*) n FROM cases WHERE COALESCE(is_demo,0)=0 "
        " AND COALESCE(award_amount,0)>0 AND award_route='경매'").fetchone()["n"]
    chk(n_est == 1,
        "★★★ /api/est-bands 와 같은 정확일치 집계가 이제 이 낙찰을 표본으로 잡는다"
        "(고치기 전엔 award_route가 NULL이라 0으로 놓쳤다)", n_est)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드133 준비/실행(api_insurer_award SQL 재현)", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — api_co_close_full 의 UPDATE 이후, 승률·완료보고지연 판정이 실제로 바뀌는가")
# ------------------------------------------------------------
i_sro = APP_SRC.index("def sweep_report_overdue(conn):")
i_sro_end = APP_SRC.index("\ndef ", i_sro + 1)
sro_src = APP_SRC[i_sro:i_sro_end].rstrip()

i_resync = APP_SRC.index("def _resync_partner_stats(conn, pid):")
i_recount_deco = APP_SRC.index('@app.post("/api/admin/recount-partner-stats")')
resync_src = APP_SRC[i_resync:i_recount_deco].rstrip()

try:
    #  sweep_report_overdue 는 notify()/SWEEP_LIMIT/sqlite3 를 참조한다 —
    #  실행에 필요한 만큼만 가짜로 채운다(전역을 통째로 흉내내지 않는다).
    calls = []
    ns = {"sqlite3": sqlite3, "SWEEP_LIMIT": 500,
          "notify": lambda *a, **k: calls.append((a, k)),
          "rows": lambda cur: [dict(r) for r in cur.fetchall()],
          "DB": type("DB", (), {"log": staticmethod(lambda *a, **k: None), "now": staticmethod(lambda: "x")})()}

    def _setting_int(conn, key, default, lo, hi):
        return default
    ns["_setting_int"] = _setting_int
    exec(compile(sro_src, "<sweep_report_overdue>", "exec"), ns)     # noqa: S102 -- 우리 소스, 실제 함수 실행
    _sweep = ns["sweep_report_overdue"]

    ns2 = {}
    exec(compile(resync_src, "<resync>", "exec"), ns2)               # noqa: S102 -- 우리 소스, 실제 함수 실행
    _resync = ns2["_resync_partner_stats"]

    def _mk_full_db():
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE cases(id INTEGER PRIMARY KEY, case_no TEXT, status TEXT, status_at TEXT,
                                partner_id INTEGER, partner_name TEXT, low_price INTEGER,
                                award_amount INTEGER, awarded_at TEXT, award_route TEXT,
                                co_extra INTEGER, is_demo INTEGER DEFAULT 0, insurer_id INTEGER);
            CREATE TABLE partners(id INTEGER PRIMARY KEY, jobs_done INTEGER, win_rate REAL);
            CREATE TABLE auctions(id INTEGER PRIMARY KEY, case_id INTEGER);
            CREATE TABLE bids(id INTEGER PRIMARY KEY, auction_id INTEGER, partner_id INTEGER, is_demo INTEGER, voided_at TEXT);
        """)
        return conn

    #  사건 60: 원래 업체 A(파트너1)에게 1차합의로 낙찰됐던 옛 이력(award_route=
    #  '1차합의', awarded_at=이틀 전) — 전체재경매로 파트너9(B)가 새로 낙찰됐다고 가정.
    conn = _mk_full_db()
    conn.execute("INSERT INTO partners(id,jobs_done,win_rate) VALUES (9,0,0)")
    conn.execute(
        "INSERT INTO cases(id,case_no,status,partner_id,award_route,awarded_at,award_amount) "
        "VALUES (60,'CO-TEST','시공중',1,'1차합의',datetime('now','+9 hours','-48 hours'),500000)")
    conn.commit()
    #  api_co_close_full 의 실제 UPDATE 문 그대로 실행(파트너9가 새로 낙찰)
    conn.execute(cf_sql, (9, "업체9", 700000, 700000, 60))
    conn.commit()
    row2 = conn.execute("SELECT award_route, awarded_at, partner_id FROM cases WHERE id=60").fetchone()
    chk(row2["award_route"] == "경매",
        "★★★ 실행: 전체재경매 확정 후 옛 '1차합의' 값이 남지 않고 '경매'로 새로 찍힌다", dict(row2))

    #  경매 낙찰 표본을 채워(파트너9가 이 사건에 입찰) 승률을 실제로 계산해 본다
    conn.execute("INSERT INTO auctions(id,case_id) VALUES (600,60)")
    conn.execute("INSERT INTO bids(auction_id,partner_id,is_demo) VALUES (600,9,0)")
    conn.execute("UPDATE cases SET status='완료' WHERE id=60")
    conn.commit()
    _resync(conn, 9)
    prow = conn.execute("SELECT win_rate FROM partners WHERE id=9").fetchone()
    chk(prow["win_rate"] == 100.0,
        "★★★ 승률: 유일하게 입찰해서 이긴 사건인데 옛 '1차합의' 값 때문에 0%로 계산되던 것이 100%로 바로잡힌다",
        dict(prow))

    #  완료보고지연 오판정 확인 — 방금(수 초 전) 낙찰됐으니 지연이면 안 된다
    conn.execute("UPDATE cases SET status='시공중' WHERE id=60")  # 재확인을 위해 되돌림
    conn.commit()
    _sweep(conn)
    row3 = conn.execute("SELECT status FROM cases WHERE id=60").fetchone()
    chk(row3["status"] == "시공중",
        "★★★ 완료보고지연: 방금 낙찰받은 업체가 옛 낙찰시각 때문에 즉시 지연 오판정되지 않는다"
        "(고치기 전엔 48시간 전 시각이 그대로 남아 즉시 '완료보고지연'으로 바뀌고 거짓 알림이 갔다)",
        dict(row3))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드133 준비/실행(api_co_close_full → 승률·완료보고지연)", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
