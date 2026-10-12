# -*- coding: utf-8 -*-
"""스캔 681라운드 회귀(직접조사, 하위위임 없음) — static/admin.js의 dispatches.status
   전용 색상 맵 DP_ST()가 같은 필드를 그리는 형제(insurer_portal.html stTag)와
   5개 키 중 3개(모집중·수배됨·취소)가 어긋나 있던 결함.

   조사 배경 — round75/644/672/677은 "상태값→색상 매핑은 이 저장소에 세 형제로
   존재한다"(insurer_portal.html stTag · partner_portal.html stTag · admin.js
   statusPill)는 전제로 그 세 곳만 대조해 왔다. 그런데 admin.js 안에는 그
   세 형제와 별개로, dispatches.status(출동 콜 자체의 상태 — 모집중/수배됨/
   도착/실패/취소, dispatch.py ST_OPEN·ST_CLAIMED와 db.py 스키마 주석이
   증언한다) 전용의 네 번째 미니맵 DP_ST가 4564행 부근에 파묻혀 있었다 —
   지금까지 어떤 라운드의 회귀 테스트도 "DP_ST"라는 이름을 언급한 적이
   없다(직접 grep 확인, 이 파일 이전엔 0건). 그런데 정확히 같은
   dispatches.status 값을 그리는 형제가 이미 있었다 — insurer_portal.html의
   dpCell(c)→stTag(d.status)(361~365행, dlCell 이 사건 목록에서 그대로
   호출한다, 240~242행)가 그것이다. 둘 다 결국 같은 원본 컬럼
   (app.py GET /api/dispatches 의 d.status, GET /api/insurer/dashboard 의
   dispatches 서브쿼리 d.status)을 그대로 받는다.

   실측(직접 조사, 고치기 전 값 기준) —
     admin.js DP_ST          = {'모집중':'blue','수배됨':'amber','도착':'green','실패':'red','취소':'gray'}
     insurer_portal.html stTag = {'모집중':'amber','수배됨':'blue','도착':'green','실패':'red','취소':'red', ...}
   5개 키 중 2개는 아예 색이 통째로 뒤바뀌어 있었다('모집중'·'수배됨' —
   blue↔amber가 서로 맞바뀐 값), 1개는 이 저장소 전체에서 유일하게 어긋난
   값이었다 — '취소'는 admin.js 자신의 statusPill()·partner_portal.html
   stTag()·insurer_portal.html stTag() 셋 다 이미 'red'로 일치하는데(정확히
   round75가 세운 원칙 "매핑에 없으면 회색이니 취소는 구분돼야 한다"의 대상),
   DP_ST만 'gray'였다. 도착·실패 2개는 원래부터 일치했다.

   재현 가능성 확인 — dispatch.py 44~45행 ST_OPEN="모집중"·ST_CLAIMED="수배됨"이
   실제 수배 개시·수락 시 찍는 값이고(391·458·541·556·603·674행 등에서 사용),
   app.py 5375행이 사건 종료 시 `UPDATE dispatches SET status='취소'`를 실제로
   실행한다 — db.py 732행 스키마 주석("모집중 / 수배됨 / 도착 / 실패 / 취소")도
   이 5개가 이 컬럼의 전체 정의역임을 확인해 준다. 셋 다 도달 가능한 정상 값이다.

   영향 — 사진 없이 접수된 같은 사건의 같은 출동 콜을, 운영 콘솔(VIEWS.dispatch
   목록·dispatchDetail 모달)에서 열면 한 색, 보험사 포털(사건 목록의 마감/진행
   열)에서 열면 다른 색으로 보인다 — round644가 잡은 것과 정확히 같은 성격의
   "같은 사실을 다른 화면이 다르게 말한다" 결함이다.

   고침 — static/admin.js의 DP_ST 정의(단일 지점 — 4677·4851행 두 호출부가
   이 상수 하나를 그대로 물려받는다)를 insurer_portal.html stTag 값에 맞춘다:
   '모집중':'amber'·'수배됨':'blue'·'취소':'red' (도착·실패는 원래부터 일치해
   무변경). build_pages.py는 admin.js를 렌더링하지 않으므로 재실행 대상이 아니다
   (admin.html은 <script src>로 외부 참조만 한다 — round678 확인 사항).
   test_template_js.py 9/17(admin.js 포함 외부참조 8개 전부) 표준 재검증 완료.

   회귀테스트(이 파일) —
   [1] 소스 — DP_ST와 insurer stTag에서 5개 키 값을 직접 뽑아 전부 일치함을
       확인하고, '취소'는 partner stTag·admin statusPill과도 일치함을 확인한다.
       실제 호출 지점(DP_ST[x.status]·DP_ST[v.status], dpCell→stTag(d.status))과
       재현 가능성 근거(ST_OPEN/ST_CLAIMED 상수, UPDATE ... status='취소',
       db.py 스키마 주석)도 소스에서 직접 정규식으로 확인한다.
   [2] 단위 — DP_ST 객체 리터럴과 세 stTag/statusPill 함수를 파일에서 그대로
       잘라내(손으로 다시 타이핑하지 않음) Node.js로 실제 실행해, admin.js
       호출부와 바이트 단위로 같은 인라인 표현식으로 만든 배지가 5개 상태
       전부에서 insurer stTag와 같은 색 클래스를 냄을 실측 증명한다.
   [3] 종단 — (a) 실제 Flask 정적 파일 서빙(GET /static/admin.js)으로 지금
       고친 DP_ST 리터럴이 실제로 응답 바이트에 그대로 담겨 나가는지 확인한다.
       (b) 스크래치 DB + 실제 Flask 라우트 두 개(GET /api/dispatches 관리자용,
       GET /api/insurer/dashboard 보험사용)로 5개 상태의 출동 콜을 실제로 만들고
       조회해, 두 라우트가 정확히 같은 원본 문자열을 내려줌을 실측한다.
   [4] 되돌리기 — [2]에서 잘라낸 (지금 고친) DP_ST 소스 문자열 안에서만 3개
       키를 옛 값으로 되돌린 사본을 독립 Node 스크립트로 만들어(실제 파일은
       전혀 건드리지 않음), 그 옛 버전이 실제로 형제 stTag와 다른 색을
       냈음을 재현 실측한다.

       python test_scan_round681_fixes.py
"""
import io
import json
import os
import re
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


