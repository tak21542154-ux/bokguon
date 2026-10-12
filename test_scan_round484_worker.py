# -*- coding: utf-8 -*-
"""라운드484 회귀 워커(test_scan_round484_fixes.py 전용 서브프로세스) —
스크래치 DB에서 실제 Flask 앱으로 12개 형제 경로 전부에 형식이 깨진
연락처("전화아님", 숫자로 시작하지 않아 RE_PHONE 실패)와 정상 연락처
("010-1234-5678")를 실제로 보내 그 결과를 그대로 출력한다. app.py의
현재 상태(고쳐진 것이든, R484_BROKEN=1 로 이 프로세스 안에서만 인메모리로
되돌린 것이든)를 그대로 반영한다 — 이 파일 자신은 절대 수정 대상이 아니다.
"""
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
_tmpdir = tempfile.mkdtemp(prefix="r484_worker_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB               # noqa: E402
DB.init_db()
conn = DB.get_db()
conn.execute("INSERT INTO admins(username,password_hash,name,role) "
             "VALUES('admin','x','검증','최고관리자')")
pid = conn.execute(
    "INSERT INTO partners(name,partner_type,status,lat,lng) "
    "VALUES('R484업체','시행사','활성',37.5,127.0)").lastrowid
iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R484보험','활성')").lastrowid
CATEGORY = "가드레일·방호울타리"   # WORK_MAJORS(app.py:15070)의 실제 표기 그대로
cid = conn.execute(
    "INSERT INTO cases(case_no,status,category,region,insurer_id,lat,lng) "
    "VALUES('26-484001','접수',?,'서울',?,37.5,127.0)", (CATEGORY, iid)).lastrowid
conn.commit()
conn.close()

import app as A                # noqa: E402

if os.environ.get("R484_BROKEN") == "1":
    #  ⚠⚠ [라운드626] 되돌림-증명용 — 실제 app.py 파일은 이 서브프로세스에서도
    #    전혀 안 건드린다(이전 버전은 메인 테스트 프로세스가 app.py 를 통째로
    #    디스크에 다시 썼다 finally 로 복원했다 — 477·509·라운드625가 세운
    #    "서브프로세스 안에서만 인메모리로 되돌린다" 방식을 12곳으로 일반화).
    #    11곳은 독립된 Flask 라우트라 기법1(view_functions 딕셔너리 스왑).
    #    _create_case() 만 다른(안 건드리는) 실라우트 2곳(api_insurer_case_create·
    #    api_v1_case_create)이 맨이름으로 부르는 공유헬퍼라 기법3(실모듈
    #    __dict__ 에 직접 exec) — 이 서브프로세스는 시나리오 실행 후 바로
    #    종료되므로 복원(restore)이 필요 없다(각 실행이 독립 프로세스).
    _APP_PATH = os.path.join(HERE, "app.py")
    _APP_SRC = io.open(_APP_PATH, encoding="utf-8").read()

    def _extract(src, start_marker, end_marker):
        a = src.find(start_marker)
        if a < 0:
            return ""
        e = src.find(end_marker, a)
        return src[a:e] if e > 0 else ""

    def _py_fn_body(src, fn_name):
        start = src.index(f"\ndef {fn_name}(")
        end = src.find("\ndef ", start + 1)
        dec = src.find("\n@app.", start + 1)
        if dec != -1 and (end == -1 or dec < end):
            end = dec
        return src[start:end if end != -1 else None]

    #  (fn_name, 블록 시작마커, 블록 끝마커, view_functions 에 되꽂을 때 씌울
    #   데코레이터 — None 이면 기법3(공유헬퍼) 을 뜻한다). 마커는
    #   test_scan_round484_fixes.py 의 SITES 와 문자 그대로 동일(그 파일의
    #   [1]이 이미 소스에 정확히 1번씩만 있음을 검증한다) — 손으로 옮겨적다
    #   어긋나는 사고를 피하려 그대로 복사.
    _SITES = [
        ("api_partner_profile_update",
         "            #  ⚠⚠ [라운드484] email과 짝인 RE_PHONE(5437행)이 12개 형제 경로",
         "            #  ⚠ [라운드80] RE_EMAIL 검사가 관리자 쪽 연락처 수정에만 있고 협력사\n",
         A.require_partner),
        ("api_insurer_profile_update",
         "            #  ⚠⚠ [라운드484] email과 짝인 RE_PHONE 검사가 없었다(협력사 자기",
         "            #  ⚠ [라운드80] RE_EMAIL 검사가 관리자 쪽 연락처 수정에만 있고 보험사\n",
         A.require_insurer),
        ("api_application_create",
         "    #  ⚠⚠ [라운드484] 형제(clean_public_form)는 RE_PHONE 으로 연락처 형식도",
         "    #  ⚠ [라운드80] 공개 폼(clean_public_form)은 RE_EMAIL 로 형식을 보는데\n",
         A.require_admin),
        ("api_partner_create",
         "    #  ⚠⚠ [라운드484] email과 짝인 RE_PHONE 검사가 이 직접등록엔 없었다.\n",
         "    #  ⚠ [라운드80] RE_EMAIL 검사가 연락처 수정에만 있고 이 직접등록엔 없었다",
         A.require_admin),
        ("api_insurer_create",
         "    #  ⚠⚠ [라운드484] email과 짝인 RE_PHONE 검사가 이 보험사 직접등록엔 없었다.\n",
         "    conn = DB.get_db()\n",
         A.require_role("최고관리자")),
        ("api_partner_update",
         "            #  ⚠⚠ [라운드484] email과 짝인 RE_PHONE 검사가 이 자리엔 없었다 —\n",
         "            #  ⚠ [라운드80] RE_EMAIL 검사가 연락처 수정(/api/contacts",
         A.require_admin),
        ("api_insurer_update",
         "            #  ⚠⚠ [라운드484] email과 짝인 RE_PHONE 검사가 이 자리엔 없었다.\n",
         "            v = _s(d[f], _R169_LIMITS[f]) if f in _R169_LIMITS else d[f]\n",
         A.require_role("최고관리자")),
        ("api_contact_update",
         "            #  ⚠⚠ [라운드484] email·email2와 짝인 RE_PHONE 검사가 이 자리엔 없었다.\n",
         "            if f in (\"email\", \"email2\") and v and not RE_EMAIL.match(v):\n",
         A.require_admin),
        ("api_contact_import",
         "                        #  ⚠⚠ [라운드484] email·email2와 짝인 RE_PHONE 검사가\n",
         "                        sets.append(f\"{field}=?\"); vals.append(v[:120])\n",
         A.require_admin),
        ("_create_case",
         "    #  ⚠⚠ [라운드484] partners·insurers.phone과 같은 결함",
         "    if _vn or _vp:\n",
         None),
        ("api_case_create",
         "    #  ⚠⚠ [라운드484] 형제(_create_case)와 같은 결함 — RE_PHONE 검사가 없어\n",
         "    if _vn or _vp:\n",
         A.require_admin),
        ("api_case_edit",
         "            #  ⚠⚠ [라운드484] 형제(_create_case·api_case_create)와 같은 결함 —\n",
         "            sets.append(f\"{f}=?\"); vals.append(nv)\n",
         A.require_role("중간관리자")),
    ]

    _ns = dict(vars(A))
    for _fn_name, _start, _end, _deco in _SITES:
        _block = _extract(_APP_SRC, _start, _end)
        assert _block, f"{_fn_name}: 블록을 못 뽑음(app.py 변경?)"
        _body = _py_fn_body(_APP_SRC, _fn_name)
        assert _block in _body, f"{_fn_name}: 대상 함수 안에 블록이 없음"
        _broken_body = _body.replace(_block, "", 1)
        assert _broken_body != _body
        exec(compile(_broken_body, f"<r484_broken_{_fn_name}>", "exec"), _ns)  # noqa: S102 -- 실소스 그대로 추출, 디스크 미기록
        if _deco is None:
            #  기법3 — 공유헬퍼(_create_case). 맨이름으로 부르는 실라우트
            #  (api_insurer_case_create·api_v1_case_create)는 그대로 두고 실모듈
            #  전역만 바꿔치기한다 — 그 실라우트들의 __globals__ 가 A.__dict__
            #  그 자체라 다음 호출부터 바로 반영된다.
            setattr(A, _fn_name, _ns[_fn_name])
        else:
            A.app.view_functions[_fn_name] = _deco(_ns[_fn_name])

BAD = "전화아님"
GOOD = "010-1234-5678"


def _admin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_name"] = "검증"
        sess["admin_role"] = "최고관리자"; sess["_csrf"] = "r484-csrf"
    return c


def _partner_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["partner_id"] = pid; sess["partner_name"] = "R484업체"
        sess["_csrf"] = "r484-csrf"
    return c


def _insurer_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["insurer_id"] = iid; sess["insurer_name"] = "R484보험"
        sess["_csrf"] = "r484-csrf"
    return c


H = {"X-CSRF-Token": "r484-csrf"}
admin_c = _admin_client()
out = {}

# A1 api_partner_create
r = admin_c.post("/api/partners", json={"name": "R484신규업체", "phone": BAD}, headers=H)
out["partner_create_bad"] = r.status_code
out["partner_create_bad_body"] = r.get_json()
r2 = admin_c.post("/api/partners", json={"name": "R484신규업체2", "phone": GOOD}, headers=H)
out["partner_create_good"] = r2.status_code

# A2 api_partner_update
r = admin_c.patch(f"/api/partners/{pid}", json={"phone": BAD}, headers=H)
out["partner_update_bad"] = r.status_code
out["partner_update_bad_body"] = r.get_json()

# A3 api_insurer_create
r = admin_c.post("/api/insurers", json={"name": "R484신규보험", "phone": BAD}, headers=H)
out["insurer_create_bad"] = r.status_code
out["insurer_create_bad_body"] = r.get_json()
r2 = admin_c.post("/api/insurers", json={"name": "R484신규보험2", "phone": GOOD}, headers=H)
out["insurer_create_good"] = r2.status_code

# A4 api_insurer_update
r = admin_c.patch(f"/api/insurers/{iid}", json={"phone": BAD}, headers=H)
out["insurer_update_bad"] = r.status_code
out["insurer_update_bad_body"] = r.get_json()

# A5 api_application_create
r = admin_c.post("/api/applications/manual",
                  json={"company": "R484신청사", "major": "금속", "phone": BAD}, headers=H)
out["application_create_bad"] = r.status_code
out["application_create_bad_body"] = r.get_json()

# A6 api_contact_update
r = admin_c.patch(f"/api/contacts/{pid}", json={"phone": BAD}, headers=H)
out["contact_update_bad"] = r.status_code
out["contact_update_bad_body"] = r.get_json()

# A7 api_contact_import (엑셀 일괄등록)
from openpyxl import Workbook
wb = Workbook()
ws = wb.active
ws.append(["업체명", "사업자번호", "이메일", "보조이메일", "연락처", "담당자", "메모", "홈페이지", "메일수신거부"])
ws.append(["R484업체", "", "", "", BAD, "", "", "", ""])
xlsx_path = os.path.join(_tmpdir, "import.xlsx")
wb.save(xlsx_path)
with open(xlsx_path, "rb") as f:
    r = admin_c.post("/api/contacts/import",
                      data={"file": (f, "import.xlsx")},
                      content_type="multipart/form-data", headers=H)
out["contact_import_status"] = r.status_code
out["contact_import_body"] = r.get_json()

# A8 api_case_create
r = admin_c.post("/api/cases",
                  json={"case_no": "26-484002", "category": CATEGORY, "insurer_id": iid,
                        "est_price": 500000, "victim_phone": BAD}, headers=H)
out["case_create_bad"] = r.status_code
out["case_create_body"] = r.get_json()

# A9 api_case_edit
r = admin_c.patch(f"/api/cases/{cid}", json={"victim_phone": BAD}, headers=H)
out["case_edit_bad"] = r.status_code
out["case_edit_bad_body"] = r.get_json()

# B1 api_partner_profile_update
partner_c = _partner_client()
r = partner_c.patch("/api/partner/profile", json={"phone": BAD}, headers=H)
out["partner_profile_bad"] = r.status_code
out["partner_profile_bad_body"] = r.get_json()

# C1 api_insurer_profile_update
insurer_c = _insurer_client()
r = insurer_c.patch("/api/insurer/profile", json={"phone": BAD}, headers=H)
out["insurer_profile_bad"] = r.status_code
out["insurer_profile_bad_body"] = r.get_json()

# C2 api_insurer_case_create -> _create_case (victim_phone)
r = insurer_c.post("/api/insurer/cases",
                    json={"category": CATEGORY, "no_photo": True, "victim_phone": BAD}, headers=H)
out["insurer_case_create_bad"] = r.status_code
out["insurer_case_create_body"] = r.get_json()

print(json.dumps(out, ensure_ascii=False))
