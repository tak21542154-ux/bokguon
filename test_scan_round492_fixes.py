# -*- coding: utf-8 -*-
"""스캔 492라운드 회귀 — change_orders(변경견적) 생애주기 가시성 결함 2건.

①api_co_full_reauction()의 MAX_CO_ROUND 소진("최종유찰" 확정) 분기에
  감사로그·통지가 전혀 없던 결함 — 같은 함수의 성공분기(전체 재경매 오픈)와
  형제 dispatch.py(회차소진→'수배실패', 840-848행)는 둘 다 DB.log를 남기는데
  이 자리만 없었다.
②TODAY_BLOCKED("오늘 할 일") 목록의 "변경 견적이 결정을 기다립니다" 항목이
  '거절'·'유찰' 상태만 잡고, 원업체가 응답하지 않는 '원업체제안' 상태는
  전혀 안 잡던 결함 — change_orders에는 응답기한 컬럼도, 그걸 보는 스윕도
  없어(sweep_* 8개 전수확인, 0건) 원업체가 알림을 놓치면 이 사건은
  정산·재배정 둘 다 막힌 채(CHANGE_ORDER_ACTIVE) 대시보드 어디에도 안 뜨고
  무기한 방치될 수 있었다.

두 결함 모두 정밀조사 Agent가 발견 → 이 세션이 직접 Read로 재확인하고
Agent의 재현 스크립트를 독립 재실행해 같은 결과를 확인한 뒤 수정했다.

[라운드624] on-disk 되돌리기(app.py에 직접 쓰고, 매번 새로 생성하는 전용
서브프로세스 워커 스크립트 test_scan_round492_worker.py로 별도 스크래치
DB까지 새로 차려 재현)를 인메모리로 이관. ①은 @require_role("중간관리자")가
달린 단일 Flask 라우트 핸들러라 view_functions 딕셔너리 항목만 잠깐
치환(기법1, round417/422/466 정착). ②는 평범한 모듈 top-level 리스트
(상수)라 exec조차 필요 없이 항목 하나(SQL 필드만)를 직접 스왑한다(기법5).
실제 파일은 전혀 안 건드리고, 워커 스크립트도 더는 필요 없어 삭제했다.
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(c, n, d=""):
    (PASS if c else FAIL).append((n, d))
    print(("  [OK]   " if c else "  [FAIL] ") + n + ("" if c else f"   {d}"))


print("=" * 72)
print("  스캔 492라운드 회귀 — 변경견적 생애주기 가시성 결함 2건")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
# ① 최종유찰 로그+통지 — 순수 삽입(원본코드 제거 없음)이라 통짜 제거로 되돌린다.
_a = APP_SRC.find('        #  ⚠⚠ [라운드492] 바로 아래 성공분기')
_marker1 = '               audience_type="admin", case_id=co["case_id"])\n'
_b = APP_SRC.find(_marker1, _a)
_b = _b + len(_marker1) if _b > 0 else -1
BLOCK1 = APP_SRC[_a:_b] if _a > 0 and _b > _a else ""

chk(bool(BLOCK1) and "DB.log" in BLOCK1 and "notify(" in BLOCK1,
    "① 최종유찰 분기에 DB.log+notify 블록을 찾았다")
chk(APP_SRC.count(BLOCK1) == 1, "① 블록이 소스에 유일하다", APP_SRC.count(BLOCK1) if BLOCK1 else 0)

# ② 대시보드 조건 확장 — TODAY_BLOCKED 튜플의 SQL(4번째 필드)만 옛 값으로 되돌린다.
_c = APP_SRC.find("    #  ⚠⚠ [라운드492] '원업체제안'(원업체 응답 대기)은")
_marker2 = '                WHERE c.id=co.case_id AND COALESCE(c.is_demo,0)=0)"),\n'
_d = APP_SRC.find(_marker2, _c)
_d = _d + len(_marker2) if _d > 0 else -1
BLOCK2 = APP_SRC[_c:_d] if _c > 0 and _d > _c else ""

ORIGINAL_BLOCK2_SQL = (
    "SELECT COUNT(*) FROM change_orders co "
    " WHERE co.status IN ('거절','유찰') "
    "   AND EXISTS (SELECT 1 FROM cases c "
    "                WHERE c.id=co.case_id AND COALESCE(c.is_demo,0)=0)")

chk(bool(BLOCK2) and "원업체제안" in BLOCK2, "② 대시보드 조건 확장 블록을 찾았다")
chk(APP_SRC.count(BLOCK2) == 1, "② 블록이 소스에 유일하다", APP_SRC.count(BLOCK2) if BLOCK2 else 0)
chk("원업체제안" not in ORIGINAL_BLOCK2_SQL, "원본 SQL에는 '원업체제안' 조건이 없다(대조군)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 Flask 앱 — 인메모리(서브프로세스 없음)")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="r492_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "v.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "u")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)


def _py_fn_body(src, fn_name):
    """함수 본문 — 다음 def뿐 아니라 다음 라우트의 @app. 데코레이터가 먼저
    나오면 거기서 자른다(round610 정착 기법)."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


