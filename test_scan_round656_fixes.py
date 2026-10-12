# -*- coding: utf-8 -*-
"""스캔 656라운드 회귀 — 협력사 포털 '못 올린 사진' 자동재전송(upqAutoFlush)이
   boot()가 UPQ.setWho() 를 정하기 **전에** 뛸 수 있어, 같은 기기를 쓴
   **다른 업체**의 사진을 이 세션 자격증명으로 업로드 시도하다 영구 삭제하던
   결함(직접조사, 하위위임 없음).

   배경 — round655가 다룬 landing.html '·' 조판 문제와는 별개 라운드656 자체
   조사: static/upqueue.js(UPQ.setWho/who 필터)와 그 유일한 사용처인
   templates/partner_portal.html 을 라운드655 핸드오프 5번("아무도 최근 안 만진
   영역") 취지로 훑다가 발견.

   근거(전부 이 세션이 grep+Read로 직접 확인):
     · UPQ.setWho() 는 reload() 안(587행 부근)에서만 불린다 — boot()가
       /api/partner/me → reload()(자체로 /api/partner/dashboard 등 여러 호출)를
       순차로 기다린 뒤에야 도달하는 지점이라, 페이지를 막 연 뒤 최소 한 번의
       네트워크 왕복만큼(신호가 나쁜 현장에선 수초까지) UPQ.who 는 계속 null 이다.
     · 그런데 upqAutoFlush() 는 파일 하단의 전역 리스너
       window.addEventListener('online', ...) · document.addEventListener(
       'visibilitychange', ...) 로 boot()/reload() 진행과 **완전히 독립적으로**도
       불린다 — 바로 이 기능이 노리는 상황("신호가 돌아오는 순간 조용히 한 번
       시도한다")이 하필 boot() 가 아직 안 끝난 그 순간에 겹칠 수 있다.
     · static/upqueue.js UPQ.all(): `if (!UPQ.who) return rows;` — who 가
       아직 null 이면 소유자 필터를 통째로 건너뛰고 **모든** 큐 항목을 돌려준다
       (다른 업체가 남긴 항목 포함 — 이 필터 자체가 그 시나리오를 막으려고
       reload() 587행 주석이 명시적으로 만든 것인데, upqAutoFlush() 는 그
       필터가 자리잡기 전에도 호출될 수 있어 보호가 새 나갔다).
     · app.py api_partner_upload_photos(12895행): 사건 소유자 확인
       `WHERE id=? AND partner_id=?`(12903행 부근)에 안 걸리면 404
       "내 시공 건이 아닙니다"(12927행)로 정확히 막는다 — 여기까진 정상이다.
     · 그런데 templates/partner_portal.html uploadPhotos() 의
       RETRYABLE = [401, 403, 408, 409, 413, 419, 423, 425, 429] 목록에는
       **404 가 없다** — 401/403/409 등은 "재시도하면 될 수도 있다"고 보존하면서,
       바로 그 옆 사촌인 404("내 사건 아님")만 permanent 로 분류돼
       UPQ.remove() 로 기기에서 **영구 삭제**된다. 이 파일 전체가 반복해서
       "현장 사진은 다시 못 찍는다"며 지키려는 바로 그 불변식이 이 한 경로로
       깨진다 — 사라지는 사진은 지금 로그인된 업체의 것도 아니라서, 화면에
       뜨는 "올릴 수 없어 대기 목록에서 제외했습니다" 토스트조차 원래 주인은
       보지 못한다.

   고침 — 단일 지점: boot() 의 UPQ.setWho() 결정 시점(reload() 587행 부근,
   성공이든 org_id 없음이든 결과와 무관하게)에 새 플래그 `_upqIdentityReady`를
   true 로 세우고, upqAutoFlush() 진입 가드에 `|| !_upqIdentityReady` 한 항을
   추가했다. upqBanner()·upRetry() 는 이 함수를 거쳐야만 도달하므로(다른
   독립 호출 경로 없음 — grep으로 확인) 이 한 곳이 유일한 초크포인트다.
   수동 "지금 올리기" 버튼(upqFlush)은 그 버튼 자체가 reload() 가 그린
   배너 안에만 있어 원래도 안전했다(안 건드림).

      python test_scan_round656_fixes.py
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


print("=" * 72)
print("  스캔 656라운드 회귀 — upqAutoFlush 가 boot() 의 UPQ.setWho() 보다 먼저 뛰는 경합")
print("=" * 72)

HTML_SRC = read("templates/partner_portal.html")
UPQ_SRC = read("static/upqueue.js")
APP_SRC = read("app.py")

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 세 지점(선언·설정·가드)과 근거로 든 인과사슬")
# ──────────────────────────────────────────────────────────────
chk("let _upqIdentityReady = false;" in HTML_SRC,
    "★★★★ 새 플래그 _upqIdentityReady 가 false 로 선언돼 있다")

_reload_i0 = HTML_SRC.index("async function reload(){")
_reload_i1 = HTML_SRC.index("\nasync function ", _reload_i0 + 10)
RELOAD_SRC = HTML_SRC[_reload_i0:_reload_i1]
chk("UPQ.setWho(D.me.org_id);\n  _upqIdentityReady = true;" in RELOAD_SRC,
    "★★★★★ reload() 가 UPQ.setWho() 바로 다음 줄에서 플래그를 true 로 세운다"
    "(성공이든 org_id 없음이든 그 if 문을 지나간 시점 자체가 '결정 끝')")
_uaf_i0 = HTML_SRC.index("let UPQ_AUTO_BUSY = false;")
_uaf_i1 = HTML_SRC.index("\nwindow.addEventListener('online'", _uaf_i0)
UPQ_AUTO_FLUSH_SRC = HTML_SRC[_uaf_i0:_uaf_i1]
chk("async function upqAutoFlush(){" in UPQ_AUTO_FLUSH_SRC,
    "upqAutoFlush() 함수 블록을 정확히 추출했다")
chk("!_upqIdentityReady) return;" in UPQ_AUTO_FLUSH_SRC,
    "★★★★★ upqAutoFlush() 진입 가드가 !_upqIdentityReady 를 포함한다")

# 이 회귀가 실제로 왜 위험한지 근거로 든 인과사슬 — 지금도 사실인지 실측
chk("if (!UPQ.who) return rows;" in UPQ_SRC,
    "★★★ (근거) upqueue.js UPQ.all() 이 who 없으면 필터를 통째로 건너뛴다")
chk('WHERE id=? AND partner_id=? AND COALESCE(is_demo,0)=0' in APP_SRC,
    "★★★ (근거) app.py 가 사건 소유자를 partner_id 로 확인한다")
chk('"내 시공 건이 아닙니다."}), 404' in APP_SRC,
    "★★★ (근거) 소유자가 아니면 404 로 막는다")
chk("RETRYABLE = [401, 403, 408, 409, 413, 419, 423, 425, 429];" in HTML_SRC,
    "★★★★★ (근거) RETRYABLE 목록에 404 가 없다 — 404 는 permanent(영구 거절)로"
    " 분류돼 UPQ.remove() 로 이어진다(아래 [2]에서 이 사슬의 앞부분을 실행 증명)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 Node.js 실행 — 플래그가 false 인 동안은 UPQ.grouped() 자체를 안 부른다")
# ──────────────────────────────────────────────────────────────
JS_HARNESS = r"""
const vm = require('vm');
const fs = require('fs');

