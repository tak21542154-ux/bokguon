# -*- coding: utf-8 -*-
"""스캔 655라운드 회귀(직접조사, 하위위임 없음) — landing.html 위전문(widow-fix)
런타임 스크립트가 "문단 전체의 진짜 마지막 줄"만 보고, <b> 로 강조한 구간이
문단 **중간**에서 끝나는 경우는 못 잡던 사각지대.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

■ 조사 각도 — round654 가 인계한 후보 ① "46건 조판 고아후보를 실제 브라우저로
  렌더 확인(round645 부터 이월, 아직 아무도 미착수)"을 따라갔다. 정식 로그인이
  필요 없는 후보(landing.html·docs/index.html·apply_partner.html·
  track_expired.html)부터 실측하기로 하고, `python -m http.server` 로 docs/ 를
  읽기전용 정적서버(127.0.0.1, 스크래치 포트)로 띄워 Claude 브라우저 pane 으로
  직접 열었다(운영서버·운영DB 전혀 안 건드림).

■ 발견 — landing.html 의 "통값 경쟁 입찰" 단계 설명문 안, <b>사진이 없어 현장
  확인이 먼저 필요했던 건</b>은 규칙이 반대입니다... (569행)이 실제 렌더에서
  375px·390px(아이폰 SE/8·12/13/14 — 가장 흔한 모바일 폭)에서만 "건" 한 글자가
  둘째 줄에 홀로 남는다. 320px·360px 에선 "필요했던 건"(2어절)째 줄이라
  정상이고, 414px 이상은 아예 안 갈린다 — Range.getClientRects() 로 320~1440px
  전수 스윕해 정확한 폭 구간을 확정했다(javascript_tool 로 라이브 DOM 측정).

■ 근본원인 — 이 자리는 <b> 문단의 **끝이 아니라 중간**이다(`</b>` 뒤에
  "은 규칙이 반대입니다. 출동 업체가..."로 문장이 몇 문장 더 이어진다).
  static/style.css 의 `body{text-wrap:pretty}`(크로미움 전용) 로도 못 채워서
  landing.html 자신이 이미 임베디드 <script> 로 별도의 위전문(widow-fix)
  런타임 처방을 갖고 있었다(round638/641 은 이 스크립트를 몰랐던 것으로
  보인다 — round641 은 이 문제를 CSS `text-wrap:balance` 로 풀었는데, 그건
  "문단의 진짜 끝"에만 적용되는 처방이라 이번 자리(문단 중간)에는 원래도 안
  맞았다). 이 스크립트의 `fix(el)` 은 `el` 하위 텍스트를 전부 이어붙여
  **문단 전체의 마지막 어절 사이 공백 단 하나만** 안 깨지는 공백(NBSP)으로
  바꾼다 — <b> 가 문단 중간에서 끝나면 그 경계는 이 알고리즘의 시야 밖이다.

  ★★더 나쁜 점 — 그냥 손 놓고 있던 게 아니라 **적극적으로 방해**했다. 이
  스크립트의 1단계("지난번에 붙였던 것을 먼저 되돌린다")가 `el` 하위 텍스트
  노드 전체를 훑어 NBSP 를 전부 원상복구하므로, `<b>` 안에 정적으로 `&nbsp;`
  를 박아 넣는 손쉬운 처방을 실제로 시도해 봤더니 로드 즉시(그리고 매
  resize 마다) 도로 지워졌다(이 세션이 직접 겪음 — 처음엔 "브라우저가 &nbsp;
  를 안 읽나?"로 오판, 격리된 최소 재현 페이지로 entity 디코딩 자체는 정상임을
  먼저 확인한 뒤에야 이 스크립트를 찾아냈다). 그래서 패치는 이 파일의 진짜
  root cause 인 `fix(el)` 자체에 냈다.

■ 고침(templates/landing.html, 위전문 <script> 블록, 843→908행 부근) — 기존
  `fix(el)` 의 2~4단계(텍스트노드 이어붙이기→마지막 공백 찾기→NBSP 로 교체)를
  `glueLastGap(nodes)` 라는 이름으로 그대로 뽑아냈다(로직 변경 없음, 이름만).
  `textNodesOf(root)` 로 트리워커 순회를 재사용 가능하게 뽑았다. 새 헬퍼
  `hasMoreText(afterEl, el)` — `Range.setStartAfter/setEnd/toString` 으로 "el
  안에서 afterEl 뒤에 글자가 하나라도 더 있는가"를 판정한다. `fix(el)` 은
  이제 기존 문단전체 처리(2)뒤에, `el.querySelectorAll('b')` 로 강조구간마다
  `hasMoreText` 로 "문단의 진짜 끝이 아님"을 확인한 것만 `glueLastGap` 을
  또 돌린다(3, 신규) — `<b>` 가 문단의 진짜 마지막 내용이면 위 2)와 같은
  자리를 두 번 건드리게 되므로 `hasMoreText` 로 건너뛴다(이중처리 방지).
  기존 1단계(되돌리기)는 그대로 두면 두 종류의 글루(문단전체·<b>전용) 모두를
  다음 run()/resize 전에 정확히 원상복구하므로 멱등성이 그대로 유지된다.

■ 실측 재확인(고친 뒤, 같은 정적서버로 320~1440px 전수 재스윕) — 375·390px
  둘 다 "필요했던 건"(2어절)로 합쳐져 더 이상 안 갈리고, 나머지 폭(320·360·
  414·480·600·768·1024·1280·1440)은 전부 무변화. 이 페이지의 **다른 모든**
  `<b>` 강조구간(89개 블록 전수, `.proc-step p` 등 SEL 이 걸리는 곳 전부)도
  같은 폭 구간에서 "마지막 줄이 폰트크기의 2.2배보다 좁은 것"이 있는지
  자동 스캔 — 새로 생긴 것은 0건.

  ★부수 발견(고치치 않음, round656 참고용) — 360px 에서만 <b>AI가 시공
  전·중·후로 분류·정렬</b> 이 "…분류·"/"정렬"(2글자)로 갈린다. 직접 확인:
  이 스크립트가 "전·중·후로"·"분류·정렬" 사이 공백을 NBSP 로 붙였는데도(글루
  자체는 정확히 걸림), 렌더러가 "분류·정렬" **안의** "·" 뒤를 별도의 줄바꿈
  허용 지점으로 보고 거기서 갈랐다 — NBSP 로 이어붙인 두 어절이라도, 그
  어절 자신이 "·" 를 담고 있으면 그 "·" 자리에서 또 갈릴 수 있다는 뜻이다.
  이 세션이 직접 재현: NBSP 를 되돌려 옛 상태로 만들어도 **같은 자리에서
  똑같이 갈린다**(재현 스크립트로 전/후 비교, 완전히 동일한 결과) — 즉
  이번 고침이 만든 회귀가 아니라 이 라운드 이전부터 있던, 이 스크립트도
  손 못 대는 별개의 사각지대("·" 자체가 소프트 줄바꿈 지점)다. 마지막 어절
  "정렬"이 2글자라 round124/641 이 세운 "1글자만 대상" 정책(2글자는 소음
  폭증 방지를 위해 의도적으로 범위 밖) 에도 안 걸린다 — 이번 라운드는
  건드리지 않고 정확히 기록만 남긴다.

■ 방법론 메모(round656+ 를 위해 — 이 세션이 두 번 겪은 함정) — (a) 같은
  스크래치 포트(예: 8799)를 서버 재시작 뒤에도 재사용하면, 브라우저의
  공유 HTTP 캐시가 **이전 서버 프로세스가 준 옛 응답**을 그대로 돌려준다
  (이 세션이 이것 때문에 "고쳤는데도 안 바뀐다"로 15분 헛돌았다) — 매
  재시작 뒤에는 새 포트를 쓰거나 URL 에 `?v=n` 캐시버스터를 붙여라. (b)
  JS 문자열에 U+00A0(NBSP)를 사람이 직접 타이핑하면 코드편집기·터미널
  출력 어디서도 U+0020(보통 공백)과 구별이 안 되는데, 둘을 혼동하면 Edit
  도구의 문자열매치가 조용히 실패하거나(달라 보이는 게 없는데 "안 맞음"
  오류) 테스트가 엉뚱한 것을 비교한다 — 항상 자바스크립트 자체의 `\\u00a0`
  이스케이프(사람이 읽을 수 있는 ASCII 6글자)로 쓰고, 실제 파일에 리터럴
  바이트를 넣어야 하는 자리(&nbsp; HTML 엔티티 등)는 Python `\\u00a0` 로
  프로그램이 대신 넣게 한다(round655 자신이 이 실수를 두 번 함 — 옛 결함
  재구성 스크립트에서도, 이 파일의 회귀검사 하네스에서도).

  회귀테스트(이 파일) — 실제 텍스트 레이아웃(줄바꿈 위치)은 브라우저 엔진의
  몫이라 round641 처럼 파이썬만으로 재현하지 않는다(위 실측이 그 증거).
  대신 **이 코드가 실제로 실행됐을 때 옳게 동작하는가**를 node 로 진짜
  실행해서 증명한다(CSS 였던 round641 보다 한 걸음 더 강한 증거 — JS 는
  레이아웃 없이도 순수 로직을 그대로 실행할 수 있다). node 는 이미
  test_template_js.py 가 쓰는 검증된 의존성(shutil.which("node") 로 확인,
  없으면 건너뛰지 않고 실패).
  [1] 실제 Flask 앱으로 landing.html 을 렌더(test_template_js.py·round641 과
  같은 기법)해 진짜 서비스 결과물에서 위전문 <script> 를 추출.
  [2] 그 안에 새 함수·호출부(textNodesOf·glueLastGap·hasMoreText·<b> 순회)가
  정확한 모양으로 있는지 구조 확인.
  [3] **직접 실행** — 미니멀 DOM 셈(TreeWalker·Range·querySelectorAll('b')만
  구현, jsdom 등 새 의존성 없음)으로 round655 결함의 정확한 모양(문단 중간에
  끝나는 <b>, 뒤에 더 문장이 있음)을 재현한 가짜 트리를 만들어, 추출한 실제
  코드를 node 로 그대로 실행 — 대상 <b> 가 실제로 글루됨·hasMoreText 가
  중간/트레일링을 정확히 구분함·fix() 를 두 번 불러도(리사이즈 흉내) 안정함·
  트레일링 대조군은 정확히 1번만 글루됨(이중처리 없음)을 모두 실제 실행으로
  확인.
  [4] 되돌림-증명 — round655 착수 직전 실제로 떠 둔 파일 백업에서 그대로
  추출한(손으로 재구성하지 않은) 옛 버전 스크립트를 같은 하네스로 돌려,
  같은 결함재현 트리에서 실제로 글루가 안 걸림(=결함이 실제로 재현됨)과
  glueLastGap·hasMoreText 자체가 없음(구조로도 재확인)을 함께 확인 — 이
  검사가 "있음/없음"을 실제로 가릴 수 있다는 증거.
  [5] check_orphan_chars.py 를 재실행해 조판 후보 수가 이번 고침(런타임 JS만
  변경, 소스의 `>텍스트<` 패턴은 그대로)으로 안 흔들림(46건 유지, round654가
  정정한 기준)을 재확인.

    python test_scan_round655_fixes.py
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 66)
print("  스캔 655라운드 회귀 — landing.html 위전문(widow-fix) <b> 사각지대")
print("=" * 66)

# ══════════════════════════════════════════════════════════════
print("\n[1] 실행 준비 — 스크래치 DB + 실제 app.py import + landing.html 렌더")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round655_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "verify.log")
os.environ.setdefault("BOKGUON_ENV", "dev")
os.environ.setdefault("BOKGUON_SEED_DEMO", "0")
sys.path.insert(0, HERE)

import db as DB                 # noqa: E402
DB.init_db()
import app as A                 # noqa: E402
from flask import render_template  # noqa: E402

with A.app.test_request_context("/"):
    HTML = render_template("landing.html", nonce="testnonce", build="t", ver="t")
chk(bool(HTML) and "proc-step" in HTML, "① landing.html 이 실제로 렌더되고 proc-step 을 담고 있다")

SCRIPTS = re.findall(r"<script[^>]*>(.*?)</script>", HTML, re.S)
WIDOW_JS = next((s for s in SCRIPTS if "glueLastGap" in s), "")
chk(bool(WIDOW_JS), "② 렌더된 페이지에서 위전문(widow-fix) 임베디드 <script> 를 찾았다(glueLastGap 포함)")


# ══════════════════════════════════════════════════════════════
print("\n[2] 구조 확인 — 새 함수·호출부가 실제 렌더 결과에 정확히 있다")
# ──────────────────────────────────────────────────────────────
chk("function textNodesOf(root){" in WIDOW_JS, "③ textNodesOf() 신설")
chk("function glueLastGap(nodes){" in WIDOW_JS, "④ glueLastGap() 신설(기존 fix() 2~4단계를 뽑아낸 것)")
chk("function hasMoreText(afterEl, el){" in WIDOW_JS, "⑤ hasMoreText() 신설(이중처리 방지 가드)")
chk("el.querySelectorAll('b').forEach(function(b){" in WIDOW_JS
    and "if(hasMoreText(b, el)) glueLastGap(textNodesOf(b));" in WIDOW_JS,
    "⑥ fix() 안에서 <b> 강조구간마다 hasMoreText 가드 뒤에 glueLastGap 을 호출한다")


# ══════════════════════════════════════════════════════════════
print("\n[3] node 실행 하네스 — 실제 코드를 진짜로 실행해 증명한다(문자열 매치가 아니라)")
# ──────────────────────────────────────────────────────────────
#  ⚠ test_template_js.py 가 이미 쓰는 것과 같은 의존성 확인 방식 — 없으면
#    조용히 건너뛰지 않고 실패로 답한다("검사 안 함"과 "통과"는 다르다).
NODE = shutil.which("node")
if not NODE:
    print("\n  ✖ node 를 찾을 수 없습니다. 이 검사는 실제 JS 실행으로 증명합니다.")
    print("     (설치: https://nodejs.org — 검사를 건너뛰지 않고 실패로 답합니다)")
    sys.exit(2)

#  ⚠⚠ [라운드655] 미니멀 DOM 셈 — 이 스크립트가 실제로 쓰는 API 표면만
#    구현한다(TreeWalker 로 텍스트노드 순회, Range 로 "afterEl 뒤에 글자가
#    더 있는가", querySelectorAll('b') 는 태그명 검색만). jsdom 같은 새
#    의존성을 추가하지 않는다(ponytail — 필요한 만큼만).
DOM_SHIM_JS = r"""// Minimal DOM shim -- just enough surface for the landing.html widow-fix
// IIFE to execute under plain Node.js (no jsdom dependency). Ponytail-scoped:
// only the exact APIs that script calls (TreeWalker over text nodes, a Range
// with setStartAfter/setEnd/toString, and querySelectorAll('b')).
'use strict';

