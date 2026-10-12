# -*- coding: utf-8 -*-
"""스캔 594라운드 회귀 — 관리자 콘솔 사건 등록(api_case_create, POST /api/cases)이
insurer_id 없이 보험사 "이름"만으로 발주처를 찾을 때 SQL "WHERE name=?" 바이트
비교를 쓰던 결함.

  이 함수는 insurer_id 가 없으면 insurer(이름)로 유일 매칭을 시도한다(11550행
  부근). 지금 관리자 화면(admin.js createCase)은 <select> 옵션의 id 를 항상
  같이 보내 이 분기를 타지 않지만, 이 라우트는 require_admin 뿐이라 관리자
  세션으로 직접 호출(스크립트·curl, 또는 향후 폼 변경)하면 insurer_id 없이
  이름만 보낼 수 있다 — 그 이름이 등록된 보험사명과 유니코드 정규화 형태만
  다르면(한글 자모를 완성형 대신 풀어쓴 NFD — 맥에서 복사한 텍스트에 흔하다)
  시각적으로 완전히 같아도 이 비교가 실패해, 실재하는 보험사를 "발주 보험사를
  선택해 주세요"(NO_INSURER)로 튕겼다 — round593이 연락처 일괄등록
  (api_contact_import)에서 고친 것과 같은 결함군이면서, app.py 전체 "name="
  류 SQL 바이트비교 전수확인에서 새로 드러난 세 번째 인스턴스다(첫 번째는
  round593이 고친 api_contact_import, 두 번째는 api_application_create —
  이미 별도 태스크로 이관되어 이 라운드가 손대지 않는다).

  고침: insurer_id 가 없을 때, insurers 전체를 읽어 이름을 NFKC로 정규화해
  대조한다(round593과 같은 처방). 유일하게 하나만 맞을 때만 해석하는 기존
  안전장치(동명 보험사 대비, round105)는 그대로 유지된다 — 정규화 형태만
  다른 동명 보험사 2곳이 있어도 여전히 애매함(NO_INSURER)으로 막힌다.

  [1] 소스 확인 — 새 정규화 대조가 실제로 있음.
  [2] 실제 Flask 앱 — NFD로 보낸 보험사 이름이 NFC로 저장된 기존 보험사와
      매칭되어 사건이 실제로 생성됨(핵심 재현).
  [3] 되돌림-증명 — unicodedata.normalize 를 프로세스 메모리에서만(디스크
      무수정) 항등함수로 바꿔치기해 옛(취약) 동작 — NO_INSURER 400 — 이 실제로
      재현됨을 확인한 뒤 원복.
  [4] 회귀 없음 — 바이트가 완전히 같은 이름(기존 경로)은 그대로 매칭된다.
  [5] 부수 안전성 — 정규화 형태만 다르게 등록된 동명 보험사 2곳은 여전히
      애매함(NO_INSURER)으로 막히고 어느 쪽도 조용히 골라잡히지 않는다.

      python test_scan_round594_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 594라운드 회귀 — 관리자 사건등록 보험사 이름매칭 유니코드 정규화 불일치")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
APP_SRC = io.open(os.path.join(HERE, "app.py"), encoding="utf-8").read()

i0 = APP_SRC.index("def api_case_create(")
i1 = APP_SRC.index("\n\n\n", i0)
FN_SRC = APP_SRC[i0:i1]

chk('_norm_target = unicodedata.normalize("NFKC", insurer_name)' in FN_SRC,
    "★★★★★ api_case_create가 보험사 이름을 NFKC로 정규화해 대조한다")
chk('unicodedata.normalize("NFKC", r["name"] or "") == _norm_target' in FN_SRC,
    "★★★★★ insurers 각 행의 이름도 같은 방식으로 정규화해 비교한다")
chk('"SELECT id, name FROM insurers WHERE name=? "' not in FN_SRC,
    "STEP 옛 바이트비교 SQL(name=?)은 이 함수에서 사라졌다")
chk("row = _cands[0] if len(_cands) == 1 else None" in FN_SRC,
    "★★★ 유일하게 하나만 맞을 때만 해석한다(동명 보험사 안전장치 유지)")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[5] 실제 Flask 앱 실행")
# ══════════════════════════════════════════════════════════════
_tmpdir = tempfile.mkdtemp(prefix="round594_")
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
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r594admin','x','검증','중간관리자')")
    conn.commit()

    admin = A.app.test_client()
    _tok = "r594-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r594admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    def _create_case_by_name(case_no, insurer_text):
        payload = {"case_no": case_no, "category": "누수·배관·설비",
                   "insurer": insurer_text, "no_photo": True}
        r = admin.post("/api/cases", headers=_hdr, json=payload)
        return r, (r.get_json() or {})

    # ── [2] 핵심 재현 — NFC로 저장된 보험사를 NFD 표기로 이름만 보낸다 ──
    NFC_NAME = "R594정규화검증보험"
    NFD_NAME = unicodedata.normalize("NFD", NFC_NAME)
    assert NFC_NAME != NFD_NAME, "테스트 전제(NFC!=NFD 바이트다름) 불성립"
    iid1 = conn.execute("INSERT INTO insurers(name) VALUES(?)", (NFC_NAME,)).lastrowid
    conn.commit()

    r2, j2 = _create_case_by_name("R594-CASE-01", NFD_NAME)
    chk(r2.status_code == 200 and j2.get("ok") is True,
        "★★★★★ NFD 표기로 보내도 NFC로 저장된 기존 보험사와 매칭되어 사건이 생성된다"
        "(예전엔 NO_INSURER 400으로 튕겼다)", j2)
    if j2.get("ok"):
        row1 = conn.execute("SELECT insurer_id, insurer FROM cases WHERE id=?",
                             (j2["id"],)).fetchone()
        chk(row1 is not None and row1["insurer_id"] == iid1,
            "★★★★★ 실제 DB에도 올바른 insurer_id로 저장됐다",
            dict(row1) if row1 else None)

    # ── [3] 되돌림-증명 — normalize를 프로세스 메모리에서만 항등함수로 ──
    NFC_NAME2 = "R594되돌림검증보험"
    NFD_NAME2 = unicodedata.normalize("NFD", NFC_NAME2)
    assert NFC_NAME2 != NFD_NAME2, "테스트 전제(NFC!=NFD 바이트다름) 불성립"
    conn.execute("INSERT INTO insurers(name) VALUES(?)", (NFC_NAME2,))
    conn.commit()

    _orig_normalize = A.unicodedata.normalize
    A.unicodedata.normalize = lambda form, s: s  # 정규화를 안 한 것과 동일 효과
    try:
        r3, j3 = _create_case_by_name("R594-CASE-02", NFD_NAME2)
        chk(r3.status_code == 400 and j3.get("code") == "NO_INSURER",
            "★★★★★ 정규화를 되돌리면 NFD 표기 매칭이 실패해 NO_INSURER로 빠진다"
            "(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명)", j3)
        row2 = conn.execute("SELECT 1 FROM cases WHERE case_no=?", ("R594-CASE-02",)).fetchone()
        chk(row2 is None,
            "★★★★★ 되돌린 상태에서는 실제로 사건이 생성되지 않았다"
            "(라운드594가 막으려던 바로 그 사고)")
    finally:
        A.unicodedata.normalize = _orig_normalize

    # ── [4] 회귀 없음 — 바이트가 완전히 같은 이름은 여전히 매칭된다 ──
    NFC_NAME3 = "R594일반매칭보험"
    iid3 = conn.execute("INSERT INTO insurers(name) VALUES(?)", (NFC_NAME3,)).lastrowid
    conn.commit()
    r4, j4 = _create_case_by_name("R594-CASE-03", NFC_NAME3)
    chk(r4.status_code == 200 and j4.get("ok") is True,
        "STEP 바이트가 완전히 같은 이름(기존 경로)은 그대로 매칭된다(과잉 변경 아님)", j4)
    if j4.get("ok"):
        row3 = conn.execute("SELECT insurer_id FROM cases WHERE id=?", (j4["id"],)).fetchone()
        chk(row3 is not None and row3["insurer_id"] == iid3,
            "STEP insurer_id도 올바르게 채워졌다", dict(row3) if row3 else None)

    # ── [5] 부수 안전성 — 정규화 형태가 서로 다른 동명 보험사 2곳은 애매함으로 걸러진다 ──
    NFC_NAME4 = "R594동명검증보험"
    NFD_NAME4 = unicodedata.normalize("NFD", NFC_NAME4)
    conn.execute("INSERT INTO insurers(name) VALUES(?)", (NFC_NAME4,))
    conn.execute("INSERT INTO insurers(name) VALUES(?)", (NFD_NAME4,))
    conn.commit()
    r5, j5 = _create_case_by_name("R594-CASE-04", NFC_NAME4)
    chk(r5.status_code == 400 and j5.get("code") == "NO_INSURER",
        "★★★ 정규화 형태만 다르게 등록된 동명 보험사 2곳은 애매함으로 막히고 "
        "어느 쪽도 조용히 골라잡히지 않는다(옛 코드는 이 경우를 감지하지 못하고 "
        "우연히 바이트가 맞는 한쪽만 조용히 골랐을 위험이 있었다)", j5)
    row4 = conn.execute("SELECT 1 FROM cases WHERE case_no=?", ("R594-CASE-04",)).fetchone()
    chk(row4 is None, "STEP 애매한 동명 보험사 상황에서는 사건이 생성되지 않았다")

    conn.close()

except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]~[5] 실제 앱 재현 준비/실행", f"{type(e).__name__}: {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
