# -*- coding: utf-8 -*-
"""스캔 641라운드 회귀(직접조사, 하위위임 없음) — landing.html "협력사 포털"
카드 설명문이 실제 렌더에서 "· 정산" 두 글자만 마지막 줄에 홀로 남는
고아문자(orphan) 결함. static/style.css 의 body{text-wrap:pretty} 가
전역으로 상속되는데도 이 특정 문구에서는 못 채웠다.

  조사 각도 — round640 이 다음 후보로 남긴 것 중 "check_orphan_chars.py 가
  낸 41개 조판 고아문자 후보는 소스 정규식뿐이라 실제 렌더 측정(브라우저)이
  안 됐다"를 따라갔다. 41개 후보를 공개 페이지(landing.html·apply_partner.html)
  기준으로 실제 Chromium 렌더에 띄워, 이 저장소 자신의 측정 도구
  (orphan_probe.js, window.__scan/__compare — 문단을 줄 단위로 재구성해
  '규칙을 끈 상태'와 '켠 상태'를 비교해 진짜 고아문자만 골라낸다)로 비교했다.

  실측(모바일 375px·데스크톱 폭 둘 다, 실제 8771 운영 서버를 브라우저로 직접
  로드) — "입찰 공고 · 원터치 입찰 · 시공 사진 보고 · 정산" 이 두 폭 모두에서
  text-wrap:pretty 가 켜진 채로도 마지막 줄에 "· 정산"만 남았다(마지막 줄
  너비 ≈ 글자 2.2개분). 옆 카드("사건 등록 · 입찰 현황 · 낙찰 승인 · 절감
  리포트")는 우연히 pretty 만으로 충분했을 뿐 — 같은 처방이 필요 없던 게
  아니라 이 문구만 pretty 의 휴리스틱이 못 채운 경우였다(직접 스크린샷으로
  대조 확인).

  왜 check_orphan_chars.py(정적 스캔)는 이 자리를 41개 후보에 못 넣었나 —
  그 도구의 orphan_candidates() 는 `len(words[-1]) == 1`(마지막 어절이
  정확히 1글자)만 후보로 본다. 그런데 이 문구의 마지막 어절 "정산"은
  2글자다 — 1글자 기준으로는 못 걸렀지만 실제로는 고아문자였다. 이 자체를
  "체크 도구의 사각지대"로 보고 기준을 <=2 로 넓히는 것은 **하지 않는다** —
  round124 가 이미 겪은 "자주 우는 늑대"(오탐 폭주) 문제가 그대로 재발한다
  (한글 명사 대다수가 2글자라 후보가 폭증하고, 대부분은 이번처럼 실제
  문제가 아니다 — 옆 카드가 그 증거). 정적 스캔의 1글자 기준은 저지레벨을
  낮게 유지하려는 **의도된 설계**로 보고 그대로 둔다 — 이번 조치는 실제로
  드러난 이 자리 하나를 고치는 것으로 한정한다.

  고침(templates/landing.html, .portal-card 의 유일한 정의 자리) — 이 클래스가
  쓰이는 곳은 landing.html 하나뿐이라(전수 확인: templates/*.html·static/*.css·
  static/*.js grep) 그 안의 임베디드 <style> 블록만 고치면 된다. 기존
  `.portal-card p{color:#5A7089;font-size:.9rem;line-height:1.6}` 규칙에
  `text-wrap:balance` 를 추가했다 — 이 저장소가 짧은 라벨류(h1~h4·.pt·.k·
  .lbl·.tag·.pill·label, static/style.css 32행)와 표 셀(40행)에 이미 쓰는
  것과 같은 처방(균형분배가 pretty 의 단순휴리스틱보다 안정적으로 마지막
  줄을 채운다). .portal-card p 는 클래스+타입 선택자(특이도 0,1,1)라 body
  (0,0,1)보다 항상 우선한다 — 소스 순서와 무관하게 확정적으로 적용된다.

  실기동 확인 — 실제 8771 서버를 재기동한 뒤(정적 파일 변경이므로 재기동
  필요) 브라우저로 다시 로드해 __scan() 이 이 문구를 더 이상 고아문자로
  보지 않음과, 두 줄로 "입찰 공고 · 원터치 입찰 / · 시공 사진 보고 · 정산"
  처럼 고르게 나뉨을 스크린샷으로 확인했다(이 파일은 그 실측을 코드로
  재현하진 않는다 — 실제 텍스트 레이아웃 엔진은 폰트 메트릭이 필요해
  파이썬 표준 라이브러리만으로 재현할 수 없다).

  회귀테스트(이 파일) — 실제 텍스트 레이아웃(줄바꿈 위치)은 브라우저 엔진의
  몫이라 파이썬만으로 재현하지 않는다. 대신 이 저장소가 실제로 신뢰할 수
  있는 것 — "CSS 규칙이 올바른 선택자에 정확히 걸려 있는가"를 **진짜 CSS
  블록 구조**로 확인한다(문자열이 파일 어딘가에 있는지가 아니라, 선택자
  목록을 콤마로 나누고 중괄호 블록을 실제로 파싱해 선언을 선택자별로
  귀속시킨다). [1] 실제 Flask 앱으로 landing.html 을 렌더(test_template_js.py
  와 같은 기법)해 진짜 서비스 결과물에서 임베디드 <style> 을 추출.
  [2] 그 안에서 `.portal-card p` 선택자의 선언 목록을 진짜로 파싱해
  text-wrap:balance 를 확인(다른 선택자 `.portal-card h4` 에는 안 묻어있음도
  대조 확인 — 파싱이 선택자별로 제대로 격리됨을 증명). [3] 되돌림-증명 —
  이 규칙의 `;text-wrap:balance` 부분만 인메모리로 제거한 옛 버전 문자열을
  만들어(실제 파일은 안 건드림) 같은 파서에 통과시키면 text-wrap 이 사라짐을
  확인 — 이 검사 자체가 실제로 있음/없음을 가릴 수 있다는 것을 증명한다
  (round640 지적대로 "파일에 그 글자가 있는지"만 보는 검사가 아니다).
  [4] 렌더된 실제 HTML에서 "협력사 포털" 카드 문구가 지금도 정확히 그
  문제의 모양(마지막 어절 2글자)임을 확인 — 문구가 나중에 바뀌어도 이
  회귀가 계속 같은 자리를 지키고 있는지 드러나게 한다. [5] check_orphan_chars.py
  를 서브프로세스로 실행해 조판 후보가 여전히 41건(이번 고침으로 소스
  후보 개수가 흔들리지 않음 — CSS 선언 추가는 `>텍스트<` 패턴과 무관)임을
  재확인.

    python test_scan_round641_fixes.py
"""
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