def func_src_brace(src, header):
    """round644/672가 쓴 것과 같은 경계 찾기 — header부터 그 뒤 처음 나오는
    '줄 첫머리 단독 닫는 중괄호'(\\n})까지."""
    i = src.find(header)
    if i < 0:
        return ""
    j = src.find("\n}", i + len(header))
    return src[i:j + 2] if j >= 0 else ""


def cls_of(html):
    m = re.search(r'class="(?:tag|pill) ([a-z]+)"', html)
    return m.group(1) if m else None


print("=" * 72)
print("  스캔 681라운드 회귀 — admin.js DP_ST() dispatches.status 색상 어긋남")
print("=" * 72)

ADMIN_SRC = read("static/admin.js")
INSURER_SRC = read("templates/insurer_portal.html")
PARTNER_SRC = read("templates/partner_portal.html")
DISPATCH_SRC = read("dispatch.py")
APP_SRC = read("app.py")
DB_SRC = read("db.py")

# ============================================================
print("\n[1] 소스 확인 — DP_ST·형제 stTag 5개 키 직접 대조 + 실제 호출 지점 + 재현 가능성 근거")
# ------------------------------------------------------------
DP_ST_M = re.search(r"const DP_ST = \{[^}]*\};", ADMIN_SRC)
chk(DP_ST_M is not None, "  admin.js에서 DP_ST 정의를 실제로 찾았다")
DP_ST_SRC = DP_ST_M.group(0) if DP_ST_M else ""

