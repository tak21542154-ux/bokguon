# -*- coding: utf-8 -*-
"""스캔 104라운드 회귀 — 정산 내보내기 드릴다운 누락·협력사 대시보드 동명업체 정산 누출.

  [1] 정산 화면에서 대시보드 금액카드(예: 「업체 지급 예정」)를 눌러 좁혀 놓고
      실제 클릭 가능한 [엑셀 내보내기](xlsxBtn→/api/export/settlements)를 누르면,
      화면 배너가 "그 카드와 같은 조건" 이라고 말하는 것과 달리 그 조건(money)
      없이 항상 전체 정산이 나갔다. 102라운드가 고친 /api/settlements/export
      (CSV) 는 저장소 어디에도 이 버튼이 없어(data-act 0건) 실제로는 안 눌리는
      경로였다 — 다만 그 CSV 와 실제 엑셀 버튼이 같은 _settle_filter 를 공유해
      102라운드 수정 자체는 무의미하지 않았다. 이번엔 그 공유 함수에 money 축을
      더하고, 실제 버튼(ACT.exportXlsx)이 그 값을 보내도록 연결한다.
  [2] 협력사 대시보드(/api/partner/dashboard)의 레거시 정산 폴백이
      `partner_id IS NULL AND partner_name=?` 만 보고, db.py 백필이 지키는
      "이름이 유일할 때만" 조건을 안 봤다. 동명 업체가 둘 이상이면 그 이름을
      가진 모든 협력사가 같은 레거시 정산(목록·지급예정/완료 금액 둘 다)을
      자기 것으로 봤다.

      python test_scan_round104_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")
ADMINJS_SRC = read("static/admin.js")

print("═" * 72)
print("  스캔 104라운드 회귀 — 정산 내보내기 드릴다운 누락·협력사 대시보드 동명업체 누출")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 두 지점 모두 확인")
# ──────────────────────────────────────────────────────────────
filt_body = _py_fn_body(APP_SRC, "_settle_filter")
chk("if money in MONEY_DRILL:" in filt_body,
    "★★★ _settle_filter 가 이제 money(대시보드 드릴다운)를 받는다")

#  ⚠⚠ [라운드142] "settleQS().toString() : ''" 를 그대로 이어붙은 문자열로
#    검사했었다 — 142라운드가 exportXlsx 의 3항연산자 사슬에 하자·도입문의·
#    입점신청 분기를 settlements 분기 **바로 뒤**에 추가하면서 그 리터럴이
#    깨졌다(의미는 그대로: settlements 는 여전히 settleQS() 를 쓴다). 그
#    "바로 뒤에 무엇이 오는가"에 기대는 대신, settlements 분기 자체가
#    settleQS() 를 쓰는지만 확인하도록 고친다.
chk("q.set('money', settleMoney)" in ADMINJS_SRC
    and "(a === 'settlements') ? settleQS().toString()" in ADMINJS_SRC,
    "★★★ 실제 엑셀 버튼(ACT.exportXlsx)이 money 를 실어 보낸다"
    "(헬퍼 정의뿐 아니라 실제 호출 지점까지 확인)")

dash_body = _py_fn_body(APP_SRC, "api_partner_dashboard")
chk("(SELECT COUNT(*) FROM partners q WHERE q.name = ?) = 1" in dash_body,
    "★★★ 협력사 대시보드의 레거시 폴백이 백필과 같은 유일성 조건을 건다")
chk("COALESCE(is_demo,0)=0" in dash_body,
    "★★ 협력사 정산 조회도 데모를 뺀다(형제 정산 쿼리들과 동일)")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[3] 실행 — 실제 시나리오를 돌린다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round104_")
_dbpath = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_DB_PATH"] = _dbpath
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A
    from openpyxl import load_workbook

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','중간관리자')")
    admin = A.app.test_client()
    _tok = "r104-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok

    # ── [2] 정산 엑셀 내보내기가 money 드릴다운을 그대로 반영한다 ──────────
    conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_name,amount,fee,payout,"
        "                        transfer_status,created_at) "
        "VALUES(0,'R104-대기건','R104보험','R104업체',1000000,100000,900000,'대기',?)", (DB.now(),))
    conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_name,amount,fee,payout,"
        "                        transfer_status,created_at) "
        "VALUES(0,'R104-완료건','R104보험','R104업체',2000000,200000,1800000,'이체완료',?)", (DB.now(),))
    conn.commit()

    r1 = admin.get("/api/export/settlements?money=payout_pending")
    chk(r1.status_code == 200, "STEP 엑셀 내보내기 자체는 200 이다", r1.status_code)
    if r1.status_code == 200:
        wb = load_workbook(io.BytesIO(r1.data))
        ws = wb.active
        rows_out = list(ws.iter_rows(min_row=2, values_only=True))
        # case_no 열 인덱스를 헤더에서 직접 찾는다(내보내기 컬럼 순서에 의존하지 않기 위해)
        headers = [c.value for c in ws[1]]
        ci = headers.index("접수번호") if "접수번호" in headers else 1
        case_nos = [r[ci] for r in rows_out]
        chk(case_nos == ["R104-대기건"],
            "★★★ money=payout_pending 을 실은 엑셀에 '대기' 건 하나만 담긴다"
            "(예전엔 이 조건 없이 항상 전체가 나갔다)",
            case_nos)

    # ── [3] 협력사 대시보드 — 동명업체는 레거시 정산을 아무도 못 본다 ──────
    p_dup1 = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R104동명업체','시행사','활성')").lastrowid
    p_dup2 = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R104동명업체','시행사','활성')").lastrowid
    p_uniq = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R104유일업체','시행사','활성')").lastrowid
    # 레거시 정산 — 백필이 손대지 않아 partner_id 가 계속 NULL 인 상태를 흉내낸다.
    conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_name,amount,fee,payout,"
        "                        transfer_status,created_at) "
        "VALUES(0,'R104-동명레거시','R104보험','R104동명업체',3000000,300000,2664000,'대기',?)",
        (DB.now(),))
    conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_name,amount,fee,payout,"
        "                        transfer_status,created_at) "
        "VALUES(0,'R104-유일레거시','R104보험','R104유일업체',1000000,100000,900000,'대기',?)",
        (DB.now(),))
    conn.commit()

    def _dash(pid):
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["partner_id"] = pid
        return c.get("/api/partner/dashboard").get_json()

    j1 = _dash(p_dup1)
    j2 = _dash(p_dup2)
    ju = _dash(p_uniq)
    setts1 = [s["case_no"] for s in j1.get("settlements") or []]
    setts2 = [s["case_no"] for s in j2.get("settlements") or []]
    settsu = [s["case_no"] for s in ju.get("settlements") or []]
    chk("R104-동명레거시" not in setts1 and "R104-동명레거시" not in setts2,
        "★★★ 동명 업체 둘 중 어느 쪽도 레거시 정산을 자기 것으로 못 본다"
        "(예전엔 둘 다 같은 2,664,000원을 봤다)",
        (setts1, setts2))
    chk("R104-유일레거시" in settsu,
        "STEP 이름이 유일한 업체는 레거시 정산을 여전히 정상적으로 본다(과잉차단 아님)",
        settsu)
    chk((j1.get("payout_pending") or 0) == 0 and (j2.get("payout_pending") or 0) == 0,
        "★★ 지급예정 합계 KPI 도 동명업체 둘 다 0원이다(목록만이 아니라 금액 카드도 안전)",
        (j1.get("payout_pending"), j2.get("payout_pending")))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드104 서버측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
