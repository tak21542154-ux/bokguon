# -*- coding: utf-8 -*-
"""복구온 배포 스모크 테스트

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

배포 직후 "실제로 서비스가 도는가"를 사람이 클릭하지 않고 확인한다.
공개면 → 3자 포털 인증 → 권한 격리 → 핵심 업무 흐름 → 보안 방어 순으로 실행한다.

  python smoke_test.py                        기본 http://127.0.0.1:8771
  python smoke_test.py https://도메인          운영 서버 대상
  python smoke_test.py --skip-write           읽기 검사만 (운영 데이터에 쓰지 않음)

표준 라이브러리만 사용한다(requests 불필요).
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import ssl
import zlib
import struct
import secrets
import json
import http.cookiejar
import urllib.request
import urllib.error

#  운영(prod)은 세션 쿠키에 Secure 를 걸어 파이썬 http.cookiejar 가 http 로는
#  쿠키를 안 보낸다 → dev 모드 인스턴스를 띄워 BOKGUON_TEST_BASE 로 가리킬 것.
BASE = os.environ.get("BOKGUON_TEST_BASE", "http://127.0.0.1:8771")

# ── 검증용 자격증명 ────────────────────────────────────────────
#  ⚠ 비밀번호를 파일에 적어 두면, 비밀번호를 바꿔도 옛 값이 저장소에 남는다.
#    (실제로 데모 비번이 인터넷에 열린 적이 있다) 환경변수로만 받는다.
def _cred(env):
    return os.environ.get(env, "").strip()


def _creds_or_skip(*envs):
    missing = [e for e in envs if not _cred(e)]
    if missing:
        print("=" * 66)
        print("  [건너뜀] 검증용 계정 비밀번호가 설정되지 않았습니다.")
        print("           " + " / ".join(missing))
        print("=" * 66)
        return False
    return True


SKIP_WRITE = False

PASS, FAIL, SKIP = [], [], []

#  ⚠⚠ [라운드285] 관리자·협력사·보험사 로그인 3곳(admin/partner/insurer)은 계정
#    자체가 db.py:seed() 의 데모 값으로 **하드코딩**돼 있다. manage.py go-live —
#    모든 실운영 배포의 필수·문서화된 단계(DEPLOY.md 49행이 스스로 "다음 단계
#    go-live 가 그 이름을 지운다"고 미리 경고한다) — 는 admins.admin/staff 를
#    DELETE 하고 partners/insurers.login_id='partner'|'insurer'|'insurer2' 를
#    login_id=NULL 로 만든다. 그 순간부터 이 세 로그인은 **어떤 비밀번호를
#    넣어도 영원히 실패**하는데, 이 실패는 "데모 비밀번호가 이미 교체됨(운영
#    서버에서는 정상)"이라는 무해한 문구로만 찍힌다 — 그런데 test_csrf·
#    test_bidding·test_blockers·test_photos 는 전부 `if not m`/`if not (m and p
#    and i)` 로 그 결과를 물려받아 통째로 건너뛴다(bootstrap.sh 자신의 주석은
#    "그 검사만 건너뛰고 나머지는 계속 돈다"고 믿고 있었는데 실측 결과는 아니다
#    — 전체 ~90개 검사 중 CSRF·입찰·이중지급방지·IDOR·정산money-flow·사진
#    업로드/열람권한 등 ~53개가 여기 걸린다). FAIL 이 0건이라 exit 0(전부
#    통과)이 그대로 나가고, "go-live 뒤라 이 정도 건너뜀은 정상"이라는 안내와
#    "보안 회귀 검사 대부분이 사실상 하나도 안 돌았다"는 사실이 구분되지 않는다.
#    이 3곳의 skip 이 (SECURE_COOKIE_BLOCK 과는 별개로) '데모 계정 자체가
#    사라져서'인지를 따로 기록해, 요약에서 숨기지 않는다.
DEMO_LOGIN_GONE = []

# 운영 모드는 세션 쿠키에 Secure 플래그를 붙인다. 평문 http 로 접속하면 클라이언트가
# 쿠키를 되돌려주지 않으므로 로그인 이후 검사가 전부 401 이 된다 — 결함이 아니라 정상 동작이다.
# 이 상황을 감지해 "실패"가 아니라 "https 로 다시 실행하라"고 안내한다.
SECURE_COOKIE_BLOCK = False


def c(code, s):
    return f"\033[{code}m{s}\033[0m"


class CIHeaders(dict):
    """대소문자를 가리지 않는 응답 헤더 조회.

    ⚠ HTTP 헤더 이름은 규격상 대소문자를 구분하지 않는다. 게다가 **HTTP/2 는 헤더명을
      전부 소문자로 보낸다.** 예전에는 `hdr.get("X-Frame-Options")` 처럼 대문자로 찾아서,
      nginx·클라우드플레어 같은 HTTP/2 프록시 뒤의 **실제 운영 서버를 검사하면 보안 헤더가
      전부 '없음'으로 잡혔다.** 헤더가 멀쩡히 붙어 있는데도 실패로 보고되어,
      진짜 결함과 구분할 수 없었다.
    """

    def __init__(self, headers):
        super().__init__({str(k).lower(): v for k, v in dict(headers).items()})

    def get(self, key, default=None):
        return super().get(str(key).lower(), default)

    def __contains__(self, key):
        return super().__contains__(str(key).lower())

    def __getitem__(self, key):
        return super().__getitem__(str(key).lower())


class Client:
    """쿠키를 유지하는 최소 HTTP 클라이언트 (세션 1개 = 주체 1명)."""

    def __init__(self, name):
        self.name = name
        self.jar = http.cookiejar.CookieJar()
        # 로컬 리허설(dev_tls_proxy)은 자체 서명 인증서를 쓰므로 검증을 끈다.
        # 운영 도메인(https://…) 대상 실행에서는 정상 검증한다.
        handlers = [urllib.request.HTTPCookieProcessor(self.jar), NoRedirect()]
        if "127.0.0.1" in BASE or "localhost" in BASE:
            unverified = ssl.create_default_context()
            unverified.check_hostname = False
            unverified.verify_mode = ssl.CERT_NONE
            handlers.append(urllib.request.HTTPSHandler(context=unverified))
        self.opener = urllib.request.build_opener(*handlers)
        self.csrf = None

    def req(self, method, path, body=None):
        url = BASE + path
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        r = urllib.request.Request(url, data=data, method=method)
        if data:
            r.add_header("Content-Type", "application/json")
        if self.csrf:
            r.add_header("X-CSRF-Token", self.csrf)
        try:
            resp = self.opener.open(r, timeout=20)
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, raw, CIHeaders(resp.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), CIHeaders(e.headers)

    def get(self, path):
        return self.req("GET", path)

    def post(self, path, body):
        return self.req("POST", path, body)

    def jpost(self, path, body):
        st, raw, _ = self.post(path, body)
        try:
            return st, json.loads(raw)
        except Exception:
            return st, {}

    def jget(self, path):
        st, raw, _ = self.get(path)
        try:
            return st, json.loads(raw)
        except Exception:
            return st, {}

    def jreq(self, method, path, body=None):
        st, raw, _ = self.req(method, path, body)
        try:
            return st, json.loads(raw)
        except Exception:
            return st, {}

    def multipart(self, path, files):
        """(파일명, 바이트) 목록을 photos 필드로 업로드한다."""
        sep = "----bokguon" + secrets.token_hex(8)
        crlf = "\r\n"
        parts = []
        for name, data in files:
            ct = "image/png" if name.endswith(".png") else "application/octet-stream"
            hdr = ("--" + sep + crlf
                   + 'Content-Disposition: form-data; name="photos"; filename="' + name + '"' + crlf
                   + "Content-Type: " + ct + crlf + crlf)
            parts.append(hdr.encode() + data + crlf.encode())
        payload = b"".join(parts) + ("--" + sep + "--" + crlf).encode()

        r = urllib.request.Request(BASE + path, data=payload, method="POST")
        r.add_header("Content-Type", "multipart/form-data; boundary=" + sep)
        if self.csrf:
            r.add_header("X-CSRF-Token", self.csrf)
        try:
            resp = self.opener.open(r, timeout=40)
            raw, st = resp.read().decode("utf-8", "replace"), resp.status
        except urllib.error.HTTPError as e:
            raw, st = e.read().decode("utf-8", "replace"), e.code
        try:
            return st, json.loads(raw)
        except Exception:
            return st, {}

    def load_csrf(self):
        st, d = self.jget("/api/csrf")
        self.csrf = d.get("token")
        return self.csrf

    def has_session_cookie(self):
        return any(ck.name == "session" for ck in self.jar)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """리다이렉트를 따라가지 않는다 — 302 Location 자체를 검사하기 위함."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  {c(92, '✔')} {name}" + (f"  {c(90, detail)}" if detail else ""))
    else:
        FAIL.append((name, detail))
        print(f"  {c(91, '✘')} {name}" + (f"  {c(91, detail)}" if detail else ""))
    return cond


