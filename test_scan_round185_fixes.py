# -*- coding: utf-8 -*-
"""스캔 185라운드 회귀 — 2차 경매 개시(open-auction)가 work_lots 이 비어
있으면 category 문자열을 '·' 로 직접 쪼개 넣던 결함.

  이 파일 자신의 case_trades()(7148·7150행)가 이미 두 번 금지한 방식이다 —
  WORK_MAJORS 12개 중 10개가 이름 안에 '·'를 품고 있어(유리·샷시·자동문 등),
  이렇게 쪼갠 조각 행은 이후 case_trades() 가 "work_lots 에 행이 있으면
  그대로 믿는다"며 곧이곧대로 돌려준다 — 도급 적법성 관문(compliance.py)이
  같은 공종의 다른 사건을 못 알아봐 분할의심을 도급가능으로 오판할 수 있다
  (건산법 §95조의2). 실측(운영DB): work_lots 는 현재 깨끗하지만(81건 전부
  정상), 사건 #614(26-73330, 유찰·미배정)가 to-dispatch 로 '접수'로 되돌아간
  뒤 이 경로를 다시 타면 그대로 재현되는 상태다.

      python test_scan_round185_fixes.py
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
print("  스캔 185라운드 회귀 — 2차 경매 개시가 공종을 '·'로 직접 쪼개던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_case_open_auction(cid):")
i1 = APP_SRC.index("\n@app.", i0 + 1)
body = APP_SRC[i0:i1]
chk('for cat in case_trades(conn, cid, c["category"]):' in body,
    "★★★ work_lots 생성이 이 파일 자신의 case_trades() 를 재사용한다"
    "(고치기 전엔 category.split('·') 로 직접 쪼갰다)")
chk('.split("·")' not in body,
    "★★★★ '·' 로 직접 쪼개던 코드가 완전히 사라졌다"
    "(case_trades()·dispatch._case_trades() 가 두 번 금지한 방식)")

# ============================================================
print("\n[2] 실행 — 실제 라우트로 사진없음(2-track) 경로를 재현")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round185_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','최고관리자')")
    iid = conn.execute(
        "INSERT INTO insurers(name,status,login_id,created_at) "
        "VALUES('R185보험사','활성','r185i',?)", (DB.now(),)).lastrowid

    def mk_case(tag, category):
        cid = conn.execute(
            "INSERT INTO cases(case_no,status,category,region,insurer_id,est_price,"
            "                  is_demo,created_at) "
            "VALUES(?,'접수',?,'서울',?,5000000,0,?)",
            (f"R185-{tag}", category, iid, DB.now())).lastrowid
        conn.execute(
            "INSERT INTO photos(case_id,uploader,uploader_role,rel_path,kind,created_at) "
            "VALUES(?,'검증','협력사','r185_test.jpg','착공전',?)", (cid, DB.now()))
        return cid

    # ① 단일 공종(이름 안에 '·' 포함) — 한 줄 그대로 남아야 한다
    cid1 = mk_case("SINGLE", "유리·샷시·자동문")
    # ② 복합 사건 — case_trades() 의 원칙대로 "추측하지 않고" 빈 목록이어야 한다
    cid2 = mk_case("COMBO", "복합(가드레일·방호울타리 · 유리·샷시·자동문)")
    conn.commit()

    admin = A.app.test_client()
    atok = "r185-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = atok
    ahdr = {"X-CSRF-Token": atok}

    r1 = admin.post(f"/api/cases/{cid1}/open-auction",
                     json={"est_basis": "검증용 개시 근거 문구입니다"}, headers=ahdr)
    j1 = r1.get_json() or {}
    chk(r1.status_code == 200 and j1.get("ok") is True,
        "① 단일 공종 사건의 2차 경매 개시 자체는 성공한다", (r1.status_code, j1))

    lots1 = [row["category"] for row in conn.execute(
        "SELECT category FROM work_lots WHERE case_id=? ORDER BY id", (cid1,))]
    chk(lots1 == ["유리·샷시·자동문"],
        "★★★★ work_lots 가 공종 이름을 쪼개지 않고 원문 그대로 한 줄만 남긴다"
        "(고치기 전엔 ['유리','샷시','자동문'] 3줄로 조각났다)", lots1)

    trades1 = A.case_trades(conn, cid1, "유리·샷시·자동문")
    chk(trades1 == ["유리·샷시·자동문"],
        "★★★★ case_trades() 로 되짚어도 원래 공종 그대로 나온다"
        "(도급 적법성 관문·수배 매칭이 실제로 보는 값)", trades1)

    r2 = admin.post(f"/api/cases/{cid2}/open-auction",
                     json={"est_basis": "검증용 개시 근거 문구입니다"}, headers=ahdr)
    j2 = r2.get_json() or {}
    chk(r2.status_code == 200 and j2.get("ok") is True,
        "② 복합 사건의 2차 경매 개시 자체도 성공한다", (r2.status_code, j2))

    lots2 = [row["category"] for row in conn.execute(
        "SELECT category FROM work_lots WHERE case_id=? ORDER BY id", (cid2,))]
    chk(lots2 == [],
        "★★★ 복합 표시문자열은 추측해 쪼개지 않고 빈 목록으로 남긴다"
        "(고치기 전엔 ['복합(가드레일','방호울타리','유리','샷시','자동문)'] 처럼 "
        "5조각으로 깨졌다)", lots2)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드185 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
