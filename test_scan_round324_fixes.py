# -*- coding: utf-8 -*-
"""스캔 324라운드 회귀 — api_case_coords()(사건 좌표 수동 입력·해제) 결함 2건,
   이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견(app.py 최상위 def/route
   480개를 AST로 추출해 test_scan_round2~323 전체와 대조 — 174개가 이름으로
   개별 언급된 적 없음을 확인, 그중 도급관문 GET 4종·알림읽음 2종·하위계정
   CRUD 10종·출동배차 상태머신·OTP 2단계인증은 기존 require_role/err_500
   전역방어로 이미 안전함을 확인해 클린 처리 — 정당한 결과).

   ① [중간] 사건 스코프 라우트 중 유일하게 UPDATE 전에 cases 행을 조회하지
      않는다 — 존재하지 않는 cid 를 줘도 UPDATE 0행 뒤 그대로 {"ok":true}를
      반환해 오타를 운영자가 못 알아챈다.
   ② [중간] DB.log() 의 detail 을 f"case {cid}"(내부 숫자 PK)로 남겨,
      사건별 감사 이력을 찾는 유일한 통로인 case_history_report()의
      `detail LIKE '%'||case_no||'%'` + `_case_no_in_detail()` 경계검사(318
      라운드가 세운 관행 — 90여 곳 DB.log() 호출부가 case_no 를 맨 앞에
      두는 것과 같은 원리)와 애초에 형식이 달라 100% 매치 실패한다(318
      라운드의 "부분열끼리 충돌"과 달리 이쪽은 "애초에 case_no 문자열 자체가
      detail 에 없어 무조건 못 찾음" — 더 확실한 블라인드 스팟). 좌표를
      잘못 입력했다가 고친 이력이 그 사건의 분쟁 소명 리포트에 영원히 안
      나타난다(전역 활동로그에는 남아있어 안 지워졌다는 것 자체는 확인
      가능하지만, 사건 단위로는 못 찾음).
   두 곳 다 sibling 호출부(app.py:9590, 18080)와 같은 관행으로 통일 —
   함수 시작에 case_no 조회+404 가드를 추가하고, DB.log 의 detail 을
   c["case_no"] 기반으로 교체.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_scratch = tempfile.mkdtemp(prefix="bokguon_r324_")
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
print("  스캔 324라운드 회귀 — api_case_coords() 무경비 UPDATE + 감사로그 형식이탈")
print("=" * 74)

import db as DB  # noqa: E402
DB.init_db(seed_demo=True)
import app as A  # noqa: E402

print("\n[1] 준비 — 실제 사건 1건 생성")
conn = DB.get_db()
conn.execute("BEGIN IMMEDIATE")
now = DB.now()
CASE_NO = "26-99001"
cur = conn.execute(
    "INSERT INTO cases(case_no,insurer,category,region,address,status,is_demo,created_at,status_at)"
    " VALUES(?,?,?,?,?,?,0,?,?)",
    (CASE_NO, "테스트보험", "누수·배관·설비", "서울", "서울시 강남구", "정산대기", now, now))
cid = cur.lastrowid
conn.commit()

app_client = A.app.test_client()
row = DB.get_db().execute("SELECT username FROM admins LIMIT 1").fetchone()
_tok = "r324-admin-csrf"
with app_client.session_transaction() as sess:
    sess["admin"] = row["username"] if row else "admin"
    sess["admin_role"] = "최고관리자"
    sess["_csrf"] = _tok
_hdr = {"X-CSRF-Token": _tok}

print("\n[2] 실행 — 존재하지 않는 사건 id 로 좌표를 입력하면 조용히 성공하지 않는다")
r_missing = app_client.post("/api/cases/999999999/coords", headers=_hdr, json={"lat": 37.5, "lng": 127.0})
chk(r_missing.status_code == 404,
    "★★★★ 존재하지 않는 cid 는 404 를 낸다(고치기 전엔 UPDATE 0행 뒤에도 200/ok:true 였다)",
    r_missing.status_code)

print("\n[3] 실행 — 실제 사건에 좌표를 입력하면 감사로그 detail 에 접수번호가 들어간다")
r_set = app_client.post(f"/api/cases/{cid}/coords", headers=_hdr, json={"lat": 37.55, "lng": 127.05})
chk(r_set.status_code == 200 and r_set.get_json().get("ok") is True,
    "  좌표 입력 자체는 정상 200/ok", (r_set.status_code, r_set.get_data(as_text=True)))

logs_after_set = DB.get_db().execute(
    "SELECT action, detail FROM activity_log WHERE action='사건 좌표 입력' ORDER BY id DESC LIMIT 1"
).fetchone()
chk(logs_after_set is not None and A._case_no_in_detail(logs_after_set["detail"], CASE_NO),
    "★★★★★ 좌표 입력 감사로그의 detail 이 접수번호 경계검사를 통과한다"
    "(고치기 전엔 'case 123' 형식이라 case_no 문자열 자체가 없어 무조건 실패했다)",
    logs_after_set["detail"] if logs_after_set else None)

print("\n[4] 실행 — 좌표를 해제해도 감사로그 detail 에 접수번호가 들어간다")
r_clear = app_client.post(f"/api/cases/{cid}/coords", headers=_hdr, json={"clear": True})
chk(r_clear.status_code == 200 and r_clear.get_json().get("ok") is True,
    "  좌표 해제 자체는 정상 200/ok", r_clear.status_code)

logs_after_clear = DB.get_db().execute(
    "SELECT action, detail FROM activity_log WHERE action='사건 좌표 해제' ORDER BY id DESC LIMIT 1"
).fetchone()
chk(logs_after_clear is not None and A._case_no_in_detail(logs_after_clear["detail"], CASE_NO),
    "★★★★★ 좌표 해제 감사로그의 detail 도 접수번호 경계검사를 통과한다",
    logs_after_clear["detail"] if logs_after_clear else None)

print("\n[5] 실행 — 실제 /report/case/<id>(이 사건의 분쟁 소명 리포트)에 두 로그가 이제 나타난다")
r_report = app_client.get(f"/report/case/{cid}")
body = r_report.get_data(as_text=True)
chk(r_report.status_code == 200, "  /report/case 200 응답", r_report.status_code)
chk("사건 좌표 입력" in body,
    "★★★★★ 좌표 입력 이력이 이 사건의 리포트에 나타난다"
    "(고치기 전엔 detail 형식이 달라 case_history_report() 의 LIKE 필터에 전혀 안 걸렸다)")
chk("사건 좌표 해제" in body,
    "★★★★★ 좌표 해제 이력도 이 사건의 리포트에 나타난다")

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
