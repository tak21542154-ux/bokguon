# -*- coding: utf-8 -*-
"""스캔 192라운드 회귀 — 두 결함.

  ① app.py api_case_cancel_award(): 1차 합의로 낙찰된 사건(field_agreements.
    status='합의')의 배정을 취소해도 그 합의 행을 정리하지 않았다. bid_cap_of()
    (4527행)는 오직 이 표의 '결렬' 존재 여부로만 재개설 경매가 1차(가견적=상한)
    인지 2차(가견적=하한, 상한없음)인지 정하는데, '합의'는 '결렬'이 아니므로
    재공고는 항상 1차 규칙으로 떨어진다 — 현장 실측으로 이미 부족하다고 확정된
    접수 당시 가견적이 재입찰의 상한으로 다시 걸린다.

  ② legal_docs.py·static/form.js: "면허번호"를 "협력업체 계정 등록(입점 승인
    후)" 필수 항목으로 적었는데, 그 시점에 그런 필드는 없다. 실제로 파트너가
    자유기재하는 "보유 면허·등록업종"은 승인 *전* 신청 단계의 선택 항목이고,
    "면허번호"라는 구체적 값은 관리자가 KISCON 을 조회해 사후 기록하는
    별개의 값(api_partner_license, 파트너가 제출하지 않음)이다.

      python test_scan_round192_fixes.py
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")
FORM_SRC = read("static/form.js")
LEGAL_SRC = read("legal_docs.py")

print("=" * 72)
print("  스캔 192라운드 회귀 — cancel-award 의 1차합의 잔재 · 면허번호 고지 오류")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_case_cancel_award(cid):")
i1 = APP_SRC.index("\ndef ", i0 + 1)
body = APP_SRC[i0:i1]
chk("UPDATE field_agreements" in body and "DP.AG_BROKEN" in body and "DP.AG_DONE" in body,
    "★★★★ cancel-award 가 '합의' 상태이던 field_agreements 를 '결렬'로 닫는다"
    "(고치기 전엔 이 함수 전체에서 field_agreements 참조가 0건이었다)")

_row_account = LEGAL_SRC[LEGAL_SRC.index("협력업체 계정 등록"):
                          LEGAL_SRC.index("정산 계좌 정보")]
chk("면허번호" not in _row_account,
    "★★★ 공식 개인정보처리방침 '계정 등록(승인 후)' 필수 항목에서 "
    "'면허번호'가 빠졌다(실제로 그 시점에 그런 필드가 없다)")
_row_apply_optional = LEGAL_SRC[LEGAL_SRC.index("면허·보험 보유 여부") - 20:
                                  LEGAL_SRC.index("면허·보험 보유 여부") + 20]
chk("면허·등록업종" in _row_apply_optional,
    "★★★ '면허·등록업종'(실제 파트너 자유기재 필드)이 입점신청 선택 항목으로 옮겨졌다")
chk("면허·등록업종" in FORM_SRC,
    "★★★ CONSENT_SPEC.partner.items 에도 같은 항목이 반영됐다")

# ============================================================
print("\n[2] 실행 — 1차합의로 낙찰된 사건의 낙찰을 취소하면 재개설 경매가 "
      "2차 규칙(가견적=하한, 상한없음)으로 바뀐다")
# ------------------------------------------------------------
_tmpdir_env_set = False
try:
    import tempfile
    _tmpdir = tempfile.mkdtemp(prefix="round192_")
    os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
    os.environ["BOKGUON_ENV"] = "dev"
    os.environ["BOKGUON_SEED_DEMO"] = "0"
    sys.path.insert(0, HERE)
    _tmpdir_env_set = True

    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    now = DB.now()

    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r192admin','x','검증','중간관리자')")
    iid = conn.execute(
        "INSERT INTO insurers(name,status,login_id,created_at) "
        "VALUES('R192보험', '활성', 'r192i', ?)", (now,)).lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name, status, license_status, region, created_at) "
        "VALUES('R192업체', '활성', '확인됨', '서울', ?)", (now,)).lastrowid

    #  접수 당시 데스크 가견적(300만원) — 현장 실측 뒤 1차합의로 550만원에
    #  보험사 승인을 거쳐 낙찰(시공중)됐다고 가정. est_price 는 0이 아니었으므로
    #  settle_agreement 의 백필 가드(est_price=0일 때만 채움)가 안 건드려 그대로다.
    cid = conn.execute(
        "INSERT INTO cases(case_no, status, category, region, insurer_id, "
        "                   est_price, partner_id, partner_name, award_amount, "
        "                   award_route, awarded_at, is_demo, created_at) "
        "VALUES('R192-001', '시공중', '유리', '서울', ?, 3000000, ?, 'R192업체', "
        "       5500000, '1차합의', ?, 0, ?)",
        (iid, pid, now, now)).lastrowid
    fid = conn.execute(
        "INSERT INTO field_agreements(case_id, partner_id, partner_name, "
        "                              field_amount, status, created_at) "
        "VALUES(?, ?, 'R192업체', 5500000, '합의', ?)", (cid, pid, now)).lastrowid
    conn.commit()

    c_before = conn.execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone()
    cap_before = A.bid_cap_of(conn, c_before)

    admin = A.app.test_client()
    atok = "r192-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r192admin"; sess["admin_role"] = "중간관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = atok
    ahdr = {"X-CSRF-Token": atok}

    resp = admin.post(f"/api/cases/{cid}/cancel-award",
                       json={"reason": "낙찰업체 부도로 재공고합니다"}, headers=ahdr)
    j = resp.get_json() or {}

    fa_after = conn.execute("SELECT status FROM field_agreements WHERE id=?", (fid,)).fetchone()
    c_after = conn.execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone()
    cap_after = A.bid_cap_of(conn, c_after)

    chk(resp.status_code == 200 and j.get("ok") is True,
        "낙찰 취소 자체는 정상 성공한다(회귀 없음)", (resp.status_code, j))
    chk(cap_before[3] == 1,
        "준비: 취소 전엔 bid_cap_of 가 1차(가견적=상한)로 판정한다"
        "(field_agreements 가 아직 '합의' 상태라 '결렬' 조회에 안 걸림)", cap_before)
    chk(fa_after["status"] == "결렬",
        "★★★★ 낙찰 취소와 동시에 '합의'였던 field_agreements 가 '결렬'로 닫힌다"
        "(고치기 전엔 '합의' 그대로 남았다)", fa_after["status"] if fa_after else None)
    chk(cap_after[3] == 2,
        "★★★★ 재개설된 경매는 이제 2차 규칙(가견적=하한, 상한없음)으로 판정된다"
        "(고치기 전엔 취소 후에도 1차로 남아 300만원 상한이 재입찰에 다시 걸렸다)",
        cap_after)
    chk(cap_after[1] == 0,
        "★★★ 2차 규칙이므로 상한이 없다(0)", cap_after)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드192 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
