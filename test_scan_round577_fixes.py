# -*- coding: utf-8 -*-
"""스캔 577라운드 회귀 — static/sw.js 의 PRECACHE 배열이 style.css·fonts.css·
   actions.js·form.js 를 물음표 없는 맨 경로로 넣어 두던 결함(직접조사, 하위위임 없음).

   조사 각도 — round572("서버가 낡았다" 자기점검이 실제로는 스스로 말하는 범위보다
   좁았다)와 round239(이 파일 자신의 캐시쓰기가 waitUntil 로 안 묶여 있었다)가 이미
   다룬 바로 그 static/sw.js 를, "이 파일이 스스로 하는 약속을 실제 코드가 지키는가"
   라는 세 번째 각도로 다시 훑었다. 파일 상단 주석 5행이 이미 "/static/*(버전 쿼리
   ?v= 로 캐시버스팅되는 자산)만 캐시 우선으로 빠르게 연다"고 스스로 말하는데,
   PRECACHE 배열(설치 단계에서 미리 캐시를 데워 두는 목록)에는 물음표 없는 맨 경로
   ('/static/style.css' 등)가 그대로 박혀 있었다. app.py:asset()(312행, 모든 템플릿이
   CSS/JS 를 링크할 때 쓰는 유일한 헬퍼)는 배포 후 캐시를 계속 못 쓰게 하려고 이 4개
   파일을 전부 "/static/파일명?v=<파일내용 sha256 앞10자리>" 형태로만 내보낸다.

   실제 영향 — Cache API 의 match/addAll 은 기본적으로(ignoreSearch 옵션을 안 쓰면,
   이 저장소 전체 grep 결과 사용처 0건) 요청 URL을 물음표 뒤 쿼리스트링까지 정확히
   같아야 같은 캐시 키로 본다. install 이 캐시에 넣는 키(물음표 없음)와 실제 페이지가
   요청하는 키(asset() 이 만든, 물음표+해시)가 영영 어긋나므로, install 이 미리
   데워 둔 이 4개 항목은 실제 요청과 단 한 번도 맞아떨어질 수 없었다 — precache 가
   스스로 밝힌 존재 이유(설치 직후부터 앱 셸을 캐시로 빠르게 연다)를 못 한다.
   icon-192.png(manifest.webmanifest 가 물음표 없이 그대로 참조, 확인함)와 /offline
   (내비게이션 요청도 물음표가 안 붙음)은 원래도 문제 없었다.

   고침 — static/sw.js 의 PRECACHE 4개 항목을 자리표시자로 바꾸고, app.py:
   service_worker()(이 파일을 내려보내는 유일한 라우트, __APP_VERSION__·__BUILD__ 를
   이미 같은 방식으로 채워 주던 바로 그 자리) 한 곳에서 asset() 실제 값으로 채운다 —
   페이지가 <link>/<script> 를 만들 때 쓰는 것과 정확히 같은 함수라 항상 같은 키가
   된다(새 헬퍼·새 상수 없음, 이미 있던 단일 소스를 그대로 재사용).

   이 회귀테스트는 [1] 소스 확인, [2] 스크래치 DB로 실제 app.py 를 안전하게 띄워
   test_client 로 진짜 /sw.js 를 받아 자리표시자가 실제 asset() 값(그 값이 파일 내용
   sha256 앞10자리와도 일치함을 독립 재계산)으로 정확히 채워졌는지 실측, [3] 되돌리기
   — 같은 fetch 핸들러 로직(파일에서 그대로 가져온, 손대지 않은 나머지 전부)에
   PRECACHE 배열만 옛(맨 경로) 버전으로 바꿔치기한 것과 지금 버전을, Node 의 실제
   Cache API 의미론(쿼리스트링까지 정확히 같아야 히트, 상대경로는 워커 origin 기준
   절대경로로 정규화됨)을 그대로 구현한 하네스에 나란히 태워 대조한다 — 옛 버전은
   install 후에도 실제 페이지 요청(물음표+해시 URL)에서 라이브 fetch 가 다시 발생함
   (캐시미스)을, 지금 버전은 발생하지 않음(캐시히트)을 실측하고, 물음표 없는
   icon-192.png 는 옛/새 버전 둘 다 정상 히트함(회귀 없음)도 함께 확인한다.

      python test_scan_round577_fixes.py
"""
import hashlib
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


