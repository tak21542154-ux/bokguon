# -*- coding: utf-8 -*-
"""스캔 564라운드 회귀 — 보험사 월 정산 명세서 기본 조회월(_stmt_period_args)이
   자기 자신의 문서("없으면 지난달")와 실제 동작("없으면 이번 달")이 어긋나던 결함.

   조사 각도 — 오케스트레이터가 제시한 신선한 각도 중 "보험사 statement/정산내역서
   생성이 청구기간 경계에서 정확한가"를 따라가다 발견. _stmt_period_args() 의
   docstring 은 "?year=&month= 파싱 — 없으면 지난달(정산은 보통 월 마감 후 다음
   달에 뽑는다)"이라고 스스로 적어 두고 있는데, 실제 구현은 파라미터가 없을 때
   now.year/now.month(이번 달, 진행 중이라 아직 안 끝난 달)를 그대로 돌려주고
   있었다 — 자기 문서와 정반대로 동작한다.

   왜 문제인가 — 이 헬퍼는 보험사 자기조회 JSON(GET /api/insurer/statement,
   api_insurer_statement_self)·자기조회 엑셀(GET /api/insurer/statement/export)·
   어드민 조회(GET /api/insurer-statement)·어드민 엑셀(GET /api/insurer-statement/
   export) 4곳이 공유하는 유일한 파라미터 파서다. 어드민 화면(admin.js)과 보험사
   포털(insurer_portal.html)의 <select> 는 둘 다 매번 year·month 를 명시적으로
   붙여 보내 이 기본값 경로를 평소엔 타지 않지만, 이 GET 엔드포인트는 파라미터
   없이도 호출 가능한 JSON API 이고 실제로 기존 회귀테스트 두 개
   (test_scan_round96_fixes.py:139, test_scan_round534_fixes.py:207/222)가 이미
   파라미터 없이 이 경로를 부른다 — 즉 "파라미터 생략" 은 이 API 의 실제 호출
   표면이다. 그 상태로 "이번 달"이 기본값이면, 월이 다 지나기도 전에 아직 안
   끝난 정산 숫자를 '월 정산 명세서' 라는 이름으로 내려주고, 정작 방금 마감된
   지난달(문서가 원래 의도한 값)은 명시 파라미터 없이는 볼 수 없다.

   고침 — app.py:_stmt_period_args(). now.year/now.month 기본값을, 이번 달 1일에서
   하루를 뺀 지난달(연도 경계도 함께 넘어간다 — 1월이면 자동으로 작년 12월)로
   바꿨다. 단일 공유 지점 하나만 고치면 4개 호출부 전부 동시에 맞는다. 명시
   ?year=&month= 파라미터 우선순위·1~12 범위검사 폴백 구조는 그대로 둔다(회귀 없음).

   이 회귀테스트는 ONLY 안전한 기법만 쓴다 — on-disk app.py 는 조회만 하고,
   "되돌리기" 증명은 옛(이번 달 기본값) _stmt_period_args 리터럴만 별도 문자열로
   재구성해 exec() 한 뒤, 실제 앱 모듈의 전역(A._stmt_period_args)에 잠깐
   갈아끼워 **같은 실제 라이브 라우트**로 증상을 재현하고 원상복구한다. "오늘"은
   실제 OS 시계 대신 app 모듈의 datetime 이름 자체를 가짜 클래스로 재바인딩해
   고정한다(datetime.datetime 은 불변이라 직접 monkeypatch 가 안 된다).

      python test_scan_round564_fixes.py
"""
import io
import os
import sys
import tempfile
from datetime import datetime as REAL_DATETIME

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


print("=" * 72)
print("  스캔 564라운드 회귀 — 보험사 정산명세서 기본 조회월이 '지난달' 문서와 어긋남")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — app.py 가 실제로 고쳐졌는가")
# ------------------------------------------------------------
APP_SRC = read("app.py")
STMT_BODY = _body(APP_SRC, "_stmt_period_args")

chk("없으면 지난달" in STMT_BODY,
    "  (전제) 문서 자체는 그대로 '없으면 지난달' 이라고 말하고 있다(계약 불변)")
chk("or now.year" not in STMT_BODY and "or now.month" not in STMT_BODY,
    "★★★★★ 옛 버그 폴백(now.year/now.month = 이번 달)이 더 이상 없다")
chk(".replace(day=1)" in STMT_BODY and "timedelta(days=1)" in STMT_BODY,
    "★★★★★ 이번 달 1일에서 하루를 빼 지난달을 만드는 방식으로 바뀌었다")
