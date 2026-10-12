# -*- coding: utf-8 -*-
"""죽은 버튼 찾기 — data-act 이름과 ACT 등록 이름을 대조한다.

  왜 필요한가 —
   이 프로젝트의 버튼은 전부 `data-act="이름"` 으로 걸리고, 그 이름을
   `window.ACT` 레지스트리에서 찾아 부른다. 이름이 한 글자만 달라도
   **버튼은 멀쩡히 보이는데 눌러도 아무 일이 없다.** 오류도 안 난다.

   실제로 `data-act-input="fmtMoney"` 가 4곳에 있었는데 등록된 이름은
   `moneyInput` 이었다. 가견적 점검 기준·표준단가 입력칸에서 천 단위 콤마가
   한 번도 찍히지 않았고, 그 값들이 「이상 저가 경보」의 기준선이었다.

  ⚠ 반대 방향(등록만 하고 안 쓰는 이름)은 잡지 않는다 — 코드에서 직접
     ACT.x() 로 부르는 경우가 있어 오탐이 된다.
"""
import glob
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

#  화면 하나 = 액션이 정의된 파일들 + 그 액션을 쓰는 마크업 파일들
SCREENS = {
    "어드민 콘솔": {
        #  ⚠ 템플릿 안 인라인 스크립트에도 ACT 등록이 있다(ACT.logout 등).
        #     defines 에서 빼면 멀쩡한 버튼을 죽었다고 오탐한다.
        "defines": ["static/admin.js", "static/actions.js", "templates/admin.html"],
        "uses": ["static/admin.js", "templates/admin.html"],
    },
    "보험사 포털": {
        "defines": ["templates/insurer_portal.html", "static/actions.js"],
        "uses": ["templates/insurer_portal.html"],
    },
    "협력사 포털": {
        "defines": ["templates/partner_portal.html", "static/actions.js"],
        "uses": ["templates/partner_portal.html"],
    },
}

USE_RE = re.compile(r'data-act(?:-change|-input)?="([A-Za-z0-9_]+)"')
#  ACT.name = ...   /   ACT['name'] = ...   /   ACT.name ??= ...
DEF_RE = re.compile(r"""ACT\s*(?:\.\s*([A-Za-z0-9_]+)|\[\s*['"]([A-Za-z0-9_]+)['"]\s*\])\s*=""")


def read(rel):
    p = os.path.join(HERE, rel)
    if not os.path.exists(p):
        return ""
    return io.open(p, encoding="utf-8").read()


ok = fail = 0


