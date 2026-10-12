# -*- coding: utf-8 -*-
"""스캔 624라운드 회귀 — 사건 생성(_create_case, 보험사 포털·v1 API 공용)이
데모 발주처(insurers.is_demo=1)가 만든 사건에 cases.is_demo 표식을 안 붙이던
결함(직접조사 발견 — 하위위임 없음).

증거 사슬(전부 이 세션이 grep+Read로 직접 확인):
  · db.py 자신의 주석(1664행 부근) — "화면·집계 23곳이 bids.is_demo·
    dispatches.is_demo·field_agreements.is_demo·notifications.is_demo 를 보고
    데모를 거른다" — 이 전부와 _backfill_child_is_demo() 캐스케이드
    (db.py:1676-1734)는 오직 `cases.is_demo=1` 하나만을 진원지로 삼는다.
  · app.py의 _LIVE(17840행, "오늘 할 일" 대시보드 전용)도 `COALESCE(is_demo,0)=0`
    하나만 본다 — insurers.is_demo 는 안 본다. 그 밖에도 사건목록·하자·해피콜 등
    최소 12곳(grep "is_demo" app.py, insurer 무관 자리)이 같은 방식이다.
  · 그런데 고치기 전 _create_case()(app.py:4301-)의 INSERT INTO cases(...) 는
    is_demo 컬럼 자체가 목록에 없었다 — 스키마 기본값(db.py:1141, INTEGER
    DEFAULT 0)이 항상 그대로 박혔다. require_insurer/require_api_key 둘 다
    is_demo 를 안 보므로(실측 확인), 데모 발주처가 정상적으로 로그인해 만든
    사건은 발주처가 데모라는 사실과 무관하게 **항상 is_demo=0** 으로 만들어졌다.
  · 이 클래스의 문제를 이 세션 자신이 이미 세 각도에서 목격했다 —
    ① round528(app.py 2316-2330·9714-9723) 은 정확히 같은 이유로
      deliver_webhook()·api_insurer_webhook_test() 에 "발주처 자신의 is_demo
      도 본다"는 검사를 **따로** 추가했다(그 주석이 "지금 이 운영DB의 데모
      발주처 6곳" 이라고 현재형으로 실측까지 남겼다).
    ② manage.py의 DEMO_CASE_SQL(2667행)이 정확히 같은 이유로 `insurer_id IN
      (데모 발주처)` 를 OR 로 더한다 — 그 주석: "is_demo 표식만 보면 검증이
      만든 사건을 놓친다 — 테스트가 API로 만든 사건에는 표식이 안 붙기
      때문이다."
    ③ test_scan_round187/188/209_fixes.py 는 "표식 없는 유령 사건"을 원시
      SQL로 직접 만들어 청소도구(prune-orphans/go-live)가 그래도 자식표를
      찾아내는지를 검증해 왔다 — 즉 이 세션 전부가 "사건 생성 시점에 표식이
      안 붙을 수 있다"를 이미 알고 그 **증상**(웹훅 유출·유령 자식표)마다
      개별 방어를 쌓았을 뿐, **뿌리**(사건 생성 자체)는 한 번도 고치지
      않았다.
  · round187/188/209 의 "유령 사건" 시나리오는 전부 원시 INSERT INTO cases로
    직접 재현하므로(_create_case()를 거치지 않는다) 이번 수정과 겹치지 않고
    깨지지 않는다 — go-live 청소는 여전히 DEMO_CASE_SQL로 두 경로(직접
    is_demo=1 · insurer_id IN 데모발주처) 모두를 잡으므로 이 수정 이후에도
    안전망은 그대로 남는다(중복 방어일 뿐, 회귀 아님).

고침: _create_case() 안에서 insurers.is_demo 를 한 번 더 읽어(iid 는 이미
파라미터로 있다 — 새 조회 하나만 추가) 그 값을 그대로 cases.is_demo 에 심는다.
이후 db.py의 _backfill_child_is_demo() 캐스케이드와 화면·집계 23여 곳이 전부
cases.is_demo 만 보고 있으므로 이 한 곳만 고치면 자동으로 따라온다 — 새
헬퍼·새 컬럼·새 정책 없음, round528 이 이미 세운 원칙("발주처 자신의 is_demo
도 본다")을 사건 생성 시점으로 옮겼을 뿐이다.

되돌림-증명은 round416/422/492 가 확립한 안전패턴 그대로 — _create_case() 는
라우트가 아니라 api_insurer_case_create()·api_v1_case_create() 가 맨이름으로
부르는 평범한 모듈함수라(기법3), 되돌린 버전(같은 이름으로 재정의)을
A.__dict__ 자체에 직접 exec 해야 호출부의 전역조회가 그것을 보게 된다.
실제 app.py 파일은 전혀 안 건드리고, finally 에서 원래 함수객체로 되돌린다.

    python test_scan_round624_fixes.py
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
print("  스캔 624라운드 회귀 — 데모 발주처가 만든 사건에 is_demo 표식 누락")
print("=" * 72)

print("\n[1] 소스 확인")


def _py_fn_body(src, fn_name):
    """함수 본문 — 다음 def뿐 아니라 다음 라우트의 @app. 데코레이터가 먼저
    나오면 거기서 자른다(round610 정착 기법)."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


