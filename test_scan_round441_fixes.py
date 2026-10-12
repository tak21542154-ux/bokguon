# -*- coding: utf-8 -*-
"""스캔 441라운드 회귀 — /api/insurer/defects·/api/partner/defects 의 SELECT *
   스키마드리프트 위험, 2건. 각도1(관리자 내부메모 노출) 조사 중 부수 발견 —
   원래 질문(memos·contact_note 등 진짜 관리자 전용 필드가 협력사·보험사에
   샌다)은 클린이었지만, 형제 라우트 api_insurer_bids(라운드422가 이미 같은
   유형을 bids 서브쿼리에서 고침)와 같은 패턴이 defects 목록 두 곳에는 아직
   남아 있었다.

   `SELECT * FROM defects ...` → `jsonify(data)` 직결이라, 지금은 defects에
   민감 컬럼이 없어(직접 확인: 27개 컬럼 전부 비민감) 실제 유출은 없지만,
   나중에 관리자 전용 컬럼(예: 내부 협상메모)이 이 테이블에 추가되는 순간
   이 두 자리만 조용히 새는 스키마드리프트 구조였다.

   고침: 현재 컬럼 27개(기본 23 + 마이그레이션 4: dispute_reason·
   disputed_at·dispute_resolved_at·is_demo) 전부를 그대로 나열해 동작은
   완전히 똑같이 유지하면서 화이트리스트로 명시(제거된 필드 없음) — 라운드
   422가 세운 것과 완전히 같은 패턴, 새 로직 불필요, 트레이드오프 없는
   "그냥 고치면 되는 것".

   ⚠ 각도1의 원래 질문(memos·contact_note·webhook_secret·api_key_hash 등
   진짜 관리자 전용 필드 노출) 자체는 정밀조사 Agent가 실측(61/61)으로
   이미 클린 확인했고 코드 변경도 없어 이 파일이 별도로 재확인하지 않는다.
   각도2(검색/필터 SQL 조합)도 클린(사용자 제어 ORDER BY 없음, LIKE 이스케이프
   실증, 인젝션 페이로드 무해)이라 코드 변경 없음 — 이 파일 범위 밖.
   ⚠ cases 테이블에도 같은 유형(SELECT c.* 무화이트리스트)이 보험사 쪽
   3곳(dashboard·case detail·bids)에서 추가로 발견됐으나, cases는 37개+
   컬럼에 프론트엔드 소비처가 훨씬 많아 안전하게 좁히려면 별도의 전용
   라운드가 필요 — 이번 라운드 범위 밖으로 분류, 다음 라운드 후보로 기록.

   ⚠⚠ [라운드622] [4] 탐지력 증명을 옛 세대(app.py를 실제로 디스크에 써넣고
   `python -c`서브프로세스로 재현한 뒤 복원)에서 안전한 인메모리 기법으로
   이관한다. api_insurer_defects()는 단일 라우트 핸들러고 다른 함수가
   이름으로 부르지 않으므로(app.py 안 유일 언급은 형제 함수 주석뿐), 되돌린
   본문을 exec로 독립 사본 네임스페이스에 재구성해 A.app.view_functions
   딕셔너리 항목만 잠깐 치환한다 — 진짜 app.py 파일은 전혀 안 쓴다. 두
   시나리오(되돌림·새 코드)가 같은 프로세스·같은 스크래치 DB를 공유하므로
   ALTER TABLE 은 한 번만 하고, 시나리오마다 새 보험사 계정으로 격리한다.

       python test_scan_round441_fixes.py
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
print("  스캔 441라운드 회귀 — defects 목록 SELECT * 스키마드리프트")
print("=" * 72)

print("\n[1] 소스 확인")
_i0 = APP_SRC.index('def api_insurer_defects():')
_i1 = APP_SRC.index("\n@app.", _i0)
_insurer_body = APP_SRC[_i0:_i1]
chk("SELECT * FROM defects" not in _insurer_body,
    "★★★★★ api_insurer_defects()가 더는 SELECT * 를 안 쓴다")
chk("dispute_reason" in _insurer_body and "is_demo" in _insurer_body,
    "  화이트리스트에 마이그레이션 컬럼(dispute_reason·is_demo 등)까지 포함됐다")

_j0 = APP_SRC.index('def api_partner_defects():')
_j1 = APP_SRC.index("\n@app.", _j0)
_partner_body = APP_SRC[_j0:_j1]
chk("SELECT * FROM defects" not in _partner_body,
    "★★★★★ api_partner_defects()가 더는 SELECT * 를 안 쓴다")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round441_")
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
    iid = conn.execute(
        "INSERT INTO insurers(name,login_id,password_hash,status) "
        "VALUES('R441보험사','r441ins',?, '활성')", (DB.hash_pw("Testpw123!"),)).lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,"
        "login_id,password_hash,created_at) "
        "VALUES('R441업체','시공사','활성','가드레일','서울',"
        "'r441par',?,?)", (DB.hash_pw("Testpw123!"), DB.now())).lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,partner_id,created_at) "
        "VALUES('R441-CASE','완료','가드레일','서울',?,?,?)", (iid, pid, DB.now())).lastrowid
    did = conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,insurer_id,partner_id,category,"
        "                    region,title,content,severity,status,cost_bearer,"
        "                    dispute_reason,created_at) "
        "VALUES('R441-DEF',?,?,?,?,'가드레일','서울','금이 감','상세','중대','접수',"
        "       '시행사','원인규명 필요',?)", (cid, "R441-CASE", iid, pid, DB.now())).lastrowid
    conn.commit()

    ins = A.app.test_client()
    r = ins.post("/api/insurer/login", json={"login_id": "r441ins", "password": "Testpw123!"})
    assert r.status_code == 200, r.get_data(as_text=True)
    par = A.app.test_client()
    r = par.post("/api/partner/login", json={"login_id": "r441par", "password": "Testpw123!"})
    assert r.status_code == 200, r.get_data(as_text=True)

    print("\n[3] 실행 — 새 화이트리스트로도 실제 컬럼값이 전부 그대로 온다(회귀 없음)")
    r_ins = ins.get("/api/insurer/defects")
    chk(r_ins.status_code == 200, "  GET /api/insurer/defects 200", r_ins.status_code)
    j_ins = r_ins.get_json()
    d_ins = next((x for x in j_ins if x["id"] == did), None)
    chk(d_ins is not None, "  방금 만든 하자가 목록에 있다")
    if d_ins:
        chk(d_ins.get("title") == "금이 감" and d_ins.get("severity") == "중대"
            and d_ins.get("dispute_reason") == "원인규명 필요" and d_ins.get("case_no") == "R441-CASE",
            "★★★★★ 기본컬럼·마이그레이션컬럼(dispute_reason) 전부 값이 그대로 온다"
            "(화이트리스트가 실제 필드를 빠뜨리지 않았다)", d_ins)

    r_par = par.get("/api/partner/defects")
    chk(r_par.status_code == 200, "  GET /api/partner/defects 200", r_par.status_code)
    j_par = r_par.get_json()
    d_par = next((x for x in j_par if x["id"] == did), None)
    chk(d_par is not None and d_par.get("title") == "금이 감",
        "  협력사 쪽도 동일하게 회귀 없음", d_par)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[4] 탐지력 증명 — 미래에 민감 컬럼이 추가되면 새 코드는 막고, 옛 코드는 샌다")
# ------------------------------------------------------------
SECRET_MARKER = "R441_SECRET_INTERNAL_NOTE_9f3a"

try:
    NEW_SELECT = (
        "        \"SELECT id, defect_no, case_id, case_no, insurer, insurer_id, partner_id, \"\n"
        "        \"       partner_name, category, region, title, content, severity, reporter, \"\n"
        "        \"       reporter_type, status, assigned_at, due_date, resolved_at, resolution, \"\n"
        "        \"       cost_bearer, warranty_ok, created_at, dispute_reason, disputed_at, \"\n"
        "        \"       dispute_resolved_at, is_demo \"\n"
        "        \"FROM defects WHERE insurer_id=? AND COALESCE(is_demo,0)=0 \"\n"
    )
    OLD_SELECT = "        \"SELECT * FROM defects WHERE insurer_id=? AND COALESCE(is_demo,0)=0 \"\n"
    chk(APP_SRC.count(NEW_SELECT) == 1, "  (준비) 되돌리기 대상이 app.py에 유일하게 존재한다")
    chk(NEW_SELECT in _insurer_body, "  (준비) 대상 SELECT가 함수 본문 안에 있다(경계 확인)")
    REVERTED_BODY = _insurer_body.replace(NEW_SELECT, OLD_SELECT)
    assert REVERTED_BODY != _insurer_body, "되돌림 치환이 실제로 안 먹었다"

    #  두 시나리오(되돌림·새 코드)가 이 프로세스의 스크래치 DB를 공유하므로
    #  ALTER TABLE 은 한 번만 하고, 시나리오마다 새 보험사 계정으로 격리한다.
    _connx = DB.get_db()
    _connx.execute("ALTER TABLE defects ADD COLUMN admin_secret_note TEXT")
    _connx.commit(); _connx.close()

    def _seed_secret_insurer(tag):
        c = DB.get_db()
        iid_s = c.execute(
            "INSERT INTO insurers(name,login_id,password_hash,status) "
            f"VALUES('R441비밀보험{tag}','r441sec{tag}',?, '활성')",
            (DB.hash_pw("Testpw123!"),)).lastrowid
        c.execute(
            "INSERT INTO defects(defect_no,insurer_id,category,region,title,content,"
            "                    status,cost_bearer,admin_secret_note,created_at) "
            f"VALUES('R441-DEF{tag}',?,'가드레일','서울','금이 감','상세','접수','시행사',"
            "       ?,?)", (iid_s, SECRET_MARKER, DB.now()))
        c.commit(); c.close()
        cl = A.app.test_client()
        r = cl.post("/api/insurer/login",
                     json={"login_id": f"r441sec{tag}", "password": "Testpw123!"})
        assert r.status_code == 200, r.get_data(as_text=True)
        return cl

    #  (a) 되돌림 시나리오 — view_functions 딕셔너리 항목만 잠깐 치환
    _ns = dict(vars(A))
    exec(compile(REVERTED_BODY, "<round441_reverted_api_insurer_defects>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_fn = A.require_insurer(_ns["api_insurer_defects"])
    _orig_view = A.app.view_functions["api_insurer_defects"]
    A.app.view_functions["api_insurer_defects"] = old_fn
    try:
        cl_old = _seed_secret_insurer("old")
        r_old = cl_old.get("/api/insurer/defects")
        leaked_old = SECRET_MARKER in r_old.get_data(as_text=True)
    finally:
        A.app.view_functions["api_insurer_defects"] = _orig_view
    chk(leaked_old,
        "★★★★★ 옛 코드(SELECT *)는 미래에 추가된 민감 컬럼을 그대로 흘려보낸다"
        "(인과관계 직접증명)")

    #  (b) 새 코드(현재, 이미 원상태) 시나리오
    cl_new = _seed_secret_insurer("new")
    r_new = cl_new.get("/api/insurer/defects")
    leaked_new = SECRET_MARKER in r_new.get_data(as_text=True)
    chk(not leaked_new,
        "★★★★★ 새 코드(화이트리스트)는 같은 미래 컬럼을 막는다"
        "(이 회귀테스트의 탐지력 증명)")
    chk(A.app.view_functions["api_insurer_defects"] is _orig_view,
        "  되돌림-증명 뒤 view_functions가 원래 함수객체로 복원됐다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 탐지력 증명 실행", f"{type(e).__name__} {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(view_functions 딕셔너리 항목 임시치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
