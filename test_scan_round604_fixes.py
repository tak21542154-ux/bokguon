# -*- coding: utf-8 -*-
"""스캔 604라운드 회귀 — 하자(defect/warranty) 서브시스템 + 시공완료보고, 자유텍스트
   필드(title·content·resolution·reason·memo) 12곳이 형제결함군(raw
   `(d.get(...) or "").strip()` / `(d.get(...) or "")[:N]` / `d['x'][:N]`,
   round601 `_create_case()` case_no · round602 `_idem_fingerprint()` address ·
   round603 `is_bot()` website_url/_hp)과 똑같은 결함이라, 보험사 포털·협력사
   포털이 그 필드를 숫자 등 비문자열로 보내면 AttributeError/TypeError 로
   500이 나던 결함.

   조사 배경 — 이번 라운드 지시각도(3) "raw .strip() 형제결함군의 4번째 인스턴스
   사냥 — 아직 못 본 파이프라인"을 따라, 이미 닫힌 두 파이프라인(보험사
   B2B `/api/v1/cases`·공개폼 `/api/leads`·`/api/applications`) 밖에서 값을
   받는 자리를 찾았다. 먼저 app.py 전체의 notify() 호출 114건을 AST로 정적분석해
   message 인자가 f-string/리터럴이 아닌 자리를 추렸는데(직접조사, 하위위임 없음),
   대부분은 f-string 산술결합이라 실제로는 안전했다 — 그런데 그 과정에서 우연히
   두 곳(api_defect_update 옛 15413·15480행 부근)의 **notify 메시지 조립
   조건문 자체**가 `(d.get("resolution") or "").strip()` 형태임을 발견했다.
   같은 필드(resolution)를 이 함수 안에서 또 어디서 읽는지 전수 grep(`_idem_
   fingerprint`가 이미 겪은 "같은 값을 두 번째로 다시 읽다가 놓친다" 패턴을
   경계해)한 결과 changed_fields 루프(옛 15460행)에도 raw `(d[f] or "")[:1000]`
   가 있었다 — 실제로는 이 자리가 가장 먼저 실행돼 크래시 지점이었다(실측
   재현, 아래 [3]). 같은 하자 서브시스템의 형제 라우트까지 grep 을 넓힌 결과
   3곳이 더 나왔다:
     · api_defect_create(POST /api/defects, **보험사 포털 또는 어드민**) —
       title(옛 15200·15246·15288행, 3곳이 같은 값을 raw로 반복해 읽음)·
       content(옛 15288행) — 형제(_create_case 등)와 달리 이 라우트는 보험사
       포털이 직접 부를 수 있는데도 이 결함군의 검토 대상에서 빠져 있었다.
     · api_partner_defect_resolve(POST /api/partner/defects/<id>/resolve,
       **협력사 포털**) — resolution(옛 15841행). 재시공 완료 보고 자체가
       막힌다.
     · api_partner_defect_dispute(POST /api/partner/defects/<id>/dispute,
       **협력사 포털**) — reason(옛 15897행). 귀책 이의제기 자체가 막힌다.
   1차 수정·실측(아래 [2])에서 보험사 포털의 숫자 title 이 여전히 500임을
   발견 — **f-string 보간 자체는 str() 강제라 안전해도, 그 안의 하위식이
   먼저 평가된다**는 것을 놓쳤다: `f"...{d['title'][:20]}"` 는 슬라이스
   `d['title'][:20]` 가 f-string 이 문자열화하기 **전에** 실행되므로 title 이
   비문자열이면 f-string 에 닿기도 전에 TypeError 가 난다(옛 15311·15316행,
   notify·DB.log 각 1곳) — "f-string 이라 안전하다"는 판단이 상위식에는
   맞아도 하위식에는 적용되지 않는다는 것을 이번 라운드가 실측으로 직접
   교훈삼았다. 같은 실수를 하지 않았는지 전수 재확인(정규식으로 raw
   dict 읽기에 슬라이스/문자열메서드가 곧바로 이어붙는 자리 전체를 훑음)
   하다가 완전히 다른 함수 api_partner_complete(POST 시공완료보고,
   **협력사 포털**)의 memo(옛 12297행, `body().get("memo", "")[:500]` —
   "memo" 키가 있는데 비문자열이면 기본값 ""가 안 먹혀 그대로 슬라이스됨)
   도 같은 결함임을 발견해 함께 고쳤다.
   즉 이 결함군은 이제 보험사 B2B API·공개폼에 이어 **보험사 포털·협력사
   포털**(둘 다 올림포스 직원이 아닌 외부 업체가 직접 쓰는 화면/연동)까지
   4번째·5번째 파이프라인으로 확인됐다 — admin 전용 경로(api_defect_update)
   에도 같은 결함이 있어 총 12개 지점, 5개 함수에 걸쳐 있었다.

   범위 판단(정책 메모) — 위 grep 을 app.py 전체로 넓히면 라운드601 메모가
   "이미 검토완료·안전"이라 정리해 둔 어드민 콘솔 전용 경로에서도 같은 raw
   패턴이 80곳 넘게 더 나온다(예: api_insurer_credentials·issue_partner_login
   의 login_id, api_notice_create 의 title/body 등 — 전부 로그인한 직원만
   호출 가능). 이번 라운드는 그 전수 하드닝은 **일부러 하지 않았다** — 이번
   지시각도의 목표는 "새 파이프라인 사냥"이었고, 관리자 콘솔 전용 경로는
   이미 별도로 검토된 낮은 우선순위 더미이며, 80여 곳을 한 라운드에 몰아
   고치면 리뷰 가능한 최소 diff 원칙에 어긋난다. 대신 그 목록을 그대로
   보존해 605 라운드 인계에 남긴다(최종 보고 참고) — 사이트 하나하나를
   패치하기보다 공용 정제 데코레이터/헬퍼로 한 번에 막는 설계가 더 나을
   수 있다는 제안과 함께.

   왜 그동안 안 걸렸나 — severity·cost_bearer 는 이미 화이트리스트(`not in
   (...)`) 로 막혀 있어 이 자리에 도달할 때는 항상 안전한 문자열이다(직접
   대조 확인, 아래 [0]). due_date 는 정규식(`\\d{4}-\\d{2}-\\d{2}`)으로 막힌다.
   그런데 title·content·resolution·reason·memo 는 자유 텍스트라 그런 형식
   검증이 원래 없고, 딱 하나 있어야 할 방어(_s() 의 문자열 강제)만 빠져
   있었다 — round601~603 이 각각 다른 함수에서 발견한 것과 정확히 같은
   모양의 구멍이다.

   고침 — 새 정책·헬퍼 없이, 형제들이 이미 쓰는 `_s(d.get(...), n)` 을 12곳
   전부에 그대로 적용했다(app.py):
     · api_defect_create(): `_title = _s(d.get("title"), 100)` 을 함수 앞부분에서
       한 번만 계산해 이후 중복확인 쿼리·INSERT·notify·DB.log 네 곳에서
       재사용(raw 재조회 제거) + INSERT 의 content 를 `_s(d.get("content"), 1000)` 로.
     · api_defect_update(): changed_fields 루프의 resolution 슬라이스를
       `_s(d[f], 1000)` 로, '반려'·'하자이의처리' 두 notify 의 resolution
       조건을 각각 `_s(d.get("resolution"))` 로(cost_bearer 조건은 이미
       화이트리스트를 통과해야만 도달하므로 그대로 둠 — 과잉수정 없음).
     · api_partner_defect_resolve(): UPDATE 값을 `_s(d.get("resolution"), 1000)` 로.
     · api_partner_defect_dispute(): `reason = _s(d.get("reason"))` 로(그 뒤
       길이검증·1000자 절단 로직은 손대지 않음).
     · api_partner_complete(): `memo = _s(body().get("memo"), 500)` 로.

   [0] 소스 확인 — 12곳 전부 옛 raw 패턴이 사라지고 _s() 로 바뀌었다(주석이 아니라
       실제 코드 줄에서, round549 가 쓴 "코드만 남기고 주석 제거 후 대조" 방식).
   [1] 준비 — 스크래치 DB, 어드민·보험사·협력사 계정 + 사건·하자 픽스처.
   [2] 실행(api_defect_create) — 보험사 포털이 title 을 숫자로, 어드민이 content 를
       숫자로 보내도 500 대신 200 이고 DB 에 문자열화되어 저장됨을 확인.
   [3] 실행(api_defect_update) — resolution 숫자를 (a) 상태변경 없이,
       (b) '반려'와 함께, (c) 귀책이의 처리 경로로 각각 보내 셋 다 500 대신
       200 임을 확인(옛 코드였다면 (a)(c)는 changed_fields 루프에서, (b)는
       반려 notify 조건에서 각각 다른 예외로 죽었을 자리 — [6]이 실측 증명).
   [4] 실행(협력사 포털) — api_partner_defect_resolve 의 resolution 숫자,
       api_partner_defect_dispute 의 reason 숫자(짧은 값·긴 값 둘 다) 처리 확인.
   [4B] 실행(api_partner_complete) — 협력사 시공완료보고의 memo 숫자 처리 확인
       (하자 서브시스템과 무관한 별개 함수 — 전수 재확인 중 발견).
   [5] 회귀 안전 — 정상 문자열 입력은 지금 코드에서도 그대로 동작(과잉교정 없음):
       severity·cost_bearer 화이트리스트, resolution 실제 변경 시 로그, 문자열
       reason 10자 미만 거부.
   [6] 되돌리기 — app.py 파일은 전혀 건드리지 않고, 공용 헬퍼 A._s 하나만 "604
       이전"(문자열 강제 없이 raw strip/slice) 버전으로 즉시 원복 가능하게
       몽키패치해, 위 [2]~[4B]와 정확히 같은 요청들이 실제로 다시 500 이 되는지
       확인한 뒤 원래 _s 로 되돌린다(finally) — 인과관계 직접증명. app.py 파일
       내용 자체가 이 절차 동안 전혀 안 바뀌었음을 해시로 확인한다.

   app.py 자신의 라우트 5곳(api_defect_create·api_defect_update·
   api_partner_defect_resolve·api_partner_defect_dispute·api_partner_complete)을
   고쳤으므로 서버 재기동 필요.

      python test_scan_round604_fixes.py
"""
import hashlib
import io
import os
import shutil
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


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


