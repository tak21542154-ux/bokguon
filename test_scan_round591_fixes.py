# -*- coding: utf-8 -*-
"""스캔 591라운드 회귀 — round590이 "부수 발견"으로만 남기고 넘어간 미스터리(전체배터리
   재실행 도중 app.py:api_unlock_login() 의 실패기록삭제 keys 목록이 잠깐 옛 4개 키
   (uname·"P:"·"I:"·"OTP:") 형태로 보였다 — round414 가 더한 "PW:"·"PWX:", round554 가
   더한 "OTPSETUP:" 세 창구가 빠진 상태)의 정확한 인과관계를 확정한다.

   round590 은 "동시세션 여러개 가능(git無)→라운드번호 파일 경합" 을 원인으로 **추정**만
   하고 원문을 복원한 뒤 넘어갔다. 직접 조사(하위위임 없음) 결과 더 정확한 인과관계를
   찾았다 — 별도 세션이 없어도 이 저장소 **자기 자신의** test_scan_round414_fixes.py
   [7-3]이 그 원인이었다.

   [7-3]은 (수정 전) "이 함수를 예전(round414 이전) 코드로 되돌려 계정잠금이 실제로
   안 풀리는 결함을 재현한다"를 증명하려고, reverted_3(옛 4키 버전)을 **실제 on-disk
   app.py 에 잠깐 써넣고** 하위 프로세스(파이썬 재기동 + db.init_db() + 전체 app.py
   재import + 브루트포스 루프)를 돌린 뒤 finally 에서 복원하는 옛 세대(round409~515대)
   기법을 썼다. 복원 로직 자체는 항상 정확했다(APP_SRC 는 매번 새로 읽고, NEW_3
   하드코딩 리터럴도 지금 app.py 문구와 바이트 단위로 일치 — "복원이 낡은 버전으로
   된다" 가설은 직접 대조로 반증됨). 문제는 write(reverted)→subprocess.run→write(restore)
   사이에 실제 파일이 옛 코드 상태로 열려 있는 **창** 자체였다 — 그 창이 열려 있는 동안
   이 저장소를 읽는 어떤 창구든(동시 세션이든, 이 세션 자신이 배터리를 background 로
   돌리며 병렬로 하는 Read/Grep 이든) 옛 코드를 보게 된다. round554([4])는 같은 함수를
   다루면서도 이미 "실제 파일은 전혀 건드리지 않는" exec()-네임스페이스 기법을 썼다 —
   round591 은 [7-3]을 그 형제 관례로 옮겨 창 자체를 없앴다(test_scan_round414_fixes.py
   자체 수정, OLD_3/NEW_3 상수와 인과관계 증명 내용은 그대로 — 기법만 교체).

   이 파일의 검사:
   [0] 정적 확인 — test_scan_round414_fixes.py 가 이제 실제로 안전 기법을 쓰는지
       (표시자: "_api_unlock_login_pre414" 존재, 그 재구성 블록 안에는 APP_PATH 쓰기가
       없음).
   [1] 격리 재현(더미 스크래치 파일만 사용, 진짜 app.py 는 전혀 손대지 않음) — 옛
       기법과 정확히 같은 모양(write reverted → subprocess.run → write restore in
       finally)이 동시 폴러에게 관측 가능한 창을 만든다는 것을 실측으로 증명한다
       (round590 관찰의 일반 메커니즘 증명).
   [2] 실제 실행 기반 회귀 가드 — 지금(수정된) test_scan_round414_fixes.py 를 실제
       하위 프로세스로 돌리면서, 그 동안 진짜 app.py 를 계속 폴링해 unlock_login()
       함수가 단 한 번도 옛 4키 형태(OLD_3)로 관측되지 않는지 확인한다(회귀 방지 —
       이 검사가 실패하면 [7-3]이 다시 실제 파일을 건드리는 기법으로 되돌아갔다는
       뜻). 실행 뒤 app.py 가 실행 전과 바이트 단위로 동일한지도 확인한다.

       python test_scan_round591_fixes.py
"""
import ast
import hashlib
import io
import os
import subprocess
import sys
import tempfile
import threading
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(HERE, "app.py")
R414_PATH = os.path.join(HERE, "test_scan_round414_fixes.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(path):
    return io.open(path, encoding="utf-8").read()


print("=" * 72)
print("  스캔 591라운드 회귀 — api_unlock_login() 키목록 '일시 되돌아감'의 인과관계")
print("=" * 72)

R414_SRC = read(R414_PATH)

# ==================================================================
print("\n[0] 정적 확인 — test_scan_round414_fixes.py [7-3]이 안전 기법(exec 재구성)을 쓰는가")
# ------------------------------------------------------------------
try:
    ast.parse(R414_SRC)
    chk(True, "STEP test_scan_round414_fixes.py 전체 ast.parse 성공")

    chk("_api_unlock_login_pre414" in R414_SRC,
        "★★★★★ [7-3]이 round554 형제 기법(exec 네임스페이스 재구성)을 쓴다"
        "(고치기 전엔 이 이름이 없었다)")

    #  ⚠ [7-3] 블록의 끝 경계는 "다음 except Exception as e:"(되돌리기 전체를 감싸는
    #    바깥쪽 안전망)다 — [라운드611] 이전엔 그 바로 뒤에 7-1·7-2를 위해 일부러
    #    남겨 둔 finally(io.open(APP_PATH, "w", ...) 복원)가 있었지만, 611이 7-1·7-2도
    #    같은 기법으로 옮기며 그 공유 안전망 자체를 걷어냈다(더 쓰는 곳이 없어서) —
    #    except 블록은 여전히 남아 있어 이 경계잡기는 그대로 유효하다.
    _i_73 = R414_SRC.index("[7-3]")
    _i_end73 = R414_SRC.index("except Exception as e:", _i_73)
    _block73 = R414_SRC[_i_73:_i_end73]
    chk("io.open(APP_PATH" not in _block73,
        "★★★★★ [7-3] 블록 안에는 실제 app.py(APP_PATH) 쓰기가 전혀 없다"
        "(round590이 관측한 그 창이 이 스텝에서는 구조적으로 불가능해졌다)")
    chk("_run_repro(" not in _block73,
        "STEP [7-3]이 더는 옛 세대 _run_repro()(실 파일 write) 헬퍼를 안 쓴다")

    #  [라운드611] 7-1·7-2도 이 라운드가 뒤이어 옮겼다 — "의도한 최소범위인지"
    #  (그대로 옛 기법을 쓰는지) 감시하던 이 검사는 이제 "뒤이은 이관이 실제로
    #  끝났는지"(_run_repro 가 파일 전체에서 완전히 사라졌는지)를 확인하는 검사로
    #  바뀐다 — round591 자신이 증명한 인과관계(창 자체가 위험하다)는 그대로,
    #  대상 스텝이 3개에서 0개로 준 것만 반영한다.
    _block71_72 = R414_SRC[R414_SRC.index("[7-1]"):_i_73]
    #  ⚠ 괄호(정의 "def _run_repro(" 또는 호출 "_run_repro(reverted_…")까지 봐야 한다 —
    #    이 파일·이 파일 자신의 역사를 설명하는 산문 주석(예: "잠깐 써넣고(_run_repro) …")
    #    은 그 이름을 언급만 할 뿐 실제 호출이 아니라, 이름만 보면 오탐이 난다.
    chk("_run_repro(" not in R414_SRC,
        "★★★★★ [라운드611] _run_repro()(옛 세대 실 파일 write 헬퍼)의 정의·호출이 이제 "
        "파일 전체에서 완전히 사라졌다(7-1·7-2까지 이관 완료 — 이름을 언급만 하는 "
        "산문 주석은 남아 있을 수 있다)")
    chk("_api_change_password_pre414" in _block71_72 and "_api_otp_disable_pre414" in _block71_72,
        "★★★★★ [라운드611] 7-1·7-2도 [7-3]과 같은 exec 재구성 기법(함수 리네임 후 "
        "네임스페이스 사본에서 재정의)을 쓴다")
    chk("io.open(APP_PATH" not in _block71_72,
        "★★★★★ [라운드611] 7-1·7-2 블록 안에도 실제 app.py(APP_PATH) 쓰기가 전혀 없다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [0] 정적 확인", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[1] 격리 재현 — 옛 write-revert-restore 기법이 동시 폴러에게 관측 가능한 창을 "
      "만드는가(더미 스크래치 파일만 사용, 진짜 app.py 는 전혀 안 건드림)")
# ------------------------------------------------------------------
try:
    _tmpdir = tempfile.mkdtemp(prefix="round591_windowproof_")
    dummy = os.path.join(_tmpdir, "dummy_app.py")
    CONTENT_CURRENT = "KEYS = ('uname','P:','I:','OTP:','PW:','PWX:','OTPSETUP:')\n" * 50
    CONTENT_REVERTED = "KEYS = ('uname','P:','I:','OTP:')\n" * 50
    io.open(dummy, "w", encoding="utf-8", newline="\n").write(CONTENT_CURRENT)

    seen = {"reverted": 0, "polls": 0}
    stop = threading.Event()

    def _poller():
        while not stop.is_set():
            try:
                data = io.open(dummy, "r", encoding="utf-8").read()
            except OSError:
                continue
            seen["polls"] += 1
            if data == CONTENT_REVERTED:
                seen["reverted"] += 1

    def _run_repro_like():
        """test_scan_round414_fixes.py 의 옛 _run_repro() 와 정확히 같은 모양."""
        try:
            io.open(dummy, "w", encoding="utf-8", newline="\n").write(CONTENT_REVERTED)
            subprocess.run([sys.executable, "-c", "import time; time.sleep(0.15)"],
                            capture_output=True, text=True, timeout=30)
        finally:
            io.open(dummy, "w", encoding="utf-8", newline="\n").write(CONTENT_CURRENT)

    th = threading.Thread(target=_poller, daemon=True)
    th.start()
    _run_repro_like()
    stop.set()
    th.join(timeout=2)

    final = io.open(dummy, "r", encoding="utf-8").read()
    chk(seen["polls"] > 0, "STEP 동시 폴러가 실제로 여러 번 읽었다", seen["polls"])
    chk(seen["reverted"] > 0,
        "★★★★★ 동시 폴러가 되돌려진(옛) 내용을 실제로 관측했다"
        "(round590이 본 것과 같은 메커니즘 — 복원이 틀린 게 아니라 창이 실재한다)",
        seen)
    chk(final == CONTENT_CURRENT,
        "STEP 복원은 항상 정확하다(최종 내용이 원본과 바이트 단위로 동일) — "
        "\"복원이 낡은 버전으로 된다\" 가설은 기각, \"창이 실재한다\"만 참",
        len(final))

    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [1] 격리 재현", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[2] 실제 실행 기반 회귀 가드 — 지금 코드로 test_scan_round414_fixes.py 를 실제로 "
      "돌리는 동안, 진짜 app.py 의 api_unlock_login() 이 단 한 번도 옛 4키 형태로 안 "
      "보이는가")
