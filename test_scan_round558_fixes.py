# -*- coding: utf-8 -*-
"""스캔 558라운드 회귀 — sweep_dispatches() 의 같은 루프 안 형제 셋 중 둘
(출동 실패 처리기·회차소진 처리기)이 raise 로 스윕 전체를 끊던 결함.

  round557 이 제안한 각도를 직접 조사(하위위임 없음) — 셋째 형제(재수배
  처리기, 라운드182·411이 이미 고친 자리)는 "대상 하나의 실패가 나머지
  전부의 처리를 막아선 안 된다"(이 함수 docstring 자신이 못박은 존재
  이유)는 원칙으로 rollback 후 continue 하는데, 나머지 둘(출동 실패
  처리기·회차소진 처리기)은 여전히
  `except Exception: conn.rollback(); raise` 로 남아 있었다 — 대상 하나의
  일시적 DB 락 경합만으로도 이 스윕(최대 SWEEP_LIMIT=50건)의 나머지 대상
  전부, 나아가 manage.py cmd_sweep()(라운드557이 고친 그 바깥 경계)의
  이후 단계(무입찰경보~웹훅재전송·cli_sweep 생존신호)까지 이번 회차 전부
  건너뛰게 만드는 훨씬 큰 사고로 이어진다 — 조사 결과 이 둘이 형제와
  다르게 raise 해야 할 트랜잭션/리스 상의 이유는 없었다(rollback 이 이미
  이 대상의 미완료 트랜잭션을 정리하므로 다음 대상의 BEGIN IMMEDIATE 는
  안전하다 — 형제가 이미 증명한 것과 같은 전제).

  고침 — 두 처리기 모두 형제(재수배 처리기)와 같은 원칙으로 수렴한다.
   · 출동 실패 처리기: rollback 후 로그하고 continue(바로 위 CAS-미스
     분기 자신과 같은 처방).
   · 회차소진 처리기: rollback 후 로그만 하고 raise 하지 않는다(이 if
     분기가 for 루프 몸통의 마지막이라 continue 없이도 자연스럽게 다음
     대상으로 넘어간다) — res["gaveup"] 증가도 성공했을 때만 세도록 try
     안(commit 직후)으로 옮겼다(실패를 성공으로 잘못 세지 않는다).

  이 회귀테스트는 ONLY 안전한 기법만 쓴다 — 실제 dispatch.py 는 몽키패치
  대상(DB.log)만 갈아 끼워 실제 DP.sweep_dispatches()를 그대로 부르고,
  '되돌리기' 증명은 지금 파일에서 읽은 실제 함수 본문 문자열의 딱 그 두
  지점만(짧고 고유한 표식으로 잘라) 옛 모양으로 되돌린 사본을 만들어
  exec()로 돌려 인과관계를 실측한다(on-disk dispatch.py는 전혀 건드리지
  않는다 — 이 세션의 절대 규칙).

      python test_scan_round558_fixes.py
"""
import ast
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


DISPATCH_SRC = read("dispatch.py")

print("=" * 72)
print("  스캔 558라운드 회귀 — sweep_dispatches() 형제 처리기 셋 중 둘의 raise")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — 두 처리기 모두 raise 가 사라지고 형제(재수배 처리기)와 수렴했는가")
# ------------------------------------------------------------
i0 = DISPATCH_SRC.index("def sweep_dispatches(")
i1 = DISPATCH_SRC.index("\ndef ", i0 + 1)
SD_BODY = DISPATCH_SRC[i0:i1]

chk(SD_BODY.count("[라운드558]") == 2,
    "★★★★ sweep_dispatches 안에 라운드558 표식이 정확히 2곳(두 처리기) 있다",
    SD_BODY.count("[라운드558]"))

chk('except Exception:\n                #  ⚠⚠ [라운드558] 같은' in SD_BODY,
    "★★★★★ 첫 번째 처리기(출동 실패 처리)가 라운드558 주석으로 바뀌었다")
