# -*- coding: utf-8 -*-
"""스캔 230라운드 회귀 — build_pages.py 의 공개 정적 사이트(docs/)가
   서버 전용 경로를 그대로 실어 나르던 결함 두 가지.

  [1] landing.html 의 서비스워커 등록 스크립트는 서버가 직접 호스팅할
      때만 뜻이 있다 — /sw.js 는 서버가 굳이 **루트**에서 서빙한다
      (스코프를 '/' 로 만들기 위해서, app.py 자체 주석 참고). 그런데 이
      정적 빌드는 static/ 를 통째로 docs/static/ 로만 옮겨(sw.js 도
      거기로만 감) 루트엔 아무것도 없다 — 실측: 실제 배포된
      docs/index.html 이 여전히 '/sw.js' 를 그대로 등록 시도해 조용히
      404(.catch 로 감춰짐)만 냈다. 설령 경로를 맞춰도 sw.js 자신이
      __APP_VERSION__·__BUILD__ 자리표시자를 그대로 담고 있고(서버
      라우트가 실행 시점에 채우는 값), 캐시할 목록에 이 빌드가
      의도적으로 빼는 static/actions.js·form.js 까지 들어 있어 정적
      사이트에서는 애초에 완전하게 살릴 수 없는 기능이다 — 반쪽짜리를
      어설프게 흉내내는 대신 지운다.
  [2] manifest.webmanifest 도 절대경로(도메인 루트 기준)를 그대로 담고
      있었다 — 실서버는 루트에 뜨지만 이 정적 사이트는 GitHub Pages
      **프로젝트** 사이트라 서브경로(<계정>.github.io/<저장소>/)에
      뜬다(deploy\\외부공개_안내.md 가 그 주소 형태를 그렇게 안내한다).
      "/" 를 그대로 두면 설치 시도 시 시작주소·스코프가 계정 루트로
      잘못 잡히고 "/static/icons/..." 도 깨진다 — manifest 파일 자신을
      기준으로 한 상대경로로 바꾼다.
  [3] manifest.webmanifest 의 shortcuts.url("/insurer"·"/partner")도 같은
      계열 — 정적 사이트엔 그 경로로 갈 백엔드가 없다. 본문 링크(fix_links)
      와 같은 규칙(실서비스 주소 있으면 그쪽, 없으면 죽은 링크를 안 만든다)
      을 따르되, PWA 바로가기는 tel:/mailto: 로 못 바꾸므로 주소가 없으면
      바로가기 자체를 통째로 뺀다.

      python test_scan_round230_fixes.py
"""
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


BP_SRC = read("build_pages.py")
LANDING_SRC = read("templates/landing.html")

print("═" * 72)
print("  스캔 230라운드 회귀 — 공개 정적 사이트의 죽은 서비스워커 등록")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — strip_jinja() 함수 경계 안")
# ──────────────────────────────────────────────────────────────
sj_body = _py_fn_body(BP_SRC, "strip_jinja")
#  ⚠ 소스엔 정규식이라 register\('/sw\.js'\) 처럼 이스케이프된 형태로 들어있다
#    (landing.html 원본의 있는 그대로 문자열과는 다른 모양) — 그 형태로 찾는다.
chk("register\\('/sw\\.js'\\)" in sj_body,
    "★★★★ strip_jinja() 가 이제 서비스워커 등록 스크립트를 제거하는 로직을 갖는다")
chk('if "serviceWorker" in html:' in sj_body,
    "STEP legal.html(이 스크립트 자체가 없음) 처리 시 오탐하지 않도록 "
    "존재 여부를 먼저 확인한다(과잉실패 방지)")

chk("register('/sw.js')" in LANDING_SRC,
    "STEP landing.html 원본 자체엔 이 스크립트가 여전히 있다"
    "(서버가 직접 호스팅할 때는 정상 동작 — 지우는 건 정적 빌드 쪽뿐)")

