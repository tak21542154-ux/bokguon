# -*- coding: utf-8 -*-
"""스캔 176라운드 회귀 — manage.py create-admin 이 아이디를 소문자로 맞추지도,
형식을 검증하지도 않고 그대로 저장하던 결함.

  웹 경로(api_admin_create, app.py:1549)는 이미 strip+lower+정규식
  [a-z0-9_-]{4,20} 를 강제하고, 형제 CLI 명령(create-insurer)도 이미 소문자로
  맞추는데, 이 CLI 명령만 argv 를 그대로 저장했다. 로그인(app.py:2603)은
  입력을 항상 소문자로 맞춰 비교하므로, 대문자가 섞인 아이디로 이 명령을
  실행하면 **그 계정은 만들어진 순간부터 웹으로 영영 로그인할 수 없다**
  (비밀번호 오류처럼 보여 원인을 알 방법이 없다). 실측(운영DB): 현재 두
  admins 계정(admin·staff)은 전부 정상 형식이라 아직 피해는 없다.

      python test_scan_round176_fixes.py
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


SRC = read("manage.py")

print("=" * 72)
print("  스캔 176라운드 회귀 — create-admin 의 아이디 정규화·형식검증 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = SRC.index("def cmd_create_admin(")
i1 = SRC.index("\ndef ", i0 + 1)
body = SRC[i0:i1]
chk("username = argv[0].strip().lower()" in body,
    "★★★ cmd_create_admin 이 아이디를 소문자로 맞춘다(웹 경로와 동일 규칙)")
chk('re.fullmatch(r"[a-z0-9_-]{4,20}", username)' in body,
    "★★★ cmd_create_admin 이 웹 경로와 같은 형식(영문소문자·숫자·-·_ 4~20자)을 강제한다")

# ============================================================
print("\n[2] 실행 — 대문자 섞인 아이디로 만든 계정이 실제로 로그인되는가")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round176_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import manage as M
    import app as A

    # ① 형식위반(너무 짧음) — 계정이 아예 만들어지지 않아야 한다
    rc0 = M.cmd_create_admin(["ab", "--name", "짧은아이디"])
    chk(rc0 == 1, "★ 4자 미만 아이디는 거부되고 계정을 만들지 않는다", rc0)
    conn = DB.get_db()
    n0 = conn.execute("SELECT COUNT(*) FROM admins WHERE username='ab'").fetchone()[0]
    chk(n0 == 0, "거부된 요청은 실제로 행을 남기지 않는다", n0)
    conn.close()

    # ② 대문자 섞인 아이디 — 예전엔 그대로 'JohnDoe' 로 저장돼 웹 로그인이 영영 안 됐다
    rc1 = M.cmd_create_admin(["JohnDoe", "--name", "테스트관리자", "--role", "중간관리자"])
    chk(rc1 is None, "★ 대문자 섞인 아이디도 정규화되어 계정 생성은 성공한다", rc1)

    conn = DB.get_db()
    row = conn.execute("SELECT username, password_hash FROM admins "
                        "WHERE username IN ('johndoe','JohnDoe')").fetchone()
    chk(row is not None and row["username"] == "johndoe",
        "★★★ 저장된 아이디가 소문자로 정규화됨(고치기 전엔 'JohnDoe' 그대로 저장됐다)",
        dict(row) if row else None)

    # 알려진 비밀번호로 바꿔 두고, 실제 로그인 라우트로 대문자 섞어 입력해 본다
    known_hash = DB.hash_pw("R176테스트비번!")
    conn.execute("UPDATE admins SET password_hash=? WHERE username='johndoe'", (known_hash,))
    conn.commit(); conn.close()

    client = A.app.test_client()
    r = client.post("/api/login", json={"username": "JohnDoe", "password": "R176테스트비번!"})
    j = r.get_json() or {}
    chk(r.status_code == 200 and j.get("ok") is True,
        "★★★★ 대문자로 발급 요청했던 계정이 실제 로그인 라우트로 로그인된다"
        "(고치기 전엔 저장값 'JohnDoe' ≠ 로그인이 소문자로 맞춘 'johndoe' 라서 "
        "영원히 로그인 불가였다)", (r.status_code, j))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드176 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
