# -*- coding: utf-8 -*-
"""스캔 206라운드 회귀 — 콘솔(admin) 알림벨의 배지 수·읽음처리가 형제(보험사·
협력사) 포털과 달리 브로드캐스트(audience_type='all')를 포함시키던 결함.

  notify() 는 audience_type='all' 을 "전체(모든 포털)" 브로드캐스트로 정식
  지원한다. 포털(insurer·partner)은 그 공유행을 배지·읽음처리에서 명시적으로
  뺀다 — read_at 컬럼이 행 하나에 하나뿐이라, 한 사람이 전체를 읽음처리하면
  다른 포털에서도 그 항목이 조용히 "읽음"으로 보이는 사고를 막기 위해서다.
  콘솔(admin)만 세 곳(피드·배지·읽음처리) 전부에 ADMIN_FEED_SQL(admin OR all)
  을 그대로 재사용해 이 원칙을 어겼다 — 관리자가 "모두 읽음"을 누르면 그
  브로드캐스트 행의 read_at 이 채워져, 아직 한 번도 안 연 보험사·협력사
  화면에서도 그 항목이 "읽음"으로 보인다.

  지금은 audience_type="all" 로 실제 알리는 호출이 코드에 없어(notify() 의
  문서화된 정식 값인데도) 이 결함이 잠들어 있지만, 다음에 "전체 공지" 기능이
  이 값을 그대로 쓰는 순간 바로 재현된다 — 예방적 수정이다.

  ADMIN_OWN_SQL(admin 전용)을 신설해 배지·읽음처리에만 쓰고, 피드 표시는
  기존대로 브로드캐스트를 포함한다.

      python test_scan_round206_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 206라운드 회귀 — 콘솔 알림벨이 브로드캐스트를 배지·읽음처리에 포함시키던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk('ADMIN_OWN_SQL = "audience_type=\'admin\'"' in APP_SRC,
    "★★★★ admin 전용(브로드캐스트 제외) SQL 상수가 신설됐다")

i0 = APP_SRC.index("def api_admin_notifications(")
i1 = APP_SRC.index("\ndef api_admin_notifications_read")
feed_body = APP_SRC[i0:i1]
chk("WHERE {ADMIN_FEED_SQL} AND COALESCE(is_demo,0)=0" in feed_body,
    "★ 피드 목록 조회는 그대로 ADMIN_FEED_SQL(브로드캐스트 포함)을 쓴다"
    "(과잉수정 아님 — 피드엔 여전히 떠야 한다)")
chk("WHERE {ADMIN_OWN_SQL} " in feed_body and "read_at IS NULL" in feed_body,
    "★★★★ 배지(unread) 집계는 ADMIN_OWN_SQL(admin 전용)로 바뀌었다")

i2 = APP_SRC.index("def api_admin_notifications_read(")
i3 = APP_SRC.index("\n\n\n", i2)
read_body = APP_SRC[i2:i3]
chk(read_body.count("ADMIN_OWN_SQL") == 2 and "ADMIN_FEED_SQL" not in read_body,
    "★★★★ 읽음처리(단건·전체 둘 다)가 ADMIN_OWN_SQL 만 쓴다"
    "(ADMIN_FEED_SQL 참조가 이 함수에서 완전히 사라졌다)")

# ============================================================
print("\n[2] 실행 — 실제 서버(Flask test_client)로 브로드캐스트 오염 여부 확인")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round206_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r206admin','x','검증','최고관리자')")
    iid = conn.execute(
        "INSERT INTO insurers(name,status,login_id) VALUES('R206보험','활성','r206ins')").lastrowid
    nid_admin = conn.execute(
        "INSERT INTO notifications(ntype,channel,target,message,status,audience_type,is_demo,created_at) "
        "VALUES('보안','웹','운영팀','R206 admin 전용 알림','전달됨','admin',0,?)", (DB.now(),)).lastrowid
    nid_all = conn.execute(
        "INSERT INTO notifications(ntype,channel,target,message,status,audience_type,is_demo,created_at) "
        "VALUES('보안','웹','전체','R206 전체 브로드캐스트 알림','전달됨','all',0,?)", (DB.now(),)).lastrowid
    conn.commit()

    admin_c = A.app.test_client()
    atok = "r206-admin-csrf"
    with admin_c.session_transaction() as sess:
        sess["admin"] = "r206admin"; sess["admin_role"] = "최고관리자"; sess["_csrf"] = atok
    ahdr = {"X-CSRF-Token": atok}

    insurer_c = A.app.test_client()
    with insurer_c.session_transaction() as sess:
        sess["insurer_id"] = iid; sess["insurer_name"] = "R206보험"

    r_feed = admin_c.get("/api/admin/notifications")
    j_feed = r_feed.get_json()
    ids_in_feed = {n["id"] for n in j_feed["notifications"]}
    chk({nid_admin, nid_all} <= ids_in_feed,
        "★ (사전조건) 콘솔 피드엔 admin 전용·브로드캐스트 둘 다 보인다", ids_in_feed)
    chk(j_feed["unread"] == 1,
        "★★★★ 콘솔 배지 수는 admin 전용 1건만 센다(브로드캐스트는 안 셈 — "
        "고치기 전엔 2였다)", j_feed["unread"])

    r_read_all = admin_c.post("/api/admin/notifications/read", json={}, headers=ahdr)
    chk(r_read_all.status_code == 200 and r_read_all.get_json().get("ok"),
        "STEP 콘솔 '모두 읽음'이 200/ok 다")

    row_admin = dict(conn.execute(
        "SELECT read_at FROM notifications WHERE id=?", (nid_admin,)).fetchone())
    row_all = dict(conn.execute(
        "SELECT read_at FROM notifications WHERE id=?", (nid_all,)).fetchone())
    chk(row_admin["read_at"] is not None,
        "★ admin 전용 알림은 '모두 읽음'으로 정상적으로 read_at 이 채워진다", row_admin)
    chk(row_all["read_at"] is None,
        "★★★★ 브로드캐스트 알림은 콘솔의 '모두 읽음'에도 read_at 이 안 채워진다"
        "(고치기 전엔 여기서 채워져 다른 포털까지 오염시켰다)", row_all)

    r_insurer_feed = insurer_c.get("/api/insurer/notifications")
    j_ins = r_insurer_feed.get_json()
    ins_row = next((n for n in j_ins["notifications"] if n["id"] == nid_all), None)
    chk(ins_row is not None and ins_row["read_at"] is None,
        "★★★★★ 핵심 — 보험사 화면에서 그 브로드캐스트 항목은 여전히 '안 읽음'"
        "으로 보인다(관리자가 자기 콘솔에서 '모두 읽음'을 눌렀는데도 보험사가"
        " 아직 한 번도 안 연 항목이 조용히 '읽음'으로 오염되지 않는다)", ins_row)

    # ── 단건(id 지정) 읽음처리도 브로드캐스트는 건드리지 않는다 ──
    r_read_one = admin_c.post("/api/admin/notifications/read", json={"id": nid_all}, headers=ahdr)
    chk(r_read_one.status_code == 200, "STEP 단건 읽음처리 요청도 200 이다(에러 없음)")
    row_all2 = dict(conn.execute(
        "SELECT read_at FROM notifications WHERE id=?", (nid_all,)).fetchone())
    chk(row_all2["read_at"] is None,
        "★★★ 브로드캐스트를 콕 집어(id 지정) 읽음처리해도 admin 전용이 아니라서 "
        "그대로 안 읽음 상태다", row_all2)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드206 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
