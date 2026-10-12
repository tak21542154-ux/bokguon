# -*- coding: utf-8 -*-
"""스캔 481라운드 회귀 — 477·479라운드가 insurer_portal.html·
partner_portal.html에서 고친 "성공 분기는 모달·목록을 정리하는데 catch
분기는 toast만 하고 낡은 모달을 방치한다" 패턴의 형제 자리가 admin.js
(관리자 화면)에도 있었음, 3곳(정밀조사 Agent가 발견, 전부 직접 재확인):

  ① agRequest(caseId)  — 1차합의 승인요청(admin.js:4833-4843)
  ② agSettle(caseId,0) — 1차합의 부동의 기록(admin.js:4846-4859), 이
     함수는 field-agreement open + settle 두 API를 순차 호출한다.
  ③ dpAssign(cid)      — 출동 직접배정(admin.js:4682-4708), 두 실패
     경로 — DISPATCH_LIVE 재시도(supersede)가 다시 실패하는 안쪽 catch,
     그리고 DISPATCH_LIVE가 아닌 다른 409(이미 배정불가 상태·이미 사진
     확보됨)로 떨어지는 바깥 fallback.

  대응 백엔드 409 확인(app.py·dispatch.py 직접 재확인):
    api_field_agreement_open의 "이미 1차 합의가 부동의로 끝난 사건"
    (app.py:17563-17565)·"현장 사진이 확보된 출동 건이 없습니다"
    (17584-17585, dispatch.py open_agreement()의 세 가지 None-반환
    사유를 감쌈: 도착 수배 없음/사건이 이미 다른 경로로 확정/이미 결렬).
    api_field_agreement_settle이 그대로 전달하는 settle_agreement()의
    "이미 처리된 건입니다"(dispatch.py:1135-1137)·"상태가 바뀌어
    처리하지 못했습니다"(1158-1160, rowcount TOCTOU 재확인).
    assign_dispatch()의 "배정할 수 있는 상태가 아닙니다"(dispatch.py:
    477-479)·"이미 다른 업체가 현장에 도착해 사진을 확보한 사건입니다"
    (490-492).

  고침: 477·479라운드와 동일 원칙 — 각 함수(각 catch 분기) 자신의
  성공 분기가 이미 하는 정리호출(closeModal·VIEWS.dispatch())을 그대로
  옮김(새 헬퍼 없이 4개 catch 지점 각각 인라인).

  [1] 소스 확인 — 새 catch 4곳 모두 정리호출을 가짐.
  [2] 실제 JS 실행(Node vm, 340·464·477·479라운드 방식) — api() 실패
      시 4개 catch 지점 전부 정리호출을 실제로 하는지 확인.
  [3] 되돌림-증명 — 4곳 모두 옛(toast만) 코드로 임시 되돌려 옛 동작이
      실제로 재현되는지 대조.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 481라운드 회귀 — admin.js의 477·479라운드 패턴 형제 자리 3곳")
print("=" * 72)

ADM_PATH = os.path.join(HERE, "static", "admin.js")
ADM_SRC = io.open(ADM_PATH, encoding="utf-8").read()


def extract_flat_catch(src, fn_name):
    """agRequest·agSettle처럼 중첩 없는 단일 catch — 함수 시작 뒤 첫
    '}catch(' ~ 그 catch 를 닫는 '\\n  }' 까지를 실제 파일에서 그대로
    뽑는다(477·479라운드가 세운 방식)."""
    i = src.find(f"async function {fn_name}(")
    pos = src.find("}catch(", i)
    e = src.find("\n  }", pos)
    if i < 0 or pos < 0 or e < 0:
        return ""
    return src[pos:e + len("\n  }")]


def extract_dpassign_inner(src):
    """dpAssign 안쪽(재시도 supersede 실패) catch — 6칸 들여쓰기로 닫힌다
    (바깥 catch 안의 if 블록 안의 try 이므로 중첩이 한 단계 더 깊다)."""
    #  ⚠ "}catch(e2){"는 admin.js 전체에서 유일하지 않다(다른 함수도 e2를
    #    재시도용 catch 변수명으로 쓴다) — 반드시 dpAssign 함수 시작 위치
    #    뒤에서부터 찾아야 한다(처음엔 이걸 놓쳐 엉뚱한 함수를 뽑았었다).
    fn_start = src.find("async function dpAssign(")
    c = src.find("}catch(e2){", fn_start)
    e = src.find("\n      }", c)
    return src[c:e + len("\n      }")] if fn_start >= 0 and c >= 0 and e >= 0 else ""


def extract_dpassign_outer(src):
    """dpAssign 바깥 catch의 DISPATCH_LIVE 가 아닌 경우 fallback —
    고유 주석부터 함수 끝(2칸 들여쓰기 catch 닫힘 + 0칸 함수 닫힘)까지."""
    fn_start = src.find("async function dpAssign(")
    a = src.find("//  [라운드481] DISPATCH_LIVE가 아닌 다른 409", fn_start)
    e = src.find("\n  }\n}", a)
    return src[a:e + len("\n  }\n}")] if fn_start >= 0 and a >= 0 and e >= 0 else ""


TARGETS = [
    {"label": "① agRequest", "key": "agRequest", "extract": lambda s: extract_flat_catch(s, "agRequest")},
    {"label": "② agSettle", "key": "agSettle", "extract": lambda s: extract_flat_catch(s, "agSettle")},
    {"label": "③ dpAssign(재시도 실패)", "key": "dpAssign_retry_fail", "extract": extract_dpassign_inner},
    {"label": "③ dpAssign(그 외 409)", "key": "dpAssign_other_409", "extract": extract_dpassign_outer},
]
OLD_CATCH = {
    "agRequest": "}catch(e){ toast(e.message); }",
    "agSettle": "}catch(e){ toast(e.message); }",
    "dpAssign_retry_fail": "}catch(e2){ toast(e2.message); }",
    "dpAssign_other_409": "toast(e.message);\n  }\n}",
}

print("\n[1] 소스 확인 — 새 catch 블록이 실제로 정리호출을 갖는가")
NEW_CATCH = {}
for t in TARGETS:
    block = t["extract"](ADM_SRC)
    NEW_CATCH[t["key"]] = block
    chk(bool(block) and "[라운드481]" in block,
        f"{t['label']} — catch 블록에 [라운드481] 주석이 있다",
        "블록을 못 뽑음" if not block else "")
    chk("closeModal()" in block and "VIEWS.dispatch()" in block,
        f"{t['label']} — catch 블록이 closeModal + VIEWS.dispatch()를 호출한다", block)
    chk(ADM_SRC.count(block) == 1 if block else False,
        f"{t['label']} — 되돌림-증명에 쓸 블록이 소스에 정확히 1번만 있다",
        ADM_SRC.count(block) if block else "블록을 못 뽑음")

print("\n[2] 실제 JS 실행(Node vm) — api() 실패 시 4개 catch 지점이 정리호출을 하는가")
NODE_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");

const admPath = process.argv[2];
const src = fs.readFileSync(admPath, "utf8");

function extractFn(name) {
  const startPat = new RegExp("async\\s+function\\s+" + name + "\\s*\\([^)]*\\)");
  const m = startPat.exec(src);
  if (!m) throw new Error("함수를 못 찾음: " + name);
  const braceStart = src.indexOf("{", m.index + m[0].length);
  let depth = 0, i = braceStart;
  for (; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}") { depth--; if (depth === 0) break; }
  }
  if (depth !== 0) throw new Error("중괄호 짝을 못 찾음: " + name);
  return src.slice(m.index, i + 1);
}

function makeSandbox(elMap, apiImpl) {
  const calls = { toast: 0, closeModal: 0, dispatch: 0 };
  const sandbox = {
    AG_RANGE: null,
    $: (sel) => (elMap && elMap[sel]) || { value: "" },
    confirm: () => true,
    prompt: () => "충분히 긴 부동의 사유",
    esc: (x) => x,
    won: (n) => String(n),
    toast: () => { calls.toast++; },
    closeModal: () => { calls.closeModal++; },
    VIEWS: { dispatch: () => { calls.dispatch++; } },
    api: apiImpl,
    console,
  };
  vm.createContext(sandbox);
  return { sandbox, calls };
}

const alwaysReject = async () => { throw { message: "TEST_FAIL" }; };

async function run() {
  const out = {};

  { const { sandbox, calls } = makeSandbox(null, alwaysReject);
    vm.runInContext(extractFn("agRequest") + "\nthis.agRequest = agRequest;", sandbox);
    await vm.runInContext("agRequest(1)", sandbox);
    out.agRequest = calls; }

  { const { sandbox, calls } = makeSandbox(null, alwaysReject);
    vm.runInContext(extractFn("agSettle") + "\nthis.agSettle = agSettle;", sandbox);
    await vm.runInContext("agSettle(1, 0)", sandbox);
    out.agSettle = calls; }

  //  ③-1 DISPATCH_LIVE 로 걸린 뒤, 재시도(supersede)도 실패
  { const elMap = { "#as_partner": { value: "5" }, "#as_reason": { value: "충분한 사유" } };
    let n = 0;
    const api2 = async () => {
      n++;
      if (n === 1) throw { code: "DISPATCH_LIVE", message: "진행중 수배 있음" };
      throw { message: "RETRY_FAIL" };
    };
    const { sandbox, calls } = makeSandbox(elMap, api2);
    vm.runInContext(extractFn("dpAssign") + "\nthis.dpAssign = dpAssign;", sandbox);
    await vm.runInContext("dpAssign(1)", sandbox);
    out.dpAssign_retry_fail = calls; }

  //  ③-2 DISPATCH_LIVE 가 아닌 다른 409(이미 배정불가 등)
  { const elMap = { "#as_partner": { value: "5" }, "#as_reason": { value: "충분한 사유" } };
    const api3 = async () => { throw { message: "이 사건은 배정할 수 있는 상태가 아닙니다" }; };
    const { sandbox, calls } = makeSandbox(elMap, api3);
    vm.runInContext(extractFn("dpAssign") + "\nthis.dpAssign = dpAssign;", sandbox);
    await vm.runInContext("dpAssign(1)", sandbox);
    out.dpAssign_other_409 = calls; }

  console.log(JSON.stringify(out));
}

run().catch(e => { console.error(e.stack || String(e)); process.exit(1); });
"""