def _code_only(body):
    """주석 줄(이번 수정이 남긴 설명 안에 옛 raw 패턴 문자열이 인용돼 있어,
       주석까지 그대로 검색하면 '옛 패턴이 아직 있다'는 오탐이 난다)을 빼고
       실제 코드 줄만 이어붙인다."""
    return "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("#"))


print("=" * 72)
print("  스캔 604라운드 회귀 — 하자 서브시스템+시공완료보고 12곳, raw .strip()/슬라이스")
print("  형제결함군(round601~603과 같은 부류) — 보험사포털·협력사포털·어드민")
print("=" * 72)

APP_SRC = read("app.py")

# ==================================================================
print("\n[0] 소스 확인 — 12곳 전부 옛 raw 패턴이 사라지고 _s() 로 바뀌었다")
# ------------------------------------------------------------------
try:
    dc_code = _code_only(_py_fn_body(APP_SRC, "api_defect_create"))
    chk('d["title"].strip()' not in dc_code and '(d.get("title") or "").strip()' not in dc_code,
        "★★★★★ api_defect_create() 에 title 의 raw strip 이 더 이상 없다")
    chk('(d.get("content") or "")[:1000]' not in dc_code,
        "★★★★ api_defect_create() 에 content 의 raw 슬라이스가 더 이상 없다")
    chk('_title = _s(d.get("title"), 100)' in dc_code,
        "★★★★★ api_defect_create() 가 title 을 한 번만 _s() 로 정제해 재사용한다")
    chk(dc_code.count("_title") >= 5,
        "STEP _title 이 최소 5곳(검증·중복확인·INSERT·notify·DB.log)에서 재사용된다",
        dc_code.count("_title"))
    chk('_s(d.get("content"), 1000)' in dc_code,
        "★★★★ api_defect_create() 의 content 가 _s() 로 정제된다")
    chk("d['title'][" not in dc_code and 'd["title"][' not in dc_code,
        "★★★★★ api_defect_create() 에 f-string 안 raw d['title'][:N] 슬라이스가 "
        "더 이상 없다(f-string 보간 자체는 안전해도 그 안의 슬라이스는 먼저 "
        "평가된다는 것을 실측[2]으로 확인한 뒤 추가한 검사)")
    chk("_title[:20]" in dc_code and "_title[:24]" in dc_code,
        "★★★★ 두 f-string(notify·DB.log) 모두 안전한 _title 을 슬라이스한다")

    du_code = _code_only(_py_fn_body(APP_SRC, "api_defect_update"))
    chk('(d.get("resolution") or "").strip()' not in du_code,
        "★★★★★ api_defect_update() 에 resolution raw .strip() 조건이 더 이상 없다")
    chk('(d[f] or "")[:1000]' not in du_code,
        "★★★★★ api_defect_update() 의 changed_fields 루프에 raw 슬라이스가 더 이상 없다")
    chk(du_code.count("_s(d.get(\"resolution\"))") == 2,
        "★★★★ '반려'·'하자이의처리' 두 notify 조건이 각각 _s(d.get(\"resolution\")) 다",
        du_code.count('_s(d.get("resolution"))'))
    chk('v = _s(d[f], 1000) if f == "resolution" else d[f]' in du_code,
        "★★★★★ changed_fields 루프의 resolution 칸이 _s(d[f], 1000) 로 바뀌었다")
    chk('(d.get("cost_bearer") or "").strip()' in du_code,
        "STEP cost_bearer 조건은 그대로다(이미 화이트리스트를 거쳐야만 도달 — 과잉수정 없음)")

    pr_code = _code_only(_py_fn_body(APP_SRC, "api_partner_defect_resolve"))
    chk('(d.get("resolution") or "")[:1000]' not in pr_code,
        "★★★★★ api_partner_defect_resolve() 에 raw 슬라이스가 더 이상 없다")
    chk('_s(d.get("resolution"), 1000)' in pr_code,
        "★★★★★ api_partner_defect_resolve() 가 _s(d.get(\"resolution\"), 1000) 을 쓴다")

    pd_code = _code_only(_py_fn_body(APP_SRC, "api_partner_defect_dispute"))
    chk('(d.get("reason") or "").strip()' not in pd_code,
        "★★★★★ api_partner_defect_dispute() 에 reason raw .strip() 이 더 이상 없다")
    chk('reason = _s(d.get("reason"))' in pd_code,
        "★★★★★ api_partner_defect_dispute() 가 reason = _s(d.get(\"reason\")) 를 쓴다")
    chk("if len(reason) < 10:" in pd_code and "reason = reason[:1000]" in pd_code,
        "STEP 길이검증(10자 이상)·1000자 절단 로직은 그대로다(새 정책 없음)")

    pc_code = _code_only(_py_fn_body(APP_SRC, "api_partner_complete"))
    chk('body().get("memo", "")[:500]' not in pc_code,
        "★★★★★ api_partner_complete() 에 memo 의 raw 슬라이스가 더 이상 없다")
    chk('memo = _s(body().get("memo"), 500)' in pc_code,
        "★★★★★ api_partner_complete() 가 memo = _s(body().get(\"memo\"), 500) 를 쓴다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드604 [0] 소스 확인", f"{type(e).__name__} {e}")