NEW_BLOCK = '''    #  ⚠⚠ [라운드624] 이 INSERT 는 is_demo 를 안 심어 스키마 기본값(db.py,
    #    INTEGER DEFAULT 0)이 항상 그대로 박혔다 — 데모 발주처(insurers.is_demo=1)가
    #    포털·API 로 정상적으로(require_insurer/require_api_key 둘 다 is_demo 를
    #    안 본다) 만든 사건도 항상 is_demo=0 으로 생성됐다. db.py 의
    #    _backfill_child_is_demo() 캐스케이드와 화면·집계 23여 곳(db.py 주석)은
    #    전부 cases.is_demo 하나만 보고 데모를 거르므로, 이 뿌리에서 안 심으면
    #    그 발주처의 사건·입찰·출동·통지·정산이 전부 "실적"처럼 새어 나간다 —
    #    round528 이 deliver_webhook()/api_insurer_webhook_test() 에, manage.py
    #    가 DEMO_CASE_SQL(insurer_id IN 데모발주처)에 각각 따로 심은 것과 같은
    #    "발주처 자신의 is_demo 도 본다" 원칙을 사건 생성 시점으로 옮긴다.
    _insurer_demo = 1 if (one(conn.execute(
        "SELECT is_demo FROM insurers WHERE id=?", (iid,))) or {}).get("is_demo") else 0
    cur = conn.execute(
        """INSERT INTO cases(case_no,insurer,insurer_id,category,region,address,urgent,is_composite,
           status,est_price,low_price,manager,warranty_months,note,source,intake_type,
           lat,lng,geo_src,created_at,status_at,is_demo)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (case_no, iname, iid, category, _region_in,
         _s(d.get("address"), 200),
         1 if _truthy(d.get("urgent")) else 0, is_comp,
         "접수" if no_photo else "입찰중", est, 0,
         _s(d.get("manager"), 40) or "보험사 등록", 24, note, source,
         "사진없음" if no_photo else "사진있음",
         lat, lng, "주소검색" if lat is not None else None, DB.now(), DB.now(),
         _insurer_demo),
    )'''

OLD_BLOCK = '''    cur = conn.execute(
        """INSERT INTO cases(case_no,insurer,insurer_id,category,region,address,urgent,is_composite,
           status,est_price,low_price,manager,warranty_months,note,source,intake_type,
           lat,lng,geo_src,created_at,status_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (case_no, iname, iid, category, _region_in,
         _s(d.get("address"), 200),
         1 if _truthy(d.get("urgent")) else 0, is_comp,
         "접수" if no_photo else "입찰중", est, 0,
         _s(d.get("manager"), 40) or "보험사 등록", 24, note, source,
         "사진없음" if no_photo else "사진있음",
         lat, lng, "주소검색" if lat is not None else None, DB.now(), DB.now()),
    )'''

_cc_body = _py_fn_body(APP_SRC, "_create_case")
chk(NEW_BLOCK in _cc_body,
    "★★★★★ _create_case() 가 발주처 자신의 is_demo 를 읽어 cases.is_demo 에 심는다")
