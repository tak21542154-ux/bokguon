# -*- coding: utf-8 -*-
"""스캔 645라운드 회귀(직접조사, 하위위임 없음) — 시행사(협력사) 포털의
   '시공 현장' 카드(RENDER.sites, templates/partner_portal.html ~1495행)가
   같은 파일의 stTag() 와 별도인 자기완결 색상 조건식을 갖고 있던 결함.

   배경 — 라운드644가 이 파일의 stTag() 에서 '시공중'만 'blue'였던 걸(형제
   insurer_portal.html stTag·admin.js statusPill 은 둘 다 'green') 찾아
   고쳤다. 그때 라운드644는 RENDER.sites 카드(1505행 부근)의 별도 인라인
   조건문은 "stTag() 와 무관한, 자기완결적인 조건식이라 형제 불일치 증거가
   없다"며 의도적으로 건드리지 않고 다음 라운드 후보로만 남겼다.

   실측(이번 라운드) — 그 카드의 실제 코드(수정 전):
     <span class="tag ${c.status==='시공중'?'blue':(c.status==='완료보고지연'
       ?'red':(c.status==='검수대기'?'amber':'green'))}">${esc(c.status)}</span>
   이 조건식은 명시한 3개 값(시공중·완료보고지연·검수대기) 이외에는 전부
   'green' 으로 뭉갠다. 그런데 이 카드가 그리는 my_cases 는 app.py 의
   쿼리(약 5239행)가 status IN ('시공중','완료보고지연','검수대기',
   '정산진행','완료') 로 내려주므로 '완료'도 실제로 이 카드에 나타난다.
   같은 파일 stTag()(형제 insurer_portal.html stTag·admin.js statusPill
   과도 이미 일치)의 정답 매핑과 대조하면:
     · '시공중' → 여기선 'blue', stTag() 는 'green'  (불일치 1 — 라운드644와
       동종의 드리프트가 이 카드에도 남아 있었다)
     · '완료'   → 여기선 default 로 'green', stTag() 는 'gray'  (불일치 2 —
       라운드644도 미처 못 본, 이번에 새로 발견한 결함)
   '정산진행'(→ default 'green', stTag 도 'green')과 '완료보고지연'·
   '검수대기'는 우연히 일치해 지금까지 드러나지 않았다.

   고침 — templates/partner_portal.html 1511행의 별도 3항 조건식을 지우고
   같은 파일에 이미 있는(라운드644가 이미 형제와 동기화해 둔) stTag(c.status)
   호출로 교체했다(재사용 — 매핑을 두 곳에 유지하지 않는다). esc() 처리도
   stTag() 내부에서 이미 하므로 중복 escape 도 함께 제거됐다.

   회귀테스트(이 파일) —
   [1] 소스 — RENDER.sites 함수 몸통 안에서 옛 3항 조건식이 사라졌고
       stTag(c.status) 호출로 바뀌었음을 확인.
   [2] 소스 — stTag() 매핑 자체는 '시공중':'green'·'완료':'gray' 를 유지한다
       (이번 수정이 기댄 전제 — 회귀 여부와 무관하게 지금도 참이어야 한다).
   [3] 단위 — stTag() 를 파일에서 그대로 잘라내 Node.js 로 실행해, my_cases
       가 실제로 낼 수 있는 5개 상태값 전부(시공중·완료보고지연·검수대기·
       정산진행·완료) 에서 나오는 색상 클래스가 stTag() 의 정답과 실제로
       일치함을 실측한다.
   [4] 되돌리기(파일은 전혀 안 건드림, 메모리 문자열로만 재구성) — 지운
       옛 3항 조건식을 그대로 옮겨 적은 oldTagColor() 를 Node 로 실행해,
       옛 코드였다면 '시공중'→blue·'완료'→green 이 나와 stTag() 의 정답
       (green/gray)과 실제로 갈렸음을 재현 증명한다.
   [5] 종단 — 실제 Flask 템플릿 렌더(로그인 세션 없이 render_template 직접
       호출)로 partner_portal.html 을 그대로 그려, 서버가 실제로 내보내는
       HTML 안에 옛 조건식이 없고 새 호출이 살아 있는지 확인한다.

       python test_scan_round645_fixes.py
"""
import io
import json
import os
import re
import shutil
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


