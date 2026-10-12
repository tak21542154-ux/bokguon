# -*- coding: utf-8 -*-
"""스캔 553라운드 회귀 — 입점신청 직접접수(api_application_create)의 중복확인이
   BEGIN IMMEDIATE 없이 read-then-write 라 동시 접수 시 대기 신청서가 중복
   생성되던 결함.

   조사 배경 — round550이 app.py 의 POST/PATCH/DELETE 라우트 145개를 AST로
   전수조사해 "SELECT 로 읽고 쓰기까지 하면서 BEGIN IMMEDIATE 가 없는 곳"을
   21개 후보로 추렸다. 그중 20개는 이미 다른 라운드가 막았거나, 실제로 활성
   업체를 만드는 최종 관문(api_application_update)이 대신 막고 있어 안전하다고
   판단해 통과시켰지만, api_application_create(입점 신청 직접접수, "전화·팩스·
   영업으로 받은 업체를 담당자가 대신 등록") 하나만은 "이론적으로는 동시 접수
   시 중복 대기건이 생길 수 있어 보이나 ... 이번 라운드는 이 항목을 고치지
   않고 다음 라운드 조사거리로만 남긴다"고 round550 자신의 기록(run_all_tests.py
   등록 문구)에 명시적으로 남아 있었다 — 오케스트레이터가 이번 라운드에 준
   "이미 닫힌 각도" 목록에서도 이 함수만 예외로 적혀 있다. 이번 라운드가 그
   항목을 직접 조사해 실제로 재현·수정했다.

   결함(수정 전 app.py:7730-7743, api_application_create) — 업체명 중복확인
   (SELECT ... FROM partner_applications WHERE company=? AND status IN
   ('신규','서류검토'))과 사업자번호 교차확인(SELECT ... FROM partners WHERE
   biz_no=? AND status='활성') 둘 다 BEGIN IMMEDIATE 없이 그냥 conn.execute()
   로 조회한 뒤, 결과가 없으면 그대로 INSERT 했다. 이 라우트 자체가 여러 담당자
   (전화 상담원)가 같은 화면으로 동시에 접수하는 것을 전제로 하는데, 같은 업체를
   두 사람이 거의 동시에 접수하거나 화면에서 이중 클릭하면 두 요청 모두 "심사
   중인 신청 없음"을 읽어 둘 다 INSERT 에 성공한다 — 같은 업체의 대기 신청서가
   2건 생긴다.

   영향 범위(과장하지 않는다) — 활성 협력사 중복까지는 번지지 않는다. 실제로
   활성 업체를 만드는 유일한 관문인 api_application_update() 는 이미
   round189/248/429 가 BEGIN IMMEDIATE + DUP_BIZNO 검사로 막아 뒀다(아래 [0]
   에서 이번 라운드가 안 건드렸음을 재확인). 그래서 이 결함의 실제 피해는
   "같은 업체의 대기 신청서 2건"에 그친다 — 정산·입찰 자격이 갈라지는 심각한
   결과는 아니고, 담당자가 심사함에서 중복 신청서 두 건을 보고 헷갈리거나 감사
   추적에 잡음이 남는 운영상 문제다.

   고침 — 새 헬퍼 없이, 바로 아래(app.py:7780, 이 파일 안에서 몇 줄 뒤)의 형제
   api_application_update() 가 이미 쓰는 것과 정확히 같은 자리·같은 방식을
   그대로 옮겼다: conn = DB.get_db() 직후 conn.execute("BEGIN IMMEDIATE") 를
   추가하고, 두 중복확인의 조기 반환 두 곳 모두 conn.close() 를
   conn.rollback(); conn.close() 로 바꿨다. 사이에 있는 _picked_coords(d) 호출은
   순수 계산(디스크·네트워크 I/O 없음)이라 잠금을 오래 쥐지 않는다 — 이미 이
   파일의 다른 145개 라우트가 증명한 것과 같은 전제.

   테스트 기법 — [3]/[4]는 threading.Barrier 로 두 요청을 동기화하고,
   _picked_coords() 에 테스트 전용 인위적 지연(0.25초)을 monkeypatch 로 걸어
   "잠금을 쥔 채 대기하는 창"을 결정론적으로 넓힌다(실제 코드는 건드리지 않고
   테스트 안에서만 지연을 주입 — 회귀 재현이 스레드 스케줄링 운에 좌우되지
   않게 하기 위함). app.py·run_all_tests.py 파일은 이 지연 주입과 무관하게
   전혀 손대지 않는다. [4]의 "옛 코드"는 이 세션이 수정 **직전** Read 로 확인한
   원문을 문자열로 재구성해 exec() 한 것이다(round543·547·549·550 과 같은 기법
   — 실제 on-disk .py 파일은 절대 건드리지 않는다).

      python test_scan_round553_fixes.py
"""
import io
import os
import sys
import tempfile
import threading
import time

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
    end = src.find("\n@app.", start + 1)
    return src[start:end if end != -1 else None]


