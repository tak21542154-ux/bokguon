# -*- coding: utf-8 -*-
"""스캔 491라운드 회귀 — api_case_renotify()(공고 재알림, app.py:19432)의 30분
쿨다운에 형제(api_settlement_remind_approval 라운드85·api_case_remind_report
라운드490)와 같은 BEGIN IMMEDIATE 가 없어, 진짜 동시요청 두 개가 똑같이
쿨다운 확인을 통과해 알림이 중복 발송될 수 있던 결함.

⚠ 이 라운드의 수정도(490라운드처럼) 함수 안 다섯 곳(BEGIN IMMEDIATE 삽입 +
  기존 조기반환 4곳 각각에 conn.rollback() 추가)에 흩어져 있어, 함수 전체를
  통째로(데코레이터부터 마지막 return 까지) 고정문자열로 캡처해 원본 전체
  텍스트로 통째 치환하는 방식으로 되돌린다.

실행 확인은 소스검사뿐 아니라 실제 threading.Barrier 로 두 스레드를 쿨다운
확인 SELECT 지점에 동시 도달시키는 진짜 경합 재현을 포함한다(라운드491
조사 에이전트가 만든 재현 스크립트와 같은 기법 — 이 세션이 독립 재실행해
같은 결과를 직접 확인했다).

⚠⚠ [라운드622] 되돌림-증명 기법을 옛 세대(app.py를 실제로 디스크에 써넣고
   매 실행 새로 생성한 워커 스크립트(test_scan_round491_worker.py)를
   서브프로세스로 돌린 뒤 복원)에서 round490이 확립한 안전패턴으로 이관한다.
   api_case_renotify()는 단일 라우트 핸들러라 ORIGINAL_FUNC 텍스트(데코레이터
   제거)를 exec로 독립 사본 네임스페이스에 재구성해 A.app.view_functions
   딕셔너리 항목만 잠깐 치환한다 — 진짜 app.py 파일도, 워커 파일도 전혀
   안 쓴다(옛 워커는 더 이상 생성하지 않는다). 진짜 동시성 재현
   (threading.Barrier + 실제 스레드 2개)은 그대로 유지하되 별도 서브프로세스
   대신 이 프로세스 안에서 직접 돈다 — db.py의 get_db()는 호출마다 새
   sqlite3 커넥션을 열 뿐 스레드 간 공유가 없고, WAL+BEGIN IMMEDIATE
   직렬화는 프로세스 경계와 무관하게 동작하므로 안전하다(round490과 같은
   근거).
"""
import io
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(c, n, d=""):
    (PASS if c else FAIL).append((n, d))
    print(("  [OK]   " if c else "  [FAIL] ") + n + ("" if c else f"   {d}"))


print("=" * 72)
print("  스캔 491라운드 회귀 — 공고 재알림 쿨다운 동시성 결함")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 함수 전체를 통째로 추출")
# ──────────────────────────────────────────────────────────────
START = '@app.post("/api/cases/<int:cid>/renotify")'
END_MARK = ('                                "협력사 온보딩에서 계정을 먼저 발급해 주세요.")})\n')
_s = APP_SRC.find(START)
_e = APP_SRC.find(END_MARK, _s)
_e = _e + len(END_MARK) if _e > 0 else -1
CURRENT_FUNC = APP_SRC[_s:_e] if _s > 0 and _e > _s else ""

chk(bool(CURRENT_FUNC), "함수 전체를 찾았다")
chk(APP_SRC.count(CURRENT_FUNC) == 1, "함수 텍스트가 소스에 유일하다",
    APP_SRC.count(CURRENT_FUNC) if CURRENT_FUNC else 0)
chk("BEGIN IMMEDIATE" in CURRENT_FUNC, "BEGIN IMMEDIATE가 있다")
chk(CURRENT_FUNC.count("conn.rollback()") == 4,
    "조기반환 4곳(404·409·409·429) 모두 rollback을 한다",
    CURRENT_FUNC.count("conn.rollback()"))

