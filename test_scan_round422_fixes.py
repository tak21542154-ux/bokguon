# -*- coding: utf-8 -*-
"""스캔 422라운드 회귀 — api_insurer_bids()(app.py:4222-, 보험사 포털의 낙찰
   후보 조회)가 `SELECT b.*`로 bids 테이블을 통째로 받아 형제(api_insurer_
   case_detail, 9495행 부근 — 이미 화이트리스트로 좁혀 받음)와 다른 관례를
   쓰던 결함(정밀조사 Agent 발견 — 각도1: 역할별 API 응답 필드 과다노출 조사
   중 부기된 관찰). 지금은 bids 테이블에 민감 컬럼이 없어 실제 유출은 없지만
   (직접 컬럼 목록 대조 확인), 나중에 내부용 컬럼이 추가되면 이 자리만
   조용히 새는 스키마드리프트 위험이 있다.

   고침: bids 의 현재 컬럼 11개(id·auction_id·partner_id·partner_name·
   amount·days·created_at·is_demo·first_bid_at·voided_at·void_reason)를
   전부 나열한 화이트리스트로 교체 — 지금 당장의 동작은 완전히 동일(제거된
   필드 없음), 새 컬럼이 추가돼도 여기 명시적으로 추가하지 않는 한 자동으로
   안 새는 것만 달라진다.

       python test_scan_round422_fixes.py
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


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 422라운드 회귀 — api_insurer_bids() SELECT b.* 스키마드리프트")
print("=" * 72)

print("\n[1] 소스 확인")
_i0 = APP_SRC.index("def api_insurer_bids(")
_i1 = APP_SRC.index("\ndef ", _i0 + 1)
_body = APP_SRC[_i0:_i1]
chk("SELECT b.*" not in _body,
    "★★★★★ api_insurer_bids() 가 더는 b.* 를 안 쓴다")
chk("b.void_reason" in _body and "b.first_bid_at" in _body,
    "★★★★ bids 의 현재 컬럼 전부를 명시적으로 나열한다")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round422_")
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
    conn.execute("INSERT INTO insurers(name,status) VALUES('R422보험사','활성')")
    iid = conn.execute("SELECT id FROM insurers WHERE name='R422보험사'").fetchone()["id"]
    conn.execute("INSERT INTO partners(name,login_id,password_hash,status,partner_type,"
                 "rating,jobs_done,region) VALUES('R422업체','r422p','x','활성','시공사',4.5,10,'서울')")
    pid = conn.execute("SELECT id FROM partners WHERE login_id='r422p'").fetchone()["id"]
    conn.execute("INSERT INTO cases(case_no,status,is_demo,insurer_id,region) "
                 "VALUES('R422-CASE','입찰중',0,?,'서울')", (iid,))
    cid = conn.execute("SELECT id FROM cases WHERE case_no='R422-CASE'").fetchone()["id"]
    conn.execute("INSERT INTO auctions(case_id, deadline, status) "
                 "VALUES(?, datetime('now','+1 hours'), '진행')", (cid,))
    aid = conn.execute("SELECT id FROM auctions WHERE case_id=?", (cid,)).fetchone()["id"]
    conn.execute("INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
                 "VALUES(?,?,?,?,?,?)", (aid, pid, "R422업체", 1000000, 5, DB.now()))
    conn.commit()

    def _insurer_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["insurer_id"] = iid; sess["insurer_login"] = "r422insurer"
            sess["insurer_name"] = "R422보험사"; sess["_csrf"] = "r422-csrf"
        return c

    print("\n[3] 실행 — 정상 응답에 기존 필드가 전부 그대로 있다(회귀없음)")
    c1 = _insurer_client()
    r1 = c1.get(f"/api/insurer/cases/{cid}/bids")
    chk(r1.status_code == 200, "  200 응답(회귀없음)", r1.status_code)
    b0 = (r1.get_json() or {}).get("bids", [{}])[0]
    for f in ("id", "amount", "days", "partner_name", "rating", "jobs_done", "p_region"):
        chk(f in b0, f"  기존 필드 '{f}' 가 응답에 그대로 있다(회귀없음)", b0)

    print("\n[4] 실행 — 나중에 bids 에 민감 컬럼이 추가돼도 안 새는지 실측")
    #  ⚠ 실제로 스키마를 바꿔(가상의 미래 시나리오) 화이트리스트가 정말
    #    작동하는지 확인한다 — b.* 였다면 이 값이 그대로 샜을 것이다.
    conn.execute("ALTER TABLE bids ADD COLUMN internal_cost_note TEXT")
    conn.execute("UPDATE bids SET internal_cost_note='내부 원가 메모(보험사 비공개)' WHERE id=?",
                 (conn.execute("SELECT id FROM bids WHERE auction_id=?", (aid,)).fetchone()["id"],))
    conn.commit()
    c2 = _insurer_client()
    r2 = c2.get(f"/api/insurer/cases/{cid}/bids")
    b1 = (r2.get_json() or {}).get("bids", [{}])[0]
    chk("internal_cost_note" not in b1,
        "★★★★★ 나중에 추가된 민감 컬럼은 화이트리스트 덕에 응답에 안 샌다"
        "(고치기 전엔 b.* 라 자동으로 샜을 것)", b1)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 되돌리기 — 옛 코드(b.*)로 되돌리면 새 컬럼이 실제로 새는가")
# ------------------------------------------------------------
#  ⚠⚠ [라운드617] on-disk 되돌리기(파일에 직접 쓰고 subprocess 로, 별도
#    스크래치 DB 까지 새로 차려 재현)를 인메모리 exec 로 이관 —
#    api_insurer_bids() 는 @require_insurer 데코레이터가 달린 단일 Flask
#    라우트 핸들러라 A.app.view_functions 딕셔너리 항목만 잠깐 치환한다.
#    신설 함수는 _api_insurer_bids_pre422 로 리네임해 사본 이름공간에 exec
#    한 뒤, 실 모듈의 A.require_insurer 로 다시 감싸 인증 동작은 그대로
#    유지한다(round417 이 정착시킨 기법1). [4]에서 이미 같은 프로세스·같은
#    스크래치 DB 에 internal_cost_note 컬럼과 값을 심어 놨으므로 새 DB를
#    또 차릴 필요 없이 그대로 재사용한다 — 실제 파일은 이제 전혀 안 건드린다.

NEW_QUERY = '''    bids = rows(conn.execute(
        """SELECT b.id, b.auction_id, b.partner_id, b.partner_name, b.amount, b.days,
                  b.created_at, b.is_demo, b.first_bid_at, b.voided_at, b.void_reason,
                  p.rating, p.jobs_done, p.region AS p_region
           FROM bids b LEFT JOIN partners p ON p.id=b.partner_id
           WHERE b.auction_id IN (SELECT id FROM auctions
                                   WHERE case_id=? AND change_order_id IS NULL)
             AND b.voided_at IS NULL
             --  퇴출·정지된 업체의 입찰은 후보로 보여 주지 않는다(고르면 교착이다)
             AND COALESCE(p.status,'활성') = '활성'
           ORDER BY b.amount ASC""", (cid,)))'''
OLD_QUERY = '''    bids = rows(conn.execute(
        """SELECT b.*, p.rating, p.jobs_done, p.region AS p_region
           FROM bids b LEFT JOIN partners p ON p.id=b.partner_id
           WHERE b.auction_id IN (SELECT id FROM auctions
                                   WHERE case_id=? AND change_order_id IS NULL)
             AND b.voided_at IS NULL
             --  퇴출·정지된 업체의 입찰은 후보로 보여 주지 않는다(고르면 교착이다)
             AND COALESCE(p.status,'활성') = '활성'
           ORDER BY b.amount ASC""", (cid,)))'''


def _py_fn_body(src, fn_name):
    """함수 본문 — 다음 def뿐 아니라 다음 라우트의 @app. 데코레이터가 먼저
    나오면 거기서 자른다(round610 정착 기법)."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


