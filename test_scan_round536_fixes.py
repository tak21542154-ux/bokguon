# -*- coding: utf-8 -*-
"""스캔 536라운드 회귀 — 인라인 마감 스윕(_sweep_if_due, app.py:6888)의 바깥
   except 가 로그 한 줄 없이 예외를 삼키던 결함.

   조사 배경 — round523 자신이 이 정확한 자리(app.py 5792행 주석)에서 이미
   지목만 해 두고 그때는 손대지 않은 결함이다. round523 은 형제 _sweep_claim()
   (리스 확보, app.py:5779)의 락 경합 실패(sqlite3.Error)만 app.logger.exception
   으로 고쳤는데, 그 주석 자신이 "그런데도 _sweep_if_due() 의 바깥 except 는
   로그 한 줄 없이 삼켜 아무도 못 알아챈다"고 명시적으로 남겨 둔 채 524~535
   라운드 동안 아무도 이 함수 자체는 고치지 않았다(grep 재확인 — _sweep_if_due
   를 실제로 수정한 라운드가 없다).

   _sweep_if_due() 는 조회 화면(보험사 포털 3549행·관리자 대시보드 6937행·
   협력사 포털 21135·21163행)을 열 때마다 곁들여 도는, 5개 스윕(sweep_auctions·
   sweep_no_bid_alert·sweep_report_overdue·sweep_review_reminders·
   sweep_warranty_expiry)을 감싸는 유일한 공유 관문이다. 그 바깥 except
   Exception 은 (자신의 docstring대로) "어떤 예외도 그 요청을 깨뜨리지 않는다"는
   설계는 맞지만, 5개 스윕 중 하나가 (락 경합이 아닌) 다른 이유로 실패하면
   그 회차 전체가 조용히 건너뛰어지는데 _LAST_INLINE_SWEEP 는 이미 갱신돼
   있어 INLINE_SWEEP_GAP_SEC(60초) 동안 재시도조차 안 열리고, 그 실패
   자체가 어디에도 안 남았다 — 마감 점검이 몇 분씩 멈춰도 화면은 계속 200을
   반환하니 아무도 눈치챌 수 없다.

   고침 — 예외를 여전히 밖으로 올리지 않는다(주 업무 흐름은 이 함수 실패로
   깨지면 안 된다는 원래 설계 그대로 유지). except 블록 안에서
   app.logger.exception() 으로 실패 사실만 남긴다 — 형제(_sweep_claim
   5809행·notify_victim round529)와 정확히 같은 관례를 재사용했을 뿐,
   새 헬퍼·새 상수는 없다.

      python test_scan_round536_fixes.py
"""
import io
import os
import shutil
import sqlite3
import sys
import tempfile
import logging