chk("datetime.now(DB.KST)" in STMT_BODY,
    "  회귀 방지: 여전히 OS naive 시각이 아니라 DB.KST 기준이다(round67 철칙 유지)")

_call_count = APP_SRC.count("_stmt_period_args()")
chk(_call_count == 5,  # 정의 1(def) 밖 호출부 4곳 = 어드민 조회/내보내기·보험사 자기조회/내보내기
    "  단일 공유 지점 — 정의 1곳 + 호출 4곳(어드민 2 + 보험사 포털 2)뿐, "
    "새로 중복된 로직이 없다", _call_count)

# ============================================================
print("\n[2] 준비 — 스크래치 DB + app 모듈 로드")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round564_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB
DB.init_db()
import app as A

OLD_STMT_SRC = '''
def _stmt_period_args():
    """?year=&month= 파싱 — 없으면 지난달(정산은 보통 월 마감 후 다음 달에 뽑는다)."""
    now = datetime.now(DB.KST)
    try:
        y = int(request.args.get("year") or 0) or now.year
        m = int(request.args.get("month") or 0) or now.month
    except (TypeError, ValueError):
        y, m = now.year, now.month
    if not (1 <= m <= 12):
        m = now.month
    return y, m
'''
_ns = {}
exec(compile(OLD_STMT_SRC, "<round564-reverted:_stmt_period_args>", "exec"), A.__dict__, _ns)
OLD_STMT_FN = _ns["_stmt_period_args"]
NEW_STMT_FN = A._stmt_period_args   # 고친 현재 버전(원상복구용으로 미리 쥐고 있는다)


def _fixed_now_class(y, mo, d, h=10):
    """app 모듈의 전역 이름 datetime 을 통째로 갈아끼우는 가짜 클래스.

    datetime.datetime 은 불변 타입이라 datetime.now 를 직접 monkeypatch 할 수
    없다 — 대상 모듈(app.py)이 참조하는 이름 자체(A.datetime)를 재바인딩한다.
    .now(tz) 가 돌려주는 값은 **진짜** datetime 인스턴스라 .replace()·뺄셈 등
    이후 연산은 전부 정상 동작한다.
    """
    class _Fake:
        @staticmethod
        def now(tz=None):
            return REAL_DATETIME(y, mo, d, h, 0, 0, tzinfo=tz)
    return _Fake


_ORIG_DATETIME = A.datetime

# ============================================================
print("\n[3] 되돌리기 증명 — 함수 단독 호출(요청 컨텍스트만, 아직 HTTP 아님)")
# ------------------------------------------------------------
try:
    A.datetime = _fixed_now_class(2026, 3, 15)   # "오늘" = 2026-03-15(3월, 진행중)
    with A.app.test_request_context("/api/insurer/statement"):
        old_ym = OLD_STMT_FN()
        new_ym = A._stmt_period_args()
    chk(old_ym == (2026, 3),
        "★★★★★★ 되돌린(옛) 버전은 실제로 재현된다 — 파라미터 없이 부르면 "
        "'이번 달'(3월, 아직 안 끝남)을 내려준다", old_ym)
    chk(new_ym == (2026, 2),
        "★★★★★★ 원상복구한 현재 버전은 같은 조건에서 정확히 '지난달'(2월)을 내려준다", new_ym)

    A.datetime = _fixed_now_class(2026, 1, 10)   # 연도 경계 — "오늘" = 2026-01-10
    with A.app.test_request_context("/api/insurer/statement"):
        old_jan = OLD_STMT_FN()
        new_jan = A._stmt_period_args()
    chk(old_jan == (2026, 1),
        "  되돌린 버전은 1월에도 '이번 달'(2026-01)을 내려준다(연도 경계 증상까지 동일)", old_jan)
    chk(new_jan == (2025, 12),
        "★★★★★ 연도 경계도 정확하다 — 1월의 지난달은 작년(2025) 12월로 자동으로 넘어간다", new_jan)

    A.datetime = _fixed_now_class(2026, 3, 15)   # 나머지 확인은 다시 3월 기준(지난달=2026-02)으로
    with A.app.test_request_context("/api/insurer/statement?year=2020&month=7"):
        override_ym = A._stmt_period_args()
    chk(override_ym == (2020, 7),
        "  회귀 방지: 명시 ?year=&month= 파라미터는 여전히 기본값보다 우선한다", override_ym)

    with A.app.test_request_context("/api/insurer/statement?month=13"):
        bad_month_ym = A._stmt_period_args()
    chk(bad_month_ym == (2026, 2),
        "  회귀 방지: 범위를 벗어난 month(13)는 여전히 폴백되되, 이제는 '이번 달'이 "
        "아니라 '지난달'(2월) 기준으로 폴백된다", bad_month_ym)
