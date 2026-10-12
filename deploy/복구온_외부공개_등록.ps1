<#
  복구온 외부 공개 감시자 등록 (Windows 작업 스케줄러)
  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

  왜 필요한가
    외부접속_상시가동.ps1 은 **서버(waitress)와 Cloudflare 터널을 살려 두는 감시자**다.
    이게 안 돌면 —
      · 서버가 죽어도 아무도 다시 안 띄운다(PC 는 켜져 있는데 서비스만 죽는다)
      · 터널이 끊기면 외부 접속이 통째로 사라진다
      · 터널 주소가 바뀌어도 허용 Host 가 갱신되지 않아 **400 BAD_HOST** 로 막힌다

    ⚠ 2026-08-06 실제 사고 — 감시자가 꺼져 있는 동안 서버를 손으로 재시작했더니
      외부가 전부 400 으로 막혔다. 그런데 **로컬 점검은 전부 통과**해서
      (127.0.0.1 은 늘 허용) 몇 시간 동안 아무도 몰랐다.

  사용법 (관리자 PowerShell)
      .\복구온_외부공개_등록.ps1              등록 (로그온 시 자동 시작)
      .\복구온_외부공개_등록.ps1 -Remove      해제
      .\복구온_외부공개_등록.ps1 -RunNow      등록 후 즉시 시작

  확인
      Get-ScheduledTask -TaskName 복구온_외부공개
      바탕화면 복구온_외부주소.txt  /  logs\supervisor.log
#>
param(
    [switch]$Remove,
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'
$TaskName = '복구온_외부공개'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Here          # bokguon_service
$Script = Join-Path $Here '외부접속_상시가동.ps1'

if (-not (Test-Path $Script)) {
    Write-Error "감시자 스크립트를 찾을 수 없습니다: $Script"
}

if ($Remove) {
    #  ⚠⚠ [라운드126] 예전엔 예약 해제·시작프로그램 삭제만 하고, 이미 떠 있는
    #    감시자(외부접속_상시가동.ps1 의 무한루프)·서버·터널은 그대로 뒀다 —
    #    화면엔 "해제됨"이 뜨는데 외부는 계속 응답했다. 저장소 루트의
    #    복구온_외부공개_중지.bat 이 이미 하는 실제 종료 로직(감시자 프로세스
    #    kill + cloudflared kill)을 여기도 넣는다 — 사고 대응 중에는 이 파일의
    #    -Remove 를 먼저 찾을 사람이 많은데, 그 전용 중지 도구에 대한 언급이
    #    이 파일 어디에도 없었다(grep: "중지" 0회).
    $me = $PID
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessId -ne $me -and $_.CommandLine -like '*상시가동*' } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Output "  감시자 프로세스 종료: PID $($_.ProcessId)"
        }
    Start-Sleep -Milliseconds 500
    $tunnels = @(Get-Process cloudflared -ErrorAction SilentlyContinue)
    if ($tunnels) {
        $tunnels | Stop-Process -Force -ErrorAction SilentlyContinue
        Write-Output "  cloudflared 터널 종료: $($tunnels.Count)개"
    }

    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Output "해제됨: $TaskName"
    } else {
        Write-Output "작업 스케줄러에는 등록돼 있지 않습니다: $TaskName"
    }
    #  시작프로그램 대안으로 걸었을 수 있다 — 그것도 함께 지운다
    $lnk0 = Join-Path ([Environment]::GetFolderPath('Startup')) '복구온_외부공개.lnk'
    if (Test-Path $lnk0) { Remove-Item -LiteralPath $lnk0 -Force; Write-Output "시작프로그램 항목 제거됨" }
    Write-Output "외부 접속이 차단되었습니다(서버는 이 PC 안에서 계속 돕니다)."
    return
}

$PwshExe = (Get-Command powershell -ErrorAction SilentlyContinue).Source
if (-not $PwshExe) { Write-Error 'powershell 을 찾을 수 없습니다.' }

$LogDir = Join-Path $Root 'logs'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

