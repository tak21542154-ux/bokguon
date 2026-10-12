# -*- coding: utf-8 -*-
"""스캔 62라운드 회귀 — 변경견적 원업체 수락(api_co_decision)에 업체 상태·건설업
   등록 재확인이 빠져 있었다(HIGH).

  조사 에이전트가 정적 추적(계약금액을 바꾸는 5곳 전수 대조)으로 짚고, 이번
  라운드에서 실측(실제 test_client)으로 재확인한 결함:

  계약금액을 바꾸는 자리는 정확히 5곳이다(보험사 낙찰·관리자 낙찰·전체재경매·
  1차합의·변경견적 원업체 수락) — 앞의 4곳은 이미 라운드52에서 "제안이 오간
  사이 업체가 경고로 내려가거나 무등록이 확정될 수 있다"며 업체 상태(활성)와
  건설업 등록(license_block_reason) 을 확정 시점에 다시 본다. 딱 하나,
  api_co_decision(원업체가 스스로 수락/거절하는 라우트)만 이 재확인이 없었다.
  '경고' 상태는 로그인을 막지 않는다(신규 배정만 끊는다는 게 이 서비스의
  명시적 설계) — 그래서 세션은 살아 있는데, 그 세션으로 수락을 누르면 사실상
  새 배정과 같은 효과(계약금액 확정)가 조용히 일어난다.

      python test_scan_round62_fixes.py
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
DISPATCH_SRC = read("dispatch.py")

print("═" * 72)
print("  스캔 62라운드 회귀 — api_co_decision 업체상태·등록 재확인 누락(계약금액 5곳 중 유일)")
print("═" * 72)


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
n_award_sites = APP_SRC.count("award_amount=?") + DISPATCH_SRC.count("award_amount=?")
chk(n_award_sites == 5, "계약금액을 바꾸는 UPDATE 가 정확히 5곳이다(전제 확인, app.py+dispatch.py)",
    n_award_sites)

decision_body = _body(APP_SRC, "api_co_decision")
chk('code": "PARTNER_NOT_ACTIVE"' in decision_body,
    "★★★ api_co_decision — 업체 상태(활성) 재확인이 이제 있다")
chk("DP.license_block_reason(conn, pid)" in decision_body,
    "★★★ api_co_decision — 건설업 등록(무등록) 재확인이 이제 있다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 서버(test_client)로 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round62_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    _tok = "regress-round62-csrf-token"
    _hdr = {"X-CSRF-Token": _tok}
    CATEGORY = "누수·배관·설비"

    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('검증보험사62','활성')").lastrowid

    # ── ① 경고 상태(로그인은 살아있음) 업체가 수락을 시도 ──
    p_warn = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('경고업체62','시공사','경고')"
    ).lastrowid
    cid1 = conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,partner_id,partner_name,"
        "                  award_amount,category,region) "
        "VALUES(?,'시공중',?,?,?,?,3000000,?,'서울')",
        ("62D-0001", "검증보험사62", iid, p_warn, "경고업체62", CATEGORY)).lastrowid
    coid1 = conn.execute(
        "INSERT INTO change_orders(case_id,round,status,incumbent_partner_id,incumbent_amount,"
        "                          combined_amount,add_low,insurer_ack,insurer_ack_amount) "
        "VALUES(?,1,'원업체제안',?,3000000,5000000,2000000,'확인',5000000)",
        (cid1, p_warn)).lastrowid

    # ── ② 무등록 확정 업체(활성 상태지만 license_status='무등록')가 수락을 시도 ──
    p_unlic = conn.execute(
        "INSERT INTO partners(name,partner_type,status,license_status) "
        "VALUES('무등록업체62','시공사','활성','무등록')"
    ).lastrowid
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,partner_id,partner_name,"
        "                  award_amount,category,region) "
        "VALUES(?,'시공중',?,?,?,?,3000000,?,'서울')",
        ("62D-0002", "검증보험사62", iid, p_unlic, "무등록업체62", CATEGORY)).lastrowid
    coid2 = conn.execute(
        "INSERT INTO change_orders(case_id,round,status,incumbent_partner_id,incumbent_amount,"
        "                          combined_amount,add_low,insurer_ack,insurer_ack_amount) "
        "VALUES(?,1,'원업체제안',?,3000000,5000000,2000000,'확인',5000000)",
        (cid2, p_unlic)).lastrowid

    # ── 대조군 — 진짜 활성·등록확인 업체는 정상적으로 수락된다 ──
    p_ok = conn.execute(
        "INSERT INTO partners(name,partner_type,status,license_status) "
        "VALUES('정상업체62','시공사','활성','등록확인')"
    ).lastrowid
    cid3 = conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,partner_id,partner_name,"
        "                  award_amount,category,region) "
        "VALUES(?,'시공중',?,?,?,?,3000000,?,'서울')",
        ("62D-0003", "검증보험사62", iid, p_ok, "정상업체62", CATEGORY)).lastrowid
    coid3 = conn.execute(
        "INSERT INTO change_orders(case_id,round,status,incumbent_partner_id,incumbent_amount,"
        "                          combined_amount,add_low,insurer_ack,insurer_ack_amount) "
        "VALUES(?,1,'원업체제안',?,3000000,5000000,2000000,'확인',5000000)",
        (cid3, p_ok)).lastrowid
    conn.commit(); conn.close()

    def _accept_as(pid, coid):
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["partner_id"] = pid; sess["_csrf"] = _tok
        return c.post(f"/api/change-orders/{coid}/decision", json={"accept": True}, headers=_hdr)

    r_warn = _accept_as(p_warn, coid1)
    chk(r_warn.status_code == 409 and (r_warn.get_json() or {}).get("code") == "PARTNER_NOT_ACTIVE",
        "★★★ '경고' 상태(로그인은 살아있음) 업체의 수락이 이제 막힌다"
        "(고치기 전엔 그대로 계약금액이 확정됐다)", (r_warn.status_code, r_warn.get_json()))

    r_unlic = _accept_as(p_unlic, coid2)
    chk(r_unlic.status_code == 409 and (r_unlic.get_json() or {}).get("code") == "NO_LICENSE",
        "★★★ 무등록 확정 업체의 수락도 막힌다"
        "(고치기 전엔 무등록 하도급이 그대로 성립했다)", (r_unlic.status_code, r_unlic.get_json()))

    r_ok = _accept_as(p_ok, coid3)
    chk(r_ok.status_code == 200,
        "★ 대조군 — 활성·등록확인 업체는 정상적으로 수락된다(과잉차단 아님)",
        (r_ok.status_code, r_ok.get_json()))

    conn = DB.get_db()
    aw1 = conn.execute("SELECT award_amount FROM cases WHERE id=?", (cid1,)).fetchone()[0]
    aw2 = conn.execute("SELECT award_amount FROM cases WHERE id=?", (cid2,)).fetchone()[0]
    aw3 = conn.execute("SELECT award_amount FROM cases WHERE id=?", (cid3,)).fetchone()[0]
    conn.close()
    chk(aw1 == 3000000, "★★ 막힌 건(경고)은 award_amount 가 옛 금액(3,000,000)에 그대로 머문다", aw1)
    chk(aw2 == 3000000, "★★ 막힌 건(무등록)도 award_amount 가 그대로 머문다", aw2)
    chk(aw3 == 5000000, "★ 대조군은 award_amount 가 합산가(5,000,000)로 정상 확정된다", aw3)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드62 실측 준비/실행", f"{type(e).__name__} {e}")
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
