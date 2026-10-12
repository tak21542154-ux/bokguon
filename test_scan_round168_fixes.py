# -*- coding: utf-8 -*-
"""스캔 168라운드 회귀 — 클라이언트측 HTML 이스케이프 esc() 가 3곳(admin.js·
partner_portal.html·insurer_portal.html)에서만 작은따옴표(')를 안 거르던 결함.

  form.js 는 "여기서 const esc 를 또 선언하면 두 클래식 스크립트가 같은
  전역 스코프에 const 를 중복선언해 SyntaxError 로 화면이 멈춘다"는 걸 알고
  일부러 window.esc 에 더 강한 판(작은따옴표까지 이스케이프)을 심어 뒀다.
  그런데 정작 두 포털(partner_portal.html·insurer_portal.html)은 form.js
  로딩 직후 자기만의 const esc(작은따옴표 누락판)를 다시 선언한다 — 이건
  SyntaxError 는 안 나지만, 전역 렉시컬 스코프에서 그 이름의 const 바인딩이
  window 속성 조회보다 우선하므로 형제 파일(addrpick.js 등)이 쓰는 window.esc
  로도 안 가고, 화면의 모든 esc() 호출이 이 약한 판으로 조용히 뒤바뀐다.
  admin.js 는 형제와 무관하게 그 자체가 처음부터 약한 판이었다.

  지금 당장 작은따옴표로 감싼 속성에 꽂히는 자리는 없어 즉시 뚫리진 않지만,
  이 코드베이스 스스로 만든 방어층(form.js)이 두 포털에서는 조용히 죽어
  있었다는 뜻이고, 나중에 누가 자연스럽게 attr='...' 를 하나 추가하면
  "esc() 로 막고 있다"고 믿은 채로 뚫린다.

      python test_scan_round168_fixes.py
"""
import io
import json
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


SITES = [
    ("static/admin.js", "admin.js"),
    ("templates/partner_portal.html", "partner_portal.html"),
    ("templates/insurer_portal.html", "insurer_portal.html"),
]

print("=" * 72)
print("  스캔 168라운드 회귀 — esc() 작은따옴표 이스케이프 누락(3곳)")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
extracted = {}
for rel, label in SITES:
    src = read(rel)
    #  ⚠ 첫 ";" 로 자르면 안 된다 — 치환 맵의 HTML 엔티티 문자열 자체가
    #    세미콜론을 담고 있다('&amp;' 의 그 ';'). 이 화살표 함수의 고정된
    #    끝(}[c]));)을 찾아 거기까지 정확히 자른다.
    i0 = src.index("const esc = s =>")
    i1 = src.index("}[c]));", i0) + len("}[c]));")
    line = src[i0:i1]
    extracted[label] = line
    chk('[&<>"\']' in line, f"★★★ {label} — esc() 정규식에 작은따옴표가 포함된다", line)
    chk("'&#39;'" in line, f"★★ {label} — 작은따옴표를 &#39; 로 치환한다", line)

# ============================================================
print("\n[2] 실행 — 실제 Node.js 로 esc() 를 돌려 다섯 특수문자가 전부 이스케이프되는가")
# ------------------------------------------------------------
NODE = shutil.which("node")
if not NODE:
    chk(False, "★★★ node 를 찾을 수 없다 — 이 검사는 실제 실행으로만 증명된다", "node not found")
else:
    PAYLOAD = "a&b<c>d\"e'f"
    EXPECT = "a&amp;b&lt;c&gt;d&quot;e&#39;f"
    for rel, label in SITES:
        line = extracted[label]
        #  JSON 문자열 리터럴은 그대로 유효한 JS 문자열 리터럴이다(따옴표·이스케이프
        #  방식이 호환) — Python repr() 에 기대는 것보다 이쪽이 더 확실하다.
        script = f"{line}\nprocess.stdout.write(esc({json.dumps(PAYLOAD)}));"
        try:
            r = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=10,
                                encoding="utf-8", errors="replace")
            out = r.stdout
        except Exception as e:                                     # noqa: BLE001
            out = f"<실행 실패: {e}>"
        chk(out == EXPECT,
            f"★★★ {label} — 실제 esc() 실행 결과가 다섯 특수문자를 전부 이스케이프한다"
            f"(고치기 전엔 작은따옴표만 그대로 남았다)", (out, EXPECT))

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
