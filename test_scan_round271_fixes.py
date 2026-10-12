# -*- coding: utf-8 -*-
"""스캔 271라운드 회귀 — 수집이메일 정리(clean_collected_emails.py) 결함 3건
   (collect_emails.py 감사 라운드267의 직접적 후속 companion, 이 세션에서
   사상 첫 주조사 — 정밀조사 Agent가 발견, 독립 재검증 후 수정).

  [1] UPDATE가 예외처리 밖에 있고 commit은 루프 전체가 끝난 뒤 단 한 번뿐
      이었다 — 저장 하나가 실패하면(락 경합 등) 이미 화면에 "삭제"로 찍힌
      나머지 행까지 전부 저장되지 않았다(실측: 재조회하면 아무것도 안
      지워져 있었다). 형제(geocode_fill.py·seed_boq_led.py, 라운드265·268)
      처럼 행마다 즉시 커밋하고 실패한 행만 건너뛰도록 수정.

  [2] 되돌릴 수 없는 삭제인데(기본 실행이 곧 실행) 대상 DB 경로 표시·완료
      감사로그가 없었다 — 형제 배치도구(geocode_fill.py·seed_boq.py 등)는
      전부 DB.log()로 남기는데 이 파일만 빠져 있었다. 표시·로그를 추가.

  [3] 지운 이메일 원문 대신 정적 문구("[자동수집 부적합 주소 제거]")만
      남겨, 오탐이 나도 무엇을 지웠는지 DB 백업 없인 알 수 없었다. 게다가
      같은 정크 주소가 재수집→재정리를 반복하면 이 정적 문구가 무한히
      중복 누적됐다(실측). 지운 원문을 메모에 남기고, 이미 있는 마커는
      다시 안 붙이도록 수정.

      python test_scan_round271_fixes.py
"""
import io
import os
import secrets
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []

#  ⚠ db.py 를 불러오기 전에 검증용 DB 경로부터 정한다.
_tmpdir = tempfile.mkdtemp(prefix="round271_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


SRC = read("clean_collected_emails.py")

print("=" * 72)
print("  스캔 271라운드 회귀 — clean_collected_emails.py 배치전멸·안전장치 부재")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_main = SRC.index("def main():")
main_body = SRC[i_main:]
chk("try:" in main_body and "except Exception as ex:" in main_body and "conn.commit()" in main_body,
    "★★★★★ 행마다 즉시 커밋 + 실패 시 건너뛰는 구조가 생겼다"
    "(고치기 전엔 루프 끝에서 단 한 번만 커밋했다)")
chk('DB.DB_PATH' in main_body,
    "★★★★ 대상 DB 경로를 화면에 표시한다(형제 manage.py show_db_target() 관용구)")
chk("DB.log(conn," in main_body,
    "★★★★ 완료 시 감사로그를 남긴다(형제 배치도구들과 통일)")
chk("marker not in note" in main_body and 'f"[자동수집 부적합 주소 제거: {old_email}]"' in main_body,
    "★★★★★ 지운 이메일 원문을 메모에 남기고, 중복 마커는 다시 안 붙인다")

# ============================================================
print("\n[2] 실행 준비")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
try:
    import importlib
    import db as DB
    DB.init_db()
    import clean_collected_emails as CCE
    importlib.reload(CCE)

    def _mk_junk_partner(name, email, note=""):
        conn = DB.get_db()
        pid = conn.execute(
            "INSERT INTO partners(name,partner_type,major,category,region,email,email_source,"
            "                     email_consent,contact_note,status,created_at) "
            "VALUES(?,'시행사','금속ㆍ창호','금속ㆍ창호ㆍ지붕ㆍ건축물조립공사업','서울',?,"
            "       '수집(홈페이지)',0,?,'활성',?)",
            (name, email, note, DB.now())).lastrowid
        conn.commit()
        conn.close()
        return pid

    class _FlakyConn:
        def __init__(self, real, fail_on_substr, fail_count=1):
            self._real = real
            self._fail_on = fail_on_substr
            self._fail_count = fail_count
            self._fired = 0

        def execute(self, sql, *a, **kw):
            if self._fail_on in sql and self._fired < self._fail_count:
                self._fired += 1
                raise sqlite3.OperationalError("SIMULATED-DB-FAIL-R271")
            return self._real.execute(sql, *a, **kw)

        def __getattr__(self, name):
            return getattr(self._real, name)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드271 [2] 준비", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — 저장 1건 실패해도 이미 처리한 나머지가 살아남는가")
