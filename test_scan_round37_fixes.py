# -*- coding: utf-8 -*-
"""스캔 37라운드 회귀 — 2단계 인증(OTP) 코드 무차별 대입 계정 잠금.

  조사 에이전트가 찾은 결함: `/api/login/otp` 는 대기 세션당 5회 시도 상한이
  있었지만(OTP_MAX_TRIES), 비밀번호를 다시 맞히기만 하면 그 상한이 **무한
  리필**됐다 — 이미 비밀번호를 아는 공격자(피싱·유출·재사용)에게는 사실상
  무제한 코드 추측 창구였다. 유일한 방어는 `/api/login/otp` 자체의 IP 레이트
  리밋(20회/600초)뿐이었는데, 이건 시간이 지나면 그냥 다시 채워진다.

  고침: 비밀번호 로그인이 이미 갖고 있던 계정 잠금 장치
  (`login_attempts` + `_recent_fails`/`_log_attempt` + MAX_LOGIN_FAILS·
  LOCKOUT_MINUTES) 를 **그대로 재사용**해, OTP 실패도 같은 표에
  "OTP:"+아이디 로 쌓는다. 대기 세션을 새로 발급하기 전에 그 계정의 최근
  실패 수를 먼저 확인 — 5회 쌓이면 비밀번호가 맞아도 대기 세션 자체를 안 준다.

      python test_scan_round37_fixes.py
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

print("═" * 72)
print("  스캔 37라운드 회귀 — OTP 코드 무차별 대입 계정 잠금")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 배선이 실제로 있는가")
# ──────────────────────────────────────────────────────────────
chk('otp_fails = _recent_fails(conn, "OTP:" + u["username"])' in APP_SRC,
    "★ /api/login 이 대기 세션 발급 전에 OTP 실패 이력을 먼저 본다")
chk("if otp_fails >= MAX_LOGIN_FAILS:" in APP_SRC,
    "★★ 비밀번호 로그인과 같은 문턱(MAX_LOGIN_FAILS)을 쓴다")
chk(APP_SRC.count('_log_attempt(conn, "OTP:" + u["username"], True)') == 2,
    "★ TOTP·복구코드 두 성공 경로 모두 성공을 기록한다")
chk('_log_attempt(conn, "OTP:" + u["username"], False)' in APP_SRC,
    "★★ 틀린 코드가 login_attempts 에 실패로 남는다(재사용 코드 안내와는 별개)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제로 5회 틀리면, 비밀번호가 맞아도 잠기는가")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="otplock_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_OTP_POLICY"] = "always"     # 내부망이어도 코드 요구 — IP 판정에 안 흔들리게
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    import totp as TOTP
    DB.init_db()
    conn = DB.get_db()

    PW = "RoundThirtySeven!2026"
    secret1 = TOTP.new_secret()
    conn.execute(
        "INSERT INTO admins(username,password_hash,name,role,totp_enabled,totp_secret) "
        "VALUES('otplock_a',?,'검증A','중간관리자',1,?)", (DB.hash_pw(PW), secret1))
    secret2 = TOTP.new_secret()
    conn.execute(
        "INSERT INTO admins(username,password_hash,name,role,totp_enabled,totp_secret) "
        "VALUES('otplock_b',?,'검증B','중간관리자',1,?)", (DB.hash_pw(PW), secret2))
    conn.commit()
    conn.close()

    import app as A
    client = A.app.test_client()

    # ── A 계정 — 5회 틀림 → 잠기는지 ──────────────────────────
    r = client.post("/api/login", json={"username": "otplock_a", "password": PW})
    d = r.get_json()
    chk(r.status_code == 200 and d.get("need_otp") is True,
        "★ 첫 로그인은 정상적으로 대기 세션을 받는다(과잉차단 아님)", d)

    for i in range(5):
        r = client.post("/api/login/otp", json={"code": "000000"})
        chk(r.status_code == 401, f"틀린 코드 {i+1}/5 회는 그대로 거부", r.status_code)

    r = client.post("/api/login", json={"username": "otplock_a", "password": PW})
    d = r.get_json()
    chk(r.status_code == 429,
        "★★★ 5회 누적 뒤엔 비밀번호가 맞아도 429 — 대기 세션을 다시 안 준다", (r.status_code, d))
    chk(d.get("need_otp") is not True,
        "★★ 잠긴 응답은 need_otp 를 켜지 않는다(진짜 새 세션이 안 만들어짐)", d)

    # ── B 계정 — 3회만 틀림(문턱 미만) → 여전히 정상 발급되는가 ──
    r = client.post("/api/login", json={"username": "otplock_b", "password": PW})
    chk(r.get_json().get("need_otp") is True, "B계정 첫 로그인 정상")
    for i in range(3):
        r = client.post("/api/login/otp", json={"code": "000000"})
        chk(r.status_code == 401, f"B계정 틀린 코드 {i+1}/3 회 거부", r.status_code)
    r = client.post("/api/login", json={"username": "otplock_b", "password": PW})
    d = r.get_json()
    chk(r.status_code == 200 and d.get("need_otp") is True,
        "★★ 문턱(5회) 밑이면 여전히 정상 발급 — 과잉차단 아님", (r.status_code, d))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ OTP 잠금 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_OTP_POLICY", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
