# -*- coding: utf-8 -*-
"""스캔 637라운드 회귀(직접조사, 하위위임 없음) — 발주처 관리 화면(admin.js
VIEWS.insurers)의 요약 카드 4개가 데모 발주처를 실적에 그대로 합산하던 결함.

배경: round624~626이 바로 이 화면·이 API(GET /api/insurers?all=1)의 is_demo
배선을 연달아 고치면서 실측 남긴 값 그대로 — 운영DB(읽기전용, 2026-09-13)
재확인: 활성 발주처 7곳 중 6곳이 is_demo=1(실제 보험사명을 그대로 쓴 시연용
데이터), 실계약은 'R450검증손보' 1곳뿐이다. 목록 각 행에는 이미 회색 '데모'
표가 붙는데(round626이 실측 근거로 인용한 그 표), 정작 화면 맨 위 요약 카드
넷("등록 발주처"·"계약 체결"·"포털 계정"·"평균 계약 요율")은 고침 전에는
`data`(all=1 전체, 데모 포함) 를 그대로 세고 있었다 — "평균 계약 요율"이
실계약 1곳이 아니라 데모 6곳까지 섞인 값으로 떴다(이번 실측: 9.9% vs 실제
10.0%. 데모 요율이 우연히 실계약과 비슷해 차이가 작아 보이지만, 등록/활성
발주처 수 자체는 7 vs 실제 1로 7배 부풀어 있었다 — 데모가 하나라도 다른
요율을 갖게 바뀌면 평균도 그만큼 더 벌어진다). 이 코드베이스 전체가
지키는 "데모는 실적 집계에서 뺀다"는 원칙(대시보드·KPI·v1 API 등 여러
곳 — round636 AWARD_CONFIRMED_SQL 계열, round624~626 is_demo 배선 등)이
이 화면 요약 카드에는 미치지 못했던 사각지대다.

고침(static/admin.js, VIEWS.insurers):
  const act = data.filter(i=>i.status==='활성');
        ↓
  const real = data.filter(i=>!i.is_demo);
  const act = real.filter(i=>i.status==='활성');
그리고 "계약 체결"·"포털 계정" 카드도 data.filter(...) → real.filter(...) 로.
목록 표(행마다 '데모' 표)는 그대로 data 전체를 보여준다 — 요약 숫자만 고쳤다.

검증 순서:
  [1] 소스 확인 — 고친 두 줄이 실제로 있고, 옛(버그) 줄과 옛 data.filter 형태가
      VIEWS.insurers 안에 더는 없다(round253 이 확립한 함수경계 슬라이스 재사용).
  [2] Node 실행(실제 파일에서 그대로 뽑은 계산식+krow 템플릿을 통째로 실행) —
      운영DB 실측과 같은 모양의 목데이터(활성 7곳 중 6곳 데모)를 넣어
      "등록 발주처=1·활성=1·평균 요율=10.0%"이 실제로 나오는지 확인한다.
  [3] 되돌림-증명 — **admin.js 는 이 세션 내내 단 한 바이트도 건드리지 않는다.**
      옛(버그) 코드를 별도의 임시 스크래치 .js 파일(round626이 확립한 기법 —
      실제 저장소 파일이 아닌 tempfile.mkdtemp() 산출물)에 손으로 재현해 같은
      목데이터로 실행하면 "등록 발주처=7·평균 요율=9.9%" 로 실제로 새는 것을
      보여준다 — 이 테스트가 진짜로 결함을 잡아낼 능력이 있음을 증명한다.

    python test_scan_round637_fixes.py
"""
import io
import os
import sys
import json
import shutil
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(c, n, d=""):
    (PASS if c else FAIL).append((n, d))
    print(("  [OK]   " if c else "  [FAIL] ") + n + ("" if c else f"   {d}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


ADMIN_JS_PATH = os.path.join(HERE, "static", "admin.js")
ADMIN_JS_BEFORE = read("static/admin.js")

print("=" * 72)
print("  스캔 637라운드 회귀 — 발주처 요약 카드가 데모 발주처까지 실적에 합산")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — VIEWS.insurers 함수 경계 안에서만 본다(round253 기법)")
# ──────────────────────────────────────────────────────────────
i0 = ADMIN_JS_BEFORE.index("VIEWS.insurers = async () => {")
i1 = ADMIN_JS_BEFORE.index("\n};", i0)
INS_VIEW = ADMIN_JS_BEFORE[i0:i1]

NEW_REAL_LINE = "const real = data.filter(i=>!i.is_demo);"
NEW_ACT_LINE = "const act = real.filter(i=>i.status==='활성');"
OLD_ACT_LINE = "const act = data.filter(i=>i.status==='활성');"

chk(NEW_REAL_LINE in INS_VIEW,
    "★★★★★ 데모를 뺀 real 목록을 새로 만든다")
chk(NEW_ACT_LINE in INS_VIEW,
    "★★★★★ act(활성)는 이제 real 에서 뽑는다(data 아님)")
chk(OLD_ACT_LINE not in INS_VIEW,
    "★★★★★ 옛(버그) 줄 — data 를 직접 세는 act 선언이 더는 없다")
chk("real.filter(i=>i.contract_status==='계약중')" in INS_VIEW,
    "★★★★ '계약 체결' 카드도 real 기준(데모 제외)")
chk("real.filter(i=>i.login_id)" in INS_VIEW,
    "★★★★ '포털 계정' 카드도 real 기준(데모 제외)")
chk("data.filter(i=>i.contract_status==='계약중')" not in INS_VIEW
    and "data.filter(i=>i.login_id)" not in INS_VIEW,
    "★★★★★ '계약 체결'·'포털 계정' 카드에 옛(data 직접) 형태가 남아있지 않다")
chk("${real.length}" in INS_VIEW and "활성 ${act.length}곳" in INS_VIEW,
    "STEP '등록 발주처' 카드가 real.length 를 보여준다")

# ══════════════════════════════════════════════════════════════
print("\n[2] Node 실행 — 실제 파일에서 그대로 뽑은 계산식+krow 템플릿을 통째로 실행")
# ──────────────────────────────────────────────────────────────
#  bpPct 도 손으로 다시 안 적고 실제 정의를 그대로 뽑는다(house 관례 — round626 과 같음).
bp_i = ADMIN_JS_BEFORE.index("const bpPct = ")
bp_line = ADMIN_JS_BEFORE[bp_i:ADMIN_JS_BEFORE.index("\n", bp_i)]
chk(bp_line.startswith("const bpPct = ") and bp_line.endswith(";"),
    "STEP bpPct 정의를 소스에서 그대로 뽑았다", bp_line)

krow_start = ADMIN_JS_BEFORE.index('<div class="krow k4">', i0)
krow_end = ADMIN_JS_BEFORE.index('\n    <div class="panel">', krow_start)
KROW_TPL = ADMIN_JS_BEFORE[krow_start:krow_end]
chk("평균 계약 요율" in KROW_TPL and "${real.length}" in KROW_TPL,
    "STEP krow 템플릿 블록을 정확한 경계로 뽑았다(다음 panel 앞까지)")

#  운영DB 실측(2026-09-13, 읽기전용 SELECT)과 정확히 같은 모양 — 활성 7곳 중
#  6곳이 is_demo=1, 진짜 계약은 id=50 (R450검증손보) 한 곳뿐이다.
MOCK_DATA = [
    {"id": 1, "name": "OO손보", "status": "활성", "is_demo": 1,
     "fee_rate_bp": 1000, "contract_status": "계약중", "login_id": "insurer"},
    {"id": 2, "name": "XX화재", "status": "활성", "is_demo": 1,
     "fee_rate_bp": 1000, "contract_status": "시범운영", "login_id": None},
    {"id": 3, "name": "메리츠화재", "status": "활성", "is_demo": 1,
     "fee_rate_bp": 1000, "contract_status": "계약중", "login_id": None},
    {"id": 4, "name": "DB손보", "status": "활성", "is_demo": 1,
     "fee_rate_bp": 1000, "contract_status": "계약중", "login_id": None},
    {"id": 5, "name": "KB손보", "status": "활성", "is_demo": 1,
     "fee_rate_bp": 1000, "contract_status": "계약중", "login_id": None},
    {"id": 6, "name": "공제조합", "status": "활성", "is_demo": 1,
     "fee_rate_bp": 900, "contract_status": "계약중", "login_id": None},
    {"id": 50, "name": "R450검증손보", "status": "활성", "is_demo": 0,
     "fee_rate_bp": 1000, "contract_status": "계약중", "login_id": "r450ins"},
]


def _extract_v(html):
    """krow 템플릿이 뱉은 HTML에서 <div class="v"> 안의 숫자 텍스트 4개를 순서대로
    뽑는다. 값 뒤에 <small>단위</small>가 바로 붙어 있어(같은 div 안, 내부 태그),
    </div> 까지 통째로 보면 '1<small>곳</small>'처럼 단위 태그까지 딸려온다 —
    다음 태그(<small) 시작 전까지, 즉 순수 텍스트만 자른다."""
    import re
    return re.findall(r'<div class="v">([^<]*)', html)


def _run_node(script_text, label):
    tmpdir = tempfile.mkdtemp(prefix="r637js_")
    tmpjs = os.path.join(tmpdir, "check.js")
    io.open(tmpjs, "w", encoding="utf-8").write(script_text)
    try:
        r = subprocess.run(["node", tmpjs], capture_output=True, text=True,
                            encoding="utf-8", timeout=20)
        if r.returncode != 0:
            raise RuntimeError(f"{label} 실행 실패: {r.stdout}\n{r.stderr}")
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


FIXED_SCRIPT = f"""
{bp_line}
const data = {json.dumps(MOCK_DATA, ensure_ascii=False)};
{NEW_REAL_LINE}
{NEW_ACT_LINE}
const html = `{KROW_TPL}`;
console.log(JSON.stringify(html));
"""

try:
    fixed_html = _run_node(FIXED_SCRIPT, "고친 코드")
    vals = _extract_v(fixed_html)
    chk(len(vals) == 4, "★ krow 렌더 실행이 카드 4개를 돌려줬다", vals)
    if len(vals) == 4:
        reg, contract, portal, avg = vals
        chk(reg == "1",
            "★★★★★ 새 코드: '등록 발주처' 카드가 데모 6곳을 빼고 실제 1곳만 센다",
            f"got {reg!r}, want '1'")
        chk("활성 1곳" in fixed_html,
            "★★★★★ 새 코드: '활성 N곳' 서브라벨도 1곳(데모 제외)")
        chk(contract == "1",
            "★★★★ 새 코드: '계약 체결' 카드도 실제 1곳만 센다", f"got {contract!r}")
        chk(portal == "1",
            "★★★★ 새 코드: '포털 계정' 카드도 실제 1곳만 센다", f"got {portal!r}")
        chk(avg == "10.0",
            "★★★★★ 새 코드: '평균 계약 요율'이 데모 6곳 안 섞고 실계약(10.0%)만 반영",
            f"got {avg!r}, want '10.0'")
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2] 고친 코드 Node 실행", f"{type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 되돌림-증명 — admin.js 는 안 건드리고, 별도 스크래치 .js 에서만 옛 코드를 재현")
# ──────────────────────────────────────────────────────────────
#  ⚠ 이 문자열은 admin.js 어디에도 안 쓰인다 — round626 이 확립한 기법 그대로
#    tempfile.mkdtemp() 산출물(저장소 밖 임시 파일)에만 쓰고 끝나면 지운다.
BROKEN_SCRIPT = f"""
{bp_line}
const data = {json.dumps(MOCK_DATA, ensure_ascii=False)};
{OLD_ACT_LINE}
const html = `{KROW_TPL.replace("real.length", "data.length").replace("real.filter", "data.filter")}`;
console.log(JSON.stringify(html));
"""

try:
    broken_html = _run_node(BROKEN_SCRIPT, "옛(되돌린) 코드")
    bvals = _extract_v(broken_html)
    chk(len(bvals) == 4, "STEP (되돌림) 렌더 실행이 카드 4개를 돌려줬다", bvals)
    if len(bvals) == 4:
        breg, bcontract, bportal, bavg = bvals
        chk(breg == "7",
            "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림): "
            "데모 6곳까지 합쳐 '등록 발주처'가 7로 부풀려 재현된다"
            " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
            f"got {breg!r}")
        chk(bavg == "9.9",
            "★★★★★ 옛 코드(되돌림): '평균 계약 요율'도 9.9%로 실제와 다르게 샌다"
            "(실제 10.0% — 데모 6곳의 요율이 섞여 왜곡)",
            f"got {bavg!r}, want '9.9'")
        chk(breg != "1" and bavg != "10.0",
            "★★★★★ 되돌린 결과가 고친 결과(1 / 10.0%)와 실제로 다르다"
            "(두 코드가 진짜 다른 답을 낸다는 뜻)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "[3] 되돌림 Node 실행", f"{type(e).__name__}: {e}")

chk(read("static/admin.js") == ADMIN_JS_BEFORE,
    "★★★★★ admin.js는 이 테스트 실행 내내 단 한 바이트도 안 바뀌었다"
    "(계산은 전부 저장소 밖 임시 .js 파일에서만 했다)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
