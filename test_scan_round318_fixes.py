# -*- coding: utf-8 -*-
"""스캔 318라운드 회귀 — 사건 감사로그를 LIKE '%접수번호%' 로 찾는 3곳이 다른
   사건 접수번호의 부분열에 걸려 서로 오염되던 결함[심각] + error.html 의
   {{ msg|safe }} 가 필요 없는 6곳까지 이스케이프를 꺼 두던 결함[경미,잠재적],
   이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견(자체 재구성 기법으로
   templates/case_history.html 을 찾아냄 — 어느 라운드 설명에도 주 타겟으로
   등장한 적이 없었다).

   activity_log 는 case_id 외래키가 없어(db.py 스키마), 사건 감사로그를
   `detail LIKE '%접수번호%'` 로 찾는다(사건 이력 리포트·정산 상세 타임라인·
   재알림 30분 쿨다운, 3곳 전부 동일 패턴). 접수번호는 발주처가 직접 정하고
   (app.py:_create_case, 형식 검증 없음) 20자 이내 자유입력만 막지 않으면 뭐든
   저장된다 — 접수번호 하나가 다른 접수번호의 부분열이면(예: "1023"과 "10234")
   LIKE 는 둘을 구분 못 한다. 이 문서(사건 이력 리포트)는 발주처에게 그대로
   건네질 수 있어(라우트 자신의 '철칙 4') 무관한 사건의 확정 낙찰금액·시공사명이
   섞여 나갈 수 있다. geo.py 의 지명 경계판정(_word_in)과 같은 원리로, LIKE 로
   후보만 거른 뒤 파이썬에서 앞뒤가 숫자·영문이 아닐 때만 진짜 일치로 인정하는
   _case_no_in_detail() 을 만들어 세 곳 모두에 적용했다.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_scratch = tempfile.mkdtemp(prefix="bokguon_r318_")
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
print("  스캔 318라운드 회귀 — 사건 감사로그 부분열 오염 + error.html 과잉 |safe")
print("=" * 74)

print("\n[1] 실행 — _case_no_in_detail() 경계검사 자체(순수 함수, DB 불필요)")
import db as DB  # noqa: E402
DB.init_db(seed_demo=True)
import app as A  # noqa: E402

chk(A._case_no_in_detail("10234 낙찰 확정 5,500만원 (주)OO건설", "1023") is False,
    "★★★★★ '1023' 이 '10234'(뒤에 붙은 접수번호)의 로그와는 매치되지 않는다")
chk(A._case_no_in_detail("1023 접수 확인", "1023") is True,
    "★★★★★ '1023' 자기 자신의 로그와는 정상적으로 매치된다")
chk(A._case_no_in_detail("공고 91023 마감", "1023") is False,
    "★★★ 앞에 숫자가 더 붙은 경우(91023)도 매치되지 않는다(양방향 경계)")
chk(A._case_no_in_detail("[26-80001] 낙찰 승인", "26-80001") is True,
    "★★★ 하이픈이 든 실제 채번 형식(26-80001)도 정상 매치(대괄호는 경계로 인정)")
chk(A._case_no_in_detail("26-800012 낙찰", "26-80001") is False,
    "★★★ 채번 형식 뒤에 숫자가 더 붙어도(26-800012) 매치되지 않는다")
chk(A._case_no_in_detail("", "1023") is False and A._case_no_in_detail("1023 접수", "") is False,
    "  빈 문자열 입력은 매치되지 않는다(예외 없이)")

print("\n[2] 준비 — 실제 부분열 충돌 사건 2건 생성 + 실제 DB.log() 형식의 감사로그")
conn = DB.get_db()
conn.execute("BEGIN IMMEDIATE")
now = DB.now()
cur1 = conn.execute(
    "INSERT INTO cases(case_no,insurer,category,region,address,status,award_amount,is_demo,created_at,status_at)"
    " VALUES(?,?,?,?,?,?,?,0,?,?)",
    ("1023", "테스트보험", "유리·샷시·자동문", "서울", "서울시 강남구", "정산대기", 300000, now, now))
cid1 = cur1.lastrowid
cur2 = conn.execute(
    "INSERT INTO cases(case_no,insurer,category,region,address,status,award_amount,is_demo,created_at,status_at)"
    " VALUES(?,?,?,?,?,?,?,0,?,?)",
    ("10234", "테스트보험", "누수·배관·설비", "부산", "부산시 해운대구", "정산대기", 55000000, now, now))
cid2 = cur2.lastrowid
DB.log(conn, "테스트관리자", "사건 등록(직접등록)", "1023 · 유리·샷시·자동문")
DB.log(conn, "관리자", "낙찰 승인", "10234 → (주)OO건설 55,000,000원")
conn.commit()

print("\n[3] 실행 — 형제 두 곳(정산 상세 타임라인·재알림 쿨다운)도 같은 헬퍼로 동일 원리 확인")
#  ⚠ 이 확인은 라우트를 부르기 **전에** 한다 — case_history_report() 자신도
#    "이 문서를 뽑았다"는 로그를 새로 남기므로(라우트 독스트링에 명시), 뒤에서
#    /report/case 를 부른 뒤에 검사하면 그 자기로그까지 후보에 섞여 "부분열
#    오염 후보 2건·진짜 1건"이라는 이 단계의 취지가 흐려진다.
DB_SRC = open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
_settle_start = DB_SRC.index("def api_settlement_detail(")
_settle_end = DB_SRC.index("\ndef ", _settle_start + 10)
_renotify_start = DB_SRC.index("def api_case_renotify(")
_renotify_end = DB_SRC.index("\ndef ", _renotify_start + 10)
chk("_case_no_in_detail(r[\"detail\"], s[\"case_no\"])" in DB_SRC[_settle_start:_settle_end],
    "★★★★ api_settlement_detail() 도 경계검사 헬퍼를 실제로 쓴다")
chk("_case_no_in_detail(r[\"detail\"], c[\"case_no\"])" in DB_SRC[_renotify_start:_renotify_end],
    "★★★★ api_case_renotify() 도 경계검사 헬퍼를 실제로 쓴다"
    "(고치기 전엔 부분열 충돌로 정당한 재알림이 남의 쿨다운에 막힐 수 있었다)")
# 같은 픽스처로 실제 정산 타임라인 쿼리를 그대로 재현해 결과 확인
timeline_candidates = DB.get_db().execute(
    "SELECT detail FROM activity_log WHERE detail LIKE ? ESCAPE '\\'",
    (f"%{A._like_escape('1023')}%",)).fetchall()
timeline_filtered = [r for r in timeline_candidates if A._case_no_in_detail(r["detail"], "1023")]
chk(len(timeline_candidates) == 2 and len(timeline_filtered) == 1,
    "★★★★★ 같은 쿼리를 실행하면 LIKE 후보는 2건(부분열 오염 포함)이지만 "
    "경계검사를 거치면 진짜 1건만 남는다(실측)",
    (len(timeline_candidates), len(timeline_filtered)))

print("\n[4] 실행 — 실제 /report/case/<id> 라우트(case_no='1023')가 남의 낙찰금액을 안 보여준다")
app_client = A.app.test_client()
row = DB.get_db().execute(
    "SELECT username FROM admins LIMIT 1").fetchone()
with app_client.session_transaction() as sess:
    sess["admin"] = row["username"] if row else "admin"
r = app_client.get(f"/report/case/{cid1}")
body = r.get_data(as_text=True)
chk(r.status_code == 200, "  /report/case 200 응답", r.status_code)
chk("OO건설" not in body and "55,000,000" not in body,
    "★★★★★ 사건 1023 의 리포트에 무관한 사건(10234)의 낙찰업체·금액이 안 보인다"
    "(고치기 전엔 부분열 매치로 여기 섞여 들어왔다)")
chk("유리·샷시·자동문" in body,
    "  사건 1023 자기 자신의 로그(사건 등록)는 정상적으로 보인다")

print("\n[5] 실행 — 반대 방향(사건 10234 의 리포트)도 남의 로그가 안 섞인다(대조군)")
r2 = app_client.get(f"/report/case/{cid2}")
body2 = r2.get_data(as_text=True)
chk("사건 등록" not in body2 or "1023 ·" not in body2,
    "  사건 10234 의 리포트에 무관한 사건(1023)의 등록 로그가 안 섞인다", r2.status_code)

print("\n[6] 실행 — error.html 은 이제 기본 이스케이프, ref 만 명시적으로 안전 표시")
with A.app.test_request_context("/"):
    from flask import render_template as _rt
    html_plain = _rt("error.html", code=404, title="테스트", msg="일반 문구 <script>없음</script>")
    chk("&lt;script&gt;" in html_plain and "<script>없음</script>" not in html_plain,
        "★★★★★ 일반 문자열 msg 는 이제 이스케이프된다(고치기 전엔 |safe 로 그대로 삽입됐다)")
    html_ref = _rt("error.html", code=500, title="테스트",
                   msg=A.Markup("문제가 계속되면 오류번호 <b>{}</b> 를 알려주세요.")
                       .format(A.escape("ab12cd34")))
    chk("<b>ab12cd34</b>" in html_ref,
        "★★★ Markup 으로 명시적으로 표시한 곳(오류번호)은 여전히 굵게 나온다(회귀 없음)")

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
