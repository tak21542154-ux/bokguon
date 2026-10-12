# -*- coding: utf-8 -*-
"""스캔 648라운드 회귀(직접조사, 하위위임 없음) — collect_emails.py 의
   refuses_collection() 이 REFUSE_MARKERS 의 유일한 비(非)한글 항목
   "email collection denial" 을 대소문자가 다르면 못 잡던 결함.

   조사 배경 — 라운드514(BAD_LOCAL 의 "webmaster@example" 죽은 항목)·
   라운드647(BAD_DOMAIN 의 "naver.com." 죽은 항목)이 이 파일의 리터럴
   목록들을 "이 항목이 실제로 한 번이라도 맞을 수 있는가" 관점에서 훑은
   데 이어, 이번엔 REFUSE_MARKERS(74~78행, §50-2 수집거부 문구 목록)를
   같은 관점으로 훑었다. 8개 항목 중 7개는 한글이라 대소문자 개념 자체가
   없고, 나머지 1개 "email collection denial" 만 영문이다.

   refuses_collection() 은 다음과 같이 매치했다(고치기 전):
       flat = re.sub(r"\\s+", "", re.sub(r"<[^>]+>", "", html))
       return any(re.sub(r"\\s+", "", m) in flat for m in REFUSE_MARKERS)
   flat 에도 각 마커 m 에도 .lower() 가 전혀 없었다 — 대소문자를 그대로
   비교한다는 뜻이다. REFUSE_MARKERS 의 영문 항목은 이미 전부 소문자로
   적혀 있으므로, 실제 사이트가 이 문구를 "Email Collection Denial"·
   "EMAIL COLLECTION DENIAL"처럼 다른 대소문자로 적으면(사람이 직접 쓰는
   영문 안내문이라 표기가 얼마든지 갈릴 수 있다) 정확히 이 문구를 페이지에
   명시한 사이트조차 refuses_collection() 이 False 를 냈다(실측: 아래
   [2]·[3]).

   이 파일의 존재 이유(모듈 docstring 11~15행)가 바로 "정보통신망법
   §50-2 — 수집을 거부하는 의사가 명시된 페이지에서 자동 수집하면 안
   된다"이므로, 대소문자 하나 때문에 명시적 거부 의사를 못 알아보는 것은
   이 파일 자신의 목적을 정면으로 벗어난다.

   고침 — collect_emails.py refuses_collection() 에 .lower() 두 곳
   추가(flat 자체와 마커 비교 양쪽) — 한글 7개 항목은 대소문자가 없어
   .lower() 가 완전한 무연산(no-op)이라 회귀 위험이 없고, 영문 1개 항목만
   이제 대소문자 무관하게 잡힌다. 448→456줄(+8, 대부분 근거 주석).

   검증 —
   [1] 소스 — refuses_collection() 함수 몸통에 .lower() 가 (flat 한 번 +
       마커 비교 한 번) 정확히 존재한다.
   [2] 단위 — 영문 마커를 대문자·Title 케이스로 적은 HTML 이 이제
       refuses_collection() 에서 True 로 잡힌다. 기존처럼 소문자 그대로인
       경우·태그로 끊긴 한글 마커(라운드267 케이스)·마커가 전혀 없는
       평범한 한/영 소개문은 전부 회귀 없이 그대로 동작한다(과잉탐지 방지
       대조군 포함).
   [3] 되돌리기 — 실제 파일은 전혀 건드리지 않고, 고치기 전 소스 그대로를
       독립된 이름공간에 exec 해(REFUSE_MARKERS 는 CE 에서 그대로 가져와
       공유 — 안전원칙 3항의 함수 단위 되돌리기 기법) 같은 대문자 샘플에
       돌리면 실제로 False 를 내는지(결함이 실제로 있었음을) 인과관계로
       재현한다. 같은 되돌린 함수가 소문자 그대로인 마커는 여전히 잡는
       것도 함께 확인해, 이번 회귀가 "대소문자"에만 정확히 좁혀져 있음을
       보인다.

       python test_scan_round648_fixes.py
"""
import ast
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    import io
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


print("=" * 72)
print("  스캔 648라운드 회귀 — collect_emails.refuses_collection() 영문마커 대소문자")
print("=" * 72)

