@echo off
REM ==============================================================
REM  Bokguon daily ops - scheduled task runs this at 03:30 daily.
REM  (c) Olympos Networks / Yu Kyungtak
REM
REM  1) DB backup  2) purge personal data  3) purge access logs
REM  2)3) actually execute the retention periods promised in the
REM  privacy policy. Promising without deleting violates PIPA 21/30.
REM
REM  NOTE 1: comments kept in ASCII - .bat is read in the console
REM          codepage and Korean here breaks on some machines.
REM  NOTE 2: this file MUST be written with a real backslash in
REM          "logs\backup.log". A previous version had a literal
REM          0x08 (backspace) byte there - every redirect failed,
REM          cmd skipped every command, and the task still exited 0.
REM          Result: backups silently stopped while the scheduler
REM          reported success. Never trust exit 0 alone - the
REM          self-check at the bottom verifies real work happened.
REM ==============================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
set BOKGUON_ENV=prod
set PYTHONIOENCODING=utf-8
set LOG=logs\backup.log
set FAILED=0

if not exist "logs" mkdir "logs"

REM Prove the log path is writable BEFORE relying on it.
REM (If the redirect target is malformed, cmd fails here loudly
REM  instead of skipping every later command in silence.)
echo [%date% %time%] --- daily ops start --- >> "%LOG%"
if errorlevel 1 (
  echo FATAL: cannot write "%LOG%" - daily ops aborted 1>&2
  exit /b 9
)

REM (1) DB backup - online backup API, 30-day retention
python manage.py backup >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] !! BACKUP FAILED - check disk space and permissions >> "%LOG%"
  set FAILED=1
)

REM (2) purge personal data - privacy policy article 3 retention
REM     leads/applications 1y, exited partner accounts, victim info after warranty
python manage.py prune-personal >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] !! PRUNE-PERSONAL FAILED >> "%LOG%"
  set FAILED=1
)

REM (3) purge access logs - beyond statutory retention
python manage.py prune-logs >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] !! PRUNE-LOGS FAILED >> "%LOG%"
  set FAILED=1
)

REM (4) self-check - a backup file for TODAY must exist.
REM     Without this the task can "succeed" having done nothing at all.
python deploy\backup_selfcheck.py >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] !! SELF-CHECK FAILED - no fresh backup on disk >> "%LOG%"
  set FAILED=1
)

if "%FAILED%"=="1" (
  echo [%date% %time%] --- daily ops FINISHED WITH ERRORS --- >> "%LOG%"
  exit /b 1
)
echo [%date% %time%] --- daily ops done --- >> "%LOG%"
exit /b 0
