# -*- coding: utf-8 -*-
"""스캔 510라운드 회귀 — valid_website() 가 스킴 이름 한가운데 탭/개행이 낀
"java<TAB>script:..." 류 값을 "스킴 없음"으로 오판해 통과시키던 결함.

  직접 조사(하위위임 없음) — run_all_tests.py 전체를 먼저 정독해 이미
  포화된 축(형제 엔드포인트 잠금 비대칭 504~507, 정책문서 불일치
  289·317·508)과 라운드509 가 남긴 꼬리(insurer_portal.html·
  partner_portal.html 등 admin.js 외 템플릿의 href/src 주입 전수 확인)를
  먼저 훑었다 — 사진 URL 은 전부 photos.id 기반 서버생성값(app.py:12414·
  14840·14850·14855), notiOpen() 의 location.href 는 notify() 호출 117곳
  전수 확인 결과 전부 하드코딩 리터럴이거나 안전한 정수 보간이라(스크립트로
  기계적 전수확인) 클린이었다. 그러다 라운드509 자신이 **막 추가한**
  valid_website()(app.py:5525, 아직 이 세션 이전에는 아무도 재검증하지
  않은 새 코드)를 정밀히 다시 읽다가, 정규식 자체의 스킴 판정 로직에서
  새로운 결함을 발견했다.

  결함: _RE_URL_SCHEME = r"^\\s*([a-zA-Z][a-zA-Z0-9+.\\-]*):" 의 스킴
  문자클래스에는 탭(\\t)·개행(\\n\\r) 이 없다. 그런데 브라우저는 URL 의
  스킴을 읽기 **전에** ASCII 탭·개행을 문자열 어디에 있든 전부 제거한다
  (WHATWG URL 표준 "remove all ASCII tab or newline" — jav&#9;ascript: 류
  필터 우회는 PortSwigger XSS 치트시트에도 실린 잘 알려진 기법이다). 그
  결과 "java<TAB>script:alert(1)" 을 정규식에 넣으면 "java" 뒤에 콜론이
  아니라 탭이 와서 매치가 실패하고, valid_website() 는 "스킴을 못 찾았다
  = 위험한 스킴이 없다"로 오판해 True(통과)를 돌려준다 — 정작 그 값을
  href 에 넣고 클릭하면 브라우저는 탭을 지운 뒤 진짜 "javascript:" 로
  실행한다. esc() 가 막는 &<>"' 다섯 문자를 하나도 안 쓰므로 라운드509 가
  막으려던 것과 완전히 같은 등급상승 경로(가장 낮은 등급인 하위관리자가
  세 진입로 중 하나로 website 를 심고, 그 업체의 연락처 수정창을 여는
  어떤 관리자든 클릭하면 그 세션에서 실행)가 그대로 재발한다. 개행
  변형은 엑셀 셀에서 Alt+Enter 한 번이면 생겨 탭보다도 더 자연스러운
  입력 경로다.

  이 세션이 실제 Claude 브라우저로 직접 실측 확인했다 — 정적 HTML 을
  로컬 HTTP 서버로 띄운 뒤 href="java<TAB>script:...코드..." 인 <a> 를
  실제로 클릭시켜(자바스크립트 .click() 은 실제 클릭과 동일한 링크추적
  경로를 탄다), 페이지의 다른 엘리먼트 텍스트가 그 스크립트에 의해
  실제로 바뀌고 console.log 가 실제로 찍히는 것을 확인했다(탭·개행 두
  변형 전부). 곧 valid_website("java\\tscript:alert(1)") 을 실제로
  호출하면 True 가 나오는 것을 이 세션이 직접 재현했다 — round509 의
  회귀테스트(payload 는 전부 "javascript:..." 처럼 스킴이 문자열 맨
  앞에 온전히 붙어 있는 모양만 검증)는 이 모양을 다루지 않아 못 잡았다.

  영향 범위: valid_website() 는 세 진입로(api_partner_create·
  api_partner_update·api_contact_import 엑셀 일괄등록) 가 공유하는 단일
  관문이라 셋 다 동시에 뚫려 있었다 — admin.js ctEdit() 의 렌더 쪽 방어
  (http/https 로 시작할 때만 <a href> 로 건다, 스킴 없는 값 취급이라
  탭이 섞인 값은 애초에 "http" 로 시작하지 않아 링크가 안 걸린다)가
  현재 알려진 유일한 렌더 지점에서는 두 번째 방어선 역할을 해 실제
  클릭 경로는 막아 주지만, 그건 이 값이 **저장은 이미 허용된 뒤의**
  우연한 보험일 뿐 — valid_website() 자신의 계약("위험한 스킴이 없으면
  True")은 깨져 있고, 다른 진입로나 향후 화면이 이 함수만 믿고 href 에
  꽂으면 그대로 뚫린다(라운드509 자신이 이 서버쪽 검사를 "옛 데이터·
  다른 진입로에 대비한 방어심화"라고 부른 이유이기도 하다).

  고침: valid_website() 안에서 스킴 판정 **전에** 브라우저와 같은 문자
  (ASCII 탭·CR·LF)를 지운다 — `v = re.sub(r"[\\t\\r\\n]", "", v or "")`.
  단일 공유 함수 안의 한 줄만 고치면 세 진입로가 동시에 다 고쳐진다.
  저장값 자체는 바꾸지 않는다(판정에만 쓰고, 통과/거부는 기존과 똑같이
  이분법 그대로 — 호출부 3곳은 전혀 안 건드렸다).

  [1] 소스 — valid_website() 본문에 새 코드가 정확히 한 번 있다.
  [2] 실행 — 서브프로세스(하위관리자 세션, 세 진입로 전부)로 탭·개행이
      낀 페이로드가 실제로 400/스킵 처리되고 DB 에 안 남는지, 정상값
      (https:// · 스킴 없는 도메인)은 그대로 통과하는지(과잉차단 아님)
      확인. 순수 함수 자체도 같은 프로세스에서 여러 변형(탭·개행·CR·
      스킴 중간/양끝)으로 직접 호출해 확인.
  [3] 되돌림-증명 — valid_website() 를 라운드509 까지의 구현(탭 제거
      한 줄이 없는 버전)으로 **런타임에** 되돌려(파일은 안 건드린다 —
      이 함수는 DB·세션 등 외부상태가 없는 순수함수라 안전하다) 같은
      배터리를 다시 돌리면, 탭·개행 낀 페이로드가 세 진입로 전부에서
      실제로 200 으로 통과해 DB 에 원문 그대로(탭·개행 문자 포함)
      저장되는 옛 결함이 재현됨을 실측 확인.

      python test_scan_round510_fixes.py
"""
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 510라운드 회귀 — valid_website() 탭/개행 스킴 우회")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — valid_website() 본문 확인")
# ──────────────────────────────────────────────────────────────
vw_body = _body(APP_SRC, "valid_website")
NEW_LINE = 'v = re.sub(r"[\\t\\r\\n]", "", v or "")'
chk(APP_SRC.count(NEW_LINE) == 1,
    "★★★ 새 코드(탭·CR·LF 제거)가 파일 전체에 정확히 1번 있다")
