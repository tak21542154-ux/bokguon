# -*- coding: utf-8 -*-
"""스캔 45라운드 회귀 — 핫패스 인덱스 2개 누락(login_attempts·notifications).

  조사 에이전트가 실측(5만·4만행)으로 증명한 결함:
  ① `_recent_fails()`(모든 로그인 시도마다 호출)의 WHERE 는 username·ip·
     created_at 세 조건인데, 기존 인덱스는 (username, created_at)까지만 —
     정확히 이 표가 막아야 하는 상황(같은 아이디를 여러 IP로 두드리는 분산
     공격)에서 ip 필터가 인덱스 밖에서 걸러진다. 271배 실측.
  ② 콘솔 벨(api_admin_notifications, 주기적으로 폴링됨)의 'ORDER BY id DESC
     LIMIT 60' 을 기존 인덱스(audience_type, read_at)가 못 태워 매칭 전체를
     모아 정렬한다. 582배 실측.

  이 회귀는 EXPLAIN QUERY PLAN 으로 **그 특정 인덱스가 실제로 선택되는지**를
  결정적으로(타이밍이 아니라) 확인한다.

      python test_scan_round45_fixes.py
"""
import io
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


DB_SRC = read("db.py")

print("═" * 72)
print("  스캔 45라운드 회귀 — 인덱스 2개(login_attempts·notifications)")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 배선이 실제로 있는가")
# ──────────────────────────────────────────────────────────────
chk('"CREATE INDEX IF NOT EXISTS idx_login_lockout "' in DB_SRC,
    "★ idx_login_lockout 정의가 있다")
chk("ON login_attempts(username, ip, created_at)" in DB_SRC,
    "★★ 세 컬럼(username·ip·created_at) 순서로 만들어졌다")
chk('"CREATE INDEX IF NOT EXISTS idx_notif_admin_feed "' in DB_SRC,
    "★ idx_notif_admin_feed 정의가 있다")
chk("ON notifications(audience_type, id)" in DB_SRC,
    "★★ (audience_type, id) 순서로 만들어졌다(id 로 LIMIT 정렬 태우기)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 새 DB 생성 시 실제로 인덱스가 만들어지는가")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="idx45_")
db_path = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_DB_PATH"] = db_path
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    names = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    chk("idx_login_lockout" in names, "★★★ idx_login_lockout 이 실제 DB에 생성됐다")
    chk("idx_notif_admin_feed" in names, "★★★ idx_notif_admin_feed 가 실제 DB에 생성됐다")

    # ── ① login_attempts — 분산 공격 모양(같은 아이디, 서로 다른 IP 다수)으로 채운다
    print("\n[3] 실행 — 실제 핫패스 쿼리가 새 인덱스를 쓰는가(EXPLAIN QUERY PLAN)")
    conn.execute("BEGIN")
    rows_ = []
    for i in range(3000):
        rows_.append(("victim_admin", f"203.0.113.{i % 250}.{i // 250}"[:15], 0,
                       "2026-08-24 00:00:00"))
    conn.executemany(
        "INSERT INTO login_attempts(username, ip, success, created_at) VALUES(?,?,?,?)",
        rows_)
    conn.commit()
    conn.execute("ANALYZE")

    plan1 = conn.execute(
        """EXPLAIN QUERY PLAN
           SELECT COUNT(*) n FROM login_attempts
           WHERE username=? AND ip=? AND success=0
             AND created_at > datetime('now','+9 hours', ?)""",
        ("victim_admin", "203.0.113.5.0", "-10 minutes")).fetchall()
    plan1_txt = " ".join(r["detail"] for r in plan1)
    chk("idx_login_lockout" in plan1_txt,
        "★★★ _recent_fails() 실쿼리가 idx_login_lockout 을 쓴다", plan1_txt)

    # ── ② notifications — 실제 분포를 흉내낸다(admin/all 이 전부가 아니어야
    #    WHERE 가 실제로 선택적이다 — 전부 매칭이면 풀스캔이 오히려 최적이라
    #    이 검사가 무의미해진다. 조사 에이전트 실측치(약 65% admin/all)에 맞춘다).
    AUD_MIX = (["admin"] * 4 + ["all"] * 2 + ["insurer"] * 3 + ["partner"] * 3)
    rows2 = []
    for i in range(30000):
        aud = AUD_MIX[i % len(AUD_MIX)]
        rows2.append((aud, f"검증{i}", "2026-08-24 00:00:00"))
    conn.executemany(
        "INSERT INTO notifications(audience_type, message, created_at) VALUES(?,?,?)",
        rows2)
    conn.commit()
    conn.execute("ANALYZE")

    plan2 = conn.execute(
        """EXPLAIN QUERY PLAN
           SELECT id, ntype, message, url, case_id, read_at, created_at
             FROM notifications
            WHERE (audience_type='admin' OR audience_type='all') AND COALESCE(is_demo,0)=0
            ORDER BY id DESC LIMIT 60""").fetchall()
    plan2_txt = " ".join(r["detail"] for r in plan2)
    chk("idx_notif_admin_feed" in plan2_txt and "SCAN notifications" not in plan2_txt,
        "★★★ api_admin_notifications() 실쿼리가 SCAN 대신 idx_notif_admin_feed 로 SEARCH 한다",
        plan2_txt)
    #  ⚠ OR 두 분기(admin/all)를 id 역순으로 합치는 마지막 정렬(B-TREE)은 이 인덱스로도
    #    남을 수 있다 — 이 인덱스가 없애는 건 그 앞의 '전체 스캔'이지 병합정렬 자체가
    #    아니다. 그래서 여기선 정렬 유무를 단정하지 않는다(과잉주장 금지).

    # ── 실측 타이밍 — 구조(SEARCH) 뿐 아니라 실제로 빨라졌는지도 잰다
    import time
    t0 = time.perf_counter()
    for _ in range(50):
        conn.execute(
            """SELECT id, ntype, message, url, case_id, read_at, created_at
                 FROM notifications
                WHERE (audience_type='admin' OR audience_type='all') AND COALESCE(is_demo,0)=0
                ORDER BY id DESC LIMIT 60""").fetchall()
    with_idx_ms = (time.perf_counter() - t0) * 1000 / 50
    conn.execute("DROP INDEX idx_notif_admin_feed")
    conn.execute("ANALYZE")
    t0 = time.perf_counter()
    for _ in range(50):
        conn.execute(
            """SELECT id, ntype, message, url, case_id, read_at, created_at
                 FROM notifications
                WHERE (audience_type='admin' OR audience_type='all') AND COALESCE(is_demo,0)=0
                ORDER BY id DESC LIMIT 60""").fetchall()
    without_idx_ms = (time.perf_counter() - t0) * 1000 / 50
    print(f"       콘솔 벨 쿼리(3만행): 인덱스 있음 {with_idx_ms:.2f}ms · 없음 {without_idx_ms:.2f}ms")
    chk(with_idx_ms < without_idx_ms,
        "★★★ 실제로 인덱스가 있을 때가 더 빠르다", f"{with_idx_ms:.2f}ms vs {without_idx_ms:.2f}ms")
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 인덱스 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
