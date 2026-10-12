# -*- coding: utf-8 -*-
"""스캔 595라운드 회귀 — 자릿수만 비정상으로 큰 정수 입력이 sqlite3 바인딩에서
OverflowError로 새어 "없는 자원"(정상 404/응답)이 아니라 500 SERVER_ERROR가 되던
결함. 같은 근본원인, 서로 다른 두 유입구에서 확인해 각자의 단일 공유 지점에서 고쳤다.

■ 결함 A — <int:...> 라우트 변환기(URL 경로 세그먼트, 120곳)
  이 앱은 사건·사진·협력사·입찰 등 120곳의 라우트가 `<int:cid>` 류를 그대로 받아
  원시 SQL(`WHERE id=?`)에 바인딩한다. sqlite3는 자기 INTEGER 컬럼의 실제 상한
  (부호있는 8바이트, 2**63-1)을 넘는 파이썬 int를 바인딩하면 OverflowError를
  던지는데, Flask/Werkzeug의 기본 IntegerConverter는 자릿수 상한이 없어(`\\d+`
  정규식만 검사) 그 값을 그대로 뷰 함수까지 통과시킨다. 그 결과 "없는 id"(정상
  404)와 "자릿수만 비정상으로 큰 id"가 같은 경로에서 전혀 다르게 샌다 — 후자는
  전역 예외핸들러(450라운드)까지 올라가 500 SERVER_ERROR + 매번 전체
  스택트레이스 로그를 남긴다. 정보 유출은 없지만(전역 핸들러가 이미 참조번호만
  노출), 스캐너·봇의 무작위 대입이나 연동 스크립트의 자릿수 오타만으로도 실서비스
  로그가 이 소음으로 채워지고 모니터링·알림이 오작동한다.

  고침: 라우트마다 `<int(max=...):x>`를 120번 반복하는 대신, 이 앱의 기본 int
  변환기 자체(`app.url_map.converters["int"]`)를 sqlite 상한(2**63-1)으로 막는
  `_BoundedIntConverter`로 교체한다(app.py, Flask 앱 생성 직후 — 라우트 등록보다
  반드시 먼저 와야 한다. Werkzeug는 Rule을 라우팅 맵에 추가하는 시점에 변환기를
  인스턴스화해 그 Rule에 고정시키므로, 이 교체가 첫 `@app.get(...)`보다 뒤에
  있으면 이미 등록된 라우트에는 적용되지 않는다). 실제 자동증가 id는 이 상한
  근처에도 못 가므로 정상 동작에는 영향이 없다.

■ 결함 B — insurer_id 쿼리스트링(같은 근본원인, URL 경로가 아니라 못 걸러짐)
  /api/insurer-statement·-export 두 라우트는 `int(request.args.get("insurer_id"))`
  가 성공하면 그대로 믿는다 — 파이썬 int()는 자릿수 제한이 없어(오버플로 없음)
  자릿수만 비정상으로 큰 쿼리스트링 값도 통과하고, 두 라우트가 공유하는
  `_insurer_statement()` 안의 SELECT 바인딩에서야 결함 A와 같은 OverflowError가
  터진다. 결함 A의 라우트 변환기는 URL **경로**만 검사하므로 쿼리스트링은
  못 막는다 — 같은 병, 다른 유입구.

  고침: 두 라우트가 공유하는 유일한 지점인 `_insurer_statement()` 안에서
  sqlite에 안전하게 바인딩할 수 없는 insurer_id는 -1(실제 id와 절대 안 겹침)로
  치환한다 — 이 함수는 이미 "존재하지 않는 id"(ins=None)를 정상 처리하므로
  호출부·반환 모양을 바꿀 필요가 없다.

  [1] 소스 확인 — 두 변환기/함수 수정이 실제로 있고, 순서 불변조건(변환기 등록이
      첫 라우트보다 앞선다)이 지켜진다.
  [2] 실제 Flask 앱(결함 A) — 서로 다른 두 라우트(`/api/photos/<id>/file`,
      `/api/cases/<id>/detail`)에서 자릿수만 큰 id가 500이 아니라 404로 응답한다
      (핵심 재현 — 정상 out-of-range 대조군과 같은 상태코드 계열).
  [3] 되돌림-증명(결함 A) — 이미 등록된 Rule에 고정된 변환기 인스턴스의 `.max`
      속성만 메모리에서 임시로 None으로 되돌려(몽키패치, 디스크 무수정) 옛(취약)
      동작 — 500 SERVER_ERROR — 이 실제 뷰·DB 경로를 통해 재현됨을 확인한 뒤 원복.
  [4] 회귀 없음(결함 A) — 실제로 존재하는 사건을 정상 id로 조회하면 그대로
      200이 오고, 경계값 id=0도 평소처럼 "없음" 404로 정상 라우팅된다.
  [5] 경계 정확성(결함 A) — sqlite 상한값(2**63-1) 자체는 정상 라우팅되고(그냥
      없는 자원 404), 상한+1은 라우터 단계에서 걸러진다(NOT_FOUND).
  [6] 실제 Flask 앱(결함 B) — 두 라우트 모두 huge insurer_id로 200(빈 명세)을
      받는다 — "존재하지 않는 보험사"와 똑같이 정상 처리된다(핵심 재현).
  [7] 되돌림-증명(결함 B) — `_insurer_statement`를 새 가드가 빠진 옛 동작을
      그대로 재현하는 대역으로 몽키패치(디스크 무수정)해, 같은 huge
      insurer_id가 실제로 500 SERVER_ERROR를 냄을 확인한 뒤 원복.
  [8] 회귀 없음(결함 B) — 실제 존재하는 보험사는 정상 insurer_id로 여전히
      올바른 명세(그 보험사 이름 포함)를 받는다.
  [9] 경계 정확성(결함 B) — insurer_id=0·음수는 (기존 그대로) 라우트 자체가
      "보험사를 선택해 주세요" 400으로 막고, sqlite 상한값 자체는 정상 처리된다.

      python test_scan_round595_fixes.py
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


print("=" * 72)
print("  스캔 595라운드 회귀 — 자릿수만 비정상으로 큰 정수 → OverflowError→500 (2곳)")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
APP_SRC = io.open(os.path.join(HERE, "app.py"), encoding="utf-8").read()

i_flask = APP_SRC.index('from werkzeug.routing import IntegerConverter')
i_class = APP_SRC.index("class _BoundedIntConverter(IntegerConverter):")
i_assign = APP_SRC.index('app.url_map.converters["int"] = _BoundedIntConverter')
i_first_route = APP_SRC.index('@app.get("/api/version")')

chk(i_flask > 0, "★★★★★ werkzeug.routing.IntegerConverter를 import한다")
chk("kwargs.setdefault(\"max\", 2**63 - 1)" in APP_SRC,
    "★★★★★ 결함A — 새 변환기가 sqlite INTEGER 상한(2**63-1)을 기본값으로 강제한다")
chk(i_assign > i_class,
    "STEP 변환기 클래스 정의 뒤에 등록 대입이 온다(순서)")
chk(i_assign < i_first_route,
    "★★★★★ 변환기 등록이 첫 라우트 데코레이터보다 앞선다"
    "(Werkzeug는 Rule 추가 시점에 변환기를 인스턴스화해 고정하므로, "
    "뒤에 있으면 이미 등록된 라우트에는 효과가 없다)")

i_fn = APP_SRC.index("def _insurer_statement(")
i_fn_end = APP_SRC.index("\n\n\n", i_fn)
FN_SRC = APP_SRC[i_fn:i_fn_end]
chk("insurer_id = -1" in FN_SRC,
    "★★★★★ 결함B — _insurer_statement가 바인딩 불가능한 insurer_id를 -1로 치환한다")
chk("0 < insurer_id <= 2**63 - 1" in FN_SRC,
    "STEP 결함B 가드 조건이 같은 sqlite 상한(2**63-1)을 쓴다(결함A와 상수 통일)")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[9] 실제 Flask 앱 실행")
# ══════════════════════════════════════════════════════════════
_tmpdir = tempfile.mkdtemp(prefix="round595_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    SQLITE_INT_MAX = 2**63 - 1
    HUGE = int("9" * 40)          # 자릿수만 비정상으로 큰 값 — sqlite 상한을 한참 넘는다

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r595admin','x','검증','최고관리자')")
    real_cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,address,created_at) "
        "VALUES('R595-CASE-01','접수','누수·배관·설비','서울','서울 어딘가',datetime('now'))"
    ).lastrowid
    conn.commit()

    admin = A.app.test_client()
    with admin.session_transaction() as sess:
        sess["admin"] = "r595admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"

    # ── [2] 핵심 재현 — 서로 다른 두 <int:...> 라우트 모두 huge id에 404를 준다 ──
    r_photo = admin.get(f"/api/photos/{HUGE}/file")
    chk(r_photo.status_code == 404,
        "★★★★★ /api/photos/<huge>/file — 자릿수만 큰 id가 500이 아니라 404",
        (r_photo.status_code, r_photo.get_json()))
    chk((r_photo.get_json() or {}).get("code") == "NOT_FOUND",
        "STEP 라우터 단계에서 걸러진 표준 404(NOT_FOUND)다(뷰 코드는 실행되지 않음)",
        r_photo.get_json())

    r_case = admin.get(f"/api/cases/{HUGE}/detail")
    chk(r_case.status_code == 404,
        "★★★★★ /api/cases/<huge>/detail — 자릿수만 큰 id가 500이 아니라 404"
        "(120곳이 공유하는 한 지점 수정이 서로 다른 라우트에도 함께 적용됨을 확인)",
        (r_case.status_code, r_case.get_json()))

    # ── [3] 되돌림-증명 — 이미 바인딩된 Rule의 변환기 인스턴스만 메모리에서 되돌린다 ──
    def _bound_converter_for(endpoint, varname):
        for rule in A.app.url_map.iter_rules(endpoint):
            return rule._converters[varname]
        raise LookupError(endpoint)

    conv = _bound_converter_for("api_photo_file", "pid")
    chk(conv.max == SQLITE_INT_MAX,
        "STEP 되돌리기 전 전제 확인 — 실제 바인딩된 변환기가 sqlite 상한을 갖고 있다",
        conv.max)
    _orig_max = conv.max
    conv.max = None   # 옛(패치 전) 무제한 변환기와 동일 효과 — 오직 이 라우트, 이 프로세스 메모리에서만
    #  ⚠⚠ [라운드596] 이 자리도 더 이상 500으로 새지 않는다 — round596이 전역
    #    예외핸들러(err_500)에 OverflowError→400 분기를 추가해, 라우트 변환기의
    #    상한(위에서 뺀 것)이 없어도 전역 방어가 받아낸다(방어심층 — 정상). 이
    #    테스트가 여전히 증명하는 것은 "이 변환기가 없으면 500이 된다"가 아니라
    #    "이 변환기가 없으면 (전역 방어가 대신 받아도) 라우터 단계의 깔끔한 404가
    #    아니라 뷰까지 들어갔다 나온 제네릭 400으로 떨어진다"이다.
    try:
        r_old = admin.get(f"/api/photos/{HUGE}/file")
        chk(r_old.status_code == 400 and (r_old.get_json() or {}).get("code") == "BAD_INPUT",
            "★★★★★ 상한을 되돌리면 huge id가 500이 아니라 round596의 전역 방어"
            "(400/BAD_INPUT)로 받아진다 — 라우터 변환기가 주는 '뷰 진입 전 404'라는 "
            "더 깔끔한 결과를 잃는다는 것을 이 테스트가 여전히 증명함(OverflowError가 "
            "뷰의 SELECT ... WHERE id=? 바인딩에서 실제로 발생)", r_old.get_json())
    finally:
        conv.max = _orig_max   # 원복 — 디스크 파일은 애초에 건드리지 않았다

    r_restored = admin.get(f"/api/photos/{HUGE}/file")
    chk(r_restored.status_code == 404,
        "STEP 원복 후에는 다시 404로 돌아온다(테스트가 전역 상태를 오염시키지 않음)",
        r_restored.status_code)

    # ── [4] 회귀 없음 — 실제 존재하는 정상 id·경계값 id=0은 그대로 동작한다 ──
    r_real = admin.get(f"/api/cases/{real_cid}/detail")
    chk(r_real.status_code == 200 and (r_real.get_json() or {}).get("case", {}).get("case_no")
        == "R595-CASE-01",
        "★★★★★ 실제 존재하는 사건은 정상 id로 여전히 200을 받는다(과잉 변경 아님)",
        r_real.get_json())

    r_zero = admin.get("/api/cases/0/detail")
    chk(r_zero.status_code == 404 and (r_zero.get_json() or {}).get("error") != "요청하신 주소를 찾을 수 없습니다.",
        "STEP id=0(경계값, 존재하지 않음)은 라우팅 자체는 통과하고 "
        "뷰의 '사건을 찾을 수 없습니다' 404로 응답한다(변환기가 막지 않음)",
        r_zero.get_json())

    # ── [5] 경계 정확성 — sqlite 상한 자체는 정상 라우팅, 상한+1은 라우터가 막는다 ──
    r_at_ceiling = admin.get(f"/api/cases/{SQLITE_INT_MAX}/detail")
    chk(r_at_ceiling.status_code == 404
        and (r_at_ceiling.get_json() or {}).get("code") != "NOT_FOUND",
        "★★★ sqlite 상한값(2**63-1) 자체는 라우팅을 통과해 뷰까지 도달한다"
        "(상한이 실제보다 더 taut하게 걸리지 않았다)", r_at_ceiling.get_json())

    r_over_ceiling = admin.get(f"/api/cases/{SQLITE_INT_MAX + 1}/detail")
    chk(r_over_ceiling.status_code == 404
        and (r_over_ceiling.get_json() or {}).get("code") == "NOT_FOUND",
        "★★★ 상한+1은 라우터 단계에서 걸러진다(뷰가 실행되지 않는 표준 404)",
        r_over_ceiling.get_json())

    # ── [6] 핵심 재현(결함B) — huge insurer_id도 500이 아니라 "없음"과 같은 200 ──
    real_iid = conn.execute("INSERT INTO insurers(name) VALUES('R595보험')").lastrowid
    conn.commit()

    r_ins = admin.get(f"/api/insurer-statement?insurer_id={HUGE}&year=2026&month=9")
    chk(r_ins.status_code == 200 and (r_ins.get_json() or {}).get("insurer_name") == "-",
        "★★★★★ /api/insurer-statement?insurer_id=<huge> — 500이 아니라 "
        "'존재하지 않는 보험사'와 동일하게 200으로 처리된다", r_ins.get_json())

    r_ins_exp = admin.get(f"/api/insurer-statement/export?insurer_id={HUGE}&year=2026&month=9")
    chk(r_ins_exp.status_code == 200,
        "★★★★★ /api/insurer-statement/export?insurer_id=<huge> — 같은 공유 지점을 "
        "타는 두 번째 라우트도 함께 방어된다(엑셀 응답 200)", r_ins_exp.status_code)

    # ── [7] 되돌림-증명(결함B) — _insurer_statement를 새 가드 없는 대역으로 몽키패치 ──
    def _prefix_insurer_statement(conn, insurer_id, year, month):
        """라운드595 가드(insurer_id 상한 치환)를 뺀, 수정 전과 동일한 크래시 지점만
        재현하는 최소 대역 — 실제 옛 코드가 그랬듯 SELECT 바인딩에서 그대로 죽는다."""
        ym = f"{int(year):04d}-{int(month):02d}"
        ins = A.one(conn.execute("SELECT id, name FROM insurers WHERE id=?", (insurer_id,)))
        return {"insurer_id": insurer_id, "insurer_name": ins["name"] if ins else "-",
                "year": int(year), "month": int(month), "ym": ym, "lines": [], "totals": {}}

    #  ⚠⚠ [라운드596] 이 자리는 더 이상 500으로 새지 않는다 — round596이 전역
    #    예외핸들러(err_500)에 OverflowError→400 분기를 추가해, _insurer_statement
    #    자신의 방어(위에서 뺀 것)가 없어도 전역 방어가 받아낸다(방어심층 — 정상).
    #    이 테스트가 여전히 증명하는 것은 바뀌었다 — "이 함수의 방어가 없으면
    #    500이 된다"가 아니라 "이 함수의 방어가 없으면 (전역 방어가 대신 받아도)
    #    이 라우트만의 값어치 있는 결과(200 + '존재하지 않는 보험사' — 명세서를
    #    비워서라도 정상 응답하는 것)를 잃고 제네릭 400으로 떨어진다"이다.
    _orig_fn = A._insurer_statement
    A._insurer_statement = _prefix_insurer_statement
    try:
        r_old_ins = admin.get(f"/api/insurer-statement?insurer_id={HUGE}&year=2026&month=9")
        chk(r_old_ins.status_code == 400
            and (r_old_ins.get_json() or {}).get("code") == "BAD_INPUT",
            "★★★★★ 새 가드를 빼면 huge insurer_id가 500이 아니라 round596의 전역 "
            "방어(400/BAD_INPUT)로 받아진다 — 이 함수 고유의 '200 + 존재하지 않는 "
            "보험사'라는 더 나은 결과를 잃는다는 것을 이 테스트가 여전히 증명함 "
            "(OverflowError가 SELECT ... WHERE id=? 바인딩에서 실제로 발생)",
            r_old_ins.get_json())
    finally:
        A._insurer_statement = _orig_fn   # 원복 — 디스크 파일은 애초에 건드리지 않았다

    r_ins_restored = admin.get(f"/api/insurer-statement?insurer_id={HUGE}&year=2026&month=9")
    chk(r_ins_restored.status_code == 200,
        "STEP 원복 후에는 다시 200(정상 처리)으로 돌아온다", r_ins_restored.status_code)

    # ── [8] 회귀 없음(결함B) — 실제 존재하는 보험사는 정상 명세를 그대로 받는다 ──
    r_real_ins = admin.get(f"/api/insurer-statement?insurer_id={real_iid}&year=2026&month=9")
    chk(r_real_ins.status_code == 200 and (r_real_ins.get_json() or {}).get("insurer_name") == "R595보험",
        "★★★★★ 실제 존재하는 보험사는 정상 insurer_id로 여전히 올바른 명세를 받는다"
        "(과잉 변경 아님)", r_real_ins.get_json())

    # ── [9] 경계 정확성(결함B) — 0/음수는 기존 그대로 400, sqlite 상한 자체는 통과 ──
    r_ins_zero = admin.get("/api/insurer-statement?insurer_id=0&year=2026&month=9")
    chk(r_ins_zero.status_code == 400,
        "STEP insurer_id=0(기존부터 있던 '선택 안 함' 검사)은 그대로 400 — "
        "이번 수정이 기존 검증을 대체하지 않는다", r_ins_zero.get_json())

    #  음수는 0과 다르다 — `if not iid` 검사(라우트)를 통과해 _insurer_statement 까지
    #  들어간다. 자릿수만 큰 음수도 보통 음수(sqlite에 안전하게 바인딩되는 -5 등)와
    #  **똑같이** "존재하지 않는 보험사" 200으로 처리돼야 한다(가드가 이 경우에만
    #  다른 상태코드를 새로 만들면 안 된다).
    r_ins_small_neg = admin.get("/api/insurer-statement?insurer_id=-5&year=2026&month=9")
    r_ins_huge_neg = admin.get(f"/api/insurer-statement?insurer_id=-{HUGE}&year=2026&month=9")
    chk(r_ins_small_neg.status_code == 200 and r_ins_huge_neg.status_code == 200
        and r_ins_small_neg.get_json() == r_ins_huge_neg.get_json(),
        "STEP 자릿수만 큰 음수 insurer_id도 sqlite에 안전한 보통 음수(-5)와 "
        "동일하게 200(존재하지 않는 보험사)으로 처리된다(가드가 새 상태코드를 "
        "만들지 않는다)", (r_ins_small_neg.status_code, r_ins_huge_neg.status_code))

    r_ins_ceiling = admin.get(f"/api/insurer-statement?insurer_id={SQLITE_INT_MAX}&year=2026&month=9")
    chk(r_ins_ceiling.status_code == 200,
        "STEP sqlite 상한값(2**63-1) 자체는 '가짜 huge'로 오판되지 않고 정상 처리된다"
        "(상한이 실제보다 더 taut하게 걸리지 않았다)", r_ins_ceiling.get_json())

    conn.close()

except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]~[5] 실제 앱 재현 준비/실행", f"{type(e).__name__}: {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
