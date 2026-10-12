# -*- coding: utf-8 -*-
"""스캔 588라운드 회귀 — check_rate_limit()(app.py:952, 레이트리밋 카운터)의
   "버킷 길이확인 → append"가 락 없이 두 문장으로 쪼개져 있어, waitress
   스레드풀(BOKGUON_THREADS, 기본 여럿)이 같은 IP·경로로 동시요청을 처리하면
   여러 스레드가 서로의 append 전에 나란히 상한 확인을 통과해 실제 허용
   건수가 설정된 limit 을 넘어서던 결함(직접조사, 하위위임 없음).

   조사 각도 — 오케스트레이터가 이번 라운드에 준 "아직 안 해본 각도" 중
   "동시성 실측 재현"을 택했다. app.py 전역 인메모리 공유상태를 훑어
   `_rate_buckets`(defaultdict(deque), 옛 901행)를 찾았다 — app.py 전체에
   threading.Lock 이 단 한 곳도 없었고(기존 동시성 방어는 전부 BEGIN
   IMMEDIATE 류의 DB 트랜잭션이었고, threading 은 오직 threading.Thread
   (백그라운드 웹훅 발송)에만 쓰였다 — 전수 grep 확인), check_rate_limit()
   은 @app.before_request(1091행 부근)로 **모든 요청마다** 이 딕셔너리를
   읽고 쓴다. 39·414·450라운드 등 기존 테스트는 `A._rate_buckets.clear()`
   로 버킷을 비워 다른 테스트를 격리하는 용도로만 이 이름을 썼을 뿐,
   check_rate_limit() 자신의 스레드 안전성을 실측한 적은 없었다(전수 확인
   — test_*.py 전체에서 "_rate_buckets|check_rate_limit|RATE_RULES" 를
   언급하는 파일은 4개뿐이고 전부 clear() 로 격리 용도).

   결함(수정 전 app.py, check_rate_limit()) —
       bucket = _rate_buckets[key]
       while bucket and now - bucket[0] > window:
           bucket.popleft()
       if len(bucket) >= limit:
           return int(window - (now - bucket[0])) + 1
       bucket.append(now)
   확인(len)과 추가(append)가 하나의 락 없이 분리된 두 문장이다. waitress
   는 threads>=1(기본 여러 개, BOKGUON_THREADS)로 요청을 동시에 처리하므로,
   같은 IP 가 병렬 커넥션 여러 개로 같은 경로를 동시에 두드리면(스크립트
   브루트포스의 흔한 패턴 — 로그인 폼도 이 함수를 거친다) 여러 스레드가
   **아직 아무도 append 하지 않은 시점의 같은 길이**를 함께 읽어 상한
   확인을 나란히 통과할 수 있다 — 그 라운드에 몰린 요청 수만큼 limit 을
   넘어 버킷에 쌓인다. 이 계층 자신의 주석(옛 941~948행)은 "이것은 2차
   방어선, 1차는 nginx"라고 명시하지만 그 주석은 워커 **프로세스** 수에
   따른 배수 문제만 다룰 뿐 **같은 프로세스 안 스레드 경쟁**은 언급하지
   않는다 — waitress 프로세스가 하나만 떠 있어도(운영 배포가 그렇다) 이
   경쟁으로 뚫린다.

   영향 범위(과장하지 않는다) — 이 계층은 스스로 "보조 역할"이라 밝힌 2차
   방어선이고, 로그인 무차별 대입의 실제 저지선은 DB 기반 계정 잠금
   (login_attempts, 워커·재시작과 무관)이다. 따라서 이 결함만으로 계정이
   뚫리지는 않지만, 레이트리밋이라는 기능 자체의 정의("창당 최대 N 회")를
   스레드 경쟁이 있는 그대로 못 지키는 것은 이 계층의 존재 이유에 반하는
   결함이다 — 특히 /api/leads·/api/applications 같은 공개 폼(10분 5회)은
   이 계층이 사실상 유일한 스팸 방어선이다.

   고침(app.py) — 모듈 전역 `_rate_lock = threading.Lock()` 을
   `_rate_buckets` 옆에 신설하고, check_rate_limit() 의 정리+확인+추가
   구간 전체를 `with _rate_lock:` 로 감쌌다(임계구간이 전부 인메모리
   dict/deque 연산뿐이라 락 경합 비용은 무시할 만하다 — I/O 없음). app.py
   전체에 이런 종류의 첫 Python 락이라 따를 형제 관례가 없었고, DB 가
   전혀 관여하지 않는 순수 프로세스 메모리 경쟁이라 BEGIN IMMEDIATE 류는
   애초에 적용 대상이 아니다 — threading.Lock 이 이 결함 유형의 정확한
   도구(ponytail: 키별 락이 아니라 전역 락 하나 — 임계구간이 마이크로초
   단위라 이 앱 규모에서는 충분하고, 처리량이 실제 병목이 되면 키별 락으로
   올릴 것).

   검증 기법 — check_rate_limit() 은 DB 를 전혀 건드리지 않으므로(순수
   인메모리) 서버·DB 픽스처가 필요 없다. app.py 실제 소스에서 함수 전체를
   오려내(on-disk 파일은 절대 안 건드림) "bucket.append(now)" 직전에만
   테스트 전용 배리어 훅을 문자열로 심어 exec() 하고(round585 의 "정확한
   경계로 오려내 exec()" 기법), 그렇게 만든 함수 객체를 실제 Flask
   test_request_context + 진짜 threading.Thread N개로 부른다(round566 의
   실스레드+Barrier 기법). 이 배리어는 "언제 append 하는가"를 새로 정하는
   것이 아니라 원래 있던 두 문장 사이의 그 경계에만 얹은 관측 장치라서,
   새 경쟁을 만들어내는 게 아니라 원래 있던 경쟁을 결정론적으로 드러낼
   뿐이다(round566 이 make_delay_probe() 에서 이미 실측한 대로 순수
   time.sleep() 지연은 재현이 안 됨 — 이 세션도 스레드 N=40·전환간격을
   1e-6 으로 낮춘 순수 경쟁 시도로 먼저 확인했고, 배리어 없이는 매 실행
   허용 정확히 limit 개로 재현되지 않았다).
       [1] 소스 확인 — _rate_lock 신설·with 블록·들여쓰기·개수.
       [2] 순차 안전 — 락을 씌워도 스레드 하나뿐일 때는 기존과 동일하게
           동작한다(허용 limit 개 그대로, 회귀 없음).
       [3] 지금 코드(락 있음) — N=12 스레드가 같은 키로 동시에 부딪혀도
           배리어 훅에 도달하는 스레드가 정확히 limit(=3)개뿐이다(락이
           나머지를 애초에 못 들어오게 막으므로 경쟁 자체가 성립 안 함)
           → 허용 3·차단 9·최종 버킷길이 3.
       [4] 되돌리기-증명 — `with _rate_lock:` 한 줄만 지우고 들여쓰기만
           되돌린(그 외 문자열은 완전히 동일함을 대조해 과잉수정 방지)
           옛 버전을 같은 방식으로 실행 — 배리어 훅에 12개 스레드 전부
           도달(아무도 먼저 append 하지 않은 채 다 같이 길이확인을
           통과했다는 뜻) → 허용 12·최종 버킷길이 12(limit=3 을 4배
           초과) 실측(0→1 이 아니라 "한도 안"→"한도 밖" 이 이 수정의
           인과효과).

       python test_scan_round588_fixes.py
"""
import io
import os
import re
import sys
import tempfile
import threading
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
print("  스캔 588라운드 회귀 — check_rate_limit() 의 확인+추가가 락 없이")
print("  분리돼 있어 동시요청이 레이트리밋 상한을 넘어서던 결함")
print("=" * 72)

