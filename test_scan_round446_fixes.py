# -*- coding: utf-8 -*-
"""스캔 446라운드 회귀 — 백업/복구 관련 결함 2건. 정밀조사 Agent가
   각도1(DB 백업의 실제 복구 가능성)에서 발견, 둘 다 실제 재현으로 확인:

   [1] `cmd_restore()`(manage.py:1350-)가 파일 무결성(PRAGMA integrity_
   check)만 확인하고, **지금 .env의 BOKGUON_ENC_KEY로 이 DB 안의 암호화된
   계좌정보를 실제로 열 수 있는지**는 전혀 확인하지 않았다. `cmd_check()`
   (246-265행)는 이미 이 왕복확인 로직을 갖고 있는데, 정작 키가 안 맞을
   위험이 가장 큰 순간(다른 서버·다른 .env로 복구하는 바로 그 시점)엔
   아무도 그 검사를 부르지 않았다 — 실측: 다른 키로 암호화된 백업을
   복구하면 무결성 검사까지 전부 "정상"으로 통과하고, 계좌정보는
   crypto_util.decrypt()가 실패를 삼켜 조용히 빈 문자열이 된다(화면상
   "계좌 미등록"과 구분 불가) — 되돌릴 수 없는 데이터 손실인데 알아챌
   방법이 없었다.

   [2] `cmd_backup()`의 보관기간(기본 30일) 정리 루프(manage.py 1341행
   부근)에 예외 방어가 없었다 — 바로 3줄 위, 같은 함수 안의 형제 루프
   (이전 실행 찌꺼기 .part 파일 정리)는 `try/except OSError: pass`로
   방어돼 있는데 이 루프만 없었다. 실측: 정리 대상 파일 중 하나가 다른
   프로세스에 잠겨 있으면(백신 실시간 검사·오프사이트 동기화 등 Windows
   에서 드물지 않은 조건) `os.remove()`가 예외를 던져 함수 전체가 죽고
   (그날 백업 자체는 이미 끝나 있었는데도 "실패"로 기록됨), 같은 파일이
   매일 잠긴다면 그 뒤로 보관기간 정리가 영구히 멈춰 백업이 무한정
   쌓일 수 있다.

   고침: [1] cmd_restore()에 cmd_check()와 같은 복호화 왕복 확인을
   무결성검사 통과 직후 추가(막지는 않음 — 파일 복구는 이미 끝났으므로
   사후 경고만). [2] 보관기간 루프에 형제 루프와 같은 try/except OSError
   적용. 둘 다 트레이드오프 없는 "그냥 고치면 되는 것".

       python test_scan_round446_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MANAGE_PATH = os.path.join(HERE, "manage.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


MANAGE_SRC = io.open(MANAGE_PATH, encoding="utf-8").read()

print("=" * 72)
print("  스캔 446라운드 회귀 — 백업/복구 결함 2건")
print("=" * 72)

print("\n[1] 소스 확인")
_i0 = MANAGE_SRC.index("def cmd_restore(argv):")
_i1 = MANAGE_SRC.index("\n\n\n#", _i0)
_restore_body = MANAGE_SRC[_i0:_i1]
chk("bank_account_enc" in _restore_body and "CRYPTO.decrypt" in _restore_body,
    "★★★★★ cmd_restore()에 복호화 왕복 확인 코드가 추가됐다")

_j0 = MANAGE_SRC.index("# 보관 기간 (기본 30일) 지난 백업 정리")
_j1 = MANAGE_SRC.index("if removed:", _j0)
_retention_body = MANAGE_SRC[_j0:_j1]
chk("try:" in _retention_body and "except OSError:" in _retention_body,
    "★★★★★ 보관기간 정리 루프에 try/except OSError가 추가됐다")

print("\n[2] 실행 준비 — 스크래치 DB·백업 디렉터리")
_tmpdir = tempfile.mkdtemp(prefix="round446_")
DB_PATH = os.path.join(_tmpdir, "verify.db")
BACKUP_DIR = os.path.join(_tmpdir, "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)
os.environ["BOKGUON_DB_PATH"] = DB_PATH
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
os.environ["BOKGUON_BACKUP_DIR"] = BACKUP_DIR
os.environ["BOKGUON_PORT"] = "18799"   # 실제 운영 포트(8771)와 절대 안 겹치게
KEY_A = "aXZlY3J5cHRvdGVzdGtleUEwMDAwMDAwMDAwMDAwMDA="
KEY_B = "aXZlY3J5cHRvdGVzdGtleUIwMDAwMDAwMDAwMDAwMDA="
os.environ["BOKGUON_ENC_KEY"] = KEY_A
os.environ["BOKGUON_INDEX_KEY"] = KEY_A
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import crypto_util as CRYPTO
    import manage as M

    conn = DB.get_db()
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,created_at,"
        "                     bank_account_enc,bank_account_idx) "
        "VALUES('R446업체','시공사','활성','가드레일','서울',?,?,?)",
        (DB.now(), CRYPTO.encrypt("110-234-567890"), CRYPTO.blind_index("110-234-567890"))
    ).lastrowid
    conn.commit(); conn.close()

    print("\n[3] 실행 — 정상 키로 백업+복구하면 경고가 없다(대조군, 과잉경고 아님)")
    rc_backup = M.cmd_backup([])
    chk(rc_backup == 0, "  cmd_backup() 정상 종료", rc_backup)
    backups = sorted(f for f in os.listdir(BACKUP_DIR) if f.endswith(".db"))
    chk(len(backups) == 1, "  백업 파일 1개 생성됨", backups)
    backup_path = os.path.join(BACKUP_DIR, backups[0])

    buf = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(buf):
        rc_restore_ok = M.cmd_restore([backup_path, "--force", "--yes"])
    out_ok = buf.getvalue()
    chk(rc_restore_ok is None or rc_restore_ok == 0,
        "  같은 키로 복구하면 정상 종료", rc_restore_ok)
    chk("복호화 왕복 확인 실패" not in out_ok,
        "★★★★★ 같은 키로 복구하면 경고가 안 뜬다(과잉경고 아님)", out_ok[-500:])

    print("\n[4] 실행 — 다른 키로 복구를 재현하면 새 검사가 실제로 잡아낸다")
    os.environ["BOKGUON_ENC_KEY"] = KEY_B
    os.environ["BOKGUON_INDEX_KEY"] = KEY_B
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc_restore_bad = M.cmd_restore([backup_path, "--force", "--yes"])
    out_bad = buf2.getvalue()
    chk("복호화 왕복 확인 실패" in out_bad,
        "★★★★★ 다른 키로 복구하면 새 검사가 경고를 낸다"
        "(고치기 전엔 이 상황도 '복구 완료'로만 조용히 끝났다)", out_bad[-500:])
    #  ⚠ 복구 자체(파일 복사·무결성검사)는 여전히 성공해야 한다 — 이 검사는
    #    사후 경고일 뿐 복구를 막지 않는다(막을 이유가 없다 — 파일은 이미 멀쩡함).
    chk("복구 완료" in out_bad, "  복구 자체는 여전히 완료로 끝난다(막지 않음, 경고만)", out_bad[-500:])
    os.environ["BOKGUON_ENC_KEY"] = KEY_A
    os.environ["BOKGUON_INDEX_KEY"] = KEY_A

    print("\n[5] 실행 — 보관기간 정리 중 파일 하나가 잠겨도 나머지는 계속 정리된다")
    import time as _time
    old_ts = _time.time() - 40 * 86400   # 40일 전 (기본 보관 30일 초과)
    for name in ("bokguon_a.db", "bokguon_b.db", "bokguon_c.db"):
        p = os.path.join(BACKUP_DIR, name)
        io.open(p, "wb").write(b"dummy")
        os.utime(p, (old_ts, old_ts))
    _orig_remove = os.remove

    def _flaky_remove(path):
        if os.path.basename(path) == "bokguon_b.db":
            raise PermissionError("[WinError 32] 다른 프로세스가 사용 중")
        return _orig_remove(path)

    os.remove = _flaky_remove
    try:
        buf3 = io.StringIO()
        with contextlib.redirect_stdout(buf3):
            rc_backup2 = M.cmd_backup([])
    finally:
        os.remove = _orig_remove
    chk(rc_backup2 == 0,
        "★★★★★ 파일 하나가 잠겨 있어도 cmd_backup() 전체가 예외로 죽지 않는다"
        "(고치기 전엔 여기서 함수 전체가 죽었다)", rc_backup2)
    remaining = set(os.listdir(BACKUP_DIR))
    chk("bokguon_a.db" not in remaining and "bokguon_c.db" not in remaining,
        "  잠기지 않은 파일 둘은 정상적으로 삭제됐다", remaining)
    chk("bokguon_b.db" in remaining,
        "  잠겼던 파일만 남아있다(그 파일만 건너뜀, 다음 회차에 재시도 가능)", remaining)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
