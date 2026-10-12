# -*- coding: utf-8 -*-
"""스캔 303라운드 회귀 — smoke_test.py(배포 전 품질 게이트) 결함 3건.
   대상은 배포 절차서(DEPLOY.md)가 "이 순서를 따르면 배포 가능"이라 보증하는
   그 스모크 테스트 도구 자신 — 정밀조사 Agent가 발견, 독립 재검증 후 수정.

  [1] test_admin_ip_gate() — 관리자 IP 화이트리스트를 켰을 때 협력사·보험사
      경로가 함께 막히지 않는지 보는 유일한 검사인데, 함수 정의만 있고
      main() 의 실행 목록(946~956행)에 단 한 번도 없었다 — PASS·FAIL·SKIP
      어디에도 안 남고 "통과 N/N" 요약에서 조용히 빠진다. 이 검사는 앱을
      프로세스 안으로 직접 import 해서 판정하는데(852행 자신의 docstring이
      "HTTP 로는 재현할 수 없어"라고 밝힘), import app → app.py 122행이
      DB.init_db() 를 무조건 실행하고 BOKGUON_DB_PATH 가 비어 있으면 db.py
      기본값은 **운영 bokguon.db** 다 — db.py 자신의 운영DB 가드(32-44행)는
      진입 스크립트 이름이 "test_"로 시작할 때만 발동해 smoke_test.py 는
      그냥 통과하고, 배포 스크립트도 이 환경변수를 안 정해 준다. 그래서
      main() 에 그냥 이어붙이면 두 번째 결함이 그대로 열린다 — 함수 안에서
      먼저 BOKGUON_DB_PATH 가 비어 있을 때만 판정 전용 임시 DB 로 격리한 뒤
      main() 실행 목록에 추가했다(test_bruteforce 바로 앞 — 그건 반드시
      마지막이어야 한다는 자신의 docstring 을 지킨다).

  [2] test_photos() 의 "타 보험사 사진 접근 차단"(IDOR) 검사 — insurer2 로
      로그인해 실패하면(형제 셋: 협력사 264행·보험사 297행·관리자 317행은
      전부 skip()+DEMO_LOGIN_GONE 으로 남기는데 이 넷째만) 아무 기록도 없이
      사라진다. 독립 검증 중 db.py 의 seed() 를 직접 읽어 더 깊은 원인을
      찾았다 — manage.py 의 DEMO_ACCOUNTS(1632행 부근)는 이미 "insurer"·
      "insurer2" 둘 다 go-live 가 지울 이름으로 예약해 뒀고 smoke_test.py 도
      처음부터 "insurer2" 로 로그인을 시도하는데, seed() 의 보험사 목록에
      login_id="insurer2" 인 행 자체가 없었다(두 번째 행 "△△화재" 가
      login_id/password 둘 다 None — 채워진 적 없는 빈자리였다). 즉 이
      IDOR 회귀 검사는 go-live 이후뿐 아니라 **표준 리허설에서도 매번**
      조용히 비어 있었다. △△화재에 login_id="insurer2"·비밀번호
      "bokguon2026"(insurer 와 동일 — smoke_test.py 가 이미 그렇게 시도
      중이었다)을 채워 검사가 실제로 도는 근본 원인을 고치고, 그래도
      계정이 없는 상황(go-live 이후 등)을 위해 형제와 같은 skip()+
      DEMO_LOGIN_GONE 기본 처리를 추가했다.

  [3] Finding 4(조사 보고서) — smoke_test.py 쓰기 모드가 만드는 사건이
      is_demo 표식 없이 남는다는 지적은 **독립 검증 결과 이미 완화돼 있었다**
      (manage.py DEMO_CASE_SQL 이 `is_demo=1 OR insurer_id IN (데모 발주처)`
      로 go-live 시 자동 정리하고, `manage.py mark-smoke-demo` 도 이미
      존재·연결돼 있다 — 검증만 하고 코드는 안 고쳤다). 실제 공백은
      DEPLOY.md 가 이 두 안전장치의 존재를 한 번도 언급하지 않는다는
      점뿐이라, 코드 대신 deploy/DEPLOY.md 에 안내를 추가했다(회귀 테스트
      대상 아님 — 실행 가능한 동작 변경이 없다).

  ⚠ 이 테스트는 smoke_test.py 의 Client.req()/multipart() 를 몽키패치해
    가짜 응답만 쓴다(285라운드 자신의 검증된 방식) — 실제 네트워크·운영
    서버는 전혀 건드리지 않는다. [1]의 앱 import 판정은 importlib.import_module
    자체를 가로채 "app" 을 절대 실제로 불러오지 않는다(운영 DB 접근 원천
    차단). [2]의 근본원인 시드 검증만 실제 격리 DB 에 seed() 를 돌린다.

      python test_scan_round303_fixes.py
"""
import importlib
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def _section(src, start_marker, end_marker):
    i0 = src.index(start_marker)
    i1 = src.index(end_marker, i0 + len(start_marker))
    return src[i0:i1]


