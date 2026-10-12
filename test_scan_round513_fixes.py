# -*- coding: utf-8 -*-
"""스캔 513라운드 회귀 — api_auction_set_deadline()의 "마감된 재경매 다시 열기"
   분기가 형제 api_case_reopen(원경매)과 달리 reopen_count/MAX_REOPEN 상한을
   전혀 안 보던 결함.

  직접 조사(하위위임 없음) — run_all_tests.py 전체를 먼저 정독해 이미 포화된
  축(형제 엔드포인트 잠금 비대칭 504~507, change_orders 생애주기 가시성 492,
  자격증명 전역유일 494, DUP_BIZNO 계열, 개인정보파기 6버킷 495, activity_log
  마스킹 496·249, 가운뎃점 정규화 499, 출동수배 버튼 등급게이트 502, catch분기
  화면정리 481·486·500·501·503·504, 입점신청 상태역전 504, 정책문서 불일치
  289·317·508, website 저장형 XSS 509·510, 지역판정 버그클래스 511·512)와
  겹치지 않는 각도를 찾다가 "2차경매(재경매) 엣지케이스"를 따라 change_orders에
  딸린 auctions 재개(reopen) 경로를 형제 함수들과 나란히 대조했다.

  결함 — app.py:api_auction_set_deadline()(POST /api/auctions/<aid>/deadline)의
  "이미 마감된 재경매를 다시 연다" 분기는, 정확히 같은 목적(막힌 입찰을 무한정
  계속하지 못하게 상한을 걸고 그 뒤엔 사람이 개입하게 만든다)을 가진 형제
  api_case_reopen()(POST /api/cases/<cid>/reopen, 원경매 전용)과 달리
  auctions.reopen_count 컬럼을 한 번도 읽지도 늘리지도 않았다 — 즉 상한이
  전혀 없어 몇 번이든 계속 재개할 수 있었다(회귀 전 SQL은 "UPDATE auctions
  SET status='진행', deadline=? WHERE id=? AND status='마감' AND
  change_order_id IS NOT NULL" 뿐, 횟수 조건이 아예 없다). 게다가 전체재경매
  자체의 라운드 상한(MAX_CO_ROUND=3, api_co_full_reauction — "3차까지 실패하면
  최종유찰")은 change_orders.round 를 올리며 "새 라운드"를 여는 경로에만
  걸리므로, 이 경로로 "같은 라운드를 계속 연장"하면 그 상한도 우회되어
  변경견적이 최종유찰(사람이 개입해야 하는 확정 상태)에 영원히 도달하지 못할
  수 있었다.

  고침 — 형제(api_case_reopen)와 같은 상수(MAX_REOPEN=3, 이미 정의돼 있음)와
  컬럼(auctions.reopen_count, 이미 스키마에 있음)을 그대로 재사용해, 상한
  도달 시 409(code=MAX_EXTEND)로 막고 성공 시 reopen_count 를 늘린다.
  새 상수·새 컬럼을 만들지 않는다(ponytail 원칙 — 이미 있는 것을 쓴다).
  BEGIN IMMEDIATE 를 이미 함수 상단에서 잡고 있어(이 함수 자체가 원래 그렇다)
  SELECT 후 UPDATE 두 문장으로 나눠도 동시성 문제가 없다(같은 함수 안의 다른
  단계도 이미 이 방식이다).

  [1] 소스 확인 — 새 코드가 api_auction_set_deadline() 본문 안에 정확히 한 번.
  [2] 실행 — 실제 sqlite3 스크래치 DB + Flask test_client 로 변경견적
      전체재경매를 만들고, "마감→관리자가 재개"를 MAX_REOPEN(3)번 반복해
      매번 200으로 성공하고 reopen_count 가 1씩 느는지, 그 다음(4번째)은
      409(MAX_EXTEND)로 막히고 reopen_count·status 가 더 안 움직이는지 확인.
  [3] 대조 — 원경매(change_order_id IS NULL)는 여전히 이 경로로 못 되살아난다
      (형제 회귀 test_b4_review_fixes.py 라인 234-237 이 이미 보장하는 결론을
      이 스크립트에서도 독립적으로 재확인 — 회귀 없음).
  [4] 되돌림-증명 — 이 라운드 이전에 실제로 쓰이던 SQL 그대로(상한 검사 없음)를
      순수 sqlite3(:memory:)에 직접 반복 실행해, reopen_count 가 상한을 훌쩍
      넘겨도(5) 매번 rowcount=1(무조건 성공)임을 재현한다 — 새 코드의
      SELECT+상한검사가 없으면 정말 무제한이었음을 증명한다.

      python test_scan_round513_fixes.py
"""
import io
import os
import shutil
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 513라운드 회귀 — 재경매 재개(deadline) 상한(reopen_count) 부재")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
fn_body = _py_fn_body(APP_SRC, "api_auction_set_deadline")
chk("[라운드513]" in fn_body, "★★★ 새 코드가 api_auction_set_deadline() 본문 안에 있다")
chk(APP_SRC.count("[라운드513]") == 1, "라운드513 표식이 전체 소스에 정확히 1번뿐(중복 삽입 아님)")
chk('"code": "MAX_EXTEND"' in fn_body, "★★★ 상한 도달 시 code=MAX_EXTEND 로 막는다")
chk("reopen_count=COALESCE(reopen_count,0)+1" in fn_body,
    "★★★ 성공한 재개는 reopen_count 를 늘린다")
