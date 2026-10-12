# -*- coding: utf-8 -*-
"""스캔 100라운드 회귀 — 입찰 화면 3건.

  [1] _bid_scores 의 하자 점수가 partner_rating 과 다른 술어를 썼다. 후자는
      "완료·시행사귀책" 하자만 깎는데(같은 파일의 명시적 설계 의도, 반려·타사
      귀책은 안 깎는다), 전자는 무조건 COUNT(*) 라 반려된 하자까지 만점 감점
      시켰다. 같은 낙찰 화면 한 줄에 '평점 4.5 ★ · 하자 3건'처럼 서로 모순되는
      두 숫자가 나란히 찍힌다.
  [2] 세 낙찰 경로(보험사·어드민 원경매·변경견적 마감)의 "최저가가 아니면
      사유 강제" 게이트가 퇴출·정지 업체 입찰까지 포함해 최저가를 계산했다.
      후보 목록·마감 집계는 전부 활성 업체만 보는데 이 게이트만 모집단이
      달라서, 화면에 유일하게 보이는 최저가를 골라도 "최저가가 아니다"로
      막히고 그 사유가 §188 3호 소명 근거로 감사로그에 거짓 기록됐다.
  [3] defects·happy_calls 도 자기 is_demo 컬럼이 있고 읽는 쪽은 이미
      COALESCE(is_demo,0)=0 으로 데모를 거르는데, 채우는 코드가 없어(정본
      캐스케이드에도 없음) 그 필터가 항상 전 행을 통과시켰다(96·99라운드와
      같은 모양의 세 번째·네 번째 사례).

      python test_scan_round100_fixes.py
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
DB_SRC = read("db.py")

print("═" * 72)
print("  스캔 100라운드 회귀 — 하자점수 술어불일치·최저가게이트 모집단불일치·데모캐스케이드 2건 누락")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 세 지점 모두 정본 함수/술어를 그대로 쓴다")
# ──────────────────────────────────────────────────────────────
bs_body = _py_fn_body(APP_SRC, "_bid_scores")
chk("status='완료' AND COALESCE(cost_bearer,'')='시행사'" in bs_body,
    "★★★ _bid_scores 의 하자 카운트가 partner_rating 과 같은 술어(완료·시행사귀책)를 쓴다")

chk("def _lowest_active_bid_amount(conn, auction_id):" in APP_SRC,
    "★★ 최저가 계산이 정본 헬퍼 하나로 모였다")
lo_body = _py_fn_body(APP_SRC, "_lowest_active_bid_amount")
chk("JOIN partners p ON p.id = b.partner_id" in lo_body and "COALESCE(p.status,'활성') = '활성'" in lo_body,
    "★★★ 그 헬퍼가 활성 업체만 최저가 모집단으로 본다(후보 목록·마감 집계와 동일)")

for fn in ("api_insurer_award", "api_case_award", "api_co_close_full"):
    body = _py_fn_body(APP_SRC, fn)
    chk("_lowest_active_bid_amount(conn, b[\"auction_id\"])" in body,
        f"★★ {fn} 가 정본 헬퍼를 호출한다(손으로 복붙한 MIN 쿼리가 아니다)")
    chk("SELECT MIN(amount) m FROM bids WHERE auction_id=? AND voided_at IS NULL" not in body,
        f"★ {fn} 에 예전의 활성필터 없는 MIN 쿼리가 더 이상 안 남아 있다")

chk('("defects",' in DB_SRC and "UPDATE defects SET is_demo=1" in DB_SRC,
    "★★★ _CHILD_DEMO_SQL 에 defects 캐스케이드가 추가됐다")
chk('("happy_calls",' in DB_SRC and "UPDATE happy_calls SET is_demo=1" in DB_SRC,
    "★★★ _CHILD_DEMO_SQL 에 happy_calls 캐스케이드가 추가됐다")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[4] 실행 — 세 시나리오를 실제로 돌린다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round100_")
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

    # ── [2] 하자 점수 — 반려/타사귀책 하자는 만점 감점시키지 않는다 ──────
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,jobs_done) "
        "VALUES('R100업체','시행사','활성',4)").lastrowid
    conn.execute(
        "INSERT INTO defects(defect_no,case_id,title,status,cost_bearer,partner_id,created_at) "
        "VALUES('R100-DF1',0,'완료+시행사 귀책(깎여야 함)','완료','시행사',?,?)", (pid, DB.now()))
    conn.execute(
        "INSERT INTO defects(defect_no,case_id,title,status,cost_bearer,partner_id,created_at) "
        "VALUES('R100-DF2',0,'반려(안 깎여야 함)','반려','시행사',?,?)", (pid, DB.now()))
    conn.execute(
        "INSERT INTO defects(defect_no,case_id,title,status,cost_bearer,partner_id,created_at) "
        "VALUES('R100-DF3',0,'완료+보험사 귀책(안 깎여야 함)','완료','보험사',?,?)", (pid, DB.now()))
    conn.commit()
    bid = {"amount": 1000000, "days": 10, "rating": 4.5, "jobs_done": 4, "partner_id": pid}
    scored = A._bid_scores(conn, {"region": "서울"}, [bid])
    chk(len(scored) == 1, "STEP _bid_scores 가 결과를 돌려준다", len(scored))
    if scored:
        chk(scored[0]["defect_count"] == 1,
            "★★★ 하자 3건 중 '완료+시행사귀책' 1건만 세어졌다(예전엔 3건 전부 세어 만점 감점)",
            scored[0].get("defect_count"))

    # ── [3] 최저가 게이트 — 퇴출 업체의 더 싼 입찰은 최저가에서 빠진다 ────
    p_retired = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R100퇴출업체','시행사','퇴출')").lastrowid
    p_active = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R100활성업체','시행사','활성')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R100-AW01','입찰중','가드레일','서울',0)").lastrowid
    aid = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,NULL,'원경매',0,'마감',2000000,2,0,?,?)", (cid, DB.now(), DB.now())).lastrowid
    conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,1000000,10,?)", (aid, p_retired, "R100퇴출업체", DB.now()))
    conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,1500000,10,?)", (aid, p_active, "R100활성업체", DB.now()))
    conn.commit()
    lowest_amt = A._lowest_active_bid_amount(conn, aid)
    chk(lowest_amt == 1500000,
        "★★★ 활성 업체 중 최저가(150만원)를 돌려준다 — 퇴출 업체의 100만원은 후보가 아니므로 제외",
        lowest_amt)

    # ── [4] defects·happy_calls 도 사건에서 is_demo 를 물려받는다 ────────
    cid_demo = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R100-DEMO01','완료','가드레일','서울',1)").lastrowid
    conn.execute(
        "INSERT INTO defects(defect_no,case_id,title,status,created_at) "
        "VALUES('R100-DF-DEMO',?,'데모 사건 하자','접수',?)", (cid_demo, DB.now()))
    conn.execute(
        "INSERT INTO happy_calls(case_id,score,created_at) VALUES(?,5,?)", (cid_demo, DB.now()))
    conn.commit()

    DB._backfill_child_is_demo(conn)
    conn2 = DB.get_db()
    defect_demo = conn2.execute(
        "SELECT is_demo FROM defects WHERE case_id=?", (cid_demo,)).fetchone()["is_demo"]
    hc_demo = conn2.execute(
        "SELECT is_demo FROM happy_calls WHERE case_id=?", (cid_demo,)).fetchone()["is_demo"]
    conn2.close()
    chk(defect_demo == 1,
        "★★★ 데모 사건의 하자도 이제 is_demo 가 붙는다(보험사 대시보드 하자 배지가 더는 안 센다)",
        defect_demo)
    chk(hc_demo == 1,
        "★★★ 데모 사건의 해피콜도 이제 is_demo 가 붙는다(해피콜 평균·업체 평점이 더는 안 섞인다)",
        hc_demo)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드100 서버측 준비/실행", f"{type(e).__name__} {e}")
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
