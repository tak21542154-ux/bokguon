# -*- coding: utf-8 -*-
"""스캔 116라운드 회귀 — 협력사포털 등급게이트 4곳, 시공증거 관문 낙찰업체본인 미확인,
   auctions.is_demo 영구 미백필.

  [1] (UX·교착) 협력사 포털의 dpClaim(출동수락)·dpArrive(도착보고)·
      dpNoRepair(미수선종결)·reBidForm(재경매입찰) 4곳에 등급게이트(canAct/canBid)
      가 없었다 — 서버는 전부 중간관리자 이상으로 잠그는데 화면만 안 가려서,
      하위관리자(조회·접수) 계정이 확인창까지 통과한 뒤에야 403을 봤다. dpClaim은
      선착순 30분 안에 눌러야 하는 되돌릴 수 없는 확정행위라 특히 치명적이다.
  [2] (금전·하자보증) 완료보고·검수승인(정산생성) 관문이 '협력사가 올렸나'만
      보고 '어느 협력사가 올렸나'는 안 봤다 — 2트랙 접수(사진없이 접수→업체A
      출동→발주처 부동의→업체C 낙찰)에서 C가 사진을 한 장도 안 올려도 A의
      사진으로 두 관문이 통과됐다.
  [3] (데이터정합) auctions.is_demo 를 채우는 코드가 어디에도 없었다 —
      go-live 미리보기가 삭제 대상 경매 수를 실제보다 적게 보여줬다.

      python test_scan_round116_fixes.py
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
DB_SRC = read("db.py")
PARTNER_SRC = read("templates/partner_portal.html")

print("═" * 72)
print("  스캔 116라운드 회귀 — 협력사포털 등급게이트·시공증거 낙찰업체본인·auctions is_demo")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
chk('${canAct() ? `<button class="btn p sm" data-act="dpClaim"' in PARTNER_SRC,
    "★★★ dpClaim(출동수락)에 등급게이트가 생겼다")
chk('${canAct() ? `\n          <button class="btn p sm" data-act="dpArrive"' in PARTNER_SRC,
    "★★ dpArrive·dpNoRepair 에 등급게이트가 생겼다")
chk("? (canBid()" in PARTNER_SRC and "중간관리자 이상인 시행사" in PARTNER_SRC,
    "★★ reBidForm 에 canBid()(등급+시행사) 게이트가 생겼다")

pc_body = _py_fn_body(APP_SRC, "api_partner_complete")
chk("uploader_role='협력사' AND partner_id=?\", (cid, pid)" in pc_body,
    "★★★ 완료보고 관문이 낙찰업체 본인 사진만 증거로 인정한다")

ca_body = _py_fn_body(APP_SRC, "api_case_approve")
chk('uploader_role=\'협력사\' AND partner_id=?"' in ca_body and '(cid, c["partner_id"])' in ca_body,
    "★★★ 검수승인(정산생성) 관문도 낙찰업체 본인 사진만 증거로 인정한다")

cps_body = _py_fn_body(APP_SRC, "_case_photos_stat")
chk("def _case_photos_stat(conn, cid, partner_id=None):" in APP_SRC
    and "where_p = \"\" if partner_id is None" in cps_body,
    "★★ 표시용 사진집계도 낙찰업체 지정 시 그 업체 것만 센다")

chk('("auctions",\n     """UPDATE auctions SET is_demo=1' in DB_SRC,
    "★★★ auctions 도 데모표식 백필 목록에 들어갔다(96·100라운드가 두 번 놓친 자리)")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[4] 실행 — 실제 시나리오를 돌린다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round116_")
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
                 "VALUES('r116admin','x','검증','중간관리자')")
    conn.commit()
    admin = A.app.test_client()
    _tok = "r116-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r116admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    # ── [2] 완료보고 — 낙찰업체(C) 아닌 전 업체(A)의 사진으로는 통과 못 한다 ──
    p_a = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R116업체A','시행사','활성')").lastrowid
    p_c = conn.execute(
        "INSERT INTO partners(name,partner_type,status,login_id,password_hash) "
        "VALUES('R116업체C','시행사','활성','r116pc','x')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,partner_name,is_demo) "
        "VALUES('R116-C1','시공중','가드레일','서울',?,'R116업체C',0)", (p_c,)).lastrowid
    # 2트랙 접수에서 먼저 출동했던 A가 남긴 착공전 사진(A는 이후 부동의로 탈락)
    conn.execute(
        "INSERT INTO photos(case_id,uploader,uploader_role,partner_id,rel_path,orig_name,"
        "                   mime,ext,size,sha256,kind,review_status,created_at) "
        "VALUES(?,'R116업체A','협력사',?,'a.jpg','a.jpg','image/jpeg','jpg',1,'r116sha_a',"
        "       '착공전','승인',?)", (cid, p_a, DB.now()))
    conn.commit()

    partner_c = A.app.test_client()
    with partner_c.session_transaction() as psess:
        psess["partner_id"] = p_c
        psess["_csrf"] = "r116-partner-csrf"
    _phdr = {"X-CSRF-Token": "r116-partner-csrf"}

    r1 = partner_c.post(f"/api/partner/cases/{cid}/complete", headers=_phdr, json={"memo": "완료"})
    chk(r1.status_code == 409 and r1.get_json().get("code") == "NO_PHOTO",
        "★★★ 낙찰업체(C)가 사진을 안 올렸으면, 전 업체(A)의 사진이 있어도 완료보고를 막는다"
        "(예전엔 A의 사진으로 그대로 통과됐다)",
        (r1.status_code, r1.get_json()))

    # C가 자기 사진을 올리면 정상적으로 완료보고된다 — 과잉차단 아님
    conn.execute(
        "INSERT INTO photos(case_id,uploader,uploader_role,partner_id,rel_path,orig_name,"
        "                   mime,ext,size,sha256,kind,review_status,created_at) "
        "VALUES(?,'R116업체C','협력사',?,'c.jpg','c.jpg','image/jpeg','jpg',1,'r116sha_c',"
        "       '완료','승인',?)", (cid, p_c, DB.now()))
    conn.commit()
    r2 = partner_c.post(f"/api/partner/cases/{cid}/complete", headers=_phdr, json={"memo": "완료"})
    chk(r2.status_code == 200,
        "STEP 낙찰업체 본인 사진이 있으면 정상적으로 완료보고된다(과잉차단 아님)",
        (r2.status_code, r2.get_data(as_text=True)[:200]))

    # ── [3] 검수승인(정산생성) — 마찬가지로 낙찰업체 본인 사진만 본다 ──────
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,award_amount,partner_id,"
        "                  partner_name,is_demo) "
        "VALUES('R116-C2','검수대기','가드레일','서울',4000000,?,'R116업체C',0)", (p_c,)).lastrowid
    conn.execute(
        "INSERT INTO photos(case_id,uploader,uploader_role,partner_id,rel_path,orig_name,"
        "                   mime,ext,size,sha256,kind,review_status,created_at) "
        "VALUES(?,'R116업체A','협력사',?,'a2.jpg','a2.jpg','image/jpeg','jpg',1,'r116sha_a2',"
        "       '완료','승인',?)", (cid2, p_a, DB.now()))
    conn.commit()

    r3 = admin.post(f"/api/cases/{cid2}/approve", headers=_hdr)
    chk(r3.status_code == 409 and r3.get_json().get("code") == "NO_PHOTO",
        "★★★ 검수승인도 전 업체(A) 사진만으로는 통과 못 한다(낙찰업체는 C)"
        "(예전엔 그대로 통과해 정산이 생성됐다)",
        (r3.status_code, r3.get_json()))
    sett = conn.execute("SELECT id FROM settlements WHERE case_id=?", (cid2,)).fetchone()
    chk(sett is None, "STEP 막힌 요청이 정산을 안 만들었다", sett)

    # 표시용 집계(_case_photos_stat)도 같은 결론이어야 한다
    r3b = admin.get(f"/api/cases/{cid2}/detail", headers=_hdr)
    chk(r3b.get_json()["photos"]["total"] == 0,
        "★★ 표시용 사진집계도 전 업체(A) 사진을 낙찰업체(C) 시공 증거로 안 센다",
        r3b.get_json()["photos"])

    # ── [4] auctions.is_demo 백필 ─────────────────────────────────────
    cid_demo = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R116-DEMO','입찰중','누수','서울',1)").lastrowid
    aid_demo = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,NULL,'원경매',0,'진행',0,0,0,?,?)", (cid_demo, DB.now(), DB.now())).lastrowid
    conn.commit()
    before = conn.execute("SELECT is_demo FROM auctions WHERE id=?", (aid_demo,)).fetchone()
    chk((before["is_demo"] or 0) == 0, "STEP 백필 전에는 auctions.is_demo 가 0이다(현재 버그 상태 재현)",
        dict(before))
    DB._backfill_child_is_demo(conn)
    conn.commit()
    after = conn.execute("SELECT is_demo FROM auctions WHERE id=?", (aid_demo,)).fetchone()
    chk(after["is_demo"] == 1,
        "★★★ 백필 실행 뒤 데모 사건의 auctions.is_demo 가 1로 채워진다"
        "(예전엔 채우는 코드가 없어 go-live 미리보기가 삭제 대상을 실제보다 적게 보여줬다)",
        dict(after))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드116 서버측 준비/실행", f"{type(e).__name__} {e}")
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