# ------------------------------------------------------------------
try:
    before_hash = hashlib.sha256(io.open(APP_PATH, "rb").read()).hexdigest()

    #  ⚠ OLD_3 문자열은 test_scan_round414_fixes.py 자신이 이미 정확한 원문으로 들고
    #    있다 — 손으로 다시 옮겨 적으면(한글·특수문자 포함) 오타 위험이 있으므로
    #    그 파일의 상수를 그대로 가져다 쓴다(직접 재입력 금지 — 이 프로젝트가 이미
    #    여러 번 겪은 "겹친 따옴표가 대상파일을 깨뜨린다" 류 함정 회피).
    _ns = {"__name__": "__round591_check__", "__file__": R414_PATH}
    _header_end = R414_SRC.index('print("=" * 72)')
    exec(compile(R414_SRC[:_header_end], "<r414_header>", "exec"), _ns)
    OLD_3 = _ns["OLD_3"]
    chk(isinstance(OLD_3, str) and len(OLD_3) > 10,
        "STEP test_scan_round414_fixes.py 에서 OLD_3 상수를 그대로 가져왔다")

    watch = {"saw_old_unlock": False, "polls": 0, "samples": []}
    stop2 = threading.Event()

    def _watch_unlock():
        while not stop2.is_set():
            try:
                cur = io.open(APP_PATH, encoding="utf-8").read()
            except OSError:
                time.sleep(0.005)
                continue
            watch["polls"] += 1
            if OLD_3 in cur:
                watch["saw_old_unlock"] = True
                watch["samples"].append(time.time())
            time.sleep(0.01)

    wth = threading.Thread(target=_watch_unlock, daemon=True)
    wth.start()

    _env = dict(os.environ)
    _env.setdefault("PYTHONIOENCODING", "utf-8")
    t0 = time.time()
    r = subprocess.run([sys.executable, R414_PATH], cwd=HERE, capture_output=True,
                        text=True, env=_env, encoding="utf-8", errors="replace",
                        timeout=180)
    elapsed = time.time() - t0

    stop2.set()
    wth.join(timeout=2)

    after_hash = hashlib.sha256(io.open(APP_PATH, "rb").read()).hexdigest()

    chk(r.returncode == 0,
        "STEP test_scan_round414_fixes.py 실제 실행이 지금도 그린이다(회귀 없음)",
        (r.returncode, (r.stdout + r.stderr)[-500:]))
    chk(watch["polls"] > 0, "STEP 감시 스레드가 실행 동안 app.py 를 실제로 여러 번 읽었다",
        (watch["polls"], f"{elapsed:.1f}초"))
    chk(watch["saw_old_unlock"] is False,
        "★★★★★ 실행 도중 단 한 번도 api_unlock_login() 이 옛 4키 형태(OLD_3)로 "
        "관측되지 않았다(회귀 가드 — round590이 본 창이 이 스텝에서는 사라졌다)",
        watch["samples"])
    chk(before_hash == after_hash,
        "★★★★★ 실행 전/후 app.py 가 바이트 단위로 완전히 동일하다(부작용 없음)",
        (before_hash[:12], after_hash[:12]))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] 실제 실행 기반 회귀 가드", f"{type(e).__name__} {e}")


print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
