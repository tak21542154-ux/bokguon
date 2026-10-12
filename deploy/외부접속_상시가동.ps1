# ══════════════════════════════════════════════════════════════
#  복구온 외부 접속 상시 가동 (Cloudflare 터널 감시자)
#  ㈜올림포스네트웍스 전략사업실 유경탁 파트장
#
#  하는 일: prod 서버(waitress)와 Cloudflare 터널을 **살아 있게 유지**한다.
#    · 둘 중 하나가 죽으면 다시 띄운다 (PC 는 켜져 있는데 서비스만 죽는 경우 방지)
#    · 터널이 새로 뜨면 바뀐 주소를 파일에 기록한다 (바탕화면 + 회사 Z 드라이브)
#    · 로그온 시 자동 실행되도록 등록해두면(같은 폴더 등록.ps1) 재부팅도 견딘다
#
#  ⚠ 이 스크립트는 UTF-8 BOM 으로 저장되어야 한다 (한글 깨짐·구문오류 방지)
# ══════════════════════════════════════════════════════════════
$ErrorActionPreference = 'Continue'

#  ⚠ 경로는 **스크립트 위치에서 계산**한다. 리터럴로 박아 두면 다른 PC 로
#    옮겼을 때 서버가 아예 안 뜨는데, 그 사실이 로그에만 남고 아무도 안 본다.
#    (형제 스크립트 등록.ps1 들은 이미 $MyInvocation 으로 계산한다)
$SVC      = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $SVC 'serve_waitress.py'))) {
    #  폴더 구조가 다르면 종전 경로로 되돌아간다(이 PC 에서의 동작을 깨지 않는다)
    $SVC  = "C:\Users\개발자3\Desktop\olympos_bot\bokguon_service"
}
$CFD      = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
if (-not (Test-Path $CFD)) {
    $_c = (Get-Command cloudflared -ErrorAction SilentlyContinue)
    if ($_c) { $CFD = $_c.Source }
}
$PORT     = 8771
$DESK     = [Environment]::GetFolderPath('Desktop')
$URLFILE  = Join-Path $DESK "복구온_외부주소.txt"
$ZURLFILE = "Z:\11_부서내부\01_기획팀\13_신사업\08_기타피해물_플랫폼\260716_기타피해물_연계플랫폼\05_서비스_백엔드\_현재_외부주소.txt"
$LOGDIR   = Join-Path $SVC "logs"
$CFLOG    = Join-Path $LOGDIR "cloudflared.log"
$SUPLOG   = Join-Path $LOGDIR "supervisor.log"
$WOUT     = Join-Path $LOGDIR "waitress_out.log"
$WERR     = Join-Path $LOGDIR "waitress_err.log"

if (-not (Test-Path $LOGDIR)) { New-Item -ItemType Directory -Path $LOGDIR -Force | Out-Null }

function Note($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Host $line
    Add-Content -LiteralPath $SUPLOG -Value $line -Encoding utf8
}

function ServerAlive {
    #  ⚠⚠ [라운드128] 예전엔 6초였다 — db.py 의 BOKGUON_SQLITE_BUSY_MS(기본
    #    8000ms)가 이미 6초보다 크다. 쓰기 경합으로 busy_timeout 만큼(최대 8초)
    #    기다리는 스레드가 서버 안에서 정상적으로 도는 중이어도, 그 스레드가
    #    /healthz 를 처리할 차례를 못 받으면(스레드풀 8개 공유) 이 함수는 그걸
    #    "죽었다"로 오판한다. busy_timeout 보다 여유 있게 잡는다.
    try {
        $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$PORT/healthz" -TimeoutSec 10
        return $r.StatusCode -eq 200
    } catch { return $false }
}

