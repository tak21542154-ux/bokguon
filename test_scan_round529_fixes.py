# -*- coding: utf-8 -*-
"""스캔 529라운드 회귀 — 피해자 안내 적재(notify_victim, app.py:19469)가
   sqlite3.Error 를 로그 한 줄 없이 삼키던 결함.

   조사 배경 — round528 과 같은 방식(라우트 데코레이터~다음 def 사이에
   "라운드" 문자열이 없는 함수 전수 추출)을 라우트가 아닌 **헬퍼 함수**까지
   넓혀 다시 뽑아 보니(126개 라우트 후보는 이미 재확인해 전부 형제와 일치),
   호출 빈도 상위권에 notify_victim() 이 있었다. 이 함수는 낙찰확정
   (app.py:4666)·변경견적(11115)·경매 낙찰(11599)·완료보고(11806)·직접배정
   (18261)·조회링크 발급(19464) 6곳에서 불리는, 피해자에게 나가는 문자를
   발송대기함에 적재하는 유일한 공유 관문이다.

   본문 전체가 `except sqlite3.Error: pass` 로 감싸여 있었다 — 형제 함수
   _dispatch_notify(내부 콜백, app.py:17346)가 이미 겪고 고친 것과 정확히
   같은 모양의 결함이다. 그 형제의 수정 코멘트가 스스로 적어 둔 두 가지
   잘못 중 하나가 "삼키면서 로그도 안 남겨, 콜이 0건 나간 사실이 어디에도
   안 남았다"인데, notify_victim 은 그 잘못만 그대로 갖고 있었다(TypeError
   위험은 이미 `if not c` 로 방어돼 있어 형제의 첫 번째 잘못은 없다).

   실제 영향 — notify() 내부 INSERT 가 어떤 이유로든 sqlite3.Error 를
   내면(예: DB 잠금·디스크 오류), notify_victim 은 아무 흔적도 안 남기고
   조용히 넘어간다. 그런데 조회링크 발급 라우트(api_track_link, 19007행)는
   notify_victim 을 부른 **직후 무조건** sent=True 를 찍고, 화면에
   "안내 예약"이라고 답한다 — 실제로는 발송대기함에 아무것도 안 쌓였는데
   운영자는 보낸 줄 알고 넘어간다. notify() 자기 자신은 같은 종류의 실패
   (1884행, 데모표식 조회 실패)에 이미 app.logger.exception 을 쓴다 —
   그 형제 관례를 notify_victim 에도 맞춘다.

   고침 — 예외를 여전히 밖으로 올리지 않는다(주 업무 흐름은 이 함수 실패로
   깨지면 안 된다는 원래 설계는 유지, docstring 그대로). `except` 블록
   안에서 app.logger.exception() 으로 실패 사실만 남긴다(새 헬퍼·새 상수
   없음 — notify() 자신의 1884행과 같은 관례 재사용).

      python test_scan_round529_fixes.py
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
print("  스캔 529라운드 회귀 — 피해자 안내 적재(notify_victim)의 예외 삼킴")
print("=" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ==================================================================
print("\n[1] 소스: notify_victim() 이 실패를 로그로 남긴다 "
      "(형제 notify() 1884행과 같은 관례)")
# ------------------------------------------------------------------
nv_body = _py_fn_body(APP_SRC, "notify_victim")
chk("except sqlite3.Error:" in nv_body,
    "★★ 주 업무 흐름 보호(예외를 밖으로 올리지 않는다)는 그대로 남아 있다"
    "(원래 설계 docstring 그대로 유지)")
chk("app.logger.exception(" in nv_body,
    "★★★★★ except 블록이 이제 app.logger.exception() 으로 실패 사실을 남긴다"
    "(고치기 전엔 pass 하나뿐이었다)")
_except_idx = nv_body.index("except sqlite3.Error:")
_after_except = nv_body[_except_idx:]
#  '삼키기만 하고 아무것도 안 하는' 옛 몸통(공백 제외 "pass" 한 줄)이
#  except 블록 전체를 이루는 게 아니라, 로그 호출이 실제 실행문으로 있어야 한다.
chk("app.logger.exception(" in _after_except.split("\n\n")[0],
    "STEP 로그 호출이 except 블록 자신의 몸통 안에 있다(엉뚱한 자리 아님)")

# ==================================================================
# 실행 준비
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round529_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r529-csrf"
A = None
DB = None
cid = None


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


# ==================================================================
print("\n[2] 실행: notify_victim() 정상 경로 — 과잉수정이 아니다 "
      "(연락처가 있으면 그대로 잘 쌓인다)")
# ------------------------------------------------------------------
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
    cid = conn0.execute(
        "INSERT INTO cases(case_no,status,category,region,victim_phone,is_demo) "
        "VALUES('R529-1','접수','가드레일','서울','01011112222',0)"
    ).lastrowid
    conn0.commit()

    before_n = conn0.execute(
        "SELECT COUNT(*) n FROM notifications WHERE case_id=? AND ntype='피해자안내'",
        (cid,)).fetchone()["n"]
    A.notify_victim(conn0, cid, "정상 경로 확인 메시지")
    conn0.commit()
    after_n = conn0.execute(
        "SELECT COUNT(*) n FROM notifications WHERE case_id=? AND ntype='피해자안내'",
        (cid,)).fetchone()["n"]
    conn0.close()

    chk(after_n == before_n + 1,
        "★★★ 연락처가 있고 conn 이 멀쩡하면 정상적으로 1건 적재된다"
        "(이 라운드가 정상 경로를 막지 않았다)", (before_n, after_n))
    chk(_cap.records == [],
        "STEP 정상 경로에서는 실패 로그가 전혀 안 남는다(과잉 로깅 아님)",
        _cap.records)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드529 [2] 정상 경로 준비/실행", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[3] 실행: notify_victim() 에 실제 sqlite3.Error 를 자연 발생시킨다 "
      "(닫힌 커넥션 — 몽키패치 아닌 진짜 예외)")
# ------------------------------------------------------------------
try:
    _cap.records.clear()
    conn_closed = DB.get_db()
    conn_closed.close()          # 이 순간부터 이 conn 의 모든 execute() 는 진짜 sqlite3.Error

    # 닫힌 커넥션에 진짜로 sqlite3.Error 가 나는지 먼저 확인(전제 검증)
    _raised = None
    try:
        conn_closed.execute("SELECT 1")
    except sqlite3.Error as e:
        _raised = e
    chk(isinstance(_raised, sqlite3.Error),
        "STEP 전제 확인 — 닫힌 커넥션은 실제로 sqlite3.Error(ProgrammingError) 를 낸다"
        "(이 테스트가 몽키패치가 아니라 진짜 예외로 검증한다는 근거)",
        type(_raised).__name__ if _raised else None)

    _boom = None
    try:
        A.notify_victim(conn_closed, cid, "실패 경로 확인 메시지")
    except Exception as e:                                          # noqa: BLE001
        _boom = e
    chk(_boom is None,
        "★★★★★ notify_victim() 은 sqlite3.Error 가 나도 밖으로 예외를 올리지 않는다"
        "(호출부 6곳의 주 업무 흐름은 여전히 안 깨진다)", repr(_boom))
    chk(any("피해자 안내" in r and str(cid) in r for r in _cap.records),
        "★★★★★ 지금 코드는 실패하면 app.logger.exception() 으로 흔적을 남긴다 "
        "(사건 id 가 메시지에 포함) — 고치기 전엔 이 리스트가 항상 비어 있었다",
        _cap.records)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드529 [3] 실패 경로 실행", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[4] 실행(라우트): 조회링크 발급이 notify_victim 실패에도 200/'안내 예약'을 "
      "그대로 돌려주면서 — 이제는 실패 로그가 함께 남는다")
# ------------------------------------------------------------------
_orig_notify = None
try:
    _cap.records.clear()
    conn1 = DB.get_db()
    cid2 = conn1.execute(
        "INSERT INTO cases(case_no,status,category,region,victim_phone,is_demo) "
        "VALUES('R529-2','접수','가드레일','서울','01033334444',0)"
    ).lastrowid
    conn1.commit(); conn1.close()

    before_n2 = None
    conn_chk = DB.get_db()
    before_n2 = conn_chk.execute(
        "SELECT COUNT(*) n FROM notifications WHERE case_id=?", (cid2,)).fetchone()["n"]
    conn_chk.close()

    #  notify() 자체를 sqlite3.OperationalError 로 몽키패치 — "DB 잠금" 류
    #  실제 실패를 재현한다(이 라우트 안에서 notify() 를 부르는 곳은 오직
    #  notify_victim 뿐이라 다른 호출에는 영향이 없다 — DB.log 는 별개 함수).
    _orig_notify = A.notify

    def _boom_notify(*a, **k):
        raise sqlite3.OperationalError("database is locked (round529 시뮬레이션)")
    A.notify = _boom_notify

    admin_c = _admin_client()
    r = admin_c.post(f"/api/cases/{cid2}/track-link", headers={"X-CSRF-Token": CSRF})
    j = r.get_json()

    chk(r.status_code == 200 and j.get("ok") is True,
        "★★★★ notify() 가 sqlite3.Error 로 실패해도 조회링크 발급 라우트는 "
        "여전히 200/ok:True 다(원래 설계대로 주 업무 흐름은 안 깨진다)",
        (r.status_code, j))
    chk(j.get("has_phone") is True,
        "STEP has_phone=True 는 그대로다(이 라운드가 바꾼 것은 API 응답이 아니라 "
        "관측가능성이다 — 응답 의미를 바꾸는 것은 이 라운드의 범위가 아니다)",
        j.get("has_phone"))
    chk(any("피해자 안내" in r_ for r_ in _cap.records),
        "★★★★★ 화면은 '안내 예약'이라 말하지만, 서버 로그에는 실패 흔적이 "
        "실제로 남는다(고치기 전엔 이 실패가 어디에도 안 남아 아무도 몰랐다)",
        _cap.records)

    conn_chk2 = DB.get_db()
    after_n2 = conn_chk2.execute(
        "SELECT COUNT(*) n FROM notifications WHERE case_id=?", (cid2,)).fetchone()["n"]
    conn_chk2.close()
    chk(after_n2 == before_n2,
        "STEP 실제로는 발송대기함에 아무것도 안 쌓였다(응답의 '안내 예약'과 달리) "
        "— 바로 이 간극이 로그 없이는 아무도 못 보던 부분이다", (before_n2, after_n2))
finally:
    if _orig_notify is not None:
        A.notify = _orig_notify

# ==================================================================
print("\n[5] 되돌리기 — 로그 호출을 빼면(수정 전 코드 재구성) 정말 조용히 "
      "삼키기만 하는가(인과관계 직접증명)")
# ------------------------------------------------------------------
#  ⚠ app.py 자체는 건드리지 않는다 — 동시에 다른 세션이 같은 파일을 건드릴 수
#    있는 환경(round520 이후 표준 관례). 되돌림-증명은 이 라운드가 고치기
#    **직전**의 실제 notify_victim 본문(수정 직전 이 세션이 Read 로 확인한
#    원문)을 테스트 안에서만 문자열로 재구성해 같은 시나리오에 직접 실행한다.
try:
    def _notify_victim_pre529(conn, cid_, message):
        """round529 이전 notify_victim() 재구성 — sqlite3.Error 를 로그 없이 삼킨다."""
        try:
            c = A.one(conn.execute(
                "SELECT case_no, victim_name, victim_phone, track_token FROM cases WHERE id=?",
                (cid_,)))
            if not c or not (c["victim_phone"] or "").strip():
                return
            tail = f" 진행조회: {A._site_url()}/track/{c['track_token']}" if c["track_token"] else ""
            A.notify(conn, "피해자안내", "문자", c["victim_phone"],
                     f"[복구온] {message}{tail}{A._victim_notice()}",
                     case_id=cid_)
        except sqlite3.Error:
            pass                                        # ← 라운드529 이전엔 이게 전부였다

    _cap.records.clear()
    _boom_old = None
    try:
        _notify_victim_pre529(conn_closed, cid, "옛 코드 확인 메시지")
    except Exception as e:                                          # noqa: BLE001
        _boom_old = e

    chk(_boom_old is None,
        "★★★★★ 옛 코드(재구성)도 예외를 밖으로 올리지 않는다(겉보기 동작은 "
        "지금 코드와 똑같다 — 그래서 지금까지 아무도 눈치 못 챘다)", repr(_boom_old))
    chk(_cap.records == [],
        "★★★★★ 그런데 옛 코드는 같은 실패에서 로그를 단 한 줄도 안 남긴다 "
        "— 지금 코드(위 [3])는 같은 입력에서 실제로 로그를 남겼다. 이 차이가 "
        "이 회귀가 실제로 결함을 잡아낼 능력이 있다는 인과관계 증명이다",
        _cap.records)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드529 [5] 되돌림-증명", f"{type(e).__name__} {e}")

# ==================================================================
# 정리
# ------------------------------------------------------------------
try:
    if _orig_notify is not None and A is not None:
        A.notify = _orig_notify
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
