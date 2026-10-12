# -*- coding: utf-8 -*-
"""스캔 507라운드 회귀 — api_campaign_cancel()(마케팅 캠페인 취소,
POST /api/campaigns/<id>/cancel)가 형제 api_campaign_create()(라운드348이
BEGIN IMMEDIATE 이식)와 달리 트랜잭션 잠금이 전혀 없던 결함.

관리자 두 명(또는 더블클릭·재시도)이 같은 캠페인을 거의 동시에(또는
순서대로 두 번) 취소하면, 상태 확인이 '발송완료'만 볼 뿐 '이미 취소됨'은
보지 않아서 매번 UPDATE·감사로그가 다시 실행돼 "마케팅 캠페인 취소"
감사로그가 중복 적재됐다(최종 status 자체는 '취소' 하나뿐이라 데이터
훼손은 아니지만 감사로그 중복이 실제로 발생 — round505의 api_partner_
delete와 같은 성격).

round505가 확립한 원칙대로 — 이 함수도 조건 없이 무조건 UPDATE하는
구조라서 잠금만으로는 부족하다. BEGIN IMMEDIATE + "이미 취소된
캠페인입니다" 재확인 둘 다 필요하다.

⚠ campaign_targets 쪽(WHERE campaign_id=? AND status='대기')은 원래부터
자기 자신의 조건부 WHERE를 갖고 있어 중복 실행에도 안전했다(둘째 실행은
0행에 적용) — 이번 라운드가 고치는 것은 정확히 campaigns.status 무조건
UPDATE와 그로 인한 감사로그 중복이다.

⚠⚠ [라운드616] 되돌림-증명 기법을 옛 세대(app.py를 실제로 디스크에
  써넣고 워커 스크립트를 서브프로세스로 돌려 재현한 뒤 복원)에서
  round488/round414/round515가 확립한 안전패턴으로 이관한다.
  api_campaign_cancel() 은 단일 라우트 핸들러라 ORIGINAL_FUNC 텍스트에서
  @app.post(...) 등록줄만 제거(@require_role 데코레이터는 그대로 둔 채
  텍스트에 남겨 exec 시 다시 입혀짐)한 사본을 실제 app 모듈의 독립 사본
  네임스페이스(dict(vars(A)))에 exec해 얻은 함수 객체로 A.app.
  view_functions 딕셔너리 항목만 잠깐 치환한다 — 진짜 app.py 파일은
  전혀 안 쓴다. threading.Barrier 동시성 프로브(예전엔
  test_scan_round507_worker.py 서브프로세스 안에서 실행)도 이 파일
  안으로 그대로 옮겨와 시나리오마다(A·B·C) 독립된 새 캠페인으로
  반복하므로 서로 오염되지 않는다 — 이 파일은 더 이상 워커를 띄우지
  않는다.
"""
import hashlib
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
print("  스캔 507라운드 회귀 — 마케팅 캠페인 취소 동시성 경합")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()
APP_HASH_BEFORE = hashlib.sha256(APP_SRC.encode("utf-8")).hexdigest()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — api_campaign_cancel() 함수 전체를 통째로 캡처")
# ──────────────────────────────────────────────────────────────
CUR_FUNC = ('''@app.post("/api/campaigns/<int:cmid>/cancel")
@require_role("중간관리자")
def api_campaign_cancel(cmid):
    """캠페인 취소.

    ⚠⚠ [라운드507] 형제(api_campaign_create, 라운드348이 BEGIN IMMEDIATE 이식)와
      달리 이 함수는 잠금이 전혀 없고, 상태 확인도 '발송완료'만 볼 뿐 '이미
      취소됨'은 보지 않았다 — 관리자 두 명(또는 더블클릭)이 같은 캠페인을
      거의 동시에(또는 순서대로 두 번) 취소하면 매번 UPDATE·감사로그가 다시
      실행돼 "마케팅 캠페인 취소" 로그가 중복 적재됐다(실측: threading.Barrier
      로 두 요청을 SELECT 지점에 강제 동시 도달시키면 둘 다 200 성공하고
      감사로그가 2건 남는다). 최종 status 자체는 '취소' 하나뿐이라 데이터
      훼손은 아니지만(라운드505의 api_partner_delete와 같은 성격), 이 함수도
      조건 없이 무조건 UPDATE하는 구조라 잠금만으로는 부족하다 — 이미
      종결상태 재확인을 별도로 더한다(settleVoid류의 원칙과 동일).
    """
    conn = DB.get_db()
    conn.execute("BEGIN IMMEDIATE")
    c = one(conn.execute("SELECT title, status FROM campaigns WHERE id=?", (cmid,)))
    if not c:
        conn.rollback(); conn.close()
        return jsonify({"ok": False, "error": "캠페인을 찾을 수 없습니다."}), 404
    if c["status"] == "발송완료":
        conn.rollback(); conn.close()
        return jsonify({"ok": False, "error": "이미 발송된 캠페인입니다."}), 409
    if c["status"] == "취소":
        conn.rollback(); conn.close()
        return jsonify({"ok": False, "error": "이미 취소된 캠페인입니다."}), 409
    conn.execute("UPDATE campaigns SET status='취소' WHERE id=?", (cmid,))
    conn.execute("UPDATE campaign_targets SET status='제외', reason='캠페인 취소' "
                 "WHERE campaign_id=? AND status='대기'", (cmid,))
    DB.log(conn, actor(), "마케팅 캠페인 취소", c["title"])
    conn.commit(); conn.close()
    return jsonify({"ok": True})''')

