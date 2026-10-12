# -*- coding: utf-8 -*-
"""스캔 477라운드 회귀 — 1차합의(현장 견적) 승인 경합에서 진 쪽이 받는
NOT_PENDING 응답이 이미 fetch해 둔 합의 정보를 버리고 맨 문구만 돌려주던
결함(app.py) + 보험사 포털(insurer_portal.html)의 faDecide·doAward 둘 다
실패 분기에서 성공 분기와 달리 모달을 안 닫고 새로고침도 안 하던 결함,
총 2건.

형제 비교: api_insurer_award()의 ALREADY_AWARDED 409는
"(현재 상태: {c['status']})"로 현재 상태를 알려주고, dispatch.py의
settle_agreement() 가드도 "(현재 상태 'X' · 담당 Y)" 식으로 상태+행위자를
알려준다. 반면 api_insurer_field_agreement_decision()의 NOT_PENDING
409는 line 17722에서 이미 DP.agreement_view(conn, cid)로 합의 전체
행(승인자·확정금액·시각 포함)을 fetch해 놓고도 그걸 통째로 버린 채
"승인 대기 중인 현장 견적이 없습니다."만 돌려줬다 — 경합에서 진 보험사
직원은 누가·언제·얼마에 이미 처리했는지 알 방법이 없었다.

[1] 소스 확인 — 새 _detail 블록·[라운드477] 주석·프런트 catch 두 곳의
    closeModal/reload 호출이 실제로 있음.
[2] 실제 Flask 앱(서브프로세스 워커) 실행 — 사건접수→출동→도착→1차합의
    개시까지 실제로 진행시킨 뒤 보험사가 승인(1차, 이김) → 곧바로 같은
    사건에 다시 결정 시도(2차, 짐)를 실제 HTTP 호출로 재현, 진 쪽 응답에
    현재 상태·승인자명이 실제로 담기는지 확인.
[3] 되돌림-증명(백엔드) — app.py의 새 블록을 옛(취약) 한 줄짜리 메시지로
    임시 되돌려(파일을 실제로 잠깐 고쳤다가 finally에서 원본과 바이트단위로
    동일하게 복원) 같은 시나리오에서 진 쪽이 맨 문구만 받는 옛 동작이
    실제로 재현되는지 대조.
[4] 실제 JS 실행(Node vm, 340·464라운드가 세운 방식 그대로) — faDecide·
    doAward의 catch 분기가 실패 시 toast뿐 아니라 closeModal·reload·show도
    실제로 호출하는지 확인.
[5] 되돌림-증명(프런트) — 두 catch 블록을 옛(토스트만) 코드로 임시
    되돌려 옛 동작(모달 미갱신)이 실제로 재현되는지 대조.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 477라운드 회귀 — 1차합의 승인경합 부실 에러 + 모달 미갱신")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ══════════════════════════════════════════════════════════════
APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

OLD_BACKEND = '''        a = DP.agreement_view(conn, cid)
        if not a or a.get("status") != DP.AG_REVIEW:
            return jsonify({"ok": False, "code": "NOT_PENDING",
                            "error": "승인 대기 중인 현장 견적이 없습니다."}), 409'''

_bi = APP_SRC.find('def api_insurer_field_agreement_decision(cid):')
_bstart = APP_SRC.find("        a = DP.agreement_view(conn, cid)", _bi)
_bend = APP_SRC.find('"error": "승인 대기 중인 현장 견적이 없습니다." + _detail}), 409', _bstart)
_bend = APP_SRC.find("\n", _bend) if _bend > 0 else -1
NEW_BACKEND = APP_SRC[_bstart:_bend] if _bstart > 0 and _bend > 0 else ""

chk(_bi > 0, "api_insurer_field_agreement_decision() 함수를 소스에서 찾았다")
chk("[라운드477]" in NEW_BACKEND and "_detail" in NEW_BACKEND,
    "★★★★★ NOT_PENDING 분기에 [라운드477] 상세정보 블록이 실제로 있다")
chk(APP_SRC.count(NEW_BACKEND) == 1 and len(NEW_BACKEND) > 0,
    "되돌림-증명에 쓸 새 블록이 소스에 정확히 1번만 있다(대체 지점 특정 가능)",
    APP_SRC.count(NEW_BACKEND) if NEW_BACKEND else "블록을 못 뽑음")

TPL_PATH = os.path.join(HERE, "templates", "insurer_portal.html")
TPL_SRC = io.open(TPL_PATH, encoding="utf-8").read()

_fi = TPL_SRC.find("async function faDecide(")
_fcatch = TPL_SRC.find("}catch(e){", _fi)
_fend = TPL_SRC.find("\n  }\n}", _fcatch)
faDecide_block = TPL_SRC[_fi:_fend + len("\n  }\n}")] if _fi > 0 and _fcatch > 0 and _fend > 0 else ""

_di = TPL_SRC.find("async function doAward(")
_dcatch = TPL_SRC.find("}catch(e){", _di)
_dend = TPL_SRC.find("\n  }\n}", _dcatch)
doAward_block = TPL_SRC[_di:_dend + len("\n  }\n}")] if _di > 0 and _dcatch > 0 and _dend > 0 else ""

#  되돌림-증명(아래 [4]+[5])에 쓸 catch 블록 그 자체(함수 전체가 아니라)를
#  같은 find()로 뽑아 둔다 — 손으로 옮겨 적으면 공백·줄바꿈이 어긋나기
#  쉽다(이 세션의 reference_edit_drops_bundled_line류 실수를 반복하지
#  않기 위해 항상 실제 파일에서 프로그램으로 추출).
NEW_FADECIDE_CATCH = TPL_SRC[_fcatch:_fend + len("\n  }\n}")] if _fcatch > 0 and _fend > 0 else ""
NEW_DOAWARD_CATCH = TPL_SRC[_dcatch:_dend + len("\n  }\n}")] if _dcatch > 0 and _dend > 0 else ""
OLD_FADECIDE_CATCH = "}catch(e){ toast(esc(e.message)); }\n}"
OLD_DOAWARD_CATCH = "}catch(e){ toast(e.message); }\n}"

chk(_fi > 0 and _di > 0, "faDecide·doAward 함수를 templates/insurer_portal.html에서 찾았다")
chk("closeModal(); await reload(); show('home');" in faDecide_block
    and faDecide_block.count("closeModal()") == 2,
    "★★★★★ faDecide의 catch 분기도 closeModal·reload를 호출한다(성공분기와 동일)",
    faDecide_block[-300:] if faDecide_block else "블록을 못 뽑음")
chk("closeModal(); await reload(); show('cases');" in doAward_block
    and doAward_block.count("closeModal()") == 2,
    "★★★★★ doAward의 catch 분기도 closeModal·reload를 호출한다(성공분기와 동일)",
    doAward_block[-300:] if doAward_block else "블록을 못 뽑음")

# ══════════════════════════════════════════════════════════════
print("\n[2]+[3] 실제 Flask 서브프로세스 — 승인경합 재현 + 되돌림-증명(백엔드)")
# ══════════════════════════════════════════════════════════════
WORKER = os.path.join(HERE, "test_scan_round477_worker.py")


def _run_worker(broken=False):
    """broken=True 면 워커 서브프로세스 **안에서** 기법1(view_functions 스왑)로
    api_insurer_field_agreement_decision 라우트를 되돌린 버전으로 바꿔치기하고
    실행한다(R477_BROKEN 환경변수로 트리거) — 실제 app.py 파일은 이 프로세스에서도
    저 서브프로세스에서도 전혀 안 건드린다(라운드625, 이전 버전은 여기서
    io.open(APP_PATH,"w").write(reverted_src) 로 실제 파일에 썼다가 복원했다)."""
    env = dict(os.environ)
    if broken:
        env["R477_BROKEN"] = "1"
    r = subprocess.run([sys.executable, "-u", WORKER], capture_output=True,
                        text=True, encoding="utf-8", timeout=60, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"워커 실행 실패(rc={r.returncode}): {r.stdout}\n{r.stderr}")
    return json.loads(r.stdout.strip().splitlines()[-1])


try:
    fixed = _run_worker()
    chk(fixed.get("fa_open_status") == 200, "1차합의 개시(관리자) 200", fixed.get("fa_open_status"))
    chk(fixed.get("win_status") == 200 and fixed["win_body"].get("ok") is True,
        "★★★★★ 1차 결정(이긴 쪽)은 200으로 성공한다", fixed.get("win_body"))
    chk(fixed.get("field_agreement_after", {}).get("status") == "합의",
        "합의 확정 후 field_agreements.status == '합의'", fixed.get("field_agreement_after"))
    lose_body = fixed.get("lose_body", {})
    chk(fixed.get("lose_status") == 409 and lose_body.get("code") == "NOT_PENDING",
        "2차 결정(진 쪽)은 409 NOT_PENDING을 받는다", lose_body)
    chk("현재 상태 '합의'" in (lose_body.get("error") or ""),
        "★★★★★ 진 쪽 에러 메시지에 현재 상태('합의')가 실제로 담긴다", lose_body.get("error"))
    chk("R477보험" in (lose_body.get("error") or ""),
        "★★★★★ 진 쪽 에러 메시지에 승인자명(R477보험)이 실제로 담긴다", lose_body.get("error"))

    # (B) 되돌림-증명 — 기법1(view_functions 스왑), 실제 app.py는 안 건드림
    broken = _run_worker(broken=True)
    _lose = broken.get("lose_body", {})
    chk(broken.get("lose_status") == 409 and _lose.get("code") == "NOT_PENDING",
        "옛 코드(되돌림)도 409 NOT_PENDING 자체는 그대로 낸다(구조는 안 바뀜)", _lose)
    chk(_lose.get("error") == "승인 대기 중인 현장 견적이 없습니다.",
        "★★★★★ 옛 코드(되돌림)는 현재 상태·승인자명 없이 맨 문구만 돌려준다"
        " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", _lose.get("error"))
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] 백엔드 실행/되돌림-증명", f"{type(e).__name__}: {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py는 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일)")

# ══════════════════════════════════════════════════════════════
print("\n[4]+[5] 실제 JS 실행(Node vm) — faDecide·doAward 되돌림-증명(프런트)")
# ══════════════════════════════════════════════════════════════

#  ⚠ 340·464라운드가 세운 방식 그대로 — Node harness를 문자열로 갖고 있다가
#    임시파일로 떨궈 실행한다. 함수 경계는 고정 길이 텍스트창이 아니라
#    실제 괄호 균형으로 찾는다(라운드15가 겪은 창구간 충돌 클래스 회피).
NODE_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");

const tplPath = process.argv[2];
const src = fs.readFileSync(tplPath, "utf8");

function extractFn(name) {
  const startPat = new RegExp("async\\s+function\\s+" + name + "\\s*\\([^)]*\\)");
  const m = startPat.exec(src);
  if (!m) throw new Error("함수를 못 찾음: " + name);
  let depth = 0, i = m.index + m[0].length;
  const braceStart = src.indexOf("{", i);
  depth = 0;
  for (i = braceStart; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}") { depth--; if (depth === 0) break; }
  }
  if (depth !== 0) throw new Error("중괄호 짝을 못 찾음: " + name);
  return src.slice(m.index, i + 1);
}

const faDecideSrc = extractFn("faDecide");
const doAwardSrc = extractFn("doAward");

function makeSandbox() {
  const calls = { toast: 0, closeModal: 0, reload: 0, show: [] };
  const sandbox = {
    window: { FA_VIEW: { case_no: "T", amount: 900000, partner: "P" } },
    AW_BIDS: [],
    SELBID: null,
    document: { getElementById: () => ({ value: "" }) },
    confirm: () => true,
    esc: (x) => x,
    toast: () => { calls.toast++; },
    closeModal: () => { calls.closeModal++; },
    reload: async () => { calls.reload++; },
    show: (v) => { calls.show.push(v); },
    api: async () => { throw { message: "TEST_FAIL" }; },
    console,
  };
  vm.createContext(sandbox);
  return { sandbox, calls };
}

async function run() {
  const out = {};

  { const { sandbox, calls } = makeSandbox();
    vm.runInContext(faDecideSrc + "\nthis.faDecide = faDecide;", sandbox);
    await vm.runInContext("faDecide(1, 1)", sandbox);
    out.faDecide = calls; }

  { const { sandbox, calls } = makeSandbox();
    vm.runInContext(doAwardSrc + "\nthis.doAward = doAward;", sandbox);
    await vm.runInContext("doAward(1)", sandbox);
    out.doAward = calls; }

  console.log(JSON.stringify(out));
}

run().catch(e => { console.error(e.stack || String(e)); process.exit(1); });
"""


