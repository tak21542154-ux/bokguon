# -*- coding: utf-8 -*-
"""스캔 424라운드 회귀 — bids 테이블에 부분 UNIQUE 인덱스로 방어심화, 1건.

   정밀조사 Agent(각도2: 입찰 제출 동시성 TOCTOU)가 사진 경로탐색/IDOR(각도1)와
   입찰 동시성 둘 다 클린으로 확정했다 — api_partner_bid()·api_partner_
   reauction_bid()(app.py:4988·5204) 둘 다 "읽고-계산하고-쓰는" 구간 전체를
   BEGIN IMMEDIATE 로 감싸고, 그 안에서 "voided_at IS NULL 인 기존 입찰이
   있으면 UPDATE, 없으면 INSERT"(5077-5104·5282-5308) 로 파트너당 활성 입찰
   1건을 유지한다. 코드 추적으로는 안전하지만, bids 테이블 자체(db.py:324)에는
   이 불변식을 강제하는 UNIQUE 제약이 전혀 없어 — 동시성 안전성이 전적으로
   "이 두 호출부가 항상 BEGIN IMMEDIATE 규율을 지킨다"는 애플리케이션 계층의
   약속에만 의존하고 있었다(제안 항목, 결함은 아님 — 현재 두 호출부 다 규율을
   지키고, 실제 운영 DB(bokguon.db) 를 직접 조회해 (auction_id,partner_id)당
   voided_at IS NULL 인 중복 행이 0건임을 확인).

   고침(방어심화, 새 정책 없음): db.py 의 idx_cases_idem(부분 UNIQUE 인덱스)과
   같은 패턴으로 `CREATE UNIQUE INDEX idx_bids_active_partner ON
   bids(auction_id, partner_id) WHERE voided_at IS NULL` 추가 — 지금 두
   호출부의 동작은 전혀 안 바뀌고(이미 지키고 있는 불변식이라 정상 경로에서
   이 인덱스에 걸릴 일이 없음), 앞으로 새 입찰-쓰기 경로가 이 규율을 빠뜨려도
   DB 자체가 중복 활성입찰 삽입을 거부하는 마지막 안전망이 생긴다. db.py 의
   인덱스 생성 루프(1447-1450행)는 각 CREATE INDEX 문을 개별 try/except 로
   감싸 하나가 실패해도 서버 기동이 안 죽는 구조라 안전하게 추가 가능함을
   확인.

       python test_scan_round424_fixes.py
"""
import io
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


DB_SRC = read("db.py")

print("=" * 72)
print("  스캔 424라운드 회귀 — bids 부분 UNIQUE 인덱스(동시성 방어심화)")
print("=" * 72)

print("\n[1] 소스 확인")
chk("idx_bids_active_partner" in DB_SRC,
    "★★★★★ db.py 에 새 인덱스 idx_bids_active_partner 가 등록됐다")
chk("ON bids(auction_id, partner_id) WHERE voided_at IS NULL" in DB_SRC,
    "★★★★ 부분 UNIQUE 인덱스가 정확히 (auction_id,partner_id)+voided_at IS NULL 조건이다")

