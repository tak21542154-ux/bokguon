# -*- coding: utf-8 -*-
"""스캔 569라운드 회귀 — 어드민 콘솔 자체 모달(직접조사, 하위위임 없음).

  피해자 조회 링크 발급 모달(트리거: trackLink(id), static/admin.js)의
  주소 입력칸이 인라인 onclick="this.select()" 로 "클릭하면 전체 선택"을
  구현하고 있었는데, 이 앱의 전역 CSP(app.py:_security_headers,
  script-src 'self' 'nonce-…' — unsafe-inline/unsafe-hashes 전혀 없음)가
  인라인 이벤트 핸들러를 무조건 차단한다. round319가 이미 같은 이유로
  서버 렌더 템플릿 3곳(offline.html 등)의 <button onclick=...>을 잡아냈지만,
  그 수정은 세 파일만의 일회성 정규식 테스트였다 — admin.js가 **JS 안에서
  직접 그리는** 모달(서버가 내려주는 HTML이 아니라 브라우저에서 문자열로
  조립되는 마크업)까지는 어떤 상시 회귀검사도 보지 않았다.

  기존 상시검사(test_dead_actions.py, 매 라운드 실행)도 이 결함을 못 잡는다 —
  그 검사는 data-act="이름" ↔ ACT.이름 등록의 '짝이 맞는가'만 본다. 인라인
  onclick 은애초에 data-act 자체가 없으니 '미등록'으로도 안 걸린다(사각지대).

  실제 영향 — 클릭해도 아무 일도 없다(콘솔 에러도 없다, CSP 위반 경고만
  뜨는데 운영자는 개발자도구를 안 연다). 다만 이 모달엔 실제 복사를 담당하는
  "주소 복사" 버튼(data-act="copyTrack")이 이미 정상 동작해 주 기능은
  살아 있었다 — 입력칸 자체를 클릭해 수동으로 선택하려던 보조 동선만 죽어
  있었다[경미].

  고침 —
   ① static/admin.js: trackLink()의 <input id="tk_url" ...> 에서
      onclick="this.select()" 를 제거하고 data-act="selectText" 로 교체,
      바로 위에 ACT.selectText = (a, el) => el.select(); 를 새로 등록
      (기존 관용구 — 모든 형제 상호작용이 쓰는 것과 동일한 data-act/ACT 방식,
      새 메커니즘 없음).
   ② test_dead_actions.py: "인라인 이벤트 핸들러가 없다" 상시검사를 신설해
      data-act 존재 여부와 무관하게 admin.js·actions.js·admin.html·
      insurer_portal.html·partner_portal.html 전체에서 <tag on*="...">
      패턴을 정규식으로 잡는다 — round319가 세 템플릿에서만 일회성으로 잡던
      것을, 이 세션이 매 라운드 도는 상시 배터리 안에 들여 "앞으로 추가될
      인라인 핸들러도 자동으로" 잡히게 한다(단일 지점, 대상 파일이 늘어도
      SCREENS 딕셔너리 재사용).

  이 회귀테스트는 ONLY 안전한 기법만 쓴다 — on-disk 파일은 조회만 하고,
  "되돌리기" 증명은 admin.js 실제 문자열에서 이 한 줄만 옛 버전으로 되돌린
  **메모리상의 문자열**([5])과, 위임 디스패처 계약을 그대로 옮긴 순수
  파이썬 시뮬레이션([6])으로 한다. 파일 쓰기·exec() 로 실제 앱 상태를
  바꾸는 동작은 전혀 없다.

      python test_scan_round569_fixes.py
"""
import io
import os
import re
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
print("  스캔 569라운드 회귀 — 어드민 모달 인라인 onclick이 CSP에 막혀 죽어있던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — admin.js 의 trackLink() 모달이 실제로 고쳐졌는가")
# ------------------------------------------------------------
ADMIN_JS_SRC = read("static/admin.js")
_tl_start = ADMIN_JS_SRC.index("\nasync function trackLink(id){")
_tl_end = ADMIN_JS_SRC.index("\nasync function ", _tl_start + 10)
TL_SRC = ADMIN_JS_SRC[_tl_start:_tl_end]

NEW_LINE = '<input id="tk_url" value="${esc(url)}" readonly data-act="selectText"></div>'
OLD_LINE = '<input id="tk_url" value="${esc(url)}" readonly onclick="this.select()"></div>'

chk(NEW_LINE in TL_SRC,
    "★★★★★ trackLink() 모달의 tk_url 입력칸이 이제 data-act=\"selectText\" 를 쓴다")
