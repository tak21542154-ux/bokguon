# -*- coding: utf-8 -*-
"""스캔 581라운드 회귀 — manage.py cmd_check()의 "외부 공개 주소" 자가점검이
   `if _pub: ... elif _pub: ...` 로 두 조건이 글자 그대로 같아, logs/
   public_host.txt 가 없거나(신규 배포 전) 전부 주석·빈 줄뿐이면 이 절 전체가
   ok·warn·bad 무엇도 안 찍고 조용히 사라지던 결함(직접조사, 하위위임 없음).

   조사 각도 — pyflakes 정적분석(사람이 그냥 읽어서는 눈에 안 띄는 조용한
   모순을 찾는 도구)을 이 저장소 핵심 모듈 전체에 걸었다. app.py 의 경보
   8건은 전부 무해로 판명(logger.exception 이 예외를 자동 포함·flask.g 를
   안 쓰는 함수 안의 섀도잉·고정 4/8열 표에 맞는 하드코드 열문자 등 — 소스만
   읽고 판단 가능해 회귀 불필요). geo.py 의 "dictionary key repeated" 15건은
   이미 [라운드293] 주석이 "아래 값만 유효, 차이는 0~472m 로 실사고 없음"이라고
   스스로 실측·설명해 둔 사안이라 재조사하지 않는다. 남은 manage.py:585의
   "local variable '_allow' is assigned to but never used" 를 따라가다 바로
   아래 `elif _pub:` 를 발견했다 — 바로 위 `if _pub:` 와 조건이 문자 그대로
   같아, `if X: ... elif X: ...` 는 X 값과 무관하게 elif 가 영원히 못 걸리는
   항등식이다(파이썬 제어흐름 자체의 문제이지 pyflakes 의 판정이 아니다 —
   아래 [2]가 실제 실행으로 재확인한다).

   실제 영향 — 이 절(3-2절)은 주석이 스스로 밝히듯 **2026-08-06 실제 운영
   사고**(재시작 후 허용 Host 목록이 옛 값으로 남아 외부 요청이 전부 400 으로
   막혔는데, 로컬 점검은 전부 통과해 몇 시간 동안 아무도 몰랐다) 재발 방지용
   이다. logs/public_host.txt 는 배포 스크립트가 쓰는 파일이라 신규 클론
   직후·그 파일을 지운 뒤·전부 주석 처리된 상태에서 `python manage.py check`
   를 돌리면 `_pub` 가 빈 리스트가 되어 if 도 elif 도 안 걸린다 — 그런데 같은
   함수 안(공종 커버리지 점검 자리)이 이미 "이유 없는 건너뜀은 통과처럼
   읽힌다"는 원칙을 명시해 두고도, 이 절만 그 원칙을 어기고 ok/warn/bad
   어느 줄도 안 찍은 채 다음 절로 넘어간다 — 이 검사가 있는지조차 출력만
   보고는 알 수 없다.

   형제 대조 — 같은 함수(cmd_check) 안에서 "확인할 수 없으면" 유형은 전부
   이유를 대며 warn()+warns 증가를 쓴다(공종 커버리지 점검 실패·사진 폴더
   못 읽음·접속기록 예약 미확인·시계 드리프트 비교불가 등). 이 절만 그
   관례를 안 따르고 있었다.

   고침 — manage.py: `elif _pub:` 를 `else:` 로 바꾸고, 그 자리에 죽어 있던
   `ok(f"외부 공개 주소 {_pub[0]} (Host 검사 없음)")`(애초에 `_pub` 가 비어야만
   오는 자리라 `_pub[0]` 자체가 IndexError — 이 분기가 실행된 적이 있었다면
   그 자리에서 바로 죽었을 것이다) 대신, 형제들과 같은 형식의 warn()+warns
   증가로 바꿨다. `if _pub:` 안의 기존 분기(있음/서버다운/400/그 외 상태코드)
   는 전혀 안 건드렸다 — 실제로 살아 있던 사각지대(_pub 가 빈 경우)만 메운다.

   이 회귀테스트는 [1] 소스 확인(옛 `elif _pub:` 패턴 소멸 + 새 else 가
   warn()+warns 를 쓴다), [2] 되돌리기-증명 — manage.py 의 실제 소스 문자열
   에서 이 절만 그대로 오려내(on-disk 파일은 절대 안 건드린다) 지금 버전과
   고치기 전 그대로 재구성한 버전을 각각 독립 함수로 exec() 해, 같은 입력
   (_pub 를 만들 logs/public_host.txt 가 없음 · 있어도 주석·빈 줄뿐)을
   통과시키고 실제로 옛 버전은 ok/warn/bad 어느 것도 안 부르고 warns 도 그대로
   인 반면 지금 버전은 warn() 을 정확히 한 번 부르고 warns 가 1 늘어나는 것을
   실측 대조한다. [3] 회귀 없음 — `_pub` 가 있는(정상) 경로는 기존 분기가
   그대로 살아 있는지, 아무도 안 듣는 포트로 강제 연결거부를 유도해 실제
   실행으로 확인한다.

       python test_scan_round581_fixes.py
"""
import io
import os
import socket
import sys
import tempfile
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


