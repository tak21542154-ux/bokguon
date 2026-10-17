// ══════════ 복구온 콘솔 — 데이터 연동 로직 ══════════
let CUR = 'dash';
const TITLES = {
  dash:['대시보드','콘솔 · 모니터링'], cases:['사건·입찰 관제','콘솔 · 모니터링'],
  traffic:['접속 통계','콘솔 · 분석'], defects:['하자·A/S 관리','콘솔 · 운영'],
  leads:['도입 문의함','콘솔 · 유입·심사'], apps:['입점 신청함','콘솔 · 유입·심사'],
  partners:['업체 등록·관리','콘솔 · 유입·심사'], insurers:['발주처(보험사) 관리','콘솔 · 유입·심사'],
  photos:['AI 사진 검수','콘솔 · 운영'], dispatch:['현장 출동 수배','콘솔 · 운영'],
  map:['현장 지도','콘솔 · 모니터링'], calendar:['일정 달력','콘솔 · 운영'],
  happycall:['해피콜·만족도','콘솔 · 운영'],
  settle:['정산 관리','콘솔 · 운영'], statement:['월 정산 명세서','콘솔 · 운영'], changeorders:['변경 견적·재경매','콘솔 · 운영'], newcase:['공고·사건 등록','콘솔 · 운영'],
  opskpi:['운영 KPI','콘솔 · 분석'],
  stats:['통계·리포트','콘솔 · 분석'], ops:['운영 알림 로그','콘솔 · 소통'],
  contacts:['연락처 관리','콘솔 · 분석·소통'], campaigns:['마케팅 캠페인','콘솔 · 분석·소통'],
  outbox:['발송 대기함','콘솔 · 소통'], estbands:['가견적 점검 기준','콘솔 · 시스템'],
  notices:['공지사항','콘솔 · 소통'], boq:['표준 단가·내역','콘솔 · 시스템'],
  admins:['관리자 계정','콘솔 · 시스템'], set:['설정 · 감사로그','콘솔 · 시스템'],
  //  ⚠ 여기 빠지면 머리글에 **뷰 이름이 영어 그대로** 뜬다('today 콘솔').
  //    화면을 새로 만들 때마다 잊혀서, 부팅 첫 화면인 '오늘 할 일' 까지
  //    영어로 떠 있었다. 아래 회귀가 메뉴 항목과 이 표를 대조한다.
  today:['오늘 할 일','콘솔 · 운영'], license:['건설업 등록 조사','콘솔 · 유입·심사'],
  onboard:['협력사 온보딩','콘솔 · 유입·심사'], selfcheck:['운영 점검','콘솔 · 시스템'],
};

// ── utils ──
const $ = s => document.querySelector(s);
const won = n => (n||0).toLocaleString('ko-KR');
// 금액 입력 도우미 — 실수 방지: 천단위 콤마 + '원' + 한글 읽기(3600000→360만원)
const digits = v => String(v||'').replace(/[^0-9]/g,'');
function koMoney(n){
  n = Number(n)||0; if(!n) return '';
  const 억=Math.floor(n/1e8), 만=Math.floor((n%1e8)/1e4), 원=n%1e4;
  return [억&&억+'억', 만&&만+'만', 원&&원].filter(Boolean).join(' ')+'원';
}
//  오늘(KST). ⚠ toISOString() 은 **UTC** 기준이라 한국 00:00~09:00 사이에는
//   전날 날짜를 돌려준다 — 어제가 기한이던 건이 그 9시간 동안 '기한 초과'에서 빠졌다.
//   서버는 전부 KST(datetime('now','+9 hours'))로 저장하므로 화면도 KST 로 센다.
const todayKST = () => new Date(Date.now() + 9*3600*1000).toISOString().slice(0,10);

function fmtMoney(el){
  const raw = digits(el.value);
  el.value = raw ? Number(raw).toLocaleString('ko-KR') : '';
  const hint = el.parentElement && el.parentElement.querySelector('.money-ko');
  if(hint) hint.textContent = raw ? ('= '+koMoney(raw)) : '';
}
// 콤마 낀 금액 입력에서 순수 숫자만 뽑는다(제출용)
const moneyVal = id => digits(($(id)||{}).value);

// ── 공통 검색바 ──
//   전 메뉴에서 같은 모양의 키워드·날짜·카테고리 검색을 쓴다.
//   state: {q,from,to,category} 객체를 뷰마다 하나씩 두고, 이 컴포넌트가 읽고 쓴다.
const SEARCH = {};   // 뷰이름 → {q,from,to,category}
function searchState(view){ return SEARCH[view] || (SEARCH[view] = {q:'',from:'',to:'',category:''}); }
// 검색창 폭 — 화면이 넓어져도 늘어나지 않게 한다.
//  `flex:1` 로 두면 1600px 화면에서 검색창 하나가 600px 를 먹어(검색바의 48%)
//  입력할 글자수에 비해 지나치게 길어 보인다. 기준폭 320px 로 두되
//  좁은 화면에서는 줄어들게(0 1) 해서 모바일 줄바꿈은 그대로 살린다.
//  ※ 이 상수는 아래 함수들보다 먼저 선언해야 한다(선언 전 참조 오류 방지).
const SEARCH_W = 'flex:0 1 320px;min-width:150px';

function searchBar(view, opts){
  opts = opts || {};
  const st = searchState(view);
  const cats = opts.categories;   // 배열이면 카테고리 셀렉트 표시
  return `<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:2px 0 10px;padding:10px;background:var(--mist);border-radius:10px">
    <input id="sb_q" value="${esc(st.q)}" placeholder="🔍 ${esc(opts.ph||'검색')}" style="${SEARCH_W}" data-act-enter="runSearch" data-arg="${view}">
    ${cats?`<select id="sb_cat" style="width:auto"><option value="">공종 전체</option>${cats.map(c=>`<option ${st.category===c?'selected':''}>${esc(c)}</option>`).join('')}</select>`:''}
    <label style="font-size:.7rem;color:var(--faint)">기간</label>
    <input id="sb_from" type="date" value="${esc(st.from)}" style="width:auto">
    <span style="color:var(--faint)">~</span>
    <input id="sb_to" type="date" value="${esc(st.to)}" style="width:auto">
    <button class="btn p sm" data-act="runSearch" data-arg="${view}">검색</button>
    ${(st.q||st.from||st.to||st.category)?`<button class="btn g sm" data-act="clearSearch" data-arg="${view}">초기화</button>`:''}
  </div>`;
}
function searchQS(view){
  const st = searchState(view); const qs = new URLSearchParams();
  if(st.q) qs.set('q', st.q); if(st.from) qs.set('from', st.from);
  if(st.to) qs.set('to', st.to); if(st.category) qs.set('category', st.category);
  return qs;
}
function runSearch(view){
  const st = searchState(view);
  st.q = ($('#sb_q').value||'').trim();
  st.from = $('#sb_from').value||''; st.to = $('#sb_to').value||'';
  const cat=$('#sb_cat'); st.category = cat?cat.value:'';
  VIEWS[view]();
}
function clearSearch(view){ SEARCH[view]={q:'',from:'',to:'',category:''}; VIEWS[view](); }
// 수수료율 bp → % (0% 와 '미설정' 을 구분: null 만 기본 10%)
const bpPct = bp => ((bp===null||bp===undefined)?1000:bp)/100;
// 엑셀 내보내기 버튼(항목 지정) — 로그인 세션으로 직접 다운로드
function xlsxBtn(section, label){
  return `<button class="btn g sm" data-act="exportXlsx" data-arg="${section}" title="${label||''} 엑셀(.xlsx) 내보내기">엑셀 내보내기</button>`;
}
//  ⚠⚠ [라운드168] '(작은따옴표)가 빠져 있었다 — form.js 가 창(window.esc)에 심어
//    둔 더 강한 판(작은따옴표까지 이스케이프)이 있지만, 이 파일이 같은 이름으로
//    const esc 를 다시 선언하는 순간 그 판을 완전히 가린다(전역 렉시컬 스코프
//    특성 — window 속성 조회보다 const 바인딩이 우선한다). 지금은 이 값이
//    작은따옴표로 감싼 속성에 꽂히는 자리가 없어 당장 뚫리진 않지만, 나중에
//    누가 자연스럽게 attr='...' 형태를 하나 추가하면 esc() 가 이미 막아주고
//    있다고 믿은 채로 뚫린다. 형제 판(addrpick.js·tray.js·lightbox.js·form.js)과
//    맞춘다.
const esc = s => (s==null?'':String(s)).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let CSRF = '';
//  ⚠⚠ [라운드77] 업로드가 도는 동안은 페이지를 떠나지 않게 잡는다 — 전화·팩스
//    접수 현장사진·하자사진은 다시 못 찍는다. partner_portal.html·insurer_portal.html
//    (76라운드)은 이미 이 잠금(UP_BUSY)이 있는데 관리자 화면만 없었다 — 30초
//    알림 폴링(pollNotifications)이 api() 를 거치므로, 관리자가 사진을 올리는
//    도중 세션이 만료되면(유휴 타임아웃·비밀번호 변경·계정 강등) 그 폴링이 401 을
//    만나 곧바로 로그인 화면으로 튕겼고, 그 강제 이동이 진행 중이던 FormData
//    업로드를 그대로 끊었다. 관리자 업로드 경로는 협력사처럼 기기 큐 백업도
//    없어(admin.html 은 upqueue.js 를 안 불러온다) 유실이 그대로 확정된다.
let UP_BUSY = false;
window.addEventListener('beforeunload', function (e) {
  if (!UP_BUSY) return;
  e.preventDefault();
  e.returnValue = '사진을 올리는 중입니다. 지금 나가면 사진이 올라가지 않습니다.';
});
async function api(method, url, body){
  const headers = {'Content-Type':'application/json'};
  if(method !== 'GET' && CSRF) headers['X-CSRF-Token'] = CSRF;   // [보안] CSRF 토큰
  const opt = {method, headers, credentials:'same-origin'};
  if(body) opt.body = JSON.stringify(body);
  const r = await fetch(url, opt);
  //  ⚠ [라운드77] 업로드 중(UP_BUSY)이면 강제 이동을 미룬다 — partner_portal.html·
  //    insurer_portal.html api() 와 같은 이유·같은 방식.
  if(r.status===401){
    if(UP_BUSY){ throw new Error('auth-deferred'); }
    location.href='/admin/login'; throw new Error('auth');
  }
  if(r.status===429){ const d=await r.json().catch(()=>({})); toast(d.error||'요청이 너무 많습니다'); throw new Error('rate'); }
  const d = await r.json().catch(()=>({}));
  if(!r.ok){
    // 응답 본문을 오류에 붙여 둔다 — 관문(409)들이 '무엇이 걸렸는지'를 함께 내려주므로,
    // 호출부가 그 내용으로 확인 모달을 띄우거나 안내를 바꿀 수 있어야 한다.
    const err = new Error(d.error||'요청 실패');
    err.data = d; err.status = r.status; err.code = d.code;
    throw err;
  }
  return d;
}
function toast(html){ const t=$('#toast'); t.innerHTML=html; t.classList.add('show'); clearTimeout(t._h); t._h=setTimeout(()=>t.classList.remove('show'),2800); }
function openModal(html){
  // 이전 모달의 미니 지도를 먼저 파기한다(innerHTML 을 갈아끼우면 지도 DOM 만 사라지고 인스턴스가 남는다)
  if(typeof nearMapDestroy === 'function') nearMapDestroy();
  $('#modal').innerHTML=html; $('#modalBack').classList.add('show');
}
function closeModal(){
  $('#modalBack').classList.remove('show');
  // 모달 안의 미니 지도는 닫을 때 반드시 파기한다(사라진 DOM 을 붙들면 다음 열기에서 깨진다)
  if(typeof nearMapDestroy === 'function') nearMapDestroy();
}
function statusPill(s){
  //  ⚠⚠ [라운드677] 하자(defects) 상태값 DEFECT_FLOW(app.py 15390행 —
  //    ["접수","확인중","재시공배정","완료","반려"], 이 파일 3801행에도 같은
  //    상수가 그대로 복사돼 있다) 중 '확인중'·'재시공배정' 두 개가 이 매핑에
  //    처음부터 없었다 — round672가 정산(settlements) 쪽에서 잡은 것과 같은
  //    성격의 결함이지만 방향이 반대다: 그때는 형제 stTag() 둘은 이미 갖고 있는
  //    키가 insurer_portal.html에만 없었는데, 이번엔 형제 stTag() 둘
  //    (templates/insurer_portal.html·partner_portal.html, 둘 다 확인중=blue·
  //    재시공배정=amber 값을 이미 갖고 있다) 대신 이 운영 콘솔 쪽
  //    statusPill()이 두 키를 빠뜨렸다. 실제 호출부(3860·3974행
  //    statusPill(d.status), 하자 목록·상세 모달의 "상태"/"현재 상태" 칸)가
  //    이 두 값을 실제로 받는다 — 이 파일 자신의 DEFECT_FLOW 상수·defectAct
  //    버튼(3996~3999행 data-arg2="확인중"/"재시공배정")이 이미 그 사실을
  //    증명한다. 매핑에 없으면 기본값(회색)으로 떨어져(바로 아래 '새로 생긴
  //    상태' 주석과 같은 원칙) '확인중'·'재시공배정'이 '완료'·'반려'·'접수'와 똑같은
  //    회색으로 보였다 — 운영자가 목록만 보고 "지금 진행 중인 하자"와
  //    "이미 끝난 하자"를 색으로 구분할 수 없었다. 형제 stTag() 둘과 같은
  //    색으로 맞춘다(단일 지점 수정, 다른 키는 무변경).
  const map={'신규':'red','검토중':'amber','서류검토':'amber','승인':'green',
    '확인중':'blue','재시공배정':'amber','반려':'gray',
    '활성':'green','심사중':'amber','경고':'red','퇴출':'gray',
    '입찰중':'blue','승인대기':'amber','시공중':'green','검수대기':'amber','완료보고지연':'red','정산진행':'green','완료':'gray','접수':'gray',
    '입금완료':'green','대기':'gray','이체완료':'green','이체예약':'amber',
    //  ⚠ 새로 생긴 상태가 매핑에 없으면 전부 회색으로 뭉개진다 — 취소·유찰은 눈에 띄어야 한다
    '취소':'red','유찰':'amber','미수선종결':'gray','수배중':'amber','수배실패':'red','사진확보':'green',
    '계약':'green','계약중':'green','시범운영':'blue','협의중':'amber','중지':'gray'};
  return `<span class="pill ${map[s]||'gray'}">${esc(s)}</span>`;
}

// ── boot ──
let ME = {};
const RANK = {'최고관리자':3,'중간관리자':2,'하위관리자':1};
const myRank = () => RANK[ME.role]||0;
async function boot(){
  try{
    const me = await api('GET','/api/me');
    ME = me; CSRF = me.csrf || '';
    $('#me-name').textContent = me.name; $('#me-role').textContent = me.role;
    $('#av').textContent = (me.name||'·').slice(0,1);
  }catch(e){ return; }
  // 좌하단 내 이름 클릭 → 내 계정(이름·비밀번호 변경)
  const meBox = document.querySelector('.me');
  if(meBox){ meBox.style.cursor='pointer'; meBox.title='내 계정 관리'; meBox.addEventListener('click', myAccount); }
  // 등급별 메뉴 노출 — 최고관리자만 '관리자 계정' 메뉴를 본다
  applyRoleMenus();
  //  메뉴로 직접 들어올 때는 대시보드에서 걸어 둔 금액 필터를 푼다.
  //  (안 풀면 "정산 내역인데 일부만 보이는" 화면이 되고, 왜 그런지 단서가 없다)
  document.querySelectorAll('.mi[data-v]').forEach(m=>m.addEventListener('click',()=>{
    settleMoney=''; loadView(m.dataset.v);
  }));
  initNavGroups();
  tickClock(); setInterval(tickClock, 30000);
  // 알림 폴링 — 첫 회는 기준선만 잡고, 이후 30초마다 새 것만 띄운다
  pollNotifications();
  NOTI_TIMER = setInterval(pollNotifications, 30000);
  // 다른 곳을 누르면 벨 목록을 닫는다
  document.addEventListener('click', e=>{
    const pop = $('#bellPop');
    if(pop && !pop.hidden && !e.target.closest('.bellwrap')) pop.hidden = true;
  });
  document.addEventListener('keydown', e=>{
    if(e.key === 'Escape'){ const p=$('#bellPop'); if(p) p.hidden = true; }
  });
  await refreshBadges();
  //  ⚠ 콘솔을 켜면 **오늘 치가 먼저** 보여야 한다. 대시보드는 '얼마나 되나'
  //    이고 여기는 '무엇을 하나' 다 — 아침에 필요한 것은 후자다.
  loadView('today');
}
// ══════════════════════════════════════════════════════════════
//  메뉴 접기 + 좁은 화면 덮개
//
//  메뉴가 31개라 한 번에 다 펼치면 무엇부터 봐야 할지 알 수 없다.
//  사건 흐름(① 접수 → ② 수배·입찰 → ③ 시공·검수 → ④ 정산 → ⑤ 사후)대로
//  묶고, 지금 안 쓰는 묶음은 접어 둔다. 접힘 상태는 브라우저에 기억된다.
// ══════════════════════════════════════════════════════════════
const NAV_FOLD_KEY = 'bokguon.navfold';
// 처음 여는 사람에게는 흐름 단계만 펼쳐 보인다(뒤쪽 관리 메뉴는 접어 둔다).
const NAV_FOLD_DEFAULT = ['member', 'analysis', 'comm', 'sys'];

function navFolded(){
  try{
    const raw = localStorage.getItem(NAV_FOLD_KEY);
    if(raw === null) return new Set(NAV_FOLD_DEFAULT);
    return new Set(JSON.parse(raw) || []);
  }catch(e){ return new Set(NAV_FOLD_DEFAULT); }   // 저장값이 깨져도 메뉴는 떠야 한다
}
function navSaveFolded(set){
  try{ localStorage.setItem(NAV_FOLD_KEY, JSON.stringify([...set])); }catch(e){}
}
function applyNavFold(){
  const folded = navFolded();
  document.querySelectorAll('.nav .grp[data-g]').forEach(g=>{
    const on = folded.has(g.dataset.g);
    g.classList.toggle('fold', on);
    g.setAttribute('aria-expanded', String(!on));
  });
  document.querySelectorAll('.mi[data-g]').forEach(m=>{
    // 등급 때문에 숨긴 메뉴(applyRoleMenus)는 건드리지 않는다
    if(m.style.display === 'none') return;
    m.classList.toggle('fold', folded.has(m.dataset.g));
  });
  markGroupBadges();
}
// 접힌 묶음 안에 안 읽은 배지가 있으면 제목에 점을 띄운다 — 접었다고 놓치면 안 된다.
function markGroupBadges(){
  document.querySelectorAll('.nav .grp[data-g]').forEach(g=>{
    const has = [...document.querySelectorAll(`.mi[data-g="${g.dataset.g}"] .bdg.show`)].length > 0;
    g.classList.toggle('hasbdg', has && g.classList.contains('fold'));
  });
}
function initNavGroups(){
  document.querySelectorAll('.nav .grp[data-g]').forEach(g=>{
    g.setAttribute('role', 'button');
    g.setAttribute('tabindex', '0');
    const toggle = () => {
      const folded = navFolded();
      folded.has(g.dataset.g) ? folded.delete(g.dataset.g) : folded.add(g.dataset.g);
      navSaveFolded(folded); applyNavFold();
    };
    g.addEventListener('click', toggle);
    g.addEventListener('keydown', e=>{ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); toggle(); } });
  });
  applyNavFold();
}
// 지금 보고 있는 메뉴가 접힌 묶음 안에 있으면 그 묶음만 펼친다
// (주소로 바로 들어오거나 화면 안 버튼으로 이동했을 때 메뉴가 사라져 보이지 않게).
function navRevealFor(v){
  const mi = document.querySelector(`.mi[data-v="${v}"]`);
  if(!mi || !mi.dataset.g) return;
  const folded = navFolded();
  if(folded.has(mi.dataset.g)){ folded.delete(mi.dataset.g); navSaveFolded(folded); applyNavFold(); }
}
function navToggle(){
  const aside = document.querySelector('aside');
  const open = !aside.classList.contains('open');
  aside.classList.toggle('open', open);
  $('#navScrim').classList.toggle('show', open);
  const btn = document.querySelector('.navtoggle');
  if(btn) btn.setAttribute('aria-expanded', String(open));
}
function navClose(){
  document.querySelector('aside').classList.remove('open');
  $('#navScrim').classList.remove('show');
  const btn = document.querySelector('.navtoggle');
  if(btn) btn.setAttribute('aria-expanded', 'false');
}

// ══════════════════════════════════════════════════════════════
//  알림 — 상단 벨 + 우측 하단 트레이
//
//  운영팀 앞으로 오는 알림이 DB 에는 쌓이는데 콘솔에서 읽을 곳이 없었다.
//  30초마다 물어보고, 새로 생긴 건은 우측 아래에 띄운다. 누르면 그 사건으로 간다.
//  ⚠ 처음 켤 때 쌓여 있던 수십 건이 한꺼번에 튀어나오면 안 된다 —
//    첫 조회는 '기준선'만 잡고 아무것도 띄우지 않는다.
// ══════════════════════════════════════════════════════════════
let NOTI_SEEN = null;        // null = 아직 기준선 없음(첫 조회)
let NOTI_LIST = [];
let NOTI_TIMER = null;
const NOTI_AMBER = ['출동', '기한', '유찰', '경보', '지연', '취소', '실패', '변경'];

function notiIsUrgent(t){ return NOTI_AMBER.some(k => (t||'').includes(k)); }

async function pollNotifications(){
  try{
    const qs = NOTI_SEEN !== null ? '?since=' + NOTI_SEEN : '';
    const d = await api('GET', '/api/admin/notifications' + qs);
    NOTI_LIST = d.notifications || [];
    setBellCount(d.unread || 0);
    if(NOTI_SEEN === null){
      NOTI_SEEN = d.latest_id || 0;      // 기준선만 잡고 조용히 넘어간다
    }else if((d.fresh||[]).length){
      d.fresh.slice().reverse().forEach(n => trayPush(n));
      NOTI_SEEN = d.latest_id || NOTI_SEEN;
      const b = $('#bellBtn');
      if(b){ b.classList.remove('ring'); void b.offsetWidth; b.classList.add('ring'); }
    }
    if(!$('#bellPop').hidden) renderBell();
  }catch(e){ /* 알림이 안 와도 화면은 살아 있어야 한다 */ }
}
function setBellCount(n){
  const dot = $('#bellDot');
  if(!dot) return;
  if(n > 0){ dot.textContent = n > 99 ? '99+' : n; dot.classList.add('show'); }
  else dot.classList.remove('show');
}
function renderBell(){
  const box = $('#bellList'), cnt = $('#bellCnt');
  if(!box) return;
  const un = NOTI_LIST.filter(n=>!n.read_at).length;
  if(cnt) cnt.textContent = un ? `안 읽음 ${un}건` : '모두 읽음';
  box.innerHTML = NOTI_LIST.length ? NOTI_LIST.map(n=>`
    <div class="bi ${n.read_at?'rd':'un'}" data-act="notiOpen" data-arg="${n.id}">
      <div style="min-width:0;flex:1">
        <div class="bt">${esc(n.message||'')}</div>
        <div class="bm"><span class="tag ${notiIsUrgent(n.ntype)?'amber':'blue'}">${esc(n.ntype||'알림')}</span>
          <span>${timeAgo(n.created_at)}</span></div>
      </div>
    </div>`).join('') : '<div class="bempty">받은 알림이 없습니다</div>';
}
// '3분 전' 처럼 읽히게 — 정확한 시각보다 얼마나 급한지가 중요하다
function timeAgo(ts){
  if(!ts) return '';
  const t = Date.parse(ts.replace(' ','T') + '+09:00');
  if(isNaN(t)) return esc(ts.slice(5,16));
  const s = Math.max(0, (Date.now() - t) / 1000);
  if(s < 60) return '방금';
  if(s < 3600) return `${Math.floor(s/60)}분 전`;
  if(s < 86400) return `${Math.floor(s/3600)}시간 전`;
  if(s < 604800) return `${Math.floor(s/86400)}일 전`;
  return esc(ts.slice(5,16));
}
function trayPush(n){
  const tray = $('#tray');
  if(!tray) return;
  if(tray.children.length >= 4) tray.firstElementChild?.remove();   // 화면을 덮지 않게
  const el = document.createElement('div');
  el.className = 'tc' + (notiIsUrgent(n.ntype) ? ' amber' : '');
  el.dataset.act = 'notiOpen'; el.dataset.arg = n.id;
  el.innerHTML = `
    <div class="ti">${notiIsUrgent(n.ntype)?'⚠️':'🔔'}</div>
    <div class="tw">
      <div class="tt">${esc(n.ntype||'새 알림')}</div>
      <div class="tb">${esc(n.message||'')}</div>
      <!--  ⚠ 문구와 동작이 같은 함수를 봐야 한다. 종전에는 n.link 만 보고 적었는데
            실제 이동은 case_id 로도 됐다 — 갈 수 있는데 "방금 도착" 이라고 적었다. -->
      <div class="tg">${notiLinkOf(n)?'눌러서 바로 이동 →':'방금 도착'}</div>
    </div>
    <button class="tx" data-act="trayClose" aria-label="닫기">×</button>`;
  tray.appendChild(el);
  setTimeout(()=>trayDismiss(el), 9000);
}
function trayDismiss(el){
  if(!el || !el.isConnected) return;
  el.classList.add('out');
  setTimeout(()=>el.remove(), 260);
}
//  ⚠ 알림 93건 중 31건은 url 없이 나간다. 사건번호(case_id)까지 없는 것들은
//    눌러도 "열어 볼 화면이 없습니다" 만 뜬다 — 운영자는 그게 고장인 줄 안다.
//    호출부 31곳을 고치는 대신 **종류로 갈 곳을 정한다**(한 곳에서 끝난다).
const NOTI_VIEW = {
  '도입문의':'leads', '입점신청':'apps', '입점승인':'partners', '업체상태변경':'partners',
  '변경견적':'changeorders', '재경매입찰':'changeorders', '추가분유찰':'changeorders',
  '재경매마감':'changeorders', '재경매낙찰':'changeorders',
  '정산':'settle', '정산취소':'settle',
  '하자접수':'defects', '하자완료':'defects', '하자이의':'defects', '재시공보고':'defects',
  '재시공배정':'defects',
  '출동수배':'dispatch', '출동배정':'dispatch', '출동취소':'dispatch', '수배필요':'dispatch',
  '참여업체없음':'dispatch',
  '사진업로드':'photos', '사진검수':'photos', '사진반려':'photos', '사진확보':'photos',
  '보안':'admins', '위치정보':'set', '하한없음':'boq', '도급판정':'ops',
};
//  '갈 곳' 을 한 군데서 정한다 — 화면 문구와 실제 이동이 어긋나지 않게.
function notiLinkOf(n){
  if(!n) return '';
  if(n.link) return n.link;
  if(n.case_id) return '#cases/' + n.case_id;
  const v = NOTI_VIEW[n.ntype];
  return v ? '#' + v : '';
}
// 알림을 눌렀을 때 — 읽음 처리하고 그 사건으로 이동한다
async function notiOpen(id){
  const n = NOTI_LIST.find(x=>x.id === id) || {};
  try{ await api('POST','/api/admin/notifications/read', {id}); }catch(e){}
  const link = notiLinkOf(n);
  $('#bellPop').hidden = true;
  document.querySelectorAll('.tray .tc').forEach(t=>{ if(+t.dataset.arg === id) trayDismiss(t); });
  //  ⚠⚠ **서버는 `/admin#settle` 처럼 절대경로+해시로 저장한다.**
  //    그 값은 알림톡·푸시에서도 그대로 쓰이는 링크라 경로가 붙어 있다.
  //    그런데 여기서는 `#settle` 만 알아봐서, url 이 저장된 알림은 전부
  //    "열어 볼 화면이 따로 없습니다" 로 떨어졌다 —
  //    **운영 DB 실측: 어드민 알림 1,302건 중 123건**(정산 77 · 사건 46).
  //    해시가 붙어 있으면 그 뒷부분만 본다.
  const hash = link.includes('#') ? link.slice(link.indexOf('#')) : '';
  if(hash.startsWith('#cases/')){
    const cid = +hash.split('/')[1];
    loadView('cases');
    // 목록이 그려진 뒤 상세를 연다(바로 열면 데이터가 아직 없다)
    setTimeout(()=>{ if(typeof caseDetail === 'function') caseDetail(cid); }, 700);
  }else if(hash){
    loadView(hash.slice(1));
  }else if(link.startsWith('/')){
    //  해시 없는 절대경로(예: 다른 포털) — 진짜로 이동한다
    location.href = link;
  }else{
    // 갈 곳이 없으면 그렇다고 말한다 — 예전엔 눌러도 조용해서 고장으로 보였다
    toast('이 알림은 열어 볼 화면이 따로 없습니다.');
  }
  pollNotifications();
}

// 등급이 낮으면 민감 메뉴를 숨긴다(서버도 막지만, 안 보이는 편이 혼란이 적다).
//  ⚠⚠ [라운드246] set(설정·감사로그) 은 2 였다 — 그런데 그 메뉴 안 감사 로그는
//    require_admin(등급 1, 누구나)이 진짜 문턱이다. 메뉴 문턱을 등급2로 걸면
//    하위관리자는 볼 자격이 있는 감사 로그까지 통째로 못 봤다. 메뉴는 더 낮은
//    쪽(감사 로그) 기준으로 열고, 등급3 문턱인 입찰·정산 정책 패널은 VIEWS.set
//    자신이 스스로 가린다(VIEWS.admins 와 같은 방식).
function applyRoleMenus(){
  const gate = {admins:3, insurers:3};   // 메뉴 data-v : 필요 등급
  document.querySelectorAll('.mi[data-v]').forEach(m=>{
    const need = gate[m.dataset.v];
    if(need && myRank() < need) m.style.display='none';
  });
}
function tickClock(){
  const d=new Date(); const p=n=>String(n).padStart(2,'0');
  const wd=['일','월','화','수','목','금','토'][d.getDay()];
  $('#clock').textContent = `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} (${wd}) ${p(d.getHours())}:${p(d.getMinutes())}`;
}
async function refreshBadges(){
  try{
    const s = await api('GET','/api/stats');
    setBadge('bdg-leads', s.leads_pending);
    setBadge('bdg-apps', s.apps_pending);
    setBadge('bdg-settle', s.settle_review);
    setBadge('bdg-co', s.co_active);
    setBadge('bdg-defect', s.defect_open);
    // 출동 기한초과·해피콜 대기 — 시간에 걸린 대기열이라 메뉴에서 바로 보여야 한다.
    //  (stats 한 번으로 받는다 — 배지마다 별도 호출을 쌓으면 30초 주기가 무거워진다)
    setBadge('bdg-dispatch', s.dispatch_overdue);
    setBadge('bdg-hc', s.hc_pending);
    //  ⚠ '오늘 할 일' 배지는 그 화면을 열지 않아도 차 있어야 한다. 다른 메뉴에
    //    있는 동안 새로 막힌 건이 생긴 것을 알아야 하기 때문이다.
    setBadge('bdg-today', s.today_urgent);
    markGroupBadges();   // 접힌 묶음에 새 대기건이 생겼으면 제목에 점을 띄운다
  }catch(e){}
}
function setBadge(id, n){ const e=$('#'+id); if(!e)return; if(n>0){e.textContent=n;e.classList.add('show');}else{e.classList.remove('show');} }
async function logout(){ await api('POST','/api/logout'); location.href='/admin/login'; }

function loadView(v){
  CUR = v;
  document.querySelectorAll('.mi[data-v]').forEach(m=>m.classList.toggle('on',m.dataset.v===v));
  navRevealFor(v);   // 접힌 묶음 안의 메뉴로 이동했으면 그 묶음을 펼친다
  navClose();        // 좁은 화면에서 메뉴를 골랐으면 덮개를 닫는다
  // 제목이 빠진 메뉴 하나 때문에 화면 전체가 멈추면 안 된다.
  // (TITLES 에 항목을 안 넣으면 여기서 예외가 나 메뉴가 열리지 않았다)
  const t = TITLES[v] || [v, '콘솔'];
  $('#vtitle').textContent = t[0]; $('#vcrumb').textContent = t[1];
  $('#content').innerHTML = '<div class="loading">불러오는 중…</div>';
  $('#content').scrollTop = 0;
  const view = VIEWS[v];
  if(!view){ $('#content').innerHTML = '<div class="empty">준비 중</div>'; return; }
  // 화면 하나가 실패했으면 실패했다고 말해야 한다.
  // 예전에는 예외가 그냥 삼켜져 '불러오는 중…'에 영원히 멈췄고,
  // 서버가 낡아 API 가 404 인 상황과 화면 버그를 구분할 수 없었다.
  Promise.resolve().then(view).catch(e => viewError(v, e));
}

function viewError(v, e){
  const msg = (e && e.message) ? String(e.message) : String(e);
  // 라우트 자체가 없다 = 십중팔구 서버가 옛 코드로 떠 있다(재시작하면 해결)
  const stale = /찾을 수 없|404|Not Found/i.test(msg);
  $('#content').innerHTML = `
    <div class="panel">
      <div class="ph"><span class="pt">화면을 불러오지 못했습니다
        <small>${esc((TITLES[v]||[v])[0])}</small></span></div>
      <div class="notice" style="border-color:#F0C9C9;background:#FDF3F3;color:#8A2B2B">
        ${esc(msg)}
        ${stale ? `<br><br><b>서버가 예전 코드로 실행 중일 수 있습니다.</b>
          이 메뉴는 최근에 추가돼서, 그 전에 켠 서버에는 아직 없습니다.
          <b>서버 창을 닫고 다시 실행</b>하면 해결됩니다.` : ''}
      </div>
      <button class="btn p" data-act="reloadView" data-arg="${esc(v)}">다시 시도</button>
    </div>`;
}

// ══════════ VIEWS ══════════
const VIEWS = {};

// ── 대시보드 — 작업 진행 현황 + 거래 대금 ──
const ACTION_MENU = {'낙찰_승인대기':'cases','사진_검수대기':'photos','지급_검수대기':'settle','입점_심사대기':'apps','도입문의_대기':'leads',
  '유찰_재공고대기':'cases','재경매_마감확인':'changeorders',
  '출동수배_필요':'dispatch','출동_기한초과':'dispatch','해피콜_대기':'happycall'};
// 각 '오늘 처리할 일'을 눌렀을 때, 전체가 아니라 **그 대기 건만** 걸러 보여준다.
const ACTION_DRILL = {
  '낙찰_승인대기': ()=>{ caseSearch={q:'',from:'',to:'',category:''}; caseFilter='승인대기'; loadView('cases'); },
  '사진_검수대기': ()=>loadView('photos'),      // 검수 화면은 원래 대기만 보여준다
  '지급_검수대기': ()=>loadView('settle'),      // 정산 화면은 대기 지표가 상단
  //  ⚠ 배지 숫자는 두 상태를 합쳐서 센다(app.py 의 같은 카운트 SQL과 맞춘다) —
  //    한 상태만 열면 배지를 눌렀을 때 목록 건수가 배지 숫자보다 적게 보인다(실측).
  '입점_심사대기': ()=>{ appFilter='신규,서류검토'; loadView('apps'); },
  '도입문의_대기': ()=>{ leadFilter='신규,검토중'; loadView('leads'); },
  '유찰_재공고대기': ()=>{ caseSearch={q:'',from:'',to:'',category:''}; caseFilter='유찰'; loadView('cases'); },
  '재경매_마감확인': ()=>loadView('changeorders'),
  // 보험사 완료승인 대기 — 정산 화면에서 독촉할 수 있게 그쪽으로 보낸다
  '보험사_완료승인대기': ()=>loadView('settle'),
  // 수배가 회차를 다 써 멈춘 건 — 출동 관제에서 직접 배정/회복 수배를 한다
  '출동수배_실패': ()=>loadView('dispatch'),
  '출동수배_필요': ()=>loadView('dispatch'),
  '출동_기한초과': ()=>loadView('dispatch'),
  '해피콜_대기': ()=>loadView('happycall'),
};
// 마감 점검이 실제로 돌고 있는지 보여준다.
//  자동 마감은 '조용히 안 도는 것'이 가장 위험한 실패라서, 안 돌면 눈에 띄어야 한다.
function sweepBadge(lastOk){
  let mins = null;
  if(lastOk){
    const t = Date.parse(lastOk.replace(' ','T')+'+09:00');
    if(!isNaN(t)) mins = Math.max(0, Math.round((Date.now()-t)/60000));
  }
  const stale = mins === null || mins > 30;
  return `<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;
              background:${stale?'#FDF3F3':'var(--mist)'};border:1px solid ${stale?'#F0C9C9':'var(--line)'};
              border-radius:11px;padding:9px 14px;margin-bottom:14px;font-size:.76rem">
    <b style="color:${stale?'#8A2B2B':'var(--sub)'}">
      ⏱ 입찰 마감 점검 ${mins===null?'기록 없음':(mins+'분 전 실행')}</b>
    ${stale?`<span style="color:#8A2B2B">— 자동 점검이 돌지 않고 있습니다. 아래 버튼으로 지금 처리하거나 예약 실행을 등록하세요.</span>`:''}
    <span style="flex:1"></span>
    <button class="btn g sm" data-act="runSweep">지금 실행</button>
  </div>`;
}

//  ══════════════════════════════════════════════════════════
//   오늘 할 일 — 숫자가 아니라 **행동**
//
//   ⚠ 0건 항목은 서버가 이미 빼고 준다. 화면은 온 것만 그린다 —
//     "0건" 이 잔뜩 찍힌 목록은 아무것도 말하지 않는다.
//  ══════════════════════════════════════════════════════════
const TONE = {
  red:   {bd:'#F1C9C1', bg:'#FDF4F2', fg:'var(--red)'},
  amber: {bd:'#F5DCB2', bg:'var(--amber-bg)', fg:'var(--amber-text)'},
  blue:  {bd:'#BFD8EE', bg:'var(--blue-bg)', fg:'var(--blue)'},
};
function todayCard(g){
  const t = TONE[g.tone] || TONE.blue;
  return `<div class="panel" style="border:1.5px solid ${t.bd};background:${t.bg}">
    <div class="ph"><span class="pt" style="color:${t.fg}">${esc(g.title)}</span>
      <span class="tag" style="background:${t.fg};color:#fff">${g.n}건</span></div>
    <div class="tbl-wrap"><table class="tbl" style="background:transparent">
      ${/*  ⚠ 셀 수 없는 항목은 **숨기지 않는다.** 예전엔 조용히 빠져서
             '그런 일이 없다' 와 '못 셌다' 가 화면에서 똑같아 보였다.  */''}
      ${g.items.map(it=>`<tr class="rowclick" data-act="loadView" data-arg="${esc((it.go||'#').slice(1))}">
        <td style="width:74px" class="r">${it.broken
          ? `<b style="font-size:1.05rem;color:var(--red)">?</b>`
          : `<b style="font-size:1.15rem;color:${t.fg}">${it.n}</b>`}</td>
        <td><b>${esc(it.label)}</b>${it.broken?' <span class="pill red">집계 실패</span>':''}${
          it.why?`<div class="sub" style="margin-top:2px">${esc(it.why).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>')}</div>`:''}</td>
        <td class="r" style="width:64px"><span class="hint">열기 ›</span></td>
      </tr>`).join('')}
    </table></div>
  </div>`;
}
VIEWS.today = async () => {
  let d;
  try{ d = await api('GET','/api/ops-today'); }
  catch(e){
    $('#content').innerHTML = `<div class="panel"><div class="empty">
      오늘 할 일을 불러오지 못했습니다 — ${esc(e.message)}</div></div>`;
    return;
  }
  const badge = $('#bdg-today');
  if(badge){ badge.textContent = d.total || ''; badge.style.display = d.total?'':'none'; }
  const comm = d.comm || {items:[]};
  $('#content').innerHTML = `
    <div class="panel" style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">
      <div><div style="font-size:.72rem;color:var(--faint);font-weight:800;letter-spacing:.12em">오늘 반드시</div>
        <div style="font-size:1.7rem;font-weight:800;letter-spacing:-.02em;margin-top:2px;color:${d.total?'var(--red)':'var(--ok)'}">
          ${d.total||0}<small style="font-size:.9rem;color:var(--faint)">건</small></div></div>
      ${/*  ⚠ '오늘 반드시' 와 '봐 두면 좋은 것' 을 한 숫자로 합치지 않는다.
             합치면 600 이 넘고, 그 숫자는 "오늘은 글렀다" 로만 읽힌다. */''}
      <div style="font-size:.78rem;color:var(--sub);line-height:1.7">
        막힌 것 + 상대가 기다리는 것<br>
        <span style="color:var(--faint)">그 밖에 봐 둘 것 ${d.later||0}건 · ${esc((d.as_of||'').slice(0,16))} 기준</span></div>
      <div style="margin-left:auto"><button class="btn g sm" data-act="loadView" data-arg="today">새로고침</button></div>
    </div>
    ${d.clear ? `<div class="panel" style="border:1.5px solid #C4E4CF;background:#F2FAF4">
      <div style="padding:26px 10px;text-align:center">
        <div style="font-size:2.1rem">✓</div>
        <div style="font-weight:800;color:#0E5F2C;margin-top:6px;font-size:1.02rem">지금 손댈 일이 없습니다</div>
        <div class="sub" style="margin-top:6px">막힌 건도, 기다리는 상대도 없습니다.
          새 사건이 들어오면 여기에 뜹니다.</div>
      </div></div>` : (d.groups||[]).map(todayCard).join('')}
    ${(d.prep||[]).length ? `<div class="panel">
      <div class="ph"><span class="pt">준비 과제 <small>매일 하는 일이 아니라 한 번 끝내는 일</small></span></div>
      <div class="tbl-wrap"><table class="tbl">
        ${d.prep.map(p=>`<tr class="rowclick" data-act="loadView" data-arg="${esc((p.go||'#').slice(1))}">
          <td><b>${esc(p.label)}</b><div class="sub" style="margin-top:2px">${esc(p.why)}</div></td>
          <td style="width:210px">
            <div style="display:flex;align-items:center;gap:8px">
              <div style="flex:1;height:8px;border-radius:99px;background:var(--mist);overflow:hidden">
                <div style="height:100%;width:${p.pct}%;background:linear-gradient(90deg,var(--blue),#3E9BDD)"></div></div>
              <span style="font-weight:800;font-size:.74rem;width:44px;text-align:right">${p.pct}%</span></div>
            <div class="sub" style="margin-top:3px">${p.done} / ${p.total}곳 · <b>${p.left}곳 남음</b></div>
          </td>
          <td class="r" style="width:64px"><span class="hint">열기 ›</span></td>
        </tr>`).join('')}
      </table></div>
    </div>` : ''}
    ${comm.items.length ? `<div class="panel" style="border:1.5px solid ${comm.live?'#BFD8EE':'#F5DCB2'}">
      <div class="ph"><span class="pt">알림 전달</span>
        <span class="pill ${comm.live?'blue':'amber'}">${comm.live?'실발송 켜짐':'실발송 꺼짐 — 포털 알림만'}</span></div>
      ${!comm.live?`<div class="notice">문자·알림톡이 나가지 않는 동안에는 <b>포털을 여는 사람만</b> 소식을 압니다.
        급한 건은 아래 숫자를 보고 직접 연락해 주세요.</div>`:''}
      <div class="tbl-wrap"><table class="tbl">
        ${comm.items.map(it=>`<tr class="rowclick" data-act="loadView" data-arg="${esc((it.go||'#').slice(1))}">
          <td style="width:74px" class="r"><b style="font-size:1.1rem">${it.n}</b></td>
          <td><b>${esc(it.label)}</b><div class="sub" style="margin-top:2px">${esc(it.why).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>')}</div></td>
          <td class="r" style="width:64px"><span class="hint">열기 ›</span></td>
        </tr>`).join('')}
      </table></div>
    </div>` : ''}`;
};
VIEWS.dash = async () => {
  const d = await api('GET','/api/dashboard');
  const m = d.money;
  MONEY_META = d.money_drill || {};     // 라벨·설명은 서버(집계 조건과 같은 곳)에서 온다
  const maxPipe = Math.max(...d.pipeline.map(p=>p.count), 1);
  const maxIns = Math.max(...d.by_insurer.map(x=>x.amt), 1);
  const totalActions = Object.values(d.actions).reduce((a,b)=>a+b,0);
  $('#content').innerHTML = `
    <!-- 거래 대금 — 카드를 누르면 **그 금액을 이룬 내역**으로 간다 -->
    <div class="krow k6">
      <div class="kc hero clickable" data-act="drillCases" data-arg="진행중" title="진행 중인 사건 목록 보기">
        <div class="k">진행중 공사금액 (WIP) <span class="kgo">›</span></div>
        <div class="v">${won(m.wip_amount)}<small>원</small></div><div class="d">진행 사건 ${d.cases_active}건</div></div>
      <div class="kc clickable" data-act="drillMoney" data-arg="gmv_total" title="누적 거래액을 이룬 정산 내역 보기">
        <div class="k">누적 거래액 <span class="kgo">›</span></div>
        <div class="v">${won(m.gmv_total)}<small>원</small></div><div class="d">정산 확정 기준</div></div>
      <div class="kc gold clickable" data-act="drillMoney" data-arg="fee_paid" title="수납된 수수료 내역 보기">
        <div class="k">수수료 수익 <span class="kgo">›</span></div>
        <div class="v">${won(m.fee_paid)}<small>원</small></div>
        <div class="d">발생 <a href="#" data-act="drillMoney" data-arg="fee_total" style="color:inherit;text-decoration:underline">${won(m.fee_total)}원</a> 중 수납</div></div>
      <div class="kc clickable" data-act="drillMoney" data-arg="inflow_pending" title="송금 대기 중인 건 보기">
        <div class="k">보험사 송금 대기 <span class="kgo">›</span></div>
        <div class="v">${won(m.inflow_pending)}<small>원</small></div><div class="d">승인 후 시행사 미입금</div></div>
      <div class="kc clickable" data-act="drillMoney" data-arg="payout_pending" title="지급 예정 건 보기">
        <div class="k">업체 지급 예정 <span class="kgo">›</span></div>
        <div class="v">${won(m.payout_pending)}<small>원</small></div><div class="d">지급 검수 후 · 이체 실행 대기</div></div>
      <div class="kc clickable" data-act="drillSaving" title="절감 산출 근거 보기">
        <div class="k">누적 절감액 <span class="kgo">›</span></div>
        <div class="v">${won(m.saved_amount)}<small>원</small></div>
        ${/*  ⚠ 이 값(avg_rate)은 SAVE_BASE_SQL 기반이라 2차 건에서는 **표준단가
             개산 상단**과 비교한 것이다. '가견적 대비' 라고 쓰면 우리 계산값이
             보상담당자가 낸 금액처럼 읽힌다(철칙 2). 리포트·엑셀·명세서와
             같은 이름을 쓴다. */''}
        <div class="d" style="color:var(--green)">비교 기준 대비 −${m.saved_rate}%</div></div>
    </div>

    ${sweepBadge(d.sweep_last_ok)}

    <!-- 오늘의 액션 -->
    <div class="panel">
      <div class="ph"><span class="pt">오늘 처리할 일 <small>클릭하면 그 대기 건만 걸러서 열립니다</small></span>
        <span class="pill ${totalActions>0?'red':'green'}">${totalActions>0?totalActions+'건 대기':'모두 처리됨'}</span></div>
      <div class="krow k5" style="margin:0">
        ${Object.entries(d.actions).map(([k,v])=>{
          //  건수만으로는 오늘 손댈 일인지 알 수 없다 — 가장 오래된 건이 며칠째인지 함께 본다.
          const age = (d.actions_oldest||{})[k];
          const hot = v>0 && age>=7;
          return `
          <div class="kc ${v>0?'act':''}" style="cursor:pointer" data-act="drillAction" data-arg="${k}">
            <div class="k">${esc(k.replace(/_/g,' '))}</div>
            <div class="v" style="${v>0?'color:var(--red)':'color:var(--faint)'}">${v}<small>건</small></div>
            ${v>0 && age!=null ? `<div class="d" style="${hot?'color:var(--red);font-weight:800':''}">
              ${age>=1?`가장 오래된 건 <b>${age}일째</b>${hot?' ⚠':''}`:'오늘 들어옴'}</div>`:''}
          </div>`;}).join('')}
      </div>
    </div>

    <!-- 작업 파이프라인 -->
    <div class="panel">
      <div class="ph"><span class="pt">작업 진행 파이프라인 <small>단계를 클릭하면 해당 건만 사건 목록에서 열립니다</small></span></div>
      <div class="pipe">
        ${d.pipeline.map((p,i)=>`
          <div class="pstep ${i===d.pipeline.length-1?'done':''}" style="cursor:pointer" data-act="drillStage" data-arg="${esc(p.status)}" title="${esc(p.stage)} ${p.count}건 보기">
            <div class="pn">${esc(p.stage)}</div>
            <div class="pv">${p.count}<span>건</span></div>
            <div class="pa">${won(p.amount)}원</div>
            <div class="pbar"><div class="pfill" style="width:${Math.round(p.count/maxPipe*100)}%"></div></div>
          </div>`).join('')}
      </div>
    </div>

    <div class="row2">
      <div class="panel">
        <div class="ph"><span class="pt">정체·경보 <small>오래 멈춘 순 — 며칠째 이 상태인가</small></span><span class="pill red">${d.alerts.length}건</span></div>
        <div class="tbl-wrap"><table class="tbl">
          <tr><th style="width:52px" class="r">경과</th><th>사건</th><th>발주처</th><th>공종</th><th>상태</th><th class="r">액션</th></tr>
          ${d.alerts.length?d.alerts.map(c=>{const dd=c.stale_days||0;
            const hot = dd>=7 ? 'color:var(--red);font-weight:800' : dd>=3 ? 'color:var(--amber-text);font-weight:700' : '';
            return `<tr>
            <td class="r" style="white-space:nowrap;${hot}">${dd}일${dd>=7?' ⚠':''}</td>
            <td class="em" data-act="caseDetail" data-arg="${c.id}" style="cursor:pointer">${esc(c.case_no)}</td>
            <td>${esc(c.insurer)}</td><td>${esc(c.category)}</td>
            <td>${statusPill(c.status)}</td>
            <td class="r"><button class="btn g sm" data-act="caseDetail" data-arg="${c.id}">처리</button></td></tr>`;}).join('')
            :'<tr><td colspan="6" class="empty">정체 건 없음 ✓</td></tr>'}
        </table></div>
        <div class="hint" style="margin-top:6px">3일 이상 같은 상태면 주의, 7일 이상은 경고로 표시합니다.</div>
      </div>
      <div class="panel">
        <div class="ph"><span class="pt">이상 저가 입찰
          <small>${d.low_price_alert_pct
            ? `가견적 대비 ${d.low_price_alert_pct}% 이상 낮은 건 — 산출 근거 확인 필요`
            : '저가 경보가 꺼져 있습니다(설정에서 기준 %를 지정하면 켜집니다)'}</small></span>
          <span class="pill${(d.risky||[]).length?' red':''}">${(d.risky||[]).length}건</span></div>
        <div class="tbl-wrap"><table class="tbl">
          <tr><th>사건</th><th>공종</th><th class="r">가견적</th><th class="r">최저가</th><th class="r">하락률</th></tr>
          ${(d.risky||[]).length ? d.risky.map(x=>`<tr>
            <td class="em">${esc(x.case_no)}</td><td>${esc(x.category)}</td>
            <td class="r">${won(x.est_price)}</td><td class="r">${won(x.low_price)}</td>
            <td class="r" style="color:var(--red);font-weight:800">−${x.drop_pct}%</td></tr>`).join('')
            : '<tr><td colspan="5" class="empty">이상 저가 없음 ✓</td></tr>'}
        </table></div>
      </div>
      <div class="panel">
        <div class="ph"><span class="pt">발주처별 거래액</span></div>
        <div class="prog">
          ${d.by_insurer.map(x=>`<div class="r"><span class="k">${esc(x.insurer||'-')}</span>
            <div class="track"><div class="fill" style="width:${Math.round(x.amt/maxIns*100)}%"></div></div>
            <span class="v" style="width:80px">${won(x.amt)}</span></div>`).join('')||'<div class="empty">데이터 없음</div>'}
        </div>
        <div class="ph" style="margin-top:16px"><span class="pt">진행중 공종별 물량</span></div>
        <div class="tbl-wrap" style="max-height:180px"><table class="tbl">
          <tr><th>공종</th><th class="r">건수</th><th class="r">금액</th></tr>
          ${d.by_major.map(x=>`<tr><td>${esc(x.category)}</td><td class="r">${x.n}건</td><td class="r em">${won(x.amt)}</td></tr>`).join('')||'<tr><td colspan="3" class="empty">진행 물량 없음</td></tr>'}
        </table></div>
      </div>
    </div>

    <div class="panel">
      <div class="ph"><span class="pt">최근 활동</span><span class="pill blue">LIVE</span></div>
      <div class="feed">
        ${d.recent.map(a=>`<div class="fi"><span class="ic">•</span>
          <div><div class="a">${esc(a.action)}${a.detail?' — '+esc(a.detail):''}</div><div class="b">${esc(a.actor)}</div></div>
          <span class="t">${esc((a.created_at||'').slice(5,16))}</span></div>`).join('')||'<div class="empty">활동 없음</div>'}
      </div>
    </div>`;
};

// ── 접속 통계 (대시보드에서 분리) ──
VIEWS.traffic = async () => {
  const t = await api('GET','/api/traffic');
  const maxD = Math.max(...t.days.map(d=>d.n), 1);
  const maxH = Math.max(...t.by_hour.map(h=>h.n), 1);
  const todayTotal = t.by_hour.reduce((a,h)=>a+h.n, 0);
  const peakH = todayTotal ? +(t.by_hour.find(h=>h.n===maxH)||{}).h : null;
  const maxP = Math.max(...t.by_path.map(p=>p.n), 1);
  const roleTotal = t.by_role.reduce((a,r)=>a+r.n,0) || 1;
  const W=720, H=200;
  const pts = t.days.map((d,i)=>{
    const x = t.days.length>1 ? (i/(t.days.length-1))*W : W/2;
    const y = H - (d.n/maxD)*(H-20) - 10;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  $('#content').innerHTML = `
    <div class="krow k4">
      <div class="kc hero"><div class="k">오늘 요청</div><div class="v">${won(t.today)}<small>건</small></div><div class="d">고유 IP ${t.uniq_today}개</div></div>
      <div class="kc"><div class="k">누적 요청</div><div class="v">${won(t.total)}<small>건</small></div><div class="d">접속기록 보관 중</div></div>
      <div class="kc"><div class="k">로그인 성공</div><div class="v">${won(t.logins)}<small>회</small></div><div class="d">누적</div></div>
      <div class="kc gold"><div class="k">이용 주체</div><div class="v">${t.by_role.length}<small>유형</small></div><div class="d">${t.by_role.map(r=>r.role).slice(0,3).join(' · ')}</div></div>
    </div>
    <div class="panel">
      <div class="ph"><span class="pt">일별 접속 추이 <small>최근 ${t.days.length}일</small></span></div>
      ${t.days.length>1?`<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:200px" preserveAspectRatio="none">
        <defs><linearGradient id="gA" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#0064B2" stop-opacity=".25"/><stop offset="1" stop-color="#0064B2" stop-opacity="0"/></linearGradient></defs>
        <g stroke="#EAF1F8" stroke-width="1">${[0.25,0.5,0.75].map(f=>`<line x1="0" y1="${H*f}" x2="${W}" y2="${H*f}"/>`).join('')}</g>
        <polygon points="0,${H} ${pts} ${W},${H}" fill="url(#gA)"/>
        <polyline points="${pts}" fill="none" stroke="#0064B2" stroke-width="2.5"/>
      </svg>
      <div style="display:flex;justify-content:space-between;font-size:.62rem;color:var(--faint);font-weight:700">
        <span>${esc(t.days[0].d)}</span><span>${esc(t.days[t.days.length-1].d)}</span></div>`
      :'<div class="empty">데이터가 쌓이면 추이가 표시됩니다 (현재 '+t.days.length+'일치)</div>'}
    </div>
    <div class="row2">
      <div class="panel">
        <div class="ph"><span class="pt">시간대별 접속 <small>오늘 0~23시</small></span>
          <span class="sub" style="font-size:.72rem">최다 ${maxH.toLocaleString()}건${peakH!==null?` · ${peakH}시`:''}</span></div>
        ${todayTotal ? `
        <div class="hbars">
          ${t.by_hour.map(h=>{
            const cur = h.h === t.now_hour;
            const future = t.now_hour && h.h > t.now_hour;
            return `<div class="hb${cur?' now':''}${future?' fut':''}" title="${h.h}시 · ${h.n}건">
              <div class="hb-track"><div class="hb-fill" style="height:${h.n?Math.max(3, Math.round(h.n/maxH*100)):0}%"></div></div>
              <div class="hb-n">${h.n||''}</div>
              <div class="hb-l">${(+h.h)%3===0?(+h.h):''}</div>
            </div>`;}).join('')}
        </div>
        <div class="hbars-foot">
          <span>0시</span><span>6시</span><span>12시</span><span>18시</span><span>23시</span>
        </div>`
        : '<div class="empty">오늘 접속 기록이 아직 없습니다</div>'}
      </div>
      <div class="panel">
        <div class="ph"><span class="pt">이용 주체별</span></div>
        <div class="prog">
          ${t.by_role.map(r=>`<div class="r"><span class="k">${esc(r.role)}</span>
            <div class="track"><div class="fill ${r.role==='비로그인'?'amber':''}" style="width:${Math.round(r.n/roleTotal*100)}%"></div></div>
            <span class="v">${r.n}</span></div>`).join('')||'<div class="empty">없음</div>'}
        </div>
      </div>
    </div>
    <div class="panel">
      <div class="ph"><span class="pt">많이 호출된 경로 <small>상위 12</small></span></div>
      <div class="prog">
        ${t.by_path.map(p=>`<div class="r"><span class="k" style="width:230px">${esc(p.path)}</span>
          <div class="track"><div class="fill" style="width:${Math.round(p.n/maxP*100)}%"></div></div>
          <span class="v">${p.n}</span></div>`).join('')||'<div class="empty">없음</div>'}
      </div>
      <p style="font-size:.66rem;color:var(--faint);margin-top:10px">※ 접속기록은 개인정보보호법 「개인정보의 안전성 확보조치 기준」에 따라 보관·점검됩니다.</p>
    </div>`;
};

// ── 도입 문의함 ──
let leadFilter = '전체';
VIEWS.leads = async () => {
  const qs = searchQS('leads'); if(leadFilter!=='전체') qs.set('status', leadFilter);
  const data = await api('GET','/api/leads'+(qs.toString()?'?'+qs:''));
  const F = ['전체','신규','검토중','승인','반려'];
  $('#content').innerHTML = `
    <div class="panel">
      <div class="ph"><span class="pt">보험사·공제조합 도입 문의 <small>${data.length}건</small></span><span style="flex:1"></span>${xlsxBtn('leads','도입문의')}
        <div class="filters">${F.map(f=>`<span class="fc ${f===leadFilter?'on':''}" data-act="setLeadFilter" data-arg="${esc(f)}">${f}</span>`).join('')}</div>
      </div>
      ${searchBar('leads',{ph:'기관·담당자·연락처·관심사항'})}
      <div class="tbl-wrap"><table class="tbl">
        <tr><th>#</th><th>기관</th><th>유형</th><th>담당자</th><th>연락처</th><th>관심사항</th><th>상태</th><th>접수일</th><th class="r">액션</th></tr>
        ${data.length?data.map(l=>`<tr data-act="leadDetail" data-arg="${l.id}" style="cursor:pointer">
          <td class="em">${l.id}</td><td class="em">${esc(l.company)}</td><td>${esc(l.org_type)}</td>
          <td>${esc(l.name)} ${l.title?esc(l.title):''}</td><td>${esc(l.phone)}</td><td>${esc(l.interest)}</td>
          <td>${statusPill(l.status)}</td><td>${esc((l.created_at||'').slice(0,10))}</td>
          <td class="r"><button class="btn g sm" data-act="leadDetail" data-arg="${l.id}">상세</button></td></tr>`).join(''):'<tr><td colspan="9" class="empty">문의 없음</td></tr>'}
      </table></div>
    </div>`;
  window._leads = data;
};
function setLeadFilter(f){ leadFilter=f; VIEWS.leads(); }
function leadDetail(id){
  const l = window._leads.find(x=>x.id===id); if(!l)return;
  openModal(`<h3>${esc(l.company)}</h3><div class="msub">도입 문의 #${l.id} · ${esc((l.created_at||'').slice(0,16))}</div>
    <div class="kv"><span class="k">기관 유형</span><span class="v">${esc(l.org_type)}</span></div>
    <div class="kv"><span class="k">담당자</span><span class="v">${esc(l.name)} ${esc(l.title||'')}</span></div>
    <div class="kv"><span class="k">연락처</span><span class="v">${esc(l.phone)}</span></div>
    <div class="kv"><span class="k">이메일</span><span class="v">${esc(l.email||'-')}</span></div>
    <div class="kv"><span class="k">관심사항</span><span class="v">${esc(l.interest)}</span></div>
    <div class="kv"><span class="k">현재 상태</span><span class="v">${statusPill(l.status)}</span></div>
    <div class="field" style="margin-top:14px"><label>문의 내용</label><textarea readonly>${esc(l.message||'')}</textarea></div>
    <div class="field"><label>내부 메모</label><textarea id="lnote">${esc(l.note||'')}</textarea></div>
    <div class="modal-foot">
      <button class="btn a" data-act="leadAct" data-arg="${l.id}" data-arg2="검토중">검토중</button>
      <button class="btn p" data-act="leadAct" data-arg="${l.id}" data-arg2="승인">승인(계약추진)</button>
      <button class="btn g" data-act="leadAct" data-arg="${l.id}" data-arg2="반려">반려</button>
      <span style="flex:1"></span>
      <button class="btn g" data-act="closeModal">닫기</button>
    </div>`);
}
async function leadAct(id, status){
  const note = $('#lnote') ? $('#lnote').value : undefined;
  //  ⚠⚠ [라운드205] 바로 아래 형제(appAct, 130행 뒤)는 이미 89라운드에서
  //    "위임 실행기는 반환값을 기다리지도 catch 하지도 않아 서버 오류가
  //    unhandled rejection 으로 끝난다"는 이유로 try/catch 가 붙었는데,
  //    가장 가까운 이웃인 여기는 빠진 채 남아 있었다.
  try{
    await api('PATCH','/api/leads/'+id, {status, note});
  }catch(e){
    //  ⚠⚠ [라운드501] 형제(defectAct·settleVoid 등, 라운드481·486·500) 참조
    //    — catch도 성공 분기(바로 아래)와 같이 정리한다.
    toast(e.message || '처리하지 못했습니다.'); closeModal(); refreshBadges(); VIEWS.leads(); return;
  }
  closeModal(); toast(`도입 문의 <b>${status}</b> 처리됨`); refreshBadges(); VIEWS.leads();
}

// ── 입점 신청함 ──
let appFilter = '전체';
VIEWS.apps = async () => {
  const qs = searchQS('apps'); if(appFilter!=='전체') qs.set('status', appFilter);
  const data = await api('GET','/api/applications'+(qs.toString()?'?'+qs:''));
  const F = ['전체','신규','서류검토','승인','반려'];
  $('#content').innerHTML = `
    <div class="panel">
      <div class="ph"><span class="pt">시공업체 입점 신청 <small>${data.length}건 · 승인 시 협력업체로 자동 등록</small></span>
        <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
          <div class="filters">${F.map(f=>`<span class="fc ${f===appFilter?'on':''}" data-act="setAppFilter" data-arg="${esc(f)}">${f}</span>`).join('')}</div>
          ${xlsxBtn('applications','입점신청')}
          <button class="btn p sm" data-act="appIntakeForm" title="전화·팩스·영업으로 받은 신청을 대신 접수">+ 직접 접수</button>
        </div>
      </div>
      ${searchBar('apps',{ph:'업체명·대표·사업자번호·지역', categories:ALL_MAJORS})}
      <div class="tbl-wrap"><table class="tbl">
        <tr><th>#</th><th>업체명</th><th>구분</th><th>대표</th><th>공종</th><th>권역</th><th>서류</th><th>상태</th><th>접수일</th><th class="r">액션</th></tr>
        ${data.length?data.map(a=>`<tr data-act="appDetail" data-arg="${a.id}" style="cursor:pointer">
          <td class="em">${a.id}</td><td class="em">${esc(a.company)}${a.source==='직접접수'?' <span class="pill amber" title="담당자가 대신 접수">직접</span>':''}</td>
          <td>${a.partner_type==='시행사'?'<span class="pill blue">시행사</span>':'<span class="pill gray">시공사</span>'}</td>
          <td>${esc(a.ceo||'-')}</td>
          <td>${esc(a.major)}</td><td>${esc(a.region||'-')}</td>
          <td>${a.has_license?'면허✓ ':''}${a.has_insurance?'보험✓':''}${!a.has_license&&!a.has_insurance?'-':''}</td>
          <td>${statusPill(a.status)}</td><td>${esc((a.created_at||'').slice(0,10))}</td>
          <td class="r"><button class="btn g sm" data-act="appDetail" data-arg="${a.id}">심사</button></td></tr>`).join(''):'<tr><td colspan="10" class="empty">신청 없음</td></tr>'}
      </table></div>
    </div>`;
  window._apps = data;
};
function setAppFilter(f){ appFilter=f; VIEWS.apps(); }

// 직접 접수 — 전화·팩스·영업으로 받은 업체를 담당자가 대신 접수한다.
//   바로 업체로 등록하지 않고 공개 폼과 같은 심사 단계(신규→서류검토→승인)를 태운다.
//   면허·보험 확인을 건너뛰지 않기 위해서다.
function appIntakeForm(){
  openModal(`<h3>입점 신청 직접 접수</h3>
    <div class="msub">전화·팩스·영업으로 받은 신청을 대신 등록합니다. 등록 후 일반 신청과 같은 심사 절차를 거칩니다.</div>
    <div class="field"><label>업체 구분 *</label>
      <select id="q_type">
        <option value="시공사">🔧 시공사 — 하도급 풀 (단일 공종 전문)</option>
        <option value="시행사">🏢 시행사 — 통값 입찰 주체 (다공종 관리)</option>
      </select></div>
    <div class="grid2">
      <div class="field"><label>업체명 *</label><input id="q_company" placeholder="예: ○○건설(주)"></div>
      <div class="field"><label>사업자번호</label><input id="q_biz" placeholder="000-00-00000" inputmode="numeric"></div>
    </div>
    <div class="grid2">
      <div class="field"><label>대표자</label><input id="q_ceo"></div>
      <div class="field"><label>연락처</label><input id="q_phone" placeholder="010-0000-0000"></div>
    </div>
    <div class="grid2">
      <div class="field"><label>주력 공종 *</label><select id="q_major">${ALL_MAJORS.map(m=>`<option>${m}</option>`).join('')}</select></div>
      <div class="field"><label>권역</label><input id="q_region" placeholder="예: 서울·경기"></div>
    </div>
    <!--  ⚠ 권역만으로는 좌표를 못 만든다 — 주소가 없으면 이 업체가 승인된 뒤
          거리순 출동 호출에서 계속 뒤로 밀린다(공개 폼·직접 등록은 이미 받는다). -->
    <div class="field"><label>주소</label><input id="q_addr" placeholder="도로명·건물명·지번 (선택이지만 없으면 거리순 배차에서 불리합니다)"></div>
    <div class="grid2">
      <div class="field"><label>세부 취급</label><input id="q_cat" placeholder="예: 가드레일, 방호울타리"></div>
      <div class="field"><label>이메일</label><input id="q_email"></div>
    </div>
    <div class="grid2">
      <div class="field"><label><input type="checkbox" id="q_lic" style="width:auto;margin-right:6px">면허·등록증 보유 확인</label></div>
      <div class="field"><label><input type="checkbox" id="q_ins" style="width:auto;margin-right:6px">보험 가입 확인</label></div>
    </div>
    <div class="field"><label>대표 외 상시 인력 수 <small style="color:var(--red);font-weight:700">(1인 사업자는 입점 불가)</small></label>
      <input id="q_staff" type="number" min="0" placeholder="예: 3 — 대표 제외 상시 인력">
      <div style="font-size:.66rem;color:var(--faint);margin-top:3px">0(대표뿐)이면 접수가 거부됩니다. 미입력 시 심사 때 확인하세요.</div>
    </div>
    <div class="field"><label>접수 메모 <small style="color:var(--faint)">(경위·담당자 등 — 심사에 참고)</small></label><input id="q_msg" placeholder="예: 07/21 김OO 팀장 전화 접수, 명함 수령"></div>
    <div class="modal-foot">
      <button class="btn p" data-act="saveIntake">접수</button>
      <span style="flex:1"></span>
      <button class="btn g" data-act="closeModal">취소</button>
    </div>`);
  //  폼이 그려진 **뒤에** 붙인다(먼저 붙이면 붙일 칸이 아직 없다)
  if(window.AddrPick) AddrPick.attach({input:'#q_addr', region:'#q_region'});
}
async function saveIntake(){
  const body = {
    partner_type:$('#q_type').value, company:$('#q_company').value.trim(),
    biz_no:$('#q_biz').value.trim(), ceo:$('#q_ceo').value.trim(),
    phone:$('#q_phone').value.trim(), major:$('#q_major').value, region:$('#q_region').value.trim(),
    address:$('#q_addr').value.trim(),
    category:$('#q_cat').value.trim(), email:$('#q_email').value.trim(),
    has_license:$('#q_lic').checked, has_insurance:$('#q_ins').checked,
    staff_count:$('#q_staff').value.trim(),
    message:$('#q_msg').value.trim(),
    //  고른 주소의 좌표 — 있으면 승인 뒤 이 업체가 거리순 호출에 제대로 들어간다
    ...(window.AddrPick ? AddrPick.coords('#q_addr') : {})
  };
  if(!body.company){ toast('업체명을 입력해 주세요.'); return; }
  try{
    const r = await api('POST','/api/applications/manual', body);
    toast(`접수했습니다. (#${r.id}) 심사 목록에서 확인하세요.`);
    closeModal(); appFilter='전체'; VIEWS.apps(); refreshBadges();
  }catch(e){ toast(e.message); }
}
function appDetail(id){
  const a = window._apps.find(x=>x.id===id); if(!a)return;
  const approved = a.status==='승인';
  openModal(`<h3>${esc(a.company)}</h3><div class="msub">입점 신청 #${a.id} · ${esc((a.created_at||'').slice(0,16))}</div>
    <div class="kv"><span class="k">업체 구분</span><span class="v">${a.partner_type==='시행사'?'<span class="pill blue">시행사 — 통값 입찰 주체</span>':'<span class="pill gray">시공사 — 하도급 풀</span>'}</span></div>
    <div class="kv"><span class="k">사업자번호</span><span class="v">${esc(a.biz_no||'-')}</span></div>
    <div class="kv"><span class="k">대표자</span><span class="v">${esc(a.ceo||'-')}</span></div>
    <div class="kv"><span class="k">주력 공종</span><span class="v">${esc(a.major)}</span></div>
    <div class="kv"><span class="k">세부 취급</span><span class="v">${esc(a.category||'-')}</span></div>
    <div class="kv"><span class="k">권역</span><span class="v">${esc(a.region||'-')}</span></div>
    <div class="kv"><span class="k">주소</span><span class="v">${esc(a.address||'-')}</span></div>
    <div class="kv"><span class="k">연락처</span><span class="v">${esc(a.phone)} · ${esc(a.email||'')}</span></div>
    <div class="kv"><span class="k">서류</span><span class="v">${a.has_license?'<span class="pill green">면허 보유</span> ':'<span class="pill gray">면허 미제출</span> '}${a.has_insurance?'<span class="pill green">배상책임보험</span>':'<span class="pill gray">보험 미가입</span>'}</span></div>
    <div class="kv"><span class="k">보유 장비</span><span class="v">${esc(a.equipment||'-')}</span></div>
    ${/*  ⚠⚠ [라운드288] 상시 인력 수(staff_count)가 API 응답(SELECT *)에는 이미
           있는데 이 화면 어디에도 안 보였다 — 1인 사업자 제외 정책의 최종
           승인 관문이 이 값을 보고 판정하는데, 정작 판정 버튼을 누르는 사람은
           그 값을 볼 방법이 없었다(직접접수 폼의 "미입력 시 심사 때
           확인하세요" 안내도 확인할 화면이 없어 무의미했다). */''}
    <div class="kv"><span class="k">상시 인력</span><span class="v">${
      a.staff_count==null ? '<span class="pill amber">미확인 — 승인 전 확인 필요</span>'
      : a.staff_count<1 ? `<span class="pill red">${esc(a.staff_count)}명(1인 사업자)</span>`
      : esc(a.staff_count)+'명'}</span></div>
    <div class="kv"><span class="k">현재 상태</span><span class="v">${statusPill(a.status)}${approved?' · 업체 #'+a.partner_id+' 등록됨':''}</span></div>
    <div class="field" style="margin-top:14px"><label>신청 메시지</label><textarea readonly>${esc(a.message||'')}</textarea></div>
    <div class="field"><label>심사 메모</label><textarea id="anote"${myRank()<2?' readonly':''}>${esc(a.note||'')}</textarea></div>
    ${/*  ⚠⚠ [라운드248] PATCH /api/applications/<id> 는 메모만 저장할 때도 포함해
           전부 @require_role("중간관리자") 다(별도의 "메모만 저장" 경로가 없다) —
           그런데 이 세 버튼은 등급 무관하게 항상 그려져, 하위관리자가 메모를 쓰고
           아무 버튼이나 눌러야만 403을 만났다(형제 admins·set·estbands·boq 는
           246·247라운드에 이미 자기차단을 받았다). */''}
    ${(!approved && myRank() < 2) ? `<div class="hint" style="margin-top:10px">
      심사 처리(서류검토·승인·반려)와 메모 저장은 중간관리자 이상만 할 수 있습니다.</div>` : ''}
    <div class="modal-foot">
      ${(approved || myRank() < 2)?'':`<button class="btn a" data-act="appAct" data-arg="${a.id}" data-arg2="서류검토">서류검토</button>
      <button class="btn p" data-act="appAct" data-arg="${a.id}" data-arg2="승인">✓ 승인 → 협력업체 등록</button>
      <button class="btn g" data-act="appAct" data-arg="${a.id}" data-arg2="반려">반려</button>`}
      <span style="flex:1"></span>
      <button class="btn g" data-act="closeModal">닫기</button>
    </div>`);
}
async function appAct(id, status){
  const note = $('#anote') ? $('#anote').value : undefined;
  //  ⚠ **실패를 삼키면 안 된다.** 위임 실행기는 반환값을 기다리지도 catch 하지도
  //    않으므로, 서버가 403/409/500 을 주면 unhandled rejection 으로 끝난다 —
  //    모달은 열린 채, 목록도 그대로라 담당자는 '눌렀는데 반응이 없다'만 본다.
  //    콘솔의 다른 변경 동작은 전부 try/catch + toast 로 감싸져 있다.
  try{
    await api('PATCH','/api/applications/'+id, {status, note});
  }catch(e){
    //  ⚠⚠ [라운드504] 형제(leadAct 등, 라운드481·486·500·501·503) 참조 —
    //    catch도 성공 분기(바로 아래)와 같이 정리한다. 이 함수(appAct)는
    //    실은 그 형제들의 원조다(라운드89가 여기 먼저 try/catch를 붙였고,
    //    라운드205가 leadAct·defectAct·dispatchSweep에 "형제(appAct)처럼"
    //    옮겼다) — 정작 원조 자신은 나중에 이 정리 원칙을 못 물려받았다.
    //    다른 관리자가 먼저 승인해 이미 협력업체가 생성된 신청서를 이
    //    모달이 계속 낡은 상태로 보여주면 반려를 눌러 상태를 뒤집으려 들 수
    //    있다(서버는 이제 이걸 409로 막지만, 화면은 그래도 새로고침해야 한다).
    toast(e.message || '처리하지 못했습니다.'); closeModal(); refreshBadges(); VIEWS.apps(); return;
  }
  closeModal();
  toast(status==='승인'
    ? '입점 <b>승인</b> — 협력업체로 등록되었습니다.<br><small>업체 등록·관리 → 수정에서 <b>포털 계정을 발급</b>해야 업체가 로그인할 수 있습니다.</small>'
    : `입점 신청 <b>${status}</b> 처리됨`);
  refreshBadges(); VIEWS.apps();
}

// ══════════════════════════════════════════════════════════
//   건설업 등록 전수조사 워크벤치
//
//   ⚠ 목적은 '보여 주기' 가 아니라 **398건을 실제로 해치우는 것**이다.
//     한 행을 처리하면 그 행이 사라지고 진행률이 줄어든다 — 줄어드는 게
//     보이지 않으면 사람은 끝까지 못 간다.
//   ⚠ 조회 → 판정이 **한 줄 안에서** 끝난다(모달을 열고 닫지 않는다).
// ══════════════════════════════════════════════════════════

/*  ── 협력사 온보딩 ────────────────────────────────────────────
    활성 399곳인데 포털 계정은 1곳이었다. 공고를 열어도 **누를 사람이 없다.**
    그런데 화면 어디에도 그게 안 보여서, 운영자는 20곳이 대기 중이라 믿고 기다린다.
    이 화면의 목적은 그 거짓 안심을 깨는 것이다.
    ⚠ 업체를 밀거나 추천하는 표시·정렬을 두지 않는다(하도급법 §18의8 3호).
      점수·등수·추천 배지 없음. 정렬은 지역·이름뿐.
    ⚠ 임시 비밀번호는 서버에 저장되지 않는다 — 발급 응답이 유일한 기회다.  */

/*  ── 운영 점검 ────────────────────────────────────────────────
    「오늘 할 일」의 한 항목이 운영에서 조용히 사라져 있었다. 자식 표에 없는
    컬럼으로 걸러 SQL 이 죽었는데 except 가 삼켜서, 0건도 아니고 항목 자체가
    없어졌다. 회귀 31개는 전부 소스 문자열만 봐서 통과했다.
    이 화면은 정의를 **실제로 실행**해 보고, 실패를 숨기지 않는다.  */
VIEWS.selfcheck = async () => {
  let d;
  try{ d = await api('GET','/api/self-check'); }
  catch(e){
    $('#content').innerHTML = `<div class="panel"><div class="empty">
      점검을 불러오지 못했습니다 — ${esc(e.message)}</div></div>`;
    return;
  }
  const badge = $('#bdg-selfcheck');
  if(badge){ badge.textContent = d.n_failed || ''; badge.style.display = d.n_failed?'':'none'; }

  const fail = (d.failed||[]).map(p => `<tr>
      <td><b>${esc(p.label)}</b><div class="sub">${esc(p.group||'')}</div></td>
      <td style="color:var(--red)">${esc(p.why||'')}</td></tr>`).join('');

  const setRows = (d.settings||[]).map(s => `<tr>
      <td style="width:190px"><b>${esc(s.label)}</b></td>
      <td style="width:150px"><span class="pill ${esc(s.tone||'gray')}">${esc(s.value)}</span></td>
      <td class="sub">${esc(s.why||'')}</td></tr>`).join('');

  const play = (d.playbook||[]).map(p => `<tr>
      <td style="width:230px"><b>${esc(p.when)}</b></td>
      <td>${esc(p.do)}</td></tr>`).join('');

  $('#content').innerHTML = `
    <div class="panel">
      <div class="ph"><span class="pt">집계 자기점검
        <small>화면이 쓰는 조회를 그대로 돌려 봅니다 — 실패를 숨기지 않습니다</small></span>
        <button class="btn g sm" data-act="selfRun">다시 점검</button></div>
      ${d.n_failed
        ? `<div style="border:1.5px solid #E9A7A2;background:#FDECEC;color:#B3261E;border-radius:12px;
             padding:12px 14px;margin-bottom:12px;font-size:.85rem;line-height:1.75">
            <b>집계 ${d.n_failed}개가 실패합니다.</b><br>
            이 항목들은 화면에서 0건으로 보이는 것이 아니라 <b>아예 사라집니다</b> —
            없는 일과 못 센 일이 똑같이 보입니다.</div>
           <div class="tbl-wrap"><table class="tbl">
             <thead><tr><th>항목</th><th>원인</th></tr></thead><tbody>${fail}</tbody></table></div>`
        : `<div style="border:1.5px solid #A9D9BC;background:#E7F6EC;color:#137A38;border-radius:12px;
             padding:12px 14px;font-size:.85rem;line-height:1.75">
            <b>조회 ${d.n_probe}개가 모두 정상입니다.</b>
            화면에 뜨는 숫자를 그대로 믿으셔도 됩니다.</div>`}
    </div>

    <div class="panel">
      <div class="ph"><span class="pt">지금 설정 <small>실테스트 전에 확인할 것들</small></span></div>
      <div class="tbl-wrap"><table class="tbl"><tbody>${setRows}</tbody></table></div>
      <div style="margin-top:12px">
        <a class="btn g sm" href="/docs/insurer-api" target="_blank" rel="noopener">발주처 연동 안내서 ↗</a>
        <span class="sub" style="margin-left:8px">발주처 담당자에게 그대로 건네는 문서입니다</span>
      </div>
    </div>

    <div class="panel">
      <div class="ph"><span class="pt">계정 잠금 해제
        <small>비밀번호를 5회 틀리면 10분 잠깁니다 — 실사용자가 급하면 여기서 바로 풉니다</small></span></div>
      ${/*  ⚠⚠ [339라운드] POST /api/login-attempts/unlock 은 require_role(중간관리자,
              app.py:2390) — 등급 무관하게 그려져 있었다. 입력칸의 data-act-enter
              (Enter 로도 같은 핸들러를 부른다, actions.js)까지 함께 가려야 한다 —
              버튼만 숨기면 입력 후 Enter 로 그대로 우회된다. */''}
      <div class="filters">
        ${myRank()>=2
          ? `<input id="unlock_uname" placeholder="아이디" data-act-enter="unlockLogin" style="max-width:220px">
             <button class="btn p sm" data-act="unlockLogin">잠금 해제</button>`
          : '<span class="sub">중간관리자 이상만 사용할 수 있습니다</span>'}
      </div>
    </div>

    <div class="panel">
      <div class="ph"><span class="pt">일이 잘못됐을 때
        <small>되돌릴 수 있습니다 — 어디를 누르는지만 알면 됩니다</small></span></div>
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>이런 일이 생기면</th><th>이렇게 하세요</th></tr></thead>
        <tbody>${play}</tbody></table></div>
    </div>`;
};

let ONB = {stage:'계정 없음', q:'', region:'전체', ptype:'전체'};
let ONB_SIDO = [];   // 서버가 주는 17개 광역 — 화면이 목록을 따로 적지 않는다
let ONB_CREDS = [];
const ONB_TONE = {'계정 없음':'red','안내 전':'amber','안내함 · 미접속':'amber',
                  '접속함 · 미입찰':'blue','입찰 경험 있음':'green'};

function onbRow(p){
  const dt = (s) => s ? esc(String(s).slice(0,10)) : '<span class="sub">—</span>';
  return `<tr id="onb-${p.id}">
    <td style="width:34px"><input type="checkbox" class="onb-ck" value="${p.id}"
        aria-label="${esc(p.name)} 선택"></td>
    <td><b>${esc(p.name)}</b>
      <div class="sub">${esc(p.partner_type||'')}${p.region?' · '+esc(p.region):''}${p.major?' · '+esc(p.major):''}</div>
      ${/*  ⚠ 지역을 못 읽은 값은 **어느 지역 필터에도 안 걸린다.** 조용히 빠지면
             그 업체는 영영 안 불린다 — 그래서 목록에서 눈에 띄게 표시한다. */''}
      ${(p.region_norm && p.region_norm.length) ? '' :
        `<div class="sub" style="color:var(--amber);font-weight:700">지역 확인 필요 — 어느 지역으로도 검색되지 않습니다</div>`}
      ${p.reachable ? `<div class="sub">${esc(p.phone||p.email||'')}</div>`
        : `<div class="sub" style="color:var(--red);font-weight:700">연락처 없음 — 안내할 방법이 없습니다</div>`}</td>
    <td style="width:132px"><span class="pill ${ONB_TONE[p.stage]||'gray'}">${esc(p.stage)}</span></td>
    <td style="width:118px">${p.login_id ? `<code>${esc(p.login_id)}</code>`
                                          : '<span class="sub">—</span>'}</td>
    <td style="width:92px">${dt(p.invited_at)}</td>
    <td style="width:92px">${dt(p.first_login_at)}</td>
    <td style="width:92px">${dt(p.first_bid_at)}</td>
  </tr>`;
}

VIEWS.onboard = async () => {
  const qs = new URLSearchParams();
  if(ONB.stage !== '전체') qs.set('stage', ONB.stage);
  if(ONB.q) qs.set('q', ONB.q);
  if(ONB.region !== '전체') qs.set('region', ONB.region);
  if(ONB.ptype !== '전체') qs.set('ptype', ONB.ptype);
  let d;
  try{ d = await api('GET','/api/partner-onboarding?'+qs.toString()); }
  catch(e){
    $('#content').innerHTML = `<div class="panel"><div class="empty">
      온보딩 현황을 불러오지 못했습니다 — ${esc(e.message)}</div></div>`;
    return;
  }
  ONB_SIDO = d.sido || ONB_SIDO;
  const f = d.funnel || [];
  const ready = (f.find(x=>x.label==='입찰 경험 있음')||{}).n;
  const none  = (f.find(x=>x.label==='계정 없음')||{}).n;
  const badge = $('#bdg-onboard');
  if(badge){ badge.textContent = none || ''; badge.style.display = none?'':'none'; }

  const steps = f.map((s,i) => `
    <div class="pstep ${i===f.length-1?'done':''} ${ONB.stage===s.label?'sel':''}"
         style="cursor:pointer${ONB.stage===s.label?';box-shadow:0 0 0 2px var(--blue) inset':''}"
         data-act="onbStage" data-arg="${esc(s.label)}" title="${esc(s.why)}">
      <div class="pn">${esc(s.label)}</div>
      <div class="pv">${s.error ? '<span style="color:var(--red);font-size:.8rem">집계 실패</span>'
                                : (s.n||0)}<span>곳</span></div>
      <div class="pa">${esc(s.why)}</div>
    </div>`).join('');

  $('#content').innerHTML = `
    <div class="panel">
      <div class="ph"><span class="pt">협력사 온보딩
        <small>계정을 만든 것 · 안내한 것 · 실제로 들어온 것은 전부 다릅니다</small></span></div>
      ${ready===0 ? `<div style="border:1.5px solid #F0C36D;background:#FDF3E2;color:#7A5410;
          border-radius:12px;padding:12px 14px;margin-bottom:13px;font-size:.84rem;line-height:1.7">
        <b>지금 공고를 열면 입찰할 업체가 없습니다.</b><br>
        한 번이라도 입찰해 본 업체가 0곳입니다. 실테스트 전에 계정 발급과 안내가 필요합니다.</div>` : ''}
      <div class="pipe">${steps}</div>
      <div class="filters" style="margin:15px 0">
        <input id="onb_q" placeholder="업체명 · 지역 · 공종" value="${esc(ONB.q)}"
               data-act-enter="onbSearch" style="flex:1;min-width:150px">
        ${/*  ⚠ 자유 입력이 아니라 **고른 값**으로 받는다. 실데이터의 지역 표기가
               149가지라("충남" 14 · "충청남도" 9 · "충남(천안)" 1 …) 손으로 치면
               자기가 친 표기와 같은 것만 걸린다. 서버가 표기를 정규화해 맞춘다. */''}
        <select id="onb_rg" data-act-change="onbSearch" style="width:104px">
          <option${ONB.region==='전체'?' selected':''}>전체</option>
          ${(ONB_SIDO||[]).map(v=>`<option${ONB.region===v?' selected':''}>${esc(v)}</option>`).join('')}
        </select>
        <select id="onb_pt" data-act-change="onbPtype">
          ${['전체','시행사','시공사'].map(v=>`<option${ONB.ptype===v?' selected':''}>${v}</option>`).join('')}
        </select>
        <button class="btn g sm" data-act="onbSearch">찾기</button>
        <span style="flex:1"></span>
        <button class="btn g sm" data-act="onbExport">대상 목록 엑셀</button>
        <button class="btn g sm" data-act="onbAll">보이는 것 모두 선택</button>
        ${/*  ⚠⚠ [라운드250] /api/partners/bulk-credentials 는 require_role(최고관리자)
               인데 이 버튼은 등급 무관하게 그려졌다 — 형제(협력사 상세의 개별
               계정발급, 1457행)는 이미 myRank()<3 이면 안내문으로 바꾼다. 여기는
               한 줄 툴바라 같은 안내문 대신 형제 boq·estbands 버튼(246·247라운드)
               처럼 자격 없으면 조용히 숨긴다. */''}
        ${myRank()>=3?'<button class="btn p sm" data-act="onbIssue">선택 업체 계정 만들기</button>':''}
        <button class="btn a sm" data-act="onbInvite">선택 업체 안내 표시</button>
      </div>
      <div class="sub" style="margin-bottom:10px">${esc(d.notify_why||'')}</div>
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr><th></th><th>업체</th><th>단계</th><th>아이디</th>
          <th>안내</th><th>첫 접속</th><th>첫 입찰</th></tr></thead>
        <tbody>${(d.rows||[]).map(onbRow).join('') ||
          '<tr><td colspan="7" class="empty">조건에 맞는 업체가 없습니다.</td></tr>'}</tbody>
      </table></div>
      <div class="sub" style="margin-top:10px">${d.shown||0} / ${d.total||0}곳 표시${
        (d.total||0) > (d.shown||0) ? ' — 조건을 좁히면 나머지가 보입니다' : ''}</div>
    </div>`;
};

/*  발급 결과 — 임시 비밀번호는 서버에 저장되지 않는다. 이 화면이 유일한 기회다.
    ⚠ 콘솔에 찍지 않는다. 파일은 사용자가 명시적으로 누를 때만 만든다.  */
function onbShowCreds(d){
  const iss = d.issued || [], sk = d.skipped || [];
  ONB_CREDS = iss;
  const rows = iss.map(r => `<tr>
      <td>${esc(r.name)}</td><td><code>${esc(r.login_id)}</code></td>
      <td><code>${esc(r.temp_password)}</code></td></tr>`).join('');
  openModal(`<h3>계정 ${iss.length}곳 발급됨</h3>
    <div style="border:1.5px solid #F0C36D;background:#FDF3E2;color:#7A5410;border-radius:12px;
                padding:12px 14px;font-size:.83rem;line-height:1.7;margin-bottom:12px">
      <b>임시 비밀번호는 지금 한 번만 표시됩니다.</b><br>
      서버에 저장되지 않으므로 창을 닫으면 다시 볼 수 없고, 재발급만 가능합니다.
      각 업체는 첫 로그인에서 비밀번호를 반드시 바꾸게 되어 있습니다.</div>
    ${iss.length ? `<div class="tbl-wrap"><table class="tbl">
      <thead><tr><th>업체</th><th>아이디</th><th>임시 비밀번호</th></tr></thead>
      <tbody>${rows}</tbody></table></div>` :
      '<div class="empty">새로 만든 계정이 없습니다.</div>'}
    ${sk.length ? `<div class="sub" style="margin-top:12px"><b>건너뛴 ${sk.length}곳</b><br>${
      sk.map(s=>`${esc(s.name)} — ${esc(s.why)}`).join('<br>')}</div>` : ''}
    <div class="modal-foot">
      ${iss.length ? '<button class="btn p" data-act="onbCredCsv">전달용 파일 내려받기</button>' : ''}
      <span style="flex:1"></span>
      <button class="btn g" data-act="closeModal">닫기</button></div>`);
}

let LIC = {status:'미확인', q:'', ptype:'전체'};
let LIC_LOOKUP = 'https://www.kiscon.net/gongsi';
function licRow(p){
  const st = p.license_status || '미확인';
  const pill = st==='등록확인' ? 'green' : st==='무등록' ? 'red' : 'gray';
  return `<tr id="lic-${p.id}">
    <td><b>${esc(p.name)}</b>
      <div class="sub">${esc(p.partner_type||'')}${p.has_login?' · <span style="color:var(--blue)">계정 있음</span>':''}
        ${p.major?' · '+esc(p.major):''}${p.region?' · '+esc(p.region):''}</div>
      ${p.phone?`<div class="sub">${esc(p.phone)}</div>`:''}</td>
    <td style="width:150px">
      ${/*  ⚠ 사업자번호가 있어야 조회가 된다 — 지금 399곳 중 1곳뿐이다.
             조사하며 알게 된 값을 **그 자리에서** 남기게 한다. */''}
      <input id="lb-${p.id}" value="${esc(p.biz_no||'')}" placeholder="사업자번호"
             style="width:100%;font-size:.74rem" title="조회에 필요합니다"></td>
    <td style="width:126px">
      ${/*  조회처는 서버가 준다(코드가 이미 정해 둔 무인증 조회처) */''}
      <a class="btn g sm" href="${esc(LIC_LOOKUP)}" target="_blank" rel="noopener">KISCON 조회 ↗</a>
      <button class="btn g sm" data-act="licCopy" data-arg="${p.id}" title="업체명을 복사해 조회창에 붙여넣기">이름 복사</button></td>
    <td style="width:150px">
      <input id="ln-${p.id}" value="${esc(p.license_no||'')}" placeholder="등록번호"
             style="width:100%;font-size:.74rem" title="'등록확인' 이면 반드시 필요합니다"></td>
    <td style="width:212px" class="r">
      <span class="pill ${pill}" style="margin-right:6px">${esc(st)}</span>
      <button class="btn p sm" data-act="licSet" data-arg="${p.id}" data-arg2="등록확인">등록</button>
      <button class="btn a sm" data-act="licSet" data-arg="${p.id}" data-arg2="무등록">무등록</button></td>
  </tr>`;
}
VIEWS.license = async () => {
  const qs = new URLSearchParams();
  qs.set('status', LIC.status);
  if(LIC.q) qs.set('q', LIC.q);
  if(LIC.ptype !== '전체') qs.set('partner_type', LIC.ptype);
  let d;
  try{ d = await api('GET','/api/license-survey?'+qs.toString()); }
  catch(e){
    $('#content').innerHTML = `<div class="panel"><div class="empty">
      조사 목록을 불러오지 못했습니다 — ${esc(e.message)}</div></div>`;
    return;
  }
  LIC_LOOKUP = d.lookup || LIC_LOOKUP;
  const g = d.progress || {};
  const badge = $('#bdg-license');
  if(badge){ badge.textContent = g.todo || ''; badge.style.display = g.todo?'':'none'; }
  const F = ['미확인','등록확인','무등록','전체'];
  $('#content').innerHTML = `
    <div class="panel">
      <div class="ph"><span class="pt">건설업 등록 조사 <small>하도급 상대는 등록 건설사업자여야 합니다 (건산법 §25②)</small></span></div>
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
        <div style="flex:1;height:12px;border-radius:99px;background:var(--mist);overflow:hidden">
          <div style="height:100%;width:${g.pct||0}%;background:linear-gradient(90deg,var(--blue),#3E9BDD);transition:width .3s"></div></div>
        <div style="font-weight:800;font-size:.9rem;white-space:nowrap">${g.pct||0}%</div>
      </div>
      <div class="sub" style="margin-bottom:12px">확인 <b>${g.done||0}</b> / ${g.total||0}곳 ·
        <b style="color:var(--amber-text)">${g.todo||0}곳 남음</b>
        ${(g.agg||{})['무등록']?` · 무등록 ${g.agg['무등록']}곳`:''}</div>
      <div class="notice">이 값은 <b>도급 적법성 관문</b>이 배정 때 근거로 쓰는 데이터입니다.
        미확인이 많으면 관문이 제 역할을 못 합니다.
        <b>투찰 자격이 있는 곳(시행사·계정 보유)</b>을 앞에 두었습니다 — 그쪽부터 끝내면
        전부 끝나기 전에도 효과가 납니다.</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:10px 0;padding:10px;background:var(--mist);border-radius:10px">
        <div class="filters">${F.map(f=>`<span class="fc ${LIC.status===f?'on':''}" data-act="licFilter" data-arg="${esc(f)}">${f}</span>`).join('')}</div>
        <select id="lic_pt" style="width:auto" data-act-change="licPtype">
          ${['전체','시행사','시공사'].map(t=>`<option ${LIC.ptype===t?'selected':''}>${t}</option>`).join('')}</select>
        <input id="lic_q" value="${esc(LIC.q)}" placeholder="🔍 업체명·사업자번호·지역·대표"
               style="${SEARCH_W}" data-act-enter="licSearch">
        <button class="btn p sm" data-act="licSearch">검색</button>
      </div>
      <div class="tbl-wrap"><table class="tbl">
        <tr><th>업체</th><th>사업자번호</th><th>조회</th><th>등록번호</th><th class="r">판정</th></tr>
        ${(d.items||[]).length ? d.items.map(licRow).join('')
          : `<tr><td colspan="5" class="empty">${LIC.status==='미확인'
              ? '미확인이 남지 않았습니다 — 전수조사가 끝났습니다.'
              : '조건에 맞는 업체가 없습니다.'}</td></tr>`}
      </table></div>
      ${d.total > (d.items||[]).length ? `<div class="hint" style="margin-top:10px">
        조건에 맞는 ${d.total}곳 중 ${d.items.length}곳 표시 — 처리하면 다음 것이 올라옵니다.</div>` : ''}
    </div>`;
};

// ── 업체 등록·관리 (시행사 / 시공사 분리) ──
let partnerFilter = {major:'전체', q:'', ptype:'시행사'};
function partnerQS(){
  const qs = new URLSearchParams();
  if(partnerFilter.major!=='전체') qs.set('major', partnerFilter.major);
  if(partnerFilter.q) qs.set('q', partnerFilter.q);
  if(partnerFilter.ptype!=='전체') qs.set('partner_type', partnerFilter.ptype);
  return qs;
}
VIEWS.partners = async () => {
  const qs = partnerQS();
  //  ⚠ 등록 전수조사 진행률은 서버가 이미 세고 있었는데 부르는 화면이 없었다.
  //    실패해도 목록은 떠야 한다 — 진행률이 없을 뿐이다.
  const [data, s, la] = await Promise.all([
    api('GET','/api/partners?'+qs.toString()), api('GET','/api/stats'),
    api('GET','/api/license-audit').catch(()=>null)]);
  const isPrime = partnerFilter.ptype==='시행사';
  const majors = isPrime
    ? ['전체','종합시행(종합건설)','종합 원상복구']
    : ['전체','가드레일·방호울타리','교통안전시설','방음벽·휀스·펜스','유리·샷시·자동문','셔터·차단기·게이트','누수·배관·설비','지붕·판넬·캐노피','외벽·석재·담장·조적','도장·방수·미장','간판·전기·가로등','조경·수목','종합 원상복구'];
  $('#content').innerHTML = `
    <div class="krow k4">
      <div class="kc hero"><div class="k">시행사 (통값 입찰 참여)</div><div class="v">${s.prime_count||0}<small>개사</small></div><div class="d">경매에 직접 입찰하는 원수급 주체</div></div>
      <div class="kc"><div class="k">시공사 (시행사 하도급 풀)</div><div class="v">${s.sub_count||0}<small>개사</small></div><div class="d">공종별 전문 — 향후 협업 분리발주 대비</div></div>
      <div class="kc gold"><div class="k">전체 등록</div><div class="v">${s.total_partners}<small>개사</small></div><div class="d">활성 기준</div></div>
      ${/* 건설업 등록 조사 — **몇 곳이 남았는지**가 이 숫자의 존재 이유다.
           업체별 상태를 고치는 화면은 있었는데 진행률을 보는 곳이 없어,
           전수조사가 어디까지 갔는지 아무도 몰랐다. */''}
      ${la ? `<div class="kc"><div class="k">건설업 등록 조사</div>
        <div class="v" style="${la.todo>0?'color:var(--amber-text)':''}">${la.todo}<small>곳 남음</small></div>
        <div class="d">확인 ${la.done} / ${la.total}곳 · 무등록 ${(la.agg||{})['무등록']||0}곳</div></div>`
      : `<div class="kc"><div class="k">건설업 등록 조사</div>
        <div class="v" style="font-size:1.1rem;color:var(--faint)">불러오지 못함</div>
        <div class="d">진행률만 못 봅니다 — 목록은 정상입니다</div></div>`}
    </div>
    <div class="panel">
      <div style="background:var(--blue-bg);border-radius:12px;padding:12px 15px;font-size:.76rem;color:var(--blue);font-weight:600;margin-bottom:14px">
        🏗️ <b>시행사</b>는 한 현장을 통째로 받아 자기가 시공사를 골라 <b>통값(lump-sum)</b>으로 우리 경매에 입찰합니다.
        <b>시공사</b>는 시행사가 쓰는 공종별 전문 풀이며, 향후 협업(공종 분리발주) 모델 전환 시 직접 입찰 주체가 됩니다.
      </div>
      <div class="ph">
        <div class="filters">
          ${['시행사','시공사','전체'].map(t=>`<span class="fc ${t===partnerFilter.ptype?'on':''}" data-act="setPtype" data-arg="${esc(t)}">${t==='시행사'?'🏢 시행사':t==='시공사'?'🔧 시공사':'전체'}</span>`).join('')}
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
          <input id="pq" placeholder="🔍 업체명·지역·공종·사업자번호·대표·연락처" value="${esc(partnerFilter.q)}" style="border:1px solid var(--line);border-radius:9px;padding:7px 12px;font-size:.78rem;flex:1 1 220px;min-width:150px" data-act-enter="doPartnerSearch">
          <button class="btn g sm" data-act="doPartnerSearch">검색</button>
          ${xlsxBtn('partners','협력업체')}
          <button class="btn p sm" data-act="partnerForm">+ 업체 등록</button>
        </div>
      </div>
      <div class="filters" style="margin-bottom:12px">${majors.map(m=>`<span class="fc ${m===partnerFilter.major?'on':''}" data-act="setPartnerMajor" data-arg="${esc(m)}">${m}</span>`).join('')}</div>
      <div style="font-weight:800;font-size:.85rem;margin-bottom:8px">${isPrime?'🏢 시행사':partnerFilter.ptype==='시공사'?'🔧 시공사':'전체'} <span style="color:var(--faint);font-weight:600">${data.length}개사</span></div>
      <div class="tbl-wrap"><table class="tbl tbl-partners">
        <tr><th>#</th><th>업체명</th><th>구분</th><th>대공종</th><th>권역</th><th>연락처</th>${isPrime?'<th>면허</th>':'<th>평점</th>'}<th class="r">이행</th><th>상태</th><th class="r">액션</th></tr>
        ${data.length?data.map(p=>`<tr data-act="partnerForm" data-arg="${p.id}" style="cursor:pointer">
          <td>${p.id}</td><td class="em">${esc(p.name)}</td>
          <td>${p.partner_type==='시행사'?'<span class="pill blue">시행사</span>':'<span class="pill gray">시공사</span>'}</td>
          <td class="cat">${esc(p.major)}</td><td>${esc(p.region)}</td>
          <td class="tel">${esc(p.phone||'-')}</td>
          ${isPrime?`<td>${p.license_status==='등록확인'?'<span class="pill green">등록확인</span>':p.license_status==='무등록'?'<span class="pill red">무등록</span>':'<span class="pill gray">미확인</span>'}</td>`:`<td>${p.rating?p.rating+' ★':'-'}</td>`}
          <td class="r">${p.jobs_done}건</td>
          <td>${statusPill(p.status)}</td>
          <td class="r"><button class="btn g sm" data-act="partnerForm" data-arg="${p.id}">수정</button></td></tr>`).join(''):'<tr><td colspan="10" class="empty">업체 없음</td></tr>'}
      </table></div>
    </div>`;
  window._partners = data;
};
function setPartnerMajor(m){ partnerFilter.major=m; VIEWS.partners(); }
function setPtype(t){ partnerFilter.ptype=t; partnerFilter.major='전체'; VIEWS.partners(); }
function doPartnerSearch(){ partnerFilter.q = $('#pq').value.trim(); VIEWS.partners(); }
const ALL_MAJORS = ['종합시행(종합건설)','종합 원상복구','가드레일·방호울타리','교통안전시설','방음벽·휀스·펜스','유리·샷시·자동문','셔터·차단기·게이트','누수·배관·설비','지붕·판넬·캐노피','외벽·석재·담장·조적','도장·방수·미장','간판·전기·가로등','조경·수목'];
function partnerForm(id){
  const p = id ? (window._partners||[]).find(x=>x.id===id) : {partner_type:partnerFilter.ptype==='시공사'?'시공사':'시행사'};
  openModal(`<h3>${id?'업체 정보 수정':'업체 등록'}</h3><div class="msub">${id?'업체 #'+id:'시행사 또는 시공사를 직접 등록합니다'}</div>
    <div class="field"><label>업체 구분 *</label>
      <select id="p_type">
        <option value="시행사" ${p.partner_type==='시행사'?'selected':''}>🏢 시행사 — 통값으로 경매에 직접 입찰 (다공종 관리)</option>
        <option value="시공사" ${p.partner_type==='시공사'?'selected':''}>🔧 시공사 — 시행사 하도급 풀 (단일 공종 전문)</option>
      </select></div>
    <div class="grid2">
      <div class="field"><label>업체명 *</label><input id="p_name" value="${esc(p.name||'')}"></div>
      <div class="field"><label>사업자번호</label><input id="p_biz" value="${esc(p.biz_no||'')}"></div>
    </div>
    <div class="grid2">
      <div class="field"><label>대표자</label><input id="p_ceo" value="${esc(p.ceo||'')}"></div>
      <div class="field"><label>연락처</label><input id="p_phone" value="${esc(p.phone||'')}"></div>
    </div>
    <div class="grid2">
      <div class="field"><label>대공종</label><select id="p_major">${ALL_MAJORS.map(m=>`<option ${p.major===m?'selected':''}>${m}</option>`).join('')}</select></div>
      <div class="field"><label>권역</label><input id="p_region" value="${esc(p.region||'')}"></div>
    </div>
    <div class="field"><label>세부 취급</label><input id="p_cat" value="${esc(p.category||'')}"></div>
    <div class="field"><label>보유 면허·등록업종 <span style="color:var(--faint);font-weight:600">(자기신고 — 참고용, 아래 조사 결과가 정본)</span></label><input id="p_lic" value="${esc(p.license||'')}" placeholder="예: 건축공사업, 실내건축공사업, 시설물유지관리"></div>
    ${id?`<div style="margin-top:10px;padding:12px 14px;border:1px solid ${p.license_status==='등록확인'?'#C4E4CF':p.license_status==='무등록'?'#F1C9C1':'var(--line)'};border-radius:10px;background:${p.license_status==='등록확인'?'#F2FAF4':p.license_status==='무등록'?'#FDF4F2':'var(--mist)'}">
      <div style="font-weight:800;font-size:.8rem;margin-bottom:6px">🏛️ 건설업 등록 조사 <span class="pill ${p.license_status==='등록확인'?'green':p.license_status==='무등록'?'red':'gray'}">${esc(p.license_status||'미확인')}</span></div>
      <div class="msub" style="margin-bottom:8px">KISCON(www.kiscon.net/gongsi)에서 무인증 조회 후 기록하세요.
        하도급 상대는 <b>등록 건설사업자</b>여야 합니다(건설산업기본법 제25조②) — 무등록 업체는 도급 건 배정에서 제외됩니다.</div>
      <div class="grid2">
        <div class="field"><label>조사 결과</label>
          <select id="lc_status">${['미확인','등록확인','무등록'].map(s=>`<option ${(p.license_status||'미확인')===s?'selected':''}>${s}</option>`).join('')}</select></div>
        <div class="field"><label>등록번호 <small style="color:var(--faint)">(등록확인 시 필수)</small></label>
          <input id="lc_no" value="${esc(p.license_no||'')}" placeholder="예: 대전중구 22-나-05"></div>
      </div>
      <div class="field"><label>보유 업종(KISCON 표기)</label>
        <input id="lc_trades" value="${esc(p.license_trades||'')}" placeholder="예: 금속·창호·지붕·건축물조립공사업"></div>
      <button class="btn g sm" data-act="licenseSave" data-arg="${id}">조사 결과 저장</button>
      ${p.license_checked_at?`<span class="hint" style="margin-left:8px">최근 조사 ${esc((p.license_checked_at||'').slice(0,16))} · ${esc(p.license_checked_by||'')}</span>`:''}
      <div id="subcheckbox" class="msub" style="margin-top:8px">하도급 적격 확인 중…</div>
    </div>`:''}
    <div class="field"><label>주소</label><input id="p_addr" value="${esc(p.address||'')}"></div>
    <div class="grid2">
      <div class="field"><label>이메일</label><input id="p_email" value="${esc(p.email||'')}"></div>
      <div class="field"><label>상태</label><select id="p_status">${['활성','심사중','경고','퇴출'].map(s=>`<option ${(p.status||'심사중')===s?'selected':''}>${s}</option>`).join('')}</select></div>
    </div>
    ${id?`<div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--line)">
      <div style="font-weight:700;margin-bottom:4px">협력사 포털 계정</div>
      <div class="msub" style="margin-bottom:8px">포털에는 회원가입이 없습니다. 입점 승인 후 <b>여기서 계정을 발급해야</b> 업체가 로그인해 입찰할 수 있습니다.</div>
      <div id="credbox">${myRank() < 3
        ? (p.login_id
            ? `<div class="kv"><span class="k">아이디</span><span class="v em">${esc(p.login_id)}</span></div>
               <span style="font-size:.72rem;color:var(--faint)">비밀번호 재발급은 최고관리자만 할 수 있습니다.</span>`
            : `<span style="font-size:.72rem;color:var(--faint)">계정 발급은 최고관리자만 할 수 있습니다.</span>`)
        : (p.login_id
            ? `<div class="kv"><span class="k">아이디</span><span class="v em">${esc(p.login_id)}</span></div>
               <button class="btn g sm" data-act="issueCred" data-arg="${id}">비밀번호 재발급</button>
               <span style="font-size:.66rem;color:var(--faint);margin-left:8px">분실 시에만 — 기존 비밀번호가 즉시 무효화됩니다</span>`
            : `<div class="grid2"><div class="field"><label>포털 아이디 <small style="color:var(--faint)">(영문 소문자·숫자 4~20자)</small></label>
                 <input id="cred_id" placeholder="예: mucheon2026" autocomplete="off"></div>
               <div class="field" style="display:flex;align-items:flex-end">
                 <button class="btn a sm" data-act="issueCred" data-arg="${id}">계정 발급</button></div></div>`)}</div>
      <div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--line)">
      <div style="font-weight:700;margin-bottom:4px">정산 지급 계좌</div>
      <div class="msub" style="margin-bottom:8px">이체 완료 처리에 필요합니다. 최고관리자만 조회·변경할 수 있고, 변경 사실은 감사로그에 남습니다.</div>
      <div id="acctbox" class="msub">불러오는 중…</div>
    </div></div>`:''}
    <div class="modal-foot">
      <button class="btn p" data-act="savePartner" data-arg="${id||0}">${id?'저장':'등록'}</button>
      ${/*  ⚠⚠ [339라운드] DELETE /api/partners/<id>(퇴출) 는 require_role(중간관리자,
              app.py:8023, 되돌리기 어려운 조치라는 8022행 주석과 같은 선) — 등급
              무관하게 그려져 있었다. askStatusReason() 프롬프트를 다 채운 뒤에야
              403 을 만나는 시간낭비형 결함(등록/저장은 등급무관이 맞아 그대로 둠). */''}
      ${id && myRank()>=2?`<button class="btn danger" data-act="deletePartner" data-arg="${id}">퇴출</button>`:''}
      <span style="flex:1"></span>
      <button class="btn g" data-act="closeModal">취소</button>
    </div>`);
  if(id){ loadAccount(id); loadSubcontractCheck(id); }
}

// 건설업 등록 조사 결과 저장 — KISCON 조회값을 기록한다(하도급 자격의 근거)
async function licenseSave(id){
  const body = {
    license_status: $('#lc_status').value,
    license_no: $('#lc_no').value.trim(),
    license_trades: $('#lc_trades').value.trim()};
  try{
    await api('POST',`/api/partners/${id}/license`, body);
    toast('조사 결과를 저장했습니다.'); closeModal(); VIEWS.partners();
  }catch(e){
    //  ⚠⚠ [라운드476] '무등록'으로 기록하는데 이 업체가 진행 중 사건을 안고
    //    있으면 서버가 먼저 되묻는다 — demoteConfirm()(퇴출 등 status 전용,
    //    "포털에서 완료 보고를 할 수 없어 멈춘다"는 고정 문구가 license_
    //    status 에는 사실과 다르다: 로그인·완료보고는 안 막힌다)을 재사용하지
    //    않고, 서버가 이미 정확하게 써 준 error 문구를 그대로 보여준다.
    if(e && e.data && e.data.code === 'PARTNER_HAS_WORK' && confirm(e.data.error)){
      try{
        await api('POST',`/api/partners/${id}/license`, {...body, confirm_license:true});
        toast('조사 결과를 저장했습니다.'); closeModal(); VIEWS.partners();
      }catch(e2){ toast(e2.message); }
      return;
    }
    toast(e.message);
  }
}

// 정산 계좌 — 등록 화면이 아예 없어서 첫 지급 때 계좌가 시스템 밖(전화·메신저)으로 돌던 문제를 막는다.
async function loadAccount(id){
  const box = $('#acctbox'); if(!box) return;
  try{
    const a = await api('GET', `/api/partners/${id}/account`);
    box.innerHTML = `<div class="grid2">
        <div class="field"><label>은행</label><input id="b_bank" value="${esc(a.bank_name||'')}" placeholder="예: 국민은행"></div>
        <div class="field"><label>예금주</label><input id="b_holder" value="${esc(a.bank_holder||'')}"></div>
      </div>
      <div class="field"><label>계좌번호</label>
        <input id="b_acct" value="${esc(a.bank_account||'')}" placeholder="숫자만 8~20자리" inputmode="numeric"></div>
      ${a.bank_account ? `<label style="display:flex;align-items:center;gap:6px;font-size:.72rem;color:var(--red);margin:2px 0 8px">
        <input type="checkbox" id="b_clear" data-act-change="acctClearToggle" style="width:auto">
        계좌번호를 삭제합니다(복구 불가) — 은행·예금주만 바꾸려면 체크하지 마세요</label>` : ''}
      <button class="btn p sm" data-act="saveAccount" data-arg="${id}">계좌 저장</button>`;
  }catch(e){
    // 최고관리자가 아니면 403 — 권한 없음을 그대로 알려준다(빈 화면으로 두지 않는다)
    box.textContent = e.message || '계좌 정보를 불러오지 못했습니다.';
  }
}
// 하도급 적격 판정(건산법 §25②) — compliance.check_subcontractor() 를 그대로 보여준다.
// 위 조사 결과 select 는 license_status 값 자체(무엇을 조사했는지)이고, 이 줄은
// "그 값으로 지금 하도급을 줘도 되는가"에 대한 법적 판정+근거문(별개 정보)이다.
async function loadSubcontractCheck(id){
  const box = $('#subcheckbox'); if(!box) return;
  try{
    const r = await api('GET', `/api/partners/${id}/subcontract-check`);
    const c = r.check;
    box.innerHTML = `<b>하도급 적격</b> <span class="pill ${c.ok?'green':'red'}">${c.ok?'가능':'불가'}</span> — ${esc(c.reason)}`;
  }catch(e){
    box.textContent = e.message || '하도급 적격 확인을 불러오지 못했습니다.';
  }
}
let CRED_TEXT = '';
async function issueCred(id){
  const box = $('#credbox'); if(!box) return;
  const idInput = $('#cred_id');
  const payload = idInput ? {login_id: idInput.value.trim()} : {};
  if(idInput && !payload.login_id){ toast('포털 아이디를 정해 주세요.'); return; }
  if(!idInput && !confirm('비밀번호를 재발급하시겠습니까?' + String.fromCharCode(10) + '기존 비밀번호는 즉시 사용할 수 없게 됩니다.')) return;
  try{
    const r = await api('POST', `/api/partners/${id}/credentials`, payload);
    // 임시 비밀번호는 이 응답에 한 번만 온다 — 닫기 전까지 화면에 남겨 옮겨 적게 한다
    box.innerHTML = `<div style="background:var(--mist);border:1px solid var(--line);border-radius:8px;padding:10px 12px">
      <div style="font-weight:700;margin-bottom:4px">${r.reissued?'비밀번호 재발급 완료':'계정 발급 완료'}</div>
      <div class="kv"><span class="k">아이디</span><span class="v em">${esc(r.login_id)}</span></div>
      <div class="kv"><span class="k">임시 비밀번호</span><span class="v em" style="font-family:monospace;font-size:.9rem;user-select:all">${esc(r.temp_password)}</span></div>
      <div style="font-size:.66rem;color:var(--red);margin-top:6px">⚠ 지금 한 번만 표시됩니다. 업체에 안전한 경로로 전달하세요. 최초 로그인 시 변경이 강제됩니다.</div>
      <button class="btn sm" style="margin-top:8px" data-act="credCopy">안내문 복사</button>
    </div>`;
    //  운영자가 매번 손으로 옮겨 적다 보면 주소를 빼먹거나 아이디를 잘못 적는다.
    //  전달할 문장을 통째로 만들어 둔다(전송은 운영자가 고른 경로로 한다 — 여기서 보내지 않는다).
    //  ⚠ 여기 적힌 것이 **첫 주에 전화가 가장 많이 오는 지점**이다.
    //    미리 알려 두면 그 전화가 안 온다 — 특히 ①현장 떠나기 전 사진 ②계좌
    //    ③건설업 등록증. 셋 다 나중에 알면 되돌릴 수 없거나 일이 멈춘다.
    CRED_TEXT = [
      '[복구온] 협력사 포털 계정 안내',
      '',
      '접속 주소: ' + location.origin + '/partner/login',
      '아이디: ' + r.login_id,
      '임시 비밀번호: ' + r.temp_password,
      '',
      '[처음 하실 일]',
      '· 최초 로그인 시 비밀번호를 반드시 변경하셔야 합니다.',
      '· 휴대폰으로 접속해 [홈 화면에 추가]를 누르시면 앱처럼 쓰실 수 있습니다.',
      '  (현장에서 사진을 올리려면 휴대폰 접속이 편합니다)',
      '· 사업자등록증 사본·통장 사본·건설업 등록증을 운영팀에 보내 주세요.',
      '  - 계좌가 없으면 공사를 마쳐도 이체가 나가지 않습니다.',
      '  - 건설업 등록이 확인되지 않으면 도급 건 입찰·출동 배정에서 제외됩니다.',
      '',
      '[꼭 알아 두실 것]',
      '· 완료 보고는 시공 사진을 올린 뒤에만 됩니다. 현장을 떠나면 다시 찍을 수',
      '  없고, 완료 보고 시각이 하자보증 기산점이 됩니다. 떠나기 전에 찍어 주세요.',
      '· 통신이 안 되는 곳에서 찍은 사진은 휴대폰에 저장돼 있다가 신호가 돌아오면',
      '  자동으로 올라갑니다. 앱을 지우지만 마세요.',
      '· 입찰가는 내릴 수만 있습니다(1차). 2차 공고는 반대로 최소 금액 아래로',
      '  내려갈 수 없습니다 — 화면에 그 금액이 표시됩니다.',
      '· 다른 업체의 견적·낙찰가는 보이지 않습니다. 사진과 금액 규칙만 보고',
      '  정하시면 됩니다.',
      '',
      '[담당자 계정을 더 만드실 때]',
      '· 포털 안에서 직접 만드실 수 있고, 등급이 둘입니다.',
      '  - 중간관리자: 조회 + 입찰 제출까지',
      '  - 조회·접수: 보기만. 입찰 제출은 서버가 막습니다.',
      '· 회사 명의로 금액을 내는 일이므로, 권한이 있는 분에게만 중간관리자를 주세요.'
    ].join(String.fromCharCode(10));
    toast(r.message || '발급했습니다.');
  }catch(e){ toast(e.message); }
}

async function saveAccount(id){
  const clearBox = $('#b_clear');
  const clearing = !!(clearBox && clearBox.checked);
  const acct = $('#b_acct').value.trim();
  const body = { bank_name:$('#b_bank').value.trim(), bank_holder:$('#b_holder').value.trim() };
  //  ⚠⚠ [라운드241] 서버(api_partner_account_set)는 clear_account:true 를
  //    받으면 실제로 지울 수 있는데(이미 완성돼 있었다), 그걸 보내는 화면
  //    쪽 통로가 아예 없었다 — "정말 지우려면 '계좌 삭제'를 사용하세요"라는
  //    안내가 가리키는 기능 자체가 존재하지 않았다(240라운드 admin.js 협력사
  //    관리 감사에서 발견). 삭제 체크박스가 있을 때만 이 통로를 연다.
  if(clearing){
    if(!confirm('계좌번호를 삭제하시겠습니까?' + String.fromCharCode(10)
                + '되돌릴 수 없고, 정산 이체가 새 계좌를 등록할 때까지 멈춥니다.')) return;
    body.bank_account = ''; body.clear_account = true;
  }else if(acct){
    // ⚠ 계좌칸이 비어 있으면(삭제 의사가 아닌 한) **아예 보내지 않는다.**
    //   예전에는 항상 보내서, 예금주만 고치려다 저장 한 번에 암호문이 지워졌다
    //   (복구 불가 → 그 업체 정산이 지급 관문에서 영영 막힌다).
    //   서버에도 같은 가드가 있지만, 화면에서 아예 만들지 않는 편이 안전하다.
    body.bank_account = acct;
  }
  try{
    const r = await api('PATCH', `/api/partners/${id}/account`, body);
    toast(clearing ? '계좌번호를 삭제했습니다.'
          : acct ? `계좌를 저장했습니다. ${r.masked||''}`
                 : '은행·예금주를 저장했습니다 (계좌번호는 그대로 유지)');
    loadAccount(id);   // 방금 바뀐 상태(특히 삭제)를 화면에 다시 반영한다
  }catch(e){ toast(e.message); }
}
async function savePartner(id){
  const body = {
    name:$('#p_name').value.trim(), partner_type:$('#p_type').value,
    biz_no:$('#p_biz').value.trim(), ceo:$('#p_ceo').value.trim(),
    phone:$('#p_phone').value.trim(), major:$('#p_major').value, region:$('#p_region').value.trim(),
    category:$('#p_cat').value.trim(), license:$('#p_lic').value.trim(),
    address:$('#p_addr').value.trim(), email:$('#p_email').value.trim(),
    status:$('#p_status').value
  };
  if(!body.name){ toast('업체명은 필수입니다.'); return; }
  try{
    if(id) await api('PATCH','/api/partners/'+id, body);
    else await api('POST','/api/partners', body);
    closeModal(); toast(id?'업체 정보가 저장되었습니다':'협력업체가 <b>등록</b>되었습니다'); VIEWS.partners();
  }catch(e){
    // 진행 중 사건·미지급 정산이 걸려 있으면 서버가 막는다 → 무엇이 걸리는지 보여주고 재확인
    if(e && e.data && e.data.code === 'NEED_REASON'){
      const reason = askStatusReason(body.status);
      if(reason === null) return;
      try{
        await api('PATCH','/api/partners/'+id, {...body, status_reason:reason});
        closeModal(); toast('업체 상태를 변경하고 <b>업체에 통지</b>했습니다'); VIEWS.partners();
      }catch(e2){
        if(await demoteConfirm(e2, body.status)){
          try{
            await api('PATCH','/api/partners/'+id,
                      {...body, status_reason:reason, confirm_demote:true});
            closeModal(); toast('업체 상태를 변경했습니다 — 진행 건은 운영팀이 이어받아야 합니다');
            VIEWS.partners();
          }catch(e3){ toast(e3.message); }
          return;
        }
        toast(e2.message);
      }
      return;
    }
    if(await demoteConfirm(e, body.status)){
      const reason = askStatusReason(body.status);
      if(reason === null) return;
      try{
        await api('PATCH','/api/partners/'+id,
                  {...body, status_reason:reason, confirm_demote:true});
        closeModal(); toast('업체 상태를 변경했습니다 — 진행 건은 운영팀이 이어받아야 합니다'); VIEWS.partners();
      }catch(e2){ toast(e2.message); }
      return;
    }
    toast(e.message);
  }
}
// 상태 변경 사유를 받는다. 사유는 감사로그에 남고 **업체에게도 그대로 통지**되므로
// 내부 은어 대신 당사자가 읽을 문장으로 적게 안내한다.
function askStatusReason(status){
  const r = prompt(
    `'${status||'퇴출'}'(으)로 변경하는 사유를 적어 주세요 (5자 이상).
`
    + `이 사유는 해당 업체에게 그대로 통지됩니다.`, '');
  if(r === null) return null;                 // 취소
  if(r.trim().length < 5){ toast('사유를 5자 이상 적어 주세요.'); return null; }
  return r.trim();
}
// 강등을 막은 이유를 보여주고 그래도 진행할지 묻는다. 진행 의사면 true.
async function demoteConfirm(err, status){
  const info = err && err.data;
  if(!info || info.code !== 'PARTNER_HAS_WORK') return false;
  const list = (info.active_cases||[]).slice(0,6)
    .map(c=>`· ${c.case_no} (${c.status})`).join('\n');
  //  ⚠ 하자는 사건 status 를 안 건드려 active_cases 에 안 잡힌다 — 따로 보여준다.
  const dlist = (info.open_defects||[]).slice(0,6)
    .map(d=>`· ${d.case_no} (${d.status})`).join('\n');
  return confirm(
    `이 업체는 아직 일이 걸려 있습니다.\n\n`
    + `진행 중 사건: ${info.active_count}건\n`
    + (info.unpaid_count?`미지급 정산: ${info.unpaid_count}건 ${(info.unpaid_amount||0).toLocaleString('ko-KR')}원\n`:'')
    + (info.open_defect_count?`열린 하자: ${info.open_defect_count}건 — 담당을 바꿀 방법이 없어 내리면 고칠 사람이 없어집니다\n`:'')
    + (list?`\n${list}\n`:'')
    + (dlist?`\n${dlist}\n`:'')
    + `\n'${status||'퇴출'}'으로 내리면 그 업체는 포털에서 완료 보고를 할 수 없어\n`
    + `해당 사건이 멈춥니다. 그래도 진행하시겠습니까?`);
}
async function deletePartner(id){
  const reason = askStatusReason('퇴출');
  if(reason === null) return;
  const q = '?reason=' + encodeURIComponent(reason);
  try{
    await api('DELETE','/api/partners/'+id+q);
    closeModal(); toast('업체를 퇴출 처리하고 <b>업체에 통지</b>했습니다'); VIEWS.partners();
  }catch(e){
    if(await demoteConfirm(e, '퇴출')){
      try{
        await api('DELETE','/api/partners/'+id+q+'&confirm=1');
        closeModal(); toast('업체를 퇴출 처리했습니다 — 진행 건은 운영팀이 이어받아야 합니다'); VIEWS.partners();
      }catch(e2){ toast(e2.message); }
      return;
    }
    toast(e.message);
  }
}

// ── 공고·사건 등록 ──
VIEWS.newcase = async () => {
  const majors = ['가드레일·방호울타리','교통안전시설','방음벽·휀스·펜스','유리·샷시·자동문','셔터·차단기·게이트','누수·배관·설비','지붕·판넬·캐노피','외벽·석재·담장·조적','도장·방수·미장','간판·전기·가로등','조경·수목','종합 원상복구'];
  const insurers = await api('GET','/api/insurers');   // 실제 등록 보험사 (id 기반)
  //  ★ **개산 근거가 없는 공종을 미리 안다.** 종전에는 2차 공고를 여는 순간
  //    NO_FLOOR 로 막혔는데, 그때는 가견적 수정이 '입찰중' 전용이라 이미 잠겨
  //    손쓸 수 없었다. 등록 화면에서 미리 말해 그 자리에서 적게 한다.
  //    못 받아 와도 등록은 막지 않는다(경고가 없을 뿐이다).
  let COV = {};
  try { COV = (await api('GET','/api/work-coverage')).coverage || {}; } catch(e) {}
  const auto = '26-' + String(Math.floor(70000+Math.random()*9999));
  $('#content').innerHTML = `
    <div class="panel" style="max-width:760px">
      <div class="ph"><span class="pt">공고·사건 등록 <small>등록 시 매칭 업체에 자동 공고 발송</small></span></div>
      ${!insurers.length ? `<div style="background:#FDF1F1;border:1px solid #E9BCBE;border-radius:11px;
            padding:12px 15px;font-size:.8rem;color:#8C2A30;line-height:1.6;margin-bottom:12px">
          <b>발주처가 아직 한 곳도 없습니다.</b> 사건은 발주처에 소속되므로 먼저 등록해야 합니다.<br>
          ${/*  ⚠ 종전 문구는 「사건 등록 시점의 요율」이었는데 **코드에 그런 규칙이 없다.**
                요율이 얼어붙는 시점은 정산 행이 만들어지는 **검수 승인** 이고, cases 에는
                요율 컬럼조차 없다. 화면이 반대로 말하면 운영자가 요율을 언제 바꿔도
                안전하다고 믿는다. */''}
          요율(수수료)도 발주처마다 계약값으로 정해집니다. 요율은 <b>정산이 만들어지는 시점(지급 검수 승인)</b>의
          값으로 확정되며, 그 전에 요율을 바꾸면 <b>진행 중인 사건에도 적용됩니다</b>.
          <button class="btn p sm" data-act="loadView" data-arg="insurers" style="margin-top:8px">발주처 등록하러 가기 →</button>
        </div>` : ''}
      <div class="grid2">
        <div class="field"><label>접수번호 *</label><input id="c_no" value="${auto}"></div>
        <div class="field"><label>발주처(보험사) *</label><select id="c_ins">${insurers.length?insurers.map(i=>`<option value="${i.id}">${esc(i.name)}${i.is_demo?' [데모]':''}${(i.fee_rate_bp!==null&&i.fee_rate_bp!==undefined&&i.fee_rate_bp!==1000)?` (수수료 ${bpPct(i.fee_rate_bp)}%)`:''}</option>`).join(''):'<option value="">— 발주처를 먼저 등록하세요 —</option>'}</select></div>
      </div>
      <div class="grid2">
        ${/*  ⚠ 근거 없는 공종에 표를 달아 **고르기 전에** 보이게 한다.
               (금액을 만들어 주는 게 아니다 — 근거 유무만 말한다) */''}
        <div class="field"><label>공종(대공종) *</label>
          ${/*  ⚠⚠ **value 를 반드시 명시한다.** value 없는 <option> 은 표시 텍스트가
                 곧 값이다 — 경고 문구를 붙이는 순간 서버로 가는 공종명이
                 "조경·수목  ⚠ 개산 근거 없음" 이 되어 판정표·단가·통계가 전부 어긋난다. */''}
          <select id="c_cat" data-act-change="catCoverage">${majors.map(m=>`<option value="${esc(m)}"${COV[m] && COV[m].need_est ? ' data-needest="1"' : ''}>${m}${COV[m] && COV[m].need_est ? '  ⚠ 개산 근거 없음' : ''}</option>`).join('')}</select>
          <div id="cov_warn" style="display:none;margin-top:6px;background:#FFF7E6;border:1px solid #F0D18C;
               border-radius:9px;padding:9px 11px;font-size:.75rem;color:#8A5A00;line-height:1.55"></div></div>
        <div class="field"><label>가견적 <small style="color:var(--faint)">(원) · 1차 입찰 상한</small><br><small style="font-weight:400;color:var(--faint)">사진 없이 접수해 현장 확인이 먼저 필요한 건은, 이 금액이 2차 공고에서 <b>최소 금액(하한)</b>이 됩니다</small></label><input id="c_est" type="text" inputmode="numeric" placeholder="예: 3,600,000" data-act-input="moneyInput" style="text-align:right"><div class="money-ko" style="font-size:.7rem;color:var(--amber-text);font-weight:700;margin-top:3px;text-align:right"></div></div>
      </div>
      <div class="grid2">
        <div class="field"><label>지역 <small style="color:var(--faint)">(주소를 고르면 자동으로 채워집니다)</small></label><input id="c_region" placeholder="예: 인천 남동"></div>
        <div class="field"><label>현장 주소</label><input id="c_addr" placeholder="도로명·건물명·지번으로 검색 (예: 올림픽로 300)" autocomplete="off">
          <input id="c_addr_detail" placeholder="상세주소 — 동·호수·현장 표식 (선택)" autocomplete="off" style="margin-top:6px"></div>
      </div>
      <div class="grid2">
        <div class="field"><label>피해자 성함 <small style="color:var(--faint)">(선택)</small></label><input id="c_vname" placeholder="예: 홍길동" autocomplete="off"></div>
        <div class="field"><label>피해자 연락처 <small style="color:var(--faint)">(선택 · 진행 안내 문자에 씁니다)</small></label><input id="c_vphone" placeholder="010-0000-0000" inputmode="tel" autocomplete="off"></div>
      </div>
      <div class="field"><label>옵션</label>
        <div style="display:flex;gap:18px">
          <label class="check" style="font-size:.82rem"><input type="checkbox" id="c_urgent"> 긴급 (2시간 내 출동)</label>
          <label class="check" style="font-size:.82rem"><input type="checkbox" id="c_comp"> 복합 현장 (다공종 협업)</label>
        </div>
      </div>
      <div class="field">
        <label>피해 사진 <small style="color:var(--faint);font-weight:400">— 선택. 전화·팩스로 받은 사진이 있으면 붙여 주세요</small></label>
        <input type="file" id="c_photos" accept="image/*" multiple>
        <div class="hint" style="margin-top:5px">
          사진을 붙이면 <b>바로 입찰 공고</b>가 열리고 AI 파손 분석이 함께 돌아갑니다.<br>
          없으면 종전대로 <b>인근 업체 출동</b>으로 현장 사진을 먼저 확보합니다.
        </div>
      </div>
      <div class="modal-foot"><button class="btn p" data-act="createCase">공고 등록 · 입찰 오픈</button></div>
    </div>`;
  //  폼이 그려진 **뒤에** 붙인다(먼저 붙이면 붙일 칸이 아직 없다)
  if(window.AddrPick) AddrPick.attach({input:'#c_addr', region:'#c_region', detail:'#c_addr_detail'});
};
async function createCase(){
  const sel = $('#c_ins');
  const body = {
    case_no:$('#c_no').value.trim(), insurer_id:sel.value,
    insurer:sel.options[sel.selectedIndex]?.textContent||'', category:$('#c_cat').value,
    est_price:moneyVal('#c_est'), region:$('#c_region').value.trim(),
    //  상세주소(동·호수)는 검색 결과에 없다 — 고른 주소 뒤에 붙여 한 줄로 저장한다
    address:[$('#c_addr').value.trim(), ($('#c_addr_detail')||{value:''}).value.trim()]
              .filter(Boolean).join(' '),
    urgent:$('#c_urgent').checked, is_composite:$('#c_comp').checked,
    //  ★ **사진이 없으면 '출동 수배' 로 접수한다.**
    //    바로 위 안내문은 "사진을 붙이면 입찰 공고, 없으면 인근 업체 출동" 이라고
    //    말하는데, 종전에는 이 키를 아예 안 보내서 서버가 항상 '입찰중' 으로 열었다
    //    (app.py 는 no_photo 를 읽을 준비가 돼 있었다 — 보내는 쪽만 없었다).
    //    사진 없이 입찰중으로 열리면 협력사는 볼 것이 없는 공고를 받고,
    //    출동 수배는 '접수' 상태에서만 열려 되돌릴 수도 없었다.
    //    (#c_photos 는 바로 아래 1267행이 실제 업로드에 쓰는 그 입력이다)
    no_photo: !(($('#c_photos') || {}).files || []).length,
    victim_name:($('#c_vname')||{value:''}).value.trim(),
    victim_phone:($('#c_vphone')||{value:''}).value.trim(),
    //  고른 주소의 좌표 — 있으면 지도가 '동네'가 아니라 '현장'을 가리킨다
    ...(window.AddrPick ? AddrPick.coords('#c_addr') : {})
  };
  if(!body.case_no){ toast('접수번호는 필수입니다.'); return; }
  //  ★ 근거 없는 공종 + 사진 없음 + 가견적 없음 = **2차 공고가 확실히 막히는 조합**.
  //    등록을 막지는 않는다(운영자가 알고 넣을 수도 있다) — 대신 한 번 확인받는다.
  {
    const _sel = document.getElementById('c_cat');
    const _need = _sel?.options[_sel.selectedIndex]?.dataset?.needest === '1';
    if(_need && body.no_photo && !body.est_price){
      if(!confirm(`'${body.category}' 는 표준단가 개산 근거가 없고, 사진도 가견적도 없습니다.\n` +
                  `이대로 두면 2차 공고를 열 때 하한을 만들 수 없어 막힙니다.\n\n` +
                  `그래도 등록할까요? (가견적을 지금 적는 편이 안전합니다)`)) return;
    }
  }
  if(!body.insurer_id){
    //  ⚠ 목록이 비어 있는데 "선택해 주세요"라고만 하면 운영자는 여기서 멈춘다.
    //    첫날(발주처 0곳)에 실제로 막혔던 지점이다 — 무엇을 해야 하는지 말해 준다.
    const sel = document.getElementById('c_ins');
    const empty = !sel || ![...sel.options].some(o => o.value);
    toast(empty ? '등록된 발주처가 없습니다. [거래처·심사 → 발주처]에서 먼저 등록해 주세요.'
                : '발주 보험사를 선택해 주세요.');
    if(empty) loadView('insurers');
    return;
  }
  try{
    const r = await api('POST','/api/cases', body);
    //  ⚠ 사진 없이 접수하면 경매를 열지 않고 '접수' 로 앉는다. 그런데도 무조건
    //    "입찰 공고가 발송되었습니다" 를 띄워, 나가지도 않은 공고를 나갔다고 말했다.
    toast(r.no_photo
      ? `접수 완료 — 사진이 없어 <b>입찰 공고는 열지 않았습니다</b>. [현장 출동 수배]에서 사진을 먼저 확보하세요`
      : `공고 등록 완료 — 매칭 업체 <b>${r.matched}곳</b>에 입찰 공고가 발송되었습니다`);
    // 피해 사진은 선택이다 — 있으면 붙이고, 실패해도 사건 등록은 이미 끝났다.
    const fin = $('#c_photos');
    if(fin && fin.files && fin.files.length && r.id){
      const fd = new FormData();
      for(const f of fin.files) fd.append('photos', f);
      toast(`피해 사진 ${fin.files.length}장 올리는 중…`);
      //  ⚠ [라운드77] 이 구간이 도는 동안은 세션만료로 인한 강제이동을 미룬다
      //    (위 api() 주석 참조) — 반드시 아래 try/catch 를 다 벗어난 뒤 끈다.
      UP_BUSY = true;
      try{
        const pr = await fetch(`/api/cases/${r.id}/photos/damage`, {
          method:'POST', headers:{'X-CSRF-Token':CSRF}, credentials:'same-origin', body:fd});
        const pd = await pr.json().catch(()=>({}));
        if(pd.ok){
          //  서버가 실제로 저장한 장수를 알린다 — 보낸 장수로 말하면 거절분이 숨는다.
          //  붙인 수와 다르면 **왜 다른지**(중복·오류)를 같이 말한다. 안 그러면
          //  "2장 넣었는데 1장이라고 뜬다"에서 운영자가 멈춘다.
          const why = [];
          if(pd.duplicates) why.push(`같은 사진 ${pd.duplicates}장 제외`);
          if(pd.errors && pd.errors.length) why.push(esc(String(pd.errors[0]).slice(0,40)));
          const head = `사진 <b>${pd.count}/${fin.files.length}장</b> 등록`
                     + (why.length ? ` (${why.join(' · ')})` : '');
          toast(pd.ai_report ? `${head}<br><b>AI 분석:</b> ${esc(pd.ai_report)}` : head);
        }else{
          toast(`사건은 등록됐지만 사진은 올라가지 않았습니다 — ${esc(pd.error||'다시 시도해 주세요')}`);
        }
      }catch(e){
        toast('사건은 등록됐지만 사진 전송에 실패했습니다. 사건 상세에서 다시 붙일 수 있습니다.');
      } finally {
        UP_BUSY = false;
      }
    }
    loadView('cases');
  }catch(e){ toast(e.message); }
}

// ── 사건·입찰 관제 ──
let caseFilter = '전체';
let caseSearch = {q:'', from:'', to:'', category:''};
let caseSort = 'recent';
function sortCasesList(list){
  const s=caseSort;
  return list.slice().sort((a,b)=>{
    //  ⚠ 표에 그리는 금액은 `award_amount||low_price` 인데 정렬은 low_price 만
    //    봤다. 경매 없이 확정되는 1차합의 건은 입찰이 없어 low_price 가 비어 있어,
    //    확정 금액이 가장 큰 건이 '높은순' 맨 아래로 밀렸다 — 보이는 열과 순서가
    //    어긋나면 정렬을 믿을 수 없다. **화면과 같은 값으로 정렬한다.**
    const _amt = (x) => (x.award_amount || x.low_price || 0);
    if(s==='award')  return _amt(b) - _amt(a);
    if(s==='award_asc') return _amt(a) - _amt(b);
    if(s==='saving') return (b.saving||0)-(a.saving||0);
    if(s==='est')    return (b.est_price||0)-(a.est_price||0);
    if(s==='stale')  return (b.stale_days||0)-(a.stale_days||0);   // 오래 멈춘 순
    return (b.id||0)-(a.id||0);
  });
}
// 며칠째 이 상태인가 — 3일 이상 주의, 7일 이상 경고
function staleCell(c){
  const d = c.stale_days||0;
  if(c.status==='완료') return `<span class="hint">-</span>`;
  const st = d>=7 ? 'color:var(--red);font-weight:800' : d>=3 ? 'color:var(--amber-text);font-weight:700' : 'color:var(--faint)';
  return `<span style="white-space:nowrap;${st}">${d}일${d>=7?' ⚠':''}</span>`;
}
//  화면이 지금 보고 있는 조건 — 목록과 엑셀이 **같은 것**을 쓴다.
//  ⚠ 예전에는 엑셀 버튼이 조건을 하나도 안 실어서, 화면에 12건이 떠 있는데
//    파일에는 사건 전부(데모 포함)가 담겼다. 받은 사람은 그 차이를 모른다.
function caseQS(){
  const qs = new URLSearchParams();
  if(caseFilter!=='전체') qs.set('status', caseFilter);
  if(caseSearch.q) qs.set('q', caseSearch.q);
  if(caseSearch.from) qs.set('from', caseSearch.from);
  if(caseSearch.to) qs.set('to', caseSearch.to);
  if(caseSearch.category) qs.set('category', caseSearch.category);
  return qs;
}
VIEWS.cases = async () => {
  const qs = caseQS();
  const data = await api('GET','/api/cases'+(qs.toString()?('?'+qs.toString()):''));
  //  유찰·취소도 골라볼 수 있어야 한다 — 필터에 없으면 '전체'에서 눈으로 찾아야 한다
  const F = ['전체','입찰중','승인대기','시공중','검수대기','정산진행','완료','유찰','취소'];
  const shown = sortCasesList(data);
  $('#content').innerHTML = `
    <div class="panel">
      <div class="ph"><span class="pt">사건 검색 <small>${data.length}건${(caseSearch.q||caseSearch.from||caseSearch.to||caseSearch.category)?' · 검색결과':''}</small></span>
        ${/* 파이프라인에서 넘어오면 filter 가 '검수대기,완료보고지연' 처럼 묶여 올 수 있다 */''}
        <div class="filters">${F.map(f=>`<span class="fc ${String(caseFilter).split(',')[0]===f?'on':''}" data-act="setCaseFilter" data-arg="${esc(f)}">${f}</span>`).join('')}
          ${xlsxBtn('cases','사건')}
          <button class="btn p sm" data-act="loadView" data-arg="newcase">+ 공고 등록</button></div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:2px 0 10px;padding:10px;background:var(--mist);border-radius:10px">
        <input id="cs_q" value="${esc(caseSearch.q)}" placeholder="🔍 접수번호·발주처·공종·지역·주소·업체" style="${SEARCH_W}" data-act-enter="doCaseSearch">
        <select id="cs_cat" style="width:auto" title="공종으로 모아 보기">
          <option value="">공종 전체</option>
          ${ALL_MAJORS.map(c=>`<option ${caseSearch.category===c?'selected':''}>${esc(c)}</option>`).join('')}
        </select>
        <label style="font-size:.7rem;color:var(--faint)">등록일</label>
        <input id="cs_from" type="date" value="${esc(caseSearch.from)}" style="width:auto">
        <span style="color:var(--faint)">~</span>
        <input id="cs_to" type="date" value="${esc(caseSearch.to)}" style="width:auto">
        <button class="btn p sm" data-act="doCaseSearch">검색</button>
        ${(caseSearch.q||caseSearch.from||caseSearch.to||caseSearch.category)?'<button class="btn g sm" data-act="clearCaseSearch">초기화</button>':''}
        <label style="font-size:.7rem;color:var(--faint);margin-left:auto">정렬</label>
        <select id="cs_sort" data-act-change="setCaseSort" style="width:auto">
          <option value="recent" ${caseSort==='recent'?'selected':''}>최신순</option>
          <option value="award" ${caseSort==='award'?'selected':''}>낙찰가 높은순</option>
          <option value="award_asc" ${caseSort==='award_asc'?'selected':''}>낙찰가 낮은순</option>
          <option value="saving" ${caseSort==='saving'?'selected':''}>절감률 높은순</option>
          <option value="est" ${caseSort==='est'?'selected':''}>가견적 높은순</option>
          <option value="stale" ${caseSort==='stale'?'selected':''}>정체 오래된순</option>
        </select>
      </div>
      <p style="font-size:.66rem;color:var(--faint);margin:-4px 0 8px">행을 클릭하면 상세 보기·수정이 열립니다. <b>경과</b>는 지금 상태로 바뀐 뒤 지난 일수입니다.</p>
      <div class="tbl-wrap"><table class="tbl">
        <tr><th>접수번호</th><th>발주처</th><th>공종</th><th>지역</th><th>상태</th><th style="width:52px" class="r">경과</th><th class="r">가견적</th><th class="r">최저/낙찰</th><th class="r">절감률</th><th>담당</th></tr>
        ${shown.length?shown.map(c=>`<tr data-act="caseDetail" data-arg="${c.id}" style="cursor:pointer">
          <td class="em">${esc(c.case_no)}${c.is_composite?' <span class="pill amber">복합</span>':''}${c.urgent?' <span class="pill red">긴급</span>':''}${c.intake_type==='사진없음'?` <span class="pill ${c.dispatch_status==='사진확보'?'blue':c.dispatch_status==='수배실패'?'red':'gray'}" title="간접 출동콜 — ${esc(c.dispatch_status||'수배 대기')}">📷무 ${esc(c.dispatch_status||'수배대기')}</span>`:''}${c.award_route==='1차합의'?' <span class="pill green" title="경매 없이 발주처 승인으로 확정">승인</span>':c.award_route==='미수선'?' <span class="pill gray">미수선</span>':''}</td>
          <td>${esc(c.insurer)}</td><td>${esc(c.category)}</td><td>${esc(c.region)}</td>
          <td>${statusPill(c.status)}</td><td class="r">${staleCell(c)}</td>
          <td class="r">${won(c.est_price)}</td><td class="r">${won(c.award_amount||c.low_price)}</td>
          ${/*  ⚠ [라운드78] c.saving(app.py api_cases)은 확정가가 비교기준을 넘으면
               **음수**가 된다(1차합의 등 초과 낙찰). 그런데 이 셀은 `>0`만 보고
               나머지는 전부 데이터없음과 똑같은 '-'로 찍었다 — 같은 사건을 보는
               insurer_portal.html(621행)은 부호대로 초록/빨강+−/+ 로 정확히
               보여주는데, 관리자 목록만 초과 낙찰을 안 보이게 감췄다(절감률
               높은순 정렬은 부호값을 그대로 써서 이 건들을 맨 아래로 내리는데,
               화면엔 빈칸과 구분이 안 된다). 형제와 같은 방식으로 맞춘다. */''}
          <td class="r" style="color:${(c.saving||0)>=0?'var(--green)':'var(--red)'};font-weight:800">${c.saving?((c.saving>0?'−':'+')+Math.abs(c.saving)+'%'):'-'}</td><td>${esc(c.manager)}</td></tr>`).join(''):'<tr><td colspan="10" class="empty">해당 사건 없음</td></tr>'}
      </table></div>
    </div>`;
};
function setCaseFilter(f){ caseFilter=f; VIEWS.cases(); }
function setCaseSort(v){ caseSort = v || 'recent'; VIEWS.cases(); }
function doCaseSearch(){
  caseSearch = {q:($('#cs_q').value||'').trim(), from:$('#cs_from').value||'',
                to:$('#cs_to').value||'', category:(($('#cs_cat')||{}).value||'')};
  VIEWS.cases();
}
function clearCaseSearch(){ caseSearch={q:'',from:'',to:'',category:''}; VIEWS.cases(); }
// 대시보드 파이프라인/현황 클릭 → 사건 목록을 그 상태로 필터해 연다
function drillStage(status){ caseSearch={q:'',from:'',to:'',category:''}; caseFilter=status||'전체'; loadView('cases'); }

// ── 대시보드 금액 → 그 금액을 이룬 내역 ──────────────────────────
//  숫자만 뜨고 "어느 건들인지" 갈 길이 없었다. 운영자는 정산 목록을 눈으로 훑으며
//  머릿속으로 더해 보는 수밖에 없었고, 그래서 아무도 대조하지 않았다.
let MONEY_META = {};       // 서버가 준 라벨·설명·합산열 (대시보드 응답에서 채운다)
let settleMoney = '';      // 지금 걸린 금액 필터 키
function drillMoney(key){
  if(!key) return;
  settleMoney = key;
  //  다른 검색 조건이 남아 있으면 합계가 카드 숫자와 안 맞는다 — 비우고 연다.
  Object.assign(searchState('settle'), {q:'', from:'', to:'', category:''});
  loadView('settle');
}
function clearMoneyDrill(){ settleMoney=''; VIEWS.settle(); }
//  진행중 공사금액은 정산이 아니라 **사건** 이다 — 사건 목록의 미완료로 보낸다.
function drillCases(){ caseSearch={q:'',from:'',to:'',category:''}; caseFilter='진행중'; loadView('cases'); }
//  절감액은 운영 KPI 의 절감 코어로 계산된다 — 같은 코어를 쓰는 화면으로 보낸다.
function drillSaving(){ loadView('opskpi'); }

// 사건 상세 보기 — 입찰·사진·정산·하자를 한 화면에. 수정 가능한 필드는 인라인 폼.
async function caseDetail(id){
  let d;
  try{ d = await api('GET','/api/cases/'+id+'/detail'); }catch(e){ toast(e.message); return; }
  const c = d.case, ph = d.photos||{}, st = d.settlement;
  //  ⚠ **'접수' 도 고칠 수 있다.** 잠그는 이유는 진행 중 경매의 규칙을 바꾸면
  //    응찰 업체의 유·불리가 갈리기 때문인데, '접수' 는 공고가 열리지도 않아
  //    열린 경매도 입찰도 없다. 종전에는 이 상태까지 잠겨서, 2차 공고가
  //    NO_FLOOR 로 막혔을 때 오류가 시키는 "사건 상세에서 가견적을 입력" 이
  //    화면에서부터 불가능했다(서버도 409 로 거부했다 — 완전한 순환).
  const editable = (c.status==='입찰중' || c.status==='접수');
  openModal(`<h3>${esc(c.case_no)} <span style="font-weight:400;font-size:.8rem;color:var(--faint)">${esc(c.category)}</span></h3>
    <div class="msub">${esc(c.insurer)} · ${statusPill(c.status)} · 등록 ${esc((c.created_at||'').slice(0,16))}</div>

    <div class="ph" style="margin-top:12px"><span class="pt" style="font-size:.8rem">🔎 가견적 점검</span></div>
    <div id="ebbox" class="msub">불러오는 중…</div>

    <div class="ph" style="margin-top:12px"><span class="pt" style="font-size:.8rem">⚖️ 도급 적법성 판정 이력</span></div>
    <div id="ghbox" class="msub">불러오는 중…</div>

    <div class="ph" style="margin-top:12px"><span class="pt" style="font-size:.8rem">📉 입찰 인하 이력 <small>역경매 증거</small></span></div>
    <div id="bhbox" class="msub">불러오는 중…</div>

    <div class="ph" style="margin-top:12px"><span class="pt" style="font-size:.8rem">🧭 진행 타임라인</span></div>
    <div id="tlbox" class="msub">불러오는 중…</div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:12px 0">
      <div class="kc"><div class="k">가견적(${c.auction_round===2?'2차 하한':'상한'})</div>
        <div class="v" style="font-size:1.1rem">${won(c.auction_round===2?c.bid_floor:c.est_price)}<small>원</small></div>
        ${c.auction_round===2?`<div class="d">현장 실견적 ${won(c.field_ref)}원 · 상한 없음</div>`:''}</div>
      <div class="kc"><div class="k">최저/낙찰</div><div class="v" style="font-size:1.1rem">${won(c.low_price||c.award_amount)}<small>원</small></div></div>
      <div class="kc"><div class="k">시공 사진</div><div class="v" style="font-size:1.1rem">${ph.total||0}<small>장 (승인 ${ph.approved||0})</small></div></div>
      <div class="kc"><div class="k">정산</div><div class="v" style="font-size:.9rem">${st?statusPill(st.transfer_status):'<span class="pill gray">미생성</span>'}</div></div>
    </div>

    <div class="ph" style="margin-top:6px"><span class="pt" style="font-size:.8rem">입찰 내역 <small>${d.bids.length}건</small></span></div>
    <div class="tbl-wrap" style="max-height:180px;overflow:auto"><table class="tbl">
      <tr><th>업체</th><th class="r">입찰가</th><th class="r">공기</th><th>일시</th></tr>
      ${d.bids.length?d.bids.map((b,i)=>`<tr><td>${esc(b.partner_name||'-')}${i===0?' <span class="pill green">최저</span>':''}</td>
        <td class="r em">${won(b.amount)}</td><td class="r">${b.days}일</td><td>${esc((b.created_at||'').slice(5,16))}</td></tr>`).join('')
        :'<tr><td colspan="4" class="empty">입찰 없음</td></tr>'}
    </table></div>

    ${d.defects.length?`<div class="ph" style="margin-top:10px"><span class="pt" style="font-size:.8rem;color:var(--red)">하자 ${d.defects.length}건</span></div>
      <div style="font-size:.72rem">${d.defects.map(x=>`· ${esc(x.defect_no)} ${esc(x.title)} <span style="color:var(--faint)">(${esc(x.severity)}/${esc(x.status)})</span>`).join('<br>')}</div>`:''}

    <div class="ph" style="margin-top:14px;padding-top:10px;border-top:1px solid var(--line)"><span class="pt" style="font-size:.8rem">사건 정보 수정</span></div>
    ${editable?'':`<div class="msub" style="color:var(--amber-text)">※ 입찰이 마감된 사건입니다. 가견적은 잠기고, 공종·지역·주소·담당·긴급·보증만 수정할 수 있습니다.</div>`}
    ${/*  ⚠⚠ [라운드249] PATCH /api/cases/<id>(이 폼 전체+아래 피해자 정보가 모두
           이 한 엔드포인트로 간다)는 중간관리자 이상 전용인데, 이 폼은 등급 무관하게
           항상 편집 가능하게 그려졌다 — 하위관리자는 값을 다 고치고 저장을 눌러야만
           403을 만났다. 형제 화면(estbands·boq, 246·247라운드)처럼 등급 미달이면
           읽기전용으로 바꾼다(값은 계속 보여준다 — 참고정보로 여전히 유용하다). */''}
    ${myRank()<2?'<div class="hint">사건 정보·피해자 정보 수정은 중간관리자 이상만 할 수 있습니다.</div>':''}
    <div class="grid2">
      <div class="field"><label>공종</label><input id="e_cat" value="${esc(c.category||'')}"${myRank()<2?' disabled':''}></div>
      <div class="field"><label>지역</label><input id="e_region" value="${esc(c.region||'')}"${myRank()<2?' disabled':''}></div>
    </div>
    <div class="field"><label>주소</label><input id="e_addr" value="${esc(c.address||'')}"${myRank()<2?' disabled':''}></div>
    <div class="grid2">
      <div class="field"><label>가견적(${c.auction_round===2?'2차 하한':'상한'}) ${editable?'':'<small style="color:var(--faint)">— 잠김</small>'}</label><input id="e_est" type="text" inputmode="numeric" value="${(c.est_price||0).toLocaleString('ko-KR')}" data-act-input="moneyInput" style="text-align:right" ${(editable&&myRank()>=2)?'':'disabled style="background:var(--mist)"'}><div class="money-ko" style="font-size:.7rem;color:var(--amber-text);font-weight:700;margin-top:3px;text-align:right"></div>${c.auction_round===2&&!c.est_price?`<div class="d">0원(직접 입력 안 함) → 표준단가 개산 하한 ${won(c.bid_floor)}원이 실제 적용 중</div>`:''}</div>
      <div class="field"><label>담당</label><input id="e_mgr" value="${esc(c.manager||'')}"${myRank()<2?' disabled':''}></div>
    </div>
    <div class="grid2">
      <!--  0 은 '무보증' 이라는 유효한 값이다 — || 는 0 도 걸러 24로 둔갑시킨다.
            (0 으로 저장해 놓고 이 폼을 다시 열면 24가 보여 관리자가 저장된 값을 오독한다) -->
      <div class="field"><label>보증(개월)</label><input id="e_warr" type="number" min="0" max="120" value="${c.warranty_months??24}"${myRank()<2?' disabled':''}></div>
      <div class="field"><label>긴급</label><select id="e_urgent"${myRank()<2?' disabled':''}><option value="0" ${!c.urgent?'selected':''}>일반</option><option value="1" ${c.urgent?'selected':''}>긴급</option></select></div>
    </div>
    <div class="ph" style="margin-top:14px;padding-top:10px;border-top:1px solid var(--line)"><span class="pt" style="font-size:.8rem">📝 메모 · 추가 요청</span></div>
    <div id="memobox" class="msub">불러오는 중…</div>
    <div style="display:flex;gap:8px;align-items:center;margin-top:8px">
      <input id="memo_body" placeholder="추가 요청·중요 메모 입력" style="flex:1" data-act-enter="addMemo" data-arg="case:${id}">
      <label style="font-size:.72rem;white-space:nowrap"><input type="checkbox" id="memo_imp" style="width:auto;margin-right:4px">중요</label>
      <button class="btn p sm" data-act="addMemo" data-arg="case:${id}">메모 추가</button>
    </div>
    <div class="ph" style="margin-top:14px;padding-top:10px;border-top:1px solid var(--line)"><span class="pt" style="font-size:.8rem">🧰 운영 도구</span></div>
    <div class="grid2">
      <div class="field"><label>피해자 이름</label><input id="e_vname" value="${esc(c.victim_name||'')}" placeholder="해피콜·안내용"${myRank()<2?' disabled':''}></div>
      <div class="field"><label>피해자 연락처</label><input id="e_vphone" value="${esc(c.victim_phone||'')}" placeholder="010-0000-0000"${myRank()<2?' disabled':''}></div>
    </div>
    <div class="grid2">
      <div class="field"><label>위도 <small style="color:var(--faint)">(정밀 위치 필요 시)</small></label><input id="e_lat" value="${c.lat??''}" placeholder="37.5145"></div>
      <div class="field"><label>경도</label><input id="e_lng" value="${c.lng??''}" placeholder="127.1059"></div>
    </div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin:2px 0 4px">
      <button class="btn g sm" data-act="coordsSave" data-arg="${id}">📍 좌표 저장</button>
      ${c.lat!=null?`<button class="btn g sm" data-act="coordsClear" data-arg="${id}">좌표 해제</button>`:''}
      <button class="btn g sm" data-act="caseGate" data-arg="${id}">⚖️ 도급 판정</button>
      <button class="btn g sm" data-act="dispatchReport" data-arg="${id}">📄 현장 출동 보고서</button>
      ${/*  ⚠ 링크가 있으면 **열어 봤는지**를 함께 보여 준다. 보낸 사실만 알면
             "안내했는데 왜 전화가 오나" 를 설명할 수 없다. */''}
      <a class="btn g sm" href="/report/case/${id}" target="_blank" rel="noopener"
         title="접수부터 정산까지 누가 언제 무엇을 했는지 한 장으로 — 분쟁 대응용">📄 사건 전체 이력</a>
      <button class="btn g sm" data-act="trackLink" data-arg="${id}">🔗 피해자 조회 링크 ${c.track_token?'재발급':'발급'}</button>
      ${c.track_token ? `<span class="hint" style="margin-left:8px">${
        (c.track_views||0) > 0
          ? `피해자가 <b style="color:var(--ok)">${c.track_views}회</b> 확인 (마지막 ${esc((c.track_last_at||'').slice(5,16))})`
          : '<b style="color:var(--amber-text)">아직 열어 보지 않음</b>'}</span>` : ''}
      ${/*  ⚠ 서버 오류 문구는 "마감을 늦춰 주세요"라고 지시하는데, 마감시각을 바꿀
             창구가 어느 화면에도 없었다(라우트만 있고 버튼이 없었다). */''}
      ${(d.auction && d.auction.status==='진행' && myRank()>=2)
        ? `<button class="btn g sm" data-act="auctionDeadline" data-arg="${d.auction.id}"
             data-arg2="${esc(d.auction.deadline||'')}">⏱ 입찰 마감 변경</button>` : ''}
      ${/*  ⚠ 보험사가 메일·카톡으로 뒤늦게 사진을 보내와도 붙일 칸이 없어,
             '사진없음' 접수 건이 '접수'에 갇혔다(경매를 여는 근거가 사진이다). */''}
      ${(c.status==='접수' && myRank()>=2)
        ? `<label class="btn a sm" style="cursor:pointer">📷 피해 사진 올리기
             <input type="file" accept="image/*" multiple hidden id="dmg_${id}"></label>` : ''}
      ${c.status==='완료'?`<button class="btn g sm" data-act="hcForm" data-arg="${id}" data-arg2="${esc(c.case_no)}">📞 해피콜 기록</button>`:''}
    </div>
    ${c.track_token?`<div class="hint">현재 조회 링크: <span class="em">/track/${esc(c.track_token)}</span> — 재발급하면 이전 링크는 무효가 됩니다.</div>`:''}
    ${(d.auction && d.auction.deadline)?`<div class="hint">입찰 마감 <b>${esc(String(d.auction.deadline).slice(0,16))}</b> · 경매 ${esc(d.auction.status)}</div>`:''}
    <div id="gate-result"></div>

    <div class="ph" style="margin-top:14px;padding-top:10px;border-top:1px solid var(--line)">
      <span class="pt" style="font-size:.8rem">🏗️ 현장 근처 시행·시공사 <small>가까운 순</small></span>
      <span style="flex:1"></span>
      <label style="font-size:.7rem;color:var(--faint)"><input type="checkbox" id="near_trade" data-act-change="nearbyReload" data-arg="${id}" style="width:auto;margin-right:4px">이 공종만</label>
    </div>
    <div id="nearbox" class="msub">불러오는 중…</div>

    <div class="modal-foot">
      ${myRank()>=2?`<button class="btn p" data-act="saveCaseEdit" data-arg="${id}">수정 저장</button>`:''}
      ${(c.status==='유찰' && myRank()>=2)
        ? `<button class="btn g" data-act="caseReopen" data-arg="${id}">입찰 재개</button>
           <button class="btn g" data-act="caseCloseOffline" data-arg="${id}"
             title="재개해도 입찰이 없을 때 — 이 사건을 플랫폼에서 종결합니다">📴 오프라인 전환 종결</button>` : ''}
      ${(c.status==='미수선종결' && myRank()>=2)
        ? `<button class="btn g" data-act="caseUndoNoRepair" data-arg="${id}"
             title="현장에서 잘못 눌렀을 때 되돌립니다">↩ 미수선 종결 되돌리기</button>` : ''}
      ${/*  ⚠ 마감 전에 손쓸 수 있는 유일한 수단이다. 유찰이 된 뒤에는
             재공고밖에 없고, 그동안 피해자는 아무 일도 없이 기다린다.
             알림을 다시 보낼 뿐 — 낙찰을 정하거나 업체를 지목하지 않는다.
             ⚠⚠ [라운드249] 이 버튼은 게이트 대상이 아니다 — api_case_renotify는
             require_role("하위관리자")로 등급 무관 전체 허용, 형제 버튼들과 다르다. */''}
      ${c.status==='입찰중'
        ? `<button class="btn g" data-act="caseRenotify" data-arg="${id}"
             title="열려 있는 공고를 협력사에게 다시 알립니다">🔔 공고 다시 알리기</button>` : ''}
      ${((c.status==='입찰중'||c.status==='승인대기') && myRank()>=2)
        ? `<button class="btn g" data-act="caseFailBidding" data-arg="${id}">유찰 확정</button>` : ''}
      ${/*  ⚠ 시스템은 세 곳에서 "업체 계정을 발급하거나 **출동 수배로 전환하세요**" 라고
             알린다. 그 전환 라우트를 만들어 놓고 **누를 곳을 안 만들어서**, 운영자는
             여전히 시킨 일을 할 수 없었다(라우트만 있고 입구가 없는 상태). */''}
      ${((c.status==='입찰중'||c.status==='유찰') && !c.partner_id && myRank()>=2)
        ? `<button class="btn g" data-act="caseToDispatch" data-arg="${id}"
             title="투찰이 없을 때 — 공고를 접고 인근 업체 출동으로 현장 사진을 먼저 확보합니다">🚨 출동 수배로 전환</button>` : ''}
      ${(c.status==='검수대기' && myRank()>=2)
        ? `<button class="btn a" data-act="caseApprove" data-arg="${id}">✅ 검수 승인 · 정산 생성</button>` : ''}
      ${(['시공중','완료보고지연'].includes(c.status) && c.partner_id && myRank()>=2)
        ? `<button class="btn g" data-act="caseCancelAward" data-arg="${id}" title="낙찰업체 부도·잠적·착공거부 시">⛔ 낙찰 취소·재공고</button>` : ''}
      ${/*  ⚠⚠ [라운드249] 이 버튼도 게이트 대상이 아니다 — api_case_remind_report는
             @require_admin(등급 무관)이다. */''}
      ${c.status==='완료보고지연'
        ? `<button class="btn a" data-act="caseRemindReport" data-arg="${id}" title="협력사에 완료 보고를 독촉합니다">📣 완료보고 독촉</button>` : ''}
      ${(c.status==='접수' && myRank()>=2)
        ? `<button class="btn a" data-act="caseOpenAuction" data-arg="${id}" title="확보한 현장 사진으로 공고를 엽니다">🔨 경매 열기(공고)</button>` : ''}
      <span style="flex:1"></span>
      <button class="btn g" data-act="closeModal">닫기</button>
    </div>`);
  loadMemos('case', id);
  loadEstCheck(id);
  loadGateHistory(id);
  loadBidHistory(id);
  loadTimeline(id);
  loadNearby(id);
  const dmg = document.getElementById('dmg_'+id);
  if(dmg) dmg.addEventListener('change', ()=>uploadDamagePhotos(id, dmg));
}

//  뒤늦게 받은 피해 사진 붙이기 — 이게 있어야 '접수'에 갇힌 건이 공고로 나갈 수 있다.
//  (경매를 여는 근거는 사진이다. 서버 라우트는 원래 있었고 화면만 없었다)
async function uploadDamagePhotos(cid, input){
  const files = [...(input.files||[])];
  if(!files.length) return;
  const big = files.filter(f=>f.size > 8*1024*1024);
  if(big.length) toast(`${big.length}장이 8MB를 넘어 제외됩니다.`);
  const ok = files.filter(f=>f.size <= 8*1024*1024);
  if(!ok.length){ input.value=''; return; }
  const fd = new FormData();
  ok.forEach(f=>fd.append('photos', f));
  toast(`사진 ${ok.length}장 올리는 중…`);
  //  ⚠ [라운드77] createCase() 와 같은 이유 — 이 구간이 도는 동안은 세션만료로
  //    인한 강제이동을 미룬다.
  UP_BUSY = true;
  try{
    const r = await fetch(`/api/cases/${cid}/photos/damage`,
      {method:'POST', headers:{'X-CSRF-Token':CSRF}, credentials:'same-origin', body:fd});
    const j = await r.json().catch(()=>({}));
    if(!r.ok || !j.ok) throw new Error(j.error || '업로드에 실패했습니다.');
    //  ⚠ 보낸 장수가 아니라 **서버가 저장한 장수**를 센다(형식·중복은 서버가 거른다).
    const n = (typeof j.count === 'number') ? j.count : ok.length;
    //  ⚠⚠ [라운드249] createCase() 형제(등록 화면 안의 같은 업로드, "[라운드77]
    //    createCase()와 같은 이유"로 이미 스스로 짝지어 놓은 그 코드)는 왜 장수가
    //    다른지(중복·오류)와 AI 분석까지 같이 보여주는데, 이 화면은 성공하면
    //    그냥 "N장을 올렸습니다"만 말해 5장을 보내고 2장이 걸러져도 이유를 알
    //    길이 없었다 — 바로 위 주석("형식·중복은 서버가 거른다")이 이미 인정하는
    //    사실을 정작 화면엔 안 보여준 것. 같은 구성으로 통일.
    if(n){
      const why = [];
      if(j.duplicates) why.push(`같은 사진 ${j.duplicates}장 제외`);
      if(j.errors && j.errors.length) why.push(esc(String(j.errors[0]).slice(0,40)));
      const head = `피해 사진 <b>${n}/${ok.length}장</b> 등록. 이제 공고를 열 수 있습니다.`
                 + (why.length ? ` (${why.join(' · ')})` : '');
      toast(j.ai_report ? `${head}<br><b>AI 분석:</b> ${esc(j.ai_report)}` : head);
    }else{
      toast(`저장된 사진이 없습니다. ${esc((j.errors||[''])[0]||'파일 형식을 확인해 주세요.')}`);
    }
    closeModal(); caseDetail(cid);
  }catch(e){ toast(e.message); }
  finally { UP_BUSY = false; }
  input.value = '';
}

// ── 도급 적법성 판정 이력 (확정 시점 스냅샷) ────────────────────
async function loadGateHistory(id){
  const box = $('#ghbox'); if(!box) return;
  let d;
  try{ d = await api('GET','/api/cases/'+id+'/gate-history'); }
  catch(e){ box.textContent='판정 이력을 불러오지 못했습니다.'; return; }
  const h = d.history||[];
  if(!h.length){
    box.innerHTML = `<div class="sub" style="padding:4px 0">${esc(d.note||'')}
      <button class="btn g sm" data-act="caseGate" data-arg="${id}" style="margin-left:6px">지금 판정해 보기</button></div>`;
    return;
  }
  const pill = c => c==='도급가능' ? 'green' : c==='판정불가' ? 'gray' : 'red';
  box.innerHTML = `<div class="tbl-wrap" style="max-height:180px;overflow:auto"><table class="tbl">
      <tr><th>판정</th><th>경로</th><th class="r">금액</th><th class="r">합산</th><th>판정표</th><th>확정</th></tr>
      ${h.map(x=>`<tr>
        <td><span class="pill ${pill(x.code)}">${esc(x.code)}</span></td>
        <td>${esc(x.route||'-')}</td>
        <td class="r">${won(x.amount)}</td>
        <td class="r">${x.related_amount?won(x.related_amount):'-'}</td>
        <td class="hint">${esc(x.rules_version||'-')}${x.rules_version!==d.current_rules_version?' <span style="color:var(--amber-text)">(구판)</span>':''}</td>
        <td class="hint">${esc((x.decided_at||'').slice(5,16))}<br>${esc(x.decided_by||'')}</td></tr>`).join('')}
    </table></div>
    ${h[0].reason?`<div class="hint" style="margin-top:4px">${esc(h[0].reason)}</div>`:''}
    ${h[0].related_case_nos?`<div class="hint">합산 대상(확정 시점): ${esc(h[0].related_case_nos)}</div>`:''}
    <div class="hint" style="margin-top:4px">${esc(d.note||'')}</div>`;
}

// ── 입찰 인하 이력 (역경매 증거) ────────────────────────────────
async function loadBidHistory(id){
  const box = $('#bhbox'); if(!box) return;
  let d;
  try{ d = await api('GET','/api/cases/'+id+'/bid-history'); }
  catch(e){ box.textContent='입찰 이력을 불러오지 못했습니다.'; return; }
  const bp = d.by_partner||[], ev = d.events||[];
  if(!bp.length){ box.innerHTML=`<div class="sub" style="padding:4px 0">${esc(d.note||'')}</div>`; return; }
  box.innerHTML = `
    ${(d.shared_ip||[]).length?`<div class="notice red" style="margin-bottom:8px">
      ⚠ 같은 접속 위치에서 서로 다른 업체가 투찰했습니다 — 들러리·담합 여부를 확인하세요.
      ${d.shared_ip.map(x=>`<div style="font-size:.72rem">${esc(x.names||'')} (${x.n_partner}개사)</div>`).join('')}</div>`:''}
    <div class="tbl-wrap" style="max-height:180px;overflow:auto"><table class="tbl">
      <tr><th>업체</th><th class="r">첫 투찰</th><th class="r">최종</th><th class="r">총 인하</th><th class="r">회차</th><th>기간</th></tr>
      ${bp.map(b=>`<tr>
        <td>${esc(b.partner_name||'')}${b.low_flag?' <span class="pill red" title="저가 경보가 걸린 투찰 포함">저가</span>':''}</td>
        <td class="r">${won(b.first_amount)}</td>
        <td class="r em">${won(b.last_amount)}</td>
        <td class="r" style="color:var(--green);font-weight:800">${b.total_drop_pct>0?'-'+b.total_drop_pct+'%':'-'}</td>
        <td class="r">${b.rounds}회</td>
        <td class="hint">${esc((b.first_at||'').slice(5,16))}${b.rounds>1?` → ${esc((b.last_at||'').slice(5,16))}`:''}</td></tr>`).join('')}
    </table></div>
    ${ev.length>bp.length?`<details style="margin-top:6px"><summary style="cursor:pointer;font-size:.72rem;color:var(--blue)">투찰 시계열 ${ev.length}건 펼치기</summary>
      <div class="tbl-wrap"><table class="tbl" style="margin-top:5px"><tr><th>시각</th><th>업체</th><th>구분</th><th class="r">직전</th><th class="r">제출</th><th class="r">인하</th></tr>
      ${ev.map(e=>`<tr><td class="hint">${esc((e.created_at||'').slice(5,16))}</td>
        <td>${esc(e.partner_name||'')}</td><td class="hint">${esc(e.kind||'')} ${e.seq}회</td>
        <td class="r hint">${e.prev_amount?won(e.prev_amount):'-'}</td>
        <td class="r em">${won(e.amount)}</td>
        <td class="r" style="color:var(--green)">${e.drop_pct?'-'+e.drop_pct+'%':'-'}</td></tr>`).join('')}
      </table></div></details>`:''}
    <div class="hint" style="margin-top:4px">${esc(d.note||'')}</div>`;
}

// ── 가견적 점검 (운영자용 · 읽기) ───────────────────────────────
//  파손 정도 확정·경보 확인은 **보험사가** 한다(판정 주체는 보상 담당자).
//  운영자는 무엇이 걸려 있는지 보고, 점검 기준을 채운다.
const EB_PILL = {'정상':'green','금액과다':'red','금액과소':'amber','판정없음':'amber',
  '기준없음':'gray','복합미대조':'gray','사진없음':'red'};
async function loadEstCheck(id){
  const box = $('#ebbox'); if(!box) return;
  let b;
  try{ b = await api('GET','/api/cases/'+id+'/est-basis'); }
  catch(e){ box.textContent = '점검 결과를 불러오지 못했습니다.'; return; }
  box.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span class="pill ${EB_PILL[b.code]||'gray'}">${esc(b.code)}</span>
      <span style="font-size:.76rem">${esc(b.note||'')}</span>
    </div>
    <div style="font-size:.72rem;color:var(--sub);margin-top:5px">
      가견적 <b>${won(b.est_price)}원</b> · 파손정도 ${esc(b.severity||'미정')}(${esc(b.severity_src||'')})
      · 점검구간 ${b.band?won(b.band.min_price)+'~'+won(b.band.max_price)+'원':'기준 미등록'}
      · 현장사진 ${b.photo_count||0}장
      ${b.acked?` · <span style="color:var(--green)">확인완료 ${esc(b.ack_by||'')}</span>`:''}
    </div>
    ${b.code==='기준없음'?`<div class="hint" style="margin-top:4px">이 공종의 점검 기준을 등록하면 대조가 시작됩니다 — 좌측 <b>가견적 점검 기준</b> 메뉴.</div>`:''}
    ${b.code==='판정없음'?`<div class="hint" style="margin-top:4px">파손 정도 확정은 보험사 담당자가 포털에서 직접 합니다(판정 주체=사람).</div>`:''}`;
}

// ── 진행 타임라인 (접수→출동→합의/경매→시공→완료→정산→해피콜) ──
const TL_ICON = {'접수':'📥','출동':'🚨','종결':'🚫','합의':'🤝','낙찰':'⚖️',
  '시공':'🔨','완료':'✅','정산':'💰','해피콜':'📞'};
const TL_COLOR = {'접수':'#0064B2','출동':'#C0392B','종결':'#8496A6','합의':'#137A38',
  '낙찰':'#004E8C','시공':'#B26A00','완료':'#137A38','정산':'#7A4FBF','해피콜':'#0064B2'};
async function loadTimeline(id){
  const box = $('#tlbox'); if(!box) return;
  let d;
  try{ d = await api('GET','/api/cases/'+id+'/timeline'); }
  catch(e){ box.textContent='타임라인을 불러오지 못했습니다.'; return; }
  const ev = d.events||[];
  if(!ev.length){ box.innerHTML='<div class="sub" style="padding:4px 0">아직 진행 이력이 없습니다.</div>'; return; }
  const pc = (d.photo_phases||[]).filter(p=>['착공전','시공중','완료'].includes(p.kind));
  box.innerHTML = `
    <div style="position:relative;padding-left:18px;margin-top:4px">
      <div style="position:absolute;left:6px;top:6px;bottom:6px;width:2px;background:var(--line)"></div>
      ${ev.map(e=>`<div style="position:relative;margin-bottom:11px">
        <div style="position:absolute;left:-18px;top:1px;width:14px;height:14px;border-radius:50%;
          background:${TL_COLOR[e.kind]||'#8496A6'};border:2px solid #fff;box-shadow:0 0 0 1px var(--line)"></div>
        <div style="font-size:.78rem;font-weight:800">${TL_ICON[e.kind]||'•'} ${esc(e.title)}</div>
        ${e.note?`<div style="font-size:.7rem;color:var(--sub)">${esc(e.note)}</div>`:''}
        <div style="font-size:.64rem;color:var(--faint)">${esc((e.at||'').slice(0,16))}</div>
      </div>`).join('')}
    </div>
    ${pc.length?`<div class="hint" style="margin-top:6px;padding-top:6px;border-top:1px dashed var(--line)">
      📸 사진 연속성: ${pc.map(p=>`${esc(p.kind)} ${p.n}장(승인 ${p.approved||0})`).join(' → ')}</div>`:''}`;
}

// ── 현장 근처 시행·시공사 (거리순) ──────────────────────────────
async function loadNearby(id){
  const box = $('#nearbox'); if(!box) return;
  const trade = ($('#near_trade')||{}).checked ? 1 : 0;
  box.innerHTML = '불러오는 중…';
  let d;
  try{ d = await api('GET',`/api/cases/${id}/nearby?limit=8&trade=${trade}`); }
  catch(e){ box.textContent = '인근 업체를 불러오지 못했습니다.'; return; }
  if(!d.partners || !d.partners.length){
    box.innerHTML = `<div class="sub" style="padding:4px 0">${esc(d.note||'표시할 인근 업체가 없습니다.')}</div>`;
    return;
  }
  const pill = t => t==='시행사'
    ? '<span class="pill blue" style="font-size:.6rem">시행</span>'
    : '<span class="pill gray" style="font-size:.6rem">시공</span>';
  const lic = l => l==='등록확인'
    ? '<span style="color:var(--green)">건설업 등록확인</span>'
    : `<span style="color:var(--faint)">건설업 ${esc(l||'미확인')}</span>`;
  //  ★ **첫 주에는 이 칸이 제일 중요하다.** 포털 계정도 휴대폰도 없는 업체가
  //    399곳 중 330곳이라, 업체를 부르는 길은 사실상 전화뿐이다.
  //    번호를 눌러 바로 걸 수 있게 하고, 연락 수단을 사실대로 적는다.
  const REACH = {'포털':['green','앱에서 수락 가능'],'문자':['blue','문자 발송 가능'],
                 '유선':['gray','유선만 — 전화로만 연결'],'없음':['gray','연락 수단 없음']};
  const nearPhone = p => {
    const [cls, tip] = REACH[p.reach] || REACH['없음'];
    const tag = `<span class="pill ${cls}" style="font-size:.58rem" title="${esc(tip)}">${esc(p.reach||'없음')}</span>`;
    if(!p.phone) return `<span style="color:var(--faint)">번호 없음</span> ${tag}`;
    //  ⚠ data-act 를 붙이지 않는다 — 등록되지 않은 액션은 '죽은 버튼' 으로 잡힌다.
    //    행 클릭(지도 이동)도 함께 일어나지만 해가 없다.
    return `<a href="tel:${esc(String(p.phone).replace(/[^0-9+]/g,''))}"
              style="font-weight:700">${esc(p.phone)}</a> ${tag}`;
  };
  box.innerHTML = `<div class="hint" style="margin:0 0 6px">현장 좌표(${esc(d.case_geo_src||'개략')}) 기준 직선거리 · 도로거리와 다를 수 있습니다. 전체 ${d.total_scored}개사 중 가까운 ${d.partners.length}곳.</div>
    <div id="nearmap" style="height:230px;border-radius:10px;border:1px solid var(--line);margin-bottom:8px"></div>
    <div class="tbl-wrap" style="max-height:210px;overflow:auto"><table class="tbl">
      <tr><th style="width:30px" class="r">#</th><th style="width:52px" class="r">거리</th><th>업체</th><th>연락처</th><th>공종</th><th>등록·실적</th></tr>
      ${d.partners.map((p,i)=>`<tr data-act="nearFocus" data-arg="${i}" style="cursor:pointer" title="지도에서 위치 보기">
        <td class="r hint">${i+1}</td>
        <td class="r em" style="color:var(--blue);white-space:nowrap">${p.dist_km}<small>km</small></td>
        <td>${pill(p.type)} ${esc(p.name)}${p.called?' <span class="pill amber" style="font-size:.58rem">이미 부름</span>':''}</td>
        <td style="font-size:.72rem;white-space:nowrap">${nearPhone(p)}</td>
        <!--  ⚠ 실제 데이터의 공종은 200자를 넘는다("외벽공사 / 테라스·데크 / 부분
              리모델링~전체 인테리어 / 철제 구조물 / 철거 / 타일 / 설비"). 그대로 두면
              한 행이 예닐곱 줄이 되어, 스크롤 상자(210px) 안에 두 곳밖에 안 보인다 —
              첫 주엔 이 표가 곧 콜 리스트다. 두 줄로 자르고 전체는 툴팁으로 준다. -->
        <td style="font-size:.72rem" title="${esc(p.category||'')}">
          <span style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
                       overflow:hidden">${esc(p.category||'-')}</span>
          <span style="color:var(--faint)">${esc(p.region||'')}</span></td>
        <td style="font-size:.68rem">${lic(p.license)} · 평점 ${p.rating||'-'} · 이행 ${p.jobs||0}건</td>
      </tr>`).join('')}
    </table></div>`;
  nearMapDraw(d);
}

// ── 인근업체 미니 지도 (사건 상세 모달 안) ─────────────────────
//  ⚠ 모달은 열고 닫힐 때마다 innerHTML 이 갈리므로, 지도 인스턴스를 반드시 정리한다.
//    안 그러면 Leaflet 이 사라진 DOM 을 붙들고 있어 다음 열기에서 깨진다.
let NEAR_MAP = null, NEAR_MARKERS = [], NEAR_DATA = null;
function nearMapDestroy(){
  if(NEAR_MAP){ try{ NEAR_MAP.remove(); }catch(e){} NEAR_MAP = null; }
  NEAR_MARKERS = []; NEAR_DATA = null;
}
function nearMapDraw(d){
  nearMapDestroy();
  const el = $('#nearmap');
  if(!el || typeof L === 'undefined' || d.case_lat == null) { if(el) el.style.display='none'; return; }
  NEAR_DATA = d;
  NEAR_MAP = L.map('nearmap', {zoomControl:true, attributionControl:false});
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:18}).addTo(NEAR_MAP);

  // 현장 — 빨간 원(가운데)
  const site = L.circleMarker([d.case_lat, d.case_lng],
    {radius:11, weight:3, color:'#fff', fillColor:'#C0392B', fillOpacity:.95}).addTo(NEAR_MAP);
  site.bindPopup(`<div style="font-family:'Malgun Gothic',sans-serif"><b>🚩 사고 현장</b><br>
    <span style="font-size:.74rem;color:#888">${esc(d.case_geo_src||'개략 위치')}</span></div>`);

  // 인근 업체 — 순번 뱃지(시행=파랑 ▲ / 시공=금색 ■)
  const pts = [[d.case_lat, d.case_lng]];
  (d.partners||[]).forEach((p,i)=>{
    const prime = p.type==='시행사';
    const bg = prime ? '#004E8C' : '#C9852A';
    const ic = L.divIcon({className:'', iconSize:[20,20], iconAnchor:[10,10],
      html:`<div style="width:20px;height:20px;border-radius:50%;background:${bg};color:#fff;
        font:800 11px 'Malgun Gothic',sans-serif;display:flex;align-items:center;justify-content:center;
        border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.4)">${i+1}</div>`});
    const m = L.marker([p.lat, p.lng], {icon:ic}).addTo(NEAR_MAP);
    m.bindPopup(`<div style="font-family:'Malgun Gothic',sans-serif;min-width:150px">
      <b>${esc(p.name)}</b> <span style="font-size:.7rem">(${esc(p.type)})</span><br>
      <span style="font-size:.78rem;color:#0064B2;font-weight:700">현장에서 약 ${p.dist_km}km</span><br>
      <span style="font-size:.74rem">${esc(p.category||'')} · ${esc(p.region||'')}</span><br>
      <span style="font-size:.7rem;color:#888">건설업 ${esc(p.license)} · 평점 ${p.rating||'-'}</span></div>`);
    NEAR_MARKERS.push(m);
    pts.push([p.lat, p.lng]);
    // 현장 ↔ 업체 연결선(가까운 3곳만 — 다 그리면 지저분하다)
    if(i < 3) L.polyline([[d.case_lat,d.case_lng],[p.lat,p.lng]],
      {color:'#0064B2', weight:1.5, opacity:.35, dashArray:'4,4'}).addTo(NEAR_MAP);
  });
  const bounds = L.latLngBounds(pts).pad(0.18);
  NEAR_MAP.fitBounds(bounds);
  // 모달이 방금 그려져 크기가 0인 채 초기화될 수 있다 — 다음 프레임에 재계산.
  //  ⚠ 크기가 0이었을 때만 경계를 다시 맞춘다. 무조건 다시 맞추면 사용자가 그새 지도를
  //    움직였을 경우 시야를 강제로 되돌려 버린다.
  const wasBlind = (NEAR_MAP.getSize().x < 8 || NEAR_MAP.getSize().y < 8);
  setTimeout(()=>{
    if(!NEAR_MAP) return;
    NEAR_MAP.invalidateSize();
    if(wasBlind) NEAR_MAP.fitBounds(bounds);   // 크기를 몰라 줌이 어긋난 경우만 복구
  }, 120);
}
function nearFocus(i){
  if(!NEAR_MAP || !NEAR_MARKERS[i]) return;
  const p = (NEAR_DATA.partners||[])[i];
  NEAR_MAP.setView([p.lat, p.lng], 13, {animate:true});
  NEAR_MARKERS[i].openPopup();
  $('#nearmap').scrollIntoView({behavior:'smooth', block:'nearest'});
}

// ── 메모 (추가 요청·중요 메모) ──
async function loadMemos(type, id){
  const box=$('#memobox'); if(!box) return;
  try{
    const ms = await api('GET',`/api/memos?target=${type}&id=${id}`);
    box.innerHTML = ms.length?ms.map(m=>`<div style="display:flex;justify-content:space-between;gap:8px;padding:7px 10px;border:1px solid var(--line);border-radius:8px;margin-bottom:6px;${m.important&&!m.done?'background:#FFFBF3;border-color:#F5DCB2':''}${m.done?'opacity:.55':''}">
        <div style="font-size:.76rem">${m.important?'<span class="pill amber" style="margin-right:6px">중요</span>':''}${m.done?'<span class="pill gray" style="margin-right:6px">완료</span>':''}${esc(m.body)}
          <div style="font-size:.64rem;color:var(--faint);margin-top:2px">${esc(m.author||'')} · ${esc((m.created_at||'').slice(0,16))}</div></div>
        <div style="white-space:nowrap">
          ${m.important&&!m.done?`<button class="btn g sm" data-act="memoDone" data-arg="${m.id}" data-arg2="${type}:${id}" title="처리 완료">✓</button>`:''}
          ${/*  ⚠⚠ [339라운드] DELETE /api/memos/<id> 는 require_role(중간관리자,
                  app.py:1472) — 등급 무관하게 그려져 있었다. 이 위젯을 쓰는 모든
                  화면(사건상세 등)에 공통으로 적용되던 결함이라 여기 한 곳만
                  고치면 전부 해결된다(memoDone/PATCH 는 require_admin 이라
                  등급무관이 맞아 그대로 둠). */''}
          ${myRank()>=2?`<button class="btn g sm" data-act="memoDel" data-arg="${m.id}" data-arg2="${type}:${id}" title="삭제">✕</button>`:''}
        </div>
      </div>`).join(''):'<div class="sub" style="padding:4px 0">메모 없음</div>';
  }catch(e){ box.textContent='메모를 불러오지 못했습니다.'; }
}
async function addMemo(arg){
  const [type,id]=String(arg).split(':');
  const body=($('#memo_body').value||'').trim();
  if(!body){ toast('메모 내용을 입력하세요.'); return; }
  try{
    await api('POST','/api/memos',{target_type:type, target_id:Number(id), body, important:$('#memo_imp').checked});
    $('#memo_body').value=''; $('#memo_imp').checked=false;
    loadMemos(type, id); refreshBadges();
  }catch(e){ toast(e.message); }
}
async function memoDone(mid, tgt){
  try{ await api('PATCH','/api/memos/'+mid,{done:true}); const [t,i]=String(tgt).split(':'); loadMemos(t,i); refreshBadges(); }catch(e){ toast(e.message); }
}
async function memoDel(mid, tgt){
  if(!confirm('이 메모를 삭제합니다. 되돌릴 수 없습니다. 진행할까요?')) return;
  try{ await api('DELETE','/api/memos/'+mid); const [t,i]=String(tgt).split(':'); loadMemos(t,i); refreshBadges(); }catch(e){ toast(e.message); }
}

//  입찰 마감 변경 — 서버는 이 경로가 있는데 화면에 버튼이 없어, "마감을 늦춰 주세요"라는
//  오류 안내를 받고도 아무도 늦출 수 없었다. 형식은 서버가 검사한다(YYYY-MM-DD HH:MM).
async function auctionDeadline(aid, cur){
  const NL = String.fromCharCode(10);
  const v = prompt('입찰 마감 시각을 바꿉니다.' + NL +
    '형식: YYYY-MM-DD HH:MM (예: 2026-08-10 18:00)' + NL + NL +
    '· 마감을 앞당기면 아직 들어올 수 있었던 더 낮은 입찰이 잘립니다.',
    String(cur || '').slice(0, 16));
  if(v === null) return;
  const s = v.trim();
  if(!s){ toast('마감 시각을 적어 주세요.'); return; }
  try{
    await api('POST','/api/auctions/'+aid+'/deadline',{deadline: s.length===16 ? s+':00' : s});
    toast('입찰 마감을 <b>'+esc(s)+'</b>(으)로 바꿨습니다.');
    closeModal(); VIEWS.cases();
  }catch(e){ toast(e.message); closeModal(); VIEWS.cases(); }
}

// ── 운영 도구 (사건 상세) ──────────────────────────────────────
async function coordsSave(id){
  const lat = ($('#e_lat')||{}).value, lng = ($('#e_lng')||{}).value;
  if(!lat || !lng){ toast('위도·경도를 모두 입력해 주세요.'); return; }
  try{
    await api('POST',`/api/cases/${id}/coords`,{lat:Number(lat),lng:Number(lng)});
    toast('좌표를 저장했습니다 — 지도에 정밀 위치로 표시됩니다.');
  }catch(e){ toast(e.message); }
}
async function coordsClear(id){
  try{ await api('POST',`/api/cases/${id}/coords`,{clear:true}); toast('좌표를 해제했습니다.'); caseDetail(id); }
  catch(e){ toast(e.message); }
}
async function caseGate(id){
  // 도급 판정 — 이 건을 우리가 도급받아도 되는가(경미한 건설공사 관문)
  const box = $('#gate-result'); if(box) box.innerHTML = '<div class="hint">판정 중…</div>';
  try{
    const r = await api('GET',`/api/cases/${id}/contract-gate`);
    const gt = r.gate||{};
    if(box) box.innerHTML = `<div style="margin-top:8px;padding:12px 14px;border-radius:10px;font-size:.82rem;
        background:${gt.ok?'#E6F4EA':'#FBEAE7'};border:1px solid ${gt.ok?'#C4E4CF':'#F1C9C1'}">
      <b>${gt.ok?'✅ 도급 가능':'⛔ '+esc(gt.code||'차단')}</b> — ${esc(gt.reason||'')}
      ${gt.fallback?`<div style="margin-top:4px">대안: <b>${esc(gt.fallback)}</b></div>`:''}
      ${(gt.related_cases||[]).length?`<div class="hint" style="margin-top:4px">합산 대상: ${gt.related_cases.map(x=>esc(x.case_no)).join(', ')}</div>`:''}
    </div>`;
  }catch(e){ if(box) box.innerHTML = `<div class="hint" style="color:var(--red)">${esc(e.message)}</div>`; }
}
async function trackLink(id){
  if(!confirm('피해자 조회 링크를 발급할까요? (재발급하면 이전 링크는 즉시 무효가 됩니다)')) return;
  let r;
  try{ r = await api('POST',`/api/cases/${id}/track-link`,{}); }
  catch(e){ toast(e.message); return; }
  const url = r.full_url || (location.origin + r.url);
  //  발급 결과를 **정직하게** 보여 준다 — 무엇이 어디로 갔고 안 갔는지.
  //  예전에는 주소 하나만 prompt 로 띄워, 운영자는 안내가 나간 줄 알았다.
  const sent = r.has_phone
    ? (r.sms_live
        ? `<b style="color:var(--ok)">${esc(r.victim_name||'피해자')}님께 ${esc(r.channel||'문자')} 발송이 예약</b>되었습니다.`
        : `${esc(r.victim_name||'피해자')}님 앞으로 <b>발송대기함에 적재</b>되었습니다.
           <span style="color:var(--amber-text)">문자 연동이 아직 켜지지 않아 실제로는 나가지 않습니다</span>
           — 발송대기함에서 확인해 주세요.`)
    : `<b style="color:var(--amber-text)">피해자 연락처가 없어 안내를 보내지 못했습니다.</b>
       사건 수정에서 연락처를 넣으면 다시 발급할 때 함께 나갑니다.`;
  openModal(`<h3>피해자 조회 링크</h3>
    <div class="hint" style="line-height:1.8">${sent}</div>
    <div class="field"><label>조회 주소 <small style="color:var(--faint)">— 직접 전달하실 때 쓰세요</small></label>
      <input id="tk_url" value="${esc(url)}" readonly data-act="selectText"></div>
    <div class="hint" style="margin-top:6px">피해자에게는 <b>진행 단계·업체명·예상 완료일</b>만 보이고,
      <b>금액과 상세 주소는 보이지 않습니다.</b> 아래에서 실제 화면을 확인하실 수 있습니다.</div>
    <iframe src="${esc(r.url)}" title="피해자 조회 화면 미리보기"
      style="width:100%;height:420px;border:1px solid var(--line);border-radius:11px;margin-top:8px;background:#fff"></iframe>
    <div class="modal-foot">
      <button class="btn g" data-act="copyTrack">주소 복사</button>
      <span style="flex:1"></span>
      <button class="btn g" data-act="closeModal">닫기</button>
    </div>`);
}

async function saveCaseEdit(id){
  //  ⚠⚠ [라운드464] 이 폼은 늘 전체 스냅샷을 보냈다 — 서버(api_case_edit)는
  //    보낸 값이 DB 현재값과 다르면 무조건 "바뀐 것"으로 보고 되돌린다.
  //    그래서 관리자1이 지역만 고쳐 저장한 직후 관리자2가 공종만 고쳐
  //    저장하면, 관리자2 폼에 남은 옛 지역값이 관리자1의 변경을 조용히
  //    되돌렸다(실측: 동시성 재현 스크립트, lost update). 이 폼이 실제로
  //    만진 필드만 보내면 "안 만진 필드가 남의 변경을 덮어쓰는" 사고는
  //    막힌다(같은 필드를 진짜 동시에 고치는 충돌은 별개 — 그건 낙관적
  //    잠금이 필요한 제품판단 대상으로 남겨 둔다). 원래값은 폼을 채울 때
  //    브라우저가 그대로 들고 있는 defaultValue/defaultSelected로 안다 —
  //    새 상태를 따로 안 둬도 된다.
  const orig = el => el.tagName==='SELECT'
    ? (Array.from(el.options).find(o=>o.defaultSelected)||{}).value||''
    : (el.defaultValue||'');
  const body = {};
  const catEl=$('#e_cat'), regEl=$('#e_region'), addrEl=$('#e_addr'), mgrEl=$('#e_mgr'),
        warrEl=$('#e_warr'), urgEl=$('#e_urgent'), vnEl=$('#e_vname'), vpEl=$('#e_vphone');
  if(catEl && catEl.value.trim()!==orig(catEl).trim()) body.category=catEl.value.trim();
  if(regEl && regEl.value.trim()!==orig(regEl).trim()) body.region=regEl.value.trim();
  if(addrEl && addrEl.value.trim()!==orig(addrEl).trim()) body.address=addrEl.value.trim();
  if(mgrEl && mgrEl.value.trim()!==orig(mgrEl).trim()) body.manager=mgrEl.value.trim();
  if(warrEl && warrEl.value!==orig(warrEl)) body.warranty_months=warrEl.value;
  if(urgEl && (urgEl.value==='1')!==(orig(urgEl)==='1')) body.urgent=urgEl.value==='1';
  if(vnEl && vnEl.value.trim()!==orig(vnEl).trim()) body.victim_name=vnEl.value.trim();
  if(vpEl && vpEl.value.trim()!==orig(vpEl).trim()) body.victim_phone=vpEl.value.trim();
  const est=$('#e_est');
  if(est && !est.disabled && digits(est.value)!==digits(est.defaultValue)) body.est_price = moneyVal('#e_est');
  if(!Object.keys(body).length){ toast('변경사항이 없습니다.'); return; }
  try{
    const r = await api('PATCH','/api/cases/'+id, body);
    toast(r.unchanged?'변경사항이 없습니다.':('수정했습니다'+(r.changed&&r.changed.length?' — '+r.changed.join(', '):'')));
    closeModal(); VIEWS.cases();
  }catch(e){ toast(e.message); closeModal(); VIEWS.cases(); }
}

// ── 발주처(보험사) 관리 ──
//   계약 요율은 정산 금액을 직접 정하는 값이다. 서버 셸이 아니라 화면에서 다루고,
//   변경은 감사로그에 전/후가 남는다(서버가 기록).
VIEWS.insurers = async () => {
  //  ⚠⚠ [라운드253] applyRoleMenus() 는 사이드바 메뉴 항목만 숨긴다(등급3
  //    미만이면 display:none) — loadView() 자체엔 등급 검사가 없어, 메뉴가
  //    아닌 다른 경로로 'insurers' 를 부르면 그대로 실행됐다. 실제로 그런
  //    경로가 있었다: VIEWS.newcase(등급 무관, 하위관리자도 접수 보조로
  //    씀)가 발주처 0곳일 때 보여주는 "발주처 등록하러 가기→" 버튼이 바로
  //    이 화면을 연다. GET /api/insurers?all=1 은 require_admin(등급무관)
  //    이라 서버도 못 막아, 전 발주처의 담당자·부서·연락처·포털계정 보유
  //    여부·계약상태가 하위관리자에게도 그대로 노출됐다. 형제(VIEWS.admins,
  //    2733행)와 같은 방식으로 화면 스스로 막는다.
  if(myRank() < 3){ $('#content').innerHTML = '<div class="panel"><p class="empty">최고관리자만 접근할 수 있습니다.</p></div>'; return; }
  const qs = searchQS('insurers');
  const data = await api('GET','/api/insurers?all=1'+(qs.toString()?'&'+qs:''));
  window._insurers = data;
  //  ⚠⚠ [라운드637] 이 요약 카드 넷은 data(all=1, 전 상태) 를 그대로 세어 데모
  //    발주처까지 "등록 발주처"·"평균 계약 요율"에 합산했다 — round624~626이
  //    이미 이 화면(정확히 이 API)의 is_demo 배선을 다듬으며 실측한 값 그대로
  //    (운영DB 재확인: 활성 7곳 중 6곳이 is_demo=1), "평균 계약 요율"이 실제
  //    계약 1곳이 아니라 데모 6곳까지 섞인 값으로 뜬다. 아래 표(행마다 '데모'
  //    회색 표)는 이미 구분해 보여주는데 맨 위 요약 숫자만 못 걸렀다 — 이
  //    코드베이스 전체가 지키는 "데모는 실적 집계에서 뺀다"는 원칙을 이 네
  //    카드에도 그대로 적용한다(목록·행별 표시는 그대로 전체를 보여준다).
  const real = data.filter(i=>!i.is_demo);
  const act = real.filter(i=>i.status==='활성');
  $('#content').innerHTML = `
    <div class="krow k4">
      <div class="kc"><div class="k">등록 발주처</div><div class="v">${real.length}<small>곳</small></div><div class="d">활성 ${act.length}곳</div></div>
      <div class="kc"><div class="k">계약 체결</div><div class="v">${real.filter(i=>i.contract_status==='계약중').length}<small>곳</small></div><div class="d">위수탁 계약 완료</div></div>
      <div class="kc"><div class="k">포털 계정</div><div class="v">${real.filter(i=>i.login_id).length}<small>곳</small></div><div class="d">보험사 포털 접속 가능</div></div>
      <div class="kc hero"><div class="k">평균 계약 요율</div><div class="v">${act.length?(act.reduce((a,i)=>a+bpPct(i.fee_rate_bp),0)/act.length).toFixed(1):'—'}<small>%</small></div><div class="d">활성 발주처 기준(데모 제외)</div></div>
    </div>
    <div class="panel">
      <div class="ph"><span class="pt">발주처 목록 <small>보험사 · 공제조합 — 요율은 사건 등록 시점의 계약값이 정산에 적용됩니다</small></span>
        <button class="btn p sm" data-act="insurerForm">+ 발주처 등록</button></div>
      ${searchBar('insurers',{ph:'기관명·담당자·부서·연락처'})}
      <div class="tbl-wrap"><table class="tbl">
        <tr><th>기관명</th><th>구분</th><th>담당</th><th>연락처</th><th class="r">수수료율</th><th>계약</th><th>상태</th><th class="r">사건</th><th class="r">관리</th></tr>
        ${data.length?data.map(i=>`<tr data-act="insurerForm" data-arg="${i.id}" style="cursor:pointer">
          <td class="em">${esc(i.name)}${i.login_id?' <span class="pill blue" title="포털 계정 있음">포털</span>':''}${i.is_demo?' <span class="pill gray" title="시연용 예시 데이터 — 실제 계약 관계가 아닙니다">데모</span>':''}</td>
          <td>${esc(i.org_type||'-')}</td>
          <td>${esc(i.manager||'-')}${i.dept?`<br><small style="color:var(--faint)">${esc(i.dept)}</small>`:''}</td>
          <td class="tel">${esc(i.phone||'-')}</td>
          <td class="r em">${bpPct(i.fee_rate_bp).toFixed(1).replace('.0','')}%</td>
          <td>${statusPill(i.contract_status||'검토중')}</td>
          <td>${statusPill(i.status)}</td>
          <td class="r">${i.case_count||0}건</td>
          <td class="r"><button class="btn g sm" data-act="insurerForm" data-arg="${i.id}">수정</button></td></tr>`).join('')
        :'<tr><td colspan="9" class="empty">등록된 발주처가 없습니다</td></tr>'}
      </table></div>
      <p style="font-size:.66rem;color:var(--faint);margin-top:10px">※ 요율 변경은 <b>이후 새로 만들어지는 정산</b>부터 적용됩니다. 이미 생성된 정산 행은 생성 시점 요율로 확정되어 소급되지 않습니다.</p>
    </div>`;
};

function insurerForm(id){
  const i = id ? (window._insurers||[]).find(x=>x.id===id) : {};
  openModal(`<h3>${id?'발주처 정보 수정':'발주처 등록'}</h3>
    <div class="msub">${id?esc(i.name)+' — 요율 변경은 감사로그에 전/후가 기록됩니다':'보험사 · 공제조합을 등록합니다'}</div>
    <div class="grid2">
      <div class="field"><label>기관명 *</label><input id="i_name" value="${esc(i.name||'')}" ${id?'readonly style="background:var(--mist)"':''}></div>
      <div class="field"><label>구분</label><select id="i_type">${['손해보험','공제조합','기타'].map(t=>`<option ${i.org_type===t?'selected':''}>${t}</option>`).join('')}</select></div>
    </div>
    <div class="grid2">
      <div class="field"><label>담당자</label><input id="i_mgr" value="${esc(i.manager||'')}"></div>
      <div class="field"><label>부서</label><input id="i_dept" value="${esc(i.dept||'')}"></div>
    </div>
    <div class="grid2">
      <div class="field"><label>연락처</label><input id="i_phone" value="${esc(i.phone||'')}"></div>
      <div class="field"><label>이메일</label><input id="i_email" value="${esc(i.email||'')}"></div>
    </div>
    <div class="grid2">
      <div class="field"><label>수수료율(%) — 정산에 직접 적용<br>
              <small style="font-weight:400;color:var(--faint)">⚠ 이미 만들어진 정산에는 소급되지 않지만,
              <b>아직 정산 전인 진행 사건에는 바뀐 값이 적용</b>됩니다(협력사가 투찰 때 본 금액과 달라질 수 있습니다).</small></label><input id="i_fee" type="number" step="0.1" min="0" max="100" value="${(i.fee_rate_bp!==null&&i.fee_rate_bp!==undefined)?bpPct(i.fee_rate_bp):(id?10:'')}" placeholder="예: 10 또는 9.5"></div>
      <div class="field"><label>계약 상태</label><select id="i_ct">${['검토중','협의중','시범운영','계약중'].map(t=>`<option ${i.contract_status===t?'selected':''}>${t}</option>`).join('')}</select></div>
    </div>
    ${id?`<div class="field"><label>상태</label><select id="i_st">${['활성','중지'].map(t=>`<option ${i.status===t?'selected':''}>${t}</option>`).join('')}</select></div>`:''}
    ${id?`
    <div style="background:var(--mist);border-radius:12px;padding:12px 14px;margin-top:6px">
      <div style="font-size:.82rem;font-weight:800;margin-bottom:7px">포털 계정 · 전산 연동</div>
      <div style="font-size:.76rem;color:var(--sub);line-height:1.6;margin-bottom:9px">
        포털 로그인 아이디: <b>${i.login_id?esc(i.login_id):'미발급'}</b>
        ${i.login_id?'':' — 발급해야 발주처가 포털에 들어올 수 있습니다'}
      </div>
      <div style="display:flex;gap:7px;flex-wrap:wrap">
        <button class="btn ${i.login_id?'g':'p'} sm" data-act="insCred" data-arg="${id}"
                data-arg2="${i.login_id?'재발급':'발급'}">
          ${i.login_id?'비밀번호 재발급':'포털 계정 발급'}</button>
        <button class="btn g sm" data-act="insApi" data-arg="${id}">API·웹훅 연동</button>
      </div>
    </div>`:''}
    <div class="modal-foot">
      <button class="btn p" data-act="saveInsurer" data-arg="${id||0}">${id?'저장':'등록'}</button>
      <span style="flex:1"></span>
      <button class="btn g" data-act="closeModal">취소</button>
    </div>`);
}

// 발주처 포털 계정 발급 / 재발급
//  임시 비밀번호는 응답에 한 번만 온다 — 화면에서 복사할 수 있게 크게 보여 준다.
async function insCred(id, mode){
  const i = (window._insurers||[]).find(x=>x.id===id) || {};
  let login_id = i.login_id;
  if(!login_id){
    login_id = (prompt('발주처가 쓸 포털 아이디를 정해 주세요.\n(영문 소문자·숫자·-·_ 4~20자)')||'').trim();
    if(!login_id) return;
  }else if(!confirm(`${i.name} 의 포털 비밀번호를 재발급합니다.\n기존 비밀번호는 즉시 사용할 수 없게 됩니다. 진행할까요?`)){
    return;
  }
  let r;
  try{ r = await api('POST', `/api/insurers/${id}/credentials`, {login_id}); }
  catch(e){ toast(e.message || '발급하지 못했습니다'); return; }
  openModal(`<h3>${r.reissued?'비밀번호 재발급 완료':'포털 계정 발급 완료'}</h3>
    <div class="msub">${esc(i.name||'')} — 아래 정보는 <b>지금 한 번만</b> 표시됩니다.</div>
    <div style="background:var(--mist);border-radius:12px;padding:16px 18px;margin:10px 0">
      <div class="kv"><span class="k">로그인 주소</span><span class="v">${esc(location.origin)}/insurer</span></div>
      <div class="kv"><span class="k">아이디</span><span class="v" style="font-size:1rem">${esc(r.login_id)}</span></div>
      <div class="kv"><span class="k">임시 비밀번호</span>
        <span class="v" style="font-size:1.15rem;letter-spacing:.04em;font-family:ui-monospace,monospace">${esc(r.temp_password)}</span></div>
    </div>
    <div class="hint">최초 로그인 시 비밀번호 변경이 강제됩니다. 안전한 경로로 전달하세요.</div>
    <div class="modal-foot">
      <button class="btn p" data-act="copyText" data-arg="${esc(location.origin)}/insurer ${esc(r.login_id)} / ${esc(r.temp_password)}">복사</button>
      <span style="flex:1"></span>
      <button class="btn g" data-act="closeModal">닫기</button>
    </div>`);
  loadView('insurers');
}

// 발주처 전산 연동 — API 키·웹훅.
//  라우트는 진작 있었는데 **화면 진입점이 없어** 콘솔에서 켤 수가 없었다.
async function insApi(id){
  const i = (window._insurers||[]).find(x=>x.id===id) || {};
  let d;
  try{ d = await api('GET', `/api/insurers/${id}/api`); }
  catch(e){ toast(e.message); return; }
  const f = d.info || {};
  const st = s => ({성공:'green', 실패:'red', 포기:'red', 대기:'gray'})[s] || 'gray';
  openModal(`<h3>전산 연동 · ${esc(i.name||'')}</h3>
    <div class="msub">보험사 전산이 우리 API 로 사건을 접수하고 상태를 받아갑니다.</div>
    <div class="kv"><span class="k">API 키</span><span class="v">
      ${f.has_key?`${esc(f.api_key_prefix)}··· <span class="pill gray">${esc((f.api_key_created||'').slice(0,10))} 발급</span>`:'미발급'}</span></div>
    <div class="kv"><span class="k">연동 상태</span><span class="v">
      <span class="pill ${f.api_enabled?'green':'gray'}">${f.api_enabled?'사용 중':'꺼짐'}</span></span></div>
    <div class="kv"><span class="k">접수 주소</span><span class="v" style="font-size:.76rem">${esc(d.base_url||'')}/api/v1/cases</span></div>
    <div class="field" style="margin-top:12px">
      <label>상태 통지(webhook) 주소 — https 만</label>
      <input id="wh_url" value="${esc(f.webhook_url||'')}" placeholder="https://보험사도메인/bokguon/webhook">
    </div>
    <div style="display:flex;gap:7px;flex-wrap:wrap;margin-bottom:12px">
      <button class="btn p sm" data-act="insApiKey" data-arg="${id}">${f.has_key?'키 재발급':'키 발급'}</button>
      ${f.has_key?`<button class="btn danger sm" data-act="insApiRevoke" data-arg="${id}">키 폐기</button>`:''}
      <button class="btn g sm" data-act="insApiToggle" data-arg="${id}" data-arg2="${f.api_enabled?0:1}">
        ${f.api_enabled?'연동 끄기':'연동 켜기'}</button>
      <button class="btn g sm" data-act="insWhSave" data-arg="${id}">주소 저장</button>
      <button class="btn g sm" data-act="insWhTest" data-arg="${id}">테스트 발송</button>
    </div>
    <div class="ph"><span class="pt" style="font-size:.82rem">최근 통지 20건</span></div>
    <div class="tbl-wrap" style="max-height:230px"><table class="tbl">
      <tr><th>이벤트</th><th>사건</th><th>결과</th><th>시각</th></tr>
      ${(d.deliveries||[]).length ? d.deliveries.map(x=>`<tr>
        <td>${esc(x.event||'')}</td><td>${esc(x.case_no||'')}</td>
        <td><span class="pill ${st(x.status)}">${esc(x.status||'')}</span>
          ${x.http_code?` ${x.http_code}`:''}${x.error?`<div style="font-size:.68rem;color:var(--red)">${esc(String(x.error).slice(0,50))}</div>`:''}</td>
        <td style="font-size:.72rem">${esc((x.created_at||'').slice(5,16))}</td></tr>`).join('')
        : '<tr><td colspan="4" class="empty">아직 통지 기록이 없습니다</td></tr>'}
    </table></div>
    <div class="modal-foot"><span style="flex:1"></span>
      <button class="btn g" data-act="closeModal">닫기</button></div>`);
}

//  ⚠⚠ [라운드253] 형제(demoteConfirm, 1667행)는 partners 전용 필드명
//    (active_cases·unpaid_count·open_defects)을 그대로 쓴다 — 보험사는
//    _insurer_demote_gate 가 다른 모양(pending_settlements·pending_agreements)
//    으로 응답해 그대로 재사용할 수 없다. 같은 목적의 보험사 전용 버전.
async function insurerDemoteConfirm(err, status){
  const info = err && err.data;
  if(!info || info.code !== 'INSURER_HAS_WORK') return false;
  const slist = (info.pending_settlements||[]).slice(0,6)
    .map(s=>`· ${s.case_no}`).join('\n');
  const alist = (info.pending_agreements||[]).slice(0,6)
    .map(a=>`· ${a.case_no} (${a.status})`).join('\n');
  return confirm(
    `이 보험사는 아직 일이 걸려 있습니다.\n\n`
    + (info.pending_settlement_count?`완료 승인 대기 정산: ${info.pending_settlement_count}건\n`:'')
    + (info.pending_agreement_count?`1차합의 검토중: ${info.pending_agreement_count}건\n`:'')
    + `\n${[slist, alist].filter(Boolean).join('\n')}\n\n`
    + `'중지'하면 이 보험사는 로그인할 수 없어 위 승인들을 영원히 못 넘기게 됩니다`
    + `(관리자가 대신 승인할 방법이 없습니다).\n\n그래도 '${status}'(으)로 변경하시겠습니까?`);
}
async function saveInsurer(id){
  const body = {
    org_type:$('#i_type').value, manager:$('#i_mgr').value.trim(), dept:$('#i_dept').value.trim(),
    phone:$('#i_phone').value.trim(), email:$('#i_email').value.trim(),
    fee_rate_pct:$('#i_fee').value.trim(), contract_status:$('#i_ct').value
  };
  try{
    if(id){
      if($('#i_st')) body.status = $('#i_st').value;
      const r = await api('PATCH','/api/insurers/'+id, body);
      toast((r.changed&&r.changed.length)?('저장했습니다 — '+r.changed.join(', ')):'저장했습니다.');
    }else{
      body.name = $('#i_name').value.trim();
      if(!body.name){ toast('기관명을 입력해 주세요.'); return; }
      await api('POST','/api/insurers', body);
      toast('발주처를 등록했습니다.');
    }
    closeModal(); VIEWS.insurers();
  }catch(e){
    //  ⚠⚠ [라운드253] insurerForm() 에 상태 <select>(i_st)만 있고 사유 입력·
    //    강등확인 재요청 배선이 전혀 없었다 — 형제(savePartner, 1620행)가 이미
    //    구현한 NEED_REASON→prompt→재요청, INSURER_HAS_WORK→confirm→
    //    confirm_demote 재요청까지 그대로 옮긴다. 이게 없으면 최고관리자가
    //    발주처 상태를 활성↔중지로 바꾸는 기능이 콘솔에서 사실상 동작 불능이었다
    //    (토스트 에러만 뜨고 모달이 그대로 남는다 — 입력할 곳이 없어서).
    if(e && e.data && e.data.code === 'NEED_REASON'){
      const reason = askStatusReason(body.status);
      if(reason === null) return;
      try{
        await api('PATCH','/api/insurers/'+id, {...body, status_reason:reason});
        closeModal(); toast('발주처 상태를 변경하고 통지했습니다'); VIEWS.insurers();
      }catch(e2){
        if(await insurerDemoteConfirm(e2, body.status)){
          try{
            await api('PATCH','/api/insurers/'+id,
                      {...body, status_reason:reason, confirm_demote:true});
            closeModal(); toast('발주처 상태를 변경했습니다'); VIEWS.insurers();
          }catch(e3){ toast(e3.message); }
          return;
        }
        toast(e2.message);
      }
      return;
    }
    if(await insurerDemoteConfirm(e, body.status)){
      const reason = askStatusReason(body.status);
      if(reason === null) return;
      try{
        await api('PATCH','/api/insurers/'+id,
                  {...body, status_reason:reason, confirm_demote:true});
        closeModal(); toast('발주처 상태를 변경했습니다'); VIEWS.insurers();
      }catch(e2){ toast(e2.message); }
      return;
    }
    toast(e.message);
  }
}

// ── 관리자 계정 (최고관리자 전용) ──
//   대표 혼자가 아니라 담당자들이 직접 들어와 일한다. 등급으로 권한을 나눈다.
VIEWS.admins = async () => {
  if(myRank() < 3){ $('#content').innerHTML = '<div class="panel"><p class="empty">최고관리자만 접근할 수 있습니다.</p></div>'; return; }
  const qs = searchQS('admins');
  const data = await api('GET','/api/admins'+(qs.toString()?'?'+qs:''));
  window._admins = data;
  const badge = r => r==='최고관리자'?'<span class="pill green">최고관리자</span>'
    : r==='중간관리자'?'<span class="pill blue">중간관리자</span>':'<span class="pill gray">하위관리자</span>';
  $('#content').innerHTML = `
    <div class="panel">
      <div style="background:#F3F8FE;border:1px solid #CFE3F7;border-radius:12px;padding:12px 15px;font-size:.74rem;color:#134E86;margin-bottom:14px">
        👤 <b>등급별 권한</b> — 최고관리자: 전권(계정·계좌·요율·정산이체) · 중간관리자: 일상 운영(사건·검수·정산·하자) · 하위관리자: 조회·접수 보조
      </div>
      <div class="ph"><span class="pt">관리자 계정 <small>${data.length}명</small></span>
        <button class="btn p sm" data-act="adminForm">+ 관리자 추가</button></div>
      ${searchBar('admins',{ph:'아이디·이름·등급'})}
      <div class="tbl-wrap"><table class="tbl">
        <tr><th>아이디</th><th>이름</th><th>등급</th><th>비밀번호</th><th>등록일</th><th class="r">관리</th></tr>
        ${data.map(a=>`<tr>
          <td class="em">${esc(a.username)}${a.username===ME.username?' <span class="pill amber">나</span>':''}</td>
          <td>${esc(a.name||'-')}</td><td>${badge(a.role)}</td>
          <td>${a.must_change_pw?'<span class="pill amber">변경 대기</span>':'<span class="pill gray">설정됨</span>'}</td>
          <td>${esc((a.created_at||'').slice(0,10))}</td>
          <td class="r"><button class="btn g sm" data-act="adminForm" data-arg="${a.id}">수정</button></td></tr>`).join('')}
      </table></div>
    </div>`;
};

function adminForm(id){
  const a = id ? (window._admins||[]).find(x=>x.id===id) : {role:'하위관리자'};
  const isNew = !id;
  const isMe = a.username===ME.username;
  openModal(`<h3>${isNew?'관리자 추가':'관리자 정보 수정'}</h3>
    <div class="msub">${isNew?'담당자 계정을 만들고 등급을 정합니다':esc(a.username)+(isMe?' — 본인 계정':'')}</div>
    ${isNew?`<div class="grid2">
      <div class="field"><label>아이디 * <small style="color:var(--faint)">(영문 소문자·숫자 4~20자)</small></label><input id="ad_user" placeholder="예: kim2026" autocomplete="off"></div>
      <div class="field"><label>이름 *</label><input id="ad_name"></div>
    </div>`:`<div class="field"><label>이름</label><input id="ad_name" value="${esc(a.name||'')}"></div>`}
    <div class="field"><label>등급</label>
      <select id="ad_role">${['최고관리자','중간관리자','하위관리자'].map(r=>`<option ${a.role===r?'selected':''}>${r}</option>`).join('')}</select>
      <div style="font-size:.66rem;color:var(--faint);margin-top:4px">최고관리자=전권 · 중간관리자=일상운영 · 하위관리자=조회·접수</div>
    </div>
    <div id="ad_cred"></div>
    <div class="modal-foot">
      <button class="btn p" data-act="saveAdmin" data-arg="${id||0}">${isNew?'생성':'저장'}</button>
      ${(!isNew && !isMe)?`<button class="btn g sm" data-act="resetAdminPw" data-arg="${id}">비밀번호 재발급</button>
        <button class="btn danger sm" data-act="deleteAdmin" data-arg="${id}">삭제</button>`:''}
      <span style="flex:1"></span>
      <button class="btn g" data-act="closeModal">취소</button>
    </div>`);
}

function _showTempPw(where, username, pw, label){
  const box = $(where); if(!box) return;
  box.innerHTML = `<div style="background:var(--mist);border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin-top:10px">
    <div style="font-weight:700;margin-bottom:4px">${label||'발급 완료'}</div>
    <div class="kv"><span class="k">아이디</span><span class="v em">${esc(username)}</span></div>
    <div class="kv"><span class="k">임시 비밀번호</span><span class="v em" style="font-family:monospace;font-size:.9rem;user-select:all">${esc(pw)}</span></div>
    <div style="font-size:.66rem;color:var(--red);margin-top:6px">⚠ 지금 한 번만 표시됩니다. 본인에게 전달하세요. 최초 로그인 시 변경이 강제됩니다.</div>
  </div>`;
}

async function saveAdmin(id){
  try{
    if(!id){
      const body = {username:$('#ad_user').value.trim(), name:$('#ad_name').value.trim(), role:$('#ad_role').value};
      if(!body.username || !body.name){ toast('아이디와 이름을 입력해 주세요.'); return; }
      const r = await api('POST','/api/admins', body);
      _showTempPw('#ad_cred', r.username, r.temp_password, '관리자 계정 생성 완료');
      toast('관리자를 추가했습니다.'); if(window._admins) VIEWS.admins();
    }else{
      const r = await api('PATCH','/api/admins/'+id, {name:$('#ad_name').value.trim(), role:$('#ad_role').value});
      toast('저장했습니다.'); closeModal(); VIEWS.admins();
    }
  }catch(e){ toast(e.message); }
}
async function resetAdminPw(id){
  if(!confirm('비밀번호를 재발급하시겠습니까? 기존 비밀번호는 즉시 무효화됩니다.')) return;
  try{
    const r = await api('PATCH','/api/admins/'+id, {reset_pw:true});
    const a = (window._admins||[]).find(x=>x.id===id)||{};
    _showTempPw('#ad_cred', a.username, r.temp_password, '비밀번호 재발급 완료');
  }catch(e){ toast(e.message); }
}
async function deleteAdmin(id){
  const a = (window._admins||[]).find(x=>x.id===id)||{};
  if(!confirm(`관리자 '${a.username}' 계정을 삭제하시겠습니까?`)) return;
  try{ await api('DELETE','/api/admins/'+id); toast('삭제했습니다.'); closeModal(); VIEWS.admins(); }
  catch(e){ toast(e.message); }
}

// ── 내 계정 (좌하단 이름 클릭) ──
async function myAccount(){
  let me, otp={};
  try{ me = await api('GET','/api/me'); }catch(e){ return; }
  try{ otp = await api('GET','/api/me/otp'); }catch(e){ otp={}; }
  openModal(`<h3>내 계정</h3><div class="msub">${esc(me.username||'')} · ${esc(me.role||'')}</div>
    <div class="field"><label>이름</label><input id="my_name" value="${esc(me.name||'')}"></div>
    <button class="btn p sm" data-act="saveMyName">이름 저장</button>
    <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--line)">
      <div style="font-weight:700;margin-bottom:8px">비밀번호 변경</div>
      <div class="field"><label>현재 비밀번호</label><input id="my_cur" type="password" autocomplete="current-password"></div>
      <div class="grid2">
        <div class="field"><label>새 비밀번호</label><input id="my_new" type="password" autocomplete="new-password"></div>
        <div class="field"><label>새 비밀번호 확인</label><input id="my_new2" type="password" autocomplete="new-password"></div>
      </div>
      <button class="btn a sm" data-act="saveMyPw">비밀번호 변경</button>
    </div>
    <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--line)" id="otpBox">
      ${otpPanel(otp)}
    </div>
    <div class="modal-foot"><span style="flex:1"></span><button class="btn g" data-act="closeModal">닫기</button></div>`);
}

// ── 2단계 인증(외부 접속용 일회용 비밀번호) ──
//  [법령] 개인정보 안전성 확보조치 기준 §6④ — 외부 접속엔 안전한 인증수단이 필요하다.
function otpPanel(o){
  const need = o.required_for_external;
  if(o.enabled){
    return `<div style="font-weight:700;margin-bottom:8px">2단계 인증 <span class="pill green">사용 중</span></div>
      <div class="sub" style="font-size:.74rem;line-height:1.6">
        ${esc((o.since||'').slice(0,16))} 등록 · 남은 복구 코드 <b>${o.recovery_left||0}장</b><br>
        외부(사무실 밖)에서 로그인할 때 휴대폰 인증 앱의 6자리 코드가 필요합니다.
      </div>
      ${o.internal_now
        ? `<div class="field" style="margin-top:10px"><label>해제하려면 비밀번호 확인</label>
             <input id="otp_off_pw" type="password" autocomplete="current-password"></div>
           <button class="btn r sm" data-act="otpDisable">2단계 인증 해제</button>`
        : `<div class="sub" style="font-size:.72rem;margin-top:8px">해제·재등록은 사무실 PC에서만 가능합니다.</div>`}`;
  }
  return `<div style="font-weight:700;margin-bottom:8px">2단계 인증
      <span class="pill ${need?'red':'gray'}">${need?'미등록 — 외부 접속 불가':'꺼짐'}</span></div>
    <div class="sub" style="font-size:.74rem;line-height:1.6">
      ${need ? '외부(사무실 밖)에서 콘솔에 접속하려면 <b>법령상 일회용 비밀번호가 필요</b>합니다'
             + '(개인정보 안전성 확보조치 기준 제6조 제4항). 지금 등록해 두면 폰만 있으면 어디서든 들어올 수 있습니다.'
             : '지금은 정책상 필요하지 않습니다.'}
    </div>
    ${o.internal_now
      ? `<button class="btn p sm" style="margin-top:10px" data-act="otpSetup">2단계 인증 등록하기</button>`
      : `<div class="sub" style="font-size:.72rem;margin-top:8px">
           ⚠ 등록은 <b>사무실 PC(내부망)</b>에서만 가능합니다 — 계정을 탈취당해도 공격자가 자기 폰을 등록할 수 없게 한 장치입니다.
         </div>`}`;
}
async function otpSetup(){
  let d; try{ d = await api('POST','/api/me/otp/setup', {}); }catch(e){ toast(e.message, true); return; }
  const chunks = (d.secret||'').match(/.{1,4}/g)||[];
  openModal(`<h3>2단계 인증 등록</h3>
    <div class="msub">휴대폰 인증 앱으로 아래 QR을 찍은 뒤, 앱에 뜬 6자리 코드를 입력하세요.</div>
    <div style="display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start;margin:12px 0">
      <div style="background:#fff;padding:8px;border:1px solid var(--line);border-radius:10px;width:212px">
        ${d.qr_svg ? d.qr_svg.replace(/width="\d+" height="\d+"/, 'width="196" height="196"')
                   : '<div class="sub" style="padding:20px;font-size:.74rem">QR을 만들지 못했습니다. 아래 키를 직접 입력하세요.</div>'}
      </div>
      <div style="flex:1;min-width:220px">
        <div class="sub" style="font-size:.74rem;line-height:1.7">
          <b>앱이 없다면</b> 구글 OTP(Google Authenticator)·MS Authenticator 등 아무 인증 앱이나 됩니다.<br><br>
          <b>QR을 못 찍으면</b> 앱에서 "키 직접 입력"을 고르고 아래 키를 넣으세요.
        </div>
        <div style="margin-top:8px;padding:10px;background:var(--bg2,#F6F8FA);border-radius:8px;
                    font-family:ui-monospace,Consolas,monospace;font-size:.86rem;letter-spacing:.08em;word-break:break-all">
          ${esc(chunks.join(' '))}
        </div>
      </div>
    </div>
    <div class="field"><label>앱에 표시된 6자리 코드</label>
      <input id="otp_conf" inputmode="numeric" maxlength="6" placeholder="000000"
             style="letter-spacing:.25em;text-align:center;font-size:1.1rem"></div>
    <div class="modal-foot">
      <span style="flex:1"></span>
      <button class="btn g" data-act="closeModal">취소</button>
      <button class="btn p" data-act="otpConfirm">확인하고 켜기</button>
    </div>`);
}
async function otpConfirm(){
  const code = ($('#otp_conf')||{}).value || '';
  if(!/^\d{6}$/.test(code.trim())){ toast('6자리 숫자를 입력해 주세요.'); return; }
  let d; try{ d = await api('POST','/api/me/otp/confirm', {code:code.trim()}); }
  catch(e){ toast(e.message, true); return; }
  openModal(`<h3>2단계 인증이 켜졌습니다</h3>
    <div style="background:var(--amber-bg,#FDF6E9);border:1px solid #F5DCB2;border-radius:11px;
                padding:12px 15px;font-size:.78rem;color:#7A5410;line-height:1.6;margin-bottom:12px">
      ⚠ <b>복구 코드를 지금 저장하세요.</b> 이 화면을 닫으면 다시 볼 수 없습니다.<br>
      휴대폰을 잃어버렸을 때 이 코드로만 들어올 수 있습니다. 한 장당 1회만 쓸 수 있습니다.
    </div>
    <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;
                font-family:ui-monospace,Consolas,monospace;font-size:.92rem">
      ${(d.recovery_codes||[]).map(c=>`<div style="padding:8px 10px;background:var(--bg2,#F6F8FA);
        border-radius:8px;text-align:center;letter-spacing:.06em">${esc(c)}</div>`).join('')}
    </div>
    <div class="modal-foot">
      <span style="flex:1"></span>
      <button class="btn g" data-act="otpCopyCodes">복사</button>
      <button class="btn p" data-act="closeModal">저장했습니다</button>
    </div>`);
  window._otpCodes = d.recovery_codes || [];
}
async function otpDisable(){
  const pw = ($('#otp_off_pw')||{}).value || '';
  if(!pw){ toast('비밀번호를 입력해 주세요.'); return; }
  if(!confirm('2단계 인증을 해제하면 외부(사무실 밖)에서 접속할 수 없게 됩니다. 해제할까요?')) return;
  try{ await api('POST','/api/me/otp/disable', {password:pw}); toast('2단계 인증을 해제했습니다.'); closeModal(); }
  catch(e){ toast(e.message, true); }
}
async function saveMyName(){
  const name = $('#my_name').value.trim();
  if(!name){ toast('이름을 입력해 주세요.'); return; }
  try{ const r = await api('PATCH','/api/me', {name}); $('#me-name').textContent = r.name; $('#av').textContent=(r.name||'·').slice(0,1); toast('이름을 변경했습니다.'); }
  catch(e){ toast(e.message); }
}
async function saveMyPw(){
  const cur=$('#my_cur').value, nw=$('#my_new').value, nw2=$('#my_new2').value;
  if(!cur||!nw){ toast('현재·새 비밀번호를 입력해 주세요.'); return; }
  if(nw!==nw2){ toast('새 비밀번호가 서로 다릅니다.'); return; }
  try{ await api('POST','/api/change-password', {current:cur, new:nw}); toast('비밀번호를 변경했습니다.'); closeModal(); }
  catch(e){ toast(e.message); }
}

// ── 변경 견적·재경매 (실사 후 증액) ──
//   낙찰업체 실사요청 → 추가분경매 → 원업체제안 → (수락확정 | 거절→전체재경매 → 낙찰/유찰 → 최대 3라운드)
VIEWS.changeorders = async () => {
  const qs = searchQS('changeorders');
  const data = await api('GET','/api/change-orders'+(qs.toString()?'?'+qs:''));
  window._cos = data;
  const coPill = s => {
    const m={'실사요청':'amber','추가경매중':'blue','원업체제안':'amber','수락확정':'green',
      '거절':'red','전체재경매중':'blue','유찰':'red','낙찰확정':'green','최종유찰':'gray'};
    return `<span class="pill ${m[s]||'gray'}">${esc(s)}</span>`;
  };
  $('#content').innerHTML = `
    <div class="panel">
      <div style="background:#F3F8FE;border:1px solid #CFE3F7;border-radius:12px;padding:12px 15px;font-size:.74rem;color:#134E86;margin-bottom:14px">
        🔁 <b>변경 견적 흐름</b> — 낙찰업체가 실사 후 증액 요청 → <b>추가분 경매</b> 오픈 → 최저가를 원업체에 <b>합산 제시</b> →
        수락하면 확정 / 거절하면 추가 사진 붙여 <b>전체 재경매</b>(최대 3차)
      </div>
      <div class="ph"><span class="pt">진행 중 변경 건 <small>${data.length}건</small></span></div>
      ${searchBar('changeorders',{ph:'접수번호·업체·사유', categories:ALL_MAJORS})}
      <div class="tbl-wrap"><table class="tbl">
        <tr><th>접수번호</th><th>라운드</th><th>사유</th><th class="r">원 낙찰가</th><th class="r">추가 최저</th><th class="r">합산</th><th>상태</th><th class="r">처리</th></tr>
        ${data.length?data.map(co=>`<tr>
          <td class="em">${esc(co.case_no||('#'+co.case_id))}</td>
          <td class="r">${co.round}차</td>
          <td style="max-width:220px;white-space:normal">${esc((co.reason||'').slice(0,50))}</td>
          <td class="r">${won(co.incumbent_amount)}</td>
          <td class="r">${co.add_low?won(co.add_low):'-'}</td>
          <td class="r em">${co.combined_amount?won(co.combined_amount):'-'}</td>
          <td>${coPill(co.status)}</td>
          <td class="r">${coActions(co)}</td></tr>`).join('')
        :'<tr><td colspan="8" class="empty">진행 중 변경 건 없음</td></tr>'}
      </table></div>
    </div>`;
};
// 상태별로 관리자가 눌러야 할 버튼만 보여준다
function coActions(co){
  //  ⚠⚠ [라운드252] 이 함수가 내는 버튼 7개(coAddAuction·coWithdrawReq·coOffer·
  //    coFailAdd·coWithdraw·coFullReauction·coCloseFull) 전부 백엔드가
  //    require_role(중간관리자) 인데 등급 무관하게 그려졌다 — 형제(cmNew·boqForm,
  //    246·247·251라운드)처럼 자격 없으면 조용히 안내문으로 바꾼다. 목록 조회
  //    (GET /api/change-orders)는 require_admin(등급무관)이라 하위관리자도
  //    화면 자체는 정상적으로 보되, 처리는 여기서 막힌다.
  if(myRank()<2) return '<span class="sub">중간관리자 이상만 처리할 수 있습니다</span>';
  switch(co.status){
    //  ⚠ 종전에는 여기 버튼이 하나뿐이라, 자릿수 오타 하나를 정리하려고
    //    협력사 399곳에 **실제 추가분 공고**를 띄운 뒤 유찰까지 밟아야 했다.
    case '실사요청': return `<button class="btn p sm" data-act="coAddAuction" data-arg="${co.id}">추가분 경매 오픈</button>
      <button class="btn g sm" data-act="coWithdrawReq" data-arg="${co.id}">철회</button>`;
    case '추가경매중': return `<button class="btn a sm" data-act="coOffer" data-arg="${co.id}">마감→원업체 제시</button>
      <button class="btn g sm" data-act="coFailAdd" data-arg="${co.id}">추가분 유찰</button>`;
    //  ⚠ 여기에 버튼이 하나도 없어서, 원업체가 수락·거절을 안 누르면 **영영 멈췄다.**
    //    그동안 원 사건의 낙찰취소·재공고까지 함께 잠기고(CHANGE_ORDER_ACTIVE),
    //    협력사의 재요청도 409 로 막힌다. 서버에는 회수 경로가 이미 있었는데 입구가 없었다.
    case '원업체제안': return `<span class="sub">원업체 응답 대기</span>
      <button class="btn g sm" data-act="coWithdraw" data-arg="${co.id}"
        title="원업체 제안을 물리고 추가분 경매로 되돌립니다">제안 회수</button>`;
    case '거절': return `<button class="btn p sm" data-act="coFullReauction" data-arg="${co.id}">전체 재경매 오픈</button>`;
    case '전체재경매중': return `<button class="btn a sm" data-act="coCloseFull" data-arg="${co.id}">재경매 마감</button>`;
    case '유찰': return `<button class="btn p sm" data-act="coFullReauction" data-arg="${co.id}">다음 라운드</button>`;
    default: return '<span class="sub">-</span>';
  }
}
//  원업체가 응답하지 않을 때의 출구 — 제안을 물리고 추가분 경매로 되돌린다.
//  (수락·거절이 이미 눌렸으면 서버가 409 로 막는다. 그 뒤 절차가 이미 움직였기 때문)
async function coWithdraw(id){
  const reason = askOverride('원업체 제안을 회수합니다.',
    '추가분 경매가 다시 열리고, 원업체에 보낸 제안은 무효가 됩니다.',
    '회수 사유를 적어 주세요.');
  if(reason === null) return;
  try{
    const r = await api('POST','/api/change-orders/'+id+'/withdraw-offer',{reason});
    toast(r.message || '제안을 회수하고 추가분 경매로 되돌렸습니다.');
    VIEWS.changeorders();
  }catch(e){
    //  ⚠⚠ [라운드503] 형제(caseCancelAward 등, 라운드481·486·500·501)가
    //    이미 세운 원칙 — 성공 분기(바로 위)만 목록을 새로고침하면, 동시에
    //    다른 관리자가 먼저 처리해 이미 상태가 바뀐 변경건을 이 화면만
    //    계속 처리 가능한 것으로 보여준다. catch도 성공 분기와 같이 정리한다.
    toast(e.message); VIEWS.changeorders();
  }
}
async function coAddAuction(id){
  //  ⚠⚠ [라운드503] 형제(coWithdraw, 위 참조) 참조 — catch도 성공 분기와 같이 정리한다.
  try{ await api('POST','/api/change-orders/'+id+'/add-auction',{}); toast('추가분 경매를 열었습니다. 협력사 앱에 노출됩니다.'); VIEWS.changeorders(); }
  catch(e){ toast(e.message); VIEWS.changeorders(); }
}
async function coOffer(id){
  try{ const r=await api('POST','/api/change-orders/'+id+'/offer',{});
    toast(`추가 최저 ${won(r.add_low)}원 · 합산 ${won(r.combined)}원을 원업체에 제시했습니다.`); VIEWS.changeorders(); }
  catch(e){ toast(e.message); VIEWS.changeorders(); }
}
async function coFullReauction(id){
  try{ const r=await api('POST','/api/change-orders/'+id+'/full-reauction',{});
    toast(`전체 재경매 ${r.round}차를 열었습니다.`); VIEWS.changeorders(); }
  catch(e){ toast(e.message); VIEWS.changeorders(); }
}
async function coCloseFull(id){
  const co=(window._cos||[]).find(x=>x.id===id)||{};
  // 재경매 입찰 조회해서 낙찰/유찰 선택
  let bids=[];
  //  ⚠⚠ [라운드74] 조회가 실패해도 조용히 [] 로 넘어갔다 — 그러면 아래 화면이
  //    "입찰이 없습니다. 유찰 처리하세요"를 **진짜 0건인 것과 똑같이** 보여준다.
  //    마감이 지난 재경매에는 서버(api_co_close_full)의 실입찰 수 체크가 없다
  //    (마감 전 가드만 있다) — 실제로 입찰이 있는데 이 화면이 "0건"으로 잘못
  //    보여주면, 관리자가 유찰을 눌러 그 입찰들을 되돌릴 수 없이 지워 버린다.
  try{ bids = await api('GET','/api/change-orders/'+id+'/bids'); }
  catch(e){ toast(e.message); return; }
  const rows = bids.length?bids.map(b=>`<label style="display:flex;justify-content:space-between;padding:8px;border:1px solid var(--line);border-radius:8px;margin-bottom:6px;cursor:pointer">
      <span><input type="radio" name="cobid" value="${b.id}" style="margin-right:8px">${esc(b.partner_name)}</span>
      <b>${won(b.amount)}원 · ${b.days}일</b></label>`).join('')
    : '<p class="sub">입찰이 없습니다. 유찰 처리하세요.</p>';
  openModal(`<h3>전체 재경매 마감 · ${co.round}차</h3>
    <div class="msub">${esc(co.case_no||'')} · 낙찰할 업체를 고르거나 유찰 처리합니다</div>
    <div style="margin:12px 0">${rows}</div>
    ${bids.length?`<div class="field"><label>최저가가 아닌 업체 선택 시 사유
      <small style="color:var(--faint);font-weight:400">— 선정 근거로 기록됩니다</small></label>
      <input id="co_reason" placeholder="예: 공기 단축 필요 · 동일 현장 연속 시공"></div>
      ${/*  ⚠⚠ [라운드252] 서버(api_co_close_full)는 이 낙찰금액을 발주처가 사전에
             '확인' 하지 않았으면 insurer_instruction(5자 이상 유선지시 근거)이
             없는 한 409(INSURER_ACK_REQUIRED)로 거부한다 — 이 재경매는 원업체가
             거절한 옛 합산가를 상한으로 인하 입찰되므로 낙찰가가 그 옛 확인금액과
             거의 항상 달라 이 관문에 실제로 자주 걸린다. 그런데 이 칸이 화면에
             아예 없어서, 걸리면 콘솔로는 영원히 낙찰을 확정할 수 없었다(원시
             API 호출로 우회해야 했다). co_reason 과 같은 방식 — 평소엔 안 쓰여도
             막히면 여기 적어야 한다. */''}
      <div class="field"><label>발주처 확인 근거(유선 지시 등)
      <small style="color:var(--faint);font-weight:400">— 이 낙찰금액을 발주처가 사전에 확인하지 않았다면 필요합니다</small></label>
      <input id="co_instruction" placeholder="예: 08-20 14:00 김○○ 손해사정사 유선 승인"></div>`:''}
    <div class="modal-foot">
      ${bids.length?`<button class="btn p" data-act="coAwardFull" data-arg="${id}">선택 업체 낙찰</button>`:''}
      <button class="btn danger sm" data-act="coFailFull" data-arg="${id}">유찰 처리</button>
      <span style="flex:1"></span><button class="btn g" data-act="closeModal">취소</button>
    </div>`);
}
async function coAwardFull(id){
  const sel=document.querySelector('input[name=cobid]:checked');
  if(!sel){ toast('낙찰할 업체를 선택하세요.'); return; }
  const bidId = Number(sel.value);
  //  ⚠ 이 경로는 실사 후 **금액이 올라가는** 구간이다. 최저가가 아니면 서버가 사유를 요구한다.
  const reason = (document.getElementById('co_reason')?.value || '').trim();
  const instruction = (document.getElementById('co_instruction')?.value || '').trim();
  try{ const r=await api('POST','/api/change-orders/'+id+'/close-full',
                         {bid_id:bidId, reason, insurer_instruction:instruction});
    toast(`${esc(r.awarded)} 낙찰 (${won(r.amount)}원)`); closeModal(); VIEWS.changeorders(); }
  catch(e){
    //  아직 마감 전이면 서버가 되묻는다 — 지금 자르면 더 낮은 입찰을 잘라 버린다.
    if(e.code === 'NOT_CLOSED'){
      if(!confirm((e.message || '아직 마감 시각 전입니다.')
          + String.fromCharCode(10) + String.fromCharCode(10)
          + '지금 마감하면 아직 들어올 수 있었던 더 낮은 입찰이 잘립니다. 되돌릴 수 없습니다.'
          + String.fromCharCode(10) + '그래도 지금 마감하시겠습니까?')) return;
      try{ const r=await api('POST','/api/change-orders/'+id+'/close-full',
                             {bid_id:bidId, reason, insurer_instruction:instruction, force:true});
           //  ⚠ '되돌릴 수 없습니다' 라고 경고하고 누른 버튼인데, 결과가 일반 문구뿐이라
    //    누가 얼마에 낙찰됐는지 모른 채 모달이 닫혔다. 정상 마감 경로와 같은 말을 한다.
    toast(r.awarded ? `${esc(r.awarded)} 낙찰 (${won(r.amount)}원)`
                    : (r.message || '재경매를 마감했습니다.'));
    closeModal(); VIEWS.changeorders(); }
      //  ⚠⚠ [라운드503] 형제(coWithdraw 등) 참조 — catch도 성공 분기(바로 위)와
      //    같이 정리한다.
      catch(e2){ toast(e2.message); closeModal(); VIEWS.changeorders(); }
      return;
    }
    if(e.code === 'NOT_LOWEST'){
      toast(e.message);
      const el = document.getElementById('co_reason');
      if(el){ el.focus(); el.style.borderColor = 'var(--red)'; }
      return;
    }
    //  ⚠⚠ [라운드252] 이 칸이 아예 없어서 이 오류를 만나면 콘솔로는 영원히
    //    낙찰을 확정할 수 없었다(위 co_instruction 신설과 짝) — NOT_LOWEST 와
    //    같은 방식으로 어디를 채워야 하는지 바로 알려준다.
    if(e.code === 'INSURER_ACK_REQUIRED'){
      toast(e.message);
      const el = document.getElementById('co_instruction');
      if(el){ el.focus(); el.style.borderColor = 'var(--red)'; }
      return;
    }
    //  ⚠⚠ [라운드503] 형제(coWithdraw 등, 라운드481·486·500·501) 참조 — 이
    //    자리(알 수 없는 오류)도 catch가 성공 분기(맨 위)와 같이 정리한다.
    //    NOT_LOWEST·INSURER_ACK_REQUIRED 는 사용자가 입력 중이던 칸을 그대로
    //    두고 포커스만 옮기는 게 의도라 일부러 손대지 않는다.
    toast(e.message); closeModal(); VIEWS.changeorders();
  }
}
async function coFailFull(id){
  if(!confirm('이 라운드를 유찰 처리하시겠습니까?')) return;
  try{ const r=await api('POST','/api/change-orders/'+id+'/close-full',{failed:true});
    toast(r.message); closeModal(); VIEWS.changeorders(); }
  catch(e){
    //  ⚠ 마감 전 유찰도 **아직 투찰할 수 있던 업체를 통째로 배제**한다.
    //    낙찰 경로에만 되묻기가 있어서, 서버 가드가 붙은 순간 이 버튼만 막혔다.
    if(e.code === 'NOT_CLOSED'){
      if(!confirm((e.message || '아직 마감 시각 전입니다.')
          + String.fromCharCode(10) + String.fromCharCode(10)
          + '지금 유찰 처리하면 아직 투찰할 수 있던 업체가 배제됩니다. 되돌릴 수 없습니다.'
          + String.fromCharCode(10) + '그래도 지금 유찰 처리하시겠습니까?')) return;
      try{ const r2=await api('POST','/api/change-orders/'+id+'/close-full',
                              {failed:true, force:true});
           toast(r2.message || '유찰 처리했습니다.'); closeModal(); VIEWS.changeorders(); }
      //  ⚠⚠ [라운드503] 형제(coWithdraw 등) 참조 — catch도 성공 분기(바로 위)와
      //    같이 정리한다.
      catch(e2){ toast(e2.message); closeModal(); VIEWS.changeorders(); }
      return;
    }
    //  ⚠⚠ [라운드503] 형제(coWithdraw 등, 라운드481·486·500·501) 참조 — 이
    //    자리(알 수 없는 오류)도 catch가 성공 분기(위)와 같이 정리한다.
    toast(e.message); closeModal(); VIEWS.changeorders();
  }
}

// ── 정산 관리 ──


VIEWS.settle = async () => {
  //  ⚠ **상단 지표는 화면에서 더하지 않는다.** 목록은 LIMIT 1000 이고 취소분도 섞여 있어,
  //    대시보드(전 테이블·취소 제외)와 숫자가 어긋난다. 서버가 같은 기준으로 낸 값을 쓴다.
  let sum = null;
  try { sum = await api('GET','/api/settlements/summary'); } catch(e) {}
  const all = await api('GET','/api/settlements');       // 표에 그릴 행(최근 1000건)
  const qs = searchQS('settle');
  //  대시보드 금액에서 넘어왔으면 그 금액을 이룬 행만 — 조건은 서버가 대시보드와 같은 SQL 로 건다
  if(settleMoney) qs.set('money', settleMoney);
  const data = qs.toString() ? await api('GET','/api/settlements?'+qs) : all;
  const md = settleMoney ? (MONEY_META[settleMoney] || {}) : null;
  //  ⚠ 드릴다운 합계는 **서버가 낸 값**을 쓴다. data 는 LIMIT 1000 이라
  //    1000건을 넘는 순간 "대시보드와 같아야 합니다" 라고 써 둔 바로 그 자리에서
  //    숫자가 갈린다(잘렸다는 표시도 없다). 못 받으면 종전처럼 목록을 더한다.
  let drill = null;
  if(md){ try { drill = (await api('GET','/api/settlements/summary?'+qs)).drill; } catch(e) {} }
  const dsum = col => drill ? (drill[col]||0) : data.reduce((a,s)=>a+(s[col]||0),0);
  const pend = all.filter(s=>s.insurer_paid==='입금완료' && s.review_status==='대기');
  // ⚠ 보험사 '공사 완료 승인'이 없으면 입금 확인부터 막힌다(서버 가드). 예전에는 이 대기가
  //   '입금 확인 대기'에 뭉뚱그려져 며칠째 멈춰 있는지도 안 보였다 → 별도 칸으로 세운다.
  //  ⚠ 대시보드는 `insurer_approved=0 AND void_status<>'취소'` 로 센다 — 같은 술어를 쓴다.
  const apWait = all.filter(s=>!s.insurer_approved && s.void_status!=='취소');
  // 입금 확인이 지금 가능한 건 — 일괄 처리 대상(서버 가드와 같은 조건)
  const payable = data.filter(canPay);
  //  ⚠⚠ [337라운드] 일괄 입금확인(/api/settlements/paid-bulk)도 require_role
  //    (중간관리자, app.py:12568) — 아래 바·체크박스열은 이 등급일 때만 보인다
  //    (settleAction() 과 같은 사유, 여기 주석 참조).
  const canBulk = myRank() >= 2 && payable.length;
  const stale = s => {
    if(!s.created_at) return 0;
    const t = Date.parse(String(s.created_at).replace(' ','T')+'+09:00');
    return isNaN(t) ? 0 : Math.floor((Date.now()-t)/86400000);
  };
  $('#content').innerHTML = `
    ${/*  고정 열수는 사이드바를 뺀 실제 폭을 몰라 마지막 카드를 자른다 — 남는 폭으로 접는다 */''}
    <div class="krow k4" style="grid-template-columns:repeat(auto-fit,minmax(178px,1fr))">
      <div class="kc"${apWait.length?' style="border-color:var(--red)"':''}><div class="k">보험사 완료승인 대기</div>
        <div class="v"${apWait.length?' style="color:var(--red)"':''}>${apWait.length}<small>건</small></div>
        <div class="d">${apWait.length?'이 승인이 없으면 입금 확인부터 막힘':'대기 없음'}</div></div>
      ${/*  ⚠ 취소된 정산은 기다릴 대상이 아니다. 같은 화면의 형제 지표
             (완료승인 대기·이체 실행 대기·canPay())는 전부 void_status 를 보는데
             이 카드만 안 봐서, 취소한 건이 영원히 '대기 1건' 으로 남았다. */''}
      <div class="kc"><div class="k">입금 확인 대기</div><div class="v">${all.filter(s=>s.insurer_approved && s.insurer_paid!=='입금완료' && s.void_status!=='취소').length}<small>건</small></div><div class="d">승인 완료 · 송금 확인 필요</div></div>
      <div class="kc"><div class="k">지급 검수 대기</div><div class="v">${pend.length}<small>건</small></div><div class="d">입금확인 → 이체 전 승인</div></div>
      ${/*  ⚠ 검수 승인 뒤 '이체예약'으로 들어간 건을 **아무도 세지 않았다.**
             화면은 자동이체라고 말하고 실제로는 사람이 눌러야 하니, 협력사 대금이
             무기한 멈춰도 알아채는 사람이 없었다. */''}
      ${(()=>{const wait = all.filter(s=>s.review_status==='승인' && s.transfer_status!=='이체완료' && s.void_status!=='취소');
        const amt = wait.reduce((a,s)=>a+(s.payout||0),0);
        return `<div class="kc${wait.length?' act':''}"><div class="k">이체 실행 대기</div>
          <div class="v"${wait.length?' style="color:var(--red)"':''}>${wait.length}<small>건</small></div>
          <div class="d">${wait.length?`${won(amt)}원 — 담당자가 이체를 눌러야 나갑니다`:'대기 없음'}</div></div>`;})()}
      ${/*  ⚠ 돈 3칸은 **서버 집계(sum)** 를 쓴다. 화면에서 목록을 더하면 LIMIT 1000 에
             잘리고 취소된 정산까지 섞여, 대시보드와 숫자가 어긋난다. */''}
      <div class="kc"><div class="k">평균 수수료율</div><div class="v">${sum ? (sum.fee_rate_avg ?? '—') : '—'}<small>%</small></div><div class="d">시행사 수수료 납부완료 기준 · 취소분 제외</div></div>
      <div class="kc hero"><div class="k">수수료 수납액</div><div class="v">${won(sum ? sum.fee_paid : 0)}<small>원</small></div><div class="d">시행사→복구온 납부완료 누적 · 취소분 제외</div></div>
      <div class="kc"><div class="k">총 정산 건</div><div class="v">${sum ? sum.n : all.length}<small>건</small></div><div class="d">${sum ? '취소분 제외' : '표시 기준'}</div></div>
    </div>
    ${apWait.length?`<div class="panel" style="border:1.5px solid var(--red);margin-bottom:12px">
      <div class="ph"><span class="pt">보험사 완료승인 대기 <small>이 승인이 없으면 수수료 수납·업체 지급이 함께 멈춥니다</small></span>
        <span class="pill red">${apWait.length}건</span></div>
      <div class="tbl-wrap"><table class="tbl">
        <tr><th style="width:52px" class="r">경과</th><th>사건</th><th>발주처</th><th>시공업체</th><th class="r">공사대금</th><th class="r">액션</th></tr>
        ${apWait.sort((a,b)=>stale(b)-stale(a)).slice(0,12).map(s=>{const dd=stale(s);
          const hot = dd>=7?'color:var(--red);font-weight:800':dd>=3?'color:var(--amber-text);font-weight:700':'';
          return `<tr>
          <td class="r" style="white-space:nowrap;${hot}">${dd}일${dd>=7?' ⚠':''}</td>
          <td class="em"><a href="#" data-act="settleDetail" data-arg="${s.id}" style="color:var(--blue);font-weight:700">${esc(s.case_no)}</a></td>
          <td>${esc(s.insurer)}</td><td>${esc(s.partner_name)}</td><td class="r">${won(s.amount)}</td>
          <td class="r"><button class="btn a sm" data-act="remindApproval" data-arg="${s.id}">승인 독촉</button></td></tr>`;}).join('')}
      </table></div>
      <div class="hint" style="margin-top:6px">독촉은 발주처 포털 알림으로 갑니다. 같은 사건에 24시간 안에는 다시 보내지 않습니다(그때는 전화가 빠릅니다).</div>
    </div>`:''}
    ${md?`<div class="panel" style="border:2px solid var(--blue);margin-bottom:12px">
      <div class="ph"><span class="pt">📊 ${esc(md.label||'')} 상세 내역
        <small>대시보드에서 누른 금액을 이루는 정산 건입니다</small></span>
        <span style="flex:1"></span>
        <button class="btn g sm" data-act="clearMoneyDrill">전체 정산 내역으로</button></div>
      <div class="krow k4" style="margin:0">
        <div class="kc hero"><div class="k">${esc(md.label||'')} 합계</div>
          <div class="v">${won(dsum(md.sum_col))}<small>원</small></div>
          <div class="d">${drill?drill.n:data.length}건 · ${esc(md.sum_col==='fee'?'수수료':md.sum_col==='payout'?'업체 지급액':'공사대금')} 기준</div></div>
        <div class="kc"><div class="k">공사대금 합계</div><div class="v">${won(dsum('amount'))}<small>원</small></div><div class="d">${drill?'전체 기준':'이 목록 기준'}</div></div>
        <div class="kc"><div class="k">수수료 합계</div><div class="v">${won(dsum('fee'))}<small>원</small></div><div class="d">${drill?'전체 기준':'이 목록 기준'}</div></div>
        <div class="kc"><div class="k">업체 지급액 합계</div><div class="v">${won(dsum('payout'))}<small>원</small></div><div class="d">${drill?'전체 기준':'이 목록 기준'}</div></div>
      </div>
      <div class="hint" style="margin-top:8px">${esc(md.note||'')}
        대시보드 카드와 <b>같은 조건</b>으로 걸러 냈으므로, 위 합계가 그 숫자와 같아야 합니다.</div>
    </div>`:''}
    <div class="panel">
      <div class="ph"><span class="pt">정산 내역 <small>${md?`${esc(md.label)} ${data.length}건 · `:(qs.toString()?data.length+'건 검색결과 · ':'')}보험사→시행사 직접 지급 확인 → 내부 검수(필수) → 지급 확정 · 수수료는 보험사가 복구온에 별도 송금(상세에서 확인)</small></span></div>
      ${searchBar('settle',{ph:'접수번호·발주처·시공업체'})}
      <div style="display:flex;justify-content:flex-end;margin-bottom:8px">
        ${xlsxBtn('settlements','정산')}
      </div>
      ${canBulk?`<div id="paybar" class="notice" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px">
        <b>입금 확인 대기 ${payable.length}건</b>
        <span class="sub">보험사는 여러 건을 한 번에 송금합니다 — 통장에서 확인한 건을 골라 한 번에 처리하세요.</span>
        <span style="flex:1"></span>
        <button class="btn g sm" data-act="settlePickAll">대기 전체 선택</button>
        <button class="btn p sm" data-act="settlePaidBulk" id="pbBtn" disabled>선택 <span id="pbN">0</span>건 입금 확인</button>
      </div>`:''}
      <div class="tbl-wrap"><table class="tbl">
        <tr>${canBulk?'<th style="width:34px"></th>':''}<th>사건</th><th>보험사</th><th>시공업체</th><th class="r">공사대금</th><th class="r">수수료</th><th class="r">업체 지급액</th><th>입금</th><th>지급검수</th><th>이체</th><th class="r">액션</th></tr>
        ${data.map(s=>`<tr${s.void_status==='취소'?' style="opacity:.55;text-decoration:line-through"':''}>
          ${canBulk?`<td>${canPay(s)?`<input type="checkbox" class="pbx" value="${s.id}" data-amt="${s.amount||0}" data-act-change="pbSync" aria-label="${esc(s.case_no)} 입금 확인 선택">`:''}</td>`:''}
          <td class="em"><a href="#" data-act="settleDetail" data-arg="${s.id}" style="color:var(--blue);font-weight:700">${esc(s.case_no)}</a>
            ${s.void_status==='취소'?` <span class="pill gray" title="${esc(s.void_reason||'')}">취소</span>`:''}</td>
          <td>${esc(s.insurer)}</td><td>${esc(s.partner_name)}</td>
          <td class="r">${won(s.amount)}</td><td class="r em">${won(s.fee)}</td><td class="r">${won(s.payout)}</td>
          <td>${statusPill(s.insurer_paid)}</td><td>${statusPill(s.review_status)}</td><td>${statusPill(s.transfer_status)}</td>
          <td class="r">${settleAction(s)}</td></tr>`).join('')}
      </table></div>
      <p style="font-size:.66rem;color:var(--faint);margin-top:10px">※ <b>보험사→시행사 지급 확인 → 지급 검수 승인 → 이체 완료</b> 순서로만 진행됩니다. 공사대금은 보험사가 시행사에 직접 지급하고, 복구온 수수료는 (기존과 같이 시행사 부담으로) 시행사가 별도로 송금합니다(수수료 입금 확인은 각 건 상세에서 처리). 확인 전 지급 예약은 서버에서 차단되며, 모든 단계가 감사 로그에 기록됩니다.</p>
    </div>`;
};
// 보험사에 완료승인을 다시 안내한다(상태는 바뀌지 않는다 — 알림만).
async function remindApproval(sid){
  try{
    const r = await api('POST','/api/settlements/'+sid+'/remind-approval',{});
    toast(r.message);
  }catch(e){
    if(e.code==='COOLDOWN'||e.code==='ALREADY_APPROVED'){ toast(e.message); return; }
    toast(e.message);
  }
}

// 정산은 세 관문을 순서대로 통과한다. 현재 단계에 맞는 버튼 하나만 보여준다.
function settleExport(){ location.href = '/api/settlements/export'; }

function settleAction(s){
  // 취소된 정산은 아무 단계도 진행하지 않는다(기록으로만 남는다).
  if (s.void_status === '취소') return '<span class="sub">취소됨</span>';
  // 이체가 나간 뒤에는 되돌릴 수 없다(돈이 이미 은행 밖으로 나갔다).
  if (s.transfer_status === '이체완료') return '<span class="sub">완료</span>';
  //  ⚠⚠ [337라운드] 이 함수가 내는 버튼 6개 전부 백엔드가 require_role 인데
  //    (입금확인·더블체크승인·되돌리기=중간관리자, 정산취소·이체완료=최고관리자,
  //    app.py 12529·13409·13297·13211·12625행) 등급 무관하게 그려졌다 — 형제
  //    (coActions, 252라운드)처럼 자격 없으면 버튼 대신 조용히 안내문으로
  //    바꾼다. 목록 조회(GET /api/settlements)는 require_admin(등급무관)이라
  //    하위관리자도 화면 자체는 정상적으로 보되, 처리는 여기서 막힌다. 버튼별로
  //    필요등급이 갈려(2 vs 3) coActions() 처럼 함수 전체를 한 번에 막을 수
  //    없다 — 등급을 여기서 한 번만 읽어 버튼마다 개별로 확인한다.
  const rank = myRank();
  // 진행한 단계가 있으면 되돌리기를 함께 보여준다 — 오처리로 사건이 고착되지 않게.
  const undo = (rank >= 2 && (s.insurer_paid === '입금완료' || s.review_status === '승인'))
    ? ` <button class="btn g sm" data-act="settleUndo" data-arg="${s.id}" title="직전 단계 되돌리기">되돌리기</button>` : '';
  // 정산 취소는 **돈이 움직이기 전**에만 — 입금·검수·이체가 시작되면 되돌리기가 먼저다.
  const canVoid = (s.insurer_paid !== '입금완료' && s.review_status !== '승인');
  const voidBtn = (rank >= 3 && canVoid)
    ? ` <button class="btn g sm" data-act="settleVoid" data-arg="${s.id}" title="잘못 만든 정산을 무효화하고 사건을 검수대기로 되돌립니다">정산 취소</button>` : '';
  // ①보험사 완료 승인이 입금확인의 선행 관문
  if (!s.insurer_approved)
    return `<span class="pill amber" title="보험사 포털에서 '공사 완료 승인'을 눌러야 진행됩니다">보험사 승인 대기</span>${voidBtn}`;
  if (s.insurer_paid !== '입금완료')
    return rank >= 2
      ? `<button class="btn g sm" data-act="settlePaid" data-arg="${s.id}">입금 확인</button>${voidBtn}`
      : `<span class="sub">중간관리자 이상만 처리할 수 있습니다</span>${voidBtn}`;
  if (s.review_status !== '승인')
    return rank >= 2
      ? `<button class="btn a sm" data-act="settleReview" data-arg="${s.id}">더블체크·지급 승인</button>${undo}`
      : `<span class="sub">중간관리자 이상만 처리할 수 있습니다</span>${undo}`;
  //  ⚠ 확인창이 "어느 건인지"를 말할 수 있게 값을 버튼에 실어 보낸다.
  //    (돈이 나가는 마지막 문인데 종전 확인창에는 사건도 업체도 금액도 없었다)
  //  ⚠⚠ [라운드242] `|| s.amount` 는 여기서도 **0% 이 아니라 100% 요율**을 삼킨다
  //    (라운드74가 fee_rate_bp 에서 고친 것과 같은 함정 — 0 이 falsy 라서 "없음"과
  //    "정확히 0" 을 구분 못한다). 수수료 100% 계약(_parse_fee_pct 는 0~100 을 다
  //    허용)이면 payout 은 정확히 0 인데, 이 확인창만 공사대금 전액을 "지급 완료로
  //    기록합니다"라고 보여준다 — 바로 한 단계 전 더블체크 모달(위 376행 부근,
  //    won(s.payout))은 이미 0원이라고 정확히 보여준 뒤라 **돈이 나가는 마지막
  //    문에서 두 화면이 서로 다른 금액을 말한다.** 실제 이체 요청엔 금액을 안 실어
  //    보내 DB·통지는 영향 없지만, 운영자가 이 확인창을 보고 잘못 판단할 수 있다.
  //    ?? 로 바꿔 "정말 없음(null/undefined)"일 때만 amount 로 대체한다.
  const tinfo = esc([s.case_no, s.partner_name].filter(Boolean).join(" · "))
                + "|" + Number(s.payout ?? s.amount ?? 0);
  return rank >= 3
    ? `<button class="btn p sm" data-act="settleTransfer" data-arg="${s.id}" data-info="${tinfo}">이체 완료</button>${undo}`
    : `<span class="sub">최고관리자만 처리할 수 있습니다</span>${undo}`;
}
// 정산 취소 — 행을 지우지 않고 무효 표시만 남긴다(과거 명세서가 뒤에서 바뀌지 않게).
async function settleVoid(sid){
  const reason = prompt('이 정산을 취소(무효화)합니다.\n'
    + '사유를 5자 이상 남겨 주세요 (예: 검수 승인 오처리로 재작성 필요).\n\n'
    + '· 행은 남고 취소 표시만 됩니다(회계 이력 보존).\n'
    + '· 사건은 검수대기로 돌아가 다시 승인할 수 있습니다.');
  if(reason===null) return;
  if(reason.trim().length<5){ toast('사유를 5자 이상 입력해 주세요.'); return; }
  try{
    const r = await api('POST','/api/settlements/'+sid+'/void',{reason:reason.trim()});
    toast(r.message); VIEWS.settle(); refreshBadges();
  }catch(e){
    //  ⚠⚠ [라운드500] 형제(caseDetail 액션버튼, 라운드481·486)가 이미 세운
    //    원칙 — 성공 분기만 목록을 새로고침하면, 동시에 다른 관리자가 먼저
    //    처리해 이미 취소·완료된 건을 이 화면만 계속 처리 가능한 것으로
    //    계속 보여준다(서버 여러 지점이 "취소된 정산 건입니다"류 409를
    //    code 없이 반환해 원인 구분도 못 한다). catch도 성공 분기와 같이
    //    정리한다 — 정산 6개 함수(settleVoid·Undo·Paid·PaidBulk·
    //    doSettleReview·settleTransfer) 전부 같은 결함이었다.
    toast(e.message); VIEWS.settle(); refreshBadges();
  }
}

async function settleDetail(id){
  let d;
  try{ d = await api('GET','/api/settlements/'+id+'/detail'); }catch(e){ toast(e.message); return; }
  const s=d.settlement, c=d.case||{}, p=d.partner||{};
  const step=(label,done,ts)=>`<div style="display:flex;align-items:center;gap:8px;padding:5px 0">
    <span style="width:16px;height:16px;border-radius:50%;background:${done?'var(--green)':'var(--line)'};color:#fff;font-size:.6rem;display:flex;align-items:center;justify-content:center">${done?'✓':''}</span>
    <span style="flex:1;font-size:.8rem">${label}</span>
    <span style="font-size:.7rem;color:var(--faint)">${done?esc(ts||'완료'):'대기'}</span></div>`;
  openModal(`<h3>정산 상세 · ${esc(s.case_no)}</h3>
    <div class="msub">${esc(s.insurer)} · ${esc(c.category||'')} ${esc(c.region||'')}</div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:12px 0">
      <div class="kc"><div class="k">공사대금</div><div class="v" style="font-size:1.05rem">${won(s.amount)}<small>원</small></div></div>
      ${/*  ⚠ `|| 1000` 은 **0% 계약을 10% 로 만든다**(0 이 falsy). 돈(s.fee)은 맞는데
             요율 표시만 거짓이라, 검수자가 「10% 계약인데 왜 0원이지」로 헷갈린다.
             같은 파일의 bpPct·settleReview·서버(_fee_rate_bp) 는 이미 null 판정이다. */''}
      <div class="kc"><div class="k">수수료 (${((s.fee_rate_bp ?? 1000)/100).toFixed(1).replace('.0','')}%)</div><div class="v" style="font-size:1.05rem">${won(s.fee)}<small>원</small></div></div>
      <div class="kc hero"><div class="k">업체 지급액</div><div class="v" style="font-size:1.05rem">${won(s.payout)}<small>원</small></div></div>
    </div>
    ${c.co_extra?`<div class="msub" style="color:var(--amber-text)">※ 변경 견적 추가분 ${won(c.co_extra)}원이 합산된 금액입니다.</div>`:''}
    ${d.tax?`
    <div style="background:var(--mist);border-radius:11px;padding:11px 14px;margin:10px 0;
                font-size:.78rem;line-height:1.7">
      <b>세금계산서 (복구온 → 시공사, 중개수수료)</b>
      <div style="display:flex;gap:18px;flex-wrap:wrap;margin-top:5px">
        <span>공급가액 <b>${won(d.tax.supply)}원</b></span>
        <span>부가세(${d.tax.rate}%) <b>${won(d.tax.vat)}원</b></span>
        <span>합계 <b>${won(d.tax.total)}원</b></span>
      </div>
      <div style="font-size:.7rem;color:var(--faint);margin-top:4px">${esc(d.tax.basis)}</div>
    </div>`:''}
    <div class="ph" style="margin-top:6px"><span class="pt" style="font-size:.8rem">정산 단계 (공사대금 — 보험사 → 시행사 직접 지급)</span></div>
    <div style="padding:4px 0">
      ${step('보험사 공사 완료 승인', !!s.insurer_approved, (s.insurer_approved_at||'').slice(5,16))}
      ${step('보험사 → 시행사 지급 확인', s.insurer_paid==='입금완료')}
      ${step('지급 검수 승인 (더블 크로스체크)', s.review_status==='승인')}
      ${step('시행사 지급 완료', s.transfer_status==='이체완료')}
    </div>
    <div class="ph" style="margin-top:10px"><span class="pt" style="font-size:.8rem">시행사 지급 계좌</span></div>
    <div class="kv"><span class="k">시공업체</span><span class="v">${esc(p.name||'')}</span></div>
    <div class="kv"><span class="k">계좌</span><span class="v">${esc(p.bank_name||'-')} ${esc(p.account_masked||'미등록')} ${p.bank_holder?'('+esc(p.bank_holder)+')':''}</span></div>
    ${/*  ⚠ 정산구조 변경(2026-10-18) — 수수료는 더 이상 시행사 지급액에서 공제돼
           나가는 게 아니라, 보험사가 복구온에 별도로 송금한다. 그래서 위 '정산
           단계'(시행사 지급 체인)와는 완전히 독립된 별도 확인 절차·버튼을 둔다 —
           review_status 승인만 선행 관문(이 건이 정당한지는 먼저 확인돼야 하므로),
           순서는 시행사 지급과 무관하게 아무 때나 할 수 있다. */''}
    <div class="ph" style="margin-top:10px"><span class="pt" style="font-size:.8rem">복구온 수수료 (시행사 부담 — 시행사 → 복구온 별도 송금)</span></div>
    <div style="padding:4px 0">
      ${step('수수료 입금 확인', s.fee_collect_status==='완료', (s.fee_collected_at||'').slice(5,16))}
    </div>
    ${s.void_status!=='취소' && s.review_status==='승인' && s.fee_collect_status!=='완료'
      ? (myRank()>=2
          ? `<button class="btn a sm" data-act="settleFeeCollected" data-arg="${s.id}">수수료 입금 확인</button>`
          : `<span class="sub">중간관리자 이상만 처리할 수 있습니다</span>`)
      : (s.review_status!=='승인' && s.fee_collect_status!=='완료'
          ? `<span class="sub">지급 검수 승인 후 확인할 수 있습니다</span>` : '')}
    ${d.timeline&&d.timeline.length?`<div class="ph" style="margin-top:10px"><span class="pt" style="font-size:.8rem">처리 이력</span></div>
      <div style="font-size:.72rem;max-height:150px;overflow:auto">${d.timeline.map(t=>`· ${esc((t.created_at||'').slice(5,16))} ${esc(t.actor||'')} — ${esc(t.action)}`).join('<br>')}</div>`:''}
    <div class="modal-foot"><span style="flex:1"></span><button class="btn g" data-act="closeModal">닫기</button></div>`);
}

async function settleUndo(id){
  const reason = prompt('직전 정산 단계를 되돌립니다.' + String.fromCharCode(10) +
    '감사로그에 남길 사유를 적어 주세요. (5자 이상)');
  if(reason === null) return;
  if(reason.trim().length < 5){ toast('사유를 5자 이상 적어 주세요.'); return; }
  //  ⚠⚠ [라운드228] 이 클릭 1회에 해당하는 열쇠 — fetch 가 네트워크 계층에서
  //    같은 요청을 재전송해도 이 값은 그대로라, 서버가 "방금 그 요청"과
  //    "새로 한 번 더 누른 요청"을 구분할 수 있다.
  const undoKey = Date.now().toString(36) + Math.random().toString(36).slice(2);
  try{
    const r = await api('POST','/api/settlements/'+id+'/undo',{reason:reason.trim(), undo_key:undoKey});
    toast(r.message || '되돌렸습니다.');
    refreshBadges(); VIEWS.settle();
  }catch(e){
    //  ⚠⚠ [라운드500] 형제(settleVoid) 참조 — catch도 성공 분기와 같이 정리한다.
    toast(e.message); refreshBadges(); VIEWS.settle();
  }
}

async function settlePaid(id){
  try{
    await api('POST','/api/settlements/'+id+'/paid');
    toast('보험사 <b>입금 확인</b> 처리했습니다. 이제 지급 검수를 진행하세요.');
    refreshBadges(); VIEWS.settle();
  }catch(e){
    //  ⚠⚠ [라운드500] 형제(settleVoid) 참조 — catch도 성공 분기와 같이 정리한다.
    toast(e.message); refreshBadges(); VIEWS.settle();
  }
}

//  정산구조 변경(2026-10-18) 신규 — 시행사 지급 체인(settlePaid→Review→Transfer)과
//  완전히 독립된 별도 확인. 성공하면 상세 모달을 다시 열어 체크 표시를 바로 보여준다
//  (닫아버리면 '진짜 저장됐는지' 다시 눌러 확인해야 해서 — 형제들과 다르게 이 모달
//  자체를 새로고침하는 이유).
async function settleFeeCollected(id){
  try{
    await api('POST','/api/settlements/'+id+'/fee-collected');
    toast('복구온 <b>수수료 입금</b>을 확인했습니다.');
    refreshBadges(); VIEWS.settle(); settleDetail(id);
  }catch(e){
    toast(e.message);
  }
}

// ── 입금 확인 일괄 처리 ─────────────────────────────────────────
//  보험사는 여러 건 대금을 한 번에 보낸다. 한 건씩 누르면 대기 15건에 왕복 15회였다.
//  ⚠ 묶는 건 **입금 확인까지**다 — 검수·이체는 계좌·하자를 건별로 봐야 해서 묶지 않는다.
function canPay(s){
  return (s.void_status !== '취소') && !!s.insurer_approved && s.insurer_paid !== '입금완료';
}
function pbSync(){
  const box = document.getElementById('paybar'); if(!box) return;
  const n = document.querySelectorAll('.pbx:checked').length;
  const lab = document.getElementById('pbN'); if(lab) lab.textContent = n;
  const btn = document.getElementById('pbBtn'); if(btn) btn.disabled = !n;
}
function settlePickAll(){
  const boxes = [...document.querySelectorAll('.pbx')];
  const on = boxes.some(b=>!b.checked);          // 하나라도 안 골랐으면 전체 선택, 아니면 해제
  boxes.forEach(b=>{ b.checked = on; });
  pbSync();
}
async function settlePaidBulk(){
  const picked = [...document.querySelectorAll('.pbx:checked')];
  if(!picked.length){ toast('입금 확인할 건을 골라 주세요.'); return; }
  const sum = picked.reduce((a,b)=>a+Number(b.dataset.amt||0),0);
  const NL = String.fromCharCode(10);
  if(!confirm(`선택한 ${picked.length}건(공사대금 합계 ${won(sum)}원)의 보험사 입금을 확인 처리합니다.` + NL + NL +
              '통장에 실제로 들어온 건만 고르셨는지 확인해 주세요.' + NL +
              '(잘못 눌렀으면 각 행의 「되돌리기」로 취소할 수 있습니다)')) return;
  const memo = prompt('메모를 남기려면 적어 주세요 (선택 · 예: 8/3 삼성화재 일괄입금)', '') || '';
  try{
    const r = await api('POST','/api/settlements/paid-bulk',
                        {ids: picked.map(b=>Number(b.value)), memo: memo.trim()});
    const skip = (r.skipped_count||0)
      ? ` · 건너뜀 ${r.skipped_count}건(${(r.skipped||[]).slice(0,3).map(x=>esc(x.case_no)+' '+esc(x.why)).join(', ')})`
      : '';
    toast(`<b>${r.done_count}건</b> 입금 확인 (${won(r.total_amount||0)}원)${skip}`);
    refreshBadges(); VIEWS.settle();
  }catch(e){
    //  ⚠⚠ [라운드500] 형제(settleVoid) 참조 — catch도 성공 분기와 같이 정리한다.
    toast(e.message); refreshBadges(); VIEWS.settle();
  }
}

// 지급 검수 = 우리측 '더블 크로스체크'. 3가지 확인을 모두 체크해야 승인 버튼이 열린다.
//  ⚠ '계좌를 확인했습니다'에 서명하려면 화면에 계좌가 실제로 보여야 한다. 예전에는
//    계좌를 띄우지도 않고 체크만 받았고, 계좌 미등록이어도 이체완료까지 눌려
//    '완료로 닫힌 채 지급 누락'이 만들어졌다.
async function settleReview(id){
  let d = null;
  //  ⚠⚠ [라운드74] 조회가 실패해도 조용히 null 로 넘어갔다 — 아래 폴백(p={}, s={})이
  //    "공사대금 0원 − 공제 0원 = 0원 — 금액이 정확합니다"와 "계좌 미등록"을
  //    **실제 상태인 것처럼** 띄운다. 체크박스가 잠겨(hasAcct=false) 승인
  //    자체는 못 누르니 잘못된 지급으로 이어지진 않지만(안전하게 막힘), 검수자가
  //    가짜 "계좌 미등록"을 보고 이미 등록된 계좌를 다시 등록하려 들 수 있다.
  //    형제(settleDetail)처럼 실패를 그대로 알리고 멈춘다.
  try{ d = await api('GET','/api/settlements/'+id+'/detail'); }
  catch(e){ toast(e.message); return; }
  const p = (d && d.partner) || {};
  const s = (d && d.settlement) || {};
  //  ⚠ `|| 1000` 은 **0% 계약을 10% 로 만든다**(0 이 falsy 라서).
  //    수수료 0% 로 계약한 발주처의 정산 화면이 10% 를 인쇄하면
  //    검수자가 틀린 금액에 서명하게 된다. 서버는 이미 ?? 로 고쳤다.
  const pct = ((s.fee_rate_bp ?? 1000) / 100);
  //  ★ 부가세 기준은 정산 행이 아니라 응답의 tax 에 온다(app.py: "vat_included": _inc).
  const _vatInc = (d && d.tax && typeof d.tax.vat_included === 'boolean')
                  ? d.tax.vat_included : true;
  const _vatR   = (d && d.tax && Number(d.tax.rate)) || 10;
  const hasAcct = !!p.has_account;
  const ck = (t, disabled)=>`<label style="display:flex;align-items:center;gap:9px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;margin-bottom:8px;font-size:.82rem;cursor:${disabled?'not-allowed':'pointer'};${disabled?'opacity:.55':''}">
    <input type="checkbox" class="dc" ${disabled?'disabled':''}> ${t}</label>`;
  openModal(`<h3>지급 검수 승인 — 더블 크로스체크</h3>
    <div class="msub">아래 3가지를 모두 확인해야 수수료 공제 후 이체가 예약됩니다.</div>
    ${ck(`공사대금 ${won(s.amount)}원 − 공제 ${won(s.fee)}원 = 업체 지급액 ${won(s.payout)}원 — 금액이 정확합니다`
         /*  ⚠ 종전 조건은 `s.fee_vat_included === false` 였다. `s` 는
             `SELECT * FROM settlements` 원본인데 그 표에는 그 컬럼이 **없다** —
             undefined === false 는 늘 거짓이라 아래 '부가세 별도' 분해 줄은
             한 번도 렌더된 적이 없다. 기준은 응답의 tax.vat_included 로 온다. */
         + (_vatInc === false
            ? `<br><span class="sub">(요율 ${pct}% ${won(Math.round((s.fee||0)/(1+_vatR/100)))}원 + 부가세 ${won((s.fee||0)-Math.round((s.fee||0)/(1+_vatR/100)))}원 = 공제 ${won(s.fee)}원 · <b>부가세 별도</b> 기준)</span>`
            : `<span class="sub"> (요율 ${pct}% · 부가세 포함 기준)</span>`))}
    ${ck(hasAcct
        ? `시공업체 정산 계좌를 확인했습니다 — <b>${esc(p.bank_name||'')} ${esc(p.account_masked||'')}</b> (예금주 ${esc(p.bank_holder||'-')})`
        : `시공업체 정산 계좌 — <b style="color:var(--red)">미등록</b> (등록 전에는 지급할 수 없습니다)`,
        !hasAcct)}
    ${/*  ⚠ 예전에는 하자를 화면에 띄우지도 않고 '하자 없음'에 서명받았다.
           보이지 않으니 늘 체크됐고, 그 체크가 지급 보류 관문을 무력화했다. */''}
    ${/*  ⚠ 체크박스를 잠그면 안 된다 — 서버에는 '사유를 남기고 넘기는' 경로가 있는데
           화면에서 버튼이 영영 안 열리면 그 경로에 닿을 수 없어 새 교착이 된다.
           막지 말고 **무엇이 열려 있는지 보여준 뒤** 서명하게 한다. */''}
    ${(d && (d.open_defects||[]).length)
      ? ck(`위 <b style="color:var(--red)">하자 ${d.open_defects.length}건</b>을 확인했고, 그럼에도 지급해야 한다고 판단합니다`)
      : ck('미해결 하자가 없어 전액 지급 가능합니다 <span class="sub">(열린 하자 0건 — 서버 확인)</span>')}
    ${(d && (d.open_defects||[]).length) ? `<div class="notice" style="border-color:var(--red);margin-bottom:8px">
      <b>열린 하자 ${d.open_defects.length}건</b> — 이 상태로는 지급 승인이 막힙니다(사유를 남기면 넘길 수 있습니다).
      <div style="margin-top:6px">${d.open_defects.slice(0,5).map(x=>`
        <div style="font-size:.78rem;line-height:1.7">· <b>${esc(x.defect_no)}</b> ${esc(x.title)}
          <span class="pill ${x.severity==='중대'?'red':x.severity==='보통'?'amber':'gray'}">${esc(x.severity)}</span>
          ${statusPill(x.status)}${x.due_date?` · 기한 ${esc(x.due_date)}`:''}</div>`).join('')}
        ${d.open_defects.length>5?`<div class="sub">외 ${d.open_defects.length-5}건</div>`:''}</div></div>`:''}
    ${hasAcct?'':`<div class="hint" style="color:var(--red);margin-bottom:8px">
      ⚠ ${esc(p.name||'시공업체')}의 지급 계좌가 등록되지 않았습니다. 계좌를 등록한 뒤 지급을 진행하세요.
      (계좌 등록 = 최고관리자 · 업체 관리 화면)</div>`}
    <div class="modal-foot">
      <button class="btn a" id="dc_ok" data-act="doSettleReview" data-arg="${id}" disabled>더블 체크 완료 · 지급 승인</button>
      <span style="flex:1"></span><button class="btn g" data-act="closeModal">취소</button>
    </div>`);
  const modal=document.getElementById('modal');
  modal.querySelectorAll('.dc').forEach(cb=>cb.addEventListener('change',()=>{
    const boxes=[...modal.querySelectorAll('.dc')].filter(x=>!x.disabled);
    const all = boxes.length===3 && boxes.every(x=>x.checked);
    const b=modal.querySelector('#dc_ok'); if(b) b.disabled=!all;
  }));
}
// ── 관문을 넘길 때 쓰는 공용 물음 ────────────────────────────────
//  ⚠ 서버에는 "부득이하면 사유를 적어 진행할 수 있습니다"라는 예외 경로가 여럿 있는데,
//    **화면에 그 창구가 없어 실제로는 아무도 못 넘겼다.** 관문에 걸리면 그냥 막혔다.
//    사유는 감사로그에 남는다 — 넘긴 사람과 이유가 기록된다.
function askOverride(title, detail, ask){
  const NL = String.fromCharCode(10);
  const r = prompt(title + NL + NL + detail + NL + NL + ask + ' (5자 이상)', '');
  if(r === null) return null;
  if(r.trim().length < 5){ toast('사유를 5자 이상 적어 주세요.'); return null; }
  return r.trim();
}

//  관문이 **겹칠 수 있다**(하자 + 계좌 미등록). 하나씩만 처리하면 사유를 적어 넘긴 뒤
//  다음 관문에서 또 막혀 되돌아온다 — 이체 화면과 같은 방식으로 이어서 묻는다.
async function doSettleReview(id){
  const GATE = {
    DEFECT_OPEN: {
      field: 'defect_override_reason',
      title: '처리 중인 하자가 남아 있습니다.',
      ask: '그래도 지급 승인해야 하는 사유를 적어 주세요.',
      done: '하자 미처리 사유' },
    NO_BANK_ACCOUNT: {
      field: 'no_account_reason',
      title: '지급 계좌가 등록되지 않았습니다.',
      ask: '상계·별도 합의 등 계좌 없이 정리하는 사유를 적어 주세요.',
      done: '계좌 미등록 사유' },
  };
  const extra = {double_checked:true}, passed = [];
  for(let round = 0; round < 4; round++){
    try{
      await api('POST','/api/settlements/'+id+'/review', extra);
      closeModal();
      toast(passed.length
        ? `${passed.join(' · ')}를 남기고 지급 검수를 <b>승인</b>했습니다`
        : '더블 체크 완료 · 지급 검수 <b>승인</b> — 수수료 공제 후 이체를 실행하세요');
      refreshBadges(); VIEWS.settle();
      return;
    }catch(e){
      const g = GATE[e.code];
      //  ⚠⚠ [라운드500] 형제(settleVoid) 참조 — 이 분기는 모달이 열린 채로
      //    끝나는 경로다. 성공 분기(위)가 closeModal()까지 하므로 여기도
      //    같이 정리한다.
      if(!g || extra[g.field]){ toast(e.message); closeModal(); refreshBadges(); VIEWS.settle(); return; }
      const reason = askOverride(g.title, e.message || '', g.ask);
      if(reason === null) return;
      extra[g.field] = reason;
      passed.push(g.done);
    }
  }
}

async function settleTransfer(id, _b, el){
  //  ★ **어느 건인지 먼저 말한다.** 목록에서 옆 줄을 눌러도 알 수 없었다.
  const raw = (el && el.dataset && el.dataset.info) || '';
  const [who, amtRaw] = raw.split('|');
  const amt = Number(amtRaw || 0);
  const ok = confirm(
    (who ? '[' + who + ']' + String.fromCharCode(10) : '')
    + (amt ? amt.toLocaleString('ko-KR') + '원을 지급 완료로 기록합니다.'
             + String.fromCharCode(10) : '')
    + String.fromCharCode(10)
    + '이체가 실제로 완료되었습니까?' + String.fromCharCode(10) + String.fromCharCode(10)
    + '확인 시 해당 사건이 「완료」로 닫히고 업체에 이체 완료가 통지됩니다.');
  if(!ok) return;
  //  돈이 나가는 마지막 문이다. 관문이 **여러 개 겹칠 수 있다**(하자 + 계좌 미등록).
  //  한 번에 하나씩만 처리하면 사유를 적어 넘긴 뒤 다음 관문에서 다시 막힌다 —
  //  그래서 통과한 사유를 모아 두고, 막히는 게 없어질 때까지 이어서 묻는다.
  const GATE = {
    DEFECT_OPEN: {
      field: 'defect_override_reason',
      title: '처리 중인 하자가 남아 있습니다.',
      ask: '그래도 지급해야 하는 사유를 적어 주세요.',
      done: '하자 미처리 사유' },
    NO_BANK_ACCOUNT: {
      field: 'no_account_reason',
      title: '지급 계좌가 등록되지 않았습니다.',
      ask: '상계·별도 합의 등 계좌 없이 정리하는 사유를 적어 주세요.',
      done: '계좌 미등록 사유' },
  };
  const extra = {}, passed = [];
  for(let round = 0; round < 4; round++){
    try{
      await api('POST','/api/settlements/'+id+'/transfer', extra);
      toast(passed.length
        ? `${passed.join(' · ')}를 남기고 <b>이체 완료</b>했습니다`
        : '<b>이체 완료</b> 처리했습니다. 사건이 완료되었습니다.');
      refreshBadges(); VIEWS.settle();
      return;
    }catch(e){
      const g = GATE[e.code];
      //  ⚠⚠ [라운드500] 형제(settleVoid) 참조 — catch도 성공 분기와 같이 정리한다.
      if(!g || extra[g.field]){ toast(e.message); refreshBadges(); VIEWS.settle(); return; }   // 모르는 오류거나 이미 넘긴 관문
      const reason = askOverride(g.title, e.message || '', g.ask);
      if(reason === null) return;
      extra[g.field] = reason;
      passed.push(g.done);
    }
  }
  toast('관문이 계속 남아 있습니다. 정산 상세에서 상태를 먼저 정리해 주세요.');
  refreshBadges(); VIEWS.settle();
}

// ── 하자·A/S 관리 ──
let defectFilter = '전체';
const DEFECT_FLOW = ['접수','확인중','재시공배정','완료','반려'];
VIEWS.defects = async () => {
  const qs = searchQS('defects'); if(defectFilter!=='전체') qs.set('status', defectFilter);
  const data = await api('GET','/api/defects'+(qs.toString()?'?'+qs:''));
  //  ⚠ 상단 카드는 **서버 집계**를 쓴다. 종전에는 /api/defects 를 한 번 더 불러
  //    (LIMIT 1000) 그 배열 길이로 셌다 — 하자가 1000건을 넘으면 대시보드 배지
  //    (COUNT(*) 전수)와 갈리고, 정렬이 '중대 먼저'라 잘리는 쪽이 경미·오래된
  //    건으로 편향된다. 못 받으면 종전 방식으로 돌아간다.
  let sm = null;
  try { sm = await api('GET','/api/defects/summary'); } catch(e) {}
  const all = sm ? null : await api('GET','/api/defects');
  const cnt = {
    total:    sm ? sm.total    : all.length,
    open:     sm ? sm.open     : all.filter(d=>d.status!=='완료'&&d.status!=='반려').length,
    severe:   sm ? sm.severe   : all.filter(d=>d.status!=='완료'&&d.status!=='반려'&&d.severity==='중대').length,
    overdue:  sm ? sm.overdue  : all.filter(d=>d.status!=='완료'&&d.status!=='반려'&&d.due_date&&d.due_date<todayKST()).length,
    disputed: sm ? sm.disputed : all.filter(d=>d.dispute_reason&&d.status!=='완료'&&d.status!=='반려').length,
    disputed_all: sm ? sm.disputed_all : all.filter(d=>d.dispute_reason).length,
  };
  $('#content').innerHTML = `
    <div class="krow k4">
      <div class="kc hero"><div class="k">처리중 하자</div><div class="v">${cnt.open}<small>건</small></div><div class="d">전체 ${cnt.total}건</div></div>
      <div class="kc"><div class="k">중대 하자</div><div class="v" style="${cnt.severe?'color:var(--red)':''}">${cnt.severe}<small>건</small></div><div class="d">우선 처리 대상</div></div>
      <div class="kc"><div class="k">기한 초과</div><div class="v" style="${cnt.overdue?'color:var(--red)':''}">${cnt.overdue}<small>건</small></div><div class="d">재시공 지연</div></div>
      <div class="kc ${cnt.disputed?'':'gold'}"
           style="${cnt.disputed?'border:1.5px solid var(--amber)':''}">
        <div class="k">귀책 이의</div>
        <div class="v">${cnt.disputed_all}<small>건</small></div>
        <div class="d">협력사 이의 — 사람이 재검토</div></div>
    </div>
    <div class="panel">
      <div style="background:#FFFBF3;border:1px solid #F5DCB2;border-radius:12px;padding:12px 15px;font-size:.76rem;color:#7A5410;font-weight:600;margin-bottom:14px">
        🔧 보험사에 <b>"하자 시 재시공 책임 주선"</b>을 약속했습니다. 접수 → 확인 → 재시공 배정 → 완료 흐름으로 관리하며,
        하자보증 기간 내 건은 <b>시행사 비용 부담</b>입니다. 비용 부담이 <b>시행사</b>로 확정된 완료 건만 해당 업체 평점에서 차감됩니다(중대 0.2 · 보통 0.1점).
      </div>
      <div class="ph"><span class="pt">하자 목록 <small>${data.length}건</small></span>
        <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
          <div class="filters">${['전체',...DEFECT_FLOW].map(f=>`<span class="fc ${f===defectFilter?'on':''}" data-act="setDefectFilter" data-arg="${esc(f)}">${f}</span>`).join('')}</div>
          ${/*  ⚠ 하자가 전화·메일로 들어오면 시스템에 넣을 창구가 없었다. 보험사가
                 포털로 올린 것만 존재했고, 나머지는 운영자 머릿속에만 남았다. */''}
          <button class="btn p sm" data-act="defectNew">+ 하자 접수</button>
          ${xlsxBtn('defects','하자·A/S')}
        </div>
      </div>
      ${searchBar('defects',{ph:'하자번호·접수번호·발주처·업체·제목', categories:ALL_MAJORS})}
      <div class="tbl-wrap"><table class="tbl">
        <tr><th>하자번호</th><th style="min-width:210px">사건 <span class="hint" style="font-weight:600">— 어떤 공사였나</span></th><th>보험사</th><th>제목</th><th>심각도</th><th>시행사</th><th>보증</th><th>기한</th><th>상태</th><th class="r">액션</th></tr>
        ${data.length?data.map(d=>{
          const od = d.due_date && d.due_date < todayKST() && d.status!=='완료';
          return `<tr>
          <td class="em">${esc(d.defect_no)}</td>
          <td>${caseBrief(d)}</td><td>${esc(d.insurer||'-')}</td>
          <td>${esc(d.title)}${d.dispute_reason?' <span class="pill amber" title="협력사 귀책 이의">이의</span>':''}
            ${d.marked_photos?`<span class="pill ${d.fixed_photos>=d.marked_photos?'green':'red'}"
               title="보험사가 지적한 사진 ${d.marked_photos}곳 중 보수 사진 ${d.fixed_photos||0}곳">📷 ${d.fixed_photos||0}/${d.marked_photos}</span>`:''}</td>
          <td><span class="pill ${d.severity==='중대'?'red':d.severity==='보통'?'amber':'gray'}">${esc(d.severity)}</span></td>
          <td>${esc(d.partner_name||'-')}</td>
          <td>${d.warranty_left===null?'-':(d.warranty_left>=0?`<span class="pill green">${d.warranty_left}일</span>`:'<span class="pill red">만료</span>')}</td>
          <td style="${od?'color:var(--red);font-weight:800':''}">${esc(d.due_date||'-')}${od?' ⚠':''}</td>
          <td>${statusPill(d.status)}</td>
          <td class="r"><button class="btn g sm" data-act="defectDetail" data-arg="${d.id}">처리</button></td></tr>`;}).join('')
          :'<tr><td colspan="10" class="empty">해당 하자가 없습니다</td></tr>'}
      </table></div>
    </div>`;
  window._defects = data;
};
function setDefectFilter(f){ defectFilter=f; VIEWS.defects(); }

//  운영자 하자 접수 — 전화·메일·현장 연락으로 들어온 하자를 시스템에 넣는다.
//   서버(POST /api/defects)는 이미 관리자 접수를 지원한다(reporter_type='내부').
//   보증기간·기한(7일)·하자번호 채번도 서버가 한다 — 화면은 사건과 내용만 받는다.
async function defectNew(){
  openModal(`<h3>하자 접수 <span style="font-weight:400;font-size:.8rem;color:var(--faint)">운영팀 대리 접수</span></h3>
    <div class="msub">전화·메일로 들어온 하자를 기록합니다. 접수하면 배정된 시행사에 통지됩니다.</div>
    <div class="field"><label>사건 *</label>
      <input id="dn_q" placeholder="접수번호·발주처·업체로 검색 (예: 26-80145)"
             data-act-input="defectNewSearch" autocomplete="off">
      <div id="dn_hits" class="msub" style="max-height:190px;overflow:auto;margin-top:6px"></div>
      <div id="dn_pick" style="margin-top:6px"></div></div>
    <div class="field"><label>하자 제목 *</label>
      <input id="dn_title" placeholder="예: 우천 시 이음부 누수 재발" autocomplete="off"></div>
    <div class="field"><label>심각도</label>
      <select id="dn_sev"><option>보통</option><option>중대</option><option>경미</option></select></div>
    <div class="field"><label>내용</label>
      <textarea id="dn_content" placeholder="누가 언제 어떻게 알려 왔는지, 증상과 위치를 적어 주세요."></textarea></div>
    <div class="modal-foot">
      <button class="btn p" id="dn_ok" data-act="defectNewSubmit" disabled>하자 접수</button>
      <span style="flex:1"></span><button class="btn g" data-act="closeModal">취소</button>
    </div>`);
  window._dnCase = null;
}
let _dnTimer = null;
function defectNewSearch(v){
  clearTimeout(_dnTimer);
  _dnTimer = setTimeout(async ()=>{
    const q = (v||'').trim();
    const box = $('#dn_hits'); if(!box) return;
    if(q.length < 2){ box.innerHTML = '<span class="sub">두 글자 이상 입력해 주세요.</span>'; return; }
    try{
      //  하자는 시공이 끝난 건에 생긴다 — 완료·정산진행 건만 고르게 한다.
      const list = (await api('GET','/api/cases?q='+encodeURIComponent(q)))
        .filter(c=>['완료','정산진행','검수대기'].includes(c.status)).slice(0,8);
      box.innerHTML = list.length ? list.map(c=>`
        <div class="bi" style="padding:8px 10px;cursor:pointer;border-bottom:1px solid var(--mist)"
             data-act="defectNewPick" data-arg="${c.id}">
          <b>${esc(c.case_no)}</b> · ${esc(c.category||'')} · ${esc(c.region||'')}
          <div class="sub">${esc(c.insurer||'')} → ${esc(c.partner_name||'업체 미정')} · ${statusPill(c.status)}</div>
        </div>`).join('')
        : '<span class="sub">시공이 끝난 사건 중에는 없습니다. (완료·정산진행·검수대기 건만 접수할 수 있습니다)</span>';
      window._dnHits = list;
    }catch(e){ box.innerHTML = `<span class="sub" style="color:var(--red)">${esc(e.message)}</span>`; }
  }, 250);
}
function defectNewPick(id){
  const c = (window._dnHits||[]).find(x=>x.id===Number(id)); if(!c) return;
  window._dnCase = c;
  $('#dn_hits').innerHTML = '';
  $('#dn_pick').innerHTML = `<div class="notice">선택: <b>${esc(c.case_no)}</b> · ${esc(c.category||'')} ·
    ${esc(c.address||c.region||'')} · 시행사 <b>${esc(c.partner_name||'미정')}</b></div>`;
  const b = $('#dn_ok'); if(b) b.disabled = false;
}
async function defectNewSubmit(){
  const c = window._dnCase;
  if(!c){ toast('사건을 먼저 고르세요.'); return; }
  const title = ($('#dn_title').value||'').trim();
  if(!title){ toast('하자 제목을 적어 주세요.'); return; }
  try{
    await api('POST','/api/defects',{case_id:c.id, title,
      severity:$('#dn_sev').value, content:($('#dn_content').value||'').trim()});
    closeModal();
    toast(`<b>${esc(c.case_no)}</b> 하자를 접수했습니다. 시행사에 통지됩니다.`);
    refreshBadges(); VIEWS.defects();
  }catch(e){ toast(e.message); }
}
//  하자 목록의 「사건」 칸 — 접수번호만 있으면 어떤 현장인지 알 수 없어 하나씩 열어 봐야 했다.
//  공종 · 지역/현장 · 공사금액을 한 줄씩 붙여 목록에서 바로 식별하게 한다.
function caseBrief(d){
  const addr = (d.case_address||'').trim();
  const place = addr || d.case_region || '';
  return `<div style="font-weight:800;color:var(--blue)">${esc(d.case_no||'-')}</div>
    <div style="font-size:.72rem;color:var(--sub);line-height:1.5">
      ${d.case_category?`<b>${esc(d.case_category)}</b>`:''}${d.case_category&&place?' · ':''}
      ${place?`<span title="${esc(place)}">${esc(place.length>26?place.slice(0,26)+'…':place)}</span>`:''}
    </div>
    ${d.case_amount?`<div style="font-size:.7rem;color:var(--faint)">공사금액 ${won(d.case_amount)}원${
      d.case_completed_at?` · 완료 ${esc(String(d.case_completed_at).slice(0,10))}`:''}</div>`:''}`;
}
function defectDetail(id){
  const d = (window._defects||[]).find(x=>x.id===id); if(!d)return;
  const done = d.status==='완료';
  openModal(`<h3>${esc(d.title)}</h3>
    <div class="msub">${esc(d.defect_no)} · 사건 ${esc(d.case_no)} · 접수 ${esc((d.created_at||'').slice(0,16))}</div>
    <div class="kv"><span class="k">보험사</span><span class="v">${esc(d.insurer||'-')} (신고: ${esc(d.reporter||'-')})</span></div>
    <div class="kv"><span class="k">시행사</span><span class="v">${esc(d.partner_name||'-')}</span></div>
    <div class="kv"><span class="k">공종·지역</span><span class="v">${esc(d.category||'-')} · ${esc(d.region||'-')}</span></div>
    <div class="kv"><span class="k">심각도</span><span class="v"><span class="pill ${d.severity==='중대'?'red':d.severity==='보통'?'amber':'gray'}">${esc(d.severity)}</span></span></div>
    <div class="kv"><span class="k">하자보증</span><span class="v">${d.warranty_left===null?'정보 없음':(d.warranty_left>=0?`잔여 ${d.warranty_left}일 — <b style="color:var(--green)">시행사 부담</b>`:'<b style="color:var(--red)">기간 만료 — 비용 협의 필요</b>')}</span></div>
    <div class="field" style="margin-top:6px"><label>비용 부담(귀책) <small style="color:var(--faint)">— 위 판정은 보증기간만 본 초기값입니다. 사진·기록 확인 후 필요하면 조정하세요</small></label>
      <!--  ⚠⚠ [라운드243] 서버(api_defect_update)는 103라운드부터 '보험사'도 정당한
            값으로 검증·저장한다(61라운드: 이의 검토 후 귀책을 보험사로 정하는
            정상 경로) — 그런데 이 드롭다운엔 그 옵션이 없었다. 이미 cost_bearer=
            '보험사' 인 하자를 열면 일치하는 <option> 이 없어 브라우저가 첫 옵션
            (시행사)으로 자동 표시하고, defectAct() 의 "안 바뀌면 안 보낸다" 가드
            (89라운드, 아래 3802행 부근)가 이 값을 절대 "시행사"와 같다고 보지
            않아 다음 상태전이 버튼(확인중·완료·반려 등 무엇이든)을 누를 때마다
            매번 '시행사'로 조용히 되돌리고 있었다 — 보험사 귀책으로 이미 결론난
            건이 협력사 평점 차감(refresh_partner_rating)까지 다시 맞을 수 있었다. -->
      <select id="d_cb">
        <option value="시행사"${d.cost_bearer==='시행사'?' selected':''}>시행사 부담</option>
        <option value="보험사"${d.cost_bearer==='보험사'?' selected':''}>보험사 부담</option>
        <option value="협의필요"${d.cost_bearer==='협의필요'?' selected':''}>협의필요</option>
      </select></div>
    <div class="kv"><span class="k">처리 기한</span><span class="v">${esc(d.due_date||'-')}</span></div>
    <div class="kv"><span class="k">현재 상태</span><span class="v">${statusPill(d.status)}</span></div>
    ${d.dispute_reason?`<div class="notice" style="margin-top:12px;border-left:3px solid var(--amber)">
      <b>⚖ 협력사 귀책 이의</b> <span class="msub">(${esc((d.disputed_at||'').slice(0,16))})</span><br>
      ${esc(d.dispute_reason)}<br>
      <span style="font-size:.72rem;color:var(--sub)">※ 이의는 귀책을 자동으로 바꾸지 않습니다.
      사진·기록을 확인한 뒤 <b>비용 부담</b>을 조정하거나 그대로 두고 협력사에 회신해 주세요.</span></div>`:''}
    <div class="field" style="margin-top:14px"><label>하자 내용</label><textarea readonly>${esc(d.content||'')}</textarea></div>
    <div class="ph" style="margin-top:6px"><span class="pt" style="font-size:.8rem">📷 하자 사진</span>
      <label class="btn g sm" style="cursor:pointer">사진 첨부<input type="file" accept="image/*" multiple hidden id="d_photo_${id}" data-defphoto="${id}"></label></div>
    <div id="defphotos" class="msub" style="display:flex;gap:8px;flex-wrap:wrap">불러오는 중…</div>
    <div class="field" style="margin-top:10px"><label>조치 내용 ${done?'':'(완료 처리 시 입력)'}</label><textarea id="d_res">${esc(d.resolution||'')}</textarea></div>
    <div class="modal-foot">
      ${/*  ⚠⚠ [337라운드] 이 버튼 5개 전부 PATCH /api/defects/<id> 를 부르고
              그 API 는 require_role(중간관리자, app.py:13846) — 이 화면(하자·A/S
              관리)은 applyRoleMenus() 의 등급게이트(admins·insurers·settle
              등만 제한)에 없어 하위관리자도 그대로 열 수 있었다(205라운드가
              try/catch 는 붙였지만 이 게이트는 못 붙였다). 형제(coActions,
              252라운드)처럼 자격 없으면 버튼 대신 조용히 안내문으로 바꾼다. */''}
      ${myRank()<2 ? '<span class="sub">중간관리자 이상만 처리할 수 있습니다</span>' : (done?`
        ${/*  ⚠ 예전에는 '완료' 가 되면 버튼 4개가 통째로 사라져 되돌릴 입구가 없었다.
               잘못 누른 완료는 지급 게이트를 열어 버리고(열린 하자 0건으로 보인다),
               보험사에는 이미 '재시공 완료' 알림이 나간 뒤다. 되돌릴 문 하나는 남긴다. */''}
        <button class="btn g" data-act="defectAct" data-arg="${d.id}" data-arg2="확인중"
          title="완료를 잘못 눌렀을 때 되돌립니다">완료 취소 · 확인중으로</button>`:`
        <button class="btn g" data-act="defectAct" data-arg="${d.id}" data-arg2="확인중">확인중</button>
        <button class="btn a" data-act="defectAct" data-arg="${d.id}" data-arg2="재시공배정">재시공 배정</button>
        <button class="btn p" data-act="defectAct" data-arg="${d.id}" data-arg2="완료">완료 처리</button>
        <button class="btn g" data-act="defectAct" data-arg="${d.id}" data-arg2="반려">반려</button>`)}
      <span style="flex:1"></span><button class="btn g" data-act="closeModal">닫기</button>
    </div>`);
  loadDefectPhotos(id);
  const inp = document.getElementById('d_photo_'+id);
  if(inp) inp.addEventListener('change', ()=>uploadDefectPhotos(id, inp));
}
async function loadDefectPhotos(did){
  const box=$('#defphotos'); if(!box) return;
  try{
    const r = await api('GET','/api/defects/'+did+'/photos');
    //  응답이 배열에서 객체로 바뀌었다(첨부 + 지적). 옛 형태도 받아 준다.
    const ps = Array.isArray(r) ? r : (r.items || []);
    const marked = Array.isArray(r) ? [] : (r.marked || []);
    const thumb = (p, red) => `<a href="/api/photos/${p.id}/file" target="_blank"
        title="${esc(p.note || p.orig_name || '')}">
      <img src="/api/photos/${p.id}/file" style="width:78px;height:78px;object-fit:cover;
        border-radius:8px;border:${red?'2.5px solid var(--red)':'1px solid var(--line)'}"></a>`;
    //  ★ 지적 아래에 **그 자리를 고친 사진**을 붙여 보여준다. 검수자가 대조 없이
    //    "완료 처리"를 누르면 하자 절차가 형식으로 죽는다.
    box.innerHTML =
      (marked.length ? `<div style="width:100%;font-size:.76rem;font-weight:800;color:var(--red);
          margin-bottom:5px">🔴 보험사가 지적한 사진 ${marked.length}장 — 보수 완료 ${r.fixed_count||0}곳</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;width:100%;margin-bottom:10px">
          ${marked.map(p=>{const fx=(p.fixes||[])[0];
            return `<div style="width:166px;display:flex;gap:5px">
            <div style="width:78px">${thumb(p, true)}
              <div style="font-size:.66rem;color:var(--red);line-height:1.35;margin-top:2px">
                ${esc((p.note||'사유 미기재').slice(0,28))}</div></div>
            <div style="width:78px">${fx
              ? `<a href="${esc(fx.url)}" target="_blank" title="보수: ${esc(p.note||'')}">
                   <img src="${esc(fx.url)}" style="width:78px;height:78px;object-fit:cover;
                     border-radius:8px;border:2.5px solid #1F8A55"></a>
                 <div style="font-size:.66rem;color:#1F8A55;margin-top:2px">보수 완료</div>`
              : `<div style="width:78px;height:78px;border-radius:8px;border:1px dashed var(--line);
                   display:grid;place-items:center;font-size:.62rem;color:var(--faint);text-align:center">보수<br>사진<br>없음</div>`}
            </div></div>`;}).join('')}
        </div>` : '')
      + (ps.length ? ps.map(p => thumb(p, false)).join('')
         : (marked.length ? '' : '<span class="sub">첨부된 사진이 없습니다. 어떤 하자인지 사진으로 남겨 주세요.</span>'));
    if(window.Lightbox) Lightbox.bind(box, {caption: img =>
      (img.closest('a') && img.closest('a').title) ? `<b>${esc(img.closest('a').title)}</b>` : ''});
  }catch(e){ box.textContent='사진을 불러오지 못했습니다.'; }
}
async function uploadDefectPhotos(did, input){
  if(!input.files || !input.files.length) return;
  const fd = new FormData();
  for(const f of input.files){ if(f.size<=8*1024*1024) fd.append('photos', f); }
  //  ⚠ [라운드77] createCase() 와 같은 이유 — 이 구간이 도는 동안은 세션만료로
  //    인한 강제이동을 미룬다.
  UP_BUSY = true;
  try{
    const r = await fetch('/api/defects/'+did+'/photos', {method:'POST', headers:{'X-CSRF-Token':CSRF}, credentials:'same-origin', body:fd});
    const d = await r.json();
    if(!r.ok){ toast(d.error||'업로드 실패'); return; }
    toast(`사진 ${d.count}장 첨부`); input.value=''; loadDefectPhotos(did);
  }catch(e){ toast('업로드 실패'); }
  finally { UP_BUSY = false; }
}
async function defectAct(id, status){
  const res = $('#d_res') ? $('#d_res').value : undefined;
  //  ⚠⚠ [라운드89] 귀책(cost_bearer)을 바꿀 수 있는 화면 입구가 여기 말고 아예
  //    없었다 — 서버(api_defect_update)는 이미 이 필드를 완전히 지원하는데,
  //    이의 알림 문구는 "비용 부담을 조정하세요" 라고 담당자에게 말해 놓고
  //    실제로 조정할 셀렉트박스가 화면에 없었다. 값이 안 바뀌었으면 안 보낸다 —
  //    서버가 "cost_bearer in d" 를 "담당자가 방금 정했다"는 신호로 쓰기 때문에
  //    바뀌지도 않은 값을 매번 보내면 관련 없는 상태전이에도 이의가 "검토완료"로
  //    잘못 닫힌다.
  const d = (window._defects||[]).find(x=>x.id===id);
  const cbSel = $('#d_cb');
  const cb = cbSel ? cbSel.value : undefined;
  //  ⚠ '확인중'을 이미 확인중인 하자에 다시 눌러 귀책만 고치는 경우 — 서버는
  //    상태가 안 바뀌면(=status===row.status) 다른 필드는 보지도 않고 조용히
  //    끝낸다. status 를 아예 안 보내면 그 지름길을 안 타고 귀책·조치내용이
  //    정상적으로 반영된다(다른 경로의 상태전이 로직은 그대로다).
  const unchanged = d && status === d.status;
  //  ⚠ '완료'·'반려'는 누르는 즉시 보험사에 통지가 나가고 평점이 다시 계산된다.
  //     특히 '완료'는 지급 관문을 열어 이체가 나갈 수 있게 만든다 — 한 번 되묻는다.
  const NL = String.fromCharCode(10);
  if(status==='완료' && !confirm('하자를 완료로 닫습니다.' + NL + NL
      + '· 보험사에 「재시공 완료」가 통보됩니다' + NL
      + '· 이 하자 때문에 잡혀 있던 지급 보류가 풀립니다' + NL
      + '· 업체 평점이 다시 계산됩니다' + NL + NL + '진행할까요?')) return;
  if(status==='반려' && !confirm('이 하자 접수를 반려합니다.' + NL
      + '보험사에 반려 사실이 전달됩니다. 진행할까요?')) return;
  //  '확인중'은 접수 직후에도 누르는 정상 동작이다 — **완료를 되돌릴 때만** 묻는다.
  //  (지금 열린 모달에 '완료 취소' 버튼이 있다 = 이 하자는 완료 상태다)
  const reverting = status==='확인중' && !!document.querySelector(
      '.modal [data-act="defectAct"][data-arg2="확인중"][title]');
  if(reverting && !confirm('완료를 취소하고 「확인중」으로 되돌립니다.' + NL
      + '지급 보류가 다시 걸릴 수 있습니다. 진행할까요?')) return;
  const body = {resolution: res};
  if (!unchanged) body.status = status;
  if (cb && d && cb !== d.cost_bearer) body.cost_bearer = cb;
  //  ⚠⚠ [라운드205] 형제(appAct, 1009행)는 "콘솔의 다른 변경 동작은 전부
  //    try/catch + toast 로 감싸져 있다"고 스스로 적어 뒀지만 여기는 빠져
  //    있었다 — 이 액션의 API(/api/defects/<id>)는 require_role("중간관리자")
  //    인데 이 화면(하자·A/S 관리) 메뉴는 applyRoleMenus() 의 등급게이트
  //    (admins·insurers·set 만 제한)에 없어 하위관리자도 그대로 열 수 있다.
  //    하위관리자가 완료·반려·재시공배정을 누르면 서버가 403 을 주는데 여기
  //    try/catch 가 없어 unhandled rejection 으로 끝나 모달도 안 닫히고
  //    아무 안내도 없다 — 특히 '완료'는 지급 보류를 푸는 액션이다(3744행).
  try{
    await api('PATCH','/api/defects/'+id, body);
  }catch(e){
    //  ⚠⚠ [라운드501] 형제(settleVoid 등, 라운드481·486·500)가 이미 세운
    //    원칙 — 성공 분기(바로 아래 closeModal·refreshBadges·VIEWS.defects)
    //    만 화면을 정리하면, 동시에 다른 관리자가 먼저 상태를 바꿔 여기가
    //    막히는 흔한 경우(app.py DEFECT_BAD_TRANSITION 409)에 이 모달만
    //    옛 상태로 계속 열려 있는다. catch도 성공 분기와 같이 정리한다.
    toast(e.message || '처리하지 못했습니다.'); closeModal(); refreshBadges(); VIEWS.defects(); return;
  }
  closeModal();
  //  ⚠ 실발송 스위치(BOKGUON_NOTIFY_ENABLED)가 꺼진 지금은 발송대기 큐에만
  //    쌓인다. 하자 재시공은 기한이 걸린 작업이라, 나가지도 않은 알림톡을
  //    "발송" 이라고 적으면 운영자가 연락을 안 한다. 같은 콘솔의 리마인드
  //    안내문은 이미 이 사실을 정직하게 적어 두었다 — 문구를 맞춘다.
  //  ⚠⚠ 여기는 **템플릿 리터럴 밖**이다. `${/* */''}` 주석을 쓰면 구문 오류가 난다
  //    (이 파일에서 이미 세 번 저지른 실수다 — node --check 가 잡았다).
  toast(status==='재시공배정'?'재시공이 <b>배정</b>되었습니다 — 시행사 포털 알림 등록(문자·알림톡은 발송사 연동 후)'
    :status==='완료'?'하자 처리 <b>완료</b> — 보험사 통보 및 업체 평점 반영'
    :`하자 <b>${status}</b> 처리됨`);
  refreshBadges(); VIEWS.defects();
}

// ── AI 사진 검수 (실데이터) ──────────────────────────────
const PHOTO_KINDS = ['착공전','시공중','완료','영수증','기타'];
const PK_LABEL = {'착공전':'착공 전','시공중':'시공 중','완료':'완료','영수증':'영수증','기타':'미분류'};

// AI 를 얼마나 믿을지 정하는 칸.
// 신뢰도가 기준을 넘은 사진은 담당자를 거치지 않고 바로 승인된다.
// 기준을 올리면 사람 손이 늘고, 내리면 오분류가 새어나간다.
// 그래서 '지금 기준에서 AI 가 실제로 얼마나 맞았는지'를 같이 보여준다.
function aiTrustPanel(st){
  const accu = st.accuracy == null ? '—' : st.accuracy + '%';
  const autoPct = st.total ? Math.round(st.auto_approved*100/st.total) : 0;
  const opts = [70,75,80,85,90,95,100].map(v=>
    `<option value="${v}"${v===st.threshold?' selected':''}>${v}점 이상</option>`).join('');
  // 자동 승인 구간(기준 이상)에서 사람이 뒤집은 적이 있으면 그게 바로 위험 신호다
  const risky = (st.bands||[]).find(b => b.band==='90~100' && b.accuracy!=null && b.accuracy < 95);
  return `
    <div style="border:1px solid var(--line);border-radius:14px;padding:15px 17px;margin-bottom:14px;background:#FAFBFD">
      <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;justify-content:space-between;margin-bottom:12px">
        <div style="font-size:.82rem;font-weight:800;color:var(--ink)">🎯 AI 자동 승인 기준
          <small style="display:block;font-weight:600;color:var(--muted);margin-top:3px">
            신뢰도가 기준을 넘은 <b>공사 사진</b>만 자동 승인됩니다. 영수증·기타는 항상 담당자가 확인합니다.</small></div>
        <div style="display:flex;gap:8px;align-items:center">
          <select id="ai_th" data-act-change="aiSetTh" style="width:auto">${opts}</select>
        </div>
      </div>
      <div class="krow k4">
        <div class="kc"><div class="k">AI 판정 정확도</div><div class="v">${accu}</div>
          <div class="d">사람 판단과 일치한 비율 (${st.total}건 기준)</div></div>
        <div class="kc"><div class="k">자동 승인</div><div class="v">${st.auto_approved}<small>장</small></div>
          <div class="d">전체의 ${autoPct}% — 담당자 손이 안 간 분량</div></div>
        <div class="kc"><div class="k">담당자 검수</div><div class="v">${st.human_reviewed}<small>장</small></div></div>
        <div class="kc"><div class="k">검수 대기</div><div class="v">${st.pending}<small>장</small></div></div>
      </div>
      ${(st.bands||[]).length ? `
        <div class="tbl-wrap" style="margin-top:12px"><table class="tbl">
          <tr><th>AI 신뢰도 구간</th><th class="r">판정 건수</th><th class="r">사람과 일치</th><th>처리</th></tr>
          ${st.bands.map(b=>`<tr>
            <td class="em">${esc(b.band)}점</td>
            <td class="r">${b.n}</td>
            <td class="r">${b.accuracy==null?'—':b.accuracy+'%'}</td>
            <td>${parseInt(b.band) >= st.threshold
                  ? '<span style="color:var(--green);font-weight:700">자동 승인</span>'
                  : '<span style="color:var(--muted)">담당자 확인</span>'}</td>
          </tr>`).join('')}
        </table></div>` : `
        <div style="margin-top:11px;font-size:.75rem;color:var(--muted)">
          아직 판정 기록이 쌓이지 않았습니다. 사진이 검수될수록 정확도가 채워집니다.</div>`}
      ${risky ? `
        <div style="margin-top:11px;background:var(--amber-bg);border:1px solid #F5DCB2;border-radius:10px;
                    padding:11px 14px;font-size:.76rem;color:#7A5410;font-weight:700">
          ⚠ 자동 승인 구간에서도 담당자가 뒤집은 건이 있습니다(일치 ${risky.accuracy}%).
          기준을 올려 사람 확인을 늘리는 편이 안전합니다.</div>` : ''}
    </div>`;
}

// ══════════════════════════════════════════════════════════════
//  현장 지도 — 사건과 인근 시행·시공사를 한 화면에서
//
//  좌표는 시군구 중심의 개략값이다(geo.py). 정밀 위치가 아니라 '배치'이며,
//  화면에도 그렇게 적는다 — 지도가 정밀한 척하면 현장에서 신뢰를 잃는다.
// ══════════════════════════════════════════════════════════════
let MAP = null, MAP_LAYERS = {cases:null, partners:null};
const MAP_COLORS = {'접수':'#8496A6','입찰중':'#0064B2','수배중':'#E8A33D','승인대기':'#7A4FBF',
  '시공중':'#C9852A','검수대기':'#B26A00','정산진행':'#137A38','완료':'#137A38',
  '유찰':'#C0392B','미수선종결':'#4A5B6C'};

VIEWS.map = async () => {
  const st = searchState('map');
  $('#content').innerHTML = `
    <div class="panel">
      <div class="ph"><span class="pt">현장 지도 <small id="map-count"></small></span>
        <span style="flex:1"></span>
        <select id="map-status" style="width:auto" data-act-change="mapReload">
          ${['전체','접수','입찰중','수배중','승인대기','시공중','검수대기','정산진행','완료'].map(s=>`<option ${st.status===s?'selected':''}>${s}</option>`).join('')}
        </select>
        <select id="map-cat" style="width:auto" data-act-change="mapReload">
          <option value="전체">공종 전체</option>
          ${ALL_MAJORS.map(c=>`<option ${st.category===c?'selected':''}>${esc(c)}</option>`).join('')}
        </select>
        <select id="map-ptype" style="width:auto" data-act-change="mapReload"
                title="업체 유형만 골라 보면 분포가 한눈에 들어옵니다">
          ${['업체 전체','시행사만','시공사만','업체 숨김'].map(s=>
            `<option ${(st.ptype||'업체 전체')===s?'selected':''}>${s}</option>`).join('')}
        </select>
      </div>
      <div class="hint" style="margin-bottom:8px">표시 위치는 <b>시군구 중심의 개략값</b>입니다. 정밀 위치는 사건 상세에서 좌표를 직접 입력하면 그 자리로 옮겨집니다.</div>
      <div id="themap" style="height:calc(100vh - 250px);min-height:420px;border-radius:12px;border:1px solid var(--line)"></div>
      <div class="hint" style="margin-top:8px;display:flex;gap:14px;flex-wrap:wrap;align-items:center">
        <span><span style="display:inline-block;width:0;height:0;border-left:6px solid transparent;
          border-right:6px solid transparent;border-bottom:11px solid #004E8C;
          vertical-align:-1px"></span> <b>시행사</b></span>
        <span><span style="display:inline-block;width:11px;height:11px;border-radius:50%;
          background:#C9852A;border:1.5px solid #fff;box-shadow:0 0 0 1px #ccc;
          vertical-align:-1px"></span> <b>시공사</b></span>
        <span style="opacity:.65">흐린 색 = 건설업 등록 미확인</span>
        <span><span style="display:inline-block;width:17px;height:17px;border-radius:50%;
          background:#C9852A;color:#fff;font:800 9px sans-serif;text-align:center;
          line-height:17px;vertical-align:-4px">7</span> 같은 지역 여러 곳(눌러서 목록)</span>
        <span style="margin-left:auto;opacity:.7">지도 © OpenStreetMap contributors</span>
      </div>
      <div id="map-nogeo" class="hint" style="display:none;margin-top:8px;
        background:var(--amber-bg);border:1px solid #F5DCB2;color:#7A5410"></div>
    </div>`;
  // 지도는 한 번 만들고 데이터만 갈아끼운다(매번 새로 만들면 화면이 튄다)
  if(MAP){ MAP.remove(); MAP = null; }
  MAP = L.map('themap').setView([36.5, 127.8], 7);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    {maxZoom: 18, attribution: '© OpenStreetMap'}).addTo(MAP);
  await mapReload();
};

async function mapReload(){
  if(!MAP) return;
  const st = searchState('map');
  st.status = ($('#map-status')||{}).value || '전체';
  st.category = ($('#map-cat')||{}).value || '전체';
  const qs = new URLSearchParams();
  if(st.status && st.status!=='전체') qs.set('status', st.status);
  if(st.category && st.category!=='전체') qs.set('category', st.category);
  const d = await api('GET','/api/map/cases'+(qs.toString()?'?'+qs:''));
  ['cases','partners'].forEach(k=>{ if(MAP_LAYERS[k]){ MAP.removeLayer(MAP_LAYERS[k]); MAP_LAYERS[k]=null; } });

  // 사건 — 상태색 원형 마커
  const cg = L.layerGroup();
  (d.cases||[]).forEach(c=>{
    //  ⚠ '수배중'은 c.status 값이 아니라 c.dispatch_status 값이다(서버가 같은
    //    이유로 필터 컬럼을 가른 것과 같다) — status 로만 찾으면 항상 못 찾아
    //    기본색(회색)으로만 찍혔다.
    const _mst = c.dispatch_status === '수배중' ? '수배중' : c.status;
    const m = L.circleMarker([c.lat, c.lng], {
      radius: 9, weight: 2, color: '#fff',
      fillColor: MAP_COLORS[_mst]||'#8496A6', fillOpacity: .92});
    m.bindPopup(`<div style="font-family:'Malgun Gothic',sans-serif;min-width:190px">
      <b>${esc(c.case_no)}</b> <span style="font-size:.75rem;color:#666">(${esc(c.status)})</span><br>
      <span style="font-size:.8rem">${esc(c.category||'')} · ${esc(c.region||'')}</span><br>
      <span style="font-size:.74rem;color:#888">담당 ${esc(c.manager||'-')} · ${esc(c.partner_name||'업체 미정')}</span><br>
      <span style="font-size:.7rem;color:#aaa">${esc(c.geo_src||'')}</span><br>
      <a href="#" data-act="mapOpenCase" data-arg="${c.id}" style="font-size:.78rem;font-weight:700">사건 상세 열기 →</a></div>`);
    cg.addLayer(m);
  });
  cg.addTo(MAP); MAP_LAYERS.cases = cg;

  // 협력사 — 시행사 ▲ 파랑 / 시공사 ● 주황.
  //  같은 시군구 업체가 한 점에 겹쳐 서로 가리던 문제가 있었다.
  //  좌표가 같은 무리는 하나의 '묶음 표식(개수)'으로 그리고, 누르면 목록이 열린다.
  //  (좌표를 지어내 흩뜨리면 지도가 거짓말을 하게 되므로, 겹친다는 사실을 그대로 보여준다)
  st.ptype = ($('#map-ptype')||{}).value || '업체 전체';
  if(st.ptype !== '업체 숨김'){
    const shown = (d.partners||[]).filter(p=>
      st.ptype === '시행사만' ? p.type === '시행사'
      : st.ptype === '시공사만' ? p.type !== '시행사'
      : true);
    const pg = L.layerGroup();
    const bucket = {};
    shown.forEach(p=>{
      const k = p.lat.toFixed(3)+','+p.lng.toFixed(3);
      (bucket[k] = bucket[k] || []).push(p);
    });
    Object.values(bucket).forEach(list=>{
      const p = list[0];
      if(list.length > 1){
        // 묶음 — 시행사가 하나라도 있으면 파랑 테두리로 알린다
        const prime = list.some(x=>x.type==='시행사');
        const ic = L.divIcon({className:'', iconSize:[30,30], iconAnchor:[15,15],
          html:`<div style="width:28px;height:28px;border-radius:50%;
            background:${prime?'#004E8C':'#C9852A'};color:#fff;border:2.5px solid #fff;
            box-shadow:0 1px 5px rgba(0,0,0,.35);display:grid;place-items:center;
            font:800 11px 'Malgun Gothic',sans-serif">${list.length}</div>`});
        const m = L.marker([p.lat, p.lng], {icon: ic});
        const rows = list.slice(0, 40).map(x=>`
          <div style="padding:4px 0;border-bottom:1px solid #eee;font-size:.76rem">
            <b>${esc(x.name)}</b>
            <span style="color:${x.type==='시행사'?'#004E8C':'#C9852A'};font-weight:700">
              ${x.type==='시행사'?'▲':'●'} ${esc(x.type)}</span><br>
            <span style="color:#888;font-size:.72rem">${esc(x.category||'')} ·
              건설업 ${esc(x.license)} · 이행 ${x.jobs||0}건</span></div>`).join('');
        m.bindPopup(`<div style="font-family:'Malgun Gothic',sans-serif;min-width:230px">
          <b style="font-size:.9rem">${esc(p.region||'이 지역')} ${list.length}개사</b>
          <div style="font-size:.7rem;color:#999;margin:2px 0 6px">
            시행 ${list.filter(x=>x.type==='시행사').length} ·
            시공 ${list.filter(x=>x.type!=='시행사').length}</div>
          <div style="max-height:240px;overflow:auto">${rows}</div>
          ${list.length>40?`<div style="font-size:.7rem;color:#999;padding-top:5px">
            외 ${list.length-40}개사 — 업체 목록에서 확인하세요</div>`:''}</div>`,
          {maxWidth: 300});
        pg.addLayer(m);
      }else{
        const prime = p.type==='시행사';
        const licensed = p.license==='등록확인';
        // 시행사는 위로 뾰족한 삼각형(파랑), 시공사는 원(주황).
        // 건설업 등록이 확인된 곳은 진하게·테두리를 줘서 한눈에 갈린다.
        const ic = L.divIcon({className:'', iconSize:[18,18], iconAnchor:[9,9],
          html: prime
            ? `<div style="width:0;height:0;border-left:9px solid transparent;
                 border-right:9px solid transparent;
                 border-bottom:16px solid ${licensed?'#004E8C':'#9DB6CB'};
                 filter:drop-shadow(0 1px 2px rgba(0,0,0,.4))"></div>`
            : `<div style="width:14px;height:14px;border-radius:50%;
                 background:${licensed?'#C9852A':'#E3D2B4'};
                 border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.35)"></div>`});
        const m = L.marker([p.lat, p.lng], {icon: ic, title: p.name});
        m.bindPopup(`<div style="font-family:'Malgun Gothic',sans-serif;min-width:180px">
          <b>${esc(p.name)}</b>
          <span style="color:${prime?'#004E8C':'#C9852A'};font-weight:800;font-size:.74rem">
            ${prime?'▲':'●'} ${esc(p.type)}</span><br>
          <span style="font-size:.78rem">${esc(p.category||'')} · ${esc(p.region||'')}</span><br>
          <span style="font-size:.74rem;color:#888">건설업 ${esc(p.license)} ·
            평점 ${p.rating||'-'} · 이행 ${p.jobs||0}건</span><br>
          <span style="font-size:.68rem;color:#aaa">${esc(p.geo_src||'')}</span></div>`);
        pg.addLayer(m);
      }
    });
    pg.addTo(MAP); MAP_LAYERS.partners = pg;
  }
  const el = $('#map-count');
  const P = d.partners||[];
  if(el) el.textContent = `사건 ${d.cases.length}건 · 협력사 ${P.length}개사`
    + ` (시행 ${P.filter(x=>x.type==='시행사').length} · 시공 ${P.filter(x=>x.type!=='시행사').length})`
    + (d.no_coords ? ` · 사건 좌표 미해석 ${d.no_coords}건` : '')
    + (d.partner_no_coords ? ` · 업체 위치 미상 ${d.partner_no_coords}곳` : '');
  // 위치 정보가 아예 없는 업체는 지도에 못 찍는다 — 그렇다고 없는 셈 치면 안 되므로
  // 지도 아래에 이름을 그대로 적어 준다(주소를 채우면 지도로 올라온다).
  const box = $('#map-nogeo');
  if(box){
    const miss = d.partners_no_geo || [];
    box.innerHTML = miss.length ? `
      <b>위치 미상 ${miss.length}곳</b> — 지역·주소가 비어 있어 지도에 찍지 못했습니다.
      업체 등록·관리에서 주소를 채우면 지도에 나타납니다.<br>
      ${miss.map(x=>`<span class="pill" style="margin:3px 4px 0 0">${esc(x.name)}
        <span style="opacity:.6">(${esc(x.type)})</span></span>`).join('')}` : '';
    box.style.display = miss.length ? 'block' : 'none';
  }
}

// ══════════════════════════════════════════════════════════════
//  일정 달력 — 자동 일정(마감·기한·완료·보증만료) + 수동 등록
// ══════════════════════════════════════════════════════════════
let CAL = (()=>{ const t=new Date(); return {y:t.getFullYear(), m:t.getMonth()+1}; })();
const CAL_KIND = {'입찰마감':'blue','출동기한':'red','시공완료':'green','보증만료':'amber','일정':'gray'};

VIEWS.calendar = async () => {
  const d = await api('GET',`/api/calendar?year=${CAL.y}&month=${CAL.m}`);
  const ev = d.events||[];
  const byDate = {};
  ev.forEach(e=>{ (byDate[e.date]=byDate[e.date]||[]).push(e); });
  const first = new Date(CAL.y, CAL.m-1, 1);
  const startDow = first.getDay();
  const days = new Date(CAL.y, CAL.m, 0).getDate();
  const today = (()=>{ const t=new Date(); return `${t.getFullYear()}-${String(t.getMonth()+1).padStart(2,'0')}-${String(t.getDate()).padStart(2,'0')}`; })();
  let cells = '';
  for(let i=0;i<startDow;i++) cells += `<div class="cal-cell off"></div>`;
  for(let day=1; day<=days; day++){
    const ds = `${CAL.y}-${String(CAL.m).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
    const list = byDate[ds]||[];
    cells += `<div class="cal-cell ${ds===today?'today':''}" data-act="calDay" data-arg="${ds}" style="cursor:pointer">
      <div class="cal-d">${day}</div>
      ${list.slice(0,6).map(e=>`<div class="cal-ev ${CAL_KIND[e.kind]||'gray'}" title="${esc(e.title)}">${e.time?e.time+' ':''}${esc(e.title)}</div>`).join('')}
      ${list.length>6?`<div class="cal-more">+${list.length-6}건</div>`:''}
    </div>`;
  }
  $('#content').innerHTML = `
    <style>
      .cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}
      .cal-dow{text-align:center;font-size:.72rem;font-weight:800;color:var(--faint);padding:4px 0}
      .cal-cell{min-height:clamp(165px, calc((100vh - 270px)/6), 280px);background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:8px 8px 6px}
      .cal-cell.off{background:transparent;border:none}
      .cal-cell.today{border-color:var(--blue);box-shadow:0 0 0 2px rgba(0,100,178,.14)}
      .cal-d{font-size:.8rem;font-weight:800;margin-bottom:5px}
      .cal-ev{font-size:.68rem;font-weight:700;padding:3px 7px;border-radius:5px;margin-bottom:3px;
        white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .cal-ev.blue{background:#E6F1FA;color:#004E8C} .cal-ev.red{background:#FBEAE7;color:#C0392B}
      .cal-ev.green{background:#E6F4EA;color:#137A38} .cal-ev.amber{background:#FDF0DC;color:#B26A00}
      .cal-ev.gray{background:var(--mist);color:var(--sub)}
      .cal-more{font-size:.6rem;color:var(--faint)}
    </style>
    <div class="panel">
      <div class="ph">
        <button class="btn g sm" data-act="calMove" data-arg="-1">◀</button>
        <span class="pt" style="min-width:130px;text-align:center">${CAL.y}년 ${CAL.m}월</span>
        <button class="btn g sm" data-act="calMove" data-arg="1">▶</button>
        <button class="btn g sm" data-act="calMove" data-arg="0">오늘</button>
        <span style="flex:1"></span>
        <span class="hint">입찰마감 <span class="cal-ev blue" style="display:inline">■</span> ·
          출동기한 <span class="cal-ev red" style="display:inline">■</span> ·
          완료 <span class="cal-ev green" style="display:inline">■</span> ·
          보증만료 <span class="cal-ev amber" style="display:inline">■</span></span>
        <button class="btn p sm" data-act="calAdd">+ 일정 등록</button>
      </div>
      <div class="cal-grid">
        ${['일','월','화','수','목','금','토'].map(w=>`<div class="cal-dow">${w}</div>`).join('')}
        ${cells}
      </div>
    </div>`;
};

function calMove(dir){
  dir = Number(dir);
  if(dir===0){ const t=new Date(); CAL={y:t.getFullYear(), m:t.getMonth()+1}; }
  else{ CAL.m += dir; if(CAL.m<1){CAL.m=12;CAL.y--;} if(CAL.m>12){CAL.m=1;CAL.y++;} }
  VIEWS.calendar();
}

async function calDay(ds){
  const d = await api('GET',`/api/calendar?year=${CAL.y}&month=${CAL.m}`);
  const list = (d.events||[]).filter(e=>e.date===ds);
  openModal(`<h3>${ds} 일정 <span style="font-weight:400;font-size:.8rem;color:var(--faint)">${list.length}건</span></h3>
    ${list.length?list.map(e=>`<div style="display:flex;gap:8px;align-items:center;padding:9px 12px;border:1px solid var(--line);border-radius:9px;margin-bottom:6px">
      <span class="cal-ev ${CAL_KIND[e.kind]||'gray'}" style="display:inline">${esc(e.kind)}</span>
      <div style="flex:1;font-size:.85rem"><b>${e.time?e.time+' · ':''}${esc(e.title)}</b>
        ${e.detail?`<div class="hint">${esc(e.detail)}</div>`:''}</div>
      ${e.case_id?`<button class="btn g sm" data-act="mapOpenCase" data-arg="${e.case_id}">사건</button>`:''}
      ${/*  ⚠⚠ [339라운드] DELETE /api/schedule-events/<id> 는 require_role(중간관리자,
              app.py:17825, 68라운드가 하위관리자에서 올림) — 이 버튼은 등급 무관하게
              그려져 있었다(등록 자체(POST, 17785행)는 require_role(하위관리자)라
              등급무관이 맞아 calAdd 는 그대로 둔다). */''}
      ${e.event_id && myRank()>=2?`<button class="btn g sm" data-act="calDel" data-arg="${e.event_id}">삭제</button>`:''}
    </div>`).join(''):'<div class="empty">일정 없음</div>'}
    <div class="modal-foot">
      <button class="btn p" data-act="calAdd" data-arg="${ds}">이 날짜에 일정 등록</button>
      <span style="flex:1"></span><button class="btn g" data-act="closeModal">닫기</button>
    </div>`);
}

function calAdd(ds){
  openModal(`<h3>일정 등록</h3>
    <div class="field"><label>제목 *</label><input id="se_title" placeholder="예: ○○보험 정기 미팅"></div>
    <div class="grid2">
      <div class="field"><label>날짜 *</label><input id="se_date" type="date" value="${esc(typeof ds==='string'&&/^\d{4}/.test(ds)?ds:'')}"></div>
      <div class="field"><label>시각(선택)</label><input id="se_time" type="time"></div>
    </div>
    <div class="field"><label>메모</label><input id="se_memo" placeholder="선택 입력"></div>
    <div class="field"><label>사건 번호(선택)</label><input id="se_case" type="number" placeholder="사건 id — 사건에 붙는 일정이면"></div>
    <div class="modal-foot">
      <button class="btn p" data-act="calSave">등록</button>
      <span style="flex:1"></span><button class="btn g" data-act="closeModal">닫기</button>
    </div>`);
}

async function calSave(){
  try{
    await api('POST','/api/schedule-events',{
      title: $('#se_title').value.trim(), event_date: $('#se_date').value,
      event_time: $('#se_time').value, memo: $('#se_memo').value.trim(),
      case_id: $('#se_case').value ? Number($('#se_case').value) : null});
    toast('일정을 등록했습니다'); closeModal(); VIEWS.calendar();
  }catch(e){ toast(e.message); }
}

async function calDel(id){
  if(!confirm('이 일정을 삭제합니다. 되돌릴 수 없습니다. 진행할까요?')) return;
  try{ await api('DELETE','/api/schedule-events/'+id); toast('삭제했습니다'); closeModal(); VIEWS.calendar(); }
  catch(e){ toast(e.message); }
}

// ══════════════════════════════════════════════════════════════
//  해피콜·만족도 — 복구 완료 후 피해자의 목소리 (머큐리 절차의 마지막 단계)
//  '완료됐는데 해피콜이 없는 건'이 이 화면의 핵심이다.
// ══════════════════════════════════════════════════════════════
VIEWS.happycall = async () => {
  const d = await api('GET','/api/happy-calls');
  const stars = n => '★'.repeat(n)+'☆'.repeat(5-n);
  $('#content').innerHTML = `
    <div class="panel">
      <div class="ph"><span class="pt">해피콜·만족도</span>
        <span style="flex:1"></span>
        <span class="hint">평균 ${d.avg??'-'}점 · 누적 ${d.count}건</span></div>
      <div class="ph" style="margin-top:4px"><span class="pt" style="font-size:.85rem;color:var(--amber-text)">📞 해피콜 대기 <small>${d.pending.length}건</small></span></div>
      <div class="tbl-wrap"><table class="tbl">
        <tr><th>접수번호</th><th>공종</th><th>업체</th><th>완료일</th><th>피해자</th><th class="r">액션</th></tr>
        ${d.pending.length?d.pending.map(c=>`<tr>
          <td class="em">${esc(c.case_no)}</td><td>${esc(c.category||'')}</td>
          <td>${esc(c.partner_name||'-')}</td><td>${esc((c.completed_at||'').slice(0,10))}</td>
          <td>${esc(c.victim_name||'-')} ${c.victim_phone?`<span class="hint">${esc(c.victim_phone)}</span>`:'<span class="hint" style="color:var(--red)">연락처 없음</span>'}</td>
          <td class="r"><button class="btn p sm" data-act="hcForm" data-arg="${c.id}" data-arg2="${esc(c.case_no)}">해피콜 기록</button></td>
        </tr>`).join(''):'<tr><td colspan="6" class="empty">대기 건 없음 — 완료 사건에 해피콜이 모두 기록됐습니다</td></tr>'}
      </table></div>
      <div class="ph" style="margin-top:16px"><span class="pt" style="font-size:.85rem">기록 완료 <small>${d.done.length}건</small></span></div>
      <div class="tbl-wrap"><table class="tbl">
        <tr><th>접수번호</th><th>업체</th><th>점수</th><th>의견</th><th>방법</th><th>기록자</th><th>일시</th></tr>
        ${d.done.length?d.done.map(h=>`<tr>
          <td class="em">${esc(h.case_no)}</td><td>${esc(h.partner_name||'-')}</td>
          <td style="color:var(--amber-text);font-weight:800">${stars(h.score)}</td>
          <td style="max-width:280px">${esc(h.feedback||'-')}</td>
          <td>${esc(h.method||'')}</td><td>${esc(h.called_by||'')}</td>
          <td class="hint">${esc((h.created_at||'').slice(0,16))}</td>
        </tr>`).join(''):'<tr><td colspan="7" class="empty">기록 없음</td></tr>'}
      </table></div>
    </div>`;
};

function hcForm(cid, caseNo){
  openModal(`<h3>해피콜 기록 <span style="font-weight:400;font-size:.8rem;color:var(--faint)">${esc(caseNo||'')}</span></h3>
    <div class="msub">피해자에게 전화·문자로 확인한 결과를 기록합니다. 점수는 업체 평점에 곧바로 반영됩니다. (사건당 1회)</div>
    <div class="field"><label>만족도 *</label>
      <select id="hc_score">${[5,4,3,2,1].map(s=>`<option value="${s}">${'★'.repeat(s)+'☆'.repeat(5-s)} (${s}점)</option>`).join('')}</select></div>
    <div class="field"><label>피해자 의견</label><input id="hc_fb" placeholder="예: 빠르게 처리해 주셔서 만족"></div>
    <div class="field"><label>확인 방법</label>
      <select id="hc_m"><option>전화</option><option>문자</option><option>방문</option></select></div>
    <div class="modal-foot">
      <button class="btn p" data-act="hcSave" data-arg="${cid}">기록</button>
      <span style="flex:1"></span><button class="btn g" data-act="closeModal">닫기</button>
    </div>`);
}

async function hcSave(cid){
  try{
    const r = await api('POST',`/api/cases/${cid}/happy-call`,{
      score: Number($('#hc_score').value), feedback: $('#hc_fb').value.trim(),
      method: $('#hc_m').value});
    toast(r.message); closeModal(); VIEWS.happycall();
  }catch(e){ toast(e.message); }
}

// ══════════════════════════════════════════════════════════════
//  현장 출동 수배 관제 — 사진 없이 접수된 사건이 어디까지 갔는가
//
//  운영자가 봐야 하는 것은 두 가지뿐이다.
//   ① 수배가 돌고 있는가   ② 멈춘 건이 있는가(기한 초과·수배 실패)
//  그래서 기한이 지난 건을 맨 위로 올리고, 점검이 살아 있는지도 함께 보여준다.
// ══════════════════════════════════════════════════════════════
//  ⚠⚠ [라운드681] 이 맵은 dispatches.status(dispatch.py ST_OPEN='모집중'·
//    ST_CLAIMED='수배됨'로 실제 배정, app.py 5375행 UPDATE dispatches SET
//    status='취소'로 실제 취소)를 색칠하는 이 파일 유일의 전용 맵인데, 같은
//    필드를 그리는 형제가 하나 더 있다는 걸 이제껏 아무도 대조하지 않았다
//    — templates/insurer_portal.html의 dpCell()→stTag(d.status)(사건
//    목록 dlCell 이 그대로 호출)가 정확히 같은 dispatches.status 값을
//    그린다. round75·644·672·677는 항상 "형제 stTag/statusPill 셋"만
//    맞췄고, admin.js 안에 파묻힌 이 네 번째 미니맵은 비교 대상에 든 적이
//    없었다. 실측 대조 결과 5개 키 중 3개가 형제와 어긋났다: '모집중'
//    (여기 blue ↔ insurer amber), '수배됨'(여기 amber ↔ insurer blue —
//    두 색이 통째로 뒤바뀌어 있었다), '취소'(여기 gray ↔ insurer·partner
//    stTag·admin statusPill 전부 red — 이 저장소 전체에서 '취소'를 회색으로
//    두는 유일한 자리였다. round75 자신이 세운 원칙 "매핑에 없으면 회색이니
//    취소는 구분돼야 한다"를 정작 이 넷째 맵에는 못 지켰다). 그 결과 같은
//    출동 건을 관제 화면(VIEWS.dispatch 목록·dispatchDetail 모달)에서 열면
//    한 색, 보험사 포털 사건 목록에서 열면 다른 색으로 보인다. 형제
//    insurer stTag 값에 맞춘다(단일 지점 수정 — DP_ST 정의는 이 한 곳뿐이고
//    4659·4833행 두 호출부가 그대로 이 값을 물려받는다).
const DP_ST = {'모집중':'amber','수배됨':'blue','도착':'green','실패':'red','취소':'red'};

VIEWS.dispatch = async () => {
  const qs = searchQS('dispatch');
  const d = await api('GET','/api/dispatches'+(qs.toString()?'?'+qs:''));
  const items = d.items || [];
  const a = d.agg || {};
  //  ⚠⚠ [라운드245] items 는 검색바 필터가 걸린 채로 올 수 있다(SEARCH['dispatch']
  //    는 '초기화'를 누르기 전까지 다음 새로고침에도 남는다) — 그 필터가 걸린
  //    목록에서 다시 세면 진짜 기한초과 건이 필터 밖에 있을 때 이 화면만
  //    "기한 내 진행"이라고 조용히 잘못 말한다(같은 화면의 다른 지표들, 사이드바
  //    배지 전부 서버가 낸 전체집계를 쓰는데 여기만 화면에서 다시 더했다).
  //    서버가 이미 agg 처럼 전체집계로 낸 값을 그대로 쓴다.
  const overdue = d.overdue || 0;
  // 점검이 멈추면 기한 초과 건이 영원히 재수배되지 않는다 — 생존 신호를 표시한다
  //  ⚠ last_run_at 은 KST 문자열이다(dispatch.py:591 datetime('now','+9 hours')).
  //    오프셋을 안 붙이면 브라우저 로컬 시각으로 읽혀, 관리자 PC 가 UTC 면
  //    **기한 점검이 9시간 넘게 죽어 있어도 초록으로 보인다.** 같은 파일의
  //    나머지 4곳은 이미 +09:00 을 붙이고 있었다.
  const _swT = d.sweep_last ? Date.parse(String(d.sweep_last).replace(' ','T')+'+09:00') : NaN;
  const stale = isNaN(_swT) || (Date.now() - _swT > 30*60*1000);

  $('#content').innerHTML = `
    <div class="panel">
      <div class="ph"><span class="pt">현장 출동 수배 <small>제한 ${d.minutes}분 · 최대 ${d.max_round}회차</small></span>
        <span style="flex:1"></span>
        <button class="btn g sm" data-act="reliability">📊 업체 응답 이력</button>
        ${/*  ⚠⚠ [337라운드] POST /api/admin/dispatch-sweep 는 require_role
                (중간관리자, app.py:16978)인데 이 버튼은 등급 무관하게 그려졌다
                (205라운드가 try/catch 는 붙였지만 이 게이트는 못 붙였다) —
                과기한 건이 있으면 강조색(p)까지 입혀 하위관리자에게도 클릭을
                권했다. 형제(coActions, 252라운드)처럼 자격 없으면 숨긴다.
                조회(현장 출동 수배 목록)는 등급 무관이라 화면 자체는 그대로 보인다. */''}
        ${myRank()>=2?`<button class="btn ${overdue?'p':'g'} sm" data-act="dispatchSweep">기한 점검 실행${overdue?` (${overdue})`:''}</button>`:''}
      </div>
      ${searchBar('dispatch',{ph:'접수번호·공종·지역·업체', categories:ALL_MAJORS})}
      <div class="krow" style="margin-bottom:12px">
        <div class="kc ${a['모집중']?'hero':''}"><div class="k">모집중</div><div class="v">${a['모집중']||0}<small>건</small></div><div class="d">업체 수락 대기</div></div>
        <div class="kc ${overdue?'red':''}"><div class="k">출동중</div><div class="v">${a['수배됨']||0}<small>건</small></div><div class="d">${overdue?`<b style="color:var(--red)">기한 초과 ${overdue}건</b>`:'기한 내 진행'}</div></div>
        <div class="kc"><div class="k">사진 확보</div><div class="v">${a['도착']||0}<small>건</small></div><div class="d">경매·협의 가능</div></div>
        <div class="kc"><div class="k">미수선 종결</div><div class="v">${d.no_repair||0}<small>건</small></div><div class="d">공사 없이 종결</div></div>
      </div>
      ${stale?`<div class="notice red">⚠ 기한 점검이 30분 이상 돌지 않았습니다. 기한이 지난 출동이 자동 재수배되지 않습니다.
        <b>[기한 점검 실행]</b>을 눌러 주세요. ${d.sweep_last?`(마지막 ${esc(d.sweep_last)})`:'(실행 기록 없음)'}</div>`:
        `<div class="hint" style="margin-bottom:10px">기한 점검 정상 · 마지막 ${esc(d.sweep_last||'-')} ${d.sweep_note?`· ${esc(d.sweep_note)}`:''}</div>`}

      ${(d.need_dispatch||[]).length?`<div style="border:1.5px solid var(--amber);border-radius:11px;padding:11px;margin-bottom:12px">
        <div style="font-weight:800;font-size:.84rem;margin-bottom:7px">🕐 수배를 열어야 하는 사건 ${d.need_dispatch.length}건
          <small style="font-weight:400;color:var(--faint)">사진 없이 접수됐는데 아직 수배가 시작되지 않음</small></div>
        <div class="tbl-wrap" style="max-height:200px;overflow:auto"><table class="tbl">
          <tr><th style="width:50px" class="r">경과</th><th>접수번호</th><th>공종</th><th>지역</th><th class="r">액션</th></tr>
          ${d.need_dispatch.map(c=>`<tr>
            <td class="r" style="${c.stale_days>=1?'color:var(--red);font-weight:800':''}">${c.stale_days||0}일</td>
            <td class="em">${esc(c.case_no)}</td><td>${esc(c.category||'')}</td><td>${esc(c.region||'-')}</td>
            <td class="r">${
              //  ⚠⚠ [라운드502] 형제(dispatchSweep, 라운드337)는 이미 등급게이트가
              //    있는데(위 4543행 부근), 같은 화면의 나머지 세 형제(dpOpen·
              //    dpRetry·dpAssignForm)는 337라운드가 "기한 점검 실행" 버튼
              //    하나만 다루고 빠뜨렸다 — 세 곳 다 서버(app.py, /dispatch·
              //    /dispatch/assign)가 같은 require_role("중간관리자")라 337
              //    자신의 설계의도("조회는 등급무관 그대로, 처리 버튼만 형제
              //    coActions처럼 안내문/숨김")를 그대로 확장한다.
              myRank()>=2?`<button class="btn p sm" data-act="dpOpen" data-arg="${c.id}">수배 개시</button>`
                :'<span class="hint">중간관리자 이상만 처리할 수 있습니다</span>'
            }</td></tr>`).join('')}
        </table></div></div>`:''}

      ${(d.failed_cases||[]).length?`<div style="border:1.5px solid var(--red);border-radius:11px;padding:11px;margin-bottom:12px">
        <div style="font-weight:800;font-size:.84rem;margin-bottom:7px;color:var(--red)">🚫 수배가 중단된 사건 ${d.failed_cases.length}건
          <small style="font-weight:400;color:var(--faint)">선착순으로는 회복되지 않습니다 — 사람이 개입해야 합니다</small></div>
        <div class="tbl-wrap" style="max-height:220px;overflow:auto"><table class="tbl">
          <tr><th style="width:50px" class="r">경과</th><th>접수번호</th><th>공종</th><th>지역</th><th class="r">부른 곳</th><th>중단 사유</th><th class="r">액션</th></tr>
          ${d.failed_cases.map(c=>`<tr>
            <td class="r" style="${c.stale_days>=1?'color:var(--red);font-weight:800':''}">${c.stale_days||0}일</td>
            <td class="em">${esc(c.case_no)}</td><td>${esc(c.category||'')}</td><td>${esc(c.region||'-')}</td>
            <td class="r hint">${c.called_total||0}개사 · ${c.rounds||0}회차</td>
            <td class="hint" style="max-width:180px;white-space:normal">${esc(c.last_reason||'-')}</td>
            <td class="r" style="white-space:nowrap">${
              //  ⚠⚠ [라운드502] 형제(dpOpen, 위 참조) 참조 — 같은 이유로 게이트한다.
              myRank()>=2?`
              <button class="btn g sm" data-act="dpRetry" data-arg="${c.id}" title="이전에 부른 곳도 다시 부릅니다">재수배</button>
              <button class="btn p sm" data-act="dpAssignForm" data-arg="${c.id}" data-arg2="${esc(c.case_no)}">직접 배정</button>`
                :'<span class="hint">중간관리자 이상만 처리할 수 있습니다</span>'
            }</td></tr>`).join('')}
        </table></div>
        <div class="hint" style="margin-top:6px">재수배는 거절한 곳만 빼고 다시 부릅니다. 그래도 후보가 없으면 전화로 잡은 업체를 <b>직접 배정</b>하세요(사유 필수).</div></div>`:''}
      <div class="tbl-wrap"><table class="tbl">
        <tr><th>#</th><th>접수번호</th><th>공종</th><th>지역</th><th>회차</th><th>상태</th><th>수락 업체</th>
            <th>기한</th><th class="r">사진</th><th class="r">실견적</th><th>결과</th></tr>
        ${items.length?items.map(x=>`<tr data-act="dispatchDetail" data-arg="${x.id}" style="cursor:pointer${x.overdue?';background:#FBEAE7':''}">
          <td class="em">${x.id}</td>
          <td class="em">${esc(x.case_no||'-')}</td>
          <td>${esc(x.category||'-')}</td>
          <td>${esc(x.region||'-')}</td>
          <td>${x.round}차</td>
          <td><span class="pill ${DP_ST[x.status]||'gray'}">${esc(x.status)}</span></td>
          <td>${esc(x.claimed_name||'-')}<div class="hint">${x.called}개사 알림</div></td>
          <td>${x.overdue?'<b style="color:var(--red)">초과</b>':esc(x.due_at||'-')}</td>
          <td class="r">${x.photo_count||0}</td>
          <td class="r">${x.field_estimate?won(x.field_estimate)+'원':'-'}</td>
          <td>${x.outcome==='미수선종결'?`<span class="pill gray">미수선</span><div class="hint">${esc(x.no_repair_reason||'')}</div>`
              :x.outcome==='수선진행'?'<span class="pill green">수선</span>'
              :x.fail_reason?`<span class="hint">${esc(x.fail_reason)}</span>`:'-'}</td>
        </tr>`).join(''):'<tr><td colspan="11" class="empty">출동 수배 기록이 없습니다. 사진 없이 접수된 사건에서 수배가 시작됩니다.</td></tr>'}
      </table></div>
    </div>`;
};

async function dispatchSweep(){
  //  ⚠⚠ [라운드205] 형제(ACT.runSweep, 대시보드 마감점검)는 try/catch 로
  //    감싸져 있는데 여기(출동수배 기한점검)는 없었다 — 이 API 도
  //    require_role("중간관리자") 인데 '현장 출동 수배' 메뉴는 등급게이트
  //    밖이라 하위관리자가 열 수 있고, 기한초과 건이 있으면 이 버튼이 강조색
  //    (class="btn p")으로 바뀌어 누르라고 유도한다 — 그 상황에서 하위관리자가
  //    누르면 403 이 조용히 unhandled rejection 으로 사라진다.
  try{
    const r = await api('POST','/api/admin/dispatch-sweep',{});
    toast(`기한 점검 완료 — 만료 ${r.expired||0} · 재수배 ${r.reopened||0} · 중단 ${r.gaveup||0}`);
    VIEWS.dispatch();
  }catch(e){
    //  ⚠⚠ [라운드501] 형제(settleVoid 등, 라운드481·486·500) 참조 — catch도
    //    성공 분기와 같이 정리한다(목록 화면 버튼이라 closeModal은 불필요).
    toast(e.message || '처리하지 못했습니다.'); VIEWS.dispatch();
  }
}

// ── 수배 개시 · 회복 수배 · 직접 배정 ──────────────────────────
//  '수배실패' 는 선착순으로 회복되지 않는다(부를 후보가 구조적으로 0이 된다).
//  그래서 ①거절한 곳만 빼고 다시 부르기 ②사람이 잡은 업체를 직접 넣기 두 경로를 둔다.
//  누구를 부를지 정하는 자리에서 **누가 실제로 받아 줬는지**를 본다.
//   서버(/api/partner-reliability)는 진작 완성돼 있었는데 여는 화면이 없었다.
//   ⚠ 수배 운영 참고용이다 — 낙찰·금액 판단에는 쓰지 않는다(자동화가 낙찰을 정하지 않는다).
async function reliability(){
  let d;
  try{ d = await api('GET','/api/partner-reliability'); }
  catch(e){ toast(e.message); return; }
  const rs = d.items || [];
  const pct = v => (v==null?'-':v+'%');
  openModal(`<h3>업체 응답 이력</h3>
    <div class="hint" style="margin-bottom:8px">${esc(d.note||'')}</div>
    ${rs.length?`<div class="tbl-wrap" style="max-height:60vh;overflow:auto">
      <table class="tbl" style="min-width:760px">
      <tr><th style="min-width:150px">업체</th><th style="min-width:130px">지역·공종</th>
          <th class="r">호출</th><th class="r">수락</th>
          <th class="r">무응답</th><th class="r">수락률</th><th class="r">평균응답</th>
          <th class="r">평균거리</th><th style="min-width:110px">최근 수락</th></tr>
      ${rs.map(r=>`<tr${(r['수락률']||0)===0 && (r['호출']||0)>=3
            ? ' style="background:#FDECEC"' : ''}>
        <td class="em" style="white-space:normal;word-break:keep-all">${esc(r.name||'')}</td>
        <td class="sub" style="white-space:normal;word-break:keep-all">${esc(r.region||'-')} · ${esc(r.major||'-')}</td>
        <td class="r">${r['호출']||0}</td>
        <td class="r">${r['수락']||0}</td>
        <td class="r">${r['무응답']||0}</td>
        <td class="r"><b>${pct(r['수락률'])}</b></td>
        <td class="r">${r['평균응답분']!=null?r['평균응답분']+'분':'-'}</td>
        <td class="r">${r['평균거리km']!=null?r['평균거리km']+'km':'-'}</td>
        <td class="sub">${esc((r['최근수락']||'').slice(0,16)||'-')}</td></tr>`).join('')}
    </table></div>
    <div class="hint" style="margin-top:8px">붉은 줄 = <b>3번 넘게 불렀는데 한 번도 안 받은 곳</b>.
      연락처가 맞는지, 아직 영업 중인지 확인해 주세요.</div>`
    :'<div class="empty">아직 출동 호출 이력이 없습니다.</div>'}
    <div class="modal-foot"><span style="flex:1"></span>
      <button class="btn g" data-act="closeModal">닫기</button></div>`);
}

async function dpOpen(cid, retry){
  try{
    const r = await api('POST',`/api/cases/${cid}/dispatch`, retry?{include_tried:true}:{});
    //  '몇 곳에 알렸다'만 띄우면 운영자는 그만큼 기다린다.
    //  실제로 **수락을 누를 수 있는 곳**이 몇인지까지 말해 준다.
    toast(`수배를 열었습니다 — ${r.called}개사 호출 (${r.minutes}분 제한)<br>`
        + `<span style="font-size:.78rem">앱에서 수락 가능 <b>${r.can_accept??'-'}</b>곳 · `
        + `문자 도달 <b>${r.sms_ok??'-'}</b>곳</span>`);
    if(r.warn) alert('⚠ 수배는 열렸지만 확인이 필요합니다\n\n' + r.warn.replace(/\*\*/g,''));
    VIEWS.dispatch();
  }catch(e){
    if(e.code==='NO_CANDIDATE'){
      if(e.data && e.data.can_retry_with_tried &&
         confirm('부를 수 있는 업체가 없습니다.\n\n이전에 불렀던 곳도 다시 부를까요?\n(거절 의사를 밝힌 곳은 제외합니다)')){
        return dpOpen(cid, true);
      }
      toast(e.message + ' — 직접 배정을 이용하세요.');
      return;
    }
    toast(e.message);
  }
}
function dpRetry(cid){ return dpOpen(cid, true); }

async function dpAssignForm(cid, caseNo){
  // 후보는 이 사건 기준 가까운 순으로 뽑아 준다(전화로 잡을 때 순서가 그대로 근거가 된다)
  let near = {partners:[]};
  try{ near = await api('GET',`/api/cases/${cid}/nearby?limit=15`); }catch(e){}
  openModal(`<h3>출동 직접 배정 — ${esc(caseNo||'')}</h3>
    <div class="msub">선착순으로 회복되지 않는 건을 사람이 잡아 넣습니다.
      전화로 확인한 업체를 고르고 <b>사유를 반드시</b> 남겨 주세요.</div>
    <div class="field"><label>배정할 업체 <small style="color:var(--faint)">현장에서 가까운 순</small></label>
      <select id="as_partner">
        <option value="">${(near.partners||[]).length ? '— 업체 선택 —' : '— 근처에 등록된 업체가 없습니다 —'}</option>
        <!--  ⚠⚠ [라운드245] 형제(loadNearby, 위 2277행 부근)는 같은 API 응답의
              phone·called 를 이미 화면에 보여준다("이미 부름" 배지 + tel: 링크,
              중복 전화 방지가 목적). 여기는 <select> 라 HTML 뱃지·링크는 못
              담지만, <option> 은 일반 텍스트는 담을 수 있다 — 전화를 걸 번호와
              "이미 부름" 여부만이라도 텍스트로 함께 준다. 안내문("전화로 확인한
              업체를 고르세요")이 요구하는 바로 그 번호가 지금까지는 이 화면
              어디에도 없었다. -->
        ${(near.partners||[]).map(p=>`<option value="${p.id}">${p.dist_km}km · ${esc(p.name)} (${esc(p.type||'')}${p.license==='등록확인'?' · 등록확인':''}) · ${p.phone?esc(p.phone):'번호없음'}${p.called?' · 이미 부름':''}</option>`).join('')}
      </select></div>
    ${(near.partners||[]).length ? '' : `<div style="background:#FDF1F1;border:1px solid #E9BCBE;border-radius:9px;
        padding:10px 13px;font-size:.76rem;color:#8C2A30;line-height:1.6;margin:-4px 0 10px">
        이 현장 근처에 <b>좌표가 등록된 협력사가 없습니다.</b> 업체는 있는데 여기 안 뜬다면
        그 업체의 <b>주소가 비어 있거나 좌표가 없는</b> 경우입니다 —
        [업체] 화면에서 주소를 검색해 고르면 거리 계산에 들어옵니다.
      </div>`}
    <div class="field"><label>배정 사유 * <small style="color:var(--faint)">왜 선착순을 건너뛰었는지</small></label>
      <input id="as_reason" placeholder="예: 야간 지방 건으로 전화 확인 후 배정"></div>
    <div class="hint">배정하면 그 업체 포털에 출동 건으로 뜨고, 도착 보고를 할 수 있게 됩니다.
      발주처에도 업체 배정 사실이 통지됩니다.</div>
    <div class="modal-foot">
      <button class="btn p" data-act="dpAssign" data-arg="${cid}">직접 배정</button>
      <span style="flex:1"></span><button class="btn g" data-act="closeModal">취소</button>
    </div>`);
}
async function dpAssign(cid){
  const pid = ($('#as_partner')||{}).value;
  const reason = (($('#as_reason')||{}).value||'').trim();
  if(!pid){ toast('배정할 업체를 선택하세요.'); return; }
  if(reason.length<2){ toast('배정 사유를 남겨 주세요.'); return; }
  try{
    const r = await api('POST',`/api/cases/${cid}/dispatch/assign`,{partner_id:Number(pid), reason});
    closeModal(); toast(esc(r.message)); VIEWS.dispatch();
  }catch(e){
    //  ⚠ 첫 주에는 수락 가능 업체가 0곳이라 수배가 늘 '모집중' 으로 돌고 있다.
    //    그때 전화로 잡은 업체를 넣으려 하면 여기서 막혔고, 그 수배를 멈출
    //    방법도 없어 회차가 소진될 때까지 기다려야 했다. 이제 접고 넘어간다.
    if(e.code === 'DISPATCH_LIVE'){
      if(!confirm('이 사건에는 아직 돌고 있는 수배가 있습니다.'
          + String.fromCharCode(10) + String.fromCharCode(10)
          + '지금 직접 배정하면 그 수배는 취소되고, 부른 업체들은 더 이상 수락할 수 없습니다.'
          + String.fromCharCode(10) + '계속하시겠습니까?')) return;
      try{
        const r2 = await api('POST',`/api/cases/${cid}/dispatch/assign`,
                             {partner_id:Number(pid), reason, supersede:true});
        closeModal(); toast(r2.message); VIEWS.dispatch();
      }catch(e2){
        //  [라운드481] 재시도(supersede)마저 경합에 걸리면(예: 그 사이 사건이
        //    이미 낙찰됨) 토스트만 하고 낡은 배정모달이 남았다 — 성공 분기와
        //    같이 정리한다.
        toast(e2.message); closeModal(); VIEWS.dispatch();
      }
      return;
    }
    //  [라운드481] DISPATCH_LIVE가 아닌 다른 409(dispatch.py assign_dispatch의
    //    "배정할 수 있는 상태가 아닙니다"·"이미 다른 업체가 현장에 도착해 사진을
    //    확보한 사건입니다" 등 — 이 모달이 열린 사이 사건이 이미 다른 경로로
    //    진행된 진짜 경합)도 같은 문제였다. 성공 분기와 같이 정리한다.
    toast(e.message); closeModal(); VIEWS.dispatch();
  }
}

async function dispatchDetail(id){
  const r = await api('GET','/api/dispatches/'+id);
  const v = r.dispatch || {};
  const calls = v.calls || [];
  openModal(`<h3>출동 수배 #${v.id}</h3>
    <div class="msub">${esc(v.case_no||'-')} · ${esc(v.category||'')} · ${esc(v.region||'')}</div>
    <div class="tbl-wrap"><table class="tbl">
      <tr><th>접수번호</th><td class="em">${esc(v.case_no||'-')}</td><th>공종</th><td>${esc(v.category||'-')}</td></tr>
      <tr><th>지역</th><td>${esc(v.region||'-')}</td><th>회차</th><td>${v.round}차</td></tr>
      <tr><th>상태</th><td><span class="pill ${DP_ST[v.status]||'gray'}">${esc(v.status)}</span></td>
          <th>제한시간</th><td>${v.minutes}분</td></tr>
      <tr><th>수락 업체</th><td>${esc(v.claimed_name||'-')}</td><th>수락 시각</th><td>${esc(v.claimed_at||'-')}</td></tr>
      <tr><th>도착 기한</th><td>${esc(v.due_at||'-')}</td><th>도착 시각</th><td>${esc(v.arrived_at||'-')}</td></tr>
      <tr><th>현장 사진</th><td>${v.photo_count||0}장</td><th>실견적</th><td>${v.field_estimate?won(v.field_estimate)+'원':'-'}</td></tr>
      ${v.outcome==='미수선종결'?`<tr><th>미수선 사유</th><td colspan="3">${esc(v.no_repair_reason||'')}
        ${v.no_repair_note?`<div class="hint">${esc(v.no_repair_note)}</div>`:''}
        ${v.no_repair_by?`<div class="hint">확인: ${esc(v.no_repair_by)}</div>`:''}</td></tr>`:''}
      ${v.fail_reason?`<tr><th>실패 사유</th><td colspan="3">${esc(v.fail_reason)}</td></tr>`:''}
    </table></div>
    <div style="font-weight:800;font-size:.85rem;margin:14px 0 6px">알림을 받은 업체 ${calls.length}개사 <small style="font-weight:400;color:var(--faint)">— 현장에서 가까운 순으로 호출</small></div>
    <div class="tbl-wrap" style="max-height:280px;overflow:auto"><table class="tbl">
      <tr><th style="width:34px" class="r">순</th><th style="width:48px" class="r">거리</th><th>업체</th><th>응답</th><th>응답 시각</th></tr>
      ${calls.map((c,i)=>`<tr>
        <td class="r hint">${c.call_order||(i+1)}</td>
        <td class="r em" style="color:var(--blue);white-space:nowrap">${c.dist_km!=null?c.dist_km+'<small>km</small>':'<span class="hint">-</span>'}</td>
        <td>${esc(c.partner_name||'')}</td>
        <td>${c.response==='수락'?'<span class="pill green">수락</span>':
             c.response==='거절'?'<span class="pill red">거절</span>':
             c.response==='마감'?'<span class="pill gray">마감</span>':
             c.response?esc(c.response):'<span class="hint">대기</span>'}</td>
        <td class="hint">${esc(c.responded_at||'')}</td></tr>`).join('')}
    </table></div>
    <div class="mact">
      ${v.status==='도착' && v.outcome!=='미수선종결'
        ? `<button class="btn p" data-act="agForm" data-arg="${v.case_id}" data-arg2="${v.field_estimate||0}">📤 견적 원문 승인 요청 (실견적 ${won(v.field_estimate||0)}원)</button>` : ''}
      <span style="flex:1"></span>
      <button class="btn g" data-act="closeModal">닫기</button></div>`);
}

// ══════════════════════════════════════════════════════════════
//  현장 견적 승인 요청 — 출동 업체 실견적을 보험사에 '그대로' 올린다
//
//  ★ 법률 철칙 — 금액을 정하는 주체는 **보험사**다.
//    · 우리가 하는 일 = 견적 원문 전달 + 표준단가 개산 구간(참고) 첨부
//    · 우리가 하지 않는 일 = 금액 입력·조정, 협의·합의 대행, 의견 진술
//      (그 행위가 무등록 손해사정업 / 변호사법 §109① 에 닿는다)
//    그래서 이 화면에는 **금액 입력칸도, '합의 성사' 버튼도 없다.**
// ══════════════════════════════════════════════════════════════
let AG_RANGE = null, AG_PATTERNS = [];

async function agForm(caseId, fieldEst){
  try{ AG_PATTERNS = (await api('GET','/api/repair-patterns')).patterns || []; }
  catch(e){ AG_PATTERNS = []; }
  AG_RANGE = null;
  openModal(`<h3>현장 견적 승인 요청</h3>
    <div class="msub">출동 업체가 낸 견적을 <b>원문 그대로</b> 발주처에 올립니다.
      승인·부동의는 발주처가 포털에서 단독으로 결정합니다.</div>
    <div class="kc" style="margin:10px 0"><div class="k">출동 업체 실견적 <small>(이 금액이 그대로 올라갑니다)</small></div>
      <div class="v" style="font-size:1.2rem">${won(fieldEst)}<small>원</small></div></div>
    <div class="field"><label>수선 유형(표준 카탈로그) — 개산 구간을 참고로 함께 첨부</label>
      <select id="ag_pattern" data-act-change="agPattern">
        <option value="">— 유형 선택 (구간 계산용) —</option>
        ${AG_PATTERNS.map(p=>`<option value="${esc(p.pattern)}">${esc(p.name)}${p.complete?'':' (보완필요→실측권장)'}</option>`).join('')}
      </select></div>
    <div id="ag_inputs"></div>
    <div style="display:flex;gap:6px;align-items:center;margin:6px 0">
      <button class="btn g sm" data-act="agCalc">📐 표준단가 구간 계산</button>
      <div id="ag_range" class="hint">유형과 수량을 넣고 계산하세요 (선택 사항)</div>
    </div>
    <div class="hint" style="margin:10px 0;padding:9px 12px;background:var(--mist);border-radius:9px;line-height:1.6">
      ⚖️ 복구온은 이 금액을 <b>조정하지 않습니다.</b> 금액 협의·합의는 하지 않으며,
      승인 여부는 발주처가 단독으로 판단합니다. 부동의되면 확보한 현장 사진으로 2차 경매를 엽니다.
    </div>
    <div class="modal-foot">
      <button class="btn p" data-act="agRequest" data-arg="${caseId}">📤 발주처에 승인 요청</button>
      <button class="btn g" data-act="agSettle" data-arg="${caseId}" data-arg2="0">⛔ 부동의 기록 (사진으로 2차 경매)</button>
      <button class="btn g" data-act="dispatchReport" data-arg="${caseId}">📄 출동 보고서</button>
      <span style="flex:1"></span>
      <button class="btn g" data-act="closeModal">닫기</button>
    </div>`);
}

function agPattern(){
  const pid = ($('#ag_pattern')||{}).value;
  const box = $('#ag_inputs'); if(!box) return;
  const p = AG_PATTERNS.find(x=>x.pattern===pid);
  //  ⚠ choice 항목을 텍스트칸으로 두면 어떤 값이 되는지 안 보이고, 숫자로만
  //    적으면(예: 지주간격 choices=[2,4]) 서버가 문자열 vs 숫자 타입 불일치로
  //    **둘 다 거부**했다 — 실측: 빈칸으로 둬야만 통과해 기본값이 조용히 박혔다.
  //    choices 가 있으면 select 로, 없으면 min/max 를 붙인 number 로 그린다.
  box.innerHTML = p ? `<div class="grid2">${p.inputs.map(i=>
    `<div class="field"><label>${esc(i.label)}</label>` + (i.choices
      ? `<select class="ag-in" data-key="${esc(i.key)}">${i.choices.map(c=>
          `<option${c===i.default?' selected':''}>${esc(String(c))}</option>`).join('')}</select>`
      : `<input class="ag-in" type="number" data-key="${esc(i.key)}"
           ${i.min!=null?`min="${i.min}"`:''} ${i.max!=null?`max="${i.max}"`:''}
           ${i.default!=null?`value="${esc(String(i.default))}"`:''}>`)
    + `</div>`).join('')}</div>` : '';
  AG_RANGE = null;
  const r = $('#ag_range'); if(r) r.textContent = '수량을 넣고 계산하세요';
}

async function agCalc(){
  const pid = ($('#ag_pattern')||{}).value;
  if(!pid){ toast('수선 유형을 먼저 선택하세요.'); return; }
  const inputs = {};
  document.querySelectorAll('.ag-in').forEach(el=>{ if(el.value.trim()) inputs[el.dataset.key]=el.value.trim(); });
  try{
    const r = await api('POST','/api/repair-estimate',{pattern:pid, inputs});
    const e = r.estimate;
    // 서버가 합의 개시 때 **다시 계산**하므로, 금액이 아니라 '무엇을 넣었는지'를 보관한다.
    //  (금액을 그대로 보내 저장하면 화면을 우회해 근거를 위조할 수 있다)
    AG_RANGE = {pattern:pid, inputs, low:e.range_low, high:e.range_high};
    const dbTag = e.db_prices_used
      ? `표준단가표 ${e.db_prices_used}/${e.line_count}줄 적용`
      : `내장 기본단가 기준`;
    $('#ag_range').innerHTML = `표준단가 개산 <b style="color:var(--blue)">${won(e.range_low)} ~ ${won(e.range_high)}원</b>
      <span class="hint">(${esc(e.gate)} · ${dbTag}) — 확정가 아님·참고 근거</span>`;
  }catch(e){ $('#ag_range').innerHTML = `<span style="color:var(--red)">${esc(e.message)}</span>`; }
}

// 견적 원문을 발주처 승인 대기로 올린다(금액은 실견적 그대로 — 우리가 손대지 않는다).
//  개산 근거는 패턴·입력만 보내고 **서버가 다시 계산**한다(위조 방지 + 재현 가능).
async function agRequest(caseId){
  try{
    const opened = await api('POST',`/api/cases/${caseId}/field-agreement`,
      AG_RANGE ? {pattern: AG_RANGE.pattern, inputs: AG_RANGE.inputs} : {});
    const a = opened.agreement || {};
    closeModal();
    toast(`발주처에 <b>승인 요청</b>했습니다 — 실견적 ${won(a.field_amount||0)}원. `
        + `승인·부동의는 발주처가 결정합니다.`);
    VIEWS.dispatch();
  }catch(e){
    //  [라운드481] 이 모달이 열려 있는 사이 사건이 이미 다른 경로로 낙찰되거나
    //    1차 합의가 부동의로 끝나 있으면 409를 받는데(dispatch.py의 open_agreement
    //    가드), 토스트만 하고 낡은 모달·출동목록을 그대로 뒀다 — 477·479라운드가
    //    insurer_portal.html·partner_portal.html에서 고친 것과 같은 패턴. 성공
    //    분기와 같이 정리한다.
    toast(e.message); closeModal(); VIEWS.dispatch();
  }
}
// 부동의(결렬) 기록 — 발주처가 부동의한 사실을 운영자가 대신 남길 수 있다.
//  ⚠ 승인(agreed=true)은 이 경로로 보내지 않는다. 서버가 403 으로 거절한다.
async function agSettle(caseId, agreed){
  if(Number(agreed)===1){ toast('승인은 발주처 포털에서만 가능합니다.'); return; }
  const note = prompt('부동의 사유를 입력하세요 (발주처가 부동의한 내용)');
  if(note===null) return;
  if(!note.trim()){ toast('사유를 입력해 주세요.'); return; }
  try{
    const opened = await api('POST',`/api/cases/${caseId}/field-agreement`,
      AG_RANGE ? {pattern: AG_RANGE.pattern, inputs: AG_RANGE.inputs} : {});
    const aid = opened.agreement_id;
    const r = await api('POST',`/api/field-agreements/${aid}/settle`,
      {agreed:false, note: note.trim()});
    toast(r.message); closeModal(); VIEWS.dispatch();
  }catch(e){
    //  [라운드481] agRequest()와 같은 문제 — settle_agreement()의 "이미 처리된
    //    건입니다"·"상태가 바뀌어 처리하지 못했습니다" 409(다른 운영자가 먼저
    //    부동의를 기록했거나 보험사가 포털에서 먼저 승인한 경우)에서도 낡은
    //    모달이 그대로 남았다. 성공 분기와 같이 정리한다.
    toast(e.message); closeModal(); VIEWS.dispatch();
  }
}

VIEWS.photos = async () => {
  const qs = searchQS('photos');
  const d = await api('GET','/api/photos'+(qs.toString()?'?'+qs:''));
  const st = await api('GET','/api/ai/review-stats').catch(()=>null);
  //  ⚠ 증빙 무결성 점검이 서버에만 있고 화면이 없었다. 실패해도 검수 화면은 떠야 한다.
  const ru = await api('GET','/api/photo-reuse').catch(()=>null);
  const items = d.items || [];
  const pending = items.reduce((a,x)=>a+(x.pending||0),0);
  const unclass = items.reduce((a,x)=>a+(x.unclassified||0),0);

  $('#content').innerHTML = `
    <div class="panel">
      <div class="ph"><span class="pt">AI 사진 검수
        <small>일괄 업로드 → 전·중·후 자동 분류 → 검수 승인 → 보험사 전달</small></span></div>
      ${searchBar('photos',{ph:'접수번호·업체·파일명', categories:ALL_MAJORS})}
      ${d.ai_enabled
        ? `<div style="background:var(--green-bg);border:1px solid #BFE3CB;border-radius:12px;padding:13px 16px;font-size:.78rem;color:#0E5F2C;font-weight:700;margin-bottom:14px">
             🤖 AI 자동 분류가 켜져 있습니다. <b>신뢰도가 낮은 건만</b> 집중 검수하시면 됩니다.
           </div>`
        : `<div style="background:var(--amber-bg);border:1px solid #F5DCB2;border-radius:12px;padding:13px 16px;font-size:.78rem;color:#7A5410;font-weight:700;margin-bottom:14px">
             ⚠ <b>AI 자동 분류가 아직 연동되지 않았습니다.</b> 사진은 정상 접수되지만 분류는 담당자가 직접 지정해야 합니다.<br>
             <span style="font-weight:600">.env 에 BOKGUON_GEMINI_KEY 를 넣으면 자동 분류가 켜집니다 (구글 AI 스튜디오 무료 등급).</span>
           </div>`}
      <div class="krow k4" style="margin-bottom:14px">
        <div class="kc"><div class="k">검수 대기 사진</div><div class="v">${pending}<small>장</small></div></div>
        <div class="kc"><div class="k">미분류</div><div class="v">${unclass}<small>장</small></div><div class="d">분류해야 승인 가능</div></div>
        <div class="kc"><div class="k">대상 사건</div><div class="v">${items.length}<small>건</small></div></div>
        <div class="kc"><div class="k">AI 분류</div><div class="v" style="font-size:1.1rem">${d.ai_enabled?'연동됨':'미연동'}</div></div>
      </div>
      ${st ? aiTrustPanel(st) : ''}
      ${/* 같은 파일이 여러 사건에 올라온 경우. **차단하지 않는다** — 같은 현장을
           나눠 접수한 정상 사유가 있다. 보이게만 하고 판단은 사람이 한다(철칙 5). */''}
      ${ru ? (ru.count ? `
        <div style="background:var(--amber-bg);border:1px solid #F5DCB2;border-radius:12px;padding:13px 16px;margin-bottom:14px">
          <div style="font-size:.82rem;font-weight:800;color:#7A5410;margin-bottom:6px">
            🔁 같은 사진이 여러 사건에 올라왔습니다 — ${ru.count}건</div>
          <div style="font-size:.74rem;color:#7A5410;font-weight:600;margin-bottom:10px">${esc(ru.note||'')}</div>
          <div class="tbl-wrap"><table class="tbl">
            <tr><th>파일 지문</th><th class="r">사건 수</th><th class="r">장수</th><th>올라온 사건</th></tr>
            ${ru.groups.map(g=>`<tr>
              <td><code style="font-size:.72rem">${esc(g.sha256)}…</code></td>
              <td class="r"><b>${g.n_case}</b></td>
              <td class="r">${g.n_photo}</td>
              <td style="font-size:.74rem">${(g.photos||[]).map(p=>
                `${esc(p.case_no||('사건'+p.case_id))} <span style="color:var(--faint)">(${esc(p.uploader||p.uploader_role||'-')})</span>`
              ).join(' · ')}</td></tr>`).join('')}
          </table></div>
        </div>` : `
        <div style="background:var(--green-bg);border:1px solid #BFE3CB;border-radius:12px;padding:11px 16px;font-size:.76rem;color:#0E5F2C;font-weight:700;margin-bottom:14px">
          ✓ 여러 사건에 겹쳐 올라온 사진은 없습니다.</div>`) : ''}
      <div class="tbl-wrap"><table class="tbl">
        <tr><th>사건</th><th>업체</th><th>공종</th><th class="r">사진</th><th class="r">미분류</th>
            <th class="r">영수증</th><th>상태</th><th class="r">액션</th></tr>
        ${items.length ? items.map(x=>`<tr>
          <td class="em">${esc(x.case_no||('#'+x.case_id))}</td>
          <td>${esc(x.partner_name||'-')}</td>
          <td>${esc(x.category||'-')}</td>
          <td class="r">${x.total}장</td>
          <td class="r"${x.unclassified?' style="color:var(--red);font-weight:800"':''}>${x.unclassified}</td>
          <td class="r">${x.receipts}</td>
          <td>${x.pending ? statusPill('검수대기')
                : (x.rejected ? `<span class="pill red">반려 ${x.rejected}장 남음</span>` : statusPill('완료'))}</td>
          <td class="r"><button class="btn g sm" data-photos="${x.case_id}">사진 검수</button></td>
        </tr>`).join('') : '<tr><td colspan="8" class="empty">업로드된 사진이 없습니다</td></tr>'}
      </table></div>
    </div>
    <div id="photobox"></div>`;

  $('#content').querySelectorAll('[data-photos]').forEach(b=>{
    b.addEventListener('click', ()=>openPhotoReview(b.dataset.photos));
  });
};

async function openPhotoReview(caseId){
  const box = $('#photobox');
  box.innerHTML = '<div class="panel"><div class="empty">불러오는 중…</div></div>';
  const d = await api('GET', `/api/cases/${caseId}/photos`);
  //  ⚠⚠ [339라운드] 반려·반려취소(app.py 12241·12218행)·삭제(12091행)·전체검수승인
  //    (12041행) 전부 require_role(중간관리자)인데 등급 무관하게 그려졌다 —
  //    12034·12213행 주석이 이미 "재현확인: 하위관리자 세션으로 200"·"하위관리자가
  //    중간관리자의 검수 판단을 일방적으로 무효화"라고 지목한 바로 그 결함이 화면에는
  //    한 번도 안 들어왔다(정산의 필수 관문이라 여섯 결함 중 가장 위험). 분류(kind,
  //    아래 select)는 그대로 등급무관(12040행 주석 — 실무입력이라 의도적으로 열어 둠).
  const canReview = myRank() >= 2;

  const cell = (p) => `
    <figure class="pcell${p.review_status==='반려'?' rej':''}">
      <a href="${p.url}" target="_blank" rel="noopener"><img src="${p.url}" alt="${esc(p.orig_name||'시공 사진')}"></a>
      <figcaption>
        <select data-kind="${p.id}">
          ${!p.kind?'<option value="" selected disabled>— 분류 선택 —</option>':''}
          ${PHOTO_KINDS.map(k=>`<option value="${k}"${p.kind===k?' selected':''}>${PK_LABEL[k]}</option>`).join('')}
        </select>
        <span class="sub">${p.ai_confidence ? 'AI '+p.ai_confidence+'%' : (p.ai_note?esc(p.ai_note):'수동')}</span>
        ${canReview ? (p.review_status==='반려'
          ? `<button class="btn g sm" data-unreject="${p.id}" style="padding:3px 8px;font-size:.66rem">반려 취소</button>`
          : `<button class="btn danger sm" data-reject="${p.id}" style="padding:3px 8px;font-size:.66rem">반려</button>`) : ''}
        ${canReview ? `<button class="btn g sm" data-del="${p.id}" style="padding:3px 8px;font-size:.66rem" title="사진 삭제">✕</button>` : ''}
        ${p.review_status==='반려'?`<span class="prej">반려: ${esc(p.reject_reason||'')}</span>`:''}
      </figcaption>
    </figure>`;

  const group = (title, list, note='') => !list.length ? '' : `
    <div class="pgroup"><div class="pgtitle">${title} <span class="sub">${list.length}장</span>${note}</div>
      <div class="pgrid">${list.map(cell).join('')}</div></div>`;
  box.innerHTML = `
    <div class="panel" style="border:2px solid var(--blue)">
      <div class="ph"><span class="pt">${esc(d.case.case_no)} 사진 검수
        <small>${esc(d.case.partner_name||'')} · ${esc(d.case.category||'')} · 총 ${d.total}장</small></span>
        ${canReview?'<button class="btn a sm" id="approveAll">전체 검수 승인</button>':''}
        <button class="btn g sm" id="closeReview">닫기</button></div>
      ${group('시공 사진 <span class="sub">(착공 전 → 시공 중 → 완료)</span>', d.construction)}
      ${group('자재 영수증·서류', d.receipts, ' <span class="sub">— 시공 사진과 분리 보관·전달</span>')}
      ${group('미분류 <span class="sub" style="color:var(--red)">— 분류해야 승인할 수 있습니다</span>', d.unclassified)}
      ${d.total ? '' : '<div class="empty">사진이 없습니다</div>'}
    </div>`;

  //  검수는 크게 봐야 판단이 된다 — 썸네일로 승인/반려를 누르면 검수가 형식이 된다.
  //  ⚠ 반드시 **표를 그린 뒤에** 붙인다(앞에서 부르면 빈 화면에 붙어 아무 일도 안 한다).
  if(window.Lightbox) Lightbox.bind(box, {caption: img =>
    (img.alt ? `<b>${esc(img.alt)}</b>` : '')});

  box.querySelectorAll('[data-kind]').forEach(sel=>{
    const _prevKind = sel.value;
    sel.addEventListener('change', async ()=>{
      const _apply = async (extra)=>{
        await api('POST', `/api/photos/${sel.dataset.kind}/kind`, Object.assign({kind: sel.value}, extra||{}));
        toast(`분류를 '${PK_LABEL[sel.value]}'(으)로 변경했습니다`);
        openPhotoReview(caseId);
      };
      try{
        await _apply();
      }catch(e){
        //  ⚠ [라운드107] 낙찰취소 뒤 재입찰 중인 사건 — 확인하면 통과시킨다
        //    (하드블록이면 이번 회차의 정당한 재분류까지 막다른 길이 된다).
        if(e.code === 'PHOTO_REBID_EXPOSE' && confirm(e.message + '\n\n그래도 이 분류로 바꾸시겠습니까?')){
          try{ await _apply({confirm_expose: true}); return; }catch(e2){ toast(e2.message); }
        } else if(e.code !== 'PHOTO_REBID_EXPOSE'){
          toast(e.message);
        }
        sel.value = _prevKind;
      }
    });
  });
  box.querySelectorAll('[data-del]').forEach(b=>{
    b.addEventListener('click', async ()=>{
      if(!confirm('이 사진을 삭제하시겠습니까? 되돌릴 수 없습니다.')) return;
      try{
        await api('DELETE', `/api/photos/${b.dataset.del}`);
        toast('사진을 삭제했습니다.');
        openPhotoReview(caseId);
      }catch(e){ toast(e.message); }
    });
  });
  box.querySelectorAll('[data-unreject]').forEach(b=>{
    b.addEventListener('click', async ()=>{
      try{
        await api('POST', `/api/photos/${b.dataset.unreject}/unreject`, {});
        toast('반려를 취소했습니다. 다시 검수할 수 있습니다.');
        openPhotoReview(caseId);
      }catch(e){ toast(e.message); }
    });
  });
  box.querySelectorAll('[data-reject]').forEach(b=>{
    b.addEventListener('click', async ()=>{
      const reason = prompt('반려 사유를 입력하세요 (업체에 그대로 전달됩니다)');
      if(!reason) return;
      try{
        await api('POST', `/api/photos/${b.dataset.reject}/reject`, {reason});
        toast('반려 처리했습니다. 업체에 재촬영 요청이 전달됩니다.');
        openPhotoReview(caseId);
      }catch(e){ toast(e.message); }
    });
  });
  $('#closeReview').addEventListener('click', ()=>{ box.innerHTML=''; });
  //  ⚠ 등급 미달이면 버튼 자체가 없다(위 canReview) — getElementById 는 null 이라
  //    바로 addEventListener 를 부르면 죽는다.
  const approveBtn = $('#approveAll');
  if (approveBtn) approveBtn.addEventListener('click', async ()=>{
    try{
      const r = await api('POST', `/api/cases/${caseId}/photos/approve`, {});
      toast(`사진 ${r.approved}장 검수 승인 완료`);
      box.innerHTML=''; VIEWS.photos();
    }catch(e){ toast(e.message); }
  });
  box.scrollIntoView({behavior:'smooth'});
}

// ── 통계·리포트 ──
// ── 보험사 월 정산 명세서 ──────────────────────────────────────
//  ⚠ 정산은 마감 다음 달에 뽑는다(서버 _stmt_period_args 문서 — "없으면 지난달").
//    그런데 이 화면의 기본 선택값은 여태 '이번 달'이었다 — 아래 <select> 가 매번
//    값을 명시해서 보내므로 서버의 그 기본값은 실제로는 한 번도 안 타고, 담당자는
//    화면을 열 때마다 아직 안 끝난 이번 달의 미완성 숫자를 먼저 보게 됐다. KST
//    기준으로 지난달을 계산해 기본 선택값 자체를 맞춘다(todayKST() 와 같은 이유로,
//    브라우저 시간대와 무관하게 정확해야 한다).
const [_ty, _tm] = todayKST().split('-').map(Number);
const _lastY = _tm === 1 ? _ty - 1 : _ty, _lastM = _tm === 1 ? 12 : _tm - 1;
let STMT = {insurer_id:'', year:_lastY, month:_lastM};
VIEWS.statement = async () => {
  // 보험사 목록(발주처)
  let insurers = [];
  try{ insurers = await api('GET','/api/insurers'); }catch(e){}
  const monthOpts = Array.from({length:12},(_,i)=>i+1).map(m=>`<option value="${m}" ${STMT.month==m?'selected':''}>${m}월</option>`).join('');
  const yearNow = _ty;
  const yearOpts = [yearNow, yearNow-1, yearNow-2].map(y=>`<option value="${y}" ${STMT.year==y?'selected':''}>${y}년</option>`).join('');
  $('#content').innerHTML = `
    <div class="panel">
      <div class="ph"><span class="pt">월 정산 명세서 <small>발주처(보험사)별 한 달 사건·지급·수수료·절감</small></span>
        <span style="flex:1"></span>
        <button class="btn g sm" data-act="billingGuide">📘 청구 항목 설명서</button></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding:10px;background:var(--mist);border-radius:10px">
        <select id="st_ins" style="width:auto;min-width:220px">
          <option value="">발주처를 선택하세요</option>
          ${insurers.map(x=>`<option value="${x.id}" ${STMT.insurer_id==x.id?'selected':''}>${esc(x.name)}${x.is_demo?' [데모]':''}</option>`).join('')}
        </select>
        <select id="st_year" style="width:auto">${yearOpts}</select>
        <select id="st_month" style="width:auto">${monthOpts}</select>
        <button class="btn p sm" data-act="stmtLoad">명세 조회</button>
        <span style="flex:1"></span>
        <button class="btn g sm" data-act="stmtExport">엑셀 내보내기</button>
        <button class="btn g sm" data-act="stmtPrint">인쇄</button>
      </div>
      <div id="stmtbox" style="margin-top:12px"><div class="hint">발주처와 기간을 고르고 <b>명세 조회</b>를 누르세요.</div></div>
    </div>`;
  if(STMT.insurer_id) stmtLoad();
};
function stmtRead(){
  STMT.insurer_id = ($('#st_ins')||{}).value || '';
  STMT.year = ($('#st_year')||{}).value || _lastY;
  STMT.month = ($('#st_month')||{}).value || _lastM;
}
async function stmtLoad(){
  stmtRead();
  const box = $('#stmtbox'); if(!box) return;
  if(!STMT.insurer_id){ box.innerHTML='<div class="hint">발주처를 선택해 주세요.</div>'; return; }
  box.innerHTML='<div class="loading">불러오는 중…</div>';
  let d;
  try{ d = await api('GET',`/api/insurer-statement?insurer_id=${STMT.insurer_id}&year=${STMT.year}&month=${STMT.month}`); }
  catch(e){ box.innerHTML=`<div class="empty">${esc(e.message)}</div>`; return; }
  box.innerHTML = stmtRender(d);
}
function stmtRender(d){
  const t = d.totals;
  if(!d.lines.length){
    return `<div id="stmtdoc"><div class="empty">${esc(d.insurer_name)} · ${d.year}년 ${d.month}월 — 해당 월 정산 건이 없습니다.</div></div>`;
  }
  return `<div id="stmtdoc">
    <div style="text-align:center;margin:6px 0 14px">
      <div style="font-size:1.2rem;font-weight:900;color:var(--blue)">월 정산 명세서</div>
      <div style="font-size:.85rem;color:var(--sub)">${esc(d.insurer_name)} · ${d.year}년 ${d.month}월</div>
    </div>
    <div class="krow k4" style="margin-bottom:12px">
      <div class="kc"><div class="k">정산 사건</div><div class="v">${t.n}<small>건</small></div></div>
      <div class="kc hero"><div class="k">확정 공사대금</div><div class="v">${won(t.amount)}<small>원</small></div><div class="d">보험사 지급 기준</div></div>
      <div class="kc gold"><div class="k">복구온 수수료</div><div class="v">${won(t.fee)}<small>원</small></div><div class="d">계약 요율</div></div>
      <div class="kc"><div class="k">절감액</div><div class="v" style="color:${t.saved>0?'var(--green)':'var(--muted)'}">${won(t.saved)}<small>원</small></div><div class="d">비교 기준 대비<br><small style="font-weight:400">1차 가견적 · 2차 표준단가 개산</small></div></div>
    </div>
    <div class="tbl-wrap"><table class="tbl">
      <tr><th>접수번호</th><th>공종</th><th>지역</th><th>시공업체</th><th class="r">비교 기준<br><small style="font-weight:400;color:var(--faint)">1차 가견적 · 2차 개산</small></th><th class="r">확정 대금</th><th class="r">절감액</th><th class="r">수수료</th><th>상태</th></tr>
      ${d.lines.map(l=>`<tr>
        <td class="em">${esc(l.case_no)}</td><td>${esc(l.category)}</td><td>${esc(l.region)}</td>
        <td>${esc(l.partner_name)}</td>
        <td class="r">${won(l.saving_base||l.est_price)}</td><td class="r em">${won(l.amount)}</td>
        <td class="r" style="color:${l.saved>0?'var(--green)':'var(--muted)'}">${
            l.saved>0 ? '-'+won(l.saved) : (l.saved<0 ? '+'+won(-l.saved) : '-')}</td>
        <td class="r">${won(l.fee)}</td><td>${statusPill(l.transfer_status)}</td></tr>`).join('')}
      <tr style="background:var(--mist);font-weight:800">
        <td colspan="4">합계 ${t.n}건</td>
        <td class="r">${won(t.est)}</td><td class="r">${won(t.amount)}</td>
        <td class="r" style="color:${t.saved>0?'var(--green)':'var(--muted)'}">${
            t.saved>0 ? '-'+won(t.saved) : (t.saved<0 ? '+'+won(-t.saved) : '-')}</td><td class="r">${won(t.fee)}</td><td></td></tr>
    </table></div>
    <div class="hint" style="margin-top:10px">본 명세는 ${d.year}년 ${d.month}월에 생성된 정산 건 기준입니다. 확정 공사대금은 보험사 지급액, 수수료는 계약 요율에 따른 복구온 수수료, 절감액은 <b>비교 기준</b>(1차 = 보상담당자 가견적 · 2차 = 표준단가 개산) 대비 확정가의 차액입니다.</div>
  </div>`;
}
function stmtExport(){
  stmtRead();
  if(!STMT.insurer_id){ toast('발주처를 선택해 주세요.'); return; }
  window.open(`/api/insurer-statement/export?insurer_id=${STMT.insurer_id}&year=${STMT.year}&month=${STMT.month}`,'_blank');
}
function stmtPrint(){
  const doc = $('#stmtdoc');
  if(!doc){ toast('먼저 명세를 조회하세요.'); return; }
  const w = window.open('','_blank');
  w.document.write(`<html><head><title>월 정산 명세서</title>
    <style>body{font-family:'Malgun Gothic',sans-serif;padding:24px;color:#222}
      table{width:100%;border-collapse:collapse;font-size:12px;margin-top:10px}
      th,td{border:1px solid #ccc;padding:6px 8px;text-align:left}
      th{background:#0064B2;color:#fff} .r{text-align:right}
      .krow{display:none}</style></head><body>${doc.innerHTML}</body></html>`);
  w.document.close(); w.focus(); setTimeout(()=>w.print(),300);
}

// ── 운영 KPI (출동·합의·절감) ──────────────────────────────────
let KPI_PERIOD = {from:'', to:''};
VIEWS.opskpi = async () => {
  const qs = new URLSearchParams();
  if(KPI_PERIOD.from) qs.set('from', KPI_PERIOD.from);
  if(KPI_PERIOD.to) qs.set('to', KPI_PERIOD.to);
  let k;
  try{ k = await api('GET','/api/ops-kpi'+(qs.toString()?'?'+qs:'')); }
  catch(e){ $('#content').innerHTML=`<div class="panel"><div class="empty">${esc(e.message)}</div></div>`; return; }
  const D=k.dispatch, A=k.agreement, S=k.saving;
  const gauge=(pct,color)=>`<div style="height:7px;background:var(--mist);border-radius:4px;overflow:hidden;margin-top:6px">
    <div style="height:100%;width:${Math.min(100,pct)}%;background:${color}"></div></div>`;
  $('#content').innerHTML = `
    <div class="panel" style="margin-bottom:12px">
      <div class="ph"><span class="pt">운영 KPI <small>2트랙(경매콜·출동콜) 도입 성과 · ${esc(k.period.label)}</small></span>
        <span style="flex:1"></span>
        <label style="font-size:.7rem;color:var(--faint)">기간</label>
        <input id="kpi_from" type="date" value="${esc(KPI_PERIOD.from)}" style="width:auto">
        <span style="color:var(--faint)">~</span>
        <input id="kpi_to" type="date" value="${esc(KPI_PERIOD.to)}" style="width:auto">
        <button class="btn p sm" data-act="kpiApply">적용</button>
        ${(KPI_PERIOD.from||KPI_PERIOD.to)?'<button class="btn g sm" data-act="kpiClear">전체</button>':''}
        <button class="btn g sm" data-act="kpiExport">엑셀</button>
      </div>
    </div>

    <div style="font-weight:800;font-size:.82rem;color:var(--sub);margin:4px 2px 8px">🚨 현장 출동 (간접 출동콜)</div>
    <div class="krow k4">
      <div class="kc hero"><div class="k">출동 수배</div><div class="v">${D.total}<small>건</small></div><div class="d">실패 ${D.failed}건</div></div>
      <div class="kc"><div class="k">수락률</div><div class="v">${D.claim_rate}<small>%</small></div><div class="d">${D.claimed}/${D.total}건 수락</div>${gauge(D.claim_rate,'#0064B2')}</div>
      <div class="kc"><div class="k">평균 응답시간</div><div class="v">${D.resp_min}<small>분</small></div><div class="d">수배 → 수락</div></div>
      <div class="kc gold"><div class="k">기한 내 도착률</div><div class="v">${D.due_rate}<small>%</small></div><div class="d">${D.due_ok}/${D.due_base}건</div>${gauge(D.due_rate,'#E8A33D')}</div>
    </div>
    <div class="krow k4" style="margin-top:10px">
      <div class="kc"><div class="k">도착 완료</div><div class="v">${D.arrived}<small>건</small></div><div class="d">수락 대비 ${D.arrive_rate}%</div></div>
      <div class="kc"><div class="k">평균 도착시간</div><div class="v">${D.arrive_min}<small>분</small></div><div class="d">수락 → 현장 도착</div></div>
      <div class="kc"><div class="k">미수선 종결</div><div class="v">${D.no_repair}<small>건</small></div><div class="d">도착 대비 ${D.no_repair_rate}%</div></div>
      <div class="kc"><div class="k">현장 실패</div><div class="v">${D.failed}<small>건</small></div><div class="d">부를 업체 없음 등</div></div>
    </div>

    <div style="font-weight:800;font-size:.82rem;color:var(--sub);margin:16px 2px 8px">📤 현장 견적 승인 (경매 없이 확정)</div>
    <div class="krow k3">
      <div class="kc"><div class="k">승인 요청</div><div class="v">${A.total}<small>건</small></div><div class="d">현장 견적 원문 전달</div></div>
      <div class="kc hero"><div class="k">발주처 승인율</div><div class="v">${A.ok_rate}<small>%</small></div><div class="d">${A.ok}/${A.total}건 · 경매 생략</div>${gauge(A.ok_rate,'#137A38')}</div>
      <div class="kc"><div class="k">평균 승인 금액</div><div class="v">${won(A.avg_amount)}<small>원</small></div><div class="d">승인된 건 기준(실견적)</div></div>
    </div>

    <div style="font-weight:800;font-size:.82rem;color:var(--sub);margin:16px 2px 8px">💰 절감 실적 (완료·정산 기준)</div>
    <div class="krow k3">
      <div class="kc"><div class="k">절감 집계 건수</div><div class="v">${S.done}<small>건</small></div><div class="d">완료·낙찰 확정</div></div>
      <div class="kc hero"><div class="k">평균 절감률</div><div class="v" style="color:var(--green)">-${S.avg_rate}<small>%</small></div><div class="d">비교 기준 대비</div></div>
      ${/*  ⚠ 이 값도 SAVE_BASE_SQL 기반이라 2차 건에서는 **표준단가 개산 상단**을
             뺀 것이다. '가견적 −' 라고 쓰면 우리 계산값이 보상담당자가 낸
             금액처럼 읽힌다(철칙 2). 바로 아래 안내문이 이미 '비교 기준
             (1차 = 보상담당자 가견적 · 2차 = 표준단가 개산)' 이라고 풀어 쓴다. */''}
      <div class="kc gold"><div class="k">누적 절감액</div><div class="v">${won(S.saved_amount)}<small>원</small></div><div class="d">비교 기준 − 낙찰/합의가</div></div>
    </div>
    <div style="font-weight:800;font-size:.82rem;color:var(--sub);margin:16px 2px 8px">⏳ 단계 정체 <small style="font-weight:400;color:var(--faint)">지금 멈춰 있는 것 — 기간 필터와 무관</small></div>
    <div class="panel">
      <div class="tbl-wrap"><table class="tbl">
        <tr><th>단계</th><th class="r">건수</th><th class="r">평균 체류</th><th class="r">최장 체류</th><th style="width:200px">적체</th></tr>
        ${(k.stages||[]).length?(()=>{const mx=Math.max(...k.stages.map(s=>s.avg_days||0),1);
          return k.stages.map(s=>{const hot=(s.avg_days||0)>=7?'var(--red)':(s.avg_days||0)>=3?'#E8A33D':'var(--blue)';
          return `<tr><td>${statusPill(s.status)}</td><td class="r">${s.n}건</td>
            <td class="r em" style="color:${hot}">${s.avg_days||0}일</td>
            <td class="r" style="${(s.max_days||0)>=14?'color:var(--red);font-weight:800':''}">${s.max_days||0}일</td>
            <td><div style="height:8px;border-radius:99px;background:var(--mist);overflow:hidden">
              <div style="height:100%;width:${Math.round((s.avg_days||0)/mx*100)}%;background:${hot}"></div></div></td></tr>`;}).join('');})()
          :'<tr><td colspan="5" class="empty">진행 중 사건이 없습니다</td></tr>'}
      </table></div>
      <div class="hint" style="margin-top:8px">평균 3일 이상이면 주의, 7일 이상이면 그 단계에 병목이 있다는 뜻입니다. 최장 체류가 14일을 넘으면 그 건은 개별 확인이 필요합니다.</div>
    </div>
    <div class="hint" style="margin-top:12px">응답·도착 시간은 KST 기준 실측이며, 데모 데이터는 제외됩니다. 절감액은 <b>비교 기준</b>(1차 = 보상담당자 가견적 · 2차 = 표준단가 개산) 대비 실제 확정가의 차이입니다.</div>`;
};
function kpiApply(){ KPI_PERIOD={from:($('#kpi_from')||{}).value||'', to:($('#kpi_to')||{}).value||''}; VIEWS.opskpi(); }
function kpiClear(){ KPI_PERIOD={from:'',to:''}; VIEWS.opskpi(); }
function kpiExport(){
  const qs=new URLSearchParams();
  if(KPI_PERIOD.from) qs.set('from',KPI_PERIOD.from);
  if(KPI_PERIOD.to) qs.set('to',KPI_PERIOD.to);
  window.open('/api/ops-kpi/export'+(qs.toString()?'?'+qs:''),'_blank');
}

VIEWS.stats = async () => {
  const s = await api('GET','/api/stats');
  //  ★ **돈 숫자는 서버 집계 한 곳에서만 가져온다.**
  //    종전에는 /api/settlements(LIMIT 1000 · 취소 포함)를 화면에서 더했다.
  //    정산이 1000건을 넘는 순간부터 정산 화면·대시보드와 어긋나기 시작하고,
  //    취소된 정산까지 수수료로 잡힌다. 같은 줄의 '누적 거래액'은 서버 집계라
  //    두 카드가 서로 다른 모집단을 말하고 있었다.
  let sum = {}; try{ sum = await api('GET','/api/settlements/summary'); }catch(e){}
  //  ★ 절감률도 서버가 확정건만 세어 둔 값을 쓴다(대시보드·보험사 리포트와 같은 코어).
  //    /api/cases 의 saving 은 아직 낙찰되지 않은 건의 '현재 최저가'까지 절감으로
  //    잡고 음수(초과)는 평균에서 빼 버려, 이 화면만 늘 후하게 나왔다.
  let kpi = {}; try{ kpi = await api('GET','/api/ops-kpi'); }catch(e){}
  const avgSave = Number((kpi.saving && kpi.saving.avg_rate) || 0).toFixed(1);
  //  ⚠ 아래 '발주처별 건수' 표가 여전히 이 목록을 쓴다 — 돈 카드만 서버 집계로
  //    옮겼지 이 fetch 를 지우면 화면이 통째로 죽는다(ReferenceError).
  const cases = await api('GET','/api/cases');
  const maxN = Math.max(...s.by_major.map(m=>m.n),1);
  $('#content').innerHTML = `
    <div class="krow k4">
      <div class="kc hero"><div class="k">누적 거래액</div><div class="v">${won(s.gmv)}<small>원</small></div><div class="d">정산 기준</div></div>
      <div class="kc"><div class="k">누적 수수료</div><div class="v">${won(sum.fee_paid||0)}<small>원</small></div><div class="d">이체완료 · 취소 제외</div></div>
      <div class="kc"><div class="k">평균 절감률</div><div class="v">-${avgSave}<small>%</small></div><div class="d">확정 낙찰 기준</div></div>
      <div class="kc"><div class="k">활성 업체</div><div class="v">${s.total_partners}<small>개사</small></div><div class="d"></div></div>
    </div>
    <div class="row2">
      <div class="panel"><div class="ph"><span class="pt">공종별 업체 분포</span></div>
        <div class="prog">${s.by_major.map(m=>`<div class="r"><span class="k">${esc(m.major)}</span>
          <div class="track"><div class="fill" style="width:${Math.round(m.n/maxN*100)}%"></div></div><span class="v">${m.n}</span></div>`).join('')}</div>
      </div>
      <div class="panel"><div class="ph"><span class="pt">발주처별 사건</span></div>
        <div class="tbl-wrap"><table class="tbl"><tr><th>발주처</th><th class="r">건수</th></tr>
          ${Object.entries(cases.reduce((m,c)=>{m[c.insurer]=(m[c.insurer]||0)+1;return m;},{})).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`<tr><td class="em">${esc(k)}</td><td class="r">${v}건</td></tr>`).join('')}
        </table></div>
      </div>
    </div>`;
};

// ── 운영 알림 로그 ──
VIEWS.ops = async () => {
  const qs = searchQS('ops');
  const data = await api('GET','/api/notifications'+(qs.toString()?'?'+qs:''));
  $('#content').innerHTML = `
    <div class="panel">
      <div class="ph"><span class="pt">운영 알림 로그 <small>현장 발생·거래 알림 (마케팅과 분리)</small></span></div>
      ${searchBar('ops',{ph:'유형·채널·대상·내용'})}
      <div class="tbl-wrap"><table class="tbl">
        <tr><th>시각</th><th>유형</th><th>채널</th><th>수신자</th><th>내용</th><th>상태</th></tr>
        ${data.length?data.map(n=>`<tr>
          <td>${esc((n.created_at||'').slice(5,16))}</td><td><span class="pill blue">${esc(n.ntype)}</span></td>
          <td>${esc(n.channel)}</td><td>${esc(n.target)}</td><td>${esc(n.message)}</td><td>${statusPill(n.status)}</td></tr>`).join(''):'<tr><td colspan="6" class="empty">알림 없음</td></tr>'}
      </table></div>
    </div>`;
};

// ── 공지사항 ──
// ═════════ 연락처 관리 ═════════
//  초기 398개사는 리서치로 모아 전화는 있으나 이메일이 없다.
//  '채워야 할 곳'을 눈에 보이게 하고, 엑셀로 내려받아 채운 뒤 되올리는 흐름을 만든다.
let ctFilter = {ptype:'', missing:'', q:''};
VIEWS.contacts = async () => {
  const s = await api('GET','/api/contacts/summary');
  const qs = new URLSearchParams();
  if(ctFilter.ptype) qs.set('ptype', ctFilter.ptype);
  if(ctFilter.missing) qs.set('missing', ctFilter.missing);
  if(ctFilter.q) qs.set('q', ctFilter.q);
  const list = await api('GET','/api/contacts'+(qs.toString()?('?'+qs):''));
  const card = r => `<div class="kc"><div class="k">${esc(r.type)} <small>${r.total}개사</small></div>
    <div class="v">${r.email_pct}<small>%</small></div>
    <div class="d">이메일 ${r.email}/${r.total} · 전화 ${r.phone}(${r.phone_pct}%) · 수신거부 ${r.opt_out}<br>
      홈페이지 수집 ${r.collected||0} · <b>광고 수신동의 ${r.consent||0}</b></div></div>`;
  $('#content').innerHTML = `
    <div class="krow">${s.summary.map(card).join('')}
      <div class="kc gold"><div class="k">채워야 할 이메일</div>
        <div class="v">${s.summary.reduce((a,r)=>a+(r.total-r.email),0)}<small>곳</small></div>
        <div class="d">콜드메일 발송 대상에서 자동 제외됩니다</div></div>
    </div>
    <div class="panel">
      <div class="ph"><span class="pt">연락처 수집 <small>${list.length}건 표시 (최대 500)</small></span>
        <div class="filters">
          <a class="btn g sm" href="/api/export/contacts_missing">이메일 없는 곳 내려받기</a>
          <a class="btn g sm" href="/api/export/contacts">전체 내려받기</a>
          <label class="btn p sm" style="cursor:pointer">엑셀 일괄 등록
            <input type="file" accept=".xlsx" hidden data-act-change="ctImport"></label>
        </div>
      </div>
      <div style="background:var(--amber-bg);border:1px solid #F5DCB2;border-radius:11px;padding:12px 15px;
                  font-size:.76rem;color:#7A5410;line-height:1.6;margin-bottom:10px">
        <b>주소를 아는 것과 보내도 되는 것은 다릅니다.</b>
        홈페이지에서 모은 주소는 <b>공개된 연락처</b>일 뿐 광고 수신 동의가 아닙니다.
        광고성 메일에는 사전 동의가 필요하고(정보통신망법 제50조 제1항),
        수집 거부를 밝힌 사이트에서는 자동 수집 자체가 금지됩니다(같은 법 제50조의2).<br>
        동의 없는 곳은 <b>1:1 사업 제안·전화 안내</b>로 접근하고, 동의를 받은 뒤에 캠페인 대상에 넣으세요.
      </div>
      <div class="notice">내려받은 엑셀에 <b>이메일·담당자</b>를 채워 그대로 되올리면 일괄 반영됩니다.
        <b>업체명</b> 열은 그대로 두세요(매칭 기준). 동명 업체는 <b>사업자번호</b>로 구분됩니다.</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:2px 0 10px;padding:10px;background:var(--mist);border-radius:10px">
        <input id="ct_q" value="${esc(ctFilter.q)}" placeholder="🔍 업체명·권역·공종" style="${SEARCH_W}" data-act-enter="ctSearch">
        <select id="ct_ptype" data-act-change="ctSetType" style="width:auto">
          <option value="">전체 구분</option>
          <option value="시행사" ${ctFilter.ptype==='시행사'?'selected':''}>시행사</option>
          <option value="시공사" ${ctFilter.ptype==='시공사'?'selected':''}>시공사</option>
        </select>
        <select id="ct_missing" data-act-change="ctSetMissing" style="width:auto">
          <option value="">전체</option>
          <option value="email" ${ctFilter.missing==='email'?'selected':''}>이메일 없음</option>
          <option value="phone" ${ctFilter.missing==='phone'?'selected':''}>연락처 없음</option>
        </select>
        <button class="btn p sm" data-act="ctSearch">검색</button>
      </div>
      <div class="tbl-wrap"><table class="tbl">
        <tr><th>업체명</th><th>구분</th><th>공종</th><th>권역</th><th>연락처</th><th>이메일</th><th>담당자</th><th>수신</th><th></th></tr>
        ${list.length?list.map(p=>`<tr>
          <td class="em">${esc(p.name)}</td><td>${esc(p.partner_type)}</td>
          <td class="cat">${esc(p.major||'-')}</td><td>${esc(p.region||'-')}</td>
          <td class="tel">${esc(p.phone||'-')}</td>
          <td>${p.email?esc(p.email):'<span class="pill amber">없음</span>'}</td>
          <td>${esc(p.manager||'-')}</td>
          <td>${p.email_opt_out?'<span class="pill red">거부</span>':'<span class="pill">가능</span>'}</td>
          <td class="r"><button class="btn g sm" data-act="ctEdit" data-arg="${p.id}">수정</button></td>
        </tr>`).join(''):'<tr><td colspan="9" class="empty">해당 업체 없음</td></tr>'}
      </table></div>
    </div>`;
};
function ctSearch(){ ctFilter.q = ($('#ct_q').value||'').trim(); VIEWS.contacts(); }
function ctSetType(v){ ctFilter.ptype = v; VIEWS.contacts(); }
function ctSetMissing(v){ ctFilter.missing = v; VIEWS.contacts(); }
async function ctEdit(id){
  const list = await api('GET','/api/contacts');
  const p = list.find(x=>x.id===id) || {};
  //  [라운드509] website 를 esc() 만으로 감싸 <a href> 에 그대로 꽂으면 안 된다 —
  //    esc() 는 &<>"' 다섯 문자만 이스케이프할 뿐 URL 스킴은 안 막아서, 'javascript:...'
  //    값이 그대로 클릭 가능한 링크가 됐다(app.py valid_website() 가 저장 시점에 막지만,
  //    옛 데이터·다른 진입로에 대비한 방어심화 — http/https 로 시작할 때만 링크로 건다).
  openModal(`<h3>연락처 수정 — ${esc(p.name||'')}</h3>
    <div class="msub">${esc(p.partner_type||'')} · ${esc(p.major||'')} · ${esc(p.region||'')}</div>
    <div class="grid2">
      <div class="field"><label>연락처</label><input id="ce_phone" value="${esc(p.phone||'')}"></div>
      <div class="field"><label>담당자</label><input id="ce_mgr" value="${esc(p.manager||'')}"></div>
      <div class="field"><label>이메일</label><input id="ce_email" value="${esc(p.email||'')}" placeholder="name@company.co.kr"></div>
      <div class="field"><label>보조 이메일</label><input id="ce_email2" value="${esc(p.email2||'')}"></div>
    </div>
    <div class="field"><label>수집 메모</label><textarea id="ce_note">${esc(p.contact_note||'')}</textarea></div>
    <div class="field"><label>광고성 수신</label>
      <label class="check"><input type="checkbox" id="ce_opt" ${p.email_opt_out?'checked':''}> 메일 수신거부(광고성 발송에서 제외)</label></div>
    ${p.website?`<p style="font-size:.7rem;color:var(--faint)">홈페이지: ${/^https?:\/\//i.test(p.website)?`<a href="${esc(p.website)}" target="_blank" rel="noopener">${esc(p.website)}</a>`:esc(p.website)} — 이메일 확인에 참고</p>`:''}
    <div class="modal-foot"><button class="btn p" data-act="ctSave" data-arg="${id}">저장</button>
      <span style="flex:1"></span><button class="btn g" data-act="closeModal">취소</button></div>`);
}
async function ctSave(id){
  const v = i => ($('#'+i)||{}).value || '';
  try{
    await api('PATCH','/api/contacts/'+id, {phone:v('ce_phone'), manager:v('ce_mgr'),
      email:v('ce_email'), email2:v('ce_email2'), contact_note:v('ce_note'),
      email_opt_out: $('#ce_opt').checked});
    closeModal(); toast('연락처를 저장했습니다.'); VIEWS.contacts();
  }catch(e){ toast(e.message); }
}
async function ctImport(_v, el){
  const f = el.files && el.files[0];
  if(!f) return;
  const fd = new FormData(); fd.append('file', f);
  toast('엑셀을 읽는 중…');
  try{
    const r = await fetch('/api/contacts/import',{method:'POST',headers:{'X-CSRF-Token':CSRF},
      credentials:'same-origin', body:fd});
    const d = await r.json().catch(()=>({}));
    if(!r.ok || !d.ok) throw new Error(d.error||'등록 실패');
    let m = d.message;
    //  ⚠ [라운드98] error_count 는 화면에 안 보여주는 나머지 오류까지 포함한
    //    실제 총 개수다(errors 자체는 10건으로 잘려 온다) — 그 사실을 숨기지 않는다.
    if(d.errors && d.errors.length){
      m += '<br>⚠ '+esc(d.errors[0]);
      if((d.error_count||0) > d.errors.length) m += ` 외 ${d.error_count - d.errors.length}건`;
    }
    toast(m); el.value=''; VIEWS.contacts();
  }catch(e){ toast(esc(e.message)); }
}

// ═════════ 마케팅 캠페인 ═════════
//  ⚠ 운영 알림과 분리된 **광고성 발송 전용** 메뉴.
//    실제 발송은 대행사 연동 전이라 '발송대기'까지만 진행된다(보낸 척하지 않는다).
VIEWS.campaigns = async () => {
  const qs = searchQS('campaigns');
  const list = await api('GET','/api/campaigns'+(qs.toString()?'?'+qs:''));
  $('#content').innerHTML = `
    <div class="panel">
      <div class="ph"><span class="pt">마케팅 캠페인 <small>광고성 발송 전용 · 운영 알림과 분리</small></span>
        ${/*  ⚠⚠ [라운드251] api_campaign_preview·api_campaign_create·api_campaign_cancel
               전부 require_role(중간관리자)인데 이 버튼들은 등급 무관하게 그려졌다 —
               형제(estbands·boq, 246·247라운드)처럼 자격 없으면 조용히 숨긴다. */''}
        ${myRank()>=2?'<button class="btn p sm" data-act="cmNew">+ 새 캠페인</button>':''}</div>
      ${searchBar('campaigns',{ph:'캠페인명·채널·대상·제목'})}
      <div class="notice">📌 공고 안내·검수 독촉 같은 <b>현장 운영 알림</b>은 「운영 알림 로그」에서 처리됩니다.
        이 메뉴는 <b>광고성 정보</b> 전용이라 제목 <b>(광고)</b> 표기와 <b>무료 수신거부 안내</b>가 자동으로 붙고,
        <b>수신거부한 업체는 자동 제외</b>됩니다.</div>
      <div class="notice" style="background:var(--amber-bg);border-color:var(--amber)">
        ⚠ <b>실제 발송은 아직 연결되지 않았습니다</b>(발송 대행사 계약 대기).
        지금은 수신자를 확정해 <b>발송 대기열에 등록</b>하는 데까지 동작합니다.</div>
      <div class="tbl-wrap"><table class="tbl">
        <tr><th>캠페인</th><th>채널</th><th>수신자</th><th>제외</th><th>상태</th><th>등록</th><th class="r">관리</th></tr>
        ${list.length?list.map(c=>`<tr data-act="cmDetail" data-arg="${c.id}" style="cursor:pointer">
          <td class="em">${esc(c.title)}</td><td>${esc(c.channel)}</td>
          <td class="r">${c.total_count}곳</td>
          <td class="r"><span class="sub">거부 ${c.skipped_optout} · 연락처없음 ${c.skipped_nocontact}${c.skipped_noconsent?` · 동의없음 ${c.skipped_noconsent}`:''}</span></td>
          <td>${statusPill(c.status)}</td><td>${esc((c.created_at||'').slice(5,16))}</td>
          <td class="r">${(c.status==='발송대기' && myRank()>=2)?`<button class="btn g sm" data-act="cmCancel" data-arg="${c.id}">취소</button>`:'-'}</td>
        </tr>`).join(''):'<tr><td colspan="7" class="empty">등록된 캠페인이 없습니다</td></tr>'}
      </table></div>
    </div>`;
};
const CM_TEMPLATE = `{업체명} 대표님께

안녕하세요, 피해물 복구 입찰 플랫폼 「복구온」 파트너십팀입니다.
{지역}에서 {공종} 시공을 하시는 대표님께 보험사 복구공사 물량을 소개드리고자 연락드렸습니다.

■ 복구온은 이런 서비스입니다
· 손해보험사가 접수한 사고 피해물(가드레일·유리·담장·차단기 등) 복구공사를 공고합니다
· 원하는 건에만 입찰하시면 됩니다 — 영업비·소개비가 없습니다
· 공사대금은 검수 승인 후 수수료를 제외하고 지급됩니다

■ 입점 조건
· 입점비·월회비 없음 (낙찰 시에만 수수료)
· 사업자등록증 + 배상책임보험 + 시공 실적 자료

10분 통화로 자세히 안내드리겠습니다. 편하신 시간을 회신 주세요.`;
function cmNew(){
  openModal(`<h3>새 캠페인</h3>
    <div class="msub">수신자는 아래 조건으로 자동 산출되며, 수신거부·연락처 없는 곳은 제외됩니다.</div>
    <div class="grid2">
      <div class="field"><label>캠페인 이름 *</label><input id="cm_title" placeholder="예: 입점 제안 4차 — 호남권"></div>
      <div class="field"><label>채널</label><select id="cm_ch">
        <option value="메일">이메일 (콜드메일)</option>
        <option value="문자">문자</option>
        <option value="알림톡">카카오 알림톡 (템플릿 사전승인 필요)</option>
      </select></div>
    </div>
    <div class="grid2">
      <div class="field"><label>대상 구분</label><select id="cm_ptype">
        <option value="">전체</option><option value="시행사">시행사</option><option value="시공사">시공사</option></select></div>
      <div class="field"><label>권역 (선택)</label><input id="cm_region" placeholder="예: 전북 / 강원"></div>
    </div>
    <div class="grid2">
      <div class="field"><label>공종 (선택)</label><input id="cm_major" placeholder="예: 가드레일"></div>
      <div class="field"><label>범위</label>
        <label class="check" style="margin-top:8px"><input type="checkbox" id="cm_nologin" checked> 아직 입점하지 않은 곳만</label></div>
    </div>
    <div style="background:var(--amber-bg);border:1px solid #F5DCB2;border-radius:11px;padding:12px 15px;
                font-size:.76rem;color:#7A5410;line-height:1.6;margin-bottom:12px">
      <b>⚠ 광고성 정보는 사전 동의가 있어야 보낼 수 있습니다</b> (정보통신망법 제50조 제1항).<br>
      홈페이지에서 모은 주소·번호는 <b>공개된 연락처일 뿐 동의가 아닙니다.</b>
      동의 없는 곳에는 광고 대신 <b>1:1 사업 제안</b>이나 전화 통화 후 안내로 접근하세요.
      <div style="margin-top:9px;padding:9px 11px;background:#fff;border-radius:9px;
                  border:1px solid var(--line);font-size:.76rem;line-height:1.6">
        이 화면은 <b>수신 동의를 받은 곳에만</b> 발송합니다(선택 사항이 아닙니다).<br>
        문자·알림톡에는 본문 맨 앞에 <b>(광고)</b> 표기가 자동으로 붙고,
        <b>21시~08시에는 발송할 수 없습니다</b>(같은 법 제50조 제3항·제4항).<br>
        동의는 채널별로 따로 봅니다 — 메일 동의가 문자 동의를 대신하지 않습니다.
      </div>
    </div>
    <div class="field"><label>제목 (메일)</label><input id="cm_subject" placeholder="보험사 복구공사 물량 안내 — 영업 없이 수주하세요"></div>
    <div class="field"><label>본문 <span style="color:var(--faint);font-weight:600">치환자: {업체명} {공종} {지역}</span></label>
      <textarea id="cm_body" style="min-height:200px">${esc(CM_TEMPLATE)}</textarea></div>
    <div id="cm_prev"></div>
    <div class="modal-foot">
      <button class="btn g" data-act="cmPreview">수신자 미리보기</button>
      <button class="btn p" data-act="cmSave">발송 대기열 등록</button>
      <span style="flex:1"></span><button class="btn g" data-act="closeModal">취소</button></div>`);
}
function cmForm(){
  const v = i => ($('#'+i)||{}).value || '';
  return {title:v('cm_title'), channel:v('cm_ch'), ptype:v('cm_ptype'), region:v('cm_region'),
    major:v('cm_major'), no_login: $('#cm_nologin').checked,
    subject:v('cm_subject'), body:v('cm_body'),
    audience: [v('cm_ptype')||'전체', v('cm_region'), v('cm_major')].filter(Boolean).join(' · ')};
}
async function cmPreview(){
  try{
    const r = await api('POST','/api/campaigns/preview', cmForm());
    $('#cm_prev').innerHTML = `<div class="notice" style="margin-top:10px">
      수신 대상 <b>${r.count}곳</b> · 제외: 수신거부 ${r.skipped_optout} · 연락처없음 ${r.skipped_nocontact}${r.skipped_noconsent?` · <b style="color:#7A5410">수신동의 없음 ${r.skipped_noconsent}</b>`:''}<br>
      제목 미리보기: <b>${esc(r.subject_preview||'')}</b>
      ${r.sample_name?`<br><br><b>${esc(r.sample_name)}</b> 기준 치환 결과:<br>
        <span style="white-space:pre-wrap;font-size:.75rem;color:var(--sub)">${esc((r.sample_body||'').slice(0,220))}…</span>`:''}
    </div>`;
  }catch(e){ toast(e.message); }
}
async function cmSave(){
  try{
    const r = await api('POST','/api/campaigns', cmForm());
    closeModal(); toast(r.message); VIEWS.campaigns();
  }catch(e){ toast(e.message); }
}
async function cmDetail(id){
  const d = await api('GET','/api/campaigns/'+id);
  const c = d.campaign;
  openModal(`<h3>${esc(c.title)}</h3>
    <div class="msub">${esc(c.channel)} · ${esc(c.audience||'전체')} · ${statusPill(c.status)}</div>
    <div class="kv"><span class="k">수신자</span><span class="v">${c.total_count}곳</span></div>
    <div class="kv"><span class="k">제외</span><span class="v">수신거부 ${c.skipped_optout} · 연락처없음 ${c.skipped_nocontact}${c.skipped_noconsent?` · 동의없음 ${c.skipped_noconsent}`:''}</span></div>
    <div class="kv"><span class="k">제목</span><span class="v">${esc(c.subject||'-')}</span></div>
    <div class="ph" style="margin-top:10px"><span class="pt" style="font-size:.8rem">본문</span></div>
    <div style="white-space:pre-wrap;font-size:.76rem;color:var(--sub);max-height:180px;overflow:auto;background:var(--mist);padding:12px;border-radius:10px">${esc(c.body||'')}</div>
    <div class="ph" style="margin-top:10px"><span class="pt" style="font-size:.8rem">수신자 (최대 300)</span></div>
    <div class="tbl-wrap" style="max-height:200px"><table class="tbl">
      <tr><th>업체</th><th>연락처</th><th>상태</th></tr>
      ${(d.targets||[]).map(t=>`<tr><td>${esc(t.name)}</td><td>${esc(t.contact)}</td><td>${statusPill(t.status)}</td></tr>`).join('')}
    </table></div>
    <div class="modal-foot"><span style="flex:1"></span><button class="btn g" data-act="closeModal">닫기</button></div>`);
}
async function cmCancel(id){
  if(!confirm('이 캠페인을 취소하시겠습니까?')) return;
  try{ await api('POST','/api/campaigns/'+id+'/cancel'); toast('취소했습니다.'); VIEWS.campaigns(); }
  catch(e){ toast(e.message); }
}

VIEWS.notices = async () => {
  const qs = searchQS('notices');
  const data = await api('GET','/api/notices'+(qs.toString()?'?'+qs:''));
  $('#content').innerHTML = `
    <div class="panel">
      <div class="ph"><span class="pt">공지사항 <small>협력업체·보험사 대상</small></span><button class="btn p sm" data-act="noticeForm">+ 공지 작성</button></div>
      ${searchBar('notices',{ph:'제목·내용'})}
      <div class="tbl-wrap"><table class="tbl">
        <tr><th>#</th><th>제목</th><th>대상</th><th>고정</th><th>작성일</th><th class="r">액션</th></tr>
        ${data.length?data.map(n=>`<tr>
          <td>${n.id}</td><td class="em">${n.pinned?'📌 ':''}${esc(n.title)}</td><td>${esc(n.audience)}</td>
          <td>${n.pinned?'<span class="pill amber">고정</span>':'-'}</td><td>${esc((n.created_at||'').slice(0,10))}</td>
          ${/*  ⚠⚠ [339라운드] DELETE /api/notices/<id> 는 require_role(중간관리자,
                  app.py:14412) — 등급 무관하게 그려져 있었다(등록(POST, require_admin,
                  330라운드)은 등급무관이 맞아 noticeForm 은 그대로 둔다). */''}
          <td class="r">${myRank()>=2?`<button class="btn danger sm" data-act="deleteNotice" data-arg="${n.id}" data-arg2="${esc(n.title)}">삭제</button>`:''}</td></tr>`).join(''):'<tr><td colspan="6" class="empty">공지 없음</td></tr>'}
      </table></div>
    </div>`;
};
function noticeForm(){
  openModal(`<h3>공지 작성</h3><div class="msub">협력업체 앱·웹에 노출됩니다</div>
    <div class="field"><label>제목 *</label><input id="n_title"></div>
    <div class="field"><label>내용</label><textarea id="n_body"></textarea></div>
    <div class="grid2">
      <div class="field"><label>대상</label><select id="n_aud"><option>협력업체</option><option>보험사</option><option>전체</option></select></div>
      <div class="field"><label>상단 고정</label><select id="n_pin"><option value="0">아니오</option><option value="1">예</option></select></div>
    </div>
    <div class="modal-foot"><button class="btn p" data-act="saveNotice">등록</button><span style="flex:1"></span><button class="btn g" data-act="closeModal">취소</button></div>`);
}
async function saveNotice(){
  const body={title:$('#n_title').value.trim(), body:$('#n_body').value.trim(), audience:$('#n_aud').value, pinned:$('#n_pin').value==='1'};
  if(!body.title){ toast('제목은 필수입니다.'); return; }
  await api('POST','/api/notices', body); closeModal(); toast('공지가 등록되었습니다'); VIEWS.notices();
}
async function deleteNotice(id, title){
  // 확인 없이 한 번에 지워지고 되돌릴 수 없었다 — 무엇을 지우는지 보여 주고 되묻는다
  const t = title || '이 공지';
  if(!confirm(`「${t}」 공지를 삭제합니다.
협력사·보험사 화면에서도 사라지며 되돌릴 수 없습니다. 진행할까요?`)) return;
  try{ await api('DELETE','/api/notices/'+id); toast('공지를 삭제했습니다'); VIEWS.notices(); }
  catch(e){ toast(e.message); }
}

// ── 발송 대기함 (B7) ──
//  알림은 '발송대기'까지만 기록된다(실발송 계약 전). 문제는 **아무도 안 본다**는 것이었다.
//  경고를 잘 만들어도 사람에게 닿지 않으면 없는 것과 같다.
let obFilter = '발송대기';
//  기본은 최근 7일 — 새로 생긴 알림이 옛 건 수백 개에 묻히지 않게.
let obDays = 7;
VIEWS.outbox = async () => {
  const qs = searchQS('outbox'); qs.set('status', obFilter); qs.set('days', obDays);
  const d = await api('GET', '/api/outbox?' + qs.toString());
  const cnt = d.counts || {};
  //  '목록 N건 발송' 이 쓸 id — 화면에 보이는 것만 보낸다(서버 상한 100건).
  window.__OB_IDS = (d.items || []).filter(x => (x.status || '발송대기') === '발송대기')
                                   .map(x => x.id).filter(Boolean);
  const waitDays = d.oldest_waiting
    ? Math.floor((Date.now() - Date.parse(d.oldest_waiting.replace(' ','T')+'+09:00')) / 86400000)
    : null;
  $('#content').innerHTML = `
    <div class="krow k4" style="margin-bottom:14px">
      <div class="kc${(cnt['발송대기']||0)?' gold':''}"><div class="k">발송 대기</div>
        <div class="v">${cnt['발송대기']||0}<small>건</small></div>
        <div class="d">${waitDays!==null?`가장 오래된 건 ${waitDays}일 경과`:'없음'}
          ${d.older_waiting?`<br><span style="color:var(--amber-text);font-weight:700">
            이 기간 밖에 ${d.older_waiting}건 더 있음</span>`:''}</div></div>
      <div class="kc"><div class="k">사람이 처리함</div><div class="v">${cnt['수동처리']||0}<small>건</small></div></div>
      <div class="kc"><div class="k">도달</div><div class="v">${cnt['도달']||0}<small>건</small></div></div>
      <div class="kc${d.send_enabled?' gold':''}"><div class="k">팝빌 실발송</div>
        <div class="v" style="font-size:1.05rem">${d.send_enabled
          ? (d.popbill&&d.popbill.test_mode?'테스트베드':'운영')
          : (d.popbill&&d.popbill.ready?'스위치 꺼짐':'미설정')}</div>
        <div class="d">${d.popbill&&d.popbill.sender?('발신 '+esc(d.popbill.sender)):(d.popbill&&d.popbill.missing?esc(d.popbill.missing.join(', ')):'')}</div></div>
    </div>
    <div class="panel">
      <div class="ph"><span class="pt">발송 대기함 <small>${(d.items||[]).length}건 표시</small></span>
        <div class="filters">
          ${/*  ⚠ '지금 발송' 은 **최근 48시간 건만** 보낸다(연동 첫날 과거분이 한꺼번에
                 나가는 사고 방지). 그래서 9일 전 건은 눌러도 '0건'이 뜨고 왜인지
                 화면 어디에도 안 나왔다 — 그 건들을 보낼 수단이 아예 없었다. */''}
          ${/*  ⚠⚠ [라운드251] 세 버튼 모두 백엔드가 require_role(중간관리자) 인데
                 이 화면은 d.send_enabled(팝빌 스위치)만 보고 그렸다 — 특히 테스트
                 발송은 임의 번호로 실제 SMS 가 나가는 동작인데도 그랬다. 형제
                 obHandled·obReopen(바로 아래·5451행)은 require_admin 이라 게이트가
                 없는 게 맞는데, 이 셋만 놓쳤다. */''}
          ${(d.send_enabled && myRank()>=2)?`<button class="btn sm" data-act="obSendNow">지금 발송 <small>(최근 48시간)</small></button>
          ${obFilter==='발송대기' && (d.items||[]).length
            ? `<button class="btn g sm" data-act="obSendListed" title="지금 목록에 보이는 건을 나이 제한 없이 보냅니다">목록 ${(d.items||[]).length}건 발송</button>` : ''}
          <button class="btn g sm" data-act="obTestSend">테스트 발송</button>`:''}
          <select data-act-change="obSetFilter" style="width:auto">
            ${['발송대기','수동처리','도달','실패'].map(x=>
              `<option ${obFilter===x?'selected':''}>${x}</option>`).join('')}
          </select>
          <select data-act-change="obSetDays" style="width:auto" title="기간을 좁혀야 새 알림이 보입니다">
            ${[[7,'최근 7일'],[30,'최근 30일'],[90,'최근 90일'],[0,'전체 기간']].map(([v,t])=>
              `<option value="${v}" ${obDays===v?'selected':''}>${t}</option>`).join('')}
          </select>
        </div>
      ${searchBar('outbox',{ph:'유형·채널·대상·내용'})}
      </div>
      <div style="background:var(--amber-bg);border:1px solid #F5DCB2;border-radius:11px;
                  padding:12px 15px;font-size:.76rem;color:#7A5410;line-height:1.6;margin-bottom:10px">
        ${esc(d.notice||'')}
      </div>
      <div class="tbl-wrap"><table class="tbl">
        <tr><th>종류</th><th>수단</th><th>대상</th><th>내용</th><th>등록</th><th class="r">처리</th></tr>
        ${(d.items||[]).length ? d.items.map(x=>`<tr>
          <td class="em">${esc(x.ntype||'-')}</td>
          <td>${esc(x.channel||'-')}</td>
          <td>${esc(x.to_name||x.target||'-')}
            ${x.to_phone
              ? `<div style="font-size:.72rem;margin-top:2px"><a href="tel:${esc(x.to_phone)}"
                   style="color:var(--brand);font-weight:700">${esc(x.to_phone)}</a></div>`
              : `<div style="font-size:.68rem;color:var(--muted);margin-top:2px">번호 없음</div>`}</td>
          <td style="max-width:380px">${esc((x.message||'').slice(0,90))}
            ${x.send_detail?`<div style="font-size:.68rem;color:${x.status==='실패'?'var(--red,#C0392B)':'var(--muted)'};margin-top:3px">${esc(x.send_detail)}</div>`:''}
            ${x.handled_note?`<div style="font-size:.68rem;color:var(--muted);margin-top:3px">처리메모: ${esc(x.handled_note)}</div>`:''}
            ${x.status==='수동처리'?`<div style="margin-top:5px"><button class="btn g sm"
                 data-act="obReopen" data-arg="${x.id}">발송 대기로 되돌리기</button></div>`
             //  ⚠⚠ [라운드410] 마무리기록 실패로 status='발송대기' 인 채 send_attempts
             //    만 3에 도달한 좀비 건 — 겉보기엔 방금 생긴 정상 대기 건과 똑같아서
             //    표식 없인 존재조차 안 보였다(자동스윕·[지금 보내기] 둘 다 이 조건에
             //    막혀 영영 못 나감, app.py api_outbox_reopen 이 이제 이 조건도 받아줌).
             : (x.status==='발송대기' && (x.send_attempts||0)>=3)
             ? `<div style="margin-top:5px"><div style="font-size:.68rem;color:var(--red,#C0392B)">
                  ⚠ 재시도 소진(${x.send_attempts}회) — 자동발송이 이 건을 더 이상 안 집습니다</div>
                <button class="btn g sm" data-act="obReopen" data-arg="${x.id}">발송 대기로 되돌리기</button></div>`
             : ''}</td>
          <td style="font-size:.72rem">${esc((x.created_at||'').slice(5,16))}</td>
          <td class="r">${(x.status==='발송대기'||x.status==='실패')
            ? `<button class="btn g sm" data-act="obHandled" data-arg="${x.id}">처리함</button>`
            : `<span class="sub" style="font-size:.7rem">${esc(x.status)}${x.sent_at?' '+esc(x.sent_at.slice(5,16)):''}<br>${esc(x.handled_by||'')}</span>`}</td>
        </tr>`).join('') : '<tr><td colspan="6" class="empty">해당 건이 없습니다</td></tr>'}
      </table></div>
    </div>`;
};

// ── 가견적 점검 기준 (B5) + 실적 현황 (B8) ──
VIEWS.estbands = async () => {
  const qs = searchQS('estbands');
  const d = await api('GET', '/api/est-bands'+(qs.toString()?'?'+qs:''));
  const st = await api('GET', '/api/outcome-stats').catch(()=>null);
  const sevs = d.severities || ['경미','보통','중대'];
  $('#content').innerHTML = `
    <div class="panel">
      <div class="ph"><span class="pt">가견적 점검 기준
        <small>공종·파손 정도별로 "이 정도면 이 범위" 를 정해 둔다</small></span></div>
      ${searchBar('estbands',{ph:'공종·파손정도·근거', categories:ALL_MAJORS})}
      <div style="background:var(--amber-bg);border:1px solid #F5DCB2;border-radius:11px;
                  padding:12px 15px;font-size:.76rem;color:#7A5410;line-height:1.6;margin-bottom:12px">
        <b>이 값은 통계가 아니라 운영팀이 정한 기준입니다.</b>
        완료 실적이 ${st ? st.total : 0}건이라 평균을 낼 표본이 없습니다
        (최소 ${st ? st.min_sample : 30}건 필요).
        그래서 <b>근거를 반드시 적게</b> 했습니다 — 나중에 실적이 쌓이면 그 숫자로 바꿉니다.
      </div>
      ${/*  ⚠⚠ [라운드247] POST/DELETE /api/est-bands 는 @require_role("최고관리자")
             인데 이 입력폼·삭제버튼은 등급 무관하게 항상 그려졌다 — 같은 메뉴그룹
             (시스템)의 형제 admins·set 은 이미 자기차단이 있는데(set 은 바로 지난
             246라운드에 고침) 이 화면만 못 받았다. 폼을 다 채운 뒤에야 403을 만나는
             건 246라운드가 정확히 지적한 시간낭비 패턴이다. */''}
      ${myRank() >= 3 ? `<div class="grid2">
        <div class="field"><label>공종</label>
          <select id="eb_major">${(d.categories||[]).map(m=>`<option>${esc(m)}</option>`).join('')}</select></div>
        <div class="field"><label>파손 정도</label>
          <select id="eb_sev">${sevs.map(x=>`<option>${esc(x)}</option>`).join('')}</select></div>
      </div>
      <div class="grid2">
        <div class="field"><label>하한 (선택)</label>
          <input id="eb_min" type="text" inputmode="numeric" placeholder="예: 3,000,000" data-act-input="moneyInput"></div>
        <div class="field"><label>상한 (선택)</label>
          <input id="eb_max" type="text" inputmode="numeric" placeholder="예: 8,000,000" data-act-input="moneyInput"></div>
      </div>
      <div class="field"><label>근거 * <span style="color:var(--faint);font-weight:600">이 값을 무엇으로 정했는지</span></label>
        <input id="eb_src" placeholder="예: 2026년 조달청 가드레일 단가 + 평균 시공량 20m 기준"></div>
      <div style="margin-top:10px"><button class="btn p" data-act="ebSave">기준 저장</button></div>` :
        `<div class="hint">기준 추가·삭제는 최고관리자만 할 수 있습니다 — 아래 표는 조회만 됩니다.</div>`}
      <div class="tbl-wrap" style="margin-top:16px"><table class="tbl">
        <tr><th>공종</th><th>파손 정도</th><th class="r">하한</th><th class="r">상한</th><th>근거</th><th>수정</th><th></th></tr>
        ${(d.bands||[]).length ? d.bands.map(b=>`<tr>
          <td class="em cat">${esc(b.major)}</td><td>${esc(b.severity)}</td>
          <td class="r">${b.min_price?won(b.min_price):'-'}</td>
          <td class="r">${b.max_price?won(b.max_price):'-'}</td>
          <td style="max-width:300px;font-size:.74rem">${esc(b.src||'')}</td>
          <td style="font-size:.72rem">${esc((b.updated_at||'').slice(0,10))}<br>${esc(b.updated_by||'')}</td>
          <td class="r">${myRank() >= 3 ? `<button class="btn g sm" data-act="ebDel" data-arg="${b.id}">삭제</button>` : ''}</td>
        </tr>`).join('') : '<tr><td colspan="7" class="empty">등록된 기준이 없습니다 — 기준이 없으면 금액 대조를 하지 않습니다</td></tr>'}
      </table></div>
    </div>
    ${st ? `<div class="panel">
      <div class="ph"><span class="pt">공종별 실적 현황
        <small>기준을 숫자로 바꿀 수 있을 만큼 쌓였는지 보는 화면</small></span></div>
      <div class="notice">${esc(st.notice||'')}</div>
      ${(st.by_major||[]).length ? `<div class="tbl-wrap"><table class="tbl">
        <tr><th>공종</th><th class="r">완료 건수</th><th class="r">시행사 수</th><th class="r">파손정도 미기록</th></tr>
        ${st.by_major.map(x=>`<tr><td class="em cat">${esc(x.major)}</td>
          <td class="r">${x.n}</td><td class="r">${x.n_partner}</td><td class="r">${x.n_no_sev}</td></tr>`).join('')}
      </table></div>` : '<div class="empty">완료된 실적이 아직 없습니다</div>'}
      ${(st.boq_missing||[]).length ? `<div style="margin-top:12px;font-size:.76rem;color:var(--sub)">
        <b>표준 단가가 비어 있는 공종 ${st.boq_missing.length}개</b> —
        ${st.boq_missing.map(m=>esc(m)).join(' · ')}
        <div style="color:var(--muted);margin-top:4px">기준을 세우려면 이 공종들의 단가부터 채워야 합니다.</div>
      </div>` : ''}
    </div>` : ''}`;
};

// ── 표준 단가·내역 ──
VIEWS.boq = async () => {
  const qs = searchQS('boq');
  const d = await api('GET','/api/boq'+(qs.toString()?'?'+qs:''));
  const data = d.items || [];
  BOQ_MAJORS = d.majors || BOQ_MAJORS;
  BOQ_ROWS = data;                       // 수정·이력 모달이 참조한다
  const grouped = data.reduce((m,b)=>{(m[b.major]=m[b.major]||[]).push(b);return m;},{});
  const empty = (d.majors||[]).filter(m=>!grouped[m]);
  $('#content').innerHTML = `
    <div class="panel">
      ${/*  ⚠⚠ [라운드247] POST/PATCH/DELETE /api/boq 는 @require_role("중간관리자")
             인데 이 추가·수정·비활성 버튼은 등급 무관하게 항상 그려졌다 — 같은
             메뉴그룹(시스템)의 형제 admins·set(246라운드) 은 이미 자기차단이
             있다. 하위관리자가 눌러야 403을 만나는 시간낭비 패턴을 여기도 막는다. */''}
      <div class="ph"><span class="pt">표준 단가·내역서 <small>입찰 비교의 기준 · 공종별 표준 항목</small></span>${myRank() >= 2 ? `<button class="btn p sm" data-act="boqForm">+ 항목 추가</button>` : ''}</div>
      ${searchBar('boq',{ph:'공종·항목·규격·근거', categories:ALL_MAJORS})}
      <div style="background:var(--blue-bg);border-radius:12px;padding:12px 15px;font-size:.76rem;color:var(--blue);font-weight:600;margin-bottom:12px">
        📐 모든 업체가 같은 표준 내역(항목·규격·단위) 기준으로 입찰하므로 견적을 공정하게 비교할 수 있습니다.
      </div>
      <div style="background:var(--amber-bg);border:1px solid #F5DCB2;border-radius:12px;padding:12px 15px;
                  font-size:.76rem;color:#7A5410;line-height:1.65;margin-bottom:14px">
        <b>참고단가는 항목별 단가이며 수량이 없습니다 — 합계를 내지 않습니다.</b>
        금액 판단의 참고로만 쓰세요.
        ${d.no_src ? `<br><b>근거가 적혀 있지 않은 항목이 ${d.no_src}개</b> 있습니다.
          근거 없는 단가는 어디서 온 값인지 알 수 없으니, 확인해서 채우거나 지워 주세요.` : ''}
        ${empty.length ? `<br>단가가 하나도 없는 공종 ${empty.length}개 — ${empty.map(m=>esc(m)).join(' · ')}` : ''}
      </div>
      ${Object.entries(grouped).map(([major, items])=>`
        <div style="font-weight:800;font-size:.85rem;color:var(--blue);margin:14px 0 6px">${esc(major)}</div>
        <div class="tbl-wrap"><table class="tbl">
          <tr><th>항목</th><th>규격</th><th>단위</th><th class="r">참고단가</th><th>근거</th><th class="r">액션</th></tr>
          ${items.map(b=>`<tr><td class="em">${esc(b.item)}${b.sku_key?` <span class="pill blue" title="이 단가는 자동견적 엔진에 주입됩니다 (${esc(b.sku_key)}) — 고치면 개산 구간이 바뀝니다">엔진</span>`:''}</td><td>${esc(b.spec)}</td><td>${esc(b.unit)}</td>
            <td class="r">${won(b.ref_price)}원</td>
            <td style="max-width:300px;font-size:.72rem">${b.price_src
              ? esc(b.price_src) + (b.price_date?`<span style="color:var(--muted)"> · ${esc(b.price_date)}</span>`:'')
              : '<span style="color:var(--red);font-weight:700">근거 없음</span>'}</td>
            <td class="r" style="white-space:nowrap">
              ${myRank() >= 2 ? `<button class="btn g sm" data-act="boqEdit" data-arg="${b.id}">수정</button>` : ''}
              <button class="btn g sm" data-act="boqHistory" data-arg="${b.id}" title="개정 이력">이력</button>
              ${myRank() >= 2 ? `<button class="btn danger sm" data-act="deleteBoq" data-arg="${b.id}" title="비활성(과거 견적 근거는 보존)">비활성</button>` : ''}
            </td></tr>`).join('')}
        </table></div>`).join('')}
    </div>`;
};
let BOQ_MAJORS = [], BOQ_ROWS = [];
function boqForm(){
  // 공종 목록은 서버(WORK_MAJORS)에서 받은 것을 쓴다 — 화면마다 따로 적어두면 조용히 어긋난다.
  const majors = BOQ_MAJORS.length ? BOQ_MAJORS : ['가드레일·방호울타리'];
  openModal(`<h3>표준 내역 항목 추가</h3><div class="msub">입찰 비교의 기준 항목입니다</div>
    <div class="field"><label>공종 *</label><select id="b_major">${majors.map(m=>`<option>${esc(m)}</option>`).join('')}</select></div>
    <div class="grid2">
      <div class="field"><label>항목 *</label><input id="b_item" placeholder="예: 레일(W빔)"></div>
      <div class="field"><label>규격</label><input id="b_spec" placeholder="예: 4M·2겹"></div>
    </div>
    <div class="grid2">
      <div class="field"><label>단위</label><input id="b_unit" placeholder="예: 본"></div>
      <div class="field"><label>참고단가(원)</label><input id="b_price" type="text" inputmode="numeric" placeholder="62,000" data-act-input="moneyInput"></div>
    </div>
    <div class="field"><label>근거 <span style="color:var(--faint);font-weight:600">어디서 온 값인지 · 자재비인지 시공비 포함인지</span></label>
      <input id="b_src" placeholder="예: 조달청 나라장터 종합쇼핑몰 2025 · 자재비 기준"></div>
    <div class="field"><label>자료 기준일</label>
      <input id="b_date" placeholder="예: 2025-06"></div>
    <div style="background:var(--amber-bg);border:1px solid #F5DCB2;border-radius:10px;padding:10px 13px;
                font-size:.74rem;color:#7A5410;margin-top:4px">
      근거를 비워두면 목록에 <b>근거 없음</b>으로 표시됩니다.
      나중에 이 값이 어디서 왔는지 아무도 알 수 없게 되니 되도록 채워 주세요.
    </div>
    <div class="modal-foot"><button class="btn p" data-act="saveBoq">추가</button><span style="flex:1"></span><button class="btn g" data-act="closeModal">취소</button></div>`);
}
async function saveBoq(){
  const body={major:$('#b_major').value, item:$('#b_item').value.trim(), spec:$('#b_spec').value.trim(),
    unit:$('#b_unit').value.trim(), ref_price:digits($('#b_price').value),
    price_src:$('#b_src').value.trim(), price_date:$('#b_date').value.trim()};
  if(!body.item){ toast('항목은 필수입니다.'); return; }
  try{ await api('POST','/api/boq', body); }catch(e){ toast(e.message); return; }
  closeModal(); toast('표준 내역 항목이 추가되었습니다'); VIEWS.boq();
}
async function deleteBoq(id){
  if(!confirm('이 항목을 비활성하시겠습니까?\n\n행은 지우지 않습니다 — 이 단가로 낸 과거 견적의 근거를 보존합니다.')) return;
  try{ const r = await api('DELETE','/api/boq/'+id); toast(r.message||'항목을 비활성했습니다'); VIEWS.boq(); }
  catch(e){ toast(e.message); }
}
// 단가 수정 — 개정 이력이 남는다(고칠 때마다 한 줄)
function boqEdit(id){
  const b = BOQ_ROWS.find(x=>x.id===Number(id));
  if(!b){ toast('항목을 찾지 못했습니다.'); return; }
  openModal(`<h3>표준 단가 수정</h3>
    <div class="msub">${esc(b.major)} · <b>${esc(b.item)}</b> — 고치면 개정 이력이 남습니다</div>
    ${/*  ⚠⚠ [라운드247] 목록의 "엔진" 표식(sku_key 있음)이 뜻하는 바 — 단위를
           바꾸면 자동견적 엔진(_load_price_book)이 이 행을 조용히 무시하고
           내장 기본값으로 되돌아간다 — 를 정작 그 값을 실제로 고치는 이 폼
           에서는 알 방법이 없었다. 서버(api_boq_update)도 이제 막지만, 폼을
           다 채운 뒤에야 아는 것보다 미리 아는 편이 낫다. */''}
    ${b.sku_key ? `<div class="notice" style="margin-bottom:10px">
      ⚙ 이 항목은 자동견적 엔진에 연결돼 있습니다 — 단위를 <b>'${esc(b.unit||'')}'</b>
      로 유지해야 합니다. 바꾸면 이 단가가 견적 계산에서 조용히 빠지고 내장
      기본값으로 되돌아갑니다.</div>` : ''}
    <div class="grid2">
      <div class="field"><label>규격</label><input id="e_spec" value="${esc(b.spec||'')}"></div>
      <div class="field"><label>단위</label><input id="e_unit" value="${esc(b.unit||'')}"></div>
    </div>
    <div class="field"><label>참고단가(원) <small style="color:var(--faint)">현재 ${won(b.ref_price)}원</small></label>
      <input id="e_price" type="text" inputmode="numeric" value="${(b.ref_price||0).toLocaleString('ko-KR')}" data-act-input="moneyInput"></div>
    <div class="field"><label>근거 * <small style="color:var(--faint)">단가가 있으면 근거는 필수입니다</small></label>
      <input id="e_src" value="${esc(b.price_src||'')}" placeholder="예: 조달청 나라장터 종합쇼핑몰 2025 · 자재비 기준"></div>
    <div class="field"><label>자료 기준일</label><input id="e_date" value="${esc(b.price_date||'')}" placeholder="예: 2025-06"></div>
    <div class="modal-foot"><button class="btn p" data-act="boqSave" data-arg="${id}">저장</button>
      <span style="flex:1"></span><button class="btn g" data-act="closeModal">취소</button></div>`);
}
async function boqSave(id){
  const body={spec:$('#e_spec').value.trim(), unit:$('#e_unit').value.trim(),
    ref_price:digits($('#e_price').value), price_src:$('#e_src').value.trim(),
    price_date:$('#e_date').value.trim()};
  try{
    await api('PATCH','/api/boq/'+id, body);
    closeModal(); toast('단가를 수정했습니다 — 개정 이력에 남았습니다'); VIEWS.boq();
  }catch(e){ toast(e.message); }
}
async function boqHistory(id){
  let d;
  try{ d = await api('GET','/api/boq/'+id+'/history'); }catch(e){ toast(e.message); return; }
  const h = d.history||[];
  const b = BOQ_ROWS.find(x=>x.id===Number(id)) || {};
  openModal(`<h3>단가 개정 이력</h3>
    <div class="msub">${esc(b.major||'')} · <b>${esc(b.item||'')}</b></div>
    ${h.length?`<div class="tbl-wrap" style="max-height:320px;overflow:auto"><table class="tbl">
      <tr><th>구분</th><th class="r">이전</th><th class="r">변경</th><th>근거</th><th>처리</th></tr>
      ${h.map(x=>`<tr>
        <td><span class="pill ${x.action==='비활성'?'gray':x.action==='수정'?'amber':'green'}">${esc(x.action)}</span></td>
        <td class="r hint">${x.old_price?won(x.old_price):'-'}</td>
        <td class="r em">${x.new_price?won(x.new_price):'-'}</td>
        <td style="font-size:.7rem;max-width:220px;white-space:normal">${esc(x.price_src||'')}
          ${x.price_date?`<span style="color:var(--faint)"> · ${esc(x.price_date)}</span>`:''}</td>
        <td class="hint">${esc((x.changed_at||'').slice(5,16))}<br>${esc(x.actor||'')}</td></tr>`).join('')}
    </table></div>`:'<div class="empty">개정 이력이 없습니다(이 기능 도입 전 등록분).</div>'}
    <div class="hint" style="margin-top:8px">이력은 '그때 그 단가 대비 낙찰가'를 되짚는 근거입니다 — 캘리브레이션의 기준이 됩니다.</div>
    <div class="modal-foot"><span style="flex:1"></span><button class="btn g" data-act="closeModal">닫기</button></div>`);
}

// ── 설정 · 감사로그 ──
VIEWS.set = async () => {
  const s = await api('GET','/api/settings');
  const ver = await api('GET','/api/version').catch(()=>({}));
  const opts = (cur, arr) => arr.map(o=>`<option ${String(cur)===String(o)?'selected':''}>${o}</option>`).join('');
  $('#content').innerHTML = `
    <div class="panel" style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">
      <div>
        <div style="font-size:.72rem;color:var(--faint);font-weight:800;letter-spacing:.12em">APP VERSION</div>
        <div style="font-size:1.6rem;font-weight:800;letter-spacing:-.02em;margin-top:2px">
          ${esc(ver.version||'—')}
          <span class="pill ${ver.channel==='운영'?'blue':'amber'}" style="vertical-align:middle;margin-left:6px">${esc(ver.channel||'')}</span>
        </div>
      </div>
      <div style="font-size:.78rem;color:var(--sub);line-height:1.7">
        빌드 <b>${esc(ver.build||'—')}</b><br>
        <span style="color:var(--faint)">문제 신고 시 이 두 값을 함께 알려 주세요</span>
      </div>
      <div style="margin-left:auto;display:flex;gap:8px">
        <a class="btn g sm" href="/version" target="_blank" rel="noopener">앱 버전 화면 열기</a>
      </div>
    </div>
    ${/* ⚠ row2(1.6fr 1fr) 안에 감사 로그를 넣어 뒀더니 오른쪽 좁은 칸에 눌려
           14줄짜리 장식이 됐다. 분쟁 때 근거가 되는 기록이다 — 폭을 준다. */''}
      ${/*  ⚠⚠ [라운드246] 이 메뉴(data-v="set")는 applyRoleMenus() 에서 중간관리자
             이상(등급 2)만 보이게 걸려 있었다 — 그런데 이 패널의 실제 문턱은
             PATCH /api/settings 자체가 @require_role("최고관리자")(등급 3)로
             더 높고, 아래 감사 로그는 반대로 @require_admin(등급 1, 누구나)으로
             더 낮다. 하나의 등급 값(2)이 양쪽 다 안 맞았다 — 중간관리자는 이
             패널을 다 채워 넣고 저장을 눌러야만 403을 만나고(폼이 시간낭비가
             됨), 하위관리자는 메뉴 자체가 안 보여 볼 자격이 있는 감사 로그까지
             못 봤다. 메뉴 문턱은 더 낮춰(감사 로그 쪽 맞춤, admin.js 상단
             applyRoleMenus 수정) 누구나 열리게 하고, 이 패널만 형제(VIEWS.admins,
             위 2695행의 myRank()<3 자기차단과 같은 방식)처럼 스스로 가린다. */''}
      ${myRank() >= 3 ? `<div class="panel">
        <div class="ph"><span class="pt">입찰·정산 정책</span><button class="btn p sm" data-act="saveSettings">저장</button></div>
        <div class="grid2">
          <div class="field"><label>수수료율(%)</label><input id="s_fee" type="number" value="${esc(s.fee_rate)}"></div>
          <div class="field"><label>수수료 부가세 기준</label>
            <select id="s_vat">
              <option value="1" ${String(s.fee_vat_included ?? '1')!=='0'?'selected':''}>부가세 포함 (지급액 변동 없음)</option>
              <option value="0" ${String(s.fee_vat_included ?? '1')==='0'?'selected':''}>공급가액 기준 · 세액 별도</option>
            </select>
            <div style="font-size:.7rem;color:var(--faint);margin-top:5px;line-height:1.6">
              세금계산서의 공급가액·세액을 나누는 기준입니다.
              <b>'별도'로 바꾸면 협력사 수령액이 세액만큼 줄어듭니다</b> — 계약서 문구와 맞추세요.
            </div>
          </div>
          <div class="field"><label>최소 입찰 성립 업체수</label><input id="s_min" type="number" value="${esc(s.min_bidders)}"></div>
        </div>
        <div class="grid2">
          <div class="field"><label>저가 경보 기준(%)</label><input id="s_low" type="number" value="${esc(s.low_price_alert)}"></div>
          <div class="field"><label>완료보고 기한(시간)</label><input id="s_rep" type="number" value="${esc(s.report_deadline_hours)}">
            <small style="color:var(--muted)">낙찰 후 이 시간이 지나도록 완료 보고가 없으면 <b>완료보고지연</b>으로 표시하고 업체에 알립니다</small></div>
        </div>
        <div class="grid2">
          <div class="field"><label>입찰 기간(시간)</label><input id="s_ah" type="number" value="${esc(s.auction_hours||48)}">
            <small style="color:var(--muted)">공고를 열고 이 시간이 지나면 자동 마감</small></div>
          <div class="field"><label>재경매 기간(시간)</label><input id="s_rh" type="number" value="${esc(s.reauction_hours||24)}">
            <small style="color:var(--muted)">변경 견적 재경매용</small></div>
        </div>
        <div class="grid2">
          <!--  ⚠⚠ [라운드246] cur 이 undefined(키가 아예 없는 새 DB)면 String(undefined)
                가 어떤 옵션과도 안 맞아 브라우저가 첫 옵션('15분 간격')을 조용히
                선택 상태로 보여준다 — 그런데 실제 서버 기본값(_remind_minutes 의
                default=30)은 30분이다. 바로 옆 fee_vat_included(위 5639행)는 같은
                문제를 ?? 로 이미 막고 있는데 이 둘만 빠져 있었다. saveSettings() 는
                건드리지 않은 필드도 매번 그대로 다시 보내므로, 화면을 열고 다른 값만
                고쳐 저장해도 이 15분이 그대로 DB 에 박혀 실제 리마인드 주기가
                조용히 반토막났다. -->
          <div class="field"><label>사진 검수 리마인드</label><select id="s_rphoto">${opts(s.reminder_photo ?? '30분 간격',['15분 간격','30분 간격','1시간 간격','2시간 간격'])}</select>
            <small style="color:var(--muted)">이 시간을 넘겨 대기 중인 검수가 있으면 운영 알림을 남깁니다</small></div>
          <div class="field"><label>지급 검수 리마인드</label><select id="s_rpay">${opts(s.reminder_payment ?? '30분 간격',['15분 간격','30분 간격','1시간 간격','지정 시각(일 2회)'])}</select>
            <small style="color:var(--muted)">같은 기준으로 지급 검수 대기를 알립니다</small></div>
        </div>
        <div class="hint" style="margin-top:6px">리마인드는 현재 <b>운영 알림(인앱)</b>으로만 남습니다 — 문자·알림톡 발송은 발송사 연동 후 켜집니다.
          점검은 마감 점검과 같은 주기로 돕니다(콘솔 접속 시 + 예약 실행 <code>manage.py sweep</code>).</div>
      </div>` : `<div class="panel"><p class="empty">💰 입찰·정산 정책은 최고관리자만 조회·변경할 수 있습니다.</p></div>`}
      <div class="panel">
        <div class="ph"><span class="pt">감사 로그 <small>모든 승인·수정 기록</small></span>
          <span class="hint" id="audit_cnt"></span>
          ${/*  ⚠ 화면에 걸린 **그 조건 그대로** 내려받는다. 조건을 안 실으면
                 화면과 파일이 다른 모집단을 주고, 받은 사람은 그 차이를 모른다. */''}
          <button class="btn g sm" data-act="auditExport">엑셀 내려받기</button></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:2px 0 10px;padding:10px;background:var(--mist);border-radius:10px">
          ${/*  ⚠ **걸린 조건을 화면에 되살린다.** 22라운드에 이걸 빼먹어서,
               조건을 걸고 다른 메뉴에 갔다 돌아오면 검색창은 비었는데 목록·총건수는
               필터된 값 그대로였다(실측 재현: 검색창 '' · 총 143건). 운영자는 143건을
               전체로 읽는다. 사건 화면은 이미 value 를 되살리고 있다 — 같은 방식. */''}
          <input id="au_q" value="${esc(AUDIT.q)}" placeholder="🔍 접수번호·행위자·내용" style="${SEARCH_W}" data-act-enter="auditSearch">
          <select id="au_act" style="width:auto" title="행위로 좁혀 보기"><option value="">행위 전체</option></select>
          <label style="font-size:.7rem;color:var(--faint)">기간</label>
          <input id="au_from" type="date" value="${esc(AUDIT.from)}" style="width:auto">
          <span style="color:var(--faint)">~</span>
          <input id="au_to" type="date" value="${esc(AUDIT.to)}" style="width:auto">
          <button class="btn p sm" data-act="auditSearch">검색</button>
          <button class="btn g sm" data-act="auditClear">초기화</button>
        </div>
        <div class="feed" id="audit_box"><div class="empty">불러오는 중…</div></div>
        <div style="text-align:center;margin-top:10px">
          <button class="btn g sm" id="audit_more" data-act="auditMore" style="display:none">더 보기</button>
        </div>
      </div>`;
  renderAudit();
};
//  감사 로그는 **분쟁 때 근거**다. 예전 화면은 최근 14줄만 그렸고 총 건수도 안 알려
//  줘서, 8천 건이 쌓인 표를 보고도 "기록이 이것뿐" 이라고 읽게 만들었다.
const AUDIT = {q:'', action:'', from:'', to:'', limit:100};
async function renderAudit(){
  const box = document.getElementById('audit_box'); if(!box) return;
  const qs = new URLSearchParams();
  if(AUDIT.q) qs.set('q', AUDIT.q);
  if(AUDIT.action) qs.set('action', AUDIT.action);
  if(AUDIT.from) qs.set('from', AUDIT.from);
  if(AUDIT.to) qs.set('to', AUDIT.to);
  qs.set('limit', AUDIT.limit);
  let r;
  try{ r = await api('GET','/api/activity?'+qs.toString()); }
  catch(e){ box.innerHTML = `<div class="empty">불러오지 못했습니다 — ${esc(e.message)}</div>`; return; }
  const items = r.items||[], total = r.total||0;
  //  행위 목록은 **한 번만** 채운다 — 매번 채우면 고른 값이 초기화된다
  const sel = document.getElementById('au_act');
  if(sel && sel.options.length <= 1){
    sel.insertAdjacentHTML('beforeend',
      (r.actions||[]).map(a=>`<option value="${esc(a)}">${esc(a)}</option>`).join(''));
    //  옵션을 채운 **뒤에** 고른 값을 되살린다 — 채우기 전에 넣으면 무시된다
    if(AUDIT.action) sel.value = AUDIT.action;
  }
  //  ⚠ 몇 건 중 몇 건인지 반드시 말한다 — 잘린 목록을 전부로 읽는 게 원래 결함이었다
  const cnt = document.getElementById('audit_cnt');
  if(cnt) cnt.innerHTML = (total > items.length)
    ? `총 <b>${total.toLocaleString()}</b>건 중 최근 <b>${items.length}</b>건 표시`
    : `총 <b>${total.toLocaleString()}</b>건`;
  box.innerHTML = items.map(a=>`<div class="fi"><span class="ic">🔒</span>
      <div><div class="a">${esc(a.action)}${a.detail?' — '+esc(a.detail):''}</div><div class="b">${esc(a.actor)}</div></div>
      <span class="t">${esc((a.created_at||'').slice(0,16))}</span></div>`).join('')
    || '<div class="empty">조건에 맞는 기록이 없습니다.</div>';
  const more = document.getElementById('audit_more');
  if(more) more.style.display = (total > items.length) ? '' : 'none';
}
async function saveSettings(){
  const body={fee_rate:$('#s_fee').value, min_bidders:$('#s_min').value, low_price_alert:$('#s_low').value,
    report_deadline_hours:$('#s_rep').value, reminder_photo:$('#s_rphoto').value, reminder_payment:$('#s_rpay').value,
    auction_hours:$('#s_ah').value, reauction_hours:$('#s_rh').value,
    fee_vat_included:$('#s_vat').value};
  // 부가세 기준은 협력사 수령액을 바꾼다 — 실수로 넘어가지 않게 한 번 묻는다
  if(String(body.fee_vat_included)==='0' &&
     !confirm('부가세 기준을 「공급가액 기준·세액 별도」로 바꾸면\n협력사 수령액이 세액만큼 줄어듭니다.\n계약서가 그렇게 되어 있는지 확인하셨습니까?')) return;
  // ⚠ 예전엔 실패해도 아무 말이 없었다(성공 토스트도 안 뜸).
  //   범위를 벗어난 값이 400 으로 거절되면 저장된 줄 알고 넘어가게 된다.
  try{
    await api('PATCH','/api/settings', body);
  }catch(e){ toast(e.message || '설정을 저장하지 못했습니다'); return; }
  // 이미 열려 있는 공고의 마감시각은 바뀌지 않는다. 바뀐다고 오해하면 운영 사고가 난다.
  toast('저장되었습니다 — 이후 새로 여는 공고부터 적용됩니다(이미 열린 공고의 마감시각은 그대로)');
}

boot();


// ── 인라인 핸들러 대체 (CSP nonce 전환) ──────────────────────
//  data-act="이름" 으로 적힌 동작을 실제 함수에 연결한다.
//  ⚠ 즉시실행 함수로 감싼다 — 클래식 스크립트들이 전역 렉시컬 스코프를 공유하므로
//    최상위에서 const ACT 를 선언하면 다른 스크립트와 중복 선언 충돌이 나고,
//    그 스크립트가 통째로 실행되지 않는다(화면이 "불러오는 중…" 에서 멈춘다).
(function () {
  window.ACT = window.ACT || {};
  var ACT = window.ACT;
  // data 속성은 항상 문자열이라, 숫자를 받던 함수가 깨지지 않도록 되돌린다
  var _n = function (v) { return (v !== null && v !== "" && !isNaN(v)) ? Number(v) : v; };
  ACT.appAct = (a, el, ev, b) => appAct(_n(a), _n(b), el, ev);
  ACT.appDetail = (a, el, ev, b) => appDetail(_n(a), _n(b), el, ev);
  ACT.boqForm = (a, el, ev, b) => boqForm(_n(a), _n(b), el, ev);
  ACT.boqEdit = (a) => boqEdit(_n(a));
  ACT.boqSave = (a) => boqSave(_n(a));
  ACT.boqHistory = (a) => boqHistory(_n(a));
  ACT.closeModal = (a, el, ev, b) => closeModal(_n(a), _n(b), el, ev);
  ACT.createCase = (a, el, ev, b) => createCase(_n(a), _n(b), el, ev);
  ACT.defectAct = (a, el, ev, b) => defectAct(_n(a), _n(b), el, ev);
  ACT.defectDetail = (a, el, ev, b) => defectDetail(_n(a), _n(b), el, ev);
  ACT.deleteBoq = (a, el, ev, b) => deleteBoq(_n(a), _n(b), el, ev);
  // 현장 출동 수배 관제
  ACT.dispatchSweep = (a, el, ev, b) => dispatchSweep();
  ACT.dispatchDetail = (a, el, ev, b) => dispatchDetail(_n(a));
  // 현장 지도
  ACT.mapReload = () => mapReload();
  ACT.mapOpenCase = (a, el, ev) => { if(ev) ev.preventDefault(); closeModal(); caseDetail(_n(a)); };
  // 일정 달력
  ACT.calMove = (a) => calMove(a);
  ACT.calDay = (a) => calDay(a);
  ACT.calAdd = (a) => calAdd(a);
  ACT.calSave = () => calSave();
  ACT.calDel = (a) => calDel(_n(a));
  // 해피콜
  ACT.hcForm = (a, el, ev, b) => hcForm(_n(a), b);
  ACT.hcSave = (a) => hcSave(_n(a));
  // 사건 운영 도구
  ACT.coordsSave = (a) => coordsSave(_n(a));
  ACT.coordsClear = (a) => coordsClear(_n(a));
  ACT.caseGate = (a) => caseGate(_n(a));
  //  보고서는 인쇄·PDF 로 넘길 문서다 — 콘솔 안이 아니라 새 창으로 연다
  ACT.reliability = () => reliability();
  ACT.dispatchReport = (a) => window.open('/report/dispatch/' + _n(a), '_blank', 'noopener');
  ACT.billingGuide = () => window.open('/report/billing', '_blank', 'noopener');
  ACT.trackLink = (a) => trackLink(_n(a));
  //  ⚠ [라운드569] readonly 입력칸을 클릭하면 select() 되던 것이 CSP script-src
  //    (nonce 만 허용, unsafe-inline/-hashes 없음)에 막혀 인라인 onclick="this.select()"
  //    가 조용히 죽어 있었다 — 형제 상호작용은 전부 actions.js 의 data-act 로
  //    옮겨 갔는데 이것만 옛 방식으로 남아 있었다. 같은 관례로 옮긴다.
  ACT.selectText = (a, el) => el.select();
  ACT.copyTrack = () => {
    const el = $('#tk_url');
    if(!el) return;
    el.select();
    //  clipboard API 는 사내망 http 에서 막히는 경우가 있다 — 옛 방식으로 폴백한다
    (navigator.clipboard ? navigator.clipboard.writeText(el.value)
                         : Promise.reject()).then(()=>toast('주소를 복사했습니다.'))
      .catch(()=>{ try{ document.execCommand('copy'); toast('주소를 복사했습니다.'); }
                   catch(e){ toast('복사가 막혀 있습니다. 주소를 직접 선택해 복사해 주세요.'); } });
  };
  ACT.nearbyReload = (a) => loadNearby(_n(a));
  ACT.nearFocus = (a) => nearFocus(_n(a));
  // 운영 KPI
  ACT.kpiApply = () => kpiApply();
  ACT.kpiClear = () => kpiClear();
  ACT.kpiExport = () => kpiExport();
  // 월 정산 명세서
  ACT.stmtLoad = () => stmtLoad();
  ACT.stmtExport = () => stmtExport();
  ACT.stmtPrint = () => stmtPrint();
  // 출동 수배 — 개시·회복·직접배정
  ACT.dpOpen = (a) => dpOpen(_n(a));
  ACT.dpRetry = (a) => dpRetry(_n(a));
  ACT.dpAssignForm = (a, el, ev, b) => dpAssignForm(_n(a), b);
  ACT.dpAssign = (a) => dpAssign(_n(a));
  ACT.remindApproval = (a) => remindApproval(_n(a));
  // 1차 합의
  ACT.agForm = (a, el, ev, b) => agForm(_n(a), _n(b));
  ACT.agPattern = () => agPattern();
  ACT.agCalc = () => agCalc();
  ACT.agRequest = (a) => agRequest(_n(a));
  ACT.agSettle = (a, el, ev, b) => agSettle(_n(a), _n(b));
  // 건설업 등록 조사
  ACT.licenseSave = (a) => licenseSave(_n(a));
  ACT.deleteNotice = (a, el, ev, b) => deleteNotice(_n(a), _n(b), el, ev);
  ACT.deletePartner = (a, el, ev, b) => deletePartner(_n(a), _n(b), el, ev);
  ACT.doPartnerSearch = (a, el, ev, b) => doPartnerSearch(_n(a), _n(b), el, ev);
  ACT.leadAct = (a, el, ev, b) => leadAct(_n(a), _n(b), el, ev);
  ACT.leadDetail = (a, el, ev, b) => leadDetail(_n(a), _n(b), el, ev);
  ACT.loadView = (a, el, ev, b) => loadView(_n(a), _n(b), el, ev);
  ACT.noticeForm = (a, el, ev, b) => noticeForm(_n(a), _n(b), el, ev);
  ACT.partnerForm = (a, el, ev, b) => partnerForm(_n(a), _n(b), el, ev);
  ACT.saveBoq = (a, el, ev, b) => saveBoq(_n(a), _n(b), el, ev);
  ACT.saveNotice = (a, el, ev, b) => saveNotice(_n(a), _n(b), el, ev);
  ACT.savePartner = (a, el, ev, b) => savePartner(_n(a), _n(b), el, ev);
  ACT.saveAccount = (a, el, ev, b) => saveAccount(_n(a), _n(b), el, ev);
  //  삭제 체크 시 계좌번호 칸을 비우고 잠근다 — 남겨 둔 숫자와 "삭제"가 동시에
  //  보이면 어느 쪽이 진짜 의도인지 헷갈린다. 해제하면 다시 입력할 수 있게 푼다.
  ACT.acctClearToggle = (v, el) => {
    const acct = $('#b_acct'); if(!acct) return;
    acct.disabled = el.checked;
    if(el.checked) acct.value = '';
  };
  ACT.saveSettings = (a, el, ev, b) => saveSettings(_n(a), _n(b), el, ev);
  ACT.setAppFilter = (a, el, ev, b) => setAppFilter(_n(a), _n(b), el, ev);
  ACT.setCaseFilter = (a, el, ev, b) => setCaseFilter(_n(a), _n(b), el, ev);
  ACT.setCaseSort = (a, el) => setCaseSort(el.value);
  ACT.reloadView = (v) => loadView(v);
  ACT.navToggle = () => navToggle();
  ACT.navClose = () => navClose();
  // 발주처 포털 계정 · 전산 연동
  // 확보한 현장 사진으로 공고(2차 경매)를 연다 — 라우트는 있었는데 부르는 화면이 없었다
  ACT.caseOpenAuction = async (a) => {
    const id = _n(a);
    // ★ 2차 경매는 상한이 없다 — 운영자가 금액을 만들지 않는다.
    //   기준선은 출동 업체가 낸 실견적이고, 서버가 그 값을 읽어 쓴다.
    const basis = prompt('2차 경매를 여는 근거를 적어 주세요.\n' +
                         '(예: 현장 사진 4장 확보 · 보험사 부동의로 경매 전환)');
    if(!basis) return;
    try{
      const r = await api('POST', `/api/cases/${id}/open-auction`, {est_basis: basis});
      toast(r.message || '공고를 열었습니다');
      closeModal(); loadView('cases');
    }catch(e){
      // 서버가 이유를 코드로 준다 — 무엇을 해야 하는지까지 알려 준다
      const m = e.message || '';
      toast(e.code === 'NO_PHOTO'
        ? '현장 사진이 없습니다. 출동 업체의 도착 보고(사진)를 먼저 확인해 주세요.'
        : e.code === 'NO_FIELD_EST'
        ? '출동 업체의 실견적이 없습니다. 1차 합의가 부동의로 끝난 건만 2차 경매를 열 수 있습니다.'
        : m);
      //  [라운드486] 성공 분기와 달리 모달을 안 닫고 새로고침도 안 해, 이미
      //  바뀐 사건 상태 위에 낡은 화면이 그대로 남았다(462·477·479·481라운드와
      //  같은 패턴). 성공 분기와 같이 정리한다.
      closeModal(); loadView('cases');
    }
  };
  ACT.caseRemindReport = async (a) => {
    //  ⚠⚠ [라운드490] 형제 caseRenotify(6505행)는 이미 확인창이 있다 —
    //    너무 잦은 알림은 업체가 알림을 꺼 버리게 만든다는 같은 이유.
    //    서버가 24시간 쿨다운을 다시 판정한다(여기 확인창은 편의일 뿐).
    if(!confirm('시공사에 완료 보고를 독촉합니다.\n'
      + '너무 잦은 알림은 업체가 알림을 꺼 버리게 만듭니다 — 정말 보낼까요?')) return;
    try{ const r = await api('POST', `/api/cases/${_n(a)}/remind-report`, {});
      toast(r.message || '독촉했습니다'); }
    catch(e){ toast(e.message); }
  };
  ACT.insCred = (a, el, ev, b) => insCred(_n(a), b);
  ACT.insApi = (a) => insApi(_n(a));
  ACT.insApiKey = async (a) => {
    if(!confirm('새 API 키를 발급합니다.\n기존 키는 즉시 무효가 되어 보험사 전산 연동이 끊깁니다.\n키 원문은 이번 한 번만 표시됩니다. 진행할까요?')) return;
    try{
      const r = await api('POST', `/api/insurers/${_n(a)}/apikey`, {});
      openModal(`<h3>API 키 발급 완료</h3>
        <div class="msub">이 값은 <b>지금 한 번만</b> 표시됩니다. 다시 볼 수 없습니다.</div>
        <div style="background:var(--mist);border-radius:12px;padding:16px;margin:10px 0;
                    font-family:ui-monospace,monospace;font-size:.86rem;word-break:break-all">${esc(r.api_key||'')}</div>
        <div class="hint">보험사 전산 담당자에게 안전한 경로로 전달하세요.
          호출 시 <b>Authorization: Bearer &lt;키&gt;</b> 헤더에 넣습니다.</div>
        <div class="modal-foot">
          <button class="btn p" data-act="copyText" data-arg="${esc(r.api_key||'')}">복사</button>
          <span style="flex:1"></span>
          <button class="btn g" data-act="insApi" data-arg="${_n(a)}">연동 화면으로</button>
        </div>`);
    }catch(e){ toast(e.message); }
  };
  ACT.insApiRevoke = async (a) => {
    if(!confirm('API 키를 폐기합니다. 보험사 전산 연동이 즉시 끊깁니다. 진행할까요?')) return;
    try{ await api('DELETE', `/api/insurers/${_n(a)}/apikey`); toast('키를 폐기했습니다'); insApi(_n(a)); }
    catch(e){ toast(e.message); }
  };
  ACT.insApiToggle = async (a, el, ev, b) => {
    try{ await api('POST', `/api/insurers/${_n(a)}/api-enable`, {enabled: String(b) === '1'});
      toast(String(b) === '1' ? '연동을 켰습니다' : '연동을 껐습니다'); insApi(_n(a)); }
    catch(e){ toast(e.message); }
  };
  ACT.insWhSave = async (a) => {
    //  ⚠⚠ [라운드149] 서버는 웹훅마다 HMAC-SHA256 서명(X-Bokguon-Signature)을
    //    붙이고(app.py _webhook_send), 그 서명 검증용 webhook_secret 을 이 응답에
    //    실어 보낸다(app.py api_insurer_webhook_set) — 그런데 여기서 응답 자체를
    //    버려서, API 키(insApiKey)는 화면에 보여주면서 이 값만 어디에도 노출되지
    //    않았다. 발주처 개발자가 서명을 검증하려면 이 값이 필요하다.
    const _url = $('#wh_url').value.trim();
    try{ const r = await api('PATCH', `/api/insurers/${_n(a)}/webhook`, {webhook_url: _url});
      toast('통지 주소를 저장했습니다');
      //  주소를 해제(빈 값)했을 땐 아직 쓸 곳이 없는 서명키를 굳이 보여주지 않는다.
      if (_url && r && r.webhook_secret) {
        openModal(`<h3>웹훅 서명 비밀키</h3>
          <div class="msub">발주처가 서명(X-Bokguon-Signature, HMAC-SHA256)을 검증할 때 씁니다.
            주소를 다시 저장해도 같은 값입니다 — 필요하면 언제든 여기서 다시 확인할 수 있습니다.</div>
          <div style="background:var(--mist);border-radius:12px;padding:16px;margin:10px 0;
                      font-family:ui-monospace,monospace;font-size:.86rem;word-break:break-all">${esc(r.webhook_secret)}</div>
          <div class="hint">발주처 개발 담당자에게 안전한 경로로 전달하세요.</div>
          <div class="modal-foot">
            <button class="btn p" data-act="copyText" data-arg="${esc(r.webhook_secret)}">복사</button>
            <span style="flex:1"></span>
            <button class="btn g" data-act="insApi" data-arg="${_n(a)}">연동 화면으로</button>
          </div>`);
      } else {
        insApi(_n(a));
      }
    }
    catch(e){ toast(e.message); }
  };
  ACT.insWhTest = async (a) => {
    try{ const r = await api('POST', `/api/insurers/${_n(a)}/webhook-test`, {});
      toast(`테스트를 보냈습니다 → ${r.sent_to || ''} (아래 목록에서 결과 확인)`); insApi(_n(a)); }
    catch(e){ toast(e.message); }
  };
  // 한 번만 보이는 값(임시 비밀번호·API 키)을 옮겨 적다 틀리지 않게
  ACT.copyText = async (a) => {
    try{ await navigator.clipboard.writeText(String(a||'')); toast('복사했습니다'); }
    catch(e){ toast('복사하지 못했습니다 — 직접 선택해 주세요'); }
  };
  ACT.bellToggle = () => {
    const p = $('#bellPop'), b = $('#bellBtn');
    p.hidden = !p.hidden;
    b.setAttribute('aria-expanded', String(!p.hidden));
    if(!p.hidden) renderBell();
  };
  ACT.bellReadAll = async () => {
    try{
      await api('POST','/api/admin/notifications/read', {});
      NOTI_LIST = NOTI_LIST.map(n=>({...n, read_at: n.read_at || '읽음'}));
      setBellCount(0); renderBell();
    }catch(e){ toast('읽음 처리 실패'); }
  };
  ACT.notiOpen = (a) => notiOpen(_n(a));
  ACT.trayClose = (a, el) => trayDismiss(el.closest('.tc'));
  ACT.obSetFilter = (a, el) => { obFilter = el.value; loadView('outbox'); };
  ACT.obSetDays = (a, el) => { obDays = Number(el.value); loadView('outbox'); };
  ACT.obSendNow = async () => {
    if(!confirm('발송대기 중인 알림톡·문자를 지금 팝빌로 발송합니다.'
      + String.fromCharCode(10) + String.fromCharCode(10)
      + '⚠ 최근 48시간 안에 만들어진 건만 나갑니다.'
      + String.fromCharCode(10)
      + '더 오래된 건은 옆의 「목록 N건 발송」 을 쓰세요.')) return;
    try{
      const r = await api('POST','/api/outbox/send-now',{});
      toast(`발송 ${r.sent||0}건 · 실패 ${r.failed||0}건`
        + ((r.sent||0)===0 ? ' — 48시간이 지난 건은 이 버튼으로 나가지 않습니다' : ''));
      loadView('outbox');
    }catch(e){ toast(e.message||'발송 실패', true); }
  };
  //  ⚠ 나이 제한 없이 **지금 목록에 보이는 건**을 보낸다. 서버 라우트는 있었는데
  //    부르는 화면이 없어 죽은 라우트였다(그래서 오래된 건은 영영 못 나갔다).
  ACT.obSendListed = async () => {
    const ids = (window.__OB_IDS || []);
    if(!ids.length){ toast('보낼 건이 없습니다.'); return; }
    if(!confirm(`지금 목록에 보이는 ${ids.length}건을 발송합니다(나이 제한 없음).`
      + String.fromCharCode(10) + String.fromCharCode(10)
      + '⚠ 오래전에 만들어진 안내가 지금 나갑니다 — 받는 사람에게 뜬금없을 수 있습니다.'
      + String.fromCharCode(10) + '내용을 먼저 확인하셨습니까?')) return;
    try{
      const r = await api('POST','/api/outbox/send-selected',{ids: ids.slice(0,100)});
      toast(`발송 ${r.sent||0}건 · 실패 ${r.failed||0}건`); loadView('outbox');
    }catch(e){ toast(e.message||'발송 실패', true); }
  };
  ACT.obTestSend = async () => {
    const phone = prompt('테스트 문자를 받을 휴대전화 번호 (예: 01012345678)');
    if(!phone) return;
    try{
      const r = await api('POST','/api/outbox/test-send',{phone});
      toast(r.detail||'테스트 발송 접수');
    }catch(e){ toast(e.message||'테스트 발송 실패', true); }
  };
  ACT.obReopen = async (a) => {
  if(!confirm('이 알림을 다시 발송 대기로 되돌릴까요?\n(팝빌 키가 켜지면 그때 실제로 나갑니다)')) return;
  try{
    const r = await api('POST', `/api/outbox/${a}/reopen`, {});
    toast(r.message || '되돌렸습니다.'); VIEWS.outbox();
  }catch(e){ toast(e.message || '되돌리지 못했습니다.'); }
};
//  ⚠ **이름이 겹치면 안 된다.** 처음엔 이것도 `ACT.coWithdraw` 였는데, 같은 키를
//    쓰는 옛 핸들러(`ACT.coWithdraw = (a) => coWithdraw(_n(a))`, 원업체 제안 회수)가
//    **더 아래에서 덮어써서** 새 [철회] 버튼이 /withdraw-offer 를 부르고 409 를 받았다.
//    두 버튼은 하는 일이 다르다 — '실사요청 철회' vs '원업체제안 회수'.
//  ★ 공종을 고를 때마다 개산 근거 유무를 말한다. 금액은 만들지 않는다(철칙 3).
//    판정은 서버가 내려 준 need_est 하나만 본다 — 화면이 규칙을 다시 쓰면 갈린다.
ACT.catCoverage = () => {
  const box = document.getElementById('cov_warn');
  const sel = document.getElementById('c_cat');
  if(!box || !sel) return;
  const need = sel.options[sel.selectedIndex]?.dataset?.needest === '1';
  if(!need){ box.style.display = 'none'; box.innerHTML = ''; return; }
  box.style.display = 'block';
  box.innerHTML = `<b>이 공종은 표준단가 개산 근거(레시피)가 없습니다.</b><br>
    사진 없이 접수해 <b>2차 공고</b>로 가면 최소 금액(하한)을 만들 근거가
    <b>가견적뿐</b>입니다. 지금 가견적을 적어 두지 않으면 그때 공고가 막히고,
    가견적 수정은 '입찰중' 에서만 되므로 되돌리기 어렵습니다.`;
};

ACT.caseToDispatch = async (a) => {
  const reason = prompt('전환 사유를 5자 이상 적어 주세요 (예: 포털 계정이 없어 투찰 0건)');
  if(reason === null) return;
  if((reason||'').trim().length < 5){ toast('사유를 5자 이상 적어 주세요.'); return; }
  try{
    const r = await api('POST', `/api/cases/${a}/to-dispatch`, {reason});
    toast(r.message || '전환했습니다.');
    closeModal && closeModal();
    loadView('dispatch');
  }catch(e){ toast(e.message || '전환하지 못했습니다.'); closeModal && closeModal(); loadView('dispatch'); }
};
ACT.coWithdrawReq = async (a) => {
  const reason = prompt('철회 사유를 5자 이상 적어 주세요 (예: 금액 자릿수 오기 — 재접수 예정)');
  if(reason === null) return;
  if((reason||'').trim().length < 5){ toast('사유를 5자 이상 적어 주세요.'); return; }
  try{
    const r = await api('POST', `/api/change-orders/${a}/withdraw`, {reason});
    toast(r.message || '철회했습니다.'); VIEWS.changeorders();
  }catch(e){
    //  ⚠⚠ [라운드503] 형제(coWithdraw 등, 라운드481·486·500·501) 참조 —
    //    catch도 성공 분기와 같이 정리한다.
    toast(e.message || '철회하지 못했습니다.'); VIEWS.changeorders();
  }
};
ACT.obHandled = async (a) => {
    const note = prompt('어떻게 처리하셨나요? (예: 담당자에게 전화 완료)');
    if (note === null) return;
    try{ await api('POST','/api/outbox/'+_n(a)+'/handled', {note}); toast('처리로 기록했습니다'); loadView('outbox'); }
    catch(e){ toast(e.message); }
  };
  ACT.ebSave = async () => {
    const body = {major:$('#eb_major').value, severity:$('#eb_sev').value,
      min_price:digits($('#eb_min').value), max_price:digits($('#eb_max').value),
      src:$('#eb_src').value};
    try{ await api('POST','/api/est-bands', body); toast('기준을 저장했습니다'); loadView('estbands'); }
    catch(e){ toast(e.message); }
  };
  ACT.ebDel = async (a) => {
    if(!confirm('이 기준을 삭제하시겠습니까? 삭제하면 해당 공종은 금액 대조를 하지 않습니다.')) return;
    try{ await api('DELETE','/api/est-bands/'+_n(a)); toast('삭제했습니다'); loadView('estbands'); }
    catch(e){ toast(e.message); }
  };
  ACT.ctSearch = () => ctSearch();
  ACT.aiSetTh = async (a, el) => {
    const v = parseInt(el.value);
    try{
      await api('PATCH','/api/ai/threshold',{threshold:v});
      toast(`자동 승인 기준을 ${v}점으로 바꿨습니다`);
      VIEWS.photos();
    }catch(e){ toast(e.message); VIEWS.photos(); }
  };
  ACT.ctSetType = (a, el) => ctSetType(el.value);
  ACT.ctSetMissing = (a, el) => ctSetMissing(el.value);
  ACT.ctEdit = (a, el, ev, b) => ctEdit(_n(a));
  ACT.ctSave = (a, el, ev, b) => ctSave(_n(a));
  ACT.ctImport = (a, el) => ctImport(a, el);
  ACT.cmNew = () => cmNew();
  ACT.cmPreview = () => cmPreview();
  ACT.cmSave = () => cmSave();
  ACT.cmDetail = (a, el, ev, b) => cmDetail(_n(a));
  ACT.cmCancel = (a, el, ev, b) => cmCancel(_n(a));
  ACT.setDefectFilter = (a, el, ev, b) => setDefectFilter(_n(a), _n(b), el, ev);
  ACT.setLeadFilter = (a, el, ev, b) => setLeadFilter(_n(a), _n(b), el, ev);
  ACT.setPartnerMajor = (a, el, ev, b) => setPartnerMajor(_n(a), _n(b), el, ev);
  ACT.setPtype = (a, el, ev, b) => setPtype(_n(a), _n(b), el, ev);
  ACT.settleReview = (a, el, ev, b) => settleReview(_n(a), _n(b), el, ev);
  ACT.doSettleReview = (a, el, ev, b) => doSettleReview(_n(a), _n(b), el, ev);
  ACT.settlePaid = (a, el, ev, b) => settlePaid(_n(a), _n(b), el, ev);
  ACT.settleFeeCollected = (a) => settleFeeCollected(_n(a));
  ACT.pbSync = () => pbSync();
  ACT.settlePickAll = () => settlePickAll();
  ACT.settlePaidBulk = () => settlePaidBulk();
  ACT.settleTransfer = (a, el, ev, b) => settleTransfer(_n(a), _n(b), el, ev);
  ACT.settleUndo = (a, el, ev, b) => settleUndo(_n(a), _n(b), el, ev);
  ACT.settleVoid = (a) => settleVoid(_n(a));
  ACT.settleExport = () => settleExport();
  ACT.settleDetail = (a) => settleDetail(_n(a));
  ACT.insurerForm = (a, el, ev, b) => insurerForm(_n(a), _n(b), el, ev);
  ACT.saveInsurer = (a, el, ev, b) => saveInsurer(_n(a), _n(b), el, ev);
  ACT.adminForm = (a, el, ev, b) => adminForm(_n(a), _n(b), el, ev);
  ACT.saveAdmin = (a, el, ev, b) => saveAdmin(_n(a), _n(b), el, ev);
  ACT.resetAdminPw = (a, el, ev, b) => resetAdminPw(_n(a), _n(b), el, ev);
  ACT.deleteAdmin = (a, el, ev, b) => deleteAdmin(_n(a), _n(b), el, ev);
  ACT.saveMyName = () => saveMyName();
  ACT.saveMyPw = () => saveMyPw();
  ACT.otpSetup = () => otpSetup();
  ACT.otpConfirm = () => otpConfirm();
  ACT.otpDisable = () => otpDisable();
  ACT.otpCopyCodes = () => {
    const t = (window._otpCodes || []).join('\n');
    if (navigator.clipboard) navigator.clipboard.writeText(t).then(
      () => toast('복구 코드를 복사했습니다'), () => toast('복사하지 못했습니다 — 직접 적어 주세요', true));
    else toast('이 브라우저는 복사를 지원하지 않습니다 — 직접 적어 주세요', true);
  };
  ACT.doCaseSearch = () => doCaseSearch();
  ACT.clearCaseSearch = () => clearCaseSearch();
  //  ⚠⚠ [라운드290] 검색창(searchBar()) 은 클릭(data-arg=view, 1번째 자리)과
  //    Enter(el.value, 1번째 자리 — view 는 이제 4번째) 두 경로로 온다. arg 가
  //    있으면(Enter) 그걸, 없으면(클릭) a 를 view 로 쓴다 — 둘 다 지원해야 한다.
  ACT.runSearch = (a, el, ev, arg) => runSearch(arg != null ? arg : a);
  ACT.clearSearch = (a) => clearSearch(a);
  ACT.drillStage = (a) => drillStage(a);
  ACT.runSweep = async () => {
    try{
      const r = await api('POST','/api/admin/sweep', {});
      toast(r.scanned ? `마감 ${r.closed} · 유찰 ${r.failed} · 재경매 ${r.reauction_closed}`
                      : '마감할 공고가 없습니다');
      VIEWS.dash();
    }catch(e){ toast(e.message); }
  };
  // ⚠ 처리 후 모달을 닫는다. 안 닫으면 방금 바뀐 상태가 아니라 **낡은 화면**이
  //   그대로 남아, 같은 버튼을 다시 눌러 409 를 보게 된다.
  ACT.caseReopen = async (a) => {
    if(!confirm('이 사건의 입찰을 다시 여시겠습니까?')) return;
    try{ const r = await api('POST','/api/cases/'+_n(a)+'/reopen', {});
      closeModal(); toast(`입찰을 재개했습니다 (${r.reopen_count}회차)`); loadView('cases');
    }catch(e){ toast(e.message); closeModal(); loadView('cases'); }
  };
  ACT.caseCloseOffline = async (a) => {
    //  ⚠ 되돌릴 수 없다 — 무엇이 확정되는지 먼저 말한다.
    const reason = prompt('이 사건을 **플랫폼에서 종결**합니다(오프라인 처리로 전환).'
      + String.fromCharCode(10) + '되돌릴 수 없고, 진행중 목록에서 사라집니다.'
      + String.fromCharCode(10) + String.fromCharCode(10) + '사유를 적어 주세요 (5자 이상)');
    if (!reason || reason.trim().length < 5) return;
    try {
      await api('POST', `/api/cases/${_n(a)}/close-offline`, { reason: reason.trim() });
      toast('오프라인 전환으로 종결했습니다.'); closeModal(); loadView('cases');
    } catch (e) { toast(e.message); closeModal(); loadView('cases'); }
  };
  ACT.caseUndoNoRepair = async (a) => {
    const reason = prompt('미수선 종결을 되돌려 「접수」 로 복귀시킵니다.'
      + String.fromCharCode(10) + String.fromCharCode(10) + '사유를 적어 주세요 (5자 이상)');
    if (!reason || reason.trim().length < 5) return;
    try {
      await api('POST', `/api/cases/${_n(a)}/undo-no-repair`, { reason: reason.trim() });
      toast('접수 상태로 되돌렸습니다.'); closeModal(); loadView('cases');
    } catch (e) { toast(e.message); closeModal(); loadView('cases'); }
  };
  ACT.caseFailBidding = async (a) => {
    if(!confirm('유찰로 확정하시겠습니까? 제출된 입찰은 채택되지 않습니다.')) return;
    try{ await api('POST','/api/cases/'+_n(a)+'/fail-bidding', {});
      closeModal(); toast('유찰 처리했습니다'); loadView('cases');
    }catch(e){ toast(e.message); closeModal(); loadView('cases'); }
  };
  // 검수 승인 → 정산 생성. ⚠ 라우트는 있었는데 **호출하는 버튼이 없어서** 콘솔에서
  //   정산을 아예 만들 수 없었다(지급 파이프라인이 시작조차 안 됐다).
  ACT.caseApprove = async (a) => {
    if(!confirm('검수를 승인하고 정산을 생성하시겠습니까?\n\n'
      + '· 사진 검수가 통과된 사건만 승인됩니다.\n'
      + '· 낙찰 확정가를 기준으로 수수료가 계산됩니다.')) return;
    try{
      const r = await api('POST','/api/cases/'+_n(a)+'/approve', {});
      closeModal();
      toast(`검수 승인 · 정산을 만들었습니다 — 공사대금 ${won(r.amount)}원 · `
          + `수수료 ${won(r.fee)}원 · 지급 ${won(r.payout)}원`);
      loadView('settle'); refreshBadges();
    }catch(e){ toast(e.message); closeModal(); loadView('settle'); refreshBadges(); }
  };
  // 낙찰 취소 — 부도·잠적·착공거부로 '시공중'에 묶인 사건을 되살린다
  ACT.caseRenotify = async (a) => {
    /*  알림을 다시 보낼 뿐이지만, 협력사 전체에게 나가는 일이라 한 번 묻는다.
        서버가 30분 잠금·마감 확인을 다시 판정한다(여기 판정은 편의일 뿐). */
    if(!confirm('열려 있는 공고를 협력사에게 다시 알립니다.\n'
      + '너무 잦은 알림은 업체가 알림을 꺼 버리게 만듭니다 — 정말 보낼까요?')) return;
    try{
      const r = await api('POST','/api/cases/'+_n(a)+'/renotify', {});
      toast(esc(r.message || '다시 알렸습니다.'));
    }catch(e){ toast(esc(e.message)); }
  };
  ACT.caseCancelAward = async (a) => {
    const reason = prompt('낙찰을 취소하고 재공고합니다.\n'
      + '사유를 5자 이상 남겨 주세요 (예: 낙찰업체 연락 불가로 착공 불가).');
    if(reason===null) return;
    if(reason.trim().length<5){ toast('사유를 5자 이상 입력해 주세요.'); return; }
    try{
      const r = await api('POST','/api/cases/'+_n(a)+'/cancel-award', {reason:reason.trim()});
      closeModal(); toast(r.message); loadView('cases'); refreshBadges();
    }catch(e){ toast(e.message); closeModal(); loadView('cases'); refreshBadges(); }
  };
  ACT.coFailAdd = async (a) => {
    if(!confirm('추가분 경매를 유찰로 확정하시겠습니까? 이후 전체 재경매를 열 수 있습니다.')) return;
    try{ const r = await api('POST','/api/change-orders/'+_n(a)+'/fail-add', {});
      toast(`추가분 유찰 처리했습니다 (입찰 ${r.bid_count}건)`); loadView('changeorders');
    }catch(e){
      //  ⚠⚠ [라운드503] 형제(caseCancelAward, 바로 위) 참조 — catch도 성공
      //    분기와 같이 정리한다.
      toast(e.message); loadView('changeorders');
    }
  };
  ACT.drillAction = (a) => { const fn=ACTION_DRILL[a]; if(fn) fn(); else loadView(ACTION_MENU[a]||'dash'); };
  ACT.drillMoney = (a) => drillMoney(a);           // 금액 카드 → 그 금액을 이룬 정산 내역
  ACT.clearMoneyDrill = () => clearMoneyDrill();
  ACT.drillCases = (a) => drillCases(a);
  ACT.drillSaving = () => drillSaving();
  ACT.coAddAuction = (a) => coAddAuction(_n(a));
  ACT.coOffer = (a) => coOffer(_n(a));
  ACT.coWithdraw = (a) => coWithdraw(_n(a));      // 원업체제안 교착 탈출
  ACT.defectNew = () => defectNew();               // 운영팀 대리 하자 접수
  ACT.defectNewSearch = (v) => defectNewSearch(v);
  ACT.defectNewPick = (a) => defectNewPick(a);
  ACT.defectNewSubmit = () => defectNewSubmit();
  ACT.auctionDeadline = (a, el, ev, b) => auctionDeadline(_n(a), b);   // 입찰 마감 변경
  ACT.coFullReauction = (a) => coFullReauction(_n(a));
  ACT.coCloseFull = (a) => coCloseFull(_n(a));
  ACT.coAwardFull = (a) => coAwardFull(_n(a));
  ACT.coFailFull = (a) => coFailFull(_n(a));
  //  ⚠⚠ [라운드290] 메모입력칸도 검색창과 같은 구조(클릭=data-arg 1번째,
  //    Enter=el.value 1번째·arg 는 4번째)라 같은 방식으로 고친다.
  ACT.addMemo = (a, el, ev, arg) => addMemo(arg != null ? arg : a);
  ACT.memoDone = (a, el, ev, b) => memoDone(_n(a), b);
  ACT.memoDel = (a, el, ev, b) => memoDel(_n(a), b);
  ACT.moneyInput = (a, el) => fmtMoney(el);
  ACT.appIntakeForm = () => appIntakeForm();
  ACT.saveIntake = () => saveIntake();
  ACT.issueCred = (a, el, ev, b) => issueCred(_n(a), _n(b), el, ev);
  ACT.credCopy = async () => {
    if(!CRED_TEXT){ toast('복사할 안내문이 없습니다.'); return; }
    try{
      await navigator.clipboard.writeText(CRED_TEXT);
      toast('안내문을 복사했습니다. 업체에 안전한 경로로 보내 주세요.');
    }catch(e){
      //  클립보드가 막힌 환경(비-HTTPS 등) — 직접 고를 수 있게 펼쳐 준다
      const ta = document.createElement('textarea');
      ta.value = CRED_TEXT;
      ta.style.cssText = 'width:100%;min-height:150px;margin-top:6px;font-size:.75rem';
      const box = $('#credbox'); if(box) box.appendChild(ta);
      ta.select();
      toast('자동 복사가 막혀 있습니다 — 아래 상자의 내용을 직접 복사해 주세요.');
    }
  };
  ACT.auditSearch = () => {
    AUDIT.q = (($('#au_q')||{}).value||'').trim();
    AUDIT.action = ($('#au_act')||{}).value || '';
    AUDIT.from = ($('#au_from')||{}).value || '';
    AUDIT.to = ($('#au_to')||{}).value || '';
    AUDIT.limit = 100;
    renderAudit();
  };
  ACT.auditClear = () => {
    AUDIT.q=''; AUDIT.action=''; AUDIT.from=''; AUDIT.to=''; AUDIT.limit=100;
    ['au_q','au_from','au_to'].forEach(id=>{ const e=$('#'+id); if(e) e.value=''; });
    const s=$('#au_act'); if(s) s.value='';
    renderAudit();
  };
  //  서버 상한이 2000 이다 — 그 위로는 올리지 않는다(올려도 잘려서 거짓말이 된다)
  ACT.auditMore = () => { AUDIT.limit = Math.min(AUDIT.limit + 400, 2000); renderAudit(); };
  //  ⚠ 화면의 조건을 그대로 싣는다(limit 은 뺀다 — 파일은 화면보다 넉넉히 담는다)
  ACT.auditExport = () => {
    const qs = new URLSearchParams();
    if(AUDIT.q) qs.set('q', AUDIT.q);
    if(AUDIT.action) qs.set('action', AUDIT.action);
    if(AUDIT.from) qs.set('from', AUDIT.from);
    if(AUDIT.to) qs.set('to', AUDIT.to);
    location.href = '/api/activity/export' + (qs.toString() ? '?'+qs : '');
  };
  ACT.selfRun = () => VIEWS.selfcheck();
  ACT.unlockLogin = async () => {
    const el = $('#unlock_uname');
    const uname = ((el||{}).value||'').trim();
    if(!uname){ toast('아이디를 입력해 주세요'); return; }
    try{
      const r = await api('POST','/api/login-attempts/unlock', {username: uname});
      //  ⚠ "잠겨 있지 않았다"고 단정하지 않는다 — 서버가 아는 네 창구(관리자·협력사·
      //    보험사·OTP) 밖의 잠금이면 여기서도 0건이 나온다. 사실만 말한다(실측:
      //    이 단정 때문에 운영자가 실제로 잠긴 계정 조사를 여기서 멈췄었다).
      toast(r.cleared > 0
        ? `<b>${esc(uname)}</b> 잠금을 해제했습니다 (실패기록 ${r.cleared}건 삭제)`
        : `<b>${esc(uname)}</b> — 남은 실패 기록이 없습니다`);
      if(el) el.value = '';
    }catch(e){ toast(esc(e.message||'해제하지 못했습니다')); }
  };
  ACT.onbStage  = (a) => { ONB.stage = a; VIEWS.onboard(); };
  ACT.onbPtype  = () => { ONB.ptype = ($('#onb_pt')||{}).value || '전체'; VIEWS.onboard(); };
  ACT.onbSearch = () => {
    ONB.q = (($('#onb_q')||{}).value||'').trim();
    ONB.region = (($('#onb_rg')||{}).value||'').trim() || '전체';
    VIEWS.onboard();
  };
  ACT.onbExport = () => {
    /*  ⚠ 화면에 걸린 조건을 **그대로** 실어 보낸다(limit 만 뺀다 —
        파일은 화면보다 넉넉히 담는다). 조건을 안 실으면 화면과 다른
        모집단이 나오고, 받은 사람은 그걸 알 방법이 없다. */
    const qs = new URLSearchParams();
    if(ONB.stage !== '전체') qs.set('stage', ONB.stage);
    if(ONB.q) qs.set('q', ONB.q);
    if(ONB.region !== '전체') qs.set('region', ONB.region);
    if(ONB.ptype !== '전체') qs.set('ptype', ONB.ptype);
    window.location = '/api/partner-onboarding/export?' + qs.toString();
  };
  ACT.onbAll = () => {
    const cks = document.querySelectorAll('.onb-ck');
    const on = [...cks].some(c => !c.checked);   // 하나라도 안 켜졌으면 전부 켠다
    cks.forEach(c => { c.checked = on; });
  };
  const onbPicked = () => [...document.querySelectorAll('.onb-ck:checked')].map(c => +c.value);

  ACT.onbIssue = async () => {
    const ids = onbPicked();
    if(!ids.length){ toast('업체를 먼저 고르세요'); return; }
    /*  ⚠ 임시 비밀번호가 **딱 한 번만** 나온다는 것을 누르기 전에 알린다 —
        모르고 창을 닫으면 재발급밖에 방법이 없다. */
    if(!confirm(ids.length + '곳에 계정을 만듭니다.\n\n'
      + '임시 비밀번호는 이 뒤 화면에 한 번만 표시됩니다. 창을 닫으면 다시 볼 수 없습니다.\n'
      + '이미 계정이 있는 업체는 건드리지 않습니다.')) return;
    let d;
    try{ d = await api('POST','/api/partners/bulk-credentials',{ids}); }
    catch(e){ toast('발급 실패 — '+esc(e.message)); return; }
    onbShowCreds(d);
  };

  ACT.onbInvite = async () => {
    const ids = onbPicked();
    if(!ids.length){ toast('업체를 먼저 고르세요'); return; }
    let d;
    try{ d = await api('POST','/api/partners/invite',{ids}); }
    catch(e){ toast('처리 실패 — '+esc(e.message)); return; }
    toast((d.notify_live
        ? `${d.marked.length}곳 안내 표시 · 실제 발송 ${d.sent}건`
        : `${d.marked.length}곳 '안내함'으로 표시 (문자 발송은 꺼져 있습니다)`)
      + (d.skipped.length ? ` · 건너뜀 ${d.skipped.length}곳` : ''));
    VIEWS.onboard();
  };

  ACT.onbCredCsv = () => {
    if(!ONB_CREDS.length){ toast('내려받을 내용이 없습니다'); return; }
    /*  엑셀이 한글을 깨뜨리지 않게 BOM 을 붙이고, 값의 큰따옴표를 이스케이프한다. */
    const q = (s) => '"' + String(s==null?'':s).replace(/"/g,'""') + '"';
    const csv = '\ufeff' + ['업체명,아이디,임시비밀번호'].concat(
      ONB_CREDS.map(r => [r.name, r.login_id, r.temp_password].map(q).join(','))).join('\r\n');
    const url = URL.createObjectURL(new Blob([csv], {type:'text/csv;charset=utf-8'}));
    const a = document.createElement('a');
    a.href = url; a.download = 'bokguon_partner_credentials.csv';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(url), 1000);
    toast('내려받았습니다 — 전달한 뒤 파일을 지워 주세요');
  };
  ACT.licFilter = (a) => { LIC.status = a; VIEWS.license(); };
  ACT.licPtype = () => { LIC.ptype = ($('#lic_pt')||{}).value || '전체'; VIEWS.license(); };
  ACT.licSearch = () => { LIC.q = (($('#lic_q')||{}).value||'').trim(); VIEWS.license(); };
  ACT.licCopy = async (a) => {
    const row = document.getElementById('lic-'+a);
    const nm = row ? row.querySelector('b').textContent.trim() : '';
    try{ await navigator.clipboard.writeText(nm); toast(`<b>${esc(nm)}</b> 복사됨 — 조회창에 붙여넣으세요`); }
    catch(e){ toast('복사가 막혀 있습니다 — 업체명을 직접 입력해 주세요'); }
  };
  //  ⚠ 처리한 행은 **그 자리에서 사라진다**(미확인 목록일 때). 목록 전체를 다시
  //    그리면 스크롤이 맨 위로 튀어 어디까지 했는지 잃는다 — 398건짜리 작업에서는
  //    그것만으로 사람이 포기한다.
  ACT.licSet = async (a, el, ev, b) => {
    const pid = _n(a), st = b;
    const bz = (($('#lb-'+pid)||{}).value||'').trim();
    const no = (($('#ln-'+pid)||{}).value||'').trim();
    if(st === '등록확인' && !no){
      toast('등록확인으로 기록하려면 <b>등록번호</b>를 함께 적어 주세요 (KISCON 조회값)');
      const f = $('#ln-'+pid); if(f) f.focus();
      return;
    }
    const _licBody = {license_status: st, license_no: no, biz_no: bz};
    try{
      await api('POST', `/api/partners/${pid}/license`, _licBody);
    }catch(e){
      //  ⚠⚠ [라운드476] licenseSave()와 같은 이유로 같은 재확인을 이 대량조사
      //    화면에도 그대로 이식 — 여기가 오히려 더 위험하다(398건을 빠르게
      //    훑는 화면이라 진행 중 사건이 있는 업체를 멈춰서 보지 않으면
      //    지나치기 쉽다). 서버가 써 준 error 문구를 그대로 보여준다(demote
      //    Confirm()의 고정 문구는 login/완료보고가 막힌다고 하는데 license_
      //    status 는 그렇지 않아 여기엔 안 맞는다).
      if(e && e.data && e.data.code === 'PARTNER_HAS_WORK' && confirm(e.data.error)){
        try{
          await api('POST', `/api/partners/${pid}/license`, {..._licBody, confirm_license:true});
        }catch(e2){ toast(e2.message || '기록하지 못했습니다.'); return; }
      } else {
        toast(e.message || '기록하지 못했습니다.'); return;
      }
    }
    const row = document.getElementById('lic-'+pid);
    if(row && LIC.status === '미확인'){ row.remove(); }
    else if(row){ row.querySelector('.pill').textContent = st; }
    toast(`<b>${esc(st)}</b>(으)로 기록했습니다`);
    //  진행률만 조용히 갱신한다 — 목록은 그대로 두어 하던 자리를 잃지 않게
    try{
      const g = (await api('GET','/api/license-survey?status=미확인&limit=1')).progress || {};
      const bar = document.querySelector('#content .panel div[style*="width:"]');
      if(bar) bar.style.width = (g.pct||0) + '%';
      const badge = $('#bdg-license');
      if(badge){ badge.textContent = g.todo || ''; badge.style.display = g.todo?'':'none'; }
    }catch(e){}
  };
  ACT.exportXlsx = (a, el, ev, b) => {
    //  화면에 걸린 필터를 그대로 실어 보낸다 — 목록이 쓰는 QS 빌더와 같다.
    //  ⚠⚠ [라운드104] 정산 드릴다운(settleMoney)을 빼먹고 있었다 — "「업체 지급
    //    예정」 카드와 같은 조건" 이라는 화면 배너를 믿고 내보내기를 누르면
    //    실제로는 그 조건 없이 전체 정산이 나갔다(서버 _settle_filter 는 이제
    //    money 를 받는다 — 여기서도 목록(VIEWS.settle)과 같이 실어 보낸다).
    const settleQS = () => { const q = searchQS('settle'); if (settleMoney) q.set('money', settleMoney); return q; };
    //  ⚠⚠ [라운드142] 하자·입점신청·도입문의는 서버가 필터를 안 받던 시절 헷갈리지
    //    않게 QS 를 아예 빼 뒀었다 — 이제 서버(_defect_filter 등)가 받으니 목록과
    //    같은 QS 빌더를 그대로 쓴다. VIEWS 키와 검색상태 키가 다른 자리에 주의:
    //    입점신청은 라우트/내보내기는 'applications' 지만 검색상태는 'apps' 다.
    const defectQS = () => { const q = searchQS('defects'); if (defectFilter !== '전체') q.set('status', defectFilter); return q; };
    const leadQS = () => { const q = searchQS('leads'); if (leadFilter !== '전체') q.set('status', leadFilter); return q; };
    const appQS = () => { const q = searchQS('apps'); if (appFilter !== '전체') q.set('status', appFilter); return q; };
    const q = (a === 'cases') ? caseQS().toString()
            : (a === 'partners') ? partnerQS().toString()
            : (a === 'settlements') ? settleQS().toString()
            : (a === 'defects') ? defectQS().toString()
            : (a === 'leads') ? leadQS().toString()
            : (a === 'applications') ? appQS().toString() : '';
    location.href = '/api/export/'+encodeURIComponent(a) + (q ? '?'+q : '');
  };
  ACT.caseDetail = (a, el, ev, b) => caseDetail(_n(a), _n(b), el, ev);
  ACT.saveCaseEdit = (a, el, ev, b) => saveCaseEdit(_n(a), _n(b), el, ev);
})();
