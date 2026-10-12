# -*- coding: utf-8 -*-
"""스캔 85라운드 회귀 — 완료승인 독촉(api_settlement_remind_approval)의
   쿨다운 확인(SELECT)과 기록(INSERT) 사이 잠금 누락.

  형제(sweep_review_reminders·sweep_approval_overdue)는 이미 "확인과 삽입 사이가
  비어 있었다"는 정확히 같은 결함을 BEGIN IMMEDIATE 로 고쳤고, sweep_approval_overdue
  의 주석은 "수동 독촉과 같은 쿨다운(24시간) — 두 경로가 겹쳐 두 번 가지 않게
  한다"고 스스로 적어 두기까지 했다. 그런데 정작 그 "두 경로" 중 하나인 이 수동
  독촉 라우트 자신은 트랜잭션이 없었다 — 빠른 더블클릭이나 자동 스윕과 겹치면
  같은 24시간 쿨다운 안에 두 번 나간다(관리자 화면 버튼도 확인창·비활성화가 없다).

      python test_scan_round85_fixes.py
"""
import io
import os
import shutil
import sqlite3
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

print("═" * 72)
print("  스캔 85라운드 회귀 — 완료승인 독촉 쿨다운 확인-삽입 사이 잠금 누락")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
remind_body = _py_fn_body(APP_SRC, "api_settlement_remind_approval")
chk('conn.execute("BEGIN IMMEDIATE")' in remind_body,
    "★★★ api_settlement_remind_approval 이 확인-삽입을 한 트랜잭션으로 묶는다")
chk(remind_body.count("conn.rollback()") >= 3,
    "★★ 조기 반환(404/409/409/429) 전에 트랜잭션을 되돌린다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실서버 경로(Flask test_client + 임시 DB)로 경합 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round85_")
_dbpath = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_DB_PATH"] = _dbpath
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','하위관리자')")
    iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R85보험','활성')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id) "
        "VALUES('R85-1','정산진행','가드레일','서울',?)", (iid,)).lastrowid
    sid = conn.execute(
        "INSERT INTO settlements(case_id,insurer_id,amount,created_at) "
        "VALUES(?,?,1000000,?)", (cid, iid, DB.now())).lastrowid
    conn.commit(); conn.close()

    admin = A.app.test_client()
    _tok = "r85-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "하위관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    #  ⚠ _LockProbe — 실제 라우트가 "쿨다운 있음?" SELECT 를 실행하려는 바로 그
    #    순간, 별도의(짧은 타임아웃) 진짜 커넥션으로 "동시에 겹친 다른 요청이
    #    이미 독촉 알림을 하나 심었다"는 경쟁자를 흉내낸다. 고친 코드는 이 SELECT
    #    전에 이미 BEGIN IMMEDIATE 로 쓰기 잠금을 쥐고 있어 경쟁자의 INSERT 가
    #    락 경합으로 실패해야 한다(원자성의 증거) — 안 고친 코드는 잠금이 없어
    #    경쟁자가 그냥 끼어들고, 그 뒤 실제 라우트도 자기 몫을 또 심어 중복이 난다.
    #  ⚠ 이 요청 하나에서도 DB.get_db() 가 여러 번 불린다(인증 확인·access_log
    #    후처리 등 라우트 밖에서도 각자 커넥션을 새로 연다) — "마지막으로 만들어진
    #    래퍼"를 들고 있으면 엉뚱한(관심 밖) 커넥션을 붙잡을 수 있다. 어떤 래퍼가
    #    실제로 그 SQL 을 봤는지와 무관하게, 상태를 전부가 공유하는 한 곳에 쓴다.
    _shared = {"tried": False, "inserted": False}

    class _LockProbe:
        def __init__(self, real):
            self._real = real

        def execute(self, sql, params=()):
            if not _shared["tried"] and "ntype='완료승인독촉'" in sql:
                _shared["tried"] = True
                try:
                    _pc = sqlite3.connect(_dbpath, timeout=0.3)
                    _pc.execute(
                        "INSERT INTO notifications(ntype,channel,target,message,status,"
                        "case_id,created_at) VALUES('완료승인독촉','웹','R85보험',"
                        "'경쟁자 독촉','전달됨',?,?)", (cid, DB.now()))
                    _pc.commit()
                    _shared["inserted"] = True
                except sqlite3.OperationalError:
                    _shared["inserted"] = False
                finally:
                    try:
                        _pc.close()
                    except Exception:
                        pass
            return self._real.execute(sql, params)

        def __getattr__(self, name):
            return getattr(self._real, name)

    _real_get_db = DB.get_db

    def _patched_get_db():
        return _LockProbe(_real_get_db())
    DB.get_db = _patched_get_db
    try:
        r = admin.post(f"/api/settlements/{sid}/remind-approval", headers=_hdr)
    finally:
        DB.get_db = _real_get_db

    chk(_shared["tried"], "STEP 경쟁자 주입 시도가 실제로 발동했다")
    chk(_shared["inserted"] is False,
        "★★★ 라우트가 쿨다운 확인 시점에 이미 쓰기 잠금을 쥐고 있어, "
        "동시에 끼어들려는 경쟁자의 삽입이 락 경합으로 실패한다"
        "(고치기 전엔 잠금이 없어 경쟁자가 그냥 끼어들었다)", dict(_shared))

    _c = DB.get_db()
    _n = _c.execute(
        "SELECT COUNT(*) n FROM notifications WHERE case_id=? AND ntype='완료승인독촉'",
        (cid,)).fetchone()["n"]
    _c.close()
    chk(_n == 1,
        "★★ 결과적으로 같은 24시간 창에 독촉 알림이 정확히 1건만 존재한다"
        "(고치기 전엔 경쟁자 1건 + 라우트 자신의 1건 = 2건이 쌓였다)", f"n={_n}")
    chk(r.status_code == 200, "STEP 정상 요청 자체는 200으로 처리된다", r.status_code)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드85 서버측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
