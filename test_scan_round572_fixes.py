# -*- coding: utf-8 -*-
"""스캔 572라운드 회귀 — "서버가 스스로 낡았다고 말한다"는 방어(_src_hash/
   server_is_stale, admin.html·insurer_portal.html·partner_portal.html 상단
   빨간 배너)가 실제로는 app.py·db.py **둘만** 보고 있어서, app.py 가 import
   하는 나머지 로컬 모듈 11개(compliance·dispatch·photo_ai·geo·legal_docs·
   crypto_util·totp·notify_popbill·addr_search·repair_estimate·envload)가
   바뀌어도 배너가 절대 뜨지 않던 결함(직접조사, 하위위임 없음).

   조사 각도 — round571 이 "인라인 핸들러 상시검사 자신의 스캔 범위가 정말
   전수인가"를 되짚었던 것과 같은 각도를, 또 다른 "상시 자기점검" 장치인
   _src_hash() 에 적용했다. 이 장치의 주석은 "파이썬 코드는 기동 시점 것이
   메모리에 박혀 있다"고 일반적으로 말하지만, 실제 구현은 ("app.py","db.py")
   두 파일만 열어 봤다. app.py 는 db 말고도 로컬 모듈을 11개 더 top-level
   import 하고, 그것들도 db.py 와 똑같이 기동 시점 것이 프로세스 메모리에
   그대로 눌러앉는다 — 그중 compliance.py 는 compliance.gate() 하나로
   무등록 도급 형사벌(건산법상 5년 이하)을 막는 이 서비스의 유일한 법적
   방어선이다(db.py 의 contract_gate_log 스키마 주석에 그대로 적혀 있다).

   실제 영향 — 이 세션에서만도 crypto_util.py·dispatch.py·addr_search.py 가
   app.py 와 같은 시각대(2026-09-11, os.path.getmtime 실측)에 함께 수정됐고
   legal_docs.py 는 하루 전에 수정됐다. 즉 이 사각지대는 이론이 아니라 매
   라운드 실제로 밟히는 경로다 — compliance.py 의 법적 판정 로직을 고치고
   재시작을 잊어도 화면은 끝까지 "최신"이라 말한다. 지금까지
   _src_hash·server_is_stale·_BOOT_SRC_HASH 를 다룬 회귀테스트는 하나도
   없었다(전 test_*.py grep 0건 — round572 이전엔 아무도 이 장치를 검사하지
   않았다).

   고침 — app.py 의 _src_hash() 단일 지점(이 값의 유일한 정의처이자
   server_is_stale() 의 유일한 호출 대상, 다른 caller 없음). app.py 최상단에
   `import sys` 를 추가하고, 하드코딩된 ("app.py","db.py") 튜플을 sys.modules
   순회로 교체했다 — 지금 실제로 메모리에 로드된 모듈 중 __file__ 의 폴더가
   app.py 와 같은 것을 전부 훑는다. _build_hash()(바로 위 형제 함수)가 이미
   한 번 배운 "손으로 나열한 파일 목록은 반드시 어긋난다"는 교훈을 그대로
   따른 것이라, 이번에도 새 하드코딩 목록을 만들지 않았다 — 새 로컬 모듈이
   생겨도 import 되는 순간 저절로 감시 대상에 잡힌다.

   이 회귀테스트는 [1] 소스 확인, [2] 스크래치 DB로 안전하게 실제 app.py 를
   import 해 sys.modules 를 실측(진짜로 로컬 모듈 12개+ 가 잡히는가),
   [3] 되돌리기 — 옛(2파일) 버전을 인메모리 문자열로 재구성해 **같은 실제
   프로세스**에서 새 버전과 나란히 놓고 compliance 모듈을 sys.modules 에서
   잠깐 뺐다 복원하는 방식으로 인과관계를 실측(on-disk 파일은 전혀 건드리지
   않는다), [4] 스크래치 디렉토리에 심은 가짜 로컬 모듈의 **내용 자체가
   바뀌었을 때** 옛 방식은 놓치고 새 방식은 잡는지까지 확인한다.

      python test_scan_round572_fixes.py
"""
import hashlib
import io
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


print("=" * 72)
print("  스캔 572라운드 회귀 — '서버 낡음' 배너(_src_hash)가 app.py·db.py만 보던 결함")
print("=" * 72)

APP_SRC = read("app.py")

# ============================================================
print("\n[1] 소스 확인 — app.py 가 실제로 넓어졌는가")
# ------------------------------------------------------------
chk("\nimport sys\n" in APP_SRC[:200],
    "★★★★★ app.py 최상단에 import sys 가 추가됐다")
