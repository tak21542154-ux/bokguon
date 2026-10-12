# -*- coding: utf-8 -*-
"""스캔 496라운드 회귀 — 사건 수동 수정 감사로그(activity_log)에
피해자 "이름"만 원문 그대로 남던 결함(전화번호는 라운드249가 이미 마스킹).

activity_log 는 cmd_prune_personal() 파기 대상이 아니라서(라운드495가
확정한 6개 파기 버킷 어디에도 activity_log 는 없다), 사건 쪽
cases.victim_name 이 하자담보 만료 후 지워져도 과거 수정 이력에 남은
원문 이름은 영구 보존된다. 처리방침 제3조는 "피해자 성명·연락처"를
같은 줄로 묶어 같은 기준(하자담보 만료 후 파기)을 약속하므로, 형제
필드(전화번호)와 똑같이 이름도 감사로그에는 마스킹만 남겨야 한다.

⚠ 이 라운드는 activity_log "전체"의 파기 정책(라운드434가 이미
  사용자결정 대기로 등록한 별개 축 — 5년 보관 의무 있는 협력업체
  감사증적과 뒤섞여 일괄삭제 불가)을 건드리지 않는다. 여기 고침은
  "앞으로 새로 남는 로그에 원문을 안 남긴다"는 좁은 범위이고, 이미
  쌓인 과거 로그의 소급 마스킹이나 activity_log 행 자체의 나이 기반
  파기는 라운드434의 정책결정 사안 그대로 남아 있다.
"""
import ast
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(c, n, d=""):
    (PASS if c else FAIL).append((n, d))
    print(("  [OK]   " if c else "  [FAIL] ") + n + ("" if c else f"   {d}"))


