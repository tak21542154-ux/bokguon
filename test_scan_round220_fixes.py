# -*- coding: utf-8 -*-
"""스캔 220라운드 회귀 — static/admin.css 가 static/style.css 의 우측 하단
   알림 트레이(.tray) 정의를 통째로 다시 선언해, admin.html 에서는(둘 다
   로드하는데 admin.css 가 나중이라 같은 명시도에서 항상 이김) style.css
   쪽 값이 아니라 admin.css 쪽 값이 적용되던 결함. 특히 style.css 가 PWA
   standalone 대응으로 나중에 추가한 안전영역 보정
   (bottom:calc(10px + env(safe-area-inset-bottom)))이 admin 콘솔에서만
   조용히 완전히 가려졌다 — 실측: 실제 브라우저(admin.html 과 동일한 순서로
   두 스택시트 로드)에서 getComputedStyle 확인, right 가 16px 가 아니라
   admin.css 의 18px 로 나왔다.

   .field 같은 의도적 오버라이드는 그 이유를 적은 주석이 있는데(session
   기존 확립 원칙, partner_portal.html:79 참고) .tray 사본에는 그런 설명이
   전혀 없어 실수로 복붙된 것으로 판단, admin.css 쪽 사본을 제거했다.

      python test_scan_round220_fixes.py
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


print("═" * 72)
print("  스캔 220라운드 회귀 — admin.css 의 .tray 중복정의(style.css 와 충돌)")
print("═" * 72)

ADMIN_CSS = read("static/admin.css")
STYLE_CSS = read("static/style.css")
ADMIN_HTML = read("templates/admin.html")

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
#  CSS 선택자 형태(.tray{ 또는 .tray .tc)만 찾는다 — 이 파일에 남긴 설명
#  주석 자체가 "★★★★ .tray 를..." 처럼 산문으로 이 이름을 언급하므로,
#  단순 부분일치는 자기 주석에 걸려 오탐한다.
_admin_tray_hits = re.findall(r"\.tray\s*\{|\.tray\s+\.tc\b", ADMIN_CSS)
chk(len(_admin_tray_hits) == 0,
    "★★★★ admin.css 는 더 이상 .tray 를 재정의하지 않는다"
    "(예전엔 여기 사본이 style.css 보다 나중에 로드돼 매번 이겼다)",
    _admin_tray_hits)

chk(".bellpop{position:fixed;top:64px" in ADMIN_CSS,
    "STEP admin 전용 .bellpop 규칙은 그대로 살아있다(과잉삭제 아님)")
chk(".bell.ring,.belldot.show,.bellpop{animation:none}" in ADMIN_CSS,
    "STEP prefers-reduced-motion 규칙도 .tray .tc 만 빠지고 나머지"
    "(.bell.ring·.belldot.show·.bellpop)는 그대로 살아있다(과잉삭제 아님)")

chk(".tray{position:fixed;right:16px;bottom:16px" in STYLE_CSS,
    "★★★ style.css 쪽 기본 정의는 그대로 남아 있다(유일한 정의가 됨)")
chk(".tray{ bottom:calc(10px + env(safe-area-inset-bottom)) }" in STYLE_CSS,
    "★★★ style.css 의 PWA 안전영역 보정도 그대로 남아 있다"
    "(이제 admin.html 에도 실제로 적용된다)")

chk('href="{{ asset(\'style.css\') }}"' in ADMIN_HTML,
    "STEP admin.html 은 여전히 style.css 를 로드한다"
    "(그래서 admin.css 에서 지워도 트레이 위젯 자체는 계속 스타일을 받는다)")

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