print("=" * 66)
print("  스캔 641라운드 회귀 — landing.html 협력사 포털 카드 고아문자")
print("=" * 66)

# ══════════════════════════════════════════════════════════════
print("\n[1] 실행 준비 — 스크래치 DB + 실제 app.py import")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round641_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "verify.log")
os.environ.setdefault("BOKGUON_ENV", "dev")
os.environ.setdefault("BOKGUON_SEED_DEMO", "0")
sys.path.insert(0, HERE)

import db as DB                 # noqa: E402
DB.init_db()
import app as A                 # noqa: E402
from flask import render_template  # noqa: E402

with A.app.test_request_context("/"):
    HTML = render_template("landing.html", nonce="testnonce", build="t", ver="t")
chk(bool(HTML) and "portal-card" in HTML, "① landing.html 이 실제로 렌더되고 portal-card 를 담고 있다")

STYLES = re.findall(r"<style[^>]*>(.*?)</style>", HTML, re.S)
CSS = next((s for s in STYLES if ".portal-card" in s), "")
chk(bool(CSS), "② 렌더된 페이지의 임베디드 <style> 중 .portal-card 규칙을 담은 블록을 찾았다")


# ══════════════════════════════════════════════════════════════
print("\n[2] 진짜 CSS 블록 파서 — 선택자별로 선언을 귀속시킨다")
# ──────────────────────────────────────────────────────────────
def parse_css_rules(css_text):
    """[(선택자 목록, {속성: 값}), ...] — 콤마로 나뉜 선택자와 중괄호 블록을
    실제로 구조적으로 분리한다(파일 어딘가에 문자열이 있는지가 아니라).
    이 페이지의 embedded <style> 은 최상위 규칙 나열이 대부분이고, 유일한
    중첩(@media(...){...}) 은 .portal-card 와 무관해 안전하게 무시된다
    (ponytail: 이 파일에 필요한 범위만 — 일반 CSS 파서는 과한 엔지니어링)."""
    css_text = re.sub(r"/\*.*?\*/", "", css_text, flags=re.S)
    rules = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css_text):
        selectors = [s.strip() for s in m.group(1).split(",") if s.strip()]
        decls = {}
        for part in m.group(2).split(";"):
            part = part.strip()
            if not part or ":" not in part:
                continue
            k, v = part.split(":", 1)
            decls[k.strip()] = v.strip()
        rules.append((selectors, decls))
    return rules


