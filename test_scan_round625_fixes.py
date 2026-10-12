# -*- coding: utf-8 -*-
"""스캔 625라운드 회귀 — 관리자수동 사건등록(api_case_create, POST /api/cases)이
데모 발주처(insurers.is_demo=1)가 만든 사건에 cases.is_demo 표식을 안 붙이던
결함(직접조사 발견 — 하위위임 없음). round624이 고친 형제 경로(_create_case,
보험사 포털·v1 API 공용)와 정확히 같은 결함 클래스가 사건을 만드는 **두 번째
문**에 그대로 남아 있었다 — round624 자신의 되돌림-증명 주석이 이미 "사건을
만드는 문이 둘이면 둘 다 걸어야 한다"(11913행 부근, 진행조회 링크 관련)고
스스로 적어 둔 원칙인데, 정작 is_demo 표식은 그 원칙을 안 따랐다.

증거(전부 이 세션이 grep+Read로 직접 확인):
  · app.py 전체에 `INSERT INTO cases(` 이 정확히 두 곳뿐이다(_create_case,
    api_case_create) — round624은 grep 없이 하나만 보고 그것만 고쳤다.
  · admin.js의 발주처 드롭다운(createCase, 1779행 부근: `insurers.map(i=>...)`)은
    is_demo 필터가 전혀 없이 전체 발주처를 그대로 보여준다 — 관리자가 데모
    발주처를 화면 그대로(정상 절차로) 골라도 아무 경고 없이 등록된다.
  · api_case_create 자신의 round594 주석이 이미 "require_admin 뿐이라 관리자
    세션으로 직접 호출(스크립트·curl 등)하면 insurer_id 없이도 부를 수 있다"고
    적어 둘 만큼, 이 라우트가 콘솔 화면 밖에서도 자유롭게 도달 가능함을
    스스로 문서화하고 있었다.
  · 고치기 전 이 경로의 INSERT는 is_demo 컬럼 자체가 목록에 없어 스키마
    기본값(db.py, INTEGER DEFAULT 0)이 항상 그대로 박혔다 — round624이 옮긴
    db.py의 _backfill_child_is_demo() 캐스케이드와 화면·집계 23여 곳은 전부
    cases.is_demo 하나만 보고 데모를 거르므로, 관리자수동으로 등록된 데모
    사건은 이 뿌리에서부터 "실적"처럼 새어 나간다.

고침: _create_case()(round624)와 정확히 같은 처방 — insurer 조회(두 갈래:
insurer_id 직접조회·NFKC 이름매칭) 시 is_demo 도 함께 읽어 cases.is_demo 에
그대로 심는다. 새 헬퍼·새 컬럼·새 정책 없음.

되돌림-증명은 round624/504/509/477이 세운 안전패턴 그대로 — api_case_create()는
_create_case()와 달리 라우트 자신이므로(기법1) view_functions 딕셔너리 스왑을
쓴다. 실제 app.py 파일은 전혀 안 건드리고, finally 에서 원래 함수객체로
되돌린다.

    python test_scan_round625_fixes.py
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
print("  스캔 625라운드 회귀 — 관리자수동 사건등록에 데모 발주처 is_demo 표식 누락")
print("=" * 72)

print("\n[1] 소스 확인")


def _py_fn_body(src, fn_name):
    """함수 본문 텍스트 — 다음 def뿐 아니라 다음 라우트의 @app. 데코레이터가
    먼저 나오면 거기서 자른다(round610/624 정착 기법)."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


chk(APP_SRC.count("INSERT INTO cases(") == 2,
    "  app.py 전체에 사건생성 INSERT 지점이 정확히 둘뿐이다(_create_case·api_case_create)"
    " — round624은 그중 하나만 고쳤었다", APP_SRC.count("INSERT INTO cases("))

_body = _py_fn_body(APP_SRC, "api_case_create")

