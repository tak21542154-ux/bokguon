# -*- coding: utf-8 -*-
"""스캔 519라운드 회귀 — round518(check_orphan_chars.py)과 같은 클래스의 cp949
   콘솔 크래시가 남아 있던 형제 배치 CLI 6개.

   배경 — round518이 check_orphan_chars.py 하나를 고치면서 "이 저장소의 거의
   모든 단독 실행 CLI는 이미 stdout.reconfigure(utf-8) 방어를 갖고 있다"고
   적어 뒀다. 이번 라운드는 그 말을 액면 그대로 믿지 않고 직접 grep 으로
   "실행: python 파일명.py" 식 배치 CLI를 전수 나열한 뒤, 그중 방어가 없는
   자리를 하나씩 대조했다(하위위임 없음, 이 세션이 직접 확인).

   [1순위] 이미 리드가 있던 3개 — 전부 grep 으로 방어 부재를 직접 재확인 후 수정.
     · collect_emails.py:351  print(f"  이메일 수집 — 대상 {{len(targets)}}곳 …")
     · build_pages.py(drop_unfilled_rows)  print(f"  ⚠ 표 밖 자리표시자 {{after}}곳 — 문구 확인 필요")
       build_pages.py(build 끝)            print(f"  docs/ 생성 완료 — 파일 {{n}}개")
     · clean_collected_emails.py(main 머리) print(f"  수집분 검사 — {{len(rows)}}건")
       clean_collected_emails.py(삭제 실패) print(f"  ⚠ {{r['name'][:20]:20}} 삭제 실패(…) — 건너뜀")

   [2순위] 전수조사로 새로 찾은 것 — serve_waitress.py (실서비스 운영 진입점 자신).
     app.py(print 8곳 실측 — 전부 fingerprint(d) 오탐이거나 개발서버 전용 분기)와
     wsgi.py(prints는 자신의 __main__ 분기뿐, import 시엔 안 돎)는 클린이었지만,
     serve_waitress.py 는 실제 배너 출력에 '⚠'(U+26A0, cp949 인코딩 불가 — 이
     세션이 c.encode('cp949') 로 직접 실측)를 쓰면서 방어가 전혀 없었다.
       · serve_waitress.py:72  print("  ⚠ BOKGUON_ENV=prod 가 아닙니다 …")
     BOKGUON_ENV 를 prod 로 명시하지 않은 채(dev 기본값) 감시자가 stdout 을
     파일로 리다이렉트해 재시작하면(운영 재시작 방식 그대로, round273 참고)
     서버가 배너조차 못 찍고 죽어 아예 기동하지 않는다 — 원래 3개보다 파급이
     더 크다고 판단해 이번 라운드에서 함께 고쳤다.

     serve_waitress.py 를 조사하다가 app.py 가 import 하는 로컬 모듈 11개를
     cp949 강제 환경에서 하나씩 import 해 stdout 인코딩 변화를 대조하는 방법
     으로(bisection) repair_estimate.py 가 이미 갖고 있던 방어가 app.py 를
     거치는 모든 실행에 **부작용으로** 전파된다는 것도 함께 밝혀졌다 — 그
     김에 app.py 가 import 하는 나머지 로컬 모듈의 __main__ 자체점검 블록도
     전수로 열어 보다가 crypto_util.py 도 같은 결함이 있음을 발견했다.
       · crypto_util.py(__main__ 자체점검 마지막 줄)  print("\\n검증 통과 — 암호화/복호화 정상")
     이 파일은 app.py 를 거쳐 실행될 땐 repair_estimate.py 의 방어에 우연히
     묻어가지만, "python crypto_util.py" 로 자기 자신의 암복호화 자체점검을
     단독 실행하면 그 우연한 구제가 없어 그대로 죽는다(실측 확인).

     crypto_util.py 를 고치며 같은 논리를 이어서, app.py 가 import 하는 db.py
     자신의 __main__ 자체점검("python db.py")도 열어 보니 똑같이 방어가 없고
     ⚠(U+26A0)을 쓰는 경고줄("기존 DB 에 데이터가 있습니다")이 있었다 — db.py
     는 app.py 보다 더 아래(기반) 계층이라 repair_estimate.py 의 우연한 구제가
     아예 닿지 않는다(app.py 가 db.py 를 import 하지, 그 반대가 아니다).

   여섯 파일 모두 고침은 동일 — check_tx_paths.py 가 이미 쓰는 방어(try: reconfigure,
   실패 시 TextIOWrapper 폴백)를 각 파일의 기존 import 직후에 그대로 옮겼다
   (새 헬퍼·새 상수 없음).

   실행 방식 — round518 의 표준을 따른다: 전부 실제 서브프로세스를
   PYTHONIOENCODING=cp949 로 강제해서 돌리고(콘솔에 안 붙어 있을 때 파이썬이
   stdout 인코딩을 고를 때 실제로 참조하는 값이자 이 저장소가 도는 한국어
   윈도 기본 ANSI 코드페이지), 각 파일마다 방어만 도려낸 사본으로 실제
   크래시를 재현하는 되돌림-증명까지 포함한다. DB 를 쓰는 두 파일
   (collect_emails.py·clean_collected_emails.py)은 BOKGUON_DB_PATH 를 스크래치
   경로로 못박고 seed_demo=False 인 빈 스키마로 초기화해(대상 0건 →
   네트워크 호출도 UPDATE 도 전혀 없음) 부작용 없이 print 라인만 지나가게
   했다. build_pages.py 는 실제 build()가 docs/ 를 rmtree 하므로 리포지토리
   실제 docs/ 를 절대 안 건드리도록 격리된 임시 디렉터리에 필요한 파일
   (templates/·static/·data/·legal_docs.py·envload.py)만 복사해 그 안에서
   돌렸다. serve_waitress.py 는 round273 이 이미 확립한 격리 포트 하드킬
   패턴을 그대로 재사용했다(운영 포트 8771 은 전혀 건드리지 않음).

      python test_scan_round519_fixes.py
"""
import io
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_healthz(port, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(0.2)
    return False


print("=" * 72)
print("  스캔 519라운드 회귀 — 배치 CLI 6종 cp949 콘솔 크래시(형제 미적용분)")
print("=" * 72)

GUARD_NEEDLE = 'sys.stdout.reconfigure(encoding="utf-8")'
#  네 파일 모두 이 접두어로 시작하는 같은 모양의 방어 주석을 쓴다(문구 뒷부분만 다름).
COMMENT_START = "#  ⚠ 윈도 기본 콘솔은 cp949 라 '"
#  가드 블록이 끝나고 원래 코드가 다시 시작되는 지점 — 파일마다 다르다.
RESUME_MARK = {
    "collect_emails.py": "_log = logging.getLogger(__name__)",
    "build_pages.py": "#  ⚠⚠ [라운드108] 이 스크립트만 공유 .env 로더(envload.py",
    "clean_collected_emails.py": "def is_junk(email, website):",
    "serve_waitress.py": "#  ⚠⚠ [라운드273] envload.py 자신의 문서는",
    "crypto_util.py": "_log = logging.getLogger(__name__)",
    "db.py": "_log = logging.getLogger(__name__)",
}

CP949_ENV = dict(os.environ)
CP949_ENV["PYTHONIOENCODING"] = "cp949"
CP949_ENV.pop("PYTHONUTF8", None)

_tmpdir = tempfile.mkdtemp(prefix="round519_")


def strip_guard(fn):
    """방어 블록만 정확히 도려낸 사본 소스를 돌려준다(되돌림-증명용)."""
    src = read(fn)
    gs = src.index(COMMENT_START)
    ge = src.index(RESUME_MARK[fn])
    assert 0 <= gs < ge, f"{fn}: 가드 경계를 못 찾음 — 앵커 재확인 필요"
    reverted = src[:gs] + src[ge:]
    assert GUARD_NEEDLE not in reverted, f"{fn}: 되돌린 사본에 방어가 아직 남아 있음"
    return reverted


def write_reverted(fn):
    path = os.path.join(HERE, f"_r519_reverted_{fn}")
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(strip_guard(fn))
    return path


def write_dep_revert(fn, alias):
    """의존 모듈(fn)의 방어를 지운 사본을 alias.py 이름으로 써서 경로를 돌려준다.

    ⚠ db.py 도 이번 라운드에서 방어가 생겼다 — collect_emails.py나
    clean_collected_emails.py 자신의 방어만 지우고 "import db as DB"는 그대로
    두면, 그 import 시점에 (이제 고쳐진) db.py 의 방어가 먼저 stdout 을
    utf-8 로 돌려놔 정작 보려는 파일 자신의 방어 부재가 가려진다(clean_
    collected_emails.py가 collect_emails.py에 대해 이미 겪은 것과 같은 함정을
    한 단계 더 아래 계층에서 다시 밟는다 — 이 세션이 실측으로 재확인). 인과
    관계를 순수하게 보려는 되돌리기는 이 의존 모듈도 함께 되돌려야 한다.
    """
    path = os.path.join(HERE, f"{alias}.py")
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(strip_guard(fn))
    return path


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 6개 파일 모두 형제(check_tx_paths.py)와 같은 방어가 있는가")
# ──────────────────────────────────────────────────────────────
FILES = ["collect_emails.py", "build_pages.py", "clean_collected_emails.py", "serve_waitress.py",
         "crypto_util.py", "db.py"]
for fn in FILES:
    src = read(fn)
    chk(GUARD_NEEDLE in src, f"{fn} 에 stdout.reconfigure(utf-8) 방어가 있다")
    chk(src.count(GUARD_NEEDLE) == 1, f"{fn} 방어는 정확히 한 번만 있다(중복 삽입 아님)",
        src.count(GUARD_NEEDLE))
sib = read("check_tx_paths.py")
chk(GUARD_NEEDLE in sib, "형제 check_tx_paths.py 도 같은 방어를 이미 갖고 있다(비교 기준)")


# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — collect_emails.py, cp949 로 강제해도 351행에서 안 죽는가")
# ──────────────────────────────────────────────────────────────
try:
    db1 = os.path.join(_tmpdir, "verify_collect.db")
    env1 = dict(CP949_ENV)
    env1["BOKGUON_DB_PATH"] = db1
    env1["BOKGUON_ENV"] = "dev"
    r_init = subprocess.run(
        [PY, "-c", "import db as DB; DB.init_db(seed_demo=False)"],
        cwd=HERE, env=env1, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60)
    chk(r_init.returncode == 0, "STEP 스크래치 DB 초기화 성공(partners 0건, 데모 없음)",
        r_init.stderr[-300:])

    r = subprocess.run([PY, "collect_emails.py", "--limit", "0", "--dry"], cwd=HERE, env=env1,
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        timeout=60)
    chk("UnicodeEncodeError" not in (r.stderr or ""),
        "★★★★★ cp949 로 강제해도 UnicodeEncodeError 없이 끝까지 돈다", (r.stderr or "")[-300:])
    chk("Traceback" not in (r.stderr or ""),
        "★★★★ 어떤 예외로도 죽지 않는다(트레이스백 없음)", (r.stderr or "")[-300:])
    chk("이메일 수집 — 대상 0곳" in (r.stdout or ""),
        "★★★★★ 351행 머리글이 실제로 출력된다(대상 0곳 — 네트워크 호출 없음)",
        (r.stdout or "")[:300])
    chk(r.returncode == 0, "정상 종료(대상 0곳이라 반복문 없이 바로 끝)", r.returncode)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] 준비/실행", f"{type(e).__name__} {e}")


