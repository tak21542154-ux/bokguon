# -*- coding: utf-8 -*-
"""스캔 65라운드 회귀 — 개인정보 파기(manage.py prune-personal) 예약 실행이
   윈도 배포 스크립트에는 없었다(MEDIUM, 처리방침 §21·§30).

  조사 에이전트가 정적 추적(리눅스 bootstrap.sh 와 윈도 windows_setup.ps1 대조)
  으로 짚고, 이번 라운드에서 실측(manage.py 함수 실제 호출)으로 재확인·보강한
  결함:

  manage.py prune-personal 은 처리방침 제3조가 약속한 개인정보 보유기간(문의
  1년·계좌 퇴출시·피해자 하자담보 만료)을 실제로 지키는 유일한 실행 경로다.
  리눅스 배포(bootstrap.sh)는 이걸 매주 일요일 04:30 크론으로 등록하는데,
  윈도 배포(windows_setup.ps1)는 접속기록 파기(prune-logs)까지만 등록하고
  이 항목이 통째로 빠져 있었다 — 실행되는 예약이 없으면 방침 위반이 그대로
  사실이 되는데, 아무 증상도 안 남아(그냥 안 지워질 뿐) 아무도 못 본다.

  ★ 이 라운드에서 실측으로 확인(read-only, file:...?mode=ro): 운영 DB에는
    아직 보유기간을 넘긴 대상이 0건이라 오늘 당장 방침 위반이 발생하지는
    않았다 — 그러나 예약 자체가 없으므로 시간이 지나면 반드시 발생한다.

  같은 라운드에서 함께 보강: manage.py check 이 sweep(예약 실행) 정지를 미리
  잡는 것과 같은 방식으로, prune-personal 이 한 번도/오래 안 돌았을 때도
  미리 경고하도록 job_locks 표식과 점검을 추가했다(코드는 있는데 예약이
  없어 조용히 멈추는 클래스의 결함을 셀프 디텍션하는 이 서비스 고유의 장치를
  그대로 재사용).

  ⚠ windows_setup.ps1 은 실제 운영 Task Scheduler 에 새 예약을 등록하는
    스크립트다 — 이 테스트는 스크립트의 **내용**만 확인하고, 실제로
    Register-ScheduledTask 를 실행하지는 않는다(그건 사람이 판단할 운영
    조치다).

      python test_scan_round65_fixes.py
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


PS_SRC = read(os.path.join("deploy", "windows_setup.ps1"))
DEPLOY_SRC = read(os.path.join("deploy", "DEPLOY.md"))
MANAGE_SRC = read("manage.py")

print("═" * 72)
print("  스캔 65라운드 회귀 — 개인정보 파기 예약이 윈도 배포엔 없었다 + 셀프디텍션 보강")
print("═" * 72)


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 배포 스크립트·문서·함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
chk('$taskPrunePersonal = "복구온_개인정보파기"' in PS_SRC,
    "★★★ windows_setup.ps1 — 개인정보 파기 예약(작업명)이 새로 등록된다")
chk('"manage.py prune-personal"' in PS_SRC,
    "★★ windows_setup.ps1 — 등록되는 명령이 실제로 prune-personal 이다")
chk("-Weekly -DaysOfWeek Sunday -At 4:30am" in PS_SRC,
    "★ windows_setup.ps1 — 주기가 리눅스 크론(일요일 04:30)과 맞다"
    "(접속기록 파기 04:00 바로 뒤)")

#  ⚠ "처리방침에 약속한 개인정보 파기" 라는 문구는 이 문서에 이미 다른 자리
#    (수동 명령 참고 목록의 주석)에도 있다 — 표 행 자체(매주(자동) 접두어 포함)로
#    찾아야 방금 추가한 정기 점검 표 항목만 정확히 짚는다.
chk("매주(자동) | 처리방침에 약속한 개인정보 파기" in DEPLOY_SRC,
    "★ DEPLOY.md — 정기 점검 표에 개인정보 파기 항목이 올라간다")

check_body = _body(MANAGE_SRC, "cmd_check")
chk("job_locks WHERE name='prune_personal'" in check_body,
    "★★★ manage.py check — prune-personal 예약 정지도 미리 잡는다(sweep 과 같은 방식)")

prune_body = _body(MANAGE_SRC, "cmd_prune_personal")
chk("INSERT INTO job_locks(name, last_run_at) VALUES('prune_personal'" in prune_body,
    "★★ manage.py prune-personal — 실행됐다는 표식을 남긴다(cli_sweep 과 같은 방식)")
chk('if not dry:' in prune_body and "job_locks" in prune_body[prune_body.index("if not dry:"):],
    "★ 표식은 --dry-run 에서는 안 남는다(미리보기를 실행으로 착각하지 않는다)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 함수 호출(manage.py)로 셀프디텍션 전 구간 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round65_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import manage as M
    import io as _io
    import contextlib as _cl

    def _run_check():
        buf = _io.StringIO()
        with _cl.redirect_stdout(buf):
            M.cmd_check([])
        return buf.getvalue()

    def _lock_row():
        c = DB.get_db()
        r = c.execute("SELECT last_run_at FROM job_locks WHERE name='prune_personal'").fetchone()
        c.close()
        return r[0] if r else None

    chk(_lock_row() is None, "STEP 처음엔 prune_personal 표식이 없다(전제 확인)", None)

    out0 = _run_check()
    chk("개인정보 파기(prune-personal)가 한 번도 실행되지 않았습니다" in out0,
        "★★★ manage.py check — 예약이 없으면(첫 실행 전) 실제로 경고한다"
        "(고치기 전엔 이 항목 자체가 없어 아무 경고도 없었다)", None)

    #  ⚠ --dry-run 은 "실행됐다"는 표식을 남기면 안 된다 — 미리보기일 뿐이다.
    M.cmd_prune_personal(["--dry-run"])
    chk(_lock_row() is None,
        "★★ --dry-run 뒤에도 표식이 안 남는다(미리보기를 실제 실행으로 착각 안 함)", None)

    M.cmd_prune_personal([])
    lock1 = _lock_row()
    chk(lock1 is not None,
        "★★★ 실제 실행(빈 DB · 파기 대상 0건) 뒤에는 표식이 남는다"
        "(대상이 0건이어도 '돌긴 돌았다'가 남아야 한다)", lock1)

    out1 = _run_check()
    chk("개인정보 파기(prune-personal)가 한 번도 실행되지 않았습니다" not in out1,
        "★★ 실행 뒤에는 '한 번도 실행되지 않았다' 경고가 사라진다", None)
    chk("개인정보 파기 예약 정상" in out1,
        "★★ 실행 뒤에는 정상 표시로 바뀐다", None)

    #  ⚠ 오래 안 돈 경우(주 1회 예정인데 10일 넘게 정지)도 잡아야 한다 — 표식 시각을
    #    직접 되돌려 재현한다(실제로는 예약이 며칠간 안 돈 상황과 같다).
    conn = DB.get_db()
    conn.execute(
        "UPDATE job_locks SET last_run_at=datetime('now','+9 hours','-15 days') "
        "WHERE name='prune_personal'")
    conn.commit(); conn.close()
    out2 = _run_check()
    chk("일째 실행되지 않았습니다" in out2 and "개인정보 파기" in out2,
        "★★★ manage.py check — 15일째 정지된 예약도 잡는다(고치기 전엔 이런 개념 자체가 없었다)",
        None)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드65 실측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
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