class TextNode {
  constructor(value) { this.nodeType = 3; this._v = value; this.parentNode = null; }
  get nodeValue() { return this._v; }
  set nodeValue(v) { this._v = v; }
}
class Elem {
  constructor(tag, children) {
    this.nodeType = 1;
    this.tagName = tag;
    this.childNodes = children || [];
    this.parentNode = null;
    for (const c of this.childNodes) c.parentNode = this;
  }
  querySelectorAll(sel) {
    // Only tag-name selectors are ever used by this script ("b").
    const out = [];
    (function walk(n) {
      for (const c of (n.childNodes || [])) {
        if (c.nodeType === 1) { if (c.tagName === sel) out.push(c); walk(c); }
      }
    })(this);
    return out;
  }
}

function flattenOrder(root) {
  // document order list of every node (text + element) under root.
  const out = [];
  (function walk(n) {
    out.push(n);
    for (const c of (n.childNodes || [])) walk(c);
  })(root);
  return out;
}

function makeTreeWalker(root, whatToShow) {
  const SHOW_TEXT = 4;
  // real TreeWalker never yields the root itself, only its descendants.
  const list = flattenOrder(root)
    .filter(n => n !== root)
    .filter(n => (whatToShow === SHOW_TEXT ? n.nodeType === 3 : true));
  let i = -1;
  return { nextNode() { i++; return i < list.length ? list[i] : null; } };
}

