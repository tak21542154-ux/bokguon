# -*- coding: utf-8 -*-
"""스캔 502라운드 회귀 — VIEWS.dispatch(현장 출동 수배) 화면의 액션버튼
4형제 중 dispatchSweep(라운드337이 이미 등급게이트)만 빼고 dpOpen(수배
개시)·dpRetry(재수배)·dpAssignForm(직접 배정) 3곳이 등급 무관하게 그려지던
결함.

서버(app.py) 확인: /api/cases/<id>/dispatch(dpOpen·dpRetry 공용) ·
/api/cases/<id>/dispatch/assign(dpAssign) 둘 다 require_role("중간관리자")
— dispatchSweep의 /api/admin/dispatch-sweep와 같은 등급.

라운드337 자신의 설계의도(그 라운드 자신의 문서: "조회(목록) API는
require_admin(등급무관)이라 화면 자체는 계속 보이는 게 맞다 — 처리
버튼만 형제(coActions, 라운드252)처럼 자격 없으면 조용히 안내문/숨김
으로 바뀌어야 한다")를 그대로 확장한다 — 새 정책 발명이 아니라 337
자신이 "기한 점검 실행" 버튼 하나만 다루고 빠뜨린 같은 화면의 나머지
세 형제를 마저 채우는 것.
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


def chk(c, n, d=""):
    (PASS if c else FAIL).append((n, d))
    print(("  [OK]   " if c else "  [FAIL] ") + n + ("" if c else f"   {d}"))


print("=" * 72)
print("  스캔 502라운드 회귀 — 출동수배 화면 액션버튼 3형제 등급게이트 누락")
print("=" * 72)

JS_PATH = os.path.join(HERE, "static", "admin.js")
JS_SRC = io.open(JS_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 두 지점을 각각 독립적으로 추출(서로 안 겹침)")
# ──────────────────────────────────────────────────────────────
#  블록A: dpOpen 셀 — 우리가 직접 작성한 라운드502 주석을 시작 마커로,
#  그 뒤 첫 번째 </td> 를 끝 마커로 잡는다. </tr>`).join('')} 는 우리
#  편집 범위 밖(전후 그대로인 기존 코드)이라 블록에 포함하지 않는다.
CELL_CLOSE = "\n            }</td>"
A_START = '<td class="r">${\n              //  ⚠⚠ [라운드502] 형제(dispatchSweep'
a_start_idx = JS_SRC.index(A_START)
a_end_idx = JS_SRC.index(CELL_CLOSE, a_start_idx) + len(CELL_CLOSE)
BLOCK_A = JS_SRC[a_start_idx:a_end_idx]

#  블록B: dpRetry·dpAssignForm 공유 셀
B_START = '<td class="r" style="white-space:nowrap">${\n              //  ⚠⚠ [라운드502] 형제(dpOpen'
b_start_idx = JS_SRC.index(B_START)
b_end_idx = JS_SRC.index(CELL_CLOSE, b_start_idx) + len(CELL_CLOSE)
BLOCK_B = JS_SRC[b_start_idx:b_end_idx]

chk("myRank()>=2" in BLOCK_A and 'data-act="dpOpen"' in BLOCK_A,
    "블록A(dpOpen 셀)에 등급게이트가 있다")
chk(JS_SRC.count(BLOCK_A) == 1, "블록A가 소스에 유일하다", JS_SRC.count(BLOCK_A))
chk("myRank()>=2" in BLOCK_B and 'data-act="dpRetry"' in BLOCK_B and 'data-act="dpAssignForm"' in BLOCK_B,
    "블록B(dpRetry·dpAssignForm 셀)에 등급게이트가 있다")
chk(JS_SRC.count(BLOCK_B) == 1, "블록B가 소스에 유일하다", JS_SRC.count(BLOCK_B))

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 Node 실행 — 등급별로 실제 무엇이 렌더링되는지")
# ──────────────────────────────────────────────────────────────
NODE_SRC = r"""
function esc(s){ return String(s==null?'':s); }
function renderA(rank){
  const myRank = () => rank;
  const c = {id: 7};
  return `""" + BLOCK_A + r"""`;
}
function renderB(rank){
  const myRank = () => rank;
  const c = {id: 7, case_no: 'R502-1'};
  return `""" + BLOCK_B + r"""`;
}
const results = [];
for (const rank of [1, 2, 3]) {
  const ha = renderA(rank), hb = renderB(rank);
  results.push({
    rank,
    a_hasAct: ha.includes('data-act="dpOpen"'), a_hasNotice: ha.includes('중간관리자 이상만 처리할 수 있습니다'),
    b_hasRetry: hb.includes('data-act="dpRetry"'), b_hasAssign: hb.includes('data-act="dpAssignForm"'),
    b_hasNotice: hb.includes('중간관리자 이상만 처리할 수 있습니다'),
  });
}
console.log(JSON.stringify(results));
"""


def run_node():
    path = os.path.join(HERE, "_r502_node_tmp.js")
    io.open(path, "w", encoding="utf-8").write(NODE_SRC)
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True,
                            encoding="utf-8", timeout=20)
        if r.returncode != 0:
            raise RuntimeError(f"node 실행 실패: {r.stdout}\n{r.stderr}")
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


try:
    rows = run_node()
    for row in rows:
        expect = row["rank"] >= 2
        chk(row["a_hasAct"] == expect and row["a_hasNotice"] == (not expect),
            f"★★★★★ rank={row['rank']} → dpOpen(수배 개시) {'노출' if expect else '안내문 대체'}이어야 함", row)
        chk(row["b_hasRetry"] == expect and row["b_hasAssign"] == expect and row["b_hasNotice"] == (not expect),
            f"★★★★★ rank={row['rank']} → dpRetry·dpAssignForm(재수배·직접배정) "
            f"{'노출' if expect else '안내문 대체'}이어야 함", row)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2] Node 실행", f"{type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 되돌림-증명 — 옛 코드(등급게이트 없음)라면 하위관리자에게도 뜨는가")
# ──────────────────────────────────────────────────────────────
#  라운드502 이전 원문 그대로(각 블록 전체를 이 리터럴로 되돌린다).
ORIG_A = '<td class="r"><button class="btn p sm" data-act="dpOpen" data-arg="${c.id}">수배 개시</button></td>'
ORIG_B = ('''<td class="r" style="white-space:nowrap">
              <button class="btn g sm" data-act="dpRetry" data-arg="${c.id}" title="이전에 부른 곳도 다시 부릅니다">재수배</button>
              <button class="btn p sm" data-act="dpAssignForm" data-arg="${c.id}" data-arg2="${esc(c.case_no)}">직접 배정</button>
            </td>''')

try:
    # 3-1) 렌더 결과만으로 순수하게 되돌림-증명(디스크에 손대지 않음).
    OLD_NODE_SRC = r"""
