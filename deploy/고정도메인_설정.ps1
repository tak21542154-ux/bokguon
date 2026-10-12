# ══════════════════════════════════════════════════════════════
#  복구온 고정 도메인 설정 (bokguon.com 등)
#  ㈜올림포스네트웍스 전략사업실 유경탁 파트장
#
#  임시 터널은 서버가 다시 뜰 때마다 주소가 바뀐다. 이 스크립트는 그 주소를
#  **고정 도메인**으로 바꾼다. 한 번만 실행하면 된다.
#
#  ── 실행 전에 끝나 있어야 하는 것 ────────────────────────────
#   1) 도메인을 **구매**했다 (예: bokguon.com — 가비아·후이즈·Cloudflare 등)
#   2) 그 도메인을 **Cloudflare 계정에 추가**하고, 등록업체에서 네임서버를
#      Cloudflare 가 알려준 값으로 바꿨다 (반영에 최대 24시간, 보통 수십 분)
#      → Cloudflare 대시보드에서 도메인 상태가 "Active" 여야 한다
#
#  ⚠ 사용법:  PowerShell 창에서 직접 실행할 것 (중간에 브라우저 로그인이 뜬다)
#     .\고정도메인_설정.ps1 -Domain bokguon.com
#
#  ⚠ 두 번째 도메인을 추가하고 싶으면(예: app.bokguon.com 도 같이) 그냥 그
#    도메인으로 다시 실행하면 된다 — 기존 도메인은 유지되고 새 도메인이
#    추가된다(322라운드부터: 예전엔 config.yml을 통째로 덮어써 기존 도메인이
#    조용히 404로 죽었다 — Cloudflare 엣지에서 막혀 서버 로그엔 흔적도 안
#    남는 방식). 기존 도메인을 빼고 싶으면 -Replace 를 붙인다.
# ══════════════════════════════════════════════════════════════
param(
    [Parameter(Mandatory = $true)]
    [string]$Domain,                       # 예: bokguon.com  또는  app.bokguon.com
    [string]$TunnelName = "bokguon",
    [int]$Port = 8771,
    [switch]$Replace,                      # 기존 config.yml의 다른 도메인을 없애고 이번 도메인만 남긴다
    [string]$CfdExe = "C:\Program Files (x86)\cloudflared\cloudflared.exe",
    [string]$ConfigDir = (Join-Path $env:USERPROFILE ".cloudflared"),
    [string]$EnvFile,                      # 기본값은 서비스 루트의 .env (회귀테스트에서만 다른 경로로 override)
    [switch]$SkipRestart                   # 감시자 재기동을 건너뜀(회귀테스트 전용 — 실사용시 쓰지 말 것)
)

$ErrorActionPreference = 'Stop'
$CFD = $CfdExe
$CFDIR = $ConfigDir
if (-not $EnvFile) { $EnvFile = Join-Path (Split-Path $PSScriptRoot -Parent) ".env" }

function Step($n, $msg) { Write-Host "`n[$n] $msg" -ForegroundColor Cyan }
function Ok($msg) { Write-Host "  OK  $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  !!  $msg" -ForegroundColor Yellow }

Write-Host "============================================================"
Write-Host "  복구온 고정 도메인 설정 — $Domain"
Write-Host "============================================================"

if (-not (Test-Path $CFD)) { throw "cloudflared 를 찾을 수 없습니다: $CFD" }

# ── 1. Cloudflare 로그인 (브라우저) ──────────────────────────
Step 1 "Cloudflare 로그인"
$cert = Join-Path $CFDIR "cert.pem"
if (Test-Path $cert) {
    Ok "이미 로그인되어 있습니다 (cert.pem)"
} else {
    Warn "브라우저가 열립니다. Cloudflare 에 로그인하고 **$Domain 을 선택**해 주세요."
    & $CFD tunnel login
    if (-not (Test-Path $cert)) { throw "로그인이 끝나지 않았습니다. 다시 실행해 주세요." }
    Ok "로그인 완료"
}

# ── 2. 터널 생성 ─────────────────────────────────────────────
#  이름이 "포함"되는지가 아니라 **정확히 일치**하는 터널만 찾는다 — 예전엔
#  "bokguon"이 다른 터널 이름(예: "my-bokguon-old-test")의 부분문자열이기만
#  해도 "이미 있다"고 오판했다(322라운드에서 발견). cloudflared 2026.7.2가
#  지원하는 `tunnel list --name <정확한 이름> --output json`으로 교체.
Step 2 "터널 생성 ($TunnelName)"
$tunnels = @()
try {
    $listJson = & $CFD tunnel list --name $TunnelName --output json 2>&1 | Out-String
    $parsed = $listJson | ConvertFrom-Json
    if ($parsed) { $tunnels = @($parsed) }
} catch { $tunnels = @() }

if ($tunnels.Count -gt 0) {
    $tunnelId = $tunnels[0].id
    Ok "이미 있는 터널을 씁니다 (이름 정확히 일치, id: $tunnelId)"
} else {
    & $CFD tunnel create $TunnelName
    Ok "터널 생성됨"
    $listJson = & $CFD tunnel list --name $TunnelName --output json 2>&1 | Out-String
    $parsed = $listJson | ConvertFrom-Json
    $tunnels = @()
    if ($parsed) { $tunnels = @($parsed) }
    if ($tunnels.Count -eq 0) { throw "터널을 생성했지만 방금 만든 '$TunnelName'을 다시 찾지 못했습니다." }
    $tunnelId = $tunnels[0].id
}

