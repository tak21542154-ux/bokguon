# -*- coding: utf-8 -*-
"""스캔 313라운드 회귀 — crypto_util.py 의 '키 완전부재' 경고가 실제로는 매번이 아니라
   프로세스당 딱 1번만 뜨고 그 뒤로 영구 침묵하던 결함, 이 세션 사상 첫 정밀조사한
   정밀조사 Agent가 발견.

   _load_key() 의 개발용 고정키 대체 분기(주석 자신이 "매번 경고를 남긴다"고 명시)가
   warnings.warn() 을 썼다 — 파이썬 warnings 모듈의 기본 필터는 (메시지·카테고리·
   호출지점) 조합을 프로세스 생애 동안 기억해 콜사이트당 딱 1번만 출력한다. app.py 의
   계좌 저장 라우트는 encrypt() 와 blind_index() 를 같은 줄에서 반복 호출하므로, 키가
   완전히 빠진 채 서버가 떠 있으면 최초 협력사 1곳이 계좌를 등록하는 순간에만 경고가
   뜨고 그 뒤 수백 곳이 등록되는 내내 조용히 개발용 고정키로 계속 암호화됐다. 이 파일의
   다른 두 경고(라운드261 형식오류·라운드120 복호화실패)는 이미 _log.warning() 을
   쓰는데(로깅은 이런 자동 중복제거가 없음) 이 자리만 안 따라갔다 — 통일해서 고쳤다.

   실제 warnings 모듈 기본필터로 옛 동작(1회만 기록)을 재현하고, 실제 crypto_util 을
   그대로 불러 logging 채널로 매 호출 기록되는지 실측한다.
"""
import io
import logging
import os
import sys
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PASS = FAIL = 0
FAILED = []


def chk(cond, msg, detail=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {msg}")
    else:
        FAIL += 1
        FAILED.append(msg)
        print(f"  [FAIL] {msg}" + (f"   {detail}" if detail else ""))


print("=" * 74)
print("  스캔 313라운드 회귀 — crypto_util.py 키 완전부재 경고가 1회만 뜨던 결함")
print("=" * 74)

print("\n[1] 소스 확인")
SRC = io.open(os.path.join(HERE, "crypto_util.py"), encoding="utf-8").read()
_dev_section_start = SRC.index("# 개발 편의용 고정 키")
_dev_section_end = SRC.index("\ndef encrypt(", _dev_section_start)
DEV_BRANCH = SRC[_dev_section_start:_dev_section_end]
#  ⚠ 새 코드 자신의 설명주석이 옛 API 이름(warnings.warn)을 문장으로 인용하므로
#    그 문자열만 찾으면 주석 속 인용과 실제 코드를 못 가른다 — 실제 사용 여부는
#    "import warnings" 줄 자체의 존재로 판별한다(고친 뒤엔 이 줄도 함께 지웠다).
chk("import warnings" not in DEV_BRANCH,
    "★★★★★ 개발용 고정키 대체 분기가 더는 warnings 모듈을 쓰지 않는다"
    "(그 모듈의 기본필터는 콜사이트당 1회만 기록해 '매번'이라는 주석과 어긋났다)")
chk("_log.warning(" in DEV_BRANCH,
    "★★★★★ 대신 이 파일의 다른 두 경고(라운드120·261)와 같은 _log.warning() 을 쓴다"
    "(로깅 채널은 위치 기반 자동 중복제거가 없어 호출마다 확실히 남는다)")

print("\n[2] 실행 준비 — 키 완전부재 상태 구성(BOKGUON_ENC_KEY 미설정 · BOKGUON_ENV=dev)")
os.environ.pop("BOKGUON_ENC_KEY", None)
os.environ.pop("BOKGUON_INDEX_KEY", None)
os.environ["BOKGUON_ENV"] = "dev"
import crypto_util as CU  # noqa: E402  (환경변수를 먼저 정한 뒤에 import 순서는 무관 — _load_key 가 매 호출마다 os.environ 을 다시 읽는다)

print("\n[3] 실행 — 파이썬 warnings 모듈 '기본 필터'로 옛(반증용) 동작을 실제로 재현")
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("default")
    for _ in range(5):
        warnings.warn("[대조군] 콜사이트당 1회만 기록되는 것을 보여주는 자리표시자 경고",
                       RuntimeWarning, stacklevel=1)
chk(len(caught) == 1,
    "★★ (대조군) 파이썬 기본 경고필터는 같은 자리에서 5번 warn() 해도 1건만 기록한다"
    "(수정 전 crypto_util.py 가 이 채널에 의존했던 이유를 실측으로 확인)",
    len(caught))

print("\n[4] 실행 — 실제 crypto_util.encrypt() 를 같은 줄에서 5회 호출, logging 호출 횟수 실측")
warn_calls = []
CU._log.warning = lambda *a, **k: warn_calls.append((a, k))  # 실제 logging 인프라를 거치지 않고 호출 횟수만 센다
for _ in range(5):
    CU.encrypt("계좌테스트123")
chk(len(warn_calls) == 5,
    "★★★★★ encrypt() 를 같은 줄에서 5회 호출하면 경고가 정확히 5회(매번) 기록된다"
    "(고치기 전엔 warnings 모듈 기본필터에 걸려 1회만 기록되고 나머지 4회는 완전 침묵했다)",
    len(warn_calls))

print("\n[5] 실행 — blind_index() 의 BOKGUON_INDEX_KEY 부재 경고도 동일하게 매번 기록되는가")
warn_calls.clear()
for _ in range(3):
    CU.blind_index("110-234-567890")
chk(len(warn_calls) == 3,
    "★★★ blind_index() 도 같은 _load_key() 를 공유하므로 3회 호출 시 경고 3회(매번) 기록",
    len(warn_calls))

print("\n[6] 실행 — 정상 키가 있으면(형식도 맞으면) 경고가 아예 안 뜬다(회귀 없음)")
os.environ["BOKGUON_ENC_KEY"] = "uqQT4f0GntVYnZMaEBg0aQdI1paT_YLDmaGHunvqb7Y="
warn_calls.clear()
tok = CU.encrypt("계좌테스트456")
chk(len(warn_calls) == 0 and tok.startswith("v1:"),
    "★★ 정상 형식의 실제 키가 있으면 암호화는 되고 경고는 안 뜬다", (len(warn_calls), tok[:10]))
chk(CU.decrypt(tok) == "계좌테스트456",
    "★★ 같은 키로 왕복 복호화가 정상 동작한다(회귀 없음)")
os.environ.pop("BOKGUON_ENC_KEY", None)

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
