# -*- coding: utf-8 -*-
"""스캔 122라운드 회귀 — schedule_events 데모표식 미백필/go-live 미정리,
   dispatch.py 로거가 실제 로그파일에 안 닿음, 분할회피 판정(compliance)이
   복합사건 category 표시문자열 완전일치에 의존.

  [1] schedule_events 도 자기 is_demo 컬럼이 있고 캘린더 조회가 이 컬럼으로
      데모를 거르는데, 채우는 코드가 없었다(96·100·116라운드와 같은 결함
      클래스, 형제 8곳 중 이 표만 빠짐). go-live 도 이 표를 안 지워
      삭제된 사건을 가리키는 고아 행이 영구히 남았다.
  [2] dispatch.py 의 "bokguon.dispatch" 로거가 app.logger(이름="app")에만
      붙은 파일핸들러를 물려받지 못해, "수배 알림 실패는 반드시 남긴다"는
      자신의 설계와 달리 실제로는 로그파일에 한 줄도 안 남았다(120·121
      라운드가 새로 단 crypto_util·legal_docs 의 경고도 같은 이유로 미도달).
  [3] compliance.related_sum() 의 "같은 공종" 판정이 cases.category
      표시문자열 완전일치라, 복합사건('복합(A · B)')은 자신의 구성요소
      단독사건과도, 다른 복합사건과도 절대 매칭되지 않았다 — 형사책임
      직결(무등록 건설업 5년 이하 징역) 판정에 dispatch.py/app.py 에서
      이미 3번 고쳐진 것과 같은 결함이 있었다.

      python test_scan_round122_fixes.py
"""
import io
import logging
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


DB_SRC = read("db.py")
MANAGE_SRC = read("manage.py")
APP_SRC = read("app.py")
CP_SRC = read("compliance.py")

print("═" * 72)
print("  스캔 122라운드 회귀 — schedule_events 데모누락·dispatch로거 미도달·분할회피 category일치")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
chk('("schedule_events",' in DB_SRC and DB_SRC.count("schedule_events") >= 2,
    "★★★ db.py _CHILD_DEMO_SQL 이 schedule_events 를 백필한다")
chk('"bid_events", "est_outcome", "damage_reads", "schedule_events")' in MANAGE_SRC,
    "★★★ manage.py go-live 삭제목록에 schedule_events 가 들어갔다")
chk("logging.getLogger().addHandler(_handler)" in APP_SRC
    and "app.logger.addHandler(_handler)" not in APP_SRC,
    "★★★ app.py 가 파일핸들러를 app.logger 대신 루트에 붙인다")
rs_body = _py_fn_body(CP_SRC, "related_sum")
chk("_case_trades" in rs_body and "my_trades & other_trades" in rs_body,
    "★★★ compliance.related_sum 이 work_lots 기반 트레이드 겹침으로 판정한다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — schedule_events 데모 백필 + go-live 정리")
# ──────────────────────────────────────────────────────────────
sys.path.insert(0, HERE)
_tmpdir = tempfile.mkdtemp(prefix="round122_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"

try:
    import db as DB
    DB.init_db()
    conn = DB.get_db()

    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R122-DEMO','접수','가드레일','서울',1)").lastrowid
    eid = conn.execute(
        "INSERT INTO schedule_events(title,event_date,case_id,created_at) "
        "VALUES('현장방문','2026-09-01',?,?)", (cid, DB.now())).lastrowid
    conn.commit()

    n = DB._backfill_child_is_demo(conn)
    conn.commit()
    row = conn.execute("SELECT is_demo FROM schedule_events WHERE id=?", (eid,)).fetchone()
    chk(row["is_demo"] == 1,
        "★★★ 데모 사건에 붙은 일정이 백필로 is_demo=1 이 된다"
        "(예전엔 영원히 0 — 캘린더 데모필터가 무력했다)", dict(row))

    import manage as M
    buf = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(buf):
        M.cmd_go_live(["--yes"])
    left = conn.execute("SELECT COUNT(*) n FROM schedule_events WHERE id=?", (eid,)).fetchone()["n"]
    cases_left = conn.execute("SELECT COUNT(*) n FROM cases").fetchone()["n"]
    chk(cases_left == 0,
        "STEP go-live 가 데모 사건을 실제로 지운다(전제조건 확인)", cases_left)
    chk(left == 0,
        "★★★ go-live 가 schedule_events 고아행도 함께 지운다"
        "(예전엔 사건이 지워져도 이 표만 남아 없는 사건을 계속 가리켰다)", left)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드122 준비/실행(schedule_events)", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — dispatch.py 로거가 실제로 루트(=app.py 의 파일핸들러)에 닿는가")