finally:
    A.datetime = _ORIG_DATETIME

# ============================================================
print("\n[4] 실행 — 실제 라이브 라우트(GET /api/insurer/statement)로 종단까지 확인")
# ------------------------------------------------------------
conn = DB.get_db()
iid = conn.execute(
    "INSERT INTO insurers(name, org_type, status) VALUES(?,?,?)",
    ("R564보험", "손해보험", "활성")).lastrowid
# 지난달(2월, 마감 완료) 정산 1건 + 이번 달(3월, 진행중) 정산 1건
conn.execute(
    "INSERT INTO settlements(case_no, insurer, insurer_id, partner_name, amount, fee, "
    "                        payout, insurer_paid, review_status, transfer_status, "
    "                        created_at, is_demo) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
    ("R564-FEB", "R564보험", iid, "R564업체", 1000000, 100000, 900000,
     "대기", "대기", "대기", "2026-02-20 10:00:00", 0))
conn.execute(
    "INSERT INTO settlements(case_no, insurer, insurer_id, partner_name, amount, fee, "
    "                        payout, insurer_paid, review_status, transfer_status, "
    "                        created_at, is_demo) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
    ("R564-MAR", "R564보험", iid, "R564업체", 2000000, 200000, 1800000,
     "대기", "대기", "대기", "2026-03-05 10:00:00", 0))
conn.commit()
conn.close()

client = A.app.test_client()
with client.session_transaction() as sess:
    sess["insurer_id"] = iid
    sess["insurer_name"] = "R564보험"
    sess["insurer_login"] = "r564_login"

A.datetime = _fixed_now_class(2026, 3, 15)
try:
    r = client.get("/api/insurer/statement")   # 파라미터 없음 — 실제 호출 표면(round96·534 관례)
    j = r.get_json() or {}
    chk(r.status_code == 200 and j.get("ok") is True,
        "  라우트가 200/ok:true 를 돌려준다(전제 조건)", (r.status_code, j))
    chk((j.get("year"), j.get("month")) == (2026, 2),
        "★★★★★★ 실제 라이브 라우트 — 파라미터 없이 부르면 응답 자체가 지난달(2월) 명세다", j)
    case_nos = [x.get("case_no") for x in (j.get("lines") or [])]
    chk("R564-FEB" in case_nos and "R564-MAR" not in case_nos,
        "★★★★★★ 마감된 지난달 정산만 담기고, 아직 진행 중인 이번 달 정산은 "
        "미완성 상태로 새지 않는다", case_nos)

    # 명시 파라미터를 주면 이번 달도 여전히 볼 수 있다 — 기본값만 바뀌었을 뿐 데이터 손실이 아니다
    r_explicit = client.get("/api/insurer/statement?year=2026&month=3")
    case_nos_explicit = [x.get("case_no") for x in (r_explicit.get_json() or {}).get("lines", [])]
    chk("R564-MAR" in case_nos_explicit and "R564-FEB" not in case_nos_explicit,
        "  회귀 방지: ?year=2026&month=3 을 명시하면 여전히 이번 달 정산을 정확히 볼 수 있다",
        case_nos_explicit)

    print("\n[5] 되돌리기 증명 — 같은 라이브 라우트에서 옛 버전으로 실제 재현")
    A._stmt_period_args = OLD_STMT_FN
    r_old = client.get("/api/insurer/statement")
    j_old = r_old.get_json() or {}
    chk((j_old.get("year"), j_old.get("month")) == (2026, 3),
        "★★★★★★ 되돌리면 라이브 라우트도 실제로 재현된다 — 응답이 미완성 '이번 달'(3월)이다",
        j_old)
    case_nos_old = [x.get("case_no") for x in (j_old.get("lines") or [])]
    chk("R564-MAR" in case_nos_old and "R564-FEB" not in case_nos_old,
        "  되돌린 버전 증상 — 진행 중인 이번 달 정산이 노출되고 마감된 지난달 정산은 빠진다",
        case_nos_old)
finally:
    A._stmt_period_args = NEW_STMT_FN
    A.datetime = _ORIG_DATETIME

# 원상복구 재확인 — finally 이후에도 실제로 고쳐진 채로 남아 있는지 마지막으로 한 번 더 확인
r_final = client.get("/api/insurer/statement?year=2026&month=2")
chk(r_final.status_code == 200
    and "R564-FEB" in [x.get("case_no") for x in (r_final.get_json() or {}).get("lines", [])],
    "  원상복구 확인 — 되돌리기 실험 이후에도 실제 함수·시계가 정상으로 복구돼 있다")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
