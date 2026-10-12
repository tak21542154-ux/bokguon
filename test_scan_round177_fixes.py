# -*- coding: utf-8 -*-
"""스캔 177라운드 회귀 — partner_type/status 화이트리스트(101·174라운드)가
같은 값을 쓰는 형제 3곳(공개 입점신청·관리자 직접등록)엔 없던 결함.

  api_partner_update(협력사 정보수정)만 이 두 값을 화이트리스트로 막는데,
  같은 값의 다른 생성 경로들은 안 막혔다:
    ① POST /api/applications — 인증 없는 공개폼(비로그인·CSRF면제). 승인되면
       partner_applications.partner_type 이 partners.partner_type 으로 그대로
       복사돼(6952행), 통값·재경매 입찰 자격판정(4669·4876행)이 오염된다.
       가장 가까운 형제(관리자 수기접수, api_application_create)는 이미
       "화이트리스트 아니면 기본값" 관용구를 쓰고 있어 그대로 맞췄다.
    ② POST /api/partners — 관리자 직접등록. 바로 아래 있는 수정 라우트와
       같은 자원인데 등록 쪽만 검증이 없었다 — 수정 라우트와 같은 문턱
       (화이트리스트 아니면 400)을 그대로 맞췄다.

      python test_scan_round177_fixes.py
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

print("=" * 72)
print("  스캔 177라운드 회귀 — 공개입점신청·관리자직접등록의 구분/상태값 검증 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_create_application():")
i1 = APP_SRC.index("\n@app.", i0 + 1)
chk('_ptype = d.get("partner_type") if d.get("partner_type") in PARTNER_TYPES else "시공사"'
    in APP_SRC[i0:i1],
    "★★★ 공개 입점신청(api_create_application)이 partner_type 을 화이트리스트로 거른다")

i2 = APP_SRC.index("def api_partner_create():")
i3 = APP_SRC.index("\n@app.", i2 + 1)
body3 = APP_SRC[i2:i3]
chk('if d.get("partner_type") and d["partner_type"] not in PARTNER_TYPES:' in body3,
    "★★★ 관리자 직접등록(api_partner_create)이 partner_type 을 화이트리스트로 막는다")
chk('if d.get("status") and d["status"] not in PARTNER_STATUSES:' in body3,
    "★★★ 관리자 직접등록이 status 도 화이트리스트로 막는다")

# ============================================================
print("\n[2] 실행 — 공개폼은 조용히 기본값으로, 관리자등록은 명시적으로 거부")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round177_")
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
                 "VALUES('admin','x','검증','최고관리자')")
    conn.commit(); conn.close()

    public = A.app.test_client()

    # ① 공개 입점신청 — 비로그인, CSRF 헤더 없이(면제 라우트)
    r1 = public.post("/api/applications", json={
        "company": "R177테스트업체", "phone": "010-0000-0000",
        "agree_privacy": True, "partner_type": "원청",
        #  ⚠ [라운드288] 공개 접수가 이제 상시 인력 수(staff_count)를 필수로
        #    본다 — 이 테스트는 partner_type 화이트리스트만 검증하는 게
        #    목적이라 그 관문을 그냥 통과할 값만 채운다.
        "staff_count": "5"})
    j1 = r1.get_json() or {}
    chk(r1.status_code == 200 and j1.get("ok") is True,
        "공개폼 접수 자체는 거부되지 않는다(임의값 이유로 400 내지 않음)", (r1.status_code, j1))

    conn = DB.get_db()
    row = conn.execute(
        "SELECT partner_type FROM partner_applications WHERE company='R177테스트업체'").fetchone()
    chk(row is not None and row["partner_type"] == "시공사",
        "★★★ 임의 구분값('원청')이 안전한 기본값으로 조용히 대체됨"
        "(고치기 전엔 '원청'이 그대로 저장돼 승인 시 partners 로 복사됐다)",
        row["partner_type"] if row else None)
    conn.close()

    # 정상값은 그대로 통과해야 한다 — 과도필터 아님
    r1b = public.post("/api/applications", json={
        "company": "R177테스트업체2", "phone": "010-0000-0001",
        "agree_privacy": True, "partner_type": "시행사",
        "staff_count": "5"})   # ⚠ [라운드288] 위와 같은 이유
    conn = DB.get_db()
    row_b = conn.execute(
        "SELECT partner_type FROM partner_applications WHERE company='R177테스트업체2'").fetchone()
    chk(r1b.status_code == 200 and row_b is not None and row_b["partner_type"] == "시행사",
        "정상 구분값(시행사)은 그대로 저장됨(과도필터 아님)",
        row_b["partner_type"] if row_b else None)
    conn.close()

    # ② 관리자 직접등록 — 임의 구분값은 명시적으로 거부
    admin = A.app.test_client()
    atok = "r177-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_name"] = "검증"; sess["_csrf"] = atok
    ahdr = {"X-CSRF-Token": atok}

    r2 = admin.post("/api/partners", json={"name": "R177관리자등록", "partner_type": "원청"},
                     headers=ahdr)
    j2 = r2.get_json() or {}
    chk(r2.status_code == 400 and j2.get("ok") is False,
        "★★★ 관리자 직접등록의 임의 구분값은 400 으로 거부됨"
        "(고치기 전엔 'partner_type'='원청' 그대로 저장됐다)", (r2.status_code, j2))

    r3 = admin.post("/api/partners", json={"name": "R177관리자등록2", "status": "이상한상태"},
                     headers=ahdr)
    j3 = r3.get_json() or {}
    chk(r3.status_code == 400 and j3.get("ok") is False,
        "★★★ 관리자 직접등록의 임의 상태값도 400 으로 거부됨", (r3.status_code, j3))

    conn = DB.get_db()
    n_bad = conn.execute(
        "SELECT COUNT(*) FROM partners WHERE name IN ('R177관리자등록','R177관리자등록2')"
    ).fetchone()[0]
    chk(n_bad == 0, "★★★ 거부된 등록 요청은 실제로 행을 남기지 않는다", n_bad)
    conn.close()

    # 정상값(관리자등록)은 여전히 통과 — 과도필터 아님
    r4 = admin.post("/api/partners", json={"name": "R177관리자등록3", "partner_type": "시행사",
                                            "status": "활성"}, headers=ahdr)
    chk(r4.status_code == 200 and (r4.get_json() or {}).get("ok") is True,
        "관리자 직접등록의 정상값은 여전히 통과함(과도필터 아님)", r4.get_json())
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드177 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
