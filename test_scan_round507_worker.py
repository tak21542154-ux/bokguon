# -*- coding: utf-8 -*-
import io, json, os, sys, tempfile, threading
d = tempfile.mkdtemp(prefix='r507_')
os.environ['BOKGUON_DB_PATH'] = os.path.join(d, 'v.db')
os.environ['BOKGUON_UPLOAD_DIR'] = os.path.join(d, 'u')
os.environ['BOKGUON_ENV'] = 'dev'
os.environ['BOKGUON_SEED_DEMO'] = '0'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db as DB
DB.init_db()
c = DB.get_db()
c.execute("INSERT INTO admins(username,password_hash,name,role) "
          "VALUES('a1','x','n1','중간관리자')")
c.execute("INSERT INTO admins(username,password_hash,name,role) "
          "VALUES('a2','x','n2','중간관리자')")
camp_id = c.execute(
    "INSERT INTO campaigns(title,channel,status,total_count,created_by,created_at,queued_at) "
    "VALUES('테스트캠페인','메일','발송대기',1,'seed',?,?)", (DB.now(), DB.now())).lastrowid
c.execute("INSERT INTO campaign_targets(campaign_id,partner_id,name,contact,status,created_at) "
          "VALUES(?,?,?,?,?,?)", (camp_id, 1, 'p1', 'p1@x.com', '대기', DB.now()))
c.commit(); c.close()
import app as A
cl1 = A.app.test_client()
cl2 = A.app.test_client()
with cl1.session_transaction() as s:
    s['admin'] = 'a1'; s['admin_role'] = '중간관리자'; s['_csrf'] = 'c1'
with cl2.session_transaction() as s:
    s['admin'] = 'a2'; s['admin_role'] = '중간관리자'; s['_csrf'] = 'c2'

#  api_campaign_cancel()의 유일한 읽기지점(SELECT title, status FROM campaigns
#  WHERE id=?)에 threading.Barrier를 걸어 두 요청이 같은 순간에 그 실행에
#  도달하도록 강제한다(라운드505·506이 확립한 지연주입 프로브 기법과 같은 계열).
#  ⚠ 새 코드(BEGIN IMMEDIATE가 이 SELECT 바로 앞에 붙음)에서는 두 번째 스레드가
#    자기 자신의 BEGIN IMMEDIATE에서 먼저 막혀 이 SELECT에 함께 못 오는 경우가
#    많다 — 그러면 바리어가 5초 뒤 깨지고(BrokenBarrierError) 첫 스레드 혼자
#    진행한 뒤 잠금이 풀리며 둘째 스레드가 뒤늦게 도착한다(round506과 동일).
#    이건 결함이 아니라 잠금이 정확히 의도대로 두 스레드를 떼어놓았다는 증거다.
barrier = threading.Barrier(2, timeout=5)
hit = {'n': 0}
hit_lock = threading.Lock()


class _Probe:
    def __init__(self, real):
        self._real = real

    def execute(self, sql, params=()):
        if sql == "SELECT title, status FROM campaigns WHERE id=?":
            with hit_lock:
                hit['n'] += 1
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass
        return self._real.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._real, name)


_real_get_db = DB.get_db


def _patched():
    return _Probe(_real_get_db())


results = {}


def worker(key, cl, hdr):
    r = cl.post(f'/api/campaigns/{camp_id}/cancel', json={}, headers=hdr)
    results[key] = (r.status_code, (r.get_json() or {}).get('ok'))


DB.get_db = _patched
A.DB.get_db = _patched
t1 = threading.Thread(target=worker, args=('t1', cl1, {'X-CSRF-Token': 'c1'}))
t2 = threading.Thread(target=worker, args=('t2', cl2, {'X-CSRF-Token': 'c2'}))
t1.start(); t2.start(); t1.join(15); t2.join(15)
DB.get_db = _real_get_db
A.DB.get_db = _real_get_db

conn = A.DB.get_db()
log_n = conn.execute(
    "SELECT COUNT(*) n FROM activity_log WHERE action='마케팅 캠페인 취소'").fetchone()[0]
final_status = conn.execute("SELECT status FROM campaigns WHERE id=?", (camp_id,)).fetchone()[0]
excluded_n = conn.execute(
    "SELECT COUNT(*) n FROM campaign_targets WHERE campaign_id=? AND status='제외'",
    (camp_id,)).fetchone()[0]
conn.close()
print(json.dumps({
    'barrier_hits': hit['n'],
    'r1': list(results.get('t1', (None, None))),
    'r2': list(results.get('t2', (None, None))),
    'activity_log_count': log_n,
    'final_status': final_status,
    'excluded_targets': excluded_n,
}))
