# -*- coding: utf-8 -*-
"""스캔 253라운드 회귀 — 보험사(발주처) 관리 화면 결함 2건
   (admin.js 보험사 관리 화면군 Agent 조사로 발견, 전부 독립 재검증 후 수정).

  [1] VIEWS.insurers 에 자기차단이 없었다 — applyRoleMenus() 는 사이드바
      메뉴 항목만 등급3 미만이면 숨기는데, loadView() 자체는 등급을 안 보고
      그대로 VIEWS[v]()를 실행한다. 실제로 메뉴가 아닌 경로가 있었다 —
      VIEWS.newcase(등급 무관, 하위관리자도 씀)가 발주처 0곳일 때 보여주는
      "발주처 등록하러 가기→" 버튼이 정확히 이 화면을 연다. 서버(GET
      /api/insurers?all=1)도 require_admin(등급무관)이라 전 발주처의
      담당자·부서·연락처·포털계정 보유여부·계약상태가 하위관리자에게도
      그대로 노출됐다. 형제(VIEWS.admins)처럼 화면 스스로 막고, 화면만
      믿지 않고 서버(all=1 분기)도 함께 막는다(사건등록이 쓰는 기본
      모드는 등급 무관 그대로 둔다 — fee_rate_bp 는 원래 거기서도 필요).

  [2] 발주처 상태(활성/중지) 변경이 콘솔에서 사실상 동작 불능이었다 —
      insurerForm() 은 상태 <select> 만 두고 사유 입력·강등확인 재요청
      배선이 전혀 없어, 서버가 NEED_REASON(사유 5자 이상 필요)이나
      INSURER_HAS_WORK(대기 정산·1차합의 있음, confirm_demote 필요)로
      막으면 토스트 에러만 뜨고 모달이 그대로 남았다. 형제(savePartner)가
      이미 구현한 사유입력→재요청, 강등확인→재요청 배선을 그대로 옮겼다.

      python test_scan_round253_fixes.py
"""
import io
import os
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
print("  스캔 253라운드 회귀 — 보험사화면 등급게이트·상태변경 배선")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = ADMIN_JS.index("VIEWS.insurers = async () => {")
i1 = ADMIN_JS.index("\n};", i0)
ins_view = ADMIN_JS[i0:i1]
chk("if(myRank() < 3){" in ins_view,
    "★★★★ VIEWS.insurers 가 등급3 미만이면 스스로 막는다")

i2 = APP_SRC.index("def api_insurers_list(")
i3 = APP_SRC.index("\n\n\n", i2)
list_body = APP_SRC[i2:i3]
chk('if request.args.get("all") == "1" and _admin_rank() < 3:' in list_body,
    "★★★★ 서버도 all=1 조회를 최고관리자 미만이면 막는다(화면만 믿지 않는다)")
chk('WHERE status=\'활성\' ORDER BY name' in list_body,
    "STEP 사건등록이 쓰는 기본 모드(전체 아님)는 등급 검사에 안 걸린다")

i4 = ADMIN_JS.index("async function insurerDemoteConfirm(")
i5 = ADMIN_JS.index("\nasync function saveInsurer(", i4)
demote_body = ADMIN_JS[i4:i5]
chk("info.code !== 'INSURER_HAS_WORK'" in demote_body,
    "★★★★ 보험사 전용 강등확인 함수가 생겼다(형제 demoteConfirm 은 partners 전용 필드라 재사용 불가)")

i6 = ADMIN_JS.index("async function saveInsurer(")
i7 = ADMIN_JS.index("\n// ── 관리자 계정", i6)
save_body = ADMIN_JS[i6:i7]
chk("e.data.code === 'NEED_REASON'" in save_body,
    "★★★★ saveInsurer() 가 NEED_REASON 을 받으면 사유를 물어 재요청한다")
chk("await insurerDemoteConfirm(e" in save_body and "await insurerDemoteConfirm(e2" in save_body,
    "★★★★ 강등확인이 먼저 오는 경우·사유 다음에 오는 경우 둘 다 처리한다")
chk(save_body.count("confirm_demote:true") == 2,
    "STEP 두 경로 모두 최종 재요청엔 confirm_demote:true 를 싣는다")

