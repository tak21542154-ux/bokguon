# -*- coding: utf-8 -*-
"""스캔 93라운드 회귀 — 실적표본 통계 2곳이 경매/1차합의를 안 갈랐다.

  dispatch.py:1041 은 스스로 "award_route 로 경매 건과 구분해 통계가 섞이지
  않게 한다"고 적어 뒀다 — 사진없는 접수가 출동→실견적→보험사 **승인**(경매를
  안 열고 그 업체와 바로 계약, award_route='1차합의')으로 끝나는 경로가 있고,
  이건 경쟁 입찰이 아니라 단독 협상이다. 그런데 /api/outcome-stats·
  /api/est-bands 둘 다 이 컬럼을 한 번도 안 봐서, 경쟁 없는 1차합의 건까지
  "낙찰 표본"에 섞여 OUTCOME_MIN_SAMPLE(=30) 문턱을 채운다 — "근거 없는
  숫자를 화면에 띄우는 것이 이 기능에서 가장 나쁜 결과"라는 이 표들 자신의
  주석과 정반대 상태였다.

      python test_scan_round93_fixes.py
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
print("  스캔 93라운드 회귀 — 실적표본 통계 2곳의 경매/1차합의 미분리")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스: 두 통계가 경매(bid_count 有 / award_route='경매')만 센다")
# ──────────────────────────────────────────────────────────────
outcome_body = _py_fn_body(APP_SRC, "api_outcome_stats")
bands_body = _py_fn_body(APP_SRC, "api_est_bands")
chk("o.bid_count IS NOT NULL" in outcome_body,
    "★★★ api_outcome_stats 가 est_outcome 자신의 스냅샷(bid_count)으로 경매만 센다")
chk("award_route='경매'" in bands_body,
    "★★★ api_est_bands 가 award_route='경매' 인 사건만 낙찰표본으로 센다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행: 1차합의(단독협상) 건은 두 통계 모두에서 빠지고, 경매 건은 그대로 잡힌다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round93_")
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
                 "VALUES('admin','x','검증','중간관리자')")
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R93업체','시행사','활성')"
    ).lastrowid

    # (a) 진짜 경매로 낙찰된 사건 — auctions 행(bid_count=3)이 있다.
    c_auc = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,award_amount,"
        "                  award_route,is_demo,awarded_at) "
        "VALUES('R93-AUC','시공중','가드레일·방호울타리','서울',?,5000000,'경매',0,?)",
        (pid, DB.now())).lastrowid
    conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,NULL,'원경매',0,'마감',5000000,3,0,?,?)", (c_auc, DB.now(), DB.now()))
    conn.execute("INSERT INTO work_lots(case_id,category,status,created_at) "
                 "VALUES(?,'가드레일·방호울타리','낙찰',?)", (c_auc, DB.now()))

    # (b) 경매 없이 1차합의(단독협상)로 끝난 사건 — auctions 행이 아예 없다.
    c_agr = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,award_amount,"
        "                  award_route,is_demo,awarded_at) "
        "VALUES('R93-AGR','시공중','가드레일·방호울타리','서울',?,5000000,'1차합의',0,?)",
        (pid, DB.now())).lastrowid
    conn.execute("INSERT INTO work_lots(case_id,category,status,created_at) "
                 "VALUES(?,'가드레일·방호울타리','낙찰',?)", (c_agr, DB.now()))
    conn.commit()

    A._record_outcome(conn, c_auc)
    A._record_outcome(conn, c_agr)
    conn.commit()

    bc_auc = conn.execute(
        "SELECT bid_count FROM est_outcome WHERE case_id=?", (c_auc,)).fetchone()["bid_count"]
    bc_agr = conn.execute(
        "SELECT bid_count FROM est_outcome WHERE case_id=?", (c_agr,)).fetchone()["bid_count"]
    conn.close()
    chk(bc_auc == 3 and bc_agr is None,
        "STEP 준비: 스냅샷 자체가 경매(bid_count=3)와 1차합의(NULL)를 정확히 구분해 담았다",
        f"auc={bc_auc} agr={bc_agr}")

    admin = A.app.test_client()
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"

    jo = admin.get("/api/outcome-stats").get_json()
    total_n = sum(m["n"] for m in jo.get("by_major", []))
    chk(total_n == 1,
        "★★★ 공종별 실적 표본이 경매 건 1개만 센다(1차합의 건은 안 섞인다)", f"total={total_n}")

    je = admin.get("/api/est-bands").get_json()
    chk(je.get("award_samples") == 1,
        "★★★ 낙찰 표본 수(award_samples)도 경매 건 1개만 센다", je.get("award_samples"))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드93 서버측 준비/실행", f"{type(e).__name__} {e}")
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
