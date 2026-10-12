# -*- coding: utf-8 -*-
"""스캔 117라운드 회귀 — 옛 출동업체 사진 계속 쓰기, 1차합의 부동의 상태무시,
   접수번호 LIKE 이스케이프 누락 3곳(교차 테넌시 유출).

  [1] (금전·교착) 출동했다가 낙찰 못 받은 업체가 다른 업체에게 넘어간 사건에
      계속 사진을 써 넣을 수 있었다 — 사진 업로드의 출동모드 허용조건이
      "낙찰 전(partner_id NULL)"인지 안 봤고, close_live_dispatches 도
      '도착' 상태 수배는 안 닫았다. 정원을 채우면 진짜 낙찰업체가 증거를
      한 장도 못 올려 완료보고·정산이 막힌다.
  [2] (기록정합) 1차합의 승인 가지는 사건이 아직 '접수'인지 다시 보는데
      부동의 가지는 그 재확인이 없어, 이미 다른 방식으로 종결된 사건도
      award_route 를 '경매'로 덮어썼다.
  [3] (정보유출·확인됨) 발주처가 직접 정하는 접수번호가 검증 없이 LIKE 패턴에
      그대로 들어가는 자리 3곳 — 접수번호에 '%'·'_' 를 넣으면 남의 사건
      감사로그(낙찰금액·시공사명)가 새거나, 정당한 재알림이 남의 로그에
      걸려 막혔다.

      python test_scan_round117_fixes.py
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
DISPATCH_SRC = read("dispatch.py")

print("═" * 72)
print("  스캔 117라운드 회귀 — 옛 출동업체 사진남용·1차합의 부동의무시·접수번호 LIKE유출")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
pup_body = _py_fn_body(APP_SRC, "api_partner_upload_photos")
#  [라운드171] 이 자리에 COALESCE(cs.is_demo,0)=0 이 추가됐다(실제 협력사가
#  데모 사건에 배정될 수 있어 데모 격리도 함께 걸어야 했다) — partner_id NULL
#  검사 자체는 그대로 살아있는지만 본다(문자열 위치는 이제 다르다).
chk("WHERE cs.id=? AND cs.partner_id IS NULL AND" in pup_body
    and "COALESCE(cs.is_demo,0)=0" in pup_body,
    "★★★ 사진 업로드 출동모드 허용이 낙찰 전(partner_id NULL)인지 다시 본다")

cld_body = _py_fn_body(APP_SRC, "close_live_dispatches")
chk(cld_body.count("status IN ('모집중','수배됨','도착')") == 2,
    "★★★ close_live_dispatches 가 '도착' 상태 수배도 닫는다")

settle_body = _py_fn_body(DISPATCH_SRC, "settle_agreement")
chk('cs2 = conn.execute(\n                "SELECT status, partner_id FROM cases WHERE id=?"' in settle_body,
    "★★★ 1차합의 부동의도 사건이 아직 '접수'·미배정인지 다시 본다")

for label, fn in (("case_history_report", "case_history_report"),
                  ("api_settlement_detail", "api_settlement_detail"),
                  ("api_case_renotify", "api_case_renotify")):
    body_ = _py_fn_body(APP_SRC, fn)
    chk("_like_escape(" in body_ and "ESCAPE '\\\\'" in body_,
        f"★★★ {label} 이 접수번호를 LIKE 에 넣기 전 이스케이프한다")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[4] 실행 — 실제 시나리오를 돌린다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round117_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A
    import dispatch as DP

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r117admin','x','검증','중간관리자')")
    conn.commit()
    admin = A.app.test_client()
    _tok = "r117-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r117admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    # ── [2] 출동업체(A)가 낙찰 전에는 사진을 올릴 수 있다(정상) ──────────
    p_a = conn.execute(
        "INSERT INTO partners(name,partner_type,status,login_id,password_hash) "
        "VALUES('R117업체A','시행사','활성','r117pa','x')").lastrowid
    p_c = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R117업체C','시행사','활성')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R117-C1','접수','가드레일','서울',0)").lastrowid
    conn.execute(
        "INSERT INTO dispatches(case_id,status,claimed_partner_id,claimed_name,created_at,claimed_at) "
        "VALUES(?,'도착',?,'R117업체A',?,?)", (cid, p_a, DB.now(), DB.now()))
    conn.commit()

    partner_a = A.app.test_client()
    with partner_a.session_transaction() as asess:
        asess["partner_id"] = p_a
        asess["_csrf"] = "r117-a-csrf"
    _ahdr = {"X-CSRF-Token": "r117-a-csrf"}

    img = (io.BytesIO(b"\xff\xd8\xff\xe0fake-jpeg"), "site1.jpg")
    r1 = partner_a.post(f"/api/partner/cases/{cid}/photos", headers=_ahdr,
                         data={"photos": [img]}, content_type="multipart/form-data")
    chk(r1.status_code == 200,
        "STEP 낙찰 전에는 출동업체(A)가 정상적으로 사진을 올릴 수 있다(과잉차단 아님)",
        (r1.status_code, r1.get_data(as_text=True)[:200]))

    # 사건이 다른 업체(C)에게 낙찰됐다(2차 경매 결과를 상태로 직접 재현)
    conn.execute("UPDATE cases SET status='시공중', partner_id=?, partner_name='R117업체C' "
                 "WHERE id=?", (p_c, cid))
    conn.commit()

    img2 = (io.BytesIO(b"\xff\xd8\xff\xe0fake-jpeg-2"), "site2.jpg")
    r2 = partner_a.post(f"/api/partner/cases/{cid}/photos", headers=_ahdr,
                         data={"photos": [img2]}, content_type="multipart/form-data")
    chk(r2.status_code == 404,
        "★★★ 사건이 다른 업체(C)에게 낙찰된 뒤에는 옛 출동업체(A)가 더 이상 "
        "사진을 못 올린다(예전엔 '도착' 수배만으로 계속 통과됐다)",
        (r2.status_code, r2.get_data(as_text=True)[:200]))

    # close_live_dispatches 가 '도착' 상태 수배도 직접 닫는지 확인
    cid_b = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R117-C1B','접수','가드레일','서울',0)").lastrowid
    did_b = conn.execute(
        "INSERT INTO dispatches(case_id,status,claimed_partner_id,claimed_name,created_at,claimed_at) "
        "VALUES(?,'도착',?,'R117업체A',?,?)", (cid_b, p_a, DB.now(), DB.now())).lastrowid
    conn.commit()
    with A.app.test_request_context():
        moved = A.close_live_dispatches(conn, cid_b, "R117-C1B", "테스트 종료", "테스트 알림")
    conn.commit()
    d_row = conn.execute("SELECT status FROM dispatches WHERE id=?", (did_b,)).fetchone()
    chk(moved == 1 and d_row["status"] == "취소",
        "★★ close_live_dispatches 가 '도착' 상태 수배도 직접 닫는다",
        (moved, dict(d_row)))

    # ── [3] 1차합의 부동의 — 사건이 이미 종결됐으면 award_route 를 안 건드린다 ──
    p_d = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R117업체D','시행사','활성')").lastrowid
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,award_route,is_demo) "
        "VALUES('R117-C2','미수선종결','가드레일','서울','미수선',0)").lastrowid
    aid2 = conn.execute(
        """INSERT INTO field_agreements(case_id,partner_id,partner_name,field_amount,status,created_at)
           VALUES(?,?,?,?, '검토중', datetime('now','+9 hours'))""",
        (cid2, p_d, "R117업체D", 5000000)).lastrowid
    conn.commit()

    ok_, msg = DP.settle_agreement(conn, aid2, agreed=False, note="가격 안 맞음(검증)")
    conn.commit()
    chk(not ok_,
        "★★★ 이미 종결(미수선종결)된 사건은 뒤늦은 1차합의 부동의를 거부한다"
        "(예전엔 그대로 통과해 award_route 가 '경매'로 덮어써졌다)",
        (ok_, msg))
    case2_after = conn.execute(
        "SELECT status, award_route FROM cases WHERE id=?", (cid2,)).fetchone()
    chk(case2_after["award_route"] == "미수선",
        "STEP 거부된 요청이 award_route 를 실제로 안 바꿨다", dict(case2_after))

    # 사건이 여전히 '접수'·미배정이면 부동의는 정상적으로 반영된다 — 과잉차단 아님
    p_e = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R117업체E','시행사','활성')").lastrowid
    cid3 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R117-C3','접수','가드레일','서울',0)").lastrowid
    aid3 = conn.execute(
        """INSERT INTO field_agreements(case_id,partner_id,partner_name,field_amount,status,created_at)
           VALUES(?,?,?,?, '검토중', datetime('now','+9 hours'))""",
        (cid3, p_e, "R117업체E", 5000000)).lastrowid
    conn.commit()
    ok3, msg3 = DP.settle_agreement(conn, aid3, agreed=False, note="가격 안 맞음(검증)")
    conn.commit()
    case3_after = conn.execute(
        "SELECT award_route FROM cases WHERE id=?", (cid3,)).fetchone()
    chk(ok3 and case3_after["award_route"] == "경매",
        "STEP 사건이 여전히 접수 상태면 부동의가 정상적으로 반영된다(과잉차단 아님)",
        (ok3, msg3, dict(case3_after)))

    # ── [4] 접수번호 LIKE 이스케이프 — 남의 사건 감사로그가 새지 않는다 ──────
    cid_victim = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('26-80042','완료','가드레일','서울',0)").lastrowid
    DB.log(conn, "검증", "낙찰 확정", "26-80042 · R117피해업체 · 3,400,000원")
    cid_evil = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('26-8%','접수','가드레일','서울',0)").lastrowid
    conn.commit()

    r4 = admin.get(f"/report/case/{cid_evil}", headers=_hdr)
    chk(r4.status_code == 200, "STEP 리포트 요청 자체는 성공한다", r4.status_code)
    chk("R117피해업체" not in r4.get_data(as_text=True),
        "★★★ 접수번호에 '%'를 넣어도 남의 사건(피해업체) 감사로그가 새지 않는다"
        "(예전엔 '26-8%' 가 '26-8'을 포함하는 모든 것과 매치돼 새어 나왔다)",
        r4.get_data(as_text=True)[:300])

    sid_evil = conn.execute(
        "INSERT INTO settlements(case_no,case_id,insurer,amount,fee,payout,created_at) "
        "VALUES(?,?,?,4000000,200000,3800000,?)",
        ("26-8%", cid_evil, "R117보험", DB.now())).lastrowid
    conn.commit()
    r5 = admin.get(f"/api/settlements/{sid_evil}/detail", headers=_hdr)
    j5 = r5.get_json()
    chk(r5.status_code == 200 and not any("R117피해업체" in str(x) for x in j5.get("timeline", [])),
        "★★★ 정산 상세 타임라인도 '%' 접수번호로 남의 로그를 안 끌어온다",
        j5.get("timeline"))

    # 재알림 쿨다운도 남의 로그에 안 걸린다
    DB.log(conn, "검증", "공고 재알림", "26-80042 관련 무관한 재알림 기록(검증)")
    conn.commit()
    aid_evil = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,NULL,'원경매',0,'진행',0,0,0,"
        "       datetime('now','+9 hours','+2 hours'),?)", (cid_evil, DB.now())).lastrowid
    conn.commit()
    r6 = admin.post(f"/api/cases/{cid_evil}/renotify", headers=_hdr)
    chk(r6.status_code == 200 and r6.get_json().get("ok"),
        "★★ 재알림도 '%' 접수번호 때문에 남의 로그에 걸려 막히지 않는다"
        "(예전엔 무관한 재알림 기록에 오매치돼 COOLDOWN 으로 막힐 수 있었다)",
        (r6.status_code, r6.get_json()))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드117 서버측 준비/실행", f"{type(e).__name__} {e}")
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
