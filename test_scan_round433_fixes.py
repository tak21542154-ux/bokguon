# -*- coding: utf-8 -*-
"""스캔 433라운드 회귀 — 하자 severity 검증 우회(평점 조작 벡터) +
   happy_calls 고아행 사각지대, 2건.

   정밀조사 Agent(각도1: 협력사 평점 계산, 각도2: 사건 하드삭제 캐스케이드)가
   발견:

   [1] api_defect_update()(app.py:14147-)의 severity 검증(라운드109가 추가)이
       바로 옆 형제 cost_bearer 와 다른 술어를 썼다 — `d.get("severity") and
       ...`(truthy)라 severity=""/null 이면 검증 자체가 스킵되고, 뒤이은
       범용 저장 루프는 `"severity" in d`(존재)만 보고 빈 값을 그대로 저장
       한다. `RATING_PENALTY.get(severity, 0.1)`(app.py:13917)이 빈 값에
       0.1('보통')을 조용히 적용해 '중대'(0.2) 하자의 평점 차감이 절반으로
       줄어드는 평점 조작 벡터가 된다(도달권한은 중간관리자 이상으로 제한돼
       있어 내부자/탈취계정 위협모델).

   [2] manage.py 의 CASE_CHILD_TABLES(cmd_check 고아탐지·cmd_prune_orphans
       정리가 공유하는 단일 목록, "점검과 정리가 같은 목록을 봐야 한다"는
       자기 주석까지 있음)에 happy_calls(case_id NOT NULL UNIQUE, db.py:802)
       가 빠져 있었다 — go-live(cmd_go_live)는 이 표를 조건 없이 통째로
       비워 우연히 사각지대를 피하지만, 사건 하나를 직접 SQL로 지우는
       경우(라운드158이 이미 "실제 사고"로 증언한 시나리오)엔 이 표만 고아로
       남아 check·prune-orphans 둘 다 못 잡고, partner_rating() 의 해피콜
       평균에 삭제된 사건의 점수가 영구히 남는다.

   고침: (a) severity 검증을 cost_bearer 와 완전히 같은 존재(presence)
   검사로 통일. (b) CASE_CHILD_TABLES 에 "happy_calls" 추가 — 형제 4곳
   (라운드158)과 완전히 같은 패턴, 새 로직 불필요. 둘 다 트레이드오프
   없는 "그냥 고치면 되는 것".

   ⚠⚠ [라운드623] 되돌림-증명 기법을 옛 세대(app.py/manage.py를 실제로
      디스크에 써넣고 서브프로세스를 새로 띄워 확인한 뒤 원본을 다시
      디스크에 써 복원)에서 두 가지 확립된 안전기법으로 이관한다.
      (a) api_defect_update()는 다른 함수가 맨이름으로 호출하지 않는 단일
      라우트 핸들러라, ast로 함수 본문 경계(데코레이터 제외)를 뽑아
      severity 조건 한 줄만 치환한 뒤 독립 사본 네임스페이스에 exec하고
      `A.app.view_functions["api_defect_update"]` 딕셔너리 항목만 잠깐
      바꿔치기한다(round491/499가 확립한 기법1+2). (b) manage.py의
      CASE_CHILD_TABLES는 cmd_check·cmd_prune_orphans 가 매 호출마다
      모듈 전역에서 새로 읽는 순수 튜플 상수라, `M.CASE_CHILD_TABLES` 값
      자체를 잠깐 옛 값(happy_calls 제외)으로 스왑하는 것만으로 충분하다
      (기법5). app.py도 manage.py도 이 테스트 실행 내내 디스크에 다시
      쓰이지 않고, 서브프로세스도 전혀 안 쓴다 — 이미 import된 모듈
      객체를 그대로 재사용한다.

       python test_scan_round433_fixes.py
"""
import ast
import contextlib as _cl
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(HERE, "app.py")
MANAGE_PATH = os.path.join(HERE, "manage.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def _ast_fn_src(src, fn_name):
    """ast로 함수의 정확한 경계(decorator 제외, def~마지막 줄)를 뽑는다.
    (round499가 확립한 헬퍼 — 함수 전체를 손으로 옮겨 적지 않아도 안전하게
    현재 소스에서 그대로 추출해 텍스트 치환 대상으로 쓸 수 있다.)"""
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            return "".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError(f"함수 {fn_name} 을 못 찾음")


APP_SRC = read("app.py")
MANAGE_SRC = read("manage.py")

print("=" * 72)
print("  스캔 433라운드 회귀 — severity 검증우회 + happy_calls 고아사각지대")
print("=" * 72)

print("\n[1] 소스 확인")
_i0 = APP_SRC.index("def api_defect_update(did):")
_i1 = APP_SRC.index("\n@app.", _i0 + 1)
_du_body = APP_SRC[_i0:_i1]
chk('if "severity" in d and d["severity"] not in SEVERITY_VALUES:' in _du_body,
    "★★★★★ api_defect_update() 의 severity 검증이 형제 cost_bearer 와 같은 "
    "존재(presence) 검사로 통일됐다")

_ci0 = MANAGE_SRC.index("CASE_CHILD_TABLES = (")
_ci1 = MANAGE_SRC.index("\n)", _ci0)
_case_block = MANAGE_SRC[_ci0:_ci1]
chk('"happy_calls"' in _case_block,
    "★★★★★ CASE_CHILD_TABLES 에 happy_calls 가 등록됐다")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round433_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A
    import manage as M

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','중간관리자')")
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,created_at) "
        "VALUES('R433업체','시공사','활성','가드레일','서울',?)", (DB.now(),)).lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,created_at) "
        "VALUES('R433-CASE','완료','가드레일','서울',?)", (DB.now(),)).lastrowid
    did = conn.execute(
        "INSERT INTO defects(defect_no,case_id,partner_id,title,severity,status,"
        "                    cost_bearer,created_at) "
        "VALUES('R433-DF1',?,?,'테스트 하자','중대','완료','시행사',?)",
        (cid, pid, DB.now())).lastrowid
    #  ⚠ partner_rating() 은 happy_calls 가 하나도 없으면 "평점 아직 없음"으로
    #    즉시 반환하고 defects 페널티 계산 자체를 안 한다(13906-13909) — 실제
    #    페널티 계산 경로를 타려면 해피콜이 최소 1건 있어야 한다.
    conn.execute(
        "INSERT INTO happy_calls(case_id,partner_id,score,created_at) "
        "VALUES(?,?,5,?)", (cid, pid, DB.now()))
    conn.commit()

    admin = A.app.test_client()
    _tok = "r433-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    hdr = {"X-CSRF-Token": _tok}

    print("\n[3] 실행 — severity='' 는 이제 cost_bearer 처럼 400 으로 거부된다")
    r1 = admin.patch(f"/api/defects/{did}", headers=hdr, json={"severity": ""})
    chk(r1.status_code == 400,
        "★★★★★ severity 빈 문자열이 400 으로 거부된다"
        "(고치기 전엔 200 으로 그대로 저장됐다)", (r1.status_code, r1.get_json()))

    r2 = admin.patch(f"/api/defects/{did}", headers=hdr, json={"severity": None})
    chk(r2.status_code == 400,
        "★★★★★ severity=null 도 400 으로 거부된다", (r2.status_code, r2.get_json()))

    _row = conn.execute("SELECT severity FROM defects WHERE id=?", (did,)).fetchone()
    chk(_row["severity"] == "중대",
        "★★★★ 거부된 요청으로 기존 값('중대')이 안 바뀌었다(회귀없음)", dict(_row))

    val, info = A.partner_rating(conn, pid)
    chk(info["penalty"] == 0.2,
        "★★★★★ 평점 차감이 여전히 '중대' 기준(0.2)으로 정확히 계산된다"
        "(고치기 전엔 우회 성공 시 0.1로 반토막났을 것)", info)

    print("\n[4] 실행 — happy_calls: 사건이 직접 SQL로 지워지면 이제 고아로 잡히고 정리된다")
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,created_at) "
        "VALUES('R433-CASE2','완료','가드레일','서울',?)", (DB.now(),)).lastrowid
    hcid = conn.execute(
        "INSERT INTO happy_calls(case_id,partner_id,score,created_at) "
        "VALUES(?,?,5,?)", (cid2, pid, DB.now())).lastrowid
    conn.execute("DELETE FROM cases WHERE id=?", (cid2,))
    conn.commit()

    def _alive(table, rid):
        c = DB.get_db()
        r = c.execute(f"SELECT COUNT(*) n FROM {table} WHERE id=?", (rid,)).fetchone()["n"]
        c.close()
        return r == 1

    chk(_alive("happy_calls", hcid),
        "  (사전조건) 사건이 지워진 뒤에도 happy_calls 행은 그대로 남아있다")

    buf = io.StringIO()
    with _cl.redirect_stdout(buf):
        M.cmd_check([])
    chk("고아" in buf.getvalue(),
        "★★★★★ cmd_check 가 이제 이 고아 happy_calls 행을 잡아낸다"
        "(고치기 전엔 목록에 없어 경고 없이 통과했다)", buf.getvalue()[-300:])

    rc = M.cmd_prune_orphans(["--yes"])
    chk(rc == 0, "  prune-orphans --yes 실행이 정상 종료한다", rc)
    chk(not _alive("happy_calls", hcid),
        "★★★★★ 고아가 된 happy_calls 행이 실제로 정리된다", None)

    # ============================================================
    print("\n[5] 되돌리기 — 옛 코드였다면 두 결함 다 재현되는가"
          " (뷰함수 딕셔너리 스왑 + 모듈상수 스왑, 디스크 미기록·서브프로세스 미사용)")
    # ------------------------------------------------------------
    NEW_SEVERITY = 'if "severity" in d and d["severity"] not in SEVERITY_VALUES:'
    OLD_SEVERITY = 'if d.get("severity") and d["severity"] not in SEVERITY_VALUES:'

    # (a) api_defect_update — 기법1+2: ast로 현재 본문을 뽑아 한 줄만 치환한 뒤
    #     독립 사본 네임스페이스에 exec, view_functions 딕셔너리 항목만 스왑.
    CURRENT_BODY = _ast_fn_src(APP_SRC, "api_defect_update")
    chk(CURRENT_BODY.count(NEW_SEVERITY) == 1,
        "  (준비) severity 되돌리기 대상이 함수 본문 안에 유일하게 있다")
    REVERTED_BODY = CURRENT_BODY.replace(NEW_SEVERITY, OLD_SEVERITY)
    chk(REVERTED_BODY != CURRENT_BODY, "  (준비) 되돌린 함수 본문이 실제로 달라졌다")

    _ns = dict(vars(A))
    exec(compile(REVERTED_BODY, "<round433_reverted_api_defect_update>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_defect_update = A.require_role("중간관리자")(_ns["api_defect_update"])
    _orig_view = A.app.view_functions["api_defect_update"]

    # (b) manage.py CASE_CHILD_TABLES — 기법5: 모듈 상수 값 자체를 스왑.
    _orig_case_child_tables = M.CASE_CHILD_TABLES
    chk("happy_calls" in _orig_case_child_tables,
        "  (준비) 현재 CASE_CHILD_TABLES에 happy_calls가 있다")
    OLD_CASE_CHILD_TABLES = tuple(t for t in _orig_case_child_tables if t != "happy_calls")
    chk("happy_calls" not in OLD_CASE_CHILD_TABLES,
        "  (준비) 되돌린 CASE_CHILD_TABLES에서 happy_calls가 빠졌다")

    A.app.view_functions["api_defect_update"] = old_defect_update
    M.CASE_CHILD_TABLES = OLD_CASE_CHILD_TABLES
    try:
        #  독립된 새 업체·사건·하자로 시나리오를 만들어 위 [3]의 판정(평점 0.2)과
        #  섞이지 않게 한다(원래 서브프로세스가 완전히 새 DB로 격리하던 것과 같은
        #  효과 — 같은 스크래치 DB 안에서 새 partner_id 로 데이터를 분리한다).
        pid_old = conn.execute(
            "INSERT INTO partners(name,partner_type,status,category,region,created_at) "
            "VALUES('R433업체(구코드)','시공사','활성','가드레일','서울',?)",
            (DB.now(),)).lastrowid
        cid_old = conn.execute(
            "INSERT INTO cases(case_no,status,category,region,created_at) "
            "VALUES('R433-CASE-OLD','완료','가드레일','서울',?)", (DB.now(),)).lastrowid
        did_old = conn.execute(
            "INSERT INTO defects(defect_no,case_id,partner_id,title,severity,status,"
            "                    cost_bearer,created_at) "
            "VALUES('R433-DF-OLD',?,?,'테스트 하자(구코드)','중대','완료','시행사',?)",
            (cid_old, pid_old, DB.now())).lastrowid
        conn.execute(
            "INSERT INTO happy_calls(case_id,partner_id,score,created_at) "
            "VALUES(?,?,5,?)", (cid_old, pid_old, DB.now()))
        conn.commit()

        r_old = admin.patch(f"/api/defects/{did_old}", headers=hdr, json={"severity": ""})
        chk(r_old.status_code == 200,
            "★★★★★ 옛 코드(뷰함수 스왑)는 severity='' 를 200으로 그대로 받아들인다"
            "(인과관계 직접증명)", (r_old.status_code, r_old.get_json()))
        _val_old, info_old = A.partner_rating(conn, pid_old)
        chk(info_old["penalty"] == 0.1,
            "★★★★★ 옛 코드(뷰함수 스왑)에서는 '중대' 하자의 차감이 실제로 0.1로 "
            "반토막난다(인과관계 직접증명)", info_old)

        cid3 = conn.execute(
            "INSERT INTO cases(case_no,status,category,region,created_at) "
            "VALUES('R433-CASE3','완료','가드레일','서울',?)", (DB.now(),)).lastrowid
        hcid2 = conn.execute(
            "INSERT INTO happy_calls(case_id,partner_id,score,created_at) "
            "VALUES(?,?,5,?)", (cid3, pid, DB.now())).lastrowid
        conn.execute("DELETE FROM cases WHERE id=?", (cid3,))
        conn.commit()

        buf2 = io.StringIO()
        with _cl.redirect_stdout(buf2):
            M.cmd_check([])
        chk("고아" not in buf2.getvalue(),
            "★★★★★ 옛 CASE_CHILD_TABLES(모듈상수 스왑)의 cmd_check 는 이 고아 "
            "happy_calls 행을 전혀 언급하지 않는다(인과관계 직접증명)",
            buf2.getvalue()[-300:])
        rc2 = M.cmd_prune_orphans(["--yes"])
        chk(_alive("happy_calls", hcid2),
            "★★★★★ 옛 CASE_CHILD_TABLES 의 prune-orphans(rc="
            f"{rc2}) 로도 이 행은 안 지워지고 영구히 남는다(인과관계 직접증명)")
    finally:
        A.app.view_functions["api_defect_update"] = _orig_view
        M.CASE_CHILD_TABLES = _orig_case_child_tables

    chk(A.app.view_functions["api_defect_update"] is _orig_view,
        "  api_defect_update view_functions가 원래 함수객체로 복원됐다")
    chk(M.CASE_CHILD_TABLES == _orig_case_child_tables and "happy_calls" in M.CASE_CHILD_TABLES,
        "  CASE_CHILD_TABLES가 원래 값(happy_calls 포함)으로 복원됐다")

    #  원복 후 재확인 — 스왑이 안 샜는지(다시 새 코드처럼 400으로 막는지)
    cid_after = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,created_at) "
        "VALUES('R433-CASE-AFTER','완료','가드레일','서울',?)", (DB.now(),)).lastrowid
    did_after = conn.execute(
        "INSERT INTO defects(defect_no,case_id,partner_id,title,severity,status,"
        "                    cost_bearer,created_at) "
        "VALUES('R433-DF-AFTER',?,?,'테스트 하자(원복후)','중대','완료','시행사',?)",
        (cid_after, pid, DB.now())).lastrowid
    conn.commit()
    r_after = admin.patch(f"/api/defects/{did_after}", headers=hdr, json={"severity": ""})
    chk(r_after.status_code == 400,
        "★★★★ 원복 후에는 다시 severity='' 가 400으로 거부된다(바꿔치기가 안 샜다)",
        (r_after.status_code, r_after.get_json()))

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행/되돌리기", f"{type(e).__name__} {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다")
chk(io.open(MANAGE_PATH, encoding="utf-8").read() == MANAGE_SRC,
    "★★★★★ manage.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
