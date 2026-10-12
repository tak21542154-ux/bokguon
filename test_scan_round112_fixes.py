# -*- coding: utf-8 -*-
"""스캔 112라운드 회귀 — 전체재경매 무효입찰 낙찰가능, notify() case_id 누락 6곳,
   연락처 일괄등록의 메일수신거부·홈페이지 유실.

  [1] (치명·금전) 전체재경매 낙찰(api_co_close_full)과 그 목록(api_co_bids)이
      voided_at 을 안 걸렀다 — 형제 세 낙찰경로(보험사·어드민 원경매·이 함수 자신의
      최저가 계산)는 전부 거르는데 여기만 무효화된(반려·취소된) 입찰을 그대로
      후보로 보여주고 그 금액으로 낙찰을 확정할 수 있었다.
  [2] (운영신뢰) notify() 는 case_id 를 받아야만 데모 표식을 채우는데, 사건에
      매인 알림 6곳이 case_id 를 안 넘겼다 — 데모 사건 알림이 운영 알림벨에
      새고, case_id 가 없어 나중에 백필로도 못 고친다.
  [3] (§50④) 연락처 내려받기 양식은 '메일수신거부'·'홈페이지' 열을 내주고
      "그대로 채워 되올리면 반영된다"고 약속하는데, 되올리는 쪽이 이 두 열을
      읽지 않았다 — 수신거부 의사가 조용히 사라지고 광고 대상에서 안 빠졌다.

      python test_scan_round112_fixes.py
"""
import contextlib
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

print("═" * 72)
print("  스캔 112라운드 회귀 — 전체재경매 무효입찰·notify case_id 누락·연락처 유실")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
cob_body = _py_fn_body(APP_SRC, "api_co_bids")
chk("WHERE auction_id=? AND voided_at IS NULL" in cob_body,
    "★★★ api_co_bids 목록이 무효화된 입찰을 뺀다")

ccf_body = _py_fn_body(APP_SRC, "api_co_close_full")
chk("WHERE b.id=? AND b.auction_id=? AND b.voided_at IS NULL" in ccf_body,
    "★★★ api_co_close_full 낙찰이 무효화된 입찰을 거부한다")

#  ⚠ 그냥 "case_id=" 를 세면 같은 함수 안의 무관한 SQL 조각(예: WHERE case_id=?,
#    dd.case_id=cs.id)까지 걸려 함수 하나에 실제로는 notify() 호출 하나만 고쳐도
#    항상 "이미 있음"으로 통과한다. **더 교묘한 함정**: api_partner_bid 에는
#    이미 case_id 를 넘기던 '저가경보' notify() 가 두 곳 있어서, 짧은 꼬리
#    (`case_id=case_id)`)로 찾으면 그 둘이 내가 고친 '입찰' notify() 없이도
#    항상 통과시켜 버린다(실측). ntype·메시지까지 포함한, 그 호출 하나만
#    가리키는 문자열로 짚는다.
_NOTIFY_CASEID_CHECKS = (
    ("api_partner_bid",
     'notify(conn, "입찰", "웹", "운영팀", f"{me[\'name\']} — {c[\'case_no\']} 통값 입찰 {amount:,}원",\n'
     '           audience_type="admin", case_id=case_id)'),
    ("api_change_order_create",
     'notify(conn, "변경견적", "웹", "운영팀",\n'
     '           f"{c[\'case_no\']} 실사 증액 요청 — 추가 예상 {add_est:,}원",\n'
     '           audience_type="admin", case_id=cid)'),
    ("api_co_withdraw_offer", 'case_id=(_co_cid["case_id"] if _co_cid else None))'),
    ("api_co_decision",
     'notify(conn, "변경견적", "웹", "운영팀", f"{c[\'case_no\']} 원업체 수락 — 합산가 확정",\n'
     '               audience_type="admin", case_id=co["case_id"])'),
    ("api_co_decision",
     'notify(conn, "변경견적", "웹", "운영팀",\n'
     '               f"{c[\'case_no\']} 원업체 거절 — 전체 재경매 필요",\n'
     '               audience_type="admin", case_id=co["case_id"])'),
    ("api_partner_upload_photos",
     'notify(conn, "사진업로드", "웹", "운영팀",\n'
     '               f"{c[\'case_no\']} 시공 사진 {len(saved)}장 업로드 — 검수 필요",\n'
     '               audience_type="admin", case_id=cid)'),
    ("api_partner_defect_resolve",
     'notify(conn, "재시공보고", "웹", "운영팀", f"{row[\'case_no\']} 재시공 완료 보고 — 검수 필요",\n'
     '           audience_type="admin", case_id=row["case_id"])'),
)
for fn_name, needle in _NOTIFY_CASEID_CHECKS:
    fn_body = _py_fn_body(APP_SRC, fn_name)
    chk(needle in fn_body, f"★★ {fn_name} 의 notify() 가 case_id 를 넘긴다")

