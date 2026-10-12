# -*- coding: utf-8 -*-
"""스캔 337라운드 회귀 — 정산·하자·출동수배 3개 화면의 등급 무관 처리버튼
   (admin.js 화면군 Agent 조사로 발견, 246~253라운드 등급게이트 전수 스윕이
   settle 화면 자체를 안 훑고 지나갔고, defects·dispatch 는 205라운드가
   try/catch 만 붙이고 정작 등급게이트는 못 붙인 채 남겨 둔 결함).

  [1] VIEWS.settle 의 settleAction() — 버튼 6개(입금확인·더블체크승인·
      되돌리기=중간관리자, 정산취소·이체완료=최고관리자, app.py 12529·13409·
      13297·13211·12625행)가 등급 무관하게 그려졌다. coActions()(252라운드)와
      달리 버튼별 필요등급이 2/3 으로 갈려 함수 전체를 한 번에 막을 수 없다 —
      버튼마다 개별로 myRank() 를 확인하도록 수정. 일괄 입금확인 바·체크박스
      열(payable/paybar, /api/settlements/paid-bulk=중간관리자)도 같은 사유로
      canBulk 로 새로 게이트.

  [2] defectDetail() 의 모달 하단 처리버튼 5개(확인중·재시공배정·완료·반려·
      완료취소) — PATCH /api/defects/<id> 는 require_role(중간관리자,
      app.py:13846)인데 이 화면(하자·A/S 관리) 메뉴는 applyRoleMenus() 의
      등급게이트에 없어 하위관리자도 열 수 있었다. 205라운드가 try/catch 는
      붙였지만(언핸들드 리젝션 방지) 등급게이트 자체는 못 붙였다.

  [3] VIEWS.dispatch 의 "기한 점검 실행"(dispatchSweep) 버튼 — POST
      /api/admin/dispatch-sweep 는 require_role(중간관리자, app.py:16978)
      인데 등급 무관하게 그려졌고, 과기한 건이 있으면 강조색(btn p)까지
      입혀 하위관리자에게도 클릭을 권했다.

  세 곳 다 조회(목록) API 는 require_admin(등급무관)이라 화면 자체는 계속
  보이는 게 맞다 — 처리 버튼만 형제(coActions, 252라운드)처럼 자격 없으면
  조용히 안내문/숨김으로 바뀌어야 한다.

      python test_scan_round337_fixes.py
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


def run_node(src, tag):
    node_path = os.path.join(tempfile.gettempdir(), f"r337_{tag}.js")
    io.open(node_path, "w", encoding="utf-8").write(src)
    try:
        r = subprocess.run(["node", node_path], capture_output=True, text=True,
                            encoding="utf-8", timeout=20)
        if r.returncode != 0:
            chk(False, f"★★★ Node 실행({tag})", r.stderr[-800:])
            return None
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:                                              # noqa: BLE001
        chk(False, f"★★★ Node 준비({tag})", f"{type(e).__name__} {e}")
        return None
    finally:
        try: os.remove(node_path)
        except OSError: pass


ADMIN_JS = read("static/admin.js")
APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 337라운드 회귀 — 정산·하자·출동수배 처리버튼 등급게이트")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — 백엔드 필요등급 재확인 + 프론트 게이트 존재 확인")
# ============================================================
chk('@app.post("/api/settlements/<int:sid>/paid")\n@require_role("중간관리자")' in APP_SRC,
    "(사전조건) 입금확인은 중간관리자 이상")
chk('@app.post("/api/settlements/<int:sid>/transfer")\n@require_role("최고관리자")' in APP_SRC,
    "(사전조건) 이체완료는 최고관리자 전용")
chk('@app.post("/api/settlements/<int:sid>/void")\n@require_role("최고관리자")' in APP_SRC,
    "(사전조건) 정산취소는 최고관리자 전용")
chk('@app.patch("/api/defects/<int:did>")' in APP_SRC and '@require_role("중간관리자")\ndef api_defect_update' in APP_SRC,
    "(사전조건) 하자 처리는 중간관리자 이상")
chk('@app.post("/api/admin/dispatch-sweep")\n@require_role("중간관리자")' in APP_SRC,
    "(사전조건) 출동수배 기한점검은 중간관리자 이상")

i0 = ADMIN_JS.index("function settleAction(s){")
i1 = ADMIN_JS.index("\nasync function settleVoid(", i0)
settle_body = ADMIN_JS[i0:i1]
chk("const rank = myRank();" in settle_body, "★★★★ settleAction() 이 등급을 실제로 읽는다")
chk(settle_body.count("rank >= 2") >= 1 and settle_body.count("rank >= 3") >= 2,
    "★★★★ 버튼별로 2등급·3등급 기준이 각각 적용된다", settle_body.count("rank >= 2"))

i1b = ADMIN_JS.index("const canBulk = myRank() >= 2 && payable.length;")
i1c = ADMIN_JS.index("\n// 보험사에 완료승인을", i1b)
bulk_snip = ADMIN_JS[i1b:i1c]
chk("const canBulk = myRank() >= 2 && payable.length;" in ADMIN_JS,
    "★★★★ 일괄 입금확인 바(paid-bulk)도 등급을 확인하는 canBulk 로 게이트된다")
chk(bulk_snip.count("canBulk?") >= 3,
    "STEP 그 canBulk 가 바·체크박스 열·행별 체크박스 3곳 모두에 실제로 쓰인다",
    bulk_snip.count("canBulk?"))
chk("payable.length?" not in bulk_snip,
    "STEP 등급 미확인 옛 조건(payable.length?)이 그 자리에 안 남아 있다")

i2 = ADMIN_JS.index("function defectDetail(id){")
i3 = ADMIN_JS.index("\nasync function loadDefectPhotos(", i2)
defect_body = ADMIN_JS[i2:i3]
chk("myRank()<2 ?" in defect_body, "★★★★ defectDetail() 모달 하단이 등급을 확인한다")

i4 = ADMIN_JS.index("VIEWS.dispatch = async () => {")
i5 = ADMIN_JS.index("기한 점검 실행", i4)
dispatch_snip = ADMIN_JS[i4:i5 + 300]
dispatch_line = dispatch_snip[dispatch_snip.index("${myRank()>=2?"):].split("\n")[0]
chk("myRank()>=2?" in dispatch_snip, "★★★★ 출동수배 화면의 기한점검 버튼이 등급을 확인한다")
chk(dispatch_line.rstrip().endswith(":''}"),
    "(사전조건) 추출한 한 줄이 그 줄 끝(:''})까지 온전히 잡혔다", dispatch_line)

# ============================================================
print("\n[2] 실행(Node) — settleAction() 이 등급·상태별로 실제 뭘 그리는지")
# ============================================================
node_src = r"""
function esc(s){ return String(s==null?'':s); }
function settleAction(s, _rank){
  const myRank = () => _rank;
""" + settle_body[settle_body.index("\n", settle_body.index("function settleAction(s){")) + 1:] + r"""
const base = {id:1, case_no:'R337-1', partner_name:'R337업체'};
const scenarios = [
  {stage:0, ...base, insurer_approved:0, insurer_paid:null, review_status:null},           // 승인대기 단계 — voidBtn 만 가능
  {stage:1, ...base, insurer_approved:1, insurer_paid:null, review_status:null},           // 입금확인 단계
  {stage:2, ...base, insurer_approved:1, insurer_paid:'입금완료', review_status:'대기'},    // 더블체크 단계
  {stage:3, ...base, insurer_approved:1, insurer_paid:'입금완료', review_status:'승인'},    // 이체 단계
];
const acts = ['settlePaid', 'settleReview', 'settleTransfer', 'settleVoid', 'settleUndo'];
const results = [];
for (const s of scenarios){
  for (const rank of [1, 2, 3]){
    const html = settleAction(s, rank);
    const row = {stage: s.stage, rank};
    for (const act of acts) row[act] = html.includes(`data-act="${act}"`);
    results.push(row);
  }
}
console.log(JSON.stringify(results));
"""
rows = run_node(node_src, "settleaction")
if rows is not None:
    #  ★ settleAction() 은 각 정산 건의 "지금 단계"에 맞는 주버튼 딱 하나만 낸다
    #    (state 로 정해짐) — 등급은 그 안에서 노출 여부만 가른다. 그래서 기대값은
    #    "이 버튼은 등급req 이상"이 아니라 "이 단계+등급 조합에서 이 버튼이 뜨는가"다.
    #    voidBtn(canVoid)·undo 는 state 조건이 별개(app.py 로직과 동일하게 재현).
    def expect_row(stage, rank):
        can_void = stage in (0, 1)          # insurer_paid!=입금완료 && review_status!=승인
        undo_cond = stage in (2, 3)         # insurer_paid==입금완료 || review_status==승인
        primary = {0: None, 1: "settlePaid", 2: "settleReview", 3: "settleTransfer"}[stage]
        primary_need = {1: 2, 2: 2, 3: 3}.get(stage)
        return {
            "settlePaid": stage == 1 and rank >= 2,
            "settleReview": stage == 2 and rank >= 2,
            "settleTransfer": stage == 3 and rank >= 3,
            "settleVoid": can_void and rank >= 3,
            "settleUndo": undo_cond and rank >= 2,
        }

    for row in rows:
        exp = expect_row(row["stage"], row["rank"])
        for act in ("settlePaid", "settleReview", "settleTransfer", "settleVoid", "settleUndo"):
            chk(row[act] == exp[act],
                f"★★★★ stage={row['stage']} rank={row['rank']} {act} → "
                f"{'노출' if exp[act] else '숨김'}이어야 함", row)
    #  ★ 하위관리자(rank1)는 어느 단계에서도 처리 버튼을 전혀 못 본다(대조군)
    r1_rows = [r for r in rows if r["rank"] == 1]
    acts5 = ("settlePaid", "settleReview", "settleTransfer", "settleVoid", "settleUndo")
    chk(all(not any(r[a] for a in acts5) for r in r1_rows),
        "★★★★★ 하위관리자는 어느 단계에서도 처리 버튼을 전혀 못 본다")
    #  ★ 최고관리자(rank3)는 각 단계에서 해당 주버튼을 실제로 본다(과잉차단 아님)
    r3 = {r["stage"]: r for r in rows if r["rank"] == 3}
    chk(r3[1]["settlePaid"] and r3[2]["settleReview"] and r3[3]["settleTransfer"],
        "★★★ 최고관리자는 단계별 주버튼을 정상적으로 본다(과잉차단 아님)")

# ============================================================
print("\n[3] 실행(Node) — defectDetail() 모달이 등급별로 실제 뭘 그리는지")
# ============================================================
node_src2 = r"""
function esc(s){ return String(s==null?'':s); }
function statusPill(){ return ''; }
let CAPTURED = '';
function openModal(html){ CAPTURED = html; }
function loadDefectPhotos(){}
const document = { getElementById: () => null };
let window = {};
""" + defect_body + r"""
const results = [];
for (const rank of [1, 2, 3]){
  for (const done of [false, true]){
    window._defects = [{id:1, title:'t', defect_no:'D1', case_no:'C1', status: done?'완료':'확인중',
      severity:'보통', warranty_left:10, cost_bearer:'시행사'}];
    globalThis.myRank = () => rank;
    CAPTURED = '';
    defectDetail(1);
    results.push({rank, done, hasAct: CAPTURED.includes('data-act="defectAct"'),
      hasNotice: CAPTURED.includes('중간관리자 이상만 처리할 수 있습니다')});
  }
}
console.log(JSON.stringify(results));
"""
rows2 = run_node(node_src2, "defectdetail")
if rows2 is not None:
    for row in rows2:
        expect = row["rank"] >= 2
        chk(row["hasAct"] == expect,
            f"★★★★ rank={row['rank']} done={row['done']} → 처리버튼 {'노출' if expect else '숨김'}이어야 함", row)
        chk(row["hasNotice"] == (not expect),
            f"★★★ rank={row['rank']} done={row['done']} → 안내문 {'노출' if not expect else '숨김'}이어야 함", row)

# ============================================================
print("\n[4] 실행(Node) — 출동수배 기한점검 버튼이 등급별로 실제 뭘 그리는지")
# ============================================================
node_src3 = r"""
function render(overdue, rank){
  const myRank = () => rank;
  return `""" + dispatch_line + r"""`;
}
const results = [];
for (const rank of [1, 2, 3]) for (const overdue of [0, 5]) {
  const html = render(overdue, rank);
  results.push({rank, overdue, hasAct: html.includes('data-act="dispatchSweep"')});
}
console.log(JSON.stringify(results));
"""
rows3 = run_node(node_src3, "dispatchsweep")
if rows3 is not None:
    for row in rows3:
        expect = row["rank"] >= 2
        chk(row["hasAct"] == expect,
            f"★★★★ rank={row['rank']} overdue={row['overdue']} → 기한점검 버튼 "
            f"{'노출' if expect else '숨김'}이어야 함", row)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
