# -*- coding: utf-8 -*-
"""스캔 251라운드 회귀 — 발송함(outbox)·캠페인(campaigns) 화면 결함 4건
   (admin.js 아웃박스·캠페인 화면군 Agent 병렬조사로 발견, 전부 독립 재검증 후 수정).

  [1] 캠페인 생성·취소(+새 캠페인/취소 버튼)에 등급 게이트가 없었다.
      api_campaign_preview·api_campaign_create·api_campaign_cancel 전부
      require_role(중간관리자)인데 화면은 등급 무관하게 그려, 하위관리자가
      폼을 다 채우거나 취소 확인창을 누른 뒤에야 403을 만났다.

  [2] 발송함의 지금발송·목록발송·테스트발송 버튼도 같은 유형 — d.send_enabled
      (팝빌 스위치)만 보고 그렸지 등급은 안 봤다. 세 라우트 모두
      require_role(중간관리자)이고, 특히 테스트발송은 임의 번호로 실제
      문자가 나가는 동작이라 더 위험했다(형제 obHandled·obReopen 은
      require_admin=등급무관이라 원래도 게이트가 없는 게 맞음 — 그대로 둠).

  [3] api_campaign_create() 에 중복클릭 방어가 전혀 없었다 — cmSave() 는
      버튼 비활성화도 디바운스도 안 하고(전역 디스패처에도 이런 방어 자체가
      없음) 즉시 POST 한다. "발송 대기열 등록"을 두 번 누르면(느린 응답
      재클릭) 제목·채널·본문이 완전히 같은 캠페인 두 건이 각자 수신자
      스냅샷까지 따로 생겨, 실발송이 연동되는 순간 그대로 이중발송으로
      이어질 구조였다. 형제(/api/partners/invite, 라운드250)와 같은
      "방금 처리한 것과 같으면 새로 안 만든다" 관용구로 막는다.

  [4] api_campaign_preview() 의 sample_body 가 실제 저장 시 항상 붙는
      AD_FOOTER·비메일채널 AD_PREFIX 를 빼먹었다 — 이 미리보기는 정보통신망법
      §50 표기의무 준수를 확인하려고 있는 건데, 정작 그 표기 자체를 안
      보여줬다(바로 옆 subject_preview 는 이미 AD_PREFIX 를 반영하는데
      본문만 놓침). 저장 시와 같은 규칙으로 통일.

      python test_scan_round251_fixes.py
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


ADMIN_JS = read("static/admin.js")
APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 251라운드 회귀 — 캠페인·발송함 등급게이트·중복생성·미리보기표기")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = ADMIN_JS.index("VIEWS.campaigns = async () => {")
i1 = ADMIN_JS.index("\nasync function cmDetail(", i0)
cm_body = ADMIN_JS[i0:i1]
chk("myRank()>=2?'<button class=\"btn p sm\" data-act=\"cmNew\">" in cm_body,
    "★★★★ + 새 캠페인 버튼이 myRank()>=2 로 게이트됐다")
chk("(c.status==='발송대기' && myRank()>=2)?" in cm_body,
    "★★★★ 취소 버튼도 myRank()>=2 로 게이트됐다")

i2 = ADMIN_JS.index("VIEWS.outbox = async () => {")
i3 = ADMIN_JS.index('data-act="obTestSend"', i2)
ob_body = ADMIN_JS[i2:i3 + 30]
chk("(d.send_enabled && myRank()>=2)?" in ob_body,
    "★★★★ 지금발송·목록발송·테스트발송 버튼 3개가 myRank()>=2 로 함께 게이트됐다")

i4 = APP_SRC.index("def api_campaign_preview(")
i5 = APP_SRC.index("\n\n\n", i4)
prev_body = APP_SRC[i4:i5]
chk('sample = (sample if _ch == "메일" else AD_PREFIX + sample) + AD_FOOTER' in prev_body,
    "★★★★ 미리보기 본문이 저장 시와 같은 규칙(AD_PREFIX·AD_FOOTER)을 반영한다")

i6 = APP_SRC.index("def api_campaign_create(")
i7 = APP_SRC.index("\n\n\n", i6)
create_body = APP_SRC[i6:i7]
chk('"duplicate": True' in create_body and "-30 seconds" in create_body,
    "★★★★ 30초 안의 같은 제목·채널 재요청은 새로 만들지 않고 기존 것을 돌려준다")

# ============================================================
print("\n[2] 실행(Flask) — 중복생성 방지 · 미리보기 표기 실측")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round251_")
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
                 "VALUES('r251mid','x','검증','중간관리자')")
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r251low','x','검증하위','하위관리자')")
    conn.execute(
        "INSERT INTO partners(name,partner_type,status,email,email_opt_out,email_consent,"
        "phone,sms_opt_out,sms_consent,region) "
        "VALUES('R251업체','시공사','활성','r251@example.com',0,1,"
        "'010-2222-3333',0,1,'서울')")
    conn.commit(); conn.close()

    mid = A.app.test_client()
    tok = "r251-csrf"
    with mid.session_transaction() as sess:
        sess["admin"] = "r251mid"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    low = A.app.test_client()
    tok_low = "r251-csrf-low"
    with low.session_transaction() as sess:
        sess["admin"] = "r251low"; sess["admin_role"] = "하위관리자"; sess["admin_name"] = "검증하위"
        sess["_csrf"] = tok_low
    hdr_low = {"X-CSRF-Token": tok_low}

    #  ⚠ 미리보기(문자)는 시각 제한이 없어(api_campaign_preview 에 야간검사가 없다)
    #    그대로 쓰지만, 실제 생성(create)의 문자·알림톡은 21시~08시 발송을 막는
    #    기존 규칙(정보통신망법 §50③)에 걸린다 — 이 배터리가 새벽에도 돌 수 있으므로
    #    생성쪽 시나리오는 그 규칙의 적용을 안 받는 메일 채널로 검증한다(중복생성
    #    방지 자체는 채널과 무관한 로직이라 메일로 검증해도 결함 재현·수정 확인에
    #    지장이 없다).
    body_sms = {"title": "R251-미리보기용", "channel": "문자", "body": "{업체명}님께 안내드립니다"}
    body = {"title": "R251-테스트캠페인", "channel": "메일", "subject": "안내",
            "body": "{업체명}님께 안내드립니다"}

    #  ── (a) 하위관리자는 여전히 백엔드에서 403(화면 게이트와 별개로 서버가 최종 방어) ──
    r0 = low.post("/api/campaigns/preview", json=body_sms, headers=hdr_low)
    chk(r0.status_code == 403, "STEP 하위관리자는 캠페인 미리보기가 여전히 서버에서 막힌다(방어의 마지막 선)", r0.status_code)

    #  ── (b) 미리보기 — 문자 채널이면 본문에 (광고) 접두 + 발신자 정보 꼬리가 함께 보인다 ──
    rp = mid.post("/api/campaigns/preview", json=body_sms, headers=hdr)
    jp = rp.get_json()
    chk(rp.status_code == 200 and jp.get("count") == 1, "STEP 대상 1곳이 정상 산출된다", jp)
    chk((jp.get("sample_body") or "").startswith("(광고) "),
        "★★★★ 미리보기 본문에 (광고) 표기가 실제로 보인다(문자·알림톡)", jp.get("sample_body"))
    chk("올림포스네트웍스" in (jp.get("sample_body") or ""),
        "★★★★ 미리보기 본문에 발신자 정보 꼬리(AD_FOOTER)도 보인다", jp.get("sample_body"))

    #  ── (c) 같은 제목·채널로 곧바로 두 번 생성 요청(더블클릭 재현) → 캠페인 1개만 ──
    r1 = mid.post("/api/campaigns", json=body, headers=hdr)
    j1 = r1.get_json()
    chk(r1.status_code == 200 and j1.get("ok") and not j1.get("duplicate"),
        "STEP 첫 생성 요청은 정상적으로 새 캠페인을 만든다", j1)
    r2 = mid.post("/api/campaigns", json=body, headers=hdr)
    j2 = r2.get_json()
    chk(r2.status_code == 200 and j2.get("duplicate") and j2.get("id") == j1.get("id"),
        "★★★★★ 곧바로 같은 요청을 다시 보내도(더블클릭) 새 캠페인을 안 만들고 "
        "방금 것을 그대로 돌려준다", j2)

    conn = DB.get_db()
    n = conn.execute(
        "SELECT COUNT(*) c FROM campaigns WHERE title='R251-테스트캠페인'"
    ).fetchone()["c"]
    n_targets = conn.execute(
        "SELECT COUNT(*) c FROM campaign_targets WHERE campaign_id=?", (j1.get("id"),)
    ).fetchone()["c"]
    conn.close()
    chk(n == 1, "★★★★★ 실제 DB 에도 캠페인이 1건만 생성됐다(두 번째 클릭이 중복 insert 안 함)", n)
    chk(n_targets == 1, "STEP 수신자 스냅샷도 중복 생성되지 않았다", n_targets)

    #  ── (d) 대조군 — 제목이 다르면 정상적으로 별개 캠페인이 생성된다(과잉차단 아님) ──
    body2 = dict(body, title="R251-다른캠페인")
    r3 = mid.post("/api/campaigns", json=body2, headers=hdr)
    j3 = r3.get_json()
    chk(r3.status_code == 200 and j3.get("ok") and not j3.get("duplicate")
        and j3.get("id") != j1.get("id"),
        "STEP 대조군 — 제목이 다른 캠페인은 정상적으로 별개 생성된다(과잉차단 아님)", j3)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드251 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
