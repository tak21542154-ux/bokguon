# -*- coding: utf-8 -*-
"""스캔 568라운드 회귀 — manage.py:main()(모든 명령이 실제로 거치는 유일한
   지점)의 명령 실행 호출에 try 가 없던 결함.

   조사 각도 — round557/558/559 가 이미 닫은 "예약 실행이 조용히 죽는다"
   앵글을 이 세션이 직접 조사(하위위임 없음)해, 그 세 라운드가 손대지 않은
   네 번째 지점을 찾았다. round557 은 cmd_sweep() **내부**의 무방비 try만
   고쳤을 뿐 main()(COMMANDS[cmd] 호출부, 당시도 지금도 try 없음) 자체는
   그대로 뒀다 — cmd_sweep 자신은 이제 내부에서 다 잡으니 상관없지만, 같은
   pythonw.exe 무출력리다이렉트 방식으로 등록되는 형제 예약(deploy/
   windows_setup.ps1 284·315·327행 New-ScheduledTaskAction — 전부 $vpyw 뿐
   ">>" 없음) 중 backup 을 뺀 나머지는 이 바깥 경계 없이는 무방비다:
     · cmd_prune_logs() — 본문(DELETE 두 건 + commit)에 try 자체가 없다.
     · cmd_prune_personal() — except sqlite3.Error 뿐이라, 그 안에서 도는
       int(os.environ.get("BOKGUON_TRASH_KEEP_DAYS", "30")) 같은 자리가
       ValueError 를 던지면(이 코드베이스 자신이 이미 겪은 함정 —
       manage.py _upload_root() 의 "빈 값을 기본값이 아니라 빈 문자열로
       받는다" 문제와 같은 계열의 운영자 설정 실수) 그대로 새나간다.
   이 세션 브리핑 1번 항목이 "여러 세션이 동시 편집 중"이라고 명시할 만큼
   WAL 동시쓰기 경합이 실제로 자주 있는 환경이라, sqlite3.OperationalError
   ("database is locked") 한 번이면 개인정보 보호법 §21 이 요구하는 주간
   파기(prune-logs·prune-personal 둘 다)가 콘솔도 없는 pythonw 아래서
   흔적 없이 죽는다 — manage.py check 의 job_locks 정체 감지(796·835행)가
   최대 10일 뒤 "멈췄다"는 보여줘도 **왜** 멈췄는지는 여전히 안 보인다
   (round557 이 cmd_sweep 에서 이미 짚은 바로 그 증상, 다른 명령에서 재발).

   고침 — 명령마다 따로 감싸는 대신, 모든 명령이 실제로 통과하는 단일
   지점인 main() 에 cmd_sweep 이 이미 세운 처방과 같은 모양(app 로거로
   전체 트레이스백을 남기고, 짧은 이유는 화면에도 찍고, 종료코드는 실패로)
   을 그대로 적용했다(manage.py 1곳, COMMANDS[cmd] 호출을 try/except
   Exception 으로 감쌈) — 이제 어떤 명령이 실패해도, 앞으로 추가될
   명령까지 포함해 자동으로 이 안전망을 받는다.

   이 회귀테스트는 ONLY 안전한 기법만 쓴다 — 실제 on-disk manage.py 는
   조회만 한다. "되돌리기" 증명은 이 세션이 고치기 직전 상태였던 옛
   main() 의 단일 반환문(`return COMMANDS[cmd](sys.argv[2:]) or 0`, try 없음)
   을 문자열로 그대로 재구성해 exec() 로 돌리고, 실제 M.COMMANDS 에 잠깐
   가짜 명령 하나만 주입해(실제 명령 로직은 전혀 안 건드림) 인과관계를
   실측한다 — round557 이 cmd_sweep 에 쓴 것과 같은 기법을 main() 에 적용.

       python test_scan_round568_fixes.py
"""
import contextlib
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


print("=" * 72)
print("  스캔 568라운드 회귀 — manage.py main() 의 명령 실행 호출에 try 없음")
print("=" * 72)

# ==================================================================
print("\n[0] 소스 확인 — manage.py main() 이 실제로 고쳐졌는가")
# ------------------------------------------------------------------
MANAGE_SRC = read("manage.py")
i0 = MANAGE_SRC.index("def main():")
MAIN_BODY = MANAGE_SRC[i0:]   # main() 은 파일의 마지막 함수(바로 뒤는 __main__ 블록)

chk("try:\n        return COMMANDS[cmd](sys.argv[2:]) or 0\n    except Exception as e:" in MAIN_BODY,
    "★★★★★ main() 의 COMMANDS[cmd] 호출이 이제 try/except Exception 으로 "
    "감싸져 있다(전에는 아무 방어도 없었다)")
chk("A.app.logger.exception(" in MAIN_BODY,
    "★★★★ 실패를 app 로거로 남긴다(형제 cmd_sweep, round557 과 같은 처방)")
chk('bad(f"명령 실행 중 처리되지 않은 오류로 중단됨' in MAIN_BODY,
    "  화면에도 짧은 이유를 찍는다")
chk(MAIN_BODY.count("return 1") >= 1 and "except Exception as e:" in MAIN_BODY,
    "★★★ 실패하면 종료코드 1을 반환한다(0을 보고해 조용히 성공으로 "
    "보이는 사고를 막는다)")
# import app 실패까지 대비하는 이중 안전망도 확인
_except_idx = MAIN_BODY.index("except Exception as e:")
_inner = MAIN_BODY[_except_idx:_except_idx + 400]
chk("import app as A" in _inner and "except Exception:\n            pass" in _inner,
    "  app 임포트 자체가 실패해도(예: DB 미초기화) 최소한 콘솔 메시지는 "
    "그대로 남도록 이중으로 감쌌다")

