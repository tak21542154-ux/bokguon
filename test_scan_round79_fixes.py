# -*- coding: utf-8 -*-
"""스캔 79라운드 회귀 — 폼 입력검증 형제드리프트/누락 2건.

  ① templates/partner_portal.html submitReBid() — 자릿수 의심 방어가 절대값
     기준(10만원 미만)이었다. 1차 경매(bidConfirm)는 상대 기준(기준선의 50%
     미만)인데, 재경매 상한은 보통 수백만~수천만원이라 "0 하나 빠뜨린" 금액
     대부분이 10만원을 그냥 넘어 이 방어를 통과했다. 서버(api_partner_reauction_bid)
     에도 원경매엔 있는 저가경보(_low_price_alert_pct)가 없어, 클라이언트 확인
     문구 하나가 유일한 방어였다 — 그마저 기준이 헐거웠다.

  ② app.py 의 사업자등록번호(valid_biz_no) 검사 — 국세청 검사식이 있는데
     실제로 쓰인 곳은 협력사 자기 프로필 수정 단 한 곳이었다. 조사 화면
     (api_partner_license, 무등록 판정을 하는 바로 그 자리), 업체 정보수정
     (api_partner_update), 업체 직접등록(api_partner_create), 입점신청
     직접접수(api_application_create) 는 전부 검사 없이 값을 그대로 심었다.
     오타가 들어가면 조사가 빈손이 되고, 일단 값이 박히면 협력사 자기
     프로필 수정으로도 못 고친다(이미 있는 값은 덮어쓰기 자체를 거부).

      python test_scan_round79_fixes.py
"""
import io
import json
import os
import shutil
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


PP = read("templates/partner_portal.html")
APP_SRC = read("app.py")

print("═" * 72)
print("  스캔 79라운드 회귀 — 재경매 자릿수 방어 헐거움 + 사업자번호 검사 누락 4곳")
print("═" * 72)


def _js_fn_body(src, header):
    i = src.find(header)
    if i < 0:
        return ""
    depth = 0
    started = False
    for k in range(i, len(src)):
        if src[k] == "{":
            depth += 1
            started = True
        elif src[k] == "}":
            depth -= 1
            if started and depth == 0:
                return src[i:k + 1]
    return ""


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


def _mk_biz_no(d9):
    """valid_biz_no() 와 같은 국세청 검사식으로 유효한 체크숫자를 만든다."""
    w = (1, 3, 7, 1, 3, 7, 1, 3, 5)
    s2 = sum(int(d9[i]) * w[i] for i in range(9)) + (int(d9[8]) * 5) // 10
    return d9 + str((10 - s2 % 10) % 10)


NODE = shutil.which("node")

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
rb_body = _js_fn_body(PP, "async function submitReBid(auctionId){")
chk(bool(rb_body), "STEP partner_portal.html 에서 submitReBid 함수 본문을 추출했다", len(rb_body))
chk("_n < 100000" not in rb_body, "STEP 옛 절대값(10만원) 기준이 사라졌다")
chk("_n < _base * 0.5" in rb_body,
    "★★★ ① submitReBid 가 1차 경매(bidConfirm)와 같은 상대 기준(_base×0.5)으로 "
    "자릿수 의심을 판정한다")

reau_body = _py_fn_body(APP_SRC, "api_partner_reauction_bid")
chk("_low_price_alert_pct(conn)" in reau_body and "저가경보" in reau_body,
    "★★ ①-서버 api_partner_reauction_bid 에도 원경매와 같은 저가경보가 붙었다"
    "(고치기 전엔 이 창구에만 없었다)")

license_body = _py_fn_body(APP_SRC, "api_partner_license")
chk("valid_biz_no(_bz)" in license_body,
    "★★★ ②-1 api_partner_license(조사 화면) 가 valid_biz_no 를 거친다")

update_body = _py_fn_body(APP_SRC, "api_partner_update")
chk('valid_biz_no(d[f])' in update_body,
    "★★★ ②-2 api_partner_update(업체 정보수정) 가 valid_biz_no 를 거친다")

create_body = _py_fn_body(APP_SRC, "api_partner_create")
chk('valid_biz_no(d["biz_no"])' in create_body,
    "★★ ②-3 api_partner_create(업체 직접등록) 가 valid_biz_no 를 거친다")

appcreate_body = _py_fn_body(APP_SRC, "api_application_create")
chk("valid_biz_no(biz)" in appcreate_body,
    "★★ ②-4 api_application_create(입점신청 직접접수) 가 valid_biz_no 를 거친다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 클라이언트 함수를 node 로 실제 실행")
# ──────────────────────────────────────────────────────────────
if not NODE:
    chk(False, "★★★ node 실행 파일을 찾을 수 없다", "")