chk(_cc_body.count(NEW_BLOCK) == 1, "  그 블록이 함수 안에 유일하다", _cc_body.count(NEW_BLOCK))
chk(OLD_BLOCK not in APP_SRC, "  (준비) 되돌림 대상 옛 INSERT는 지금 소스에 없다(대조군)")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round624_")
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
    conn.execute("INSERT INTO insurers(name,status,is_demo) VALUES('R624실보험사','활성',0)")
    real_iid = conn.execute("SELECT id FROM insurers WHERE name='R624실보험사'").fetchone()["id"]
    conn.execute("INSERT INTO insurers(name,status,is_demo) VALUES('R624데모보험사','활성',1)")
    demo_iid = conn.execute("SELECT id FROM insurers WHERE name='R624데모보험사'").fetchone()["id"]
    conn.commit()

    def _insurer_client(iid, name):
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["insurer_id"] = iid
            sess["insurer_login"] = "r624ins"
            sess["insurer_name"] = name
            sess["_csrf"] = "r624-csrf"
        return c

    def _post_case(iid, name, case_no):
        return _insurer_client(iid, name).post(
            "/api/insurer/cases",
            json={"category": "가드레일·방호울타리", "no_photo": True, "case_no": case_no},
            headers={"X-CSRF-Token": "r624-csrf"})

    print("\n[3] 실행 — 새 코드: 발주처 데모여부가 사건에 그대로 반영되는지")
    r_real = _post_case(real_iid, "R624실보험사", "R624-REAL")
    chk(r_real.status_code == 200, "  실보험사 사건 등록 200(회귀없음)", r_real.get_json())
    row_real = conn.execute("SELECT is_demo FROM cases WHERE case_no='R624-REAL'").fetchone()
    chk(row_real is not None and int(row_real["is_demo"] or 0) == 0,
        "  실보험사가 만든 사건은 is_demo=0(회귀없음)",
        dict(row_real) if row_real else None)

    r_demo = _post_case(demo_iid, "R624데모보험사", "R624-DEMO")
    chk(r_demo.status_code == 200, "  데모보험사 사건 등록 200", r_demo.get_json())
    row_demo = conn.execute("SELECT is_demo FROM cases WHERE case_no='R624-DEMO'").fetchone()
    chk(row_demo is not None and int(row_demo["is_demo"] or 0) == 1,
        "★★★★★ 새 코드: 데모 발주처가 만든 사건은 is_demo=1로 표식이 붙는다"
        "(이전엔 0 — 화면·집계 23여 곳과 _backfill_child_is_demo 캐스케이드가 "
        "전부 놓쳤다)", dict(row_demo) if row_demo else None)

    print("\n[4] 되돌림-증명 — _create_case()를 라운드624 이전으로 되돌리면 재현되는가"
          "(디스크 미기록)")
    #  ⚠ _create_case() 는 api_insurer_case_create()·api_v1_case_create() 가
    #    맨이름으로 부르는 평범한 모듈함수다(기법3) — 되돌린 본문을 같은
    #    이름으로 A.__dict__ 에 직접 exec 하면 그 호출부들의 전역조회가
    #    곧바로 옛 버전을 보게 된다. 실제 파일은 전혀 안 건드린다.
    reverted_body = _cc_body.replace(NEW_BLOCK, OLD_BLOCK, 1)
    chk(reverted_body != _cc_body and OLD_BLOCK in reverted_body,
        "  (준비) 되돌림 치환이 실제로 적용됐다")

    _orig_create_case = A._create_case
    exec(compile(reverted_body, "<round624_pre624_create_case>", "exec"), A.__dict__)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    chk(A._create_case is not _orig_create_case,
        "  (준비) A._create_case가 실제로 옛 버전 함수객체로 바뀌었다")
    try:
        r_demo2 = _post_case(demo_iid, "R624데모보험사", "R624-DEMO-OLD")
        chk(r_demo2.status_code == 200, "  (되돌림) 등록 자체는 여전히 200", r_demo2.get_json())
        row_old = conn.execute(
            "SELECT is_demo FROM cases WHERE case_no='R624-DEMO-OLD'").fetchone()
        chk(row_old is not None and int(row_old["is_demo"] or 0) == 0,
            "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림): 데모 발주처가 만든 "
            "사건인데도 is_demo=0으로 새는 '유령 사건'이 실제로 재현된다 — "
            "이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
            dict(row_old) if row_old else None)
    finally:
        A._create_case = _orig_create_case

    #  원복 확인 — 복원 후엔 같은 종류 요청이 다시 is_demo=1로 표식된다(바꿔치기가 안 샘)
    r_after = _post_case(demo_iid, "R624데모보험사", "R624-DEMO-AFTER")
    chk(r_after.status_code == 200, "  원복 후 재등록 200", r_after.get_json())
    row_after = conn.execute(
        "SELECT is_demo FROM cases WHERE case_no='R624-DEMO-AFTER'").fetchone()
    chk(row_after is not None and int(row_after["is_demo"] or 0) == 1,
        "  원복 후에는 다시 is_demo=1로 표식이 붙는다(바꿔치기가 안 샜다)",
        dict(row_after) if row_after else None)
    chk(A._create_case is _orig_create_case,
        "  A._create_case가 원래 함수객체로 복원됐다")

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
