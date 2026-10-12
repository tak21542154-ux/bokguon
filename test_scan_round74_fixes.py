# -*- coding: utf-8 -*-
"""스캔 74라운드 회귀 — 클라이언트단(admin.js·템플릿 인라인 JS) 4곳.

  ① admin.js coCloseFull() — 전체 재경매 마감 모달을 열기 전 입찰 조회가
     실패해도 조용히 []로 넘어갔다. 그러면 "입찰이 없습니다. 유찰 처리하세요"가
     **진짜 0건인 것과 똑같이** 뜬다. 서버(api_co_close_full)의 실입찰 수 체크는
     마감 전(alive)에만 있고 마감 후 유찰(failed:true)에는 전혀 없다 — 실제로
     입찰이 있는데 이 화면이 조회실패로 "0건"을 보여주면, 관리자가 유찰을 눌러
     그 입찰들을 되돌릴 수 없이 지운다.
  ② admin.js settleReview() — 같은 종류의 조회 실패를 조용히 삼켜, 지급 검수
     "더블 크로스체크" 모달에 가짜 금액(0원)과 가짜 "계좌 미등록"을 띄웠다.
     체크박스가 잠겨(hasAcct=false) 승인 자체는 못 눌러 안전하게 막히지만,
     검수자가 진짜 상태를 오인할 수 있다.
  ③ templates/insurer_portal.html 의 leftText() — 같은 이름의
     partner_portal.html leftText() 는 이미 "분을 반올림하면 60이 나올 수 있다"
     결함(h=1.999 → '1시간 60분')을 고쳤는데, 이 사본은 안 고쳐진 채 남아
     있었다 — 사본이 둘이라 한쪽만 고치면 다시 갈라진다.
  ④ templates/partner_portal.html 의 dlText() — 같은 반올림 결함의 변종
     (h=0.999시간 근처에서 '60분'이 단독으로 찍힘, 여긴 시간 단위 조합이
     없어 '1시간 60분'은 안 나오지만 '60분' 단독 오표시는 있었다).

      python test_scan_round74_fixes.py
"""
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


ADMIN_JS = read("static/admin.js")
PP = read("templates/partner_portal.html")
IP = read("templates/insurer_portal.html")

print("═" * 72)
print("  스캔 74라운드 회귀 — 클라이언트단 조회실패 삼킴 2곳 + 카운트다운 반올림 사본 2곳")
print("═" * 72)


def _js_fn_body(src, header):
    """`function <name>(...)  { ... }` 를 중괄호 균형으로 자른다(주석·문자열 안
    중괄호는 없다고 가정 — 대상 함수 둘 다 그렇다, round25 의 leftText 검사와 같은 전제)."""
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
print("\n[1] 소스 — admin.js 두 함수의 조회실패 처리")
# ──────────────────────────────────────────────────────────────
def _js_fn(src, name):
    i = src.find(f"async function {name}(")
    return _js_fn_body(src, f"async function {name}(")


co_body = _js_fn(ADMIN_JS, "coCloseFull")
chk("catch(e){ toast(e.message); return; }" in co_body,
    "★★★ ① coCloseFull — 입찰 조회 실패 시 사용자에게 알리고 멈춘다"
    "(고치기 전엔 조용히 []로 넘어가 '입찰 없음'과 구분이 안 됐다)")

sr_body = _js_fn(ADMIN_JS, "settleReview")
chk("catch(e){ toast(e.message); return; }" in sr_body,
    "★★ ② settleReview — 상세 조회 실패 시 사용자에게 알리고 멈춘다"
    "(고치기 전엔 조용히 null 로 넘어가 가짜 0원·가짜 미등록을 띄웠다)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 소스+실행 — 카운트다운 반올림 사본 2곳(node 로 실제 실행)")
# ──────────────────────────────────────────────────────────────
chk("if(mm === 60){ hh += 1; mm = 0; }" in IP,
    "★★ ③ insurer_portal.html leftText 도 반올림 60분 방지 로직을 갖는다")

NODE_MISSING = "node 를 찾을 수 없습니다"
import shutil
NODE = shutil.which("node")
if not NODE:
    chk(False, "★★★ node 실행 파일을 찾을 수 없다", NODE_MISSING)
else:
    # ── ③ insurer_portal.html leftText ──
    _lt = _js_fn_body(IP, "function leftText(")
    chk(bool(_lt), "STEP insurer_portal.html 에서 leftText 함수 본문을 추출했다",
        len(_lt))
    if _lt:
        _js = _lt + "\n" + "".join(
            f"console.log(JSON.stringify([{h}, leftText({h})]));"
            for h in (1.999, 0.9999, 2.4999, 47.999, 1.5, 0.5, 0))
        _r = subprocess.run(["node", "-e", _js], capture_output=True)
        _out = (_r.stdout or b"").decode("utf-8", "replace")
        _bad = [ln for ln in _out.splitlines() if "60분" in ln]
        chk(not _bad and _out,
            "★★★ ③ insurer_portal.html leftText 를 실제로 돌려도 60분이 안 나온다"
            "(고치기 전엔 h=1.999 에서 '1시간 60분'이 찍혔다)",
            f"{_bad or _out or (_r.stderr or b'').decode('utf-8', 'replace')[:200]}")
        if _out:
            print("        " + " · ".join(_out.split()))

    # ── ④ partner_portal.html dlText ──
    _dt = _js_fn_body(PP, "function dlText(")
    chk(bool(_dt), "STEP partner_portal.html 에서 dlText 함수 본문을 추출했다",
        len(_dt))
    if _dt:
        #  dlText 는 내부에서 Date.now() 를 쓰므로, 원하는 h 값을 직접 재현하려면
        #  dl 대신 h 를 바로 계산하는 보조 버전으로 감싼다(로직은 100% 동일,
        #  시각 계산 부분만 우회 — round25 leftText 검사도 같은 이유로 본문만 뽑아 쓴다).
        _dt_h = _dt.replace(
            "const t = Date.parse(String(dl).replace(' ','T')+'+09:00');",
            "const t = Date.now() + dl * 3600000;"
        ).replace(
            "const h = (t - Date.now())/3600000;",
            "const h = dl;"
        )
        #  dlText 는 화면 공용 esc()(HTML 이스케이프)를 부른다 — 라벨 내용 자체는
        #  이 검사의 관심사가 아니므로(관심사는 '남음' 카운트다운 텍스트) 항등
        #  스텁으로 대신한다.
        _js2 = "function esc(s){return String(s);}\n" + _dt_h + "\n" + "".join(
            f"console.log(JSON.stringify([{h}, dlText({h})]));"
            for h in (0.9999, 0.999, 0.5, 2, 0))
        _r2 = subprocess.run(["node", "-e", _js2], capture_output=True)
        _out2 = (_r2.stdout or b"").decode("utf-8", "replace")
        #  ⚠ "60분"은 렌더된 HTML 안에 다른 글자와 붙어 나온다(예: ">60분 남음</span>")
        #    — 양쪽에 따옴표가 바로 붙어 있다고 가정하면 못 잡는다. 부분 문자열로 본다.
        _bad2 = [ln for ln in _out2.splitlines() if "60분" in ln]
        chk(not _bad2 and _out2,
            "★★ ④ partner_portal.html dlText 를 실제로 돌려도 '60분' 단독 오표시가"
            " 안 나온다(고치기 전엔 h=0.9999 에서 '60분'이 찍혔다 — '1시간' 이어야 함)",
            f"{_bad2 or _out2 or (_r2.stderr or b'').decode('utf-8', 'replace')[:300]}")
        if _out2:
            print("        " + " · ".join(_out2.split()))

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
