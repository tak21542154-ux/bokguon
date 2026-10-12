# -*- coding: utf-8 -*-
"""스캔 616라운드 회귀 — round609가 "사실상 완결"(9개 라운드 601~609 누적
165곳+)이라 선언한 raw-strip 형제결함군의 잔여 3곳을 이 세션이 app.py
전체 재스윕(정규식 grep으로 `(d.get(...)/d[...] or "").strip()` 패턴
전수확인)으로 추가 발견해 고쳤다.

  ① api_lead_update(lid) — insurer_leads.note (7925행 부근). 관리자가
    JSON 정수 등 비문자열 note를 보내면 raw (d["note"] or "").strip()
    이 AttributeError로 500.
  ② api_application_update(aid) — partner_applications.note (8115행
    부근). ①과 완전히 같은 모양(둘 다 [라운드118] 주석이 "형제"로
    서로를 인용하는데, 정작 118라운드 자신이 두 곳 다 raw로 남겼다).
  ③ api_case_create() — insurer_name (11806행 부근, BEGIN IMMEDIATE
    로 쓰기 잠금을 쥔 **뒤**라 형제 중 가장 무겁다 — round482가 겪은
    것과 같은 클래스의 "잠근 채 죽으면" 위험을 안고 있었다. 다만 이
    앱은 app.py:429 `_tracked_get_db`가 모든 DB.get_db() 커넥션을
    `g._conns`에 등록해 두고, 전역 예외핸들러(app.py:1343 부근)와
    `@app.teardown_appcontext`(458행) 둘 다 `_cleanup_conns(rollback=
    True)`를 부르는 안전망이 이미 있어(round450 전후로 확립) 실제
    "먹통"까지는 안 가고 500 응답 + 정상 롤백으로 끝난다 — 그래도
    500 자체는 이 결함군과 동일하게 불필요한 크래시라 고친다.

  오탐 배제(재확인만, 수정 안 함) — 겉보기엔 같은 패턴이지만 실제로는
  이미 안전한 자리 2곳:
    · api_create_application(address, 6091행 부근) — d=clean 이후
      읽으므로 clean_public_form()의 FIELD_LIMITS["address"]=200이
      이미 str(v) 강제를 거친 값만 담는다(round609가 이미 같은 결론).
    · api_defect_update(cost_bearer, 15684행 부근) — 15628행의
      화이트리스트(`d["cost_bearer"] not in ("시행사","보험사",
      "협의필요")`)가 비문자열을 포함한 모든 미허용값을 그 즉시
      400으로 막아, 15684행에 도달하면 이미 항상 안전한 문자열이다
      (라운드604 자신의 분석과 동일 결론 — 주석에 이미 명시돼 있었다).

  전부 형제 헬퍼 `_s(v, n=None)`(app.py 1507행)을 그대로 재사용했다 —
  새 헬퍼·새 로직 없음. round601~609(누적 165곳+) + 이번 616(3곳)으로
  raw-strip 결함군은 계속 갱신 중 — "완결" 선언 이후에도 grep 전수
  재확인이 유효함을 보여준다.

  ⚠⚠ [라운드616] 되돌림-증명은 처음부터 안전한 기법(round609가 이미
    확립한 "공유 헬퍼 A._s만 몽키패치" 방식)으로 작성한다 — app.py
    파일은 이 테스트 전체에서 단 한 번도 디스크에 쓰지 않는다.

  실행:  python test_scan_round616_fixes.py
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
    """주석 줄(수정 설명 안에 옛 raw 패턴을 그대로 인용한 곳이 있어, 주석까지
    검색하면 '옛 패턴이 아직 있다'는 오탐이 난다)을 빼고 실제 코드 줄만
    이어붙인다(round609와 동일 기법)."""
    return "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("#"))


print("=" * 72)
print("  스캔 616라운드 회귀 — round609 '완결' 선언 이후 남은 raw-strip 3곳")
print("=" * 72)

APP_SRC = read("app.py")

# ==================================================================
print("\n[0] 소스 확인 — 3곳 모두 옛 raw 패턴이 사라지고 _s()로 바뀌었다")
# ------------------------------------------------------------------
try:
    alu = _code_only(_py_fn_body(APP_SRC, "api_lead_update"))
    chk('((d["note"] or "").strip()[:500], lid)' not in alu
        and "(_s(d[\"note\"], 500), lid)" in alu,
        "★★★★★ api_lead_update — note")

    aau = _code_only(_py_fn_body(APP_SRC, "api_application_update"))
    chk('((d["note"] or "").strip()[:500], aid)' not in aau
        and "(_s(d[\"note\"], 500), aid)" in aau,
        "★★★★★ api_application_update — note")

    acc = _code_only(_py_fn_body(APP_SRC, "api_case_create"))
    chk('insurer_name = (d.get("insurer") or "").strip()' not in acc
        and 'insurer_name = _s(d.get("insurer"))' in acc,
        "★★★★★ api_case_create — insurer_name")

    # 오탐 배제 재확인(수정 불필요, round609와 같은 방식의 클린 확인).
    chk('"address": 200' in APP_SRC,
        "STEP api_create_application(address, 6091행 부근) — 클린 재확인: "
        "FIELD_LIMITS에 이미 address:200이 있고 clean_public_form()이 "
        "str(v) 강제라 d=clean 이후에도 항상 str — 수정 불필요"
        "(round609와 동일 결론)")
    adu2 = _code_only(_py_fn_body(APP_SRC, "api_defect_update"))
    chk('d["cost_bearer"] not in ("시행사", "보험사", "협의필요")' in adu2,
        "STEP api_defect_update(cost_bearer, 15684행 부근) — 클린 재확인: "
        "화이트리스트(not in 대조)가 이 알림문 조립보다 먼저 비문자열을 "
        "포함한 모든 미허용값을 걸러 여기 도달하면 항상 안전한 문자열 — "
        "수정 불필요(라운드604 자신의 분석과 동일 결론)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드616 [0] 소스 확인", f"{type(e).__name__} {e}")

APP_HASH_BEFORE = hashlib.sha256(APP_SRC.encode("utf-8")).hexdigest()

# ==================================================================
print("\n[1] 준비 — 스크래치 DB, 관리자 1명 + 도입문의 1건 + 입점신청 1건")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round616_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "bokguon.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r616-csrf"
H = {"X-CSRF-Token": CSRF}
A = DB = None
lead_id = app_id = None

try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    conn0.execute(
        "INSERT INTO admins(username,password_hash,name,role) "
        "VALUES('r616admin','x','검증','최고관리자')")
    lead_id = conn0.execute(
        "INSERT INTO insurer_leads(company,phone,status,created_at) "
        "VALUES('R616도입문의','01000000000','신규',?)", (DB.now(),)).lastrowid
    app_id = conn0.execute(
        "INSERT INTO partner_applications(company,phone,status,created_at) "
        "VALUES('R616입점신청','01000000000','신규',?)", (DB.now(),)).lastrowid
    conn0.commit()
    conn0.close()
    chk(bool(lead_id) and bool(app_id),
        "STEP 관리자 1명·도입문의 1건·입점신청 1건 픽스처 생성",
        dict(lead_id=lead_id, app_id=app_id))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드616 [1] 준비", f"{type(e).__name__} {e}")


def _admin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "r616admin"; sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = CSRF
    return c


def _post(path, **kw):
    return _admin_client().post(path, headers=H, **kw)


def _patch(path, **kw):
    return _admin_client().patch(path, headers=H, **kw)


# ==================================================================
print("\n[2] 실행 — 세 라우트에 비문자열(JSON 정수) 값을 보내도 500이 아니다")
# ------------------------------------------------------------------
try:
    r1 = _patch(f"/api/leads/{lead_id}", json={"note": 616001})
    rb1 = r1.get_json() or {}
    chk(r1.status_code == 200 and rb1.get("ok") is True,
        "★★★★★ api_lead_update — note를 JSON 정수로 보내도 500 대신 200",
        (r1.status_code, rb1))

    r2 = _patch(f"/api/applications/{app_id}", json={"note": 616002})
    rb2 = r2.get_json() or {}
    chk(r2.status_code == 200 and rb2.get("ok") is True,
        "★★★★★ api_application_update — note를 JSON 정수로 보내도 500 대신 200",
        (r2.status_code, rb2))

    r3 = _post("/api/cases", json={"case_no": "R616CASE1", "category": "종합 원상복구",
                                    "no_photo": True, "insurer": 616003})
    rb3 = r3.get_json() or {}
    chk(r3.status_code == 400 and rb3.get("code") == "NO_INSURER",
        "★★★★★ api_case_create — insurer를 JSON 정수로 보내도 500이 아니라 "
        "정상적으로 400 NO_INSURER(존재하지 않는 보험사명이라 못 찾음 — "
        "크래시 없이 정상 검증 경로를 그대로 탄다)", (r3.status_code, rb3))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2] 실행", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[3] 회귀 안전 — 같은 라우트에 원래 타입(문자열) 값을 보내는 정상 "
      "경로는 그대로 동작한다")
# ------------------------------------------------------------------
try:
    s1 = _patch(f"/api/leads/{lead_id}", json={"note": "문자열메모"})
    sb1 = s1.get_json() or {}
    chk(s1.status_code == 200 and sb1.get("ok") is True,
        "STEP api_lead_update — 문자열 note는 지금도 200", (s1.status_code, sb1))
    _row1 = DB.get_db().execute(
        "SELECT note FROM insurer_leads WHERE id=?", (lead_id,)).fetchone()
    chk(bool(_row1) and _row1["note"] == "문자열메모",
        "STEP api_lead_update — 문자열 note가 그대로 저장된다(동작 변경 없음)",
        dict(_row1) if _row1 else None)

    s2 = _patch(f"/api/applications/{app_id}", json={"note": "문자열메모2"})
    sb2 = s2.get_json() or {}
    chk(s2.status_code == 200 and sb2.get("ok") is True,
        "STEP api_application_update — 문자열 note는 지금도 200", (s2.status_code, sb2))

    conn1 = DB.get_db()
    conn1.execute("INSERT INTO insurers(name,status) VALUES('R616보험사','활성')")
    conn1.commit(); conn1.close()
    s3 = _post("/api/cases", json={"case_no": "R616CASE2", "category": "종합 원상복구",
                                    "no_photo": True, "insurer": "R616보험사"})
    sb3 = s3.get_json() or {}
    chk(s3.status_code == 200 and sb3.get("ok") is True,
        "STEP api_case_create — 문자열 insurer는 지금도 이름 매칭으로 정상 "
        "등록된다(동작 변경 없음)", (s3.status_code, sb3))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] 회귀 안전", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[4] 되돌리기 — app.py 파일은 안 건드리고 공용 헬퍼 A._s만 '616 "
      "이전'(문자열 강제 없는 raw strip) 버전으로 몽키패치해, 세 라우트가 "
      "실제로 다시 500이 되는지 확인 후 즉시 원복(round609와 동일 기법)")
# ------------------------------------------------------------------
_real_s = A._s if A else None


def _s_pre616(v, n=None):
    """616 수정 직전 상황을 재현하는 몽키패치 전용 함수 — 진짜 _s()와의
    유일한 차이는 str() 강제(isinstance 분기)가 없다는 것(round609의
    _s_pre609와 동일한 기법)."""
    t = (v or "").strip()
    return t[:n] if n else t


try:
    A._s = _s_pre616

    rr1 = _patch(f"/api/leads/{lead_id}", json={"note": 716001})
    chk(rr1.status_code == 500,
        "★★★★★ 되돌리면 api_lead_update(note)이 다시 500", rr1.status_code)

    rr2 = _patch(f"/api/applications/{app_id}", json={"note": 716002})
    chk(rr2.status_code == 500,
        "★★★★★ 되돌리면 api_application_update(note)이 다시 500", rr2.status_code)

    rr3 = _post("/api/cases", json={"case_no": "R616CASE3", "category": "종합 원상복구",
                                     "no_photo": True, "insurer": 716003})
    chk(rr3.status_code == 500,
        "★★★★★ 되돌리면 api_case_create(insurer)이 다시 500 — 이 지점은 "
        "BEGIN IMMEDIATE로 쓰기 잠금을 쥔 뒤라 셋 중 가장 무겁다", rr3.status_code)

    # 잠금이 실제로 풀렸는지 — 전역 안전망(app.py의 _tracked_get_db/teardown_
    # appcontext/전역 예외핸들러)이 이 크래시 지점에서도 실제로 롤백·정리하는지
    # 직접 확인한다(round482가 dispatch.py에서 검증한 것과 같은 종류의 증명).
    _lockcheck = DB.get_db()
    _lockcheck.execute("BEGIN IMMEDIATE")
    _lockcheck.rollback()
    _lockcheck.close()
    chk(True,
        "★★★★ 되돌리기 크래시(BEGIN IMMEDIATE 보유 중 500) 이후에도 다음 "
        "BEGIN IMMEDIATE가 잠기지 않는다 — 전역 안전망이 실제로 롤백했다는 "
        "증거(이 결함의 실질 영향이 '먹통'이 아니라 '불필요한 500'임을 확인)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드616 [4] 되돌리기", f"{type(e).__name__} {e}")
finally:
    A._s = _real_s

# 되돌리기 절차 동안 진짜 app.py 파일은 전혀 건드리지 않았음을 해시로 확인
APP_HASH_AFTER = hashlib.sha256(read("app.py").encode("utf-8")).hexdigest()
chk(APP_HASH_BEFORE == APP_HASH_AFTER,
    "★★★★★ 되돌리기 절차 동안 app.py 파일 내용이 전혀 안 바뀌었다"
    "(몽키패치만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

# 원복 확인 — 같은 모양의 요청이 다시 정상으로 돌아오는지
try:
    rz1 = _patch(f"/api/leads/{lead_id}", json={"note": 816001})
    chk(rz1.status_code == 200,
        "★★★★★ A._s 원복 후 api_lead_update의 숫자 note가 다시 정상(200)",
        rz1.status_code)

    rz2 = _post("/api/cases", json={"case_no": "R616CASE4", "category": "종합 원상복구",
                                     "no_photo": True, "insurer": "R616보험사"})
    rzb2 = rz2.get_json() or {}
    chk(rz2.status_code == 200 and rzb2.get("ok") is True,
        "★★★★★ A._s 원복 후 api_case_create도 다시 정상(200)", rz2.status_code)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드616 원복 확인", f"{type(e).__name__} {e}")


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