function PublicServable {
    <#
      **공개 주소로 들어온 요청이 실제로 처리되는가.**

      ⚠ ServerAlive 만으로는 부족하다 — 그 확인은 127.0.0.1 로 가는데,
        그 호스트는 허용 목록에 늘 있으므로 **터널 주소가 막혀 있어도 200** 이다.
        2026-08-06 에 감시자가 일주일째 살아 있으면서도 외부 장애를 못 본 이유가
        정확히 이것이다(사람이 손으로 서버를 재시작해 허용 목록이 옛것으로 돌아갔다).
      터널을 거치지 않고 **Host 헤더만 바꿔** 같은 서버에 물어본다 —
      Host 관문을 통과하는지만 보면 되므로 외부 왕복이 필요 없다(빠르고 확실하다).
    #>
    if (-not $script:TunnelHost) { return $true }   # 아직 주소를 모르면 판단 보류
    try {
        $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$PORT/healthz" `
             -Headers @{ Host = $script:TunnelHost } -TimeoutSec 6
        return $r.StatusCode -eq 200
    } catch {
        $code = $null
        try { $code = $_.Exception.Response.StatusCode.value__ } catch {}
        if ($code -eq 400) { return $false }        # BAD_HOST — 허용 목록이 어긋났다
        return $true                                 # 그 밖의 오류는 ServerAlive 가 본다
    }
}