print("=" * 72)
print("  스캔 553라운드 회귀 — 입점신청 직접접수 중복확인 TOCTOU(대기 신청서 중복생성)")
print("=" * 72)

APP_SRC = read("app.py")

# ==================================================================
print("\n[0] 소스 — 고친 지점이 실제로 app.py 에 있는가"
      "(동시편집 세션이 되돌렸다면 여기서부터 정직하게 실패해야 한다)")
# ------------------------------------------------------------------
try:
    import ast as _ast
    chk(_ast.parse(APP_SRC) is not None, "STEP app.py 전체 ast.parse 성공")

    fn_body = _py_fn_body(APP_SRC, "api_application_create")
    chk("BEGIN IMMEDIATE" in fn_body,
        "★★★★★ api_application_create() 안에 BEGIN IMMEDIATE 가 있다"
        "(고치기 전엔 이 토큰이 없었다)")
    _i_begin = fn_body.index("BEGIN IMMEDIATE")
    #  ⚠ [라운드689] 앵커를 "SELECT id, status" 접두사까지로 좁혔다 — round688 이
    #    같은 SELECT 에 company 컬럼을 더하면서("SELECT id, status, company FROM
    #    partner_applications", NFKC 정규화 대조로 전환) 옛 리터럴 전체가 사라져
    #    이 줄이 ValueError: substring not found 로 죽었다. 이 검사의 의도는
    #    "잠금이 중복확인 조회보다 앞에 있다" 하나뿐이고 컬럼 목록은 그 의도와
    #    무관하므로, 컬럼이 더 늘어도 견디는 접두사로 고정한다(이 함수 본문에
    #    1회만 등장함을 round689 가 실측 확인).
    _i_dupsel = fn_body.index("SELECT id, status")
    chk(_i_begin < _i_dupsel,
        "STEP BEGIN IMMEDIATE 가 업체명 중복확인 SELECT 보다 앞에 있다(조회 전에 잠근다)")
    _n_rb = fn_body.count("conn.rollback(); conn.close()")
    chk(_n_rb == 2,
        "★★★★ 두 중복확인(업체명·사업자번호) 조기반환 모두 rollback 후 close 로 "
        "바뀌었다(형제 api_application_update 와 같은 관례)", _n_rb)
    #  ⚠ "conn.close()"라는 문자열 자체는 3번 나온다 — 두 rollback 줄에 각각
    #    하나씩(합쳐서 "conn.rollback(); conn.close()"), 그리고 맨 끝 성공
    #    경로에 단독으로 하나. 잠금 연 채 나가던 옛 방식(rollback 없는 단독
    #    conn.close())이 남아있지 않은지는 위 _n_rb==2 검사가 이미 증명한다
    #    (조기반환 두 곳 전부가 그 짝 문자열이므로, 단독으로 남은 close 는
    #    성공 경로 1개뿐이어야 한다).
    chk(fn_body.count("conn.close()") == 3,
        "STEP conn.close() 총 등장 횟수는 3(rollback 짝 2 + 성공경로 단독 1)",
        fn_body.count("conn.close()"))
    chk("conn.commit()" in fn_body,
        "STEP 성공 경로는 그대로 commit 뒤 close 한다(회귀 없음)")

    # 형제(api_application_update)는 이번 라운드가 손대지 않았다 — 그대로인지 대조.
    sib_body = _py_fn_body(APP_SRC, "api_application_update")
    chk(sib_body.count("BEGIN IMMEDIATE") == 1,
        "STEP 형제 api_application_update() 의 BEGIN IMMEDIATE 는 그대로 1곳이다"
        "(round189/248/429 가 이미 막아 둔 최종 관문 — 이번에 안 건드림)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드553 [0] 소스 확인", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[1] 준비 — 격리 스크래치 DB · 관리자 세션")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round553_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r553-csrf"
A = DB = None

try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('admin553','x','실행계정553','최고관리자')")
    conn0.commit(); conn0.close()
    chk(True, "STEP 스크래치 DB·관리자 계정 준비 완료")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드553 [1] 준비", f"{type(e).__name__} {e}")


def _call_with_session(fn, payload, path="/api/applications/manual"):
    """fn 을 관리자 세션이 실린 test_request_context 안에서 호출하고 (status, json) 을 돌려준다."""
    with A.app.test_request_context(path, method="POST", json=payload):
        from flask import session as _s
        _s["admin"] = "admin553"
        _s["admin_name"] = "실행계정553"
        _s["admin_role"] = "최고관리자"
        _s["_csrf"] = CSRF
        resp = fn()
    if isinstance(resp, tuple):
        resp_obj, code = resp[0], resp[1]
    else:
        resp_obj, code = resp, 200
    return code, resp_obj.get_json()


# ==================================================================
print("\n[2] 순차 회귀 안전 — 동시성이 없을 때는 지금까지와 똑같이 동작하는가"
      "(업체명 중복·사업자번호 교차확인 둘 다)")
# ------------------------------------------------------------------
try:
    p1 = {"company": "R553순차업체", "major": "가드레일·방호울타리", "phone": "010-1111-2222"}
    code1, body1 = _call_with_session(A.api_application_create, p1)
    chk(code1 == 200 and body1.get("ok") is True,
        "STEP 첫 접수는 정상적으로 200·ok:true", (code1, body1))

    code2, body2 = _call_with_session(A.api_application_create, p1)
    chk(code2 == 409 and body2.get("ok") is False
        and "이미 심사 중인 신청이 있습니다" in (body2.get("error") or ""),
        "STEP 같은 업체명을 순차로 다시 접수하면 여전히 409(회귀 없음)", (code2, body2))

    conn = DB.get_db()
    conn.execute("INSERT INTO partners(name,biz_no,status) VALUES('R553기존업체','1234567891','활성')")
    conn.commit(); conn.close()
    #  ⚠ "123-45-67891" 은 valid_biz_no() 의 국세청 검사식을 실제로 통과하는 값이다
    #    (자릿수만 맞춘 임의값이면 형식오류 400 에 먼저 걸려 이 테스트가 뜻하는
    #    지점까지 못 간다). 숫자만 남기면 위 partners.biz_no 와 정확히 같은
    #    '1234567891' 이어야 교차확인이 실제로 매칭된다.
    p2 = {"company": "R553새이름", "major": "유리·샷시·자동문", "biz_no": "123-45-67891"}
    code3, body3 = _call_with_session(A.api_application_create, p2)
    chk(code3 == 409 and "이미 등록된 업체입니다" in (body3.get("error") or "")
        and "R553기존업체" in (body3.get("error") or ""),
        "STEP 사업자번호 교차확인도 순차 상황에서는 여전히 409(회귀 없음, "
        "Markup 이스케이프 문구도 형태 그대로)", (code3, body3))

    n = DB.get_db().execute(
        "SELECT COUNT(*) c FROM partner_applications WHERE company='R553순차업체'").fetchone()["c"]
    chk(n == 1, "STEP 순차 상황에서는 대기 신청서가 정확히 1건만 쌓인다(중복 아님)", n)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드553 [2] 순차 회귀 안전", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[3]+[4] 실제 동시접수 — 지금 코드는 정확히 하나만 성공시키는가, "
      "옛 코드(재구성)는 정말 둘 다 성공시켜 버리는가")
