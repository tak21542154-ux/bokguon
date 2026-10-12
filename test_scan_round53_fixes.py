# -*- coding: utf-8 -*-
"""스캔 53라운드 회귀 — 협력사 조직 하위계정 등급 게이트 누락 4곳.

  조사 에이전트(+직접 코드 대조)가 실측으로 증명한 결함: "되돌릴 수 없는 확정
  행위"는 이 저장소가 8곳에서 이미 require_portal_role("partner","중간관리자")
  로 조회 등급(하위관리자)을 막고 있는데(입찰·완료보고·출동수락 등), 그와
  똑같이 되돌릴 수 없는 4곳이 require_partner(로그인만)로 남아 있었다:

    ① 사업자번호 최초 등록 — 한 번 쓰면 본인도 조직 최고관리자도 못 고친다.
       건설업 등록 조사(KISCON)의 조회 키이자 라운드52 도급 적법성 판정
       (license_block_reason)의 뿌리라, 잘못 박히면 그 판정 전체가 오염된다.
    ② 하자 재시공 완료 보고 — 지급 관문(DEFECT_OPEN)을 여는 회사 명의 선언.
    ③ 하자 귀책 이의 — 하자당 1회뿐, 되돌리는 경로가 전 코드에 없다.
    ④ 출동 수배 거절 — 회복 수배에서 영구 배제로 남는다(형제 셋인 수락·도착·
       수선불가에는 이미 문턱이 있었다).

  ①만 라우트 전체가 아니라 biz_no 분기에만 걸었다(연락처·주소는 하위관리자도
  정당 업무이므로 열어 둔다). ②③④는 형제와 같은 데코레이터 한 줄로 맞췄다.

      python test_scan_round53_fixes.py
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


APP_SRC = read("app.py")
TPL_SRC = read(os.path.join("templates", "partner_portal.html"))

print("═" * 72)
print("  스캔 53라운드 회귀 — 협력사 하위계정 등급 게이트 누락 4곳")
print("═" * 72)


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
prof = _body(APP_SRC, "api_partner_profile_update")
chk('PORTAL_ROLE_RANK.get(_portal_role(), 0) < PORTAL_ROLE_RANK["중간관리자"]' in prof
    and '"PORTAL_FORBIDDEN"' in prof,
    "★★★ ① api_partner_profile_update — biz_no 분기에 등급 문턱이 생겼다")
chk('for f in ("ceo", "phone", "email", "address", "region")' in prof,
    "① 연락처·주소 필드는 여전히 문턱 없이 열려 있다(과잉차단 방지 확인)")

for fn_name, label in (("api_partner_defect_resolve", "② api_partner_defect_resolve"),
                        ("api_partner_defect_dispute", "③ api_partner_defect_dispute"),
                        ("api_partner_dispatch_decline", "④ api_partner_dispatch_decline")):
    #  ⚠ 데코레이터는 함수 정의 위에 있어 _body() 범위 밖이다 — 정의 직전 8줄만 본다.
    idx = APP_SRC.index(f"\ndef {fn_name}(")
    head = APP_SRC[max(0, idx - 400):idx]
    chk('require_portal_role("partner", "중간관리자")' in head,
        f"★★★ {label} — require_partner 대신 형제와 같은 등급 문턱을 쓴다")

# 프론트 — 등급 없는 사람에게 눌러도 403 날 버튼을 보여 주지 않는가
chk(TPL_SRC.count('data-act="resolveForm"') >= 1 and "canAct() ? `<button class=\"btn a sm\" data-act=\"resolveForm\"" in TPL_SRC,
    "★ partner_portal.html — 완료 보고 버튼이 canAct() 로 가려졌다")
chk("canAct() ? `<button class=\"btn g sm\" data-act=\"disputeForm\"" in TPL_SRC,
    "★ partner_portal.html — 귀책 이의 버튼이 canAct() 로 가려졌다")
chk('canAct() ? `<button class="btn g sm" data-act="dpDecline"' in TPL_SRC,
    "★ partner_portal.html — 거절 버튼이 canAct() 로 가려졌다")
chk('canAct() ? `<input id="mp_biz"' in TPL_SRC,
    "★ partner_portal.html — 사업자번호 입력칸이 canAct() 로 가려졌다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 서버(test_client)로 하위관리자 세션을 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round53_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

_seq = [0]


def _no(prefix):
    _seq[0] += 1
    return f"{prefix}{_seq[0]:04d}"


try:
    import db as DB
    DB.init_db()
    import app as A

    client = A.app.test_client()
    _tok = "regress-round53-csrf-token"
    _hdr = {"X-CSRF-Token": _tok}

    def _sess(sess, pid, role):
        sess["partner_id"] = pid
        sess["portal_role"] = role
        sess["_csrf"] = _tok

    conn = DB.get_db()
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('검증조직53','시행사','활성')"
    ).lastrowid
    conn.commit(); conn.close()

    # ── ① 사업자번호 — 하위관리자는 등록 못 한다 ──
    with client.session_transaction() as sess:
        _sess(sess, pid, "하위관리자")
    r1 = client.patch("/api/partner/profile", json={"biz_no": "1208136214"}, headers=_hdr)
    d1 = r1.get_json()
    chk(r1.status_code == 403 and d1.get("code") == "PORTAL_FORBIDDEN",
        "★★★ ① 하위관리자는 사업자번호를 등록할 수 없다(고치기 전엔 200)", (r1.status_code, d1))
    conn = DB.get_db()
    biz_after = conn.execute("SELECT biz_no FROM partners WHERE id=?", (pid,)).fetchone()["biz_no"]
    conn.close()
    chk(not biz_after, "① 실제로 DB 에 사업자번호가 안 박혔다", biz_after)

    # 대조군 — 같은 하위관리자가 연락처는 그대로 고칠 수 있다(과잉차단 아님)
    r1b = client.patch("/api/partner/profile", json={"phone": "010-1234-5678"}, headers=_hdr)
    chk(r1b.status_code == 200, "★ 대조군 — 하위관리자도 연락처는 그대로 고칠 수 있다", r1b.get_json())

    # 대조군 — 중간관리자는 사업자번호를 등록할 수 있다
    with client.session_transaction() as sess:
        _sess(sess, pid, "중간관리자")
    r1c = client.patch("/api/partner/profile", json={"biz_no": "1208136214"}, headers=_hdr)
    chk(r1c.status_code == 200, "★ 대조군 — 중간관리자는 사업자번호를 그대로 등록할 수 있다",
        (r1c.status_code, r1c.get_json()))

    # ── ② 하자 완료 보고 ──
    conn = DB.get_db()
    cid_d = conn.execute(
        "INSERT INTO cases(case_no,status,partner_id,category,region) "
        "VALUES(?,'완료',?,'금속','서울')", (_no("53D-"), pid)).lastrowid
    did_resolve = conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,partner_id,title,status) "
        "VALUES(?,?,?,?,'테스트 하자','접수')", (_no("53DF-"), cid_d, _no("53D-"), pid)).lastrowid
    did_dispute = conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,partner_id,title,status) "
        "VALUES(?,?,?,?,'테스트 하자2','접수')", (_no("53DF-"), cid_d, _no("53D-"), pid)).lastrowid
    conn.commit(); conn.close()

    with client.session_transaction() as sess:
        _sess(sess, pid, "하위관리자")
    r2 = client.post(f"/api/partner/defects/{did_resolve}/resolve",
                     json={"resolution": "재시공 완료"}, headers=_hdr)
    d2 = r2.get_json()
    chk(r2.status_code == 403 and d2.get("code") == "PORTAL_FORBIDDEN",
        "★★★ ② 하위관리자는 하자 완료 보고를 할 수 없다(고치기 전엔 200)", (r2.status_code, d2))
    conn = DB.get_db()
    st_after = conn.execute("SELECT status FROM defects WHERE id=?", (did_resolve,)).fetchone()["status"]
    conn.close()
    chk(st_after == "접수", "② 하자 상태가 오염되지 않았다(그대로 접수)", st_after)

    # ── ③ 하자 귀책 이의 ──
    r3 = client.post(f"/api/partner/defects/{did_dispute}/dispute",
                     json={"reason": "저희 시공 문제가 아니라고 판단합니다"}, headers=_hdr)
    d3 = r3.get_json()
    chk(r3.status_code == 403 and d3.get("code") == "PORTAL_FORBIDDEN",
        "★★★ ③ 하위관리자는 귀책 이의를 제기할 수 없다(고치기 전엔 200)", (r3.status_code, d3))
    conn = DB.get_db()
    dr_after = conn.execute(
        "SELECT dispute_reason FROM defects WHERE id=?", (did_dispute,)).fetchone()["dispute_reason"]
    conn.close()
    chk(not dr_after, "③ 이의가 실제로 기록되지 않았다(1회뿐인 창구가 소진되지 않았다)", dr_after)

    # 대조군 — 중간관리자는 이 둘을 그대로 할 수 있다
    with client.session_transaction() as sess:
        _sess(sess, pid, "중간관리자")
    r2c = client.post(f"/api/partner/defects/{did_resolve}/resolve",
                      json={"resolution": "재시공 완료"}, headers=_hdr)
    chk(r2c.status_code == 200, "★ 대조군 — 중간관리자는 하자 완료 보고를 그대로 할 수 있다",
        (r2c.status_code, r2c.get_json()))
    r3c = client.post(f"/api/partner/defects/{did_dispute}/dispute",
                      json={"reason": "저희 시공 문제가 아니라고 판단합니다"}, headers=_hdr)
    chk(r3c.status_code == 200, "★ 대조군 — 중간관리자는 귀책 이의를 그대로 제기할 수 있다",
        (r3c.status_code, r3c.get_json()))

    # ── ④ 출동 수배 거절 ──
    conn = DB.get_db()
    cid_p = conn.execute(
        "INSERT INTO cases(case_no,status,category,region) VALUES(?,'접수','금속','서울')",
        (_no("53P-"),)).lastrowid
    did_dp = conn.execute(
        "INSERT INTO dispatches(case_id,round,status,due_at,created_at) "
        "VALUES(?,1,'모집중',datetime('now','+9 hours','+30 minutes'),datetime('now','+9 hours'))",
        (cid_p,)).lastrowid
    conn.execute(
        "INSERT INTO dispatch_calls(dispatch_id,partner_id,partner_name,call_order,"
        "                           notified_at,created_at) "
        "VALUES(?,?,'검증조직53',1,datetime('now','+9 hours'),datetime('now','+9 hours'))",
        (did_dp, pid))
    conn.commit(); conn.close()

    with client.session_transaction() as sess:
        _sess(sess, pid, "하위관리자")
    r4 = client.post(f"/api/partner/dispatches/{did_dp}/decline", headers=_hdr)
    d4 = r4.get_json()
    chk(r4.status_code == 403 and d4.get("code") == "PORTAL_FORBIDDEN",
        "★★★ ④ 하위관리자는 출동 수배를 거절할 수 없다(고치기 전엔 200)", (r4.status_code, d4))
    conn = DB.get_db()
    resp_after = conn.execute(
        "SELECT response FROM dispatch_calls WHERE dispatch_id=? AND partner_id=?",
        (did_dp, pid)).fetchone()["response"]
    conn.close()
    chk(not resp_after, "④ 실제로 거절이 기록되지 않았다(회복 수배 후보에서 안 빠졌다)", resp_after)

    # 대조군 — 중간관리자는 거절할 수 있다
    with client.session_transaction() as sess:
        _sess(sess, pid, "중간관리자")
    r4c = client.post(f"/api/partner/dispatches/{did_dp}/decline", headers=_hdr)
    chk(r4c.status_code == 200, "★ 대조군 — 중간관리자는 출동 수배를 그대로 거절할 수 있다",
        (r4c.status_code, r4c.get_json()))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드53 실측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
