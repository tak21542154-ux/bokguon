# -*- coding: utf-8 -*-
"""스캔 51라운드 회귀 — 재경매 투찰 관문 누락(무등록·데모) + 사진 용량 상한 우회.

  조사 에이전트(+직접 코드 대조)가 실측으로 증명한 결함 2건:

  ① api_partner_reauction_bid(/api/partner/reauction-bids) 가 형제 라우트
     api_partner_bid(/api/partner/bids) 의 자격 검사 3개 중 **건설업 무등록
     검사만 베끼지 않았다.** 재경매(특히 전체재경매)는 낙찰되면 도급 전체가
     넘어가므로, 무등록 업체가 통값 입찰 관문을 그대로 우회해 도급을 받을 수
     있었다(건설산업기본법 §25조 제2항). 같은 라우트가 **데모 사건 차단도**
     빠뜨렸다(원경매 투찰엔 있음).

  ② 사진 업로드 3곳(협력사 시공사진·피해현장사진·하자사진)의 사건 누적 용량
     상한 검사가 **이미 저장된 바이트만** 보고 "이번에 들어올 바이트"를 더하지
     않았다 — 상한을 깨는 바로 그 요청은 항상 통과했다(에이전트 실측: 상한
     1MB 인데 8장·3.3MB 저장 = 상한의 3.15배). 세 곳 모두 같은 결함이 복붙돼
     있었으므로 공유 헬퍼(_case_photo_quota_guard) 하나로 모았다.

      python test_scan_round51_fixes.py
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
print("  스캔 51라운드 회귀 — 재경매 자격검사 누락 + 사진 용량 상한 우회")
print("═" * 72)


def _body(fn_name):
    start = APP_SRC.index(f"\ndef {fn_name}(")
    end = APP_SRC.find("\ndef ", start + 1)
    return APP_SRC[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
reauc = _body("api_partner_reauction_bid")
chk("NO_LICENSE" in reauc and "license_status" in reauc,
    "★★★ ① api_partner_reauction_bid — 무등록 업체 차단 검사가 생겼다")
chk('"is_demo"' in reauc or "case_demo" in reauc or "is_demo" in reauc,
    "★★ ① api_partner_reauction_bid — 데모 사건 차단 검사가 생겼다")

# 형제(이미 정상이던) 라우트는 손대지 않았는지 — 회귀 방지용 대조
orig_bid = _body("api_partner_bid")
chk("NO_LICENSE" in orig_bid and "license_status" in orig_bid,
    "api_partner_bid(형제, 원래 정상) — 그대로 무등록 검사를 갖고 있다(안 건드림)")

# 공유 헬퍼가 세 호출지점 모두에서 쓰이는가
chk(APP_SRC.count("_case_photo_quota_guard(conn, cid, files)")
    + APP_SRC.count("_case_photo_quota_guard(conn, _cid_for_limit, files)") == 3,
    "★★★ ② 사진 업로드 3곳(협력사·피해현장·하자) 모두 공유 헬퍼를 쓴다",
    APP_SRC.count("_case_photo_quota_guard("))
guard_body = _body("_case_photo_quota_guard")
chk('u["b"] + incoming' in guard_body,
    "★★★ ② 헬퍼가 '이미 저장 + 이번에 들어올 바이트'를 더해서 비교한다(옛 결함: 저장분만 비교)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 서버(test_client)로 두 결함을 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round51_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    client = A.app.test_client()
    _tok = "regress-round51-csrf-token"
    _hdr = {"X-CSRF-Token": _tok}

    def _partner_sess(sess, pid):
        sess["partner_id"] = pid
        sess["_csrf"] = _tok

    # ── ① 무등록 업체 — 재경매 투찰은 auction_id 가 실존하지 않아도
    #     자격검사에서 먼저 걸려야 한다(라우트 안에서 license 검사가 au 조회보다 앞선다) ──
    conn = DB.get_db()
    p_nolic = conn.execute(
        "INSERT INTO partners(name,partner_type,status,license_status) "
        "VALUES('검증무등록51','시행사','활성','무등록')").lastrowid
    conn.commit(); conn.close()

    with client.session_transaction() as sess:
        _partner_sess(sess, p_nolic)
    r1 = client.post("/api/partner/reauction-bids",
                      json={"auction_id": 999999, "amount": 1000000, "days": 5}, headers=_hdr)
    d1 = r1.get_json()
    chk(r1.status_code == 403 and d1.get("code") == "NO_LICENSE",
        "★★★ ① 무등록 업체의 재경매 투찰이 403 NO_LICENSE 로 막힌다(고치기 전엔 통과)",
        (r1.status_code, d1))

    # ── ② 데모 사건의 전체재경매 — 정상(미확인) 업체라도 막혀야 한다 ──
    conn = DB.get_db()
    p_ok = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('검증정상51','시행사','활성')"
    ).lastrowid
    p_incumbent = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('검증원업체51','시공사','활성')"
    ).lastrowid
    cid_demo = conn.execute(
        "INSERT INTO cases(case_no,status,is_demo,category,region) "
        "VALUES('검증51-DEMO','시공중',1,'금속','서울')").lastrowid
    coid_demo = conn.execute(
        "INSERT INTO change_orders(case_id,round,status,combined_amount,"
        "                          incumbent_amount,incumbent_partner_id) "
        "VALUES(?,1,'전체재경매중',5000000,4000000,?)", (cid_demo, p_incumbent)).lastrowid
    auid_demo = conn.execute(
        "INSERT INTO auctions(case_id,status,change_order_id,kind) "
        "VALUES(?,'진행',?,'전체재경매')", (cid_demo, coid_demo)).lastrowid
    conn.commit(); conn.close()

    with client.session_transaction() as sess:
        _partner_sess(sess, p_ok)
    r2 = client.post("/api/partner/reauction-bids",
                      json={"auction_id": auid_demo, "amount": 4500000, "days": 5}, headers=_hdr)
    d2 = r2.get_json()
    chk(r2.status_code == 404 and d2.get("ok") is False,
        "★★★ ② 데모 사건의 재경매 투찰이 막힌다(고치기 전엔 200으로 통과)", (r2.status_code, d2))
    conn = DB.get_db()
    n_bids_demo = conn.execute(
        "SELECT COUNT(*) FROM bids WHERE auction_id=?", (auid_demo,)).fetchone()[0]
    conn.close()
    chk(n_bids_demo == 0, "② 데모 사건에 실제로 입찰 행이 안 생겼다", n_bids_demo)

    # ── 대조군 — 정상(비데모) 사건·정상 업체는 재경매 투찰이 그대로 성립한다 ──
    conn = DB.get_db()
    cid_ok = conn.execute(
        "INSERT INTO cases(case_no,status,is_demo,category,region) "
        "VALUES('검증51-OK','시공중',0,'금속','서울')").lastrowid
    coid_ok = conn.execute(
        "INSERT INTO change_orders(case_id,round,status,combined_amount,"
        "                          incumbent_amount,incumbent_partner_id) "
        "VALUES(?,1,'전체재경매중',5000000,4000000,?)", (cid_ok, p_incumbent)).lastrowid
    auid_ok = conn.execute(
        "INSERT INTO auctions(case_id,status,change_order_id,kind) "
        "VALUES(?,'진행',?,'전체재경매')", (cid_ok, coid_ok)).lastrowid
    conn.commit(); conn.close()

    r3 = client.post("/api/partner/reauction-bids",
                      json={"auction_id": auid_ok, "amount": 4500000, "days": 5}, headers=_hdr)
    chk(r3.status_code == 200, "★ 대조군 — 정상 업체·정상 사건의 재경매 투찰은 그대로 성립한다(과잉차단 아님)",
        (r3.status_code, r3.get_json()))

    # ══════════════════════════════════════════════════════════
    print("\n[3] 실행 — 실제 사진 업로드 2회로 용량 상한 우회를 재현")
    # ──────────────────────────────────────────────────────────
    from PIL import Image

    def _noise_jpeg(seed_byte):
        w = h = 500
        data = bytes(((b + seed_byte) % 256) for b in os.urandom(w * h * 3))
        img = Image.frombytes("RGB", (w, h), data)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()

    jpg1 = _noise_jpeg(0)
    jpg2 = _noise_jpeg(77)

    conn = DB.get_db()
    cid_up = conn.execute(
        "INSERT INTO cases(case_no,status,is_demo,partner_id,category,region) "
        "VALUES('검증51-UP','시공중',0,?,'금속','서울')", (p_ok,)).lastrowid
    conn.commit(); conn.close()

    _orig_cap = A.PHOTO.MAX_BYTES_PER_CASE
    try:
        with client.session_transaction() as sess:
            _partner_sess(sess, p_ok)
        #  ⚠ 서버가 저장 전에 EXIF 제거·재인코딩을 하므로 저장 크기는 업로드
        #    원본 크기와 다르다 — 상한은 **실제 저장된 크기**를 기준으로 잡는다.
        ru1 = client.post(f"/api/partner/cases/{cid_up}/photos",
                          data={"photos": (io.BytesIO(jpg1), "a.jpg")},
                          content_type="multipart/form-data", headers=_hdr)
        du1 = ru1.get_json()
        chk(ru1.status_code == 200 and du1.get("ok") is True,
            "③ 1차 업로드(기본 상한 이내) — 정상 저장된다", (ru1.status_code, du1))

        conn = DB.get_db()
        stored_after_1 = conn.execute(
            "SELECT COALESCE(SUM(size),0) FROM photos WHERE case_id=?", (cid_up,)).fetchone()[0]
        conn.close()
        chk(stored_after_1 > 0, "③ 1차 업로드 직후 저장 용량이 0보다 크다", stored_after_1)

        #  한 장은 여유, 두 장째부터 넘치도록 상한을 1차 저장량의 1.5배로 낮춘다.
        A.PHOTO.MAX_BYTES_PER_CASE = int(stored_after_1 * 1.5)

        ru2 = client.post(f"/api/partner/cases/{cid_up}/photos",
                          data={"photos": (io.BytesIO(jpg2), "b.jpg")},
                          content_type="multipart/form-data", headers=_hdr)
        du2 = ru2.get_json()
        chk(ru2.status_code == 409 and du2.get("code") == "CASE_SIZE_LIMIT",
            "★★★ ③ 2차 업로드(상한을 넘기는 바로 그 요청) — 409 로 막힌다(고치기 전엔 200)",
            (ru2.status_code, du2))

        conn = DB.get_db()
        stored_after_2 = conn.execute(
            "SELECT COALESCE(SUM(size),0) FROM photos WHERE case_id=?", (cid_up,)).fetchone()[0]
        conn.close()
        chk(stored_after_2 == stored_after_1,
            "★★★ ③ 차단된 2차 파일은 실제로 저장되지 않았다(용량이 늘지 않았다)",
            (stored_after_2, stored_after_1))
    finally:
        A.PHOTO.MAX_BYTES_PER_CASE = _orig_cap

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드51 실측 준비/실행", f"{type(e).__name__} {e}")
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
