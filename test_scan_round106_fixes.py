# -*- coding: utf-8 -*-
"""스캔 106라운드 회귀 — 이체관문 하자사유 형식불일치, 하도급 자격판정 컬럼오류, 하자 평점집계 데모오염.

  [1] 지급 검수(review)와 이체(transfer) 두 관문이 같은 defect_override_reason
      필드를 다른 세기로 봤다 — transfer 는 body() 원시값의 truthy 만 봐서
      공백(" ")도 통과시켰고, 그 뒤 로그만 나중에 strip 해 감사기록엔
      "하자 있는 상태로 지급 강행" 경고가 안 남았다. 화면(askOverride)이
      약속하는 "5자 이상"도 서버 어느 쪽에도 없었다.
  [2] 건산법 §25② 하도급 자격 판정(check_subcontractor)이 정본 컬럼
      (license_status, license_block_reason 등 실제 강제규칙이 보는 곳)이 아니라
      표류 컬럼(license, 업체 자기신고 자유텍스트)을 봐서 판정 방향이 실측
      100% 반대였다(등록확인 유일 업체는 차단, 미확인 다수는 통과).
  [3] _bid_scores·partner_rating 의 하자 집계 술어(status='완료'
      AND cost_bearer='시행사')에 is_demo 필터가 없어, 데모 사건의 하자가
      실제 협력사의 낙찰점수·평점 차감에 섞였다(형제인 happy_calls 질의는
      이미 걸러냄).

      python test_scan_round106_fixes.py
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
COMPLIANCE_SRC = read("compliance.py")

print("═" * 72)
print("  스캔 106라운드 회귀 — 이체관문 하자사유·하도급 자격판정 컬럼오류·하자 집계 데모오염")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 다섯 지점 모두 확인")
# ──────────────────────────────────────────────────────────────
tr_body = _py_fn_body(APP_SRC, "api_settlement_transfer")
chk("if open_d2 and len(_dov) < 5:" in tr_body,
    "★★★ 이체 관문이 5자 이상을 요구한다(예전엔 공백도 통과)")
rv_body = _py_fn_body(APP_SRC, "api_settlement_review")
chk("if open_d and len(_dov) < 5:" in rv_body,
    "★★ 검수 관문도 같은 기준(5자 이상)을 요구한다")

sc_body = _py_fn_body(COMPLIANCE_SRC, "check_subcontractor")
chk('status = _g("license_status") or "미확인"' in sc_body,
    "★★★ 하도급 자격판정이 정본 컬럼(license_status)을 본다")
chk('if status != "등록확인":' in sc_body,
    "★★ 미확인 상태는 통과시키지 않는다(확인 안 됨 ≠ 안전)")

bs_body = _py_fn_body(APP_SRC, "_bid_scores")
_bs_defect_query = bs_body[bs_body.index("SELECT COUNT(*) n FROM defects"):
                           bs_body.index("(b[\"partner_id\"],)))")]
chk("COALESCE(is_demo,0)=0" in _bs_defect_query,
    "★★★ _bid_scores 의 하자 집계가 이제 데모를 뺀다")
pr_body = _py_fn_body(APP_SRC, "partner_rating")
_pr_defect_query = pr_body[pr_body.index("ds = rows"):pr_body.index("GROUP BY severity")]
chk("COALESCE(is_demo,0)=0" in _pr_defect_query,
    "★★ partner_rating 의 하자 집계도 이제 데모를 뺀다")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[4] 실행 — 실제 시나리오를 돌린다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round106_")
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
    import compliance as CP

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','최고관리자')")
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,bank_name,bank_holder,bank_account_enc) "
        "VALUES('R106업체','시행사','활성','국민','R106업체','enc:1234')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,is_demo) "
        "VALUES('R106-C1','정산진행','가드레일','서울',?,0)", (pid,)).lastrowid
    conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,title,status,created_at) "
        "VALUES('R106-DF1',?,'R106-C1','누수 재발','접수중',?)", (cid, DB.now()))
    sid = conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_id,partner_name,amount,fee,"
        "                        payout,review_status,transfer_status,created_at) "
        "VALUES(?,'R106-C1','R106보험',?,'R106업체',3000000,300000,2700000,'승인','대기',?)",
        (cid, pid, DB.now())).lastrowid
    conn.commit()

    admin = A.app.test_client()
    _tok = "r106-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    r1 = admin.post(f"/api/settlements/{sid}/transfer", headers=_hdr,
                     json={"defect_override_reason": " "})
    chk(r1.status_code == 409 and r1.get_json().get("code") == "DEFECT_OPEN",
        "★★★ 공백 하나짜리 사유로는 이체 관문을 못 넘는다"
        "(예전엔 truthy 라 통과 — 감사로그에 강행 경고가 안 남았다)",
        (r1.status_code, r1.get_json()))

    r2 = admin.post(f"/api/settlements/{sid}/transfer", headers=_hdr,
                     json={"defect_override_reason": "협의완료함"})
    chk(r2.status_code == 200, "STEP 5자 이상 사유면 정상적으로 이체가 진행된다(과잉차단 아님)",
        (r2.status_code, r2.get_data(as_text=True)[:200]))
    log_row = conn.execute(
        "SELECT detail FROM activity_log WHERE action='이체 완료' ORDER BY id DESC LIMIT 1").fetchone()
    chk(log_row and "지급 강행" in (log_row["detail"] or ""),
        "★★★ 실제로 강행했을 때는 감사로그에 경고 문구가 정확히 남는다",
        dict(log_row) if log_row else None)

    # ── review 쪽도 같은 기준(5자 미만 거부) ────────────────────────────
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,is_demo) "
        "VALUES('R106-C2','정산진행','가드레일','서울',?,0)", (pid,)).lastrowid
    conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,title,status,created_at) "
        "VALUES('R106-DF2',?,'R106-C2','창틀 하자','접수중',?)", (cid2, DB.now()))
    sid2 = conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_id,partner_name,amount,fee,"
        "                        payout,review_status,transfer_status,insurer_paid,created_at) "
        "VALUES(?,'R106-C2','R106보험',?,'R106업체',1000000,100000,900000,'대기','대기','입금완료',?)",
        (cid2, pid, DB.now())).lastrowid
    conn.commit()
    r3 = admin.post(f"/api/settlements/{sid2}/review", headers=_hdr,
                     json={"double_checked": True, "defect_override_reason": "짧음"})
    chk(r3.status_code == 409 and r3.get_json().get("code") == "DEFECT_OPEN",
        "★★ 검수 관문도 5자 미만 사유는 거부한다(예전엔 빈 문자열만 아니면 통과)",
        (r3.status_code, r3.get_json()))

    # ── [3] 하도급 자격판정 — license_status 3분기 ───────────────────────
    r4 = CP.check_subcontractor({"name": "무등록업체", "license_status": "무등록"})
    chk(not r4["ok"] and r4["code"] == "무등록", "★★★ 무등록 확정 업체는 차단된다", r4)
    r5 = CP.check_subcontractor({"name": "미확인업체", "license_status": "미확인"})
    chk(not r5["ok"], "★★★ 아직 조사 안 된 업체도 차단된다(확인 안 됨은 안전이 아니다)", r5)
    r6 = CP.check_subcontractor({"name": "확인업체", "license_status": "등록확인", "license_no": "실내건축 제1호"})
    chk(r6["ok"], "STEP 등록 확인된 업체는 정상적으로 통과한다(과잉차단 아님)", r6)

    # ── [4] 하자 집계 데모오염 ────────────────────────────────────────
    p2 = conn.execute(
        "INSERT INTO partners(name,partner_type,status,jobs_done) "
        "VALUES('R106업체2','시행사','활성',4)").lastrowid
    cid_demo = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R106-DEMO','완료','가드레일','서울',1)").lastrowid
    conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,title,status,cost_bearer,partner_id,created_at) "
        "VALUES('R106-DFDEMO',?,'R106-DEMO','데모 하자','완료','시행사',?,?)",
        (cid_demo, p2, DB.now()))
    conn.execute(
        "INSERT INTO happy_calls(case_id,partner_id,score,created_at) VALUES(?,?,5,?)",
        (cid_demo, p2, DB.now()))
    conn.commit()
    #  ⚠ is_demo 는 사건에만 붙는다 — 자식표(defects 포함)는 이 캐스케이드를
    #    명시적으로 돌려야 물려받는다(실제 운영에서는 기동 시마다 돈다).
    DB._backfill_child_is_demo(conn)
    bid = {"amount": 1000000, "days": 10, "rating": 4.5, "jobs_done": 4, "partner_id": p2}
    scored = A._bid_scores(conn, {"region": "서울"}, [bid])
    chk(bool(scored) and scored[0]["defect_count"] == 0,
        "★★★ 데모 사건의 하자는 _bid_scores 에서 더는 안 세어진다(예전엔 1건으로 감점됐다)",
        scored[0].get("defect_count") if scored else None)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드106 서버측 준비/실행", f"{type(e).__name__} {e}")
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
