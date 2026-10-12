# -*- coding: utf-8 -*-
"""스캔 78라운드 회귀 — 돈·퍼센트 표시 형제사본 드리프트 3곳.

  ① templates/partner_portal.html bidConfirm() — "자릿수 의심" 경고의 기준선은
     `_base = cap || floorC || (mine ? mine.amount : 0)` 로 이미 넓혀져 있는데
     (가견적도 개산 하단도 없는 사진없음 접수 건까지 덮으려고), 경고 문구
     자체는 그 뒤에도 여전히 `cap` 으로 나눴다. cap=0 인 채 mine.amount 기준으로
     suspicious 가 true 가 되면 `n*100/cap` 이 0으로 나눠 "가견적 0원의 Infinity%"
     를 그대로 보여준다 — 하필 그 방어가 새로 덮으려던 바로 그 경우에.

  ② static/admin.js VIEWS.cases 의 절감률 셀 — 서버(api_cases)의 c.saving 은
     확정가가 비교기준을 넘으면 음수가 된다(1차합의 등 초과 낙찰). 그런데 이
     셀은 `c.saving>0` 만 보고 나머지(음수 포함)를 전부 데이터없음과 같은 '-'
     로 찍었다. 같은 사건을 보는 insurer_portal.html(621행)은 부호대로
     초록/빨강 + −/+ 로 정확히 보여주는데, 관리자 목록만 초과 낙찰을 숨겼다.

  ③ app.py api_insurer_case_detail + templates/insurer_portal.html — 보험사
     화면이 "원 낙찰가"를 `combined_amount - requested_amount` 로 역산했다.
     실제로는 combined_amount = incumbent_amount + add_low(추가분 경매
     낙찰가) 이지 requested_amount(협력사 자기신고 예상액)와는 무관하다 —
     서버 SELECT 에 incumbent_amount 자체가 없어 화면이 이렇게 거꾸로 계산할
     수밖에 없었다. 합산 전(combined_amount 없음)이면 역산값이 음수라 0으로
     접혀 원 낙찰가가 0원으로 보였다.

      python test_scan_round78_fixes.py
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
IP = read("templates/insurer_portal.html")
ADMIN_JS = read("static/admin.js")
APP_SRC = read("app.py")

print("═" * 72)
print("  스캔 78라운드 회귀 — 돈·퍼센트 표시 형제사본 드리프트 3곳")
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


NODE = shutil.which("node")

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
bc_body = _js_fn_body(PP, "function bidConfirm(caseId){")
chk(bool(bc_body), "STEP partner_portal.html 에서 bidConfirm 함수 본문을 추출했다", len(bc_body))
chk("${_baseLabel} ${won(_base)}원의 ${(n*100/_base).toFixed(1)}% 입니다." in bc_body,
    "★★★ ① bidConfirm 의 자릿수 의심 경고가 cap 이 아니라 실제 기준선(_base)으로 나눈다")
chk("가견적 ${won(cap)}원의 ${(n*100/cap).toFixed(1)}%" not in bc_body,
    "STEP 옛 cap 나눗셈 표현식이 사라졌다")

cases_body = _js_fn_body(ADMIN_JS, "VIEWS.cases = async () => {")
chk(bool(cases_body), "STEP admin.js 에서 VIEWS.cases 함수 본문을 추출했다", len(cases_body))
chk("${c.saving>0?'-'+c.saving+'%':'-'}" not in cases_body,
    "STEP 옛 절감률 셀 표현식이 사라졌다")
chk("${(c.saving||0)>=0?'var(--green)':'var(--red)'}" in cases_body
    and "${c.saving?((c.saving>0?'−':'+')+Math.abs(c.saving)+'%'):'-'}" in cases_body,
    "★★ ② admin.js 절감률 셀이 부호에 따라 색·기호를 정한다"
    "(형제 insurer_portal.html 621행과 동일)")

detail_fn = _py_fn_body(APP_SRC, "api_insurer_case_detail")
chk("incumbent_amount" in detail_fn and "FROM change_orders WHERE case_id=?" in detail_fn,
    "★★★ ③ api_insurer_case_detail 의 변경건 조회 SQL이 incumbent_amount 를 포함한다")

co_body = _js_fn_body(IP, "(()=>{const o=r.change_order;")
chk(bool(co_body), "STEP insurer_portal.html 에서 change_order 렌더 블록을 추출했다", len(co_body))
chk("const inc=" not in co_body, "STEP 옛 combined-requested 역산 변수(inc)가 사라졌다")
chk("won(o.incumbent_amount)" in co_body,
    "★★★ ③ 화면이 역산 대신 서버가 주는 incumbent_amount 를 그대로 쓴다")
chk("o.combined_amount?won(o.combined_amount)+'원':'-'" in co_body,
    "★ ③ 합산 전(combined_amount 없음)이면 '0원' 대신 '-' 로 표시한다"
    "(admin.js 변경건 목록의 기존 가드와 동일)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 클라이언트 함수를 node 로 실제 실행")
# ──────────────────────────────────────────────────────────────
if not NODE:
    chk(False, "★★★ node 실행 파일을 찾을 수 없다", "")
else:
    # ── ① bidConfirm — cap=0(mine.amount 기준 의심) vs cap>0(정상, 회귀 없음) ──
    _js1 = """
    function esc(s){return String(s);}
    function koRead(n){return '';}
    function leftText(h){return '';}
    function dlLeft(dl){return null;}
    const feePct = bp => 0;
    const vatNote = () => '';
    const payoutOf = (amount, bp) => amount;
    const won = n => (n||0).toLocaleString('ko-KR');
    const onlyDigits = v => String(v||'').replace(/[^0-9]/g,'');
    var __modal = null;
    function openModal(html){ __modal = html; }
    var currentAmt = '0';
    var document = {
      getElementById(id){
        if(id==='b_amt') return {value: currentAmt};
        if(id==='b_days') return {value:'10'};
        return null;
      }
    };
    var D = { open_cases: [
      {id:1, case_no:'R78-1', category:'테스트', region:'', auction_round:1,
       bid_cap:null, est_price:0, bid_floor:null, fee_rate_bp:null, deadline:null},
      {id:2, case_no:'R78-2', category:'테스트', region:'', auction_round:1,
       bid_cap:5000000, est_price:5000000, bid_floor:null, fee_rate_bp:null, deadline:null}
    ], my_bids: [{case_id:1, amount:8000000}] };
    """ + bc_body + """
    currentAmt = '700000';
    bidConfirm(1);
    const modal1 = __modal;
    currentAmt = '2000000';
    bidConfirm(2);
    const modal2 = __modal;
    console.log(JSON.stringify({modal1, modal2}));
    """
    r1 = subprocess.run(["node", "-e", _js1], capture_output=True)
    out1 = (r1.stdout or b"").decode("utf-8", "replace")
    err1 = (r1.stderr or b"").decode("utf-8", "replace")
    line1 = next((ln for ln in out1.splitlines() if ln.strip().startswith("{")), "")
    chk(bool(line1), "STEP node 실행이 결과를 냈다(①)", f"out={out1!r} err={err1[:400]!r}")
    if line1:
        p1 = json.loads(line1)
        m1, m2 = p1.get("modal1") or "", p1.get("modal2") or ""
        chk("Infinity" not in m1,
            "★★★ ① cap=0·최저가=0 인데 직전 입찰 기준으로 자릿수 의심이 뜨는 경우에도 "
            "'Infinity%' 가 나오지 않는다(고치기 전엔 '가견적 0원의 Infinity%' 로 표시됐다)",
            m1[:400])
        chk("직전 입찰가" in m1 and "8,000,000원" in m1,
            "★ ① 이 경우 경고 문구가 실제 기준(직전 입찰가 8,000,000원)으로 표시된다", m1[:400])
        chk("Infinity" not in m2 and "가견적" in m2 and "40.0%" in m2,
            "★ 대조군 — cap>0 인 정상 케이스는 그대로 '가견적'·정확한 %로 표시된다"
            "(과잉수정 아님)", m2[:400])

    # ── ② admin.js VIEWS.cases — 음수 절감률이 형제와 같은 방식으로 보이는가 ──
    sort_body = _js_fn_body(ADMIN_JS, "function sortCasesList(list){")
    _js2 = """
    function esc(s){return String(s);}
    function xlsxBtn(a,b){return '';}
    function statusPill(s){return String(s);}
    function staleCell(c){return '';}
    const won = n => (n||0).toLocaleString('ko-KR');
    const ALL_MAJORS = [];
    const SEARCH_W = '';
    let caseFilter = '전체';
    let caseSearch = {q:'', from:'', to:'', category:''};
    let caseSort = 'recent';
    function caseQS(){ return new URLSearchParams(); }
    var __content = {innerHTML:''};
    function $(sel){ return __content; }
    async function api(method, url){
      return [
        {id:1, case_no:'R78-NEG', insurer:'테스트', category:'테스트', region:'서울',
         is_composite:false, urgent:false, intake_type:'', award_route:null, dispatch_status:'',
         status:'완료', stale_days:0, est_price:5000000, award_amount:6500000, low_price:null,
         saving:-30.0, manager:'홍길동'},
        {id:2, case_no:'R78-POS', insurer:'테스트', category:'테스트', region:'서울',
         is_composite:false, urgent:false, intake_type:'', award_route:null, dispatch_status:'',
         status:'완료', stale_days:0, est_price:5000000, award_amount:3500000, low_price:null,
         saving:30.0, manager:'홍길동'}
      ];
    }
    """ + sort_body + "\nvar VIEWS={};\n" + cases_body + """
    (async () => {
      await VIEWS.cases();
      console.log(JSON.stringify({html: __content.innerHTML}));
    })();
    """
    r2 = subprocess.run(["node", "-e", _js2], capture_output=True)
    out2 = (r2.stdout or b"").decode("utf-8", "replace")
    err2 = (r2.stderr or b"").decode("utf-8", "replace")
    line2 = next((ln for ln in out2.splitlines() if ln.strip().startswith("{")), "")
    chk(bool(line2), "STEP node 실행이 결과를 냈다(②)", f"out={out2!r} err={err2[:400]!r}")
    if line2:
        html = json.loads(line2).get("html", "")

        def _row(marker):
            i = html.find(marker)
            j = html.find("</tr>", i)
            return html[i:j] if i >= 0 and j >= 0 else ""

        neg_row = _row("R78-NEG")
        pos_row = _row("R78-POS")
        chk(bool(neg_row) and bool(pos_row), "STEP 두 행이 렌더된 HTML에서 발견됐다",
            html[:200])
        chk("+30%" in neg_row and "var(--red)" in neg_row and "-30%" not in neg_row
            and ">-<" not in neg_row,
            "★★★ ② 초과 낙찰(음수 절감률) 행이 '+30%'·빨강으로 보인다"
            "(고치기 전엔 데이터없음과 똑같은 '-' 로 숨겨졌다)", neg_row)
        chk("var(--green)" in pos_row and "−30%" in pos_row,
            "★ 대조군 — 정상(양수) 절감률 행은 기존처럼 초록 '−30%'로 보인다(과잉수정 아님)",
            pos_row)

    # ── ③ insurer_portal.html — change_order 렌더가 실값을 쓰는가 ──
    #  ⚠⚠ [라운드115] 이 렌더 블록이 canAct() 를 새로 쓴다(등급 미달이면 버튼
    #    대신 안내문) — 이 조사와는 무관한 함수라 이 최소 샌드박스에는 없었다.
    #    실행만 되게 참(true)으로 채운다(이 테스트의 관심사는 incumbent_amount다).
    _js3 = """
    function esc(s){return String(s);}
    const won = n => (n||0).toLocaleString('ko-KR');
    const canAct = () => true;
    var r;
    function render(){ return """ + co_body + """)(); }
    r = {change_order: {status:'원업체제안', incumbent_amount:8000000, requested_amount:3000000,
                         combined_amount:10200000, reason:'테스트', created_at:'2026-08-01 00:00:00',
                         insurer_ack:null, insurer_ack_amount:null, insurer_ack_by:'',
                         insurer_ack_at:'', insurer_ack_note:''}};
    const htmlA = render();
    r = {change_order: {status:'추가경매중', incumbent_amount:8000000, requested_amount:3000000,
                         combined_amount:null, reason:'테스트', created_at:'2026-08-01 00:00:00',
                         insurer_ack:null, insurer_ack_amount:null, insurer_ack_by:'',
                         insurer_ack_at:'', insurer_ack_note:''}};
    const htmlB = render();
    console.log(JSON.stringify({htmlA, htmlB}));
    """
    r3 = subprocess.run(["node", "-e", _js3], capture_output=True)
    out3 = (r3.stdout or b"").decode("utf-8", "replace")
    err3 = (r3.stderr or b"").decode("utf-8", "replace")
    line3 = next((ln for ln in out3.splitlines() if ln.strip().startswith("{")), "")
    chk(bool(line3), "STEP node 실행이 결과를 냈다(③)", f"out={out3!r} err={err3[:400]!r}")
    if line3:
        p3 = json.loads(line3)
        ha, hb = p3.get("htmlA") or "", p3.get("htmlB") or ""

        def _field(html, label):
            pat = f'>{label}</span><span class="v'
            i = html.find(pat)
            if i < 0:
                return None
            tag_end = html.find(">", i + len(pat))    # 값 span 의 여는 태그가 닫히는 지점
            val_end = html.find("</span>", tag_end + 1)
            return html[tag_end + 1:val_end]

        wa = _field(ha, "원 낙찰가")
        wb = _field(hb, "원 낙찰가")
        cb = _field(hb, "합산가")
        chk(wa == "8,000,000원",
            "★★★ ③ 합산 완료 건에서 원 낙찰가가 실값(8,000,000원)으로 보인다"
            "(고치기 전엔 combined-requested=7,200,000원 으로 잘못 표시됐다)", wa)
        chk(wb == "8,000,000원",
            "★★★ ③ 합산 전(combined_amount 없음) 건에서도 원 낙찰가가 0원이 아니라 "
            "실값(8,000,000원)으로 보인다(고치기 전엔 역산이 음수가 되어 0원으로 표시됐다)", wb)
        chk(cb == "-",
            "★ ③ 합산 전이면 합산가가 '0원' 대신 '-' 로 표시된다"
            "(admin.js 변경건 목록과 같은 가드)", cb)

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 실서버 경로(Flask test_client + 임시 DB)로 서버 응답 확인")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round78_")
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
    iid = conn.execute("INSERT INTO insurers(name) VALUES('R78보험')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,est_price,award_amount) "
        "VALUES('R78-CO-1','시공중','가드레일','서울',?,5000000,8000000)", (iid,)).lastrowid
    #  ⚠ combined_amount(10,200,000) - requested_amount(3,000,000) = 7,200,000 ≠
    #    incumbent_amount(8,000,000) — 옛 역산 공식이 실값과 다른 값을 내도록
    #    일부러 벌려 놓은 테스트 데이터다(실제로도 add_low 가 requested_amount 와
    #    같을 이유가 없다 — 후자는 협력사 자기신고, 전자는 제3업체 실제 낙찰가).
    conn.execute(
        "INSERT INTO change_orders(case_id,round,incumbent_amount,requested_amount,"
        "combined_amount,status,created_at) VALUES(?,1,8000000,3000000,10200000,'원업체제안',?)",
        (cid, DB.now()))
    conn.commit()
    conn.close()

    client = A.app.test_client()
    with client.session_transaction() as sess:
        sess["insurer_id"] = iid
    resp = client.get(f"/api/insurer/cases/{cid}/detail")
    d = resp.get_json() or {}
    co = (d or {}).get("change_order") or {}
    chk(resp.status_code == 200, "STEP 보험사 사건상세 API가 200을 반환한다",
        f"{resp.status_code} {d}")
    old_wrong = (co.get("combined_amount") or 0) - (co.get("requested_amount") or 0)
    chk(old_wrong != 8000000,
        "STEP (참고) 이 테스트 데이터에서 옛 역산 공식(combined-requested)은 "
        f"실값과 다른 값({old_wrong:,}원)을 낸다 — 그래야 이 검사가 의미가 있다", co)
    chk(co.get("incumbent_amount") == 8000000,
        "★★★ ③ 서버 응답이 incumbent_amount(원 낙찰가 실값)를 그대로 포함한다"
        "(고치기 전엔 이 필드 자체가 응답에 없어 화면이 combined-requested 로 역산했다)",
        co)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드78 서버측 준비/실행", f"{type(e).__name__} {e}")
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
