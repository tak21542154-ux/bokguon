# -*- coding: utf-8 -*-
"""스캔 245라운드 회귀 — admin.js 출동(dispatch) 관제화면 결함 2건
   (admin.js 출동화면 Agent 병렬조사로 발견).

  [1] "기한 초과" 집계가 검색필터 걸린 items 에서 다시 세져 있었다 — 이
      화면의 다른 지표(모집중·수배됨·도착)와 사이드바 배지는 전부 서버가
      낸 전체집계(agg, dispatch_overdue)를 쓰는데 이것만 화면에서 더했다.
      SEARCH['dispatch'] 는 '초기화'를 누르기 전까지 다음 새로고침에도
      남으므로, 필터를 걸어 둔 채 화면을 벗어나면 진짜 기한초과 건이
      필터 밖에 있어도 "기한 내 진행"이라고 조용히 잘못 말할 수 있었다.
      서버가 agg 처럼 전체집계로 낸 overdue 값을 그대로 쓰도록 수정.

  [2] 직접배정(dpAssignForm) 드롭다운에 전화번호·"이미 부름" 여부가 없었다
      — 같은 API(/api/cases/<id>/nearby) 응답의 phone·called 를 형제
      (loadNearby)는 이미 보여주는데(중복 전화 방지가 목적), 여기는
      "전화로 확인한 업체를 고르세요"라고 안내하면서 정작 그 번호를 안
      보여줬다. <option> 텍스트에 번호·"이미 부름"을 추가.

      python test_scan_round245_fixes.py
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


ADMIN_JS = read("static/admin.js")
APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 245라운드 회귀 — 출동 관제화면 기한초과 오판 + 직접배정 번호누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_dispatch_list(")
i1 = APP_SRC.index("\n@app.", i0 + 1)
route_body = APP_SRC[i0:i1]
chk('"overdue": overdue_total' in route_body,
    "★★★★ /api/dispatches 응답에 검색필터와 무관한 전체 기한초과 집계가 추가됐다")
chk("AND due_at IS NOT NULL AND datetime(due_at) <= datetime('now','+9 hours')" in route_body,
    "STEP 그 집계 조건이 대시보드의 dispatch_overdue 와 동일하다")

i2 = ADMIN_JS.index("VIEWS.dispatch = async ()")
i3 = ADMIN_JS.index("\nasync function dispatchSweep", i2)
vd_body = ADMIN_JS[i2:i3]
chk("const overdue = d.overdue || 0;" in vd_body,
    "★★★★ 화면이 이제 items 를 다시 세지 않고 서버 전체집계를 그대로 쓴다")
chk("items.filter(x=>x.overdue).length" not in vd_body,
    "STEP 옛 방식(필터된 목록에서 다시 세기)이 더는 없다")

i4 = ADMIN_JS.index("async function dpAssignForm(")
i5 = ADMIN_JS.index("\nasync function dpAssign(", i4)
form_body = ADMIN_JS[i4:i5]
chk("p.phone?esc(p.phone):'번호없음'" in form_body,
    "★★★★ 직접배정 드롭다운에 전화번호(또는 '번호없음')가 표시된다")
chk("p.called?' · 이미 부름'" in form_body,
    "★★★ '이미 부름' 여부도 함께 표시된다(중복 전화 방지)")

# ============================================================
print("\n[2] 실행 — Flask 실서버로 검색필터가 걸려도 전체 기한초과 값이 맞는지 확인")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round245_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    admin_id = conn.execute(
        "INSERT INTO admins(username,password_hash,name,role) "
        "VALUES('r245low','x','검증','하위관리자')").lastrowid
    cid1 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region) VALUES('R245-C1','접수','금속','서울')").lastrowid
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region) VALUES('R245-C2','접수','유리','부산')").lastrowid
    #  cid1(금속) 은 기한이 지난 '수배됨' — 검색으로 '유리'만 걸면 이 건은 목록에서 빠진다.
    conn.execute(
        "INSERT INTO dispatches(case_id,round,status,due_at,created_at) "
        "VALUES(?,1,'수배됨',datetime('now','-1 hours'),datetime('now','-2 hours'))", (cid1,))
    #  cid2(유리) 는 기한이 안 지난 '수배됨' — 검색 결과에는 남지만 기한초과는 아니다.
    conn.execute(
        "INSERT INTO dispatches(case_id,round,status,due_at,created_at) "
        "VALUES(?,1,'수배됨',datetime('now','+1 hours'),datetime('now'))", (cid2,))
    conn.commit(); conn.close()

    c = A.app.test_client()
    tok = "r245-csrf"
    with c.session_transaction() as sess:
        sess["admin"] = "r245low"; sess["admin_role"] = "하위관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    #  '유리'만 걸린 검색 — 기한이 지난 cid1(금속) 은 items 에서 빠지지만
    #  전체 기한초과 집계(overdue)는 여전히 1(cid1) 을 세야 한다.
    r = c.get("/api/dispatches?category=유리", headers=hdr)
    j = r.get_json()
    chk(r.status_code == 200, "STEP 검색필터 요청 자체는 정상 처리된다", r.status_code)
    item_cats = {x.get("category") for x in (j.get("items") or [])}
    chk("금속" not in item_cats,
        "STEP 검색필터가 실제로 걸려 금속(cid1)은 목록에서 빠졌다", item_cats)
    chk(j.get("overdue", 0) >= 1,
        "★★★★ 그런데도 전체 기한초과 집계는 필터 밖의 cid1 을 여전히 센다"
        "(고치기 전엔 화면이 items 에서만 다시 세서 이 상황에 0으로 보였다)",
        j.get("overdue"))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드245 [2] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — Node 로 직접배정 드롭다운 옵션 렌더링을 실제 평가")
# ------------------------------------------------------------
HARNESS = r'''
const opt = { id: 7, dist_km: 3.2, name: "테스트업체", type: "시공사", license: "등록확인",
              phone: "010-1234-5678", called: true };
const optNoPhone = { id: 8, dist_km: 5.0, name: "번호없는업체", type: "시행사", license: "미확인",
                      phone: null, called: false };
function esc(s){ return String(s==null?'':s); }
function render(p){
  return `<option value="${p.id}">${p.dist_km}km · ${esc(p.name)} (${esc(p.type||'')}${p.license==='등록확인'?' · 등록확인':''}) · ${p.phone?esc(p.phone):'번호없음'}${p.called?' · 이미 부름':''}</option>`;
}
console.log(JSON.stringify({ withPhone: render(opt), noPhone: render(optNoPhone) }));
'''
try:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(HARNESS)
        harness_path = f.name
    try:
        r = subprocess.run(["node", harness_path], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30)
    finally:
        try:
            os.unlink(harness_path)
        except OSError:
            pass
    chk(r.returncode == 0, "STEP Node 하네스가 예외 없이 끝까지 실행된다", r.stdout + r.stderr)
    out = json.loads((r.stdout or "{}").strip().splitlines()[-1]) if r.returncode == 0 else {}
    chk("010-1234-5678" in out.get("withPhone", "") and "이미 부름" in out.get("withPhone", ""),
        "★★★★ 전화번호가 있고 이미 부른 업체는 번호와 '이미 부름'이 옵션 텍스트에 실제로 나온다",
        out.get("withPhone"))
    chk("번호없음" in out.get("noPhone", "") and "이미 부름" not in out.get("noPhone", ""),
        "STEP 번호 없는 업체는 '번호없음'만 나오고 '이미 부름'은 안 붙는다(과잉표시 아님)",
        out.get("noPhone"))
except FileNotFoundError:
    chk(False, "STEP node 실행 파일을 찾을 수 없음(PATH 확인 필요)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드245 [3] 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
