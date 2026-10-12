# -*- coding: utf-8 -*-
"""스캔 559라운드 회귀 — deploy/windows_setup.ps1 이 예약작업 4개(DB백업·사진백업·
   접속기록정리·개인정보파기)를 등록할 때 `Register-ScheduledTask ... | Out-Null`
   뒤 조건 없이 성공 메시지(Ok)를 찍기만 했다.

   이번 라운드가 직접 조사(하위위임 없음)해 짚은 사실관계:
     · 이 파일 25행 `$ErrorActionPreference = "Stop"` 이 있어도, Register-ScheduledTask
       가 내는 CIM 오류("Access is denied" 등)는 그걸로 승격되지 않는다 — 바로 이
       결함 클래스를 형제 스크립트 두 개가 이미 실제 사고로 겪고 고쳤다:
         - deploy/복구온_예약실행_등록.ps1 121~141행
         - deploy/복구온_외부공개_등록.ps1  100~116행
       두 스크립트 모두 "2026-08-06 실제로 그랬다 — Access is denied 인데 화면은
       등록됐다고 했다"는 동일 사고를 comment 로 명시하고, 그 처리로
       (1) `-ErrorAction Stop` + try/catch, (2) 등록 뒤 `Get-ScheduledTask` 로
       실제 재조회, 두 겹을 쓴다.
     · 그런데 이 수정이 그 두 스크립트에만 머물고, windows_setup.ps1 이 직접
       등록하는 4곳(복구온_DB백업·복구온_사진백업·복구온_접속기록정리·
       복구온_개인정보파기, 255~311행 — 라운드296 이 고친 건 pythonw.exe 콘솔
       깜빡임이라는 *다른* 결함이고 이 재조회 결함은 손대지 않았다)에는 한 번도
       옮겨오지 않았다. 권한 문제가 있는 PC에서 이 스크립트를 실행하면 DB
       백업도, 처리방침이 공개 약속한 개인정보 파기(299~303행, 개인정보 보호법
       §21·§30 이행)도 전혀 등록되지 않는데 화면은 전부 초록 [OK]만 보여줄 수
       있었다 — manage.py:cmd_sweep()(라운드557)·dispatch.sweep_dispatches()
       (라운드558)가 이미 닫은 "예약작업이 조용히 실패한다" 앵글의 세 번째
       변종(이번엔 실행 시점이 아니라 *등록* 시점의 침묵 실패)이다.

   고침 — 형제 두 스크립트와 같은 처리(-ErrorAction Stop + try/catch + 등록 뒤
   재조회)를 함수 하나(Register-BokguonTask)로 모아 4곳이 전부 그것만 쓰게
   했다(중복 대신 공유 지점 하나, 형제 스크립트의 확립된 스타일 그대로).

   검증 방법 — windows_setup.ps1 은 .ps1 이라 Python monkeypatch 대상이 아니므로
   round296 이 이미 쓴 방식을 그대로 따른다: 실제 소스에서 함수 정의를 중괄호
   균형으로(문자열 매칭이 아니라) 정확히 뽑아, PowerShell 자신에게 가짜
   Register-ScheduledTask/Get-ScheduledTask 를 주입해 진짜로 실행시켜 인과관계를
   확인한다(실제 스케줄러에는 전혀 닿지 않음 — 이름이 같은 함수가 스코프 안에서
   cmdlet을 가린다). 되돌리기 증명은 실제 파일을 건드리지 않고 옛 패턴을
   메모리 문자열로 재구성해 같은 가짜 아래서 돌려 비교한다.

      python test_scan_round559_fixes.py
"""
import io
import os
import subprocess
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


PS1_PATH = os.path.join(HERE, "deploy", "windows_setup.ps1")
PS1_SRC = read(os.path.join("deploy", "windows_setup.ps1"))
SIBLING1_SRC = read(os.path.join("deploy", "복구온_예약실행_등록.ps1"))
SIBLING2_SRC = read(os.path.join("deploy", "복구온_외부공개_등록.ps1"))

print("=" * 72)
print("  스캔 559라운드 회귀 — windows_setup.ps1 예약작업 4개 등록 침묵실패")
print("=" * 72)


def _section(src, start_marker, end_marker):
    i0 = src.index(start_marker)
    i1 = src.index(end_marker, i0 + len(start_marker))
    return src[i0:i1]


def extract_function(src, name):
    """중괄호 깊이를 실제로 세어 함수 본문을 뽑는다(문자열 부분매칭이 아니라
    구조로 판정 — 창(window) 판정은 구조가 아니라는 이전 사고를 반복하지 않는다:
    이 함수 몸통 안에 try/catch/if 가 중첩돼 있어 첫 '}' 만 찾으면 잘린다)."""
    marker = f"function {name}("
    i0 = src.index(marker)
    i_open = src.index("{", i0)
    depth = 0
    i = i_open
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[i0:i + 1]
        i += 1
    raise ValueError("함수 " + name + " 의 닫는 중괄호를 못 찾았다")


