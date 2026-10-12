# -*- coding: utf-8 -*-
"""
359라운드 회귀 — api_case_cancel_award()(app.py:19358, POST
/api/cases/<cid>/cancel-award, 낙찰 취소) 가 형제 자식표(field_agreements·
bids·change_orders·auctions·est_outcome·협력사 실적캐시)는 전부 꼼꼼히
정리하면서 defects(하자) 만 빠뜨리고 있던 결함[중간, 데이터정합성 —
배정 해제된 옛 업체를 가리키는 하자가 재공고 뒤에도 그대로 남음].

  배경: 하자(defect) 상태전이를 조사한 Agent가 "사건 취소가 진행중
  하자를 정리 안 한다"고 지목했는데, 그 구체적 재현(api_insurer_case_
  cancel, 4158행 — 발주처의 자체 사건취소)은 직접 확인 결과 성립
  불가능이었다: 그 라우트는 `status in ('접수','입찰중')`(4186행)일
  때만 허용되는데, 하자는 실무상 업체가 배정돼 시공이 진행/완료된
  뒤에야 생긴다 — 두 조건이 같은 사건에서 동시에 성립할 수 없다
  (에이전트의 위협모델 재구성이 부정확했던 사례).

  대신 직접 코드를 따라가 더 현실적인 자리를 찾았다 — api_case_
  cancel_award()(19358행, `status in ('시공중','완료보고지연')` 대상)는
  실제로 시공이 진행/완료된 단계에서 동작하고, api_defect_create()
  (13707행)는 case.status 를 전혀 안 봐서(실측 확인) 그 단계에서
  하자 접수 자체를 막지 않는다 — 특히 '완료보고지연'(시공은 끝났는데
  보고만 밀린 상태)에서 보험사가 현장을 보고 하자를 접수하는 그림은
  실제로 가능하다. 그 상태에서 낙찰이 취소되면(부도·잠적 등) 열린
  하자 행이 배정 해제된 옛 업체를 가리킨 채 남고, 사건은 재공고돼
  전혀 다른 업체가 낙찰될 수 있다 — 새 업체는 자기가 안 한 일의
  하자를 떠안을 근거가 없고, 그 하자를 누가 처리할지는 사람의 판단
  영역이라 코드가 임의로 정할 수 없다.

  고침: 하자 상태를 억지로 바꾸거나 지우지 않고, 같은 함수가 이미
  정산·변경견적에 쓰는 것과 똑같은 방식(존재하면 조용히 진행시키지
  않고 명확한 사유와 함께 차단)으로 세 번째 관문을 추가 — 하자를
  먼저 완료·반려로 정리해야 낙찰 취소가 가능하다. DEFECT_CLOSED_STATES
  (13525행, 이미 여러 곳에서 재사용되는 기존 상수)를 그대로 재사용.

  실행기반 검증: 실제 Flask app.test_client() 로 '완료보고지연' 사건에
  열린 하자를 심어 낙찰취소를 시도해 409/DEFECT_ACTIVE 로 막히는지,
  그 하자를 완료 처리한 뒤 재시도하면 정상 진행되는지, 하자가 아예
  없는 대조군 사건은 처음부터 막히지 않는지 실측 — round91·103·134·
  139·192의 기존 cancel_award 테스트도 회귀 없이 그대로 통과함을
  재확인(전부 defects 를 안 다루는 기존 테스트라 이번 수정과 안 겹침).
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


print("=" * 72)
print("  스캔 359라운드 회귀 — 낙찰취소가 열린 하자를 놓치던 결함")
print("=" * 72)

APP_SRC = read("app.py")

print("\n[1] 소스 확인")
i0 = APP_SRC.index("def api_case_cancel_award(cid):")
i1 = APP_SRC.index("\ndef ", i0 + 1)
body_src = APP_SRC[i0:i1]
chk("DEFECT_ACTIVE" in body_src and "DEFECT_CLOSED_STATES" in body_src,
    "★★★★★ cancel_award 가 열린 하자를 DEFECT_CLOSED_STATES 기준으로 확인해 차단한다")
i_dfc = body_src.index("DEFECT_ACTIVE")
i_co = body_src.index("CHANGE_ORDER_ACTIVE")
chk(i_dfc > i_co,
    "★★★ 하자 확인이 기존 정산·변경견적 확인 뒤(같은 자리 순서)에 이어진다")

print("\n[2] 실행 — 실제 Flask 서버로 '완료보고지연' 사건에 열린 하자를 심어 낙찰취소를 시도")
_tmpdir = tempfile.mkdtemp(prefix="round359_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    now = DB.now()

    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r359admin','x','검증','중간관리자')")
    iid = conn.execute(
        "INSERT INTO insurers(name,status,login_id,created_at) "
        "VALUES('R359보험', '활성', 'r359i', ?)", (now,)).lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name, status, license_status, region, created_at) "
        "VALUES('R359업체', '활성', '확인됨', '서울', ?)", (now,)).lastrowid

    #  ── 사건A: '완료보고지연'(시공은 끝났는데 보고만 밀린 상태) + 열린 하자 1건 ──
    cid_a = conn.execute(
        "INSERT INTO cases(case_no, status, category, region, insurer_id, "
        "                   est_price, partner_id, partner_name, award_amount, "
        "                   award_route, awarded_at, is_demo, created_at) "
        "VALUES('R359-A', '완료보고지연', '유리', '서울', ?, 3000000, ?, 'R359업체', "
        "       5500000, '1차합의', ?, 0, ?)",
        (iid, pid, now, now)).lastrowid
    did_a = conn.execute(
        "INSERT INTO defects(defect_no, case_id, case_no, status, title, "
        "                     reporter, reporter_type, due_date, created_at) "
        "VALUES('D359-A', ?, 'R359-A', '접수', '누수 재발', '검증', '내부', ?, ?)",
        (cid_a, now[:10], now)).lastrowid

    #  ── 대조군 사건B: 같은 조건이지만 하자가 아예 없음 ──
    cid_b = conn.execute(
        "INSERT INTO cases(case_no, status, category, region, insurer_id, "
        "                   est_price, partner_id, partner_name, award_amount, "
        "                   award_route, awarded_at, is_demo, created_at) "
        "VALUES('R359-B', '완료보고지연', '유리', '서울', ?, 3000000, ?, 'R359업체', "
        "       5500000, '1차합의', ?, 0, ?)",
        (iid, pid, now, now)).lastrowid
    conn.commit()

    admin = A.app.test_client()
    atok = "r359-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r359admin"; sess["admin_role"] = "중간관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = atok
    ahdr = {"X-CSRF-Token": atok}

    r1 = admin.post(f"/api/cases/{cid_a}/cancel-award",
                     json={"reason": "낙찰업체 부도로 재공고합니다"}, headers=ahdr)
    j1 = r1.get_json() or {}
    chk(r1.status_code == 409 and j1.get("code") == "DEFECT_ACTIVE",
        "★★★★★ 열린 하자가 있으면 낙찰취소가 409/DEFECT_ACTIVE 로 막힌다"
        "(고치기 전엔 그대로 진행돼 하자가 배정해제된 옛 업체를 가리킨 채 남았다)",
        (r1.status_code, j1))

    c_a_after_block = conn.execute("SELECT status, partner_id FROM cases WHERE id=?", (cid_a,)).fetchone()
    chk(c_a_after_block["status"] == "완료보고지연" and c_a_after_block["partner_id"] == pid,
        "  차단됐으니 사건 상태·배정은 전혀 안 바뀌었다(부분 변경 없음)",
        dict(c_a_after_block))

    # 하자를 완료 처리한 뒤 재시도 — 이번엔 정상 진행돼야 한다
    conn.execute("UPDATE defects SET status='완료', resolved_at=? WHERE id=?", (now, did_a))
    conn.commit()
    r2 = admin.post(f"/api/cases/{cid_a}/cancel-award",
                     json={"reason": "낙찰업체 부도로 재공고합니다"}, headers=ahdr)
    j2 = r2.get_json() or {}
    chk(r2.status_code == 200 and j2.get("ok") is True,
        "★★★★ 그 하자를 완료 처리하고 나면 같은 사건도 정상적으로 낙찰취소된다"
        "(과잉차단 아님 — 하자를 지우거나 상태를 억지로 바꾸지 않고도 통과)",
        (r2.status_code, j2))
    c_a_after = conn.execute("SELECT status, partner_id FROM cases WHERE id=?", (cid_a,)).fetchone()
    chk(c_a_after["status"] == "입찰중" and c_a_after["partner_id"] is None,
        "  실제로 배정이 해제되고 재공고 상태로 넘어갔다", dict(c_a_after))

    # 대조군 — 하자가 아예 없는 사건은 처음부터 막히지 않는다
    r3 = admin.post(f"/api/cases/{cid_b}/cancel-award",
                     json={"reason": "낙찰업체 부도로 재공고합니다"}, headers=ahdr)
    j3 = r3.get_json() or {}
    chk(r3.status_code == 200 and j3.get("ok") is True,
        "  대조군 — 하자가 아예 없는 사건은 과잉차단 없이 그대로 낙찰취소된다",
        (r3.status_code, j3))

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n[3] 회귀 확인 — 기존 cancel_award 테스트(91·103·134·139·192)가 여전히 통과하는가")
import subprocess  # noqa: E402
for rn in (91, 103, 134, 139, 192):
    fn = f"test_scan_round{rn}_fixes.py"
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, fn)],
                            capture_output=True, text=True, encoding="utf-8",
                            cwd=HERE, timeout=60)
        chk(r.returncode == 0, f"  {fn} 단독 재실행 통과",
            (r.returncode, (r.stdout or "")[-300:], (r.stderr or "")[-200:]))
    except Exception as e:                                          # noqa: BLE001
        chk(False, f"  {fn} 재실행 준비", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
