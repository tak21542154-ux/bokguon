# -*- coding: utf-8 -*-
"""스캔 534라운드 회귀 — 보험사 포털 "자기조회" 내보내기 2곳(절감 리포트·
   월 정산 명세서)이 파일은 내주면서 감사 로그를 안 남기던 결함.

   조사 배경 — 지시받은 신선한 각도 예시 (2)"관리자 콘솔의 CSV/엑셀 내보내기가
   전부 감사 로그를 남기는가"를 실제로 app.py 전수(ast로 함수 경계 추출) 검사했다.
   Workbook()을 만드는 내보내기 라우트 8개(api_ops_kpi_export·api_export_xlsx·
   api_settlements_export·api_insurer_statement_export·api_activity_export·
   api_partner_onboarding_export·api_insurer_report_export·
   api_insurer_statement_self_export) 중 마지막 두 개만 DB.log 호출이 없었다.

   결정적 증거 — api_insurer_statement_export(어드민, 13822행)와
   api_insurer_statement_self_export(보험사 포털, 14059행 부근)는 **같은 헬퍼
   _statement_xlsx() 를 불러 바이트 단위로 동일한 파일**을 만든다. 그런데
   어드민이 대신 뽑으면 "월 정산 명세서 내보내기"가 activity_log 에 남고,
   보험사 본인이 자기 명세서를 뽑으면 아무 흔적이 없었다 — 오히려 더 자주
   쓰일 경로(보험사 본인 다운로드)가 감사 사각지대였다. api_insurer_report_export
   (절감 리포트, 이 함수 자신의 docstring이 "분기 보고서·결재 첨부용"이라고
   스스로 밝힌다)도 형제 api_ops_kpi_export(어드민 운영KPI, 같은 계산 코어
   _compute_ops_kpi 공유)와 달리 DB.log 가 없었다. test_feature_audit_export.py
   가 이미 "내보낸 사실도 감사 로그에 남긴다 — 개인정보 취급 이력"이라고 명시한
   원칙이 보험사 포털 자기조회 두 곳에서만 새지 않고 있었다.

   고침 — app.py 두 함수 끝(각각 buf/blob 완성 직후, resp 조립 직전)에 형제와
   똑같은 모양의 DB.log(_c, portal_actor(), "...", detail); _c.commit(); _c.close()
   블록을 이식했다. actor() 대신 portal_actor()를 쓰는 것만 다르다(app.py
   1448행 자신의 설명 + 라운드141 관례 — 조직명만으로는 하위계정 중 누가
   내려받았는지 특정 못 한다). 새 헬퍼·새 상수 없음.
     · api_insurer_report_export       (app.py, "엑셀 내보내기"        — 운영KPI 형제와 동일 라벨)
     · api_insurer_statement_self_export (app.py, "월 정산 명세서 내보내기" — 어드민 형제와 동일 라벨)

   회귀 검사 — [1] 소스: 두 함수 다 DB.log(portal_actor()..)·commit 을 갖고,
   어드민 형제 둘(actor() 그대로)은 이번 라운드가 안 건드렸다. [2]~[4] 실행
   (진짜 Flask app + test_client + 격리 DB): 되돌림-증명으로 방금 심은 블록만
   ast 로 뽑은 함수 소스에서 정확히 도려낸 "라운드534 이전" 버전을 만들어
   app.view_functions 에 임시로 꽂아 보면 — 파일은 여전히 200으로 잘 받아지는데
   activity_log 는 0건 늘어난다(실제로 재현됨). 되돌린 뷰를 원상복구한 뒤
   지금의(고친) 버전으로 같은 호출을 하면 정확히 2건이 늘고, actor 열이
   session["insurer_name"] 그대로가 아니라 portal_actor() 형식
   ("조직명(로그인아이디)")으로 남는 것까지 확인한다.

   ⚠ app.py 자신에 정의된 함수 본문을 고쳤다(다른 모듈을 통해서가 아니라) —
     이미 떠 있는 프로세스가 있다면 재시작해야 이 수정이 실제로 반영된다.

      python test_scan_round534_fixes.py
"""
import ast
import io
import os
import shutil
import sys
import tempfile

#  ⚠ 윈도 기본 콘솔은 cp949 라 em dash(—) 같은 문자를 print 하면
#    UnicodeEncodeError 로 죽는다 — 형제 테스트(round529·533 등)와 같은 방어.
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
print("  스캔 534라운드 회귀 — 보험사 포털 자기내보내기 감사로그 누락")
print("=" * 74)


