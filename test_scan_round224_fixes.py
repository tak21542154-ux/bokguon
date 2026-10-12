# -*- coding: utf-8 -*-
"""스캔 224라운드 회귀 — AI 자동승인 임계값(ai_auto_threshold) 변경 시,
   전용 엔드포인트(PATCH /api/ai/threshold, 실제 화면이 유일하게 쓰는 경로)가
   새 값만 감사로그에 남기던 결함.

   형제(PATCH /api/settings, api_settings_set)는 같은 키를 다루면서 "덮어쓰기
   전에 옛 값을 읽어 이전값 → 새값으로 남긴다" — 그 이유(19342행 주석)를
   그대로 밝힌다: 이 값이 시공사진 자동승인 문턱이라 나중에 "그때 기준이
   뭐였나"에 답할 수 있어야 한다(보험사 정산액에 영향을 주는 fee_rate 급
   파급력). 그런데 정작 화면이 실제로 부르는 전용 라우트만 이 원칙을 어겼다.

      python test_scan_round224_fixes.py
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


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


APP_SRC = read("app.py")

print("═" * 72)
print("  스캔 224라운드 회귀 — AI 자동승인 임계값 변경 로그에 옛값 누락")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 함수 경계 안에서")
# ──────────────────────────────────────────────────────────────
th_body = _py_fn_body(APP_SRC, "api_ai_threshold_set")
chk("SELECT value FROM settings WHERE key='ai_auto_threshold'" in th_body,
    "★★★★ api_ai_threshold_set 이 덮어쓰기 전에 옛 값을 먼저 읽는다"
    "(예전엔 곧바로 INSERT OR REPLACE 만 하고 새 값만 로그에 남겼다)")
chk('f"{old}% → {v}%"' in th_body,
    "★★★ 로그 문구가 형제(api_settings_set)와 같은 원칙으로 이전값 → 새값을 남긴다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실서버 경로(Flask test_client + 임시 DB)로 실제 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round224_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r224admin','x','검증','최고관리자')")
    #  이 값이 아예 없던 상태에서 시작한다 — "옛값 없음" 경로까지 함께 확인.
    conn.execute("DELETE FROM settings WHERE key='ai_auto_threshold'")
    conn.commit()
    conn.close()

    admin = A.app.test_client()
    _tok = "r224-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r224admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    hdr = {"X-CSRF-Token": _tok}

    def last_detail():
        c = DB.get_db()
        row = c.execute(
            "SELECT detail FROM activity_log WHERE action='AI 자동승인 임계값 변경' "
            "ORDER BY id DESC LIMIT 1").fetchone()
        c.close()
        return row["detail"] if row else None

    # ── ① 최초 설정(옛값 없음) ──
    r1 = admin.patch("/api/ai/threshold", headers=hdr, json={"threshold": 90})
    chk(r1.status_code == 200, "STEP 최초 설정 자체는 정상 처리된다(과잉차단 아님)",
        (r1.status_code, r1.get_json()))
    chk(last_detail() == "90%",
        "STEP 옛값이 없을 때는 예전과 같은 모양(그냥 '90%')으로 남는다(회귀 아님)",
        last_detail())

    # ── ② 값 변경 — 이전값 → 새값이 남는가(이번 라운드의 핵심) ──
    r2 = admin.patch("/api/ai/threshold", headers=hdr, json={"threshold": 77})
    chk(r2.status_code == 200, "STEP 변경 자체는 정상 처리된다", (r2.status_code, r2.get_json()))
    chk(last_detail() == "90% → 77%",
        "★★★★ 임계값을 90→77 로 바꾸면 감사로그에 '90% → 77%'로 남는다"
        "(고치기 전엔 '77%'만 남아 이전 기준이 무엇이었는지 알 수 없었다)",
        last_detail())

    # ── ③ 연속 변경 — 매번 '직전' 값을 기준으로 남는가 ──
    r3 = admin.patch("/api/ai/threshold", headers=hdr, json={"threshold": 82})
    chk(r3.status_code == 200, "STEP 두 번째 변경도 정상 처리된다", (r3.status_code, r3.get_json()))
    chk(last_detail() == "77% → 82%",
        "★★★ 연속 변경도 매번 '바로 직전' 값을 기준으로 남는다(스냅샷이 안 밀린다)",
        last_detail())

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드224 서버측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
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
