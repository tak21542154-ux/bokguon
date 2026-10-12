# -*- coding: utf-8 -*-
"""스캔 97라운드 회귀 — 웹훅이 데모 사건을 실제 보험사 서버로 그대로 내보냈다.

  deliver_webhook()/safe_webhook() 은 8개 이벤트(낙찰·완료·정산승인·정산지급·
  미수선·낙찰취소·1차합의승인 등)가 전부 거치는 유일한 공유 지점인데, 그중
  api_insurer_field_agreement_decision 한 곳만 "데모 사건은 여기서 끊는다"는
  자기 가드가 있었다(그 가드 자신의 주석: 실측 2026-08-18, 발주처 포털
  승인대기 2건이 둘 다 데모). 나머지 7곳은 전혀 없어서, 데모 사건에 대해서도
  실제 보험사가 등록해 둔 webhook_url 로 그대로 배송 이력이 '대기'(발송 큐행)
  로 잡혔다. 유일한 공유 관문(deliver_webhook)에서 한 번에 막는다 — 이력
  행은 남기되(감사) 상태를 이미 문서화된 값인 '미설정'으로 고정해 실제
  HTTP 전송 큐에는 절대 올리지 않는다.

      python test_scan_round97_fixes.py
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
print("  스캔 97라운드 회귀 — 웹훅의 데모사건 실전송 차단")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스: deliver_webhook 이 case_no 로 is_demo 를 확인해 enabled 를 끈다")
# ──────────────────────────────────────────────────────────────
dw_body = _py_fn_body(APP_SRC, "deliver_webhook")
chk("SELECT is_demo FROM cases WHERE case_no=?" in dw_body,
    "★★★ deliver_webhook 이 case_no 로 사건의 is_demo 를 직접 조회한다")
chk("enabled = False" in dw_body,
    "★★★ 데모로 확인되면 enabled 를 꺼서 실제 발송 큐에 올리지 않는다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행: 데모 사건은 '미설정'으로 막히고, 실제 사건은 '대기'로 정상 큐잉된다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round97_")
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
    # 실제로 설정된(운영 중인) 보험사 — webhook_url·api_enabled·status 전부 정상.
    iid = conn.execute(
        "INSERT INTO insurers(name,status,webhook_url,webhook_secret,api_enabled) "
        "VALUES('R97보험','활성','https://real-insurer.example.com/hook','sec',1)"
    ).lastrowid
    conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
        "VALUES('R97-DEMO','시공중','가드레일','서울',?,1)", (iid,))
    conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
        "VALUES('R97-REAL','시공중','가드레일','서울',?,0)", (iid,))
    conn.commit()

    with A.app.test_request_context():
        did_demo = A.deliver_webhook(conn, iid, "case.awarded", "R97-DEMO", {"amount": 1000000})
        conn.commit()
        did_real = A.deliver_webhook(conn, iid, "case.awarded", "R97-REAL", {"amount": 1000000})
        conn.commit()

    row_demo = conn.execute(
        "SELECT status, target_url FROM webhook_deliveries WHERE id=?", (did_demo,)).fetchone()
    row_real = conn.execute(
        "SELECT status, target_url FROM webhook_deliveries WHERE id=?", (did_real,)).fetchone()
    conn.close()

    chk(row_demo["status"] == "미설정",
        "★★★ 데모 사건의 웹훅은 '미설정'으로 막혀 발송 큐에 올라가지 않는다"
        "(예전엔 이 상태가 '대기'였다 — 실제 보험사 서버로 나갈 준비가 됐었다)",
        dict(row_demo))
    chk(row_real["status"] == "대기",
        "★★ 실제(비데모) 사건은 그대로 '대기'로 정상 큐잉된다(과잉차단 아님)",
        dict(row_real))
    chk(row_demo["target_url"] == row_real["target_url"] == "https://real-insurer.example.com/hook",
        "STEP 두 이력 행 모두 target_url 자체는 그대로 기록된다(감사용 — 실제 발송만 막힘)",
        (row_demo["target_url"], row_real["target_url"]))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드97 서버측 준비/실행", f"{type(e).__name__} {e}")
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
