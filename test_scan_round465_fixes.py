# -*- coding: utf-8 -*-
"""스캔 465라운드 회귀 — `api_insurer_settlement_approve()`(app.py)가
정산 4형제(review·transfer·void·paid[-bulk])와 달리 최종 UPDATE에
상태조건+rowcount 재확인 겹방어가 빠져 있던 결함, 1건(방어심화).

⚠ 이건 "지금 뚫리는 결함을 고쳤다"가 아니다 — 정밀조사 Agent가 실제
동시 스레드 재현(2~5개, 3회 반복)으로 확인한 대로, 이 함수는 이미
`BEGIN IMMEDIATE`(app.py 3407행)로 쓰기잠금을 즉시 잡고 그 안에서
읽기→사전확인(`if st["insurer_approved"]: return 409`)→쓰기를 전부
끝내므로, 다른 트랜잭션은 그 사이에 절대 끼어들 수 없다 — 지금 이
경로로는 이중승인이 안 난다(재검증 완료). 다만 같은 파일의 형제 4곳
(`api_settlement_review`13888행·`transfer`·`void`·`paid`)은 전부 그
사전확인에 **더해** 최종 UPDATE 자체에도 `WHERE ...=상태` +
`cur.rowcount` 재확인을 겹쳐 건다 — `BEGIN IMMEDIATE` 하나만 믿지
않고, 나중에 격리수준이 약해지거나 이 UPDATE 문이 다른 경로에서
재사용돼도(사전확인을 안 거치고) 스스로 방어하게 하기 위해서다.
이 함수만 그 겹방어가 빠져 있었다 — 돈이 걸린 자리라 형제와 같은
패턴을 이식한다(새 메커니즘 없음, 트레이드오프 없음).

[1] 소스 확인 — WHERE+rowcount 겹방어 코드가 실제로 있음.
[2] 실제 Flask 앱 실행 — 정상 흐름(1회 승인 성공→DB 반영→알림 1건,
    재승인 시도는 여전히 사전확인에서 409)이 안 깨졌음을 확인.
[3] SQL 가드 자체의 단위 검증 — 이 UPDATE 문을 사전확인 없이 스크래치
    DB에 직접 실행해, 이미 승인된 행(insurer_approved=1)에는
    rowcount=0(거부), 아직 승인 전 행(=0)에는 rowcount=1(반영)임을
    확인 — 사전확인이 없는 가상의 호출 경로에서도 이 UPDATE 문 자신이
    스스로 막는다는, 겹방어의 실제 값어치를 증명한다.
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


print("=" * 72)
print("  스캔 465라운드 회귀 — 보험사 완료승인 겹방어(defense in depth)")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

GUARD_SQL = ('"UPDATE settlements SET insurer_approved=1, insurer_approved_at=? "\n'
             '        "WHERE id=? AND insurer_approved=0", (DB.now(), sid))')
chk(GUARD_SQL in APP_SRC,
    "★★★★★ api_insurer_settlement_approve()의 UPDATE에 상태조건 겹방어가 있다")
chk('if not cur.rowcount:' in APP_SRC[APP_SRC.find("def api_insurer_settlement_approve"):
                                       APP_SRC.find("def api_insurer_settlement_approve") + 2500],
    "★★★★ rowcount 재확인이 함수 안에 실제로 있다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 Flask 앱 — 정상 흐름 회귀 없음 확인")
# ══════════════════════════════════════════════════════════════
_tmpdir = tempfile.mkdtemp(prefix="r465_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB               # noqa: E402
DB.init_db()
import app as A                # noqa: E402

conn = DB.get_db()
iid = conn.execute(
    "INSERT INTO insurers(name,status) VALUES('R465보험','활성')").lastrowid
cid = conn.execute(
    "INSERT INTO cases(case_no,status,category,region,insurer_id) "
    "VALUES('26-465001','완료','가드레일','서울',?)", (iid,)).lastrowid
sid = conn.execute(
    "INSERT INTO settlements(case_id,case_no,insurer_id,partner_name,amount,fee,payout,"
    "fee_rate_bp,transfer_status,insurer_paid,review_status,insurer_approved,void_status) "
    "VALUES(?,?,?,?,?,?,?,?,?,?,?,0,NULL)",
    (cid, "26-465001", iid, "R465업체", 1000000, 100000, 900000, 1000,
     "대기", "미확인", "대기")).lastrowid
conn.commit()
conn.close()

c = A.app.test_client()
with c.session_transaction() as sess:
    sess["insurer_id"] = iid
    sess["insurer_name"] = "R465보험"
    sess["insurer_role"] = "중간관리자"
    sess["_csrf"] = "r465-csrf"

r1 = c.post(f"/api/insurer/settlements/{sid}/approve", json={},
            headers={"X-CSRF-Token": "r465-csrf"})
chk(r1.status_code == 200, "★★★★★ 첫 승인은 정상 200", (r1.status_code, r1.get_json()))

conn2 = DB.get_db()
row = conn2.execute("SELECT insurer_approved FROM settlements WHERE id=?", (sid,)).fetchone()
n_notify = conn2.execute(
    "SELECT COUNT(*) n FROM notifications WHERE ntype='완료승인' AND case_id=?",
    (cid,)).fetchone()["n"]
conn2.close()
chk(row["insurer_approved"] == 1, "DB에 insurer_approved=1로 반영됐다")
chk(n_notify == 1, "완료승인 알림이 1건 나갔다")

r2 = c.post(f"/api/insurer/settlements/{sid}/approve", json={},
            headers={"X-CSRF-Token": "r465-csrf"})
chk(r2.status_code == 409 and "이미 완료 승인" in (r2.get_json() or {}).get("error", ""),
    "★★★★★ 재승인 시도는 여전히(사전확인에서) 409 — 회귀 없음", r2.get_json())

conn3 = DB.get_db()
n_notify2 = conn3.execute(
    "SELECT COUNT(*) n FROM notifications WHERE ntype='완료승인' AND case_id=?",
    (cid,)).fetchone()["n"]
conn3.close()
chk(n_notify2 == 1, "재승인 시도로 알림이 추가로 안 나갔다(1건 유지)")

# ══════════════════════════════════════════════════════════════
print("\n[3] SQL 가드 자체 단위 검증 (사전확인을 건너뛴 가상 호출을 흉내)")
# ══════════════════════════════════════════════════════════════
raw_path = os.path.join(_tmpdir, "raw_guard.db")
rc = sqlite3.connect(raw_path)
rc.execute("CREATE TABLE settlements(id INTEGER PRIMARY KEY, insurer_approved INTEGER DEFAULT 0, "
           "insurer_approved_at TEXT)")
rc.execute("INSERT INTO settlements(id, insurer_approved) VALUES (1, 0)")
rc.execute("INSERT INTO settlements(id, insurer_approved) VALUES (2, 1)")
rc.commit()

cur_fresh = rc.execute(
    "UPDATE settlements SET insurer_approved=1, insurer_approved_at=? "
    "WHERE id=? AND insurer_approved=0", ("2026-09-06", 1))
chk(cur_fresh.rowcount == 1,
    "★★★★ 아직 미승인(0) 행에는 이 UPDATE가 실제로 반영된다(rowcount=1)",
    cur_fresh.rowcount)

cur_already = rc.execute(
    "UPDATE settlements SET insurer_approved=1, insurer_approved_at=? "
    "WHERE id=? AND insurer_approved=0", ("2026-09-06", 2))
chk(cur_already.rowcount == 0,
    "★★★★★ 이미 승인(1)된 행에는 사전확인 없이도 이 UPDATE 자체가 거부한다(rowcount=0)"
    " — 겹방어의 실제 값어치", cur_already.rowcount)
rc.close()

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