chk('_mf2 = _mf.replace(\'"start_url": "/"\', \'"start_url": ".."\')' in BP_SRC,
    "★★★★ build() 가 manifest.webmanifest 의 start_url·scope 를 정적 빌드용 "
    "상대경로로 바꾸는 로직을 갖는다")
_orig_manifest = read("static/manifest.webmanifest")
chk('"start_url": "/"' in _orig_manifest and '"scope": "/"' in _orig_manifest,
    "STEP 원본 static/manifest.webmanifest 는 여전히 절대경로다"
    "(서버가 루트에서 직접 호스팅할 때는 정상 — 바뀌는 건 정적 빌드 사본뿐)")
chk('_mf2 = re.sub(r\',?\\s*"shortcuts":\\s*\\[.*?\\]\', "", _mf2, flags=re.S)' in BP_SRC,
    "★★★★ build() 가 SERVICE_URL 없을 때 manifest 의 shortcuts 를 통째로 "
    "빼는 로직도 갖는다(PWA 바로가기는 tel:/mailto: 로 못 바꾼다)")
chk('"url": "/insurer"' in _orig_manifest,
    "STEP 원본은 여전히 /insurer·/partner 절대경로다(서버 호스팅 시 정상)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — strip_jinja() 를 실제 landing.html 에 돌려본다")
# ──────────────────────────────────────────────────────────────
sys.path.insert(0, HERE)
_cwd = os.getcwd()
os.chdir(HERE)
try:
    import build_pages as BP

    out = BP.strip_jinja(LANDING_SRC, 0)
    chk("serviceWorker" not in out,
        "★★★★ landing.html 을 정적 빌드용으로 처리하면 서비스워커 등록 "
        "스크립트가 완전히 사라진다(예전엔 그대로 남아 매 방문마다 "
        "'/sw.js' 를 등록 시도했지만 늘 조용히 404였다)", out[:200])
    chk("register('/sw.js')" not in out,
        "STEP register('/sw.js') 호출 자체도 남지 않는다", out[:200])

    # legal.html 은 이 스크립트가 없으니 strip_jinja 자체가 오탐(하드에러)하면 안 된다.
    # (legal.html 은 build() 안에서 doc 치환을 먼저 거친 뒤 strip_jinja 를 타므로,
    #  여기서는 "serviceWorker" 가드 분기 자체가 안전한지만 별도로 확인한다.)
    _fake_legal_shell = "<html><body>{{ doc.title }}</body></html>"
    try:
        BP.strip_jinja(_fake_legal_shell.replace("{{ doc.title }}", "테스트"), 1)
        _guard_ok = True
    except SystemExit:
        _guard_ok = False
    chk(_guard_ok,
        "★★★ serviceWorker 언급이 아예 없는 템플릿(legal.html 류)에는 "
        "이 제거 로직이 관여하지 않아 하드에러가 안 난다(과잉실패 방지)")
finally:
    os.chdir(_cwd)

# ══════════════════════════════════════════════════════════════
print("\n[3] 실제 배포 산출물 — docs/index.html 에도 반영됐는가")
# ──────────────────────────────────────────────────────────────
_docs_index = os.path.join(HERE, "docs", "index.html")
if os.path.exists(_docs_index):
    docs_html = io.open(_docs_index, encoding="utf-8").read()
    chk("serviceWorker" not in docs_html,
        "★★★★ 실제 생성된 docs/index.html 에도 서비스워커 등록 스크립트가 "
        "없다(python build_pages.py 로 재생성된 최신 산출물)", docs_html[:200])
else:
    chk(False, "STEP docs/index.html 이 존재한다(빌드 산출물 확인 전제)",
        "python build_pages.py 를 먼저 실행해야 합니다")