#  이 세션이 수정 직전에 직접 Read로 확인해 둔 원본(라운드491 이전) 전체 텍스트.
ORIGINAL_FUNC = '''@app.post("/api/cases/<int:cid>/renotify")
@require_role("하위관리자")
def api_case_renotify(cid):
    """열려 있는 공고를 협력사에게 **다시** 알린다.

      왜 —
        첫 알림을 놓치거나 못 본 채 마감이 다가오는 일이 실제로 생긴다.
        그때 운영자가 할 수 있는 일이 '기다리기' 밖에 없으면 유찰로 간다.

      ⚠ 이것은 **알림을 다시 보내는 것뿐**이다. 낙찰을 정하지도, 금액을
        바꾸지도, 특정 업체를 부르지도 않는다(철칙 5·7).
      ⚠ 마감이 지난 공고에는 보내지 않는다 — 들어와도 투찰이 막혀
        업체는 헛걸음을 하고 우리를 못 믿게 된다.
      ⚠ 너무 자주 보내면 알림이 소음이 된다. 30분 안에 다시 누르면 막는다.
    """
    conn = DB.get_db()
    c = one(conn.execute(
        """SELECT c.id, c.case_no, c.category, c.region, c.status,
                  a.id AS auction_id, a.deadline, a.status AS astatus
             FROM cases c LEFT JOIN auctions a
               ON a.case_id=c.id AND a.status='진행'
            WHERE c.id=?""", (cid,)))
    if not c:
        conn.close(); return jsonify({"ok": False, "error": "사건을 찾을 수 없습니다."}), 404
    if not c["auction_id"]:
        conn.close()
        return jsonify({"ok": False,
                        "error": "지금 열려 있는 공고가 없습니다. 먼저 공고를 열어 주세요."}), 409
    _left = one(conn.execute(
        "SELECT (deadline > datetime('now','+9 hours')) AS alive FROM auctions WHERE id=?",
        (c["auction_id"],)))
    if not (_left or {}).get("alive"):
        conn.close()
        return jsonify({"ok": False,
                        "error": "이미 마감된 공고입니다. 다시 알려도 투찰할 수 없습니다 — "
                                 "재공고를 여시거나 출동 수배로 전환해 주세요."}), 409
    #  ⚠ 30분 안에 또 누르는 것을 막는다. 감사 로그를 기준으로 본다 —
    #    따로 컬럼을 두면 그 값만 갱신되고 로그와 어긋난다.
    #  ⚠⚠ [라운드117] 접수번호를 이스케이프 없이 LIKE 에 넣으면, '%'·'_' 가
    #    든 접수번호를 가진 사건은 **남의** 재알림 기록에 걸려 정당한 재알림이
    #    엉뚱하게 30분 쿨다운(COOLDOWN)에 막힐 수 있었다.
    #  ⚠⚠ [라운드318] LIKE 후보만으로 세면, 접수번호가 다른 사건 접수번호의
    #    부분열일 때 **남의** 재알림 기록에 걸려 정당한 재알림이 엉뚱하게
    #    쿨다운에 막힐 수 있다(_case_no_in_detail 주석 참고) — 경계검사로
    #    한 번 더 확인한 뒤에 센다.
    recent_candidates = rows(conn.execute(
        "SELECT detail FROM activity_log "
        " WHERE action='공고 재알림' AND detail LIKE ? ESCAPE '\\\\' "
        "   AND created_at > datetime('now','+9 hours','-30 minutes')",
        (f"%{_like_escape(c['case_no'])}%",)))
    if any(_case_no_in_detail(r["detail"], c["case_no"]) for r in recent_candidates):
        conn.close()
        return jsonify({"ok": False,
                        "error": "30분 안에 이미 다시 알렸습니다. 너무 잦은 알림은 "
                                 "업체가 알림 자체를 꺼 버리게 만듭니다."}), 429

    n_match = conn.execute(
        "SELECT COUNT(*) FROM partners WHERE partner_type='시행사' AND status='활성' "
        "  AND COALESCE(login_id,'') <> ''").fetchone()[0]
    notify(conn, "공고재개", "푸시", f"시행사 {n_match}곳",
           f"[{c['case_no']}] {(c['region'] or '')} {(c['category'] or '')} "
           f"공고가 곧 마감됩니다. 참여를 원하시면 지금 입찰해 주세요.",
           audience_type="all-partner", case_id=cid, url="/app/partner")
    DB.log(conn, actor(), "공고 재알림",
           f"{c['case_no']} · 대상 시행사 {n_match}곳")
    conn.commit(); conn.close()
    return jsonify({"ok": True, "targets": n_match,
                    "message": (f"시행사 {n_match}곳에 다시 알렸습니다."
                                if n_match else
                                "부를 수 있는 시행사가 0곳입니다 — "
                                "협력사 온보딩에서 계정을 먼저 발급해 주세요.")})
'''

