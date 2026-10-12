# -*- coding: utf-8 -*-
"""스캔 630라운드 회귀 — `manage.py go-live`의 사후요약이 "협력업체가
0개사여도" 그대로 "유지됨"(정상)으로 찍던 결함, 1건(직접조사,
하위위임 없음. 611~629라운드 마이그레이션·미세보수가 끝난 뒤의 순수
신규조사).

배경 — round627은 go-live 사후요약에 발주처(n_insurer) 0명 경고를,
round629는 "관리자는 있지만 최고관리자 0명" 경고를 각각 이식하며
"형제 요약이 이미 아는 것을 이 요약도 알아야 한다"는 원칙을 세웠다.
그런데 바로 그 두 형제와 나란히 같은 트랜잭션에서 함께 세는 세 번째
숫자 — n_partner(협력업체 수) — 만은 이 원칙이 한 번도 적용된 적이
없었다. go-live는 partners 행 자체를 지우지 않지만(문서화된 대로
실제 영업 자산이라 보존 — 로그인 수단·평판만 정리), partners에는
create-admin/create-insurer 같은 CLI가 없어 콘솔에서만 등록·삭제된다.
누군가 go-live 전에 콘솔에서 협력사를 전부 지웠거나(예: 삭제 기능
테스트), 애초에 한 곳도 등록하지 않은 채(흔한 첫 배포 실수: init
직후 바로 go-live부터 돌리는 순서 — 실측: 아래 시나리오 그대로) go-live를
돌리면, 사후요약은 n_partner==0 이어도 무조건 "협력업체 0개사
유지됨"을 초록(ok)으로 찍는다 — 낙찰받아 공사를 진행할 업체가 하나도
없어 사건을 아무도 처리 못 하는, n_insurer==0(사건 등록 불가)·
n_super==0(관리 기능 불가)과 정확히 같은 급의 운영 정지 상태인데도.

고침(manage.py, cmd_go_live() 사후요약 한 자리) — 삭제 로직·판정
기준은 전혀 안 바꾼다(정책 변경 아님). n_insurer·n_admin과 같은 모양
(if 0: warn 아니면 ok)으로 n_partner도 맞춘다. partners에는 CLI가
없으므로 복구 안내는 콘솔 화면 이름([업체 등록·관리])을 가리킨다.

검증
[1] 소스 확인 — 수정 지점이 실제로 있음.
[2] 실제 CLI로 되돌림-증명(round627/629 launcher 패턴 그대로, manage.py
    실제 파일은 디스크에서 전혀 안 건드림) — 스크래치 DB에서 세 시나리오
    (①협력업체 0곳 ②협력업체 1곳 ③되돌린 옛 코드에서의 협력업체 0곳)를
    실제 CLI 서브프로세스로 밟아, 고친 코드가 ①만 새로 경고하고 ②는
    기존 그대로(과잉경보 아님) 동작하는지, 되돌린 코드는 ①에서도
    침묵하며 거짓 초록을 찍는지 대조한다. 같은 사후요약 블록에서
    함께 세는 발주처·관리자 형제 경고가 이 수정으로 옆에서 깨지지
    않았는지도 함께 확인한다(회귀 없음).
"""
import io
import os
import sqlite3
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MANAGE_PATH = os.path.join(HERE, "manage.py")
LAUNCHER_PATH = os.path.join(HERE, "test_scan_round630_launcher.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 630라운드 회귀 — go-live 사후요약이 '협력업체 0개사'를 놓침")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ══════════════════════════════════════════════════════════════
MANAGE_SRC = io.open(MANAGE_PATH, encoding="utf-8").read()

NEW_BLOCK = '''    print("─" * 62)
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
    if n_insurer == 0:'''

chk(NEW_BLOCK in MANAGE_SRC,
    "★★★★★ cmd_go_live() 사후요약이 '협력업체 0개사'를 발주처·관리자와 같은 모양으로 경고한다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 CLI — 되돌림-증명(launcher가 인메모리로만 되돌림, manage.py는 원본 그대로)")
