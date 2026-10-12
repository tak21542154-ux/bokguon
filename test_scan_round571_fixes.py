# -*- coding: utf-8 -*-
"""스캔 571라운드 회귀 — "인라인 이벤트 핸들러가 없다" 상시검사(round569 신설,
   test_dead_actions.py)가 자기 docstring/등록설명의 "재발을 이 검사 하나로
   앞으로도 막는다"는 약속과 달리, 실제 스캔 범위는 SCREENS 딕셔너리(3화면 ·
   5개 파일 — static/admin.js·actions.js·templates/admin.html·
   insurer_portal.html·partner_portal.html)뿐이었던 결함(직접조사, 하위위임 없음).

   조사 각도 — round565~570 이 반복해 온 "형제 사이에 좁게 닫힌 방어를 전수
   재확인" 패턴을 이 검사 자신에게 적용했다. round569 는 "data-act 존재
   여부와 무관하게 admin.js·actions.js·admin.html·insurer_portal.html·
   partner_portal.html 전체에서 <tag on*="..."> 패턴을 잡아 앞으로 추가되는
   인라인 핸들러에도 자동 적용되게 한다"고 등록설명에 명시했다. 그런데
   실제 이 프로젝트의 templates/*.html 은 20개, static/*.js 는 8개다 —
   위 5개를 뺀 나머지 templates 15개(하필 round319 가 **원래** <button
   onclick= 을 고쳤던 offline.html·case_history.html·insurer_api_guide.html
   세 곳도 포함 — 그 셋은 test_scan_round319_fixes.py 가 <button onclick= 이라는
   좁은 패턴 하나만 별도로 볼 뿐, on*= 전체나 다른 태그는 안 본다)와 static
   JS 6개(addrpick.js·form.js·lightbox.js·sw.js·tray.js·upqueue.js)가 이
   "상시" 검사의 사각지대였다.

   실제 영향 — app.py:_security_headers 는 `@app.after_request` 라 예외 없이
   모든 응답에 같은 CSP(script-src 'self' 'nonce-…', unsafe-inline/-hashes
   전혀 없음)를 붙인다(실측: 코드 확인). 즉 CSP 위험 자체는 SCREENS 3화면에
   국한되지 않는데, 그 위험을 잡는 유일한 상시검사는 3화면에만 국한돼 있었다.
   지금 이 순간 실제 20+8개 파일을 전부 훑어도(이 테스트 [3]에서 실측)
   위반 0건이라 **당장 살아있는 죽은 버튼은 없다** — 이 라운드는 "다음에
   생길 회귀를 이 검사가 정말로 잡는가"라는 검사 자신의 커버리지 결함이다.

   고침 — test_dead_actions.py 단일 지점(이 검사의 유일한 정의처, 다른
   caller 없음). SCREENS 에서 파일 목록을 뽑던 `_inline_files` 를
   `glob.glob("templates/*.html")`+`glob.glob("static/*.js")` 로 교체했다.
   data-act↔ACT 대조(SCREENS 기반, 손대지 않음)는 화면 단위 defines/uses
   짝이 구조적으로 필요하지만, 인라인 핸들러 검사는 "화면"이 아니라 "브라우저에
   내려가는 파일" 단위라 글롭이 더 정확한 수렴점이다. static/leaflet/ 처럼
   하위 폴더에 있는 외부 라이브러리는 글롭이 비재귀라 자연히 빠진다(의도된
   범위 — 우리가 안 쓴 벤더 코드를 검사할 이유가 없다).

   이 회귀테스트는 on-disk test_dead_actions.py 를 조회만 한다. "되돌리기"
   증명은 실제 파일에서 SCREENS 블록과 새 글롭 코드를 그대로 잘라내 별도
   네임스페이스에서 exec() 하고(라운드562·570과 같은 기법), 스크래치 디렉토리에
   심은 가짜 파일로 인과관계를 실측한다. 마지막으로 실제 test_dead_actions.py
   를 서브프로세스로 그대로 실행해 저장소 전체가 여전히 0건임을 확인한다.

      python test_scan_round571_fixes.py
"""
import glob
import io
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
print("  스캔 571라운드 회귀 — 인라인 핸들러 상시검사의 스캔 범위 누락(SCREENS 5개뿐)")
print("=" * 72)

DA_SRC = read("test_dead_actions.py")

# ============================================================
print("\n[1] 소스 확인 — test_dead_actions.py 가 실제로 넓어졌는가")
# ------------------------------------------------------------
chk("import glob" in DA_SRC, "★★★★★ glob 모듈을 새로 import 한다")
chk('glob.glob(os.path.join(HERE, pat))' in DA_SRC
    and 'for pat in ("templates/*.html", "static/*.js")' in DA_SRC,
    "★★★★★ _inline_files 가 SCREENS 대신 templates/*.html·static/*.js 글롭으로 뽑힌다")
