# -*- coding: utf-8 -*-
"""스캔 77라운드 회귀 — admin.js 의 api() 가 partner_portal.html·insurer_portal.html
   (76라운드)에 이미 있던 업로드-중-강제이동 유예(UP_BUSY) 를 못 받고 있었다.

  관리자가 전화·팩스 접수 현장사진·하자사진을 올리는 도중 세션이 만료되면
  (유휴 타임아웃·비밀번호 변경·계정 강등), 30초 알림 폴링(pollNotifications)이
  api() 를 거치다 401 을 만나 곧바로 로그인 화면으로 튕겼다 — 그 강제 이동이
  진행 중이던 FormData 업로드를 그대로 끊어 사진이 서버에 닿지 못한 채
  증발했다(관리자 업로드 경로는 협력사처럼 기기 큐 백업도 없다).

      python test_scan_round77_fixes.py
"""
import io
import json
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


JS = read("static/admin.js")

print("═" * 72)
print("  스캔 77라운드 회귀 — admin.js 업로드중 강제이동 유예(UP_BUSY) 누락")
print("═" * 72)


def _js_fn_body(src, header):
    i = src.find(header)
    if i < 0:
        return ""
    depth = 0
    started = False
    for k in range(i, len(src)):
        if src[k] == "{":
            depth += 1
            started = True
        elif src[k] == "}":
            depth -= 1
            if started and depth == 0:
                return src[i:k + 1]
    return ""


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
api_body = _js_fn_body(JS, "async function api(method, url, body){")
chk(api_body.count("if(UP_BUSY){ throw new Error('auth-deferred'); }") >= 1,
    "★★★ api() 가 401 응답 시 UP_BUSY 를 확인한다")

chk("let UP_BUSY = false;" in JS, "★ UP_BUSY 전역 플래그가 선언됐다")
chk("beforeunload" in JS, "★ 업로드 중 페이지 이탈 경고(beforeunload)가 추가됐다")

cc_body = _js_fn_body(JS, "async function createCase(){")
chk(cc_body.count("UP_BUSY = true") >= 1 and cc_body.count("UP_BUSY = false") >= 1,
    "★★ createCase() 의 피해사진 업로드 구간이 UP_BUSY 로 감싸져 있다")

udp_body = _js_fn_body(JS, "async function uploadDamagePhotos(cid, input){")
chk(udp_body.count("UP_BUSY = true") >= 1 and udp_body.count("UP_BUSY = false") >= 1,
    "★★ uploadDamagePhotos() 가 UP_BUSY 로 감싸져 있다")

udef_body = _js_fn_body(JS, "async function uploadDefectPhotos(did, input){")
chk(udef_body.count("UP_BUSY = true") >= 1 and udef_body.count("UP_BUSY = false") >= 1,
    "★★ uploadDefectPhotos() 가 UP_BUSY 로 감싸져 있다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 브라우저 전역(fetch·location)을 흉내내 node 로 실제 실행")
# ──────────────────────────────────────────────────────────────
NODE = shutil.which("node")
if not NODE:
    chk(False, "★★★ node 실행 파일을 찾을 수 없다", "node --check 로 파싱하는 검사라 건너뛸 수 없음")
else:
    _js = api_body + "\n" + """
    var CSRF = 'tok';
    var _navigated = false;
    var location = { set href(v) { _navigated = true; }, get href(){ return ''; } };
    function fakeFetch(status){
      return async function(){
        return { status: status, headers: null, json: async () => ({}) };
      };
    }
    async function run(){
      // ── 업로드 중(UP_BUSY=true) — 401 을 맞아도 강제이동하지 않고 미뤄야 한다 ──
      global.UP_BUSY = true; global.fetch = fakeFetch(401);
      let deferred = false, navigated1 = false;
      try{ await api('GET','/x'); }
      catch(e){ deferred = (e.message === 'auth-deferred'); navigated1 = _navigated; }
      console.log(JSON.stringify({case:'busy_401', deferred, navigated: navigated1}));

      // ── 평상시(UP_BUSY=false) — 401 이면 그대로 로그인으로 이동해야 한다(회귀 없음) ──
      _navigated = false;
      global.UP_BUSY = false; global.fetch = fakeFetch(401);
      let navigated2 = false, threw_auth = false;
      try{ await api('GET','/x'); }
      catch(e){ threw_auth = (e.message === 'auth'); navigated2 = _navigated; }
      console.log(JSON.stringify({case:'idle_401', navigated: navigated2, threw_auth}));
    }
    run();
    """
    _r = subprocess.run(["node", "-e", _js], capture_output=True)
    _out = (_r.stdout or b"").decode("utf-8", "replace")
    _err = (_r.stderr or b"").decode("utf-8", "replace")
    lines = [ln for ln in _out.splitlines() if ln.strip().startswith("{")]
    chk(len(lines) == 2, "STEP node 실행이 두 케이스 결과를 모두 냈다", f"out={_out!r} err={_err[:300]!r}")
    if len(lines) == 2:
        r1 = json.loads(lines[0])
        r2 = json.loads(lines[1])
        chk(r1.get("deferred") is True and r1.get("navigated") is False,
            "★★★ 업로드 중(UP_BUSY=true) 401 은 강제이동 없이 'auth-deferred' 로 미뤄진다"
            "(고치기 전엔 UP_BUSY 자체가 없어 무조건 location.href 로 이동했다)", r1)
        chk(r2.get("threw_auth") is True and r2.get("navigated") is True,
            "★ 평상시(UP_BUSY=false) 401 은 여전히 정상적으로 로그인 화면으로 이동한다"
            "(과잉차단 아님 — 회귀 없음)", r2)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
