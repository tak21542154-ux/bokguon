# -*- coding: utf-8 -*-
"""스캔 272라운드 회귀 — 팝빌 연동점검(popbill_check.py) 결함 2건
   (notify_popbill.py 감사 라운드262의 companion, 이 세션에서 사상 첫
   주조사 — 정밀조사 Agent가 발견, 독립 재검증 후 수정).

  [1] 이 도구는 항상 새 프로세스로 뜨므로, 라운드262가 막은 "키 교체 후
      재시작 전"(notify_popbill._cache 가 옛 키를 든 채 살아있는) 상태를
      이 프로세스 자신은 절대 겪을 수 없다 — 그래서 이 점검이 전부 성공
      으로 끝나도, 그건 "이 프로세스 기준으로는 문제없다"는 뜻일 뿐 이미
      떠 있는 운영 서버(app.py)가 재시작됐다는 보장이 아니다. 이 사실을
      한 줄도 알리지 않아 운영자가 이 도구의 성공을 운영 서버의 성공으로
      오인할 수 있었다(실측: 두 프로세스를 나란히 흉내내 재현). 매번
      알리는 경고를 추가.

  [2] 자체 .env 파서가 모든 진입점이 공유하는 envload.py 와 달리 값의
      따옴표를 안 벗겼다 — POPBILL_LINK_ID="ABC" 처럼 따옴표를 쓴 .env 를
      쓰면 이 도구만 따옴표까지 낀 값을 읽어 "LinkID 가 틀렸습니다"라는
      오탐을 낸다(실측). "서버와 같은 값으로 점검한다"는 이 함수 자신의
      목적을 지키려면 서버가 실제로 쓰는 그 로더(envload.load_dotenv)에
      위임해야 한다.

      python test_scan_round272_fixes.py
"""
import contextlib
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


SRC = read("popbill_check.py")

print("=" * 72)
print("  스캔 272라운드 회귀 — popbill_check.py 재시작인지불가·env파서분기")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk("import envload" in SRC,
    "★★★★ popbill_check.py 가 공유 .env 로더 모듈을 가져온다")

i_load = SRC.index("def _load_env():")
i_load_end = SRC.index("\n\n\ndef ", i_load)
load_body = SRC[i_load:i_load_end]
chk("envload.load_dotenv()" in load_body and "os.environ.setdefault" not in load_body,
    "★★★★★ _load_env() 가 자체 파싱 대신 공유 로더에 위임한다"
    "(고치기 전엔 따옴표를 안 벗기는 자체 파서였다)")

i_main = SRC.index("def main():")
i_banner_end = SRC.index("# ── 1. 키", i_main)
banner_region = SRC[i_main:i_banner_end]
chk("이미 떠 있는 운영 서버(app.py)도 반드시" in banner_region,
    "★★★★★ 매 실행마다 운영 서버 재시작 필요성을 알리는 경고가 배너 직후에 있다"
    "(고치기 전엔 이런 문구가 전무했다 — '재시작'이라는 단어 자체가 없었다)")

# ============================================================
print("\n[2] 실행 — .env 따옴표 값을 공유 로더를 통해(popbill_check 경로로) 벗기는가")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
try:
    import envload
    import popbill_check as PC

    _tmpdir = tempfile.mkdtemp(prefix="round272_")
    fake_env = os.path.join(_tmpdir, ".env")
    with open(fake_env, "w", encoding="utf-8") as f:
        f.write('POPBILL_LINK_ID="R272-QUOTED-VALUE"\n')

    _orig_env_path = envload._ENV_PATH
    envload._ENV_PATH = fake_env
    os.environ.pop("POPBILL_LINK_ID", None)
    try:
        PC._load_env()
    finally:
        envload._ENV_PATH = _orig_env_path

    chk(os.environ.get("POPBILL_LINK_ID") == "R272-QUOTED-VALUE",
        "★★★★★ popbill_check._load_env() 가 공유 로더를 거쳐 따옴표 없는 값을 읽는다"
        "(고치기 전엔 자체 파서가 따옴표까지 그대로 남겨 실제 값과 달라졌다)",
        os.environ.get("POPBILL_LINK_ID"))
    del os.environ["POPBILL_LINK_ID"]
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드272 [2] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — main() 실행 시 실제로 재시작 경고가 화면에 찍히는가")
# ------------------------------------------------------------
try:
    #  ⚠ 이 저장소의 실제 .env 에는 팝빌 자격증명이 비어 있어(실측 확인됨,
    #    라운드272 조사 보고) 아래 실행은 "[1] 키 설정"에서 정상 종료된다 —
    #    그래도 경고 배너는 그보다 먼저 찍혀야 한다(무조건 배너 직후).
    real_argv = sys.argv
    sys.argv = ["popbill_check.py"]
    _out = io.StringIO()
    try:
        with contextlib.redirect_stdout(_out):
            PC.main()
    finally:
        sys.argv = real_argv
    printed = _out.getvalue()
    chk("방금 새로 시작한 이 점검 프로세스 기준" in printed,
        "★★★★★ 실제 실행 화면에 재시작 경고가 찍힌다(자격증명 없이도 이 경고는 먼저 나온다)",
        printed[:300])
    i_warn = printed.index("방금 새로 시작한")
    i_step1 = printed.index("[1]")
    chk(i_warn < i_step1, "STEP 경고가 [1]단계보다 먼저(배너 직후) 나온다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드272 [3] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
