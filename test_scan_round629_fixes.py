# -*- coding: utf-8 -*-
"""스캔 629라운드 회귀 — `manage.py go-live`의 사후요약이 "관리자는 있지만
최고관리자가 0명"인 상태를 그대로 "정상(유지됨)"으로 찍던 결함, 1건
(직접조사, 하위위임 없음. 611~627라운드의 17라운드짜리 마이그레이션
배틀이 끝난 뒤의 순수 신규조사).

배경 — round475는 이미 이 정확한 위험을 실측으로 증명했다: "관리자가
1명 이상이어도 전부 중간·하위관리자뿐이면 계정관리·정산이체·요율설정
등 최고관리자 전용 기능은 아무도 못 켠다"(create-admin을 --role 없이
돌린 뒤 go-live를 실행하면 실제로 이 상태가 재현됨). 그 라운드는 이
위험을 **두 곳**에 심었다 — ① `cmd_check()`(317-337행)의 사전점검에
n_super 분기(관리자 0명과 "관리자는 있지만 최고관리자 0명"을 구분해서
경고), ② `cmd_go_live()`의 ③단계 삭제 루프(2129-2137행)에 "이 삭제 자체가
마지막 최고관리자를 지우면 안 된다"는 가드. round627이 바로 이 함수의
사후요약(3번째 자리)에 n_insurer를 보태며 "형제 요약이 이미 아는 것을
이 요약도 알아야 한다"는 원칙을 세웠는데, 그 원칙이 admins 자신에게는
적용된 적이 없었다 — go-live의 사후요약은 `n_admin == 0` 만 보고, 관리자가
1명 이상이면 최고관리자가 하나도 없어도 무조건 "관리자 계정 N개 유지"
(정상)로 찍는다. ③단계 가드는 "go-live의 삭제 자체가 최고관리자를
0명으로 만드는 것"만 막을 뿐 — go-live를 **돌리기 전부터** 이미
최고관리자가 0명이던 상태(데모 admin/staff가 애초에 없거나 이미
지워진 채, create-admin을 --role 없이 돌려 만든 계정 하나만 있는 흔한
배포 실수)는 그대로 통과시켜 화면에 초록을 찍는다 — round475가
cmd_check()에서 "bad"로 잡는 바로 그 상태를, go-live 자신의 요약에서는
아무도 못 알아챈다.

고침(manage.py, cmd_go_live() 한 함수 두 자리) — 삭제 로직·판정 기준은
전혀 안 바꾼다(정책 변경 아님). 트랜잭션 안에서 n_admin과 나란히 n_super
(role='최고관리자')를 한 번 더 세고, 사후요약에 cmd_check()와 같은 문구
(관리자는 있지만 최고관리자 0명 → 경고+복구명령, 아니면 최고관리자
포함 개수 보고)를 이식한다 — 새 컬럼·새 정책·새 메커니즘 없음.

검증
[1] 소스 확인 — 두 수정 지점이 실제로 있음.
[2] 실제 CLI로 되돌림-증명(round627 launcher 패턴 그대로, manage.py 실제
    파일은 디스크에서 전혀 안 건드림) — 스크래치 DB에서 세 시나리오
    (①관리자 0명 ②관리자 1명·전부 중간관리자 ③관리자 1명·최고관리자
    포함)를 실제 CLI 서브프로세스로 밟아, 고친 코드가 ②만 새로 경고하고
    ①·③은 기존 그대로(회귀 없음) 동작하는지, 되돌린(회귀) 코드는 ②를
    놓치고 침묵하는지(거짓 초록) 대조한다.
"""
import io
import os
import sqlite3
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MANAGE_PATH = os.path.join(HERE, "manage.py")
LAUNCHER_PATH = os.path.join(HERE, "test_scan_round629_launcher.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 629라운드 회귀 — go-live 사후요약이 '관리자는 있지만 최고관리자 0명'을 놓침")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ══════════════════════════════════════════════════════════════
MANAGE_SRC = io.open(MANAGE_PATH, encoding="utf-8").read()

