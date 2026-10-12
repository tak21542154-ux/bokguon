# -*- coding: utf-8 -*-
"""스캔 199라운드 회귀 — 협력사 계정 일괄발급이 "발급 중 오류"로 보고한 건도
실제로는 DB에 커밋되던 결함.

  issue_partner_login() 은 스스로 커밋하지 않는다("일괄 발급이 한 트랜잭션으로
  묶일 수 있어야 한다"는 게 그 함수 자신의 설계) — UPDATE(로그인ID·비밀번호
  해시)를 먼저 실행한 뒤 DB.log()·notify() 를 부르고 return 한다. 일괄발급
  반복문은 이 호출을 try/except 로 감싸 예외가 나면 "발급 중 오류"로만
  기록하고 다음 업체로 넘어가는데, conn.rollback() 을 부르지 않는다. 반복이
  끝나면 무조건 commit() 되므로, notify() 등 UPDATE **이후** 어딘가에서
  예외가 나면 실패로 보고된 그 업체도 실제로는 커밋된다 — 아무도 모르는
  임시 비밀번호로 계정이 만들어져 로그인이 막힌다.

      python test_scan_round199_fixes.py
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
print("  스캔 199라운드 회귀 — 협력사 계정 일괄발급의 부분실패 오커밋")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_partner_bulk_credentials():")
i1 = APP_SRC.index("\n@app.get(", i0 + 1)
body_seg = APP_SRC[i0:i1]
chk("SAVEPOINT bulk_cred" in body_seg,
    "★★★★ 일괄발급 반복이 업체별 SAVEPOINT 를 쓴다"
    "(고치기 전엔 예외를 잡고도 아무것도 되돌리지 않았다)")
chk("ROLLBACK TO SAVEPOINT bulk_cred" in body_seg,
    "★★★★ 예외가 나면 그 업체 몫만 SAVEPOINT 로 되돌린다")

# ============================================================
print("\n[2] 실행 — 일괄발급 중 한 업체에서만 예외가 나면, 그 업체는 실제로도 "
      "미발급 상태로 남고 나머지는 정상 발급된다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round199_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    pid_a = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R199업체A','시공사','활성')"
    ).lastrowid
    pid_b = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R199업체B','시공사','활성')"
    ).lastrowid
    pid_c = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R199업체C','시공사','활성')"
    ).lastrowid
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r199top','x','검증최고','최고관리자')")
    conn.commit()

    #  notify() 가 UPDATE(로그인ID·비밀번호해시) **이후**에 예외를 던지는 상황을
    #  그대로 재현한다 — 업체 B 에만 걸리게 한다(A·C 는 정상 동작).
    _real_notify = A.notify

    def _flaky_notify(conn_, ntype, *a, **kw):
        if kw.get("partner_id") == pid_b:
            raise RuntimeError("R199 검증용 강제 실패(알림 발송 도중)")
        return _real_notify(conn_, ntype, *a, **kw)

    A.notify = _flaky_notify

    top = A.app.test_client()
    tok = "r199-top-csrf"
    with top.session_transaction() as sess:
        sess["admin"] = "r199top"; sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증최고"; sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    resp = top.post("/api/partners/bulk-credentials",
                     json={"ids": [pid_a, pid_b, pid_c]}, headers=hdr)
    j = resp.get_json() or {}
    A.notify = _real_notify

    issued_ids = {r.get("id") for r in (j.get("issued") or [])}
    skipped_ids = {r.get("id") for r in (j.get("skipped") or [])}

    row_a = conn.execute("SELECT login_id, password_hash FROM partners WHERE id=?", (pid_a,)).fetchone()
    row_b = conn.execute("SELECT login_id, password_hash FROM partners WHERE id=?", (pid_b,)).fetchone()
    row_c = conn.execute("SELECT login_id, password_hash FROM partners WHERE id=?", (pid_c,)).fetchone()

    chk(resp.status_code == 200 and j.get("ok") is True,
        "일괄발급 요청 자체는 정상 응답한다(회귀 없음)", (resp.status_code, j))
    chk(pid_a in issued_ids and pid_c in issued_ids,
        "정상 업체(A·C)는 그대로 발급 성공으로 보고된다(회귀 없음)",
        (issued_ids, skipped_ids))
    chk(pid_b in skipped_ids,
        "예외가 난 업체(B)는 실패로 보고된다(회귀 없음)", skipped_ids)
    chk(bool(row_a["login_id"]) and bool(row_a["password_hash"]),
        "★★★ 정상 발급된 A는 실제로 로그인ID·비밀번호가 DB에 있다", dict(row_a))
    chk(bool(row_c["login_id"]) and bool(row_c["password_hash"]),
        "★★★ 정상 발급된 C도 실제로 로그인ID·비밀번호가 DB에 있다", dict(row_c))
    chk(row_b["login_id"] is None and row_b["password_hash"] is None,
        "★★★★ '발급 중 오류'로 보고된 B는 실제로도 로그인ID·비밀번호가 없다"
        "(고치기 전엔 실패로 보고해 놓고 실제로는 커밋되어, 아무도 모르는 "
        "임시 비밀번호로 계정이 생겨 로그인이 영영 막혔다)", dict(row_b))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드199 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