# ══════════════════════════════════════════════════════════════
print("\n[3] 되돌리기 — collect_emails.py 방어를 지우면 실제로 다시 죽는가")
# ──────────────────────────────────────────────────────────────
#  ⚠ collect_emails.py 는 db.py 를 import 한다. db.py 도 이번 라운드에서
#    방어가 생겼으므로, db.py 도 함께 되돌린 사본을 보도록 import 대상을
#    바꿔치기해야 순수한 인과관계가 나온다(write_dep_revert 참고).
revert1 = revert1_dep_db = None
try:
    revert1_dep_db = write_dep_revert("db.py", "_r519_reverted_dep_db")

    main_src = strip_guard("collect_emails.py")
    chk("import db as DB" in main_src,
        "STEP 되돌린 사본에 원래 'import db as DB' 문이 있다(치환 전 확인)")
    main_src = main_src.replace("import db as DB", "import _r519_reverted_dep_db as DB")
    revert1 = os.path.join(HERE, "_r519_reverted_collect_emails.py")
    with io.open(revert1, "w", encoding="utf-8") as f:
        f.write(main_src)

    r2 = subprocess.run([PY, os.path.basename(revert1), "--limit", "0", "--dry"],
                         cwd=HERE, env=env1, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=60)
    chk(r2.returncode != 0, "★★★★★ 방어를 지우면(db.py 도 함께) 비정상 종료한다"
        "(고치기 전엔 이랬다)", r2.returncode)
    chk("UnicodeEncodeError" in (r2.stderr or ""),
        "★★★★★ 방어를 지우면 cp949 환경에서 실제로 UnicodeEncodeError 로 죽는다"
        "(인과관계 확인)", (r2.stderr or "")[-300:])
    chk("이메일 수집 — 대상 0곳" not in (r2.stdout or ""),
        "★★★★ 되돌린 사본은 그 진단 줄을 한 줄도 못 낸다", (r2.stdout or "")[:200])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] 준비/실행", f"{type(e).__name__} {e}")
