# -*- coding: utf-8 -*-
import io, json, os, sys, tempfile
d = tempfile.mkdtemp(prefix='r496_')
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
cid = c.execute(
    "INSERT INTO cases(case_no,status,victim_name,is_demo) "
    "VALUES('R496-1','접수','홍길동',0)").lastrowid
c.commit(); c.close()
import app as A
cl = A.app.test_client()
with cl.session_transaction() as s:
    s['admin'] = 'a1'; s['admin_role'] = '최고관리자'; s['_csrf'] = 'c1'
r = cl.patch(f'/api/cases/{cid}', json={'victim_name': '홍길순'},
             headers={'X-CSRF-Token': 'c1'})
resp = r.get_json() or {}
conn = A.DB.get_db()
log_row = conn.execute(
    "SELECT detail FROM activity_log WHERE action='사건 수동 수정' "
    "ORDER BY id DESC LIMIT 1").fetchone()
conn.close()
print(json.dumps({
    'status': r.status_code,
    'changed': resp.get('changed'),
    'log_detail': (dict(log_row) or {}).get('detail') if log_row else None,
}))
