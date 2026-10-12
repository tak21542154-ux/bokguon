# -*- coding: utf-8 -*-
import io, json, os, sys, tempfile
d = tempfile.mkdtemp(prefix='r499_')
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
# 사건 쪽 공종은 정본 가운뎃점(U+00B7) — 실제 운영 정본 표기 3종 중 하나.
REGION = "서울특별시 송파구"
cid = c.execute(
    "INSERT INTO cases(case_no,status,category,region,is_demo) "
    "VALUES('R499-1','접수','가드레일·방호울타리',?,0)", (REGION,)).lastrowid
# 협력사 쪽 major 는 정부 공식 업종 표기 습관(U+318D 아래아) — 라운드186이
# 실측한 실제 협력사 10곳(id 305~314)과 같은 표기 패턴.
pid = c.execute(
    "INSERT INTO partners(name,status,region,major,license_status,phone) "
    "VALUES('아래아상사','활성',?,'가드레일ㆍ방호울타리','건설업',?)",
    (REGION, "01012345678")).lastrowid
c.commit(); c.close()

import dispatch as DP
conn = DB.get_db()
cands = DP.candidates(conn, cid)
conn.close()
match = next((x for x in cands if x["id"] == pid), None)

import app as A
cl = A.app.test_client()
with cl.session_transaction() as s:
    s['admin'] = 'a1'; s['admin_role'] = '최고관리자'; s['_csrf'] = 'c1'
r = cl.get(f'/api/cases/{cid}/nearby?trade=1', headers={'X-CSRF-Token': 'c1'})
resp = r.get_json() or {}
nearby_ids = [p["id"] for p in (resp.get("partners") or [])]

print(json.dumps({
    'dispatch_found': match is not None,
    'dispatch_why': match["why"] if match else None,
    'nearby_status': r.status_code,
    'nearby_found': pid in nearby_ids,
}))