def skip(name, why):
    SKIP.append(name)
    print(f"  {c(90, '–')} {c(90, name + '  (' + why + ')')}")


def head(t):
    print(f"\n{c(1, t)}\n" + "─" * 66)


# ══════════════════════════════════════════════════════════════
def test_public():
    head("1. 공개면")
    a = Client("anon")
    for path, must in [("/", "복구온"), ("/apply/insurer", "도입"), ("/apply/partner", "입점"),
                       ("/legal/privacy", "개인정보"), ("/legal/terms", "이용약관"),
                       ("/legal/business", "사업자")]:
        st, raw, _ = a.get(path)
        check(f"{path} 200 응답", st == 200 and must in raw, f"HTTP {st}, {len(raw):,}바이트")

    st, raw, _ = a.get("/robots.txt")
    check("robots.txt 에 관리자 경로 차단", st == 200 and "Disallow: /admin" in raw)
    st, raw, _ = a.get("/sitemap.xml")
    check("sitemap.xml 유효", st == 200 and "<urlset" in raw)
    st, raw, _ = a.get("/static/favicon.svg")
    check("파비콘 제공", st == 200)

    st, raw, hdr = a.get("/")
    check("보안 헤더 X-Frame-Options=DENY", hdr.get("X-Frame-Options") == "DENY")
    check("보안 헤더 X-Content-Type-Options=nosniff", hdr.get("X-Content-Type-Options") == "nosniff")
    check("보안 헤더 CSP 적용", "Content-Security-Policy" in hdr)
    srv = (hdr.get("Server") or "").lower()
    # 서버 종류·버전이 드러나면 알려진 취약점 탐색의 출발점이 된다 (KISA 웹서버 보안 권고)
    leaks = any(k in srv for k in ("werkzeug", "python", "gunicorn", "waitress", "nginx/"))
    #  개발 인스턴스(Werkzeug)에서 돌리면 당연히 새어 나온다 — 그건 이 검사의 대상이 아니다.
    #  운영 WSGI 로 띄웠을 때만 판정하고, 아니면 건너뛴다(거짓 빨간불을 만들지 않는다).
    if "werkzeug" in srv:
        skip("Server 헤더에 버전 미노출", "개발 서버(Werkzeug) — 운영 WSGI 에서 확인할 것")
    else:
        check("Server 헤더에 버전 미노출", not leaks, f"Server: {hdr.get('Server') or '(없음)'}")

    st, d = a.jget("/healthz")
    check("헬스체크 정상", st == 200 and d.get("ok") is True, json.dumps(d, ensure_ascii=False))


def test_auth_isolation():
    head("2. 인증 · 권한 격리 (OWASP 2025 A01)")
    a = Client("anon")
    for path in ["/api/dashboard", "/api/partner/dashboard", "/api/insurer/dashboard"]:
        st, _ = a.jget(path)
        check(f"비로그인 {path} 차단", st in (401, 403), f"HTTP {st}")

    st, raw, hdr = a.get("/admin")
    check("비로그인 /admin → 로그인 화면 유도", st in (302, 303) and "login" in (hdr.get("Location") or ""),
          f"HTTP {st} → {hdr.get('Location')}")

    # 협력사 세션으로 관리자 API 접근
    global SECURE_COOKIE_BLOCK
    p = Client("partner")
    st, d = p.jpost("/api/partner/login", {"login_id": "partner", "password": _cred("BOKGUON_TEST_PARTNER_PW")})
    if st == 200 and d.get("ok") and not p.has_session_cookie() and BASE.startswith("http://"):
        SECURE_COOKIE_BLOCK = True
        print(f"  {c(93, '▲')} 운영 모드(Secure 쿠키) + 평문 http 조합이라 로그인 세션이 유지되지 않습니다.")
        print(f"    {c(90, '→ 이는 정상 동작입니다. 인증 이후 검사는 https:// 주소로 다시 실행하세요.')}")
        skip("인증 이후 검사 전체", "Secure 쿠키 · http 접속")
        return None, None
    if st != 200 or not d.get("ok"):
        skip("협력사 교차 접근 차단", "데모 협력사 계정 없음(운영 서버에서는 정상)")
        DEMO_LOGIN_GONE.append("협력사")
        return None, None
    st, _ = p.jget("/api/dashboard")
    check("협력사 세션으로 관리자 API 접근 차단", st in (401, 403), f"HTTP {st}")
    st, _ = p.jget("/api/insurer/dashboard")
    check("협력사 세션으로 보험사 API 접근 차단", st in (401, 403), f"HTTP {st}")

    i = Client("insurer")
    st, d = i.jpost("/api/insurer/login", {"login_id": "insurer", "password": _cred("BOKGUON_TEST_INSURER_PW")})
    if st == 200 and d.get("ok"):
        st, _ = i.jget("/api/dashboard")
        check("보험사 세션으로 관리자 API 접근 차단", st in (401, 403), f"HTTP {st}")
    else:
        #  ⚠⚠ [라운드123] 협력사 분기(264-266행)는 로그인 실패 시 명시적으로 skip 하고
        #    None 을 반환하는데, 여기만 그 처리가 없어 인증 안 된 Client 를 그대로
        #    반환했다 — Client 는 __bool__/__len__ 이 없어 항상 참(truthy)이라, 아래
        #    test_bidding/test_blockers/test_photos 의 `if not (m and p and i)` 게이트가
        #    이 상황을 못 걸러 인증 없이 API 를 호출하다 401/403 으로 엉뚱한 이름의
        #    FAIL 을 여러 건 남긴다(진짜 원인=보험사 테스트 계정 자격증명 문제).
        skip("보험사 관련 검사", "데모 보험사 계정 없음(운영 서버에서는 정상)")
        DEMO_LOGIN_GONE.append("보험사")
        i = None
    return p, i


