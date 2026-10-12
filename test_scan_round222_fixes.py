# -*- coding: utf-8 -*-
"""스캔 222라운드 회귀 — 관리자 IP 화이트리스트(ADMIN_IP_ALLOW)가 3개 라우트를
   우회하던 결함(billing_guide·insurer_api_guide·api_me).

  before_request 의 전역 게이트는 _is_admin_path() 로 "관리자 경로"를 판정하는데,
  이 함수는 (a) /admin 접두사 (b) /api/login (c) @require_admin 이 심는
  view._admin_only 플래그, 셋 중 하나로만 관리자 경로를 알아본다. 관리자·발주처·
  협력사가 함께 쓰는 라우트는 데코레이터를 못 붙이니 이 셋 어디에도 안 걸려
  전역 게이트가 아예 발동하지 않는다.

  이 문제를 풀려고 만든 것이 _mixed_actor_guard() (JSON API 7곳이 씀)인데,
  billing_guide·insurer_api_guide 는 "화면이라 JSON 오류를 못 보인다"는 이유로
  이걸 안 쓰고 인증·생사확인을 손으로 다시 구현하면서 정확히 IP 검사 절만
  빠뜨렸다. api_me() 도 데코레이터가 없어 같은 구멍이 있었다.

  _admin_ip_denied() 로 판정을 뽑아내 세 라우트 모두에 적용했다.

      python test_scan_round222_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile

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
    return src[start:end if end != -1 else None]


APP_SRC = read("app.py")

print("═" * 72)
print("  스캔 222라운드 회귀 — ADMIN_IP_ALLOW 가 billing_guide 등 3곳을 우회")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 함수 경계 안에서")
# ──────────────────────────────────────────────────────────────
chk("def _admin_ip_denied():" in APP_SRC,
    "★★★★ 공용 판정 함수 _admin_ip_denied() 가 새로 생겼다")

guard_body = _py_fn_body(APP_SRC, "_mixed_actor_guard")
chk("_admin_ip_denied()" in guard_body,
    "STEP _mixed_actor_guard() 도 이제 공용 함수를 쓴다(과잉리팩터 확인)")

for fn in ("billing_guide", "insurer_api_guide"):
    body = _py_fn_body(APP_SRC, fn)
    chk("_admin_ip_denied()" in body,
        f"★★★★ {fn}() 가 이제 IP 화이트리스트를 검사한다"
        "(예전엔 인증·생사확인만 하고 이 절이 아예 없었다)")

me_body = _py_fn_body(APP_SRC, "api_me")
chk("_admin_ip_denied()" in me_body,
    "★★★ api_me() 도 이제 IP 화이트리스트를 검사한다"
    "(예전엔 탈취된 관리자 세션이 사무실 밖에서도 이름·CSRF 를 계속 받을 수 있었다)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실서버 경로(Flask test_client + 임시 DB, ADMIN_IP_ALLOW 실제 설정)")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round222_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
ALLOWED_IP = "203.0.113.10"
os.environ["BOKGUON_ADMIN_IP_ALLOW"] = ALLOWED_IP
DENIED_IP = "198.51.100.20"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    chk(A.ADMIN_IP_ALLOW == [ALLOWED_IP],
        "STEP 모듈이 실제로 이 화이트리스트를 읽어 들였다(테스트 전제 확인)",
        A.ADMIN_IP_ALLOW)

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r222admin','x','검증','최고관리자')")
    iid = conn.execute("INSERT INTO insurers(name) VALUES('R222보험사')").lastrowid
    conn.commit()
    conn.close()

    admin = A.app.test_client()
    with admin.session_transaction() as sess:
        sess["admin"] = "r222admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"

    def get(client, path, ip):
        return client.get(path, environ_overrides={"REMOTE_ADDR": ip})

    # ── 대조군 — 기존에 이미 잘 막히던 경로들이 그대로 막히는지 ──
    r_admin_denied = get(admin, "/admin", DENIED_IP)
    chk(r_admin_denied.status_code == 403,
        "STEP (대조군) /admin 콘솔 자체는 여전히 비허용 IP 에서 403 이다", r_admin_denied.status_code)
    r_notices_denied = get(admin, "/api/notices", DENIED_IP)
    chk(r_notices_denied.status_code == 403
        and (r_notices_denied.get_json() or {}).get("code") == "IP_DENIED",
        "STEP (대조군) _mixed_actor_guard 를 쓰는 /api/notices 도 여전히 403 IP_DENIED 다",
        (r_notices_denied.status_code, r_notices_denied.get_json()))

    # ── 예전엔 뚫려 있던 3곳 — 비허용 IP 에서 이제 막히는가 ──
    r_bill_denied = get(admin, "/report/billing", DENIED_IP)
    chk(r_bill_denied.status_code == 403,
        "★★★★ /report/billing 이 비허용 IP 에서 이제 403 이다"
        "(고치기 전엔 관리자 세션만 있으면 어디서든 200 이었다)", r_bill_denied.status_code)

    r_docs_denied = get(admin, "/docs/insurer-api", DENIED_IP)
    chk(r_docs_denied.status_code == 403,
        "★★★★ /docs/insurer-api 가 비허용 IP 에서 이제 403 이다"
        "(연동 키 발급방법이 담긴 비공개 문서인데도 어디서든 열렸었다)", r_docs_denied.status_code)

    r_me_denied = get(admin, "/api/me", DENIED_IP)
    chk(r_me_denied.status_code == 403
        and (r_me_denied.get_json() or {}).get("code") == "IP_DENIED",
        "★★★ /api/me 도 비허용 IP 에서 이제 403 IP_DENIED 다"
        "(고치기 전엔 이름·아이디·새 CSRF 토큰을 계속 내줬다)",
        (r_me_denied.status_code, r_me_denied.get_json()))

    # ── 허용 IP 에서는 여전히 정상 동작(과잉차단 아님) ──
    r_bill_ok = get(admin, "/report/billing", ALLOWED_IP)
    chk(r_bill_ok.status_code == 200,
        "STEP 허용된 IP 에서는 /report/billing 이 정상 200 이다(과잉차단 아님)",
        r_bill_ok.status_code)
    r_me_ok = get(admin, "/api/me", ALLOWED_IP)
    chk(r_me_ok.status_code == 200 and r_me_ok.get_json().get("username") == "r222admin",
        "STEP 허용된 IP 에서는 /api/me 도 정상 200 이다(과잉차단 아님)",
        (r_me_ok.status_code, r_me_ok.get_json()))

    # ── 관리자가 아닌 발주처 세션은 애초에 IP 게이트 대상이 아니다(설계 의도) ──
    insurer_client = A.app.test_client()
    with insurer_client.session_transaction() as sess:
        sess["insurer_id"] = iid
    r_bill_insurer = get(insurer_client, "/report/billing", DENIED_IP)
    chk(r_bill_insurer.status_code == 200,
        "STEP 발주처 세션은 '비허용 IP'에서도 billing_guide 를 그대로 본다"
        "(_admin_ip_denied 는 admin 세션에만 적용 — 과잉차단 아님, 설계 의도 그대로)",
        r_bill_insurer.status_code)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드222 서버측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    os.environ.pop("BOKGUON_ADMIN_IP_ALLOW", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
