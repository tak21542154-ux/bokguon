# -*- coding: utf-8 -*-
"""스캔 427라운드 회귀 — 정산 이체완료/검수승인 라우트에 취소(void) 방어 보강,
   1건(형제 2곳).

   정밀조사 Agent(각도1: 정산 지급완료 상태전이 무결성)가 발견 — 형제 4곳
   (api_settlement_paid·paid-bulk·api_insurer_settlement_approve·remind-
   approval)은 전부 `void_status=='취소'`를 명시적으로 거부하는데, 그 뒤
   단계인 `api_settlement_review`(app.py:13638-)·`api_settlement_transfer`
   (app.py:12846-)만 이 검사가 빠져 있었다.

   **지금 당장은 도달 불가능함을 직접 확인**: `api_settlement_void`(13435-)
   자신이 취소 시점에 이체완료·입금완료·검수승인 중 하나라도 있으면 거부하고
   (13462·13467·13472), `insurer_paid='입금완료'`를 세팅하는 유일한 두 곳
   (api_settlement_paid·paid-bulk)이 이미 void_status를 거부하므로, 취소된
   건은 insurer_paid가 영원히 '대기'로 묶여 review()의 NOT_PAID 관문(13654)
   에 막히고, review_status도 영원히 '대기'로 묶여 transfer()의 관문(12860)
   에 막힌다 — 세 컬럼 다 단일 세터(single writer)라 이 사슬에 예외가 없다.

   다만 이는 review/transfer 자신이 아니라 **다른 라우트들이 우연히 지키는
   불변식**에 기댄 것이라, 나중에 insurer_paid를 세팅하는 새 경로(예: 관리자
   수기보정)가 하나라도 이 검사를 빠뜨리면 조용히 뚫리는 잠복위험이다(424
   라운드의 bids UNIQUE 인덱스와 같은 종류의 방어심화).

   고침: review·transfer 둘 다 형제와 같은 `void_status=='취소'` 조기거부를
   추가 — 정상 경로의 동작은 전혀 안 바뀐다(정상 경로로는 이 상태 자체가
   못 만들어지므로).

       python test_scan_round427_fixes.py
"""
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

print("=" * 72)
print("  스캔 427라운드 회귀 — 정산 review/transfer 취소(void) 방어 보강")
print("=" * 72)

print("\n[1] 소스 확인")
_ti0 = APP_SRC.index("def api_settlement_transfer(sid):")
_ti1 = APP_SRC.index("\n@app.", _ti0 + 1)
_transfer_body = APP_SRC[_ti0:_ti1]
chk('(st["void_status"] or "") == "취소"' in _transfer_body,
    "★★★★★ api_settlement_transfer() 가 이제 취소된 건을 자체적으로 거부한다")

_ri0 = APP_SRC.index("def api_settlement_review(sid):")
_ri1 = APP_SRC.index("\n@app.", _ri0 + 1)
_review_body = APP_SRC[_ri0:_ri1]
chk('(s["void_status"] or "") == "취소"' in _review_body,
    "★★★★★ api_settlement_review() 도 이제 취소된 건을 자체적으로 거부한다")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round427_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)


def _seed(conn, tag):
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,bank_name,bank_holder,bank_account_enc) "
        f"VALUES('R427업체{tag}','시행사','활성','국민','R427업체{tag}','enc:1234')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,is_demo) "
        f"VALUES('R427-C{tag}','정산진행','가드레일','서울',?,0)", (pid,)).lastrowid
    return pid, cid


try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','최고관리자')")
    conn.commit()

    admin = A.app.test_client()
    _tok = "r427-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    hdr = {"X-CSRF-Token": _tok}

    print("\n[3] 실행 — transfer(): 정상 경로로는 못 만드는 상태(취소+검수승인)를 직접 "
          "구성해 방어를 실측")
    #  ⚠ 이 상태는 실제 API로는 못 만든다(위 docstring 증명) — 이 함수 자신이
    #    독립적으로 방어하는지 확인하려고 SQL로 직접 구성한다(백스톱 실효성 검증).
    pid1, cid1 = _seed(conn, "T")
    sid1 = conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_id,partner_name,amount,fee,"
        "                        payout,review_status,transfer_status,void_status,created_at) "
        "VALUES(?,'R427-CT','R427보험',?,'R427업체T',3000000,300000,2700000,"
        "'승인','대기','취소',?)", (cid1, pid1, DB.now())).lastrowid
    conn.commit()
    r1 = admin.post(f"/api/settlements/{sid1}/transfer", headers=hdr, json={})
    chk(r1.status_code == 409,
        "★★★★★ 취소된 건은 검수승인 상태여도 transfer() 자체가 거부한다"
        "(형제 결함 재현 방지 — 옛 코드였다면 통과했을 것)", (r1.status_code, r1.get_json()))
    st1 = conn.execute("SELECT transfer_status FROM settlements WHERE id=?", (sid1,)).fetchone()
    chk(st1["transfer_status"] == "대기",
        "  이체상태가 실제로 안 바뀌었다(회귀없음)", dict(st1))

    print("\n[4] 실행 — review(): 정상 경로로는 못 만드는 상태(취소+입금완료)를 직접 "
          "구성해 방어를 실측")
    pid2, cid2 = _seed(conn, "R")
    sid2 = conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_id,partner_name,amount,fee,"
        "                        payout,review_status,transfer_status,insurer_paid,void_status,"
        "                        created_at) "
        "VALUES(?,'R427-CR','R427보험',?,'R427업체R',1000000,100000,900000,"
        "'대기','대기','입금완료','취소',?)", (cid2, pid2, DB.now())).lastrowid
    conn.commit()
    r2 = admin.post(f"/api/settlements/{sid2}/review", headers=hdr,
                     json={"double_checked": True})
    chk(r2.status_code == 409,
        "★★★★★ 취소된 건은 입금완료 상태여도 review() 자체가 거부한다"
        "(형제 결함 재현 방지 — 옛 코드였다면 통과했을 것)", (r2.status_code, r2.get_json()))
    st2 = conn.execute("SELECT review_status FROM settlements WHERE id=?", (sid2,)).fetchone()
    chk(st2["review_status"] == "대기",
        "  검수상태가 실제로 안 바뀌었다(회귀없음)", dict(st2))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 되돌리기 — 옛 코드(void_status 미검사)였다면 실제로 통과했는가")