function textOf(node) {
  if (node.nodeType === 3) return node.nodeValue;
  return (node.childNodes || []).map(textOf).join('');
}

function rangeTextAfter(afterEl, root) {
  // Real Range.setStartAfter(afterEl) skips afterEl's *entire* subtree --
  // it walks up through ancestors collecting each level's later siblings,
  // stopping at root. (A naive pre-order flatten would wrongly include
  // afterEl's own children as "after" it -- caught by the trailing-<b>
  // control case, which must see no more text.)
  let result = '';
  let node = afterEl;
  while (node && node !== root) {
    const parent = node.parentNode;
    const idx = parent.childNodes.indexOf(node);
    for (let i = idx + 1; i < parent.childNodes.length; i++) result += textOf(parent.childNodes[i]);
    node = parent;
  }
  return result;
}

global.NodeFilter = { SHOW_TEXT: 4 };
global.document = {
  createTreeWalker(root, whatToShow) { return makeTreeWalker(root, whatToShow); },
  createRange() {
    let _afterEl = null, _root = null;
    return {
      setStartAfter(el) { _afterEl = el; },
      setEnd(root) { _root = root; },
      toString() { return rangeTextAfter(_afterEl, _root); },
    };
  },
  querySelectorAll() { return []; },   // only used by run()'s auto-invoke; irrelevant to direct calls below
};
global.window = { addEventListener() {} };

