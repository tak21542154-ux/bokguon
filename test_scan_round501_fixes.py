# -*- coding: utf-8 -*-
"""스캔 501라운드 회귀 — defectAct()(하자관리)·dispatchSweep()(출동수배
기한점검)·leadAct()(도입 문의) 세 함수의 catch 분기가 형제(settleVoid 등,
라운드481·486·500이 세운 "catch도 성공 분기와 같이 정리한다" 원칙)를
못 물려받아 toast만 하고 화면(모달·목록)을 방치하던 결함 — 481→486→500에
이은 네 번째 클러스터. 세 함수는 라운드205가 "세 형제 액션 함수"로 함께
묶어 try/catch를 붙인 그룹이라 이번에도 함께 고친다.

관리자 A·B가 같은 하자 상세 모달을 동시에 열어둔 상태에서 B가 먼저
상태를 바꾸면, 서버(app.py DEFECT_BAD_TRANSITION 409)가 A의 다음 액션을
막지만 A의 모달은 옛 상태로 계속 열려 있는다.

라운드205는 이 세 함수에 try/catch **자체**만 추가했을 뿐(unhandled
rejection 방지) — catch가 성공 분기와 같은 정리를 하는 481+ 원칙은
그 당시 아직 존재하지 않아 못 물려받았다. round205 자신의 회귀테스트가
"실패하면 화면을 아무것도 안 건드린다"를 리터럴로 검증하고 있어(그
시절엔 맞는 기대값), 이번 수정으로 그 검증도 함께 갱신했다(같은 파일
아래 별도 조치 — round205 테스트 자체는 여기서 건드리지 않는다).
"""
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(c, n, d=""):
    (PASS if c else FAIL).append((n, d))
    print(("  [OK]   " if c else "  [FAIL] ") + n + ("" if c else f"   {d}"))


print("=" * 72)
print("  스캔 501라운드 회귀 — 하자관리·출동수배·도입문의 catch 분기 화면정리 누락")
print("=" * 72)

JS_PATH = os.path.join(HERE, "static", "admin.js")
JS_SRC = io.open(JS_PATH, encoding="utf-8").read()


def fn_body(src, start_marker):
    """중괄호 짝을 실제로 세어 함수 끝을 찾는다(라운드500이 확립한 방식 —
    '다음 함수 선언 전까지'로 찾으면 화살표함수 등 다른 선언 스타일이
    사이에 끼어 있을 때 훨씬 뒤의 무관한 함수까지 통째로 삼킬 수 있다)."""
    i = src.index(start_marker)
    depth = 0
    started = False
    j = i
    while j < len(src):
        ch = src[j]
        if ch == "{":
            depth += 1
            started = True
        elif ch == "}":
            depth -= 1
            if started and depth == 0:
                return src[i:j + 1]
        j += 1
    raise ValueError("no matching close brace")


DA_MARKER = "async function defectAct(id, status){"
DS_MARKER = "async function dispatchSweep(){"
LA_MARKER = "async function leadAct(id, status){"
da_body = fn_body(JS_SRC, DA_MARKER)
ds_body = fn_body(JS_SRC, DS_MARKER)
la_body = fn_body(JS_SRC, LA_MARKER)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 세 함수 catch가 성공 분기와 같은 정리를 한다")
# ──────────────────────────────────────────────────────────────
chk(JS_SRC.count(da_body) == 1, "defectAct() 함수 본문이 소스에 유일하게 추출된다")
chk(JS_SRC.count(ds_body) == 1, "dispatchSweep() 함수 본문이 소스에 유일하게 추출된다")
chk(JS_SRC.count(la_body) == 1, "leadAct() 함수 본문이 소스에 유일하게 추출된다")

NEW_DA_CATCH = ("toast(e.message || '처리하지 못했습니다.'); "
                "closeModal(); refreshBadges(); VIEWS.defects(); return;")
chk(NEW_DA_CATCH in da_body,
    "defectAct() catch가 성공 분기와 같은 정리(closeModal·refreshBadges·VIEWS.defects)를 한다")