# ------------------------------------------------------------
try:
    mark = "R271A-" + secrets.token_hex(3)
    p1 = _mk_junk_partner(f"{mark}-1", "info@mysite.com")     # BAD_DOMAIN
    p2 = _mk_junk_partner(f"{mark}-2", "noreply@real-domain.co.kr")  # BAD_LOCAL
    p3 = _mk_junk_partner(f"{mark}-3", "ad@daangn.com")       # BAD_DOMAIN

    _orig_get_db = DB.get_db
    DB.get_db = lambda: _FlakyConn(_orig_get_db(), "UPDATE partners SET email=''", fail_count=1)
    real_argv = sys.argv
    sys.argv = ["clean_collected_emails.py"]
    crashed = False
    try:
        CCE.main()
    except Exception:
        crashed = True
    finally:
        sys.argv = real_argv
        DB.get_db = _orig_get_db

    chk(not crashed,
        "★★★★★ 저장 1건이 실패해도 스크립트 전체가 죽지 않는다"
        "(고치기 전엔 여기서 그대로 죽어 이미 처리한 행까지 전부 유실됐다)")

    conn = DB.get_db()
    rows = {r["id"]: r["email"] for r in conn.execute(
        "SELECT id, email FROM partners WHERE id IN (?,?,?)", (p1, p2, p3))}
    conn.close()
    cleared = sum(1 for v in rows.values() if v == "")
    chk(cleared >= 2,
        "★★★★★ 저장이 실패한 1건을 제외한 나머지는 실제로 DB에도 지워져 있다"
        "(고치기 전엔 단일커밋 구조상 이마저 0건으로 날아갔을 것)",
        rows)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드271 [3] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[4] 실행 — DB경로 표시·감사로그, 그리고 삭제 원문 기록+중복방지")
# ------------------------------------------------------------
try:
    mark2 = "R271B-" + secrets.token_hex(3)
    junk_email = "info@mysite.com"
    pid = _mk_junk_partner(f"{mark2}-대상", junk_email, note="기존 통화메모")

    conn = DB.get_db()
    before_log = conn.execute("SELECT COUNT(*) n FROM activity_log").fetchone()["n"]
    conn.close()

    _out = io.StringIO()
    import contextlib
    real_argv = sys.argv
    sys.argv = ["clean_collected_emails.py"]
    try:
        with contextlib.redirect_stdout(_out):
            CCE.main()
    finally:
        sys.argv = real_argv
    printed = _out.getvalue()

    chk("대상 DB:" in printed and os.environ["BOKGUON_DB_PATH"] in printed,
        "★★★★ 실행 화면에 실제 대상 DB 경로가 정확히 찍힌다")

    conn = DB.get_db()
    after_log = conn.execute("SELECT COUNT(*) n FROM activity_log").fetchone()["n"]
    row = conn.execute("SELECT email, contact_note FROM partners WHERE id=?", (pid,)).fetchone()
    conn.close()
    chk(after_log > before_log, "★★★★ 완료 후 감사로그(activity_log)가 실제로 늘었다")
    chk(row["email"] == "", "STEP 정크 이메일이 실제로 비워졌다")
    chk("기존 통화메모" in row["contact_note"] and junk_email in row["contact_note"],
        "★★★★★ 사람이 남긴 기존 메모는 보존되고, 지운 이메일 원문이 함께 남는다"
        "(고치기 전엔 원문 없이 정적 문구만 붙었다)", row["contact_note"])

    #  같은 정크 주소가 재수집→재정리를 반복해도 마커가 중복되지 않는가.
    conn = DB.get_db()
    conn.execute(
        "UPDATE partners SET email=?, email_source='수집(홈페이지)', email_consent=0 WHERE id=?",
        (junk_email, pid))
    conn.commit()
    conn.close()
    sys.argv = ["clean_collected_emails.py"]
    try:
        CCE.main()
    finally:
        sys.argv = real_argv
    conn = DB.get_db()
    row2 = conn.execute("SELECT contact_note FROM partners WHERE id=?", (pid,)).fetchone()
    conn.close()
    chk(row2["contact_note"].count(junk_email) == 1,
        "★★★★★ 같은 주소를 두 번째 정리해도 마커가 중복되지 않는다"
        "(고치기 전엔 정적 문구가 매 회차 무한히 누적됐다)", row2["contact_note"])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드271 [4] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
