# -*- coding: utf-8 -*-
"""스캔 140라운드 회귀 — 2건.

  [1] RATING_PENALTY 에 '경미' 등급이 빠져 있었다 — partner_rating()이
      .get(severity, 0.1) 기본값으로 떨어져 '경미' 하자가 '보통' 하자와
      똑같이 0.1점 감점됐다(3단계 심각도가 실제로는 2단계로 무너져 있었다).
  [2] api_insurer_field_agreement_decision(1차합의 승인/부동의)이 승인자
      이름을 session["insurer_name"](=조직명, 하위계정 전원 동일)으로 남겨
      같은 보험사의 서로 다른 하위계정이 승인해도 field_agreements.
      approver_name·activity_log.actor 가 구분되지 않았다 — 같은 파일의
      portal_actor()(조직명+로그인아이디)로 통일한다.

      python test_scan_round140_fixes.py
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


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 140라운드 회귀 — 평점감점표 '경미' 누락 · 1차합의 승인자 하위계정 미구분")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk('RATING_PENALTY = {"중대": 0.2, "보통": 0.1, "경미": 0.05}' in APP_SRC,
    "★★★ RATING_PENALTY 에 '경미' 등급이 추가되어 3단계 전부 서로 다른 감점을 갖는다")

i_gate = APP_SRC.index("def api_insurer_field_agreement_decision(")
i_gate_end = APP_SRC.index("\ndef ", i_gate + 1)
gate_body = APP_SRC[i_gate:i_gate_end]
chk('"name": portal_actor() or "보험사"' in gate_body,
    "★★★ api_insurer_field_agreement_decision 이 approver.name 을 portal_actor()로 채운다")
chk('"name": session.get("insurer_name")' not in gate_body,
    "★★★ 하위계정을 구분 못 하던 옛 session.get('insurer_name') 직접 사용이 사라졌다")

# ============================================================
print("\n[2] 실행 — partner_rating(): '경미'·'보통' 하자가 이제 다른 감점을 받는다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round140_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A
    import dispatch as DP

    conn = DB.get_db()

    def _mk_partner(tag):
        return conn.execute(
            "INSERT INTO partners(name,partner_type,status,category,region) "
            f"VALUES('R140업체{tag}','시공사','활성','가드레일','서울')").lastrowid

    def _mk_case(tag, pid):
        return conn.execute(
            "INSERT INTO cases(case_no,status,category,region,partner_id,is_demo) "
            f"VALUES('R140-{tag}','완료','가드레일','서울',?,0)", (pid,)).lastrowid

    def _rated(tag, severity):
        """같은 해피콜 기준점(4.62점) 위에 하자 1건만 severity로 심어 평점을 본다."""
        pid = _mk_partner(tag)
        cid = _mk_case(tag, pid)
        conn.execute("INSERT INTO happy_calls(partner_id,case_id,score,is_demo) "
                     "VALUES(?,?,4.62,0)", (pid, cid))
        conn.execute(
            "INSERT INTO defects(case_id,partner_id,title,severity,status,cost_bearer,is_demo) "
            "VALUES(?,?,'검증용 하자',?,'완료','시행사',0)", (cid, pid, severity))
        conn.commit()
        return A.partner_rating(conn, pid)

    val_mild, info_mild = _rated("mild", "경미")
    val_mod, info_mod = _rated("mod", "보통")
    val_sev, info_sev = _rated("sev", "중대")
    chk(val_mild is not None and val_mod is not None and val_sev is not None,
        "★ (사전조건) 세 시나리오 모두 평점이 산출된다(해피콜 존재)",
        (val_mild, val_mod, val_sev))
    chk(val_mild != val_mod,
        "★★★ '경미' 하자 평점이 '보통'과 더는 같지 않다"
        "(고치기 전엔 둘 다 .get(severity,0.1) 기본값 0.1로 떨어져 완전히 동일했다)",
        {"경미": val_mild, "보통": val_mod})
    chk(val_mild > val_mod,
        "★★★ '경미'가 '보통'보다 감점이 작아 평점이 더 높다", {"경미": val_mild, "보통": val_mod})
    chk(val_mod > val_sev,
        "★ '보통'이 '중대'보다는 여전히 감점이 작다(기존 서열 유지)", {"보통": val_mod, "중대": val_sev})
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드140 [1] 평점감점표 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — 1차합의 승인 라우트: 같은 보험사의 서로 다른 하위계정이 구분된다")
# ------------------------------------------------------------
try:
    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,org_type,status,fee_rate_bp) "
        "VALUES('R140보험','손해보험','활성',900)").lastrowid
    #  ⚠ 두 하위계정의 login_id 만 다르고 조직은 동일 — session["insurer_name"]은
    #    둘 다 'R140보험'으로 같다(_portal_authenticate 의 하위계정 분기가 org["name"]
    #    을 그대로 돌려주기 때문). 이 동일함이 바로 고치기 전 결함의 전제조건이다.
    sub1 = conn.execute(
        "INSERT INTO portal_users(org_type,org_id,login_id,password_hash,name,role,status) "
        "VALUES('insurer',?,?,'x','김대리','중간관리자','활성')", (iid, "r140_kim")).lastrowid
    sub2 = conn.execute(
        "INSERT INTO portal_users(org_type,org_id,login_id,password_hash,name,role,status) "
        "VALUES('insurer',?,?,'x','박대리','중간관리자','활성')", (iid, "r140_park")).lastrowid
    conn.commit()

    def _open_review(tag, pid):
        """수배→수락→도착→1차합의 개시 까지 실제 함수 체인으로 만들어 AG_REVIEW 를 연다."""
        cid = conn.execute(
            "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
            f"VALUES('R140-AG{tag}','접수','가드레일','서울',?,0)", (iid,)).lastrowid
        did = conn.execute(
            "INSERT INTO dispatches(case_id,status,created_at) VALUES(?,?,datetime('now','+9 hours'))",
            (cid, DP.ST_OPEN)).lastrowid
        conn.execute("INSERT INTO dispatch_calls(dispatch_id,partner_id) VALUES(?,?)", (did, pid))
        conn.commit()
        ok_c, _, _ = DP.claim(conn, did, pid, f"R140업체{tag}")
        ok_a, _ = DP.arrive(conn, did, pid, 3, field_estimate=850000)
        chk(ok_c is True and ok_a is True, f"★ (사전조건 {tag}) 수배 수락·도착 성공", (ok_c, ok_a))
        aid = DP.open_agreement(conn, cid, dispatch_id=did, our_staff="검증", insurer_staff="검증보험")
        chk(aid is not None, f"★ (사전조건 {tag}) 1차합의 검토 개설 성공")
        conn.commit()
        return cid, aid

    pid1 = _mk_partner_r140 = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,phone,login_id) "
        "VALUES('R140출동1','시공사','활성','가드레일','서울','01011110000','r140p1')").lastrowid
    pid2 = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,phone,login_id) "
        "VALUES('R140출동2','시공사','활성','가드레일','서울','01022220000','r140p2')").lastrowid
    conn.commit()

    cid1, aid1 = _open_review("1", pid1)
    cid2, aid2 = _open_review("2", pid2)

    client = A.app.test_client()

    def _approve_as(sub_id, login_id, cid):
        tok = f"r140-csrf-{sub_id}"
        with client.session_transaction() as sess:
            sess.clear()
            sess["insurer_id"] = iid
            sess["insurer_name"] = "R140보험"       # 하위계정 전원 동일(조직명) — 고의로 재현
            sess["insurer_login"] = login_id
            sess["portal_sub_id"] = sub_id
            sess["portal_role"] = "중간관리자"
            sess["pw_role"] = "insurer"
            sess["_csrf"] = tok
        r = client.post(f"/api/insurer/cases/{cid}/field-agreement/decision",
                        json={"approve": True}, headers={"X-CSRF-Token": tok})
        return r

    r1 = _approve_as(sub1, "r140_kim", cid1)
    chk(r1.status_code == 200, "★ 하위계정1(김대리) 승인 요청이 200으로 처리된다",
        (r1.status_code, r1.get_data(as_text=True)))
    r2 = _approve_as(sub2, "r140_park", cid2)
    chk(r2.status_code == 200, "★ 하위계정2(박대리) 승인 요청이 200으로 처리된다",
        (r2.status_code, r2.get_data(as_text=True)))

    name1 = conn.execute(
        "SELECT approver_name FROM field_agreements WHERE id=?", (aid1,)).fetchone()["approver_name"]
    name2 = conn.execute(
        "SELECT approver_name FROM field_agreements WHERE id=?", (aid2,)).fetchone()["approver_name"]
    chk(name1 == "R140보험(r140_kim)", "★★★ 하위계정1의 approver_name 이 로그인아이디까지 특정한다", name1)
    chk(name2 == "R140보험(r140_park)", "★★★ 하위계정2의 approver_name 이 로그인아이디까지 특정한다", name2)
    chk(name1 != name2,
        "★★★ 같은 보험사의 서로 다른 하위계정이 서로 다른 승인자로 기록된다"
        "(고치기 전엔 둘 다 조직명 'R140보험'으로 동일해 누가 승인했는지 구분이 불가능했다)",
        {"하위계정1": name1, "하위계정2": name2})

    log1 = conn.execute(
        "SELECT actor FROM activity_log WHERE action='1차 합의 승인(보험사)' "
        "ORDER BY id DESC LIMIT 2").fetchall()
    actors = {r["actor"] for r in log1}
    chk(actors == {"R140보험(r140_kim)", "R140보험(r140_park)"},
        "★★★ activity_log.actor 도 승인자별로 구분되어 남는다(감사 추적)", actors)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드140 [2] 하위계정 승인자 구분 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