module.exports = { TextNode, Elem };
"""

HARNESS_JS = r"""'use strict';
// Usage: node harness.js <script-file-to-test>
// Loads the given widow-fix script text (extracted from a real Flask render,
// or a reconstructed OLD baseline), exposes its internals, builds a mock tree
// reproducing the exact round655 bug shape, and prints JSON results.
const fs = require('fs');
const { TextNode, Elem } = require('./dom_shim.js');

const scriptPath = process.argv[2];
let src = fs.readFileSync(scriptPath, 'utf8');

// Expose whatever internals exist by name-probing inside the IIFE, right
// before its closing `})();` -- works whether the script is the current
// (has glueLastGap/hasMoreText/textNodesOf) or the old pre-fix baseline
// (only has fix/run/isWS). Wrapped in try/catch per-name so missing names
// in the OLD baseline don't throw ReferenceError and abort the whole script.
const EXPOSE = `
  global.__exposed = {};
  ['fix','run','glueLastGap','hasMoreText','textNodesOf','isWS'].forEach(function(nm){
    try { global.__exposed[nm] = eval(nm); } catch (e) { /* not defined in this version */ }
  });
`;
const lastClose = src.lastIndexOf('})();');
if (lastClose < 0) throw new Error('could not find IIFE close });');
src = src.slice(0, lastClose) + EXPOSE + src.slice(lastClose);