_docs_manifest = os.path.join(HERE, "docs", "static", "manifest.webmanifest")
if os.path.exists(_docs_manifest):
    mf_out = io.open(_docs_manifest, encoding="utf-8").read()
    chk('"start_url": ".."' in mf_out and '"scope": ".."' in mf_out,
        "★★★★ 실제 생성된 docs/static/manifest.webmanifest 의 start_url·scope 가 "
        "상대경로로 바뀌어 있다(예전엔 '/' 라 서브경로 배포 시 계정 루트로 잘못 잡혔다)",
        mf_out[:200])
    chk('"src": "/static/' not in mf_out and '"src": "icons/' in mf_out,
        "★★★★ 아이콘 경로도 절대경로가 아니라 manifest 자신 기준 상대경로다"
        "(예전엔 계정 루트 기준이라 서브경로 배포에서 아이콘이 깨졌다)",
        mf_out[:400])
    chk('"shortcuts"' not in mf_out,
        "★★★★ SERVICE_URL 없는 현재 설정에서는 shortcuts 자체가 빠져 있다"
        "(가리킬 곳 없는 바로가기를 만들지 않는다)", mf_out[:400])
    try:
        json.loads(mf_out)
        _mf_valid_json = True
    except ValueError as e:
        _mf_valid_json = False
        _json_err = str(e)
    chk(_mf_valid_json,
        "★★★ shortcuts 를 정규식으로 통째로 제거해도 남은 JSON 이 문법적으로 "
        "유효하다(쉼표가 잘못 남지 않았다)",
        "" if _mf_valid_json else _json_err)
else:
    chk(False, "STEP docs/static/manifest.webmanifest 이 존재한다(빌드 산출물 확인 전제)",
        "python build_pages.py 를 먼저 실행해야 합니다")

# ══════════════════════════════════════════════════════════════
print("\n[4] 실행 — SERVICE_URL 을 지정하면 shortcuts 가 절대주소로 바뀌는가")
# ──────────────────────────────────────────────────────────────
#  ⚠ docs/ 는 실제 공개되는 GitHub Pages 산출물이다 — 예전엔 이 블록이
#    가짜 예시 도메인으로 **실제 docs/ 를 직접** 재빌드한 뒤 마지막 줄에서
#    SERVICE_URL 없이 한 번 더 재빌드해 원상복구했다. 그 두 빌드 사이에
#    예외 안전장치가 없어서, 이 블록이 도중에 죽으면(타임아웃·Ctrl+C 등)
#    실제 docs/ 가 가짜 도메인을 낀 채로 남을 수 있었다. [2]에서 이미
#    쓴 라운드108과 같은 방식대로 BP.OUT 을 임시 디렉터리로 돌려, 애초에
#    실제 docs/ 를 손대지 않는다 — 그러면 원상복구 단계 자체가 필요 없다.
_tmpdir4 = tempfile.mkdtemp(prefix="round230_svc_")
_real_out, _real_url = BP.OUT, BP.SERVICE_URL
try:
    BP.OUT = os.path.join(_tmpdir4, "docs_svc")
    BP.SERVICE_URL = "https://bokguon.example.com"
    BP.build()
    mf_svc = io.open(os.path.join(BP.OUT, "static", "manifest.webmanifest"),
                      encoding="utf-8").read()
    try:
        svc_data = json.loads(mf_svc)
        chk(svc_data.get("shortcuts") == [
                {"name": "보험사 포털", "short_name": "보험사",
                 "url": "https://bokguon.example.com/insurer"},
                {"name": "협력사 포털", "short_name": "협력사",
                 "url": "https://bokguon.example.com/partner"}],
            "★★★★ SERVICE_URL 을 지정하면 shortcuts.url 이 그 실서비스 주소로 "
            "바뀐다(본문 링크 fix_links() 와 같은 규칙)", svc_data.get("shortcuts"))
    except ValueError as e:
        chk(False, "STEP SERVICE_URL 빌드 산출물도 유효한 JSON이다", str(e))
except Exception as e:                                              # noqa: BLE001
    chk(False, "STEP SERVICE_URL 지정 빌드 자체는 정상 종료한다", f"{type(e).__name__} {e}")
finally:
    BP.OUT, BP.SERVICE_URL = _real_out, _real_url
    shutil.rmtree(_tmpdir4, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