#  이 프로세스가 실수로 운영 DB 를 열지 않도록 먼저 격리 경로를 지정한다
#  (collect_emails.py 는 최상위에서 `import db as DB`).
os.environ["BOKGUON_DB_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="r648_"), "_unused.db")
sys.path.insert(0, HERE)
import collect_emails as CE           # noqa: E402

SRC = read("collect_emails.py")

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — refuses_collection() 몸통에 .lower() 가 양쪽에 있는가")
# ──────────────────────────────────────────────────────────────
#  ⚠ 텍스트 슬라이스+substring count 는 이 라운드 자신이 남긴 설명주석 안의
#    ".lower()" 인용까지 "코드"로 잘못 집어 함께 세어 버린다(round647이 이미
#    "주석 속 인용부호에 오염되지 않도록" ast를 쓴 것과 같은 함정 — 여기서도
#    실측으로 재현: 순수 substring count 는 3을 낸다, 주석 1 + 실제 코드 2).
#    주석은 AST에 안 남으므로 함수 본문을 ast로 파싱해 실제 실행되는
#    .lower() 호출(Attribute 노드)만 센다.
i_rc = SRC.index("def refuses_collection(")
i_rc_end = SRC.index("\n\n\ndef ", i_rc)
rc_body = SRC[i_rc:i_rc_end]
chk(rc_body.count(".lower()") == 3,
    "STEP 문서화 — 이 함수의 근거주석 자신도 '.lower()' 문구를 인용해서 "
    "쓰므로, 순수 텍스트 카운트는 실제 코드(2)+주석 인용(1)=3이 나온다"
    "(바로 다음 검사가 이 오염을 걷어내고 실제 코드만 센다)",
    rc_body.count(".lower()"))
_rc_tree = ast.parse(rc_body)
_rc_func = _rc_tree.body[0]
assert isinstance(_rc_func, ast.FunctionDef) and _rc_func.name == "refuses_collection"
_lower_calls = [n for n in ast.walk(_rc_func)
                if isinstance(n, ast.Attribute) and n.attr == "lower"]
chk(len(_lower_calls) == 2,
    "★★★★★ 주석을 배제한 실제 AST 기준 — refuses_collection() 안에 "
    ".lower() 호출이 정확히 2번(flat 한 번 + 마커 한 번) 있다",
    len(_lower_calls))
chk('re.sub(r"<[^>]+>", "", html)' in rc_body,
    "라운드267 의 태그제거 로직은 그대로 남아 있다(회귀 없음)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 대소문자가 다른 영문 마커도 이제 잡히는가")
# ──────────────────────────────────────────────────────────────
UPPER_HTML = ("<html><body><h1>NOTICE</h1><p>This site posts: "
              "<b>EMAIL COLLECTION DENIAL</b>. Automated scraping is not permitted."
              "</p></body></html>")
TITLE_HTML = ("<p>Please note our <span>Email</span> <span>Collection</span> "
              "<span>Denial</span> policy before contacting us.</p>")
EXACT_HTML = "<p>email collection denial - do not harvest this page.</p>"
KOREAN_TAGGED = "<html><body><p>이메일<b>무단</b> 수집을 거부합니다.</p></body></html>"
PLAIN_EN_NO_MARKER = ("<p>Welcome to Daehan Guardrail Co. We specialize in "
                      "highway safety barriers. Contact info@r648realcompany.co.kr.</p>")
PLAIN_KO_NO_MARKER = "<p>회사소개: 저희는 방수·도장 전문 시공업체입니다. 문의는 전화로 부탁드립니다.</p>"

chk(CE.refuses_collection(UPPER_HTML) is True,
    "★★★★★ 전부 대문자(EMAIL COLLECTION DENIAL)인 영문 마커도 탐지한다"
    "(고치기 전엔 미탐)", UPPER_HTML)
chk(CE.refuses_collection(TITLE_HTML) is True,
    "★★★★★ Title 케이스 + <span> 으로 단어마다 끊긴 영문 마커도 탐지한다"
    "(대소문자·태그 결함이 동시에 걸린 현실적인 조합)", TITLE_HTML)
chk(CE.refuses_collection(EXACT_HTML) is True,
    "STEP 대조군 — 기존처럼 소문자 그대로인 영문 마커는 그대로 탐지된다(회귀 없음)")
chk(CE.refuses_collection(KOREAN_TAGGED) is True,
    "STEP 대조군 — 라운드267 이 고친 한글 태그끊김 케이스는 그대로 동작한다(회귀 없음)")
chk(CE.refuses_collection(PLAIN_EN_NO_MARKER) is False,
    "STEP 대조군 — 마커 없는 평범한 영문 소개문은 여전히 False(과잉탐지 아님)",
    PLAIN_EN_NO_MARKER)
chk(CE.refuses_collection(PLAIN_KO_NO_MARKER) is False,
    "STEP 대조군 — 마커 없는 평범한 한글 소개문은 여전히 False(과잉탐지 아님)")

# ══════════════════════════════════════════════════════════════
print("\n[3] 되돌리기 — 대소문자 접기 이전 코드로는 실제로 결함이 있었는가")
# ──────────────────────────────────────────────────────────────
#  ★★★ 디스크의 실제 파일은 전혀 건드리지 않는다 — 고치기 전 소스를
#      독립된 이름공간에 exec 해서만 재구성한다(안전 원칙 3항, 함수단위).
OLD_SRC = (
    'def refuses_collection(html):\n'
    '    flat = re.sub(r"\\s+", "", re.sub(r"<[^>]+>", "", html))\n'
    '    return any(re.sub(r"\\s+", "", m) in flat for m in REFUSE_MARKERS)\n'
)
_ns = {"re": re, "REFUSE_MARKERS": CE.REFUSE_MARKERS}
exec(compile(OLD_SRC, "<round648_old_refuses_collection>", "exec"), _ns)
old_refuses_collection = _ns["refuses_collection"]

chk(old_refuses_collection(UPPER_HTML) is False,
    "★★★★★ 되돌린(고치기 전) 코드는 대문자 영문 마커를 놓친다 — "
    "결함이 실제로 재현된다", UPPER_HTML)
chk(old_refuses_collection(TITLE_HTML) is False,
    "★★★★★ 되돌린 코드는 Title 케이스 마커도 놓친다 — 결함 재현", TITLE_HTML)
chk(old_refuses_collection(EXACT_HTML) is True,
    "대조군 — 되돌린 코드도 소문자 그대로인 마커는 원래부터 잡았다"
    "(이번 회귀가 '대소문자'에만 좁혀진 것이지 전면 파손이 아님을 확인)")
chk(old_refuses_collection(KOREAN_TAGGED) is True,
    "대조군 — 되돌린 코드도 한글 마커(대소문자 무관)는 원래부터 잡았다"
    "(라운드267 결함과는 서로 다른 결함임을 확인)")

# CE 모듈 자체는 이 섹션에서 한 번도 바뀌지 않았다 — 실제로 안 바뀌었는지도 확인.
chk(CE.refuses_collection is not old_refuses_collection,
    "고쳐진 CE.refuses_collection 과 되돌린 사본은 서로 다른 객체다"
    "(모듈을 몽키패치하지 않고 독립 이름공간만 썼음을 보증)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
