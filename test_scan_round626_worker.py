# -*- coding: utf-8 -*-
"""라운드626 회귀 워커(test_scan_round626_fixes.py 전용 서브프로세스) —
스크래치 DB에서 실제 Flask 앱으로 데모 발주처 1곳 + 실제 발주처 1곳을
만들고 관리자 세션으로 GET /api/insurers(기본모드, ?all=1 아님)를 실제로
호출해 그 결과를 그대로 출력한다. app.py의 현재 상태(고쳐진 것이든,
R626_BROKEN=1 로 이 프로세스 안에서만 인메모리로 되돌린 것이든)를 그대로
반영한다 — 이 파일 자신은 절대 수정 대상이 아니다.
"""
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
_tmpdir = tempfile.mkdtemp(prefix="r626_worker_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB               # noqa: E402
DB.init_db()
conn = DB.get_db()
conn.execute("INSERT INTO admins(username,password_hash,name,role) "
             "VALUES('admin','x','검증','최고관리자')")
conn.execute("INSERT INTO insurers(name,status,is_demo) VALUES('R626실보험','활성',0)")
conn.execute("INSERT INTO insurers(name,status,is_demo) VALUES('R626데모보험','활성',1)")
conn.commit()
conn.close()

import app as A                # noqa: E402

if os.environ.get("R626_BROKEN") == "1":
    #  ⚠⚠ [라운드626] 되돌림-증명용 — 실제 app.py 파일은 이 서브프로세스에서도
    #    전혀 안 건드린다. api_insurers_list() 는 독립된 단일 Flask 라우트라
    #    기법1(view_functions 딕셔너리 스왑) — 이 서브프로세스는 시나리오 실행
    #    후 바로 종료되므로 복원(restore)이 필요 없다.
    _APP_PATH = os.path.join(HERE, "app.py")
    _APP_SRC = io.open(_APP_PATH, encoding="utf-8").read()

    def _py_fn_body(src, fn_name):
        start = src.index(f"\ndef {fn_name}(")
        end = src.find("\ndef ", start + 1)
        dec = src.find("\n@app.", start + 1)
        if dec != -1 and (end == -1 or dec < end):
            end = dec
        return src[start:end if end != -1 else None]

    _NEW_SELECT = ('"SELECT id, name, org_type, fee_rate_bp, contract_status, is_demo FROM insurers "\n'
                   '            "WHERE status=\'활성\' ORDER BY name"))')
    _OLD_SELECT = ('"SELECT id, name, org_type, fee_rate_bp, contract_status FROM insurers "\n'
                   '            "WHERE status=\'활성\' ORDER BY name"))')
    _body = _py_fn_body(_APP_SRC, "api_insurers_list")
    assert _NEW_SELECT in _body, "R626_BROKEN: 대상 SELECT를 못 찾음(app.py 변경?)"
    _broken_body = _body.replace(_NEW_SELECT, _OLD_SELECT, 1)
    assert _broken_body != _body
    _ns = dict(vars(A))
    exec(compile(_broken_body, "<r626_broken_api_insurers_list>", "exec"), _ns)  # noqa: S102 -- 실소스 그대로 추출, 디스크 미기록
    A.app.view_functions["api_insurers_list"] = A.require_admin(_ns["api_insurers_list"])


def _admin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "admin"
        sess["admin_name"] = "검증"
        sess["admin_role"] = "최고관리자"
        sess["_csrf"] = "r626-csrf"
    return c


admin_c = _admin_client()
r = admin_c.get("/api/insurers")  # 기본모드 — ?all=1 없음(사건 등록·정산명세서 드롭다운이 쓰는 자리)

print(json.dumps({"status": r.status_code, "body": r.get_json()}, ensure_ascii=False))
