# -*- coding: utf-8 -*-
"""스캔 578라운드 회귀 — partner_accounts.py 의 _csv_safe() 가 "app.py 의 동명
   헬퍼와 같은 규칙"이라는 자기 자신의 docstring 약속과 달리, 탭(\t)으로 시작하는
   값의 수식주입을 못 막던 결함(직접조사, 하위위임 없음).

   조사 각도 — round577("이 파일이 스스로 하는 약속을 실제 코드가 지키는가")을
   변형해 **여러 파일에 걸친 약속**("app.py 의 동명 헬퍼와 같은 규칙")이 실제로
   지켜지는지를 봤다. app.py 는 이미 round423 에서 _csv_safe()·_xl_safe() 두
   형제 모두 "\t=1+1" 처럼 탭으로 시작하는 값도 트리거로 잡게 고쳤다(제어문자
   필터는 탭을 보존하면서도, 트리거 판정 v[:1] in ("=","+","-","@") 는 그 탭을
   반영하지 않았던 결함). 그런데 이 저장소 전체에서 같은 판정식을 쓰는 곳은
   정확히 3곳(app.py 2곳 + partner_accounts.py 1곳, 실측: grep)뿐이고,
   round423 의 수정은 app.py 안의 두 곳에만 적용됐다 — 세 번째 형제인
   partner_accounts.py:_csv_safe() 는 자기 docstring 이 "app.py 의 동명
   헬퍼와 같은 규칙"이라고 명시하는데도 옛(round423 이전) 판정식 그대로
   남아 있었다.

   실제 영향 — partner_accounts.py 는 협력사(partners) 표의 업체명·지역·공종·
   연락처를 CSV 로 내보낸다(--out). 이 값들은 이 파일 자신의 docstring 이 이미
   "업체가 스스로 입력한 자유 텍스트"라고 부르는 값이다. 업체명이 "\t=1+1..."
   처럼 탭으로 시작하면(round423 이 app.py 쪽에서 이미 실측한 것과 동일한 형태),
   옛 _csv_safe() 는 v[:1] 이 "=" 가 아니라 "\t" 이므로 방어용 `'` 접두를 안
   붙이고 원문 그대로 CSV 에 쓴다 — 엑셀로 열면 수식으로 실행된다.

   고침 — partner_accounts.py:_csv_safe() 의 트리거 집합에 "\t" 를 추가해
   app.py 의 두 형제와 정확히 같은 규칙으로 맞춘다(새 헬퍼·새 상수 없음, 이미
   있던 단일 규칙을 세 번째 자리에도 그대로 적용). 이 파일 자신의 --self-check
   (demo())에도 이 규칙을 직접 확인하는 assert 3개를 추가했다(round418 이 같은
   파일의 gen_pw() 를 고칠 때 세운 것과 같은 관례 — 고친 함수는 이 파일 자신의
   자체점검에도 반영한다).

   이 회귀테스트는 [1] 소스 확인(3곳 전수 일치), [2] 실제 실행(모듈을 그대로
   import 해 _csv_safe 호출 + CLI --self-check 서브프로세스 실행), [3] 되돌리기
   — 옛 트리거 집합(탭 없음)을 문자열 치환+exec 로 재구성(on-disk 파일은 절대
   건드리지 않음)해 옛 버전이 실제로 탭우회를 막지 못했음을 대조 확인한다.

       python test_scan_round578_fixes.py
"""
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


print("=" * 72)
print("  스캔 578라운드 회귀 — partner_accounts.py _csv_safe() 탭우회 수식주입")
print("=" * 72)

PA_SRC = read("partner_accounts.py")
APP_SRC = read("app.py")

# ============================================================
print("\n[1] 소스 확인 — 형제 전수(이 저장소 전체에서 이 판정식을 쓰는 곳은 3곳뿐)")
# ------------------------------------------------------------
TRIGGER_WITH_TAB = '("=", "+", "-", "@", "\\t")'
TRIGGER_NO_TAB = '("=", "+", "-", "@")'

chk(PA_SRC.count(TRIGGER_WITH_TAB) == 1,
    "★★★★★ partner_accounts.py:_csv_safe() 트리거 집합에 탭이 추가됐다",
    PA_SRC.count(TRIGGER_WITH_TAB))
chk(TRIGGER_NO_TAB not in PA_SRC,
    "★★★★★ partner_accounts.py 에 탭 없는 옛 판정식이 더는 안 남아있다")
#  ⚠⚠ [라운드599] app.py 안의 두 형제 중 로컬 _csv_safe()(api_settlements_export)가
#    없어지고 공유 _xl_safe() 를 직접 쓰게 되면서(round221과 같은 근본원인의
#    두 번째 사례 — 셀 정제 독자재구현, 이번엔 트리거가 아니라 제어문자
#    보존범위가 갈라졌었다) 이 판정식은 이제 app.py 안에 1곳(_xl_safe)뿐이다.
chk(APP_SRC.count(TRIGGER_WITH_TAB) == 1,
    "  회귀 없음 — app.py 는 이제 _xl_safe() 1곳뿐(round599가 _csv_safe 사본을 "
    "없애 _xl_safe 로 통합, partner_accounts.py 의 별도 사본은 그대로 3번째)",
    APP_SRC.count(TRIGGER_WITH_TAB))
