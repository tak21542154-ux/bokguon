# -*- coding: utf-8 -*-
"""스캔 30라운드 회귀 — 조사 에이전트가 찾은 것 중 이번에 고친 두 자리.

  ① 검색 필터의 가운뎃점 표기 불일치 — _partner_filter·_case_filter 가
     search_filters 의 정규화 없이 각자 LIKE 를 다시 짜서, 정부 공식 업종
     표기('ㆍ' U+318D 아래아)를 쓰는 협력사가 표준 가운뎃점('·' U+00B7)
     검색에 하나도 안 걸렸다(실측: 협력사 10곳, id 305~314). 결과가 0건이라
     검색이 잘 된 줄 알고 넘어간다. 새 공용 함수 _kw_like_clause 로 세
     자리(search_filters·_partner_filter·_case_filter)를 하나로 묶었다.
     ⚠ 이 항목의 실행 회귀는 test_b4_review_fixes.py 의 [부록-2] 에 있다
       (그 파일이 이미 가운뎃점 검사를 갖고 있어 같은 곳에 모았다) — 여기서는
       소스 배선만 다시 확인한다.

  ② 하자보증 만료 임박·당일 알림이 아무에게도 안 나갔다 — /api/calendar 를
     그 달로 직접 넘겨봐야만 보였고 notify() 호출이 전무했다. 사용자 결정
     (2026-08-21): 운영팀에게만, 만료 30일 전·7일 전·당일 세 번 알린다.
     sweep_warranty_expiry 를 추가해 인라인 스윕(_sweep_if_due)과 5분 주기
     크론(manage.py cmd_sweep) 양쪽에 걸었다 — 하나만 걸면 사람이 화면을
     안 열거나 크론이 안 도는 쪽에서 조용히 샌다.

      python test_scan_round30_fixes.py
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def slice_by_anchor(src, start_marker, end_marker):
    i = src.find(start_marker)
    j = src.find(end_marker, i)
    if i < 0 or j < 0 or j <= i:
        return ""
    return src[i:j]


APP = read("app.py")
MNG = read("manage.py")

print("═" * 72)
print("  스캔 30라운드 회귀 — 검색 가운뎃점 정규화 · 하자보증 만료 알림")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 검색 필터 — 세 자리가 같은 정규화 함수를 쓰는가(소스 배선)")
# ──────────────────────────────────────────────────────────────
chk("def _kw_like_clause(kw, cols):" in APP, "★ 공용 정규화 함수를 찾았다")

_pf = slice_by_anchor(APP, "def _partner_filter(args):", "\ndef ")
chk("_kw_like_clause(" in _pf,
    "★★★ _partner_filter 가 공용 함수를 쓴다(실측 결함 재현·수정 확인)",
    "안 쓰면 아래아 표기 협력사가 표준 검색에 하나도 안 걸린다")

_cf = slice_by_anchor(APP, "def _case_filter(args):", "\ndef ")
chk("_kw_like_clause(" in _cf,
    "★★★ _case_filter 도 공용 함수를 쓴다(실측 결함 재현·수정 확인)")

_sf = slice_by_anchor(APP, "def search_filters(", "\n\n\n# ── 관리자")
chk("_kw_like_clause(" in _sf, "★ search_filters 자신도 같은 함수로 정리됐다(중복 제거)")

print("  (실행 회귀는 test_b4_review_fixes.py [부록-2] 참고)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 하자보증 만료 알림 — 소스 배선")
# ──────────────────────────────────────────────────────────────
chk("def sweep_warranty_expiry(conn):" in APP, "★ 스윕 함수를 찾았다")
chk("WARRANTY_ALERT_DAYS = (30, 7, 0)" in APP, "★ 30일·7일·당일 세 문턱이 그대로 있다")
chk("sweep_warranty_expiry(conn)" in slice_by_anchor(APP, "def _sweep_if_due():", "\n\n\n@app.get"),
    "★★ 화면을 열 때 곁들이는 인라인 스윕에도 걸려 있다")
chk("A.sweep_warranty_expiry(conn)" in MNG,
    "★★★ 5분 주기 크론(manage.py cmd_sweep)에도 걸려 있다 — 이게 진짜 실행 경로다",
    "인라인만 있으면 아무도 화면을 안 여는 밤·주말엔 여전히 안 나간다")
chk('audience_type="admin"' in slice_by_anchor(APP, "def sweep_warranty_expiry(conn):", "\n\ndef "),
    "★ 알림 대상이 운영팀이다(사용자 결정 — 보험사에는 안 보냄)")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 30일·7일·당일 문턱에서 정확히 한 번씩만 나가는가")
# ──────────────────────────────────────────────────────────────
import tempfile
_tmpdir = tempfile.mkdtemp(prefix="warranty_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "wt.db")
sys.path.insert(0, HERE)
try:
    import db as DB
    import app as A
    DB.init_db()
    conn = DB.get_db()

    today = conn.execute("SELECT date('now','+9 hours')").fetchone()[0]

    def mk(days, no):
        completed = conn.execute(
            "SELECT date(?, '-24 months', ?)", (today, f"+{days} days")).fetchone()[0]
        return conn.execute(
            "INSERT INTO cases(case_no,category,status,completed_at,warranty_months,"
            "partner_name,created_at,is_demo) "
            "VALUES(?,'누수·배관·설비','완료',?,24,'검증업체',datetime('now','+9 hours'),0)",
            (no, completed)).lastrowid

    c30 = mk(30, "RD30-A")
    c7 = mk(7, "RD30-B")
    c0 = mk(0, "RD30-C")
    c99 = mk(99, "RD30-D")   # 문턱이 아니다 — 알림이 없어야 정상
    conn.commit()

    n = A.sweep_warranty_expiry(conn)
    chk(n == 3, "★★★ 문턱 3건에서만 발송된다(99일짜리는 안 걸림)", f"발송={n}")

    for cid, no, want in ((c30, "RD30-A", "보증만료30일전"),
                          (c7, "RD30-B", "보증만료7일전"),
                          (c0, "RD30-C", "보증만료당일")):
        row = conn.execute(
            "SELECT ntype FROM notifications WHERE case_id=?", (cid,)).fetchone()
        chk(bool(row) and row["ntype"] == want, f"★ {no} → {want}", row)

    n99 = conn.execute(
        "SELECT COUNT(*) FROM notifications WHERE case_id=?", (c99,)).fetchone()[0]
    chk(n99 == 0, "★ 문턱이 아닌 99일짜리는 알림이 없다(과잉 발송 아님)", n99)

    n2 = A.sweep_warranty_expiry(conn)
    chk(n2 == 0, "★★★ 같은 스윕을 다시 돌려도 중복 발송되지 않는다", f"재실행 발송={n2}")

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 하자보증 만료 알림 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
