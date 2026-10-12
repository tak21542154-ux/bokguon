# -*- coding: utf-8 -*-
"""스캔 639라운드 회귀 — collect_emails.py 의 robots_allows() 가 응답 없는
   서버를 만나면 무한정 멈추던 결함(이 파일의 다른 모든 네트워크 호출과
   달리 timeout 이 전혀 없었다).

   조사 배경 — 표준 라이브러리 urllib.robotparser.RobotFileParser.read() 는
   내부에서 `urllib.request.urlopen(self.url)` 을 timeout 인자 없이 호출한다
   (실제 소스로 확인: read() 정의에 timeout 관련 코드가 전혀 없음). 이
   파일의 다른 모든 네트워크 호출은 명시적으로 시간을 제한한다 — fetch() 는
   `urlopen(req, timeout=TIMEOUT)`(8초). 그런데 robots_allows() 만은 그
   방어가 빠져 있었고, collect_one() 은 이 함수를 fetch() 보다 먼저,
   사이트 한 곳당 최대 7번(진입 1회 + SUB_PATHS 6회) 부른다 — 서버 하나가
   TCP 연결만 받고 응답을 전혀 안 보내면(방화벽·과부하·의도적 슬로로리스성
   서버 등) main() 의 배치 루프 전체가 그 자리에서 영구히 멈춘다. 이는 이
   파일 자신의 docstring 이 명시한 원칙("응답이 느리거나 막히면 그냥
   건너뛴다 — 수집은 부가 작업이지 서비스가 아니다")과 정면으로 어긋난다.

   고침(collect_emails.py robots_allows(), 225~266행): rp.read() 호출
   구간에만 프로세스 전역 소켓 기본 타임아웃을 fetch() 와 같은 TIMEOUT(8초)
   으로 잠깐 걸었다 finally 로 복원한다. rp.read() 자체의 HTTP 오류코드
   처리(401/403 전체거부·기타 4xx 전체허용)는 그대로 재사용된다.

   이 테스트는 실제로 바이트를 전혀 보내지 않는 로컬 TCP 리스너를 세워
   놓고, (1) 고친 함수가 실제로 시간 안에 돌아오는지, (2) 되돌린(고치기 전)
   함수는 같은 시간 안에 돌아오지 못하고 여전히 멈춰 있는지, (3) 실제
   호출부인 collect_one() 도 끝까지 시간 안에 완주하는지를 모두 실측한다
   (소스 텍스트 검사가 아니라 실행 시간으로 증명한다).

      python test_scan_round639_fixes.py
"""
import os
import sys
import socket
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 639라운드 회귀 — collect_emails.robots_allows() 무한대기 결함")
print("=" * 72)

#  이 프로세스가 실수로 운영 DB 를 열지 않도록 먼저 격리 경로를 지정한다
#  (collect_emails 는 최상위에서 `import db as DB` 를 한다).
os.environ.setdefault("BOKGUON_DB_PATH", os.path.join(HERE, "_r639_unused.db"))
#  이 테스트의 목적은 SSRF 방어(라운드517)가 아니라 timeout 자체이므로,
#  라운드517·218 테스트와 같은 방식으로 로컬 서버만 예외로 허용한다
#  (운영에서는 이 환경변수를 절대 켜지 않는다).
os.environ["BOKGUON_COLLECT_ALLOW_LOCAL"] = "1"
sys.path.insert(0, HERE)
import collect_emails as CE  # noqa: E402

CE.PAUSE = 0


# ══════════════════════════════════════════════════════════════
#  바이트를 전혀 보내지 않는 TCP 리스너 — 연결은 받지만 응답이 영원히
#  없는 서버(방화벽에 막혔거나 멈춘 사이트)를 흉내낸다.
# ══════════════════════════════════════════════════════════════
class HangingServer:
    def __init__(self):
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(5)
        self.port = self.srv.getsockname()[1]
        self.held = []
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._accept_loop, daemon=True)
        self._t.start()

    def _accept_loop(self):
        self.srv.settimeout(0.5)
        while not self._stop.is_set():
            try:
                conn, _ = self.srv.accept()
                self.held.append(conn)          # 받기만 하고 절대 쓰지 않는다
            except socket.timeout:
                continue
            except OSError:
                break

    @property
    def base(self):
        return f"http://127.0.0.1:{self.port}"

    def close(self):
        self._stop.set()
        for c in self.held:
            try:
                c.close()
            except Exception:
                pass
        try:
            self.srv.close()
        except Exception:
            pass


def run_bounded(fn, *args, wait):
    """fn(*args) 를 별도 스레드에서 실행하고 wait 초 안에 끝나는지 관찰한다.
    반환: (finished_within_wait, result_or_None)."""
    box = {}

    def _run():
        box["val"] = fn(*args)

    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(wait)
    return (not th.is_alive()), box.get("val")