NEW_DS_CATCH = "toast(e.message || '처리하지 못했습니다.'); VIEWS.dispatch();"
chk(NEW_DS_CATCH in ds_body,
    "dispatchSweep() catch가 성공 분기와 같은 정리(VIEWS.dispatch)를 한다")

NEW_LA_CATCH = ("toast(e.message || '처리하지 못했습니다.'); "
                "closeModal(); refreshBadges(); VIEWS.leads(); return;")
chk(NEW_LA_CATCH in la_body,
    "leadAct() catch가 성공 분기와 같은 정리(closeModal·refreshBadges·VIEWS.leads)를 한다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 Node 실행 — 두 함수를 진짜 호출(성공/실패 각각)")
# ──────────────────────────────────────────────────────────────
HARNESS_HEAD = r"""
const calls = [];
global.toast = (m) => calls.push('toast:' + String(m).slice(0,30));
global.closeModal = () => calls.push('closeModal');
global.refreshBadges = () => calls.push('refreshBadges');
global.VIEWS = { defects: () => calls.push('VIEWS.defects'), dispatch: () => calls.push('VIEWS.dispatch'), leads: () => calls.push('VIEWS.leads') };
global.document = { querySelector: () => null };
global.$ = (s) => null;
global.window = { _defects: [] };
global.confirm = () => true;
let SHOULD_FAIL = process.env.R501_FAIL === '1';
global.api = async (method, url, body) => {
  if (SHOULD_FAIL) { const e = new Error("'확인중' 에서 '재시공배정' 로는 바꿀 수 없습니다."); e.code = 'DEFECT_BAD_TRANSITION'; throw e; }
  return { expired: 0, reopened: 0, gaveup: 0 };
};
"""
HARNESS_TAIL_DA = r"""
(async () => {
  await defectAct(1, '재시공배정');
  console.log(JSON.stringify(calls));
})();
"""
HARNESS_TAIL_DS = r"""
(async () => {
  await dispatchSweep();
  console.log(JSON.stringify(calls));
})();
"""
HARNESS_TAIL_LA = r"""
(async () => {
  await leadAct(1, '승인');
  console.log(JSON.stringify(calls));
})();
"""


def run_node(body, tail, fail):
    src = HARNESS_HEAD + "\n" + body + "\n" + tail
    path = os.path.join(HERE, "_r501_node_tmp.js")
    io.open(path, "w", encoding="utf-8").write(src)
    env = dict(os.environ)
    env["R501_FAIL"] = "1" if fail else "0"
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True,
                            encoding="utf-8", timeout=20, env=env)
        if r.returncode != 0:
            raise RuntimeError(f"node 실행 실패: {r.stdout}\n{r.stderr}")
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