try:
    import db as DB
    DB.init_db()
    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('a1','x','n1','중간관리자')")
    pid = conn.execute("INSERT INTO partners(name) VALUES('원업체')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,partner_id,is_demo,created_at) "
        "VALUES('R492-1','시공중',?,0,?)", (pid, DB.now())).lastrowid
    # ① MAX_CO_ROUND(3)에 도달한 변경건 — 4차 시도하면 최종유찰
    coid1 = conn.execute(
        "INSERT INTO change_orders(case_id,round,incumbent_partner_id,incumbent_amount,"
        "    combined_amount,status,created_at) VALUES(?,3,?,10000000,12000000,'유찰',?)",
        (cid, pid, DB.now())).lastrowid
    # 대조군: 정상(1차) 변경건 하나 더 생성 — 성공분기가 여전히 log를 남기는지 확인용
    cid_ctrl = conn.execute(
        "INSERT INTO cases(case_no,status,partner_id,is_demo,created_at) "
        "VALUES('R492-CTRL','시공중',?,0,?)", (pid, DB.now())).lastrowid
    coid_ctrl = conn.execute(
        "INSERT INTO change_orders(case_id,round,incumbent_partner_id,incumbent_amount,"
        "    combined_amount,status,created_at) VALUES(?,1,?,10000000,12000000,'거절',?)",
        (cid_ctrl, pid, DB.now())).lastrowid
    # ② 원업체제안 2건 — 하나는 방금(0일), 하나는 3일 전
    cid_fresh = conn.execute(
        "INSERT INTO cases(case_no,status,partner_id,is_demo,created_at) "
        "VALUES('R492-FRESH','시공중',?,0,?)", (pid, DB.now())).lastrowid
    conn.execute(
        "INSERT INTO change_orders(case_id,round,incumbent_partner_id,combined_amount,"
        "    status,created_at) VALUES(?,1,?,12000000,'원업체제안',?)",
        (cid_fresh, pid, DB.now()))
    cid_stale = conn.execute(
        "INSERT INTO cases(case_no,status,partner_id,is_demo,created_at) "
        "VALUES('R492-STALE','시공중',?,0,"
        "datetime('now','+9 hours','-3 days'))", (pid,)).lastrowid
    conn.execute(
        "INSERT INTO change_orders(case_id,round,incumbent_partner_id,combined_amount,"
        "    status,created_at) VALUES(?,1,?,12000000,'원업체제안',"
        "datetime('now','+9 hours','-3 days'))", (cid_stale, pid))
    conn.commit()
    conn.close()

    import app as A

    def _admin_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["admin"] = "a1"; sess["admin_role"] = "중간관리자"; sess["_csrf"] = "c1"
        return c

    hdr = {"X-CSRF-Token": "c1"}
    cl = _admin_client()

    r_ctrl = cl.post(f"/api/change-orders/{coid_ctrl}/full-reauction", json={}, headers=hdr)
    conn = A.DB.get_db()
    n_log_ctrl = conn.execute(
        "SELECT COUNT(*) n FROM activity_log WHERE action='전체 재경매 오픈'").fetchone()["n"]
    conn.close()
    chk(bool((r_ctrl.get_json() or {}).get("ok")) and n_log_ctrl == 1,
        "대조군: 정상 성공분기(1차→2차)는 여전히 감사로그 1건을 남긴다(회귀 없음)",
        (r_ctrl.status_code, n_log_ctrl))

    r1 = cl.post(f"/api/change-orders/{coid1}/full-reauction", json={}, headers=hdr)
    j1 = r1.get_json()
    conn = A.DB.get_db()
    co1_status = conn.execute(
        "SELECT status FROM change_orders WHERE id=?", (coid1,)).fetchone()["status"]
    n_log1 = conn.execute(
        "SELECT COUNT(*) n FROM activity_log WHERE detail LIKE '%R492-1 %'").fetchone()["n"]
    n_notif1 = conn.execute(
        "SELECT COUNT(*) n FROM notifications WHERE case_id=?", (cid,)).fetchone()["n"]
    conn.close()
    chk(r1.status_code == 409 and (j1 or {}).get("code") == "MAX_ROUND",
        "MAX_CO_ROUND 소진 시 여전히 409/MAX_ROUND를 반환한다(동작 안 바뀜)", (r1.status_code, j1))
    chk(co1_status == "최종유찰", "change_orders.status가 '최종유찰'로 굳는다", co1_status)
    chk(n_log1 == 1,
        "★★★★★ 새 코드: '최종유찰' 확정 시 감사로그가 정확히 1건 남는다"
        "(이전엔 0건이었다 — 조사 에이전트 재현과 일치)", n_log1)
    chk(n_notif1 == 1,
        "★★★★★ 새 코드: '최종유찰' 확정 시 통지가 정확히 1건 간다(이전엔 0건)", n_notif1)

    # TODAY_BLOCKED — 대시보드가 실제로 쓰는 그 리스트에서 SQL을 직접 찾아 실행
    _idx2 = next(i for i, t in enumerate(A.TODAY_BLOCKED)
                 if t[0] == "변경 견적이 결정을 기다립니다")
    _orig_tuple2 = A.TODAY_BLOCKED[_idx2]

    def _blocked_count():
        c2 = A.DB.get_db()
        n = c2.execute(A.TODAY_BLOCKED[_idx2][3]).fetchone()[0]
        c2.close()
        return n

    blocked_count = _blocked_count()
    chk(blocked_count == 1,
        "★★★★★ 새 코드: 오늘할일 '변경 견적이 결정을 기다립니다'가 "
        "3일 방치된 원업체제안 1건만 잡는다(방금 생긴 원업체제안은 안 잡음, "
        "거절 상태 변경건은 이미 2차로 넘어가 카운트에서 빠짐)", blocked_count)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 되돌림-증명 — ① view_functions 스왑, ② 리스트 항목 직접 스왑")
    # ──────────────────────────────────────────────────────────
    # ① api_co_full_reauction() 은 @require_role("중간관리자") 가 달린 단일
    #   Flask 라우트 핸들러다 — view_functions 딕셔너리 항목만 잠깐 치환한다.
    _body492 = _py_fn_body(APP_SRC, "api_co_full_reauction")
    chk(BLOCK1 in _body492, "  (준비) api_co_full_reauction() 본문 안에 BLOCK1이 있다")
    _old_body492 = (_body492
                    .replace("def api_co_full_reauction(coid):",
                             "def _api_co_full_reauction_pre492(coid):", 1)
                    .replace(BLOCK1, "", 1))
    chk("_api_co_full_reauction_pre492" in _old_body492 and BLOCK1 not in _old_body492,
        "  (준비) 함수 리네임 + BLOCK1 제거가 정확히 적용됐다(실제 파일은 안 건드림)")

    _ns492 = dict(vars(A))
    exec(compile(_old_body492, "<round492_pre492_co_full_reauction>", "exec"), _ns492)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_reauction_fn = A.require_role("중간관리자")(_ns492["_api_co_full_reauction_pre492"])

    #  coid1은 이미 '최종유찰'로 굳어 재사용 불가(그 상태에선 애초에 라우트
    #  맨 앞의 상태검사에서 바로 409로 막혀 MAX_ROUND 분기 자체에 도달 못 한다) —
    #  같은 모양(3차·유찰)의 새 사건을 하나 더 만든다.
    conn = A.DB.get_db()
    cid1b = conn.execute(
        "INSERT INTO cases(case_no,status,partner_id,is_demo,created_at) "
        "VALUES('R492-1B','시공중',?,0,?)", (pid, DB.now())).lastrowid
    coid1b = conn.execute(
        "INSERT INTO change_orders(case_id,round,incumbent_partner_id,incumbent_amount,"
        "    combined_amount,status,created_at) VALUES(?,3,?,10000000,12000000,'유찰',?)",
        (cid1b, pid, DB.now())).lastrowid
    conn.commit()
    conn.close()

    _orig_view492 = A.app.view_functions["api_co_full_reauction"]
    A.app.view_functions["api_co_full_reauction"] = old_reauction_fn
    try:
        r_old = cl.post(f"/api/change-orders/{coid1b}/full-reauction", json={}, headers=hdr)
    finally:
        A.app.view_functions["api_co_full_reauction"] = _orig_view492

    conn = A.DB.get_db()
    n_log1b = conn.execute(
        "SELECT COUNT(*) n FROM activity_log WHERE detail LIKE '%R492-1B%'").fetchone()["n"]
    n_notif1b = conn.execute(
        "SELECT COUNT(*) n FROM notifications WHERE case_id=?", (cid1b,)).fetchone()["n"]
    conn.close()
    chk(r_old.status_code == 409 and n_log1b == 0 and n_notif1b == 0,
        "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림): '최종유찰' 확정에도 "
        "감사로그·통지가 0건 — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
        (r_old.status_code, n_log1b, n_notif1b))
    chk(A.app.view_functions["api_co_full_reauction"] is _orig_view492,
        "  view_functions가 원래 함수객체로 복원됐다")

    # ② TODAY_BLOCKED 항목의 SQL 필드만 옛 값으로 잠깐 스왑(제목 등 나머지는
    #   현재 값 그대로 — 인과관계를 검증할 유일한 변수는 SQL 뿐이다).
    _old_tuple2 = _orig_tuple2[:3] + (ORIGINAL_BLOCK2_SQL,)
    A.TODAY_BLOCKED[_idx2] = _old_tuple2
    try:
        old_blocked_count = _blocked_count()
    finally:
        A.TODAY_BLOCKED[_idx2] = _orig_tuple2
    chk(old_blocked_count == 0,
        "★★★★★ 옛 코드(되돌림): 3일 방치된 원업체제안도 오늘할일에 전혀 안 잡힌다",
        old_blocked_count)
    chk(A.TODAY_BLOCKED[_idx2] == _orig_tuple2,
        "  TODAY_BLOCKED 항목이 원래 튜플로 복원됐다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] 실행/되돌림-증명", f"{type(e).__name__}: {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
