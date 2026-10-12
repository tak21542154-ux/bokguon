// 공개 신청 폼 공용 유틸
// [보안] HTML 이스케이프 — innerHTML 로 서버 데이터를 그릴 때 반드시 통과시킬 것.
//        보험사가 입력한 공종·지역 문자열이 그대로 렌더되면 저장형 XSS 가 된다.
//
// ⚠ 여기서 `const esc = ...` 로 선언하면 안 된다.
//    포털 화면들도 각자 인라인 스크립트에서 같은 이름을 선언하고 있어서,
//    두 개의 클래식 스크립트가 같은 전역 렉시컬 스코프에 const 를 중복 선언하게 된다.
//    그러면 **나중 스크립트가 통째로 실행되지 않고**(SyntaxError) 화면이 '불러오는 중…'
//    에서 멈춘다. 콘솔을 열지 않으면 원인을 찾기 어려운 종류의 고장이다.
//    window 속성으로 두면 중복 선언 문제가 생기지 않는다.
if (typeof window.esc !== 'function') {
  window.esc = function (s) {
    return (s == null ? '' : String(s)).replace(/[&<>"']/g,
      function (c) {
        return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
      });
  };
}
function val(id){ const e=document.getElementById(id); return e ? (e.value||'').trim() : ''; }
function toast(msg){
  const t=document.getElementById('toast'); if(!t)return;
  t.innerHTML=msg; t.classList.add('show');
  clearTimeout(t._h); t._h=setTimeout(()=>t.classList.remove('show'),3000);
}
async function postForm(url, body, onOk){
  const btn=document.querySelector('button[type=submit]');
  //  ⚠ 원래 글자를 기억해 둔다 — 실패해도 '전송 중…' 이 그대로 남아 있으면
  //    누를 수 있는 버튼인데 아직 처리 중인 것처럼 보여 사람을 기다리게 한다.
  const label = btn ? btn.textContent : '';
  const restore = () => { if(btn){ btn.disabled=false; btn.textContent=label; } };
  if(btn){btn.disabled=true;btn.textContent='전송 중…';}
  try{
    const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json().catch(()=>({}));
    if(r.ok && d.ok){ onOk(d); }
    else{ toast(d.error||'제출에 실패했습니다. 잠시 후 다시 시도해 주세요.'); restore(); }
  }catch(e){ toast('네트워크 오류입니다. 연결을 확인한 뒤 다시 눌러 주세요.'); restore(); }
}
function successHTML(title, sub){
  return `<div class="success-box">
    <div class="ico">✓</div>
    <h2>${title}</h2>
    <p>${sub}</p>
    <div style="margin-top:26px"><a class="btn p" href="/">홈으로 돌아가기</a></div>
  </div>`;
}

// ══════════════════════════════════════════════════════════════
//  개인정보 수집·이용 동의 (개인정보 보호법 §15①1 · §22 / 정보통신망법 §50)
//
//  두 폼(보험사 도입문의 · 협력업체 입점신청)이 같은 블록을 쓴다.
//  수집 항목은 실제 서버가 저장하는 컬럼과 일치해야 한다 — 바뀌면 legal_docs.py 도 함께 고칠 것.
// ══════════════════════════════════════════════════════════════
const CONSENT_SPEC = {
  insurer: {
    purpose: '서비스 도입 문의에 대한 상담 회신 및 제휴 협의',
    items: '기관명, 기관 유형, 담당자 성명, 직함, 연락처, 이메일 <span style="color:var(--faint)">(선택: 관심 분야, 문의 내용)</span>',
    period: '수집일로부터 <b>1년</b> — 제휴 계약 체결 시 계약 종료 후 5년'
  },
  partner: {
    purpose: '입점 신청 접수, 자격(면허·보험·장비) 검증, 승인 여부 통지',
    items: '업체명, 업체 구분, 사업자등록번호, 대표자 성명, 연락처, 이메일, 주력 공종, 활동 권역, 사업장 주소(위치정보 포함), 대표 외 상시 인력 수 <span style="color:var(--faint)">(선택: 세부 취급 품목, 면허·등록업종, 면허·보험 보유 여부, 보유 장비, 문의 내용)</span>',
    period: '수집일로부터 <b>1년</b> — 입점 승인 시 거래 종료 후 5년'
  }
};

function consentBlock(kind){
  const s = CONSENT_SPEC[kind];
  return `
  <div class="consent" id="consentBox">
    <h4>🔒 개인정보 수집·이용 동의</h4>
    <table>
      <tr><th>수집·이용 목적</th><td>${s.purpose}</td></tr>
      <tr><th>수집 항목</th><td>${s.items}</td></tr>
      <tr><th>보유·이용 기간</th><td>${s.period}</td></tr>
    </table>
    <label class="agree" for="agree_privacy">
      <input type="checkbox" id="agree_privacy">
      <span class="tag req">필수</span>
      <span>위와 같이 개인정보를 수집·이용하는 데 동의합니다.</span>
    </label>
    <label class="agree" for="agree_marketing">
      <input type="checkbox" id="agree_marketing">
      <span class="tag opt">선택</span>
      <span>복구온의 서비스 소식·자료를 이메일/문자로 받아보겠습니다. <span style="font-weight:600;color:var(--sub)">(동의하지 않아도 신청은 정상 접수됩니다. 언제든 수신을 거부할 수 있습니다.)</span></span>
    </label>
    <p class="more">
      동의를 거부할 권리가 있으나, <b>필수 항목에 동의하지 않으면 신청을 접수할 수 없습니다.</b>
      자세한 내용은 <a href="/legal/privacy" target="_blank" rel="noopener">개인정보 처리방침</a>을 확인해 주세요.
    </p>
  </div>`;
}

/** 필수 동의 검증. 통과하면 서버로 보낼 동의 값을 반환, 실패하면 null. */
function consentValues(){
  const box = document.getElementById('consentBox');
  const req = document.getElementById('agree_privacy');
  if(!req || !req.checked){
    if(box){
      box.classList.add('err');
      box.scrollIntoView({behavior:'smooth', block:'center'});
      setTimeout(()=>box.classList.remove('err'), 2600);
    }
    toast('개인정보 수집·이용에 대한 <b>필수 동의</b>가 필요합니다.');
    return null;
  }
  return {
    agree_privacy: true,
    agree_marketing: document.getElementById('agree_marketing').checked
  };
}