# ------------------------------------------------------------
#  ⚠⚠ [라운드619] on-disk 되돌리기(파일에 직접 쓰고 subprocess)를 인메모리로
#    이관 — api_settlement_transfer() 는 @require_role 데코레이터가 달린
#    단일 Flask 라우트 핸들러라 A.app.view_functions 딕셔너리 항목만 잠깐
#    치환한다(기법1, round417/422 가 정착시킨 방식). 되돌린 함수는 사본
#    이름공간(dict(vars(A)))에 exec해 만들고, 실 모듈의 A.require_role 로
#    다시 감싸 인증 동작은 그대로 유지한다 — review() 의 부수정은 [1]의
#    정적 소스확인만으로 이미 커버되어 여기서 별도 재현은 안 한다(기존
#    범위 그대로).
NEW_TRANSFER = '''    st = one(conn.execute("SELECT * FROM settlements WHERE id=?", (sid,)))
    if not st:
        conn.rollback(); conn.close()
        return jsonify({"ok": False, "error": "정산 건을 찾을 수 없습니다."}), 404
    #  ⚠ [427라운드] 형제(api_settlement_paid·paid-bulk)와 같은 방어를 여기도 둔다.
    #    지금은 취소 관문(void)이 이체완료/입금완료/검수승인 중 하나라도 있으면
    #    막아 이 자리까지 취소된 건이 절대 못 오지만, 그 보장은 이 함수가 아니라
    #    void·paid·review 세 라우트가 지키는 것이라 새 입금확인 경로가 하나라도
    #    추가되면 조용히 뚫릴 수 있다 — 이 함수 자신도 독립적으로 방어한다.
    if (st["void_status"] or "") == "취소":
        conn.rollback(); conn.close()
        return jsonify({"ok": False, "error": "취소된 정산 건입니다."}), 409
    if st["review_status"] != "승인":'''
OLD_TRANSFER = '''    st = one(conn.execute("SELECT * FROM settlements WHERE id=?", (sid,)))
    if not st:
        conn.rollback(); conn.close()
        return jsonify({"ok": False, "error": "정산 건을 찾을 수 없습니다."}), 404
    if st["review_status"] != "승인":'''


def _ast_fn_src(src, fn_name):
    """ast로 함수의 정확한 경계(decorator 제외, def~마지막 줄)를 뽑는다."""
    import ast
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            return "".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError(f"함수 {fn_name} 을 못 찾음")


try:
    _transfer_src = _ast_fn_src(APP_SRC, "api_settlement_transfer")
    chk(_transfer_src.count(NEW_TRANSFER) == 1,
        "  (준비) transfer 되돌리기 대상 텍스트가 함수 본문 안에 유일하게 식별된다")
    reverted_transfer_src = _transfer_src.replace(NEW_TRANSFER, OLD_TRANSFER)
    chk(reverted_transfer_src != _transfer_src, "  (준비) 되돌리기 텍스트가 실제로 달라졌다")

    #  ⚠ 위 [2]-[4] 블록이 이미 conn.close()를 했다 — 이 섹션은 새 커넥션을 연다.
    conn2 = DB.get_db()
    pid1, cid1 = _seed(conn2, "T2")
    sid1 = conn2.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_id,partner_name,amount,fee,"
        "                        payout,review_status,transfer_status,void_status,created_at) "
        "VALUES(?,'R427-CT2','R427보험',?,'R427업체T2',3000000,300000,2700000,"
        "'승인','대기','취소',?)", (cid1, pid1, DB.now())).lastrowid
    conn2.commit()

    _ns = dict(vars(A))
    exec(compile(reverted_transfer_src, "<round427_reverted:api_settlement_transfer>", "exec"), _ns)  # noqa: S102 -- 우리 소스 그대로 추출, 디스크 미기록
    old_transfer_fn = A.require_role("최고관리자")(_ns["api_settlement_transfer"])

    _orig_view = A.app.view_functions["api_settlement_transfer"]
    A.app.view_functions["api_settlement_transfer"] = old_transfer_fn
    try:
        r_old = admin.post(f"/api/settlements/{sid1}/transfer", headers=hdr, json={})
    finally:
        A.app.view_functions["api_settlement_transfer"] = _orig_view

    st_old = conn2.execute("SELECT transfer_status FROM settlements WHERE id=?", (sid1,)).fetchone()
    chk(r_old.status_code == 200 and st_old["transfer_status"] == "이체완료",
        "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림)는 취소된 건인데도 실제로 "
        "이체를 완료 처리해버린다(인과관계 직접증명)",
        (r_old.status_code, dict(st_old)))
    chk(A.app.view_functions["api_settlement_transfer"] is _orig_view,
        "  view_functions가 원래 함수객체로 복원됐다")
    conn2.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기 실행", f"{type(e).__name__} {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py는 이 되돌림-증명 내내 디스크에서 전혀 건드려지지 않았다")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