chk("rc >= MAX_REOPEN" in fn_body, "★★★ 형제(api_case_reopen)와 같은 상수 MAX_REOPEN 을 그대로 재사용한다")
chk(APP_SRC.count("def api_auction_set_deadline(") == 1, "함수 정의가 정확히 1번(중복 정의 없음)")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[3] 실행 — 실제 시나리오(Flask test_client + 스크래치 DB)")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round513_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    chk(A.MAX_REOPEN == 3, "전제 확인 — MAX_REOPEN 상수가 여전히 3이다(바뀌면 아래도 그 값을 따라간다)",
        A.MAX_REOPEN)

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r513admin','x','검증','중간관리자')")
    conn.commit()
    admin = A.app.test_client()
    _tok = "r513-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r513admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R513-C1','시공중','가드레일','서울',0)").lastrowid
    coid = conn.execute(
        "INSERT INTO change_orders(case_id,round,reason,requested_amount,status,created_at) "
        "VALUES(?,1,'실사 증액','추가 공사','전체재경매중',?)", (cid, DB.now())).lastrowid
    aid = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,?,'전체재경매',1,'마감',0,0,0,?,?)", (cid, coid, DB.now(), DB.now())).lastrowid
    conn.commit()

    # [2] MAX_REOPEN(3)번은 성공하고, reopen_count 가 매번 1씩 늘어난다.
    for i in range(1, A.MAX_REOPEN + 1):
        r = admin.post(f"/api/auctions/{aid}/deadline", headers=_hdr,
                        json={"deadline": f"2026-12-{20 + i:02d} 09:00:00"})
        chk(r.status_code == 200, f"★★★ {i}번째 재개는 성공한다(200)", (r.status_code, r.get_json()))
        row = conn.execute("SELECT status, reopen_count FROM auctions WHERE id=?", (aid,)).fetchone()
        chk(row["status"] == "진행", f"  {i}번째 재개 후 상태가 '진행'", dict(row))
        chk(row["reopen_count"] == i, f"★★★ {i}번째 재개 후 reopen_count == {i}", dict(row))
        # 다음 반복을 위해 "연장한 마감도 다시 지났다"를 흉내낸다(실서비스에서는
        # sweep_auctions 가 뒤에 이 상태전이를 만든다 — 이 테스트는 그 스윕을
        # 직접 부르지 않고 결과 상태만 재현한다).
        conn.execute("UPDATE auctions SET status='마감' WHERE id=?", (aid,))
        conn.commit()

    # 상한(3회)을 채운 뒤 4번째 시도는 막힌다.
    r4 = admin.post(f"/api/auctions/{aid}/deadline", headers=_hdr,
                      json={"deadline": "2026-12-31 09:00:00"})
    chk(r4.status_code == 409 and r4.get_json().get("code") == "MAX_EXTEND",
        "★★★★★ 상한(3회) 도달 후 4번째 재개는 409(MAX_EXTEND)로 막힌다"
        "(고치기 전엔 무제한으로 계속 성공했다)", (r4.status_code, r4.get_json()))
    row_after = conn.execute("SELECT status, reopen_count FROM auctions WHERE id=?", (aid,)).fetchone()
    chk(row_after["status"] == "마감", "  막힌 뒤에도 상태는 그대로 '마감'(되돌리지 않음)", dict(row_after))
    chk(row_after["reopen_count"] == A.MAX_REOPEN,
        "  막힌 뒤에는 reopen_count 도 더 안 늘어난다", dict(row_after))

    # [3] 대조군 — 원경매(change_order_id IS NULL)는 여전히 이 경로로 못 되살아난다.
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R513-C2','입찰중','가드레일','서울',0)").lastrowid
    aid2 = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,NULL,'원경매',0,'마감',0,0,0,?,?)", (cid2, DB.now(), DB.now())).lastrowid
    conn.commit()
    r5 = admin.post(f"/api/auctions/{aid2}/deadline", headers=_hdr,
                      json={"deadline": "2026-12-31 09:00:00"})
    chk(r5.status_code == 409 and r5.get_json().get("code") != "MAX_EXTEND",
        "대조 — 원경매는 이 경로로 못 되살아난다(회귀 없음, MAX_EXTEND 가 아닌 "
        "'진행 중인 경매가 아닙니다' 사유로 막힌다)", (r5.status_code, r5.get_json()))

    # [3b] 대조군 — 원경매가 api_case_reopen()으로 이미 reopen_count==MAX_REOPEN까지
    #      썼어도(그 함수 본연의 상한 소진), 그 뒤 이 경로(/deadline)로 오면
    #      "재개 상한 도달"이 아니라 여전히 "재경매가 아니다"로 막혀야 한다 —
    #      두 함수가 같은 컬럼을 서로 다른 뜻으로 읽어 메시지가 뒤섞이면 안 된다.
    cid3 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R513-C3','입찰중','가드레일','서울',0)").lastrowid
    aid3 = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at,reopen_count) "
        "VALUES(?,NULL,'원경매',0,'마감',0,0,0,?,?,?)",
        (cid3, DB.now(), DB.now(), A.MAX_REOPEN)).lastrowid
    conn.commit()
    r6 = admin.post(f"/api/auctions/{aid3}/deadline", headers=_hdr,
                      json={"deadline": "2026-12-31 09:00:00"})
    chk(r6.status_code == 409 and r6.get_json().get("code") != "MAX_EXTEND",
        "★★★ 원경매의 reopen_count가 이미 MAX_REOPEN이어도 이 경로는 여전히 "
        "'재경매가 아님' 사유로 막힌다(컬럼은 같아도 두 함수의 의미가 안 섞인다)",
        (r6.status_code, r6.get_json()))

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드513 서버측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌림-증명 — 라운드513 이전 SQL 그대로면 상한이 정말 없었는가")
# ──────────────────────────────────────────────────────────────


