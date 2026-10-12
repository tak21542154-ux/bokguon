# -*- coding: utf-8 -*-
"""스캔 290라운드 회귀 — 공유 디스패처(actions.js) data-act-enter 가 data-arg 를
   안 넘기던 결함 1건[심각], static/actions.js·tray.js·lightbox.js 사상 첫
   정밀조사(이 세션 static/ 안의 마지막 미조사 JS 3종)로 정밀조사 Agent가 발견.

  actions.js 는 4종의 디스패처(click·change·input·keydown-Enter)로 data-act
  계열 속성을 실제 함수에 연결한다. change·input 두 디스패처는 이미
  el.getAttribute('data-arg') 를 4번째 인자로 넘기는데(input 쪽은 61~63행
  자신의 주석이 "안 넘기면 조용히 죽는다"고 이미 경고해 뒀다) enter
  디스패처만 그 넘기기가 빠져 있었다 — fn(el.value, el, ev) 세 개뿐.

  이 결함은 data-act-enter 를 쓰는 곳 자체는 흔해도(admin.js 9곳+
  insurer_portal.html 1곳) 대부분 무해하다 — data-arg 를 아예 안 읽는
  핸들러(doCaseSearch 등)이거나, data-arg 를 읽어도 그 값을 실제로 안 쓰는
  파라미터(doPartnerSearch, 함수 자체가 무인자)이기 때문이다. 그러나 정확히
  2곳은 **클릭 경로(data-arg 1번째 자리)와 Enter 경로(el.value 가 1번째,
  data-arg 는 원래 4번째여야 함)를 모두 지원하도록 설계된 공유 컴포넌트**라
  실제로 깨졌다:
    ① searchBar() — 관리자 콘솔 15개 화면이 공유하는 검색창(admin.js 66행,
       runSearch). Enter 를 치면 화면 이름(view) 대신 방금 입력한 검색어
       자체가 view 로 들어가 VIEWS[view] 가 undefined 라 TypeError 로
       죽는다 — 화면이 그대로 멈추고 아무 반응도 없다. 같은 화면의 "검색"
       버튼을 클릭하면 정상 동작해 왔으므로 버그가 안 드러났다.
    ② 사건 상세의 "메모 추가"(admin.js 2065행, addMemo) — Enter 를 치면
       "case:77" 대신 방금 입력한 메모 본문 자체가 인자로 들어가
       target_type=그 문자열, target_id=NaN(→JSON 직렬화 시 null)이 되어
       서버(app.py MEMO_TARGETS 검사)가 400 "잘못된 대상입니다"로 거부한다
       — 메모가 저장되지 않는다. "메모 추가" 버튼을 클릭하면 정상 동작한다.

  고친 자리 3곳: actions.js 의 enter 디스패처가 이제 4번째 인자로 data-arg
  를 넘긴다(형제 change·input 디스패처와 통일) + admin.js 의 ACT.runSearch·
  ACT.addMomo 두 등록이 "arg(4번째, Enter 경로) 가 있으면 그걸, 없으면(클릭
  경로) a(1번째) 를 쓴다"로 두 경로를 모두 지원하도록 수정. 클릭 경로는
  arg 가 항상 null 이라 동작이 그대로 보존된다(회귀 없음).

      python test_scan_round290_fixes.py
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


ACTIONS_SRC = read(os.path.join("static", "actions.js"))
ADMIN_SRC = read(os.path.join("static", "admin.js"))

print("=" * 72)
print("  스캔 290라운드 회귀 — data-act-enter 디스패처의 data-arg 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk("ev.preventDefault(); fn(el.value, el, ev, el.getAttribute('data-arg'));" in ACTIONS_SRC,
    "★★★ actions.js 의 enter 디스패처가 형제(change·input)처럼 data-arg 를 4번째로 넘긴다")

chk("ACT.runSearch = (a, el, ev, arg) => runSearch(arg != null ? arg : a);" in ADMIN_SRC,
    "★★★ ACT.runSearch 가 Enter(4번째 arg)·클릭(1번째 a) 두 경로를 모두 지원한다")
chk("ACT.addMemo = (a, el, ev, arg) => addMemo(arg != null ? arg : a);" in ADMIN_SRC,
    "★★★ ACT.addMemo 가 Enter(4번째 arg)·클릭(1번째 a) 두 경로를 모두 지원한다")

# ============================================================
print("\n[2] 실행 — actions.js 실제 디스패처 + admin.js 실제 핸들러를 Node.js 로 종단간 검증")
# ------------------------------------------------------------
try:
    node_script = r'''
const fs = require("fs");
const actionsSrc = fs.readFileSync(process.argv[2], "utf-8");
const adminSrc = fs.readFileSync(process.argv[3], "utf-8");

// ── 최소 가짜 DOM: addEventListener 로 등록된 핸들러를 보관만 한다 ──
const handlers = {};
global.document = {
  addEventListener(type, fn) { (handlers[type] = handlers[type] || []).push(fn); },
};
global.window = {};

function makeEl(attrs) {
  attrs = attrs || {};
  return {
    _attrs: attrs,
    value: attrs.value || "",
    tagName: attrs.tagName || "INPUT",
    type: attrs.type,
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null; },
    hasAttribute(k) { return Object.prototype.hasOwnProperty.call(this._attrs, k); },
    closest(sel) {
      const m = sel.match(/^\[([\w-]+)\]$/);
      if (m && this.hasAttribute(m[1])) return this;
      return null;
    },
  };
}
function fire(type, ev) {
  for (const h of (handlers[type] || [])) h(ev);
}
function clickEl(el) {
  fire("click", { target: el, preventDefault(){ this.defaultPrevented = true; } });
}
function enterEl(el) {
  fire("keydown", { key: "Enter", target: el, preventDefault(){ this.defaultPrevented = true; } });
}

// actions.js 는 자기완결적이라 통째로 로드해 실제 디스패처 등록을 그대로 쓴다
eval(actionsSrc);
// 브라우저에서는 window.ACT = {} 가 곧 전역 ACT 이기도 하다(window 자체가 전역객체) —
// Node 샌드박스에선 그렇지 않으므로 admin.js 가 그대로 쓰는 맨 "ACT." 참조를 위해 맞춰준다
global.ACT = window.ACT;

// ── admin.js 에서 이번 라운드가 손댄 두 조각만 추출 (거대 파일 전체 eval 은 불필요·위험) ──
function extract(src, startMarker, endMarker){
  const i0 = src.indexOf(startMarker);
  const i1 = src.indexOf(endMarker, i0 + startMarker.length);
  return src.slice(i0, i1);
}
const runSearchSrc = extract(adminSrc, "function runSearch(view){", "\nfunction clearSearch");
const addMemoSrc = extract(adminSrc, "async function addMemo(arg){", "\nasync function memoDone");
const actRunSearchLine = adminSrc.split("\n").find(l => l.includes("ACT.runSearch ="));
const actAddMemoLine = adminSrc.split("\n").find(l => l.includes("ACT.addMemo ="));

// ── runSearch 가 쓰는 의존성 스텁 ──
const calls = { views: [] };
global.VIEWS = new Proxy({}, { get(_, key){ return () => calls.views.push(String(key)); } });
const DOM = { sb_q: makeEl({ value: "" }), sb_from: makeEl({ value: "" }),
              sb_to: makeEl({ value: "" }), sb_cat: null,
              memo_body: makeEl({ value: "" }), memo_imp: { checked: false } };
global.$ = (sel) => DOM[sel.replace("#", "")] || null;
global.searchState = (view) => ({ q:"", from:"", to:"", category:"" });

// ── addMemo 가 쓰는 의존성 스텁 ──
let lastApiCall = null;
global.api = async (method, url, body) => { lastApiCall = { method, url, body }; return {}; };
global.toast = () => {};
global.loadMemos = () => {};
global.refreshBadges = () => {};

eval(runSearchSrc);
eval(addMemoSrc);
eval(actRunSearchLine);
eval(actAddMemoLine);

(async () => {
  // ═══ 시나리오 A: 검색창(searchBar) — 클릭은 그대로, Enter 가 고쳐졌는지 ═══
  const sbq = makeEl({ value: "협상", "data-act-enter": "runSearch", "data-arg": "leads" });
  const searchBtn = makeEl({ "data-act": "runSearch", "data-arg": "leads" });

  calls.views = [];
  clickEl(searchBtn);
  const clickView = calls.views[0];

  calls.views = [];
  let enterThrew = null;
  try { enterEl(sbq); } catch(e) { enterThrew = e.message; }
  const enterView = calls.views[0];

  // ═══ 시나리오 B: 메모(addMemo) — 클릭은 그대로, Enter 가 고쳐졌는지 ═══
  const memoBtn = makeEl({ "data-act": "addMemo", "data-arg": "case:77" });
  DOM.memo_body.value = "이 건 우선 처리 요망";
  lastApiCall = null;
  clickEl(memoBtn);
  await new Promise(r => setTimeout(r, 0));   // addMemo 는 async
  const clickMemoBody = lastApiCall && lastApiCall.body;

  const memoInput = makeEl({ value: "이 건 우선 처리 요망", "data-act-enter": "addMemo", "data-arg": "case:77" });
  DOM.memo_body.value = "이 건 우선 처리 요망";
  lastApiCall = null;
  enterEl(memoInput);
  await new Promise(r => setTimeout(r, 0));
  const enterMemoBody = lastApiCall && lastApiCall.body;

  console.log(JSON.stringify({
    clickView, enterView, enterThrew,
    clickMemoBody, enterMemoBody,
  }));
})();
'''
    _nd = tempfile.mkdtemp(prefix="round290_node_")
    node_path = os.path.join(_nd, "check.js")
    io.open(node_path, "w", encoding="utf-8").write(node_script)
    r = subprocess.run(
        ["node", node_path,
         os.path.join(HERE, "static", "actions.js"),
         os.path.join(HERE, "static", "admin.js")],
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    chk(r.returncode == 0, "Node.js 스크립트 정상 종료",
        (r.stdout + r.stderr)[-2000:] if r.returncode else "")
    if r.returncode == 0:
        out = json.loads(r.stdout.strip().splitlines()[-1])
        chk(out.get("clickView") == "leads",
            "검색창: 클릭 경로는 그대로 VIEWS.leads 를 부른다(회귀없음)", out.get("clickView"))
        chk(out.get("enterThrew") is None,
            "★★★ 검색창: Enter 가 더는 TypeError 로 죽지 않는다", out.get("enterThrew"))
        chk(out.get("enterView") == "leads",
            "★★★ 검색창: Enter 도 VIEWS.leads 를 정확히 부른다(고치기 전엔 입력값이 view 자리로 감)",
            out.get("enterView"))
        chk((out.get("clickMemoBody") or {}).get("target_type") == "case"
            and (out.get("clickMemoBody") or {}).get("target_id") == 77,
            "메모: 클릭 경로는 그대로 {case, 77} 을 보낸다(회귀없음)", out.get("clickMemoBody"))
        chk((out.get("enterMemoBody") or {}).get("target_type") == "case"
            and (out.get("enterMemoBody") or {}).get("target_id") == 77,
            "★★★ 메모: Enter 도 {case, 77} 을 정확히 보낸다"
            "(고치기 전엔 입력한 메모 본문이 target_type 자리로 가 서버가 400 으로 거부)",
            out.get("enterMemoBody"))
except FileNotFoundError:
    chk(True, "Node.js 미설치 환경 — [2] 스킵(다른 검증으로 충분히 커버되지 않으므로 주의)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드290 [2] Node.js 종단간 검증", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
