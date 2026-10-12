# -*- coding: utf-8 -*-
"""스캔 530라운드 회귀 — app.py에서 통째로 사라졌던 마감판정 상수 5개 복원.

   직전 529라운드가 배터리를 두 번 독립 실행했는데 무관한 다수 테스트
   (round414·433·435·443·477·484·492·521·522·523·526 등)가 동시에 실패하는
   현상을 발견했다. 원인을 AUCTION_EXPIRED_SQL·REAUCTION_HOURS_DEFAULT·
   MIN_BIDDERS_DEFAULT 세 이름의 미정의로 좁혔지만, 동시편집 중인 다른
   세션의 미완성 작업일 가능성 때문에 손대지 않고 재기동을 보류했다.

   이번 530라운드가 직접 재조사(하위위임 없음) — 시간이 지나도 세 이름이
   여전히 미정의였다. 게다가 grep 이 아니라 AST 로 app.py 전체의
   Load/Store 바인딩을 대조해 보니 대상이 세 개가 아니라 **다섯 개**였다:
   위 세 개에 더해 AUCTION_HOURS_DEFAULT·LOW_PRICE_ALERT_DEFAULT 도 같은
   자리(3782~3794행, _min_bidders·_low_price_alert_pct·_auction_hours·
   _reauction_hours 네 헬퍼가 나란히 참조)에서 함께 사라져 있었다 —
   bokguon.log 의 오늘(2026-09-09)자 라이브 트레이스백에도 이 다섯 이름의
   NameError 가 실제로 찍혀 있어(다른 동시 세션이 띄운 서버가 이 파일을
   그대로 물고 있었다는 뜻) 별개 결함이 아니라 같은 삭제사고의 일부임을
   확인했다.

   복원값 근거(창작 아님, 전부 기존 흔적에서 역산):
     · MIN_BIDDERS_DEFAULT=3·LOW_PRICE_ALERT_DEFAULT=20·AUCTION_HOURS_
       DEFAULT=48·REAUCTION_HOURS_DEFAULT=24 — db.py 두 자리(1541행 마이그
       레이션 seed, 2143~2151행 신규DB seed)가 서로 다른 시점에 독립적으로
       똑같은 값을 명시하고 있다.
     · AUCTION_EXPIRED_SQL — app.py 5917행(sweep_auctions 내부)에 같은
       판정식의 인라인 사본이 별칭(a.)만 붙은 채 그대로 남아 있었다:
       "a.deadline IS NOT NULL AND a.deadline <= datetime('now','+9 hours')".
       AUCTION_EXPIRED_SQL 의 모든 호출부(5181·5373·5887·10537·10857·
       20411행)는 별칭 없는 단일 auctions 조회라 별칭만 벗겨 복원했다.
       이 식의 부정(NOT)이 다른 여러 자리(4700·4756·12014·21074·21108행)의
       "deadline IS NULL OR deadline > datetime(...)" 형태와 드모르간
       법칙으로 정확히 일치함도 대조해 확인했다(3값 논리 포함 — deadline
       이 NULL이면 양쪽 다 "만료 아님"으로 일치).

   회귀 검사 — [1] 소스: 다섯 상수가 전부 정의됨. [2] 실행: 스크래치 DB로
   네 헬퍼(_min_bidders 등)를 직접 호출해 NameError 없이 돌고 db.py 시드와
   값이 일치. [3] 실행: 원경매를 실제로 열어(_open_original_auction →
   _auction_hours 경유) AUCTION_EXPIRED_SQL 이 미래 마감엔 안 걸리고 과거
   마감엔 걸림을 대조. [4] 실행: sweep_auctions() 를 force=True로 실제
   호출해(MIN_BIDDERS_DEFAULT·AUCTION_EXPIRED_SQL 둘 다 이 한 경로 안에서
   쓰인다) NameError 없이 끝까지 돌아 사건이 '승인대기'로 전환됨을 확인.

       python test_scan_round530_fixes.py
"""
import ast
import io
import os
import sys
import tempfile

#  ⚠ 윈도 기본 콘솔은 cp949 라 em dash(—) 같은 문자를 print 하면
#    UnicodeEncodeError 로 죽는다 — 형제 테스트(round528·529 등)가 이미 쓰는
#    방어를 그대로 옮긴다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 530라운드 회귀 — 마감판정 상수 5개 복원(NameError)")
print("=" * 72)

# ══════════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 다섯 상수가 전부 app.py 에 정의돼 있다(AST 바인딩 분석)")
# ══════════════════════════════════════════════════════════════════
APP_SRC = open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
_tree = ast.parse(APP_SRC)
_assigned = set()
for _node in ast.walk(_tree):
    if isinstance(_node, ast.Name) and isinstance(_node.ctx, ast.Store):
        _assigned.add(_node.id)

NAMES = ("MIN_BIDDERS_DEFAULT", "LOW_PRICE_ALERT_DEFAULT",
         "AUCTION_HOURS_DEFAULT", "REAUCTION_HOURS_DEFAULT",
         "AUCTION_EXPIRED_SQL")
for _name in NAMES:
    chk(_name in _assigned, f"★★★★★ {_name} 이 정의돼 있다(더 이상 NameError 원천이 아님)")

