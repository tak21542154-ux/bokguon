# -*- coding: utf-8 -*-
"""스캔 505라운드 회귀 — api_partner_delete()(협력사 퇴출, DELETE /api/
partners/<id>)가 형제 api_partner_update()(PATCH, 같은 partners.status
컬럼, 라운드493이 BEGIN IMMEDIATE 이식)와 달리 잠금이 전혀 없던 결함.

관리자 두 명(또는 재시도)이 같은 업체에게 거의 동시에 퇴출을 실행하면
둘 다 200을 받아, 협력사에게 "등록이 퇴출로 변경되었습니다" 알림톡이
두 번 나가고 감사로그도 중복됐다(최종 status 자체는 '퇴출' 하나뿐이라
데이터 훼손은 아니지만 알림 비용·감사로그 중복이 실제로 발생).

잠금만으로는 부족하다 — 두 번째 요청이 락을 얻은 뒤에도 원래 코드는
"이미 퇴출됨"을 확인하지 않고 그대로 다시 UPDATE·통지를 실행하므로,
BEGIN IMMEDIATE + "이미 퇴출된 업체입니다" 재확인 둘 다 필요하다.

라운드504의 "형제 분기 방어 비대칭"을 함수 내부 분기가 아니라 같은
자원(partners.status)을 쓰는 두 형제 엔드포인트(PATCH/DELETE) 사이로
확장한 사례.

⚠⚠ [라운드621] 되돌림-증명 기법을 옛 세대(app.py를 실제로 디스크에 써넣고
별도 워커 서브프로세스를 두 번 돌린 뒤 복원)에서 round488/507이 확립한
안전패턴으로 이관한다. api_partner_delete()는 단일 라우트 핸들러라
ORIGINAL_FUNC 텍스트(데코레이터 제거)를 exec로 독립 사본 네임스페이스에
재구성해 A.app.view_functions 딕셔너리 항목만 잠깐 치환한다 — 진짜 app.py
파일은 전혀 안 쓴다. 동시성 재현(threading.Barrier + _Probe로 DB.get_db()를
감싸 UPDATE 문 도달을 강제)은 옛 워커(test_scan_round505_worker.py, 삭제됨)의
로직을 그대로 옮겨 같은 프로세스 안에서 세 번(현재 코드·되돌린 코드·원복
후) 호출한다.
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
print("  스캔 505라운드 회귀 — 협력사 퇴출(DELETE) 동시성 경합")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — api_partner_delete() 함수 전체를 통째로 캡처")
# ──────────────────────────────────────────────────────────────
CUR_FUNC = ('''@app.delete("/api/partners/<int:pid>")
#  ⚠ 퇴출은 그 업체의 매출을 끊고 통지까지 나가는, 되돌리기 어려운 조치다.
@require_role("중간관리자")
def api_partner_delete(pid):
    conn = DB.get_db()
    try:
        #  ⚠⚠ [라운드505] 형제(api_partner_update, 라운드493 — 같은 partners.status
        #    컬럼)는 이미 BEGIN IMMEDIATE로 잠그는데 이 자리(퇴출)만 잠금이 없었다
        #    — 관리자 두 명(또는 재시도)이 같은 업체에게 거의 동시에 퇴출을
        #    실행하면 둘 다 200을 받고 협력사에게 "등록이 퇴출로 변경되었습니다"
        #    알림톡이 두 번 나가고 감사로그도 중복됨을 threading.Barrier로 실측
        #    확인(최종 status 자체는 '퇴출' 하나뿐이라 데이터 훼손은 아니지만
        #    알림 비용·감사로그가 중복된다). 잠금 + "이미 퇴출됨" 재확인 둘 다
        #    있어야 한다 — 잠금만으론 두 번째 요청이 락을 얻은 뒤에도 그대로
        #    다시 UPDATE·통지를 실행하기 때문.
        conn.execute("BEGIN IMMEDIATE")
        blocked = _partner_demote_gate(conn, pid, "퇴출",
                                      request.args.get("confirm") in ("1", "true"))
        if blocked:
            conn.rollback()
            return blocked
        prev = one(conn.execute("SELECT name, status FROM partners WHERE id=?", (pid,)))
        if not prev:
            conn.rollback()
            return jsonify({"ok": False, "error": "없는 업체입니다."}), 404
        if prev["status"] == "퇴출":
            conn.rollback()
            return jsonify({"ok": False, "error": "이미 퇴출된 업체입니다."}), 409
        reason = (request.args.get("reason") or "").strip()[:300]  # [331라운드] status_reason과 동일 관례
        if len(reason) < 5:
            conn.rollback()
            return jsonify({"ok": False, "code": "NEED_REASON",
                            "error": "퇴출 사유를 5자 이상 적어 주세요. 사유는 업체에게도 통지됩니다."}), 400
        conn.execute("UPDATE partners SET status='퇴출', status_reason=?, "
                     "status_changed_at=datetime('now','+9 hours'), status_changed_by=? WHERE id=?",
                     (reason, actor(), pid))
        DB.log(conn, actor(), "업체 퇴출", f"#{pid} (사유: {reason})")
        notify(conn, "업체상태변경", "알림톡", prev["name"] or "",
               f"협력사 등록이 '퇴출'로 변경되었습니다. 사유: {reason}",
               audience_type="partner", partner_id=pid, url="/app/partner")
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()''')

ORIGINAL_FUNC = ('''@app.delete("/api/partners/<int:pid>")
#  ⚠ 퇴출은 그 업체의 매출을 끊고 통지까지 나가는, 되돌리기 어려운 조치다.
@require_role("중간관리자")
def api_partner_delete(pid):
    conn = DB.get_db()
    try:
        blocked = _partner_demote_gate(conn, pid, "퇴출",
                                      request.args.get("confirm") in ("1", "true"))
        if blocked:
            return blocked
        prev = one(conn.execute("SELECT name, status FROM partners WHERE id=?", (pid,)))
        if not prev:
            return jsonify({"ok": False, "error": "없는 업체입니다."}), 404
        reason = (request.args.get("reason") or "").strip()[:300]  # [331라운드] status_reason과 동일 관례
        if len(reason) < 5:
            return jsonify({"ok": False, "code": "NEED_REASON",
                            "error": "퇴출 사유를 5자 이상 적어 주세요. 사유는 업체에게도 통지됩니다."}), 400
        conn.execute("UPDATE partners SET status='퇴출', status_reason=?, "
                     "status_changed_at=datetime('now','+9 hours'), status_changed_by=? WHERE id=?",
                     (reason, actor(), pid))
        DB.log(conn, actor(), "업체 퇴출", f"#{pid} (사유: {reason})")
        notify(conn, "업체상태변경", "알림톡", prev["name"] or "",
               f"협력사 등록이 '퇴출'로 변경되었습니다. 사유: {reason}",
               audience_type="partner", partner_id=pid, url="/app/partner")
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()''')

chk(APP_SRC.count(CUR_FUNC) == 1, "api_partner_delete() 현재 함수 전체가 소스에 유일하다", APP_SRC.count(CUR_FUNC))
chk("BEGIN IMMEDIATE" not in ORIGINAL_FUNC, "원본 대조 함수에는 잠금이 없다(대조군)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 준비 — 스크래치 DB + threading.Barrier로 실제 동시 DELETE 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round505_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB                 # noqa: E402
DB.init_db()
import app as A                 # noqa: E402

_seed_n = [0]


def _seed_partner():
    """옛 워커의 시드 로직 — 매 시나리오(현재/되돌림/원복)마다 독립된
    관리자·업체를 새로 만들어 세 번의 호출이 서로 간섭하지 않게 한다."""
    _seed_n[0] += 1
    n = _seed_n[0]
    c = DB.get_db()
    c.execute("INSERT INTO admins(username,password_hash,name,role) "
              f"VALUES('a{n}1','x','n1','최고관리자')")
    c.execute("INSERT INTO admins(username,password_hash,name,role) "
              f"VALUES('a{n}2','x','n2','최고관리자')")
    pid = c.execute("INSERT INTO partners(name,status,phone) "
                     f"VALUES('C상사{n}','활성','01000000000')").lastrowid
    c.commit(); c.close()
    return pid, f"a{n}1", f"a{n}2"


def _run_concurrent_delete(pid, u1, u2):
    """api_partner_delete()의 유일한 쓰기지점(UPDATE ... SET status='퇴출')에
    threading.Barrier를 걸어 두 요청이 같은 순간에 그 실행에 도달하도록
    강제한다(옛 워커 test_scan_round505_worker.py의 로직을 그대로 옮김)."""
    cl1 = A.app.test_client()
    cl2 = A.app.test_client()
    with cl1.session_transaction() as s:
        s["admin"] = u1; s["admin_role"] = "최고관리자"; s["_csrf"] = "c1"
    with cl2.session_transaction() as s:
        s["admin"] = u2; s["admin_role"] = "최고관리자"; s["_csrf"] = "c2"

    barrier = threading.Barrier(2, timeout=5)
    hit = {"n": 0}
    hit_lock = threading.Lock()

    class _Probe:
        def __init__(self, real):
            self._real = real

        def execute(self, sql, params=()):
            if "SET status='퇴출'" in sql:
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
        r = cl.delete(f"/api/partners/{pid}?reason=" + "무등록%20확인됨", headers=hdr)
        results[key] = (r.status_code, (r.get_json() or {}).get("ok"))

    DB.get_db = _patched
    A.DB.get_db = _patched
    t1 = threading.Thread(target=worker, args=("t1", cl1, {"X-CSRF-Token": "c1"}))
    t2 = threading.Thread(target=worker, args=("t2", cl2, {"X-CSRF-Token": "c2"}))
    t1.start(); t2.start(); t1.join(15); t2.join(15)
    DB.get_db = _real_get_db
    A.DB.get_db = _real_get_db

    conn = A.DB.get_db()
    notif_n = conn.execute(
        "SELECT COUNT(*) n FROM notifications WHERE ntype='업체상태변경' AND partner_id=?",
        (pid,)).fetchone()[0]
    log_n = conn.execute(
        "SELECT COUNT(*) n FROM activity_log WHERE action='업체 퇴출' AND detail LIKE ?",
        (f"#{pid}%",)).fetchone()[0]
    final_status = conn.execute("SELECT status FROM partners WHERE id=?", (pid,)).fetchone()[0]
    conn.close()
    return {
        "barrier_hits": hit["n"],
        "r1": list(results.get("t1", (None, None))),
        "r2": list(results.get("t2", (None, None))),
        "notify_count": notif_n,
        "activity_log_count": log_n,
        "final_status": final_status,
    }


try:
    pid1, u11, u12 = _seed_partner()
    out = _run_concurrent_delete(pid1, u11, u12)
    chk(out["barrier_hits"] >= 1, "두 요청 중 적어도 하나는 실제로 그 지점에 도달했다(경합 시도 자체는 성립)", out)
    chk((out["r1"], out["r2"]).count([200, True]) == 1,
        "★★★★★ 새 코드: 동시 퇴출 요청 중 정확히 하나만 성공한다", out)
    chk(out["notify_count"] == 1,
        "★★★★★ 새 코드: 협력사에게 퇴출 알림톡이 정확히 1번만 나간다(중복 통지 없음)", out)
    chk(out["activity_log_count"] == 1,
        "★★★★★ 새 코드: 감사로그도 정확히 1건만 남는다(중복 없음)", out)
    chk(out["final_status"] == "퇴출", "최종 상태는 정상적으로 '퇴출'이다(회귀 아님)", out)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 되돌림-증명 — view_functions 딕셔너리 항목만 잠깐 치환(실제 파일은 안 건드림)")
    # ──────────────────────────────────────────────────────────
    _marker = "def api_partner_delete(pid):"
    ORIGINAL_BODY_FOR_EXEC = _marker + ORIGINAL_FUNC.split(_marker, 1)[1]
    _ns = dict(vars(A))
    exec(compile(ORIGINAL_BODY_FOR_EXEC, "<round505_reverted_partner_delete>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_fn = A.require_role("중간관리자")(_ns["api_partner_delete"])

    _orig_view = A.app.view_functions["api_partner_delete"]
    A.app.view_functions["api_partner_delete"] = old_fn
    try:
        pid2, u21, u22 = _seed_partner()
        out2 = _run_concurrent_delete(pid2, u21, u22)
    finally:
        A.app.view_functions["api_partner_delete"] = _orig_view

    chk((out2["r1"], out2["r2"]).count([200, True]) == 2,
        "★★★★★ 옛 코드(되돌림): 동시 퇴출 요청 둘 다 200으로 성공해버린다", out2)
    chk(out2["notify_count"] == 2,
        "★★★★★ 옛 코드(되돌림): 협력사에게 퇴출 알림톡이 실제로 2번 나간다 — "
        "이 테스트가 진짜 결함(중복 통지·중복 감사로그)을 잡아낼 능력이 있음을 증명", out2)
    chk(out2["activity_log_count"] == 2,
        "★★★★★ 옛 코드(되돌림): 감사로그도 실제로 2건 생긴다", out2)

    print("\n[4] 원복 확인 — 되돌리기 이후 다시 잠기는가(바꿔치기가 안 샜다)")
    chk(A.app.view_functions["api_partner_delete"] is _orig_view,
        "  view_functions가 원래 함수객체로 복원됐다")
    pid3, u31, u32 = _seed_partner()
    out3 = _run_concurrent_delete(pid3, u31, u32)
    chk((out3["r1"], out3["r2"]).count([200, True]) == 1,
        "★★★★ 원복 후에는 다시 동시 요청 중 하나만 성공한다(바꿔치기가 안 샜다)", out3)
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
