/* 우측 하단 알림 트레이 — 협력사·보험사 포털 공용.
 *
 *  ㈜올림포스네트웍스 전략사업실 유경탁 파트장
 *
 *  왜 필요한가: 두 포털에는 상단 벨이 있지만, **벨은 눌러야 보인다.**
 *  현장 기사는 다른 탭을 보고 있고, 보험사 담당자는 사건 등록 중이다.
 *  새 출동 콜·낙찰·승인 요청이 오면 지금 보고 있는 화면 위로 스스로 알려야 한다.
 *
 *  설계 원칙
 *   · 처음 켤 때 쌓여 있던 알림이 한꺼번에 튀어나오면 안 된다 →
 *     첫 조회는 '기준선'만 잡고 아무것도 띄우지 않는다.
 *   · 화면을 덮으면 안 된다 → 최대 4장, 9초 뒤 자동으로 사라진다.
 *   · 누르면 그 화면으로 간다 → 이동 처리는 포털이 준 콜백에 맡긴다
 *     (포털마다 화면 이름·라우팅이 다르므로 여기서 알 필요가 없다).
 */
(function (global) {
  'use strict';

  var MAX_CARDS = 4;
  var LIFE_MS = 9000;
  // 시간에 쫓기는 알림 — 앰버로 눈에 띄게 한다
  var URGENT = ['출동', '기한', '마감', '유찰', '경보', '지연', '취소', '실패', '변경', '하자'];

  function isUrgent(t) {
    t = t || '';
    for (var i = 0; i < URGENT.length; i++) if (t.indexOf(URGENT[i]) >= 0) return true;
    return false;
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function box() {
    var el = document.getElementById('tray');
    if (!el) {
      el = document.createElement('div');
      el.id = 'tray';
      el.className = 'tray';
      el.setAttribute('aria-live', 'polite');
      document.body.appendChild(el);
    }
    return el;
  }
  function dismiss(card) {
    if (!card || !card.isConnected) return;
    card.classList.add('out');
    setTimeout(function () { card.remove(); }, 260);
  }

  function push(n, onOpen) {
    var tray = box();
    while (tray.children.length >= MAX_CARDS) tray.firstElementChild.remove();
    var urgent = isUrgent(n.ntype);
    var card = document.createElement('div');
    card.className = 'tc' + (urgent ? ' amber' : '');
    card.innerHTML =
      '<div class="ti">' + (urgent ? '⚠️' : '🔔') + '</div>' +
      '<div class="tw">' +
        '<div class="tt">' + esc(n.ntype || '새 알림') + '</div>' +
        '<div class="tb">' + esc(n.message || '') + '</div>' +
        '<div class="tg">눌러서 바로 이동 →</div>' +
      '</div>' +
      '<button class="tx" aria-label="닫기">×</button>';
    card.querySelector('.tx').addEventListener('click', function (e) {
      e.stopPropagation();       // 닫기가 '열기'로 새지 않게
      dismiss(card);
    });
    card.addEventListener('click', function () {
      dismiss(card);
      if (typeof onOpen === 'function') onOpen(n);
    });
    tray.appendChild(card);
    setTimeout(function () { dismiss(card); }, LIFE_MS);
  }

  /* 목록을 통째로 넘기면, 기준선보다 뒤에 생긴 안 읽은 것만 골라 띄운다.
     반환값은 다음에 쓸 기준선(가장 큰 id). */
  function feed(list, seenId, onOpen) {
    list = list || [];
    var top = 0;
    for (var i = 0; i < list.length; i++) if (list[i].id > top) top = list[i].id;
    if (seenId === null || seenId === undefined) return top;   // 첫 조회 — 조용히 기준선만
    var fresh = list.filter(function (n) { return n.id > seenId && !n.read_at; });
    fresh.sort(function (a, b) { return a.id - b.id; });        // 오래된 것부터 쌓이게
    fresh.slice(-MAX_CARDS).forEach(function (n) { push(n, onOpen); });
    return top > seenId ? top : seenId;
  }

  global.Tray = { push: push, feed: feed, dismiss: dismiss, isUrgent: isUrgent };
})(window);
