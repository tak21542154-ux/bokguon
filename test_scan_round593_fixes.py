# -*- coding: utf-8 -*-
"""스캔 593라운드 회귀 — 연락처 일괄등록(api_contact_import)의 업체명 대조가
유니코드 정규화 형태를 안 봐서 실재하는 업체를 "없음"으로 오판하던 결함.

  사업자번호가 없는 업체는 업체명으로 대조하는데(9727행 부근, 말단 경로),
  예전 코드는 단순 SQL "WHERE name=?" 바이트열 비교였다. 유니코드는 같은
  글자를 다른 바이트열로도 적을 수 있어(한글 자모를 완성형 대신 풀어쓴 NFD —
  맥에서 복사한 텍스트에 흔하다) 시각적으로 완전히 같은 업체명인데도 이
  비교가 실패해, 되올린 엑셀 행이 "존재하지 않는 업체"(skip_none)로 조용히
  버려졌다 — 라운드458이 보험사명 등록 중복검사에서 고친 것과 같은 결함군이
  이 함수만 빠져 있었다(app.py 전체에 unicodedata.normalize 호출은 그 한
  곳뿐이었다).

  고침: 잠금을 잡기 전에 partners 전체를 한 번 읽어 이름을 NFKC로 정규화한
  사전(_by_norm_name)을 만들고, 엑셀 이름도 같은 방식으로 정규화해 대조한다
  (업체 400여 곳 — round70이 지킨 "쓰기 잠금은 짧게" 원칙과 같은 자리에 둠).
  이 방식은 부수적으로 "동명업체" 중복 판정도 더 안전해진다 — 두 업체가
  서로 다른 정규화 형태로 저장돼 있어도(옛 코드는 이 경우 하나만 우연히
  걸려 엉뚱한 업체가 조용히 갱신될 수 있었다) 이제는 둘 다 같은 이름으로
  잡혀 애매함(skip_dup)으로 처리된다.

  [1] 소스 확인 — 새 정규화 사전·조회가 실제로 있음.
  [2] 실제 Flask 앱 — NFD로 되올린 엑셀 이름이 NFC로 저장된 기존 업체와
      매칭되어 연락처가 실제로 갱신됨(핵심 재현).
  [3] 되돌림-증명 — unicodedata.normalize 를 프로세스 메모리에서만(디스크
      무수정) 항등함수로 바꿔치기해 옛(취약) 동작 — 매칭 실패·not_found — 이
      실제로 재현됨을 확인한 뒤 원복.
  [4] 회귀 없음 — 바이트가 완전히 같은 이름(기존 다수 경로)은 그대로 매칭됨.
  [5] 부수 안전성 — 서로 다른 정규화 형태로 저장된 동명업체 2곳은 여전히
      "동명업체" 애매함으로 걸러지고 어느 쪽도 조용히 갱신되지 않음.

      python test_scan_round593_fixes.py
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
print("  스캔 593라운드 회귀 — 연락처 일괄등록 업체명 유니코드 정규화 불일치")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
APP_SRC = io.open(os.path.join(HERE, "app.py"), encoding="utf-8").read()

chk('_by_norm_name.setdefault(unicodedata.normalize("NFKC", _pr["name"] or ""), []).append(_pr["id"])'
    in APP_SRC,
    "★★★★★ api_contact_import가 partners 이름을 NFKC로 정규화한 사전을 만든다")
chk('same_ids = _by_norm_name.get(unicodedata.normalize("NFKC", name), [])' in APP_SRC,
    "★★★★★ 엑셀 업체명도 같은 방식으로 정규화해 대조한다")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[5] 실제 Flask 앱 실행")
# ══════════════════════════════════════════════════════════════
_tmpdir = tempfile.mkdtemp(prefix="round593_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A
    from openpyxl import Workbook

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r593admin','x','검증','중간관리자')")
    conn.commit()

    admin = A.app.test_client()
    _tok = "r593-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r593admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    def _import_one(company_cell_name, email):
        wb = Workbook()
        ws = wb.active
        ws.append(["업체명", "이메일"])
        ws.append([company_cell_name, email])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        r = admin.post("/api/contacts/import", headers=_hdr,
                        data={"file": (buf, "test.xlsx")},
                        content_type="multipart/form-data")
        return r, (r.get_json() or {})

    # ── [2] 핵심 재현 — NFC로 저장된 업체를 NFD 표기 엑셀로 되올린다 ──
    NFC_NAME = "R593정규화검증업체"
    NFD_NAME = unicodedata.normalize("NFD", NFC_NAME)
    assert NFC_NAME != NFD_NAME, "테스트 전제(NFC!=NFD 바이트다름) 불성립"
    pid1 = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES(?,'시행사','활성')",
        (NFC_NAME,)).lastrowid
    conn.commit()

    r2, j2 = _import_one(NFD_NAME, "r593-nfd@example.com")
    chk(r2.status_code == 200 and j2.get("updated") == 1 and j2.get("not_found") == 0,
        "★★★★★ NFD 표기로 되올려도 NFC로 저장된 기존 업체와 매칭되어 갱신된다"
        "(예전엔 not_found로 조용히 버려졌다)", j2)
    row1 = conn.execute("SELECT email FROM partners WHERE id=?", (pid1,)).fetchone()
    chk(row1["email"] == "r593-nfd@example.com",
        "★★★★★ 실제 DB에도 이메일이 반영됐다", dict(row1))

    # ── [3] 되돌림-증명 — normalize를 프로세스 메모리에서만 항등함수로 ──
    NFC_NAME2 = "R593되돌림검증업체"
    NFD_NAME2 = unicodedata.normalize("NFD", NFC_NAME2)
    assert NFC_NAME2 != NFD_NAME2, "테스트 전제(NFC!=NFD 바이트다름) 불성립"
    pid2 = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES(?,'시행사','활성')",
        (NFC_NAME2,)).lastrowid
    conn.commit()

    _orig_normalize = A.unicodedata.normalize
    A.unicodedata.normalize = lambda form, s: s  # 정규화를 안 한 것과 동일 효과
    try:
        r3, j3 = _import_one(NFD_NAME2, "r593-should-not-apply@example.com")
        chk(r3.status_code == 200 and j3.get("not_found") == 1 and j3.get("updated") == 0,
            "★★★★★ 정규화를 되돌리면 NFD 표기 매칭이 실패해 not_found로 빠진다"
            "(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명)", j3)
        row2 = conn.execute("SELECT email FROM partners WHERE id=?", (pid2,)).fetchone()
        chk(row2["email"] is None,
            "★★★★★ 되돌린 상태에서는 실제로 이메일이 반영되지 않는다"
            "(라운드593이 막으려던 바로 그 사고)", dict(row2))
    finally:
        A.unicodedata.normalize = _orig_normalize

    # ── [4] 회귀 없음 — 바이트가 완전히 같은 이름은 여전히 매칭된다 ──
    NFC_NAME3 = "R593일반매칭업체"
    pid3 = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES(?,'시행사','활성')",
        (NFC_NAME3,)).lastrowid
    conn.commit()
    r4, j4 = _import_one(NFC_NAME3, "r593-plain@example.com")
    chk(r4.status_code == 200 and j4.get("updated") == 1,
        "STEP 바이트가 완전히 같은 이름(기존 절대다수 경로)은 그대로 매칭된다"
        "(과잉 변경 아님)", j4)

    # ── [5] 부수 안전성 — 정규화 형태가 서로 다른 동명업체 2곳은 애매함으로 걸러진다 ──
    NFC_NAME4 = "R593동명검증업체"
    NFD_NAME4 = unicodedata.normalize("NFD", NFC_NAME4)
    pid4a = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES(?,'시행사','활성')",
        (NFC_NAME4,)).lastrowid
    pid4b = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES(?,'시행사','활성')",
        (NFD_NAME4,)).lastrowid
    conn.commit()
    r5, j5 = _import_one(NFC_NAME4, "r593-dup@example.com")
    chk(r5.status_code == 200 and j5.get("skipped_duplicate") == 1 and j5.get("updated") == 0,
        "★★★ 정규화 형태만 다르게 저장된 동명업체 2곳은 '동명업체'로 걸러지고 "
        "어느 쪽도 조용히 갱신되지 않는다(옛 코드는 이 경우를 감지 못하고 "
        "우연히 바이트가 맞는 한쪽만 조용히 갱신할 위험이 있었다)", j5)
    row4a = conn.execute("SELECT email FROM partners WHERE id=?", (pid4a,)).fetchone()
    row4b = conn.execute("SELECT email FROM partners WHERE id=?", (pid4b,)).fetchone()
    chk(row4a["email"] is None and row4b["email"] is None,
        "STEP 애매한 동명업체 둘 다 이메일이 반영되지 않았다", (dict(row4a), dict(row4b)))

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
