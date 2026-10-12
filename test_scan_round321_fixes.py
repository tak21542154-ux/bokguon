# -*- coding: utf-8 -*-
"""스캔 321라운드 회귀 — db.py 함수 단위 라운드태그 커버리지 대조로 찾은 결함 2건,
   이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견(db.py 최상위 함수 16개 중
   태그 없던 10개를 전수 확인 — get_db/now/sql_now/hash_pw/verify_pw/
   is_legacy_hash/log/init_db 등은 클린, 나머지 둘은 실결함).

   ① [심각] _backfill_track_token_hash() 의 행별 UPDATE 에 예외처리가 없어
      형제 두 함수(_backfill_sku_keys·_backfill_child_is_demo, 둘 다
      sqlite3.OperationalError 를 잡음)와 다르다. deploy/DEPLOY.md 의 실제
      배포절차는 서비스 재시작 **전에** manage.py migrate 를 먼저 돌리므로,
      살아있는 서비스가 쓰기 잠금을 쥔 순간과 겹치면 "database is locked"가
      그대로 새어나가 migrate()→init_db()→app.py 모듈최상단의 무방비
      DB.init_db() 까지 뚫려 워커 기동이 죽을 수 있었다 — 형제와 같은
      try/except 패턴으로 통일(이 함수는 이미 멱등이라 실패 행은 다음
      migrate() 실행이 마저 채운다).
   ② [경미/설계상 잠재위험] sql_now() 가 offset 을 이스케이프 없이 SQL
      문자열에 그대로 이어붙인다 — 현재 호출부 2곳(app.py)은 안전한 값만
      넘겨 안 뚫리지만, 헬퍼 자체가 이를 강제하지 않았다. docstring 이
      이미 보여주는 형식만 허용하는 화이트리스트 검증을 추가.
"""
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_scratch = tempfile.mkdtemp(prefix="bokguon_r321_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_scratch, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SQLITE_BUSY_MS"] = "200"  # 실제 락 재현을 빠르게(기본 8000ms 대신 200ms)

import db as DB  # noqa: E402

PASS = FAIL = 0
FAILED = []


def chk(cond, msg, detail=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {msg}")
    else:
        FAIL += 1
        FAILED.append(msg)
        print(f"  [FAIL] {msg}" + (f"   {detail}" if detail else ""))


print("=" * 74)
print("  스캔 321라운드 회귀 — db.py 무방비 백필 UPDATE + sql_now() 검증누락")
print("=" * 74)

DB.init_db(seed_demo=False)

print("\n[1] 준비 — 진행조회 토큰은 있지만 해시는 없는 사건 2건 생성")
conn = DB.get_db()
conn.execute("BEGIN IMMEDIATE")
now = DB.now()
case_ids = []
for tok in ("tok-aaa111", "tok-bbb222"):
    cur = conn.execute(
        "INSERT INTO cases(case_no,insurer,category,region,address,status,is_demo,"
        "                  track_token,track_token_hash,created_at,status_at)"
        " VALUES(?,?,?,?,?,?,0,?,NULL,?,?)",
        (f"321-{tok}", "테스트보험", "유리·샷시·자동문", "서울", "서울시", "정산대기", tok, now, now))
    case_ids.append(cur.lastrowid)
conn.commit()

print("\n[2] 실행 — 다른 커넥션이 진짜 쓰기잠금을 쥔 상태에서 백필을 돌린다(실제 SQLite 락)")
locker = DB.get_db()
locker.execute("BEGIN IMMEDIATE")
locker.execute("UPDATE cases SET status=status WHERE id=?", (case_ids[0],))  # 실제로 쓰기 잠금을 쥐게 만든다
try:
    try:
        DB._backfill_track_token_hash(conn, verbose=True)
        raised = False
    except Exception as ex:
        raised = ex
    chk(raised is False,
        "★★★★★ 다른 커넥션이 쓰기잠금을 쥔 상태에서도 예외 없이 조용히 넘어간다"
        "(고치기 전엔 sqlite3.OperationalError('database is locked')가 그대로 전파됐다)",
        raised)
    still_null = conn.execute(
        "SELECT COUNT(*) n FROM cases WHERE track_token LIKE 'tok-%' AND track_token_hash IS NULL"
    ).fetchone()["n"]
    chk(still_null == 2,
        "  잠금 때문에 이번엔 실제로 2건 다 아직 안 채워졌다(조용히 건너뛴 것이지 몰래 성공한 게 아님)",
        still_null)
finally:
    locker.rollback()  # 잠금 해제

print("\n[3] 실행 — 잠금이 풀린 뒤 재실행하면(멱등) 남은 행이 실제로 채워진다")
DB._backfill_track_token_hash(conn, verbose=True)
rows = conn.execute(
    "SELECT track_token, track_token_hash FROM cases WHERE track_token LIKE 'tok-%'").fetchall()
import hashlib
chk(len(rows) == 2 and all(r["track_token_hash"] == hashlib.sha256(r["track_token"].encode()).hexdigest()
                            for r in rows),
    "★★★★ 잠금 해제 후 재실행하면 두 건 다 정확한 해시로 채워진다(재시도로 완전히 회복)")

print("\n[4] 실행 — migrate() 전체 경로도 같은 잠금 조건에서 안 죽는다")
conn.execute(
    "UPDATE cases SET track_token_hash=NULL WHERE track_token LIKE 'tok-%'")
conn.commit()
locker2 = DB.get_db()
locker2.execute("BEGIN IMMEDIATE")
locker2.execute("UPDATE cases SET status=status WHERE id=?", (case_ids[0],))
try:
    try:
        DB.migrate(conn, verbose=False)
        raised2 = False
    except Exception as ex:
        raised2 = ex
    chk(raised2 is False,
        "★★★★★ migrate() 전체를 잠금 상태에서 실행해도 예외가 밖으로 안 새어나온다"
        "(실제 배포절차 — 서비스 살아있는 채로 migrate 실행 — 를 그대로 재현)", raised2)
finally:
    locker2.rollback()

print("\n[5] 실행 — sql_now() 가 정상 형식은 통과시키고, SQL 인젝션 시도는 막는다")
for good in ("-10 minutes", "-30 seconds", "5 hours", "1 day", ""):
    try:
        DB.sql_now(good)
        ok = True
    except ValueError:
        ok = False
    chk(ok, f"  정상 형식 통과: {good!r}")
for bad in ("'); DROP TABLE cases; --", "10 minutes' OR '1'='1", "10; DELETE FROM cases"):
    try:
        DB.sql_now(bad)
        blocked = False
    except ValueError:
        blocked = True
    chk(blocked, f"★★★★★ 비정상 형식(SQL 인젝션 시도)을 막는다: {bad!r}"
        "(고치기 전엔 검증 없이 그대로 SQL 문자열에 이어붙였다)")

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