APP_HASH_BEFORE = hashlib.sha256(APP_SRC.encode("utf-8")).hexdigest()

# ==================================================================
print("\n[1] 준비 — 스크래치 DB·업로드·로그 격리, 어드민·보험사·협력사 계정 "
      "+ 사건·하자 픽스처")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round604_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "bokguon.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r604-csrf"
H = {"X-CSRF-Token": CSRF}
A = DB = None
iid = pid = cid = did_list = None

try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('admin604','x','실행계정604','중간관리자')")
    conn0.execute("INSERT INTO insurers(name,status) VALUES('R604보험사','활성')")
    iid = conn0.execute("SELECT id FROM insurers WHERE name='R604보험사'").fetchone()["id"]
    pid = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,created_at) "
        "VALUES('R604업체','시공사','활성','가드레일','서울',?)", (DB.now(),)).lastrowid
    cid = conn0.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer,insurer_id,partner_id,"
        "                  partner_name,created_at) "
        "VALUES('R604-CASE','완료','가드레일','서울','R604보험사',?,?,'R604업체',?)",
        (iid, pid, DB.now())).lastrowid
    conn0.commit()
    conn0.close()
    chk(bool(iid and pid and cid), "STEP 어드민·보험사·협력사·사건 픽스처 생성", (iid, pid, cid))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드604 [1] 준비", f"{type(e).__name__} {e}")


