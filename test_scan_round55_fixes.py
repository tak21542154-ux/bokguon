# -*- coding: utf-8 -*-
"""스캔 55라운드 회귀 — ①발주처 '부동의' 금액이 그대로 확정되던 CRITICAL 결함
   ②하자 상태 전이 무가드로 지급 관문이 흔적 없이 열리고 닫히던 HIGH 결함.

  조사 에이전트(+직접 코드 대조)가 공개 API 만으로 실증한 결함:

  ① api_co_close_full(전체재경매 마감)이 발주처 확인 여부(insurer_ack)는
     안 보고 **금액만** 대조했다. 그런데 원업체 제안 회수(withdraw-offer)는
     combined_amount 만 지우고 insurer_ack/insurer_ack_amount 는 남겨 뒀다 —
     그 뒤 새 라운드에서(전체재경매 상한이 combined_amount 없을 때 쓰는
     대체식 때문에) 우연히 같은 금액이 다시 나오면, 발주처가 명시적으로
     '부동의' 했던 그 금액이 그대로 계약금액으로 확정됐다(보험업법·변호사법
     철칙 위반). 형제 라우트(api_co_decision)는 처음부터 확인 여부와 금액을
     둘 다 봤다 — 판단을 공유 함수(_insurer_ack_ok)로 모으고, withdraw-offer
     에서 금액을 지울 때 확인도 함께 무효화한다.

  ② api_defect_update 의 UPDATE 는 WHERE id=? 뿐이라 선행상태 조건이 없었다.
     '접수'에서 확인중·재시공배정을 건너뛰고 '완료'로 한 번에 갈 수 있었고,
     그러면 지급 관문(DEFECT_OPEN)이 정규 완료보고 경로(사유 요구·⚠ 감사로그
     표시)보다 더 조용하게 열리고 닫혔다. 전이표(DEFECT_NEXT)를 도입해
     허용된 다음 상태만 통과시킨다. 덤으로 '완료 취소' 시 resolved_at 이
     안 지워지던 것과, 재시공배정 알림이 이번 요청의 새 기한이 아니라
     옛 기한을 실어 보내던 것도 함께 고쳤다.

      python test_scan_round55_fixes.py
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

print("═" * 72)
print("  스캔 55라운드 회귀 — 발주처 부동의 금액 확정 + 하자 상태전이 무가드")
print("═" * 72)


def _body(fn_name):
    start = APP_SRC.index(f"\ndef {fn_name}(")
    end = APP_SRC.find("\ndef ", start + 1)
    return APP_SRC[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
chk("def _insurer_ack_ok(co, amount):" in APP_SRC,
    "★★★ ① 공유 판단 함수 _insurer_ack_ok 가 생겼다")
chk(APP_SRC.count("not _insurer_ack_ok(co,") == 2,
    "★★ ① api_co_decision·api_co_close_full 둘 다 같은 함수를 부른다(중복구현 아님)",
    APP_SRC.count("not _insurer_ack_ok(co,"))
withdraw_body = _body("api_co_withdraw_offer")
chk("insurer_ack=NULL" in withdraw_body and "insurer_ack_amount=NULL" in withdraw_body,
    "★★★ ① withdraw-offer 가 금액과 함께 확인도 무효화한다(옛 확인이 안 남는다)")

defect_flow_idx = APP_SRC.index('DEFECT_FLOW = ["접수"')
defect_next_region = APP_SRC[defect_flow_idx:defect_flow_idx + 900]
chk("DEFECT_NEXT = {" in defect_next_region,
    "★★★ ② 하자 전이표(DEFECT_NEXT)가 생겼다")
defect_update_body = _body("api_defect_update")
chk('st not in DEFECT_NEXT.get(row["status"], ())' in defect_update_body,
    "★★★ ② api_defect_update 가 전이표로 다음 상태를 검사한다")
chk('sets.append("resolved_at=?"); vals.append(None)' in defect_update_body,
    "★★ ② 완료를 벗어나면 resolved_at 도 함께 지운다")
chk('_due = d.get("due_date") or row["due_date"]' in defect_update_body,
    "★ ② 재시공배정 알림이 이번 요청의 새 기한을 본다(옛 기한 아님)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — ① 발주처 부동의 금액 확정 전체 흐름을 실제 HTTP로 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round55_")
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
    _insurer_ack_ok = A._insurer_ack_ok

    # ── 순수 함수 단위 검증 — 껍데기(HTTP·DB) 없이 판단 로직만 ──
    co_ok = {"insurer_ack": "확인", "insurer_ack_amount": 1200000}
    co_reject = {"insurer_ack": "부동의", "insurer_ack_amount": 1200000}
    co_none = {"insurer_ack": None, "insurer_ack_amount": None}
    co_stale = {"insurer_ack": "확인", "insurer_ack_amount": 1000000}
    chk(_insurer_ack_ok(co_ok, 1200000) is True, "★ 확인+금액일치 → 통과")
    chk(_insurer_ack_ok(co_reject, 1200000) is False,
        "★★★ 부동의여도 금액이 우연히 같으면 — 그래도 막힌다(핵심 로직)")
    chk(_insurer_ack_ok(co_none, 0) is False, "★ 미회신 → 막힌다")
    chk(_insurer_ack_ok(co_stale, 1200000) is False, "★ 확인했지만 다른 금액 → 막힌다")

    client = A.app.test_client()
    _tok = "regress-round55-csrf-token"
    _hdr = {"X-CSRF-Token": _tok}

    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('검증보험사55','활성')").lastrowid
    p_incumbent = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('원업체55','시공사','활성')"
    ).lastrowid
    p_rival = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('경쟁사55','시행사','활성')"
    ).lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,partner_id,partner_name,"
        "                  award_amount,category,region) "
        "VALUES(?,'시공중',?,?,?,?,1000000,'금속','서울')",
        (_no("55C-"), "검증보험사55", iid, p_incumbent, "원업체55")).lastrowid
    #  '실사요청→추가경매중 오픈' 은 이 결함과 무관하므로 그 결과 상태를 직접 심는다.
    coid = conn.execute(
        "INSERT INTO change_orders(case_id,round,status,incumbent_partner_id,incumbent_amount,"
        "                          requested_amount) "
        "VALUES(?,1,'추가경매중',?,1000000,300000)", (cid, p_incumbent)).lastrowid
    auid1 = conn.execute(
        "INSERT INTO auctions(case_id,status,change_order_id,kind,created_at) "
        "VALUES(?,'진행',?,'추가분',datetime('now','+9 hours','-1 hours'))",
        (cid, coid)).lastrowid
    conn.commit(); conn.close()

    def _admin_sess(sess):
        sess["admin"] = "admin55"; sess["admin_role"] = "중간관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = _tok

    def _insurer_sess(sess):
        sess["insurer_id"] = iid; sess["insurer_name"] = "검증보험사55"; sess["_csrf"] = _tok

    def _rival_sess(sess):
        sess["partner_id"] = p_rival; sess["_csrf"] = _tok

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                "VALUES('admin55','x','검증','중간관리자')")
    conn.commit(); conn.close()

    # STEP 3 — 경쟁사가 추가분에 투찰
    with client.session_transaction() as sess:
        _rival_sess(sess)
    r3 = client.post("/api/partner/reauction-bids",
                     json={"auction_id": auid1, "amount": 200000, "days": 5}, headers=_hdr)
    chk(r3.status_code == 200, "STEP3 경쟁사 추가분 투찰 200,000원", (r3.status_code, r3.get_json()))

    # STEP 4 — 운영자, 원업체에 합산가 제시(1,000,000+200,000=1,200,000)
    with client.session_transaction() as sess:
        _admin_sess(sess)
    r4 = client.post(f"/api/change-orders/{coid}/offer", json={"force": True}, headers=_hdr)
    d4 = r4.get_json()
    chk(r4.status_code == 200 and d4.get("combined") == 1200000,
        "STEP4 운영자 원업체 제안(합산 1,200,000원)", (r4.status_code, d4))

    # STEP 5 — 발주처, 명시적으로 '부동의'
    with client.session_transaction() as sess:
        _insurer_sess(sess)
    r5 = client.post(f"/api/insurer/change-orders/{coid}/ack",
                     json={"ack": "부동의", "note": "시공사는 이 금액으로 확정할 수 없습니다"},
                     headers=_hdr)
    chk(r5.status_code == 200 and r5.get_json().get("ok") is True,
        "★★★ STEP5 발주처가 명시적으로 부동의를 회신했다", (r5.status_code, r5.get_json()))

    # STEP 6 — 운영자, 제안을 회수(withdraw-offer)
    with client.session_transaction() as sess:
        _admin_sess(sess)
    r6 = client.post(f"/api/change-orders/{coid}/withdraw-offer",
                     json={"reason": "합의 불발로 재경매 진행"}, headers=_hdr)
    chk(r6.status_code == 200, "STEP6 운영자가 제안을 회수했다", (r6.status_code, r6.get_json()))

    conn = DB.get_db()
    co_after_withdraw = dict(conn.execute(
        "SELECT status, combined_amount, insurer_ack, insurer_ack_amount "
        "  FROM change_orders WHERE id=?", (coid,)).fetchone())
    conn.close()
    chk(co_after_withdraw["insurer_ack"] is None and co_after_withdraw["insurer_ack_amount"] is None,
        "★★★ STEP6 이후 옛 '부동의' 확인이 실제로 지워졌다(고치기 전엔 남아 있었다)",
        co_after_withdraw)

    # STEP 7 — 운영자, 추가분 유찰 확정
    #  ⚠⚠ [라운드114] fail-add 가 형제(close-full)와 같은 마감가드를 갖게 됐다 —
    #    이 시나리오의 관심사는 마감 타이밍이 아니라 그 다음(withdraw 뒤 재경매)
    #    이므로, 실제 운영자가 하듯 확인(force)하고 넘어간다.
    r7 = client.post(f"/api/change-orders/{coid}/fail-add", headers=_hdr, json={"force": True})
    chk(r7.status_code == 200, "STEP7 추가분 경매 유찰 확정", (r7.status_code, r7.get_json()))

    # STEP 8 — 운영자, 전체 재경매 오픈(2차)
    r8 = client.post(f"/api/change-orders/{coid}/full-reauction", headers=_hdr)
    d8 = r8.get_json()
    chk(r8.status_code == 200 and d8.get("round") == 2,
        "STEP8 전체 재경매(2차) 오픈", (r8.status_code, d8))

    # STEP 9 — 경쟁사, 옛날 발주처가 거부했던 바로 그 금액(1,200,000)으로 투찰
    #          (combined_amount 가 지워졌으므로 상한은 incumbent+requested 대체식 —
    #           1,000,000+300,000=1,300,000 을 10만원 단위로 내림 = 1,200,000)
    auid2 = None
    conn = DB.get_db()
    _row = conn.execute(
        "SELECT id FROM auctions WHERE change_order_id=? AND kind='전체재경매' "
        "ORDER BY id DESC LIMIT 1", (coid,)).fetchone()
    conn.close()
    auid2 = _row["id"] if _row else None
    with client.session_transaction() as sess:
        _rival_sess(sess)
    r9 = client.post("/api/partner/reauction-bids",
                     json={"auction_id": auid2, "amount": 1200000, "days": 5}, headers=_hdr)
    d9 = r9.get_json()
    chk(r9.status_code == 200, "STEP9 경쟁사가 옛 거부금액(1,200,000)으로 재투찰",
        (r9.status_code, d9))

    # STEP 10 — 운영자, 낙찰 확정 시도 (insurer_instruction 없이)
    with client.session_transaction() as sess:
        _admin_sess(sess)
    bid_id = d9.get("bid_count") and None  # placeholder, 아래에서 실제 bid_id 조회
    conn = DB.get_db()
    bid_row = conn.execute(
        "SELECT id FROM bids WHERE auction_id=? AND partner_id=?", (auid2, p_rival)).fetchone()
    conn.close()
    bid_id = bid_row["id"]
    r10 = client.post(f"/api/change-orders/{coid}/close-full",
                      json={"bid_id": bid_id, "force": True}, headers=_hdr)
    d10 = r10.get_json()
    chk(r10.status_code == 409 and d10.get("code") == "INSURER_ACK_REQUIRED",
        "★★★ STEP10 발주처가 거부했던 금액은 확정되지 않는다(고치기 전엔 200으로 확정됨)",
        (r10.status_code, d10))

    conn = DB.get_db()
    case_after = dict(conn.execute(
        "SELECT status, award_amount, partner_id FROM cases WHERE id=?", (cid,)).fetchone())
    conn.close()
    chk(case_after["award_amount"] == 1000000 and case_after["partner_id"] == p_incumbent,
        "★★★ 막힌 뒤 사건의 계약금액·담당업체가 오염되지 않았다(그대로 원업체·1,000,000원)",
        case_after)

    # 대조군 — 발주처가 실제로 확인한 금액이면 유선지시 없이도 그대로 확정된다
    r10b = client.post(f"/api/change-orders/{coid}/close-full",
                       json={"bid_id": bid_id, "force": True,
                             "insurer_instruction": "2026-08-25 유선 지시 — 최저가로 확정 진행"},
                       headers=_hdr)
    chk(r10b.status_code == 200,
        "★ 대조군 — 유선지시 근거를 남기면 정상적으로 확정된다(과잉차단 아님)",
        (r10b.status_code, r10b.get_json()))

    #  ── 격리 재현 — withdraw-offer 체인 없이 close-full 자체의 확인검사만 ──
    #    위 STEP3~10 은 withdraw-offer 가 확인을 지우는 것(수정②)만으로도 이
    #    특정 경로는 막힌다 — close-full 자체의 판단(수정①)이 정말 필요한지는
    #    이걸로 못 가른다. insurer_ack='부동의' 인 change_order 를 직접 심어
    #    withdraw-offer 를 거치지 않고 바로 close-full 을 불러 독립적으로 증명한다.
    conn = DB.get_db()
    cid_direct = conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,partner_id,partner_name,"
        "                  award_amount,category,region) "
        "VALUES(?,'시공중',?,?,?,?,900000,'금속','서울')",
        (_no("55CD-"), "검증보험사55", iid, p_incumbent, "원업체55")).lastrowid
    coid_direct = conn.execute(
        "INSERT INTO change_orders(case_id,round,status,incumbent_partner_id,incumbent_amount,"
        "                          insurer_ack,insurer_ack_amount) "
        "VALUES(?,1,'전체재경매중',?,900000,'부동의',900000)",
        (cid_direct, p_incumbent)).lastrowid
    auid_direct = conn.execute(
        "INSERT INTO auctions(case_id,status,change_order_id,kind) "
        "VALUES(?,'진행',?,'전체재경매')", (cid_direct, coid_direct)).lastrowid
    bid_direct = conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount) VALUES(?,?,?,900000)",
        (auid_direct, p_rival, "경쟁사55")).lastrowid
    conn.commit(); conn.close()

    r_direct = client.post(f"/api/change-orders/{coid_direct}/close-full",
                           json={"bid_id": bid_direct, "force": True}, headers=_hdr)
    chk(r_direct.status_code == 409,
        "★★★ 격리재현 — withdraw-offer 없이도 close-full 자체가 부동의 금액을 막는다"
        "(수정①이 독립적으로 필요하다는 증명)", (r_direct.status_code, r_direct.get_json()))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ ① 라운드55 실측 준비/실행", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — ② 하자 상태 전이 실제 HTTP 재현")
# ──────────────────────────────────────────────────────────────
try:
    conn = DB.get_db()
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region) VALUES(?,'완료','금속','서울')",
        (_no("55D-"),)).lastrowid
    did = conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,title,status,due_date) "
        "VALUES(?,?,?,'테스트 하자','접수','2026-09-01')", (_no("55DF-"), cid2, _no("55D-"))
    ).lastrowid
    conn.commit(); conn.close()

    with client.session_transaction() as sess:
        _admin_sess(sess)

    # ★★★ 핵심 — 접수에서 완료로 한 번에 건너뛰기(지급관문 우회)가 막히는가
    rj = client.patch(f"/api/defects/{did}", json={"status": "완료"}, headers=_hdr)
    dj = rj.get_json()
    chk(rj.status_code == 409 and dj.get("code") == "DEFECT_BAD_TRANSITION",
        "★★★ 접수→완료 한번에 건너뛰기가 막힌다(고치기 전엔 200으로 통과)",
        (rj.status_code, dj))
    conn = DB.get_db()
    st_after_jump = conn.execute("SELECT status, resolved_at FROM defects WHERE id=?",
                                 (did,)).fetchone()
    conn.close()
    chk(st_after_jump["status"] == "접수" and st_after_jump["resolved_at"] is None,
        "막힌 뒤 하자 상태가 오염되지 않았다(그대로 접수)", dict(st_after_jump))

    # 정상 경로 — 접수 → 확인중 → 재시공배정(새 기한) → 완료
    r_ok1 = client.patch(f"/api/defects/{did}", json={"status": "확인중"}, headers=_hdr)
    chk(r_ok1.status_code == 200, "정상 전진 접수→확인중은 그대로 된다(과잉차단 아님)",
        r_ok1.status_code)

    r_ok2 = client.patch(f"/api/defects/{did}",
                         json={"status": "재시공배정", "due_date": "2026-12-31"}, headers=_hdr)
    chk(r_ok2.status_code == 200, "정상 전진 확인중→재시공배정(새 기한 지정)도 된다",
        r_ok2.status_code)
    conn = DB.get_db()
    noti_msg = conn.execute(
        "SELECT message FROM notifications WHERE ntype='재시공배정' AND case_id=?"
        " ORDER BY id DESC LIMIT 1", (cid2,)).fetchone()
    conn.close()
    chk(noti_msg and "2026-12-31" in noti_msg["message"] and "2026-09-01" not in noti_msg["message"],
        "★★ 재시공배정 알림이 이번 요청의 새 기한(2026-12-31)을 담았다(고치기 전엔 옛 기한)",
        dict(noti_msg) if noti_msg else None)

    r_ok3 = client.patch(f"/api/defects/{did}", json={"status": "완료"}, headers=_hdr)
    chk(r_ok3.status_code == 200, "정상 전진 재시공배정→완료도 된다", r_ok3.status_code)

    # ★★ 완료에서 재시공배정으로 직접 되돌리기는 이제 막힌다(완료 취소=확인중만 허용)
    r_bad_back = client.patch(f"/api/defects/{did}", json={"status": "재시공배정"}, headers=_hdr)
    chk(r_bad_back.status_code == 409,
        "★★ 완료→재시공배정 직접 되돌리기는 막힌다(완료 취소는 확인중으로만)",
        r_bad_back.status_code)

    # ★★★ '완료 취소'(완료→확인중)는 여전히 되고, resolved_at 이 실제로 지워진다
    r_cancel = client.patch(f"/api/defects/{did}", json={"status": "확인중"}, headers=_hdr)
    chk(r_cancel.status_code == 200, "★★★ 화면의 '완료 취소'(완료→확인중)는 그대로 된다(회귀 방지)",
        r_cancel.status_code)
    conn = DB.get_db()
    row_after_cancel = conn.execute(
        "SELECT status, resolved_at FROM defects WHERE id=?", (did,)).fetchone()
    conn.close()
    chk(row_after_cancel["status"] == "확인중" and row_after_cancel["resolved_at"] is None,
        "★★ 완료 취소 뒤 resolved_at 이 실제로 비워졌다(고치기 전엔 완료일이 남았다)",
        dict(row_after_cancel))

    # 반려는 되살리지 않는다
    conn = DB.get_db()
    did2 = conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,title,status) "
        "VALUES(?,?,?,'테스트 하자2','반려')", (_no("55DF-"), cid2, _no("55D-"))).lastrowid
    conn.commit(); conn.close()
    r_revive = client.patch(f"/api/defects/{did2}", json={"status": "확인중"}, headers=_hdr)
    chk(r_revive.status_code == 409, "★ 반려된 하자는 되살아나지 않는다", r_revive.status_code)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ ② 라운드55 실측 준비/실행", f"{type(e).__name__} {e}")
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
