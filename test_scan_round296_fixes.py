# -*- coding: utf-8 -*-
"""스캔 296라운드 회귀 — deploy/windows_setup.ps1 이 예약작업 3개(DB백업·
   접속기록정리·개인정보파기)를 python.exe 로 직접 등록해, 그 작업이 실행될
   때마다(매일 새벽 3시 + 매주 일요일 새벽 2회) 콘솔 창이 떴다 사라지는 결함
   (라운드292 가 복구온_예약실행_등록.ps1 에서 이미 고친 것과 같은 결함 클래스).

   조사 에이전트가 이 세션 최초로 windows_setup.ps1 을 정밀조사해 짚었고,
   실측(schtasks /Query /TN 복구온_경매마감·복구온_일일백업 /XML, 읽기전용)으로
   재확인한 사실관계:
     · 이 스크립트 자신의 산출물(venv·bokguon 서비스·4개 예약작업 이름)이
       이 PC엔 하나도 없다 — 즉 이 스크립트가 이 운영 PC를 만든 게 아니다.
     · 이 PC의 실제 운영 예약작업은 '복구온_경매마감'(pythonw.exe, sweep)과
       '복구온_일일백업'(cmd.exe → deploy\\일일백업.bat, 백업+파기 3종 통합)
       단 둘뿐이며, 후자가 이 스크립트의 백업·접속기록정리·개인정보파기 3개
       작업이 하려는 일을 이미 로그+자가점검까지 갖춰 대신하고 있다.
     · 그런데도 이 3개를 "재현 안 해도 되는 중복"으로 지우는 것은 별개
       판단이다 — bootstrap.sh(리눅스판)도 정확히 이 스크립트와 같은 3분리
       구조로 cron 을 등록하므로(실측: grep, 260~289행), 3분리 자체는 두
       플랫폼 스크립트가 의도적으로 맞춘 설계다. 그래서 구조는 그대로 두고,
       확실한 결함(python.exe 콘솔 깜빡임)만 고친다 — 복구온_예약실행_등록.ps1
       이 이미 쓰는 것과 같은 pythonw.exe 폴백 변수($vpyw)를 새로 만들어
       예약작업 3개의 -Execute 에만 쓴다. NSSM 서비스 등록(세션0, 콘솔 자체가
       없음)과 그 위의 대화형 설치 단계(사람이 출력을 봐야 함)는 그대로 $vpy.

      python test_scan_round296_fixes.py
"""
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


PS1_PATH = os.path.join(HERE, "deploy", "windows_setup.ps1")
PS1_SRC = read(os.path.join("deploy", "windows_setup.ps1"))
BOOTSTRAP_SRC = read(os.path.join("deploy", "bootstrap.sh"))

print("=" * 72)
print("  스캔 296라운드 회귀 — windows_setup.ps1 예약작업 3개 콘솔 깜빡임")
print("=" * 72)


def _section(src, start_marker, end_marker):
    i0 = src.index(start_marker)
    i1 = src.index(end_marker, i0 + len(start_marker))
    return src[i0:i1]


STEP7 = _section(PS1_SRC, 'Step "7. 정기 작업', '# ── 8.')

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 7단계(예약작업) 구간 안에서 확인")
# ──────────────────────────────────────────────────────────────
chk('$vpyw = Join-Path $venv "Scripts\\pythonw.exe"' in STEP7,
    "★★★ pythonw.exe 경로를 스스로 찾는 $vpyw 가 정의돼 있다")
chk("if (-not (Test-Path $vpyw)) { $vpyw = $vpy }" in STEP7,
    "★★★ pythonw.exe 가 없으면 python.exe 로 폴백한다")

chk('New-ScheduledTaskAction -Execute $vpyw -Argument "manage.py backup"' in STEP7,
    "★★★ DB백업 작업이 $vpyw 를 쓴다(콘솔 깜빡임 대상이었던 3곳 중 1)")