chk("BEGIN IMMEDIATE" not in ORIGINAL_FUNC, "원본 텍스트에는 BEGIN IMMEDIATE가 없다(대조군)")
chk(ORIGINAL_FUNC.count("conn.close()") == 5,
    "원본은 5곳(404·409·409·429·성공) 모두 rollback 없이 그냥 close만 한다",
    ORIGINAL_FUNC.count("conn.close()"))

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 준비 — 스크래치 DB + 실제 Flask 인프로세스 호출(진짜 스레드 경합)")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round491_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB                 # noqa: E402
DB.init_db()
import app as A                  # noqa: E402

_seed_n = [0]


def _seed_case():
    """매 시나리오(현재/되돌림/원복)마다 독립된 관리자 2명·사건·진행중 공고를
    새로 만들어 세 번의 호출이 서로 간섭하지 않게 한다(옛 워커의 시드 로직)."""
    _seed_n[0] += 1
    n = _seed_n[0]
    c = DB.get_db()
    c.execute("INSERT INTO admins(username,password_hash,name,role) "
              f"VALUES('ra{n}','x','n1','하위관리자')")
    c.execute("INSERT INTO admins(username,password_hash,name,role) "
              f"VALUES('rb{n}','x','n2','하위관리자')")
    case_no = f"R491-{n}"
    cid = c.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES(?,'접수','가드레일','서울',0)", (case_no,)).lastrowid
    c.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,NULL,'원경매',0,'진행',0,0,0,"
        "       datetime('now','+9 hours','+2 hours'),?)", (cid, DB.now()))
    c.commit(); c.close()
    return cid, case_no, f"ra{n}", f"rb{n}"


def _run_concurrent_renotify(cid, case_no, u1, u2):
    """옛 워커(test_scan_round491_worker.py, 더 이상 생성 안 함)의 로직을 그대로
    옮김 — 진짜 스레드 2개가 threading.Barrier로 쿨다운 확인 SELECT 지점에
    동시 도달한 뒤 같은 사건에 재알림을 동시 호출한다."""
    cl1 = A.app.test_client()
    cl2 = A.app.test_client()
    with cl1.session_transaction() as s:
        s["admin"] = u1; s["admin_role"] = "하위관리자"; s["_csrf"] = "c1"
    with cl2.session_transaction() as s:
        s["admin"] = u2; s["admin_role"] = "하위관리자"; s["_csrf"] = "c2"

    barrier = threading.Barrier(2, timeout=5)
    hit = {"n": 0}
    hit_lock = threading.Lock()

    class _Probe:
        def __init__(self, real):
            self._real = real

        def execute(self, sql, params=()):
            if "activity_log" in sql and "공고 재알림" in sql:
                with hit_lock:
                    hit["n"] += 1
                try:
                    barrier.wait()
                except threading.BrokenBarrierError:
                    pass
            return self._real.execute(sql, params)

        def __getattr__(self, name):
            return getattr(self._real, name)

    _real_get_db = DB.get_db

    def _patched():
        return _Probe(_real_get_db())

    results = {}

    def worker(key, cl, hdr):
        r = cl.post(f"/api/cases/{cid}/renotify", headers=hdr)
        results[key] = (r.status_code, r.get_json())

    DB.get_db = _patched
    t1 = threading.Thread(target=worker, args=("t1", cl1, {"X-CSRF-Token": "c1"}))
    t2 = threading.Thread(target=worker, args=("t2", cl2, {"X-CSRF-Token": "c2"}))
    t1.start(); t2.start(); t1.join(15); t2.join(15)
    DB.get_db = _real_get_db

    conn2 = A.DB.get_db()
    n_log = conn2.execute(
        "SELECT COUNT(*) n FROM activity_log WHERE action='공고 재알림' AND detail LIKE ?",
        (f"%{case_no}%",)).fetchone()["n"]
    n_notif = conn2.execute(
        "SELECT COUNT(*) n FROM notifications WHERE case_id=? AND ntype='공고재개'",
        (cid,)).fetchone()["n"]
    conn2.close()
    success_count = sum(1 for k in ("t1", "t2")
                         if results[k][0] == 200 and (results[k][1] or {}).get("ok"))
    return {"barrier_hits": hit["n"], "success_count": success_count,
            "n_log": n_log, "n_notif": n_notif,
            "codes": [results["t1"][0], results["t2"][0]]}