// eslint-disable-next-line no-eval
eval(src);
const EXP = global.__exposed;

function buildTree() {
  // Mirrors templates/landing.html's ".proc-step.gold p":
  //   <p>...<b>사진이 없어 현장 확인이 먼저 필요했던 건</b>은 규칙이 반대입니다. ...</p>
  // trimmed to just the parts relevant to the bug (leading/trailing filler
  // text kept short but present, so "more text after" is genuinely exercised).
  const leadText = new TextNode('앞쪽 문장입니다. ');
  const bText = new TextNode('사진이 없어 현장 확인이 먼저 필요했던 건');
  const bElem = new Elem('b', [bText]);
  const tailText = new TextNode('은 규칙이 반대입니다. 뒤에 더 긴 문장이 이어집니다.');
  const p = new Elem('p', [leadText, bElem, tailText]);

  // control: a <b> that IS the trailing content of its own block (nothing
  // after it) -- hasMoreText must say "no" so it is left to the whole-block
  // pass only, proving no double-processing.
  const trailB = new Elem('b', [new TextNode('마지막 항목 두 글자')]);
  const trailP = new Elem('p', [new TextNode('앞 문장 '), trailB]);

  return { p, bElem, trailP, trailB };
}

const out = { hasFns: Object.keys(EXP) };

