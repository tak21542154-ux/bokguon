# -*- coding: utf-8 -*-
"""스캔 183라운드 회귀 — manage.py check(운영 전 필수 점검)의 데모 데이터
잔존 판정이 죽은 코드였던 결함.

  바깥 try 는 안쪽 try 가 sqlite3.Error 를 전부 먼저 삼켜 버려 영원히
  실행되지 않는 죽은 코드였다 — 13개 표 중 하나라도(예: 마이그레이션 전
  DB) is_demo 컬럼이 없으면, "확인 불가"를 뜻하는 demo_total=-1 대신
  초기값 0 이 그대로 남아 "데모 데이터 없음"이라는 거짓 초록을 냈다.
  go-live 를 막아야 할 게이트가 정반대로 통과시킨 셈이다. 부수적으로
  happy_calls·schedule_events(116·122라운드에서 자기 is_demo 를 갖게
  됐다)도 이 점검 목록에서 아예 빠져 있었다.

      python test_scan_round183_fixes.py
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


SRC = read("manage.py")

print("=" * 72)
print("  스캔 183라운드 회귀 — check 의 데모잔존 판정이 죽은 코드였던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = SRC.index("def cmd_check(argv):")
i1 = SRC.index("\ndef ", i0 + 1)
body = SRC[i0:i1]
chk('"happy_calls", "schedule_events"' in body,
    "★★★ happy_calls·schedule_events 도 점검 목록에 들어갔다")
#  ⚠ [라운드184 collateral] "실패하면 무조건 demo_total=-1" 은 부분 실패에서도
#    이미 확인된 양수 합계를 지우는 결함이 있어 184라운드가 없앴다(demo_total
#    은 이제 끝까지 실측 합계로 남고, "확인 불가" 판정은 _demo_dead 유무로만
#    따로 본다) — 이 파일은 "실패한 표가 실제로 _demo_dead 에 남는가"만 본다.
chk("_demo_dead.append(t)" in body,
    "★★★ 실패한 표를 실제로 모아서(_demo_dead) '확인 불가' 판정에 쓴다"
    "(고치기 전엔 바깥 except 가 죽은 코드라 이 판정이 실행된 적이 없었다)")

# ============================================================
print("\n[2] 실행 — DB_PATH 는 db.py 모듈 import 시점에 고정되므로, 시나리오별로")
print("     별도 프로세스(별도 DB 파일)로 나눠 검증한다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round183_")
PY = sys.executable


def run_scenario(db_path, setup_sql):
    """별도 프로세스에서 DB.init_db() → setup_sql 실행 → cmd_check([]) 출력을 돌려준다."""
    script = (
        "import os, sys, io, contextlib\n"
        f"os.environ['BOKGUON_DB_PATH'] = {db_path!r}\n"
        "os.environ['BOKGUON_ENV'] = 'dev'\n"
        "os.environ['BOKGUON_SEED_DEMO'] = '0'\n"
        f"sys.path.insert(0, {HERE!r})\n"
        "import db as DB\n"
        "DB.init_db()\n"
        "conn = DB.get_db()\n"
        f"for _stmt in {setup_sql!r}:\n"
        "    conn.execute(_stmt)\n"
        "conn.commit(); conn.close()\n"
        "import manage as M\n"
        "buf = io.StringIO()\n"
        "with contextlib.redirect_stdout(buf):\n"
        "    M.cmd_check([])\n"
        "print(buf.getvalue())\n"
    )
    r = subprocess.run([PY, "-u", "-c", script], capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    return r.stdout + r.stderr


# ── ① 정상 스키마 + happy_calls·schedule_events 에만 데모 데이터 ──
#    (그 외 표는 전부 실제 0건) — 예전엔 이 두 표를 점검하지 않아 항상
#    '없음'으로 나왔다.
db1 = os.path.join(_tmpdir, "verify1.db")
out1 = run_scenario(db1, [
    "INSERT INTO insurers(name,status,login_id,created_at) "
    "VALUES('R183보험사','활성','r183i',datetime('now'))",
    "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo,created_at) "
    "VALUES('R183-CASE','접수','가드레일','서울',1,0,datetime('now'))",
    "INSERT INTO happy_calls(case_id,is_demo,created_at) VALUES(1,1,datetime('now'))",
    "INSERT INTO schedule_events(case_id,is_demo,created_at) VALUES(1,1,datetime('now'))",
])
chk("데모 데이터 없음" not in out1,
    "★★★ happy_calls·schedule_events 의 데모 데이터가 실제로 잡혀"
    "'없음'으로 잘못 보고되지 않는다(고치기 전엔 이 둘을 아예 안 봤다)",
    out1[:400])

# ── ② 표 하나(field_agreements)만 is_demo 컬럼을 없애 마이그레이션
#    이전 스키마를 흉내낸다 — 다른 표는 전부 정상(데모 데이터 0건).
db2 = os.path.join(_tmpdir, "verify2.db")
out2 = run_scenario(db2, ["ALTER TABLE field_agreements DROP COLUMN is_demo"])
#  ⚠ [라운드184 collateral] 경고 문구가 "표식 컬럼이 없습니다"(스키마 누락
#    전용)에서 "확인하지 못했습니다"(스키마 누락 + 일시적 오류 공용)로
#    바뀌었다 — 184라운드가 같은 판정에 들어가는 ghost 쪽도 실패를 여기로
#    합류시키며 문구를 두 원인 다 아우르게 고쳤다.
chk("데모 표식을 전부 확인하지 못했습니다" in out2,
    "★★★★ 표 하나만 컬럼이 없어도 '데모 데이터 없음'이 아니라 "
    "'확인 불가(마이그레이션 필요)'로 정확히 보고한다"
    "(고치기 전엔 바깥 except 가 죽은 코드라 조용히 '없음'으로 나왔다)",
    out2[:500])
chk("데모 데이터 없음" not in out2,
    "★★★★ 위와 동시에 거짓 초록('없음')도 더는 나오지 않는다", out2[:500])

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
