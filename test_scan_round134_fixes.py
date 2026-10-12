# -*- coding: utf-8 -*-
"""스캔 134라운드 회귀 — 133라운드와 같은 계열(여러 곳에 복붙된 상태전이
   로직 중 일부만 필드를 리셋 안 함)의 결함 2건.

  [1] api_case_cancel_award(낙찰 취소)가 co_extra(변경견적 추가분)를 안
      지운다 — 취소된 업체의 변경견적 금액이 그대로 남은 채 사건이
      재공고되어 전혀 다른 업체가 새로 낙찰되면, 정산 상세 화면이 그 옛
      추가분을 새 업체 계약의 일부인 것처럼 영구 표시한다.
  [2] api_case_undo_no_repair(미수선종결 되돌리기)가 dispatch_status 를 안
      지운다 — close_no_repair 가 남긴 '사진확보' 값이 그대로 남아, 이
      사건이 '출동수배_필요' 목록(WHERE dispatch_status='')에서 영구히
      빠진다. admin.js 의 '수배 개시' 버튼은 그 목록 안에만 있어 화면
      어디서도 되살릴 방법이 없다.

      python test_scan_round134_fixes.py
"""
import io
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 134라운드 회귀 — 낙찰취소 co_extra 누수 · 미수선되돌리기 dispatch_status 누수")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_ca = APP_SRC.index("def api_case_cancel_award(cid):")
i_ca_end = APP_SRC.index("\ndef ", i_ca + 1)
ca_body = APP_SRC[i_ca:i_ca_end]
ca_sql_i = ca_body.index("UPDATE cases")
ca_sql = ca_body[ca_sql_i:ca_body.index('"""', ca_sql_i)]
chk("co_extra=0" in ca_sql,
    "★★★ api_case_cancel_award: 낙찰취소 UPDATE 가 co_extra 를 0으로 리셋한다", ca_sql)

i_un = APP_SRC.index("def api_case_undo_no_repair(cid):")
i_un_end = APP_SRC.index("\ndef ", i_un + 1)
un_body = APP_SRC[i_un:i_un_end]
chk("dispatch_status=NULL" in un_body,
    "★★★ api_case_undo_no_repair: 되돌리기 UPDATE 가 dispatch_status 를 NULL로 리셋한다")

# ============================================================
print("\n[2] 실행 — 실제 UPDATE 문을 그대로 돌려 다운스트림(정산상세·수배목록)까지 확인")
# ------------------------------------------------------------


def _mkdb():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE cases(id INTEGER PRIMARY KEY, case_no TEXT, status TEXT, status_at TEXT,
                            partner_id INTEGER, partner_name TEXT, award_amount INTEGER,
                            awarded_at TEXT, award_route TEXT, co_extra INTEGER,
                            award_canceled_at TEXT, award_cancel_reason TEXT,
                            no_repair_reason TEXT, dispatch_status TEXT,
                            category TEXT, region TEXT, address TEXT, created_at TEXT,
                            is_demo INTEGER DEFAULT 0);
    """)
    return conn


try:
    #  ── 시나리오A: 변경견적으로 co_extra=50000 이 붙은 업체A가 낙찰취소된 뒤,
    #     사건이 재공고돼 업체B가 새로 낙찰된다 ──────────────────────────
    conn = _mkdb()
    conn.execute(
        "INSERT INTO cases(id,case_no,status,partner_id,partner_name,award_amount,co_extra) "
        "VALUES (70,'CANCEL-TEST','시공중',101,'업체A',350000,50000)")
    conn.commit()
    conn.execute(ca_sql, ("부도로 인한 낙찰 취소", 70))
    conn.commit()
    row = conn.execute("SELECT co_extra, partner_id, award_amount FROM cases WHERE id=70").fetchone()
    chk(row["co_extra"] == 0,
        "★★★ 낙찰취소 실행 후 co_extra가 0으로 지워진다(고치기 전엔 50000이 그대로 남았다)",
        dict(row))
    #  재공고 → 전혀 다른 업체B가 새로 낙찰(단순화된 UPDATE로 시뮬레이션)
    conn.execute("UPDATE cases SET partner_id=202, partner_name='업체B', award_amount=280000, "
                 "status='시공중' WHERE id=70")
    conn.commit()
    #  api_settlement_detail 이 실제로 읽는 것과 같은 SELECT
    srow = conn.execute("SELECT award_amount, co_extra FROM cases WHERE id=70").fetchone()
    chk(srow["co_extra"] == 0,
        "★★★ 업체B의 정산 상세 조회 시 co_extra가 0 — 취소된 업체A의 변경견적 추가분이 "
        "더는 새 낙찰업체 정산에 섞이지 않는다", dict(srow))
    conn.close()

    #  ── 시나리오B: close_no_repair 로 dispatch_status='사진확보' 가 붙은 사건을
    #     되돌린 뒤, '출동수배_필요' 목록에 실제로 다시 나타나는가 ──────────
    conn = _mkdb()
    conn.execute(
        "INSERT INTO cases(id,case_no,status,partner_id,dispatch_status,no_repair_reason,"
        "category,region,address,created_at) "
        "VALUES (80,'UNDO-TEST','미수선종결',NULL,'사진확보','현장 오선택',"
        "'가드레일','서울','서울 송파구',datetime('now','+9 hours'))")
    conn.commit()
    #  ⚠ 이 UPDATE 는 (api_case_cancel_award 와 달리) 삼중따옴표 한 덩어리가
    #    아니라 나란히 이어붙는 문자열 리터럴 3개다 — 원시 텍스트를 그대로
    #    자르면 중간에 닫는/여는 따옴표가 섞여 유효한 SQL이 안 된다. 여는
    #    따옴표부터 닫는 따옴표까지(파이썬 인접 리터럴 이어붙이기 문법 그대로)
    #    를 잘라 eval() 하면 파이썬이 정확히 이어붙여 준다(우리 소스 그대로).
    _end_anchor = 'AND partner_id IS NULL", (cid,))'
    un_sql_start = un_body.index('"UPDATE cases')
    un_sql_end = un_body.index(_end_anchor) + len('AND partner_id IS NULL"')
    un_sql = eval("(" + un_body[un_sql_start:un_sql_end] + ")")  # noqa: S307 -- 우리 소스 리터럴만 이어붙임
    conn.execute(un_sql, (80,))
    conn.commit()
    urow = conn.execute("SELECT status, dispatch_status, no_repair_reason FROM cases WHERE id=80").fetchone()
    chk(urow["dispatch_status"] is None,
        "★★★ 미수선종결 되돌리기 실행 후 dispatch_status가 NULL로 지워진다"
        "(고치기 전엔 '사진확보'가 그대로 남았다)", dict(urow))
    #  '출동수배_필요' 목록이 실제로 쓰는 것과 같은 WHERE 조건
    n_need = conn.execute(
        "SELECT COUNT(*) n FROM cases "
        " WHERE status='접수' AND COALESCE(dispatch_status,'')='' AND COALESCE(is_demo,0)=0"
    ).fetchone()["n"]
    chk(n_need == 1,
        "★★★ 되돌린 사건이 '출동수배_필요' 목록에 다시 나타난다"
        "(고치기 전엔 dispatch_status가 안 지워져 이 목록·수배개시 버튼 양쪽에서 영구히 빠졌다)",
        n_need)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드134 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