def _admin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "admin604"; sess["admin_name"] = "실행계정604"
        sess["admin_role"] = "중간관리자"; sess["_csrf"] = CSRF
    return c


def _insurer_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["insurer_id"] = iid; sess["insurer_login"] = "r604insurer"
        sess["insurer_name"] = "R604보험사"; sess["_csrf"] = CSRF
    return c


def _partner_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["partner_id"] = pid; sess["partner_name"] = "R604업체"; sess["_csrf"] = CSRF
    return c


def _mk_defect(no, **extra):
    conn = DB.get_db()
    cols = dict(defect_no=no, case_id=cid, case_no="R604-CASE", partner_id=pid,
                title="테스트 하자", severity="보통", status="확인중",
                cost_bearer="시행사", resolution="초기 메모", due_date="2026-09-20",
                created_at=DB.now())
    cols.update(extra)
    keys = list(cols.keys())
    ph = ",".join("?" * len(keys))
    new_id = conn.execute(
        f"INSERT INTO defects({','.join(keys)}) VALUES({ph})",
        [cols[k] for k in keys]).lastrowid
    conn.commit(); conn.close()
    return new_id


# ==================================================================
print("\n[2] 실행(api_defect_create) — 보험사 포털이 title 을 숫자로, "
      "어드민이 content 를 숫자로 보내도 500 대신 200")