STTAG_INSURER = func_src_brace(INSURER_SRC, "function stTag(s){")
STTAG_PARTNER = func_src_brace(PARTNER_SRC, "function stTag(s){")
PILL_ADMIN = func_src_brace(ADMIN_SRC, "function statusPill(s){")
chk(bool(DP_ST_SRC) and bool(STTAG_INSURER) and bool(STTAG_PARTNER) and bool(PILL_ADMIN),
    "  네 소스(DP_ST·세 형제 함수)를 전부 실제 파일에서 잘라냈다",
    f"len={len(DP_ST_SRC)}/{len(STTAG_INSURER)}/{len(STTAG_PARTNER)}/{len(PILL_ADMIN)}")


def _color_in(body, s):
    m = re.search(re.escape(f"'{s}':") + r"'([a-z]+)'", body)
    return m.group(1) if m else None


EXPECT = {"모집중": "amber", "수배됨": "blue", "도착": "green", "실패": "red", "취소": "red"}
for key, expect in EXPECT.items():
    c_dp = _color_in(DP_ST_SRC, key)
    c_ins = _color_in(STTAG_INSURER, key)
    star = "★★★★★" if key in ("모집중", "수배됨", "취소") else "  (회귀 없음)"
    chk(c_dp == expect, f"{star} admin.js DP_ST의 '{key}'가 이제 '{expect}'다", f"실제 값: {c_dp!r}")
    chk(c_dp == c_ins, f"{star} DP_ST와 insurer stTag의 '{key}' 색이 일치한다(형제 동기화)",
        f"DP_ST={c_dp!r} insurer={c_ins!r}")

# '취소'는 이 저장소의 나머지 두 형제(파트너 stTag·admin statusPill)와도 맞아야 한다
# (round75가 세운 "취소는 회색이면 안 된다" 원칙의 4번째 증인).
c_dp_cancel = _color_in(DP_ST_SRC, "취소")
c_partner_cancel = _color_in(STTAG_PARTNER, "취소")
c_admin_main_cancel = _color_in(PILL_ADMIN, "취소")
chk(c_dp_cancel == c_partner_cancel == c_admin_main_cancel == "red",
    "★★★★★ '취소' 색이 admin.js DP_ST·partner stTag·admin statusPill 셋 다 'red'로 일치한다",
    f"DP_ST={c_dp_cancel!r} partner={c_partner_cancel!r} adminMain={c_admin_main_cancel!r}")

# 실제 호출 지점 — 죽은 매핑이 아니라 실제로 쓰인다는 증거.
chk("<span class=\"pill ${DP_ST[x.status]||'gray'}\">${esc(x.status)}</span>" in ADMIN_SRC,
    "  admin.js가 실제로 DP_ST[x.status]를 호출한다(VIEWS.dispatch 목록 '상태' 열)")
chk("<span class=\"pill ${DP_ST[v.status]||'gray'}\">${esc(v.status)}</span>" in ADMIN_SRC,
    "  admin.js가 실제로 DP_ST[v.status]를 호출한다(dispatchDetail 모달 '상태' 행)")
chk("const bits=[stTag(d.status)];" in INSURER_SRC,
    "  insurer_portal.html이 실제로 stTag(d.status)를 호출한다(dpCell — 사건 목록 진행 열)")
chk("if(c.intake_type==='사진없음' && c.status==='접수') return dpCell(c);" in INSURER_SRC,
    "  (전제) dlCell()이 사건 목록 렌더 시 dpCell()을 실제로 경유한다")

# 재현 가능성 — 세 값 모두 도달 가능한 정상 상태값인가.
chk('ST_OPEN = "모집중"' in DISPATCH_SRC and 'ST_CLAIMED = "수배됨"' in DISPATCH_SRC,
    "  dispatch.py가 '모집중'·'수배됨'을 실제 상수(ST_OPEN·ST_CLAIMED)로 정의한다")
chk(DISPATCH_SRC.count("ST_OPEN") >= 3 and DISPATCH_SRC.count("ST_CLAIMED") >= 3,
    "  두 상수가 dispatch.py 안에서 여러 번 실제로 쓰인다(수배 개시·수락 등)",
    f"ST_OPEN={DISPATCH_SRC.count('ST_OPEN')}회 ST_CLAIMED={DISPATCH_SRC.count('ST_CLAIMED')}회")
