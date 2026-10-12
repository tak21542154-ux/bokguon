# -*- coding: utf-8 -*-
import io, json, os, sys, tempfile
d = tempfile.mkdtemp(prefix='r488_')
os.environ['BOKGUON_DB_PATH'] = os.path.join(d, 'v.db')
os.environ['BOKGUON_UPLOAD_DIR'] = os.path.join(d, 'u')
os.environ['BOKGUON_ENV'] = 'dev'
os.environ['BOKGUON_SEED_DEMO'] = '0'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db as DB
DB.init_db()
c = DB.get_db()
c.execute("INSERT INTO admins(username,password_hash,name,role,totp_secret) "
          "VALUES('b','x','n2','최고관리자',?)", ('ENC',))
c.commit(); c.close()
import app as A
cl = A.app.test_client()
with cl.session_transaction() as s:
    s['admin']='b'; s['admin_role']='최고관리자'; s['_csrf']='x'
A.CRYPTO.decrypt = lambda x: 'SECRET'
A.TOTP.verify = lambda secret, code: (False, 0, 'bad')
codes = []
for i in range(10):
    r = cl.post('/api/me/otp/confirm', json={'code':'000000'}, headers={'X-CSRF-Token':'x'})
    codes.append(r.status_code)
print(json.dumps({'codes': codes}))