# ------------------------------------------------------------------
try:
    ins_c = _insurer_client()
    r1 = ins_c.post("/api/defects", headers=H,
                     json={"case_id": cid, "title": 20260912})
    rb1 = r1.get_json() or {}
    chk(r1.status_code == 200 and rb1.get("ok") is True,
        "★★★★★ 보험사 포털이 title 을 숫자로 보내도 500 대신 200(위 [0]이 없으면 "
        "이 요청이 옛 코드에서 500 이었음을 [6]이 실측 증명)", (r1.status_code, rb1))
    if rb1.get("ok"):
        row1 = DB.get_db().execute(
            "SELECT title FROM defects WHERE id=?", (rb1["id"],)).fetchone()
        chk(row1["title"] == "20260912",
            "STEP DB 에 title 이 문자열 '20260912' 로 저장됐다(숫자 그대로가 아님)",
            row1["title"] if row1 else None)

    admin_c = _admin_client()
    r2 = admin_c.post("/api/defects", headers=H,
                       json={"case_id": cid, "title": "콘텐츠필드검증604", "content": 887766})
    rb2 = r2.get_json() or {}
    chk(r2.status_code == 200 and rb2.get("ok") is True,
        "★★★★★ 어드민이 content 를 숫자로 보내도 500 대신 200", (r2.status_code, rb2))
    if rb2.get("ok"):
        row2 = DB.get_db().execute(
            "SELECT content FROM defects WHERE id=?", (rb2["id"],)).fetchone()
        chk(row2["content"] == "887766",
            "STEP DB 에 content 가 문자열 '887766' 으로 저장됐다",
            row2["content"] if row2 else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드604 [2] api_defect_create", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[3] 실행(api_defect_update) — resolution 숫자를 무상태변경/'반려'/"
      "귀책이의 세 경로 각각으로 보내도 500 대신 200")
# ------------------------------------------------------------------
try:
    admin_c = _admin_client()
    did_a = _mk_defect("R604-DF-A")
    r3 = admin_c.patch(f"/api/defects/{did_a}", headers=H, json={"resolution": 12345})
    rb3 = r3.get_json() or {}
    chk(r3.status_code == 200 and rb3.get("ok") is True,
        "★★★★★ (a) 상태변경 없이 resolution 숫자만 보내도 200"
        "(changed_fields 루프 — 옛 코드는 여기서 TypeError)", (r3.status_code, rb3))
    if rb3.get("ok"):
        rowA = DB.get_db().execute(
            "SELECT resolution FROM defects WHERE id=?", (did_a,)).fetchone()
        chk(rowA["resolution"] == "12345", "STEP DB 저장값이 문자열 '12345' 다",
            rowA["resolution"] if rowA else None)

    did_b = _mk_defect("R604-DF-B")
    r4 = admin_c.patch(f"/api/defects/{did_b}", headers=H,
                        json={"status": "반려", "resolution": 999})
    rb4 = r4.get_json() or {}
    chk(r4.status_code == 200 and rb4.get("ok") is True,
        "★★★★★ (b) status='반려' + resolution 숫자 — '반려' notify 조건에서도 "
        "500 대신 200(옛 코드는 여기서 AttributeError)", (r4.status_code, rb4))

    did_c = _mk_defect("R604-DF-C", dispute_reason="시공 부실 이의있음")
    r5 = admin_c.patch(f"/api/defects/{did_c}", headers=H,
                        json={"cost_bearer": "협의필요", "resolution": 555})
    rb5 = r5.get_json() or {}
    chk(r5.status_code == 200 and rb5.get("ok") is True,
        "★★★★★ (c) 귀책이의 처리(cost_bearer 변경) + resolution 숫자 — "
        "'하자이의처리' notify 조건에서도 500 대신 200", (r5.status_code, rb5))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드604 [3] api_defect_update", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[4] 실행(협력사 포털) — resolve 의 resolution 숫자, dispute 의 "
      "reason 숫자(짧은 값·긴 값)")