else:
    _js = """
    function esc(s){return String(s);}
    const won = n => (n||0).toLocaleString('ko-KR');
    var __confirmMsg = null;
    var __confirmReturn = false;
    global.confirm = function(msg){ __confirmMsg = msg; return __confirmReturn; };
    var __rbAmt = '0', __rbDays = '5';
    var document = {
      getElementById(id){
        if(id==='rb_amt') return {value: __rbAmt};
        if(id==='rb_days') return {value: __rbDays};
        if(id==='rebidbox') return {innerHTML:''};
        return null;
      }
    };
    var REAU = [];
    async function api(method, url, body){ return {kind:'추가분', bid_count:1}; }
    function toast(m){}
    var RENDER = { reauction: async () => {} };
    """ + rb_body + """
    async function run(){
      const out = {};
      //  ① cap 기준 자릿수 의심 — 상한 12,000,000 의 950,000(7.9%)
      REAU = [{auction_id:1, cap:12000000, my_bid:null, kind:'추가분'}];
      __rbAmt = '950000';
      await submitReBid(1);
      out.msg1 = __confirmMsg;

      //  ② cap 없음(전체재경매 유찰 등) → 직전 입찰가 기준 폴백 — 5,000,000 의 2,000,000(40%)
      REAU = [{auction_id:2, cap:0, my_bid:5000000, kind:'전체재경매'}];
      __rbAmt = '2000000';
      await submitReBid(2);
      out.msg2 = __confirmMsg;

      //  ③ 대조군 — 상한 12,000,000 의 9,000,000(75%, 의심 아님) → 경고 없어야 정상
      REAU = [{auction_id:3, cap:12000000, my_bid:null, kind:'추가분'}];
      __rbAmt = '9000000';
      await submitReBid(3);
      out.msg3 = __confirmMsg;

      console.log(JSON.stringify(out));
    }
    run();
    """
    r = subprocess.run(["node", "-e", _js], capture_output=True)
    out = (r.stdout or b"").decode("utf-8", "replace")
    err = (r.stderr or b"").decode("utf-8", "replace")
    line = next((ln for ln in out.splitlines() if ln.strip().startswith("{")), "")
    chk(bool(line), "STEP node 실행이 결과를 냈다", f"out={out!r} err={err[:400]!r}")
    if line:
        p = json.loads(line)
        m1, m2, m3 = p.get("msg1") or "", p.get("msg2") or "", p.get("msg3") or ""
        chk("상한 12,000,000원의 7.9%입니다" in m1 and "0을 빠뜨리지" in m1,
            "★★★ ① 상한 대비 자릿수 의심(950,000원/12,000,000원=7.9%)이 정확히 경고된다"
            "(고치기 전엔 950,000 ≥ 100,000 이라 절대 아무 경고도 안 떴다)", m1)
        chk("직전 입찰 5,000,000원의 40.0%입니다" in m2 and "0을 빠뜨리지" in m2,
            "★★ ② 상한이 없을 때(cap=0) 직전 입찰가로 폴백해도 자릿수 의심이 잡힌다", m2)
        chk("0을 빠뜨리지" not in m3,
            "★ 대조군 — 정상 범위(상한의 75%) 금액엔 자릿수 의심 경고가 안 뜬다"
            "(과잉경고 아님)", m3)

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 실서버 경로(Flask test_client + 임시 DB)로 서버 응답 확인")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round79_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    VALID1 = _mk_biz_no("123456781")
    VALID2 = _mk_biz_no("123456782")
    VALID3 = _mk_biz_no("123456783")
    VALID4 = _mk_biz_no("123456784")
    INVALID = VALID1[:9] + str((int(VALID1[9]) + 1) % 10)   # 체크숫자만 어긋난, 형식은 멀쩡한 값
    chk(A.valid_biz_no(VALID1) and not A.valid_biz_no(INVALID),
        "STEP (참고) 테스트용 사업자번호 생성이 실제로 유효/무효로 갈린다",
        f"VALID1={VALID1} INVALID={INVALID}")

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','중간관리자')")
    pid0 = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R79조사대상','시공사','활성')"
    ).lastrowid
    conn.commit()
    conn.close()

    admin = A.app.test_client()
    _tok = "r79-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    # ── ②-1 api_partner_license ──
    r1 = admin.post(f"/api/partners/{pid0}/license",
                     json={"license_status": "무등록", "biz_no": INVALID}, headers=_hdr)
    chk(r1.status_code == 400,
        "★★★ ②-1 조사 화면 — 무효한 사업자번호는 400으로 거부된다"
        "(고치기 전엔 그대로 저장되고 '무등록' 판정까지 확정됐다)", f"{r1.status_code} {r1.get_json()}")
    r1b = admin.post(f"/api/partners/{pid0}/license",
                      json={"license_status": "미확인", "biz_no": VALID1}, headers=_hdr)
    chk(r1b.status_code == 200, "STEP 대조군 — 유효한 사업자번호는 그대로 통과한다(과잉차단 아님)",
        f"{r1b.status_code} {r1b.get_json()}")
    _c = DB.get_db()
    _row = _c.execute("SELECT biz_no FROM partners WHERE id=?", (pid0,)).fetchone()
    _c.close()
    chk(_row["biz_no"] == VALID1, "STEP 유효한 값은 실제로 저장됐다", dict(_row))

    # ── ②-2 api_partner_update ──
    r2 = admin.patch(f"/api/partners/{pid0}", json={"biz_no": INVALID}, headers=_hdr)
    chk(r2.status_code == 400,
        "★★★ ②-2 업체 정보수정 — 무효한 사업자번호는 400으로 거부된다", f"{r2.status_code} {r2.get_json()}")
    r2b = admin.patch(f"/api/partners/{pid0}", json={"biz_no": VALID2}, headers=_hdr)
    chk(r2b.status_code == 200, "STEP 대조군 — 유효한 값은 통과한다", f"{r2b.status_code} {r2b.get_json()}")

    # ── ②-3 api_partner_create ──
    r3 = admin.post("/api/partners", json={"name": "R79신규1", "biz_no": INVALID}, headers=_hdr)
    chk(r3.status_code == 400,
        "★★ ②-3 업체 직접등록 — 무효한 사업자번호는 400으로 거부된다", f"{r3.status_code} {r3.get_json()}")
    r3b = admin.post("/api/partners", json={"name": "R79신규2", "biz_no": VALID3}, headers=_hdr)
    chk(r3b.status_code == 200 and (r3b.get_json() or {}).get("ok"),
        "STEP 대조군 — 유효한 값이면 정상 등록된다", f"{r3b.status_code} {r3b.get_json()}")

    # ── ②-4 api_application_create ──
    r4 = admin.post("/api/applications/manual",
                     json={"company": "R79입점1", "major": "가드레일·방호울타리", "biz_no": INVALID},
                     headers=_hdr)
    chk(r4.status_code == 400,
        "★★ ②-4 입점신청 직접접수 — 무효한 사업자번호는 400으로 거부된다", f"{r4.status_code} {r4.get_json()}")
    r4b = admin.post("/api/applications/manual",
                      json={"company": "R79입점2", "major": "가드레일·방호울타리", "biz_no": VALID4},
                      headers=_hdr)
    chk(r4b.status_code == 200 and (r4b.get_json() or {}).get("ok"),
        "STEP 대조군 — 유효한 값이면 정상 접수된다", f"{r4b.status_code} {r4b.get_json()}")

    # ── ① 서버측 저가경보 — 재경매 투찰 ──
    conn = DB.get_db()
    pid_inc = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R79원업체','시행사','활성')").lastrowid
    pid_bid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R79입찰업체','시행사','활성')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region) "
        "VALUES('R79-CO-1','시공중','가드레일','서울')").lastrowid
    coid = conn.execute(
        "INSERT INTO change_orders(case_id,round,incumbent_partner_id,incumbent_amount,"
        "requested_amount,status,created_at) "
        "VALUES(?,1,?,8000000,3000000,'추가경매중',?)", (cid, pid_inc, DB.now())).lastrowid
    aid = conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,status,created_at) "
        "VALUES(?,?,'추가분','진행',?)", (cid, coid, DB.now())).lastrowid
    conn.commit()
    conn.close()

    partner_client = A.app.test_client()
    _ptok = "r79-partner-csrf"
    with partner_client.session_transaction() as sess:
        sess["partner_id"] = pid_bid
        sess["_csrf"] = _ptok
    #  cap(=requested_amount)=3,000,000 의 1,000,000원 → 66.7% 인하, 기본 임계 20% 를 크게 넘는다
    r5 = partner_client.post("/api/partner/reauction-bids",
                              json={"auction_id": aid, "amount": 1000000, "days": 5},
                              headers={"X-CSRF-Token": _ptok})
    chk(r5.status_code == 200,
        "STEP 재경매 투찰 자체는 정상 처리된다", f"{r5.status_code} {r5.get_json()}")
    _c = DB.get_db()
    _n = _c.execute(
        "SELECT COUNT(*) n FROM notifications WHERE ntype='저가경보' AND case_id=?",
        (cid,)).fetchone()["n"]
    _c.close()
    chk(_n >= 1,
        "★★★ ①-서버 재경매 투찰이 상한 대비 크게 낮으면(66.7%↓) 저가경보가 실제로 기록된다"
        "(고치기 전엔 이 창구에서 이런 알림이 전혀 안 났다)", f"n={_n}")

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드79 서버측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