try:
    da_ok = run_node(da_body, HARNESS_TAIL_DA, fail=False)
    chk("VIEWS.defects" in da_ok and "closeModal" in da_ok, "defectAct() 정상 처리 시 모달을 닫고 목록을 새로고침한다(대조군)", da_ok)

    da_fail = run_node(da_body, HARNESS_TAIL_DA, fail=True)
    chk(any(c.startswith("toast:") for c in da_fail), "defectAct() 서버 오류 시 toast는 뜬다", da_fail)
    chk("closeModal" in da_fail and "refreshBadges" in da_fail and "VIEWS.defects" in da_fail,
        "★★★★★ 새 코드: defectAct() 서버 오류(동시편집 충돌 등)에도 모달을 닫고 목록을 "
        "새로고침한다(다른 관리자가 먼저 바꾼 옛 상태 모달이 안 남는다)", da_fail)

    ds_ok = run_node(ds_body, HARNESS_TAIL_DS, fail=False)
    chk("VIEWS.dispatch" in ds_ok, "dispatchSweep() 정상 처리 시 화면을 새로고침한다(대조군)", ds_ok)

    ds_fail = run_node(ds_body, HARNESS_TAIL_DS, fail=True)
    chk("VIEWS.dispatch" in ds_fail,
        "★★★★★ 새 코드: dispatchSweep() 서버 오류(권한없음 등)에도 화면을 새로고침한다", ds_fail)

    la_ok = run_node(la_body, HARNESS_TAIL_LA, fail=False)
    chk("VIEWS.leads" in la_ok and "closeModal" in la_ok, "leadAct() 정상 처리 시 모달을 닫고 목록을 새로고침한다(대조군)", la_ok)

    la_fail = run_node(la_body, HARNESS_TAIL_LA, fail=True)
    chk("closeModal" in la_fail and "refreshBadges" in la_fail and "VIEWS.leads" in la_fail,
        "★★★★★ 새 코드: leadAct() 서버 오류에도 모달을 닫고 목록을 새로고침한다", la_fail)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 되돌림-증명 — 옛 코드(성공 분기만 정리)는 catch에서 화면을 방치한다")
    # ──────────────────────────────────────────────────────────
    OLD_DA_CATCH = "catch(e){ toast(e.message || '처리하지 못했습니다.'); return; }"
    reverted_da = da_body.replace(
        "catch(e){\n    //  ⚠⚠ [라운드501] 형제(settleVoid 등, 라운드481·486·500)가 이미 세운\n    //    원칙 — 성공 분기(바로 아래 closeModal·refreshBadges·VIEWS.defects)\n    //    만 화면을 정리하면, 동시에 다른 관리자가 먼저 상태를 바꿔 여기가\n    //    막히는 흔한 경우(app.py DEFECT_BAD_TRANSITION 409)에 이 모달만\n    //    옛 상태로 계속 열려 있는다. catch도 성공 분기와 같이 정리한다.\n    " + NEW_DA_CATCH + "\n  }",
        OLD_DA_CATCH)
    assert reverted_da != da_body, "defectAct 되돌림 치환이 실제로 안 먹었다"
    da_old_fail = run_node(reverted_da, HARNESS_TAIL_DA, fail=True)
    chk("closeModal" not in da_old_fail and "VIEWS.defects" not in da_old_fail,
        "★★★★★ 옛 코드(되돌림): defectAct() 서버 오류 시 toast만 뜨고 모달·목록은 방치된다 — "
        "이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", da_old_fail)

    OLD_DS_CATCH = "catch(e){ toast(e.message || '처리하지 못했습니다.'); }"
    reverted_ds = ds_body.replace(
        "catch(e){\n    //  ⚠⚠ [라운드501] 형제(settleVoid 등, 라운드481·486·500) 참조 — catch도\n    //    성공 분기와 같이 정리한다(목록 화면 버튼이라 closeModal은 불필요).\n    " + NEW_DS_CATCH + "\n  }",
        OLD_DS_CATCH)
    assert reverted_ds != ds_body, "dispatchSweep 되돌림 치환이 실제로 안 먹었다"
    ds_old_fail = run_node(reverted_ds, HARNESS_TAIL_DS, fail=True)
    chk("VIEWS.dispatch" not in ds_old_fail,
        "★★★★★ 옛 코드(되돌림): dispatchSweep() 도 서버 오류 시 화면을 방치한다", ds_old_fail)

    OLD_LA_CATCH = "catch(e){ toast(e.message || '처리하지 못했습니다.'); return; }"
    reverted_la = la_body.replace(
        "catch(e){\n    //  ⚠⚠ [라운드501] 형제(defectAct·settleVoid 등, 라운드481·486·500) 참조\n    //    — catch도 성공 분기(바로 아래)와 같이 정리한다.\n    " + NEW_LA_CATCH + "\n  }",
        OLD_LA_CATCH)
    assert reverted_la != la_body, "leadAct 되돌림 치환이 실제로 안 먹었다"
    la_old_fail = run_node(reverted_la, HARNESS_TAIL_LA, fail=True)
    chk("closeModal" not in la_old_fail and "VIEWS.leads" not in la_old_fail,
        "★★★★★ 옛 코드(되돌림): leadAct() 도 서버 오류 시 모달·목록을 방치한다", la_old_fail)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] Node 실행/되돌림-증명", f"{type(e).__name__}: {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