def _mkdb():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE auctions(id INTEGER PRIMARY KEY, change_order_id INTEGER,
                               status TEXT, deadline TEXT, reopen_count INTEGER DEFAULT 0);
    """)
    #  reopen_count=5 — 이미 상한(3)을 훌쩍 넘긴 값으로 시작한다.
    conn.execute("INSERT INTO auctions(id,change_order_id,status,deadline,reopen_count) "
                 "VALUES (1,100,'마감','2026-01-01 00:00:00',5)")
    conn.commit()
    return conn


try:
    old_conn = _mkdb()
    #  라운드513 이전 실제 코드가 쓰던 SQL 그대로(상한 검사 없음) — 5번 반복해도
    #  전부 성공(rowcount==1)해야 "이 테스트가 진짜 결함을 잡아낼 능력이 있다"가 증명된다.
    all_succeeded = True
    for i in range(5):
        cur = old_conn.execute(
            "UPDATE auctions SET status='진행', deadline=? "
            " WHERE id=? AND status='마감' AND change_order_id IS NOT NULL",
            (f"2026-02-{10 + i:02d} 00:00:00", 1))
        old_conn.execute("UPDATE auctions SET status='마감' WHERE id=1")  # 다음 반복 위해 다시 마감
        all_succeeded = all_succeeded and (cur.rowcount == 1)
    chk(all_succeeded,
        "★★★★★ 옛 SQL(상한 검사 없음)은 reopen_count=5(이미 상한 초과)여도 "
        "5번 다 무조건 성공한다 — 이 회귀가 실제로 막던 결함을 재현", all_succeeded)
    old_conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [4] 되돌림-증명", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
