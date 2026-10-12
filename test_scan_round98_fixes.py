# -*- coding: utf-8 -*-
"""스캔 98라운드 회귀 — 연락처 일괄등록이 형식오류 행을 아무 카운터에도 안 잡았다(97라운드 후속).

  api_contact_import 의 행별 루프에서, 그 행의 유일한 채운 칸이 형식오류(예:
  이메일)면 sets 가 끝까지 비어 "채울 게 없음" 분기(if not sets: continue)로
  빠졌다 — upd·skip_dup·skip_none 어느 카운터에도 안 잡히고, errs 에 이미
  쌓인 메시지도 응답의 errors[:10] 절단에 걸리면 완전히 사라진다. 결과적으로
  "ok:true" 응답의 어떤 숫자를 더해도 실제 업로드한 행 수가 안 나오고,
  10건을 넘는 오류는 흔적도 없이 사라졌다(형제 기능 api_partner_bulk_credentials
  는 목록을 안 자른다).

      python test_scan_round98_fixes.py
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
print("  스캔 98라운드 회귀 — 연락처 일괄등록 형식오류 행 누락 집계")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스: 형식오류로 빈 행과 '채울 게 없는' 행을 구분해서 센다")
# ──────────────────────────────────────────────────────────────
ci_body = _py_fn_body(APP_SRC, "api_contact_import")
chk("skip_invalid" in ci_body,
    "★★★ 형식오류로 통째로 빠진 행을 세는 별도 카운터(skip_invalid)가 있다")
chk("if len(errs) > _errs_before:" in ci_body,
    "★★ '이 행에서 errs 가 실제로 늘었는가'로 형식오류와 단순 무입력을 구분한다")
chk('"error_count": len(errs)' in ci_body,
    "★★★ 응답에 잘리지 않은 실제 총 오류 건수(error_count)가 포함된다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행: 이메일 형식 오류만 있는 행이 skipped_invalid 로 잡히고, 오류가 전부 보인다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round98_")
_dbpath = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_DB_PATH"] = _dbpath
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
                 "VALUES('admin','x','검증','중간관리자')")
    N_BAD = 12  # errors[:10] 절단을 실제로 넘기는 개수
    for i in range(N_BAD):
        conn.execute(
            "INSERT INTO partners(name,partner_type,status) VALUES(?,'시행사','활성')",
            (f"R98업체{i}",))
    conn.commit()

    wb = Workbook()
    ws = wb.active
    ws.append(["업체명", "이메일"])
    for i in range(N_BAD):
        # 유일하게 채운 칸(이메일)이 형식오류 — 다른 칸은 전부 빈칸.
        ws.append([f"R98업체{i}", "이건이메일이아님"])
    xbuf = io.BytesIO()
    wb.save(xbuf)
    xbuf.seek(0)

    admin = A.app.test_client()
    _tok = "r98-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    r = admin.post("/api/contacts/import", headers=_hdr,
                    data={"file": (xbuf, "test.xlsx")},
                    content_type="multipart/form-data")
    j = r.get_json()
    chk(r.status_code == 200 and j.get("ok"), "STEP 요청 자체는 200 ok:true 로 끝난다", j)
    chk(j.get("skipped_invalid") == N_BAD,
        f"★★★ 형식오류만 있던 {N_BAD}개 행이 전부 skipped_invalid 로 잡힌다"
        "(예전엔 updated·skipped_duplicate·not_found 어디에도 안 잡혔다)",
        j.get("skipped_invalid"))
    chk(j.get("updated") == 0 and j.get("skipped_duplicate") == 0 and j.get("not_found") == 0,
        "STEP 다른 카운터는 그대로 0이다(엉뚱한 곳에 잘못 잡히지 않음)",
        (j.get("updated"), j.get("skipped_duplicate"), j.get("not_found")))
    chk(j.get("error_count") == N_BAD,
        f"★★★ error_count 가 절단 전 실제 총 오류 수({N_BAD})를 그대로 알려준다"
        "(예전엔 이 필드 자체가 없어 10건 넘는 오류는 흔적도 없이 사라졌다)",
        j.get("error_count"))
    chk(len(j.get("errors") or []) == 10,
        "STEP 화면 표시용 목록(errors)은 여전히 10건으로 잘려 있다(그 사실 자체는 error_count 로 알 수 있음)",
        len(j.get("errors") or []))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드98 서버측 준비/실행", f"{type(e).__name__} {e}")
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
