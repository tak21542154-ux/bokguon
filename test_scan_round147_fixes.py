# -*- coding: utf-8 -*-
"""스캔 147라운드 회귀 — 개인정보 처리방침 제2·3조가 "로그인 시도 기록"을
접속IP·일시·User-Agent 와 같은 행에 묶어 "접속 기록(로그) — 2년"으로 공개
약속했는데, 실제 파기 코드(cmd_prune_logs)는 access_log 만 지우고
login_attempts 는 어떤 파기 경로에도 걸리지 않아 무기한 보존되던 결함.

  잠금 판정(_recent_fails)은 LOCKOUT_MINUTES 짜리 최근 창만 보므로, 2년 지난
  행을 지워도 계정 잠금 기능에는 영향이 없다(146라운드처럼 별도 통계 보존
  걱정이 필요 없는, access_log 와 동일 성격의 순수 로그 테이블).

      python test_scan_round147_fixes.py
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
LEGAL_SRC = read("legal_docs.py")

print("=" * 72)
print("  스캔 147라운드 회귀 — 로그인 시도 기록 2년 보유(처리방침) 미이행")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk("로그인 시도 기록" in LEGAL_SRC and "접속 기록(로그)" in LEGAL_SRC,
    "★ (전제) 처리방침이 로그인 시도 기록을 접속기록과 같은 2년 보유항목으로 약속한다")
i_pl = MANAGE_SRC.index("def cmd_prune_logs(")
i_pl_end = MANAGE_SRC.index("\ndef ", i_pl + 1)
pl_body = MANAGE_SRC[i_pl:i_pl_end]
chk("DELETE FROM login_attempts WHERE created_at < ?" in pl_body,
    "★★★ cmd_prune_logs 가 이제 login_attempts 도 같은 기준으로 파기한다")
chk('ok(f"접속기록 {n:,}건 파기")' in pl_body and 'ok(f"로그인 시도기록 {n_login:,}건 파기")' in pl_body,
    "★ 두 테이블의 파기 건수를 각각 보고한다")

# ============================================================
print("\n[2] 실행 — 3년 지난 access_log/login_attempts 를 prune-logs 가 함께 지운다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round147_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import manage as M

    conn = DB.get_db()
    old_ts = "2023-01-01 09:00:00"    # 정책 2년·기본 730일 보관기준을 모두 지난 시점
    recent_ts = DB.now()              # 대조군 — 방금 생긴 기록은 지워지면 안 된다

    conn.execute(
        "INSERT INTO login_attempts(username,ip,success,created_at) "
        "VALUES('old_real_user','1.2.3.4',1,?)", (old_ts,))
    conn.execute(
        "INSERT INTO login_attempts(username,ip,success,created_at) "
        "VALUES('old_attacker_guess','5.6.7.8',0,?)", (old_ts,))
    conn.execute(
        "INSERT INTO login_attempts(username,ip,success,created_at) "
        "VALUES('fresh_user','9.9.9.9',1,?)", (recent_ts,))
    conn.commit()

    before = conn.execute("SELECT COUNT(*) n FROM login_attempts").fetchone()["n"]
    chk(before == 3, "★ (사전조건) 오래된 기록 2건 + 최근 기록 1건이 준비됐다", before)

    rc = M.cmd_prune_logs([])
    chk(rc is None or rc == 0, "STEP cmd_prune_logs 정상 종료", rc)

    old_left = conn.execute(
        "SELECT COUNT(*) n FROM login_attempts WHERE created_at=?", (old_ts,)).fetchone()["n"]
    chk(old_left == 0,
        "★★★ 2년 넘은 로그인 시도 기록(성공 1건 포함)이 이제 파기된다"
        "(고치기 전엔 access_log 만 지워지고 이 테이블은 무기한 보존됐다)", old_left)

    recent_left = conn.execute(
        "SELECT COUNT(*) n FROM login_attempts WHERE created_at=?", (recent_ts,)).fetchone()["n"]
    chk(recent_left == 1,
        "★★★ 아직 보관기간이 안 지난 최근 기록은 그대로 남는다(과잉파기 아님)", recent_left)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드147 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
