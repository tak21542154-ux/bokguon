# -*- coding: utf-8 -*-
"""스캔 170라운드 회귀 — 관리자 감사로그 행위자(actor())가 위조 가능하던 결함.

  admins.name(표시이름)은 유일성 제약이 없고 PATCH /api/me 로 누구나(최하위
  등급 "하위관리자" 포함, 역할 제한 없음) 자유 문자열로 바꿀 수 있다. actor()
  는 그 표시이름만 반환했으므로, 하위관리자가 자기 이름을 다른(로그인해 본
  적도 없는) 최고관리자와 똑같이 바꾸면 그 뒤 모든 행동이 activity_log·
  memos.author 에 그 사람 실명으로 남았다 — "분쟁 때 근거가 되는 기록"이라고
  코드 스스로 밝힌 바로 그 감사로그의 귀속(accountability)이 깨지는
  결함이었다. 포털(보험사·협력사) 쪽은 이미 이 문제를 portal_actor() 로
  막고 있었다(조직명+로그인ID) — 같은 처방을 admin 쪽 actor() 하나에만
  적용해 DB.log()·memos.author 를 쓰는 모든 호출부를 한 번에 고쳤다.

      python test_scan_round170_fixes.py
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
print("  스캔 170라운드 회귀 — 관리자 감사로그 행위자(actor()) 위조 가능 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def actor():")
i1 = APP_SRC.index("\ndef ", i0 + 1)
body = APP_SRC[i0:i1]
chk('uid = session.get("admin")' in body,
    "★★★ actor() 가 로그인 계정(session['admin'], 불변·유일)을 함께 본다")
chk('return f"{name}({uid})" if uid else name' in body,
    "★★★ actor() 가 표시이름 뒤에 로그인 계정을 덧붙인다(포털의 portal_actor()와 같은 처방)")

# ============================================================
print("\n[2] 실행 — 하위관리자가 이름을 다른 관리자와 똑같이 바꿔도 로그가 구분되는가")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round170_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    #  최고관리자 "김철수" — 실측 시나리오대로 한 번도 로그인하지 않는다
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('topadmin','x','김철수','최고관리자')")
    #  하위관리자 "박영희" — 실제로 로그인해 활동하는 쪽
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('lowadmin','x','박영희','하위관리자')")
    conn.commit(); conn.close()

    low = A.app.test_client()
    tok = "r170-low-csrf"
    with low.session_transaction() as sess:
        sess["admin"] = "lowadmin"; sess["admin_role"] = "하위관리자"
        sess["admin_name"] = "박영희"; sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    #  ① 박영희가 자기 이름을 김철수(다른 실존 관리자)로 바꾼다 — 역할 제한이 없다
    r1 = low.patch("/api/me", json={"name": "김철수"}, headers=hdr)
    chk(r1.status_code == 200 and r1.get_json().get("name") == "김철수",
        "STEP 하위관리자가 표시이름을 다른 관리자와 똑같이 바꿀 수 있다"
        "(등급 제한 없음 — 결함이 아니라 이번 결함의 전제조건)", r1.get_json())

    #  ② 같은 세션으로 메모를 하나 남긴다(모든 등급이 접근 가능한 라우트)
    r2 = low.post("/api/memos", json={"target_type": "case", "target_id": 999999,
                                       "body": "r170 spoof-test"}, headers=hdr)
    chk(r2.status_code == 200, "STEP 메모 작성이 200 이다", r2.status_code)

    conn = DB.get_db()
    mrow = dict(conn.execute(
        "SELECT author FROM memos WHERE target_id=999999").fetchone())
    lrow = dict(conn.execute(
        "SELECT actor FROM activity_log WHERE action='메모 작성' ORDER BY id DESC LIMIT 1").fetchone())
    conn.close()
    chk(mrow["author"] == "김철수(lowadmin)",
        "★★★ 메모 작성자가 '김철수(lowadmin)'로 남아 실제 최고관리자(topadmin)와"
        " 구분된다(고치기 전엔 그냥 '김철수'라 로그인한 적도 없는 그 계정 것으로 보였다)",
        mrow)
    chk(lrow["actor"] == "김철수(lowadmin)",
        "★★★ 감사로그(activity_log.actor)도 마찬가지로 로그인 계정까지 함께 남는다", lrow)
    chk("(topadmin)" not in mrow["author"] and "(topadmin)" not in lrow["actor"],
        "★ 실제로 로그인한 적 없는 topadmin 계정 것으로는 남지 않는다", (mrow, lrow))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드170 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
