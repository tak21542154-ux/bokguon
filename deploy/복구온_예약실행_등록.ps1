# -*- coding: utf-8 -*-
<#
  복구온 예약 실행 등록 (Windows 작업 스케줄러)
  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

  왜 필요한가
    `manage.py sweep` 은 사람이 화면을 열지 않아도 돌아야 하는 것들을 한다:
      · 입찰 마감 처리          — 안 돌면 공고가 영원히 '입찰중'
      · 출동 기한 점검·재수배    — 안 돌면 '수배됨'에서 멈춘 채 다음 업체로 안 넘어감
      · 완료보고 지연·검수 리마인드
      · 보험사 완료승인 독촉     — 돈이 실제로 멈추는 자리
      · 알림 실발송(팝빌)        — 안 돌면 문자·알림톡이 발송대기함에 쌓이기만 함

    ⚠ 코드에는 다 있는데 **예약이 등록돼 있지 않으면 하나도 실행되지 않는다.**
      실제로 이 PC에 등록이 없었고, 그 상태로는 팝빌 키를 넣어도 문자가 안 나간다.

  사용법 (관리자 PowerShell)
      .\복구온_예약실행_등록.ps1              등록
      .\복구온_예약실행_등록.ps1 -Remove      해제
      .\복구온_예약실행_등록.ps1 -RunNow      등록 후 즉시 1회 실행해 확인
      .\복구온_예약실행_등록.ps1 -Force       이미 같은 스윕 작업이 있어도 강행

  확인
      작업 스케줄러 > 작업 스케줄러 라이브러리 > "복구온_스윕"
      또는  Get-ScheduledTask -TaskName 복구온_스윕
#>
param(
    [switch]$Remove,
    [switch]$RunNow,
    [switch]$Force,
    [int]$IntervalMinutes = 10
)

$ErrorActionPreference = 'Stop'
$TaskName = '복구온_스윕'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Here          # bokguon_service
$Manage = Join-Path $Root 'manage.py'

if (-not (Test-Path $Manage)) {
    Write-Error "manage.py 를 찾을 수 없습니다: $Manage"
}

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Output "해제됨: $TaskName"
    } else {
        Write-Output "등록돼 있지 않습니다: $TaskName"
    }
    return
}

# python.exe 경로 — 스케줄러는 PATH 를 안 물려받는 경우가 있어 절대경로로 박는다
$Py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Py) { $Py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $Py) { Write-Error 'python 을 찾을 수 없습니다. Python 설치 후 다시 실행해 주세요.' }

#  ⚠⚠ [라운드292] python.exe 로 예약작업을 등록하면 5분(여기선 기본 10분)마다
#    콘솔 창이 떴다 사라진다 — 실제 이 PC의 '복구온_경매마감'(이 스크립트와는
#    다른 이름, 같은 목적의 작업)이 이미 pythonw.exe 로 손으로 바로잡혀
#    있음을 schtasks 로 직접 확인했다. 같은 python.exe 를 그대로 쓰는 이
#    스크립트도 실제로 (재)등록에 쓰이면 같은 깜빡임이 재발한다 — 같은
#    디렉터리에 있는 pythonw.exe 로 바꾼다(없으면 python.exe 로 폴백).
$PyW = Join-Path (Split-Path $Py -Parent) 'pythonw.exe'
if (-not (Test-Path $PyW)) { $PyW = $Py }

$LogDir = Join-Path $Root 'logs'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

#  ⚠ .bat 을 거치지 않고 python 을 직접 부른다.
#    배치 파일에서 한글 경로·역슬래시 이스케이프가 깨져 명령이 통째로 건너뛰이면서도
#    종료코드는 0 으로 보고되는 사고가 있었다(스케줄러는 초록불인데 아무 일도 안 함).
$Action = New-ScheduledTaskAction -Execute $PyW `
    -Argument "`"$Manage`" sweep" -WorkingDirectory $Root

#  10분마다 — 입찰 마감·출동 기한이 분 단위로 의미가 있다.
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)

$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

