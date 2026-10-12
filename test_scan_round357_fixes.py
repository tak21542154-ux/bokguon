# -*- coding: utf-8 -*-
"""
357라운드 회귀 — deploy/windows_setup.ps1(윈도 메인 설치 스크립트)가
manage.py sweep(입찰 마감·출동 기한·완료보고 독촉·문자/알림톡 실발송)
예약 등록을 아예 안 하던 결함[중간, 신규 배포 시 서비스가 반쯤 죽은
채로 뜸 — 이 PC 자체는 별도 수동조치로 이미 정상].

  배경: bootstrap.sh(리눅스, 276행)는 `*/5 * * * * ... manage.py sweep`을
  직접 등록하는데, 그 바로 옆 주석(275행)이 "윈도 배포는 복구온_예약실행_
  등록.ps1 이 같은 일을 한다"고 적어 뒀다 — 그런데 windows_setup.ps1(윈도의
  '메인' 설치 스크립트, DEPLOY.md 가 안내하는 그 스크립트)은 정작 그
  스크립트를 부르지 않았다. 그 별도 스크립트(복구온_예약실행_등록.ps1)
  자신의 6~15행이 이미 "실제로 이 PC에 등록이 없었고, 그 상태로는 팝빌
  키를 넣어도 문자가 안 나간다"는 과거 실제 사고를 기록해 뒀다 — 즉
  windows_setup.ps1 하나만 보고 새 윈도 서버에 처음 배포하면 이 사고가
  그대로 재현된다(manage.py check 는 통과해도 서비스는 반쯤 죽는다).

  조사 Agent가 함께 지목한 "환경변수 명명 불일치"(BOKGUON_HOST/PORT
  vs BOKGUON_BIND)는 독립검증 결과 오판으로 제외 — windows_setup.ps1
  자신의 5~6행이 이미 "윈도 전용, 리눅스는 bootstrap.sh 를 쓴다"고
  명시하고, 실제로 윈도는 serve_waitress.py(BOKGUON_HOST/PORT 를 읽음),
  리눅스는 gunicorn_conf.py(BOKGUON_BIND 를 읽음)로 **서로 다른 WSGI
  서버**를 쓰므로 각 스크립트가 자기 플랫폼의 서버가 읽는 변수를 정확히
  맞춰 쓰는 것이 옳다 — 두 스크립트를 뒤섞어 쓰는 시나리오 자체가
  성립하지 않는다.

  고침: windows_setup.ps1 안에 등록 로직을 새로 베끼지 않고(그러면 이미
  잘 만들어진 복구온_예약실행_등록.ps1 의 중복작업 감지(.bat 내용까지
  검사, 126라운드)·등록 후 실제 조회 확인(121~124행) 로직과 따로 노는
  두 번째 구현이 생긴다), 그 스크립트를 그대로 호출하도록 한 줄 추가 —
  단일 관문 원칙을 유지한다. 실패해도(예: 이 PC처럼 '복구온_경매마감'이
  이미 돌고 있어 중복감지로 정확히 실패하는 경우) 경고로만 낮춰 나머지
  설치 단계를 막지 않는다.

  이 파일은 app.py 가 import 하지 않는 배포 스크립트라 재기동·BUILD_HASH
  와 무관 — 순수 정적 텍스트 대조로 검증한다(300·306라운드류와 같은
  검증한계, PowerShell 을 실행하지 않고 파일 내용만 확인 — 292라운드가
  이미 경고한 대로 실제 스케줄러 API 를 테스트에서 부르지 않는다).
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS = FAIL = 0


def chk(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f"   {detail}" if detail else ""))


def read(rel):
    with io.open(os.path.join(HERE, rel), encoding="utf-8") as f:
        return f.read()


print("=" * 72)
print("  스캔 357라운드 회귀 — windows_setup.ps1 스윕 예약 위임 호출")
print("=" * 72)

WIN_SETUP = read(os.path.join("deploy", "windows_setup.ps1"))
BOOTSTRAP = read(os.path.join("deploy", "bootstrap.sh"))
SWEEP_REG = read(os.path.join("deploy", "복구온_예약실행_등록.ps1"))

print("\n[1] windows_setup.ps1 — 스윕 위임 호출이 실제로 있는가")
#  ⚠ 이 파일엔 211행에 296라운드가 이미 남긴, 파일명만 언급하는 옛 주석이
#    있다(이번 수정과 무관) — 그보다 뒤에 있는, 실제 변수 대입(`$sweepScript =`)
#    지점을 앵커로 잡아야 이번에 새로 넣은 실제 호출부를 정확히 짚는다.
i_var = WIN_SETUP.find('$sweepScript = Join-Path')
chk(i_var != -1,
    "★★★★★ windows_setup.ps1 이 복구온_예약실행_등록.ps1 경로를 변수로 잡는다")
# "& $sweepScript" 형태의 실제 호출문이 있는지(단순 언급이 아니라 실행)
call_section = WIN_SETUP[max(0, i_var - 100):i_var + 500]
chk("& $sweepScript" in call_section or "&$sweepScript" in call_section,
    "★★★★★ 단순 언급이 아니라 실제로 & 호출연산자로 실행한다")
chk("try {" in call_section and "catch" in call_section,
    "★★★★ 실패해도(중복 스윕 감지 등) try/catch 로 감싸 나머지 설치를 막지 않는다")
chk("Test-Path $sweepScript" in WIN_SETUP or "Test-Path" in call_section,
    "★★★ 스크립트 파일 존재 여부를 먼저 확인한다(없으면 경고만)")

print("\n[2] 형제 파일 대조 — 새 등록 로직을 windows_setup.ps1 안에 다시 베끼지 않았다")
chk("New-ScheduledTaskAction" not in call_section,
    "★★★★ windows_setup.ps1 자신은 스케줄 등록 API를 직접 다시 안 부른다"
    "(단일 관문 — 복구온_예약실행_등록.ps1 에게 위임)")

print("\n[3] 대조군 — 기존 4개 작업(백업·사진백업·접속기록·개인정보파기) 등록은 회귀 없다")
for name, marker in [
    ("DB 백업", "복구온_DB백업"),
    ("사진 백업", "복구온_사진백업"),
    ("접속기록 정리", "복구온_접속기록정리"),
    ("개인정보 파기", "복구온_개인정보파기"),
]:
    chk(marker in WIN_SETUP, f"  {name} 작업 등록 블록이 그대로 남아 있다({marker})")

print("\n[4] 참고 확인 — bootstrap.sh 의 sweep 등록·주석은 그대로(비교 기준)")
chk("manage.py sweep" in BOOTSTRAP, "  bootstrap.sh 자신의 sweep cron 등록은 그대로")
chk("복구온_예약실행_등록.ps1" in BOOTSTRAP,
    "  bootstrap.sh 주석이 가리키는 파일명과 이번에 호출한 파일명이 일치한다"
    "(오타로 다른 파일을 부르지 않았는지 교차확인)")
chk("manage.py sweep" in SWEEP_REG,
    "  실제로 호출한 그 파일 자신도 manage.py sweep 을 등록하는 파일이 맞다"
    "(파일명만 맞고 내용이 다른 엉뚱한 파일이 아닌지 확인)")

print(f"\n{'=' * 72}\n  통과 {PASS} · 실패 {FAIL}\n{'=' * 72}")
sys.exit(1 if FAIL else 0)
