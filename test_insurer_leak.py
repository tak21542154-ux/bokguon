# -*- coding: utf-8 -*-
"""보험사 노출 철칙 전수 검사 — test_partner_leak.py(협력사 쪽, 라이브서버 대상)의
   보험사측 대칭 버전(round422 제안, round435가 사진/문서 IDOR 핵심 6개 라우트만
   부분적으로 메웠음 — test_scan_round435_fixes.py). 이 파일은 round435가 안 건드린
   나머지 두 축을 채운다.

   (a) test_partner_leak.py [3]("관리자 GET 라우트를 소스에서 자동추출해 전수
       두드리는" 스윕)의 보험사판이 이 저장소에 하나도 없었다 — 손으로 적은
       목록이 아니라 @require_admin/@require_role 데코레이터를 정규식으로
       뽑아내므로 새 관리자 화면이 생겨도 목록을 안 고쳐도 자동으로 커버된다.
   (b) 보험사 자신의 목록성 GET 응답(대시보드·하자·정산명세 등)이 **다른
       보험사**의 사건번호·피해자 연락처·추적토큰·업체계좌를 흘리는지 재귀
       스캔 — test_partner_leak.py [1]의 "금지 키/금지 값 훑기"에 대응한다.

   round435와 달리 무거운 라이브서버(port 8799) 방식이 아니라 이 세션의
   test_scan_round*.py 들과 같은 인프로세스 Flask test_client + 스크래치 DB로
   작성해 run_all_tests.py --quick 에 편입한다(round435가 세운 비례성 판단을
   그대로 따름). [2]는 round435가 이미 훨씬 넓게 검증한 사건상세 IDOR을 이
   파일 혼자서도 최소한으로 재현해, 이 파일이 round435 존재 여부에 기대지
   않고 단독으로도 뜻이 통하게 한다.

       python test_insurer_leak.py
"""
import io
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(HERE, "app.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

print("=" * 72)
print("  보험사 노출 철칙 전수 검사 (test_partner_leak.py 보험사측 대칭)")
print("=" * 72)

_tmpdir = tempfile.mkdtemp(prefix="insurer_leak_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
#  ⚠ [라운드603] DB·업로드는 갈라놓으면서 로그는 안 갈라놓으면 app.py:1226의
#    LOG_FILE 기본값이 이 저장소의 진짜 bokguon.log(실서버가 쓰는 그 파일)로
#    떨어진다 — round603이 실측으로 확인한 바로 그 결함(run_all_tests.py에서
#    고침)을 이 파일 스스로 반복하지 않는다.
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "test.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB
DB.init_db()
import app as A

PW = "Testpw123!"
conn = DB.get_db()

# ══════════════════════════════════════════════════════════════
#  픽스처 — 보험사I1(사건A, 민감정보 보유) · 보험사I2(사건B, 조회자/공격자)
# ══════════════════════════════════════════════════════════════
i1 = conn.execute("INSERT INTO insurers(name,login_id,password_hash,status) "
                   "VALUES('I1보험사','ileak_ins1',?, '활성')", (DB.hash_pw(PW),)).lastrowid
i2 = conn.execute("INSERT INTO insurers(name,login_id,password_hash,status) "
                   "VALUES('I2보험사','ileak_ins2',?, '활성')", (DB.hash_pw(PW),)).lastrowid
p1 = conn.execute("INSERT INTO partners(name,partner_type,status,category,region,"
                   "bank_account_enc,created_at) "
                   "VALUES('P1업체','시공사','활성','가드레일','서울',"
                   "'ENC(SECRETBANKACCT999)',?)", (DB.now(),)).lastrowid

SECRET_CASE_NO = "ILEAK-A-" + os.urandom(3).hex().upper()
SECRET_VICTIM_PHONE = "010-9999-8888"
SECRET_VICTIM_NAME = "김비밀"
SECRET_ADDR = "서울 A현장 극비주소 999"
SECRET_TRACK_TOKEN = "TRACKTOK-" + os.urandom(4).hex()

case_a = conn.execute(
    "INSERT INTO cases(case_no,status,category,region,address,insurer_id,partner_id,"
    "                  insurer,partner_name,victim_name,victim_phone,track_token,created_at) "
    "VALUES(?,'시공중','가드레일','서울',?,?,?,"
    "       'I1보험사','P1업체',?,?,?,?)",
    (SECRET_CASE_NO, SECRET_ADDR, i1, p1, SECRET_VICTIM_NAME, SECRET_VICTIM_PHONE,
     SECRET_TRACK_TOKEN, DB.now())).lastrowid
case_b = conn.execute(
    "INSERT INTO cases(case_no,status,category,region,address,insurer_id,"
    "                  insurer,created_at) "
    "VALUES('ILEAK-B','접수','가드레일','서울','서울 B현장 주소 111',?,"
    "       'I2보험사',?)", (i2, DB.now())).lastrowid
conn.commit()


def login_insurer(login_id):
    c = A.app.test_client()
    r = c.post("/api/insurer/login", json={"login_id": login_id, "password": PW})
    assert r.status_code == 200, (login_id, r.status_code, r.get_data(as_text=True))
    return c


ins1 = login_insurer("ileak_ins1")   # 사건A 소속(대조군 — 자기 것은 열려야 정상)
ins2 = login_insurer("ileak_ins2")   # 사건B 소속(공격자 겸 조회 대상)


def walk(node, path=""):
    """응답 JSON을 재귀로 훑어 (경로, 키, 값)을 모두 뽑는다(test_partner_leak.py와 동일 기법)."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield (path, k, v)
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node[:80]):
            yield from walk(v, f"{path}[{i}]")


BANNED_KEYS = {"password_hash", "bank_account_enc", "bank_account_idx"}
SECRET_VALUES = {SECRET_CASE_NO, SECRET_VICTIM_PHONE, SECRET_VICTIM_NAME,
                 SECRET_ADDR, SECRET_TRACK_TOKEN, "SECRETBANKACCT999"}

ENDPOINTS = [
    ("GET", "/api/insurer/dashboard"),
    ("GET", "/api/insurer/defects"),
    ("GET", "/api/insurer/notifications"),
    ("GET", "/api/insurer/report"),
    ("GET", "/api/insurer/statement"),
    ("GET", "/api/insurer/subaccounts"),
    ("GET", "/api/insurer/profile"),
    ("GET", "/api/insurer/me"),
]

print(f"\n감시 대상 — 타사(I1) 사건번호·피해자성명·피해자연락처·상세주소·추적토큰·업체계좌 각 1개")
print("\n[1] 보험사I2 자기 응답 전수 훑기 — 금지 필드/타사(I1) 값 없음")
for method, ep in ENDPOINTS:
    resp = ins2.get(ep)
    st = resp.status_code
    try:
        d = resp.get_json()
    except Exception:
        d = None
    if st != 200 or d is None:
        print(f"  [건너뜀] {ep} ({st})")
        continue
    bad_keys, bad_vals = [], []
    for p, k, v in walk(d):
        if k in BANNED_KEYS and v not in (None, "", 0):
            bad_keys.append(f"{p}.{k}={str(v)[:24]}")
        if isinstance(v, str) and v.strip() in SECRET_VALUES:
            bad_vals.append(f"{p}.{k}={v[:24]}(타사 사건A 값)")
    chk(not bad_keys, f"{ep} — 금지 필드(비밀번호해시·업체계좌) 없음", bad_keys[:3])
    chk(not bad_vals, f"★ {ep} — 타 보험사(I1) 사건A 값 없음", bad_vals[:3])

print("\n[2] 남의 사건 직접 접근(IDOR) — 최소 재현(round435가 이미 더 넓게 검증)")
r = ins2.get(f"/api/insurer/cases/{case_a}/detail")
chk(r.status_code == 404, "★★★ GET /api/insurer/cases/{A}/detail — 타 보험사 차단(404)", r.status_code)
r = ins2.get(f"/api/insurer/cases/{case_a}/bids")
chk(r.status_code == 404, "★★★ GET /api/insurer/cases/{A}/bids — 타 보험사 차단(404)", r.status_code)
r = ins1.get(f"/api/insurer/cases/{case_a}/detail")
chk(r.status_code == 200, "  대조군 — 사건A 소속 보험사I1은 정상 조회(과잉차단 아님)", r.status_code)

print("\n[3] 관리자 전용 라우트에 보험사 접근 — app.py 소스에서 자동추출해 전수 두드림")
#  ⚠ test_partner_leak.py [3]과 같은 이유: 손목록은 기능이 늘수록 뒤처진다.
#    @app.get(...) 바로 다음 줄에 @require_admin/@require_role 이 붙은 라우트를
#    전부 뽑는다(협력사 자기것·보험사 자기것·발주처 API 키 경로는 제외).
_admin_eps = []
for _m in re.finditer(r'@app\.get\(\s*"([^"]+)"\s*\)\s*\n\s*@(require_admin|require_role)\b',
                      APP_SRC):
    _p = _m.group(1)
    if _p.startswith("/api/partner") or _p.startswith("/api/insurer") or _p.startswith("/api/v1"):
        continue
    _admin_eps.append(re.sub(r"<[^>]+>", "1", _p))
_admin_eps = sorted(set(_admin_eps))
chk(len(_admin_eps) >= 7, f"관리자 GET 라우트를 소스에서 뽑았다 — {len(_admin_eps)}개",
    "0개면 정규식이 라우트 서식과 어긋난 것이다(조용히 아무것도 검사 안 함)")
for ep in _admin_eps:
    r = ins2.get(ep)
    #  ⚠ 404를 통과로 세면 안 된다 — 게이트가 막았다면 조회 전에 401/403이 난다.
    chk(r.status_code in (401, 403), f"★ {ep} — 보험사 세션 차단", r.status_code)

print("\n[4] 내 건은 볼 수 있어야 한다(과잉 차단 확인)")
r = ins2.get("/api/insurer/dashboard")
d = r.get_json() or {}
mine = [c for c in (d.get("cases") or []) if c.get("id") == case_b]
chk(bool(mine), "내(I2) 사건B가 대시보드 목록에 있다", len(d.get("cases") or []))
if mine:
    chk(mine[0].get("case_no") == "ILEAK-B", "★ 내 사건번호는 정상적으로 보인다", mine[0].get("case_no"))

print("\n[5] 탐지력 증명 — 관리자 게이트가 뚫리면 [3]이 실제로 잡아내는가")
#  ⚠ 이 회귀는 버그를 고친 게 아니라(클린 확인) 이미 맞는 코드에 새 자동스윕을
#    처음 씌운 것 — round435와 같은 상황이라 되돌릴 "옛 코드"가 없다. 대신
#    실제 게이트 하나를 임시로 없애 [3]의 판정 기준이 그 상태를 잡아내는지
#    증명한다. ⚠⚠ app.py **파일 자체는 절대 건드리지 않는다**(이 저장소는
#    git이 없어 동시에 다른 세션이 같은 파일을 만질 수 있다 — 디스크의 진짜
#    app.py에 깨진 코드를 쓰면 그 창에서 다른 세션·재기동이 그 상태를 그대로
#    읽을 위험이 있다). 대신 Flask가 등록해 둔 `app.view_functions` 딕셔너리
#    항목 하나만 메모리에서 임시 치환한다(요청 즉시 finally로 원복, 파일 변경 없음).
_victim_ep = "/api/settlements"
_victim_epname = next((r.endpoint for r in A.app.url_map.iter_rules()
                       if r.rule == _victim_ep and "GET" in r.methods), None)
chk(_victim_epname is not None, "  (준비) 스윕 대상 라우트의 endpoint 이름을 찾았다", _victim_ep)
if _victim_epname:
    _orig_view = A.app.view_functions[_victim_epname]
    A.app.view_functions[_victim_epname] = lambda *a, **k: ("OK", 200)  # [검증용 임시무력화]
    try:
        r = ins2.get(_victim_ep)
        chk(r.status_code == 200,
            "  (무력화 중) 게이트를 임시로 없애면 실제로 200이 난다(준비 확인)", r.status_code)
        chk(r.status_code not in (401, 403),
            "★★★★★ [3]과 같은 판정 기준(401/403 아니면 FAIL)이 무력화된 게이트를 "
            "실제로 잡아낸다(공허한 통과가 아니라는 증명)", r.status_code)
    finally:
        A.app.view_functions[_victim_epname] = _orig_view
    r2 = ins2.get(_victim_ep)
    chk(r2.status_code in (401, 403), "  무력화 해제 후 다시 정상 차단됨(원복 확인)", r2.status_code)

print("\n[6] 탐지력 증명 — 대시보드가 타사 값을 흘리면 [1]이 실제로 잡아내는가")
_dash_ep = "/api/insurer/dashboard"
_dash_epname = next((r.endpoint for r in A.app.url_map.iter_rules()
                     if r.rule == _dash_ep and "GET" in r.methods), None)
chk(_dash_epname is not None, "  (준비) 대시보드 라우트의 endpoint 이름을 찾았다", _dash_ep)
if _dash_epname:
    _orig_dash = A.app.view_functions[_dash_epname]

    def _leaky_dashboard():   # [검증용 임시무력화] 타사(I1) 사건이 섞여 나온다고 가정
        return A.jsonify({"cases": [{"id": case_a, "case_no": SECRET_CASE_NO,
                                      "address": SECRET_ADDR}]})

    A.app.view_functions[_dash_epname] = _leaky_dashboard
    try:
        resp = ins2.get(_dash_ep)
        d = resp.get_json()
        bad_vals = [f"{p}.{k}={v}" for p, k, v in walk(d)
                    if isinstance(v, str) and v.strip() in SECRET_VALUES]
        chk(bool(bad_vals),
            "★★★★★★★★★★ [1]과 같은 판정 기준(재귀 훑기)이 무력화된 대시보드의 타사 "
            "값을 실제로 잡아낸다(공허한 통과가 아니라는 증명)", bad_vals[:3])
    finally:
        A.app.view_functions[_dash_epname] = _orig_dash
    resp2 = ins2.get(_dash_ep)
    d2 = resp2.get_json() or {}
    chk(not any(isinstance(v, str) and v.strip() in SECRET_VALUES for _, _, v in walk(d2)),
        "  무력화 해제 후 다시 정상(타사 값 없음) — 원복 확인")

conn.close()
print(f"\n  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
