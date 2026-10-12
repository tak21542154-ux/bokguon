# -*- coding: utf-8 -*-
"""스캔 129라운드 회귀 — partner_portal.html 의 서비스워커 대시보드 캐시가
   계정 구분 없이(URL만 열쇠) 이전 협력사 사본을 새 계정 화면에 보여줄 수
   있었다(sw.js: /api/partner/dashboard·/api/partner/dispatches 만 네트워크
   우선+마지막사본 전략, 캐시 키에 계정 구분 없음 — 파일 자신의 주석 "철칙4"가
   이미 이 위험을 명시하고 logout()에만 clearAppCaches()를 걸어 뒀었다).

  로그아웃 버튼을 거치지 않고 세션이 끝나는 경로(탭만 닫기, 401 강제이동,
  관리자 정지)는 이 방어가 전혀 없었다 — 그 상태에서 다른 협력사가 같은
  기기로 로그인해 대시보드 첫 로드가 하필 오프라인/네트워크 실패로 걸리면
  이전 업체의 사건 주소·계약금액이 새 계정 화면에 그대로 뜬다.

  수정: boot() 가 이 기기에서 마지막으로 쓰던 계정 id(localStorage)를 지금
  로그인한 계정 id와 대조해, 다르면 reload() 전에 캐시를 먼저 지운다 —
  로그아웃을 거쳤는지와 무관하게 "새 로그인" 이라는 하나의 관문에서 막는다.

      python test_scan_round129_fixes.py
"""
import io
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


PP = read("templates/partner_portal.html")
SW = read("static/sw.js")

print("=" * 72)
print("  스캔 129라운드 회귀 — partner_portal.html sw캐시 계정간 유출(로그아웃 안 거친 계정전환)")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
MARK_START = "//  ⚠ 로그아웃 없이 계정이 바뀌었다면"
i0 = PP.index(MARK_START)
i1 = PP.index("}catch(e){}", i0) + len("}catch(e){}")
BLOCK = PP[i0:i1]

chk("localStorage.getItem('bokguon_partner_last_id')" in BLOCK,
    "★★★ boot() 가 이 기기의 마지막 계정id를 localStorage에서 읽는다")
chk("lastId !== String(me.id)" in BLOCK and "await clearAppCaches()" in BLOCK,
    "★★★ 마지막 계정과 다르면 clearAppCaches()를 부른다")
chk("localStorage.setItem('bokguon_partner_last_id', String(me.id))" in BLOCK,
    "★★ 매번 지금 계정id로 갱신한다(다음 boot()의 대조 기준)")

# 배치 위치 확인: reload() 호출(캐시된 대시보드를 물어오는 지점)보다 먼저 실행돼야 한다
boot_i = PP.index("async function boot(){")
reload_call_i = PP.index("await reload();", boot_i)
chk(boot_i < i0 < reload_call_i,
    "★★★ 신원 대조가 boot() 안에서 reload()(대시보드 fetch) 보다 먼저 실행되는 위치다")

chk("/api/partner/dashboard" in SW and "/api/partner/dispatches" in SW,
    "★ sw.js가 캐시하는 대상이 여전히 이 두 경로뿐임을 확인(범위 재확인)")

# ============================================================
print("\n[2] 실행 — node 로 실제 신원대조 블록을 실행")
# ------------------------------------------------------------
NODE = shutil.which("node")
if not NODE:
    chk(False, "★★★ node 실행 파일을 찾을 수 없다", "실제 실행 검증을 건너뛸 수 없음")
else:
    _js = f"""
    async function checkIdentity(me, store, clearedLog) {{
      var localStorage = {{
        getItem: function(k) {{ return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; }},
        setItem: function(k, v) {{ store[k] = v; }}
      }};
      async function clearAppCaches() {{ clearedLog.push(true); }}
{BLOCK}
    }}

    async function run() {{
      // ── case 1: 이 기기 첫 로그인(저장값 없음) — 지우면 안 된다 ──
      var store1 = {{}};
      var cleared1 = [];
      await checkIdentity({{id: 7}}, store1, cleared1);
      console.log(JSON.stringify({{case:'first_login', cleared: cleared1.length, stored: store1['bokguon_partner_last_id']}}));

      // ── case 2: 같은 계정 재방문 — 지우면 안 된다(오프라인 내성 유지) ──
      var store2 = {{ bokguon_partner_last_id: '7' }};
      var cleared2 = [];
      await checkIdentity({{id: 7}}, store2, cleared2);
      console.log(JSON.stringify({{case:'same_account', cleared: cleared2.length, stored: store2['bokguon_partner_last_id']}}));

      // ── case 3: 로그아웃 없이 다른 계정으로 전환 — 반드시 지워야 한다 ──
      var store3 = {{ bokguon_partner_last_id: '7' }};
      var cleared3 = [];
      await checkIdentity({{id: 9}}, store3, cleared3);
      console.log(JSON.stringify({{case:'switched_account', cleared: cleared3.length, stored: store3['bokguon_partner_last_id']}}));
    }}
    run();
    """
    _r = subprocess.run(["node", "-e", _js], capture_output=True)
    _out = (_r.stdout or b"").decode("utf-8", "replace")
    _err = (_r.stderr or b"").decode("utf-8", "replace")
    lines = [ln for ln in _out.splitlines() if ln.strip().startswith("{")]
    chk(len(lines) == 3, "STEP node 실행이 세 케이스 결과를 모두 냈다", f"out={_out!r} err={_err[:400]!r}")
    if len(lines) == 3:
        import json as _json
        r1, r2, r3 = (_json.loads(ln) for ln in lines)
        chk(r1.get("cleared") == 0 and r1.get("stored") == "7",
            "★★★ 첫 로그인(기록 없음)은 캐시를 안 지우고, 계정id를 새로 기록한다", r1)
        chk(r2.get("cleared") == 0 and r2.get("stored") == "7",
            "★★★ 같은 계정 재방문은 캐시를 안 지운다(오프라인 내성 회귀 없음)", r2)
        chk(r3.get("cleared") == 1 and r3.get("stored") == "9",
            "★★★ 로그아웃 없이 다른 계정(7→9)으로 바뀌면 캐시를 지우고 새 id를 기록한다"
            "(고치기 전엔 이 대조 자체가 없어 이전 업체 사본이 그대로 남았다)", r3)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
