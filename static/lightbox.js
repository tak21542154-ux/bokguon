/* 사진 확대 보기 — 어드민·보험사·협력사 공용.
 *
 *  ㈜올림포스네트웍스 전략사업실 유경탁 파트장
 *
 *  왜 필요한가
 *   화면의 사진은 전부 썸네일(78~140px)이다. 그 크기로는
 *    · 보험사가 하자를 잡아내지 못하고,
 *    · 시행사는 "어디가 문제인지" 지적 사진을 봐도 알 수 없으며,
 *    · 검수자는 파손 정도를 판단할 수 없다.
 *   현장 작업자는 **폰으로** 본다. 손가락으로 넘기고, 두 번 눌러 키울 수 있어야 한다.
 *
 *  쓰는 법 — 컨테이너만 알려 주면 그 안의 <img> 를 한 묶음으로 잡는다.
 *      Lightbox.bind(document.getElementById('ph-12'));
 *      Lightbox.bind(box, {caption: img => img.dataset.note});
 *   같은 묶음 안에서 ← → 로 넘어간다(다른 묶음으로는 안 넘어간다 — 섞이면 헷갈린다).
 *
 *  설계 원칙
 *   · 외부 라이브러리 없음(CSP 를 건드리지 않는다).
 *   · 원본 URL 을 그대로 쓴다 — 썸네일과 원본이 같은 파일이므로 추가 요청이 없다.
 *   · 화면을 못 쓰게 만들지 않는다 — ESC·바깥 클릭·닫기 버튼 어느 쪽으로도 닫힌다.
 */
