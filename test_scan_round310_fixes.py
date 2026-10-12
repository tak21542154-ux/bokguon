# -*- coding: utf-8 -*-
"""스캔 310라운드 회귀 — deploy/팝빌_연동가이드.md·외부접속_안내.md·
   backup.sh 결함 3건 + 죽은 파일 정리, 이 세션 사상 첫 정밀조사한
   정밀조사 Agent가 발견(실제 발송 자격증명은 이 환경에 전부 비어 있음을
   먼저 확인 후 조사 — 실발송 위험 없음). deploy/실테스트_준비절차.md
   전수대조는 이미 309라운드가 클린으로 확인했고, 이번 조사의 다른 절반인
   deploy/외부접속_안내.md vs 외부공개_안내.md 관계는 상호보완적이고
   모순 없음을 확인(클린). notify_popbill.py 의 바이트기준(90/2000)·
   재시도 3회·outbox 문구 등 팝빌 가이드의 다른 모든 구체적 수치도
   301·280라운드 이후 수정과 전부 일치함을 재확인(클린).

  [1][심각] 팝빌_연동가이드.md 의 .env 복사블록이 값 뒤에 `#` 대신 `←`
      로 설명을 붙여 뒀다 — envload.py 의 실제 파서(python-dotenv 든
      대체파서든)는 `#` 로 시작하는 주석만 인식한다. 그대로 복사해
      붙이면 POPBILL_TEST 값이 문자열 "1"이 아니게 되고, notify_popbill.py
      는 "1"이 아니면 **운영(실발송·과금) 모드**로 읽는다 — 이 가이드가
      막으려던 바로 그 사고를 이 가이드 자신의 복사블록이 만들 수 있었다.
      설명을 `#`으로 시작하는 별도 줄로 옮김(진짜 .env 파일 자신의 관례).
  [2] 외부접속_안내.md 의 "자동 시작 끄기" 안내가 존재하지 않는 파일명
      (`복구온_외부접속_자동시작.bat`)을 가리키고 있었다 — 실제 등록
      스크립트(복구온_외부공개_등록.ps1)는 작업 스케줄러가 기본 경로이고,
      시작프로그램 폴백조차 다른 이름(`복구온_외부공개.lnk`)을 쓴다.
      이 안내를 그대로 따르면 "지웠는데 왜 다시 뜨지" 상태가 된다 —
      같은 문서 바로 위 줄이 이미 정확히 안내하는 중지 배치파일 + 실제
      존재하는 -Remove 스위치로 정정.
  [3] backup.sh 가 보존기간 환경변수 이름을 BOKGUON_BACKUP_KEEP 으로
      읽었다 — bootstrap.sh·windows_setup.ps1 이 .env 에 실제로 써 넣고
      manage.py 도 읽는 표준 이름은 BOKGUON_BACKUP_KEEP_DAYS 다. 이
      스크립트를 실제로 쓰는 운영자가 표준 이름으로 보존기간을 정해도
      조용히 하드코딩 기본값(30일)으로 돌아갔다 — 이름을 통일.
  ⚠ scratch_r171_repro.py(307라운드가 죽은 코드로 확인, 이번 라운드가
    재확인 후 삭제 — 인용된 app.py 줄번호 3곳 전부 이후 라운드들의 편집
    으로 이미 드리프트돼 있어 참고자료로서도 가치가 없었다)를 삭제.
    deploy/backup.sh 자체는 죽은 코드가 아니다 — manage.py 의 자체
    점검(cmd_check)·backup_selfcheck.py(309라운드) 둘 다 이 스크립트가
    남기는 .db.gz 형식을 알고 있는 살아있는 대안이라 삭제하지 않고
    이름만 통일 + DEPLOY.md 에 존재를 문서화(회귀 대상 아님).

  ⚠ [1]은 진짜 설치된 python-dotenv 로 실제 파싱해 검증한다(격리 임시
    파일만 사용, 실제 .env·발송 자격증명은 전혀 안 건드림 — 이 환경엔
    애초에 진짜 팝빌 키가 비어 있음을 조사 단계에서 이미 확인했다).

      python test_scan_round310_fixes.py
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


POPBILL_GUIDE = read(os.path.join("deploy", "팝빌_연동가이드.md"))
EXTERNAL_GUIDE = read(os.path.join("deploy", "외부접속_안내.md"))
BACKUP_SH = read(os.path.join("deploy", "backup.sh"))
DEPLOY_SRC = read(os.path.join("deploy", "DEPLOY.md"))
REGISTER_PS1 = read(os.path.join("deploy", "복구온_외부공개_등록.ps1"))

print("=" * 72)
print("  스캔 310라운드 회귀 — 팝빌가이드 화살표주석·외부접속안내 파일명·backup.sh 변수명")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
_popbill_section = (POPBILL_GUIDE.split(".env 에 넣기")[1].split("패키지 설치")[0]
                    if ".env 에 넣기" in POPBILL_GUIDE and "패키지 설치" in POPBILL_GUIDE else "")
_popbill_fence = _popbill_section.split("```")[1] if _popbill_section.count("```") >= 2 else ""
chk(bool(_popbill_fence) and "←" not in _popbill_fence,
    "★★★★★ 팝빌 가이드의 .env 복사블록(코드펜스) 안에는 더는 화살표(←) 인라인 주석이 없다"
    "(그 위 경고문이 옛 결함을 설명하며 화살표를 인용하는 것은 별개 — 실제로 복사해 붙일 "
    "코드펜스 안쪽만 본다)")
chk("POPBILL_TEST=1\n" in POPBILL_GUIDE and "BOKGUON_NOTIFY_ENABLED=1\n" in POPBILL_GUIDE,
    "STEP 두 값이 이제 한 줄에 값만 온다(설명은 # 로 시작하는 별도 줄)")
chk("복구온_외부접속_자동시작.bat" not in EXTERNAL_GUIDE,
    "★★★★ 외부접속 안내에서 존재하지 않는 옛 파일명이 사라졌다")
chk("복구온_외부공개_중지.bat" in EXTERNAL_GUIDE and "-Remove" in EXTERNAL_GUIDE,
    "★★★★★ 대신 실제로 존재·동작하는 중지 배치파일과 -Remove 스위치를 안내한다")
chk("-Remove" in REGISTER_PS1 and "[switch]$Remove" in REGISTER_PS1,
    "STEP (사전조건) -Remove 스위치가 실제로 그 스크립트에 존재한다")
chk('KEEP_DAYS="${BOKGUON_BACKUP_KEEP:-30}"' not in BACKUP_SH,
    "★★★★ backup.sh 가 더는 틀린 변수 이름(BOKGUON_BACKUP_KEEP)을 안 쓴다")
chk('KEEP_DAYS="${BOKGUON_BACKUP_KEEP_DAYS:-30}"' in BACKUP_SH,
    "★★★★★ backup.sh 가 이제 manage.py·bootstrap.sh 와 같은 표준 이름"
    "(BOKGUON_BACKUP_KEEP_DAYS)을 읽는다")
chk("deploy/backup.sh" in DEPLOY_SRC and ".db.gz" in DEPLOY_SRC,
    "STEP DEPLOY.md 가 이제 backup.sh 의 존재와 용도(gzip 압축 대안)를 문서화한다")
chk(not os.path.isfile(os.path.join(HERE, "scratch_r171_repro.py")),
    "★★★★ scratch_r171_repro.py(307라운드가 죽은코드로 확인한 파일)가 실제로 삭제됐다")

# ============================================================
print("\n[2] 실행 — 진짜 python-dotenv 로 옛/새 .env 블록을 실제 파싱")
# ------------------------------------------------------------
try:
    from dotenv import dotenv_values
    _HAS_DOTENV = True
except ImportError:
    _HAS_DOTENV = False
chk(_HAS_DOTENV, "STEP (사전조건) python-dotenv 가 설치돼 있다 — 이 환경에서 살아있는 경로가 맞다")

OLD_BLOCK = (
    "POPBILL_LINK_ID=발급받은_LinkID\n"
    "POPBILL_SECRET_KEY=발급받은_SecretKey\n"
    "POPBILL_CORP_NUM=6568702554\n"
    "POPBILL_SENDER=사전등록된_발신번호\n"
    "POPBILL_TEST=1            ← 처음엔 반드시 1 (테스트베드)\n"
    "BOKGUON_NOTIFY_ENABLED=1  ← 발송 마스터 스위치\n"
)
_tmpdir = tempfile.mkdtemp(prefix="round310_env_")
try:
    _old_path = os.path.join(_tmpdir, "old.env")
    with open(_old_path, "w", encoding="utf-8") as f:
        f.write(OLD_BLOCK)
    old_vals = dotenv_values(_old_path)
    chk(old_vals.get("POPBILL_TEST") != "1",
        "★★★★★ 대조군 — 옛(화살표) 블록은 실제로 POPBILL_TEST 가 '1'이 아니게 파싱된다"
        "(고쳐야 했던 바로 그 결함 — 이 상태면 notify_popbill.py 가 운영모드로 읽는다)",
        repr(old_vals.get("POPBILL_TEST")))
    chk(old_vals.get("BOKGUON_NOTIFY_ENABLED") != "1",
        "STEP 대조군 — BOKGUON_NOTIFY_ENABLED 도 같은 이유로 '1'이 아니게 파싱된다",
        repr(old_vals.get("BOKGUON_NOTIFY_ENABLED")))

    # 지금 문서에 실제로 있는 새 블록을 그대로 뽑아 검증한다(하드코딩 사본 아님,
    # [1]에서 이미 추출해 둔 코드펜스를 그대로 재사용).
    _new_path = os.path.join(_tmpdir, "new.env")
    with open(_new_path, "w", encoding="utf-8") as f:
        f.write(_popbill_fence)
    new_vals = dotenv_values(_new_path)
    chk(new_vals.get("POPBILL_TEST") == "1",
        "★★★★★ 지금 문서에 실제로 있는(고친) 블록은 POPBILL_TEST 가 정확히 '1'로 파싱된다",
        repr(new_vals.get("POPBILL_TEST")))
    chk(new_vals.get("BOKGUON_NOTIFY_ENABLED") == "1",
        "★★★★★ 같은 블록에서 BOKGUON_NOTIFY_ENABLED 도 정확히 '1'로 파싱된다",
        repr(new_vals.get("BOKGUON_NOTIFY_ENABLED")))
    chk(new_vals.get("POPBILL_CORP_NUM") == "6568702554",
        "STEP 대조군 — 원래도 문제없던 값(POPBILL_CORP_NUM)은 회귀 없이 그대로 파싱된다",
        repr(new_vals.get("POPBILL_CORP_NUM")))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드310 [2] .env 파싱 실측", f"{type(e).__name__} {e}")
finally:
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

# ============================================================
print("\n[3] 실행 — backup.sh 문법 확인(Git Bash, 실행은 안 함)")
# ------------------------------------------------------------
_bash = r"C:\Program Files\Git\bin\bash.exe"
if os.path.isfile(_bash):
    r = subprocess.run([_bash, "-n", os.path.join(HERE, "deploy", "backup.sh")],
                        capture_output=True, text=True, timeout=15,
                        encoding="utf-8", errors="replace")
    chk(r.returncode == 0, "★★★★ backup.sh 가 여전히 유효한 bash 문법이다(-n, 실행 없음)",
        (r.returncode, r.stderr[-300:]))
else:
    print("  [건너뜀] Git Bash 를 찾지 못해 문법 검사를 생략합니다")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
