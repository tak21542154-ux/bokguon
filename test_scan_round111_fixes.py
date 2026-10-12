# -*- coding: utf-8 -*-
"""스캔 111라운드 회귀 — 유찰확정 입찰 무효화 누락, 무입찰경보 회차별 유실,
   유찰·오프라인종결 탈락자 미통지.

  [1] (치명·돈) 화면은 "유찰로 확정하면 제출된 입찰은 채택되지 않습니다"라고
      확인받는데, 서버(api_case_fail_bidding)는 실제로 bids 를 무효화하지
      않았다. 재개(api_case_reopen)가 같은 auctions 행을 재사용하므로,
      다음 회차에 아무도 새로 투찰하지 않아도 반려된 입찰이 살아남아
      마감 점검에서 '성립'으로 잡히고 그 금액 그대로 낙찰될 수 있었다
      (낙찰취소 형제 경로가 이미 막는 것과 동일한 위험).
  [2] (운영) 무입찰경보의 중복방지가 사건 단위·무기한이라, 재개로 같은
      auctions 행이 재사용되면 1회차에 한 번 보낸 뒤로는 2·3회차가 또
      무입찰이어도 영원히 다시 안 울렸다.
  [3] (공정성) 낙찰 3경로는 전부 탈락자에게 결과를 알리는데, 유찰 확정·
      오프라인 종결(둘 다 "입찰이 있었는데 안 됐다")은 아무도 안 알렸다.

      python test_scan_round111_fixes.py
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
print("  스캔 111라운드 회귀 — 유찰확정 입찰방치·무입찰경보 회차유실·탈락자 미통지")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 다섯 지점 모두 확인")
# ──────────────────────────────────────────────────────────────
fb_body = _py_fn_body(APP_SRC, "api_case_fail_bidding")
chk("void_reason='유찰 확정'" in fb_body and "voided_at IS NULL AND auction_id=?" in fb_body,
    "★★★ 유찰 확정이 실제로 입찰을 무효화한다")
chk("low_price=0, bid_count=0" in fb_body and "UPDATE cases SET low_price=NULL" in fb_body,
    "★★★ 유찰 확정이 최저가·건수도 함께 되돌린다(낙찰취소 형제와 동일)")
chk("notify_bid_losers" in fb_body,
    "★★ 유찰 확정이 탈락자(입찰자)에게도 결과를 알린다")

co_body = _py_fn_body(APP_SRC, "api_case_close_offline")
chk("notify_bid_losers" in co_body,
    "★★ 오프라인 전환 종결도 남아 있는 입찰자에게 결과를 알린다")

nbl_body = _py_fn_body(APP_SRC, "notify_bid_losers")
chk("msg=None" in nbl_body and "_msg = msg or" in nbl_body,
    "★ notify_bid_losers 가 메시지를 바꿔 낼 수 있다(낙찰 아닌 경로에서 "
    "'다른 업체로 확정'이라는 거짓 문구를 안 보내려면 필요)")

nba_body = _py_fn_body(APP_SRC, "sweep_no_bid_alert")
chk("nn.created_at >= COALESCE(c.status_at, c.created_at, '1970-01-01')" in nba_body,
    "★★★ 무입찰경보 중복방지가 회차(reopen 이 status_at 을 새로 찍음) 단위다"
    "(status_at·created_at 둘 다 비어도 안전하게 대체)")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[4] 실행 — 실제 시나리오를 돌린다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round111_")
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
                 "VALUES('r111admin','x','검증','중간관리자')")

    # ── [2] 유찰 확정 — 입찰이 실제로 무효화되고, 재개 뒤에도 되살아나지 않는다 ──
    p1 = conn.execute(
        "INSERT INTO partners(name,partner_type,status,login_id) "
        "VALUES('R111갑','시행사','활성','r111p1')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer,insurer_id,is_demo) "
        "VALUES('R111-C1','입찰중','가드레일','서울','R111보험',1,0)").lastrowid
    aid = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,NULL,'원경매',0,'진행',1000000,1,0,"
        "       datetime('now','+9 hours','+2 hours'),?)", (cid, DB.now())).lastrowid
    bid1 = conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,1000000,10,?)", (aid, p1, "R111갑", DB.now())).lastrowid
    conn.commit()

    admin = A.app.test_client()
    _tok = "r111-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r111admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    r1 = admin.post(f"/api/cases/{cid}/fail-bidding", headers=_hdr)
    chk(r1.status_code == 200, "STEP 유찰 확정 요청이 성공한다", (r1.status_code, r1.get_data(as_text=True)[:200]))

    bid_row = conn.execute("SELECT voided_at, void_reason FROM bids WHERE id=?", (bid1,)).fetchone()
    chk(bool(bid_row["voided_at"]),
        "★★★ 유찰 확정 직후 입찰이 실제로 무효화됐다(예전엔 그대로 살아 있었다)",
        dict(bid_row))
    case_row = conn.execute("SELECT status, low_price FROM cases WHERE id=?", (cid,)).fetchone()
    chk(case_row["status"] == "유찰" and case_row["low_price"] is None,
        "★★ 사건 상태가 유찰이고 최저가도 비워졌다", dict(case_row))
    auc_row = conn.execute("SELECT low_price, bid_count FROM auctions WHERE id=?", (aid,)).fetchone()
    chk(auc_row["low_price"] == 0 and auc_row["bid_count"] == 0,
        "★★ 경매 최저가·건수도 0으로 되돌아갔다", dict(auc_row))

    loser_notif = conn.execute(
        "SELECT message FROM notifications WHERE ntype='입찰결과' AND partner_id=? "
        "ORDER BY id DESC LIMIT 1", (p1,)).fetchone()
    chk(bool(loser_notif) and "유찰" in loser_notif["message"] and "다른 업체" not in loser_notif["message"],
        "★★ 입찰자에게 결과가 통지되고, 문구가 '유찰'이지 없는 승자를 지어낸 "
        "'다른 업체로 확정'이 아니다",
        dict(loser_notif) if loser_notif else None)

    r2 = admin.post(f"/api/cases/{cid}/reopen", headers=_hdr)
    chk(r2.status_code == 200, "STEP 재개 요청이 성공한다", (r2.status_code, r2.get_data(as_text=True)[:200]))
    case_row2 = conn.execute("SELECT status, status_at FROM cases WHERE id=?", (cid,)).fetchone()
    chk(case_row2["status"] == "입찰중", "STEP 재개 뒤 사건이 다시 입찰중이다", dict(case_row2))

    live_bids = conn.execute(
        "SELECT COUNT(*) n FROM bids WHERE auction_id=? AND voided_at IS NULL", (aid,)).fetchone()["n"]
    chk(live_bids == 0,
        "★★★ 재개된 2회차에 반려된 1회차 입찰이 살아 있지 않다(예전엔 이 입찰이 "
        "그대로 남아 아무도 새로 투찰하지 않아도 마감 점검이 이 금액으로 낙찰승인을 조를 수 있었다)",
        f"live_bids={live_bids}")

    # ── [3] 오프라인 전환 종결 — 남은 입찰자에게도 결과가 통지된다 ──────────
    p2 = conn.execute(
        "INSERT INTO partners(name,partner_type,status,login_id) "
        "VALUES('R111을','시행사','활성','r111p2')").lastrowid
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer,insurer_id,is_demo) "
        "VALUES('R111-C2','유찰','가드레일','서울','R111보험',1,0)").lastrowid
    aid2 = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,NULL,'원경매',0,'유찰',900000,1,0,?,?)", (cid2, DB.now(), DB.now())).lastrowid
    conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,900000,10,?)", (aid2, p2, "R111을", DB.now()))
    conn.commit()

    r3 = admin.post(f"/api/cases/{cid2}/close-offline", headers=_hdr,
                     json={"reason": "협력사 인근 부재로 플랫폼 진행 불가"})
    chk(r3.status_code == 200, "STEP 오프라인 전환 종결 요청이 성공한다",
        (r3.status_code, r3.get_data(as_text=True)[:200]))
    loser_notif2 = conn.execute(
        "SELECT message FROM notifications WHERE ntype='입찰결과' AND partner_id=? "
        "ORDER BY id DESC LIMIT 1", (p2,)).fetchone()
    chk(bool(loser_notif2) and "오프라인" in loser_notif2["message"],
        "★★ 오프라인 종결 뒤에도 입찰자에게 결과가 통지된다(예전엔 침묵)",
        dict(loser_notif2) if loser_notif2 else None)

    # ── [4] 무입찰경보 — 회차가 바뀌면(status_at 갱신) 다시 울린다 ──────────
    #  ⚠ status_at 을 명시한다 — 실제 접수 코드(app.py:3568)는 항상 이 값을
    #    찍는다. 비워 두면(NULL) SQL 의 `>=` 비교가 전부 미결정이 되어
    #    COALESCE 대체(created_at)로 넘어간다 — 그 경로도 맞는지는 아래에서
    #    별도로 확인한다.
    cid3 = conn.execute(
        "INSERT INTO cases(case_no,insurer,insurer_id,category,region,status,is_demo,status_at) "
        "VALUES('R111-C3','R111보험',1,'누수','서울','입찰중',0,?)", (DB.now(),)).lastrowid
    conn.execute(
        "INSERT INTO auctions(case_id,deadline,status,created_at) "
        "VALUES(?, datetime('now','+9 hours','+20 minutes'), '진행', "
        "       datetime('now','+9 hours','-5 hours'))", (cid3,))
    conn.commit()

    n1 = A.sweep_no_bid_alert(conn)
    chk(n1 == 1, "STEP 무입찰경보 1차 발송 — 정확히 1건", n1)
    n2 = A.sweep_no_bid_alert(conn)
    chk(n2 == 0, "★★ 같은 회차에 다시 돌려도 중복 발송되지 않는다", n2)

    #  api_case_reopen 이 하는 것과 동일하게 status_at 을 새로 찍는다(= 새 회차 시작).
    #  ⚠ DB.now() 는 초 단위 정밀도라, 방금 나간 알림과 지금(status_at 갱신)이
    #    테스트 실행 속도상 같은 초에 몰릴 수 있다 — status_at 을 미래로
    #    앞당기면(예: +10초) 그 다음 알림(n3, 실제 notify() 가 진짜 '지금'을
    #    찍는다)의 created_at 이 그 가짜 미래보다 과거로 남아 오히려 dedup 이
    #    거꾸로 깨진다(실측: n3 가 또 새 게 아니라 재발송으로 잡혔다). 대신
    #    **이미 보낸 알림 쪽을 과거로 밀어낸다** — status_at 은 실제 재개 코드와
    #    똑같이 진짜 '지금'을 찍는다.
    conn.execute(
        "UPDATE notifications SET created_at=datetime('now','+9 hours','-1 hour') "
        " WHERE ntype='무입찰경보' AND case_id=?", (cid3,))
    conn.execute("UPDATE cases SET status_at=datetime('now','+9 hours') WHERE id=?", (cid3,))
    conn.commit()
    n3 = A.sweep_no_bid_alert(conn)
    chk(n3 == 1,
        "★★★ 재개로 회차가 바뀌면 여전히 무입찰이어도 경보가 다시 울린다"
        "(예전엔 사건 단위로 평생 한 번뿐이라 1회차 뒤로는 영원히 침묵했다)",
        n3)

    # ── [4-b] status_at 이 비어 있어도(NULL) created_at 대체로 안전하게 dedup 된다 ──
    #  created_at 은 실제 접수 코드처럼 채운다 — status_at 만 비워(NULL) 그 대체
    #    경로만 따로 본다. 두 값 다 비우면 COALESCE 도 NULL 이 되어 버려
    #    이 시나리오가 의도한 "대체가 실제로 작동하는가"를 못 가린다.
    cid4 = conn.execute(
        "INSERT INTO cases(case_no,insurer,insurer_id,category,region,status,is_demo,"
        "                  created_at,status_at) "
        "VALUES('R111-C4','R111보험',1,'누수','서울','입찰중',0,?,NULL)", (DB.now(),)).lastrowid
    conn.execute(
        "INSERT INTO auctions(case_id,deadline,status,created_at) "
        "VALUES(?, datetime('now','+9 hours','+20 minutes'), '진행', "
        "       datetime('now','+9 hours','-5 hours'))", (cid4,))
    conn.commit()
    n4a = A.sweep_no_bid_alert(conn)
    n4b = A.sweep_no_bid_alert(conn)
    chk(n4a == 1 and n4b == 0,
        "★ status_at 이 NULL 인 사건도 created_at 대체로 정상 dedup 된다"
        "(대체가 없으면 NULL 비교가 항상 미결정이라 매번 다시 발송됐다)",
        (n4a, n4b))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드111 서버측 준비/실행", f"{type(e).__name__} {e}")
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
