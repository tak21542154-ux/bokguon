# -*- coding: utf-8 -*-
"""스캔 319라운드 회귀 — templates/offline.html·case_history.html·
   insurer_api_guide.html 세 화면의 유일한 버튼이 CSP 에 막혀 죽어있던 결함
   [경미], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견(legal.html 은 이번
   조사로 전담 클린 확정 — 재조사 불필요).

   app.py 의 _security_headers 가 모든 응답에 예외 없이
   `script-src 'self' 'nonce-{요청별 난수}'`(unsafe-inline 없음)를 붙인다.
   nonce 는 우리가 작성한 <script> 블록에만 붙을 자리가 있고, onclick="..."
   같은 인라인 이벤트 핸들러에는 애초에 붙일 자리가 없어 모든 최신 브라우저가
   무조건 차단한다 — 바로 이 이유로 static/actions.js(이벤트 위임 디스패처)가
   이미 만들어져 있고 템플릿 40여 개 중 37개가 이미 이 패턴으로 전환돼 있는데,
   offline.html의 '다시 시도'·case_history.html/insurer_api_guide.html의
   '인쇄 / PDF 저장' 세 버튼만 옛 onclick= 그대로 남아 있었다. 500/에러 응답이
   아니라 200 OK + 브라우저 콘솔 CSP 위반 경고 하나로만 나타나 서버 쪽 회귀
   테스트로는 원천적으로 못 잡는 종류의 결함이다.

   무거운 actions.js 전체를 새로 얹는 대신(세 페이지 다 이미 안 쓰고 있었다),
   각자 id + nonce 가 붙은 짧은 <script> 로 addEventListener 를 직접 연결했다.
"""
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_scratch = tempfile.mkdtemp(prefix="bokguon_r319_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_scratch, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"

import db as DB  # noqa: E402
DB.init_db(seed_demo=True)
import app as A  # noqa: E402

PASS = FAIL = 0
FAILED = []


def chk(cond, msg, detail=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {msg}")
    else:
        FAIL += 1
        FAILED.append(msg)
        print(f"  [FAIL] {msg}" + (f"   {detail}" if detail else ""))


print("=" * 74)
print("  스캔 319라운드 회귀 — CSP 가 막는 인라인 onclick 3곳")
print("=" * 74)

TEMPLATES = ["offline.html", "case_history.html", "insurer_api_guide.html"]

#  ⚠ 옛 결함을 설명하는 주석 자신이 'onclick="..."' 문구를 그대로 인용하므로
#    (313라운드가 겪은 것과 같은 자기참조 함정), 실제 버튼 태그의 기능적
#    사용(<button onclick=)만 좁혀서 찾는다 — 산문 인용과 헷갈리지 않는다.
_ONCLICK_TAG = re.compile(r"<button\s+onclick=")

print("\n[1] 소스 확인 — 세 템플릿 모두 <button onclick= 가 더는 없다")
for t in TEMPLATES:
    src = open(os.path.join(HERE, "templates", t), encoding="utf-8").read()
    chk(_ONCLICK_TAG.search(src) is None,
        f"★★★★ {t} 에 더는 <button onclick= 인라인 핸들러가 없다")
    chk('nonce="{{ csp_nonce }}"' in src,
        f"★★★ {t} 가 nonce 붙은 <script> 로 버튼을 연결한다")


def _extract_nonce_from_csp(resp):
    csp = resp.headers.get("Content-Security-Policy", "")
    m = [p for p in csp.split(";") if "script-src" in p]
    if not m or "'nonce-" not in m[0]:
        return None
    return m[0].split("'nonce-")[1].split("'")[0]


def check_route(client, path, btn_id, handler_snippet, label):
    r = client.get(path)
    body = r.get_data(as_text=True)
    chk(r.status_code == 200, f"  {label} — {path} 200 응답", r.status_code)
    chk(_ONCLICK_TAG.search(body) is None, f"★★★★ {label} — 실제 응답에 <button onclick= 이 전혀 없다")
    chk(f'id="{btn_id}"' in body, f"  {label} — 버튼에 id={btn_id!r} 이 실제로 렌더된다")
    chk(handler_snippet in body, f"  {label} — addEventListener 코드가 실제로 렌더된다")
    #  ★ 가장 중요한 검증 — 스크립트에 박힌 nonce 가 실제 CSP 헤더의 nonce 와
    #    정확히 같은지. 다르면 브라우저가 이 스크립트 자체를 통째로 차단한다
    #    (nonce 불일치는 nonce 가 아예 없는 것과 같은 실패 방식).
    hdr_nonce = _extract_nonce_from_csp(r)
    chk(bool(hdr_nonce), f"  {label} — CSP 헤더에 script-src nonce 가 있다", r.headers.get("Content-Security-Policy"))
    if hdr_nonce:
        chk(f'nonce="{hdr_nonce}"' in body,
            f"★★★★★ {label} — 응답 본문의 <script nonce=...> 값이 CSP 헤더의 nonce 와 정확히 일치한다"
            "(실제 브라우저가 이 스크립트를 실행할 조건)", hdr_nonce)


print("\n[2] 실행 — 실제 /offline 라우트(인증 불필요)")
client = A.app.test_client()
check_route(client, "/offline", "retryBtn", "location.reload()", "오프라인 셸")

#  ⚠ /docs/insurer-api 는 데코레이터가 아니라 함수 안에서 직접
#    session.get("admin") or insurer_id 를 확인한다(17983행) — 로그인 안 한
#    클라이언트는 /insurer/login 으로 302 된다. 아래 두 라우트 모두 같은
#    관리자 세션으로 확인한다.
admin_row = DB.get_db().execute("SELECT username FROM admins LIMIT 1").fetchone()
with client.session_transaction() as sess:
    sess["admin"] = admin_row["username"] if admin_row else "admin"

print("\n[3] 실행 — 실제 /docs/insurer-api 라우트(관리자 세션)")
check_route(client, "/docs/insurer-api", "printBtn", "window.print()", "발주처 연동안내서")

print("\n[4] 실행 — 실제 /report/case/<id> 라우트(인증 필요 — 하위관리자 이상)")
conn = DB.get_db()
conn.execute("BEGIN IMMEDIATE")
now = DB.now()
cur = conn.execute(
    "INSERT INTO cases(case_no,insurer,category,region,address,status,is_demo,created_at,status_at)"
    " VALUES(?,?,?,?,?,?,0,?,?)",
    ("319테스트", "테스트보험", "유리·샷시·자동문", "서울", "서울시 강남구", "정산대기", now, now))
cid = cur.lastrowid
conn.commit()
check_route(client, f"/report/case/{cid}", "printBtn", "window.print()", "사건 이력 리포트")

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