finally:
    for p in (revert1, revert1_dep_db):
        if p:
            try:
                os.remove(p)
            except OSError:
                pass


# ══════════════════════════════════════════════════════════════
print("\n[4] 실행 — build_pages.py drop_unfilled_rows(), cp949 로 강제해도 "
      "'표 밖 자리표시자' 줄에서 안 죽는가")
# ──────────────────────────────────────────────────────────────
#  모듈을 import 만 해서는(envload.load_dotenv 뿐) 파일시스템에 아무것도 안 쓴다 —
#  build() 를 실제로 부르지 않는 이 확인은 templates/static/data 사본 없이도 안전하다.
SYNTHETIC_HTML = ("<h3>제6조 (개인정보 처리의 위탁)</h3>"
                   "<p>일부 위탁 내용은 (미기재) 상태입니다.</p>"
                   "<h3>다음 조항</h3>")
_FN_SANDBOX = os.path.join(_tmpdir, "fn_sandbox")
try:
    os.makedirs(_FN_SANDBOX, exist_ok=True)
    shutil.copy2(os.path.join(HERE, "build_pages.py"), _FN_SANDBOX)
    shutil.copy2(os.path.join(HERE, "envload.py"), _FN_SANDBOX)
    snippet = ("import build_pages as BP\n"
               f"BP.drop_unfilled_rows({SYNTHETIC_HTML!r})\n")
    r = subprocess.run([PY, "-c", snippet], cwd=_FN_SANDBOX, env=CP949_ENV,
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        timeout=30)
    chk("UnicodeEncodeError" not in (r.stderr or ""),
        "★★★★★ cp949 로 강제해도 drop_unfilled_rows() 가 안 죽는다", (r.stderr or "")[-300:])
    chk("표 밖 자리표시자 1곳" in (r.stdout or ""),
        "★★★★★ '표 밖 자리표시자' 줄이 실제로 출력된다", (r.stdout or "")[:300])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [4] 준비/실행", f"{type(e).__name__} {e}")