#  ⚠ 윈도 기본 콘솔은 cp949 라 em dash(—) 같은 문자를 print 하면
#    UnicodeEncodeError 로 죽는다 — 형제 테스트(round528 등)가 이미 쓰는
#    방어를 그대로 옮긴다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 536라운드 회귀 — 인라인 마감 스윕(_sweep_if_due)의 예외 삼킴")
print("=" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ==================================================================
print("\n[1] 소스: _sweep_if_due() 가 이제 실패를 로그로 남긴다 "
      "(형제 _sweep_claim 5809행·notify_victim round529 와 같은 관례)")
# ------------------------------------------------------------------
import ast as _ast
chk(_ast.parse(APP_SRC) is not None, "STEP app.py 전체 ast.parse 성공")

sd_body = _py_fn_body(APP_SRC, "_sweep_if_due")
chk("except Exception:" in sd_body,
    "★★ 주 업무 흐름 보호(어떤 예외도 밖으로 올리지 않는다)는 그대로 남아 있다"
    "(원래 설계 docstring 그대로 유지 — 좁히지 않았다)")
chk("app.logger.exception(" in sd_body,
    "★★★★★ except 블록이 이제 app.logger.exception() 으로 실패 사실을 남긴다"
    "(고치기 전엔 로그 호출이 한 줄도 없었다)")
_except_idx = sd_body.index("except Exception:")
_after_except = sd_body[_except_idx:]
#  '삼키기만 하고 로그가 없는' 옛 몸통과 달리, 로그 호출이 except 블록
#  자신의 몸통(rollback try 이전) 안에 실행문으로 있어야 한다 — 엉뚱하게
#  finally 블록 등 다른 자리에 들어간 게 아님을 확인한다.
chk("app.logger.exception(" in _after_except.split("\n\n")[0],
    "STEP 로그 호출이 except 블록 자신의 몸통 안에 있다(엉뚱한 자리 아님)")
_log_idx = _after_except.index("app.logger.exception(")
_rollback_idx = _after_except.index("conn.rollback()")
chk(_log_idx < _rollback_idx,
    "STEP 로그 호출이 rollback 시도보다 먼저 실행된다(실패 사실이 rollback "
    "성패와 무관하게 항상 남는다)")

#  다섯 스윕 호출이 이번 수정으로 하나라도 빠지거나 순서가 바뀌지 않았다 —
#  주석을 끼워 넣다가 실행문 한 줄을 통째로 지우는 사고(과거 라운드가 겪은
#  Edit 앵커 사고와 같은 클래스)가 없었는지 실측한다.
_sweep_calls = ["sweep_auctions(conn)", "sweep_no_bid_alert(conn)",
                "sweep_report_overdue(conn)", "sweep_review_reminders(conn)",
                "sweep_warranty_expiry(conn)"]
_positions = [sd_body.index(c) for c in _sweep_calls]
chk(_positions == sorted(_positions),
    "★★★ 5개 스윕 호출이 전부 그대로, 원래 순서 그대로 남아 있다"
    "(주석을 끼워 넣으며 실행문을 지우지 않았다)", _positions)
chk(all(p < _except_idx for p in _positions),
    "STEP 5개 스윕 호출이 전부 try 블록 안(except 이전)에 있다")

#  형제 _sweep_claim() 은 이번 라운드가 손대지 않았다 — round523 의 수정이
#  그대로 살아 있는지 대조한다.
sc_body = _py_fn_body(APP_SRC, "_sweep_claim")
chk("app.logger.exception(\"경매마감 리스 확보 실패" in sc_body,
    "★★★ 형제 _sweep_claim() 의 round523 로그 호출은 이번 라운드가 손대지 "
    "않고 그대로 남아 있다")

# ==================================================================
# 실행 준비
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round536_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r536-csrf"
A = None
DB = None


class _Capture(logging.Handler):
    """A.app.logger 로 실제 나가는 레코드를 가로채 실행기반으로 검증한다
    (소스 문자열 매치가 아니라, 진짜 logger.exception() 호출이 도는지 본다)."""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record.getMessage())


def _admin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "admin"
        sess["admin_name"] = "검증"
        sess["admin_role"] = "최고관리자"
        sess["_csrf"] = CSRF
    return c


_cap = None
try:
    import db as DB
    DB.init_db()
    import app as A

    _cap = _Capture()
    _cap.setLevel(logging.DEBUG)
    A.app.logger.addHandler(_cap)
    A.app.logger.setLevel(logging.DEBUG)

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('admin','x','검증','최고관리자')")
    conn0.commit()
    conn0.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드536 실행 준비(DB.init_db·app import)", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[2] 실행: 정상 경로 — 아무것도 실패하지 않으면 과잉 로깅이 없다"
      "(빈 DB 에서도 안전하게 돈다)")
# ------------------------------------------------------------------
try:
    A._LAST_INLINE_SWEEP[0] = 0.0     # 조절창(60초) 강제 통과
    _boom = None
    try:
        A._sweep_if_due()
    except Exception as e:                                          # noqa: BLE001
        _boom = e
    chk(_boom is None,
        "★★★ 정상 경로에서 _sweep_if_due() 는 예외를 올리지 않는다(빈 DB 에서도)",
        repr(_boom))
    chk(_cap.records == [],
        "STEP 아무것도 실패하지 않았으면 실패 로그도 안 남는다(과잉 로깅 아님)",
        _cap.records)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드536 [2] 정상 경로", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[2-b] 실행: 조절창(INLINE_SWEEP_GAP_SEC) 이 이번 수정으로 안 깨졌다"
      "(60초 안 재호출은 여전히 건너뛴다)")
