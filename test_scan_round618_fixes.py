# -*- coding: utf-8 -*-
"""스캔 618라운드 회귀 — partner_accounts.py(협력사 포털 계정 일괄발급 CLI)
make_login_id()가 유니코드 전각숫자를 걸러내지 못해 발급 아이디 끝자리에
전각 문자가 그대로 박히던 결함.

형제(app.py:_auto_login_id, 8352행 — issue_partner_login()의 자동채번
경로가 쓰는 바로 그 함수)는 이미 [^0-9]로 사업자번호에서 숫자만 뽑는데,
이 CLI만 \\D(=\\d 의 여집합)를 썼다 — round497이 valid_biz_no()에서 이미
밝힌 것과 같은 결함 클래스다: 파이썬의 \\d 는 유니코드 전각숫자(１２３ 등,
U+FF10~19)도 "숫자"로 쳐서 \\D 가 지우지 않는다.

partners.biz_no 에 전각숫자가 섞여 있으면(round497 수정 이전에 등록됐거나,
이 CLI 자신은 valid_biz_no()를 아예 거치지 않고 partners 표의 biz_no 값을
그대로 신뢰하므로 — pick()이 그냥 SELECT 해 올 뿐이다) 그 문자가 살아남아
로그인 아이디 끝에 그대로 박힌다. 이 함수 자신이 위에서 "사람이 전화로
불러 주기 쉬워야 한다"고 명시한 설계 목적(혼동하기 쉬운 0/O·1/l/I 를 이미
알파벳에서 뺀 것과 같은 이유)에 정면으로 어긋나고, issue_partner_login 의
수동 아이디 지정 경로가 요구하는 [a-z0-9_-] 형식과도 어긋난다 — 업체가
일괄발급받은 아이디를 타이핑조차 못 해 첫 로그인 자체가 막힐 수 있다.

⚠ partner_accounts.py는 app.py가 import하는 모듈이 아니라 독립 CLI라서,
  이 라운드는 서버 재기동·BUILD_HASH 로테이션이 필요 없다(라운드475·482·
  495와 같은 독립 CLI류 예외).

    python test_scan_round618_fixes.py
"""
import ast
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(c, n, d=""):
    (PASS if c else FAIL).append((n, d))
    print(("  [OK]   " if c else "  [FAIL] ") + n + ("" if c else f"   {d}"))


print("=" * 72)
print("  스캔 618라운드 회귀 — 협력사 계정발급 아이디의 전각숫자 미정규화")
print("=" * 72)

