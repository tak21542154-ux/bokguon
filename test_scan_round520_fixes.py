# -*- coding: utf-8 -*-
"""스캔 520라운드 회귀 — 포털(협력사·보험사) 로그인이 레거시(SHA256) 비밀번호
해시를 검증은 하면서도 PBKDF2로 승급하지 않던 결함.

  db.py:verify_pw() 는 두 형식을 다 받는다 — 새 형식(pbkdf2$반복수$솔트$해시)과
  옛 형식(솔트 없이 "bokguon$"+비번을 SHA256 한 번 돌린 것, 레거시 계정 호환용).
  admin 로그인(app.py:api_login)은 로그인 성공 시 DB.is_legacy_hash() 로 옛
  형식을 확인해 그 자리에서 새 형식으로 갈아 끼운다("승급도 해시를 바꾼다 —
  아래에서 세션에 심을 지문이 새 값이어야 한다"는 그 자리의 주석이 이미 그
  의도를 밝힌다).

  그런데 협력사·보험사 포털의 원계정·하위계정 로그인이 전부 거치는 유일한
  관문인 _portal_authenticate()(app.py:784)는 그 승급이 아예 없었다 —
  admin 과 완전히 같은 db.verify_pw()/hash_pw() 를 쓰면서도 형제 함수의
  로직만 안 옮겨진 것이다. 관리자 계정보다 노출 표면이 훨씬 큰 외부 조직
  계정(협력사 수백 곳·보험사 전체, 각자 원계정+하위계정)이 옛 방식(솔트 없는
  단일회 SHA256 — 레인보우테이블·GPU 무차별대입에 훨씬 약하다)으로 남아 있는
  한 로그인은 계속 성공시키면서도 그 약한 해시를 영원히 그대로 방치한다.

  round520 수정: _portal_authenticate() 의 원계정(row) 분기와 하위계정(sub)
  분기 둘 다에 admin 로그인과 같은 DB.is_legacy_hash() 승급을 추가했다
  (원계정은 partners/insurers, 하위계정은 portal_users 를 각자 갱신).

      python test_scan_round520_fixes.py
"""
import hashlib
import io
import os
import sys
import tempfile

#  ⚠ 윈도 콘솔(cp949)에서 이 파일의 '—' 등을 print() 하면 죽는다 — 이 저장소
#    거의 모든 CLI/점검 도구가 이미 쓰는 방어(check_tx_paths.py 등, round518/519)
#    를 회귀테스트 자신에도 그대로 적용한다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def legacy_hash(pw):
    """db.py:verify_pw() 의 레거시 분기가 인정하는 옛 형식 — 솔트 없는 단일회 SHA256."""
    return hashlib.sha256(("bokguon$" + pw).encode()).hexdigest()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 520라운드 회귀 — 포털 로그인 레거시 해시 미승급")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — _portal_authenticate() 두 분기 모두 승급 코드가 있다")
# ------------------------------------------------------------
i0 = APP_SRC.index("def _portal_authenticate(conn, org_type, login_id, password):")
i1 = APP_SRC.index("\ndef ", i0 + 1)
body_seg = APP_SRC[i0:i1]
chk("DB.is_legacy_hash(row[" in body_seg,
    "★★★★ 원계정(row) 분기가 레거시 해시를 검사한다")
chk("DB.is_legacy_hash(sub[" in body_seg,
    "★★★★ 하위계정(sub) 분기도 레거시 해시를 검사한다")
chk('UPDATE {table} SET password_hash=?' in body_seg,
    "★★★ 원계정은 자기 표(partners/insurers)의 해시를 갱신한다")
chk("UPDATE portal_users SET password_hash=?" in body_seg,
    "★★★ 하위계정은 portal_users 의 해시를 갱신한다")
# 형제(admin 로그인)도 같은 함수를 쓰는지 참고 확인(회귀 판단 기준선)
chk("DB.is_legacy_hash(u[" in APP_SRC,
    "(참고) 형제 admin 로그인도 원래부터 같은 승급을 한다 — 이번에 새로 생긴 "
    "패턴이 아니라 이미 있던 패턴을 포털에도 맞춘 것")

# ============================================================
print("\n[2] 실행 준비 — 격리 스크래치 DB")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round520_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
DB = A = None
try:
    import db as DB
    DB.init_db()
    import app as A
    chk(True, "스크래치 DB·app 모듈 로드 성공", os.environ["BOKGUON_DB_PATH"])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 준비 실패", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — 협력사 원계정: 레거시 해시로 로그인하면 PBKDF2로 승급된다")
