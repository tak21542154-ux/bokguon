# -*- coding: utf-8 -*-
"""GitHub Pages 용 정적 사이트 빌드 — 복구온 **서비스 소개면만**.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

무엇을 만드는가
  · 서비스 소개(랜딩) + 법정 게시물(처리방침·이용약관·사업자정보)
  · 회사 정보는 data/company_info.json 의 실제 값이 박혀 나간다

무엇을 만들지 '않는가' — 만들 수 없다
  · 로그인·입찰·낙찰·정산·사진검수는 전부 서버가 처리한다(라우트 85개 중 69개가 API).
    GitHub Pages 는 정적 파일만 서빙하므로 이 기능들은 올릴 수 없다.
  · 도입문의·입점신청 '폼 제출'도 서버가 받는다. 정적 사이트에서는 접수가 불가능하므로
    **전화·이메일 문의로 바꿔서** 내보낸다(작동하지 않는 폼을 남겨 두면 문의가 조용히 유실된다).

실행:  python build_pages.py       →  docs/ 폴더 생성
"""
import io
import os
import re
import shutil
import sys

#  ⚠ 윈도 기본 콘솔은 cp949 라 '—' 같은 문자를 print 하면 UnicodeEncodeError 로
#    죽는다(아래 drop_unfilled_rows() 의 "표 밖 자리표시자" 줄, build() 의
#    "docs/ 생성 완료" 줄). 형제 점검 도구(check_tx_paths.py 등)가 이미 쓰는
#    방어를 그대로 옮긴다(round519).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

#  ⚠⚠ [라운드108] 이 스크립트만 공유 .env 로더(envload.py — 그 파일 자신의
#    docstring이 "app.py/wsgi.py/serve_waitress.py/manage.py 전부가 공유한다"고
#    적어 둔 목록)를 안 썼다. 그래서 아래 ADMIN_IP_ALLOW 조회가 .env 의
#    BOKGUON_ADMIN_IP_ALLOW 값을 못 보고 항상 "미설정"으로만 읽혔다.
import envload
envload.load_dotenv()

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "docs")
TPL = os.path.join(HERE, "templates")

# 문의 창구 — 폼을 못 쓰는 대신 실제로 닿는 경로로 바꾼다
TEL = "1533-7120"
MAIL = "c.common@olymposnetworks.com"

# 실서비스(백엔드) 주소. 지정하면 소개면의 '보험사·협력사 포털' 버튼이 그쪽으로 연결된다.
#   예)  BOKGUON_SERVICE_URL=https://bokguon.olymposnetworks.com  python build_pages.py
# 비워 두면 포털 버튼은 문의 창구로 대체된다(죽은 링크를 만들지 않는다).
SERVICE_URL = (os.environ.get("BOKGUON_SERVICE_URL") or "").rstrip("/")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _write(rel, html):
    dst = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(html)
    return dst


