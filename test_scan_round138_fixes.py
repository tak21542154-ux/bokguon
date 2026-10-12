# -*- coding: utf-8 -*-
"""스캔 138라운드 회귀 — cases.dispatch_status 리셋 누락 2곳(134라운드와
   같은 계열).

  [1] api_case_open_auction(2차 경매 개시)이 dispatch_status 를 안 지운다
      — 출동수배가 살아있는 도중(수배중/출동중) 2차 경매를 열면 그 값이
      영원히 남아, 이미 낙찰·시공·완료된 사건이 지도 화면(api_map_cases,
      WHERE dispatch_status='수배중')에 계속 "출동 수배중" amber 핀으로
      뜬다(실측 재현).
  [2] dispatch.settle_agreement(1차합의 승인)도 dispatch_status 를 안
      지운다 — arrive() 가 남긴 '사진확보'가 계약 성립 뒤에도 영구히
      남는다(현재는 이 값만 콕 집어 읽는 화면이 없어 잠재적이지만, "'접수'
      를 벗어나면 dispatch_status 를 지운다"는 이미 확립된 관례를 이
      경로만 어기고 있었다).

      python test_scan_round138_fixes.py
"""
import io
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("BOKGUON_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="round138_"), "verify.db"))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")
DP_SRC = read("dispatch.py")

print("=" * 72)
print("  스캔 138라운드 회귀 — 2차경매개시·1차합의승인이 dispatch_status 를 안 지우던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_oa = APP_SRC.index("def api_case_open_auction(")
i_oa_end = APP_SRC.index("\ndef ", i_oa + 1)
oa_body = APP_SRC[i_oa:i_oa_end]
chk("award_route='경매', dispatch_status=NULL" in oa_body,
    "★★★ api_case_open_auction 이 dispatch_status 를 NULL로 리셋한다")

i_sa = DP_SRC.index("def settle_agreement(conn, agreement_id, agreed, amount=0, note=\"\", actor=\"\",")
i_sa_end = DP_SRC.index("\ndef ", i_sa + 1)
sa_body = DP_SRC[i_sa:i_sa_end]
chk("dispatch_status=NULL" in sa_body,
    "★★★ settle_agreement 가 승인 시 dispatch_status 를 NULL로 리셋한다")

# ============================================================
print("\n[2] 실행 — api_case_open_auction 의 실제 UPDATE 문 재현")
# ------------------------------------------------------------
try:
    #  ⚠ 이 UPDATE 는 삼중따옴표 한 덩어리가 아니라 나란히 이어붙는 문자열
    #    리터럴 3개다(136라운드가 겪은 것과 같은 모양) — 여는 따옴표부터 닫는
    #    따옴표까지를 그대로 잘라 eval() 하면 파이썬이 정확히 이어붙여 준다.
    oa_anchor_start = '"UPDATE cases SET status=\'입찰중\''
    oa_anchor_end = "AND status='접수'\""
    oa_sql_start = oa_body.index(oa_anchor_start)
    oa_sql_end = oa_body.index(oa_anchor_end, oa_sql_start) + len(oa_anchor_end)
    oa_sql = eval("(" + oa_body[oa_sql_start:oa_sql_end] + ")")  # noqa: S307 -- 우리 소스 리터럴만 이어붙임
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE cases(id INTEGER PRIMARY KEY, status TEXT, status_at TEXT, "
                 "award_route TEXT, dispatch_status TEXT)")
    conn.execute("INSERT INTO cases(id,status,dispatch_status) VALUES (90,'접수','수배중')")
    conn.commit()
    conn.execute(oa_sql, (90,))
    conn.commit()
    row = conn.execute("SELECT status, dispatch_status FROM cases WHERE id=90").fetchone()
    chk(row["dispatch_status"] is None,
        "★★★ 2차경매 개시 실행 후 dispatch_status가 NULL로 지워진다"
        "(고치기 전엔 '수배중'이 그대로 남아 지도에 영구 표시됐다)", dict(row))
    #  api_map_cases 가 실제로 쓰는 것과 같은 필터
    n_map = conn.execute("SELECT COUNT(*) n FROM cases WHERE dispatch_status='수배중'").fetchone()["n"]
    chk(n_map == 0, "★★★ 지도의 '수배중' 필터에 더는 안 걸린다", n_map)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드138 준비/실행(open-auction SQL 재현)", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — 실제 dispatch.py 함수 체인(수배→수락→도착→합의승인)으로 재현")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round138_exec_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
try:
    import db as DB
    DB.init_db()
    conn = DB.get_db()
    import dispatch as DP

    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,phone,login_id) "
        "VALUES('업체138','시공사','활성','가드레일','서울','01000000000','p138')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R138-TEST','접수','가드레일','서울',0)").lastrowid
    did = conn.execute(
        "INSERT INTO dispatches(case_id,status,created_at) VALUES(?,?,datetime('now','+9 hours'))",
        (cid, DP.ST_OPEN)).lastrowid
    conn.execute("INSERT INTO dispatch_calls(dispatch_id,partner_id) VALUES(?,?)", (did, pid))
    conn.commit()

    ok_c, _, _ = DP.claim(conn, did, pid, "업체138")
    chk(ok_c is True, "★ (사전조건) 수배 수락 성공")
    ok_a, _ = DP.arrive(conn, did, pid, 3, field_estimate=850000)
    chk(ok_a is True, "★ (사전조건) 도착 보고 성공")
    row_mid = conn.execute("SELECT dispatch_status FROM cases WHERE id=?", (cid,)).fetchone()
    chk(row_mid["dispatch_status"] == DP.CS_PHOTO,
        "★ (사전조건) 도착 직후 dispatch_status='사진확보'", dict(row_mid))

    aid = DP.open_agreement(conn, cid, dispatch_id=did, our_staff="검증", insurer_staff="검증보험")
    chk(aid is not None, "★ (사전조건) 1차합의 검토 개설 성공")
    ok_s, msg_s = DP.settle_agreement(
        conn, aid, True, amount=850000, note="",
        approver={"org_id": 1, "user_id": 1, "name": "검증보험담당", "role": "중간관리자"})
    chk(ok_s is True, "★ (사전조건) 1차합의 승인 성공", msg_s)

    row_after = conn.execute(
        "SELECT status, dispatch_status, partner_id, award_route FROM cases WHERE id=?", (cid,)).fetchone()
    chk(row_after["status"] == "시공중" and row_after["partner_id"] == pid
        and row_after["award_route"] == "1차합의",
        "★ (사전조건) 승인 후 사건이 정상적으로 시공중·낙찰업체·경로로 확정된다", dict(row_after))
    chk(row_after["dispatch_status"] is None,
        "★★★ 1차합의 승인 후 dispatch_status가 NULL로 지워진다"
        "(고치기 전엔 '사진확보'가 계약 성립 뒤에도 영구히 남았다)", dict(row_after))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드138 준비/실행(settle_agreement 함수체인 재현)", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
