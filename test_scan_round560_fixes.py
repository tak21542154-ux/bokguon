# -*- coding: utf-8 -*-
"""스캔 560라운드 회귀 — 관리자 콘솔 사건등록(api_case_create)이 발주 보험사 본인에게
   "사건접수" 알림을 전혀 보내지 않던 결함.

   조사 배경 — 오케스트레이터가 이번 라운드에 준 새 각도 중 "서로 다른 행위자
   유형(관리자·보험사 등)이 같은 행을 동시에 건드리는 경우"를 조사하는 과정에서,
   그 전 단계로 두 사건등록 경로(_create_case vs api_case_create)를 다시 대조했다
   — round556 이 이 정확히 같은 함수 쌍을 INSERT 컬럼 기준으로 대조해 source
   누락을 잡은 바로 그 자리인데, 이번엔 컬럼이 아니라 notify() 호출을 전수 대조했다.

   발견 — _create_case(보험사 포털·v1 API 공용, app.py 4078행)는 사진 유무와
   무관하게 두 분기 모두에서 발주 보험사 본인에게 "사건접수" 알림을 보낸다
   (audience_type="insurer", 4186행·4212행). 그런데 api_case_create(관리자 콘솔
   전용, POST /api/cases, app.py 11268행)는 바로 위에 남아 있는 주석(①②③)이
   스스로 밝히듯 "보험사 경로(api_insurer_case_create)가 대조군"이라며 협력사·
   운영팀 알림 결함 3건을 그 대조군을 보고 고쳤으면서도, 정작 그 대조군이
   보내는 "보험사 본인" 알림 자체는 옮기지 않았다 — 대상이 협력사·운영팀이지
   보험사가 아니라 그 수정의 시야 밖에 있었던 것으로 보인다.

   영향 — 관리자 콘솔(전화·팩스로 받은 사건을 담당자가 대신 등록하는 통로)로
   등록된 사건은, 사진 유무와 무관하게, 그 사건의 소유자인 보험사의 포털
   알림함(GET /api/insurer/notifications, audience_type='insurer' AND
   insurer_id=? 로 거른다)에 단 한 건도 뜨지 않는다. 협력사·운영팀은 새 공고를
   알게 되는데 정작 사건의 주인인 보험사만 모른다 — 포털을 직접 열어 사건
   목록을 뒤지기 전에는 자기 사건이 접수됐는지조차 알 방법이 없었다.

   고침(app.py, api_case_create) — n_match 계산 뒤·DB.log() 바로 앞, no_photo
   분기와 무관한 공통 지점에 _create_case 와 같은 문구의
   notify(audience_type="insurer", insurer_id=insurer_id, ...) 호출 1개를
   추가했다(분기마다 따로 넣지 않고 한 곳에서 메시지만 갈라 정합을 지켰다).

   같이 검토했으나 이번 결함과 무관한 것 — round556 이 이미 note/warranty_months
   컬럼 드리프트를 조사해 "실질적 차이 없음"으로 결론 낸 바 있다(그 라운드
   테스트 파일 참고). 이번 결함은 컬럼이 아니라 notify() 호출 누락이라 별개다.

   이 회귀테스트는 ONLY 안전한 기법만 쓴다 — on-disk app.py 는 조회만 하고,
   "되돌리기" 증명은 옛(보험사 알림이 없던) api_case_create 꼬리부를 별도
   문자열로 재구성해 exec()으로 스크래치 DB에 직접 실행해 인과관계를 실측한다.
   그 다음 실제 라이브 라우트(Flask test_client)로 수정 후 두 분기 모두와,
   보험사 본인 계정으로 실제 알림함 API를 불러 종단까지 확인한다.

       python test_scan_round560_fixes.py
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


print("=" * 72)
print("  스캔 560라운드 회귀 — 관리자 사건등록(api_case_create)의 보험사 알림 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — app.py 가 실제로 고쳐졌는가")
# ------------------------------------------------------------
APP_SRC = read("app.py")
_ac_start = APP_SRC.index("def api_case_create()")
_ac_end = APP_SRC.index("\ndef ", _ac_start + 10)
AC_SRC = APP_SRC[_ac_start:_ac_end]

chk('audience_type="insurer", insurer_id=insurer_id, case_id=cid, url="/app/insurer")' in AC_SRC,
    "★★★★★ api_case_create 안에 보험사 본인 대상 notify() 호출이 추가됐다")
chk('notify(conn, "사건접수", "웹", insurer_name,' in AC_SRC,
    "★★★★★ 알림 종류·대상 표시명이 형제(_create_case)와 같은 '사건접수'/insurer_name 이다")
chk(AC_SRC.count('audience_type="insurer"') == 1,
    "  이 함수 안에 보험사 알림 호출이 정확히 1곳(두 분기의 공통 지점)이다 — "
    "분기마다 따로 넣어 문구가 갈라지는 사고를 피했다")
# 회귀 방지 — 이번 수정이 손대면 안 되는 기존 협력사·운영팀 알림은 그대로 남아 있어야 한다
chk('audience_type="all-partner", case_id=cid, url="/app/partner"' in AC_SRC
    and 'audience_type="admin", case_id=cid, url="/admin#partners"' in AC_SRC,
    "  회귀 방지: 기존 협력사·운영팀 알림(공고오픈·참여업체없음)은 그대로다")

# ============================================================
print("\n[2] 준비 — 스크래치 DB(오늘자 실제 스키마) + 관리자 계정")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round560_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB
DB.init_db()
import app as A

conn = DB.get_db()
conn.execute("INSERT INTO admins(username,password_hash,name,role) "
             "VALUES('admin','x','검증','중간관리자')")
conn.commit()


def _mkinsurer(tag):
    conn.execute("INSERT INTO insurers(name,status) VALUES(?,'활성')", (f"{tag}보험사",))
    conn.commit()
    return conn.execute("SELECT id, name FROM insurers WHERE name=?",
                         (f"{tag}보험사",)).fetchone()


def _insurer_feed(iid):
    return A.rows(conn.execute(
        "SELECT id,ntype,message,url,case_id FROM notifications "
        "WHERE audience_type='insurer' AND insurer_id=? ORDER BY id", (iid,)))


# ============================================================
print("\n[3] 되돌리기 — api_case_create의 옛(보험사 알림 없는) 꼬리부를 오늘자 스키마에")
print("    그대로 실행하면 실제로 보험사 알림함이 텅 비는가 (인과관계 실측)")
# ------------------------------------------------------------
ins_old = _mkinsurer("R560OLD")
conn.execute("BEGIN IMMEDIATE")
cur = conn.execute(
    """INSERT INTO cases(case_no,insurer,insurer_id,category,region,address,urgent,is_composite,
                         status,est_price,low_price,manager,source,lat,lng,geo_src,created_at,status_at)
       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    ("R560OLD-1", ins_old["name"], ins_old["id"], "유리·샷시·자동문", "", "", 0, 0,
     "접수", 0, 0, "자동", "관리자수동", None, None, None, DB.now(), DB.now()))
