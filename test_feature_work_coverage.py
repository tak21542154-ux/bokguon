# -*- coding: utf-8 -*-
"""[기능] 공종 개산 근거 커버리지 경고 — 회귀.

  왜 만들었나 —
    2차 경매의 하한은 `가견적 → (없으면) 표준단가 개산 하단` 2단이다.
    개산 레시피가 없는 공종(실측 3개: 방음벽·휀스·펜스 / 조경·수목 / 종합 원상복구)은
    engine_low 가 0으로 남고, 가견적까지 0이면 2차 공고가 NO_FLOOR 로 막힌다.
    **그런데 그 시점엔 가견적 수정이 '입찰중' 전용이라 이미 잠겨 손쓸 수 없다.**
    게다가 NO_FLOOR 는 사진 게이트 뒤에 있어, 운영자는 출동→도착보고→부동의를
    다 밟은 뒤에야 막힌 걸 안다.

    그래서 **사건을 만드는 순간** 알린다. 금액을 만들어 주지 않는다(철칙 3) —
    근거 유무만 말하고, 가견적을 적어 두라고 안내한다.

      python test_feature_work_coverage.py
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

print("═" * 70)
print("  공종 개산 근거 경고 — 회귀")
print("═" * 70)

print("\n[1] 서버가 근거 유무를 알려 준다")
_b = strip_py(func_body(APP, "def api_work_coverage"))
chk('"/api/work-coverage"' in APP, "★ 커버리지 API 가 있다")
chk("standard_boq" in _b and "COALESCE(active,1)=1" in _b,
    "★ **활성** 표준단가만 근거로 센다",
    "비활성 행만 남은 공종은 실제로는 근거가 없다(철칙 3 — 근거 없는 단가를 "
    "활성으로 쓰지 않는다)")
#  ⚠ 21라운드에서 판정을 `_need_est_majors()` 한 곳으로 모았다(관리자 콘솔과
#    발주처 포털이 각자 규칙을 쓰지 않게). 불변식은 그대로이므로 **보는 위치만** 옮긴다.
_ne = strip_py(func_body(APP, "def _need_est_majors"))
chk("RECIPES" in _ne and ".values()" in _ne,
    "★ RECIPES 를 값으로 순회한다(dict 다 — 키로 돌면 조용히 터진다)")
chk("_need_est_majors()" in _b,
    "★ 커버리지 API 가 그 한 곳의 판정을 쓴다(규칙을 복제하지 않는다)")
chk('"need_est"' in _b,
    "★ **판정을 서버가 내린다**",
    "화면이 규칙(레시피 없음 → 가견적 필요)을 다시 쓰면 두 곳이 갈린다")
for money in ("price", "amount", "estimate("):
    chk(money not in _b.replace("est_price", ""),
        f"금액을 만들지 않는다 — '{money}' 없음 (철칙 3)")

print("\n[2] 등록 화면이 고르기 전에 말한다")
_S = strip_js(ADM)
chk("'/api/work-coverage'" in _S, "★ 등록 화면이 커버리지를 받아 온다")
chk("catch(e) {}" in _S or "catch(e){}" in _S,
    "받아 오지 못해도 등록을 막지 않는다(경고가 없을 뿐)")
chk("data-needest" in _S and 'data-act-change="catCoverage"' in _S,
    "★ 공종을 고칠 때마다 다시 판정한다")
chk("ACT.catCoverage" in _S and _S.count("ACT.catCoverage =") == 1,
    "★ 핸들러가 하나만 등록된다(키 중복 대입 금지)")

print("\n[3] ★★ 옵션 value 가 오염되지 않는다")
_i = ADM.find('<select id="c_cat"')
_seg = ADM[_i:_i + 500] if _i > 0 else ""
chk('<option value="${esc(m)}"' in _seg,
    "★★ option 에 value 를 명시한다",
    "value 없는 option 은 **표시 텍스트가 곧 값**이다 — 경고 문구를 붙이는 순간 "
    "서버로 가는 공종명이 '조경·수목  ⚠ 개산 근거 없음' 이 되어 도급 판정표·"
    "표준단가·통계·엑셀이 전부 어긋난다. 실제로 이 버그를 만들었다가 잡았다")

print("\n[4] 확실히 막히는 조합은 한 번 확인받는다")
def js_func(src, header):
    """중괄호 균형으로 함수 본문 전체를 뜬다 — **글자수로 자르지 않는다.**

    ⚠ 이 검사를 처음 쓸 때 `+2600` 고정 창으로 잘랐다가, 바로 이 라운드에서
      확인창 코드를 넣자 검사 대상이 창 밖으로 밀려 멀쩡한 코드가 실패로 떴다.
    """
    i = src.find(header)
    if i < 0:
        return ""
    depth, j = 0, src.find("{", i)
    if j < 0:
        return ""
    while j < len(src):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
        j += 1
    return src[i:]


_cc = strip_js(js_func(ADM, "async function createCase"))
chk("_need && body.no_photo && !body.est_price" in _cc,
    "★ 근거없음 + 사진없음 + 가견적없음 조합에서 확인창",
    "이 셋이 겹치면 2차 공고에서 하한을 만들 방법이 아예 없다. 등록을 막지는 "
    "않되(운영자가 알고 넣을 수 있다) 모르고 지나치지는 않게 한다")

print("\n[5] 막는 자리가 그대로 살아 있다(경고는 대체가 아니라 앞당김)")
_oa = strip_py(func_body(APP, "def api_case_open_auction"))
chk("NO_FLOOR" in _oa, "★ 2차 공고의 하한 가드는 그대로다")
chk(_oa.find("NO_PHOTO") < _oa.find("NO_FLOOR"),
    "사진 게이트가 하한 가드보다 먼저다(그래서 등록 시점 경고가 필요하다)")

print("\n[6] 처리방침이 실제 설정과 같은 말을 한다")
#  ⚠ 문자열 replace 는 공백 하나만 어긋나도 **조용히 아무것도 안 한다.**
#    '치환 코드가 있다'가 아니라 '문장이 실제로 빠졌다'를 본다.
sys.path.insert(0, HERE)
try:
    import legal_docs as _LEGAL
    _on, _off = _LEGAL.privacy_body(True), _LEGAL.privacy_body(False)
    _KEY = "관리자 콘솔 접속 IP 제한"
    chk(_KEY in _on and _KEY not in _off,
        "★ IP 제한 설정이 꺼져 있으면 그 문구를 빼고 표시한다",
        "처리방침은 그 조치를 '시행하고 있습니다' 라고 공개 고지하는데, "
        "BOKGUON_ADMIN_IP_ALLOW 가 비면 app.py 의 두 가드가 통째로 건너뛴다 — "
        "안 하는 일을 한다고 적은 공개 문서였다")
    chk(len(_on) - len(_off) > 10,
        "★ 실제로 글자가 줄었다(치환이 헛돌지 않았다)",
        f"차이 {len(_on) - len(_off)}자")
    for _k in ("고시 제5조·제6조", "PBKDF2-HMAC-SHA256", "AES-256-GCM",
               "권한 변경·말소 이력"):
        chk(_k in _on and _k in _off, f"다른 조항은 그대로 남는다 — {_k}")
    for _t in ("<tr>", "</tr>", "<table"):
        chk(_on.count(_t) == _off.count(_t),
            f"표 구조가 깨지지 않는다 — {_t} {_on.count(_t)}개")
except Exception as _e:
    chk(False, "처리방침 설정 연동", f"{type(_e).__name__}: {_e}")

_lp = strip_py(func_body(APP, "def legal_page"))
chk("privacy_body" in _lp and "ADMIN_IP_ALLOW" in _lp,
    "★ 렌더 경로가 실제 설정값을 넘긴다",
    "생성기만 만들고 안 쓰면 공개 페이지는 그대로다")

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
