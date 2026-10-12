# -*- coding: utf-8 -*-
"""스캔 289라운드 회귀 — legal_docs.py 하자담보책임기간 고정표기 결함 2건
   + insurer_portal.html 하자접수 모달 하자보증 고정표기 결함 1건.

  cases.warranty_months 는 사건마다 관리자가 0~120 사이로 다르게 정하는 실제
  컬럼인데(기본 24, NULL 일 때만 24로 대체 — db.py 278행), 공개 법정 문서(약관·
  처리방침)와 보험사 포털 하자접수 모달이 전부 "24개월"을 보편적 고정값처럼
  적어 두었다.

  ① legal_docs.py TERMS 제7조·PRIVACY 제3조(하자보수 관련 기록·피해자 성명·
     연락처) — 실제 파기 기준일(manage.py _WEND)과 실제 하자보증 판정(app.py
     _warranty_left)은 전부 COALESCE(warranty_months,24)/wm 을 쓰는데 문서만
     "24개월"이 보편사실인 것처럼 적었다. 사건별로 정해지며 기본이 24개월이라는
     사실 자체를 밝히도록 수정(운영 메커니즘은 그대로 — 문서 정확성만 고침).
  ② insurer_portal.html defectForm() — 접수 전 안내문이 "하자보증 24개월" 고정
     문구였는데, 접수 직후 토스트는 사건별 실제 warranty_ok(서버가 사건의
     warranty_months 로 계산)를 알려준다 — 같은 사건에 대해 접수 전후 안내가
     서로 다른 말을 했다. 형제 화면(partner_portal.html 386행)이 이미 쓰는
     c.warranty_months??24 로 통일.

      python test_scan_round289_fixes.py
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


LEGAL_SRC = read("legal_docs.py")
INS_SRC = read(os.path.join("templates", "insurer_portal.html"))

print("=" * 72)
print("  스캔 289라운드 회귀 — 하자담보책임기간(24개월) 고정표기 vs 사건별 실값")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — legal_docs.py")
# ------------------------------------------------------------
#  ⚠ 아래 두 "not in" 검사는 파일 전체 텍스트(이번 수정 자체를 설명하는 주석 포함)를
#    본다 — 그 주석들이 옛 문구를 그대로 인용하므로, 표/조문 안에서만 실제로 쓰이는
#    형태(뒤에 "만료"·"</b> 시공"이 바로 붙는 꼴)로 좁혀 주석과 혼동되지 않게 한다.
chk("하자담보책임기간(24개월) 만료" not in LEGAL_SRC,
    "★★★ PRIVACY 표에 '하자담보책임기간(24개월) 만료' 고정 문구가 더는 없다"
    "(사건별로 정해지며 기본 24개월로 대체됨)")
chk(LEGAL_SRC.count("하자담보책임기간(사건별로 정해지며, 기본 24개월)") == 2,
    "★★★ PRIVACY 표 두 행(하자보수 관련 기록·피해자 성명·연락처) 모두 새 문구로 바뀜",
    LEGAL_SRC.count("하자담보책임기간(사건별로 정해지며, 기본 24개월)"))
chk("<b>24개월간</b> 시공 하자" not in LEGAL_SRC,
    "★★★ TERMS 제7조의 '24개월간' 고정 문구가 더는 없다")
chk("하자담보책임기간은 사건별로 정해지며" in LEGAL_SRC,
    "★★★ TERMS 제7조가 사건별로 정해진다는 사실을 밝힌다")
chk("공종별로 관계 법령이 이보다 긴 기간을 정한 경우에는" in LEGAL_SRC
    and "그에 따릅니다" in LEGAL_SRC,
    "기존 법령우선 조항 문구는 그대로 보존됨(문구 삭제 아님)")

print("\n[2] 소스 확인 — insurer_portal.html defectForm()")
# ------------------------------------------------------------
_i0 = INS_SRC.index("function defectForm(cid){")
_i1 = INS_SRC.index("\nasync function submitDefect", _i0 + 30)
DEFECT_FORM_SRC = INS_SRC[_i0:_i1]
#  ⚠ 이 함수 자신의 새 설명 주석이 옛 문구("하자보증 24개월")를 그대로 인용하므로,
#    실제 템플릿 리터럴에서만 나타나는 꼴(뒤에 "</div>"가 바로 붙는 꼴)로 좁힌다.
chk("하자보증 24개월</div>" not in DEFECT_FORM_SRC,
    "★★★ defectForm() 모달에 '하자보증 24개월' 고정 문구가 더는 없다")
chk("하자보증 ${c.warranty_months??24}개월" in DEFECT_FORM_SRC,
    "★★★ defectForm() 모달이 형제(partner_portal.html)와 같은 ??24 표기로 실값을 보여준다")

# ============================================================
print("\n[3] 실행 — legal_docs.py 실제 렌더 결과에도 잔존 문구가 없다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round289_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import legal_docs as LEGAL
    chk("하자담보책임기간(24개월)" not in LEGAL.PRIVACY,
        "★★★ 실제 PRIVACY 상수 렌더 결과에도 고정 문구가 없다")
    chk("<b>24개월간</b>" not in LEGAL.TERMS,
        "★★★ 실제 TERMS 상수 렌더 결과에도 고정 문구가 없다")
    chk("사건별" in LEGAL.PRIVACY and "사건별" in LEGAL.TERMS,
        "PRIVACY·TERMS 둘 다 실제로 '사건별' 안내를 포함한다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드289 [3] legal_docs import/렌더", f"{type(e).__name__} {e}")

# ============================================================
print("\n[4] 실행 — /legal 페이지 실제 HTTP 응답에도 잔존 문구가 없다(운영모드 포함)")
# ------------------------------------------------------------
try:
    import db as DB
    DB.init_db()
    import app as A
    client = A.app.test_client()

    r1 = client.get("/legal/terms")
    chk(r1.status_code == 200 and "24개월간" not in r1.get_data(as_text=True),
        "★★★ /legal/terms 실제 응답에 '24개월간' 고정 문구가 없다", r1.status_code)

    r2 = client.get("/legal/privacy")
    chk(r2.status_code == 200 and "하자담보책임기간(24개월)" not in r2.get_data(as_text=True),
        "★★★ /legal/privacy 실제 응답에 고정 문구가 없다", r2.status_code)

    #  운영모드(IS_PROD)에서도 본문 자체(치환된 문구)는 그대로 나가야 한다 — 이번
    #  수정은 PENDING 미기재 배너와 무관한, 항상 노출되는 본문 자체이기 때문이다.
    _was_prod = A.IS_PROD
    A.IS_PROD = True
    try:
        r3 = client.get("/legal/privacy")
        chk("사건별로 정해지며" in r3.get_data(as_text=True),
            "★★★ 운영모드에서도 새 안내 문구가 그대로 노출된다(pending배너와는 별개)")
    finally:
        A.IS_PROD = _was_prod
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드289 [4] /legal 실제 응답 검증", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 실행 — insurer_portal.html defectForm() 실제 렌더링 (Node.js)")
# ------------------------------------------------------------
try:
    node_script = r'''
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf-8");
const i0 = src.indexOf("function defectForm(cid){");
const i1 = src.indexOf("\nasync function submitDefect", i0 + 30);
const body = src.slice(i0, i1);

let captured = null;
global.openModal = (html) => { captured = html; };
global.esc = (s) => String(s == null ? "" : s);
global.loadDefectPhotos = () => {};
global.D = { cases: [] };

function run(caseObj){
  captured = null;
  global.D.cases = [caseObj];
  eval(body);
  defectForm(caseObj.id);
  return captured;
}

const r1 = run({id:1, case_no:"C1", category:"가드레일", partner_name:"업체A", warranty_months:6});
const r2 = run({id:2, case_no:"C2", category:"가드레일", partner_name:"업체B", warranty_months:0});
const r3 = run({id:3, case_no:"C3", category:"가드레일", partner_name:"업체C", warranty_months:null});

console.log(JSON.stringify({
  has6: r1.includes("하자보증 6개월"),
  has0: r2.includes("하자보증 0개월"),
  hasDefault24: r3.includes("하자보증 24개월"),
}));
'''
    _nd = tempfile.mkdtemp(prefix="round289_node_")
    node_path = os.path.join(_nd, "check.js")
    io.open(node_path, "w", encoding="utf-8").write(node_script)
    r = subprocess.run(
        ["node", node_path, os.path.join(HERE, "templates", "insurer_portal.html")],
        capture_output=True, text=True, timeout=30,
        encoding="utf-8", errors="replace")
    chk(r.returncode == 0, "Node.js 스크립트 정상 종료",
        (r.stdout + r.stderr)[-1500:] if r.returncode else "")
    if r.returncode == 0:
        out = json.loads(r.stdout.strip().splitlines()[-1])
        chk(out.get("has6") is True,
            "★★★ warranty_months=6 인 사건은 '하자보증 6개월'로 렌더링됨(값 그대로 반영)")
        chk(out.get("has0") is True,
            "★★★ warranty_months=0(무보증) 인 사건은 '하자보증 0개월'로 렌더링됨"
            "(?? 는 0을 유효값으로 존중 — || 였다면 24로 둔갑했을 것)")
        chk(out.get("hasDefault24") is True,
            "★★★ warranty_months=null 인 사건만 기본값 24로 렌더링됨")
except FileNotFoundError:
    chk(True, "Node.js 미설치 환경 — [5] 스킵(다른 검증으로 충분히 커버됨)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드289 [5] Node.js 렌더 검증", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
