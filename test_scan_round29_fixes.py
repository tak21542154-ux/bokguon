# -*- coding: utf-8 -*-
"""스캔 29라운드 회귀 — 1차 합의 부동의 뒤 재상신이 막히지 않던 결함.

  보험사가 1차 합의를 부동의(결렬)하면 settle_agreement 는 사건을 2차 경매
  경로로 돌린다(award_route='경매', dispatch.py 주석: "결렬 — 2차 경매로
  간다"). 그런데 수배(dispatch) 자체는 여전히 '도착' 상태로 남아, 화면의
  '발주처에 승인 요청' 버튼이 사라지지 않는다(admin.js:4326, v.status==='도착'
  조건만 봄 — 이전 합의의 결렬 여부는 안 봄). 운영자가 그 버튼을 다시 누르면
  기존 검증 코드는 "검토중(AG_REVIEW)" 인 합의만 중복 방지했지, "결렬
  (AG_BROKEN)" 로 끝난 합의는 걸러내지 않아 같은 사건에 새 1차 합의가 또
  열렸다 — 반려 이력은 화면(보험사 승인 대기 화면은 최신 1건만 봄)에서
  사라진 채로, 2차 경매와 재상신된 1차 합의가 같은 사건을 놓고 동시에
  돈다.

  고친 방향 — open_agreement 에 '이미 결렬된 합의가 있으면 막는다' 가드를
  하나 더 추가했다(사건 상태 가드와 같은 원칙: 한쪽 문이 닫히면 안 열어
  준다). 라우트에는 정확한 사유("2차 경매로 진행하라")를 안내한다.

      python test_scan_round29_fixes.py
"""
import io
import os
import secrets
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


sys.path.insert(0, HERE)
import db as DB                                                   # noqa: E402
import dispatch as DP                                             # noqa: E402

APP = read("app.py")
DSP = read("dispatch.py")

print("═" * 72)
print("  스캔 29라운드 회귀 — 1차 합의 부동의 뒤 재상신 차단")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 결렬 가드가 실제로 있는가")
# ──────────────────────────────────────────────────────────────
_i_oa = DSP.find("def open_agreement(")
_j_oa = DSP.find("\ndef settle_agreement(")
OA_SRC = DSP[_i_oa:_j_oa] if 0 <= _i_oa < _j_oa else ""
chk(bool(OA_SRC.strip()), "open_agreement 함수를 찾았다")
_dedup_queries = OA_SRC.count("FROM field_agreements WHERE case_id=? AND status=?")
chk("AG_BROKEN" in OA_SRC and _dedup_queries >= 2,
    "★★★ 결렬(AG_BROKEN) 이력이 있으면 재상신을 막는 가드를 찾았다(검토중 가드와 별도로)",
    f"AG_BROKEN 참조={'AG_BROKEN' in OA_SRC} · 같은 모양 조회 수={_dedup_queries}(2 이상이어야 함)")

_i_route = APP.find("def api_field_agreement_open(cid):")
_j_route = APP.find("\n@app.", _i_route)
ROUTE_SRC = APP[_i_route:_j_route] if 0 <= _i_route < _j_route else ""
chk(bool(ROUTE_SRC.strip()), "api_field_agreement_open 라우트를 찾았다")
chk('DP.AG_BROKEN' in ROUTE_SRC, "★★ 라우트가 그 결렬 상태를 실제로 조회한다")
#  ⚠ 오류 메시지는 파이썬 인접 문자열 리터럴로 줄바꿈돼 있다("...2차 경매로 " +
#    "진행해 주세요.") — 소스 원문에는 두 리터럴 사이에 따옴표가 그대로 남으므로
#    공백만 지우는 정규화로는 안 이어진다. 두 조각을 따로 확인한다.
chk("2차 경매로" in ROUTE_SRC and "진행해 주세요" in ROUTE_SRC,
    "★ 정확한 다음 행동(2차 경매)을 안내하는 오류 메시지가 있다", ROUTE_SRC[-400:])

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 부동의 뒤 재상신이 실제로 막히는가")
# ──────────────────────────────────────────────────────────────
MARK = "R29" + secrets.token_hex(3)


def mkcase(conn):
    iid = conn.execute("SELECT id FROM insurers LIMIT 1").fetchone()["id"]
    cur = conn.execute(
        """INSERT INTO cases(case_no,insurer_id,insurer,category,region,address,
                             est_price,low_price,status,intake_type,created_at,is_demo)
           VALUES(?,?,?,?,?,?,0,0,'접수','사진있음',?,1)""",
        (f"{MARK}-{secrets.token_hex(2)}", iid, "검증보험", "누수·배관·설비",
         "서울 송파구", "검증용 주소", DB.now()))
    conn.commit()
    return cur.lastrowid


def mkarrived(conn, cid, partner_name, field_estimate):
    cur = conn.execute(
        """INSERT INTO dispatches(case_id, round, status, claimed_partner_id, claimed_name,
                                  field_estimate, created_at, is_demo)
           VALUES(?,1,?,999999,?,?,?,1)""",
        (cid, DP.ST_ARRIVED, partner_name, field_estimate, DB.now()))
    conn.commit()
    return cur.lastrowid


def cleanup(conn):
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM cases WHERE case_no LIKE ?", (MARK + "%",))]
    for cid in ids:
        conn.execute("DELETE FROM notifications WHERE case_id=?", (cid,))
        conn.execute("DELETE FROM field_agreements WHERE case_id=?", (cid,))
        conn.execute("DELETE FROM dispatches WHERE case_id=?", (cid,))
        conn.execute("DELETE FROM cases WHERE id=?", (cid,))
    conn.commit()


conn = DB.get_db()
cleanup(conn)
try:
    cid = mkcase(conn)
    mkarrived(conn, cid, f"{MARK}-업체", 1_000_000)

    aid1 = DP.open_agreement(conn, cid, our_staff="검증")
    chk(bool(aid1), "★ 1차 합의(승인 요청) 최초 개시 — 정상 성공", aid1)

    ok, msg = DP.settle_agreement(conn, aid1, agreed=False, note="가격 안 맞음(검증)",
                                   actor="검증")
    chk(ok, "★ 부동의(결렬) 기록 — 정상 성공", msg)

    row = conn.execute("SELECT award_route FROM cases WHERE id=?", (cid,)).fetchone()
    chk(row["award_route"] == "경매", "★ 부동의 후 사건이 2차 경매 경로로 표시된다", row["award_route"])

    aid2 = DP.open_agreement(conn, cid, our_staff="검증(재시도)")
    chk(aid2 is None,
        "★★★ 같은 사건에 1차 합의 재상신 시도 — 이제는 막힌다(결함 재현·수정 확인)",
        f"돌아온 값={aid2}")

    n_rows = conn.execute(
        "SELECT COUNT(*) FROM field_agreements WHERE case_id=?", (cid,)).fetchone()[0]
    chk(n_rows == 1, "★★★ field_agreements 행이 여전히 1건뿐이다(중복 생성 안 됨)", n_rows)

    #  ⚠ 회귀 방지 — 결렬 이력이 없는 새 사건은 정상적으로 1차 합의를 열 수 있어야 한다
    cid2 = mkcase(conn)
    mkarrived(conn, cid2, f"{MARK}-업체2", 500_000)
    aid3 = DP.open_agreement(conn, cid2, our_staff="검증")
    chk(bool(aid3), "★ 결렬 이력이 없는 새 사건은 그대로 정상 개시된다(과잉 차단 아님)", aid3)

finally:
    cleanup(conn)
    conn.close()

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