chk(NEW_LINE in vw_body,
    "★★★ 그 새 코드가 valid_website() 함수 **본문 안**에 있다")
chk("[라운드510]" in vw_body,
    "valid_website() 독스트링에 라운드510 표식이 있다")
chk(APP_SRC.count("def valid_website(") == 1,
    "valid_website() 정의가 정확히 1번만 있다(중복 정의 없음)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 순수 함수 직접 호출(같은 프로세스)")
# ──────────────────────────────────────────────────────────────
import tempfile

_tmpdir = tempfile.mkdtemp(prefix="round510_unit_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    UNIT_CASES = [
        ("javascript:alert(1)", False, "라운드509 대조군 — 순수 javascript: 는 여전히 거부"),
        ("vbscript:alert(1)", False, "라운드509 대조군 — vbscript: 는 여전히 거부"),
        ("data:text/html,x", False, "라운드509 대조군 — data: 는 여전히 거부"),
        ("https://example.com", True, "라운드509 대조군 — https:// 는 여전히 통과"),
        ("http://example.co.kr/x", True, "라운드509 대조군 — http:// 는 여전히 통과"),
        ("example.com", True, "라운드509 대조군 — 스킴 없는 값은 여전히 통과(과잉차단 아님)"),
        ("java\tscript:alert(1)", False, "★★★★★ 스킴 중간 탭 — 이제 거부된다(이 라운드의 핵심)"),
        ("java\nscript:alert(1)", False, "★★★★★ 스킴 중간 개행(LF) — 이제 거부된다"),
        ("java\rscript:alert(1)", False, "★★★★★ 스킴 중간 개행(CR) — 이제 거부된다"),
        ("vbscr\nipt:alert(1)", False, "★ vbscript 에도 같은 우회가 통했었다 — 이제 거부"),
        ("\tjavascript:alert(1)", False, "선두 탭(라운드509 시절에도 이미 걸렸음, 회귀 없음)"),
    ]
    for payload, expected, label in UNIT_CASES:
        got = A.valid_website(payload)
        chk(got == expected, label, f"valid_website({payload!r}) = {got}, expected {expected}")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 순수 함수 직접 호출 준비/실행", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 서브프로세스(하위관리자 세션, 세 진입로 전부)")
