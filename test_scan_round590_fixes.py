# -*- coding: utf-8 -*-
"""스캔 590라운드 회귀 — 계정 잠금(_recent_fails/_log_attempt, app.py:2597-)의
   "실패 횟수 확인"과 "실패 기록"이 느린 verify_pw(PBKDF2 60만회) 를 사이에
   두고 잠금 없이 떨어져 있어, waitress 스레드풀로 같은 (계정,IP)를 동시에
   두드리면 MAX_LOGIN_FAILS(기본 5)보다 많은 횟수가 새는 결함(직접조사,
   하위위임 없음).

   조사 각도 — 오케스트레이터가 이번 라운드에 준 "다른 in-memory 공유상태나
   다른 백그라운드스레드" 각도를 택했다. app.py 전체의 모듈전역 가변 상태를
   훑어 `_ASSET_VER`(무해 — 순수함수 결과의 멱등 캐시)·`_rate_buckets`+
   `_rate_lock`(round588 이미 수정)·`_LAST_INLINE_SWEEP`(무해 — DB 트랜잭션
   자체가 이미 동시안전) 를 확인한 뒤, "check_rate_limit() 은 인메모리라 락이
   필요했지만, 계정 잠금(login_attempts)은 DB 기반이라 워커·재시작에 안전하다"
   (옛 941~947행, check_rate_limit() 바로 위 주석)는 이 프로젝트 자신의 명시적
   전제를 의심했다 — "DB 기반"이라는 말이 곧 "확인+기록이 원자적"이라는
   뜻은 아니다.

   결함(수정 전 app.py) —
       def _recent_fails(conn, username):
           row = conn.execute("SELECT COUNT(*) ... WHERE ... success=0 ...")
           return row["n"]
       def _log_attempt(conn, username, ok):
           conn.execute("INSERT INTO login_attempts(...) VALUES(...)")
   호출부(api_login 등 8곳) 는 전부
       fails = _recent_fails(conn, key)
       if fails >= MAX_LOGIN_FAILS: return 429
       ok = DB.verify_pw(password, ...)      # PBKDF2 60만회, 실측 평균 111ms
       _log_attempt(conn, key, ok)
   형태다. _recent_fails 의 SELECT 는 (sqlite3 기본 isolation_level 하에서)
   그 자체로 트랜잭션을 열지 않는 단발 읽기이고, _log_attempt 의 INSERT 는
   느린 verify_pw **뒤**에야 일어난다 — 이 둘을 묶는 잠금이 이 파일 어디에도
   없다(전수 확인: "BEGIN IMMEDIATE" 는 이 두 함수 근처 145곳 넘게 있지만
   이 자리엔 한 번도 없다). waitress 스레드풀(BOKGUON_THREADS, 기본 8)이 같은
   (계정,IP) 를 동시에 두드리면(스크립트 브루트포스의 흔한 패턴), 아무도 아직
   커밋하지 않은 순간에 여럿이 나란히 "아직 db_fails 미만"을 읽어 통과한다 —
   round588 이 인메모리 레이트리미터에서 고친 것과 정확히 같은 부류의 결함이
   "더 신뢰할 수 있다"던 DB 기반 계정 잠금 쪽에 그대로 있었다.

   영향 범위(과장하지 않는다) — waitress 스레드 수(기본 8)와 /api/login 자신의
   레이트리밋(RATE_RULES, 5분 10회)으로 상한이 걸려 있어 "무제한 대입"은
   아니다. 매 잠금 창(기본 10분)마다 의도한 5회 대신 최대 min(스레드수,
   레이트리밋)회(기본 최대 8~10회)까지 새는, 한도가 실제 설정값을 못 지키는
   결함이다 — check_rate_limit() 자신이 "창당 최대 N회"를 못 지키면 결함이라고
   본 것(round588)과 같은 기준을 여기에도 그대로 적용한다.

   고침(app.py, _recent_fails/_log_attempt 단일 공유 지점) — 느린 verify_pw를
   BEGIN IMMEDIATE 로 통째로 감싸면 그 동안 앱 전체 쓰기가 멎으므로(사진
   업로드 AI 분류를 트랜잭션 밖에서 하는 것과 같은 이유로 금지) 대신,
   "커밋된 실패 수"에 "지금 검증 중이라 아직 안 커밋된 시도 수"를 더한다.
   후자는 round588 이 이미 만든 `_rate_lock`+`_rate_buckets`(같은 락, 같은
   deque 슬라이딩 윈도 관례)를 그대로 재사용해 "LOGINFLIGHT:"+username+"|"+IP
   키에 시각을 적립하고(_recent_fails), 검증이 끝나면 지운다(_log_attempt).

   실행 기반 배터리(run_all_tests.py --quick)로 전수 재확인하며 첫 구현의
   구멍 두 개를 더 잡았다(전부 기존 회귀 재실행이 직접 드러낸 것 — 추측 아님) —
     (a) [test_scan_round37_fixes.py 가 잡음] 매번 _log_attempt 없이 끝나는
         '조회 전용' 호출(api_login 의 OTP 관문 확인 — 실제 코드 검증은 별도
         엔드포인트 /api/login/otp 가 한다)까지 표식을 남기면, 그 표식은 지울
         사람이 없어 뒤이은 진짜 시도 전부의 집계를 +1 만큼 부풀린다 → 그런
         호출은 mark_inflight=False 로 표식 자체를 안 남기게 한다.
     (b) [test_scan_round413/414_fixes.py 가 잡음] 이미 문턱을 넘은 뒤에도
         (그 이후 요청은 caller 가 곧 거절해 _log_attempt 가 절대 안 불린다)
         표식을 계속 남겨, 잠긴 계정을 계속 두드리기만 해도(공격자의 전형적
         행동) 표식이 한도 없이 쌓였다 — 수동 잠금해제(api_unlock_login)가
         DB 행을 지운 직후에도 안 지워진 표식 때문에 몇 초간 잠금이 유령처럼
         되살아났다(실측: 정상 5회째가 401 대신 429, 잠금해제 직후 재시도도
         429) → 합계가 이미 문턱 이상이면 표식 자체를 안 남긴다.
     (c) [직접 대조로 발견] 표식 키가 아이디만으로 돼 있어(IP 없음) 이 함수
         자신의 문서화된 방어 ②(계정 잠금 DoS — 아이디만 알면 다른 IP 의
         정당한 로그인까지 잠글 수 있던 옛 결함)를 인메모리 계층에서 다시
         열고 있었다 → 키에 client_ip() 를 더해 DB 조회와 같은 (아이디,IP)
         단위로 좁혔다.
   (부수 발견 — 이번 라운드 범위 밖: 같은 배터리 재실행 중 api_unlock_login()
   의 실패기록 삭제 키 목록이 round414·488·554 가 이미 추가했던 "PW:"·"PWX:"·
   "OTPSETUP:" 세 창구 없이 옛(라운드414 이전) 4개 키 형태로 되돌아가 있음을
   발견 — 이 라운드가 손댄 적 없는 코드이고 동시세션 파일경합 가능성이 이미
   문서화된 프로젝트라, 그 세 라운드 자신의 회귀테스트가 이미 들고 있는
   정확한 원문으로 복원만 하고 이 파일의 검증 범위에는 넣지 않았다 —
   test_scan_round414_fixes.py 자신이 그 복원을 15/15 로 이미 검증한다.)

   검증 기법 — round588 과 같은 "정확한 경계로 오려내 exec()" 기법을 쓰되,
   경쟁 지점이 함수 하나 **안**이 아니라 두 함수(_recent_fails 호출 → 느린
   verify_pw → _log_attempt 호출) **사이**에 있으므로, 소스에 인공 배리어
   훅을 심을 필요가 없다 — 테스트 하네스 자신의 worker() 함수에서 "_recent_
   fails 호출 직후·_log_attempt 호출 직전"에 threading.Barrier 를 두어
   "여러 스레드의 verify_pw 가 동시에 끝난" 상황을 결정론적으로 재현한다.
   실제 app.py 파일은 절대 건드리지 않는다 — 두 함수를 문자열로 오려내고,
   그 안에서 이번에 새로 생긴 블록만 정확히 잘라내 되돌린(OLD) 버전을 만들어
   (round585 식 재구성), 진짜 SQLite 스크래치 DB(WAL, 운영과 동일 스키마) 위에서
   진짜 threading.Thread N개로 두 버전을 나란히 경합시킨다. THRESHOLD 는 실제
   MAX_LOGIN_FAILS 값을 그대로 쓴다(_recent_fails 자신이 내부에서 그 상수로
   표식 추가 여부를 가르므로, 테스트만의 별도 문턱을 쓰면 안팎이 어긋난다).
       [1] 소스 확인 — LOGIN_INFLIGHT_SEC·LOGINFLIGHT: 키(+IP)·with _rate_lock:·
           mark_inflight 탈출구·문턱 게이팅 개수.
       [2] 순차 안전 — 스레드 하나뿐이면 지금 코드도 옛 코드와 동일하게
           동작한다(허용 정확히 THRESHOLD 개, 회귀 없음).
       [3] 지금 코드 — N 스레드가 같은 (계정,IP) 로 동시에 부딪혀도 허용되는
           수가 정확히 THRESHOLD 개뿐이다(나머지는 자신이 등록한 inflight
           표식을 통해 서로를 보고 스스로 물러난다).
       [4] 되돌리기-증명 — 이번에 추가된 블록만 제거한(그 외 코드는 바이트
           단위로 동일함을 대조) 옛 버전을 같은 방식으로 실행 — N 전부가
           허용된다(아무도 서로의 커밋 전 상태를 못 봐 전원 통과) → 이 차이가
           이번 수정의 인과효과.
       [5] 자연소멸 확인 — _log_attempt 를 부르지 않고 끝나는 예외 경로를
           흉내내(표식만 남기고 방치) LOGIN_INFLIGHT_SEC 경과 후 재확인하면
           표식이 스스로 사라져 있다(영구 잠금 누수가 아님을 직접 실측).
       [6] mark_inflight=False 확인 — (a)의 원인·수정을 함수 수준에서 직접
           재현(대조군: mark_inflight=True 면 옛 결함이 그대로 재현됨을 같은
           코드로 확인).
       [7] 문턱 게이팅 확인 — (b)의 원인·수정을 직접 재현: 이미 잠긴 뒤에는
           아무리 두드려도 표식이 안 쌓임(대조군: 문턱 검사를 빼면 무한정
           쌓임)을 확인.
       [8] IP 분리 확인 — (c)의 원인·수정을 직접 재현: 공격자 IP 가 같은
           아이디로 동시에 몰려와도 **다른 IP** 의 db_fails=0 인 정상 사용자는
           영향을 받지 않음(대조군: 키에서 IP 를 빼면 다른 IP 까지 오염됨)을
           확인.

       python test_scan_round590_fixes.py
"""
import io
import os
import sys
import tempfile
import threading
import time
from collections import defaultdict, deque

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