function StartServer {
    # 좀비 서버가 옛 코드를 서빙하는 사고가 반복됐다 — 먼저 전부 정리한다
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*serve_waitress*' } |
        ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force } catch {} }
    Start-Sleep 2
    # [보안] 허용 Host 를 서버에 넘긴다 — X-Forwarded-Host 위조로 CSRF 방어가
    #        무력화되는 것을 막는다. 터널 주소는 매번 바뀌므로 사람이 관리하면
    #        반드시 어긋난다 → 감시자가 아는 주소를 그대로 주입한다.
    $hosts = "127.0.0.1,localhost"
    if ($script:TunnelHost) { $hosts = "$hosts,$($script:TunnelHost)" }
    $env:BOKGUON_ALLOWED_HOSTS = $hosts
    #  ⚠⚠ [라운드127] 표준출력·표준에러를 어디로도 안 흘려보냈다 — 실제 운영
    #    로그(supervisor.log)에 "서버 응답 없음 → 재기동"이 128회(2026-07-30
    #    이후, 최근엔 하루에도 여러 번) 찍혀 있는데, 그 128번 각각에 무슨 예외가
    #    났는지는 어디에도 안 남았다(형제인 cloudflared 는 애초부터
    #    -RedirectStandardError 를 쓰는데 서버만 예외였다 — 재기동 40행 아래).
    #    강제종료(Stop-Process -Force) 로 다음 기동을 하므로, 그 순간 이전
    #    트레이스백은 숨김 콘솔째로 영구히 사라진다. 이제 남긴다 — 매 기동마다
    #    지난 세션 로그는 지우고 새로 받는다(cloudflared.log 와 같은 방식이라
    #    무한히 쌓이지 않는다).
    if (Test-Path $WOUT) { Remove-Item -LiteralPath $WOUT -Force -ErrorAction SilentlyContinue }
    if (Test-Path $WERR) { Remove-Item -LiteralPath $WERR -Force -ErrorAction SilentlyContinue }
    Start-Process -WindowStyle Hidden -WorkingDirectory $SVC -FilePath "python" -ArgumentList "serve_waitress.py" `
        -RedirectStandardOutput $WOUT -RedirectStandardError $WERR
    Note "서버 기동 시도 (포트 $PORT · 허용 Host: $hosts)"
    for ($i = 0; $i -lt 15; $i++) { Start-Sleep 2; if (ServerAlive) { Note "서버 정상"; return $true } }
    Note "⚠ 서버가 15회 확인에도 응답 없음 — 로그 확인: $WERR"
    return $false
}

function TunnelProcs { Get-Process cloudflared -ErrorAction SilentlyContinue }

function StartTunnel {
    TunnelProcs | ForEach-Object { try { Stop-Process -Id $_.Id -Force } catch {} }
    Start-Sleep 2
    if (Test-Path $CFLOG) { Remove-Item -LiteralPath $CFLOG -Force -ErrorAction SilentlyContinue }
    # 고정 도메인 터널(named tunnel)이 설정돼 있으면 그걸 쓴다 — 주소가 안 바뀐다.
    # 없으면 임시 터널(trycloudflare)로 즉시 서비스한다.
    #
    # ⚠ 판정 기준을 `bokguon.json` 존재로 두면 안 된다 —
    #   `cloudflared tunnel create bokguon` 은 자격증명을 **터널 UUID 이름**으로
    #   저장한다(예 `a1b2c3….json`). 터널 이름으로 된 파일은 생기지 않으므로
    #   고정 도메인을 다 설정해도 계속 임시 터널로 돌게 된다.
    #   그래서 `config.yml` + `cert.pem` 존재로 판정하고, 접속 주소는
    #   config.yml 의 hostname 에서 읽는다(사람이 두 곳에 적지 않게).
    $cfDir = Join-Path $env:USERPROFILE ".cloudflared"
    $cfg = Join-Path $cfDir "config.yml"
    $cert = Join-Path $cfDir "cert.pem"
    if ((Test-Path $cfg) -and (Test-Path $cert)) {
        $host1 = (Select-String -LiteralPath $cfg -Pattern '^\s*-?\s*hostname:\s*(\S+)' -AllMatches |
                  ForEach-Object { $_.Matches[0].Groups[1].Value }) | Select-Object -First 1
        Start-Process -WindowStyle Hidden -FilePath $CFD `
            -ArgumentList "tunnel","--config",$cfg,"run" -RedirectStandardError $CFLOG
        if ($host1) {
            PublishUrl "https://$host1"
            Note "고정 도메인 터널 기동 — $host1"
        } else {
            Note "⚠ config.yml 에 hostname 이 없다 — 주소를 알 수 없음 ($cfg)"
        }
        return
    }
    Start-Process -WindowStyle Hidden -FilePath $CFD `
        -ArgumentList "tunnel","--url","http://127.0.0.1:$PORT","--no-autoupdate" `
        -RedirectStandardError $CFLOG
    Note "임시 터널 기동 — 주소 확인 중"
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep 2
        if (-not (Test-Path $CFLOG)) { continue }
        $m = (Select-String -LiteralPath $CFLOG -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -AllMatches -ErrorAction SilentlyContinue).Matches.Value | Select-Object -First 1
        if ($m) { PublishUrl $m; return }
    }
    #  ⚠⚠ [라운드127] 예전엔 경고만 찍고 cloudflared 프로세스는 죽이지 않고 뒀다 —
    #    TunnelProcs 는 계속 "있음"으로 보여 아래 감시 루프의 재시도 조건
    #    (`if (-not (TunnelProcs))`)이 다시는 안 걸렸다. PublicServable 도
    #    $script:TunnelHost 가 없으면 "문제없음"으로 보류하므로(그 함수 자체
    #    주석 참조), 이 경로로 들어오면 유일한 실패 감지 장치가 무기한 잠든다
    #    (실측: 지금까지 실제로 발생한 적은 없다 — 측정된 7건 모두 4~14초로
    #    40초에 크게 못 미쳤다 — 하지만 유일한 방어선이 이 경우에만 완전히
    #    비활성화되는 구조적 결함은 확정적이다). 프로세스를 정리해 다음 순회가
    #    정상적으로 재시도하게 한다.
    Note "⚠ 터널 주소를 찾지 못했다 — 다시 시도하도록 정리한다 (로그: $CFLOG)"
    TunnelProcs | ForEach-Object { try { Stop-Process -Id $_.Id -Force } catch {} }
}