def test_admin():
    head("3. 관리자 콘솔")
    if SECURE_COOKIE_BLOCK:
        skip("관리자 콘솔 검사", "Secure 쿠키 · http 접속 — https 로 재실행 필요")
        return None
    m = Client("admin")
    st, d = m.jpost("/api/login", {"username": "admin", "password": _cred("BOKGUON_TEST_ADMIN_PW")})
    if st != 200 or not d.get("ok"):
        skip("관리자 로그인", "데모 비밀번호가 이미 교체됨(운영 서버에서는 정상)")
        DEMO_LOGIN_GONE.append("관리자")
        return None
    m.csrf = d.get("csrf")
    check("관리자 로그인", True, f"{d.get('name')} / {d.get('role')}")

    st, d = m.jget("/api/dashboard")
    ok = st == 200 and isinstance(d.get("pipeline"), list) and len(d["pipeline"]) >= 5
    check("대시보드 작업 파이프라인", ok, f"{len(d.get('pipeline', []))}단계")

    st, d = m.jget("/api/traffic")
    check("접속 통계(별도 메뉴)", st == 200, f"HTTP {st}")

    # 관리자 문의함은 공개 폼(POST /api/leads)과 **같은 경로**다.
    # 레이트리밋이 메서드를 구분하지 않으면 관리자가 새로고침 몇 번에 자기 화면에서 쫓겨난다.
    blocked = 0
    for _ in range(10):
        st, _d = m.jget("/api/leads")
        if st == 429:
            blocked += 1
    check("관리자 문의함 연속 조회 차단 없음(공개 폼과 경로 공유)", blocked == 0,
          f"10회 중 {blocked}회 차단")

    for path, label in [("/api/partners", "업체 목록"), ("/api/cases", "사건 목록"),
                        ("/api/settlements", "정산"), ("/api/defects", "하자·A/S"),
                        ("/api/leads", "도입문의함"), ("/api/applications", "입점신청함")]:
        st, d = m.jget(path)
        n = len(d) if isinstance(d, list) else len(d.get("items", []) if isinstance(d, dict) else [])
        check(f"{label} 조회", st == 200, f"HTTP {st} · {n}건")
    return m


def test_csrf(m):
    head("4. CSRF 방어")
    if not m:
        skip("CSRF 검사", "관리자 세션 없음")
        return
    saved, m.csrf = m.csrf, None                      # 토큰 없이 쓰기 시도
    st, d = m.jpost("/api/notices", {"title": "csrf-probe", "body": "x"})
    check("CSRF 토큰 없는 쓰기 차단", st == 403 and d.get("code") == "CSRF", f"HTTP {st}")
    m.csrf = "forged-token-0000"   # HTTP 헤더는 latin-1 이므로 ASCII 로 위조한다
    st, d = m.jpost("/api/notices", {"title": "csrf-probe", "body": "x"})
    check("위조 CSRF 토큰 차단", st == 403, f"HTTP {st}")
    m.csrf = saved


def test_consent():
    head("5. 개인정보 수집·이용 동의 (개인정보 보호법 §15·§22)")
    a = Client("anon")
    st, d = a.jpost("/api/leads", {"company": "스모크테스트기관", "phone": "02-0000-0000"})
    if st == 429:
        # 직전 실행의 레이트리밋 창(10분)이 아직 살아 있는 경우 — 결함이 아니다
        skip("동의 검사", f"레이트리밋 잔여 — {d.get('error','')[:26]}")
        return
    check("동의 없는 제출 거부", st == 400 and d.get("code") == "CONSENT",
          f"HTTP {st} · {d.get('error', '')[:34]}")
    if SKIP_WRITE:
        skip("동의 포함 제출", "--skip-write")
        return
    st, d = a.jpost("/api/leads", {"company": "스모크테스트기관", "phone": "02-0000-0000",
                                   "agree_privacy": True, "agree_marketing": False})
    check("동의 포함 제출 접수", st == 200 and d.get("ok"), f"lead id={d.get('id')}")


def test_bidding(m, p, i):
    head("6. 핵심 업무 흐름 — 사건 등록 → 입찰 → 낙찰")
    if SECURE_COOKIE_BLOCK:
        skip("업무 흐름 검사", "Secure 쿠키 · http 접속 — https 로 재실행 필요")
        return
    if SKIP_WRITE:
        skip("업무 흐름 검사", "--skip-write")
        return
    if not (m and p and i):
        skip("업무 흐름 검사", "3자 세션이 모두 필요")
        return
    i.load_csrf()
    st, d = i.jpost("/api/insurer/cases", {
        "category": "가드레일·방호울타리", "region": "경기 용인",
        "address": "스모크테스트 현장", "est_price": 4000000,
        "detail": "스모크테스트 자동 생성 건", "urgent": False})
    if not check("보험사 사건 등록(가견적=입찰 상한)", st == 200 and d.get("ok"), f"HTTP {st}"):
        return
    cid = d.get("id")

    p.load_csrf()
    st, d = p.jpost("/api/partner/bids", {"case_id": cid, "amount": 3600000, "days": 3})
    check("시행사 통값 입찰 제출", st == 200 and d.get("ok"),
          f"HTTP {st} · 최저 {d.get('low_price')}원 · {d.get('error', '')[:40]}")

    # 가견적(400만) 위로는 투찰할 수 없어야 한다 — 역경매의 존재 이유
    st, d = p.jpost("/api/partner/bids", {"case_id": cid, "amount": 9900000, "days": 3})
    check("가견적 상한 초과 입찰 거부", st == 400 and d.get("code") == "OVER_CAP",
          f"HTTP {st} · {d.get('error', '')[:46]}")

    # 재투찰은 인하만
    st, d = p.jpost("/api/partner/bids", {"case_id": cid, "amount": 3800000, "days": 3})
    check("재투찰 인상 거부(인하만 가능)", st == 400 and not d.get("ok"),
          f"HTTP {st} · {d.get('error', '')[:40]}")
    st, d = p.jpost("/api/partner/bids", {"case_id": cid, "amount": 3400000, "days": 3})
    check("재투찰 인하 허용", st == 200 and d.get("ok"), f"최저 {d.get('low_price')}원")

    i.load_csrf()
    st, d = i.jget(f"/api/insurer/cases/{cid}/bids")
    check("보험사 입찰 현황 조회", st == 200, f"HTTP {st} · {len(d) if isinstance(d, list) else '-'}건")


