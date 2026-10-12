# -*- coding: utf-8 -*-
import io, json, os, sys, tempfile
d = tempfile.mkdtemp(prefix='r498_')
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
pid1 = c.execute(
    "INSERT INTO partners(name,status,biz_no) "
    "VALUES('A상사','활성','1234567891')").lastrowid
pid2 = c.execute(
    "INSERT INTO partners(name,status) "
    "VALUES('B상사','심사중')").lastrowid
c.commit(); c.close()
import app as A

if os.environ.get("R498_BROKEN") == "1":
    #  ⚠⚠ [라운드626] 되돌림-증명용 — 실제 app.py 파일은 이 서브프로세스에서도
    #    전혀 안 건드린다(이전 버전은 메인 테스트 프로세스가 app.py 를 통째로
    #    디스크에 다시 썼다 finally 로 복원했다). 8곳 중 6곳은 독립된 Flask
    #    라우트라 기법1(view_functions 스왑), clean_public_form()·
    #    _auto_login_id() 2곳은 다른(안 건드리는) 실함수가 맨이름으로 부르는
    #    헬퍼라 기법3(실모듈 __dict__ 에 직접 exec) — 이 서브프로세스는
    #    시나리오 실행 후 바로 종료되므로 복원(restore)이 필요 없다.
    _APP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    _APP_SRC = io.open(_APP_PATH, encoding="utf-8").read()

    def _py_fn_body(src, fn_name):
        start = src.index(f"\ndef {fn_name}(")
        end = src.find("\ndef ", start + 1)
        dec = src.find("\n@app.", start + 1)
        if dec != -1 and (end == -1 or dec < end):
            end = dec
        return src[start:end if end != -1 else None]

    #  (fn_name, 이 라운드(498) 자신의 [^0-9] 정규화, 되돌릴 \D 정규화,
    #   view_functions 에 되꽂을 데코레이터 — None 이면 기법3(헬퍼)).
    #   cur/orig 문자열은 test_scan_round498_fixes.py 의 PAIRS 와 문자
    #   그대로 동일(그 파일의 [1]이 이미 소스에 정확히 1번씩만 있음을
    #   검증한다) — 손으로 옮겨적다 어긋나는 사고를 피하려 그대로 복사.
    _SITES = [
        ("api_partner_profile_update",
         '        _bz = re.sub(r"[^0-9]", "", _s(d.get("biz_no")))\n',
         '        _bz = re.sub(r"\\D", "", _s(d.get("biz_no")))\n',
         A.require_partner),
        ("clean_public_form",
         '        out["biz_no"] = re.sub(r"[^0-9]", "", out["biz_no"])\n',
         '        out["biz_no"] = re.sub(r"\\D", "", out["biz_no"])\n',
         None),
        ("api_application_create",
         '    biz = re.sub(r"[^0-9]", "", biz)\n',
         '    biz = re.sub(r"\\D", "", biz)\n',
         A.require_admin),
        ("api_application_update",
         '            _biz = re.sub(r"[^0-9]", "", app_row.get("biz_no") or "")\n',
         '            _biz = re.sub(r"\\D", "", app_row.get("biz_no") or "")\n',
         A.require_role("중간관리자")),
        ("_auto_login_id",
         '    biz = re.sub(r"[^0-9]", "", (p["biz_no"] or ""))\n',
         '    biz = re.sub(r"\\D", "", (p["biz_no"] or ""))\n',
         None),
        ("api_partner_create",
         '    _biz = re.sub(r"[^0-9]", "", _s(d.get("biz_no")))\n',
         '    _biz = re.sub(r"\\D", "", _s(d.get("biz_no")))\n',
         A.require_admin),
        ("api_partner_update",
         '                d[f] = re.sub(r"[^0-9]", "", _s(d[f]))\n',
         '                d[f] = re.sub(r"\\D", "", _s(d[f]))\n',
         A.require_admin),
        ("api_partner_license",
         '            _bz = re.sub(r"[^0-9]", "", _bz)\n',
         '            _bz = re.sub(r"\\D", "", _bz)\n',
         A.require_role("하위관리자")),
    ]

    _ns = dict(vars(A))
    for _fn_name, _cur, _orig, _deco in _SITES:
        _body = _py_fn_body(_APP_SRC, _fn_name)
        assert _cur in _body, f"{_fn_name}: 되돌림 대상 정규화를 못 찾음(app.py 변경?)"
        _broken_body = _body.replace(_cur, _orig, 1)
        assert _broken_body != _body
        exec(compile(_broken_body, f"<r498_broken_{_fn_name}>", "exec"), _ns)  # noqa: S102 -- 실소스 그대로 추출, 디스크 미기록
        if _deco is None:
            #  기법3 — 공유헬퍼(clean_public_form·_auto_login_id). 맨이름으로
            #  부르는 실함수(api_create_lead·api_create_application·
            #  issue_partner_login)는 그대로 두고 실모듈 전역만 바꿔치기한다.
            setattr(A, _fn_name, _ns[_fn_name])
        else:
            A.app.view_functions[_fn_name] = _deco(_ns[_fn_name])

# ASCII 10자리 유효 사업자번호 + 잉여 유니코드 전각숫자 1개(총 11자) —
# valid_biz_no() 내부는 이 잉여문자를 [^0-9]로 지우고 10자리로 체크섬
# 통과시키지만(라운드497), 호출부 자신의 정규화가 [^0-9]로 통일되기
# 전(라운드497까지)에는 \D 기반이라 이 잉여문자를 못 지워 11자 그대로
# 저장되던 결함.
NOISY_BIZ = "1234567891" + "０"

cl = A.app.test_client()
with cl.session_transaction() as s:
    s['admin'] = 'a1'; s['admin_role'] = '최고관리자'; s['_csrf'] = 'c1'
r = cl.patch(f'/api/partners/{pid2}',
             json={'biz_no': NOISY_BIZ, 'status': '활성',
                   'status_reason': '심사완료함'},
             headers={'X-CSRF-Token': 'c1'})
resp = r.get_json() or {}

conn = A.DB.get_db()
active_count = conn.execute(
    "SELECT COUNT(*) n FROM partners WHERE status='활성'").fetchone()["n"]
p2 = dict(conn.execute("SELECT status, biz_no FROM partners WHERE id=?", (pid2,)).fetchone())
conn.close()
print(json.dumps({
    'status': r.status_code,
    'code': resp.get('code'),
    'active_count': active_count,
    'p2_status': p2['status'],
    'p2_biz_no': p2['biz_no'],
    'p2_biz_no_len': len(p2['biz_no']) if p2['biz_no'] else 0,
}))
