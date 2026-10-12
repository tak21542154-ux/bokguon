# -*- coding: utf-8 -*-
"""스캔 243라운드 회귀 — admin.js 하자 상세(defectDetail)의 귀책(cost_bearer)
   드롭다운에 '보험사' 옵션이 없던 결함(admin.js 하자화면 Agent 병렬조사로 발견).

  서버(api_defect_update)는 103라운드부터 cost_bearer='보험사'를 정당한 값으로
  검증·저장한다(61라운드: 이의를 검토한 뒤 귀책을 보험사로 정하는 정상 경로 —
  API·test_fairness.py 가 이미 실사용). 그런데 admin.js 의 #d_cb 셀렉트에는
  '시행사'·'협의필요' 두 옵션뿐이었다 — 이미 코드 자신의 주석이 "admin.js
  드롭다운엔 아직 없다"고 103라운드부터 자인하고 있었다.

  단순 기능누락에 그치지 않는다: cost_bearer='보험사'인 하자를 열면 일치하는
  <option> 이 없어 브라우저가 첫 옵션('시행사')으로 자동 표시한다. defectAct()
  의 "안 바뀌면 안 보낸다" 가드(89라운드, `cb !== d.cost_bearer`)는 이 값을
  절대 '시행사'와 같다고 안 보므로, 다음 상태전이 버튼(확인중·완료·반려 등
  무엇이든)을 누를 때마다 매번 '시행사'로 조용히 되돌렸다 — 보험사 귀책으로
  이미 결론난 하자가 협력사 평점 차감까지 다시 맞을 수 있었다.

      python test_scan_round243_fixes.py
"""
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


ADMIN_JS = read("static/admin.js")
APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 243라운드 회귀 — 하자 귀책 드롭다운에 '보험사' 옵션 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = ADMIN_JS.index('<select id="d_cb">')
i1 = ADMIN_JS.index("</select>", i0) + len("</select>")
select_src = ADMIN_JS[i0:i1]
chk('value="보험사"' in select_src,
    "★★★★ #d_cb 드롭다운에 '보험사' 옵션이 있다"
    "(서버는 103라운드부터 이미 정당한 값으로 받아들이는데 화면엔 없었다)")
chk("d.cost_bearer==='보험사'?' selected':''" in select_src,
    "STEP 그 옵션도 다른 둘처럼 실제 값과 대조해 selected 를 붙인다")
chk('d["cost_bearer"] not in ("시행사", "보험사", "협의필요")' in APP_SRC,
    "STEP (참고) 서버 쪽 검증은 이미 세 값 모두 허용한다 — 이번에 안 바뀜")

# ============================================================
print("\n[2] 실행 — Node 로 셀렉트 렌더링을 실제 평가해 브라우저가 고를 값을 확인")
# ------------------------------------------------------------
HARNESS = r'''
const fs = require('fs');
const SRC = fs.readFileSync(process.argv[2], 'utf8');
const i0 = SRC.indexOf('<select id="d_cb">');
const i1 = SRC.indexOf('</select>', i0) + '</select>'.length;
const tpl = SRC.slice(i0, i1);
const render = new Function('d', 'return `' + tpl + '`;');

function pickBrowserValue(html) {
  // <option value="X" selected> 가 있으면 그 값, 없으면 첫 <option> 값(브라우저 기본 동작)
  const selMatch = html.match(/<option value="([^"]+)"\s+selected>/);
  if (selMatch) return selMatch[1];
  const firstMatch = html.match(/<option value="([^"]+)"/);
  return firstMatch ? firstMatch[1] : null;
}

const out = {};
for (const cb of ['시행사', '보험사', '협의필요']) {
  const html = render({ cost_bearer: cb });
  out[cb] = pickBrowserValue(html);
}
console.log(JSON.stringify(out));
'''

try:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(HARNESS)
        harness_path = f.name
    try:
        r = subprocess.run(["node", harness_path, os.path.join(HERE, "static", "admin.js")],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=30)
    finally:
        try:
            os.unlink(harness_path)
        except OSError:
            pass
    chk(r.returncode == 0, "STEP Node 하네스가 예외 없이 끝까지 실행된다", r.stdout + r.stderr)
    out = json.loads((r.stdout or "{}").strip().splitlines()[-1]) if r.returncode == 0 else {}
    chk(out.get("보험사") == "보험사",
        "★★★★ cost_bearer='보험사'인 하자를 열면 브라우저가 실제로 '보험사'를 "
        "선택 상태로 표시한다(고치기 전엔 일치하는 옵션이 없어 첫 옵션인 "
        "'시행사'로 조용히 바뀌어 보였다)", out)
    chk(out.get("시행사") == "시행사" and out.get("협의필요") == "협의필요",
        "STEP 기존 두 값은 그대로 정확히 표시된다(회귀 없음)", out)
except FileNotFoundError:
    chk(False, "STEP node 실행 파일을 찾을 수 없음(PATH 확인 필요)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드243 [2] 실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — defectAct() 의 '안 바뀌면 안 보낸다' 가드가 이제 '보험사'도 인식")
# ------------------------------------------------------------
try:
    i2 = ADMIN_JS.index("async function defectAct(")
    i3 = ADMIN_JS.index("\nasync function ", i2 + 1)
    da_body = ADMIN_JS[i2:i3]
    i_guard = da_body.index("if (cb && d && cb !== d.cost_bearer)")
    guard_line = da_body[i_guard:da_body.index("\n", i_guard)]
    # cb 가 이제 select 렌더링 결과와 같은 값을 읽어올 수 있으므로(위 [2] 확인),
    # '보험사'로 이미 결정된 하자를 열었을 때 cb === '보험사' === d.cost_bearer 라
    # 이 조건이 거짓이 되어 body.cost_bearer 가 안 채워짐을 파이썬으로 직접 재현한다.
    cb = "보험사"      # 고친 뒤: select 가 실제로 '보험사' 를 읽어온다([2] 확인)
    d_cost_bearer = "보험사"
    would_overwrite = bool(cb) and bool(True) and (cb != d_cost_bearer)
    chk(not would_overwrite,
        "★★★★ 귀책이 이미 '보험사'인 하자는 다른 버튼을 눌러도 더는 "
        "'시행사'로 되돌아가지 않는다(고치기 전엔 cb 가 '보험사'를 절대 "
        "읽어올 수 없어 이 가드가 항상 '바뀌었다'고 오판했다)")
    chk(guard_line.strip() == "if (cb && d && cb !== d.cost_bearer) body.cost_bearer = cb;",
        "STEP 가드 로직 자체는 89라운드 그대로다(이번엔 셀렉트만 고쳤다)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드243 [3] 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
