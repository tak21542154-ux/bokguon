# -*- coding: utf-8 -*-
"""스캔 158라운드 회귀 — 고아 행 점검·정리 목록에서 4개 표가 빠져 있던 결함.

  manage.py 의 CASE_CHILD_TABLES(case_id 로 사건에 붙는 표)·FK_CHILD_TABLES
  (다른 열쇠로 부모에 닿는 표) 는 "점검(check)과 정리(prune-orphans)가 같은
  목록을 봐야 한다"고 스스로 주석까지 달아 뒀는데, 정작 db.py 에 case_id 가
  있는 notifications·schedule_events·contract_gate_log 셋과, auction_id 로
  auctions 에 닿는 bids 가 그 목록에 없었다 — 고아가 있어도 점검은 초록,
  정리 명령도 못 지운다.

  실측(운영 DB 읽기전용 조회, 이 테스트에는 없음): notifications 에 이미
  34건의 고아(없어진 사건을 가리키는 미확인 알림)가 쌓여 있었고, 그중
  14곳은 지금도 로그인 가능한 활성 협력사라 포털 배지에 그대로 노출된다.

      python test_scan_round158_fixes.py
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


APP_SRC = read("manage.py")

print("=" * 72)
print("  스캔 158라운드 회귀 — 고아 행 점검·정리 목록에 빠졌던 4개 표")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
#  ⚠ 첫 ")" 로 자르면 안 된다 — 이 블록 자체의 설명 주석 안에 괄호 닫는
#    글자가 있어(예: "미확인 알림)가") 튜플이 끝나기 한참 전에 잘린다.
#    실제 튜플 끝(줄바꿈 직전의 닫는 괄호)까지 명시적으로 찾는다.
i0 = APP_SRC.index("CASE_CHILD_TABLES = (")
i1 = APP_SRC.index("\n)", i0)
case_block = APP_SRC[i0:i1]
for t in ("notifications", "schedule_events", "contract_gate_log"):
    chk(f'"{t}"' in case_block,
        f"★★★ CASE_CHILD_TABLES 에 {t} 가 등록됐다(case_id 로 사건에 붙는 표)")

i2 = APP_SRC.index("FK_CHILD_TABLES = (")
i3 = APP_SRC.index("\n)", i2)
fk_block = APP_SRC[i2:i3]
chk('("bids", "auction_id", "auctions")' in fk_block,
    "★★★ FK_CHILD_TABLES 에 bids(auction_id→auctions) 가 등록됐다")

# ============================================================
print("\n[2] 실행 — 고아 행이 실제로 잡히고 지워지는가(임시 DB)")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round158_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import manage as M

    conn = DB.get_db()
    #  실제로 있다가 없어지는 사건 하나 — 지운 뒤에도 자식 행은 그대로 남는다
    #  (매니지먼트 스크립트가 잘못 운영 DB 를 겨냥해 사건만 지운 실제 사고와
    #  같은 모양, reference_test_default_db_is_prod.md 참조).
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,created_at) "
        "VALUES('R158-ORPHAN','접수','가드레일','서울',?)", (DB.now(),)).lastrowid
    partner_id = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,created_at) "
        "VALUES('R158업체','시공사','활성','가드레일','서울',?)", (DB.now(),)).lastrowid
    aid = conn.execute(
        "INSERT INTO auctions(case_id,status,created_at) VALUES(?,?,?)",
        (cid, '낙찰', DB.now())).lastrowid
    nid = conn.execute(
        "INSERT INTO notifications(audience_type,partner_id,case_id,ntype,message,created_at) "
        "VALUES('partner',?,?,'현장 출동 수배','테스트',?)", (partner_id, cid, DB.now())).lastrowid
    sid = conn.execute(
        "INSERT INTO schedule_events(title,event_date,case_id,created_at) "
        "VALUES('R158일정','2026-08-28',?,?)", (cid, DB.now())).lastrowid
    gid = conn.execute(
        "INSERT INTO contract_gate_log(case_id,decided_at) VALUES(?,?)",
        (cid, DB.now())).lastrowid
    bid = conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,created_at) "
        "VALUES(?,?,?,?,?)", (aid, partner_id, 'R158업체', 100000, DB.now())).lastrowid
    #  사건과 경매를 지운다 — notifications/schedule_events/contract_gate_log 는
    #  case_id 로, bids 는 auction_id 로 각각 고아가 된다.
    conn.execute("DELETE FROM auctions WHERE id=?", (aid,))
    conn.execute("DELETE FROM cases WHERE id=?", (cid,))
    conn.commit()
    conn.close()

    def _alive(table, rid):
        c = DB.get_db()
        r = c.execute(f"SELECT COUNT(*) n FROM {table} WHERE id=?", (rid,)).fetchone()["n"]
        c.close()
        return r == 1

    chk(_alive("notifications", nid) and _alive("schedule_events", sid)
        and _alive("contract_gate_log", gid) and _alive("bids", bid),
        "★ (사전조건) 부모가 지워진 뒤에도 자식 행 4개는 그대로 남아있다")

    rc = M.cmd_prune_orphans(["--yes"])
    chk(rc == 0, "STEP prune-orphans --yes 실행이 정상 종료한다", rc)

    chk(not _alive("notifications", nid),
        "★★★ 고아가 된 notifications 행이 정리된다(실운영 34건과 같은 종류)")
    chk(not _alive("schedule_events", sid),
        "★★★ 고아가 된 schedule_events 행이 정리된다")
    chk(not _alive("contract_gate_log", gid),
        "★★★ 고아가 된 contract_gate_log 행이 정리된다")
    chk(not _alive("bids", bid),
        "★★★ 고아가 된 bids 행이 정리된다(case_id 가 아니라 auction_id 경유)")

    #  대조군 — 사건과 무관한(case_id/auction_id 가 원래 NULL인) 정상 행은
    #  그대로 남는다(과잉 삭제 아님).
    conn = DB.get_db()
    keep_n = conn.execute(
        "INSERT INTO notifications(audience_type,partner_id,ntype,message,created_at) "
        "VALUES('partner',?, '공지','전체공지',?)", (partner_id, DB.now())).lastrowid
    keep_s = conn.execute(
        "INSERT INTO schedule_events(title,event_date,created_at) "
        "VALUES('R158무관일정','2026-08-29',?)", (DB.now(),)).lastrowid
    conn.commit(); conn.close()
    rc2 = M.cmd_prune_orphans(["--yes"])
    chk(rc2 == 0 and _alive("notifications", keep_n) and _alive("schedule_events", keep_s),
        "★ 사건과 무관한(case_id NULL) 정상 행은 지워지지 않는다(과잉삭제 아님)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드158 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
