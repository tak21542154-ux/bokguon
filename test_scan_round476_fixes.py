# -*- coding: utf-8 -*-
"""스캔 476라운드 회귀 — 협력사 건설업 등록조사(`api_partner_license`)가
'무등록'으로 기록할 때 진행 중 사건·미지급 정산·열린 하자를 안 보여주고
확인도 안 받던 결함, 1건.

형제(`_partner_demote_gate`, status를 '퇴출'·'경고'로 내릴 때 쓰는
확인관문)와 같은 성격의 확인이 `license_status`에는 전혀 없었다 —
'무등록'은 도급 적법성의 법정 판정 기준(건설산업기본법 제25조②)인데도
등급이 더 낮은(하위관리자) 이 화면은 진행 중인 사건이 있어도 아무 경고
없이 그대로 기록됨. 이미 진행 중인 도급까지 자동으로 멈추거나
재배정하는 것은 새 정책 판단이 필요해 손대지 않고, 형제와 같은
"미리 보여주고 확인받는" 정보성 관문만 이식한다(새 메커니즘 없음).

[1] 소스 확인 — 백엔드 관문 + 프런트 두 호출부(licenseSave·ACT.licSet)의
    재확인 배선이 실제로 있음.
[2] 실제 Flask 앱으로 되돌림-증명 — app.py의 새 코드블록을 옛(취약)
    상태로 임시로 되돌려(디스크 파일 실제 수정 후 원상복구) 옛 동작이
    실제로 확인 없이 통과시키는지, 새 코드가 실제로 막는지(그리고
    confirm_license로 통과하는지) 서브프로세스로 대조.
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
print("  스캔 476라운드 회귀 — 협력사 무등록 기록 시 진행중 사건 확인관문")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
APP_PATH = os.path.join(HERE, "app.py")
ADM_PATH = os.path.join(HERE, "static", "admin.js")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()
ADM_SRC = io.open(ADM_PATH, encoding="utf-8").read()

OLD_CALL = '''        #  ⚠ **사업자번호도 여기서 받는다.** 조사하려면 그 번호가 필요한데
        #    활성 399곳 중 1곳에만 있었다 — 조사하며 알게 된 값을 그 자리에서
        #    남기지 못하면 다음 사람이 또 찾는다.'''

NEW_BLOCK = '''        #  ⚠⚠ [라운드476] 형제(_partner_demote_gate, 8122행 — status를
        #    '퇴출'·'경고'로 내릴 때 진행 중 사건·미지급 정산·열린 하자를 미리
        #    보여주고 확인을 받는다)와 같은 성격의 확인이 license_status에는
        #    전혀 없었다 — '무등록'은 도급 적법성의 법정 판정 기준
        #    (건설산업기본법 제25조②, license_block_reason 참조)인데도
        #    등급이 더 낮은(하위관리자) 이 화면은 진행 중인 사건이 있어도
        #    아무 경고 없이 그대로 기록됨(실측 재현: 시공중 사건을 둔 업체를
        #    확인 없이 무등록으로 바꿔도 200). 이미 진행 중인 도급까지
        #    자동으로 멈추거나 재배정하는 것은 새 정책 판단이 필요해 손대지
        #    않는다 — 여기서는 형제와 같은 "미리 보여주고 확인받는" 정보성
        #    관문만 이식한다(새 메커니즘 없음, `confirm_license`가 오면
        #    통과).
        if st == "무등록" and not _truthy(d.get("confirm_license")):
            _info = _partner_exit_load(conn, pid)
            if _info["active_count"] or _info["unpaid_count"] or _info["open_defect_count"]:
                _names = ", ".join(f"{c['case_no']}({c['status']})"
                                    for c in _info["active_cases"][:3])
                return jsonify({
                    "ok": False, "code": "PARTNER_HAS_WORK",
                    "error": (f"이 업체는 진행 중 사건 {_info['active_count']}건"
                              + (f" · 미지급 정산 {_info['unpaid_count']}건 "
                                 f"{_info['unpaid_amount']:,}원" if _info["unpaid_count"] else "")
                              + (f" · 열린 하자 {_info['open_defect_count']}건"
                                 if _info["open_defect_count"] else "")
                              + f"을 안고 있습니다. — {_names}. "
                                f"'무등록'으로 기록해도 이미 진행 중인 사건은 시스템이 자동으로 "
                                f"멈추지 않습니다 — 도급 적법성(건설산업기본법 제25조②) 문제가 "
                                f"있다면 그 사건들은 운영팀이 개별적으로 검토해야 합니다. "
                                f"그래도 기록하시겠습니까?"),
                    **_info}), 409
        #  ⚠ **사업자번호도 여기서 받는다.** 조사하려면 그 번호가 필요한데
        #    활성 399곳 중 1곳에만 있었다 — 조사하며 알게 된 값을 그 자리에서
        #    남기지 못하면 다음 사람이 또 찾는다.'''

chk(NEW_BLOCK in APP_SRC,
    "★★★★★ api_partner_license()에 진행중사건 확인관문이 있다")
chk(APP_SRC.count(NEW_BLOCK) == 1,
    "되돌림-증명에 쓸 새 블록이 소스에 정확히 1번만 있다(대체 지점 특정 가능)",
    APP_SRC.count(NEW_BLOCK))
chk("confirm_license" in ADM_SRC and ADM_SRC.count("PARTNER_HAS_WORK") == 3,
    "★★★★ 프런트 두 호출부(licenseSave·ACT.licSet) 모두 재확인 배선이 있다"
    "(기존 demoteConfirm() 1곳+새 2곳=3곳 기대)", ADM_SRC.count("PARTNER_HAS_WORK"))

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 Flask 앱 — 되돌림-증명 (in-process view_functions 딕트 스왑,")
print("    app.py 파일은 읽기 전용 — round620 마이그레이션, 구 서브프로세스 워커 폐기)")
# ══════════════════════════════════════════════════════════════
_tmpdir = tempfile.mkdtemp(prefix="r476_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB               # noqa: E402
    DB.init_db()
    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','최고관리자')")
    iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R476보험','활성')").lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,license_status,lat,lng) "
        "VALUES('R476업체','시행사','활성','등록확인',37.5,127.0)").lastrowid
    conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,partner_id,partner_name) "
        "VALUES('26-476001','시공중','가드레일','서울',?,?,'R476업체')", (iid, pid))
    conn.commit()
    conn.close()

    import app as A                # noqa: E402

    def _admin_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["admin"] = "admin"
            sess["admin_name"] = "검증"
            sess["admin_role"] = "최고관리자"
            sess["_csrf"] = "r476-csrf"
        return c

    def _license_of(pid):
        conn = DB.get_db()
        try:
            return conn.execute(
                "SELECT license_status FROM partners WHERE id=?", (pid,)).fetchone()["license_status"]
        finally:
            conn.close()

    # (A) 현재(고쳐진) 코드로 먼저 실행 — 실제 view_functions 그대로, 아무것도 안 바꿈
    c = _admin_client()
    r1 = c.post(f"/api/partners/{pid}/license", json={"license_status": "무등록"},
                headers={"X-CSRF-Token": "r476-csrf"})
    r1_body = r1.get_json() or {}
    chk(r1.status_code == 409 and r1_body.get("code") == "PARTNER_HAS_WORK",
        "★★★★★ 고쳐진 코드는 확인 없이 무등록 기록을 시도하면 409로 먼저 되묻는다", r1_body)
    chk(_license_of(pid) == "등록확인",
        "★★★★★ 되물은 시점엔 license_status가 아직 안 바뀌어 있다", _license_of(pid))
    r2 = c.post(f"/api/partners/{pid}/license",
                json={"license_status": "무등록", "confirm_license": True},
                headers={"X-CSRF-Token": "r476-csrf"})
    chk(r2.status_code == 200 and _license_of(pid) == "무등록",
        "★★★★★ confirm_license를 붙여 재요청하면 정상 반영된다",
        (r2.status_code, _license_of(pid)))

    # (B) 되돌림 — 되돌린 함수 본문을 독립 사본 네임스페이스에만 exec하고, 실제
    #     require_role 데코레이터로 다시 감싸 view_functions 딕트만 임시로 스왑한다
    #     (app.py 파일은 물론, 실제 A 모듈의 __dict__도 전혀 안 건드림).
    reverted_src = APP_SRC.replace(NEW_BLOCK, OLD_CALL)
    assert reverted_src != APP_SRC, "되돌림 치환이 실제로 안 먹었다"

    _tree = ast.parse(reverted_src)
    _lines = reverted_src.splitlines(keepends=True)
    _fn_src = None
    for _node in ast.walk(_tree):
        if isinstance(_node, ast.FunctionDef) and _node.name == "api_partner_license":
            _fn_src = "".join(_lines[_node.lineno - 1:_node.end_lineno])
            break
    assert _fn_src, "되돌린 api_partner_license() 함수 소스를 AST로 못 뽑음"
    chk(OLD_CALL.strip() in _fn_src and "PARTNER_HAS_WORK" not in _fn_src,
        "  (준비) 되돌린 함수 소스에 확인관문이 없다(되돌림 확인)")

    _ns = dict(vars(A))
    exec(compile(_fn_src, "<round476-reverted:api_partner_license>", "exec"), _ns)
    temp_fn = A.require_role("하위관리자")(_ns["api_partner_license"])

    # 재시도용으로 pid를 다시 '등록확인'으로 리셋(위 (A)에서 이미 '무등록'으로 바뀜)
    conn = DB.get_db()
    conn.execute("UPDATE partners SET license_status='등록확인' WHERE id=?", (pid,))
    conn.commit()
    conn.close()

    original_fn = A.app.view_functions["api_partner_license"]
    A.app.view_functions["api_partner_license"] = temp_fn
    try:
        broken = c.post(f"/api/partners/{pid}/license", json={"license_status": "무등록"},
                         headers={"X-CSRF-Token": "r476-csrf"})
        chk(broken.status_code == 200,
            "★★★★★ 옛 코드(되돌림)는 진행 중 사건이 있어도 확인 없이 곧바로 200을 준다",
            broken.get_json())
        chk(_license_of(pid) == "무등록",
            "★★★★★ 옛 코드(되돌림)는 첫 호출만으로 이미 license_status가 바뀌어 버린다"
            " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", _license_of(pid))
    finally:
        A.app.view_functions["api_partner_license"] = original_fn

    chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
        "★★★★★ app.py는 되돌림-증명 내내 디스크에서 전혀 건드려지지 않았다"
        "(되돌린 함수는 dict(vars(A)) 독립 사본에만 exec되고 view_functions만 임시 스왑됨)")

except Exception as e:                                              # noqa: BLE001
    chk(False, "[2] 되돌림-증명 준비/실행", f"{type(e).__name__}: {e}")
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
