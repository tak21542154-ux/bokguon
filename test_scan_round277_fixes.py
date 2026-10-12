# -*- coding: utf-8 -*-
"""스캔 277라운드 회귀 — db.py migrate() 핵심 마이그레이션 함수 결함 2건
   (정밀조사 Agent가 발견, db.py 전체가 아닌 migrate() 로 범위를 좁혀 독립
   재검증 — 매 app.py 기동마다 도는 함수라 이 세션에서 가장 근본적인 지점).

  [1] status_at·발송대기함·B4(job_locks/설정/마감백필)·관리자등급·수수료율bp·
      정산백필, 6개 블록의 except 가 전부 `except: pass` 로 완전 침묵했다.
      형제인 MIGRATIONS 루프(위쪽)는 verbose 모드에서 실패를 print 하는데
      이 6곳만 침묵 — 스키마 드리프트가 있어도 아무 신호가 안 남는다.

  [2] 6개 블록 중 여러 문장을 한 커밋에 묶은 것(B4·관리자등급·정산백필)은
      except 에 rollback 이 없어, **먼저 실행된(그러나 미커밋인) 문장이
      다음 블록의 트랜잭션에 얹혀** 다음 블록이 성공하면 "우연히" 같이
      저장되고(자가치유), 뒤이은 블록들마저 전부 실패하면 close() 에서
      통째로 사라진다 — 실측(정밀조사 Agent의 폴트주입): job_locks·settings
      가 재연결 후 0행이 됐다(그 INSERT 자체는 실패하지 않았는데도). 이는
      _sweep_claim() 이 기대는 행이라, 사라지면 경매 마감이 예외도 로그도
      없이 영원히 멈춘다. 문장을 블록별로 쪼개 각자 즉시 커밋하고, 실패
      시 rollback 으로 그 블록만 깨끗이 되돌리도록 수정(job_locks 는 가장
      중요하므로 설정값·마감백필보다도 먼저·독립적으로 커밋한다).

  ⚠ 이 테스트는 임시 디렉터리의 격리 DB만 쓴다 — 운영 bokguon.db 는 전혀
    건드리지 않는다.

      python test_scan_round277_fixes.py
"""
import contextlib
import io
import os
import secrets
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []

