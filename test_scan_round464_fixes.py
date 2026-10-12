# -*- coding: utf-8 -*-
"""스캔 464라운드 회귀 — 사건 정보 수정(PATCH /api/cases/<id>, admin.js의
saveCaseEdit) 폼이 항상 전체 스냅샷을 보내 동시수정 lost-update를
일으키던 결함, 1건.

`api_case_edit()`(app.py)은 요청에 들어온 각 필드를 **그 순간의 DB
현재값**과만 비교해 다르면 갱신한다 — "내가 폼을 열었을 때 본 값과
같은가"는 확인하지 않는다(cases 테이블엔 updated_at/version류 컬럼
자체가 없다, db.py 확인). 그런데 프런트(admin.js saveCaseEdit)가
사용자가 안 건드린 필드까지 항상 폼의 현재 표시값 전체를 함께
보냈으므로, 관리자1이 지역만 고쳐 저장한 직후 관리자2가(그 폼을 그보다
먼저 열어 옛 지역값을 그대로 들고 있는 채로) 공종만 고쳐 저장하면,
관리자2의 폼에 남은 옛 지역값이 관리자1의 변경을 조용히 되돌렸다 —
서버 쪽 실제 동시성 재현(순차 2회 PATCH, 진짜 동시 스레드 est_price)
으로 이미 확인된 lost-update.

이 결함의 "그냥 고치면 되는" 부분은 **폼이 실제로 만진 필드만 보내는
것**이다(서버·스키마 변경 없음) — 같은 필드를 두 사람이 진짜 동시에
고치는 충돌까지 막지는 못하지만(그건 낙관적 잠금 인프라가 필요한 별개
제품판단), "안 만진 필드가 남의 변경을 덮어쓰는" 절대다수의 사고
경로는 이것으로 막힌다.

[1] 소스 확인 — 필드별 diff 코드가 실제로 있음.
[2] 실제 JS 실행(Node vm, 340라운드가 세운 방식 그대로 임시 harness
    파일 사용)으로 되돌림-증명 — admin.js의 새 코드블록을 옛(취약)
    전체스냅샷 코드로 임시로 되돌려(★[라운드627] tempfile 스크래치
    사본에만 쓴다 — 실제 static/admin.js는 이 검증 내내 안 건드림)
    옛 동작이 실제로 재현되는지, 새 코드가 실제로 막는지 대조.
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
print("  스캔 464라운드 회귀 — 사건수정 폼 전체스냅샷 lost-update")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
ADM_PATH = os.path.join(HERE, "static", "admin.js")
ADM_SRC = io.open(ADM_PATH, encoding="utf-8").read()

OLD_BLOCK = '''async function saveCaseEdit(id){
  const body = {
    category:$('#e_cat').value.trim(), region:$('#e_region').value.trim(),
    address:$('#e_addr').value.trim(), manager:$('#e_mgr').value.trim(),
    warranty_months:$('#e_warr').value, urgent:$('#e_urgent').value==='1',
    victim_name:($('#e_vname')||{value:''}).value.trim(),
    victim_phone:($('#e_vphone')||{value:''}).value.trim()
  };
  const est=$('#e_est'); if(est && !est.disabled) body.est_price = moneyVal('#e_est');
  try{'''

_i = ADM_SRC.find("async function saveCaseEdit(id){")
_j = ADM_SRC.find("\n  try{", _i)
NEW_BLOCK = ADM_SRC[_i:_j + len("\n  try{")] if _i > 0 and _j > 0 else ""

chk(_i > 0, "saveCaseEdit() 함수를 소스에서 찾았다")
chk("defaultSelected" in NEW_BLOCK and "orig(" in NEW_BLOCK,
    "★★★★★ 필드별 diff(orig() 대조) 코드가 실제로 있다")
chk(ADM_SRC.count(NEW_BLOCK) == 1 and len(NEW_BLOCK) > 0,
    "되돌림-증명에 쓸 새 블록이 소스에 정확히 1번만 있다(대체 지점 특정 가능)",
    ADM_SRC.count(NEW_BLOCK) if NEW_BLOCK else "블록을 못 뽑음")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 JS 실행(Node vm) — 되돌림-증명 (admin.js를 임시로 되돌렸다가 복원)")
# ══════════════════════════════════════════════════════════════

#  ⚠ 라운드340이 세운 방식 그대로 — Node harness를 문자열로 갖고 있다가
#    임시파일로 떨궈 실행한다(admin.js 안에 saveCaseEdit()을 직접 실행하는
#    다른 test_scan_round*.py 는 없음을 grep으로 사전확인 — round15는
#    순수 정적 텍스트창 대조일 뿐 실행이 없다). 함수 경계는 고정 길이
#    텍스트창이 아니라 실제 괄호 균형으로 찾는다 — 라운드15가 겪은
#    창구간 충돌 클래스를 이 새 테스트에서 반복하지 않기 위해서다.
NODE_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");

const admPath = process.argv[2];
const src = fs.readFileSync(admPath, "utf8");

function extractFn(name) {
  const startPat = new RegExp("(async\\s+function\\s+" + name + "\\s*\\([^)]*\\)"
    + "|function\\s+" + name + "\\s*\\([^)]*\\)"
    + "|const\\s+" + name + "\\s*=[^\\n]*?=>)");
  const m = startPat.exec(src);
  if (!m) throw new Error("함수를 못 찾음: " + name);
  const matchEnd = m.index + m[0].length;
  const afterArrow = src.slice(matchEnd).match(/^\s*/)[0].length;
  const firstCh = src[matchEnd + afterArrow];
  if (firstCh === "{") {
    let depth = 0, i = matchEnd + afterArrow;
    for (; i < src.length; i++) {
      if (src[i] === "{") depth++;
      else if (src[i] === "}") { depth--; if (depth === 0) break; }
    }
    if (depth !== 0) throw new Error("중괄호 짝을 못 찾음: " + name);
    return src.slice(m.index, i + 1);
  }
  let d1 = 0, d2 = 0, d3 = 0, i = matchEnd;
  for (; i < src.length; i++) {
    const c = src[i];
    if (c === "(") d1++; else if (c === ")") d1--;
    else if (c === "[") d2++; else if (c === "]") d2--;
    else if (c === "{") d3++; else if (c === "}") d3--;
    else if (c === ";" && d1 === 0 && d2 === 0 && d3 === 0) break;
  }
  if (i >= src.length) throw new Error("문장 끝(;)을 못 찾음: " + name);
  return src.slice(m.index, i + 1);
}

const digitsSrc = extractFn("digits");
const moneyValSrc = extractFn("moneyVal");
const saveCaseEditSrc = extractFn("saveCaseEdit");

function makeEl(o) {
  return { value: o.value, defaultValue: o.defaultValue !== undefined ? o.defaultValue : o.value,
           tagName: o.tagName || "INPUT", options: o.options || null, disabled: !!o.disabled };
}
function opt(value, defaultSelected) { return { value, defaultSelected: !!defaultSelected }; }

function runScenario(elMap) {
  const calls = [];
  const sandbox = {
    $: (sel) => elMap[sel] || null,
    api: async (method, url, body) => { calls.push({ method, url, body }); return { ok: true, changed: [] }; },
    toast: (msg) => { calls.push({ toast: msg }); },
    closeModal: () => {},
    VIEWS: { cases: () => {} },
    console, Array, Object,
  };
  vm.createContext(sandbox);
  vm.runInContext(digitsSrc + "\nthis.digits = digits;", sandbox);
  vm.runInContext(moneyValSrc + "\nthis.moneyVal = moneyVal;", sandbox);
  vm.runInContext(saveCaseEditSrc + "\nthis.saveCaseEdit = saveCaseEdit;", sandbox);
  return vm.runInContext("saveCaseEdit(999)", sandbox).then(() => calls);
}

function baseline() {
  return {
    "#e_cat": makeEl({ value: "가드레일", tagName: "INPUT" }),
    "#e_region": makeEl({ value: "서울", tagName: "INPUT" }),
    "#e_addr": makeEl({ value: "서울시 어딘가", tagName: "INPUT" }),
    "#e_mgr": makeEl({ value: "자동", tagName: "INPUT" }),
    "#e_warr": makeEl({ value: "24", tagName: "INPUT" }),
    "#e_urgent": makeEl({ value: "0", tagName: "SELECT", options: [opt("0", true), opt("1", false)] }),
    "#e_vname": makeEl({ value: "", tagName: "INPUT" }),
    "#e_vphone": makeEl({ value: "", tagName: "INPUT" }),
    "#e_est": makeEl({ value: "1,000,000", tagName: "INPUT", disabled: false }),
  };
}

(async () => {
  const out = {};

  const els1 = baseline();
  out.no_change = await runScenario(els1);

  const els2 = baseline();
  els2["#e_region"] = makeEl({ value: "부산", defaultValue: "서울", tagName: "INPUT" });
  out.region_only = await runScenario(els2);

  const els3 = baseline();
  els3["#e_est"] = makeEl({ value: "2,000,000", defaultValue: "1,000,000", tagName: "INPUT" });
  out.est_price_only = await runScenario(els3);

  const els4 = baseline();
  els4["#e_urgent"] = makeEl({ value: "1", tagName: "SELECT", options: [opt("0", true), opt("1", false)] });
  out.urgent_only = await runScenario(els4);

  console.log(JSON.stringify(out));
})().catch(e => { console.error(e.stack || String(e)); process.exit(1); });
"""


