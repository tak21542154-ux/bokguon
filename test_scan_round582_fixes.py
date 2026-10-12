# -*- coding: utf-8 -*-
"""스캔 582라운드 회귀 — static/addrpick.js 의 attach() 가 호출될 때마다
`document.addEventListener('click', ...)` 를 새로 하나씩 등록해, 이 위젯이 붙는
폼(사건 등록·입점신청 등)을 SPA 라우팅으로 다시 열 때마다(=매번 새 DOM 노드로
attach() 가 재호출될 때마다, round202 주석이 이미 문서화한 바로 그 시나리오)
리스너가 하나씩 영구히 쌓이던 결함.

  이 파일(addrpick.js) 자체의 `attach()` 안 마지막 줄은
  `document.addEventListener('click', function (e) {
      if (!wrap.contains(e.target)) close($('.aplist', wrap));
   });`
  였다 — attach() 가 새로 호출될 때마다 새 익명함수가 등록되는데, 그 참조를
  어디에도 남기지 않으므로 removeEventListener() 로 지울 방법이 없다. 그 클로저는
  당시의 `wrap`(입력칸·검색버튼·안내문구·열린 드롭다운까지 포함한 서브트리 전체)을
  붙잡고 있어, 그 wrap 이 이미 화면(라이브 DOM)에서 사라진 뒤에도 GC 되지 못하고
  영원히 메모리에 남는다. admin.js:977·1819, insurer_portal.html:691,
  partner_portal.html:2520, apply_partner.html:97 — 5개 호출부 중 최소 2곳(사건
  등록 모달·발주처 신규 접수)은 SPA 네비게이션으로 하루에도 수십 번씩 다시 열리는
  화면이라(round202 자신의 주석이 "폼을 다시 열 때마다"라고 이미 확인해 둔 사실),
  운영자가 오래 콘솔을 켜 두고 일할수록 죽은 리스너·DOM 서브트리가 계속 쌓인다.

  고침 — 공유 지점을 attach() 안에서 모듈 최상위로 옮긴다. `document`
  클릭리스너를 파일이 로드될 때 **딱 한 번만** 등록하고, 그 안에서
  `document.querySelectorAll('.apwrap')` 로 그 순간 실제로 문서에 남아 있는
  wrap 만 훑는다 — 지워진 옛 wrap 은 이 질의에 애초에 안 잡히므로 리스너 개수도
  더 이상 attach() 호출 횟수를 따라가지 않는다. attach() 안에는 그 등록을
  완전히 제거했다(동작은 그대로 — "바깥을 클릭하면 그 위젯의 드롭다운을 닫는다"는
  계약을 델리게이션으로 옮겼을 뿐).

  Node.js 로 addrpick.js 를 실제 실행해(round202 와 같은 최소 DOM 스텁을
  document.querySelectorAll·리스너 카운터로 확장) attach() 를 세 번(=세 번의
  "폼 재열기") 호출한 뒤 document 에 남은 click 리스너 개수를 실측하고,
  되돌리기(고치기 전 코드를 문자열로만 재구성 — on-disk 파일은 안 건드림)로
  같은 시나리오를 다시 돌려 리스너 개수가 실제로 3개까지 쌓임을 대조해
  인과관계를 증명한다. 델리게이션으로 바뀐 뒤에도 "바깥 클릭 시 닫힘·안쪽
  클릭 시 유지"라는 기존 계약이 그대로 동작하는지도 같은 실행에서 확인한다.

      python test_scan_round582_fixes.py
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


SRC = read("static/addrpick.js")

print("=" * 72)
print("  스캔 582라운드 회귀 — addrpick.js document 클릭리스너 누적 누수")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
n_total = SRC.count("document.addEventListener(")
chk(n_total == 1,
    "★★★ document.addEventListener 등록이 파일 전체에서 딱 1번뿐이다"
    "(attach() 가 호출될 때마다 하나씩 늘던 예전 방식이면 이 수는 호출 전엔 "
    "0, 소스에도 attach() 안에 등록문이 그대로 남는다)", n_total)

i_attach = SRC.index("function attach(opt) {")
i_coords_comment = SRC.index("/* 저장할 때 함께 보낼 좌표.")
attach_body = SRC[i_attach:i_coords_comment]
chk("document.addEventListener(" not in attach_body,
    "★★★★ attach() 함수 본문 안에는 document.addEventListener 호출이 없다"
    "(호출마다 새로 등록하던 자리를 완전히 걷어냈다)")

if n_total == 1:
    i_listener = SRC.index("document.addEventListener(")
    chk(i_listener < i_attach,
        "★★★ 그 유일한 등록이 attach() 정의보다 앞 — 모듈이 로드될 때 "
        "한 번만 실행되는 최상위 스코프에 있다")
    chk("document.querySelectorAll('.apwrap')" in SRC,
        "★★ 그 리스너가 특정 wrap 하나를 클로저로 붙잡지 않고, 호출 시점에 "
        "실제로 문서에 남아 있는 .apwrap 을 매번 다시 찾는다(델리게이션)")

# ============================================================
print("\n[2] 실행(Node.js 실제 실행) — attach() 3회(=폼 3번 재열기) 뒤 리스너 수")
# ------------------------------------------------------------
#  round202 가 이미 만든 addrpick.js 전용 최소 DOM 스텁을 그대로 이어받아
#  ① document 클릭리스너 등록을 카운트하고 ② document.querySelectorAll 을
#  추가한다 — 두 가지 모두 round202 하네스엔 없던(당시엔 필요 없던) 부분이다.
JS_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');

var ALL_ELEMENTS = [];

function makeEl(tag) {
  const el = {
    tag: tag, className: '', dataset: {}, value: '', textContent: '',
    style: {}, children: [], parentNode: null, _listeners: {}, _html: '', _removed: false,
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
    this._removed = true;
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

function createElement(tag) {
  var el = makeEl(tag);
  ALL_ELEMENTS.push(el);
  return el;
}

var registry = {};
var DOC_LISTENERS = {};
var headEl = createElement('head');
var fakeDocument = {
  head: headEl,
  createElement: createElement,
  getElementById: function (id) { return registry[id] || null; },
  querySelector: function (sel) {
    if (sel[0] === '#') return registry[sel.slice(1)] || null;
    return fakeDocument.querySelectorAll(sel)[0] || null;
  },
  //  ⚠ round582 이전엔 fakeDocument 에 querySelectorAll 자체가 없었다(문서
  //    스코프에서 .apwrap 을 찾을 필요가 없는 코드였으므로). 지금 코드가
  //    쓰는 클래스-선택자 질의만 지원하면 충분하다.
  querySelectorAll: function (sel) {
    var cls = sel.replace('.', '');
    return ALL_ELEMENTS.filter(function (e) {
      return !e._removed && (e.className || '').split(' ').indexOf(cls) !== -1;
    });
  },
  addEventListener: function (type, fn) {
    (DOC_LISTENERS[type] = DOC_LISTENERS[type] || []).push(fn);
  },
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
  var el = makeEl('input');           // registry 로만 찾는 입력칸 자체는 추적 대상 아님(.apwrap 아님)
  el.parentNode = makeEl('div');
  el.parentNode.children.push(el);
  registry[id] = el;
  return el;
}

(async function () {
  var out = {};

  //  "폼을 세 번 다시 연다" — 매번 완전히 새 입력칸에 attach() 를 부른다.
  //  (SPA 라우팅이 wrap.innerHTML 을 통째로 갈아엎어 매번 새 DOM 노드를
  //   만드는 것과 동일 — round202 주석·테스트가 이미 이 시나리오를 실측했다)
  newInputNode('addr1'); sandbox.window.AddrPick.attach({ input: '#addr1' });
  newInputNode('addr2'); sandbox.window.AddrPick.attach({ input: '#addr2' });
  newInputNode('addr3'); sandbox.window.AddrPick.attach({ input: '#addr3' });

  out.doc_click_listeners_after_3_attaches = (DOC_LISTENERS['click'] || []).length;

  //  ── 기능 회귀 확인 — 델리게이션으로 바뀌어도 "바깥 클릭하면 그 위젯의
  //     드롭다운만 닫힌다" 계약은 그대로여야 한다 ──
  var input1 = registry['addr1'];
  var wrap1 = input1.parentNode;
  input1.value = '검색어';
  var btn1 = wrap1.children.filter(function (c) { return c.tag === 'button'; })[0];
  await btn1._listeners['click'][0]();      // run() → fetch(모킹) → render() 로 드롭다운 생성
  out.dropdown_open_after_search = wrap1.querySelectorAll('.aplist').length > 0;

  var clickListeners = DOC_LISTENERS['click'] || [];
  // 안쪽 클릭(같은 wrap 안의 input 자신) — 드롭다운이 유지돼야 한다
  clickListeners.forEach(function (fn) { fn({ target: input1 }); });
  out.dropdown_open_after_inside_click = wrap1.querySelectorAll('.aplist').length > 0;

  // 바깥 클릭(어느 wrap 에도 안 속한 새 엘리먼트) — 드롭다운이 닫혀야 한다
  var outsideEl = createElement('div');
  clickListeners.forEach(function (fn) { fn({ target: outsideEl }); });
  out.dropdown_open_after_outside_click = wrap1.querySelectorAll('.aplist').length > 0;

  console.log(JSON.stringify(out));
})().catch(function (e) { console.error('HARNESS_ERROR: ' + (e && e.stack || e)); process.exit(1); });
"""


