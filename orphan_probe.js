// 고아문자 측정기 — 브라우저 콘솔이나 자동화에서 붙여 실행한다.
//
//   ㈜올림포스네트웍스 전략기획팀 유경탁
//
// 고아문자 = 문단(블록)의 **마지막 줄**에 한두 글자만 남는 것.
//
// 재는 데 두 번 헛짚었으므로 그 함정을 여기 남긴다.
//  ① 텍스트 노드에는 소스의 줄바꿈·들여쓰기가 들어 있다. 그대로 재면
//     '공백만 있는 줄'이 마지막 줄로 잡혀 가짜 고아문자가 무더기로 나온다.
//     → 블록 단위로 innerText 를 재고, 인라인 조각만 따로 재지 않는다.
//  ② 한 줄 안에 글자 크기가 다른 요소가 섞이면(예: 숫자 + <small>원</small>)
//     rect 의 top 이 서로 달라 **같은 줄을 두 줄로** 센다.
//     → top 값을 반올림해 묶지 말고, 세로로 겹치는지로 묶어야 한다.
window.__scan = function () {
  const BLOCKS = 'p,li,h1,h2,h3,h4,h5,td,th,div,span,label,button,a,small,b';
  const out = [];
  let 검사 = 0;
  for (const el of document.querySelectorAll(BLOCKS)) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.display === 'inline') continue;
    // 자식에 또 블록이 있으면 그 자식이 따로 검사된다(중복 방지)
    if ([...el.children].some(c => {
      const d = getComputedStyle(c).display;
      return d && d !== 'inline' && d !== 'none';
    })) continue;
    const t = (el.innerText || '').trim();
    if (t.length < 6) continue;
    검사++;

    const r = document.createRange();
    r.selectNodeContents(el);
    const rects = [...r.getClientRects()].filter(x => x.width > 1 && x.height > 0);
    if (rects.length < 2) continue;

    // 세로로 겹치는 것끼리 한 줄로 묶는다(글자 크기가 달라도 같은 줄로 인식)
    const sorted = rects.slice().sort((a, b) => a.top - b.top);
    const lines = [];
    for (const x of sorted) {
      const cur = lines[lines.length - 1];
      const overlap = cur && Math.min(cur.bottom, x.bottom) - Math.max(cur.top, x.top) > 1;
      if (overlap) {
        cur.width += x.width;
        cur.top = Math.min(cur.top, x.top);
        cur.bottom = Math.max(cur.bottom, x.bottom);
      } else {
        lines.push({ top: x.top, bottom: x.bottom, width: x.width });
      }
    }
    if (lines.length < 2) continue;

    const fs = parseFloat(cs.fontSize) || 14;
    const last = lines[lines.length - 1];
    if (last.width <= fs * 2.4) {
      const w = t.split(/\s+/);
      out.push({
        text: t.replace(/\s+/g, ' ').slice(0, 40),
        끝어절: w[w.length - 1],
        줄수: lines.length,
        마지막줄글자수: +(last.width / fs).toFixed(1),
        tag: el.tagName.toLowerCase(),
        cls: (el.className || '').toString().slice(0, 24),
      });
    }
  }
  return { 검사, 고아: out };
};

// 대조 실험 — 조판 규칙을 껐다 켜서 잰다.
// 이걸 안 하면 "고아문자가 없다"와 "측정기가 아무것도 못 본다"를 구분할 수 없다.
window.__compare = function () {
  const st = document.createElement('style');
  st.textContent = '*{text-wrap:wrap !important}';
  document.head.appendChild(st);
  const off = window.__scan();
  st.remove();
  const on = window.__scan();
  return {
    검사블록: on.검사,
    규칙끔: off.고아.length,
    규칙켬: on.고아.length,
    남은고아: on.고아,
    고쳐진예: off.고아.slice(0, 6).map(o => `${o.text} → “${o.끝어절}”`),
  };
};