(function (global) {
  'use strict';

  var box = null, imgs = [], idx = 0, zoomed = false;

  function css() {
    if (document.getElementById('lb-css')) return;
    var st = document.createElement('style');
    st.id = 'lb-css';
    st.textContent =
      /*  ⚠ 모달(150)·트레이(200)·토스트(200) 위에 떠야 한다. 사진을 키웠는데
          그 위에 다른 것이 겹치면 확대의 의미가 없다. */
      '.lb{position:fixed;inset:0;z-index:2000;background:rgba(8,16,26,.94);' +
      ' display:none;flex-direction:column;touch-action:none;' +
      ' padding:env(safe-area-inset-top) env(safe-area-inset-right)' +
      ' env(safe-area-inset-bottom) env(safe-area-inset-left)}' +
      '.lb.on{display:flex}' +
      '.lb-top{display:flex;align-items:center;gap:12px;padding:12px 16px;color:#fff;' +
      ' font:600 .85rem "Malgun Gothic",sans-serif;flex:0 0 auto}' +
      '.lb-cnt{opacity:.75}' +
      '.lb-x{margin-left:auto;background:rgba(255,255,255,.12);border:0;color:#fff;' +
      ' width:38px;height:38px;border-radius:10px;font-size:1.2rem;cursor:pointer}' +
      '.lb-x:hover{background:rgba(255,255,255,.24)}' +
      '.lb-body{flex:1;display:flex;align-items:center;justify-content:center;' +
      ' overflow:hidden;position:relative;min-height:0}' +
      '.lb-body img{max-width:96%;max-height:100%;object-fit:contain;' +
      ' border-radius:8px;transition:transform .18s;cursor:zoom-in;user-select:none}' +
      '.lb-body img.zoom{transform:scale(2);cursor:zoom-out}' +
      '.lb-nav{position:absolute;top:50%;transform:translateY(-50%);background:rgba(255,255,255,.14);' +
      ' border:0;color:#fff;width:46px;height:64px;border-radius:12px;font-size:1.5rem;' +
      ' cursor:pointer;display:grid;place-items:center}' +
      '.lb-nav:hover{background:rgba(255,255,255,.28)}' +
      '.lb-nav.prev{left:10px} .lb-nav.next{right:10px}' +
      '.lb-cap{flex:0 0 auto;padding:12px 18px 20px;color:#E8EEF4;text-align:center;' +
      ' font:400 .85rem/1.7 "Malgun Gothic",sans-serif;max-width:900px;margin:0 auto}' +
      '.lb-cap b{color:#FFB4AC}' +
      '@media(max-width:640px){.lb-nav{width:40px;height:56px}.lb-body img{max-width:100%}}';
    document.head.appendChild(st);
  }

  function build() {
    if (box) return box;
    css();
    box = document.createElement('div');
    box.className = 'lb';
    box.innerHTML =
      '<div class="lb-top"><span class="lb-cnt"></span>' +
      '<button class="lb-x" aria-label="닫기">✕</button></div>' +
      '<div class="lb-body">' +
      '<button class="lb-nav prev" aria-label="이전">‹</button>' +
      '<img alt="사진 확대">' +
      '<button class="lb-nav next" aria-label="다음">›</button></div>' +
      '<div class="lb-cap"></div>';
    document.body.appendChild(box);

    box.querySelector('.lb-x').addEventListener('click', close);
    box.querySelector('.prev').addEventListener('click', function (e) { e.stopPropagation(); go(-1); });
    box.querySelector('.next').addEventListener('click', function (e) { e.stopPropagation(); go(1); });
    //  사진을 누르면 키우고, 배경을 누르면 닫는다
    var im = box.querySelector('img');
    im.addEventListener('click', function (e) { e.stopPropagation(); toggleZoom(); });
    box.querySelector('.lb-body').addEventListener('click', close);

    //  폰에서 손가락으로 넘긴다 — 현장에서 가장 많이 쓰는 동작이다
    var x0 = null;
    box.addEventListener('touchstart', function (e) { x0 = e.touches[0].clientX; }, { passive: true });
    box.addEventListener('touchend', function (e) {
      if (x0 === null || zoomed) return;             // 확대 중에는 넘기지 않는다(이동과 헷갈린다)
      var dx = e.changedTouches[0].clientX - x0;
      if (Math.abs(dx) > 45) go(dx < 0 ? 1 : -1);
      x0 = null;
    });
    return box;
  }

  function toggleZoom() {
    zoomed = !zoomed;
    box.querySelector('img').classList.toggle('zoom', zoomed);
  }

  function show() {
    var it = imgs[idx];
    if (!it) return;
    zoomed = false;
    var im = box.querySelector('img');
    im.classList.remove('zoom');
    im.src = it.src;
    im.alt = it.alt || '사진 확대';
    box.querySelector('.lb-cnt').textContent = (idx + 1) + ' / ' + imgs.length;
    box.querySelector('.lb-cap').innerHTML = it.cap || '';
    var many = imgs.length > 1;
    box.querySelector('.prev').style.display = many ? '' : 'none';
    box.querySelector('.next').style.display = many ? '' : 'none';
  }

  function go(step) {
    if (!imgs.length) return;
    idx = (idx + step + imgs.length) % imgs.length;   // 끝에서 처음으로 돌아온다
    show();
  }

  function close() {
    if (box) box.classList.remove('on');
    document.body.style.overflow = '';
    document.removeEventListener('keydown', onKey);
  }

  function onKey(e) {
    if (e.key === 'Escape') close();
    else if (e.key === 'ArrowLeft') go(-1);
    else if (e.key === 'ArrowRight') go(1);
  }

  function open(list, start) {
    if (!list || !list.length) return;
    build();
    imgs = list;
    idx = Math.max(0, Math.min(start || 0, list.length - 1));
    box.classList.add('on');
    document.body.style.overflow = 'hidden';          // 뒤 화면이 같이 스크롤되지 않게
    document.addEventListener('keydown', onKey);
    show();
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* 컨테이너 안의 <img> 를 한 묶음으로 묶어 확대 보기를 붙인다.
     opt.caption(img) 로 사진마다 설명을 줄 수 있다(없으면 alt·figcaption 을 쓴다). */
  function bind(root, opt) {
    if (!root) return 0;
    opt = opt || {};
    var list = [].slice.call(root.querySelectorAll('img'));
    if (!list.length) return 0;
    list.forEach(function (im, i) {
      if (im.dataset.lbOn) return;
      im.dataset.lbOn = '1';
      im.style.cursor = 'zoom-in';
      im.addEventListener('click', function (ev) {
        ev.preventDefault(); ev.stopPropagation();
        var items = list.map(function (x) {
          var cap = '';
          if (typeof opt.caption === 'function') cap = opt.caption(x) || '';
          if (!cap) {
            var fc = x.closest('figure') && x.closest('figure').querySelector('figcaption');
            cap = fc ? esc(fc.textContent.trim()) : esc(x.alt || '');
          }
          return { src: x.dataset.full || x.src, alt: x.alt, cap: cap };
        });
        open(items, i);
      });
    });
    return list.length;
  }

  global.Lightbox = { bind: bind, open: open, close: close };
})(window);