chk("onclick=" not in TL_SRC,
    "★★★★★ trackLink() 모달 안에 인라인 onclick= 이 더 이상 없다")
chk('data-act="copyTrack"' in TL_SRC,
    "  회귀 방지: 같은 모달의 실제 복사 버튼(copyTrack)은 그대로 남아 있다 — 주 기능 훼손 없음")

_st_m = re.search(r"ACT\.selectText\s*=\s*\(([^)]*)\)\s*=>\s*([^;]+);", ADMIN_JS_SRC)
chk(_st_m is not None, "★★★★★ ACT.selectText 가 admin.js 에 실제로 등록돼 있다")
if _st_m:
    chk("el" in [p.strip() for p in _st_m.group(1).split(",")],
        "  ACT.selectText 가 두 번째 인자(el, actions.js run()의 dispatch 계약)를 받는다",
        _st_m.group(1))
    chk(_st_m.group(2).strip() == "el.select()",
        "★★★★★ ACT.selectText 의 본문이 정확히 el.select() 다", _st_m.group(2))

# ============================================================
print("\n[2] 소스 확인 — admin.js 전체에 인라인 on*= 핸들러가 전무하다(이 한 곳만의 임시방편이 아님)")
# ------------------------------------------------------------
DA_SRC = read("test_dead_actions.py")
_pat_m = re.search(r"INLINE_HANDLER_RE = re\.compile\(r'(.+?)'\)", DA_SRC)
chk(_pat_m is not None,
    "  test_dead_actions.py 에서 신설된 INLINE_HANDLER_RE 정규식을 그대로 추출했다")
INLINE_HANDLER_RE = re.compile(_pat_m.group(1)) if _pat_m else None

if INLINE_HANDLER_RE:
    chk(not INLINE_HANDLER_RE.findall(ADMIN_JS_SRC),
        "★★★★ 고친 현재 admin.js 전체가 이 정규식을 통과한다(0건)")

# ============================================================
print("\n[3] 되돌리기 증명 — 이 한 줄만 옛 버전으로 되돌린 문자열엔 새 검사가 실제로 걸린다")
# ------------------------------------------------------------
#  ⚠ on-disk admin.js 는 건드리지 않는다 — 실제 현재 문자열에서 딱 이 한 줄만
#    치환한 **메모리상의 별도 문자열**을 만들어 인과관계를 증명한다.
chk(OLD_LINE not in ADMIN_JS_SRC, "  (전제) 옛 인라인 onclick 줄은 실제 파일에 더 이상 없다")
OLD_ADMIN_JS_SRC = ADMIN_JS_SRC.replace(NEW_LINE, OLD_LINE, 1)
chk(OLD_ADMIN_JS_SRC != ADMIN_JS_SRC and OLD_LINE in OLD_ADMIN_JS_SRC,
    "  (전제) 되돌린 메모리 문자열에는 옛 줄이 실제로 들어갔다")

if INLINE_HANDLER_RE:
    old_hits = INLINE_HANDLER_RE.findall(OLD_ADMIN_JS_SRC)
    chk(bool(old_hits),
        "★★★★★★ 되돌린(옛) admin.js 문자열은 새로 만든 상시검사(INLINE_HANDLER_RE)에 실제로 걸린다"
        " — 이 검사가 이미 있었다면 애초에 이 결함이 통과 못 했을 것", old_hits)
    new_hits = INLINE_HANDLER_RE.findall(ADMIN_JS_SRC)
    chk(not new_hits,
        "★★★★★★ 원상태(고친 현재) admin.js 는 같은 검사를 다시 돌려도 여전히 통과한다(0건)")

# ============================================================
print("\n[4] 되돌리기 증명 — 위임 디스패처 계약 시뮬레이션(actions.js run()을 그대로 옮김)")
# ------------------------------------------------------------
#  actions.js: var name = el.getAttribute('data-act'); var fn = window.ACT[name];
#  data-act 자체가 없으면 document.querySelector 의 closest('[data-act]') 가
#  애초에 그 요소를 후보로도 못 올린다 — 그래서 "속성이 없다"를 곧 "위임
#  체계로는 100% 무반응"으로 취급한다(실제 브라우저 동작과 동일).
class MockEl:
    def __init__(self, attrs):
        self._attrs = attrs
        self.selected = False

    def getAttribute(self, name):
        return self._attrs.get(name)

    def select(self):
        self.selected = True