SEL1_NEW = "SELECT id, name, is_demo FROM insurers WHERE id=?"
SEL1_OLD = "SELECT id, name FROM insurers WHERE id=?"
DEMO_LINE = '    _insurer_demo = 1 if row.get("is_demo") else 0\n'
NEW_INSERT = '''    cur = conn.execute(
        """INSERT INTO cases(case_no,insurer,insurer_id,category,region,address,urgent,is_composite,
                             status,est_price,low_price,manager,source,lat,lng,geo_src,created_at,status_at,
                             is_demo)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (d["case_no"], insurer_name, insurer_id, d["category"], _region_in, d.get("address", ""),
         1 if d.get("urgent") else 0, 1 if d.get("is_composite") else 0,
         "접수" if no_photo else "입찰중", est, 0,
         d.get("manager", "자동"), "관리자수동",
         lat, lng, "주소검색" if lat is not None else None, DB.now(), DB.now(),
         _insurer_demo),
    )'''
OLD_INSERT = '''    cur = conn.execute(
        """INSERT INTO cases(case_no,insurer,insurer_id,category,region,address,urgent,is_composite,
                             status,est_price,low_price,manager,source,lat,lng,geo_src,created_at,status_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (d["case_no"], insurer_name, insurer_id, d["category"], _region_in, d.get("address", ""),
         1 if d.get("urgent") else 0, 1 if d.get("is_composite") else 0,
         "접수" if no_photo else "입찰중", est, 0,
         d.get("manager", "자동"), "관리자수동",
         lat, lng, "주소검색" if lat is not None else None, DB.now(), DB.now()),
    )'''

chk(_body.count(SEL1_NEW) == 1,
    "  insurer_id 직접조회 SELECT가 is_demo도 함께 읽는다(유일)")
chk(_body.count("SELECT id, name, is_demo FROM insurers") == 2,
    "  두 SELECT(insurer_id 직접조회·NFKC 이름매칭) 모두 is_demo를 함께 읽는다",
    _body.count("SELECT id, name, is_demo FROM insurers"))
chk(_body.count(DEMO_LINE) == 1,
    "  _insurer_demo 계산 줄이 함수 안에 유일하게 있다")
chk(_body.count(NEW_INSERT) == 1,
    "  ★★★★★ INSERT 문이 is_demo 컬럼을 실제로 심는다(대체 지점 유일)")
