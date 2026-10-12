# -*- coding: utf-8 -*-
"""스캔 647라운드 회귀(직접조사, 하위위임 없음) — collect_emails.py 의
   BAD_DOMAIN 목록에서 "naver.com."(꼬리점) 이 절대 못 맞는 죽은 항목이던 결함.

   조사 배경 — 라운드514가 이 파일의 BAD_LOCAL 에서 "webmaster@example"(local
   part 리스트인데 "@"가 들어 있어 절대 매치 안 되는 죽은 항목)를 잡아낸 뒤로,
   이 세션은 같은 클래스("이 항목이 실제로 한 번이라도 맞을 수 있는가")를
   BAD_DOMAIN 전체에 대해서도 훑었다. BAD_DOMAIN 26개 항목 중
   "naver.com." 하나만 꼬리에 마침표(.)가 붙어 있다 — 나머지는 전부 평범한
   도메인 문자열이다.

   실제로 절대 못 맞는 이유는 이중이다.
   [1] EMAIL_RE(80행)의 도메인부는 `[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}` 로 끝나서
       — 마지막 글자군이 문자만 허용하는 `[A-Za-z]{2,}` 다 — 정규식이 매치한
       문자열 자체가 애초에 마침표로 끝날 수 없다(뒤에 "." 가 더 있으면
       그 "."는 매치 밖이다).
   [2] pick_emails()(283행) 은 `e = m.strip().strip(".").lower()` 로 앞뒤
       마침표를 한 번 더 명시적으로 지운 뒤에야 `local, _, dom = e.partition("@")`
       로 dom 을 뽑는다 — [1] 이 만에 하나 뚫려도 여기서 다시 막는다.
   두 방어 다 "dom 이 마침표로 끝난다"를 원천적으로 허용하지 않으므로,
   `dom.endswith("naver.com.")` 는 이 함수가 존재하는 한 True 가 될 수 없다.

   확산 범위 — clean_collected_emails.py 24행이 `from collect_emails import
   BAD_DOMAIN` 으로 **같은 튜플 객체**를 그대로 가져다 쓴다(is_junk(), 44행).
   즉 이 죽은 항목은 수집 시점(collect_emails.pick_emails)과 사후 정리
   시점(clean_collected_emails.is_junk) 양쪽에서 동시에 죽어 있었다 —
   네이버 위젯·지도·블로그 배지가 회사 자체 도메인 페이지에 남긴
   "…@naver.com" 류 기본 문의주소가 실제 업체 연락처인 양 그대로
   수집·보존될 수 있었다(옆 주석이 명시하는 "보내면 엉뚱한 회사에 간다"는
   바로 이 상황).

   고침 — collect_emails.py BAD_DOMAIN(118~126행) 의 "naver.com." 마침표
   제거 → "naver.com". 값이 아니라 오타(꼬리점)만 지웠으므로 import 로
   이 튜플을 공유하는 clean_collected_emails.py 는 손댈 필요가 없다(공유
   지점 하나만 고치면 양쪽 다 고쳐진다).

   ⚠ 이 고침은 naver.com 전체를 통째로 막는다(googleapis.com·sentry.io 등
   목록의 다른 항목들과 같은 "위젯·플랫폼이 흘리는 도메인 전체 차단" 방식).
   실제 협력사가 @naver.com 개인 메일을 업체 대표주소로 써 온 경우도 이제
   함께 걸러진다 — 목록에 이미 있던 다른 wholesale 차단(daangn.com 등)과
   같은 트레이드오프이지 이 라운드가 새로 만든 정책이 아니다.

   검증 —
   [1] 소스 — BAD_DOMAIN 리터럴에 "naver.com." (꼬리점) 토큰이 더 이상
       없고 "naver.com" 이 있다.
   [2] 구조 — EMAIL_RE 는 뒤에 마침표가 와도 도메인을 그 마침표 앞에서
       끊는다(정규식 자체가 꼬리점을 못 만든다는 것을 실측).
   [3] 단위 — pick_emails() 가 실제 회사 주소는 남기고 네이버 위젯 주소만
       거른다. clean_collected_emails.is_junk() 도 같은 주소를 "정리 대상"
       으로 잡는다(공유 지점 하나로 두 소비자 모두 고쳐졌음을 증명).
   [4] 되돌리기 — 모듈 속성만 메모리에서 옛 값(꼬리점 버전)으로 잠깐
       바꿔(디스크는 전혀 안 건드림) [3] 을 다시 돌리면 두 함수 모두
       네이버 주소를 놓친다 — 결함이 실제로 있었음을 실측.

       python test_scan_round647_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


print("=" * 72)
print("  스캔 647라운드 회귀 — collect_emails.BAD_DOMAIN 'naver.com.' 죽은 항목")
print("=" * 72)

#  이 프로세스가 실수로 운영 DB 를 열지 않도록 먼저 격리 경로를 지정한다
#  (collect_emails·clean_collected_emails 둘 다 최상위에서 `import db as DB`).
os.environ["BOKGUON_DB_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="r647_"), "_unused.db")
sys.path.insert(0, HERE)
import collect_emails as CE           # noqa: E402
import clean_collected_emails as CC   # noqa: E402

SRC = read("collect_emails.py")

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — BAD_DOMAIN 리터럴에서 꼬리점 항목이 사라졌는가")
# ──────────────────────────────────────────────────────────────
#  ⚠ 텍스트슬라이스+정규식으로 따옴표를 훑으면 이 라운드 자신이 남긴
#    주석 안의 설명용 인용부호("naver.com.", ".")까지 "토큰"으로 잘못
#    집어 함께 걸린다 — 주석은 무시하고 실제 대입되는 값만 보도록
#    ast 로 파싱해 리터럴 값 자체를 얻는다(주석 오염 없음).
import ast as _ast
_tree = _ast.parse(SRC)
_bad_domain_node = None
for _node in _ast.walk(_tree):
    if isinstance(_node, _ast.Assign) and any(
            isinstance(t, _ast.Name) and t.id == "BAD_DOMAIN" for t in _node.targets):
        _bad_domain_node = _node.value
        break
chk(_bad_domain_node is not None, "BAD_DOMAIN 정의를 소스에서 찾을 수 있다")
tokens = _ast.literal_eval(_bad_domain_node) if _bad_domain_node is not None else ()
chk("naver.com." not in tokens,
    "BAD_DOMAIN 리터럴에 꼬리점 붙은 'naver.com.' 이 더 이상 없다",
    tokens)
chk("naver.com" in tokens,
    "BAD_DOMAIN 리터럴에 'naver.com'(꼬리점 없이) 이 있다",
    tokens)
#  이 파싱이 실제 런타임 값과도 일치하는지(따로 안 어긋나는지) 함께 확인
chk(tuple(tokens) == CE.BAD_DOMAIN,
    "소스에서 파싱한 값이 import 된 실제 CE.BAD_DOMAIN 과 정확히 같다",
    (tokens, CE.BAD_DOMAIN))

# ══════════════════════════════════════════════════════════════
print("\n[2] 구조 — EMAIL_RE 매치 자체가 꼬리점을 포함할 수 없음을 실측")
# ──────────────────────────────────────────────────────────────
sample = "문의: help@naver.com. 감사합니다"
hits = CE.EMAIL_RE.findall(sample)
chk(hits == ["help@naver.com"],
    "본문에 마침표가 뒤따라도 정규식 매치 자체가 그 앞에서 끊긴다"
    "(dom 이 애초에 '.'로 끝날 수 없다)", hits)
chk(CE.pick_emails(sample, "")[0].endswith(".") is False if CE.pick_emails(sample, "") else True,
    "pick_emails() 의 e.strip('.') 방어까지 포함해도 결과에 꼬리점이 안 남는다")

# ══════════════════════════════════════════════════════════════
print("\n[3] 단위 — 고친 지금: pick_emails() 와 is_junk() 둘 다 naver.com 을 거른다")
# ──────────────────────────────────────────────────────────────
#  실제 시나리오 — 업체 자체 도메인 페이지에 네이버 지도/위젯이 남긴
#  기본 문의주소가 진짜 업체 대표주소와 나란히 떠 있다.
HTML = """
<footer>
  <p>대표: 대한가드레일 · 사업자문의 biz@daehan-guardrail.co.kr</p>
  <div id="naver-map-widget">제공: 네이버 지도 · 문의 help@naver.com</div>