# ============================================================
print("\n[2] 실행(Flask) — 등급 차단·상태변경 전 과정 실측")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round253_")
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
                 "VALUES('r253low','x','검증하위','하위관리자')")
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r253top','x','검증최고','최고관리자')")
    #  ⚠ 대기 정산이 있는 보험사 — 강등확인(INSURER_HAS_WORK) 경로용
    iid_busy = conn.execute(
        "INSERT INTO insurers(name,org_type,status,fee_rate_bp) "
        "VALUES('R253바쁜보험사','손해보험','활성',1000)").lastrowid
    conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,insurer_id,partner_name,"
        "amount,fee,payout,insurer_paid,review_status,transfer_status,created_at) "
        "VALUES(NULL,'R253-1','R253바쁜보험사',?,'R253업체',1000000,100000,900000,0,'대기','대기',?)",
        (iid_busy, DB.now()))
    #  ⚠ 대기 업무가 없는 보험사 — NEED_REASON 단독 경로용
    iid_clean = conn.execute(
        "INSERT INTO insurers(name,org_type,status,fee_rate_bp) "
        "VALUES('R253한가한보험사','손해보험','활성',1000)").lastrowid
    conn.commit(); conn.close()

    low = A.app.test_client()
    tok_low = "r253-csrf-low"
    with low.session_transaction() as sess:
        sess["admin"] = "r253low"; sess["admin_role"] = "하위관리자"; sess["admin_name"] = "검증하위"
        sess["_csrf"] = tok_low
    hdr_low = {"X-CSRF-Token": tok_low}

    top = A.app.test_client()
    tok_top = "r253-csrf-top"
    with top.session_transaction() as sess:
        sess["admin"] = "r253top"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증최고"
        sess["_csrf"] = tok_top
    hdr_top = {"X-CSRF-Token": tok_top}

    #  ── (a) 하위관리자는 all=1 상세조회가 서버에서 막힌다(방어의 마지막 선) ──
    ra = low.get("/api/insurers?all=1", headers=hdr_low)
    chk(ra.status_code == 403, "★★★★★ 하위관리자의 all=1 조회는 서버에서 403으로 막힌다", ra.status_code)

    #  ── (b) 대조군 — 기본 모드(사건등록용)는 하위관리자도 여전히 정상 조회 ──
    rb = low.get("/api/insurers", headers=hdr_low)
    chk(rb.status_code == 200, "STEP 대조군 — 기본 조회(사건등록 드롭다운용)는 등급 무관 그대로 된다", rb.status_code)

    #  ── (c) 최고관리자가 바쁜 보험사를 중지 시도 → 강등확인 관문에 막힌다 ──
    rc = top.patch(f"/api/insurers/{iid_busy}", json={"status": "중지"}, headers=hdr_top)
    jc = rc.get_json()
    chk(rc.status_code == 409 and jc.get("code") == "INSURER_HAS_WORK",
        "STEP 대기 업무 있는 보험사는 확인 없이 바로 중지되지 않는다", jc)

    #  ── (d) 강행 확인은 보냈지만 사유가 없다 → NEED_REASON ──
    rd = top.patch(f"/api/insurers/{iid_busy}",
                   json={"status": "중지", "confirm_demote": True}, headers=hdr_top)
    jd = rd.get_json()
    chk(rd.status_code == 400 and jd.get("code") == "NEED_REASON",
        "STEP 강행해도 사유 없인 안 된다(둘 다 필요)", jd)

    #  ── (e) 확인 + 사유 둘 다 있으면 — 이제 실제로 상태가 바뀐다 ──
    re_ = top.patch(f"/api/insurers/{iid_busy}",
                    json={"status": "중지", "confirm_demote": True,
                          "status_reason": "계약 종료 협의 완료"}, headers=hdr_top)
    je = re_.get_json()
    chk(re_.status_code == 200 and je.get("ok"),
        "★★★★★ 확인+사유를 함께 보내면(화면이 이제 이걸 자동으로 한다) 실제로 상태가 바뀐다", je)
    conn = DB.get_db()
    row = conn.execute("SELECT status FROM insurers WHERE id=?", (iid_busy,)).fetchone()
    conn.close()
    chk(row["status"] == "중지", "STEP DB 에도 실제로 반영된다", row["status"])

    #  ── (f) 대조군 — 대기 업무 없는 보험사는 강등확인 없이 사유만으로 바로 된다 ──
    rf1 = top.patch(f"/api/insurers/{iid_clean}", json={"status": "중지"}, headers=hdr_top)
    chk(rf1.status_code == 400 and rf1.get_json().get("code") == "NEED_REASON",
        "STEP 대조군 — 대기 업무 없으면 강등확인 없이 곧장 사유만 요구한다", rf1.get_json())
    rf2 = top.patch(f"/api/insurers/{iid_clean}",
                    json={"status": "중지", "status_reason": "계약 미갱신"}, headers=hdr_top)
    chk(rf2.status_code == 200 and rf2.get_json().get("ok"),
        "STEP 사유만 채우면 confirm_demote 없이도 바로 성공한다(과잉차단 아님)", rf2.get_json())
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드253 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
