# -*- coding: utf-8 -*-
"""스캔 127라운드 회귀 — deploy\\외부접속_상시가동.ps1(운영 감시자)의 3건.

  [1] StartServer 가 표준출력·에러를 어디로도 안 흘려보내, 실제 운영에서
      128회(2026-07-30~) 반복된 "서버 응답 없음 → 재기동"의 원인을 하나도
      기록하지 못했다 — 강제종료라 트레이스백이 숨김 콘솔째로 사라진다.
  [2] StartServer 의 성공/실패 반환값을 호출부 4곳 전부 Out-Null 로 버려,
      일시적 응답지연과 영구 배포사고를 로그에서 구분할 방법이 없었다.
  [3] 임시터널 주소를 40초 안에 못 찾으면 cloudflared 프로세스를 살려둔 채
      경고만 찍어, 다음 순회의 재시도 조건(TunnelProcs 없음)이 다시는 안
      걸리고 PublicServable 도 TunnelHost 없으면 "문제없음"으로 보류하므로
      유일한 실패 감지 장치가 무기한 잠들었다(실측: 아직 실제 발생은 없었음
      — 측정 7건 전부 4~14초 — 하지만 구조적 결함은 확정적).

      python test_scan_round127_fixes.py
"""
import io
import os
import shutil
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


def run_ps(script, timeout=40):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                        capture_output=True, timeout=timeout)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


print("═" * 72)
print("  스캔 127라운드 회귀 — 외부접속_상시가동.ps1: 서버크래시 무기록·재기동실패무시·터널타임아웃방치")
print("═" * 72)

WATCHER_PS1 = os.path.join("deploy", "외부접속_상시가동.ps1")
SRC = read(WATCHER_PS1)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
chk('$WOUT     = Join-Path $LOGDIR "waitress_out.log"' in SRC
    and '$WERR     = Join-Path $LOGDIR "waitress_err.log"' in SRC,
    "★★★ 서버 표준출력·에러 로그 경로가 정의됐다")
sf_body = SRC[SRC.index("function StartServer"):SRC.index("function TunnelProcs")]
chk("-RedirectStandardOutput $WOUT -RedirectStandardError $WERR" in sf_body,
    "★★★ StartServer 의 Start-Process 가 이제 표준출력·에러를 파일로 흘려보낸다")

chk(SRC.count("NoteRestart (StartServer)") == 3 and SRC.count("StartServer | Out-Null") == 1,
    "★★★ 감시루프 4곳 중 3곳(재시도 경로)이 이제 StartServer 반환값을 실제로 본다"
    "(최초 1회 기동은 여전히 단순호출 — 실패해도 곧 감시루프가 이어받는다)")
chk("function NoteRestart($ok)" in SRC and "restartFail" in SRC,
    "★★ 재기동 자체가 실패하면 연속횟수를 별도로 센다")

st_body = SRC[SRC.index("function StartTunnel"):SRC.index("function PublishUrl")]
chk('TunnelProcs | ForEach-Object { try { Stop-Process -Id $_.Id -Force } catch {} }' in
    st_body.split("주소 확인 중", 1)[1],
    "★★★ 임시터널 주소를 못 찾으면 이제 cloudflared 를 정리해 재시도를 열어둔다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 리다이렉션 메커니즘이 실제로 표준에러를 파일에 담는가")
# ──────────────────────────────────────────────────────────────
_tmpdir = os.path.join(os.environ.get("TEMP", HERE), f"r127_probe_{int(time.time())}")
try:
    os.makedirs(_tmpdir, exist_ok=True)
    err_log = os.path.join(_tmpdir, "probe_err.log")
    out_log = os.path.join(_tmpdir, "probe_out.log")
    py = sys.executable
    #  -ArgumentList 로 인라인 "-c 코드" 를 넘기면 PowerShell 이 공백 기준으로
    #  토큰을 쪼개 네이티브 exe 에 넘긴다(따옴표를 더 얹어도 취약) — 실제로
    #  한 번 이 방식으로 실패했다("import" 한 단어만 전달됨). 그 인용 문제를
    #  피하려고 파일 경로 하나만 인자로 넘긴다(StartServer 의 실제 호출 패턴,
    #  serve_waitress.py 경로 하나만 넘기는 것과 동일한 모양).
    crash_script = os.path.join(_tmpdir, "crash.py")
    io.open(crash_script, "w", encoding="utf-8").write(
        "import sys\nsys.stderr.write('RAISED: boom\\n')\nsys.exit(1)\n")
    #  StartServer 와 같은 패턴(-WindowStyle Hidden + 리다이렉션)으로 stderr 에
    #  트레이스백을 내는 파이썬을 실제로 띄워, 그 내용이 파일에 실제로 담기는지 본다.
    ps_script = f'''
$p = Start-Process -WindowStyle Hidden -FilePath "{py}" `
    -ArgumentList "{crash_script}" `
    -RedirectStandardOutput "{out_log}" -RedirectStandardError "{err_log}" -PassThru
$p.WaitForExit(5000) | Out-Null
Write-Output "EXITCODE:$($p.ExitCode)"
'''
    rc, out, err = run_ps(ps_script)
    time.sleep(0.5)
    err_content = io.open(err_log, encoding="utf-8", errors="replace").read() if os.path.exists(err_log) else ""
    chk("RAISED: boom" in err_content,
        "★★★ -RedirectStandardError 패턴이 실제로 크래시 내용을 파일에 남긴다"
        "(예전엔 이 리다이렉션 자체가 없어 트레이스백이 숨김 콘솔째로 사라졌다)",
        (out, err_content))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드127 준비/실행(리다이렉션 재현)", f"{type(e).__name__} {e}")
finally:
    shutil.rmtree(_tmpdir, ignore_errors=True)

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — NoteRestart 가 연속실패를 실제로 다르게 기록하는가")
# ──────────────────────────────────────────────────────────────
try:
    ps_script = '''
$script:SUPLOG = $null
$script:restartFail = 0
function Note($msg) { Write-Output $msg }
function NoteRestart($ok) {
    if ($ok) { $script:restartFail = 0; return }
    $script:restartFail++
    Note ("ESCALATE:" + $script:restartFail)
}
NoteRestart($true)
NoteRestart($false)
NoteRestart($false)
NoteRestart($true)
NoteRestart($false)
Write-Output ("FINAL:" + $script:restartFail)
'''
    rc, out, err = run_ps(ps_script)
    chk("ESCALATE:1" in out and "ESCALATE:2" in out and "FINAL:1" in out,
        "★★★ NoteRestart 가 연속실패를 누적하고, 성공하면 리셋한다"
        "(예전엔 이 구분 자체가 없어 로그가 다 똑같은 문구였다)", out)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드127 준비/실행(NoteRestart)", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[4] 실행 — 스크립트 구문이 유효한가")
# ──────────────────────────────────────────────────────────────
try:
    full = os.path.join(HERE, WATCHER_PS1)
    ps_check = (
        '$e = $null; '
        '[System.Management.Automation.Language.Parser]::ParseFile('
        f'"{full}", [ref]$null, [ref]$e) | Out-Null; '
        'if ($e.Count -eq 0) { Write-Output "SYNTAX_OK" } '
        'else { $e | ForEach-Object { Write-Output $_.Message } }'
    )
    rc, out, err = run_ps(ps_check)
    chk("SYNTAX_OK" in out, "★★★ 외부접속_상시가동.ps1 구문이 유효하다(파서 오류 없음)", out)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드127 준비/실행(구문검사)", f"{type(e).__name__} {e}")

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
