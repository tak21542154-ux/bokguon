# -*- coding: utf-8 -*-
"""스캔 499라운드 회귀 — 출동후보 매칭(dispatch.py candidates())과 근처
업체 검색(app.py api_case_nearby())의 공종(category/major) LIKE 비교가
가운뎃점 표기 흔들림('ㆍ' U+318D 아래아·'･' U+FF65 반각 vs 정본
'·' U+00B7)을 정규화하지 않던 결함.

형제(_kw_like_clause, 관리자 검색바, 라운드186)는 이미 양쪽(검색어·컬럼)을
전부 정본 '·'로 정규화해 비교하는데, 실제 자동 출동수배(dispatch.py의
candidates(), open_dispatch()가 직접 호출해 SMS/알림톡 발송 대상을 정함)와
수동 "근처 업체" 화면(api_case_nearby())은 이 정규화를 안 거쳤다.

정부 공식 업종 표기('ㆍ' 아래아)를 쓰는 협력사가 실제로 10곳(id 305~314,
라운드186 실측) 있다 — 그 업체들의 major/category가 사건 쪽 정본 표기
('·')와 문자열이 달라지면: api_case_nearby()는 trade=1 필터에서 하드
배제(지역-only 폴백이 없음)되고, dispatch.py의 candidates()는 1·3순위
(공종이 걸리는 순위)에서 빠지고 2순위(같은 지역, 공종 무관)로 밀려나
트레이드 우선순위를 잃는다(2순위조차 1순위가 이미 lim을 채우면 안 뜬다).

dispatch.py는 순환임포트를 피하려 app.py를 안 불러오므로(_like_escape와
같은 이유), _norm_dot()의 로컬 사본을 새로 둔다.
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
print("  스캔 499라운드 회귀 — 출동후보·근처업체 매칭의 가운뎃점 표기 미정규화")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
DP_PATH = os.path.join(HERE, "dispatch.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()
DP_SRC = io.open(DP_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 세 지점을 각각 독립적으로 추출(서로 안 겹침)")
# ──────────────────────────────────────────────────────────────
#  블록A: dispatch.py의 _norm_dot() 신설(순수 삽입 — 통짜 제거로 되돌림)
_a = DP_SRC.find('\n\n\ndef _norm_dot(s):')
_marker_a = "    return (s or \"\").replace(\"ㆍ\", \"·\").replace(\"･\", \"·\")\n"
_b = DP_SRC.find(_marker_a, _a)
_b = _b + len(_marker_a) if _a > 0 and _b > _a else -1
BLOCK_A = DP_SRC[_a:_b] if _a > 0 and _b > _a else ""

#  블록B: dispatch.py의 candidates() 트레이드 조건(기존 줄 수정 — 원본 문자열로 치환)
CUR_B = ('''    #  ⚠⚠ [라운드499] 형제(app.py:_kw_like_clause, 라운드186)는 이미 가운뎃점
    #    표기(ㆍ·･ vs 정본 ·)를 정규화하는데 이 자리는 안 거쳤다 — _norm_dot()
    #    독스트링 참조.
    _trade_where = " OR ".join(
        "REPLACE(REPLACE(COALESCE(category,''),'ㆍ','·'),'･','·') LIKE ? ESCAPE '\\\\'"
        " OR REPLACE(REPLACE(COALESCE(major,''),'ㆍ','·'),'･','·') LIKE ? ESCAPE '\\\\'"
        for _ in trades)
    _trade_params = [v for _t in trades for v in
                     (f"%{_like_escape(_norm_dot(_t))}%", f"%{_like_escape(_norm_dot(_t))}%")]
''')
ORIG_B = ('''    _trade_where = " OR ".join(
        "COALESCE(category,'') LIKE ? ESCAPE '\\\\' OR COALESCE(major,'') LIKE ? ESCAPE '\\\\'" for _ in trades)
    _trade_params = [v for _t in trades for v in
                     (f"%{_like_escape(_t)}%", f"%{_like_escape(_t)}%")]
''')

#  블록C: app.py의 api_case_nearby() 트레이드 조건(기존 줄 수정 — 원본 문자열로 치환)
CUR_C = ('''            #  ⚠⚠ [라운드499] 형제(_kw_like_clause, 라운드186)는 가운뎃점 표기
            #    (ㆍ·･ vs 정본 ·)를 정규화하는데 이 자리(및 dispatch.py의
            #    candidates())는 안 거쳤다 — 정부 공식 업종 표기(ㆍ)를 쓰는
            #    협력사(id 305~314 등)가 trade=1 필터에서 완전히 빠질 수
            #    있었다(이 화면은 dispatch.py 와 달리 지역-only 폴백 순위가
            #    없어 하드 배제된다).
            q += " AND (" + " OR ".join(
                "REPLACE(REPLACE(COALESCE(p.category,''),'ㆍ','·'),'･','·') LIKE ? ESCAPE '\\\\'"
                " OR REPLACE(REPLACE(COALESCE(p.major,''),'ㆍ','·'),'･','·') LIKE ? ESCAPE '\\\\'"
                for _ in _trades) + ")"
            for _t in _trades:
                _te = _like_escape(_norm_dot(_t))
                params += [f"%{_te}%", f"%{_te}%"]
''')
ORIG_C = ('''            q += " AND (" + " OR ".join(
                "COALESCE(p.category,'') LIKE ? ESCAPE '\\\\' OR COALESCE(p.major,'') LIKE ? ESCAPE '\\\\'"
                for _ in _trades) + ")"
            for _t in _trades:
                _te = _like_escape(_t)
                params += [f"%{_te}%", f"%{_te}%"]
''')

chk(bool(BLOCK_A) and "_norm_dot" in BLOCK_A, "블록A(dispatch.py _norm_dot)를 찾았다")
chk(DP_SRC.count(BLOCK_A) == 1, "블록A가 dispatch.py에 유일하다", DP_SRC.count(BLOCK_A) if BLOCK_A else 0)
chk(DP_SRC.count(CUR_B) == 1, "블록B(candidates 트레이드 조건)가 dispatch.py에 유일하다", DP_SRC.count(CUR_B))
chk(APP_SRC.count(CUR_C) == 1, "블록C(api_case_nearby 트레이드 조건)가 app.py에 유일하다", APP_SRC.count(CUR_C))
chk("ㆍ" not in ORIG_B and "ㆍ" not in ORIG_C, "원본 대조 문자열에는 정규화 로직이 없다(대조군)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 서브프로세스 실행 — 실제 함수 직접 호출")
# ──────────────────────────────────────────────────────────────
WORKER = os.path.join(HERE, "test_scan_round499_worker.py")


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
    chk(out["dispatch_found"] and out["dispatch_why"] == "같은 지역 · 공종 일치",
        "★★★★★ 새 코드: 아래아(ㆍ) 표기 협력사가 dispatch 후보 1순위(지역+공종 일치)에 뜬다", out)
    chk(out["nearby_status"] == 200 and out["nearby_found"],
        "★★★★★ 새 코드: 같은 협력사가 근처업체 trade=1 필터에도 뜬다", out)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 되돌림-증명 — dispatch.py는 candidates()를 독립 사본")
    print("    네임스페이스에서 재구성해 직접 호출(파일 미수정),")
    print("    app.py는 api_case_nearby() 뷰만 메모리에서 교체(파일 미수정)")
    # ──────────────────────────────────────────────────────────
    CANDIDATES_SRC = _ast_fn_src(DP_SRC, "candidates")
    chk(CUR_B in CANDIDATES_SRC, "블록B가 candidates() 함수 본문 안에 있다(경계 확인)")
    REVERTED_CANDIDATES_SRC = CANDIDATES_SRC.replace(CUR_B, ORIG_B)
    assert REVERTED_CANDIDATES_SRC != CANDIDATES_SRC, "dispatch.py 되돌림 치환이 실제로 안 먹었다"

    NEARBY_SRC = _ast_fn_src(APP_SRC, "api_case_nearby")
    chk(CUR_C in NEARBY_SRC, "블록C가 api_case_nearby() 함수 본문 안에 있다(경계 확인)")
    REVERTED_NEARBY_SRC = NEARBY_SRC.replace(CUR_C, ORIG_C)
    assert REVERTED_NEARBY_SRC != NEARBY_SRC, "app.py 되돌림 치환이 실제로 안 먹었다"

    _tmpdir2 = tempfile.mkdtemp(prefix="r499_revert_")
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
        REGION2 = "서울특별시 송파구"
        cid2 = conn0.execute(
            "INSERT INTO cases(case_no,status,category,region,is_demo) "
            "VALUES('R499-2','접수','가드레일·방호울타리',?,0)", (REGION2,)).lastrowid
        pid2 = conn0.execute(
            "INSERT INTO partners(name,status,region,major,license_status,phone) "
            "VALUES('아래아상사2','활성',?,'가드레일ㆍ방호울타리','건설업',?)",
            (REGION2, "01087654321")).lastrowid
        conn0.commit(); conn0.close()

        #  candidates()는 dispatch.py 안에서 open_dispatch()가 바로 이름으로
        #  부르지만, 이 테스트는 candidates() 자체만 직접 두드리므로 독립
        #  사본(dict(vars(dispatch)))에 되돌린 소스를 exec해 그 사본만 호출한다
        #  — 실제 dispatch 모듈 객체는 이 과정에서 전혀 안 바뀐다.
        import dispatch as DP2
        _ns = dict(vars(DP2))
        exec(compile(REVERTED_CANDIDATES_SRC, "<round499-reverted:candidates>", "exec"), _ns)
        conn1 = DB2.get_db()
        cands2 = _ns["candidates"](conn1, cid2)
        conn1.close()
        match2 = next((x for x in cands2 if x["id"] == pid2), None)
        chk(match2 is None or match2["why"] != "같은 지역 · 공종 일치",
            "★★★★★ 옛 코드(되돌림): 아래아(ㆍ) 표기 협력사가 dispatch 1순위(지역+공종 "
            "일치)에서 빠진다(2순위로 밀리거나 아예 안 뜬다) — 이 테스트가 진짜 결함을 "
            "잡아낼 능력이 있음을 증명", match2)

        import app as A2
        client2 = A2.app.test_client()
        with client2.session_transaction() as s:
            s["admin"] = "a1"; s["admin_role"] = "최고관리자"; s["_csrf"] = "c1"
        _ns2 = dict(vars(A2))
        exec(compile(REVERTED_NEARBY_SRC, "<round499-reverted:api_case_nearby>", "exec"), _ns2)
        _orig_view = A2.app.view_functions["api_case_nearby"]
        A2.app.view_functions["api_case_nearby"] = A2.require_role("하위관리자")(_ns2["api_case_nearby"])
        try:
            r2 = client2.get(f"/api/cases/{cid2}/nearby?trade=1", headers={"X-CSRF-Token": "c1"})
            resp2 = r2.get_json() or {}
            nearby_ids2 = [p["id"] for p in (resp2.get("partners") or [])]
            chk(r2.status_code == 200 and pid2 not in nearby_ids2,
                "★★★★★ 옛 코드(되돌림): 같은 협력사가 근처업체 trade=1 필터에서 완전히 "
                "빠진다(하드 배제)", {"status": r2.status_code, "ids": nearby_ids2})
        finally:
            A2.app.view_functions["api_case_nearby"] = _orig_view
    finally:
        os.environ.pop("BOKGUON_DB_PATH", None)
        os.environ.pop("BOKGUON_UPLOAD_DIR", None)
        os.environ.pop("BOKGUON_ENV", None)
        os.environ.pop("BOKGUON_SEED_DEMO", None)
        shutil.rmtree(_tmpdir2, ignore_errors=True)

    chk(io.open(DP_PATH, encoding="utf-8").read() == DP_SRC,
        "★★★★★ dispatch.py는 이 되돌림-증명 내내 디스크에서 전혀 건드려지지 않았다")
    chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
        "★★★★★ app.py도 전혀 건드려지지 않았다(뷰 함수만 메모리에서 교체)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] 실행/되돌림-증명", f"{type(e).__name__}: {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
