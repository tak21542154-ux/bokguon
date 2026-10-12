# -*- coding: utf-8 -*-
"""스캔 59라운드 회귀 — 경매 마감 스윕 TOCTOU 경합(HIGH) + 종결상태 목록 드리프트
   (CASE_OPEN_SQL 미적용 4곳, MEDIUM).

  조사 에이전트가 실측(격리 DB + 순차 재현/실제 서버)으로 증명한 결함:

  ① sweep_auctions() 가 입찰자 수(nb)를 **잠금을 잡기 전에** 세고, 잠금(BEGIN
     IMMEDIATE) 뒤에는 다시 안 세고 그 죽은 값을 그대로 썼다 — 형제 함수
     sweep_dispatches() 는 이미 '잠금 뒤 조건부 UPDATE' 로 이 함정을 피해 가는데
     여기만 예외였다. 마감 직전에 커밋된 정상 입찰이 스윕의 잠금 대기 구간에
     걸리면, 그 입찰은 실제로 존재하는데도 스윕은 0건으로 착각해 사건을 '유찰'
     로 자동 종결한다 — 협력사에겐 에러도 안 뜨고(자기 요청은 성공했으므로),
     보험사에겐 "입찰 0건" 알림이 간다.
  ② CASE_OPEN_SQL(종결상태 3종 NOT IN)이 딱 이 드리프트를 막으려고 만든
     단일 소스인데, 4곳이 각자 손으로 다시 적어 그중 3곳은 '취소'가 빠지고
     1곳은 종결 필터가 아예 없었다. 취소된 사건이 운영 대시보드의
     '출동수배_실패' 카드·오늘 할 일 목록·출동 관제 화면·KPI 단계정체 표에
     계속 걸린다.

      python test_scan_round59_fixes.py
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


APP_SRC = read("app.py")

print("═" * 72)
print("  스캔 59라운드 회귀 — 경매마감 스윕 TOCTOU 경합 + 종결상태 드리프트 4곳")
print("═" * 72)


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
sweep_body = _body(APP_SRC, "sweep_auctions")
i_begin = sweep_body.find('conn.execute("BEGIN IMMEDIATE")')
i_nb = sweep_body.find('"SELECT COUNT(DISTINCT b.partner_id)')
chk(i_begin != -1 and i_nb != -1 and i_begin < i_nb,
    "★★★ ① sweep_auctions — 입찰자 수를 BEGIN IMMEDIATE **뒤**에 센다"
    "(고치기 전엔 잠금 전에 세고 다시 안 셌다)", (i_begin, i_nb))

#  ⚠⚠ [라운드213] 정확히 5곳으로 못박으면, CASE_OPEN_SQL 을 새로 채택하는
#    합당한 확장(보험사 포털 KPI 등)이 생길 때마다 이 카운트가 거짓 실패한다
#    — 최소 개수(지금까지 확립된 5곳)만 확인한다. 하나도 안 줄었는지가
#    핵심이지, "더는 안 늘어난다"가 핵심이 아니다.
n_open_sql_refs = APP_SRC.count("{CASE_OPEN_SQL}")
chk(n_open_sql_refs >= 5,
    "★★ ② CASE_OPEN_SQL 참조가 기존 1곳(사건 드릴다운) + 새로 고친 4곳 = "
    "최소 5곳(그 뒤로도 정당한 채택이 늘 수 있다)",
    n_open_sql_refs)
chk('_OPEN = "status NOT IN' not in APP_SRC,
    "★ ② 중복 재정의(_OPEN)를 지우고 CASE_OPEN_SQL 하나로 합쳤다")

dash_body = _body(APP_SRC, "api_dashboard")
chk('f"AND {CASE_OPEN_SQL} AND COALESCE(is_demo,0)=0"' in dash_body,
    "★★ ② api_dashboard — 출동수배_실패 카드가 CASE_OPEN_SQL 을 쓴다")

kpi_body = _body(APP_SRC, "_compute_ops_kpi")
chk("WHERE {WS} AND {CASE_OPEN_SQL}" in kpi_body,
    "★★ ② _compute_ops_kpi — 단계정체 표가 CASE_OPEN_SQL 을 쓴다")

dispatch_body = _body(APP_SRC, "api_dispatch_list")
chk("AND {CASE_OPEN_SQL}" in dispatch_body,
    "★★ ② api_dispatch_list — 정체 목록이 CASE_OPEN_SQL 을 쓴다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 DB(임시 파일)로 ① TOCTOU 경합 순차 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round59_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)


class _RaceProxy:
    """conn 을 감싸 첫 BEGIN IMMEDIATE 직전에 '동시 입찰 커밋'을 주입한다.

    스레드/sleep 없이도 "그 순간 막 커밋된 입찰을 이 SELECT 가 보는가" 를
    결정적으로 재현한다 — 고치기 전(잠금 전에 세는 코드)엔 주입이 BEGIN
    IMMEDIATE 시점에 일어나므로 그보다 앞서 실행된 nb 조회는 여전히 0을 든
    채로 남고, 고친 뒤(잠금 뒤에 세는 코드)엔 nb 조회 자체가 주입 이후에
    실행되어 새 입찰을 정확히 본다.
    """

    def __init__(self, real_conn, on_first_begin_immediate):
        self._real = real_conn
        self._fired = False
        self._hook = on_first_begin_immediate

    def execute(self, sql, *a, **kw):
        if (not self._fired) and sql.strip() == "BEGIN IMMEDIATE":
            self._fired = True
            self._hook()
        return self._real.execute(sql, *a, **kw)

    def __getattr__(self, name):
        return getattr(self._real, name)


try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('검증보험사59','활성')").lastrowid
    p_race = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('경합입찰사59','시공사','활성')"
    ).lastrowid

    #  ── 경주 대상 사건·경매 (id 가 더 작아 스윕 루프에서 먼저 처리된다) ──
    cid_race = conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,category,region) "
        "VALUES(?,'입찰중',?,?,?,'서울')",
        ("59R-0001", "검증보험사59", iid, "누수·배관·설비")).lastrowid
    auid_race = conn.execute(
        "INSERT INTO auctions(case_id,status,kind,deadline) "
        "VALUES(?,'진행','원경매',datetime('now','+9 hours','-1 hours'))", (cid_race,)).lastrowid

    #  ── 대조군 사건·경매 (진짜로 입찰 0건 — id 가 더 커서 나중에 처리된다) ──
    cid_ctrl = conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,category,region) "
        "VALUES(?,'입찰중',?,?,?,'서울')",
        ("59R-0002", "검증보험사59", iid, "누수·배관·설비")).lastrowid
    auid_ctrl = conn.execute(
        "INSERT INTO auctions(case_id,status,kind,deadline) "
        "VALUES(?,'진행','원경매',datetime('now','+9 hours','-1 hours'))", (cid_ctrl,)).lastrowid
    conn.commit()

    def _inject_race_bid():
        #  ⚠ 별도(진짜) 커넥션으로 — 스윕의 conn 은 아직 BEGIN IMMEDIATE 를
        #    실행하기 전이라 잠금이 없다. 여기서 커밋해 두면, 그 직후 스윕이
        #    잠금을 잡고 나서(고친 코드) 또는 이미 잡은 뒤(옛 코드) nb 를
        #    셀 때 이 커밋이 보이거나 이미 지나쳤거나가 갈린다.
        c2 = sqlite3.connect(os.environ["BOKGUON_DB_PATH"], timeout=30)
        try:
            c2.execute("BEGIN IMMEDIATE")
            c2.execute(
                "INSERT INTO bids(auction_id,partner_id,partner_name,amount,created_at) "
                "VALUES(?,?,?,?,datetime('now','+9 hours'))",
                (auid_race, p_race, "경합입찰사59", 1500000))
            c2.commit()
        finally:
            c2.close()

    conn2 = DB.get_db()
    proxy = _RaceProxy(conn2, _inject_race_bid)
    res = A.sweep_auctions(proxy, force=True)
    conn2.close()

    chk(res.get("scanned") == 2, "STEP 스윕이 경주·대조군 경매 2건을 모두 대상으로 잡았다", res)

    conn = DB.get_db()
    case_race = dict(conn.execute("SELECT status FROM cases WHERE id=?", (cid_race,)).fetchone())
    auc_race = dict(conn.execute("SELECT status FROM auctions WHERE id=?", (auid_race,)).fetchone())
    n_bids_race = conn.execute(
        "SELECT COUNT(*) FROM bids WHERE auction_id=?", (auid_race,)).fetchone()[0]
    case_ctrl = dict(conn.execute("SELECT status FROM cases WHERE id=?", (cid_ctrl,)).fetchone())
    conn.close()

    chk(n_bids_race == 1, "STEP 경주 입찰이 실제로 1건 커밋되어 있다(전제 확인)", n_bids_race)
    chk(case_race["status"] == "승인대기",
        "★★★ ① 잠금 대기 중 막 커밋된 입찰을 스윕이 놓치지 않는다"
        "(고치기 전엔 죽은 nb=0 으로 '유찰' 오판정)", case_race)
    chk(auc_race["status"] == "마감",
        "★ ① 경매 자체는 정상적으로 마감 처리된다(유찰이 아니라 마감)", auc_race)
    chk(case_ctrl["status"] == "유찰",
        "★ 대조군 — 진짜 입찰 0건인 경매는 여전히 정확히 유찰 처리된다"
        "(과잉교정 아님)", case_ctrl)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 실행 — 실제 서버(test_client)로 ② CASE_OPEN_SQL 드리프트 재현")
    # ──────────────────────────────────────────────────────────
    #  취소된 사건인데 옛 실패 수배 표식이 남아 있는 경우 — 4곳 모두 안 잡혀야 한다.
    conn = DB.get_db()
    cid_cancel = conn.execute(
        "INSERT INTO cases(case_no,status,dispatch_status,insurer,insurer_id,category,region) "
        "VALUES(?,'취소','수배실패',?,?,?,'서울')",
        ("59C-0001", "검증보험사59", iid, "누수·배관·설비")).lastrowid
    conn.commit(); conn.close()

    conn = DB.get_db()
    g_blocked = A._today_group(conn, A.TODAY_BLOCKED, "blocked", "t", "red")
    conn.close()
    labels_blocked = [it["label"] for it in g_blocked["items"]]
    chk("출동 수배가 실패했습니다" not in labels_blocked,
        "★★ ②-오늘할일 취소된 사건은 '출동 수배가 실패했습니다' 항목에 안 잡힌다"
        "(고치기 전엔 필터가 아예 없어 무조건 잡혔다)", labels_blocked)

    client = A.app.test_client()
    _tok = "regress-round59-csrf-token"
    _hdr = {"X-CSRF-Token": _tok}
    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin59','x','검증','중간관리자')")
    conn.commit(); conn.close()

    def _admin_sess(sess):
        sess["admin"] = "admin59"; sess["admin_role"] = "중간관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = _tok

    with client.session_transaction() as sess:
        _admin_sess(sess)

    rd = client.get("/api/dashboard")
    chk(rd.status_code == 200, "STEP /api/dashboard 정상 응답", rd.status_code)
    n_dispatch_failed = (rd.get_json() or {}).get("actions", {}).get("출동수배_실패")
    chk(n_dispatch_failed == 0,
        "★★ ②-대시보드 '출동수배_실패' 카드가 취소된 사건을 안 센다"
        "(고치기 전엔 '취소'가 빠져 1로 잡혔다)", n_dispatch_failed)

    rl = client.get("/api/dispatches")
    chk(rl.status_code == 200, "STEP /api/dispatches 정상 응답", rl.status_code)
    failed_nos = [f["case_no"] for f in (rl.get_json() or {}).get("failed_cases", [])]
    chk("59C-0001" not in failed_nos,
        "★★ ②-출동관제 취소된 사건이 정체 목록에 안 뜬다"
        "(고치기 전엔 '취소'가 빠져 계속 떴다)", failed_nos)

    rk = client.get("/api/ops-kpi")
    chk(rk.status_code == 200, "STEP /api/ops-kpi 정상 응답", rk.status_code)
    stage_statuses = [s["status"] for s in (rk.get_json() or {}).get("stages", [])]
    chk("취소" not in stage_statuses,
        "★★ ②-KPI단계정체 '취소' 상태 행이 단계정체 표에 안 뜬다"
        "(고치기 전엔 '취소'가 빠져 정체 상태처럼 표에 남았다)", stage_statuses)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드59 실측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
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