print("=" * 72)
print("  스캔 590라운드 회귀 — 계정 잠금(_recent_fails/_log_attempt) 확인+기록")
print("  사이의 느린 verify_pw 구간이 잠금 없이 비어 있어 동시요청이 상한을")
print("  넘어서던 결함(+배터리 재확인이 잡은 2차 결함 두 가지)")
print("=" * 72)

#  ⚠ import app 은 모듈 최상단에서 DB.init_db() 를 실제로 실행한다(round566·
#    588 관례) — 프로젝트 트리에 흔적이 안 남게 매번 새 임시 디렉터리를 쓴다.
_tmpdir = tempfile.mkdtemp(prefix="round590_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ.setdefault("BOKGUON_LOG_FILE",
                       os.path.join(HERE, "logs", "test_round590.log"))
sys.path.insert(0, HERE)

import app as A  # noqa: E402

APP_SRC = read("app.py")

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk(APP_SRC.count("LOGIN_INFLIGHT_SEC = 5") == 1,
    "★★★ LOGIN_INFLIGHT_SEC 전역 상수가 정확히 한 곳에서 신설됐다")

_RF_SIG = "def _recent_fails(conn, username, mark_inflight=True):"
_rf_start = APP_SRC.index("\n" + _RF_SIG) + 1
_la_start = APP_SRC.index("\ndef _log_attempt(conn, username, ok):") + 1
_la_end_marker = ('        (uname, client_ip(), 1 if ok else 0, DB.now()),\n'
                   '    )\n')
