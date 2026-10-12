# -*- coding: utf-8 -*-
"""스캔 429라운드 회귀 — 사업자등록번호 체크섬 우회(공개폼→승인) + 중복 활성계정
   방지 공백(create/update) + 표기 정규화 부재, 5개 지점.

   정밀조사 Agent(각도2: 사업자등록번호 검증 실효성)가 발견 — round79는 이미
   valid_biz_no()(app.py, 국세청 검사식)를 4곳(api_partner_license·update·
   create·api_application_create)에 심었는데, **가장 흔한 유입경로인 공개
   입점신청(clean_public_form)** 은 자릿수·하이픈 위치만 보는 RE_BIZNO 정규식
   만 거치고 체크섬 검증이 전혀 없었다. 게다가 실제로 partners 테이블에 값이
   박히는 유일한 지점(api_application_update 승인관문)도 체크섬 재검증이
   없어, 오타난 값이 공개폼→승인까지 아무 저지 없이 영구 저장될 수 있었다.

   round248의 활성계정 중복방지(같은 biz_no로 활성업체 2개 금지)도 승인관문
   단 한 곳에만 있고, 신청서를 거치지 않는 관리자 직접등록(api_partner_
   create)·정보수정(api_partner_update)에는 없었다. 게다가 저장값이 하이픈
   유무 등 표기를 정규화하지 않아(api_partner_profile_update만 예외), 같은
   사업자를 하이픈 위치만 바꿔 제출하면 문자열 등치 중복확인을 우회했다.

   고침(전부 트레이드오프 없는 기계적 확장 — round79/248/profile_update가
   이미 세운 원칙을 남은 형제 자리에 적용):
   (a) clean_public_form 의 biz_no 검사를 RE_BIZNO(형식만)→valid_biz_no()
       (체크섬)로 교체 + 숫자만 저장하도록 정규화. RE_BIZNO 는 이제 아무
       데서도 안 쓰여 삭제.
   (b) api_application_update 승인관문에 체크섬 재검증 추가(round79의 "접수
       때 못 걸러졌어도 승인 관문에서 막는다" 원칙을 이 필드에도 적용) +
       partners 에 복사되는 값을 정규화.
   (c) api_partner_create·api_partner_update 에 round248과 같은 활성계정
       중복확인 추가(update는 자기 자신 제외) + 저장값 정규화.
   (d) api_partner_license 도 정규화만 추가(이미 있는 값을 덮어쓸지 여부는
       이 화면 특유의 정정 요구와 충돌하는 트레이드오프라 제품판단 필요로
       분리, 미구현).

       python test_scan_round429_fixes.py
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


def fn_body(src, def_line):
    i0 = src.index(def_line)
    i1 = src.index("\n@app.", i0 + 1)
    return src[i0:i1]


APP_SRC = read("app.py")

# 국세청 검사식으로 유효한 값을 직접 계산(코드 값과 완전히 독립적으로 검증)
_W = (1, 3, 7, 1, 3, 7, 1, 3, 5)


def mk_valid(d9):
    s2 = sum(int(d9[i]) * _W[i] for i in range(9)) + (int(d9[8]) * 5) // 10
    return d9 + str((10 - s2 % 10) % 10)


VALID_A = mk_valid("300000000")   # 숫자만
VALID_A_HYPHEN = VALID_A[:3] + "-" + VALID_A[3:5] + "-" + VALID_A[5:]  # 같은 값, 하이픈 표기
VALID_B = mk_valid("400000000")
INVALID = VALID_A[:-1] + str((int(VALID_A[-1]) + 1) % 10)  # 형식은 맞지만 체크섬 실패

print("=" * 72)
print("  스캔 429라운드 회귀 — 사업자번호 체크섬 우회 + 중복계정 방지 공백")
print("=" * 72)

print("\n[1] 소스 확인")
chk("RE_BIZNO = re.compile" not in APP_SRC,
    "★★★★ 이제 아무 데서도 안 쓰는 RE_BIZNO 정의를 삭제했다(죽은 코드 정리)"
    "(주석 속 역사적 언급은 남아 있어도 됨 — 실제 바인딩만 확인)")
cpf_body = fn_body(APP_SRC, "def clean_public_form(d, required):")
chk('valid_biz_no(out["biz_no"])' in cpf_body,
    "★★★★★ clean_public_form() 이 이제 valid_biz_no() 체크섬을 거친다")
#  ⚠⚠ [라운드498] 정규식이 \D(유니코드 인식)에서 [^0-9](ASCII 전용)로
#    바뀌었다 — 유니코드 전각숫자가 \D를 통과해 정규화를 우회하던 결함을
#    라운드497(valid_biz_no 내부)·498(이 호출부들)이 고치면서 문자클래스가
#    바뀌었을 뿐, "정규화한다"는 이 라운드(429)의 취지는 그대로 유지된다.
chk('out["biz_no"] = re.sub(r"[^0-9]", "", out["biz_no"])' in cpf_body,
    "★★★★ clean_public_form() 이 통과값을 숫자만 남기고 정규화한다")

au_body = fn_body(APP_SRC, "def api_application_update(aid):")
chk('_biz = re.sub(r"[^0-9]", "", app_row.get("biz_no") or "")' in au_body,
    "★★★★★ api_application_update() 승인관문이 biz_no 를 정규화한다")
chk("if _biz and not valid_biz_no(_biz):" in au_body,
    "★★★★★ api_application_update() 승인관문이 이제 체크섬을 재검증한다")

pc_body = fn_body(APP_SRC, "def api_partner_create():")
chk('_pdup = one(conn.execute(\n            "SELECT name FROM partners WHERE biz_no=? AND status=\'활성\'"' in pc_body,
    "★★★★★ api_partner_create() 에 활성계정 중복확인이 추가됐다")

pu_body = fn_body(APP_SRC, "def api_partner_update(pid):")
chk("AND status='활성' AND id<>?" in pu_body,
    "★★★★★ api_partner_update() 의 중복확인은 자기 자신을 제외한다")
#  ⚠⚠ [라운드608] round601~ 형제결함군(raw re.sub 3번째 인자가 JSON 비문자열이면
#    TypeError로 500) 처방으로 d[f] 가 _s() 를 거치게 바뀌었다 — 리터럴만 갱신,
#    "정규화한다"는 이 라운드(429)의 취지는 그대로.
chk('d[f] = re.sub(r"[^0-9]", "", _s(d[f]))' in pu_body,
    "★★★★ api_partner_update() 가 biz_no 를 정규화한다(라운드498부터 [^0-9])")

pl_body = fn_body(APP_SRC, "def api_partner_license(pid):")
chk('_bz = re.sub(r"[^0-9]", "", _bz)' in pl_body,
    "★★★★ api_partner_license() 도 biz_no 를 정규화한다(라운드498부터 [^0-9])")

print("\n[2] 실행 준비 — 스크래치 DB + Flask 서버")
_tmpdir = tempfile.mkdtemp(prefix="round429_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    chk(A.valid_biz_no(VALID_A) and A.valid_biz_no(VALID_B) and not A.valid_biz_no(INVALID),
        "  (준비) 테스트용 사업자번호 3종이 의도한 대로 유효/무효로 갈린다",
        (VALID_A, VALID_B, INVALID))

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','최고관리자')")
    conn.commit()

    admin = A.app.test_client()
    _tok = "r429-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    hdr = {"X-CSRF-Token": _tok}

    print("\n[3] 실행 — 공개 입점신청: 체크섬 무효값은 거부, 하이픈 유효값은 정규화 저장")
    r1 = admin.post("/api/applications", json={
        "company": "R429무효신청", "phone": "010-1111-2222", "biz_no": INVALID,
        "staff_count": "5", "agree_privacy": True}, headers=hdr)
    # 공개 라우트지만 admin 세션으로 호출해도(CSRF 면제 무관) clean_public_form 은 그대로 거친다
    chk(r1.status_code == 400,
        "★★★★★ 체크섬이 틀린 사업자번호는 공개 접수 단계에서 거부된다"
        "(고치기 전엔 형식(자릿수)만 맞으면 그대로 통과했다)", (r1.status_code, r1.get_json()))

    r2 = admin.post("/api/applications", json={
        "company": "R429유효신청", "phone": "010-3333-4444", "biz_no": VALID_A_HYPHEN,
        "staff_count": "5", "agree_privacy": True}, headers=hdr)
    chk(r2.status_code == 200 and r2.get_json().get("ok"),
        "  하이픈 표기의 유효한 값은 정상 접수된다(과잉차단 아님)", r2.get_json())
    _row = conn.execute(
        "SELECT id, biz_no FROM partner_applications WHERE company='R429유효신청'").fetchone()
    chk(_row["biz_no"] == VALID_A,
        "★★★★ 저장된 값은 하이픈이 빠진 숫자만 남은 정규화된 형태다", dict(_row))
    aid_valid = _row["id"]

    print("\n[4] 실행 — 승인관문: 체크섬이 깨진 옛 신청서는 승인 자체가 막힌다")
    aid_bad = conn.execute(
        "INSERT INTO partner_applications(company,biz_no,phone,status,major,created_at) "
        "VALUES('R429구신청','9999999999','010-5555-6666','신규','금속',datetime('now'))"
    ).lastrowid
    conn.commit()
    r3 = admin.patch(f"/api/applications/{aid_bad}", json={"status": "승인"}, headers=hdr)
    chk(r3.status_code == 400,
        "★★★★★ 체크섬이 깨진 신청서는 승인 관문 자체에서 거부된다"
        "(고치기 전엔 그대로 partners 에 영구 저장됐다)", (r3.status_code, r3.get_json()))

    r4 = admin.patch(f"/api/applications/{aid_valid}", json={"status": "승인"}, headers=hdr)
    chk(r4.status_code == 200 and r4.get_json().get("ok"),
        "  유효한(하이픈 정규화된) 신청서는 정상 승인된다(과잉차단 아님)", r4.get_json())
    _prow = conn.execute("SELECT biz_no FROM partners WHERE name='R429유효신청'").fetchone()
    chk(bool(_prow) and _prow["biz_no"] == VALID_A,
        "★★★★ 승인 후 partners 에도 정규화된 숫자만 저장된다", dict(_prow) if _prow else None)

    print("\n[5] 실행 — api_partner_create: 활성계정 중복확인이 실제로 막는다")
    r5 = admin.post("/api/partners", json={"name": "R429직접등록1", "biz_no": VALID_B,
                                            "status": "활성"}, headers=hdr)
    chk(r5.status_code == 200, "  첫 등록은 정상 성공한다", r5.get_json())
    VALID_B_HYPHEN = VALID_B[:3] + "-" + VALID_B[3:5] + "-" + VALID_B[5:]
    r6 = admin.post("/api/partners", json={"name": "R429직접등록2(표기다름)",
                                            "biz_no": VALID_B_HYPHEN, "status": "활성"}, headers=hdr)
    chk(r6.status_code == 409 and r6.get_json().get("code") == "DUP_BIZNO",
        "★★★★★ 하이픈 표기만 다른 같은 사업자번호도 중복으로 거부된다"
        "(고치기 전엔 이 라우트에 중복확인 자체가 없었다)", (r6.status_code, r6.get_json()))

    print("\n[6] 실행 — api_partner_update: 남의 사업자번호로 바꿔치기 불가, 자기 자신은 예외")
    pid_c = conn.execute("SELECT id FROM partners WHERE name='R429직접등록1'").fetchone()["id"]
    VALID_C = mk_valid("500000000")
    pid_d = admin.post("/api/partners", json={"name": "R429직접등록3", "biz_no": VALID_C,
                                               "status": "활성"}, headers=hdr).get_json()["id"]
    r7 = admin.patch(f"/api/partners/{pid_d}", json={"biz_no": VALID_B}, headers=hdr)
    chk(r7.status_code == 409 and r7.get_json().get("code") == "DUP_BIZNO",
        "★★★★★ 다른 업체가 이미 쓰는 사업자번호로는 못 바꾼다"
        "(고치기 전엔 이 수정 라우트에 중복확인이 없었다)", (r7.status_code, r7.get_json()))
    r8 = admin.patch(f"/api/partners/{pid_c}", json={"biz_no": VALID_B}, headers=hdr)
    chk(r8.status_code == 200,
        "  자기 자신의 사업자번호를 그대로(또는 재확인) 저장하는 것은 막히지 않는다"
        "(자기제외 조건 확인, 과잉차단 아님)", r8.get_json())
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[7] 되돌리기 — 옛 코드였다면 실제로 뚫렸는가")
# ------------------------------------------------------------
NEW_CPF = '''    if out.get("biz_no"):
        #  ⚠ [429라운드] RE_BIZNO(자릿수·하이픈 위치만 확인)는 체크섬을 안 봐서
        #    오타가 그대로 들어간다 — 가장 흔한 유입경로(이 공개폼)만 형제
        #    (api_application_create·api_partner_create 등)가 이미 쓰는
        #    valid_biz_no() 검사숫자 검증을 안 거치고 있었다. round79 원칙을
        #    그대로 확장한다.
        if not valid_biz_no(out["biz_no"]):
            return None, "사업자등록번호가 올바르지 않습니다. 10자리 숫자를 다시 확인해 주세요."
        out["biz_no"] = re.sub(r"[^0-9]", "", out["biz_no"])
    return out, None'''
OLD_CPF = '''    if out.get("biz_no") and not RE_BIZNO.match(out["biz_no"]):
        return None, "사업자등록번호 형식을 확인해 주세요. (예: 656-87-02554)"
    return out, None'''
#  ⚠⚠ [라운드619] on-disk 되돌리기(파일에 직접 쓰고 subprocess)를 인메모리로
#    이관 — clean_public_form()은 라우트가 아니라 api_applications() 라우트가
#    "바로 이름으로" 부르는 평범한 모듈함수라 view_functions 치환(기법1)이
#    아니라 실 모듈 딕셔너리(vars(A) — 사본이 아니라 그 자체)에 직접 exec한다
#    (기법3). 옛 코드는 이미 삭제된 RE_BIZNO를 참조하므로 같은 exec 안에 그
#    정의도 함께 넣어 NameError를 막는다.


def _ast_fn_src(src, fn_name):
    """ast로 함수의 정확한 경계(decorator 제외, def~마지막 줄)를 뽑는다."""
    import ast
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            return "".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError(f"함수 {fn_name} 을 못 찾음")


try:
    _cpf_src = _ast_fn_src(APP_SRC, "clean_public_form")
    chk(_cpf_src.count(NEW_CPF) == 1,
        "  (준비) clean_public_form 되돌리기 대상이 함수 본문 안에 유일하게 식별된다")
    reverted_cpf_src = _cpf_src.replace(NEW_CPF, OLD_CPF)
    chk(reverted_cpf_src != _cpf_src, "  (준비) 되돌리기 텍스트가 실제로 달라졌다")
    chk("RE_BIZNO" not in vars(A), "  (준비) 지금 실 모듈에는 RE_BIZNO가 없다(삭제 확인)")

    _real_ns = vars(A)
    _orig_cpf = _real_ns["clean_public_form"]
    _revert_src = ('RE_BIZNO = re.compile(r"^\\d{3}-?\\d{2}-?\\d{5}$")\n\n\n' + reverted_cpf_src)
    exec(compile(_revert_src, "<round429_reverted:clean_public_form>", "exec"), _real_ns)  # noqa: S102 -- 우리 소스 그대로 추출, 디스크 미기록
    try:
        r_old = admin.post("/api/applications", json={
            "company": "R429무효신청구", "phone": "010-1111-2222", "biz_no": INVALID,
            "staff_count": "5", "agree_privacy": True}, headers=hdr)
        chk(r_old.status_code == 200,
            "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림)는 체크섬이 깨진 사업자번호도 "
            "그대로 접수해버린다(인과관계 직접증명)", (r_old.status_code, r_old.get_json()))
    finally:
        _real_ns["clean_public_form"] = _orig_cpf
        _real_ns.pop("RE_BIZNO", None)
    chk(A.clean_public_form is _orig_cpf, "  clean_public_form 이 원래 함수객체로 복원됐다")
    chk("RE_BIZNO" not in vars(A), "  RE_BIZNO 도 실 모듈에서 다시 제거됐다(원상복구 확인)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기(clean_public_form) 실행", f"{type(e).__name__} {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py는 이 되돌림-증명 내내 디스크에서 전혀 건드려지지 않았다")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