def _run_js_harness(tpl_path=None):
    harness_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                          encoding="utf-8") as f:
            f.write(NODE_HARNESS)
            harness_path = f.name
        r = subprocess.run(["node", harness_path, tpl_path or TPL_PATH],
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
        if r.returncode != 0:
            raise RuntimeError(f"Node 실행 실패(rc={r.returncode}): {r.stdout}\n{r.stderr}")
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        if harness_path and os.path.exists(harness_path):
            os.unlink(harness_path)


try:
    fixed_js = _run_js_harness()
    chk(fixed_js["faDecide"]["toast"] == 1 and fixed_js["faDecide"]["closeModal"] == 1
        and fixed_js["faDecide"]["reload"] == 1 and fixed_js["faDecide"]["show"] == ["home"],
        "★★★★★ 새 코드: faDecide 실패 시 toast뿐 아니라 closeModal·reload·show도 호출됨",
        fixed_js["faDecide"])
    chk(fixed_js["doAward"]["toast"] == 1 and fixed_js["doAward"]["closeModal"] == 1
        and fixed_js["doAward"]["reload"] == 1 and fixed_js["doAward"]["show"] == ["cases"],
        "★★★★★ 새 코드: doAward 실패 시 toast뿐 아니라 closeModal·reload·show도 호출됨",
        fixed_js["doAward"])

    # (B) 되돌림-증명 — ⚠⚠ [라운드625] 이전 버전은 여기서 실제 살아있는
    #    templates/insurer_portal.html 파일에 직접 썼다 — _run_js_harness가
    #    이미 파일 경로를 인자로 받게 돼 있으므로, tempfile 스크래치 사본에
    #    되돌린 내용을 쓰고 그 경로를 하니스에 넘긴다(실제 템플릿은 안 건드림).
    assert NEW_FADECIDE_CATCH and NEW_DOAWARD_CATCH, "새 catch 블록을 못 뽑았다"
    reverted_tpl = TPL_SRC.replace(NEW_FADECIDE_CATCH, OLD_FADECIDE_CATCH) \
                          .replace(NEW_DOAWARD_CATCH, OLD_DOAWARD_CATCH)
    assert reverted_tpl != TPL_SRC, "되돌림 치환이 실제로 안 먹었다(faDecide/doAward)"
    assert OLD_FADECIDE_CATCH in reverted_tpl, "되돌림 치환이 실제로 안 먹었다(faDecide 확인)"
    assert OLD_DOAWARD_CATCH in reverted_tpl, "되돌림 치환이 실제로 안 먹었다(doAward 확인)"
    _scratch_dir = tempfile.mkdtemp(prefix="r477_tpl_")
    _scratch_tpl = os.path.join(_scratch_dir, "insurer_portal.html")
    io.open(_scratch_tpl, "w", encoding="utf-8", newline="\n").write(reverted_tpl)
    try:
        broken_js = _run_js_harness(tpl_path=_scratch_tpl)
        chk(broken_js["faDecide"]["toast"] == 1 and broken_js["faDecide"]["closeModal"] == 0
            and broken_js["faDecide"]["reload"] == 0,
            "★★★★★ 옛 코드(되돌림)는 faDecide 실패 시 toast만 하고 모달은 안 건드린다"
            " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", broken_js["faDecide"])
        chk(broken_js["doAward"]["toast"] == 1 and broken_js["doAward"]["closeModal"] == 0
            and broken_js["doAward"]["reload"] == 0,
            "★★★★★ 옛 코드(되돌림)는 doAward 실패 시 toast만 하고 모달은 안 건드린다"
            " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", broken_js["doAward"])
    finally:
        shutil.rmtree(_scratch_dir, ignore_errors=True)

except Exception as e:                                              # noqa: BLE001
    chk(False, "[4]+[5] 프런트 실행/되돌림-증명", f"{type(e).__name__}: {e}")

chk(io.open(TPL_PATH, encoding="utf-8").read() == TPL_SRC,
    "★★★★★ insurer_portal.html은 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