function FakeFile(parts, name, opts) { this.parts = parts; this.name = name;
  this.type = (opts && opts.type) || ''; }

function makeSandbox(groupsToReturn) {
  var calls = { grouped: 0, upRetry: 0, upqBanner: 0, remove: [] };
  var sandbox = { console: console, File: FakeFile };
  sandbox.window = sandbox;
  sandbox.UP_BUSY = false;
  sandbox.UP_RETRY = null;
  sandbox.navigator = { onLine: true };
  sandbox._upqIdentityReady = false;     // 시작은 항상 '아직 결정 전'
  sandbox.UPQ = {
    grouped: function () { calls.grouped++; return Promise.resolve(groupsToReturn); },
    remove: function (ids) { calls.remove.push(ids); return Promise.resolve(); },
  };
  sandbox.upRetry = async function () { calls.upRetry++; };
  sandbox.upqBanner = async function () { calls.upqBanner++; };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), sandbox, { filename: 'upqAutoFlush.js' });
  return { sandbox: sandbox, calls: calls };
}

// 다른 업체 사건(caseId:999)의 사진 한 장이 큐에 남아 있다고 가정한다
var FOREIGN_GROUP = [{ caseId: 999, caseNo: 'OTHER-ORG', items: [{ id: 1, blob: {}, name: 'a.jpg' }] }];