print("=" * 72)
print("  스캔 577라운드 회귀 — sw.js PRECACHE 가 asset() 의 ?v= 버전쿼리를 놓치던 결함")
print("=" * 72)

SW_SRC = read("static/sw.js")
APP_SRC = read("app.py")

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
for ph in ("__ASSET_STYLE_CSS__", "__ASSET_FONTS_CSS__", "__ASSET_ACTIONS_JS__", "__ASSET_FORM_JS__"):
    chk(SW_SRC.count(ph) == 1, f"★★★ static/sw.js PRECACHE 에 {ph} 자리표시자가 정확히 1번",
        SW_SRC.count(ph))

chk(not any(lit in SW_SRC for lit in
            ("'/static/style.css',", "'/static/fonts.css',",
             "'/static/actions.js',", "'/static/form.js',")),
    "★★★★★ PRECACHE 배열에 물음표 없는 옛 경로 리터럴이 더는 없다")
chk("'/static/icons/icon-192.png'," in SW_SRC and "'/offline'," in SW_SRC,
    "회귀 없음 — 원래도 문제 없던 두 항목(icon-192·offline)은 그대로 맨 경로")
chk(SW_SRC.count("e.waitUntil(caches.open(CACHE).then((c) => c.put(req, copy)));") == 2,
    "회귀 없음 — round239 가 고친 waitUntil() 캐시쓰기 두 곳 모두 그대로 남아있다")

_sw_start = APP_SRC.index("def service_worker():")
_sw_end = APP_SRC.index('@app.get("/offline")')
SW_ROUTE_SRC = APP_SRC[_sw_start:_sw_end]
for name, ph in (("style.css", "__ASSET_STYLE_CSS__"), ("fonts.css", "__ASSET_FONTS_CSS__"),
                  ("actions.js", "__ASSET_ACTIONS_JS__"), ("form.js", "__ASSET_FORM_JS__")):
    chk(f'"{ph}", asset("{name}")' in SW_ROUTE_SRC,
        f"★★★★★ service_worker() 가 {ph} 를 실제 asset('{name}') 값으로 채운다")
chk('src.replace("__APP_VERSION__", APP_VERSION).replace("__BUILD__", BUILD_HASH)' in SW_ROUTE_SRC,
    "회귀 없음 — 기존 __APP_VERSION__/__BUILD__ 치환 줄도 그대로 있다")