try:
    chk(APP_SRC.count(NEW_QUERY) == 1, "  (준비) 되돌리기 대상 텍스트가 유일하게 식별된다")
    reverted = APP_SRC.replace(NEW_QUERY, OLD_QUERY)
    chk(reverted != APP_SRC, "  (준비) 되돌리기 텍스트가 실제로 달라졌다")

    _body422 = _py_fn_body(APP_SRC, "api_insurer_bids")
    chk(NEW_QUERY in _body422, "  (준비) api_insurer_bids() 본문 안에 NEW_QUERY가 있다")
    _old_body422 = (_body422
                    .replace("def api_insurer_bids(cid):", "def _api_insurer_bids_pre422(cid):", 1)
                    .replace(NEW_QUERY, OLD_QUERY, 1))
    chk(_old_body422.count(OLD_QUERY) == 1 and "_api_insurer_bids_pre422" in _old_body422,
        "  (준비) 함수 리네임 + 되돌리기가 정확히 적용됐다(실제 파일은 안 건드림)")

    _ns422 = dict(vars(A))
    exec(compile(_old_body422, "<round422_pre422_insurer_bids>", "exec"), _ns422)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_bids_fn = A.require_insurer(_ns422["_api_insurer_bids_pre422"])

    #  [4]에서 이미 이 스크래치 DB(같은 프로세스)에 internal_cost_note 컬럼과
    #  값을 심어 놨다 — 새 DB를 또 차릴 필요 없이 그대로 재사용한다.
    _orig_view422 = A.app.view_functions["api_insurer_bids"]
    A.app.view_functions["api_insurer_bids"] = old_bids_fn
    try:
        c3 = _insurer_client()
        r_old = c3.get(f"/api/insurer/cases/{cid}/bids")
    finally:
        A.app.view_functions["api_insurer_bids"] = _orig_view422

    b_old = (r_old.get_json() or {}).get("bids", [{}])[0]
    chk("internal_cost_note" in b_old,
        "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림)는 나중에 추가된 민감 컬럼을 "
        "그대로 흘린다(인과관계 직접증명)", b_old)

    chk(A.app.view_functions["api_insurer_bids"] is _orig_view422,
        "  view_functions가 원래 함수객체로 복원됐다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