# ══════════════════════════════════════════════════════════════


def _run_scenario(n_partners=0, broken=False):
    """스크래치 DB에서: init(데모 없음, admin·insurer·partner 전부 0)→
    [선택: partners 테이블에 n_partners개 행을 직접 INSERT로 준비]→
    go-live 순서를 실제 CLI 서브프로세스(launcher 경유)로 밟고, 최종
    partners 상태와 go-live 출력을 돌려준다. broken=True 면 launcher가
    R630_BROKEN=1을 보고 manage.py 소스를 인메모리로만 옛(회귀 전) 코드로
    치환해 실행한다 — 실제 manage.py 파일은 어느 프로세스에서도 안 건드린다.
    partners에는 CLI가 없으므로(콘솔 전용 등록) 스크래치 DB에 직접
    INSERT한다 — 이는 실제 콘솔 등록을 흉내 낸 테스트 준비일 뿐, 검증
    대상인 go-live 자신의 삭제 로직과는 무관하다(go-live는 partners 행을
    지우지 않는다는 것이 이 함수가 확인하려는 사실 중 하나이기도 하다)."""
    tmpdir = tempfile.mkdtemp(prefix="r630_")
    env = dict(os.environ)
    env["BOKGUON_DB_PATH"] = os.path.join(tmpdir, "verify.db")
    env["BOKGUON_UPLOAD_DIR"] = os.path.join(tmpdir, "uploads")
    env["BOKGUON_BACKUP_DIR"] = os.path.join(tmpdir, "backups")
    env["BOKGUON_ENV"] = "dev"
    if broken:
        env["R630_BROKEN"] = "1"

    def run(*args):
        return subprocess.run([sys.executable, LAUNCHER_PATH, *args], cwd=HERE, env=env,
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=30)

    r_init = run("init")  # --with-demo 없음 — admin/insurer/partner 전부 애초에 0
    assert r_init.returncode == 0, f"init 준비 실패: {r_init.stdout}{r_init.stderr}"
    if n_partners:
        dbc = sqlite3.connect(env["BOKGUON_DB_PATH"])
        for i in range(n_partners):
            dbc.execute("INSERT INTO partners(name) VALUES(?)", (f"검증협력사{i}",))
        dbc.commit()
        dbc.close()
    r_live = run("go-live", "--yes")

    dbc = sqlite3.connect(env["BOKGUON_DB_PATH"])
    dbc.row_factory = sqlite3.Row
    partners = [dict(row) for row in dbc.execute("SELECT id, name FROM partners ORDER BY id")]
    dbc.close()
    return {"partners": partners, "live_out": r_live.stdout, "live_rc": r_live.returncode}


