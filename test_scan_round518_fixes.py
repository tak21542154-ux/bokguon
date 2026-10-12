# -*- coding: utf-8 -*-
"""스캔 518라운드 회귀 — check_orphan_chars.py 가 cp949 콘솔(한국어 윈도 기본
   코드페이지)에서 결과를 한 줄도 못 내고 UnicodeEncodeError 로 죽던 결함.

   조사 배경 — 직접 조사(하위위임 없음). 이미 포화된 축(형제 엔드포인트 잠금
   비대칭 504~507, 지역문자열 독자구현 511·512·516, XSS/SSRF 509·510·517,
   정책문서 불일치 289·317·508 등)과 겹치지 않는 새 각도를 찾다가, 이 저장소가
   스스로 만들어 둔 점검 도구(check_*.py)들을 실제로 **실행**해 보는 접근을
   택했다 — 소스만 읽어서는 "돌긴 하는데 결과가 이상하다"류 결함을 못 잡는다.
   check_tx_paths.py 를 먼저 실행해 클린(106개 함수 전부 정상)임을 확인한 뒤,
   형제 도구 check_orphan_chars.py 를 실행하자 **결과를 내기도 전에** 다음
   트레이스백으로 죽었다.

       File "check_orphan_chars.py", line 166, in main
         print(f"\\n[1] 깨진 문자 — 대상 {len(files)}개 파일")
       UnicodeEncodeError: 'cp949' codec can't encode character '\\u2014'
       in position 12: illegal multibyte sequence

   원인 — check_tx_paths.py(19~27행)·repair_estimate.py(33~39행)·popbill_check.py·
   manage.py·partner_accounts.py 등 이 저장소의 거의 모든 단독 실행 CLI 도구는
   "윈도 기본 콘솔은 cp949 라 '—' 같은 문자를 print 하면 UnicodeEncodeError 로
   죽는다"는 이유로 stdout 을 UTF-8 로 reconfigure() 하는 방어를 이미 갖고
   있는데(27개 파일에서 확인), 같은 저자·같은 목적(check_*.py 점검 도구)·거의
   같은 구조인 check_orphan_chars.py 만 이 방어가 빠져 있었다 — 정확히 이
   코드베이스가 스스로 반복해서 잡아내는 "형제는 이미 막았는데 이 파일만
   빠졌다" 패턴이다. 더 나쁜 것은 이 스크립트 자신이 "고아문자·깨진문자
   점검"이라는 **다른 코드의 인코딩 결함을 잡는 도구**라는 점 — 그 도구
   자신이 한국어 윈도 콘솔(cp949)에서 결과를 한 줄도 못 내고 죽으면, 실제로
   깨진 문자가 있는지 없는지조차 알 방법이 없다("자기도구가 내는 거짓
   초록"과 자매인 "자기도구가 아예 안 도는" 실패 양상).

   재현 조건 — PYTHONIOENCODING=cp949 는 콘솔에 직접 붙어있지 않을 때(파이프로
   리다이렉트·로그 파일로 저장·예약실행 등, 이 스크립트를 실제로 쓰는 방식과
   정확히 같다) 파이썬이 stdout 인코딩을 고를 때 실제로 참조하는 값이며, 이
   저장소가 도는 한국어 윈도의 기본 ANSI 코드페이지와 같다(이 세션이 실제
   cmd.exe 로 파일 리다이렉트해 같은 크래시를 환경변수 없이도 재현 확인).

   고침 — check_tx_paths.py 가 이미 쓰는 것과 정확히 같은 방어(try: reconfigure,
   실패하면 TextIOWrapper 폴백)를 check_orphan_chars.py 맨 위(기존 import 直後)에
   그대로 옮겼다. 새 헬퍼·새 상수 없음 — 형제의 기존 코드를 그대로 복사.

      python test_scan_round518_fixes.py
"""
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "check_orphan_chars.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("═" * 72)
print("  스캔 518라운드 회귀 — check_orphan_chars.py cp949 콘솔 크래시")
print("═" * 72)

src = io.open(TARGET, encoding="utf-8").read()
GUARD_NEEDLE = 'sys.stdout.reconfigure(encoding="utf-8")'
GUARD_COMMENT_START = "#  ⚠⚠ 윈도 기본 콘솔은 cp949"
HEADER_AFTER_GUARD = "HERE = os.path.dirname(os.path.abspath(__file__))"

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 형제(check_tx_paths.py)와 같은 reconfigure 방어가 있는가")
# ──────────────────────────────────────────────────────────────
chk(GUARD_NEEDLE in src,
    "check_orphan_chars.py 에 stdout.reconfigure(utf-8) 방어가 있다")
