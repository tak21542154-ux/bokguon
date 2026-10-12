# -*- coding: utf-8 -*-
"""스캔 535라운드 회귀 — 대시보드 "최근 활동" 위젯이 관리자 계정 관련 감사로그를
   마스킹 없이 노출하던 결함.

   조사 배경 — 지시받은 신선한 각도 예시 (6)"관리자 콘솔에서 다른 관리자의 활동을
   볼 때(activity_log 조회), 민감한 필드가 로그 문자열에 실수로 포함돼 있는지"를
   따라가다, activity_log 를 읽는 모든 지점을 app.py 전수(grep "FROM activity_log")
   했다. (참고: 임시비밀번호 발급 라우트 6곳은 이미 전수 확인 — 비밀번호 값 자체는
   DB.log detail 에 애초에 안 실린다. 이번 결함은 그쪽이 아니다.)

   결정적 증거 — 라운드326 은 "관리자 계정 생성·등급변경·이름변경·비밀번호재발급·
   삭제" 5개 행위(_ADMIN_ACCOUNT_ACTIONS)의 detail 을 최고관리자 미만에게는
   가리는 헬퍼 _mask_admin_activity() 를 만들어 형제 둘 — api_activity(화면,
   17330행 부근)·api_activity_export(엑셀, 17251행) — 에 심었다. 이 둘은 감사
   로그 화면 자체가 등급 무관 @require_admin 이라, 하위관리자가 /api/admins
   (관리자 목록, 최고관리자 전용)에서는 403 을 받으면서도 감사 로그로 같은
   정보를 우회해 볼 수 있었던 것을 막는 조치였다.

   그런데 activity_log 를 읽는 **세 번째** 지점이 있었다 — api_dashboard()
   (/api/dashboard, 역시 @require_admin·등급 무관) 의 "최근 활동" 위젯(최신
   8건, 7124행 부근)이다. static/admin.js:759 가
   `${a.action}${a.detail?' — '+esc(a.detail):''}` 로 action·detail 을 가감
   없이 그린다. 로그인하면 가장 먼저 보는 대시보드 첫 화면에서, 하위관리자가
   /api/activity 에서는 가려지는 "대상 관리자의 아이디·이름·등급" 을 마스킹
   없이 그대로 볼 수 있었다 — 라운드326 이 막으려던 것과 똑같은 우회로가
   세 번째 문으로 남아 있었던 셈이다.

   고침 — app.py api_dashboard() 안의 `recent = rows(conn.execute(...))` 를
   형제 둘과 완전히 같은 모양으로 `recent = _mask_admin_activity(rows(conn.execute(...)))`
   로 감쌌다(7130행 부근). 새 헬퍼·새 정책 없음 — 라운드326 이 이미 만든
   헬퍼를 세 번째 호출부에 그대로 이식했을 뿐이다.

   회귀 검사 — [1] 소스: api_dashboard 가 _mask_admin_activity(를 부르고
   [라운드535] 표식이 있다. [2] 무회귀: 형제 둘(api_activity·api_activity_export)
   은 이번 라운드가 손대지 않았다(여전히 _mask_admin_activity 호출). [3] app.py
   구문 전체 유효. [4]~[7] 실행(진짜 Flask app + test_client + 격리 DB): 방금
   심은 래핑만 도려낸 "라운드535 이전" 소스를 만들어 view_functions 에 임시로
   꽂아 보면 — 하위관리자 세션으로 /api/dashboard 를 불렀을 때 "관리자 계정
   생성" 행의 detail 이 원문 그대로 샌다(실제로 재현됨). 되돌린 뷰를 원상복구한
   뒤 지금(고친) 버전으로 같은 호출을 하면 그 detail 이 가려지고, 최고관리자
   세션으로 부르면 지금도 원문 그대로 보인다(과잉마스킹 아님 확인).

   ⚠ app.py 자신에 정의된 함수(api_dashboard) 본문을 고쳤다(다른 모듈을 통해서가
     아니라) — 이미 떠 있는 프로세스가 있다면 재시작해야 이 수정이 실제로 반영된다.

      python test_scan_round535_fixes.py
"""
import ast
import io
import os
import shutil
import sys
import tempfile

#  ⚠ 윈도 기본 콘솔은 cp949 라 em dash(—) 같은 문자를 print 하면
#    UnicodeEncodeError 로 죽는다 — 형제 테스트(round529·533·534 등)와 같은 방어.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 74)
print("  스캔 535라운드 회귀 — 대시보드 최근활동 위젯 관리자계정 마스킹 누락")
print("=" * 74)