# ══════════════════════════════════════════════════════════════
print("\n[5] 되돌리기 — build_pages.py 방어를 지우면 실제로 다시 죽는가"
      "('표 밖 자리표시자' 줄)")
# ──────────────────────────────────────────────────────────────
try:
    reverted_src = strip_guard("build_pages.py")
    with io.open(os.path.join(_FN_SANDBOX, "build_pages.py"), "w", encoding="utf-8") as f:
        f.write(reverted_src)
    snippet = ("import build_pages as BP\n"
               f"BP.drop_unfilled_rows({SYNTHETIC_HTML!r})\n")
    r2 = subprocess.run([PY, "-c", snippet], cwd=_FN_SANDBOX, env=CP949_ENV,
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         timeout=30)
    chk(r2.returncode != 0, "★★★★★ 방어를 지우면 비정상 종료한다(고치기 전엔 이랬다)",
        r2.returncode)
    chk("UnicodeEncodeError" in (r2.stderr or ""),
        "★★★★★ 방어를 지우면 cp949 환경에서 실제로 UnicodeEncodeError 로 죽는다",
        (r2.stderr or "")[-300:])
    chk("표 밖 자리표시자 1곳" not in (r2.stdout or ""),
        "★★★★ 되돌린 사본은 그 진단 줄을 한 줄도 못 낸다", (r2.stdout or "")[:200])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [5] 준비/실행", f"{type(e).__name__} {e}")


# ══════════════════════════════════════════════════════════════
print("\n[6] 실행 — build_pages.py 전체 build(), 격리 사본에서 마지막 요약줄까지 "
      "안 죽고 끝까지 도는가(리포지토리 실제 docs/ 는 안 건드림)")
