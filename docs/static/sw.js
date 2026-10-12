/* 복구온 서비스워커 — 설치형 앱(PWA)의 오프라인 셸.
 *  원칙(보안·최신성):
 *   · GET 이 아닌 요청(로그인·입찰·정산 등 쓰기)은 절대 가로채지 않는다.
 *   · /api/* 응답은 캐시하지 않는다 — 세션·정산·사건은 항상 최신·인증 경로로.
 *   · /static/* (버전 쿼리 ?v= 로 캐시버스팅되는 자산)만 캐시 우선으로 빠르게 연다.
 *   · 문서(HTML)는 네트워크 우선. 오프라인이면 안내 셸을 보여준다(포털은 로그인 필요).
 */
/* 캐시 이름에 앱 버전이 들어간다 — 서버(app.py service_worker)가 내려보낼 때
 * __APP_VERSION__ 을 실제 값으로 바꿔 준다. 버전이 오르면 이름이 달라지므로
 * activate 단계에서 옛 캐시가 통째로 지워지고 새 화면이 뜬다.
 * (파일에 v1 로 고정해 두면 배포해도 폰에 옛 화면이 남는다) */
const APP_VERSION = '__APP_VERSION__';
const BUILD = '__BUILD__';
const CACHE = 'bokguon-' + APP_VERSION + '-' + BUILD;
/* [라운드577] style.css·fonts.css·actions.js·form.js 는 실제로는 항상
 * ?v=<해시> 가 붙어 요청된다(app.py asset() — 배포 후 옛 캐시를 계속 쓰지
 * 않도록 모든 템플릿이 이 헬퍼로만 링크를 건다). Cache API 의 match/addAll
 * 은 기본적으로 쿼리스트링까지 정확히 같아야 같은 키로 본다(ignoreSearch
 * 미사용) — 그래서 여기 이 배열에 물음표 없는 맨 경로를 넣으면, install
 * 단계가 캐시에 넣는 키(물음표 없음)와 실제 fetch 핸들러가 찾는 키(물음표+
 * 해시)가 영영 어긋나 이 4개는 매번 캐시미스로 새로 받아온다 — precache 가
 * 존재 이유를 못 한다(오프라인 셸이 빨리 뜬다는 이 파일 자신의 설명과 어긋남).
 * icon-192.png·offline 은 물음표 없이 그대로 요청되므로 문제 없다.
 * app.py service_worker() 가 이 자리표시자를 asset() 실제 값으로 채운다 —
 * 페이지가 링크를 만들 때 쓰는 것과 같은 단일 소스라 항상 같은 키가 된다. */
const PRECACHE = [
  '__ASSET_STYLE_CSS__',
  '__ASSET_FONTS_CSS__',
  '__ASSET_ACTIONS_JS__',
  '__ASSET_FORM_JS__',
  '/static/icons/icon-192.png',
  '/offline',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

/* 화면이 "지금 깔린 앱이 몇 버전이냐"고 물어보면 알려 준다 */
self.addEventListener('message', (e) => {
  if (e.data === 'version' && e.source) {
    e.source.postMessage({ type: 'sw-version', version: APP_VERSION, build: BUILD, cache: CACHE });
  }
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;                       // 쓰기 요청은 네트워크 그대로
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;        // 외부 출처는 건드리지 않음
  //  ⚠ API 는 원칙적으로 캐시하지 않는다(인증·최신성). 딱 하나 예외 —
  //    **이미 수락한 출동**은 신호가 끊기면 주소도 기한도 화면에서 사라졌다.
  //    현장으로 가는 길에 지하주차장·산간에서 앱을 열면 아무것도 없다.
  //    그래서 협력사 대시보드만 '네트워크 우선 + 마지막 사본' 으로 둔다.
  //    · 성공하면 항상 새 값을 쓰고 사본을 갱신한다(오래된 값이 이길 일 없음)
  //    · 실패했을 때만 마지막 사본을 돌려준다 — 화면이 비는 것보다 낫다
  //    · 사본에는 X-From-Cache 를 붙여, 화면이 "이건 마지막 사본이다"를 알 수 있게 한다
  //  ★ 출동 목록도 지킨다. 기사가 신호 없는 지하주차장에서 화면을 열면
  //    '내가 맡은 출동'과 그 **주소**가 통째로 사라져, 어디로 가야 하는지도 모르게 된다.
  if (url.pathname === '/api/partner/dashboard' ||
      url.pathname === '/api/partner/dispatches') {
    e.respondWith(
      fetch(req).then((res) => {
        if (res && res.ok) {
          const copy = res.clone();
          //  ⚠ respondWith() 의 생명연장은 res 를 반환하는 순간까지만이다 — 이
          //    캐시쓰기를 waitUntil() 로 따로 묶지 않으면, 응답이 화면에 간 직후
          //    브라우저가(특히 신호 나쁜 현장의 모바일 배터리 절약 정책상) 이
          //    서비스워커를 바로 종료시켜 아직 안 끝난 캐시쓰기가 통째로 사라질
          //    수 있다 — 정작 신호가 끊겼을 때 돌려줄 "마지막 사본"이 애초에
          //    저장 안 된 상태로 남는다(이 캐시블록 전체의 존재 이유를 무너뜨림).
          e.waitUntil(caches.open(CACHE).then((c) => c.put(req, copy)));
        }
        return res;
      }).catch(() =>
        caches.match(req).then((hit) => {
          if (!hit) throw new Error('offline-no-cache');
          const h = new Headers(hit.headers);
          h.set('X-From-Cache', '1');
          return hit.blob().then((b) => new Response(b, { status: 200, headers: h }));
        })
      )
    );
    return;
  }
  if (url.pathname.startsWith('/api/')) return;           // 그 외 API 는 캐시 금지

  // 정적 자산: 캐시 우선(있으면 즉시, 없으면 받아 저장)
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(req).then((hit) =>
        hit || fetch(req).then((res) => {
          const copy = res.clone();
          e.waitUntil(caches.open(CACHE).then((c) => c.put(req, copy)));   // 위와 같은 이유
          return res;
        }).catch(() => hit))
    );
    return;
  }

  // 문서/그 외: 네트워크 우선, 오프라인이면 안내 셸
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).catch(() => caches.match('/offline')));
  }
});
