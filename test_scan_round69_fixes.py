# -*- coding: utf-8 -*-
"""스캔 69라운드 회귀 — repair_estimate.py 잘못된 자재SKU(LED 보안등) +
   manage.py cmd_go_live 커밋 전 파일삭제(트랜잭션 무보호).

  ① repair_estimate.py 'led_security_light' 레시피가 led_fixture150 을 썼다 —
     이건 seed_boq_led.py 61행 "LED 가로등기구 자재"·"150W 일체형·일반형"이다.
     설치비 SKU(led_sec_ins_*)는 이미 "50W 이하"로 정확히 보안등인데 자재만
     카테고리가 틀렸다. 옆 레시피 barrier_bar 와 같은 처방 — complete=False 로
     내려 자동확정에서 빼고 실측으로 보낸다(지어낸 값을 쓰지 않는다는 이 모듈
     자신의 원칙, docstring 18~21행).
  ② manage.py cmd_go_live 가 BEGIN IMMEDIATE~commit 사이를 try/except 로
     보호하지 않았고, 사진 파일을 그 트랜잭션 도중(커밋 전) os.remove() 로
     즉시 지웠다 — 그 뒤 ~150줄의 DELETE 중 하나라도 실패해 롤백되면 DB 행은
     되살아나는데 파일은 이미 사라져 "행은 있는데 파일이 없는" 상태가 된다.
     고아정리 명령(cmd_prune_orphans)은 이미 이 문제를 겪고 고쳤다(커밋 뒤에만
     이동 + 휴지통행, 삭제 아님). go-live 도 같은 원칙으로 맞춘다.

      python test_scan_round69_fixes.py
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


RE_SRC = read("repair_estimate.py")
MNG_SRC = read("manage.py")

print("═" * 72)
print("  스캔 69라운드 회귀 — LED보안등 자재SKU 오류 + go-live 커밋전 파일삭제")
print("═" * 72)


def _dict_entry(src, key, next_key):
    start = src.index(f'"{key}": {{')
    end = src.index(f'"{next_key}": {{', start)
    return src[start:end]


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수/레시피 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
led_recipe = _dict_entry(RE_SRC, "led_security_light", "brick_wall")
chk('"complete": False' in led_recipe,
    "★★ ① led_security_light 레시피가 complete=False (자동확정에서 빠짐)")
chk('"led_fixture150"' in led_recipe,
    "STEP 자재 SKU 는 그대로 있다(가격을 지어내지 않고 실측으로 보냄)")

chk('ENGINE_VER = "2026.08-2"' in RE_SRC,
    "★ ① ENGINE_VER 가 레시피 변경에 맞춰 올라갔다(모듈 자신의 원칙, 56행)")

golive_body = _body(MNG_SRC, "cmd_go_live")
chk("except sqlite3.Error as e:" in golive_body and "conn.rollback()" in golive_body,
    "★★★ ② cmd_go_live 트랜잭션 전체가 try/except/rollback 으로 보호된다")
chk("finally:" in golive_body and golive_body.count("conn.close()") >= 1,
    "★★ ② finally 에서 conn.close() 한다")
chk("shutil.move(_src, _dst)" in golive_body,
    "★★★ ② 사진을 지우지 않고 휴지통(_trash)으로 옮긴다(cmd_prune_orphans 와 동일 원칙)")
chk("os.remove(photo_ai.abs_path" not in golive_body,
    "★★ ② 커밋 전 즉시 os.remove() 하던 옛 코드가 없다")
chk(golive_body.find("conn.commit()") >= 0
    and golive_body.find("shutil.move(_src, _dst)") >= 0
    and golive_body.find("conn.commit()") < golive_body.find("shutil.move(_src, _dst)"),
    "★★★ ② 파일 이동 코드가 commit 보다 뒤에 있다(순서 보장)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — ① 실제 엔진 호출로 게이트 확인")
# ──────────────────────────────────────────────────────────────
sys.path.insert(0, HERE)
import repair_estimate as RE  # noqa: E402

res = RE.estimate("led_security_light", {"n": 1, "mount": "등주"})
chk(res["gate"] == "실측필요",
    "★★★ ① led_security_light 견적이 이제 실측필요로 게이트된다"
    "(고치기 전엔 원격확정가능이라 아무도 현장을 안 보고 자재비 오류가 그대로 확정됐다)",
    res)

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — ② cmd_go_live 실패주입(롤백 시 파일 보존) + 정상경로(휴지통 이동)")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round69_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
os.environ.setdefault("BOKGUON_BACKUP_DIR", os.path.join(_tmpdir, "backups"))

try:
    import db as DB
    DB.init_db()
    import manage as M
    import sqlite3 as _sqlite3

    os.makedirs(os.environ["BOKGUON_UPLOAD_DIR"], exist_ok=True)
    _rel = "2026/08/round69-test.jpg"
    _abs = os.path.join(os.environ["BOKGUON_UPLOAD_DIR"], *_rel.split("/"))
    os.makedirs(os.path.dirname(_abs), exist_ok=True)
    with open(_abs, "wb") as f:
        f.write(b"fake-jpeg-bytes-round69")

    conn = DB.get_db()
    cid = conn.execute(
        "INSERT INTO cases(case_no, is_demo, status) VALUES('R69-DEMO-01', 1, '완료')"
    ).lastrowid
    conn.execute(
        "INSERT INTO photos(case_id, rel_path) VALUES(?, ?)", (cid, _rel))
    conn.commit(); conn.close()

    def _run_golive():
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = M.cmd_go_live(["--yes"])
        return rc, buf.getvalue()

    # ── 실패주입: 트랜잭션 후반부(로그인시도 정리)에서 sqlite3 오류를 강제한다 ──
    class _FailProxy:
        def __init__(self, real, trigger):
            self._real, self._trig = real, trigger

        def execute(self, sql, *a, **kw):
            if self._trig in sql:
                raise _sqlite3.OperationalError("의도적 주입 실패(라운드69 회귀테스트)")
            return self._real.execute(sql, *a, **kw)

        def __getattr__(self, name):
            return getattr(self._real, name)

    _real_get_db = M.DB.get_db

    def _patched_get_db():
        return _FailProxy(_real_get_db(), "DELETE FROM login_attempts")
    M.DB.get_db = _patched_get_db
    try:
        rc1, out1 = _run_golive()
    finally:
        M.DB.get_db = _real_get_db

    chk(rc1 == 1, "★★★ ② 트랜잭션 후반부 실패 시 cmd_go_live 가 예외 없이 1을 반환한다"
        "(고치기 전엔 이 실패가 함수 밖까지 그대로 터졌다)", f"rc={rc1}")

    _c = DB.get_db()
    _row = _c.execute("SELECT 1 FROM cases WHERE id=?", (cid,)).fetchone()
    _c.close()
    chk(_row is not None,
        "★★★ ② 실패 뒤 롤백돼 데모 사건 행이 그대로 남아 있다(DB 는 안전)", _row)
    chk(os.path.isfile(_abs),
        "★★★ ② 실패 뒤에도 사진 파일이 원래 자리에 그대로 남아 있다"
        "(고치기 전엔 DELETE 들 중 하나가 실패해도 파일은 이미 지워진 뒤였다 — "
        "'행은 있는데 파일이 없는' 상태)", _abs)
    _trash_check = os.path.join(os.environ["BOKGUON_UPLOAD_DIR"], "_trash", *_rel.split("/"))
    chk(not os.path.isfile(_trash_check),
        "STEP 실패 뒤엔 휴지통에도 옮겨지지 않았다(파일 이동 자체가 아예 실행 안 됨)")

    # ── 정상 경로: 이번엔 진짜로 정리되고, 파일은 삭제가 아니라 휴지통행이다 ──
    rc2, out2 = _run_golive()
    #  ⚠ cmd_go_live 는 성공 시 명시적 return 이 없다(None) — main() 이 `... or 0`
    #    으로 정규화한다(round66 의 cmd_restore 와 같은 관례). falsy 로 확인한다.
    chk(not rc2, "★★ ② 정상 경로에서 cmd_go_live 가 실패 아님(None/0)을 반환한다",
        f"rc={rc2} out={out2[-500:]}")

    _c = DB.get_db()
    _row2 = _c.execute("SELECT 1 FROM cases WHERE id=?", (cid,)).fetchone()
    _c.close()
    chk(_row2 is None, "★★ ② 정상 경로에서는 데모 사건 행이 실제로 지워진다", _row2)
    chk(not os.path.isfile(_abs),
        "★★ ② 정상 경로에서는 사진이 원래 자리에서 사라진다", _abs)
    chk(os.path.isfile(_trash_check),
        "★★★ ② 정상 경로에서는 삭제가 아니라 휴지통(_trash)으로 옮겨진다"
        "(고치기 전엔 os.remove() 로 영구삭제 — 되돌릴 방법이 없었다)", _trash_check)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드69 실측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    os.environ.pop("BOKGUON_BACKUP_DIR", None)
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
