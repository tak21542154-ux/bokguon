# -*- coding: utf-8 -*-
"""스캔 418라운드 회귀 — partner_accounts.py::gen_pw()(협력사 계정 일괄발급용
   임시비밀번호 생성)가 형제 3곳(app.py:_gen_temp_pw, manage.py:gen_password,
   발주처 인라인 발급)이 이미 쓰는 "대문자·소문자·숫자 각 1개 이상 보장"
   재시도 루프 없이 secrets.choice() 한 방으로 끝내던 결함(정밀조사 Agent
   발견 — 각도2: 임시비밀번호 예측가능성. 몬테카를로 20만회 실측 약 16%
   확률로 숫자가 하나도 없는 비밀번호가 나와, 이 앱 자신의 password_policy_
   error() 기준(두 종류 이상 조합)을 위반한 채 실제 협력사 계정에 발급될 수
   있었다). 같은 파일의 자체 점검(demo(), --self-check)도 길이·혼동글자만
   보고 문자종 구성은 안 봐서 이 결함을 통과시키고 있었다.

   무차별대입 관점의 보안결함은 아니다(49자×12자리 ≈ 67비트, 여전히
   강력) — 순전히 "이 코드베이스가 이미 3곳에서 확립한 패턴과 이 1곳만
   다르다"는 일관성 결함. 형제와 같은 재시도 루프를 그대로 이식.

       python test_scan_round418_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FILE_PATH = os.path.join(HERE, "partner_accounts.py")
PASS, FAIL = [], []

#  ⚠ gen_pw() 자체는 DB 를 안 건드리지만, partner_accounts.py 는 import 만
#    해도 db 모듈을 끌어오므로 이 세션의 표준 방어(테스트가 운영 DB 경로를
#    가리키면 중단)에 걸린다 — 다른 모든 test_scan_round*.py 와 같은 방식으로
#    스크래치 경로를 먼저 지정한다.
_tmpdir = tempfile.mkdtemp(prefix="round418_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


SRC = read("partner_accounts.py")

print("=" * 72)
print("  스캔 418라운드 회귀 — partner_accounts.py gen_pw() 문자종 보장 누락")
print("=" * 72)

print("\n[1] 소스 확인")


def body_of(fn_name):
    i0 = SRC.index(f"def {fn_name}(")
    try:
        i1 = SRC.index("\ndef ", i0 + 1)
    except ValueError:
        i1 = len(SRC)          # 파일의 마지막 함수(뒤에 def 가 더 없음)
    return SRC[i0:i1]


chk("while True:" in body_of("gen_pw") and "any(c.isdigit() for c in pw)" in body_of("gen_pw"),
    "★★★★★ gen_pw() 가 형제와 같은 재시도 루프로 문자종을 보장한다")
chk("any(c.isdigit() for c in pw)" in body_of("demo"),
    "★★★★ demo() 자체점검도 문자종 구성을 확인한다(전엔 길이·혼동글자만 봤다)")

sys.path.insert(0, HERE)
import secrets as _secrets_mod
import partner_accounts as PA

print("\n[2] 실행 — 결정론적 프록시로 '첫 시도 실패 → 재시도' 인과관계 실측")
#  ⚠ 확률적 결함(약 16%)이라 통계 시행보다, secrets.choice 를 큐 기반
#    가짜로 바꿔 "1차 시도(전부 소문자, 문자종 미달) → 재시도(정상 조합)"
#    순서를 결정론적으로 재현한다(411라운드의 _FailNthCommit 프록시 기법과
#    같은 정신 — 타이밍에 기대지 않는다).
BAD_BATCH = list("aaaaaaaaaaaa")          # 12자, 전부 소문자(숫자·대문자 0개)
GOOD_BATCH = list("Ab1Ab1Ab1Ab1")         # 12자, 대/소문자·숫자 전부 포함
QUEUE = BAD_BATCH + GOOD_BATCH + GOOD_BATCH   # 여유분

_orig_choice = _secrets_mod.choice
_calls = {"n": 0}


def _fake_choice(seq):
    i = _calls["n"]
    _calls["n"] += 1
    return QUEUE[i]


_secrets_mod.choice = _fake_choice
try:
    pw = PA.gen_pw(n=12)
finally:
    _secrets_mod.choice = _orig_choice

chk(_calls["n"] == 24,
    "★★★★★ 1차 시도(12회) 실패 후 정확히 재시도(12회 더)해 총 24회 호출됐다"
    "(고치기 전엔 12회로 끝났을 것)", _calls["n"])
chk(pw == "".join(GOOD_BATCH),
    "★★★★★ 최종 반환값은 재시도로 얻은 정상 조합이다(1차 실패작이 아니다)", pw)
chk(any(c.isupper() for c in pw) and any(c.islower() for c in pw) and any(c.isdigit() for c in pw),
    "  최종 반환값이 실제로 대/소문자·숫자를 전부 포함한다", pw)

print("\n[3] 대조군 — 정상 경로(진짜 secrets.choice)는 항상 정책을 만족한다")
ok_all = True
for _ in range(500):
    p = PA.gen_pw(n=12)
    if not (any(c.isupper() for c in p) and any(c.islower() for c in p)
            and any(c.isdigit() for c in p)):
        ok_all = False
        break
chk(ok_all, "  500회 반복 생성 전부 문자종 조건을 만족한다(회귀없음)")

# ============================================================
print("\n[4] 되돌리기 — 옛 코드로 되돌리면 1차 실패작을 그대로 반환하는가")
# ------------------------------------------------------------
#  ⚠⚠ [라운드617] on-disk 되돌리기(파일에 직접 쓰고 subprocess 로 재현)를
#    인메모리 exec 로 이관 — gen_pw() 는 이 테스트가 PA.gen_pw() 로 직접
#    부르는 평범한 모듈함수다(213·287행의 내부 호출자는 이 테스트 경로에서
#    안 불린다) — 독립 사본 이름공간에 exec 해도 안전(기법2). secrets.choice
#    몽키패치는 실제 secrets 모듈 객체 자체를 바꾸므로 사본에서도 그대로
#    보인다 — 실제 파일은 이제 전혀 안 건드린다.

NEW_GEN = '''def gen_pw(n=12):
    #  ⚠⚠ [라운드418] 형제(app.py:_gen_temp_pw, manage.py:gen_password)는 이미
    #    "대문자·소문자·숫자 각 1개 이상"을 재시도로 보장하는데 여기만 없었다
    #    — 몬테카를로 20만회 실측 약 16% 확률로 숫자가 하나도 없는 순문자
    #    비밀번호가 나와, 이 앱 자신의 password_policy_error() 기준(두 종류
    #    이상 조합) 위반 상태로 발급될 수 있었다. 같은 재시도 패턴을 이식한다.
    while True:
        pw = "".join(secrets.choice(ALPHABET) for _ in range(n))
        if (any(c.isupper() for c in pw) and any(c.islower() for c in pw)
                and any(c.isdigit() for c in pw)):
            return pw'''
OLD_GEN = '''def gen_pw(n=12):
    return "".join(secrets.choice(ALPHABET) for _ in range(n))'''

try:
    chk(SRC.count(NEW_GEN) == 1, "  (준비) 되돌리기 대상 텍스트가 유일하게 식별된다")
    reverted = SRC.replace(NEW_GEN, OLD_GEN)
    chk(reverted != SRC, "  (준비) 되돌리기 텍스트가 실제로 달라졌다")

    _ns418 = dict(vars(PA))
    exec(compile(OLD_GEN, "<round418_revert_gen_pw>", "exec"), _ns418)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    _old_gen_pw = _ns418["gen_pw"]

    QUEUE_OLD = list("aaaaaaaaaaaa") + list("Ab1Ab1Ab1Ab1")
    _calls2 = {"n": 0}

    def _fake_choice2(seq):
        i = _calls2["n"]
        _calls2["n"] += 1
        return QUEUE_OLD[i]

    _secrets_mod.choice = _fake_choice2
    try:
        old_pw = _old_gen_pw(n=12)
    finally:
        _secrets_mod.choice = _orig_choice

    chk(_calls2["n"] == 12,
        "★★★★★ 옛 코드는 재시도 없이 1차 12회 호출만으로 끝난다(인과관계 직접증명)",
        _calls2["n"])
    chk(not any(c.isdigit() for c in old_pw),
        "★★★★★ 옛 코드는 숫자가 하나도 없는 비밀번호를 그대로 반환한다"
        "(인과관계 직접증명 — password_policy_error 위반 상태로 발급됨)",
        old_pw)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
