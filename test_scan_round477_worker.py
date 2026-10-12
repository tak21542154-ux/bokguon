# -*- coding: utf-8 -*-
"""라운드477 회귀 워커(test_scan_round477_fixes.py 전용 서브프로세스) —
스크래치 DB에서 사건접수→출동배정→도착→1차합의 개시(검토중)까지 실제로
진행시킨 뒤, 보험사가 그 사건을 승인해 합의를 확정시키고(1차 호출),
곧바로 같은 사건에 다시 결정을 시도(2차 호출 — 경합에서 진 쪽을 흉내)해
그 응답(상태코드·JSON 본문)을 그대로 출력한다. app.py의 현재 상태(고쳐진
것이든, 되돌림-증명을 위해 임시로 되돌린 것이든)를 그대로 반영한다 —
이 파일 자신은 절대 수정 대상이 아니다.
"""
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
_tmpdir = tempfile.mkdtemp(prefix="r477_worker_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB               # noqa: E402
DB.init_db()
import dispatch as DP         # noqa: E402
import app as A               # noqa: E402

if os.environ.get("R477_BROKEN") == "1":
    #  ⚠⚠ [라운드625] 되돌림-증명용 — 실제 app.py 파일은 이 서브프로세스에서도
    #    전혀 안 건드린다. api_insurer_field_agreement_decision 은 독립된 단일
    #    Flask 라우트라 기법1(view_functions 딕셔너리 스왑) — 메인 테스트
    #    프로세스(test_scan_round477_fixes.py)의 NEW_BACKEND 추출 로직과
    #    똑같은 find() 규칙을 이 프로세스 안에서 다시 실행해(디스크는 원본
    #    그대로) 그 자리만 옛(취약) 코드로 바꾼 버전을 exec 해 view_functions
    #    에 갈아 끼운다.
    _APP_PATH = os.path.join(HERE, "app.py")
    _APP_SRC = io.open(_APP_PATH, encoding="utf-8").read()
    _bi = _APP_SRC.find('def api_insurer_field_agreement_decision(cid):')
    _bstart = _APP_SRC.find("        a = DP.agreement_view(conn, cid)", _bi)
    _bend = _APP_SRC.find('"error": "승인 대기 중인 현장 견적이 없습니다." + _detail}), 409', _bstart)
    _bend = _APP_SRC.find("\n", _bend) if _bend > 0 else -1
    _NEW_BACKEND = _APP_SRC[_bstart:_bend] if _bstart > 0 and _bend > 0 else ""
    _OLD_BACKEND = '''        a = DP.agreement_view(conn, cid)
        if not a or a.get("status") != DP.AG_REVIEW:
            return jsonify({"ok": False, "code": "NOT_PENDING",
                            "error": "승인 대기 중인 현장 견적이 없습니다."}), 409'''
    assert _NEW_BACKEND, "R477_BROKEN: NEW_BACKEND 블록을 못 찾음(app.py 변경?)"

    def _py_fn_body(src, fn_name):
        start = src.index(f"\ndef {fn_name}(")
        end = src.find("\ndef ", start + 1)
        dec = src.find("\n@app.", start + 1)
        if dec != -1 and (end == -1 or dec < end):
            end = dec
        return src[start:end if end != -1 else None]

    _body = _py_fn_body(_APP_SRC, "api_insurer_field_agreement_decision")
    assert _NEW_BACKEND in _body, "R477_BROKEN: 대상 함수 안에 블록이 없음"
    _broken_body = _body.replace(_NEW_BACKEND, _OLD_BACKEND, 1)
    assert _broken_body != _body
    _ns = dict(vars(A))
    exec(compile(_broken_body, "<r477_broken_field_agreement_decision>", "exec"), _ns)  # noqa: S102 -- 실소스 그대로 추출, 디스크 미기록
    A.app.view_functions["api_insurer_field_agreement_decision"] = (
        A.require_portal_role("insurer", "중간관리자")(_ns["api_insurer_field_agreement_decision"]))

conn = DB.get_db()
conn.execute("INSERT INTO admins(username,password_hash,name,role) "
             "VALUES('admin','x','검증','최고관리자')")
iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R477보험','활성')").lastrowid
pid = conn.execute(
    "INSERT INTO partners(name,partner_type,status,lat,lng) "
    "VALUES('R477업체','시행사','활성',37.5,127.0)").lastrowid
cid = conn.execute(
    "INSERT INTO cases(case_no,status,category,region,insurer_id,lat,lng) "
    "VALUES('26-477001','접수','가드레일','서울',?,37.5,127.0)", (iid,)).lastrowid
conn.commit()

did, _called, _sent = DP.open_dispatch(conn, cid)
conn.commit()
ok_a, _msg_a, did2 = DP.assign_dispatch(conn, cid, pid, "테스트 직접배정")
conn.commit()
use_did = did2 if ok_a else did
DP.claim(conn, use_did, pid, "R477업체")
conn.commit()
ok_r, msg_r = DP.arrive(conn, use_did, pid, photo_count=3, field_estimate=900000)
conn.commit()
if not ok_r:
    print(json.dumps({"error": f"arrive 준비 실패: {msg_r}"}))
    sys.exit(1)
conn.close()


def _admin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "admin"
        sess["admin_name"] = "검증"
        sess["admin_role"] = "최고관리자"
        sess["_csrf"] = "r477-csrf"
    return c


def _insurer_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["insurer_id"] = iid
        sess["insurer_name"] = "R477보험"
        sess["_csrf"] = "r477-csrf"
    return c


admin_c = _admin_client()
r_fa = admin_c.post(f"/api/cases/{cid}/field-agreement", json={},
                     headers={"X-CSRF-Token": "r477-csrf"})

#  1차 호출 — 이긴 쪽. 실제로 승인해 field_agreements.status 를 '합의'로
#  확정시키고 approver_name 을 남긴다(두 세션이 동시에 눌렀다고 가정할 때
#  DB에 먼저 반영되는 쪽 — 순서만 시뮬레이션, 결과는 스레드 타이밍과 무관).
insurer_c1 = _insurer_client()
r_win = insurer_c1.post(f"/api/insurer/cases/{cid}/field-agreement/decision",
                         json={"approve": True},
                         headers={"X-CSRF-Token": "r477-csrf"})

#  2차 호출 — 진 쪽(같은 사건에 뒤늦게 도착한 결정 요청). 별도 세션(하위
#  탭 등)이어도 같은 회사 로그인이면 같은 응답을 받으므로 세션은 재사용.
r_lose = insurer_c1.post(f"/api/insurer/cases/{cid}/field-agreement/decision",
                          json={"approve": True},
                          headers={"X-CSRF-Token": "r477-csrf"})

conn2 = DB.get_db()
fa_row = conn2.execute(
    "SELECT status, approver_name FROM field_agreements WHERE case_id=? "
    "ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
conn2.close()

print(json.dumps({
    "fa_open_status": r_fa.status_code,
    "win_status": r_win.status_code, "win_body": r_win.get_json(),
    "lose_status": r_lose.status_code, "lose_body": r_lose.get_json(),
    "field_agreement_after": dict(fa_row) if fa_row else None,
}, ensure_ascii=False))