chk(APP_SRC.count(_la_end_marker) == 1,
    "(준비) _log_attempt() 끝 표식이 파일 전체에서 유일하다")
_la_end = APP_SRC.index(_la_end_marker) + len(_la_end_marker)

RECENT_FAILS_NEW = APP_SRC[_rf_start:_la_start - 1]
LOG_ATTEMPT_NEW = APP_SRC[_la_start:_la_end]

chk(RECENT_FAILS_NEW.startswith(_RF_SIG),
    "(준비) _recent_fails 본문을 정확히 추출했다")
chk(LOG_ATTEMPT_NEW.startswith("def _log_attempt(conn, username, ok):"),
    "(준비) _log_attempt 본문을 정확히 추출했다")
chk(RECENT_FAILS_NEW.count('key = "LOGINFLIGHT:" + username + "|" + client_ip()') == 1
    and LOG_ATTEMPT_NEW.count('key = "LOGINFLIGHT:" + username + "|" + client_ip()') == 1,
    "★★★★★ 두 함수 모두 LOGINFLIGHT: 키에 IP 를 붙여 정확히 한 번씩 쓴다"
    "(계정 잠금 DoS 방어 ②를 인메모리 계층에서 다시 뚫지 않는다)")
chk(RECENT_FAILS_NEW.count("with _rate_lock:") == 1
    and LOG_ATTEMPT_NEW.count("with _rate_lock:") == 1,
    "★★★★★ 두 함수 모두 with _rate_lock: 을 정확히 한 번씩 쓴다(round588 락 재사용)")
chk('return total' in RECENT_FAILS_NEW,
    "  회귀 방지: db_fails + inflight 합산(total)이 그대로 남아 있다")
chk("if not mark_inflight:" in RECENT_FAILS_NEW and 'return row["n"]' in RECENT_FAILS_NEW,
    "★★★★★ mark_inflight=False 조회 전용 탈출구가 있다"
    "(round37 회귀가 실측으로 잡아낸 2차 결함의 수정)")
chk("if total < MAX_LOGIN_FAILS:" in RECENT_FAILS_NEW
    and RECENT_FAILS_NEW.count("bucket.append(now)") == 1,
    "★★★★★ 이미 문턱 이상이면 표식을 안 남기는 게이팅이 있다"
    "(round413·414 회귀가 실측으로 잡아낸 3차 결함의 수정)")
