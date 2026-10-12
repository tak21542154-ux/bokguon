# -*- coding: utf-8 -*-
"""스캔 545라운드 회귀 — partner_portal.html dlText() 입찰마감 카운트다운의
시간(정수) 자릿수가 반올림돼 실제보다 최대 30분 가까이 여유가 있는 것처럼
보였던 결함.

  지시받은 신선한 각도 (5) '날짜/기간 표시가 실제 남은 시간과 정확히
  일치하는지, 반올림/버림 방식이 사용자에게 유리한 쪽인지 불리한 쪽인지
  일관되는지'를 직접 조사(하위위임 없음)해 발견했다 — "값이 안 바뀌어도
  로그"·타임존 경계 등 이미 포화된 각도와는 다른, 순수 표시 반올림 방향
  결함이다.

  ⚠⚠ dlText()(templates/partner_portal.html, "진행중 입찰 공고" 표의 "마감"
    열 — 시공사가 입찰 여유시간을 보고 지금 넣을지 미룰지 판단하는 바로 그
    숫자)는 h(마감까지 남은 시간, 시간 단위)가 1 이상이면 수정 전
    `Math.round(h)+'시간'` 이었다. h=1.5(정확히 1시간30분 남음)에서
    Math.round(1.5)===2(JS 는 .5 를 위로 반올림)라 "2시간 남음"이 찍혀
    실제보다 30분 가까이 여유가 있는 것처럼 보였다(h=1.99 처럼 1시간59분대인
    경우도 "2시간"으로 반내림 없이 올림).
  ⚠⚠ 같은 파일의 형제 카운트다운 셋은 전부 "실제보다 많다고 말하지 않는다"
    원칙을 지킨다 — leftText()(1210행)의 정수 시간 자릿수는 항상
    `Math.floor(h)`(분 자릿수만 반올림 + 60분 캐리 처리, 최대 오차 30초에
    불과), dpLeft()(766행, 출동 수락 카운트다운)는 분 단위를 통째로
    `Math.floor(t/60000)`(오차는 항상 과소평가 쪽). dlText() 의 h<1 분기도
    이미 라운드74가 "분을 반올림해 60분이 단독 표기되는" 결함은 고쳐 뒀는데,
    바로 그 옆 h>=1 분기는 그 라운드가 손대지 않은 채 반대 방향(과대평가)
    반올림이 그대로 남아 있었다 — round74 자신의 회귀테스트(node 실행값
    0.9999/0.999/0.5/2/0)에도 이 분기를 가르는 분수 h(1.0<h<2 구간)가 아예
    없어 지금까지 걸리지 않았다.
  ⚠ 실사용 영향 — 시공사가 "2시간 남았다"고 보고 여유를 부리다, 실제로는
    1시간30분1초 뒤(최악의 경우 그보다 더 이른 시점)에 마감돼 입찰 기회를
    놓칠 수 있다. 다른 카운트다운(leftText·dpLeft)과 정반대로 사용자에게
    유리한 착시를 주는 방향이라 나머지 셋과도 정책이 갈라져 있었다.

  고침 — 새 정책·새 헬퍼 없이 형제 leftText 의 관례(정수 시간 자릿수는
  Math.floor)를 그대로 이식했다(app.py:templates/partner_portal.html,
  dlText() h>=1 분기: `Math.round(h)` → `Math.floor(h)`). h<1 분기(라운드74
  수정분)·label·urgent 판정·반환 HTML 구조는 전혀 안 건드렸다. 정적 템플릿
  파일이라 app.py 자신의 함수도, app.py 가 import 하는 .py 모듈도 아니다 —
  다만 .env 의 BOKGUON_ENV=prod 로 실서비스는 IS_PROD=True 이고 app.py 가
  TEMPLATES_AUTO_RELOAD=not IS_PROD 로 끄므로(app.py:156), Jinja 가 컴파일된
  템플릿을 캐시해 이 수정도 프로세스 재기동 전까지는 반영되지 않는다.

  회귀테스트 — round25·round74 와 같은 전제(대상 함수엔 문자열·주석 안 중괄호가
  없다)로 중괄호 균형만으로 dlText() 본문을 실파일에서 그대로 뽑아 node 로
  실행한다(Date.now() 의존 부분만 round74 와 동일한 방식으로 우회 치환 —
  로직 자체는 100% 원본).

      python test_scan_round545_fixes.py
"""
import io
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