def strip_jinja(html, depth=0):
    """서버 전용 구문을 정적 등가물로 바꾼다."""
    up = "../" * depth
    html = html.replace("{{ asset('fonts.css') }}", f"{up}static/fonts.css")
    html = html.replace("{{ url_for('static', filename='favicon.svg') }}", f"{up}static/favicon.svg")
    html = re.sub(r"""\s*nonce="\{\{\s*csp_nonce\s*\}\}\"""", "", html)

    # ── 서비스워커 등록 스크립트도 공개면에서 통째로 제거 ─────────────
    #  ⚠⚠ [라운드230] landing.html 의 이 스크립트는 **서버가 직접 호스팅할 때**만
    #    뜻이 있다 — /sw.js 는 서버가 굳이 루트에서 서빙한다(app.py 주석: "스코프가
    #    '/' 가 되어야 설치·오프라인 셸을 제어한다"). 그런데 이 정적 빌드는
    #    static/ 를 통째로 docs/static/ 로만 옮겨(sw.js 도 거기로만 간다), 루트엔
    #    아무것도 없다 — 실측: 실제 배포된 docs/index.html 이 여전히 '/sw.js' 를
    #    그대로 등록 시도해 조용히 404(.catch 로 감춰짐)만 낸다. 설령 경로를
    #    맞춰도 sw.js 자신이 __APP_VERSION__·__BUILD__ 자리표시자를 그대로 담고
    #    있고(서버 라우트가 실행 시점에 채워 주는 값, 정적 빌드엔 그 서버가 없다),
    #    캐시할 목록에 static/actions.js·form.js(바로 아래에서 admin.js 등과 함께
    #    이 빌드가 의도적으로 빼는 파일들)까지 들어 있어 어차피 못 채운다.
    #    소개면 하나뿐인 정적 사이트가 얻을 게 없는 반쪽 PWA 를 어설프게
    #    흉내내는 대신, 효과 없이 매 방문마다 헛요청만 내는 블록을 지운다.
    #  ⚠ strip_jinja() 는 landing.html·legal.html 양쪽에 다 쓰인다 — legal.html
    #    에는 이 스크립트 자체가 없으므로, "serviceWorker" 언급이 있을 때만
    #    시도하고 그때만 실패를 하드에러로 다룬다(없는 템플릿에서 오탐 방지).
    if "serviceWorker" in html:
        _before_sw = html
        html = re.sub(
            r"<script\b[^>]*>(?:(?!</script>).)*?register\('/sw\.js'\)(?:(?!</script>).)*?</script>",
            "", html, flags=re.S)
        if html == _before_sw:
            raise SystemExit("서비스워커 등록 스크립트를 못 찾았습니다 — landing.html 이 바뀌었는지 확인하세요.")

    # ── 체험 계정 안내 블록은 **공개면에서 통째로 제거** ──────────────
    #  서버 화면에서는 내부 시연용으로 계정을 띄울 수 있지만(BOKGUON_SHOW_DEMO_HINT),
    #  이 정적 사이트는 인터넷 전체에 열리는 소개면이다. 계정이 새어 나가면 안 되므로
    #  조건과 무관하게 블록 자체를 삭제한다(값이 아니라 마크업을 지운다).
    html = re.sub(r"\{%\s*if\s+show_demo_hint\s*%\}.*?\{%\s*endif\s*%\}", "", html, flags=re.S)
    #  마크업만 지우면 잔여 CSS 와 주석이 남는다. 스타일 자체는 무해하지만
    #  "내부 시연용 체험 계정 …" 주석과 환경변수 이름이 공개면 소스에 남으면
    #  숨은 기능의 존재와 스위치 이름을 그대로 광고하는 셈이라 함께 지운다.
    html = re.sub(r"/\*[^*]*체험 계정[^*]*\*/\s*", "", html)
    html = re.sub(r"^\.f-demo[^{]*\{[^}]*\}\s*", "", html, flags=re.M)
    #  .f-demo 만 다루는 반응형 규칙도 통째로(중괄호 2겹) 제거
    html = re.sub(r"^@media[^{]*\{\s*\.f-demo[^{]*\{[^}]*\}\s*\}\s*", "", html, flags=re.M)

    # 남은 Jinja 가 있으면 화면에 그대로 노출되므로 실패로 처리한다
    leftover = re.findall(r"\{\{.*?\}\}|\{%.*?%\}", html)
    if leftover:
        raise SystemExit(f"처리 못 한 Jinja 구문이 남았습니다: {leftover[:3]}")
    return html


