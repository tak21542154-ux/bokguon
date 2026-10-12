# -*- coding: utf-8 -*-
"""스캔 203라운드 회귀 — partner_portal.html 의 boot() 가 재진입 가드 없이
.tab 클릭 리스너 부착과 30초 알림 폴링(setInterval)을 매번 새로 무장하던 결함.

  boot() 는 최초 페이지 로드(맨 아래 한 줄) 말고도 reestimateGo()(실사 증액
  요청 제출 성공 후, 1569행)·coSend()(변경견적 수락/거절 후, 1610행)가
  "성공했으니 전체를 새로고침" 용도로 세션 중 다시 부른다 — 둘 다 예외적
  상황이 아니라 정상 업무 흐름이다. 그런데 .tab 리스너 부착과 setInterval
  무장에 재진입 가드가 전혀 없어서, boot() 를 부를 때마다 클릭 리스너가 또
  하나씩 늘고(탭 클릭 한 번에 show() 가 여러 번 실행) 30초 알림 폴링도 또
  하나씩 겹쳐 돈다(선착순 출동 콜을 가져오는 loadDispatch 포함) — 세션이
  길수록(현장 기사가 하루 종일 켜 두는 화면) 계속 나빠진다.

  (대조: insurer_portal.html 은 같은 구조의 boot()/setInterval 을 쓰지만
  호출부가 페이지 로드 한 곳뿐이라 이 결함이 없다 — 파트너 포털만의 결함)

  Node.js 로 boot() 를 원본 그대로 뽑아 최소 스텁으로 실행해, 두 번 불러도
  리스너·인터벌이 각각 1개만 무장되는지 실제로 검증한다.

      python test_scan_round203_fixes.py
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


HTML_SRC = read("templates/partner_portal.html")

print("=" * 72)
print("  스캔 203라운드 회귀 — boot() 재진입 시 리스너·폴링 누적")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = HTML_SRC.index("let _bootedOnce = false;")
i1 = HTML_SRC.index("\nasync function reload()", i0)
boot_block = HTML_SRC[i0:i1]
_has_guard = "if(!_bootedOnce){" in boot_block
chk(_has_guard, "★★★★ boot() 에 재진입 가드(_bootedOnce)가 생겼다")
if _has_guard:
    _i_guard = boot_block.index("if(!_bootedOnce){")
    _i_tab = boot_block.index("addEventListener('click',()=>show(t.dataset.v))")
    _i_interval = boot_block.index("setInterval(loadNotifs, 30000)")
    _i_reload = boot_block.index("await reload();")
    chk(_i_guard < _i_tab < _i_interval < _i_reload,
        "★★★ 가드 안에 탭리스너·인터벌 무장이 함께 있고, reload()/show()/"
        "loadNotifs() 는 가드 밖(=매번 실행)에 그대로 남았다"
        "(boot() 재호출의 '새로고침' 의도는 안 건드림)")
else:
    chk(False, "★★★ (건너뜀) 가드가 없어 위치관계를 확인할 수 없음")

boot_src_start = HTML_SRC.index("let _bootedOnce = false;")
boot_src_end = HTML_SRC.index("\nasync function reload()", boot_src_start)
BOOT_JS = HTML_SRC[boot_src_start:boot_src_end]

# ============================================================
print("\n[2] 실행(Node.js 실제 실행) — boot() 를 두 번 불러도 리스너·인터벌은 1개")
# ------------------------------------------------------------
JS_HARNESS = r"""
const vm = require('vm');
const fs = require('fs');

const tabs = [1,2,3].map(function(){
  return { dataset: {v:'home'}, style:{}, classList:{toggle:function(){}}, _listeners: [],
           addEventListener: function(type, fn){ this._listeners.push(fn); } };
});
const idElements = {};
function fakeIdEl(){ return { textContent:'', style:{} }; }
['pname','ptype','tab-accounts'].forEach(function(id){ idElements[id] = fakeIdEl(); });

const intervalCalls = [];
const store = {};

