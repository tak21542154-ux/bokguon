@echo off
chcp 65001 > nul
title 복구온 — 체험 서버
cd /d "%~dp0"
color 0F

echo.
echo  ============================================================
echo    복구온 (BOKGUON) — 체험 서버
echo    (주)올림포스네트웍스 전략사업실 유경탁 파트장
echo  ============================================================
echo.

REM ══════════════════════════════════════════════════════════════
REM  이 파일 하나로 끝나게 만든 이유
REM
REM  다른 컴퓨터에서 기존 실행 파일을 눌렀을 때 창만 뜨고 포털이
REM  안 열리는 일이 있었다. 원인은 두 가지였다.
REM    ① .env 가 운영(prod)으로 되어 있어 개발 서버가 기동을 거부한다.
REM    ② 운영 모드는 데모 계정을 만들지 않아, 떠도 로그인할 계정이 없다.
REM  그래서 이 창에서만 개발 모드로 덮어쓰고 체험 계정을 함께 만든다.
REM  (.env 파일 자체는 건드리지 않는다 — 운영 설정은 그대로 두는 게 맞다)
REM ══════════════════════════════════════════════════════════════
set BOKGUON_ENV=dev
set BOKGUON_HOST=127.0.0.1
set BOKGUON_PORT=8770
set BOKGUON_SEED_DEMO=1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM ── 1단계: 파이썬이 있는지 ──────────────────────────────────
python --version > nul 2>&1
if errorlevel 1 (
    echo   [멈춤] 파이썬이 설치되어 있지 않습니다.
    echo.
    echo   https://www.python.org/downloads/ 에서 설치한 뒤
    echo   설치 화면에서 "Add python.exe to PATH" 를 반드시 체크하세요.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo   [확인] %%v

REM ── 2단계: 필요한 꾸러미 ────────────────────────────────────
python -c "import flask, waitress, cryptography" > nul 2>&1
if errorlevel 1 (
    echo   [설치] 처음 실행이라 필요한 것들을 내려받습니다. 잠시 기다려 주세요...
    python -m pip install -r requirements.txt --quiet --disable-pip-version-check
    if errorlevel 1 (
        echo.
        echo   [멈춤] 설치에 실패했습니다. 인터넷 연결을 확인하고 다시 실행하세요.
        pause
        exit /b 1
    )
)
echo   [확인] 필요한 꾸러미가 모두 있습니다.

REM ── 3단계: 데이터베이스 준비 (기존 데이터는 보존) ───────────
echo   [준비] 데이터베이스를 확인합니다...
python manage.py init > nul 2>&1
if errorlevel 1 (
    echo.
    echo   [멈춤] 데이터베이스 준비에 실패했습니다.
    echo   아래 명령을 직접 실행해 오류 내용을 확인하세요.
    echo       python manage.py init
    echo.
    pause
    exit /b 1
)

REM ── 4단계: 체험 계정이 실제로 있는지 확인 ───────────────────
REM    여기서 확인하지 않으면, 서버는 떴는데 로그인이 안 되는 상태로
REM    사용자가 원인을 모른 채 헤매게 된다.
python -c "import db;c=db.get_db();n=c.execute(\"SELECT COUNT(*) FROM admins\").fetchone()[0];p=c.execute(\"SELECT COUNT(*) FROM partners WHERE login_id IS NOT NULL AND login_id<>''\").fetchone()[0];c.close();exit(0 if (n and p) else 3)" > nul 2>&1
if errorlevel 3 (
    echo   [보완] 체험 계정이 없어 새로 만듭니다...
    python -c "import db; db.init_db(seed_demo=True, verbose=False)" > nul 2>&1
)

echo.
echo  ------------------------------------------------------------
echo    접속 주소  (브라우저에서 여세요)
echo  ------------------------------------------------------------
echo      관리자 콘솔    http://127.0.0.1:8770/admin
echo      협력사 포털    http://127.0.0.1:8770/partner
echo      보험사 포털    http://127.0.0.1:8770/insurer
echo      서비스 소개    http://127.0.0.1:8770/
echo.
echo  ------------------------------------------------------------
echo    체험 계정
echo  ------------------------------------------------------------
echo      관리자     admin     /  bokguon2026
echo      담당자     staff     /  staff2026
echo      협력사     partner   /  partner2026
echo      보험사     insurer   /  bokguon2026
echo.
echo    * 세 화면을 브라우저 탭 3개로 함께 엽니다.
echo    * 종료하려면 이 창에서 Ctrl+C 를 누르거나 창을 닫으세요.
echo  ============================================================
echo.

REM ── 5단계: 세 포털을 모두 연다 ──────────────────────────────
REM    예전에는 한 곳만 열어서, 나머지 포털이 "안 뜬다"고 오해하기 쉬웠다.
start "" http://127.0.0.1:8770/admin
timeout /t 1 /nobreak > nul
start "" http://127.0.0.1:8770/partner
timeout /t 1 /nobreak > nul
start "" http://127.0.0.1:8770/insurer

python serve_waitress.py

echo.
echo   서버가 종료되었습니다.
pause
