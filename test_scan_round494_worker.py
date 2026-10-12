# -*- coding: utf-8 -*-
"""라운드494 회귀 워커(test_scan_round494_fixes.py 전용 서브프로세스) —
스크래치 DB에서 실제 Flask 앱으로 ①api_admin_create 같은이름 경합과
②③협력사·보험사 교차표 같은 아이디 경합을 실제 스레드로 재현한다.
app.py의 현재 상태(고쳐진 것이든, R494_BROKEN=1 로 이 프로세스 안에서만
인메모리로 되돌린 것이든)를 그대로 반영한다 — 이 파일 자신은 절대
수정 대상이 아니다.

⚠⚠ [라운드626] 이전 버전은 test_scan_round494_fixes.py 가 이 파일을
매번 이스케이프-유니코드 문자열로 통째로 다시 썼다(내용은 결정적이라
매번 동일) — 정적 파일로 바꾸고 되돌림-증명용 R494_BROKEN 분기를
추가했다. app.py 실제 파일은 이 서브프로세스에서도 전혀 안 건드린다.
"""
import io
import json
import os
import sys
import tempfile
import threading

d = tempfile.mkdtemp(prefix='r494_')
os.environ['BOKGUON_DB_PATH'] = os.path.join(d, 'v.db')
os.environ['BOKGUON_UPLOAD_DIR'] = os.path.join(d, 'u')
os.environ['BOKGUON_ENV'] = 'dev'
os.environ['BOKGUON_SEED_DEMO'] = '0'
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import db as DB
DB.init_db()
c = DB.get_db()
c.execute("INSERT INTO admins(username,password_hash,name,role) "
          "VALUES('a1','x','n1','최고관리자')")
c.execute("INSERT INTO admins(username,password_hash,name,role) "
          "VALUES('a2','x','n2','최고관리자')")
pid = c.execute("INSERT INTO partners(name,status) VALUES('협력사1','활성')").lastrowid
iid = c.execute("INSERT INTO insurers(name,status) VALUES('보험사1','활성')").lastrowid
c.commit(); c.close()
import app as A
import time

if os.environ.get("R494_BROKEN") == "1":
    #  ⚠⚠ [라운드626] 되돌림-증명용 — 실제 app.py 파일은 이 서브프로세스에서도
    #    전혀 안 건드린다. ①api_admin_create·②api_partner_credentials는
    #    이 세션이 직접 확인한바 서로 부르지 않는 완전히 독립된 두 Flask
    #    라우트(round625가 "미검증"으로 남긴 캐리포워드 메모와 달리, 기법4의
    #    의존순서 실행이 필요 없다) — 기법1(view_functions 딕셔너리 스왑)을
    #    두 곳에 그대로 적용한다. 본문 텍스트는 별도 인터프리터(이 워커)라
    #    상태를 못 물려받으므로 라운드494 원본(수정 전) 함수를 그대로
    #    옮겨적었다(477·509 워커와 같은 관례).
    _ns = dict(vars(A))

    _OLD_ADMIN_CREATE_BODY = '''def api_admin_create():
    """관리자 계정 생성. 임시 비밀번호는 응답에 1회만 — 최초 로그인 시 변경 강제."""
    d = body()
    username = (d.get("username") or "").strip().lower()
    name = (d.get("name") or "").strip()[:40]
    role = d.get("role") if d.get("role") in ADMIN_ROLES else "하위관리자"
    if not re.fullmatch(r"[a-z0-9_-]{4,20}", username):
        return jsonify({"ok": False, "error": "아이디는 영문 소문자·숫자·-·_ 4~20자로 정해 주세요."}), 400
    if not name:
        return jsonify({"ok": False, "error": "이름은 필수입니다."}), 400
    conn = DB.get_db()
    if conn.execute("SELECT 1 FROM admins WHERE username=?", (username,)).fetchone():
        conn.close(); return jsonify({"ok": False, "error": "이미 존재하는 아이디입니다."}), 409
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    while True:
        temp_pw = "".join(secrets.choice(alphabet) for _ in range(12))
        if (any(c.isupper() for c in temp_pw) and any(c.islower() for c in temp_pw)
                and any(c.isdigit() for c in temp_pw)):
            break
    conn.execute(
        "INSERT INTO admins(username,password_hash,name,role,must_change_pw,created_at) "
        "VALUES(?,?,?,?,1,?)", (username, DB.hash_pw(temp_pw), name, role, DB.now()))
    DB.log(conn, actor(), "관리자 계정 생성", f"{username} ({role}) {name}")
    conn.commit(); conn.close()
    return jsonify({"ok": True, "username": username, "temp_password": temp_pw,
                    "message": "임시 비밀번호는 지금 한 번만 표시됩니다. 최초 로그인 시 변경이 강제됩니다."})
'''
    exec(compile(_OLD_ADMIN_CREATE_BODY, "<r494_broken_api_admin_create>", "exec"), _ns)  # noqa: S102 -- 라운드494 원본 그대로, 디스크 미기록
    A.app.view_functions["api_admin_create"] = A.require_role("최고관리자")(_ns["api_admin_create"])

    _OLD_PARTNER_CRED_BODY = '''def api_partner_credentials(pid):
    """협력사 포털 계정 발급 / 비밀번호 재발급 (한 곳).

    포털에는 회원가입 화면이 없다(무단 가입 방지). 입점 승인이 끝난 업체에
    **여기서 계정을 만들어 줘야** 포털에 들어와 입찰할 수 있다.
    임시 비밀번호는 이 응답에 한 번만 나온다 — 저장하지 않으므로 즉시 전달할 것.
    """
    conn = DB.get_db()
    ok, res, st = issue_partner_login(conn, pid, body().get("login_id"))
    if not ok:
        conn.close()
        return jsonify({"ok": False, **res}), st
    conn.commit(); conn.close()
    return jsonify({"ok": True, "login_id": res["login_id"],
                    "temp_password": res["temp_password"], "reissued": res["reissued"],
                    "message": "임시 비밀번호는 지금 한 번만 표시됩니다. "
                               "업체에 안전한 경로로 전달하세요."})
'''
    exec(compile(_OLD_PARTNER_CRED_BODY, "<r494_broken_api_partner_credentials>", "exec"), _ns)  # noqa: S102 -- 라운드494 원본 그대로, 디스크 미기록
    A.app.view_functions["api_partner_credentials"] = A.require_role("최고관리자")(_ns["api_partner_credentials"])

