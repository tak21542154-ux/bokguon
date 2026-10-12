# -*- coding: utf-8 -*-
"""템플릿이 뿜는 **인라인 JS 가 실제로 파싱되는가**.

  왜 필요한가 —
   세 포털의 화면은 거의 전부 템플릿 안의 인라인 스크립트다. 그 안은 중첩된
   템플릿 리터럴(백틱)·삼항·`${}` 로 빽빽해서, **괄호 하나만 어긋나도
   그 화면이 통째로 뜨지 않는다.** 그런데 파이썬 문법 검사도, HTTP 테스트도
   이걸 못 잡는다 — 서버는 200 을 주고 브라우저에서만 죽기 때문이다.

  ⚠ 오늘(2026-08-06) 템플릿을 열 번 넘게 고쳤는데 확인할 수단이 이것뿐이었다.
    파일을 문자열로 세는 것(괄호 개수 세기)은 못 믿는다 —
    주석·문자열 안의 괄호까지 세어 **멀쩡한 코드를 불균형이라고 말한다.**
    실제로 렌더해서 node 로 파싱해 보는 것만이 증거다.

      python test_template_js.py
"""
import io
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 66)
print("  템플릿 인라인 JS 구문 검사")
print("=" * 66)

NODE = shutil.which("node")
if not NODE:
    #  ⚠ 없다고 조용히 통과시키지 않는다 — '검사 안 함'과 '통과'는 다르다.
    print("\n  ✖ node 를 찾을 수 없습니다. 이 검사는 node --check 로 파싱합니다.")
    print("     (설치: https://nodejs.org — 검사를 건너뛰지 않고 실패로 답합니다)")
    sys.exit(2)

os.environ.setdefault("BOKGUON_ENV", "dev")
os.environ.setdefault("BOKGUON_SEED_DEMO", "0")
sys.path.insert(0, HERE)
os.chdir(HERE)

import app as A  # noqa: E402
from flask import render_template  # noqa: E402

#  화면을 그리는 템플릿 — 로그인 화면·공개 폼까지 포함한다(거기도 인라인 JS 가 있다)
TARGETS = [
    ("admin.html", "/admin"),
    ("insurer_portal.html", "/app/insurer"),
    ("partner_portal.html", "/app/partner"),
    ("landing.html", "/"),
    ("insurer_login.html", "/insurer/login"),
    ("partner_login.html", "/partner/login"),
    ("apply_partner.html", "/apply/partner"),
    ("apply_insurer.html", "/apply/insurer"),
    ("change_password.html", "/change-password"),
]

total_js = 0
ext_js = {}  # 실 파일경로 → 참조한 템플릿 이름들 (round678)
for tpl, path in TARGETS:
    if not os.path.exists(os.path.join(HERE, "templates", tpl)):
        chk(False, f"{tpl} — 파일이 없다")
        continue
    try:
        with A.app.test_request_context(path):
            html = render_template(tpl, nonce="testnonce", build="t", ver="t")
    except Exception as e:
        chk(False, f"{tpl} — 렌더 실패", f"{type(e).__name__}: {e}")
        continue

    #  ⚠⚠ [round678] admin.html 처럼 <script src="{{ asset('admin.js') }}"></script>
    #    로 "외부 참조"만 하는 자리는 본문이 비어 있어(위 인라인 정규식이 빈 문자열을
    #    걸러낸다) admin.js 자신은 이 파일이 한 번도 실제로 파싱해 본 적이 없었다
    #    (round677 발견 — admin.js·actions.js·lightbox.js·addrpick.js·leaflet.js 등
    #    전부 사각지대). 지금 렌더된 HTML 에서 src="/static/....js" 를 직접 뽑아 실제
    #    파일을 모아 둔다 — 하드코딩 목록이 아니라 그때그때 렌더 결과를 신뢰하므로
    #    템플릿이 새 JS 를 추가해도 자동으로 따라간다.
    for src in re.findall(r'<script\b[^>]*\bsrc="([^"]+)"', html):
        if src.startswith("/static/"):
            rel = src.split("?", 1)[0].lstrip("/")
            fp = os.path.join(HERE, *rel.split("/"))
            ext_js.setdefault(fp, set()).add(tpl)

    scripts = [s for s in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S) if s.strip()]
    bad = []
    for k, sc in enumerate(scripts):
        total_js += len(sc)
        p = os.path.join(HERE, f"._tplchk_{tpl}_{k}.js")
        io.open(p, "w", encoding="utf-8").write(sc)
        try:
            #  ⚠ [round678] encoding 을 안 주면(이 저장소 경로 자신에 낀 한글 "개발자3" 때문에)
            #    node 가 실제 에러에서 그 경로를 찍을 때 그 출력을 읽는 내부 리더 스레드가
            #    OS 로케일(cp949)로 잘못 디코드하다 UnicodeDecodeError 로 죽는다 — 프로세스
            #    전체는 안 죽지만(실측: 메인 스레드는 예외를 못 받는다) r.stderr 가 통째로
            #    None 이 되어 정작 필요한 실패 원인 메시지가 사라지고, 콘솔엔 무관해 보이는
            #    스레드 traceback 만 남는다(returncode 는 정상 반영되어 FAIL 자체는 잡히지만
            #    사람이 볼 상세 메시지가 빈다 — "실제로 파싱해 보는 것만이 증거다"라는 이
            #    파일의 취지가 실패 상세에서는 무력화된다). 이 배터리의 다른 서브프로세스
            #    호출들이 이미 쓰는 관례(run_all_tests.py 의 run() 등)를 그대로 맞춘다.
            r = subprocess.run([NODE, "--check", p], capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
            if r.returncode:
                #  node 는 임시 파일 경로를 찍는다 — 사람이 읽을 수 있게 줄만 남긴다
                msg = (r.stderr or "").strip().splitlines()
                msg = " / ".join(x.strip() for x in msg[:4] if x.strip())
                bad.append(f"#{k}: {msg[:220]}")
        finally:
            try:
                os.remove(p)
            except OSError:
                pass
    chk(not bad, f"★ {tpl} — 인라인 JS {len(scripts)}개 파싱", " | ".join(bad))

#  [round678] 그 외부참조 static/*.js 파일들 자신을 node --check 한다 — 이미 완결된
#  스크립트 파일이라 인라인처럼 잘라낼 필요 없이 원본을 그대로 검사한다. 같은 파일이
#  여러 템플릿에서 참조되면(예: actions.js) 한 번만 검사한다.
for fp in sorted(ext_js):
    rel = os.path.relpath(fp, HERE).replace("\\", "/")
    tpls = ", ".join(sorted(ext_js[fp]))
    if not os.path.exists(fp):
        chk(False, f"★ {rel} — src 로 참조되지만 파일이 없다", f"참조: {tpls}")
        continue
    #  ⚠ encoding 미지정 시 위와 같은 이유로 실패 메시지가 None 이 될 수 있어 여기도 맞춰 준다.
    r = subprocess.run([NODE, "--check", fp], capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    detail = ""
    if r.returncode:
        msg = (r.stderr or "").strip().splitlines()
        detail = " / ".join(x.strip() for x in msg[:4] if x.strip())
    chk(r.returncode == 0, f"★ {rel} — 외부참조 JS 파싱(src=, {tpls})", detail)

print(f"\n  검사한 인라인 JS 총 {total_js:,}자 · 외부참조 JS 파일 {len(ext_js)}개")
print("\n" + "=" * 66)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}  {dt}")
print("=" * 66)
sys.exit(1 if FAIL else 0)
