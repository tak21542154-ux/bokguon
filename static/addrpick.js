/* 주소 검색 — 어드민·보험사·협력사 공용 입력 위젯.
 *
 *  ㈜올림포스네트웍스 전략사업실 유경탁 파트장
 *
 *  왜 필요한가
 *   지금까지 주소는 사람이 그대로 타이핑했다. 그래서 같은 자리가
 *   "송파구 올림픽로300" / "서울 송파 올림픽로 300" / "잠실 롯데타워 앞" 으로 제각각 남고,
 *   좌표는 **시군구 중심**밖에 못 잡아 지도가 현장이 아니라 '동네'를 가리켰다.
 *   (실제로 사건 76건 중 좌표가 있는 건 1건뿐이었다)
 *   주소를 **골라서** 넣으면 도로명·지번·우편번호·좌표가 한 번에 확정된다.
 *
 *  쓰는 법
 *    AddrPick.attach({
 *      input:  '#c_addr',        // 주소가 들어갈 칸 (필수)
 *      region: '#c_region',      // 시군구를 자동으로 채울 칸 (선택)
 *      detail: '#c_addr_detail', // 상세주소(동·호수) 칸 (선택)
 *      onPick: (r) => {...}      // 고른 뒤 할 일 (선택)
 *    });
 *    AddrPick.coords('#c_addr')  → {lat, lng} 또는 {} — 저장할 때 함께 보낸다
 *
 *  설계 원칙
 *   · **검색이 실패해도 직접 입력은 항상 열려 있다.** 외부 조회가 막히는 날에도
 *     사건 접수는 멈추면 안 된다.
 *   · 상세주소(동·호수)는 검색 결과에 없다 — 따로 받아 뒤에 붙인다.
 *   · 좌표는 고른 주소에만 딸려 온다. 주소를 손으로 고치면 좌표를 **버린다**
 *     (옛 좌표가 남으면 지도가 조용히 틀린 곳을 가리킨다).
 */
