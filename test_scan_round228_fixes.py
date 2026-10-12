# -*- coding: utf-8 -*-
"""스캔 228라운드 회귀 — 재시도(같은 요청이 네트워크 재전송 등으로 두 번
   도착) 안전성 두 결함.

  [1] api_settlement_undo 가 "지금 상태만 보고" 되돌릴 다음 단계를
      추론하다 보니, 같은 요청이 그대로 재시도되면 첫 호출이 이미 되돌린
      다음 단계까지 캐스케이드로 또 되돌렸다(실측: 지급검수 되돌리기
      재시도가 실제로 입금된 돈을 '미확인' 상태로 되돌렸다). 클라이언트가
      클릭 1회당 한 번만 만드는 undo_key 를 저장해, 같은 열쇠 재시도는
      이미 한 일을 또 하지 않게 막는다.
  [2] api_defect_create 에 재시도 방어가 전혀 없어, 같은 요청을 두 번
      보내면 하자가 그대로 2건 생기고 시공사 알림도 2번 나갔다. 형제
      (api_settlement_remind_approval)의 짧은 쿨다운 패턴을 그대로 가져와
      10초 안의 완전동일 재접수(사건·작성자·제목 일치)는 새로 만들지
      않는다.

      python test_scan_round228_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("═" * 72)
print("  스캔 228라운드 회귀 — 정산 되돌리기 재시도 캐스케이드 · 하자접수 중복")
print("═" * 72)

_tmpdir = tempfile.mkdtemp(prefix="round228_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(settlements)")]
    conn.close()
    chk("last_undo_key" in cols,
        "★★★ 새 DB 스키마에 settlements.last_undo_key 컬럼이 생긴다", cols)

    conn = DB.get_db()
    now = DB.now()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r228admin','x','검증','중간관리자')")
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R228업체','시공사','활성')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,is_demo) "
        "VALUES('R228-001','정산진행','유리','서울',?,0)", (pid,)).lastrowid
    sid = conn.execute(
        "INSERT INTO settlements(case_id,case_no,partner_id,partner_name,amount,fee,"
        "                        payout,review_status,transfer_status,insurer_paid,created_at) "
        "VALUES(?,?,?,?,5000000,500000,4500000,'승인','대기','입금완료',?)",
        (cid, "R228-001", pid, "R228업체", now)).lastrowid
    conn.commit()
    conn.close()

    admin = A.app.test_client()
    atok = "r228-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r228admin"; sess["admin_role"] = "중간관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = atok
    ahdr = {"X-CSRF-Token": atok}

    def settle_state():
        c = DB.get_db()
        r = c.execute("SELECT review_status, insurer_paid, transfer_status FROM settlements "
                      "WHERE id=?", (sid,)).fetchone()
        c.close()
        return dict(r)

    # ══════════════════════════════════════════════════════════
    print("\n[1] api_settlement_undo — 같은 undo_key 재시도 캐스케이드 방지")
    # ──────────────────────────────────────────────────────────
    r1 = admin.post(f"/api/settlements/{sid}/undo", headers=ahdr,
                     json={"reason": "1차 테스트되돌리기", "undo_key": "r228-key-1"})
    chk(r1.status_code == 200, "STEP 첫 되돌리기는 정상 처리된다(과잉차단 아님)",
        (r1.status_code, r1.get_json()))
    st1 = settle_state()
    chk(st1 == {"review_status": "대기", "insurer_paid": "입금완료", "transfer_status": "대기"},
        "STEP 첫 되돌리기는 '지급 검수 승인'만 되돌린다(입금확인은 그대로)", st1)

    r2 = admin.post(f"/api/settlements/{sid}/undo", headers=ahdr,
                     json={"reason": "1차 테스트되돌리기", "undo_key": "r228-key-1"})
    chk(r2.status_code == 200 and r2.get_json().get("duplicate") is True,
        "★★★★ 같은 undo_key 로 재시도하면 '이미 처리함'으로만 응답한다"
        "(고치기 전엔 상태만 보고 다음 단계로 캐스케이드돼 200 성공하며 "
        "실제로 또 되돌렸다)", (r2.status_code, r2.get_json()))
    st2 = settle_state()
    chk(st2 == st1,
        "★★★★ 재시도 후에도 보험사 입금확인 상태가 그대로 '입금완료'다"
        "(고치기 전엔 이게 조용히 '대기'로 되돌아갔다 — 실제 입금된 돈인데)",
        st2)

    r3 = admin.post(f"/api/settlements/{sid}/undo", headers=ahdr,
                     json={"reason": "2차 진짜새클릭", "undo_key": "r228-key-2"})
    chk(r3.status_code == 200 and not r3.get_json().get("duplicate"),
        "STEP 다른 undo_key(=진짜 새 클릭)는 정상적으로 다음 단계를 되돌린다"
        "(과잉차단 아님 — 의도적인 연속 되돌리기까지 막으면 안 된다)",
        (r3.status_code, r3.get_json()))
    st3 = settle_state()
    chk(st3["insurer_paid"] == "대기",
        "STEP 진짜 새 클릭은 보험사 입금확인까지 정상적으로 되돌린다", st3)

    # ══════════════════════════════════════════════════════════
    print("\n[2] api_defect_create — 10초 내 완전동일 재접수 중복방지")
    # ──────────────────────────────────────────────────────────
    dhdr = {"X-CSRF-Token": atok}
    payload = {"case_id": cid, "title": "R228 재시도 테스트 하자", "content": "동일요청 재시도 테스트"}
    d1 = admin.post("/api/defects", headers=dhdr, json=payload)
    chk(d1.status_code == 200 and d1.get_json().get("ok") is True,
        "STEP 첫 하자접수는 정상 처리된다(과잉차단 아님)", (d1.status_code, d1.get_json()))

    d2 = admin.post("/api/defects", headers=dhdr, json=payload)
    chk(d2.status_code == 200 and d2.get_json().get("duplicate") is True,
        "★★★★ 같은 사건·같은 제목으로 10초 내 재접수하면 새로 만들지 않고 "
        "'이미 처리함'으로 응답한다(고치기 전엔 하자가 그대로 2건 생기고 "
        "시공사 알림도 2번 나갔다)", (d2.status_code, d2.get_json()))

    conn = DB.get_db()
    n_defects = conn.execute("SELECT COUNT(*) n FROM defects WHERE case_id=?", (cid,)).fetchone()["n"]
    n_notif = conn.execute(
        "SELECT COUNT(*) n FROM notifications WHERE ntype='하자접수' AND case_id=?", (cid,)
    ).fetchone()["n"]
    conn.close()
    chk(n_defects == 1, "★★★ 하자 레코드가 1건만 생긴다(중복 없음)", n_defects)
    chk(n_notif == 1, "★★★ 시공사 알림도 1건만 나간다(중복 없음)", n_notif)

    d3 = admin.post("/api/defects", headers=dhdr,
                     json={"case_id": cid, "title": "완전히 다른 제목의 새 하자", "content": "새 접수"})
    chk(d3.status_code == 200 and not d3.get_json().get("duplicate"),
        "STEP 제목이 다른 새 하자는 정상적으로 새로 접수된다(과잉차단 아님)",
        (d3.status_code, d3.get_json()))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드228 서버측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