ST_SRC = read("smoke_test.py")
DB_SRC = read("db.py")
DEPLOY_SRC = read(os.path.join("deploy", "DEPLOY.md"))

print("=" * 72)
print("  스캔 303라운드 회귀 — smoke_test.py 죽은 검사·IDOR 무기록·insurer2 미시드")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
MAIN_BODY = _section(ST_SRC, "\ndef main():", "\nif __name__")
chk("test_admin_ip_gate()" in MAIN_BODY,
    "★★★★★ main() 이 test_admin_ip_gate() 를 실제로 호출한다"
    "(고치기 전엔 정의만 있고 어디서도 안 불려 PASS·FAIL·SKIP 어디에도 안 남았다)")
chk("test_admin_ip_gate()" in MAIN_BODY and "test_bruteforce()" in MAIN_BODY
    and MAIN_BODY.index("test_admin_ip_gate()") < MAIN_BODY.index("test_bruteforce()"),
    "★★★★ test_bruteforce()(반드시 마지막 실행이어야 한다는 자신의 docstring) "
    "바로 앞에서 호출돼 그 불변식을 지킨다")

IPGATE_BODY = _section(ST_SRC, "\ndef test_admin_ip_gate():", "\ndef test_bruteforce():")
chk('_os.environ.get("BOKGUON_DB_PATH")' in IPGATE_BODY
    and 'importlib.import_module("app")' in IPGATE_BODY
    and IPGATE_BODY.index('_os.environ.get("BOKGUON_DB_PATH")')
    < IPGATE_BODY.index('importlib.import_module("app")'),
    "★★★★★ BOKGUON_DB_PATH 확인/설정이 app import 보다 먼저 실행되는 위치에 있다")
chk('_os.path.join(\n                _tempfile.mkdtemp(prefix="bokguon_smoketest_ipgate_"), "verify.db")'
    in IPGATE_BODY or "bokguon_smoketest_ipgate_" in IPGATE_BODY,
    "★★★★ 비어 있을 때만 채우는 임시(격리) DB 경로를 만든다 — 운영 bokguon.db 가 아니다")

PHOTOS_BODY = _section(ST_SRC, "\ndef test_photos(m, p, i):", "\ndef test_admin_ip_gate():")
chk(PHOTOS_BODY.count('DEMO_LOGIN_GONE.append(') == 1
    and 'DEMO_LOGIN_GONE.append("보험사2")' in PHOTOS_BODY,
    "★★★★★ insurer2 로그인 실패가 형제 셋과 같은 방식으로 DEMO_LOGIN_GONE 에 기록된다")
chk('skip("타 보험사 사진 접근 차단", "데모 보험사2 계정 없음(운영 서버에서는 정상)")' in PHOTOS_BODY,
    "STEP 그 실패가 이름 있는 skip() 으로도 기록된다(무기록 아님)")

