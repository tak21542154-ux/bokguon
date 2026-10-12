# -*- coding: utf-8 -*-
"""스캔 52라운드 회귀 — 도급이 실제로 만들어지는 자리 4곳의 무등록·비활성 재확인 누락.

  조사 에이전트(+직접 코드 대조)가 실측으로 증명한 결함: 무등록·비활성 배제는
  지금까지 **진입 문**에만 있었다(후보선정·직접배정·통값입찰·재경매입찰 — 전부
  이전 라운드에서 이미 막음). 그런데 도급이 **실제로 확정되는** 자리는 하나도
  다시 보지 않았다 — 선택과 확정 사이(수배 30분, 보험사 승인 대기 수일)에
  조사로 '무등록'이 확정되거나 업체가 퇴출돼도 아무도 다시 보지 않았다
  (건설산업기본법 §25조 제2항).

  실측으로 확인된 자리 4곳:
    ① dispatch.settle_agreement — 1차 합의 승인. 활성·무등록 **둘 다** 없었다.
    ② app.api_insurer_award    — 보험사 원경매 낙찰. 활성은 있는데 무등록이 없었다.
    ③ app.api_case_award       — 어드민 원경매 낙찰. 위와 같다.
    ④ app.api_co_close_full    — 전체재경매 마감(도급 전체를 갈아치움). 위와 같다.
       ⚠ 이 자리는 조사 에이전트 보고서에 없었다 — round8 자체 회귀
         (`app_s.count('"PARTNER_NOT_ACTIVE"') >= 3`)를 근거로 직접 대조해 찾았다.
  덤으로 /api/reauctions 가 형제(open-auctions)에는 있는 데모 필터를 빠뜨려
  협력사가 투찰 못 할 데모 재경매를 목록에서 보게 되는 것도 함께 고쳤다.

      python test_scan_round52_fixes.py
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
print("  스캔 52라운드 회귀 — 도급 확정 4곳의 무등록·비활성 재확인 누락")
print("═" * 72)


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
chk("def license_block_reason(conn, partner_id)" in DISPATCH_SRC,
    "★ dispatch.license_block_reason 공유 헬퍼가 생겼다")

settle = _body(DISPATCH_SRC, "settle_agreement")
chk('pt["status"] != "활성"' in settle,
    "★★★ ① settle_agreement — 출동 업체의 활성 재확인이 생겼다(원래 없었다)")
chk("license_block_reason(conn, a[\"partner_id\"])" in settle,
    "★★★ ① settle_agreement — 무등록 재확인이 생겼다(원래 없었다)")

for fn_name, label in (("api_insurer_award", "② api_insurer_award"),
                        ("api_case_award", "③ api_case_award"),
                        ("api_co_close_full", "④ api_co_close_full")):
    body = _body(APP_SRC, fn_name)
    chk('DP.license_block_reason(conn, b["partner_id"])' in body and '"NO_LICENSE"' in body,
        f"★★★ {label} — 무등록 재확인이 생겼다(활성 재확인만 있었다)")
    chk('"PARTNER_NOT_ACTIVE"' in body,
        f"{label} — 기존 활성 재확인은 그대로 있다(안 건드림, round8 회귀 보존)")

chk(APP_SRC.count('DP.license_block_reason(conn, b["partner_id"])') == 3,
    "★ 세 낙찰 경로 모두 같은 공유 헬퍼 한 곳을 부른다(중복 구현 아님)",
    APP_SRC.count('DP.license_block_reason(conn, b["partner_id"])'))

reau = _body(APP_SRC, "api_reauctions")
chk("COALESCE(c.is_demo,0)=0" in reau,
    "★ api_reauctions — 데모 재경매 필터가 생겼다(형제 open-auctions 에는 있었다)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 1차 합의(dispatch.settle_agreement) 전체 흐름 실측")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round52_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import dispatch as DPX

    _seq = [0]

    def _no(prefix):
        _seq[0] += 1
        return f"{prefix}{_seq[0]:04d}"

    def _run_agreement_chain(conn, partner_status, partner_license, label):
        """수배 개설 → claim → arrive → open_agreement → settle_agreement(agreed=True)
        까지 진짜 흐름 그대로 실행하고 (settle 성공여부, 메시지, 최종 사건행) 을 돌려준다."""
        pid = conn.execute(
            "INSERT INTO partners(name,partner_type,status,license_status) "
            "VALUES(?,'시행사',?,?)", (_no(f"{label}업체"), partner_status, partner_license)
        ).lastrowid
        cid = conn.execute(
            "INSERT INTO cases(case_no,status,category,region) "
            "VALUES(?,'접수','금속','서울')", (_no("52C-"),)).lastrowid
        did = conn.execute(
            "INSERT INTO dispatches(case_id,round,status,due_at,created_at) "
            "VALUES(?,1,?,datetime('now','+9 hours','+30 minutes'),datetime('now','+9 hours'))",
            (cid, DPX.ST_OPEN)).lastrowid
        conn.execute(
            "INSERT INTO dispatch_calls(dispatch_id,partner_id,partner_name,call_order,"
            "                           notified_at,created_at) "
            "VALUES(?,?,?,1,datetime('now','+9 hours'),datetime('now','+9 hours'))",
            (did, pid, f"{label}업체"))
        conn.commit()

        ok_c, msg_c, _ = DPX.claim(conn, did, pid, f"{label}업체")
        ok_a, msg_a = DPX.arrive(conn, did, pid, 3, field_estimate=850000)
        aid = DPX.open_agreement(conn, cid, dispatch_id=did,
                                 our_staff="검증", insurer_staff="검증보험")
        ok_s, msg_s = DPX.settle_agreement(
            conn, aid, agreed=True,
            approver={"org_id": 1, "user_id": 1, "name": "검증", "role": "최고관리자"})
        row = conn.execute("SELECT status, partner_id FROM cases WHERE id=?", (cid,)).fetchone()
        return ok_c, ok_a, ok_s, msg_s, dict(row)

    conn = DB.get_db()
    # ── 무등록 업체 ──
    c1, a1, s1, m1, r1 = _run_agreement_chain(conn, "활성", "무등록", "무등록")
    chk(c1 and a1, "① (사전조건) 무등록 업체도 claim·arrive 는 그대로 성공한다", (c1, a1))
    chk(s1 is False, "★★★ ① 무등록 업체는 1차 합의 승인이 막힌다(고치기 전엔 True)", (s1, m1))
    chk(r1["status"] == "접수" and r1["partner_id"] is None,
        "① 막힌 뒤 사건 상태가 오염되지 않았다(그대로 접수)", r1)

    # ── 퇴출된 업체 ──
    c2, a2, s2, m2, r2 = _run_agreement_chain(conn, "퇴출", "미확인", "퇴출")
    chk(c2 and a2, "② (사전조건) 퇴출 업체도 claim·arrive 는 그대로 성공한다", (c2, a2))
    chk(s2 is False, "★★★ ② 퇴출 업체는 1차 합의 승인이 막힌다(고치기 전엔 True)", (s2, m2))
    chk(r2["status"] == "접수" and r2["partner_id"] is None,
        "② 막힌 뒤 사건 상태가 오염되지 않았다(그대로 접수)", r2)

    # ── 대조군 — 정상(활성·미확인) 업체는 그대로 성립한다(과잉차단 아님) ──
    c3, a3, s3, m3, r3 = _run_agreement_chain(conn, "활성", "미확인", "정상")
    chk(s3 is True, "★ 대조군 — 정상 업체는 1차 합의가 그대로 성립한다(과잉차단 아님)", (s3, m3))
    chk(r3["status"] == "시공중" and r3["partner_id"] is not None,
        "대조군 — 사건이 정상적으로 시공중으로 배정됐다", r3)
    conn.close()

    # ══════════════════════════════════════════════════════════
    print("\n[3] 실행 — 경매 낙찰 확정 라우트 2곳(보험사·전체재경매마감) HTTP 실측")
    # ──────────────────────────────────────────────────────────
    import app as A
    client = A.app.test_client()
    _tok = "regress-round52-csrf-token"
    _hdr = {"X-CSRF-Token": _tok}

    conn = DB.get_db()
    admin_u = conn.execute(
        "INSERT INTO admins(username,password_hash,name,role) "
        "VALUES('admin52','x','검증','최고관리자')").lastrowid
    iid = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('검증보험사52','활성')").lastrowid
    p_nolic = conn.execute(
        "INSERT INTO partners(name,partner_type,status,license_status) "
        "VALUES('검증무등록52-award','시공사','활성','무등록')").lastrowid
    p_ok = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('검증정상52-award','시공사','활성')"
    ).lastrowid
    conn.commit(); conn.close()

    def _admin_sess(sess):
        sess["admin"] = "admin52"; sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = _tok

    def _insurer_sess(sess):
        sess["insurer_id"] = iid; sess["insurer_name"] = "검증보험사52"; sess["_csrf"] = _tok

    # ── ② 보험사 낙찰 — 무등록 업체 ──
    conn = DB.get_db()
    cid_i = conn.execute(
        "INSERT INTO cases(case_no,status,insurer_id,category,region) "
        "VALUES(?,'입찰중',?,'금속','서울')", (_no("52I-"), iid)).lastrowid
    auid_i = conn.execute("INSERT INTO auctions(case_id,status) VALUES(?,'진행')", (cid_i,)).lastrowid
    bid_i = conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount) VALUES(?,?,?,2500000)",
        (auid_i, p_nolic, "검증무등록52-award")).lastrowid
    conn.commit(); conn.close()

    with client.session_transaction() as sess:
        _insurer_sess(sess)
    ri = client.post(f"/api/insurer/cases/{cid_i}/award", json={"bid_id": bid_i}, headers=_hdr)
    di = ri.get_json()
    chk(ri.status_code == 409 and di.get("code") == "NO_LICENSE",
        "★★★ ② 보험사 낙찰 — 무등록 업체는 낙찰이 막힌다(고치기 전엔 200)", (ri.status_code, di))

    # 대조군 — 정상 업체는 그대로 낙찰된다
    conn = DB.get_db()
    cid_i2 = conn.execute(
        "INSERT INTO cases(case_no,status,insurer_id,category,region) "
        "VALUES(?,'입찰중',?,'금속','서울')", (_no("52I-"), iid)).lastrowid
    auid_i2 = conn.execute("INSERT INTO auctions(case_id,status) VALUES(?,'진행')", (cid_i2,)).lastrowid
    bid_i2 = conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount) VALUES(?,?,?,2500000)",
        (auid_i2, p_ok, "검증정상52-award")).lastrowid
    conn.commit(); conn.close()
    ri2 = client.post(f"/api/insurer/cases/{cid_i2}/award", json={"bid_id": bid_i2}, headers=_hdr)
    chk(ri2.status_code == 200, "★ 대조군 — 정상 업체는 그대로 낙찰된다(과잉차단 아님)",
        (ri2.status_code, ri2.get_json()))

    # ── ④ 전체재경매 마감 — 무등록 업체(내가 직접 찾은 자리) ──
    conn = DB.get_db()
    cid_c = conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,category,region) "
        "VALUES(?,'시공중',?,?,'금속','서울')", (_no("52CO-"), "검증보험사52", iid)).lastrowid
    coid_c = conn.execute(
        "INSERT INTO change_orders(case_id,round,status,combined_amount,incumbent_amount) "
        "VALUES(?,1,'전체재경매중',5000000,4000000)", (cid_c,)).lastrowid
    auid_c = conn.execute(
        "INSERT INTO auctions(case_id,status,change_order_id,kind) "
        "VALUES(?,'진행',?,'전체재경매')", (cid_c, coid_c)).lastrowid
    bid_c = conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount) VALUES(?,?,?,4500000)",
        (auid_c, p_nolic, "검증무등록52-award")).lastrowid
    conn.commit(); conn.close()

    with client.session_transaction() as sess:
        _admin_sess(sess)
    rc = client.post(f"/api/change-orders/{coid_c}/close-full",
                     json={"bid_id": bid_c, "force": True}, headers=_hdr)
    dc = rc.get_json()
    chk(rc.status_code == 409 and dc.get("code") == "NO_LICENSE",
        "★★★ ④ 전체재경매 마감 — 무등록 업체는 낙찰이 막힌다(고치기 전엔 200)",
        (rc.status_code, dc))
    conn = DB.get_db()
    row_c = conn.execute("SELECT partner_id FROM cases WHERE id=?", (cid_c,)).fetchone()
    conn.close()
    chk(row_c["partner_id"] is None, "④ 막힌 뒤 사건의 담당 업체가 갈아치워지지 않았다", dict(row_c))

    # ══════════════════════════════════════════════════════════
    print("\n[4] 실행 — /api/reauctions 데모 필터 HTTP 실측")
    # ──────────────────────────────────────────────────────────
    conn = DB.get_db()
    p_real = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('검증실협력사52','시행사','활성')"
    ).lastrowid
    cid_demo = conn.execute(
        "INSERT INTO cases(case_no,status,is_demo,category,region) "
        "VALUES(?,'시공중',1,'금속','서울')", (_no("52DEMO-"),)).lastrowid
    coid_demo = conn.execute(
        "INSERT INTO change_orders(case_id,round,status,combined_amount) "
        "VALUES(?,1,'전체재경매중',5000000)", (cid_demo,)).lastrowid
    conn.execute(
        "INSERT INTO auctions(case_id,status,change_order_id,kind) "
        "VALUES(?,'진행',?,'전체재경매')", (cid_demo, coid_demo))
    cid_real = conn.execute(
        "INSERT INTO cases(case_no,status,is_demo,category,region) "
        "VALUES(?,'시공중',0,'금속','서울')", (_no("52REAL-"),)).lastrowid
    coid_real = conn.execute(
        "INSERT INTO change_orders(case_id,round,status,combined_amount) "
        "VALUES(?,1,'전체재경매중',5000000)", (cid_real,)).lastrowid
    conn.execute(
        "INSERT INTO auctions(case_id,status,change_order_id,kind) "
        "VALUES(?,'진행',?,'전체재경매')", (cid_real, coid_real))
    conn.commit(); conn.close()

    with client.session_transaction() as sess:
        sess["partner_id"] = p_real; sess["_csrf"] = _tok
    rr = client.get("/api/reauctions", headers=_hdr)
    dr = rr.get_json()
    seen_cases = {row.get("case_no") for row in dr} if isinstance(dr, list) else set()
    chk(rr.status_code == 200, "/api/reauctions 정상 응답", rr.status_code)
    chk(not any(("52DEMO-" in (cn or "")) for cn in seen_cases),
        "★★★ 데모 재경매는 목록에 안 뜬다(고치기 전엔 떴다)", seen_cases)
    chk(any(("52REAL-" in (cn or "")) for cn in seen_cases),
        "정상 재경매는 그대로 목록에 뜬다(과잉차단 아님)", seen_cases)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드52 실측 준비/실행", f"{type(e).__name__} {e}")
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
