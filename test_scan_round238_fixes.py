# -*- coding: utf-8 -*-
"""스캔 238라운드 회귀 — deploy/개인정보_내부관리계획.md 제4조(취급자의 역할 및
   책임)가 실제 코드의 관리자 등급과 어긋나 있던 결함(Agent 병렬조사로 발견).

  문서는 "최고관리자·운영관리자" 2단계만 적었는데, 실제 코드(app.py ADMIN_ROLES)는
  "최고관리자·중간관리자·하위관리자" 3단계다. '운영관리자'는 3등급 체계로 통일
  하기 전의 옛 등급명(db.py 마이그레이션이 부팅마다 '중간관리자'로 자동 치환하는
  바로 그 이름)이라 실제로는 어떤 계정에도 존재하지 않는다 — 개인정보 고시가
  요구하는 "취급자의 범위와 역할·책임"을 실제와 다르게 적어 두면, 이 문서로
  권한 등급을 감사하려는 사람이 존재하지 않는 등급을 찾고 실제 3번째 등급
  (하위관리자, 수십 개 라우트를 실제로 게이팅함)은 놓친다.

  이 테스트는 문서의 역할표가 app.py 의 ADMIN_ROLES 와 항상 일치하도록 묶어
  둔다 — 등급 체계가 나중에 또 바뀌면(추가·개명) 이 테스트가 먼저 잡는다.

      python test_scan_round238_fixes.py
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


APP_SRC = read("app.py")
DOC = read("deploy/개인정보_내부관리계획.md")

print("=" * 72)
print("  스캔 238라운드 회귀 — 개인정보 내부관리계획의 관리자 등급 불일치")
print("=" * 72)

# ============================================================
print("\n[1] 실제 등급 추출 — app.py")
# ------------------------------------------------------------
m = re.search(r'ADMIN_ROLES\s*=\s*\[(.*?)\]', APP_SRC)
chk(bool(m), "★★★ app.py 에서 ADMIN_ROLES 정의를 찾는다")
roles = re.findall(r'"([^"]+)"', m.group(1)) if m else []
chk(roles == ["최고관리자", "중간관리자", "하위관리자"],
    "STEP 현재 3등급 체계(최고·중간·하위)를 그대로 읽어낸다", roles)

# ============================================================
print("\n[2] 문서 대조 — deploy/개인정보_내부관리계획.md 제4조")
# ------------------------------------------------------------
i4 = DOC.index("제4조")
i5 = DOC.index("제5조")
sec4 = DOC[i4:i5]
for r in roles:
    chk(r in sec4, f"★★★★ 제4조 역할표에 실제 등급 '{r}' 이 있다")
chk("운영관리자" not in DOC,
    "★★★★ 폐지된 옛 등급명 '운영관리자'가 문서 어디에도 남아있지 않다"
    "(db.py 마이그레이션이 부팅마다 '중간관리자'로 자동 치환하는 이름 — "
    "실제로는 어떤 계정에도 존재하지 않는다)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