chk('conn.rollback()\n                _log.exception("출동 실패 처리 실패 dispatch=%s", t["id"])\n'
    '                continue\n            res["expired"] += 1' in SD_BODY,
    "★★★★★ 첫 번째 처리기가 rollback 후 로그하고 continue 한다(raise 로 "
    "스윕 전체를 끊지 않는다) — 바로 위 CAS-미스 분기 자신과 같은 모양")
chk('conn.rollback()\n                raise\n            res["expired"]' not in SD_BODY,
    "★★★ 첫 번째 처리기의 옛 raise 형태가 사라졌다")

chk('conn.commit()\n                    res["gaveup"] += 1\n                except Exception:\n'
    '                    #  ⚠⚠ [라운드558] 형제' in SD_BODY,
    "★★★★★ 두 번째 처리기(회차소진)의 res[gaveup] 증가가 try 안"
    "(commit 직후, 성공시에만)으로 옮겨졌다")
chk('conn.rollback()\n                    _log.exception("출동수배 중단 처리 실패 case=%s", t["case_id"])\n'
    '            else:' in SD_BODY,
    "★★★★★ 두 번째 처리기가 rollback 후 로그만 하고 raise 하지 않는다"
    "(이 if 가 for 몸통의 마지막이라 continue 없이도 자연스럽게 다음 대상으로)")
chk('except Exception:\n                    conn.rollback()\n                    raise\n'
    '                res["gaveup"]' not in SD_BODY,
    "★★★ 두 번째 처리기의 옛 raise 형태가 사라졌다")

chk('except Exception:\n                    #  ⚠⚠ [라운드182]' in SD_BODY,
    "  형제(세 번째 처리기, 재수배)는 이번 수정과 무관하게 그대로 보존됨(회귀 없음)")
chk(SD_BODY.count("except Exception:") == 4,
    "  except 블록 수는 여전히 4개(루프 안 형제 셋 + 함수 맨 끝의 바깥"
    "(981행대) 처리기 — 형태만 바뀌었지 처리기 자체를 더하거나 빼지 않았다)",
    SD_BODY.count("except Exception:"))

try:
    ast.parse(DISPATCH_SRC)
    chk(True, "★★ dispatch.py 전체가 여전히 유효한 파이썬 구문이다")
except SyntaxError as e:
    chk(False, "★★★★★ dispatch.py 전체가 여전히 유효한 파이썬 구문이다", str(e))

# ============================================================
print("\n[2] 되돌리기 준비 — 지금 소스에서 딱 그 두 지점만 옛(raise) 모양으로 "
      "되돌린 사본을 만든다(on-disk 파일은 안 건드림)")
# ------------------------------------------------------------
#  ⚠ 긴 주석 블록을 통째로 손으로 다시 타이핑하는 대신, 짧고 고유한 표식만
#    잘라 옛 모양으로 바꿔치기한다 — 한 글자라도 틀리면 .replace() 가
#    조용히 매칭에 실패해 "되돌린 사본"이 사실은 새 코드 그대로인 채로
#    있을 위험을 줄인다.
h1_marker = 'except Exception:\n                #  ⚠⚠ [라운드558] 같은'
h1_start = SD_BODY.index(h1_marker)
h1_tail = 'res["expired"] += 1'
h1_end = SD_BODY.index(h1_tail, h1_start) + len(h1_tail)
OLD_FN_SRC = (SD_BODY[:h1_start]
              + 'except Exception:\n'
              + '                conn.rollback()\n'
              + '                raise\n'
              + '            res["expired"] += 1'
              + SD_BODY[h1_end:])

h2_marker = ('conn.commit()\n                    res["gaveup"] += 1\n'
             '                except Exception:')
h2_start = OLD_FN_SRC.index(h2_marker)
h2_tail_marker = '_log.exception("출동수배 중단 처리 실패 case=%s", t["case_id"])'
h2_end = OLD_FN_SRC.index(h2_tail_marker, h2_start) + len(h2_tail_marker)
OLD_FN_SRC = (OLD_FN_SRC[:h2_start]
              + 'conn.commit()\n'
              + '                except Exception:\n'
              + '                    conn.rollback()\n'
              + '                    raise\n'
              + '                res["gaveup"] += 1'
              + OLD_FN_SRC[h2_end:])

