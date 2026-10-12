# -*- coding: utf-8 -*-
"""라운드469 회귀 워커(test_scan_round469_fixes.py 전용 서브프로세스) —
스크래치 DB에서 사건접수→출동배정→도착→1차합의 개시(검토중)까지 실제로
진행시킨 뒤, 발주처가 그 사건을 취소하는 라우트를 실제로 호출해 결과
(취소 성공여부·1차합의 상태)를 JSON 한 줄로 출력한다. app.py의 현재
상태(고쳐진 것이든, 되돌림-증명을 위해 임시로 되돌린 것이든)를 그대로
반영한다 — 이 파일 자신은 절대 수정 대상이 아니다.
"""
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
_tmpdir = tempfile.mkdtemp(prefix="r469_worker_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB               # noqa: E402
DB.init_db()
import dispatch as DP         # noqa: E402
import app as A               # noqa: E402

conn = DB.get_db()
conn.execute("INSERT INTO admins(username,password_hash,name,role) "
             "VALUES('admin','x','검증','최고관리자')")
iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R469보험','활성')").lastrowid
pid = conn.execute(
    "INSERT INTO partners(name,partner_type,status,lat,lng) "
    "VALUES('R469업체','시행사','활성',37.5,127.0)").lastrowid
cid = conn.execute(
    "INSERT INTO cases(case_no,status,category,region,insurer_id,lat,lng) "
    "VALUES('26-469001','접수','가드레일','서울',?,37.5,127.0)", (iid,)).lastrowid
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
    print(json.dumps({"error": f"arrive 준비 실패: {msg_r}"}))
    sys.exit(1)
conn.close()


def _admin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "admin"
        sess["admin_name"] = "검증"
        sess["admin_role"] = "최고관리자"
        sess["_csrf"] = "r469-csrf"
    return c


def _insurer_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["insurer_id"] = iid
        sess["insurer_name"] = "R469보험"
        sess["_csrf"] = "r469-csrf"
    return c


admin_c = _admin_client()
r_fa = admin_c.post(f"/api/cases/{cid}/field-agreement", json={},
                     headers={"X-CSRF-Token": "r469-csrf"})

insurer_c = _insurer_client()
r_cancel = insurer_c.post(f"/api/insurer/cases/{cid}/cancel",
                           json={"reason": "테스트용 취소 사유입니다"},
                           headers={"X-CSRF-Token": "r469-csrf"})

conn2 = DB.get_db()
fa_row = conn2.execute(
    "SELECT status FROM field_agreements WHERE case_id=? ORDER BY id DESC LIMIT 1",
    (cid,)).fetchone()
case_status = conn2.execute("SELECT status FROM cases WHERE id=?", (cid,)).fetchone()["status"]
conn2.close()

print(json.dumps({
    "fa_open_status": r_fa.status_code, "fa_open_body": r_fa.get_json(),
    "cancel_status": r_cancel.status_code, "cancel_body": r_cancel.get_json(),
    "case_status_after": case_status,
    "field_agreement_status_after": (fa_row["status"] if fa_row else None),
}, ensure_ascii=False))
