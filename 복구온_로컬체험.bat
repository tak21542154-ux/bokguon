@echo off
chcp 65001 > nul
title 복구온 — 로컬 체험 서버
cd /d "%~dp0"

echo ============================================================
echo   복구온 (BOKGUON) — 로컬 체험 서버
echo   (주)올림포스네트웍스 전략사업실 유경탁 파트장
echo ============================================================
echo.

REM ── .env 를 고치지 않고 이 창에서만 개발 모드로 돌린다 ──
REM    .env 는 운영(prod)으로 맞춰져 있고 그 상태로 두는 게 맞다.
REM    운영 모드는 세션 쿠키에 Secure 를 붙이므로, 평문 http 로 접속하면
REM    브라우저가 쿠키를 되돌려주지 않아 로그인이 유지되지 않는다(결함이 아니다).
REM    그래서 체험용으로는 이 창에서만 dev 로 덮어쓴다.
set BOKGUON_ENV=dev
set BOKGUON_HOST=127.0.0.1
set BOKGUON_PORT=8770
set BOKGUON_THREADS=4
set PYTHONUTF8=1
REM ── 체험은 **운영 DB 를 건드리지 않는다** ────────────────────────
REM    이 창은 데모 시드를 켠다(아래). 운영 DB 를 그대로 쓰면
REM    출시 뒤 연습 한 번에 실사건 옆으로 데모 사건이 끼어든다.
REM    지워도 운영에 영향이 없는 체험 전용 파일로 갈아끼운다.
set BOKGUON_DB_PATH=%~dp0bokguon_체험.db
REM DB 를 처음 만들 때 체험 계정(admin/staff/partner/insurer)이 함께 생성되도록.
REM .env 의 BOKGUON_SEED_DEMO=0 을 이 창에서만 덮어쓴다(없으면 빈 DB 로 떠서 로그인 불가).
set BOKGUON_SEED_DEMO=1

echo   접속 주소
echo     관리자 콘솔   http://127.0.0.1:8770/admin
echo     협력사 포털   http://127.0.0.1:8770/partner
echo     보험사 포털   http://127.0.0.1:8770/insurer
echo     서비스 소개   http://127.0.0.1:8770/
echo.
echo   * 이 창은 체험 전용 DB(bokguon_체험.db)를 씁니다 — 운영 자료와 별개입니다.
echo.
echo   체험 계정 (체험 DB 전용 · 운영 계정과 무관)
echo     관리자   admin    / bokguon2026     ^(최고관리자^)
echo     담당자   staff    / staff2026
echo     협력사   partner  / partner2026     ^(시행사 - 입찰 가능^)
echo     보험사   insurer  / bokguon2026
echo.
echo   * 종료하려면 이 창에서 Ctrl+C 를 누르세요.
echo ============================================================
echo.

start "" http://127.0.0.1:8770/admin
python serve_waitress.py

echo.
echo   서버가 종료되었습니다.
pause