chk("UPDATE dispatches SET status='취소'" in APP_SRC,
    "★★★★ app.py가 실제로 UPDATE dispatches SET status='취소'를 실행한다(사건 종료 시)")
chk("모집중 / 수배됨 / 도착 / 실패 / 취소" in DB_SRC,
    "  (전제) db.py 스키마 주석이 이 5개를 dispatches.status의 전체 정의역으로 명시한다")

# ============================================================
print("\n[2] 단위 — DP_ST·세 형제 함수를 파일에서 그대로 잘라내 Node.js로 직접 실행")
# ------------------------------------------------------------
NODE = shutil.which("node")
if not NODE:
    chk(False, "node 실행파일을 찾을 수 없다 — 이 구간은 건너뛰지 않고 실패로 답한다")
    NODE = None

ESC_LINE_M = re.search(r"const esc = s =>.*?;\n", PARTNER_SRC)
chk(ESC_LINE_M is not None, "  partner_portal.html에서 esc() 헬퍼를 찾았다")
ESC_LINE = ESC_LINE_M.group(0) if ESC_LINE_M else ""
chk(bool(ESC_LINE) and ESC_LINE in INSURER_SRC and ESC_LINE in ADMIN_SRC,
    "  (전제) esc() 헬퍼가 세 파일에서 바이트 단위로 동일하다(그대로 재사용 가능)")

# 이름이 같은 stTag()가 둘이라 한 스크립트에 같이 넣으려면 식별자만 바꾼다(round672와 동일 요령).
STTAG_PARTNER_R = STTAG_PARTNER.replace("function stTag(s){", "function stTagPartner(s){", 1)
chk(STTAG_PARTNER_R != STTAG_PARTNER and STTAG_PARTNER_R.count("stTagPartner") == 1,
    "  (harness) partner 함수명만 바꿨다(본문은 그대로)")

_scratch_node = tempfile.mkdtemp(prefix="round681_node_")


def run_node_probe(dp_st_src, label, statuses=("모집중", "수배됨", "도착", "실패", "취소")):
    """DP_ST + 세 형제 함수를 한 Node 스크립트에 모아, admin.js 실제 호출부와
    바이트 단위로 같은 인라인 표현식으로 배지를 만들어 지정한 상태값들을 실행한다."""
    script = (
        ESC_LINE + "\n"
        + dp_st_src + "\n\n"
        + STTAG_INSURER + "\n\n"
        + STTAG_PARTNER_R + "\n\n"
        + PILL_ADMIN + "\n\n"
        + "function dpPill(s){ return `<span class=\"pill ${DP_ST[s]||'gray'}\">${esc(s)}</span>`; }\n"
        + "const statuses = " + json.dumps(list(statuses), ensure_ascii=False) + ";\n"
        + "const out = {};\n"
        + "for (const s of statuses) { out[s] = {"
        + "dp: dpPill(s), insurer: stTag(s), partner: stTagPartner(s), adminMain: statusPill(s)}; }\n"
        + "console.log(JSON.stringify(out));\n"
    )
    p = os.path.join(_scratch_node, f"probe_{len(os.listdir(_scratch_node))}.js")
    io.open(p, "w", encoding="utf-8").write(script)
    r = subprocess.run([NODE, p], capture_output=True, text=True, encoding="utf-8", timeout=15)
    if r.returncode != 0:
        chk(False, f"  {label} Node 실행 실패", (r.stderr or "")[:300])
        return None
    try:
        return json.loads(r.stdout.strip())
    except Exception as e:
        chk(False, f"  {label} Node 출력 파싱 실패", f"{e}: {r.stdout[:200]}")
        return None