if (EXP.hasMoreText && EXP.glueLastGap && EXP.textNodesOf) {
  const { p, bElem, trailP, trailB } = buildTree();

  out.hasMoreText_midParagraph = EXP.hasMoreText(bElem, p);
  out.hasMoreText_trailing = EXP.hasMoreText(trailB, trailP);

  // direct-call proof: glue just the target <b>'s own text nodes.
  EXP.glueLastGap(EXP.textNodesOf(bElem));
  out.targetGlued = Array.from(bElem.childNodes[0].nodeValue).some(c => c.charCodeAt(0) === 0xa0);
  out.targetText_afterGlue = bElem.childNodes[0].nodeValue;
}

if (EXP.fix) {
  // exercise the real fix(el) entry point end-to-end (revert step + whole
  // block glue + new per-<b> loop), on a *fresh* tree.
  const { p, trailP } = buildTree();
  EXP.fix(p);
  const bNode = p.childNodes[1].childNodes[0];
  out.fix_targetGlued = Array.from(bNode.nodeValue).some(c => c.charCodeAt(0) === 0xa0);
  // run fix() a second time (simulating a resize) -- must remain glued at
  // exactly the same spot, not accumulate additional NBSPs.
  const firstPass = bNode.nodeValue;
  EXP.fix(p);
  out.fix_resizeStable = bNode.nodeValue === firstPass;

  // control through the *real* entry point too: a block whose only content
  // is itself a trailing <b> must still get exactly one glue (from the
  // whole-block pass) -- the new per-<b> pass must not add a second one.
  EXP.fix(trailP);
  const trailText = trailP.childNodes[1].childNodes[0].nodeValue;
  const nbspCount = (trailText.match(/\u00a0/g) || []).length;
  out.trailing_singleGlueOnly = nbspCount === 1;
}