# ------------------------------------------------------------------
try:
    partner_c = _partner_client()
    did_d = _mk_defect("R604-DF-D", status="접수")
    r6 = partner_c.post(f"/api/partner/defects/{did_d}/resolve", headers=H,
                         json={"resolution": 424242})
    rb6 = r6.get_json() or {}
    chk(r6.status_code == 200 and rb6.get("ok") is True,
        "★★★★★ 협력사 재시공완료 보고 — resolution 숫자를 보내도 500 대신 200"
        "(옛 코드는 UPDATE 파라미터 계산에서 TypeError)", (r6.status_code, rb6))
    if rb6.get("ok"):
        rowD = DB.get_db().execute(
            "SELECT resolution, status FROM defects WHERE id=?", (did_d,)).fetchone()
        chk(rowD["resolution"] == "424242" and rowD["status"] == "확인중",
            "STEP DB 저장값이 문자열 '424242' 고 상태도 정상 전이(확인중)했다",
            dict(rowD) if rowD else None)

    did_e = _mk_defect("R604-DF-E", status="접수")
    r7 = partner_c.post(f"/api/partner/defects/{did_e}/dispute", headers=H,
                         json={"reason": 42})
    rb7 = r7.get_json() or {}
    chk(r7.status_code == 400 and rb7.get("ok") is False and "10자 이상" in (rb7.get("error") or ""),
        "★★★★ reason=42(문자열화하면 '42', 2자) — 500 이 아니라 원래 있던 "
        "'10자 이상' 400 검증이 정상 작동(과잉통과 아님)", (r7.status_code, rb7))

    did_f = _mk_defect("R604-DF-F", status="접수")
    r8 = partner_c.post(f"/api/partner/defects/{did_f}/dispute", headers=H,
                         json={"reason": 12345678901234})
    rb8 = r8.get_json() or {}
    chk(r8.status_code == 200 and rb8.get("ok") is True,
        "★★★★★ reason 이 문자열화하면 10자 이상인 숫자(14자) — 500 대신 200"
        "(옛 코드는 .strip() 자체에서 AttributeError, 길이검증 근처도 못 감)",
        (r8.status_code, rb8))
    if rb8.get("ok"):
        rowF = DB.get_db().execute(
            "SELECT dispute_reason FROM defects WHERE id=?", (did_f,)).fetchone()
        chk(rowF["dispute_reason"] == "12345678901234",
            "STEP DB 에 dispute_reason 이 문자열로 저장됐다",
            rowF["dispute_reason"] if rowF else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드604 [4] 협력사 포털", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[4B] 실행(api_partner_complete) — 협력사 시공완료보고의 memo 숫자도 "
      "500 대신 200(하자 서브시스템과 완전히 다른 함수 — 전수 재확인 중 발견)")
