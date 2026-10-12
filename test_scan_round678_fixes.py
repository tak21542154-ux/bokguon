# -*- coding: utf-8 -*-
"""스캔 678라운드 회귀(직접조사, 하위위임 없음) — 테스트 인프라 자체의 사각지대 보강.
   기능 버그가 아니라 안전망(test_template_js.py) 의 커버리지 결함을 고친다.

   배경(round677 이 발견하고 손대지 않은 것) —
     test_template_js.py 는 각 템플릿을 실제로 렌더한 뒤
     `<script[^>]*>(.*?)</script>` 로 태그 사이 **본문**만 뽑아 node --check 로
     파싱한다. templates/admin.html 은 static/admin.js 를
     `<script src="{{ asset('admin.js') }}"></script>` 로 **외부 참조만** 하므로
     태그 사이가 비어 있어(`if s.strip()` 에 걸러짐) admin.js 의 실제 소스는
     이 파일이 "9/9 통과"를 찍는 동안 단 한 번도 node --check 를 받은 적이
     없었다 — actions.js·lightbox.js·addrpick.js·form.js·tray.js·upqueue.js·
     leaflet.js 도 같은 사각지대. 안전규칙 문서가 "static/admin.js 를 고치면
     test_template_js.py 를 재실행하라"고 15회 넘게 요구해 온 전제와 실제
     커버리지가 어긋나 있었다.

   고침(test_template_js.py) — 각 템플릿을 렌더할 때 이미 갖고 있는 HTML 에서
   `<script src="/static/....js">` 를 정규식으로 직접 뽑아(하드코딩 목록이
   아니라 그 순간 렌더 결과를 신뢰) 실제 파일 경로로 접어, 인라인처럼 잘라낼
   필요 없이 원본 그대로 node --check 한다. 같은 파일이 여러 템플릿에서
   참조되면(actions.js 등) 한 번만 검사한다. 새 test_scan_roundNNN 파일이
   아니라 기존 테스트 인프라 파일 자체를 고치는 것이라 이 회귀테스트는
   "그 고침이 실제로 사각지대를 메우는가"를 증명하는 데 집중한다.

   실측 결과(오늘 리포지토리) — 렌더된 9개 템플릿에서 정확히 8개의 고유
   static/*.js 파일이 발견된다: admin.js·actions.js·addrpick.js·form.js·
   leaflet/leaflet.js·lightbox.js·tray.js·upqueue.js — 전부 node --check 통과.
   (sw.js 는 <script src=> 로 참조되지 않는 서비스워커라 대상 밖 — 무관.)

   ⚠ 부수 발견(이번 라운드에서 함께 고침) — 위 고침을 이 환경(경로에 한글
   사용자명 "개발자3"이 낀 Windows)에서 직접 실행해 보다가, test_template_js.py의
   두 node --check subprocess.run 호출(기존 인라인용 1곳 + 이번에 늘린 외부참조용
   1곳) 모두 encoding 을 안 준다는 것을 발견했다 — node 가 실제 에러에서 그 경로를
   찍으면 파이썬 내부 리더 스레드가 OS 로케일(cp949)로 잘못 디코드하다 죽는다.
   프로세스 전체가 죽지는 않지만(실측: 예외가 메인 스레드로 전파되지 않는다)
   r.stderr 가 None 이 되어 정작 필요한 실패 원인 메시지가 통째로 사라지고,
   콘솔엔 무관해 보이는 스레드 traceback 만 남는다 — "실제로 파싱해 보는 것만이
   증거다"라는 이 파일의 취지가 정작 실패했을 때의 상세 진단에서는 무력화되는
   결함이다. 두 호출 모두 encoding="utf-8", errors="replace" 를 추가해 이 배터리의
   다른 서브프로세스 호출(run_all_tests.py의 run() 등)과 관례를 맞췄다.

   회귀테스트(이 파일) —
   [1] 소스 — test_template_js.py 자신에서 새 정규식·새 subprocess 호출·중복
       제거 구조를 실제로 잘라내 확인하고(손으로 재입력하지 않음), 파일명을
       하드코딩한 리스트가 없음(동적 탐색)을 확인. 기존 인라인 정규식은
       이번 라운드에서 안 건드렸음도 함께 확인.
   [2] 단위 — 실제 test_template_js.py 를 스크래치 DB 로 서브프로세스 실행해
       오늘 리포지토리에 대해 정말 통과하는지, 8개 파일 전부를 이름으로
       실제로 언급하는지 확인하고, 템플릿 원문을 독립적으로(렌더가 아니라
       소스 정규식으로) 다시 스캔해 그 개수·이름 집합이 일치함을 대조한다.
   [3] 인과관계 실측 — 실제 admin.html 을 렌더해, (a) 옛 인라인 정규식이
       admin.js 의 실제 내용(특징 토큰 "function statusPill")을 단 한 글자도
       못 본다는 것과, (b) 새 정규식은 그 자리에서 실제 static/admin.js 절대
       경로를 정확히 복원한다는 것을 같은 렌더 결과로 동시에 증명한 뒤,
       실제 admin.js 바이트를 스크래치 사본으로만 떠서(원본 무변경) 정상
       사본은 node --check 통과·마지막 '}' 한 글자만 제거한 손상 사본은
       실패로 갈리는 것을 실측한다 — "옛 경로는 손상 여부와 무관하게 늘
       통과, 새 경로는 정확히 반응"이라는 이번 수정의 핵심 효과를 재현한다.
       이어서 위 부수 발견(encoding)도 같은 손상 사본으로 재현 — encoding 없이
       돌리면 stderr 가 None 이 되어 진단이 사라짐을, encoding="utf-8"을 주면
       정상 메시지가 실려 옴을 나란히 실측한다.

       python test_scan_round678_fixes.py
"""
import io
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


