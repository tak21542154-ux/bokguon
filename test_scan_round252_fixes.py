# -*- coding: utf-8 -*-
"""스캔 252라운드 회귀 — 변경주문(추가공사) 화면 결함 2건
   (admin.js 변경주문 화면군 Agent 조사로 발견, 전부 독립 재검증 후 수정).

  [1] (심각) 전체재경매 낙찰 확정에 필요한 insurer_instruction(발주처 미확인
      금액을 유선지시 등 근거로 남기고 강행하는 통로)이 화면에 아예 없었다.
      서버(api_co_close_full)는 이미 이 필드를 받아 처리하는데(5자 이상이면
      insurer_ack 불일치를 우회), 전체재경매는 구조상 원업체가 거절한 옛
      합산가를 상한으로 인하 입찰되므로 낙찰가가 그 옛 발주처 확인금액과
      거의 항상 달라 이 관문(INSURER_ACK_REQUIRED)에 실제로 자주 걸린다 —
      그런데 입력할 곳이 없어 콘솔로는 영원히 낙찰을 확정할 수 없었다(원시
      API 호출로 우회해야 했다). co_reason(최저가 아닌 사유)과 같은 방식의
      입력칸을 추가하고, 에러 코드도 형제(NOT_LOWEST)처럼 바로 그 칸을
      가리키게 했다.

  [2] coActions()가 내는 변경주문 처리 버튼 7개(추가분 경매 오픈·철회·마감→
      원업체 제시·추가분 유찰·제안 회수·전체 재경매 오픈·재경매 마감) 전부
      등급 게이트가 없었다 — 대응하는 백엔드 라우트 7개가 전부
      require_role(중간관리자)인데 하위관리자에게도 그대로 노출돼 눌러야만
      403을 만났다. 목록 조회(GET /api/change-orders)는 require_admin(등급
      무관)이라 화면 자체는 계속 보이는 게 맞고, 처리 버튼만 가려야 한다.
      형제(cmNew·boqForm, 246·247·251라운드)와 같은 방식으로 통일.

      python test_scan_round252_fixes.py
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
print("  스캔 252라운드 회귀 — 변경주문 발주처확인우회칸·처리버튼 등급게이트")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = ADMIN_JS.index("async function coCloseFull(")
i1 = ADMIN_JS.index("\nasync function coAwardFull(", i0)
close_body = ADMIN_JS[i0:i1]
i2 = i1
i3 = ADMIN_JS.index("\nasync function coFailFull(", i2)
award_body = ADMIN_JS[i2:i3]

chk('id="co_instruction"' in close_body, "★★★★ 발주처 확인 근거 입력칸이 모달에 생겼다")
chk("insurer_instruction:instruction" in award_body,
    "★★★★ coAwardFull() 이 그 값을 실제로 요청 본문에 싣는다")
chk(award_body.count("insurer_instruction:instruction") >= 2,
    "STEP 정상 마감·강행(force) 재시도 양쪽 다 그 값을 싣는다")
chk("e.code === 'INSURER_ACK_REQUIRED'" in award_body
    and "co_instruction" in award_body.split("e.code === 'INSURER_ACK_REQUIRED'")[1][:200],
    "★★★★ 그 오류를 만나면 형제(NOT_LOWEST)처럼 입력칸을 바로 가리켜 준다")

i4 = ADMIN_JS.index("function coActions(")
i5 = ADMIN_JS.index("\nasync function coWithdraw(", i4)
actions_body = ADMIN_JS[i4:i5]
chk("if(myRank()<2) return" in actions_body,
    "★★★★ 처리 버튼 전부가 등급 미달이면 안내문으로 바뀐다")
for act in ("coAddAuction", "coWithdrawReq", "coOffer", "coFailAdd", "coWithdraw", "coFullReauction"):
    chk(f'data-act="{act}"' in actions_body,
        f"STEP {act} 버튼 자체는 여전히 (등급 충족 시) 존재한다")

# ============================================================
print("\n[2] 실행(Node) — coActions() 가 등급별로 실제 뭘 그리는지")
# ------------------------------------------------------------
node_src = r"""
function coActions(co, rank){
  const myRank = () => rank;
""" + actions_body[actions_body.index("\n", actions_body.index("function coActions(")) + 1:] + r"""
const cases = [
  ['실사요청', 'coAddAuction'], ['추가경매중', 'coOffer'],
  ['원업체제안', 'coWithdraw'], ['거절', 'coFullReauction'],
  ['전체재경매중', 'coCloseFull'], ['유찰', 'coFullReauction'],
];
const results = [];
for(const [status, act] of cases){
  for(const rank of [1, 3]){
    const html = coActions({status, id:1}, rank);
    const has = html.includes(`data-act="${act}"`);
    results.push({status, rank, act, has, ok: has === (rank >= 2)});
  }
}
console.log(JSON.stringify(results));
"""
node_path = os.path.join(tempfile.gettempdir(), "r252_coactions_render.js")
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
                f"→ {'노출' if row['rank']>=2 else '숨김'}이어야 함",
                f"실제: {'노출' if row['has'] else '숨김'}")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ Node 렌더링 준비", f"{type(e).__name__} {e}")
finally:
    try: os.remove(node_path)
    except OSError: pass

# ============================================================
print("\n[3] 실행(Flask) — 새 입력칸이 실제로 낙찰을 확정시키는지")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round252_")
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
                 "VALUES('r252mid','x','검증','중간관리자')")
    inc_pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R252원업체','시공사','활성')").lastrowid
    new_pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R252새업체','시공사','활성')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,address,partner_id,"
        "award_amount,low_price,is_demo) "
        "VALUES('R252-1','시공중','가드레일','서울','서울 강남구 1',?,10000000,10000000,0)",
        (inc_pid,)).lastrowid
    #  ⚠ insurer_ack 를 일부러 '부동의'(현재 요청 금액과도 안 맞는 옛 확인)로 둔다 —
    #    이게 바로 이 결함이 실제로 걸리는 조건이다(옛 확인은 남아 있는데 새 낙찰가와 다름).
    coid = conn.execute(
        "INSERT INTO change_orders(case_id,round,incumbent_partner_id,incumbent_amount,"
        "reason,status,insurer_ack,insurer_ack_amount) "
        "VALUES(?,2,?,10000000,'실사 증액','전체재경매중','부동의',11500000)",
        (cid, inc_pid)).lastrowid
    au_id = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "bid_count,extend_count,deadline,created_at) "
        "VALUES(?,?,'전체재경매',2,'진행',0,1,0,datetime('now','+9 hours','-2 hours'),?)",
        (cid, coid, DB.now())).lastrowid
    bid_id = conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,'R252새업체',11200000,10,?)", (au_id, new_pid, DB.now())).lastrowid
    conn.commit(); conn.close()

    mid = A.app.test_client()
    tok = "r252-csrf"
    with mid.session_transaction() as sess:
        sess["admin"] = "r252mid"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    #  ── (a) 근거 없이 낙찰 시도 → 여전히 막힌다(관문 자체는 안 풀었다) ──
    r0 = mid.post(f"/api/change-orders/{coid}/close-full", json={"bid_id": bid_id}, headers=hdr)
    chk(r0.status_code == 409 and r0.get_json().get("code") == "INSURER_ACK_REQUIRED",
        "STEP 근거 없이는 여전히 막힌다(관문을 없앤 게 아니라 입력통로만 열었다)", r0.get_json())

    #  ── (b) 새로 생긴 필드로 근거를 남기면 — 이제 낙찰이 확정된다 ──
    r1 = mid.post(f"/api/change-orders/{coid}/close-full",
                  json={"bid_id": bid_id, "insurer_instruction": "08-20 14:00 김담당 유선 승인"},
                  headers=hdr)
    j1 = r1.get_json()
    chk(r1.status_code == 200 and j1.get("ok"),
        "★★★★★ insurer_instruction 을 채우면 콘솔에서도 낙찰이 확정된다"
        "(고치기 전엔 이 값을 보낼 방법이 없어 영원히 막혀 있었다)", j1)

    conn = DB.get_db()
    c_row = conn.execute("SELECT partner_id, award_amount FROM cases WHERE id=?", (cid,)).fetchone()
    co_row = conn.execute("SELECT status FROM change_orders WHERE id=?", (coid,)).fetchone()
    conn.close()
    chk(c_row["partner_id"] == new_pid and c_row["award_amount"] == 11200000,
        "STEP 사건의 낙찰업체·금액이 실제로 새 값으로 갱신된다", dict(c_row))
    chk(co_row["status"] == "낙찰확정", "STEP 변경건 상태가 낙찰확정으로 바뀐다", co_row["status"])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드252 [3] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
