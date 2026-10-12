# -*- coding: utf-8 -*-
"""스캔 194라운드 회귀 — 두 결함.

  ① app.py api_settlement_undo(): 정산 단계를 되돌리면서(지급 검수 승인 취소)
    형제(api_settlement_void)와 달리 아무에게도 알리지 않았다. 협력사는 방금
    받은 "…원 지급 검수가 끝났습니다. 입금됩니다"(13039행) 알림이 알림함에
    그대로 남는데, 실제로는 지급이 보류된 것을 알 방법이 없었다. _NTYPE_VIEW
    에 정의만 되고 한 번도 안 쓰이던 "정산정정"을 채운다.

  ② manage.py _WEND(하자보증 만료일, 말일보정 완료)에 '+3 years'를 그대로
    씌운 개인정보 파기 기준일이 윤년 2월29일 만료 건에서 하루 늦게 잡히던
    결함(SQLite date('2028-02-29','+3 years')='2031-03-01', 실측 확인).

      python test_scan_round194_fixes.py
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
MANAGE_SRC = read("manage.py")

print("=" * 72)
print("  스캔 194라운드 회귀 — 정산 되돌리기 무통지 · 하자파기 윤년 하루지연")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_settlement_undo(sid):")
i1 = APP_SRC.index("\ndef ", i0 + 1)
body = APP_SRC[i0:i1]
chk('notify(conn, "정산정정"' in body,
    "★★★★ 정산 되돌리기가 '정산정정' 알림을 보낸다"
    "(고치기 전엔 이 함수 전체에서 notify() 호출이 0건이었다)")
chk("audience_type=\"partner\"" in body,
    "★★★★ 지급 검수 승인을 되돌리면 협력사에게도 통지한다")

_i_dwhere = MANAGE_SRC.index("_dwhere = (")
_dwhere_def = MANAGE_SRC[_i_dwhere:MANAGE_SRC.index(")\n", _i_dwhere)]
chk("_DEFECT_PURGE_AT" in _dwhere_def and "+3 years" not in _dwhere_def,
    "★★★ 하자기록 파기 기준일 산식이 별도 상수(_DEFECT_PURGE_AT)를 쓴다"
    "(고치기 전엔 이 자리에서 직접 datetime(_WEND, '+3 years')를 썼다)")
i2 = MANAGE_SRC.index("_DEFECT_PURGE_AT = (")
i3 = MANAGE_SRC.index(")\n", i2)
purge_def = MANAGE_SRC[i2:i3]
chk("start of month" in purge_def,
    "★★★★ _DEFECT_PURGE_AT 가 _WEND 와 같은 말일보정(start of month, -1 day)을 "
    "'+3 years' 뒤에도 적용한다(고치기 전엔 SQLite +3 years 를 그대로 썼다)")

# ============================================================
print("\n[2] 실행 — ① 지급검수 승인을 되돌리면 협력사·운영팀 양쪽에 알림이 "
      "생긴다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round194_")
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
    now = DB.now()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r194admin','x','검증','중간관리자')")
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R194업체','시공사','활성')"
    ).lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,is_demo) "
        "VALUES('R194-001','정산진행','유리','서울',?,0)", (pid,)).lastrowid
    sid = conn.execute(
        "INSERT INTO settlements(case_id,case_no,partner_id,partner_name,amount,fee,"
        "                        payout,review_status,transfer_status,insurer_paid,created_at) "
        "VALUES(?,?,?,?,5000000,500000,4500000,'승인','대기','대기',?)",
        (cid, "R194-001", pid, "R194업체", now)).lastrowid
    conn.commit()

    n_before = conn.execute("SELECT COUNT(*) n FROM notifications").fetchone()["n"]

    admin = A.app.test_client()
    atok = "r194-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r194admin"; sess["admin_role"] = "중간관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = atok
    ahdr = {"X-CSRF-Token": atok}

    resp = admin.post(f"/api/settlements/{sid}/undo",
                       json={"reason": "계좌 확인 오류로 되돌립니다"}, headers=ahdr)
    j = resp.get_json() or {}

    n_partner = conn.execute(
        "SELECT COUNT(*) n FROM notifications "
        " WHERE ntype='정산정정' AND audience_type='partner' AND partner_id=?", (pid,)
    ).fetchone()["n"]
    n_admin = conn.execute(
        "SELECT COUNT(*) n FROM notifications "
        " WHERE ntype='정산정정' AND audience_type='admin'").fetchone()["n"]
    s_after = conn.execute("SELECT review_status, transfer_status FROM settlements WHERE id=?",
                            (sid,)).fetchone()

    chk(resp.status_code == 200 and j.get("ok") is True and j.get("undone") == "지급 검수 승인",
        "정산 되돌리기 자체는 정상 성공한다(회귀 없음)", (resp.status_code, j))
    chk(s_after["review_status"] == "대기" and s_after["transfer_status"] == "대기",
        "review_status·transfer_status 모두 '대기'로 되돌아간다", dict(s_after))
    chk(n_partner >= 1,
        "★★★★ 협력사 앞으로 '정산정정' 알림이 실제로 생긴다"
        "(고치기 전엔 0건 — 방금 받은 '입금됩니다' 알림만 알림함에 남아 있었다)",
        n_partner)
    chk(n_admin >= 1,
        "★★★ 운영팀 앞으로도 '정산정정' 알림이 생긴다", n_admin)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드194 [2] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — ② 윤년 2월29일 만료 건의 파기 기준일이 하루 당겨진다")
# ------------------------------------------------------------
try:
    import sqlite3
    import manage as M
    mem = sqlite3.connect(":memory:")
    mem.execute("CREATE TABLE cases(id INTEGER PRIMARY KEY, completed_at TEXT, warranty_months INTEGER)")
    # completed_at=2027-08-31, warranty=6개월 → _WEND(말일보정) = 2028-02-29(윤년)
    mem.execute("INSERT INTO cases(id, completed_at, warranty_months) VALUES(1, '2027-08-31', 6)")
    # 대조군 — 윤년이 아닌 평범한 사건(회귀 없음 확인)
    mem.execute("INSERT INTO cases(id, completed_at, warranty_months) VALUES(2, '2026-08-31', 6)")

    wend1 = mem.execute(f"SELECT {M._WEND} FROM cases WHERE id=1").fetchone()[0]
    old1 = mem.execute(f"SELECT datetime({M._WEND}, '+3 years') FROM cases WHERE id=1").fetchone()[0]
    new1 = mem.execute(f"SELECT {M._DEFECT_PURGE_AT} FROM cases WHERE id=1").fetchone()[0]
    new2 = mem.execute(f"SELECT {M._DEFECT_PURGE_AT} FROM cases WHERE id=2").fetchone()[0]

    chk(wend1 == "2028-02-29", "준비: 이 사건의 하자보증 만료일은 윤년 2월29일이다", wend1)
    chk(old1 == "2031-03-01 00:00:00",
        "준비: 옛 계산(datetime(_WEND,'+3 years'))은 3월1일로 넘친다(SQLite 자체 결함)", old1)
    chk(new1 == "2031-02-28 00:00:00",
        "★★★★ 고친 파기 기준일은 2월28일로 정확히 보정된다"
        "(고치기 전엔 3월1일까지 하루 더 보관됐다)", new1)
    chk(new2 == "2030-02-28 00:00:00",
        "★★★ 평범한(윤년 아닌) 사건은 결과가 그대로다(회귀 없음)", new2)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드194 [3] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