def drop_unfilled_rows(html):
    """아직 정하지 않은 수탁자 행은 공개면에서 뺀다.

    이 소개 사이트에서는 정산이 일어나지 않으므로 PG 위탁도 없다.
    계약도 안 한 곳을 '(미기재)' 상태로 수탁자 표에 걸어 두면
    보는 사람에게는 미완성 고지로, 사실관계로는 부정확한 공개가 된다.
    실제로 위탁 중인 곳만 남긴다(서버 배포본에는 그대로 두어 운영자가 채우게 한다).

    ⚠⚠ [라운드294] 예전엔 페이지 전체에서 "(미기재)"가 들어간 <tr> 을
    닥치는 대로 지웠다 — 그런데 _ph() 의 그 표시 방식은 처리방침 제12조의
    개인정보 보호책임자·연락처 행, 사업자정보의 통신판매업 신고번호·
    대표전화·개인정보 보호책임자 행에도 똑같이 쓰인다. 그 값이 하나라도
    비면(운영 중 재설정 등) 자리표시자만 지워지는 게 아니라 행 전체
    (제목 칸까지)가 통째로 사라져, 전자상거래법 §10·개인정보 보호법 §30
    가 요구하는 표시의무 항목이 "표시 안 됨"이 아니라 "애초에 없던 항목"
    처럼 보였다(실측: company_info.json 에서 dpo·mail_order_no 를 비우고
    실제로 빌드해 재현 — 두 표에서 행이 통째로 사라짐. 현재 운영값은
    전부 채워져 있어 지금 당장 발현 중은 아니다). 제6조(위탁) 표만
    정확히 그 절 범위로 좁힌다 — 그 절이 아예 없는 문서(약관·사업자정보)
    는 손대지 않는다.
    """
    SECTION_START = "<h3>제6조 (개인정보 처리의 위탁)</h3>"
    start = html.find(SECTION_START)
    if start < 0:
        return html          # 이 절이 없는 문서(약관·사업자정보)는 대상 아님
    next_h3 = html.find("<h3>", start + len(SECTION_START))
    end = next_h3 if next_h3 >= 0 else len(html)
    section = html[start:end]

    before = section.count("(미기재)")
    section = re.sub(r"<tr>(?:(?!</tr>).)*?\(미기재\)(?:(?!</tr>).)*?</tr>", "", section, flags=re.S)
    after = section.count("(미기재)")
    if after:
        # 표 밖에 남은 자리표시자는 문장 중간이라 통째로 지우면 문맥이 깨진다.
        # 눈에 띄지 않게 다듬되, 남아 있다는 사실은 빌드 로그로 알린다.
        print(f"  ⚠ 표 밖 자리표시자 {after}곳 — 문구 확인 필요")
    if before - after:
        print(f"  미확정 수탁자 {before - after}행 제외(공개면)")
    return html[:start] + section + html[end:]


def fix_links(html, depth=0):
    """서버 경로 → 정적 경로. 폼 페이지는 전화·이메일로 대체."""
    up = "../" * depth
    html = html.replace('href="/static/', f'href="{up}static/')
    html = html.replace('src="/static/', f'src="{up}static/')
    for key in ("privacy", "terms", "business"):
        html = html.replace(f'href="/legal/{key}"', f'href="{up}legal/{key}.html"')
    html = html.replace('href="/"', f'href="{up}index.html"')

    # 접수 폼은 서버가 필요하다. 안내 문구와 함께 실제 연락처로 돌린다.
    html = html.replace('href="/apply/insurer"', f'href="tel:{TEL}"')
    html = html.replace('href="/apply/partner"', f'href="mailto:{MAIL}?subject=복구온 입점 신청 문의"')
    html = html.replace("보험사 도입 문의 →", f"보험사 도입 문의 {TEL} →")
    html = html.replace("시행사·시공사 입점 신청", "시행사·시공사 입점 문의")

    # ── 포털·관리자 링크 (정적 사이트에는 백엔드가 없다) ──────────────
    #  ⚠ 이 처리가 없으면 공개된 소개면에 /insurer·/partner·/admin 링크가 그대로 남아
    #     ① 누르면 404 가 나고 ② **관리자 콘솔 경로가 외부에 광고**된다.
    #  · 실서비스 주소(BOKGUON_SERVICE_URL)가 있으면 그쪽으로 연결한다.
    #  · 없으면 죽은 링크를 만들지 않고 문의 창구로 돌린다.
    #  · 관리자 콘솔 링크는 **어떤 경우에도 공개면에서 제거**한다.
    html = re.sub(r'<a\b[^>]*class="[^"]*\bf-admin\b[^"]*"[^>]*>.*?</a>', "", html, flags=re.S)
    if SERVICE_URL:
        html = html.replace('href="/insurer"', f'href="{SERVICE_URL}/insurer"')
        html = html.replace('href="/partner"', f'href="{SERVICE_URL}/partner"')
    else:
        html = html.replace('href="/insurer"', f'href="tel:{TEL}"')
        html = html.replace('href="/partner"', f'href="mailto:{MAIL}?subject=복구온 협력사 포털 문의"')
    html = html.replace('href="/admin"', f'href="tel:{TEL}"')   # 잔여 방어
    return html