print("=" * 72)
print("  스캔 678라운드 회귀 — test_template_js.py 의 <script src=> 사각지대 보강")
print("=" * 72)

TTJ_SRC = read("test_template_js.py")

# ============================================================
print("\n[1] 소스 확인 — 새 로직을 실제 파일에서 그대로 잘라내 확인")
# ------------------------------------------------------------
m_new = re.search(r"for src in re\.findall\((r'.*?')\s*,\s*html\)\s*:", TTJ_SRC)
chk(bool(m_new), "  새 src= 추출 정규식을 test_template_js.py에서 실제로 잘라냈다")
NEW_SRC_PATTERN = eval(m_new.group(1)) if m_new else None  # 우리 자신의 파일 리터럴 — 안전

m_old = re.search(r"for s in re\.findall\((r\".*?\")\s*,\s*html\s*,\s*re\.S\)", TTJ_SRC)
chk(bool(m_old), "  (회귀 없음) 기존 인라인 정규식도 그대로 남아 있어 함께 잘라냈다")
OLD_PATTERN = eval(m_old.group(1)) if m_old else None

chk('subprocess.run([NODE, "--check", fp]' in TTJ_SRC,
    "★★★ 새 코드가 인라인처럼 임시파일로 잘라내지 않고, 해석한 실제 경로(fp)를 "
    "그대로 node --check 한다(원본 파일 자체를 검사)")
chk("ext_js.setdefault(fp, set()).add(tpl)" in TTJ_SRC,
    "  같은 파일을 여러 템플릿이 참조해도 경로 기준으로 중복 제거한다")

# 부수 발견(이번 라운드에서 함께 고침) — subprocess.run(...,text=True) 두 곳 모두
# encoding 이 없으면 이 저장소 경로 자체에 낀 한글 때문에 실패 시 진단 메시지가
# 사라진다(아래 [3]에서 실제로 재현). 두 호출부 모두 고쳤는지 소스로 직접 확인한다.
_run_calls = [c[:200] for c in TTJ_SRC.split("subprocess.run(")[1:]]
chk(len(_run_calls) == 2,
    "  (harness) test_template_js.py에 subprocess.run 호출이 정확히 2곳(인라인 1·"
    "외부참조 1) 있다", len(_run_calls))
chk(all('encoding="utf-8"' in c and 'errors="replace"' in c for c in _run_calls),
    "★★★★★ (round678 부수 수정) 두 subprocess.run 호출 모두 encoding=\"utf-8\", "
    "errors=\"replace\" 를 명시한다 — 아래 [3]이 이 kwargs 없이 실제로 진단 메시지가 "
    "사라짐을 재현한다", _run_calls)

