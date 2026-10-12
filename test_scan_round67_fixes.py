# -*- coding: utf-8 -*-
"""스캔 67라운드 회귀 — 서버 시간대가 KST 가 아니면(UTC 컨테이너 등) 조용히
   틀어지는 naive datetime.now() 5곳 + 장식으로만 있던 시계 점검(HIGH) +
   manage.py --help 가 실제 명령 20개 중 4개를 안 보여줌(LOW).

  조사 에이전트가 정적 추적(SQLite datetime('now') 는 항상 UTC 기반이라 SQL 쪽은
  이미 안전하다는 사실을 이 기기에서 직접 검증한 뒤, DB.now()/DB.KST 를 안 쓰고
  naive datetime.now() 를 직접 부르는 자리를 전수 조사)으로 짚고, 이번 라운드에서
  실측(가짜 시각 주입으로 어긋난 서버시각을 재현)으로 재확인한 결함:

  ① 하자 처리기한(due_date, 7일 SLA)·진행조회 링크 만료(_track_expired)·정산
     명세 기본 조회월(_stmt_period_args)·접속기록 파기 보관기준(prune-logs) 이
     naive datetime.now() 를 썼다 — DB 에 저장된 시각은 전부 KST 문자열인데
     이 넷만 'OS 가 KST 로 맞춰져 있다'는 가정에 기댔다.
  ② manage.py check 의 "DB 기준 시각 vs OS 시각" 줄은 **비교 없이 나란히 보여
     주기만** 했다 — 사람이 매번 암산으로 맞춰 봐야 하는데 아무도 그렇게 안 해서
     늘 초록이었다. 정작 주석은 "나란히 보여 눈으로 잡게 한다" 는데 코드에
     if/warn 이 없었다.
  ③ bootstrap.sh 의 시간대 설정은 timedatectl 이 실패해도(컨테이너 등, 스스로
     "그럴 수 있다"고 주석에 적어 놓은 바로 그 경우) 바로 다음 줄에서 무조건
     "✔ 시간대 Asia/Seoul" 을 또 찍었다 — 실패 문구 옆에 성공 문구가 나란히
     뜨면 사람 눈엔 성공만 남는다.

      python test_scan_round67_fixes.py
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


APP_SRC = read("app.py")
MANAGE_SRC = read("manage.py")
BOOTSTRAP_SRC = read(os.path.join("deploy", "bootstrap.sh"))

print("═" * 72)
print("  스캔 67라운드 회귀 — naive datetime.now() KST 어긋남 5곳 + 장식 시계점검 + help 누락")
print("═" * 72)


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계·문서 안에서 확인")
# ──────────────────────────────────────────────────────────────
chk("datetime.now(DB.KST) + timedelta(days=7)" in APP_SRC,
    "★★★ ① 하자 처리기한(due_date) 이 KST 기준으로 계산된다")

track_body = _body(APP_SRC, "_track_expired")
chk("datetime.now(DB.KST).replace(tzinfo=None)" in track_body,
    "★★★ ① 진행조회 링크 만료 판정이 KST 기준이다")

stmt_body = _body(APP_SRC, "_stmt_period_args")
chk("now = datetime.now(DB.KST)" in stmt_body,
    "★★ ① 정산 명세 기본 조회월이 KST 기준이다")

prunelogs_body = _body(MANAGE_SRC, "cmd_prune_logs")
chk("datetime.now(DB.KST) - timedelta(days=days)" in prunelogs_body,
    "★★ ① 접속기록 파기 보관기준이 형제(prune-personal)와 같은 KST 기준이다")

check_body = _body(MANAGE_SRC, "cmd_check")
chk("_drift = abs((os_now - _kst_dt).total_seconds())" in check_body
    and "_drift > 120" in check_body,
    "★★★ ② manage.py check — DB 기준 시각과 OS 시각을 실제로 비교한다"
    "(고치기 전엔 나란히 보여주기만 하고 비교가 없었다)")

for _cmd in ("set-fee", "sweep", "install-scheduler", "mark-smoke-demo"):
    chk(f"manage.py {_cmd}" in MANAGE_SRC[:3000],
        f"★ manage.py 사용법(문서 맨 위)에 '{_cmd}' 가 있다"
        "(COMMANDS 에는 20개가 있는데 문서엔 16개만 있었다)")

chk("if timedatectl set-timezone Asia/Seoul 2>/dev/null; then" in BOOTSTRAP_SRC,
    "★★ ③ bootstrap.sh — 시간대 설정 성공 문구가 실제 성공에만 뜬다"
    "(고치기 전엔 실패해도 바로 다음 줄에서 무조건 성공 문구가 또 찍혔다)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 함수 호출로 ①② 재현(가짜 시각 주입)")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round67_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A
    import manage as M
    from datetime import datetime as _real_datetime, timedelta as _td
    import io as _io
    import contextlib as _cl

    # ── ① _track_expired — datetime.now(tz) 로 부르는지를 직접 구분해 본다 ──
    #    tz 없이 부르면(옛 코드) '아득한 미래'를, tz=DB.KST 로 부르면(고친 코드)
    #    진짜 현재 시각을 돌려주는 가짜로 바꿔치기한다 — 어느 쪽을 부르는지에
    #    따라 "방금 발급한 링크"의 만료 판정이 갈린다.
    class _FakeDT:
        @staticmethod
        def now(tz=None):
            if tz is None:
                return _real_datetime.now() + _td(days=9999)
            return _real_datetime.now(tz)
        strptime = staticmethod(_real_datetime.strptime)

    issued_now = DB.now()  # 방금 KST 로 발급된 링크
    _real_app_dt = A.datetime
    A.datetime = _FakeDT
    try:
        expired = A._track_expired(issued_now)
    finally:
        A.datetime = _real_app_dt
    chk(expired is False,
        "★★★ ① 방금 발급한 링크는 만료로 안 잡힌다(datetime.now(DB.KST) 를 실제로 쓴다 — "
        "tz 없이 불렀다면 '아득한 미래'를 현재로 착각해 즉시 만료로 잡혔을 것)", expired)

    # ── ② manage.py check — 실제 서버시각(이 기기는 이미 KST)에서는 정상 표시 ──
    def _run_check():
        buf = _io.StringIO()
        with _cl.redirect_stdout(buf):
            M.cmd_check([])
        return buf.getvalue()

    out_normal = _run_check()
    chk("서버 시간대가 KST" not in out_normal,
        "★ 대조군 — 이 기기는 실제로 KST 라 시간대 경고가 안 뜬다(과잉경고 아님)", None)
    chk("DB 기준 시각(KST)" in out_normal,
        "STEP DB 기준 시각 줄이 정상적으로 찍힌다", None)

    #  ⚠ 9시간 어긋난 OS 시각을 흉내낸다 — UTC 로 뜬 컨테이너를 그대로 재현.
    class _FakeDTSkewed:
        @staticmethod
        def now():
            return _real_datetime.now() - _td(hours=9)
        strptime = staticmethod(_real_datetime.strptime)

    _real_mng_dt = M.datetime
    M.datetime = _FakeDTSkewed
    try:
        out_skewed = _run_check()
    finally:
        M.datetime = _real_mng_dt
    chk("서버 시간대가 KST(Asia/Seoul)가 아닐 수 있습니다" in out_skewed,
        "★★★ ② 9시간 어긋난 OS 시각을 흉내내면 실제로 경고한다"
        "(고치기 전엔 이 상황에서도 그냥 초록이었다)", out_skewed[-400:])

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드67 실측 준비/실행", f"{type(e).__name__} {e}")
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
