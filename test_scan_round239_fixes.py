# -*- coding: utf-8 -*-
"""스캔 239라운드 회귀 — static/sw.js(서비스워커)의 캐시쓰기가 waitUntil() 로
   묶여 있지 않던 결함.

  respondWith() 의 생명연장은 그 프라미스가 res 를 내놓는 순간까지만이다.
  fetch(req).then(res => { ...; caches.open(CACHE).then(c=>c.put(req,copy));
  return res; }) 처럼 캐시쓰기를 반환값과 묶지 않고 따로 띄워 두면(fire-and-
  forget), 응답이 화면에 전달된 직후 브라우저가(특히 신호 나쁜 현장에서
  배터리 절약을 위해 유휴 서비스워커를 적극적으로 종료하는 모바일 환경)
  이 워커를 바로 죽여 아직 안 끝난 캐시쓰기가 통째로 사라질 수 있다.

  이 파일의 캐시블록 두 곳(협력사 대시보드/출동목록의 '마지막 사본', 정적
  자산의 '캐시 우선')이 정확히 이 패턴이었다 — 그것도 이 코드베이스가 반복해서
  강조하는 바로 그 시나리오("지하주차장·산간에서 신호 끊김")를 위해 만든
  코드인데, 정작 그 시나리오(워커가 강제 종료되는 환경)에서 가장 먼저 깨지는
  구조였다. e.waitUntil() 로 캐시쓰기 프라미스를 명시적으로 붙잡아 해결한다.

      python test_scan_round239_fixes.py
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


SW_SRC = read("static/sw.js")

print("=" * 72)
print("  스캔 239라운드 회귀 — sw.js 캐시쓰기가 워커 종료에 취약하던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
FIXED_LINE = "e.waitUntil(caches.open(CACHE).then((c) => c.put(req, copy)));"
chk(SW_SRC.count(FIXED_LINE) == 2,
    "★★★★ 두 캐시블록(대시보드 사본·정적자산) 모두 캐시쓰기를 waitUntil() 로 묶는다",
    f"발견 횟수: {SW_SRC.count(FIXED_LINE)}")
BROKEN_LINE = "caches.open(CACHE).then((c) => c.put(req, copy));"
#  ⚠ FIXED_LINE 자체도 이 부분문자열을 포함하므로(뒤에 waitUntil( 이 더 있을 뿐),
#    "고친 줄 두 개를 뺀 나머지"에 옛 패턴이 남아있는지만 따로 센다.
_stripped = SW_SRC.replace(FIXED_LINE, "")
chk(BROKEN_LINE not in _stripped,
    "★★★ waitUntil() 없이 캐시쓰기만 남아있는(fire-and-forget) 자리가 더는 없다")

# ============================================================
print("\n[2] 실행 — Node 로 fetch 핸들러를 직접 돌려 waitUntil 호출을 확인")
# ------------------------------------------------------------
HARNESS = r'''
const fs = require('fs');
const vm = require('vm');
const SW_SRC = fs.readFileSync(process.argv[2], 'utf8');

function makeSandbox() {
  const handlers = {};
  const cacheStore = {};
  const fakeCache = {
    put: (req, res) => { cacheStore[req.url] = res; return Promise.resolve(); },
    match: (req) => Promise.resolve(cacheStore[req.url]),
    addAll: () => Promise.resolve(),
  };
  const sandbox = {
    self: {
      addEventListener: (name, fn) => { handlers[name] = fn; },
      skipWaiting: () => {}, clients: { claim: () => {} },
      location: { origin: 'https://example.com' },
    },
    caches: {
      open: () => Promise.resolve(fakeCache),
      match: (req) => fakeCache.match(req),
      keys: () => Promise.resolve([]), delete: () => Promise.resolve(true),
    },
    fetch: (req) => Promise.resolve({ ok: true, clone: function () { return this; }, url: req.url }),
    URL, Headers, console,
  };
  vm.createContext(sandbox);
  vm.runInContext(SW_SRC, sandbox);
  return handlers;
}

function fireFetch(handlers, url) {
  const waitUntilPromises = [];
  let respondWithPromise = null;
  handlers.fetch({
    request: { method: 'GET', url },
    respondWith: (p) => { respondWithPromise = p; },
    waitUntil: (p) => { waitUntilPromises.push(p); },
  });
  return { respondWithPromise, waitUntilPromises };
}

async function main() {
  const out = {};
  {
    const { respondWithPromise, waitUntilPromises } =
      fireFetch(makeSandbox(), 'https://example.com/api/partner/dashboard');
    await respondWithPromise;
    await Promise.all(waitUntilPromises);
    out.dashboard_waitUntilCount = waitUntilPromises.length;
  }
  {
    const { respondWithPromise, waitUntilPromises } =
      fireFetch(makeSandbox(), 'https://example.com/static/style.css');
    await respondWithPromise;
    await Promise.all(waitUntilPromises);
    out.static_waitUntilCount = waitUntilPromises.length;
  }
  console.log(JSON.stringify(out));
}
main().catch((e) => { console.log(JSON.stringify({ error: String(e && e.stack || e) })); process.exit(1); });
'''

try:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(HARNESS)
        harness_path = f.name
    try:
        r = subprocess.run(["node", harness_path, os.path.join(HERE, "static", "sw.js")],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=30)
        out = json.loads((r.stdout or "").strip().splitlines()[-1]) if r.stdout.strip() else {}
    finally:
        try:
            os.unlink(harness_path)
        except OSError:
            pass
    chk("error" not in out, "STEP Node 하네스가 예외 없이 끝까지 실행된다", out)
    chk(out.get("dashboard_waitUntilCount", 0) >= 1,
        "★★★★ /api/partner/dashboard 경로 — 캐시쓰기가 실제로 waitUntil() 에 "
        "잡혀 있다(고치기 전엔 0 — respondWith() 가 끝나면 즉시 버려질 수 있었다)",
        out)
    chk(out.get("static_waitUntilCount", 0) >= 1,
        "★★★★ /static/* 경로 — 캐시쓰기가 실제로 waitUntil() 에 잡혀 있다"
        "(고치기 전엔 0)", out)
except FileNotFoundError:
    chk(False, "STEP node 실행 파일을 찾을 수 없음(PATH 확인 필요)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드239 [2] 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
