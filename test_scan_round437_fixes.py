# -*- coding: utf-8 -*-
"""스캔 437라운드 회귀 — 보험사 정지(중지) 게이트가 진행 중 사건(cases)을
   전혀 보지 않던 결함, 1건. 정산 지급완료(paid/paid-bulk) 동시성은 각도2로
   조사됐으나 클린(BEGIN IMMEDIATE + rowcount 가드 이미 충분) — 이 파일은
   각도1의 핵심 결함만 다룬다.

   정밀조사 Agent가 발견 — `_insurer_exit_load()`(app.py:8040-)는 형제
   `_partner_exit_load()`(7989-, 진행 중 사건까지 검사)와 달리 settlements·
   field_agreements 두 가지만 봤다. settlements 행은 완료보고~검수 단계에
   가서야 생기므로, **입찰중**(공고만 뜬 상태) 또는 **낙찰 직후 시공중**
   (완료보고 전이라 정산행이 아직 없는) 사건은 이 두 조건 어디에도 안 걸려
   확인(confirm_demote) 없이 그대로 200으로 '중지' 처리됐다. 그 뒤에도
   협력사는 그 공고에 계속 투찰 가능(api_partner_bid 는 사건의 insurer
   상태를 안 봄)해 나중에 완료보고→승인 단계에서야 영구 정체가 드러난다.
   partner_id 는 낙찰 이후에나 붙어 _partner_exit_load 의 좁은 상태목록
   (시공중·완료보고지연·검수대기·정산진행)으로 충분하지만, insurer_id 는
   사건 생성 시점부터 붙어 있어 더 넓은 CASE_OPEN_SQL(미종결 전체)이 필요.

   고침: `_insurer_exit_load()`에 `cases WHERE insurer_id=? AND
   {CASE_OPEN_SQL} AND is_demo=0` 검사를 추가(형제와 같은 패턴, 새 로직
   불필요), `_insurer_demote_gate()`의 차단조건·안내문에 active_count 반영.
   트레이드오프 없는 "그냥 고치면 되는 것". (사후 가시성 공백 — 사건상세/
   목록 API가 협력사·보험사 상태를 안 보여주는 별개 발견은 이번 라운드
   범위 밖, 다음 라운드 후보로 기록. 협력사가 정지된 보험사 공고에 계속
   투찰 가능한 것도 이 게이트가 고쳐지면 향후 신규 정지부터는 자연히
   해소되는 부수효과라 이번엔 별도로 안 건드림.)

   ⚠⚠ [라운드622] 되돌림-증명([5])을 옛 세대(app.py를 실제로 디스크에 써넣고
   `python -c`서브프로세스로 재현한 뒤 복원)에서 안전한 인메모리 기법으로
   이관한다. `_insurer_exit_load()`·`_insurer_demote_gate()` 둘 다 평범한
   모듈함수(라우트 아님)이고, 실제 호출자는 `_insurer_demote_gate`가 안에서
   `_insurer_exit_load`를 바로 부르는 것 하나, 그리고 이 되돌림 대상 밖의
   진짜 라우트 `api_insurer_update`(9389행)가 `_insurer_demote_gate`를
   **이름으로**(전역조회) 부르는 것 하나 — 즉 실제 app 모듈 자신의 __dict__에
   심어야 손 안 댄 진짜 라우트가 되돌린 버전을 보게 된다(기법3). 두 함수를
   한 번의 exec로 함께 A.__dict__에 심어(정의 순서상 load가 먼저라 상호참조도
   그대로 해결) 실제 Flask test_client 호출로 재현한 뒤 원래 함수 객체로
   복원한다 — 진짜 app.py 파일은 이 되돌림-증명 내내 전혀 안 건드린다.

       python test_scan_round437_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(HERE, "app.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

print("=" * 72)
print("  스캔 437라운드 회귀 — 보험사 정지 게이트의 cases 사각지대")
print("=" * 72)

print("\n[1] 소스 확인")
_i0 = APP_SRC.index("def _insurer_exit_load(conn, iid):")
_i1 = APP_SRC.index("\ndef _insurer_demote_gate(", _i0)
_i2 = APP_SRC.index("\n\n\n@app.get(\"/api/partners/<int:pid>/exit-check\")", _i1)
NEW_BLOCK = APP_SRC[_i0:_i2]
chk("active_cases" in NEW_BLOCK and "active_count" in NEW_BLOCK and "CASE_OPEN_SQL" in NEW_BLOCK,
    "★★★★★ _insurer_exit_load()가 이제 cases(CASE_OPEN_SQL)를 검사하고 "
    "active_cases/active_count를 반환한다")
chk('info["active_count"]' in NEW_BLOCK,
    "★★★★★ _insurer_demote_gate()의 차단조건이 active_count도 함께 본다")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round437_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r437admin','x','검증','최고관리자')")

    #  (a) 입찰중 사건만 있는 보험사 — settlements/field_agreements 는 0건
    iid_bidding = conn.execute(
        "INSERT INTO insurers(name,org_type,status,fee_rate_bp) "
        "VALUES('R437보험(입찰중)','손해보험','활성',1000)").lastrowid
    conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo,created_at) "
        "VALUES('R437-BID','입찰중','가드레일','서울',?,0,?)", (iid_bidding, DB.now()))

    #  (b) 낙찰 직후 시공중(정산행 아직 없음)인 사건만 있는 보험사
    iid_constr = conn.execute(
        "INSERT INTO insurers(name,org_type,status,fee_rate_bp) "
        "VALUES('R437보험(시공중)','손해보험','활성',1000)").lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,created_at) "
        "VALUES('R437업체','시공사','활성','가드레일','서울',?)", (DB.now(),)).lastrowid
    conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,partner_id,is_demo,created_at) "
        "VALUES('R437-CONSTR','시공중','가드레일','서울',?,?,0,?)",
        (iid_constr, pid, DB.now()))

    #  (c) 대조군 — 데모 사건만 있는 보험사(진짜 업무 아님, 카운트에서 빠져야 함)
    iid_demo_only = conn.execute(
        "INSERT INTO insurers(name,org_type,status,fee_rate_bp) "
        "VALUES('R437보험(데모만)','손해보험','활성',1000)").lastrowid
    conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo,created_at) "
        "VALUES('R437-DEMO','시공중','가드레일','서울',?,1,?)", (iid_demo_only, DB.now()))

    #  (d) 대조군 — 진짜로 업무 없는 보험사(NEED_REASON만으로 통과해야 함)
    iid_clean = conn.execute(
        "INSERT INTO insurers(name,org_type,status,fee_rate_bp) "
        "VALUES('R437보험(한가함)','손해보험','활성',1000)").lastrowid
    conn.commit()

    admin = A.app.test_client()
    tok = "r437-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r437admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    print("\n[3] 실행 — 새 코드는 입찰중/시공중 사건도 확인 없이는 못 내린다")
    r1 = admin.patch(f"/api/insurers/{iid_bidding}", headers=hdr, json={"status": "중지"})
    j1 = r1.get_json() or {}
    chk(r1.status_code == 409 and j1.get("code") == "INSURER_HAS_WORK" and j1.get("active_count") == 1,
        "★★★★★ 입찰중 사건 하나뿐이어도 확인 없이는 409로 막힌다"
        "(고치기 전엔 200으로 그냥 통과됐다)", (r1.status_code, j1))

    r2 = admin.patch(f"/api/insurers/{iid_constr}", headers=hdr, json={"status": "중지"})
    j2 = r2.get_json() or {}
    chk(r2.status_code == 409 and j2.get("code") == "INSURER_HAS_WORK" and j2.get("active_count") == 1,
        "★★★★★ 낙찰 직후 시공중(정산행 아직 없음) 사건도 확인 없이는 409로 막힌다", (r2.status_code, j2))

    r3 = admin.patch(f"/api/insurers/{iid_constr}", headers=hdr,
                      json={"status": "중지", "confirm_demote": True, "status_reason": "계약 종료"})
    j3 = r3.get_json() or {}
    chk(r3.status_code == 200 and j3.get("ok"),
        "  확인+사유를 함께 보내면(강행 의사 명시) 실제로 상태가 바뀐다(과잉차단 아님)", j3)
    row3 = conn.execute("SELECT status FROM insurers WHERE id=?", (iid_constr,)).fetchone()
    chk(row3["status"] == "중지", "  DB에도 실제로 반영된다", dict(row3))

    print("\n[4] 대조군 — 데모 사건뿐이거나 업무가 정말 없으면 과잉차단하지 않는다")
    r4 = admin.patch(f"/api/insurers/{iid_demo_only}", headers=hdr,
                      json={"status": "중지", "status_reason": "테스트 정리"})
    j4 = r4.get_json() or {}
    chk(r4.status_code == 200 and j4.get("ok"),
        "  데모 사건만 있으면(is_demo=1) active_count에 안 잡혀 사유만으로 바로 통과", j4)

    r5 = admin.patch(f"/api/insurers/{iid_clean}", headers=hdr, json={"status": "중지"})
    j5 = r5.get_json() or {}
    chk(r5.status_code == 400 and j5.get("code") == "NEED_REASON",
        "  업무가 정말 없는 보험사는 강등확인 없이 곧장 사유만 요구한다(기존 동작 유지)", j5)
    r5b = admin.patch(f"/api/insurers/{iid_clean}", headers=hdr,
                       json={"status": "중지", "status_reason": "계약 미갱신"})
    chk(r5b.status_code == 200 and (r5b.get_json() or {}).get("ok"),
        "  사유만 채우면 confirm_demote 없이도 바로 성공(기존 동작 유지)", r5b.get_json())

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 되돌리기 — 옛 코드(cases 미검사)였다면 실제로 재현되는가")
# ------------------------------------------------------------
OLD_BLOCK = NEW_BLOCK
#  active_cases 쿼리·반환키·차단조건·안내문 4곳을 전부 옛 모습으로 되돌린다.
OLD_BLOCK = OLD_BLOCK.replace(
    '''    active = rows(conn.execute(
        f"""SELECT id, case_no, status FROM cases
             WHERE insurer_id=? AND {CASE_OPEN_SQL} AND COALESCE(is_demo,0)=0
             ORDER BY id DESC LIMIT 20""", (iid,)))
    pending_settle''', '    pending_settle')
OLD_BLOCK = OLD_BLOCK.replace(
    '    return {"active_cases": active, "active_count": len(active),\n'
    '            "pending_settlements": pending_settle,',
    '    return {"pending_settlements": pending_settle,')
OLD_BLOCK = OLD_BLOCK.replace(
    'if not info["active_count"] and not info["pending_settlement_count"]'
    ' and not info["pending_agreement_count"]:',
    'if not info["pending_settlement_count"] and not info["pending_agreement_count"]:')
OLD_BLOCK = OLD_BLOCK.replace(
    '''    cnames = ", ".join(f"{c['case_no']}({c['status']})" for c in info["active_cases"][:3])
    snames''', '    snames')
OLD_BLOCK = OLD_BLOCK.replace(
    '''        "error": (
            (f"진행 중 사건 {info['active_count']}건({cnames})"
             if info["active_count"] else "")
            + (" · " if info["active_count"]
               and (info["pending_settlement_count"] or info["pending_agreement_count"]) else "")
            + (f"완료 승인 대기 정산''',
    '''        "error": (
            (f"완료 승인 대기 정산''')

try:
    chk(OLD_BLOCK != NEW_BLOCK, "  (준비) 되돌리기 텍스트가 실제로 달라졌다")
    chk("active_cases" not in OLD_BLOCK and "active_count" not in OLD_BLOCK,
        "  (준비) 되돌린 블록에 cases 검사 흔적이 완전히 사라졌다")

    #  ⚠ _insurer_exit_load()·_insurer_demote_gate() 둘 다 평범한 모듈함수라
    #    데코레이터가 없다 — 그대로 A.__dict__에 exec하면 두 함수가 한 번에
    #    다시 정의되고(순서상 load가 먼저라 gate 안의 참조도 그대로 풀린다),
    #    이 되돌림 대상 밖의 진짜 라우트 api_insurer_update(9389행 부근)가
    #    _insurer_demote_gate를 이름으로(전역조회) 부르므로 자연히 되돌린
    #    버전을 타게 된다 — app.py 파일도, import app도 다시 할 필요 없다.
    _orig_load = A._insurer_exit_load
    _orig_gate = A._insurer_demote_gate
    exec(compile(OLD_BLOCK, "<round437_reverted_insurer_exit_gate>", "exec"), A.__dict__)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    try:
        conn2 = DB.get_db()
        iid2 = conn2.execute(
            "INSERT INTO insurers(name,org_type,status,fee_rate_bp) "
            "VALUES('R437보험(입찰중,되돌림)','손해보험','활성',1000)").lastrowid
        conn2.execute(
            "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo,created_at) "
            "VALUES('R437-BID2','입찰중','가드레일','서울',?,0,?)", (iid2, DB.now()))
        conn2.commit()
        c2 = A.app.test_client()
        with c2.session_transaction() as sess:
            sess["admin"] = "r437admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
            sess["_csrf"] = "tok2"
        r6 = c2.patch(f"/api/insurers/{iid2}", headers={"X-CSRF-Token": "tok2"},
                       json={"status": "중지", "status_reason": "계약 종료"})
        old_status = r6.status_code
        old_db_status = conn2.execute(
            "SELECT status FROM insurers WHERE id=?", (iid2,)).fetchone()["status"]
        conn2.close()
    finally:
        A.__dict__["_insurer_exit_load"] = _orig_load
        A.__dict__["_insurer_demote_gate"] = _orig_gate

    chk(old_status == 200,
        "★★★★★ 옛 코드는 입찰중 사건이 있어도 확인 없이 200으로 그냥 통과시킨다"
        "(인과관계 직접증명)", old_status)
    chk(old_db_status == "중지",
        "★★★★★ 옛 코드에서는 실제로 DB까지 '중지'로 바뀐다(경고 한 번 없이)", old_db_status)
    chk(A._insurer_exit_load is _orig_load and A._insurer_demote_gate is _orig_gate,
        "  되돌림-증명 뒤 두 함수 모두 원래 객체로 복원됐다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기 실행", f"{type(e).__name__} {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(모듈 __dict__ 임시치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
