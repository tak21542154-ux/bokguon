# -*- coding: utf-8 -*-
"""새 DB 가 통째로 만들어지는가 — **새 서버 배포의 첫 관문**.

  왜 따로 있나 —
   운영·검증 DB 는 이미 테이블이 다 있어서, 스키마 SQL 이 깨져도 멀쩡히 돈다.
   깨진 건 **새 서버에 처음 배포할 때만** 드러난다. 그때는 이미 현장이다.

  실제로 겪은 것(2026-08-05):
   `photos.defect_id` 인덱스를 스키마 SQL 에 넣었는데,
    ① photos 테이블 정의보다 **앞**에 둬서 `no such table: main.photos`
    ② 옮겼더니 defect_id 가 **마이그레이션으로 생기는 컬럼**이라 `no such column`
   두 번 다 `executescript` 가 중간에서 죽어 **테이블 절반만 만들어진 DB** 가 남았고,
   보험사 계정 발급이 `insurers has no column named must_change_pw` 로 실패했다.
   기존 DB 로 도는 테스트는 전부 통과했다 — 이 검사만 잡을 수 있었다.

  ⚠ 인덱스가 마이그레이션 컬럼 위에 있으면 SCHEMA 가 아니라 migrate() 쪽에 둔다.
"""
import io
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OK = FAIL = 0


def chk(cond, name, got=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}   {got}")


def main():
    tmp = tempfile.mkdtemp(prefix="bokguon_fresh_")
    db = os.path.join(tmp, "fresh.db")
    try:
        print("[1] 빈 DB 를 처음부터 만든다 (manage.py init)")
        env = dict(os.environ)
        env.update({"BOKGUON_DB_PATH": db, "BOKGUON_ENV": "dev",
                    "BOKGUON_SEED_DEMO": "0", "PYTHONIOENCODING": "utf-8"})
        r = subprocess.run([sys.executable, "manage.py", "init"], cwd=HERE, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        chk(r.returncode == 0, "★ init 이 끝까지 돈다", out.strip().splitlines()[-1:] or "")
        chk("OperationalError" not in out,
            "★ 스키마 실행 중 SQL 오류가 없다(중간에 죽으면 반쪽 DB 가 남는다)",
            [ln for ln in out.splitlines() if "Error" in ln][:2])
        if not os.path.exists(db):
            chk(False, "DB 파일 생성", "파일이 없다")
            return 1

        print("\n[2] 마이그레이션까지 돌린 뒤 스키마가 완전한가")
        subprocess.run([sys.executable, "manage.py", "migrate"], cwd=HERE, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
        conn = sqlite3.connect(db)

        #  운영에서 실제로 쓰는 테이블이 다 있는가
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        need_tables = {"cases", "bids", "auctions", "partners", "insurers", "settlements",
                       "photos", "defects", "dispatches", "dispatch_calls",
                       "field_agreements", "notifications", "standard_boq",
                       "portal_users", "job_locks", "activity_log"}
        missing_t = sorted(need_tables - tables)
        chk(not missing_t, "★ 필수 테이블이 전부 있다", f"없음: {missing_t}")

        #  마이그레이션으로 붙는 컬럼 중 **계정 발급·정산이 곧바로 쓰는** 것들
        def cols(t):
            return {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}

        need_cols = {
            "insurers": {"must_change_pw", "fee_rate_bp", "login_id", "status"},
            "partners": {"must_change_pw", "bank_account_enc", "portal_role", "lat", "lng"},
            "admins": {"must_change_pw", "role"},
            "cases": {"award_amount", "status_at", "victim_phone", "is_demo", "track_token"},
            "photos": {"defect_id", "fix_for", "review_status", "sha256"},
            "settlements": {"fee_rate_bp", "void_status", "double_checked"},
            "notifications": {"audience_type", "send_attempts", "handled_by"},
        }
        for t, need in need_cols.items():
            if t not in tables:
                continue
            miss = sorted(need - cols(t))
            chk(not miss, f"★ {t} 컬럼 완비", f"없음: {miss}")

        #  인덱스도 실제로 만들어지는가(마이그레이션 컬럼 위의 것 포함)
        idx = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        need_idx = {"idx_photo_defect", "idx_photo_case", "idx_defect_case",
                    "idx_auctions_sweep"}
        miss_i = sorted(need_idx - idx)
        chk(not miss_i, "★ 핵심 인덱스가 만들어진다", f"없음: {miss_i}")

        #  예약 실행 감시용 행 — 없으면 배지가 '항상 초록'이 된다
        locks = {r[0] for r in conn.execute("SELECT name FROM job_locks")}
        chk({"auction_sweep", "dispatch_sweep", "cli_sweep"} <= locks,
            "★ 스윕 잠금 3종이 시드된다(cli_sweep 이 없으면 감시 배지가 거짓말한다)",
            sorted(locks))
        conn.close()

        print("\n[3] 그 DB 로 실제 계정을 만들 수 있는가")
        for args, label in (
                (["create-admin", "freshadm", "--name", "검증", "--role", "최고관리자"],
                 "관리자 계정 발급"),
                (["create-insurer", "검증손보", "freshins", "10"], "보험사 계정 발급")):
            r = subprocess.run([sys.executable, "manage.py", *args], cwd=HERE, env=env,
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            o = (r.stdout or "") + (r.stderr or "")
            chk(r.returncode == 0 and "임시 비번" in o, f"★ {label}",
                [ln for ln in o.splitlines() if "Error" in ln or "error" in ln][:2])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("-" * 66)
    print(f"  통과 {OK} · 실패 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