PA_PATH = os.path.join(HERE, "partner_accounts.py")
PA_SRC = io.open(PA_PATH, encoding="utf-8").read()
APP_SRC = io.open(os.path.join(HERE, "app.py"), encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — make_login_id() 내부의 한 줄만 바뀌었는지")
# ──────────────────────────────────────────────────────────────
CUR = 'biz = re.sub(r"[^0-9]", "", row["biz_no"] or "")\n'
ORIG = 'biz = re.sub(r"\\D", "", row["biz_no"] or "")\n'

chk(PA_SRC.count(CUR) == 1, "새 정규식([^0-9]) 줄이 소스에 정확히 한 번만 있다", PA_SRC.count(CUR))
i_def = PA_SRC.index("def make_login_id(")
chk(0 < PA_SRC.index(CUR) - i_def < 1500, "그 한 줄이 make_login_id() 함수 본문 안에 있다")
chk('biz = re.sub(r"[^0-9]", "", (p["biz_no"] or ""))' in APP_SRC,
    "형제 app.py:_auto_login_id()는 원래도 [^0-9]를 쓴다(대조군 — 이번 라운드가 안 건드림)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 호출 — 전각숫자 섞인 사업자번호로 make_login_id() 직접 실행")
# ──────────────────────────────────────────────────────────────
#  ⚠ partner_accounts.py는 top-level에서 db.py를 import한다(BOKGUON_DB_PATH
#    기본값이 실제 bokguon.db 경로) — 이 테스트는 FakeConn만 써서 DB를 아예
#    안 열지만, 표준 안전수칙대로 import 전에 스크래치 경로로 리다이렉트한다.
_tmpdir = tempfile.mkdtemp(prefix="r618_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "v.db")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "test.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
import partner_accounts as PA


class _FakeConn:
    """이 파일 자신의 demo() self-check(273행 부근)가 이미 쓰는 것과 같은
    가짜 연결 — _taken_anywhere()가 무엇을 조회하든 '아무 데도 없음'만
    응답한다. 진짜 sqlite3 연결을 열 필요가 없다(make_login_id()의 순수
    문자열 로직만 검증하면 되므로)."""
    def execute(self, *a):
        class R:
            def fetchone(self_inner):
                return None
        return R()


#  ASCII 숫자 10자리 + 잉여 전각숫자 1개(U+FF11) — round497이 valid_biz_no()
#  회귀테스트에서 쓴 것과 같은 모양의 입력이다.
FULLWIDTH_BIZ = "1234567890１"
conn = _FakeConn()

lid = PA.make_login_id(conn, {"id": 1, "biz_no": FULLWIDTH_BIZ}, set())
chk(lid == "p567890",
    "★★★★★ 새 코드: 전각숫자가 정규화 단계에서 걸러져 나머지 10자리 ASCII "
    "숫자만으로 아이디를 만든다(형제 _auto_login_id·이 파일 demo()의 "
    "'123-45-67890'→'p567890'과 같은 규칙)", lid)
chk(lid.isascii(), "★★★★★ 새 코드: 발급된 아이디가 순수 ASCII다(전각 문자가 안 섞인다)", lid)
chk(all(ch in "abcdefghijklmnopqrstuvwxyz0123456789" for ch in lid),
    "새 코드: 아이디가 issue_partner_login이 요구하는 [a-z0-9_-] 문자집합 안에 있다", lid)

#  회귀없음 — 순수 ASCII 사업자번호는 그대로 동작한다(demo()의 기존 값과 동일)
lid_ascii = PA.make_login_id(conn, {"id": 7, "biz_no": "123-45-67890"}, set())
chk(lid_ascii == "p567890", "회귀없음: 순수 ASCII 사업자번호는 여전히 정상 동작한다", lid_ascii)

# ══════════════════════════════════════════════════════════════
print("\n[3] 되돌림-증명 — 그 한 줄만 되돌려 독립 사본 네임스페이스에서 재실행")
print("    (partner_accounts.py 파일 자체는 이 과정에서 전혀 안 건드림)")
# ──────────────────────────────────────────────────────────────
reverted = PA_SRC.replace(CUR, ORIG)
assert reverted != PA_SRC, "되돌림 치환이 실제로 안 먹었다"

_tree = ast.parse(reverted)
_lines = reverted.splitlines(keepends=True)
_reverted_fn_src = None
for _node in ast.walk(_tree):
    if isinstance(_node, ast.FunctionDef) and _node.name == "make_login_id":
        _reverted_fn_src = "".join(_lines[_node.lineno - 1:_node.end_lineno])
        break
assert _reverted_fn_src, "되돌린 make_login_id() 함수 소스를 AST로 못 뽑음"
chk("\\D" in _reverted_fn_src, "되돌린 함수 소스에 옛 \\D 정규식이 들어 있다(되돌림 확인)")

#  독립 사본 네임스페이스(dict(vars(PA)))에만 exec — 실제 partner_accounts
#  모듈도, 디스크의 파일도 이 과정에서 전혀 안 바뀐다.
_ns = dict(vars(PA))
exec(compile(_reverted_fn_src, "<round618-reverted:make_login_id>", "exec"), _ns)
lid2 = _ns["make_login_id"](conn, {"id": 1, "biz_no": FULLWIDTH_BIZ}, set())
chk(not lid2.isascii(),
    "★★★★★ 옛 코드(되돌림): 아이디 끝에 전각 문자가 그대로 살아남는다 — 이 테스트가 "
    "진짜 결함을 잡아낼 능력이 있음을 증명", lid2)
chk(lid2 == "p67890１",
    "★★★★★ 옛 코드(되돌림): 정확히 예상한 모양(전각숫자가 아이디 마지막 글자로 "
    "그대로 박힘)으로 재현된다", lid2)

chk(io.open(PA_PATH, encoding="utf-8").read() == PA_SRC,
    "★★★★★ partner_accounts.py는 이 되돌림-증명 내내 디스크에서 전혀 건드려지지 않았다"
    "(되돌린 함수는 dict(vars(PA)) 독립 사본에만 exec됨)")

os.environ.pop("BOKGUON_DB_PATH", None)
os.environ.pop("BOKGUON_LOG_FILE", None)
os.environ.pop("BOKGUON_ENV", None)
os.environ.pop("BOKGUON_SEED_DEMO", None)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
