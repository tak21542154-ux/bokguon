# ══════════════════════════════════════════════════════════════
#  복구온 서비스 — Windows 서버 설치 스크립트
#  ㈜올림포스네트웍스 기획팀 유경탁
#
#  사내 Windows 서버에 배포할 때 사용한다.
#  리눅스 배포는 deploy/bootstrap.sh 를 쓴다.
#
#  사용법 (관리자 권한 PowerShell):
#     cd C:\bokguon
#     .\deploy\windows_setup.ps1 -Domain bokguon.olymposnetworks.com
#
#  ⚠ Windows 에서도 앱을 인터넷에 직접 노출하지 않는다.
#     반드시 IIS(ARR) 또는 nginx 를 앞에 두고 TLS 를 종단시킨 뒤,
#     앱은 127.0.0.1 에만 바인딩한다. 그래야
#       · HTTPS 강제, 레이트 리밋, 관리자 IP 제한이 실제로 걸리고
#       · 운영 모드의 Secure 쿠키가 정상 동작한다.
# ══════════════════════════════════════════════════════════════
param(
    [string]$AppDir  = (Split-Path -Parent $PSScriptRoot),
    [string]$Domain  = "",
    [int]   $Port    = 8771,
    [string]$NssmExe = "nssm"
)

$ErrorActionPreference = "Stop"
function Ok($m)   { Write-Host "  [OK] $m"   -ForegroundColor Green }
function Warn($m) { Write-Host "  [!!] $m"   -ForegroundColor Yellow }
function Step($m) { Write-Host "`n$m" -ForegroundColor Cyan; Write-Host ("-" * 62) }

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "관리자 권한 PowerShell 에서 실행하세요."
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor White
Write-Host "  복구온 서비스 설치 (Windows)" -ForegroundColor White
Write-Host "  ㈜올림포스네트웍스 기획팀 유경탁"
Write-Host "  설치 경로 : $AppDir"
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor White

# ── 1. 파이썬 확인 ────────────────────────────────────────────
Step "1. 파이썬 · 가상환경"
$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) { throw "python 을 찾을 수 없습니다. Python 3.11 이상을 설치하세요." }
Ok ("파이썬 " + (& python -c "import sys;print('.'.join(map(str,sys.version_info[:3])))"))

#  ⚠⚠ [라운드125] 아래 네이티브 exe 호출들도 238행 주석이 설명하는 것과 같은
#    구멍이었다 — $ErrorActionPreference='Stop' 은 네이티브 exe 의 0 아닌
#    종료코드를 승격시키지 않는다. 저자가 238~249·253~256행에서 이미 이해하고
#    고쳐 둔 바로 그 패턴을, 같은 파일 안의 나머지 7곳(venv 생성·pip 설치 2회·
#    icacls 2회·manage.py init·create-admin)에는 일관되게 적용하지 못했었다
#    (실행 재현: 존재하지 않는 경로에 icacls 를 호출해도 바로 다음 줄이
#    무조건 [OK] 를 찍는 것을 확인했다).
$venv = Join-Path $AppDir "venv"
if (-not (Test-Path $venv)) {
    & python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "가상환경 생성 실패(종료코드 $LASTEXITCODE) — python -m venv 를 직접 실행해 원인을 확인하세요." }
    Ok "가상환경 생성"
} else { Ok "가상환경 이미 존재" }

