# -*- coding: utf-8 -*-
"""스캔 479라운드 회귀 — 477라운드가 insurer_portal.html의 faDecide()·
doAward()에서 고친 "성공 분기는 모달을 정리하는데 catch 분기는 toast만
하고 낡은 모달을 방치한다" 패턴의 형제 자리 4곳(직접 조사로 발견,
정밀조사 Agent가 먼저 찾고 이 세션이 전부 재확인):

  ① insurer_portal.html coAck()        — 추가공사 증액 확인/부동의
  ② insurer_portal.html rejectBids()   — 낙찰승인 모달 안, doAward() 바로
                                          옆 버튼(같은 모달을 공유)
  ③ insurer_portal.html cancelCase()   — 입찰 0건일 때만 뜨는 버튼(TOCTOU)
  ④ partner_portal.html reestimateGo() — 실사 후 증액 요청

  네 곳 모두 대응하는 백엔드 라우트가 실제로 도달 가능한 409를 갖고
  있음을 직접 확인(app.py: api_insurer_co_ack CO_CLOSED/NO_AMOUNT
  13472-13486, api_insurer_case_cancel HAS_BIDS 4346-4350, api_insurer_
  reject_bids 4419-4421, api_change_order_create 10069-10080). 고침은
  477라운드와 동일 — 각 함수 자신의 성공 분기가 이미 하는 정리 호출을
  catch 분기에 그대로 옮긴다(새 헬퍼 발명 없음, 4개 지점 각각 인라인).

  [1] 소스 확인 — 새 catch 4곳 모두 성공분기와 같은 정리호출을 가짐.
  [2] 실제 JS 실행(Node vm, 340·464·477라운드 방식) — api()가 실패할 때
      4개 함수 모두 catch에서 toast뿐 아니라 closeModal/reload(또는
      boot)/show도 실제로 호출되는지 확인.
  [3] 되돌림-증명 — 4곳 모두 옛(토스트만) 코드로 임시 되돌려 옛 동작
      (모달 미갱신)이 실제로 재현되는지 대조.
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
print("  스캔 479라운드 회귀 — 477라운드 패턴의 형제 자리 4곳(모달 미갱신)")
print("=" * 72)

INS_PATH = os.path.join(HERE, "templates", "insurer_portal.html")
PTN_PATH = os.path.join(HERE, "templates", "partner_portal.html")
INS_SRC = io.open(INS_PATH, encoding="utf-8").read()
PTN_SRC = io.open(PTN_PATH, encoding="utf-8").read()


def extract_catch_block(src, fn_name):
    """함수 시작부터 '}catch(e){' ~ 그 함수를 닫는 '\\n  }\\n}' 까지를
    실제 파일에서 그대로 뽑는다 — 손으로 옮겨 적지 않는다(공백·줄바꿈
    불일치로 되돌림 치환이 조용히 실패하는 사고를 막기 위해, 477라운드가
    세운 방식 그대로)."""
    i = src.find(f"async function {fn_name}(")
    c = src.find("}catch(e){", i)
    e = src.find("\n  }\n}", c)
    if i < 0 or c < 0 or e < 0:
        return ""
    return src[c:e + len("\n  }\n}")]


TARGETS = [
    {"label": "① coAck", "file": "insurer_portal.html", "src_name": "INS_SRC", "fn": "coAck"},
    {"label": "② rejectBids", "file": "insurer_portal.html", "src_name": "INS_SRC", "fn": "rejectBids"},
    {"label": "③ cancelCase", "file": "insurer_portal.html", "src_name": "INS_SRC", "fn": "cancelCase"},
    {"label": "④ reestimateGo", "file": "partner_portal.html", "src_name": "PTN_SRC", "fn": "reestimateGo"},
]
SRCS = {"INS_SRC": INS_SRC, "PTN_SRC": PTN_SRC}
OLD_CATCH = {
    "coAck": "}catch(e){ toast(e.message); }\n}",
    "rejectBids": "}catch(e){ toast(e.message); }\n}",
    "cancelCase": "}catch(e){ toast(e.message); }\n}",
    "reestimateGo": "}catch(e){ toast(e.message); }\n}",
}

print("\n[1] 소스 확인 — 새 catch 블록이 실제로 정리호출을 갖는가")
NEW_CATCH = {}
for t in TARGETS:
    src = SRCS[t["src_name"]]
    block = extract_catch_block(src, t["fn"])
    NEW_CATCH[t["fn"]] = block
    chk(bool(block) and "[라운드479]" in block, f"{t['label']} — catch 블록에 [라운드479] 주석이 있다",
        "블록을 못 뽑음" if not block else "")
    chk("closeModal()" in block and ("reload()" in block or "boot()" in block),
        f"{t['label']} — catch 블록이 closeModal + reload/boot를 호출한다", block)
    chk(src.count(block) == 1 if block else False,
        f"{t['label']} — 되돌림-증명에 쓸 블록이 소스에 정확히 1번만 있다",
        src.count(block) if block else "블록을 못 뽑음")

print("\n[2] 실제 JS 실행(Node vm) — api() 실패 시 4개 함수 모두 정리호출을 하는가")
NODE_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");

const insPath = process.argv[2];
const ptnPath = process.argv[3];
const insSrc = fs.readFileSync(insPath, "utf8");
const ptnSrc = fs.readFileSync(ptnPath, "utf8");

function extractFn(src, name) {
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

function makeSandbox(elMap) {
  const calls = { toast: 0, closeModal: 0, reload: 0, boot: 0, show: [] };
  const sandbox = {
    window: { FA_VIEW: {} },
    AW_BIDS: [], SELBID: null,
    document: { getElementById: (id) => (elMap && elMap[id]) || { value: "" } },
    confirm: () => true,
    prompt: () => "충분히 긴 사유 5자 이상",
    esc: (x) => x,
    toast: () => { calls.toast++; },
    closeModal: () => { calls.closeModal++; },
    reload: async () => { calls.reload++; return Promise.resolve(); },
    boot: () => { calls.boot++; },
    show: (v) => { calls.show.push(v); },
    api: async () => { throw { message: "TEST_FAIL" }; },
    console,
  };
  vm.createContext(sandbox);
  return { sandbox, calls };
}

const flush = () => new Promise(r => setTimeout(r, 0));

async function run() {
  const out = {};

  { const { sandbox, calls } = makeSandbox();
    vm.runInContext(extractFn(insSrc, "coAck") + "\nthis.coAck = coAck;", sandbox);
    await vm.runInContext("coAck(1, 1)", sandbox);
    await flush();
    out.coAck = calls; }

  { const { sandbox, calls } = makeSandbox();
    vm.runInContext(extractFn(insSrc, "rejectBids") + "\nthis.rejectBids = rejectBids;", sandbox);
    await vm.runInContext("rejectBids(1)", sandbox);
    await flush();
    out.rejectBids = calls; }

  { const { sandbox, calls } = makeSandbox();
    vm.runInContext(extractFn(insSrc, "cancelCase") + "\nthis.cancelCase = cancelCase;", sandbox);
    await vm.runInContext("cancelCase(1)", sandbox);
    await flush();
    out.cancelCase = calls; }

  { const { sandbox, calls } = makeSandbox({
      re_reason: { value: "충분히 긴 사유 5자 이상" }, re_amt: { value: "500000" } });
    vm.runInContext(extractFn(ptnSrc, "reestimateGo") + "\nthis.reestimateGo = reestimateGo;", sandbox);
    await vm.runInContext("reestimateGo(1)", sandbox);
    await flush();
    out.reestimateGo = calls; }

  console.log(JSON.stringify(out));
}

run().catch(e => { console.error(e.stack || String(e)); process.exit(1); });
"""


