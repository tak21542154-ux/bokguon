# -*- coding: utf-8 -*-
"""스캔 305라운드 회귀 — envload.py(모든 진입점 공유 .env 로더) 결함 3건,
   이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — envload.py 자신의
   override 우선순위(이미 정해진 process 환경변수가 .env 보다 우선)는
   두 경로(python-dotenv 있음/없음) 모두 실측 결과 클린(round296 이 겪은
   현상은 이 메커니즘 자체의 결함이 아니었다). db.py 의 is_prod/seed_demo
   판정은 함수 안에서 그때그때 읽어 이번 결함들에 안 걸림. gunicorn_conf.py
   는 이미 287라운드가 정밀조사했고 이번에 확인한 각도(윈도/리눅스 바인딩·
   방화벽 정합성, X-Forwarded-For 신뢰범위, 로그·prune-logs 무관함, graceful
   reload 구조차이)도 전부 클린으로 재확인.

  [1][심각] envload.py 의 살아있는 경로(python-dotenv 설치돼 있으면 항상 이
      분기를 탄다 — requirements.txt 고정설치 확인)가 dotenv.load_dotenv() 를
      encoding 인자 없이 불러, 파이썬 기본값 "utf-8" 이 BOM 을 안 벗겼다.
      Windows 메모장·PowerShell 이 만든 .env(DEPLOY.md 92행이 이미 이 위험을
      경고)의 첫 줄 키가 그대로 "﻿KEY" 라는 다른 이름이 되어 os.environ
      에 원래 이름으로는 전혀 안 잡힌다 — 예외도 경고도 없다. 바로 아래
      대체 파서(34~39행)는 이미 encoding="utf-8-sig" 로 이 문제를 정확히
      막아 두고 있었는데, python-dotenv 가 있는 한 그 코드는 죽은 코드라
      실제로는 아무도 안 막고 있었다(if/else 두 경로 중 방어된 쪽만 죽어
      있는, 이 세션에 여러 번 나온 "보호된 분기는 안 도는데 도는 분기는
      무방비" 형태 — 이번엔 라운드286 이 아니라 처음부터 이 파일 자신의
      두 분기 사이 비대칭이었다). dotenv.load_dotenv() 에도 같은
      encoding="utf-8-sig" 를 넘겨 두 경로를 동일하게 방어.
  [2] manage.py 의 cmd_check() 가 자기만의 .env 재파싱(utf-8-sig 로 BOM 을
      막아 [1]보다 오히려 더 견고했다)을 따로 갖고 있어, 서버가 실제로
      쓰는 envload.load_dotenv() 가 [1] 결함으로 어떤 키를 놓쳐도 이
      재파싱이 os.environ.setdefault() 로 조용히 그 키를 되살려 냈다 —
      "manage.py check 는 배포 가능 이라는데 실제 서버는 dev 모드로 뜬다"는
      자기도구 거짓 초록(272라운드가 popbill_check.py 에서 이미 고친 것과
      같은 유형 — 서버가 실제로 쓰는 로더에 위임하지 않고 자체 파서를 둠).
      manage.py 61행의 envload.load_dotenv() 가 이미 이 명령 실행 전에
      끝나 있으므로, cmd_check() 의 중복 재파싱 블록을 제거하고 그 결과를
      그대로 신뢰하도록 수정.
  [3][심각] app.py 가 db·photo_ai 등 로컬 모듈 11개를 import 한 **뒤에**
      .env 를 로드했다(주석 자신은 "모듈 최상단에서 로드한다"고 주장했지만
      실제 위치는 그 11개 import 뒤였다). photo_ai.py 는 GEMINI_KEY·
      UPLOAD_ROOT·MAX_FILES_PER_CASE 등을 함수 안이 아니라 **모듈
      최상단에서 즉시 os.environ.get() 으로 읽어 전역변수에 얼려 둔다** —
      .env 로드가 그 import 보다 늦으면 그 사이에 이미 굳어 버린 값은
      그 뒤에 .env 를 로드해도 절대 안 바뀐다. wsgi.py·serve_waitress.py
      경유는 그쪽이 자신의 import(from app import app) 보다 먼저 이미
      한 번 로드해 둬서 우연히 안전했을 뿐 — `python app.py` 로 직접
      띄우는 경로(복구온_서버실행.bat 60행이 실제로 이 경로, 이 저장소
      docstring 3행도 이 실행법을 문서화)에서만 노출된다. .env 로드를
      다른 모든 import 보다 앞(import os 바로 다음)으로 옮겨 실제로
      "모듈 최상단"이 되도록 수정.

  ⚠ 이 테스트는 진짜 python-dotenv(설치 확인)·진짜 photo_ai.py·진짜
    app.py 를 그대로 쓴다. 실제 운영 .env·bokguon.db 는 전혀 안 건드리고,
    전부 스크래치 임시디렉터리의 가짜 .env·격리 DB로만 검증한다.
    import-순서 결함은 서브프로세스 3개(순서만 다르게 재현)로 실측한다 —
    이미 로드된 이 프로세스 자신의 sys.modules 캐시로는 재현이 불가능하다.

      python test_scan_round305_fixes.py
"""
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def _section(src, start_marker, end_marker):
    i0 = src.index(start_marker)
    i1 = src.index(end_marker, i0 + len(start_marker))
    return src[i0:i1]