# ══════════════════════════════════════════════════════════════════
print("\n[2] 실행 — 스크래치 DB 로 네 헬퍼를 직접 호출, NameError 없이 도는가 · 값도 맞는가")
# ══════════════════════════════════════════════════════════════════
_tmpdir = tempfile.mkdtemp(prefix="round530_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
os.environ.setdefault("BOKGUON_LOG_FILE", os.path.join(_tmpdir, "test.log"))
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()

    chk(A.MIN_BIDDERS_DEFAULT == 3, "MIN_BIDDERS_DEFAULT == 3(db.py 시드와 일치)",
        A.MIN_BIDDERS_DEFAULT)
    chk(A.LOW_PRICE_ALERT_DEFAULT == 20, "LOW_PRICE_ALERT_DEFAULT == 20",
        A.LOW_PRICE_ALERT_DEFAULT)
    chk(A.AUCTION_HOURS_DEFAULT == 48, "AUCTION_HOURS_DEFAULT == 48",
        A.AUCTION_HOURS_DEFAULT)
    chk(A.REAUCTION_HOURS_DEFAULT == 24, "REAUCTION_HOURS_DEFAULT == 24",
        A.REAUCTION_HOURS_DEFAULT)

    vals = (A._min_bidders(conn), A._low_price_alert_pct(conn),
            A._auction_hours(conn), A._reauction_hours(conn))
    chk(True, "★★★★★ _min_bidders/_low_price_alert_pct/_auction_hours/"
              "_reauction_hours 네 헬퍼가 NameError 없이 실행된다(여기 도달 자체가 증거)")
    chk(vals == (3, 20, 48, 24),
        "  빈 settings 에서도 db.py 시드 기본값과 같은 값을 돌려준다(3,20,48,24)", vals)

    # ══════════════════════════════════════════════════════════════
    print("\n[3] 실행 — 원경매를 실제로 열어 AUCTION_EXPIRED_SQL 이 미래/과거 마감을 올바로 가른다")
    # ══════════════════════════════════════════════════════════════
    conn.execute("INSERT INTO insurers(name,status) VALUES('R530보험사','활성')")
    iid = conn.execute("SELECT id FROM insurers WHERE name='R530보험사'").fetchone()["id"]
    conn.execute(
        "INSERT INTO partners(name,login_id,password_hash,status,partner_type,"
        "rating,jobs_done,region) VALUES('R530업체','r530p','x','활성','시행사',4.5,10,'서울')")
    pid = conn.execute("SELECT id FROM partners WHERE login_id='r530p'").fetchone()["id"]
    conn.execute(
        """INSERT INTO cases(case_no, insurer_id, insurer, category, region, address,
                             est_price, low_price, status, created_at)
           VALUES('R530-CASE',?,?,?,?,?,?,0,'입찰중',?)""",
        (iid, "R530보험사", "가드레일·방호울타리", "서울", "검증용", 10_000_000, DB.now()))
    cid = conn.execute("SELECT id FROM cases WHERE case_no='R530-CASE'").fetchone()["id"]
    conn.execute("INSERT INTO work_lots(case_id,category,status,created_at) "
                 "VALUES(?,?,'입찰중',?)", (cid, "가드레일·방호울타리", DB.now()))
    #  ⚠ hours=None(기본값) 으로 불러 AUCTION_HOURS_DEFAULT 경유 경로까지 같이 태운다.
    aid = A._open_original_auction(conn, cid)
    conn.commit()

    n_future = conn.execute(
        f"SELECT COUNT(*) FROM auctions WHERE id=? AND {A.AUCTION_EXPIRED_SQL}",
        (aid,)).fetchone()[0]
    chk(n_future == 0, "★★★★ 방금 연 경매(미래 마감)는 AUCTION_EXPIRED_SQL 에 안 걸림", n_future)
    alive = conn.execute(
        f"SELECT 1 FROM auctions WHERE id=? AND NOT {A.AUCTION_EXPIRED_SQL}", (aid,)).fetchone()
    chk(alive is not None, "  NOT AUCTION_EXPIRED_SQL 로는 '아직 살아있음'이 잡힌다")

    conn.execute("UPDATE auctions SET deadline=datetime('now','+9 hours','-1 hours') "
                 "WHERE id=?", (aid,))
    conn.commit()

    n_past = conn.execute(
        f"SELECT COUNT(*) FROM auctions WHERE id=? AND {A.AUCTION_EXPIRED_SQL}",
        (aid,)).fetchone()[0]
    chk(n_past == 1, "★★★★★ 마감시각이 지나면 AUCTION_EXPIRED_SQL 이 실제로 걸린다", n_past)
    alive2 = conn.execute(
        f"SELECT 1 FROM auctions WHERE id=? AND NOT {A.AUCTION_EXPIRED_SQL}", (aid,)).fetchone()
    chk(alive2 is None, "  마감 뒤에는 NOT AUCTION_EXPIRED_SQL 로 안 잡힌다(일관성)")

    # ══════════════════════════════════════════════════════════════
    print("\n[4] 실행 — sweep_auctions() 전체 경로(MIN_BIDDERS_DEFAULT+AUCTION_EXPIRED_SQL 동시사용)")
    # ══════════════════════════════════════════════════════════════
    conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,?,?,?)", (aid, pid, "R530업체", 9_000_000, 5, DB.now()))
    conn.commit()

    r = A.sweep_auctions(conn, force=True)
    chk(r.get("errors", 1) == 0,
        "★★★★★ sweep_auctions() 이 NameError 를 삼키지 않고(errors==0) 끝까지 돈다", r)
    c = conn.execute("SELECT status FROM cases WHERE id=?", (cid,)).fetchone()
    chk(bool(c) and c["status"] == "승인대기",
        "  입찰 1건(최소성립 3 미달)으로 마감 → 사건이 '승인대기'로 전환됨(자동유찰 아님)",
        dict(c) if c else None)
    au = conn.execute("SELECT status FROM auctions WHERE id=?", (aid,)).fetchone()
    chk(bool(au) and au["status"] == "마감", "  경매 자체도 '마감'으로 전환됨")

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행 중 예외 없음", f"{type(e).__name__}: {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
