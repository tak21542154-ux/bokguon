# -*- coding: utf-8 -*-
"""스캔 202라운드 회귀 — addrpick.js 의 PICKED 캐시가 DOM 노드가 아니라 선택자
문자열로 유지돼, 폼을 다시 그릴 때(새 사건 등록·새 입점신청 접수) 이전 레코드가
고른 좌표가 새 레코드로 조용히 넘어가던 결함.

  insurer_portal.html 의 RENDER.newcase() 는 "사건 등록"을 열 때마다
  wrap.innerHTML 을 통째로 갈아엎어 #c_addr 를 매번 새 <input> 으로 만든다.
  AddrPick.attach() 의 "두 번 안 붙는다" 가드(dataset.apOn)는 그 노드만 보므로
  새 노드엔 항상 다시 붙지만, PICKED['#c_addr'] 는 그대로 남아 있었다. 주소는
  선택 입력이라(라벨에 * 없음) 새 사건을 주소 없이 제출하면 createCase() 의
  `...AddrPick.coords('#c_addr')` 가 **이전 사건의 좌표**를 그대로 실어 보낸다
  — 주소는 빈칸인데 엉뚱한 사건의 GPS 좌표를 갖게 되고, 그 좌표가 출동 배차
  거리계산에 그대로 쓰인다. 화면엔 주소 텍스트 자체가 없어 아무도 못 알아챈다.
  (AddrPick.clear() 는 이미 만들어져 있었지만 코드베이스 어디서도 호출되지 않았다)

  Node.js 로 addrpick.js 를 실제 실행해(최소 DOM 스텁) attach→pick→재렌더링
  →재attach→coords() 순서를 그대로 재현한다 — 문자열 대조가 아니라 실제 동작을
  검증한다.

      python test_scan_round202_fixes.py
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


ADDRPICK_SRC = read("static/addrpick.js")

print("=" * 72)
print("  스캔 202라운드 회귀 — addrpick.js 재렌더링 시 이전 레코드 좌표 유출")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
#  ⚠ attach() 안에는 이미 다른 delete PICKED[opt.input] 이 하나 더 있다(입력칸에
#    사람이 손으로 다른 값을 치면 지우는 기존 로직, input 이벤트 리스너 안).
#    "attach() 함수 전체"를 그냥 훑으면 그 기존 줄에 걸려 내 수정이 없어도 항상
#    통과한다 — 라운드202 새 줄의 정확한 위치(guard 직후 ~ wrap 생성 직전)만 본다.
i0 = ADDRPICK_SRC.index("input.dataset.apOn = '1';")
i1 = ADDRPICK_SRC.index("var wrap = document.createElement('span');", i0)
new_block = ADDRPICK_SRC[i0:i1]
chk("delete PICKED[opt.input];" in new_block,
    "★★★★ attach() 가 새 노드에 붙을 때(가드 통과 직후·wrap 생성 전) 그 선택자의 "
    "이전 PICKED 값을 지운다")

# ============================================================
print("\n[2] 실행(Node.js 실제 실행) — 재렌더링 시나리오")
# ------------------------------------------------------------
JS_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');

function makeEl(tag) {
  const el = {
    tag: tag, className: '', dataset: {}, value: '', textContent: '',
    style: {}, children: [], parentNode: null, _listeners: {}, _html: '',
  };
  Object.defineProperty(el, 'innerHTML', {
    get() { return this._html; },
    set(v) {
      this._html = v;
      this.children = this.children.filter(function (c) { return !c._fromHtml; });
      var re = /<div class="aprow" data-i="(\d+)">/g, m;
      while ((m = re.exec(v))) {
        var child = makeEl('div');
        child.className = 'aprow';
        child.dataset.i = m[1];
        child._fromHtml = true;
        child.parentNode = el;
        el.children.push(child);
      }
    },
  });
  el.appendChild = function (c) { this.children.push(c); c.parentNode = this; return c; };
  el.insertBefore = function (n) { this.children.push(n); n.parentNode = this; return n; };
  el.addEventListener = function (type, fn) {
    (this._listeners[type] = this._listeners[type] || []).push(fn);
  };
  el.removeEventListener = function () {};
  el.remove = function () {
    if (this.parentNode) {
      this.parentNode.children = this.parentNode.children.filter(function (c) { return c !== el; });
    }
  };
  el.contains = function (node) {
    if (node === el) return true;
    return el.children.some(function (c) { return c.contains ? c.contains(node) : false; });
  };
  el.querySelectorAll = function (sel) {
    var byTag = sel[0] !== '.' && sel[0] !== '#';
    var cls = byTag ? null : sel.replace('.', '');
    var out = [];
    el.children.forEach(function (c) {
      var hit = byTag ? c.tag === sel : (c.className || '').split(' ').indexOf(cls) !== -1;
      if (hit) out.push(c);
      out = out.concat(c.querySelectorAll ? c.querySelectorAll(sel) : []);
    });
    return out;
  };
  el.querySelector = function (sel) { return el.querySelectorAll(sel)[0] || null; };
  return el;
}

var registry = {};
var headEl = makeEl('head');
var fakeDocument = {
  head: headEl,
  createElement: function (tag) { return makeEl(tag); },
  getElementById: function (id) { return registry[id] || null; },
  querySelector: function (sel) {
    if (sel[0] === '#') return registry[sel.slice(1)] || null;
    return null;
  },
  addEventListener: function () {},
};

var sandbox = { console: console };
sandbox.window = sandbox;
sandbox.document = fakeDocument;
sandbox.fetch = function () {
  return Promise.resolve({
    json: function () {
      return Promise.resolve({ items: [{ road: '가상주소', lat: 37.111, lng: 127.111, jibun: '', zipcode: '' }] });
    },
  });
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), sandbox, { filename: 'addrpick.js' });

function newInputNode(id) {
  var el = makeEl('input');
  el.parentNode = makeEl('div');   // .parentNode.insertBefore 가 쓸 부모
  el.parentNode.children.push(el);
  registry[id] = el;
  return el;
}

function findBtn(wrapGuessParent) {
  // btn 은 attach() 가 만든 wrap(=input 의 새 parentNode)의 두 번째 자식이다.
  var wrap = wrapGuessParent.parentNode;
  return wrap.children.filter(function (c) { return c.tag === 'button'; })[0];
}

async function pickOnce(inputId) {
  var input = registry[inputId];
  input.value = '검색어';
  var btn = findBtn(input);
  await btn._listeners['click'][0]();               // run() 실행 — fetch(모킹) 대기
  var wrap = input.parentNode;
  var box = wrap.children.filter(function (c) { return c.className === 'aplist'; }).pop();
  var row = box.querySelectorAll('.aprow')[0];
  row._listeners['click'][0]();                      // 검색결과 클릭 — pick() 실행
}

(async function () {
  var out = {};

  // ── 사건 A: #c_addr 를 붙이고 주소를 골라 좌표를 확정한다 ──
  newInputNode('c_addr');
  sandbox.window.AddrPick.attach({ input: '#c_addr' });
  await pickOnce('c_addr');
  out.after_pick_A = sandbox.window.AddrPick.coords('#c_addr');

  // ── 사건 B: RENDER.newcase() 처럼 wrap.innerHTML 을 갈아엎어 #c_addr 를
  //    완전히 새로운 DOM 노드로 다시 만든다(사건 A 의 좌표는 절대 다시 안 고름) ──
  newInputNode('c_addr');
  sandbox.window.AddrPick.attach({ input: '#c_addr' });
  out.after_rerender_B_no_pick = sandbox.window.AddrPick.coords('#c_addr');

  // ── 회귀 방지: 같은(아직 살아있는) 노드에 attach 가 중복 호출돼도
  //    진행 중인 pick 은 안 지워져야 한다 ──
  await pickOnce('c_addr');
  var afterPickB = sandbox.window.AddrPick.coords('#c_addr');
  sandbox.window.AddrPick.attach({ input: '#c_addr' });   // 같은 노드에 중복 attach
  out.after_duplicate_attach_same_node = sandbox.window.AddrPick.coords('#c_addr');
  out.picked_B_before_duplicate = afterPickB;

  console.log(JSON.stringify(out));
})().catch(function (e) { console.error('HARNESS_ERROR: ' + (e && e.stack || e)); process.exit(1); });
"""