def _run_harness(adm_path=None):
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
    # (A) 현재(고쳐진) 코드로 먼저 실행
    fixed = _run_harness()
    chk(fixed["no_change"] == [{"toast": "변경사항이 없습니다."}],
        "★★★★★ 아무것도 안 바꾸면 PATCH 자체를 안 보낸다", fixed["no_change"])
    chk(fixed["region_only"][0]["body"] == {"region": "부산"},
        "★★★★★ region만 바꾸면 body에 region만 담긴다(category 등 안 딸려옴)",
        fixed["region_only"][0]["body"])
    chk(fixed["est_price_only"][0]["body"] == {"est_price": "2000000"},
        "est_price만 바꾸면 body에 est_price만 담긴다(콤마 제거 포함)",
        fixed["est_price_only"][0]["body"])
    chk(fixed["urgent_only"][0]["body"] == {"urgent": True},
        "urgent(select)만 바꾸면 body에 urgent만 담긴다(defaultSelected 대조)",
        fixed["urgent_only"][0]["body"])

    # (B) 되돌림-증명 — ⚠⚠ [라운드627] 이전 버전은 여기서 실제 살아있는
    #    static/admin.js 파일에 직접 썼다(io.open(ADM_PATH,"w")) — _run_harness가
    #    이미 경로 인자를 받게 돼 있으므로(477·509 선례), tempfile 스크래치
    #    사본에 되돌린 내용을 쓰고 그 경로를 하니스에 넘긴다(실제 파일은
    #    이 검증 내내 전혀 안 건드린다).
    reverted_src = ADM_SRC.replace(NEW_BLOCK, OLD_BLOCK)
    assert reverted_src != ADM_SRC, "되돌림 치환이 실제로 안 먹었다"
    _scratch_dir = tempfile.mkdtemp(prefix="r464_js_")
    try:
        _scratch_adm = os.path.join(_scratch_dir, "admin.js")
        io.open(_scratch_adm, "w", encoding="utf-8", newline="\n").write(reverted_src)
        broken = _run_harness(adm_path=_scratch_adm)
        _body = broken["region_only"][0]["body"]
        chk(_body.get("region") == "부산" and _body.get("category") == "가드레일",
            "★★★★★ 옛 코드(되돌림)는 region만 고쳤는데도 안 건드린 category까지 "
            "폼의 옛값 그대로 함께 보낸다 — 이게 남의 동시수정을 덮어쓰는 원인",
            _body)
        chk(set(_body.keys()) >= {"category", "region", "address", "manager",
                                   "warranty_months", "urgent", "est_price"},
            "★★★★★ 옛 코드(되돌림)는 안 바뀐 필드 전부를 스냅샷째로 함께 보낸다"
            " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
            sorted(_body.keys()))
    finally:
        shutil.rmtree(_scratch_dir, ignore_errors=True)

except Exception as e:                                              # noqa: BLE001
    chk(False, "[2] 되돌림-증명 준비/실행", f"{type(e).__name__}: {e}")

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
