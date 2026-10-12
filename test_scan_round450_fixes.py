# -*- coding: utf-8 -*-
"""스캔 450라운드 회귀 — 평문 로그(bokguon.log) CRLF 개행주입(로그위조), 1건.

app.logger.error(...) 가 request.path 를 %s 로 그대로 찍으면, 경로에
URL인코딩된 CRLF(%0D%0A)가 있을 때 하나의 로그 레코드가 실제로 여러
물리적 줄로 쪼개져, 그중 한 줄이 실제 로그 포맷과 구분 안 되는 위조
항목이 될 수 있다(로그 위조 — 관리자를 속여 없었던 이벤트를 있었던
것처럼 보이게 하거나, 있었던 흔적을 헷갈리게 만듦). 같은 파일 1006행이
이미 %r 을 쓰는 안전한 관용구를 두고 있는데, 접속기록 실패 핸들러
(1111행 부근)와 전역 예외핸들러 err_500(1229행 부근, 앱 전체 처리 안
된 예외의 공용 싱크)만 %s 를 써 형제와 어긋나 있었다.

[1] 소스 확인 — 두 실제 호출부가 모두 %r 을 씀(옛 %s 버전은 없음).
[2] 순수 포맷 메커니즘 재현 — app.py 를 건드리지 않고 옛 포맷문자열
    (%s)과 새 포맷문자열(%r)을 직접 비교해 실제로 로그파일 물리줄이
    쪼개지는지/안 쪼개지는지 실측(되돌림-증명, 파일 미변경).
[3] 실제 app.py 통합 재현 — before_request 를 프로세스 메모리에서만
    강제로 예외를 던지게 바꿔치기해(디스크 파일은 무수정) 진짜
    err_500 이 실행되게 만들고, 그 실제 로그 출력을 캡처해 위조 문구가
    독립된 줄로 안 나타남을 확인.
"""
import io
import logging
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 450라운드 회귀 — 로그 CRLF 개행주입(로그위조)")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
APP_SRC = io.open(os.path.join(HERE, "app.py"), encoding="utf-8").read()

chk('app.logger.error("접속기록 저장 실패 %s %r — %s", request.method, request.path, e)' in APP_SRC,
    "★★★★★ 접속기록 실패 로그가 request.path 에 %r 을 쓴다")
chk('app.logger.error("[%s] %s %r — %s\\n%s", ref, request.method, request.path, e, traceback.format_exc())'
    in APP_SRC,
    "★★★★★ err_500(전역 예외핸들러)이 request.path 에 %r 을 쓴다")
chk('app.logger.error("접속기록 저장 실패 %s %s — %s", request.method, request.path, e)' not in APP_SRC,
    "옛 %s 버전(접속기록 실패 로그)이 더는 없다")
chk('app.logger.error("[%s] %s %s — %s\\n%s", ref, request.method, request.path, e, traceback.format_exc())'
    not in APP_SRC,
    "옛 %s 버전(err_500)이 더는 없다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 순수 포맷 메커니즘 재현 — app.py 무변경, 되돌림-증명")
# ══════════════════════════════════════════════════════════════
#  ⚠ 여기서 비교하는 "옛 포맷문자열"은 app.py 파일에서 읽어온 게 아니라
#    이 테스트가 인과관계 증명용으로 직접 적어 넣은 리터럴이다 — [1]이
#    이미 실제 app.py 에 이 문자열이 하나도 없음을 확인했다.
OLD_FMT = "[%s] %s %s — %s"      # 450라운드 이전(취약)
NEW_FMT = "[%s] %s %r — %s"      # 450라운드 이후(현재 app.py 와 동일)

forged_line = "2099-01-01 00:00:00 INFO FORGED-BY-TEST 관리자(admin) 로그인 성공"
malicious_path = "/probe\r\n" + forged_line + "\r\nend"


def _write_and_readback(fmt):
    tmpdir = tempfile.mkdtemp(prefix="round450_fmt_")
    log_path = os.path.join(tmpdir, "scratch.log")
    logger = logging.getLogger(f"round450-{id(fmt)}")
    logger.setLevel(logging.ERROR)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.error(fmt, "ref123", "GET", malicious_path, "RuntimeError(테스트)")
    handler.close()
    logger.removeHandler(handler)
    return io.open(log_path, encoding="utf-8").read().splitlines()


old_lines = _write_and_readback(OLD_FMT)
new_lines = _write_and_readback(NEW_FMT)


def _forged_appears_standalone(lines):
    return any(ln.strip() == forged_line for ln in lines)


chk(_forged_appears_standalone(old_lines),
    "★★★★★ 옛 %s 포맷(되돌림)에서는 위조 문구가 실제로 독립된 로그 줄로 쪼개진다"
    "(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명)",
    old_lines)
chk(not _forged_appears_standalone(new_lines),
    "★★★★★ 새 %r 포맷(현재 app.py)에서는 위조 문구가 독립된 줄로 안 나타난다",
    new_lines)
chk(len(old_lines) >= 2,
    "옛 포맷은 CRLF 때문에 물리적으로 여러 줄이 된다", old_lines)
chk(len(new_lines) == 1,
    "새 포맷은 CRLF 가 이스케이프되어 물리적으로 한 줄 그대로다", new_lines)
chk("\\r\\n" in new_lines[0] if new_lines else False,
    "새 포맷의 그 한 줄 안에 CRLF 가 리터럴 \\r\\n 으로(원본 바이트 아님) 보인다",
    new_lines)

# ══════════════════════════════════════════════════════════════
print("\n[3] 실제 app.py 통합 재현 — 진짜 err_500 실행 결과 캡처")
# ══════════════════════════════════════════════════════════════
_tmpdir = tempfile.mkdtemp(prefix="round450_app_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB              # noqa: E402
    DB.init_db()
    import app as A              # noqa: E402

    class _Capture(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []

        def emit(self, record):
            self.records.append(self.format(record))

    cap = _Capture()
    cap.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    A.app.logger.addHandler(cap)
    A.app.logger.setLevel(logging.ERROR)

    #  ⚠ before_request 가 무조건 부르는 함수를 프로세스 메모리에서만
    #    바꿔치기한다(디스크의 app.py 는 전혀 안 건드림) — 이 세션이
    #    계속 써 온 인위 결함주입 방법론(라운드270·446·450조사)과 동일.
    _orig_rate_limit = A.check_rate_limit

    def _boom(*a, **k):
        raise RuntimeError("R450-TEST-INJECTED-FAULT(재현용 인위결함, 실제 앱 결함 아님)")

    A.check_rate_limit = _boom
    try:
        c = A.app.test_client()
        r = c.get("/probe%0D%0A" + forged_line.replace(" ", "%20") + "%0D%0Aend")
        chk(r.status_code == 500,
            "강제 예외가 실제로 500 을 냄(err_500 실제 도달 확인)", r.status_code)
    finally:
        A.check_rate_limit = _orig_rate_limit
        A.app.logger.removeHandler(cap)

    captured_lines = []
    for rec in cap.records:
        captured_lines.extend(rec.splitlines())

    chk(len(cap.records) >= 1, "err_500 로그가 실제로 최소 1건 기록됨")
    chk(not _forged_appears_standalone(captured_lines),
        "★★★★★ 실제 app.py 실행 결과에서도 위조 문구가 독립된 줄로 안 나타난다",
        captured_lines)
    chk(any("\\r\\n" in ln for ln in captured_lines),
        "실제 캡처된 로그에도 CRLF 가 리터럴 \\r\\n 으로 남는다(원본 바이트 아님)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "[3] 통합 재현 준비/실행", f"{type(e).__name__}: {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