def build():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT, exist_ok=True)

    # 1) 랜딩 → index.html
    html = _read(os.path.join(TPL, "landing.html"))
    html = fix_links(strip_jinja(html, 0), 0)
    #  ★ canonical 은 **실주소가 있을 때만** 넣는다.
    #    종전에는 템플릿에 bokguon.olymposnetworks.com 이 박혀 있었는데
    #    그 도메인은 DNS 에 없다(조회 실패). robots.txt 는 Allow: / 이므로,
    #    검색엔진은 "정본은 저 주소" 라는 말을 믿고 **실제로 뜨는 이 페이지를
    #    색인에서 내린다.** 없는 주소를 가리키느니 canonical 을 안 쓰는 게 맞다
    #    (없으면 지금 열린 URL 이 곧 정본이다).
    if SERVICE_URL:
        html = html.replace(
            "</head>", f'<link rel="canonical" href="{SERVICE_URL}/">\n</head>', 1)
    _write("index.html", html)

    # 2) 법정 게시물 (실제 회사 정보가 박혀 나간다)
    import legal_docs as LEGAL
    #  ⚠⚠ [라운드108] app.py:2018-2020 의 서버 라우트는 이미 "처리방침은 실제
    #    설정과 같은 말을 해야 한다"며 privacy 를 특별 처리하는데, 이 정적
    #    빌드는 그 특례 없이 doc["body"] 원문을 그대로 썼다. 실측: .env 의
    #    BOKGUON_ADMIN_IP_ALLOW 가 비어 있어 그 접근통제는 실제로 시행되지
    #    않는데(app.py 의 두 가드가 통째로 건너뜀), GitHub Pages 로 나가는
    #    공개 처리방침엔 "관리자 콘솔 접속 IP 제한을 시행 중"이라고 계속
    #    적혀 있었다 — 서버 라우트와 똑같은 규칙을 여기도 적용한다.
    _admin_ip_allow = bool([x.strip() for x in
                            (os.environ.get("BOKGUON_ADMIN_IP_ALLOW", "") or "").split(",")
                            if x.strip()])
    #  ⚠⚠ [라운드317] app.py 의 legal_page() 와 같은 이유 — 이 정적 빌드도
    #    로그인잠금·세션만료·로그보관기간 실제 운영값을 반영해야 한다.
    _max_login_fails = int(os.environ.get("BOKGUON_MAX_LOGIN_FAILS", "5") or "5")
    _session_min = int(os.environ.get("BOKGUON_SESSION_MIN", "30") or "30")
    _log_retention_days = int(os.environ.get("BOKGUON_LOG_RETENTION_DAYS", "730") or "730")
    #  ⚠⚠ [라운드508] app.py 의 legal_page() 와 같은 이유 — photo_ai.py 가 실제로
    #    쓰는 것과 같은 판정(BOKGUON_GEMINI_KEY 존재 여부)을 그대로 재사용한다
    #    (photo_ai 모듈을 여기서 새로 import 하지 않는다 — 이 파일은 이미
    #    envload.load_dotenv() 로 os.environ 을 채워 뒀으므로 직접 조회로 충분하고,
    #    바로 위 세 값과 같은 방식이다).
    _ai_photo_enabled = bool((os.environ.get("BOKGUON_GEMINI_KEY", "") or "").strip())
    shell = _read(os.path.join(TPL, "legal.html"))
    for key, doc in LEGAL.DOCS.items():
        page = shell
        if key == "privacy" and hasattr(LEGAL, "privacy_body"):
            doc = dict(doc)
            doc["body"] = LEGAL.privacy_body(
                _admin_ip_allow, max_login_fails=_max_login_fails,
                session_min=_session_min, log_retention_days=_log_retention_days,
                ai_photo_enabled=_ai_photo_enabled)
        # legal.html 은 서버에서 doc·key·pending 을 주입한다. 같은 자리를 채워 넣는다.
        page = page.replace("{{ doc.title }}", doc["title"])
        page = page.replace("{{ doc.sub }}", doc.get("sub", ""))
        page = page.replace("{{ doc.body|safe }}", doc["body"])
        # 현재 페이지 표시 — {% if key=='xxx' %}aria-current="page"{% endif %}
        page = re.sub(r"\{%\s*if key=='(\w+)'\s*%\}(.*?)\{%\s*endif\s*%\}",
                      lambda m: m.group(2) if m.group(1) == key else "", page, flags=re.S)
        # 미기재 경고 블록({% if pending %}…)은 운영자용이므로 공개면에서 제거
        page = re.sub(r"\{%\s*if pending\s*%\}.*?\{%\s*endif\s*%\}", "", page, flags=re.S)
        page = re.sub(r"\{%.*?%\}", "", page, flags=re.S)      # 남은 제어구문 정리
        page = drop_unfilled_rows(page)
        page = fix_links(strip_jinja(page, 1), 1)
        _write(f"legal/{key}.html", page)

    # 3) 정적 자산 (글꼴 포함 — 외부 CDN 을 쓰지 않으므로 통째로 옮긴다)
    shutil.copytree(os.path.join(HERE, "static"), os.path.join(OUT, "static"),
                    ignore=shutil.ignore_patterns("admin.js", "admin.css", "actions.js", "form.js"))

    #  ⚠⚠ [라운드230] manifest.webmanifest 도 절대경로(도메인 루트 기준)를 그대로
    #    담고 있다 — 실서버는 루트에 뜨지만 이 정적 사이트는 GitHub Pages
    #    **프로젝트** 사이트라 서브경로(예: <계정>.github.io/<저장소>/)에 뜬다
    #    (바로 위 안내문서가 이 주소 형태를 그렇게 안내한다). "/" 를 그대로
    #    두면 설치 시도 시 시작주소·스코프가 계정 루트로 잘못 잡히고,
    #    "/static/icons/..." 도 계정 루트 기준이라 아이콘이 깨진다. manifest
    #    파일과 아이콘은 항상 static/ 밑에 나란히 있으므로, 그 파일 자신을
    #    기준으로 한 상대경로로 바꾸면 서브경로든 루트든 항상 맞는다.
    _mf_path = os.path.join(OUT, "static", "manifest.webmanifest")
    _mf = _read(_mf_path)
    _mf2 = _mf.replace('"start_url": "/"', '"start_url": ".."')
    _mf2 = _mf2.replace('"scope": "/"', '"scope": ".."')
    _mf2 = re.sub(r'"src": "/static/', '"src": "', _mf2)
    if _mf2 == _mf:
        raise SystemExit("manifest.webmanifest 의 절대경로를 못 찾았습니다 — 파일이 바뀌었는지 확인하세요.")
    #  shortcuts.url 도 같은 문제다 — fix_links() 가 본문 <a href="/insurer"> 에
    #    이미 적용하는 것과 같은 규칙(실서비스 주소가 있으면 그쪽, 없으면 죽은
    #    링크를 만들지 않는다)을 그대로 따른다. 다만 이건 tel:/mailto: 로
    #    바꿀 수 없다 — PWA 바로가기는 같은 출처(웹) URL이어야 브라우저가
    #    받아 준다. 실서비스 주소가 없으면 바로가기 자체를 통째로 뺀다
    #    (가리킬 곳 없는 바로가기를 목록에 남기지 않는다).
    if SERVICE_URL:
        _mf2 = _mf2.replace('"url": "/insurer"', f'"url": "{SERVICE_URL}/insurer"')
        _mf2 = _mf2.replace('"url": "/partner"', f'"url": "{SERVICE_URL}/partner"')
    else:
        _mf2 = re.sub(r',?\s*"shortcuts":\s*\[.*?\]', "", _mf2, flags=re.S)
    with open(_mf_path, "w", encoding="utf-8") as f:
        f.write(_mf2)

    # 4) GitHub Pages 가 _ 로 시작하는 경로를 Jekyll 로 처리하지 않도록
    _write(".nojekyll", "")

    # 5) 검색엔진 안내 — 소개면만 있으므로 전체 허용
    _write("robots.txt", "User-agent: *\nAllow: /\n")

    n = sum(len(f) for _, _, f in os.walk(OUT))
    print(f"  docs/ 생성 완료 — 파일 {n}개")
    #  ⚠⚠ [라운드306] 이 자리는 위 docs/ 를 이미 다 쓴 뒤, 요약 출력 한 줄만을
    #    위해 company_info.json 을 **독립적으로 다시** 읽고 있었다(legal_docs
    #    는 위 201행에서 이미 import 해 두고도 안 씀) — 그런데 이 자리만 아무
    #    보호가 없어, set-info 를 한 번도 안 한 상태(파일 없음, 정상 상태)에서
    #    build_pages.py 를 돌리면 실제 빌드는 이미 성공했는데도 이 마지막
    #    줄에서 FileNotFoundError 로 죽어 exit 1 이 됐다(deploy/외부공개_안내.md
    #    가 안내하는 `python build_pages.py && git add docs && git commit`
    #    같은 셸이면 성공한 빌드를 커밋 안 하고 건너뛴다). 121라운드가 정확히
    #    이 파일에 대해 이미 세운 방어(파일 없음=정상, 그 외 오류=경고만)를
    #    다시 구현하는 대신, 그 방어가 이미 적용된 legal_docs.INFO 를 그대로
    #    재사용한다(위 201행의 import 로 이미 로드돼 있다 — 다시 읽지 않는다).
    info = LEGAL.INFO
    #  ⚠⚠ [라운드294] len(info) 는 JSON 키 개수일 뿐이다 — 키는 있는데 값이
    #    비었거나 공백뿐이면(legal_docs.py _ph() 기준으로는 "미기재") 여기선
    #    그대로 채워진 것으로 세어져, 실제로는 표시행이 빠진 채로 빌드됐는데도
    #    "8/8 반영"이라고 찍힐 수 있었다(실측: dpo·tel 을 빈 문자열로 두고
    #    빌드 — "미확정 수탁자 N행 제외" 경고와 "8/8 반영"이 같은 실행에서
    #    동시에 찍힘). _ph() 와 같은 기준(비거나 공백뿐이면 미기재)으로 센다.
    filled = sum(1 for v in info.values() if (v or "").strip())
    #  ⚠ 분모를 8로 박아 두면(2026-10-18 PG 항목 삭제로 INFO_FIELDS 가 8→7이
    #    된 것처럼) 항목이 늘거나 줄 때마다 조용히 틀린 비율을 찍는다 — 실제
    #    정의(len(LEGAL.INFO_FIELDS))를 그대로 읽는다.
    print(f"  회사 정보 {filled}/{len(LEGAL.INFO_FIELDS)} 반영")
    print(f"  문의 창구: 전화 {TEL} · 메일 {MAIL}")


if __name__ == "__main__":
    build()
