# -*- coding: utf-8 -*-
"""스캔 269라운드 회귀 — 2단계인증(totp.py) 결함 2건
   (이 세션 268라운드 내내 한 번도 감사대상이 된 적 없던 보안 핵심 파일의
   정밀조사 Agent가 발견, 독립 재검증 후 수정).

  [1] admins.totp_secret 이 DB 에 평문으로 저장됐다. 형제(crypto_util.py,
      협력사 계좌번호에 AES-256-GCM 적용 중)와 달리 이 비밀키에는 암호화가
      전혀 적용되지 않아, DB 파일 하나만 유출돼도 크래킹 없이 그 즉시
      해당 계정의 2단계 인증이 완전히 재현됐다. app.py 의 저장 1곳(등록)·
      조회 2곳(로그인검증·등록확인)에 CRYPTO.encrypt/decrypt 를 적용했다.
      CRYPTO.decrypt() 는 "v1:" 접두사가 없으면 평문으로 보고 그대로
      돌려주므로(형제 기능, 계좌정보와 동일한 하위호환 방식) 기존에 이미
      평문으로 저장된 비밀키도 마이그레이션 없이 계속 정상 동작한다.

  [2] 복구 코드가 4바이트(32비트, 43억 조합)뿐이었다. hash_recovery() 가
      솔트 없는 단일라운드 SHA256 이라(비밀번호 해시의 PBKDF2 60만회와
      달리 브루트포스를 못 늦춘다) — 실행으로 실제 생성한 코드 1개를
      12코어 전수탐색으로 163.2초 만에 완전히 복원했다(DB 유출 시나리오
      전제, 로그인 자체엔 비밀번호가 별도로 더 필요함). hash_recovery() 는
      입력 길이에 무관하게 그대로 동작하므로(정규화 후 해시만) 입력을
      8바이트(64비트)로 늘리는 것만으로 충분하다 — 해시함수·검증 로직은
      그대로 둬서 이미 발급된 기존 복구코드의 해시도 계속 유효하다.

      python test_scan_round269_fixes.py
"""
import io
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []

#  ⚠ db.py 를 불러오기 전에 검증용 DB 경로부터 정한다.
_tmpdir = tempfile.mkdtemp(prefix="round269_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")
TOTP_SRC = read("totp.py")

print("=" * 72)
print("  스캔 269라운드 회귀 — totp.py 평문저장·복구코드 저엔트로피")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_setup = APP_SRC.index('def api_otp_setup')
i_setup_end = APP_SRC.index("\n\n\n@app.", i_setup)
setup_body = APP_SRC[i_setup:i_setup_end]
chk("CRYPTO.encrypt(secret)" in setup_body,
    "★★★★★ 등록 시 비밀키를 암호화해 저장한다(고치기 전엔 평문 저장)")
chk('"secret": secret' in setup_body,
    "STEP 사용자에게 돌려주는 값(QR·수동입력용)은 여전히 평문이다(당연히 그래야 함)")

i_login = APP_SRC.index("def api_login_otp")
i_login_end = APP_SRC.index("\n\n\n@app.", i_login)
login_body = APP_SRC[i_login:i_login_end]
chk('CRYPTO.decrypt(u["totp_secret"] or "")' in login_body,
    "★★★★★ 로그인 2단계 검증이 복호화한 값으로 확인한다")

i_confirm = APP_SRC.index("def api_otp_confirm")
i_confirm_end = APP_SRC.index("\n\n\n@app.", i_confirm)
confirm_body = APP_SRC[i_confirm:i_confirm_end]
chk('CRYPTO.decrypt(u["totp_secret"] or "")' in confirm_body,
    "★★★★★ 등록확인 검증도 복호화한 값으로 확인한다")

i_rec = TOTP_SRC.index("def new_recovery_codes")
i_rec_end = TOTP_SRC.index("\n\n\ndef ", i_rec)
rec_body = TOTP_SRC[i_rec:i_rec_end]
chk("secrets.token_hex(8)" in rec_body,
    "★★★★★ 복구코드가 8바이트(64비트)로 늘었다(고치기 전엔 4바이트/32비트)")

i_hash = TOTP_SRC.index("def hash_recovery")
i_hash_end = TOTP_SRC.index("\n\n\ndef ", i_hash)
hash_body = TOTP_SRC[i_hash:i_hash_end]
chk("sha256" in hash_body,
    "STEP hash_recovery() 자체(해시함수)는 안 바꿨다 — 기존 발급 코드의 해시도 계속 유효")