# 하드코딩 목록이 아니라 그때그때 렌더 결과에서 뽑는지 — 새로 늘어난 블록의 "코드"
# 줄(주석 제외) 안에 파일명이 따옴표로 박힌 리터럴이 없어야 한다. 주석 속 설명 예시
# (예: 이 파일 자신의 "asset('admin.js')" 같은 인용구)는 실행되는 데이터가 아니므로 제외한다.
_block_start = TTJ_SRC.find("ext_js = {}")
_new_block = TTJ_SRC[_block_start:] if _block_start >= 0 else ""
chk(bool(_new_block), "  (harness) 새 블록의 시작 지점을 찾았다")
_code_only = "\n".join(ln for ln in _new_block.splitlines() if not ln.strip().startswith("#"))
_hardcoded = re.findall(r'''["'][A-Za-z][A-Za-z0-9_./-]*\.js["']''', _code_only)
chk(not _hardcoded,
    "★★★ 새 블록의 코드(주석 제외) 어디에도 .js 파일명이 따옴표 문자열 리터럴로 "
    "박혀 있지 않다(하드코딩 목록이 아니라 렌더된 HTML에서 동적으로 찾는다)",
    str(_hardcoded))

if NEW_SRC_PATTERN:
    _probe_html = ('<script src="{{ asset(\'leaflet/leaflet.js\') }}"></script>'
                   .replace("{{ asset('leaflet/leaflet.js') }}", "/static/leaflet/leaflet.js?v=abcd123456"))
    _found = re.findall(NEW_SRC_PATTERN, _probe_html)
    chk(_found == ["/static/leaflet/leaflet.js?v=abcd123456"],
        "  (자기완결) 잘라낸 정규식이 중첩 경로(leaflet/leaflet.js)의 src도 정확히 뽑는다",
        _found)

print("\n[2] 단위 — 실제 test_template_js.py를 서브프로세스로 오늘 리포지토리에 대해 실행")
# ------------------------------------------------------------
NODE = shutil.which("node")
if not NODE:
    chk(False, "node 실행파일을 찾을 수 없다 — 이 구간은 건너뛰지 않고 실패로 답한다")

# 독립 경로 — 렌더가 아니라 템플릿 "원문"을 직접 정규식으로 스캔해 기대 집합을 만든다
# (test_template_js.py의 TARGETS 리스트를 그대로 잘라 써서, 검사 대상 자체는
#  일치시키되 탐색 방법은 렌더 대신 소스 스캔으로 완전히 다르게 한다).
m_targets = re.search(r"TARGETS = \[(.*?)\n\]", TTJ_SRC, re.S)
chk(bool(m_targets), "  TARGETS 목록을 test_template_js.py에서 그대로 잘라냈다")
TARGETS = eval("[" + m_targets.group(1) + "]") if m_targets else []

expected = {}
for tpl, _ in TARGETS:
    tpl_path = os.path.join(HERE, "templates", tpl)
    if not os.path.exists(tpl_path):
        continue
    src = io.open(tpl_path, encoding="utf-8").read()
    for name in re.findall(r"<script[^>]*\bsrc=\"\{\{\s*asset\('([^']+\.js)'\)\s*\}\}\"", src):
        expected.setdefault(name, set()).add(tpl)
chk(len(expected) > 0, "  (harness) 템플릿 원문 스캔으로 기대 파일 집합을 만들었다", sorted(expected))