def test_blockers(m, p, i):
    """감사에서 확정된 블로커 결함의 회귀 검사.

    '고쳤다'는 주장만으로는 부족하다. 각 결함을 실제로 재현 시도해서 막히는지 확인한다.
    """
    head("8. 블로커 회귀 검사 (감사 확정 결함)")
    if SECURE_COOKIE_BLOCK or SKIP_WRITE:
        skip("블로커 회귀 검사", "인증 세션·쓰기 필요")
        return
    if not (m and p and i):
        skip("블로커 회귀 검사", "3자 세션이 모두 필요")
        return

    # ── A-3 ① 타 보험사 입찰을 자기 사건 낙찰로 확정 (bid IDOR) ──
    i.load_csrf()
    st, caseA = i.jpost("/api/insurer/cases", {
        "category": "가드레일·방호울타리", "region": "경기", "address": "스모크 A현장",
        "est_price": 5000000, "detail": "A"})
    st, caseB = i.jpost("/api/insurer/cases", {
        "category": "유리·샷시·자동문", "region": "서울", "address": "스모크 B현장",
        "est_price": 5000000, "detail": "B"})
    cidA, cidB = caseA.get("id"), caseB.get("id")
    p.load_csrf()
    stA, bA = p.jpost("/api/partner/bids", {"case_id": cidA, "amount": 4100000, "days": 3})
    stB, bB = p.jpost("/api/partner/bids", {"case_id": cidB, "amount": 4200000, "days": 3})
    if not (stA == 200 and stB == 200):
        check("블로커 회귀 검사 준비(입찰 제출)", False,
              f"A:HTTP{stA} {bA.get('error','')[:30]} / B:HTTP{stB} {bB.get('error','')[:30]}")
        return

    i.load_csrf()
    st, dB = i.jget(f"/api/insurer/cases/{cidB}/bids")
    bidsB = dB.get("bids") if isinstance(dB, dict) else None
    bidB_id = bidsB[0]["id"] if bidsB else None
    if bidB_id:
        # B사건의 입찰을 A사건 낙찰에 사용 시도 → 막혀야 한다
        st, d = i.jpost(f"/api/insurer/cases/{cidA}/award", {"bid_id": bidB_id})
        check("A-3 타 사건 입찰로 낙찰 시도 차단(bid IDOR)", st == 400 and not d.get("ok"),
              f"HTTP {st} · {d.get('error','')[:40]}")
    else:
        check("A-3 타 사건 입찰로 낙찰 시도 차단(bid IDOR)", False, "입찰 조회 실패")

    # ── A-3 ② 정상 낙찰 후 재낙찰 시도 ──
    st, dA = i.jget(f"/api/insurer/cases/{cidA}/bids")
    bidsA = dA.get("bids") if isinstance(dA, dict) else None
    bidA_id = bidsA[0]["id"] if bidsA else None
    if not (bidA_id and bidB_id):
        check("블로커 회귀 검사 준비(입찰 생성)", False, f"A={bidA_id} B={bidB_id}")
        return
    st, d = i.jpost(f"/api/insurer/cases/{cidA}/award", {"bid_id": bidA_id})
    check("낙찰 승인 정상 처리", st == 200 and d.get("ok"), f"낙찰가 {d.get('award_amount')}원")
    st, d = i.jpost(f"/api/insurer/cases/{cidA}/award", {"bid_id": bidA_id})
    check("A-3 낙찰 완료 건 재낙찰 차단", st == 409 and d.get("code") == "ALREADY_AWARDED",
          f"HTTP {st} · {d.get('error','')[:34]}")

    # ── B-5 무인증 사건 데이터 노출 ──
    anon = Client("anon2")
    st, d = anon.jget("/api/open-auctions")
    check("B-5 비로그인 공고 조회 차단", st in (401, 403), f"HTTP {st}")
    p.load_csrf()
    st, d = p.jget("/api/open-auctions")
    leaked = [k for k in ("address", "insurer", "manager", "partner_name", "insurer_id")
              if isinstance(d, list) and d and k in d[0]]
    check("B-5 공고 응답에 주소·보험사·담당자 미포함", st == 200 and not leaked,
          f"유출 컬럼: {leaked}" if leaked else "필요한 컬럼만 반환")

    # ── E-2 금액 입력 검증 ──
    st, d = p.jpost("/api/partner/bids", {"case_id": cidB, "amount": 10 ** 20, "days": 3})
    check("E-2 과대 금액 거부(500 아님)", st == 400, f"HTTP {st} · {d.get('error','')[:34]}")
    st, d = p.jpost("/api/partner/bids", {"case_id": cidB, "amount": "삼백만원", "days": 3})
    check("E-2 문자열 금액 거부", st == 400, f"HTTP {st} · {d.get('error','')[:34]}")

    # ── E-3 비정상 본문 ──
    st, raw, _ = anon.req("POST", "/api/leads", ["배열", "본문"])
    check("E-3 비-객체 JSON 본문에 500 미발생", st == 400, f"HTTP {st}")

    # ── A-4 / E-13 낙찰 → 사진 업로드·검수 → 완료보고 → 검수승인 → 정산 생성 ──
    # 사진 검수가 정산의 필수 관문이므로(MONEY-05), 사진 1장을 올려 승인까지 마친다.
    p.load_csrf()
    p.multipart(f"/api/partner/cases/{cidA}/photos", [("done.png", _png((90, 170, 110)))])
    m.csrf = m.csrf or m.load_csrf()
    st, pl = m.jget(f"/api/cases/{cidA}/photos")
    for x in pl.get("unclassified", []):
        m.jpost(f"/api/photos/{x['id']}/kind", {"kind": "완료"})
    m.jpost(f"/api/cases/{cidA}/photos/approve", {})

    p.load_csrf()
    st, d = p.jpost(f"/api/partner/cases/{cidA}/complete", {"memo": "스모크 완료 보고"})
    check("A-4 협력사 완료 보고 → 검수대기", st == 200 and d.get("status") == "검수대기",
          f"HTTP {st} · {d.get('error','')[:34]}")

    st, d = m.jpost(f"/api/cases/{cidA}/approve", {})
    amount, fee, payout = d.get("amount"), d.get("fee"), d.get("payout")
    check("A-4 검수 승인 시 정산 레코드 생성", st == 200 and d.get("settlement_id"),
          f"총액 {amount:,}원 · 수수료 {fee:,}원 · 지급 {payout:,}원" if st == 200 else f"HTTP {st}")
    if st == 200:
        check("A-4 수수료 10% 정확 (총액 = 수수료 + 지급액)",
              fee == amount // 10 and amount == fee + payout,
              f"{amount:,} = {fee:,} + {payout:,}")
        st2, d2 = m.jpost(f"/api/cases/{cidA}/approve", {})
        check("A-4 중복 정산 생성 차단", st2 == 409, f"HTTP {st2}")

    # ── B-6 계좌 변경 권한 ──
    #  ⚠ 바로 위(33행) 주석이 "비밀번호를 파일에 적어 두면 옛 값이 저장소에 남는다"고
    #    적어 놓고, 정작 여기에 비번이 박혀 있었다. 이 파일은 Z 드라이브로 나간다.
    staff = Client("staff")
    _spw = _cred("BOKGUON_TEST_STAFF_PW")
    if not _spw:
        skip("B-6 계좌 변경 권한", "BOKGUON_TEST_STAFF_PW 미설정")
        return
    st, d = staff.jpost("/api/login", {"username": "staff", "password": _spw})
    if st == 200 and d.get("ok"):
        staff.csrf = d.get("csrf")
        st, d = staff.jreq("PATCH", "/api/partners/94/account",
                           {"bank_name": "국민", "bank_holder": "테스트", "bank_account": "12345678901"})
        check("B-6 운영관리자의 계좌 변경 차단(최고관리자 전용)", st == 403, f"HTTP {st}")
    else:
        skip("B-6 계좌 변경 권한", "중간관리자(staff) 계정 없음")