def declarations_for(css_text, selector):
    """selector 를 선택자 목록에 정확히 포함하는 **마지막** 최상위 규칙의
    선언 dict. 없으면 None(소스 순서상 나중 규칙이 이기는 일반 CSS 동작과
    같게 마지막 매치를 쓴다)."""
    result = None
    for selectors, decls in parse_css_rules(css_text):
        if selector in selectors:
            result = decls
    return result


FIXED_DECLS = declarations_for(CSS, ".portal-card p")
chk(FIXED_DECLS is not None, "③ .portal-card p 규칙이 실제로 파싱됐다")
chk(bool(FIXED_DECLS) and FIXED_DECLS.get("text-wrap") == "balance",
    "④ .portal-card p 에 text-wrap:balance 가 걸려 있다(고아문자 방지)",
    f"실제 선언: {FIXED_DECLS}")

# 대조군 — 파싱이 선택자별로 제대로 격리되는지(옆 규칙에 안 새는지)
H4_DECLS = declarations_for(CSS, ".portal-card h4")
chk(bool(H4_DECLS) and "text-wrap" not in H4_DECLS,
    "⑤ 대조군 — .portal-card h4 에는 text-wrap 이 없다(파싱이 선택자별로 격리됨)",
    f"실제 선언: {H4_DECLS}")


# ══════════════════════════════════════════════════════════════
print("\n[3] 되돌림-증명 — 이 검사가 '있음/없음'을 실제로 가릴 수 있는가")
# ──────────────────────────────────────────────────────────────
#  ⚠ 실제 파일(templates/landing.html)은 절대 건드리지 않는다 — 렌더된 CSS
#    문자열 안에서만 옛 버전을 인메모리로 재구성한다.
NEW_RULE = ".portal-card p{color:#5A7089;font-size:.9rem;line-height:1.6;text-wrap:balance}"
OLD_RULE = ".portal-card p{color:#5A7089;font-size:.9rem;line-height:1.6}"
chk(NEW_RULE in CSS, "⑥ 지금 렌더된 CSS에 고친 규칙 원문이 정확히 있다(치환 앵커 확인)")

REVERTED_CSS = CSS.replace(NEW_RULE, OLD_RULE, 1)
chk(REVERTED_CSS != CSS and OLD_RULE in REVERTED_CSS,
    "⑦ 되돌린 사본이 실제로 옛(고아문자 방지 없는) 규칙을 담고 있다")

OLD_DECLS = declarations_for(REVERTED_CSS, ".portal-card p")
chk(bool(OLD_DECLS) and "text-wrap" not in OLD_DECLS,
    "⑧ 되돌린 옛 버전은 이 검사에서 text-wrap 이 없는 것으로(=결함 있음) 정확히 잡힌다",
    f"실제 선언: {OLD_DECLS}")
