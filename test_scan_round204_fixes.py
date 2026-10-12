# -*- coding: utf-8 -*-
"""스캔 204라운드 회귀 — 현장 사진 업로드 실패 안전망의 두 가지 구멍.

  (a) static/upqueue.js: UPQ.put() 의 IndexedDB 트랜잭션에서 s.add() 요청마다
      onerror 가 없었다. IndexedDB 스펙상 처리 안 된 요청 오류는 트랜잭션
      전체를 abort 시켜 **이미 성공한 이전 add() 까지 전부 롤백**된다 —
      30장 배치 중 1장만 저장공간 부족으로 실패해도 29장 전부 못 큐잉된다.
      요청마다 onerror(ev=>ev.preventDefault())를 달아 그 요청 하나만 실패
      처리되고 트랜잭션은 나머지를 계속 커밋하게 했다.

  (b) templates/partner_portal.html uploadPhotos(): 위 (a) 등으로 최초
      UPQ.put() 자체가 실패하면(qids=[]) 이후 네트워크 전송까지 실패해도
      재큐잉 조건(retryFiles && !qids.length)이 retryFiles(재시도 호출)만
      보고 최초 호출을 걸러내 버려, 실패한 사진이 기기 큐에 전혀 안 들어간
      채 메모리(UP_RETRY)에만 남았다 — 재시도 버튼을 누르기 전에 탭이
      죽으면 사진이 기기·서버 어디에도 없이 사라진다. 조건을 "실패분 중
      큐 id 를 하나도 확보 못한 경우"(!failIds.length)로 바꿔, 최초/재시도
      호출 여부와 무관하게 항상 다시 채워 넣게 했다.

  둘 다 Node.js 로 실제 실행해 검증한다 — (a)는 최소 가짜 IndexedDB로 실제
  트랜잭션 abort/계속 동작을, (b)는 원본 조건문 블록을 그대로 뽑아 여러
  입력 조합으로 재큐잉 여부를 검증한다.

      python test_scan_round204_fixes.py
"""
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


UPQ_SRC = read("static/upqueue.js")
HTML_SRC = read("templates/partner_portal.html")

print("=" * 72)
print("  스캔 204라운드 회귀 — 사진 업로드 안전망 두 구멍(IndexedDB 트랜잭션·재큐잉 조건)")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = UPQ_SRC.index("put: function (caseId, files, caseNo) {")
i1 = UPQ_SRC.index("\n    all: function", i0)
put_body = UPQ_SRC[i0:i1]
chk("req.onerror = function (ev) { ev.preventDefault(); };" in put_body,
    "★★★★ upqueue.js put() 의 add() 요청마다 onerror(preventDefault)가 생겼다")

chk("if(window.UPQ && !failIds.length){" in HTML_SRC,
    "★★★★ partner_portal.html 재큐잉 조건이 !failIds.length 로 바뀌었다"
    "(retryFiles 여부와 무관하게 실패분 큐확보 여부만 본다)")