chk("for cfg in SCREENS.values() for rel in cfg[\"defines\"] + cfg[\"uses\"]" not in DA_SRC,
    "★★★★ 옛(SCREENS 전용) _inline_files 정의가 더는 없다")
# 회귀 방지 — data-act↔ACT 대조(다른 검사)는 이번 라운드가 손대지 않는다
chk('SCREENS = {' in DA_SRC and '"어드민 콘솔"' in DA_SRC and '"보험사 포털"' in DA_SRC
    and '"협력사 포털"' in DA_SRC,
    "  회귀 방지: SCREENS 딕셔너리(다른 검사가 쓴다) 자체는 그대로 남아 있다")
chk("DEF_RE = re.compile" in DA_SRC and "USE_RE = re.compile" in DA_SRC,
    "  회귀 방지: data-act↔ACT 대조 정규식이 그대로다")
chk('for screen, cfg in SCREENS.items():' in DA_SRC,
    "  회귀 방지: SCREENS 기반 죽은버튼 루프 자체는 그대로다")

# ============================================================
print("\n[2] 되돌리기 — 실제 파일에서 SCREENS 블록 + 새 글롭 코드를 그대로 잘라내")
print("    exec()로 돌리면, 옛 방식이 놓치던 파일을 새 방식은 잡는가 (인과관계)")
# ------------------------------------------------------------
#  ⚠ 손으로 SCREENS 를 베끼면 실제 파일과 몰래 어긋날 수 있다 — on-disk 소스에서
#    정확히 그 블록만 오려내 exec() 한다(라운드562·570과 같은 안전 기법).
_scr_start = DA_SRC.index("SCREENS = {")
_scr_end = DA_SRC.index("\n}\n", _scr_start) + 3
SCREENS_SRC = DA_SRC[_scr_start:_scr_end]
_ns = {}
exec(SCREENS_SRC, {}, _ns)
SCREENS_REAL = _ns["SCREENS"]

OLD_FILES = sorted({rel for cfg in SCREENS_REAL.values() for rel in cfg["defines"] + cfg["uses"]})
NEW_FILES = sorted(
    os.path.relpath(p, HERE).replace(os.sep, "/")
    for pat in ("templates/*.html", "static/*.js")
    for p in glob.glob(os.path.join(HERE, pat)))

chk(OLD_FILES == ["static/actions.js", "static/admin.js", "templates/admin.html",
                   "templates/insurer_portal.html", "templates/partner_portal.html"],
    "★★★★★ 옛(SCREENS 전용) 스캔 대상은 정확히 5개 파일이었다(실측)", OLD_FILES)
chk(len(NEW_FILES) >= 26,
    f"★★★★★ 새 스캔 대상은 {len(NEW_FILES)}개로 5개보다 훨씬 넓다", NEW_FILES)
_missed_by_old = sorted(set(NEW_FILES) - set(OLD_FILES))
chk("templates/login.html" in _missed_by_old and "templates/landing.html" in _missed_by_old,
    "  일반 진입 화면(login·landing)이 옛 스캔에서는 빠져 있었다")
chk("templates/offline.html" in _missed_by_old
    and "templates/case_history.html" in _missed_by_old
    and "templates/insurer_api_guide.html" in _missed_by_old,
    "★★★★★★ (핵심) round319가 **원래 <button onclick= 버그를 고쳤던 바로 그 세 파일**"
    "(offline·case_history·insurer_api_guide)조차 round569의 '상시' 인라인 핸들러 검사"
    "에는 빠져 있었다", _missed_by_old)
chk("static/form.js" in _missed_by_old and "static/addrpick.js" in _missed_by_old,
    "  정적 JS 6개(form.js·addrpick.js 등)도 옛 스캔에서는 빠져 있었다")
chk(len(_missed_by_old) >= 21,
    f"★★★★★ 옛 스캔이 놓치던 파일이 {len(_missed_by_old)}개나 됐다(새 스캔은 전부 포함)")

# ============================================================
print("\n[3] 실제 영향 실측 — 스크래치 디렉토리에 심은 가짜 버그를 옛 방식은")
print("    놓치고 새 방식은 잡는가 (되돌리기의 인과관계 핵심)")
# ------------------------------------------------------------
INLINE_HANDLER_RE_SRC = DA_SRC[DA_SRC.index("INLINE_HANDLER_RE = re.compile("):]
INLINE_HANDLER_RE_SRC = INLINE_HANDLER_RE_SRC[:INLINE_HANDLER_RE_SRC.index("\n")]
_ns2 = {}
exec("import re\n" + INLINE_HANDLER_RE_SRC, {}, _ns2)
INLINE_RE = _ns2["INLINE_HANDLER_RE"]

