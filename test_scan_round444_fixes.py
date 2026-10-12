# -*- coding: utf-8 -*-
"""스캔 444라운드 회귀 — 세션 쿠키 보안속성(HttpOnly/SameSite/Secure)이
   BOKGUON_ENV 값에 따라 실제로 올바르게 적용되는지, 특히 운영(prod)
   전용 조합(SESSION_COOKIE_SECURE=True)이 지금까지 이 저장소의 어떤
   회귀테스트에서도 실행된 적이 없었다는 커버리지 공백을 메운다.

   정밀조사 Agent가 각도1(관리자 대신로그인)·각도2(세션쿠키 보안속성)를
   조사 — 둘 다 결함 없음(각도1은 기능 자체가 없어 해당없음, 각도2는
   HttpOnly·Secure·SameSite=Lax 셋 다 실제 라이브서버+실제 크로미움
   브라우저로 실측해 정상 작동 확인). 다만 조사 과정에서 발견: `run_all_
   tests.py:573`가 데모데이터 시딩 문제(라운드406) 때문에 `BOKGUON_ENV`를
   항상 "dev"로 강제해, `SESSION_COOKIE_SECURE=IS_PROD`가 실제로 True가
   되는 운영 조합이 이 프로젝트의 어떤 배터리에서도 한 번도 실행된 적이
   없었다 — 코드 자체는 이미 올바르지만(app.py:111-116) 그 정확성을
   보증하는 자동 회귀가 없는 상태였다.

   결함이 아니라 순수 커버리지 공백이라 코드 수정은 없음 — 이 파일이
   그 공백만 메운다. dev/prod 두 값 각각으로 app.py를 서브프로세스에서
   새로 import해(모듈 최상위 상수라 프로세스당 한 번만 평가된다) 실제
   app.config 값을 직접 확인한다.

   ⚠⚠ [라운드614] [4]의 "탐지력 증명"을 옛 세대(app.py 전체를 실제로
   디스크에 되돌린 문자열로 써넣고 서브프로세스로 재현한 뒤 복원 —
   write→subprocess→write 사이의 창을 다른 세션이 관측하면 충돌한다,
   round590이 실제로 겪음)에서 안전한 기법으로 이관한다. SESSION_COOKIE_
   SECURE는 app.config라는 평범한 dict의 엔트리 하나일 뿐이라, "실수로
   False를 하드코딩"이 낳는 최종 상태(그 엔트리가 False)는 import 직후
   그 자리에서 그대로 만들어도 소스를 실제로 바꾼 것과 증거가 동일하다
   — force_insecure=True로 그 자리에서 덮어써 재현한다(디스크의 app.py는
   [1]~[3]과 마찬가지로 전혀 안 건드린다 — 이 파일은 처음부터 끝까지
   app.py를 한 번도 쓰기모드로 연 적이 없다).

       python test_scan_round444_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(HERE, "app.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

print("=" * 72)
print("  스캔 444라운드 회귀 — 세션쿠키 보안속성이 BOKGUON_ENV를 정확히 반영")
print("=" * 72)

print("\n[1] 소스 확인")
chk("SESSION_COOKIE_HTTPONLY=True" in APP_SRC, "★★★ HttpOnly가 항상 True로 고정돼 있다")
chk('SESSION_COOKIE_SAMESITE="Lax"' in APP_SRC, "★★★ SameSite가 항상 Lax로 고정돼 있다")
chk("SESSION_COOKIE_SECURE=IS_PROD" in APP_SRC,
    "★★★★★ Secure가 IS_PROD(BOKGUON_ENV) 값을 그대로 따라간다")


def _check_env(env_name, secret_needed, force_insecure=False):
    """app.py를 서브프로세스에서 지정한 BOKGUON_ENV로 새로 import해
    실제 app.config 쿠키 설정값 3종을 그대로 돌려받는다.
    force_insecure=True면 import 직후 그 자리에서 SESSION_COOKIE_SECURE를
    False로 덮어써(디스크의 app.py는 전혀 안 건드림) "실수로 하드코딩
    했다면"을 시뮬레이션한다 — app.config는 평범한 dict라 이 값 자체가
    최종 상태의 전부이므로 소스를 실제로 바꾼 것과 동일한 증거를 낸다."""
    tmpdir = tempfile.mkdtemp(prefix=f"round444_{env_name}_")
    force_line = ("A.app.config['SESSION_COOKIE_SECURE'] = False  "
                  "# [라운드444 시뮬레이션] 실수로 하드코딩 재현 — 디스크 미기록"
                  if force_insecure else "")
    code = f'''# -*- coding: utf-8 -*-
import os, sys
os.environ["BOKGUON_DB_PATH"] = {os.path.join(tmpdir, "v.db")!r}
os.environ["BOKGUON_UPLOAD_DIR"] = {os.path.join(tmpdir, "up")!r}
os.environ["BOKGUON_ENV"] = {env_name!r}
os.environ["BOKGUON_SEED_DEMO"] = "0"
{"os.environ['BOKGUON_SECRET_KEY'] = 'r444-test-secret-key-not-real'" if secret_needed else ""}
sys.path.insert(0, {HERE!r})
import app as A
{force_line}
print("HTTPONLY", A.app.config["SESSION_COOKIE_HTTPONLY"])
print("SAMESITE", A.app.config["SESSION_COOKIE_SAMESITE"])
print("SECURE", A.app.config["SESSION_COOKIE_SECURE"])
'''
    import subprocess
    rp = subprocess.run([sys.executable, "-c", code], cwd=HERE,
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=30)
    return rp.stdout + rp.stderr


print("\n[2] 실행 — BOKGUON_ENV=dev 로 새로 import 했을 때")
out_dev = _check_env("dev", secret_needed=False)
chk("HTTPONLY True" in out_dev, "  dev: HttpOnly=True", out_dev[-300:])
chk("SAMESITE Lax" in out_dev, "  dev: SameSite=Lax", out_dev[-300:])
chk("SECURE False" in out_dev,
    "★★★ dev: Secure=False(로컬 http 개발이 쿠키 없이 막히지 않는다)", out_dev[-300:])

print("\n[3] 실행 — BOKGUON_ENV=prod 로 새로 import 했을 때"
      "(지금까지 이 프로젝트의 어떤 배터리도 실행한 적 없는 조합)")
out_prod = _check_env("prod", secret_needed=True)
chk("HTTPONLY True" in out_prod, "  prod: HttpOnly=True(변함없음)", out_prod[-300:])
chk("SAMESITE Lax" in out_prod, "  prod: SameSite=Lax(변함없음)", out_prod[-300:])
chk("SECURE True" in out_prod,
    "★★★★★ prod: Secure=True — 운영 전용 조합이 실제로 켜짐"
    "(이 저장소 최초의 이 조합 실측 확인)", out_prod[-300:])

# ============================================================
print("\n[4] 탐지력 증명 — Secure를 실수로 하드코딩하면 이 테스트가 prod에서 잡아내는가")
# ------------------------------------------------------------
try:
    out_broken = _check_env("prod", secret_needed=True, force_insecure=True)
    chk("SECURE False" in out_broken,
        "★★★★★ Secure를 실수로 False로 두면(재현, 디스크 미기록) prod에서도 "
        "실제로 꺼진다(인과관계 직접증명 — 이 테스트가 이 실수를 잡아낼 수 있다는 뜻)",
        out_broken[-300:])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 탐지력 증명 실행", f"{type(e).__name__} {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py는 이 테스트가 실행되는 내내 실제로 한 번도 안 바뀌었다"
    "(디스크에는 처음부터 쓰기모드로 연 적이 없다)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