# ──────────────────────────────────────────────────────────────
_BUILD_SANDBOX = os.path.join(_tmpdir, "build_sandbox")
try:
    os.makedirs(_BUILD_SANDBOX, exist_ok=True)
    shutil.copytree(os.path.join(HERE, "templates"), os.path.join(_BUILD_SANDBOX, "templates"))
    shutil.copytree(os.path.join(HERE, "static"), os.path.join(_BUILD_SANDBOX, "static"))
    shutil.copytree(os.path.join(HERE, "data"), os.path.join(_BUILD_SANDBOX, "data"))
    shutil.copy2(os.path.join(HERE, "legal_docs.py"), _BUILD_SANDBOX)
    shutil.copy2(os.path.join(HERE, "envload.py"), _BUILD_SANDBOX)
    shutil.copy2(os.path.join(HERE, "build_pages.py"), _BUILD_SANDBOX)   # 고친(현재) 버전

    r = subprocess.run([PY, "build_pages.py"], cwd=_BUILD_SANDBOX, env=CP949_ENV,
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        timeout=60)
    chk("UnicodeEncodeError" not in (r.stderr or ""),
        "★★★★★ cp949 로 강제해도 build() 전체가 안 죽는다", (r.stderr or "")[-300:])
    chk(r.returncode == 0, "정상 종료", (r.stderr or "")[-300:])
    chk("docs/ 생성 완료 — 파일" in (r.stdout or ""),
        "★★★★★ 마지막 요약줄이 실제로 출력된다(진짜 끝까지 돌았다는 증거)",
        (r.stdout or "")[:300])
    chk(os.path.isdir(os.path.join(_BUILD_SANDBOX, "docs", "legal")),
        "실제로 격리 사본 안에 docs/legal/ 이 생성됐다(리포지토리 실제 docs/ 는 무관)")
    chk(not os.path.isdir(os.path.join(HERE, "docs", "__round519_probe__")),
        "STEP 리포지토리 실제 docs/ 에는 이 테스트가 아무 흔적도 안 남겼다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [6] 준비/실행", f"{type(e).__name__} {e}")


# ══════════════════════════════════════════════════════════════
print("\n[7] 실행 — clean_collected_emails.py, cp949 로 강제해도 머리글에서 안 죽는가")
# ──────────────────────────────────────────────────────────────
try:
    env2 = dict(CP949_ENV)
    env2["BOKGUON_DB_PATH"] = db1        # [2]가 이미 초기화해 둔 같은 빈 스크래치 DB 재사용
    env2["BOKGUON_ENV"] = "dev"
    r = subprocess.run([PY, "clean_collected_emails.py", "--dry"], cwd=HERE, env=env2,
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        timeout=60)
    chk("UnicodeEncodeError" not in (r.stderr or ""),
        "★★★★★ cp949 로 강제해도 UnicodeEncodeError 없이 끝까지 돈다", (r.stderr or "")[-300:])
    chk("Traceback" not in (r.stderr or ""),
        "★★★★ 어떤 예외로도 죽지 않는다(트레이스백 없음)", (r.stderr or "")[-300:])
    chk("수집분 검사 — 0건" in (r.stdout or ""),
        "★★★★★ 머리글이 실제로 출력된다(대상 0건 — UPDATE 없음)",
        (r.stdout or "")[:300])
    chk(r.returncode == 0, "정상 종료", r.returncode)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [7] 준비/실행", f"{type(e).__name__} {e}")