def act_dispatch(el, registry):
    name = el.getAttribute("data-act")
    if name is None:
        return "NO_DATA_ACT"          # closest('[data-act]') 조차 못 찾음 — 클릭 무반응
    fn = registry.get(name)
    if fn is None:
        return "UNREGISTERED"          # 이름은 있는데 등록이 없음(형제 결함 유형, 이번 건 아님)
    fn(el.getAttribute("data-arg"), el)
    return "DISPATCHED"


#  admin.js 에 실제로 등록된 ACT 이름 전체를 그대로 가져와, "selectText" 가
#  진짜 그 안에 있는지까지 확인한다(가짜 레지스트리로 자문자답하지 않는다).
DEF_RE = re.compile(r"""ACT\s*(?:\.\s*([A-Za-z0-9_]+)|\[\s*['"]([A-Za-z0-9_]+)['"]\s*\])\s*=""")
REAL_ACT_NAMES = {m.group(1) or m.group(2) for m in DEF_RE.finditer(ADMIN_JS_SRC)}
chk("selectText" in REAL_ACT_NAMES,
    "  (전제) 'selectText' 가 admin.js 의 실제 ACT 등록 이름 집합 안에 있다")

REGISTRY_SIM = {"selectText": lambda arg, el: el.select()}

old_el = MockEl({})                              # 옛 마크업 — data-act 자체가 없다
new_el = MockEl({"data-act": "selectText"})       # 새 마크업

r_old = act_dispatch(old_el, REGISTRY_SIM)
r_new = act_dispatch(new_el, REGISTRY_SIM)

chk(r_old == "NO_DATA_ACT" and old_el.selected is False,
    "★★★★★★ 옛 마크업(onclick만 있음)은 위임 디스패처 후보에도 못 오른다 — select() 가 절대 안 불린다",
    r_old)
chk(r_new == "DISPATCHED" and new_el.selected is True,
    "★★★★★★ 새 마크업(data-act=selectText)은 실제로 디스패치되어 select() 가 불린다",
    r_new)

# ============================================================
print("\n[5] 실측 — 실제 살아있는 앱의 CSP 헤더가 인라인 핸들러를 무조건 차단하는 이유를 확인")
# ------------------------------------------------------------
#  round319와 동일 기법 — 인증 불필요한 /offline 라우트로 실제 CSP 헤더를 받아
#  script-src 에 unsafe-inline·unsafe-hashes 가 전혀 없음을 실측한다
#  (nonce 는 <script> 태그 전용이라 인라인 이벤트 핸들러엔 애초에 붙을 자리가 없다).
_tmpdir = tempfile.mkdtemp(prefix="round569_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB
DB.init_db()
import app as A

client = A.app.test_client()
r = client.get("/offline")
csp = r.headers.get("Content-Security-Policy", "")
script_src = next((p.strip() for p in csp.split(";") if p.strip().startswith("script-src")), "")
chk(r.status_code == 200 and bool(script_src), "  /offline 200 + CSP 헤더에 script-src 가 있다", script_src)
chk("'unsafe-inline'" not in script_src and "'unsafe-hashes'" not in script_src,
    "★★★★★ 실제 CSP script-src 에 unsafe-inline·unsafe-hashes 가 전혀 없다"
    " — 인라인 on*= 핸들러는 이 서버가 실제로 내려주는 헤더 기준으로도 무조건 차단된다",
    script_src)

# ============================================================
print("\n[6] 실행 — test_dead_actions.py(상시검사)를 실제로 서브프로세스 실행해 통과를 확인")
# ------------------------------------------------------------
#  ⚠ Windows 콘솔 기본 코드페이지(cp949)로 자동판정하면 한글 출력이
#    UnicodeDecodeError 를 낸다 — 자식 프로세스에도 PYTHONIOENCODING=utf-8 을
#    물려주고, 부모의 디코딩도 utf-8 로 고정한다(이 저장소의 표준 관례).
_env = dict(os.environ, PYTHONIOENCODING="utf-8")
proc = subprocess.run([sys.executable, "test_dead_actions.py"], cwd=HERE,
                       capture_output=True, encoding="utf-8", errors="replace",
                       env=_env, timeout=60)
chk(proc.returncode == 0,
    "★★★★★ test_dead_actions.py 실제 실행이 0(전부 통과)으로 끝난다", proc.returncode)
chk("인라인 이벤트 핸들러가 없다" in proc.stdout,
    "  실제 실행 출력에 신설된 인라인 핸들러 검사 구간이 들어 있다")
chk("static/admin.js — 인라인 on*= 이벤트 핸들러가 없다" in proc.stdout,
    "  실제 실행 출력에 admin.js 가 그 검사를 통과했다는 줄이 있다")

# ── 정리 ──────────────────────────────────────────────────────
print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
