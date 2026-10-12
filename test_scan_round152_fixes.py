# -*- coding: utf-8 -*-
"""스캔 152라운드 회귀 — cases.first_partner_id/first_photo_at("최초 출동업체
— 1차 합의 상대이자 결렬 시에도 사진 제공자로 남는 기록", arrive() 자신의
주석)가 재수배로 조용히 덮어써지던 결함.

  open_dispatch() 의 중복출동 방지 가드는 dispatches.status IN (모집중,수배됨)
  만 보고, arrive() 로 이미 '도착'(사진확보)이 된 이전 회차는 안 본다 —
  status='접수'·partner_id=NULL 인 채로 1차 합의가 검토 중이거나 방금
  부동의로 끝나 2차 경매를 열기 전인 좁은 틈에서, 새 수배가 열려 다른 업체가
  claim+arrive 하면 최초 출동업체 식별자가 나중 업체로 바뀐다 — field_agreements
  는 여전히 원래 업체를 가리켜, 사건의 '최초 출동업체'와 '실제 1차합의 상대'가
  서로 다른 업체를 가리키게 된다. cases.dispatch_status='사진확보'(CS_PHOTO)일
  때는 재수배를 막도록 가드를 넓혔다.

      python test_scan_round152_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


DP_SRC = read("dispatch.py")

print("=" * 72)
print("  스캔 152라운드 회귀 — 최초 출동업체(first_partner_id)가 재수배로 덮어써지던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_od = DP_SRC.index("def open_dispatch(")
i_od_end = DP_SRC.index("\ndef ", i_od + 1)
od_body = DP_SRC[i_od:i_od_end]
chk("cs[3] == CS_PHOTO" in od_body,
    "★★★ open_dispatch 가 dispatch_status=CS_PHOTO(사진확보) 인 사건의 재수배를 막는다")
chk('"SELECT status, partner_id, case_no, dispatch_status FROM cases WHERE id=?"' in od_body,
    "★ 그 판정에 필요한 dispatch_status 컬럼을 함께 조회한다")

# ============================================================
print("\n[2] 실행 — 실제 함수체인(1회차 도착→1차합의 검토중→2회차 재수배 시도)")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round152_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import dispatch as DP

    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name, login_id, status) VALUES('R152보험','r152ins','활성')").lastrowid
    pa = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,login_id,phone) "
        "VALUES('R152-A','시공사','활성','가드레일','서울','r152a','01011110001')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,insurer_id,insurer,category,region,address,"
        "                  est_price,low_price,status,intake_type,created_at,is_demo) "
        "VALUES('R152-CASE',?,?,?,?,?,0,0,'접수','사진없음',?,0)",
        (iid, "R152보험", "가드레일", "서울", "검증용 주소", DB.now())).lastrowid
    conn.commit()

    # ── 1회차: A가 수배를 잡고 도착(사진 확보) → 1차 합의 검토중 ──
    did1, cnt1, _ = DP.open_dispatch(conn, cid)
    conn.commit()
    chk(did1 and cnt1 == 1, "★ (사전조건) 1회차 수배가 열리고 A가 후보로 불린다", (did1, cnt1))
    ok_c, _, _ = DP.claim(conn, did1, pa, "R152-A")
    ok_a, _ = DP.arrive(conn, did1, pa, photo_count=2, field_estimate=800000)
    conn.commit()
    chk(ok_c is True and ok_a is True, "★ (사전조건) A가 수락·도착에 성공한다", (ok_c, ok_a))

    row1 = dict(conn.execute(
        "SELECT dispatch_status, first_partner_id FROM cases WHERE id=?", (cid,)).fetchone())
    chk(row1["dispatch_status"] == "사진확보" and row1["first_partner_id"] == pa,
        "★ (사전조건) 최초 출동업체가 A로 기록되고 dispatch_status='사진확보'다", row1)

    aid = DP.open_agreement(conn, cid, dispatch_id=did1, our_staff="검증", insurer_staff="검증보험")
    conn.commit()
    chk(aid is not None, "★ (사전조건) 1차 합의 검토가 A 명의로 열린다(아직 보험사 승인 전)")

    pb = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,login_id,phone) "
        "VALUES('R152-B','시공사','활성','가드레일','서울','r152b','01011110002')").lastrowid
    conn.commit()

    # ── 2회차: 사건은 여전히 '접수'/미배정이지만, 이미 사진을 확보했다 ──
    did2, cnt2, _ = DP.open_dispatch(conn, cid)
    conn.commit()
    chk(did2 == 0 and cnt2 == 0,
        "★★★ 이미 사진을 확보(1차합의 검토중)한 사건은 재수배가 열리지 않는다"
        "(고치기 전엔 여기서 새 수배가 열려 B가 후보로 불렸다)", (did2, cnt2))

    row2 = dict(conn.execute(
        "SELECT dispatch_status, first_partner_id FROM cases WHERE id=?", (cid,)).fetchone())
    chk(row2["first_partner_id"] == pa,
        "★★★ 최초 출동업체 식별자가 A로 그대로 보존된다"
        "(고치기 전엔 재수배로 B가 도착하면 이 값이 B로 조용히 덮어써졌다)", row2)

    fa_after = dict(conn.execute(
        "SELECT partner_id, status FROM field_agreements WHERE id=?", (aid,)).fetchone())
    chk(fa_after["partner_id"] == pa and fa_after["status"] == DP.AG_REVIEW,
        "★ 1차 합의 검토 건도 그대로 A를 가리키며 검토중 상태를 유지한다(부수 피해 없음)",
        fa_after)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드152 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
