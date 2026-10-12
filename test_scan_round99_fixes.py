# -*- coding: utf-8 -*-
"""스캔 99라운드 회귀 — cmd_mark_smoke_demo 의 자식표 캐스케이드가 정본과 따로 놀았다.

  db.py 의 정본 캐스케이드(_backfill_child_is_demo)는 bids·dispatches·
  field_agreements·notifications·settlements 를 사건에서 물려받게 하는
  **유일한** 지점이어야 한다(그 자신의 주석: "읽는 23곳을 각각 고치면 새로
  쓰는 질의가 같은 실수를 반복한다"). 그런데 manage.py 의 mark-smoke-demo
  명령은 손으로 또 다른 목록(settlements·auctions·dispatches·photos)을
  들고 있었고, bids·field_agreements·notifications 가 빠진 데다 auctions·
  photos 는 애초에 is_demo 컬럼이 없어(PRAGMA 확인 없이 try/except 로
  삼켜졌다) 매번 조용히 헛일이었다. 그 결과 스모크 데이터에 표식을 붙여도
  협력사 '누적 제출'·관리자 알림벨·보험사 리포트의 1차합의 집계는 계속
  스모크 건을 실적으로 셌다. 정본 함수 하나만 부르도록 바꾼다.

      python test_scan_round99_fixes.py
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


MANAGE_SRC = read("manage.py")

print("═" * 72)
print("  스캔 99라운드 회귀 — mark-smoke-demo 자식표 캐스케이드 정본화")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스: cmd_mark_smoke_demo 가 정본 캐스케이드 함수를 그대로 쓴다")
# ──────────────────────────────────────────────────────────────
msd_body = _py_fn_body(MANAGE_SRC, "cmd_mark_smoke_demo")
chk("DB._backfill_child_is_demo(conn)" in msd_body,
    "★★★ cmd_mark_smoke_demo 가 손으로 나열한 목록 대신 정본 함수를 호출한다")
chk('for t in ("settlements", "auctions", "dispatches", "photos")' not in msd_body,
    "★★ 드리프트된 옛 손목록이 더 이상 안 남아 있다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행: 스모크 표식 이후 bids·field_agreements·notifications 도 데모로 잡힌다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round99_")
_dbpath = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_DB_PATH"] = _dbpath
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("manage_r99", os.path.join(HERE, "manage.py"))
    M = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(M)

    conn = DB.get_db()
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R99업체','시행사','활성')"
    ).lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,address,partner_id,is_demo) "
        "VALUES('E2E-99001','완료','가드레일','서울','스모크 테스트 주소',?,0)", (pid,)).lastrowid
    aid = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,NULL,'원경매',0,'마감',1000000,1,0,?,?)", (cid, DB.now(), DB.now())).lastrowid
    conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,1000000,10,?)", (aid, pid, "R99업체", DB.now()))
    conn.execute(
        "INSERT INTO field_agreements(case_id,partner_id,partner_name,field_amount,"
        "                             status,created_at) VALUES(?,?,?,900000,'합의',?)",
        (cid, pid, "R99업체", DB.now()))
    conn.execute(
        "INSERT INTO notifications(ntype,channel,target,message,status,case_id,created_at) "
        "VALUES('낙찰','웹','운영팀','R99업체 낙찰','전달됨',?,?)", (cid, DB.now()))
    conn.commit()

    rc = M.cmd_mark_smoke_demo([])
    conn2 = DB.get_db()
    case_demo = conn2.execute("SELECT is_demo FROM cases WHERE id=?", (cid,)).fetchone()["is_demo"]
    bid_demo = conn2.execute(
        "SELECT is_demo FROM bids WHERE auction_id=?", (aid,)).fetchone()["is_demo"]
    fa_demo = conn2.execute(
        "SELECT is_demo FROM field_agreements WHERE case_id=?", (cid,)).fetchone()["is_demo"]
    noti_demo = conn2.execute(
        "SELECT is_demo FROM notifications WHERE case_id=?", (cid,)).fetchone()["is_demo"]
    conn2.close()

    chk(rc == 0, "STEP cmd_mark_smoke_demo 자체는 정상 종료한다", rc)
    chk(case_demo == 1, "STEP 사건 자신은 표식이 붙는다(원래도 되던 부분)", case_demo)
    chk(bid_demo == 1,
        "★★★ 입찰(bids)도 이제 데모로 잡힌다(예전엔 손목록에 없어 계속 실적처럼 보였다)",
        bid_demo)
    chk(fa_demo == 1,
        "★★★ 1차합의(field_agreements)도 데모로 잡힌다"
        "(보험사 리포트의 합의 집계가 더는 스모크 건을 안 센다)", fa_demo)
    chk(noti_demo == 1,
        "★★★ 알림(notifications)도 데모로 잡힌다(관리자 알림벨이 더는 스모크 건을 안 보여준다)",
        noti_demo)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드99 서버측 준비/실행", f"{type(e).__name__} {e}")
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