NEW_BLOCK_1 = '''        conn.commit()

        #  ⚠⚠ [라운드629] 바로 아래 n_admin과 같은 자리에 있는 진짜 형제 결함 — round475가
        #    이미 "관리자 1명 이상이어도 전부 중간·하위관리자뿐이면 계정관리·
        #    정산이체·요율설정을 아무도 못 켠다"며 cmd_check()(317-337행)에 n_super
        #    분기를 넣고, 위 ③단계 삭제 루프(2129-2137행)에도 "이 삭제 자체가
        #    마지막 최고관리자를 지우면 안 된다"는 가드를 넣었다 — 그런데 go-live가
        #    **자기 실행 직후 찍는 이 요약**만은 그 형제 취급을 못 받았다. ③단계
        #    가드는 go-live의 삭제가 최고관리자를 0명으로 만드는 것만 막을 뿐, go-live를
        #    돌리기 **전부터** 최고관리자가 0명이던 상태(예: create-admin을 --role
        #    없이 돌려 만든 계정 하나뿐이고 데모 admin/staff는 애초에 없거나 이미
        #    지워진 경우)는 그대로 통과시킨다 — 아래 요약은 n_admin>0 이면 무조건
        #    "관리자 계정 N개 유지"(정상)로 찍어, cmd_check()가 이미 "bad"로 잡는
        #    바로 그 상태를 go-live 자신의 화면에서는 초록으로 보여준다. 다음 줄의
        #    "python manage.py check"가 뒤늦게 잡아 주긴 하지만, round627이 insurers에
        #    적용한 것과 같은 원칙(형제 요약이 이미 아는 것을 이 요약도 알아야 한다)
        #    으로 여기도 맞춘다 — 삭제 로직·판정 기준은 전혀 안 바꾸고 개수만 센다.
        #    n_admin·n_partner·n_insurer 세 줄(round627이 이미 확정한 블록) **앞**에
        #    둔다 — 그 블록 안이나 뒤에 끼우면 round627 자신의 회귀테스트가 소스를
        #    원문 그대로(문자 단위) 대조하는 자리를 깨뜨린다(직접 재현·확인).
        n_super = conn.execute(
            "SELECT COUNT(*) n FROM admins WHERE role='최고관리자'").fetchone()["n"]
        n_admin = conn.execute("SELECT COUNT(*) n FROM admins").fetchone()["n"]'''

NEW_BLOCK_2 = '''    if n_admin == 0:
        warn("관리자 계정이 하나도 없습니다. 반드시 만드세요:")
        print("      python manage.py create-admin <아이디> --role 최고관리자")
        print("      ※ 'admin' 이 아닌 실제 담당자 아이디를 쓰세요.")
    elif n_super == 0:
        #  ⚠⚠ [라운드629] cmd_check()(317-337행)와 같은 기준 — 관리자는 있지만
        #    전부 중간·하위관리자뿐이면 계정관리·정산이체·요율설정을 아무도 못 켠다.
        warn(f"관리자 계정은 {n_admin}개 있지만 최고관리자가 0명입니다 — "
             f"계정관리·정산이체·요율설정을 아무도 할 수 없습니다. 반드시 만드세요:")
        print("      python manage.py create-admin <아이디> --role 최고관리자")
    else:
        ok(f"관리자 계정 {n_admin}개(최고관리자 {n_super}명 포함) 유지")
    print()
    print("  다음 단계:  python manage.py check")'''

chk(NEW_BLOCK_1 in MANAGE_SRC,
    "★★★★★ cmd_go_live()가 트랜잭션 안에서 n_super(최고관리자 수)를 센다")
chk(NEW_BLOCK_2 in MANAGE_SRC,
    "★★★★★ cmd_go_live() 사후요약이 '관리자는 있지만 최고관리자 0명'을 따로 경고한다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 CLI — 되돌림-증명(launcher가 인메모리로만 되돌림, manage.py는 원본 그대로)")
