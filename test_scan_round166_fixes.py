# -*- coding: utf-8 -*-
"""스캔 166라운드 회귀 — manage.py reset-pw 가 협력사/보험사 아이디를
정규화 없이 그대로 비교해, 대문자·앞뒤공백이 섞이면 계정이 있어도
"찾을 수 없습니다"로 조용히 실패하던 결함.

  partners/insurers.login_id 는 로그인(app.py api_partner_login·
  api_insurer_login)·중복확인(_login_id_taken)·생성(cmd_create_insurer)
  전부 strip+lower 로 정규화해 소문자로만 저장한다. 이 명령(reset-pw)만
  그 정규화 없이 SQL '=' 비교에 그대로 넣었다 — 급하게 계정을 복구해야
  하는 지원 상황에서 실재하는 계정을 "없다"고 오인시켰다.

      python test_scan_round166_fixes.py
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


SRC = read("manage.py")

print("=" * 72)
print("  스캔 166라운드 회귀 — reset-pw 의 협력사/보험사 아이디 정규화 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = SRC.index("def cmd_reset_pw(")
i1 = SRC.index("\ndef ", i0 + 1)
body = SRC[i0:i1]
chk('argv[1].strip().lower() if argv[0] in ("partner", "insurer") else argv[1].strip()' in body,
    "★★★ cmd_reset_pw 가 partner/insurer 아이디를 strip+lower 로 정규화한다")

# ============================================================
print("\n[2] 실행 — 대문자·공백 섞인 아이디로도 실제 계정을 찾아 재설정하는가")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round166_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import manage as M

    conn = DB.get_db()
    conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,login_id,"
        "                     password_hash,created_at) "
        "VALUES('R166업체','시공사','활성','가드레일','서울','r166p','old-hash',?)", (DB.now(),))
    conn.execute(
        "INSERT INTO insurers(name,status,login_id,password_hash,created_at) "
        "VALUES('R166보험사','활성','r166i','old-hash',?)", (DB.now(),))
    conn.commit(); conn.close()

    def _hash_of(table, login_id):
        c = DB.get_db()
        r = c.execute(f"SELECT password_hash, must_change_pw FROM {table} WHERE login_id=?",
                      (login_id,)).fetchone()
        c.close()
        return dict(r) if r else None

    #  ① 대문자로 친 협력사 아이디 — 고치기 전엔 "찾을 수 없습니다"로 실패했다
    M.cmd_reset_pw(["partner", "R166P"])
    row1 = _hash_of("partners", "r166p")
    chk(row1 is not None and row1["password_hash"] != "old-hash" and row1["must_change_pw"] == 1,
        "★★★ 대문자로 친 협력사 아이디도 실제 계정을 찾아 비밀번호를 재설정한다"
        "(고치기 전엔 대소문자가 달라 찾지 못했다)", row1)

    #  ② 앞뒤 공백이 섞인 보험사 아이디
    M.cmd_reset_pw(["insurer", "  r166i  "])
    row2 = _hash_of("insurers", "r166i")
    chk(row2 is not None and row2["password_hash"] != "old-hash" and row2["must_change_pw"] == 1,
        "★★★ 앞뒤 공백이 섞인 보험사 아이디도 정규화해 실제 계정을 찾는다", row2)

    #  ③ 대조군 — 정말로 없는 아이디는 여전히 정확히 실패해야 한다(과잉매칭 아님)
    rc3 = M.cmd_reset_pw(["partner", "존재안함"])
    chk(rc3 == 1, "★ 실제로 없는 아이디는 여전히 실패로 정확히 보고한다(과잉매칭 아님)", rc3)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드166 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