ENVLOAD_SRC = read("envload.py")
MANAGE_SRC = read("manage.py")
APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 305라운드 회귀 — envload.py BOM·manage.py 이중파서·app.py import순서")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
DOTENV_BRANCH = _section(ENVLOAD_SRC, "from dotenv import load_dotenv as _ld", "except ImportError:")
chk('_ld(path, override=False, encoding="utf-8-sig")' in DOTENV_BRANCH,
    "★★★★★ envload.py 의 python-dotenv 경로가 이제 encoding=utf-8-sig 로 BOM 을 막는다"
    "(고치기 전엔 인자가 없어 파이썬 기본 utf-8 이 BOM 을 그대로 남겼다)")

CHECK_BODY = _section(MANAGE_SRC, "\ndef cmd_check(argv):", "\n    if os.environ.get(\"BOKGUON_ENV\"")
chk("open(envfile" not in CHECK_BODY,
    "★★★★★ manage.py cmd_check() 가 더는 .env 를 직접 재파싱하지 않는다"
    "(고치기 전엔 자체 파서가 있어 envload.py 의 결함을 조용히 가렸다)")
chk("envload.load_dotenv()" in MANAGE_SRC,
    "STEP manage.py 는 여전히(모듈 최상단에서) 공유 로더를 쓴다 — 없애기만 하고 안 부르게 된 게 아니다")

_i_load = APP_SRC.index("_load_dotenv()")
_i_db_import = APP_SRC.index("\nimport db as DB")
chk(_i_load < _i_db_import,
    "★★★★★ app.py 의 .env 로드가 이제 실제로 db 등 로컬 모듈 import 보다 앞선다"
    "(고치기 전엔 주석은 '모듈 최상단'이라 주장했지만 실제로는 11개 import 뒤였다)")
_i_import_os = APP_SRC.index("\nimport os")
chk(_i_import_os < _i_load < APP_SRC.index("\nimport io"),
    "STEP .env 로드가 import os 바로 다음, 그 뒤의 표준 라이브러리 import(io)보다도 앞이다"
    "(진짜 '모듈 최상단')")

# ============================================================
print("\n[2] 실행 — envload.py 가 BOM 붙은 .env 를 실제로 올바르게 읽는가")
# ------------------------------------------------------------
try:
    import dotenv as _dotenv_probe  # noqa: F401
    _HAS_DOTENV = True
except ImportError:
    _HAS_DOTENV = False
chk(_HAS_DOTENV, "STEP (사전조건) python-dotenv 가 실제로 설치돼 있다 — 이 환경에서 [1]의 살아있는 경로가 검증 대상이 맞다")

_tmpdir2 = tempfile.mkdtemp(prefix="round305_bom_")
_bom_env = os.path.join(_tmpdir2, "bom.env")
with open(_bom_env, "wb") as f:
    f.write(b"\xef\xbb\xbf")                      # UTF-8 BOM
    f.write("ROUND305_BOM_KEY=first-line-value\nROUND305_PLAIN_KEY=second-line-value\n".encode("utf-8"))

sys.path.insert(0, HERE)
try:
    import envload as EL

    for k in ("ROUND305_BOM_KEY", "ROUND305_PLAIN_KEY", "﻿ROUND305_BOM_KEY"):
        os.environ.pop(k, None)
    EL.load_dotenv(_bom_env)
    chk(os.environ.get("ROUND305_BOM_KEY") == "first-line-value",
        "★★★★★ BOM 붙은 .env 의 첫 줄 키가 실제로 정확한 이름(BOM 없이)으로 잡힌다"
        "(고치기 전엔 os.environ에 이 이름 자체가 없고 대신 앞에 BOM이 붙은 다른"
        " 이름으로 들어가 있었다)",
        os.environ.get("ROUND305_BOM_KEY"))
    chk("﻿ROUND305_BOM_KEY" not in os.environ,
        "STEP BOM이 붙은 잘못된 키 이름으로는 안 들어간다")
    chk(os.environ.get("ROUND305_PLAIN_KEY") == "second-line-value",
        "STEP 대조군 — BOM 의 영향을 안 받는 둘째 줄 키도 정상 반영된다(회귀 없음)")