# 여러 개의 서로 다른 중복확인 SQL(_login_id_taken의 4개 질의·
# 보험사 자체 검사 등)을 하나의 바리어로 정확히 맞물리게 하는 대신,
# 읽기-쓰기 사이에 짧은 인공 지연을 두어 경쟁 창을 매번 넓혀 놓는다(도입된
# BEGIN IMMEDIATE가 있으면 그 사이 둘째 연결은 자체적으로 블록되어 지연이
# 의미가 없고, 없으면 지연이 실제로 둘 다 중복확인을 통과하게 만든다).
def make_delay_probe(match_sql_substr, delay=0.3):
    hit = {'n': 0}
    lock = threading.Lock()
    class _Probe:
        def __init__(self, real): self._real = real
        def execute(self, sql, params=()):
            if match_sql_substr in sql:
                with lock: hit['n'] += 1
                time.sleep(delay)
            return self._real.execute(sql, params)
        def __getattr__(self, name): return getattr(self._real, name)
    return _Probe, hit

results = {}

# --- 테스트 A: api_admin_create 같은이름 경합 ---
_Probe, hitA = make_delay_probe("SELECT 1 FROM admins WHERE username=?")
_real_get_db = DB.get_db
DB.get_db = lambda: _Probe(_real_get_db())
cl1 = A.app.test_client(); cl2 = A.app.test_client()
with cl1.session_transaction() as s:
    s['admin']='a1'; s['admin_role']='최고관리자'; s['_csrf']='c1'
with cl2.session_transaction() as s:
    s['admin']='a2'; s['admin_role']='최고관리자'; s['_csrf']='c2'
def workerA(key, cl, hdr):
    r = cl.post('/api/admins', json={'username':'racenew','name':'테스트'}, headers=hdr)
    results[key] = (r.status_code, (r.get_json() or {}).get('ok'))
t1 = threading.Thread(target=workerA, args=('A1', cl1, {'X-CSRF-Token':'c1'}))
t2 = threading.Thread(target=workerA, args=('A2', cl2, {'X-CSRF-Token':'c2'}))
t1.start(); t2.start(); t1.join(15); t2.join(15)
DB.get_db = _real_get_db
conn = A.DB.get_db()
n_racenew = conn.execute("SELECT COUNT(*) n FROM admins WHERE username='racenew'").fetchone()['n']
conn.close()

# --- 테스트 B: 교차표(협력사 vs 보험사) 같은 아이디 ---
_Probe2, hitB = make_delay_probe("LOWER(login_id)")
DB.get_db = lambda: _Probe2(_real_get_db())
cl3 = A.app.test_client(); cl4 = A.app.test_client()
with cl3.session_transaction() as s:
    s['admin']='a1'; s['admin_role']='최고관리자'; s['_csrf']='c3'
with cl4.session_transaction() as s:
    s['admin']='a2'; s['admin_role']='최고관리자'; s['_csrf']='c4'
def workerB_partner():
    r = cl3.post(f'/api/partners/{pid}/credentials', json={'login_id':'crossrace'},
                 headers={'X-CSRF-Token':'c3'})
    results['Bp'] = (r.status_code, (r.get_json() or {}).get('ok'))
def workerB_insurer():
    r = cl4.post(f'/api/insurers/{iid}/credentials', json={'login_id':'crossrace'},
                 headers={'X-CSRF-Token':'c4'})
    results['Bi'] = (r.status_code, (r.get_json() or {}).get('ok'))
tB1 = threading.Thread(target=workerB_partner)
tB2 = threading.Thread(target=workerB_insurer)
tB1.start(); tB2.start(); tB1.join(15); tB2.join(15)
DB.get_db = _real_get_db
conn = A.DB.get_db()
n_partner_cross = conn.execute("SELECT COUNT(*) n FROM partners WHERE login_id='crossrace'").fetchone()['n']
n_insurer_cross = conn.execute("SELECT COUNT(*) n FROM insurers WHERE login_id='crossrace'").fetchone()['n']
conn.close()

print(json.dumps({
    'hitA': hitA['n'], 'A1': list(results.get('A1', (None, None))), 'A2': list(results.get('A2', (None, None))),
    'n_racenew': n_racenew,
    'hitB': hitB['n'], 'Bp': list(results.get('Bp', (None, None))), 'Bi': list(results.get('Bi', (None, None))),
    'n_partner_cross': n_partner_cross, 'n_insurer_cross': n_insurer_cross,
}))
