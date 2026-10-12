# -*- coding: utf-8 -*-
"""스캔 671라운드 회귀(직접조사, 하위위임 없음) — 협력사 포털 '시공 현장' 카드의
   '실사 증액 요청' 버튼이 사건 상태가 '완료보고지연'(낙찰 후 24시간이 지나면
   자동으로 붙는 상태 — 지방·주말 공사에서는 정상)일 때는 나타나지 않던 결함.

   조사 배경 — app.py api_change_order_create()(POST /api/cases/<id>/change-order,
   실사 후 증액 요청을 접수하는 유일한 창구)는
       if c["status"] not in ("시공중", "검수대기", "완료보고지연"):
   로 막는다 — 즉 서버는 이 세 상태를 전부 받는다. 그 함수 자신의 주석이 이유까지
   적어 둔다: "'완료보고지연'은 낙찰 후 24시간이 지나면 자동으로 붙는 상태다
   (지방·주말 공사에서는 정상). 그런데 증액 요청만 이 상태를 안 받아, 현장에서
   파손이 더 크다는 걸 확인한 업체가 요청 창구를 잃었다 ... 여기만 빠져 있었다"
   — 서버 쪽은 이미 그렇게 고쳐져 있었다.

   그런데 이 버튼을 실제로 그리는 templates/partner_portal.html RENDER.sites()는
   여전히 ['시공중','검수대기'].includes(c.status) 로만 걸었다 — '완료보고지연'이
   빠진 옛 2원소 집합 그대로였다. 같은 사건 카드의 바로 위 두 버튼(📷 촬영/앨범
   업로드 1542행 · 완료 보고 1554행)은 이미 '완료보고지연'을 포함하는 3원소·2원소
   조건으로 고쳐져 있고, 이 버튼 바로 위에 붙은 주석조차 "서버가 받는 상태와 같은
   집합을 쓴다"고 스스로 규칙을 적어 놨는데, 정작 이 버튼 자신은 그 규칙을 어기고
   있었다 — round645가 고친 상태색 드리프트, round670이 고친 dispatch_status 드리프트와
   같은 "형제는 고쳐졌는데 이 자리만 안 퍼졌다" 계열의 결함이다.

   실제 영향 — 낙찰 후 24시간 안에 완료 보고를 못 낸(흔한 지방·주말 공사) 협력사가
   현장에서 파손이 더 크다는 걸 뒤늦게 확인해도, '시공 현장' 카드에서 '실사 증액
   요청' 버튼 자체가 사라져 있어(같은 카드의 다른 두 버튼은 멀쩡히 남아 있다) 증액을
   요청할 방법이 없었다. 서버는 이미 받을 준비가 되어 있었으므로 손실은 순전히
   화면 쪽 누락이었다 — 정확히 그 서버 주석이 막으려던 상황이 화면에서는 여전히
   벌어지고 있었다.

   고침 — 조건을 ['시공중','검수대기','완료보고지연']로 서버와 맞춘다
   (templates/partner_portal.html, 단일 지점 수정). build_pages.py 재실행 +
   test_scan_round306_fixes.py(11/11) · test_template_js.py(9/9) 표준 재검증 완료.

   회귀테스트(이 파일) —
   [1] 소스 — partner_portal.html의 '실사 증액 요청' 버튼 조건과 app.py
       api_change_order_create()의 서버측 허용 상태 집합을 각각 정규식으로 뽑아
       (손으로 베끼지 않고 각자 소스에서 직접 파싱) 두 집합이 정확히 같음을 구조적
       으로 확인한다. '완료보고지연'이 그 집합 안에 있음·옛 2원소 조건이 이 버튼
       자리에 더는 없음도 함께 확인한다.
   [2] 단위 — [1]에서 실제 템플릿 파일 그대로 잘라낸 배열 리터럴 텍스트를 손으로
       다시 타이핑하지 않고 node로 직접 실행해, 시공중·검수대기·완료보고지연
       세 상태 모두 true, 정산진행·완료 두 상태는 여전히 false임을 증명한다.
   [3] 종단 — (a) 실제 Flask 렌더 파이프라인(render_template, test_template_js.py와
       같은 호출)으로 partner_portal.html을 그려, 렌더된 실제 HTML/JS 안에도 고쳐진
       조건이 그대로 들어 있음을 재확인한다(Jinja가 이 구간을 건드리지 않음을 렌더
       결과로 직접 증명). (b) 스크래치 DB + 실제 Flask 라우트
       (POST /api/cases/<id>/change-order)로 status='완료보고지연'인 내 낙찰 사건에
       실제 증액 요청을 접수해 200이 남을 실측 — 화면이 이제 보여주는 버튼이 가짜가
       아니라 서버가 실제로 받아 주는 진짜 창구임을 증명한다.
   [4] 되돌리기 — [2]에서 잘라낸 배열 리터럴 텍스트에서 '완료보고지연'만 제거한
       사본(실제 파일은 무변경, 문자열로만 재구성)을 같은 node 실행에 넣으면 그
       상태만 false로 바뀌어 고치기 전 결함이 그대로 재현됨을 실측 — 이 테스트가
       실제로 그 결함을 잡을 수 있었음을 증명한다.

   templates/partner_portal.html만 변경 — API 라우트·DB 스키마 무변경(서버측 허용
   집합은 원래부터 3원소였고 이번에 손대지 않았다), static 무변경. 재기동 후
   BUILD_HASH 로테이션 필요(static/templates 해시 대상).

       python test_scan_round671_fixes.py
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


def func_src(src, header):
    """round253이 확립한 함수경계 슬라이스 — header부터 다음 '@app.'나
    최상위 'def ' 직전까지."""
    i = src.find(header)
    if i < 0:
        return ""
    m = re.search(r"\n(?:@app\.|def )", src[i + len(header):])
    return src[i:i + len(header) + m.start()] if m else src[i:]


print("=" * 72)
print("  스캔 671라운드 회귀 — partner_portal.html '실사 증액 요청' 버튼의 "
      "'완료보고지연' 누락")
print("=" * 72)

APP_SRC = read("app.py")
TPL_SRC = read("templates/partner_portal.html")

# ============================================================
print("\n[1] 소스 확인 — 화면 조건과 서버 허용집합이 실제로 같은가")
# ------------------------------------------------------------
REESTIMATE_RE = re.compile(
    r"\(\[([^\]]*)\]\.includes\(c\.status\)\s*&&\s*canAct\(\)\)\s*\?\s*`<button[^`]*"
    r'data-reestimate="\$\{c\.id\}"'
)
m_front = REESTIMATE_RE.search(TPL_SRC)
chk(m_front is not None, "★ partner_portal.html에서 '실사 증액 요청' 버튼 조건을 찾았다")
FRONT_ARR_TEXT = m_front.group(1) if m_front else ""
FRONT_SET = set(re.findall(r"'([^']*)'", FRONT_ARR_TEXT))
chk(bool(FRONT_ARR_TEXT), "  (전제) 배열 리터럴 텍스트를 실제로 뽑았다", FRONT_ARR_TEXT)

CO_FN_SRC = func_src(APP_SRC, "def api_change_order_create(cid):")
chk(CO_FN_SRC != "", "api_change_order_create() 함수를 실제로 찾았다")
SERVER_RE = re.compile(r'c\["status"\]\s*not in\s*\(([^)]*)\)')
m_server = SERVER_RE.search(CO_FN_SRC)
chk(m_server is not None, "★ api_change_order_create()에서 서버 허용 상태 검사를 찾았다")
SERVER_ARR_TEXT = m_server.group(1) if m_server else ""
SERVER_SET = set(re.findall(r'"([^"]*)"', SERVER_ARR_TEXT))
chk(bool(SERVER_ARR_TEXT), "  (전제) 서버측 튜플 텍스트를 실제로 뽑았다", SERVER_ARR_TEXT)

chk("완료보고지연" in SERVER_SET,
    "  (전제) 서버는 실제로 '완료보고지연'을 증액 요청 허용 상태로 받는다", SERVER_SET)
chk("완료보고지연" in FRONT_SET,
    "★★★★★ 화면 버튼 조건도 이제 '완료보고지연'을 포함한다(핵심 수정 지점)", FRONT_SET)
chk(FRONT_SET == SERVER_SET,
    "★★★★★ 화면 조건 집합과 서버 허용 집합이 정확히 같다(옆 주석 자신의 규칙을 "
    "이제 이 버튼도 지킨다)", (FRONT_SET, SERVER_SET))
chk(len(FRONT_SET) == 3, "  화면 조건이 정확히 3개 상태다(2개짜리 옛 조건이 아니다)", FRONT_SET)

OLD_BROKEN_RE = re.compile(
    r"\(\['시공중','검수대기'\]\.includes\(c\.status\)\s*&&\s*canAct\(\)\)\s*\?\s*`<button[^`]*"
    r'data-reestimate='
)
chk(OLD_BROKEN_RE.search(TPL_SRC) is None,
    "  옛 결함 조건(['시공중','검수대기']만, 완료보고지연 누락)이 이 버튼 자리에 "
    "더는 없다")

# ============================================================
print("\n[2] 단위 — 실제 템플릿에서 그대로 잘라낸 배열 리터럴을 node로 직접 실행")
# ------------------------------------------------------------
NODE = shutil.which("node")
if not NODE:
    print("\n  ✖ node를 찾을 수 없습니다. 이 검사는 node로 JS 배열 리터럴을 직접 "
          "실행해 증명합니다.")
    sys.exit(2)

_scratch = tempfile.mkdtemp(prefix="round671_js_")


def _node_status_check(arr_text):
    """arr_text(예: "'시공중','검수대기','완료보고지연'")를 그대로 배열 리터럴에 "
    "넣어 각 상태에 대한 .includes() 결과를 JSON으로 돌려준다."""
    statuses = ["시공중", "검수대기", "완료보고지연", "정산진행", "완료"]
    script = (
        "const arr = [" + arr_text + "];\n"
        "const statuses = " + json.dumps(statuses, ensure_ascii=False) + ";\n"
        "const out = {};\n"
        "for (const s of statuses) out[s] = arr.includes(s);\n"
        "console.log(JSON.stringify(out));\n"
    )
    p = os.path.join(_scratch, "check.js")
    io.open(p, "w", encoding="utf-8").write(script)
    r = subprocess.run([NODE, p], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"node 실행 실패: {r.stderr}")
    return json.loads(r.stdout.strip())