#  ★ **이미 같은 일을 하는 작업이 있으면 하나 더 만들지 않는다.**
#    이 PC 에는 `복구온_경매마감` 이라는 다른 이름으로 같은 `manage.py sweep` 이
#    5분마다 돌고 있었다. 모르고 또 걸면 스윕이 두 벌 돌아 알림이 겹쳐 나간다.
#  ⚠⚠ [라운드126] 이 검사는 Arguments 문자열만 봐서, manage.py::cmd_install_scheduler
#    가 등록하는 방식(인자 없이 .bat 하나만 가리키고 "manage.py sweep" 은 그
#    .bat **내부**에만 있다 — 실제로 이 PC의 '복구온_경매마감'이 이 방식이다)을
#    영원히 못 잡는 사각지대였다(실행 확인: 같은 패턴의 임시 작업을 만들어
#    이 검사를 그대로 돌려보니 탐지되지 않았다). 실행파일이 .bat/.cmd 면
#    그 내용도 함께 본다.
function Test-SweepAction($action) {
    if ("$($action.Arguments)" -like '*manage.py* sweep*' -or
        "$($action.Arguments)" -like '*manage.py" sweep*') { return $true }
    $exe = "$($action.Execute)"
    if ($exe -match '\.(bat|cmd)$' -and (Test-Path $exe)) {
        try {
            if ((Get-Content -Raw -Path $exe -ErrorAction Stop) -match 'manage\.py"?\s+sweep') { return $true }
        } catch {}
    }
    return $false
}
$dup = @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
    $_.TaskName -ne $TaskName -and ($_.Actions | Where-Object { Test-SweepAction $_ })
})
if ($dup) {
    Write-Output "  ⚠ 이미 같은 스윕을 도는 작업이 있습니다: $($dup.TaskName -join ', ')"
    Write-Output "     둘 다 두면 알림이 두 번 나갑니다. 하나만 남기세요."
    #  ⚠⚠ [라운드126] 예전엔 "여기서 중단하고..."라고 말만 하고 스크립트 자신은
    #    절대 멈추지 않았다(실측: 지금 이 PC에 이 상태가 실재해, 이 스크립트를
    #    그대로 실행하면 실제로 중복 등록이 됐다). 말한 대로 실제로 멈춘다 —
    #    정말 둘 다 두려는 의도면 -Force 로 명시해야 한다.
    if (-not $Force) {
        Write-Error "중복 등록을 막았습니다. 옛 작업($($dup.TaskName -join ', '))을 먼저 해제하거나, 정말 둘 다 두려면 -Force 를 붙여 다시 실행하세요."
    }
    Write-Output "     -Force 지정됨 — 중복에도 불구하고 계속 진행합니다."
}

#  ⚠ **실패를 성공이라고 말하지 않는다.** Register-ScheduledTask 는 권한이 없으면
#    CIM 오류를 내는데 그게 종료를 막지 못해 아래 "등록됨" 이 그대로 찍혔다
#    (형제 스크립트 복구온_외부공개_등록.ps1 에서 2026-08-06 실제로 그랬다).
#    등록 뒤에 **실제로 조회해** 확인한다.
$registered = $false
try {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
        -Settings $Settings -Description '복구온 — 입찰 마감·출동 기한·독촉·알림 실발송 점검' `
        -Force -ErrorAction Stop | Out-Null
} catch {
    Write-Output "  작업 스케줄러 등록 실패: $($_.Exception.Message)"
}
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    $registered = $true
    Write-Output "등록됨: $TaskName ($IntervalMinutes 분마다)"
    Write-Output "  실행: $PyW `"$Manage`" sweep"
} else {
    Write-Error "등록에 실패했습니다. **관리자 권한 PowerShell** 에서 다시 실행해 주세요.
  (스윕이 안 돌면 입찰 마감·출동 기한·독촉·문자 실발송이 전부 멈춥니다.
   임시로는  python manage.py sweep  을 사람이 주기적으로 돌려야 합니다.)"
}

if ($RunNow -and $registered) {
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 8
    $t = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Output "  마지막 실행: $($t.LastRunTime) · 결과코드: $($t.LastTaskResult) (0이면 정상)"
    Write-Output "  ⚠ 결과코드만 믿지 말고 콘솔 대시보드의 '마감 점검' 배지가 초록인지 확인하세요."
}