_tmp = tempfile.mkdtemp(prefix="round571_")
os.makedirs(os.path.join(_tmp, "templates"))
os.makedirs(os.path.join(_tmp, "static"))
#  SCREENS 의 5개 파일은 깨끗하게(빈 내용) — 옛 스캔도 여기선 통과해야 정상이다.
for rel in OLD_FILES:
    p = os.path.join(_tmp, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, "w", encoding="utf-8").write("<html></html>")
#  ★ SCREENS 밖의 화면(login.html)에 실제 죽은 버튼을 심는다 — CSP가 막는
#    바로 그 모양(<button onclick=...)이다.
BUGGY_REL = "templates/login.html"
io.open(os.path.join(_tmp, BUGGY_REL), "w", encoding="utf-8").write(
    '<button onclick="doLogin()">로그인</button>')
#  벤더 라이브러리(하위 폴더)는 절대 스캔되면 안 된다 — 일부러 심하게 오염시켜 둔다.
os.makedirs(os.path.join(_tmp, "static", "leaflet"))
io.open(os.path.join(_tmp, "static", "leaflet", "leaflet.js"), "w", encoding="utf-8").write(
    'x.setAttribute("onclick", "evil()");  /* 실제 속성 리터럴이 아니라 스캔 밖 */')


def _old_scan(root):
    bad_files = []
    for rel in OLD_FILES:
        p = os.path.join(root, rel)
        txt = io.open(p, encoding="utf-8").read() if os.path.exists(p) else ""
        if INLINE_RE.findall(txt):
            bad_files.append(rel)
    return bad_files


def _new_scan(root):
    bad_files = []
    files = sorted(
        os.path.relpath(p, root).replace(os.sep, "/")
        for pat in ("templates/*.html", "static/*.js")
        for p in glob.glob(os.path.join(root, pat)))
    for rel in files:
        p = os.path.join(root, rel)
        txt = io.open(p, encoding="utf-8").read()
        if INLINE_RE.findall(txt):
            bad_files.append(rel)
    return bad_files


old_bad = _old_scan(_tmp)
new_bad = _new_scan(_tmp)
chk(old_bad == [],
    "★★★★★★ (핵심 증거) 옛 스캔(SCREENS 5개 파일만)은 login.html에 심은 죽은 "
    "버튼을 완전히 놓친다 — 검사가 0건/전부통과로 답해 '이상 없음'이라고 말한다",
    old_bad)
chk(new_bad == [BUGGY_REL],
    "★★★★★★ (핵심 증거) 새 스캔(글롭)은 같은 디렉토리에서 정확히 그 파일 하나를 "
    "잡아낸다", new_bad)
chk(not any("leaflet" in b for b in new_bad),
    "  벤더 라이브러리(static/leaflet/, 하위 폴더)는 글롭이 비재귀라 스캔되지 않는다"
    "(의도된 범위 — 오탐 방지)", new_bad)

# ============================================================
print("\n[4] 실행 — 실제 test_dead_actions.py를 서브프로세스로 그대로 돌려")
print("    저장소 전체가 지금 정말로 0건인지 확인 (현재는 클린 — 미래 회귀만 방지)")
# ------------------------------------------------------------
r = subprocess.run([sys.executable, "-u", os.path.join(HERE, "test_dead_actions.py")],
                    capture_output=True, text=True, cwd=HERE, encoding="utf-8")
chk(r.returncode == 0, "★★★★★ test_dead_actions.py 를 실제로 실행하면 종료코드 0(전부 통과)",
    (r.returncode, r.stdout[-800:], r.stderr[-800:]))
for must in ("templates/login.html", "templates/landing.html", "templates/offline.html",
             "templates/case_history.html", "templates/insurer_api_guide.html",
             "static/form.js", "static/addrpick.js", "static/lightbox.js",
             "static/sw.js", "static/tray.js", "static/upqueue.js"):
    chk(must in r.stdout,
        f"★★★★ 실제 실행 출력에 {must} 검사 결과가 실제로 찍힌다(진짜로 스캔됐다는 증거)")
# 회귀 방지 — 죽은버튼(data-act↔ACT) 대조와 메뉴 제목 검사도 여전히 도는지
chk("어드민 콘솔 — data-act 를 찾았다" in r.stdout and "보험사 포털" in r.stdout
    and "협력사 포털" in r.stdout,
    "  회귀 방지: SCREENS 기반 죽은버튼 검사도 실제 실행에서 여전히 돈다")
chk("모든 메뉴 항목에 한글 제목이 있다" in r.stdout,
    "  회귀 방지: 메뉴 제목 검사도 실제 실행에서 여전히 돈다")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
