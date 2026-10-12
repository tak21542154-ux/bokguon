# -*- coding: utf-8 -*-
"""스캔 332라운드 회귀 — api_notice_create()(app.py:14372, POST /api/notices)
   가 공지 제목·본문을 무제한 길이로 저장하던 결함[중간], 이 세션 사상 첫
   정밀조사한 정밀조사 Agent가 발견(331라운드가 세운 "저장 전 자르기" 관례
   확대조사 — note/memo/comment/message/content/detail/instruction/reason/
   feedback류 자유텍스트 필드를 app.py·dispatch.py·compliance.py·db.py
   스키마 전수로 훑음. insurer_leads/partner_applications의 message·note,
   defect_photos.note, change_orders.reason/note, field_agreements.note,
   schedule_events.memo, happy_calls.feedback, photos.reject_reason,
   dispatches.fail_reason(항상 내부 리터럴)은 전부 [:200~2000]으로 이미
   정상 방어됨을 확인 — 정당한 클린 결과. compliance.py override_reason은
   315라운드가 이미 "재조사 금지"로 정리한 별개 사안이라 제외).

   `@require_admin`(등급 무관 — 632행, 하위관리자도 통과)만 걸린 이 라우트는
   `title`·`body`를 그대로 `INSERT INTO notices`(14380행)와 `DB.log`
   (14383행)에 넣었다 — 같은 파일에 이미 확립된 "title 은 100~120자로
   자른다" 관례(8892행 [:120], 13741·13774행 [:100])에서 이 라우트만
   빠졌다(331라운드의 "필드 이름은 같은데 이 라우트만 검색망에 안 걸렸다"
   류가 아니라, 이번엔 "이름도 관례도 똑같은데 이 라우트 하나만 적용을
   깜빡함" — 13772행 주석이 하자 접수(title·content)에서 이미 겪은 것과
   토씨까지 같은 실패모드: "무제한 저장 → DB 비대화 + 여러 화면 렌더링
   지연"). 게다가 `GET /api/notices`(14342행)는 `SELECT *`를 LIMIT 없이
   그대로 내려주므로, 공지 하나가 부풀면 관리자·협력사·보험사 포털 전체가
   대시보드를 열 때마다 그 큰 문자열을 매번 그대로 받는다(자기유발 DoS —
   클라이언트가 이스케이프해 렌더링하므로 XSS는 아님). 형제와 같은 상한
   (title[:100]·body[:2000])을 적용.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_scratch = tempfile.mkdtemp(prefix="bokguon_r332_")
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
print("  스캔 332라운드 회귀 — 공지 등록 title·body 무제한 저장")
print("=" * 74)

import db as DB  # noqa: E402
DB.init_db(seed_demo=True)
import app as A  # noqa: E402

conn = DB.get_db()
app_client = A.app.test_client()
_tok = "r332-admin-csrf"
with app_client.session_transaction() as sess:
    #  ⚠ 일부러 최하위 등급 — @require_admin 은 등급을 안 가리므로
    #    하위관리자도 이 라우트를 그대로 쓸 수 있다는 게 결함의 핵심.
    sess["admin"] = "staff"
    sess["admin_role"] = "하위관리자"
    sess["_csrf"] = _tok
_hdr = {"X-CSRF-Token": _tok}
LONG_TITLE = "가" * 2000
LONG_BODY = "나" * 5000

print("\n[1] 실행 — 하위관리자가 실제로 매우 긴 제목·본문으로 공지를 등록")
r1 = app_client.post("/api/notices", headers=_hdr,
                      json={"title": LONG_TITLE, "body": LONG_BODY, "audience": "전체"})
j1 = r1.get_json() or {}
chk(r1.status_code == 200 and j1.get("ok") is True,
    "  공지 등록 자체는 정상 200/ok", (r1.status_code, r1.get_data(as_text=True)[:200]))
nid = j1.get("id")

row = conn.execute("SELECT title, body FROM notices WHERE id=?", (nid,)).fetchone()
chk(row is not None, "  notices 행이 실제로 생성된다")
if row:
    chk(LONG_TITLE not in row["title"] and len(row["title"]) <= 100,
        "★★★★★ notices.title 에 2000자 원문이 그대로 안 들어간다"
        "(고치기 전엔 길이제한이 없어 그대로 들어갔다)",
        (len(row["title"]), row["title"][:30]))
    chk(LONG_BODY not in row["body"] and len(row["body"]) <= 2000,
        "★★★★ notices.body 도 5000자 원문이 그대로 안 들어간다",
        (len(row["body"]), row["body"][:30]))

log_row = conn.execute(
    "SELECT detail FROM activity_log WHERE action='공지 등록' ORDER BY id DESC LIMIT 1").fetchone()
chk(log_row is not None and LONG_TITLE not in (log_row["detail"] or ""),
    "  감사로그 detail 에도 2000자 원문 제목이 그대로 안 들어간다",
    log_row["detail"][:30] if log_row else None)

print("\n[2] 실행 — 실제 GET /api/notices 로도 잘린 값만 내려온다(읽기 경로까지 확인)")
r2 = app_client.get("/api/notices", headers=_hdr)
chk(r2.status_code == 200, "  공지 목록 조회 자체는 정상 200", r2.status_code)
items = r2.get_json() or []
mine = next((it for it in items if it.get("id") == nid), None)
chk(mine is not None and len(mine.get("title") or "") <= 100 and len(mine.get("body") or "") <= 2000,
    "★★★ 목록 응답에서도 잘린 제목·본문만 내려온다(저장 시점에 이미 잘렸으므로 당연한 결과지만 실제 응답으로 재확인)",
    mine)

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
