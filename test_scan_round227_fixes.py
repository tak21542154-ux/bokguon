# -*- coding: utf-8 -*-
"""스캔 227라운드 회귀 — Idempotency-Key 재사용이 '내용이 다른 요청'이어도
   조용히 첫 요청의 사건을 그대로 돌려주고, 두 번째 요청은 흔적 없이
   사라지던 결함(api_v1_case_create·api_insurer_case_create 형제 둘 다).

   idem_key 는 "같은 요청을 두 번 보냈나"만 막도록 설계됐는데(198라운드),
   실제로는 "같은 열쇠"만 보고 내용은 전혀 안 봤다 — 열쇠를 재사용하며
   공종·지역·가견적을 완전히 다르게 보내도 그대로 통과했다. 핵심 내용의
   지문(idem_fingerprint)을 같이 저장해, 같은 열쇠인데 지문이 다르면
   409 로 거절한다. 지문이 없는(이 수정 전에 만들어진) 옛 행은 대조할
   수 없으니 예전처럼 그냥 duplicate 로 넘어간다(하위호환).

      python test_scan_round227_fixes.py
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


print("═" * 72)
print("  스캔 227라운드 회귀 — Idempotency-Key 재사용 시 내용불일치 미검사")
print("═" * 72)

_tmpdir = tempfile.mkdtemp(prefix="round227_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(cases)")]
    conn.close()
    chk("idem_fingerprint" in cols,
        "★★★ 새 DB 스키마에 cases.idem_fingerprint 컬럼이 생긴다", cols)

    RAW_KEY = "bok_live_r227testkey0000000000000000000000000"
    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,status,api_enabled,api_key_hash,login_id,password_hash) "
        "VALUES(?,?,1,?,?,?)",
        ("R227보험사", "활성", A._hash_api_key(RAW_KEY), "r227insurer", "x")).lastrowid
    conn.commit()
    conn.close()

    client = A.app.test_client()
    hdr = {"X-API-Key": RAW_KEY}
    KEY = "r227-idem-key-1"

    # ══════════════════════════════════════════════════════════
    print("\n[1] /api/v1/cases — 같은 열쇠, 다른 내용")
    # ──────────────────────────────────────────────────────────
    r1 = client.post("/api/v1/cases", headers={**hdr, "Idempotency-Key": KEY},
                      json={"category": "유리·샷시·자동문", "address": "서울시 강남구", "est_price": "500000"})
    chk(r1.status_code == 201, "STEP 첫 요청은 정상 접수된다(과잉차단 아님)",
        (r1.status_code, r1.get_json()))
    first_case_no = r1.get_json().get("case_no") if r1.status_code == 201 else None

    r2 = client.post("/api/v1/cases", headers={**hdr, "Idempotency-Key": KEY},
                      json={"category": "가드레일·방호울타리", "address": "부산시 해운대구", "est_price": "30000000"})
    chk(r2.status_code == 409 and r2.get_json().get("code") == "IDEM_KEY_MISMATCH",
        "★★★★ 같은 열쇠로 완전히 다른 내용(공종·지역·가견적)을 보내면 이제 409 "
        "IDEM_KEY_MISMATCH 로 거절된다(예전엔 조용히 첫 요청 사건을 그대로 "
        "돌려주고 이 두 번째 요청은 흔적 없이 사라졌다)",
        (r2.status_code, r2.get_json()))

    conn = DB.get_db()
    n_cases = conn.execute("SELECT COUNT(*) n FROM cases").fetchone()["n"]
    conn.close()
    chk(n_cases == 1,
        "★★★ 거절된 두 번째 요청은 사건을 만들지 않는다(중복도 오염도 없음)", n_cases)

    r3 = client.post("/api/v1/cases", headers={**hdr, "Idempotency-Key": KEY},
                      json={"category": "유리·샷시·자동문", "address": "서울시 강남구", "est_price": "500000"})
    chk(r3.status_code == 200 and r3.get_json().get("duplicate") is True
        and r3.get_json().get("case_no") == first_case_no,
        "STEP 같은 열쇠·같은 내용(진짜 재시도)은 예전처럼 200 duplicate 로 "
        "정상 처리된다(과잉차단 아님)", (r3.status_code, r3.get_json()))

    # ══════════════════════════════════════════════════════════
    print("\n[2] /api/insurer/cases(포털) — 같은 형제 결함")
    # ──────────────────────────────────────────────────────────
    portal = A.app.test_client()
    _tok = "r227-portal-csrf"
    with portal.session_transaction() as sess:
        sess["insurer_id"] = iid; sess["insurer_login"] = "r227insurer"
        sess["insurer_name"] = "R227보험사"; sess["_csrf"] = _tok
    phdr = {"X-CSRF-Token": _tok}
    PKEY = "r227-portal-idem-1"

    p1 = portal.post("/api/insurer/cases", headers=phdr,
                      json={"category": "누수·배관·설비", "address": "인천시 남동구", "est_price": "800000",
                            "idempotency_key": PKEY})
    chk(p1.status_code == 200 and p1.get_json().get("ok") is True,
        "STEP 포털 첫 요청도 정상 접수된다(과잉차단 아님)", (p1.status_code, p1.get_json()))

    p2 = portal.post("/api/insurer/cases", headers=phdr,
                      json={"category": "지붕·판넬·캐노피", "address": "대전시 유성구", "est_price": "12000000",
                            "idempotency_key": PKEY})
    chk(p2.status_code == 409 and p2.get_json().get("code") == "IDEM_KEY_MISMATCH",
        "★★★★ 포털 경로도 같은 열쇠·다른 내용이면 409 로 거절된다"
        "(api_v1_case_create 와 같은 지문 대조를 형제 함수에도 동일 적용)",
        (p2.status_code, p2.get_json()))

    # ══════════════════════════════════════════════════════════
    print("\n[3] 하위호환 — 지문이 없는 옛 행(이 수정 전 데이터)")
    # ──────────────────────────────────────────────────────────
    OLD_KEY = "r227-legacy-key"
    conn = DB.get_db()
    conn.execute(
        "INSERT INTO cases(case_no,status,category,region,address,est_price,insurer_id,idem_key,is_demo) "
        "VALUES('26-90001','접수','유리','서울','서울시 종로구',300000,?,?,0)",
        (iid, OLD_KEY))
    conn.commit()
    conn.close()
    r_legacy = client.post("/api/v1/cases", headers={**hdr, "Idempotency-Key": OLD_KEY},
                            json={"category": "완전히다른공종", "address": "다른주소", "est_price": "999999999"})
    chk(r_legacy.status_code == 200 and r_legacy.get_json().get("duplicate") is True,
        "STEP 지문이 NULL인 옛 행은 내용이 달라도 409 로 오판하지 않고 "
        "예전처럼 duplicate 로 넘어간다(하위호환 — 지문을 대조할 근거가 없다)",
        (r_legacy.status_code, r_legacy.get_json()))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드227 서버측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
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