ORIGINAL_FUNC = ('''@app.post("/api/campaigns/<int:cmid>/cancel")
@require_role("중간관리자")
def api_campaign_cancel(cmid):
    conn = DB.get_db()
    c = one(conn.execute("SELECT title, status FROM campaigns WHERE id=?", (cmid,)))
    if not c:
        conn.close(); return jsonify({"ok": False, "error": "캠페인을 찾을 수 없습니다."}), 404
    if c["status"] == "발송완료":
        conn.close(); return jsonify({"ok": False, "error": "이미 발송된 캠페인입니다."}), 409
    conn.execute("UPDATE campaigns SET status='취소' WHERE id=?", (cmid,))
    conn.execute("UPDATE campaign_targets SET status='제외', reason='캠페인 취소' "
                 "WHERE campaign_id=? AND status='대기'", (cmid,))
    DB.log(conn, actor(), "마케팅 캠페인 취소", c["title"])
    conn.commit(); conn.close()
    return jsonify({"ok": True})''')

chk(APP_SRC.count(CUR_FUNC) == 1, "api_campaign_cancel() 현재 함수 전체가 소스에 유일하다", APP_SRC.count(CUR_FUNC))
chk("BEGIN IMMEDIATE" not in ORIGINAL_FUNC, "원본 대조 함수에는 잠금이 없다(대조군)")
chk("이미 취소된 캠페인" not in ORIGINAL_FUNC, "원본 대조 함수에는 '이미 취소' 재확인이 없다(대조군)")
chk(ORIGINAL_FUNC != CUR_FUNC, "대조군과 현재 코드가 실제로 다르다")

#  exec용 되돌림판 — @app.post(...) 등록줄만 제거(재등록 시도로 Flask가
#  AssertionError를 던지는 것을 막는다), @require_role 데코레이터는 텍스트에
#  그대로 남겨 exec 시 다시 입혀지게 한다(round488/515와 같은 원칙).
ORIGINAL_BODY_FOR_EXEC = ORIGINAL_FUNC.split("\n", 1)[1]
chk(ORIGINAL_BODY_FOR_EXEC.startswith('@require_role("중간관리자")'),
    "되돌림판 exec용 본문이 @require_role 데코레이터부터 정확히 시작한다(@app.post 줄만 제거)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 준비 — 스크래치 DB")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="r507_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB                 # noqa: E402
