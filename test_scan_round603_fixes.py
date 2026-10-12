# -*- coding: utf-8 -*-
"""스캔 603라운드 회귀 — is_bot()(app.py, 공개폼 허니팟 판정)가 raw
   (d.get(...) or d.get(...) or "").strip() 이라 website_url/_hp 를 문자열이
   아닌 값(숫자·배열·객체)으로 보내면 AttributeError 로 500이 나던 결함.

   602라운드까지의 형제결함(_create_case()의 case_no, 601라운드 /
   _idem_fingerprint()의 address, 602라운드)과 같은 패턴이지만, 그 두 곳은
   보험사 B2B 연동(/api/v1/cases) 쪽 dict였고 이번 건은 완전히 다른 파이프라인
   — **미인증 공개폼**(/api/leads·/api/applications)의 봇 차단 로직이다.
   602라운드가 "그 값을 읽는 다른 모든 자리"로 전수대조한 범위는 보험사 사건
   생성 dict 하나였을 뿐, is_bot() 이 읽는 dict(공개폼 원본 body())는 애초에
   대조 대상이 아니었다 — 603라운드가 "형제결함탐지기법을 다른 결함군에도
   적용"한 결과 새로 찾은 인스턴스.

   더 나쁜 점 — is_bot() 자신의 설계 의도가 "봇에게는 성공한 것처럼 보이게
   한다(실패를 알려주면 우회 방법을 찾는다)"인데, 크래시로 500이 나가면 그
   의도가 정반대로 뒤집힌다(진짜 실패를 봇에게 그대로 드러낸다).

   고침: 형제와 같은 처방 — _s() 로 감싼다(app.py 1곳, is_bot() 본문).
   or 단락 순서(website_url 우선, 없으면 _hp)는 그대로 두고 최종값만 안전하게
   문자열화한다.

   [사안2] bokguon.log 마이닝(603라운드 지시 각도4 계속) 중 발견한 별개 결함 —
   run_all_tests.py:main() 이 UNIT 자식에게 BOKGUON_DB_PATH·BOKGUON_UPLOAD_DIR는
   스크래치로 갈라 주면서 **BOKGUON_LOG_FILE 은 안 갈라 줬다.** app.py:1226 의
   LOG_FILE 기본값은 그 값이 없으면 이 저장소 폴더의 **진짜 bokguon.log**(실서버가
   쓰는 그 파일)로 떨어진다. test_scan_round*.py 400여 개 중 스스로 이 값을
   세팅하는 건 20개 남짓뿐(grep 확인) — 나머지는 "고의로 예외를 던져 로그에
   남는지 확인"류 검사를 할 때마다 그 트레이스백이 실서버 로그에 그대로
   쌓인다. 실측 — bokguon.log·log.1 을 마이닝해 보니 "R430 지연발송(테스트
   주입)"·"R450-TEST-INJECTED-FAULT"·"simulated gate bug(round527 test)" 처럼
   이름표가 붙은 것부터, 이름표 없이 진짜 운영장애처럼 보이는 "Cannot operate
   on a closed database"(2026-07-23부터 오늘까지 15~45분 간격 반복 — 이
   배터리가 도는 주기와 일치)까지 섞여 있고, 후자를 실제로 열어 보면 파일
   경로가 test_scan_round527_fixes.py:_broken_record_gate 등 **이 배터리
   자신**을 가리킨다. 결과: bokguon.log 는 실제 운영 신호 대 자기유발 소음의
   비율이 극단적으로 낮아 이후 라운드가 매번 소스대조로 걸러내야 했고
   (601·602가 실제로 그렇게 함), 5MB 회전 한도를 실제 트래픽보다 훨씬 빨리
   채워 진짜 과거 장애 기록을 조기에 밀어낸다. 고침 — UPLOAD_DIR 과 같은
   자리·같은 패턴으로 run_all_tests.py:main() 이 스크래치 BOKGUON_LOG_FILE
   기본값을 한 곳에서만 세팅(이미 자기 몫을 세팅하는 파일들은 os.environ
   .setdefault/직접대입이라 영향 없음 — 이미 있으면 안 건드림).

       python test_scan_round603_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(HERE, "app.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

print("=" * 72)
print("  스캔 603라운드 회귀 — is_bot() 허니팟 판정의 raw .strip() 타입크래시")
print("=" * 72)

print("\n[1] 소스 확인")
NEEDLE_NEW = 'return bool(_s(d.get("website_url") or d.get("_hp") or ""))'
NEEDLE_OLD = 'return bool((d.get("website_url") or d.get("_hp") or "").strip())'
chk(APP_SRC.count(NEEDLE_NEW) == 1, "  is_bot() 이 _s() 로 감싼 새 코드를 정확히 1곳 쓴다")
chk(APP_SRC.count(NEEDLE_OLD) == 0, "  raw .strip() 옛 코드는 더 이상 없다")

_tmpdir = tempfile.mkdtemp(prefix="round603_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
#  ⚠ [사안2가 바로 이 결함이다] DB·업로드만 갈라놓고 로그를 안 갈라놓으면
#    이 파일 자신의 import app이 진짜 bokguon.log에 쓴다 — 실제로 이 검사를
#    처음 작성할 때 이 줄 없이 돌려 실측(★ 아래 [5]의 되돌림-증명이 만드는
#    의도적 크래시가 실서버 로그에 그대로 남는 것을 직접 확인)한 뒤 추가했다.
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "test.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB
DB.init_db()
import app as A

CONSENT = {"agree_privacy": True, "agree_marketing": False}


#  ⚠ /api/leads·/api/applications 는 공개 폼 스팸 방지로 IP당 10분 5회 상한이
#    있다(RATE_RULES, app.py:950-951) — 이 테스트가 그보다 훨씬 많이 두드리므로
#    (route39·414 라운드가 이미 쓰는 관례 그대로) 매 호출 전 인메모리 버킷을
#    비운다. 결함과 무관한 테스트 자신의 트래픽량 문제이지, 대상 코드가 아니다.
def _leads(payload):
    A._rate_buckets.clear()
    body = {"company": "정상사", "phone": "02-1234-5678", **CONSENT, **payload}
    c = A.app.test_client()
    return c.post("/api/leads", json=body)


def _applications(payload):
    A._rate_buckets.clear()
    body = {"company": "정상사", "phone": "02-1234-5678", **CONSENT, **payload}
    c = A.app.test_client()
    return c.post("/api/applications", json=body)


print("\n[2] 지금 코드 — 문자열이 아닌 허니팟 값도 크래시 없이 처리된다")
for label, ep_fn in (("/api/leads", _leads), ("/api/applications", _applications)):
    for fname in ("website_url", "_hp"):
        for bad in (12345, ["a"], {"x": 1}, True):
            r = ep_fn({fname: bad})
            chk(r.status_code != 500,
                f"  {ep_fn.__name__} {fname}={bad!r} — 500 아님(크래시 없음)", r.status_code)
            #  ★ 봇 차단 성공 시 응답은 위장성공(ok:true, id:0)이어야 한다
            #    (is_bot() 의 설계 의도 — 봇에게 실패를 알리지 않는다).
            d = r.get_json() or {}
            chk(r.status_code == 200 and d.get("ok") is True and d.get("id") == 0,
                f"  {ep_fn.__name__} {fname}={bad!r} — 봇으로 판정되어 위장성공 응답",
                (r.status_code, d))

print("\n[3] 회귀 없음 — 정상 제출(허니팟 필드 없음)은 그대로 동작")
r = _leads({})
chk(r.status_code == 200 and (r.get_json() or {}).get("ok") is True,
    "  허니팟 필드 없는 정상 도입문의는 여전히 접수된다", (r.status_code, r.get_data(as_text=True)))
r = _applications({})
#  1인사업자 가드(round288)에 안 걸리게 최소 인원을 채운다 — 이 테스트의 관심사가 아니다.
r2 = _applications({"staff_count": 3})
chk(r2.status_code == 200 and (r2.get_json() or {}).get("ok") is True,
    "  허니팟 필드 없는 정상 입점신청은 여전히 접수된다", (r2.status_code, r2.get_data(as_text=True)))

print("\n[4] 단위 — is_bot() 자체의 단락(or) 순서·의미가 그대로 보존된다(회귀 없음)")
chk(A.is_bot({}) is False, "  둘 다 없음 → False")
chk(A.is_bot({"website_url": ""}) is False, "  website_url 빈 문자열 → False")
chk(A.is_bot({"website_url": "   "}) is False, "  website_url 공백만 → False(strip 후 빈 값)")
chk(A.is_bot({"website_url": 0, "_hp": ""}) is False,
    "  website_url=0(falsy) → _hp 로 폴백, _hp도 빈값 → False(원래 단락 순서 보존)")
chk(A.is_bot({"website_url": 0, "_hp": "filled"}) is True,
    "  website_url=0(falsy) → _hp='filled' 로 폴백 → True(원래 단락 순서 보존)")
chk(A.is_bot({"website_url": "filled"}) is True, "  website_url 값 있음 → True")
chk(A.is_bot({"_hp": "filled"}) is True, "  _hp 값 있음 → True")
chk(A.is_bot({"website_url": 12345}) is True, "  website_url=숫자(non-str truthy) → True, 크래시 없음")
chk(A.is_bot({"website_url": [1, 2]}) is True, "  website_url=배열 → True, 크래시 없음")

print("\n[5] 되돌림-증명 — 옛(raw .strip()) 코드였다면 실제로 크래시가 났음을 인과관계로 확인")
#  ⚠⚠ [규칙] 디스크의 진짜 app.py 파일에는 절대 깨진 코드를 쓰지 않는다(이
#    저장소는 git 없이 여러 세션이 동시에 같은 파일을 만질 수 있다). 대신
#    is_bot 함수 객체 자체를 monkeypatch 로 옛 구현으로 잠깐 바꿔치기하고
#    (모듈 전역 이름 재바인딩 — 다른 상태에 부작용 없음) finally 로 원복한다.
_orig_is_bot = A.is_bot


def _old_is_bot(d):
    return bool((d.get("website_url") or d.get("_hp") or "").strip())


A.is_bot = _old_is_bot
try:
    threw = False
    try:
        _old_is_bot({"website_url": 12345})
    except AttributeError as e:
        threw = True
        _exc = e
    chk(threw, "★★★★★ 옛 코드(raw .strip())는 website_url=숫자에서 실제로 AttributeError를 던진다",
        "" if threw else "안 던짐 — 되돌림-증명 실패")

    #  실제 HTTP 경로로도 인과관계를 직접 증명한다 — app.py 모듈 전역 is_bot 을
    #  옛 구현으로 바꿔치기한 상태에서 진짜 라우트(api_create_lead)를 그대로 호출.
    #  라우트 함수 자신은 그 함수를 호출할 때 모듈 전역 is_bot 을 참조하므로
    #  (같은 모듈 안의 이름조회), 바깥에서 이름만 바꿔도 라우트 동작에 그대로 반영된다.
    r = _leads({"website_url": 12345})
    chk(r.status_code == 500,
        "★★★★★★★★★★ is_bot 을 옛 코드로 되돌리면 /api/leads 가 실제로 500을 낸다"
        "(인과관계 직접증명 — 지금 코드에서 이 시나리오가 200인 것은 우연이 아니다)",
        (r.status_code, r.get_data(as_text=True)))
finally:
    A.is_bot = _orig_is_bot

r = _leads({"website_url": 12345})
chk(r.status_code == 200 and (r.get_json() or {}).get("id") == 0,
    "  원복 후 다시 정상(200, 위장성공) — monkeypatch 원복 확인", r.status_code)

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "  app.py 파일 자체는 이 테스트 내내 전혀 건드리지 않았다(내용 불변)")


# ══════════════════════════════════════════════════════════════
#  [사안2] run_all_tests.py 가 UNIT 자식에게 스크래치 BOKGUON_LOG_FILE 을 준다
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("  [사안2] run_all_tests.py — UNIT 자식의 로그가 실서버 bokguon.log 로 새던 결함")
print("=" * 72)

RAT_PATH = os.path.join(HERE, "run_all_tests.py")
RAT_SRC = io.open(RAT_PATH, encoding="utf-8").read()

print("\n[6] 소스 확인")
NEEDLE_LOGFIX = 'if not os.environ.get("BOKGUON_LOG_FILE"):'
chk(RAT_SRC.count(NEEDLE_LOGFIX) == 1,
    "  run_all_tests.py main() 이 BOKGUON_LOG_FILE 스크래치 기본값을 정확히 1곳에서 세팅한다")
#  UPLOAD_DIR 블록보다 뒤에 있어야 한다(둘 다 BOKGUON_DB_PATH 디렉터리를 재사용하므로
#  UPLOAD_DIR 이 os.makedirs 로 그 디렉터리 존재를 먼저 보장해 둬야 안전하다).
_up_idx = RAT_SRC.find('os.environ.get("BOKGUON_UPLOAD_DIR")')
_log_idx = RAT_SRC.find(NEEDLE_LOGFIX)
chk(0 < _up_idx < _log_idx, "  BOKGUON_UPLOAD_DIR 블록 뒤에 위치한다(그 디렉터리가 이미 존재함을 보장받음)")

print("\n[7] 계산 확인 — BOKGUON_LOG_FILE 미설정시 app.py 의 폴백은 진짜 운영 bokguon.log 경로와 "
      "정확히 일치한다(왜 위험했는지의 근거 — 이 폴백을 실제로 타는 import 는 하지 않는다)")
_prod_log_fallback = os.path.join(os.path.dirname(os.path.abspath(A.__file__)), "bokguon.log")
chk(os.path.normcase(os.path.abspath(_prod_log_fallback)) ==
    os.path.normcase(os.path.join(HERE, "bokguon.log")),
    "  폴백 경로 == 이 저장소의 실제 bokguon.log", _prod_log_fallback)

print("\n[8] 전제조건 — round527 회귀는 BOKGUON_LOG_FILE 을 스스로 세팅하지 않는다"
      "(그래서 이 검사가 실제 결함을 드러낼 수 있었다)")
_r527_src = io.open(os.path.join(HERE, "test_scan_round527_fixes.py"), encoding="utf-8").read()
chk("BOKGUON_LOG_FILE" not in _r527_src,
    "  test_scan_round527_fixes.py는 BOKGUON_LOG_FILE을 스스로 안 정한다")
chk("BOKGUON_DB_PATH" in _r527_src,
    "  (참고) 같은 파일이 BOKGUON_DB_PATH는 스스로 스크래치로 돌린다 — DB만 갈리고 로그는 안 갈렸다는 대조")

print("\n[9] 실행기반 — run_all_tests.run() 이 자식에게 스크래치 로그를 실제로 물려준다")
#  ⚠ 이 검사는 진짜 bokguon.log 의 내용·크기를 관찰 대상으로 삼지 않는다 — 그
#    파일은 실서버가 계속 쓰는 파일이라 이 테스트가 그 상태에 의존하거나
#    건드리면 안 된다([사안2] 결함을 이 테스트 스스로 재현하지 않기 위해
#    "미설정시 어디로 가는가"는 [7]처럼 계산으로만 확인한다). 대신 실제
#    run_all_tests.run() 을 호출해, 그 함수가 만든 스크래치 로그 파일 안에
#    자식(태그된 예외를 던지는 round527)의 트레이스백이 들어왔는지만 본다.
import importlib
RAT = importlib.import_module("run_all_tests")

_logtmp = tempfile.mkdtemp(prefix="round603_logfix_")
_scratch_log = os.path.join(_logtmp, "verify.log")
_prev_logfile_env = os.environ.get("BOKGUON_LOG_FILE")
os.environ["BOKGUON_LOG_FILE"] = _scratch_log
try:
    RAT.run("test_scan_round527_fixes.py", "round603검증-round527")
finally:
    if _prev_logfile_env is None:
        os.environ.pop("BOKGUON_LOG_FILE", None)
    else:
        os.environ["BOKGUON_LOG_FILE"] = _prev_logfile_env

chk(os.path.exists(_scratch_log), "  run() 호출 후 스크래치 로그 파일이 실제로 생겼다", _scratch_log)
_logcontent = (io.open(_scratch_log, encoding="utf-8", errors="replace").read()
               if os.path.exists(_scratch_log) else "")
chk("round527" in _logcontent or "simulated gate bug" in _logcontent,
    "★★★★★ 자식(round527)의 태그된 예외 트레이스백이 실제로 스크래치 로그로 들어왔다"
    "(BOKGUON_LOG_FILE 을 안 물려줬다면 이 내용은 실서버 bokguon.log 로 갔을 것 — [7]의 "
    "계산과 결합해 인과관계 성립)", len(_logcontent))

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