# ------------------------------------------------------------------
_orig_picked_coords = A._picked_coords


def _slow_picked_coords(d):
    #  ⚠ 테스트 전용 인위적 지연 — 실제 코드에는 없다. 두 접수 요청이 "동시에
    #    도달"했다고 부를 수 있는 겹침 구간을 결정론적으로 만들기 위한 조치다
    #    (스레드 스케줄링에 우연히 기대면 라운드마다 통과/실패가 흔들린다).
    time.sleep(0.25)
    return _orig_picked_coords(d)


def _race(fn, company, n=2):
    barrier = threading.Barrier(n)
    results = [None] * n

    def _worker(idx):
        payload = {"company": company, "major": "가드레일·방호울타리", "phone": "010-9999-0000"}
        try:
            barrier.wait(timeout=5)
            results[idx] = _call_with_session(fn, payload)
        except Exception as e:                                      # noqa: BLE001
            results[idx] = ("EXC", f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    return results


try:
    A._picked_coords = _slow_picked_coords

    # ── [3] 지금 코드(실제 함수, 실제 라우트가 그대로 참조하는 그 객체) ──
    res_new = _race(A.api_application_create, "R553동시접수업체", 2)
    codes_new = sorted(str(r[0]) for r in res_new)
    chk(codes_new == ["200", "409"],
        "★★★★★ 지금 코드: 동시에 부딪힌 두 접수 중 정확히 하나만 200(성공), "
        "나머지 하나는 409(중복)다", res_new)
    n_new = DB.get_db().execute(
        "SELECT COUNT(*) c FROM partner_applications WHERE company='R553동시접수업체'"
    ).fetchone()["c"]
    chk(n_new == 1,
        "★★★★★ 지금 코드: 동시 접수 뒤에도 대기 신청서는 정확히 1건이다"
        "(옛 코드는 바로 아래 [4]에서 2건이 생김을 실측한다)", n_new)

    # ── [4] 원인 재현 — 수정 직전(이 세션이 Read 로 확인한 원문) 함수 본문을
    #    문자열로 재구성해(exec) 같은 동시접수를 실행한다. app.py·
    #    run_all_tests.py 는 이 과정에서 전혀 건드리지 않는다.
    _PRE553_SRC = '''
def _api_application_create_pre553():
    d = body()
    company = (d.get("company") or "").strip()
    if not company:
        return jsonify({"ok": False, "error": "업체명은 필수입니다."}), 400
    if not d.get("major"):
        return jsonify({"ok": False, "error": "주력 공종을 선택해 주세요."}), 400
    ptype = d.get("partner_type") if d.get("partner_type") in PARTNER_TYPES else "시공사"
    try:
        staff_n = int(d.get("staff_count")) if str(d.get("staff_count", "")).strip() else None
    except (TypeError, ValueError):
        staff_n = None
    if d.get("solo") is True or (staff_n is not None and staff_n < 1):
        return jsonify({"ok": False, "code": "SOLO",
                        "error": "1인 사업자(대표 외 상시 인력 없음)는 입점 대상이 아닙니다."}), 400
    biz = (d.get("biz_no") or "").strip()[:20]
    if biz and not valid_biz_no(biz):
        return jsonify({"ok": False,
                        "error": "사업자등록번호가 올바르지 않습니다. "
                                 "10자리 숫자를 다시 확인해 주세요."}), 400
    biz = re.sub(r"[^0-9]", "", biz)
    _phone = (d.get("phone") or "").strip()
    if _phone and not RE_PHONE.match(_phone):
        return jsonify({"ok": False,
                        "error": f"연락처 형식이 올바르지 않습니다: {_phone}"}), 400
    _email = (d.get("email") or "").strip()
    if _email and not RE_EMAIL.match(_email):
        return jsonify({"ok": False,
                        "error": f"이메일 형식이 올바르지 않습니다: {_email}"}), 400
    conn = DB.get_db()
    dup = one(conn.execute(
        "SELECT id, status FROM partner_applications WHERE company=? "
        "AND status IN ('신규','서류검토') ORDER BY id DESC", (company,)))
    if dup:
        conn.close()
        return jsonify({"ok": False,
                        "error": f"이미 심사 중인 신청이 있습니다. (#{dup['id']} · {dup['status']})"}), 409
    if biz:
        pdup = one(conn.execute(
            "SELECT name FROM partners WHERE biz_no=? AND status='활성'", (biz,)))
        if pdup:
            conn.close()
            return jsonify({"ok": False,
                            "error": str(Markup(
                                "이미 등록된 업체입니다. (사업자번호 일치: {}) "
                                "업체 등록·관리에서 확인하세요.").format(escape(pdup["name"])))}), 409
    _alat, _alng = _picked_coords(d)
    cur = conn.execute(
        """INSERT INTO partner_applications(company,biz_no,ceo,major,category,region,address,phone,
           email,has_license,has_insurance,message,status,partner_type,staff_count,source,created_at,
           lat,lng)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (company, biz, (d.get("ceo") or "").strip()[:40],
         d["major"], (d.get("category") or "").strip()[:120], (d.get("region") or "").strip()[:40],
         (d.get("address") or "").strip()[:200],
         (d.get("phone") or "").strip()[:20], (d.get("email") or "").strip()[:80],
         1 if d.get("has_license") else 0, 1 if d.get("has_insurance") else 0,
         (d.get("message") or "").strip()[:500], "신규", ptype, staff_n, "직접접수", DB.now(),
         _alat, _alng))
    DB.log(conn, actor(), "입점신청 직접접수", f"{company} ({ptype})")
    conn.commit()
    aid = cur.lastrowid
    conn.close()
    return jsonify({"ok": True, "id": aid})
'''
    _ns = dict(vars(A))          # app 모듈 네임스페이스 복사(진짜 모듈은 안 건드림)
    #  ⚠ 위에서 A._picked_coords 를 이미 slow 버전으로 바꿔 뒀으므로 이 복사본에도
    #    slow 버전이 담긴다 — 옛 코드도 지금 코드와 같은 지연 조건에서 겨룬다.
    exec(compile(_PRE553_SRC, "<round553_pre_reconstructed>", "exec"), _ns)
    old_fn = _ns["_api_application_create_pre553"]

    res_old = _race(old_fn, "R553구코드동시접수", 2)
    codes_old = sorted(str(r[0]) for r in res_old)
    chk(codes_old == ["200", "200"],
        "★★★★★ 옛 코드(재구성): 동시에 부딪힌 두 접수가 둘 다 200으로 성공해버린다 "
        "— 지금 코드(위 [3])는 같은 시나리오에서 정확히 하나만 성공했다. 이 차이가 "
        "이 회귀가 결함을 실제로 잡아낼 능력이 있다는 인과관계 증명이다", res_old)
    n_old = DB.get_db().execute(
        "SELECT COUNT(*) c FROM partner_applications WHERE company='R553구코드동시접수'"
    ).fetchone()["c"]
    chk(n_old == 2,
        "★★★★★ 옛 코드(재구성): 동시 접수 뒤 대기 신청서가 실제로 2건 생긴다"
        "(지금 코드는 위 [3]에서 1건이었다) — 결함이 실재했음을 실측으로 증명", n_old)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드553 [3]+[4] 동시접수 실행/원인재현", f"{type(e).__name__} {e}")
finally:
    A._picked_coords = _orig_picked_coords
    chk(A._picked_coords is _orig_picked_coords, "STEP _picked_coords 원상복구 완료(다른 테스트 오염 방지)")


# ==================================================================
# 정리
# ------------------------------------------------------------------
os.environ.pop("BOKGUON_DB_PATH", None)
os.environ.pop("BOKGUON_ENV", None)
os.environ.pop("BOKGUON_SEED_DEMO", None)
try:
    import shutil as _shutil
    _shutil.rmtree(_tmpdir, ignore_errors=True)
except Exception:
    pass

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