_i_guard = RECENT_FAILS_NEW.index("if not mark_inflight:")
_i_lock = RECENT_FAILS_NEW.index("with _rate_lock:")
_i_gate = RECENT_FAILS_NEW.index("if total < MAX_LOGIN_FAILS:")
_i_append = RECENT_FAILS_NEW.index("bucket.append(now)")
chk(_i_guard < _i_lock < _i_gate < _i_append,
    "★★ 탈출구 → 락 → 문턱게이트 → append 순서가 코드에 그대로 있다")


# ============================================================
print("\n[2]+[3]+[4] 실행 — 실제 함수를 배리어로 경합시켜 지금/옛 버전을 대조")
# ------------------------------------------------------------

def _strip_recent_fails_fix(fn_src):
    """_recent_fails 에서 이번 라운드가 추가한 블록(mark_inflight 탈출구·IP
    포함 키·문턱 게이팅 전부)을 제거해 옛(수정 전) 버전을 복원한다 —
    round585/588 식 "고치기 전 그대로 재구성" 기법. 반환문 앞 블록만
    건드리므로 그 앞(SELECT)·독스트링은 완전히 동일하게 남는다."""
    added = (
        '    if not mark_inflight:\n'
        '        return row["n"]\n'
        '    #  ⚠ DB 조회와 똑같이 (아이디,IP) 로 좁힌다 — ②의 계정 잠금 DoS 방어를\n'
        '    #    이 인메모리 계층에서 다시 뚫지 않기 위해서다.\n'
        '    key = "LOGINFLIGHT:" + username + "|" + client_ip()\n'
        '    now = time.time()\n'
        '    with _rate_lock:\n'
        '        bucket = _rate_buckets[key]\n'
        '        while bucket and now - bucket[0] > LOGIN_INFLIGHT_SEC:\n'
        '            bucket.popleft()\n'
        '        inflight = len(bucket)      # 나를 빼고, 지금 같이 검증 중인 다른 시도 수\n'
        '        total = row["n"] + inflight\n'
        '        #  ⚠ 이미 문턱 이상이면(=이 요청은 caller 가 곧 거절해 _log_attempt 가\n'
        '        #    절대 안 불린다) 표식을 남기지 않는다 — 안 남기면 지울 사람도 없이\n'
        '        #    한도 없이 쌓이는 일이 원천적으로 없어진다(위 실측 (a) 참조).\n'
        '        if total < MAX_LOGIN_FAILS:\n'
        '            bucket.append(now)      # 나도 등록 — 뒤이은 동시 요청이 나를 본다\n'
        '    return total\n'
    )
    chk(fn_src.count(added) == 1,
        "(준비) _recent_fails 안에서 이번에 추가된 블록을 정확히 한 번 찾았다")
    stripped = fn_src.replace(added, '    return row["n"]\n', 1)
    #  진짜 원본(590라운드 이전)은 mark_inflight 매개변수 자체가 없었다 —
    #  시그니처도 함께 되돌려야 "고치기 전 그대로"가 정확해진다.
    chk(stripped.count(_RF_SIG) == 1,
        "(준비) 시그니처를 되돌리기 전, 지금 시그니처가 정확히 한 번 있다")
    return stripped.replace(_RF_SIG, "def _recent_fails(conn, username):", 1)


def _strip_log_attempt_fix(fn_src):
    """_log_attempt 에서 이번 라운드가 추가한 '표식 지우기' 블록만 제거한다."""
    added = (
        "    #  ⚠⚠ [라운드590] 검증이 끝났다 — 위 _recent_fails 가 남긴 '진행 중' 표식을\n"
        "    #    지운다. 못 찾아도(이미 5초 지나 스스로 정리됐어도, 또는 이미 문턱\n"
        "    #    이상이라 애초에 표식을 안 남겼어도) 조용히 넘어간다.\n"
        '    key = "LOGINFLIGHT:" + username + "|" + client_ip()\n'
        "    with _rate_lock:\n"
        "        bucket = _rate_buckets.get(key)\n"
        "        if bucket:\n"
        "            bucket.popleft()\n"
    )
    chk(fn_src.count(added) == 1,
        "(준비) _log_attempt 안에서 이번에 추가된 블록을 정확히 한 번 찾았다")
    return fn_src.replace(added, "", 1)


RECENT_FAILS_OLD = _strip_recent_fails_fix(RECENT_FAILS_NEW)
LOG_ATTEMPT_OLD = _strip_log_attempt_fix(LOG_ATTEMPT_NEW)

#  ⚠ 되돌린 옛 버전이 실제로 락/inflight 없이 순수 SELECT-then-return, 순수
#    INSERT 뿐인지 대조한다(과잉수정 방지 — round588 이 break 이후 동일성을
#    대조한 것과 같은 목적).
chk("_rate_lock" not in RECENT_FAILS_OLD and "_rate_lock" not in LOG_ATTEMPT_OLD,
    "★★ (준비) 되돌린 옛 버전 두 함수 모두에 락이 전혀 없다")
chk(RECENT_FAILS_OLD.strip().endswith('return row["n"]'),
    "(준비) 되돌린 _recent_fails 는 옛날처럼 db_fails 만 그대로 반환한다")