print("=" * 72)
print("  스캔 496라운드 회귀 — 사건수정 감사로그의 피해자 이름 원문 노출")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
CU_PATH = os.path.join(HERE, "crypto_util.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()
CU_SRC = io.open(CU_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 두 파일의 독립 블록을 각각 추출(서로 안 겹침)")
# ──────────────────────────────────────────────────────────────
#  블록A: crypto_util.py의 mask_name() 신설(순수 삽입 — 통짜 제거로 되돌림)
BLOCK_A = ('\n\ndef mask_name(name: str) -> str:\n'
           '    """화면 표시용 마스킹 — 첫 글자만 노출(라운드496)."""\n'
           '    if not name:\n'
           '        return ""\n'
           '    return name[0] + "*" * (len(name) - 1) if len(name) > 1 else "*"\n\n')

#  블록B: app.py의 이름 마스킹 분기(기존 줄 수정 — 원본 문자열로 치환해 되돌림)
CUR_B = ('''            sets.append(f"{f}=?"); vals.append(nv)
            #  ⚠⚠ [라운드496] 위 라운드249 주석은 전화번호만 마스킹하는 이유
            #    (감사로그 유출이 그 자체로 연락처 유출 경로가 되지 않도록)를
            #    남겼는데, 이름은 원문 그대로 남아 있었다 — activity_log 는
            #    cmd_prune_personal() 파기 대상이 아니라서 사건 쪽 victim_name
            #    이 하자담보 만료 후 지워져도 여기 남긴 원문은 영구 보존된다.
            #    처리방침 제3조가 "피해자 성명·연락처"를 같은 줄로 묶어 같은
            #    기준(하자담보 만료 후 파기)을 약속하므로 이름도 형제와 같은
            #    원칙으로 마스킹한다.
            if f == "victim_phone":
                notes.append(f"피해자 연락처 {POPBILL.mask_phone(c[f]) if c[f] else '(없음)'}"
                             f"→{POPBILL.mask_phone(nv) if nv else '(없음)'}")
            else:
                notes.append(f"피해자 이름 {CRYPTO.mask_name(c[f]) if c[f] else '(없음)'}"
                             f"→{CRYPTO.mask_name(nv) if nv else '(없음)'}")
''')
ORIG_B = ('''            sets.append(f"{f}=?"); vals.append(nv)
            if f == "victim_phone":
                notes.append(f"피해자 연락처 {POPBILL.mask_phone(c[f]) if c[f] else '(없음)'}"
                             f"→{POPBILL.mask_phone(nv) if nv else '(없음)'}")
            else:
                notes.append(f"피해자 이름 '{c[f] or ''}'→'{nv}'")
''')

chk(CU_SRC.count(BLOCK_A) == 1, "블록A(crypto_util.mask_name)가 소스에 유일하다", CU_SRC.count(BLOCK_A))
chk(APP_SRC.count(CUR_B) == 1, "블록B(app.py 이름 마스킹 분기)가 소스에 유일하다", APP_SRC.count(CUR_B))
chk("mask_name" not in ORIG_B, "원본 대조 문자열(app.py)에는 mask_name이 없다(대조군)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 서브프로세스 실행 — /api/cases/<id> PATCH 직접 호출")
# ──────────────────────────────────────────────────────────────
WORKER = os.path.join(HERE, "test_scan_round496_worker.py")


def run():
    r = subprocess.run([sys.executable, "-u", WORKER], capture_output=True,
                        text=True, encoding="utf-8", timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"워커 실행 실패(rc={r.returncode}): {r.stdout}\n{r.stderr}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def _ast_fn_src(src, fn_name):
    """ast로 함수의 정확한 경계(decorator 제외, def~마지막 줄)를 뽑는다."""
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            return "".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError(f"함수 {fn_name} 을 못 찾음")


try:
    out = run()
    chk(out["status"] == 200, "PATCH /api/cases/<id>이 정상 처리(200)된다", out)
    chk("홍길동" not in (out["log_detail"] or "") and "홍길순" not in (out["log_detail"] or ""),
        "★★★★★ 새 코드: activity_log에 피해자 이름 원문이 전혀 남지 않는다", out)
    chk("홍**" in (out["log_detail"] or ""),
        "새 코드: activity_log에 마스킹된 이름(홍**)만 남는다", out)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 되돌림-증명 — app.py는 api_case_edit() 뷰만 메모리에서 교체")
    print("    (파일 미수정), crypto_util.py는 아예 안 건드린다")
    print("    — 되돌린 뷰가 mask_name()을 안 부르니 그 존재는 원래도 무관하다")
    # ──────────────────────────────────────────────────────────
    VIEW_SRC = _ast_fn_src(APP_SRC, "api_case_edit")
    chk(CUR_B in VIEW_SRC, "블록B가 api_case_edit() 함수 본문 안에 있다(경계 확인)")
    REVERTED_VIEW_SRC = VIEW_SRC.replace(CUR_B, ORIG_B)
    assert REVERTED_VIEW_SRC != VIEW_SRC, "되돌림 치환이 실제로 안 먹었다"

    _tmpdir2 = tempfile.mkdtemp(prefix="r496_revert_")
    os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir2, "v.db")
    os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir2, "u")
    os.environ["BOKGUON_ENV"] = "dev"
    os.environ["BOKGUON_SEED_DEMO"] = "0"
    try:
        import db as DB2
        DB2.init_db()
        conn0 = DB2.get_db()
        conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                      "VALUES('a1','x','n1','최고관리자')")
        cid2 = conn0.execute(
            "INSERT INTO cases(case_no,status,victim_name,is_demo) "
            "VALUES('R496-2','접수','홍길동',0)").lastrowid
        conn0.commit(); conn0.close()

        import app as A
        client2 = A.app.test_client()
        with client2.session_transaction() as s:
            s["admin"] = "a1"; s["admin_role"] = "최고관리자"; s["_csrf"] = "c1"

        #  되돌린 뷰 소스를 app 모듈 전역(DB·POPBILL·actor 등)의 독립 사본에
        #  exec해 raw 함수를 얻고, 실제와 같은 데코레이터로 감싼다.
        _ns = dict(vars(A))
        exec(compile(REVERTED_VIEW_SRC, "<round496-reverted:api_case_edit>", "exec"), _ns)
        _orig_view = A.app.view_functions["api_case_edit"]
        A.app.view_functions["api_case_edit"] = A.require_role("중간관리자")(_ns["api_case_edit"])
        try:
            r2 = client2.patch(f"/api/cases/{cid2}", json={"victim_name": "홍길순"},
                                headers={"X-CSRF-Token": "c1"})
            conn1 = A.DB.get_db()
            log_row2 = conn1.execute(
                "SELECT detail FROM activity_log WHERE action='사건 수동 수정' "
                "ORDER BY id DESC LIMIT 1").fetchone()
            conn1.close()
            detail2 = dict(log_row2)["detail"] if log_row2 else None
            chk(r2.status_code == 200, "옛 코드(되돌림)도 정상 처리(200)된다", r2.status_code)
            chk("홍길동" in (detail2 or "") and "홍길순" in (detail2 or ""),
                "★★★★★ 옛 코드(되돌림): activity_log에 피해자 이름 원문(홍길동→홍길순)이 "
                "그대로 노출된 채 남는다 — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
                detail2)
        finally:
            A.app.view_functions["api_case_edit"] = _orig_view
    finally:
        os.environ.pop("BOKGUON_DB_PATH", None)
        os.environ.pop("BOKGUON_UPLOAD_DIR", None)
        os.environ.pop("BOKGUON_ENV", None)
        os.environ.pop("BOKGUON_SEED_DEMO", None)
        shutil.rmtree(_tmpdir2, ignore_errors=True)

    chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
        "★★★★★ app.py는 이 되돌림-증명 내내 디스크에서 전혀 건드려지지 않았다")
    chk(io.open(CU_PATH, encoding="utf-8").read() == CU_SRC,
        "★★★★★ crypto_util.py도 전혀 건드려지지 않았다"
        "(되돌린 뷰가 mask_name을 안 부르므로 애초에 무관)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] 실행/되돌림-증명", f"{type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════
print("\n[4] mask_name() 단위 확인 — 경계값")
# ──────────────────────────────────────────────────────────────
sys.path.insert(0, HERE)
import crypto_util as _CU_check
chk(_CU_check.mask_name("홍길동") == "홍**", "3글자 이름 → 첫 글자+별표 2개")
chk(_CU_check.mask_name("이봄") == "이*", "2글자 이름 → 첫 글자+별표 1개")
chk(_CU_check.mask_name("A") == "*", "1글자 이름 → 완전 마스킹(형제 mask_account의 짧은값 전량마스킹과 같은 원칙)")
chk(_CU_check.mask_name("") == "", "빈 문자열 → 빈 문자열(형제 mask_account/mask_phone과 동일)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