# ══════════════════════════════════════════════════════════════


def _run_scenario(admin_role=None, broken=False):
    """스크래치 DB에서: init(데모 없음)→[선택: create-admin 으로 관리자 1명
    추가, admin_role 로 등급 지정. None 이면 관리자 자체를 안 만든다]→go-live
    순서를 실제 CLI 서브프로세스(launcher 경유)로 밟고, 최종 admins 상태와
    go-live 출력을 돌려준다. broken=True 면 launcher가 R629_BROKEN=1을 보고
    manage.py 소스를 인메모리로만 옛(회귀 전) 코드로 치환해 실행한다 — 실제
    manage.py 파일은 어느 프로세스에서도 안 건드린다."""
    tmpdir = tempfile.mkdtemp(prefix="r629_")
    env = dict(os.environ)
    env["BOKGUON_DB_PATH"] = os.path.join(tmpdir, "verify.db")
    env["BOKGUON_UPLOAD_DIR"] = os.path.join(tmpdir, "uploads")
    env["BOKGUON_BACKUP_DIR"] = os.path.join(tmpdir, "backups")
    env["BOKGUON_ENV"] = "dev"
    if broken:
        env["R629_BROKEN"] = "1"

    def run(*args):
        return subprocess.run([sys.executable, LAUNCHER_PATH, *args], cwd=HERE, env=env,
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=30)

    run("init")  # --with-demo 없음 — 데모 admin/staff가 애초에 존재하지 않는 상태를 만든다
    if admin_role is not None:
        args = ["create-admin", "r629adm"]
        if admin_role:
            args += ["--role", admin_role]
        r_create = run(*args)
        assert r_create.returncode == 0, f"create-admin 준비 실패: {r_create.stdout}{r_create.stderr}"
    r_live = run("go-live", "--yes")

    dbc = sqlite3.connect(env["BOKGUON_DB_PATH"])
    dbc.row_factory = sqlite3.Row
    admins = [dict(row) for row in
              dbc.execute("SELECT username, role FROM admins ORDER BY id")]
    dbc.close()
    return {"admins": admins, "live_out": r_live.stdout, "live_rc": r_live.returncode}


