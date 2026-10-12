# -*- coding: utf-8 -*-
"""스캔 308라운드 회귀 — deploy/ 문서군 상호정합성 결함 6건, 이 세션 사상
   첫 정밀조사한 정밀조사 Agent가 발견(admin-before-go-live 순서·398개사·
   manage.py 실제 명령목록·.env 키·PWA 매니페스트/아이콘·bokguon.service
   등은 전부 클린 재확인). 306·307라운드가 다진 "추적돼야 할 사본이 실제로
   추적되는지 아무도 확인 안 함" 패턴이 이번엔 코드가 아니라 **문서**에서
   재발한 변종이다.

  [1][심각] AWS·네이버클라우드 배포절차 둘 다 오픈 절차의 smoke_test.py
      호출 앞에 자격증명 export 3줄이 없었다 — DEPLOY.md 는 125·285라운드
      사고로 이미 export 를 붙여 뒀는데(smoke_test.py 의 _creds_or_skip()
      가 셋 중 하나라도 없으면 어떤 검사도 안 돌고 exit 2), 두 클라우드
      문서는 "로그인만 건너뛴다, 공개면·보안헤더는 검증된다"고 적어 놓고
      정작 그 검증 자체가 통째로 안 도는 상태였다. DEPLOY.md 와 같은
      export+unset 블록과 종료코드 4 안내문으로 통일.
  [2] 네이버 문서의 "6건은 이미 채워져 있다"가 틀렸다(company_info.json
      실측 7/8 — AWS 문서는 이미 정확). 7건으로 정정.
  [3][컴플라이언스] company_info.json 의 hosting 값이 "아마존웹서비스
      (AWS) — 서울 리전"으로 고정돼 있다(공개 처리방침에 수탁자로 노출).
      manage.py check 의 미기재 판정은 값이 있으면 통과시키므로 이 오기재를
      못 잡는다 — 네이버클라우드 문서에 set-info hosting 단계 신설.
  [4] AWS 문서의 "옛 배포묶음 재사용 금지" 경고(실제 사고 인용 + 7줄
      검증 grep)가 네이버 문서엔 아예 없었다 — 클라우드와 무관한 위험인데
      한쪽만 알고 있었다. 네이버 문서에도 이식.
  [5] 두 클라우드 문서 다 "메모장 금지(BOM 때문에 첫 줄이 무시된다)"를
      현재형으로 적어 뒀다 — 305라운드가 envload.py 를 고쳐 이제 앱은 BOM
      을 걸러낸다. DEPLOY.md 는 이미 그 사실에 맞게 완화된 문구를 쓰는데
      두 클라우드 문서만 안 따라갔다. 같은 문구로 통일.
  [6][심각, 교차파일] nginx_bokguon.conf 의 숨김파일 차단 정규식
      (location 물결 슬래시역슬래시점)이 앱스토어_배포_가이드.md 가 안내하는
      `/.well-known/assetlinks.json` 경로까지 막고 있었다 — nginx 는 접두사
      매칭이 ^~ 없이 이겨도(심지어 그 접두사가 더 길어도) 뒤따르는 정규식을
      파일 순서대로 마저 검사한다(포트 80 블록엔 인증서 갱신용 예외가
      있는데 443 블록엔 짝이 없었다). `location ^~ /.well-known/` 로
      확정시켜 정규식 검사 자체를 안 타게 수정(alias 로 실제 디렉터리 연결
      — /static/ 과 같은 패턴). 앱스토어 가이드에도 그 디렉터리 경로를
      명시.

  ⚠ 이 라운드는 문서·설정 텍스트만 고쳐 실행 코드 변경이 없다 — 회귀
    테스트는 grep 기반 구조 확인과, nginx 의 실제 location 매칭 알고리즘을
    이 파일의 진짜 location 블록에 대해 그대로 재현해 실행하는 것으로
    구성한다(라이브 nginx 없이도 "이 설정을 nginx 가 실제로 어떻게
    처리할지"를 정확히 검증할 수 있다 — 알고리즘은 nginx 공식 문서의
    위치 매칭 규칙을 그대로 옮긴 것).

      python test_scan_round308_fixes.py
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


AWS_SRC = read(os.path.join("deploy", "AWS_배포절차.md"))
NAVER_SRC = read(os.path.join("deploy", "네이버클라우드_배포절차.md"))
APPSTORE_SRC = read(os.path.join("deploy", "앱스토어_배포_가이드.md"))
NGINX_SRC = read(os.path.join("deploy", "nginx_bokguon.conf"))
COMPANY_INFO = read(os.path.join("data", "company_info.json"))

print("=" * 72)
print("  스캔 308라운드 회귀 — deploy/ 문서군 상호정합성 6건")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — 스모크테스트 자격증명 export (AWS·네이버 공통)")
# ------------------------------------------------------------
for name, src in (("AWS", AWS_SRC), ("네이버클라우드", NAVER_SRC)):
    chk('export BOKGUON_TEST_ADMIN_PW="bokguon2026"' in src
        and 'export BOKGUON_TEST_INSURER_PW="bokguon2026"' in src
        and 'export BOKGUON_TEST_PARTNER_PW="partner2026"' in src,
        f"★★★★★ {name} 문서가 smoke_test.py 앞에 세 자격증명을 export 한다"
        "(고치기 전엔 없어 검사가 통째로 0건 실행)")
    chk("unset BOKGUON_TEST_ADMIN_PW BOKGUON_TEST_INSURER_PW BOKGUON_TEST_PARTNER_PW" in src,
        f"STEP {name} 문서가 사용 뒤 unset 도 한다(DEPLOY.md 와 같은 위생)")
    chk("종료코드 4" in src, f"STEP {name} 문서가 정확한 기대 종료코드(4)를 안내한다(0 이 아님)")

# ============================================================
print("\n[2][3] 소스 확인 — 회사정보 건수·hosting 값")
# ------------------------------------------------------------
_m = re.search(r'"hosting":\s*"([^"]*)"', COMPANY_INFO)
chk(bool(_m) and "AWS" in _m.group(1),
    "STEP (사전조건) company_info.json 의 hosting 이 실제로 AWS 로 박혀 있다"
    "(이 값이 그대로 나가면 네이버클라우드 배포에선 오기재가 된다)", _m.group(1) if _m else None)
chk("6건은 이미" not in NAVER_SRC,
    "★★★★ 네이버 문서에 틀린 6건 문구가 더는 없다")
chk("7건은 이미 채워져 있다" in NAVER_SRC,
    "★★★★★ 네이버 문서가 실측과 일치하는 7건으로 정정됐다(AWS 문서의 7/8 과 일치)")
chk('set-info hosting "네이버클라우드"' in NAVER_SRC,
    "★★★★★ 네이버 문서가 hosting 값을 실제 배포 대상에 맞게 재설정하는 단계를 갖는다"
    "(고치기 전엔 AWS 로 고정된 값이 공개 처리방침에 그대로 노출될 뻔했다)")

# ============================================================
print("\n[4] 소스 확인 — 옛 배포묶음 재사용 경고 이식")
# ------------------------------------------------------------
chk("올리기 직전에 새로 만든다" in NAVER_SRC and "3분의 1 크기" in NAVER_SRC,
    "★★★★ 네이버 문서에 AWS 문서의 옛 배포묶음 재사용 경고가 이식됐다")
chk("grep -E 'bokguon_service/(app|db|manage|dispatch|compliance|notify_popbill|partner_accounts)" in NAVER_SRC,
    "STEP 네이버 문서도 7개 핵심파일 포함 여부를 grep 으로 직접 검증하는 단계를 갖는다")

# ============================================================
print("\n[5] 소스 확인 — BOM 문구 현재형→완화형 통일")
# ------------------------------------------------------------
for name, src in (("AWS", AWS_SRC), ("네이버클라우드", NAVER_SRC)):
    chk("BOM 때문에 첫 줄이 무시된다" not in src,
        f"★★★★ {name} 문서에 305라운드 이전(BOM 무조건 무시) 낡은 문구가 더는 없다")
    chk("걸러내도록" in src and "고쳐 뒀지만" in src and "305라운드" in src,
        f"STEP {name} 문서가 DEPLOY.md 와 같은 완화된 문구를 쓴다")

# ============================================================
print("\n[6] 실행 — nginx 실제 location 매칭 알고리즘을 이 파일 그대로 재현")
# ------------------------------------------------------------
LOC_RE = re.compile(r"location\s+(=|~\*|~|\^~)?\s*([^\s{]+)\s*\{")


def _extract_443_block(src):
    i_443 = src.index("listen 443 ssl;")
    i_start = src.rindex("server {", 0, i_443)
    depth, i = 0, i_start
    while True:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    return src[i_start:i + 1]


def _locations(block):
    return [(m.group(1) or "", m.group(2)) for m in LOC_RE.finditer(block)]


def _resolve(path, locations):
    """nginx 공식 문서의 location 선택 규칙을 그대로 구현 — 실제 nginx 없이도
    이 설정파일이 어떤 요청을 어느 location 으로 보낼지 정확히 판정한다."""
    for mod, loc in locations:
        if mod == "=" and path == loc:
            return mod, loc
    best = None
    for mod, loc in locations:
        if mod in ("", "^~") and path.startswith(loc):
            if best is None or len(loc) > len(best[1]):
                best = (mod, loc)
    if best and best[0] == "^~":
        return best
    for mod, loc in locations:
        if mod in ("~", "~*"):
            flags = re.IGNORECASE if mod == "~*" else 0
            if re.search(loc, path, flags):
                return mod, loc
    return best


try:
    block_443 = _extract_443_block(NGINX_SRC)
    locs = _locations(block_443)
    chk(("^~", "/.well-known/") in locs,
        "STEP 443 블록에 ^~ /.well-known/ location 이 실제로 파싱된다(전제조건)")

    r1 = _resolve("/.well-known/assetlinks.json", locs)
    chk(r1 == ("^~", "/.well-known/"),
        "★★★★★ /.well-known/assetlinks.json 요청이 이제 정규식(숨김파일 차단)이 아니라"
        " ^~ /.well-known/ location 으로 확정된다(고치기 전엔 location ~ /\\. 이 잡아 404)",
        r1)

    r2 = _resolve("/.env", locs)
    chk(r2[0] in ("~", "~*") and r2[1] == r"/\.",
        "★★★★ 대조군 — 진짜 숨김파일 경로(/.env)는 여전히 차단 규칙에 걸린다"
        "(과잉교정 아님 — 원래 보호가 그대로 살아있다)", r2)

    r3 = _resolve("/", locs)
    chk(r3 == ("", "/"),
        "STEP 대조군 — 루트 요청은 여전히 일반 location / (앱 프록시)로 간다", r3)

    r4 = _resolve("/static/style.css", locs)
    chk(r4 == ("", "/static/"),
        "STEP 대조군 — 정적 파일 요청은 여전히 /static/ (alias)로 간다(회귀 없음)", r4)

    r5 = _resolve("/api/photos/5/file", locs)
    chk(r5[0] == "~" and "photos" in r5[1],
        "STEP 대조군 — 사진 파일 서빙 경로(레이트리밋 제외)는 여전히 그 전용 "
        "location 으로 간다(더 앞선 정규식이라 순서상 먼저 걸림, 회귀 없음)", r5)

    r6 = _resolve("/api/login", locs)
    chk(r6 == ("=", "/api/login"),
        "STEP 대조군 — 로그인 레이트리밋 exact-match location 은 그대로 최우선 유지된다", r6)

    # ⚠ ^~ 없이(과거 초안처럼) 두면 여전히 안 고쳐진 것과 같다는 걸 이 파일
    #   자신의 location 목록으로 대조 — 실제로 ^~ 가 빠진 사본을 만들어 확인.
    _plain_locs = [(("" if mod == "^~" else mod), loc) for mod, loc in locs]
    r_plain = _resolve("/.well-known/assetlinks.json", _plain_locs)
    chk(r_plain[0] in ("~", "~*"),
        "★★★★★ 대조군 — ^~ 를 빼면(처음에 실제로 그렇게 썼다가 스스로 발견해 고침)"
        " 같은 경로가 다시 숨김파일 차단 정규식에 잡힌다 — ^~ 가 이 수정의 핵심이었음을 증명",
        r_plain)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드308 [6] nginx 매칭 실측", f"{type(e).__name__} {e}")

# ============================================================
print("\n[7] 소스 확인 — 앱스토어 가이드 보강")
# ------------------------------------------------------------
chk("네이버클라우드_배포절차.md" in APPSTORE_SRC,
    "STEP 앱스토어 가이드가 이제 AWS 문서만이 아니라 네이버클라우드 문서도 안내한다")
chk("/opt/bokguon/.well-known/" in APPSTORE_SRC,
    "STEP 앱스토어 가이드가 실제 assetlinks.json 배치 디렉터리를 명시한다")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
