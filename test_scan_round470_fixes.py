# -*- coding: utf-8 -*-
"""스캔 470라운드 회귀 — 포털 하위계정(portal_users) 생성·비밀번호
재발급이 `secrets.token_urlsafe(6)`을 써서 이 앱 자신의
`password_policy_error()`(1276행, 개인정보 안전성 확보조치 기준 인용)
를 약 84% 확률로 위반하던 결함, 1건.

`token_urlsafe(6)`은 항상 정확히 8자이고 URL-safe base64 알파벳
64종 중 특수문자는 `-`·`_` 단 2종뿐이다. 정책은 "2종 조합(문자+숫자)
이면 10자 이상, 3종 조합(문자+숫자+특수문자)이면 8자 이상"을 요구
하는데, 8자짜리 결과가 통과하려면 희귀한 특수문자가 반드시 껴야
한다 — 정밀조사 Agent가 실제발급 300건·몬테카를로 20만회·조합론
계산 세 방법 모두 약 84% 위반으로 서로 정합함을 확인했다.

[1] 소스 확인 — 정책을 만족하는 형제 생성기(_gen_temp_pw)로 통일됐음.
[2]~[4] 실제 Flask 앱으로 되돌림-증명.

   ⚠⚠ [라운드614] 되돌림-증명 기법을 옛 세대(app.py를 실제로 디스크에
   써넣고 워커 서브프로세스로 재현한 뒤 복원 — write→subprocess→write
   사이의 창을 다른 세션이 관측하면 충돌한다, round590이 실제로 겪음)
   에서 round416이 확립한 안전패턴으로 이관한다. `_sub_create_impl`·
   `_sub_resetpw_impl` 둘 다 실제 뷰함수(api_insurer_sub_create·
   api_insurer_sub_reset 등, require_portal_owner 로 잠긴 라우트 자체)가
   맨이름(bare name)으로 부르는 평범한 모듈함수다 — 뷰함수 자체는 전혀
   안 건드리고, 그 호출부의 전역조회가 되돌린 버전을 보게 하려면
   A.__dict__(진짜 모듈 전역) 자체에 이 두 이름만 잠깐 걸어야 한다
   (round416의 _normalize_categories와 동일 발상). 진짜 app.py 파일은
   전혀 안 쓴다 — 예전 워커(test_scan_round470_worker.py)는 더 이상
   쓰지 않는다(그 파일 자신은 남겨 두되 이 파일에서 참조하지 않음).
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
print("  스캔 470라운드 회귀 — 하위계정 임시비밀번호 정책위반")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
OLD_LINE = "    temp = secrets.token_urlsafe(6)"
NEW_LINE = "    temp = _gen_temp_pw()"

chk(APP_SRC.count(OLD_LINE) == 0,
    "★★★★★ 하위계정 생성/재발급 어디에도 token_urlsafe(6)가 더는 없다")
chk(APP_SRC.count(NEW_LINE) == 2,
    "★★★★★ 생성·재발급 두 지점 모두 정책을 만족하는 _gen_temp_pw()로 통일됐다",
    APP_SRC.count(NEW_LINE))


def body_of(fn_name):
    i0 = APP_SRC.index(f"\ndef {fn_name}(")
    i1 = APP_SRC.index("\ndef ", i0 + 1)
    return APP_SRC[i0:i1]


CREATE_BODY = body_of("_sub_create_impl")
RESET_BODY = body_of("_sub_resetpw_impl")
chk(CREATE_BODY.count(NEW_LINE) == 1, "  _sub_create_impl() 안에 NEW_LINE이 유일하다")
chk(RESET_BODY.count(NEW_LINE) == 1, "  _sub_resetpw_impl() 안에 NEW_LINE이 유일하다")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round470_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R470보험','활성')").lastrowid
    conn.commit()
    conn.close()

    def _insurer_owner_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["insurer_id"] = iid
            sess["insurer_name"] = "R470보험"
            sess["_csrf"] = "r470-csrf"
        return c

    def _create_and_check(n, prefix):
        """n개 하위계정을 실제 라우트로 생성 + 1회 재발급, 정책위반 건수를 센다.
        A.app.view_functions 는 전혀 안 건드린다 — 되돌림 여부는 순전히
        A._sub_create_impl/_sub_resetpw_impl 이 지금 어느 버전이냐에 달려 있다."""
        client = _insurer_owner_client()
        violations = checked = 0
        last_uid = None
        for i in range(n):
            r = client.post("/api/insurer/subaccounts",
                             json={"login_id": f"{prefix}{i:03d}", "name": f"담당자{i}",
                                   "role": "하위관리자"},
                             headers={"X-CSRF-Token": "r470-csrf"})
            b = r.get_json() or {}
            if r.status_code != 200 or "temp_password" not in b:
                raise RuntimeError(f"생성 실패 idx={i}: {r.status_code} {b}")
            pw = b["temp_password"]
            checked += 1
            if A.password_policy_error(pw, ident=b.get("login_id", "")):
                violations += 1
            c2 = DB.get_db()
            last_uid = c2.execute("SELECT id FROM portal_users WHERE login_id=?",
                                   (f"{prefix}{i:03d}",)).fetchone()["id"]
            c2.close()
        r_reset = client.post(f"/api/insurer/subaccounts/{last_uid}/reset-pw", json={},
                               headers={"X-CSRF-Token": "r470-csrf"})
        rb = r_reset.get_json() or {}
        reset_pw = rb.get("temp_password")
        reset_violation = bool(A.password_policy_error(reset_pw, ident="")) if reset_pw else None
        return {"checked": checked, "violations": violations,
                "reset_status": r_reset.status_code, "reset_violation": reset_violation}

    print("\n[3] 실행 — 현재(고쳐진) 코드로 30건 생성 + 재발급 1회")
    fixed = _create_and_check(30, "r470f")
    chk(fixed["checked"] == 30, "30건 생성 전부 성공했다", fixed)
    chk(fixed["violations"] == 0,
        "★★★★★ 고쳐진 코드는 30건 전부 정책을 통과한다(위반 0건)", fixed)
    chk(fixed["reset_violation"] is False, "재발급 경로도 정책을 통과한다", fixed)

    print("\n[4] 되돌리기 — _sub_create_impl·_sub_resetpw_impl만 옛 코드로"
          "(실제 파일은 안 건드림)")
    old_create_src = CREATE_BODY.replace(NEW_LINE, OLD_LINE, 1)
    old_reset_src = RESET_BODY.replace(NEW_LINE, OLD_LINE, 1)
    chk(old_create_src.count(OLD_LINE) == 1 and old_create_src != CREATE_BODY,
        "  (준비) _sub_create_impl 되돌리기 텍스트가 실제로 달라졌다")
    chk(old_reset_src.count(OLD_LINE) == 1 and old_reset_src != RESET_BODY,
        "  (준비) _sub_resetpw_impl 되돌리기 텍스트가 실제로 달라졌다")

    _orig_create = A._sub_create_impl
    _orig_reset = A._sub_resetpw_impl
    exec(compile(old_create_src, "<round470_old_sub_create_impl>", "exec"), A.__dict__)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    exec(compile(old_reset_src, "<round470_old_sub_resetpw_impl>", "exec"), A.__dict__)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    chk(A._sub_create_impl is not _orig_create and A._sub_resetpw_impl is not _orig_reset,
        "  (준비) A._sub_create_impl·_sub_resetpw_impl이 실제로 옛 버전 함수객체로 바뀌었다")
    try:
        broken = _create_and_check(30, "r470b")
    finally:
        A._sub_create_impl = _orig_create
        A._sub_resetpw_impl = _orig_reset

    chk(broken["checked"] == 30, "옛 코드(되돌림)에서도 30건 생성 자체는 성공한다", broken)
    chk(broken["violations"] >= 15,
        "★★★★★ 옛 코드(되돌림)는 30건 중 절반 이상이 정책을 위반한다"
        "(이론치 약 84% = 약 25건 — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명)",
        broken)

    print("\n[5] 원복 확인 — 되돌리기 이후 다시 정책을 통과하는가(바꿔치기가 안 샜다)")
    chk(A._sub_create_impl is _orig_create and A._sub_resetpw_impl is _orig_reset,
        "  A._sub_create_impl·_sub_resetpw_impl이 원래 함수객체로 복원됐다")
    restored = _create_and_check(5, "r470r")
    chk(restored["violations"] == 0,
        "★★★★ 원복 후에는 다시 5건 전부 정책을 통과한다(바꿔치기가 안 샜다)", restored)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__}: {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