def _build_ns(rate_buckets, rate_lock):
    ns = dict(vars(A))
    ns["_rate_buckets"] = rate_buckets
    ns["_rate_lock"] = rate_lock
    return ns


def _compile_pair(rf_src, la_src, rate_buckets, rate_lock):
    ns = _build_ns(rate_buckets, rate_lock)
    exec(compile(rf_src, "<r590_recent_fails>", "exec"), ns)   # noqa: S102
    exec(compile(la_src, "<r590_log_attempt>", "exec"), ns)    # noqa: S102
    return ns["_recent_fails"], ns["_log_attempt"]


IP = "203.0.113.90"
#  ⚠ _recent_fails 자신이 내부에서 MAX_LOGIN_FAILS 로 표식 추가 여부를 가르므로
#    (문턱 게이팅), 테스트만의 별도 문턱을 쓰면 안팎이 어긋난다 — 실제 상수를
#    그대로 THRESHOLD 로 쓴다.
THRESHOLD, N = A.MAX_LOGIN_FAILS, A.MAX_LOGIN_FAILS * 2


def _run_race(rf_src, la_src, n, key, use_barrier=True):
    """n개 스레드가 같은 (계정,IP) 로 "확인 → (배리어로 동시화) → 기록" 을
    경합한다. 배리어는 '느린 verify_pw 가 다 함께 끝난 순간'을 흉내낸다 —
    실제 결함은 그 확인과 기록 사이(코드 두 곳 사이)에 있으므로, 소스에
    인공 훅을 심지 않고 테스트 하네스 자신에서 그 경계를 재현한다.

    ⚠ use_barrier=False(순차 검증)일 때는 스레드를 하나씩 start-then-join 한다
      — 전부 먼저 start() 하고 나중에 join() 하면 배리어가 없어도 스레드
      스케줄러가 여러 개를 겹쳐 돌려 '순차'가 전혀 아니게 된다(이 파일의
      첫 초안에서 실제로 걸린 함정 — 회귀 방지 차원에서 남긴다).
    ⚠ key 는 호출마다 달라야 한다 — 스크래치 DB 파일 하나를 테스트 전체가
      공유하므로, 같은 키를 재사용하면 이전 단계([2]/[3]/[4])가 남긴
      login_attempts 행이 다음 단계의 db_fails 초기값을 오염시킨다.
    """
    rate_buckets, rate_lock = defaultdict(deque), threading.Lock()
    recent_fails, log_attempt = _compile_pair(rf_src, la_src, rate_buckets, rate_lock)
    barrier = threading.Barrier(n) if use_barrier else None
    results = [None] * n

    def worker(i):
        with A.app.test_request_context("/r590x", method="POST",
                                         environ_base={"REMOTE_ADDR": IP}):
            conn = A.DB.get_db()
            try:
                fails = recent_fails(conn, key)
                if barrier is not None:
                    try:
                        barrier.wait(timeout=5)
                    except threading.BrokenBarrierError:
                        pass
                allowed = fails < THRESHOLD
                if allowed:
                    log_attempt(conn, key, False)   # verify_pw 가 실패했다고 가정
                    conn.commit()
                results[i] = allowed
            except Exception as e:                                  # noqa: BLE001
                results[i] = ("EXC", f"{type(e).__name__}: {e}")
            finally:
                conn.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    if use_barrier:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
    else:
        for t in threads:               # 진짜 순차 — 하나 끝난 뒤에야 다음을 만든다
            t.start()
            t.join(timeout=15)

    conn = A.DB.get_db()
    try:
        db_rows = conn.execute(
            "SELECT COUNT(*) n FROM login_attempts WHERE username=? AND ip=? AND success=0",
            (key, IP)).fetchone()["n"]
    finally:
        conn.close()

    return {
        "allowed": sum(1 for r in results if r is True),
        "blocked": sum(1 for r in results if r is False),
        "exc": [r for r in results if isinstance(r, tuple)],
        "db_rows": db_rows,
        "results": results,
    }