# ══════════════════════════════════════════════════════════════
print("\n[8] 되돌리기 — clean_collected_emails.py 방어를 지우면 실제로 다시 죽는가")
# ──────────────────────────────────────────────────────────────
#  ⚠ clean_collected_emails.py 는 collect_emails.py 와 db.py 둘 다 import 한다
#    (24·23행). 둘 다 이미 이번 라운드에서 고쳐져 있어, 그 import 시점에
#    형제의 방어가 먼저 stdout 을 utf-8 로 돌려놔 이 파일 자신의 방어 부재가
#    가려진다 — 처음 실행에서 실제로 이 함정에 빠져 "안 죽음"으로 잘못 나옴을
#    이 세션이 실측으로 발견했다(원인: 프로세스의 sys.stdout 은 하나뿐이라
#    어느 모듈이든 먼저 reconfigure 하면 그 뒤 import 되는 모든 모듈의 print
#    가 함께 보호받는다). 인과관계를 순수하게 보려면 이 한 번의 실행에서는
#    collect_emails.py·db.py 둘 다 함께 되돌린 사본을 보도록 import 대상을
#    바꿔치기한다(collect_emails.py 사본 자신도 db.py 를 import 하므로 그
#    사본 안의 import 도 함께 바꿔친다 — 사슬 전체를 되돌려야 한다).
revert2 = revert2_dep = revert2_dep_db = None
try:
    revert2_dep_db = write_dep_revert("db.py", "_r519_reverted_dep_db")

    dep_src = strip_guard("collect_emails.py")
    chk("import db as DB" in dep_src,
        "STEP 되돌린 collect_emails.py 사본에 원래 'import db as DB' 문이 있다(치환 전 확인)")
    dep_src = dep_src.replace("import db as DB", "import _r519_reverted_dep_db as DB")
    revert2_dep = os.path.join(HERE, "_r519_reverted_dep_collect_emails.py")
    with io.open(revert2_dep, "w", encoding="utf-8") as f:
        f.write(dep_src)

    main_src = strip_guard("clean_collected_emails.py")
    chk("from collect_emails import" in main_src and "import db as DB" in main_src,
        "STEP 되돌린 사본에 원래 import 문 둘 다 있다(치환 전 확인)")
    main_src = main_src.replace("from collect_emails import",
                                 "from _r519_reverted_dep_collect_emails import")
    main_src = main_src.replace("import db as DB", "import _r519_reverted_dep_db as DB")
    revert2 = os.path.join(HERE, "_r519_reverted_clean_collected_emails.py")
    with io.open(revert2, "w", encoding="utf-8") as f:
        f.write(main_src)

    r2 = subprocess.run([PY, os.path.basename(revert2), "--dry"], cwd=HERE, env=env2,
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         timeout=60)
    chk(r2.returncode != 0, "★★★★★ 방어를 지우면(형제들도 함께) 비정상 종료한다"
        "(고치기 전엔 이랬다)", r2.returncode)
    chk("UnicodeEncodeError" in (r2.stderr or ""),
        "★★★★★ 방어를 지우면 cp949 환경에서 실제로 UnicodeEncodeError 로 죽는다"
        "(인과관계 확인)", (r2.stderr or "")[-300:])
    chk("수집분 검사 — 0건" not in (r2.stdout or ""),
        "★★★★ 되돌린 사본은 그 진단 줄을 한 줄도 못 낸다", (r2.stdout or "")[:200])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [8] 준비/실행", f"{type(e).__name__} {e}")
finally:
    for p in (revert2, revert2_dep, revert2_dep_db):
        if p:
            try:
                os.remove(p)
            except OSError:
                pass


# ══════════════════════════════════════════════════════════════
print("\n[9] 실행 — serve_waitress.py, 격리 포트+cp949 로 강제해도 72행 경고에서 "
      "안 죽고 정상 기동하는가(round273 격리 포트 패턴 재사용, 운영 포트 8771 안 건드림)")
# ──────────────────────────────────────────────────────────────
try:
    port1 = _free_port()
    env3 = dict(CP949_ENV)
    env3["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify_waitress.db")
    env3["BOKGUON_PORT"] = str(port1)
    env3["BOKGUON_ENV"] = "dev"          # prod 가 아니어야 72행 경고 분기를 실제로 탄다

    out_path = os.path.join(_tmpdir, "stdout_waitress.log")
    with open(out_path, "wb") as out_f:
        proc = subprocess.Popen([PY, "serve_waitress.py"], cwd=HERE, env=env3,
                                 stdout=out_f, stderr=subprocess.PIPE)
        up = _wait_healthz(port1)
        chk(up, "STEP 격리 포트에서 서버가 정상 기동했다(healthz 200, cp949 환경에서도)")
        proc.kill()
        try:
            _, stderr_tail = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            stderr_tail = b""
    with open(out_path, encoding="utf-8", errors="replace") as f:
        logged = f.read()
    chk("UnicodeEncodeError" not in (stderr_tail or b"").decode("utf-8", "replace"),
        "★★★★★ cp949 로 강제해도 UnicodeEncodeError 없이 기동한다",
        (stderr_tail or b"")[-300:])
    chk("복구온 서비스" in logged, "★★★★ 시작 배너가 로그에 남아 있다")
    chk("BOKGUON_ENV=prod 가 아닙니다" in logged,
        "★★★★★ 72행 경고줄까지 실제로 출력된다(고치기 전엔 여기서 죽었다)",
        logged[:300])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [9] 준비/실행", f"{type(e).__name__} {e}")


# ══════════════════════════════════════════════════════════════
print("\n[10] 되돌리기 — serve_waitress.py 방어를 지우면 실제로 다시 죽는가"
      "(포트를 바인딩하기 전에 죽으므로 서버는 안 뜬다)")
