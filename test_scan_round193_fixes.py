# -*- coding: utf-8 -*-
"""스캔 193라운드 회귀 — 완료보고(api_partner_complete)의 사진 경고가 이용약관
제6조①이 요구하는 4종(착공 전·시공 중·완료·자재 영수증) 중 '완료' 하나만
확인하던 결함.

  약관은 네 종류를 다 요구하는데, 코드는 '완료' 종류가 없을 때만 경고하고
  착공 전·시공 중·영수증 누락은 어떤 신호도 주지 않았다. kind 는 AI 분류라
  틀릴 수 있으므로(코드 자신의 기존 주석) 이번에도 **막지는 않는다** — 기존
  '완료' 경고와 같은 원칙으로 넷 다 확인해 알리기만 한다.

      python test_scan_round193_fixes.py
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
print("  스캔 193라운드 회귀 — 완료보고 사진경고가 4종 중 '완료'만 보던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_partner_complete(cid):")
i1 = APP_SRC.index("\ndef ", i0 + 1)
body = APP_SRC[i0:i1]
chk("kind='착공전'" in body and "kind='시공중'" in body
    and "kind='완료'" in body and "kind='영수증'" in body,
    "★★★★ 완료보고 관문이 이용약관 제6조가 요구하는 4종을 전부 센다"
    "(고치기 전엔 '완료' 하나만 셌다)")
chk("_missing" in body,
    "★★★ 없는 종류만 골라 경고 문구에 담는다")

# ============================================================
print("\n[2] 실행 — 협력사가 '완료' 사진 1장만 올리고 완료보고하면 나머지 "
      "3종 누락이 경고에 나타나고, 4종을 모두 갖추면 경고가 사라진다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round193_")
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
    now = DB.now()
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R193업체','시공사','활성')"
    ).lastrowid
    iid = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('R193보험','활성')").lastrowid

    def mk_case(tag):
        return conn.execute(
            "INSERT INTO cases(case_no,status,category,region,partner_id,insurer_id,is_demo) "
            "VALUES(?,'시공중','유리','서울',?,?,0)", (f"R193-{tag}", pid, iid)).lastrowid

    def add_photo(cid, kind):
        conn.execute(
            "INSERT INTO photos(case_id,partner_id,uploader,uploader_role,rel_path,orig_name,"
            "                   mime,ext,size,sha256,kind,review_status,created_at) "
            "VALUES(?,?,'R193업체','협력사',?,?,'image/jpeg','jpg',1,?,?,'대기',?)",
            (cid, pid, f"{kind}.jpg", f"{kind}.jpg", f"sha-{kind}-{cid}", kind, now))

    # ① '완료' 사진 1장뿐인 사건 — 나머지 3종이 누락으로 보고돼야 한다
    cid1 = mk_case("PARTIAL")
    add_photo(cid1, "완료")
    # ② 4종을 모두 갖춘 사건 — 경고가 없어야 한다(회귀 없음)
    cid2 = mk_case("FULL")
    for k in ("착공전", "시공중", "완료", "영수증"):
        add_photo(cid2, k)
    conn.commit()

    partner_c = A.app.test_client()
    tok = "r193-partner-csrf"
    with partner_c.session_transaction() as sess:
        sess["partner_id"] = pid; sess["partner_name"] = "R193업체"; sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    r1 = partner_c.post(f"/api/partner/cases/{cid1}/complete", headers=hdr, json={})
    j1 = r1.get_json() or {}
    r2 = partner_c.post(f"/api/partner/cases/{cid2}/complete", headers=hdr, json={})
    j2 = r2.get_json() or {}

    chk(r1.status_code == 200 and j1.get("ok") is True,
        "① 사진 1장뿐이어도 완료보고 자체는 막히지 않는다(경고만 한다)",
        (r1.status_code, j1))
    warn1 = j1.get("warn") or ""
    chk(all(w in warn1 for w in ("착공 전", "시공 중", "영수증")),
        "★★★★ 누락된 3종(착공 전·시공 중·영수증)이 전부 경고에 나타난다"
        "(고치기 전엔 '완료'만 봐서 이 경우엔 경고 자체가 아예 없었다)", warn1)
    chk("완료" not in warn1,
        "있는 종류('완료')는 누락 목록에 안 들어간다", warn1)

    chk(r2.status_code == 200 and j2.get("ok") is True,
        "② 4종을 다 갖춘 사건도 정상 성공한다", (r2.status_code, j2))
    chk(not j2.get("warn"),
        "★★★ 4종을 모두 갖추면 경고가 없다(회귀 없음)", j2.get("warn"))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드193 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
