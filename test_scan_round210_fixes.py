# -*- coding: utf-8 -*-
"""스캔 210라운드 회귀 — go-live 의 하위계정(portal_users) 정리(209라운드 신설)가
보험사 쪽에서만 실행 순서 때문에 조용히 무력화되던 결함.

  cmd_go_live 는 세 단계로 돈다: ①데모 사건 자식행 정리 → ②DEMO_TABLES(cases·
  settlements·defects·**insurers**·... — db.py:1273) 일괄 is_demo=1 삭제 →
  ③데모 계정(DEMO_ACCOUNTS) 정리. 209라운드가 ③에 추가한 하위계정 삭제는
  "SELECT id FROM insurers WHERE login_id='insurer'" 서브쿼리로 조직을
  다시 찾았는데, **insurers 는 ②에도 들어 있어** 그 행이 is_demo=1 이면(실측:
  운영DB 의 데모 보험사 6곳 전부 그렇다) ②단계에서 이미 통째로 삭제된 뒤다 —
  ③의 서브쿼리는 매번 0건이라 209라운드가 고친 하위계정 정리가 보험사에서만
  조용히 무력화됐다(협력사는 DEMO_TABLES 에 없어 문제없었다 — 그래서 209라운드
  자신의 재현으로는 이 결함이 드러나지 않았다).

  조직 id를 트랜잭션 맨 앞(② 이전)에서 미리 잡아 두고, ③은 그 id 를 직접
  쓰도록 고쳤다 — ②가 나중에 그 행을 지우든 말든 하위계정 정리는 항상
  올바른 조직을 겨눈다.

  이 결함의 전체 재현(실제 go-live --yes 서브프로세스 실행, is_demo=1 보험사
  + 하위계정)은 test_scan_round209_fixes.py 에 있다 — 이 파일은 이 라운드가
  고친 부분(조기 id 확보와 그 사용 순서)만 소스 수준으로 집중 검증한다.

      python test_scan_round210_fixes.py
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


MANAGE_SRC = read("manage.py")

print("=" * 72)
print("  스캔 210라운드 회귀 — go-live 하위계정 정리가 보험사에서만 무력화되던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = MANAGE_SRC.index("def cmd_go_live(argv):")
i1 = MANAGE_SRC.index("\ndef ", i0 + 1)
body = MANAGE_SRC[i0:i1]

DB_SRC = read("db.py")
_demo_tables_literal = DB_SRC.split("DEMO_TABLES = [", 1)[1].split("]", 1)[0]
chk('"insurers"' in _demo_tables_literal,
    "★ (사전조건) insurers 가 실제로 db.py 의 DEMO_TABLES 에 포함돼 있다"
    "(그래서 ②단계 일괄삭제 대상이 된다 — 이 조건이 있어야 아래 버그가 성립)")
chk("for t in DB.DEMO_TABLES:" in body,
    "★ (사전조건) go-live ②단계가 그 DEMO_TABLES 를 그대로 순회하며 지운다")

chk("_demo_org_ids = {}" in body,
    "★★★★★ 핵심 — 조직 id 를 담을 사전이 신설됐다")
_i_capture = body.find("_demo_org_ids = {}")
_i_bulk = body.find("for t in DB.DEMO_TABLES:")
_i_use = body.find("DELETE FROM portal_users WHERE org_type=? AND org_id=?")
chk(_i_capture != -1 and _i_bulk != -1 and _i_use != -1,
    "★★★ 세 지점(id 확보·②단계 일괄삭제·하위계정 삭제)이 모두 존재한다",
    (_i_capture, _i_bulk, _i_use))
if _i_capture != -1 and _i_bulk != -1 and _i_use != -1:
    chk(_i_capture < _i_bulk,
        "★★★★★ 핵심 — id 확보가 ②단계(DEMO_TABLES 일괄삭제)보다 앞선다"
        "(고치기 전엔 이 확보 코드 자체가 없어, insurers 행이 ②에서 먼저 "
        "지워지면 login_id 재조회가 항상 0건이었다)")
    chk(_i_bulk < _i_use,
        "★ ②단계가 먼저 돌고, 그 다음(순서상) 하위계정 삭제가 미리 확보한 "
        "id 를 쓴다")

chk('_row = conn.execute(f"SELECT id FROM {_table} WHERE {_col}=?", (_nm,)).fetchone()' in body,
    "★★★ id 확보가 org별 login_id 로 정확히 조회한다")
chk('_oid = _demo_org_ids.get((table, nm))' in body,
    "★★★★ ③단계가 (더 이상 서브쿼리가 아니라) 미리 확보한 id 를 직접 쓴다")

print("\n  (전체 실행 재현 — is_demo=1 보험사 + 하위계정으로 실제 go-live --yes 를 "
      "돌려 하위계정이 지워지는지까지 검증하는 통합 테스트는 "
      "test_scan_round209_fixes.py 에 있다.)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