DB.init_db()
import app as A                  # noqa: E402

_conn0 = DB.get_db()
_conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                "VALUES('a1507','x','n1','중간관리자')")
_conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                "VALUES('a2507','x','n2','중간관리자')")
_conn0.commit(); _conn0.close()


def _run_concurrent_cancel(tag):
    """새 캠페인을 만들고 두 관리자 세션이 threading.Barrier로 강제 동시
    도달하며 취소를 시도하게 한 뒤 결과를 반환한다(라운드505·506이 확립한
    지연주입 프로브 기법과 같은 계열)."""
    conn = DB.get_db()
    camp_id = conn.execute(
        "INSERT INTO campaigns(title,channel,status,total_count,created_by,created_at,queued_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (f"테스트캠페인{tag}", "메일", "발송대기", 1, "seed", DB.now(), DB.now())).lastrowid
    conn.execute("INSERT INTO campaign_targets(campaign_id,partner_id,name,contact,status,created_at) "
                 "VALUES(?,?,?,?,?,?)", (camp_id, 1, "p1", "p1@x.com", "대기", DB.now()))
    conn.commit(); conn.close()

    cl1 = A.app.test_client()
    cl2 = A.app.test_client()
    with cl1.session_transaction() as s:
        s["admin"] = "a1507"; s["admin_role"] = "중간관리자"; s["_csrf"] = "c1"
    with cl2.session_transaction() as s:
        s["admin"] = "a2507"; s["admin_role"] = "중간관리자"; s["_csrf"] = "c2"

    #  ⚠ 새 코드(BEGIN IMMEDIATE가 이 SELECT 바로 앞에 붙음)에서는 두 번째
    #    스레드가 자기 자신의 BEGIN IMMEDIATE에서 먼저 막혀 이 SELECT에 함께
    #    못 오는 경우가 많다 — 그러면 바리어가 5초 뒤 깨지고(BrokenBarrierError)
    #    첫 스레드 혼자 진행한 뒤 잠금이 풀리며 둘째 스레드가 뒤늦게 도착한다.
    #    이건 결함이 아니라 잠금이 정확히 의도대로 두 스레드를 떼어놓았다는 증거다.
    barrier = threading.Barrier(2, timeout=5)
    hit = {"n": 0}
    hit_lock = threading.Lock()

    class _Probe:
        def __init__(self, real):
            self._real = real

        def execute(self, sql, params=()):
            if sql == "SELECT title, status FROM campaigns WHERE id=?":
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
        r = cl.post(f"/api/campaigns/{camp_id}/cancel", json={}, headers=hdr)
        results[key] = (r.status_code, (r.get_json() or {}).get("ok"))

    DB.get_db = _patched
    A.DB.get_db = _patched
    t1 = threading.Thread(target=worker, args=("t1", cl1, {"X-CSRF-Token": "c1"}))
    t2 = threading.Thread(target=worker, args=("t2", cl2, {"X-CSRF-Token": "c2"}))
    t1.start(); t2.start(); t1.join(15); t2.join(15)
    DB.get_db = _real_get_db
    A.DB.get_db = _real_get_db

    conn = A.DB.get_db()
    log_n = conn.execute(
        "SELECT COUNT(*) n FROM activity_log WHERE action='마케팅 캠페인 취소' AND detail=?",
        (f"테스트캠페인{tag}",)).fetchone()[0]
    final_status = conn.execute("SELECT status FROM campaigns WHERE id=?", (camp_id,)).fetchone()[0]
    excluded_n = conn.execute(
        "SELECT COUNT(*) n FROM campaign_targets WHERE campaign_id=? AND status='제외'",
        (camp_id,)).fetchone()[0]
    conn.close()
    return {
        "barrier_hits": hit["n"],
        "r1": list(results.get("t1", (None, None))),
        "r2": list(results.get("t2", (None, None))),
        "activity_log_count": log_n,
        "final_status": final_status,
        "excluded_targets": excluded_n,
    }


try:
    print("\n[3] 실행 — threading.Barrier로 실제 동시 취소 재현(현재/고쳐진 코드)")
    out = _run_concurrent_cancel("A")
    chk(out["barrier_hits"] >= 1, "두 요청 중 적어도 하나는 실제로 그 지점에 도달했다(경합 시도 자체는 성립)", out)
    chk([out["r1"], out["r2"]].count([200, True]) == 1,
        "★★★★★ 새 코드: 동시 취소 요청 중 정확히 하나만 성공한다", out)
    chk([out["r1"], out["r2"]].count([409, False]) == 1,
        "★★★★★ 새 코드: 나머지 하나는 '이미 취소됨' 409로 정확히 막힌다", out)
    chk(out["activity_log_count"] == 1,
        "★★★★★ 새 코드: '마케팅 캠페인 취소' 감사로그가 정확히 1건만 남는다(중복 없음)", out)
    chk(out["final_status"] == "취소", "최종 상태는 정상적으로 '취소'이다(회귀 아님)", out)
    chk(out["excluded_targets"] == 1, "캠페인 대상 1건도 정상적으로 '제외'로 처리된다(회귀 아님)", out)

    # ══════════════════════════════════════════════════════════
    print("\n[4] 되돌림-증명 — view_functions 딕셔너리 항목만 잠깐 치환(실제 파일은 안 건드림)")
    # ──────────────────────────────────────────────────────────
    _ns = dict(vars(A))
    exec(compile(ORIGINAL_BODY_FOR_EXEC, "<round507_reverted_campaign_cancel>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_fn = _ns["api_campaign_cancel"]  # ORIGINAL_BODY_FOR_EXEC 안의 @require_role이 이미 입혔다

    _orig_view = A.app.view_functions["api_campaign_cancel"]
    A.app.view_functions["api_campaign_cancel"] = old_fn
    try:
        out2 = _run_concurrent_cancel("B")
    finally:
        A.app.view_functions["api_campaign_cancel"] = _orig_view

    chk([out2["r1"], out2["r2"]].count([200, True]) == 2,
        "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림): 동시 취소 요청 둘 다 200으로 성공해버린다", out2)
    chk(out2["activity_log_count"] == 2,
        "★★★★★ 옛 코드(되돌림): '마케팅 캠페인 취소' 감사로그가 실제로 2건 생긴다 — "
        "이 테스트가 진짜 결함(중복 감사로그)을 잡아낼 능력이 있음을 증명", out2)
    chk(out2["final_status"] == "취소", "옛 코드도 최종 상태 자체는 '취소'다(데이터 훼손은 아님, 부작용만 중복)", out2)

    print("\n[5] 원복 확인 — 되돌리기 이후 다시 잠기는가(바꿔치기가 안 샜다)")
    chk(A.app.view_functions["api_campaign_cancel"] is _orig_view,
        "  view_functions가 원래 함수객체로 복원됐다")
    out3 = _run_concurrent_cancel("C")
    chk([out3["r1"], out3["r2"]].count([200, True]) == 1,
        "★★★★ 원복 후에는 다시 동시 취소 중 하나만 성공한다(바꿔치기가 안 샜다)", out3)
    chk(out3["activity_log_count"] == 1,
        "★★★★ 원복 후에는 감사로그도 다시 1건뿐이다", out3)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[3]+[4] 실행/되돌림-증명", f"{type(e).__name__}: {e}")

APP_HASH_AFTER = hashlib.sha256(io.open(APP_PATH, encoding="utf-8").read().encode("utf-8")).hexdigest()
chk(APP_HASH_AFTER == APP_HASH_BEFORE,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(view_functions 딕셔너리 항목 임시치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
