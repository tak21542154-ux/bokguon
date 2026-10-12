# -*- coding: utf-8 -*-
"""스캔 118라운드 회귀 — 하자(defect) 자유텍스트 3곳 + 관리자 메모 2곳에
   길이 상한이 없었다.

  이 파일 안의 사유·메모류 자유텍스트는 전부 [:300]~[:1000] 으로 자르는
  관례가 있다(예: 협력사 이의제기 reason[:1000], 도입문의 memo[:500]).
  그런데 하자 접수(title·content), 협력사 재시공완료 보고(resolution),
  관리자 하자수정(resolution), 도입문의·입점신청 관리자 메모(note) 만
  이 관례를 빠뜨려 무제한 문자열이 그대로 저장됐다(실측: 100만~200만자
  문자열이 200 OK 로 저장 확인 — DB 비대화 + 여러 포털 렌더링 지연 위험).

      python test_scan_round118_fixes.py
"""
import io
import os
import shutil
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
print("  스캔 118라운드 회귀 — 하자·관리자메모 자유텍스트 길이상한 누락 5곳")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
#  ⚠⚠ [라운드604] 세 지점 모두 raw (d.get(...) or "")[:N] 이 형제결함군(round601~603과
#    같은 부류 — 비문자열 입력 시 AttributeError/TypeError)이라 _s(d.get(...), N) 으로
#    바뀌었다 — 이 round118 검사가 지키려는 "저장 전에 N자로 자른다"는 계약 자체는
#    100% 그대로 보존됐고(_s() 도 마지막에 [:n] 슬라이스, 아래 [2] 실행검사가 실측
#    재확인), 검사 문자열만 새 코드에 맞게 갱신한다(약화 아님 — round604 자신의
#    test_scan_round604_fixes.py 가 이 갱신과 정확히 같은 소스 문자열로 12곳 전부의
#    비문자열 안전성까지 별도로 검증한다).
dc_body = _py_fn_body(APP_SRC, "api_defect_create")
chk('_title = _s(d.get("title"), 100)' in dc_body and '_s(d.get("content"), 1000)' in dc_body,
    "★★★ api_defect_create 가 title·content 를 저장 전에 자른다")

dr_body = _py_fn_body(APP_SRC, "api_partner_defect_resolve")
chk('_s(d.get("resolution"), 1000)' in dr_body,
    "★★★ api_partner_defect_resolve 가 resolution 을 자른다")

du_body = _py_fn_body(APP_SRC, "api_defect_update")
chk('v = _s(d[f], 1000) if f == "resolution" else d[f]' in du_body,
    "★★★ api_defect_update 가 resolution 을 자른다(형제인 severity·due_date·"
    "cost_bearer 는 이미 검증되는 같은 루프)")

lu_body = _py_fn_body(APP_SRC, "api_lead_update")
chk('_s(d["note"], 500)' in lu_body,
    "★★ api_lead_update 가 관리자 메모(note)를 자른다"
    "([라운드616] raw (d[\"note\"] or \"\").strip()[:500] → _s(d[\"note\"], 500)"
    " — round423이 남긴 strip()은 여전히 그대로(문자열 입력의 동작 불변), "
    "비문자열 JSON(숫자 등)도 이제 AttributeError 없이 안전하게 문자열화된다)")

