# -*- coding: utf-8 -*-
"""스캔 175라운드 회귀 — 로그인 잠금 수동해제(api_unlock_login)가 아이디를
소문자로 정규화하지 않아, 저장된 실패기록(전부 소문자)과 대소문자가 다르면
0건 지우고도 "잠겨 있지 않았다"는 거짓 확인을 주던 결함.

  저장 쪽 네 곳(관리자 로그인 2603행·협력사 2691행·보험사 2887행·OTP)은
  전부 .lower() 로 강제하는데, 유일하게 지우는 쪽인 이 라우트만 없었다.
  login_attempts.username 은 COLLATE NOCASE 도 없어 IN 비교가 대소문자를
  구분한다 — 실측(운영DB): 'staff' 144건·'P:partner' 22건이 지금 이 상태로
  쌓여 있고, 운영자가 대문자 섞어 치면(모바일 자동대문자화 등) 0건 삭제.

      python test_scan_round175_fixes.py
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
print("  스캔 175라운드 회귀 — 잠금 수동해제의 아이디 대소문자 정규화 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_unlock_login():")
i1 = APP_SRC.index("\n@app.", i0 + 1)
body = APP_SRC[i0:i1]
#  ⚠⚠ [라운드609] round601~608 형제결함군 — uname이 raw (d.get(...) or "").strip()
#    였다(숫자 등을 보내면 AttributeError로 500). _s() 로 바뀌며 리터럴도 바뀌었다 —
#    소문자 정규화(이 라운드의 검증 취지)는 그대로 유지된다.
chk('uname = _s(d.get("username")).lower()[:40]' in body,
    "★★★ api_unlock_login 이 아이디를 저장 쪽과 같은 규칙(소문자)으로 맞춘다")

# ============================================================
print("\n[2] 실행 — 저장은 소문자인데 운영자가 대소문자 섞어 해제 요청")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round175_")
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
    #  실사용 그대로: 운영자는 창구를 모르고 아이디 한 칸만 입력하므로(2317행
    #  주석), 같은 아이디가 네 창구 전부에 실패기록을 남긴 상황을 재현한다.
    for uname in ("r175id", "P:r175id", "I:r175id", "OTP:r175id"):
        conn.execute(
            "INSERT INTO login_attempts(username,ip,success,created_at) VALUES(?,?,0,?)",
            (uname, "127.0.0.1", DB.now()))
    conn.commit(); conn.close()

    admin = A.app.test_client()
    atok = "r175-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = atok
    ahdr = {"X-CSRF-Token": atok}

    # 운영자가 대문자 섞어 입력(모바일 자동대문자화 재현) — 그래도 전부 지워져야 한다
    r = admin.post("/api/login-attempts/unlock", json={"username": "R175Id"}, headers=ahdr)
    j = r.get_json() or {}
    chk(r.status_code == 200 and j.get("ok") is True and j.get("cleared", 0) >= 4,
        "★★★ 대문자 섞어 입력해도 소문자로 저장된 실패기록 4건이 전부 지워진다"
        "(고치기 전엔 0건 — 거짓 '잠겨 있지 않았다' 확인이 나갔다)", j)

    conn = DB.get_db()
    left = conn.execute(
        "SELECT COUNT(*) FROM login_attempts WHERE success=0 AND username IN "
        "('r175id','P:r175id','I:r175id','OTP:r175id')").fetchone()[0]
    chk(left == 0, "★★★ 네 창구(본인·협력사·보험사·OTP) 실패기록이 실제로 다 지워짐",
        f"남은 {left}건")
    conn.close()

    # 정상(이미 소문자) 입력도 여전히 통과해야 한다 — 과도필터 아님
    conn = DB.get_db()
    conn.execute(
        "INSERT INTO login_attempts(username,ip,success,created_at) VALUES(?,?,0,?)",
        ("r175again", "127.0.0.1", DB.now()))
    conn.commit(); conn.close()
    r2 = admin.post("/api/login-attempts/unlock", json={"username": "r175again"}, headers=ahdr)
    j2 = r2.get_json() or {}
    chk(r2.status_code == 200 and j2.get("cleared", 0) >= 1,
        "소문자 그대로 입력해도 여전히 정상 동작(회귀 없음)", j2)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드175 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
