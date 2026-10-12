# -*- coding: utf-8 -*-
"""스캔 483라운드 회귀 — 보험사 등록(api_insurer_create)·관리자수정
(api_insurer_update)이 형제(api_insurer_profile_update·api_partner_
create·api_partner_update)와 달리 RE_EMAIL 형식검사가 빠져 있던 결함,
2건(정밀조사 Agent가 RE_EMAIL.match() 호출 8곳 전수 grep으로 발견).

  형식이 깨진 이메일이 관리자 등록·수정 화면으로 심어지면, 그 보험사가
  나중에 마이페이지(api_insurer_profile_update, 이미 RE_EMAIL 검사 있음)
  에서 이메일과 무관한 필드 하나만 고쳐도 화면이 manager/dept/phone/
  email 4개를 통째로 재전송해(insurer_portal.html) 그 자리에서 비로소
  400이 뜬다 — 정작 값을 깨뜨린 등록·수정 화면에는 아무 경고가 없었다.
  협력사 쪽은 등록(api_partner_create,7988)·관리자수정(api_partner_
  update,8262)·자기수정(api_partner_profile_update,3024) 세 곳 전부
  검사하는데 보험사만 자기수정 한 곳뿐인 비대칭 구조였음을 확인.

  고침: 형제(api_partner_create·api_partner_update)와 정확히 같은
  문구·조건으로 이식(새 헬퍼 없이 각 지점 인라인).

  [1] 소스 확인 — 두 지점 모두 RE_EMAIL.match 호출이 실제로 있음.
  [2] 실제 Flask 앱(서브프로세스 워커) 실행 — 형식이 깨진 이메일로
      등록·수정 시도 시 400, 그 사이 값이 DB에 저장 안 됨(등록) 또는
      기존 값이 안 바뀜(수정)을 실제 HTTP 왕복+DB 조회로 확인, 정상
      이메일은 그대로 통과함도 함께 확인.
  [3] 되돌림-증명 — app.py의 두 새 블록을 옛(검사 없음) 코드로 각각
      임시 되돌려 같은 시나리오에서 형식이 깨진 이메일이 실제로 그대로
      저장돼 버리는 옛 동작이 재현되는지 대조.
"""
import ast
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 483라운드 회귀 — 보험사 등록·관리자수정 이메일 형식검사 누락")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 두 지점 모두 실제로 RE_EMAIL 검사를 갖는가")
# ──────────────────────────────────────────────────────────────


def extract(src, start_marker, end_marker):
    a = src.find(start_marker)
    if a < 0:
        return ""
    e = src.find(end_marker, a)
    return src[a:e] if e > 0 else ""


NEW_CREATE = extract(
    APP_SRC,
    "    #  ⚠⚠ [라운드483] 형제(api_partner_create 7988행·api_insurer_profile_",
    "    conn = DB.get_db()\n")
NEW_UPDATE = extract(
    APP_SRC,
    "            #  ⚠⚠ [라운드483] 형제(api_insurer_profile_update 3177행·api_partner_",
    "            v = _s(d[f], _R169_LIMITS[f]) if f in _R169_LIMITS else d[f]\n")

chk(bool(NEW_CREATE) and "RE_EMAIL.match" in NEW_CREATE,
    "① api_insurer_create — 새 이메일 검사 블록을 찾았다",
    "블록을 못 뽑음" if not NEW_CREATE else "")
chk(APP_SRC.count(NEW_CREATE) == 1 if NEW_CREATE else False,
    "① 되돌림-증명에 쓸 블록이 소스에 정확히 1번만 있다",
    APP_SRC.count(NEW_CREATE) if NEW_CREATE else "")
chk(bool(NEW_UPDATE) and "RE_EMAIL.match" in NEW_UPDATE,
    "② api_insurer_update — 새 이메일 검사 블록을 찾았다",
    "블록을 못 뽑음" if not NEW_UPDATE else "")
chk(APP_SRC.count(NEW_UPDATE) == 1 if NEW_UPDATE else False,
    "② 되돌림-증명에 쓸 블록이 소스에 정확히 1번만 있다",
    APP_SRC.count(NEW_UPDATE) if NEW_UPDATE else "")

OLD_CREATE = ""
OLD_UPDATE = "            v = _s(d[f], _R169_LIMITS[f]) if f in _R169_LIMITS else d[f]\n"

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 Flask 앱(in-process) — 형식오류 거부 + 정상값 통과 확인")
print("    [round620 마이그레이션: view_functions 딕트 스왑, app.py는 읽기 전용,")
print("     구 서브프로세스 워커 폐기]")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="r483_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

BAD_EMAIL = "담당자@손해보험"     # TLD 없음 — RE_EMAIL이 막아야 할 형식
GOOD_EMAIL = "ops@example.com"