chk(OLD_FN_SRC != SD_BODY,
    "  되돌린 사본이 실제로 지금 소스와 다르다(치환이 헛돌지 않았다)")
chk('raise\n            res["expired"]' in OLD_FN_SRC
    and 'raise\n                res["gaveup"]' in OLD_FN_SRC,
    "  되돌린 사본에 옛 raise 모양 두 곳이 실제로 들어갔다(재현 전제조건)")
chk("[라운드558]" not in OLD_FN_SRC,
    "  되돌린 사본에는 라운드558 주석 흔적이 안 남는다")

OLD_FN_SRC = OLD_FN_SRC.replace("def sweep_dispatches(", "def _old_sweep_dispatches(", 1)
try:
    ast.parse(OLD_FN_SRC)
    chk(True, "  되돌린 사본도 그 자체로 유효한 파이썬 구문이다")
except SyntaxError as e:
    chk(False, "★★★ 되돌린 사본도 그 자체로 유효한 파이썬 구문이다", str(e))

# ============================================================
print("\n[3] 준비 — 스크래치 DB, 실제 모듈 로드")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round558_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import dispatch as DP

    conn = DB.get_db()
    max_round = DP.dispatch_max_round(conn)
    chk(max_round > 1,
        "  전제조건 — dispatch_max_round()(기본3)가 1보다 커서 round=1 은 "
        "아직 회차소진이 아니다(첫 처리기 시나리오와 둘째 처리기 시나리오를 "
        "서로 다른 회차로 명확히 나눌 수 있다)", max_round)

    class _PoisonLog:
        """DB.log 를 감싸 지정한 (action, marker) 조합일 때만 실패시키고
        나머지는 그대로 진짜 DB.log 를 부른다 — 대상 하나의 실패만 정확히
        겨냥해 타이밍에 기대지 않고 결정론적으로 재현한다."""
        def __init__(self, real):
            self._real = real
            self.action = None
            self.marker = None
            self.hits = 0

        def arm(self, action, marker):
            self.action, self.marker, self.hits = action, marker, 0

        def disarm(self):
            self.action = self.marker = None

        def __call__(self, conn_, actor, action, detail=""):
            if self.action is not None and action == self.action and self.marker in detail:
                self.hits += 1
                raise sqlite3.OperationalError(
                    f"simulated: database is locked ({self.marker})")
            return self._real(conn_, actor, action, detail)

    _real_log = DB.log
    poison = _PoisonLog(_real_log)
    DB.log = poison

    def mk_target(tag, round_no, dispatch_status="출동중"):
        cid = conn.execute(
            "INSERT INTO cases(case_no,status,category,region,dispatch_status,"
            "is_demo,created_at) VALUES(?,'접수','가드레일','서울',?,0,?)",
            (f"R558-{tag}", dispatch_status, DB.now())).lastrowid
        did = conn.execute(
            "INSERT INTO dispatches(case_id,status,round,due_at,claimed_partner_id,"
            "created_at) VALUES(?,?,?,'2020-01-01 00:00:00',999,?)",
            (cid, DP.ST_CLAIMED, round_no, DB.now())).lastrowid
        conn.commit()
        return cid, did

    def dstatus(did):
        return conn.execute("SELECT status FROM dispatches WHERE id=?",
                             (did,)).fetchone()["status"]

    def cdispatch_status(cid):
        return conn.execute("SELECT dispatch_status FROM cases WHERE id=?",
                             (cid,)).fetchone()["dispatch_status"]

    def ndispatches(cid):
        return conn.execute("SELECT COUNT(*) c FROM dispatches WHERE case_id=?",
                             (cid,)).fetchone()["c"]

    old_globals = {
        "SWEEP_LIMIT": DP.SWEEP_LIMIT,
        "ST_OPEN": DP.ST_OPEN,
        "ST_CLAIMED": DP.ST_CLAIMED,
        "ST_FAILED": DP.ST_FAILED,
        "CS_FAILED": DP.CS_FAILED,
        "DISPATCH_OVERDUE_SQL": DP.DISPATCH_OVERDUE_SQL,
        "DISPATCH_UNCLAIMED_SQL": DP.DISPATCH_UNCLAIMED_SQL,
        "dispatch_minutes": DP.dispatch_minutes,
        "dispatch_max_round": DP.dispatch_max_round,
        "_claim_lease": DP._claim_lease,
        "_release_lease": DP._release_lease,
        "_log": DP._log,
        "DB": DB,
        "open_dispatch": DP.open_dispatch,
    }
    exec(compile(OLD_FN_SRC, "<r558_old_sweep_dispatches>", "exec"), old_globals)
    old_sweep_dispatches = old_globals["_old_sweep_dispatches"]

    # ============================================================
    print("\n[4] 실행 — 첫 번째 처리기(출동 실패 처리)만 실패시킨 실제 "
          "DP.sweep_dispatches()")
    # ------------------------------------------------------------
    cid_a1, did_a1 = mk_target("A1", round_no=1)
    cid_a2, did_a2 = mk_target("A2", round_no=1)
    poison.arm("출동 실패", "R558-A1")
    raised_a = None
    try:
        DP.sweep_dispatches(conn, force=True)
    except Exception as e:                                          # noqa: BLE001
        raised_a = e
    finally:
        poison.disarm()

    chk(poison.hits == 1,
        "  준비 확인 — 의도한 대상(A1)의 '출동 실패' 로그가 실제로 1회 실패했다",
        poison.hits)
    chk(raised_a is None,
        "★★★★★ 대상A1 의 실패가 있어도 실제 sweep_dispatches() 는 예외 없이 "
        "정상 반환한다(고치기 전엔 통째로 죽었다)",
        f"{type(raised_a).__name__}: {raised_a}" if raised_a else "정상")
    chk(dstatus(did_a1) == DP.ST_CLAIMED,
        "★★★★★ A1 자신은 rollback 되어 원래 상태(수배됨) 그대로다"
        "(commit 전에 실패했으므로 되돌아간다)", dstatus(did_a1))
    chk(ndispatches(cid_a1) == 1,
        "  A1 은 재수배 시도조차 안 됨(다음 회차 dispatches 행이 새로 안 생김)",
        ndispatches(cid_a1))
    chk(dstatus(did_a2) == DP.ST_FAILED,
        "★★★★★ A2(정상)는 A1 의 실패와 무관하게 끝까지 '실패' 처리됐다"
        "(대상 하나의 실패가 나머지를 막지 않는다)", dstatus(did_a2))

    # ============================================================
    print("\n[5] 되돌리기 — 같은 조건, 옛(raise) 사본에서는 실제로 예외가 새고 "
          "A2 는 아예 처리되지 못하는가")
    # ------------------------------------------------------------
    cid_a1b, did_a1b = mk_target("A1B", round_no=1)
    cid_a2b, did_a2b = mk_target("A2B", round_no=1)
    poison.arm("출동 실패", "R558-A1B")
    raised_ab = None
    try:
        old_sweep_dispatches(conn, force=True, notify=None)
    except Exception as e:                                          # noqa: BLE001
        raised_ab = e
    finally:
        poison.disarm()

    chk(raised_ab is not None,
        "★★★★★ 옛(raise) 모양은 같은 조건에서 실제로 예외가 밖으로 샌다"
        "(인과관계 직접증명)", repr(raised_ab))
    chk(dstatus(did_a1b) == DP.ST_CLAIMED,
        "  옛 모양에서도 A1B 자신은 rollback 되어 원상태(전제조건 동일 확인)",
        dstatus(did_a1b))
    chk(dstatus(did_a2b) == DP.ST_CLAIMED,
        "★★★★★ 옛 모양에서는 A2B 가 아예 손도 안 닿은 채(여전히 '수배됨') "
        "남는다 — A1B 하나의 실패가 A2B 까지 막았다([4]와 정반대 결과)",
        dstatus(did_a2b))

    # ============================================================
    print("\n[6] 실행 — 두 번째 처리기(회차소진)만 실패시킨 실제 "
          "DP.sweep_dispatches()")
    # ------------------------------------------------------------
    cid_b1, did_b1 = mk_target("B1", round_no=max_round, dispatch_status="출동중")
    cid_b2, did_b2 = mk_target("B2", round_no=max_round, dispatch_status="출동중")
    poison.arm("출동수배 중단", "R558-B1")
    raised_b = None
    try:
        DP.sweep_dispatches(conn, force=True)
    except Exception as e:                                          # noqa: BLE001
        raised_b = e
    finally:
        poison.disarm()

    chk(poison.hits == 1,
        "  준비 확인 — 의도한 대상(B1)의 '출동수배 중단' 로그가 실제로 1회 실패했다",
        poison.hits)
    chk(raised_b is None,
        "★★★★★ B1 의 회차소진 처리 실패가 있어도 실제 sweep_dispatches() 는 "
        "예외 없이 정상 반환한다(고치기 전엔 통째로 죽었다)",
        f"{type(raised_b).__name__}: {raised_b}" if raised_b else "정상")
    chk(dstatus(did_b1) == DP.ST_FAILED,
        "  B1 자신의 출동은 별도의 먼저 커밋된 트랜잭션이라 회차소진 실패와 "
        "무관하게 '실패' 그대로다", dstatus(did_b1))
    chk(cdispatch_status(cid_b1) != DP.CS_FAILED,
        "★★★★★ B1 의 사건 차원 전환(CS_FAILED)만 rollback 되어 원래 값 "
        "그대로다(commit 전에 실패했으므로 되돌아간다)",
        cdispatch_status(cid_b1))
    chk(dstatus(did_b2) == DP.ST_FAILED,
        "  B2 도 정상적으로 '실패' 처리됐다", dstatus(did_b2))
    chk(cdispatch_status(cid_b2) == DP.CS_FAILED,
        "★★★★★ B2(정상)는 B1 의 실패와 무관하게 끝까지 '수배실패'로 "
        "전환됐다(대상 하나의 실패가 나머지를 막지 않는다)",
        cdispatch_status(cid_b2))

    # ============================================================
    print("\n[7] 되돌리기 — 같은 조건, 옛(raise) 사본에서는 실제로 예외가 새고 "
          "B2 는 아예 처리되지 못하는가")
    # ------------------------------------------------------------
    cid_b1c, did_b1c = mk_target("B1C", round_no=max_round, dispatch_status="출동중")
    cid_b2c, did_b2c = mk_target("B2C", round_no=max_round, dispatch_status="출동중")
    poison.arm("출동수배 중단", "R558-B1C")
    raised_bc = None
    try:
        old_sweep_dispatches(conn, force=True, notify=None)
    except Exception as e:                                          # noqa: BLE001
        raised_bc = e
    finally:
        poison.disarm()

    chk(raised_bc is not None,
        "★★★★★ 옛(raise) 모양은 같은 조건에서 실제로 예외가 밖으로 샌다"
        "(인과관계 직접증명)", repr(raised_bc))
    chk(dstatus(did_b1c) == DP.ST_FAILED,
        "  옛 모양에서도 B1C 자신의 출동은 이미 확정 커밋(전제조건 동일 확인)",
        dstatus(did_b1c))
    chk(dstatus(did_b2c) == DP.ST_CLAIMED,
        "★★★★★ 옛 모양에서는 B2C 가 아예 손도 안 닿은 채(여전히 '수배됨') "
        "남는다 — B1C 하나의 회차소진 실패가 B2C 까지 막았다([6]과 정반대 결과)",
        dstatus(did_b2c))

    DB.log = _real_log
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드558 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
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