def _run_js_harness(adm_path=None):
    harness_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                          encoding="utf-8") as f:
            f.write(NODE_HARNESS)
            harness_path = f.name
        r = subprocess.run(["node", harness_path, adm_path or ADM_PATH],
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
        if r.returncode != 0:
            raise RuntimeError(f"Node 실행 실패(rc={r.returncode}): {r.stdout}\n{r.stderr}")
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        if harness_path and os.path.exists(harness_path):
            os.unlink(harness_path)


try:
    fixed = _run_js_harness()
    chk(fixed["agRequest"]["toast"] == 1 and fixed["agRequest"]["closeModal"] == 1
        and fixed["agRequest"]["dispatch"] == 1,
        "★★★★★ 새 코드: agRequest 실패 시 정리호출도 실제로 일어난다", fixed["agRequest"])
    chk(fixed["agSettle"]["toast"] == 1 and fixed["agSettle"]["closeModal"] == 1
        and fixed["agSettle"]["dispatch"] == 1,
        "★★★★★ 새 코드: agSettle 실패 시 정리호출도 실제로 일어난다", fixed["agSettle"])
    chk(fixed["dpAssign_retry_fail"]["toast"] == 1 and fixed["dpAssign_retry_fail"]["closeModal"] == 1
        and fixed["dpAssign_retry_fail"]["dispatch"] == 1,
        "★★★★★ 새 코드: dpAssign 재시도(supersede) 실패 시 정리호출도 일어난다",
        fixed["dpAssign_retry_fail"])
    chk(fixed["dpAssign_other_409"]["toast"] == 1 and fixed["dpAssign_other_409"]["closeModal"] == 1
        and fixed["dpAssign_other_409"]["dispatch"] == 1,
        "★★★★★ 새 코드: dpAssign의 DISPATCH_LIVE 아닌 409도 정리호출을 한다",
        fixed["dpAssign_other_409"])

    print("\n[3] 되돌림-증명 — 4곳 모두 스크래치 사본에 옛 코드를 써서 재현(실제 파일은 안 건드림)")
    #  ⚠⚠ [라운드627] 이전 버전은 이 루프에서 매번 실제 static/admin.js 파일에
    #    직접 썼다(io.open(ADM_PATH,"w")) — _run_js_harness가 이미 경로 인자를
    #    받게 돼 있으므로(477·509 선례), tempfile 스크래치 사본에 되돌린
    #    내용을 쓰고 그 경로를 하니스에 넘긴다(실제 파일은 이 검증 내내
    #    전혀 안 건드린다 — finally 복원 자체가 필요 없어짐).
    for t in TARGETS:
        key = t["key"]
        block = NEW_CATCH[key]
        assert block, f"{key} 블록을 못 뽑았다"
        old = OLD_CATCH[key]
        reverted = ADM_SRC.replace(block, old)
        assert reverted != ADM_SRC, f"{key} 되돌림 치환이 안 먹었다"
        _scratch_dir = tempfile.mkdtemp(prefix="r481_js_")
        try:
            _scratch_adm = os.path.join(_scratch_dir, "admin.js")
            io.open(_scratch_adm, "w", encoding="utf-8", newline="\n").write(reverted)
            broken = _run_js_harness(adm_path=_scratch_adm)
            b = broken[key]
            chk(b["toast"] == 1 and b["closeModal"] == 0 and b["dispatch"] == 0,
                f"★★★★★ {t['label']} — 옛 코드(되돌림)는 toast만 하고 정리호출은 안 한다"
                " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", b)
        finally:
            shutil.rmtree(_scratch_dir, ignore_errors=True)

except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] 실행/되돌림-증명", f"{type(e).__name__}: {e}")

chk(io.open(ADM_PATH, encoding="utf-8").read() == ADM_SRC,
    "★★★★★ admin.js는 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
