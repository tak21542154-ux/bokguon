# -*- coding: utf-8 -*-
"""스캔 205라운드 회귀 — admin.js 의 세 형제 액션 함수(defectAct·dispatchSweep·
leadAct)가 try/catch 없이 api() 를 호출해, 서버가 오류(403·409·500 등)를
주면 unhandled rejection 으로 끝나던 결함.

  형제(appAct, 89라운드 수정)는 "콘솔의 다른 변경 동작은 전부 try/catch +
  toast 로 감싸져 있다"고 스스로 주석에 적어 뒀지만 그 단언은 틀렸다 — 이
  세 함수가 빠져 있었다. 특히 defectAct·dispatchSweep 이 여는 두 화면(하자·
  A/S 관리, 현장 출동 수배)은 applyRoleMenus() 의 등급게이트
  (admins·insurers·set 만 제한)에 없어 하위관리자도 그대로 열 수 있는데,
  두 액션의 서버 API는 require_role("중간관리자") 라 하위관리자가 누르면
  100% 재현되는 403 무응답이었다(leadAct 는 서버쪽 등급제한은 없어 트리거는
  네트워크·DB 일시오류 등 더 좁지만 같은 유형의 결함이다).

  각 함수를 원본 그대로 뽑아 Node.js 로 실행해, api() 가 거부(reject)될 때
  (a) 함수 자체는 예외 없이 정상 종료하고 (b) toast 로 실패를 알리며
  (c) closeModal/성공후처리(refreshBadges·VIEWS.*)는 실행되지 않는지,
  반대로 api() 가 성공하면 기존과 동일하게 전부 실행되는지 검증한다.

      python test_scan_round205_fixes.py
"""
import io
import json
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


JS_SRC = read("static/admin.js")