if NODE:
    _scratch = tempfile.mkdtemp(prefix="round678_run_")
    _env = dict(os.environ)
    _env["BOKGUON_DB_PATH"] = os.path.join(_scratch, "verify.db")
    _env["BOKGUON_UPLOAD_DIR"] = os.path.join(_scratch, "uploads")
    _env["BOKGUON_LOG_FILE"] = os.path.join(_scratch, "verify.log")
    _env["BOKGUON_ENV"] = "dev"
    _env["BOKGUON_SEED_DEMO"] = "0"
    _env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run([sys.executable, "-u", "test_template_js.py"], cwd=HERE,
                        capture_output=True, text=True, env=_env,
                        encoding="utf-8", errors="replace", timeout=120)
    out = (r.stdout or "") + (r.stderr or "")
    chk(r.returncode == 0,
        "★★★★★ 실제 test_template_js.py를 스크래치 DB로 서브프로세스 실행 — 오늘 "
        "리포지토리에 대해 통과한다(0/9 실패)", out[-400:] if r.returncode else "")

    m_cnt = re.search(r"외부참조 JS 파일 (\d+)개", out)
    chk(bool(m_cnt), "  출력에서 '외부참조 JS 파일 N개' 집계 줄을 실제로 찾았다")
    if m_cnt:
        chk(int(m_cnt.group(1)) == len(expected),
            f"★★★★ 실행이 실제로 찾은 외부참조 JS 파일 수({m_cnt.group(1)}개)가 템플릿 "
            f"원문을 독립적으로 스캔한 기대 개수({len(expected)}개)와 일치한다",
            f"expected={sorted(expected)}")

    for name in sorted(expected):
        chk(f"static/{name}" in out,
            f"  ★ 실행 출력이 {name} 을(를) 실제로 이름으로 언급한다(자리만 세지 않고 "
            f"실제로 검사했다는 증거)")

    for tpl, _ in TARGETS:
        if os.path.exists(os.path.join(HERE, "templates", tpl)):
            chk(f"{tpl} — 인라인 JS" in out,
                f"  (회귀 없음) {tpl} 의 인라인 JS 검사 줄도 여전히 출력에 있다")
else:
    chk(False, "  [2] node가 없어 서브프로세스 실행을 건너뛸 수밖에 없었다")