if NODE:
    out_new = run_node_probe(DP_ST_SRC, "[지금 고친 버전]")
    chk(out_new is not None, "  Node로 지금 버전(고친 뒤)을 실제 실행했다", str(out_new))
    if out_new:
        for s, expect in EXPECT.items():
            g_dp, g_ins = cls_of(out_new[s]["dp"]), cls_of(out_new[s]["insurer"])
            star = "★★★★★★" if s in ("모집중", "수배됨", "취소") else "  (회귀 없음)"
            chk(g_dp == expect and g_ins == expect,
                f"{star} 실제 실행 결과 — 상태 '{s}' → DP_ST·insurer stTag 모두 '{expect}' 클래스",
                f"dp={g_dp} insurer={g_ins}")
        g_dp_c, g_p_c, g_a_c = (cls_of(out_new["취소"][k]) for k in ("dp", "partner", "adminMain"))
        chk(g_dp_c == g_p_c == g_a_c == "red",
            "★★★★ 실제 실행 결과 — '취소'는 DP_ST·partner stTag·admin statusPill 모두 'red'",
            f"dp={g_dp_c} partner={g_p_c} adminMain={g_a_c}")

    # ============================================================
    print("\n[3] 종단 — (a) 실제 정적 파일 서빙  (b) 스크래치 DB + 실제 라우트 2개")
    # ------------------------------------------------------------
    _tmpdir = tempfile.mkdtemp(prefix="round681_")
    os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
    os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
    os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "app.log")
    os.environ["BOKGUON_ENV"] = "dev"
    os.environ["BOKGUON_SEED_DEMO"] = "0"
    sys.path.insert(0, HERE)

    import db as DB  # noqa: E402
    DB.init_db()
    import app as A  # noqa: E402

    # -- (a) 실제 정적 파일 서빙 파이프라인 --
    static_client = A.app.test_client()
    r_static = static_client.get("/static/admin.js")
    chk(r_static.status_code == 200, "  (a) GET /static/admin.js 준비 확인 — 200", r_static.status_code)
    served = r_static.get_data(as_text=True)
    chk("const DP_ST = {'모집중':'amber','수배됨':'blue','도착':'green','실패':'red','취소':'red'};" in served,
        "★★★★★ 실제로 서빙된 /static/admin.js 응답 바이트 안에 고친 DP_ST가 그대로 담겨 있다")

    # -- (b) 스크래치 DB에 5개 상태의 실제 출동 콜을 만들고, 실제 라우트 두 개로 조회 --
    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name, status, is_demo) VALUES (?, '활성', 0)",
        ("R681테스트보험사",)).lastrowid
    STATUSES = ["모집중", "수배됨", "도착", "실패", "취소"]
    case_ids = {}
    for i, st in enumerate(STATUSES):
        cno = f"R681-CASE-{i}"
        cid = conn.execute(
            """INSERT INTO cases(case_no, insurer, insurer_id, category, region, address, status,
                                  award_amount, low_price, is_demo, created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (cno, "R681테스트보험사", iid, "가드레일", "서울", "테스트로 1",
             "접수", 5000000, 4800000, 0, DB.now())).lastrowid
        conn.execute(
            "INSERT INTO dispatches(case_id, round, status, created_at) VALUES(?,1,?,?)",
            (cid, st, DB.now()))
        case_ids[st] = (cid, cno)
    conn.commit()
    conn.close()

    admin_client = A.app.test_client()
    conn2 = DB.get_db()
    conn2.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('r681admin','x','검증','중간관리자')")
    conn2.commit()
    conn2.close()
    with admin_client.session_transaction() as sess:
        sess["admin"] = "r681admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"

    insurer_client = A.app.test_client()
    with insurer_client.session_transaction() as sess:
        sess["insurer_id"] = iid; sess["insurer_name"] = "R681테스트보험사"

    r_admin = admin_client.get("/api/dispatches")
    chk(r_admin.status_code == 200, "  (b) GET /api/dispatches(관리자) 준비 확인 — 200", r_admin.status_code)
    admin_items = {it["case_no"]: it for it in (r_admin.get_json() or {}).get("items", [])}

    r_ins = insurer_client.get("/api/insurer/dashboard")
    chk(r_ins.status_code == 200, "  (b) GET /api/insurer/dashboard(보험사) 준비 확인 — 200", r_ins.status_code)
    insurer_cases = {c["case_no"]: c for c in (r_ins.get_json() or {}).get("cases", [])}

    for st in STATUSES:
        cid, cno = case_ids[st]
        a_item = admin_items.get(cno)
        i_case = insurer_cases.get(cno)
        chk(a_item is not None, f"  (b) 관리자 라우트 응답에 {cno}({st}) 출동 콜이 실제로 들어 있다")
        chk(i_case is not None and i_case.get("dispatch") is not None,
            f"  (b) 보험사 라우트 응답에 {cno}({st}) 사건·출동 정보가 실제로 들어 있다")
        if a_item and i_case and i_case.get("dispatch"):
            a_status = a_item.get("status")
            i_status = i_case["dispatch"].get("status")
            chk(a_status == st == i_status,
                f"★★★★★ '{st}' — 관리자·보험사 두 실제 라우트가 정확히 같은 원본 문자열을 내려준다"
                "(화면이 DP_ST()·stTag()에 넘기는 값이 이 문자열임을 실측)",
                f"admin={a_status!r} insurer={i_status!r}")

    # ============================================================
    print("\n[4] 되돌리기 — 잘라낸 (고친) DP_ST 소스 문자열 안에서만 3개 키를 옛 값으로 되돌려 재현")
    #      ⚠ 실제 파일은 전혀 건드리지 않는다.
    # ------------------------------------------------------------
    OLD_DP_ST_SRC = DP_ST_SRC.replace(
        "{'모집중':'amber','수배됨':'blue','도착':'green','실패':'red','취소':'red'}",
        "{'모집중':'blue','수배됨':'amber','도착':'green','실패':'red','취소':'gray'}")
    chk(OLD_DP_ST_SRC != DP_ST_SRC
        and "'모집중':'blue'" in OLD_DP_ST_SRC and "'수배됨':'amber'" in OLD_DP_ST_SRC
        and "'취소':'gray'" in OLD_DP_ST_SRC,
        "  (전제) 되돌린 사본에서 옛 값 3개가 실제로 들어갔다(실제 파일은 무변경)")

    out_old = run_node_probe(OLD_DP_ST_SRC, "[되돌린 옛 버전]")
    chk(out_old is not None, "  Node로 옛 버전(고치기 전 재현)을 실제 실행했다", str(out_old))
    if out_old:
        for s, old_expect in (("모집중", "blue"), ("수배됨", "amber"), ("취소", "gray")):
            g_dp_old = cls_of(out_old[s]["dp"])
            g_ins = cls_of(out_old[s]["insurer"])
            chk(g_dp_old == old_expect,
                f"★★★★★★ (인과관계 실측) 옛 코드라면 DP_ST는 '{s}'를 '{old_expect}'로 냈다",
                f"실제 값: {g_dp_old!r}")
            chk(g_dp_old != g_ins,
                f"★★★★★★ (인과관계 실측) 같은 옛 코드에서 '{s}'는 형제 insurer stTag와 다른 색을 "
                "냈다 — 즉 불일치가 실제로 재현된다(위 [2]의 지금 결과와 정반대 = 이번 수정이 "
                "실제로 이 불일치를 없앤 것)", f"dp={g_dp_old!r} insurer={g_ins!r}")
        # 안 건드린 두 키(도착·실패)는 옛 버전에서도 이미 일치했어야 한다(회귀 없음 sanity).
        for s in ("도착", "실패"):
            g_dp_old, g_ins = cls_of(out_old[s]["dp"]), cls_of(out_old[s]["insurer"])
            chk(g_dp_old == g_ins,
                f"  (회귀 없음) 옛 버전에서도 '{s}'는 이미 형제와 일치했다(이번 수정과 무관한 키)",
                f"dp={g_dp_old!r} insurer={g_ins!r}")

    # 실제 파일이 여전히 고친 상태 그대로인지 마지막으로 재확인(회귀 없음).
    chk("const DP_ST = {'모집중':'amber','수배됨':'blue','도착':'green','실패':'red','취소':'red'};"
        in read("static/admin.js"),
        "  (sanity) 실제 파일(디스크)은 여전히 고친 상태 그대로다(위 [4]는 메모리 문자열만 다뤘다)")
else:
    chk(False, "  [2]~[4] node가 없어 건너뛸 수밖에 없었다")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