$vpy  = Join-Path $venv "Scripts\python.exe"
$vpip = Join-Path $venv "Scripts\pip.exe"
& $vpip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) { Warn "pip 자체 업그레이드 실패(종료코드 $LASTEXITCODE) — 계속 진행합니다." }
& $vpip install --quiet -r (Join-Path $AppDir "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "의존성 설치 실패(종료코드 $LASTEXITCODE) — requirements.txt 를 직접 설치해 원인(빌드 도구 누락 등)을 확인하세요." }
Ok "의존성 설치 완료"

# ── 2. 환경설정 ───────────────────────────────────────────────
Step "2. 환경설정 (.env)"
$envFile = Join-Path $AppDir ".env"
if (Test-Path $envFile) {
    Ok ".env 이미 존재 — 그대로 둡니다 (덮어쓰면 계좌번호 복호화 불가)"
} else {
    $secret = & $vpy -c "import secrets;print(secrets.token_hex(32))"
    $enck   = & $vpy -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
    $idxk   = & $vpy -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
    $backup = Join-Path $AppDir "backups"
@"
# 복구온 운영 환경설정 — windows_setup.ps1 자동 생성 $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
# BOKGUON_ENC_KEY 를 잃어버리면 저장된 계좌번호를 영구히 복호화할 수 없습니다.
BOKGUON_ENV=prod
BOKGUON_SECRET_KEY=$secret
BOKGUON_ENC_KEY=$enck
BOKGUON_INDEX_KEY=$idxk
BOKGUON_HOST=127.0.0.1
BOKGUON_PORT=$Port
BOKGUON_THREADS=8
BOKGUON_BEHIND_PROXY=1
BOKGUON_FORWARDED_ALLOW=127.0.0.1
BOKGUON_SESSION_MIN=30
BOKGUON_MAX_LOGIN_FAILS=5
BOKGUON_LOCKOUT_MIN=10
BOKGUON_LOG_RETENTION_DAYS=730
BOKGUON_ADMIN_IP_ALLOW=
BOKGUON_SEED_DEMO=0
BOKGUON_SQLITE_BUSY_MS=8000
BOKGUON_BACKUP_DIR=$backup
BOKGUON_BACKUP_KEEP_DAYS=30
"@ | Set-Content -Path $envFile -Encoding utf8
    Ok ".env 생성"
    Warn "아래 암호화 키를 지금 안전한 곳에 백업하세요:"
    Write-Host "     BOKGUON_ENC_KEY=$enck" -ForegroundColor Yellow
}

# ── 3. 파일 권한 (ACL) ────────────────────────────────────────
Step "3. 파일 권한"
#  실패해도 서비스 자체는 계속 뜰 수 있어 여기서 throw 하지는 않는다 — 대신
#  8단계의 최종 판정(SetupWarnFail)에 반영해 "설치 완료" 초록이 이 실패를
#  덮지 못하게 한다(238행과 같은 원리를 조기 종료 대신 최종 게이트로 적용).
$SetupWarnFail = $false
# .env 와 DB 는 관리자·SYSTEM 만 읽을 수 있어야 한다.
# 상속을 끊지 않으면 Users 그룹이 그대로 읽을 수 있다.
foreach ($f in @($envFile, (Join-Path $AppDir "bokguon.db"))) {
    if (Test-Path $f) {
        & icacls $f /inheritance:r /grant:r "Administrators:(F)" "SYSTEM:(F)" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Warn ("권한 제한 실패(종료코드 " + $LASTEXITCODE + ") — " + (Split-Path -Leaf $f) + " 이 기본 권한(Users 읽기 가능)으로 남아 있을 수 있습니다.")
            $SetupWarnFail = $true
        } else {
            Ok ("권한 제한 — " + (Split-Path -Leaf $f))
        }
    }
}
$backupDir = Join-Path $AppDir "backups"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
& icacls $backupDir /inheritance:r /grant:r "Administrators:(OI)(CI)F" "SYSTEM:(OI)(CI)F" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Warn ("백업 디렉터리 권한 제한 실패(종료코드 " + $LASTEXITCODE + ") — 시공 사진·개인정보가 기본 권한으로 노출될 수 있습니다.")
    $SetupWarnFail = $true
} else {
    Ok "백업 디렉터리 권한 제한"
}

