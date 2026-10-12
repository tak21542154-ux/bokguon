# -*- coding: utf-8 -*-
"""스캔 164라운드 회귀 — 마케팅 캠페인의 '수신동의 없음' 제외 건수가
저장되지 않고 사라지던 결함.

  _campaign_recipients() 는 ok·no_contact·opted·no_consent 넷을 돌려주는데,
  campaigns 표에는 skipped_optout·skipped_nocontact 컬럼만 있고
  skipped_noconsent 컬럼 자체가 없었다. 미리보기(/api/campaigns/preview)
  응답에는 잠깐 나타났다가, 캠페인을 저장(POST /api/campaigns)하는 순간
  그 숫자는 영구히 사라졌다 — "수신동의가 없어 몇 곳을 뺐는가"는
  정보통신망법 §50① 위반 여부를 소명할 유일한 근거인데, 나중에 캠페인을
  다시 열어봐도(감사 상황에서 가장 필요한 바로 그 순간) 그 숫자만 없었다.

      python test_scan_round164_fixes.py
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


DB_SRC = read("db.py")
APP_SRC = read("app.py")
JS_SRC = read("static/admin.js")

print("=" * 72)
print("  스캔 164라운드 회귀 — 캠페인 '수신동의 없음' 제외 건수 소실")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk('("campaigns", "skipped_noconsent", "INTEGER DEFAULT 0")' in DB_SRC,
    "★★★ campaigns 표에 skipped_noconsent 컬럼 마이그레이션이 등록됐다")

i0 = APP_SRC.index("def api_campaign_create(")
i1 = APP_SRC.index("\n@app.", i0 + 1)
body = APP_SRC[i0:i1]
chk("skipped_optout,skipped_nocontact,skipped_noconsent," in body,
    "★★★ INSERT 열 목록에 skipped_noconsent 가 들어갔다")
chk("opted, no_contact, no_consent," in body,
    "★★★ INSERT 값 목록에 no_consent 가 들어갔다")

chk("${c.skipped_noconsent?` · 동의없음 ${c.skipped_noconsent}`:''}" in JS_SRC,
    "★★★ 캠페인 목록·상세 화면이 동의없음 건수를 렌더링한다(2곳)")
chk(JS_SRC.count("${c.skipped_noconsent?` · 동의없음 ${c.skipped_noconsent}`:''}") == 2,
    "★ 목록 행 + 상세 모달 2곳 모두 반영됐다")

# ============================================================
print("\n[2] 실행 — 캠페인 생성 후에도 동의없음 건수가 그대로 남아있는가")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round164_")
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
                 "VALUES('admin','x','검증','최고관리자')")
    #  ① 동의 있음 — 발송대상(ok)
    conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,email,"
        "                     email_opt_out,email_consent,created_at) "
        "VALUES('R164동의O','시공사','활성','가드레일','서울','ok@r164.test',0,1,?)", (DB.now(),))
    #  ② 동의 없음 — no_consent 로 빠져야 한다(이번 결함의 핵심)
    conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,email,"
        "                     email_opt_out,email_consent,created_at) "
        "VALUES('R164동의X','시공사','활성','가드레일','서울','no@r164.test',0,0,?)", (DB.now(),))
    #  ③ 수신거부 — opted 로 빠진다(동의없음과 구분되는 대조군)
    conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,email,"
        "                     email_opt_out,email_consent,created_at) "
        "VALUES('R164거부','시공사','활성','가드레일','서울','opt@r164.test',1,1,?)", (DB.now(),))
    #  ④ 연락처 없음 — no_contact 로 빠진다(대조군)
    conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,email,"
        "                     email_opt_out,email_consent,created_at) "
        "VALUES('R164무연락처','시공사','활성','가드레일','서울','',0,1,?)", (DB.now(),))
    conn.commit(); conn.close()

    admin = A.app.test_client()
    tok = "r164-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}
    body = {"title": "R164캠페인", "channel": "메일", "subject": "제목", "body": "본문 {업체명}",
            "audience": "전체"}

    r1 = admin.post("/api/campaigns/preview", json=body, headers=hdr)
    pv = r1.get_json()
    chk(r1.status_code == 200 and pv.get("skipped_noconsent") == 1,
        "STEP 미리보기가 동의없음 1건을 정확히 낸다(회귀 아님, 기존에도 됐다)", pv)

    r2 = admin.post("/api/campaigns", json=body, headers=hdr)
    cr = r2.get_json()
    chk(r2.status_code == 200 and cr.get("ok"),
        "STEP 캠페인 생성이 200/ok 다", (r2.status_code, cr))
    chk(cr.get("skipped_noconsent") == 1,
        "★ 생성 직후 응답에도 동의없음 1건이 담긴다", cr)
    camp_id = cr.get("id")

    conn = DB.get_db()
    row = dict(conn.execute(
        "SELECT skipped_optout, skipped_nocontact, skipped_noconsent FROM campaigns WHERE id=?",
        (camp_id,)).fetchone())
    conn.close()
    chk(row["skipped_optout"] == 1 and row["skipped_nocontact"] == 1,
        "★ (사전조건) 형제 컬럼(거부·연락처없음)은 원래도 저장됐다", row)
    chk(row["skipped_noconsent"] == 1,
        "★★★ 동의없음 1건이 DB 에 그대로 저장된다"
        "(고치기 전엔 이 컬럼 자체가 없어 저장할 수 없었다)", row)

    #  ★★★ 다시 열어봐도(목록·상세) 사라지지 않고 그대로 보이는가 — 이게 이번 버그의 핵심
    r3 = admin.get("/api/campaigns")
    lst = [c for c in r3.get_json() if c["id"] == camp_id]
    chk(len(lst) == 1 and lst[0].get("skipped_noconsent") == 1,
        "★★★ 목록(/api/campaigns) 재조회에서도 동의없음 건수가 그대로 보인다"
        "(고치기 전엔 저장 자체가 안 돼 나중엔 확인할 방법이 없었다)",
        lst[0] if lst else None)

    r4 = admin.get(f"/api/campaigns/{camp_id}")
    dt = r4.get_json()
    chk(dt.get("campaign", {}).get("skipped_noconsent") == 1,
        "★★★ 상세(/api/campaigns/<id>) 재조회에서도 동의없음 건수가 그대로 보인다", dt)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드164 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