PP = read("templates/partner_portal.html")

print("=" * 72)
print("  스캔 545라운드 회귀 — dlText() 마감 카운트다운 시간자릿수 반올림 방향")
print("=" * 72)


def _js_fn_body(src, header):
    """`function <name>(...)  { ... }` 를 중괄호 균형으로 자른다(주석·문자열 안
    중괄호는 없다고 가정 — 대상 함수가 그렇다, round25·round74 의 leftText/
    dlText 검사와 같은 전제)."""
    i = src.find(header)
    if i < 0:
        return ""
    depth = 0
    started = False
    for k in range(i, len(src)):
        if src[k] == "{":
            depth += 1
            started = True
        elif src[k] == "}":
            depth -= 1
            if started and depth == 0:
                return src[i:k + 1]
    return ""


# ══════════════════════════════════════════════════════════════
print("\n[0] 소스 — 고친 자리 · 형제(leftText·dpLeft)·round74 수정분은 그대로인지")
# ──────────────────────────────────────────────────────────────
chk("left = Math.floor(h)+'시간';" in PP,
    "★★★ dlText h>=1 분기가 Math.floor(h) 다(이번 수정)")
chk("left = Math.round(h)+'시간';" not in PP,
    "★★★ 옛 Math.round(h)+'시간' 문구가 더는 없다")
chk("let hh = Math.floor(h), mm = Math.round((h % 1) * 60);" in PP,
    "형제 leftText 의 정수 시간자릿수 Math.floor 관례는 그대로다(안 건드림)")
chk("if(mm === 60){ hh += 1; mm = 0; }" in PP,
    "형제 leftText 의 60분 캐리 처리(라운드74)도 그대로다(회귀 없음)")
chk("mm >= 60 ? '1시간' : mm + '분'" in PP,
    "dlText 자신의 라운드74 수정(60분 단독표기 방지)도 그대로다(회귀 없음)")
chk("const m = Math.floor(t/60000);" in PP,
    "형제 dpLeft 의 분단위 내림(항상 과소평가) 관례도 그대로다(안 건드림)")

_dt = _js_fn_body(PP, "function dlText(")
chk(bool(_dt), "STEP partner_portal.html 에서 dlText 함수 본문을 추출했다", len(_dt))
chk("Math.floor(h)" in _dt and "Math.round(h)+" not in _dt,
    "STEP 추출한 dlText 본문 자체에 새 코드가 들어 있다(추출 성공 확인)")

NODE = shutil.which("node")
if not NODE:
    chk(False, "★★★ node 실행 파일을 찾을 수 없다", "node 를 찾을 수 없습니다 — [1]~[3] 스킵")
elif not _dt:
    chk(False, "★★★ dlText 본문을 못 뽑아 [1]~[3] 스킵", "")