try:
    # ── [2] 순차 안전 — 스레드 하나씩(진짜 순차), 배리어 없이 (threshold+2)회 호출 ──
    seq = _run_race(RECENT_FAILS_NEW, LOG_ATTEMPT_NEW, THRESHOLD + 2, "r590_seq",
                     use_barrier=False)
    chk(not seq["exc"], "STEP 순차 호출은 예외 없이 끝난다", seq["exc"])
    chk(seq["allowed"] == THRESHOLD and seq["blocked"] == 2,
        "STEP 순차(동시성 없음) 호출은 지금까지처럼 정확히 threshold 개만 허용한다"
        "(회귀 없음)", seq)

    # ── [3] 지금 코드 — N개 스레드가 동시에 부딪힌다 ──
    new = _run_race(RECENT_FAILS_NEW, LOG_ATTEMPT_NEW, N, "r590_new", use_barrier=True)
    chk(not new["exc"], "STEP 지금 코드: 예외 없이 모두 응답했다", new["exc"])
    chk(new["allowed"] == THRESHOLD and new["blocked"] == N - THRESHOLD,
        f"★★★★★ 지금 코드: {N}개 동시요청 중 정확히 threshold={THRESHOLD}개만 허용된다"
        "(inflight 표식으로 서로를 보고 나머지는 스스로 물러난다)", new)
    chk(new["db_rows"] == THRESHOLD,
        "★★★★★ 지금 코드: 실제 DB 에 커밋된 실패 행도 threshold 개를 넘지 않는다",
        new["db_rows"])

    # ── [4] 되돌리기-증명 — 이번 블록만 제거한 옛 버전을 같은 방식으로 경합 ──
    old = _run_race(RECENT_FAILS_OLD, LOG_ATTEMPT_OLD, N, "r590_old", use_barrier=True)
    chk(not old["exc"], "STEP 되돌린 옛 코드: 예외 없이 모두 응답했다", old["exc"])
    chk(old["allowed"] == N,
        f"★★★★★ 되돌린(옛) 코드: threshold={THRESHOLD} 인데 {N}개 요청이 전부 허용된다"
        "(아무도 서로의 커밋 전 상태를 못 봐 전원이 '아직 미만'을 읽었다는 뜻 — "
        "이것이 락 없는 원래 결함의 경쟁 조건이다. 지금 코드는 정확히 threshold개만 "
        "허용 — 이 차이가 이번 수정의 인과효과)", old)
    chk(old["db_rows"] == N and old["db_rows"] > THRESHOLD,
        f"★★★★★ 되돌린(옛) 코드: 실제 DB 에 커밋된 실패 행이 {old['db_rows']}개로 "
        f"threshold={THRESHOLD} 을 실제로 초과한다(설정한 한도가 무의미해짐)", old)
except Exception as e:                                                 # noqa: BLE001
    chk(False, "★★★ 라운드590 [2]~[4] 실행", f"{type(e).__name__}: {e}")


# ============================================================
print("\n[5] 자연소멸 확인 — _log_attempt 를 안 부르고 끝나는 예외 경로를 흉내낸다")
# ------------------------------------------------------------
#  api_login_otp() 의 "이미 사용한 코드" 분기·api_otp_confirm() 의 "등록 미시작"
#  분기처럼 _recent_fails 만 부르고 _log_attempt 는 안 부른 채 끝나는 실제
#  코드 경로가 있다(본문 주석 참조) — 그 표식이 영원히 안 지워지면 그 자체가
#  새 결함(자기잠금)이 된다는 것을 직접 실측으로 확인한다.
try:
    rate_buckets, rate_lock = defaultdict(deque), threading.Lock()
    recent_fails, _log_attempt_unused = _compile_pair(
        RECENT_FAILS_NEW, LOG_ATTEMPT_NEW, rate_buckets, rate_lock)
    with A.app.test_request_context("/r590leak", method="POST",
                                     environ_base={"REMOTE_ADDR": IP}):
        conn = A.DB.get_db()
        try:
            leak_key = "r590_leak_user"
            f1 = recent_fails(conn, leak_key)     # _log_attempt 를 절대 안 부른다(누수 흉내)
            chk(f1 == 0, "(준비) 첫 확인은 db_fails=0·inflight=0", f1)
            f2 = recent_fails(conn, leak_key)     # 창 안(<5초)에서 재확인 — 표식이 아직 살아있다
            chk(f2 == 1,
                "★★★ 창 안에서는 방치된 표식이 카운트에 그대로 잡힌다(과대집계 — 예상된 동작)",
                f2)
            time.sleep(A.LOGIN_INFLIGHT_SEC + 0.5)
            f3 = recent_fails(conn, leak_key)     # 5초 지남 — 스스로 지워졌어야 한다
            chk(f3 == 0,
                "★★★★★ LOGIN_INFLIGHT_SEC 경과 후에는 방치된 표식이 스스로 사라진다"
                "(영구 자기잠금 누수가 아니다)", f3)
        finally:
            conn.close()
except Exception as e:                                                 # noqa: BLE001
    chk(False, "★★★ 라운드590 [5] 자연소멸 확인", f"{type(e).__name__}: {e}")