cid_old = cur.lastrowid
conn.commit()
#  ⚠ api_case_create 에 실제로 있었던 옛(이번 라운드 이전) 꼬리부만 문자열로
#    재구성한다 — on-disk 파일은 전혀 건드리지 않는다(안전 규칙: in-memory
#    재구성 + exec 만 쓴다). no_photo 갈래(관리자수동 등록에서 가장 흔한 경로)를 재현.
OLD_TAIL_SRC = (
    "conn.execute(\"UPDATE cases SET intake_type='사진없음' WHERE id=?\", (cid,))\n"
    "n_match = conn.execute(\n"
    "    \"SELECT COUNT(*) FROM partners WHERE partner_type='시행사' AND status='활성' \"\n"
    "    \"  AND COALESCE(login_id,'') <> ''\").fetchone()[0]\n"
    "DB.log(conn, '검증', '공고·사건 등록', case_no)\n"
)
exec(OLD_TAIL_SRC, {}, {"conn": conn, "DB": DB, "cid": cid_old, "case_no": "R560OLD-1"})
conn.commit()
chk(_insurer_feed(ins_old["id"]) == [],
    "★★★★★ 보험사 알림 호출이 없는 옛 꼬리부를 그대로 실행하면 보험사 알림함이 "
    "실제로 텅 빈다(수정 전 실제 증상을 인과관계로 증명)",
    _insurer_feed(ins_old["id"]))

# ============================================================
print("\n[4] 실행 — 실제 라이브 라우트(POST /api/cases)로 지금 두 분기 모두")
print("    보험사 본인이 '사건접수' 알림을 받는가")
# ------------------------------------------------------------
admin_c = A.app.test_client()
_tok = "r560-admin-csrf"
with admin_c.session_transaction() as sess:
    sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
    sess["_csrf"] = _tok

ins_np = _mkinsurer("R560NP")     # 사진없음 분기
r1 = admin_c.post("/api/cases", headers={"X-CSRF-Token": _tok}, json={
    "case_no": "R560NP-1", "category": "유리·샷시·자동문",
    "insurer_id": ins_np["id"], "insurer": ins_np["name"], "no_photo": True,
})
rd1 = r1.get_json() or {}
chk(r1.status_code == 200 and rd1.get("ok"),
    "사진없음 분기 — 실제 라우트가 200으로 사건을 만든다", (r1.status_code, rd1))
