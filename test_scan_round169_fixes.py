# -*- coding: utf-8 -*-
"""스캔 169라운드 회귀 — 협력사/보험사 직접등록·정보수정이 자유텍스트 필드에
서버측 길이 제한을 전혀 안 걸던 결함.

  같은 컬럼을 다루는 형제 경로(자기수정 프로필: [:120]/[:80], 공개폼:
  FIELD_LIMITS)는 전부 길이를 자르는데, 관리자 콘솔의 직접등록·정보수정
  4곳(협력사 POST/PATCH, 보험사 POST/PATCH)만 라운드79·80 에서 형식 검사
  (사업자번호·이메일)는 받았으면서 길이는 그때도 지금도 안 봤다. 실측으로
  확인한 대로, **최하위 등급(하위관리자) 계정도** region 등에 수십만자를
  그대로 저장할 수 있었다 — 여러 화면·엑셀 내보내기가 동시에 깨질 수 있는
  데이터 무결성 문제였다.

      python test_scan_round169_fixes.py
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
print("  스캔 169라운드 회귀 — 관리자 직접등록·정보수정의 길이 제한 누락(4곳)")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
for fn, marker in (
    ("def api_partner_create(", '_s(d.get("name"), FIELD_LIMITS["name"])'),
    ("def api_partner_update(", "FIELD_LIMITS.get(f, 200)"),
    ("def api_insurer_create(", '_s(d.get("manager"), 80)'),
    ("def api_insurer_update(", "_R169_LIMITS"),
):
    i0 = APP_SRC.index(fn)
    i1 = APP_SRC.index("\n@app.", i0 + 1)
    body = APP_SRC[i0:i1]
    chk(marker in body, f"★★★ {fn.split('(')[0][4:]} 이 길이 제한을 적용한다")

# ============================================================
print("\n[2] 실행 — 하위관리자 계정도, 오버사이즈 입력이 실제로 잘려 저장되는가")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round169_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    HUGE = "가" * 200000

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r169low','x','검증','하위관리자')")
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r169top','x','검증','최고관리자')")
    conn.commit(); conn.close()

    def _admin_client(username, role):
        c = A.app.test_client()
        tok = f"r169-{username}-csrf"
        with c.session_transaction() as sess:
            sess["admin"] = username; sess["admin_role"] = role; sess["admin_name"] = "검증"
            sess["_csrf"] = tok
        return c, {"X-CSRF-Token": tok}

    low, hdr_low = _admin_client("r169low", "하위관리자")
    top, hdr_top = _admin_client("r169top", "최고관리자")

    #  ── ① 협력사 직접등록(POST /api/partners) — 최하위 등급으로도 접근된다 ──
    r1 = low.post("/api/partners", json={"name": "R169업체", "region": HUGE}, headers=hdr_low)
    chk(r1.status_code == 200 and r1.get_json().get("ok"),
        "STEP 하위관리자도 업체 직접등록에 접근된다(등급검사 없음, 결함 아님)", r1.get_json())
    pid = r1.get_json()["id"]
    conn = DB.get_db()
    row1 = dict(conn.execute("SELECT region FROM partners WHERE id=?", (pid,)).fetchone())
    conn.close()
    chk(len(row1["region"]) == 100,
        f"★★★ region 이 FIELD_LIMITS 상한(100자)으로 잘려 저장된다"
        f"(고치기 전엔 20만자 그대로 저장됐다) 실제길이={len(row1['region'])}", row1["region"][:30])

    #  ── ② 협력사 정보수정(PATCH /api/partners/<id>) ──
    r2 = low.patch(f"/api/partners/{pid}", json={"name": HUGE, "category": HUGE, "address": HUGE},
                    headers=hdr_low)
    chk(r2.status_code == 200, "STEP 정보수정 요청이 200 이다", r2.status_code)
    conn = DB.get_db()
    row2 = dict(conn.execute("SELECT name, category, address FROM partners WHERE id=?", (pid,)).fetchone())
    conn.close()
    chk(len(row2["name"]) == 40 and len(row2["category"]) == 200 and len(row2["address"]) == 200,
        "★★★ name/category/address 각각 FIELD_LIMITS 상한으로 잘린다"
        f" 실제길이=({len(row2['name'])},{len(row2['category'])},{len(row2['address'])})", row2)

    #  ── ③ 보험사 등록(POST /api/insurers) — 최고관리자 전용 ──
    r3 = top.post("/api/insurers", json={"name": "R169보험사", "manager": HUGE}, headers=hdr_top)
    chk(r3.status_code == 200 and r3.get_json().get("ok"), "STEP 보험사 등록이 200/ok 다", r3.get_json())
    iid = r3.get_json()["id"]
    conn = DB.get_db()
    row3 = dict(conn.execute("SELECT manager FROM insurers WHERE id=?", (iid,)).fetchone())
    conn.close()
    chk(len(row3["manager"]) == 80,
        f"★★★ 보험사 manager 도 자기수정과 같은 80자로 잘린다"
        f"(고치기 전엔 20만자 그대로) 실제길이={len(row3['manager'])}", row3["manager"][:20])

    #  ── ④ 보험사 정보수정(PATCH /api/insurers/<id>) ──
    r4 = top.patch(f"/api/insurers/{iid}", json={"dept": HUGE}, headers=hdr_top)
    chk(r4.status_code == 200, "STEP 보험사 정보수정이 200 이다", r4.status_code)
    conn = DB.get_db()
    row4 = dict(conn.execute("SELECT dept FROM insurers WHERE id=?", (iid,)).fetchone())
    conn.close()
    chk(len(row4["dept"]) == 80,
        f"★★★ 보험사 dept 도 80자로 잘린다 실제길이={len(row4['dept'])}", row4["dept"][:20])

    #  대조군 — 정상 길이 값은 그대로 온전히 저장된다(과잉절단 아님)
    r5 = low.patch(f"/api/partners/{pid}", json={"phone": "010-1234-5678"}, headers=hdr_low)
    conn = DB.get_db()
    row5 = dict(conn.execute("SELECT phone FROM partners WHERE id=?", (pid,)).fetchone())
    conn.close()
    chk(row5["phone"] == "010-1234-5678",
        "★ 정상 길이 값은 그대로 온전히 저장된다(과잉절단 아님)", row5)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드169 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