chk(OLD_INSERT not in APP_SRC,
    "  (대조군) 되돌림 대상 옛 INSERT는 지금 소스에 없다")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round625_")
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
                 "VALUES('r625admin','x','검증','최고관리자')")
    conn.execute("INSERT INTO insurers(name,status,is_demo) VALUES('R625실보험사','활성',0)")
    real_iid = conn.execute("SELECT id FROM insurers WHERE name='R625실보험사'").fetchone()["id"]
    conn.execute("INSERT INTO insurers(name,status,is_demo) VALUES('R625데모보험사','활성',1)")
    demo_iid = conn.execute("SELECT id FROM insurers WHERE name='R625데모보험사'").fetchone()["id"]
    conn.commit()

    def _admin_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["admin"] = "r625admin"; sess["admin_role"] = "최고관리자"
            sess["admin_name"] = "검증"; sess["_csrf"] = "r625-csrf"
        return c

    def _post_case(iid, case_no):
        return _admin_client().post(
            "/api/cases",
            json={"case_no": case_no, "category": "가드레일·방호울타리",
                  "insurer_id": iid, "no_photo": True},
            headers={"X-CSRF-Token": "r625-csrf"})

    print("\n[3] 실행 — 새 코드: 관리자수동 등록도 발주처 데모여부가 사건에 반영되는지")
    r_real = _post_case(real_iid, "R625-REAL")
    chk(r_real.status_code == 200, "  실보험사 사건 등록 200(회귀없음)", r_real.get_json())
    row_real = conn.execute("SELECT is_demo FROM cases WHERE case_no='R625-REAL'").fetchone()
    chk(row_real is not None and int(row_real["is_demo"] or 0) == 0,
        "  실보험사가 관리자수동으로 만든 사건은 is_demo=0(회귀없음)",
        dict(row_real) if row_real else None)

    r_demo = _post_case(demo_iid, "R625-DEMO")
    chk(r_demo.status_code == 200, "  데모보험사 사건 등록 200", r_demo.get_json())
    row_demo = conn.execute("SELECT is_demo FROM cases WHERE case_no='R625-DEMO'").fetchone()
    chk(row_demo is not None and int(row_demo["is_demo"] or 0) == 1,
        "★★★★★ 새 코드: 관리자가 데모 발주처를 골라 관리자수동으로 등록해도 "
        "is_demo=1로 표식이 붙는다(이전엔 0 — admin.js 드롭다운이 데모를 안 가려도 "
        "서버가 스스로 표식한다)", dict(row_demo) if row_demo else None)

    print("\n[4] 되돌림-증명 — view_functions 스왑(기법1)으로 되돌리면 재현되는가"
          "(디스크 미기록)")
    broken_body = _body.replace(SEL1_NEW, SEL1_OLD, 1)
    broken_body = broken_body.replace(
        "SELECT id, name, is_demo FROM insurers", "SELECT id, name FROM insurers", 1)
    assert DEMO_LINE in broken_body, "되돌림 준비: DEMO_LINE을 못 찾음"
    broken_body = broken_body.replace(DEMO_LINE, "", 1)
    assert NEW_INSERT in broken_body, "되돌림 준비: NEW_INSERT를 못 찾음"
    broken_body = broken_body.replace(NEW_INSERT, OLD_INSERT, 1)
    chk(broken_body != _body, "  (준비) 되돌림 치환이 실제로 적용됐다")
    chk("_insurer_demo" not in broken_body,
        "  (준비) 되돌린 본문에 _insurer_demo 참조가 하나도 안 남았다(일관된 되돌림)")

    _ns = dict(vars(A))
    exec(compile(broken_body, "<round625_broken_api_case_create>", "exec"), _ns)  # noqa: S102 -- 실소스 그대로 추출, 디스크 미기록
    broken_view = A.require_admin(_ns["api_case_create"])

    _orig_view = A.app.view_functions["api_case_create"]
    A.app.view_functions["api_case_create"] = broken_view
    try:
        r_demo2 = _post_case(demo_iid, "R625-DEMO-OLD")
        chk(r_demo2.status_code == 200, "  (되돌림) 등록 자체는 여전히 200", r_demo2.get_json())
        row_old = conn.execute(
            "SELECT is_demo FROM cases WHERE case_no='R625-DEMO-OLD'").fetchone()
        chk(row_old is not None and int(row_old["is_demo"] or 0) == 0,
            "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림): 데모 발주처가 관리자수동으로 "
            "만든 사건인데도 is_demo=0으로 새는 '유령 사건'이 실제로 재현된다 — "
            "이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
            dict(row_old) if row_old else None)
    finally:
        A.app.view_functions["api_case_create"] = _orig_view
    chk(A.app.view_functions["api_case_create"] is _orig_view,
        "  (복원) api_case_create 라우트가 원래 함수객체로 복원됐다")

    #  원복 확인 — 복원 후엔 같은 종류 요청이 다시 is_demo=1로 표식된다(바꿔치기가 안 샘)
    r_after = _post_case(demo_iid, "R625-DEMO-AFTER")
    chk(r_after.status_code == 200, "  원복 후 재등록 200", r_after.get_json())
    row_after = conn.execute(
        "SELECT is_demo FROM cases WHERE case_no='R625-DEMO-AFTER'").fetchone()
    chk(row_after is not None and int(row_after["is_demo"] or 0) == 1,
        "  원복 후에는 다시 is_demo=1로 표식이 붙는다(바꿔치기가 안 샜다)",
        dict(row_after) if row_after else None)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py는 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
