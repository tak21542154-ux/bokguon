# -*- coding: utf-8 -*-
"""스캔 626라운드 회귀 — GET /api/insurers 기본 모드(사건 등록·정산명세서
드롭다운용, ?all=1 아님)가 is_demo 를 안 담아 관리자가 데모 발주처를
구분할 방법이 전혀 없던 결함, 2건(백엔드 1 + 프런트 2자리).

  직접조사(하위위임 없음) — round624/625가 "cases.is_demo가 발주처 기준을
  정확히 반영해야 한다"는 불변식을 세운 뒤, 그 불변식이 정말 다른 모든
  관련 경로에도 지켜지는지 확인하다가 round625 자신의 되돌림-증명
  근거("admin.js의 발주처 드롭다운(createCase)은 is_demo 필터가 전혀
  없다")를 실제로 파고들어 발견 — round625는 이 사실을 DB 저장값
  일관성(cases.is_demo)의 근거로만 썼을 뿐, 화면에 실제로 표시가
  빠졌다는 사실 자체는 고치지 않고 남겨 뒀다.

  근거(전부 이 세션이 grep+Read로 직접 확인):
    · api_insurers_list()(app.py) 의 기본 모드(all=1 아님) SELECT는
      "id, name, org_type, fee_rate_bp, contract_status" 뿐 — is_demo가
      아예 없다. 자기 docstring이 "기본은 사건 등록 드롭다운용"이라고
      스스로 밝히고 있다.
    · all=1 모드(발주처 관리 화면 전용, 최고관리자만)는 이미 i.is_demo를
      담고, admin.js 발주처 목록(2659행 부근)은 그 값으로 회색 '데모' 표를
      붙인다 — 같은 개념을 이미 한 화면은 보여주는데 다른 화면은 안 보여줌.
    · 이 기본 모드를 쓰는 프런트 자리는 정확히 둘(admin.js): ①createCase
      의 발주처 <select id="c_ins">(1779행 부근) ②월 정산 명세서의
      발주처 <select id="st_ins">(5168행 부근) — 이 세션이 grep으로
      `/api/insurers'` 호출부 전수(1755·2824·5156행)를 대조해 2824는
      POST(등록)라 무관함을 확인, GET 은 이 둘뿐임을 확정.
    · 운영 DB(읽기전용 조회) — 지금 활성 발주처 7곳 중 6곳이 is_demo=1
      이고 전부 실제 손해보험사명(DB손보·KB손보·메리츠화재 등)을 그대로
      쓴 데모 데이터라, 관리자가 이 드롭다운만 보고는 어느 게 실제
      계약처인지 전혀 구분할 수 없다 — 이론적 위험이 아니라 지금 이
      순간의 실제 상태.

  round624/625가 이미 데이터 자체(cases.is_demo)는 발주처 기준으로
  정확히 심도록 고쳐 놓았으므로 통계·정산 집계가 새는 위험은 없다 —
  이 결함은 "사람이 고르는 순간 아무 경고가 없다"는 절차적 위험이다
  (엉뚱한 발주처를 골라 시간을 낭비하거나, 데모인 줄 모르고 실제
  업무처럼 다루는 혼동).

  고침: 새 컬럼·새 정책·새 API 없음 — 이미 있는 컬럼을 이미 있는
  자리에 노출만 한다.
    (a) 백엔드 — 기본 모드 SELECT에 i.is_demo 추가(별칭 없이 그대로,
        all=1 모드와 같은 컬럼명).
    (b) 프런트 — 두 <option> 렌더에 `i.is_demo?' [데모]':''` 를
        이름 뒤에 붙인다(옵션 태그는 HTML을 못 담으므로 목록화면의
        <span class="pill gray"> 대신 대괄호 평문 표기 — select 드롭다운의
        관용적 표기).

  [1] 소스 확인 — 새 SELECT·새 옵션 렌더 두 곳이 실제로 있음.
  [2] 실제 Flask 서브프로세스(관리자 세션) — 데모 발주처 1곳 + 실제
      발주처 1곳을 심고 GET /api/insurers(기본 모드)를 실제로 호출해
      응답 JSON에 is_demo가 정확한 값으로 담기는지 확인.
  [3] 실제 Node vm 실행 — admin.js의 두 옵션 렌더 표현식을 그대로 뽑아
      실행해, 데모 발주처는 "[데모]"가 옵션 텍스트에 실제로 붙고 실제
      발주처는 안 붙는지 확인.
  [4] 되돌림-증명 — 백엔드는 기법1(view_functions 스왑, R626_BROKEN
      환경변수로 워커 서브프로세스 안에서만 트리거), 프런트는 스크래치
      메모리 문자열로 옛 표현식을 재구성해 Node로 실행 — 둘 다 실제
      app.py·admin.js 파일은 전혀 안 건드린다.
"""
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(HERE, "app.py")
JS_PATH = os.path.join(HERE, "static", "admin.js")
WORKER = os.path.join(HERE, "test_scan_round626_worker.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 626라운드 회귀 — /api/insurers 기본모드 is_demo 노출 누락(드롭다운 2곳)")
print("=" * 72)