function PublishUrl($url) {
    $script:TunnelHost = ([Uri]$url).Host      # 서버 허용 Host 목록에 넣을 값
    $now = Get-Date -Format 'yyyy-MM-dd HH:mm'
    $body = @"
복구온 외부 접속 주소   (갱신 $now)
============================================================

  관리자 콘솔 : $url/admin
  보험사 포털 : $url/insurer
  협력사 포털 : $url/partner
  서비스 소개 : $url/

============================================================
· 이 주소는 임시 터널이라 **서버·PC 가 다시 뜰 때마다 바뀐다.**
  바뀌면 이 파일이 자동으로 갱신되니 여기서 확인하면 된다.
· 주소를 고정하고 싶으면 deploy\외부접속_안내.md 의 '고정 도메인' 절을 따른다
  (도메인은 bokguon.com — olymposcar.com 은 회사 홈페이지 DNS 라 건드리지 않는다).
· 이 주소를 아는 사람은 로그인 화면까지 도달한다 — 링크를 공유하지 말 것.
"@
    Set-Content -LiteralPath $URLFILE -Value $body -Encoding utf8
    try { Set-Content -LiteralPath $ZURLFILE -Value $body -Encoding utf8 -ErrorAction Stop } catch {}
    #  ★ 서버가 직접 읽는 **기계용** 파일도 함께 쓴다.
    #    사람이 손으로 `python serve_waitress.py` 를 실행해도 이 파일 덕에
    #    허용 Host 가 유지된다 — 안 그러면 외부가 조용히 400 으로 막히는데
    #    로컬 점검은 전부 통과해서 아무도 모른다(2026-08-06 실제 사고).
    $HOSTFILE = Join-Path $LOGDIR "public_host.txt"
    Set-Content -LiteralPath $HOSTFILE -Encoding utf8 -Value @(
        "# 감시자(외부접속_상시가동.ps1)가 갱신한다. 손으로 고치지 말 것.",
        $script:TunnelHost)
    Note "외부 주소 = $url  (바탕화면 복구온_외부주소.txt · logs\public_host.txt 갱신)"
}

# ── 감시 루프 ────────────────────────────────────────────────
#  ⚠ 순서가 중요하다: **터널을 먼저** 띄워 주소를 알아낸 뒤 서버를 기동한다.
#    서버가 시작할 때 허용 Host 목록(BOKGUON_ALLOWED_HOSTS)에 터널 주소가 들어가야
#    하기 때문이다. 터널이 먼저 떠서 잠깐 502 를 내는 것은 문제가 되지 않는다.
#  ★ **감시자는 한 번에 하나만 돈다.**
#    자동 시작 경로가 둘(작업 스케줄러 · 시작프로그램 폴더)이라 재부팅 직후
#    두 개가 동시에 뜰 수 있다. 그러면 서로 상대의 cloudflared 를 죽이고
#    새 터널을 띄우는 경합이 벌어져 **주소가 몇 분마다 바뀐다** —
#    바깥에서는 '가끔 안 열린다'로만 보이고 로그에는 경고가 한 줄도 안 남는다.
#    Global\ 로 잡아야 작업 스케줄러(세션 0)와 로그온 세션이 서로를 본다.
$script:Mutex = New-Object System.Threading.Mutex($false, 'Global\Bokguon_Supervisor')
$script:HaveLock = $false
try { $script:HaveLock = $script:Mutex.WaitOne(0) }
catch [System.Threading.AbandonedMutexException] { $script:HaveLock = $true }
if (-not $script:HaveLock) {
    Note "이미 다른 감시자가 돌고 있다 — 이번 실행은 그냥 종료한다(2중 실행 방지)"
    exit 0
}

$script:TunnelHost = $null
Note "===== 감시자 시작 ====="

