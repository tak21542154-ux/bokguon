# -*- coding: utf-8 -*-
"""스캔 658라운드 회귀 — popbill_check.py `_hint()` 오류코드 매핑 결함 2건.

   round649가 "공식 문서 필요"로 미결 처리한 뒤 5라운드(649~657) 보류돼 있던
   항목을 웹 접근으로 직접 해소 — 공식 linkhub-sdk/popbill.exception 저장소의
   990_linkhub.csv(UTF-8)·150_message.csv(EUC-KR)를 원문 바이트 대조.

   [결함1] exact 표의 '-99004022'/'-99004023'는 실제로는 "생성할 링크아이디정보/
   서비스 목록이 입력되지 않았습니다"(신규 LinkID 발급용 관리자 API 오류 — 이
   도구가 부르는 checkIsMember/getCorpInfo/getSenderNumberList/getBalance/send
   어느 것도 낼 수 없는 코드)인데 "SecretKey가 틀렸다"는 근거 없는 문구가 붙어
   있었다. 진짜 서명불일치 코드 -99010007은 특정 안내가 없어 애매한 '-99'
   통합문구로만 떨어졌다.

   [결함2] 발신번호 판정 `c.startswith("-100") or "1004" in c`가 실제 발신번호
   미등록 코드(-15001009~014)를 단 하나도 못 잡는다("-15001" 대역이라 "-100"
   prefix에 안 걸리고 "1004" 부분문자열도 없음). 반대로 전혀 무관한 -15001004
   ("삭제할 수신거부번호가 입력되지 않았습니다")는 "1004" 부분일치로 오탐.

   고침 — exact 표를 검증된 코드로 교체(-99004022/023 제거, -99010007 추가),
   발신번호 판정을 실제 6개 코드(-15001009~014)의 정확한 set 매칭으로 교체.
   demo() 안의 합성코드 '-1004'도 실제 코드 '-15001014'로 교체.

   [1] AST — exact 딕셔너리 키 집합과 발신번호 set 이 정확한 코드 집합인지 확인.
   [2] 실행 — _hint() 직접호출로 6개 코드(신규·제거·오탐수정·정직한 폴백 포함) 검증.
   [3] 실행 — 실제 main()/step() 파이프라인 종단확인. notify_popbill._services 를
       가짜 서비스로 바꿔치고(실제 popbill.PopbillException 을 던지게 함) main() 을
       그대로 호출해 화면 출력에 올바른 힌트가 실제로 찍히는지 확인.
   [4] 되돌리기 — 고치기 전 _hint() 소스를 문자열로 격리 네임스페이스에 exec해
       (실파일 미접촉) 옛 버전이 네 가지 증상(미탐지·오탐·근거없는 확정문구·
       애매한 폴백)을 실제로 냈음을 인과관계로 증명.
   [5] --self-check 서브프로세스 재확인.

   python test_scan_round658_fixes.py
"""
import ast
import contextlib
import io
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


SRC = read("popbill_check.py")

print("=" * 72)
print("  스캔 658라운드 회귀 — popbill_check.py _hint() 오류코드 매핑 결함 2건")
print("=" * 72)

print("\n[1] 소스 확인 (AST)")
tree = ast.parse(SRC, filename="popbill_check.py")
hint_fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_hint")

exact_keys = set()
sender_codes = set()
for node in ast.walk(hint_fn):
    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict) \
            and any(isinstance(t, ast.Name) and t.id == "exact" for t in node.targets):
        exact_keys = {k.value for k in node.value.keys}
    if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "c" \
            and any(isinstance(op, ast.In) for op in node.ops):
        for comparator in node.comparators:
            if isinstance(comparator, ast.Tuple):
                vals = {e.value for e in comparator.elts if isinstance(e, ast.Constant)}
                if vals and all(str(v).startswith("-15001") for v in vals):
                    sender_codes = vals

chk(exact_keys == {"-99004021", "-99010007"},
    "★★★★★ exact 표가 정확히 {-99004021, -99010007} 만 담는다(가짜 -99004022/023 제거)",
    exact_keys)
chk(sender_codes == {"-15001009", "-15001010", "-15001011",
                      "-15001012", "-15001013", "-15001014"},
    "★★★★★ 발신번호 판정이 실제 6개 코드의 정확한 set 이다(부분일치 아님)",
    sender_codes)
chk('c.startswith("-100") or "1004" in c' not in SRC,
    "★★★★★ 옛(미탐지+오탐) 발신번호 판정 문자열이 소스에 더 이상 없다")
_demo_body = SRC.split("def demo()")[1] if "def demo()" in SRC else ""
chk('_hint("-1004")' not in _demo_body and 'assert "발신번호" in _hint("-15001014")' in _demo_body,
    "STEP demo() 의 자체점검이 합성코드 '-1004' 대신 실제 코드(-15001014)로 "
    "_hint() 를 부른다(주석의 과거형 설명은 코드가 아니므로 별개)")

print("\n[2] 실행 — _hint() 직접호출로 6개 코드 검증")
sys.path.insert(0, HERE)
import importlib
import popbill_check as PC  # noqa: E402

chk("LinkID" in PC._hint("-99004021"),
    "★★★★ 유지된 실제 코드 -99004021 은 여전히 LinkID 안내를 낸다")
chk("서명" in PC._hint("-99010007") or "연동인증" in PC._hint("-99010007"),
    "★★★★★ 신규 추가된 진짜 서명불일치 코드 -99010007 이 이제 구체적으로 안내된다",
    PC._hint("-99010007"))
chk("SecretKey가 틀렸다" not in PC._hint("-99004022") and "SecretKey 가 틀렸다" not in PC._hint("-99004022"),
    "★★★★★ 삭제된 가짜 코드 -99004022 는 더 이상 근거없는 'SecretKey 틀렸다' "
    "확정 문구를 안 낸다(이제 '-99004' prefix 의 정직한 일반 안내로 폴백)",
    PC._hint("-99004022"))