finally:
    for k in ("ROUND305_BOM_KEY", "ROUND305_PLAIN_KEY", "﻿ROUND305_BOM_KEY"):
        os.environ.pop(k, None)

# ============================================================
print("\n[3] 실행 — import 순서: photo_ai 를 .env 로드보다 먼저/나중에 불렀을 때")
# ------------------------------------------------------------
_tmpdir3 = tempfile.mkdtemp(prefix="round305_order_")
_fake_env = os.path.join(_tmpdir3, "fake.env")
with open(_fake_env, "w", encoding="utf-8") as f:
    f.write("BOKGUON_GEMINI_KEY=round305-real-secret-999\n")


def _run(code):
    return subprocess.run([PY, "-c", code], cwd=HERE, capture_output=True,
                           text=True, encoding="utf-8", timeout=30)


try:
    # (A) 고친 순서 재현: .env 를 photo_ai import 전에 로드
    code_a = (
        "import sys; sys.path.insert(0, %r)\n"
        "import envload\n"
        "envload._ENV_PATH = %r\n"
        "envload.load_dotenv()\n"
        "import photo_ai as PHOTO\n"
        "print('GEMINI_KEY=' + repr(PHOTO.GEMINI_KEY))\n"
    ) % (HERE, _fake_env)
    ra = _run(code_a)
    chk("round305-real-secret-999" in ra.stdout,
        "★★★★★ .env 를 photo_ai import 전에 로드하면(지금 app.py 의 순서) "
        "GEMINI_KEY 가 .env 값을 정확히 받는다", ra.stdout + ra.stderr)

    # (B) 대조군 — 옛(결함) 순서 재현: photo_ai 를 먼저 import, 그 뒤에 .env 로드
    code_b = (
        "import sys; sys.path.insert(0, %r)\n"
        "import photo_ai as PHOTO\n"
        "import envload\n"
        "envload._ENV_PATH = %r\n"
        "envload.load_dotenv()\n"
        "print('GEMINI_KEY=' + repr(PHOTO.GEMINI_KEY))\n"
    ) % (HERE, _fake_env)
    rb = _run(code_b)
    chk("GEMINI_KEY=''" in rb.stdout,
        "★★★★★ 대조군 — photo_ai 를 .env 로드보다 먼저 import 하면(옛 app.py 순서) "
        "그 뒤에 .env 를 로드해도 GEMINI_KEY 는 빈 채로 얼어붙는다"
        "(고쳐야 했던 바로 그 결함의 메커니즘 실측)", rb.stdout + rb.stderr)

    # (C) 실제 app.py 를 그대로 import — 고친 파일 자체가 실제로 동작하는지
    _verify_db = os.path.join(_tmpdir3, "verify.db")
    code_c = (
        "import sys, os; sys.path.insert(0, %r)\n"
        "os.environ['BOKGUON_DB_PATH'] = %r\n"
        "os.environ['BOKGUON_ENV'] = 'dev'\n"
        "os.environ['BOKGUON_SEED_DEMO'] = '0'\n"
        "import envload\n"
        "envload._ENV_PATH = %r\n"
        "import app\n"
        "print('GEMINI_KEY=' + repr(app.PHOTO.GEMINI_KEY))\n"
    ) % (HERE, _verify_db, _fake_env)
    rc = _run(code_c)
    chk(rc.returncode == 0 and "round305-real-secret-999" in rc.stdout,
        "★★★★★ 실제 app.py(고친 뒤)를 그대로 import 해도 photo_ai.GEMINI_KEY 가 "
        ".env 값을 정확히 받는다 — 이 라운드가 옮긴 자리가 실제로 그 파일 안에서 "
        "동작한다", (rc.returncode, rc.stdout, rc.stderr[-800:]))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드305 [3] 준비/실행", f"{type(e).__name__} {e}")
finally:
    import shutil
    shutil.rmtree(_tmpdir2, ignore_errors=True)
    shutil.rmtree(_tmpdir3, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
