# -*- coding: utf-8 -*-
"""스캔 75라운드 회귀 — insurer_portal.html 이 admin.js·partner_portal.html 에
   이미 있던 두 수정을 받지 못하고 있었다(사본 드리프트, round73/74 와 같은 계열).

  ① filteredCases() 의 '낙찰가 높은순' 정렬이 low_price 만 봤다 — admin.js
     sortCasesList() 는 이미 "표에 그리는 금액은 award_amount||low_price 인데
     정렬은 low_price 만 본다"는 결함을 award_amount 우선으로 고쳤다. 경매 없이
     확정되는 1차합의 건은 입찰이 없어 low_price 가 비어 있어, 확정 금액이
     가장 큰 건이 '높은순' 맨 아래로 밀렸다.
  ② stTag() 의 '취소' 가 gray 였다 — partner_portal.html stTag() 는 이미
     "매핑에 없으면 회색이니 취소·유찰은 구분돼야 한다"며 red 로 고쳤다.
     사건 취소는 실제로 이 함수를 거치는 경로다(app.py: UPDATE cases
     SET status='취소').

      python test_scan_round75_fixes.py
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


IP = read("templates/insurer_portal.html")
PP = read("templates/partner_portal.html")
ADMIN_JS = read("static/admin.js")

print("═" * 72)
print("  스캔 75라운드 회귀 — insurer_portal.html 정렬·상태색 사본 드리프트 2곳")
print("═" * 72)


def _js_fn_body(src, header):
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
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
fc_body = _js_fn_body(IP, "function filteredCases(")
chk("award_amount || x.low_price" in fc_body or "x.award_amount || x.low_price" in fc_body,
    "★★ ① insurer_portal.html filteredCases 의 정렬이 award_amount 를 우선 본다")
chk("(b.low_price||0)-(a.low_price||0)" not in fc_body,
    "STEP 옛 low_price 단독 정렬식이 사라졌다")

st_body = _js_fn_body(IP, "function stTag(")
chk("'취소':'red'" in st_body,
    "★ ② insurer_portal.html stTag 의 '취소'가 red 다(partner_portal.html 과 일치)")
chk("'취소':'gray'" not in st_body,
    "STEP 옛 gray 매핑이 사라졌다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — node 로 실제 실행")
# ──────────────────────────────────────────────────────────────
NODE = shutil.which("node")
if not NODE:
    chk(False, "★★★ node 실행 파일을 찾을 수 없다", "node --check 로 파싱하는 검사라 건너뛸 수 없음")
else:
    # ── ① 정렬 — 실제 filteredCases() 함수 자체를 호출한다(직접 재구현하지
    #    않는다 — round72 에서 자체 SQL을 실행해 앱 코드를 안 거친 채 통과하던
    #    자가결함을 겪었다. 여기서도 처음엔 정렬식을 테스트가 스스로 다시 써서
    #    되돌린 코드로도 통과하는 결함이 있었다 — 실제 함수를 불러야 한다).
    #    award_amount 만 있고 low_price 는 0/없음인 두 사건을 비교한다.
    _sort_js = """
    const D = { cases: [
      {id:1, award_amount: 50000000, low_price: 0},   // 1차합의 확정(입찰 없음) — 고액
      {id:2, award_amount: 0, low_price: 3000000}      // 경매 낙찰 — 저액
    ]};
    const CF = {status:'', region:'', cat:'', q:'', sort:'award'};
    """ + fc_body + "\n" + "console.log(JSON.stringify(filteredCases().map(c=>c.id)));"
    _r = subprocess.run(["node", "-e", _sort_js], capture_output=True)
    _out = (_r.stdout or b"").decode("utf-8", "replace").strip()
    chk(_out == '[1,2]',
        "★★★ ① 1차합의 확정(입찰 없음·고액)이 낙찰가 높은순 맨 위로 온다"
        "(고치기 전 로직이면 low_price=0 인 1번이 밑으로 밀려 [2,1] 이 나온다)",
        f"out={_out!r} stderr={(_r.stderr or b'').decode('utf-8','replace')[:200]}")

    # ── ② stTag('취소') 색상 ──
    _tag_js = "function esc(s){return String(s);}\n" + st_body + "\nconsole.log(stTag('취소'));"
    _r2 = subprocess.run(["node", "-e", _tag_js], capture_output=True)
    _out2 = (_r2.stdout or b"").decode("utf-8", "replace").strip()
    chk('class="tag red"' in _out2,
        "★★ ② stTag('취소') 가 실제로 red 클래스를 낸다(고치기 전엔 gray 였다)",
        f"out={_out2!r} stderr={(_r2.stderr or b'').decode('utf-8','replace')[:200]}")

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
