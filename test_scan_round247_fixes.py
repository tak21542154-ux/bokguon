# -*- coding: utf-8 -*-
"""스캔 247라운드 회귀 — admin.js 가견적기준·표준단가 화면 결함 3건
   (admin.js estbands/boq 화면 Agent 병렬조사로 발견).

  [1] boq·estbands 메뉴의 추가·수정·삭제 버튼이 등급 무관하게 항상 그려졌다
      — POST/DELETE /api/est-bands 는 최고관리자(3) 전용, POST/PATCH/DELETE
      /api/boq 는 중간관리자(2) 전용인데, 같은 메뉴그룹(시스템)의 형제
      admins·set(246라운드) 은 이미 자기차단이 있었다. 폼을 다 채운 뒤에야
      403을 만나는 시간낭비 패턴 — myRank() 로 두 화면 모두 자기차단 추가.

  [2] api_est_band_set 이 ON CONFLICT 로 기존 기준을 조용히 덮어쓰면서 옛값을
      감사로그에 안 남겼다 — 형제(api_boq_update)와 224라운드가 정확히 같은
      이유로 고친 ai_auto_threshold 는 이미 옛값→새값을 남긴다. 덮어쓰기 전에
      먼저 읽어 로그에 남기도록 수정.

  [3] api_boq_update 가 자동견적 엔진에 연결된(sku_key 有) 행의 unit 을
      아무 값으로나 바꿀 수 있게 뒀다 — _load_price_book() 자신의 주석이 이미
      "unit 이 엔진 내장값과 다르면 조용히 무시하고 내장 기본값으로 돌아간다"
      고 경고하는데, 그 검사가 주입 시점에만 있고 실제 값을 고치는 이 라우트
      에는 없었다. 저장은 200 성공, 그 순간부터 가견적 계산엔 영원히 반영
      안 됨(에러도 로그도 없음) — 서버는 이제 막고, 화면(boqEdit)도 미리 경고.

      python test_scan_round247_fixes.py
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


ADMIN_JS = read("static/admin.js")
APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 247라운드 회귀 — 가견적기준·표준단가 화면 결함 3건")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — 등급 자기차단")
# ------------------------------------------------------------
i0 = ADMIN_JS.index("VIEWS.estbands = async ()")
i1 = ADMIN_JS.index("\n// ── 표준 단가·내역 ──", i0)
eb_body = ADMIN_JS[i0:i1]
chk("myRank() >= 3 ? `<div class=\"grid2\">" in eb_body,
    "★★★★ VIEWS.estbands 의 입력폼이 myRank()>=3 으로 스스로 가려진다")
chk('myRank() >= 3 ? `<button class="btn g sm" data-act="ebDel"' in eb_body,
    "★★★ 삭제 버튼도 같은 문턱으로 가려진다")

i2 = ADMIN_JS.index("VIEWS.boq = async ()")
i3 = ADMIN_JS.index("\nfunction boqForm", i2)
boq_body = ADMIN_JS[i2:i3]
chk('myRank() >= 2 ? `<button class="btn p sm" data-act="boqForm">' in boq_body,
    "★★★★ VIEWS.boq 의 '+ 항목 추가' 버튼이 myRank()>=2 로 스스로 가려진다")
chk('myRank() >= 2 ? `<button class="btn g sm" data-act="boqEdit"' in boq_body,
    "★★★ 수정 버튼도 같은 문턱으로 가려진다")
chk('myRank() >= 2 ? `<button class="btn danger sm" data-act="deleteBoq"' in boq_body,
    "★★★ 비활성 버튼도 같은 문턱으로 가려진다")
chk('data-act="boqHistory"' in boq_body,
    "STEP 이력(읽기전용) 버튼은 등급 무관하게 그대로 남아 있다(과잉차단 아님)")

print("\n[1] 소스 확인 — 옛값→새값 로그 + SKU 단위보호")
i4 = APP_SRC.index("def api_est_band_set(")
i5 = APP_SRC.index("\n@app.delete(\"/api/est-bands", i4)
eb_route = APP_SRC[i4:i5]
chk("prev = one(conn.execute(" in eb_route and "SELECT min_price, max_price, src FROM est_check_band" in eb_route,
    "★★★★ 덮어쓰기 전 기존 기준값을 먼저 읽는다")
chk('f"{major}/{sev} {_fmt(prev[\'min_price\'])}' in eb_route,
    "★★★ 기존 기준이 있으면 옛값→새값 형태로 로그를 남긴다")

i6 = APP_SRC.index("def api_boq_update(")
i7 = APP_SRC.index("\n\n@app.", i6)
boq_route = APP_SRC[i6:i7]
chk('vals["unit"] != RE.SKU[sku_key][2]' in boq_route,
    "★★★★ 엔진 연결(sku_key) 행의 unit 변경을 실제 SKU 단위와 대조한다")
chk('"code": "SKU_UNIT_MISMATCH"' in boq_route,
    "STEP 불일치 시 전용 코드로 400 거부한다(조용히 성공시키지 않는다)")

i8 = ADMIN_JS.index("function boqEdit(")
i9 = ADMIN_JS.index("\nasync function boqSave(", i8)
edit_body = ADMIN_JS[i8:i9]
chk("b.sku_key ? `<div class=\"notice\"" in edit_body,
    "★★★ boqEdit() 모달이 엔진 연결 행에는 미리 경고 문구를 보여준다")

# ============================================================
print("\n[2] 실행 — Flask 실서버로 실제 시나리오 검증")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round247_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A
    import repair_estimate as RE

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r247top','x','검증','최고관리자')")
    conn.commit(); conn.close()

    top = A.app.test_client()
    tok = "r247-csrf"
    with top.session_transaction() as sess:
        sess["admin"] = "r247top"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    #  ── (a) est-bands 옛값→새값 로그 실측 ──
    r1 = top.post("/api/est-bands", json={
        "major": "가드레일·방호울타리", "severity": "중대",
        "min_price": "5,000,000", "max_price": "12,000,000", "src": "1차 기준"}, headers=hdr)
    chk(r1.status_code == 200, "STEP 최초 기준 등록 성공", r1.status_code)
    r2 = top.post("/api/est-bands", json={
        "major": "가드레일·방호울타리", "severity": "중대",
        "min_price": "3,000,000", "max_price": "8,000,000", "src": "2차 정정"}, headers=hdr)
    chk(r2.status_code == 200, "STEP 같은 공종·파손정도 재저장(=수정) 성공", r2.status_code)
    conn = DB.get_db()
    last_log_row = conn.execute(
        "SELECT detail FROM activity_log WHERE action='가견적 점검 기준 설정' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    detail = (last_log_row["detail"] or "") if last_log_row else ""
    chk("5,000,000" in detail and "12,000,000" in detail,
        "★★★★ 두 번째 저장(수정)의 감사로그에 옛값(5,000,000~12,000,000)이 실제로 남는다"
        "(고치기 전엔 새값만 남아 무엇에서 무엇으로 바뀌었는지 알 수 없었다)",
        detail)
    chk("3,000,000" in detail and "8,000,000" in detail,
        "STEP 새값(3,000,000~8,000,000)도 함께 남는다", detail)

    #  ── (b) boq SKU 단위 보호 실측 — 실제 SKU 키 하나를 골라 재현 ──
    sku_key = next(iter(RE.SKU))
    sku_unit = RE.SKU[sku_key][2]
    wrong_unit = sku_unit + "_다른단위"
    conn = DB.get_db()
    bid = conn.execute(
        "INSERT INTO standard_boq(major,item,spec,unit,ref_price,price_src,price_date,"
        "                         active,is_demo,sku_key,created_at,updated_at) "
        "VALUES('가드레일·방호울타리','R247항목','규격',?,10000,'근거','2026',1,0,?,datetime('now'),datetime('now'))",
        (sku_unit, sku_key)).lastrowid
    conn.commit(); conn.close()

    r3 = top.patch(f"/api/boq/{bid}", json={"unit": wrong_unit}, headers=hdr)
    chk(r3.status_code == 400 and r3.get_json().get("code") == "SKU_UNIT_MISMATCH",
        "★★★★ 엔진 연결 행의 단위를 실제 SKU 단위와 다르게 바꾸려 하면 거부된다"
        "(고치기 전엔 200 으로 조용히 성공해 그 뒤로 가견적 계산에서 영원히 빠졌다)",
        r3.get_json())
    conn = DB.get_db()
    unit_after = conn.execute("SELECT unit FROM standard_boq WHERE id=?", (bid,)).fetchone()["unit"]
    conn.close()
    chk(unit_after == sku_unit, "STEP 거부된 시도는 실제로 반영되지 않았다(단위 그대로)", unit_after)

    #  ── (c) 대조군 — 단위를 그대로 두고 다른 필드만 고치면 정상 동작 ──
    r4 = top.patch(f"/api/boq/{bid}", json={"ref_price": "12000"}, headers=hdr)
    chk(r4.status_code == 200,
        "★★★ 대조군 — 단위를 안 건드리고 다른 필드만 고치면 여전히 정상 동작한다"
        "(과잉차단 아님)", r4.get_json())
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드247 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
