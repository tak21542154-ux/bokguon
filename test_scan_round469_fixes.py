# -*- coding: utf-8 -*-
"""스캔 469라운드 회귀 — 발주처 사건취소(api_insurer_case_cancel)가
검토중인 1차 합의(field_agreements)를 안 닫아 고아로 남기던 결함, 1건.

형제(api_case_open_auction, app.py:16077-)는 2차 경매를 열 때 이미
검토중인 1차 합의를 '결렬'로 자동 종료하는데, 발주처 취소 경로만 이
정리가 빠져 있었다 — 취소된 사건의 field_agreements 행이 영원히
'검토중'으로 남는다. settle_agreement()의 사건상태 재확인(dispatch.py
1175·1247행, 승인·부동의 둘 다 "사건이 접수 상태가 아니면 거부")이
이미 다운스트림을 막고 있어 지금 위험한 결과로 이어지진 않지만(정밀
조사 Agent와 독립적으로 직접 코드 대조로 재확인), 안 닫은 '검토중'
행이 감사·집계 쿼리를 오도할 수 있어 형제와 같은 정리를 이식한다.

[1] 소스 확인 — 정리 코드가 실제로 있음.
[2]~[3] 실제 Flask 앱으로 되돌림-증명.

   ⚠⚠ [라운드614] 되돌림-증명 기법을 옛 세대(app.py를 실제로 디스크에
   써넣고 워커 서브프로세스로 재현한 뒤 복원 — write→subprocess→write
   사이의 창을 다른 세션이 관측하면 충돌한다, round590이 실제로 겪음)
   에서 round610이 api_boq_update 에 확립한 안전패턴으로 이관한다.
   api_insurer_case_cancel() 은 단일 라우트 핸들러라 A.app.view_functions
   딕셔너리 항목만 옛 버전(이 함수 자신의 소스에서 NEW_BLOCK→OLD_CALL로
   되돌린 사본을 exec 로 재구성, require_portal_role 데코레이터도 같은
   방식으로 다시 입힘)으로 잠깐 치환한다 — 진짜 app.py 파일은 전혀 안
   쓴다. 예전 워커(test_scan_round469_worker.py)는 더 이상 쓰지 않는다
   (그 파일 자신은 남겨 두되 이 파일에서 참조하지 않음).
"""
import hashlib
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(HERE, "app.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")
APP_HASH_BEFORE = hashlib.sha256(APP_SRC.encode("utf-8")).hexdigest()

print("=" * 72)
print("  스캔 469라운드 회귀 — 발주처 사건취소 시 1차합의 고아 방지")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
OLD_CALL = '''        conn.execute("UPDATE cases SET dispatch_status=NULL WHERE id=?", (cid,))
        notify(conn, "사건취소", "웹", "운영팀",'''

NEW_BLOCK = '''        conn.execute("UPDATE cases SET dispatch_status=NULL WHERE id=?", (cid,))
        #  ⚠⚠ [라운드469] 검토중인 1차 합의를 여기서도 함께 닫는다 — 형제
        #    (api_case_open_auction, 16077행)는 2차 경매를 열 때 이미 이
        #    정리를 하는데 발주처 취소만 빠져 있었다. settle_agreement()의
        #    사건상태 재확인(dispatch.py 1175·1247행)이 승인·부동의 둘 다
        #    이미 막고 있어(사건이 '접수'가 아니면 거부) 지금 위험한 결과로
        #    이어지진 않지만(실측 확인), 안 닫은 '검토중' 행이 감사·집계
        #    쿼리를 오도할 수 있어 형제와 같은 정리를 이식한다. 새 메커니즘
        #    없음.
        _hung = conn.execute(
            """UPDATE field_agreements
                  SET status=?, decided_at=datetime('now','+9 hours'),
                      reject_reason='발주처 사건 취소로 자동 종료'
                WHERE case_id=? AND status=?""",
            (DP.AG_BROKEN, cid, DP.AG_REVIEW)).rowcount
        if _hung:
            DB.log(conn, portal_actor(c["insurer"]), "1차 합의 자동 종료",
                   f"{c['case_no']} · 발주처 취소로 검토중 {_hung}건 종료")
        notify(conn, "사건취소", "웹", "운영팀",'''