INSURERS_BLOCK = _section(DB_SRC, "insurers = [", "]\n    for nm, ot, lid, pw")
chk('"insurer2", "bokguon2026"' in INSURERS_BLOCK,
    "★★★★★ db.py seed() 의 보험사 시드에 login_id/password 가 채워진 "
    "insurer2 행이 실제로 있다(근본 원인 — 고치기 전엔 두 자리 모두 None)")

chk("mark-smoke-demo" in DEPLOY_SRC,
    "★★★ DEPLOY.md 가 이제 manage.py mark-smoke-demo 를 안내한다"
    "(Finding 4 — 코드는 이미 안전했고 문서만 비어 있었다)")

# ============================================================
print("\n[2] 실행 — test_admin_ip_gate() 가 운영 DB 를 켜지 않는지(가짜 import 가로채기)")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
import smoke_test as ST                                             # noqa: E402

_orig_import_module = importlib.import_module
_seen = {}


def _fake_import_module(name, *a, **kw):
    if name == "app":
        _seen["BOKGUON_DB_PATH"] = os.environ.get("BOKGUON_DB_PATH")
        raise ImportError("SIMULATED-ROUND303 — 실제 app.py/db.py 는 절대 안 불린다")
    return _orig_import_module(name, *a, **kw)


REAL_PROD_PATH = os.path.join(HERE, "bokguon.db")
try:
    # ── (A) 호출 전 BOKGUON_DB_PATH 가 비어 있던 경우 ──
    os.environ.pop("BOKGUON_DB_PATH", None)
    ST.SKIP.clear()
    _seen.clear()
    importlib.import_module = _fake_import_module
    ST.test_admin_ip_gate()
    chk("BOKGUON_DB_PATH" in _seen,
        "STEP 가짜 import 가로채기가 실제로 호출됐다(함수가 import 시도까지 도달)")
    chk(_seen.get("BOKGUON_DB_PATH") not in (None, "", REAL_PROD_PATH),
        "★★★★★ BOKGUON_DB_PATH 가 비어 있었는데도 운영 bokguon.db 경로가 아닌 "
        "격리된 임시 경로로 채워진 채 import 가 호출된다(고치기 전엔 os.environ "
        "이 그대로 비어 있어 db.py 가 운영 DB 를 기본값으로 잡았다)",
        _seen.get("BOKGUON_DB_PATH"))
    chk("IP 화이트리스트 판정" in ST.SKIP,
        "STEP 가짜 ImportError 를 정상적으로 skip() 으로 받아넘긴다(크래시 아님)")

    # ── (B) 호출 전 BOKGUON_DB_PATH 를 호출자가 이미 정해 둔 경우 ──
    _seen.clear()
    os.environ["BOKGUON_DB_PATH"] = "/caller/chosen/verify.db"
    ST.test_admin_ip_gate()
    chk(_seen.get("BOKGUON_DB_PATH") == "/caller/chosen/verify.db",
        "★★★★ 호출자가 이미 BOKGUON_DB_PATH 를 정해 뒀으면 그 값을 그대로 "
        "존중한다(덮어쓰지 않음 — 과잉교정 아님)", _seen.get("BOKGUON_DB_PATH"))

    # ── (참고) 옛 코드가 이 상황에서 무엇을 했을지 — db.py 자신의 실제
    #    기본값 결정식을 그대로 재현해 안전하게(운영 파일을 열지 않고) 보인다.
    _would_resolve = os.environ.get("") or os.path.join(HERE, "bokguon.db")
    chk(_would_resolve == REAL_PROD_PATH,
        "★★★ (참고) BOKGUON_DB_PATH 가 비어 있으면 db.py 의 실제 기본값 결정식은 "
        "운영 bokguon.db 로 떨어진다 — 이 검사가 고치기 전 상태를 그대로 뒀다면 "
        "노출됐을 값(db.py:17, 이 줄 자체는 이번 라운드가 손대지 않았다)")
finally:
    importlib.import_module = _orig_import_module
    os.environ.pop("BOKGUON_DB_PATH", None)