try:
    # (A) 고쳐진 코드 — 시나리오1: 관리자 1명·전부 중간관리자(--role 없이 create-admin)
    #     → 정확히 round475가 실측 재현한 그 상태 → 경고
    fixed_mid = _run_scenario(admin_role="")
    chk(len(fixed_mid["admins"]) == 1 and fixed_mid["admins"][0]["role"] == "중간관리자",
        "시나리오1 준비 확인 — go-live 뒤에도 관리자 1명(중간관리자)이 그대로 남았다"
        "(go-live는 데모 admin/staff가 없으면 이 계정을 건드리지 않는다)",
        fixed_mid["admins"])
    chk("관리자 계정은 1개 있지만 최고관리자가 0명입니다" in fixed_mid["live_out"],
        "★★★★★ 고쳐진 코드 — 관리자 1명뿐이고 전부 중간관리자면 go-live 출력에 경고가 실제로 뜬다",
        fixed_mid["live_out"][-600:])
    chk("python manage.py create-admin" in fixed_mid["live_out"].split("다음 단계")[0],
        "★★★★★ 고쳐진 코드 — 경고에 정확한 복구 명령(create-admin --role 최고관리자)이 함께 뜬다",
        fixed_mid["live_out"][-600:])
    chk("관리자 계정 1개 유지" not in fixed_mid["live_out"],
        "★★★★★ 고쳐진 코드 — 이 상태에서는 예전의 '유지됨'(거짓 초록) 문구가 안 뜬다",
        fixed_mid["live_out"][-600:])

    # (B) 고쳐진 코드 — 대조군: 관리자 1명·최고관리자 → 경고 없이 개수 보고(과잉경보 아님)
    fixed_super = _run_scenario(admin_role="최고관리자")
    chk(len(fixed_super["admins"]) == 1 and fixed_super["admins"][0]["role"] == "최고관리자",
        "대조군 준비 확인 — go-live 뒤 관리자 1명(최고관리자)이 그대로 남았다",
        fixed_super["admins"])
    chk("관리자 계정 1개(최고관리자 1명 포함) 유지" in fixed_super["live_out"],
        "★★★★★ 고쳐진 코드 — 최고관리자가 있으면 경고 대신 개수(최고관리자 포함)를 보고한다",
        fixed_super["live_out"][-600:])
    chk("최고관리자가 0명입니다" not in fixed_super["live_out"],
        "고쳐진 코드 — 최고관리자가 있으면 0명 경고는 안 뜬다(과잉경보 아님)")

    # (C) 고쳐진 코드 — 회귀 없음 확인: 관리자 0명(기존 분기, round629 이전부터 있던 경고)
    fixed_zero = _run_scenario(admin_role=None)
    chk(fixed_zero["admins"] == [],
        "회귀없음 준비 확인 — 관리자를 아예 안 만들면 go-live 뒤에도 0명이다",
        fixed_zero["admins"])
    chk("관리자 계정이 하나도 없습니다" in fixed_zero["live_out"],
        "★★★★★ 고쳐진 코드 — 관리자 0명이면 (round629 이전부터 있던) 기존 경고가 그대로 뜬다"
        "(elif로 붙였으므로 n_admin==0 분기는 회귀 없이 그대로 동작해야 한다)",
        fixed_zero["live_out"][-600:])
    chk("최고관리자가 0명입니다" not in fixed_zero["live_out"],
        "고쳐진 코드 — 관리자 0명일 때는 최고관리자 0명 경고(새 분기)와 안 겹친다(중복경보 아님)")

    # (D) 되돌림 — launcher가 R629_BROKEN=1을 보고 manage.py 두 지점을 인메모리로만
    #     옛(회귀 전) 코드로 치환해 실행(실제 파일은 안 건드림)
    broken_mid = _run_scenario(admin_role="", broken=True)
    chk(len(broken_mid["admins"]) == 1 and broken_mid["admins"][0]["role"] == "중간관리자",
        "옛 코드에서도 삭제 로직은 그대로다(회귀는 삭제가 아니라 보고 누락) — 관리자 1명(중간관리자) 그대로",
        broken_mid["admins"])
    chk("최고관리자가 0명입니다" not in broken_mid["live_out"],
        "★★★★★ 옛 코드(되돌림) — 관리자가 전부 중간관리자인데도 go-live 출력 어디에도 "
        "최고관리자 관련 경고가 전혀 없다 — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
        broken_mid["live_out"][-600:])
    chk("관리자 계정 1개 유지" in broken_mid["live_out"],
        "★★★★★ 옛 코드(되돌림) — 최고관리자가 0명인데도 '관리자 계정 1개 유지'라는 "
        "거짓 초록이 그대로 찍힌다(바로 이게 결함)",
        broken_mid["live_out"][-600:])

    broken_super = _run_scenario(admin_role="최고관리자", broken=True)
    chk(len(broken_super["admins"]) == 1 and broken_super["admins"][0]["role"] == "최고관리자",
        "옛 코드에서도 최고관리자 1명은 그대로 살아남는다(삭제 로직 자체는 무관)",
        broken_super["admins"])
    chk("관리자 계정 1개 유지" in broken_super["live_out"],
        "옛 코드(되돌림) — 최고관리자가 실제로 있을 때는 (문구는 다르지만) 여전히 정상으로 보고한다"
        "(이 대조군에서는 옛 코드도 우연히 틀리지 않는다 — 결함은 오직 '관리자는 있는데 "
        "최고관리자가 없을 때'만 드러난다)")

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