chk('"엑셀 수식 인젝션 방지 — app.py 의 동명 헬퍼(_csv_safe·_xl_safe)와 같은 규칙."'
    in PA_SRC or "app.py 의 동명 헬퍼(_csv_safe·_xl_safe)와 같은 규칙" in PA_SRC,
    "  docstring 이 이제 형제 두 곳(_csv_safe·_xl_safe) 모두를 명시한다")

# demo() 자체점검이 이 규칙을 직접 확인하는지
_di = PA_SRC.index("def demo():")
DEMO_SRC = PA_SRC[_di:]
chk('_csv_safe("\\t=1+1")[:1] == "\'"' in DEMO_SRC,
    "★★★★ partner_accounts.py 자체점검(demo)이 탭우회 방어를 직접 확인한다")
chk('_csv_safe("=1+1") == "\'=1+1"' in DEMO_SRC,
    "  자체점검에 대조군(=로 시작하는 기존 방어)도 함께 있다")

# ============================================================
print("\n[2] 실제 실행")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round578_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "partner_accounts.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import partner_accounts as PA  # noqa: E402  (경로 준비 뒤 import)

chk(PA._csv_safe("\t=1+1")[:1] == "'",
    "★★★★★ 실제 모듈의 _csv_safe() 가 탭으로 시작하는 값을 이제 막는다",
    PA._csv_safe("\t=1+1"))
chk(PA._csv_safe("=1+1") == "'=1+1", "  대조군 — 기존 방어(=로 시작)는 그대로(회귀없음)")
chk(PA._csv_safe("+1+1") == "'+1+1", "  대조군 — 기존 방어(+로 시작)는 그대로(회귀없음)")
chk(PA._csv_safe("정상업체명") == "정상업체명", "  대조군 — 평범한 값은 안 바뀐다(회귀없음)")
chk(PA._csv_safe("hello\tworld") == "hello\tworld",
    "  대조군 — 문자열 중간의 탭은 그대로 보존된다(제어문자 필터 회귀없음)")

try:
    PA.demo()
    chk(True, "★★★★ partner_accounts.demo() 가 예외 없이 통과한다(위 3개 assert 포함)")
except AssertionError as e:
    chk(False, "★★★★ partner_accounts.demo()", str(e))

# 공식 진입점(python partner_accounts.py --self-check)도 그대로 통과하는가
r = subprocess.run([sys.executable, os.path.join(HERE, "partner_accounts.py"), "--self-check"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    cwd=HERE, timeout=30)
chk(r.returncode == 0, "  CLI `python partner_accounts.py --self-check` 종료코드 0", r.returncode)
chk("CSV 수식주입 방어" in (r.stdout or ""),
    "  CLI 출력에 새 자체점검 문구가 실제로 찍힌다", repr(r.stdout[-200:]))

# ============================================================
print("\n[3] 되돌리기 — 옛 판정식(탭 없음)이었다면 실제로 탭우회를 막지 못했는가")
# ------------------------------------------------------------
_fi0 = PA_SRC.index("def _csv_safe(v):")
_fi1 = PA_SRC.index("\ndef ", _fi0 + 1)   # 다음 함수 시작 — docstring 안의 빈 줄에 안 속는다
NEW_FN_SRC = PA_SRC[_fi0:_fi1]
chk(TRIGGER_WITH_TAB in NEW_FN_SRC, "  (준비) 함수 슬라이스 안에 새 트리거 문자열이 있다")

OLD_FN_SRC = NEW_FN_SRC.replace(TRIGGER_WITH_TAB, TRIGGER_NO_TAB)
chk(OLD_FN_SRC != NEW_FN_SRC, "  (준비) 옛 버전 재구성이 실제로 트리거 집합만 바꿔치기했다")

ns_old = {}
exec(compile(OLD_FN_SRC, "<old_csv_safe>", "exec"), ns_old)  # noqa: S102 -- 우리 소스, on-disk 파일은 안 건드림
old_csv_safe = ns_old["_csv_safe"]

chk(old_csv_safe("\t=1+1") == "\t=1+1",
    "★★★★★★ (핵심증거) 옛 판정식은 탭으로 시작하는 값을 그대로 통과시켰다"
    "(인과관계 직접증명 — 지금 버전은 위 [2]에서 막음을 이미 확인)",
    old_csv_safe("\t=1+1"))
chk(old_csv_safe("=1+1") == "'=1+1",
    "  대조군 — 옛 버전도 = 로 시작하는 값은 원래부터 막았다(회귀 아님, 딱 탭만 사각지대)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
