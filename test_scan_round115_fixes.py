# -*- coding: utf-8 -*-
"""스캔 115라운드 회귀 — 검수승인 변경견적 무시, 취소정산 독촉, 발주처확인 등급게이트 누락.

  [1] (금전·교착) 검수 승인(정산 생성)이 진행 중인 변경견적을 안 본다 —
      형제(낙찰취소)에는 있는 가드가 여기만 없어, 발주처가 이미 확인한
      증액분을 무시한 채 옛 낙찰가로 정산이 굳고, 그 뒤 변경견적 수락은
      CASE_LOCKED 로 영구히 막혔다.
  [2] (사외통신·정합) 완료승인 독촉이 취소된 정산에도 나갔다 — 형제 4곳과
      자동 스윕은 이미 취소 정산을 거르는데 이 수동 독촉만 안 걸렀다.
  [3] (UX·화면드리프트) 발주처 포털의 변경견적 확인/부동의 버튼에만 등급
      게이트(canAct)가 없어, 조회 등급이 확인창까지 통과한 뒤 403을 봤다
      — 같은 화면의 형제 컨트롤은 전부 사전에 가려서 안내한다.

      python test_scan_round115_fixes.py
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
PORTAL_SRC = read("templates/insurer_portal.html")

print("═" * 72)
print("  스캔 115라운드 회귀 — 검수승인 변경견적무시·취소정산독촉·발주처확인 등급게이트")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
ca_body = _py_fn_body(APP_SRC, "api_case_approve")
chk('"code": "CHANGE_ORDER_ACTIVE"' in ca_body
    and "status NOT IN ('수락확정','최종유찰','낙찰확정','철회')" in ca_body,
    "★★★ 검수 승인이 진행 중인 변경견적을 막는다(형제 낙찰취소와 동일 가드)")

ra_body = _py_fn_body(APP_SRC, "api_settlement_remind_approval")
chk('(s["void_status"] or "") == "취소"' in ra_body,
    "★★ 완료승인 독촉이 취소된 정산은 막는다")

chk("확인·부동의는 <b>중간관리자 이상</b>만 할 수 있습니다" in PORTAL_SRC,
    "★★ 발주처 확인/부동의 버튼도 등급 미달이면 사전에 안내로 가려진다")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[4] 실행 — 실제 시나리오를 돌린다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round115_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r115admin','x','검증','중간관리자')")
    conn.commit()
    admin = A.app.test_client()
    _tok = "r115-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r115admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    def _mk_ready_case(case_no, partner_id):
        """검수대기 + 협력사 승인사진 1장 — approve 전제조건을 만족하는 사건."""
        cid = conn.execute(
            "INSERT INTO cases(case_no,status,category,region,award_amount,partner_id,"
            "                  partner_name,is_demo) "
            f"VALUES('{case_no}','검수대기','가드레일','서울',4000000,?,'R115업체',0)",
            (partner_id,)).lastrowid
        #  ⚠ 116라운드 — 승인관문이 사진의 partner_id 를 낙찰업체와 대조하므로
        #    (2트랙 접수에서 탈락한 전 업체 사진이 지금 낙찰업체 증거로 잡히는
        #    걸 막는 수정), 이 사진도 낙찰업체(partner_id) 본인 것으로 채운다.
        conn.execute(
            "INSERT INTO photos(case_id,uploader,uploader_role,partner_id,rel_path,orig_name,"
            "                   mime,ext,size,sha256,kind,review_status,created_at) "
            f"VALUES(?,'R115업체','협력사',?,'{case_no}.jpg','{case_no}.jpg','image/jpeg','jpg',1,"
            f"       'r115sha_{case_no}','완료','승인',?)", (cid, partner_id, DB.now()))
        return cid

    p1 = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R115업체','시행사','활성')").lastrowid

    # ── [2] 검수 승인이 진행 중인 변경견적을 막는다 ─────────────────────
    cid1 = _mk_ready_case("R115-C1", p1)
    coid1 = conn.execute(
        "INSERT INTO change_orders(case_id,round,reason,requested_amount,status,"
        "                          combined_amount,created_at) "
        "VALUES(?,1,'실사 증액','추가 공사','원업체제안',5000000,?)",
        (cid1, DB.now())).lastrowid
    conn.commit()

    r1 = admin.post(f"/api/cases/{cid1}/approve", headers=_hdr)
    chk(r1.status_code == 409 and r1.get_json().get("code") == "CHANGE_ORDER_ACTIVE",
        "★★★ 진행 중인 변경견적(원업체제안)이 있으면 검수 승인을 막는다"
        "(예전엔 그대로 통과해 발주처가 확인한 증액분이 옛 낙찰가로 굳었다)",
        (r1.status_code, r1.get_json()))
    sett1 = conn.execute("SELECT id FROM settlements WHERE case_id=?", (cid1,)).fetchone()
    chk(sett1 is None, "STEP 막힌 요청이 정산을 안 만들었다", sett1)

    # 변경견적이 이미 종결(철회)된 사건은 여전히 정상적으로 검수 승인된다 — 과잉차단 아님
    cid2 = _mk_ready_case("R115-C2", p1)
    conn.execute(
        "INSERT INTO change_orders(case_id,round,reason,requested_amount,status,created_at) "
        "VALUES(?,1,'실사 증액','추가 공사','철회',?)", (cid2, DB.now()))
    conn.commit()
    r2 = admin.post(f"/api/cases/{cid2}/approve", headers=_hdr)
    chk(r2.status_code == 200,
        "STEP 변경견적이 이미 철회된 사건은 여전히 정상적으로 검수 승인된다(과잉차단 아님)",
        (r2.status_code, r2.get_data(as_text=True)[:200]))

    # ── [3] 완료승인 독촉이 취소된 정산은 막는다 ─────────────────────────
    iid = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('R115보험','활성')").lastrowid
    cid3 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer,insurer_id,is_demo) "
        "VALUES('R115-C3','정산진행','가드레일','서울','R115보험',?,0)", (iid,)).lastrowid
    sid_voided = conn.execute(
        "INSERT INTO settlements(case_no,case_id,insurer,insurer_id,amount,fee,payout,"
        "                        insurer_approved,void_status,created_at) "
        "VALUES('R115-C3',?,?,?,4000000,200000,3800000,0,'취소',?)",
        (cid3, "R115보험", iid, DB.now())).lastrowid
    conn.commit()
    r3 = admin.post(f"/api/settlements/{sid_voided}/remind-approval", headers=_hdr)
    chk(r3.status_code == 409,
        "★★★ 취소된 정산에는 완료승인 독촉을 못 보낸다"
        "(예전엔 그대로 통과해 사라진 정산을 두고 발주처를 계속 졸랐다)",
        (r3.status_code, r3.get_json()))
    remind_notif = conn.execute(
        "SELECT 1 FROM notifications WHERE ntype='완료승인독촉' AND case_id=?", (cid3,)).fetchone()
    chk(remind_notif is None, "STEP 막힌 요청이 알림을 안 보냈다", remind_notif)

    # 취소 안 된 정산은 여전히 정상적으로 독촉할 수 있다 — 과잉차단 아님
    cid4 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer,insurer_id,is_demo) "
        "VALUES('R115-C4','정산진행','가드레일','서울','R115보험',?,0)", (iid,)).lastrowid
    sid_live = conn.execute(
        "INSERT INTO settlements(case_no,case_id,insurer,insurer_id,amount,fee,payout,"
        "                        insurer_approved,created_at) "
        "VALUES('R115-C4',?,?,?,4000000,200000,3800000,0,?)",
        (cid4, "R115보험", iid, DB.now())).lastrowid
    conn.commit()
    r4 = admin.post(f"/api/settlements/{sid_live}/remind-approval", headers=_hdr)
    chk(r4.status_code == 200,
        "STEP 취소 안 된 정산은 여전히 정상적으로 독촉된다(과잉차단 아님)",
        (r4.status_code, r4.get_data(as_text=True)[:200]))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드115 서버측 준비/실행", f"{type(e).__name__} {e}")
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
