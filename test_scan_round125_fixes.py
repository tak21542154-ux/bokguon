# -*- coding: utf-8 -*-
"""스캔 125라운드 회귀 — windows_setup.ps1 네이티브 exe 7곳 종료코드 미검사,
   스모크 테스트 필수 자격증명이 배포 스크립트 어디에도 안 실림.

  [1] deploy/windows_setup.ps1 이 venv 생성·pip 설치 2회·icacls 2회·
      manage.py init·create-admin, 7곳에서 네이티브 exe 종료코드를 안 봤다.
      PowerShell 5.1 의 $ErrorActionPreference='Stop' 은 네이티브 exe 의
      0 아닌 종료코드를 오류로 승격시키지 않는다 — 저자가 같은 파일의
      manage.py check·smoke_test.py 호출부(238~256행)에는 이미 이해하고
      고쳐 둔 패턴을 나머지 7곳에는 일관되게 못 넣었다(실행 재현: icacls
      강제 실패에도 바로 다음 줄이 무조건 [OK] 를 찍음).
  [2] smoke_test.py 가 요구하는 BOKGUON_TEST_ADMIN_PW·_INSURER_PW·_PARTNER_PW
      세 환경변수가 deploy/bootstrap.sh·windows_setup.ps1·DEPLOY.md 어디에도
      없었다(저장소 전수 grep 0곳) — 문서대로 배포하면 스모크 테스트가 매번
      "검사 0건·종료코드 2"로 끝나 실제 배포상태와 무관하게 항상 붉은 배너가
      떴다(영구 거짓 빨강 — 알람 피로 위험).

      python test_scan_round125_fixes.py
"""
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


print("═" * 72)
print("  스캔 125라운드 회귀 — windows_setup.ps1 종료코드 미검사 7곳·스모크 자격증명 미배선")
print("═" * 72)

DB_SRC = read("db.py")
PS1_SRC = read(os.path.join("deploy", "windows_setup.ps1"))
SH_SRC = read(os.path.join("deploy", "bootstrap.sh"))

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — windows_setup.ps1 의 7곳이 이제 $LASTEXITCODE 를 본다")
# ──────────────────────────────────────────────────────────────
chk(PS1_SRC.count("$LASTEXITCODE") >= 9,
    "★★★ windows_setup.ps1 전체에서 $LASTEXITCODE 확인이 9곳 이상이다"
    "(예전엔 manage.py check·smoke_test.py 2곳뿐)", PS1_SRC.count("$LASTEXITCODE"))

for needle in ('& python -m venv $venv', '& $vpip install --quiet --upgrade pip',
               '& $vpip install --quiet -r (Join-Path $AppDir "requirements.txt")',
               '& icacls $f /inheritance:r', '& icacls $backupDir /inheritance:r',
               '& $vpy (Join-Path $AppDir "manage.py") init',
               '& $vpy (Join-Path $AppDir "manage.py") create-admin'):
    start = PS1_SRC.index(needle)
    window = PS1_SRC[start:start + 400]
    chk("$LASTEXITCODE" in window,
        f"★★ '{needle[:40]}...' 직후 400자 안에 $LASTEXITCODE 확인이 있다")

chk("$SetupWarnFail" in PS1_SRC and "-or $SetupWarnFail)" in PS1_SRC,
    "★★★ ACL·관리자계정 실패가 최종 판정(8단계 배너)에 반영된다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — $LASTEXITCODE 확인 패턴이 실제로 실패를 잡는가 (격리된 PowerShell)")
# ──────────────────────────────────────────────────────────────
def run_ps(script):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                        capture_output=True, timeout=30)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


try:
    _, out_bug, _ = run_ps(
        '$ErrorActionPreference = "Stop"; '
        '& cmd.exe /c "exit 7"; '
        'Write-Output "REACHED_AFTER_FAILURE"'
    )
    chk("REACHED_AFTER_FAILURE" in out_bug,
        "STEP 재현: $ErrorActionPreference='Stop' 은 네이티브 exe 의 0 아닌 종료코드를 "
        "승격하지 않는다(이 버그의 근본 원인 — 이 프로젝트가 코드를 못 고치는 부분이 "
        "아니라 PowerShell 5.1 자체의 동작)", out_bug)

    _, out_fixed, _ = run_ps(
        '$ErrorActionPreference = "Stop"; '
        '& cmd.exe /c "exit 7"; '
        'if ($LASTEXITCODE -ne 0) { Write-Output ("CAUGHT:" + $LASTEXITCODE) } '
        'else { Write-Output "NOT_CAUGHT" }'
    )
    chk("CAUGHT:7" in out_fixed,
        "★★★ $LASTEXITCODE 를 명시적으로 보는 패턴(이번에 7곳에 추가한 것과 동일)은 "
        "실제로 실패를 잡는다", out_fixed)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드125 준비/실행(PowerShell 격리검증)", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — windows_setup.ps1 구문 자체가 깨지지 않았는가")
# ──────────────────────────────────────────────────────────────
try:
    rc, out, err = run_ps(
        '$e = $null; '
        '[System.Management.Automation.Language.Parser]::ParseFile('
        f'"{os.path.join(HERE, "deploy", "windows_setup.ps1")}", [ref]$null, [ref]$e) | Out-Null; '
        'if ($e.Count -eq 0) { Write-Output "SYNTAX_OK" } else { $e | ForEach-Object { Write-Output $_.Message } }'
    )
    chk("SYNTAX_OK" in out, "★★★ windows_setup.ps1 구문이 유효하다(파서 오류 없음)", out)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드125 준비/실행(구문검사)", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[4] 소스 확인 — 스모크 테스트 자격증명이 이제 배포 스크립트에 실린다")
# ──────────────────────────────────────────────────────────────
# db.py 의 실제 시드 값과 정확히 일치하는지까지 대조한다(값이 나중에
# 바뀌어도 이 테스트가 드리프트를 잡도록).
chk('hash_pw("bokguon2026")' in DB_SRC, "STEP db.py 의 admin 시드 비밀번호가 여전히 bokguon2026 이다(전제조건)")
chk('"insurer", "bokguon2026"' in DB_SRC, "STEP db.py 의 insurer 시드 비밀번호가 여전히 bokguon2026 이다(전제조건)")
chk('hash_pw("partner2026")' in DB_SRC, "STEP db.py 의 partner 시드 비밀번호가 여전히 partner2026 이다(전제조건)")

chk('$env:BOKGUON_TEST_ADMIN_PW = "bokguon2026"' in PS1_SRC
    and '$env:BOKGUON_TEST_INSURER_PW = "bokguon2026"' in PS1_SRC
    and '$env:BOKGUON_TEST_PARTNER_PW = "partner2026"' in PS1_SRC,
    "★★★ windows_setup.ps1 이 smoke_test.py 호출 전에 세 자격증명을 db.py 시드값 "
    "그대로 싣는다(예전엔 전혀 없었다)")
chk('export BOKGUON_TEST_ADMIN_PW="bokguon2026"' in SH_SRC
    and 'export BOKGUON_TEST_INSURER_PW="bokguon2026"' in SH_SRC
    and 'export BOKGUON_TEST_PARTNER_PW="partner2026"' in SH_SRC,
    "★★★ bootstrap.sh 도 마찬가지다(리눅스 경로도 같은 결함이었다)")
chk("unset BOKGUON_TEST_ADMIN_PW BOKGUON_TEST_INSURER_PW BOKGUON_TEST_PARTNER_PW" in SH_SRC,
    "★ bootstrap.sh 가 스모크 테스트 뒤 자격증명을 셸 환경에서 정리한다(위생)")

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
