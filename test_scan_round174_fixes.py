# -*- coding: utf-8 -*-
"""스캔 174라운드 회귀 — 관리자 업체정보수정(api_partner_update)이 partner_type
을 검증 없이 그대로 기록하던 결함.

  같은 필드 예외처리 줄(101라운드)에서 status 는 PARTNER_STATUSES 화이트리스트로
  막혔는데, 형제 필드 partner_type 은 "화면이 <select> 로만 주는 짧은 고정값"
  이라는 이유로 그대로 남았다. 그런데 이 값은 통값입찰(4662행)·재경매입찰
  (4869행)이 문자열을 그대로 비교하는 자격 관문이다 — 오타·임의 값이 API로
  직접 들어가면 그 업체는 아무 통지도 사유기록도 없이 조용히 입찰길이 막힌다.

      python test_scan_round174_fixes.py
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
print("  스캔 174라운드 회귀 — 업체정보수정의 partner_type 검증 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk('PARTNER_TYPES = ("시행사", "시공사")' in APP_SRC,
    "★★★ PARTNER_TYPES 화이트리스트 상수가 있다")
i0 = APP_SRC.index("def api_partner_update(pid):")
i1 = APP_SRC.index("\n@app.", i0 + 1)
body = APP_SRC[i0:i1]
chk('if f == "partner_type" and d[f] not in PARTNER_TYPES:' in body,
    "★★★ api_partner_update 가 partner_type 을 화이트리스트로 막는다")

# ============================================================
print("\n[2] 실행 — 관리자 API로 잘못된 구분값을 직접 밀어넣는 시나리오")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round174_")
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
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,login_id,created_at) "
        "VALUES('R174업체','시행사','활성','가드레일','서울','r174p',?)", (DB.now(),)).lastrowid
    conn.commit(); conn.close()

    admin = A.app.test_client()
    atok = "r174-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_name"] = "검증"; sess["_csrf"] = atok
    ahdr = {"X-CSRF-Token": atok}

    # 잘못된 값 — 거부돼야 한다
    r1 = admin.patch(f"/api/partners/{pid}", json={"partner_type": "이상한값"}, headers=ahdr)
    j1 = r1.get_json() or {}
    chk(r1.status_code == 400 and j1.get("ok") is False,
        "★★★ 알 수 없는 구분값은 400 으로 거부된다(고치기 전엔 그대로 기록됐다)",
        (r1.status_code, j1))

    conn = DB.get_db()
    row = conn.execute("SELECT partner_type FROM partners WHERE id=?", (pid,)).fetchone()
    chk(row["partner_type"] == "시행사",
        "★★★ 거부된 요청은 기존 값을 훼손하지 않는다"
        "(고치기 전엔 '이상한값'으로 그대로 덮어써졌다)", row["partner_type"])
    conn.close()

    # 정상 값 — 여전히 통과해야 한다(과도차단 아님)
    r2 = admin.patch(f"/api/partners/{pid}", json={"partner_type": "시공사"}, headers=ahdr)
    j2 = r2.get_json() or {}
    chk(r2.status_code == 200 and j2.get("ok") is True,
        "정상 구분값(시공사)은 그대로 통과한다(과도차단 아님)", (r2.status_code, j2))

    conn = DB.get_db()
    row2 = conn.execute("SELECT partner_type FROM partners WHERE id=?", (pid,)).fetchone()
    chk(row2["partner_type"] == "시공사", "정상 값은 실제로 반영됨", row2["partner_type"])
    conn.close()

    # 입찰 자격 관문이 이제 정확한 값 기준으로 동작하는지 — 회귀 확인
    bidder = A.app.test_client()
    btok = "r174-partner-csrf"
    with bidder.session_transaction() as sess:
        sess["partner_id"] = pid; sess["partner_name"] = "R174업체"; sess["_csrf"] = btok
    r3 = bidder.get("/api/partner/dispatches", headers={"X-CSRF-Token": btok})
    chk(r3.status_code == 200,
        "★ 값 검증 추가가 무관한 협력사 API 를 막지 않는다(회귀 없음)", r3.status_code)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드174 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
