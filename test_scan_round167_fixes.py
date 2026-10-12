# -*- coding: utf-8 -*-
"""스캔 167라운드 회귀 — 관리자 로그인(/api/login)이 아이디 대소문자를
정규화하지 않아, 정상 비밀번호를 넣어도 대소문자만 다르면 실패하던 결함.

  admins.username 은 계정 생성(api_admin_create) 시점부터 정규식
  [a-z0-9_-]{4,20} 로 소문자만 강제 저장되고, admins 표는 COLLATE NOCASE
  가 없어(db.py) SQL '=' 비교가 대소문자를 구분한다. 그런데 로그인 입력값만
  .lower() 를 안 거쳐, 저장값과 대소문자 하나만 달라도 "아이디 또는
  비밀번호가 올바르지 않습니다"로 실패했다. 형제인 협력사·보험사 로그인은
  진작에 "저장은 소문자 강제, 로그인도 맞춰야 한다"는 원칙을 명시하고
  이미 적용해 뒀는데, 정작 가장 먼저 나오는 관리자 로그인만 빠져 있었다.

  실패는 login_attempts 에 그대로 적립돼 MAX_LOGIN_FAILS 에 도달하면
  LOCKOUT_MINUTES 분 잠긴다 — 정직한 재시도(모바일 자동 대문자화 등)만으로
  자기 계정을 잠그는 자가-DoS 로 이어질 수 있었다.

      python test_scan_round167_fixes.py
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
print("  스캔 167라운드 회귀 — 관리자 로그인 아이디 대소문자 정규화 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_login():")
i1 = APP_SRC.index("\n@app.", i0 + 1)
body = APP_SRC[i0:i1]
#  ⚠ [라운드605] round601~604 형제결함군(raw (d.get(...) or "").strip() 이
#    비문자열 입력에 500을 내던 결함) 수정으로 이 줄의 정제 방식이 raw
#    strip()에서 _s() 헬퍼 호출로 바뀌었다 — .strip().lower()[:60] 이라는
#    "겉모습"은 사라졌지만 이 테스트가 실제로 보장하려는 것(로그인 아이디
#    소문자 정규화)은 아래 [2]의 실행 기반 검사 6개가 이미 증명하듯 전혀
#    안 바뀌었다. 검증취지를 보존하며 새 소스 형태로 갱신(약화·삭제 아님).
chk('username = _s(d.get("username")).lower()[:60]' in body,
    "★★★ api_login 이 협력사·보험사 로그인과 같은 방식으로 아이디를 소문자화한다"
    "(round605부터는 _s() 헬퍼를 거침 — 형태만 바뀌고 정규화 자체는 유지)")

# ============================================================
print("\n[2] 실행 — 대소문자가 달라도 정상 비밀번호면 로그인되는가")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round167_")
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
    #  api_admin_create 와 같은 방식(소문자 강제 저장)으로 실제 계정을 만든다
    conn.execute(
        "INSERT INTO admins(username,password_hash,name,role) "
        "VALUES('r167admin', ?, 'R167검증', '최고관리자')",
        (DB.hash_pw("Correct-Pass-1234"),))
    conn.commit(); conn.close()

    def _try_login(username, password):
        c = A.app.test_client()
        r = c.post("/api/login", json={"username": username, "password": password})
        return r.status_code, r.get_json()

    #  ① 정확히 저장된 그대로 — 원래도 되던 대조군
    rc0, j0 = _try_login("r167admin", "Correct-Pass-1234")
    chk(rc0 == 200 and j0.get("ok"), "★ (사전조건) 정확한 대소문자 로그인은 원래도 된다", (rc0, j0))

    #  ★★★ ② 대문자로 친 아이디 — 이번 결함의 핵심(비번은 정확한데 실패했었다)
    rc1, j1 = _try_login("R167ADMIN", "Correct-Pass-1234")
    chk(rc1 == 200 and j1.get("ok"),
        "★★★ 아이디를 대문자로 쳐도 정상 비밀번호면 로그인된다"
        "(고치기 전엔 '아이디 또는 비밀번호가 올바르지 않습니다'로 실패했다)", (rc1, j1))

    #  ③ 대소문자 섞어 친 경우
    rc2, j2 = _try_login("R167Admin", "Correct-Pass-1234")
    chk(rc2 == 200 and j2.get("ok"), "★★ 대소문자를 섞어 쳐도 로그인된다", (rc2, j2))

    #  ④ 앞뒤 공백 — strip 은 원래도 됐다(회귀 없음 확인)
    rc3, j3 = _try_login("  r167admin  ", "Correct-Pass-1234")
    chk(rc3 == 200 and j3.get("ok"), "★ 앞뒤 공백은 원래도 잘리고 로그인된다(회귀 없음)", (rc3, j3))

    #  ⑤ 대조군 — 아이디는 맞아도(대문자) 비밀번호가 틀리면 여전히 실패해야 한다
    rc4, j4 = _try_login("R167ADMIN", "wrong-password")
    chk(rc4 == 401 and not j4.get("ok"),
        "★ 아이디만 맞고 비밀번호가 틀리면 대소문자와 무관하게 여전히 실패한다"
        "(과잉허용 아님)", (rc4, j4))

    #  ⑥ 대조군 — 아예 없는 아이디는 여전히 실패해야 한다
    rc5, j5 = _try_login("NOSUCHADMIN", "Correct-Pass-1234")
    chk(rc5 == 401 and not j5.get("ok"),
        "★ 존재하지 않는 아이디는 대소문자와 무관하게 여전히 실패한다(과잉허용 아님)", (rc5, j5))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드167 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