try:
    # (A) 고쳐진 코드 — 시나리오1: 협력업체 0곳(흔한 첫 배포 순서: init 직후 바로 go-live)
    fixed_zero = _run_scenario(n_partners=0)
    chk(fixed_zero["partners"] == [],
        "시나리오1 준비 확인 — go-live 뒤에도 협력업체가 0곳이다(go-live는 partners 행을 지우지 않는다)",
        fixed_zero["partners"])
    chk("협력업체가 하나도 남지 않았습니다" in fixed_zero["live_out"],
        "★★★★★ 고쳐진 코드 — 협력업체 0곳이면 go-live 출력에 경고가 실제로 뜬다",
        fixed_zero["live_out"][-700:])
    chk("[업체 등록·관리]" in fixed_zero["live_out"],
        "★★★★★ 고쳐진 코드 — 경고에 콘솔 화면 이름(업체 등록·관리)이 함께 뜬다"
        "(CLI가 없으므로 create-* 명령이 아니라 콘솔 경로를 안내해야 한다)",
        fixed_zero["live_out"][-700:])
    chk("협력업체 0개사 유지됨" not in fixed_zero["live_out"],
        "★★★★★ 고쳐진 코드 — 이 상태에서는 예전의 '유지됨'(거짓 초록) 문구가 안 뜬다",
        fixed_zero["live_out"][-700:])
    # 같은 요약 블록의 형제(발주처·관리자) 경고도 옆에서 안 깨졌는지(회귀 없음)
    chk("발주처(보험사) 계정이 하나도 남지 않았습니다" in fixed_zero["live_out"],
        "회귀없음 확인 — round627의 발주처 0명 경고가 이 수정 옆에서도 그대로 뜬다",
        fixed_zero["live_out"][-700:])
    chk("관리자 계정이 하나도 없습니다" in fixed_zero["live_out"],
        "회귀없음 확인 — round629 이전부터 있던 관리자 0명 경고도 그대로 뜬다",
        fixed_zero["live_out"][-700:])

    # (B) 고쳐진 코드 — 대조군: 협력업체 1곳 → 경고 없이 개수 보고(과잉경보 아님)
    fixed_one = _run_scenario(n_partners=1)
    chk(len(fixed_one["partners"]) == 1,
        "대조군 준비 확인 — go-live 뒤 협력업체 1곳이 그대로 남았다(로그인 수단만 정리 대상이나 "
        "이 계정은 데모 이름이 아니라 애초에 정리 대상도 아니다)",
        fixed_one["partners"])
    chk("협력업체 1개사 유지됨" in fixed_one["live_out"],
        "★★★★★ 고쳐진 코드 — 협력업체가 있으면 경고 대신 개수를 보고한다",
        fixed_one["live_out"][-700:])
    chk("협력업체가 하나도 남지 않았습니다" not in fixed_one["live_out"],
        "고쳐진 코드 — 협력업체가 있으면 0곳 경고는 안 뜬다(과잉경보 아님)")

    # (C) 되돌림 — launcher가 R630_BROKEN=1을 보고 manage.py 한 지점을 인메모리로만
    #     옛(회귀 전) 코드로 치환해 실행(실제 파일은 안 건드림)
    broken_zero = _run_scenario(n_partners=0, broken=True)
    chk(broken_zero["partners"] == [],
        "옛 코드에서도 삭제 로직은 그대로다(회귀는 삭제가 아니라 보고 누락) — 협력업체 0곳 그대로",
        broken_zero["partners"])
    chk("협력업체가 하나도 남지 않았습니다" not in broken_zero["live_out"],
        "★★★★★ 옛 코드(되돌림) — 협력업체가 0곳인데도 go-live 출력 어디에도 "
        "협력업체 관련 경고가 전혀 없다 — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
        broken_zero["live_out"][-700:])
    chk("협력업체 0개사 유지됨" in broken_zero["live_out"],
        "★★★★★ 옛 코드(되돌림) — 협력업체가 0곳인데도 '협력업체 0개사 유지됨'이라는 "
        "거짓 초록이 그대로 찍힌다(바로 이게 결함)",
        broken_zero["live_out"][-700:])
    # 되돌린 코드에서도 형제(발주처·관리자) 경고 자체는 살아있다 — 이 회귀가
    # 오직 n_partner 한 자리에만 있다는 것(다른 곳까지 깨진 게 아니라는 것)을 못박는다.
    chk("발주처(보험사) 계정이 하나도 남지 않았습니다" in broken_zero["live_out"]
        and "관리자 계정이 하나도 없습니다" in broken_zero["live_out"],
        "옛 코드(되돌림)에서도 발주처·관리자 형제 경고는 멀쩡하다 — 결함은 오직 협력업체 한 자리",
        broken_zero["live_out"][-700:])

    broken_one = _run_scenario(n_partners=1, broken=True)
    chk(len(broken_one["partners"]) == 1,
        "옛 코드에서도 협력업체 1곳은 그대로 살아남는다(삭제 로직 자체는 무관)",
        broken_one["partners"])
    chk("협력업체 1개사 유지됨" in broken_one["live_out"],
        "옛 코드(되돌림) — 협력업체가 실제로 있을 때는 여전히 정상으로 보고한다"
        "(이 대조군에서는 옛 코드도 우연히 틀리지 않는다 — 결함은 오직 '협력업체가 "
        "0곳일 때'만 드러난다)")

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
