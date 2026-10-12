# -*- coding: utf-8 -*-
"""스캔 248라운드 회귀 — 입점신청(도입문의 아님) 접수·승인 파이프라인 결함 3건
   (admin.js leads/apps 화면 Agent 병렬조사로 발견).

  [1] 공개 입점신청 폼(apply_partner.html — "가장 흔한 유입 경로", app.py 자신의
      주석)에 상시 인력 수(staff_count) 입력칸이 아예 없었다. 서버는 이미
      "1인 사업자는 접수·승인 둘 다 막는다"는 정책(app.py 5262행·7110행)을
      갖고 있는데, 그 검사가 보는 값이 이 폼에서는 절대 채워질 수 없어(항상
      None) 실제로는 한 번도 걸린 적이 없었다 — 두 관문 다 무력화된 채였다.
      관리자 직접접수 폼(admin.js appIntakeForm)이 이미 쓰는 같은 입력방식을
      그대로 옮기되, 본인이 직접 적는 폼이라 필수로 받는다.

  [2] 승인 관문(api_application_update)에 사업자번호 중복확인이 없었다 —
      형제(api_application_create, 직접접수 전용)는 이미 하는데, 실제로 업체가
      만들어지는 곳(공개폼·직접접수 두 경로가 모두 거쳐가는 유일한 지점)엔
      없었다. 표기만 다른 상호나 10분 창을 벗어난 재신청이 승인되면 같은
      사업자번호로 활성 업체가 두 개(정산·입찰 자격이 갈라진 채) 생길 수
      있었다. 승인 직전에 사업자번호로 활성 업체를 대조해 막는다.

  [3] appDetail() 의 서류검토·승인·반려 버튼이 등급 무관하게 항상 그려졌다 —
      PATCH /api/applications/<id> 는 메모만 저장할 때도 포함해 전부
      require_role("중간관리자") 인데, 형제 화면들(admins·set·estbands·boq,
      246·247라운드)은 이미 자기차단을 받았다. 하위관리자가 메모를 쓰고
      아무 버튼이나 눌러야만 403을 만나던 것을 myRank() 로 미리 막는다.

  [4] (부수 발견) run_all_tests.py 의 test_otp.py 가 실서버 필요 목록(HTTP)이
      아니라 서버불필요 목록(UNIT)에 잘못 들어 있었다 — 이번 라운드 배터리를
      돌리다 실제로 겪음(연결거부로 실패). test_otp.py 는 BASE(기본
      127.0.0.1:8799)로 진짜 로그인·OTP확인까지 하는 HTTP 테스트라 --quick
      배터리(서버 없이 도는 UNIT만 실행하고 즉시 끝남)에서는 이 세션
      232~247라운드 내내 매번 서버연결거부를 "OTP 결함"처럼 오보해 왔다.
      HTTP 목록으로 옮겨 --quick 은 건너뛰고 전체실행에서만 preflight·
      레이트리밋 보호를 받으며 돌게 정정.

      python test_scan_round248_fixes.py
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


APPLY_HTML = read("templates/apply_partner.html")
ADMIN_JS = read("static/admin.js")
APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 248라운드 회귀 — 입점신청 1인사업자 누락·중복승인·등급게이트")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk('id="staff_count"' in APPLY_HTML and 'type="number"' in APPLY_HTML,
    "★★★★ apply_partner.html 에 상시 인력 수 입력칸이 생겼다")
chk("staff_count:val('staff_count')" in APPLY_HTML,
    "★★★★ submitForm() 이 그 값을 실제로 POST 본문에 싣는다")

i0 = APP_SRC.index("def api_application_update(")
i1 = APP_SRC.index("\n\n@app.", i0)
approve_body = APP_SRC[i0:i1]
chk('"code": "DUP_BIZNO"' in approve_body,
    "★★★★ 승인 관문에 사업자번호 중복확인이 생겼다")
chk("SELECT name FROM partners WHERE biz_no=? AND status='활성'" in approve_body,
    "STEP 형제(api_application_create)와 같은 조건으로 대조한다")

i2 = ADMIN_JS.index("function appDetail(")
i3 = ADMIN_JS.index("\nasync function appAct(", i2)
appdetail_body = ADMIN_JS[i2:i3]
chk("(approved || myRank() < 2)?''" in appdetail_body,
    "★★★★ 심사 버튼(서류검토·승인·반려)이 myRank()<2 이면 스스로 가려진다")
chk("id=\"anote\"${myRank()<2?' readonly':''}" in appdetail_body,
    "STEP 메모칸도 등급 미달이면 읽기전용으로 바뀐다(쓸 수 없는데 쓰게 두지 않는다)")

RUNNER = read("run_all_tests.py")
_iu = RUNNER.index("UNIT = [")
_iu_end = RUNNER.index("\nHTTP = [", _iu)
_ih = RUNNER.index("HTTP = [")
_ih_end = RUNNER.index("\n#  ── 자기 서버를 직접 띄우는 것", _ih)
chk('"test_otp.py"' not in RUNNER[_iu:_iu_end],
    "★★★★ test_otp.py 가 서버불필요(UNIT) 목록에서 빠졌다")
chk('"test_otp.py"' in RUNNER[_ih:_ih_end],
    "★★★★ test_otp.py 가 서버필요(HTTP) 목록으로 옮겨졌다"
    "(--quick 이 매번 오탐하던 원인)")

# ============================================================
print("\n[2] 실행 — Flask 실서버로 실제 시나리오 검증")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round248_")
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
                 "VALUES('r248mid','x','검증','중간관리자')")
    conn.commit(); conn.close()
    mid = A.app.test_client()
    tok = "r248-csrf"
    with mid.session_transaction() as sess:
        sess["admin"] = "r248mid"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    #  ── (a) 새 폼이 실제로 보내는 대로 staff_count=0 이면 접수 자체가 막힌다 ──
    ra = A.app.test_client().post("/api/applications", json={
        "company": "R248-1인업체", "phone": "010-1111-2222", "staff_count": "0",
        "agree_privacy": True})
    chk(ra.status_code == 400 and ra.get_json().get("code") == "SOLO",
        "★★★★ staff_count=0(1인 사업자)이면 새 폼 그대로 보내도 접수가 거부된다"
        "(고치기 전엔 이 값 자체를 보낼 방법이 없어 이 검사가 죽어 있었다)",
        ra.get_json())

    #  ── (b) 정상 인력 수는 그대로 접수된다(과잉차단 아님) ──
    rb = A.app.test_client().post("/api/applications", json={
        "company": "R248-정상업체", "phone": "010-3333-4444", "staff_count": "5",
        "agree_privacy": True})
    chk(rb.status_code == 200 and rb.get_json().get("ok"),
        "STEP 정상 인력 수(5명)는 그대로 접수된다", rb.get_json())

    #  ── (c) 사업자번호 중복 승인 방지 ──
    #  ⚠ [429라운드] 이 값들은 국세청 검사식(valid_biz_no) 체크섬을 실제로
    #    통과하는 값이어야 한다 — 429라운드가 이 승인 관문에 체크섬 재검증을
    #    추가해, 원래 쓰던 임의 순번('1234567890' 등)은 이제 DUP_BIZNO(409)가
    #    아니라 체크섬 오류(400)로 먼저 막혀 이 테스트의 취지(중복확인 자체)를
    #    더는 검증하지 못했다 — 실제로 유효한 값으로 교체.
    conn = DB.get_db()
    conn.execute("INSERT INTO partners(name,partner_type,status,biz_no) "
                 "VALUES('R248기존업체','시공사','활성','1111111104')")
    aid = conn.execute(
        "INSERT INTO partner_applications(company,biz_no,phone,status,created_at) "
        "VALUES('R248새신청(표기다름)','1111111104','010-5555-6666','신규',datetime('now'))").lastrowid
    conn.commit(); conn.close()

    rc = mid.patch(f"/api/applications/{aid}", json={"status": "승인"}, headers=hdr)
    chk(rc.status_code == 409 and rc.get_json().get("code") == "DUP_BIZNO",
        "★★★★ 이미 등록된 사업자번호와 같은 신청은 승인이 거부된다"
        "(고치기 전엔 승인 관문에 이 대조가 없어 활성 업체가 두 개 생길 수 있었다)",
        rc.get_json())
    conn = DB.get_db()
    n_active = conn.execute(
        "SELECT COUNT(*) c FROM partners WHERE biz_no='1111111104' AND status='활성'"
    ).fetchone()["c"]
    conn.close()
    chk(n_active == 1, "STEP 거부된 시도로 업체가 추가 생성되지 않았다(여전히 1개)", n_active)

    #  ── (d) 대조군 — 다른 사업자번호는 정상 승인된다 ──
    conn = DB.get_db()
    aid2 = conn.execute(
        "INSERT INTO partner_applications(company,biz_no,phone,status,major,created_at) "
        "VALUES('R248다른업체','2222222208','010-7777-8888','신규','금속',datetime('now'))").lastrowid
    conn.commit(); conn.close()
    rd = mid.patch(f"/api/applications/{aid2}", json={"status": "승인"}, headers=hdr)
    chk(rd.status_code == 200 and rd.get_json().get("ok"),
        "STEP 대조군 — 겹치지 않는 사업자번호는 정상 승인된다(과잉차단 아님)",
        rd.get_json())
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드248 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