#  ⚠ check_rate_limit() 자신은 DB 를 전혀 안 건드리지만, `import app`은
#    (round585 의 `import db`와 달리) 모듈 최상단에서 DB.init_db() 를
#    실제로 실행해 파일을 만든다 — 그래서 프로젝트 폴더 안 고정 경로가
#    아니라 매번 새 임시 디렉터리를 쓴다(round566 관례, 재실행해도
#    프로젝트 트리에 흔적이 안 남는다).
_tmpdir = tempfile.mkdtemp(prefix="round588_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ.setdefault("BOKGUON_LOG_FILE",
                       os.path.join(HERE, "logs", "test_round588.log"))
sys.path.insert(0, HERE)

import app as A  # noqa: E402

APP_SRC = read("app.py")

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk(APP_SRC.count("_rate_lock = threading.Lock()") == 1,
    "★★★ _rate_lock 전역 락이 정확히 한 곳에서 신설됐다")

_start = APP_SRC.index("\ndef check_rate_limit():") + 1
_end_marker = "            bucket.append(now)\n        break\n    return None\n"
chk(APP_SRC.count(_end_marker) == 1,
    "(준비) check_rate_limit() 끝 표식이 파일 전체에서 유일하다")
_end = APP_SRC.index(_end_marker) + len(_end_marker)
FN_NEW = APP_SRC[_start:_end]

