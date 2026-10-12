# -*- coding: utf-8 -*-
"""스캔 188라운드 회귀 — 두 결함.

  ① manage.py cmd_sweep(): 형제 스윕(overdue·rem·dsp·appr·snd·whr·war)은 전부
    콘솔에 결과를 보고하는데 nobid(무입찰 경보)만 반환값을 변수에 담아 놓고
    어디에도 안 찍었다. 실제 알림은 정상 발송되지만 운영자는 이 스윕이 도는지
    조용히 죽었는지 콘솔로는 알 길이 없었다.

  ② manage.py cmd_prune_personal(): 형제 명령 prune-orphans·go-live 는 전부
    본 트랜잭션에 `except sqlite3.Error` 를 두는데 이 함수만 없어서, 도중에
    쿼리가 실패하면 정리된 bad() 메시지 대신 처리 안 된 traceback 으로 죽었다.

      python test_scan_round188_fixes.py
"""
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


MANAGE_SRC = read("manage.py")

print("=" * 72)
print("  스캔 188라운드 회귀 — cmd_sweep 보고 누락 · cmd_prune_personal 예외처리 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = MANAGE_SRC.index("def cmd_sweep(argv):")
i1 = MANAGE_SRC.index("\ndef ", i0 + 1)
sweep_body = MANAGE_SRC[i0:i1]

chk("nobid, overdue, rem, snd, appr, dsp, whr, war = 0, 0, {}, {}, {}, {}, 0, 0" in sweep_body,
    "★★★★ nobid 도 다른 스윕들과 함께 --dry-run 대비 사전 초기화된다"
    "(빠뜨리면 --dry-run 이 UnboundLocalError 로 죽는다 — 947행 자신의 주석이 경고)")
chk('if nobid:' in sweep_body and 'ok(f"무입찰 경보 {nobid}건 발송")' in sweep_body,
    "★★★★ 무입찰 경보 발송 건수가 형제들과 같은 방식으로 콘솔에 보고된다")

i2 = MANAGE_SRC.index("def cmd_prune_personal(argv):")
i3 = MANAGE_SRC.index("\ndef ", i2 + 1)
prune_body = MANAGE_SRC[i2:i3]
chk("except sqlite3.Error as e:" in prune_body and 'bad(f"파기 실패: {e}")' in prune_body
    and "return 1" in prune_body.split("except sqlite3.Error as e:", 1)[1].split("finally:", 1)[0],
    "★★★ prune-personal 도 형제(prune-orphans·go-live)와 같은 "
    "except sqlite3.Error → rollback → bad() → return 1 을 가진다")

# ============================================================
print("\n[2] 실행 — ① 무입찰 경보 스윕이 --dry-run 에서 안 죽고, 실행 시 보고된다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round188_")
db_path = os.path.join(_tmpdir, "verify.db")
seed_path = os.path.join(_tmpdir, "seed_and_run.py")

SEED_SCRIPT = f'''# -*- coding: utf-8 -*-
import contextlib
import io
import os
import sys

os.environ["BOKGUON_DB_PATH"] = {db_path!r}
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, {HERE!r})

import db as DB
DB.init_db()
conn = DB.get_db()
now = DB.now()

conn.execute(
    "INSERT INTO insurers(id, name, is_demo) VALUES(8801, 'R188보험', 0)")
conn.execute(
    "INSERT INTO cases(id, case_no, insurer_id, category, region, status, is_demo, created_at) "
    "VALUES(8801, 'R188-001', 8801, '유리', '서울', '접수', 0, ?)", (now,))
#  마감까지 10분(h_left≈0.17h), 창은 10시간(h_win≈10h) — 3분의 1(≈3.3h)보다
#  훨씬 적게 남아 즉시 경보 대상이 된다. 입찰은 0건, 데모도 아니다.
conn.execute(
    "INSERT INTO auctions(id, case_id, status, deadline, created_at) "
    "VALUES(8801, 8801, '진행', datetime('now','+9 hours','+10 minutes'), "
    "       datetime('now','+9 hours','-10 hours'))")
conn.commit()
conn.close()

import manage as M

#  --dry-run 은 원래도 안 죽었지만(수정 대상은 콘솔보고 누락이지, dry-run 크래시가
#  아니다) — 사전초기화 목록에서 nobid 를 빠뜨리는 실수를 하면 바로 여기서
#  UnboundLocalError 로 죽으므로, 이 실행 자체가 그 실수에 대한 회귀 방지막이다.
buf0 = io.StringIO()
with contextlib.redirect_stdout(buf0):
    rc0 = M.cmd_sweep(["--dry-run"])
print("===DRY_RC===" + str(rc0))

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = M.cmd_sweep([])
print("===RC===" + str(rc))
print("===OUT_START===")
print(buf.getvalue())
print("===OUT_END===")
'''

with io.open(seed_path, "w", encoding="utf-8") as f:
    f.write(SEED_SCRIPT)

try:
    result = subprocess.run([PY, "-u", seed_path], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=60)
    out = result.stdout
    if "===OUT_START===" not in out:
        chk(False, "★★★ 라운드188 [2] 준비 스크립트 실행",
            f"exit={result.returncode}\nSTDOUT:\n{out}\nSTDERR:\n{result.stderr}")
    else:
        dry_rc = next((l for l in out.splitlines() if l.startswith("===DRY_RC===")), "?")
        chk(dry_rc == "===DRY_RC===0",
            "★★★★ --dry-run 이 UnboundLocalError 없이 정상 종료한다"
            "(nobid 사전초기화 누락 시 여기서 즉시 죽는다)", dry_rc)

        preview_out = out.split("===OUT_START===", 1)[1].split("===OUT_END===", 1)[0]
        chk("무입찰 경보 1건 발송" in preview_out,
            "★★★★ 마감임박·무입찰 사건 1건에 대해 경보 발송 사실이 콘솔에 나타난다"
            "(고치기 전엔 실제 발송은 되는데 콘솔엔 아무 줄도 없었다)",
            f"전체 출력:\n{preview_out}")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드188 [2] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — ② prune-personal 이 도중에 쿼리 실패해도 traceback 대신 "
      "정리된 실패로 끝난다")
