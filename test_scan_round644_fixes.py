# -*- coding: utf-8 -*-
"""스캔 644라운드 회귀(직접조사, 하위위임 없음) — 시행사(협력사) 포털 stTag() 의
   '시공중' 태그 색이 보험사 포털·운영 콘솔과 어긋나 있던 결함.

   조사 배경 — 상태값→색상 매핑은 이 저장소에 사실상 세 형제로 존재한다.
     · templates/insurer_portal.html  stTag(s)   (보험사 포털)
     · templates/partner_portal.html  stTag(s)   (시행사·시공사 포털)
     · static/admin.js                statusPill(s) (운영 콘솔)
   세 함수는 이름·모양만 다를 뿐 같은 상태 어휘(입찰중·완료·시공중…)에 같은
   색을 내야 한다는 것이 이미 이 코드베이스 자신의 전제다 — insurer_portal.html
   327~328행 주석이 그 근거다: "partner_portal.html stTag 는 이미 … red 로
   고쳐 놨다"(라운드75가 '취소'를 두 stTag 에 동시에 맞춘 이력). 즉 이 두
   stTag 는 "형제이니 매핑을 동기화해야 한다"는 규칙이 이미 이 저장소
   안에서 명시적으로 선언돼 있다.

   그런데 실측: 세 매핑 중 겹치는 17개 상태값을 전수 대조하면 '시공중'
   딱 하나만 partner_portal.html 이 'blue', 나머지 둘(insurer_portal.html·
   admin.js)은 'green' 이었다 — 취소·유찰·완료 등 다른 16개는 세 곳 모두
   완전히 일치한다. 도달 가능성도 낮지 않다: '시공중'은 낙찰 직후 가장 흔한
   상태값이고, caseDetail() 모달 헤더(partner_portal.html 360·395행,
   `<h3>${esc(c.case_no)} ${stTag(c.status)}</h3>` — insurer_portal.html
   834행과 완전히 같은 패턴)가 그 값을 그대로 stTag() 에 넘긴다. 그 결과
   시행사가 자기 낙찰 건을 열면 파란 "시공중", 같은 사건을 보험사가 열면
   초록 "시공중" — 같은 사실을 두 포털이 다른 색으로 말한다.

   고침 — templates/partner_portal.html 의 stTag() 매핑에서 '시공중'을
   'blue' → 'green' 으로 바꿔 insurer_portal.html·admin.js 와 맞춘다(다수
   의견 2/3 + 운영 콘솔 자체가 그 다수에 포함된다는 점을 근거로 green 을
   정답으로 판단 — round75 가 세운 "형제 stTag 동기화" 원칙을 그대로 적용).
   같은 파일 RENDER.sites 카드(1505행 부근)의 별도 인라인 색상 조건문은
   건드리지 않았다 — 그건 stTag() 와 무관한, 이 파일 안에서만 자기완결적인
   조건식이라 "형제 불일치" 증거가 없다(다음 라운드가 참고할 별도 후보로만
   남긴다).

   회귀테스트(이 파일) —
   [1] 소스 — 세 매핑에서 '시공중' 값을 직접 뽑아 셋 다 'green'으로 일치함을
       확인. round75 의 전제(같은 두 stTag 가 서로 동기화 대상이라는 주석)도
       여전히 남아 있는지 확인한다(전제 자체가 없어지면 이 결함의 근거도
       바뀌므로).
   [2] 단위 — 세 함수 정의를 파일에서 그대로 잘라내(손으로 다시 타이핑하지
       않음) Node.js 로 실제 실행해 stTag('시공중')·statusPill('시공중')
       결과 HTML 문자열의 색상 클래스가 셋 다 'tag green'/'pill green'으로
       일치함을 실측 증명한다.
   [3] 되돌리기 — 실제 파일은 전혀 건드리지 않고, [2]에서 잘라낸 (지금 고친)
       partner stTag 소스 문자열 안에서 '시공중':'green' 한 곳만 다시
       'blue'로 치환한 옛 버전을 독립 Node 스크립트로 만들어, 그 옛 버전이
       실제로 insurer_portal.html·admin.js 와 다른 색을 냈음을(초록 vs 파랑)
       재현 실측한다.
   [4] 종단 — 실제 Flask 템플릿 렌더(로그인 세션 없이 render_template 직접
       호출 — test_template_js.py 와 같은 기법)로 partner_portal.html·
       insurer_portal.html 을 그대로 그려, 서버가 실제로 내보내는 HTML 안에
       고친 매핑이 살아 있는지 확인한다.

       python test_scan_round644_fixes.py
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
    """header(예: 'function stTag(s){')부터, 그 뒤 처음 나오는 '줄 첫머리 단독
    닫는 중괄호'(\\n})까지 — 이 파일들의 stTag/statusPill 은 내부에 중첩 블록이
    없어(객체 리터럴은 세미콜론과 같은 줄에서 닫힌다) 이 경계 찾기로 충분하다."""
    i = src.find(header)
    if i < 0:
        return ""
    j = src.find("\n}", i + len(header))
    return src[i:j + 2] if j >= 0 else ""


print("=" * 72)
print("  스캔 644라운드 회귀 — partner_portal.html stTag() '시공중' 색상 불일치")
print("=" * 72)

PARTNER_SRC = read("templates/partner_portal.html")
INSURER_SRC = read("templates/insurer_portal.html")
ADMIN_SRC = read("static/admin.js")

# ============================================================
print("\n[1] 소스 확인 — 세 매핑에서 '시공중' 값 직접 대조")
# ------------------------------------------------------------
_pat = re.compile(r"'시공중':\s*'([a-z]+)'")


def find_color(src, label):
    m = _pat.search(src)
    chk(m is not None, f"  {label} 매핑에서 '시공중' 항목을 찾았다")
    return m.group(1) if m else None


c_partner = find_color(PARTNER_SRC, "partner_portal.html stTag")
c_insurer = find_color(INSURER_SRC, "insurer_portal.html stTag")
c_admin = find_color(ADMIN_SRC, "admin.js statusPill")

chk(c_partner == "green",
    "★★★★★ partner_portal.html stTag() 의 '시공중' 이 이제 'green' 이다(고치기 전엔 'blue')",
    f"실제 값: {c_partner!r}")
chk(c_insurer == "green",
    "  (회귀 없음) insurer_portal.html stTag() 의 '시공중' 은 여전히 'green'", f"실제 값: {c_insurer!r}")
chk(c_admin == "green",
    "  (회귀 없음) admin.js statusPill() 의 '시공중' 은 여전히 'green'", f"실제 값: {c_admin!r}")
chk(c_partner == c_insurer == c_admin,
    "★★★★★ 세 매핑의 '시공중' 색이 완전히 일치한다(형제 함수 동기화 완료)",
    f"partner={c_partner!r} insurer={c_insurer!r} admin={c_admin!r}")

chk("partner_portal.html stTag 는 이미" in INSURER_SRC,
    "  전제 확인 — insurer_portal.html 에 '두 stTag 는 동기화 대상' 이라는 "
    "round75 의 근거 주석이 여전히 남아 있다(이 결함의 근거)")

# 다른 겹치는 상태값은 원래부터 세 곳 모두 일치해야 한다 — 이번 수정이
# '시공중' 이외의 값을 건드리지 않았는지 함께 확인한다(회귀 없음 보증).
#  ⚠ 파일 전체가 아니라 각 함수의 **잘라낸 몸통 안에서만** 찾는다 — admin.js
#    는 6800줄이 넘어, 파일 전체를 뒤지면 statusPill() 매핑과 무관한 곳에서
#    같은 글자가 우연히 걸릴 수 있다(실측: 이 대조 초안이 그렇게 걸렸다).
_STTAG_P_BODY = func_src_brace(PARTNER_SRC, "function stTag(s){")
_STTAG_I_BODY = func_src_brace(INSURER_SRC, "function stTag(s){")
_PILL_A_BODY = func_src_brace(ADMIN_SRC, "function statusPill(s){")


def _color_in(body, s):
    m = re.search(re.escape(f"'{s}':") + r"'([a-z]+)'", body)
    return m.group(1) if m else None


_all_keys = set(re.findall(r"'([가-힣]+)':'[a-z]+'", _STTAG_P_BODY)) \
    & set(re.findall(r"'([가-힣]+)':'[a-z]+'", _STTAG_I_BODY)) \
    & set(re.findall(r"'([가-힣]+)':'[a-z]+'", _PILL_A_BODY))
_all_keys.discard("시공중")
chk(len(_all_keys) >= 10,
    "  (전제) '시공중' 말고도 세 매핑에 공통으로 존재하는 상태값이 충분히 있다"
    "(대조군이 성립한다)", f"{len(_all_keys)}개: {sorted(_all_keys)}")
_mismatch = []
for s in sorted(_all_keys):
    vals = {_color_in(_STTAG_P_BODY, s), _color_in(_STTAG_I_BODY, s), _color_in(_PILL_A_BODY, s)}
    if len(vals) != 1:
        _mismatch.append((s, _color_in(_STTAG_P_BODY, s), _color_in(_STTAG_I_BODY, s),
                           _color_in(_PILL_A_BODY, s)))
chk(not _mismatch,
    f"  (회귀 없음) '시공중' 이외 공통 상태값 {len(_all_keys)}개는 세 매핑이 여전히 전부 일치한다",
    str(_mismatch))

# ============================================================
print("\n[2] 단위 — 세 함수를 파일에서 그대로 잘라내 Node.js 로 직접 실행")
# ------------------------------------------------------------
NODE = shutil.which("node")
if not NODE:
    chk(False, "node 실행파일을 찾을 수 없다 — 이 구간은 건너뛰지 않고 실패로 답한다")
    NODE = None

ESC_LINE = re.search(r"const esc = s =>.*?;\n", PARTNER_SRC).group(0)
chk(ESC_LINE in INSURER_SRC and ESC_LINE in ADMIN_SRC,
    "  (전제) esc() 헬퍼가 세 파일에서 바이트 단위로 동일하다(그대로 재사용 가능)")

STTAG_PARTNER = func_src_brace(PARTNER_SRC, "function stTag(s){")
STTAG_INSURER = func_src_brace(INSURER_SRC, "function stTag(s){")
STATUSPILL_ADMIN = func_src_brace(ADMIN_SRC, "function statusPill(s){")
chk(bool(STTAG_PARTNER) and bool(STTAG_INSURER) and bool(STATUSPILL_ADMIN),
    "  세 함수 소스를 실제 파일에서 전부 잘라냈다",
    f"len={len(STTAG_PARTNER)}/{len(STTAG_INSURER)}/{len(STATUSPILL_ADMIN)}")
chk("시공중':'green'" in STTAG_PARTNER,
    "  (전제) 잘라낸 partner stTag 조각 안에 고친 값이 실제로 들어 있다")

# 이름이 둘 다 stTag() 라 한 스크립트에 같이 넣으려면 식별자만 바꿔야 한다.
# 몸통(상태→색 매핑·return 문)은 한 글자도 바꾸지 않는다.
STTAG_PARTNER_R = STTAG_PARTNER.replace("function stTag(s){", "function stTagPartner(s){", 1)
STTAG_INSURER_R = STTAG_INSURER.replace("function stTag(s){", "function stTagInsurer(s){", 1)
chk(STTAG_PARTNER_R != STTAG_PARTNER and STTAG_PARTNER_R.count("stTagPartner") == 1,
    "  (harness) partner 함수명만 바꿨다(본문은 그대로)")
chk(STTAG_INSURER_R != STTAG_INSURER and STTAG_INSURER_R.count("stTagInsurer") == 1,
    "  (harness) insurer 함수명만 바꿨다(본문은 그대로)")


def run_node_probe(sttag_partner_src, label):
    """세 함수를 한 Node 스크립트에 모아 '시공중' 하나만 넣고 실행한다."""
    script = (
        ESC_LINE + "\n"
        + sttag_partner_src + "\n\n"
        + STTAG_INSURER_R + "\n\n"
        + STATUSPILL_ADMIN + "\n\n"
        + "console.log(JSON.stringify({"
        + "partner: stTagPartner('시공중'), "
        + "insurer: stTagInsurer('시공중'), "
        + "admin: statusPill('시공중')}));\n"
    )
    _tmp = tempfile.mkdtemp(prefix="round644_node_")
    p = os.path.join(_tmp, "probe.js")
    io.open(p, "w", encoding="utf-8").write(script)
    try:
        #  ⚠ 윈도 콘솔 기본 코드페이지(cp949)로 자동 디코드하면 Node 가
        #    UTF-8 로 낸 '시공중' 등이 UnicodeDecodeError 로 죽는다 — 인코딩을
        #    명시한다(이 저장소의 다른 subprocess 호출과 같은 방어).
        r = subprocess.run([NODE, p], capture_output=True, text=True,
                            encoding="utf-8", timeout=15)
    finally:
        try:
            os.remove(p); os.rmdir(_tmp)
        except OSError:
            pass
    if r.returncode != 0:
        chk(False, f"  {label} Node 실행 실패", (r.stderr or "")[:300])
        return None
    try:
        return json.loads(r.stdout.strip())
    except Exception as e:
        chk(False, f"  {label} Node 출력 파싱 실패", f"{e}: {r.stdout[:200]}")
        return None


if NODE:
    out_new = run_node_probe(STTAG_PARTNER_R, "[지금 고친 버전]")
    chk(out_new is not None, "  Node 로 지금 버전(고친 뒤) 세 함수를 실제 실행했다", str(out_new))
    if out_new:
        def cls_of(html):
            m = re.search(r'class="(?:tag|pill) ([a-z]+)"', html)
            return m.group(1) if m else None

        g_partner, g_insurer, g_admin = (cls_of(out_new[k]) for k in ("partner", "insurer", "admin"))
        chk(g_partner == "green" and g_insurer == "green" and g_admin == "green",
            "★★★★★★ 실제 실행 결과 — stTagPartner·stTagInsurer·statusPill 셋 다 "
            "'시공중'에 green 클래스를 낸다(형제 일치를 런타임으로 증명)",
            f"partner={g_partner} insurer={g_insurer} admin={g_admin}")
        chk("시공중" in out_new["partner"] and "시공중" in out_new["insurer"],
            "  (전제) 실행 결과 문자열 안에 상태 라벨 '시공중' 자체도 정상적으로 들어 있다")

    # ============================================================
    print("\n[3] 되돌리기 — 잘라낸 (고친) 소스 문자열 안에서만 옛 값으로 되돌려 재현")
    #      ⚠ 실제 파일은 전혀 건드리지 않는다. STTAG_PARTNER_R(메모리 문자열)
    #        안의 '시공중':'green' 딱 한 곳만 다시 'blue' 로 바꿔 옛 상태를
    #        재구성한다.
    # ------------------------------------------------------------
    OLD_PARTNER_R = STTAG_PARTNER_R.replace("'시공중':'green'", "'시공중':'blue'", 1)
    chk(OLD_PARTNER_R != STTAG_PARTNER_R and "'시공중':'blue'" in OLD_PARTNER_R,
        "  (전제) 되돌린 사본에 옛(고치기 전) 값 'blue' 가 들어갔다(실제 파일은 무변경)")

    out_old = run_node_probe(OLD_PARTNER_R, "[되돌린 옛 버전]")
    chk(out_old is not None, "  Node 로 옛 버전(고치기 전 재현) 세 함수를 실제 실행했다", str(out_old))
    if out_old:
        og_partner, og_insurer, og_admin = (cls_of(out_old[k]) for k in ("partner", "insurer", "admin"))
        chk(og_partner == "blue" and og_insurer == "green" and og_admin == "green",
            "★★★★★★ (인과관계 실측) 옛 코드라면 시행사 포털만 파란 '시공중', "
            "보험사 포털·운영 콘솔은 초록 '시공중' — 실제로 색이 갈렸다"
            "(위 [2]의 지금 결과와 정반대 = 이번 수정이 실제로 이 불일치를 없앤 것)",
            f"partner={og_partner} insurer={og_insurer} admin={og_admin}")
else:
    chk(False, "  [3] 되돌리기 검증 — node 가 없어 건너뛸 수밖에 없었다(위 [2]와 같은 사유)")

# ============================================================
print("\n[4] 종단 — 실제 Flask 템플릿 렌더(로그인 세션 없이, test_template_js.py 와 같은 기법)")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round644_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "app.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import app as A  # noqa: E402
from flask import render_template  # noqa: E402

with A.app.test_request_context("/partner"):
    html_partner = render_template("partner_portal.html", nonce="testnonce", build="t", ver="t")
with A.app.test_request_context("/insurer"):
    html_insurer = render_template("insurer_portal.html", nonce="testnonce", build="t", ver="t")

chk("'시공중':'green'" in html_partner,
    "★★★★★ 실제로 렌더된 partner_portal.html 응답 안에 고친 매핑이 그대로 살아 있다")
chk("'시공중':'blue'" not in html_partner,
    "★★★★★ 실제로 렌더된 partner_portal.html 응답에 옛(파란) 값이 더는 없다")
chk("'시공중':'green'" in html_insurer,
    "  (회귀 없음) insurer_portal.html 렌더 결과는 원래대로 green 을 유지한다")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
