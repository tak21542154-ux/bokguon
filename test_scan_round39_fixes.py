# -*- coding: utf-8 -*-
"""스캔 39라운드 회귀 — 로그인 응답시간으로 아이디 존재여부를 알아내는 결함.

  조사 에이전트가 실측한 결함: `bool(u) and DB.verify_pw(...)` 형태의
  단락평가 때문에, **없는 아이디는 PBKDF2(60만회 반복) 연산 자체를 건너뛰어**
  응답이 즉시 오고, **있는 아이디(비번 틀림)는 그 연산을 다 치른 뒤** 응답한다
  — 그 시간차(약 110ms, 5.85배)만으로 비밀번호 없이도 계정 존재 여부를
  알아낼 수 있었다(admin·협력사·보험사 3개 로그인 라우트 전부, 원인은 같은
  단락평가 패턴).

  고침: 아이디가 없어도 **같은 비용의 더미 해시**(`_DUMMY_PW_HASH`)로 항상
  검증을 돌려 시간차를 없앤다. 진짜 계정 존재여부는 그 해시결과가 아니라
  `bool(u)`/`bool(row)`/`bool(sub)` 로 별도 판정(더미 해시엔 항상 실패).

      python test_scan_round39_fixes.py
"""
import io
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("═" * 72)
print("  스캔 39라운드 회귀 — 로그인 타이밍 사이드채널(아이디 존재 노출)")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 배선이 실제로 있는가")
# ──────────────────────────────────────────────────────────────
chk('_DUMMY_PW_HASH = DB.hash_pw(' in APP_SRC, "★ 더미 해시 상수가 정의돼 있다")
chk('pw_ok = DB.verify_pw(password, (u["password_hash"] if u else None) or _DUMMY_PW_HASH)'
    in APP_SRC, "★★ admin 로그인이 없는 아이디에도 더미 해시로 검증한다")
chk('row_ok = DB.verify_pw(password, (row["password_hash"] if row else None) or _DUMMY_PW_HASH)'
    in APP_SRC, "★★ 포털(원계정) 로그인도 마찬가지다")
chk('sub_ok = DB.verify_pw(password, (sub["password_hash"] if sub else None) or _DUMMY_PW_HASH)'
    in APP_SRC, "★★ 포털(하위계정) 로그인도 마찬가지다")
chk('_portal_authenticate(conn, "partner", login_id, password)' in APP_SRC
    and '_portal_authenticate(conn, "insurer", login_id, password)' in APP_SRC,
    "협력사·보험사 로그인이 같은 함수를 공유한다(한 곳만 고치면 둘 다 고쳐짐)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제로 응답시간 차이가 없어졌는가")
# ──────────────────────────────────────────────────────────────
import tempfile
_tmpdir = tempfile.mkdtemp(prefix="timing39_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

N = 25
REAL_ADMIN = "timing39_admin"
REAL_PARTNER = "timing39_partner"
REAL_SUB = "timing39_subaccount"
FAKE = "timing39_nonexistent_xyz"


def _measure(client, path, body_fn, n):
    import app as A
    times = []
    for _ in range(n):
        A._rate_buckets.clear()
        conn = DB.get_db()
        conn.execute("DELETE FROM login_attempts")
        conn.commit(); conn.close()
        t0 = time.perf_counter()
        client.post(path, json=body_fn())
        times.append((time.perf_counter() - t0) * 1000)
    return times


try:
    import db as DB
    DB.init_db()
    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) VALUES(?,?,'검증','중간관리자')",
                 (REAL_ADMIN, DB.hash_pw("RealPassword!2026")))
    conn.execute("INSERT INTO partners(name,partner_type,status,login_id,password_hash) "
                 "VALUES('검증협력사','시행사','활성',?,?)",
                 (REAL_PARTNER, DB.hash_pw("RealPassword!2026")))
    pid_for_sub = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('검증협력사(하위계정용)','시행사','활성')"
    ).lastrowid
    conn.execute(
        "INSERT INTO portal_users(org_type,org_id,login_id,password_hash) "
        "VALUES('partner',?,?,?)",
        (pid_for_sub, REAL_SUB, DB.hash_pw("RealPassword!2026")))
    conn.commit()
    conn.close()

    import app as A
    client = A.app.test_client()

    exists_ms = _measure(client, "/api/login",
                          lambda: {"username": REAL_ADMIN, "password": "wrong-password"}, N)
    absent_ms = _measure(client, "/api/login",
                          lambda: {"username": FAKE, "password": "wrong-password"}, N)
    e_mean, a_mean = statistics.mean(exists_ms), statistics.mean(absent_ms)
    ratio = max(e_mean, a_mean) / max(min(e_mean, a_mean), 0.001)
    print(f"       admin: 존재={e_mean:.1f}ms · 부재={a_mean:.1f}ms · 배율={ratio:.2f}x")
    chk(ratio < 1.6,
        "★★★ admin 로그인 — 존재/부재 응답시간이 비슷해졌다(고치기 전엔 5.85배)",
        f"배율 {ratio:.2f}x (존재 {e_mean:.1f}ms / 부재 {a_mean:.1f}ms)")

    exists_ms2 = _measure(client, "/api/partner/login",
                           lambda: {"login_id": REAL_PARTNER, "password": "wrong-password"}, N)
    absent_ms2 = _measure(client, "/api/partner/login",
                           lambda: {"login_id": FAKE, "password": "wrong-password"}, N)
    e_mean2, a_mean2 = statistics.mean(exists_ms2), statistics.mean(absent_ms2)
    ratio2 = max(e_mean2, a_mean2) / max(min(e_mean2, a_mean2), 0.001)
    print(f"       partner: 존재={e_mean2:.1f}ms · 부재={a_mean2:.1f}ms · 배율={ratio2:.2f}x")
    chk(ratio2 < 1.6,
        "★★★ 협력사 로그인 — 존재/부재 응답시간이 비슷해졌다(_portal_authenticate 공유 확인)",
        f"배율 {ratio2:.2f}x (존재 {e_mean2:.1f}ms / 부재 {a_mean2:.1f}ms)")

    #  하위계정(portal_users) 경로도 따로 잰다 — 원계정 조회가 이미 더미해시를
    #  치른 뒤라, 하위계정 쪽 단락평가만 되살아나도 위 두 측정으론 안 잡힌다.
    exists_ms3 = _measure(client, "/api/partner/login",
                           lambda: {"login_id": REAL_SUB, "password": "wrong-password"}, N)
    absent_ms3 = _measure(client, "/api/partner/login",
                           lambda: {"login_id": FAKE, "password": "wrong-password"}, N)
    e_mean3, a_mean3 = statistics.mean(exists_ms3), statistics.mean(absent_ms3)
    ratio3 = max(e_mean3, a_mean3) / max(min(e_mean3, a_mean3), 0.001)
    print(f"       partner(하위계정): 존재={e_mean3:.1f}ms · 부재={a_mean3:.1f}ms · 배율={ratio3:.2f}x")
    chk(ratio3 < 1.6,
        "★★★ 하위계정 로그인도 존재/부재 응답시간이 비슷해졌다",
        f"배율 {ratio3:.2f}x (존재 {e_mean3:.1f}ms / 부재 {a_mean3:.1f}ms)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 타이밍 실측", f"{type(e).__name__} {e}")
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
