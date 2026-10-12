# -*- coding: utf-8 -*-
"""스캔 38라운드 회귀 — 웹훅 SSRF 방어 함수의 IPv4 전면 오작동.

  조사 에이전트가 찾은 결함: `_webhook_host_safe()` 가 `ip.is_site_local` 을
  무조건 불렀는데, 이 속성은 **IPv6Address 에만 있고 IPv4Address 엔 없다**
  (옛 IPv6 site-local 표기 fec0::/10 전용 개념). 사설·루프백 등은 앞선 항목
  에서 먼저 걸려 그 줄까지 안 가지만, **공인 IPv4 주소는 전부 이 줄에서
  AttributeError** 가 나서 바깥 `except Exception: return False` 가 삼킨다
  — 결과적으로 **어떤 IPv4 웹훅 주소도 등록할 수 없었다**(안전한 방향으로
  고장났지만, 기능 자체가 아무도 못 쓰는 상태). SSRF 차단 자체는 살아있었다
  (그래서 이건 보안 결함이 아니라 기능 결함)지만 고쳐야 실제로 쓸 수 있다.

  고침: `ip.is_site_local` → `getattr(ip, "is_site_local", False)`.
  IPv4 에서는 조용히 False(원래 취지와 동일 — 다른 항목이 이미 사설·예약
  대역을 다 잡음), IPv6 의 옛 site-local 대역은 여전히 차단.

      python test_scan_round38_fixes.py
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("═" * 72)
print("  스캔 38라운드 회귀 — 웹훅 SSRF 방어의 IPv4 전면 차단 버그")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 배선이 실제로 있는가")
# ──────────────────────────────────────────────────────────────
#  ⚠ [라운드84] is_site_local 검사 뒤에 CGNAT(is_global) 검사가 하나 더 붙으면서
#    이 줄이 더 이상 "):"로 곧장 안 끝난다 — 실제로 지켜야 할 불변식은 "getattr 로
#    안전하게 감쌌다"는 것 자체이지 그 줄이 조건문의 마지막 항인지가 아니다.
chk('getattr(ip, "is_site_local", False)' in APP_SRC,
    "★★ is_site_local 호출이 getattr 로 안전하게 감싸졌다")
chk("or ip.is_site_local):" not in APP_SRC,
    "★ 옛 무방비 직접호출 형태가 남아있지 않다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 함수로 경계값 6종 판정")
# ──────────────────────────────────────────────────────────────
import tempfile
_tmpdir = tempfile.mkdtemp(prefix="webhook38_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()

    import app as A

    cases = [
        ("https://127.0.0.1/hook", False, "루프백(리터럴) — 여전히 차단"),
        ("https://10.1.2.3/hook", False, "사설 대역(리터럴) — 여전히 차단"),
        ("https://169.254.169.254/hook", False, "링크로컬·메타데이터풍(리터럴) — 여전히 차단"),
        ("https://[fec0::1]/hook", False, "★★ IPv6 옛 site-local(리터럴) — getattr 고치고도 여전히 차단"),
        ("http://example.com/hook", False, "http(평문) 스킴 자체가 거부"),
        ("https://example.com/hook", True, "★★★ 공인 IPv4 도메인 — 고치기 전엔 무조건 False 였다"),
    ]
    for url, want, label in cases:
        try:
            got = A._webhook_host_safe(url)
        except Exception as e:                                      # noqa: BLE001
            chk(False, f"{label} ({url})", f"함수가 예외를 던짐: {type(e).__name__} {e}")
            continue
        chk(got == want, f"{label} ({url})", f"기대={want} 실제={got}")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 경계값 실측 준비", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 실제 라우트까지 왕복(관리자가 공인 도메인을 등록할 수 있는가)")
# ──────────────────────────────────────────────────────────────
try:
    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin38','x','검증','최고관리자')")
    iid = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('검증보험사38','활성')").lastrowid
    conn.commit()
    conn.close()

    client = A.app.test_client()
    _tok = "regress-round38-csrf-token"
    with client.session_transaction() as sess:
        sess["admin"] = "admin38"
        sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    r = client.patch(f"/api/insurers/{iid}/webhook",
                      json={"webhook_url": "https://example.com/hook"}, headers=_hdr)
    d = r.get_json()
    chk(r.status_code == 200 and d.get("ok") is True and d.get("webhook_secret"),
        "★★★ 공인 https 도메인 등록이 실제로 성공한다(라우트 왕복)", (r.status_code, d))

    r2 = client.patch(f"/api/insurers/{iid}/webhook",
                       json={"webhook_url": "https://127.0.0.1/hook"}, headers=_hdr)
    chk(r2.status_code == 400, "루프백 주소는 라우트에서도 여전히 거부된다", r2.status_code)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라우트 왕복 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
