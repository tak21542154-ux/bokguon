# -*- coding: utf-8 -*-
"""스캔 198라운드 회귀 — 보험사 포털 사건접수에 서버측 멱등성 보호가 없던 결함.

  형제(api_v1_case_create, 보험사 전산 연동)는 이미 Idempotency-Key 로 재시도를
  막는다 — "응답을 못 받고 같은 요청을 다시 보내면 사건·경매·정산이 통째로
  2벌 만들어진다(수수료도 두 번 잡힌다)"는 게 그 코드 자신의 실측 주석이다.
  포털 경로(api_insurer_case_create)만 이 보호가 없었다. 프론트의 CASE_LOCK
  (insurer_portal.html)은 같은 페이지가 떠 있는 동안의 중복 클릭만 막을 뿐
  새로고침·새 탭·응답 지연 후 재제출에는 전혀 작동하지 않고, 접수번호를
  비우면(흔한 사용) case_no 완전일치 방어도 매번 새로 채번돼 무력화된다.

      python test_scan_round198_fixes.py
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
HTML_SRC = read("templates/insurer_portal.html")

print("=" * 72)
print("  스캔 198라운드 회귀 — 보험사 포털 사건접수 멱등성 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_insurer_case_create():")
i1 = APP_SRC.index("\n@app.post(", i0 + 1)
body_seg = APP_SRC[i0:i1]
chk('d.get("idempotency_key")' in body_seg,
    "★★★ 포털 사건접수가 idempotency_key 를 실제로 읽는다")
chk('WHERE insurer_id=? AND idem_key=?' in body_seg,
    "★★★★ 포털 사건접수가 형제(API 연동)와 같은 idem_key 조회로 재제출을 막는다"
    "(고치기 전엔 이 함수 전체에 idem_key 참조가 0건이었다)")
chk('"duplicate": True' in body_seg,
    "★★★ 재제출이면 새로 만들지 않고 기존 사건을 duplicate:true 로 돌려준다")

chk("window.CASE_IDEM_KEY" in HTML_SRC,
    "★★★ 포털 폼이 사건등록 모달을 열 때마다 새 열쇠를 발급한다")
chk("idempotency_key:window.CASE_IDEM_KEY" in HTML_SRC.replace(" ", "")
    or "idempotency_key: window.CASE_IDEM_KEY" in HTML_SRC,
    "★★★ 그 열쇠가 실제 제출 body 에 실린다")

# ============================================================
print("\n[2] 실행 — 같은 열쇠로 두 번 제출하면 사건이 한 건만 생기고, "
      "다른 열쇠(또는 열쇠 없음)면 별개 사건으로 생긴다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round198_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,status,login_id) VALUES('R198보험','활성','r198ins')"
    ).lastrowid
    conn.commit()

    insurer_c = A.app.test_client()
    tok = "r198-insurer-csrf"
    with insurer_c.session_transaction() as sess:
        sess["insurer_id"] = iid; sess["insurer_name"] = "R198보험"; sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    body1 = {"categories": ["유리·샷시·자동문"], "region": "서울", "no_photo": True,
             "idempotency_key": "r198-retry-key-abc"}

    r1 = insurer_c.post("/api/insurer/cases", json=body1, headers=hdr)
    j1 = r1.get_json() or {}
    #  같은 브라우저가 응답을 못 받고 같은 요청을 다시 보낸 상황을 그대로 재현 —
    #  요청 본문이 완전히 동일하다(같은 열쇠).
    r2 = insurer_c.post("/api/insurer/cases", json=body1, headers=hdr)
    j2 = r2.get_json() or {}
    #  다른 사고 — 열쇠가 다르면 별개 사건으로 생겨야 한다(회귀 없음).
    body3 = dict(body1, idempotency_key="r198-different-key-xyz")
    r3 = insurer_c.post("/api/insurer/cases", json=body3, headers=hdr)
    j3 = r3.get_json() or {}

    n_cases = conn.execute(
        "SELECT COUNT(*) n FROM cases WHERE insurer_id=?", (iid,)).fetchone()["n"]

    chk(r1.status_code == 200 and j1.get("ok") is True and not j1.get("duplicate"),
        "첫 제출은 정상적으로 새 사건을 만든다", (r1.status_code, j1))
    chk(r2.status_code == 200 and j2.get("ok") is True and j2.get("duplicate") is True,
        "★★★★ 같은 열쇠의 재제출은 새로 안 만들고 duplicate:true 로 기존 사건을 "
        "돌려준다(고치기 전엔 사건이 또 하나 생겼다)", (r2.status_code, j2))
    chk(j1.get("id") == j2.get("id") and j1.get("case_no") == j2.get("case_no"),
        "★★★★ 재제출이 돌려준 사건이 첫 제출과 완전히 같은 사건이다",
        (j1.get("id"), j2.get("id")))
    chk(r3.status_code == 200 and j3.get("ok") is True and not j3.get("duplicate")
        and j3.get("id") != j1.get("id"),
        "★★★ 다른 열쇠(진짜 다른 사고)는 별개 사건으로 정상 생성된다(회귀 없음)",
        (r3.status_code, j3))
    chk(n_cases == 2,
        "★★★★ 이 보험사의 사건이 실제로 2건뿐이다(재제출로 늘지 않음 — "
        "고치기 전엔 3건이 됐다: 최초·재제출 중복·별개사고)", n_cases)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드198 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
