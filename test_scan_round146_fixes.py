# -*- coding: utf-8 -*-
"""스캔 146라운드 회귀 — 개인정보 처리방침 제3조가 공개 약속한 "하자보수 관련
기록(준공일로부터 하자담보책임기간(24개월) 만료 후 3년 파기)"을 실행하는
코드가 manage.py cmd_prune_personal 어디에도 없던 결함.

  ⚠ 행 자체는 지우지 않는다 — severity·status·cost_bearer 는 partner_rating()의
    귀책 하자 감점 집계가 계속 참조하는 통계값이라, 행을 통째로 지우면 오래된
    협력사일수록 감점 이력이 사라져 평점이 부당하게 좋아 보인다. 개인/식별
    소지가 있는 자유텍스트(제목·내용·처리결과·접수자)만 지운다.

      python test_scan_round146_fixes.py
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


MANAGE_SRC = read("manage.py")
LEGAL_SRC = read("legal_docs.py")

print("=" * 72)
print("  스캔 146라운드 회귀 — 하자보수 관련 기록 보유기간(처리방침 제3조) 미이행")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk("하자보수 관련 기록" in LEGAL_SRC and "만료 후 3년" in LEGAL_SRC,
    "★ (전제) 처리방침 제3조가 이 보유기간을 실제로 공개 약속하고 있다")
i_pp = MANAGE_SRC.index("def cmd_prune_personal(")
i_pp_end = MANAGE_SRC.index("\ndef ", i_pp + 1)
pp_body = MANAGE_SRC[i_pp:i_pp_end]
chk('"SELECT COUNT(*) n FROM defects" + _dwhere' in pp_body,
    "★★★ cmd_prune_personal 이 이제 defects 대상 건수를 센다")
#  ⚠⚠ [라운드194] '+3 years' 계산 자체가 _DEFECT_PURGE_AT 상수로 옮겨졌다
#    (그 자리에서 SQLite 의 +N years 윤년 말일 오버플로우까지 마저 보정하기
#    위해서다 — cmd_prune_personal 은 이제 그 상수를 참조만 한다).
chk("_DEFECT_PURGE_AT" in pp_body,
    "★★★ _WEND(하자담보 만료, app.py _warranty_left 와 같은 말일보정) 뒤 3년을 더한다"
    "(처리방침 문구와 일치 — 그 산식은 _DEFECT_PURGE_AT 에 있다)")
chk("+3 years" in MANAGE_SRC[MANAGE_SRC.index("_DEFECT_PURGE_AT = ("):
                              MANAGE_SRC.index("_DEFECT_PURGE_AT = (") + 600],
    "★★★ _DEFECT_PURGE_AT 자신이 실제로 3년을 더한다")
chk("DELETE FROM defects" not in pp_body,
    "★ defects 행 자체는 지우지 않는다(통계값 보존)")
chk("title='(파기됨)'" in pp_body and "content=NULL" in pp_body
    and "resolution=NULL" in pp_body and "reporter='(파기됨)'" in pp_body,
    "★★★ 제목·내용·처리결과·접수자만 지운다")

# ============================================================
print("\n[2] 실행 — 준공+하자담보(24개월)+3년이 지난 하자 기록은 스크럽되고, 통계값은 남는다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round146_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A
    import manage as M

    conn = DB.get_db()
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region) "
        "VALUES('R146업체','시공사','활성','유리·샷시·자동문','서울')").lastrowid

    #  ── 오래된 사건(2018년 완료) — 준공+24개월+3년이 이미 한참 지났다 ──
    cid_old = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,completed_at,warranty_months,"
        "                  victim_name,victim_phone,is_demo) "
        "VALUES('R146-OLD','완료','유리·샷시·자동문','서울','2018-01-01 10:00:00',24,"
        "       '홍길동','01012345678',0)").lastrowid
    did_old = conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,partner_id,title,content,reporter,"
        "                    reporter_type,status,severity,cost_bearer,created_at) "
        "VALUES('DEF-R146-OLD',?,?,?,'낡은 하자 제목','낡은 내용','김검수','보험사',"
        "       '완료','중대','시행사','2018-06-01 10:00:00')",
        (cid_old, "R146-OLD", pid)).lastrowid

    #  ── 최근 사건(방금 완료) — 아직 보유기간이 한참 남았다(대조군) ──
    cid_new = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,completed_at,warranty_months,"
        "                  is_demo) "
        "VALUES('R146-NEW','완료','유리·샷시·자동문','서울',datetime('now','+9 hours'),24,0)"
    ).lastrowid
    did_new = conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,partner_id,title,content,reporter,"
        "                    reporter_type,status,severity,cost_bearer,created_at) "
        "VALUES('DEF-R146-NEW',?,?,?,'최근 하자 제목','최근 내용','박검수','보험사',"
        "       '완료','중대','시행사',datetime('now','+9 hours'))",
        (cid_new, "R146-NEW", pid)).lastrowid
    conn.commit()

    before_val, before_info = A.partner_rating(conn, pid)
    chk(before_val is None,
        "★ (사전조건) 해피콜 기록이 없어 이 시점엔 평점 자체가 없다(귀책 하자 집계와는 별개 축)",
        (before_val, before_info))
    #  ⚠ partner_rating() 의 하자 집계 질의(app.py)와 정확히 같은 조건으로,
    #    파기 전 두 하자 모두 '중대' 귀책으로 잡히는지 먼저 확인한다.
    ds_before = {r["severity"]: r["n"] for r in conn.execute(
        "SELECT severity, COUNT(*) n FROM defects WHERE partner_id=? AND status='완료' "
        "  AND COALESCE(cost_bearer,'')='시행사' AND COALESCE(is_demo,0)=0 GROUP BY severity",
        (pid,))}
    chk(ds_before.get("중대") == 2,
        "★ (사전조건) 파기 전엔 두 하자(구·신) 모두 귀책 하자 집계에 잡힌다", ds_before)

    rc = M.cmd_prune_personal([])
    chk(rc == 0, "STEP cmd_prune_personal 정상 종료(0)", rc)

    old_row = dict(conn.execute(
        "SELECT title, content, resolution, reporter, severity, status, cost_bearer "
        "FROM defects WHERE id=?", (did_old,)).fetchone())
    chk(old_row["title"] == "(파기됨)" and old_row["content"] is None
        and old_row["resolution"] is None and old_row["reporter"] == "(파기됨)",
        "★★★ 오래된 하자의 제목·내용·처리결과·접수자가 파기된다"
        "(고치기 전엔 2018년 기록이 영구히 원문 그대로 남았다)", old_row)
    chk(old_row["severity"] == "중대" and old_row["status"] == "완료"
        and old_row["cost_bearer"] == "시행사",
        "★★★ 그런데도 심각도·상태·비용부담(통계값)은 그대로 보존된다"
        "(행을 통째로 지웠다면 이 값들도 함께 사라졌을 것이다)", old_row)

    new_row = dict(conn.execute(
        "SELECT title, content, reporter FROM defects WHERE id=?", (did_new,)).fetchone())
    chk(new_row["title"] == "최근 하자 제목" and new_row["reporter"] == "박검수",
        "★★★ 보유기간이 안 지난 최근 하자는 손대지 않는다(과잉파기 아님)", new_row)

    ds_after = {r["severity"]: r["n"] for r in conn.execute(
        "SELECT severity, COUNT(*) n FROM defects WHERE partner_id=? AND status='완료' "
        "  AND COALESCE(cost_bearer,'')='시행사' AND COALESCE(is_demo,0)=0 GROUP BY severity",
        (pid,))}
    chk(ds_after.get("중대") == 2,
        "★★★ 파기 뒤에도 partner_rating() 의 귀책 하자 집계는 그대로 2건이다"
        "(제목·내용만 지웠을 뿐 severity/cost_bearer/status 는 살아있어 통계가 안 깨진다)",
        ds_after)

    log = conn.execute(
        "SELECT detail FROM activity_log WHERE action='개인정보 파기' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    chk(log is not None and "하자보수기록 1" in (log["detail"] or ""),
        "★ activity_log 증적에 하자보수기록 건수가 남는다", dict(log) if log else None)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드146 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
