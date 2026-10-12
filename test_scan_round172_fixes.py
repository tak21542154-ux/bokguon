# -*- coding: utf-8 -*-
"""스캔 172라운드 회귀 — 데모 격리가 출동(dispatch) 단계·알림 브로드캐스트에서
7개 지점에 빠져 있던 결함.

  R171 은 사건상세·사진업로드·완료보고·변경견적 6곳을 막았지만, 그보다 앞선
  '출동' 단계(수배 목록·수락·거절·도착·미수선종결) 와 알림함은 손대지
  않았다. dispatches/notifications 는 (partners 와 달리) is_demo 컬럼을
  실제로 갖고 있고 db.py 의 자동 백필(_CHILD_DEMO_SQL)이 매 기동마다
  cases.is_demo=1 을 자식 표로 내려 보내는데도, 이 7개 자리는 그 값을
  전혀 읽지 않았다 — 실측(운영DB 읽기전용 조회)으로 실제 협력사 #163·#207
  이 데모 수배(#96·#99)에 '도착' 상태로 남아 있고 cases.first_partner_id
  도 이 둘로 고정돼 있음을 확인했다.

      python test_scan_round172_fixes.py
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
DP_SRC = read("dispatch.py")

print("=" * 72)
print("  스캔 172라운드 회귀 — 출동 단계·알림 브로드캐스트의 데모 격리 누락(7곳)")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_partner_dispatches():")
i1 = APP_SRC.index("\n@app.", i0 + 1)
chk("COALESCE(d.is_demo,0)=0" in APP_SRC[i0:i1],
    "★★★ api_partner_dispatches 목록이 데모 수배를 뺀다")

for fn in ("def api_partner_notifications():", "def api_insurer_notifications():"):
    j0 = APP_SRC.index(fn)
    j1 = APP_SRC.index("\n@app.", j0 + 1)
    body = APP_SRC[j0:j1]
    chk(body.count("COALESCE(is_demo,0)=0") >= 2,
        f"★★★ {fn.split('(')[0][4:]} 이 목록·미읽음 배지 양쪽에서 데모를 뺀다")

for fn, marker in (
    ("def claim(conn", 'int(d["is_demo"] or 0)'),
    ("def decline(conn", "is_demo"),
    ("def arrive(conn", "COALESCE(is_demo,0)=0"),
    ("def close_no_repair(conn", "COALESCE(is_demo,0)=0"),
):
    k0 = DP_SRC.index(fn)
    k1 = DP_SRC.index("\ndef ", k0 + 1)
    body = DP_SRC[k0:k1]
    chk(marker in body, f"★★★ dispatch.{fn.split('(')[0][4:]}() 이 데모 수배를 막는다")

# ============================================================
print("\n[2] 실행 — 실제 협력사 계정이 데모 수배에 걸린 시나리오를 그대로 재현")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round172_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A
    import dispatch as DP

    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,status,login_id,created_at) "
        "VALUES('R172보험사','활성','r172i',?)", (DB.now(),)).lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,login_id,created_at) "
        "VALUES('R172업체','시공사','활성','가드레일','서울','r172p',?)", (DB.now(),)).lastrowid

    def new_case(tag, is_demo, status="접수", partner_id=None):
        return conn.execute(
            "INSERT INTO cases(case_no,status,category,region,insurer_id,partner_id,"
            "                  is_demo,created_at) "
            "VALUES(?,?,'가드레일','서울',?,?,?,?)",
            (f"R172-{tag}", status, iid, partner_id, is_demo, DB.now())).lastrowid

    #  (A) 목록 — 데모 수배 1건 + 실제 수배 1건, 실제 것만 보여야 한다
    cid_a = new_case("LIST-DEMO", 1)
    did_a = conn.execute(
        "INSERT INTO dispatches(case_id,status,is_demo,created_at) "
        "VALUES(?,?,1,?)", (cid_a, DP.ST_OPEN, DB.now())).lastrowid
    conn.execute("INSERT INTO dispatch_calls(dispatch_id,partner_id,created_at) "
                 "VALUES(?,?,?)", (did_a, pid, DB.now()))
    cid_real = new_case("LIST-REAL", 0)
    did_real = conn.execute(
        "INSERT INTO dispatches(case_id,status,is_demo,created_at) "
        "VALUES(?,?,0,?)", (cid_real, DP.ST_OPEN, DB.now())).lastrowid
    conn.execute("INSERT INTO dispatch_calls(dispatch_id,partner_id,created_at) "
                 "VALUES(?,?,?)", (did_real, pid, DB.now()))

    #  (B) claim() — 대상 확인까지 통과해야 진짜로 막히는지 알 수 있다
    cid_b = new_case("CLAIM", 1)
    did_b = conn.execute(
        "INSERT INTO dispatches(case_id,status,is_demo,created_at) "
        "VALUES(?,?,1,?)", (cid_b, DP.ST_OPEN, DB.now())).lastrowid
    conn.execute("INSERT INTO dispatch_calls(dispatch_id,partner_id,created_at) "
                 "VALUES(?,?,?)", (did_b, pid, DB.now()))

    #  (C) decline() — 응답이 아직 없어야(response IS NULL) UPDATE 대상이 된다
    cid_c = new_case("DECLINE", 1)
    did_c = conn.execute(
        "INSERT INTO dispatches(case_id,status,is_demo,created_at) "
        "VALUES(?,?,1,?)", (cid_c, DP.ST_OPEN, DB.now())).lastrowid
    conn.execute("INSERT INTO dispatch_calls(dispatch_id,partner_id,created_at) "
                 "VALUES(?,?,?)", (did_c, pid, DB.now()))

    #  (D) arrive() — 이미 수배됨 상태 + 사진 1장 이상이라야 성공 조건을 채운다
    cid_d = new_case("ARRIVE", 1)
    did_d = conn.execute(
        "INSERT INTO dispatches(case_id,status,claimed_partner_id,claimed_name,is_demo,created_at) "
        "VALUES(?,?,?,?,1,?)", (cid_d, DP.ST_CLAIMED, pid, "R172업체", DB.now())).lastrowid
    conn.execute(
        "INSERT INTO photos(case_id,partner_id,uploader,uploader_role,rel_path,created_at) "
        "VALUES(?,?,'R172업체','협력사','r172_test.jpg',?)", (cid_d, pid, DB.now()))

    #  (E) close_no_repair() — 수배됨 상태 + 사건 status='접수' AND partner_id IS NULL
    cid_e = new_case("NOREPAIR", 1)
    did_e = conn.execute(
        "INSERT INTO dispatches(case_id,status,claimed_partner_id,claimed_name,is_demo,created_at) "
        "VALUES(?,?,?,?,1,?)", (cid_e, DP.ST_CLAIMED, pid, "R172업체", DB.now())).lastrowid

    #  (F) 알림 — 전체공지(데모/실제 각 1) + 개별수신(협력사·보험사 데모 각 1)
    conn.execute(
        "INSERT INTO notifications(ntype,channel,target,message,created_at,"
        "                          audience_type,is_demo) "
        "VALUES('전체공지','웹','전체','R172 데모 브로드캐스트',?,'all',1)", (DB.now(),))
    conn.execute(
        "INSERT INTO notifications(ntype,channel,target,message,created_at,"
        "                          audience_type,is_demo) "
        "VALUES('전체공지','웹','전체','R172 실 브로드캐스트',?,'all',0)", (DB.now(),))
    conn.execute(
        "INSERT INTO notifications(ntype,channel,target,message,created_at,"
        "                          audience_type,partner_id,is_demo) "
        "VALUES('출동배정','웹','협력사','R172 데모 직통(협력사)',?,'partner',?,1)",
        (DB.now(), pid))
    conn.execute(
        "INSERT INTO notifications(ntype,channel,target,message,created_at,"
        "                          audience_type,insurer_id,is_demo) "
        "VALUES('사진확보','웹','보험사','R172 데모 직통(보험사)',?,'insurer',?,1)",
        (DB.now(), iid))
    conn.commit(); conn.close()

    partner = A.app.test_client()
    ptok = "r172-partner-csrf"
    with partner.session_transaction() as sess:
        sess["partner_id"] = pid; sess["partner_name"] = "R172업체"
        sess["partner_role"] = "중간관리자"; sess["_csrf"] = ptok
    phdr = {"X-CSRF-Token": ptok}

    insurer = A.app.test_client()
    itok = "r172-insurer-csrf"
    with insurer.session_transaction() as sess:
        sess["insurer_id"] = iid; sess["insurer_name"] = "R172보험사"; sess["_csrf"] = itok
    ihdr = {"X-CSRF-Token": itok}

    # (A) 목록
    rA = partner.get("/api/partner/dispatches", headers=phdr)
    idsA = [x["dispatch_id"] for x in rA.get_json().get("items", [])]
    chk(rA.status_code == 200 and did_real in idsA and did_a not in idsA,
        "★★★ 수배 목록 — 데모는 빠지고 실제 건은 그대로 보인다"
        "(고치기 전엔 데모도 같이 나왔다)", idsA)

    # (B) claim()
    connB = DB.get_db()
    okB, msgB, dueB = DP.claim(connB, did_b, pid, "R172업체")
    connB.close()
    chk(okB is False,
        "★★★ claim() — 데모 수배는 수락되지 않는다(고치기 전엔 수락됐다)", (okB, msgB))

    # (C) decline()
    connC = DB.get_db()
    okC = DP.decline(connC, did_c, pid)
    connC.close()
    chk(okC is False,
        "★★★ decline() — 데모 수배는 거절 기록도 남기지 않는다(고치기 전엔 거절됐다)", okC)

    # (D) arrive()
    connD = DB.get_db()
    okD, msgD = DP.arrive(connD, did_d, pid, photo_count=1, field_estimate=100000)
    connD.close()
    chk(okD is False,
        "★★★ arrive() — 데모 수배는 도착 보고를 받지 않는다(고치기 전엔 성공했다)",
        (okD, msgD))

    # (E) close_no_repair()
    connE = DB.get_db()
    okE, msgE = DP.close_no_repair(connE, did_e, pid,
                                    reason="피해자가 수선을 원치 않음", note="", by="현장")
    connE.close()
    chk(okE is False,
        "★★★ close_no_repair() — 데모 수배는 미수선 종결도 못 낸다(고치기 전엔 성공했다)",
        (okE, msgE))

    # (F) 알림 — 협력사
    rF1 = partner.get("/api/partner/notifications", headers=phdr)
    jF1 = rF1.get_json()
    msgsF1 = [n["message"] for n in jF1.get("notifications", [])]
    chk("R172 데모 브로드캐스트" not in msgsF1 and "R172 데모 직통(협력사)" not in msgsF1,
        "★★★ 협력사 알림함 — 데모 알림(전체·직통)이 안 뜬다"
        "(고치기 전엔 전체공지가 그대로 보였다)", msgsF1)
    chk("R172 실 브로드캐스트" in msgsF1,
        "★★★ 협력사 알림함 — 실제 전체공지는 그대로 보인다(과도필터 아님)", msgsF1)
    chk(jF1.get("unread", 0) == 0,
        "★★★ 협력사 미읽음 배지 — 데모 직통 알림을 안 센다(고치기 전엔 1이었다)",
        jF1.get("unread"))

    # (F) 알림 — 보험사
    rF2 = insurer.get("/api/insurer/notifications", headers=ihdr)
    jF2 = rF2.get_json()
    msgsF2 = [n["message"] for n in jF2.get("notifications", [])]
    chk("R172 데모 브로드캐스트" not in msgsF2 and "R172 데모 직통(보험사)" not in msgsF2,
        "★★★ 보험사 알림함 — 데모 알림(전체·직통)이 안 뜬다"
        "(고치기 전엔 전체공지가 그대로 보였다)", msgsF2)
    chk("R172 실 브로드캐스트" in msgsF2,
        "★★★ 보험사 알림함 — 실제 전체공지는 그대로 보인다(과도필터 아님)", msgsF2)
    chk(jF2.get("unread", 0) == 0,
        "★★★ 보험사 미읽음 배지 — 데모 직통 알림을 안 센다(고치기 전엔 1이었다)",
        jF2.get("unread"))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드172 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