#  ⚠ db.py 를 불러오기 전에 검증용 DB 경로부터 정한다(라운드267 교훈 —
#    순서를 잘못 두면 운영DB 안전장치에 걸린다).
_tmpdir = tempfile.mkdtemp(prefix="round277_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "unused.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


DB_SRC = read("db.py")

print("=" * 72)
print("  스캔 277라운드 회귀 — db.py migrate() 침묵 except·롤백 누락 6곳")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_mig = DB_SRC.index("def migrate(conn")
i_mig_end = DB_SRC.index("\n\n\n", i_mig)
mig_body = DB_SRC[i_mig:i_mig_end]

chk(mig_body.count("conn.rollback()") >= 6,
    "★★★★★ migrate() 의 except 6곳 모두 rollback() 을 호출한다"
    "(고치기 전엔 0곳)", mig_body.count("conn.rollback()"))
chk(mig_body.count("if verbose:\n            print(f\"  [마이그레이션]") >= 6
    or mig_body.count('if verbose:\n                print(f"  [마이그레이션]') >= 1,
    "STEP verbose 로그 print 문이 여러 곳에 있다(정확한 개수는 아래 실행 테스트로 검증)")
chk("job_locks 초기행 실패" in mig_body and "설정값 기본 백필 실패" in mig_body
    and "auctions.deadline 백필 실패" in mig_body,
    "★★★★★ 구 B4 블록이 job_locks/설정값/마감백필 3개 독립 블록으로 쪼개졌다"
    "(고치기 전엔 하나의 try 로 묶여 있었다)")
chk("관리자 등급 정규화(중간관리자) 실패" in mig_body
    and "관리자 등급 정규화(하위관리자) 실패" in mig_body,
    "★★★★ 관리자 등급 정규화 2문장이 독립 블록으로 쪼개졌다")
chk("정산 partner_id 백필 실패" in mig_body and "정산 insurer_id 백필 실패" in mig_body,
    "★★★★ 정산 partner_id·insurer_id 백필이 독립 블록으로 쪼개졌다")

# ============================================================
print("\n[2] 실행 준비 — 폴트주입 커넥션 래퍼")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
import db as DB                                                     # noqa: E402


class _FaultConn:
    """지정한 부분문자열을 담은 SQL 이 오면 즉시 OperationalError 를 던진다.
    나머지는 실커넥션에 그대로 위임한다(round268 test 의 _CloseTrackingConn 과 같은 패턴).
    """
    def __init__(self, real, fault_substrings=()):
        self._real = real
        self.fault_substrings = tuple(fault_substrings)
        self.rollback_calls = 0

    def execute(self, sql, *a, **kw):
        for sub in self.fault_substrings:
            if sub in sql:
                raise sqlite3.OperationalError(f"SIMULATED-R277: {sub[:40]}")
        return self._real.execute(sql, *a, **kw)

    def rollback(self):
        self.rollback_calls += 1
        return self._real.rollback()

    def __getattr__(self, name):
        return getattr(self._real, name)


def fresh_wrapped(fault_substrings=()):
    path = os.path.join(_tmpdir, f"r277_{secrets.token_hex(4)}.db")
    real = sqlite3.connect(path)
    real.row_factory = sqlite3.Row
    return _FaultConn(real, fault_substrings), path


def reconnect(path):
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c

# ============================================================
print("\n[3] 실행 — 정상 경로(폴트 없음): 6개 블록 모두 여전히 제 몫을 하는가(회귀 없음)")
# ------------------------------------------------------------
try:
    w3, p3 = fresh_wrapped()
    #  fee_rate bp 환산·관리자등급 정규화가 실제로 걸리도록 레거시 모양 데이터를 미리 넣는다.
    #  (SCHEMA 는 executescript 라 미리 실행해도 되지만, 더 간단히 migrate() 자체가
    #   CREATE TABLE 을 하므로 먼저 한 번 불러 스키마만 세운 뒤 값을 넣는다)
    DB.migrate(w3, verbose=False)
    w3._real.execute("INSERT INTO admins(username,password_hash,name,role,created_at) "
                      "VALUES('r277a', 'x', '테스트', '운영관리자', '2026-01-01 00:00:00')")
    ins_id = w3._real.execute(
        "INSERT INTO insurers(name) VALUES('R277보험')").lastrowid
    w3._real.execute("UPDATE insurers SET fee_rate=9.0, fee_rate_bp=NULL WHERE id=?", (ins_id,))
    w3._real.commit()

    out3 = io.StringIO()
    with contextlib.redirect_stdout(out3):
        DB.migrate(w3, verbose=True)
    chk("보험사 수수료율" in out3.getvalue() and "bp 단위로 환산" in out3.getvalue(),
        "STEP 레거시 fee_rate 가 있으면 여전히 bp 로 환산되고 verbose 로그도 찍힌다")

    fresh3 = reconnect(p3)
    locks = {r["name"] for r in fresh3.execute("SELECT name FROM job_locks")}
    chk({"auction_sweep", "dispatch_sweep", "cli_sweep"} <= locks,
        "STEP job_locks 3종 초기행이 정상 경로에서도 그대로 생긴다")
    keys = {r["key"] for r in fresh3.execute("SELECT key FROM settings")}
    chk({"auction_hours", "reminder_photo", "reminder_payment"} <= keys,
        "STEP settings 기본값이 정상 경로에서도 그대로 채워진다")
    role = fresh3.execute("SELECT role FROM admins WHERE username='r277a'").fetchone()["role"]
    chk(role == "중간관리자",
        "STEP 관리자 등급 정규화가 정상 경로에서도 그대로 동작한다(운영관리자→중간관리자)", role)
    bp_row = fresh3.execute("SELECT fee_rate, fee_rate_bp FROM insurers WHERE id=?",
                            (ins_id,)).fetchone()
    chk(bp_row["fee_rate"] is None and bp_row["fee_rate_bp"] == 900,
        "STEP fee_rate→fee_rate_bp 환산이 정상 경로에서도 그대로 동작한다(9.0→900bp)",
        dict(bp_row))
    fresh3.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드277 [3] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[4] 실행 — verbose 로그: status_at 블록이 실패하면 실제로 콘솔에 남는가")
# ------------------------------------------------------------
try:
    w4, p4 = fresh_wrapped(fault_substrings=["UPDATE cases SET status_at"])
    out4 = io.StringIO()
    with contextlib.redirect_stdout(out4):
        DB.migrate(w4, verbose=True)
    chk("status_at 백필 실패" in out4.getvalue(),
        "★★★★★ status_at 백필이 실패하면 verbose 로그로 남는다(고치기 전엔 완전 침묵)",
        out4.getvalue()[-200:])
    chk(w4.rollback_calls >= 1,
        "★★★★ 실패한 블록에서 rollback() 이 실제로 호출된다(고치기 전엔 0회)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드277 [4] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 실행 — 최악의 시나리오: job_locks 뒤의 모든 블록이 동시에 실패해도"
      " job_locks 는 살아남는가(정밀조사 Agent의 T5 재연)")
# ------------------------------------------------------------
try:
    #  job_locks 를 뺀 나머지 전부를 동시에 실패시킨다 — 예전 코드라면 job_locks
    #  insert 가 성공해도 커밋 전이라, 뒤이은 블록(관리자등급 등)이 전부 실패하면
    #  구제해줄 나중 commit()이 하나도 없어 close() 에서 통째로 사라진다.
    w5, p5 = fresh_wrapped(fault_substrings=[
        "INSERT OR IGNORE INTO settings",
        "UPDATE auctions SET deadline",
        "UPDATE admins SET role='중간관리자'",
        "UPDATE admins SET role='하위관리자'",
        "fee_rate_bp = CAST",
        "UPDATE settlements SET partner_id",
        "UPDATE settlements SET insurer_id",
    ])
    out5 = io.StringIO()
    with contextlib.redirect_stdout(out5):
        DB.migrate(w5, verbose=True)
    w5.close()                       # 커밋 안 된 것은 여기서 진짜로 사라진다(재연결로 확인)

    fresh5 = reconnect(p5)
    locks5 = {r["name"] for r in fresh5.execute("SELECT name FROM job_locks")}
    chk({"auction_sweep", "dispatch_sweep", "cli_sweep"} <= locks5,
        "★★★★★★ job_locks 는 뒤의 모든 블록이 실패해도 재연결 후에도 살아있다"
        "(고치기 전엔 재연결 후 0행 — _sweep_claim() 이 기댈 행이 없어 경매 마감이"
        " 예외·로그 없이 영원히 멈춘다)", locks5)
    settings5_n = fresh5.execute("SELECT COUNT(*) n FROM settings").fetchone()["n"]
    chk(settings5_n == 0,
        "STEP 대조군 — settings 는 의도대로 실패해 0건이다(과잉통과 아님을 확인)",
        settings5_n)
    fresh5.close()

    for expect in ("설정값 기본 백필 실패", "auctions.deadline 백필 실패",
                   "관리자 등급 정규화(중간관리자) 실패", "관리자 등급 정규화(하위관리자) 실패",
                   "보험사 수수료율 bp 환산 실패", "정산 partner_id 백필 실패",
                   "정산 insurer_id 백필 실패"):
        chk(expect in out5.getvalue(), f"STEP 로그에 남음 — {expect}")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드277 [5] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[6] 실행 — 관리자 등급 G2(하위관리자)가 실패해도 G1(중간관리자)은 남는가")
# ------------------------------------------------------------
try:
    w6, p6 = fresh_wrapped()
    DB.migrate(w6, verbose=False)
    w6._real.execute("INSERT INTO admins(username,password_hash,name,role,created_at) "
                      "VALUES('r277g', 'x', '테스트', '운영관리자', '2026-01-01 00:00:00')")
    w6._real.commit()

    w6.fault_substrings = ("UPDATE admins SET role='하위관리자'",)
    out6 = io.StringIO()
    with contextlib.redirect_stdout(out6):
        DB.migrate(w6, verbose=True)
    w6.close()

    fresh6 = reconnect(p6)
    role6 = fresh6.execute("SELECT role FROM admins WHERE username='r277g'").fetchone()["role"]
    fresh6.close()
    chk(role6 == "중간관리자",
        "★★★★★ G2(하위관리자 정규화)가 실패해도 G1(운영관리자→중간관리자)은 커밋된 채 남는다"
        "(고치기 전엔 한 트랜잭션이라 G2 실패 시 G1 도 미커밋 상태로 흔들렸다)", role6)
    chk("관리자 등급 정규화(하위관리자) 실패" in out6.getvalue(), "STEP G2 실패가 로그에 남는다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드277 [6] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[7] 실행 — 정산 I2(insurer_id)가 실패해도 I1(partner_id)은 남는가")
# ------------------------------------------------------------
try:
    w7, p7 = fresh_wrapped()
    DB.migrate(w7, verbose=False)
    mark7 = "R277-" + secrets.token_hex(3)
    w7._real.execute("INSERT INTO partners(name) VALUES(?)", (mark7,))
    w7._real.execute("INSERT INTO insurers(name) VALUES(?)", (mark7,))
    w7._real.execute(
        "INSERT INTO settlements(case_no, insurer, partner_name, amount, fee, payout) "
        "VALUES('C-R277', ?, ?, 1000, 100, 900)", (mark7, mark7))
    w7._real.commit()

    w7.fault_substrings = ("UPDATE settlements SET insurer_id",)
    out7 = io.StringIO()
    with contextlib.redirect_stdout(out7):
        DB.migrate(w7, verbose=True)
    w7.close()

    fresh7 = reconnect(p7)
    row7 = fresh7.execute("SELECT partner_id, insurer_id FROM settlements WHERE case_no='C-R277'"
                          ).fetchone()
    fresh7.close()
    chk(row7["partner_id"] is not None and row7["insurer_id"] is None,
        "★★★★★ I2(insurer_id 백필)가 실패해도 I1(partner_id 백필)은 커밋된 채 남는다"
        "(고치기 전엔 한 트랜잭션이라 I2 실패 시 I1 도 미커밋 상태로 흔들렸다)", dict(row7))
    chk("정산 insurer_id 백필 실패" in out7.getvalue(), "STEP I2 실패가 로그에 남는다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드277 [7] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[8] 실행 — 두 번 연속 migrate() 해도 안전한가(멱등성 회귀 없음)")
# ------------------------------------------------------------
try:
    w8, p8 = fresh_wrapped()
    DB.migrate(w8, verbose=False)
    applied2 = DB.migrate(w8, verbose=False)
    chk(applied2 == [], "STEP 두 번째 migrate() 는 추가로 적용할 컬럼이 없다(정상 멱등)")
    fresh8 = reconnect(p8)
    n_locks = fresh8.execute("SELECT COUNT(*) n FROM job_locks").fetchone()["n"]
    fresh8.close()
    chk(n_locks == 3, "STEP 두 번 돌려도 job_locks 가 중복되지 않는다(INSERT OR IGNORE)", n_locks)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드277 [8] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