# ============================================================
print("\n[6] mark_inflight=False 확인 — 2차 결함(조회전용 호출의 영구 과대집계)")
# ------------------------------------------------------------
#  api_login()의 OTP 관문 확인(뒤이어 _log_attempt 를 절대 안 부르는 '조회
#  전용' 호출)이 매번 표식을 남기는 바람에, 그 직후 /api/login/otp 로 들어오는
#  진짜 시도 전부의 집계가 +1 씩 부풀어 마지막 정상 시도가 401(오답) 대신
#  429(조기 잠금)로 나왔다(test_scan_round37_fixes.py 가 실측으로 잡음) —
#  순수 순차 호출(동시성 전혀 없음)에서도 재현되는, 설계 자체의 결함이었다.
try:
    rate_buckets, rate_lock = defaultdict(deque), threading.Lock()
    recent_fails, log_attempt = _compile_pair(
        RECENT_FAILS_NEW, LOG_ATTEMPT_NEW, rate_buckets, rate_lock)
    with A.app.test_request_context("/r590mi", method="POST",
                                     environ_base={"REMOTE_ADDR": IP}):
        conn = A.DB.get_db()
        try:
            mkey = "r590_mi_user"
            bkey = "LOGINFLIGHT:" + mkey + "|" + IP
            # 게이트 확인 1회 — mark_inflight=False (api_login 의 OTP 관문과 같은 모양)
            gate = recent_fails(conn, mkey, mark_inflight=False)
            chk(gate == 0, "(준비) 게이트 조회는 db_fails=0을 그대로 돌려준다", gate)
            chk(len(rate_buckets.get(bkey, [])) == 0,
                "★★★★★ mark_inflight=False 호출은 표식을 전혀 안 남긴다"
                "(버킷이 비어 있다)", dict(rate_buckets))

            # 순차로 "검증→기록" (threshold-1)회 (배리어 없음 — 이 결함은 동시성과 무관했다)
            seen = []
            for i in range(THRESHOLD - 1):
                f = recent_fails(conn, mkey)          # mark_inflight 기본값(True)
                seen.append(f)
                log_attempt(conn, mkey, False)          # 매번 즉시 기록(오답 시나리오)
                conn.commit()
            chk(seen == list(range(THRESHOLD - 1)),
                f"★★★★★ 앞선 게이트 조회가 표식을 안 남겼으므로, 뒤이은 {THRESHOLD - 1}회 "
                f"순차 시도는 정확히 {list(range(THRESHOLD - 1))} 를 본다(선행 조회로 인한 "
                "영구 +1 과대집계 없음 — round37 회귀가 잡아낸 증상의 근본원인이 사라졌다는 "
                "뜻)", seen)

            # 대조군 — 게이트 확인이 기본값(mark_inflight=True)이면 옛 결함이 그대로
            # 재현되는지도 같은 코드로 직접 확인한다(과잉수정 아님을 증명).
            mkey2 = "r590_mi_user2"
            _ = recent_fails(conn, mkey2)             # 기본값 True — 표식을 남긴다
            seen2 = []
            for i in range(THRESHOLD - 1):
                f = recent_fails(conn, mkey2)
                seen2.append(f)
                log_attempt(conn, mkey2, False)
                conn.commit()
            chk(seen2 == list(range(1, THRESHOLD)),
                f"★★★★★ 대조군: 게이트 확인이 mark_inflight=True(기본값)면 매 시도가 "
                f"+1 씩 부풀어 {list(range(1, THRESHOLD))} 대신 이미 한 칸씩 밀린 값을 "
                "본다 — 이것이 실제로 재현됐던 옛 결함이고, 위 본 시나리오는 "
                "mark_inflight=False 로 이 증상이 사라짐을 보여 준다(인과관계 대조)", seen2)
        finally:
            conn.close()
except Exception as e:                                                 # noqa: BLE001
    chk(False, "★★★ 라운드590 [6] mark_inflight 확인", f"{type(e).__name__}: {e}")


# ============================================================
print("\n[7] 문턱 게이팅 확인 — 3차 결함(이미 잠긴 뒤 표식 무한 누적)")
# ------------------------------------------------------------
#  db_fails 가 이미 MAX_LOGIN_FAILS 이상이면 caller 는 곧바로 429 를 돌려주고
#  _log_attempt 를 절대 안 부른다 — 그런데 _recent_fails 자신은 그 사실을
#  모른 채 매 호출마다 표식을 계속 추가했다. 잠긴 계정을 계속 두드리기만
#  해도(공격자의 전형적 행동) 표식이 한도 없이 쌓였고, 그 직후 관리자가
#  수동잠금해제로 DB 행을 지워도 안 지워진 표식 때문에 몇 초간 잠금이
#  유령처럼 되살아났다 — test_scan_round413_fixes.py·414_fixes.py 가 실측으로
#  잡았다(정상 5회차가 401 대신 429, 잠금해제 직후 재시도도 429).
try:
    rate_buckets, rate_lock = defaultdict(deque), threading.Lock()
    recent_fails, log_attempt = _compile_pair(
        RECENT_FAILS_NEW, LOG_ATTEMPT_NEW, rate_buckets, rate_lock)
    with A.app.test_request_context("/r590gate", method="POST",
                                     environ_base={"REMOTE_ADDR": IP}):
        conn = A.DB.get_db()
        try:
            gkey = "r590_gate_user"
            bkey = "LOGINFLIGHT:" + gkey + "|" + IP
            #  먼저 문턱까지 정확히 채운다(정상 시나리오, 표식은 매번 지워진다).
            for i in range(THRESHOLD):
                recent_fails(conn, gkey)
                log_attempt(conn, gkey, False)
                conn.commit()
            chk(len(rate_buckets.get(bkey, [])) == 0,
                "(준비) 문턱을 정확히 채운 뒤 버킷은 비어 있다(정상 페어링)", dict(rate_buckets))
            #  이미 잠긴 계정을 20번 더 두드린다(공격자가 흔히 하는 행동).
            for i in range(20):
                f = recent_fails(conn, gkey)
                chk(f >= THRESHOLD, f"  이미 잠긴 뒤 {i+1}번째 조회도 문턱 이상을 본다", f)
            chk(len(rate_buckets.get(bkey, [])) == 0,
                "★★★★★ 이미 잠긴 뒤 20번을 더 두드려도 표식이 하나도 안 쌓인다"
                "(문턱 게이팅이 무한누적을 원천 차단)", dict(rate_buckets))

            #  대조군 — 게이팅 없이(항상 append) 옛 방식이면 무한정 쌓이는지 직접 대조.
            def _ungated_append(bucket, now):
                bucket.append(now)   # 문턱 검사 없이 항상 추가(옛 결함 재현)

            gkey2 = "r590_gate_user2"
            bkey2 = "LOGINFLIGHT:" + gkey2 + "|" + IP
            for i in range(THRESHOLD):
                recent_fails(conn, gkey2)
                log_attempt(conn, gkey2, False)
                conn.commit()
            ungated_bucket = rate_buckets[bkey2]
            for i in range(20):
                _ungated_append(ungated_bucket, time.time())
            chk(len(ungated_bucket) == 20,
                "★★ 대조군: 문턱 검사 없이(옛 방식) 20번 두드리면 표식이 그대로 20개 "
                "쌓인다(지금 코드의 '0개'와 대비 — 이 차이가 문턱 게이팅의 인과효과)",
                len(ungated_bucket))
        finally:
            conn.close()