(async function () {
  //  시나리오A: 페이지가 막 열려 reload() 가 아직 setWho() 에 못 닿은 상태
  //  (_upqIdentityReady=false)에서 online/visibilitychange 가 upqAutoFlush 를 부른다.
  var A = makeSandbox(FOREIGN_GROUP);
  await A.sandbox.upqAutoFlush();
  await new Promise(function (r) { setTimeout(r, 20); });

  //  시나리오B: reload() 가 setWho() 를 다 정한 뒤(_upqIdentityReady=true)라면
  //  같은 이벤트가 정상적으로 재전송을 시도해야 한다(기능 자체는 살아 있어야 함).
  var B = makeSandbox(FOREIGN_GROUP);
  B.sandbox._upqIdentityReady = true;
  await B.sandbox.upqAutoFlush();
  await new Promise(function (r) { setTimeout(r, 20); });

  console.log(JSON.stringify({
    A_grouped: A.calls.grouped, A_upRetry: A.calls.upRetry,
    B_grouped: B.calls.grouped, B_upRetry: B.calls.upRetry,
  }));
})().catch(function (e) { console.error('HARNESS_ERROR: ' + (e && e.stack || e)); process.exit(1); });
"""

_tmpdir = tempfile.mkdtemp(prefix="round656_")
_harness = os.path.join(_tmpdir, "harness.js")
_snippet = os.path.join(_tmpdir, "upqAutoFlush_new.js")
io.open(_harness, "w", encoding="utf-8").write(JS_HARNESS)
io.open(_snippet, "w", encoding="utf-8").write(UPQ_AUTO_FLUSH_SRC)

try:
    r = subprocess.run(["node", _harness, _snippet], capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=30)
    chk(r.returncode == 0, "★★★ Node 하네스가 예외 없이 끝까지 실행됐다(새 코드)", r.stderr.strip())
    out = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else None
    if out is not None:
        chk(out["A_grouped"] == 0 and out["A_upRetry"] == 0,
            "★★★★★★ (핵심) _upqIdentityReady 가 아직 false 면 UPQ.grouped() 자체를 "
            "안 부른다 — 남의 업체 사진을 건드릴 기회가 원천적으로 없다", out)
        chk(out["B_grouped"] == 1 and out["B_upRetry"] == 1,
            "★★★★★ _upqIdentityReady 가 true(boot 완료 후)면 그대로 정상 동작한다 "
            "— '신호가 돌아오면 조용히 재전송'이라는 기능 자체는 안 죽었다", out)
except FileNotFoundError:
    chk(False, "★★★ node 실행파일을 못 찾음", "node --version 확인 필요")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 준비/실행", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 되돌림-증명 — 가드에서 !_upqIdentityReady 절만 인메모리로 빼면")
print("    시나리오A(플래그 false)에서도 옛 코드처럼 그대로 진행되는가")
# ──────────────────────────────────────────────────────────────
OLD_GUARD = "if(UPQ_AUTO_BUSY || UP_BUSY || !window.UPQ) return;"
NEW_GUARD = "if(UPQ_AUTO_BUSY || UP_BUSY || !window.UPQ || !_upqIdentityReady) return;"
assert NEW_GUARD in UPQ_AUTO_FLUSH_SRC, "가드 문자열을 못 찾아 되돌림-증명을 진행할 수 없다"
REVERTED_SRC = UPQ_AUTO_FLUSH_SRC.replace(NEW_GUARD, OLD_GUARD)
assert REVERTED_SRC != UPQ_AUTO_FLUSH_SRC, "되돌림 치환이 실제로 안 먹었다"
#  ⚠ 바로 위 설명주석(라운드656 참조)엔 여전히 이 이름이 남아 있다 — 주석은
#    실행에 영향이 없으므로 무해하다. 실제로 검증해야 할 것은 **가드 조건**
#    자체가 더는 이 플래그를 안 본다는 것뿐이다.
assert "!_upqIdentityReady) return" not in REVERTED_SRC, \
    "되돌린 가드 조건에 플래그 검사가 여전히 남아 있으면 안 된다"

_snippet_old = os.path.join(_tmpdir, "upqAutoFlush_old.js")
io.open(_snippet_old, "w", encoding="utf-8").write(REVERTED_SRC)

#  하네스 자체(시나리오 구성)는 그대로 재사용한다 — 바뀌는 건 주입되는
#  스니펫 파일(REVERTED_SRC)뿐이다.
_harness_old = os.path.join(_tmpdir, "harness_old.js")
io.open(_harness_old, "w", encoding="utf-8").write(JS_HARNESS)

try:
    r2 = subprocess.run(["node", _harness_old, _snippet_old], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=30)
    chk(r2.returncode == 0, "★★★ Node 하네스가 예외 없이 끝까지 실행됐다(되돌린 옛 코드)",
        r2.stderr.strip())
    out2 = json.loads(r2.stdout.strip().splitlines()[-1]) if r2.returncode == 0 else None
    if out2 is not None:
        #  되돌린 소스엔 _upqIdentityReady 참조가 아예 없으므로 A/B 결과가 같아야
        #  정상 — "플래그를 봐서 막았다"가 아니라 "애초에 안 본다"는 뜻이다.
        chk(out2["A_grouped"] == 1 and out2["A_upRetry"] == 1,
            "★★★★★★ (핵심 증거) 가드에서 그 한 절만 빼면, boot() 가 아직 안 끝났어도"
            "(옛 코드는 이 사실 자체를 모른다) UPQ.grouped() 가 즉시 불려 남의 사진을"
            " 건드릴 기회가 그대로 열린다 — 이 테스트가 진짜 결함을 잡아낼 능력이"
            " 있음을 증명", out2)
        chk(out2["A_grouped"] == out2["B_grouped"] == 1,
            "  되돌린 코드는 A/B(boot 전·후)를 구분하지 못한다(원래 결함의 본질)", out2)
except FileNotFoundError:
    chk(False, "★★★ node 실행파일을 못 찾음", "node --version 확인 필요")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 준비/실행(되돌림)", f"{type(e).__name__} {e}")

chk(io.open(os.path.join(HERE, "templates", "partner_portal.html"), encoding="utf-8").read()
    == HTML_SRC,
    "★★★★★ templates/partner_portal.html 은 이 검증 내내 디스크에 전혀 쓰이지 않았다"
    "(원본과 동일 — 되돌림은 전부 스크래치 사본에서만 일어났다)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