APP_SRC = io.open(APP_PATH, encoding="utf-8").read()
JS_SRC = io.open(JS_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
NEW_SELECT = ('"SELECT id, name, org_type, fee_rate_bp, contract_status, is_demo FROM insurers "\n'
              '            "WHERE status=\'활성\' ORDER BY name"))')
OLD_SELECT = ('"SELECT id, name, org_type, fee_rate_bp, contract_status FROM insurers "\n'
              '            "WHERE status=\'활성\' ORDER BY name"))')
chk(APP_SRC.count(NEW_SELECT) == 1,
    "★★★★★ api_insurers_list() 기본모드 SELECT에 is_demo가 정확히 1번 추가돼 있다",
    APP_SRC.count(NEW_SELECT))
chk(OLD_SELECT not in APP_SRC, "옛(is_demo 없는) SELECT는 더 이상 없다")

NEW_OPT_CREATE = "${i.is_demo?' [데모]':''}"
NEW_OPT_STMT = "${x.is_demo?' [데모]':''}"
chk(NEW_OPT_CREATE in JS_SRC, "★★★★★ createCase 발주처 드롭다운에 데모 표기가 있다")
chk(NEW_OPT_STMT in JS_SRC, "★★★★★ 월 정산 명세서 발주처 드롭다운에 데모 표기가 있다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 Flask 서브프로세스 — 데모/실제 발주처 각각 is_demo 노출 확인")
# ──────────────────────────────────────────────────────────────


def _run_worker(broken=False):
    """broken=True 면 워커 서브프로세스 안에서 기법1(view_functions 스왑)로
    api_insurers_list 기본모드를 되돌린 버전으로 바꿔치기하고 실행한다
    (R626_BROKEN 환경변수) — 실제 app.py 파일은 전혀 안 건드린다."""
    env = dict(os.environ)
    if broken:
        env["R626_BROKEN"] = "1"
    r = subprocess.run([sys.executable, "-u", WORKER], capture_output=True,
                        text=True, encoding="utf-8", timeout=60, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"워커 실행 실패(rc={r.returncode}): {r.stdout}\n{r.stderr}")
    return json.loads(r.stdout.strip().splitlines()[-1])


try:
    fixed = _run_worker()
    chk(fixed.get("status") == 200, "GET /api/insurers 기본모드 200", fixed.get("status"))
    demo_row = next((x for x in fixed.get("body", []) if x.get("name") == "R626데모보험"), None)
    real_row = next((x for x in fixed.get("body", []) if x.get("name") == "R626실보험"), None)
    chk(demo_row is not None and real_row is not None,
        "데모·실제 발주처 둘 다 목록에 있다", fixed.get("body"))
    chk(bool(demo_row and demo_row.get("is_demo")),
        "★★★★★ 새 코드: 데모 발주처 행에 is_demo=1(참)이 실제로 담긴다", demo_row)
    chk(bool(real_row and not real_row.get("is_demo")),
        "★★★★★ 새 코드: 실제 발주처 행은 is_demo가 없거나 거짓이다", real_row)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2] 워커 실행", f"{type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] Node 실행 — admin.js 두 옵션 렌더 표현식을 그대로 실행")
# ──────────────────────────────────────────────────────────────


def _extract_option_expr(marker_after_i_id):
    """`<option value="${X.id}"...` 로 시작하는 template literal 하나를
    그 X.id 자리 뒤 첫 </option> 까지 그대로 뽑는다."""
    i = JS_SRC.find(marker_after_i_id)
    assert i > 0, f"마커를 못 찾음: {marker_after_i_id}"
    start = JS_SRC.rfind("`<option", 0, i + 40)
    end = JS_SRC.find("</option>`", start) + len("</option>`")
    return JS_SRC[start:end]


CREATE_OPT_TPL = _extract_option_expr('<option value="${i.id}">')
STMT_OPT_TPL = _extract_option_expr('<option value="${x.id}"')
chk(NEW_OPT_CREATE in CREATE_OPT_TPL, "createCase 옵션 템플릿을 정확히 뽑았다(데모표기 포함)")
chk(NEW_OPT_STMT in STMT_OPT_TPL, "정산명세서 옵션 템플릿을 정확히 뽑았다(데모표기 포함)")