result_fixed = _node_status_check(FRONT_ARR_TEXT)
for st, expect in (("시공중", True), ("검수대기", True), ("완료보고지연", True),
                   ("정산진행", False), ("완료", False)):
    chk(result_fixed.get(st) == expect,
        f"★★★ node 실행 — 상태 '{st}' → includes() == {expect}", result_fixed)

# ============================================================
print("\n[3] 종단 실행 — 실제 Flask 렌더 + 실제 라우트로 재현")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round671_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB  # noqa: E402
DB.init_db()
import app as A  # noqa: E402
from flask import render_template  # noqa: E402

# -- (a) 실제 렌더 파이프라인으로 partner_portal.html을 그려, 렌더 결과에도
#        고쳐진 조건이 그대로 있는지 확인 (test_template_js.py와 같은 호출) --
with A.app.test_request_context("/app/partner"):
    rendered_html = render_template("partner_portal.html", nonce="testnonce", build="t", ver="t")
m_rendered = REESTIMATE_RE.search(rendered_html)
chk(m_rendered is not None,
    "  (a) 실제 렌더된 HTML/JS 안에도 '실사 증액 요청' 버튼 조건이 있다")
chk(bool(m_rendered) and "완료보고지연" in set(re.findall(r"'([^']*)'", m_rendered.group(1))),
    "★★★★★★ (a) 실제 Flask 렌더 결과(파일을 직접 읽은 게 아니라 서버가 실제로 "
    "내보내는 HTML)에도 '완료보고지연'이 포함된 조건이 그대로 들어 있다")

