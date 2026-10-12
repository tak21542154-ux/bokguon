# -*- coding: utf-8 -*-
"""스캔 420라운드 회귀 — collect_emails.py 의 EMAIL_RE·태그제거 정규식 둘 다
   앵커가 없어(닫는 조건이 끝까지 안 나오면 시작위치마다 문자열 끝까지 훑는다)
   페이지 길이의 제곱에 비례해 느려지던 결함(정밀조사 Agent 발견 — 각도2:
   정규식 ReDoS. 실측: 200,000자에서 EMAIL_RE 32.9초, 250,000자에서 51.4초).

   기존 MAX_BYTES(500,000)는 **네트워크 읽기**만 제한할 뿐 정규식 처리
   시간은 안 막아서, 병리적인 한 페이지(닫는 '>'·완성되는 이메일이 없는
   페이지)가 이 배치도구의 스레드를 몇 분씩 붙잡을 수 있었다. app.py 는
   이 모듈을 import 하지 않는 독립 CLI(python collect_emails.py --limit N)
   라 실서비스 웹서버에는 영향이 없고, 담당자가 돌리는 배치 실행 한 건이
   느려질 뿐이다.

   고침: fetch() 가 반환하기 직전 새 상수 MAX_SCAN_CHARS(30,000)로 한 번
   더 자른다 — refuses_collection()·pick_emails() 호출부(본문·하위경로
   양쪽)를 안 건드리고 생산지 한 곳만 고친다. 30,000자에서 두 정규식 다
   실측 1초 미만(직접 측정, 짐작 아님)임을 확인했다.

       python test_scan_round420_fixes.py
"""
import io
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FILE_PATH = os.path.join(HERE, "collect_emails.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


SRC = read("collect_emails.py")

print("=" * 72)
print("  스캔 420라운드 회귀 — collect_emails.py 정규식 ReDoS(무제한 길이)")
print("=" * 72)

print("\n[1] 소스 확인")
chk("MAX_SCAN_CHARS = 30_000" in SRC,
    "★★★★★ MAX_SCAN_CHARS(30,000) 상수가 새로 생겼다")
_i0 = SRC.index("def fetch(url):")
_i1 = SRC.index("\ndef ", _i0 + 1)
_fetch_body = SRC[_i0:_i1]
chk("return text[:MAX_SCAN_CHARS]" in _fetch_body,
    "★★★★★ fetch() 가 반환 직전에 MAX_SCAN_CHARS 로 자른다")

print("\n[2] 실행 준비")
#  ⚠ collect_emails.py 도 db 모듈을 끌어와, 이 세션 표준 방어(테스트가 운영
#    DB 경로를 가리키면 중단, 418라운드에서 처음 만남)에 걸린다 — 다른
#    테스트와 같은 방식으로 스크래치 경로를 먼저 지정한다.
import tempfile
_tmpdir = tempfile.mkdtemp(prefix="round420_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
os.environ.setdefault("BOKGUON_LOG_FILE", os.path.join(_tmpdir, "test_r420.log"))
sys.path.insert(0, HERE)
import urllib.request
import collect_emails as CE


class _FakeResponse:
    def __init__(self, data):
        self._data = data
        self.headers = {"Content-Type": "text/html; charset=utf-8"}

    def read(self, n=-1):
        return self._data[:n] if n and n > 0 else self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


#  실제 악성 페이지를 흉내: 닫는 '>' 가 하나도 없는 태그더미 + 완성 안 되는
#  이메일 후보(@ 만 반복) — MAX_SCAN_CHARS(30,000)의 2배(60,000자)로 만들어,
#  "정말 30,000에서 잘렸는가"를 명확히 구분할 수 있게 한다.
ADVERSARIAL = (b"<" * 30_000) + (b"a@" * 15_000)   # 총 60,000바이트

print("\n[3] 실행 — fetch() 가 60,000바이트 악성 페이지를 30,000자로 자르는가")
#  ⚠⚠ [라운드664] fetch() 는 이제 urllib.request.urlopen() 이 아니라 그 위에 세운
#    _NO_REDIRECT_OPENER.open() 을 부른다(SSRF 리다이렉트 방어 — round664 참고).
#    이 절들은 실제 네트워크를 안 타게 응답을 가짜로 바꿔치기하는 것이 목적이라,
#    fetch() 가 실제로 여는 지점(그 오프너의 .open)을 바꿔치기해야 한다 — 옛
#    자리(urllib.request.urlopen)는 더 이상 안 불려서 더미 도메인에 실제 DNS
#    조회가 나가 버린다(실측: round664 고침 직후 result 가 None 이 됐다).
_orig_open = CE._NO_REDIRECT_OPENER.open


def _fake_urlopen(req, timeout=None):
    return _FakeResponse(ADVERSARIAL)


CE._NO_REDIRECT_OPENER.open = _fake_urlopen
try:
    t0 = time.perf_counter()
    result = CE.fetch("http://r420-fake.invalid/")
    elapsed = time.perf_counter() - t0
finally:
    CE._NO_REDIRECT_OPENER.open = _orig_open

chk(result is not None, "  fetch() 가 정상적으로 문자열을 돌려준다(회귀없음)")
chk(len(result) == 30_000,
    f"★★★★★ 60,000자 악성 페이지가 정확히 30,000자로 잘렸다"
    f"(고치기 전엔 60,000자 그대로 두 정규식에 넘어갔다)", len(result))
chk(elapsed < 2.0,
    f"★★★★ fetch() 자체(자르기 포함)가 2초 안에 끝난다", f"{elapsed:.3f}s")

print("\n[4] 실행 — 잘린 결과를 실제 정규식에 통과시켜도 빠르다")
t0 = time.perf_counter()
refused = CE.refuses_collection(result)
t1 = time.perf_counter()
emails = CE.pick_emails(result, "example.com")
t2 = time.perf_counter()
chk((t1 - t0) < 1.0 and (t2 - t1) < 1.0,
    f"★★★★★ 잘린(30,000자) 결과에 대한 정규식 처리 둘 다 1초 미만"
    f"(태그제거 {t1-t0:.3f}s, 이메일탐색 {t2-t1:.3f}s)")
chk(refused is False and emails == [],
    "  악성 페이지는 수집거부 문구도 이메일도 없다고 정상 판정한다(회귀없음)",
    (refused, emails))

print("\n[5] 대조군 — 정상 크기 페이지는 안 잘리고 그대로 처리된다")
#  ⚠ example.com 은 BAD_DOMAIN(collect_emails.py:88)에 이미 등록된
#    플레이스홀더 도메인이라 pick_emails() 가 일부러 걸러낸다 — 실존
#    도메인 형태를 써야 "정상적으로 찾는지"를 제대로 테스트한다.
NORMAL_HTML = "<html><body>연락처: contact@r420realcompany.co.kr</body></html>".encode("utf-8")
CE._NO_REDIRECT_OPENER.open = lambda req, timeout=None: _FakeResponse(NORMAL_HTML)
try:
    r2 = CE.fetch("http://r420-normal.invalid/")
finally:
    CE._NO_REDIRECT_OPENER.open = _orig_open
chk(r2 == NORMAL_HTML.decode("utf-8"),
    "  30,000자보다 훨씬 작은 정상 페이지는 그대로(안 잘리고) 반환된다"
    "(회귀없음)", r2)
chk("contact@r420realcompany.co.kr" in CE.pick_emails(r2, "r420realcompany.co.kr"),
    "  정상 페이지에서 이메일도 여전히 정상적으로 찾는다(회귀없음)")

# ============================================================
print("\n[6] 되돌리기 — 옛 코드로 되돌리면 안 잘리고 그대로 통과하는가")
# ------------------------------------------------------------
#  ⚠⚠ [라운드617] on-disk 되돌리기(파일에 직접 쓰고 subprocess 로 재현)를
#    인메모리 exec 로 이관 — fetch() 는 이 테스트가 CE.fetch() 로 직접
#    부르는 평범한 모듈함수다(302·323행의 내부 호출자 collect_one()/그
#    하위는 이 테스트 경로에서 안 불린다) — 독립 사본 이름공간에 exec 해도
#    안전(기법2). urllib.request.urlopen 몽키패치는 실제 urllib.request
#    모듈 객체 자체를 바꾸므로 사본에서도 그대로 보인다 — 실제 파일은
#    이제 전혀 안 건드린다. _fetch_body 는 위 [1]에서 이미 추출해 둔,
#    fetch() 의 현재(고친) 전체 함수 텍스트다.

NEW_FETCH_TAIL = '''            raw = r.read(MAX_BYTES)
        text = None
        for enc in ("utf-8", "euc-kr", "cp949"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = raw.decode("utf-8", "replace")
        #  ⚠⚠ [라운드420] 여기서 자르면 refuses_collection()·pick_emails()
        #    양쪽(본문·하위경로 둘 다) 호출부를 안 건드리고 한 곳에서 막는다
        #    — MAX_SCAN_CHARS 정의부 주석 참조.
        return text[:MAX_SCAN_CHARS]'''
OLD_FETCH_TAIL = '''            raw = r.read(MAX_BYTES)
        for enc in ("utf-8", "euc-kr", "cp949"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", "replace")'''


try:
    chk(SRC.count(NEW_FETCH_TAIL) == 1, "  (준비) 되돌리기 대상 텍스트가 유일하게 식별된다")
    reverted = SRC.replace(NEW_FETCH_TAIL, OLD_FETCH_TAIL)
    chk(reverted != SRC, "  (준비) 되돌리기 텍스트가 실제로 달라졌다")
    chk(_fetch_body.count(NEW_FETCH_TAIL) == 1, "  (준비) fetch() 본문 안에서도 유일하게 식별된다")
    reverted_fetch_src = _fetch_body.replace(NEW_FETCH_TAIL, OLD_FETCH_TAIL)

    _ns420 = dict(vars(CE))
    exec(compile(reverted_fetch_src, "<round420_revert_fetch>", "exec"), _ns420)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    _old_fetch = _ns420["fetch"]

    ADVERSARIAL2 = (b"<" * 30_000) + (b"a@" * 15_000)
    #  ⚠ _old_fetch 는 _ns420(dict(vars(CE)) 스냅샷) 이름공간에서 exec 됐지만,
    #    "_NO_REDIRECT_OPENER" 는 그 스냅샷에도 **같은 오프너 객체**(참조 복사)로
    #    들어 있다 — 그 객체의 .open 속성을 바꿔치기하면 CE.fetch() 든 이
    #    _old_fetch 든 똑같이 가짜 응답을 받는다.
    CE._NO_REDIRECT_OPENER.open = lambda req, timeout=None: _FakeResponse(ADVERSARIAL2)
    try:
        old_result = _old_fetch("http://r420-fake.invalid/")
    finally:
        CE._NO_REDIRECT_OPENER.open = _orig_open

    chk(len(old_result) == 60_000,
        "★★★★★ 옛 코드는 60,000자 악성 페이지를 안 자르고 그대로 반환한다"
        "(인과관계 직접증명 — 이 길이의 실제 정규식 처리는 초 단위로 느려진다)",
        len(old_result))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
