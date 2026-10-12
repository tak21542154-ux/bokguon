# -*- coding: utf-8 -*-
"""스캔 292라운드 회귀 — manage.py 미조사 서브커맨드 결함 3건, manage.py의
   20개 cmd_* 서브커맨드 중 17개(cmd_prune_personal·cmd_prune_orphans·
   cmd_check 만 이전 라운드가 부분적으로 다룸)를 이 세션 사상 첫 정밀조사한
   정밀조사 Agent가 발견 — cmd_backup/cmd_restore/cmd_go_live 는 이미 여러
   라운드에 걸쳐 두텁게 방어돼 있어 새 결함 없음, 나머지도 대부분 클린.

  ①[심각] cmd_install_scheduler 가 실제 이 PC에 등록된 예약작업과 완전히
     어긋나 있었다. 실측(schtasks /Query /TN 복구온_경매마감 /XML, 읽기전용):
     실제 작업은 Command=...\\pythonw.exe, Arguments="manage.py sweep",
     .bat 파일 자체가 없다(콘솔 깜빡임을 없애려 손으로 pythonw.exe 로
     고쳐 둔 상태 — 프로젝트 메모리에 이미 기록된 조치). 그런데 이 코드는
     그 사실을 전혀 모른 채 python.exe 로 _마감점검.bat 을 새로 만들어
     schtasks /Create ... /F(무조건 덮어쓰기)로 등록하고 있었다 — 이
     명령을 다시 돌리면(재배포 등) 이미 고쳐진 운영 작업을 콘솔 깜빡이는
     python.exe+.bat 방식으로 조용히 되돌렸을 것이다. 옛 .bat 경유 방식의
     근거("한글 경로가 bat 없인 조용히 실패한다")도 재실측: 지금 코드는
     이미 os.system() 문자열조립이 아니라 subprocess.run([...]) 리스트
     인자라 셸 파싱을 안 거친다 — 임시 작업이름으로 실제 등록→XML로
     확인→즉시삭제까지 해 보니 한글 경로를 절대경로 인자로 그대로 넘겨도
     정상 등록됐다. .bat·cd 없이 pythonw.exe(없으면 python.exe 로 폴백)를
     manage.py 절대경로와 함께 직접 등록하도록 수정(manage.py 자신도
     HERE=os.path.dirname(os.path.abspath(__file__)) 로만 경로를 잡고
     os.getcwd() 에 기대지 않으므로 작업 디렉터리 지정 자체가 불필요).
  ② cmd_install_scheduler 의 --remove 가 schtasks 결과를 안 보고 무조건
     "해제했습니다"를 찍었다 — 이미 해제됐거나 schtasks 자체가 막힌
     환경(정책·권한)이면 schtasks 는 예외 없이 실패 종료코드만 낸다(실측:
     없는 작업이름으로 재현 — returncode 1). 운영자가 "꺼졌다"고 믿는데
     실제로는 계속 돌 수 있었다. returncode 를 확인해 실패 시 정직하게
     보고하도록 수정(설치 경로는 이미 이렇게 하고 있어 형제와 통일).
  ③ cmd_backup 이 DB_PATH 가 없을 때(오타·미초기화) sqlite3.connect() 가
     조용히 빈 파일을 만들고, 그 빈 파일에 SELECT 를 던져 나는
     OperationalError 가 범용 except 로 떨어져 "디스크 여유 공간과 권한을
     확인하세요"라는 엉뚱한 안내를 냈다(실측: 격리 스크래치 경로로 재현).
     게다가 실패해도 DB_PATH 자리에 그 빈 파일이 남는다. 시도 전에
     os.path.exists() 로 막아 정확한 원인과 조치법을 안내하도록 수정.
     부수적으로 deploy/복구온_예약실행_등록.ps1(별도 이름 '복구온_스윕'
     작업을 만드는 다른 예약등록 스크립트)도 같은 이유로 python.exe→
     pythonw.exe 로 통일.

      python test_scan_round292_fixes.py
"""
import importlib
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
PS1_SRC = read(os.path.join("deploy", "복구온_예약실행_등록.ps1"))