except Exception as e:                                                 # noqa: BLE001
    chk(False, "★★★ 라운드590 [7] 문턱 게이팅 확인", f"{type(e).__name__}: {e}")


# ============================================================
print("\n[8] IP 분리 확인 — 4차 결함(인메모리 표식의 계정 잠금 DoS 재도입)")
# ------------------------------------------------------------
#  _recent_fails 자신의 문서화된 방어 ②는 "같은 IP 에서 온 실패만 센다 —
#  다른 곳에서 두드려도 정당한 사용자는 막히지 않는다"이다. 표식 키가
#  아이디만으로 돼 있으면(IP 없음), 공격자가 자기 IP 에서 동시요청을 쏟아
#  부을 때 **다른 IP** 의 정당한 사용자 카운트까지 인메모리 표식을 통해
#  같이 올라간다 — DB 조회는 (아이디,IP) 로 좁히면서 인메모리 표식만
#  아이디 단독이면 그 방어를 다시 여는 셈이다.
try:
    rate_buckets, rate_lock = defaultdict(deque), threading.Lock()
    recent_fails, _log_attempt_unused = _compile_pair(
        RECENT_FAILS_NEW, LOG_ATTEMPT_NEW, rate_buckets, rate_lock)
    ATTACKER_IP, VICTIM_IP = "198.51.100.7", "198.51.100.8"
    ikey = "r590_ip_user"

    def _check_from(ip):
        with A.app.test_request_context("/r590ip", method="POST",
                                         environ_base={"REMOTE_ADDR": ip}):
            conn = A.DB.get_db()
            try:
                return recent_fails(conn, ikey)
            finally:
                conn.close()

    #  공격자 IP 에서 (threshold-1)번 조회 — 전부 db_fails=0 이므로 표식을 남긴다.
    for i in range(THRESHOLD - 1):
        _check_from(ATTACKER_IP)
    victim_sees = _check_from(VICTIM_IP)
    chk(victim_sees == 0,
        "★★★★★ 공격자 IP 가 같은 아이디로 여러 번 두드려도, 다른 IP(정당한 사용자)의 "
        "조회는 영향을 안 받는다(0을 그대로 본다) — 인메모리 표식이 (아이디,IP) 로 "
        "제대로 좁혀져 있다는 뜻", victim_sees)

    #  대조군 — 키에서 IP 를 빼면(옛 결함 형태) 다른 IP 까지 오염되는지 직접 대조.
    #  (실제 _recent_fails 를 다시 부르지 않는다 — IP 없는 키를 흉내내려면 그
    #   자체가 지금 코드와 달라야 하므로, 순수 deque 연산으로 옛 키 형태만
    #   재현해 "IP 를 빼면 무슨 일이 생기는가"를 보여 준다.)
    shared = defaultdict(deque)
    now0 = time.time()
    for i in range(THRESHOLD - 1):
        shared["LOGINFLIGHT:" + ikey].append(now0 + i * 0.001)   # IP 없는 옛 키 형태
    victim_ungated_view = len(shared["LOGINFLIGHT:" + ikey])   # IP 무시하면 다른 IP 도 이 값을 본다
    chk(victim_ungated_view == THRESHOLD - 1,
        f"★★ 대조군: 키에서 IP 를 빼면(옛 형태) 공격자가 쌓은 표식 {THRESHOLD - 1}개를 "
        "다른 IP 조회도 그대로 물려받는다(지금 코드의 '0'과 대비 — 이 차이가 IP 분리의 "
        "인과효과)", victim_ungated_view)
except Exception as e:                                                 # noqa: BLE001
    chk(False, "★★★ 라운드590 [8] IP 분리 확인", f"{type(e).__name__}: {e}")


print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