ci_body = _py_fn_body(APP_SRC, "api_contact_import")
chk('("홈페이지", "website")' in ci_body,
    "★★ 연락처 일괄등록이 홈페이지 열도 반영한다(양식에 있는데 안 읽던 열)")
chk('sets.append("email_opt_out=1")' in ci_body,
    "★★★ 연락처 일괄등록이 메일수신거부 열을 반영한다(예전엔 조용히 버려졌다)")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[4] 실행 — 실제 시나리오를 돌린다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round112_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A
    from openpyxl import Workbook

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r112admin','x','검증','중간관리자')")
    conn.commit()

    admin = A.app.test_client()
    _tok = "r112-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r112admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    # ── [2] 전체재경매 — 무효 입찰은 목록에서 빠지고, 골라도 낙찰이 안 된다 ──
    p_void = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R112무효업체','시행사','활성')").lastrowid
    p_ok = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R112정상업체','시행사','활성')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R112-C1','시공중','가드레일','서울',0)").lastrowid
    coid = conn.execute(
        "INSERT INTO change_orders(case_id,round,incumbent_partner_id,incumbent_amount,"
        "                          reason,requested_amount,status,created_at) "
        "VALUES(?,1,?,1000000,'실사 증액','추가 공사',?,?)",
        (cid, p_ok, "전체재경매중", DB.now())).lastrowid
    aid = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,?,'전체재경매',1,'마감',0,2,0,"
        "       datetime('now','+9 hours','-1 hour'),?)", (cid, coid, DB.now())).lastrowid
    bid_void = conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at,"
        "                 voided_at,void_reason) "
        "VALUES(?,?,?,1000000,10,?,?,'유찰 확정')",
        (aid, p_void, "R112무효업체", DB.now(), DB.now())).lastrowid
    bid_ok = conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,2000000,10,?)", (aid, p_ok, "R112정상업체", DB.now())).lastrowid
    conn.commit()

    r1 = admin.get(f"/api/change-orders/{coid}/bids", headers=_hdr)
    j1 = r1.get_json()
    ids1 = [row["id"] for row in j1] if isinstance(j1, list) else []
    chk(bid_ok in ids1 and bid_void not in ids1,
        "★★★ 목록에 정상 입찰만 보이고 무효화된 입찰은 빠진다"
        "(예전엔 둘 다 보여 관리자가 무효 입찰을 낙찰로 고를 수 있었다)",
        ids1)

    r2 = admin.post(f"/api/change-orders/{coid}/close-full", headers=_hdr,
                     json={"bid_id": bid_void, "insurer_instruction": "유선 지시 확인 262708"})
    chk(r2.status_code == 400,
        "★★★ 무효화된 입찰 ID 로는 낙찰을 확정할 수 없다"
        "(예전엔 그대로 통과해 반려된 금액이 계약금액이 될 수 있었다)",
        (r2.status_code, r2.get_data(as_text=True)[:200]))
    case_after_void = conn.execute(
        "SELECT partner_id, award_amount FROM cases WHERE id=?", (cid,)).fetchone()
    chk(case_after_void["partner_id"] is None,
        "STEP 거부된 요청이 사건에 아무 흔적도 안 남겼다", dict(case_after_void))

    r3 = admin.post(f"/api/change-orders/{coid}/close-full", headers=_hdr,
                     json={"bid_id": bid_ok, "insurer_instruction": "유선 지시 확인 262708"})
    chk(r3.status_code == 200,
        "STEP 같은 경매의 정상 입찰은 여전히 낙찰 확정된다(과잉차단 아님)",
        (r3.status_code, r3.get_data(as_text=True)[:300]))
    case_after_ok = conn.execute(
        "SELECT partner_id, award_amount FROM cases WHERE id=?", (cid,)).fetchone()
    chk(case_after_ok["partner_id"] == p_ok and case_after_ok["award_amount"] == 2000000,
        "STEP 낙찰 결과가 정상 업체·정상 금액이다", dict(case_after_ok))

    # ── [3] notify() case_id — 데모 사건의 재시공보고 알림이 데모로 표식된다 ──
    cid_demo = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R112-DEMO','시공중','누수','서울',1)").lastrowid
    p_demo = conn.execute(
        "INSERT INTO partners(name,partner_type,status,login_id,password_hash) "
        "VALUES('R112데모업체','시행사','활성','r112demop','x')").lastrowid
    did = conn.execute(
        "INSERT INTO defects(defect_no,case_id,title,status,cost_bearer,partner_id,created_at) "
        "VALUES('R112-DF1',?,'누수 재시공','재시공배정','시행사',?,?)",
        (cid_demo, p_demo, DB.now())).lastrowid
    conn.commit()

    partner_c = A.app.test_client()
    with partner_c.session_transaction() as psess:
        psess["partner_id"] = p_demo
        psess["_csrf"] = "r112-partner-csrf"
    _phdr = {"X-CSRF-Token": "r112-partner-csrf"}
    r4 = partner_c.post(f"/api/partner/defects/{did}/resolve", headers=_phdr,
                         json={"resolution": "누수 부위 재시공 완료"})
    chk(r4.status_code == 200, "STEP 재시공 완료 보고 요청이 성공한다",
        (r4.status_code, r4.get_data(as_text=True)[:200]))
    notif = conn.execute(
        "SELECT case_id, is_demo FROM notifications WHERE ntype='재시공보고' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    chk(bool(notif) and notif["case_id"] == cid_demo and notif["is_demo"] == 1,
        "★★★ 데모 사건의 재시공보고 알림이 case_id 를 싣고 데모로 표식된다"
        "(예전엔 case_id 가 없어 데모 표식이 항상 0 이었고 나중에 백필도 못 했다)",
        dict(notif) if notif else None)

    # ── [4] 연락처 일괄등록 — 메일수신거부·홈페이지가 실제로 반영된다 ────────
    p_contact = conn.execute(
        "INSERT INTO partners(name,partner_type,status,email_opt_out) "
        "VALUES('R112연락처업체','시행사','활성',0)").lastrowid
    conn.commit()

    wb = Workbook()
    ws = wb.active
    ws.append(["업체명", "이메일", "홈페이지", "메일수신거부"])
    ws.append(["R112연락처업체", "contact@example.com", "https://example.com", "Y"])
    xbuf = io.BytesIO()
    wb.save(xbuf)
    xbuf.seek(0)

    r5 = admin.post("/api/contacts/import", headers=_hdr,
                     data={"file": (xbuf, "test.xlsx")},
                     content_type="multipart/form-data")
    j5 = r5.get_json()
    chk(r5.status_code == 200 and j5.get("updated") == 1,
        "STEP 연락처 일괄등록 요청이 1건 갱신으로 끝난다", j5)
    p_row = conn.execute(
        "SELECT website, email_opt_out FROM partners WHERE id=?", (p_contact,)).fetchone()
    chk(p_row["website"] == "https://example.com",
        "★★ 홈페이지 열이 실제로 반영됐다(예전엔 읽는 열 목록에 없었다)", dict(p_row))
    chk(p_row["email_opt_out"] == 1,
        "★★★ 메일수신거부='Y' 가 실제로 반영됐다(예전엔 조용히 버려져 광고 대상에 "
        "계속 남았다 — §50④)",
        dict(p_row))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드112 서버측 준비/실행", f"{type(e).__name__} {e}")
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
