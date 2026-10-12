# -*- coding: utf-8 -*-
"""스캔 80라운드 회귀 — 이메일 형식 검사(RE_EMAIL) 누락 5곳.

  RE_EMAIL 검사는 존재했지만 실제로 쓰인 곳은 관리자의 "연락처 관리 → 연락처
  수정"(api_contact_update) 단 한 곳이었다. 같은 partners.email 컬럼(또는
  insurers.email)에 쓰는 나머지 5개 경로 — 업체 정보수정(api_partner_update),
  업체 직접등록(api_partner_create), 입점신청 직접접수(api_application_create),
  협력사 마이페이지(api_partner_profile_update), 보험사 마이페이지
  (api_insurer_profile_update) — 는 전부 무검사로 값을 그대로 저장했다.

  형식이 깨진 주소가 저장되면: ① 같은 값을 나중에 연락처 화면에서 저장하려는
  순간 400이 뜬다(두 화면이 같은 셀을 두고 어긋난다) ② 발송 대상 집계
  (_campaign_recipients)는 "비어있는지"만 보고 형식은 안 봐서, 깨진 주소가
  캠페인 수신 대상에 그대로 실린다.

      python test_scan_round80_fixes.py
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
print("  스캔 80라운드 회귀 — 이메일 형식 검사(RE_EMAIL) 누락 5곳")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
for fn in ("api_partner_update", "api_partner_create", "api_application_create",
           "api_partner_profile_update", "api_insurer_profile_update"):
    body = _py_fn_body(APP_SRC, fn)
    chk("RE_EMAIL.match" in body, f"★★ {fn} 가 RE_EMAIL 형식 검사를 거친다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실서버 경로(Flask test_client + 임시 DB)로 서버 응답 확인")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round80_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    BAD = "hong@gmail"          # TLD 없음 — RE_EMAIL 불통과
    GOOD1, GOOD2, GOOD3, GOOD4, GOOD5 = (f"r80-{i}@example.com" for i in range(1, 6))
    chk(not A.RE_EMAIL.match(BAD) and A.RE_EMAIL.match(GOOD1),
        "STEP (참고) 테스트용 이메일이 실제로 무효/유효로 갈린다")

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','중간관리자')")
    pid_partner = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R80협력사','시행사','활성')"
    ).lastrowid
    iid_insurer = conn.execute("INSERT INTO insurers(name) VALUES('R80보험')").lastrowid
    conn.commit()
    conn.close()

    admin = A.app.test_client()
    _atok = "r80-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _atok
    _ahdr = {"X-CSRF-Token": _atok}

    # ── ① api_partner_update ──
    r1 = admin.patch(f"/api/partners/{pid_partner}", json={"email": BAD}, headers=_ahdr)
    chk(r1.status_code == 400,
        "★★★ ① 업체 정보수정 — 무효한 이메일은 400으로 거부된다"
        "(고치기 전엔 그대로 저장됐다)", f"{r1.status_code} {r1.get_json()}")
    r1b = admin.patch(f"/api/partners/{pid_partner}", json={"email": GOOD1}, headers=_ahdr)
    chk(r1b.status_code == 200, "STEP 대조군 — 유효한 이메일은 통과한다", f"{r1b.status_code} {r1b.get_json()}")

    # ── ② api_partner_create ──
    r2 = admin.post("/api/partners", json={"name": "R80신규1", "email": BAD}, headers=_ahdr)
    chk(r2.status_code == 400,
        "★★★ ② 업체 직접등록 — 무효한 이메일은 400으로 거부된다", f"{r2.status_code} {r2.get_json()}")
    r2b = admin.post("/api/partners", json={"name": "R80신규2", "email": GOOD2}, headers=_ahdr)
    chk(r2b.status_code == 200 and (r2b.get_json() or {}).get("ok"),
        "STEP 대조군 — 유효한 이메일이면 정상 등록된다", f"{r2b.status_code} {r2b.get_json()}")

    # ── ③ api_application_create ──
    r3 = admin.post("/api/applications/manual",
                     json={"company": "R80입점1", "major": "가드레일·방호울타리", "email": BAD},
                     headers=_ahdr)
    chk(r3.status_code == 400,
        "★★★ ③ 입점신청 직접접수 — 무효한 이메일은 400으로 거부된다", f"{r3.status_code} {r3.get_json()}")
    r3b = admin.post("/api/applications/manual",
                      json={"company": "R80입점2", "major": "가드레일·방호울타리", "email": GOOD3},
                      headers=_ahdr)
    chk(r3b.status_code == 200 and (r3b.get_json() or {}).get("ok"),
        "STEP 대조군 — 유효한 이메일이면 정상 접수된다", f"{r3b.status_code} {r3b.get_json()}")

    # ── ④ api_partner_profile_update ──
    partner_client = A.app.test_client()
    _ptok = "r80-partner-csrf"
    with partner_client.session_transaction() as sess:
        sess["partner_id"] = pid_partner
        sess["_csrf"] = _ptok
    _phdr = {"X-CSRF-Token": _ptok}
    r4 = partner_client.patch("/api/partner/profile", json={"email": BAD}, headers=_phdr)
    chk(r4.status_code == 400,
        "★★★ ④ 협력사 마이페이지 — 무효한 이메일은 400으로 거부된다", f"{r4.status_code} {r4.get_json()}")
    r4b = partner_client.patch("/api/partner/profile", json={"email": GOOD4}, headers=_phdr)
    chk(r4b.status_code == 200, "STEP 대조군 — 유효한 이메일은 통과한다", f"{r4b.status_code} {r4b.get_json()}")

    # ── ⑤ api_insurer_profile_update ──
    insurer_client = A.app.test_client()
    _itok = "r80-insurer-csrf"
    with insurer_client.session_transaction() as sess:
        sess["insurer_id"] = iid_insurer
        sess["_csrf"] = _itok
    _ihdr = {"X-CSRF-Token": _itok}
    r5 = insurer_client.patch("/api/insurer/profile", json={"email": BAD}, headers=_ihdr)
    chk(r5.status_code == 400,
        "★★★ ⑤ 보험사 마이페이지 — 무효한 이메일은 400으로 거부된다", f"{r5.status_code} {r5.get_json()}")
    r5b = insurer_client.patch("/api/insurer/profile", json={"email": GOOD5}, headers=_ihdr)
    chk(r5b.status_code == 200, "STEP 대조군 — 유효한 이메일은 통과한다", f"{r5b.status_code} {r5b.get_json()}")

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드80 서버측 준비/실행", f"{type(e).__name__} {e}")
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