au_body = _py_fn_body(APP_SRC, "api_application_update")
chk('_s(d["note"], 500)' in au_body,
    "★★ api_application_update 가 관리자 메모(note)를 자른다"
    "([라운드616] 형제 api_lead_update 와 같은 이유로 _s(d[\"note\"], 500)로 통일)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제로 긴 문자열을 보내 저장된 길이를 확인한다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round118_")
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
                 "VALUES('r118admin','x','검증','중간관리자')")
    iid = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('R118보험','활성')").lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R118업체','시행사','활성')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,insurer,"
        "                  partner_id,partner_name,is_demo) "
        "VALUES('R118-C1','시공중','가드레일','서울',?,'R118보험',?,'R118업체',0)",
        (iid, pid)).lastrowid
    lead_id = conn.execute(
        "INSERT INTO insurer_leads(company,status) VALUES('R118리드','신규')").lastrowid
    app_id = conn.execute(
        "INSERT INTO partner_applications(company,status) VALUES('R118신청','신규')").lastrowid
    conn.commit()

    admin = A.app.test_client()
    _atok = "r118-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r118admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _atok
    _ahdr = {"X-CSRF-Token": _atok}

    insurer = A.app.test_client()
    _itok = "r118-insurer-csrf"
    with insurer.session_transaction() as sess:
        sess["insurer_id"] = iid; sess["insurer_name"] = "R118보험"
        sess["_csrf"] = _itok
    _ihdr = {"X-CSRF-Token": _itok}

    partner = A.app.test_client()
    _ptok = "r118-partner-csrf"
    with partner.session_transaction() as sess:
        sess["partner_id"] = pid
        sess["_csrf"] = _ptok
    _phdr = {"X-CSRF-Token": _ptok}

    LONG_TITLE = "가" * 500
    LONG_CONTENT = "나" * 2_000_000
    r1 = insurer.post("/api/defects", headers=_ihdr,
                       json={"case_id": cid, "title": LONG_TITLE, "content": LONG_CONTENT})
    j1 = r1.get_json() or {}
    chk(r1.status_code == 200 and j1.get("ok"),
        "STEP 하자 접수 자체는 정상 처리된다(과잉차단 아님)",
        (r1.status_code, j1))
    did = j1.get("id")
    d_row = conn.execute(
        "SELECT length(title) tl, length(content) cl FROM defects WHERE id=?", (did,)).fetchone()
    chk(bool(did) and d_row["tl"] == 100,
        "★★★ 하자 title 이 100자로 잘려 저장된다(예전엔 500자 그대로 저장됨)",
        dict(d_row) if d_row else None)
    chk(bool(did) and d_row["cl"] == 1000,
        "★★★ 하자 content 가 1000자로 잘려 저장된다(예전엔 200만자 그대로 저장됨)",
        dict(d_row) if d_row else None)

    LONG_RESOLUTION = "다" * 1_500_000
    r2 = partner.post(f"/api/partner/defects/{did}/resolve", headers=_phdr,
                       json={"resolution": LONG_RESOLUTION})
    j2 = r2.get_json() or {}
    chk(r2.status_code == 200 and j2.get("ok"),
        "STEP 협력사 재시공완료 보고 자체는 정상 처리된다(과잉차단 아님)",
        (r2.status_code, j2))
    rl = conn.execute("SELECT length(resolution) rl FROM defects WHERE id=?", (did,)).fetchone()
    chk(rl["rl"] == 1000,
        "★★★ 협력사 resolution 이 1000자로 잘려 저장된다(예전엔 150만자 그대로 저장됨)",
        dict(rl))

    LONG_RESOLUTION2 = "라" * 1_500_000
    r3 = admin.patch(f"/api/defects/{did}", headers=_ahdr, json={"resolution": LONG_RESOLUTION2})
    j3 = r3.get_json() or {}
    chk(r3.status_code == 200 and j3.get("ok") is not False,
        "STEP 관리자 하자수정(resolution) 자체는 정상 처리된다(과잉차단 아님)",
        (r3.status_code, j3))
    rl2 = conn.execute("SELECT length(resolution) rl FROM defects WHERE id=?", (did,)).fetchone()
    chk(rl2["rl"] == 1000,
        "★★★ 관리자가 고친 resolution 도 1000자로 잘려 저장된다"
        "(형제인 severity·due_date·cost_bearer 는 이미 검증되던 같은 루프에서 resolution 만 빠졌었다)",
        dict(rl2))

    LONG_NOTE = "마" * 100_000
    r4 = admin.patch(f"/api/leads/{lead_id}", headers=_ahdr, json={"note": LONG_NOTE})
    chk(r4.status_code == 200 and (r4.get_json() or {}).get("ok"),
        "STEP 도입문의 관리자메모 저장 자체는 정상 처리된다(과잉차단 아님)",
        (r4.status_code, r4.get_json()))
    ln = conn.execute(
        "SELECT length(note) nl FROM insurer_leads WHERE id=?", (lead_id,)).fetchone()
    chk(ln["nl"] == 500,
        "★★ 도입문의 관리자메모(note)가 500자로 잘려 저장된다(예전엔 10만자 그대로 저장됨)",
        dict(ln))

    r5 = admin.patch(f"/api/applications/{app_id}", headers=_ahdr, json={"note": LONG_NOTE})
    chk(r5.status_code == 200 and (r5.get_json() or {}).get("ok"),
        "STEP 입점신청 관리자메모 저장 자체는 정상 처리된다(과잉차단 아님)",
        (r5.status_code, r5.get_json()))
    an = conn.execute(
        "SELECT length(note) nl FROM partner_applications WHERE id=?", (app_id,)).fetchone()
    chk(an["nl"] == 500,
        "★★ 입점신청 관리자메모(note)가 500자로 잘려 저장된다(예전엔 10만자 그대로 저장됨)",
        dict(an))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드118 서버측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
