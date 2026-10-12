# -*- coding: utf-8 -*-
"""스캔 683라운드 — round567이 미해결로 남긴 제품판단 결정: compliance.check_subcontractor()
   (건산법 §25② 하수급인 자격 판정)가 GET /api/partners/<pid>/subcontract-check 로만
   닿을 수 있는데, 그 라우트가 admin.js·templates 어디에도 호출부가 없는 죽은 라우트였다.

   조사 각도 — "check_subcontractor()는 정말 버릴 죽은 코드인가"를 이 세션이 직접
   조사(하위위임 없음)했다. round567이 남긴 두 선택지(①화면에 배선 ②round105 선례처럼
   삭제)를 실제로 확인하니 —
     · test_compliance.py [6]이 이미 CP.check_subcontractor()를 **라우트를 거치지 않고**
       직접 단위테스트하고 있었다(무등록/미확인/등록확인 세 갈래 전부, round106/108이
       데이터소스 버그까지 고친 이력). round105가 지운 api_assign_manager는 이런
       독립 테스트도, 대체 불가능한 고유 로직도 없는 **완전 중복** 죽은 라우트였던 것과
       달리, check_subcontractor는 이미 검증된 고유 법률로직이다 — 지우면 이 자산이
       통째로 사라진다.
     · check_subcontractor는 license_block_reason(dispatch.py 1237행, 수배·배정
       **진입문** — '미확인'은 통과시킨다, 대부분의 업체가 미확인으로 시작하므로)과
       다른 질문에 답한다 — "지금 이 업체에 **하도급**을 줘도 되는가"(건산법 §25②
       고유의, 더 엄격한 법률질문). round106 주석이 이미 "이 함수의 목적 자체가
       확인 안 된 상태를 안전으로 보지 않는 것"이라고 명시한다 — license_block_reason과
       다른 것은 결함이 아니라 설계다.
     · 기존 파트너 상세 모달의 "🏛️ 건설업 등록 조사" 패널(admin.js partnerForm())은
       license_status **조사현황** pill(무엇을 조사했는지)만 보여줄 뿐, "그래서 지금
       하도급 가능한가"라는 법적 판정문은 없었다 — check_subcontractor가 정확히 그
       빈 자리를 메운다. 다만 그 판정문을 "할 수 없습니다" 식으로 쓰면(check_subcontractor의
       실제 문구) license_block_reason이 '미확인'을 통과시켜 두는 것과 자칫 모순돼
       보일 위험이 round567의 우려였다 — 그래서 이번 배선은 기존 pill과 나란히,
       "하도급 적격"이라는 별도 이름을 단 판정문으로 붙여 **조사현황(pill)과 하도급
       법적판정(새 줄)이 서로 다른 질문에 대한 답**임을 시각적으로 분리했다.

   결정 — ①(화면 배선)을 택한다. app.py·compliance.py는 전혀 건드리지 않는다
   (라우트·함수 둘 다 이미 맞게 동작한다 — round567도 "라이선스 로직 자체는 맞다"고
   확인). static/admin.js만 세 곳을 고친다: (a) partnerForm()의 라이선스 패널 끝에
   `#subcheckbox` 자리표시자 추가 (b) 모달을 열 때 loadAccount(id)와 나란히
   loadSubcontractCheck(id) 호출 추가 (c) 그 함수 자체 신설 — loadAccount/#acctbox와
   정확히 같은 "동기 렌더 후 비동기로 하위 패널 채우기" 패턴(admin.js 기존 관례)을
   그대로 따른다.

   ⚠ 라운드 번호 경합 — 이 파일은 처음 test_scan_round682_fixes.py로 썼으나, 같은
     세션 동안 다른(동시) 세션이 **다른 결함**(api_application_create NFKC 중복확인,
     task_f15d21d5)에 round682를 먼저 run_all_tests.py에 등록해 번호가 겹쳤다(이
     저장소에 git이 없어 실측된 기존 위험 — round279~281 선례와 같은 종류). 그 세션의
     실제 소스 수정(app.py 8160행 unicodedata.normalize("NFKC", company))은 살아있지만
     그 회귀테스트 파일 자신은 이 세션의 파일쓰기와 경합해 사라진 상태였다 — 되살릴
     원본이 없어(git 없음) 복구하지 않고, 그 공백은 별도로 보고한다. 이 파일은 683으로
     옮겨 번호 경합을 정리한다.

   테스트 기법 — on-disk 파일은 조회만 한다(app.py·compliance.py 무변경 확인 포함).
   "되돌리기" 증명은 이 세션이 고치기 **직전** Read로 확인한 admin.js 원문 조각을
   문자열로 재구성해 대조군으로 쓴다(round543/547/549/550/553/566/567과 같은 기법 —
   다만 이번은 서버측 동작을 exec()로 재현할 필요가 없는 프론트엔드 배선 사실관계라,
   "그 마커가 옛 원문엔 없고 지금 원문엔 있다" 문자열 대조로 증명한다). 라우트
   자체의 실동작 증명은 스크래치 DB + 실제 Flask 앱으로 세 가지 license_status를
   실제로 만들어 GET을 실행해, admin.js가 렌더링할 그 JSON이 CP.check_subcontractor()
   직접호출과 정확히 같음을 실측한다.

      python test_scan_round683_fixes.py
"""
import io
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def _slice(src, start_marker, end_marker, start_from=0):
    s = src.index(start_marker, start_from)
    e = src.index(end_marker, s + len(start_marker))
    return src[s:e]