def _ast_fn_src(src, fn_name):
    """ast 로 함수의 **정확한** 경계(decorator 제외, def~마지막 줄)를 뽑는다.
    문자열 검색(다음 '\\ndef ' 까지)과 달리 뒤에 딸린 형제 라우트의 decorator
    줄이 섞여 들어오지 않는다 — 이 라운드는 되돌린 버전을 실제로 compile/exec
    하므로(정적 grep이 아니라) 경계가 조금이라도 어긋나면 SyntaxError 로 죽는다."""
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            return "".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError(f"함수 {fn_name} 을 못 찾음")


RPT_SRC = _ast_fn_src(APP_SRC, "api_insurer_report_export")
STMT_SRC = _ast_fn_src(APP_SRC, "api_insurer_statement_self_export")
ADMIN_STMT_SRC = _ast_fn_src(APP_SRC, "api_insurer_statement_export")
ADMIN_KPI_SRC = _ast_fn_src(APP_SRC, "api_ops_kpi_export")

print("\n[1] 소스 — 두 자리 다 이제 DB.log(portal_actor(), ...) 를 남긴다")
chk("DB.log(_c, portal_actor()," in RPT_SRC,
    "★★★★★ api_insurer_report_export 가 DB.log(portal_actor(), ...) 를 부른다")
chk("_c.commit(); _c.close()" in RPT_SRC, "★ 절감 리포트 쪽 로그가 커밋+닫힌다")
chk("DB.log(_c, portal_actor()," in STMT_SRC,
    "★★★★★ api_insurer_statement_self_export 가 DB.log(portal_actor(), ...) 를 부른다")
chk("_c.commit(); _c.close()" in STMT_SRC, "★ 정산 명세서 쪽 로그가 커밋+닫힌다")
chk('"엑셀 내보내기"' in RPT_SRC, "절감 리포트 action 라벨이 형제(운영KPI)와 같은 이름이다")
chk('"월 정산 명세서 내보내기"' in STMT_SRC, "정산 명세서 action 라벨이 형제(어드민)와 같은 이름이다")

print("\n[2] 무회귀 — 어드민 쪽 형제 둘은 이번 라운드가 손대지 않았다(여전히 actor())")
chk('DB.log(_c, actor(), "월 정산 명세서 내보내기"' in ADMIN_STMT_SRC,
    "api_insurer_statement_export(어드민) 그대로")
chk('DB.log(_c, actor(), "엑셀 내보내기"' in ADMIN_KPI_SRC,
    "api_ops_kpi_export(어드민) 그대로")

print("\n[3] app.py 구문 전체가 여전히 유효하다")
try:
    ast.parse(APP_SRC)
    chk(True, "ast.parse(app.py) 성공")
except SyntaxError as e:
    chk(False, "ast.parse(app.py) 성공", f"{e.lineno}행: {e.msg}")


def _strip_round534_block(fn_src):
    """이번 라운드가 심은 블록만 도려내 '라운드534 이전' 소스를 메모리에서
    재구성한다 — 실제 app.py 파일은 절대 건드리지 않는다(monkeypatch 전용)."""
    i = fn_src.index("[라운드534]")
    line_start = fn_src.rfind("\n", 0, i) + 1
    tail_marker = "_c.commit(); _c.close()\n"
    j = fn_src.index(tail_marker, i) + len(tail_marker)
    return fn_src[:line_start] + fn_src[j:]


REVERTED_RPT_SRC = _strip_round534_block(RPT_SRC)
REVERTED_STMT_SRC = _strip_round534_block(STMT_SRC)
chk("DB.log(" not in REVERTED_RPT_SRC,
    "되돌린 절감 리포트 소스에는 DB.log 가 정말 없다(제거 확인)")
chk("DB.log(" not in REVERTED_STMT_SRC,
    "되돌린 정산 명세서 소스에는 DB.log 가 정말 없다(제거 확인)")
chk("resp = make_response(buf.read())" in REVERTED_RPT_SRC,
    "되돌린 뒤에도 정상 응답 조립 코드는 그대로 남아 있다(과잉제거 아님)")
chk("resp = make_response(blob)" in REVERTED_STMT_SRC,
    "되돌린 뒤에도 정상 응답 조립 코드는 그대로 남아 있다(과잉제거 아님)")
#  되돌린 소스가 그 자체로 유효한 파이썬 함수인지(뒤에 미리 확인 — exec 전에 조기 발견)
try:
    ast.parse(REVERTED_RPT_SRC)
    ast.parse(REVERTED_STMT_SRC)
    chk(True, "되돌린 두 함수 소스가 단독으로도 구문상 유효하다")