print("=" * 72)
print("  스캔 292라운드 회귀 — manage.py 예약등록·백업 결함 3건")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
_i0 = MANAGE_SRC.index("def cmd_install_scheduler(argv):")
_i1 = MANAGE_SRC.index("\n    # 리눅스", _i0)
CIS_SRC = MANAGE_SRC[_i0:_i1]
chk('os.path.join(os.path.dirname(py), "pythonw.exe")' in CIS_SRC,
    "★★★ cmd_install_scheduler 가 pythonw.exe 경로를 스스로 찾는다")
chk('"@echo off\\r\\n"' not in CIS_SRC and 'f.write(f\'"{py}" manage.py sweep' not in CIS_SRC,
    "★★★ .bat 파일을 새로 만드는 옛 코드가 없다(pythonw.exe 직접 등록으로 대체)")
chk('"/TR", f\'"{pyw}" "{manage_path}" sweep\'' in CIS_SRC,
    "★★★ schtasks 에 pythonw.exe + manage.py 절대경로를 직접 넘긴다")
chk(CIS_SRC.count("if r.returncode:") >= 2,
    "★★★ --remove 도 설치 경로처럼 returncode 를 확인한다(형제와 통일)",
    CIS_SRC.count("if r.returncode:"))

chk("if not os.path.exists(DB.DB_PATH):" in MANAGE_SRC,
    "★★★ cmd_backup 이 시도 전에 DB_PATH 존재를 확인한다")

chk("$PyW = Join-Path (Split-Path $Py -Parent) 'pythonw.exe'" in PS1_SRC,
    "★★★ 복구온_예약실행_등록.ps1 도 pythonw.exe 경로를 찾는다")
chk("New-ScheduledTaskAction -Execute $PyW" in PS1_SRC,
    "★★★ 복구온_예약실행_등록.ps1 이 실제 등록에 $PyW 를 쓴다(대입만 하고 안 쓰는 실수 방지)")

