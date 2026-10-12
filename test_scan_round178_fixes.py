# -*- coding: utf-8 -*-
"""스캔 178라운드 회귀 — sweep_send_notifications 의 "철 지난 출동수배 문자"
일괄취소가 바로 옆 pend 조회가 지키는 only_ids·is_demo·channel 을 하나도
안 지키던 결함.

  only_ids 는 이 함수 docstring 이 명시한 존재 이유(검증·선택발송이 무관한
  운영 건까지 휩쓸지 않게) 그 자체를 이 취소문만 어겼다 — 사람이 발송대기함
  에서 특정 건만 골라 "지금 보내기"를 눌러도, 이 UPDATE 는 시스템 전체의
  철 지난 출동수배 문자를 다 건드렸다. is_demo 는 이 함수 자신의 원칙
  ("데모는 절대 보내지 않는다")과 어긋났다.

      python test_scan_round178_fixes.py
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
print("  스캔 178라운드 회귀 — 철지난 출동수배 문자 일괄취소의 필터 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def sweep_send_notifications(")
i1 = APP_SRC.index("\ndef ", i0 + 1)
body = APP_SRC[i0:i1]
chk("channel IN ('알림톡','문자') AND COALESCE(is_demo,0)=0" in body,
    "★★★ 일괄취소가 channel·is_demo 를 pend 와 같이 지킨다")
i_purge = body.index("SET status='실패',")
i_only_in_purge = body.index("{_only}", i_purge)
i_notexists = body.index("NOT EXISTS", i_purge)
chk(i_purge < i_only_in_purge < i_notexists,
    "★★★ 일괄취소가 {_only}(only_ids 화이트리스트)도 WHERE 안에 넣는다")
chk('out["stale_canceled"] = cur_purge.rowcount' in body,
    "일괄취소 건수가 out 요약에 남는다(감사 가능)")

# ============================================================
print("\n[2] 실행 — only_ids 로 특정 건만 지목해도 무관한 건·데모는 안 건드리는가")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round178_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "test.log")
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A
    import notify_popbill as NP

    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,status,login_id,created_at) "
        "VALUES('R178보험사','활성','r178i',?)", (DB.now(),)).lastrowid

    def mk_stale_case(tag, is_demo):
        cid = conn.execute(
            "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo,created_at) "
            "VALUES(?,?,'가드레일','서울',?,?,?)",
            (f"R178-{tag}", "미수선종결", iid, is_demo, DB.now())).lastrowid
        # 이미 끝난 수배 — status 가 모집중/수배됨이 아니면 "철 지났다"로 판정된다
        conn.execute(
            "INSERT INTO dispatches(case_id,status,is_demo,created_at) "
            "VALUES(?,'실패',?,?)", (cid, is_demo, DB.now()))
        nid = conn.execute(
            """INSERT INTO notifications(ntype,channel,target,message,status,
                   case_id,is_demo,created_at)
               VALUES('출동수배','문자','검증','검증 메시지','발송대기',?,?,?)""",
            (cid, is_demo, DB.now())).lastrowid
        return cid, nid

    cid_target, nid_target = mk_stale_case("TARGET", 0)   # only_ids 로 지목할 건
    cid_other, nid_other = mk_stale_case("OTHER", 0)      # 지목 안 한 무관한 건 — 안전해야 한다
    cid_demo, nid_demo = mk_stale_case("DEMO", 1)         # 데모 — 지목해도 안전해야 한다
    conn.commit()

    real_ready, real_notify_on = NP.ready, A.NOTIFY_ENABLED
    try:
        NP.ready = lambda: True
        A.NOTIFY_ENABLED = True
        res = A.sweep_send_notifications(conn, only_ids=[nid_target, nid_demo])

        def status_of(nid):
            return conn.execute(
                "SELECT status FROM notifications WHERE id=?", (nid,)).fetchone()["status"]

        chk(status_of(nid_target) == "실패",
            "★★★ 지목한 건(nid_target)은 철지난 수배로 정상 취소됨", status_of(nid_target))
        chk(status_of(nid_other) == "발송대기",
            "★★★ 지목 안 한 무관한 건(nid_other)은 그대로 남음"
            "(고치기 전엔 only_ids 와 무관하게 시스템 전체가 휩쓸렸다)", status_of(nid_other))
        chk(status_of(nid_demo) == "발송대기",
            "★★★ 데모 건(nid_demo)은 only_ids 로 직접 지목해도 안전하게 보호됨"
            "(고치기 전엔 데모도 그대로 '실패'로 바뀌었다)", status_of(nid_demo))
        chk(res.get("stale_canceled") == 1,
            "★ 요약(out)에 실제 취소건수(1건)만 정확히 남음", res.get("stale_canceled"))
    finally:
        NP.ready, A.NOTIFY_ENABLED = real_ready, real_notify_on
        conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드178 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
