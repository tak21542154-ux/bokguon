# -*- coding: utf-8 -*-
"""스캔 54라운드 회귀 — 협력사 로그인 잠금이 영원히 안 풀리던 결함 한 쌍
   + 어드민 등급 원칙 누락 3곳 + 협력사 계정발급 CLI 안전검사 누락.

  조사 에이전트(+직접 코드 대조)가 실측으로 증명한 결함:

  ① api_partner_login — 잠긴 상태에서의 시도까지 실패로 적립했다(A-10 위반).
     형제 둘(api_login·api_insurer_login)은 이미 "잠금 중 시도는 안 적는다"는
     불변조건을 지키는데 협력사 창구만 어겼다 — 정직한 재시도만으로 10분 창이
     매번 갱신돼 영원히 안 풀렸다. 시공중 사건은 그 업체의 완료 보고로만
     넘어가므로(대체 경로 없음), 잠기면 진행 사건이 통째로 멈춘다.
  ② api_unlock_login — 실패기록 키는 창구마다 접두사가 다른데(P:/I:/OTP:)
     해제는 원문 정확일치라 협력사·보험사·2단계인증 잠금은 하나도 안 풀렸고,
     그래도 {"ok":true,"cleared":0}이 나가 "안 잠겨 있었다"는 거짓 확인을 줬다.
  ③ api_outbox_test_send·api_notice_delete·api_memo_delete — "승인·정산·삭제는
     하위관리자 제외" 원칙(ROLE_RANK 주석)에 어긋나게 등급 문턱이 없었다.
  ④ partner_accounts.pick() — --ids 로 부르면 "활성 업체만" 안전 원칙이
     통째로 빠졌다(퇴출 업체에도 포털 계정 발급).

      python test_scan_round54_fixes.py
"""
import io
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


APP_SRC = read("app.py")
PA_SRC = read("partner_accounts.py")
ADMINJS_SRC = read(os.path.join("static", "admin.js"))

print("═" * 72)
print("  스캔 54라운드 회귀 — 협력사 로그인 잠금 무한연장 + 해제 실패 + 등급 3곳")
print("═" * 72)


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
plogin = _body(APP_SRC, "api_partner_login")
chk('_log_attempt(conn, "P:" + login_id, False)' not in plogin,
    "★★★ ① api_partner_login — 잠금 중 시도를 더 이상 실패로 적립하지 않는다")
chk(plogin.count('_log_attempt(conn, "P:" + login_id') == 1,
    "① _log_attempt 호출이 정상 로그인 판정 자리 딱 한 번만 남았다",
    plogin.count('_log_attempt(conn, "P:" + login_id'))

unlock = _body(APP_SRC, "api_unlock_login")
chk('"P:" + uname, "I:" + uname, "OTP:" + uname' in unlock,
    "★★★ ② api_unlock_login — 협력사·보험사·OTP 네임스페이스까지 함께 지운다")
chk('남은 실패 기록이 없습니다' in ADMINJS_SRC,
    "★ admin.js — '안 잠겨 있었다' 단정 대신 사실만 말한다")

for fn_name, label in (("api_outbox_test_send", "③ api_outbox_test_send"),
                        ("api_notice_delete", "③ api_notice_delete"),
                        ("api_memo_delete", "③ api_memo_delete")):
    idx = APP_SRC.index(f"\ndef {fn_name}(")
    head = APP_SRC[max(0, idx - 300):idx]
    chk('require_role("중간관리자")' in head,
        f"★★ {label} — 하위관리자를 막는 등급 문턱이 생겼다")