# -- (b) 스크래치 DB + 실제 라우트로, '완료보고지연' 사건에 실제 증액 요청 접수 --
conn = DB.get_db()
pid = conn.execute(
    "INSERT INTO partners(name, partner_type, status, created_at) VALUES(?,?,?,?)",
    ("R671테스트업체", "시공사", "활성", DB.now())).lastrowid
cid = conn.execute(
    """INSERT INTO cases(case_no, insurer, category, region, address, status,
                          partner_id, award_amount, low_price, is_demo, created_at)
       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
    ("R671-CASE-A", "테스트보험사", "가드레일", "서울", "테스트로 1",
     "완료보고지연", pid, 5000000, 4800000, 0, DB.now())).lastrowid
conn.commit()
conn.close()

CSRF = "r671-csrf"
client = A.app.test_client()
with client.session_transaction() as sess:
    sess["partner_id"] = pid
    sess["partner_name"] = "R671테스트업체"
    sess["_csrf"] = CSRF

resp = client.post(f"/api/cases/{cid}/change-order",
                    headers={"X-CSRF-Token": CSRF},
                    json={"reason": "실측 재현용 사유 5자 이상", "requested_amount": "500000"})
chk(resp.status_code == 200,
    "  (b) POST /api/cases/<id>/change-order 준비 확인 — 200", resp.status_code)
body = resp.get_json() or {}
chk(bool(body.get("ok")),
    "★★★★★★ (b) status='완료보고지연'인 내 낙찰 사건도 실제 증액 요청 라우트가 "
    "그대로 접수한다(화면이 이제 보여주는 버튼은 서버가 실제로 받아 주는 진짜 "
    "창구다) — id=%s" % body.get("id"), body)

# ============================================================
print("\n[4] 되돌리기 — '완료보고지연'만 제거한 사본으로 결함 재현 (실제 파일 무변경)")
# ------------------------------------------------------------
chk("완료보고지연" in FRONT_ARR_TEXT,
    "  (준비) 잘라낸 배열 텍스트 안에 '완료보고지연'이 실제로 있다(제거 대상 확인)")
BROKEN_ARR_TEXT = re.sub(r",?'완료보고지연'", "", FRONT_ARR_TEXT)
chk("완료보고지연" not in BROKEN_ARR_TEXT,
    "  (준비) 되돌린 사본에는 '완료보고지연'이 없다", BROKEN_ARR_TEXT)
chk(set(re.findall(r"'([^']*)'", BROKEN_ARR_TEXT)) == {"시공중", "검수대기"},
    "  (준비) 되돌린 사본은 정확히 고치기 전의 그 2원소 결함 집합과 같다",
    BROKEN_ARR_TEXT)

result_broken = _node_status_check(BROKEN_ARR_TEXT)
chk(result_broken.get("완료보고지연") is False,
    "★★★★★★ (인과관계 실측) '완료보고지연'을 되돌린 옛 조건(실제 파일은 안 건드림)은 "
    "같은 상태에서 버튼을 안 보여준다 — 위 [2]의 실제(고쳐진) 결과와 정반대", result_broken)
chk(result_broken.get("시공중") is True and result_broken.get("검수대기") is True,
    "  되돌린 사본에서도 나머지 두 상태는 그대로 true다(이 버튼이 결함 이전에도 "
    "완전히 죽어 있던 건 아니었다는 전제 확인)", result_broken)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
