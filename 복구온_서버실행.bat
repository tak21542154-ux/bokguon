@echo off
chcp 65001 > nul
title 복구온 서비스 — 개발 서버
cd /d "%~dp0"

echo ============================================
echo   복구온 (BOKGUON) — 개발용 서버
echo   (주)올림포스네트웍스 전략사업실 유경탁 파트장
echo ============================================
echo.

REM ── 운영 설정이 잡혀 있으면 개발서버로 띄우지 않는다 ──
REM    .env 에 BOKGUON_ENV=prod 가 있으면 app.py 가 스스로 기동을 거부하지만,
REM    여기서 먼저 안내해 혼란을 줄인다.
if exist ".env" (
    findstr /B /C:"BOKGUON_ENV=prod" .env > nul
    if not errorlevel 1 (
        echo   [중지] .env 가 운영 모드^(prod^)로 설정되어 있습니다.
        echo.
        echo   개발 서버로는 기동할 수 없습니다. 운영은 아래 명령을 쓰세요.
        echo       python serve_waitress.py
        echo.
        echo   그리고 운영에서는 IIS/nginx 로 HTTPS 를 종단해야
        echo   로그인 세션^(Secure 쿠키^)이 유지됩니다.
        echo.
        pause
        exit /b 1
    )
)

REM ── 의존성 확인 ──
python -c "import flask" 2>nul
if errorlevel 1 (
    echo [설치] 의존성을 설치합니다...
    python -m pip install -r requirements.txt --quiet
)

REM ── DB 생성·스키마 갱신 (기존 데이터는 보존된다) ──
echo [준비] 데이터베이스 스키마를 확인합니다...
set PYTHONUTF8=1
python manage.py init

echo.
echo  서버 시작 — 아래 주소를 브라우저에서 여세요
echo.
echo   랜딩페이지        http://127.0.0.1:8771/
echo   보험사 문의폼     http://127.0.0.1:8771/apply/insurer
echo   업체 입점신청     http://127.0.0.1:8771/apply/partner
echo   개인정보처리방침  http://127.0.0.1:8771/legal/privacy
echo   어드민 콘솔       http://127.0.0.1:8771/admin
echo   협력사 포털       http://127.0.0.1:8771/partner
echo   보험사 포털       http://127.0.0.1:8771/insurer
echo.
echo  * 개발용 데모 계정은 db.py 시드 참조 (운영 모드에서는 생성되지 않습니다)
echo  * 종료하려면 이 창에서 Ctrl+C 를 누르세요.
echo ============================================
echo.

start "" http://127.0.0.1:8771/
python app.py

pause
