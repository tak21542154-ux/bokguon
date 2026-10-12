# -*- coding: utf-8 -*-
"""스캔 114라운드 회귀 — 어드민 입찰목록 필터누락, 시공사진 집계 오염, 추가분 유찰 무방비.

  [1] (높음·잘못된 낙찰판단) 어드민 사건상세(api_case_detail)·입찰목록
      (api_case_bids)이 변경견적 재경매 입찰·퇴출업체 입찰을 그대로 섞어
      최저가·「최저」뱃지를 매겼다. 형제(api_insurer_case_detail, 101라운드)는
      이미 두 필터가 있다.
  [2] (중간·모순된 UI) 시공 사진 집계(_case_photos_stat)가 보험사·관리자가
      올린 참고 피해사진까지 세어, 같은 화면의 검수 승인 버튼(uploader_role=
      '협력사'만 보는 102라운드 관문)과 서로 다른 숫자를 말했다.
  [3] (높음·되돌릴 수 없음) 추가분 유찰(api_co_fail_add)에 형제(api_co_close_full)
      에는 있는 마감 가드가 없어 살아 있는 입찰을 즉시 죽이고, 입찰 무효화·
      탈락자 통지도 없었다 — 유찰 뒤 되돌릴 출구가 전체재경매뿐이었다.

      python test_scan_round114_fixes.py
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

print("═" * 72)
print("  스캔 114라운드 회귀 — 입찰목록 필터누락·사진집계 오염·추가분 유찰 무방비")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
cd_body = _py_fn_body(APP_SRC, "api_case_detail")
chk("a.case_id=? AND a.change_order_id IS NULL AND b.voided_at IS NULL" in cd_body
    and "COALESCE(p.status,'활성') = '활성'" in cd_body,
    "★★★ api_case_detail 입찰목록이 변경견적·퇴출업체 입찰을 뺀다")

cb_body = _py_fn_body(APP_SRC, "api_case_bids")
chk("AND COALESCE(p.status,'활성') = '활성'" in cb_body,
    "★★★ api_case_bids 도 퇴출업체 입찰을 뺀다(최저가 계산 오염 방지)")

cps_body = _py_fn_body(APP_SRC, "_case_photos_stat")
chk("uploader_role='협력사'" in cps_body,
    "★★ 시공 사진 집계가 협력사 업로드만 센다(보험사·관리자 참고사진 제외)")

cfa_body = _py_fn_body(APP_SRC, "api_co_fail_add")
chk('"code": "NOT_CLOSED"' in cfa_body and "not d.get(\"force\")" in cfa_body,
    "★★★ 추가분 유찰이 마감 전이면 확인 없이는 안 막는다(형제 close-full과 동일)")
chk("voided_at=datetime('now','+9 hours'), void_reason='추가분 유찰'" in cfa_body,
    "★★★ 추가분 유찰이 실제로 입찰을 무효화한다")
chk("notify_bid_losers(conn, au[\"id\"]" in cfa_body,
    "★★ 추가분 유찰이 입찰자에게도 결과를 알린다")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[4] 실행 — 실제 시나리오를 돌린다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round114_")
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
                 "VALUES('r114admin','x','검증','중간관리자')")
    conn.commit()
    admin = A.app.test_client()
    _tok = "r114-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r114admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    # ── [2] 사건상세·입찰목록 — 변경견적·퇴출업체 입찰이 안 섞인다 ──────
    p_ok = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R114정상업체','시행사','활성')").lastrowid
    p_retired = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R114퇴출업체','시행사','퇴출')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R114-C1','검수대기','가드레일','서울',0)").lastrowid
    aid_main = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,NULL,'원경매',0,'마감',4000000,2,0,?,?)", (cid, DB.now(), DB.now())).lastrowid
    conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,5000000,10,?)", (aid_main, p_ok, "R114정상업체", DB.now()))
    conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,4000000,10,?)", (aid_main, p_retired, "R114퇴출업체", DB.now()))
    coid = conn.execute(
        "INSERT INTO change_orders(case_id,round,reason,requested_amount,status,created_at) "
        "VALUES(?,1,'실사 증액','추가 공사','추가경매중',?)", (cid, DB.now())).lastrowid
    aid_co = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,?,'추가분',1,'마감',800000,1,0,?,?)", (cid, coid, DB.now(), DB.now())).lastrowid
    conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,800000,10,?)", (aid_co, p_retired, "R114퇴출업체", DB.now()))
    conn.commit()

    r1 = admin.get(f"/api/cases/{cid}/detail", headers=_hdr)
    j1 = r1.get_json()
    bid_amounts = sorted(b["amount"] for b in j1.get("bids", []))
    chk(bid_amounts == [5000000],
        "★★★ 사건상세 입찰목록에 정상업체 500만원만 남는다"
        "(예전엔 퇴출업체 400만·추가분 80만이 섞여 「최저」뱃지가 엉뚱한 곳에 붙었다)",
        bid_amounts)

    r2 = admin.get(f"/api/cases/{cid}/bids", headers=_hdr)
    j2 = r2.get_json()
    bid_amounts2 = sorted(b["amount"] for b in j2)
    chk(bid_amounts2 == [5000000],
        "★★★ 점수매김용 입찰목록도 정상업체 500만원만 남는다"
        "(예전엔 퇴출업체 400만원이 최저가로 잡혀 정상 응찰사 가격점수가 전부 낮게 매겨졌다)",
        bid_amounts2)

    # ── [3] 시공 사진 집계 — 보험사 참고사진은 안 세고, 승인관문과 숫자가 일치한다 ──
    #  ⚠ cid(R114-C1)는 위 [2]에서 변경견적을 이미 붙여 뒀다(115라운드 —
    #    검수승인이 진행 중인 변경견적을 막는다) — 이 사진집계 검사와는 무관한
    #    조건이 섞이지 않도록 깨끗한 사건을 새로 쓴다.
    cid_photo = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R114-C1B','검수대기','가드레일','서울',0)").lastrowid
    conn.execute(
        "INSERT INTO photos(case_id,uploader,uploader_role,rel_path,orig_name,mime,ext,"
        "                   size,sha256,kind,review_status,created_at) "
        "VALUES(?,'검증보험','보험사','ref.jpg','ref.jpg','image/jpeg','jpg',1,'r114sha_ref',"
        "       '착공전','승인',?)", (cid_photo, DB.now()))
    conn.commit()
    r3 = admin.get(f"/api/cases/{cid_photo}/detail", headers=_hdr)
    j3 = r3.get_json()
    chk(j3["photos"]["total"] == 0,
        "★★ 보험사 참고사진은 '시공 사진' 집계에 안 잡힌다"
        "(예전엔 1장으로 세어 '시공 사진 1장(승인 1)'이라며 승인 가능한 것처럼 보였다)",
        j3["photos"])
    r3b = admin.post(f"/api/cases/{cid_photo}/approve", headers=_hdr)
    chk(r3b.status_code == 409 and r3b.get_json().get("code") == "NO_PHOTO",
        "STEP 승인 관문도 같은 결론(사진 없음)이다 — 화면·관문이 이제 같은 말을 한다",
        (r3b.status_code, r3b.get_json()))

    # ── [4] 추가분 유찰 — 마감 전엔 확인 없이 못 막고, force 로 확인하면 정리된다 ──
    p_bidder = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R114추가업체','시행사','활성')").lastrowid
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R114-C2','시공중','가드레일','서울',0)").lastrowid
    coid2 = conn.execute(
        "INSERT INTO change_orders(case_id,round,reason,requested_amount,status,created_at) "
        "VALUES(?,1,'실사 증액','추가 공사','추가경매중',?)", (cid2, DB.now())).lastrowid
    aid2 = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,?,'추가분',1,'진행',900000,1,0,"
        "       datetime('now','+9 hours','+24 hours'),?)", (cid2, coid2, DB.now())).lastrowid
    bid2 = conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,900000,10,?)", (aid2, p_bidder, "R114추가업체", DB.now())).lastrowid
    #  이미 무효화된 옛 입찰 하나를 같은 경매에 섞어 둔다 — nb 집계가 voided_at
    #  을 거르는지 아닌지가 이걸로만 갈린다(살아 있는 입찰 1건뿐이면 두 버전이
    #  같은 숫자를 낸다).
    conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at,"
        "                 voided_at,void_reason) "
        "VALUES(?,?,?,850000,10,?,?,'이전 라운드 무효')",
        (aid2, p_bidder, "R114추가업체", DB.now(), DB.now()))
    conn.commit()

    r4 = admin.post(f"/api/change-orders/{coid2}/fail-add", headers=_hdr)
    chk(r4.status_code == 409 and r4.get_json().get("code") == "NOT_CLOSED",
        "★★★ 마감이 24시간 남았으면 확인 없이는 유찰 처리를 안 막는다"
        "(예전엔 그대로 통과해 살아 있는 입찰이 즉시 죽었다)",
        (r4.status_code, r4.get_json()))
    bid2_row = conn.execute("SELECT voided_at FROM bids WHERE id=?", (bid2,)).fetchone()
    chk(bid2_row["voided_at"] is None, "STEP 막힌 요청은 입찰을 안 건드렸다", dict(bid2_row))

    r5 = admin.post(f"/api/change-orders/{coid2}/fail-add", headers=_hdr, json={"force": True})
    chk(r5.status_code == 200, "STEP 확인(force)하면 마감 전이어도 유찰 처리된다",
        (r5.status_code, r5.get_data(as_text=True)[:200]))
    chk(r5.get_json().get("bid_count") == 1,
        "★★ 응답·알림의 입찰건수가 이미 무효화된 옛 입찰은 안 센다(살아 있는 1건만)"
        "(예전엔 무효 여부를 안 걸러 2건으로 부풀렸다)",
        r5.get_json())
    bid2_after = conn.execute("SELECT voided_at FROM bids WHERE id=?", (bid2,)).fetchone()
    chk(bid2_after["voided_at"] is not None,
        "★★★ 유찰 확정 뒤 그 입찰이 실제로 무효화됐다"
        "(예전엔 그대로 살아남아 다음 회차에도 낙찰 후보가 될 수 있었다)",
        dict(bid2_after))
    loser_notif = conn.execute(
        "SELECT message FROM notifications WHERE ntype='입찰결과' AND partner_id=? "
        "ORDER BY id DESC LIMIT 1", (p_bidder,)).fetchone()
    chk(bool(loser_notif) and "유찰" in loser_notif["message"],
        "★★ 입찰자에게도 결과가 통지된다(예전엔 침묵)",
        dict(loser_notif) if loser_notif else None)

    # 비교: 이미 마감시각이 지난 경매는 force 없이도 통과한다(과잉차단 아님)
    cid3 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R114-C3','시공중','가드레일','서울',0)").lastrowid
    coid3 = conn.execute(
        "INSERT INTO change_orders(case_id,round,reason,requested_amount,status,created_at) "
        "VALUES(?,1,'실사 증액','추가 공사','추가경매중',?)", (cid3, DB.now())).lastrowid
    conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,?,'추가분',1,'마감',0,0,0,"
        "       datetime('now','+9 hours','-1 hour'),?)", (cid3, coid3, DB.now()))
    conn.commit()
    r6 = admin.post(f"/api/change-orders/{coid3}/fail-add", headers=_hdr)
    chk(r6.status_code == 200,
        "STEP 이미 마감(과거)된 경매는 force 없이도 정상 유찰 처리된다(과잉차단 아님)",
        (r6.status_code, r6.get_data(as_text=True)[:200]))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드114 서버측 준비/실행", f"{type(e).__name__} {e}")
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
