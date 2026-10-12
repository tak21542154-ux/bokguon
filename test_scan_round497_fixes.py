# -*- coding: utf-8 -*-
"""스캔 497라운드 회귀 — valid_biz_no()가 유니코드 전각숫자를 걸러내지
못해 사업자등록번호 체크섬 검증과 DUP_BIZNO 중복확인을 동시에 우회하던
결함.

파이썬의 \\D(=\\d 의 여집합)는 유니코드 전각숫자(예: １２３, U+FF10~19)도
"숫자"로 쳐서 re.sub(r"\\D","",...)가 지우지 않는다 — 체크섬은 그대로
통과하고, 저장값도 전각 그대로 남아 ASCII로 이미 등록된 같은 번호와
문자열이 달라 여러 호출지점의 DUP_BIZNO 중복확인(WHERE biz_no=?)을
우회한다. 형제(insurers.name, 라운드458)는 이미 NFKC 정규화로 이 종류의
유니코드-형태 우회를 막는데, 이 함수만 못 물려받았다.

이름(자유텍스트)과 달리 사업자번호는 순수 숫자코드라 정규화-후-수용
대신 ASCII 숫자(0-9)만 인정해 전각 입력을 자릿수 미달로 거부한다
(\\D → [^0-9]).

⚠⚠ [라운드621] 되돌림-증명 기법을 옛 세대(app.py를 실제로 디스크에 써넣고
워커 서브프로세스를 돌린 뒤 복원)에서 round485가 확립한 "공유 사본
네임스페이스에 순서대로 exec" 안전패턴(기법4)으로 이관한다. valid_biz_no()
는 api_partner_update() 안에서 맨이름으로 불리므로(바로 아래 CALLER_CUR),
독립된 사본 네임스페이스 하나(_ns = dict(vars(A)))에 되돌린 valid_biz_no를
먼저 exec하고, 그 다음 되돌린 api_partner_update 본문을 **같은** _ns에
exec해야 그 안에서 맨이름으로 부르는 valid_biz_no가 실제 모듈이 아니라
이 _ns 안의 되돌린 버전으로 resolve된다(round619 gotcha — 보조
몽키패치는 반드시 사본 쪽에 미리 심어 둔다). api_partner_update()는 단일
라우트 핸들러라 결과 함수를 A.app.view_functions 딕셔너리 항목에만 잠깐
치환한다 — 진짜 app.py 파일은 전혀 안 쓴다. valid_biz_no() 단위 확인도
더 이상 별도 워커 서브프로세스가 필요 없다 — A.valid_biz_no()는 이 과정
내내 한 번도 안 바뀌므로(사본에만 exec) 그냥 직접 호출한다.
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
print("  스캔 497라운드 회귀 — 사업자번호 전각숫자 체크섬·중복확인 우회")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — valid_biz_no() 내부의 한 줄만 바뀌었는지")
# ──────────────────────────────────────────────────────────────
#  ⚠⚠ [라운드608] round601~ 형제결함군(raw re.sub 3번째 인자가 JSON 비문자열이면
#    TypeError로 500) 처방으로 valid_biz_no() 내부가 _s(s)를 거치게 바뀌었다 —
#    [^0-9]→\D 되돌림 대상(라운드497 자신의 기여)과는 독립된 축이라, CUR/ORIG
#    양쪽에 _s()는 그대로 남기고 문자클래스만 오간다(라운드498 테스트의 같은
#    원칙과 동일).
CUR = '    d = re.sub(r"[^0-9]", "", _s(s))\n'
ORIG = '    d = re.sub(r"\\D", "", _s(s))\n'

chk(APP_SRC.count(CUR) == 1, "새 정규식([^0-9])이 소스에 정확히 한 번만 있다(다른 곳에 실수로 안 퍼짐)",
    APP_SRC.count(CUR))
i_def = APP_SRC.index("def valid_biz_no(")
chk(APP_SRC.index(CUR) - i_def < 2000, "그 한 줄이 valid_biz_no() 함수 본문 안에 있다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 준비 — 스크래치 DB + /api/partners/<id> PATCH 직접 호출")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round497_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB                 # noqa: E402
DB.init_db()
import app as A                 # noqa: E402

_seed_n = [0]


def _run_patch():
    """옛 워커(test_scan_round497_worker.py, 삭제됨)의 로직을 그대로 옮김 —
    매 시나리오(현재/되돌림/원복)마다 독립된 관리자·업체를 새로 만들어
    세 번의 호출이 서로 간섭하지 않게 한다(active_count도 이 시나리오
    자신의 두 업체 id로만 좁혀서 센다)."""
    _seed_n[0] += 1
    n = _seed_n[0]
    #  체크섬은 통과하지만(라운드497 이전) 유니코드 전각숫자로 적은 같은 사업자번호
    FULLWIDTH_BIZ = "１２３４５６７８９１"

    c = DB.get_db()
    c.execute("INSERT INTO admins(username,password_hash,name,role) "
              f"VALUES('r497a{n}','x','n1','최고관리자')")
    pid1 = c.execute("INSERT INTO partners(name,status,biz_no) "
                      f"VALUES('A상사{n}','활성','1234567891')").lastrowid
    pid2 = c.execute(f"INSERT INTO partners(name,status) VALUES('B상사{n}','심사중')").lastrowid
    c.commit(); c.close()

    cl = A.app.test_client()
    with cl.session_transaction() as s:
        s["admin"] = f"r497a{n}"; s["admin_role"] = "최고관리자"; s["_csrf"] = "c1"
    r = cl.patch(f"/api/partners/{pid2}",
                 json={"biz_no": FULLWIDTH_BIZ, "status": "활성",
                       "status_reason": "심사완료함"},
                 headers={"X-CSRF-Token": "c1"})
    resp = r.get_json() or {}

    conn = A.DB.get_db()
    active_count = conn.execute(
        "SELECT COUNT(*) n FROM partners WHERE status='활성' AND id IN (?,?)",
        (pid1, pid2)).fetchone()["n"]
    p2 = dict(conn.execute("SELECT status, biz_no FROM partners WHERE id=?", (pid2,)).fetchone())
    conn.close()
    return {
        "status": r.status_code,
        "error": resp.get("error"),
        "active_count": active_count,
        "p2_status": p2["status"],
        "p2_biz_no": p2["biz_no"],
    }


try:
    out = _run_patch()
    chk(out["status"] == 400, "새 코드: 전각숫자 사업자번호는 400으로 거부된다", out)
    chk(out["p2_status"] == "심사중" and out["p2_biz_no"] is None,
        "★★★★★ 새 코드: 거부된 업체는 활성화되지 않고 biz_no도 저장되지 않는다", out)
    chk(out["active_count"] == 1,
        "★★★★★ 새 코드: 활성 업체가 1곳(기존 A상사)뿐 — 같은 번호의 중복 활성화가 없다", out)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 되돌림-증명 — valid_biz_no() 내부 + 이 테스트가 실제로 두드리는")
    print("    호출부(api_partner_update) 한 곳을 함께 원복")
    # ──────────────────────────────────────────────────────────
    #  ⚠⚠ [라운드498] 원래는 valid_biz_no() 내부(CUR/ORIG)만 되돌렸는데,
    #    라운드498이 호출부(api_partner_update 등 8곳)의 별도 정규화도
    #    [^0-9]로 통일하면서, 내부만 되돌리면 이 호출부가 이미 [^0-9]로
    #    전각숫자를 걸러내 버려 이 테스트가 원래 재현하려던 "전각이 그대로
    #    통과·저장"이 더는 안 나온다(빈 문자열이 되어 형식오류 400만 남음).
    #    이 테스트가 실제로 두드리는 그 한 호출부(api_partner_update)도
    #    함께 되돌려야 라운드497 시점의 실제 취약 상태를 재현한다 — 다른
    #    7개 호출부(라운드498 자신의 되돌림-증명 몫)는 손대지 않는다.
    #  ⚠⚠ [라운드608] 같은 이유(round601~ 형제결함군) — 이 호출부도 d[f]가
    #    _s()를 거치게 바뀌었다. [^0-9]→\D 축만 오가도록 양쪽에 _s() 유지.
    CALLER_CUR = '                d[f] = re.sub(r"[^0-9]", "", _s(d[f]))\n'
    CALLER_ORIG = '                d[f] = re.sub(r"\\D", "", _s(d[f]))\n'
    chk(APP_SRC.count(CALLER_CUR) == 1,
        "호출부(api_partner_update)의 정규화 줄이 소스에 유일하다", APP_SRC.count(CALLER_CUR))

    def _ast_fn_src(src, fn_name):
        """함수의 정확한 경계(decorator 제외, def~마지막 줄)를 ast로 뽑는다(round499 정착 기법)."""
        tree = ast.parse(src)
        lines = src.splitlines(keepends=True)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
                return "".join(lines[node.lineno - 1:node.end_lineno])
        raise AssertionError(f"함수 {fn_name} 을 못 찾음")

    REVERTED_VALID_BIZ_NO = _ast_fn_src(APP_SRC, "valid_biz_no").replace(CUR, ORIG)
    REVERTED_PARTNER_UPDATE = _ast_fn_src(APP_SRC, "api_partner_update").replace(CALLER_CUR, CALLER_ORIG)
    assert ORIG in REVERTED_VALID_BIZ_NO and CUR not in REVERTED_VALID_BIZ_NO, \
        "valid_biz_no 되돌림 치환이 실제로 안 먹었다"
    assert CALLER_ORIG in REVERTED_PARTNER_UPDATE and CALLER_CUR not in REVERTED_PARTNER_UPDATE, \
        "api_partner_update 되돌림 치환이 실제로 안 먹었다"

    #  ⚠⚠ [round619 gotcha] api_partner_update가 valid_biz_no를 맨이름으로 부르므로,
    #    되돌린 valid_biz_no를 **같은** 사본 네임스페이스에 먼저 exec해 둬야
    #    되돌린 api_partner_update가 그 맨이름을 resolve할 때 진짜 모듈이 아니라
    #    이 사본의 되돌린 버전을 찾는다 — 실제 A.valid_biz_no는 절대 안 건드린다.
    _ns = dict(vars(A))
    exec(compile(REVERTED_VALID_BIZ_NO, "<round497_reverted_valid_biz_no>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    exec(compile(REVERTED_PARTNER_UPDATE, "<round497_reverted_partner_update>", "exec"), _ns)  # noqa: S102
    old_fn = A.require_admin(_ns["api_partner_update"])

    _orig_view = A.app.view_functions["api_partner_update"]
    A.app.view_functions["api_partner_update"] = old_fn
    try:
        out2 = _run_patch()
    finally:
        A.app.view_functions["api_partner_update"] = _orig_view

    chk(out2["status"] == 200, "옛 코드(되돌림): 전각숫자 사업자번호가 그냥 통과된다", out2)
    chk(out2["p2_status"] == "활성",
        "★★★★★ 옛 코드(되돌림): 업체가 실제로 활성화된다", out2)
    chk(out2["p2_biz_no"] == "１２３４５６７８９１",
        "★★★★★ 옛 코드(되돌림): 전각 문자열이 그대로 저장된다(ASCII로 정규화 안 됨)",
        out2)
    chk(out2["active_count"] == 2,
        "★★★★★ 옛 코드(되돌림): 같은 실제 사업자번호로 활성 업체가 2곳— "
        "이 테스트가 진짜 결함(중복확인 우회)을 잡아낼 능력이 있음을 증명", out2)

    print("\n[4] 원복 확인 — 되돌리기 이후 다시 거부되는가(바꿔치기가 안 샜다)")
    chk(A.app.view_functions["api_partner_update"] is _orig_view,
        "  view_functions가 원래 함수객체로 복원됐다")
    out3 = _run_patch()
    chk(out3["status"] == 400,
        "★★★★ 원복 후에는 다시 전각숫자 사업자번호가 400으로 거부된다(바꿔치기가 안 샜다)", out3)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] 실행/되돌림-증명", f"{type(e).__name__}: {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(view_functions 딕셔너리 항목 임시치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

# ══════════════════════════════════════════════════════════════
print("\n[5] valid_biz_no() 단위 확인 — 경계값(회귀 없음 확인)")
# ──────────────────────────────────────────────────────────────
#  A.valid_biz_no는 이 과정 내내 한 번도 안 바뀌었다(되돌림은 위에서
#  사본 네임스페이스에만 exec됐다) — 그냥 직접 호출한다. 더 이상 별도
#  워커 서브프로세스(test_scan_round497_unit_worker.py, 더 이상 생성 안 함)가 필요 없다.
try:
    u = {
        "ascii_plain": A.valid_biz_no("1234567891"),
        "ascii_hyphen": A.valid_biz_no("123-45-67891"),
        "fullwidth": A.valid_biz_no("１２３４５６７８９１"),
        "partial_fullwidth": A.valid_biz_no("12345678９" + "1"),
        "known_invalid_ascii": A.valid_biz_no("1234567890"),
        "empty": A.valid_biz_no(""),
        "none": A.valid_biz_no(None),
    }
    chk(u["ascii_plain"] is True, "회귀없음: 순수 ASCII 유효값은 여전히 통과한다", u)
    chk(u["ascii_hyphen"] is True, "회귀없음: 하이픈 포함 ASCII 유효값도 여전히 통과한다(하이픈은 [^0-9]로도 지워짐)", u)
    chk(u["fullwidth"] is False, "★★★★★ 전각숫자(체크섬은 유효)는 이제 거부된다", u)
    chk(u["partial_fullwidth"] is False,
        "★★★★ 마지막 한 글자만 전각으로 섞은 값도 거부된다(부분 우회 시도도 막힘)", u)
    chk(u["known_invalid_ascii"] is False, "회귀없음: 체크섬이 원래 틀린 ASCII 값은 여전히 거부된다", u)
    chk(u["empty"] is False and u["none"] is False, "회귀없음: 빈 문자열·None은 여전히 거부된다", u)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[5] valid_biz_no() 단위 확인", f"{type(e).__name__}: {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