chk("WHERE id IN ({','.join('?' * len(ids))}) AND status='활성'" in PA_SRC,
    "★ partner_accounts.pick() — --ids 에도 활성 업체만 필터가 생겼다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 잠금~해제 전체 흐름을 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round54_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    client = A.app.test_client()
    _tok = "regress-round54-csrf-token"
    _hdr = {"X-CSRF-Token": _tok}
    REAL_PW = "테스트비번!Q2026"

    conn = DB.get_db()
    login_id = "p54lockout"
    pw_hash = DB.hash_pw(REAL_PW)
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,login_id,password_hash) "
        "VALUES('검증잠금54','시행사','활성',?,?)", (login_id, pw_hash)).lastrowid
    conn.commit(); conn.close()

    def _n_fails(prefix_key):
        c = DB.get_db()
        n = c.execute(
            "SELECT COUNT(*) FROM login_attempts WHERE username=? AND success=0",
            (prefix_key,)).fetchone()[0]
        c.close()
        return n

    #  ① 오답 5회로 잠근다
    for _ in range(A.MAX_LOGIN_FAILS):
        client.post("/api/partner/login", json={"login_id": login_id, "password": "틀린값"},
                    headers=_hdr)
    n_after_lock = _n_fails("P:" + login_id)
    chk(n_after_lock == A.MAX_LOGIN_FAILS, "① 오답 5회로 정확히 5건이 쌓였다(잠김)", n_after_lock)

    r_locked = client.post("/api/partner/login",
                           json={"login_id": login_id, "password": REAL_PW}, headers=_hdr)
    chk(r_locked.status_code == 429, "① 잠긴 동안은 정답이어도 429 다", r_locked.status_code)

    #  ⚠ 여기가 핵심 — 잠긴 동안 더 두드려도 실패 건수가 안 늘어야 한다(고치기 전엔 계속 늘었다)
    #    ⚠⚠ /api/partner/login 자체에 별도 레이트리밋(5분 10회)이 있다 — 이 구간
    #      전체(잠금 5회+확인 1회+해머+창이후 1회)가 그 예산 안에 들어야 한다.
    for _ in range(2):
        client.post("/api/partner/login",
                    json={"login_id": login_id, "password": REAL_PW}, headers=_hdr)
    n_after_hammer = _n_fails("P:" + login_id)
    chk(n_after_hammer == A.MAX_LOGIN_FAILS,
        "★★★ ① 잠긴 동안 2번 더 두드려도 실패 건수가 그대로다(고치기 전엔 계속 늘었다)",
        (n_after_lock, n_after_hammer))

    #  잠금창이 지난 것처럼 만든다 — 5건을 전부 창 밖(11분 전)으로 되돌린다
    conn = DB.get_db()
    conn.execute(
        "UPDATE login_attempts SET created_at=datetime('now','+9 hours','-11 minutes') "
        " WHERE username=? AND success=0", ("P:" + login_id,))
    conn.commit(); conn.close()

    r_after_window = client.post("/api/partner/login",
                                 json={"login_id": login_id, "password": REAL_PW}, headers=_hdr)
    chk(r_after_window.status_code == 200,
        "★★★ ① 창이 지나면 정답으로 정상 로그인된다(고치기 전엔 재시도가 창을 계속 갱신해 영영 안 풀렸다)",
        (r_after_window.status_code, r_after_window.get_json()))

    # ── ② 해제 도구 — 세 네임스페이스 모두 실제로 지워지는가 ──
    #  ⚠ 앞 섹션의 실제 협력사 로그인이 이 client 에 pw_sig 를 남겼다 — 안 지우고
    #    admin 키만 얹으면 _account_alive() 가 그 남은 서명을 어드민 해시와 대조해
    #    "비밀번호가 변경됨"으로 오판한다. 실제 로그인 라우트도 session.clear() 를
    #    먼저 한다 — 같은 규칙을 여기서도 지킨다.
    with client.session_transaction() as sess:
        sess.clear()
        sess["admin"] = "admin54"; sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = _tok
    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                "VALUES('admin54','x','검증','최고관리자')")
    uname2 = "u54unlock"
    for prefix in ("", "P:", "I:", "OTP:"):
        for _ in range(3):
            conn.execute(
                "INSERT INTO login_attempts(username,ip,success,created_at) "
                "VALUES(?,?,0,datetime('now','+9 hours'))", (prefix + uname2, "127.0.0.1"))
    conn.commit(); conn.close()

    r_unlock = client.post("/api/login-attempts/unlock", json={"username": uname2}, headers=_hdr)
    d_unlock = r_unlock.get_json()
    chk(d_unlock.get("cleared") == 12,
        "★★★ ② 해제 한 번으로 네 네임스페이스(원문·P:·I:·OTP:) 12건이 전부 지워졌다"
        "(고치기 전엔 원문 3건만 지워짐)", d_unlock)
    conn = DB.get_db()
    remain = conn.execute(
        "SELECT COUNT(*) FROM login_attempts WHERE success=0 AND "
        "(username=? OR username=? OR username=? OR username=?)",
        (uname2, "P:" + uname2, "I:" + uname2, "OTP:" + uname2)).fetchone()[0]
    conn.close()
    chk(remain == 0, "② 네 네임스페이스 모두 실제로 0건 남았다", remain)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 실행 — 어드민 등급 문턱 3곳 HTTP 실측")
    # ──────────────────────────────────────────────────────────
    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                "VALUES('staff54','x','검증하위','하위관리자')")
    nid = conn.execute(
        "INSERT INTO notices(title,body) VALUES('검증공지54','내용')").lastrowid
    conn.commit(); conn.close()

    with client.session_transaction() as sess:
        sess.clear()
        sess["admin"] = "staff54"; sess["admin_role"] = "하위관리자"
        sess["admin_name"] = "검증하위"; sess["_csrf"] = _tok

    r3a = client.delete(f"/api/notices/{nid}", headers=_hdr)
    chk(r3a.status_code == 403, "★★★ ③ 하위관리자는 공지를 삭제할 수 없다(고치기 전엔 200)",
        r3a.status_code)
    r3b = client.post("/api/outbox/test-send", json={"phone": "01012345678"}, headers=_hdr)
    chk(r3b.status_code == 403, "★★★ ③ 하위관리자는 테스트 문자를 보낼 수 없다(고치기 전엔 통과)",
        r3b.status_code)

    conn = DB.get_db()
    row_n = conn.execute("SELECT id FROM notices WHERE id=?", (nid,)).fetchone()
    conn.close()
    chk(row_n is not None, "③ 막힌 뒤 공지가 실제로 남아 있다(삭제 안 됨)", bool(row_n))

    # ══════════════════════════════════════════════════════════
    print("\n[4] 실행 — partner_accounts.pick() --ids 안전검사")
    # ──────────────────────────────────────────────────────────
    import partner_accounts as PA
    conn = DB.get_db()
    p_gone = conn.execute(
        "INSERT INTO partners(name,partner_type,status,biz_no) "
        "VALUES('검증퇴출54','시행사','퇴출','1208136214')").lastrowid
    p_live = conn.execute(
        "INSERT INTO partners(name,partner_type,status,biz_no) "
        "VALUES('검증활성54','시행사','활성','1208136214')").lastrowid
    rows_ids = PA.pick(conn, "", "", [p_gone, p_live], 20, False)
    conn.close()
    got_ids = {r["id"] for r in rows_ids}
    chk(p_gone not in got_ids,
        "★★★ ④ --ids 로 지정해도 퇴출 업체는 빠진다(고치기 전엔 포함됨)", got_ids)
    chk(p_live in got_ids, "④ 활성 업체는 그대로 포함된다(과잉차단 아님)", got_ids)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드54 실측 준비/실행", f"{type(e).__name__} {e}")
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