</footer>
"""
found = CE.pick_emails(HTML, "daehan-guardrail.co.kr")
chk("biz@daehan-guardrail.co.kr" in found,
    "실제 업체 주소는 그대로 수집된다(회귀 없음)", found)
chk("help@naver.com" not in found,
    "★★★★★ 네이버 위젯이 남긴 주소는 이제 BAD_DOMAIN 에 걸려 빠진다", found)

why = CC.is_junk("help@naver.com", "http://daehan-guardrail.co.kr")
chk(why is not None,
    "★★★★★ clean_collected_emails.is_junk() 도 같은 주소를 정리 대상으로 잡는다"
    "(BAD_DOMAIN 을 collect_emails 에서 그대로 import 해 쓰므로 한 곳만 고쳐도 같이 고쳐짐)",
    why)
why_real = CC.is_junk("biz@daehan-guardrail.co.kr", "http://daehan-guardrail.co.kr")
chk(why_real is None,
    "실제 업체 주소는 is_junk() 가 정상으로 본다(회귀 없음)", why_real)

# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌리기 — 옛 값(꼬리점 붙은 죽은 항목)이면 실제로 결함이 있었는가")
# ──────────────────────────────────────────────────────────────
#  ★★★ 디스크의 실제 파일은 전혀 건드리지 않는다 — 모듈 속성을 메모리에서만
#      옛 값으로 잠깐 바꾸고 finally 로 반드시 되돌린다(안전 원칙 3항).
_OLD_BAD_DOMAIN = tuple(
    "naver.com." if x == "naver.com" else x for x in CE.BAD_DOMAIN)
assert "naver.com." in _OLD_BAD_DOMAIN and "naver.com" not in _OLD_BAD_DOMAIN
_saved_ce, _saved_cc = CE.BAD_DOMAIN, CC.BAD_DOMAIN
try:
    CE.BAD_DOMAIN = _OLD_BAD_DOMAIN
    CC.BAD_DOMAIN = _OLD_BAD_DOMAIN
    found_old = CE.pick_emails(HTML, "daehan-guardrail.co.kr")
    chk("help@naver.com" in found_old,
        "★★★★★ 되돌린(고치기 전) BAD_DOMAIN 으로는 네이버 주소가 그대로 "
        "'수집됨'으로 잡힌다 — 결함이 실제로 재현된다", found_old)
    why_old = CC.is_junk("help@naver.com", "http://daehan-guardrail.co.kr")
    chk(why_old is None,
        "★★★★★ 되돌린 목록으로는 is_junk() 도 같은 주소를 '정상'으로 오판한다"
        "(사후 정리 경로도 함께 뚫려 있었음을 실측)", why_old)
finally:
    CE.BAD_DOMAIN = _saved_ce
    CC.BAD_DOMAIN = _saved_cc

#  복원이 실제로 됐는지도 확인 — 이 확인 자체가 실패하면 위 finally 가
#  전제하는 "복원된다"는 가정이 깨진 것이므로 반드시 함께 검사한다.
chk(CE.BAD_DOMAIN == _saved_ce and CC.BAD_DOMAIN == _saved_cc,
    "모듈 속성이 고친 값으로 정확히 복원됐다(디스크는 애초에 안 건드림)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