for code in ("-15001009", "-15001010", "-15001011", "-15001012", "-15001013", "-15001014"):
    chk("발신번호" in PC._hint(code), f"★★★★ 실제 발신번호 미등록 코드 {code} 가 정확히 잡힌다",
        PC._hint(code))
chk("발신번호" not in PC._hint("-15001004"),
    "★★★★★ 무관한 -15001004(수신거부번호 오류)는 더 이상 발신번호 오탐을 안 낸다",
    PC._hint("-15001004"))

print("\n[3] 실행 — 실제 main()/step() 파이프라인 종단확인(가짜 서비스가 진짜 "
      "popbill.PopbillException 을 던짐)")
import popbill as PB  # noqa: E402
import notify_popbill as NP  # noqa: E402

os.environ["POPBILL_LINK_ID"] = "R658TESTLINK"
os.environ["POPBILL_SECRET_KEY"] = "R658TESTSECRET"
os.environ["POPBILL_CORP_NUM"] = "6568702554"
os.environ["POPBILL_SENDER"] = "0212345678"
os.environ["POPBILL_TEST"] = "1"

_orig_services = NP._services


class _FakeSvc:
    def __init__(self, code, message):
        self._code, self._message = code, message

    def checkIsMember(self, corp_num):
        raise PB.PopbillException(self._code, self._message)


def _run_main_with_fake_code(code, message):
    fake = _FakeSvc(code, message)
    NP._services = lambda: (fake, fake)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            PC.main()
    finally:
        NP._services = _orig_services
    return buf.getvalue()


try:
    out1 = _run_main_with_fake_code("-99004021", "연동정보가 존재하지 않습니다")
    chk("LinkID" in out1, "★★★★★ 실제 main() 파이프라인에서 -99004021 예외가 나면 "
        "화면에 LinkID 안내가 정확히 찍힌다(가짜 서비스가 진짜 PopbillException 을 던짐)",
        out1[-300:])

    out2 = _run_main_with_fake_code("-99010007", "권한요청 정보의 서명이 일치하지 않습니다")
    chk("서명" in out2 or "연동인증" in out2,
        "★★★★ 실제 main() 파이프라인에서 신규 코드 -99010007 도 구체 안내로 찍힌다",
        out2[-300:])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ [3] main()/step() 종단 실행", f"{type(e).__name__} {e}")
finally:
    NP._services = _orig_services

print("\n[4] 되돌리기 — 고치기 전 _hint() 를 격리 네임스페이스에 exec해 네 가지 증상을 재현")
try:
    _pre_hint_src = '''
def _hint(code):
    c = str(code)
    exact = {
        "-99004021": "LinkID 가 틀렸습니다 - 팝빌 > 연동관리 > 연동인증 관리 의 값을 그대로 넣으세요.",
        "-99004022": "SecretKey가 틀렸습니다 - 팝빌 > 연동관리 > 연동인증 관리 의 값을 다시 확인하세요.",
        "-99004023": "SecretKey가 틀렸습니다 - 팝빌 > 연동관리 > 연동인증 관리 의 값을 다시 확인하세요.",
    }
    if c in exact:
        return exact[c]
    if c.startswith("-99004"):
        return "연동인증(LinkID SecretKey)이 맞지 않습니다."
    if c.startswith("-99005") or c.startswith("-99"):
        return "연동인증 계열 오류입니다."
    if c.startswith("-1000"):
        return "회원 정보 오류입니다."
    if c.startswith("-100") or "1004" in c:
        return "발신번호가 등록 승인되지 않았습니다."
    return "팝빌 오류 코드입니다."
'''
    ns = {}
    exec(compile(_pre_hint_src, "<round658_pre_hint>", "exec"), ns)   # noqa: S102 -- 우리 소스 재구성
    pre_hint = ns["_hint"]

    chk("SecretKey" in pre_hint("-99004022"),
        "★★★★★ 되돌린(고치기 전) 버전은 가짜 코드 -99004022 에 근거없는 'SecretKey' "
        "확정문구를 낸다 — 결함1 재현")
    chk("연동인증 계열" in pre_hint("-99010007") and "서명" not in pre_hint("-99010007"),
        "★★★★★ 되돌린 버전은 진짜 서명불일치 코드 -99010007 을 애매한 '-99' 통합문구로만 "
        "떨어뜨린다 — 결함1의 반대증상(미탐지) 재현")
    chk("발신번호" not in pre_hint("-15001014"),
        "★★★★★★ 되돌린 버전은 실제 발신번호 미등록 코드 -15001014 를 전혀 못 잡는다 "
        "— 결함2 미탐지 재현")
    chk("발신번호" in pre_hint("-15001004"),
        "★★★★★ 되돌린 버전은 무관한 -15001004 를 발신번호 오류로 오탐한다 — 결함2 오탐 재현")

    chk(PC._hint("-15001014").find("발신번호") >= 0,
        "★★★★★ 지금(수정 후) 실제 popbill_check._hint 는 같은 코드에서 정확히 잡는다"
        "(인과관계 직접증명)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ [4] 되돌림-증명 실행", f"{type(e).__name__} {e}")

print("\n[5] --self-check 서브프로세스 재확인")
try:
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "popbill_check.py"), "--self-check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    chk(r.returncode == 0, "★★★★ --self-check 서브프로세스가 0으로 종료된다", r.stdout + r.stderr)
    chk("자체 점검 통과" in r.stdout, "★★★ '자체 점검 통과' 문구가 실제로 출력된다", r.stdout)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★ [5] --self-check 서브프로세스 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
