/* 못 올린 현장 사진을 기기에 남겨 둔다.
 *
 *  왜 필요한가 —
 *   현장은 신호가 나쁘다. 업로드가 실패하면 지금까지는 실패한 파일을 JS 변수에만
 *   들고 있다가 토스트로 '다시 올리기'를 띄웠다. 그런데 작업자가 앱을 닫거나,
 *   폰이 잠겨 앱이 내려가거나, 토스트가 사라지면 **그 사진들은 그대로 없어진다.**
 *   본인은 올린 줄 알고 현장을 뜬다. 다시 찍으러 갈 수 없는 사진도 있다.
 *
 *  그래서 실패분을 IndexedDB 에 넣어 둔다. 파일(Blob)은 구조화 복제로 그대로
 *  저장되므로 재인코딩이 필요 없다. 앱을 다시 열면 남은 게 있는지 보고 알린다.
 *
 *  ⚠ 성공한 사진은 큐에 넣지 않는다. 서버에 이미 있는 것을 또 올리면 중복이 된다.
 */
(function () {
  'use strict';
  var DB = 'bokguon-upq', STORE = 'photos', VER = 1;

  function open() {
    return new Promise(function (res, rej) {
      if (!window.indexedDB) return rej(new Error('no-idb'));
      var r = indexedDB.open(DB, VER);
      r.onupgradeneeded = function () {
        var d = r.result;
        if (!d.objectStoreNames.contains(STORE)) {
          d.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
        }
      };
      r.onsuccess = function () { res(r.result); };
      r.onerror = function () { rej(r.error); };
    });
  }

  function tx(mode, fn) {
    return open().then(function (d) {
      return new Promise(function (res, rej) {
        var t = d.transaction(STORE, mode), out = fn(t.objectStore(STORE));
        t.oncomplete = function () { d.close(); res(out && out.result !== undefined ? out.result : out); };
        t.onerror = function () { d.close(); rej(t.error); };
      });
    });
  }

  var UPQ = {
    //  브라우저가 IndexedDB 를 막아 둔 경우(사생활 보호 모드 등)에도 죽지 않는다.
    //  그때는 종전처럼 메모리 재시도만 동작한다 — 기능이 줄 뿐 깨지지는 않는다.
    ok: !!window.indexedDB,

    //  ⚠ **저장한 id 배열을 돌려준다.** 예전에는 장수만 돌려줘서,
    //    "보내기 전에 먼저 저장하고 성공한 것만 지운다"를 할 수 없었다.
    //    그래서 저장이 전송 루프 **뒤**에 있었고, 그 사이 앱이 내려가면
    //    카메라에서 갓 찍은 사진이 기기에도 서버에도 남지 않았다.
    //  ⚠ 이 기기를 **누가 쓰고 있는지**를 함께 적는다.
    //    같은 폰·PC 를 두 업체가 번갈아 쓰거나(운영자가 계정을 바꿔 가며 확인할 때가 그렇다)
    //    로그아웃 후 다른 계정으로 들어오면, 남의 업체가 못 올린 사진이 내 배너에 뜬다.
    //    지우지는 않는다 — 지우면 다시 못 찍는 사진을 잃는다. **가려서 보여 줄 뿐이다.**
    who: null,
    setWho: function (partnerId) { UPQ.who = partnerId == null ? null : String(partnerId); },

    put: function (caseId, files, caseNo) {
      if (!UPQ.ok || !files || !files.length) return Promise.resolve([]);
      var ids = [];
      return tx('readwrite', function (s) {
        for (var i = 0; i < files.length; i++) {
          (function (req, idx) {
            req.onsuccess = function () { ids[idx] = req.result; };
            //  ⚠⚠ [라운드204] onerror 가 없으면 IndexedDB 스펙상 이 요청의 실패가
            //    트랜잭션 전체를 abort 시켜, 이미 add() 성공한 앞선 파일들까지
            //    전부 롤백된다(30장 중 1장만 용량초과여도 29장 전부 저장 실패).
            //    preventDefault() 로 "이 요청의 실패는 처리했다"고 알려 트랜잭션이
            //    나머지 파일을 계속 진행·커밋하게 한다 — 이 파일 하나만 ids[idx]가
            //    비고, 나머지는 정상 저장된다. 호출부(uploadPhotos)는 이미 qids[j]
            //    != null 로 "이 파일이 큐에 있는지"를 매번 확인하므로, 이렇게 생긴
            //    빈 자리도 별도 수정 없이 "못 큐잉됨"으로 올바르게 처리된다.
            req.onerror = function (ev) { ev.preventDefault(); };
          })(s.add({ caseId: caseId, caseNo: caseNo || '', blob: files[i],
                     name: files[i].name || 'photo.jpg', ts: Date.now(),
                     who: UPQ.who }), i);
        }
      }).then(function () { return ids; }).catch(function () { return []; });
    },

    all: function () {
      if (!UPQ.ok) return Promise.resolve([]);
      return tx('readonly', function (s) { return s.getAll(); })
        .then(function (rows) {
          if (!UPQ.who) return rows;
          //  who 가 없는 옛 항목은 남겨 둔다(잃는 것보다 낫다). 남의 것만 가린다.
          return (rows || []).filter(function (r) { return !r.who || r.who === UPQ.who; });
        })
        .catch(function () { return []; });
    },

    count: function () { return UPQ.all().then(function (a) { return a.length; }); },

    remove: function (ids) {
      if (!UPQ.ok || !ids || !ids.length) return Promise.resolve();
      return tx('readwrite', function (s) {
        for (var i = 0; i < ids.length; i++) s.delete(ids[i]);
      }).catch(function () {});
    },

    //  큐에 남은 사진을 사건별로 묶어 준다(사건마다 따로 올려야 하므로).
    grouped: function () {
      return UPQ.all().then(function (rows) {
        var m = {};
        rows.forEach(function (r) {
          (m[r.caseId] = m[r.caseId] || { caseId: r.caseId, caseNo: r.caseNo, items: [] })
            .items.push(r);
        });
        return Object.keys(m).map(function (k) { return m[k]; });
      });
    }
  };

  window.UPQ = UPQ;
})();
