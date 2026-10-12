# -*- coding: utf-8 -*-
"""스캔 372라운드 회귀 — 공용 목록검색 헬퍼 _sq()/_sqp()(app.py:1545·1570)의
   status_col 기본값('status')을, 실제로는 status 컬럼이 없는 테이블을 대상으로
   하는 두 호출부(api_admins_list — admins 테이블, api_notices — notices 테이블)
   가 그대로 물려받아, 그 API에 `?status=아무값` 쿼리스트링만 붙여도
   `sqlite3.OperationalError: no such column: status` 로 죽던 결함[경미,
   견고성 — 인증된 사용자가 URL만 바꿔도 500].

  배경: search_filters()(1577행)는 `status_col` 이 참(truthy)이고 요청에
  `?status=` 값이 있으면 무조건 `WHERE {status_col}=?` 를 붙인다. 이 코드베이스
  에는 이미 이 함수를 부르는 8개 지점이 있는데, 그중 두 곳(standard_boq —
  14459행, est_check_band — 15143행)은 대상 테이블에 status 컬럼이 없다는
  걸 알고 이미 `status_col=None` 을 명시했다 — **바로 이 관례**를 이번에
  건드린 두 곳(api_admins_list·api_notices)만 안 따르고 기본값(`"status"`)에
  기댔다. db.py 로 두 테이블 스키마를 직접 대조 확인: admins(id·username·
  password_hash·name·role·created_at)·notices(id·title·body·audience·pinned·
  created_at) 둘 다 status 컬럼이 원래 없다(campaigns·notifications 등 status
  컬럼이 실제로 있는 다른 호출부는 문제 없음 — 8개 호출부 전수 대조 확인).

  고침: 이미 확립된 관례 그대로, 이 두 호출부에도 `status_col=None` 을
  명시해 search_filters() 가 status 필터를 아예 만들지 않게 한다 — 공유
  헬퍼 자체의 기본값(다른 6곳은 정상 동작)은 바꾸지 않는다.

      python test_scan_round372_fixes.py
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

print("=" * 72)
print("  스캔 372라운드 회귀 — 없는 status 컬럼 쿼리로 /api/admins·/api/notices 가 죽던 결함")
print("=" * 72)

print("\n[1] 소스 확인")
i0 = APP_SRC.index("def api_admins_list():")
i1 = APP_SRC.index("\n@app.post(\"/api/admins\")")
admins_body = APP_SRC[i0:i1]
chk("status_col=None" in admins_body,
    "★★★★★ api_admins_list(): _sq/_sqp 호출에 status_col=None 이 명시됐다")

i2 = APP_SRC.index("def api_notices():")
i3 = APP_SRC.index("\n@app.post(\"/api/notices\")")
notices_body = APP_SRC[i2:i3]
chk("status_col=None" in notices_body,
    "★★★★★ api_notices(): _sq/_sqp 호출에 status_col=None 이 명시됐다")

print("\n[2] 실행 — 실제 Flask 서버로 ?status= 쿼리스트링을 붙여 재현")
_tmpdir = tempfile.mkdtemp(prefix="round372_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    now = DB.now()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r372admin','x','검증','최고관리자')")
    conn.execute("INSERT INTO notices(title,body,audience,pinned,created_at) "
                 "VALUES('첫번째 공지','본문A','전체',0,?)", (now,))
    conn.execute("INSERT INTO notices(title,body,audience,pinned,created_at) "
                 "VALUES('두번째 공지','본문B','전체',0,?)", (now,))
    conn.commit()
    conn.close()

    admin = A.app.test_client()
    with admin.session_transaction() as sess:
        sess["admin"] = "r372admin"; sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = "r372-csrf"

    for path, label in (("/api/admins", "api_admins_list"), ("/api/notices", "api_notices")):
        try:
            r = admin.get(f"{path}?status=아무값")
            crashed = (r.status_code == 500)
        except Exception:                                          # noqa: BLE001
            crashed = True
            r = None
        chk(not crashed,
            f"★★★★★ {label}: ?status=아무값 을 붙여도 500/예외 없이 정상 응답해야 한다"
            f"(고치기 전엔 no such column: status 로 죽었다)",
            (r.status_code if r else "예외 발생"))
        if not crashed:
            chk(r.status_code == 200, f"  {label}: 실제로 200을 반환한다", r.status_code)

    # 대조군 — status 파라미터가 없는 정상 호출은 회귀 없이 그대로 동작
    r_admins = admin.get("/api/admins")
    chk(r_admins.status_code == 200, "  대조군 — /api/admins 파라미터 없는 정상 호출은 회귀없이 200", r_admins.status_code)
    r_notices = admin.get("/api/notices")
    chk(r_notices.status_code == 200 and len(r_notices.get_json() or []) == 2,
        "  대조군 — /api/notices 파라미터 없는 정상 호출은 회귀없이 공지 2건 그대로 반환",
        (r_notices.status_code, r_notices.get_json()))

    # 대조군 — status_col=None 으로 바꿔도 키워드 검색(q)은 여전히 정상 동작
    r_kw = admin.get("/api/notices?q=" + "첫번째")
    kw_data = r_kw.get_json() or []
    chk(r_kw.status_code == 200 and len(kw_data) == 1 and kw_data[0]["title"] == "첫번째 공지",
        "  대조군 — status_col=None 이후에도 ?q= 키워드검색은 정상 동작(공지 1건만 매치)",
        (r_kw.status_code, kw_data))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