# ==================================================================
print("\n[1] 준비 — 스크래치 DB(오늘자 실제 스키마)")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round568_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
os.environ.setdefault("BOKGUON_LOG_FILE", os.path.join(_tmpdir, "test.log"))
sys.path.insert(0, HERE)

import db as DB
DB.init_db()
import app as A
import manage as M

_orig_argv = sys.argv
_orig_log_exc = A.app.logger.exception
_log_calls = []


def _recording_exception(msg, *a, **k):
    _log_calls.append(str(msg))
    return _orig_log_exc(msg, *a, **k)


def _raiser(argv):
    raise RuntimeError("R568_INJECTED — 가짜 명령 인위 실패")


# ==================================================================
print("\n[2] 되돌리기 — 옛(try 없는) main() 반환문을 그대로 재구성해 같은 "
      "실패가 실제로 밖까지 새는지 인과관계로 실측")
# ------------------------------------------------------------------
OLD_MAIN_DISPATCH_SRC = (
    "def _old_main_dispatch(cmd, COMMANDSd, rest_argv):\n"
    "    return COMMANDSd[cmd](rest_argv) or 0\n"
)
_ns = {}
exec(OLD_MAIN_DISPATCH_SRC, {}, _ns)

M.COMMANDS["__r568_boom__"] = _raiser
try:
    _old_raised = None
    try:
        _ns["_old_main_dispatch"]("__r568_boom__", M.COMMANDS, [])
    except RuntimeError as e:
        _old_raised = e
    except Exception as e:  # 혹시 다른 예외 모양이면 실패로 보이게 잡아 둔다
        _old_raised = e
    chk(_old_raised is not None and "R568_INJECTED" in str(_old_raised),
        "★★★★★ 옛 모양(try 없음)은 가짜 명령의 예외가 그대로 밖으로 샌다"
        "(수정 전 실제 상태를 인과관계로 증명 — 이게 새면 pythonw 아래서 "
        "트레이스백이 갈 곳 없이 사라지고 프로세스가 죽는다)",
        repr(_old_raised))

    # ==============================================================
    print("\n[3] 실행 — 실제 M.main() 은 같은 인위 실패에서도 죽지 않는가")
    # --------------------------------------------------------------
    A.app.logger.exception = _recording_exception
    sys.argv = ["manage.py", "__r568_boom__"]
    _new_raised = None
    _rc = None
    _out = io.StringIO()
    try:
        with contextlib.redirect_stdout(_out):
            _rc = M.main()
    except Exception as e:
        _new_raised = e
    finally:
        A.app.logger.exception = _orig_log_exc
    _console = _out.getvalue()

    chk(_new_raised is None,
        "★★★★★ 실제 M.main() 은 같은 인위 실패에서 더는 예외를 밖으로 "
        "던지지 않는다([2]와 정반대 결과 — 이 회귀가 진짜 차이를 잡아낼 "
        "능력이 있음)", repr(_new_raised))
    chk(_rc == 1,
        "★★★★ 실패한 명령은 종료코드 1을 반환한다", _rc)
    chk(any("__r568_boom__" in m for m in _log_calls),
        "★★★★ A.app.logger.exception() 이 실제로 호출됐다(logs/manage.log 에 "
        "왜 멈췄는지가 이제 남는다 — 전에는 pythonw 아래서 흔적이 없었다)",
        _log_calls)
    chk("명령 실행 중 처리되지 않은 오류로 중단됨" in _console
        and "R568_INJECTED" in _console,
        "  화면에도 원인 요약이 실제로 찍혔다", _console)

    # ==============================================================
    print("\n[4] 회귀 없음 — 정상 명령·미지 명령·도움말은 여전히 그대로 동작한다")
    # --------------------------------------------------------------
    _log_calls.clear()
    A.app.logger.exception = _recording_exception
    sys.argv = ["manage.py", "stats"]
    _out2 = io.StringIO()
    try:
        with contextlib.redirect_stdout(_out2):
            _rc_stats = M.main()
    finally:
        A.app.logger.exception = _orig_log_exc
    chk(_rc_stats == 0,
        "★★★ 정상 명령(stats)은 여전히 종료코드 0을 반환한다(회귀 없음)",
        _rc_stats)
    chk(not _log_calls,
        "  정상 명령은 app 로거의 exception() 을 전혀 건드리지 않는다"
        "(새 안전망이 실패도 아닌 것을 실패로 오탐하지 않는다)", _log_calls)

    sys.argv = ["manage.py", "이런명령없음"]
    _out3 = io.StringIO()
    with contextlib.redirect_stdout(_out3):
        _rc_unknown = M.main()
    chk(_rc_unknown == 1,
        "  미지 명령은 여전히 종료코드 1(새 try 블록 진입 전에 이미 걸러짐)",
        _rc_unknown)

    sys.argv = ["manage.py", "--help"]
    _out4 = io.StringIO()
    with contextlib.redirect_stdout(_out4):
        _rc_help = M.main()
    chk(_rc_help == 0, "  도움말은 여전히 종료코드 0", _rc_help)
finally:
    M.COMMANDS.pop("__r568_boom__", None)
    sys.argv = _orig_argv
    A.app.logger.exception = _orig_log_exc

# ==================================================================
# 정리
# ------------------------------------------------------------------
os.environ.pop("BOKGUON_DB_PATH", None)
os.environ.pop("BOKGUON_UPLOAD_DIR", None)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