chk(src.count(GUARD_NEEDLE) == 1,
    "그 방어는 정확히 한 번만 있다(중복 삽입 아님)", src.count(GUARD_NEEDLE))
sib = io.open(os.path.join(HERE, "check_tx_paths.py"), encoding="utf-8").read()
chk(GUARD_NEEDLE in sib,
    "형제 check_tx_paths.py 도 같은 방어를 이미 갖고 있다(비교 기준 확인)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 서브프로세스를 cp949(윈도 기본 콘솔 코드페이지)로 강제해도 "
      "안 죽는가")
# ──────────────────────────────────────────────────────────────
env = dict(os.environ)
env["PYTHONIOENCODING"] = "cp949"
env.pop("PYTHONUTF8", None)
r = subprocess.run([sys.executable, TARGET], cwd=HERE, env=env,
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=90)
chk("UnicodeEncodeError" not in (r.stderr or ""),
    "★★★★★ cp949 로 강제해도 UnicodeEncodeError 없이 끝까지 돈다",
    (r.stderr or "")[-300:])
chk("Traceback" not in (r.stderr or ""),
    "★★★★ 어떤 예외로도 죽지 않는다(트레이스백 없음)", (r.stderr or "")[-300:])
chk("고아문자·깨진문자 점검" in (r.stdout or ""),
    "★★★★★ 진단 결과 머리글이 실제로 출력된다(죽지 않고 진짜 일을 했다는 증거)",
    (r.stdout or "")[:200])
chk(r.returncode in (0, 1),
    "종료코드가 이 도구 자신의 정상 판정 범위 안이다(0=클린/1=발견있음 — "
    "이 도구가 지금 무엇을 발견했는지는 이 회귀의 관심사가 아니다)",
    r.returncode)

# ══════════════════════════════════════════════════════════════
print("\n[3] 되돌리기 — 방어를 지우면(수정 전 상태 재현) 실제로 다시 죽는가"
      "(인과관계 직접증명)")
# ──────────────────────────────────────────────────────────────
#  이 방어는 import 시점에 모듈 최상단에서 실행되는 코드라 사후 몽키패치로는
#  끌 수 없다(라운드517 은 함수를 갈아끼웠지만, 여기는 갈아끼울 함수가 아니라
#  import 부작용이다) — 방어 블록만 정확히 도려낸 사본을 만들어 실제 서브
#  프로세스로 실행해 재현한다. 도려낸 결과가 "고치기 전 원본"과 글자 그대로
#  같아야만 이 되돌리기가 유효하므로, 그 동일성부터 확인한다.
guard_start = src.index(GUARD_COMMENT_START)
guard_end = src.index(HEADER_AFTER_GUARD)
assert 0 <= guard_start < guard_end, "가드 블록 경계를 못 찾음 — 앵커 재확인 필요"
reverted_src = src[:guard_start] + src[guard_end:]
EXPECTED_OLD_HEADER = (
    "import io\nimport os\nimport re\nimport sys\nimport unicodedata\n\n"
    "HERE = os.path.dirname(os.path.abspath(__file__))")
chk(EXPECTED_OLD_HEADER in reverted_src,
    "되돌린 사본이 '고치기 전' 원본과 글자 그대로 같은 머리말을 만든다"
    "(임의로 지어낸 되돌리기가 아님을 확인)")
chk(GUARD_NEEDLE not in reverted_src,
    "되돌린 사본에는 방어 코드가 실제로 빠져 있다(사전 확인)")

revert_path = os.path.join(HERE, "_r518_reverted_check_orphan_chars.py")
try:
    with io.open(revert_path, "w", encoding="utf-8") as f:
        f.write(reverted_src)
    r2 = subprocess.run([sys.executable, revert_path], cwd=HERE, env=env,
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=90)
    chk(r2.returncode != 0,
        "★★★★★ 방어를 지우면 비정상 종료한다(고치기 전엔 이랬다)", r2.returncode)
    chk("UnicodeEncodeError" in (r2.stderr or ""),
        "★★★★★ 방어를 지우면 cp949 환경에서 실제로 UnicodeEncodeError 로 죽는다"
        "(인과관계 확인 — 이 방어가 실제로 이 크래시를 막고 있었다)",
        (r2.stderr or "")[-300:])
    chk("고아문자·깨진문자 점검" not in (r2.stdout or ""),
        "★★★★ 되돌린 사본은 진단 결과를 하나도 못 낸다"
        "(진짜 깨진 문자가 있어도 없어도 알 방법이 없었다는 뜻)",
        (r2.stdout or "")[:200])
finally:
    try:
        os.remove(revert_path)
    except OSError:
        pass

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