#  ⚠ -ExecutionPolicy Bypass 를 붙인다. 서명 정책 때문에 스크립트가 통째로
#    실행되지 않으면서도 스케줄러는 '완료(0)'로 보고하는 일이 생긴다.
$Action = New-ScheduledTaskAction -Execute $PwshExe `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Script`"" `
    -WorkingDirectory $Root

#  ① 로그온할 때 시작 — 재부팅을 견딘다
$T1 = New-ScheduledTaskTrigger -AtLogOn
#  ② 15분마다 한 번 더 걸어 둔다 — 감시자 자체가 죽어도 되살아난다.
#     (MultipleInstances IgnoreNew 라 이미 돌고 있으면 새로 뜨지 않는다)
$T2 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Minutes 15)

#  ⚠ 감시자는 **끝나지 않는 루프**다. 실행 시간 제한을 걸면 스케줄러가 중간에
#    죽여 버린다 → Zero(무제한). 유휴 상태에서도 멈추지 않게 한다.
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopOnIdleEnd -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew

#  ⚠ **실패를 성공이라고 말하지 않는다.** Register-ScheduledTask 는 권한이 없으면
#    CIM 오류를 내는데, 그게 종료를 막지 못해 아래 "등록됨" 이 그대로 찍혔다
#    (2026-08-06 실제로 그랬다 — Access is denied 인데 화면은 등록됐다고 했다).
#    등록 뒤에 **실제로 조회해** 확인하고, 없으면 대안을 시도한다.
$registered = $false
try {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger @($T1, $T2) `
        -Settings $Settings -Description '복구온 — 운영 서버·Cloudflare 터널 상시 가동 감시' `
        -Force -ErrorAction Stop | Out-Null
} catch {
    Write-Output "  작업 스케줄러 등록 실패: $($_.Exception.Message)"
}
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    $registered = $true
    Write-Output "등록됨: $TaskName (로그온 시 + 15분마다 생존 확인)"
    Write-Output "  실행: $PwshExe -File `"$Script`""
}

#  ── 대안: 시작프로그램 폴더 ────────────────────────────────────────
#  작업 스케줄러 등록에는 관리자 권한이 필요할 수 있다(정책에 따라 다르다).
#  권한이 없어도 **로그온 시 자동 시작**은 시작프로그램 폴더로 된다.
#  '켜지긴 하는데 감시는 안 되는' 상태보다, 방식이 달라도 켜지는 편이 낫다.
$startup = [Environment]::GetFolderPath('Startup')
$lnk = Join-Path $startup '복구온_외부공개.lnk'
if (-not $registered) {
    try {
        $sh = New-Object -ComObject WScript.Shell
        $s2 = $sh.CreateShortcut($lnk)
        $s2.TargetPath = $PwshExe
        $s2.Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Script`""
        $s2.WorkingDirectory = $Root
        $s2.Description = '복구온 외부 공개 감시자'
        $s2.Save()
        if (Test-Path $lnk) {
            Write-Output "시작프로그램에 등록됨(관리자 권한 불필요): $lnk"
            Write-Output "  ⚠ 작업 스케줄러가 아니므로 **로그온해야** 시작됩니다."
            Write-Output "     서버로 쓰는 PC 라면 관리자 PowerShell 로 이 스크립트를 다시 실행해"
            Write-Output "     작업 스케줄러에 등록하시는 편이 낫습니다."
            $registered = $true
        }
    } catch {
        Write-Output "  시작프로그램 등록도 실패: $($_.Exception.Message)"
    }
}
if (-not $registered) {
    Write-Error "등록에 실패했습니다. **관리자 권한 PowerShell** 에서 다시 실행해 주세요."
}

if ($RunNow) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Start-ScheduledTask -TaskName $TaskName
        Start-Sleep -Seconds 12
        $t = Get-ScheduledTaskInfo -TaskName $TaskName
        Write-Output "  마지막 실행: $($t.LastRunTime) · 결과코드: $($t.LastTaskResult)"
    } else {
        #  스케줄러에 없으면 지금 이 자리에서 직접 띄운다
        Start-Process -WindowStyle Hidden -FilePath $PwshExe `
            -ArgumentList "-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass",
                          "-WindowStyle","Hidden","-File","`"$Script`"" -WorkingDirectory $Root
        Start-Sleep -Seconds 12
        Write-Output "  감시자를 지금 직접 실행했습니다(스케줄러 미등록 상태)."
    }
    Write-Output "  ⚠ 결과코드만 믿지 마십시오 — **공개 주소로 직접 접속**해 확인하세요."
    $hf = Join-Path $LogDir 'public_host.txt'
    if (Test-Path $hf) {
        $h = (Get-Content -LiteralPath $hf | Where-Object { $_ -and -not $_.StartsWith('#') } |
              Select-Object -First 1)
        Write-Output "  공개 주소: https://$h"
    }
}