# ------------------------------------------------------------------
try:
    _calls = [0]

    def _counting_sweep(*a, **k):
        _calls[0] += 1
    _orig_sweep_auctions = A.sweep_auctions
    A.sweep_auctions = _counting_sweep
    try:
        # 방금 [2]에서 _LAST_INLINE_SWEEP 가 now 로 갱신됐으므로, 리셋 없이
        # 바로 다시 부르면 60초 조절창에 걸려 스윕 본문(카운팅 스텁 포함)
        # 자체가 아예 안 불려야 한다.
        A._sweep_if_due()
    finally:
        A.sweep_auctions = _orig_sweep_auctions
    chk(_calls[0] == 0,
        "★★★ 60초 안에 다시 열어도 스윕이 다시 돌지 않는다"
        "(이번 로그 추가가 조절창 자체를 깨지 않았다)", _calls[0])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드536 [2-b] 조절창 무회귀", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[3] 실행: 스윕 중 하나가 (락 경합이 아닌) 다른 이유로 실패하면 "
      "— 지금 코드는 흔적을 남기고, 커넥션도 제대로 정리한다")
# ------------------------------------------------------------------


class _ConnTracker:
    """진짜 커넥션을 감싸 close()/rollback() 호출 여부만 센다(동작은 그대로 위임)."""

    def __init__(self, real):
        self._real = real
        self.closed = 0
        self.rolled_back = 0

    def close(self):
        self.closed += 1
        return self._real.close()

    def rollback(self):
        self.rolled_back += 1
        return self._real.rollback()

    def __getattr__(self, name):
        return getattr(self._real, name)


_orig_get_db = DB.get_db
_orig_sweep_auctions = A.sweep_auctions
_trackers = []
try:
    _cap.records.clear()

    def _boom_sweep(*a, **k):
        #  ⚠ round527 이 이미 쓴 것과 같은 원칙 — sqlite3.Error 가 아닌 실패
        #    (락 경합이 아니라 프로그래밍 버그류)를 흉내낸다. _sweep_claim
        #    자신의 sqlite3.Error 방어(round523)로는 못 잡는 종류의 실패다.
        raise RuntimeError("round536 시뮬레이션 — sweep_auctions 내부 버그")

    def _tracked_get_db():
        t = _ConnTracker(_orig_get_db())
        _trackers.append(t)
        return t

    A.sweep_auctions = _boom_sweep
    A.DB.get_db = _tracked_get_db
    A._LAST_INLINE_SWEEP[0] = 0.0

    _boom = None
    try:
        A._sweep_if_due()
    except Exception as e:                                          # noqa: BLE001
        _boom = e

    chk(_boom is None,
        "★★★★★ sweep_auctions 가 RuntimeError(sqlite3.Error 아님)로 실패해도 "
        "_sweep_if_due() 는 밖으로 예외를 올리지 않는다(호출부 4곳의 화면이 "
        "여전히 안 깨진다)", repr(_boom))
    chk(any("인라인 마감 스윕" in r for r in _cap.records),
        "★★★★★ 지금 코드는 실패하면 app.logger.exception() 으로 흔적을 남긴다 "
        "— 고치기 전엔 이 리스트가 항상 비어 있었다", _cap.records)
    chk(len(_trackers) == 1 and _trackers[0].closed == 1,
        "★★★ 실패 경로에서도 커넥션은 정확히 한 번 닫힌다(finally 그대로 동작)",
        [(t.closed, t.rolled_back) for t in _trackers])
    chk(_trackers and _trackers[0].rolled_back == 1,
        "STEP 실패 경로에서 rollback 도 그대로 시도된다(이번 로그 추가가 "
        "기존 rollback 동작을 밀어내지 않았다)",
        [t.rolled_back for t in _trackers])
finally:
    A.sweep_auctions = _orig_sweep_auctions
    A.DB.get_db = _orig_get_db

# ==================================================================
print("\n[4] 실행(라우트): 진짜 Flask 관리자 대시보드에서도 — 화면은 여전히 "
      "200 이면서 이제는 실패 로그가 함께 남는다")