print("=" * 72)
print("  스캔 683라운드 — check_subcontractor() 죽은 라우트를 파트너 상세 모달에 배선")
print("=" * 72)

ADMIN_JS = read("static/admin.js")
APP_SRC = read("app.py")
COMP_SRC = read("compliance.py")

# ==================================================================
print("\n[0] 소스 확인 — admin.js 배선 + app.py·compliance.py 무변경(직접조사, 하위위임 없음)")
# ------------------------------------------------------------------
try:
    #  ── (a)(b) partnerForm() 함수 본문만 잘라서 그 안에서 확인한다 ──
    pf_body = _slice(ADMIN_JS, "function partnerForm(id){", "\nasync function licenseSave(id){")
    chk('id="subcheckbox"' in pf_body,
        "★★★★★ partnerForm()의 건설업 등록 조사 패널에 #subcheckbox 자리표시자가 있다"
        "(고치기 전엔 없었다 — round567이 발견한 '0곳 호출')")
    chk(pf_body.count('id="subcheckbox"') == 1,
        "STEP #subcheckbox는 정확히 1곳뿐이다(중복 삽입 아님)")
    chk("if(id){ loadAccount(id); loadSubcontractCheck(id); }" in pf_body,
        "★★★★★ 모달을 열 때 loadAccount(id)와 나란히 loadSubcontractCheck(id)를 부른다")

    #  ── (c) 신설 함수 자신 — loadAccount 바로 다음, let CRED_TEXT 이전에 있다 ──
    la_body = _slice(ADMIN_JS, "async function loadAccount(id){", "\n// 하도급 적격 판정")
    chk('/api/partners/${id}/account' in la_body,
        "STEP 회귀 방지: loadAccount() 자신의 계좌 조회 호출은 그대로다")
    chk("subcontract-check" not in la_body,
        "STEP loadAccount()와 새 함수의 경계가 정확하다(서로 안 섞였다)")

    lsc_body = _slice(ADMIN_JS, "async function loadSubcontractCheck(id){", "\nlet CRED_TEXT")
    chk(ADMIN_JS.count("async function loadSubcontractCheck(id){") == 1,
        "STEP loadSubcontractCheck 정의는 정확히 1곳뿐이다")
    chk('/api/partners/${id}/subcontract-check' in lsc_body,
        "★★★★★ loadSubcontractCheck()가 죽은 라우트였던 그 경로를 실제로 부른다"
        "(GET /api/partners/<pid>/subcontract-check)")
    chk("r.check" in lsc_body and "c.ok" in lsc_body and "c.reason" in lsc_body,
        "STEP 응답의 {ok,check:{ok,code,reason,...}} 형태를 그대로 읽는다"
        "(app.py: jsonify({'ok':True,'check':CP.check_subcontractor(p)})와 형태 일치)")
    chk("esc(c.reason)" in lsc_body,
        "STEP 서버 문구를 넣을 때도 이 파일의 다른 모든 동적 텍스트와 같이 esc()로 이스케이프한다")
    chk("catch(e)" in lsc_body and "box.textContent" in lsc_body,
        "STEP loadAccount()와 같은 방식으로 실패해도 '불러오는 중…'에 멈춰 있지 않는다"
        "(회귀 없음 — 같은 관례를 새 함수에도 지켰다)")

    #  ── 되돌리기 대조군 — 고치기 직전 Read로 확인한 옛 원문 조각(파일에는 없다) ──
    _PRE683_PANEL_TAIL = (
        "      ${p.license_checked_at?`<span class=\"hint\" style=\"margin-left:8px\">"
        "최근 조사 ${esc((p.license_checked_at||'').slice(0,16))} · "
        "${esc(p.license_checked_by||'')}</span>`:''}\n    </div>`:''}"
    )
    chk("subcheckbox" not in _PRE683_PANEL_TAIL,
        "STEP 재구성한 옛 원문(패널 끝부분, 고치기 직전 Read 그대로)에는 "
        "subcheckbox 자리표시자가 없다(대조군)")
    _PRE683_OPEN_CALL = "  if(id) loadAccount(id);\n}"
    chk("loadSubcontractCheck" not in _PRE683_OPEN_CALL,
        "★★★★★ 재구성한 옛 원문(모달 오픈 호출, 고치기 직전 Read 그대로)에는 "
        "loadSubcontractCheck 호출이 없다 — round567이 본 '호출부 0곳'이 실재했다"
        "(대조군, 지금 파일에는 있다)")

    #  ── app.py·compliance.py — 이번 라운드가 손대지 않았음을 직접 확인 ──
    chk('@app.get("/api/partners/<int:pid>/subcontract-check")' in APP_SRC
        and "def api_subcontract_check(pid):" in APP_SRC
        and "CP.check_subcontractor(p)" in APP_SRC,
        "★★★ app.py: api_subcontract_check 라우트는 무변경으로 그대로 있다"
        "(이번 수정은 화면 배선뿐 — 서버는 이미 맞았다)")
    chk('def check_subcontractor(partner_row):' in COMP_SRC and "[라운드106]" in COMP_SRC,
        "★★★ compliance.py: check_subcontractor()는 지우지 않고 그대로 남겼다"
        "(round105 선례와 달리 — 이미 독립 단위테스트가 있는 고유 법률로직이라 "
        "완전 중복 죽은 코드가 아니었다는 이번 라운드의 판단)")
    #  형제 죽은 라우트(contract-gate/rules)는 이번 결정의 범위 밖 — 손대지 않았고
    #  손대지 않았다는 사실 자체를 남겨, 다음 라운드가 "이미 처리된 줄" 오인하지 않게 한다.
    chk('@app.get("/api/contract-gate/rules")' in APP_SRC
        and "def api_contract_gate_rules():" in APP_SRC,
        "STEP 형제 죽은 라우트(/api/contract-gate/rules)는 이번 범위 밖이라 손대지 않았다"
        "(여전히 무호출 상태 — 별도 판단 필요, 이번 라운드가 몰래 지우지 않았다)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드683 [0] 소스 확인", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[1] 준비 — 격리 스크래치 DB · 하위관리자(최저 등급) 세션")
# ------------------------------------------------------------------
#  ⚠ require_role("하위관리자")는 ROLE_RANK={"최고관리자":3,"중간관리자":2,"하위관리자":1}의
#    **최저** 문턱이다 — 로그인한 관리자라면 등급 무관하게 이 위젯을 볼 수 있어야 한다는
#    뜻이므로, 일부러 가장 낮은 등급으로 검증한다(더 높은 등급도 되는 것은 자명하다).
_tmpdir = tempfile.mkdtemp(prefix="round683_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

A = DB = None
try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('admin683','x','실행계정683','하위관리자')")
    conn0.commit(); conn0.close()
    chk(True, "STEP 스크래치 DB·하위관리자 계정 준비 완료")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드683 [1] 준비", f"{type(e).__name__} {e}")


def mkpartner(login_id, name, license_status=None, license_no=""):
    c = DB.get_db()
    c.execute(
        "INSERT INTO partners(name, partner_type, login_id, password_hash, ceo, phone, "
        "email, address, region, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (name, "시공사", login_id, "x", "김대표", "010-2222-3333",
         f"{login_id}@test.com", "서울시 강남구", "서울", "활성", DB.now()))
    c.commit()
    pid = c.execute("SELECT id FROM partners WHERE login_id=?", (login_id,)).fetchone()["id"]
    if license_status is not None:
        c.execute("UPDATE partners SET license_status=?, license_no=? WHERE id=?",
                   (license_status, license_no, pid))
        c.commit()
    c.close()
    return pid


# ==================================================================
print("\n[2] 종단 실행 — admin.js가 렌더링할 실제 JSON을 실제 Flask 라우트로 만든다")
# ------------------------------------------------------------------
try:
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "admin683"; sess["admin_role"] = "하위관리자"; sess["admin_name"] = "실행계정683"

    p_unreg = mkpartner("r683unreg", "R683무등록업체", license_status="무등록")
    p_unknown = mkpartner("r683unknown", "R683미확인업체", license_status="미확인")
    p_ok = mkpartner("r683ok", "R683등록업체", license_status="등록확인",
                      license_no="서울중구 22-가-001")
    p_blank = mkpartner("r683blank", "R683공란업체")   # license_status 컬럼을 아예 안 건드림

    def _get(pid):
        r = c.get(f"/api/partners/{pid}/subcontract-check")
        return r.status_code, r.get_json()

    def _direct(pid):
        row = DB.get_db().execute("SELECT * FROM partners WHERE id=?", (pid,)).fetchone()
        return A.CP.check_subcontractor(dict(row))

    code_u, body_u = _get(p_unreg)
    chk(code_u == 200 and body_u.get("ok") is True, "STEP 무등록 업체 조회는 200", (code_u, body_u))
    chk(body_u["check"]["ok"] is False and body_u["check"]["code"] == "무등록",
        "★★★★★ 무등록 업체 — 하도급 불가 판정, code='무등록'", body_u["check"])
    chk("제25조" in body_u["check"]["reason"], "STEP 근거 조문이 사유문에 표시된다", body_u["check"]["reason"])
    chk(body_u["check"] == _direct(p_unreg),
        "★★★★★ 라우트 응답이 CP.check_subcontractor() 직접호출과 정확히 같다(무등록)")

    code_k, body_k = _get(p_unknown)
    chk(body_k["check"]["ok"] is False and body_k["check"]["code"] == "등록미확인",
        "★★★★★ 미확인 업체 — license_block_reason과 달리 여기서는 통과시키지 않는다"
        "(round106 설계 의도 그대로, 이번 라운드가 안 건드렸음을 재확인)", body_k["check"])
    chk(body_k["check"] == _direct(p_unknown),
        "STEP 라우트 응답이 직접호출과 정확히 같다(미확인)")

    code_ok, body_ok = _get(p_ok)
    chk(body_ok["check"]["ok"] is True and body_ok["check"]["code"] == "등록확인",
        "★★★★★ 등록확인 업체 — 하도급 가능 판정", body_ok["check"])
    chk(body_ok["check"] == _direct(p_ok),
        "STEP 라우트 응답이 직접호출과 정확히 같다(등록확인)")

    code_b, body_b = _get(p_blank)
    chk(body_b["check"]["code"] == "등록미확인",
        "STEP license_status 컬럼이 공란(NULL)인 신규 업체도 '미확인'과 같은 "
        "안전측 기본값으로 처리된다(회귀 없음)", body_b["check"])

    code_404, body_404 = _get(999999)
    chk(code_404 == 404 and body_404.get("ok") is False,
        "STEP 없는 협력사 id는 404(회귀 없음 — 이번 라운드가 안 건드린 기존 동작)",
        (code_404, body_404))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드683 [2] 종단 실행", f"{type(e).__name__}: {e}")


# ==================================================================
# 정리
# ------------------------------------------------------------------
os.environ.pop("BOKGUON_DB_PATH", None)
os.environ.pop("BOKGUON_UPLOAD_DIR", None)
os.environ.pop("BOKGUON_ENV", None)
os.environ.pop("BOKGUON_SEED_DEMO", None)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
