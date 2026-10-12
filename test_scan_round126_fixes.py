# -*- coding: utf-8 -*-
"""스캔 126라운드 회귀 — deploy\\복구온_예약실행_등록.ps1 의 중복스윕 경고가
   비차단이고 manage.py::cmd_install_scheduler 등록방식은 아예 못 잡던 문제,
   deploy\\복구온_외부공개_등록.ps1 의 -Remove 가 예약만 지우고 이미 뜬
   감시자·터널은 살려두던 문제.

  [1] 중복 스윕 작업 경고가 "여기서 중단하세요"라고 말만 하고 스크립트
      자신은 절대 멈추지 않았다 — 실측: 이 PC에 지금 실제로 그 상태가
      있어(복구온_경매마감이 5분마다 돎), 그대로 실행하면 진짜 중복
      등록이 재현됐다.
  [2] 같은 중복탐지가 Arguments 문자열만 봐서, manage.py::cmd_install_scheduler
      가 등록하는 방식(.bat 하나만 가리키고 "manage.py sweep"은 그 안에만
      있음)은 구조적으로 못 잡는다 — 실행 확인(임시 작업 생성→탐지 실패
      확인→즉시 삭제).
  [3] 외부공개 -Remove 가 예약 작업·시작프로그램만 지우고, 이미 실행 중인
      감시자 루프·waitress·cloudflared 터널은 그대로 둬 "해제됨"이 떠도
      외부가 계속 응답할 수 있었다 — 전용 중지 도구(복구온_외부공개_중지.bat)
      가 이미 하는 실제 종료 로직이 이 파일에는 없었다.

      python test_scan_round126_fixes.py
"""
import io
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def run_ps(script, timeout=30):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                        capture_output=True, timeout=timeout)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


print("═" * 72)
print("  스캔 126라운드 회귀 — 예약스윕 중복경고 비차단·등록사각지대 / 외부공개 Remove 미종료")
print("═" * 72)

SWEEP_PS1 = os.path.join("deploy", "복구온_예약실행_등록.ps1")
EXPOSE_PS1 = os.path.join("deploy", "복구온_외부공개_등록.ps1")
SWEEP_SRC = read(SWEEP_PS1)
EXPOSE_SRC = read(EXPOSE_PS1)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
chk("[switch]$Force" in SWEEP_SRC, "★★★ 예약등록 스크립트에 -Force 스위치가 생겼다")
chk('Write-Error "중복 등록을 막았습니다' in SWEEP_SRC,
    "★★★ 중복 발견 시 실제로 멈춘다(Write-Error, 말만 하고 안 멈추던 것 수정)")
chk("function Test-SweepAction" in SWEEP_SRC and ".bat|cmd" not in SWEEP_SRC
    and r"\.(bat|cmd)$" in SWEEP_SRC,
    "★★★ 중복탐지가 .bat/.cmd 실행파일의 내용까지 본다"
    "(manage.py::cmd_install_scheduler 등록방식 사각지대 수정)")

chk(EXPOSE_SRC.count("Stop-Process") >= 1 and "'*상시가동*'" in EXPOSE_SRC,
    "★★★ 외부공개 -Remove 가 이제 감시자 프로세스를 직접 종료한다")
chk("cloudflared" in EXPOSE_SRC.split("if ($Remove)", 1)[1].split("$PwshExe = ", 1)[0],
    "★★★ -Remove 블록 안에서 cloudflared 터널도 종료한다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 중복탐지 함수가 실제로 .bat 내부의 sweep 을 찾아내는가")
# ──────────────────────────────────────────────────────────────
_tmpdir_ps = os.path.join(os.environ.get("TEMP", HERE), f"r126_probe_{int(time.time())}")
try:
    os.makedirs(_tmpdir_ps, exist_ok=True)
    bat_path = os.path.join(_tmpdir_ps, "_마감점검_probe.bat")
    io.open(bat_path, "w", encoding="utf-8-sig", newline="\r\n").write(
        '@echo off\r\nchcp 65001 >nul\r\ncd /d "C:\\dummy"\r\n"python.exe" manage.py sweep\r\n')

    ps_script = f'''
$scriptContent = Get-Content -Raw -LiteralPath "{SWEEP_PS1.replace(os.sep, "/")}" -Encoding UTF8
$block = $scriptContent.Substring($scriptContent.IndexOf("function Test-SweepAction"))
$block = $block.Substring(0, $block.IndexOf("`$dup ="))
Invoke-Expression $block
$fakeAction = [PSCustomObject]@{{ Execute = "{bat_path.replace(os.sep, "/")}"; Arguments = "" }}
$result = Test-SweepAction $fakeAction
Write-Output "RESULT:$result"
'''
    rc, out, err = run_ps(ps_script)
    chk("RESULT:True" in out,
        "★★★ Test-SweepAction 이 .bat 내부의 'manage.py sweep' 을 실제로 찾아낸다"
        "(예전 로직으로 재현하면 이 조합은 항상 못 찾았다)", (out, err[:300]))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드126 준비/실행(중복탐지 함수)", f"{type(e).__name__} {e}")
finally:
    import shutil
    shutil.rmtree(_tmpdir_ps, ignore_errors=True)

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 두 스크립트 구문이 유효한가")
# ──────────────────────────────────────────────────────────────
for label, relpath in (("예약실행 등록", SWEEP_PS1), ("외부공개 등록", EXPOSE_PS1)):
    try:
        full = os.path.join(HERE, relpath)
        ps_check = (
            '$e = $null; '
            '[System.Management.Automation.Language.Parser]::ParseFile('
            f'"{full}", [ref]$null, [ref]$e) | Out-Null; '
            'if ($e.Count -eq 0) { Write-Output "SYNTAX_OK" } '
            'else { $e | ForEach-Object { Write-Output $_.Message } }'
        )
        rc, out, err = run_ps(ps_check)
        chk("SYNTAX_OK" in out, f"★★★ {label} 구문이 유효하다(파서 오류 없음)", out)
    except Exception as e:                                          # noqa: BLE001
        chk(False, f"★★★ 라운드126 준비/실행(구문검사 {label})", f"{type(e).__name__} {e}")

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