def _ast_fn_src(src, fn_name):
    """ast 로 함수의 **정확한** 경계(decorator 제외, def~마지막 줄)를 뽑는다.
    문자열 검색과 달리 뒤에 딸린 형제 라우트의 decorator 줄이 섞여 들어오지
    않는다 — 되돌린 버전을 실제 compile/exec 하므로 경계가 어긋나면 죽는다."""
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            return "".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError(f"함수 {fn_name} 을 못 찾음")


DASH_SRC = _ast_fn_src(APP_SRC, "api_dashboard")
ACT_SRC = _ast_fn_src(APP_SRC, "api_activity")
ACT_EXPORT_SRC = _ast_fn_src(APP_SRC, "api_activity_export")

print("\n[1] 소스 — api_dashboard 가 이제 recent 조회를 _mask_admin_activity 로 감싼다")
chk("[라운드535]" in DASH_SRC, "라운드535 표식이 있다")
chk("recent = _mask_admin_activity(rows(conn.execute(" in DASH_SRC,
    "★★★★★ api_dashboard 가 recent 조회를 _mask_admin_activity() 로 감싼다")

print("\n[2] 무회귀 — 형제 둘(api_activity·api_activity_export)은 이번 라운드가 손대지 않았다")
chk("_mask_admin_activity(rows(conn.execute(" in ACT_SRC,
    "api_activity 는 여전히 _mask_admin_activity 를 부른다")
chk("_mask_admin_activity(rows(conn.execute(" in ACT_EXPORT_SRC,
    "api_activity_export 는 여전히 _mask_admin_activity 를 부른다")

print("\n[3] app.py 구문 전체가 여전히 유효하다")
try:
    ast.parse(APP_SRC)
    chk(True, "ast.parse(app.py) 성공")
except SyntaxError as e:
    chk(False, "ast.parse(app.py) 성공", f"{e.lineno}행: {e.msg}")


AFTER_SNIPPET = ('    recent = _mask_admin_activity(rows(conn.execute(\n'
                  '        "SELECT actor, action, detail, created_at FROM activity_log '
                  'ORDER BY id DESC LIMIT 8")))')
BEFORE_SNIPPET = ('    recent = rows(conn.execute(\n'
                   '        "SELECT actor, action, detail, created_at FROM activity_log '
                   'ORDER BY id DESC LIMIT 8"))')


def _strip_round535_wrap(fn_src):
    """이번 라운드가 심은 주석+마스킹 래퍼만 벗겨 '라운드535 이전' 소스를
    메모리에서 재구성한다 — 실제 app.py 파일은 절대 건드리지 않는다(monkeypatch 전용)."""
    marker = "[라운드535]"
    i = fn_src.index(marker)
    line_start = fn_src.rfind("\n", 0, i) + 1
    assert AFTER_SNIPPET in fn_src, "AFTER_SNIPPET 이 실제 소스와 안 맞음"
    j = fn_src.index(AFTER_SNIPPET)
    end = j + len(AFTER_SNIPPET)
    return fn_src[:line_start] + BEFORE_SNIPPET + fn_src[end:]


REVERTED_DASH_SRC = _strip_round535_wrap(DASH_SRC)
chk("_mask_admin_activity" not in REVERTED_DASH_SRC,
    "되돌린 소스에는 _mask_admin_activity 호출이 정말 없다(제거 확인)")
chk("recent = rows(conn.execute(" in REVERTED_DASH_SRC,
    "되돌린 뒤에도 recent 조회 자체는 그대로 남아 있다(과잉제거 아님)")
chk('"recent": recent,' in REVERTED_DASH_SRC,
    "되돌린 뒤에도 응답 조립(jsonify recent) 은 그대로 남아 있다")
try:
    ast.parse(REVERTED_DASH_SRC)
    chk(True, "되돌린 api_dashboard 소스가 단독으로도 구문상 유효하다")
except SyntaxError as e:
    chk(False, "되돌린 api_dashboard 소스가 단독으로도 구문상 유효하다", f"{e}")

# ==================================================================
print("\n[4] 실행 준비 — 실제 app.py(전체 임포트) + 격리 DB + 관리자 세션 2종")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round535_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"