def func_src_brace(src, header):
    """header(예: 'function stTag(s){')부터, 그 뒤 처음 나오는 줄 첫머리
    단독 닫는 중괄호(\\n})까지 잘라낸다."""
    i = src.find(header)
    if i < 0:
        return ""
    j = src.find("\n}", i + len(header))
    return src[i:j + 2] if j >= 0 else ""


print("=" * 72)
print("  스캔 645라운드 회귀 — partner_portal.html RENDER.sites 카드 색상 불일치")
print("=" * 72)

PARTNER_SRC = read("templates/partner_portal.html")

# ============================================================
print("\n[1] 소스 — RENDER.sites 함수 몸통에서 옛 3항 조건식이 사라지고 stTag() 호출로 교체됐다")
# ------------------------------------------------------------
i_start = PARTNER_SRC.find("RENDER.sites = () => {")
i_end = PARTNER_SRC.find("\nRENDER.settle", i_start)
chk(i_start >= 0 and i_end > i_start, "  (전제) RENDER.sites 함수 경계를 찾았다")
SITES_BODY = PARTNER_SRC[i_start:i_end]

OLD_TERNARY = "c.status==='시공중'?'blue':(c.status==='완료보고지연'?'red':(c.status==='검수대기'?'amber':'green'))"
chk(OLD_TERNARY not in SITES_BODY,
    "★★★★★ RENDER.sites 안에 옛(자기완결) 3항 조건식이 더는 없다")
chk(OLD_TERNARY not in PARTNER_SRC,
    "  옛 조건식이 파일 전체 어디에도 남아 있지 않다(다른 카드로 옮겨간 것도 아니다)")
chk("${stTag(c.status)}" in SITES_BODY,
    "★★★★★ RENDER.sites 안에서 이제 stTag(c.status) 를 호출한다(매핑 재사용)")
chk(SITES_BODY.count("class=\"tag ") == 0,
    "  RENDER.sites 자신은 더 이상 'tag' 클래스를 직접 조립하지 않는다"
    "(stTag() 안에서만 조립 — 매핑이 한 곳에만 존재)")

# ============================================================
print("\n[2] 소스 — stTag() 매핑 자체가 이번 수정이 기대는 전제(시공중=green, 완료=gray)를 유지한다")
# ------------------------------------------------------------
STTAG_BODY = func_src_brace(PARTNER_SRC, "function stTag(s){")
chk(bool(STTAG_BODY), "  (전제) stTag() 함수 소스를 실제 파일에서 잘라냈다", f"len={len(STTAG_BODY)}")
chk("'시공중':'green'" in STTAG_BODY, "  (전제) stTag() 매핑의 '시공중' 은 'green' 이다(라운드644 상태 유지)")
chk("'완료':'gray'" in STTAG_BODY, "  (전제) stTag() 매핑의 '완료' 는 'gray' 이다")

# ============================================================
print("\n[3] 단위 — stTag() 를 그대로 잘라내 Node.js 로 실행, my_cases 의 5개 상태값 전부 대조")
# ------------------------------------------------------------
NODE = shutil.which("node")
if not NODE:
    chk(False, "node 실행파일을 찾을 수 없다 — 이 구간은 건너뛰지 않고 실패로 답한다")

ESC_LINE = re.search(r"const esc = s =>.*?;\n", PARTNER_SRC).group(0)

# app.py 약 5239행 쿼리가 my_cases 에 실제로 내려줄 수 있는 상태값 전부
# (WHERE c.status IN (...)) 와, stTag() 매핑에 적힌 정답.
REACHABLE_STATUSES = {
    "시공중": "green", "완료보고지연": "red", "검수대기": "amber",
    "정산진행": "green", "완료": "gray",
}
_APP_SRC = read("app.py")
chk("status IN ('시공중','완료보고지연','검수대기','정산진행','완료')" in _APP_SRC,
    "  (전제) app.py 의 my_cases 쿼리가 이 5개 상태값을 그대로 내려준다"
    "(도달 가능성 근거 — 하나라도 빠지면 아래 대조가 허수아비가 된다)")


