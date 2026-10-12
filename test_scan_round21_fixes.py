# -*- coding: utf-8 -*-
"""21라운드 회귀 — **교착의 입구와 출구를 함께 연다.**

  한 사건이 갇히는 데 두 개의 잠금이 겹쳐 있었다.

  ① 입구 — 발주처 포털이 '사진 없음' 을 켜면 가견적 칸을 **비우고 잠갔다.**
     바로 그 칸의 라벨은 "사진 없이 접수해 현장 확인이 먼저 필요한 건은,
     이 금액이 2차 공고에서 **최소 금액**이 됩니다" 라고 말한다 — 화면이
     스스로 모순됐다. 서버는 앞 라운드에 값을 보존하도록 고쳤는데
     화면이 막아서 그 수정이 이 경로에서는 도달 불가였다.

  ② 출구 — 2차 공고가 NO_FLOOR 로 막히면 "사건 상세에서 가견적을 입력하거나…"
     라고 안내하는데, 그 사건 상태가 '접수' 라 `가견적은 입찰중에만 고칠 수
     있습니다` 로 409 를 던졌다. '접수'→'입찰중' 으로 가려면 공고를 열어야 하고,
     공고를 열려면 가견적이 있어야 한다 — **완전한 순환**.

  둘이 겹치면 레시피 없는 3공종(방음벽·휀스·펜스 / 조경·수목 / 종합 원상복구)의
  사진없음 접수는 취소 후 재등록 외에 나갈 길이 없었다.

  실측(고친 뒤): 발주처 포털에서 조경·수목 + 사진없음 + 가견적 360만 등록 →
  est_price=3,600,000 보존. 가견적 칸 disabled=false.

      python test_scan_round21_fixes.py
"""
import ast
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
    try:
        return io.open(os.path.join(HERE, rel), encoding="utf-8").read()
    except OSError as e:
        return f"<<읽기실패 {e}>>"


def func_body(src, header):
    i = src.find(header)
    if i < 0:
        return ""
    j = len(src)
    for pat in ("\ndef ", "\n@app."):
        k = src.find(pat, i + len(header))
        if 0 < k < j:
            j = k
    return src[i:j]


def strip_py(t):
    return "\n".join(ln for ln in t.splitlines() if not ln.strip().startswith("#"))


def strip_js(t):
    t = re.sub(r"(?<![A-Za-z0-9_\"'])/\*.*?\*/", " ", t, flags=re.S)
    return "\n".join(ln for ln in t.splitlines() if not ln.strip().startswith("//"))


APP, ADM = read("app.py"), read("static/admin.js")
INS = read("templates/insurer_portal.html")

print("═" * 70)
print("  21라운드 회귀 — 교착의 입구·출구")
print("═" * 70)

print("\n[1] 입구 — '사진 없음' 이 가견적 입력을 막지 않는다")
_tn = strip_js(INS[INS.find("ACT.toggleNoPhoto"):INS.find("ACT.toggleNoPhoto") + 900])
chk("est.disabled = false" in _tn,
    "★ 가견적 칸을 잠그지 않는다",
    "잠그면 발주처로 들어온 사진없음 접수는 100% est_price=0 이 되고, 레시피 없는 "
    "3공종과 겹치면 2차 하한을 만들 근거가 둘 다 없어 공고가 영구히 막힌다")
chk("est.value = ''" not in _tn,
    "★ 이미 적은 값을 지우지 않는다")
chk("최소 금액" in INS,
    "그 칸의 라벨은 여전히 '2차 공고의 최소 금액' 이라고 말한다(이제 모순이 없다)")

print("\n[2] 출구 — '접수' 에서도 가견적을 고칠 수 있다")
_ed = strip_py(func_body(APP, "def api_case_edit"))
chk('c["status"] not in ("입찰중", "접수")' in _ed,
    "★ 서버가 '접수' 를 허용한다",
    "잠그는 이유는 진행 중 경매의 규칙이 바뀌면 응찰 업체 유·불리가 갈리기 "
    "때문인데, '접수' 는 공고가 열리지도 않아 열린 경매도 입찰도 없다")
chk("c.status==='접수'" in ADM,
    "★ 화면도 '접수' 에서 칸을 연다",
    "서버만 열면 화면이 disabled 로 막아 값을 아예 안 보낸다")
_oa = strip_py(func_body(APP, "def api_case_open_auction"))
chk("NO_FLOOR" in _oa and "사건 상세에서 가견적을 입력" in _oa,
    "NO_FLOOR 안내가 가리키는 조치가 이제 실제로 가능하다")

print("\n[3] 경고가 **두 접수 화면 모두**에 있다")
chk("def _need_est_majors" in APP and APP.count("def _need_est_majors") == 1,
    "★ 판정이 한 곳에서 나온다",
    "관리자 콘솔과 발주처 포털이 각자 규칙을 쓰면 두 화면이 서로 다른 경고를 한다")
chk('"need_est_majors": _need_est_majors()' in APP,
    "★ 발주처 대시보드가 그 목록을 함께 받는다",
    "/api/work-coverage 는 관리자 전용이라 발주처 포털이 못 부른다 — 권한을 넓히는 "
    "대신 이미 부르는 응답에 실어 보낸다")
chk("ACT.catCoverageIns" in INS and "need_est_majors" in INS,
    "★ 발주처 포털이 고른 공종에 대해 경고한다",
    "첫 주에 사건을 등록하는 주체가 발주처인데 경고가 어드민에만 있으면 "
    "정작 필요한 사람이 못 본다")
_cv = strip_py(func_body(APP, "def api_work_coverage"))
chk("_need_est_majors()" in _cv,
    "★ 관리자용 API 도 같은 판정을 쓴다(규칙 복제 없음)")

print("\n[4] 금액을 만들어 주지는 않는다 (철칙 3)")
_ne = strip_py(func_body(APP, "def _need_est_majors"))
for _bad in ("price", "amount", "estimate("):
    chk(_bad not in _ne, f"판정 함수가 금액을 만들지 않는다 — '{_bad}' 없음")

print("")
for f in ("app.py",):
    try:
        ast.parse(read(f)); ok_, why = True, ""
    except SyntaxError as e:
        ok_, why = False, f"{e.lineno}행: {e.msg}"
    chk(ok_, f"{f} 구문", why)

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
