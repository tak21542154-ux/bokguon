# -*- coding: utf-8 -*-
"""스캔 70라운드 회귀 — api_contact_import(연락처 일괄등록) 트랜잭션 무제한 보유 +
   예외경로 rollback/close 누락, partners.biz_no·name 인덱스 부재.

  ① api_contact_import 가 업로드된 엑셀 파일 전체를 처리하는 동안 BEGIN IMMEDIATE
     를 행 단위 커밋 없이 그대로 쥐고 있었다 — 상한이 없어서, 큰 파일(또는 실수로
     올린 대용량 파일)이면 그동안 입찰·수배확정·정산승인 등 다른 모든 쓰기가
     BUSY_TIMEOUT_MS(8초)만큼 기다리다 실패한다. 형제 기능
     (api_partner_bulk_credentials)은 이미 300건 상한이 있었는데 여기만 없었다.
  ② 같은 함수의 예외 경로가 conn.rollback()·close() 를 한 번도 명시적으로
     부르지 않았다 — 쓰기 잠금 해제를 가비지컬렉션 타이밍에 맡긴 셈이다(고치기
     전엔 실패해도 close() 가 안 불림 — 이 라운드의 실측 방식).
  ③ partners.biz_no·name 에 인덱스가 없어 일괄등록 행마다 partners 전체를 훑었다.

      python test_scan_round70_fixes.py
"""
import contextlib
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
DB_SRC = read("db.py")

print("═" * 72)
print("  스캔 70라운드 회귀 — 연락처 일괄등록 트랜잭션 무제한보유·예외정리 누락·인덱스부재")
print("═" * 72)


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
ci_body = _body(APP_SRC, "api_contact_import")
chk("MAX_IMPORT_ROWS = 2000" in ci_body,
    "★★ ① api_contact_import 에 행 수 상한(2000)이 생겼다"
    "(형제 api_partner_bulk_credentials 의 300건 상한과 같은 원칙)")
chk("한 번에 최대" in ci_body and "행까지 처리할 수 있습니다" in ci_body,
    "STEP 상한 초과 시 안내 문구가 있다")
chk("conn.rollback()" in ci_body and "raise" in ci_body,
    "★★★ ② 트랜잭션 중 예외가 나면 명시적으로 rollback 한다")
chk("finally:" in ci_body and "conn.close()" in ci_body,
    "★★ ② finally 에서 conn.close() 를 명시적으로 부른다"
    "(고치기 전엔 가비지컬렉션에 맡겼다)")

chk('"CREATE INDEX IF NOT EXISTS idx_partner_bizno ON partners(biz_no)"' in DB_SRC,
    "★ ③ partners.biz_no 인덱스가 생겼다")