(function (global) {
  'use strict';

  var PICKED = {};      // input 선택자 → {lat, lng, road, zipcode}

  function $(sel, root) { return (root || document).querySelector(sel); }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function css() {
    if (document.getElementById('addrpick-css')) return;
    var st = document.createElement('style');
    st.id = 'addrpick-css';
    st.textContent =
      '.apwrap{position:relative}' +
      '.apbtn{margin-left:6px;white-space:nowrap}' +
      '.aplist{position:absolute;left:0;right:0;top:100%;z-index:60;background:#fff;' +
      ' border:1px solid #CBD6E2;border-radius:11px;box-shadow:0 14px 40px rgba(6,26,48,.18);' +
      ' max-height:290px;overflow:auto;margin-top:4px}' +
      '.aprow{padding:9px 12px;cursor:pointer;border-bottom:1px solid #EEF2F6;font-size:.83rem}' +
      '.aprow:last-child{border-bottom:0}' +
      '.aprow:hover,.aprow.on{background:#EAF4FD}' +
      '.aprow .r1{font-weight:700;color:#0A2A47}' +
      '.aprow .r2{font-size:.76rem;color:#6B7C8F;margin-top:2px}' +
      '.apnote{padding:10px 12px;font-size:.78rem;color:#6B7C8F}' +
      '.apbadge{display:inline-block;font-size:.7rem;font-weight:700;color:#0064B2;' +
      ' background:#EAF4FD;border-radius:6px;padding:1px 6px;margin-left:5px}';
    document.head.appendChild(st);
  }

  function close(box) { if (box) box.remove(); }

  //  ⚠⚠ [라운드582] 예전엔 attach() 호출마다(=이 위젯이 붙는 입력칸을 열 때마다)
  //    문서 전체에 걸리는 "바깥 클릭 감지" 클릭 리스너를 새로 하나씩 등록했다. 이 위젯이
  //    붙는 폼(사건 등록·입점신청 등)은 SPA 라우팅으로 다시 열릴 때마다 #c_addr 같은
  //    입력칸을 통째로 새 DOM 노드로 갈아엎는데(round202 주석 참고), attach() 는 그때마다
  //    또 새 리스너를 문서에 얹었다 — 옛 리스너는 지워지지 않고(참조를 안 남겨 removeEventListener
  //    할 방법이 없다) 그 클로저가 잡은 옛 wrap(입력칸·버튼·드롭다운까지 포함한 서브트리 전체)을
  //    영원히 GC 되지 못하게 붙잡는다. 운영자가 하루 동안 이 폼을 수십 번 열고 닫으면
  //    수십 개의 죽은 리스너·DOM 서브트리가 그대로 쌓인다. 여기 하나로 합쳐 등록하고,
  //    그 순간 문서에 실제로 남아 있는 .apwrap 만 훑는다 — 지워진 옛 wrap 은
  //    querySelectorAll 에 애초에 안 잡히므로 리스너·누수 둘 다 새로 생기지 않는다.
  document.addEventListener('click', function (e) {
    document.querySelectorAll('.apwrap').forEach(function (w) {
      if (!w.contains(e.target)) close($('.aplist', w));
    });
  });

  function render(wrap, items, hint, onPick) {
    close($('.aplist', wrap));
    var box = document.createElement('div');
    box.className = 'aplist';
    if (!items.length) {
      box.innerHTML = '<div class="apnote">' + esc(hint || '결과가 없습니다.') + '</div>';
    } else {
      box.innerHTML = items.map(function (r, i) {
        var sub = [r.jibun, r.zipcode ? '우편 ' + r.zipcode : '',
                   (r.lat && r.lng) ? '' : '좌표 없음'].filter(Boolean).join(' · ');
        return '<div class="aprow" data-i="' + i + '">' +
          '<div class="r1">' + esc(r.road || r.jibun) +
            (r.building ? '<span class="apbadge">' + esc(r.building) + '</span>' : '') + '</div>' +
          (sub ? '<div class="r2">' + esc(sub) + '</div>' : '') + '</div>';
      }).join('');
      box.querySelectorAll('.aprow').forEach(function (el) {
        el.addEventListener('click', function () {
          onPick(items[+el.dataset.i]);
          close(box);
        });
      });
    }
    wrap.appendChild(box);
    return box;
  }

  function attach(opt) {
    css();
    var input = $(opt.input);
    if (!input || input.dataset.apOn) return;      // 두 번 붙이지 않는다
    input.dataset.apOn = '1';
    //  ⚠⚠ [라운드202] PICKED 는 DOM 노드가 아니라 선택자 문자열(opt.input)로 캐시된다.
    //    그런데 사건 등록(insurer_portal.html RENDER.newcase)·입점신청 직접접수
    //    (admin.js appIntakeForm) 는 폼을 다시 열 때마다 wrap.innerHTML 을 통째로
    //    갈아엎어 #c_addr·#q_addr 를 매번 새 DOM 노드로 만든다 — 위 dataset.apOn
    //    가드는 "그 노드"만 보므로 새 노드는 항상 통과하지만, PICKED[opt.input]
    //    은 이전 레코드가 남긴 값 그대로다. 그 상태에서 새 레코드는 주소를 안
    //    고르고(주소는 선택 입력이라 빈칸 제출이 가능하다) 그냥 제출하면,
    //    coords() 가 이전 레코드의 좌표를 그대로 돌려줘 **주소는 빈칸인데 엉뚱한
    //    사건의 GPS 좌표를 갖는 사건**이 생긴다 — 그 좌표가 출동 배차 거리계산에
    //    그대로 쓰이고, 화면엔 주소 자체가 없어 아무도 못 알아챈다. 새로 붙는
    //    입력칸이면(=이 줄에 도달했다는 것 자체가 새 노드라는 뜻) 이전 값을 버린다.
    delete PICKED[opt.input];

    var wrap = document.createElement('span');
    wrap.className = 'apwrap';
    wrap.style.display = 'block';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn g sm apbtn';
    btn.textContent = '🔍 주소 검색';
    btn.style.marginTop = '5px';
    wrap.appendChild(btn);

    var note = document.createElement('div');
    note.style.cssText = 'font-size:.72rem;color:#6B7C8F;margin-top:3px';
    note.textContent = '주소를 검색해 고르면 지도 위치와 인근 업체 거리가 정확해집니다.';
    wrap.appendChild(note);

    function pick(r) {
      var road = r.road || r.jibun || '';
      input.value = road;
      PICKED[opt.input] = { lat: r.lat, lng: r.lng, road: road, zipcode: r.zipcode || '' };
      if (opt.region) {
        var reg = $(opt.region);
        if (reg && r.region) reg.value = r.region;
      }
      note.innerHTML = (r.lat && r.lng)
        ? '✅ 위치 확정 — 지도·거리 계산에 이 좌표를 씁니다.'
          + (r.zipcode ? ' (우편 ' + esc(r.zipcode) + ')' : '')
        : '⚠ 이 주소는 좌표가 없어 지도에서는 지역 중심으로 표시됩니다.';
      note.style.color = (r.lat && r.lng) ? '#137A38' : '#7A5410';
      if (opt.detail) { var dt = $(opt.detail); if (dt) dt.focus(); }
      if (typeof opt.onPick === 'function') opt.onPick(r);
    }

    async function run() {
      var q = (input.value || '').trim();
      if (q.length < 2) {
        render(wrap, [], '두 글자 이상 입력한 뒤 검색해 주세요.', pick);
        return;
      }
      render(wrap, [], '찾는 중…', pick);
      try {
        var res = await fetch('/api/address/search?q=' + encodeURIComponent(q),
                              { headers: { 'Accept': 'application/json' } });
        var d = await res.json();
        render(wrap, d.items || [], d.hint || '결과가 없습니다. 직접 입력하셔도 됩니다.', pick);
      } catch (e) {
        //  외부 조회가 막혀도 접수는 멈추면 안 된다 — 직접 입력으로 안내한다
        render(wrap, [], '주소 검색을 쓸 수 없습니다. 주소를 직접 입력해 주세요.', pick);
      }
    }

    btn.addEventListener('click', run);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); run(); }
      else if (e.key === 'Escape') close($('.aplist', wrap));
    });
    //  손으로 고치면 고른 좌표는 버린다(주소와 좌표가 어긋나는 것이 가장 나쁘다)
    input.addEventListener('input', function () {
      if (PICKED[opt.input] && input.value !== PICKED[opt.input].road) {
        delete PICKED[opt.input];
        note.textContent = '직접 입력한 주소입니다 — 지도에서는 지역 중심으로 표시됩니다.';
        note.style.color = '#7A5410';
      }
    });
  }

  /* 저장할 때 함께 보낼 좌표. 고른 적이 없으면 빈 객체 — 서버가 알아서 무시한다. */
  function coords(sel) {
    var p = PICKED[sel];
    return (p && p.lat && p.lng) ? { lat: p.lat, lng: p.lng } : {};
  }

  function clear(sel) { delete PICKED[sel]; }

  global.AddrPick = { attach: attach, coords: coords, clear: clear };
})(window);