# ------------------------------------------------------------------
cid_pc = None
try:
    conn_pc = DB.get_db()
    cid_pc = conn_pc.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer,insurer_id,partner_id,"
        "                  partner_name,created_at) "
        "VALUES('R604-CASE-PC','시공중','가드레일','서울','R604보험사',?,?,'R604업체',?)",
        (iid, pid, DB.now())).lastrowid
    conn_pc.execute(
        "INSERT INTO photos(case_id,partner_id,uploader_role,rel_path,kind,review_status,"
        "                   created_at) "
        "VALUES(?,?,'협력사','r604/test.jpg','완료','승인',?)", (cid_pc, pid, DB.now()))
    conn_pc.commit(); conn_pc.close()

    partner_c3 = _partner_client()
    r13 = partner_c3.post(f"/api/partner/cases/{cid_pc}/complete", headers=H,
                           json={"memo": 135790})
    rb13 = r13.get_json() or {}
    chk(r13.status_code == 200 and rb13.get("ok") is True,
        "★★★★★ 협력사 시공완료보고 — memo 숫자를 보내도 500 대신 200"
        "(옛 코드는 슬라이스에서 TypeError)", (r13.status_code, rb13))
    if rb13.get("ok"):
        rowPC = DB.get_db().execute(
            "SELECT detail FROM activity_log WHERE action='시공 완료 보고' "
            "  AND detail LIKE 'R604-CASE-PC%'").fetchone()
        chk(bool(rowPC) and "135790" in rowPC["detail"],
            "STEP 감사로그에 memo 가 문자열 '135790' 으로 남았다",
            rowPC["detail"] if rowPC else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드604 [4B] api_partner_complete", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[5] 회귀 안전 — 정상 문자열 입력·기존 화이트리스트 검증은 "
      "지금 코드에서도 그대로 동작(과잉교정 없음)")
# ------------------------------------------------------------------
try:
    admin_c = _admin_client()
    did_g = _mk_defect("R604-DF-G")
    r9 = admin_c.patch(f"/api/defects/{did_g}", headers=H,
                        json={"resolution": "재시공 자재 재발주 완료"})
    rb9 = r9.get_json() or {}
    chk(r9.status_code == 200 and rb9.get("ok") is True,
        "STEP 정상 문자열 resolution 은 그대로 200", (r9.status_code, rb9))
    rowG = DB.get_db().execute(
        "SELECT resolution FROM defects WHERE id=?", (did_g,)).fetchone()
    chk(rowG["resolution"] == "재시공 자재 재발주 완료",
        "STEP 정상 문자열은 있는 그대로(공백 트리밍 외 변형 없이) 저장된다",
        rowG["resolution"] if rowG else None)

    r10 = admin_c.patch(f"/api/defects/{did_g}", headers=H, json={"severity": "터무니없음"})
    chk(r10.status_code == 400,
        "STEP severity 화이트리스트 검증은 그대로 400(과잉수정으로 안 풀림)", r10.status_code)

    r11 = admin_c.patch(f"/api/defects/{did_g}", headers=H, json={"cost_bearer": "터무니없음"})
    chk(r11.status_code == 400,
        "STEP cost_bearer 화이트리스트 검증도 그대로 400", r11.status_code)

    partner_c = _partner_client()
    did_h = _mk_defect("R604-DF-H", status="접수")
    r12 = partner_c.post(f"/api/partner/defects/{did_h}/dispute", headers=H,
                          json={"reason": "짧음"})
    chk(r12.status_code == 400,
        "STEP 정상 문자열이라도 10자 미만이면 그대로 400(길이검증 로직 안 바뀜)",
        r12.status_code)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드604 [5] 회귀 안전", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[6] 되돌리기 — app.py 파일은 안 건드리고 공용 헬퍼 A._s 만 '604 이전'"
      "(문자열 강제 없는 raw strip/slice) 버전으로 몽키패치해, 위 [2]~[4B] 와 "
      "정확히 같은 요청이 실제로 다시 500 이 되는지 확인 후 즉시 원복")
# ------------------------------------------------------------------
_real_s = A._s


def _s_pre604(v, n=None):
    """604 수정 직전의 _s() 호출부 부재 상황을 재현하는 몽키패치 전용 함수 —
       진짜 _s() 와의 유일한 차이는 str() 강제(isinstance 분기)가 없다는 것.
       그 한 줄 차이가 12곳의 크래시 여부를 가르는 인과관계임을 증명한다."""
    t = (v or "").strip()
    return t[:n] if n else t


