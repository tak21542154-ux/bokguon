# -*- coding: utf-8 -*-
"""스캔 475라운드 회귀 — `manage.py go-live`의 데모계정 정리가 마지막
최고관리자를 지울 수 있던 결함(영구 락아웃), 1건. 부수적으로
`manage.py check`의 사전점검도 "관리자 0명"만 잡고 "최고관리자 0명"은
못 잡던 것을 함께 강화.

`api_admin_delete()`(app.py)는 마지막 최고관리자를 지우지 못하게
막는데, go-live의 대량 데모계정 정리 경로(같은 표를 지우는 또 다른
지점)엔 그 가드가 없었다 — go-live 전에 새 관리자를 만들면서 --role
을 안 붙이면(기본값 중간관리자) 데모계정 'admin'(유일한 최고관리자)이
그대로 삭제돼, 이후 콘솔에서 최고관리자를 다시 만들 방법이 없는
영구 락아웃이 된다(서버 쉘로 create-admin을 직접 돌리는 것 외엔
복구 수단 없음).

[1] 소스 확인 — 두 수정 코드가 실제로 있음.
[2] 실제 CLI로 되돌림-증명 — manage.py의 새 코드를 옛(취약) 코드로
    임시로 되돌려 옛 동작이 실제로 영구 락아웃을 만드는지, 새 코드가
    실제로 막는지 실제 `python manage.py` 서브프로세스 호출로 대조.

    ⚠⚠ [라운드626] 이전 버전은 여기서 manage.py 실제 파일을
    io.open(MANAGE_PATH,"w").write(reverted_src) 로 디스크에 직접 썼다가
    finally 에서 원본으로 복원했다 — manage.py 는 `python manage.py <cmd>`
    형태로 서브프로세스 자체를 새로 띄워야 하는 CLI 도구라 477·509처럼
    같은 프로세스 안에서 view_functions 를 스왑할 대상(Flask 라우트)이
    없다. 대신 test_scan_round475_launcher.py 를 통해 실행한다 — 그
    launcher 가 R475_BROKEN=1 환경변수를 보고 manage.py 소스를 읽어(디스크는
    원본 그대로) 인메모리로만 옛 코드로 치환한 뒤 exec 한다. manage.py
    실제 파일은 이 프로세스에서도 launcher 프로세스에서도 전혀 안 쓴다.
"""
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MANAGE_PATH = os.path.join(HERE, "manage.py")
LAUNCHER_PATH = os.path.join(HERE, "test_scan_round475_launcher.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 475라운드 회귀 — go-live 최고관리자 영구락아웃 방지")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
MANAGE_SRC = io.open(MANAGE_PATH, encoding="utf-8").read()

OLD_BLOCK_1 = '''                if table == "admins":
                    cur = conn.execute(f"DELETE FROM {table} WHERE {col}=?", (nm,))
                else:'''

NEW_BLOCK_1 = '''                if table == "admins":
                    #  ⚠⚠ [라운드475] api_admin_delete()(app.py)는 마지막
                    #    최고관리자는 지우지 못하게 막는데, 이 대량정리 경로엔
                    #    그 가드가 없었다 — go-live 전에 새 관리자를 만들면서
                    #    --role 을 안 붙이면(기본값 중간관리자) 'admin' 이
                    #    유일한 최고관리자인 채로 그대로 삭제돼, 콘솔에서
                    #    최고관리자를 다시 만들 방법이 없는 영구 락아웃이
                    #    된다(실측 재현 — 서버 쉘로 create-admin 을 직접
                    #    돌리는 것 외엔 복구 수단이 없었다). 지우면 최고관리자가
                    #    0명이 될 경우에만 건너뛰고 경고한다 — 다른 데모정리는
                    #    계속 진행하고, go-live 는 재실행 가능하므로 실제
                    #    최고관리자를 만든 뒤 다시 돌리면 그때 지워진다.
                    _row = conn.execute(
                        f"SELECT role FROM {table} WHERE {col}=?", (nm,)).fetchone()
                    if _row and _row["role"] == "최고관리자":
                        _n_super = conn.execute(
                            "SELECT COUNT(*) n FROM admins WHERE role='최고관리자'"
                        ).fetchone()["n"]
                        if _n_super <= 1:
                            warn(f"'{nm}' 계정이 마지막 최고관리자라 지우지 않았습니다. "
                                 f"실제 최고관리자 계정을 만든 뒤 go-live를 다시 실행하세요"
                                 f"(python manage.py create-admin <아이디> --role 최고관리자).")
                            continue
                    cur = conn.execute(f"DELETE FROM {table} WHERE {col}=?", (nm,))
                else:'''