function esc(s){ return String(s==null?'':s); }
function renderA(rank){
  const myRank = () => rank;
  const c = {id: 7};
  return `""" + ORIG_A + r"""`;
}
function renderB(rank){
  const myRank = () => rank;
  const c = {id: 7, case_no: 'R502-1'};
  return `""" + ORIG_B + r"""`;
}
console.log(JSON.stringify({
  rank1_a: renderA(1).includes('data-act="dpOpen"'),
  rank1_b_retry: renderB(1).includes('data-act="dpRetry"'),
  rank1_b_assign: renderB(1).includes('data-act="dpAssignForm"'),
}));
"""
    path = os.path.join(HERE, "_r502_node_old_tmp.js")
    io.open(path, "w", encoding="utf-8").write(OLD_NODE_SRC)
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True,
                            encoding="utf-8", timeout=20)
        if r.returncode != 0:
            raise RuntimeError(f"node 실행 실패: {r.stdout}\n{r.stderr}")
        old = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    chk(old["rank1_a"] and old["rank1_b_retry"] and old["rank1_b_assign"],
        "★★★★★ 옛 코드(되돌림): 하위관리자(rank=1)에게도 세 버튼이 전부 그대로 뜬다 — "
        "이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", old)

    # 3-2) 실제 파일 전체 문맥에서도 같은 되돌림이 문법적으로 말이 되는지 확인.
    #  ⚠⚠ [라운드627] 이전 버전은 이 되돌림을 실제 static/admin.js 파일에 직접
    #    썼다(io.open(JS_PATH,"w")) — node --check는 경로 인자를 받을 뿐이므로,
    #    tempfile 스크래치 사본에 되돌린 전체소스를 써서 그 경로를 검사한다
    #    (실제 파일은 이 단계에서도 전혀 안 건드린다).
    reverted = JS_SRC.replace(BLOCK_A, ORIG_A).replace(BLOCK_B, ORIG_B)
    assert reverted != JS_SRC, "되돌림 치환이 실제로 안 먹었다"
    _scratch_dir = tempfile.mkdtemp(prefix="r502_js_")
    try:
        _scratch_js = os.path.join(_scratch_dir, "admin.js")
        io.open(_scratch_js, "w", encoding="utf-8", newline="\n").write(reverted)
        rc = subprocess.run(["node", "--check", _scratch_js], capture_output=True,
                             text=True, encoding="utf-8", timeout=15)
        chk(rc.returncode == 0, "되돌린 admin.js 전체도 구문 오류가 없다", rc.stderr)
    finally:
        shutil.rmtree(_scratch_dir, ignore_errors=True)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[3] 되돌림-증명", f"{type(e).__name__}: {e}")

chk(io.open(JS_PATH, encoding="utf-8").read() == JS_SRC,
    "★★★★★ admin.js는 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