# ──────────────────────────────────────────────────────────────
try:
    import app as A                      # noqa: F401  (모듈 임포트로 _handler·루트설정이 실행됨)
    import dispatch as DP                # noqa: F401  (bokguon.dispatch 로거 생성)

    def _effective_handlers(logger):
        """Logger.callHandlers() 와 같은 규칙으로 실제로 호출될 핸들러를 모은다."""
        seen, c = [], logger
        while c:
            seen.extend(c.handlers)
            if not c.propagate:
                break
            c = c.parent
        return seen

    dp_logger = logging.getLogger("bokguon.dispatch")
    reach = _effective_handlers(dp_logger)
    chk(A._handler in reach,
        "★★★ dispatch.py 의 로거가 실제 로그파일 핸들러(app.py:_handler)에 도달한다"
        "(예전엔 app.logger 라는 형제 로거에만 붙어 있어 전혀 안 닿았다)",
        (dp_logger.name, [type(h).__name__ for h in reach]))

    #  crypto_util·legal_docs(120·121라운드가 새로 단 경고)도 같은 이유로 이제 닿는다
    for modname in ("crypto_util", "legal_docs"):
        lg = logging.getLogger(modname)
        chk(A._handler in _effective_handlers(lg),
            f"★★ {modname} 의 로거도 이제 같은 파일핸들러에 도달한다(부수적으로 함께 고쳐짐)",
            [type(h).__name__ for h in _effective_handlers(lg)])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드122 준비/실행(로거 도달성)", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[4] 실행 — 분할회피 판정이 복합사건 category 문자열에 안 막히는가")
# ──────────────────────────────────────────────────────────────
_tmpdir2 = tempfile.mkdtemp(prefix="round122b_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir2, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
try:
    import importlib
    importlib.reload(DB)
    DB.init_db()
    import compliance as CP
    importlib.reload(CP)
    conn2 = DB.get_db()

    iid = conn2.execute(
        "INSERT INTO insurers(name,status) VALUES('R122보험','활성')").lastrowid
    now_ = DB.now()

    # (a) 복합사건(work_lots 로 쪼개짐) vs 그 구성요소만 접수한 단독사건 — 이제 관련으로 잡혀야 한다
    c_composite = conn2.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,est_price,is_demo,created_at) "
        "VALUES('R122-A','접수','복합(가드레일 · 유리)','서울',?,7000000,0,?)", (iid, now_)).lastrowid
    for lot in ("가드레일", "유리"):
        conn2.execute("INSERT INTO work_lots(case_id,category) VALUES(?,?)", (c_composite, lot))
    c_simple_overlap = conn2.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,est_price,is_demo,created_at) "
        "VALUES('R122-B','접수','가드레일','서울',?,7000000,0,?)", (iid, now_)).lastrowid
    conn2.commit()

    rel_amt, rel_list = CP.related_sum(conn2, c_composite)
    chk(any(r["id"] == c_simple_overlap for r in rel_list),
        "★★★ 복합사건이 자신의 구성요소(가드레일)만 단독접수한 사건과 관련건으로 잡힌다"
        "(예전엔 'complex(A · B)' 문자열이 'A'와 절대 안 맞아 항상 rel=0)",
        (rel_amt, rel_list))

    # (b) 트레이드가 전혀 다른 두 단독사건 — 여전히(의도대로) 미합산이어야 한다
    c_glass = conn2.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,est_price,is_demo,created_at) "
        "VALUES('R122-C','접수','유리·샷시·자동문','서울',?,7000000,0,?)", (iid, now_)).lastrowid
    c_leak = conn2.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,est_price,is_demo,created_at) "
        "VALUES('R122-D','접수','누수·배관·설비','서울',?,7000000,0,?)", (iid, now_)).lastrowid
    conn2.commit()
    rel_amt2, rel_list2 = CP.related_sum(conn2, c_glass)
    chk(not any(r["id"] == c_leak for r in rel_list2),
        "STEP 트레이드가 전혀 다른 두 단독사건은 여전히 미합산이다"
        "(같은 공종 요건은 그대로 유지 — 과잉확장 아님)", rel_list2)

    # (c) 둘 다 work_lots 없이 완전히 같은 category 문자열 — 예전 방식(완전일치) 그대로 보호돼야 한다
    c_e1 = conn2.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,est_price,is_demo,created_at) "
        "VALUES('R122-E','접수','가드레일','서울',?,7000000,0,?)", (iid, now_)).lastrowid
    c_e2 = conn2.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,est_price,is_demo,created_at) "
        "VALUES('R122-F','접수','가드레일','서울',?,7000000,0,?)", (iid, now_)).lastrowid
    conn2.commit()
    rel_amt3, rel_list3 = CP.related_sum(conn2, c_e1)
    chk(any(r["id"] == c_e2 for r in rel_list3),
        "STEP work_lots 없는 두 단독사건도 category 가 같으면 여전히 관련건으로 잡힌다"
        "(기존 보호 수준 유지 — 퇴행 아님)", rel_list3)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드122 준비/실행(compliance)", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir2, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