def run_node(js):
    _tmp = tempfile.mkdtemp(prefix="round645_node_")
    p = os.path.join(_tmp, "probe.js")
    io.open(p, "w", encoding="utf-8").write(js)
    try:
        r = subprocess.run([NODE, p], capture_output=True, text=True, encoding="utf-8", timeout=15)
    finally:
        try:
            os.remove(p); os.rmdir(_tmp)
        except OSError:
            pass
    return r


def cls_of(html):
    m = re.search(r'class="tag ([a-z]+)"', html)
    return m.group(1) if m else None


if NODE:
    statuses_json = json.dumps(list(REACHABLE_STATUSES.keys()), ensure_ascii=False)
    probe = (
        ESC_LINE + "\n" + STTAG_BODY + "\n\n"
        + f"const statuses = {statuses_json};\n"
        + "console.log(JSON.stringify(Object.fromEntries(statuses.map(s => [s, stTag(s)]))));\n"
    )
    r = run_node(probe)
    chk(r.returncode == 0, "  Node 로 실제 stTag() 를 5개 상태값에 대해 실행했다", (r.stderr or "")[:300])
    out = json.loads(r.stdout.strip()) if r.returncode == 0 else {}
    for s, expect in REACHABLE_STATUSES.items():
        got = cls_of(out.get(s, ""))
        chk(got == expect,
            f"★★★★★ stTag('{s}') 실제 실행 결과가 카드에 적용될 색('{expect}')과 일치한다",
            f"실제: {got!r} / html={out.get(s)!r}")

# ============================================================
print("\n[4] 되돌리기(파일 무변경, 메모리 문자열만) — 지운 옛 조건식을 재현해 실제로 갈렸음을 증명")
# ------------------------------------------------------------
if NODE:
    OLD_FN = (
        "function oldTagColor(status){\n"
        "  const c = {status};\n"
        f"  const cls = {OLD_TERNARY};\n"
        "  return cls;\n"
        "}\n"
    )
    probe2 = (
        f"const statuses = {statuses_json};\n" + OLD_FN
        + "console.log(JSON.stringify(Object.fromEntries(statuses.map(s => [s, oldTagColor(s)]))));\n"
    )
    r2 = run_node(probe2)
    chk(r2.returncode == 0, "  Node 로 (메모리에서만 재구성한) 옛 조건식을 실제 실행했다", (r2.stderr or "")[:300])
    old_out = json.loads(r2.stdout.strip()) if r2.returncode == 0 else {}
    chk(old_out.get("시공중") == "blue",
        "★★★★★★ (인과관계 실측) 옛 조건식이었다면 '시공중' 카드는 실제로 'blue' 였다"
        "(stTag() 의 정답 'green' 과 갈린다 — 결함 1 재현)", str(old_out))
    chk(old_out.get("완료") == "green",
        "★★★★★★ (인과관계 실측) 옛 조건식이었다면 '완료' 카드는 실제로 'green' 이었다"
        "(stTag() 의 정답 'gray' 와 갈린다 — 결함 2 재현, 라운드644도 못 본 것)", str(old_out))
    # 우연히 일치했던 나머지 값도 함께 확인 — "전부 달랐다"는 과장이 아님을 보인다.
    _agree = [s for s in REACHABLE_STATUSES if old_out.get(s) == REACHABLE_STATUSES[s]]
    chk(set(_agree) == {"완료보고지연", "검수대기", "정산진행"},
        "  (정확성) 옛 조건식과 정답이 우연히 일치했던 값은 딱 이 3개뿐이었다"
        "(시공중·완료만 실제로 틀렸다)", f"일치: {_agree}")

# ============================================================
print("\n[5] 종단 — 실제 Flask 템플릿 렌더(로그인 세션 없이, test_template_js.py 와 같은 기법)")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round645_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "app.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import app as A  # noqa: E402
from flask import render_template  # noqa: E402

with A.app.test_request_context("/partner"):
    html_partner = render_template("partner_portal.html", nonce="testnonce", build="t", ver="t")

chk(OLD_TERNARY not in html_partner,
    "★★★★★ 실제로 렌더된 partner_portal.html 응답에 옛 조건식이 더는 없다")
chk("${stTag(c.status)}" in html_partner,
    "★★★★★ 실제로 렌더된 partner_portal.html 응답 안에 새 stTag(c.status) 호출이 살아 있다")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