const sandbox = {
  console: console,
  document: {
    getElementById: function(id){ return idElements[id] || null; },
    querySelectorAll: function(sel){ return sel === '.tab' ? tabs : []; },
  },
  localStorage: {
    getItem: function(k){ return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
    setItem: function(k, v){ store[k] = String(v); },
  },
  setInterval: function(fn, ms){ intervalCalls.push(ms); return intervalCalls.length; },
  api: async function(method, url){
    if (url === '/api/partner/me') return { csrf: 'x', name: 'R203업체', partner_type: '시공사', is_owner: false, id: 1 };
    throw new Error('unexpected api call: ' + url);
  },
  bootFail: function(e){ sandbox.__bootFailed = true; },
  clearAppCaches: async function(){},
  reload: async function(){ sandbox.__reloadCount = (sandbox.__reloadCount||0) + 1; },
  show: function(){ sandbox.__showCount = (sandbox.__showCount||0) + 1; },
  loadNotifs: function(){ sandbox.__loadNotifsCount = (sandbox.__loadNotifsCount||0) + 1; },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), sandbox, { filename: 'boot.js' });

(async function(){
  await sandbox.boot();          // 최초 로드
  await sandbox.boot();          // reestimateGo()/coSend() 가 재호출하는 상황 재현
  await sandbox.boot();          // 세션 중 한 번 더(누적 여부 확인)

  console.log(JSON.stringify({
    bootFailed: !!sandbox.__bootFailed,
    listenerCounts: tabs.map(function(t){ return t._listeners.length; }),
    intervalCalls: intervalCalls,
    reloadCount: sandbox.__reloadCount,
    showCount: sandbox.__showCount,
    loadNotifsCount: sandbox.__loadNotifsCount,
  }));
})().catch(function(e){ console.error('HARNESS_ERROR: ' + (e && e.stack || e)); process.exit(1); });
"""

_tmpdir = tempfile.mkdtemp(prefix="round203_")
_harness_path = os.path.join(_tmpdir, "harness.js")
_boot_path = os.path.join(_tmpdir, "boot_extract.js")
with io.open(_harness_path, "w", encoding="utf-8") as f:
    f.write(JS_HARNESS)
with io.open(_boot_path, "w", encoding="utf-8") as f:
    f.write(BOOT_JS)

try:
    result = subprocess.run(["node", _harness_path, _boot_path],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=30)
    chk(result.returncode == 0,
        "★★★ Node 하네스가 예외 없이 끝까지 실행됐다", result.stderr.strip())
    out = None
    if result.returncode == 0:
        try:
            out = json.loads(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as e:
            chk(False, "★★★ 하네스 출력(JSON) 파싱", f"{e}: {result.stdout!r}")

    if out is not None:
        chk(out["bootFailed"] is False, "★ (사전조건) 세 번 다 정상 경로로 끝났다(bootFail 안 탐)")
        chk(out["listenerCounts"] == [1, 1, 1],
            "★★★★ boot() 를 세 번 불러도 각 탭에는 클릭 리스너가 정확히 1개만 "
            "붙는다(고치기 전엔 [1,1,1] → [2,2,2] → [3,3,3] 으로 계속 늘었다)",
            out["listenerCounts"])
        chk(out["intervalCalls"] == [30000],
            "★★★★ setInterval(loadNotifs, 30000) 도 딱 한 번만 무장된다"
            "(고치기 전엔 boot() 호출 횟수만큼 겹쳐 돌았다)", out["intervalCalls"])
        chk(out["reloadCount"] == 3 and out["showCount"] == 3 and out["loadNotifsCount"] == 3,
            "★★★ 반면 reload()/show()/loadNotifs() 는 boot() 를 부를 때마다 "
            "여전히 매번 실행된다(재진입 가드가 '새로고침' 의도까지 막지 않는다)",
            out)
except FileNotFoundError:
    chk(False, "★★★ 라운드203 [2] node 실행파일을 못 찾음", "node --version 확인 필요")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드203 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
