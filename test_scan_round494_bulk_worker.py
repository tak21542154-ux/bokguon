# -*- coding: utf-8 -*-
"""라운드494 회귀 워커 ②(test_scan_round494_fixes.py [4] 전용 서브프로세스) —
api_partner_bulk_credentials() 일괄발급이 BEGIN IMMEDIATE 추가 뒤에도 서로
다른 업체 2곳을 정상적으로 함께 발급하는지(회귀 없음)를 스크래치 DB에서
실제 Flask 앱으로 확인한다. 이 파일 자신은 절대 수정 대상이 아니다.

⚠⚠ [라운드657] round626은 형제 워커(test_scan_round494_worker.py, [2][3]용)
만 정적 파일로 바꾸고 이 두 번째 워커([4]용)는 그대로 남겨 뒀다 — 내용이
결정적(매 라운드 항상 동일)인데도 test_scan_round494_fixes.py가 배터리를
돌릴 때마다 이 저장소 루트에 다시 썼다(round656 핸드오프가 지목한 잔여
항목). 정적 파일로 바꿔 그 재작성을 없앤다 — 동작은 완전히 동일하다.
"""
import json
import os
import sys
import tempfile

d = tempfile.mkdtemp(prefix='r494b_')
os.environ['BOKGUON_DB_PATH'] = os.path.join(d, 'v.db')
os.environ['BOKGUON_UPLOAD_DIR'] = os.path.join(d, 'u')
os.environ['BOKGUON_ENV'] = 'dev'
os.environ['BOKGUON_SEED_DEMO'] = '0'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db as DB
DB.init_db()
c = DB.get_db()
c.execute("INSERT INTO admins(username,password_hash,name,role) "
          "VALUES('a1','x','n1','최고관리자')")
pid1 = c.execute("INSERT INTO partners(name,status) VALUES('업체1','활성')").lastrowid
pid2 = c.execute("INSERT INTO partners(name,status) VALUES('업체2','활성')").lastrowid
c.commit(); c.close()
import app as A
cl = A.app.test_client()
with cl.session_transaction() as s:
    s['admin'] = 'a1'; s['admin_role'] = '최고관리자'; s['_csrf'] = 'c1'
r = cl.post('/api/partners/bulk-credentials', json={'ids': [pid1, pid2]},
            headers={'X-CSRF-Token': 'c1'})
j = r.get_json() or {}
print(json.dumps({'status': r.status_code, 'ok': j.get('ok'),
                   'n_issued': len(j.get('issued') or []),
                   'n_skipped': len(j.get('skipped') or [])}))