chk('"CREATE INDEX IF NOT EXISTS idx_partner_name ON partners(name)"' in DB_SRC,
    "★ ③ partners.name 인덱스가 생겼다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 서버 호출로 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round70_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import sqlite3 as _sqlite3
    import db as DB
    DB.init_db()
    import app as A
    from openpyxl import Workbook

    # ── ③ 인덱스가 실제로 만들어졌는지 DB 에서 직접 확인 ──
    _c = DB.get_db()
    _idx_names = {r["name"] for r in _c.execute("PRAGMA index_list('partners')")}
    _c.close()
    chk("idx_partner_bizno" in _idx_names and "idx_partner_name" in _idx_names,
        "★ ③ 새 DB 에 실제로 인덱스가 만들어진다(PRAGMA index_list)", _idx_names)

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','최고관리자')")
    pid = conn.execute(
        "INSERT INTO partners(name, biz_no, email) VALUES('라운드70검증업체','111-11-11111','old@x.com')"
    ).lastrowid
    conn.commit(); conn.close()

    client = A.app.test_client()
    _tok = "regress-round70-csrf-token"
    with client.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    def _xlsx_bytes(rows):
        wb = Workbook()
        ws = wb.active
        ws.append(["업체명", "사업자번호", "이메일"])
        for r in rows:
            ws.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    # ── ① 상한 초과 — 실제 데이터는 마지막 한 줄뿐인 희소 파일로도 max_row 로 걸린다 ──
    def _sparse_over_cap_bytes():
        wb = Workbook()
        ws = wb.active
        ws.append(["업체명", "사업자번호", "이메일"])
        ws.cell(row=2003, column=1, value="넘치는행")
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    r1 = client.post("/api/contacts/import",
                      data={"file": (io.BytesIO(_sparse_over_cap_bytes()), "big.xlsx")},
                      headers=_hdr, content_type="multipart/form-data")
    body1 = r1.get_json() or {}
    chk(r1.status_code == 400 and not body1.get("ok") and "updated" not in body1,
        "★★★ ① 2000행 초과 파일은 처리 자체를 시작하지 않고 400 을 받는다"
        "(고치기 전엔 상한이 없어 파일 전체를 트랜잭션 하나로 처리했다)",
        f"status={r1.status_code} body={body1}")

    # ── ② 트랜잭션 도중 실패 → 명시적 rollback/close 확인 + 앞서 성공한 UPDATE 도 되돌아감 ──
    #  ⚠ 요청 하나가 DB.get_db() 를 여러 번 부른다(예: require_admin 안의
    #    _account_alive() 가 별도 연결로 계정 상태를 본다) — 트리거가 실제로
    #    발동한 그 연결만 골라서 확인한다(연결 개수 자체를 가정하지 않는다).
    class _TrackingFailProxy:
        def __init__(self, real, trigger):
            self._real, self._trig = real, trigger
            self.rollback_called = False
            self.close_called = False
            self.fired = False

        def execute(self, sql, *a, **kw):
            if self._trig in sql:
                self.fired = True
                raise _sqlite3.OperationalError("의도적 주입 실패(라운드70 회귀테스트)")
            return self._real.execute(sql, *a, **kw)

        def rollback(self):
            self.rollback_called = True
            return self._real.rollback()

        def close(self):
            self.close_called = True
            return self._real.close()

        def __getattr__(self, name):
            return getattr(self._real, name)

    _real_get_db = A.DB.get_db
    _proxies = []

    def _patched_get_db():
        #  ⚠ sets 순서상 "contact_updated=?" 는 항상 뒤에 붙는다
        #    ("UPDATE partners SET email=?,contact_updated=? WHERE id=?" 처럼) —
        #    "SET" 바로 뒤로 트리거를 잡지 않는다.
        p = _TrackingFailProxy(_real_get_db(), "UPDATE partners SET")
        _proxies.append(p)
        return p
    A.DB.get_db = _patched_get_db
    try:
        # 첫 행은 실제 UPDATE 성공(트리거는 매 UPDATE 마다 문자열로 걸리므로,
        # 이 업체 자체가 첫 행이자 유일 행이면 그 UPDATE 에서 바로 실패한다 —
        # 롤백이 "이 UPDATE 자체를 되돌리는지"를 확인하는 가장 단순한 형태다).
        r2 = client.post(
            "/api/contacts/import",
            data={"file": (io.BytesIO(_xlsx_bytes([["라운드70검증업체", "111-11-11111", "new@x.com"]])),
                            "small.xlsx")},
            headers=_hdr, content_type="multipart/form-data")
    finally:
        A.DB.get_db = _real_get_db

    body2 = r2.get_json() or {}
    chk(r2.status_code == 400 and not body2.get("ok"),
        "★★ ② 트랜잭션 도중 실패해도 사람이 읽는 400 응답을 받는다(원본 예외가 그대로 안 샌다)",
        f"status={r2.status_code} body={body2}")
    _fired = [p for p in _proxies if p.fired]
    chk(len(_fired) == 1,
        "STEP 주입한 실패가 실제로 정확히 한 연결에서 발동했다", len(_fired))
    chk(bool(_fired) and _fired[0].close_called,
        "★★★ ② 실패 뒤 conn.close() 가 실제로(명시적으로) 호출됐다"
        "(고치기 전엔 이 경로에서 close() 가 한 번도 안 불렸다)",
        [p.close_called for p in _fired])
    chk(bool(_fired) and _fired[0].rollback_called,
        "★★★ ② 실패 뒤 conn.rollback() 이 실제로 호출됐다", [p.rollback_called for p in _fired])

    _c = DB.get_db()
    _email_after = _c.execute("SELECT email FROM partners WHERE id=?", (pid,)).fetchone()["email"]
    _c.close()
    chk(_email_after == "old@x.com",
        "★★ ② 실패한 트랜잭션의 UPDATE 가 실제로 롤백되어 이메일이 그대로다"
        "(new@x.com 으로 바뀌었다면 부분 커밋된 것)", _email_after)

    # ── 정상 경로 — restructuring 이 평상시 동작을 깨지 않았는지 ──
    r3 = client.post(
        "/api/contacts/import",
        data={"file": (io.BytesIO(_xlsx_bytes([["라운드70검증업체", "111-11-11111", "final@x.com"]])),
                        "ok.xlsx")},
        headers=_hdr, content_type="multipart/form-data")
    body3 = r3.get_json() or {}
    chk(r3.status_code == 200 and body3.get("ok") and body3.get("updated") == 1,
        "★★ 정상 경로는 여전히 정상 작동한다(1건 갱신)", body3)
    _c = DB.get_db()
    _email_final = _c.execute("SELECT email FROM partners WHERE id=?", (pid,)).fetchone()["email"]
    _c.close()
    chk(_email_final == "final@x.com", "★ 정상 경로에서 이메일이 실제로 갱신됐다", _email_final)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드70 실측 준비/실행", f"{type(e).__name__} {e}")
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
