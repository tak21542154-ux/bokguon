# -*- coding: utf-8 -*-
"""스캔 242라운드 회귀 — admin.js settleAction() 의 "이체 완료" 확인창 정보가
   지급액이 정확히 0원일 때 공사대금(전액)으로 잘못 표시되던 결함(admin.js
   정산화면 Agent 병렬조사로 발견).

  `Number(s.payout || s.amount || 0)` 는 payout 이 **정확히 0**(수수료 100%
  계약 — _parse_fee_pct 는 0~100 을 다 허용해 실제로 나올 수 있는 값)일 때도
  "없음"으로 오판해 공사대금 전액으로 대체했다 — 라운드74가 fee_rate_bp 에서
  이미 고친 것과 정확히 같은 "0 은 falsy" 함정을 같은 파일 다른 자리에서
  또 밟았다. 바로 한 단계 전 더블체크 모달(settleReview, won(s.payout) 직접
  사용 — 이런 대체가 없다)은 이미 "0원"이라고 정확히 보여준 뒤라, **돈이
  나가는 마지막 문에서 두 화면이 서로 다른 금액을 말했다**(실제 이체
  요청에는 금액을 안 실어 보내므로 DB·통지는 영향 없음 — 순수 표시결함).
  `??` 로 바꿔 "정말 없음(null/undefined)"일 때만 amount 로 대체한다.

      python test_scan_round242_fixes.py
"""
import io
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

print("=" * 72)
print("  스캔 242라운드 회귀 — 이체완료 확인창의 0원 오판(공사대금 전액 표시)")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = ADMIN_JS.index("function settleAction(")
i1 = ADMIN_JS.index("\n// 정산 취소", i0 + 1)
sa_body = ADMIN_JS[i0:i1]
chk('Number(s.payout ?? s.amount ?? 0)' in sa_body,
    "★★★★ tinfo 구성이 이제 ?? 로 정확히 0 인 payout 을 amount 로 안 바꾼다")
chk('Number(s.payout || s.amount || 0)' not in sa_body,
    "STEP 옛 falsy 판정(|| 연쇄)이 더는 없다")

# ============================================================
print("\n[2] 실행 — Node 로 settleAction() 을 실제 실행해 tinfo 문자열 확인")
# ------------------------------------------------------------
HARNESS = r'''
const fs = require('fs');
const vm = require('vm');
const SRC = fs.readFileSync(process.argv[2], 'utf8');
const i0 = SRC.indexOf('function settleAction(');
const i1 = SRC.indexOf('\n// 정산 취소', i0);
const fnSrc = SRC.slice(i0, i1);
//  ⚠⚠ [337라운드] settleAction() 이 이제 myRank() 를 직접 부른다(버튼별
//    등급게이트) — 이 하네스는 그 전에 만들어져 몰랐다. 이 테스트의 관심사는
//    등급이 아니라 이체완료 확인창의 0원 표시 버그이므로, 그 버튼이 항상
//    그려지는 최고관리자(3)로 고정해 원래 시나리오(둘 다 이체 단계)를 그대로
//    검증한다 — round252 의 coActions 하네스도 같은 이유로 rank 를 받는다.
const sandbox = { esc: (s) => String(s == null ? '' : s), myRank: () => 3 };
vm.createContext(sandbox);
vm.runInContext(fnSrc + '\nthis.settleAction = settleAction;', sandbox);

const base = { id: 1, void_status: null, transfer_status: '대기',
               insurer_paid: '입금완료', review_status: '승인', insurer_approved: 1,
               case_no: 'C-1', partner_name: 'P-1' };

// 시나리오1: payout 이 정확히 0 (수수료 100%) — amount(전액)로 새면 안 된다
const html0 = sandbox.settleAction({ ...base, payout: 0, amount: 500000 });
const m0 = html0.match(/data-info="([^"]*)"/);
const info0 = m0 ? m0[1] : '';

// 시나리오2: payout 이 정상적으로 존재 — 그 값 그대로 나와야 한다(회귀 없음)
const html1 = sandbox.settleAction({ ...base, payout: 123000, amount: 500000 });
const m1 = html1.match(/data-info="([^"]*)"/);
const info1 = m1 ? m1[1] : '';

console.log(JSON.stringify({ info0, info1 }));
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
    chk(r.returncode == 0, "STEP Node 하네스가 예외 없이 끝까지 실행된다",
        r.stdout + r.stderr)
    import json
    out = json.loads((r.stdout or "{}").strip().splitlines()[-1]) if r.returncode == 0 else {}
    chk(out.get("info0", "").endswith("|0"),
        "★★★★ payout=0(수수료 100%) 이면 data-info 의 금액이 0 이다"
        "(고치기 전엔 amount=500000 이 그대로 새어 나왔다)", out)
    chk(out.get("info1", "").endswith("|123000"),
        "★★★ payout 이 정상 존재하면 그 값이 그대로 쓰인다(회귀 없음)", out)
except FileNotFoundError:
    chk(False, "STEP node 실행 파일을 찾을 수 없음(PATH 확인 필요)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드242 [2] 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
