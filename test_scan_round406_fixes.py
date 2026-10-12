# -*- coding: utf-8 -*-
"""스캔 406라운드 회귀 — run_all_tests.py 가 공유 verify.db 를 명시적으로
   초기화하지 않아, UNIT 목록에서 우연히 가장 먼저 `import app` 하는
   파일(test_template_js.py, 자기 검사엔 데모데이터가 필요없어
   BOKGUON_SEED_DEMO=0 을 스스로 세팅함)이 그 선택을 공유 DB 전체에
   떠넘기던 결함.

  배경: 405라운드가 test_b4_deadline.py 배터리 플레이크를 고치는 과정에서
  전체 UNIT 배터리(--quick)를 두 번 재현했는데, 둘 다 스캔 28·29라운드가
  `SELECT id FROM insurers LIMIT 1`.fetchone()["id"] 에서 `TypeError:
  'NoneType' object is not subscriptable` 로 죽었다(공유 DB 의 insurers
  테이블이 완전히 비어 있었다). 두 파일 다 단독 실행하면 완전히 클린이라
  배터리 위치의존적 결함으로 확정, 406라운드가 파일 단위로 COUNT(insurers)
  를 찍어 정확한 전환점을 찾았다 — test_fresh_db.py·test_dead_actions.py
  뒤에도 DB 파일 자체가 없다가, test_template_js.py 실행 직후 insurers=0
  으로(파일은 생기지만 시드는 안 됨) 떨어진다. app.py 자신이 122행에서
  무조건 DB.init_db() 를 부르고, test_template_js.py 는 자기 검사(템플릿
  인라인 JS 파싱)에 데모데이터가 필요없어 `import app` 전에
  BOKGUON_SEED_DEMO=0 을 setdefault 로 세팅해 둔다 — 그 선택이 자기
  프로세스에 한정될 의도였지만, 공유 DB 를 최초로 만드는 역할을
  우연히 떠맡는 바람에 이후 도는 모든 UNIT 테스트가 그 선택을 물려받았다.

  고침: run_all_tests.py 의 main() 에서 BOKGUON_DB_PATH 가 실제로 설정된
  경우, UNIT 루프 시작 전에 `DB.init_db(seed_demo=True)` 를 명시적으로
  호출해 둔다 — seed_demo 를 환경변수가 아니라 함수 인자로 강제하므로,
  어느 UNIT 파일이 우연히 "처음 여는 자"가 되든 그 파일 자신의
  BOKGUON_ENV/BOKGUON_SEED_DEMO 선택과 무관하게 공유 DB 는 항상 씨드된
  상태로 시작한다(db.py 의 admins==0 게이트 때문에 이후 재호출은
  다시 지우거나 건너뛰지 않는다).

      python test_scan_round406_fixes.py
"""
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


RAT_SRC = read("run_all_tests.py")

print("=" * 72)
print("  스캔 406라운드 회귀 — 공유 verify.db 초기화 누락(insurers 전체누락)")
print("=" * 72)

print("\n[1] 소스 확인")
FIX_SNIPPET = "    if dbp:\n        import db as DB\n        DB.init_db(seed_demo=True)"
chk(FIX_SNIPPET in RAT_SRC,
    "★★★★★ run_all_tests.py 가 dbp 확인 후 DB.init_db(seed_demo=True) 를 명시적으로 부른다")


def count_insurers(dbpath):
    if not os.path.exists(dbpath):
        return "no-file"
    import sqlite3
    conn = sqlite3.connect(dbpath)
    try:
        return conn.execute("SELECT COUNT(*) FROM insurers").fetchone()[0]
    except sqlite3.OperationalError as e:
        return f"err:{e}"
    finally:
        conn.close()


def run_template_js_only(dbpath):
    """test_template_js.py 를 유일한 실행자로 삼아 서브프로세스로 돌린다
       (실제 배터리에서 이 파일이 공유 DB 를 처음 여는 역할을 우연히
       떠맡는 것과 동일한 조건 — BOKGUON_DB_PATH 만 주고 나머지는 안 준다)."""
    env = dict(os.environ)
    env["BOKGUON_DB_PATH"] = dbpath
    for k in ("BOKGUON_ENV", "BOKGUON_SEED_DEMO"):
        env.pop(k, None)
    r = subprocess.run([sys.executable, "test_template_js.py"], cwd=HERE, env=env,
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace", timeout=60)
    return r


print("\n[2] 실행 — 고친 순서(먼저 seed_demo=True 로 초기화 후 template_js 실행)")
_tmp2 = tempfile.mkdtemp(prefix="round406_after_")
db_after = os.path.join(_tmp2, "verify.db")
try:
    env_init = dict(os.environ)
    env_init["BOKGUON_DB_PATH"] = db_after
    for k in ("BOKGUON_ENV", "BOKGUON_SEED_DEMO"):
        env_init.pop(k, None)
    #  run_all_tests.py 의 고친 로직과 정확히 같은 호출(같은 프로세스가
    #  아니라 서브프로세스로 재현 — db.py 의 DB_PATH 가 import 시점에
    #  고정되므로 "run_all_tests.py 를 부르기 전 초기화" 순서를 그대로
    #  흉내내려면 별도 프로세스가 더 정확하다).
    r0 = subprocess.run(
        [sys.executable, "-c",
         "import db as DB; DB.init_db(seed_demo=True); "
         "print('inited', DB.get_db().execute('SELECT COUNT(*) FROM insurers').fetchone()[0])"],
        cwd=HERE, env=env_init, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30)
    chk(r0.returncode == 0 and "inited" in (r0.stdout or ""),
        "  명시적 초기화 단계가 정상 실행된다", (r0.stdout, r0.stderr)[:2])

    r1 = run_template_js_only(db_after)
    chk(r1.returncode == 0, "  이어서 test_template_js.py 도 정상 통과한다", r1.stdout[-300:])

    n_after = count_insurers(db_after)
    chk(n_after == 6,
        "★★★★★ 먼저 초기화해 두면 template_js 가 SEED_DEMO=0 을 셋팅해도 insurers 는 그대로 6",
        n_after)
except Exception as e:                                             # noqa: BLE001
    chk(False, "★★★★★ 준비/실행([2] 고친 순서)", f"{type(e).__name__} {e}")

print("\n[3] 되돌리기 — 초기화 단계 없이 template_js 를 최초 실행자로 두면(옛 순서) 재현되는가")
_tmp3 = tempfile.mkdtemp(prefix="round406_before_")
db_before = os.path.join(_tmp3, "verify.db")
try:
    r2 = run_template_js_only(db_before)
    chk(r2.returncode == 0, "  template_js 자신은 정상 통과한다(회귀없음)", r2.stdout[-300:])
    n_before = count_insurers(db_before)
    chk(n_before == 0,
        "★★★★★ 초기화 단계 없이 template_js 가 최초 실행자면 insurers=0 으로 재현된다"
        "(고치기 전 실제 배터리에서 관찰된 것과 동일한 메커니즘)", n_before)
except Exception as e:                                             # noqa: BLE001
    chk(False, "★★★★★ 준비/실행([3] 옛 순서 재현)", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