process.stdout.write(JSON.stringify(out));
"""


def run_harness(script_text):
    """스크립트 문자열 하나를 node 로 실제 실행해 JSON 결과를 돌려준다."""
    io.open(os.path.join(_tmpdir, "dom_shim.js"), "w", encoding="utf-8").write(DOM_SHIM_JS)
    io.open(os.path.join(_tmpdir, "harness.js"), "w", encoding="utf-8").write(HARNESS_JS)
    target_path = os.path.join(_tmpdir, "target.js")
    io.open(target_path, "w", encoding="utf-8").write(script_text)
    r = subprocess.run([NODE, os.path.join(_tmpdir, "harness.js"), target_path],
                        cwd=_tmpdir, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        return None, (r.stderr or "")[:400]
    try:
        return json.loads(r.stdout.strip()), None
    except (ValueError, TypeError) as e:
        return None, f"JSON 파싱 실패: {e} / stdout={r.stdout[:300]!r}"


NEW_RESULT, err = run_harness(WIDOW_JS)
chk(NEW_RESULT is not None, "⑦ 현재(고친) 스크립트를 node 로 실제 실행했다", err or "")
if NEW_RESULT:
    chk(NEW_RESULT.get("hasMoreText_midParagraph") is True,
        "⑧ hasMoreText() — 문단 중간에서 끝나는 <b> 뒤에는 '더 있음'을 정확히 판정")
    chk(NEW_RESULT.get("hasMoreText_trailing") is False,
        "⑨ hasMoreText() — 문단의 진짜 마지막 내용인 <b> 뒤에는 '더 없음'을 정확히 판정(이중처리 방지)")
    chk(NEW_RESULT.get("targetGlued") is True,
        "⑩ glueLastGap() 직접호출 — round655 결함 문구의 <b> 안 마지막 공백이 안 깨지는 공백"
        "(NBSP)으로 바뀐다", NEW_RESULT.get("targetText_afterGlue"))
    chk(NEW_RESULT.get("fix_targetGlued") is True,
        "⑪ 실제 진입점 fix(el) 을 통째로 호출해도 같은 결과 — round655 결함 재현 트리에서 글루가 걸린다")
    chk(NEW_RESULT.get("fix_resizeStable") is True,
        "⑫ fix() 를 두 번(로드+리사이즈 흉내) 불러도 같은 자리 그대로 — 멱등성 유지")
    chk(NEW_RESULT.get("trailing_singleGlueOnly") is True,
        "⑬ 대조군 — <b> 가 문단의 진짜 끝이면 fix() 를 통째로 돌려도 글루가 정확히 1번만 걸린다"
        "(문단전체 처리와 신규 <b>전용 처리가 같은 자리를 두 번 건드리지 않는다)")


# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌림-증명 — round655 착수 직전 실제 백업에서 그대로 추출한 옛 버전으로 재현")
# ──────────────────────────────────────────────────────────────
#  ⚠ 실제 파일은 절대 안 건드린다 — round655 착수 직전에 떠 둔 실제 백업
#    (templates/landing.html.round655bak_*)에서 위전문 <script> 블록을
#    그대로 추출한 문자열이다(손으로 다시 타이핑하지 않음 — 타이핑하다
#    U+00A0/U+0020 을 혼동하는 바로 그 함정을 이 라운드 스스로 겪었기
#    때문에, 사람이 다시 옮겨 쓰는 자리를 하나 더 늘리지 않는다). NBSP 두
#    자리는 자바스크립트 자신의 `\u00a0` 이스케이프로 바꿔 써서(값은 완전히
#    동일) 이 파일 소스에도 리터럴 NBSP 바이트가 안 들어간다.
OLD_WIDOW_JS = r"""
/* 고아문자(과부/고아) 방지 — 마지막 줄에 한 어절·한두 글자만 떨어지는 것을 막는다.
   CSS 의 text-wrap:pretty 는 크로미움에서만 고아를 밀어 올려서, 사파리·구형·
   카톡/네이버 인앱 웹뷰에서는 고아가 그대로 보인다. 그래서 폭·브라우저와 무관하게
   본문의 '마지막 두 어절'을 붙여(U+00A0) 한 어절만 남는 상황 자체를 없앤다.
   pretty 와 겹쳐도 서로 방해하지 않는다. JS 가 꺼져 있으면 크로미움은 pretty 가,
   그 밖은 원래대로 — 즉 나빠지지 않는다. */