chk(APP_SRC.count("\nimport sys\n") == 1,
    "  import sys 는 한 곳에서만 추가됐다(중복 없음)")

_h_start = APP_SRC.index("def _src_hash():")
_h_end = APP_SRC.index("_BOOT_SRC_HASH = _src_hash()")
SRC_HASH_NEW_SRC = APP_SRC[_h_start:_h_end]

chk('for fn in ("app.py", "db.py")' not in SRC_HASH_NEW_SRC,
    "★★★★★ 옛(app.py·db.py 두 파일 하드코딩) 목록이 더는 없다")
chk("sys.modules" in SRC_HASH_NEW_SRC,
    "★★★★★ sys.modules 를 실제로 훑는다")
chk("os.path.dirname(os.path.abspath(_f)) == here" in SRC_HASH_NEW_SRC,
    "★★★★★ __file__ 이 app.py 와 같은 폴더인 모듈만 고른다(서드파티·stdlib 오탐 방지)")
chk("for f in sorted(files):" in SRC_HASH_NEW_SRC,
    "  파일 목록을 정렬해 순회한다(순서가 흔들리면 해시가 흔들린다 — _build_hash()와 같은 원칙)")
chk('files = {os.path.join(here, "app.py")}' in SRC_HASH_NEW_SRC,
    "  app.py 자신은 sys.modules 조회와 무관하게 항상 명시적으로 포함된다"
    "(__main__ 로 실행되든 app 모듈로 import 되든 안전)")

# ============================================================
print("\n[2] 실제 임포트 — 스크래치 DB로 안전하게 app.py 를 로드해 커버리지 실측")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round572_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB
DB.init_db()
import app as A

h1 = A._src_hash()
chk(isinstance(h1, str) and len(h1) == 12,
    "★★★★ _src_hash() 는 여전히 12자 문자열을 돌려준다(반환 형식 회귀 없음)", h1)
chk(A._BOOT_SRC_HASH == h1,
    "  부팅 직후 재계산해도 값이 같다(아직 아무것도 안 바뀌었으므로 당연)")
chk(A.server_is_stale() is False,
    "  부팅 직후에는 server_is_stale() 이 False 다")

_here_real = os.path.dirname(os.path.abspath(A.__file__))
local_mods = {name: m for name, m in sys.modules.items()
              if getattr(m, "__file__", None)
              and os.path.dirname(os.path.abspath(m.__file__)) == _here_real}
chk(len(local_mods) >= 12,
    f"★★★★★ 지금 실제로 로컬 모듈 {len(local_mods)}개가 해시 대상 폴더 안에서 잡힌다",
    sorted(local_mods))
for must in ("compliance", "dispatch", "photo_ai", "geo", "crypto_util", "legal_docs",
             "totp", "notify_popbill", "addr_search", "repair_estimate", "envload", "db"):
    chk(must in local_mods,
        f"★★★★★ {must}.py 가 실제로 sys.modules 에 잡혀 있다"
        "(예전 _src_hash 는 이 중 db 를 뺀 전부를 놓쳤다)")

# ============================================================
print("\n[3] 되돌리기 — 옛(2파일) 버전을 인메모리로 재구성해 같은 실제 환경에서 대조")
print("    (on-disk 파일은 전혀 건드리지 않는다 — sys.modules 에서 잠깐 빼고 복원)")
# ------------------------------------------------------------
OLD_SRC_HASH_SRC = '''
def _src_hash_OLD():
    h = hashlib.sha256()
    for fn in ("app.py", "db.py"):
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), fn), "rb") as f:
                h.update(f.read())
        except OSError:
            return ""
    return h.hexdigest()[:12]
'''
#  ⚠ exec 에 globals/locals 를 따로 나누면(2·3인자 분리) def 로 정의되는 함수의
#    __globals__ 가 "빈 globals" 쪽에 묶여, 나중에 이 함수를 호출할 때 본문이
#    참조하는 os/sys/hashlib/__file__ 을 못 찾는다(NameError). 한 dict 를
#    globals 겸 locals 로 써서 def 시점과 호출 시점이 같은 네임스페이스를 보게 한다.
_old_ns = {"__file__": A.__file__}
exec("import os, hashlib\n" + OLD_SRC_HASH_SRC, _old_ns)
old_hash = _old_ns["_src_hash_OLD"]

_new_ns = {"__file__": A.__file__}
exec("import os, sys, hashlib\n" + SRC_HASH_NEW_SRC, _new_ns)
new_hash = _new_ns["_src_hash"]

ho1, hn1 = old_hash(), new_hash()
chk(hn1 == h1,
    "  on-disk 소스에서 그대로 잘라낸 _src_hash 를 다시 실행해도 실제 A._src_hash() 와 같은 값")