feed_np = _insurer_feed(ins_np["id"])
chk(len(feed_np) == 1 and feed_np[0]["ntype"] == "사건접수"
    and feed_np[0]["case_id"] == rd1.get("id") and feed_np[0]["url"] == "/app/insurer",
    "★★★★★ 사진없음 분기 — 보험사 알림함에 '사건접수' 알림이 정확히 1건 남는다",
    feed_np)
chk(bool(feed_np) and "사진 없는 사고로 접수됐습니다" in feed_np[0]["message"],
    "  사진없음 분기 — 문구가 형제(_create_case)의 사진없음 문구와 같다",
    feed_np)

ins_wp = _mkinsurer("R560WP")     # 사진있음(공고 오픈) 분기
r2 = admin_c.post("/api/cases", headers={"X-CSRF-Token": _tok}, json={
    "case_no": "R560WP-1", "category": "유리·샷시·자동문",
    "insurer_id": ins_wp["id"], "insurer": ins_wp["name"], "no_photo": False,
    "est_price": "1,000,000",
})
rd2 = r2.get_json() or {}
chk(r2.status_code == 200 and rd2.get("ok"),
    "사진있음 분기 — 실제 라우트가 200으로 사건을 만든다", (r2.status_code, rd2))
feed_wp = _insurer_feed(ins_wp["id"])
chk(len(feed_wp) == 1 and feed_wp[0]["ntype"] == "사건접수"
    and feed_wp[0]["case_id"] == rd2.get("id"),
    "★★★★★ 사진있음 분기 — 보험사 알림함에도 '사건접수' 알림이 정확히 1건 남는다",
    feed_wp)
chk(bool(feed_wp) and "입찰 공고가 열렸습니다" in feed_wp[0]["message"],
    "  사진있음 분기 — 문구가 형제(_create_case)의 사진있음 문구와 같다(매칭 시행사 수 포함)",
    feed_wp)

# ============================================================
print("\n[5] 종단 — 그 보험사 본인이 실제로 로그인해 자기 알림함 API를 부르면 보이는가")
# ------------------------------------------------------------
insurer_c = A.app.test_client()
with insurer_c.session_transaction() as sess:
    sess["insurer_id"] = ins_np["id"]; sess["insurer_name"] = ins_np["name"]
r3 = insurer_c.get("/api/insurer/notifications")
j3 = r3.get_json() or {}
msgs = [n.get("message", "") for n in (j3.get("notifications") or [])]
chk(r3.status_code == 200 and any("R560NP-1" in m for m in msgs) and (j3.get("unread") or 0) >= 1,
    "★★★★★ 보험사 본인 계정으로 조회한 실제 알림함 API(/api/insurer/notifications)에도 "
    "방금 그 사건이 뜬다(unread 배지도 함께 올라간다)",
    j3)

# ============================================================
print("\n[6] 정합성 — 형제 경로(_create_case, 포털·API)는 지금도 그대로 보험사에게 보내는가")
# ------------------------------------------------------------
ins_por = _mkinsurer("R560POR")
conn.execute("BEGIN IMMEDIATE")
res_por = A._create_case(conn, ins_por["id"], ins_por["name"],
                          {"case_no": "R560POR-1", "category": "유리·샷시·자동문",
                           "no_photo": True}, "포털")
conn.commit()
feed_por = _insurer_feed(ins_por["id"])
chk(len(feed_por) == 1 and feed_por[0]["ntype"] == "사건접수",
    "  회귀 방지: 형제 경로(_create_case)는 이번 수정과 무관하게 여전히 보험사에게 보낸다",
    feed_por)

# ── 정리 ──────────────────────────────────────────────────────
for _no in ("R560OLD-1", "R560NP-1", "R560WP-1", "R560POR-1"):
    _row = conn.execute("SELECT id FROM cases WHERE case_no=?", (_no,)).fetchone()
    if _row:
        conn.execute("DELETE FROM work_lots WHERE case_id=?", (_row["id"],))
        conn.execute("DELETE FROM notifications WHERE case_id=?", (_row["id"],))
        conn.execute("DELETE FROM auctions WHERE case_id=?", (_row["id"],))
        conn.execute("DELETE FROM cases WHERE id=?", (_row["id"],))
for _tag in ("R560OLD", "R560NP", "R560WP", "R560POR"):
    conn.execute("DELETE FROM insurers WHERE name=?", (f"{_tag}보험사",))
conn.execute("DELETE FROM admins WHERE username='admin'")
conn.commit()
conn.close()

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