def _run_js_harness(ins_path=None, ptn_path=None):
    harness_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                          encoding="utf-8") as f:
            f.write(NODE_HARNESS)
            harness_path = f.name
        r = subprocess.run(["node", harness_path, ins_path or INS_PATH, ptn_path or PTN_PATH],
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
        if r.returncode != 0:
            raise RuntimeError(f"Node 실행 실패(rc={r.returncode}): {r.stdout}\n{r.stderr}")
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        if harness_path and os.path.exists(harness_path):
            os.unlink(harness_path)


try:
    fixed = _run_js_harness()
    chk(fixed["coAck"]["toast"] == 1 and fixed["coAck"]["closeModal"] == 1
        and fixed["coAck"]["reload"] == 1 and fixed["coAck"]["show"] == ["cases"],
        "★★★★★ 새 코드: coAck 실패 시 정리호출도 실제로 일어난다", fixed["coAck"])
    chk(fixed["rejectBids"]["toast"] == 1 and fixed["rejectBids"]["closeModal"] == 1
        and fixed["rejectBids"]["show"] == ["cases"],
        "★★★★★ 새 코드: rejectBids 실패 시 정리호출도 실제로 일어난다", fixed["rejectBids"])
    chk(fixed["cancelCase"]["toast"] == 1 and fixed["cancelCase"]["closeModal"] == 1
        and fixed["cancelCase"]["show"] == ["cases"],
        "★★★★★ 새 코드: cancelCase 실패 시 정리호출도 실제로 일어난다", fixed["cancelCase"])
    chk(fixed["reestimateGo"]["toast"] == 1 and fixed["reestimateGo"]["closeModal"] == 1
        and fixed["reestimateGo"]["boot"] == 1,
        "★★★★★ 새 코드: reestimateGo 실패 시 정리호출도 실제로 일어난다", fixed["reestimateGo"])

    print("\n[3] 되돌림-증명 — 4곳 모두 스크래치 사본에 옛 코드를 써서 재현(실제 파일은 안 건드림)")
    #  ⚠⚠ [라운드627] 이전 버전은 이 루프에서 매번 실제 templates/insurer_portal.html
    #    또는 partner_portal.html 파일에 직접 썼다(io.open(path,"w")) — _run_js_harness가
    #    이미 두 경로 인자를 받게 돼 있으므로(477 선례), 스크래치 디렉터리에 두 파일의
    #    사본(대상 파일만 되돌린 내용, 나머지 하나는 원본 그대로)을 만들어 그 경로들을
    #    하니스에 넘긴다(실제 두 파일 모두 이 검증 내내 전혀 안 건드린다).
    for t in TARGETS:
        src_name = t["src_name"]
        cur = SRCS[src_name]
        block = NEW_CATCH[t["fn"]]
        assert block, f"{t['fn']} 블록을 못 뽑았다"
        reverted = cur.replace(block, OLD_CATCH[t["fn"]])
        assert reverted != cur, f"{t['fn']} 되돌림 치환이 안 먹었다"
        _scratch_dir = tempfile.mkdtemp(prefix="r479_tpl_")
        try:
            _scratch_ins = os.path.join(_scratch_dir, "insurer_portal.html")
            _scratch_ptn = os.path.join(_scratch_dir, "partner_portal.html")
            io.open(_scratch_ins, "w", encoding="utf-8", newline="\n").write(
                reverted if src_name == "INS_SRC" else INS_SRC)
            io.open(_scratch_ptn, "w", encoding="utf-8", newline="\n").write(
                reverted if src_name == "PTN_SRC" else PTN_SRC)
            broken = _run_js_harness(ins_path=_scratch_ins, ptn_path=_scratch_ptn)
            b = broken[t["fn"]]
            chk(b["toast"] == 1 and b["closeModal"] == 0 and b["reload"] == 0 and b["boot"] == 0,
                f"★★★★★ {t['label']} — 옛 코드(되돌림)는 toast만 하고 정리호출은 안 한다"
                " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", b)
        finally:
            shutil.rmtree(_scratch_dir, ignore_errors=True)

except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] 실행/되돌림-증명", f"{type(e).__name__}: {e}")

chk(io.open(INS_PATH, encoding="utf-8").read() == INS_SRC,
    "★★★★★ insurer_portal.html은 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일)")
chk(io.open(PTN_PATH, encoding="utf-8").read() == PTN_SRC,
    "★★★★★ partner_portal.html은 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