# ── 4. 데이터베이스 ───────────────────────────────────────────
Step "4. 데이터베이스"
Push-Location $AppDir
$fresh = -not (Test-Path (Join-Path $AppDir "bokguon.db"))
& $vpy (Join-Path $AppDir "manage.py") init
if ($LASTEXITCODE -ne 0) { throw "DB 스키마 반영 실패(종료코드 $LASTEXITCODE) — manage.py init 을 직접 실행해 원인을 확인하세요." }
Ok "스키마 반영 · 마이그레이션 완료"
if ($fresh) {
    & $vpy (Join-Path $AppDir "manage.py") create-admin admin --name 관리자 --role 최고관리자
    if ($LASTEXITCODE -ne 0) {
        Warn "관리자 계정 생성 실패(종료코드 $LASTEXITCODE) — 로그인할 계정이 없습니다."
        Warn "  나중에 직접 실행하세요:  $vpy manage.py create-admin admin --name 관리자 --role 최고관리자"
        $SetupWarnFail = $true
    } else {
        Warn "위 임시 비밀번호를 안전하게 전달하세요. 최초 로그인 시 변경이 강제됩니다."
    }
}
Pop-Location

# ── 5. 서비스 등록 (NSSM) ─────────────────────────────────────
Step "5. Windows 서비스 등록"
$nssm = Get-Command $NssmExe -ErrorAction SilentlyContinue
if (-not $nssm) {
    Warn "NSSM 이 없습니다. https://nssm.cc 에서 받아 PATH 에 두거나 -NssmExe 로 경로를 지정하세요."
    Warn "수동 실행:  $vpy $AppDir\serve_waitress.py"
} else {
    $svc = "bokguon"
    if (Get-Service $svc -ErrorAction SilentlyContinue) {
        & $NssmExe stop $svc | Out-Null
        Ok "기존 서비스 중지"
    } else {
        & $NssmExe install $svc $vpy (Join-Path $AppDir "serve_waitress.py") | Out-Null
        Ok "서비스 생성"
    }
    & $NssmExe set $svc AppDirectory      $AppDir            | Out-Null
    & $NssmExe set $svc DisplayName        "복구온 서비스"    | Out-Null
    & $NssmExe set $svc Description        "기타피해물 복구 역경매 플랫폼 (올림포스네트웍스)" | Out-Null
    & $NssmExe set $svc Start              SERVICE_AUTO_START | Out-Null
    & $NssmExe set $svc AppEnvironmentExtra "PYTHONUTF8=1" "PYTHONIOENCODING=utf-8" | Out-Null

    # 로그 — 회전 설정이 없으면 파일이 무한히 커진다
    $logDir = Join-Path $AppDir "logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    & $NssmExe set $svc AppStdout        (Join-Path $logDir "service_out.log") | Out-Null
    & $NssmExe set $svc AppStderr        (Join-Path $logDir "service_err.log") | Out-Null
    & $NssmExe set $svc AppRotateFiles   1        | Out-Null
    & $NssmExe set $svc AppRotateOnline  1        | Out-Null
    & $NssmExe set $svc AppRotateBytes   10485760 | Out-Null   # 10MB 마다 회전
    Ok "로그 회전 설정 (10MB)"

    # 비정상 종료 시 자동 재시작
    & $NssmExe set $svc AppExit Default Restart | Out-Null
    & $NssmExe set $svc AppRestartDelay 5000    | Out-Null

    & $NssmExe start $svc | Out-Null
    Start-Sleep -Seconds 4
    $st = (Get-Service $svc).Status
    if ($st -eq "Running") { Ok "서비스 기동됨 (bokguon)" }
    else { Warn "서비스 상태: $st — $logDir\service_err.log 를 확인하세요." }
}

