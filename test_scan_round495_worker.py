# -*- coding: utf-8 -*-
"""라운드495 회귀 워커(test_scan_round495_fixes.py 전용 서브프로세스) —
manage.py cmd_prune_personal()(개인정보 파기)을 스크래치 DB에서 실제로
호출해 happy_calls(해피콜 기록)가 함께 파기되는지 확인한다. argv[1]로
되돌린 함수 소스 파일 경로를 받으면(되돌림-증명용) manage.py 자신의
네임스페이스 사본(dict(vars(M)))에만 그 함수를 exec해 대신 쓴다 — 실제
manage.py 파일은 이 프로세스 안에서도 전혀 건드리지 않는다. 이 파일
자신은 절대 수정 대상이 아니다.

⚠⚠ [라운드657] round626은 형제 워커(test_scan_round494_worker.py)만
정적 파일로 바꾸고 이 워커는 그대로 남겨 뒀다 — 내용이 결정적인데도
test_scan_round495_fixes.py가 배터리를 돌릴 때마다 이 저장소 루트에
다시 썼다(round656 핸드오프가 지목한 잔여 항목). 정적 파일로 바꿔 그
재작성을 없앤다 — 동작은 완전히 동일하다.
"""
import io
import json
import os
import sys
import tempfile

d = tempfile.mkdtemp(prefix='r495_')
os.environ['BOKGUON_DB_PATH'] = os.path.join(d, 'v.db')
os.environ['BOKGUON_ENV'] = 'dev'
os.environ['BOKGUON_SEED_DEMO'] = '0'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db as DB
DB.init_db()
c = DB.get_db()
# 8년 전 완료된 사건 — 하자담보(24개월) 만료는 확실히 지났다
cid = c.execute(
    "INSERT INTO cases(case_no,status,completed_at,warranty_months,is_demo) "
    "VALUES('R495-1','완료',datetime('now','+9 hours','-8 years'),24,0)").lastrowid
c.execute(
    "INSERT INTO happy_calls(case_id,score,feedback,called_by,created_at) "
    "VALUES(?,5,'홍길동님 자택 강남구 민원',"
    "'상담원김',datetime('now','+9 hours','-8 years'))", (cid,))
c.commit(); c.close()
import manage as M
_fn_file = sys.argv[1] if len(sys.argv) > 1 else ''
if _fn_file:
    #  [라운드618] 되돌린 함수 소스를 manage.py 자신의 네임스페이스 사본
    #  (dict(vars(M)))에만 exec한다 — 실제 manage.py 파일은 이 프로세스
    #  내내 전혀 안 건드려진다.
    _ns = dict(vars(M))
    exec(compile(io.open(_fn_file, encoding='utf-8').read(), '<r495-reverted>', 'exec'), _ns)
    rc = _ns['cmd_prune_personal']([])
else:
    rc = M.cmd_prune_personal([])
conn = DB.get_db()
case_row = dict(conn.execute("SELECT victim_name, victim_phone FROM cases WHERE id=?", (cid,)).fetchone())
hc_row = dict(conn.execute("SELECT feedback, called_by FROM happy_calls WHERE case_id=?", (cid,)).fetchone())
conn.close()
print(json.dumps({'rc': rc, 'case': case_row, 'happy_call': hc_row}))
