# -*- coding: utf-8 -*-
"""스캔 454라운드 회귀 — 백업 자가점검(backup_selfcheck.py) 2건.

[1] mode=ro 만으로는 WAL 모드 백업 사본을 열 때 -shm/-wal 사이드카가
    새로 생기고, 그 사이드카는 cmd_backup() 의 icacls 하드닝을 안 받아
    backups/ 폴더의 상속 권한을 그대로 받는다(실측: 운영 backups/의
    실제 .db-shm 파일이 CodexSandboxUsers:(I)(RX) 를 갖고 있었다) —
    mode=ro&immutable=1 로 바꿔 사이드카 생성 자체를 막는다.
[2] manage.py::cmd_backup() 의 icacls 하드닝이 실패해도(계정명 조회
    실패 등) 경고만 찍고 종료코드에 안 남아, 일일백업.bat 의 errorlevel
    검사로는 절대 못 잡는다 — backup_selfcheck.py(에러가 배치의 FAILED
    로 실제로 반영되는 유일한 자리)에 icacls 로 직접 확인하는 검사를
    새로 추가한다.

두 검사 모두 스크래치 전용 임시 디렉터리에서만 실행 — 운영 backups/·
bokguon.db 는 전혀 안 건드림(경로 문자열조차 참조 안 함).
"""
import io
import os
import shutil
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 454라운드 회귀 — 백업 자가점검 icacls·WAL사이드카")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
SRC = io.open(os.path.join(HERE, "deploy", "backup_selfcheck.py"), encoding="utf-8").read()

chk('mode=ro&immutable=1' in SRC,
    "★★★★★ SQLite 연결이 mode=ro 뿐 아니라 immutable=1 도 준다")
chk('def _has_inherited_acl' in SRC,
    "★★★★★ 상속 ACL 감지 함수가 새로 생겼다")
chk('_has_inherited_acl(newest)' in SRC,
    "★★★★★ main() 이 실제로 그 함수를 최신 백업 파일에 대해 부른다")

sys.path.insert(0, os.path.join(HERE, "deploy"))
import backup_selfcheck as BSC  # noqa: E402

# ══════════════════════════════════════════════════════════════
print("\n[2] WAL 사이드카 회피 — 되돌림-증명(옛 mode=ro만 vs 새 immutable=1)")
# ══════════════════════════════════════════════════════════════
_tmp = tempfile.mkdtemp(prefix="round454_wal_")
src_db = os.path.join(_tmp, "wal_source.db")
conn = sqlite3.connect(src_db)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("CREATE TABLE partners(id INTEGER PRIMARY KEY, name TEXT)")
conn.execute("INSERT INTO partners(name) VALUES('테스트업체')")
conn.commit()
conn.close()

old_copy = os.path.join(_tmp, "old_mode_ro_only.db")
shutil.copy2(src_db, old_copy)
before = set(os.listdir(_tmp))
c = sqlite3.connect(f"file:{old_copy}?mode=ro", uri=True)
c.execute("PRAGMA quick_check").fetchone()
c.execute("SELECT COUNT(*) FROM partners").fetchone()
c.close()
after = set(os.listdir(_tmp))
old_created = after - before

new_copy = os.path.join(_tmp, "new_immutable.db")
shutil.copy2(src_db, new_copy)
before2 = set(os.listdir(_tmp))
c2 = sqlite3.connect(f"file:{new_copy}?mode=ro&immutable=1", uri=True)
c2.execute("PRAGMA quick_check").fetchone()
c2.execute("SELECT COUNT(*) FROM partners").fetchone()
c2.close()
after2 = set(os.listdir(_tmp))
new_created = after2 - before2

chk(any(f.endswith(("-shm", "-wal")) for f in old_created),
    "★★★★★ 옛 방식(mode=ro만)은 WAL 사이드카를 실제로 만든다"
    "(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명)", old_created)
chk(not any(f.endswith(("-shm", "-wal")) for f in new_created),
    "★★★★★ 새 방식(immutable=1)은 WAL 사이드카를 안 만든다", new_created)

# ══════════════════════════════════════════════════════════════
print("\n[3] 상속 ACL 감지 — 실제 상속 계층을 스크래치로 재현")
# ══════════════════════════════════════════════════════════════
_acl_dir = tempfile.mkdtemp(prefix="round454_acl_")
#  ⚠ 일반 임시폴더는 (I) 마크가 안 붙는 경우가 있었다(1차 시도에서 직접
#    확인한 자체 함정) — 실제 backups/ 폴더처럼 상속 가능한 ACE를 이
#    스크래치 폴더 자체에 명시로 심어야 자식 파일이 (I) 를 물려받는다.
os.system(f'icacls "{_acl_dir}" /grant "Everyone:(OI)(CI)(RX)" >nul 2>&1')

unhardened = os.path.join(_acl_dir, "unhardened.db")
shutil.copy2(src_db, unhardened)
chk(BSC._has_inherited_acl(unhardened) is True,
    "★★★★★ 상속 권한만 있는 파일은 상속으로 정확히 감지된다")

hardened = os.path.join(_acl_dir, "hardened.db")
shutil.copy2(src_db, hardened)
me = os.environ.get("USERNAME") or ""
os.system(f'icacls "{hardened}" /inheritance:r /grant:r "{me}:(F)" "Administrators:(F)" "SYSTEM:(F)" >nul 2>&1')
chk(BSC._has_inherited_acl(hardened) is False,
    "★★★★★ cmd_backup() 과 같은 방식으로 하드닝된 파일은 상속 없음으로 정확히 감지된다"
    "(과잉경고 아님 대조군)")

# ══════════════════════════════════════════════════════════════
print("\n[4] main() 통합 — 상속된 백업이면 자가점검이 실제로 FAIL 한다")
# ══════════════════════════════════════════════════════════════
_orig_backup_dir = BSC.BACKUP_DIR
_orig_min_bytes = BSC.MIN_BYTES
try:
    BSC.BACKUP_DIR = _acl_dir
    BSC.MIN_BYTES = 0  # 이 검사는 icacls 자체를 시험하는 것이지 파일크기가 아니다
    for f in os.listdir(_acl_dir):
        if f.startswith("bokguon_") is False and f.endswith(".db"):
            os.rename(os.path.join(_acl_dir, f),
                      os.path.join(_acl_dir, "bokguon_" + f))
    rc_unhardened = BSC.main()
    chk(rc_unhardened == 1,
        "★★★★★ 상속된(icacls 미적용) 백업뿐이면 자가점검이 실패(1)로 끝난다"
        "(고치기 전엔 이 경로 자체가 아예 없어 조용히 통과했다)", rc_unhardened)

    for f in list(os.listdir(_acl_dir)):
        if f.startswith("bokguon_unhardened"):
            os.remove(os.path.join(_acl_dir, f))
    rc_hardened = BSC.main()
    chk(rc_hardened == 0,
        "icacls 로 정상 하드닝된 백업만 있으면 자가점검이 통과(0)한다"
        "(과잉차단 아님 대조군)", rc_hardened)
finally:
    BSC.BACKUP_DIR = _orig_backup_dir
    BSC.MIN_BYTES = _orig_min_bytes

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