_saved_cp = sys.modules.pop("compliance")
try:
    ho2, hn2 = old_hash(), new_hash()
finally:
    sys.modules["compliance"] = _saved_cp   # 반드시 복원 — 이 프로세스를 뒤 검사도 계속 쓴다

chk(ho1 == ho2,
    "★★★★★★ (핵심 증거) 옛 2파일 방식은 compliance.py 가 있든 없든 값이 완전히 같다 — "
    "무등록 도급 형사벌 방어선이 바뀌어도 절대 못 잡는다", (ho1, ho2))
chk(hn1 != hn2,
    "★★★★★★ (핵심 증거) 새 방식은 compliance.py 가 빠지면 값이 달라진다 — "
    "지금 실제로 감시 대상에 들어와 있다는 뜻", (hn1, hn2))
chk(new_hash() == hn1,
    "  compliance 모듈을 되돌려 놓으면 해시도 원래 값으로 복원된다(재현 가능·부작용 없음)")

_saved_fl = sys.modules.pop("flask")
try:
    hn3 = new_hash()
finally:
    sys.modules["flask"] = _saved_fl
chk(hn3 == hn1,
    "  대조군 — 이 폴더 밖 서드파티 모듈(flask)이 빠져도 새 방식의 값은 그대로다"
    "(과잉 포함으로 인한 오탐이 아니다)")

# ============================================================
print("\n[4] 내용 변경 시뮬레이션 — 스크래치 디렉토리의 가짜 로컬 모듈 내용이 바뀌면")
print("    옛 방식은 놓치고 새 방식은 잡는가 (파일 바이트 자체가 다른, 가장 직접적인 증거)")
# ------------------------------------------------------------
_scr = tempfile.mkdtemp(prefix="round572_content_")
io.open(os.path.join(_scr, "app.py"), "w", encoding="utf-8").write("# app v1\n")
io.open(os.path.join(_scr, "db.py"), "w", encoding="utf-8").write("# db v1\n")
io.open(os.path.join(_scr, "compliance.py"), "w", encoding="utf-8").write("# compliance v1\n")

#  db.py 는 옛 방식이 하드코딩으로 직접 여는 파일이라 실재해야 하지만(비어 있으면
#  OSError 로 옛 함수가 통째로 "" 를 반환해 대조가 무의미해진다), sys.modules 에는
#  일부러 등록하지 않는다 — 새 방식에서 db.py 의 감시는 [2]/[3]에서 이미 실제
#  환경(import db as DB)으로 증명했으므로, 여기서는 compliance.py 하나에만 집중한다.
_fake_mod = types.SimpleNamespace(__file__=os.path.join(_scr, "compliance.py"))
sys.modules["_round572_fake_compliance"] = _fake_mod
try:
    _old_ns2 = {"__file__": os.path.join(_scr, "app.py")}
    exec("import os, hashlib\n" + OLD_SRC_HASH_SRC, _old_ns2)
    _new_ns2 = {"__file__": os.path.join(_scr, "app.py")}
    exec("import os, sys, hashlib\n" + SRC_HASH_NEW_SRC, _new_ns2)

    before_old, before_new = _old_ns2["_src_hash_OLD"](), _new_ns2["_src_hash"]()
    #  compliance.py "코드를 고쳤다" — 재시작을 깜빡했다고 가정한다
    io.open(os.path.join(_scr, "compliance.py"), "w", encoding="utf-8").write(
        "# compliance v2 -- gate() bugfix\n")
    after_old, after_new = _old_ns2["_src_hash_OLD"](), _new_ns2["_src_hash"]()

    chk(before_old == after_old,
        "★★★★★★ (핵심 증거) 옛 방식은 compliance.py 내용을 실제로 고쳐도 해시가 그대로다 "
        "— 배너가 끝까지 '최신'이라 말한다", (before_old, after_old))
    chk(before_new != after_new,
        "★★★★★★ (핵심 증거) 새 방식은 같은 수정으로 해시가 바뀐다 — 배너가 '재시작 필요'로 바뀐다",
        (before_new, after_new))

    #  회귀 방지 — app.py 자신이 바뀌는 경우는 예전에도 잡혔고 지금도 잡혀야 한다
    io.open(os.path.join(_scr, "app.py"), "w", encoding="utf-8").write("# app v2\n")
    final_old, final_new = _old_ns2["_src_hash_OLD"](), _new_ns2["_src_hash"]()
    chk(final_old != after_old and final_new != after_new,
        "  회귀 방지: app.py 자신이 바뀌는 경우는 옛/새 방식 둘 다 여전히 잡는다")
finally:
    del sys.modules["_round572_fake_compliance"]

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