def chk(cond, name, got=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [OK]   {name}")
    else:
        fail += 1
        print(f"  [FAIL] {name}   {got}")


print("죽은 버튼 검사 — data-act ↔ ACT 등록")
for screen, cfg in SCREENS.items():
    defined = set()
    for rel in cfg["defines"]:
        for m in DEF_RE.finditer(read(rel)):
            defined.add(m.group(1) or m.group(2))
    used = set()
    src_all = ""
    for rel in cfg["uses"]:
        txt = read(rel)
        used.update(USE_RE.findall(txt))
        src_all += txt
    #  data-act 를 **셀렉터로만** 쓰고 리스너는 직접 다는 곳이 있다
    #  (예: wrap.querySelector('[data-act="pSaveProfile"]').addEventListener('click', pSaveProfile)).
    #  그건 죽은 버튼이 아니다 — 예외로 인정한다.
    direct = set(re.findall(r"addEventListener\(\s*['\"]\w+['\"]\s*,\s*([A-Za-z0-9_]+)", src_all))
    defined |= direct

    chk(bool(used), f"{screen} — data-act 를 찾았다", f"{len(used)}개")
    missing = sorted(used - defined)
    chk(not missing, f"★ {screen} — 눌러도 아무 일 없는 버튼이 없다",
        f"미등록 {len(missing)}개: {', '.join(missing)}")
    print(f"         (액션 {len(used)}개 사용 · {len(defined)}개 등록)")

print("\n[+] 메뉴 항목이 전부 한글 제목을 안다")
#  ⚠ TITLES 에 없으면 머리글에 **뷰 이름이 영어 그대로** 뜬다('today 콘솔').
#    화면을 새로 만들 때마다 잊혀서 한때 4개가 빠져 있었고, 그중엔
#    부팅 첫 화면인 '오늘 할 일' 도 있었다. 소스 옆 주석이 이미 같은 사고를
#    적어 두고 있었는데도 또 반복됐다 — 그래서 사람이 아니라 검사로 막는다.
_js = io.open(os.path.join(HERE, "static", "admin.js"), encoding="utf-8").read()
_ht = io.open(os.path.join(HERE, "templates", "admin.html"), encoding="utf-8").read()
_menu = set(re.findall(r'data-v="([A-Za-z_]\w*)"', _ht))
_blk = _js[_js.find("const TITLES = {"):]
_blk = _blk[:_blk.find("};")]
_titles = set(re.findall(r"([A-Za-z_]\w*)\s*:\s*\[", _blk))
_views = set(re.findall(r"VIEWS\.([A-Za-z_]\w*)\s*=", _js))
chk(len(_menu) >= 20 and len(_titles) >= 20,
    f"메뉴 {len(_menu)}개 · 제목 {len(_titles)}개를 읽었다",
    "0개면 정규식이 서식과 어긋난 것이다 — 아무것도 검사하지 않는다")
chk(not (_menu - _titles), "★★ 모든 메뉴 항목에 한글 제목이 있다", sorted(_menu - _titles))
chk(not (_menu - _views), "★★ 모든 메뉴 항목에 화면이 있다", sorted(_menu - _views))

print("\n[+] 인라인 이벤트 핸들러가 없다 (data-act 짝과 무관하게 CSP가 무조건 차단)")
#  ⚠ [라운드569] 위 data-act↔ACT 대조는 data-act 자체가 없는 버튼은 원천적으로
#    못 본다 — onclick="..." 같은 인라인 핸들러로 남으면 '미등록'으로도 안 잡힌다.
#    이 앱의 CSP(app.py _security_headers, script-src 'self' 'nonce-…')는
#    unsafe-inline/unsafe-hashes 가 전혀 없어 인라인 on*= 핸들러는 전부 조용히
#    죽는다(round319가 서버 렌더 템플릿 3곳에서, round569가 admin.js가 직접
#    그리는 모달 1곳에서 각각 실측).
#  ⚠⚠ [라운드571] round569 는 "재발을 이 검사 하나로 앞으로도 막는다"고 적었지만
#    실제 스캔 대상은 SCREENS(3화면 · 5개 파일)뿐이었다 — templates/*.html 20개
#    중 15개(round319가 원래 고쳤던 offline.html·case_history.html·
#    insurer_api_guide.html 세 곳도 포함— 그 셋은 test_scan_round319_fixes.py가
#    <button onclick= 하나만 별도로 볼 뿐이다)와 static/*.js 6개가 이 검사의
#    사각지대로 남아 있었다(실측 — 지금 이 파일들에 인라인 핸들러는 0건이라
#    당장 살아있는 버그는 아니다. 그러나 _security_headers는 @app.after_request라
#    예외 없이 모든 응답에 같은 CSP를 붙이므로, 이 20개 파일 중 어디에 다음번
#    인라인 핸들러가 추가돼도 이 상시검사도 test_scan_round319_fixes.py도 못
#    잡는다). 위 data-act↔ACT 대조는 SCREENS의 defines/uses 짝이 구조적으로
#    필요하지만, 인라인 핸들러 검사는 '화면'이라는 개념이 필요 없다 — CSP는
#    파일 종류(템플릿·정적 JS)만 본다. templates/*.html·static/*.js 전체로
#    넓힌다(글롭 — 새 템플릿·JS 파일이 추가돼도 이 목록에 손댈 필요가 없다).
#    static/leaflet/ 같은 하위 폴더의 외부 라이브러리는 글롭이 원래 비재귀라
#    자연히 빠진다(우리가 안 쓴 벤더 코드까지 검사할 이유가 없다).
INLINE_HANDLER_RE = re.compile(r'<[a-zA-Z][a-zA-Z0-9]*(?:[^<>]*?)\son[a-z]+=["\']')
_inline_files = sorted(
    os.path.relpath(p, HERE).replace(os.sep, "/")
    for pat in ("templates/*.html", "static/*.js")
    for p in glob.glob(os.path.join(HERE, pat)))
for rel in _inline_files:
    bad = INLINE_HANDLER_RE.findall(read(rel))
    chk(not bad, f"★ {rel} — 인라인 on*= 이벤트 핸들러가 없다", f"{len(bad)}개: {bad[:3]}")

print(f"\n  통과 {ok} · 실패 {fail}")
sys.exit(1 if fail else 0)