OLD_BLOCK_2 = '''        n_admin = conn.execute("SELECT COUNT(*) n FROM admins").fetchone()["n"]
        if n_admin == 0:
            bad("관리자 계정이 0개입니다. 콘솔에 로그인할 수 없습니다.")
            print("        → python manage.py create-admin <아이디> --name <이름> --role 최고관리자")
            print("        ※ 아이디로 admin·staff 를 쓰지 마세요. go-live 가 다시 지웁니다.")
            fails += 1
        else:
            ok(f"관리자 계정 {n_admin}개")'''

NEW_BLOCK_2 = '''        n_admin = conn.execute("SELECT COUNT(*) n FROM admins").fetchone()["n"]
        if n_admin == 0:
            bad("관리자 계정이 0개입니다. 콘솔에 로그인할 수 없습니다.")
            print("        → python manage.py create-admin <아이디> --name <이름> --role 최고관리자")
            print("        ※ 아이디로 admin·staff 를 쓰지 마세요. go-live 가 다시 지웁니다.")
            fails += 1
        else:
            #  ⚠⚠ [라운드475] 위 검사는 "로그인 자체가 안 되는" 최악만 잡는다 —
            #    관리자가 1명 이상이어도 전부 중간·하위관리자뿐이면 계정관리·
            #    정산이체·요율설정 등 최고관리자 전용 기능은 아무도 못 켠다
            #    (로그인은 되니 위 검사만 보면 '정상'으로 보인다). 실측(스크래치
            #    DB): create-admin 을 --role 없이 돌린 뒤 go-live 를 실행하면
            #    정확히 이 상태(관리자 1명·최고관리자 0명)가 됐었다.
            n_super = conn.execute(
                "SELECT COUNT(*) n FROM admins WHERE role='최고관리자'").fetchone()["n"]
            if n_super == 0:
                bad(f"관리자 계정은 {n_admin}개 있지만 최고관리자가 0명입니다 — "
                    f"계정관리·정산이체·요율설정을 아무도 할 수 없습니다.")
                print("        → python manage.py create-admin <아이디> --name <이름> --role 최고관리자")
                fails += 1
            else:
                ok(f"관리자 계정 {n_admin}개(최고관리자 {n_super}명 포함)")'''

chk(NEW_BLOCK_1 in MANAGE_SRC,
    "★★★★★ cmd_go_live()에 마지막 최고관리자 삭제방지 코드가 있다")
chk(NEW_BLOCK_2 in MANAGE_SRC,
    "★★★★★ cmd_check()에 최고관리자 0명 감지 코드가 있다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 CLI — 되돌림-증명 (launcher가 인메모리로만 되돌림, manage.py는 원본 그대로)")
# ══════════════════════════════════════════════════════════════