STEP7 = _section(PS1_SRC, 'Step "7. 정기 작업', '# ── 8.')

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 4개 호출 지점이 전부 공유 함수를 쓰고, 원시 호출이 남지 않았다")
# ──────────────────────────────────────────────────────────────
chk("function Register-BokguonTask(" in STEP7,
    "★★★ 공유 함수 Register-BokguonTask 가 7단계 안에 정의돼 있다")

for var, label in [("$taskBackup", "DB백업"), ("$taskPhoto", "사진백업"),
                    ("$taskPrune", "접속기록정리"), ("$taskPrunePersonal", "개인정보파기")]:
    chk(f"Register-BokguonTask {var} $a $t" in STEP7,
        f"★★★ {label}({var}) 호출 지점이 Register-BokguonTask 를 쓴다")

chk(STEP7.count("Register-BokguonTask " ) == 4,
    "★★★ Register-BokguonTask 호출이 정확히 4번뿐이다(더 늘거나 줄지 않음)",
    STEP7.count("Register-BokguonTask "))

# 4개 호출 지점(모두 $task 로 시작하는 변수를 씀)에 옛 원시 호출 패턴
# "Register-ScheduledTask -TaskName $task..." 이 하나도 남아있으면 안 된다.
# (STEP7 안에는 이 결함을 설명하는 주석 문장 자체도 "Register-ScheduledTask"
#  라는 낱말을 담고 있으므로, 전체 문자열 개수가 아니라 실제 호출 패턴만 본다.)
chk("Register-ScheduledTask -TaskName $task" not in STEP7,
    "★★★★ 4개 호출 지점 어디에도 옛 원시 호출 패턴이 남아있지 않다(핵심 회귀 방지 지표)")

FUNC_SRC = extract_function(STEP7, "Register-BokguonTask")
chk(FUNC_SRC.count("Register-ScheduledTask -TaskName $TaskName") == 1,
    "★★★ 함수 안에는 실제 cmdlet 호출이 정확히 1번뿐이다")
chk("-ErrorAction Stop" in FUNC_SRC, "★★★ 함수가 -ErrorAction Stop 을 명시한다(형제 스크립트와 동일)")
chk("catch" in FUNC_SRC, "★★★ 함수가 try/catch 로 감싼다")
chk("Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue" in FUNC_SRC,
    "★★★ 함수가 등록 뒤 실제로 재조회한다(등록됐다고 '믿지' 않는다)")
chk(FUNC_SRC.count("Ok ") == 1 and FUNC_SRC.count("Warn ") == 2,
    "★★ Ok 는 재조회로 확인된 경우에만, Warn 은 실패·재조회실패 두 경로에서 나온다",
    (FUNC_SRC.count("Ok "), FUNC_SRC.count("Warn ")))

# ══════════════════════════════════════════════════════════════
print("\n[2] 전제 확인 — 형제 두 스크립트가 실제로 이 패턴(먼저 확립된 스타일)을 갖고 있다")
# ──────────────────────────────────────────────────────────────
chk("2026-08-06" in SIBLING1_SRC and "-ErrorAction Stop" in SIBLING1_SRC,
    "★ 복구온_예약실행_등록.ps1 이 2026-08-06 사고와 -ErrorAction Stop 처리를 갖고 있다"
    "(이번 수정이 베낀 원본)")
chk("2026-08-06" in SIBLING2_SRC and "-ErrorAction Stop" in SIBLING2_SRC,
    "★ 복구온_외부공개_등록.ps1 도 같은 처리를 갖고 있다(둘 다 그대로 — 오수정 방지)")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — PowerShell 파서로 전체 파일 문법 검증(진짜 파싱)")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round559_")
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
    chk(False, "★★★ 라운드559 [3] PowerShell 파서 검증", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[4] 실행 — Register-BokguonTask 를 가짜 cmdlet 아래 실제로 3가지 시나리오로 돌린다")
#      (실제 스케줄러에는 전혀 닿지 않는다 — 같은 이름의 함수가 스코프 안에서 cmdlet을 가린다)
# ──────────────────────────────────────────────────────────────
FAKES_PREAMBLE = r'''
#  ⚠ [라운드559] round296 이 겪은 건 *입력*(BOM 없는 .ps1 을 cp949 로 오독)이었는데
#    이건 *출력* 쪽 짝이다 — Windows PowerShell 5.1 은 리다이렉트된 stdout 에 한글을
#    쓸 때도 시스템 코드페이지(cp949)를 쓴다. Python 이 encoding="utf-8" 로 읽으면
#    Warn/Ok 의 한글 메시지가 깨진다(실측: 처음 돌렸을 때 실제로 깨졌다). 콘솔
#    출력 인코딩을 UTF-8 로 못박아 왕복이 실제로 일치하게 만든다.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Ok($m)   { Write-Output "OK:$m" }
function Warn($m) { Write-Output "WARN:$m" }

function Register-ScheduledTask {
    param($TaskName, $Action, $Trigger, $RunLevel, $Description, $ErrorAction)
    if ($env:FAKE_REGISTER -eq "throw") {
        throw "Access is denied (simulated CIM failure)"
    } elseif ($env:FAKE_REGISTER -eq "silent_fail") {
        #  실제 2026-08-06 사고 재현: 호출자가 -ErrorAction Stop 을 줘도 그걸
        #  무시하고 Continue 로 오류를 내면서 정상 반환한다(CIM 오류가 승격되지
        #  않는 실측 현상의 최소 재현).
        Write-Error "Access is denied (simulated CIM failure)" -ErrorAction Continue
        return
    }
    return
}

function Get-ScheduledTask {
    param($TaskName, $ErrorAction)
    if ($env:FAKE_TASK_EXISTS -eq "1") {
        return [pscustomobject]@{ TaskName = $TaskName }
    }
    return $null
}
'''

def run_scenario(register_behavior, task_exists, func_src):
    """func_src(Register-BokguonTask 또는 옛 패턴)를 가짜 cmdlet 아래서 실행하고
    표준출력을 돌려준다."""
    script = os.path.join(_tmpdir, f"scenario_{register_behavior}_{task_exists}_{abs(hash(func_src))}.ps1")
    body = (FAKES_PREAMBLE + "\n" + func_src +
            "\nRegister-BokguonTaskOrOld 'TestTask' 'act' 'trig' 'DESC' 'REGISTERED-OK'\n")
    io.open(script, "w", encoding="utf-8-sig").write(body)
    env = dict(os.environ)
    env["FAKE_REGISTER"] = register_behavior
    env["FAKE_TASK_EXISTS"] = task_exists
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, env=env)
    return r.stdout


