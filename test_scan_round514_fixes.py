# -*- coding: utf-8 -*-
"""스캔 514라운드 회귀 — collect_emails.py BAD_LOCAL 의 "webmaster@example"
   항목이 애초에 매치될 수 없는 죽은 데이터였고, 그 자리를 메워야 할
   BAD_DOMAIN 에는 example.org·example.net(RFC 2606 예약 도메인, example.com
   과 동급)이 빠져 있어 "webmaster@example.org" 류 플레이스홀더 주소가
   그대로 "수집됨"으로 저장될 수 있었던 결함.

  직접 조사(하위위임 없음) — run_all_tests.py 를 먼저 정독해 이미 포화된
  축(형제 엔드포인트 잠금 비대칭 504~507, change_orders 생애주기 492,
  자격증명 전역유일 494, DUP_BIZNO 계열, 개인정보파기 6버킷 495,
  activity_log 마스킹 496·249, 가운뎃점 정규화 499, 출동수배 버튼
  등급게이트 502, catch분기 화면정리 481·486·500·501·503·504, 입점신청
  상태역전 504, 정책문서 불일치 289·317·508, website 저장형 XSS 509·510,
  지역판정 버그클래스 511·512, 재경매 재개 상한 513)와 겹치지 않는 각도를
  찾아, "엑셀/연락처 수집 경로의 필드 매핑·판정 오류" 힌트를 따라
  collect_emails.py(협력사 이메일 자동수집기, round218·267·299·420 이 이미
  여러 번 정밀조사한 파일)의 BAD_LOCAL/BAD_DOMAIN 판정 데이터를 값 하나하나
  대조했다.

  결함 — BAD_LOCAL = (..., "webmaster@example") 의 이 항목은 _bad_local_
  word_in(local, BAD_LOCAL) 로만 쓰이는데, `local` 은 반드시 pick_emails()
  안에서 `e.partition("@")` 로 만들어지는 **"@" 앞부분**이라 정의상 "@" 를
  포함할 수 없다. 즉 "webmaster@example" 이라는 항목 자체가 어떤 local part
  를 넣어도 절대 매치될 수 없는 죽은 데이터였다(round299 가 이미 다른
  결함 — `in` 부분열 오탐 — 을 이 근처에서 고쳤지만 이 항목의 구조적
  불능 자체는 못 봤다). 그 결과 실제로 흔한 플레이스홀더 주소인
  "webmaster@example.org"·"webmaster@example.net" 은 BAD_DOMAIN 에도
  안 걸렸다 — BAD_DOMAIN 은 example.com·example.co.kr 만 있고, RFC 2606 이
  example.com 과 동급으로 예약한 나머지 두 도메인(example.org·
  example.net)은 없었다. 그래서 collect_emails.pick_emails() 는 이 주소를
  "찾음"으로 돌려주어 그대로 partners.email 에 저장될 수 있고,
  clean_collected_emails.is_junk() 도(같은 BAD_DOMAIN/BAD_LOCAL 을
  from collect_emails import 로 공유) 사후 정리에서도 못 잡는다.

  실측(운영 DB 읽기전용) — partners 중 email_source='수집(홈페이지)' 인
  행은 현재 0건이라(이 도구가 아직 실운영에서 돌지 않음) 이미 저장된
  피해 사례는 없다 — 이 라운드의 고침은 205라운드의 "지금은 실사용
  호출이 없어 잠들어 있는 예방적 수정"과 같은 성격이다. 함수를 직접
  호출하면 결함은 그대로 재현된다(아래 [2]·[4]).

  고침 — (a) BAD_LOCAL 에서 절대 매치될 수 없는 "webmaster@example"
  항목을 없앤다(있으나 마나 한 죽은 데이터를 지운다 — 삭제는 아무 동작도
  안 바꾸지 않는 안전한 정리다, 아래 [3] 회귀 증명). (b) BAD_DOMAIN 에
  example.org·example.net 을 추가한다 — 둘 다 어느 회사도 등록할 수 없는
  RFC 2606 예약 도메인이라 오탐 위험이 없고, 새 상수·새 헬퍼 없이 이미
  있는 메커니즘(도메인 기반 차단)을 그대로 확장한다(ponytail 원칙).
  collect_emails.pick_emails() 와 clean_collected_emails.is_junk() 가
  이 튜플을 그대로 공유하므로 한 자리를 고치면 수집 시점·사후정리 시점
  둘 다 함께 고쳐진다.

  [1] 소스 확인 — "webmaster@example" 문자열이 파일에서 완전히 사라졌고,
      example.org·example.net 이 BAD_DOMAIN 정의에 정확히 한 번씩 있다.
  [2] 실행 — pick_emails()·is_junk() 양쪽에 새로 직접 호출해
      webmaster@example.{org,net,com,co.kr} 4종이 전부 걸러지는지,
      진짜 업체 주소(webmaster@실제도메인)는 그대로 통과하는지(과잉차단
      아님) 확인.
  [3] 회귀 없음 — round299 가 이미 세운 BAD_LOCAL 경계(latest·contest 는
      안 걸리고 test·no-reply 는 걸린다)가 그대로 유지된다.
  [4] 되돌림-증명 — 이 라운드 이전의 BAD_LOCAL/BAD_DOMAIN 값 그대로(파일은
      안 건드리고 모듈 속성만 임시로 되돌려) 같은 호출을 반복하면
      webmaster@example.org 가 실제로 "찾음"으로 새는 것을 재현한다.

      python test_scan_round514_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []

#  ⚠ [round299 전례] db.py 는 import 시점에 이 값을 본다 — 파일명이 test_
#    로 시작하면서 운영 DB 를 가리키면 SystemExit 한다. collect_emails.py
#    가 db 를 딸려 들여오므로, 반드시 그 어떤 import 보다도 먼저 지정한다.
_tmpdir = tempfile.mkdtemp(prefix="round514_")
os.environ.setdefault("BOKGUON_DB_PATH", os.path.join(_tmpdir, "verify.db"))
os.environ.setdefault("BOKGUON_ENV", "dev")
sys.path.insert(0, HERE)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


COLLECT_SRC = read("collect_emails.py")

print("=" * 72)
print("  스캔 514라운드 회귀 — collect_emails.py 죽은 BAD_LOCAL 항목·")
print("  BAD_DOMAIN example.org/.net 누락(webmaster@example.* 플레이스홀더 누출)")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
#  ⚠ 이 파일 자신의 위 docstring/주석이 옛 문자열 "webmaster@example" 을
#    설명을 위해 인용하므로, 파일 전체 텍스트 검색이 아니라 BAD_LOCAL 정의
#    리터럴 한 줄만 골라 검사한다(round513 류 다른 회귀도 같은 이유로
#    "정확히 한 번"을 셀 때 정의 지점을 특정한다).
import re as _re                                                      # noqa: E402
_bad_local_def = _re.search(r"BAD_LOCAL\s*=\s*\([^)]*\)", COLLECT_SRC, _re.S)
chk(bool(_bad_local_def), "STEP 전제 — BAD_LOCAL 정의를 소스에서 찾았다")
chk('"webmaster@example"' not in _bad_local_def.group(0),
    "★★★ 절대 매치될 수 없던 죽은 항목 \"webmaster@example\" 이 BAD_LOCAL 정의에서 사라졌다",
    _bad_local_def.group(0))
chk(COLLECT_SRC.count('"example.org"') == 1,
    "★★★ BAD_DOMAIN 에 example.org 가 정확히 한 번 추가됐다",
    COLLECT_SRC.count('"example.org"'))
chk(COLLECT_SRC.count('"example.net"') == 1,
    "★★★ BAD_DOMAIN 에 example.net 이 정확히 한 번 추가됐다",
    COLLECT_SRC.count('"example.net"'))

import collect_emails as CE                                          # noqa: E402
from clean_collected_emails import is_junk                            # noqa: E402

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 고친 뒤: 플레이스홀더 4종은 걸러지고, 진짜 주소는 통과한다")
# ──────────────────────────────────────────────────────────────
chk(not any("@" in b for b in CE.BAD_LOCAL),
    "STEP 전제 — BAD_LOCAL 의 어떤 항목도 이제 \"@\" 를 포함하지 않는다"
    "(local part 는 정의상 \"@\" 를 못 담으므로, 담고 있으면 죽은 데이터다)",
    CE.BAD_LOCAL)

for dom in ("example.org", "example.net", "example.com", "example.co.kr"):
    addr = f"webmaster@{dom}"
    html = f"<html><body>담당자: {addr} 로 문의하세요.</body></html>"
    found = CE.pick_emails(html, "somesite.co.kr")
    chk(addr not in found,
        f"★★★★★ pick_emails() 가 플레이스홀더 {addr} 를 더 이상 '찾음'으로 돌려주지 않는다",
        found)
    why = is_junk(addr, "https://somesite.co.kr")
    chk(bool(why),
        f"★★★★ clean_collected_emails.is_junk() 도 사후 정리에서 {addr} 를 잡아낸다",
        why)

REAL = "webmaster@r514realcompany.co.kr"
html_real = f"<html><body>담당자: {REAL} 로 문의하세요.</body></html>"
chk(REAL in CE.pick_emails(html_real, "r514realcompany.co.kr"),
    "★★★★★ 과잉차단 아님 — 실제 업체 도메인의 webmaster@ 주소는 그대로 수집된다",
    CE.pick_emails(html_real, "r514realcompany.co.kr"))
chk(is_junk(REAL, "https://r514realcompany.co.kr") is None,
    "★★★★★ 과잉차단 아님 — is_junk() 도 실제 업체 주소는 정상으로 본다")

# ══════════════════════════════════════════════════════════════
print("\n[3] 회귀 없음 — round299 가 세운 BAD_LOCAL 경계는 그대로다")
# ──────────────────────────────────────────────────────────────
chk(CE._bad_local_word_in("latest", CE.BAD_LOCAL) is None,
    "STEP 'latest' 는 여전히 안 걸린다(부분열 오탐 없음)")
chk(CE._bad_local_word_in("contest", CE.BAD_LOCAL) is None,
    "STEP 'contest' 는 여전히 안 걸린다(부분열 오탐 없음)")
chk(CE._bad_local_word_in("test", CE.BAD_LOCAL) == "test",
    "STEP 'test' 단독은 여전히 걸린다")
chk(CE._bad_local_word_in("no-reply", CE.BAD_LOCAL) is not None,
    "STEP 'no-reply' 는 여전히 걸린다")
chk(CE._bad_local_word_in("info", CE.BAD_LOCAL) is None,
    "STEP BAD_LOCAL 에 없는 정상 단어는 여전히 통과한다")

# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌림-증명 — 이 라운드 이전 데이터로는 실제로 새는지 재현")
# ──────────────────────────────────────────────────────────────
_orig_local, _orig_domain = CE.BAD_LOCAL, CE.BAD_DOMAIN
try:
    CE.BAD_LOCAL = ("example", "yourname", "your-email", "email", "sample", "test",
                    "noreply", "no-reply", "donotreply", "webmaster@example")
    CE.BAD_DOMAIN = tuple(d for d in _orig_domain if d not in ("example.org", "example.net"))
    leaked = CE.pick_emails(
        "<html><body>담당자: webmaster@example.org 로 문의하세요.</body></html>",
        "somesite.co.kr")
    chk(leaked == ["webmaster@example.org"],
        "★★★★★ 옛 데이터(되돌림) — webmaster@example.org 가 실제로 '찾음'으로 샌다"
        "(진짜 결함 재현)", leaked)
    chk(CE._bad_local_word_in("webmaster", CE.BAD_LOCAL) is None,
        "STEP 되돌림 상태에서도 \"webmaster@example\" 항목 자체는 어떤 local part 로도 "
        "못 걸린다는 구조적 불능이 재확인된다(그래서 위 [4] 가 샌다)")
finally:
    CE.BAD_LOCAL, CE.BAD_DOMAIN = _orig_local, _orig_domain
chk(CE.BAD_DOMAIN == _orig_domain and CE.BAD_LOCAL == _orig_local,
    "★★★★★ 복원 확인 — 모듈 속성이 고친(정상) 값으로 되돌아왔다")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
