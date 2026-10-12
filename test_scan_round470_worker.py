# -*- coding: utf-8 -*-
"""라운드470 회귀 워커(test_scan_round470_fixes.py 전용 서브프로세스) —
스크래치 DB에서 보험사 원계정 세션으로 하위계정(portal_users)을 여러
번 실제로 생성하고 비밀번호 1회 재발급도 호출해, 발급된 temp_password
전부를 이 앱 자신의 password_policy_error()로 직접 검사한 결과(검사
건수·위반 건수)를 JSON 한 줄로 출력한다. app.py의 현재 상태(고쳐진
것이든, 되돌림-증명을 위해 임시로 되돌린 것이든)를 그대로 반영한다 —
이 파일 자신은 절대 수정 대상이 아니다.
"""
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
_tmpdir = tempfile.mkdtemp(prefix="r470_worker_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB               # noqa: E402
DB.init_db()
import app as A                # noqa: E402

N_CREATE = 30

conn = DB.get_db()
iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R470보험','활성')").lastrowid
conn.commit()
conn.close()


def _insurer_owner_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["insurer_id"] = iid
        sess["insurer_name"] = "R470보험"
        sess["_csrf"] = "r470-csrf"
    return c


c = _insurer_owner_client()
violations = 0
checked = 0
last_uid = None
for i in range(N_CREATE):
    r = c.post("/api/insurer/subaccounts",
               json={"login_id": f"r470sub{i:03d}", "name": f"담당자{i}", "role": "하위관리자"},
               headers={"X-CSRF-Token": "r470-csrf"})
    body = r.get_json() or {}
    if r.status_code != 200 or "temp_password" not in body:
        print(json.dumps({"error": f"생성 실패 idx={i}: {r.status_code} {body}"}))
        sys.exit(1)
    pw = body["temp_password"]
    checked += 1
    if A.password_policy_error(pw, ident=body.get("login_id", "")):
        violations += 1
    conn3 = DB.get_db()
    last_uid = conn3.execute(
        "SELECT id FROM portal_users WHERE login_id=?", (f"r470sub{i:03d}",)).fetchone()["id"]
    conn3.close()

# 재발급 경로도 1회 확인(이 라우트 자체의 쿨다운 때문에 반복호출은 안 함)
r_reset = c.post(f"/api/insurer/subaccounts/{last_uid}/reset-pw", json={},
                  headers={"X-CSRF-Token": "r470-csrf"})
reset_body = r_reset.get_json() or {}
reset_pw = reset_body.get("temp_password")
reset_violation = bool(A.password_policy_error(reset_pw, ident="")) if reset_pw else None

print(json.dumps({
    "checked": checked, "violations": violations,
    "reset_status": r_reset.status_code, "reset_violation": reset_violation,
}, ensure_ascii=False))
