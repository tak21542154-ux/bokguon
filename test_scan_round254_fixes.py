# -*- coding: utf-8 -*-
"""스캔 254라운드 회귀 — 대시보드·접속통계 화면 결함 2건
   (admin.js 통계·대시보드 화면군 Agent 조사로 발견, 전부 독립 재검증 후 수정).

  [1] sweep_auctions() 가 데모 사건의 경매도 실제로 마감·낙찰승인요청·유찰
      처리하고 DB.log("입찰 자동 마감" 등)까지 남겼다 — 개발 DB 시드에
      '입찰중' 데모 사건이 많아, 관리자가 대시보드를 여는 것만으로도
      (_sweep_if_due 가 매번 돈다) 데모 건이 자동 처리되며 대시보드
      "최근 활동" 패널에 실활동과 구분 안 되는 로그가 쌓였다. 이 함수가
      건드리는 다른 모든 집계는 이미 COALESCE(is_demo,0)=0 을 거는데
      스윕 자신만 빠져 있었다 — activity_log 는 case_id·is_demo 컬럼
      자체가 없어 표시 단계에서는 거를 수 없으므로, 표식을 만드는 스윕
      쪽(대상 조회 쿼리)에서 막는다.

  [2] api_traffic() 의 "로그인 성공" 집계가 관리자 로그인(/api/login)만
      세고 협력사(/api/partner/login)·보험사(/api/insurer/login) 로그인은
      빠졌다 — 같은 응답의 by_role 은 이미 네 주체를 나란히 보여주는데
      이 카드만 하나로 좁혀, 같은 화면에서 "누가 얼마나 썼는가"와
      "몇 번 로그인했는가"가 서로 다른 모집단을 말했다.

      python test_scan_round254_fixes.py
"""
import io
import os
import secrets
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
print("  스캔 254라운드 회귀 — 데모경매 자동처리 차단·로그인 집계 전채널화")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def sweep_auctions(")
i1 = APP_SRC.index("\ndef ", i0 + 10)
sweep_body = APP_SRC[i0:i1]
chk("AND COALESCE(c.is_demo,0)=0" in sweep_body,
    "★★★★ sweep_auctions() 의 대상 조회가 데모 사건을 뺀다")

i2 = APP_SRC.index("def api_traffic(")
i3 = APP_SRC.index("\n\n\n", i2)
traffic_body = APP_SRC[i2:i3]
chk("'/api/login','/api/partner/login','/api/insurer/login'" in traffic_body,
    "★★★★ 로그인 집계가 관리자·협력사·보험사 세 경로를 다 센다")

# ============================================================
print("\n[2] 실행(Flask) — 데모경매 자동처리 차단 실측")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round254_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,org_type,status) VALUES('R254보험사','손해보험','활성')"
    ).lastrowid
    mark = "R254-" + secrets.token_hex(3)

    def mkcase(is_demo):
        cur = conn.execute(
            "INSERT INTO cases(case_no,insurer_id,insurer,category,region,address,"
            "est_price,low_price,status,is_demo,created_at) "
            "VALUES(?,?,?,?,?,?,?,0,'입찰중',?,?)",
            (f"{mark}-{'demo' if is_demo else 'real'}", iid, "R254보험사",
             "가드레일·방호울타리", "서울", "검증용", 10_000_000, 1 if is_demo else 0, DB.now()))
        cid = cur.lastrowid
        conn.execute("INSERT INTO work_lots(case_id,category,status,created_at) "
                     "VALUES(?,?,'입찰중',?)", (cid, "가드레일·방호울타리", DB.now()))
        aid = A._open_original_auction(conn, cid)
        #  마감시각을 1시간 전으로 앞당긴다 — 시간을 기다리지 않는다(형제 test_b4_deadline.py 관용구).
        conn.execute("UPDATE auctions SET deadline=datetime('now','+9 hours','-1 hours') "
                     "WHERE id=?", (aid,))
        conn.commit()
        return cid, aid

    cid_demo, aid_demo = mkcase(is_demo=True)
    cid_real, aid_real = mkcase(is_demo=False)

    n_log_before = conn.execute(
        "SELECT COUNT(*) c FROM activity_log WHERE action='입찰 자동 마감'").fetchone()["c"]
    r = A.sweep_auctions(conn, force=True)
    n_log_after = conn.execute(
        "SELECT COUNT(*) c FROM activity_log WHERE action='입찰 자동 마감'").fetchone()["c"]

    demo_case = conn.execute("SELECT status FROM cases WHERE id=?", (cid_demo,)).fetchone()
    demo_auc = conn.execute("SELECT status FROM auctions WHERE id=?", (aid_demo,)).fetchone()
    real_case = conn.execute("SELECT status FROM cases WHERE id=?", (cid_real,)).fetchone()
    real_auc = conn.execute("SELECT status FROM auctions WHERE id=?", (aid_real,)).fetchone()

    chk(demo_case["status"] == "입찰중" and demo_auc["status"] == "진행",
        "★★★★★ 데모 사건의 경매는 마감시각이 지나도 자동 처리되지 않는다",
        f"case={demo_case['status']} auction={demo_auc['status']}")
    chk(n_log_after == n_log_before,
        "★★★★★ 데모 건은 activity_log(\"입찰 자동 마감\")에 흔적을 남기지 않는다",
        f"{n_log_before}→{n_log_after}")
    chk(real_case["status"] == "유찰" and real_auc["status"] == "유찰",
        "STEP 대조군 — 실제(비데모) 사건은 그대로 정상 자동 유찰 처리된다"
        "(과잉차단 아님, 입찰 0건이라 유찰)", f"case={real_case['status']} auction={real_auc['status']}")
    chk(r["scanned"] == 1,
        "STEP 스윕이 실제로 스캔한 건 실제 사건 1건뿐이다(데모는 대상 조회에서부터 빠짐)",
        r)

    conn.execute("DELETE FROM bids WHERE auction_id IN (?,?)", (aid_demo, aid_real))
    conn.execute("DELETE FROM auctions WHERE id IN (?,?)", (aid_demo, aid_real))
    conn.execute("DELETE FROM work_lots WHERE case_id IN (?,?)", (cid_demo, cid_real))
    conn.execute("DELETE FROM cases WHERE id IN (?,?)", (cid_demo, cid_real))
    conn.commit()

    # ── 로그인 집계 3채널 실측 ──
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r254adm','x','검증','최고관리자')")
    conn.execute(
        "INSERT INTO access_log(ip,user_id,role,method,path,status,created_at) VALUES"
        "('127.0.0.1','admin','최고관리자','POST','/api/login',200,?),"
        "('127.0.0.1','p1','협력사','POST','/api/partner/login',200,?),"
        "('127.0.0.1','i1','보험사','POST','/api/insurer/login',200,?),"
        "('127.0.0.1','x','최고관리자','POST','/api/login',401,?)",
        (DB.now(), DB.now(), DB.now(), DB.now()))
    conn.commit()

    admin = A.app.test_client()
    tok = "r254-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r254adm"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = tok
    rt = admin.get("/api/traffic")
    jt = rt.get_json()
    chk(rt.status_code == 200 and jt.get("logins", 0) >= 3,
        "★★★★★ 로그인 성공 집계에 협력사·보험사 로그인도 포함된다(실패 401은 제외)",
        jt.get("logins"))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드254 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
