# -*- coding: utf-8 -*-
"""[기능] 건설업 등록 전수조사 워크벤치 — 회귀.

  왜 만들었나 —
    활성 399곳 중 **398곳이 '미확인'** 이었다. 이 값은 도급 적법성 관문이
    배정 때 근거로 쓰는 데이터라(건산법 §25② — 하도급 상대는 등록 건설사업자여야
    한다) 실운영 전에 채워야 한다. 그런데 업체 상세 모달을 하나씩 열어 고쳐야 해서
    398번 열고 닫아야 했다. **아무도 안 한다.**

  이 화면이 지켜야 할 성질 —
    ① **줄어드는 게 보여야 한다.** 한 행을 처리하면 그 행이 사라지고 진행률·배지가
       즉시 준다. 398건짜리 작업에서 진척이 안 보이면 사람은 중간에 그만둔다.
    ② **하던 자리를 잃지 않는다.** 처리 후 목록 전체를 다시 그리면 스크롤이 맨 위로
       튄다 — 그것만으로 포기한다. 그래서 행만 지우고 진행률만 갱신한다.
    ③ **투찰 자격이 있는 곳부터.** 시행사·계정 보유 순으로 앞에 둔다. 전부 끝나기
       전에도 관문이 효과를 내게 하는 순서다.
    ④ **사업자번호를 그 자리에서 남긴다.** 그게 없으면 조회 자체가 어려운데
       399곳 중 1곳에만 있었다. 조사하며 알게 된 값을 못 남기면 다음 사람이 또 찾는다.
    ⑤ **'등록확인' 이면 등록번호를 요구한다.** 근거 없는 확인은 관문을 무력화한다.

      python test_feature_license_survey.py
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


def func_src(src, header):
    i = src.find(header)
    if i < 0:
        return ""
    m = re.search(r"\n(?:@app\.|def )", src[i + len(header):])
    return src[i:i + len(header) + m.start()] if m else src[i:]


def js_func(src, header):
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


APP, ADM = read("app.py"), read("static/admin.js")
AH = read("templates/admin.html")

print("═" * 70)
print("  기능 회귀 — 건설업 등록 전수조사 워크벤치")
print("═" * 70)

print("\n[1] 작업 큐가 '지금 손댈 것' 만 준다")
chk('"/api/license-survey"' in APP, "★ 작업 큐 API 가 있다")
_q = func_src(APP, "def api_license_survey")
chk('request.args.get("status") or "미확인"' in _q,
    "★★ 기본이 '미확인' 이다",
    "전수조사의 목적은 남은 것을 없애는 것이지 전체를 다시 보는 게 아니다")
chk("(partner_type='시행사') DESC" in _q and "COALESCE(login_id,'')<>'') DESC" in _q,
    "★★ **투찰 자격이 있는 곳을 앞에** 둔다",
    "실제로 일이 갈 업체부터 확인해야, 398곳을 다 끝내기 전에도 관문이 효과를 낸다")
chk("min(int(" in _q and "300" in _q, "★ limit 에 상한이 있다")
chk("except (TypeError, ValueError)" in _q, "★ limit 이 숫자가 아니어도 죽지 않는다")
chk('"progress"' in _q and '"pct"' in _q and '"todo"' in _q,
    "★ 진행률을 함께 준다(줄어드는 게 보여야 한다)")
#  ★ 진행률 판정이 전수조사 카드와 **같은 식**인지
_a = func_src(APP, "def api_license_audit")
chk("COALESCE(license_status,'미확인')" in _q and "COALESCE(license_status,'미확인')" in _a,
    "★ 진행률이 기존 카드와 같은 판정을 쓴다(두 숫자가 갈리지 않게)")
chk('"lookup"' in _q and "kiscon" in _q.lower(),
    "★ 조회처를 서버가 준다",
    "화면에 주소를 박아 두면 바뀔 때 화면을 고쳐야 한다")

print("\n[2] 조사하며 알게 된 값을 그 자리에서 남긴다")
_l = func_src(APP, "def api_partner_license")
#  ⚠⚠ [라운드607] 형제결함군(raw d.get(...)이 JSON 비문자열이면 500)을 고치며
#    _bz = (d.get("biz_no") or "").strip() 가 _bz = _s(d.get("biz_no"), 20)으로,
#    st == "등록확인" and not (d.get("license_no") or "").strip() 가 st == "등록확인"
#    and not _s(d.get("license_no"))로 바뀌었다 — "사업자번호를 받는다"·"등록확인이면
#    등록번호를 요구한다"는 이 두 검사의 본래 취지는 그대로이므로 리터럴만 갱신한다
#    (검사 취지 약화 없음).
chk('_bz = _s(d.get("biz_no"), 20)' in _l,
    "★★ 사업자번호도 받는다",
    "그게 없으면 조회 자체가 어려운데 399곳 중 1곳에만 있었다")
chk("if _bz:" in _l,
    "★★ **빈 값이 오면 덮어쓰지 않는다**",
    "이미 있는 번호를 빈 칸으로 지우면 조사를 되돌리는 셈이다")
chk("license_checked_at=datetime('now','+9 hours')" in _l and "license_checked_by=?" in _l,
    "★ 누가 언제 확인했는지 남긴다(관문 판정의 근거다)")
chk('st == "등록확인" and not _s(d.get("license_no"))' in _l,
    "★★ '등록확인' 이면 등록번호를 요구한다",
    "근거 없는 확인은 관문을 무력화한다")
chk("DB.log(" in _l, "★ 감사 로그에 남는다")

print("\n[3] 화면이 진척을 보여 준다")
chk('data-v="license"' in AH, "★ 메뉴에 있다")
chk('id="bdg-license"' in AH, "★ 남은 건수 배지 자리가 있다")
_v = js_func(ADM, "VIEWS.license = async ()")
chk("g.pct" in _v and "transition:width" in _v, "★ 진행률 막대가 있다")
chk("곳 남음" in _v, "★ 남은 곳 수를 말한다")
chk("미확인이 남지 않았습니다" in _v,
    "★ 다 끝나면 **끝났다고 말한다**(빈 표는 고장과 구별되지 않는다)")
chk("catch(e)" in _v, "★ 못 불러오면 그 사실을 말한다")
chk("건산법 §25②" in _v,
    "★ **왜 하는 일인지** 화면이 말한다(신입도 이유를 안다)")

print("\n[4] 한 줄 안에서 끝난다 — 하던 자리를 잃지 않는다")
_s = js_func(ADM, "ACT.licSet = async")
chk("row.remove()" in _s,
    "★★ 처리한 행이 **그 자리에서 사라진다**")
chk("VIEWS.license()" not in _s,
    "★★ 목록 전체를 다시 그리지 않는다",
    "다시 그리면 스크롤이 맨 위로 튀어 어디까지 했는지 잃는다 — "
    "398건짜리 작업에서는 그것만으로 사람이 포기한다")
chk("bar.style.width" in _s and "bdg-license" in _s,
    "★ 진행률과 배지는 조용히 갱신한다")
chk("st === '등록확인' && !no" in _s,
    "★★ 등록번호 없이 '등록확인' 을 못 누른다(서버 가드와 짝)")
chk("f.focus()" in _s,
    "★ 막을 때 **어디를 채워야 하는지** 커서를 옮겨 준다")
chk("catch(e)" in _s and "toast(e.message" in _s,
    "★ 저장 실패를 삼키지 않는다")
chk('input id="lb-' in ADM and 'input id="ln-' in ADM,
    "★ 사업자번호·등록번호 칸이 한 줄 안에 있다")
chk("licCopy" in ADM, "★ 업체명 복사(조회창에 붙여넣기)")
chk('href="${esc(LIC_LOOKUP)}"' in ADM and 'target="_blank"' in ADM,
    "★ 조회처를 새 탭으로 연다(하던 작업을 잃지 않는다)")
chk('rel="noopener"' in ADM, "★ 새 탭에 opener 를 넘기지 않는다(보안)")

print("\n[5] 핸들러가 한 번씩만 등록된다")
for k in ("licSet", "licFilter", "licSearch", "licCopy", "licPtype"):
    chk(ADM.count(f"ACT.{k} =") == 1, f"★ ACT.{k} 중복 대입 없음")

print("")
try:
    ast.parse(APP); _ok, _why = True, ""
except SyntaxError as e:
    _ok, _why = False, f"{e.lineno}행: {e.msg}"
chk(_ok, "app.py 구문", _why)
chk(AH.count("<div") == AH.count("</div>"),
    "admin.html div 균형", f"{AH.count('<div')} / {AH.count('</div>')}")

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