try:
    # 실제 소스에서 뽑은 함수를 시나리오마다 호출할 수 있게 이름만 통일한 래퍼로 감싼다.
    NEW_FUNC = FUNC_SRC.replace("function Register-BokguonTask(",
                                 "function Register-BokguonTaskOrOld(", 1)
    chk(NEW_FUNC != FUNC_SRC, "함수 이름 치환이 실제로 일어났다(추출 검증)")

    # 시나리오 A: 등록 성공 + 재조회에서 실제로 발견됨 → OK 만 나오고 WARN 은 없어야 한다
    out_a = run_scenario("success", "1", NEW_FUNC)
    chk("OK:REGISTERED-OK" in out_a and "WARN:" not in out_a,
        "★★★ [새 코드] 등록 성공+재조회 성공 → OK 만 찍고 WARN 은 없다", repr(out_a))

    # 시나리오 B: Register-ScheduledTask 가 진짜로 throw → WARN, OK 는 없어야 한다
    out_b = run_scenario("throw", "0", NEW_FUNC)
    chk("WARN:" in out_b and "Access is denied" in out_b and "OK:REGISTERED-OK" not in out_b,
        "★★★★ [새 코드] Register-ScheduledTask 가 예외를 던지면 WARN 만 찍고 "
        "실패를 성공이라 말하지 않는다", repr(out_b))

    # 시나리오 C: 2026-08-06 실제 사고 재현 — 호출은 조용히 '성공'처럼 반환하지만
    # 실제로는 등록되지 않음(재조회 실패) → 재조회 안전망이 잡아야 한다
    out_c = run_scenario("silent_fail", "0", NEW_FUNC)
    chk("WARN:" in out_c and "조회되지 않습니다" in out_c and "OK:REGISTERED-OK" not in out_c,
        "★★★★★ [새 코드] 등록 호출은 조용히 넘어가도(2026-08-06 실제 사고 재현) 재조회가 "
        "빈손이면 OK 를 찍지 않는다 — 이번 라운드가 고친 핵심 결함", repr(out_c))

    # ── 되돌리기 증명: 실제 파일은 손대지 않고, 옛(수정 전) 패턴을 메모리 문자열로만
    #    재구성해 같은 가짜 아래 돌려 시나리오 C 에서 거짓 성공을 찍었었음을 보인다.
    OLD_FUNC = (
        "function Register-BokguonTaskOrOld($TaskName, $Action, $Trigger, $Description, $OkMessage) {\n"
        "    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger "
        "-RunLevel Highest -Description $Description | Out-Null\n"
        "    Ok $OkMessage\n"
        "}\n"
    )
    old_out_c = run_scenario("silent_fail", "0", OLD_FUNC)
    chk("OK:REGISTERED-OK" in old_out_c,
        "★★★★★ [되돌리기 증명] 옛 패턴은 같은 조건(2026-08-06 재현)에서 실제로 "
        "'REGISTERED-OK' 를 거짓으로 찍었다 — 이게 실제로 있던 결함이었음을 인과로 확인",
        repr(old_out_c))
    old_out_b = run_scenario("throw", "0", OLD_FUNC)
    chk("OK:REGISTERED-OK" not in old_out_b,
        "★ [되돌리기 증명 대조군] 옛 패턴도 진짜 throw 앞에서는(try/catch 자체가 없어 "
        "스크립트가 죽으므로) 거짓 OK 를 찍지 못한다 — 결함은 시나리오 C 조건에서만 "
        "재현되는 게 맞다(과잉일반화 방지)", repr(old_out_b))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 라운드559 [4] 시나리오 실행", f"{type(e).__name__} {e}")
finally:
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