try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role,created_at) "
                 "VALUES('r535_low','x','R535하위','하위관리자',?)", (DB.now(),))
    conn.execute("INSERT INTO admins(username,password_hash,name,role,created_at) "
                 "VALUES('r535_top','x','R535최고','최고관리자',?)", (DB.now(),))
    #  라운드326 이 가리는 5개 행위 중 하나 — 대상 관리자의 아이디·등급·이름이 detail 에 실린다.
    SECRET_DETAIL = "r535_victim (중간관리자) 김비밀"
    DB.log(conn, "r535_top", "관리자 계정 생성", SECRET_DETAIL)
    conn.commit()
    conn.close()

    client = A.app.test_client()

    def _login_as(username):
        with client.session_transaction() as sess:
            sess.clear()
            sess["admin"] = username
            sess["admin_name"] = username

    def _recent_detail_for(resp_json, action):
        for r in resp_json.get("recent", []):
            if r.get("action") == action:
                return r.get("detail")
        return "<이 행위가 최근활동 8건 안에 없음>"

    def _rebuild_reverted_view(fn_name, reverted_src):
        """되돌린 함수 소스를 실제 app 모듈 전역(DB·session·_mask_admin_activity 등)에
        exec 해 raw 함수를 얻고, 실제와 같은 require_admin 으로 감싼다
        (데코레이터까지 동일해야 '본문만 되돌렸을 때'를 정확히 재현한다)."""
        ns = {}
        exec(compile(reverted_src, f"<round535-reverted:{fn_name}>", "exec"), A.__dict__, ns)
        return A.require_admin(ns[fn_name])

    print("\n[5] 되돌림-증명 — 마스킹 래퍼가 없던 시절엔 하위관리자에게도 실제로 샌다")
    _orig_dash = A.app.view_functions["api_dashboard"]
    try:
        A.app.view_functions["api_dashboard"] = \
            _rebuild_reverted_view("api_dashboard", REVERTED_DASH_SRC)

        #  세션의 admin_role 은 require_admin -> _account_alive() 가 매 요청 admins.role 로
        #  덮어쓴다(강등 즉시 반영 장치, 546행 부근) — DB 값만 정확하면 세션엔 안 넣어도 된다.
        _login_as("r535_low")
        r = client.get("/api/dashboard")
        chk(r.status_code == 200, "되돌린 버전도 대시보드 자체는 정상 응답한다(200)",
            r.status_code)
        leaked = _recent_detail_for(r.get_json(), "관리자 계정 생성")
        chk(leaked == SECRET_DETAIL,
            "★★★★★★ 되돌리면 실제로 재현된다 — 하위관리자가 대상 관리자 아이디를 그대로 본다",
            f"detail={leaked!r}")
    finally:
        A.app.view_functions["api_dashboard"] = _orig_dash

    print("\n[6] 실행 — 원상복구한 지금(고친) 버전은 하위관리자에게 마스킹된 문구만 보여준다")
    _login_as("r535_low")
    r2 = client.get("/api/dashboard")
    chk(r2.status_code == 200, "고친 버전도 대시보드는 정상 응답한다(200)", r2.status_code)
    masked = _recent_detail_for(r2.get_json(), "관리자 계정 생성")
    chk(masked == "(최고관리자만 볼 수 있습니다)",
        "★★★★★★ 하위관리자에게는 detail 이 가려진다(형제 api_activity 와 동일한 문구)",
        f"detail={masked!r}")
    chk(masked != SECRET_DETAIL, "가려진 문구가 원문과 다르다(진짜 마스킹, 원문 잔존 아님)")

    print("\n[7] 과잉마스킹 방지 — 최고관리자에게는 지금도 원문이 그대로 보인다")
    _login_as("r535_top")
    r3 = client.get("/api/dashboard")
    chk(r3.status_code == 200, "최고관리자 세션도 대시보드 정상 응답(200)", r3.status_code)
    top_detail = _recent_detail_for(r3.get_json(), "관리자 계정 생성")
    chk(top_detail == SECRET_DETAIL,
        "최고관리자는 형제(api_activity)와 동일하게 원문을 그대로 본다(과잉마스킹 아님)",
        f"detail={top_detail!r}")

except Exception as e:
    import traceback
    traceback.print_exc()
    chk(False, f"실행 단계에서 예외 발생: {e!r}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "=" * 74)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 74)
sys.exit(1 if FAIL else 0)