chk(FN_NEW.startswith("def check_rate_limit():"), "(준비) 함수 본문을 정확히 추출했다")
chk(FN_NEW.count("with _rate_lock:") == 1,
    "★★★★★ check_rate_limit() 안에 with _rate_lock: 이 정확히 한 곳")
chk("bucket.append(now)" in FN_NEW and "if len(bucket) >= limit:" in FN_NEW,
    "  회귀 방지: 기존 확인·추가 로직 문구가 그대로 남아 있다")
_i_with = FN_NEW.index("with _rate_lock:")
_i_append = FN_NEW.index("bucket.append(now)")
chk(_i_with < _i_append, "★★ with _rate_lock: 이 append 보다 앞에 있다(범위 안)")


# ============================================================
print("\n[2]+[3]+[4] 실행 — 실제 함수를 배리어로 경합시켜 지금/옛 버전을 대조")
# ------------------------------------------------------------

def _dedent_after_lock(fn_src):
    """`with _rate_lock:` 한 줄만 제거하고 그 블록만 되돌려, 옛(락 없는) 버전을
    복원한다 — round585 식 "고치기 전 그대로 재구성" 기법. break 줄 앞까지만
    되돌리므로 그 뒤(break/return None)는 완전히 동일하게 남는다."""
    lines = fn_src.split("\n")
    i_lock = next(i for i, ln in enumerate(lines) if "with _rate_lock:" in ln)
    i_break = next(i for i, ln in enumerate(lines) if ln.strip() == "break")
    assert i_break > i_lock
    out = lines[:i_lock]
    for ln in lines[i_lock + 1:i_break]:
        assert ln.startswith("    "), f"예상과 다른 들여쓰기: {ln!r}"
        out.append(ln[4:])
    out.extend(lines[i_break:])
    return "\n".join(out)


def _inject_hook(fn_src):
    """"bucket.append(now)" 바로 앞줄에 테스트 전용 _BARRIER_HOOK() 호출을
    끼워 넣는다 — 실제 코드에는 없는, 검증 전용 관측 지점이다. 원래 있던
    "확인 다음에 추가" 라는 두 문장 경계에만 얹으므로 새 경쟁을 만들지
    않고 원래 경쟁을 결정론적으로 드러낼 뿐이다."""
    marker = "bucket.append(now)"
    idx = fn_src.index(marker)
    line_start = fn_src.rfind("\n", 0, idx) + 1
    indent = fn_src[line_start:idx]
    hooked = fn_src[:line_start] + indent + "_BARRIER_HOOK()\n" + fn_src[line_start:]
    assert hooked.count("_BARRIER_HOOK()") == 1
    return hooked


OLD_SRC = _dedent_after_lock(FN_NEW)
chk("with _rate_lock:" not in OLD_SRC and "bucket.append(now)" in OLD_SRC,
    "(준비) 되돌린 옛 버전에 락이 없고 나머지 로직은 그대로다")
#  ⚠ break/return 뒤쪽은 두 버전이 완전히 동일해야 한다(과잉수정 방지 대조).
chk(FN_NEW.split("break", 1)[1] == OLD_SRC.split("break", 1)[1],
    "★★ (준비) 되돌린 옛 버전은 break 지점 이후가 지금 버전과 완전히 동일하다")


def _build_fn(fn_src, rules, buckets, lock, hook):
    ns = dict(vars(A))
    ns["RATE_RULES"] = rules
    ns["_rate_buckets"] = buckets
    ns["_rate_lock"] = lock
    ns["_BARRIER_HOOK"] = hook
    exec(compile(fn_src, "<r588_check_rate_limit>", "exec"), ns)  # noqa: S102
    return ns["check_rate_limit"]


IP = "203.0.113.9"
PATH = "/r588x"
KEY = f"{IP}|*|^{re.escape(PATH)}$"