print("=" * 72)
print("  스캔 205라운드 회귀 — admin.js 형제 액션 3곳 try/catch 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
def extract(start_marker, end_marker):
    i0 = JS_SRC.index(start_marker)
    i1 = JS_SRC.index(end_marker, i0)
    return JS_SRC[i0:i1]

DEFECT_ACT = extract("async function defectAct(id, status){", "\n// ── AI 사진 검수")
DISPATCH_SWEEP = extract("async function dispatchSweep(){", "\n// ── 수배 개시")
LEAD_ACT = extract("async function leadAct(id, status){", "\n// ── 입점 신청함")

chk("try{\n    await api('PATCH','/api/defects/'+id, body);\n  }catch(e){" in DEFECT_ACT,
    "★★★★ defectAct 가 api() 호출을 try/catch 로 감쌌다")
chk("try{\n    const r = await api('POST','/api/admin/dispatch-sweep',{});" in DISPATCH_SWEEP,
    "★★★★ dispatchSweep 이 api() 호출을 try/catch 로 감쌌다")
chk("try{\n    await api('PATCH','/api/leads/'+id, {status, note});\n  }catch(e){" in LEAD_ACT,
    "★★★★ leadAct 가 api() 호출을 try/catch 로 감쌌다")

# ============================================================
print("\n[2] 실행(Node.js) — api() 가 실패해도 예외 없이 끝나고, 성공후처리는 안 한다")
# ------------------------------------------------------------
JS_HARNESS = r"""
const vm = require('vm');
const fs = require('fs');

function baseSandbox() {
  const calls = { toast: [], closeModal: 0, refreshBadges: 0, views: [] };
  const sandbox = {
    console: console,
    $: function () { return null; },
    window: {},
    document: { querySelector: function () { return null; } },
    confirm: function () { return true; },
    toast: function (msg) { calls.toast.push(msg); },
    closeModal: function () { calls.closeModal++; },
    refreshBadges: function () { calls.refreshBadges++; },
    VIEWS: {
      defects: function () { calls.views.push('defects'); },
      dispatch: function () { calls.views.push('dispatch'); },
      leads: function () { calls.views.push('leads'); },
    },
  };
  sandbox.window = sandbox;
  return { sandbox, calls };
}

async function runOne(fnSrc, fnName, args, apiShouldFail) {
  const { sandbox, calls } = baseSandbox();
  sandbox.api = apiShouldFail
    ? async function () { throw new Error('R205 검증용 403(중간관리자 이상만 가능)'); }
    : async function () { return {}; };
  vm.createContext(sandbox);
  vm.runInContext(fnSrc + '\nglobalThis.__fn = ' + fnName + ';', sandbox, { filename: fnName + '.js' });
  let threw = null;
  try {
    await sandbox.__fn.apply(null, args);
  } catch (e) {
    threw = String(e && e.message || e);
  }
  return { threw: threw, calls: calls };
}

(async function () {
  const out = {};
  const defectSrc = fs.readFileSync(process.argv[2], 'utf8');
  const dispatchSrc = fs.readFileSync(process.argv[3], 'utf8');
  const leadSrc = fs.readFileSync(process.argv[4], 'utf8');

  out.defect_fail = await runOne(defectSrc, 'defectAct', [1, '완료'], true);
  out.defect_ok = await runOne(defectSrc, 'defectAct', [1, '완료'], false);
  out.dispatch_fail = await runOne(dispatchSrc, 'dispatchSweep', [], true);
  out.dispatch_ok = await runOne(dispatchSrc, 'dispatchSweep', [], false);
  out.lead_fail = await runOne(leadSrc, 'leadAct', [1, '승인'], true);
  out.lead_ok = await runOne(leadSrc, 'leadAct', [1, '승인'], false);

  console.log(JSON.stringify(out));
})().catch(function (e) { console.error('HARNESS_ERROR: ' + (e && e.stack || e)); process.exit(1); });
"""

_tmpdir = tempfile.mkdtemp(prefix="round205_")
_harness = os.path.join(_tmpdir, "harness.js")
_defect_f = os.path.join(_tmpdir, "defect.js")
_dispatch_f = os.path.join(_tmpdir, "dispatch.js")
_lead_f = os.path.join(_tmpdir, "lead.js")
with io.open(_harness, "w", encoding="utf-8") as f:
    f.write(JS_HARNESS)
with io.open(_defect_f, "w", encoding="utf-8") as f:
    f.write(DEFECT_ACT)
with io.open(_dispatch_f, "w", encoding="utf-8") as f:
    f.write(DISPATCH_SWEEP)
with io.open(_lead_f, "w", encoding="utf-8") as f:
    f.write(LEAD_ACT)

try:
    result = subprocess.run(["node", _harness, _defect_f, _dispatch_f, _lead_f],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=30)
    chk(result.returncode == 0,
        "★★★ Node 하네스가 예외 없이 끝까지 실행됐다", result.stderr.strip())
    out = None
    if result.returncode == 0:
        try:
            out = json.loads(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as e:
            chk(False, "★★★ 하네스 출력(JSON) 파싱", f"{e}: {result.stdout!r}")

    if out is not None:
        for key, label in (("defect", "defectAct"), ("dispatch", "dispatchSweep"), ("lead", "leadAct")):
            fail = out[f"{key}_fail"]
            ok = out[f"{key}_ok"]
            chk(fail["threw"] is None,
                f"★★★★ {label}: api() 가 실패해도 함수 자체는 예외를 던지지 않는다"
                "(고치기 전엔 unhandled rejection 이었다)", fail["threw"])
            chk(len(fail["calls"]["toast"]) >= 1,
                f"★★★★ {label}: 실패하면 toast 로 사용자에게 알린다"
                "(고치기 전엔 아무 반응도 없었다)", fail["calls"])
            #  ⚠⚠ [라운드501] 이 세 함수(defect·dispatch·lead)는 이제 형제
            #    (settleVoid 등, 라운드481·486·500이 세운 "catch도 성공 분기와
            #    같이 정리한다" 원칙)를 물려받아, 실패해도 화면을 성공 분기와
            #    같은 방식으로 정리한다 — 205라운드 당시엔 그 원칙이 아직
            #    없어 "실패하면 아무것도 건드리지 않는다"가 맞는 기대값이었지만
            #    이제는 반대가 맞다(반쪽 성공이 아니라 "다른 관리자가 먼저
            #    바꾼 옛 화면"을 새로고침하는 것이 목적). dispatchSweep은
            #    성공 분기도 애초에 closeModal을 안 하는 목록화면 버튼이라
            #    그 하나만 0을 유지한다.
            _expect_close = 0 if key == "dispatch" else 1
            chk(fail["calls"]["closeModal"] == _expect_close and fail["calls"]["views"] != [],
                f"★★★★★ {label}: 실패해도 성공 분기와 같은 방식으로 화면을 정리한다"
                "(다른 관리자가 먼저 처리한 옛 화면을 계속 보여주지 않음)", fail["calls"])
            chk(ok["threw"] is None and len(ok["calls"]["views"]) == 1,
                f"★ {label}: 정상 성공 경로는 그대로 동작한다(회귀 아님)", ok["calls"])
except FileNotFoundError:
    chk(False, "★★★ node 실행파일을 못 찾음", "node --version 확인 필요")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
