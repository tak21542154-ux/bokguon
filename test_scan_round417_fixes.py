# -*- coding: utf-8 -*-
"""스캔 417라운드 회귀 — 협력사명이 담기는 JSON error 문구 3곳이 이스케이프
   없이 f-string 으로 조립돼, admin.js:toast()(innerHTML 대입, esc() 안 거침)
   로 그대로 렌더링되던 결함(정밀조사 Agent 발견 — 각도1: 출력 이스케이핑).

     ① api_application_create()(app.py:7280, POST /api/applications/manual,
        @require_admin) — 사업자번호 중복 확인 메시지
     ② api_application_update()(app.py:7377, PATCH /api/applications/<id>,
        @require_role("중간관리자")) — 승인 시 사업자번호 중복 확인 메시지
     ③ _payout_account_gate()(app.py:13568) — 계좌 미등록 지급차단 메시지

   전역 CSP(app.py:1026-1059, script-src 'self' 'nonce-…', unsafe-inline 없음)
   덕분에 현재도 <script> 실행까지는 안 가지만, 마크업·피싱링크 주입은
   가능했다. 라운드318이 이미 쓴 관용구(Markup 템플릿 + escape(보간값))를
   그대로 이식 — 새 메커니즘 없음.

       python test_scan_round417_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(HERE, "app.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 417라운드 회귀 — 협력사명 미이스케이프 JSON error 3곳")
print("=" * 72)

print("\n[1] 소스 확인")


def body_of(fn_name):
    i0 = APP_SRC.index(f"def {fn_name}(")
    i1 = APP_SRC.index("\ndef ", i0 + 1)
    return APP_SRC[i0:i1]


chk('str(Markup(\n                                "이미 등록된 업체입니다. (사업자번호 일치: {}) "\n'
    '                                "업체 등록·관리에서 확인하세요.").format(escape(pdup["name"])))'
    in body_of("api_application_create"),
    "★★★★★ api_application_create() 가 Markup+escape 로 업체명을 이스케이프한다")
chk('Markup(' in body_of("api_application_update") and 'escape(_pdup["name"])' in body_of("api_application_update"),
    "★★★★★ api_application_update() 도 같은 방식으로 이스케이프한다")
chk('Markup(' in body_of("_payout_account_gate") and 'escape(_pname)' in body_of("_payout_account_gate"),
    "★★★★★ _payout_account_gate() 도 같은 방식으로 이스케이프한다")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round417_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

EVIL_NAME = "<b>Evil</b>업체"
ESCAPED_FRAGMENT = "&lt;b&gt;Evil&lt;/b&gt;업체"
BIZ_1 = "1234567891"   # valid_biz_no() 검사식을 실제로 통과하는 값(직접 계산)
BIZ_2 = "2345678904"   # 같은 방식으로 계산한 두 번째 값
#  ⚠ [429라운드] BIZ_2는 원래 valid_biz_no() 를 통과 못 하는 값이었다 —
#    당시엔 api_application_update() 의 승인 관문이 체크섬을 안 봐서
#    "raw SQL로 넣으니 전제조건이 아니다"가 맞았지만, 429라운드가 그 관문에도
#    체크섬 재검증을 추가해 이제는 BIZ_2 도 유효해야 승인 시도가 (체크섬
#    오류 400이 아니라) 의도한 DUP_BIZNO(409) 로 거부되는지 검증할 수 있다.

try:
    import db as DB
    DB.init_db()
    import app as A
    chk(A.valid_biz_no(BIZ_1) and A.valid_biz_no(BIZ_2),
        "  (준비) 테스트용 사업자번호(BIZ_1·BIZ_2) 둘 다 valid_biz_no() 검사를 통과한다")

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role,created_at) "
                 "VALUES('r417adm', ?, 'R417관리자', '중간관리자', ?)",
                 (DB.hash_pw("R417Adm!2468"), DB.now()))
    conn.execute("INSERT INTO partners(name,login_id,password_hash,status,partner_type,biz_no) "
                 "VALUES(?,?,?,?,?,?)",
                 (EVIL_NAME, "r417p1", DB.hash_pw("x"), "활성", "시공사", BIZ_1))
    conn.execute("INSERT INTO partners(name,login_id,password_hash,status,partner_type,biz_no) "
                 "VALUES(?,?,?,?,?,?)",
                 (EVIL_NAME, "r417p2", DB.hash_pw("x"), "활성", "시공사", BIZ_2))
    conn.commit()

    def _admin_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["admin"] = "r417adm"; sess["admin_role"] = "중간관리자"
            sess["pw_role"] = "admin"; sess["_csrf"] = "r417-csrf"
        return c

    print("\n[3] 실행 — ① 직접접수(api_application_create) 사업자번호 중복")
    c1 = _admin_client()
    r1 = c1.post("/api/applications/manual", json={
        "company": "새로들어온업체", "major": "가드레일·방호울타리", "biz_no": BIZ_1,
    }, headers={"X-CSRF-Token": "r417-csrf"})
    chk(r1.status_code == 409, "  중복 사업자번호는 409로 거부된다(회귀없음)",
        (r1.status_code, r1.get_json()))
    err1 = (r1.get_json() or {}).get("error", "")
    chk(ESCAPED_FRAGMENT in err1,
        "★★★★★ ①번 응답의 업체명이 이스케이프돼 있다(고치기 전엔 <b>가 원문 그대로였다)",
        err1)
    chk("<b>" not in err1, "  ①번 응답에 원문 <b> 태그가 섞여 있지 않다", err1)

    print("\n[4] 실행 — ② 승인(api_application_update) 사업자번호 중복")
    conn.execute("INSERT INTO partner_applications(company,biz_no,major,status,staff_count) "
                 "VALUES(?,?,?,?,?)",
                 ("승인대상업체", BIZ_2, "유리·샷시·자동문", "신규", 5))
    app_id = conn.execute("SELECT id FROM partner_applications WHERE company='승인대상업체'").fetchone()["id"]
    conn.commit()
    c2 = _admin_client()
    r2 = c2.patch(f"/api/applications/{app_id}", json={"status": "승인"},
                  headers={"X-CSRF-Token": "r417-csrf"})
    chk(r2.status_code == 409, "  승인 시도도 중복 사업자번호면 409로 거부된다(회귀없음)",
        (r2.status_code, r2.get_json()))
    err2 = (r2.get_json() or {}).get("error", "")
    chk(ESCAPED_FRAGMENT in err2,
        "★★★★★ ②번 응답의 업체명도 이스케이프돼 있다", err2)

    print("\n[5] 실행 — ③ _payout_account_gate() 계좌 미등록")
    #  ⚠ 이 함수는 계좌가 없으면 (jsonify(...), 409) 튜플을 돌려준다(맨 함수
    #    아니라 Response 단독이 아님) — 그대로 .get_json() 을 부르면 AttributeError.
    with A.app.test_request_context():
        gate_ret = A._payout_account_gate(
            conn, {"case_no": "R417-CASE", "payout": 100000, "partner_name": EVIL_NAME})
    chk(isinstance(gate_ret, tuple) and gate_ret[1] == 409,
        "  계좌 정보 없는 협력사면 (Response, 409) 튜플을 돌려준다(회귀없음)",
        gate_ret)
    gate_json = gate_ret[0].get_json() if isinstance(gate_ret, tuple) else None
    err3 = (gate_json or {}).get("error", "")
    chk(ESCAPED_FRAGMENT in err3,
        "★★★★★ ③번 응답의 업체명도 이스케이프돼 있다", err3)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[6] 되돌리기 — api_application_create만 옛 코드로(실제 파일은 안 건드림)")
# ------------------------------------------------------------

#  ⚠⚠ [라운드553] 이 라우트에 BEGIN IMMEDIATE 동시성 잠금이 새로 생기면서
#    conn.close() 단독 호출이 conn.rollback(); conn.close() 로 바뀌었다(같은
#    이유로 바로 위 업체명 중복확인 쪽도 함께 바뀜 — 이 텍스트는 그쪽과 무관).
#    이 테스트가 보는 결함(이스케이프 유무)과는 완전히 다른 축이라, 되돌리기
#    대상 문자열도 그 잠금은 그대로 둔 채 이스케이프 부분만 옛 f-string 으로
#    바꾼다 — round553 의 잠금 수정과 round417 의 이스케이프 수정이 서로
#    독립된 변수임을 유지한다(둘 다 되돌리면 이 테스트가 증명하려는 인과관계가
#    흐려진다).
#  ⚠⚠ [라운드615] api_application_create()는 단일 라우트 핸들러라
#    A.app.view_functions 딕셔너리 항목만 잠깐 치환한다(신설 이스케이프
#    블록만 제거한 사본을 exec로 재구성) — 디스크의 app.py는 이제 전혀
#    안 건드린다(예전엔 실제로 파일에 썼다가 복원하는 방식이었다).
NEW_1 = '''        if pdup:
            conn.rollback(); conn.close()
            #  ⚠⚠ [라운드417] 승인된 업체명을 이스케이프 없이 f-string 으로 JSON
            #    error 에 담아 admin.js:toast()(innerHTML 대입, esc() 안 거침)로
            #    그대로 뜬다 — 라운드318과 같은 패턴(Markup.format 이 보간값만
            #    자동 이스케이프)을 그대로 이식한다.
            return jsonify({"ok": False,
                            "error": str(Markup(
                                "이미 등록된 업체입니다. (사업자번호 일치: {}) "
                                "업체 등록·관리에서 확인하세요.").format(escape(pdup["name"])))}), 409'''
OLD_1 = '''        if pdup:
            conn.rollback(); conn.close()
            return jsonify({"ok": False,
                            "error": f"이미 등록된 업체입니다. (사업자번호 일치: {pdup['name']}) "
                                     f"업체 등록·관리에서 확인하세요."}), 409'''


def _py_fn_body(src, fn_name):
    """함수 본문 — 다음 def뿐 아니라 다음 라우트의 @app. 데코레이터가 먼저
    나오면 거기서 자른다(round610 정착 기법)."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