def _node_render(tpl_src, var_name, payload):
    node_script = f"""
function esc(s){{ return String(s==null?'':s); }}
function bpPct(bp){{ return (bp/100).toFixed(2); }}
const STMT = {{insurer_id: ''}};
function render({var_name}) {{
  return ({tpl_src});
}}
console.log(JSON.stringify({json.dumps(payload)}.map(render)));
"""
    tmpjs = os.path.join(tempfile.mkdtemp(prefix="r626js_"), "check.js")
    io.open(tmpjs, "w", encoding="utf-8").write(node_script)
    try:
        r = subprocess.run(["node", tmpjs], capture_output=True, text=True, encoding="utf-8", timeout=20)
        if r.returncode != 0:
            raise RuntimeError(r.stdout + r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        import shutil
        shutil.rmtree(os.path.dirname(tmpjs), ignore_errors=True)


PAYLOAD = [{"id": 1, "name": "R626실보험", "fee_rate_bp": None, "is_demo": 0},
           {"id": 2, "name": "R626데모보험", "fee_rate_bp": None, "is_demo": 1}]

try:
    out_create = _node_render(CREATE_OPT_TPL, "i", PAYLOAD)
    chk(len(out_create) == 2, "★ createCase 렌더 실행이 2건을 돌려줬다", out_create)
    if len(out_create) == 2:
        chk("[데모]" not in out_create[0] and "R626실보험" in out_create[0],
            "★★★★★ 실제 발주처 옵션에는 [데모] 표기가 없다", out_create[0])
        chk("[데모]" in out_create[1] and "R626데모보험" in out_create[1],
            "★★★★★ 데모 발주처 옵션에는 [데모] 표기가 실제로 붙는다", out_create[1])

    out_stmt = _node_render(STMT_OPT_TPL, "x", PAYLOAD)
    chk(len(out_stmt) == 2, "★ 정산명세서 렌더 실행이 2건을 돌려줬다", out_stmt)
    if len(out_stmt) == 2:
        chk("[데모]" not in out_stmt[0], "실제 발주처 옵션(정산명세서)에는 [데모] 표기가 없다", out_stmt[0])
        chk("[데모]" in out_stmt[1], "★★★★★ 데모 발주처 옵션(정산명세서)에는 [데모] 표기가 붙는다", out_stmt[1])
except Exception as e:                                              # noqa: BLE001
    chk(False, "[3] Node 렌더 실행", f"{type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌림-증명 — 백엔드(워커 안 인메모리)+프런트(스크래치 메모리) 둘 다 재현")
# ──────────────────────────────────────────────────────────────
try:
    broken = _run_worker(broken=True)
    b_demo = next((x for x in broken.get("body", []) if x.get("name") == "R626데모보험"), None)
    chk(broken.get("status") == 200, "옛 코드(되돌림)도 200 자체는 그대로 낸다(구조는 안 바뀜)")
    chk(b_demo is not None and not b_demo.get("is_demo"),
        "★★★★★ 옛 코드(되돌림): 데모 발주처 행에도 is_demo 키가 없거나 거짓 — "
        "이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", b_demo)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[4] 백엔드 되돌림-증명", f"{type(e).__name__}: {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py는 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일)")

try:
    reverted_create_tpl = CREATE_OPT_TPL.replace(NEW_OPT_CREATE, "", 1)
    reverted_stmt_tpl = STMT_OPT_TPL.replace(NEW_OPT_STMT, "", 1)
    assert reverted_create_tpl != CREATE_OPT_TPL and reverted_stmt_tpl != STMT_OPT_TPL
    broken_create = _node_render(reverted_create_tpl, "i", PAYLOAD)
    broken_stmt = _node_render(reverted_stmt_tpl, "x", PAYLOAD)
    chk("[데모]" not in broken_create[1],
        "★★★★★ 옛 코드(되돌림): createCase 옵션은 데모 발주처도 표기 없이 보여준다"
        " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", broken_create[1])
    chk("[데모]" not in broken_stmt[1],
        "★★★★★ 옛 코드(되돌림): 정산명세서 옵션도 데모 발주처를 표기 없이 보여준다",
        broken_stmt[1])
except Exception as e:                                              # noqa: BLE001
    chk(False, "[4] 프런트 되돌림-증명", f"{type(e).__name__}: {e}")

chk(io.open(JS_PATH, encoding="utf-8").read() == JS_SRC,
    "★★★★★ admin.js는 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