# ──────────────────────────────────────────────────────────────
#  ⚠⚠ serve_waitress.py 는 from wsgi import application 으로 app.py 전체를
#    끌어오는데, app.py 가 import 하는 repair_estimate.py 가 훨씬 전(라운드
#    도입 시점 미상, 이 파일과 무관하게 이미 존재)부터 자기 몫의 reconfigure
#    방어를 모듈 최상단(조건 없이)에 갖고 있다 — sys.stdout 은 프로세스에 하나
#    뿐이라 그 부작용으로 이 프로세스 전체가 먼저 utf-8 로 바뀌어 버려서,
#    serve_waitress.py 자신의 방어만 지우고 실제 app.py 를 그대로 붙이면
#    크래시가 가려진다(이 세션이 실측으로 발견 — 처음 실행 시 이 함정에 빠져
#    되돌리기가 크래시 대신 "정상 기동 후 30초 타임아웃"으로 잘못 나왔다).
#    인과관계를 순수하게 보려면 실제 app.py 대신 아무 방어도 없는 더미 WSGI
#    앱을 붙인다 — 이 앱은 어차피 serve() 호출 전에 죽어야 정상이므로 실제
#    앱 내용은 무관하다.
revert3 = None
sw_sandbox = os.path.join(_tmpdir, "sw_sandbox")
try:
    os.makedirs(sw_sandbox, exist_ok=True)
    shutil.copy2(os.path.join(HERE, "envload.py"), sw_sandbox)
    with io.open(os.path.join(sw_sandbox, "_stub_wsgi.py"), "w", encoding="utf-8") as f:
        f.write("def application(environ, start_response):\n"
                 "    start_response('200 OK', [('Content-Type', 'text/plain')])\n"
                 "    return [b'ok']\n")

    reverted_src = strip_guard("serve_waitress.py")
    chk("from wsgi import application" in reverted_src,
        "STEP 되돌린 사본에 원래 import 문이 있다(치환 전 확인)")
    reverted_src = reverted_src.replace("from wsgi import application",
                                         "from _stub_wsgi import application")
    revert3 = os.path.join(sw_sandbox, "serve_waitress.py")
    with io.open(revert3, "w", encoding="utf-8") as f:
        f.write(reverted_src)

    port2 = _free_port()
    env4 = dict(CP949_ENV)
    env4["BOKGUON_PORT"] = str(port2)
    env4["BOKGUON_ENV"] = "dev"
    r2 = subprocess.run([PY, "serve_waitress.py"], cwd=sw_sandbox, env=env4,
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         timeout=30)
    chk(r2.returncode != 0, "★★★★★ 방어를 지우면 비정상 종료한다(고치기 전엔 이랬다)",
        r2.returncode)
    chk("UnicodeEncodeError" in (r2.stderr or ""),
        "★★★★★ 방어를 지우면 cp949 환경에서 실제로 UnicodeEncodeError 로 죽는다"
        "(인과관계 확인 — 포트는 아예 안 뜬다)", (r2.stderr or "")[-300:])
    chk(not _wait_healthz(port2, timeout=2),
        "STEP 죽었으니 그 포트에서 서버가 응답하지 않는다(운영과 무관한 격리 포트)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [10] 준비/실행", f"{type(e).__name__} {e}")
#  ⚠ _tmpdir 는 아직 지우지 않는다 — [13]이 db.py 용 스크래치 DB 를 그 안에
#    새로 만든다. 정리는 파일 맨 끝(모든 섹션이 끝난 뒤) 한 번만 한다.


# ══════════════════════════════════════════════════════════════
print("\n[11] 실행 — crypto_util.py 자체점검(__main__), cp949 로 강제해도 마지막 줄에서 "
      "안 죽는가")
# ──────────────────────────────────────────────────────────────
#  DB·app.py 의존 없음 — BOKGUON_ENC_KEY 를 안 줘도 개발용 폴백 키로 자체점검이
#  끝까지 돈다(로그는 stderr 로 나가는 경고뿐이라 여기선 안 본다).
try:
    r = subprocess.run([PY, "crypto_util.py"], cwd=HERE, env=CP949_ENV,
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        timeout=30)
    chk("UnicodeEncodeError" not in (r.stderr or ""),
        "★★★★★ cp949 로 강제해도 UnicodeEncodeError 없이 끝까지 돈다", (r.stderr or "")[-300:])
    chk("검증 통과 — 암호화" in (r.stdout or ""),
        "★★★★★ 마지막 줄이 실제로 출력된다(자체점검이 끝까지 돌았다는 증거)",
        (r.stdout or "")[:300])
    chk(r.returncode == 0, "정상 종료", r.returncode)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [11] 준비/실행", f"{type(e).__name__} {e}")


# ══════════════════════════════════════════════════════════════
print("\n[12] 되돌리기 — crypto_util.py 방어를 지우면 실제로 다시 죽는가"
      "(app.py 를 거치지 않는 단독 실행이라 형제 부작용도 없다)")
