# -*- coding: utf-8 -*-
"""스캔 322라운드 회귀 — deploy\\고정도메인_설정.ps1 재실행시 기존 도메인
   소실 + 터널/자격증명 부분일치 오판정, 이 세션 사상 첫 정밀조사한 조사
   Agent가 발견(저장소 루트 .py 32개·static/*.js 8개·templates/*.html 20개는
   전부 소진 확인 — deploy/ 안의 이 파일만 어떤 라운드에도 등장한 적 없었음).

   ① [심각] config.yml을 매번 통째로 덮어써 두 번째 실행(도메인 추가·오타
      수정)에서 기존 도메인이 ingress에서 사라진다 — Cloudflare 엣지에서
      조용히 404, 서버 로그엔 흔적이 전혀 안 남는다(로컬 origin까지 요청이
      오지 않으므로). 기존 도메인을 기본적으로 보존하고 -Replace 를
      명시해야만 빼도록 수정.
   ② [심각] 터널 존재 확인이 이름 "포함"(-match)이라 다른 터널 이름이
      우연히 부분문자열로 겹치면(예: "my-bokguon-old-test") 오판정하고,
      자격증명 파일도 "가장 최근 수정된 json"을 그냥 집어가는 방식이라
      엉뚱한 터널의 자격증명과 짝지어질 수 있었다 — cloudflared 2026.7.2가
      실제로 지원하는 `tunnel list --name <정확한 이름> --output json`으로
      교체해 정확매치(installed 버전에서 --help로 직접 확인 후 사용).

   실제 cloudflared.exe는 절대 부르지 않는다(로그인·터널 생성·DNS 변경은
   브라우저 상호작용이 필요한 진짜 Cloudflare 계정 조작이라 회귀테스트에서
   흉내만 낸다) — 실행 시점에 만드는 가짜 스텁(.ps1, STUB_PS1 문자열)으로
   실제 그 스크립트 **파일 자체**를 진짜로 실행해 검증한다(모킹이 아니라
   진짜 서브프로세스 실행 — 세션이 끝나도 이 파일 하나로 재현 가능하도록
   스텁 내용을 이 파일 안에 그대로 담아 둔다, 스크래치패드 의존 없음).
   .env 도 실제 운영 파일이 아니라 매번 새로 만드는 임시 파일을 가리키도록
   -EnvFile 로 넘긴다(운영 .env는 절대 건드리지 않는다).
"""
import os
import re
import sys
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PATH = os.path.join(HERE, "deploy", "고정도메인_설정.ps1")

PASS = FAIL = 0
FAILED = []


def chk(cond, msg, detail=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {msg}")
    else:
        FAIL += 1
        FAILED.append(msg)
        print(f"  [FAIL] {msg}" + (f"   {detail}" if detail else ""))


STUB_PS1 = r"""
$a = $args
if ($env:STUB_LOG) { ($a -join ' ') | Add-Content -LiteralPath $env:STUB_LOG -Encoding utf8 }
$SD = $env:STUB_CONFIG_DIR

if ($a.Count -ge 2 -and $a[0] -eq 'tunnel' -and $a[1] -eq 'create') {
    $name = $a[2]
    $id = "stubid-$name"
    Set-Content -LiteralPath (Join-Path $SD "_stub_tunnel_$name.id") -Value $id -Encoding utf8
    Set-Content -LiteralPath (Join-Path $SD "$id.json") -Value "{`"AccountTag`":`"x`",`"TunnelSecret`":`"y`",`"TunnelID`":`"$id`"}" -Encoding utf8
    exit 0
}
if ($a.Count -ge 2 -and $a[0] -eq 'tunnel' -and $a[1] -eq 'route') {
    exit 0
}
if ($a.Count -ge 2 -and $a[0] -eq 'tunnel' -and $a[1] -eq 'list') {
    $nameIdx = [Array]::IndexOf($a, '--name')
    if ($nameIdx -lt 0) { $nameIdx = [Array]::IndexOf($a, '-n') }
    if ($nameIdx -ge 0 -and ($nameIdx + 1) -lt $a.Count) {
        $filterName = $a[$nameIdx + 1]
        $idFile = Join-Path $SD "_stub_tunnel_$filterName.id"
        if (Test-Path -LiteralPath $idFile) {
            $id = (Get-Content -LiteralPath $idFile -Raw).Trim()
            Write-Output "[{`"id`":`"$id`",`"name`":`"$filterName`"}]"
        } else {
            Write-Output "[]"
        }
    } else {
        Write-Output "ID                                   NAME       CREATED"
        Get-ChildItem -LiteralPath $SD -Filter "_stub_tunnel_*.id" -ErrorAction SilentlyContinue | ForEach-Object {
            $n = $_.BaseName -replace '^_stub_tunnel_', ''
            Write-Output "stub-row-guid  $n   2026-01-01T00:00:00Z"
        }
    }
    exit 0
}
exit 0
"""

_scratch = tempfile.mkdtemp(prefix="bokguon_r322_")
STUB_PATH = os.path.join(_scratch, "fake_cloudflared.ps1")
with open(STUB_PATH, "w", encoding="utf-8") as f:
    f.write(STUB_PS1)


def run_ps1(config_dir, env_file, domain, tunnel_name, replace=False, stub_log=None):
    args = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", SCRIPT_PATH,
        "-Domain", domain,
        "-TunnelName", tunnel_name,
        "-CfdExe", STUB_PATH,
        "-ConfigDir", config_dir,
        "-EnvFile", env_file,
        "-SkipRestart",
    ]
    if replace:
        args.append("-Replace")
    env = dict(os.environ)
    env["STUB_CONFIG_DIR"] = config_dir
    if stub_log:
        env["STUB_LOG"] = stub_log
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=env, timeout=60)