#  같은 색상 등 다른 선언은 되돌려도 그대로 — 진짜로 이 한 속성만 가려낸다는 뜻
chk(OLD_DECLS.get("color") == FIXED_DECLS.get("color") == "#5A7089",
    "⑨ text-wrap 말고 다른 선언(color)은 되돌리기 전후 동일 — 이 검사가 딱 그 속성만 본다")


# ══════════════════════════════════════════════════════════════
print("\n[4] 실제 렌더 결과에 문제의 문구가 지금도 그 모양인가")
# ──────────────────────────────────────────────────────────────
CARDS = re.findall(r'<a class="portal-card"[^>]*>(.*?)</a>', HTML, re.S)
chk(len(CARDS) == 2, "⑩ 포털 카드가 정확히 2개 렌더된다(보험사·협력사)", f"실제 {len(CARDS)}개")

CARD_PARAS = []
for c in CARDS:
    m = re.search(r"<p>([^<]*)</p>", c)
    if m:
        CARD_PARAS.append(m.group(1).strip())
chk(len(CARD_PARAS) == 2, "⑪ 카드 두 곳 모두 설명 문단을 담고 있다", f"실제 {CARD_PARAS}")

TARGET_TEXT = "입찰 공고 · 원터치 입찰 · 시공 사진 보고 · 정산"
chk(TARGET_TEXT in CARD_PARAS,
    "⑫ 문제의 문구가 실제 렌더 결과에 정확히 있다(협력사 포털 카드)",
    f"실제: {CARD_PARAS}")
last_word = TARGET_TEXT.split()[-1]
chk(last_word == "정산" and len(last_word) == 2,
    "⑬ 마지막 어절이 2글자다 — check_orphan_chars.py 의 1글자 기준(round124 의도된 "
    "설계)이 왜 이 자리를 41개 후보에 못 넣었는지 실제 텍스트로 재확인")


# ══════════════════════════════════════════════════════════════
print("\n[5] check_orphan_chars.py 재실행 — 이번 고침이 후보 개수를 흔들지 않는다")
# ──────────────────────────────────────────────────────────────
env = dict(os.environ)
env["PYTHONIOENCODING"] = "utf-8"
r = subprocess.run([sys.executable, "-u", os.path.join(HERE, "check_orphan_chars.py")],
                    cwd=HERE, capture_output=True, text=True, encoding="utf-8", env=env)
out = r.stdout or ""
m = re.search(r"조판 후보 (\d+)건", out)
n_candidates = int(m.group(1)) if m else -1
#  ⚠⚠ [라운드654] 이 기대값은 41 이었으나, round654가 check_orphan_chars.py
#    [2]절의 결함 2건(외부링크 '↗' 오탐 미제외 + 8건 초과 시 요약 수치가
#    화면표시 상한에 종속되는 오계수)을 고치면서 **진짜** 전체 후보 수가
#    41이 아니라 46이었음이 드러났다(41은 그 오계수 결함 때문에 이미
#    틀린 값이었다 — round654 자신의 회귀 test_scan_round654_fixes.py [4]절
#    참고). 이 assertion 이 실제로 검증하려는 것은 "이 라운드(641)의 CSS
#    선언 추가가 candidate 탐지 결과를 흔들지 않는다"이지 41이라는 숫자
#    자체의 정당성이 아니었으므로, 검증 의도는 그대로 두고 기준값만 그때
#    이후 다른 라운드가 고친 정확한 값(46)으로 갱신한다.
chk(n_candidates == 46,
    "⑭ check_orphan_chars.py 의 조판 후보 수가 이번 CSS 선언 추가로 안 바뀌었다"
    "(round654가 정정한 기준 46건 유지)",
    f"실제 {n_candidates}건 (출력 꼬리: {out[-200:]!r})")


print("\n" + "=" * 66)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}  {dt}")
print("=" * 66)
sys.exit(1 if FAIL else 0)
