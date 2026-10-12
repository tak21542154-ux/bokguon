// ══════════════════════════════════════════════════════════════
//  이벤트 위임 디스패처
//  ㈜올림포스네트웍스 기획팀 유경탁
//
//  왜 필요한가 — CSP 에서 script-src 'unsafe-inline' 을 없앴기 때문이다.
//  nonce 는 우리가 작성한 <script> 블록만 구제하고,
//  `onclick="doThing(3)"` 같은 **인라인 이벤트 핸들러는 nonce 를 붙일 자리가 없어**
//  브라우저가 무조건 차단한다.
//
//  그래서 마크업에는 '무엇을 할지'만 data 속성으로 적고,
//  실제 함수 연결은 여기서 한 번에 처리한다.
//
//      <button data-act="approve" data-arg="12">승인</button>
//      ACT.approve = (arg, el, ev) => { ... }        // arg === "12"
//
//  · data-arg / data-arg2 로 최대 2개 인자를 넘긴다 (문자열로 전달된다)
//  · 등록되지 않은 이름은 아무 일도 하지 않는다 — 임의 함수 호출로 번지지 않는다
//  · 문서 단위로 한 번만 듣기 때문에, innerHTML 로 새로 그린 요소도 그대로 동작한다
// ══════════════════════════════════════════════════════════════
window.ACT = window.ACT || {};

(function () {
  // 기본 동작을 막아야 하는 요소 — 링크·제출 버튼처럼 두면 페이지가 이동해 버리는 것들.
  // 그 외(div 컨테이너 등)에서는 preventDefault 를 걸지 않는다.
  //  모달 배경처럼 넓은 영역에 data-act 가 붙어 있으면, 그 안의 텍스트 선택·
  //  체크박스 토글 같은 정상 동작까지 함께 죽기 때문이다.
  function run(el, ev) {
    var name = el.getAttribute('data-act');
    var fn = window.ACT[name];
    if (typeof fn !== 'function') return;      // 미등록 이름은 무시
    var tag = (el.tagName || '').toLowerCase();
    var isSubmit = tag === 'button' && (el.type || 'submit').toLowerCase() === 'submit';
    if (tag === 'a' || isSubmit) ev.preventDefault();
    fn(el.getAttribute('data-arg'), el, ev, el.getAttribute('data-arg2'));
  }

  document.addEventListener('click', function (ev) {
    var el = ev.target.closest && ev.target.closest('[data-act]');
    if (!el) return;
    // 예전에는 div/tr/table 등 컨테이너에 data-act 가 붙으면 '자기 자신을 직접 클릭했을 때만'
    // 발동하게 막았다. 모달 배경 오발동을 막으려던 것인데, 그 바람에 **대시보드 카드·표의 행**
    // 처럼 통째로 클릭돼야 하는 컨테이너가 시각 영역 대부분(자식 요소)에서 무반응이었다.
    // 배경 오발동은 modalBackdrop 핸들러가 스스로 `ev.target===el` 로 거르므로,
    // 여기서는 걸러진 대상을 그대로 실행한다. (자기클릭만 원하면 data-act-self 를 붙인다)
    if (el.hasAttribute('data-act-self') && ev.target !== el) return;
    run(el, ev);
  });

  // 선택 상자·입력칸은 click 이 아니라 change 로 동작해야 한다
  document.addEventListener('change', function (ev) {
    var el = ev.target.closest && ev.target.closest('[data-act-change]');
    if (!el) return;
    var fn = window.ACT[el.getAttribute('data-act-change')];
    if (typeof fn === 'function') fn(el.value, el, ev, el.getAttribute('data-arg'));
  });

  document.addEventListener('input', function (ev) {
    var el = ev.target.closest && ev.target.closest('[data-act-input]');
    if (!el) return;
    var fn = window.ACT[el.getAttribute('data-act-input')];
    // ⚠ data-arg 를 4번째로 넘긴다(change 디스패처와 맞춤).
    //   안 넘기면 data-arg 로 caseId 를 받는 핸들러(입찰창 bidCalc)가
    //   caseId 대신 입력값을 받아 조용히 죽는다. 기존 핸들러는 4번째를 안 써서 무해.
    if (typeof fn === 'function') fn(el.value, el, ev, el.getAttribute('data-arg'));
  });

  // 입력칸 Enter — onkeydown="if(key==='Enter')fn()" 를 대체한다
  document.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Enter') return;
    var el = ev.target;
    if (!el || !el.getAttribute) return;
    var name = el.getAttribute('data-act-enter');
    if (!name) return;
    var fn = window.ACT[name];
    //  ⚠⚠ [라운드290] 형제 두 디스패처(change·input)는 이미 data-arg 를 4번째로
    //    넘기는데(61~63행 주석이 그 이유까지 적어 뒀다) 이 enter 디스패처만
    //    안 넘겼다 — data-arg 로 view/caseId 등을 받고 el.value 는 그 안에서
    //    따로 읽는 핸들러(runSearch·addMemo)가 클릭으로는 되고 Enter 로는
    //    입력값을 그 인자 자리에 잘못 받아 조용히 죽었다.
    if (typeof fn === 'function') { ev.preventDefault(); fn(el.value, el, ev, el.getAttribute('data-arg')); }
  });

  // 폼 제출 — onsubmit="return doX(event)" 를 대체한다
  document.addEventListener('submit', function (ev) {
    var el = ev.target.closest && ev.target.closest('[data-act-submit]');
    if (!el) return;
    var fn = window.ACT[el.getAttribute('data-act-submit')];
    if (typeof fn === 'function') { ev.preventDefault(); fn(el, ev); }
  });

  // 키보드 접근성 — data-act 가 붙은 비버튼 요소도 Enter/Space 로 실행되게 한다
  //
  // ⚠ 여기서 판정 대상을 틀리면 화면 전체 입력이 죽는다.
  //   예전에는 closest 로 찾아 **올라간 조상**의 태그를 보고 예외 처리했는데,
  //   모달 배경(<div class="modal-back" data-act="modalBackdrop">)이 모든 입력칸의 조상이라
  //   모달 안 어디서든 스페이스·엔터가 preventDefault 되어
  //   업체명에 띄어쓰기를 못 넣고 사유란에 줄바꿈을 못 하는 상태였다.
  //
  //   두 가지를 지킨다.
  //     ① 판정은 **이벤트가 발생한 요소(ev.target)** 기준
  //     ② 편집 중인 요소의 키는 절대 가로채지 않는다
  //     ③ 대체 실행은 '그 요소 자신'이 포커스를 가진 경우로만 한정한다(el === t)
  var TYPING = ['input', 'textarea', 'select', 'button', 'a', 'option'];
  document.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    var t = ev.target;
    if (!t || !t.closest) return;
    var ttag = (t.tagName || '').toLowerCase();
    if (TYPING.indexOf(ttag) !== -1 || t.isContentEditable) return;
    var el = t.closest('[data-act]');
    if (!el || el !== t) return;      // 컨테이너가 대신 발동하지 않게 한다
    run(el, ev);
  });
})();
