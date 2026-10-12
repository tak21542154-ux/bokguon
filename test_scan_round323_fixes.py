# -*- coding: utf-8 -*-
"""스캔 323라운드 회귀 — deploy\\bokguon.service(Linux systemd 유닛, 현재는
   미사용 대안 배포경로 — 실제 운영은 이 개발기에서 serve_waitress.py 직접
   실행 중) 네트워크 하드닝 주석이 실제로 안 하는 일을 한다고 주장하던 결함,
   이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — deploy/ 폴더 전체
   20개 파일 중 이 파일만 311라운드가 ReadWritePaths(쓰기경로) 한 줄만
   훑고 몇 줄 아래 네트워크 하드닝 블록은 어느 라운드도 안 건드렸음을
   run_all_tests.py 전수 재구성으로 확인.

   [경미~중간, 오인] 63~65행 주석이 "로컬 소켓과 IPv4/IPv6 만... 외부
   바인딩은 불필요"라고 적어 마치 이 두 줄이 아웃바운드를 막는 것처럼
   보이지만, systemd 공식문서(freedesktop.org systemd.resource-control(5))
   기준으로 실제로는:
     · RestrictAddressFamilies 는 소켓 프로토콜군(어떤 종류의 소켓을 만들
       수 있는가)만 제한 — 목적지 주소는 전혀 안 본다. AF_INET/AF_INET6를
       허용목록에 넣은 시점에 인터넷 전체로 나가는 길이 열려 있다.
     · IPAddressAllow=는 IPAddressDeny=any 와 짝을 이뤄야만 화이트리스트로
       동작 — 그 짝이 없으면(이 파일엔 없음) 이 유닛엔 IP 필터링이 전혀
       안 걸려 있는 것과 같다("Otherwise, access is granted"가 매칭
       안 되는 트래픽의 기본 결과).
   즉 이 3줄은 침해된 프로세스가 이상한 프로토콜로 소켓을 만드는 것만
   막을 뿐, 외부로 나가는 연결은 전혀 안 막는다 — 보안 하드닝 블록 안에
   있어 "이미 제한돼 있다"는 착각을 주기 쉽다(311라운드가 같은 파일의
   바로 위 ReadWritePaths만 보고 지나간 이유이기도 할 것). 실제로
   아웃바운드를 제한하려면 IPAddressDeny=any + 팝빌 등 실제 호출하는
   외부 API의 IP를 IPAddressAllow=에 명시해야 하는데, 그 IP 목록을
   미리 확정하는 건 운영 판단이 필요하고 잘못 좁히면 알림 발송이 커널
   단에서 조용히 끊기므로(애플리케이션 로그 없음) 이번 라운드는 실제
   동작 변경 없이 주석을 사실대로 정정하는 데 그친다.

   이 파일은 systemd 유닛(텍스트 설정)이라 이 개발기(Windows)에서
   "실행"해 검증할 수 없다 — systemd 공식문서 자체가 근거이므로, 이
   회귀테스트는 (a) 오해를 유발하던 옛 문구가 사라졌는지, (b) 정정된
   설명이 실제로 들어있는지, (c) 그 정정이 근거로 삼는 사실(이 파일에
   IPAddressDeny 지시문이 실제로 없다 — 있었다면 설명이 달라져야 함)이
   지금도 유효한지를 정적으로 확인한다.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SVC_PATH = os.path.join(HERE, "deploy", "bokguon.service")

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
print("  스캔 323라운드 회귀 — bokguon.service 네트워크 하드닝 주석 오인 정정")
print("=" * 74)

with open(SVC_PATH, "r", encoding="utf-8") as f:
    src = f.read()

print("\n[1] 옛(오인 유발) 문구가 더는 없다")
chk("외부 바인딩은 불필요" not in src,
    "★★★★ 마치 아웃바운드가 막힌 것처럼 읽히던 옛 문구가 사라졌다")

print("\n[2] 정정된 설명이 실제로 들어있다")
chk("아웃바운드" in src and "뜻이 아니다" in src,
    "★★★★★ '아웃바운드를 막는다는 뜻이 아니다'류의 정정 문구가 있다")
chk("IPAddressDeny" in src,
    "★★★★ IPAddressDeny=any 와 짝을 이뤄야 화이트리스트로 동작한다는 설명이 있다")
chk("RestrictAddressFamilies 는 소켓 프로토콜군" in src or
    "소켓 프로토콜군" in src,
    "RestrictAddressFamilies가 프로토콜군만 제한한다는 설명이 있다")

print("\n[3] 정정된 설명이 근거로 삼는 사실이 지금도 유효하다"
      "(실제 IPAddressDeny 지시문이 파일에 없다 — 있으면 설명을 다시 써야 함)")
directive_lines = [ln for ln in src.splitlines()
                    if re.match(r"^\s*IPAddressDeny\s*=", ln)]
chk(len(directive_lines) == 0,
    "실제 IPAddressDeny= 지시문 줄은 아직 없다(주석의 '짝이 없다' 서술과 일치)",
    directive_lines)

print("\n[4] 원래 지시문 두 줄은 그대로 살아있다(삭제 사고 방지)")
chk(re.search(r"^\s*RestrictAddressFamilies\s*=\s*AF_INET AF_INET6 AF_UNIX\s*$", src, re.M) is not None,
    "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX 줄이 그대로 있다")
chk(re.search(r"^\s*IPAddressAllow\s*=\s*localhost\s*$", src, re.M) is not None,
    "IPAddressAllow=localhost 줄이 그대로 있다")

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