try:
    chk(APP_SRC.count(NEW_1) == 1, "  (준비) ①번 되돌리기 대상 텍스트가 유일하게 식별된다")
    _body6 = _py_fn_body(APP_SRC, "api_application_create")
    chk(NEW_1 in _body6, "  (준비) api_application_create() 본문 안에 NEW_1이 있다")

    _old_body = (_body6
                 .replace("def api_application_create():",
                          "def _api_application_create_pre417():", 1)
                 .replace(NEW_1, OLD_1, 1))
    chk(_old_body.count(OLD_1) == 1 and "_api_application_create_pre417" in _old_body,
        "  (준비) 함수 리네임 + 이스케이프 제거가 정확히 적용됐다(실제 파일은 안 건드림)")

    _ns = dict(vars(A))
    exec(compile(_old_body, "<round417_pre417_application_create>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_fn = A.require_admin(_ns["_api_application_create_pre417"])

    _orig_view = A.app.view_functions["api_application_create"]
    A.app.view_functions["api_application_create"] = old_fn
    try:
        c_old = _admin_client()
        r_old = c_old.post("/api/applications/manual", json={
            "company": "새로들어온업체", "major": "가드레일·방호울타리", "biz_no": BIZ_1,
        }, headers={"X-CSRF-Token": "r417-csrf"})
    finally:
        A.app.view_functions["api_application_create"] = _orig_view

    err_old = (r_old.get_json() or {}).get("error", "")
    chk(r_old.status_code == 409 and "<b>Evil</b>업체" in err_old,
        "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림)는 업체명을 원문 그대로(이스케이프 없이) "
        "돌려준다 — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", err_old)
    chk(ESCAPED_FRAGMENT not in err_old, "  옛 코드 응답엔 이스케이프된 형태가 없다", err_old)

    print("\n[7] 원복 확인 — 되돌리기 이후 다시 방어되는가(바꿔치기가 안 샜다)")
    chk(A.app.view_functions["api_application_create"] is _orig_view,
        "  view_functions가 원래 함수객체로 복원됐다")
    c_restored = _admin_client()
    r_restored = c_restored.post("/api/applications/manual", json={
        "company": "새로들어온업체", "major": "가드레일·방호울타리", "biz_no": BIZ_1,
    }, headers={"X-CSRF-Token": "r417-csrf"})
    err_restored = (r_restored.get_json() or {}).get("error", "")
    chk(r_restored.status_code == 409 and ESCAPED_FRAGMENT in err_restored,
        "★★★★ 원복 후에는 다시 이스케이프된 응답으로 정상 방어된다(바꿔치기가 안 샜다)",
        err_restored)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기 실행", f"{type(e).__name__} {e}")

APP_HASH_AFTER = read("app.py")
chk(APP_HASH_AFTER == APP_SRC,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(view_functions 딕셔너리 항목 임시치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
