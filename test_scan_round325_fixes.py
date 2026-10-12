# -*- coding: utf-8 -*-
"""스캔 325라운드 회귀 — api_admin_update()(관리자 계정 등급/비밀번호/이름
   수정, app.py:1656) 의 이름 변경 분기만 감사로그가 없던 결함[중간],
   이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견(324라운드에 이어
   app.py 최상위 함수 480개를 다시 AST로 재구성해 이번엔 "가장 가까운
   라운드 수정 주석까지의 줄 거리"로 감사밀도를 계산 — 관리자 계정 관리
   클러스터(app.py 1612-1733행)가 주변 144~186줄 안에 라운드 주석이
   전무한 완전 미검증 구역이었음을 확인).

   같은 함수 안에서 형제 두 분기(등급 변경·비밀번호 재발급)는 각각
   DB.log() 를 남기는데, 이름 변경 분기만 UPDATE 뒤 아무 흔적도 안
   남긴다 — 완전히 동일한 동작(이름 수정)을 하는 자기계정용 쌍둥이
   함수 api_me_update()(app.py:1722, "내 정보 수정")조차 DB.log 를
   남기는 것과도 대비된다. 최고관리자(또는 탈취된 세션)가 **다른**
   관리자의 표시 이름을 바꿔도 activity_log 에 무엇을 바꿨는지 전혀
   남지 않아, 사칭·혼선 유도 뒤 추적이 불가능했다. 형제와 같은
   DB.log() 호출을 추가.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_scratch = tempfile.mkdtemp(prefix="bokguon_r325_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_scratch, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"

PASS = FAIL = 0
FAILED = []


def chk(cond, msg, detail=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {msg}")
    else:
        FAIL += 1
        FAILED.append(msg)
        print(f"  [FAIL] {msg}" + (f"   {detail}" if detail else ""))


print("=" * 74)
print("  스캔 325라운드 회귀 — api_admin_update() 이름 변경 분기 감사로그 누락")
print("=" * 74)

import db as DB  # noqa: E402
DB.init_db(seed_demo=True)
import app as A  # noqa: E402

print("\n[1] 준비 — 실제 관리자 2명(행위자·대상) 확인")
staff = DB.get_db().execute("SELECT id, username, name FROM admins WHERE username='staff'").fetchone()
chk(staff is not None, "  시드 데이터의 'staff' 계정을 찾았다(대상 계정으로 사용)")
target_aid = staff["id"]
old_name = staff["name"]

app_client = A.app.test_client()
_tok = "r325-admin-csrf"
with app_client.session_transaction() as sess:
    sess["admin"] = "admin"
    sess["admin_role"] = "최고관리자"
    sess["_csrf"] = _tok
_hdr = {"X-CSRF-Token": _tok}

print("\n[2] 실행 — 최고관리자가 '다른' 관리자(staff)의 이름을 바꾼다")
r = app_client.patch(f"/api/admins/{target_aid}", headers=_hdr, json={"name": "새이름테스트"})
chk(r.status_code == 200 and r.get_json().get("ok") is True,
    "  이름 변경 자체는 정상 200/ok", (r.status_code, r.get_data(as_text=True)))

after = DB.get_db().execute("SELECT name FROM admins WHERE id=?", (target_aid,)).fetchone()
chk(after["name"] == "새이름테스트", "  DB 상 실제로 이름이 바뀌었다", after["name"])

log_row = DB.get_db().execute(
    "SELECT action, detail FROM activity_log WHERE action='관리자 이름 변경' ORDER BY id DESC LIMIT 1"
).fetchone()
chk(log_row is not None,
    "★★★★★ 이름 변경 감사로그가 실제로 남는다"
    "(고치기 전엔 UPDATE 뒤 아무 흔적도 안 남았다)")
if log_row:
    chk("staff" in log_row["detail"] and old_name in log_row["detail"] and "새이름테스트" in log_row["detail"],
        "★★★★ 감사로그 detail 에 대상 계정·이전이름·새이름이 전부 들어간다",
        log_row["detail"])

print("\n[3] 실행 — 형제 분기(등급 변경·비밀번호 재발급)는 회귀 없이 그대로 로그를 남긴다")
r_role = app_client.patch(f"/api/admins/{target_aid}", headers=_hdr, json={"role": "최고관리자"})
chk(r_role.status_code == 200, "  등급 변경 자체는 정상 200", r_role.status_code)
role_log = DB.get_db().execute(
    "SELECT detail FROM activity_log WHERE action='관리자 등급 변경' ORDER BY id DESC LIMIT 1"
).fetchone()
chk(role_log is not None and "staff" in role_log["detail"],
    "  등급 변경 감사로그는 회귀 없이 그대로 남는다(기존 동작)", role_log)

r_pw = app_client.patch(f"/api/admins/{target_aid}", headers=_hdr, json={"reset_pw": True})
chk(r_pw.status_code == 200 and r_pw.get_json().get("temp_password"),
    "  비밀번호 재발급 자체는 정상 200 + 임시비번 반환", r_pw.status_code)
pw_log = DB.get_db().execute(
    "SELECT detail FROM activity_log WHERE action='관리자 비밀번호 재발급' ORDER BY id DESC LIMIT 1"
).fetchone()
chk(pw_log is not None and pw_log["detail"] == "staff",
    "  비밀번호 재발급 감사로그도 회귀 없이 그대로 남는다(기존 동작)", pw_log)

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
