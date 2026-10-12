# -*- coding: utf-8 -*-
"""스캔 312라운드 회귀 — seed_boq.py 가 관리자의 '비활성' 결정을 흔적 없이 되돌리던 결함.

  왜 필요한가 — app.py 의 api_boq_delete 는 표준단가 항목을 비활성(active=0)하며
  boq_price_history 에 '비활성' 이력을 남긴다("과거 견적 근거는 보존"이 그 라우트
  자신의 약속이다). 그런데 seed_boq.py(seed_boq_led.py 가 공유하는 load())를
  재실행하면 같은 (공종·항목·규격) 행을 찾아 조건 없이 active=1 로 되돌리면서도,
  가격이 그대로면 이력을 전혀 남기지 않았다 — 관리자가 콘솔에서 내린 결정이
  다음 스크립트 재실행 한 번에 아무 흔적 없이 뒤집힌 것이다(312라운드, 정밀조사
  Agent 가 발견). PATCH 수정 라우트(api_boq_update)는 active 를 되돌릴 방법이
  아예 없어, 이 스크립트가 사실상 유일한 되살리기 통로다 — 그래서 되살리기
  자체는 막지 않되, '수정'과 구분되는 '재활성' 이력을 반드시 남기도록 고쳤다.

  이 테스트는 실제 seed_boq.load() 를 격리 스크래치 DB 에서 두 번 실제로 실행하고,
  그 사이 app.py 의 api_boq_delete 와 정확히 같은 SQL 로 비활성 처리한다.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_scratch = tempfile.mkdtemp(prefix="bokguon_r312_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_scratch, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"

import db as DB          # noqa: E402  (BOKGUON_DB_PATH 를 먼저 정한 뒤에 import)
import seed_boq as SB    # noqa: E402

PASS = FAIL = 0
FAILED = []


def chk(cond, msg, detail=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {msg}")
    else:
        FAIL += 1
        FAILED.append(msg)
        print(f"  [FAIL] {msg}" + (f"   {detail}" if detail else ""))


TEST_ROW = ("__테스트312__", "테스트항목", "규격A", "개", 10000, "312라운드 회귀테스트 근거", "2026-09")

print("=" * 74)
print("  스캔 312라운드 회귀 — seed_boq.py 비활성 항목 무흔적 부활")
print("=" * 74)

print("\n[1] 준비 — 격리 스크래치 DB 생성 후 1차 적재")
DB.init_db(seed_demo=False)
added1, _, _ = SB.load([TEST_ROW], dry=False, deactivate_demo=False)
chk(added1 == 1, "1차 적재(신규 추가) 성공")

conn = DB.get_db()
row = conn.execute(
    "SELECT id, active, ref_price FROM standard_boq WHERE major=? AND item=? AND spec=?",
    (TEST_ROW[0], TEST_ROW[1], TEST_ROW[2])).fetchone()
conn.close()
chk(row is not None and row["active"] == 1, "1차 적재 직후 active=1")
bid = row["id"] if row else None

print("\n[2] 실행 — app.py api_boq_delete 와 정확히 같은 SQL 로 비활성 처리(관리자의 결정)")
conn = DB.get_db()
conn.execute("UPDATE standard_boq SET active=0, updated_at=? WHERE id=?", (DB.now(), bid))
DB.boq_history(conn, bid, dict(row), action="비활성", old_price=row["ref_price"], actor="admin")
conn.commit()
conn.close()

conn = DB.get_db()
hist_after_deactivate = [h["action"] for h in conn.execute(
    "SELECT action FROM boq_price_history WHERE boq_id=? ORDER BY id", (bid,)).fetchall()]
conn.close()
chk(hist_after_deactivate == ["추가", "비활성"],
    "비활성 처리 직후 이력이 '추가'→'비활성' 2건", hist_after_deactivate)

print("\n[3] 실행 — 가격 변경 없이 seed_boq.py 재실행(운영에서 실제로 반복되는 패턴)")
added2, _, _ = SB.load([TEST_ROW], dry=False, deactivate_demo=False)
chk(added2 == 1, "2차 적재(재실행) 자체는 성공")

conn = DB.get_db()
row2 = conn.execute("SELECT active FROM standard_boq WHERE id=?", (bid,)).fetchone()
hist_after_reload = [h["action"] for h in conn.execute(
    "SELECT action FROM boq_price_history WHERE boq_id=? ORDER BY id", (bid,)).fetchall()]
conn.close()

chk(row2["active"] == 1,
    "재실행 뒤 active 가 다시 1로 돌아온다(되살리기 자체는 유일한 되돌리기 수단이라 유지)")
chk(hist_after_reload == ["추가", "비활성", "재활성"],
    "★★★★★ 재실행이 관리자의 비활성 결정을 뒤집은 사실이 '재활성' 이력으로 반드시 남는다"
    "(고치기 전엔 가격이 안 바뀌면 이력이 전혀 안 남아 '추가'·'비활성' 2건에서 멈췄다)",
    hist_after_reload)

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