# ============================================================
print("\n[2] 실행(Node.js) — (a) IndexedDB 트랜잭션: 1건 실패해도 나머지는 커밋된다")
# ------------------------------------------------------------
JS_HARNESS_A = r"""
const vm = require('vm');
const fs = require('fs');

//  최소 가짜 IndexedDB — add() 호출 순서 중 지정된 인덱스만 "실패"시킨다.
//  onerror 가 preventDefault() 를 안 부르면(=구버전 결함) 트랜잭션 전체를
//  abort 시켜 이미 성공한 add() 까지 결과를 비운다.
function makeFakeIndexedDB(failAt) {
  return {
    open: function () {
      var req = { onupgradeneeded: null, onsuccess: null, onerror: null, result: null };
      var callIndex = 0;
      var db = {
        close: function () {},
        transaction: function () {
          var pending = [];
          var aborted = false;
          var tx = { oncomplete: null, onerror: null,
            objectStore: function () {
              return {
                add: function () {
                  var idx = callIndex++;
                  var req2 = { onsuccess: null, onerror: null, result: 1000 + idx };
                  pending.push({ req: req2, idx: idx, fail: failAt.indexOf(idx) !== -1 });
                  return req2;
                },
              };
            },
          };
          queueMicrotask(function () {
            for (var i = 0; i < pending.length; i++) {
              var item = pending[i];
              if (item.fail) {
                var handled = false;
                var ev = { preventDefault: function () { handled = true; } };
                if (item.req.onerror) item.req.onerror(ev);
                if (!handled) { aborted = true; break; }
              } else {
                if (item.req.onsuccess) item.req.onsuccess();
              }
            }
            if (aborted) { if (tx.onerror) tx.onerror(); }
            else { if (tx.oncomplete) tx.oncomplete(); }
          });
          return tx;
        },
      };
      queueMicrotask(function () { req.result = db; if (req.onsuccess) req.onsuccess(); });
      return req;
    },
  };
}

async function run(failAt) {
  var sandbox = { console: console, queueMicrotask: queueMicrotask };
  sandbox.window = sandbox;
  sandbox.indexedDB = makeFakeIndexedDB(failAt);
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), sandbox, { filename: 'upqueue.js' });
  var files = [
    { name: 'a.jpg', size: 100 }, { name: 'b.jpg', size: 100 }, { name: 'c.jpg', size: 100 },
  ];
  var ids = await sandbox.window.UPQ.put(1, files, 'CASE-1');
  return ids;
}

(async function () {
  var noFail = await run([]);
  var oneFail = await run([1]);   // 3장 중 가운데(1번) 만 실패
  console.log(JSON.stringify({ noFail: noFail, oneFail: oneFail }));
})().catch(function (e) { console.error('HARNESS_ERROR: ' + (e && e.stack || e)); process.exit(1); });
"""

_tmpdir = tempfile.mkdtemp(prefix="round204_")
_harness_a = os.path.join(_tmpdir, "harness_a.js")
with io.open(_harness_a, "w", encoding="utf-8") as f:
    f.write(JS_HARNESS_A)
_upq_path = os.path.join(HERE, "static", "upqueue.js")

