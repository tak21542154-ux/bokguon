# -*- coding: utf-8 -*-
"""스캔 128라운드 회귀 — deploy\\외부접속_상시가동.ps1(운영 감시자)의 2건.

  배경: 128라운드 조사에서 실운영 확인 결과, 이 감시자 프로세스(PID 1704)가
  2026-08-21 부터 6일째 구버전 코드로 떠 있었다(PowerShell -File 스크립트는
  최초 1회만 파싱하므로, 디스크 수정은 프로세스를 재시작해야 반영된다) —
  즉 라운드126·127의 수정도 이 재시작 전까지는 전부 죽은 코드였다. 그 김에
  실측(logs/supervisor.log)으로 확인한 128회 재기동이 전부 "(1 회)" 단발
  패턴이고 같은 구간 bokguon.log 에 트레이스백이 전혀 없다는 것도 확인했다
  — 서버가 실제로 죽은 게 아니라 감시자가 단발 지연을 죽음으로 오판했을
  가능성이 높다.

  [1] ServerAlive 의 healthz 타임아웃(6초)이 db.py 의 BOKGUON_SQLITE_BUSY_MS
      (기본 8000ms)보다 짧다 — 쓰기 경합으로 8초까지 대기 중인 스레드가
      8개 스레드풀을 다 차지하면, 정상적으로 도는 요청인데도 "죽었다"로
      오판할 여유가 구조적으로 없었다.
  [2] $fail 카운터를 세기만 하고 문턱값 없이 1회부터 바로 강제종료+재기동
      했다 — 재시도 없이 단발 지연만으로 죽였다는 뜻.

      python test_scan_round128_fixes.py
"""
import io
import os
import re
import subprocess
import sys

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


print("=" * 72)
print("  스캔 128라운드 회귀 — 외부접속_상시가동.ps1: healthz 타임아웃 여유부족·재기동 디바운스없음")
print("=" * 72)

WATCHER_PS1 = os.path.join("deploy", "외부접속_상시가동.ps1")
SRC = read(WATCHER_PS1)
DB_SRC = read("db.py")

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
sa_body = SRC[SRC.index("function ServerAlive"):SRC.index("function PublicServable")]
chk("-TimeoutSec 10" in sa_body,
    "★★★ ServerAlive 의 healthz 타임아웃이 10초로 늘었다(ServerAlive 함수 안에서만)")

m = re.search(r'BUSY_TIMEOUT_MS\s*=\s*int\(os\.environ\.get\("BOKGUON_SQLITE_BUSY_MS",\s*"(\d+)"\)\)', DB_SRC)
chk(m is not None, "★ db.py 에서 BUSY_TIMEOUT_MS 기본값을 읽었다", "패턴을 못 찾음 — db.py 가 바뀌었는지 확인")
if m:
    busy_ms = int(m.group(1))
    chk(10 * 1000 > busy_ms,
        "★★★ 새 healthz 타임아웃(10초)이 BUSY_TIMEOUT_MS 보다 여유 있게 크다",
        f"busy_ms={busy_ms}")

pub_body = SRC[SRC.index("function PublicServable"):SRC.index("function StartServer")]
chk("-TimeoutSec 6" in pub_body,
    "★ PublicServable 의 타임아웃은 그대로 6초다(의도적 — 타임아웃은 이미 return $true 로 무시됨)")

loop_body = SRC[SRC.index("if (-not (ServerAlive))"):SRC.index("#  ★ 서버는 살아 있는데")]
chk("if ($fail -lt 2)" in loop_body and loop_body.count("continue") >= 2,
    "★★★ 재기동 전 최소 2회 연속실패를 요구하는 디바운스가 들어갔다")
chk(loop_body.index("if ($fail -lt 2)") < loop_body.index("NoteRestart (StartServer)"),
    "★★★ 디바운스 검사가 실제 재기동 호출보다 먼저 실행되는 순서다")

# ============================================================
print("\n[2] 실행 — 디바운스 로직이 1회 실패는 넘기고 2회째부터 재기동을 부르는가")
# ------------------------------------------------------------
try:
    # 실제 소스 조각(loop_body)을 그대로 가져다 for 루프 안에 넣고 실행한다
    # (재구현이 아니라 실제 텍스트를 실행 — continue 는 for 루프 안에서만 유효).
    harness = f'''
function Note($msg) {{ Write-Output ("NOTE:" + $msg) }}
function ServerAlive {{ return $false }}
function NoteRestart($ok) {{ Write-Output ("RESTARTCALL:" + $ok) }}
function StartServer {{ Write-Output "STARTSERVER_INVOKED"; return $true }}
$fail = 0
for ($iter = 1; $iter -le 3; $iter++) {{
    Write-Output ("ITER:" + $iter)
{loop_body}
}}
'''
    rc, out, err = run_ps(harness)
    lines = out.splitlines()

    def section(n):
        try:
            start = lines.index(f"ITER:{n}") + 1
            end = lines.index(f"ITER:{n + 1}") if f"ITER:{n + 1}" in lines else len(lines)
            return lines[start:end]
        except ValueError:
            return []

    iter1, iter2, iter3 = section(1), section(2), section(3)
    chk(not any("STARTSERVER_INVOKED" in l for l in iter1),
        "★★★ 1회째 실패에서는 재기동을 안 부른다", out)
    chk(any("STARTSERVER_INVOKED" in l for l in iter2),
        "★★★ 2회 연속실패째에 비로소 재기동을 부른다", out)
    chk(any("STARTSERVER_INVOKED" in l for l in iter3),
        "★ 3회째(계속 실패 중)도 매번 재기동을 부른다", out)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드128 준비/실행(디바운스 하네스)", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — 스크립트 구문이 유효한가")
# ------------------------------------------------------------
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
    chk(False, "★★★ 라운드128 준비/실행(구문검사)", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
