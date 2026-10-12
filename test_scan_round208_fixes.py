# -*- coding: utf-8 -*-
"""스캔 208라운드 회귀 — 협력사·보험사 로그인의 실패·잠금이 감사로그
(activity_log)에 전혀 안 남던 결함.

  형제(api_login, 관리자)는 잠금·실패·성공 세 분기 모두 DB.log() 를 남기는데,
  api_partner_login·api_insurer_login 은 **성공했을 때만** 남겼다. 유일한
  흔적인 login_attempts 테이블은 잠금 판정용 내부 카운터일 뿐 보여 주는
  화면이 없고(전수 확인: INSERT·COUNT·DELETE 세 곳뿐, 나열 API 없음), 그나마도
  운영자가 수동 잠금해제를 누르면 지워진다. 외부 조직 계정(협력사·보험사,
  가장 넓은 공격면)이 관리자보다 노출은 큰데 정작 침입 시도 흔적이
  activity_log 에 하나도 안 남는 상태였다.

  관리자와 같은 자리에 DB.log() 를 채워 잠금·실패도 감사로그에 남게 했다.

      python test_scan_round208_fixes.py
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
print("  스캔 208라운드 회귀 — 협력사·보험사 로그인 실패·잠금이 감사로그에 안 남던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_partner_login():")
i1 = APP_SRC.index("\n@app.post(\"/api/logout\")")
partner_body = APP_SRC[i0:i1]
chk('DB.log(conn, login_id or "-", "협력사 로그인 차단(잠금)", client_ip())' in partner_body,
    "★★★★ api_partner_login 잠금 분기가 DB.log() 를 남긴다")
chk('DB.log(conn, login_id or "-", "협력사 로그인 실패", client_ip())' in partner_body,
    "★★★★ api_partner_login 실패 분기가 DB.log() 를 남긴다")

i2 = APP_SRC.index("def api_insurer_login():")
i3 = APP_SRC.index("\n@app.post(\"/api/insurer/logout\")")
insurer_body = APP_SRC[i2:i3]
chk('DB.log(conn, login_id or "-", "보험사 로그인 차단(잠금)", client_ip())' in insurer_body,
    "★★★★ api_insurer_login 잠금 분기가 DB.log() 를 남긴다")
chk('DB.log(conn, login_id or "-", "보험사 로그인 실패", client_ip())' in insurer_body,
    "★★★★ api_insurer_login 실패 분기가 DB.log() 를 남긴다")

# ============================================================
print("\n[2] 실행 — 실제 서버(Flask test_client)로 잠금까지 재현해 감사로그 확인")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round208_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
os.environ.pop("BOKGUON_MAX_LOGIN_FAILS", None)
os.environ.pop("BOKGUON_LOCKOUT_MIN", None)
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    chk(A.MAX_LOGIN_FAILS == 5, "★ (사전조건) 기본 잠금 임계치는 5회", A.MAX_LOGIN_FAILS)

    conn = DB.get_db()
    good_pw = DB.hash_pw("R208realPw!1")

    def mk_partner(login_id):
        return conn.execute(
            "INSERT INTO partners(name,login_id,password_hash,status,created_at) "
            "VALUES(?,?,?,'활성',?)", (f"R208업체-{login_id}", login_id, good_pw, DB.now())).lastrowid

    def mk_insurer(login_id):
        return conn.execute(
            "INSERT INTO insurers(name,login_id,password_hash,status,created_at) "
            "VALUES(?,?,?,'활성',?)", (f"R208보험-{login_id}", login_id, good_pw, DB.now())).lastrowid

    def n_log(action, actor):
        #  DB.log(conn, login_id or "-", action, client_ip()) — 아이디는 actor 칸에
        #  들어간다(detail 엔 IP 만 들어간다).
        return conn.execute(
            "SELECT COUNT(*) n FROM activity_log WHERE action=? AND actor=?",
            (action, actor)).fetchone()["n"]

    mk_partner("r208pa"); mk_insurer("r208ia")
    conn.commit()

    client = A.app.test_client()

    # ── A. 한 번 실패해도(잠금 미도달) '실패' 로그가 남고, 정상 로그인은 그대로 된다 ──
    r_fail = client.post("/api/partner/login", json={"login_id": "r208pa", "password": "틀림"})
    chk(r_fail.status_code == 401, "STEP 협력사 오답 1회는 401", r_fail.status_code)
    chk(n_log("협력사 로그인 실패", "r208pa") == 1,
        "★★★★★ 핵심 — 협력사 로그인 실패가 activity_log 에 남는다"
        "(고치기 전엔 0건이었다)", n_log("협력사 로그인 실패", "r208pa"))

    r_ok = client.post("/api/partner/login", json={"login_id": "r208pa", "password": "R208realPw!1"})
    chk(r_ok.status_code == 200 and r_ok.get_json().get("ok"),
        "★ 실패 1회 뒤에도 정상 비밀번호면 그대로 로그인된다(과잉차단 아님)", r_ok.status_code)
    #  성공 로그의 actor 는 login_id 가 아니라 auth["name"](표시이름)이다 —
    #  실패·잠금과 다른 이미 있던(회귀 아닌) 설계라 이름으로 확인한다.
    chk(n_log("협력사 로그인", "R208업체-r208pa") >= 1,
        "★ 성공 로그는 여전히(회귀 아님) 남는다", n_log("협력사 로그인", "R208업체-r208pa"))

    # ── B. 5회 연속 오답 → 6번째는 잠금(429) → '차단(잠금)' 로그가 남는다 ──
    for _ in range(A.MAX_LOGIN_FAILS):
        client.post("/api/partner/login", json={"login_id": "r208pb-missing", "password": "틀림"})
    # 존재하지 않는 아이디로도 _log_attempt 는 login_id 문자열 기준으로 카운트된다
    r_lock = client.post("/api/partner/login",
                          json={"login_id": "r208pb-missing", "password": "틀림"})
    chk(r_lock.status_code == 429,
        "STEP 5회 실패 뒤 6번째 시도는 429(잠금)", r_lock.status_code)
    chk(n_log("협력사 로그인 차단(잠금)", "r208pb-missing") == 1,
        "★★★★★ 핵심 — 협력사 로그인 잠금도 activity_log 에 남는다"
        "(고치기 전엔 0건이었다 — 브루트포스 흔적이 전혀 안 남던 그 결함)",
        n_log("협력사 로그인 차단(잠금)", "r208pb-missing"))

    # ── C. 보험사도 동일 — 실패·잠금 둘 다 ──
    r_ifail = client.post("/api/insurer/login", json={"login_id": "r208ia", "password": "틀림"})
    chk(r_ifail.status_code == 401, "STEP 보험사 오답 1회는 401")
    chk(n_log("보험사 로그인 실패", "r208ia") == 1,
        "★★★★ 보험사 로그인 실패도 activity_log 에 남는다", n_log("보험사 로그인 실패", "r208ia"))

    for _ in range(A.MAX_LOGIN_FAILS):
        client.post("/api/insurer/login", json={"login_id": "r208ib-missing", "password": "틀림"})
    r_ilock = client.post("/api/insurer/login",
                           json={"login_id": "r208ib-missing", "password": "틀림"})
    chk(r_ilock.status_code == 429, "STEP 보험사도 5회 뒤 6번째는 429(잠금)")
    chk(n_log("보험사 로그인 차단(잠금)", "r208ib-missing") == 1,
        "★★★★ 보험사 로그인 잠금도 activity_log 에 남는다",
        n_log("보험사 로그인 차단(잠금)", "r208ib-missing"))

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드208 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