def test_frontend():
    """공개면 품질 회귀 검사 — 외부 의존·접근성·JS 비의존."""
    head("10. 공개면 품질 (외부 의존 · 접근성)")
    a = Client("front")

    # C-16 / F-14 — 외부 CDN 의존이 없어야 한다 (가용성 + 이용자 IP 국외 전달 방지)
    ext = []
    for path in ["/", "/apply/insurer", "/apply/partner", "/legal/privacy", "/admin/login"]:
        st, raw, _ = a.get(path)
        for host in ("cdn.jsdelivr.net", "fonts.googleapis.com", "fonts.gstatic.com"):
            if host in raw:
                ext.append(f"{path}→{host}")
    check("외부 CDN 의존 없음 (글꼴 자체 호스팅)", not ext, "; ".join(ext[:3]) if ext else "전 화면 자기 도메인만 참조")

    st, raw, hdr = a.get("/static/fonts/PretendardVariable.woff2")
    check("자체 호스팅 글꼴 제공", st == 200 and len(raw) > 100000, f"HTTP {st} · {len(raw):,} bytes")

    # CSP 가 외부 출처를 열어두지 않아야 한다
    #  ⚠⚠ [라운드123] "https:"/"http:" 를 지운 나머지에 "http"가 있는지로 봤는데,
    #    스킴 접두어를 지우면 그 문자열은 애초에 "http" 를 남길 수가 없다 — 즉
    #    앞 조건이 사실상 언제나 참이라 뒤의 실제 검사(jsdelivr 등 CDN 잔존)가
    #    or 로 통째로 가려진다. jsdelivr·googleapis·gstatic 이 CSP 에 다시
    #    들어와도 이 항목은 절대 FAIL 이 될 수 없었다(항진명제). 실제로 의미
    #    있는 뒤쪽 조건만 남긴다.
    st, raw, hdr = a.get("/")
    csp = hdr.get("Content-Security-Policy", "")
    check("CSP 에 외부 출처 없음", not any(h in csp for h in ("jsdelivr", "googleapis", "gstatic")),
          "object-src/frame-src 차단 포함" if "object-src 'none'" in csp else "object-src 미차단")

    # F-8 — 스크립트가 없어도 본문이 보여야 한다 (.rv 기본 상태가 opacity:1)
    st, raw, _ = a.get("/")
    check("JS 없이도 본문 노출 (.rv 기본 표시)",
          ".rv{opacity:1" in raw.replace(" ", "") or ".rv{opacity:1;transform:none}" in raw,
          "html.js 가 붙을 때만 숨김 처리")

    # F-6 — 모바일에서 전환 버튼(도입 문의)이 살아 있어야 한다
    check("모바일에서 CTA 유지", ".nav-links a:not(.btn){display:none}" in raw,
          "섹션 링크만 접고 버튼은 유지")

    # F-9 — 폼 label 이 입력과 연결돼야 한다
    st, raw, _ = a.get("/apply/partner")
    n_for = raw.count('<label for="')
    n_auto = raw.count('autocomplete="')
    check("신청 폼 label-입력 연결", n_for >= 10, f"label for= {n_for}개 · autocomplete {n_auto}개")
    check("필수 항목 required 표시", 'id="company" required' in raw and 'id="phone" required' in raw)

    # F-11 — 봇 방어 허니팟
    check("공개 폼 허니팟 존재", 'id="website_url"' in raw and 'aria-hidden="true"' in raw)

    # 법정 게시물 링크가 공개면에서 도달 가능해야 한다 (법 제30조 '쉽게 확인')
    st, raw, _ = a.get("/")
    check("랜딩에서 개인정보 처리방침 도달 가능", '/legal/privacy' in raw)

    # ── CSP nonce 회귀 ────────────────────────────────────────
    #  'unsafe-inline' 이 슬그머니 되살아나면 CSP 방어층이 사실상 사라진다.
    st, raw, hdr = a.get("/admin/login")
    csp = hdr.get("Content-Security-Policy", "")
    check("script-src 에 'unsafe-inline' 없음", "script-src" in csp and "'unsafe-inline'" not in
          csp.split("script-src")[1].split(";")[0], csp.split(";")[1].strip() if ";" in csp else csp)
    check("script-src 에 nonce 적용", "'nonce-" in csp)

    # 페이지의 인라인 스크립트에 실제로 그 nonce 가 붙어 있어야 한다
    import re as _re
    mo = _re.search(r"'nonce-([^']+)'", csp)
    if mo:
        check("인라인 script 에 동일 nonce 부여", f'nonce="{mo.group(1)}"' in raw)

    # 매 요청 다른 값이어야 한다 (고정 nonce 는 없는 것과 같다)
    _st, _r2, h2 = a.get("/admin/login")
    m2 = _re.search(r"'nonce-([^']+)'", h2.get("Content-Security-Policy", ""))
    check("nonce 가 요청마다 갱신됨", bool(mo and m2 and mo.group(1) != m2.group(1)))

    # 인라인 이벤트 핸들러는 nonce 로 구제되지 않는다 — 남아 있으면 그 버튼이 죽는다
    leftovers = []
    for path in ["/", "/admin/login", "/partner/login", "/insurer/login",
                 "/apply/insurer", "/apply/partner", "/legal/privacy"]:
        _st, body_, _h = a.get(path)
        for attr in ("onclick=", "onsubmit=", "oninput=", "onchange="):
            if attr in body_:
                leftovers.append(f"{path}:{attr}")
    check("인라인 이벤트 핸들러 잔존 없음", not leftovers, "; ".join(leftovers[:3]))

    # 위임 디스패처가 실제로 배포돼 있어야 한다
    st, raw, _ = a.get("/static/actions.js")
    check("이벤트 위임 디스패처 제공", st == 200 and "data-act" in raw)

    # ── 법정 게시물 XSS 회귀 ──────────────────────────────────
    #  처리방침 본문은 |safe 로 렌더된다. company_info.json 에서 읽어온 값이
    #  이스케이프 없이 들어가면 그 페이지에 스크립트를 심을 수 있다.
    for path in ["/legal/privacy", "/legal/business", "/legal/terms"]:
        st, raw, _ = a.get(path)
        # <article class="sheet"> … </article> 안쪽만 본다.
        # (페이지 하단의 정상 <script> 는 본문 밖이라 검사 대상이 아니다)
        seg = ""
        if "<article" in raw and "</article>" in raw:
            seg = raw.split("<article", 1)[1].split("</article>", 1)[0].lower()
        bad_tags = [t for t in ("<script", "<iframe", "<object", "<embed", "onerror=", "onload=")
                    if t in seg]
        check(f"{path} 본문에 주입된 태그 없음", bool(seg) and not bad_tags,
              ", ".join(bad_tags) if bad_tags else f"본문 {len(seg):,}자 검사")