chk('New-ScheduledTaskAction -Execute $vpyw -Argument "manage.py prune-logs"' in STEP7,
    "★★★ 접속기록정리 작업이 $vpyw 를 쓴다(2)")
chk('New-ScheduledTaskAction -Execute $vpyw -Argument "manage.py prune-personal"' in STEP7,
    "★★★ 개인정보파기 작업이 $vpyw 를 쓴다(3, 처리방침 제3조 이행 작업)")
chk(STEP7.count("-Execute $vpyw") == 3,
    "★★★ $vpyw 를 쓰는 -Execute 자리가 정확히 3곳뿐이다(더 늘거나 줄지 않음)",
    STEP7.count("-Execute $vpyw"))
chk("-Execute $vpy " not in STEP7 and "-Execute $vpy\n" not in STEP7 and "-Execute $vpy\r" not in STEP7,
    "★★ 7단계 안에는 고쳐지지 않은 -Execute $vpy 가 더 없다(부분일치 오탐 방지)")

# 사진백업(cmd.exe robocopy)은 이 결함과 무관 — 손대지 않았어야 한다
chk('New-ScheduledTaskAction -Execute "cmd.exe" -Argument (\'/c \' + $phCmd)' in STEP7,
    "★ 사진백업 작업(cmd.exe robocopy)은 그대로다(대상 아님, 오수정 방지)")

# NSSM 서비스 등록과 대화형 설치 단계는 여전히 $vpy(콘솔 보이는 python.exe) —
# 세션0 서비스·사람이 봐야 하는 출력이라 바뀌면 안 된다
NSSM_SECTION = _section(PS1_SRC, 'Step "5. Windows 서비스', '# ── 6.')
chk('$NssmExe install $svc $vpy' in NSSM_SECTION,
    "★★ NSSM 서비스 등록은 여전히 $vpy 를 쓴다(세션0이라 콘솔 자체가 없어 대상 아님)")
INSTALL_SECTION = _section(PS1_SRC, 'Step "1. 파이썬', 'Step "2. 환경설정')
chk(INSTALL_SECTION.count("$vpip") >= 2 and "$vpyw" not in INSTALL_SECTION,
    "★★ 대화형 설치 단계(pip 등)는 $vpyw 로 안 바뀌었다(사람이 출력을 봐야 함)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 전제 확인 — bootstrap.sh(리눅스)도 같은 3분리 구조다(구조 유지가 맞는 판단인지)")
# ──────────────────────────────────────────────────────────────
chk("manage.py backup" in BOOTSTRAP_SRC and "manage.py prune-logs" in BOOTSTRAP_SRC
    and "manage.py prune-personal" in BOOTSTRAP_SRC,
    "★ bootstrap.sh 도 backup·prune-logs·prune-personal 을 3개로 나눠 등록한다"
    "(3분리 자체는 결함이 아니라 두 플랫폼이 맞춘 설계 — 구조를 바꾸지 않은 근거)")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — PowerShell 파서로 전체 파일 문법 검증(진짜 파싱)")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round296_")
try:
    checker = os.path.join(_tmpdir, "parse_check.ps1")
    io.open(checker, "w", encoding="utf-8-sig").write(
        "param([string]$Target)\n"
        "$errs = $null\n"
        "[void][System.Management.Automation.Language.Parser]::ParseFile($Target, [ref]$null, [ref]$errs)\n"
        "if ($errs.Count -gt 0) { Write-Output ('PARSE_FAIL:' + $errs.Count); "
        "$errs | ForEach-Object { Write-Output $_.Message }; exit 1 }\n"
        "else { Write-Output 'PARSE_OK'; exit 0 }\n"
    )
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", checker, "-Target", PS1_PATH],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    chk(r.returncode == 0 and "PARSE_OK" in r.stdout,
        "★★★ windows_setup.ps1 전체가 PowerShell 파서를 통과한다(수정으로 문법이 깨지지 않았다)",
        (r.returncode, r.stdout.strip(), r.stderr.strip()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드296 [3] PowerShell 파서 검증", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[4] 실행 — $vpyw 폴백 로직 자체를 실제 파일시스템으로 검증(진짜 실행)")
