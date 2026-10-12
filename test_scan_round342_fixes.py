# -*- coding: utf-8 -*-
"""
342라운드 회귀 — manage.py cmd_restore() 가 shutil.copy2() 호출 자체가
예외를 던지는 경우(디스크 꽉 참·백신 잠금 등, 이 함수 자신의 기존 주석이
이미 재해복구는 이런 불안정한 환경에서 한다고 지적함)를 처리하지 않던 결함.

  배경: manage.py 를 20개 서브커맨드 단위로 재조사(cmd_backup/cmd_restore/
  cmd_reset_pw/cmd_create_admin/cmd_create_insurer 등 run_all_tests.py 어디
  에도 이름으로 언급된 적 없는 12개를 grep 으로 확인 — cmd_check·
  cmd_install_scheduler·cmd_go_live·cmd_prune_personal 등은 이미 다른
  라운드가 다뤘음)한 결과 발견. cmd_restore(1334행)는 이미 여러 겹의 안전
  장치를 갖고 있다 — 복구 전 현재 DB를 sqlite3 온라인 백업 API로 안전하게
  보존(keep, WAL 포함)하고, 복사 뒤에는 PRAGMA integrity_check 로 실제
  내용까지 확인해 실패하면 keep 에서 되돌리는 법을 안내한다(round66이 이미
  "복사 뒤 확인 없이 복구완료만 찍는" 결함을 고쳐 이 안전장치를 만들었다).
  그런데 그 사이의 실제 파일 복사(shutil.copy2, 1410행 부근)만은 try/except
  없이 노출돼 있었다 — 복사 자체가 예외를 던지면(디스크 꽉 참 등) 처리
  안 된 트레이스백과 함께 프로세스가 죽는데, 이때는 바로 20줄 아래
  무결성검사 실패 분기가 이미 안내하는 "keep 에서 되돌리는 법" 힌트를
  전혀 못 보고 죽는다 — keep 은 이미 안전하게 떠 있는데 그 사실을 이
  실패 경로에서만 못 알려주는 비대칭이었다(round66이 재현한 "복사는
  됐는데 내용이 깨진" 시나리오와는 달리, 이번은 "복사 자체가 안 됐다"는
  다른 실패 지점). 데이터 유실·손상 위험 자체는 아니다(keep 이 이미
  안전하고, 원본 DB.DB_PATH 도 shutil.copy2 가 예외를 던지면 아무것도
  안 쓴 채라 그대로 무사함) — 실패 경험의 질(안내 유무) 문제.

  고침: shutil.copy2 호출만 try/except OSError 로 감싸, 무결성검사 실패
  분기가 이미 쓰는 keep 안내 문구를 공유 헬퍼(_keep_hint)로 뽑아 양쪽이
  똑같이 쓰도록 통일 — 새 코드가 아니라 이미 있던 안내를 재사용.

  기존 test_scan_round66_fixes.py 는 이 함수를 이미 실제로 실행하는 테스트
  (M.cmd_restore 직접 호출)라 사전 확인: 그 테스트는 shutil.copy2 를
  "예외 없이 깨진 내용을 쓰는" 대역으로 바꿔치기해(디스크 손상 시나리오) 그
  뒤 무결성검사 실패 경로를 재현한다 — 이번 수정의 try/except 는 copy2가
  예외를 던지지 않는 한 전혀 안 끼어들어 그 테스트와 충돌하지 않는다(직접
  재실행으로 재확인, 아래 [3]).

  실행기반 검증: 실제 manage.cmd_restore() 를 shutil.copy2 가 진짜로
  OSError 를 던지는 상황으로 호출해, (a) 예외가 새지 않고 1을 반환하는지
  (b) 실패 메시지에 원인이 남는지 (c) keep 안내가 이 경로에서도 나오는지
  (d) keep 사본이 실제로 디스크에 남아 무결성까지 정상인지(안내만 있고
  실제로 못 쓰면 무의미) 를 실측한다.
"""
import contextlib
import io
import os
import subprocess
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    with io.open(os.path.join(HERE, rel), encoding="utf-8") as f:
        return f.read()


print("=" * 70)
print("  스캔 342라운드 회귀 — manage.py cmd_restore() copy2 예외 처리")
print("=" * 70)

MANAGE_SRC = read("manage.py")


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


print("\n[1] 소스 확인")
restore_body = _body(MANAGE_SRC, "cmd_restore")
chk("def _keep_hint():" in restore_body,
    "★★★ cmd_restore 안에 keep 안내를 공유하는 헬퍼가 생겼다")
i_call = restore_body.index("shutil.copy2(src, DB.DB_PATH)")
chk("except OSError as e:" in restore_body[i_call:i_call + 200],
    "★★★★ shutil.copy2 호출 바로 다음에 OSError 를 잡는 처리가 있다")
