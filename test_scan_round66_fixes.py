# -*- coding: utf-8 -*-
"""스캔 66라운드 회귀 — 배포/운영 스크립트 5종 점검(라운드65 개인정보 파기
   예약 발견의 직접적인 후속):

  ① 접속기록 파기(prune-logs)도 개인정보 파기(prune-personal, 라운드65)와
     같은 법정 의무·같은 주기 형제인데 job_locks 표식이 없어 manage.py check
     가 정지를 못 잡았다.
  ② manage.py restore 가 복사만 하고 결과를 확인하지 않았다 — 재해복구는
     원래 환경이 불안정할 때 하는 일이라 복사가 중간에 끊길 수 있는데, 이미
     옛 DB 는 지운 뒤라 확인 없이 "복구 완료"만 찍으면 깨진 DB 위에서
     서비스가 재시작된다.
  ③ 시공·하자 증빙사진(uploads) 백업이 도는지 보는 검사가 전 코드베이스에
     하나도 없었다 — DB 백업만 초록이면 배포 가능으로 떴다. 실측(이 라운드):
     이 기기의 backups/uploads/ 는 실제로 존재하지 않았다.
  ④ 실제 운영에 있는 통합 스크립트(deploy/일일백업.bat)가 공식 설치
     문서(windows_setup.ps1/DEPLOY.md)에는 전혀 언급되지 않아, 둘을 같이
     쓰면 같은 작업이 중복 등록될 수 있는데 아무 경고도 없었다.
  ⑤ 인터널 개인정보 관리계획 문서·주석 두 곳이 이미 260MB/8MB로 올라간
     업로드 상한을 옛 "10MB" 그대로 적고 있었다(app.py 자신의 주석이 "예전의
     10MB 상한" 이라고 스스로 증언한다).
  ⑥ 네이버클라우드 배포 가이드만 형제(AWS 가이드)와 달리 예약 실행(sweep)·
     개인정보 파기를 크론 목록에서 빠뜨렸다.

      python test_scan_round66_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


MANAGE_SRC = read("manage.py")
PHOTO_SRC = read("photo_ai.py")
DEPLOY_SRC = read(os.path.join("deploy", "DEPLOY.md"))
PLAN_SRC = read(os.path.join("deploy", "개인정보_내부관리계획.md"))
NCLOUD_SRC = read(os.path.join("deploy", "네이버클라우드_배포절차.md"))

print("═" * 72)
print("  스캔 66라운드 회귀 — 배포/운영 스크립트 5종 점검(라운드65 개인정보파기 발견의 후속)")
print("═" * 72)


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계·문서 안에서 확인")
# ──────────────────────────────────────────────────────────────
prunelogs_body = _body(MANAGE_SRC, "cmd_prune_logs")
chk("INSERT INTO job_locks(name, last_run_at) VALUES('prune_logs'" in prunelogs_body,
    "★★ ① cmd_prune_logs — 실행됐다는 표식을 남긴다")

check_body = _body(MANAGE_SRC, "cmd_check")
chk("job_locks WHERE name='prune_logs'" in check_body,
    "★★★ ① cmd_check — 접속기록 파기 정지도 미리 잡는다")
chk("_photobk = os.path.join(bdir, \"uploads\")" in check_body,
    "★★★ ③ cmd_check — 사진(uploads) 백업 정지도 잡는다(전에는 이런 검사 자체가 없었다)")

restore_body = _body(MANAGE_SRC, "cmd_restore")
#  ⚠ "shutil.copy2" 라는 글자는 이 함수 안에 설명 주석에도 한 번 더 나온다(라인
#    상단, 왜 copy2 만으로는 안 되는지 설명하는 부분) — **마지막** 등장(실제
#    호출문) 뒤쪽을 봐야 그 다음에 붙인 무결성 검사 코드를 정확히 짚는다.
chk("keep = None" in restore_body
    and "PRAGMA integrity_check" in restore_body.split("shutil.copy2")[-1],
    "★★★ ② cmd_restore — 복사 뒤 무결성을 실제로 확인한다")

chk("일일백업.bat" in DEPLOY_SRC and "이중으로 돌릴 수 있다" in DEPLOY_SRC,
    "★★ ④ DEPLOY.md — 실제 운영 스크립트(일일백업.bat)와 공식 설치의 관계를 설명한다")

chk("장당 8MB" in PLAN_SRC and "3. 업로드 파일은 크기(10MB)" not in PLAN_SRC,
    "★ ⑤ 개인정보_내부관리계획.md — 업로드 상한이 실제 값(8MB)으로 맞다")
chk("(앱 전체 상한 10MB보다 작게)" not in PHOTO_SRC,
    "★ ⑤ photo_ai.py — 옛 10MB 비교 주석이 갱신됐다")

chk("예약 실행" in NCLOUD_SRC and "개인정보 파기" in NCLOUD_SRC,
    "★★ ⑥ 네이버클라우드_배포절차.md — 예약 실행·개인정보 파기가 크론 목록에 있다"
    "(형제인 AWS 가이드와 맞춘다)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 함수 호출(manage.py)로 ①②③ 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round66_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_BACKUP_DIR"] = os.path.join(_tmpdir, "backups")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
#  ⚠ 이 기기엔 실제 운영 서버가 8771 에서 돌고 있다 — restore 재현이 그 서버를
#    '살아있음'으로 오판하지 않도록 아무도 안 쓰는 포트로 돌린다.
os.environ["BOKGUON_PORT"] = "18771"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import manage as M
    import shutil as _sh
    import io as _io
    import contextlib as _cl
    import sqlite3

    def _run_check():
        buf = _io.StringIO()
        with _cl.redirect_stdout(buf):
            M.cmd_check([])
        return buf.getvalue()

    def _lock(name):
        c = DB.get_db()
        r = c.execute("SELECT last_run_at FROM job_locks WHERE name=?", (name,)).fetchone()
        c.close()
        return r[0] if r else None

    # ── ① prune-logs 표식 ──
    chk(_lock("prune_logs") is None, "STEP 처음엔 prune_logs 표식이 없다(전제 확인)", None)
    out0 = _run_check()
    chk("접속기록 파기(prune-logs)가 한 번도 실행되지 않았습니다" in out0,
        "★★★ ① 예약 전엔 실제로 경고한다", None)
    M.cmd_prune_logs([])
    chk(_lock("prune_logs") is not None,
        "★★★ ① 실제 실행 뒤 표식이 남는다(고치기 전엔 이 표식 자체가 없었다)", None)
    out1 = _run_check()
    chk("접속기록 파기(prune-logs)가 한 번도 실행되지 않았습니다" not in out1
        and "접속기록 파기 예약 정상" in out1,
        "★★★ ① 실행 뒤엔 정상 표시로 바뀐다", None)

    # ══════════════════════════════════════════════════════════
    print("\n  ② manage.py restore 무결성 확인")
    # ──────────────────────────────────────────────────────────
    _bkdir = os.path.join(_tmpdir, "srcbk")
    os.makedirs(_bkdir, exist_ok=True)
    _good_backup = os.path.join(_bkdir, "good.db")
    _gc = sqlite3.connect(_good_backup)
    _gc.execute("CREATE TABLE t(x)"); _gc.execute("INSERT INTO t VALUES(1)")
    _gc.commit(); _gc.close()

    #  ⚠ 복사 단계 자체가 깨진 상황을 재현한다(원본은 멀쩡한데 대상이 손상되는
    #    경우 — 디스크 꽉 참·전원차단 등). shutil.copy2 를 잠깐 바꿔치기한다.
    _real_copy2 = M.shutil.copy2

    def _corrupt_copy2(src, dst):
        with open(dst, "wb") as f:
            f.write(b"NOT A VALID SQLITE FILE AT ALL")

    M.shutil.copy2 = _corrupt_copy2
    try:
        buf = _io.StringIO()
        with _cl.redirect_stdout(buf):
            rc_bad = M.cmd_restore([_good_backup, "--yes"])
        out_bad = buf.getvalue()
    finally:
        M.shutil.copy2 = _real_copy2
    chk(rc_bad != 0 and "무결성 검사 실패" in out_bad,
        "★★★ ② 복사 뒤 대상이 손상되면 실패로 보고한다(고치기 전엔 무조건 '복구 완료')",
        (rc_bad, out_bad[-300:]))
    #  DB 파일 자체는 (테스트가 깨뜨렸으므로) 지금 손상 상태다 — 다음 재현을 위해
    #  init_db 로 다시 정상화한다.
    for _suf in ("", "-wal", "-shm"):
        _p = DB.DB_PATH + _suf
        if os.path.exists(_p):
            os.remove(_p)
    DB.init_db()

    # 대조군 — 정상 복사는 그대로 통과한다(과잉차단 아님)
    #  ⚠ main() 이 `COMMANDS[cmd](...) or 0` 으로 정규화하기 전이라, 성공은
    #    여기선 원래부터 0 이 아니라 None 이다(다른 모든 cmd_* 명령과 동일 관례).
    buf = _io.StringIO()
    with _cl.redirect_stdout(buf):
        rc_ok = M.cmd_restore([_good_backup, "--yes"])
    out_ok = buf.getvalue()
    chk(not rc_ok and "무결성 검사 통과" in out_ok,
        "★ 대조군 — 정상적인 복구는 그대로 성공한다(과잉차단 아님)", (rc_ok, out_ok[-300:]))
    DB.init_db()  # 다음 섹션을 위해 다시 정상 스키마로

    # ══════════════════════════════════════════════════════════
    print("\n  ③ 사진(uploads) 백업 정지 감지")
    # ──────────────────────────────────────────────────────────
    os.makedirs(os.environ["BOKGUON_UPLOAD_DIR"], exist_ok=True)
    with open(os.path.join(os.environ["BOKGUON_UPLOAD_DIR"], "photo1.jpg"), "wb") as f:
        f.write(b"x" * 100)

    out_nobk = _run_check()
    chk("사진 백업 디렉터리가 없습니다" in out_nobk,
        "★★★ ③ 사진 백업 디렉터리가 아예 없으면 경고한다"
        "(이 라운드에서 실측한 이 기기의 실제 상태와 같은 모양)", None)

    _photobk = os.path.join(os.environ["BOKGUON_BACKUP_DIR"], "uploads")
    os.makedirs(_photobk, exist_ok=True)
    with open(os.path.join(_photobk, "photo1.jpg"), "wb") as f:
        f.write(b"x" * 100)
    out_bk_ok = _run_check()
    chk("사진 백업" in out_bk_ok and "원본과 보조를 맞추고 있음" in out_bk_ok,
        "★★ ③ 대조군 — 원본과 보조가 맞으면 정상으로 표시된다(과잉경고 아님)", None)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드66 실측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_BACKUP_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    os.environ.pop("BOKGUON_PORT", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
