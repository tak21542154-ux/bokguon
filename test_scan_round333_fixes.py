# -*- coding: utf-8 -*-
"""스캔 333라운드 회귀 — api_campaign_create()(app.py:8887, POST /api/campaigns)
   가 audience·filter_json 을 무제한 길이로 저장하던 결함[중간, 2건], round333
   배경조사 Agent가 발견(round332 자신이 검증 중 우연히 스친 뒤 범위 밖이라
   미조치로 남긴 단서 — test_scan_round332_fixes.py 상단 주석 참조).

   같은 함수 안 형제 title[:120](8892행)·subject[:200](8893행)은 이미 잘리는데
   audience(옛 8941행)·filter_json(옛 8941행)만 빠져 있었다 — filter_json 은
   더 심해서 원본 요청 d 를 통째로(json.dumps(d)) 덤프해 이미 자른 title·
   subject·body 원문을 한 번 더 그대로 끼워 넣었다. db.py 스키마 주석이
   명시하는 filter_json 의 목적("수신자 산출 조건(재현용)")과 실제 유일한
   소비자 _campaign_recipients()(app.py:8782)를 grep 으로 직접 대조한 결과
   그 함수가 실제로 읽는 건 channel/ptype/major/region/no_login 5개뿐이고,
   filter_json 자체는 어떤 코드도 프로그램적으로 다시 읽지 않는(순수 기록용)
   것도 확인됨 — 그래서 그 5개만 남기도록 축소해도 어떤 소비자도 안 깨진다.
   `GET /api/campaigns`(8874행, LIMIT 100)·`GET /api/campaigns/<id>`(8965행)
   둘 다 `@require_admin`(등급 무관)이라 round332 의 notices 와 같은 구조의
   자기유발 DoS 로 이어질 수 있었다(캠페인 이력은 삭제 라우트가 없어 한 번
   부풀면 영구적으로 남는다 — cancel 은 status 만 바꾸고 body·filter_json 은
   그대로 둠, grep 재확인). 회귀테스트는 실제 Flask test_client 로 중간관리자
   세션(이 라우트의 실제 등급 요건)이 audience 1000자·major/region 각 500자
   ·body 5000자로 실제 캠페인을 등록해 (a) DB 컬럼(audience·filter_json·body)
   전부 원문이 그대로 안 들어감 (b) filter_json 을 실제로 JSON 파싱해 키가
   정확히 5개(channel/ptype/major/region/no_login)뿐이고 title·subject·body
   원문이 어디에도 안 섞여 있음 (c) 실제 GET 목록·상세 응답에서도 잘린
   값만 내려옴을 읽기 경로까지 실측.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_scratch = tempfile.mkdtemp(prefix="bokguon_r333_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_scratch, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"

PASS = FAIL = 0
FAILED = []


def chk(cond, msg, detail=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {msg}")
    else:
        FAIL += 1
        FAILED.append(msg)
        print(f"  [FAIL] {msg}" + (f"   {detail}" if detail else ""))


print("=" * 74)
print("  스캔 333라운드 회귀 — 마케팅 캠페인 audience·filter_json 무제한 저장")
print("=" * 74)

import db as DB  # noqa: E402
DB.init_db(seed_demo=True)
import app as A  # noqa: E402

LONG_BODY = "나" * 5000
LONG_AUDIENCE = "다" * 1000
LONG_MAJOR = "마" * 500
LONG_REGION = "바" * 500

conn = DB.get_db()
#  발송대상(ok)이 최소 1곳 있어야 NO_RECIPIENT 로 조기반환되지 않는다
#  (164라운드가 세운 검증된 픽스처 패턴 재사용 — email 채널·동의·비거부·연락처보유).
#  ⚠ major는 SQL LIKE 사전필터, region은 region_matches() 사후필터라(8809·8822행,
#    grep 재확인) 이 씨앗업체의 major·region을 아래 요청이 보낼 것과 **똑같은
#    긴 문자열**로 맞춰야 필터를 실제로 통과해 recipient 로 잡힌다(짧은 값을
#    쓰면 필터에 걸려 NO_RECIPIENT 가 나고, 그러면 캠페인 행 자체가 안 만들어져
#    audience·filter_json 저장 결과를 확인할 수 없다).
conn.execute(
    "INSERT INTO partners(name,partner_type,status,category,major,region,email,"
    "                     email_opt_out,email_consent,created_at) "
    "VALUES('R333수신자','시공사','활성','가드레일',?,?,'ok@r333.test',0,1,?)",
    (LONG_MAJOR, LONG_REGION, DB.now()))
conn.commit()

app_client = A.app.test_client()
_tok = "r333-admin-csrf"
with app_client.session_transaction() as sess:
    #  "staff" 는 db.py seed_demo() 가 실제로 만드는 계정(중간관리자) — require_role
    #  이 _account_alive() 로 admins 표를 실제 조회하므로 존재하지 않는 이름은 401.
    sess["admin"] = "staff"
    sess["admin_role"] = "중간관리자"   # 이 라우트의 실제 최소 등급
    sess["_csrf"] = _tok
_hdr = {"X-CSRF-Token": _tok}

print("\n[1] 실행 — 중간관리자가 실제로 매우 긴 audience·major·region·body 로 캠페인 등록")
r1 = app_client.post("/api/campaigns", headers=_hdr, json={
    "title": "R333캠페인", "channel": "메일", "subject": "제목",
    "body": LONG_BODY, "audience": LONG_AUDIENCE,
    "ptype": "시공사", "major": LONG_MAJOR, "region": LONG_REGION, "no_login": False,
})
j1 = r1.get_json() or {}
chk(r1.status_code == 200 and j1.get("ok") is True,
    "  캠페인 등록 자체는 정상 200/ok", (r1.status_code, r1.get_data(as_text=True)[:200]))
chk(j1.get("count", 0) >= 1,
    "  (사전조건) 씨앗으로 심은 수신자가 실제로 잡혀 NO_RECIPIENT 로 조기반환되지 않았다", j1)
cid = j1.get("id")

row = conn.execute(
    "SELECT audience, filter_json, body FROM campaigns WHERE id=?", (cid,)).fetchone()
chk(row is not None, "  campaigns 행이 실제로 생성된다")
if row:
    chk(LONG_AUDIENCE not in row["audience"] and len(row["audience"]) <= 200,
        "★★★★★ campaigns.audience 에 1000자 원문이 그대로 안 들어간다"
        "(고치기 전엔 길이제한이 없어 그대로 들어갔다)",
        (len(row["audience"]), row["audience"][:30]))
    chk(LONG_BODY not in row["body"],
        "  (사전조건) body 는 형제 필드로 이미 [:2000] 적용됨 — 5000자 원문이 안 들어감",
        row["body"][:30])

    fj_raw = row["filter_json"] or ""
    chk(LONG_BODY not in fj_raw and LONG_AUDIENCE not in fj_raw,
        "★★★★★ filter_json 에 원본 body·audience 원문이 통째로 안 새 나간다"
        "(고치기 전엔 json.dumps(d) 가 요청 전체를 그대로 덤프했다)")
    try:
        fj = json.loads(fj_raw)
    except Exception as e:                                              # noqa: BLE001
        fj = None
        chk(False, "  filter_json 이 유효한 JSON 이다", f"{type(e).__name__} {e}")
    if fj is not None:
        chk(set(fj.keys()) == {"channel", "ptype", "major", "region", "no_login"},
            "★★★ filter_json 키가 정확히 실제 소비자(_campaign_recipients)가 쓰는 5개뿐이다"
            "(title·subject·body·audience 등 다른 요청 필드가 안 섞여 있다)",
            sorted(fj.keys()))
        chk(len(fj.get("major") or "") <= 120 and len(fj.get("region") or "") <= 120,
            "★★★★ filter_json 안의 major·region 도 각각 500자 원문이 그대로 안 들어간다",
            (len(fj.get("major") or ""), len(fj.get("region") or "")))
        chk(fj.get("channel") == "메일" and fj.get("ptype") == "시공사"
            and fj.get("no_login") is False,
            "  filter_json 이 실제 수신자 재현에 필요한 값은 그대로 보존한다(과잉축소 아님)", fj)

print("\n[2] 실행 — 실제 GET 목록·상세 로도 잘린 값만 내려온다(읽기 경로까지 확인)")
r2 = app_client.get("/api/campaigns", headers=_hdr)
chk(r2.status_code == 200, "  캠페인 목록 조회 자체는 정상 200", r2.status_code)
items = r2.get_json() or []
mine = next((it for it in items if it.get("id") == cid), None)
chk(mine is not None and len(mine.get("audience") or "") <= 200,
    "★★★ 목록 응답에서도 잘린 audience 만 내려온다(저장 시점에 이미 잘렸으므로 당연한 결과지만 실측 재확인)",
    mine.get("audience", "")[:30] if mine else None)

r3 = app_client.get(f"/api/campaigns/{cid}", headers=_hdr)
chk(r3.status_code == 200, "  캠페인 상세 조회 자체는 정상 200", r3.status_code)
detail = (r3.get_json() or {}).get("campaign") or {}
chk(LONG_AUDIENCE not in (detail.get("audience") or "")
    and LONG_BODY not in (detail.get("filter_json") or ""),
    "★★★ 상세 응답에서도 잘린 값만 내려오고 filter_json 에 body 원문이 안 새 나간다")

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