# ============================================================
print("\n[3] 인과관계 실측 — 실제 admin.html 렌더 + 스크래치 손상사본으로 사각지대 재현")
#     ⚠ 실제 파일(static/admin.js, templates/admin.html)은 전혀 건드리지 않는다.
# ------------------------------------------------------------
if NODE:
    _tmpdir = tempfile.mkdtemp(prefix="round678_render_")
    os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
    os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
    os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "verify.log")
    os.environ["BOKGUON_ENV"] = "dev"
    os.environ["BOKGUON_SEED_DEMO"] = "0"
    sys.path.insert(0, HERE)

    import app as A  # noqa: E402
    from flask import render_template  # noqa: E402

    with A.app.test_request_context("/admin"):
        admin_html = render_template("admin.html", nonce="r678", build="t", ver="t")
    chk(bool(admin_html), "  admin.html 을 실제로 렌더했다(스크래치 DB, 읽기전용)")

    ADMIN_JS_SRC = read("static/admin.js")
    MARKER = "function statusPill("
    chk(MARKER in ADMIN_JS_SRC,
        "  (전제) 실제 static/admin.js에 특징 토큰(statusPill 정의)이 있다")

    if OLD_PATTERN:
        old_scripts = re.findall(OLD_PATTERN, admin_html, re.S)
        chk(any(s == "" for s in old_scripts),
            "  admin.html 렌더 결과 중 최소 한 태그는 옛 정규식이 빈 본문으로 뽑는다"
            "(src= 외부참조 자리)", str([len(s) for s in old_scripts]))
        chk(all(MARKER not in s for s in old_scripts),
            "★★★★★★ (사각지대 재현) 옛 인라인 정규식은 admin.js의 실제 내용을 단 "
            "한 글자도 못 본다 — statusPill 정의가 admin.html 렌더 결과 어디에도 "
            "'인라인 스크립트 본문'으로는 나타나지 않는다",
            f"추출된 인라인 스크립트 {len(old_scripts)}개, 총 {sum(len(s) for s in old_scripts)}자")

    if NEW_SRC_PATTERN:
        new_srcs = re.findall(NEW_SRC_PATTERN, admin_html)
        admin_src = next((s for s in new_srcs if "/static/admin.js" in s), None)
        chk(admin_src is not None,
            "  새 정규식은 같은 렌더 결과에서 admin.js의 src=를 실제로 찾는다", new_srcs)
        if admin_src:
            rel = admin_src.split("?", 1)[0].lstrip("/")
            fp = os.path.join(HERE, *rel.split("/"))
            chk(os.path.abspath(fp) == os.path.abspath(os.path.join(HERE, "static", "admin.js")),
                "★★★★★★ 그 src가 해석하는 실제 파일 경로가 static/admin.js 절대경로와 "
                "정확히 같다(같은 렌더 결과, 정반대 결론 — 이것이 이번 수정의 핵심 차이)",
                fp)

    # ---- 스크래치 사본으로만 손상을 재현한다(원본 무변경) ----
    good_p = os.path.join(_tmpdir, "admin_good.js")
    bad_p = os.path.join(_tmpdir, "admin_bad.js")
    io.open(good_p, "w", encoding="utf-8").write(ADMIN_JS_SRC)
    last_brace = ADMIN_JS_SRC.rfind("}")
    chk(last_brace > 0, "  (harness) admin.js 사본에서 마지막 '}' 위치를 찾았다")
    corrupted = ADMIN_JS_SRC[:last_brace] + ADMIN_JS_SRC[last_brace + 1:]
    io.open(bad_p, "w", encoding="utf-8").write(corrupted)

    #  ⚠ 이 스크래치 경로 자체가 %TEMP% 밑이라 한글 사용자명(개발자3)을 포함한다 —
    #    아래 [부수 발견] 재현을 위해 good/bad 둘 다 encoding 을 준 버전으로 확인한다.
    r_good = subprocess.run([NODE, "--check", good_p], capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    chk(r_good.returncode == 0,
        "  admin.js 무변경 사본은 node --check 를 통과한다(sanity, 회귀 없음)",
        (r_good.stderr or "")[:200])

    r_bad = subprocess.run([NODE, "--check", bad_p], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    chk(r_bad.returncode != 0,
        "★★★★★★ (인과관계 실측) 마지막 '}' 한 글자만 제거한 손상 사본은 node --check "
        "가 실제로 실패로 답한다 — round678 이전엔 admin.js 가 이 클래스의 실수를 "
        "**한 번도** 이 테스트로 못 걸렀다(외부참조라 본문 자체를 안 봤으므로)",
        (r_bad.stderr or "")[:200])
    chk(bool((r_bad.stderr or "").strip()),
        "  encoding=\"utf-8\" 을 주면 실패 진단 메시지도 정상적으로 실려 온다"
        "(비어 있지 않다)", repr(r_bad.stderr)[:200])

    chk(r_good.returncode == 0 and r_bad.returncode != 0
        and OLD_PATTERN and all(MARKER not in s for s in old_scripts),
        "★★★★★★★ 결론 — 옛 경로(인라인 정규식)는 이 손상을 구조적으로 볼 수 없고"
        "(위에서 실측), 새 경로(node --check on 실제 파일)는 정확히 반응한다"
        "(방금 실측) — round678 의 수정이 이 구체적 격차를 메운다")

    # ---- 부수 발견 재현: encoding 미지정이면 이 환경에서 진단 메시지가 사라진다 ----
    #      (실측: 메인 스레드로 예외가 전파되지는 않는다 — subprocess 내부 리더
    #      스레드가 조용히 죽고 stderr 가 None 이 된다. "검사기가 죽는다"가 아니라
    #      "실패는 잡히는데 원인 메시지가 비어버린다"가 정확한 증상이다.)
    r_bad_noenc = subprocess.run([NODE, "--check", bad_p], capture_output=True, text=True)
    chk(r_bad_noenc.returncode != 0,
        "  (부수 발견 재현 전제) encoding 없이 돌려도 returncode 자체는 여전히 "
        "실패(1)로 정상 반영된다", r_bad_noenc.returncode)
    chk(r_bad_noenc.stderr in (None, ""),
        "★★★★★ (부수 발견 재현) 그런데 encoding 을 안 주면 이 환경(경로에 '개발자3' "
        "포함)에서 stderr 가 None/빈 문자열이 되어 실패 원인 메시지가 통째로 사라진다 "
        "— round678 이전 test_template_js.py의 두 node --check 호출이 실제 실패 시 "
        "이랬을 것이다(진단 상세만 소실, FAIL 판정 자체는 살아있었다)",
        repr(r_bad_noenc.stderr))

    # 실제 파일은 여전히 무변경인지 마지막으로 재확인 — 스크래치 사본만 다뤘다.
    chk(read("static/admin.js") == ADMIN_JS_SRC,
        "  (sanity) 실제 static/admin.js 는 이 테스트 도중에도 바이트 단위로 무변경이다")
else:
    chk(False, "  [3] node가 없어 인과관계 실측을 건너뛸 수밖에 없었다")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