print("\n[2] 실행 — 스크래치 DB 에서 인덱스가 실제로 생성되고 UNIQUE 로 등록됐는가")
_tmpdir = tempfile.mkdtemp(prefix="round424_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A
    import sqlite3

    conn = DB.get_db()
    idx = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_bids_active_partner'"
    ).fetchone()
    chk(idx is not None, "★★★★★ 인덱스가 실제로 sqlite_master 에 생성돼 있다")
    chk(idx is not None and "UNIQUE" in idx["sql"].upper(),
        "  UNIQUE 인덱스로 생성됐다(회귀없음)", dict(idx) if idx else None)

    print("\n[3] 실행 — 직접 SQL로 중복 활성입찰 INSERT 시도 시 이제 DB가 거부하는가")
    conn.execute("INSERT INTO insurers(name,status) VALUES('R424보험사','활성')")
    iid = conn.execute("SELECT id FROM insurers WHERE name='R424보험사'").fetchone()["id"]
    conn.execute("INSERT INTO partners(name,login_id,password_hash,status,partner_type,"
                 "rating,jobs_done,region) VALUES('R424업체','r424p','x','활성','시행사',4.5,10,'서울')")
    pid = conn.execute("SELECT id FROM partners WHERE login_id='r424p'").fetchone()["id"]
    conn.execute("INSERT INTO cases(case_no,status,is_demo,insurer_id,region) "
                 "VALUES('R424-CASE','입찰중',0,?,'서울')", (iid,))
    cid = conn.execute("SELECT id FROM cases WHERE case_no='R424-CASE'").fetchone()["id"]
    #  ⚠ AUCTION_EXPIRED_SQL 은 datetime('now','+9 hours')(KST) 기준으로 비교한다 —
    #    deadline 도 같은 KST 기준으로 넣어야 "+1시간 뒤"가 실제로 미래가 된다.
    conn.execute("INSERT INTO auctions(case_id, deadline, status) "
                 "VALUES(?, datetime('now','+9 hours','+1 hours'), '진행')", (cid,))
    aid = conn.execute("SELECT id FROM auctions WHERE case_id=?", (cid,)).fetchone()["id"]
    conn.execute("INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
                 "VALUES(?,?,?,?,?,?)", (aid, pid, "R424업체", 1000000, 5, DB.now()))
    conn.commit()
    try:
        conn.execute(
            "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
            "VALUES(?,?,?,?,?,?)", (aid, pid, "R424업체", 900000, 5, DB.now()))
        conn.commit()
        chk(False, "★★★★★ 중복 활성입찰 직접 INSERT 가 인덱스에 막혀야 하는데 성공해버렸다")
    except sqlite3.IntegrityError as e:
        conn.rollback()
        chk(True, "★★★★★ 같은 (auction_id,partner_id) 활성입찰 중복 INSERT 가 "
            "IntegrityError 로 거부된다(인덱스 실효성 직접확인)", str(e))

    print("\n[4] 실행 — 실제 두 스레드가 같은 협력사로 동시에 투찰해도 중복행이 안 생기는가")
    conn.execute("UPDATE bids SET voided_at=?", (DB.now(),))
    conn.commit()

    admin = A.app.test_client()

    def _partner_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["partner_id"] = pid; sess["partner_login"] = "r424p"
            sess["partner_name"] = "R424업체"; sess["portal_role"] = "중간관리자"
            sess["_csrf"] = "r424-csrf"
        return c

    HIGH, LOW = 950_000, 850_000
    results = {}
    errs = []

    def _worker(key, amount):
        try:
            c = _partner_client()
            r = c.post("/api/partner/bids", headers={"X-CSRF-Token": "r424-csrf"},
                       json={"case_id": cid, "amount": amount, "days": 5})
            results[key] = (r.status_code, r.get_json())
        except Exception as e:                                     # noqa: BLE001
            errs.append(e)

    t1 = threading.Thread(target=_worker, args=("high", HIGH))
    t2 = threading.Thread(target=_worker, args=("low", LOW))
    t1.start(); t2.start()
    t1.join(10); t2.join(10)

    chk(not errs, "★★★★★ 동시 투찰 중 스레드에서 예외 없음(회귀없음)", errs)
    rows = conn.execute(
        "SELECT * FROM bids WHERE auction_id=? AND partner_id=? AND voided_at IS NULL",
        (aid, pid)).fetchall()
    chk(len(rows) == 1,
        "★★★★★ 동시에 두 번 투찰해도 활성입찰은 정확히 1건만 남는다"
        "(순서 무관하게 성립하는 불변식 — UNIQUE 인덱스+애플리케이션 upsert 이중방어)",
        [dict(r) for r in rows])
    chk(bool(rows) and rows[0]["amount"] == LOW,
        "★★★★★ 어느 스레드가 먼저 락을 잡든 최종 금액은 항상 더 낮은 값(LOW)이다"
        "(인하만 가능 규칙이 경합 순서와 무관하게 동일한 결과로 수렴함을 실측)",
        dict(rows[0]) if rows else None)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 되돌리기 — 인덱스가 없었다면 직접 SQL 중복 INSERT 가 실제로 성공했는가")
# ------------------------------------------------------------
try:
    _tmpdir2 = tempfile.mkdtemp(prefix="round424_revert_")
    _db2 = os.path.join(_tmpdir2, "verify2.db")
    import sqlite3 as _sqlite3
    conn2 = _sqlite3.connect(_db2)
    conn2.execute("""CREATE TABLE bids(
        id INTEGER PRIMARY KEY AUTOINCREMENT, auction_id INTEGER, partner_id INTEGER,
        partner_name TEXT, amount INTEGER, days INTEGER, created_at TEXT,
        first_bid_at TEXT, is_demo INTEGER DEFAULT 0, voided_at TEXT, void_reason TEXT)""")
    # 옛 상태(이 인덱스가 생기기 전) 재현 — idx_bids_auction/idx_bids_partner 만 있고
    # idx_bids_active_partner 는 없는 상태
    conn2.execute("CREATE INDEX idx_bids_auction ON bids(auction_id)")
    conn2.execute("CREATE INDEX idx_bids_partner ON bids(partner_id)")
    conn2.execute("INSERT INTO bids(auction_id,partner_id,amount,days,created_at) "
                  "VALUES(1,1,1000000,5,'x')")
    conn2.commit()
    dup_ok = True
    try:
        conn2.execute("INSERT INTO bids(auction_id,partner_id,amount,days,created_at) "
                      "VALUES(1,1,900000,5,'y')")
        conn2.commit()
    except _sqlite3.IntegrityError:
        dup_ok = False
    n = conn2.execute(
        "SELECT COUNT(*) c FROM bids WHERE auction_id=1 AND partner_id=1").fetchone()[0]
    conn2.close()
    chk(dup_ok and n == 2,
        "★★★★★ 인덱스가 없던 옛 스키마였다면 같은 (auction_id,partner_id) 활성입찰"
        " 중복 INSERT 가 아무 제지 없이 성공해 2건이 쌓였을 것이다(인과관계 직접증명)",
        {"dup_ok": dup_ok, "count": n})
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
