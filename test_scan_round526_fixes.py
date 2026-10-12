# -*- coding: utf-8 -*-
"""스캔 526라운드 회귀 — settlements(api_case_approve)·auctions(원경매/재경매를 여는
3개 지점)·schedule_events(api_schedule_event_add)의 실시간 INSERT 문이 사건의 is_demo
를 못 물려받던 결함. round525(defects·happy_calls)와 정확히 같은 축의 잔여 3표.

  직접 조사(하위위임 없음) — 지시받은 리드(db.py 의 _CHILD_DEMO_SQL 이 나열하는 9개
  자식표를 전부 확인하라)를 그대로 따랐다. bids·dispatches·field_agreements·
  notifications 는 이미 실시간 INSERT 에서 정상 캐스케이드됨을 직접 확인했다
  (dispatch.py 의 open_dispatch·assign_dispatch·open_agreement 3곳 모두
  `COALESCE((SELECT is_demo FROM cases WHERE id=?),0)` 서브쿼리를 쓰고, notify()
  는 case_id 로 다시 조회해 채운다). round525가 막 고친 defects·happy_calls 를
  제외한 나머지 셋 — settlements·auctions·schedule_events — 을 하나하나 Read 로
  대조하니 셋 다 round525 이전 defects·happy_calls 와 정확히 같은 모양으로 살아
  있었다: is_demo 컬럼 자체가 INSERT 문에 없어 스키마 기본값 0(실 데이터)으로
  떨어진다.

  이 셋은 심지어 db.py 자신의 주석이 이미 "유일한 생성 지점이 이 컬럼을 아예 안
  채운다"고 못박아 뒀다(settlements: db.py 1692행 round96 주석 · auctions: db.py
  1715행 round116 주석 · schedule_events: db.py 1726행 round122 주석) — 그런데 그
  라운드들은 db.py 의 백필(_CHILD_DEMO_SQL, 서버 기동 시 1회)만 추가했을 뿐 app.py
  의 실시간 INSERT 자체는 그 뒤로 아무도 고치지 않았다. round525가 "백필은 가동
  중 실시간 INSERT 를 못 고쳐 준다"는 구분을 처음 명시적으로 파고들며 defects·
  happy_calls 를 고쳤는데, db.py 안에 나란히 적힌 이 세 형제 주석은 그때도 안
  보고 넘어간 것이다.

    · settlements — api_case_approve()(app.py, 검수 승인→정산 생성)의 유일한
      INSERT 에 is_demo 컬럼이 없었다.
    · auctions — 이 표에 행을 만드는 3개 지점(원경매를 여는 _open_original_
      auction · 재경매를 여는 _open_reauction · 낙찰취소 후 원경매 행이 아예
      없는 사건을 되살리는 api_case_cancel_award 내부 폴백) **전부**에 is_demo
      컬럼이 없었다.
    · schedule_events — api_schedule_event_add()(수동 일정 등록)의 유일한
      INSERT 에 is_demo 컬럼이 없었다.

  영향 — 이미 존재하는 데모 사건에 대해 가동 중(=다음 재기동 전까지) 검수 승인을
  누르거나 낙찰을 취소해 경매를 재개설하거나 변경견적 추가경매/전체재경매를 열거나
  수동 일정을 등록하면, 그 새 행이 스키마 기본값 0(실 데이터)으로 잡힌다.
  settlements 는 관리자 대시보드(GMV·수수료합계·검수대기건수, app.py 의 여러
  scalar 질의)·보험사 명세서(_insurer_statement)·go-live 삭제 미리보기가 전부
  `COALESCE(is_demo,0)=0` 으로 이 표를 거르므로, 데모 정산 1건이 실매출 지표에
  그대로 섞인다 — db.py round96 주석이 "넷 중 어느 것보다 재무적으로 더 무겁다"고
  이미 적어 둔 바로 그 표다. auctions 는 협력사 공고 목록·마감 스윕·견적엔진
  표본이 이 표를 훑으므로 데모 경매가 실 목록에 노출된다.

  고침 — 다섯 INSERT 문(settlements 1곳 · auctions 3곳 · schedule_events 1곳)
  전부에 is_demo 컬럼을 추가했다. settlements 는 이미 조회해 둔 사건 행 c 가
  있어 round525 와 같은 원칙(`int(c["is_demo"] or 0)`)을 그대로 썼다. auctions
  3곳과 schedule_events 는 사건 전체 행을 다시 조회하지 않고 cid(또는 case_id)
  만 갖고 있어 형제 dispatch.py 가 이미 쓰는 서브쿼리 원칙
  `COALESCE((SELECT is_demo FROM cases WHERE id=?),0)` 을 그대로 따랐다 —
  schedule_events 는 case_id 가 NULL(사건과 무관한 일반 일정)일 수 있는데,
  서브쿼리가 그 경우 행을 못 찾아 자동으로 0이 되므로 db.py _CHILD_DEMO_SQL 의
  schedule_events 백필과 의도가 정확히 같다. 새 헬퍼·새 상수 없음(호출 지점마다
  이미 cid 를 갖고 있고 수정 자체가 1~2줄이라 공유 함수를 만들 만큼 반복되지
  않는다).

      python test_scan_round526_fixes.py
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
print("  스캔 526라운드 회귀 — settlements·auctions(3곳)·schedule_events 가")
print("  데모 표식을 안 물려받던 결함(round525 와 같은 축의 잔여 3표)")
print("=" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ============================================================
print("\n[1] 소스 확인 — 5개 INSERT 지점 전부에 is_demo 가 추가됐다")
# ------------------------------------------------------------
approve_body = _py_fn_body(APP_SRC, "api_case_approve")
chk("transfer_status, created_at, is_demo)" in approve_body,
    "★★★ api_case_approve() 의 settlements INSERT 컬럼 목록에 is_demo 가 추가됐다")
chk('int(c["is_demo"] or 0)' in approve_body,
    "★★★ 그 값으로 사건(c)의 is_demo 를 그대로 넣는다(round525 의 defects·"
    "happy_calls 와 같은 원칙)")

orig_auc_body = _py_fn_body(APP_SRC, "_open_original_auction")
chk("deadline,created_at,is_demo)" in orig_auc_body,
    "★★★ _open_original_auction() 의 auctions INSERT 컬럼 목록에 is_demo 가 추가됐다")
chk("COALESCE((SELECT is_demo FROM cases WHERE id=?),0))" in orig_auc_body,
    "★★★ 서브쿼리로 사건의 is_demo 를 채운다(dispatch.py 와 같은 원칙)")

reauc_body = _py_fn_body(APP_SRC, "_open_reauction")
chk("deadline,created_at,is_demo)" in reauc_body,
    "★★★ _open_reauction() 의 auctions INSERT 컬럼 목록에 is_demo 가 추가됐다")
chk("COALESCE((SELECT is_demo FROM cases WHERE id=?),0))" in reauc_body,
    "★★★ 여기도 같은 서브쿼리 원칙을 쓴다")

cancel_body = _py_fn_body(APP_SRC, "api_case_cancel_award")
chk(cancel_body.count("deadline,created_at,is_demo)") >= 1,
    "★★★ api_case_cancel_award() 내부 폴백 INSERT 에도 is_demo 가 추가됐다")
chk(cancel_body.count("COALESCE((SELECT is_demo FROM cases WHERE id=?),0))") >= 1,
    "★★★ 그 폴백도 같은 서브쿼리 원칙을 쓴다")

sched_body = _py_fn_body(APP_SRC, "api_schedule_event_add")
chk("created_by, created_at, is_demo)" in sched_body,
    "★★★ api_schedule_event_add() 의 schedule_events INSERT 컬럼 목록에 is_demo 가 추가됐다")
chk("COALESCE((SELECT is_demo FROM cases WHERE id=?),0))" in sched_body,
    "★★★ case_id 가 NULL 이어도 안전한 서브쿼리 원칙을 쓴다")

# ============================================================
print("\n[2] 실행 준비 — 스크래치 DB")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round526_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB  # noqa: E402
DB.init_db()
import app as A  # noqa: E402

conn = DB.get_db()
conn.execute("INSERT INTO admins(username,password_hash,name,role) "
             "VALUES('admin','x','검증','최고관리자')")
pid = conn.execute(
    "INSERT INTO partners(name,partner_type,status,category,region) "
    "VALUES('R526업체','시공사','활성','가드레일','서울')").lastrowid
conn.commit()

client = A.app.test_client()
_tok = "r526-csrf"
with client.session_transaction() as sess:
    sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
    sess["_csrf"] = _tok
_hdr = {"X-CSRF-Token": _tok}


def mk_case(no, **kw):
    cols = ["case_no"] + list(kw.keys())
    vals = [no] + list(kw.values())
    ph = ",".join("?" * len(cols))
    cid = conn.execute(
        f"INSERT INTO cases({','.join(cols)}) VALUES({ph})", vals).lastrowid
    conn.commit()
    return cid


# ============================================================
print("\n[3] 실행 — auctions: _open_original_auction() 이 원경매를 열 때")
# ------------------------------------------------------------
try:
    c_demo1 = mk_case("R526-A-DEMO", status="접수", category="가드레일", region="서울", is_demo=1)
    c_real1 = mk_case("R526-A-REAL", status="접수", category="가드레일", region="서울", is_demo=0)
    aid_demo1 = A._open_original_auction(conn, c_demo1)
    aid_real1 = A._open_original_auction(conn, c_real1)
    conn.commit()
    row = conn.execute("SELECT is_demo FROM auctions WHERE id=?", (aid_demo1,)).fetchone()
    chk(row is not None and row["is_demo"] == 1,
        "★★★★★ 새 코드: 데모 사건의 원경매(_open_original_auction)가 is_demo=1로 저장된다",
        dict(row) if row else None)
    row2 = conn.execute("SELECT is_demo FROM auctions WHERE id=?", (aid_real1,)).fetchone()
    chk(row2 is not None and row2["is_demo"] == 0,
        "★★★ 대조군: 실사건의 원경매는 여전히 is_demo=0", dict(row2) if row2 else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] _open_original_auction 실행", f"{type(e).__name__}: {e}")

# ============================================================
print("\n[4] 실행 — auctions: _open_reauction() 이 재경매를 열 때")
# ------------------------------------------------------------
try:
    c_demo2 = mk_case("R526-B-DEMO", status="입찰중", category="가드레일", region="서울", is_demo=1)
    c_real2 = mk_case("R526-B-REAL", status="입찰중", category="가드레일", region="서울", is_demo=0)
    A._open_reauction(conn, c_demo2, 9001, "추가분", 1)
    A._open_reauction(conn, c_real2, 9002, "추가분", 1)
    conn.commit()
    row3 = conn.execute(
        "SELECT is_demo FROM auctions WHERE case_id=? AND change_order_id=9001", (c_demo2,)).fetchone()
    chk(row3 is not None and row3["is_demo"] == 1,
        "★★★★★ 새 코드: 데모 사건의 재경매(_open_reauction)가 is_demo=1로 저장된다",
        dict(row3) if row3 else None)
    row4 = conn.execute(
        "SELECT is_demo FROM auctions WHERE case_id=? AND change_order_id=9002", (c_real2,)).fetchone()
    chk(row4 is not None and row4["is_demo"] == 0,
        "★★★ 대조군: 실사건의 재경매는 여전히 is_demo=0", dict(row4) if row4 else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [4] _open_reauction 실행", f"{type(e).__name__}: {e}")

# ============================================================
print("\n[5] 실행 — auctions: 낙찰취소(api_case_cancel_award) 내부 폴백 경로")
# ------------------------------------------------------------
#  ⚠ 원경매 행이 아예 없는 사건(1차 합의로 바로 낙찰된 건)에서 낙찰을 취소하면
#    이 폴백이 새 원경매 행을 만든다 — 그 경로를 실제 HTTP 로 그대로 밟는다.
try:
    c_demo3 = mk_case("R526-C-DEMO", status="시공중", category="가드레일", region="서울",
                       partner_id=pid, partner_name="R526업체", award_amount=1000000, is_demo=1)
    c_real3 = mk_case("R526-C-REAL", status="시공중", category="가드레일", region="서울",
                       partner_id=pid, partner_name="R526업체", award_amount=1000000, is_demo=0)
    pre_demo = conn.execute(
        "SELECT COUNT(*) n FROM auctions WHERE case_id=? AND change_order_id IS NULL",
        (c_demo3,)).fetchone()["n"]
    chk(pre_demo == 0, "★ (사전조건) 데모 사건에 원경매 행이 아직 없다", pre_demo)

    r_cancel_demo = client.post(f"/api/cases/{c_demo3}/cancel-award", headers=_hdr,
                                 json={"reason": "R526 검증용 낙찰취소(데모)"})
    chk(r_cancel_demo.status_code == 200, "★ (사전조건) 데모 사건 낙찰취소 자체는 200",
        (r_cancel_demo.status_code, r_cancel_demo.get_data(as_text=True)[:300]))
    row5 = conn.execute(
        "SELECT is_demo FROM auctions WHERE case_id=? AND change_order_id IS NULL",
        (c_demo3,)).fetchone()
    chk(row5 is not None and row5["is_demo"] == 1,
        "★★★★★ 새 코드: 낙찰취소 폴백이 되살린 데모 사건의 원경매가 is_demo=1로 저장된다"
        "(고치기 전엔 스키마 기본값 0으로 떨어졌다)", dict(row5) if row5 else None)

    r_cancel_real = client.post(f"/api/cases/{c_real3}/cancel-award", headers=_hdr,
                                 json={"reason": "R526 검증용 낙찰취소(실)"})
    chk(r_cancel_real.status_code == 200, "★ (사전조건) 실사건 낙찰취소도 200",
        (r_cancel_real.status_code, r_cancel_real.get_data(as_text=True)[:300]))
    row6 = conn.execute(
        "SELECT is_demo FROM auctions WHERE case_id=? AND change_order_id IS NULL",
        (c_real3,)).fetchone()
    chk(row6 is not None and row6["is_demo"] == 0,
        "★★★ 대조군: 실사건의 낙찰취소 폴백 원경매는 여전히 is_demo=0",
        dict(row6) if row6 else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [5] 낙찰취소 폴백 실행", f"{type(e).__name__}: {e}")

# ============================================================
print("\n[6] 실행 — settlements: 검수 승인(api_case_approve) 이 정산을 만들 때")
# ------------------------------------------------------------
try:
    c_demo4 = mk_case("R526-D-DEMO", status="검수대기", category="가드레일", region="서울",
                       partner_id=pid, partner_name="R526업체", award_amount=500000, is_demo=1)
    c_real4 = mk_case("R526-D-REAL", status="검수대기", category="가드레일", region="서울",
                       partner_id=pid, partner_name="R526업체", award_amount=500000, is_demo=0)
    for _cid in (c_demo4, c_real4):
        conn.execute(
            "INSERT INTO photos(case_id,partner_id,uploader_role,rel_path,review_status) "
            "VALUES(?,?,'협력사','x.jpg','승인')", (_cid, pid))
    conn.commit()

    r_appr_demo = client.post(f"/api/cases/{c_demo4}/approve", headers=_hdr, json={})
    chk(r_appr_demo.status_code == 200, "★ (사전조건) 데모 사건 검수승인 자체는 200",
        (r_appr_demo.status_code, r_appr_demo.get_data(as_text=True)[:300]))
    row7 = conn.execute("SELECT is_demo FROM settlements WHERE case_id=?", (c_demo4,)).fetchone()
    chk(row7 is not None and row7["is_demo"] == 1,
        "★★★★★ 새 코드: 데모 사건의 정산(api_case_approve)이 is_demo=1로 저장된다"
        "(고치기 전엔 스키마 기본값 0으로 떨어져 실매출 지표에 섞였다)",
        dict(row7) if row7 else None)

    r_appr_real = client.post(f"/api/cases/{c_real4}/approve", headers=_hdr, json={})
    chk(r_appr_real.status_code == 200, "★ (사전조건) 실사건 검수승인도 200",
        (r_appr_real.status_code, r_appr_real.get_data(as_text=True)[:300]))
    row8 = conn.execute("SELECT is_demo FROM settlements WHERE case_id=?", (c_real4,)).fetchone()
    chk(row8 is not None and row8["is_demo"] == 0,
        "★★★ 대조군: 실사건의 정산은 여전히 is_demo=0", dict(row8) if row8 else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [6] 검수승인 실행", f"{type(e).__name__}: {e}")

# ============================================================
print("\n[7] 실행 — schedule_events: 수동 일정 등록(api_schedule_event_add)")
# ------------------------------------------------------------
try:
    c_demo5 = mk_case("R526-E-DEMO", status="접수", category="가드레일", region="서울", is_demo=1)
    c_real5 = mk_case("R526-E-REAL", status="접수", category="가드레일", region="서울", is_demo=0)

    r_ev_demo = client.post("/api/schedule-events", headers=_hdr,
                             json={"title": "R526 검증 일정(데모)", "event_date": "2026-09-20",
                                   "case_id": c_demo5})
    chk(r_ev_demo.status_code == 200, "★ (사전조건) 데모 사건 일정등록 자체는 200",
        (r_ev_demo.status_code, r_ev_demo.get_data(as_text=True)[:300]))
    eid_demo = (r_ev_demo.get_json() or {}).get("id")
    row9 = conn.execute("SELECT is_demo FROM schedule_events WHERE id=?", (eid_demo,)).fetchone()
    chk(row9 is not None and row9["is_demo"] == 1,
        "★★★★★ 새 코드: 데모 사건에 묶인 일정이 is_demo=1로 저장된다"
        "(고치기 전엔 스키마 기본값 0으로 떨어져 달력에 실 일정처럼 노출됐다)",
        dict(row9) if row9 else None)

    r_ev_real = client.post("/api/schedule-events", headers=_hdr,
                             json={"title": "R526 검증 일정(실)", "event_date": "2026-09-20",
                                   "case_id": c_real5})
    chk(r_ev_real.status_code == 200, "★ (사전조건) 실사건 일정등록도 200",
        (r_ev_real.status_code, r_ev_real.get_data(as_text=True)[:300]))
    eid_real = (r_ev_real.get_json() or {}).get("id")
    row10 = conn.execute("SELECT is_demo FROM schedule_events WHERE id=?", (eid_real,)).fetchone()
    chk(row10 is not None and row10["is_demo"] == 0,
        "★★★ 대조군: 실사건에 묶인 일정은 여전히 is_demo=0", dict(row10) if row10 else None)

    #  ⚠ case_id 가 없는(사건과 무관한) 일반 일정은 과잉수정으로 1이 되면 안 된다
    #    — db.py _CHILD_DEMO_SQL 의 schedule_events 백필과 같은 의도를 실제로 지키는지.
    r_ev_none = client.post("/api/schedule-events", headers=_hdr,
                             json={"title": "R526 검증 일정(사건무관)", "event_date": "2026-09-20"})
    chk(r_ev_none.status_code == 200, "★ (사전조건) 사건무관 일정등록도 200",
        (r_ev_none.status_code, r_ev_none.get_data(as_text=True)[:300]))
    eid_none = (r_ev_none.get_json() or {}).get("id")
    row11 = conn.execute("SELECT is_demo FROM schedule_events WHERE id=?", (eid_none,)).fetchone()
    chk(row11 is not None and row11["is_demo"] == 0,
        "★★★ 과잉수정 아님: case_id 없는 일반 일정은 is_demo=0(서브쿼리가 못 찾아 그대로 0)",
        dict(row11) if row11 else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [7] 일정등록 실행", f"{type(e).__name__}: {e}")

# ============================================================
print("\n[8] 되돌림-증명 — app.py 는 건드리지 않고 이전 INSERT 문 3종을 테스트 안에만 재구성")
# ------------------------------------------------------------
#  ⚠ app.py 자체는 건드리지 않는다(동시 세션이 이 파일을 같이 건드릴 수 있는 환경 —
#    round520-525 와 같은 원칙, 이 저장소는 git 이 없어 파일을 스왑했다 복원하는
#    방식 자체가 동시편집과 충돌할 위험이 더 크다). 라운드526 이전 실제 코드
#    (is_demo 컬럼이 아예 없던 INSERT 문 원문, 이번 수정 직전에 이 세션이 직접
#    Read 로 확인한 텍스트)를 문자열로만 재구성해 별도 사건에 직접 실행하고, 그
#    결과가 [3]~[7]의 새 코드 결과와 실제로 다름을 보여 이 회귀가 진짜 그 차이를
#    잡아낼 능력이 있음을 증명한다.
try:
    c_old = mk_case("R526-OLD-BASE", status="검수대기", category="가드레일", region="서울",
                     partner_id=pid, partner_name="R526업체", award_amount=700000, is_demo=1)

    OLD_SETTLE_SQL = """INSERT INTO settlements(case_id, case_no, insurer, insurer_id, partner_name, partner_id,
                               amount, fee, payout, fee_rate_bp,
                               insurer_paid, review_status, transfer_status, created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
    conn.execute(OLD_SETTLE_SQL,
                 (c_old, "R526-OLD-BASE", None, None, "R526업체", pid,
                  700000, 70000, 630000, 1000, "대기", "대기", "대기", DB.now()))
    conn.commit()
    old_settle = conn.execute(
        "SELECT is_demo FROM settlements WHERE case_id=?", (c_old,)).fetchone()
    chk(old_settle is not None and old_settle["is_demo"] == 0,
        "★★★★★ 옛 코드(재구성): settlements 도 is_demo 컬럼이 빠진 INSERT 문이라 "
        "같은 데모 사건인데 스키마 기본값 0으로 떨어진다 — [6]의 새 코드 결과(1)와 대조",
        dict(old_settle) if old_settle else None)

    OLD_AUCTION_SQL = (
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,"
        "                     low_price,bid_count,extend_count,deadline,created_at) "
        "VALUES(?,NULL,'원경매',0,'진행',0,0,0, datetime('now','+9 hours', ?), ?)")
    conn.execute(OLD_AUCTION_SQL, (c_old, "+24 hours", DB.now()))
    conn.commit()
    old_auction = conn.execute(
        "SELECT is_demo FROM auctions WHERE case_id=? AND change_order_id IS NULL",
        (c_old,)).fetchone()
    chk(old_auction is not None and old_auction["is_demo"] == 0,
        "★★★★★ 옛 코드(재구성): auctions 도 같은 이유로 데모 사건인데 is_demo=0으로 "
        "떨어진다 — [3]~[5]의 새 코드 결과(1)와 대조", dict(old_auction) if old_auction else None)

    OLD_SCHED_SQL = """INSERT INTO schedule_events(title, memo, event_date, event_time, case_id,
                                       created_by, created_at)
           VALUES(?,?,?,?,?,?,?)"""
    conn.execute(OLD_SCHED_SQL,
                 ("되돌림증명용 일정", "", "2026-09-21", None, c_old, "검증", DB.now()))
    conn.commit()
    old_sched = conn.execute(
        "SELECT is_demo FROM schedule_events WHERE case_id=? AND title='되돌림증명용 일정'",
        (c_old,)).fetchone()
    chk(old_sched is not None and old_sched["is_demo"] == 0,
        "★★★★★ 옛 코드(재구성): schedule_events 도 같은 이유로 데모 사건인데 "
        "is_demo=0으로 떨어진다 — [7]의 새 코드 결과(1)와 대조해 이 회귀가 실제로 "
        "그 차이를 잡아낼 능력이 있음을 증명", dict(old_sched) if old_sched else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [8] 되돌림-증명", f"{type(e).__name__}: {e}")
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