def fresh_dir(prefix):
    d = os.path.join(_scratch, prefix)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "cert.pem"), "w", encoding="utf-8") as f:
        f.write("fake-cert")
    return d


def fresh_env(prefix):
    p = os.path.join(_scratch, f"{prefix}.env")
    with open(p, "w", encoding="utf-8") as f:
        f.write("BOKGUON_ALLOWED_HOSTS=127.0.0.1,localhost\n")
    return p


def read_cfg(config_dir):
    p = os.path.join(config_dir, "config.yml")
    if not os.path.exists(p):
        return ""
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def hostnames_in(cfg_text):
    return re.findall(r"(?m)^\s*-\s*hostname:\s*(\S+)", cfg_text)


print("=" * 74)
print("  스캔 322라운드 회귀 — 고정도메인_설정.ps1 재실행시 도메인소실 + 부분일치 오판정")
print("=" * 74)

# ── 시나리오 1: config.yml 도메인 보존/추가/-Replace ──────────
print("\n[1] 시나리오 — 같은 터널로 두 번째 도메인을 추가해도 첫 도메인이 살아있다")
cfgdir1 = fresh_dir("cfg1")
envfile1 = fresh_env("cfg1")

r1 = run_ps1(cfgdir1, envfile1, "old.example.com", "bokguon-r322a")
chk(r1.returncode == 0, "1차 실행(도메인 old.example.com) 성공",
    (r1.stdout[-500:] + r1.stderr[-500:]) if r1.returncode else None)
hosts1 = hostnames_in(read_cfg(cfgdir1))
chk(hosts1 == ["old.example.com"], "1차 실행 후 ingress에 old.example.com 하나만 있다", hosts1)

r2 = run_ps1(cfgdir1, envfile1, "new.example.com", "bokguon-r322a")
chk(r2.returncode == 0, "2차 실행(도메인 new.example.com 추가) 성공",
    (r2.stdout[-500:] + r2.stderr[-500:]) if r2.returncode else None)
hosts2 = hostnames_in(read_cfg(cfgdir1))
chk("old.example.com" in hosts2,
    "★★★★★ 2차 실행 후에도 첫 도메인(old.example.com)이 살아있다"
    "(고치기 전엔 config.yml을 통째로 덮어써 여기서 사라졌다)", hosts2)
chk("new.example.com" in hosts2, "2차 실행에서 추가한 new.example.com도 있다", hosts2)

r3 = run_ps1(cfgdir1, envfile1, "final.example.com", "bokguon-r322a", replace=True)
chk(r3.returncode == 0, "3차 실행(-Replace, final.example.com) 성공",
    (r3.stdout[-500:] + r3.stderr[-500:]) if r3.returncode else None)
hosts3 = hostnames_in(read_cfg(cfgdir1))
chk(hosts3 == ["final.example.com"],
    "-Replace 지정 시엔 의도대로 기존 도메인이 전부 빠지고 새 도메인만 남는다", hosts3)

# ── 시나리오 2: 터널/자격증명 정확매치(부분일치 오판정 방지) ──
print("\n[2] 시나리오 — 이름이 겹치는 무관한 터널이 있어도 정확히 일치하는 것만 찾는다")
cfgdir2 = fresh_dir("cfg2")
envfile2 = fresh_env("cfg2")
decoy_id = "decoy-uuid-unrelated"
with open(os.path.join(cfgdir2, "_stub_tunnel_my-bokguon-old-test.id"), "w", encoding="utf-8") as f:
    f.write(decoy_id)
with open(os.path.join(cfgdir2, f"{decoy_id}.json"), "w", encoding="utf-8") as f:
    f.write('{"AccountTag":"x","TunnelSecret":"y","TunnelID":"%s"}' % decoy_id)

stublog2 = os.path.join(_scratch, "stub2.log")
r4 = run_ps1(cfgdir2, envfile2, "fresh.example.com", "bokguon", stub_log=stublog2)
chk(r4.returncode == 0, "무관 터널(my-bokguon-old-test)이 있어도 실행 성공",
    (r4.stdout[-800:] + r4.stderr[-800:]) if r4.returncode else None)

log2 = ""
if os.path.exists(stublog2):
    with open(stublog2, "r", encoding="utf-8") as f:
        log2 = f.read()
chk("tunnel create bokguon" in log2,
    "★★★★★ 목표 터널(bokguon)이 없으므로 실제로 tunnel create가 호출된다"
    "(고치기 전엔 이름부분일치 오판정으로 생성 자체를 건너뛰었다)", log2)

cfg2_text = read_cfg(cfgdir2)
chk("stubid-bokguon.json" in cfg2_text,
    "★★★★★ 새로 만든 bokguon 터널 자신의 자격증명 파일을 정확히 가리킨다", cfg2_text)
chk(decoy_id not in cfg2_text,
    "★★★★★ 무관한 터널(decoy)의 자격증명을 잘못 집어가지 않는다"
    "(고치기 전엔 '가장 최근 수정 json' 규칙 때문에 이걸 집어갈 수 있었다)", cfg2_text)

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

shutil.rmtree(_scratch, ignore_errors=True)
sys.exit(1 if FAIL else 0)