# ------------------------------------------------------------
if DB and A:
    try:
        conn = DB.get_db()
        pw1 = "R520테스트비번1"
        pid = conn.execute(
            "INSERT INTO partners(name,partner_type,status,login_id,password_hash) "
            "VALUES('R520협력사원계정','시공사','활성',?,?)",
            ("r520partner", legacy_hash(pw1))).lastrowid
        conn.commit()

        before = conn.execute(
            "SELECT password_hash FROM partners WHERE id=?", (pid,)).fetchone()[0]
        chk(DB.is_legacy_hash(before), "준비 확인 — 심어 둔 해시가 실제로 레거시 형식이다")

        cl = A.app.test_client()
        resp = cl.post("/api/partner/login", json={"login_id": "r520partner", "password": pw1})
        j = resp.get_json() or {}
        chk(resp.status_code == 200 and j.get("ok") is True,
            "레거시 해시로도 정상 로그인된다(verify_pw 레거시 분기 자체는 회귀 없음)",
            (resp.status_code, j))

        after = conn.execute(
            "SELECT password_hash FROM partners WHERE id=?", (pid,)).fetchone()[0]
        chk(after != before,
            "★★★★★ 로그인 성공 뒤 저장된 해시가 실제로 바뀌었다(승급 발생)",
            {"before": before, "after": after})
        chk(not DB.is_legacy_hash(after),
            "★★★★★ 승급된 해시는 더 이상 레거시 형식이 아니다(pbkdf2$)", after)
        chk(DB.verify_pw(pw1, after),
            "★★★★ 승급된 새 해시로도 같은 비밀번호가 그대로 검증된다(왕복 확인)")

        # 승급이 로그인 자체를 깨면 안 된다 — 다음 로그인도 (이제 pbkdf2 로) 정상 동작해야 한다.
        resp2 = cl.post("/api/partner/login", json={"login_id": "r520partner", "password": pw1})
        j2 = resp2.get_json() or {}
        chk(resp2.status_code == 200 and j2.get("ok") is True,
            "승급된 해시로 재로그인도 정상 동작한다(퇴행 없음)", (resp2.status_code, j2))
        conn.close()
    except Exception as e:                                          # noqa: BLE001
        chk(False, "★★★ [3] 준비/실행", f"{type(e).__name__} {e}")
else:
    chk(False, "[3] 건너뜀 — 준비 단계 실패")

# ============================================================
print("\n[4] 실행 — 보험사 하위계정(portal_users): 같은 방식으로 승급된다")
# ------------------------------------------------------------
if DB and A:
    try:
        conn = DB.get_db()
        iid = conn.execute(
            "INSERT INTO insurers(name,status) VALUES('R520보험사','활성')").lastrowid
        pw2 = "R520테스트비번2"
        sid = conn.execute(
            "INSERT INTO portal_users(org_type,org_id,login_id,password_hash,role,status) "
            "VALUES('insurer',?,?,?,'중간관리자','활성')",
            (iid, "r520insub", legacy_hash(pw2))).lastrowid
        conn.commit()

        before2 = conn.execute(
            "SELECT password_hash FROM portal_users WHERE id=?", (sid,)).fetchone()[0]
        chk(DB.is_legacy_hash(before2), "준비 확인 — 하위계정에 심어 둔 해시도 레거시 형식이다")

        cl2 = A.app.test_client()
        resp3 = cl2.post("/api/insurer/login", json={"login_id": "r520insub", "password": pw2})
        j3 = resp3.get_json() or {}
        chk(resp3.status_code == 200 and j3.get("ok") is True,
            "보험사 하위계정도 레거시 해시로 정상 로그인된다(회귀 없음)", (resp3.status_code, j3))

        after2 = conn.execute(
            "SELECT password_hash FROM portal_users WHERE id=?", (sid,)).fetchone()[0]
        chk(after2 != before2,
            "★★★★★ 하위계정도 로그인 성공 뒤 해시가 승급된다", {"before": before2, "after": after2})
        chk(not DB.is_legacy_hash(after2),
            "★★★★★ 승급된 하위계정 해시는 더 이상 레거시가 아니다")
        chk(DB.verify_pw(pw2, after2),
            "★★★★ 승급된 하위계정 해시로도 같은 비밀번호가 검증된다")
        conn.close()
    except Exception as e:                                          # noqa: BLE001
        chk(False, "★★★ [4] 준비/실행", f"{type(e).__name__} {e}")
else:
    chk(False, "[4] 건너뜀 — 준비 단계 실패")

# ============================================================
print("\n[5] 되돌림-증명 — 승급 검사를 무력화하면(round520 이전 상태와 동일한 "
      "효과) 로그인은 여전히 성공하면서 해시는 영원히 레거시로 남는다")
# ------------------------------------------------------------
if DB and A:
    try:
        conn = DB.get_db()
        pw3 = "R520테스트비번3"
        pid3 = conn.execute(
            "INSERT INTO partners(name,partner_type,status,login_id,password_hash) "
            "VALUES('R520협력사되돌림','시공사','활성',?,?)",
            ("r520revert", legacy_hash(pw3))).lastrowid
        conn.commit()

        #  코드를 되돌리는 대신(동시 세션이 app.py 를 함께 건드릴 수 있는 환경이라
        #  전체 소스 스왑은 피한다), 이 라운드가 새로 부르기 시작한 딱 그 판정
        #  함수만 "항상 아니오"로 눌러 같은 인과관계를 증명한다 — round520 이전
        #  코드는 이 판정을 아예 호출하지 않았으므로 효과가 동일하다.
        _real_is_legacy = DB.is_legacy_hash
        DB.is_legacy_hash = lambda stored: False
        try:
            cl3 = A.app.test_client()
            resp4 = cl3.post("/api/partner/login",
                              json={"login_id": "r520revert", "password": pw3})
            j4 = resp4.get_json() or {}
            chk(resp4.status_code == 200 and j4.get("ok") is True,
                "방어를 꺼도 로그인 자체는 여전히 성공한다(verify_pw 레거시 분기는 별개 코드)",
                (resp4.status_code, j4))
        finally:
            DB.is_legacy_hash = _real_is_legacy

        still = conn.execute(
            "SELECT password_hash FROM partners WHERE id=?", (pid3,)).fetchone()[0]
        chk(DB.is_legacy_hash(still),
            "★★★★★ 인과관계 확인 — 승급 검사를 끄면 로그인에 성공해도 해시는 "
            "레거시로 그대로 남는다(이것이 round520 수정 전의 실제 결함 상태)", still)
        conn.close()
    except Exception as e:                                          # noqa: BLE001
        chk(False, "★★★ [5] 되돌림-증명", f"{type(e).__name__} {e}")
else:
    chk(False, "[5] 건너뜀 — 준비 단계 실패")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