# ------------------------------------------------------------------
_orig_sweep_auctions = A.sweep_auctions
try:
    _cap.records.clear()

    def _boom_sweep2(*a, **k):
        raise RuntimeError("round536 시뮬레이션 — /api/dashboard 경유")
    A.sweep_auctions = _boom_sweep2
    A._LAST_INLINE_SWEEP[0] = 0.0

    admin_c = _admin_client()
    r = admin_c.get("/api/dashboard")

    chk(r.status_code == 200,
        "★★★★ sweep_auctions 가 실패해도 실제 /api/dashboard 라우트는 "
        "여전히 200 을 돌려준다(원래 설계대로 화면이 안 깨진다)",
        (r.status_code, r.get_data(as_text=True)[:200]))
    chk(any("인라인 마감 스윕" in r_ for r_ in _cap.records),
        "★★★★★ 실제 라우트 경유에서도 실패 흔적이 서버 로그에 남는다"
        "(바로 이 라우트 4곳 중 하나가 고치기 전엔 흔적 없이 조용했다)",
        _cap.records)
finally:
    A.sweep_auctions = _orig_sweep_auctions

# ==================================================================
print("\n[5] 되돌리기 — 로그 호출을 빼면(수정 전 코드 재구성) 정말 조용히 "
      "삼키기만 하는가(인과관계 직접증명)")
# ------------------------------------------------------------------
#  ⚠ app.py 자체는 건드리지 않는다 — 동시에 다른 세션이 같은 파일을 건드릴 수
#    있는 환경(round520 이후 표준 관례). 되돌림-증명은 이 라운드가 고치기
#    **직전**의 실제 _sweep_if_due 본문(수정 직전 이 세션이 Read 로 확인한
#    원문 — 코멘트 한 줄까지 그대로)을 테스트 안에서만 문자열로 재구성해
#    같은 시나리오에 직접 실행한다.
_PRE536_SRC = '''
def _sweep_if_due():
    """조회 화면을 열 때 곁들여 도는 마감 점검.
       전용 커넥션을 쓰고, 어떤 예외도 그 요청을 깨뜨리지 않는다.
    """
    now = time.time()
    if now - _LAST_INLINE_SWEEP[0] < INLINE_SWEEP_GAP_SEC:
        return
    _LAST_INLINE_SWEEP[0] = now
    conn = None
    try:
        conn = DB.get_db()
        sweep_auctions(conn)
        sweep_no_bid_alert(conn)
        sweep_report_overdue(conn)
        sweep_review_reminders(conn)
        sweep_warranty_expiry(conn)
    except Exception:
        try:
            if conn:
                conn.rollback()
        except sqlite3.Error:
            pass
    finally:
        if conn:
            conn.close()
'''
try:
    _ns = dict(vars(A))            # app 모듈 네임스페이스 복사(진짜 모듈은 안 건드림)
    _ns["_LAST_INLINE_SWEEP"] = [0.0]       # 실제 스윕과 완전히 독립된 조절창
    _ns["INLINE_SWEEP_GAP_SEC"] = 60

    def _boom_sweep3(*a, **k):
        raise RuntimeError("round536 시뮬레이션 — 되돌림-증명")
    _ns["sweep_auctions"] = _boom_sweep3

    exec(compile(_PRE536_SRC, "<round536_pre_reconstructed>", "exec"), _ns)
    _old_sweep_if_due = _ns["_sweep_if_due"]

    _cap.records.clear()
    _boom_old = None
    try:
        _old_sweep_if_due()
    except Exception as e:                                          # noqa: BLE001
        _boom_old = e

    chk(_boom_old is None,
        "★★★★★ 옛 코드(재구성)도 예외를 밖으로 올리지 않는다(겉보기 동작은 "
        "지금 코드와 똑같다 — 그래서 13개 라운드 동안 아무도 눈치 못 챘다)",
        repr(_boom_old))
    chk(_cap.records == [],
        "★★★★★ 그런데 옛 코드는 같은 실패에서 로그를 단 한 줄도 안 남긴다 "
        "— 지금 코드(위 [3]·[4])는 같은 입력에서 실제로 로그를 남겼다. 이 "
        "차이가 이 회귀가 실제로 결함을 잡아낼 능력이 있다는 인과관계 증명이다",
        _cap.records)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드536 [5] 되돌림-증명", f"{type(e).__name__} {e}")

# ==================================================================
# 정리
# ------------------------------------------------------------------
try:
    if A is not None and _cap is not None:
        try:
            A.app.logger.removeHandler(_cap)
        except Exception:
            pass
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
