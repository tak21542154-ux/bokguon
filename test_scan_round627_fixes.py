# -*- coding: utf-8 -*-
"""스캔 627라운드 회귀 — `manage.py go-live`가 데모 발주처(insurers,
is_demo=1 전량)를 통째로 지우면서도, 남은 실제 발주처가 몇 곳인지(0곳
포함) 사후 요약 어디에도 안 보여주던 결함, 1건.

배경 — round406이 다른 조사(공유 verify.db 시딩 경쟁조건) 도중 이 사실을
관찰만 하고 "407 이후 별도 판단 대상"으로 미뤄 뒀다: "manage.py go-live가
partners는 명시적으로 보호하면서 insurers(DEMO_TABLES 소속, is_demo=1
전량)는 정리 후 '최소 1곳은 남았는지' 경고가 없다". round475는 형제
표(admins)의 정확히 같은 모양 결함(마지막 최고관리자 삭제)을 고치며
사후요약에 "관리자 계정이 하나도 없습니다" 경고 + 정확한 복구 명령까지
넣었는데, insurers 는 그 형제 취급을 받은 적이 없다. round626이 바로 이
세션에서 운영DB를 읽기전용으로 실측한 수치(활성 발주처 7곳 중 6곳이
is_demo=1)를 그대로 가져와 확인하면, 오늘 go-live를 실행하면 실제로 1곳만
남는데도 화면 어디에도 안 나온다 — partners(`ok(f"협력업체 {n_partner}개사
유지됨")`)·admins(0명이면 경고) 둘 다 있는 요약 줄이 insurers 에는 통째로
빠져 있다(직접 Read로 확인, manage.py cmd_go_live() 사후요약 블록 전체).

고침 — 삭제 로직 자체는 전혀 안 바꾼다(정책 변경 아님, round624/625/626이
이미 확정한 is_demo 기준 그대로). ②단계(트랜잭션 안, admins·partners
카운트와 나란히) 직후에 `n_insurer` 를 한 번 더 세고, 트랜잭션이 끝난 뒤
사후요약에 admins와 같은 패턴(0곳이면 경고+정확한 복구 명령
`create-insurer`, 아니면 개수 보고)을 그대로 이식한다 — 새 컬럼·새 정책·새
메커니즘 없음, 이미 있는 카운트 자리에 한 줄 보태는 것뿐.

[1] 소스 확인 — 두 수정 지점이 실제로 있음.
[2] 실제 CLI로 되돌림-증명(round475 launcher 패턴 그대로, manage.py 실제
    파일은 디스크에서 전혀 안 건드림) — 스크래치 DB에서 두 시나리오
    (데모만 있어 go-live 뒤 발주처 0곳 / 실제 발주처 1곳을 미리 만들어
    go-live 뒤에도 1곳 유지) 각각을 고친 코드·되돌린(회귀) 코드로 실행해
    대조.
"""
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MANAGE_PATH = os.path.join(HERE, "manage.py")
LAUNCHER_PATH = os.path.join(HERE, "test_scan_round627_launcher.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 627라운드 회귀 — go-live 사후요약에 발주처(insurers) 잔존 개수 누락")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ══════════════════════════════════════════════════════════════
MANAGE_SRC = io.open(MANAGE_PATH, encoding="utf-8").read()

NEW_BLOCK_1 = '''        n_admin = conn.execute("SELECT COUNT(*) n FROM admins").fetchone()["n"]
        n_partner = conn.execute("SELECT COUNT(*) n FROM partners").fetchone()["n"]
        #  ⚠⚠ [라운드627] round406이 발견하고 미뤄 둔 형제 결함 — 관리자(n_admin)가
        #    0명이면 아래 요약이 경고+복구명령까지 주는데, 바로 위 ②단계가
        #    is_demo=1 전량을 통째로 지우는 insurers(DEMO_TABLES 소속)는 몇 곳이
        #    남았는지 어디에도 안 나온다. round626 실측(운영DB, 읽기전용): 활성
        #    발주처 7곳 중 6곳이 is_demo=1 — 오늘 go-live를 돌리면 실제로 1곳만
        #    남는데도 화면에 안 보인다. 삭제 로직은 그대로 두고(정책 변경 아님),
        #    admins·partners와 나란히 개수만 센다.
        n_insurer = conn.execute("SELECT COUNT(*) n FROM insurers").fetchone()["n"]
    except sqlite3.Error as e:'''

