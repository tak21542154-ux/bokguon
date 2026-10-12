# -*- coding: utf-8 -*-
"""스캔 490라운드 회귀 — api_case_remind_report()(완료보고 독촉)에 형제
(api_settlement_remind_approval, 라운드85)와 같은 BEGIN IMMEDIATE+24시간
쿨다운이 없던 결함. 빠른 더블클릭만으로 같은 시공사에게 실제 유료
알림톡(notify 의 channel="알림톡"→상태 '발송대기', 팝빌이
sweep_send_notifications 로 실제 발송)이 중복 발송됐다.

⚠ 이 라운드의 수정은 함수 안 다섯 곳(①BEGIN IMMEDIATE 삽입 ②③④기존
세 개의 조기 return 각각에 conn.rollback() 추가 ⑤쿨다운 검사 블록 삽입)에
흩어져 있어, 개별 블록 추출·제거로는 안전하게 되돌릴 수 없다(라운드488이
겪은 "블록 사이 원본코드" 문제의 더 심한 버전). 그 대신 함수 전체를
통째로(데코레이터부터 자기 자신의 finally: conn.close() 까지) 고정문자열로
캡처해, 이 세션이 직접 읽어 둔 원본 전체 텍스트로 통째 치환하는 방식으로
되돌린다 — 다섯 곳의 부분 수정보다 훨씬 안전하다.

⚠⚠ [라운드621] 되돌림-증명 기법을 옛 세대(app.py를 실제로 디스크에 써넣고
매 실행 새로 생성한 워커 스크립트를 서브프로세스로 돌린 뒤 복원)에서
round488/507이 확립한 안전패턴으로 이관한다. api_case_remind_report()는
단일 라우트 핸들러라 ORIGINAL_FUNC 텍스트(데코레이터 제거)를 exec로 독립
사본 네임스페이스에 재구성해 A.app.view_functions 딕셔너리 항목만 잠깐
치환한다 — 진짜 app.py 파일도, 이제는 워커 파일도 전혀 안 쓴다(옛 워커
test_scan_round490_worker.py는 더 이상 생성하지 않는다).
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
print("  스캔 490라운드 회귀 — 완료보고 독촉 쿨다운 누락")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 함수 전체를 통째로 추출")
# ──────────────────────────────────────────────────────────────
START = '@app.post("/api/cases/<int:cid>/remind-report")'
END_MARK = '    finally:\n        conn.close()\n'
_s = APP_SRC.find(START)
_e = APP_SRC.find(END_MARK, _s)
_e = _e + len(END_MARK) if _e > 0 else -1
CURRENT_FUNC = APP_SRC[_s:_e] if _s > 0 and _e > _s else ""

chk(bool(CURRENT_FUNC), "함수 전체를 찾았다")
chk(APP_SRC.count(CURRENT_FUNC) == 1, "함수 텍스트가 소스에 유일하다",
    APP_SRC.count(CURRENT_FUNC) if CURRENT_FUNC else 0)
chk("BEGIN IMMEDIATE" in CURRENT_FUNC, "① BEGIN IMMEDIATE가 있다")
chk(CURRENT_FUNC.count("conn.rollback()") == 4,
    "②③④⑤ 조기반환 4곳(404·409×2·429) 모두 rollback을 한다",
    CURRENT_FUNC.count("conn.rollback()"))
chk("code\": \"COOLDOWN\"" in CURRENT_FUNC, "⑤ COOLDOWN 429 분기가 있다")
chk("ntype='완료보고독촉'" in CURRENT_FUNC, "⑤ 쿨다운 검사가 자기 자신의 ntype으로 조회한다")

#  이 세션이 수정 직전에 직접 Read로 확인해 둔 원본(라운드490 이전) 전체 텍스트.
ORIGINAL_FUNC = (
    '@app.post("/api/cases/<int:cid>/remind-report")\n'
    '@require_admin\n'
    'def api_case_remind_report(cid):\n'
    '    """완료보고 독촉 — 기한을 넘긴 사건의 시공사에게 다시 알린다.\n'
    '\n'
    '    자동 스윕(sweep_report_overdue)은 상태를 바꾸며 한 번만 알린다.\n'
    '    그 뒤로는 운영자가 직접 재촉할 수단이 없었다.\n'
    '    """\n'
    '    conn = DB.get_db()\n'
    '    try:\n'
    '        c = one(conn.execute(\n'
    '            "SELECT id, case_no, status, partner_id, partner_name, awarded_at "\n'
    '            "FROM cases WHERE id=?", (cid,)))\n'
    '        if not c:\n'
    '            return jsonify({"ok": False, "error": "사건을 찾을 수 없습니다."}), 404\n'
    '        if c["status"] not in ("시공중", "완료보고지연"):\n'
    '            return jsonify({"ok": False, "code": "NOT_ONGOING",\n'
    '                            "error": f"시공 진행 중인 사건만 독촉할 수 있습니다(현재 \'{c[\'status\']}\')."}), 409\n'
    '        if not c["partner_id"]:\n'
    '            return jsonify({"ok": False, "error": "배정된 시공사가 없습니다."}), 409\n'
    '        notify(conn, "완료보고독촉", "알림톡", c["partner_name"] or "시공사",\n'
    '               f"[{c[\'case_no\']}] 시공 완료 보고가 아직 접수되지 않았습니다. "\n'
    '               f"포털에서 사진과 함께 완료 보고를 올려 주세요.",\n'
    '               audience_type="partner", partner_id=c["partner_id"],\n'
    '               case_id=cid, url="/app/partner")\n'
    '        DB.log(conn, actor(), "완료보고 독촉", f"{c[\'case_no\']} → {c[\'partner_name\'] or \'\'}")\n'
    '        conn.commit()\n'
    '        return jsonify({"ok": True, "message": "시공사에 완료 보고를 독촉했습니다."})\n'
    '    finally:\n'
    '        conn.close()\n'
)

