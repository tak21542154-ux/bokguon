@echo off
chcp 65001 >nul
title 복구온 - 외부 공개 중지
echo ============================================================
echo   복구온 - 외부 공개 중지
echo   (주)올림포스네트웍스 전략사업실 유경탁 파트장
echo ============================================================
echo.
echo  감시자와 터널을 내립니다. 서버는 이 PC 안에서 계속 돕니다
echo  (사무실에서 http://127.0.0.1:8771/admin 으로는 계속 쓸 수 있습니다).
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$me = $PID; Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | Where-Object { $_.ProcessId -ne $me -and $_.CommandLine -like '*상시가동*' } | ForEach-Object { taskkill /PID $_.ProcessId /F | Out-Null }; Start-Sleep 1; taskkill /IM cloudflared.exe /F 2>$null | Out-Null; $t = Get-ScheduledTask -TaskName '복구온_외부공개' -ErrorAction SilentlyContinue; if ($t) { Disable-ScheduledTask -TaskName '복구온_외부공개' | Out-Null; Write-Host '  예약 작업 복구온_외부공개 사용 안 함으로 전환' }; $sp = [Environment]::GetFolderPath('Startup'); foreach ($f in @('복구온_외부공개.lnk','복구온_외부접속_자동시작.bat')) { $p = Join-Path $sp $f; if (Test-Path $p) { Rename-Item -LiteralPath $p -NewName ($f + '.off') -Force -ErrorAction SilentlyContinue; Write-Host ('  시작프로그램 ' + $f + ' 를 .off 로 미뤄 둠') } }; Start-Sleep 1; Write-Host ('  남은 터널: ' + @(Get-Process cloudflared -ErrorAction SilentlyContinue).Count + '개')"

echo.
echo  외부 접속이 차단되었습니다.
echo.
echo  자동 재시작도 함께 꺼 두었습니다(예약 작업 + 시작프로그램).
echo  다시 열려면:  deploy\복구온_외부공개_등록.ps1 -RunNow
pause
