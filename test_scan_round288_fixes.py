# -*- coding: utf-8 -*-
"""스캔 288라운드 회귀 — 입점신청 1인사업자 제외 정책 우회 결함 2건
   (공개 신청폼 apply_partner.html/apply_insurer.html 최초 정밀조사 — apply_insurer.html
   과 /api/leads 는 실측 결과 클린, apply_partner.html 의 백엔드 관문 3곳에서만
   정밀조사 Agent가 발견 후 독립 재검증).

  [1][심각] 공개 접수(api_create_application)·직접접수(api_application_create)·
      승인(api_application_update) 세 관문이 전부 `str(staff_count)=="0"` 또는
      `==0`(정확히 문자열/정수 0)만 봤다 — 값을 아예 안 보내거나(라운드248이
      고친 바로 그 우회를 필드명만 다시 두면 재현) 음수·이상값을 보내면
      전부 통과했다. 실측(Flask 실서버, staff_count 생략): 공개 폼 접수 200
      성공 → 승인까지 200 성공 → 상시인력 미확인 업체가 그대로 입찰 가능한
      활성 협력사가 됐다. 폼의 #staff_count 는 required 라 정상 제출이면
      항상 값이 있어야 하므로, **공개 접수**는 파싱된 staff_n 으로 없음·0·
      음수를 전부 막는다. **직접접수(전화·팩스)**는 admin.js 자신의 안내
      ("미입력 시 심사 때 확인하세요")대로 미입력은 일부러 허용하는 흐름이라
      명백히 잘못된 값(0·음수)만 막고, 최종 방어선인 **승인 관문**도 같은
      기준(미입력은 검토자 판단에 맡기고, 0·음수만 최종 차단)으로 통일한다.

  [2] staff_count 가 API 응답(SELECT *)에는 이미 있는데 admin.js 심사 화면
      (appDetail()) 어디에도 안 보였다 — 목록·상세모달·엑셀 내보내기 전부.
      승인 버튼을 누르는 사람이 정작 그 값을 볼 방법이 없어, 직접접수의
      "심사 때 확인하세요" 안내 자체가 무의미했다. 상세모달에 상시 인력
      값을 보여주도록 추가(미확인/1인사업자/정상 세 갈래로 눈에 띄게).

  ⚠ [1]은 Flask 실서버(A.app.test_client())+격리 DB 로, [2]는 admin.js 를
    Node.js 로 직접 실행해 검증한다(이 세션의 admin.js 검증 표준 방식 — 다른
    세션이 이 폴더에서 이미 별도 dev 서버를 띄우고 있어 브라우저 확인은
    이번 라운드의 표준 검증 경로가 아니다).

      python test_scan_round288_fixes.py
"""
import io
import json
import os
import subprocess
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
ADMIN_JS = read("static/admin.js")

print("=" * 72)
print("  스캔 288라운드 회귀 — 입점신청 1인사업자 정책 우회(관문 3곳)")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i1 = APP_SRC.index("def api_create_application(")
i1_end = APP_SRC.index("\n\n\n", i1)
body1 = APP_SRC[i1:i1_end]
chk("staff_n is None or staff_n < 1" in body1,
    "★★★★★ 공개 접수가 미입력·음수를 전부 막는다(고치기 전엔 문자열 '0' 만 봤다)")

i2 = APP_SRC.index("def api_application_create(")
i2_end = APP_SRC.index("\n\n\n", i2)
body2 = APP_SRC[i2:i2_end]
chk("staff_n is not None and staff_n < 1" in body2,
    "★★★★ 직접접수는 미입력은 허용하되(안내와 일치) 0·음수만 막는다")

i3 = APP_SRC.index("def api_application_update(")
i3_end = APP_SRC.index("\n\n\n", i3)
body3 = APP_SRC[i3:i3_end]
chk("_sc is not None and _sc < 1" in body3,
    "★★★★★ 승인 관문도 미입력은 검토자 판단에 맡기고 0·음수만 최종 차단한다"
    "(고치기 전엔 ==0 만 봐서 음수가 그대로 승인됐다)")

