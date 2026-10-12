# -*- coding: utf-8 -*-
"""라운드510 회귀 워커(test_scan_round510_fixes.py 전용 서브프로세스) —
스크래치 DB에서 실제 Flask 앱으로 partners.website 의 세 진입로
(api_partner_create·api_partner_update·api_contact_import 엑셀 일괄등록)
전부에 "스킴 이름 한가운데 탭/개행을 끼운 javascript:" 페이로드와 정상 값을
실제로 보내 그 결과를 그대로 출력한다.

  인자로 "--revert" 를 주면, valid_website() 를 **라운드510 이전(라운드509
  까지의) 구현으로 런타임에 되돌린** 뒤 같은 배터리를 돈다 — app.py 파일
  자체는 건드리지 않고 이미 임포트된 함수 객체만 메모리에서 바꿔치기한다
  (이 함수는 DB·세션 등 외부 상태가 없는 순수 함수라 이 방식이 안전하고,
  파일을 잠깐 고쳤다 복원하는 서브프로세스 재기동 방식보다 더 단순하다).
  되돌린 구현은 라운드509가 실제로 남긴 코드(정규식 문자클래스에 탭·개행이
  없어 스킴 이름 한가운데 탭이 끼면 매치에 실패해 "스킴 없음"으로 오판하는
  버전)를 그대로 재현한다.
"""
import io
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
_tmpdir = tempfile.mkdtemp(prefix="r510_worker_")
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
    "VALUES('R510업체','시행사','활성',37.5,127.0)").lastrowid
conn.commit()
conn.close()

import app as A                # noqa: E402

if "--revert" in sys.argv:
    #  라운드509 까지의 valid_website() — 문자열을 그대로 정규식에 넣는다
    #  (탭·개행을 먼저 지우는 라운드510 의 re.sub 한 줄이 없다).
    _OLD_RE = re.compile(r"^\s*([a-zA-Z][a-zA-Z0-9+.\-]*):")

    def _old_valid_website(v):
        m = _OLD_RE.match(v or "")
        return not (m and m.group(1).lower() not in ("http", "https"))

    A.valid_website = _old_valid_website

#  스킴 이름("java" 와 "script:" 사이) 한가운데 탭 한 글자를 끼운 페이로드 —
#  esc() 가 막는 5글자(&<>"')를 하나도 안 쓰고, 브라우저는 스킴 판정 전에
#  이 탭을 지우므로 클릭하면 실제로 실행된다(이 세션이 실제 브라우저로
#  실측 확인).
XSS_TAB = "java\tscript:alert(document.cookie)"
XSS_NL = "java\nscript:alert(document.cookie)"
GOOD_HTTPS = "https://example.com"
GOOD_BARE = "example.com"          # 스킴 없음 — 과잉차단이면 안 된다


def _lowadmin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "lowadmin"; sess["admin_name"] = "말단직원"
        sess["admin_role"] = "하위관리자"; sess["_csrf"] = "r510-csrf"
    return c


H = {"X-CSRF-Token": "r510-csrf"}
c = _lowadmin_client()
out = {}

# [1] api_partner_create — 탭이 낀 스킴 페이로드
r = c.post("/api/partners", json={"name": "R510신규A", "website": XSS_TAB}, headers=H)
out["create_tab_status"] = r.status_code
out["create_tab_body"] = r.get_json()
r = c.post("/api/partners", json={"name": "R510신규B", "website": GOOD_HTTPS}, headers=H)
out["create_good_status"] = r.status_code

# [2] api_partner_update — 탭이 낀 스킴 페이로드 (기존 업체 pid)
r = c.patch(f"/api/partners/{pid}", json={"website": XSS_TAB}, headers=H)
out["update_tab_status"] = r.status_code
out["update_tab_body"] = r.get_json()
conn2 = DB.get_db()
out["db_website_after_tab_attempt"] = (conn2.execute(
    "SELECT website FROM partners WHERE id=?", (pid,)).fetchone() or {"website": None})["website"]
conn2.close()
# 개행이 낀 변형도 같은 함수를 타므로 한 번 더(엑셀 Alt+Enter 로 쉽게 생기는 모양)
r = c.patch(f"/api/partners/{pid}", json={"website": XSS_NL}, headers=H)
out["update_nl_status"] = r.status_code
r = c.patch(f"/api/partners/{pid}", json={"website": GOOD_HTTPS}, headers=H)
out["update_good_status"] = r.status_code
conn3 = DB.get_db()
out["db_website_after_good"] = (conn3.execute(
    "SELECT website FROM partners WHERE id=?", (pid,)).fetchone() or {"website": None})["website"]
conn3.close()

# [3] api_contact_import — 엑셀 일괄등록의 "홈페이지" 열에 개행이 낀 스킴
#     (엑셀 셀은 Alt+Enter 로 개행을 쉽게 담을 수 있다 — 탭보다도 더 자연스러운 입력 경로)
from openpyxl import Workbook
wb = Workbook()
ws = wb.active
ws.append(["업체명", "사업자번호", "이메일", "보조이메일", "연락처", "담당자", "메모", "홈페이지", "메일수신거부"])
ws.append(["R510업체", "", "", "", "", "", "", XSS_NL, ""])
xlsx_path = os.path.join(_tmpdir, "import.xlsx")
wb.save(xlsx_path)
with open(xlsx_path, "rb") as f:
    r = c.post("/api/contacts/import", data={"file": (f, "import.xlsx")},
               content_type="multipart/form-data", headers=H)
out["import_nl_status"] = r.status_code
out["import_nl_body"] = r.get_json()
conn4 = DB.get_db()
out["db_website_after_import_nl"] = (conn4.execute(
    "SELECT website FROM partners WHERE id=?", (pid,)).fetchone() or {"website": None})["website"]
conn4.close()

# 정상 값(스킴 없는 도메인)은 엑셀 일괄등록으로도 그대로 통과해야 한다(과잉차단 아님)
wb2 = Workbook()
ws2 = wb2.active
ws2.append(["업체명", "사업자번호", "이메일", "보조이메일", "연락처", "담당자", "메모", "홈페이지", "메일수신거부"])
ws2.append(["R510업체", "", "", "", "", "", "", GOOD_BARE, ""])
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
