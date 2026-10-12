# -*- coding: utf-8 -*-
"""스캔 331라운드 회귀 — status_reason(협력사·보험사 상태변경·퇴출 사유)
   필드 전체가 "저장 전 300자로 자르기" 관례에서 통째로 빠져 있던 결함
   [중간, 3곳], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견(330라운드가
   확립한 reason[:300] 관례를 grep으로 전수조사하되 이번엔 "reason"이 아닌
   다른 이름의 자유텍스트 필드까지 넓혀서 찾음).

   ① `_partner_update()`(app.py:7889, PATCH /api/partners/<pid>) 의
      status_reason(7993행)이 무제한으로 partners.status_reason·
      activity_log·알림톡에 그대로 들어갔다.
   ② `api_partner_delete()`(app.py:8021, DELETE /api/partners/<pid>, 퇴출)
      는 사유를 **URL 쿼리스트링**(request.args, 8030행)으로 받는 유일한
      경로인데 여기도 무제한이었다.
   ③ `api_insurer_update()`(app.py:8230, PATCH /api/insurers/<iid>) 는
      더 미묘하다 — 8249행에서 만든 reason 변수는 길이검사(5자 이상)에만
      쓰이고, 실제 저장(옛 8277행)과 통지(옛 8288행)는 그 변수를 안 쓰고
      d.get("status_reason") 을 **각자 다시 읽어** 길이제한이 단 한 번도
      적용된 적이 없었다 — 사실상 "자르는 코드는 있는데 그 결과를 아무도
      안 쓰는" 죽은 방어. 세 곳 다 118·196·330라운드가 세운 reason[:300]
      관례를 적용(③은 재조회 자체를 없애고 변수 재사용으로 통일).
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_scratch = tempfile.mkdtemp(prefix="bokguon_r331_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_scratch, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"

PASS = FAIL = 0
FAILED = []


def chk(cond, msg, detail=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {msg}")
    else:
        FAIL += 1
        FAILED.append(msg)
        print(f"  [FAIL] {msg}" + (f"   {detail}" if detail else ""))


print("=" * 74)
print("  스캔 331라운드 회귀 — status_reason 필드 3곳 무제한 저장")
print("=" * 74)

import db as DB  # noqa: E402
DB.init_db(seed_demo=True)
import app as A  # noqa: E402

conn = DB.get_db()
app_client = A.app.test_client()
_tok = "r331-admin-csrf"
with app_client.session_transaction() as sess:
    sess["admin"] = "admin"
    sess["admin_role"] = "최고관리자"
    sess["_csrf"] = _tok
_hdr = {"X-CSRF-Token": _tok}
LONG = "가" * 2000

print("\n[1] _partner_update() — 협력사 상태변경 사유")
pid1 = conn.execute(
    "INSERT INTO partners(name,status,license_status) VALUES('R331업체1','활성','확인됨')").lastrowid
conn.commit()
r1 = app_client.patch(f"/api/partners/{pid1}", headers=_hdr,
                       json={"status": "경고", "status_reason": LONG})
chk(r1.status_code == 200 and (r1.get_json() or {}).get("ok") is True,
    "  상태변경 자체는 정상 200/ok", (r1.status_code, r1.get_data(as_text=True)[:200]))
row1 = conn.execute("SELECT status_reason FROM partners WHERE id=?", (pid1,)).fetchone()
chk(row1 is not None and LONG not in (row1["status_reason"] or ""),
    "★★★★★ partners.status_reason 에 2000자 원문이 그대로 안 들어간다"
    "(고치기 전엔 길이제한이 없어 그대로 들어갔다)",
    (row1["status_reason"] or "")[:50] if row1 else None)
log1 = conn.execute(
    "SELECT detail FROM activity_log WHERE action='업체 정보수정' ORDER BY id DESC LIMIT 1").fetchone()
chk(log1 is not None and LONG not in (log1["detail"] or ""),
    "  감사로그 detail 에도 2000자 원문이 안 들어간다", log1["detail"][:50] if log1 else None)

print("\n[2] api_partner_delete() — 협력사 퇴출 사유(URL 쿼리스트링)")
pid2 = conn.execute(
    "INSERT INTO partners(name,status,license_status) VALUES('R331업체2','활성','확인됨')").lastrowid
conn.commit()
r2 = app_client.delete(f"/api/partners/{pid2}?reason={LONG}", headers=_hdr)
chk(r2.status_code == 200 and (r2.get_json() or {}).get("ok") is True,
    "  퇴출 자체는 정상 200/ok", (r2.status_code, r2.get_data(as_text=True)[:200]))
row2 = conn.execute("SELECT status_reason FROM partners WHERE id=?", (pid2,)).fetchone()
chk(row2 is not None and LONG not in (row2["status_reason"] or ""),
    "★★★★★ 퇴출 사유(URL 쿼리로 받음)도 partners.status_reason 에 원문 그대로 안 들어간다",
    (row2["status_reason"] or "")[:50] if row2 else None)

print("\n[3] api_insurer_update() — 보험사 상태변경 사유(변수 재조회로 방어가 무력화됐던 자리)")
iid3 = conn.execute("INSERT INTO insurers(name,status) VALUES('R331보험1','활성')").lastrowid
conn.commit()
r3 = app_client.patch(f"/api/insurers/{iid3}", headers=_hdr,
                       json={"status": "중지", "status_reason": LONG})
chk(r3.status_code == 200 and (r3.get_json() or {}).get("ok") is True,
    "  상태변경 자체는 정상 200/ok", (r3.status_code, r3.get_data(as_text=True)[:200]))
row3 = conn.execute("SELECT status_reason FROM insurers WHERE id=?", (iid3,)).fetchone()
chk(row3 is not None and LONG not in (row3["status_reason"] or ""),
    "★★★★★ insurers.status_reason 에 2000자 원문이 그대로 안 들어간다"
    "(고치기 전엔 길이검사용 변수와 별개로 재조회한 원문이 그대로 저장됐다)",
    (row3["status_reason"] or "")[:50] if row3 else None)

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