#      (실제 등록/삭제는 절대 하지 않는다 — 이 로직만 떼어내 임시 venv 흉내로 돌린다)
# ──────────────────────────────────────────────────────────────
try:
    i0 = PS1_SRC.index('$vpyw = Join-Path $venv "Scripts\\pythonw.exe"')
    i1 = PS1_SRC.index("\n", PS1_SRC.index("$vpyw = $vpy }", i0)) + 1
    fallback_snippet = PS1_SRC[i0:i1]
    chk("$vpyw = Join-Path" in fallback_snippet and "$vpyw = $vpy" in fallback_snippet,
        "STEP 소스에서 폴백 로직 스니펫을 정확히 추출했다(하드코딩 아님)", fallback_snippet)

    def run_fallback(venv_dir, has_pythonw):
        scripts_dir = os.path.join(venv_dir, "Scripts")
        os.makedirs(scripts_dir, exist_ok=True)
        io.open(os.path.join(scripts_dir, "python.exe"), "w").write("x")
        if has_pythonw:
            io.open(os.path.join(scripts_dir, "pythonw.exe"), "w").write("x")
        #  ⚠ [라운드296] PowerShell 5.1 은 BOM 없는 .ps1 을 시스템 코드페이지(cp949)로
        #    읽는다 — 이 스크립트 안에 그대로 박아 넣는 $venv 경로(임시 폴더 밑,
        #    실제 사용자명 "개발자3" 포함)가 한글이라 BOM 없이 쓰면 깨져서 엉뚱한
        #    경로를 Test-Path 하게 된다(참고: reference_powershell_korean_bom 메모리 —
        #    처음 이 테스트를 짤 때 encoding="utf-8" 로 썼다가 정확히 이 증상으로
        #    두 케이스 다 실패해 실측으로 재확인했다). utf-8-sig 로 BOM 을 붙인다.
        script = os.path.join(_tmpdir, f"run_{has_pythonw}.ps1")
        io.open(script, "w", encoding="utf-8-sig").write(
            f'$venv = "{venv_dir}"\n'
            f'$vpy = Join-Path $venv "Scripts\\python.exe"\n'
            + fallback_snippet +
            "Write-Output $vpyw\n"
        )
        rr = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        return rr.stdout.strip().splitlines()[-1] if rr.stdout.strip() else ""

    #  ⚠ [라운드296] 디렉터리 이름 자체(venv_with_pythonw/venv_without_pythonw)에
    #    "pythonw" 라는 부분열이 들어있어, 전체 경로 문자열에 "pythonw"가
    #    있는지로 판정하면 폴백 실패(python.exe로 떨어짐)도 디렉터리명 때문에
    #    "pythonw"가 있다고 오판할 수 있다(실측: 처음엔 이 실수로 폴백 케이스가
    #    거짓양성으로 통과할 뻔했다) — 반드시 마지막 경로요소(파일명)만 비교한다.
    venv_with = os.path.join(_tmpdir, "case_a")
    result_with = run_fallback(venv_with, has_pythonw=True)
    chk(os.path.basename(result_with).lower() == "pythonw.exe",
        "★★★ pythonw.exe 가 실제로 있으면 $vpyw 가 그것을 가리킨다(콘솔 없이 실행)",
        result_with)

    venv_without = os.path.join(_tmpdir, "case_b")
    result_without = run_fallback(venv_without, has_pythonw=False)
    chk(os.path.basename(result_without).lower() == "python.exe",
        "★★★ pythonw.exe 가 없으면 $vpyw 가 python.exe 로 안전하게 폴백한다"
        "(설치 실패 대신 예전 동작으로 저하)",
        result_without)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드296 [4] $vpyw 폴백 실행 검증", f"{type(e).__name__} {e}")
finally:
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