i4 = ADMIN_JS.index("function appDetail(")
i4_end = ADMIN_JS.index("\nasync function appAct(", i4)
body4 = ADMIN_JS[i4:i4_end]
chk("staff_count" in body4,
    "★★★★ 심사 상세모달이 상시 인력(staff_count)을 실제로 보여준다"
    "(고치기 전엔 API 응답에 있어도 화면 어디에도 안 보였다)")

# ============================================================
print("\n[2] 실행 — Flask 실서버+격리 DB 로 세 관문 전부 재현")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round288_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB                                                  # noqa: E402
    DB.init_db()
    import app as A                                                   # noqa: E402

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r288mid','x','검증','중간관리자')")
    conn.commit()
    conn.close()
    mid = A.app.test_client()
    tok = "r288-csrf"
    with mid.session_transaction() as sess:
        sess["admin"] = "r288mid"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    # ── (a) 공개 접수 — staff_count 생략(라운드248 우회 재현) ──
    ra = A.app.test_client().post("/api/applications", json={
        "company": "R288-공개-생략", "phone": "010-0001-0001", "agree_privacy": True})
    chk(ra.status_code == 400 and ra.get_json().get("code") == "SOLO",
        "★★★★★★ 공개 접수: staff_count 를 아예 안 보내면 거부된다"
        "(고치기 전엔 200 성공 — 라운드248이 막았던 것과 같은 우회가 필드명만"
        " 다시 살아 있었다)", ra.get_json())

    rb = A.app.test_client().post("/api/applications", json={
        "company": "R288-공개-음수", "phone": "010-0001-0002",
        "staff_count": "-1", "agree_privacy": True})
    chk(rb.status_code == 400 and rb.get_json().get("code") == "SOLO",
        "★★★★★ 공개 접수: staff_count=-1 도 거부된다(고치기 전엔 그대로 통과)",
        rb.get_json())

    rc0 = A.app.test_client().post("/api/applications", json={
        "company": "R288-공개-0", "phone": "010-0001-0003",
        "staff_count": "0", "agree_privacy": True})
    chk(rc0.status_code == 400 and rc0.get_json().get("code") == "SOLO",
        "STEP 회귀 없음 — staff_count=0 은 여전히 거부된다", rc0.get_json())

    rd = A.app.test_client().post("/api/applications", json={
        "company": "R288-공개-정상", "phone": "010-0001-0004",
        "staff_count": "5", "agree_privacy": True})
    chk(rd.status_code == 200 and rd.get_json().get("ok"),
        "STEP 회귀 없음 — 정상 인력 수(5명)는 그대로 접수된다", rd.get_json())

    # ── (b) 직접접수 — staff_count 생략은 "심사 때 확인" 흐름이라 허용돼야 함 ──
    re_ = mid.post("/api/applications/manual", json={
        "company": "R288-직접-생략", "phone": "010-0002-0001", "major": "누수·배관·설비"},
        headers=hdr)
    chk(re_.status_code == 200 and re_.get_json().get("ok"),
        "★★★★★ 직접접수: staff_count 생략은 여전히 허용된다"
        "(admin.js 안내 '미입력 시 심사 때 확인하세요'와 일치 — 과잉차단 아님)",
        re_.get_json())

    rf = mid.post("/api/applications/manual", json={
        "company": "R288-직접-음수", "phone": "010-0002-0002", "major": "누수·배관·설비",
        "staff_count": "-2"}, headers=hdr)
    chk(rf.status_code == 400 and rf.get_json().get("code") == "SOLO",
        "★★★★ 직접접수: staff_count=-2 는 거부된다(고치기 전엔 통과)", rf.get_json())

    # ── (c) 승인 관문 — DB 에 직접 꽂아 각 시나리오를 정확히 통제 ──
    def _mk_app(company, staff_count):
        conn = DB.get_db()
        cols = "company,phone,status,created_at,staff_count"
        aid = conn.execute(
            f"INSERT INTO {'partner_applications'}({cols}) "
            "VALUES(?,?,?,datetime('now'),?)",
            (company, "010-9999-0000", "신규", staff_count)).lastrowid
        conn.commit()
        conn.close()
        return aid

    aid_null = _mk_app("R288-승인-미입력", None)
    r_null = mid.patch(f"/api/applications/{aid_null}", json={"status": "승인"}, headers=hdr)
    chk(r_null.status_code == 200 and r_null.get_json().get("ok"),
        "★★★★★ 승인 관문: staff_count 미입력(NULL)인 직접접수 건은 승인이 막히지 "
        "않는다(검토자가 상세모달에서 직접 보고 판단 — 과잉차단으로 직접접수 "
        "흐름을 깨지 않는다)", r_null.get_json())

    aid_neg = _mk_app("R288-승인-음수", -1)
    r_neg = mid.patch(f"/api/applications/{aid_neg}", json={"status": "승인"}, headers=hdr)
    chk(r_neg.status_code == 409 and r_neg.get_json().get("code") == "SOLO",
        "★★★★★★ 승인 관문: staff_count=-1 은 최종 차단된다"
        "(고치기 전엔 ==0 만 봐서 음수가 그대로 승인 — 무자격 업체가 활성 "
        "협력사가 됐다)", r_neg.get_json())

    aid_zero = _mk_app("R288-승인-0", 0)
    r_zero = mid.patch(f"/api/applications/{aid_zero}", json={"status": "승인"}, headers=hdr)
    chk(r_zero.status_code == 409 and r_zero.get_json().get("code") == "SOLO",
        "STEP 회귀 없음 — staff_count=0 은 여전히 최종 차단된다", r_zero.get_json())

    aid_ok = _mk_app("R288-승인-정상", 4)
    r_ok = mid.patch(f"/api/applications/{aid_ok}", json={"status": "승인"}, headers=hdr)
    chk(r_ok.status_code == 200 and r_ok.get_json().get("ok"),
        "STEP 회귀 없음 — staff_count=4 인 정상 건은 그대로 승인된다", r_ok.get_json())

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드288 [2] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — admin.js 상세모달이 실제로 상시 인력을 렌더링하는가(Node.js)")
# ------------------------------------------------------------
try:
    node_script = f"""
const fs = require('fs');
const src = fs.readFileSync({json.dumps(os.path.join(HERE, "static", "admin.js"))}, 'utf-8');
const i0 = src.indexOf('function appDetail(');
const i1 = src.indexOf('\\nasync function appAct(', i0);
let body = src.slice(i0, i1);

// appDetail() 안에서 쓰는 보조함수 최소 스텁
const esc = (s) => String(s == null ? '' : s);
const myRank = () => 3;
const statusPill = (s) => s;
let _rendered = null;
const openModal = (html) => {{ _rendered = html; }};
window_apps_store = [];
const window = {{ _apps: window_apps_store }};

body = body.replace('function appDetail(id){{', 'function appDetail(id, esc, myRank, statusPill, openModal, window){{');
eval(body);

const cases = [
  {{staff_count: null,  expect: '미확인'}},
  {{staff_count: 0,     expect: '1인 사업자'}},
  {{staff_count: 3,     expect: '3명'}},
];
let ok = true;
for (const c of cases) {{
  window_apps_store.length = 0;
  window_apps_store.push({{id: 1, company: 'T', partner_type: '시공사', major: '누수·배관·설비',
    phone: '010', status: '신규', staff_count: c.staff_count}});
  _rendered = null;
  appDetail(1, esc, myRank, statusPill, openModal, window);
  const found = _rendered && _rendered.includes(c.expect);
  console.log((found ? 'OK  ' : 'FAIL') + ' staff_count=' + c.staff_count + ' -> expect "' + c.expect + '"');
  if (!found) ok = false;
}}
process.exit(ok ? 0 : 1);
"""
    node_path = os.path.join(_tmpdir, "check_appdetail.js")
    io.open(node_path, "w", encoding="utf-8").write(node_script)
    r = subprocess.run(["node", node_path], capture_output=True, text=True, encoding="utf-8", timeout=30)
    print(r.stdout)
    chk(r.returncode == 0,
        "★★★★ appDetail() 이 미확인/1인사업자/정상 인력 수를 각각 올바르게 렌더링한다",
        r.stdout + r.stderr)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드288 [3] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
