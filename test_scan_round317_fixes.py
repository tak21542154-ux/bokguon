# -*- coding: utf-8 -*-
"""스캔 317라운드 회귀 — legal_docs.py 처리방침의 보안 설정 수치 3종(로그인잠금
   횟수·세션만료 시간·접속기록 보관기간)이 실제 운영 환경변수와 연동되지 않고
   순수 리터럴("5회"·"30분"·"2년")로 박혀 있던 결함[컴플라이언스], 이 세션 사상
   첫 정밀조사한 정밀조사 Agent가 발견(legal_docs.py 는 Finding 2 로 이미 알려진
   보류항목이 있는 파일인데, 그와 무관한 새 각도).

   app.py 는 BOKGUON_MAX_LOGIN_FAILS·BOKGUON_SESSION_MIN·BOKGUON_LOG_RETENTION_DAYS
   환경변수로 이 세 값을 실제로 제어하고, .env.example 은 배포 규모에 맞춰
   조정하라고 명시적으로 안내한다(예: 5만명 미만 소규모는 보관기간 365일로
   낮춤). 그런데 처리방침 문구는 이 조정과 무관하게 항상 "5회"·"30분"·"2년"만
   말했다 — 이 파일이 이미 같은 패턴(IP제한 유무·하자담보책임기간)을 두 번
   고친 전례가 있는데, 이 세 자리만 그 교훈을 못 받았다.

   IP제한(_IP_ON/_IP_OFF)·하자담보책임기간(289라운드)과 같은 방식으로,
   privacy_body() 가 세 값을 인자로 받아 실제 운영값을 반영하도록 확장했다
   (기본값은 옛 고정 문구와 동일해 안 넘기는 호출부는 회귀 없음).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import legal_docs as LEGAL  # noqa: E402

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


def _pb(*a, **kw):
    """privacy_body() 안전 호출 — 되돌린 옛 시그니처(kwarg 미지원)에서도
    TypeError 로 스크립트 전체가 죽지 않고 이후 검사가 전부 깨끗하게 [FAIL]
    나도록(크래시 아님) 감싼다."""
    try:
        return LEGAL.privacy_body(*a, **kw)
    except TypeError:
        return ""


print("=" * 74)
print("  스캔 317라운드 회귀 — legal_docs.py 보안설정 수치 고정문구")
print("=" * 74)

print("\n[1] 실행 — 기본값(인자 생략)은 옛 고정 문구와 완전히 동일(회귀 없음)")
default_body = LEGAL.privacy_body(True)
old_call_body = LEGAL.PRIVACY  # IP 제한 켜짐일 때는 원본 PRIVACY 그대로였다
chk(default_body == old_call_body,
    "★★★★ 인자 없이 부르면(기존 test_feature_work_coverage.py 호출부와 동일) "
    "본문이 원본 PRIVACY 와 완전히 같다")
chk("2년" in default_body and "5회 연속 오류" in default_body and "30분" in default_body,
    "  기본값 문구(2년·5회·30분)가 그대로 보존된다")

print("\n[2] 실행 — 커스텀 운영값을 넘기면 본문에 실제로 반영된다")
custom = _pb(True, max_login_fails=3, session_min=15, log_retention_days=365)
chk("3회 연속 오류" in custom, "★★★★★ 로그인잠금 횟수(3회)가 반영된다")
chk("15분 무동작" in custom and "15분간 활동이 없으면" in custom,
    "★★★★★ 세션 만료 시간(15분)이 두 자리(접근통제 표·쿠키 안내) 모두 반영된다")
chk("<td><b>1년</b></td>" in custom, "★★★★★ 로그 보관기간(365일→1년)이 제3조 표에 반영된다")
chk("취급자의 접속 기록을 1년 이상 보관" in custom,
    "★★★★★ 로그 보관기간이 제7조 안전성확보조치 문단에도 함께 반영된다"
    "(형제 자리 — 처음엔 이 자리도 같은 값을 말한다는 걸 놓치기 쉽다)")
chk("5회 연속 오류" not in custom and "30분" not in custom and "<td><b>2년</b></td>" not in custom,
    "★★★★ 옛 고정 문구(5회·30분·2년)는 커스텀 값을 넘기면 더는 안 남는다")

print("\n[3] 실행 — 365 로 안 나눠떨어지는 보관기간은 '일' 단위 그대로 표기")
odd = _pb(True, log_retention_days=400)
chk("<td><b>400일</b></td>" in odd, "  365 로 안 나눠떨어지면 억지로 'N년'으로 반올림하지 않는다", )
chk(hasattr(LEGAL, "_period_text") and LEGAL._period_text(730) == "2년"
    and LEGAL._period_text(365) == "1년" and LEGAL._period_text(400) == "400일",
    "★★★ _period_text() 자체 — 730→2년·365→1년·400→400일")

print("\n[4] 실행 — IP제한 문구와 독립적으로 동작(기존 기능 회귀 없음)")
off = _pb(False, max_login_fails=3)
chk("관리자 콘솔 접속 IP 제한" not in off and "3회 연속 오류" in off,
    "  IP제한 끄기 + 로그인잠금 커스텀을 동시에 적용해도 서로 간섭 없음")

print("\n[5] 실행 — 실제 /legal/privacy 라우트가 app.py 의 실제 환경변수 값을 반영한다")
try:
    import db as DB
    DB.init_db()
    import app as A
    client = A.app.test_client()
    r = client.get("/legal/privacy")
    body = r.get_data(as_text=True)
    chk(r.status_code == 200, "  /legal/privacy 200 응답")
    chk(f"{A.MAX_LOGIN_FAILS}회 연속 오류" in body,
        "★★★★ 실제 응답이 app.py 의 MAX_LOGIN_FAILS 값을 그대로 보여준다",
        A.MAX_LOGIN_FAILS)
    chk(LEGAL._period_text(A.ACCESS_LOG_RETENTION_DAYS) in body,
        "★★★★ 실제 응답이 app.py 의 ACCESS_LOG_RETENTION_DAYS 값을 그대로 보여준다",
        A.ACCESS_LOG_RETENTION_DAYS)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★ /legal/privacy 실제 응답 검증", f"{type(e).__name__} {e}")

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