# ============================================================
print("\n[2] 실제 실행 — 스크래치 DB로 안전하게 app.py 를 띄워 진짜 /sw.js 를 받는다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round577_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB
DB.init_db()
import app as A

client = A.app.test_client()
resp = client.get("/sw.js")
body = resp.get_data(as_text=True)

chk(resp.status_code == 200, "실제 /sw.js 응답 200", resp.status_code)
chk("__ASSET_" not in body, "★★★★★ 실제 응답에 미치환 __ASSET_ 자리표시자가 하나도 안 남았다")
chk("__APP_VERSION__" not in body and "__BUILD__" not in body,
    "회귀 없음 — 기존 __APP_VERSION__/__BUILD__ 치환도 여전히 정상")

EXPECT = {}
for name in ("style.css", "fonts.css", "actions.js", "form.js"):
    url = A.asset(name)
    EXPECT[name] = url
    chk(f"'{url}'," in body,
        f"★★★★★ 실제 응답 PRECACHE 안에 {name} 이 실제 asset() 값 그대로 들어있다", url)
    #  독립검증 — asset() 을 신뢰만 하지 않고 파일 바이트로 직접 재계산해 대조
    real_hash = hashlib.sha256(open(os.path.join(HERE, "static", name), "rb").read()).hexdigest()[:10]
    chk(url == f"/static/{name}?v={real_hash}",
        f"  {name} 의 버전 해시가 실제 파일 바이트 sha256 앞10자리와 일치(asset() 자체도 정상)",
        (url, real_hash))

# ============================================================
print("\n[3] 되돌리기 — Node 의 실제 Cache API 의미론(쿼리스트링 정확매치)으로 옛/새 대조")
# ------------------------------------------------------------
_blk_start = SW_SRC.index("const PRECACHE = [")
_blk_end = SW_SRC.index("];", _blk_start) + 2
NEW_PRECACHE_BLOCK = SW_SRC[_blk_start:_blk_end]
OLD_PRECACHE_BLOCK = (
    "const PRECACHE = [\n"
    "  '/static/style.css',\n"
    "  '/static/fonts.css',\n"
    "  '/static/actions.js',\n"
    "  '/static/form.js',\n"
    "  '/static/icons/icon-192.png',\n"
    "  '/offline',\n"
    "];"
)
OLD_SW_SRC = SW_SRC.replace(NEW_PRECACHE_BLOCK, OLD_PRECACHE_BLOCK)
chk(OLD_SW_SRC != SW_SRC and "__ASSET_STYLE_CSS__" not in OLD_SW_SRC,
    "  준비 확인 — 옛 버전 재구성이 실제로 PRECACHE 블록만 바꿔치기했다")


def _fill(src):
    return (src.replace("__APP_VERSION__", "testver")
               .replace("__BUILD__", "testbuild")
               .replace("__ASSET_STYLE_CSS__", EXPECT["style.css"])
               .replace("__ASSET_FONTS_CSS__", EXPECT["fonts.css"])
               .replace("__ASSET_ACTIONS_JS__", EXPECT["actions.js"])
               .replace("__ASSET_FORM_JS__", EXPECT["form.js"]))


OLD_FILLED = _fill(OLD_SW_SRC)          # 자리표시자가 이미 없으므로 뒤 4개 replace 는 no-op
NEW_FILLED = _fill(SW_SRC)              # 실제 on-disk 파일 그대로 + 실제 asset() 값

_old_path = os.path.join(_tmpdir, "sw_old.js")
_new_path = os.path.join(_tmpdir, "sw_new.js")
io.open(_old_path, "w", encoding="utf-8").write(OLD_FILLED)
io.open(_new_path, "w", encoding="utf-8").write(NEW_FILLED)

HARNESS = r'''
const fs = require('fs');
const vm = require('vm');

function loadSW(path) {
  const src = fs.readFileSync(path, 'utf8');
  const fetchLog = [];
  const cacheStore = {};
  const fakeCache = {
    put: (req, res) => {
      cacheStore[typeof req === 'string' ? req : req.url] = res;
      return Promise.resolve();
    },
    match: (req) => Promise.resolve(cacheStore[typeof req === 'string' ? req : req.url]),
    //  ⚠ 실제 Cache.addAll 은 상대경로를 워커의 origin 기준 절대경로로 정규화해
    //    저장한다 — 이 정규화를 빼면 옛/새 버전 둘 다 항상 미스로만 보여 대조가
    //    무의미해진다(테스트 자신의 버그가 된다).
    addAll: (urls) => Promise.all(urls.map((u) => {
      const abs = new URL(u, 'https://example.com').href;
      fetchLog.push(abs);
      return Promise.resolve({ ok: true, url: abs }).then((res) => { cacheStore[abs] = res; });
    })),
  };
  const handlers = {};
  const sandbox = {
    self: {
      addEventListener: (name, fn) => { handlers[name] = fn; },
      skipWaiting: () => {},
      clients: { claim: () => {} },
      location: { origin: 'https://example.com' },
    },
    caches: {
      open: () => Promise.resolve(fakeCache),
      match: (req) => fakeCache.match(req),
      keys: () => Promise.resolve(Object.keys(cacheStore)),
      delete: () => Promise.resolve(true),
    },
    fetch: (req) => {
      const url = typeof req === 'string' ? req : req.url;
      fetchLog.push(url);
      return Promise.resolve({ ok: true, clone: function () { return this; }, url });
    },
    URL, Headers, console,
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  return { handlers, fetchLog };
}

async function fireInstall(handlers) {
  const waits = [];
  handlers.install({ waitUntil: (p) => waits.push(p) });
  await Promise.all(waits);
}

async function fireFetch(handlers, url) {
  const waits = [];
  let respondWithPromise = null;
  handlers.fetch({
    request: { method: 'GET', url },
    respondWith: (p) => { respondWithPromise = p; },
    waitUntil: (p) => waits.push(p),
  });
  if (respondWithPromise) await respondWithPromise;
  await Promise.all(waits);
}

async function scenario(path, versionedStyleUrl, iconUrl) {
  const { handlers, fetchLog } = loadSW(path);
  await fireInstall(handlers);
  const afterInstall = fetchLog.length;
  await fireFetch(handlers, versionedStyleUrl);
  const afterStyle = fetchLog.length;
  await fireFetch(handlers, iconUrl);
  const afterIcon = fetchLog.length;
  return {
    installFetchCount: afterInstall,
    styleWasLiveFetched: afterStyle > afterInstall,
    iconWasLiveFetched: afterIcon > afterStyle,
  };
}

async function main() {
  const [, , oldPath, newPath, versionedStyleUrl] = process.argv;
  const iconUrl = 'https://example.com/static/icons/icon-192.png';
  const out = {
    old: await scenario(oldPath, versionedStyleUrl, iconUrl),
    new: await scenario(newPath, versionedStyleUrl, iconUrl),
  };
  console.log(JSON.stringify(out));
}
main().catch((e) => { console.log(JSON.stringify({ error: String((e && e.stack) || e) })); process.exit(1); });
'''

_harness_path = os.path.join(_tmpdir, "harness.js")
io.open(_harness_path, "w", encoding="utf-8").write(HARNESS)

try:
    _versioned_style_url = "https://example.com" + EXPECT["style.css"]
    r = subprocess.run(
        ["node", _harness_path, _old_path, _new_path, _versioned_style_url],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    out = json.loads((r.stdout or "").strip().splitlines()[-1]) if r.stdout.strip() else {}
    chk("error" not in out, "Node 하네스가 예외 없이 끝까지 실행된다", (out, r.stderr[-300:]))
    old, new = out.get("old", {}), out.get("new", {})
    chk(old.get("installFetchCount") == 6 and new.get("installFetchCount") == 6,
        "  준비 확인 — install 이 두 버전 다 PRECACHE 6개 항목을 그대로 미리 받아온다",
        (old, new))
    chk(old.get("styleWasLiveFetched") is True,
        "★★★★★★ (핵심증거) 옛 PRECACHE(물음표 없음)는 install 후에도 실제 페이지 요청에서 "
        "라이브 fetch 가 다시 발생한다 — 캐시미스, precache 가 무효했다", old)
    chk(new.get("styleWasLiveFetched") is False,
        "★★★★★★ (핵심증거) 지금 PRECACHE(asset() 값)는 같은 요청에서 라이브 fetch 가 "
        "없다 — 캐시히트, precache 가 실제로 먹힌다", new)
    chk(old.get("iconWasLiveFetched") is False and new.get("iconWasLiveFetched") is False,
        "  회귀 없음 — 물음표 없는 icon-192.png 는 옛/새 버전 둘 다 정상 캐시히트", (old, new))
except FileNotFoundError:
    chk(False, "STEP node 실행파일을 찾을 수 없음(PATH 확인 필요)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드577 [3] Node 하네스 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
