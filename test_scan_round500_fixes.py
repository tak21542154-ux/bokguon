# -*- coding: utf-8 -*-
"""스캔 500라운드 회귀 — 정산(settlements) 처리 6개 함수의 catch 분기가
형제(caseDetail 액션버튼, 라운드481·486이 세운 "catch도 성공 분기와
같이 정리한다" 원칙)를 못 물려받아 toast만 하고 화면을 방치하던 결함.

관리자 A·B가 같은 정산 목록을 열어둔 상태에서 B가 먼저 처리(취소·이체
등)하면, 서버 여러 지점(app.py, "취소된 정산 건입니다"류 409)이 code
없이 응답해 A의 화면(settlePaid 등)은 GATE 판정도 못 하고 toast만
뜬 채 이미 무효화된 행을 계속 처리 가능한 것으로 보여준다.

대상: settleVoid·settleUndo·settlePaid·settlePaidBulk·doSettleReview·
settleTransfer (static/admin.js). 각 함수 catch는 **그 함수 자신의
성공 분기가 이미 하는 정리**(VIEWS.settle()·refreshBadges(), doSettleReview
만 모달 안에서 열리므로 closeModal()도)를 그대로 옮긴 것 — 새 정책
발명이 아니라 라운드481·486 원칙의 기계적 확장이다.
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
print("  스캔 500라운드 회귀 — 정산 6개 함수 catch 분기 화면정리 누락")
print("=" * 72)

JS_PATH = os.path.join(HERE, "static", "admin.js")
JS_SRC = io.open(JS_PATH, encoding="utf-8").read()


def fn_body(src, start_marker):
    """중괄호 짝을 실제로 세어 함수 끝을 찾는다 — 다음 'async function'/
    'function' 선언 전까지로 찾으면, 화살표함수 등 다른 선언 스타일이
    사이에 끼어 있을 때 훨씬 뒤의 무관한 함수까지 통째로 삼킬 수 있다
    (실측: 이 파일에서 실제로 그렇게 됨)."""
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


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 6개 함수 catch가 전부 성공 분기와 같은 정리를 한다")
# ──────────────────────────────────────────────────────────────
CHECKS = [
    ("async function settleVoid(sid){",
     "catch(e){\n    //  ⚠⚠ [라운드500]", "settleVoid"),
    ("async function settleUndo(id){",
     "catch(e){\n    //  ⚠⚠ [라운드500] 형제(settleVoid) 참조 — catch도 성공 분기와 같이 정리한다.\n    toast(e.message); refreshBadges(); VIEWS.settle();",
     "settleUndo"),
    ("async function settlePaid(id){",
     "catch(e){\n    //  ⚠⚠ [라운드500] 형제(settleVoid) 참조 — catch도 성공 분기와 같이 정리한다.\n    toast(e.message); refreshBadges(); VIEWS.settle();",
     "settlePaid"),
    ("async function settlePaidBulk(){",
     "catch(e){\n    //  ⚠⚠ [라운드500] 형제(settleVoid) 참조 — catch도 성공 분기와 같이 정리한다.\n    toast(e.message); refreshBadges(); VIEWS.settle();",
     "settlePaidBulk"),
]
for start_marker, expect_snippet, label in CHECKS:
    body = fn_body(JS_SRC, start_marker)
    chk(expect_snippet in body, f"{label}() catch가 성공 분기와 같은 정리(VIEWS.settle·refreshBadges)를 한다")
    chk(JS_SRC.count(body) == 1, f"{label}() 함수 본문이 소스에 유일하게 추출된다")

dsr_body = fn_body(JS_SRC, "async function doSettleReview(id){")
chk("closeModal(); refreshBadges(); VIEWS.settle(); return;" in dsr_body,
    "doSettleReview() 의 알수없는-오류 종단분기가 모달을 닫고 목록도 정리한다(모달 기반 흐름이라 closeModal 포함)")

st_body = fn_body(JS_SRC, "async function settleTransfer(id, _b, el){")
chk("toast(e.message); refreshBadges(); VIEWS.settle(); return;" in st_body,
    "settleTransfer() 의 알수없는-오류 종단분기가 목록을 정리한다")
chk("관문이 계속 남아 있습니다" in st_body and st_body.endswith("refreshBadges(); VIEWS.settle();\n}"),
    "settleTransfer() 의 4회 관문 소진 종단분기도 목록을 정리한다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 Node 실행 — 두 대표 형태(단순 catch / GATE 재시도)를 진짜 호출")
# ──────────────────────────────────────────────────────────────
sv_body = fn_body(JS_SRC, "async function settleVoid(sid){")
st_body_full = fn_body(JS_SRC, "async function settleTransfer(id, _b, el){")

HARNESS_HEAD = r"""
const calls = [];
global.toast = (m) => calls.push('toast:' + String(m).slice(0,30));
global.closeModal = () => calls.push('closeModal');
global.refreshBadges = () => calls.push('refreshBadges');
global.VIEWS = { settle: () => calls.push('VIEWS.settle') };
global.prompt = () => '충분히 긴 사유 5자 이상';
global.confirm = () => true;
global.askOverride = () => '사유';
global.won = (n) => String(n);
global.esc = (s) => String(s);
let SHOULD_FAIL = process.env.R500_FAIL === '1';
let ERR_CODE = process.env.R500_CODE || '';
global.api = async (method, url, body) => {
  if (SHOULD_FAIL) { const e = new Error('취소된 정산 건입니다.'); if (ERR_CODE) e.code = ERR_CODE; throw e; }
  return { message: 'ok', done_count: 1, total_amount: 0 };
};
"""

HARNESS_TAIL_VOID = r"""
(async () => {
  await settleVoid(1);
  console.log(JSON.stringify(calls));
})();
"""
HARNESS_TAIL_TRANSFER = r"""
(async () => {
  await settleTransfer(1, null, {dataset:{info:'A상사|100000'}});
  console.log(JSON.stringify(calls));
})();
"""


def run_node(body, tail, fail, code=""):
    src = HARNESS_HEAD + "\n" + body + "\n" + tail
    path = os.path.join(HERE, "_r500_node_tmp.js")
    io.open(path, "w", encoding="utf-8").write(src)
    env = dict(os.environ)
    env["R500_FAIL"] = "1" if fail else "0"
    env["R500_CODE"] = code
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
    calls_ok = run_node(sv_body, HARNESS_TAIL_VOID, fail=False)
    chk("VIEWS.settle" in calls_ok, "settleVoid() 정상 처리 시 목록을 새로고침한다(대조군)", calls_ok)

    calls_fail = run_node(sv_body, HARNESS_TAIL_VOID, fail=True)
    chk("toast:취소된 정산 건입니다." in calls_fail, "settleVoid() 서버 오류 시 toast는 뜬다", calls_fail)
    chk("VIEWS.settle" in calls_fail and "refreshBadges" in calls_fail,
        "★★★★★ 새 코드: settleVoid() 서버 오류(동시처리 충돌 등)에도 목록을 새로고침한다"
        "(다른 관리자가 먼저 처리한 낡은 버튼이 사라진다)", calls_fail)

    calls_st_fail = run_node(st_body_full, HARNESS_TAIL_TRANSFER, fail=True)
    chk("VIEWS.settle" in calls_st_fail and "refreshBadges" in calls_st_fail,
        "★★★★★ 새 코드: settleTransfer() 의 알수없는-코드 오류(GATE 미해당)에도 목록을 "
        "새로고침한다", calls_st_fail)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 되돌림-증명 — 옛 코드(성공 분기만 정리)는 catch에서 화면을 방치한다")
    # ──────────────────────────────────────────────────────────
    OLD_SV_CATCH = "  }catch(e){ toast(e.message); }\n}"
    NEW_SV_CATCH_MARKER = "toast(e.message); VIEWS.settle(); refreshBadges();\n  }\n}"
    assert NEW_SV_CATCH_MARKER in sv_body, "settleVoid 본문에서 새 catch 마커를 못 찾음"
    reverted_sv = sv_body[:sv_body.index("  }catch(e){")] + OLD_SV_CATCH

    calls_old_fail = run_node(reverted_sv, HARNESS_TAIL_VOID, fail=True)
    chk("VIEWS.settle" not in calls_old_fail and "refreshBadges" not in calls_old_fail,
        "★★★★★ 옛 코드(되돌림): settleVoid() 서버 오류 시 toast만 뜨고 목록은 방치된다 — "
        "이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", calls_old_fail)

    OLD_ST_LINE = "      if(!g || extra[g.field]){ toast(e.message); return; }   // 모르는 오류거나 이미 넘긴 관문"
    NEW_ST_LINE = "      if(!g || extra[g.field]){ toast(e.message); refreshBadges(); VIEWS.settle(); return; }   // 모르는 오류거나 이미 넘긴 관문"
    assert NEW_ST_LINE in st_body_full, "settleTransfer 본문에서 새 종단분기 줄을 못 찾음"
    reverted_st = st_body_full.replace(NEW_ST_LINE, OLD_ST_LINE)
    calls_old_st_fail = run_node(reverted_st, HARNESS_TAIL_TRANSFER, fail=True)
    chk("VIEWS.settle" not in calls_old_st_fail and "refreshBadges" not in calls_old_st_fail,
        "★★★★★ 옛 코드(되돌림): settleTransfer() 도 알수없는-오류 시 목록을 방치한다", calls_old_st_fail)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] Node 실행/되돌림-증명", f"{type(e).__name__}: {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