_tmpdir = tempfile.mkdtemp(prefix="round582_")
_harness_path = os.path.join(_tmpdir, "harness.js")
with io.open(_harness_path, "w", encoding="utf-8") as f:
    f.write(JS_HARNESS)


def run_harness(js_path):
    return subprocess.run(["node", _harness_path, js_path],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30)


try:
    result = run_harness(os.path.join(HERE, "static", "addrpick.js"))
    chk(result.returncode == 0,
        "★★★ Node 하네스(고친 뒤 코드)가 예외 없이 끝까지 실행됐다", result.stderr.strip())
    out = None
    if result.returncode == 0:
        try:
            out = json.loads(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as e:
            chk(False, "★★★ 하네스 출력(JSON) 파싱", f"{e}: {result.stdout!r}")

    if out is not None:
        chk(out.get("doc_click_listeners_after_3_attaches") == 1,
            "★★★★ attach() 를 세 번(폼 3번 재열기) 불러도 document 클릭리스너는 "
            "1개로 유지된다(고치기 전엔 3개까지 쌓였다 — 아래 [3]에서 대조)",
            out.get("doc_click_listeners_after_3_attaches"))
        chk(out.get("dropdown_open_after_search") is True,
            "★ (사전조건) 검색하면 드롭다운이 열린다", out.get("dropdown_open_after_search"))
        chk(out.get("dropdown_open_after_inside_click") is True,
            "★★★ 위젯 안쪽(입력칸 자신)을 클릭해도 드롭다운은 안 닫힌다(회귀 없음)",
            out.get("dropdown_open_after_inside_click"))
        chk(out.get("dropdown_open_after_outside_click") is False,
            "★★★ 위젯 바깥을 클릭하면 드롭다운이 닫힌다(델리게이션으로 바뀐 뒤에도 "
            "기존 계약 유지)", out.get("dropdown_open_after_outside_click"))

    # ========================================================
    print("\n[3] 되돌리기 — 고치기 전 코드를 문자열로만 재구성해 같은 시나리오 대조")
    # --------------------------------------------------------
    #  on-disk static/addrpick.js 는 절대 건드리지 않는다 — 지금 소스를 메모리에서
    #  역변환해 임시 파일에만 쓴다.
    _a0 = SRC.index("function close(box) { if (box) box.remove(); }") + \
        len("function close(box) { if (box) box.remove(); }")
    _a1 = SRC.index("function render(wrap, items, hint, onPick) {")
    old_src = SRC[:_a0] + "\n\n  " + SRC[_a1:]

    _tail_anchor = ("        note.style.color = '#7A5410';\n      }\n    });\n  }\n\n"
                     "  /* 저장할 때 함께 보낼 좌표.")
    chk(_tail_anchor in old_src,
        "★ (준비) attach() 꼬리 앵커를 되돌리기 대상 소스에서 찾았다")
    old_listener = ("    document.addEventListener('click', function (e) {\n"
                     "      if (!wrap.contains(e.target)) close($('.aplist', wrap));\n"
                     "    });\n")
    old_src = old_src.replace(
        _tail_anchor,
        "        note.style.color = '#7A5410';\n      }\n    });\n" + old_listener +
        "  }\n\n  /* 저장할 때 함께 보낼 좌표.", 1)
    chk("document.querySelectorAll('.apwrap')" not in old_src,
        "★★ (준비) 되돌린 소스에는 라운드582의 모듈수준 델리게이션 리스너가 없다"
        "(새 코드에서 걷어낸 것만 걷어냈는지 확인 — 과잉수정 방지)")
    chk(old_src.count("document.addEventListener(") == 1,
        "★★ (준비) 되돌린 소스는 등록문 자체가 attach() 함수 본문 안(소스상 1곳)에 있다 "
        "— 그래서 attach() 가 실행될 때마다(아래 [3] 실측처럼 3번 호출되면 3번) "
        "그 등록문도 매번 다시 실행된다", old_src.count("document.addEventListener("))

    _old_path = os.path.join(_tmpdir, "addrpick_old.js")
    with io.open(_old_path, "w", encoding="utf-8") as f:
        f.write(old_src)

    result_old = run_harness(_old_path)
    chk(result_old.returncode == 0,
        "★★ Node 하네스(고치기 전 재구성 코드)도 예외 없이 끝까지 실행됐다",
        result_old.stderr.strip())
    if result_old.returncode == 0:
        try:
            out_old = json.loads(result_old.stdout.strip().splitlines()[-1])
            chk(out_old.get("doc_click_listeners_after_3_attaches") == 3,
                "★★★★★ 되돌린(고치기 전) 코드로 같은 시나리오(attach 3회)를 실행하면 "
                "실제로 document 클릭리스너가 3개까지 쌓인다 — 지금 버전의 '1개 유지'가 "
                "이 되돌리기 대비 실측 차이(3 → 1)로 인과관계가 증명된다",
                out_old.get("doc_click_listeners_after_3_attaches"))
        except (ValueError, IndexError) as e:
            chk(False, "★★ 되돌린 코드 하네스 출력 파싱", f"{e}: {result_old.stdout!r}")
except FileNotFoundError:
    chk(False, "★★★ 라운드582 node 실행파일을 못 찾음", "node --version 확인 필요")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드582 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