_tmpdir = tempfile.mkdtemp(prefix="round202_")
_harness_path = os.path.join(_tmpdir, "harness.js")
with io.open(_harness_path, "w", encoding="utf-8") as f:
    f.write(JS_HARNESS)

_addrpick_path = os.path.join(HERE, "static", "addrpick.js")
try:
    result = subprocess.run(["node", _harness_path, _addrpick_path],
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
        a = out["after_pick_A"]
        chk(abs(a.get("lat", 0) - 37.111) < 1e-6 and abs(a.get("lng", 0) - 127.111) < 1e-6,
            "★ (사전조건) 사건 A 에서 주소를 고르면 그 좌표가 확정된다", a)

        b_no_pick = out["after_rerender_B_no_pick"]
        chk(b_no_pick == {},
            "★★★★ 재렌더링된 새 입력칸(사건 B, 아직 주소를 안 고름)은 좌표가 "
            "비어 있다 — 사건 A 의 좌표가 새지 않는다(고치기 전엔 사건 A 좌표가 "
            "그대로 남아 있었다)", b_no_pick)

        b_picked = out["picked_B_before_duplicate"]
        chk(abs(b_picked.get("lat", 0) - 37.111) < 1e-6,
            "★ (사전조건) 사건 B 도 스스로 주소를 고르면 정상적으로 좌표가 잡힌다", b_picked)

        dup = out["after_duplicate_attach_same_node"]
        chk(dup == b_picked,
            "★★★ 같은(아직 안 갈아엎인) 노드에 attach 가 중복 호출돼도 진행 중인 "
            "pick 은 안 지워진다(과잉수정 아님 — 새 노드일 때만 지운다)", dup)
except FileNotFoundError:
    chk(False, "★★★ 라운드202 [2] node 실행파일을 못 찾음", "node --version 확인 필요")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드202 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
