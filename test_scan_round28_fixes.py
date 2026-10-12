# -*- coding: utf-8 -*-
"""스캔 28라운드 회귀 — 직접배정이 밀어낸 수배에 통지가 없던 결함.

  운영자가 이미 수락(ST_CLAIMED)된 수배를 되묻고 직접배정(assign_dispatch,
  supersede=True)으로 덮어쓰면, 밀려난 협력사에게 아무 통지도 없었다 — 현장
  으로 가고 있는데 도착해서야 취소를 안다.

  같은 코드베이스에 이미 두 번 고쳐진 형제 버그의 **세 번째 사례**였다:
    · 발주처 취소            → close_live_dispatches (app.py)
    · 2차 경매 개시·낙찰 확정  → 위와 같은 관문을 통과
    · 직접배정(supersede)     → 이번까지 그 관문을 안 거쳤다
  test_dispatch.py 에 supersede 테스트가 0건이라 회귀망도 없었다(실측 확인).

  고친 방향 — on_supersede 콜백을 assign_dispatch 에 추가해, 커밋 뒤
  (open_dispatch 와 같은 원칙: 통지는 트랜잭션 밖에서) 밀려난 협력사에게
  '출동취소' 알림을 보낸다.

      python test_scan_round28_fixes.py
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
print("  스캔 28라운드 회귀 — 직접배정이 밀어낸 수배 무통지")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 콜백 배선이 실제로 있는가")
# ──────────────────────────────────────────────────────────────
chk("def assign_dispatch(conn, case_id, partner_id, reason, by=\"\", supersede=False, "
    "on_supersede=None):" in DSP,
    "★ assign_dispatch 가 on_supersede 콜백을 받는다")
chk("live[\"claimed_partner_id\"] and on_supersede" in DSP,
    "★★ 밀려난 쪽에 협력사가 있을 때만(빈 자리를 덮어쓴 경우는 제외) 부른다")
chk("def _dispatch_supersede_notify(conn):" in APP, "★★ app.py 에 통지 콜백 팩토리가 있다")
chk('notify(conn, "출동취소"' in APP, "★ 취소 통지가 실제 notify() 를 부른다")
chk("on_supersede=_dispatch_supersede_notify(conn)" in APP,
    "★★★ 직접배정 라우트가 실제로 그 콜백을 연결한다",
    "연결이 없으면 함수만 있고 안 먹는다 — 형제 버그(발주처 취소)가 이 모양으로 두 번 났다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 밀려난 협력사가 실제로 통지 대상이 되는가")
# ──────────────────────────────────────────────────────────────
MARK = "R28" + secrets.token_hex(3)


def mkcase(conn):
    iid = conn.execute("SELECT id FROM insurers LIMIT 1").fetchone()["id"]
    cur = conn.execute(
        """INSERT INTO cases(case_no,insurer_id,insurer,category,region,address,
                             est_price,low_price,status,intake_type,created_at,is_demo)
           VALUES(?,?,?,?,?,?,0,0,'접수','사진없음',?,1)""",
        (f"{MARK}-{secrets.token_hex(2)}", iid, "검증보험", "가드레일·방호울타리",
         "서울 송파구", "검증용 주소", DB.now()))
    conn.commit()
    return cur.lastrowid


def mkpartner(conn, name):
    cur = conn.execute(
        "INSERT INTO partners(name,partner_type,major,region,status) "
        "VALUES(?,'시행사','가드레일·방호울타리','서울 송파구','활성')", (name,))
    conn.commit()
    return cur.lastrowid


def cleanup(conn):
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM cases WHERE case_no LIKE ?", (MARK + "%",))]
    for cid in ids:
        conn.execute("DELETE FROM notifications WHERE case_id=?", (cid,))
        conn.execute("DELETE FROM dispatch_calls WHERE dispatch_id IN "
                     "(SELECT id FROM dispatches WHERE case_id=?)", (cid,))
        conn.execute("DELETE FROM dispatches WHERE case_id=?", (cid,))
        conn.execute("DELETE FROM cases WHERE id=?", (cid,))
    conn.execute("DELETE FROM partners WHERE name LIKE ?", (MARK + "%",))
    conn.commit()


conn = DB.get_db()
cleanup(conn)
try:
    cid = mkcase(conn)
    pa = mkpartner(conn, f"{MARK}-A")
    pb = mkpartner(conn, f"{MARK}-B")

    ok1, msg1, did1 = DP.assign_dispatch(conn, cid, pa, "먼저 A에게 배정(검증)", by="검증")
    chk(ok1, "★ 1차 배정(A) 성공", msg1)

    calls = []

    def on_sup(pid, pname, old_did, case_id_):
        calls.append((pid, pname, old_did, case_id_))

    ok2, msg2, did2 = DP.assign_dispatch(conn, cid, pb, "전화로 B가 더 빠르다고 확인(검증)",
                                          by="검증", supersede=True, on_supersede=on_sup)
    chk(ok2, "★ 2차 배정(B, supersede) 성공", msg2)
    chk(len(calls) == 1, "★★★ 밀려난 협력사(A) 콜백이 정확히 한 번 불렸다", calls)
    if calls:
        pid, pname, old_did, case_id_ = calls[0]
        chk(pid == pa, "★★★ 콜백 대상이 밀려난 A다(새로 배정된 B가 아니다)", f"{pid} vs A={pa} B={pb}")
        chk(pname == f"{MARK}-A", "★★ 콜백에 그 협력사 이름도 온다", pname)
        chk(old_did == did1, "★★ 콜백의 dispatch_id 가 밀려난(옛) 수배다", f"{old_did} vs {did1}")
        chk(case_id_ == cid, "★ 콜백에 사건 id 도 온다", case_id_)

    st_a = conn.execute("SELECT status FROM dispatches WHERE id=?", (did1,)).fetchone()[0]
    st_b = conn.execute("SELECT status FROM dispatches WHERE id=?", (did2,)).fetchone()[0]
    chk(st_a == DP.ST_CANCELED, "★ 밀려난 A의 수배는 '취소'로 닫힌다(기존 동작 — 회귀 방지)", st_a)
    chk(st_b == DP.ST_CLAIMED, "★ 새로 배정된 B는 '수배됨'이다(기존 동작 — 회귀 방지)", st_b)

    #  ⚠ 콜백을 안 줘도(on_supersede 기본값 None) 예외 없이 그대로 동작해야 한다
    cid3 = mkcase(conn)
    pc = mkpartner(conn, f"{MARK}-C")
    pd = mkpartner(conn, f"{MARK}-D")
    DP.assign_dispatch(conn, cid3, pc, "1차(검증)", by="검증")
    ok3, msg3, _ = DP.assign_dispatch(conn, cid3, pd, "2차(검증)", by="검증", supersede=True)
    chk(ok3, "★ on_supersede 를 안 줘도(기본값 None) 예외 없이 동작한다(과거 호출부 호환)", msg3)

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