# ── 6. 방화벽 ─────────────────────────────────────────────────
Step "6. 방화벽"
# 앱 포트는 127.0.0.1 바인딩이라 외부에서 못 들어오지만, 명시적으로도 차단해 둔다.
if (-not (Get-NetFirewallRule -DisplayName "복구온 앱포트 차단" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName "복구온 앱포트 차단" -Direction Inbound -LocalPort $Port `
        -Protocol TCP -Action Block -RemoteAddress Any | Out-Null
    Ok "앱 포트 $Port 외부 차단"
} else { Ok "방화벽 규칙 이미 존재" }

# ── 7. 정기 작업 ──────────────────────────────────────────────
Step "7. 정기 작업 (작업 스케줄러)"

#  ⚠⚠ [라운드296] python.exe 로 등록한 예약작업은 실행마다 콘솔 창이 떴다 사라진다 —
#    같은 결함을 복구온_예약실행_등록.ps1:59-66 이 이미 겪었다(그 스크립트의 $PyW
#    폴백과 동일 처리). 실제 이 PC의 '복구온_경매마감'이 pythonw.exe 로 등록돼
#    있음을 schtasks 로 직접 재확인했다. 아래 세 작업(백업·접속기록정리·개인정보
#    파기)의 -Execute 는 $vpy 대신 이 $vpyw 를 쓴다. NSSM 서비스(168행)는 세션0
#    이라 콘솔이 없어 대상이 아니고, 그 위 대화형 설치 단계(pip·manage.py init 등)는
#    사람이 출력을 봐야 하므로 $vpy 를 그대로 둔다.
$vpyw = Join-Path $venv "Scripts\pythonw.exe"
if (-not (Test-Path $vpyw)) { $vpyw = $vpy }

#  ⚠⚠ [라운드357] 이 스크립트가 등록하는 정기작업 목록에 **manage.py sweep 이
#    아예 빠져 있었다** — bootstrap.sh(리눅스, 276행)는 `*/5 * * * * ...
#    manage.py sweep` 을 직접 등록하는데, 그 줄 바로 옆 주석(275행)이 "윈도
#    배포는 복구온_예약실행_등록.ps1 이 같은 일을 한다"고 적어 뒀지만 정작 이
#    파일(윈도의 '메인' 설치 스크립트)은 그 스크립트를 부르지 않는다 — DEPLOY.md
#    순서대로 이 파일 하나만 실행하면 그 별도 스크립트를 부르는 단계 자체가
#    없다. sweep 이 없으면 입찰 자동마감·출동 기한만료·완료보고 독촉·문자/
#    알림톡 실발송이 전부 멈춘다(그 스크립트 자신의 6~15행이 이미 이 사고를
#    한 번 실제로 겪었다고 기록해 뒀다). 등록 로직을 여기 새로 베끼지 않고
#    —그 스크립트가 이미 중복작업 감지(.bat 내부까지 들여다봄, 126라운드)·
#    등록 후 실제 조회 확인(외부공개_등록.ps1 이 겪은 "실패해도 성공이라고
#    말한" 사고 재발 방지, 이 스크립트 자신의 121~124행)까지 다 갖춘 단일
#    관문이므로— 그대로 호출한다. 실패해도(이미 '복구온_경매마감'이 도는
#    이 PC에 재실행하면 중복감지로 정확히 이렇게 됨) 나머지 설치 단계를
#    막지 않도록 경고로만 낮춘다.
Step "7-0. 마감·독촉 스윕 예약 (별도 스크립트 위임)"
$sweepScript = Join-Path $PSScriptRoot "복구온_예약실행_등록.ps1"
if (Test-Path $sweepScript) {
    try {
        & $sweepScript
    } catch {
        Warn "스윕 예약 등록을 건너뜁니다: $($_.Exception.Message)"
        Warn "필요하면 나중에 수동 실행: $sweepScript"
    }
} else {
    Warn "$sweepScript 를 찾을 수 없습니다 — manage.py sweep 예약을 수동으로 등록하세요(5~10분마다)."
}

#  ⚠⚠ [라운드559] 아래 4개 작업(DB백업·사진백업·접속기록정리·개인정보파기) 등록은
#    전부 `Register-ScheduledTask ... | Out-Null` 뒤 조건 없이 Ok 를 찍기만 했다.
#    이 파일 맨 위(25행) $ErrorActionPreference='Stop' 이 있어도 이 cmdlet이 내는
#    CIM 오류는 승격되지 않는다 — 바로 이 결함 클래스를 형제 스크립트
#    복구온_예약실행_등록.ps1(121~141행)과 복구온_외부공개_등록.ps1(100~116행)이
#    2026-08-06 "Access is denied 인데 화면은 등록됐다고 했다"는 실제 사고로 이미
#    겪고 고쳤다(-ErrorAction Stop + try/catch + 등록 뒤 실제 재조회). 그런데 그
#    수정이 그 두 스크립트에만 머물고, 이 파일이 직접 등록하는 아래 4곳에는 한
#    번도 옮겨오지 않았다 — 권한 문제가 있는 PC에서 이 스크립트를 돌리면 DB
#    백업도, 처리방침이 공개 약속한 개인정보 파기(299~303행)도 전혀 안 도는데
#    화면은 전부 초록 [OK]만 보여줄 수 있었다. 형제 두 스크립트와 같은 처리를
#    함수 하나로 모아 4곳이 전부 쓰게 한다(중복 대신 공유 지점 하나).
function Register-BokguonTask($TaskName, $Action, $Trigger, $Description, $OkMessage) {
    try {
        Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
            -RunLevel Highest -Description $Description -ErrorAction Stop | Out-Null
    } catch {
        Warn "$TaskName 등록 실패: $($_.Exception.Message)"
        return
    }
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Ok $OkMessage
    } else {
        Warn "$TaskName 등록 명령은 오류 없이 끝났지만 실제로 조회되지 않습니다 — 작업 스케줄러에서 직접 확인하세요."
    }
}

#  ⚠ [라운드296] 이 PC의 실제 예약작업은 아래 3개가 아니라 '복구온_일일백업'
#    (deploy\일일백업.bat 하나 — 로그+자가점검 포함) 하나뿐임을 schtasks 로
#    확인했다. bootstrap.sh(리눅스)도 이 스크립트처럼 3개로 나눠 등록하므로
#    (배포 스크립트 두 플랫폼 간 의도된 동일 설계) 구조는 유지한다 — 다만
#    일일백업.bat 이 이미 도는 기존 PC에서 이 스크립트를 재실행하면 이름이
#    달라 중복 감지가 안 돼 아래 3개가 추가로 등록된다(새 머신 최초 설치가
#    이 스크립트의 용도이므로 그 시나리오에서는 해당하지 않는다).
$taskBackup = "복구온_DB백업"
if (-not (Get-ScheduledTask -TaskName $taskBackup -ErrorAction SilentlyContinue)) {
    $a = New-ScheduledTaskAction -Execute $vpyw -Argument "manage.py backup" -WorkingDirectory $AppDir
    $t = New-ScheduledTaskTrigger -Daily -At 3am
    Register-BokguonTask $taskBackup $a $t "복구온 데이터베이스 일일 백업 (무결성 검증 포함)" "일일 백업 등록 (매일 03:00)"
} else { Ok "백업 작업 이미 등록됨" }

# 시공 사진 백업 — manage.py backup 은 DB만 뜨므로 별도로
$taskPhoto = "복구온_사진백업"
if (-not (Get-ScheduledTask -TaskName $taskPhoto -ErrorAction SilentlyContinue)) {
    $uploadsBk = Join-Path $AppDir "backups\uploads"
    # ⚠ /MIR(= /E /PURGE) 를 쓰면 원본에서 지운 사진이 다음 백업 때 백업본에서도 사라진다.
    #    사진 삭제를 잘못했을 때 되살릴 방법이 없어진다(백업의 존재 이유가 없어진다).
    #    robocopy 에는 rsync --backup-dir 같은 '삭제분 보관' 기능이 없으므로,
    #    아예 지우지 않는 /E 로 간다. 백업본은 원본의 상위집합이 되어 계속 쌓인다.
    #    (용량이 문제가 되면 오래된 사건 폴더를 사람이 판단해 정리한다)
    #  ⚠ **robocopy 는 정상 복사에도 종료코드 1 을 준다**(8 이상만 진짜 실패).
    #    그대로 등록하면 작업 스케줄러의 '마지막 실행 결과'가 늘 0x1 로 찍혀
    #    성공인지 실패인지 아무도 구분하지 못한다. /LOG: 도 없어 스케줄러
    #    실행에서는 출력이 어디에도 남지 않는다 — DB 백업에는 자가점검이 있는데
    #    사진(시공 증빙·분쟁 자료)에는 결과를 확인할 장치가 하나도 없었다.
    #    → cmd 로 감싸 8 미만은 0 으로 정규화하고, 로그를 남긴다.
    $phLog = Join-Path $AppDir "logs\photo_backup.log"
    $phCmd = ('robocopy "' + (Join-Path $AppDir 'uploads') + '" "' + $uploadsBk +
              '" /E /NFL /NDL /R:2 /W:5 /LOG+:"' + $phLog + '"' +
              ' & if %ERRORLEVEL% GEQ 8 (exit /b %ERRORLEVEL%) else (exit /b 0)')
    $a = New-ScheduledTaskAction -Execute "cmd.exe" -Argument ('/c ' + $phCmd)
    $t = New-ScheduledTaskTrigger -Daily -At 3:20am
    Register-BokguonTask $taskPhoto $a $t "복구온 시공 사진 백업 (DB 백업과 별도)" "사진 백업 등록 (매일 03:20)"
} else { Ok "사진 백업 작업 이미 등록됨" }

$taskPrune = "복구온_접속기록정리"
if (-not (Get-ScheduledTask -TaskName $taskPrune -ErrorAction SilentlyContinue)) {
    $a = New-ScheduledTaskAction -Execute $vpyw -Argument "manage.py prune-logs" -WorkingDirectory $AppDir
    $t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 4am
    Register-BokguonTask $taskPrune $a $t "보관기간 지난 접속기록 파기 (개인정보 보호법 §21)" "접속기록 파기 등록 (매주 일 04:00)"
} else { Ok "접속기록 정리 작업 이미 등록됨" }

#  ★ 개인정보 파기 — 처리방침에 **우리가 공개적으로 약속한 것**이다("정산 계좌 정보는
#    거래 종료 후 지체 없이", "피해자 성명·연락처는 하자담보책임기간(24개월) 만료 후"
#    파기). bootstrap.sh(리눅스)는 이미 이 예약을 등록하는데, 여기(윈도)엔 없었다 —
#    실행하는 예약이 없으면 방침 위반이 그대로 사실이 된다. 지우는 대상·기준은
#    manage.py prune-personal 이 정한다.
$taskPrunePersonal = "복구온_개인정보파기"
if (-not (Get-ScheduledTask -TaskName $taskPrunePersonal -ErrorAction SilentlyContinue)) {
    $a = New-ScheduledTaskAction -Execute $vpyw -Argument "manage.py prune-personal" -WorkingDirectory $AppDir
    $t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 4:30am
    Register-BokguonTask $taskPrunePersonal $a $t "보관기간 지난 개인정보 파기 (개인정보 보호법 §21·§30, 처리방침 제3조)" "개인정보 파기 등록 (매주 일 04:30)"
} else { Ok "개인정보 파기 작업 이미 등록됨" }

# ── 8. 점검 ───────────────────────────────────────────────────
Step "8. 배포 전 점검"
#  ⚠⚠ **종료코드를 반드시 받는다.** 예전에는 `& $vpy manage.py check` 를 호출만 하고
#    결과를 버렸다. PowerShell 5.1 의 $ErrorActionPreference='Stop' 은 네이티브 exe 의
#    0 아닌 종료코드를 오류로 승격시키지 않으므로, check 가 '배포 불가'(데모 데이터
#    잔존·법정 고지 미기재 등)를 내고 exit 1 을 돌려줘도 스크립트는 그대로 초록
#    '설치 완료' 와 서비스 URL 을 찍고 exit 0 으로 끝났다. 설치 담당자는 붉은 글씨
#    위에 덮인 초록 결론만 보고 링크를 배포하게 된다.
#    리눅스판(bootstrap.sh)은 같은 결함을 이미 고쳐 뒀다 — 여기만 빠져 있었고,
#    **실운영은 이 윈도 경로다.**
Push-Location $AppDir
& $vpy manage.py check
$CheckRc = $LASTEXITCODE
if ($CheckRc -ne 0) { Warn "점검이 배포 불가 항목을 냈습니다(종료코드 $CheckRc)." }

#  두 번째 관문 — 스모크 테스트. 있으면 돌리고, 없으면 없다고 말한다.
#  ⚠⚠ [라운드125] smoke_test.py 자신은 세 계정 비밀번호가 전부 없으면 검사를
#    한 건도 안 돌고 종료코드 2 를 낸다("검사해서 통과"와 "검사 안 함"을
#    구분하려는 설계, smoke_test.py 907~914행) — 그런데 이 값을 실어 보내는
#    코드가 배포 스크립트 어디에도 없었다(저장소 전수 grep: deploy/ 아래 0곳).
#    그 결과 문서대로만 실행하면 매번 "검사 0건·종료코드 2"가 나서, 실제로는
#    아무 문제 없는 배포도 아래 262행의 최종 판정에서 항상 붉은 배너로
#    끝났다 — 담당자가 이 배너를 "원래 그런 것"으로 학습하면, 진짜 배포불가
#    사유(manage.py check 실패)가 났을 때도 못 알아챌 위험이 있다. 값은
#    db.py:seed() 가 만드는 시드 기본값이다(go-live 전까지만 유효 — go-live
#    후에는 이 계정 자체가 사라지고, 그때는 smoke_test.py 자신의 skip 처리가
#    해당 검사만 건너뛰고 나머지는 계속 돈다. 두 경우 모두 이전보다 낫다).
$env:BOKGUON_TEST_ADMIN_PW = "bokguon2026"
$env:BOKGUON_TEST_INSURER_PW = "bokguon2026"
$env:BOKGUON_TEST_PARTNER_PW = "partner2026"
$SmokeRc = 0
if (Test-Path (Join-Path $AppDir 'smoke_test.py')) {
    & $vpy smoke_test.py
    $SmokeRc = $LASTEXITCODE
    if ($SmokeRc -ne 0) { Warn "스모크 테스트가 실패했습니다(종료코드 $SmokeRc)." }
} else {
    Warn "smoke_test.py 가 없어 스모크 테스트를 건너뜁니다."
}
Remove-Item Env:\BOKGUON_TEST_ADMIN_PW, Env:\BOKGUON_TEST_INSURER_PW, Env:\BOKGUON_TEST_PARTNER_PW -ErrorAction SilentlyContinue
Pop-Location

if ($CheckRc -ne 0 -or $SmokeRc -ne 0 -or $SetupWarnFail) {
    Write-Host ""
    Write-Host "===========================================================" -ForegroundColor Red
    Write-Host "  설치는 끝났지만 - 아직 열면 안 됩니다" -ForegroundColor Red
    Write-Host "  위의 붉은 항목을 먼저 처리하세요. 처리 후 다시 점검:" -ForegroundColor Red
    Write-Host "    cd $AppDir; .\venv\Scripts\python.exe manage.py check"
    Write-Host "  서비스 주소는 그때까지 아무에게도 알리지 마세요." -ForegroundColor Red
    Write-Host "===========================================================" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor White
Write-Host "  설치 완료" -ForegroundColor Green
if ($Domain) { Write-Host "  서비스   : https://$Domain  (IIS/nginx 에서 TLS 종단 후 127.0.0.1:$Port 로 프록시)" }
Write-Host "  상태확인 : Get-Service bokguon"
Write-Host "  재시작   : Restart-Service bokguon"
Write-Host "  로그     : $AppDir\logs\service_err.log"
Write-Host "  점검     : cd $AppDir; .\venv\Scripts\python.exe manage.py check"
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor White
Write-Host ""
Warn "TLS 리버스 프록시(IIS ARR 또는 nginx)를 아직 설정하지 않았다면 반드시 먼저 구성하세요."
Warn "  운영 모드는 Secure 쿠키를 사용하므로, HTTPS 가 없으면 로그인이 유지되지 않습니다."