WAIT = 12   # CE.TIMEOUT(8초)보다 넉넉히 크다 — 고친 쪽은 이 안에 끝나야 하고,
            # 되돌린(옛) 쪽은 이 안에 못 끝나야 결함이 재현된 것이다.

# ══════════════════════════════════════════════════════════════
print(f"\n[1] 실행 — 고친 robots_allows() 가 응답 없는 서버에서도 {WAIT}초 안에 돌아오는가")
# ──────────────────────────────────────────────────────────────
srv1 = HangingServer()
try:
    t0 = time.time()
    finished, result = run_bounded(CE.robots_allows, srv1.base, "/", wait=WAIT)
    elapsed = time.time() - t0
    chk(finished,
        f"★★★★★ robots_allows() 가 {WAIT}초 안에 반환했다(무한대기 아님)",
        f"elapsed={elapsed:.1f}s")
    chk(result is True,
        "★★★ 응답이 없어 못 읽었으므로 보수적으로 허용(True) — 기존 원칙 그대로",
        result)
    chk(CE.TIMEOUT - 1 <= elapsed <= WAIT,
        f"★★★ 걸린 시간이 fetch() 와 같은 TIMEOUT({CE.TIMEOUT}초) 부근이다"
        "(전역 무제한이 아니라 이 상수로 제한됐다는 증거)",
        f"elapsed={elapsed:.1f}s")
finally:
    srv1.close()

# ══════════════════════════════════════════════════════════════
print(f"\n[2] 되돌리기 — 고치기 전 코드는 같은 {WAIT}초 안에 못 돌아오는가(인과관계 직접증명)")
# ──────────────────────────────────────────────────────────────
#  ⚠ 실제 파일은 절대 건드리지 않는다 — 라운드639 이전 원문 그대로를 문자열로
#    재현해 독립된 네임스페이스 사본에만 넣는다(표준 규칙 3항: 함수 단위,
#    다른 곳에서 그대로 호출되지 않는 함수 → 독립 네임스페이스에 exec).
_OLD_SRC = '''
def robots_allows(base, path="/"):
    try:
        parsed = urlparse(base)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if parsed.hostname and _host_is_internal(parsed.hostname, port):
            return False
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(urljoin(base, "/robots.txt"))
        rp.read()
        return rp.can_fetch(UA, urljoin(base, path))
    except Exception:
        return True
'''
_ns = dict(vars(CE))   # 독립 사본 — 실제 모듈 __dict__ 는 안 건드린다
exec(compile(_OLD_SRC, "<round639_old_robots_allows>", "exec"), _ns)
old_robots_allows = _ns["robots_allows"]

srv2 = HangingServer()
try:
    t0 = time.time()
    finished2, _ = run_bounded(old_robots_allows, srv2.base, "/", wait=WAIT)
    elapsed2 = time.time() - t0
    chk(not finished2,
        f"★★★★★ 되돌린(고치기 전) robots_allows() 는 {WAIT}초가 지나도 "
        "여전히 멈춰 있다 — timeout 부재로 인한 무한대기가 실제로 재현된다",
        f"elapsed>={elapsed2:.1f}s, still_running={not finished2}")
finally:
    srv2.close()   # 데몬 스레드라 프로세스 종료 시 함께 정리된다(추가 대기 없음)

# ══════════════════════════════════════════════════════════════
print(f"\n[3] 실행 — 실제 호출부 collect_one() 도 끝까지 시간 안에 완주하는가")
# ──────────────────────────────────────────────────────────────
#  collect_one() 은 robots_allows() 다음에 fetch() 도 부른다 — 같은 서버가
#  두 단계 모두에서 응답이 없으므로 최악의 경우 TIMEOUT 두 번(robots+본문)
#  만큼 걸린다. 그래도 유한해야 한다(예전엔 첫 단계에서 이미 영구히 멈췄다).
srv3 = HangingServer()
try:
    COLLECT_WAIT = CE.TIMEOUT * 2 + 6   # robots + fetch 두 번의 TIMEOUT + 여유
    t0 = time.time()
    finished3, res3 = run_bounded(CE.collect_one, srv3.base, wait=COLLECT_WAIT)
    elapsed3 = time.time() - t0
    chk(finished3,
        f"★★★★★ collect_one() 이 {COLLECT_WAIT}초 안에 끝까지 완주한다"
        "(robots_allows() 하나 때문에 배치 전체가 영구히 멈추지 않는다)",
        f"elapsed={elapsed3:.1f}s, result={res3}")
    if finished3:
        chk(res3 == ([], "접속 실패"),
            "STEP 응답 없는 서버는 결국 '접속 실패'로 정리된다(회귀 아님 확인)",
            res3)
finally:
    srv3.close()

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