chk(NEW_BLOCK in APP_SRC,
    "★★★★★ api_insurer_case_cancel()에 1차합의 자동종료 코드가 있다")
chk(APP_SRC.count(NEW_BLOCK) == 1,
    "되돌림-증명에 쓸 새 블록이 소스에 정확히 1번만 있다(대체 지점 특정 가능)",
    APP_SRC.count(NEW_BLOCK))


def _py_fn_body(src, fn_name):
    """함수 본문 — 다음 def뿐 아니라 다음 라우트의 @app. 데코레이터(그
    바로 위 주석까지)가 먼저 나오면 거기서 자른다(round610 정착 기법).
    api_insurer_case_cancel() 바로 뒤가 데코레이터 달린 다음 라우트라
    단순 '\\ndef ' 경계만 쓰면 그 데코레이터 줄까지 통째로 딸려와
    exec 시 구문오류가 난다."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


_body = _py_fn_body(APP_SRC, "api_insurer_case_cancel")
chk(NEW_BLOCK in _body, "  api_insurer_case_cancel() 본문 안에 NEW_BLOCK이 있다")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round469_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import dispatch as DP
    import app as A

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('r469admin','x','검증','최고관리자')")
    iid = conn0.execute(
        "INSERT INTO insurers(name,status) VALUES('R469보험','활성')").lastrowid
    pid = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,lat,lng) "
        "VALUES('R469업체','시행사','활성',37.5,127.0)").lastrowid
    conn0.commit()
    conn0.close()

    def _admin_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["admin"] = "r469admin"; sess["admin_name"] = "검증"
            sess["admin_role"] = "최고관리자"; sess["_csrf"] = "r469-csrf"
        return c

    def _insurer_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["insurer_id"] = iid; sess["insurer_name"] = "R469보험"
            sess["_csrf"] = "r469-csrf"
        return c

    def _run_scenario(case_no):
        """사건접수→출동배정→도착→1차합의 개시(검토중)까지 진행시킨 뒤
        발주처가 취소한다. (취소상태, 1차합의 상태) 를 돌려준다."""
        conn = DB.get_db()
        cid = conn.execute(
            "INSERT INTO cases(case_no,status,category,region,insurer_id,lat,lng) "
            "VALUES(?,'접수','가드레일','서울',?,37.5,127.0)", (case_no, iid)).lastrowid
        conn.commit()

        did, _called, _sent = DP.open_dispatch(conn, cid)
        conn.commit()
        ok_a, _msg_a, did2 = DP.assign_dispatch(conn, cid, pid, "테스트 직접배정")
        conn.commit()
        use_did = did2 if ok_a else did
        DP.claim(conn, use_did, pid, "R469업체")
        conn.commit()
        ok_r, msg_r = DP.arrive(conn, use_did, pid, photo_count=3, field_estimate=800000)
        conn.commit()
        if not ok_r:
            raise RuntimeError(f"arrive 준비 실패: {msg_r}")
        conn.close()

        r_fa = _admin_client().post(f"/api/cases/{cid}/field-agreement", json={},
                                     headers={"X-CSRF-Token": "r469-csrf"})
        r_cancel = _insurer_client().post(
            f"/api/insurer/cases/{cid}/cancel",
            json={"reason": "테스트용 취소 사유입니다"},
            headers={"X-CSRF-Token": "r469-csrf"})

        conn2 = DB.get_db()
        fa_row = conn2.execute(
            "SELECT status FROM field_agreements WHERE case_id=? ORDER BY id DESC LIMIT 1",
            (cid,)).fetchone()
        case_status = conn2.execute(
            "SELECT status FROM cases WHERE id=?", (cid,)).fetchone()["status"]
        conn2.close()
        return {
            "fa_open_status": r_fa.status_code,
            "cancel_status": r_cancel.status_code, "cancel_body": r_cancel.get_json(),
            "case_status_after": case_status,
            "field_agreement_status_after": (fa_row["status"] if fa_row else None),
        }

    print("\n[3] 실행 — 현재(고쳐진) 코드")
    fixed = _run_scenario("26-469F")
    chk(fixed["fa_open_status"] == 200, "1차합의 개시 자체는 정상 처리된다", fixed)
    chk(fixed["cancel_status"] == 200,
        "취소 요청 자체는 정상 처리된다", fixed["cancel_body"])
    chk(fixed["case_status_after"] == "취소", "사건 상태가 '취소'로 바뀐다",
        fixed["case_status_after"])
    chk(fixed["field_agreement_status_after"] == "결렬",
        "★★★★★ 고쳐진 코드는 취소 시 검토중이던 1차합의를 '결렬'로 함께 닫는다",
        fixed["field_agreement_status_after"])

    # ══════════════════════════════════════════════════════════
    print("\n[4] 되돌리기 — api_insurer_case_cancel만 옛 코드로(실제 파일은 안 건드림)")
    # ──────────────────────────────────────────────────────────
    _old_body = (_body
                 .replace("def api_insurer_case_cancel(cid):",
                          "def _api_insurer_case_cancel_pre469(cid):", 1)
                 .replace(NEW_BLOCK, OLD_CALL, 1))
    chk(_old_body.count(OLD_CALL) == 1 and "_api_insurer_case_cancel_pre469" in _old_body,
        "  (준비) 함수 리네임 + 1차합의 정리코드 제거가 정확히 적용됐다"
        "(실제 파일은 안 건드림)")

    _ns = dict(vars(A))
    exec(compile(_old_body, "<round469_pre469_case_cancel>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    #  실제 라우트는 @require_portal_role("insurer","중간관리자")로 감싸여
    #  있다 — view_functions 치환도 같은 데코레이터를 다시 입혀야 인가
    #  게이트를 우회하지 않는 정직한 대조가 된다.
    old_cancel_fn = A.require_portal_role("insurer", "중간관리자")(
        _ns["_api_insurer_case_cancel_pre469"])

    _orig_view = A.app.view_functions["api_insurer_case_cancel"]
    A.app.view_functions["api_insurer_case_cancel"] = old_cancel_fn
    try:
        broken = _run_scenario("26-469B")
    finally:
        A.app.view_functions["api_insurer_case_cancel"] = _orig_view

    chk(broken["cancel_status"] == 200,
        "옛 코드(되돌림)에서도 취소 요청 자체는 정상 처리된다", broken["cancel_body"])
    chk(broken["case_status_after"] == "취소",
        "옛 코드(되돌림)에서도 사건 상태는 '취소'로 바뀐다", broken["case_status_after"])
    chk(broken["field_agreement_status_after"] == "검토중",
        "★★★★★ 옛 코드(되돌림)는 취소해도 1차합의가 '검토중'인 채로 고아로 남는다"
        " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
        broken["field_agreement_status_after"])

    print("\n[5] 원복 확인 — 되돌리기 이후 정상 동작으로 돌아오는가(바꿔치기가 안 샜다)")
    chk(A.app.view_functions["api_insurer_case_cancel"] is _orig_view,
        "  view_functions가 원래 함수객체로 복원됐다")
    restored = _run_scenario("26-469R")
    chk(restored["field_agreement_status_after"] == "결렬",
        "★★★★ 원복 후에는 다시 1차합의가 '결렬'로 닫힌다(바꿔치기가 안 샜다)",
        restored["field_agreement_status_after"])

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__}: {e}")

APP_HASH_AFTER = hashlib.sha256(read("app.py").encode("utf-8")).hexdigest()
chk(APP_HASH_AFTER == APP_HASH_BEFORE,
    "★★★★★ 되돌리기 절차 동안 app.py 파일 내용이 전혀 안 바뀌었다"
    "(view_functions 딕셔너리 항목 임시치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