chk("BEGIN IMMEDIATE" not in ORIGINAL_FUNC, "원본 텍스트에는 BEGIN IMMEDIATE가 없다(대조군)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 준비 — 스크래치 DB + 실제 Flask 인프로세스 호출(연속 2회)")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round490_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB                 # noqa: E402
DB.init_db()
import app as A                 # noqa: E402

_seed_n = [0]


def _seed_case():
    """옛 워커의 시드 로직 — 매 시나리오(현재/되돌림/원복)마다 독립된
    관리자·시공사·사건을 새로 만들어 세 번의 호출이 서로 간섭하지 않게 한다."""
    _seed_n[0] += 1
    n = _seed_n[0]
    c = DB.get_db()
    c.execute("INSERT INTO admins(username,password_hash,name,role) "
              f"VALUES('b{n}','x','n','최고관리자')")
    pid = c.execute(f"INSERT INTO partners(name) VALUES('테스트시공사{n}')").lastrowid
    cid = c.execute(
        "INSERT INTO cases(case_no,status,partner_id,partner_name,created_at) "
        f"VALUES('R490-{n}','완료보고지연',?,'테스트시공사{n}',?)",
        (pid, DB.now())).lastrowid
    c.commit(); c.close()
    return cid, f"b{n}"


def _run_remind_twice(cid, uname):
    """옛 워커(test_scan_round490_worker.py, 더 이상 생성 안 함)의 로직을
    그대로 옮김 — 같은 사건에 연속 2회 독촉을 호출한다."""
    cl = A.app.test_client()
    with cl.session_transaction() as s:
        s["admin"] = uname; s["admin_role"] = "최고관리자"; s["_csrf"] = "x"
    codes = []
    for _ in range(2):
        r = cl.post(f"/api/cases/{cid}/remind-report", json={}, headers={"X-CSRF-Token": "x"})
        codes.append(r.status_code)
    conn2 = A.DB.get_db()
    n = conn2.execute(
        "SELECT COUNT(*) n FROM notifications WHERE case_id=? AND ntype='완료보고독촉'",
        (cid,)).fetchone()["n"]
    conn2.close()
    return {"codes": codes, "notif_count": n}


try:
    cid1, uname1 = _seed_case()
    out = _run_remind_twice(cid1, uname1)
    chk(out["codes"] == [200, 429],
        "★★★★★ 새 코드: 1차 200, 2차(즉시 연타)는 429 COOLDOWN으로 막힌다", out)
    chk(out["notif_count"] == 1,
        "★★★★★ 새 코드: 실제 발송대기 알림이 1건만 생긴다(중복발송 없음)", out)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 되돌림-증명 — view_functions 딕셔너리 항목만 잠깐 치환(실제 파일은 안 건드림)")
    # ──────────────────────────────────────────────────────────
    assert CURRENT_FUNC, "함수를 못 뽑아 되돌림-증명을 진행할 수 없다"
    _marker = "def api_case_remind_report(cid):"
    ORIGINAL_BODY_FOR_EXEC = _marker + ORIGINAL_FUNC.split(_marker, 1)[1]
    _ns = dict(vars(A))
    exec(compile(ORIGINAL_BODY_FOR_EXEC, "<round490_reverted_case_remind_report>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_fn = A.require_admin(_ns["api_case_remind_report"])

    _orig_view = A.app.view_functions["api_case_remind_report"]
    A.app.view_functions["api_case_remind_report"] = old_fn
    try:
        cid2, uname2 = _seed_case()
        out2 = _run_remind_twice(cid2, uname2)
    finally:
        A.app.view_functions["api_case_remind_report"] = _orig_view

    chk(out2["codes"] == [200, 200],
        "★★★★★ 옛 코드(되돌림): 연타 2회 모두 200으로 통과한다"
        " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", out2)
    chk(out2["notif_count"] == 2,
        "★★★★★ 옛 코드(되돌림): 실제 발송대기 알림이 2건(중복발송) 생긴다", out2)

    print("\n[4] 원복 확인 — 되돌리기 이후 다시 쿨다운이 걸리는가(바꿔치기가 안 샜다)")
    chk(A.app.view_functions["api_case_remind_report"] is _orig_view,
        "  view_functions가 원래 함수객체로 복원됐다")
    cid3, uname3 = _seed_case()
    out3 = _run_remind_twice(cid3, uname3)
    chk(out3["codes"] == [200, 429],
        "★★★★ 원복 후에는 다시 429 쿨다운이 걸린다(바꿔치기가 안 샜다)", out3)
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
