# -*- coding: utf-8 -*-
"""스캔 87라운드 회귀 — 표준단가 등록 검증누락·마케팅 수신자 채널판정 불일치.

  [F1] api_boq_create 가 parse_money() 의 (값,오류) 중 값만 집어 썼다.
    검증 실패(비숫자·음수·상한초과)가 조용히 0원으로 뭉개져 200 OK 로 저장되고,
    그 아래 _boq_history 는 검증 실패한 **원본 입력값**을 그대로 이력(new_price)
    에 남긴다 — 실제 저장 0원과 이력 값이 서로 다른 자기모순 감사기록이 생긴다.
    형제(api_boq_update)는 이미 이 검사를 한다.

  [F2] _campaign_recipients 의 채널 판정이 호출부(api_campaign_create, 유효값
    3개만 인정)와 다른 기준(그냥 truthy)을 썼다. 유효하지 않은 channel 값이
    오면 호출부는 "메일"로 떨어져 야간광고 금지 검사·(광고) 접두를 건너뛰는데,
    이 함수는 그 값을 그대로 살려 문자/전화 동의 기준으로 수신자를 골랐다 —
    채널 표기와 실제 수신자 선정 기준이 어긋난다.

      python test_scan_round87_fixes.py
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


APP_SRC = read("app.py")

print("═" * 72)
print("  스캔 87라운드 회귀 — 표준단가 검증누락·마케팅 채널판정 불일치")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] F1 — 소스: api_boq_create 가 parse_money 오류를 확인한다")
# ──────────────────────────────────────────────────────────────
boq_create_body = _py_fn_body(APP_SRC, "api_boq_create")
chk("ref_price, err = parse_money(" in boq_create_body.replace(" ", "")
    or "ref_price,err=parse_money(" in boq_create_body.replace(" ", ""),
    "★★★ api_boq_create 가 parse_money 의 (값,오류) 를 모두 받는다")
chk('"error": err}), 400' in boq_create_body or "'error': err}), 400" in boq_create_body,
    "★★ 오류가 있으면 400 으로 거부한다(형제 api_boq_update 와 같은 계약)")
chk('_boq_history(conn, bid, {**d, "ref_price": ref_price}' in boq_create_body,
    "★★★ 이력(_boq_history) 에도 원본 d 가 아니라 검증된 ref_price 를 넘긴다")

# ══════════════════════════════════════════════════════════════
print("\n[2] F2 — 소스: _campaign_recipients 채널 판정이 호출부와 같은 기준을 쓴다")
# ──────────────────────────────────────────────────────────────
recip_body = _py_fn_body(APP_SRC, "_campaign_recipients")
create_body = _py_fn_body(APP_SRC, "api_campaign_create")
_enum = '("메일", "문자", "알림톡")'
chk(_enum in recip_body and _enum in create_body,
    "★★★ 두 함수가 동일한 채널 화이트리스트 튜플을 쓴다(문자 그대로 일치)")
chk('f.get("channel") or "메일"' not in recip_body,
    "★★ _campaign_recipients 가 더 이상 단순 truthy 로 채널을 판정하지 않는다"
    "(호출부와 다른 기준으로 갈라지던 옛 코드 제거됨)")

# ══════════════════════════════════════════════════════════════
print("\n[3] F1 — 실행: 상한 초과 참고단가가 0원으로 조용히 저장되지 않는다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round87_")
_dbpath = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_DB_PATH"] = _dbpath
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','중간관리자')")
    conn.commit(); conn.close()

    admin = A.app.test_client()
    _tok = "r87-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok, "Content-Type": "application/json"}

    def _boq_count():
        c = DB.get_db()
        n = c.execute("SELECT COUNT(*) n FROM standard_boq").fetchone()["n"]
        c.close()
        return n

    n0 = _boq_count()
    # (a) 상한(100억) 초과 참고단가 — 예전엔 0원으로 뭉개져 200 이 났다.
    r1 = admin.post("/api/boq", json={
        "major": "가드레일·방호울타리", "item": "레일(W빔)",
        "ref_price": 620_000_000_000, "unit": "m", "price_src": "회사 표준"}, headers=_hdr)
    j1 = r1.get_json()
    chk(r1.status_code == 400 and "참고단가" in (j1.get("error") or ""),
        "★★★ 상한 초과 참고단가는 400 으로 거부된다(예전엔 0원 저장 + 200 OK)",
        f"status={r1.status_code} body={j1}")
    chk(_boq_count() == n0,
        "★★ 거부된 요청은 실제로 행을 만들지 않는다(부분 저장 없음)", f"n0={n0} now={_boq_count()}")

    # (b) 정상 값은 그대로 통과하고, 이력의 new_price 가 실제 저장값과 일치해야 한다.
    r2 = admin.post("/api/boq", json={
        "major": "가드레일·방호울타리", "item": "레일(W빔)",
        "ref_price": 62_000, "unit": "m", "price_src": "회사 표준"}, headers=_hdr)
    j2 = r2.get_json()
    chk(r2.status_code == 200 and j2.get("ok"),
        "★★ 정상 범위 참고단가는 그대로 통과한다", f"status={r2.status_code} body={j2}")
    bid = j2.get("id")
    c = DB.get_db()
    live = c.execute("SELECT ref_price FROM standard_boq WHERE id=?", (bid,)).fetchone()
    hist = c.execute(
        "SELECT new_price FROM boq_price_history WHERE boq_id=? ORDER BY id DESC LIMIT 1",
        (bid,)).fetchone()
    c.close()
    chk(bool(live) and bool(hist) and live["ref_price"] == hist["new_price"] == 62_000,
        "★★★ 저장된 값과 이력(new_price)이 서로 같다(자기모순 감사기록 없음)",
        f"live={dict(live) if live else None} hist={dict(hist) if hist else None}")

    # ══════════════════════════════════════════════════════════
    print("\n[4] F2 — 실행: 유효하지 않은 채널 값이 메일 기준(이메일 동의)으로 통일된다")
    # ──────────────────────────────────────────────────────────
    conn = DB.get_db()
    pid_email = conn.execute(
        "INSERT INTO partners(name,partner_type,status,email,phone,"
        "                     email_consent,sms_consent,email_opt_out,sms_opt_out) "
        "VALUES('메일동의사','시행사','활성','mail@ok.com','010-0000-0001',1,0,0,0)"
    ).lastrowid
    pid_sms = conn.execute(
        "INSERT INTO partners(name,partner_type,status,email,phone,"
        "                     email_consent,sms_consent,email_opt_out,sms_opt_out) "
        "VALUES('문자동의사','시행사','활성','mail2@ok.com','010-0000-0002',0,1,0,0)"
    ).lastrowid
    conn.commit()

    # 유효 채널 목록에 없는 값 — 호출부(api_campaign_create)라면 '메일'로 떨어진다.
    ok, no_contact, opted, no_consent = A._campaign_recipients(conn, {"channel": "카카오톡DM"})
    ids = {r["id"] for r in ok}
    conn.close()
    chk(pid_email in ids and pid_sms not in ids,
        "★★★ 잘못된 채널 값은 메일 기준(email_consent)으로 수신자를 고른다"
        "(예전엔 문자 기준(sms_consent)으로 골라 메일동의사가 빠지고 문자동의사가 들어갔다)",
        f"ids={ids} email={pid_email} sms={pid_sms}")

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드87 서버측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
