# -*- coding: utf-8 -*-
"""스캔 503라운드 회귀 — 변경견적(change_orders) 처리 8개 함수의 catch
분기가 형제(caseCancelAward 등, 라운드481·486·500·501이 세운 "catch도
성공 분기와 같이 정리한다" 원칙)를 못 물려받아 toast만 하고 화면(목록·
모달)을 방치하던 결함 — 다섯 번째 클러스터.

대상: coWithdraw·coAddAuction·coOffer·coFullReauction·coAwardFull(2곳)·
coFailFull(2곳)·ACT.coWithdrawReq·ACT.coFailAdd (static/admin.js).

특히 ACT.coFailAdd 는 이미 고쳐진 형제 ACT.caseCancelAward 바로 다음
줄에 있으면서도 못 물려받았던 자리 — coActions()(라운드252가 이미
등급게이트)의 여러 상태전이 버튼 중 하나다. 상태 '원업체제안'인
변경건에서 원업체가 먼저 응답하면 다른 관리자의 "제안 회수"(coWithdraw)
가 서버(api_co_withdraw_offer) 409 NOT_OFFERED로 막히는데, 화면은
이미 무효가 된 그 행을 계속 보여준다.
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
print("  스캔 503라운드 회귀 — 변경견적 처리 8곳 catch 분기 화면정리 누락")
print("=" * 72)

JS_PATH = os.path.join(HERE, "static", "admin.js")
JS_SRC = io.open(JS_PATH, encoding="utf-8").read()


def fn_body(src, start_marker):
    """중괄호 짝을 실제로 세어 함수 끝을 찾는다(라운드500이 확립한 방식)."""
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
print("\n[1] 소스 확인 — 8곳 전부 catch가 성공 분기와 같은 정리를 한다")
# ──────────────────────────────────────────────────────────────
co_withdraw = fn_body(JS_SRC, "async function coWithdraw(id){")
co_addauction = fn_body(JS_SRC, "async function coAddAuction(id){")
co_offer = fn_body(JS_SRC, "async function coOffer(id){")
co_fullreauction = fn_body(JS_SRC, "async function coFullReauction(id){")
co_awardfull = fn_body(JS_SRC, "async function coAwardFull(id){")
co_failfull = fn_body(JS_SRC, "async function coFailFull(id){")
act_withdrawreq = fn_body(JS_SRC, "ACT.coWithdrawReq = async (a) => {")
act_failadd = fn_body(JS_SRC, "ACT.coFailAdd = async (a) => {")

for body, label in [(co_withdraw, "coWithdraw"), (co_addauction, "coAddAuction"),
                     (co_offer, "coOffer"), (co_fullreauction, "coFullReauction"),
                     (co_awardfull, "coAwardFull"), (co_failfull, "coFailFull"),
                     (act_withdrawreq, "ACT.coWithdrawReq"), (act_failadd, "ACT.coFailAdd")]:
    chk(JS_SRC.count(body) == 1, f"{label}() 함수 본문이 소스에 유일하게 추출된다")

chk("toast(e.message); VIEWS.changeorders();\n  }\n}" in co_withdraw,
    "coWithdraw() catch가 성공 분기와 같은 정리를 한다")
chk("catch(e){ toast(e.message); VIEWS.changeorders(); }" in co_addauction,
    "coAddAuction() catch가 성공 분기와 같은 정리를 한다")
chk("catch(e){ toast(e.message); VIEWS.changeorders(); }" in co_offer,
    "coOffer() catch가 성공 분기와 같은 정리를 한다")
chk("catch(e){ toast(e.message); VIEWS.changeorders(); }" in co_fullreauction,
    "coFullReauction() catch가 성공 분기와 같은 정리를 한다")
chk(co_awardfull.count("closeModal(); VIEWS.changeorders();") >= 3,
    "coAwardFull() 성공+재시도catch+종단catch 셋 다 같은 정리를 한다(성공1+새로고침2)",
    co_awardfull.count("closeModal(); VIEWS.changeorders();"))
chk(co_failfull.count("closeModal(); VIEWS.changeorders();") >= 3,
    "coFailFull() 성공+재시도catch+종단catch 셋 다 같은 정리를 한다",
    co_failfull.count("closeModal(); VIEWS.changeorders();"))
chk("toast(e.message || '철회하지 못했습니다.'); VIEWS.changeorders();" in act_withdrawreq,
    "ACT.coWithdrawReq() catch가 성공 분기와 같은 정리를 한다")
chk("toast(e.message); loadView('changeorders');\n    }" in act_failadd,
    "ACT.coFailAdd() catch가 성공 분기(loadView)와 같은 정리를 한다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 Node 실행 — 대표 세 형태를 진짜 호출(성공/실패 각각)")
# ──────────────────────────────────────────────────────────────
HARNESS_HEAD = r"""
const calls = [];
global.toast = (m) => calls.push('toast:' + String(m).slice(0,20));
global.closeModal = () => calls.push('closeModal');
global.VIEWS = { changeorders: () => calls.push('VIEWS.changeorders') };
global.loadView = (v) => calls.push('loadView:' + v);
global.esc = (s) => String(s==null?'':s);
global.won = (n) => String(n);
global.confirm = () => true;
global.document = { getElementById: () => null };
global.askOverride = () => '사유';
let SHOULD_FAIL = process.env.R503_FAIL === '1';
let FAIL_CODE = process.env.R503_CODE || '';
global.api = async (method, url, body) => {
  if (SHOULD_FAIL) { const e = new Error('R503 테스트용 오류'); if (FAIL_CODE) e.code = FAIL_CODE; throw e; }
  return { message: 'ok', round: 1, bid_count: 0 };
};
"""


def run_node(body, tail, fail, code=""):
    src = HARNESS_HEAD + "\n" + body + "\n" + tail
    path = os.path.join(HERE, "_r503_node_tmp.js")
    io.open(path, "w", encoding="utf-8").write(src)
    env = dict(os.environ)
    env["R503_FAIL"] = "1" if fail else "0"
    env["R503_CODE"] = code
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


TAIL_WITHDRAW = "(async()=>{ await coWithdraw(1); console.log(JSON.stringify(calls)); })();"
TAIL_FAILADD = "(async()=>{ await ACT.coFailAdd(1); console.log(JSON.stringify(calls)); })();"
TAIL_FAILFULL = "(async()=>{ await coFailFull(1); console.log(JSON.stringify(calls)); })();"
ACT_WRAP_HEAD = "const ACT = {};\n"

try:
    ok1 = run_node(co_withdraw, TAIL_WITHDRAW, fail=False)
    chk("VIEWS.changeorders" in ok1, "coWithdraw() 정상 처리 시 목록을 새로고침한다(대조군)", ok1)
    fail1 = run_node(co_withdraw, TAIL_WITHDRAW, fail=True)
    chk("VIEWS.changeorders" in fail1,
        "★★★★★ 새 코드: coWithdraw() 서버 오류(동시처리 충돌 등)에도 목록을 새로고침한다", fail1)

    ok2 = run_node(ACT_WRAP_HEAD + act_failadd, TAIL_FAILADD, fail=False)
    chk("loadView:changeorders" in ok2, "ACT.coFailAdd() 정상 처리 시 목록을 새로고침한다(대조군)", ok2)
    fail2 = run_node(ACT_WRAP_HEAD + act_failadd, TAIL_FAILADD, fail=True)
    chk("loadView:changeorders" in fail2,
        "★★★★★ 새 코드: ACT.coFailAdd() 서버 오류에도 목록을 새로고침한다", fail2)

    ok3 = run_node(co_failfull, TAIL_FAILFULL, fail=False)
    chk("closeModal" in ok3 and "VIEWS.changeorders" in ok3,
        "coFailFull() 정상 처리 시 모달을 닫고 목록을 새로고침한다(대조군)", ok3)
    fail3_unknown = run_node(co_failfull, TAIL_FAILFULL, fail=True, code="SOME_OTHER_ERROR")
    chk("closeModal" in fail3_unknown and "VIEWS.changeorders" in fail3_unknown,
        "★★★★★ 새 코드: coFailFull() 알수없는 오류(종단분기)에도 모달을 닫고 목록을 "
        "새로고침한다", fail3_unknown)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 되돌림-증명 — 옛 코드(성공 분기만 정리)는 catch에서 화면을 방치한다")
    # ──────────────────────────────────────────────────────────
    OLD_WITHDRAW_CATCH = "catch(e){ toast(e.message); }"
    reverted1 = co_withdraw.replace(
        "catch(e){\n    //  ⚠⚠ [라운드503] 형제(caseCancelAward 등, 라운드481·486·500·501)가\n"
        "    //    이미 세운 원칙 — 성공 분기(바로 위)만 목록을 새로고침하면, 동시에\n"
        "    //    다른 관리자가 먼저 처리해 이미 상태가 바뀐 변경건을 이 화면만\n"
        "    //    계속 처리 가능한 것으로 보여준다. catch도 성공 분기와 같이 정리한다.\n"
        "    toast(e.message); VIEWS.changeorders();\n  }",
        OLD_WITHDRAW_CATCH)
    assert reverted1 != co_withdraw, "coWithdraw 되돌림 치환이 실제로 안 먹었다"
    old1 = run_node(reverted1, TAIL_WITHDRAW, fail=True)
    chk("VIEWS.changeorders" not in old1,
        "★★★★★ 옛 코드(되돌림): coWithdraw() 서버 오류 시 toast만 뜨고 목록은 방치된다 — "
        "이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", old1)

    OLD_FAILADD_CATCH = "catch(e){ toast(e.message); }"
    reverted2 = act_failadd.replace(
        "catch(e){\n      //  ⚠⚠ [라운드503] 형제(caseCancelAward, 바로 위) 참조 — catch도 성공\n"
        "      //    분기와 같이 정리한다.\n      toast(e.message); loadView('changeorders');\n    }",
        OLD_FAILADD_CATCH)
    assert reverted2 != act_failadd, "ACT.coFailAdd 되돌림 치환이 실제로 안 먹었다"
    old2 = run_node(ACT_WRAP_HEAD + reverted2, TAIL_FAILADD, fail=True)
    chk("loadView:changeorders" not in old2,
        "★★★★★ 옛 코드(되돌림): ACT.coFailAdd() 도 서버 오류 시 목록을 방치한다", old2)

    OLD_FAILFULL_TAIL = "    toast(e.message);\n  }\n}"
    reverted3 = co_failfull.replace(
        "    //  ⚠⚠ [라운드503] 형제(coWithdraw 등, 라운드481·486·500·501) 참조 — 이\n"
        "    //    자리(알 수 없는 오류)도 catch가 성공 분기(위)와 같이 정리한다.\n"
        "    toast(e.message); closeModal(); VIEWS.changeorders();\n  }\n}",
        OLD_FAILFULL_TAIL)
    assert reverted3 != co_failfull, "coFailFull 종단분기 되돌림 치환이 실제로 안 먹었다"
    old3 = run_node(reverted3, TAIL_FAILFULL, fail=True, code="SOME_OTHER_ERROR")
    chk("closeModal" not in old3 and "VIEWS.changeorders" not in old3,
        "★★★★★ 옛 코드(되돌림): coFailFull() 도 알수없는 오류 시 모달·목록을 방치한다", old3)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] Node 실행/되돌림-증명", f"{type(e).__name__}: {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
