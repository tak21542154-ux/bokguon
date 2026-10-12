# -*- coding: utf-8 -*-
"""스캔 488라운드 회귀 — api_otp_confirm()에 형제(api_otp_disable, 라운드414)
와 같은 _recent_fails 무차별대입 잠금이 없던 결함. 반복 오답을 보내도
안 잠기던 것을, 이제 MAX_LOGIN_FAILS 초과 시 429로 막는지 실제 Flask로
확인하고, 되돌림-증명으로 옛 동작(무제한 시도)이 실제로 재현되는지도
대조한다.

⚠ 라운드488의 수정은 한 지점이 아니라 두 지점(①TOTP.verify 호출 앞의
  잠금검사 블록 ②그 호출 뒤의 _log_attempt 호출)에 나뉘어 들어갔고 그
  사이에는 원본 코드(u = one(...) 조회·409분기·TOTP.verify 호출)가
  그대로 남아 있다 — 두 지점을 각각 독립적으로 제거해야 원본이 정확히
  복원된다(하나로 뭉뚱그려 제거하면 원본 코드까지 같이 지워진다).

⚠⚠ [라운드614] 되돌림-증명 기법을 옛 세대(app.py를 실제로 디스크에
써넣고 새로 생성한 워커 스크립트를 서브프로세스로 돌려 재현한 뒤 복원
— write→subprocess→write 사이의 창을 다른 세션이 관측하면 충돌한다,
round590이 실제로 겪음)에서 round414(스텝 7-2, api_otp_disable — 바로
이 함수의 형제)가 확립한 안전패턴으로 이관한다. api_otp_confirm() 은
단일 라우트 핸들러라 이 함수 자신의 소스에서 ①·② 블록을 제거한 사본을
exec 로 재구성(require_admin 데코레이터도 다시 입힘)해 A.app.
view_functions 딕셔너리 항목만 잠깐 치환한다 — 진짜 app.py 파일은
전혀 안 쓴다(예전 워커 test_scan_round488_worker.py 는 매 실행 새로
써서 남기던 임시 파일이었다 — 이 파일은 더 이상 그걸 만들지 않는다).
TOTP.verify/CRYPTO.decrypt 는 app.py 가 `import totp as TOTP`·
`import crypto_util as CRYPTO`로 그대로 참조하는 실제 모듈 자신이라
(사본이 아니다) 몽키패치가 프로세스 전체에 영향을 준다 — 이제 같은
프로세스 안에서 여러 시나리오를 돌리므로 반드시 finally 로 원래
함수로 복원한다(예전 워커는 복원이 필요없는 일회성 서브프로세스였다).
"""
import hashlib
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(HERE, "app.py")
PASS, FAIL = [], []