MANAGE_SRC = io.open(os.path.join(HERE, "manage.py"), encoding="utf-8").read()

print("=" * 72)
print("  스캔 581라운드 회귀 — manage.py cmd_check() 외부공개주소 점검의")
print("  elif _pub: (if _pub: 와 조건이 같아 영원히 안 걸리는) 죽은 분기")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
#  ⚠ 이 라운드 자신의 설명 주석(위 파일 헤더에도 있다)이 옛 패턴을 산문으로
#    인용하므로 "elif _pub:" 부분문자열 검색은 안 쓴다(round580 이 자기참조
#    오탐으로 이미 겪은 함정) — 실제 코드 줄(주석이 아닌, 앞공백만 뗀 줄이
#    정확히 이 문구로 시작하는 줄)만 센다.
_code_elif_pub = [ln for ln in MANAGE_SRC.splitlines()
                  if ln.strip().startswith("elif _pub:") and not ln.strip().startswith("#")]
chk(_code_elif_pub == [],
    "★★★★★ 옛 `elif _pub:`(바로 위 if 와 조건이 같아 영원히 안 걸리던 분기)가 "
    "실제 코드에는 더는 없다(설명 주석 속 인용은 별개)", _code_elif_pub)

_START = '_hf = os.path.join(HERE, "logs", "public_host.txt")'
chk(MANAGE_SRC.count(_START) == 1, "  (전제) 절 시작 앵커가 정확히 한 곳에 있다")
_start_mark = MANAGE_SRC.index(_START)
#  ⚠ _start_mark 는 `_hf` 글자 자체의 위치라 그 줄 앞의 들여쓰기(8칸)를 못
#    담는다 — 줄 시작(직전 개행 다음)까지 되돌아가야 첫 줄도 나머지 줄과
#    같은 들여쓰기를 갖고, 그래야 아래 textwrap.dedent() 가 공통 접두를
#    8칸으로 올바르게 계산한다(안 그러면 첫 줄만 0칸이 되어 dedent 가
#    사실상 무효화되고, 재들여쓰기 뒤 IndentationError 로 바로 드러난다).
_start_i = MANAGE_SRC.rfind("\n", 0, _start_mark) + 1
_END_ANCHOR = '"기록을 남기세요."); warns += 1'
chk(MANAGE_SRC.count(_END_ANCHOR) == 1, "  (전제) 절 끝 앵커가 정확히 한 곳에 있다")
_end_i = MANAGE_SRC.index(_END_ANCHOR, _start_mark) + len(_END_ANCHOR)
BLOCK = MANAGE_SRC[_start_i:_end_i]

_ELSE_MARKER = "        else:\n            #  ⚠⚠ [라운드581]"
chk(BLOCK.count(_ELSE_MARKER) == 1,
    "  새 절이 정확히 한 곳에서 `else:` + 이번 라운드 설명 주석으로 이어진다")
_tail = BLOCK.rsplit("else:", 1)[1]
chk('warn("logs/public_host.txt 에 기록된 공개 주소가 없어' in _tail
    and "warns += 1" in _tail,
    "★★★★★ else 분기가 warn() 을 부르고 warns 를 올린다(다른 '확인 불가' "
    "형제들과 같은 관례)")

# ============================================================
print("\n[2] 되돌리기-증명 — 이 절만 오려내 실행(on-disk 파일은 안 건드린다)")
# ------------------------------------------------------------
def _wrap(body_dedented):
    reindented = "\n".join(("    " + ln if ln.strip() else ln)
                            for ln in body_dedented.splitlines())
    return (
        "def _probe(HERE, calls):\n"
        "    fails = 0\n"
        "    warns = 0\n"
        "    def ok(m): calls.append(('ok', m))\n"
        "    def warn(m): calls.append(('warn', m))\n"
        "    def bad(m): calls.append(('bad', m))\n"
        + reindented + "\n"
        "    return fails, warns\n"
    )


FIXED_FN_SRC = _wrap(textwrap.dedent(BLOCK))
_ns_fixed = {"os": os}
exec(compile(FIXED_FN_SRC, "<round581_fixed_block>", "exec"), _ns_fixed)