# 자격증명 파일은 **터널 UUID 이름**으로 저장된다 — "가장 최근에 수정된
# json"이 아니라, 방금 확인한 그 터널의 UUID로 정확히 지정한다(이 PC에
# 다른 터널의 자격증명이 섞여 있어도 안전, 322라운드에서 발견한 문제 수정).
$credFile = Join-Path $CFDIR "$tunnelId.json"
if (-not (Test-Path -LiteralPath $credFile)) {
    throw "자격증명 파일을 찾지 못했습니다: $credFile"
}
Ok "자격증명: $(Split-Path -Leaf $credFile)"

# ── 3. DNS 연결 ──────────────────────────────────────────────
Step 3 "DNS 연결 ($Domain → 터널)"
try {
    & $CFD tunnel route dns $TunnelName $Domain
    Ok "DNS 레코드 생성됨"
} catch {
    Warn "DNS 연결 실패 — 이미 있는 레코드일 수 있습니다. Cloudflare 대시보드에서 확인하세요."
    Warn $_.Exception.Message
}

# ── 4. 설정 파일 ─────────────────────────────────────────────
#  기존 config.yml이 있으면 무조건 덮어쓰지 않고 기존 도메인을 보존한다 —
#  예전엔 두 번째 도메인을 추가하려고(또는 오타를 고치려고) 다시 실행하면
#  기존 도메인이 ingress에서 통째로 사라져, Cloudflare 엣지에서 조용히
#  404가 나가고(서버 로그엔 아무 흔적도 없음) 아무도 못 알아챘다(322라운드
#  에서 발견). -Replace 를 명시해야만 기존 도메인을 뺀다.
Step 4 "config.yml 작성"
$cfg = Join-Path $CFDIR "config.yml"
$hostnames = @($Domain)
if ((Test-Path -LiteralPath $cfg) -and -not $Replace) {
    $existingText = Get-Content -LiteralPath $cfg -Raw -Encoding utf8
    $oldHosts = [regex]::Matches($existingText, '(?m)^\s*-\s*hostname:\s*(\S+)') |
                ForEach-Object { $_.Groups[1].Value } |
                Where-Object { $_ -ne $Domain }
    if ($oldHosts) {
        Warn "기존 도메인을 유지합니다: $($oldHosts -join ', ') (빼려면 -Replace)"
        $hostnames = @($oldHosts) + $Domain
    }
} elseif ((Test-Path -LiteralPath $cfg) -and $Replace) {
    Warn "-Replace 지정 — 기존 config.yml의 다른 도메인은 모두 제거하고 $Domain 만 남깁니다."
}
$ingressBlock = ($hostnames | ForEach-Object { "  - hostname: $_`n    service: http://127.0.0.1:$Port" }) -join "`n"
@"
# 복구온 고정 도메인 터널 — 고정도메인_설정.ps1 이 생성
tunnel: $TunnelName
credentials-file: $credFile

ingress:
$ingressBlock
  - service: http_status:404
"@ | Set-Content -LiteralPath $cfg -Encoding utf8
Ok "$cfg (호스트: $($hostnames -join ', '))"

# ── 5. 허용 Host 등록 (보안) ─────────────────────────────────
#  이걸 빼면 새 도메인으로 들어온 요청이 전부 400 으로 막힌다.
Step 5 ".env 의 허용 주소에 $Domain 추가"
$txt = Get-Content -LiteralPath $EnvFile -Raw -Encoding utf8
if ($txt -match "(?m)^BOKGUON_ALLOWED_HOSTS=(.*)$") {
    $cur = $Matches[1]
    if ($cur -notlike "*$Domain*") {
        $txt = $txt -replace "(?m)^BOKGUON_ALLOWED_HOSTS=.*$", "BOKGUON_ALLOWED_HOSTS=$cur,$Domain"
        Set-Content -LiteralPath $EnvFile -Value $txt -Encoding utf8
        Ok "추가됨"
    } else { Ok "이미 있습니다" }
} else {
    Add-Content -LiteralPath $EnvFile -Value "`nBOKGUON_ALLOWED_HOSTS=127.0.0.1,localhost,$Domain" -Encoding utf8
    Ok "새로 추가됨"
}

# ── 6. 재시작 ────────────────────────────────────────────────
if ($SkipRestart) {
    Step 6 "감시자 재시작 (건너뜀 -SkipRestart)"
} else {
    Step 6 "감시자 재시작"
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
        Where-Object { $_.CommandLine -like '*상시가동*' } |
        ForEach-Object { taskkill /PID $_.ProcessId /F 2>&1 | Out-Null }
    taskkill /IM cloudflared.exe /F 2>&1 | Out-Null
    Start-Sleep 2
    Start-Process -WindowStyle Hidden -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSScriptRoot\외부접속_상시가동.ps1`""
    Ok "감시자 재시작됨 (고정 터널 모드로 전환)"
}

Write-Host "`n============================================================"
Write-Host "  완료 — 잠시 후 아래 주소로 접속됩니다" -ForegroundColor Green
Write-Host "    관리자 콘솔 : https://$Domain/admin"
Write-Host "    보험사 포털 : https://$Domain/insurer"
Write-Host "    협력사 포털 : https://$Domain/partner"
Write-Host "============================================================"
Write-Host "  * DNS 반영에 몇 분 걸릴 수 있습니다."
Write-Host "  * 진행 상황: logs\supervisor.log"
Write-Host ""