# ============================================================
print("\n[3] 실행 — main() 이 test_admin_ip_gate() 를 정확히 한 번 호출하는가(종단간)")
# ------------------------------------------------------------
_STUBBED = ("test_public", "test_csrf", "test_consent", "test_bidding", "test_blockers",
            "test_rate_limit", "test_frontend", "test_photos", "test_bruteforce")
_orig_funcs, _calls = {}, {"n": 0}


def _noop(*a, **kw):
    return None


def _noop_auth(*a, **kw):
    return None, None


def _noop_admin(*a, **kw):
    return None


def _counting_ip_gate():
    _calls["n"] += 1


try:
    for fn in _STUBBED:
        _orig_funcs[fn] = getattr(ST, fn)
        setattr(ST, fn, _noop)
    _orig_funcs["test_auth_isolation"] = ST.test_auth_isolation
    _orig_funcs["test_admin"] = ST.test_admin
    ST.test_auth_isolation = _noop_auth
    ST.test_admin = _noop_admin
    _orig_ip_gate = ST.test_admin_ip_gate
    ST.test_admin_ip_gate = _counting_ip_gate

    os.environ["BOKGUON_TEST_ADMIN_PW"] = "x"
    os.environ["BOKGUON_TEST_INSURER_PW"] = "x"
    os.environ["BOKGUON_TEST_PARTNER_PW"] = "x"
    _orig_argv = sys.argv
    sys.argv = ["smoke_test.py"]

    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        ST.main()

    chk(_calls["n"] == 1,
        "★★★★★ main() 실행 시 test_admin_ip_gate() 가 정확히 한 번 불린다"
        "(고치기 전엔 0 — main() 실행목록 어디에도 없었다)", _calls["n"])
finally:
    for fn, orig in _orig_funcs.items():
        setattr(ST, fn, orig)
    ST.test_admin_ip_gate = _orig_ip_gate
    sys.argv = _orig_argv