def _run_race(fn_src, limit, n, use_barrier=True):
    rules = [(None, re.compile(f"^{re.escape(PATH)}$"), limit, 600)]
    buckets = defaultdict(deque)
    lock = threading.Lock()
    hits = {"n": 0}
    hits_lock = threading.Lock()
    barrier = threading.Barrier(n) if use_barrier else None

    def hook():
        with hits_lock:
            hits["n"] += 1
        if barrier is not None:
            try:
                barrier.wait(timeout=1.5)
            except threading.BrokenBarrierError:
                pass  # 락이 막아 혼자 도달한 스레드 — 상대를 기다리지 않고 진행

    fn = _build_fn(_inject_hook(fn_src), rules, buckets, lock, hook)
    results = [None] * n

    def worker(i):
        with A.app.test_request_context(PATH, method="GET",
                                         environ_base={"REMOTE_ADDR": IP}):
            try:
                results[i] = fn()
            except Exception as e:                                    # noqa: BLE001
                results[i] = ("EXC", f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    return {
        "hits": hits["n"],
        "allowed": sum(1 for r in results if r is None),
        "blocked": sum(1 for r in results if isinstance(r, int)),
        "exc": [r for r in results if isinstance(r, tuple)],
        "final_len": len(buckets[KEY]),
        "results": results,
    }


LIMIT, N = 3, 12

try:
    # ── [2] 순차 안전 — 스레드 하나씩, 배리어 없이 (limit+2)회 호출 ──
    seq = _run_race(FN_NEW, LIMIT, LIMIT + 2, use_barrier=False)
    chk(not seq["exc"], "STEP 순차 호출은 예외 없이 끝난다", seq["exc"])
    chk(seq["allowed"] == LIMIT and seq["blocked"] == 2,
        "STEP 순차(동시성 없음) 호출은 지금까지처럼 정확히 limit 개만 허용한다"
        "(락을 씌워도 회귀 없음)", seq)

    # ── [3] 지금 코드(락 있음) — N개 스레드가 동시에 부딪힌다 ──
    new = _run_race(FN_NEW, LIMIT, N, use_barrier=True)
    chk(not new["exc"], "STEP 지금 코드: 예외 없이 모두 응답했다", new["exc"])
    chk(new["hits"] == LIMIT,
        f"★★★★★ 지금 코드: 배리어 훅에 도달한 스레드가 정확히 limit={LIMIT}개뿐"
        "(락이 나머지 스레드를 애초에 못 들어오게 막아 경쟁 자체가 성립하지 않는다)",
        new)
    chk(new["allowed"] == LIMIT and new["blocked"] == N - LIMIT,
        f"★★★★★ 지금 코드: {N}개 동시요청 중 정확히 limit={LIMIT}개만 허용된다",
        new)
    chk(new["final_len"] == LIMIT,
        "★★★★★ 지금 코드: 최종 버킷 길이가 limit 을 넘지 않는다", new["final_len"])

    # ── [4] 되돌리기-증명 — 락 없는 옛 버전을 같은 방식으로 경합 ──
    old = _run_race(OLD_SRC, LIMIT, N, use_barrier=True)
    chk(not old["exc"], "STEP 되돌린 옛 코드: 예외 없이 모두 응답했다", old["exc"])
    chk(old["hits"] == N,
        f"★★★★★ 되돌린(옛) 코드: {N}개 스레드 전부가 배리어 훅에 도달했다"
        "(아무도 먼저 append 하지 않은 채 다 같이 '아직 한도 안'을 읽었다는 뜻 "
        "— 바로 이것이 락 없는 원래 결함의 경쟁 조건이다)", old)
    chk(old["allowed"] == N,
        f"★★★★★ 되돌린(옛) 코드: limit={LIMIT} 인데 {N}개 요청이 전부 허용된다"
        "(지금 코드는 정확히 limit 개만 허용 — 이 차이가 이번 수정의 인과효과)", old)
    chk(old["final_len"] == N and old["final_len"] > LIMIT,
        f"★★★★★ 되돌린(옛) 코드: 최종 버킷 길이 {old['final_len']} 이 "
        f"limit={LIMIT} 을 실제로 초과한다(설정한 한도가 무의미해짐)", old)
except Exception as e:                                                 # noqa: BLE001
    chk(False, "★★★ 라운드588 [2]~[4] 실행", f"{type(e).__name__}: {e}")


print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