def _png(rgb=(200, 120, 60), w=40, h=30):
    """검사용 최소 PNG — 외부 의존 없이 실제 시그니처를 갖춘 이미지를 만든다."""
    raw = b"".join(bytes([0]) + bytes(rgb) * w for _ in range(h))

    def chunk(t, data):
        c = t + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    magic = bytes([0x89]) + b"PNG" + bytes([0x0D, 0x0A, 0x1A, 0x0A])
    return (magic
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def test_photos(m, p, i):
    """시공 사진 — 업로드 검증 · 접근통제 · 영수증 분리 · 검수 관문."""
    head("11. 시공 사진 파이프라인")
    if SECURE_COOKIE_BLOCK or SKIP_WRITE or not (m and p and i):
        skip("사진 파이프라인 검사", "3자 세션·쓰기 필요")
        return

    # 시공중 사건 하나를 만든다
    i.load_csrf()
    st, case = i.jpost("/api/insurer/cases", {"category": "유리·샷시·자동문", "region": "서울",
                                              "address": "스모크 사진현장", "est_price": 3000000})
    cid = case.get("id")
    p.load_csrf()
    p.jpost("/api/partner/bids", {"case_id": cid, "amount": 2500000, "days": 2})
    st, d = i.jget("/api/insurer/cases/%s/bids" % cid)
    bids = d.get("bids") or []
    if not (cid and bids):
        check("사진 검사 준비", False, f"case={cid} bids={len(bids)}")
        return
    i.jpost("/api/insurer/cases/%s/award" % cid, {"bid_id": bids[0]["id"]})

    # 확장자만 이미지인 파일은 막혀야 한다 — 확장자가 아니라 내용으로 판정하는지 확인
    p.load_csrf()
    st, d = p.multipart("/api/partner/cases/%s/photos" % cid,
                        [("evil.png", b"<?php system($_GET['c']); ?>" + b"A" * 100)])
    check("확장자 위장 파일 거부(매직바이트 검사)",
          st == 200 and d.get("count") == 0 and d.get("errors"),
          (d.get("errors") or [""])[0][:44])

    st, d = p.multipart("/api/partner/cases/%s/photos" % cid,
                        [("a.png", _png((200, 60, 50))), ("b.png", _png((230, 180, 70))),
                         ("c.png", _png((90, 170, 110))), ("r.png", _png((240, 240, 240)))])
    check("사진 4장 업로드", st == 200 and d.get("count") == 4, d.get("message", ""))

    st, d2 = p.multipart("/api/partner/cases/%s/photos" % cid, [("a.png", _png((200, 60, 50)))])
    check("동일 파일 중복 차단", st == 200 and d2.get("duplicates") == 1,
          f"중복 {d2.get('duplicates')}장")

    # PH-10: 사건 누적 상한을 넣었다고 정상 범위 업로드가 막히면 안 된다(회귀 방지).
    #   상한이 실제로 409 를 내는지는 상한을 낮춘 서버로 따로 검증했다(200장을 여기서 올릴 순 없다).
    #   올린 5장은 곧바로 지운다 — 미분류로 남으면 뒤의 검수 승인·정산을 막는다.
    st, dq = p.multipart("/api/partner/cases/%s/photos" % cid,
                         [("q%d.png" % k, _png((k * 7 % 250, 90, 200))) for k in range(5)])
    check("누적 상한이 정상 업로드를 막지 않음(PH-10)",
          st == 200 and dq.get("count") == 5, f"HTTP {st} count={dq.get('count')}")
    st, allp = m.jget("/api/cases/%s/photos" % cid)
    for grp in ("unclassified", "construction", "receipts"):
        for ph in (allp.get(grp) or []):
            if str(ph.get("orig_name", "")).startswith("q"):
                m.jreq("DELETE", "/api/photos/%s" % ph["id"])


    st, pl = p.jget("/api/cases/%s/photos" % cid)
    ids = [x["id"] for x in pl.get("unclassified", [])]
    check("응답에 저장경로·해시 미노출",
          all("rel_path" not in x and "sha256" not in x for x in pl.get("unclassified", [])))

    # 사건 사진은 사고 현장이 담긴 자료다 — 주소만 알면 받아갈 수 있으면 안 된다
    if ids:
        anon = Client("anon_photo")
        st, _raw, _h = anon.req("GET", "/api/photos/%s/file" % ids[0])
        check("비로그인 사진 접근 차단", st in (401, 403), f"HTTP {st}")
        other = Client("insurer2")
        st2, d3 = other.jpost("/api/insurer/login",
                              {"login_id": "insurer2", "password": _cred("BOKGUON_TEST_INSURER_PW")})
        if st2 == 200 and d3.get("ok"):
            st, _raw, _h = other.req("GET", "/api/photos/%s/file" % ids[0])
            check("타 보험사 사진 접근 차단", st == 403, f"HTTP {st}")
        else:
            #  ⚠⚠ [라운드303] 형제 셋(협력사 264행·보험사 297행·관리자 317행)은
            #    데모 로그인 실패를 skip()+DEMO_LOGIN_GONE 으로 남기는데 이
            #    넷째(insurer2)만 그 처리가 없어, 이 IDOR 회귀 검사가 PASS·FAIL·
            #    SKIP 어디에도 안 남고 조용히 사라졌다(db.py seed() 에 애초
            #    insurer2 계정이 없어 go-live 이전에도 매번 이랬다 — 그래서
            #    db.py 쪽도 함께 고친다).
            skip("타 보험사 사진 접근 차단", "데모 보험사2 계정 없음(운영 서버에서는 정상)")
            DEMO_LOGIN_GONE.append("보험사2")
        st, raw, hdr = p.req("GET", "/api/photos/%s/file" % ids[0])
        check("소유 협력사 사진 열람 허용",
              st == 200 and hdr.get("X-Content-Type-Options") == "nosniff", f"HTTP {st}")

    # 분류가 끝나지 않았는데 승인되면 검수가 형식적으로 흐른다
    m.csrf = m.csrf or m.load_csrf()
    st, d = m.jpost("/api/cases/%s/photos/approve" % cid, {})
    check("미분류 상태에서 검수 승인 차단", st == 400 and d.get("code") == "UNCLASSIFIED",
          f"미분류 {d.get('unclassified')}장")

    for pid, kind in zip(ids, ["착공전", "시공중", "완료", "영수증"]):
        m.jpost("/api/photos/%s/kind" % pid, {"kind": kind})
    st, d = m.jpost("/api/photos/%s/kind" % ids[0], {"kind": "없는분류"})
    check("허용되지 않은 분류값 거부", st == 400)

    st, pl = m.jget("/api/cases/%s/photos" % cid)
    check("영수증이 시공사진과 분리 반환",
          len(pl.get("receipts", [])) == 1 and len(pl.get("construction", [])) == 3,
          f"시공 {len(pl.get('construction', []))}장 / 영수증 {len(pl.get('receipts', []))}장")
    check("시공사진 착공전→시공중→완료 정렬",
          [x["kind"] for x in pl.get("construction", [])] == ["착공전", "시공중", "완료"])

    st, d = m.jpost("/api/cases/%s/photos/approve" % cid, {})
    check("분류 완료 후 검수 승인", st == 200 and d.get("approved") == 4, f"{d.get('approved')}장")

    st, d = m.jpost("/api/photos/%s/reject" % ids[1], {"reason": ""})
    check("반려 사유 없이 반려 불가", st == 400)
    st, d = m.jpost("/api/photos/%s/reject" % ids[1], {"reason": "현장 식별 곤란 — 재촬영"})
    check("사진 반려 처리", st == 200 and d.get("ok"))

    # ── MONEY-05: 사진 검수가 정산의 필수 관문인지 ────────────────
    #  방금 1장을 반려했으니 검수가 끝나지 않은 상태다. 이 상태에서 정산이 생성되면 안 된다.
    p.load_csrf()
    p.jpost("/api/partner/cases/%s/complete" % cid, {"memo": "정산 검사"})
    st, d = m.jpost("/api/cases/%s/approve" % cid, {})
    #  PHOTO_REJECTED 도 정당한 차단이다 — 반려된 사진이 남아 있으면 검수가 끝난 게 아니다.
    #  (이 코드는 나중에 추가됐는데 허용 목록이 따라오지 않아, 옳은 동작이 실패로 찍혔다)
    check("사진 검수 미완 시 정산 생성 차단(MONEY-05)",
          st == 409 and d.get("code") in ("PHOTO_PENDING", "NO_PHOTO", "PHOTO_REJECTED"),
          f"HTTP {st} · {d.get('code','')} {d.get('error','')[:34]}")

    # R5-06: 오반려를 되돌릴 수 있어야 한다 — 반려 취소 후 재승인으로 검수 마무리
    st, d = m.jpost("/api/photos/%s/unreject" % ids[1], {})
    check("반려 취소 가능(R5-06)", st == 200 and d.get("ok"), f"HTTP {st}")

    # PH-03: 검수를 통과 못 하는 사진은 삭제로 교착을 풀 수 있어야 한다
    if len(ids) >= 3:
        st, d = m.jreq("DELETE", "/api/photos/%s" % ids[2])
        check("사진 삭제로 검수 교착 해소(PH-03)", st == 200 and d.get("ok"), f"HTTP {st}")
    m.jpost("/api/cases/%s/photos/approve" % cid, {})

    # ── 정산 3단계: 입금 확인 → 지급 검수 승인 → 이체 완료 ────────
    st, d = m.jpost("/api/cases/%s/approve" % cid, {})
    sid = d.get("settlement_id")
    if not sid:
        check("정산 생성", False, f"HTTP {st} {d.get('error','')[:40]}")
        return

    st, d = m.jpost("/api/settlements/%s/review" % sid, {})
    check("입금 확인 전 지급 검수 차단", st == 409 and d.get("code") == "NOT_PAID",
          f"HTTP {st} · {d.get('error','')[:34]}")

    # ── 지급 계좌 등록 — 계좌 없이는 지급할 수 없다(NO_BANK_ACCOUNT).
    #    이건 관문이 맞다. 검사는 관문을 우회하지 말고 **정상 절차를 밟아야** 한다.
    st, sett = m.jget("/api/settlements")
    row = next((x for x in (sett if isinstance(sett, list) else [])
                if x.get("id") == sid), None)
    acct_pid = row.get("partner_id") if row else None
    if acct_pid:
        st, d = m.jreq("PATCH", "/api/partners/%s/account" % acct_pid,
                       {"bank_name": "국민은행", "bank_holder": "검증계정",
                        "bank_account": "12345678901234"})
        check("지급 계좌 등록", st == 200 and d.get("ok"),
              f"HTTP {st} · {d.get('error','')[:50]}")
    else:
        skip("지급 계좌 등록", "정산 행에서 업체를 못 찾음")

    st, d = m.jpost("/api/settlements/%s/transfer" % sid, {})
    check("검수 승인 전 이체 차단", st == 409, f"HTTP {st}")

    # ⑥ 보험사 '공사 완료 승인'이 입금확인의 선행 관문
    st, d = m.jpost("/api/settlements/%s/paid" % sid, {})
    check("보험사 완료 승인 전 입금확인 차단",
          st == 409 and d.get("code") == "INSURER_NOT_APPROVED",
          f"HTTP {st} · {d.get('error','')[:34]}")
    i.load_csrf()
    st, d = i.jpost("/api/insurer/settlements/%s/approve" % sid, {})
    check("보험사 공사 완료 승인", st == 200 and d.get("ok"), f"HTTP {st}")

    st, d = m.jpost("/api/settlements/%s/paid" % sid, {})
    check("보험사 입금 확인", st == 200 and d.get("ok"))
    st, d = m.jpost("/api/settlements/%s/paid" % sid, {})
    check("입금 확인 중복 차단", st == 409)

    # 더블 크로스체크 없이 지급 검수 승인 차단
    st, d = m.jpost("/api/settlements/%s/review" % sid, {})
    check("더블체크 없이 지급 검수 차단",
          st == 400 and d.get("code") == "NEED_DOUBLE_CHECK",
          f"HTTP {st} · {d.get('error','')[:34]}")
    st, d = m.jpost("/api/settlements/%s/review" % sid, {"double_checked": True})
    check("지급 검수 승인(더블 크로스체크)", st == 200 and d.get("ok"),
          f"HTTP {st} · {d.get('code','')} {d.get('error','')[:60]}")
    st, d = m.jpost("/api/settlements/%s/transfer" % sid, {})
    check("이체 완료 처리", st == 200 and d.get("ok"),
          f"HTTP {st} · {d.get('code','')} {d.get('error','')[:60]}")
    st, d = m.jpost("/api/settlements/%s/transfer" % sid, {})
    check("이체 완료 중복 차단", st == 409)

    st, cases = m.jget("/api/cases")
    done = [c for c in (cases if isinstance(cases, list) else []) if c.get("id") == cid]
    check("이체 완료 시 사건이 '완료'로 닫힘",
          bool(done) and done[0].get("status") == "완료",
          done[0].get("status") if done else "사건 조회 실패")



def test_admin_ip_gate():
    """관리자 IP 화이트리스트를 켰을 때 **협력사·보험사가 막히지 않는지**.

    배포 절차서는 사무실 IP 등록을 필수 단계로 안내한다.
    그런데 판정이 경로 접두사면 `/api/cases/<id>/photos` 같은 협력사용 경로가
    '/api/cases' 에 걸려, 사무실 밖 모든 협력사의 사진이 403 이 된다.
    업로드는 다른 경로라 성공하므로 "올렸는데 안 보인다"로만 나타난다.
    이 검사는 HTTP 로는 재현할 수 없어(서버 설정 변경 필요) 앱을 직접 불러 판정한다.
    """
    head("12. 관리자 IP 화이트리스트 경로 판정")
    try:
        import importlib
        import os as _os
        import tempfile as _tempfile
        #  ⚠⚠ [라운드303] 이 검사만 유일하게 앱을 프로세스 안으로 직접 불러온다
        #    (위 docstring 의 "HTTP 로는 재현할 수 없어" 사정 때문). import app 는
        #    app.py 122행에서 모듈 임포트 시점에 DB.init_db() 를 무조건 실행하는데,
        #    BOKGUON_DB_PATH 가 안 정해져 있으면 db.py 의 기본값은 **운영
        #    bokguon.db** 다(db.py:17). db.py 자신의 운영DB 가드(32-44행)는 진입
        #    스크립트 이름이 "test_" 로 시작할 때만 발동하는데 smoke_test.py 는
        #    해당하지 않아 그 가드를 그냥 통과하고, 배포 스크립트(bootstrap.sh·
        #    windows_setup.ps1)도 smoke_test.py 를 실행할 때 이 환경변수를 설정
        #    하지 않는다. 이 검사가 실제로 보는 건 Flask 의 URL 맵·뷰 함수
        #    속성뿐이라(_is_admin_path 는 DB 를 전혀 안 읽는다) 운영 DB 를 켤
        #    이유가 없다 — 호출자가 이미 BOKGUON_DB_PATH 를 정해 뒀으면(스스로
        #    격리한 경우) 그대로 존중하고, 비어 있을 때만 이 판정 전용 임시 DB
        #    로 격리한다.
        if not _os.environ.get("BOKGUON_DB_PATH"):
            _os.environ["BOKGUON_DB_PATH"] = _os.path.join(
                _tempfile.mkdtemp(prefix="bokguon_smoketest_ipgate_"), "verify.db")
        _os.environ.setdefault("BOKGUON_ENV", "dev")
        A = importlib.import_module("app")
    except Exception as e:
        skip("IP 화이트리스트 판정", f"앱 로드 불가: {type(e).__name__}")
        return

    # (메서드, 경로, 관리자 전용이어야 하는가)
    table = [
        ("GET", "/api/cases/1/photos", False), ("GET", "/api/photos/1/file", False),
        ("POST", "/api/partner/cases/1/photos", False), ("GET", "/api/partner/dashboard", False),
        ("GET", "/api/insurer/dashboard", False), ("GET", "/", False),
        ("GET", "/legal/privacy", False),
        ("GET", "/admin", True), ("POST", "/api/login", True),
        ("GET", "/api/dashboard", True), ("GET", "/api/photos", True),
        ("POST", "/api/photos/1/kind", True), ("POST", "/api/cases/1/photos/approve", True),
        ("GET", "/api/partners", True), ("GET", "/api/settlements", True),
    ]
    wrong = []
    for method, path, expect in table:
        with A.app.test_request_context(path, method=method):
            got = A._is_admin_path(path)
        if got != expect:
            wrong.append(f"{method} {path} → {'관리자' if got else '일반'}(기대 {'관리자' if expect else '일반'})")
    check("협력사·보험사 경로가 관리자 IP 제한에 걸리지 않음", not wrong, "; ".join(wrong[:3]))

    # 관리자 전용 API 는 반드시 걸려야 한다 (반대 방향 누락도 위험하다)
    check("관리자 전용 API 는 IP 제한 대상", not [w for w in wrong if "기대 관리자" in w],
          f"{len(table)}개 경로 검사")


def test_bruteforce():
    """무차별 대입 방어 — **반드시 마지막에** 실행한다.

    이 검사는 로그인 레이트리밋(5분 10회)과 계정 잠금 카운터를 일부러 소진시킨다.
    앞쪽에 두면 뒤따르는 정상 로그인이 429 로 막혀 다른 검사가 전부 무의미해진다.
    실계정을 잠그지 않도록 존재하지 않는 아이디만 사용한다.
    """
    head("9. 무차별 대입 방어 (마지막 실행)")
    a = Client("bruteforce")
    st, d = a.jpost("/api/login", {"username": "smoke-nonexistent-user", "password": "wrong-pw"})
    if st == 429:
        skip("무차별 대입 검사", "직전 실행의 레이트리밋 창이 아직 살아 있음")
        return
    check("잘못된 자격증명 거부", st == 401, f"HTTP {st}")
    check("존재하지 않는 계정과 비밀번호 오류를 구분하지 않음",
          "아이디 또는 비밀번호" in (d.get("error") or ""),
          "계정 존재 여부가 응답으로 새지 않아야 함")

    for n in range(2, 12):
        st, d = a.jpost("/api/login", {"username": "smoke-nonexistent-user", "password": f"wrong{n}"})
        if st == 429:
            check("연속 실패 시 차단", True, f"{n}회째 차단 (계정 잠금 5회/10분 · 레이트리밋 5분 10회)")
            return
    check("연속 실패 시 차단", False, "11회 연속 실패해도 차단되지 않음")


def test_rate_limit():
    head("7. 공개 폼 레이트 리밋 (무차별 대입 방어)")
    a = Client("flood")
    hit = False
    for n in range(1, 15):
        st, d = a.jpost("/api/leads", {"company": f"flood{n}", "phone": "0", "agree_privacy": True})
        if st == 429:
            hit = True
            check("공개 폼 요청 폭주 차단", True, f"{n}회째 429 (설정: 10분 5회)")
            break
    if not hit:
        check("공개 폼 요청 폭주 차단", False, "14회 연속 요청이 모두 통과함")


def main():
    #  ⚠ **"검사해서 통과"와 "검사 안 함"은 다른 결과다.**
    #    자격증명이 없으면 검사 함수를 한 번도 안 부르고 0 을 돌려줬다 —
    #    bootstrap.sh 의 `|| warn` 은 발동조차 안 하므로 배포 절차 12단계가
    #    **조용히 통과로 남는다**. 0 은 '전부 통과'일 때만 쓴다.
    if not _creds_or_skip("BOKGUON_TEST_ADMIN_PW", "BOKGUON_TEST_INSURER_PW",
                          "BOKGUON_TEST_PARTNER_PW"):
        print(c(91, "  ✖ 검사를 하나도 실행하지 않았습니다 — 통과로 세지 마십시오."))
        return 2
    global BASE, SKIP_WRITE
    for arg in sys.argv[1:]:
        if arg == "--skip-write":
            SKIP_WRITE = True
        elif arg.startswith("http"):
            BASE = arg.rstrip("/")

    print(c(1, f"\n복구온 스모크 테스트 — {BASE}") + (c(93, "  [읽기 전용]") if SKIP_WRITE else ""))

    test_public()
    p, i = test_auth_isolation()
    m = test_admin()
    test_csrf(m)
    test_consent()
    test_bidding(m, p, i)
    test_blockers(m, p, i)
    test_rate_limit()
    test_frontend()
    test_photos(m, p, i)
    test_admin_ip_gate()
    test_bruteforce()

    print("\n" + "═" * 66)
    if SECURE_COOKIE_BLOCK:
        print(c(93, "  ▲ 운영 모드 + 평문 http 로 실행되어 인증 이후 검사를 건너뛰었습니다."))
        print(c(90, "    TLS 를 붙인 뒤  python smoke_test.py https://도메인  으로 다시 실행하세요."))
    #  검사를 건너뛴 채 끝났으면 그것도 초록이 아니다.
    total = len(PASS) + len(FAIL)
    print(f"  통과 {c(92, str(len(PASS)))} / {total}"
          + (f"   실패 {c(91, str(len(FAIL)))}" if FAIL else "")
          + (f"   건너뜀 {c(90, str(len(SKIP)))}" if SKIP else ""))
    if FAIL:
        print("\n  실패 항목:")
        for name, detail in FAIL:
            print(f"    · {name}  {detail}")
    #  ⚠⚠ [라운드285] "통과 N / N, 실패 0" 만 보면 완전한 초록으로 보인다 — 그런데
    #    go-live 이후엔 관리자·협력사·보험사 로그인 3곳이 전부 이 방식으로
    #    실패하고, 그 결과 CSRF·입찰·이중지급방지·IDOR·정산·사진권한 등 이
    #    파일의 핵심 회귀 검사 ~53개가 통째로 안 돈 채 위 숫자에서 조용히
    #    빠진다. FAIL 이 0 이라는 이유만으로 "안전하다"고 읽지 않도록,
    #    무엇이 실제로 검증됐는지를 마지막에 한 번 더 못박는다.
    if DEMO_LOGIN_GONE:
        who = "·".join(DEMO_LOGIN_GONE)
        print(c(93, f"  ▲▲ {who} 데모 계정이 없어(go-live 이후 정상) 로그인 이후"
                    f" 검사 대부분(CSRF·입찰·이중지급방지·IDOR·정산·사진권한 등)이"
                    f" 통째로 건너뛰어졌습니다."))
        print(c(90, "    이 실행은 사실상 공개 화면·레이트리밋만 검증했습니다 — "
                    "회귀 검사까지 확인하려면 별도 운영용 검증 계정으로 다시 실행하세요."))
    print("═" * 66)
    if FAIL:
        return 1
    #  실패는 없지만 **아무것도 검사하지 않았다면** 통과가 아니다.
    if total == 0:
        print(c(91, "  ✖ 통과 항목이 0 입니다 — 검사가 실제로 돌지 않았습니다."))
        return 2
    #  운영 모드 + 평문이라 인증 이후를 통째로 건너뛴 경우도 '통과'로 세지 않는다.
    if SECURE_COOKIE_BLOCK:
        return 3
    #  데모 계정이 사라져 핵심 회귀 검사 대부분이 안 돈 경우도 '통과'와는 구분한다
    #  (exit 0 은 이제부터 "그 검사들까지 실제로 다 돌았다"는 뜻으로만 쓴다).
    if DEMO_LOGIN_GONE:
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
