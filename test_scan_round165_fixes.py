# -*- coding: utf-8 -*-
"""스캔 165라운드 회귀 — 캠페인 수신자 산출의 지역 필터가 SQL LIKE 라서
표기가 다르면(예: '충청남도' vs '충남') 같은 지역인데도 놓치던 결함.

  이 파일의 _onboard_rows()/_onboard_where() 가 이미 정확히 같은 문제를
  겪고 고쳤다 — 자기 주석에 "region 표기가 149가지라 SQL LIKE 로는
  '충청남도' 를 '충남' 으로 못 잡는다(실측: 충남 14→24곳)" 라고 명시하며
  region_matches() 로 파이썬에서 거르도록 바꿨다. 그런데 캠페인 기능
  (_campaign_recipients)만 그 해결책을 못 받고 예전 SQL LIKE 방식에
  그대로 남아 있었다 — 결과가 0이 아니라 "일부만" 나오므로 캠페인 생성
  자체는 에러 없이 성공해, 운영자는 다 돌렸다고 믿지만 실제로는 상당수가
  조용히 누락됐다.

      python test_scan_round165_fixes.py
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


APP_SRC = read("app.py")
JS_SRC = read("static/admin.js")

print("=" * 72)
print("  스캔 165라운드 회귀 — 캠페인 지역필터의 SQL LIKE 표기불일치 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def _campaign_recipients(")
i1 = APP_SRC.index("\n@app.", i0 + 1)
body = APP_SRC[i0:i1]
chk('"region LIKE ? ESCAPE' not in body,
    "★★★ 지역을 SQL LIKE 로 거르던 옛 조건이 사라졌다")
chk("region_matches(r.get(\"region\"), _rg)" in body,
    "★★★ _onboard_rows() 와 같은 region_matches() 파이썬 필터를 쓴다")

chk('placeholder="예: 호남 / 강원"' not in JS_SRC,
    "★ 캠페인 폼의 '호남' 예시(region_matches 조차 처리 못 하는 그룹명)가 사라졌다")

# ============================================================
print("\n[2] 실행 — 표기가 달라도(충남 vs 충청남도) 같은 지역으로 잡히는가")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round165_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    #  약칭으로 저장된 곳 — 예전에도 잡혔다(대조군)
    conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,email,"
        "                     email_opt_out,email_consent,created_at) "
        "VALUES('R165충남약칭','시공사','활성','가드레일','충남','a@r165.test',0,1,?)", (DB.now(),))
    #  풀네임으로 저장된 곳 — 이번 결함의 핵심(예전엔 LIKE '%충남%' 에 안 걸렸다)
    conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,email,"
        "                     email_opt_out,email_consent,created_at) "
        "VALUES('R165충남풀네임','시공사','활성','가드레일','충청남도','b@r165.test',0,1,?)", (DB.now(),))
    #  다른 지역 — 여전히 안 걸려야 한다(과잉매칭 아님)
    conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,email,"
        "                     email_opt_out,email_consent,created_at) "
        "VALUES('R165경북','시공사','활성','가드레일','경상북도','c@r165.test',0,1,?)", (DB.now(),))
    conn.commit()

    ok, no_contact, opted, no_consent = A._campaign_recipients(conn, {"region": "충남", "channel": "메일"})
    names = {r["name"] for r in ok}
    chk("R165충남약칭" in names, "★ (사전조건) 약칭 표기는 원래도 잡힌다", names)
    chk("R165충남풀네임" in names,
        "★★★ 풀네임 표기('충청남도')도 이제 '충남' 검색에 잡힌다"
        "(고치기 전엔 LIKE '%충남%' 에 안 걸려 놓쳤다)", names)
    chk("R165경북" not in names,
        "★ 다른 지역(경상북도)은 여전히 안 걸린다(과잉매칭 아님)", names)

    #  실제 API(/api/campaigns/preview)로도 같은 결과가 나오는가
    conn2 = DB.get_db()
    conn2.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('admin','x','검증','최고관리자')")
    conn2.commit(); conn2.close()
    admin = A.app.test_client()
    tok = "r165-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["_csrf"] = tok
    r1 = admin.post("/api/campaigns/preview",
                     json={"channel": "메일", "region": "충남", "body": "test"},
                     headers={"X-CSRF-Token": tok})
    chk(r1.status_code == 200 and r1.get_json().get("count") == 2,
        "★★★ 실제 미리보기 API 도 풀네임 표기까지 합쳐 2곳을 낸다", r1.get_json())
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드165 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
