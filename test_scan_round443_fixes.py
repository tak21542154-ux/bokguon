# -*- coding: utf-8 -*-
"""스캔 443라운드 회귀 — 보험사 쪽 cases SELECT * 스키마드리프트 3곳(백로그
   처리). 라운드441이 defects 목록 2곳을 고치면서 부수 발견하고 범위 밖으로
   미뤄 둔 항목 — cases 는 37개+(실측 60개) 컬럼에 소비처가 많아 별도 라운드가
   필요하다고 판단했던 그 작업이다.

   `api_insurer_dashboard()`(app.py:3415-)의 사건목록, `api_insurer_case_
   detail()`(9560-)의 사건상세, `api_insurer_bids()`(4220-)의 사건단건 조회
   셋 다 `SELECT c.*`/`SELECT *`로 cases 를 통째로 받아 화이트리스트 없이
   그대로 반환했다 — 라운드422(bids 서브쿼리)·라운드441(defects 목록)이
   이미 겪은 것과 똑같은 스키마드리프트 유형. 협력사 쪽 자매 라우트(api_
   partner_dashboard·api_partner_cases_detail)는 이미 명시적 화이트리스트라
   비대칭이었다.

   고침: cases 의 현재 컬럼 60개(실측: `PRAGMA table_info(cases)`) 전부를
   나열한 공용 상수 CASE_COLS_SQL(app.py, CASE_OPEN_SQL 바로 아래)을 신설해
   세 자리 모두 재사용 — 컬럼이 하나로 통일돼 있어 나중에 하나만 갱신되는
   사고를 막는다. auctions 와 JOIN하는 두 자리(dashboard·detail)는 id·
   status·low_price·created_at 등 이름이 겹쳐 c. 접두어가 필요해 상수 자체를
   c. 접두어 포함으로 정의했고, 원래 별칭이 없던 bids 자리는 FROM cases c
   로 별칭만 붙여 그대로 재사용했다. 동작은 완전히 동일 유지(제거된 필드
   없음 — victim_name/victim_phone/track_token_hash 등 민감해 보이는 필드도
   지금 이미 나가고 있던 그대로 유지, 그 값을 빼는 것은 이 하드닝과 무관한
   별도의 제품판단이라 이번엔 안 건드림). 트레이드오프 없는 "그냥 고치면
   되는 것".

   ⚠⚠ [라운드623] 되돌림-증명 기법을 옛 세대(app.py를 실제로 디스크에 써넣고
      서브프로세스를 새로 띄워 확인한 뒤 원본을 다시 디스크에 써 복원)에서
      기법5(단순 값 스왑)로 이관한다. CASE_COLS_SQL은 세 라우트 함수 본문
      안에서 f-string으로 매 호출마다 모듈 전역을 새로 조회하는 순수 문자열
      상수라(정의 시점에 함수 인자 기본값 등으로 캡처되지 않음) — exec도,
      view_functions 딕셔너리 스왑도 전혀 필요 없이 `A.CASE_COLS_SQL` 값
      자체를 잠깐 옛 값("c.*")으로 바꿔치기했다가 finally로 되돌리는 것만으로
      충분하다. app.py 파일은 이 테스트 실행 내내 단 한 번도 디스크에 다시
      쓰이지 않는다(서브프로세스도 전혀 안 씀 — 이미 이 프로세스에 import된
      A.app.test_client() 로 직접 호출).

       python test_scan_round443_fixes.py
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
print("  스캔 443라운드 회귀 — 보험사 cases SELECT * 스키마드리프트 3곳")
print("=" * 72)

print("\n[1] 소스 확인")
chk("CASE_COLS_SQL = (" in APP_SRC, "★★★★★ 공용 상수 CASE_COLS_SQL이 신설됐다")
chk('"c.victim_name, c.victim_phone"' in APP_SRC,
    "  상수에 민감해 보이는 필드(victim_name/phone)까지 전부 포함(제거된 필드 없음)")

_i0 = APP_SRC.index("def api_insurer_dashboard():")
_i1 = APP_SRC.index("\n@app.", _i0)
_dash_body = APP_SRC[_i0:_i1]
chk("SELECT c.*," not in _dash_body and "CASE_COLS_SQL" in _dash_body,
    "★★★★★ api_insurer_dashboard()가 더는 cases를 SELECT c.*로 안 받는다")

_j0 = APP_SRC.index("def api_insurer_case_detail(cid):")
_j1 = APP_SRC.index("\n@app.", _j0)
_detail_body = APP_SRC[_j0:_j1]
chk("SELECT c.*," not in _detail_body and "CASE_COLS_SQL" in _detail_body,
    "★★★★★ api_insurer_case_detail()가 더는 cases를 SELECT c.*로 안 받는다")

_k0 = APP_SRC.index("def api_insurer_bids(cid):")
_k1 = APP_SRC.index("\n@app.", _k0)
_bids_body = APP_SRC[_k0:_k1]
chk('"SELECT * FROM cases' not in _bids_body and "CASE_COLS_SQL" in _bids_body,
    "★★★★★ api_insurer_bids()가 더는 cases를 SELECT *로 안 받는다")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round443_")
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
        "VALUES('R443보험사','r443ins',?, '활성')", (DB.hash_pw("Testpw123!"),)).lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,"
        "login_id,password_hash,created_at) "
        "VALUES('R443업체','시공사','활성','가드레일','서울',"
        "'r443par',?,?)", (DB.hash_pw("Testpw123!"), DB.now())).lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,partner_id,"
        "                  note,manager,victim_name,victim_phone,track_token,"
        "                  track_token_hash,dispatch_status,lat,lng,geo_src,"
        "                  award_amount,created_at) "
        "VALUES('R443-CASE','완료','가드레일','서울',?,?,"
        "       '보험사 전달사항','김담당','홍길동','010-1234-5678','tok_abc123',"
        "       'hash_xyz789','사진확보',37.5,127.0,'수동',1000000,?)",
        (iid, pid, DB.now())).lastrowid
    conn.commit()

    ins = A.app.test_client()
    r = ins.post("/api/insurer/login", json={"login_id": "r443ins", "password": "Testpw123!"})
    assert r.status_code == 200, r.get_data(as_text=True)

    print("\n[3] 실행 — 세 라우트 전부 기존 컬럼값이 그대로 온다(회귀 없음)")
    r1 = ins.get("/api/insurer/dashboard")
    chk(r1.status_code == 200, "  GET /api/insurer/dashboard 200", r1.status_code)
    j1 = r1.get_json()
    c1 = next((x for x in (j1.get("cases") or []) if x["id"] == cid), None)
    chk(c1 is not None, "  방금 만든 사건이 대시보드 목록에 있다")
    if c1:
        chk(c1.get("note") == "보험사 전달사항" and c1.get("manager") == "김담당"
            and c1.get("victim_name") == "홍길동" and c1.get("victim_phone") == "010-1234-5678"
            and c1.get("track_token") == "tok_abc123" and c1.get("track_token_hash") == "hash_xyz789"
            and c1.get("dispatch_status") == "사진확보" and c1.get("lat") == 37.5
            and c1.get("award_amount") == 1000000,
            "★★★★★ dashboard: 기본·마이그레이션 컬럼 9종 전부 값이 그대로 온다"
            "(화이트리스트가 실제 필드를 빠뜨리지 않았다)", c1)

    r2 = ins.get(f"/api/insurer/cases/{cid}/detail")
    chk(r2.status_code == 200, "  GET /api/insurer/cases/{cid}/detail 200", r2.status_code)
    j2 = r2.get_json()
    c2 = j2.get("case") or {}
    chk(c2.get("note") == "보험사 전달사항" and c2.get("victim_name") == "홍길동"
        and c2.get("track_token_hash") == "hash_xyz789" and c2.get("lat") == 37.5,
        "★★★★★ case detail: 같은 컬럼들이 그대로 온다(회귀 없음)", c2)
    chk("is_demo" not in c2, "  case detail: 기존 동작(c.pop('is_demo'))이 그대로 유지된다"
        "(화이트리스트에 is_demo를 넣어도 이 pop이 여전히 지운다)", c2.get("is_demo", "<missing-ok>"))

    r3 = ins.get(f"/api/insurer/cases/{cid}/bids")
    chk(r3.status_code == 200, "  GET /api/insurer/cases/{cid}/bids 200", r3.status_code)
    j3 = r3.get_json()
    c3 = j3.get("case") or {}
    chk(c3.get("note") == "보험사 전달사항" and c3.get("victim_phone") == "010-1234-5678"
        and c3.get("award_amount") == 1000000,
        "★★★★★ bids: 같은 컬럼들이 그대로 온다(회귀 없음)", c3)

    # ============================================================
    print("\n[4] 탐지력 증명 — 미래에 민감 컬럼이 추가되면 세 자리 다 막는다"
          " (CASE_COLS_SQL 값만 메모리에서 스왑, 디스크 미기록·서브프로세스 미사용)")
    # ------------------------------------------------------------
    SECRET_MARKER = "R443_SECRET_INTERNAL_NEGOTIATION_7c2e"
    conn.execute("ALTER TABLE cases ADD COLUMN admin_secret_note TEXT")
    conn.execute("UPDATE cases SET admin_secret_note=? WHERE id=?", (SECRET_MARKER, cid))
    conn.commit()

    _orig_cols = A.CASE_COLS_SQL
    chk(_orig_cols != "c.*", "  (준비) 현재 CASE_COLS_SQL은 옛 값('c.*')이 아니다")
    A.CASE_COLS_SQL = "c.*"
    try:
        r_dash_old = ins.get("/api/insurer/dashboard")
        r_detail_old = ins.get(f"/api/insurer/cases/{cid}/detail")
        r_bids_old = ins.get(f"/api/insurer/cases/{cid}/bids")
        chk(SECRET_MARKER in r_dash_old.get_data(as_text=True)
            and SECRET_MARKER in r_detail_old.get_data(as_text=True)
            and SECRET_MARKER in r_bids_old.get_data(as_text=True),
            "★★★★★ 옛 값(CASE_COLS_SQL='c.*')으로 되돌리면 세 라우트 전부 미래에 추가된 "
            "민감 컬럼을 그대로 흘려보낸다(인과관계 직접증명)",
            (r_dash_old.status_code, r_detail_old.status_code, r_bids_old.status_code))
    finally:
        A.CASE_COLS_SQL = _orig_cols

    chk(A.CASE_COLS_SQL == _orig_cols, "  CASE_COLS_SQL이 원래 값(화이트리스트)으로 복원됐다")
    r_dash_new = ins.get("/api/insurer/dashboard")
    r_detail_new = ins.get(f"/api/insurer/cases/{cid}/detail")
    r_bids_new = ins.get(f"/api/insurer/cases/{cid}/bids")
    chk(SECRET_MARKER not in r_dash_new.get_data(as_text=True)
        and SECRET_MARKER not in r_detail_new.get_data(as_text=True)
        and SECRET_MARKER not in r_bids_new.get_data(as_text=True),
        "★★★★★ 원복 후(새 코드=화이트리스트) 세 라우트 전부 같은 미래 컬럼을 다시 막는다"
        "(이 회귀테스트의 탐지력 증명 + 스왑이 안 샜다는 확인)")

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(CASE_COLS_SQL 값 임시치환만 사용 — 디스크에 쓴 적도, 서브프로세스를 띄운 적도 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