chk(restore_body.count("_keep_hint()") == 3,
    "★★ 무결성검사 실패 분기도 같은 헬퍼를 재사용한다(문구 중복 없음, "
    "정의 1회+호출 2회 — copy2 실패·무결성검사 실패 두 경로 모두)")

print("\n[2] 실행 확인 — 실제 cmd_restore() 로 copy2 예외 시나리오 재현")
_tmpdir = tempfile.mkdtemp(prefix="round342_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_BACKUP_DIR"] = os.path.join(_tmpdir, "backups")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
#  ⚠ round66 과 같은 이유로 실제 운영 포트(8771)를 피한다 — 그 라운드와
#    겹치지 않는 별도 포트를 쓴다(동시 실행 시 서로 간섭하지 않도록).
os.environ["BOKGUON_PORT"] = "18772"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import manage as M

    _bkdir = os.path.join(_tmpdir, "srcbk")
    os.makedirs(_bkdir, exist_ok=True)
    _good_backup = os.path.join(_bkdir, "good.db")
    _gc = sqlite3.connect(_good_backup)
    _gc.execute("CREATE TABLE t(x)")
    _gc.execute("INSERT INTO t VALUES(1)")
    _gc.commit()
    _gc.close()

    _real_copy2 = M.shutil.copy2

    def _raising_copy2(src, dst):
        raise OSError(28, "디스크 공간이 부족합니다(라운드342 회귀테스트 주입)")

    M.shutil.copy2 = _raising_copy2
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = M.cmd_restore([_good_backup, "--yes"])
        out = buf.getvalue()
    finally:
        M.shutil.copy2 = _real_copy2

    chk(rc == 1,
        "★★★★★ copy2 가 예외를 던지면 cmd_restore 가 (죽지 않고) 1을 반환한다",
        f"rc={rc}")
    chk("백업파일 복사 실패" in out and "디스크 공간이 부족합니다" in out,
        "★★★★ 실패 메시지에 원인(예외 내용)이 그대로 남는다", out[-400:])
    chk("직전 DB 는 보존돼 있습니다" in out,
        "★★★★★ keep(사전 보존본)에서 되돌리는 안내가 이 경로에서도 나온다"
        "(고치기 전엔 이 경로에서만 트레이스백과 함께 죽어 이 안내를 못 봤다)",
        out[-400:])

    _keep_files = [f for f in os.listdir(_tmpdir)
                   if f.startswith("verify.db.before_restore_")]
    chk(len(_keep_files) == 1,
        "★★★★ keep 사본이 실제로 디스크에 남아 있다(안내가 헛말이 아니다)",
        _keep_files)
    if _keep_files:
        _kc = sqlite3.connect(os.path.join(_tmpdir, _keep_files[0]))
        try:
            _kres = _kc.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            _kc.close()
        chk(_kres == "ok",
            "★★★★ keep 사본 자신의 무결성도 정상이다(실제로 복구에 쓸 수 있다)",
            _kres)

    # 대조군 — copy2 가 정상이면 이번 수정 이후에도 회귀 없이 그대로 성공한다
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc_ok = M.cmd_restore([_good_backup, "--yes"])
    out_ok = buf2.getvalue()
    chk(not rc_ok and "무결성 검사 통과" in out_ok,
        "★★ 대조군 — copy2 가 정상이면 회귀 없이 그대로 복구 성공한다(과잉차단 아님)",
        (rc_ok, out_ok[-300:]))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ [2] 준비/실행", f"{type(e).__name__} {e}")
finally:
    for _v in ("BOKGUON_DB_PATH", "BOKGUON_UPLOAD_DIR", "BOKGUON_BACKUP_DIR",
               "BOKGUON_ENV", "BOKGUON_SEED_DEMO", "BOKGUON_PORT"):
        os.environ.pop(_v, None)

print("\n[3] 회귀 확인 — round66의 기존 cmd_restore 실행 테스트가 여전히 통과하는가")
try:
    r66 = subprocess.run(
        [sys.executable, os.path.join(HERE, "test_scan_round66_fixes.py")],
        capture_output=True, text=True, encoding="utf-8", cwd=HERE, timeout=60,
    )
    chk(r66.returncode == 0,
        "★★★★★ test_scan_round66_fixes.py 단독 재실행 통과(이번 수정과 충돌 없음)",
        (r66.returncode, (r66.stdout or "")[-500:], (r66.stderr or "")[-300:]))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★ [3] round66 재실행 준비", f"{type(e).__name__} {e}")

print(f"\n{'=' * 70}\n  통과 {len(PASS)} · 실패 {len(FAIL)}\n{'=' * 70}")
sys.exit(1 if FAIL else 0)