# ──────────────────────────────────────────────────────────────


def run_worker(revert=False):
    args = [sys.executable, "-u", os.path.join(HERE, "test_scan_round510_worker.py")]
    if revert:
        args.append("--revert")
    r = subprocess.run(args, capture_output=True, text=True, timeout=120,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"워커 실패(exit={r.returncode})\nstdout={r.stdout}\nstderr={r.stderr}")
    line = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("{")][-1]
    return json.loads(line)


try:
    d = run_worker(revert=False)

    chk(d.get("create_tab_status") == 400,
        "★★★★★ create — 탭이 낀 javascript: 페이로드는 400으로 거부", d.get("create_tab_body"))
    chk(d.get("create_good_status") == 200,
        "create — 정상 https:// 값은 200 통과")

    chk(d.get("update_tab_status") == 400,
        "★★★★★ update — 탭이 낀 페이로드는 400으로 거부", d.get("update_tab_body"))
    chk(d.get("db_website_after_tab_attempt") is None,
        "★★★★★ update — 거부된 탭 페이로드가 DB 에 반영되지 않았다(NULL 유지)",
        d.get("db_website_after_tab_attempt"))
    chk(d.get("update_nl_status") == 400,
        "★★★★★ update — 개행(LF)이 낀 페이로드도 400으로 거부")
    chk(d.get("update_good_status") == 200 and d.get("db_website_after_good") == "https://example.com",
        "update — 정상 https:// 값은 실제로 저장된다", d.get("db_website_after_good"))

    chk(d.get("import_nl_status") == 200 and (d.get("import_nl_body") or {}).get("updated") == 0
        and (d.get("import_nl_body") or {}).get("skipped_invalid") == 1,
        "★★★★★ contact_import — 개행 낀 페이로드 행은 스킵+보고되고 갱신 0건", d.get("import_nl_body"))
    chk(d.get("db_website_after_import_nl") == "https://example.com",
        "★★★★★ contact_import — 스킵된 값이 기존 저장값을 덮어쓰지 않았다",
        d.get("db_website_after_import_nl"))
    chk(d.get("import_good_bare_status") == 200
        and (d.get("import_good_bare_body") or {}).get("updated") == 1,
        "contact_import — 스킴 없는 정상 값은 그대로 갱신된다(과잉차단 아님)",
        d.get("import_good_bare_body"))
    chk(d.get("db_website_after_import_good") == "example.com",
        "contact_import — 정상 값이 실제로 저장됐다", d.get("db_website_after_import_good"))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 서브프로세스(고친 코드) 준비/실행", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌림-증명 — valid_website() 를 라운드509 까지의 구현으로 되돌리면")
# ──────────────────────────────────────────────────────────────
try:
    broken = run_worker(revert=True)

    chk(broken.get("create_tab_status") == 200,
        "★★★★★ 옛 코드(되돌림) — create 가 탭 낀 페이로드를 200으로 그대로 저장한다",
        broken.get("create_tab_body"))
    chk(broken.get("update_tab_status") == 200,
        "★★★★★ 옛 코드(되돌림) — update 도 탭 낀 페이로드를 200으로 그대로 통과시킨다",
        broken.get("update_tab_body"))
    chk(broken.get("db_website_after_tab_attempt") == "java\tscript:alert(document.cookie)",
        "★★★★★ 옛 코드(되돌림) — 탭 문자가 리터럴 그대로 DB 에 저장된다(실제 취약 재현)",
        repr(broken.get("db_website_after_tab_attempt")))
    chk(broken.get("update_nl_status") == 200,
        "★★★★★ 옛 코드(되돌림) — 개행 낀 페이로드도 200으로 통과한다")
    chk(broken.get("import_nl_status") == 200
        and (broken.get("import_nl_body") or {}).get("updated") == 1,
        "★★★★★ 옛 코드(되돌림) — 엑셀 일괄등록도 개행 낀 페이로드를 그대로 반영한다(updated=1)",
        broken.get("import_nl_body"))
    chk(broken.get("db_website_after_import_nl") == "java\nscript:alert(document.cookie)",
        "★★★★★ 옛 코드(되돌림) — 개행 문자가 리터럴 그대로 DB 에 저장된다(실제 취약 재현)",
        repr(broken.get("db_website_after_import_nl")))
    # 정상 값은 옛 코드에서도 당연히 통과해야 한다(이 라운드가 손댄 게
    # "위험한 스킴 오판" 이지 "정상값 처리" 가 아님을 대조로 확인)
    chk(broken.get("create_good_status") == 200 and broken.get("update_good_status") == 200,
        "대조군 — 옛 코드에서도 정상 https:// 값은 여전히 통과한다(회귀 지점 특정)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 서브프로세스(되돌림) 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
