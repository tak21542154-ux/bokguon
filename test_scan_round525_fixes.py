# -*- coding: utf-8 -*-
"""스캔 525라운드 회귀 — 하자 접수(api_defect_create)·해피콜 기록(api_happy_call_add)의
INSERT 문이 is_demo 를 채우지 않아, 이미 존재하는 데모 사건(is_demo=1)에 서버 가동
중 새로 접수하면 매번 스키마 기본값 0(실 데이터)으로 잘못 저장되던 결함.

  직접 조사(하위위임 없음) — 지시받은 네 후보(사진업로드 검증·정산 계산·통계 집계·
  알림 배지) 를 순서대로 Read 로 직접 대조했다. 사진업로드(photo_ai.py, 사건당
  누적상한 _case_photo_quota_guard 가 3개 라우트에 공유)·정산(compute_fee/
  split_vat/void 가드, api_settlement_review·paid·transfer 전부 형제와 같은
  void_status 방어)·알림 배지(admin/insurer/partner 세 라우트, round206 이 이미
  ADMIN_FEED_SQL 과 ADMIN_OWN_SQL 을 분리)·통계집계(api_dashboard·api_stats·
  _insurer_statement·_resync_partner_stats — 전부 COALESCE(is_demo,0)=0 과
  SAVE_BASE_SQL·CASE_AMOUNT_SQL 을 형제 자리와 일치시켜 둠)는 이미 여러 라운드에
  걸쳐 다층 방어가 있음을 직접 확인해 클린 판정했다(억지로 흠을 만들지 않음).

  네 후보 밖으로 넓혀 partner_rating()(협력사 평점 계산식, app.py:14440)을 다시
  보다가, 이 함수의 두 읽기 질의가 전부 `COALESCE(is_demo,0)=0`으로 defects·
  happy_calls 를 거른다는 것과, db.py:_backfill_child_is_demo()가 "화면·집계
  23곳이 bids.is_demo 등을 보고 데모를 거른다"며 여러 자식표에 is_demo 를
  사건에서 캐스케이드한다는 것을 함께 확인했다. 그런데 이 백필은 db.migrate()
  (서버 기동 시 1회)에서만 불린다 — app.py 안 어디에도 호출이 없다(grep 전수
  확인, "_backfill_child_is_demo" 는 app.py 안에 주석 인용 1곳뿐). 즉 **가동
  중** 실시간으로 새 자식 행이 생기는 순간에는 그 INSERT 자신이 is_demo 를
  채워야 한다 — 서버가 다음에 재기동될 때까지는 아무도 대신 고쳐 주지 않는다.

  실제로 이 원칙은 이미 두 군데서 지켜지고 있었다. ① bids(app.py:5277·5481,
  "데모 표식을 사건에서 물려받아 여기서 채운다" — INSERT 문에
  `COALESCE((SELECT c.is_demo FROM auctions a JOIN cases c ...),0)` 서브쿼리).
  ② notify()(app.py:1870, 40여 곳의 호출부를 대신해 이 함수 하나가 case_id 로
  다시 조회해 is_demo 를 채움 — "호출부가 40곳 넘으므로 각자 채우게 두지 않는다").
  그런데 형제인 defects(api_defect_create, app.py:14543)·happy_calls
  (api_happy_call_add, app.py:18868)의 INSERT 문은 둘 다(호출부가 각 1곳뿐이라
  bids·notify() 같은 공유 관문조차 없이) is_demo 컬럼이 아예 없어 스키마
  기본값(DEFAULT 0)으로 떨어진다 — 사건이 이미 is_demo=1 이어도 무관하게 매번
  0(실 데이터)으로 저장된다. round106 은 partner_rating() 의 **읽는 쪽**에
  is_demo 필터를 추가하며 "형제인 happy_calls 질의는 이미 걸러낸다"고 적었지만,
  그 "채우는 쪽"이 서버 기동 시점 일괄보정(_backfill_child_is_demo)뿐이라는
  점은 그 라운드도, 이후의 round140·round433(둘 다 defects/happy_calls 를
  손댔지만 severity 검증·고아행 정리가 목적이라 이 INSERT 문 자체는 안 봄)도
  확인하지 않았다 — 그래서 지금까지 살아남았다.

  영향 — 관리자 콘솔에서 이미 존재하는 데모 사건에(이 두 라우트 모두 case_id/cid
  의 is_demo 를 확인하지 않는다) 하자를 접수하거나 해피콜을 기록하면, 다음 서버
  재기동 전까지 그 행이 실 데이터로 잡혀 partner_rating()(평점 화면)·
  _bid_scores()(진행 중인 경매의 낙찰점수 하자 감점, app.py:11332, "채우는 쪽은
  이미 오래전부터 defects 를 정상적으로 캐스케이드하는데"라는 그 함수 자신의
  가정이 라이브 삽입 경로에는 틀렸다)·api_defects_summary()·api_happy_calls()
  의 실협력사 집계에 그대로 섞인다 — 데모 사건 하나가 실제 낙찰 결과를 바꿀 수
  있다.

  고침 — 두 INSERT 문 모두에 `is_demo` 컬럼을 추가하고, 이미 조회해 둔 사건
  행의 `c["is_demo"]`(정수로 캐스팅)를 그대로 넣는다(bids 와 같은 원칙 — 호출
  지점이 각각 하나뿐이라 새 공유 헬퍼는 만들지 않았다). api_happy_call_add() 는
  기존 SELECT 목록에 is_demo 가 없어 함께 추가했다. 새 상수 없음.

      python test_scan_round525_fixes.py
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
print("  스캔 525라운드 회귀 — 하자접수·해피콜기록이 데모 표식을 안 물려받던 결함")
print("=" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
defect_body = _py_fn_body(APP_SRC, "api_defect_create")
chk("cost_bearer,warranty_ok,created_at,is_demo)" in defect_body,
    "★★★ api_defect_create() 의 INSERT 컬럼 목록에 is_demo 가 추가됐다")
chk('int(c["is_demo"] or 0)' in defect_body,
    "★★★ 그 값으로 사건(c)의 is_demo 를 그대로 넣는다(bids·notify() 와 같은 원칙)")

hc_body = _py_fn_body(APP_SRC, "api_happy_call_add")
chk("called_by, created_at, is_demo)" in hc_body,
    "★★★ api_happy_call_add() 의 INSERT 컬럼 목록에 is_demo 가 추가됐다")
chk("SELECT id, case_no, status, partner_id, is_demo FROM cases" in hc_body,
    "★★ 그 값을 읽어 오도록 SELECT 목록도 함께 넓혔다")
chk(hc_body.count('int(c["is_demo"] or 0)') == 1,
    "★★★ 해피콜도 같은 방식으로 사건의 is_demo 를 정확히 한 번 그대로 넣는다")

# ============================================================
print("\n[2] 실행 준비 — 스크래치 DB")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round525_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB  # noqa: E402
DB.init_db()
import app as A  # noqa: E402

conn = DB.get_db()
#  ⚠ _account_alive() 가 session["admin"] 을 admins 표에서 실제로 다시 조회한다
#    (round106 test 참고) — 표에 없으면 "계정이 삭제되었습니다"로 401 → 세션이
#    clear() 되어 다음 요청부터는 CSRF 까지 연쇄로 깨진다. 반드시 먼저 심는다.
conn.execute("INSERT INTO admins(username,password_hash,name,role) "
             "VALUES('admin','x','검증','최고관리자')")
pid = conn.execute(
    "INSERT INTO partners(name,partner_type,status,category,region) "
    "VALUES('R525업체','시공사','활성','가드레일','서울')").lastrowid
cid_demo = conn.execute(
    "INSERT INTO cases(case_no,status,category,region,partner_id,is_demo) "
    "VALUES('R525-DEMO1','시공중','가드레일','서울',?,1)", (pid,)).lastrowid
cid_real = conn.execute(
    "INSERT INTO cases(case_no,status,category,region,partner_id,is_demo) "
    "VALUES('R525-REAL1','시공중','가드레일','서울',?,0)", (pid,)).lastrowid
cid_demo_done = conn.execute(
    "INSERT INTO cases(case_no,status,category,region,partner_id,is_demo) "
    "VALUES('R525-DEMO2','완료','가드레일','서울',?,1)", (pid,)).lastrowid
cid_real_done = conn.execute(
    "INSERT INTO cases(case_no,status,category,region,partner_id,is_demo) "
    "VALUES('R525-REAL2','완료','가드레일','서울',?,0)", (pid,)).lastrowid
conn.commit()

client = A.app.test_client()
_tok = "r525-csrf"
with client.session_transaction() as sess:
    sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
    sess["_csrf"] = _tok
_hdr = {"X-CSRF-Token": _tok}

# ============================================================
print("\n[3] 실행 — 새 코드: 하자 접수가 사건의 is_demo 를 그대로 물려받는다")
# ------------------------------------------------------------
try:
    r_demo = client.post("/api/defects", headers=_hdr,
                          json={"case_id": cid_demo, "title": "R525 검증용 하자(데모)"})
    chk(r_demo.status_code == 200, "★ (사전조건) 데모 사건 하자 접수 자체는 200",
        (r_demo.status_code, r_demo.get_data(as_text=True)[:200]))
    did_demo = (r_demo.get_json() or {}).get("id")
    row = conn.execute("SELECT is_demo FROM defects WHERE id=?", (did_demo,)).fetchone()
    chk(row is not None and row["is_demo"] == 1,
        "★★★★★ 새 코드: 데모 사건(is_demo=1)에 접수한 하자가 is_demo=1로 저장된다"
        "(고치기 전엔 스키마 기본값 0으로 떨어져 실 데이터로 잡혔다)",
        dict(row) if row else None)

    r_real = client.post("/api/defects", headers=_hdr,
                          json={"case_id": cid_real, "title": "R525 검증용 하자(실)"})
    chk(r_real.status_code == 200, "★ (사전조건) 실사건 하자 접수도 200", r_real.status_code)
    did_real = (r_real.get_json() or {}).get("id")
    row2 = conn.execute("SELECT is_demo FROM defects WHERE id=?", (did_real,)).fetchone()
    chk(row2 is not None and row2["is_demo"] == 0,
        "★★★ 대조군: 실사건(is_demo=0)에 접수한 하자는 여전히 is_demo=0"
        "(이번 수정이 '항상 1'로 뒤집는 과잉수정이 아니다)", dict(row2) if row2 else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] 하자 접수 실행", f"{type(e).__name__}: {e}")

# ============================================================
print("\n[4] 실행 — 새 코드: 해피콜 기록도 사건의 is_demo 를 그대로 물려받는다")
# ------------------------------------------------------------
try:
    r_hc_demo = client.post(f"/api/cases/{cid_demo_done}/happy-call", headers=_hdr,
                             json={"score": 5})
    chk(r_hc_demo.status_code == 200, "★ (사전조건) 데모 완료건 해피콜 기록 자체는 200",
        (r_hc_demo.status_code, r_hc_demo.get_data(as_text=True)[:200]))
    hc_row = conn.execute(
        "SELECT is_demo FROM happy_calls WHERE case_id=?", (cid_demo_done,)).fetchone()
    chk(hc_row is not None and hc_row["is_demo"] == 1,
        "★★★★★ 새 코드: 데모 완료건 해피콜이 is_demo=1로 저장된다"
        "(고치기 전엔 0으로 떨어져 partner_rating() 해피콜 평균에 섞였다)",
        dict(hc_row) if hc_row else None)

    r_hc_real = client.post(f"/api/cases/{cid_real_done}/happy-call", headers=_hdr,
                             json={"score": 5})
    chk(r_hc_real.status_code == 200, "★ (사전조건) 실 완료건 해피콜 기록도 200",
        r_hc_real.status_code)
    hc_row2 = conn.execute(
        "SELECT is_demo FROM happy_calls WHERE case_id=?", (cid_real_done,)).fetchone()
    chk(hc_row2 is not None and hc_row2["is_demo"] == 0,
        "★★★ 대조군: 실 완료건 해피콜은 여전히 is_demo=0", dict(hc_row2) if hc_row2 else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [4] 해피콜 기록 실행", f"{type(e).__name__}: {e}")

# ============================================================
print("\n[5] 되돌림-증명 — app.py 는 건드리지 않고 이전 INSERT 문을 테스트 안에만 재구성")
# ------------------------------------------------------------
#  ⚠ app.py 자체는 건드리지 않는다(동시 세션이 이 파일을 같이 건드릴 수 있는
#    환경 — round520-524 와 같은 원칙, 이 저장소는 git 이 없어 파일을 스왑했다
#    복원하는 방식 자체가 동시편집과 충돌할 위험이 더 크다). 라운드525 이전
#    실제 코드(is_demo 컬럼이 아예 없던 INSERT 문 원문 그대로, 이번 수정 직전에
#    이 세션이 직접 Read 로 확인한 텍스트)를 문자열로만 재구성해 별도 사건에
#    직접 실행하고, 그 결과가 [3]/[4]의 새 코드 결과와 실제로 다름을 보여
#    이 회귀가 진짜 그 차이를 잡아낼 능력이 있음을 증명한다.
try:
    OLD_DEFECT_SQL = """INSERT INTO defects(defect_no,case_id,case_no,insurer,insurer_id,partner_id,partner_name,
           category,region,title,content,severity,reporter,reporter_type,status,due_date,
           cost_bearer,warranty_ok,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
    conn.execute(
        OLD_DEFECT_SQL,
        ("R525-OLD-1", cid_demo, "R525-DEMO1", None, None, pid, "R525업체", "가드레일", "서울",
         "되돌림증명용", None, "보통", "검증", "내부", "접수", None, "시행사", 1, DB.now()))
    conn.commit()
    old_row = conn.execute(
        "SELECT is_demo FROM defects WHERE defect_no='R525-OLD-1'").fetchone()
    chk(old_row is not None and old_row["is_demo"] == 0,
        "★★★★★ 옛 코드(재구성): 같은 데모 사건(is_demo=1)에 접수해도 is_demo 컬럼이 "
        "빠진 INSERT 문이라 스키마 기본값 0으로 떨어진다 — 이게 바로 라운드525 수정 전 "
        "결함 상태이고, [3]의 새 코드 결과(1)와 정확히 대조된다", dict(old_row) if old_row else None)

    OLD_HC_SQL = """INSERT INTO happy_calls(case_id, partner_id, score, feedback, method,
                                           called_by, created_at)
                   VALUES(?,?,?,?,?,?,?)"""
    cid_demo_done2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,is_demo) "
        "VALUES('R525-DEMO3','완료','가드레일','서울',?,1)", (pid,)).lastrowid
    conn.commit()
    conn.execute(OLD_HC_SQL, (cid_demo_done2, pid, 5, "", "전화", "검증", DB.now()))
    conn.commit()
    old_hc = conn.execute(
        "SELECT is_demo FROM happy_calls WHERE case_id=?", (cid_demo_done2,)).fetchone()
    chk(old_hc is not None and old_hc["is_demo"] == 0,
        "★★★★★ 옛 코드(재구성): 해피콜도 같은 이유로 데모 사건인데 is_demo=0으로 "
        "떨어진다 — [4]의 새 코드 결과(1)와 대조해 이 회귀가 실제로 그 차이를 "
        "잡아낼 능력이 있음을 증명", dict(old_hc) if old_hc else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [5] 되돌림-증명", f"{type(e).__name__}: {e}")
finally:
    conn.close()

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
