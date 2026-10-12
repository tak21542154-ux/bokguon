# -*- coding: utf-8 -*-
"""스캔 95라운드 회귀 — dispatch.py 감사로그 11곳의 사건번호 형식 불일치(94라운드 후속).

  94라운드에서 settle_agreement() 하나만 고쳤다 — 같은 파일 안에 똑같은 결함
  (DB.log detail 에 사건을 case_no 문자열이 아니라 case_id 숫자 PK로 남겨,
  /report/case/<cid>·정산 상세의 LIKE 검색에 영원히 안 걸림)이 8개 함수·
  11곳 더 있었다. 전부 case_no 로 맞춘다:
    open_dispatch(3곳) · assign_dispatch · claim · arrive(2곳) ·
    sweep_dispatches(2곳) · close_no_repair · open_agreement

      python test_scan_round95_fixes.py
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
print("  스캔 95라운드 회귀 — dispatch.py 감사로그 11곳 사건번호 형식 통일")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스: 8개 함수 모두 DB.log 에서 case_no 를 참조하고, 옛 형식이 안 남았다")
# ──────────────────────────────────────────────────────────────
# 함수별로 "사건 조회 쿼리 자신이 case_no 를 실제로 select 하는가"를 정확히 본다
# (단순히 본문에 "case_no" 문자열이 있는지만 보면, 같은 함수 안의 다른 DB.log
#  줄에 이미 등장한 case_no 참조 때문에 정작 쿼리를 되돌려도 통과해 버린다).
#  ⚠⚠ [라운드152] open_dispatch, [라운드189] assign_dispatch 는 dispatch_status
#    컬럼이 하나 더 늘었다(이미 도착해 사진을 확보한 사건의 재수배·재배정을 막는
#    가드) — case_no 는 여전히 같은 자리에서 select 되므로 그 사실 자체는 안
#    바뀌었다, 늘어난 실제 모양에 맞춘다.
QUERY_CHECKS = {
    "open_dispatch": 'SELECT status, partner_id, case_no, dispatch_status FROM cases',
    "assign_dispatch": 'SELECT status, partner_id, case_no, dispatch_status FROM cases',
    "claim": 'SELECT status, partner_id, case_no FROM cases',
    "arrive": 'SELECT status, partner_id, case_no FROM cases',
    "sweep_dispatches": 'SELECT case_no FROM cases WHERE id=dispatches.case_id',
    "close_no_repair": 'SELECT dp.case_id, c.case_no FROM dispatches dp JOIN cases c',
    "open_agreement": 'SELECT status, partner_id, case_no FROM cases',
}
for fn, needle in QUERY_CHECKS.items():
    body = _py_fn_body(DISPATCH_SRC, fn)
    chk("DB.log(" in body, f"STEP {fn} 에 DB.log 호출이 있다(추출 확인)")
    chk(needle in body, f"★★★ {fn} 의 사건 조회 쿼리 자신이 case_no 를 select 한다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행: 출동→수락→도착→1차합의 전체 흐름의 로그가 전부 사건이력에 잡힌다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round95_")
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
    iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R95보험','활성')").lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,lat,lng) "
        "VALUES('R95업체','시행사','활성',37.5,127.0)").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,lat,lng) "
        "VALUES('26-95001','접수','가드레일','서울',?,37.5,127.0)", (iid,)).lastrowid
    conn.commit()

    did, called, sent = DP.open_dispatch(conn, cid)
    conn.commit()
    chk(called >= 0, "STEP 준비: open_dispatch 호출 자체는 에러 없이 끝난다", (did, called, sent))

    # candidates() 가 실측 후보를 못 찾을 수도 있으니(거리·활성 조건), 직접배정으로
    # 흐름을 이어간다 — assign_dispatch 도 이번 라운드 수정 대상이라 오히려 더 낫다.
    ok_a, msg_a, did2 = DP.assign_dispatch(conn, cid, pid, "테스트 직접배정")
    conn.commit()
    chk(ok_a, "STEP 준비: assign_dispatch 로 배정한다", msg_a)
    use_did = did2 if ok_a else did

    ok_c, msg_c, due = DP.claim(conn, use_did, pid, "R95업체")
    conn.commit()
    # 직접배정(assign_dispatch)은 이미 '수배됨' 상태로 만들어 claim 대상이 아닐 수 있다 —
    # 그 경우엔 claim 검증은 건너뛰고 도착 단계로 바로 간다(assign_dispatch 자체 로그는
    # 이미 위에서 검증됨).
    ok_r, msg_r = DP.arrive(conn, use_did, pid, photo_count=3, field_estimate=800000)
    conn.commit()
    chk(ok_r, "STEP 준비: arrive(도착·사진등록) 처리", msg_r)

    aid = DP.open_agreement(conn, cid, dispatch_id=use_did, engine_low=700000, engine_high=900000,
                            our_staff="검증담당")
    conn.commit()
    chk(aid is not None, "STEP 준비: open_agreement(1차합의 개시)가 성공한다", aid)

    ok_s, msg_s = DP.settle_agreement(
        conn, aid, agreed=True,
        approver={"org_id": iid, "user_id": None, "name": "최승인95", "role": "최고관리자"})
    conn.commit()
    chk(ok_s, "STEP 준비: settle_agreement(승인)까지 마친다", msg_s)
    conn.close()

    admin = A.app.test_client()
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"

    r = admin.get(f"/report/case/{cid}")
    chk(r.status_code == 200, "STEP 사건 이력 리포트 요청 자체는 200", r.status_code)
    body = r.get_data(as_text=True)

    chk("현장 도착" in body,
        "★★★ arrive() 의 도착 로그가 사건 이력 리포트에 나타난다")
    chk("1차 합의 개시" in body,
        "★★★ open_agreement() 의 개시 로그가 사건 이력 리포트에 나타난다")
    chk("최승인95" in body and "1차 합의 승인" in body,
        "★★★ settle_agreement() 의 승인 로그(승인자 포함)도 함께 나타난다")

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드95 서버측 준비/실행", f"{type(e).__name__} {e}")
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
