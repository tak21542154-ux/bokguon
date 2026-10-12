# -*- coding: utf-8 -*-
"""스캔 123라운드 회귀 — cmd_go_live 의 안전백업이 격리된 DB_PATH 와 무관하게
   진짜 운영 backups/ 로 새던 결함(실측: 이 세션이 실제로 오염시켰다가 정리함),
   backup_selfcheck.py 가 그런 오염 파일을 "최신 백업"으로 오판할 여지,
   smoke_test.py 의 CSP 항진명제 + 보험사 로그인 실패 처리 누락.

  [1] manage.py:cmd_backup 의 출력 디렉터리가 BOKGUON_DB_PATH 격리와 무관하게
      항상 BOKGUON_BACKUP_DIR(미설정 시 실제 프로젝트의 backups/)로 떨어졌다.
      cmd_go_live 가 삭제 전 안전장치로 이걸 내부 호출하므로, 격리된 스크래치
      DB 에 go-live 를 돌리는 회귀테스트마다 진짜 운영 백업 폴더가 오염됐다
      (이번 라운드 조사 중 실제로 발견 — 487KB 데모 스냅샷 6개, 정리 완료).
  [2] backup_selfcheck.py 가 "가장 최근 mtime" 파일을 무조건 신뢰해, 오염된
      작은 파일이 진짜 백업보다 새 mtime을 가지면 그걸 검사하고 진짜 백업은
      영원히 안 본다 — 직전 백업 대비 크기가 급감하면 잡는다.
  [3] smoke_test.py 의 "CSP 외부출처 없음" 검사가 스킴 접두어를 지운 뒤 그
      잔여문자열에 'http'가 있는지를 보는데, 지운 나머지엔 애초에 'http'가
      남을 수 없어 사실상 항상 통과하는 항진명제였다.
  [4] smoke_test.py 의 보험사 로그인 실패 처리가 협력사 분기와 달리 없어서,
      인증 안 된 Client 를 그대로 반환해 이후 여러 검사가 엉뚱한 이름의
      FAIL 로 찍혔다(진짜 원인=자격증명 문제인데 이름이 안 보인다).

      python test_scan_round123_fixes.py
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


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


MANAGE_SRC = read("manage.py")
BSC_SRC = read(os.path.join("deploy", "backup_selfcheck.py"))
SMOKE_SRC = read("smoke_test.py")

print("═" * 72)
print("  스캔 123라운드 회귀 — 백업디렉터리 격리누수·자가점검 오염취약·CSP항진명제·보험사로그인누락")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
chk("def _backup_dir():" in MANAGE_SRC, "★★★ manage.py 에 _backup_dir() 공용 헬퍼가 있다")
chk("os.path.dirname(os.path.abspath(DB.DB_PATH))" in _py_fn_body(MANAGE_SRC, "_backup_dir"),
    "★★★ _backup_dir 이 BOKGUON_DB_PATH 기준으로 기본 경로를 정한다")
chk(MANAGE_SRC.count("_backup_dir()") >= 3,  # 정의 1 + cmd_backup 1 + cmd_check 1
    "★★★ cmd_backup·cmd_check 둘 다 _backup_dir() 을 쓴다(손목록 중복 아님)")

chk("prev_size * 0.5" in BSC_SRC,
    "★★★ backup_selfcheck.py 가 직전 백업 대비 크기급감을 잡는다")

chk('not any(h in csp for h in ("jsdelivr", "googleapis", "gstatic"))' in SMOKE_SRC
    and 'csp.replace("https:", "")' not in SMOKE_SRC,
    "★★★ smoke_test.py CSP 검사에서 항진명제 조건이 사라졌다")
tp_body = _py_fn_body(SMOKE_SRC, "test_login_isolation") if "\ndef test_login_isolation(" in SMOKE_SRC else None
chk('skip("보험사 관련 검사"' in SMOKE_SRC and "i = None" in SMOKE_SRC,
    "★★★ smoke_test.py 가 보험사 로그인 실패도 협력사와 같이 명시적으로 처리한다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — cmd_go_live 가 더 이상 진짜 backups/ 를 오염시키지 않는다")
# ──────────────────────────────────────────────────────────────
sys.path.insert(0, HERE)
REAL_BACKUP_DIR = os.path.join(HERE, "backups")
_before = set(os.listdir(REAL_BACKUP_DIR)) if os.path.isdir(REAL_BACKUP_DIR) else set()

_tmpdir = tempfile.mkdtemp(prefix="round123_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
os.environ.pop("BOKGUON_BACKUP_DIR", None)   # 명시 설정 없이 — 기본값 로직만으로 격리돼야 한다

try:
    import db as DB
    DB.init_db()
    import manage as M

    bd = M._backup_dir()
    chk(os.path.normcase(os.path.abspath(bd)).startswith(os.path.normcase(os.path.abspath(_tmpdir))),
        "★★★ BOKGUON_BACKUP_DIR 없이도 격리된 DB_PATH 밑으로 백업 경로가 자동으로 따라간다"
        "(예전엔 항상 실제 프로젝트의 backups/ 였다)", bd)

    os.environ["BOKGUON_BACKUP_DIR"] = os.path.join(_tmpdir, "explicit_override")
    bd2 = M._backup_dir()
    chk(bd2 == os.environ["BOKGUON_BACKUP_DIR"],
        "STEP BOKGUON_BACKUP_DIR 를 명시하면 여전히 그 값이 최우선이다(기존 기능 보존)", bd2)
    os.environ.pop("BOKGUON_BACKUP_DIR", None)

    import contextlib
    conn = DB.get_db()
    conn.execute("INSERT INTO cases(case_no,status,category,region,is_demo) "
                 "VALUES('R123-DEMO','접수','가드레일','서울',1)")
    conn.commit(); conn.close()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        M.cmd_go_live(["--yes"])

    _after = set(os.listdir(REAL_BACKUP_DIR)) if os.path.isdir(REAL_BACKUP_DIR) else set()
    _stray = _after - _before
    chk(not _stray,
        "★★★★★ go-live 를 격리된 DB 에 돌려도 실제 운영 backups/ 폴더에 새 파일이 "
        "안 생긴다(이 세션이 겪었던 바로 그 오염 재현 없음)",
        (sorted(_stray) or "차이 없음"))
    if _stray:
        #  안전망 — 혹시라도 이 테스트 자체가 다시 오염시켰다면(회귀), FAIL 로
        #  보고는 하되 방금 생긴 파일은 즉시 치운다(사람이 또 수동 정리하지 않게).
        for _f in _stray:
            try:
                os.remove(os.path.join(REAL_BACKUP_DIR, _f))
            except OSError:
                pass

    isolated_backup_dir = os.path.join(_tmpdir, "backups")
    made_isolated_backup = os.path.isdir(isolated_backup_dir) and os.listdir(isolated_backup_dir)
    chk(bool(made_isolated_backup),
        "STEP 안전백업 자체는 여전히 만들어진다 — 격리된 자리로 갔을 뿐이다(과잉차단 아님)",
        isolated_backup_dir)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드123 준비/실행(백업격리)", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    os.environ.pop("BOKGUON_BACKUP_DIR", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — backup_selfcheck.py 가 크기급감 오염을 실제로 잡는가")
# ──────────────────────────────────────────────────────────────
_tmpdir2 = tempfile.mkdtemp(prefix="round123b_")
sys.path.insert(0, os.path.join(HERE, "deploy"))
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "backup_selfcheck_r123", os.path.join(HERE, "deploy", "backup_selfcheck.py"))
    BSC = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(BSC)

    def _mk_db(path, n_partners):
        c = sqlite3.connect(path)
        c.execute("CREATE TABLE partners(id INTEGER PRIMARY KEY, name TEXT)")
        for i in range(n_partners):
            c.execute("INSERT INTO partners(name) VALUES(?)", (f"p{i}",))
        #  파일을 최소 크기 문턱(100KB) 이상으로 부풀린다(실제 SQLite 페이지처럼)
        c.execute("CREATE TABLE pad(x TEXT)")
        c.execute("INSERT INTO pad(x) VALUES(?)", ("가" * 200_000,))
        c.commit()
        c.close()

    import time as _time

    # (a) 오염 시나리오 — 정상 크기 백업 다음에 훨씬 작은 "최신" 파일이 온다
    d1 = os.path.join(_tmpdir2, "poison")
    os.makedirs(d1)
    p_old = os.path.join(d1, "bokguon_260101_030000.db")
    p_new_tiny = os.path.join(d1, "bokguon_260102_030000.db")
    _mk_db(p_old, 50)
    io.open(p_new_tiny, "wb").write(b"x" * 150_000)   # MIN_BYTES(100KB)는 넘지만 old의 극히 일부
    _now = _time.time()
    os.utime(p_old, (_now - 7200, _now - 7200))
    os.utime(p_new_tiny, (_now - 60, _now - 60))       # 더 최근 mtime
    BSC.BACKUP_DIR = d1
    rc1 = BSC.main()
    chk(rc1 == 1,
        "★★★ 직전 백업보다 훨씬 작은 '최신' 파일은 실패로 잡힌다"
        "(예전엔 100KB 문턱만 넘으면 그대로 통과했다)", rc1)

    # (b) 정상 시나리오 — 매일 조금씩 자연 성장 (STEP: 과잉차단 아님)
    d2 = os.path.join(_tmpdir2, "healthy")
    os.makedirs(d2)
    p_y1 = os.path.join(d2, "bokguon_260101_030000.db")
    p_y2 = os.path.join(d2, "bokguon_260102_030000.db")
    _mk_db(p_y1, 50)
    _mk_db(p_y2, 55)
    os.utime(p_y1, (_now - 7200, _now - 7200))
    os.utime(p_y2, (_now - 60, _now - 60))
    BSC.BACKUP_DIR = d2
    rc2 = BSC.main()
    chk(rc2 == 0,
        "STEP 정상적으로 조금씩 커지는 백업은 여전히 통과한다(과잉차단 아님)", rc2)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드123 준비/실행(backup_selfcheck)", f"{type(e).__name__} {e}")
finally:
    shutil.rmtree(_tmpdir2, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