#  ★ **살아 있는 터널은 죽이지 않는다.**
#    종전에는 시작하자마자 StartTunnel 이 cloudflared 를 무조건 죽이고 다시 띄웠다.
#    임시 터널은 뜰 때마다 주소가 바뀌므로, 감시자를 켜는 것만으로 이미 공유한
#    접속 주소가 무효가 됐다(사람들에게 다시 안내해야 한다).
#    이미 돌고 있고 그 주소를 알 수 있으면 그대로 이어받는다.
$HOSTFILE0 = Join-Path $LOGDIR "public_host.txt"
$reuse = $null
if (TunnelProcs) {
    if (Test-Path $HOSTFILE0) {
        $reuse = (Get-Content -LiteralPath $HOSTFILE0 |
                  Where-Object { $_ -and -not $_.StartsWith("#") } |
                  Select-Object -First 1)
    }
    if (-not $reuse -and (Test-Path $CFLOG)) {
        $m = Select-String -LiteralPath $CFLOG -Pattern 'https://([a-z0-9-]+\.trycloudflare\.com)' -AllMatches
        if ($m) { $reuse = ($m | Select-Object -Last 1).Matches[0].Groups[1].Value }
    }
}
if ($reuse) {
    $script:TunnelHost = $reuse.Trim()
    Note "이미 돌고 있는 터널을 이어받는다 — $($script:TunnelHost) (주소 유지)"
    PublishUrl "https://$($script:TunnelHost)"
} else {
    StartTunnel
}
StartServer | Out-Null

#  ⚠⚠ [라운드127] 4곳 전부 StartServer 의 반환값(성공 $true/실패 $false)을
#    Out-Null 로 버렸다 — StartServer 자신은 30초 폴링에도 안 살아나면 분명히
#    $false 를 주는데, 호출부가 그걸 무시하니 바깥 루프는 "재기동 성공"과
#    "재기동 자체가 실패"를 구분 못 하고 무조건 30초 뒤 재시도만 반복한다.
#    일시적 응답지연과 영구 배포사고(문법오류·의존성 누락·포트 선점 등)가
#    로그상 똑같은 문구로만 남아, 사람이 원격으로 직접 들어와 손으로
#    `python serve_waitress.py` 를 실행해 보기 전까지는 구분할 방법이 없었다.
#    반환값을 실제로 보고, 연속 실패면 다른(검색하기 쉬운) 문구로 남긴다.
$restartFail = 0
function NoteRestart($ok) {
    if ($ok) { $script:restartFail = 0; return }
    $script:restartFail++
    Note "⚠⚠ 재기동 자체가 실패했습니다(연속 $($script:restartFail)회) — 로그 확인: $WERR"
}

$fail = 0
while ($true) {
    Start-Sleep 30
    if (-not (TunnelProcs)) {
        Note "터널 프로세스 없음 — 터널·서버 재기동(주소가 바뀌므로 서버도 함께)"
        StartTunnel
        NoteRestart (StartServer)
        continue
    }
    if (-not (ServerAlive)) {
        $fail++
        #  ⚠⚠ [라운드128] $fail 을 세기만 하고 문턱값 없이 매번(1회부터) 바로
        #    강제종료+재기동했다 — 실측(supervisor.log)으로 128건 전부가
        #    예외 없이 "(1 회)"였고, 같은 구간 bokguon.log 에는 트레이스백이
        #    전혀 없었다(서버가 진짜 죽은 흔적이 없다). 재시도 없이 단발
        #    지연만으로 죽였다는 뜻 — 한 번 더(다음 30초 순회) 확인하고 나서
        #    재기동한다. 진짜 장애면 다음 순회도 실패하므로 최대 30초만 늦어진다.
        if ($fail -lt 2) {
            Note "서버 응답 없음 ($fail 회) — 일시적일 수 있어 다음 순회에서 재확인"
            continue
        }
        Note "서버 응답 없음 ($fail 회) — 재기동"
        NoteRestart (StartServer)
        continue
    }
    #  ★ 서버는 살아 있는데 **공개 주소만 막힌** 상태를 잡는다.
    #    사람이 감시자를 우회해 손으로 재시작하면 허용 Host 가 .env 의 옛 목록으로
    #    돌아가 외부가 전부 400 이 된다 — 로컬 확인만으로는 영원히 못 본다.
    if (-not (PublicServable)) {
        Note "⚠ 공개 주소($($script:TunnelHost))가 400 으로 막혀 있다 — 허용 Host 를 다시 넣고 재기동"
        NoteRestart (StartServer)
        continue
    }
    $fail = 0
}