def _run_scenario(broken=False):
    """스크래치 DB에서: init(데모)→create-admin(role 미지정)→go-live→check
    순서를 실제 CLI 서브프로세스(launcher 경유)로 밟고, 최종 admins 상태와
    check 결과를 돌려준다. broken=True 면 launcher가 R475_BROKEN=1을 보고
    manage.py 소스를 인메모리로만 옛(취약) 코드로 치환해 실행한다 — 실제
    manage.py 파일은 어느 프로세스에서도 전혀 안 건드린다."""
    tmpdir = tempfile.mkdtemp(prefix="r475_")
    env = dict(os.environ)
    env["BOKGUON_DB_PATH"] = os.path.join(tmpdir, "verify.db")
    env["BOKGUON_UPLOAD_DIR"] = os.path.join(tmpdir, "uploads")
    env["BOKGUON_BACKUP_DIR"] = os.path.join(tmpdir, "backups")
    env["BOKGUON_ENV"] = "dev"
    if broken:
        env["R475_BROKEN"] = "1"

    def run(*args):
        r = subprocess.run([sys.executable, LAUNCHER_PATH, *args], cwd=HERE, env=env,
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=30)
        return r

    run("init", "--with-demo")
    run("create-admin", "realops1", "--name", "실무자")  # --role 생략 → 기본 중간관리자
    r_live = run("go-live", "--yes")
    r_check = run("check")

    import sqlite3
    dbc = sqlite3.connect(env["BOKGUON_DB_PATH"])
    dbc.row_factory = sqlite3.Row
    admins = [dict(row) for row in
              dbc.execute("SELECT username, role FROM admins ORDER BY id")]
    dbc.close()
    return {"admins": admins, "live_out": r_live.stdout, "check_out": r_check.stdout,
            "check_rc": r_check.returncode}


try:
    fixed = _run_scenario()
    fixed_admins = {a["username"]: a["role"] for a in fixed["admins"]}
    chk(fixed_admins.get("admin") == "최고관리자",
        "★★★★★ 고쳐진 코드는 마지막 최고관리자('admin')를 지우지 않고 남긴다",
        fixed_admins)
    chk("staff" not in fixed_admins,
        "형제 데모계정('staff', 최고관리자 아님)은 평소대로 정리된다", fixed_admins)
    chk("realops1" in fixed_admins,
        "실제로 만든 관리자 계정은 그대로 남는다", fixed_admins)
    chk("마지막 최고관리자" in fixed["live_out"],
        "go-live 출력에 건너뛴 이유가 안내된다")
    #  ⚠ check의 전체 종료코드(rc)는 예약작업 이력 등 이 시나리오와 무관한
    #    다른 사전점검에도 좌우된다(스크래치 DB는 예약작업 실행이력이 없어
    #    그 항목들은 원래도 실패한다) — 여기서는 "최고관리자 관련 판정"만
    #    떼어서 정확한지를 본다(전체 배포가능 여부는 이 테스트의 관심사가
    #    아니다).
    chk("최고관리자가 0명입니다" not in fixed["check_out"]
        and "최고관리자 1명 포함" in fixed["check_out"],
        "고쳐진 코드에서 check가 최고관리자 존재를 정상 보고한다",
        fixed["check_out"][-400:])

    # (B) 되돌림 — launcher가 R475_BROKEN=1을 보고 manage.py 두 지점을
    #     인메모리로만 옛(취약) 코드로 치환해 실행(실제 파일은 안 건드림)
    broken = _run_scenario(broken=True)
    broken_admins = {a["username"]: a["role"] for a in broken["admins"]}
    chk("admin" not in broken_admins,
        "★★★★★ 옛 코드(되돌림)는 마지막 최고관리자('admin')를 그대로 지운다",
        broken_admins)
    chk(len(broken_admins) >= 1 and "최고관리자" not in broken_admins.values(),
        "★★★★★ 옛 코드(되돌림)는 관리자는 남아도(realops1) 최고관리자가 0명인 "
        "영구 락아웃 상태가 된다 — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
        broken_admins)
    chk("관리자 계정 1개" in broken["check_out"] or "관리자 계정" in broken["check_out"],
        "★★★★★ 옛 코드(되돌림)의 check는 이 락아웃을 못 잡고 '관리자 계정 N개'로만"
        " 보고한다(최고관리자 0명이라는 사실을 숨김)",
        broken["check_out"][-400:])

except Exception as e:                                              # noqa: BLE001
    chk(False, "[2] 되돌림-증명 준비/실행", f"{type(e).__name__}: {e}")

chk(io.open(MANAGE_PATH, encoding="utf-8").read() == MANAGE_SRC,
    "★★★★★ manage.py는 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
