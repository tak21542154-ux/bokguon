# -*- coding: utf-8 -*-
"""스캔 105라운드 회귀 — 보험사판 동명기관 정산누출·권한우회, 담당배정 감사이력 소실.

  [1] (치명) 보험사 대시보드·완료승인이 104라운드가 협력사판에서 고친 것과
      정확히 같은 결함을 보험사판에서 갖고 있었다 — 게다가 여기는 바로 위
      주석이 "[테넌시] 이름이 아니라 ID 로 묶는다. 동명 기관이 생겨도 서로의
      정산이 섞이지 않는다"고 명시하는데 정반대였다. 동명 보험사 둘이 같은
      레거시 정산(insurer_id 미채움)을 각자 자기 것으로 보고, 심지어
      '공사 완료 승인'(api_insurer_settlement_approve — "자기 기관 정산만
      승인할 수 있다"는 그 함수 자신의 docstring과 반대)까지 할 수 있었다.
      월별 명세서(_insurer_statement)는 안전하지만 지나치게 엄격해 숫자가
      갈렸다 — 셋을 한 헬퍼로 통일한다.
  [2] 담당 매니저 배정의 실제 화면 경로(api_case_edit 의 manager 필드)는
      "누가 언제 배정했나"를 안 찍었고, 그걸 찍는 유일한 코드(api_assign_manager)
      는 admin.js·templates 어디서도 부르지 않는 죽은 라우트였다 — 그나마도
      권한 문턱이 실제 경로보다 낮았다. 실 경로로 감사컬럼을 옮기고 죽은
      라우트는 지운다.

      python test_scan_round105_fixes.py
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


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("═" * 72)
print("  스캔 105라운드 회귀 — 보험사 동명기관 정산누출·권한우회, 담당배정 감사이력 소실")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 네 지점 모두 확인")
# ──────────────────────────────────────────────────────────────
scope_body = _py_fn_body(APP_SRC, "_insurer_settlement_scope")
chk("(SELECT COUNT(*) FROM insurers q WHERE q.name = ?) = 1" in scope_body,
    "★★★ 정본 스코프 헬퍼가 백필과 같은 유일성 조건을 건다")

appr_body = _py_fn_body(APP_SRC, "api_insurer_settlement_approve")
chk("_insurer_settlement_scope(iid" in appr_body,
    "★★★ 완료승인이 정본 헬퍼를 쓴다(예전엔 유일성 없는 손조립)")

dash_body = _py_fn_body(APP_SRC, "api_insurer_dashboard")
chk(dash_body.count("_insurer_settlement_scope(iid") >= 1,
    "★★★ 보험사 대시보드(목록·KPI)가 정본 헬퍼를 쓴다")

stmt_body = _py_fn_body(APP_SRC, "_insurer_statement")
chk('_insurer_settlement_scope(insurer_id, (ins or {}).get("name"), alias="s.")' in stmt_body,
    "★★ 월별 명세서도 같은 헬퍼를 별칭(s.)과 함께 쓴다(대시보드와 모집단 통일)")

edit_body = _py_fn_body(APP_SRC, "api_case_edit")
chk('sets += ["manager_assigned_by=?", "manager_assigned_at=datetime(\'now\',\'+9 hours\')"]' in edit_body,
    "★★★ 담당 배정의 실제 경로(api_case_edit)가 감사컬럼을 찍는다")

chk("def api_assign_manager(cid):" not in APP_SRC,
    "★★ 죽은 라우트(api_assign_manager)가 삭제됐다")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[4] 실행 — 실제 시나리오를 돌린다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round105_")
_dbpath = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_DB_PATH"] = _dbpath
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
                 "VALUES('admin','x','검증','중간관리자')")
    i_dup1 = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('R105동명보험','활성')").lastrowid
    i_dup2 = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('R105동명보험','활성')").lastrowid
    i_uniq = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('R105유일보험','활성')").lastrowid
    # 레거시 정산 — 백필이 손대지 않아 insurer_id 가 계속 NULL 인 상태를 흉내낸다.
    sid_dup = conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_name,amount,fee,payout,"
        "                        insurer_paid,created_at) "
        "VALUES(0,'R105-동명레거시','R105동명보험','R105업체',5000000,500000,4500000,'대기',?)",
        (DB.now(),)).lastrowid
    sid_uniq = conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,partner_name,amount,fee,payout,"
        "                        insurer_paid,created_at) "
        "VALUES(0,'R105-유일레거시','R105유일보험','R105업체',1000000,100000,900000,'대기',?)",
        (DB.now(),)).lastrowid
    conn.commit()

    def _idash(iid):
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["insurer_id"] = iid
        return c.get("/api/insurer/dashboard").get_json()

    j1 = _idash(i_dup1)
    j2 = _idash(i_dup2)
    ju = _idash(i_uniq)
    setts1 = [s["case_no"] for s in j1.get("settlements") or []]
    setts2 = [s["case_no"] for s in j2.get("settlements") or []]
    settsu = [s["case_no"] for s in ju.get("settlements") or []]
    chk("R105-동명레거시" not in setts1 and "R105-동명레거시" not in setts2,
        "★★★ 동명 보험사 둘 중 어느 쪽도 레거시 정산을 자기 것으로 못 본다"
        "(예전엔 둘 다 500만원을 봤다)",
        (setts1, setts2))
    chk("R105-유일레거시" in settsu,
        "STEP 이름이 유일한 보험사는 레거시 정산을 여전히 정상적으로 본다(과잉차단 아님)",
        settsu)

    def _tok(iid):
        c = A.app.test_client()
        _t = f"r105-{iid}-csrf"
        with c.session_transaction() as sess:
            sess["insurer_id"] = iid; sess["_csrf"] = _t
        return c, {"X-CSRF-Token": _t}

    c1, h1 = _tok(i_dup1)
    r1 = c1.post(f"/api/insurer/settlements/{sid_dup}/approve", headers=h1, json={})
    chk(r1.status_code == 404,
        "★★★ 동명 보험사 A는 그 레거시 정산에 완료승인을 할 수 없다"
        "(예전엔 200으로 통과 — 남의 기관 정산을 승인할 수 있었다)",
        (r1.status_code, r1.get_json()))
    c2, h2 = _tok(i_dup2)
    r2 = c2.post(f"/api/insurer/settlements/{sid_dup}/approve", headers=h2, json={})
    chk(r2.status_code == 404,
        "★★★ 동명 보험사 B도 마찬가지로 승인할 수 없다", (r2.status_code, r2.get_json()))
    cu, hu = _tok(i_uniq)
    ru = cu.post(f"/api/insurer/settlements/{sid_uniq}/approve", headers=hu, json={})
    chk(ru.status_code == 200,
        "STEP 이름이 유일한 보험사는 자기 레거시 정산을 정상적으로 승인할 수 있다(과잉차단 아님)",
        (ru.status_code, ru.get_data(as_text=True)[:200]))

    # ── [4] _insurer_statement 도 유일성 있는 레거시는 집계에 넣는다 ──────
    with A.app.test_request_context():
        ym = DB.now()[:7]
        stmt_dup = A._insurer_statement(conn, i_dup1, ym[:4], ym[5:7])
        stmt_uniq = A._insurer_statement(conn, i_uniq, ym[:4], ym[5:7])
        case_nos_dup = [x["case_no"] for x in stmt_dup["lines"]]
        case_nos_uniq = [x["case_no"] for x in stmt_uniq["lines"]]
    chk("R105-동명레거시" not in case_nos_dup,
        "★★ 명세서도 동명 보험사에겐 그 레거시 건을 안 보여준다", case_nos_dup)
    chk("R105-유일레거시" in case_nos_uniq,
        "★★ 명세서가 이제 유일한 이름의 레거시 정산은 정상적으로 담는다"
        "(예전엔 insurer_id 뿐이라 대시보드엔 보이는데 명세서엔 없었다)",
        case_nos_uniq)

    # ── [5] 담당 배정 — 실 경로가 감사이력을 찍는다 ───────────────────────
    admin = A.app.test_client()
    _atok = "r105-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _atok
    _ahdr = {"X-CSRF-Token": _atok}
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R105-C1','접수','가드레일','서울',0)").lastrowid
    conn.commit()
    r5 = admin.patch(f"/api/cases/{cid}", headers=_ahdr, json={"manager": "홍길동"})
    chk(r5.status_code == 200, "STEP 담당 배정 자체는 200 이다", (r5.status_code, r5.get_data(as_text=True)[:200]))
    row = conn.execute(
        "SELECT manager, manager_assigned_by, manager_assigned_at FROM cases WHERE id=?",
        (cid,)).fetchone()
    #  [라운드170] actor() 가 표시이름 뒤에 로그인 계정을 함께 남기도록 바뀌었다
    #  (admins.name 유일성 제약이 없어 감사로그 행위자를 위조할 수 있었다) —
    #  이 테스트의 admin 세션(admin_name='검증', admin='admin')이 그대로 반영된다.
    chk(row["manager"] == "홍길동" and row["manager_assigned_by"] == "검증(admin)"
        and bool(row["manager_assigned_at"]),
        "★★★ 실 경로로 배정해도 이제 누가·언제가 함께 찍힌다(예전엔 전부 NULL)",
        dict(row))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드105 서버측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
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