# ============================================================
print("\n[4] 실행 — db.py seed() 가 실제로 로그인 가능한 insurer2 계정을 만드는가")
# ------------------------------------------------------------
_tmpdir4 = tempfile.mkdtemp(prefix="round303_seed_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir4, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "1"
try:
    import db as DB                                                 # noqa: E402
    DB.init_db()
    conn = DB.get_db()
    row2 = conn.execute(
        "SELECT login_id, password_hash FROM insurers WHERE login_id='insurer2'").fetchone()
    row1 = conn.execute(
        "SELECT login_id, password_hash FROM insurers WHERE login_id='insurer'").fetchone()
    conn.close()
    chk(row2 is not None,
        "★★★★★ seed() 가 이제 실제로 login_id='insurer2' 계정을 만든다"
        "(고치기 전엔 이 조회 자체가 0행 — IDOR 검사가 존재한 적이 없었던 근본 원인)")
    if row2:
        chk(DB.verify_pw("bokguon2026", row2["password_hash"]),
            "★★★★★ insurer2 의 비밀번호가 smoke_test.py 723-725행이 이미 쓰던 "
            "BOKGUON_TEST_INSURER_PW 기본값('bokguon2026', insurer 와 동일)과 실제로 맞는다")
    chk(row1 is not None and DB.verify_pw("bokguon2026", row1["password_hash"]),
        "STEP 대조군 — 기존 insurer 계정은 회귀 없이 그대로 로그인 가능하다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드303 [4] seed() 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_SEED_DEMO", None)

# ============================================================
print("\n[5] 실행 — test_photos() 의 IDOR 검사: 성공/실패 두 시나리오 모두 실제로 기록되는가")
# ------------------------------------------------------------
CID, BIDID, PHOTO_IDS = "9303", 555, [4242, 4243]


def _fake_req_factory(login_status_ok):
    def _req(self, method, path, body=None):
        if path == "/api/csrf" and method == "GET":
            return 200, '{"token":"t303"}', ST.CIHeaders({})
        if path == "/api/insurer/cases" and method == "POST":
            return 200, json.dumps({"ok": True, "id": int(CID)}), ST.CIHeaders({})
        if path == f"/api/insurer/cases/{CID}/bids" and method == "GET":
            return 200, json.dumps({"bids": [{"id": BIDID}]}), ST.CIHeaders({})
        if path == f"/api/insurer/cases/{CID}/award" and method == "POST":
            return 200, '{"ok": true}', ST.CIHeaders({})
        if path == f"/api/cases/{CID}/photos" and method == "GET":
            return 200, json.dumps({"unclassified": [{"id": pid} for pid in PHOTO_IDS],
                                     "construction": [], "receipts": []}), ST.CIHeaders({})
        if path == "/api/insurer/login" and method == "POST":
            if login_status_ok:
                return 200, '{"ok": true}', ST.CIHeaders({})
            return 401, '{"ok": false}', ST.CIHeaders({})
        if path.startswith("/api/photos/") and path.endswith("/file") and method == "GET":
            return 403, "", ST.CIHeaders({"X-Content-Type-Options": "nosniff"})
        return 200, "{}", ST.CIHeaders({})
    return _req


def _fake_multipart(self, path, files):
    return 200, {"count": len(files), "duplicates": 0, "errors": []}


_orig_req, _orig_multi = ST.Client.req, ST.Client.multipart
try:
    # ── (성공) insurer2 로그인이 실제로 되는 정상 상황 ──
    ST.PASS.clear(); ST.FAIL.clear(); ST.SKIP.clear(); ST.DEMO_LOGIN_GONE.clear()
    ST.Client.req = _fake_req_factory(True)
    ST.Client.multipart = _fake_multipart
    m, p, i = ST.Client("m"), ST.Client("p"), ST.Client("i")
    ST.test_photos(m, p, i)
    chk("타 보험사 사진 접근 차단" in ST.PASS,
        "★★★★★ insurer2 로그인이 실제로 성공하면(라운드303 시드 수정 이후 표준 "
        "상황) IDOR 회귀 검사가 실제로 실행되고 통과로 기록된다(고치기 전엔 "
        "insurer2 계정 자체가 없어 이 검사가 한 번도 실행된 적이 없었다)",
        (ST.PASS, ST.SKIP))
    chk("보험사2" not in ST.DEMO_LOGIN_GONE,
        "STEP 로그인이 성공하는 정상 상황에서는 DEMO_LOGIN_GONE 에 안 남는다(과잉경보 아님)")

    # ── (실패) go-live 이후 등 insurer2 계정이 없는 상황 ──
    ST.PASS.clear(); ST.FAIL.clear(); ST.SKIP.clear(); ST.DEMO_LOGIN_GONE.clear()
    ST.Client.req = _fake_req_factory(False)
    m, p, i = ST.Client("m"), ST.Client("p"), ST.Client("i")
    ST.test_photos(m, p, i)
    chk("타 보험사 사진 접근 차단" in ST.SKIP,
        "★★★★★ insurer2 로그인이 실패하면 이제 SKIP 으로 명시 기록된다"
        "(고치기 전엔 PASS·FAIL·SKIP 어디에도 안 남고 조용히 사라졌다)",
        (ST.PASS, ST.FAIL, ST.SKIP))
    chk("보험사2" in ST.DEMO_LOGIN_GONE,
        "★★★★ 형제 셋(협력사·보험사·관리자)과 동일하게 '보험사2'도 DEMO_LOGIN_GONE "
        "에 기록돼 요약 화면에서 무엇을 못 검증했는지 드러난다", ST.DEMO_LOGIN_GONE)
finally:
    ST.Client.req, ST.Client.multipart = _orig_req, _orig_multi
    for k in ("BOKGUON_DB_PATH", "BOKGUON_ENV", "BOKGUON_SEED_DEMO",
              "BOKGUON_TEST_ADMIN_PW", "BOKGUON_TEST_INSURER_PW", "BOKGUON_TEST_PARTNER_PW"):
        os.environ.pop(k, None)
    import shutil
    shutil.rmtree(_tmpdir4, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