# ──────────────────────────────────────────────────────────────
revert4 = None
try:
    revert4 = write_reverted("crypto_util.py")
    r2 = subprocess.run([PY, os.path.basename(revert4)], cwd=HERE, env=CP949_ENV,
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         timeout=30)
    chk(r2.returncode != 0, "★★★★★ 방어를 지우면 비정상 종료한다(고치기 전엔 이랬다)",
        r2.returncode)
    chk("UnicodeEncodeError" in (r2.stderr or ""),
        "★★★★★ 방어를 지우면 cp949 환경에서 실제로 UnicodeEncodeError 로 죽는다"
        "(인과관계 확인)", (r2.stderr or "")[-300:])
    chk("검증 통과 — 암호화" not in (r2.stdout or ""),
        "★★★★ 되돌린 사본은 그 마지막 줄을 못 낸다", (r2.stdout or "")[:200])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [12] 준비/실행", f"{type(e).__name__} {e}")
finally:
    if revert4:
        try:
            os.remove(revert4)
        except OSError:
            pass


# ══════════════════════════════════════════════════════════════
print("\n[13] 실행 — db.py 자체점검(__main__, 'python db.py --reset'), cp949 로 강제해도 "
      "'기존 DB 에 데이터가 있습니다' 경고줄에서 안 죽는가")
# ──────────────────────────────────────────────────────────────
#  db.py 는 app.py 처럼 repair_estimate.py 를 거치지 않는 단독 진입점이라
#  형제 부작용이 없다. 기존 데이터가 있는 DB 에 --reset(--yes 없이)을 걸면
#  ⚠ 경고 + 건수 요약을 찍고 SystemExit 으로 멈춘다 — 실제로 지우지 않는다.
db2 = os.path.join(_tmpdir, "verify_db_selfcheck.db")
env5 = dict(CP949_ENV)
env5["BOKGUON_DB_PATH"] = db2
env5["BOKGUON_ENV"] = "dev"
try:
    r_seed = subprocess.run([PY, "-c", "import db as DB; DB.init_db(seed_demo=True)"],
                             cwd=HERE, env=env5, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=60)
    chk(r_seed.returncode == 0, "STEP 데모 데이터가 있는 스크래치 DB 준비 성공(경고 조건 충족용)",
        r_seed.stderr[-300:])

    r = subprocess.run([PY, "db.py", "--reset"], cwd=HERE, env=env5,
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        timeout=60)
    chk("UnicodeEncodeError" not in (r.stderr or ""),
        "★★★★★ cp949 로 강제해도 UnicodeEncodeError 없이 경고까지 찍힌다", (r.stderr or "")[-300:])
    chk("기존 DB 에 데이터가 있습니다" in (r.stdout or ""),
        "★★★★★ 경고줄이 실제로 출력된다", (r.stdout or "")[:300])
    chk(r.returncode != 0,
        "STEP --yes 없인 실제로 지우지 않고 SystemExit 으로 멈춘다(안전 확인)", r.returncode)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [13] 준비/실행", f"{type(e).__name__} {e}")


# ══════════════════════════════════════════════════════════════
print("\n[14] 되돌리기 — db.py 방어를 지우면 실제로 다시 죽는가"
      "(app.py 를 거치지 않는 단독 실행이라 형제 부작용도 없다)")
# ──────────────────────────────────────────────────────────────
revert5 = None
try:
    revert5 = write_reverted("db.py")
    r2 = subprocess.run([PY, os.path.basename(revert5), "--reset"], cwd=HERE, env=env5,
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         timeout=60)
    chk(r2.returncode != 0, "★★★★★ 방어를 지우면 비정상 종료한다(고치기 전엔 이랬다)",
        r2.returncode)
    chk("UnicodeEncodeError" in (r2.stderr or ""),
        "★★★★★ 방어를 지우면 cp949 환경에서 실제로 UnicodeEncodeError 로 죽는다"
        "(인과관계 확인)", (r2.stderr or "")[-300:])
    chk("기존 DB 에 데이터가 있습니다" not in (r2.stdout or ""),
        "★★★★ 되돌린 사본은 그 경고줄을 못 낸다", (r2.stdout or "")[:200])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [14] 준비/실행", f"{type(e).__name__} {e}")
finally:
    if revert5:
        try:
            os.remove(revert5)
        except OSError:
            pass
    shutil.rmtree(_tmpdir, ignore_errors=True)


print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
