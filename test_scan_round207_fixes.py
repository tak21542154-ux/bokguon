# -*- coding: utf-8 -*-
"""스캔 207라운드 회귀 — 보험사 포털 계정 발급(api_insurer_credentials)의
예약어 목록이 실제 데모 계정명과 어긋나, go-live 가 지우는 이름을 실계정에
그대로 발급할 수 있던 결함.

  manage.py DEMO_ACCOUNTS 는 보험사 데모 계정명을 "insurer"·"insurer2"(풀네임
  +숫자, smoke_test.py:701 도 실제 2번째 보험사 테스트 계정으로 같은 이름을
  쓴다)로 정의하고, go-live(--yes)는 그 이름과 login_id 값이 같은 행을
  **데모 여부와 무관하게** UPDATE ... SET login_id=NULL, password_hash=NULL
  로 지운다(회사 정보는 남기고 로그인 수단만 삭제).

  그런데 계정 발급 API 의 예약어 차단 목록은 "insurer","i2","i3",... 였다 —
  형제(PARTNER_ID_RESERVED, "partner"·"p2"·"p3")의 패턴을 보험사에
  잘못 유추해 옮긴 것으로 보인다. "i2"·"i3"는 어디에도 실존하지 않는
  이름이라 막아 봐야 의미가 없고, 정작 위험한 "insurer2"는 목록에 없어
  실제 보험사에 그대로 발급할 수 있었다 — 그 상태로 go-live 를 돌리면
  그 실계정의 로그인 수단이 경고 없이 통째로 삭제된다.

  "insurer"·"insurer2"·"admin"·"staff"·"partner" 로 목록을 바로잡았다.

      python test_scan_round207_fixes.py
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
MNG_SRC = read("manage.py")

print("=" * 72)
print("  스캔 207라운드 회귀 — 보험사 계정발급 예약어와 go-live 삭제대상 불일치")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk('DEMO_ACCOUNTS = [("admins", "username", ["admin", "staff"]),' in MNG_SRC
    and '("insurers", "login_id", ["insurer", "insurer2"])]' in MNG_SRC,
    "★ (사전조건) go-live 가 실제로 지우는 보험사 데모 계정명은 insurer·insurer2 다")

i0 = APP_SRC.index("def api_insurer_credentials(iid):")
i1 = APP_SRC.index("\n@app.", i0 + 10)
cred_body = APP_SRC[i0:i1]
#  ⚠ '"i2"' 문자열 부재만으로는 못 잡는다 — 바로 위에 남긴 설명 주석 자체가
#    "여기 있던 i2·i3는…" 처럼 그 이름을 인용해 언급하기 때문이다. 실제
#    예약어 튜플 그 줄 하나로만 정확히 검사한다.
chk('if login_id in ("insurer", "insurer2", "admin", "staff", "partner"):' in cred_body,
    "★★★★ 예약어 목록이 go-live 삭제대상(insurer·insurer2)과 정확히 일치하게 고쳐졌다"
    "(실존하지 않던 i2·i3 대신)")

# ============================================================
print("\n[2] 실행 — 실제 서버(Flask test_client)로 발급 차단 확인")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round207_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A
    import manage as MNG

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r207admin','x','검증','최고관리자')")
    iid = conn.execute(
        "INSERT INTO insurers(name,status,org_type) VALUES('R207신규보험사','활성','손해보험사')").lastrowid
    conn.commit()

    admin_c = A.app.test_client()
    tok = "r207-admin-csrf"
    with admin_c.session_transaction() as sess:
        sess["admin"] = "r207admin"; sess["admin_role"] = "최고관리자"; sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    r_bad = admin_c.post(f"/api/insurers/{iid}/credentials",
                          json={"login_id": "insurer2"}, headers=hdr)
    j_bad = r_bad.get_json()
    chk(r_bad.status_code == 400 and "예약어" in (j_bad.get("error") or ""),
        "★★★★★ 핵심 — 실제 보험사에 'insurer2' 아이디 발급을 서버가 거절한다"
        "(고치기 전엔 200 으로 그대로 발급됐다 — go-live 가 지울 이름이 실계정에 붙음)",
        (r_bad.status_code, j_bad))
    row_bad = dict(conn.execute(
        "SELECT login_id FROM insurers WHERE id=?", (iid,)).fetchone())
    chk(row_bad["login_id"] is None,
        "★★★ 거절됐으니 실제로 login_id 가 저장되지 않았다", row_bad)

    r_ok = admin_c.post(f"/api/insurers/{iid}/credentials",
                         json={"login_id": "r207real1"}, headers=hdr)
    j_ok = r_ok.get_json()
    chk(r_ok.status_code == 200 and j_ok.get("ok"),
        "★ 예약어가 아닌 정상 아이디는 그대로 발급된다(과잉차단 아님)", (r_ok.status_code, j_ok))

    # ── 왜 이게 중요한지 — go-live 의 실제 삭제문으로 직접 확인 ──
    #    (이 자체는 위 수정을 검증하는 게 아니라, 막지 않았다면 실제로
    #    벌어졌을 결과를 재현해 문제의 실체를 보여 준다)
    iid2 = conn.execute(
        "INSERT INTO insurers(name,status,org_type,login_id,password_hash) "
        "VALUES('R207실제보험사(가정)','활성','손해보험사','insurer2','somehash')").lastrowid
    conn.commit()
    for table, col, names in MNG.DEMO_ACCOUNTS:
        if table != "insurers":
            continue
        for nm in names:
            conn.execute(f"UPDATE {table} SET login_id=NULL, password_hash=NULL WHERE {col}=?", (nm,))
    conn.commit()
    row2 = dict(conn.execute(
        "SELECT login_id, password_hash, name FROM insurers WHERE id=?", (iid2,)).fetchone())
    chk(row2["login_id"] is None and row2["password_hash"] is None,
        "★★★★★ (배경 확인) go-live 의 실제 삭제문은 예약어 검사와 무관하게 "
        "login_id='insurer2' 값만 보고 지운다 — 그래서 애초에 '발급 자체를 "
        "막는' 이번 수정이 유일한 방어선이다", row2)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드207 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