else:
    #  dlText 는 내부에서 Date.now() 를 쓰므로, 원하는 h(시간)를 직접 넣으려면
    #  dl 인자를 바로 h 로 쓰는 보조판으로 감싼다(로직은 100% 동일, 시각 계산
    #  부분만 우회 — round74 의 dlText 검사와 같은 치환).
    _dt_h = _dt.replace(
        "const t = Date.parse(String(dl).replace(' ','T')+'+09:00');",
        "const t = Date.now() + dl * 3600000;"
    ).replace(
        "const h = (t - Date.now())/3600000;",
        "const h = dl;"
    )
    chk("const h = dl;" in _dt_h,
        "STEP Date.now() 의존 부분을 우회 치환했다(로직 본문은 원본 그대로)")

    def run_dl(hs, fn_src):
        """h 목록을 순서대로 dlText(h) 에 넣어 반환 HTML 을 한 줄씩 받는다."""
        calls = "\n".join(f"console.log(dlText({h}));" for h in hs)
        js = "function esc(s){return String(s);}\n" + fn_src + "\n" + calls
        r = subprocess.run(["node", "-e", js], capture_output=True)
        out = (r.stdout or b"").decode("utf-8", "replace")
        err = (r.stderr or b"").decode("utf-8", "replace")
        return out.splitlines(), err

    # ══════════════════════════════════════════════════════════
    print("\n[1] 실행 — 실제 파일에서 뽑은 현재(수정 후) dlText 를 node 로 그대로 돌린다")
    # ──────────────────────────────────────────────────────────
    #  h=1.5·1.99·1.01 은 전부 "1시간대"인데 예전엔 반올림으로 "2시간"이
    #  찍혔다. h=2 는 정수라 반올림/내림이 갈리지 않는 통제군(회귀 없음
    #  확인용), h=0.9999·0.5는 라운드74가 고친 h<1 분기(이번에 안 건드림)가
    #  멀쩡한지 다시 한 번 실측으로 확인한다.
    _hs = [1.5, 1.99, 1.01, 2, 0.9999, 0.5]
    _out, _err = run_dl(_hs, _dt_h)
    chk(len(_out) == len(_hs),
        "STEP node 실행이 입력한 만큼(6줄) 출력했다", f"{len(_out)}줄 · stderr={_err[:200]}")
    if len(_out) == len(_hs):
        got = dict(zip(_hs, _out))
        print("        " + " · ".join(f"h={h}→{o}" for h, o in zip(_hs, _out)))
        chk("1시간" in got[1.5] and "2시간" not in got[1.5],
            "★★★ h=1.5(정확히 1시간30분 남음) → '1시간'(과대평가 없음)",
            got[1.5])
        chk("1시간" in got[1.99] and "2시간" not in got[1.99],
            "★★★ h=1.99(1시간59분대 남음) → '1시간'(과대평가 없음)",
            got[1.99])
        chk("1시간" in got[1.01] and "2시간" not in got[1.01],
            "h=1.01 → '1시간'(경계 근처 정상)", got[1.01])
        chk("2시간" in got[2],
            "회귀 안전 — h=2(정수, 반올림·내림이 안 갈림) → 여전히 '2시간'", got[2])
        chk("1시간" in got[0.9999] and "60분" not in got[0.9999],
            "회귀 안전 — 라운드74 수정분(h=0.9999 → '60분' 단독표기 방지)은 그대로 산다",
            got[0.9999])
        chk("30분" in got[0.5],
            "회귀 안전 — h=0.5(h<1 분기, 이번에 안 건드림) → '30분' 그대로", got[0.5])

    # ══════════════════════════════════════════════════════════
    print("\n[2] 원인 재현 — 이번 수정 직전의 실제 코드를 문자열로만 재구성해 실행")
    # ──────────────────────────────────────────────────────────
    #  ⚠ 실파일(app.py 격인 이 템플릿)에는 절대 옛 코드를 쓰지 않는다 — 방금
    #    [1]에서 뽑은 새 코드 문자열 중 이번에 고친 딱 한 줄만 메모리에서
    #    되돌려 옛 동작을 재현한다(round543·544 의 exec 재구성과 같은 방식,
    #    여기서는 node 스크립트 문자열이라 파이썬 exec 대신 subprocess 로 돌림).
    _dt_old = _dt_h.replace("left = Math.floor(h)+'시간';", "left = Math.round(h)+'시간';")
    chk(_dt_old != _dt_h,
        "STEP 옛 코드 문자열이 실제로 지금 코드와 다르게 재구성됐다(치환이 먹었다)")
    _out_old, _err_old = run_dl([1.5, 1.99], _dt_old)
    chk(len(_out_old) == 2,
        "STEP 옛 코드도 node 로 정상 실행됐다(문법 자체는 멀쩡했다는 뜻)",
        f"{len(_out_old)}줄 · stderr={_err_old[:200]}")
    if len(_out_old) == 2:
        print("        [옛 코드] " + " · ".join(f"h={h}→{o}" for h, o in zip([1.5, 1.99], _out_old)))
        chk("2시간" in _out_old[0],
            "★★★ 이 회귀의 실제 탐지력 — 옛 코드(Math.round)는 h=1.5 에서 "
            "실측으로 '2시간'을 찍는다(30분 과대평가를 인과관계로 증명)",
            _out_old[0])
        chk("2시간" in _out_old[1],
            "★★★ 옛 코드는 h=1.99 에서도 '2시간'을 찍는다", _out_old[1])

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
