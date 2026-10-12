# -*- coding: utf-8 -*-
"""스캔 287라운드 회귀 — gunicorn_conf.py 결함 2건
   (gunicorn_conf.py·wsgi.py 사상 첫 정밀조사 — wsgi.py 는 실측 결과 클린,
   gunicorn_conf.py 에서만 정밀조사 Agent가 발견 후 독립 재검증).

  [1] threads = 4 가 하드코딩돼 있었다 — .env.example(23행)에 BOKGUON_THREADS=8
      이 이미 있고 형제 진입점 serve_waitress.py(23행)는 실제로
      `int(os.environ.get("BOKGUON_THREADS", "8"))` 로 읽는데, 이 파일만
      환경변수를 아예 안 봤다. .env.example 에서 이 변수가 바로 옆
      BOKGUON_BIND·BOKGUON_WORKERS(gunicorn 전용, 실제로 읽힘)와 같은
      구역에 있어, 운영자가 이 값을 올려도(예: BOKGUON_THREADS=32) gunicorn
      은 경고·로그 없이 계속 4로 돈다 — "조용히 버려지는 설정"이었다.
      형제와 같은 변수를 읽도록 통일(기본값 4는 유지 — 이미 이 값으로
      운영 중인 배포의 동작은 안 바꿈).

  [2] "요청 헤더 크기 제한(헤더 기반 DoS 완화)"라는 주석 아래 세 값
      (limit_request_line=4094 · limit_request_fields=100 ·
      limit_request_field_size=8190)이 gunicorn 23.0.0(requirements.txt 로
      고정된 그 버전) 자체 기본값과 완전히 동일했다(실측: gunicorn 공식
      소스의 LimitRequestLine/Fields/FieldSize 클래스 default 값과 대조) —
      즉 이 블록은 실제로는 아무것도 강화하지 않는데 주석은 마치 기본보다
      더 강화된 값을 쓰는 것처럼 읽혔다. 값 자체를 더 좁히는 것은 실제
      트래픽을 보지 않고는 못 정하는 보안정책 결정이라 이번 범위 밖 —
      "왜 기본값과 같은 값을 굳이 명시했는지"(향후 gunicorn 버전업에도
      조용히 안 바뀌게 고정)를 정확히 말하도록 주석만 정정.

  ⚠ 이 테스트는 gunicorn_conf.py 를 순수 설정 모듈로 직접 로드한다
    (gunicorn 자체는 이 Windows 개발기에 설치돼 있지 않다 — 확인됨).
    운영 환경변수는 전혀 건드리지 않는다(테스트 안에서만 세팅·정리).

      python test_scan_round287_fixes.py
"""
import importlib.util
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


GC_SRC = read("gunicorn_conf.py")

print("=" * 72)
print("  스캔 287라운드 회귀 — gunicorn_conf.py 무시되는 설정·오해소지 주석")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk('os.environ.get("BOKGUON_THREADS"' in GC_SRC,
    "★★★★★ threads 가 BOKGUON_THREADS 환경변수를 읽는다(고치기 전엔 하드코딩 4)")
chk("gunicorn 23.0.0 자체 기본값과 완전히 동일하다" in GC_SRC,
    "★★★★ 헤더 상한 주석이 '기본값과 동일하다'는 사실을 정확히 말한다"
    "(고치기 전엔 강화된 값처럼 오해할 수 있는 문구였다)")


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "gunicorn_conf_r287", os.path.join(HERE, "gunicorn_conf.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ============================================================
print("\n[2] 실행 — BOKGUON_THREADS 를 실제로 설정하면 gunicorn 설정에 반영되는가")
# ------------------------------------------------------------
_orig = os.environ.get("BOKGUON_THREADS")
try:
    os.environ["BOKGUON_THREADS"] = "16"
    m = _load_module()
    chk(m.threads == 16,
        "★★★★★★ BOKGUON_THREADS=16 을 설정하면 gunicorn 의 threads 가 실제로 16이 된다"
        "(고치기 전엔 무엇을 넣어도 조용히 4로 고정됐다)", m.threads)
finally:
    if _orig is None:
        os.environ.pop("BOKGUON_THREADS", None)
    else:
        os.environ["BOKGUON_THREADS"] = _orig

# ============================================================
print("\n[3] 실행 — 회귀 없음: 환경변수가 없으면 기존 기본값(4)을 그대로 유지하는가")
# ------------------------------------------------------------
_orig2 = os.environ.pop("BOKGUON_THREADS", None)
try:
    m2 = _load_module()
    chk(m2.threads == 4,
        "STEP BOKGUON_THREADS 미설정 시 기존 기본값 4 를 그대로 유지한다"
        "(이미 이 값으로 운영 중인 배포의 동작을 안 바꿈)", m2.threads)
finally:
    if _orig2 is not None:
        os.environ["BOKGUON_THREADS"] = _orig2

# ============================================================
print("\n[4] 실행 — 회귀 없음: 헤더 상한 값 자체는 그대로인가(주석만 고침, 값은 안 바꿈)")
# ------------------------------------------------------------
try:
    m3 = _load_module()
    # ⚠ 아래 세 숫자는 이 라운드가 gunicorn 23.0.0 공식 소스(config.py 의
    #   LimitRequestLine/Fields/FieldSize.default)에서 직접 대조해 확인한
    #   값이다 — requirements.txt 가 이 버전으로 고정돼 있는 한 유효하다.
    chk((m3.limit_request_line, m3.limit_request_fields, m3.limit_request_field_size)
        == (4094, 100, 8190),
        "★★★★ 헤더 상한 세 값은 그대로 유지된다(gunicorn 23.0.0 자체 기본값과 동일 — "
        "이번 수정은 주석만 정정했지 값은 안 바꿨다)",
        (m3.limit_request_line, m3.limit_request_fields, m3.limit_request_field_size))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드287 [4] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 실행 — 회귀 없음: bind/workers 등 다른 환경변수 기반 설정은 그대로 동작하는가")
# ------------------------------------------------------------
_orig_bind = os.environ.get("BOKGUON_BIND")
try:
    os.environ["BOKGUON_BIND"] = "0.0.0.0:9999"
    m4 = _load_module()
    chk(m4.bind == "0.0.0.0:9999", "STEP BOKGUON_BIND 는 이번 수정과 무관하게 여전히 정상 반영된다",
        m4.bind)
finally:
    if _orig_bind is None:
        os.environ.pop("BOKGUON_BIND", None)
    else:
        os.environ["BOKGUON_BIND"] = _orig_bind

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