# ============================================================
print("\n[2] 실행 — cmd_install_scheduler 를 실제 schtasks 호출 없이 검증")
#      (subprocess.run 을 가짜로 바꿔 진짜 예약작업을 절대 건드리지 않는다 —
#       이 결함 자체가 "다시 돌리면 운영 작업을 조용히 되돌린다"는 것이었다)
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round292_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
_orig_run = None
try:
    import subprocess as _subprocess_mod
    import manage as MANAGE

    _orig_run = _subprocess_mod.run
    _calls = []

    class _FakeCompleted:
        #  ⚠⚠ [라운드680] cmd_install_scheduler()가 round679/680을 거치며 text=True를
        #    버리고 원시 바이트 캡처+_decode_schtasks() 수동 디코드로 바뀌었다(schtasks.exe
        #    자신의 인코딩이 실행 맥락마다 달라지는 것을 실측해 대응) — 그래서 이 가짜
        #    결과 객체도 이제 stdout/stderr를 str이 아니라 bytes로 흉내내야 한다(실제
        #    subprocess.run이 text=True 없이 돌려주는 것과 같은 타입).
        def __init__(self, returncode, stdout=b"", stderr=b""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def _fake_run_success(cmd, **kwargs):
        _calls.append(cmd)
        return _FakeCompleted(0)

    if os.name == "nt":
        MANAGE.subprocess.run = _fake_run_success
        try:
            rc = MANAGE.cmd_install_scheduler([])
        finally:
            MANAGE.subprocess.run = _orig_run
        chk(rc == 0, "install-scheduler(가짜 schtasks, 성공 흉내) 가 0을 반환한다", rc)
        create_call = next((c for c in _calls if "/Create" in c), None)
        chk(create_call is not None, "★★★ /Create 호출이 실제로 발생했다")
        if create_call:
            tr_idx = create_call.index("/TR") + 1
            tr_value = create_call[tr_idx]
            chk("pythonw.exe" in tr_value or "python.exe" in tr_value,
                "/TR 값에 pythonw.exe(또는 폴백 python.exe)가 들어있다", tr_value)
            chk(os.path.join(HERE, "manage.py") in tr_value,
                "★★★ /TR 값에 manage.py 절대경로가 그대로 들어있다(cwd 의존 없음)", tr_value)
            chk(".bat" not in tr_value,
                "★★★ /TR 값에 .bat 파일 경로가 없다(직접 등록으로 대체됨)", tr_value)
        chk(not os.path.exists(os.path.join(HERE, "_마감점검.bat")),
            "★★★ 실행 후에도 _마감점검.bat 파일이 생기지 않는다")

        # --remove 실패 흉내 — 정직하게 실패를 보고하는지
        def _fake_run_fail(cmd, **kwargs):
            _calls.append(cmd)
            return _FakeCompleted(1, stderr="ERROR: 지정한 파일을 찾을 수 없습니다.".encode("utf-8"))

        MANAGE.subprocess.run = _fake_run_fail
        try:
            rc2 = MANAGE.cmd_install_scheduler(["--remove"])
        finally:
            MANAGE.subprocess.run = _orig_run
        chk(rc2 == 1,
            "★★★ --remove 가 schtasks 실패 시 0이 아니라 1을 반환한다"
            "(고치기 전엔 실패해도 무조건 0 반환+'해제했습니다' 출력)", rc2)

        # --remove 성공 흉내 — 정상 동작 회귀 없음
        MANAGE.subprocess.run = _fake_run_success
        try:
            rc3 = MANAGE.cmd_install_scheduler(["--remove"])
        finally:
            MANAGE.subprocess.run = _orig_run
        chk(rc3 == 0, "--remove 성공 흉내는 여전히 0을 반환한다(회귀 없음)", rc3)
    else:
        chk(True, "Windows 아님 — [2] 스킵(cmd_install_scheduler 의 nt 분기 대상 아님)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드292 [2] cmd_install_scheduler 검증", f"{type(e).__name__} {e}")
finally:
    if _orig_run is not None:
        _subprocess_mod.run = _orig_run

# ============================================================
print("\n[3] 실행 — cmd_backup 의 DB_PATH 존재 확인 (실제 함수 호출)")
# ------------------------------------------------------------
try:
    import db as DB

    # 3-a: 존재하지 않는 경로 — 정확한 에러 + 빈 파일 안 남김
    missing_path = os.path.join(_tmpdir, "no_such.db")
    _orig_dbpath = DB.DB_PATH
    DB.DB_PATH = missing_path
    try:
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = MANAGE.cmd_backup([os.path.join(_tmpdir, "backups_missing")])
        out = buf.getvalue()
    finally:
        DB.DB_PATH = _orig_dbpath
    chk(rc == 1, "존재하지 않는 DB_PATH 에 대해 실패(1)를 반환한다", rc)
    chk("DB 파일이 없습니다" in out,
        "★★★ 정확한 원인(DB 파일 없음)을 안내한다"
        "(고치기 전엔 '디스크 여유 공간과 권한을 확인하세요'라는 엉뚱한 안내)", out[:300])
    chk("디스크 여유 공간과 권한" not in out,
        "★★★ 더는 엉뚱한 디스크/권한 안내를 하지 않는다", out[:300])
    chk(not os.path.exists(missing_path),
        "★★★ 시도 후에도 DB_PATH 자리에 빈 파일이 생기지 않는다"
        "(고치기 전엔 sqlite3.connect() 가 조용히 빈 파일을 만들었다)")

    # 3-b: 정상 DB — 회귀 없음(실제로 백업이 된다)
    DB.init_db()
    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r292admin','x','검증','최고관리자')")
    conn.commit(); conn.close()
    good_backup_dir = os.path.join(_tmpdir, "backups_ok")
    rc_ok = MANAGE.cmd_backup([good_backup_dir])
    made = [f for f in os.listdir(good_backup_dir) if f.endswith(".db")] \
        if os.path.isdir(good_backup_dir) else []
    chk(rc_ok == 0 and len(made) == 1,
        "정상 DB_PATH 에서는 여전히 백업 파일이 실제로 만들어진다(회귀 없음)",
        (rc_ok, made))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드292 [3] cmd_backup 검증", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
