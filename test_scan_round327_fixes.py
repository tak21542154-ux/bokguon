# -*- coding: utf-8 -*-
"""스캔 327라운드 회귀 — api_insurer_apikey_issue()(app.py, POST
   /api/insurers/<id>/apikey)의 감사로그가 발급한 API 키의 실제 조각을
   평문으로 남기던 결함[심각], 이 세션 사상 첫 정밀조사한 정밀조사
   Agent가 발견(326라운드가 세운 "등급게이트 화면 vs 그 감사로그 등급
   불일치" 패턴을 다른 @require_role("최고관리자") 전용 함수 전체에
   적용 — 나머지 12개 후보는 직접 코드 대조 결과 전부 클린: 로그값이
   이미 동일 등급 화면에서 노출 중이거나(예: login_id) 애초에 민감정보가
   아니거나, webhook_secret·임시비밀번호는 어디서도 로그에 안 남음).

   `_gen_api_key()`(app.py:1849)가 만드는 `prefix`는
   `API_KEY_PREFIX("bok_live_", 9자) + raw[9:16]`, 즉 **실제 무작위
   키(secrets.token_urlsafe(32)) 앞 7글자를 그대로 포함**한다. 발급
   라우트(app.py:8333) 는 이 `prefix`를 `DB.log()` detail 에
   `f"{r['name']} ({prefix}…)"`로 그대로 남겼는데, 형제 함수 폐기
   (app.py:8349)·연동토글(app.py:8367)은 둘 다 기관명만 남기고 어떤
   키 조각도 안 남긴다 — 이 발급 함수만 예외. `api_insurer_api_status`
   (app.py:8299, 같은 최고관리자 전용)조차 상태조회 응답에서
   `api_key_prefix`를 `has_key` 불리언으로 낮춰 최고관리자에게도 원문
   prefix를 평소엔 안 보여주는데("이 키는 지금 한 번만 표시됩니다" —
   발급 응답에서 딱 한 번만), 감사로그(`/api/activity`,
   `/api/activity/export` — 326라운드가 확인한 대로 등급 무관
   `@require_admin`)를 통하면 하위관리자도 그 조각을 영구히 볼 수
   있었다 — 7글자(약 42비트)만으로 나머지 256비트 키를 뚫을 순 없지만,
   "한 번만 보여준다"는 이 코드베이스 자신의 원칙(관리자 임시비밀번호도
   같은 원칙으로 로그엔 계정명만 남긴다)을 감사로그가 조용히 깼다.
   형제와 같은 형식(기관명만)으로 통일.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_scratch = tempfile.mkdtemp(prefix="bokguon_r327_")
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
print("  스캔 327라운드 회귀 — API 키 발급 감사로그의 키 조각 노출")
print("=" * 74)

import db as DB  # noqa: E402
DB.init_db(seed_demo=True)
import app as A  # noqa: E402

print("\n[1] 준비 — 실제 보험사 1건 생성")
conn = DB.get_db()
cur = conn.execute(
    "INSERT INTO insurers(name, created_at) VALUES(?, ?)", ("R327테스트보험", DB.now()))
iid = cur.lastrowid
conn.commit()

app_client = A.app.test_client()
_tok = "r327-admin-csrf"
with app_client.session_transaction() as sess:
    sess["admin"] = "admin"
    sess["admin_role"] = "최고관리자"
    sess["_csrf"] = _tok
_hdr = {"X-CSRF-Token": _tok}

print("\n[2] 실행 — API 키를 실제로 발급한다")
r_issue = app_client.post(f"/api/insurers/{iid}/apikey", headers=_hdr, json={})
chk(r_issue.status_code == 200, "  API 키 발급 자체는 정상 200", r_issue.status_code)
body = r_issue.get_json()
raw_key = body.get("api_key") or ""
prefix = body.get("prefix") or ""
chk(bool(raw_key) and bool(prefix) and raw_key.startswith(prefix),
    "  응답에 원문 키·prefix가 정상적으로 함께 온다(응답에서 1회 노출은 의도된 설계)",
    (raw_key[:20], prefix))
secret_tail = prefix[len("bok_live_"):]  # prefix 안의 진짜 무작위 조각(7자)
chk(len(secret_tail) > 0, "  prefix 안에 실제 무작위 키 조각이 들어있음을 확인(재현 전제조건)",
    secret_tail)

log_row = conn.execute(
    "SELECT detail FROM activity_log WHERE action='API 키 발급' ORDER BY id DESC LIMIT 1").fetchone()
chk(log_row is not None, "  'API 키 발급' 감사로그가 실제로 남는다")
if log_row:
    chk(secret_tail not in log_row["detail"],
        "★★★★★ 감사로그 detail 에 실제 키 조각이 안 남는다"
        "(고치기 전엔 prefix 전체가 그대로 찍혔다)", log_row["detail"])
    chk(log_row["detail"] == "R327테스트보험",
        "  detail 은 형제(폐기·토글)와 같은 형식(기관명만)이다", log_row["detail"])

print("\n[3] 실행 — 형제 함수(폐기·연동토글)는 회귀 없이 그대로 기관명만 남긴다")
r_revoke = app_client.delete(f"/api/insurers/{iid}/apikey", headers=_hdr)
chk(r_revoke.status_code == 200, "  키 폐기 자체는 정상 200", r_revoke.status_code)
revoke_log = conn.execute(
    "SELECT detail FROM activity_log WHERE action='API 키 폐기' ORDER BY id DESC LIMIT 1").fetchone()
chk(revoke_log is not None and revoke_log["detail"] == "R327테스트보험",
    "  키 폐기 감사로그는 회귀 없이 기관명만 남는다(기존 동작)", revoke_log)

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