try:
    A._s = _s_pre604

    ins_c2 = _insurer_client()
    rr1 = ins_c2.post("/api/defects", headers=H, json={"case_id": cid, "title": 111222})
    chk(rr1.status_code == 500,
        "★★★★★ 되돌리면(_s 무력화) 보험사 포털의 숫자 title 이 다시 500",
        rr1.status_code)

    admin_c2 = _admin_client()
    did_r1 = _mk_defect("R604-DF-REV1")
    rr2 = admin_c2.patch(f"/api/defects/{did_r1}", headers=H, json={"resolution": 321})
    chk(rr2.status_code == 500,
        "★★★★★ 되돌리면 api_defect_update 의 숫자 resolution(무상태변경)도 다시 500",
        rr2.status_code)

    did_r2 = _mk_defect("R604-DF-REV2")
    rr3 = admin_c2.patch(f"/api/defects/{did_r2}", headers=H,
                          json={"status": "반려", "resolution": 321})
    chk(rr3.status_code == 500,
        "★★★★★ 되돌리면 '반려' notify 조건의 숫자 resolution 도 다시 500",
        rr3.status_code)

    partner_c2 = _partner_client()
    did_r3 = _mk_defect("R604-DF-REV3", status="접수")
    rr4 = partner_c2.post(f"/api/partner/defects/{did_r3}/resolve", headers=H,
                           json={"resolution": 321})
    chk(rr4.status_code == 500,
        "★★★★★ 되돌리면 협력사 재시공완료 보고의 숫자 resolution 도 다시 500",
        rr4.status_code)

    did_r4 = _mk_defect("R604-DF-REV4", status="접수")
    rr5 = partner_c2.post(f"/api/partner/defects/{did_r4}/dispute", headers=H,
                           json={"reason": 12345678901234})
    chk(rr5.status_code == 500,
        "★★★★★ 되돌리면 협력사 귀책이의(긴 숫자 reason)도 다시 500",
        rr5.status_code)

    conn_pc2 = DB.get_db()
    cid_pc2 = conn_pc2.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer,insurer_id,partner_id,"
        "                  partner_name,created_at) "
        "VALUES('R604-CASE-PC-REV','시공중','가드레일','서울','R604보험사',?,?,'R604업체',?)",
        (iid, pid, DB.now())).lastrowid
    conn_pc2.execute(
        "INSERT INTO photos(case_id,partner_id,uploader_role,rel_path,kind,review_status,"
        "                   created_at) "
        "VALUES(?,?,'협력사','r604/rev.jpg','완료','승인',?)", (cid_pc2, pid, DB.now()))
    conn_pc2.commit(); conn_pc2.close()
    rr6 = partner_c2.post(f"/api/partner/cases/{cid_pc2}/complete", headers=H,
                           json={"memo": 246810})
    chk(rr6.status_code == 500,
        "★★★★★ 되돌리면 협력사 시공완료보고의 숫자 memo 도 다시 500",
        rr6.status_code)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드604 [6] 되돌리기", f"{type(e).__name__} {e}")
finally:
    A._s = _real_s

# 되돌리기 절차 동안 진짜 app.py 파일은 전혀 건드리지 않았음을 해시로 확인
APP_HASH_AFTER = hashlib.sha256(read("app.py").encode("utf-8")).hexdigest()
chk(APP_HASH_BEFORE == APP_HASH_AFTER,
    "★★★★★ 되돌리기 절차 동안 app.py 파일 내용이 전혀 안 바뀌었다"
    "(몽키패치만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

# 원복 확인 — 같은 요청이 다시 정상(200)으로 돌아오는지
try:
    admin_c3 = _admin_client()
    did_z = _mk_defect("R604-DF-Z")
    rz = admin_c3.patch(f"/api/defects/{did_z}", headers=H, json={"resolution": 777})
    rbz = rz.get_json() or {}
    chk(rz.status_code == 200 and rbz.get("ok") is True,
        "★★★★★ A._s 원복 후 같은 요청이 다시 정상(200)으로 돌아온다", (rz.status_code, rbz))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드604 원복 확인", f"{type(e).__name__} {e}")


# ==================================================================
# 정리
# ------------------------------------------------------------------
os.environ.pop("BOKGUON_DB_PATH", None)
os.environ.pop("BOKGUON_UPLOAD_DIR", None)
os.environ.pop("BOKGUON_LOG_FILE", None)
os.environ.pop("BOKGUON_ENV", None)
os.environ.pop("BOKGUON_SEED_DEMO", None)
shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