def chk(c, n, d=""):
    (PASS if c else FAIL).append((n, d))
    print(("  [OK]   " if c else "  [FAIL] ") + n + ("" if c else f"   {d}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


print("=" * 72)
print("  스캔 488라운드 회귀 — api_otp_confirm() 무차별대입 잠금 누락")
print("=" * 72)

APP_SRC = read("app.py")
APP_HASH_BEFORE = hashlib.sha256(APP_SRC.encode("utf-8")).hexdigest()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
_a = APP_SRC.find('    #  ⚠⚠ [라운드488]')
_b = APP_SRC.find('    u = one(conn.execute("SELECT * FROM admins WHERE username=?"', _a)
BLOCK_A = APP_SRC[_a:_b] if _a > 0 and _b > _a else ""

_c = APP_SRC.find('    ok, counter, _why = TOTP.verify(', _b)
_d = APP_SRC.find('\n', _c) + 1
_e = APP_SRC.find('\n', _d) + 1
BLOCK_B = APP_SRC[_d:_e] if _c > 0 else ""

chk(bool(BLOCK_A) and "_recent_fails" in BLOCK_A, "① 잠금검사 블록을 찾았다")
chk(APP_SRC.count(BLOCK_A) == 1, "① 블록이 소스에 유일하다", APP_SRC.count(BLOCK_A) if BLOCK_A else 0)
chk(bool(BLOCK_B) and "_log_attempt(conn, otp_key, ok)" in BLOCK_B, "② _log_attempt 호출을 찾았다", BLOCK_B)
chk(APP_SRC.count(BLOCK_B) == 1, "② 블록이 소스에 유일하다", APP_SRC.count(BLOCK_B) if BLOCK_B else 0)


def _py_fn_body(src, fn_name):
    """함수 본문 — 다음 def뿐 아니라 다음 라우트의 @app. 데코레이터가
    먼저 나오면 거기서 자른다(round610 정착 기법). api_otp_confirm()
    바로 뒤가 데코레이터 달린 api_otp_disable() 라 단순 '\\ndef ' 경계만
    쓰면 그 데코레이터 줄까지 통째로 딸려와 exec 시 구문오류가 난다."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


_body = _py_fn_body(APP_SRC, "api_otp_confirm")
chk(BLOCK_A in _body and BLOCK_B in _body,
    "  api_otp_confirm() 본문 안에 ①·② 블록이 모두 있다")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round488_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    def _mk_admin(uname):
        conn = DB.get_db()
        conn.execute(
            "INSERT INTO admins(username,password_hash,name,role,totp_secret) "
            "VALUES(?,?,?,?,?)", (uname, "x", "n2", "최고관리자", "ENC"))
        conn.commit(); conn.close()

    def _admin_client(uname):
        c = A.app.test_client()
        with c.session_transaction() as s:
            s["admin"] = uname; s["admin_role"] = "최고관리자"; s["_csrf"] = "x"
        return c

    def _brute(uname, n=10):
        _mk_admin(uname)
        client = _admin_client(uname)
        codes = []
        for _ in range(n):
            r = client.post("/api/me/otp/confirm", json={"code": "000000"},
                             headers={"X-CSRF-Token": "x"})
            codes.append(r.status_code)
        return codes

    #  TOTP.verify/CRYPTO.decrypt 는 실제 모듈 자신(사본이 아니다)이라
    #  이 프로세스 전체에 영향을 준다 — 반드시 finally 로 복원한다.
    _orig_decrypt = A.CRYPTO.decrypt
    _orig_verify = A.TOTP.verify
    A.CRYPTO.decrypt = lambda x: "SECRET"
    A.TOTP.verify = lambda secret, code: (False, 0, "bad")
    try:
        print("\n[3] 실행 — 현재(고쳐진) 코드로 10회 반복")
        codes_fixed = _brute("r488fixed")
        chk(429 in codes_fixed,
            "★★★★★ 새 코드: 10회 반복 중 429 잠금이 실제로 발생한다", codes_fixed)

        # ══════════════════════════════════════════════════════
        print("\n[4] 되돌리기 — api_otp_confirm만 옛 코드로(실제 파일은 안 건드림)")
        # ────────────────────────────────────────────────────
        _old_body = (_body
                     .replace("def api_otp_confirm():", "def _api_otp_confirm_pre488():", 1)
                     .replace(BLOCK_A, "", 1)
                     .replace(BLOCK_B, "", 1))
        chk("_api_otp_confirm_pre488" in _old_body
            and BLOCK_A not in _old_body and BLOCK_B not in _old_body,
            "  (준비) 함수 리네임 + ①·② 블록 제거가 정확히 적용됐다(실제 파일은 안 건드림)")

        _ns = dict(vars(A))
        exec(compile(_old_body, "<round488_pre488_otp_confirm>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
        old_confirm_fn = A.require_admin(_ns["_api_otp_confirm_pre488"])

        _orig_view = A.app.view_functions["api_otp_confirm"]
        A.app.view_functions["api_otp_confirm"] = old_confirm_fn
        try:
            codes_broken = _brute("r488broken")
        finally:
            A.app.view_functions["api_otp_confirm"] = _orig_view

        chk(429 not in codes_broken,
            "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림)는 10회 반복해도 안 잠긴다"
            " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", codes_broken)

        print("\n[5] 원복 확인 — 되돌리기 이후 다시 잠기는가(바꿔치기가 안 샜다)")
        chk(A.app.view_functions["api_otp_confirm"] is _orig_view,
            "  view_functions가 원래 함수객체로 복원됐다")
        codes_restored = _brute("r488restored")
        chk(429 in codes_restored,
            "★★★★ 원복 후에는 다시 429 잠금이 발생한다(바꿔치기가 안 샜다)", codes_restored)
    finally:
        A.CRYPTO.decrypt = _orig_decrypt
        A.TOTP.verify = _orig_verify

except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3]+[4] 실행/되돌림-증명", f"{type(e).__name__}: {e}")

APP_HASH_AFTER = hashlib.sha256(read("app.py").encode("utf-8")).hexdigest()
chk(APP_HASH_AFTER == APP_HASH_BEFORE,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(view_functions 딕셔너리 항목 임시치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
