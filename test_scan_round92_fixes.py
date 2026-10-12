# -*- coding: utf-8 -*-
"""스캔 92라운드 회귀 — 실적·표본 통계 4곳이 죽은 컬럼(stats_exclude)으로 데모를 거르려 했다.

  ⚠⚠ `stats_exclude` 컬럼은 스키마 정의(db.py)와 단위테스트 픽스처 한 곳 말고는
    이 저장소 어디에서도 값을 쓴 적이 없다(grep 으로 확인) — `COALESCE(
    stats_exclude,0)=0` 은 항상 참이라 사실상 아무것도 걸러내지 못했다.
    실제 데모 표식은 진작에 `is_demo`(13개 테이블)로 완전히 갈아탔는데
    다음 4곳만 갈아타지 못하고 남아 있었다:
      ① _resync_partner_stats(사건 완료 시 자동 재계산 — jobs_done/win_rate)
      ② /api/admin/recount-partner-stats(전체 일괄 재계산, 같은 공식)
      ③ /api/outcome-stats(공종별 실적 표본 현황)
      ④ /api/est-bands(가견적 점검 기준의 낙찰 표본 수)
    ①의 jobs_done 은 보험사가 보는 낙찰후보 하자율 점수(`s_def=1-dcnt/jobs`)의
    분모로 그대로 들어간다 — 데모 완료건이 많을수록 실적 있는 업체일수록
    근거 없는 감점을 더 크게 받는다.

      python test_scan_round92_fixes.py
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

print("═" * 72)
print("  스캔 92라운드 회귀 — 실적·표본 통계 4곳의 죽은 컬럼(stats_exclude) 제거")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스: stats_exclude 가 저장소에서 완전히 사라졌다")
# ──────────────────────────────────────────────────────────────
resync_body = _py_fn_body(APP_SRC, "_resync_partner_stats")
recount_body = _py_fn_body(APP_SRC, "api_recount_partner_stats")
outcome_body = _py_fn_body(APP_SRC, "api_outcome_stats")
bands_body = _py_fn_body(APP_SRC, "api_est_bands")
chk(resync_body.count("COALESCE(c.is_demo,0)=0") == 1
    and resync_body.count("COALESCE(c2.is_demo,0)=0") == 1,
    "★★★ _resync_partner_stats 가 is_demo 로 데모를 거른다(형제와 동일 공식)")
chk(recount_body.count("COALESCE(c.is_demo,0)=0") == 1
    and recount_body.count("COALESCE(c2.is_demo,0)=0") == 1,
    "★★★ api_recount_partner_stats 가 같은 공식(is_demo)을 쓴다")
chk("COALESCE(c.is_demo,0)=0" in outcome_body,
    "★★ api_outcome_stats(공종별 실적 표본)도 is_demo 로 거른다")
chk("COALESCE(is_demo,0)=0" in bands_body,
    "★★ api_est_bands(낙찰 표본 수)도 is_demo 로 거른다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행: 데모 완료건이 시행사 실적(jobs_done)에 안 잡힌다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round92_")
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
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','최고관리자')")
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R92업체','시행사','활성')"
    ).lastrowid
    #  ⚠ [라운드93] award_route='경매' 를 명시한다 — 93라운드부터 이 두 통계가
    #    경매 낙찰(award_route='경매')만 표본으로 세고 1차합의는 뺀다. 이
    #    픽스처는 "정상 카운트되는 완료 사건"을 만드는 게 목적이라 auction으로
    #    표시해 둔다(93라운드 자신의 테스트가 경매/1차합의 분리를 별도로 검증).
    conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,award_amount,"
        "                  award_route,is_demo) "
        "VALUES('R92-REAL','완료','가드레일','서울',?,5000000,'경매',0)", (pid,))
    conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,award_amount,"
        "                  award_route,is_demo) "
        "VALUES('R92-DEMO','완료','가드레일','서울',?,5000000,'경매',1)", (pid,))
    conn.commit(); conn.close()

    admin = A.app.test_client()
    _tok = "r92-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    r = admin.post("/api/admin/recount-partner-stats", headers=_hdr)
    chk(r.status_code == 200, "STEP 전체 재계산 요청 자체는 200으로 처리된다", r.status_code)

    c = DB.get_db()
    jobs = c.execute("SELECT jobs_done FROM partners WHERE id=?", (pid,)).fetchone()["jobs_done"]
    c.close()
    chk(jobs == 1,
        "★★★ 실제 완료건 1건만 잡힌다(예전엔 죽은 필터 탓에 데모까지 2건으로 잡혔다)",
        f"jobs_done={jobs}")

    # 자동 재계산(_resync_partner_stats) 경로도 같은 공식이므로 직접 호출로 확인.
    conn = DB.get_db()
    conn.execute("UPDATE partners SET jobs_done=99 WHERE id=?", (pid,))  # 오염값으로 세팅
    conn.commit()
    A._resync_partner_stats(conn, pid)
    conn.commit()
    jobs2 = conn.execute("SELECT jobs_done FROM partners WHERE id=?", (pid,)).fetchone()["jobs_done"]
    conn.close()
    chk(jobs2 == 1,
        "★★★ 사건완료 시 자동 재계산(_resync_partner_stats)도 데모를 제외한 1건만 센다",
        f"jobs_done={jobs2}")

    # ══════════════════════════════════════════════════════════
    print("\n[3] 실행: 공종별 실적 표본·낙찰 표본 수도 데모를 제외한다")
    # ──────────────────────────────────────────────────────────
    conn = DB.get_db()
    c_real = conn.execute("SELECT id FROM cases WHERE case_no='R92-REAL'").fetchone()["id"]
    c_demo = conn.execute("SELECT id FROM cases WHERE case_no='R92-DEMO'").fetchone()["id"]
    #  ⚠ [라운드93] bid_count 를 채운다 — 93라운드부터 api_outcome_stats 가
    #    est_outcome.bid_count IS NOT NULL(=경매 표본)만 센다. 이 픽스처는
    #    "정상 카운트되는 경매 표본"이 목적이라 3으로 채워 둔다.
    conn.execute(
        "INSERT INTO est_outcome(case_id,major,bid_count,award_amount,partner_id,created_at) "
        "VALUES(?,'가드레일·방호울타리',3,5000000,?,?)", (c_real, pid, DB.now()))
    conn.execute(
        "INSERT INTO est_outcome(case_id,major,bid_count,award_amount,partner_id,created_at) "
        "VALUES(?,'가드레일·방호울타리',3,5000000,?,?)", (c_demo, pid, DB.now()))
    conn.commit(); conn.close()

    jo = admin.get("/api/outcome-stats").get_json()
    total_n = sum(m["n"] for m in jo.get("by_major", []))
    chk(total_n == 1,
        "★★★ 공종별 실적 표본이 데모 1건을 빼고 실제 1건만 센다", f"total={total_n}")

    je = admin.get("/api/est-bands").get_json()
    chk(je.get("award_samples") == 1,
        "★★★ 낙찰 표본 수(award_samples)도 데모를 빼고 1건만 센다",
        je.get("award_samples"))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드92 서버측 준비/실행", f"{type(e).__name__} {e}")
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