# ------------------------------------------------------------
seed_path2 = os.path.join(_tmpdir, "seed_and_run2.py")
db_path2 = os.path.join(_tmpdir, "verify2.db")

SEED_SCRIPT2 = f'''# -*- coding: utf-8 -*-
import contextlib
import io
import os
import sqlite3
import sys

os.environ["BOKGUON_DB_PATH"] = {db_path2!r}
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, {HERE!r})

import db as DB
DB.init_db()
import manage as M

_real_get_db = DB.get_db

class _BreakingConn:
    """defects 를 건드리는 쿼리(⑤단계, 함수 뒤쪽)만 표적으로 실패시켜 그
    앞의 n1~n4c 단계가 이미 실행된 '도중' 상태를 재현한다."""
    def __init__(self, real):
        self._real = real

    def execute(self, sql, *a, **kw):
        if "FROM defects" in sql:
            raise sqlite3.OperationalError("R188 검증용 강제 실패")
        return self._real.execute(sql, *a, **kw)

    def __getattr__(self, name):
        return getattr(self._real, name)

def _patched_get_db(*a, **kw):
    return _BreakingConn(_real_get_db(*a, **kw))

M.DB.get_db = _patched_get_db

buf = io.StringIO()
rc = None
threw = None
with contextlib.redirect_stdout(buf):
    try:
        rc = M.cmd_prune_personal([])
    except Exception as e:                                          # noqa: BLE001
        threw = f"{{type(e).__name__}}: {{e}}"

print("===RC===" + str(rc))
print("===THREW===" + str(threw))
print("===OUT_START===")
print(buf.getvalue())
print("===OUT_END===")
'''

with io.open(seed_path2, "w", encoding="utf-8") as f:
    f.write(SEED_SCRIPT2)

try:
    result2 = subprocess.run([PY, "-u", seed_path2], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=60)
    out2 = result2.stdout
    if "===OUT_START===" not in out2:
        chk(False, "★★★ 라운드188 [3] 준비 스크립트 실행",
            f"exit={result2.returncode}\nSTDOUT:\n{out2}\nSTDERR:\n{result2.stderr}")
    else:
        rc2 = next((l for l in out2.splitlines() if l.startswith("===RC===")), "?")
        threw2 = next((l for l in out2.splitlines() if l.startswith("===THREW===")), "?")
        out2_body = out2.split("===OUT_START===", 1)[1].split("===OUT_END===", 1)[0]

        chk(threw2 == "===THREW===None",
            "★★★★ defects 쿼리가 실패해도 cmd_prune_personal 밖으로 예외가 안 새어나간다"
            "(고치기 전엔 처리 안 된 sqlite3.OperationalError 가 그대로 전파됐다)",
            f"{threw2}\n전체 출력:\n{out2_body}")
        chk(rc2 == "===RC===1",
            "★★★ 실패 시 종료코드 1을 명시적으로 돌려준다", rc2)
        chk("파기 실패" in out2_body,
            "★★★ 실패 사유가 형제 명령과 같은 방식(bad('파기 실패: ...'))으로 보고된다",
            f"전체 출력:\n{out2_body}")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드188 [3] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