try:
    cid1, case_no1, u1a, u2a = _seed_case()
    out = _run_concurrent_renotify(cid1, case_no1, u1a, u2a)
    chk(out["barrier_hits"] == 2, "두 요청 모두 쿨다운 확인 지점까지 동시 도달했다(배리어 동기화 성공)", out)
    chk(out["success_count"] == 1,
        "★★★★★ 새 코드: 진짜 동시요청이어도 단 1건만 성공한다"
        "(BEGIN IMMEDIATE가 나머지 요청을 직렬화해 신선한 쿨다운 기록을 보게 만든다)", out)
    chk(out["n_log"] == 1 and out["n_notif"] == 1,
        "★★★★★ 새 코드: 감사로그·알림이 정확히 1건만 쌓인다(중복발송 없음)", out)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 되돌림-증명 — view_functions 딕셔너리 항목만 잠깐 치환(실제 파일은 안 건드림)")
    # ──────────────────────────────────────────────────────────
    assert CURRENT_FUNC, "함수를 못 뽑아 되돌림-증명을 진행할 수 없다"
    _marker = "def api_case_renotify(cid):"
    ORIGINAL_BODY_FOR_EXEC = _marker + ORIGINAL_FUNC.split(_marker, 1)[1]
    _ns = dict(vars(A))
    exec(compile(ORIGINAL_BODY_FOR_EXEC, "<round491_reverted_api_case_renotify>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_fn = A.require_role("하위관리자")(_ns["api_case_renotify"])

    _orig_view = A.app.view_functions["api_case_renotify"]
    A.app.view_functions["api_case_renotify"] = old_fn
    try:
        cid2, case_no2, u1b, u2b = _seed_case()
        out2 = _run_concurrent_renotify(cid2, case_no2, u1b, u2b)
    finally:
        A.app.view_functions["api_case_renotify"] = _orig_view

    chk(out2["barrier_hits"] == 2, "되돌림 시나리오도 두 요청 모두 배리어에 동시 도달했다(동기화 성공)", out2)
    chk(out2["success_count"] == 2,
        "★★★★★ 옛 코드(되돌림): 진짜 동시요청 두 건이 모두 성공한다"
        " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", out2)
    chk(out2["n_log"] == 2 and out2["n_notif"] == 2,
        "★★★★★ 옛 코드(되돌림): 감사로그·알림이 2건씩(중복발송) 쌓인다", out2)

    print("\n[4] 원복 확인 — 되돌리기 이후 다시 직렬화되는가(바꿔치기가 안 샜다)")
    chk(A.app.view_functions["api_case_renotify"] is _orig_view,
        "  view_functions가 원래 함수객체로 복원됐다")
    cid3, case_no3, u1c, u2c = _seed_case()
    out3 = _run_concurrent_renotify(cid3, case_no3, u1c, u2c)
    chk(out3["success_count"] == 1,
        "★★★★ 원복 후에는 다시 단 1건만 성공한다(바꿔치기가 안 샜다)", out3)
    chk(out3["n_log"] == 1 and out3["n_notif"] == 1,
        "원복 후 감사로그·알림도 다시 1건씩이다", out3)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] 실행/되돌림-증명", f"{type(e).__name__}: {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(view_functions 딕셔너리 항목 임시치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
