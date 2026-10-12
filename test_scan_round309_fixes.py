# -*- coding: utf-8 -*-
"""스캔 309라운드 회귀 — deploy/backup_selfcheck.py(백업이 정말 만들어졌는지
   확인하는 자가점검 도구) 결함 2건 + DEPLOY.md 2장 보강, 이 세션 사상 첫
   정밀조사한 정밀조사 Agent가 발견 — deploy/실테스트_준비절차.md(주 타겟)
   는 228줄 전체를 manage.py·app.py·dispatch.py·notify_popbill.py 등 실제
   코드와 대조해 전부 정확함을 확인(클린). backup_selfcheck.py 는 현재
   유일한 호출자(deploy/일일백업.bat, 윈도 전용)에서는 우연히 두 결함
   모두 안 드러난다(windows_setup.ps1 이 고정경로와 같은 값을 넣고,
   manage.py backup 이 윈도에선 평문 .db 만 남김) — 그래도 실제 결함이고
   리눅스 자동화에 연결되는 순간 바로 발현되므로 고쳤다.

  [1] BACKUP_DIR 이 항상 `<repo>/backups` 로 고정돼 있었다 — 실제 백업을
      쓰는 manage.py._backup_dir() 는 123라운드부터 BOKGUON_BACKUP_DIR 를
      우선하고 없으면 BOKGUON_DB_PATH 기준 디렉터리를 쓰는데(DB 격리와
      백업 출력 격리가 다른 신호에 의존하면 회귀테스트가 운영 backups/ 를
      오염시켰던 사고 때문), 이 스크립트만 그 통일을 안 따라갔다.
      bootstrap.sh 는 실제로 .env 에 BOKGUON_BACKUP_DIR=/var/backups/bokguon
      을 써 넣으므로, 리눅스에서 이 스크립트를 그대로 쓰면 진짜 백업이
      쌓이는 곳과 다른 곳을 보고 "백업이 하나도 없습니다"로 매번 실패한다.
      manage.py 를 통째로 import 하지 않고 같은 두 환경변수만 직접 읽어
      같은 결론을 내도록 수정(독립 실행 도구라는 성격은 유지).
  [2] 파일 필터가 `.db` 만 인정했다 — 리눅스는 gzip 으로 `.db.gz` 를
      남기는데(manage.py 의 cmd_check 자신이 이미 같은 이유로 두 확장자를
      함께 본다), 이 스크립트만 안 따라가 정상 운영 중인 리눅스 서버에서도
      영원히 "0개"로 실패할 뻔했다. `.db.gz` 도 인정하되, sqlite3 가 압축
      파일을 직접 못 여니 그 경우엔 크기·경과만 보고 무결성 검사는
      건너뛴다(조용히 낮추지 않고 화면에 그대로 알림 — manage.py check 의
      기존 선례와 같은 수준).
  ⚠ DEPLOY.md 2장(수동 설치)이 admin 이름으로 관리자를 만드는데, 0장에
    있는 "go-live 가 이 이름을 지운다" 경고가 2장엔 없었다(2장 자체는
    go-live 를 안 불러 그 흐름만 보면 안전하지만, 나중에 이 서버에 go-live
    를 돌리면 함정이 된다) — 같은 경고를 2장에도 추가(회귀 대상 아님,
    순수 문서 보강).

  ⚠ 이 테스트는 진짜 backup_selfcheck.py 를 서브프로세스로, 진짜 sqlite3 로
    만든 유효한 DB 파일·진짜 gzip 압축으로 실제 실행한다. 전부 격리 임시
    디렉터리만 쓰고 실제 backups/·bokguon.db·.env 는 전혀 안 건드린다.

      python test_scan_round309_fixes.py
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
DEPLOY_SRC = read(os.path.join("deploy", "DEPLOY.md"))

print("=" * 72)
print("  스캔 309라운드 회귀 — backup_selfcheck.py 경로고정·gz미인식")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk('BACKUP_DIR = os.path.join(ROOT, "backups")' not in BSC_SRC,
    "★★★★★ BACKUP_DIR 가 더는 무조건 고정 경로가 아니다")
chk('os.environ.get("BOKGUON_BACKUP_DIR")' in BSC_SRC and 'os.environ.get("BOKGUON_DB_PATH")' in BSC_SRC,
    "★★★★★ BOKGUON_BACKUP_DIR·BOKGUON_DB_PATH 두 환경변수를 manage.py 와 "
    "같은 우선순위로 읽는다")
chk('f.endswith(".db") or f.endswith(".db.gz")' in BSC_SRC,
    "★★★★★ 파일 필터가 이제 .db.gz 도 인정한다(고치기 전엔 .db 만)")
chk('endswith(".db.gz")' in BSC_SRC and "무결성" in BSC_SRC and "건너뜁니다" in BSC_SRC,
    "STEP gzip 백업은 무결성 검사를 건너뛴다는 사실을 화면에 그대로 알린다"
    "(조용히 낮추지 않음)")
chk("go-live 를 나중에라도 돌릴" in DEPLOY_SRC,
    "STEP DEPLOY.md 2장에도 admin 이름 경고가 추가됐다")

# ============================================================
print("\n[2] 실행 준비 — 진짜 sqlite3 로 유효한(100KB 넘는) DB 만들기")
# ------------------------------------------------------------


def _make_valid_db(path, n_partners=5):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE partners(id INTEGER PRIMARY KEY, name TEXT)")
    for i in range(n_partners):
        conn.execute("INSERT INTO partners(name) VALUES (?)", (f"P{i}",))
    #  100KB(MIN_BYTES) 를 자연스럽게 넘기려고 진짜 데이터로 채운다
    #  (사후에 바이트를 덧붙이면 유효한 SQLite 파일 구조가 깨진다).
    #  ⚠ 반복 문자("x"*N)는 gzip 이 270배 넘게 압축해 .db.gz 시나리오에서
    #    "진짜 18MB 백업"이 아니라 741바이트짜리로 둔갑했다(실측으로 발견 —
    #    manage.py 의 100KB 기준은 압축 전후 구분이 없는 게 맞다: 실제
    #    운영 백업은 커서 이 경계에 안 걸린다). 압축이 거의 안 되는 무작위
    #    바이트로 바꿔 두 시나리오(평문·gzip) 모두 현실적인 크기가 되게 한다.
    conn.execute("CREATE TABLE _pad(data BLOB)")
    conn.execute("INSERT INTO _pad(data) VALUES (?)", (os.urandom(200000),))
    conn.commit()
    conn.close()


def _run(env):
    return subprocess.run([PY, BACKUP_SELFCHECK], env=env, capture_output=True,
                           text=True, encoding="utf-8", timeout=20)


# ============================================================
print("\n[3] 실행 — BOKGUON_BACKUP_DIR 를 실제로 존중하는가")
# ------------------------------------------------------------
_tmp_a = tempfile.mkdtemp(prefix="round309_backupdir_")
try:
    _make_valid_db(os.path.join(_tmp_a, "bokguon_20260101_030000.db"), n_partners=5)
    env_a = dict(os.environ)
    env_a["BOKGUON_BACKUP_DIR"] = _tmp_a
    env_a.pop("BOKGUON_DB_PATH", None)
    ra = _run(env_a)
    chk(ra.returncode == 0 and "협력업체 5곳" in ra.stdout,
        "★★★★★ BOKGUON_BACKUP_DIR 로 지정한 임의 디렉터리의 진짜 백업을 실제로 찾아"
        " 통과시킨다(고치기 전엔 이 디렉터리를 아예 안 봐서 '백업이 하나도 없습니다'"
        " 실패였다)", (ra.returncode, ra.stdout[-400:], ra.stderr[-300:]))
finally:
    shutil.rmtree(_tmp_a, ignore_errors=True)

# ============================================================
print("\n[4] 실행 — BOKGUON_DB_PATH 기준 폴백도 manage.py 와 같은가")
# ------------------------------------------------------------
_tmp_root_c = tempfile.mkdtemp(prefix="round309_dbpath_")
try:
    _backups_c = os.path.join(_tmp_root_c, "backups")
    os.makedirs(_backups_c)
    _make_valid_db(os.path.join(_backups_c, "bokguon_20260101_030000.db"), n_partners=7)
    env_c = dict(os.environ)
    env_c.pop("BOKGUON_BACKUP_DIR", None)
    env_c["BOKGUON_DB_PATH"] = os.path.join(_tmp_root_c, "bokguon.db")
    rc = _run(env_c)
    chk(rc.returncode == 0 and "협력업체 7곳" in rc.stdout,
        "★★★★★ BOKGUON_BACKUP_DIR 이 없을 때 BOKGUON_DB_PATH 기준 디렉터리(그 "
        "옆의 backups/)를 찾는다 — manage.py._backup_dir() 와 정확히 같은 규칙",
        (rc.returncode, rc.stdout[-400:], rc.stderr[-300:]))
finally:
    shutil.rmtree(_tmp_root_c, ignore_errors=True)

# ============================================================
print("\n[5] 실행 — .db.gz 백업을 실제로 인식하는가(진짜 gzip 압축)")
# ------------------------------------------------------------
_tmp_gz = tempfile.mkdtemp(prefix="round309_gz_")
try:
    _src_db = os.path.join(_tmp_gz, "_source.db")
    _make_valid_db(_src_db, n_partners=3)
    _gz_path = os.path.join(_tmp_gz, "bokguon_20260101_030000.db.gz")
    with open(_src_db, "rb") as f_in, gzip.open(_gz_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    os.remove(_src_db)   # 진짜 백업 디렉터리처럼 .gz 만 남긴다

    env_gz = dict(os.environ)
    env_gz["BOKGUON_BACKUP_DIR"] = _tmp_gz
    env_gz.pop("BOKGUON_DB_PATH", None)
    rgz = _run(env_gz)
    chk(rgz.returncode == 0 and "gzip 백업" in rgz.stdout,
        "★★★★★ .db.gz 백업을 실제로 찾아 통과시킨다(고치기 전엔 필터에 안 걸려"
        " '백업이 하나도 없습니다' 실패 — manage.py check 는 진작 두 확장자를"
        " 함께 봤는데 이 도구만 안 따라갔다)",
        (rgz.returncode, rgz.stdout[-400:], rgz.stderr[-300:]))
finally:
    shutil.rmtree(_tmp_gz, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
