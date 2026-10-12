# -*- coding: utf-8 -*-
"""스캔 286라운드 회귀 — envload.py 대체(fallback) 파서의 인라인 주석 오염 결함
   (envload.py 사상 첫 정밀조사, 정밀조사 Agent가 발견 후 독립 재검증).

  [1] load_dotenv() 는 python-dotenv 가 있으면 그걸 쓰고(23-26행), 없으면 자체
      대체 파서로 넘어간다(32행 이하). 이 대체 파서는 한 줄 전체가 주석인
      경우(`# ...`)만 걸렀지, 값 뒤에 붙는 **인라인 주석**(`KEY=값  # 설명`)은
      전혀 걸러내지 않아 그 문구까지 값에 그대로 붙었다 — 실측:
      `SECRET=abc123  # rotate quarterly` 를 로드하면 저장된 값이
      `'abc123  # rotate quarterly'` 가 됐다. 아무 예외·로그 없이 조용히
      비밀값·설정값이 오염된다 — 이 파일 자신의 독스트링이 경계하는 바로 그
      "진입점마다 파서가 달라 미묘한 사고가 난다"는 문제를, 대체 경로 자신이
      갖고 있었다.
      오늘은 python-dotenv 가 requirements.txt 에 고정 설치돼 있어(실제 설치
      확인됨) 이 경로 자체가 항상 건너뛰어지는 죽은 코드지만, venv 손상 등
      비정상 상황에서 이 경로를 타는 순간 조용히 발현된다. 공백 뒤에 오는
      # 부터 주석으로 잘라내되(정식 dotenv 관례와 맞춤 — # 바로 앞에 공백이
      없으면 값의 일부), 따옴표로 감싼 값은 그 안의 #을 주석으로 보지 않도록
      수정.

  ⚠ 이 테스트는 임시 디렉터리의 격리 .env 파일만 쓴다 — 운영 .env 는 전혀
    건드리지 않는다. sys.modules["dotenv"]=None 으로 대체 파서 경로를 강제
    선택해 그 경로 자체를 직접 검증한다(정밀조사 Agent와 같은 방법).

      python test_scan_round286_fixes.py
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


ENV_SRC = read("envload.py")

print("=" * 72)
print("  스캔 286라운드 회귀 — envload.py 대체파서 인라인주석 오염")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_ld = ENV_SRC.index("def load_dotenv(")
ld_body = ENV_SRC[i_ld:]
chk("_INLINE_COMMENT" in ld_body,
    "★★★★★ 대체 파서가 인라인 주석을 잘라내려 시도한다(고치기 전엔 이 로직 자체가 없었다)")
chk('if v[:1] in ("\'", \'"\'):' in ld_body,
    "★★★★ 따옴표로 감싼 값은 별도로 처리해 그 안의 #을 주석으로 오인하지 않는다")

# ============================================================
print("\n[2] 실행 준비 — python-dotenv 를 강제로 못 쓰게 해 대체 파서 경로만 검증")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
_tmpdir = tempfile.mkdtemp(prefix="round286_")


def _write_env(lines):
    p = os.path.join(_tmpdir, f"t{len(lines)}_{id(lines)}.env")
    io.open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return p


sys.modules["dotenv"] = None
import importlib                                                     # noqa: E402
if "envload" in sys.modules:
    importlib.reload(sys.modules["envload"])
import envload                                                        # noqa: E402


def _load_and_get(key, lines):
    for k in list(os.environ.keys()):
        if k.startswith("R286_"):
            del os.environ[k]
    envload.load_dotenv(_write_env(lines))
    return os.environ.get(key)

# ============================================================
print("\n[3] 실행 — 값 뒤 인라인 주석이 실제로 잘려나가는가(핵심 재현)")
# ------------------------------------------------------------
try:
    got = _load_and_get("R286_SECRET", ["R286_SECRET=abc123  # rotate quarterly"])
    chk(got == "abc123",
        "★★★★★★ 값 뒤 인라인 주석이 실제로 잘려나가 값이 오염되지 않는다"
        "(고치기 전엔 'abc123  # rotate quarterly' 가 그대로 값이 됐다)", got)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드286 [3] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[4] 실행 — 회귀 없음: 이미 확인된 8개 사례가 전부 그대로 유지되는가")
# ------------------------------------------------------------
CASES = [
    ("R286_EQ", "R286_EQ=abc=def==", "abc=def=="),
    ("R286_Q1", "R286_Q1=\"val'ue\"", "val'ue"),
    ("R286_Q2", "R286_Q2='val\"ue'", 'val"ue'),
    ("R286_NOSPACE", "R286_NOSPACE=abc123#nospace", "abc123#nospace"),
    ("R286_EMPTY", "R286_EMPTY=", ""),
    ("R286_WS", "R286_WS=   ", ""),
    ("R286_QHASH", 'R286_QHASH="quoted # not a comment"', "quoted # not a comment"),
    ("R286_NORMAL", "R286_NORMAL=normal_value", "normal_value"),
]
try:
    for key, line, expected in CASES:
        got = _load_and_get(key, [line])
        chk(got == expected, f"STEP 회귀 없음 — {key}", (line, expected, got))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드286 [4] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 실행 — 회귀 없음: 전체행 주석·빈 줄·등호없는 줄이 여전히 안전하게 무시되는가")
# ------------------------------------------------------------
try:
    got = _load_and_get("R286_AFTER", [
        "# 전체행 주석",
        "",
        "garbage no equals sign",
        "R286_AFTER=ok",
    ])
    chk(got == "ok", "STEP 전체행 주석·빈줄·등호없는 줄을 건너뛰고 다음 줄은 정상 로드된다", got)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드286 [5] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[6] 실행 — 회귀 없음: 이미 있는 OS 환경변수를 .env 가 덮어쓰지 않는가")
# ------------------------------------------------------------
try:
    os.environ["R286_PRESET"] = "real_value"
    envload.load_dotenv(_write_env(["R286_PRESET=stale_dotenv_value  # 주석"]))
    got = os.environ.get("R286_PRESET")
    chk(got == "real_value",
        "STEP 이미 설정된 진짜 환경변수는 .env 값(주석 포함)으로 덮어써지지 않는다", got)
    del os.environ["R286_PRESET"]
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드286 [6] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
