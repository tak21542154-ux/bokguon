# -*- coding: utf-8 -*-
"""스캔 149라운드 회귀 — 웹훅 서명 비밀키(webhook_secret)가 사람에게 닿는
경로가 어디에도 없던 결함.

  서버는 나가는 모든 웹훅을 HMAC-SHA256으로 서명하고(app.py _webhook_send,
  X-Bokguon-Signature 헤더), 그 검증용 webhook_secret 을
  api_insurer_webhook_set 의 응답으로 실제로 내려준다. 그런데 admin.js
  의 insWhSave 는 그 응답을 통째로 버려 화면 어디에도 안 보였고(API 키는
  같은 자리에서 insApiKey 가 잘 보여주는 것과 대비), 발주처에게 그대로
  건네는 연동 안내서(insurer_api_guide.html)에도 서명 검증 방법이 전혀
  없었다 — 보안장치는 구현됐는데 그걸 써야 할 쪽에 닿을 방법이 없었다.

      python test_scan_round149_fixes.py
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


JS_SRC = read("static/admin.js")

print("=" * 72)
print("  스캔 149라운드 회귀 — 웹훅 서명 비밀키 노출 경로 부재")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — admin.js")
# ------------------------------------------------------------
i_wh = JS_SRC.index("ACT.insWhSave = async (a) => {")
i_wh_end = JS_SRC.index("\n  ACT.insWhTest", i_wh + 1)
wh_body = JS_SRC[i_wh:i_wh_end]
chk("const r = await api('PATCH', `/api/insurers/${_n(a)}/webhook`" in wh_body,
    "★★★ insWhSave 가 이제 PATCH 응답을 변수로 받는다(예전엔 버렸다)")
chk("r.webhook_secret" in wh_body and "openModal(" in wh_body,
    "★★★ webhook_secret 을 모달로 화면에 보여준다(API 키와 동등한 대우)")
chk("if (_url && r && r.webhook_secret)" in wh_body,
    "★ 주소를 해제(빈 값)할 땐 표시하지 않는다(쓸 곳 없는 값을 굳이 안 보여줌)")

# ============================================================
print("\n[2] 실행 — 연동 안내서(/docs/insurer-api)가 서명 검증법을 실제로 담아 보낸다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round149_")
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
        "INSERT INTO insurers(name,org_type,status) VALUES('R149보험','손해보험','활성')").lastrowid
    conn.commit()

    admin = A.app.test_client()
    tok = "r149-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = tok

    r = admin.get("/docs/insurer-api")
    chk(r.status_code == 200, "STEP 연동 안내서 페이지가 200으로 렌더링된다", r.status_code)
    body = r.get_data(as_text=True)
    chk("X-Bokguon-Signature" in body,
        "★★★ 안내서에 서명 헤더 이름이 실제로 렌더링된다"
        "(고치기 전엔 이 문서에 서명 관련 언급이 전혀 없었다)")
    chk("HMAC-SHA256" in body,
        "★★★ 안내서에 서명 알고리즘(HMAC-SHA256)이 실제로 렌더링된다")
    chk(">403<" in body,
        "★ 안내서 오류표에 403(연동 꺼짐) 행이 추가됐다(실제 코드가 내는 코드인데 문서에 없었다)")

    #  실제 발급된 값이 화면에 노출되는 자리(admin.js 쪽)와 대비해, 서버가
    #  정말로 webhook_secret 을 만들어 응답에 담는지도 재확인한다(전제조건).
    #  ⚠ 8.8.8.8 은 _webhook_host_safe 자신의 회귀테스트(round84)가 이미 쓰는
    #    "평범한 공인 IPv4" 대조군이다 — 도메인은 이 샌드박스에서 DNS 해석이
    #    안 될 수 있어 IP 리터럴을 그대로 재사용한다.
    r2 = admin.patch(f"/api/insurers/{iid}/webhook",
                     json={"webhook_url": "https://8.8.8.8/hook"},
                     headers={"X-CSRF-Token": tok})
    chk(r2.status_code == 200 and bool(r2.get_json().get("webhook_secret")),
        "★ (사전조건) 서버가 실제로 webhook_secret 을 응답에 담는다"
        "(admin.js 가 이제 이 값을 버리지 않고 보여줄 대상)", r2.get_json())

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드149 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