NEW_BLOCK_2 = '''    print("─" * 62)
    #  ⚠⚠ [라운드630] 바로 아래 n_insurer·n_admin과 같은 자리에서 나란히 세던
    #    n_partner만 이 요약 자신에서는 형제 취급을 못 받았다 — round627이
    #    발주처 0명을, round629가 "관리자는 있지만 최고관리자 0명"을 각각
    #    경고로 올렸는데, 바로 이 줄의 협력업체만 n_partner==0이어도 무조건
    #    ok()로 "유지됨"을 찍는다. go-live는 partners 행 자체를 지우지
    #    않지만(문서화된 대로 실제 영업 자산이라 보존 — 로그인 수단만
    #    정리), partners에는 create-admin/create-insurer 같은 CLI가 없어
    #    콘솔에서만 등록·삭제된다 — 누군가 go-live 전에 콘솔에서 협력사를
    #    전부 지웠거나(예: 삭제 기능 테스트) 애초에 한 곳도 등록하지 않은
    #    채(흔한 첫 배포 실수: init 직후 바로 go-live부터 돌리는 순서) go-live를
    #    돌리면 — 낙찰받아 공사를 진행할 업체가 하나도 없어 사건을 아무도
    #    처리 못 하는, n_insurer==0(사건 등록 불가)·n_super==0(관리 기능
    #    불가)과 정확히 같은 급의 운영 정지 상태인데도 화면은 초록만
    #    보여준다. 삭제 로직·판정 기준은 그대로 두고(정책 변경 아님) 개수만
    #    보고 형제와 같은 모양(if 0: warn 아니면 ok)으로 맞춘다. 복구 명령은
    #    CLI가 없으므로 콘솔 화면 이름을 안내한다.
    if n_partner == 0:
        warn("협력업체가 하나도 남지 않았습니다 — 낙찰받아 공사를 진행할 업체가 없습니다. 반드시 등록하세요:")
        print("      콘솔 로그인 → [업체 등록·관리] → + 업체 등록")
    else:
        ok(f"협력업체 {n_partner}개사 유지됨")
    if n_insurer == 0:
        warn("발주처(보험사) 계정이 하나도 남지 않았습니다 — 사건을 등록할 곳이 없습니다. 반드시 만드세요:")
        print("      python manage.py create-insurer <기관명> <로그인ID>")
    else:
        ok(f"발주처 {n_insurer}개사 유지됨")
    if n_admin == 0:
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

#  ⚠⚠ [라운드629/630] round629이 바로 이 두 블록이 지키는 자리(n_admin 계열 세 줄 앞·
#    사후요약의 admins 분기 안)에 n_super(최고관리자 수) 계산과 "관리자는 있지만
#    최고관리자 0명" 경고를 보탰다 — NEW_BLOCK_1은 그 앞에 새 줄을 끼워 넣어
#    영향이 없었지만(직접 재현: 629 적용 직후 이 블록만 잠깐 어긋남을 확인 후
#    n_super 계산 위치를 n_admin 블록 **앞**으로 옮겨 되돌림-불필요하게 정리),
#    NEW_BLOCK_2는 admins의 else 분기 자체를 629가 바꿔서 이 상수도 함께
#    올려야 했다 — round627 자신이 세운 관례(형제가 이미 아는 것을 이 요약도
#    알아야 한다)를 629가 이었을 뿐, 이 파일이 검증하는 "발주처 0곳/개수 보고"
#    동작 자체는 전혀 안 바뀌었다(아래 [2]의 실제 CLI 시나리오가 그대로 통과).
#    round630은 바로 이 NEW_BLOCK_2의 맨 앞(협력업체 줄)에 자신의 if/else를
#    보탰다 — round629와 같은 이유로 이 상수도 다시 올려야 문자 단위로
#    일치한다. 이 파일이 검증하는 "발주처 0곳/개수 보고" 동작 자체는
#    이번에도 전혀 안 바뀌었다.
chk(NEW_BLOCK_1 in MANAGE_SRC,
    "★★★★★ cmd_go_live()가 트랜잭션 안에서 n_insurer를 센다")
chk(NEW_BLOCK_2 in MANAGE_SRC,
    "★★★★★ cmd_go_live() 사후요약이 발주처 0곳을 경고하거나 개수를 보고한다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 CLI — 되돌림-증명(launcher가 인메모리로만 되돌림, manage.py는 원본 그대로)")
# ══════════════════════════════════════════════════════════════


def _run_scenario(add_real_insurer, broken=False):
    """스크래치 DB에서: init(데모)→[선택: create-insurer 로 실제 발주처 1곳
    추가]→go-live 순서를 실제 CLI 서브프로세스(launcher 경유)로 밟고, 최종
    insurers 상태와 go-live 출력을 돌려준다. broken=True 면 launcher가
    R627_BROKEN=1을 보고 manage.py 소스를 인메모리로만 옛(회귀 전) 코드로
    치환해 실행한다 — 실제 manage.py 파일은 어느 프로세스에서도 안 건드린다."""
    tmpdir = tempfile.mkdtemp(prefix="r627_")
    env = dict(os.environ)
    env["BOKGUON_DB_PATH"] = os.path.join(tmpdir, "verify.db")
    env["BOKGUON_UPLOAD_DIR"] = os.path.join(tmpdir, "uploads")
    env["BOKGUON_BACKUP_DIR"] = os.path.join(tmpdir, "backups")
    env["BOKGUON_ENV"] = "dev"
    if broken:
        env["R627_BROKEN"] = "1"

    def run(*args):
        return subprocess.run([sys.executable, LAUNCHER_PATH, *args], cwd=HERE, env=env,
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=30)

    run("init", "--with-demo")
    if add_real_insurer:
        run("create-insurer", "R627실보험", "r627real")
    r_live = run("go-live", "--yes")

    import sqlite3
    dbc = sqlite3.connect(env["BOKGUON_DB_PATH"])
    dbc.row_factory = sqlite3.Row
    insurers = [dict(row) for row in
                dbc.execute("SELECT name, is_demo FROM insurers ORDER BY id")]
    dbc.close()
    return {"insurers": insurers, "live_out": r_live.stdout, "live_rc": r_live.returncode}


try:
    # (A) 고쳐진 코드 — 시나리오1: 데모만 있던 DB → go-live 뒤 발주처 0곳 → 경고
    fixed_zero = _run_scenario(add_real_insurer=False)
    chk(fixed_zero["insurers"] == [],
        "시나리오1 준비 확인 — go-live 뒤 실제로 발주처가 0곳 남았다(데모 6곳 전부 삭제)",
        fixed_zero["insurers"])
    chk("발주처(보험사) 계정이 하나도 남지 않았습니다" in fixed_zero["live_out"],
        "★★★★★ 고쳐진 코드 — 발주처 0곳이면 go-live 출력에 경고가 실제로 뜬다",
        fixed_zero["live_out"][-500:])
    chk("python manage.py create-insurer" in fixed_zero["live_out"],
        "★★★★★ 고쳐진 코드 — 경고에 정확한 복구 명령(create-insurer)이 함께 뜬다",
        fixed_zero["live_out"][-500:])

    # (B) 고쳐진 코드 — 시나리오2: 실제 발주처 1곳을 미리 만들어 둠 → go-live 뒤도 1곳 유지 → 개수 보고
    fixed_one = _run_scenario(add_real_insurer=True)
    _real_left = [r for r in fixed_one["insurers"] if not r["is_demo"]]
    chk(len(fixed_one["insurers"]) == 1 and len(_real_left) == 1
        and _real_left[0]["name"] == "R627실보험",
        "시나리오2 준비 확인 — go-live 뒤 실제 발주처 1곳만 남았다(데모 6곳은 삭제)",
        fixed_one["insurers"])
    chk("발주처 1개사 유지됨" in fixed_one["live_out"],
        "★★★★★ 고쳐진 코드 — 발주처가 1곳 남으면 경고 대신 개수를 보고한다",
        fixed_one["live_out"][-500:])
    chk("발주처(보험사) 계정이 하나도 남지 않았습니다" not in fixed_one["live_out"],
        "고쳐진 코드 — 발주처가 남아 있으면 0곳 경고는 안 뜬다(과잉경보 아님)")

    # (C) 되돌림 — launcher가 R627_BROKEN=1을 보고 manage.py 두 지점을 인메모리로만
    #     옛(회귀 전) 코드로 치환해 실행(실제 파일은 안 건드림)
    broken_zero = _run_scenario(add_real_insurer=False, broken=True)
    chk(broken_zero["insurers"] == [],
        "옛 코드도 삭제 자체는 그대로 한다(회귀는 삭제 로직이 아니라 보고 누락)",
        broken_zero["insurers"])
    chk("발주처" not in broken_zero["live_out"] and "보험사" not in broken_zero["live_out"],
        "★★★★★ 옛 코드(되돌림) — 발주처가 실제로 0곳이 됐는데도 go-live 출력 어디에도 "
        "발주처 관련 언급이 전혀 없다 — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
        broken_zero["live_out"][-500:])

    broken_one = _run_scenario(add_real_insurer=True, broken=True)
    chk(len(broken_one["insurers"]) == 1,
        "옛 코드에서도 실제 발주처 1곳은 그대로 살아남는다(삭제 로직 자체는 무관)",
        broken_one["insurers"])
    chk("발주처" not in broken_one["live_out"] and "보험사" not in broken_one["live_out"],
        "★★★★★ 옛 코드(되돌림) — 발주처가 1곳 남았을 때도 마찬가지로 아무 보고가 없다"
        "(0곳이든 1곳이든 침묵은 똑같다 — 바로 이게 결함)",
        broken_one["live_out"][-500:])

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
