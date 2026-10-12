# -*- coding: utf-8 -*-
"""스캔 458라운드 회귀 — 보험사 등록의 유니코드 정규화 미비로 중복검사
우회, 1건.

`api_insurer_create()`(app.py:8491-)의 중복검사(`SELECT 1 FROM insurers
WHERE name=?`)는 단순 바이트열 대조다. 유니코드는 같은 글자를 서로 다른
바이트열로도 표기할 수 있다(한글 자모를 완성형 대신 풀어쓴 NFD, 전각
영문 vs 반각 영문 등) — 시각적으로 완전히 같은 기관명을 다른 정규화
형태로 등록하면 이 대조를 그대로 통과해 라운드68이 막으려던 "같은
기관명 행이 2개" 사고가 다른 경로로 재발한다(맥에서 복사한 텍스트는
흔히 NFD). `unicodedata.normalize("NFKC", name)`을 등록·비교 양쪽에
적용해 막는다.

[1] 소스 확인 — import·정규화 호출이 실제로 있음.
[2] 실제 Flask 앱으로 되돌림-증명 — unicodedata.normalize 를 프로세스
    메모리에서만(디스크 무수정) 항등함수로 바꿔치기해 옛(취약) 동작을
    재현한 뒤 복원, 새(고쳐진) 동작과 대조.
"""
import io
import os
import sys
import tempfile
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 458라운드 회귀 — 보험사명 유니코드 정규화 중복검사 우회")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
APP_SRC = io.open(os.path.join(HERE, "app.py"), encoding="utf-8").read()

chk("import unicodedata" in APP_SRC,
    "★★★★★ app.py가 unicodedata를 import한다")
chk('name = unicodedata.normalize("NFKC", name)' in APP_SRC,
    "★★★★★ api_insurer_create()가 이름을 NFKC로 정규화한다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 Flask 앱 — 되돌림-증명")
# ══════════════════════════════════════════════════════════════
_tmpdir = tempfile.mkdtemp(prefix="round458_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "1"
sys.path.insert(0, HERE)

try:
    import db as DB              # noqa: E402
    DB.init_db()
    import app as A              # noqa: E402

    def _admin_client():
        c = A.app.test_client()
        r = c.post("/api/login", json={"username": "admin", "password": "bokguon2026"})
        assert r.status_code == 200, f"데모 관리자 로그인 실패: {r.status_code} {r.get_data(as_text=True)}"
        csrf = r.get_json()["csrf"]
        return c, csrf

    #  ⚠ 아래 두 상수쌍은 [2]-(B)에서 unicodedata.normalize 를 프로세스
    #    전역으로(A.unicodedata 는 이 파일의 unicodedata 와 같은 싱글턴
    #    모듈 객체다) 임시로 항등함수로 바꾸는 실험을 하므로, 그 실험이
    #    끝나기 전까지 이 함수로 새 값을 또 계산하면 안 된다 — 필요한 값은
    #    전부 지금(정상 상태) 미리 계산해 둔다.
    def _count_by_exact_names(conn, *names):
        n = 0
        for nm in names:
            n += conn.execute("SELECT COUNT(*) n FROM insurers WHERE name=?",
                               (nm,)).fetchone()["n"]
        return n

    NFC_NAME = "R458검증보험"          # 이미 완성형(정규화 기본형)
    NFD_NAME = unicodedata.normalize("NFD", NFC_NAME)
    assert NFC_NAME != NFD_NAME, "테스트 전제(NFC!=NFD 바이트다름) 불성립"
    NFC_NAME2 = "R458되돌림보험"
    NFD_NAME2 = unicodedata.normalize("NFD", NFC_NAME2)
    assert NFC_NAME2 != NFD_NAME2, "테스트 전제(NFC!=NFD 바이트다름) 불성립"

    # ── (A) 현재(고쳐진) 코드 — NFD 중복이 실제로 막히는지 ──
    c, csrf = _admin_client()
    r1 = c.post("/api/insurers", json={"name": NFC_NAME, "fee_rate_pct": 9},
                headers={"X-CSRF-Token": csrf})
    r2 = c.post("/api/insurers", json={"name": NFD_NAME, "fee_rate_pct": 9},
                headers={"X-CSRF-Token": csrf})
    conn = DB.get_db()
    total_fixed = _count_by_exact_names(conn, NFC_NAME, NFD_NAME)
    conn.close()
    chk(r1.status_code == 200, "첫 등록(NFC 표기)은 정상 성공", r1.status_code)
    chk(r2.status_code == 400,
        "★★★★★ 같은 이름의 NFD 표기 재등록은 중복으로 거부된다(400)",
        (r2.status_code, r2.get_data(as_text=True)))
    chk(total_fixed == 1,
        "★★★★★ DB에는 정확히 1행만 남는다(고쳐진 동작)", total_fixed)

    # 대조군 — 완전히 다른 이름은 여전히 정상 등록됨(과잉차단 아님)
    r3 = c.post("/api/insurers", json={"name": "R458검증보험(별도)", "fee_rate_pct": 9},
                headers={"X-CSRF-Token": csrf})
    chk(r3.status_code == 200, "이름이 실제로 다르면 정상 등록됨(과잉차단 아님)", r3.status_code)

    # ── (B) 되돌림 — normalize를 프로세스 메모리에서만 항등함수로 바꿔
    #        옛(취약) 동작이 실제로 재현되는지 증명(디스크 파일은 무수정) ──
    _orig_normalize = A.unicodedata.normalize
    A.unicodedata.normalize = lambda form, s: s  # 정규화를 안 한 것과 동일 효과
    try:
        c2, csrf2 = _admin_client()
        r4 = c2.post("/api/insurers", json={"name": NFC_NAME2, "fee_rate_pct": 9},
                     headers={"X-CSRF-Token": csrf2})
        r5 = c2.post("/api/insurers", json={"name": NFD_NAME2, "fee_rate_pct": 9},
                     headers={"X-CSRF-Token": csrf2})
        conn2 = DB.get_db()
        total_reverted = _count_by_exact_names(conn2, NFC_NAME2, NFD_NAME2)
        conn2.close()
        chk(r4.status_code == 200 and r5.status_code == 200,
            "★★★★★ 정규화를 되돌리면 NFD 재등록도 200으로 통과한다"
            "(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명)",
            (r4.status_code, r5.status_code))
        chk(total_reverted == 2,
            "★★★★★ 되돌린 상태에서는 실제로 중복 행이 2개 생긴다"
            "(라운드68이 막으려던 바로 그 사고)", total_reverted)
    finally:
        A.unicodedata.normalize = _orig_normalize

except Exception as e:                                              # noqa: BLE001
    chk(False, "[2] 실제 앱 재현 준비/실행", f"{type(e).__name__}: {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
