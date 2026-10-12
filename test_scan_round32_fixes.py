# -*- coding: utf-8 -*-
"""스캔 32라운드 회귀 — 조사 에이전트가 찾은 것 중 이번에 고친 두 자리.

  ① manage.py check 가 계좌 암호화키를 **길이만** 보고 "설정됨"이라 답했다 —
     다른 키라도 32자 이상이면 통과였다. crypto_util.decrypt() 는 실패를
     전부 삼켜 빈 문자열을 돌려주므로(계좌 없음과 구분 불가), 서버 이전 때
     이 키를 그대로 옮기지 않으면 전 업체 계좌가 조용히 사라진 것처럼
     보이는데 배포 전 점검은 그걸 못 잡았다. 실제 저장된 암호문을 복호화
     해보는 왕복 검증을 추가했다.

  ② geocode_fill.fill() 이 검색 API 가 돌려준 좌표의 **truthiness만**
     보고(`lat and lng`) 한반도 범위인지는 안 봤다 — 수동 좌표 입력
     (app.py _picked_coords)은 이미 33.0~39.5/124.0~132.0 범위를 강제하는데
     같은 방어가 여기 없었다. 0 이 아닌 잘못된 좌표(예: 도쿄)는 그대로
     저장돼 그 업체가 엉뚱한 위치로 거리 배차에 잡힐 수 있었다(실측 데이터
     오염은 없었으나 방어선 자체가 없었다).

      python test_scan_round32_fixes.py
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


MNG = read("manage.py")
GEO = read("geocode_fill.py")

print("═" * 72)
print("  스캔 32라운드 회귀 — 계좌키 복호화 왕복 검증 · 지오코딩 한반도 범위")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 배선이 실제로 있는가")
# ──────────────────────────────────────────────────────────────
chk("복호화 왕복" in MNG, "★ manage.py check 에 복호화 왕복 검사 문구가 있다")
chk("CRYPTO.decrypt(enc_row" in MNG, "★★ 실제로 crypto_util.decrypt() 를 부른다")
chk("bank_account_enc LIKE 'v1:%'" in MNG, "★ 실제 암호화된 행을 조회한다(빈 값이 아니라)")

chk("_KOREA_LAT = (33.0, 39.5)" in GEO and "_KOREA_LNG = (124.0, 132.0)" in GEO,
    "★★ geocode_fill.py 가 app.py _picked_coords 와 같은 범위 상수를 쓴다")
chk("def _in_korea(lat, lng):" in GEO, "★ 범위 판정 함수를 찾았다")
chk("_in_korea(best[\"lat\"], best[\"lng\"])" in GEO,
    "★★★ fill() 이 실제로 그 판정을 검색 결과에 적용한다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 계좌키 복호화 왕복이 실제로 키 불일치를 구분하는가")
# ──────────────────────────────────────────────────────────────
_tmpdir1 = tempfile.mkdtemp(prefix="keycheck_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir1, "kc.db")
os.environ["BOKGUON_ENC_KEY"] = "a" * 44
os.environ["BOKGUON_ENV"] = "prod"
sys.path.insert(0, HERE)
try:
    import db as DB
    import crypto_util as CRYPTO
    DB.init_db()
    conn = DB.get_db()
    enc = CRYPTO.encrypt("110-234-567890")
    conn.execute("INSERT INTO partners(name,partner_type,status,bank_account_enc) "
                 "VALUES('검증업체','시행사','활성',?)", (enc,))
    conn.commit()
    row = conn.execute(
        "SELECT bank_account_enc FROM partners WHERE bank_account_enc LIKE 'v1:%' "
        "LIMIT 1").fetchone()
    conn.close()

    ok_right = bool(CRYPTO.decrypt(row["bank_account_enc"]))
    chk(ok_right, "★ 올바른 키로는 복호화 왕복이 성공한다(과잉 차단 아님)")

    os.environ["BOKGUON_ENC_KEY"] = "b" * 44   # 재배포 때 키를 안 옮긴 상황 재현
    ok_wrong = bool(CRYPTO.decrypt(row["bank_account_enc"]))
    chk(not ok_wrong,
        "★★★ 틀린 키로는 복호화가 실패로 나온다(실측 결함 재현·수정 확인)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 계좌키 왕복 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_ENC_KEY", None)
    os.environ.pop("BOKGUON_ENV", None)
    import shutil
    shutil.rmtree(_tmpdir1, ignore_errors=True)

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 0이 아닌 한반도 밖 좌표가 실제로 저장을 안 하는가")
# ──────────────────────────────────────────────────────────────
#  ⚠ (0,0) 은 나쁜 예시다 — 옛 코드의 `lat and lng` truthiness 검사가 0.0 을
#    우연히 걸러낸다. 새 검사가 막아야 하는 건 0이 아닌데 범위 밖인 값이다.
_tmpdir2 = tempfile.mkdtemp(prefix="geo_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir2, "geo.db")
try:
    import importlib
    import db as DB2
    importlib.reload(DB2)
    DB2.init_db()
    conn2 = DB2.get_db()
    conn2.execute("DELETE FROM partners")   # 데모 399곳이 LIMIT 을 다 차지 안 하게
    pid = conn2.execute(
        "INSERT INTO partners(name,partner_type,status,region,address) "
        "VALUES('검증업체','시행사','활성','서울','서울 강남구 아무데나 1')").lastrowid
    conn2.commit()
    conn2.close()

    import geocode_fill as G
    importlib.reload(G)

    class _FakeADDR:
        @staticmethod
        def provider():
            return "검증용"

        @staticmethod
        def search(q):
            return [{"lat": 35.681236, "lng": 139.767125,   # 도쿄 — 0 아님
                     "region": "서울", "road": "강남구"}]

    G.ADDR = _FakeADDR()
    done = G.fill("partners", 10, dry=False)
    chk(done == 0, "★★★ 도쿄 좌표는 채워지지 않는다(실측 결함 재현·수정 확인)", done)

    conn3 = DB2.get_db()
    row3 = conn3.execute("SELECT lat, lng FROM partners WHERE id=?", (pid,)).fetchone()
    conn3.close()
    chk(row3["lat"] is None and row3["lng"] is None,
        "★★ DB 에도 도쿄 좌표가 저장되지 않았다", dict(row3))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 지오코딩 범위 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    import shutil
    shutil.rmtree(_tmpdir2, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