except SyntaxError as e:
    chk(False, "되돌린 두 함수 소스가 단독으로도 구문상 유효하다", f"{e}")

# ==================================================================
print("\n[4] 실행 준비 — 실제 app.py(전체 임포트) + 격리 DB + 보험사 세션")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round534_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"

try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,org_type,status,fee_rate_bp) "
        "VALUES('R534보험','손해보험','활성',900)").lastrowid
    conn.commit()
    conn.close()

    client = A.app.test_client()
    with client.session_transaction() as sess:
        sess["insurer_id"] = iid
        sess["insurer_name"] = "R534보험"
        sess["insurer_login"] = "r534_login"

    def _log_count():
        c = DB.get_db()
        try:
            return c.execute(
                "SELECT COUNT(*) n FROM activity_log WHERE action LIKE '%내보내기%'"
            ).fetchone()["n"]
        finally:
            c.close()

    def _rebuild_reverted_view(fn_name, reverted_src):
        """되돌린 함수 소스를 실제 app 모듈 전역(DB·session·portal_actor 등)에
        exec 해 raw 함수를 얻고, 실제와 같은 require_insurer 로 감싼다
        (데코레이터까지 동일해야 '본문만 되돌렸을 때'를 정확히 재현한다)."""
        ns = {}
        exec(compile(reverted_src, f"<round534-reverted:{fn_name}>", "exec"), A.__dict__, ns)
        return A.require_insurer(ns[fn_name])

    print("\n[5] 되돌림-증명 — 이번 라운드가 지운 코드가 없던 시절엔 실제로 안 남았다")
    _orig_rpt = A.app.view_functions["api_insurer_report_export"]
    _orig_stmt = A.app.view_functions["api_insurer_statement_self_export"]
    try:
        A.app.view_functions["api_insurer_report_export"] = \
            _rebuild_reverted_view("api_insurer_report_export", REVERTED_RPT_SRC)
        A.app.view_functions["api_insurer_statement_self_export"] = \
            _rebuild_reverted_view("api_insurer_statement_self_export", REVERTED_STMT_SRC)

        before = _log_count()
        r1 = client.get("/api/insurer/report/export")
        r2 = client.get("/api/insurer/statement/export")
        after = _log_count()
        chk(r1.status_code == 200 and r2.status_code == 200,
            "되돌린 버전도 파일 자체는 정상 응답한다(200) — 순수 감사로그 결함만 재현",
            f"{r1.status_code}/{r2.status_code}")
        chk(after == before,
            "★★★★★★ 되돌리면 실제로 재현된다 — 파일은 받았는데 감사 로그는 0건 늘어난다",
            f"before={before} after={after}")
    finally:
        A.app.view_functions["api_insurer_report_export"] = _orig_rpt
        A.app.view_functions["api_insurer_statement_self_export"] = _orig_stmt

    print("\n[6] 실행 — 고친 현재 버전은 실제로 감사 로그를 남긴다")
    before2 = _log_count()
    resp_rpt = client.get("/api/insurer/report/export")
    resp_stmt = client.get("/api/insurer/statement/export")
    after2 = _log_count()
    chk(resp_rpt.status_code == 200, "절감 리포트 내보내기 200 OK", resp_rpt.status_code)
    chk(resp_stmt.status_code == 200, "정산 명세서 내보내기 200 OK", resp_stmt.status_code)
    chk(after2 - before2 == 2,
        "★★★★★★ 원상복구한 현재 버전은 두 내보내기 각각 1건씩, 합 2건이 새로 남는다",
        f"before={before2} after={after2}")

    conn2 = DB.get_db()
    try:
        rows = conn2.execute(
            "SELECT actor, action FROM activity_log WHERE action LIKE '%내보내기%' "
            "ORDER BY id DESC LIMIT 2").fetchall()
    finally:
        conn2.close()
    actions = {r["action"] for r in rows}
    actors = {r["actor"] for r in rows}
    chk("월 정산 명세서 내보내기" in actions, "정산 명세서 쪽 activity_log.action 확인")
    chk("엑셀 내보내기" in actions, "절감 리포트 쪽 activity_log.action 확인")
    chk(actors == {"R534보험(r534_login)"},
        "★★★★ actor 가 portal_actor() 형식(조직명(로그인아이디))으로 남는다 "
        "— session['insurer_name'] 원문 그대로가 아니다(라운드141 관례 재확인)",
        str(actors))

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
