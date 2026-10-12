# -*- coding: utf-8 -*-
"""라운드515 회귀 워커(test_scan_round515_fixes.py 전용 서브프로세스) —
스크래치 DB에서 사건접수(피해자 연락처 포함)→출동배정→도착→1차합의
개시(검토중)까지 실제로 진행시킨 뒤, 보험사가 그 사건을 승인해 합의를
확정시키고(현장 견적 승인), notifications 테이블에 피해자안내(문자) 행이
실제로 쌓였는지 그대로 출력한다. app.py의 현재 상태(고쳐진 것이든,
되돌림-증명을 위해 임시로 되돌린 것이든)를 그대로 반영한다 — 이 파일
자신은 절대 수정 대상이 아니다.
"""
import io
import json
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
_tmpdir = tempfile.mkdtemp(prefix="r515_worker_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB               # noqa: E402
DB.init_db()
import dispatch as DP         # noqa: E402
import app as A                # noqa: E402

conn = DB.get_db()
conn.execute("INSERT INTO admins(username,password_hash,name,role) "
             "VALUES('admin','x','검증','최고관리자')")
iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R515보험','활성')").lastrowid
pid = conn.execute(
    "INSERT INTO partners(name,partner_type,status,lat,lng) "
    "VALUES('R515업체','시행사','활성',37.5,127.0)").lastrowid
#  ⚠ 피해자 연락처를 반드시 채운다 — notify_victim() 은 victim_phone 이
#    없으면 조용히 아무 일도 안 하고 리턴한다(19316행). 연락처 없이
#    돌리면 "결함이 있어도 없어도 통지 0건"이라 이 테스트가 결함을 구분
#    못 하게 된다.
cid = conn.execute(
    "INSERT INTO cases(case_no,status,category,region,insurer_id,lat,lng,"
    "victim_name,victim_phone) "
    "VALUES('26-515001','접수','가드레일','서울',?,37.5,127.0,'피해자515','01055515515')",
    (iid,)).lastrowid
conn.commit()

did, _called, _sent = DP.open_dispatch(conn, cid)
conn.commit()
ok_a, _msg_a, did2 = DP.assign_dispatch(conn, cid, pid, "테스트 직접배정")
conn.commit()
use_did = did2 if ok_a else did
DP.claim(conn, use_did, pid, "R515업체")
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
        sess["_csrf"] = "r515-csrf"
    return c


def _insurer_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["insurer_id"] = iid
        sess["insurer_name"] = "R515보험"
        sess["_csrf"] = "r515-csrf"
    return c


#  ⚠ arrive() 만으로는 합의가 '검토중'(AG_REVIEW)이 되지 않는다 — 관리자가
#    /api/cases/<cid>/field-agreement 로 1차합의를 실제로 개시해야 보험사
#    결정 엔드포인트가 그 행을 본다(477라운드 워커와 같은 순서).
admin_c = _admin_client()
r_fa = admin_c.post(f"/api/cases/{cid}/field-agreement", json={},
                     headers={"X-CSRF-Token": "r515-csrf"})
if r_fa.status_code != 200:
    print(json.dumps({"error": f"1차합의 개시 실패: {r_fa.status_code} {r_fa.get_json()}"}))
    sys.exit(1)

insurer_c = _insurer_client()
r_decide = insurer_c.post(f"/api/insurer/cases/{cid}/field-agreement/decision",
                           json={"approve": True},
                           headers={"X-CSRF-Token": "r515-csrf"})

conn2 = DB.get_db()
fa_row = conn2.execute(
    "SELECT status, approver_name FROM field_agreements WHERE case_id=? "
    "ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
victim_rows = conn2.execute(
    "SELECT ntype, channel, message FROM notifications "
    " WHERE case_id=? AND ntype='피해자안내'", (cid,)).fetchall()
case_status = conn2.execute("SELECT status, partner_name FROM cases WHERE id=?",
                             (cid,)).fetchone()
conn2.close()

print(json.dumps({
    "fa_open_status": r_fa.status_code,
    "decide_status": r_decide.status_code, "decide_body": r_decide.get_json(),
    "field_agreement_after": dict(fa_row) if fa_row else None,
    "case_after": dict(case_status) if case_status else None,
    "victim_notify_count": len(victim_rows),
    "victim_notify_rows": [dict(r) for r in victim_rows],
}, ensure_ascii=False))
