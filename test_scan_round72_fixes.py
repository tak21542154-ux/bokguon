# -*- coding: utf-8 -*-
"""스캔 72라운드 회귀 — 피해현장사진 AI 파손분석 결과가 순서 보장 없이 덮어써짐.

  _upload_damage_photos 의 AI 파손 분석은 트랜잭션 밖에서 최대 20초 걸린다
  (외부 Gemini 호출). 사건에 사진이 연달아 두 번 올라오면(보험사가 빠뜨린
  사진을 뒤늦게 추가하는 흔한 상황) 먼저 올라온 사진의 분석이 더 늦게 끝나
  나중 사진의 최신 판정을 그대로 덮어쓸 수 있었다 — 기존 BEGIN IMMEDIATE 는
  두 갱신이 뒤섞이지 않게만 막을 뿐 "어느 쪽이 최신인가" 는 보지 않았다.
  photos.id 는 AUTOINCREMENT 라 업로드 순서와 일치하므로, 이미 기록된
  ai_photo_id 보다 새 사진이 더 나중에 올라온 것일 때만 갱신하도록 고쳤다.

      python test_scan_round72_fixes.py
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

print("═" * 72)
print("  스캔 72라운드 회귀 — AI 파손분석 결과 순서보장 없는 덮어쓰기")
print("═" * 72)


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
body = _body(APP_SRC, "_upload_damage_photos")
chk("AND (ai_photo_id IS NULL OR ai_photo_id < ?)" in body,
    "★★★ AI 파손분석 갱신이 사진 id 기준 최신 여부를 WHERE 절에서 확인한다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 서버 호출로 재현(결정론적: 사진id 순서로 판정)")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round72_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A
    import photo_ai as PH

    def _jpeg_bytes(color=(30, 30, 200)):
        #  ⚠ 사진마다 내용을 다르게 한다 — 사건 안 중복 업로드는 sha256 로
        #    걸러진다(같은 내용이면 두 번째 사진이 그냥 조용히 스킵된다).
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (4, 4), color).save(buf, format="JPEG")
        return buf.getvalue()

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','중간관리자')")
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region) VALUES('R72-01','접수','가드레일','서울')"
    ).lastrowid
    conn.commit()
    conn.close()

    client = A.app.test_client()
    _tok = "regress-round72-csrf"
    with client.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    #  ⚠ 이 기기엔 BOKGUON_GEMINI_KEY 가 없어 analyze_damage() 가 즉시
    #    "미연동"(severity=None)만 돌려준다 — 성공 판정(ok=1)이 안 나와 고친
    #    분기 자체를 안 탄다. 실제로 값을 돌려주는 상황을 흉내낸다.
    _real_analyze = PH.analyze_damage

    def _fake_analyze(abs_path, mime):
        return "중대", "가짜 분석 결과(라운드72 회귀테스트)", "test-model"
    PH.analyze_damage = _fake_analyze
    try:
        r1 = client.post(
            f"/api/cases/{cid}/photos/damage",
            data={"photos": (io.BytesIO(_jpeg_bytes()), "first.jpg")},
            headers=_hdr, content_type="multipart/form-data")
    finally:
        PH.analyze_damage = _real_analyze

    body1 = r1.get_json() or {}
    chk(r1.status_code == 200 and body1.get("ai_severity") == "중대",
        "STEP 첫 업로드가 정상 분석·기록된다", body1)

    _c = DB.get_db()
    _row1 = _c.execute("SELECT ai_photo_id, ai_severity FROM cases WHERE id=?", (cid,)).fetchone()
    _c.close()
    _first_photo_id = _row1["ai_photo_id"]
    chk(_first_photo_id is not None, "STEP 첫 사진 id 가 ai_photo_id 로 기록됐다", dict(_row1))

    #  ── 시나리오 A: 실제로 더 늦게 올라온(더 큰 id) 사진의 분석 결과는
    #     정상적으로 최신값을 갱신해야 한다(고친 코드가 과잉차단하지 않는지) ──
    PH.analyze_damage = _fake_analyze
    try:
        r2 = client.post(
            f"/api/cases/{cid}/photos/damage",
            data={"photos": (io.BytesIO(_jpeg_bytes((200, 30, 30))), "second.jpg")},
            headers=_hdr, content_type="multipart/form-data")
    finally:
        PH.analyze_damage = _real_analyze

    _c = DB.get_db()
    _row2 = _c.execute("SELECT ai_photo_id FROM cases WHERE id=?", (cid,)).fetchone()
    _c.close()
    chk(_row2["ai_photo_id"] is not None and _row2["ai_photo_id"] > _first_photo_id,
        "★ 대조군 — 실제로 더 늦게 올라온 사진의 결과는 정상적으로 최신값을 갱신한다"
        "(과잉차단 아님)", dict(_row2))

    #  ── 시나리오 B(핵심): 실제 함수(_upload_damage_photos)를 통해서 재현한다.
    #     "그 사이 늦게 끝난 더 오래된 분석이 뒤늦게 도착"하는 상황은, 결과적으로
    #     "지금 막 들어온 사진(더 낮은 id)의 UPDATE 가 이미 기록된 더 높은
    #     ai_photo_id 를 덮어쓰려는" 것과 같은 모양이다 — 미리 더 높은
    #     ai_photo_id 를 심어(가상의 '이미 더 새 판정이 기록됨') 실제 업로드
    #     경로가 그걸 덮어쓰는지를 직접 관찰한다(SQL 을 테스트가 직접 실행하지
    #     않는다 — 반드시 앱 코드를 통과시켜야 회귀를 증명한다).
    _c = DB.get_db()
    _c.execute("UPDATE cases SET ai_photo_id=999999, ai_severity='중대', "
               "ai_report='[이미 기록된 더 새 판정]' WHERE id=?", (cid,))
    _c.commit(); _c.close()

    PH.analyze_damage = _fake_analyze
    try:
        r3 = client.post(
            f"/api/cases/{cid}/photos/damage",
            data={"photos": (io.BytesIO(_jpeg_bytes((30, 200, 30))), "third.jpg")},
            headers=_hdr, content_type="multipart/form-data")
    finally:
        PH.analyze_damage = _real_analyze
    chk(r3.status_code == 200, "STEP 세번째 업로드 자체는 정상 처리된다(사진은 저장됨)",
        r3.get_json())

    _c = DB.get_db()
    _row3 = _c.execute("SELECT ai_photo_id, ai_severity, ai_report FROM cases WHERE id=?",
                        (cid,)).fetchone()
    _c.close()
    chk(_row3["ai_photo_id"] == 999999 and _row3["ai_report"] == "[이미 기록된 더 새 판정]",
        "★★★ 실제로 더 낮은 id(방금 올린) 사진의 분석은 이미 기록된 더 새 판정을"
        " 덮어쓰지 못한다 — 고치기 전엔 이 UPDATE 가 조건 없이 항상 성공해"
        " 최신 판정이 옛 판정으로 조용히 되돌아갔다", dict(_row3))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드72 실측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
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
