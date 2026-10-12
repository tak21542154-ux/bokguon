# -*- coding: utf-8 -*-
"""스캔 184라운드 회귀 — manage.py check(운영 전 필수 점검)의 "표식 없는 검증
사건"(ghost) 판정이 여전히 실패를 0건으로 감추던 결함 + 그걸 고치던 라운드183
자신의 판정식에도 있던 결함(부분 실패 시 이미 확인된 양수 합계까지 '확인
불가'로 깎여 배포를 막지 못함).

  demo_total(라운드183이 고친 것)과 ghost 는 **같은 최종 판정**(bad/ok/warn)에
  같이 들어가는데, ghost 쪽만 여전히 "실패하면 0건" 이었다 — 실측(운영DB):
  이 판정 뒤에 표식 없는 검증 사건 77건·정산 39건·1억 2,950만원이 지금
  그대로 있다. 게다가 demo_total 을 무조건 -1 로 덮는 방식은 부분 실패
  (예: 12개 표는 성공해 108건을 셌는데 1개만 실패)에서도 이미 확인된 108건을
  "확인 불가"(warn, 배포를 막지 않는다)로 깎아 버린다 — bad(fails+=1)여야
  할 상황이 그냥 통과된다.

      python test_scan_round184_fixes.py
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
print("  스캔 184라운드 회귀 — check 의 ghost 판정·부분실패 판정 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = SRC.index("def cmd_check(argv):")
i1 = SRC.index("\ndef ", i0 + 1)
body = SRC[i0:i1]
chk('_demo_dead.append("cases↔insurers(표식없는 검증사건)")' in body,
    "★★★ ghost 조회 실패도 _demo_dead 에 남는다(고치기 전엔 조용히 0건이 됐다)")
chk("elif not _demo_dead:\n            ok(\"데모 데이터 없음\")" in body,
    "★★★ '없음' 판정은 실패한 확인이 하나도 없을 때만 나온다")
chk("if demo_total > 0 or ghost:" in body,
    "확정 판정(bad)은 여전히 demo_total·ghost 실측값을 그대로 쓴다"
    "(부분 실패로 -1 에 덮이지 않는다)")
chk("demo_total = -1" not in body,
    "★★★ demo_total 을 무조건 -1 로 덮던 코드가 사라졌다"
    "(고치기 전엔 부분 실패도 이미 확인된 양수 합계를 지웠다)")

# ============================================================
print("\n[2] 실행 — 별도 프로세스로 시나리오별 검증(DB_PATH 는 import 시 고정됨)")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round184_")
PY = sys.executable


def run_scenario(db_path, setup_sql, break_marker=None):
    """setup_sql 을 실행한 뒤 cmd_check([]) 을 돌린다.
    break_marker 를 주면 스키마를 건드리지 않고, 그 부분문자열을 담은
    SQL 문 하나만 sqlite3.Connection.execute 를 감싸 실패시킨다 — 표를
    통째로 지우면(예: insurers) cmd_check 의 다른 무관한 점검(277행
    기본비밀번호 검사 등)까지 깨져 정작 보려는 지점에 못 간다."""
    patch = ""
    if break_marker:
        #  ⚠ sqlite3.Connection 은 C 로 구현된 불변 타입이라 메서드를 직접
        #    못 바꾼다 — DB.get_db() 가 돌려주는 실제 커넥션을 감싸는 얇은
        #    프록시로, execute() 만 가로채고 나머지는 전부 그대로 넘긴다.
        patch = (
            "import sqlite3\n"
            f"_MARK = {break_marker!r}\n"
            "class _Proxy:\n"
            "    def __init__(self, real):\n"
            "        self._real = real\n"
            "    def execute(self, sql, *a, **kw):\n"
            "        if _MARK in sql:\n"
            "            raise sqlite3.OperationalError('검증용 강제 실패')\n"
            "        return self._real.execute(sql, *a, **kw)\n"
            "    def __getattr__(self, name):\n"
            "        return getattr(self._real, name)\n"
            "_real_get_db = DB.get_db\n"
            "DB.get_db = lambda: _Proxy(_real_get_db())\n"
        )
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
        f"{patch}"
        "import manage as M\n"
        "buf = io.StringIO()\n"
        "with contextlib.redirect_stdout(buf):\n"
        "    rc = M.cmd_check([])\n"
        "print('RC=' + str(rc))\n"
        "print(buf.getvalue())\n"
    )
    r = subprocess.run([PY, "-u", "-c", script], capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    return r.stdout + r.stderr


# ── ① ghost 조회 자체만 실패(스키마는 그대로, execute 를 감싸 재현) +
#    나머지는 전부 정상(데모 데이터 실제로 0건) — '없음'이 아니라
#    '확인 불가'가 나와야 한다.
db1 = os.path.join(_tmpdir, "verify1.db")
out1 = run_scenario(db1, [], break_marker="insurer_id IN (SELECT id FROM insurers")
chk("데모 표식을 전부 확인하지 못했습니다" in out1,
    "★★★★ ghost 조회가 실패하면 '없음'이 아니라 '확인 불가'로 보고한다"
    "(고치기 전엔 조용히 0건 처리돼 '데모 데이터 없음'이 나왔다)",
    out1[:600])
chk("데모 데이터 없음" not in out1,
    "★★★★ 위와 동시에 거짓 초록('없음')도 나오지 않는다", out1[:600])

# ── ② demo_total 을 세는 15개 표 중 하나(field_agreements)만 조회가 실패해도,
#    다른 표(cases)에서 이미 확인된 합계가 양수(3건)면 여전히 '배포 불가'
#    (bad)로 정확히 확정돼야 한다 — 라운드183 자신의 판정식이 "하나라도
#    실패하면 무조건 demo_total=-1" 이라, 부분 실패에서도 이미 확인된
#    양수 합계를 "확인 불가"(warn, 배포를 막지 않는다)로 깎아 버렸다.
db2 = os.path.join(_tmpdir, "verify2.db")
out2 = run_scenario(db2, [
    "INSERT INTO cases(case_no,status,category,region,is_demo,created_at) "
    "VALUES('R184-D1','접수','가드레일','서울',1,datetime('now'))",
    "INSERT INTO cases(case_no,status,category,region,is_demo,created_at) "
    "VALUES('R184-D2','접수','가드레일','서울',1,datetime('now'))",
    "INSERT INTO cases(case_no,status,category,region,is_demo,created_at) "
    "VALUES('R184-D3','접수','가드레일','서울',1,datetime('now'))",
], break_marker="FROM field_agreements WHERE is_demo=1")
#  ⚠ RC 는 이 시나리오에서 신뢰할 수 없다 — 검증용 최소 DB엔 관리자 계정이
#    0개라 그 자체로도 fails 가 올라가 RC=1 이 나온다(내가 보려는 결함과
#    무관). "데모 데이터 3건" 확정 문구가 실제로 찍혔는지로 직접 본다.
chk("데모 데이터 3건(표식)" in out2,
    "★★★★ 표 하나(field_agreements)만 실패해도, 다른 표(cases)에서 이미"
    " 확인된 데모 데이터(3건)가 있으면 '배포 불가'로 정확히 확정된다"
    "(고치기 전엔 -1 로 덮여 이 확정 문구 자체가 안 찍혔다)",
    out2[:800])
chk("데모 표식을 전부 확인하지 못했습니다" not in out2,
    "★★★ 확정된 양수 합계는 '확인 불가' 경고로 깎이지 않는다", out2[:800])

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