#  옛 버전 재구성 — [1]에서 이미 확인한 지금의 else 분기를, 이 라운드 이전에
#  실제로 저장소에 있던 그 문자 그대로의 두 줄로 되돌린다. 이 문자열은
#  오직 이 테스트의 로컬 변수일 뿐 — manage.py 파일에는 절대 쓰지 않는다.
_OLD_BRANCH = ('elif _pub:\n'
               '            ok(f"외부 공개 주소 {_pub[0]} (Host 검사 없음)")')
_new_branch_start = BLOCK.index(_ELSE_MARKER)
OLD_BLOCK = BLOCK[:_new_branch_start] + "        " + _OLD_BRANCH
OLD_FN_SRC = _wrap(textwrap.dedent(OLD_BLOCK))
_ns_old = {"os": os}
exec(compile(OLD_FN_SRC, "<round581_old_block>", "exec"), _ns_old)

_tmp = tempfile.mkdtemp(prefix="round581_")
os.makedirs(os.path.join(_tmp, "logs"), exist_ok=True)

# 시나리오 A — public_host.txt 자체가 없음(신규 배포 전과 동일한 상태)
_calls_old_a, _calls_new_a = [], []
_f_old_a = _ns_old["_probe"](_tmp, _calls_old_a)
_f_new_a = _ns_fixed["_probe"](_tmp, _calls_new_a)
chk(_calls_old_a == [] and _f_old_a == (0, 0),
    "★★★★★ (인과관계 실측 A) public_host.txt 없음 — 고치기 전 코드 그대로라면 "
    "ok/warn/bad 어느 것도 안 부르고 warns 도 0 그대로였다", (_calls_old_a, _f_old_a))
chk(len(_calls_new_a) == 1 and _calls_new_a[0][0] == "warn" and _f_new_a == (0, 1),
    "★★★★★ (핵심 증거 A) 지금 코드는 같은 상황에서 warn() 을 정확히 한 번 "
    "부르고 warns 가 1 이 된다", (_calls_new_a, _f_new_a))

# 시나리오 B — 파일은 있지만 전부 주석·빈 줄뿐
with io.open(os.path.join(_tmp, "logs", "public_host.txt"), "w", encoding="utf-8") as f:
    f.write("# example.invalid (주석)\n\n")
_calls_old_b, _calls_new_b = [], []
_f_old_b = _ns_old["_probe"](_tmp, _calls_old_b)
_f_new_b = _ns_fixed["_probe"](_tmp, _calls_new_b)
chk(_calls_old_b == [] and _f_old_b == (0, 0),
    "  (인과관계 실측 B) 전부 주석뿐인 파일도 옛 코드는 여전히 침묵했다",
    (_calls_old_b, _f_old_b))
chk(len(_calls_new_b) == 1 and _calls_new_b[0][0] == "warn" and _f_new_b == (0, 1),
    "  (핵심 증거 B) 지금 코드는 이 경우도 warn() 한 번으로 알린다",
    (_calls_new_b, _f_new_b))

# ============================================================
print("\n[3] 회귀 없음 — _pub 가 있는(정상) 경로는 그대로다")
# ------------------------------------------------------------
#  실제 호스트가 하나 기록돼 있으면 기존 if _pub: 분기가 여전히 살아서
#  로컬 서버에 물어본다 — 아무도 안 듣는 포트로 강제 연결거부를 유도해
#  기존 except OSError: 경로("서버 미기동" ok)를 실제로 태운다.
_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
_s.bind(("127.0.0.1", 0))
_free_port = _s.getsockname()[1]
_s.close()
with io.open(os.path.join(_tmp, "logs", "public_host.txt"), "w", encoding="utf-8") as f:
    f.write("idle-recovered-chemistry-titles.trycloudflare.com\n")
_old_port_env = os.environ.get("BOKGUON_PORT")
os.environ["BOKGUON_PORT"] = str(_free_port)
try:
    _calls_new_c = []
    _f_new_c = _ns_fixed["_probe"](_tmp, _calls_new_c)
finally:
    if _old_port_env is None:
        os.environ.pop("BOKGUON_PORT", None)
    else:
        os.environ["BOKGUON_PORT"] = _old_port_env
chk(len(_calls_new_c) == 1 and _calls_new_c[0][0] == "ok" and _f_new_c == (0, 0),
    "  _pub 가 있고 그 포트에 서버가 없으면(연결거부) 기존 '서버 미기동' ok "
    "분기가 그대로 나온다 — 이번 수정이 있던 분기를 안 건드렸다",
    (_calls_new_c, _f_new_c))

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