try:
    import db as DB               # noqa: E402
    DB.init_db()
    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','최고관리자')")
    conn.commit()
    conn.close()

    import app as A                # noqa: E402

    def _admin_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["admin"] = "admin"
            sess["admin_name"] = "검증"
            sess["admin_role"] = "최고관리자"
            sess["_csrf"] = "r483-csrf"
        return c

    def _email_row(where_sql, arg):
        conn = DB.get_db()
        try:
            row = conn.execute(f"SELECT email FROM insurers WHERE {where_sql}", (arg,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    admin_c = _admin_client()
    r_create_bad = admin_c.post("/api/insurers",
                                 json={"name": "R483보험(불량이메일)", "email": BAD_EMAIL},
                                 headers={"X-CSRF-Token": "r483-csrf"})
    r_create_good = admin_c.post("/api/insurers",
                                  json={"name": "R483보험(정상)", "email": GOOD_EMAIL},
                                  headers={"X-CSRF-Token": "r483-csrf"})
    iid = (r_create_good.get_json() or {}).get("id")

    chk(r_create_bad.status_code == 400,
        "★★★★★ 등록: 형식이 깨진 이메일은 400으로 거부된다", r_create_bad.get_json())
    chk(_email_row("name=?", "R483보험(불량이메일)") is None,
        "★★★★★ 등록: 거부된 이메일을 가진 보험사 행 자체가 안 생겼다")
    chk(r_create_good.status_code == 200,
        "등록: 정상 이메일은 그대로 통과한다(과잉차단 아님)", r_create_good.get_json())

    assert iid, "정상 등록이 실패해 관리자수정 시나리오를 진행할 수 없다"
    r_update_bad = admin_c.patch(f"/api/insurers/{iid}", json={"email": BAD_EMAIL},
                                  headers={"X-CSRF-Token": "r483-csrf"})
    r_update_good = admin_c.patch(f"/api/insurers/{iid}", json={"email": GOOD_EMAIL},
                                   headers={"X-CSRF-Token": "r483-csrf"})
    chk(r_update_bad.status_code == 400,
        "★★★★★ 관리자수정: 형식이 깨진 이메일은 400으로 거부된다", r_update_bad.get_json())
    chk(r_update_good.status_code == 200,
        "관리자수정: 정상 이메일은 그대로 통과한다(과잉차단 아님)")
    chk((_email_row("id=?", iid) or {}).get("email") == GOOD_EMAIL,
        "관리자수정: 거부된 시도는 안 반영되고 그 다음 정상값만 실제로 저장됐다",
        _email_row("id=?", iid))

    # (B) 되돌림 — 두 함수의 되돌린 본문을 독립 사본 네임스페이스에만 exec하고,
    #     실제 require_role 데코레이터로 다시 감싸 view_functions 딕트만 스왑한다.
    assert NEW_CREATE and NEW_UPDATE, "새 블록을 못 뽑아 되돌림-증명을 진행할 수 없다"
    reverted_src = APP_SRC.replace(NEW_CREATE, OLD_CREATE).replace(NEW_UPDATE, OLD_UPDATE)
    assert reverted_src != APP_SRC, "되돌림 치환이 실제로 안 먹었다"

    _tree = ast.parse(reverted_src)
    _lines = reverted_src.splitlines(keepends=True)
    _fn_src = {}
    for _node in ast.walk(_tree):
        if isinstance(_node, ast.FunctionDef) and _node.name in ("api_insurer_create", "api_insurer_update"):
            _fn_src[_node.name] = "".join(_lines[_node.lineno - 1:_node.end_lineno])
    assert set(_fn_src) == {"api_insurer_create", "api_insurer_update"}, \
        f"되돌린 함수 소스를 AST로 못 뽑음: {sorted(_fn_src)}"
    for _name, _src in _fn_src.items():
        chk("RE_EMAIL.match" not in _src, f"  (준비) 되돌린 {_name}() 소스에 이메일 검사가 없다(되돌림 확인)")

    _ns = dict(vars(A))
    exec(compile(_fn_src["api_insurer_create"], "<round483-reverted:api_insurer_create>", "exec"), _ns)
    exec(compile(_fn_src["api_insurer_update"], "<round483-reverted:api_insurer_update>", "exec"), _ns)
    temp_create = A.require_role("최고관리자")(_ns["api_insurer_create"])
    temp_update = A.require_role("최고관리자")(_ns["api_insurer_update"])

    original_create = A.app.view_functions["api_insurer_create"]
    original_update = A.app.view_functions["api_insurer_update"]
    A.app.view_functions["api_insurer_create"] = temp_create
    A.app.view_functions["api_insurer_update"] = temp_update
    try:
        broken_create = admin_c.post("/api/insurers",
                                      json={"name": "R483보험(되돌림)", "email": BAD_EMAIL},
                                      headers={"X-CSRF-Token": "r483-csrf"})
        chk(broken_create.status_code == 200,
            "★★★★★ 옛 코드(되돌림)는 등록 시 형식이 깨진 이메일도 200으로 통과시킨다"
            " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", broken_create.get_json())
        chk((_email_row("name=?", "R483보험(되돌림)") or {}).get("email") == BAD_EMAIL,
            "★★★★★ 옛 코드(되돌림)는 형식이 깨진 이메일이 실제로 그대로 저장돼 버린다"
            " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
            _email_row("name=?", "R483보험(되돌림)"))

        broken_update = admin_c.patch(f"/api/insurers/{iid}", json={"email": BAD_EMAIL},
                                       headers={"X-CSRF-Token": "r483-csrf"})
        chk(broken_update.status_code == 200,
            "★★★★★ 옛 코드(되돌림)는 관리자수정 시에도 형식이 깨진 이메일을 통과시킨다"
            " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", broken_update.get_json())
    finally:
        A.app.view_functions["api_insurer_create"] = original_create
        A.app.view_functions["api_insurer_update"] = original_update

    chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
        "★★★★★ app.py는 되돌림-증명 내내 디스크에서 전혀 건드려지지 않았다"
        "(되돌린 함수들은 dict(vars(A)) 독립 사본에만 exec되고 view_functions만 임시 스왑됨)")

except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] 실행/되돌림-증명", f"{type(e).__name__}: {e}")
finally:
    for _k in ("BOKGUON_DB_PATH", "BOKGUON_UPLOAD_DIR", "BOKGUON_ENV", "BOKGUON_SEED_DEMO"):
        os.environ.pop(_k, None)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
