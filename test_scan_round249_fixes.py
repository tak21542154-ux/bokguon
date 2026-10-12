# -*- coding: utf-8 -*-
"""스캔 249라운드 회귀 — 사건(case) 관리 화면 결함 3건
   (admin.js 사건관리 화면군 Agent 병렬조사로 발견, 전부 독립 재검증 후 수정).

  [1] caseDetail() 의 수정 폼·다수 액션 버튼에 등급 게이트(myRank)가 없었다.
      PATCH /api/cases/<id>(사건정보 수정 전체 — 공종·지역·주소·가견적·담당·
      보증·긴급·피해자정보)와 8개 액션 라우트(caseReopen·caseCloseOffline·
      caseUndoNoRepair·caseFailBidding·caseToDispatch·caseApprove·
      caseCancelAward·caseOpenAuction, 전부 require_role(중간관리자)) 및
      입찰마감변경(require_role 중간관리자)·피해사진올리기(require_role
      중간관리자)까지 전부 등급≥2 전용인데 화면은 등급 무관하게 그렸다 —
      하위관리자가 값을 다 고치거나 버튼을 눌러야만 403을 만났다. 단, 같은
      모달의 🔔공고다시알리기(require_role 하위관리자=등급무관 허용)와
      📣완료보고독촉(require_admin=등급무관 허용) 두 개는 원래도 제한이 없어
      **그대로 두었다** — 여기까지 등급을 올려 잠갔다면 그게 새 결함이 된다.

  [2] api_case_edit() 감사로그가 category·est_price만 이전값→새값을 남기고
      region·address·manager·victim_name·victim_phone·urgent·warranty_months
      는 필드명만 남겼다. 분쟁·소명 시 "무엇이 어디서 어디로 바뀌었나"를 로그
      만으로 복원할 수 없었다. 넷(region·address·manager)은 category와 같은
      형식으로, victim_phone은 계좌정보 변경(7518행 선례)과 같은 이유로
      원문 대신 POPBILL.mask_phone() 마스킹으로 남기도록 통일 — 이 값은
      응답의 changed 배열로 saveCaseEdit() 저장완료 토스트에도 그대로
      노출되므로, 화면 쪽 안내문구도 이번에 함께 구체화된다.

  [3] uploadDamagePhotos() 가 부분 실패(중복·형식오류로 일부만 저장)를
      화면에 전혀 알리지 않았다 — 성공(n>0)이면 무조건 "N장을 올렸습니다"만
      말해, 5장 보내고 2장이 걸러져도 이유를 알 길이 없었다(함수 자신의
      주석이 "형식·중복은 서버가 거른다"고 이미 인정하면서도). 같은 파일의
      형제(createCase() 안의 인라인 업로드, "[라운드77] createCase()와 같은
      이유"로 이미 스스로 짝지어진 코드)는 이미 j.duplicates·j.errors·
      j.ai_report 를 조합해 보여준다 — 같은 구성으로 통일.

      python test_scan_round249_fixes.py
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
print("  스캔 249라운드 회귀 — 사건관리 등급게이트·감사로그·사진업로드피드백")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — caseDetail() 등급 게이트")
# ------------------------------------------------------------
i0 = ADMIN_JS.index("async function caseDetail(")
i1 = ADMIN_JS.index("\nasync function uploadDamagePhotos(", i0)
cd_body = ADMIN_JS[i0:i1]

for fid in ("e_cat", "e_region", "e_addr", "e_mgr", "e_vname", "e_vphone", "e_warr"):
    chk(f'id="{fid}"' in cd_body and f"myRank()<2?' disabled'" in cd_body,
        f"★★ {fid} 입력칸이 등급 미달 시 읽기전용(disabled)이 된다")
chk('id="e_urgent"${myRank()<2?\' disabled\':\'\'}' in cd_body,
    "★★ 긴급 선택칸도 등급 미달 시 읽기전용이 된다")
chk("(editable&&myRank()>=2)?''" in cd_body,
    "★★ 가견적 칸은 '입찰마감 잠금'과 '등급 미달' 둘 다 반영해 잠긴다")
chk('myRank()<2?\'<div class="hint">사건 정보·피해자 정보 수정' in cd_body,
    "STEP 등급 미달이면 안내 문구가 뜬다")

for act, needs_rank in [
    ("saveCaseEdit", True), ("caseReopen", True), ("caseCloseOffline", True),
    ("caseUndoNoRepair", True), ("caseFailBidding", True), ("caseToDispatch", True),
    ("caseApprove", True), ("caseCancelAward", True), ("caseOpenAuction", True),
    ("auctionDeadline", True),
    ("caseRenotify", False), ("caseRemindReport", False),
]:
    j = cd_body.index(f'data-act="{act}"')
    #  ⚠ 매 최상위 삼항연산자 블록은 "\n      ${" (줄바꿈+공백6+${) 로 시작한다 —
    #    맨 뒤 bare "${" 로 찾으면 caseReopen/caseCloseOffline 처럼 **같은 블록을
    #    공유하는 앞 버튼 자신의 인라인 ${id}** 에 걸려 엉뚱한(더 안쪽) 구간을
    #    본다(실측: 이 방식으로 봤더니 caseCloseOffline 이 거짓 실패).
    seg_start = cd_body.rfind("\n      ${", 0, j)
    seg = cd_body[seg_start:j]
    has_gate = "myRank()>=2" in seg
    if needs_rank:
        chk(has_gate, f"★★★★ {act} 버튼이 myRank()>=2 로 게이트됐다", seg[:160])
    else:
        chk(not has_gate, f"★★ {act} 버튼은 원래도 등급무관 허용이라 게이트하지 **않아야** 한다"
            "(잘못 잠그면 그 자체가 새 결함)", seg[:160])

chk('id="dmg_' in cd_body, "STEP 피해사진 업로드 input 자체는 여전히 존재")
dmg_seg_start = cd_body.rfind("\n      ${", 0, cd_body.index('id="dmg_'))
chk("myRank()>=2" in cd_body[dmg_seg_start:cd_body.index('id="dmg_')],
    "★★★★ 📷 피해 사진 올리기 버튼이 myRank()>=2 로 게이트됐다")

# ============================================================
print("\n[2] 소스 확인 — api_case_edit() 감사로그")
# ------------------------------------------------------------
i2 = APP_SRC.index("def api_case_edit(")
i3 = APP_SRC.index("\n\n\n", i2)
edit_body = APP_SRC[i2:i3]
chk('notes.append(f"{f} \'{c[f] or \'\'}\'→\'{nv}\'")' in edit_body
    and "if f == \"category\" else f" not in edit_body,
    "★★★★ region·address·manager 도 category 처럼 이전값→새값을 남긴다"
    "(category 만 남기던 특례가 사라졌다)")
chk("POPBILL.mask_phone(c[f])" in edit_body and "POPBILL.mask_phone(nv)" in edit_body,
    "★★★★ 피해자 연락처는 계좌정보 변경과 같은 방식으로 마스킹해 남긴다(원문 미보존)")
#  ⚠⚠ [라운드496] 이 라운드 당시엔 이름을 원문 old→new로 남기는 게 옳은
#    선택이었다(전화번호만 "직접 연락 가능한 정보"로 보고 마스킹). 이후
#    처리방침 제3조가 "피해자 성명·연락처"를 같은 파기기준(하자담보 만료
#    후 파기)으로 묶어 약속했는데 activity_log는 cmd_prune_personal()의
#    파기 대상이 아니라서, 원문 이름이 남는 이 로그가 그 약속을 어기고
#    있음을 496라운드가 발견 — 이름도 형제(전화번호)와 같은 원칙으로
#    마스킹하도록 바뀌었다. 아래 검사는 그 새 동작을 반영한다.
chk("CRYPTO.mask_name(c[f])" in edit_body and "CRYPTO.mask_name(nv)" in edit_body,
    "STEP 피해자 이름은 라운드496부터 형제 전화번호처럼 마스킹되어 남는다"
    "(원문 old→new가 아님)")
chk('f"긴급여부 {' in edit_body, "★★ 긴급여부도 이전값→새값을 남긴다")
chk('f"보증기간 {' in edit_body and "개월" in edit_body[edit_body.index('f"보증기간'):edit_body.index('f"보증기간')+60],
    "★★ 보증기간도 이전값→새값을 남긴다")

# ============================================================
print("\n[3] 소스 확인 — uploadDamagePhotos() 부분실패 피드백")
# ------------------------------------------------------------
i4 = ADMIN_JS.index("async function uploadDamagePhotos(")
i5 = ADMIN_JS.index("\n// ── 도급 적법성 판정 이력", i4)
up_body = ADMIN_JS[i4:i5]
chk("j.duplicates" in up_body, "★★★★ 중복 제외 사유를 화면에 보여준다(형제 createCase 와 동일)")
chk("j.errors" in up_body and "j.errors.length" in up_body,
    "★★★★ 형식오류 사유를 화면에 보여준다")
chk("j.ai_report" in up_body, "★★ AI 분석 결과도 형제처럼 함께 보여준다")
chk("${n}/${ok.length}" in up_body, "STEP 보낸 장수 대비 실제 저장 장수를 함께 보여준다")

print("\n[4] 실행(Node) — 사건 상세 하단 액션버튼이 실제로 어떻게 그려지는지")
# ------------------------------------------------------------
#  ⚠ "modal-foot" 은 이 파일의 여러 모달이 공유하는 흔한 클래스명이다 — i0(캐이스
#    디테일 시작) 없이 찾으면 **다른 화면의 modal-foot** 을 집어 정작 검사는
#    엉뚱한 버튼(예: 리드 화면의 leadAct)을 렌더링하려다 ReferenceError 로 죽는다
#    (실측: 이 앵커 없이 처음 돌렸을 때 실제로 그렇게 죽었다).
foot_start = ADMIN_JS.index('    <div class="modal-foot">', i0)
foot_end = ADMIN_JS.index("\n    </div>`);", foot_start)
foot_tpl = ADMIN_JS[foot_start:foot_end] + "\n    </div>"

node_src = r"""
function render(c, id, rank, d){
  const myRank = () => rank;
  const esc = (s) => String(s==null?'':s);
  const html = `""" + foot_tpl.replace("\\", "\\\\") + r"""`;
  return html;
}
const scenarios = [
  {c:{status:'유찰', partner_id:null}, rank:1, expect:{saveCaseEdit:false, caseReopen:false, caseCloseOffline:false, caseToDispatch:false}},
  {c:{status:'유찰', partner_id:null}, rank:3, expect:{saveCaseEdit:true,  caseReopen:true,  caseCloseOffline:true,  caseToDispatch:true}},
  {c:{status:'입찰중', partner_id:null}, rank:1, expect:{caseRenotify:true, caseFailBidding:false, caseToDispatch:false}},
  {c:{status:'입찰중', partner_id:null}, rank:3, expect:{caseRenotify:true, caseFailBidding:true,  caseToDispatch:true}},
  {c:{status:'검수대기', partner_id:null}, rank:1, expect:{caseApprove:false}},
  {c:{status:'검수대기', partner_id:null}, rank:3, expect:{caseApprove:true}},
  {c:{status:'완료보고지연', partner_id:9}, rank:1, expect:{caseRemindReport:true, caseCancelAward:false}},
  {c:{status:'완료보고지연', partner_id:9}, rank:3, expect:{caseRemindReport:true, caseCancelAward:true}},
  {c:{status:'접수', partner_id:null}, rank:1, expect:{caseOpenAuction:false}},
  {c:{status:'접수', partner_id:null}, rank:3, expect:{caseOpenAuction:true}},
  {c:{status:'미수선종결', partner_id:null}, rank:1, expect:{caseUndoNoRepair:false}},
  {c:{status:'미수선종결', partner_id:null}, rank:3, expect:{caseUndoNoRepair:true}},
  //  ⚠ auctionDeadline(⏱ 입찰 마감 변경)은 <div class="modal-foot"> **밖**(그 위
  //    "운영 도구" 섹션)에 있어 foot_tpl 추출 범위 밖이다 — [1]의 소스검사가
  //    이미 그 자리를 정확히 검증하므로 여기서 중복(오배치) 시나리오를 안 만든다.
];
const results = [];
for(const s of scenarios){
  const html = render(s.c, 42, s.rank, s.d||{});
  for(const [act, want] of Object.entries(s.expect)){
    const has = html.includes(`data-act="${act}"`);
    results.push({status:s.c.status, rank:s.rank, act, want, has, ok: has===want});
  }
}
console.log(JSON.stringify(results));
"""
node_path = os.path.join(tempfile.gettempdir(), "r249_casedetail_render.js")
io.open(node_path, "w", encoding="utf-8").write(node_src)
try:
    r = subprocess.run(["node", node_path], capture_output=True, text=True, encoding="utf-8", timeout=20)
    if r.returncode != 0:
        chk(False, "★★★ Node 렌더링 실행", r.stderr[-800:])
    else:
        rows = json.loads(r.stdout.strip().splitlines()[-1])
        for row in rows:
            chk(row["ok"],
                f"★★★★ status={row['status']} rank={row['rank']} {row['act']} "
                f"→ {'노출' if row['want'] else '숨김'}이어야 함",
                f"실제: {'노출' if row['has'] else '숨김'}")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ Node 렌더링 준비", f"{type(e).__name__} {e}")
finally:
    try: os.remove(node_path)
    except OSError: pass

# ============================================================
print("\n[5] 실행(Flask) — api_case_edit 감사로그·응답이 실제로 이전값→새값을 담는지")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round249_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r249mid','x','검증','중간관리자')")
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,address,manager,"
        "victim_name,victim_phone,urgent,warranty_months,is_demo) "
        "VALUES('R249-1','접수','가드레일','서울','서울 강남구 1','김담당',"
        "'홍길동','01011112222',0,24,0)").lastrowid
    conn.commit(); conn.close()

    mid = A.app.test_client()
    tok = "r249-csrf"
    with mid.session_transaction() as sess:
        sess["admin"] = "r249mid"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    r = mid.patch(f"/api/cases/{cid}", json={
        "region": "경기", "address": "경기 성남시 2", "manager": "이담당",
        "victim_phone": "01033334444", "urgent": True, "warranty_months": 36,
    }, headers=hdr)
    j = r.get_json()
    chk(r.status_code == 200 and j.get("ok"), "STEP 정상 수정 요청은 200으로 성공한다", j)
    changed = " / ".join(j.get("changed") or [])
    chk("서울'→'경기'" in changed, "★★★★ region 응답에 이전값→새값이 담긴다(더는 필드명만이 아님)", changed)
    chk("서울 강남구 1'→'경기 성남시 2'" in changed, "★★★★ address 응답에 이전값→새값이 담긴다", changed)
    chk("김담당'→'이담당'" in changed, "★★★★ manager 응답에 이전값→새값이 담긴다", changed)
    chk("010****2222" in changed and "010****4444" in changed,
        "★★★★ 피해자 연락처는 원문이 아니라 마스킹된 형태로 담긴다", changed)
    chk("01011112222" not in changed and "01033334444" not in changed,
        "★★★★★ 전화번호 원문은 응답 어디에도 노출되지 않는다(마스킹만)", changed)
    chk("일반→긴급" in changed, "★★ 긴급여부 이전값→새값이 담긴다", changed)
    chk("24→36개월" in changed, "★★ 보증기간 이전값→새값이 담긴다", changed)

    conn = DB.get_db()
    row = conn.execute(
        "SELECT detail FROM activity_log WHERE action='사건 수동 수정' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    chk(row is not None and "010****2222" in row["detail"] and "01011112222" not in row["detail"],
        "★★★★ 감사로그(activity_log)에도 같은 마스킹 형태로만 남는다(원문 미보존)",
        row["detail"] if row else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드249 [5] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
