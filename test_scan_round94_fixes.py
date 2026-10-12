# -*- coding: utf-8 -*-
"""스캔 94라운드 회귀 — 1차합의 승인/부동의 로그가 사건 이력 리포트에서 영원히 안 보였다.

  DP.settle_agreement() 의 DB.log 가 detail 에 사건을 "사건 {case_id}"(숫자 PK)
  로 남겼는데, /report/case/<cid>(사건 전체 이력)·정산 상세의 감사로그
  타임라인은 둘 다 detail 을 case_no("26-xxxxx") 문자열로 LIKE 검색한다 —
  형식이 아예 안 겹쳐서 이 함수가 남기는 승인/부동의 기록(승인자 이름·직급
  포함 — 분쟁이 났을 때 필요한 바로 그 증거)이 두 화면 모두에서 영원히
  안 잡혔다. app.py 쪽 DB.log 는 전부 case_no 를 쓰는 게 이미 확립된 관례라
  그 관례에 맞춘다.

      python test_scan_round94_fixes.py
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


DISPATCH_SRC = read("dispatch.py")

print("═" * 72)
print("  스캔 94라운드 회귀 — 1차합의 승인/부동의 로그의 사건번호 형식 불일치")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스: settle_agreement 이 case_no 를 끌어와 DB.log 에 쓴다")
# ──────────────────────────────────────────────────────────────
sa_body = _py_fn_body(DISPATCH_SRC, "settle_agreement")
chk("JOIN cases c ON c.id = fa.case_id" in sa_body and "c.case_no" in sa_body,
    "★★★ 조회가 cases 를 조인해 case_no 를 함께 가져온다")
chk("f\"{a['case_no']} ·" in sa_body.replace(" ", "") or "f\"{a[" in sa_body,
    "STEP DB.log 문자열이 a['case_no'] 를 참조한다")
chk("사건 {a['case_id']}" not in sa_body,
    "★★★ 옛 형식(사건 {case_id})이 더 이상 안 남아 있다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행: 승인/부동의 로그가 사건 이력 리포트의 검색 조건에 실제로 걸린다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round94_")
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
    import dispatch as DP

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','중간관리자')")
    iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R94보험','활성')").lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R94업체','시행사','활성')"
    ).lastrowid

    def _mkcase(no):
        return conn.execute(
            "INSERT INTO cases(case_no,status,category,region,insurer_id) "
            "VALUES(?,'접수','가드레일','서울',?)", (no, iid)).lastrowid

    # (a) 승인(agreed=True) 케이스
    cid_ok = _mkcase("26-94001")
    aid_ok = conn.execute(
        "INSERT INTO field_agreements(case_id,partner_id,partner_name,field_amount,"
        "                             status,created_at) "
        "VALUES(?,?,?,850000,?,?)", (cid_ok, pid, "R94업체", DP.AG_REVIEW, DB.now())).lastrowid
    conn.commit()
    ok1, msg1 = DP.settle_agreement(
        conn, aid_ok, agreed=True,
        approver={"org_id": iid, "user_id": None, "name": "김보상94", "role": "최고관리자"})
    conn.commit()
    chk(ok1, "STEP 준비: 1차합의 승인 처리 자체는 성공한다", msg1)

    # (b) 부동의(agreed=False) 케이스
    cid_no = _mkcase("26-94002")
    aid_no = conn.execute(
        "INSERT INTO field_agreements(case_id,partner_id,partner_name,field_amount,"
        "                             status,created_at) "
        "VALUES(?,?,?,900000,?,?)", (cid_no, pid, "R94업체", DP.AG_REVIEW, DB.now())).lastrowid
    conn.commit()
    ok2, msg2 = DP.settle_agreement(
        conn, aid_no, agreed=False, note="현장 확인 결과 부동의합니다",
        approver={"org_id": iid, "user_id": None, "name": "박보상94", "role": "중간관리자"})
    conn.commit()
    chk(ok2, "STEP 준비: 1차합의 부동의 처리 자체는 성공한다", msg2)
    conn.close()

    admin = A.app.test_client()
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"

    r1 = admin.get(f"/report/case/{cid_ok}")
    chk(r1.status_code == 200, "STEP 승인 건 리포트 요청 자체는 200", r1.status_code)
    body1 = r1.get_data(as_text=True)
    chk("김보상94" in body1 and "1차 합의 승인" in body1,
        "★★★ 승인자 이름·직급이 담긴 로그가 사건 이력 리포트에 실제로 나타난다"
        "(예전엔 사건번호 형식이 안 맞아 '남은 감사 기록이 없습니다'만 떴다)")

    r2 = admin.get(f"/report/case/{cid_no}")
    body2 = r2.get_data(as_text=True)
    chk("박보상94" in body2 and "부동의" in body2,
        "★★★ 부동의 로그도 마찬가지로 리포트에 나타난다")

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드94 서버측 준비/실행", f"{type(e).__name__} {e}")
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
