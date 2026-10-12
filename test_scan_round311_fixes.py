# -*- coding: utf-8 -*-
"""스캔 311라운드 회귀 — deploy/일일백업.bat·backup.sh 계열 백업 하위체계의
   교차 프로세스 결함 2건, 이 세션 사상 첫 정밀조사한 정밀조사 Agent가
   발견 — deploy/일일백업.bat 자체(순서·에러전파·로그기록)와
   static/actions.js(이벤트위임 디스패처)는 전체를 정밀대조해 전부
   정확·클린임을 확인. bokguon.service 의 ReadWritePaths 가 systemd 샌드박스
   때문에 백업 쓰기를 막을 것이라는 최초 가설은 틀렸음도 직접 추적해서
   확인(백업은 애초에 systemd 유닛 안에서 안 돈다, cron 이 별도로 돈다) —
   그 추적 과정에서 아래 [2]의 진짜 결함을 찾았다.

  [1] `deploy/backup_selfcheck.py` 가 309라운드에서 BOKGUON_BACKUP_DIR·
      BOKGUON_DB_PATH 두 환경변수를 직접 읽도록 고쳐졌지만, **그 값이
      어디서 오는지**를 놓쳤다 — 유일한 실제 호출자 deploy/일일백업.bat
      는 이 스크립트를 manage.py backup 과 **서로 다른 프로세스**로
      부른다. manage.py 는 자기 안에서 envload.load_dotenv() 로 .env 를
      읽지만 그건 그 프로세스 자신의 os.environ 에만 반영되고, 형제
      프로세스(이 스크립트)나 그걸 부른 .bat 자체의 환경에는 전혀 안
      남는다(OS 프로세스 격리상 당연한 결과 — 자식이 부모나 형제의
      환경변수를 사후에 바꿀 수 없다). .bat 자신도 BOKGUON_BACKUP_DIR
      을 안 읽으므로, 이 스크립트는 .env 에 뭐라 적혀 있든 항상 자기
      fallback 경로만 봤다(윈도는 그 fallback 과 windows_setup.ps1 의
      기본값이 우연히 같아 지금까지 안 드러났다 — 커스터마이즈하는
      순간부터 영원한 거짓 실패가 시작된다). envload.py 는 manage.py
      와 달리 .env 로드 말고는 부작용이 없으므로(DB 를 안 열고 앱을
      안 띄운다) 이 스크립트도 그 공유 로더를 직접 불러 스스로 .env 를
      읽게 한다(envload.py 자신의 docstring 이 이미 "app.py/wsgi.py/
      serve_waitress.py/manage.py 전부가 공유한다"고 적어 뒀는데 이
      스크립트만 그 목록 밖에 있었다).
  [2] bootstrap.sh 6단계의 sed 치환에 `/var/backups/bokguon` → 커스텀
      BOKGUON_BACKUP_DIR 규칙이 빠져 있었다 — 설치 시 이 값을 커스텀
      경로로 주면(30행이 이미 그 값으로 실제 디렉터리를 만드는데)
      bokguon.service 의 ReadWritePaths 줄만 하드코딩된 기본값 그대로
      나간다. ReadWritePaths 는 나열된 경로가 기동 시점에 없으면(그 파일
      자신의 주석이 이미 문서화) systemd 가 유닛 자체를 안 띄운다 —
      백업만 실패하는 게 아니라 **서비스 전체**가 기동 실패한다(다행히
      바로 다음 줄이 systemctl is-active 로 확인해 죽지 않고 크게 알리긴
      한다). 기존 3개 치환과 같은 패턴으로 규칙 하나만 추가.

  ⚠ [1]은 진짜 envload.py·진짜 backup_selfcheck.py 를 실제 서브프로세스로
    실행해 검증한다(격리된 가짜 .env 파일만 사용, 실제 .env 는 전혀 안
    건드림 — runpy 로 envload._ENV_PATH 를 그 가짜 파일로 먼저 바꿔치기한
    뒤 backup_selfcheck.py 를 __main__ 처럼 그대로 실행). [2]는 bash 문법
    검사(Git Bash -n, 실행 없음)와 sed 규칙 자체를 실제로 돌려 정확성을
    확인한다(실제 systemd 는 이 환경에 없다).

      python test_scan_round311_fixes.py
"""
import gzip
import io
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
BACKUP_SELFCHECK = os.path.join(HERE, "deploy", "backup_selfcheck.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


BSC_SRC = read(os.path.join("deploy", "backup_selfcheck.py"))
BOOTSTRAP_SRC = read(os.path.join("deploy", "bootstrap.sh"))

print("=" * 72)
print("  스캔 311라운드 회귀 — backup_selfcheck.py .env 미로드·bootstrap.sh sed 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk("import envload" in BSC_SRC and "envload.load_dotenv()" in BSC_SRC,
    "★★★★★ backup_selfcheck.py 가 이제 공유 .env 로더(envload)를 직접 불러 스스로 로드한다")
chk("sys.path.insert(0, ROOT)" in BSC_SRC and "import envload" in BSC_SRC
    and BSC_SRC.index("sys.path.insert(0, ROOT)") < BSC_SRC.index("import envload"),
    "STEP sys.path 에 저장소 루트를 먼저 넣은 뒤에 envload 를 import 한다"
    "(envload.py 는 deploy/ 가 아니라 그 한 단계 위에 있다)")
chk('-e "s#/var/backups/bokguon#$BACKUP_DIR#g"' in BOOTSTRAP_SRC,
    "★★★★★ bootstrap.sh 가 이제 ReadWritePaths 의 백업 경로도 커스텀 값으로 치환한다"
    "(고치기 전엔 이 규칙이 없어 커스텀 설치 시 서비스 기동 자체가 실패할 수 있었다)")

# ============================================================
print("\n[2] 실행 준비 — 진짜 sqlite3 로 유효한 백업 DB 만들기(무작위 바이트로 채움 — "
      "반복 문자는 없음, 이번엔 gzip 안 쓰므로 상관없지만 관례를 맞춘다)")
# ------------------------------------------------------------


def _make_valid_db(path, n_partners=4):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE partners(id INTEGER PRIMARY KEY, name TEXT)")
    for i in range(n_partners):
        conn.execute("INSERT INTO partners(name) VALUES (?)", (f"P{i}",))
    conn.execute("CREATE TABLE _pad(data BLOB)")
    conn.execute("INSERT INTO _pad(data) VALUES (?)", (os.urandom(150000),))
    conn.commit()
    conn.close()


# ============================================================
print("\n[3] 실행 — 격리된 .env 파일의 BOKGUON_BACKUP_DIR 을 실제로 읽는가"
      "(일일백업.bat 와 똑같이: 이 프로세스 환경변수엔 안 심고, .env 파일로만 준다)")
# ------------------------------------------------------------
_tmp = tempfile.mkdtemp(prefix="round311_envfile_")
try:
    _custom_backup_dir = os.path.join(_tmp, "custom_backups")
    os.makedirs(_custom_backup_dir)
    _make_valid_db(os.path.join(_custom_backup_dir, "bokguon_20260101_030000.db"), n_partners=6)

    _fake_env = os.path.join(_tmp, "fake.env")
    with open(_fake_env, "w", encoding="utf-8") as f:
        f.write(f"BOKGUON_BACKUP_DIR={_custom_backup_dir}\n")

    _wrapper = os.path.join(_tmp, "_wrapper.py")
    with open(_wrapper, "w", encoding="utf-8") as f:
        f.write(
            "import sys, runpy\n"
            f"sys.path.insert(0, {HERE!r})\n"
            "import envload\n"
            f"envload._ENV_PATH = {_fake_env!r}\n"
            "sys.argv = ['backup_selfcheck.py']\n"
            f"runpy.run_path({BACKUP_SELFCHECK!r}, run_name='__main__')\n"
        )

    env = dict(os.environ)
    env.pop("BOKGUON_BACKUP_DIR", None)   # ★ 프로세스 환경변수로는 절대 안 준다 — .env 파일로만
    env.pop("BOKGUON_DB_PATH", None)
    r = subprocess.run([PY, _wrapper], env=env, capture_output=True,
                        text=True, encoding="utf-8", timeout=20)
    chk(r.returncode == 0 and "협력업체 6곳" in r.stdout,
        "★★★★★ .env 파일에만 적힌 BOKGUON_BACKUP_DIR 을 실제로 읽어 그 디렉터리의 "
        "진짜 백업을 찾아 통과시킨다(고치기 전엔 envload 를 안 불러 이 파일을 전혀 "
        "몰랐고, 일일백업.bat 가 실제로 부르는 방식 그대로 재현해도 항상 자기 "
        "fallback 경로만 봐서 '백업이 하나도 없습니다'로 실패했다)",
        (r.returncode, r.stdout[-500:], r.stderr[-400:]))
finally:
    shutil.rmtree(_tmp, ignore_errors=True)

# ============================================================
print("\n[4] 실행 — bootstrap.sh 문법 확인 + 새 sed 규칙이 실제로 치환하는가(Git Bash)")
# ------------------------------------------------------------
_bash = r"C:\Program Files\Git\bin\bash.exe"
if os.path.isfile(_bash):
    r = subprocess.run([_bash, "-n", os.path.join(HERE, "deploy", "bootstrap.sh")],
                        capture_output=True, text=True, timeout=15,
                        encoding="utf-8", errors="replace")
    chk(r.returncode == 0, "★★★★ bootstrap.sh 가 여전히 유효한 bash 문법이다(-n, 실행 없음)",
        (r.returncode, r.stderr[-300:]))

    # sed 규칙 자체가 실제로 원하는 치환을 하는지, 진짜 sed 로 실행해 확인한다.
    _tmp2 = tempfile.mkdtemp(prefix="round311_sed_")
    try:
        _svc_in = os.path.join(_tmp2, "in.service")
        with open(_svc_in, "w", encoding="utf-8") as f:
            f.write("WorkingDirectory=/opt/bokguon\n"
                    "ReadWritePaths=/opt/bokguon\n"
                    "ReadWritePaths=/var/backups/bokguon\n")
        _svc_out = os.path.join(_tmp2, "out.service")
        _sed_cmd = (
            'sed -e "s#/opt/bokguon#/custom/app#g" -e "s#User=bokguon#User=svcuser#" '
            '-e "s#Group=bokguon#Group=svcuser#" -e "s#/var/backups/bokguon#/mnt/nas/bk#g" '
            f'"{_svc_in}" > "{_svc_out}"'
        ).replace("\\", "/")
        rs = subprocess.run([_bash, "-c", _sed_cmd], capture_output=True, text=True, timeout=15,
                             encoding="utf-8", errors="replace")
        out_content = io.open(_svc_out, encoding="utf-8").read() if os.path.isfile(_svc_out) else ""
        chk(rs.returncode == 0 and "ReadWritePaths=/mnt/nas/bk" in out_content
            and "/var/backups/bokguon" not in out_content,
            "★★★★★ 새 sed 규칙을 실제로(진짜 sed 로) 돌리면 ReadWritePaths 의 백업 경로가 "
            "커스텀 값으로 정확히 치환된다(WorkingDirectory 의 /opt/bokguon 치환과 서로 "
            "간섭하지 않음도 함께 확인)", (rs.returncode, out_content))
        chk("WorkingDirectory=/custom/app" in out_content,
            "STEP 대조군 — 기존 /opt/bokguon 치환도 회귀 없이 그대로 동작한다", out_content)
    finally:
        shutil.rmtree(_tmp2, ignore_errors=True)
else:
    print("  [건너뜀] Git Bash 를 찾지 못해 문법·sed 검사를 생략합니다")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