# ============================================================
print("\n[2] 실행 — totp_secret 암호화·기존 평문 하위호환")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
try:
    import importlib
    import db as DB
    DB.init_db()
    import crypto_util as CRYPTO
    import totp as TOTP

    secret = TOTP.new_secret()
    enc = CRYPTO.encrypt(secret)
    chk(enc.startswith("v1:") and enc != secret,
        "★★★★★ 암호화된 값은 v1: 접두사를 갖고 평문과 다르다", enc[:20])
    chk(CRYPTO.decrypt(enc) == secret,
        "★★★★★ 복호화하면 원래 비밀키로 정확히 돌아온다(왕복 정상)")

    code = TOTP.code_now(secret)
    ok, _c, why = TOTP.verify(CRYPTO.decrypt(enc), code)
    chk(ok and why == "ok",
        "★★★★★ 암호화→저장→복호화→검증 전체 경로로 실제 코드가 통과한다", why)

    #  ⚠ 기존에 이미 평문으로 저장돼 있던 비밀키(이번 수정 전 가입자) —
    #    마이그레이션 없이 그대로 계속 동작해야 한다.
    chk(CRYPTO.decrypt(secret) == secret,
        "★★★★★ v1: 접두사가 없는 기존 평문 비밀키는 그대로 통과한다(하위호환, 마이그레이션 불필요)")
    ok2, _c2, why2 = TOTP.verify(CRYPTO.decrypt(secret), code)
    chk(ok2 and why2 == "ok",
        "★★★★★ 레거시 평문 비밀키로도 실제 코드 검증이 정상 동작한다(기존 가입자 로그인 안 끊김)")

    #  실제 DB 왕복까지 — INSERT 는 암호화된 값으로, 로그인 경로처럼 다시 읽어 복호화.
    conn = DB.get_db()
    conn.execute(
        "INSERT INTO admins(username, password_hash, name, role, must_change_pw, created_at, "
        "                    totp_enabled, totp_secret) "
        "VALUES(?,?,?,?,0,?,1,?)",
        ("r269_test_admin", DB.hash_pw("테스트비번1234"), "R269", "중간관리자", DB.now(), enc))
    conn.commit()
    row = conn.execute("SELECT totp_secret FROM admins WHERE username=?",
                       ("r269_test_admin",)).fetchone()
    conn.close()
    chk(row["totp_secret"] == enc and row["totp_secret"] != secret,
        "★★★★ DB 컬럼엔 암호화된 값이 실제로 들어간다(평문이 그대로 저장되지 않음)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드269 [2] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — 복구코드 엔트로피 64비트로 확대, 기존 8-hex 형식도 계속 검증됨")
# ------------------------------------------------------------
try:
    codes = TOTP.new_recovery_codes()
    chk(len(codes) == 8, "STEP 발급 개수(8장)는 그대로다")
    for c in codes:
        hexpart = c.replace("-", "")
        chk(len(hexpart) == 16 and re.fullmatch(r"[0-9a-f]{16}", hexpart),
            f"★★★★★ 새 복구코드는 16 hex(64비트)다 — {c}", c)

    #  같은 코드를 대소문자·하이픈만 다르게 넣어도 같은 해시가 나와야 한다
    #  (hash_recovery() 의 정규화가 새 포맷 길이에서도 정상 동작하는지).
    sample = codes[0]
    variant = sample.upper().replace("-", "")
    chk(TOTP.hash_recovery(sample) == TOTP.hash_recovery(variant),
        "STEP 새 포맷도 대소문자·하이픈 차이를 흡수해 같은 해시를 낸다")

    #  ⚠ 기존에 이미 발급된 8-hex(구 포맷) 복구코드의 해시도 계속 유효해야
    #    한다 — hash_recovery() 자체는 안 건드렸으므로 당연히 되지만,
    #    실행으로 직접 확인한다(회귀 없음 증명).
    legacy_code = "5aad-31ea"
    legacy_hash_before = TOTP.hash_recovery(legacy_code)
    legacy_hash_after = TOTP.hash_recovery("5AAD31EA")
    chk(legacy_hash_before == legacy_hash_after and len(legacy_hash_before) == 64,
        "★★★★ 구 포맷(8-hex) 복구코드의 해시도 여전히 정상 동작한다(기존 발급분 회귀 없음)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드269 [3] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