(function(){
  // 본문 성격의 블록만 손댄다(제목·라벨·버튼·표는 제외 — 짧아서 고아가 없다).
  //  카드 제목(h3·h4)도 넣는다 — 제목은 text-wrap:balance 로 균형을 맞추는데
  //  이 역시 크로미움 전용이라, 미지원 브라우저에선 제목도 마지막 글자만 떨어진다.
  //  단, 큰 글씨의 섹션 제목(h2)은 제외한다 — 두 어절을 묶으면 그 덩어리가
  //  좁은 화면에서 한 줄보다 길어져 오히려 글자 중간이 깨질 수 있고,
  //  실제 기기 폭(320px 이상)에서는 h2 가 원래 고아를 내지 않기 때문이다.
  var SEL='.proc-step p,.proc-branch li,.proc-branch .fk,.proc-branch .cap,'
        +'.proc-branch .bt,.sec-desc,.prob-card p,.feat p,.aud-list li,'
        +'.cmp-list li,.trust-card p,.hero-sub,.cov-item .ds,.aud-card p,'
        +'h3,h4';
  var MAXTAIL=10;   // 마지막 어절이 이보다 길면 원래도 고아가 아니라서 건드리지 않는다
  var NBSP='\u00a0';

  function isWS(c){ return c===' '||c==='\t'||c==='\n'||c==='\r'; }

  function fix(el){
    // 1) 지난번에 붙였던 것을 먼저 되돌린다(리사이즈마다 누적되지 않게 — 멱등).
    var tw0=document.createTreeWalker(el,NodeFilter.SHOW_TEXT,null);
    var t; while(t=tw0.nextNode()){
      if(t.nodeValue.indexOf(NBSP)>=0) t.nodeValue=t.nodeValue.replace(/\u00a0/g,' ');
    }
    // 2) 텍스트 노드를 이어붙여 '글자→(노드,위치)' 지도를 만든다.
    var tw=document.createTreeWalker(el,NodeFilter.SHOW_TEXT,null);
    var flat='', map=[], n;
    while(n=tw.nextNode()){
      var s=n.nodeValue;
      for(var i=0;i<s.length;i++){ flat+=s[i]; map.push([n,i]); }
    }
    // 3) 마지막 '어절 사이 공백' 하나를 찾는다.
    //    끝쪽 여백은 건너뛰고, 양옆이 글자인 '단일 공백'만 대상으로 한다
    //    (들여쓰기로 생긴 여러 칸 공백은 손대면 오히려 깨질 수 있어 피한다).
    var end=flat.length; while(end>0 && isWS(flat[end-1])) end--;   // 실제 끝 글자
    if(end<=0) return;
    var p=-1;
    for(var k=end-2;k>0;k--){
      if(isWS(flat[k]) && !isWS(flat[k-1]) && !isWS(flat[k+1])){ p=k; break; }
    }
    if(p<0) return;                       // 어절이 하나뿐 — 붙일 것이 없다
    var tail=flat.slice(p+1,end);
    if(tail.length<1 || tail.length>MAXTAIL) return;
    // 4) 그 공백 한 칸을 안 깨지는 공백으로 바꾼다 → 마지막 두 어절이 함께 움직인다.
    var node=map[p][0], off=map[p][1];
    node.nodeValue=node.nodeValue.slice(0,off)+NBSP+node.nodeValue.slice(off+1);
  }

  function run(){
    try{ document.querySelectorAll(SEL).forEach(fix); }catch(_){}
  }
  run();
  // 폭이 바뀌면 줄바꿈도 바뀌므로 다시 계산(과도한 호출은 디바운스로 억제).
  var tmr; window.addEventListener('resize',function(){
    clearTimeout(tmr); tmr=setTimeout(run,180);
  });
})();
"""

OLD_RESULT, err2 = run_harness(OLD_WIDOW_JS)
chk(OLD_RESULT is not None, "⑭ 되돌린 옛 버전도 node 로 실제 실행됐다", err2 or "")
if OLD_RESULT:
    chk(OLD_RESULT.get("hasFns") == ["fix", "run", "isWS"],
        "⑮ 옛 버전에는 glueLastGap·hasMoreText·textNodesOf 자체가 없다(구조적으로도 확인)",
        str(OLD_RESULT.get("hasFns")))
    chk(OLD_RESULT.get("fix_targetGlued") is False,
        "⑯ 옛 fix(el) 로 같은 결함재현 트리를 돌리면 글루가 안 걸린다 — 결함이 실제로 재현된다"
        "(이 검사가 '있음'과 '없음'을 실제로 가릴 수 있다는 증거, round640/641 관례와 동일)")
    chk(OLD_RESULT.get("trailing_singleGlueOnly") is True,
        "⑰ 대조군 — 옛 버전도 문단전체 처리 하나만으로 트레일링 <b> 케이스는 이미 정상(회귀 아님)")


# ══════════════════════════════════════════════════════════════
print("\n[5] check_orphan_chars.py 재실행 — 이번 고침이 후보 개수를 흔들지 않는다")
# ──────────────────────────────────────────────────────────────
env = dict(os.environ)
env["PYTHONIOENCODING"] = "utf-8"
r = subprocess.run([sys.executable, "-u", os.path.join(HERE, "check_orphan_chars.py")],
                    cwd=HERE, capture_output=True, text=True, encoding="utf-8", env=env)
out_text = r.stdout or ""
m = re.search(r"조판 후보 (\d+)건", out_text)
n_candidates = int(m.group(1)) if m else -1
chk(n_candidates == 46,
    "⑱ check_orphan_chars.py 의 조판 후보 수가 이번 고침으로 안 바뀌었다(런타임 JS 만 바꿨고 "
    "소스의 >텍스트< 패턴은 그대로 — round654가 정정한 기준 46건 유지)",
    f"실제 {n_candidates}건")


print("\n" + "=" * 66)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}  {dt}")
print("=" * 66)
sys.exit(1 if FAIL else 0)