try:
    result = subprocess.run(["node", _harness_a, _upq_path],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=30)
    chk(result.returncode == 0,
        "★★★ (a) Node 하네스가 예외 없이 끝까지 실행됐다", result.stderr.strip())
    out_a = None
    if result.returncode == 0:
        try:
            out_a = json.loads(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as e:
            chk(False, "★★★ (a) 하네스 출력(JSON) 파싱", f"{e}: {result.stdout!r}")
    if out_a is not None:
        chk(len(out_a["noFail"]) == 3 and all(x is not None for x in out_a["noFail"]),
            "★ (사전조건) 아무도 안 실패하면 3장 모두 id 를 받는다", out_a["noFail"])
        one = out_a["oneFail"]
        chk(len(one) == 3 and one[0] is not None and one[2] is not None,
            "★★★★ 3장 중 1장(가운데)이 실패해도 나머지 2장은 id 를 받는다"
            "(고치기 전엔 트랜잭션 전체 abort 로 3장 다 빈 배열이었다)", one)
        chk(len(one) < 3 or one[1] is None,
            "★★★ 실패한 그 1장 자리는 비어 있다(id 를 지어내지 않는다)", one)
except FileNotFoundError:
    chk(False, "★★★ (a) node 실행파일을 못 찾음", "node --version 확인 필요")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ (a) 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행(Node.js) — (b) 재큐잉 조건: 최초 호출에서 put() 이 실패해도 재큐잉 시도한다")
# ------------------------------------------------------------
b0 = HTML_SRC.index("if(failed.length){")
b1 = HTML_SRC.index("\n  }else{", b0)
FAILED_BLOCK_JS = HTML_SRC[b0:b1] + "\n  }"

JS_HARNESS_B = r"""
const vm = require('vm');
const fs = require('fs');

function scenario(qidsIn, putResultIds) {
  var putCalls = [];
  var sandbox = { console: console };
  sandbox.window = sandbox;
  sandbox.D = { my_cases: [{ id: 1, case_no: 'R204-CASE' }] };
  sandbox.caseId = 1;
  sandbox.done = 1;
  sandbox.errs = [];
  sandbox.UP_RETRY = null;
  sandbox.toast = function () {};
  var fileA = { name: 'a.jpg' }, fileB = { name: 'b.jpg' };
  sandbox.files = [fileA, fileB];
  sandbox.failed = [fileA, fileB];        // 이 시나리오에선 둘 다 전송 실패했다고 가정
  sandbox.qids = qidsIn;                  // put()이 앞서 돌려준 큐 id들(비었을 수도)
  //  uploadPhotos(caseId, input, retryFiles, retryQids) 의 매개변수 — 여기 두
  //  시나리오는 전부 "최초 호출"(재시도 아님)을 재현하므로 undefined 로 둔다.
  //  (구버전 조건 retryFiles && !qids.length 로 되돌렸을 때 ReferenceError 가
  //  아니라 정확히 falsy 로 평가되게 하기 위함 — 라운드204 결함의 핵심이 바로
  //  "최초 호출인데 retryFiles 만 보고 걸러진다"였다)
  sandbox.retryFiles = undefined;
  sandbox.UPQ = {
    put: function (cid, files) {
      putCalls.push({ cid: cid, n: files.length });
      return Promise.resolve(putResultIds);
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), sandbox, { filename: 'block.js' });
  return { putCalls: putCalls, sandboxRef: sandbox };
}

(async function () {
  // 시나리오1: 최초 호출에서 UPQ.put() 자체가 실패해 qids=[] — 재큐잉을 시도해야 한다(라운드204 핵심)
  var s1 = scenario([], [501, 502]);
  await new Promise(function (r) { setTimeout(r, 20); });   // put().then() 이 돌 시간을 준다

  // 시나리오2: 정상 — put() 이 이미 성공해 qids 가 채워져 있다 — 재큐잉하면 안 된다(중복)
  var s2 = scenario([501, 502], [999, 999]);
  await new Promise(function (r) { setTimeout(r, 20); });

  console.log(JSON.stringify({
    s1_putCalls: s1.putCalls.length,
    s1_upRetryQids: s1.sandboxRef.UP_RETRY && s1.sandboxRef.UP_RETRY.qids,
    s2_putCalls: s2.putCalls.length,
    s2_upRetryQids: s2.sandboxRef.UP_RETRY && s2.sandboxRef.UP_RETRY.qids,
  }));
})().catch(function (e) { console.error('HARNESS_ERROR: ' + (e && e.stack || e)); process.exit(1); });
"""

_harness_b = os.path.join(_tmpdir, "harness_b.js")
_block_path = os.path.join(_tmpdir, "failed_block.js")
with io.open(_harness_b, "w", encoding="utf-8") as f:
    f.write(JS_HARNESS_B)
with io.open(_block_path, "w", encoding="utf-8") as f:
    f.write(FAILED_BLOCK_JS)

try:
    result = subprocess.run(["node", _harness_b, _block_path],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=30)
    chk(result.returncode == 0,
        "★★★ (b) Node 하네스가 예외 없이 끝까지 실행됐다", result.stderr.strip())
    out_b = None
    if result.returncode == 0:
        try:
            out_b = json.loads(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as e:
            chk(False, "★★★ (b) 하네스 출력(JSON) 파싱", f"{e}: {result.stdout!r}")
    if out_b is not None:
        chk(out_b["s1_putCalls"] == 1,
            "★★★★ 최초 호출에서 put() 이 실패해(qids=[]) 재큐잉을 안 했던 결함 — "
            "이젠 실패분을 다시 UPQ.put() 으로 채워 넣으려 시도한다"
            "(고치기 전엔 retryFiles 가 아니라서 시도 자체를 안 했다)", out_b)
        chk(out_b["s1_upRetryQids"] == [501, 502],
            "★★★ 그 재시도 put() 의 결과 id 로 UP_RETRY.qids 가 채워진다"
            "(다음 재시도 버튼에서 이 사진을 찾을 수 있다)", out_b["s1_upRetryQids"])
        chk(out_b["s2_putCalls"] == 0,
            "★★★ 반대로 실패분이 이미 큐 id 를 확보하고 있으면(failIds 있음) "
            "재큐잉을 또 시도하지 않는다(중복 큐잉 방지)", out_b)
except FileNotFoundError:
    chk(False, "★★★ (b) node 실행파일을 못 찾음", "node --version 확인 필요")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ (b) 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
