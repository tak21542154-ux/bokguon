# -*- coding: utf-8 -*-
"""외부 접속 2단계 인증(TOTP) 검증.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

이 기능의 가장 위험한 실패는 **비밀번호만으로 들어가지는 것**(2단계가 이름뿐)과
**정당한 관리자가 영원히 잠기는 것**이다. 그 둘을 최우선으로 검사한다.
실서버를 HTTP 로 두드려 확인한다 — 함수 단위가 아니라 실제 관문을 본다.
"""
import io
import os
import sys
import json
import time
import secrets
import sqlite3
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import totp as TOTP

#  ⚠ 기본값은 **검증 서버(8799)** 다. 8771 은 운영이라, 따로 실행하면
#    운영에 임시 관리자 계정을 만들고 2단계 인증까지 켜게 된다
#    (끝나면 지우긴 하지만, 중간에 죽으면 그대로 남는다).
BASE = os.environ.get("BOKGUON_TEST_BASE", "http://127.0.0.1:8799")
DB_PATH = "bokguon.db"
OK = FAIL = 0
USER = "otptest_" + secrets.token_hex(3)
PW = "Otp!" + secrets.token_hex(8)


def chk(cond, label, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}   {detail}")


class Client:
    """쿠키를 유지하는 최소 HTTP 클라이언트 (세션 흐름을 그대로 본다)."""

    def __init__(self):
        self.cookie = ""
        self.csrf = ""

    def call(self, method, path, data=None, headers=None):
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(BASE + path, data=body, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Origin", BASE)
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        if self.csrf:
            req.add_header("X-CSRF-Token", self.csrf)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            r = urllib.request.urlopen(req, timeout=15)
            status, raw = r.status, r.read()
            sc = r.headers.get_all("Set-Cookie") or []
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
            sc = e.headers.get_all("Set-Cookie") or []
        for c in sc:
            if c.split("=")[0].strip() == "session":
                self.cookie = c.split(";")[0]
        try:
            d = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return status, {}
        if d.get("csrf"):
            self.csrf = d["csrf"]      # 로그인 성공 시 발급되는 토큰을 이후 요청에 붙인다
        return status, d


def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def main():
    print("=" * 70)
    print("  외부 접속 2단계 인증 검증")
    print("=" * 70)

    # 서버 정책이 off 면 이 검증은 성립하지 않는다(관문 자체가 없다).
    #  실패로 보고하면 "깨진 것"으로 오해하므로, 왜 못 도는지 밝히고 건너뛴다.
    probe = Client()
    st, d = probe.call("GET", "/healthz")
    import app as _A
    if _A.OTP_POLICY == "off":
        print("\n  [건너뜀] 2단계 인증이 꺼져 있습니다(BOKGUON_OTP_POLICY=off).")
        print("           검증하려면 .env 에서 external 또는 always 로 바꾸고 서버를 다시 띄우세요.")
        print("-" * 70)
        return 0

    import db as DB
    conn = db()
    conn.execute("DELETE FROM admins WHERE username=?", (USER,))
    conn.execute(
        "INSERT INTO admins(username, password_hash, name, role, must_change_pw, created_at) "
        "VALUES(?,?,?,?,0,?)",
        (USER, DB.hash_pw(PW), "OTP검증", "중간관리자", DB.now()))
    conn.commit()
    aid = conn.execute("SELECT id FROM admins WHERE username=?", (USER,)).fetchone()["id"]

    try:
        # ── 1. 등록 전 — 내부에서는 비밀번호만으로 통과 ────────────
        print("\n[1] 미등록 상태 (external 정책, 로컬 접속)")
        c = Client()
        st, d = c.call("POST", "/api/login", {"username": USER, "password": PW})
        chk(st == 200 and d.get("ok"), "내부 접속은 비밀번호만으로 로그인", (st, d.get("error")))
        st, d = c.call("GET", "/api/me/otp")
        chk(st == 200 and d.get("enabled") is False, "2단계 상태 = 꺼짐", d)
        chk(d.get("internal_now") is True, "로컬을 내부망으로 인식", d.get("internal_now"))
        chk(d.get("required_for_external") is True, "★ 외부 접속엔 필수라고 알림(법령 안내)", d)

        # ── 2. 등록 절차 ───────────────────────────────────────────
        print("\n[2] 등록 — 코드 확인 전에는 켜지지 않는다")
        st, setup = c.call("POST", "/api/me/otp/setup", {})
        chk(st == 200 and setup.get("secret") and setup.get("uri"), "비밀키·QR 발급", st)
        chk(setup.get("qr_svg", "").startswith("<svg"), "QR SVG 생성")
        secret = setup["secret"]
        st, d = c.call("GET", "/api/me/otp")
        chk(not d.get("enabled"), "★ 코드 확인 전에는 여전히 꺼짐(잘못 등록해 잠기지 않게)")
        st, d = c.call("POST", "/api/me/otp/confirm", {"code": "000000"})
        chk(st == 400, "틀린 코드로는 못 켬", st)
        st, d = c.call("POST", "/api/me/otp/confirm", {"code": TOTP.code_now(secret)})
        chk(st == 200 and len(d.get("recovery_codes") or []) == 8,
            "★ 맞는 코드 → 켜짐 + 복구 코드 8장 발급", st)
        codes = d["recovery_codes"]
        row = conn.execute("SELECT totp_enabled, totp_secret FROM admins WHERE id=?", (aid,)).fetchone()
        chk(row["totp_enabled"] == 1, "DB 에 켜짐 기록")
        stored = {r["code_hash"] for r in conn.execute(
            "SELECT code_hash FROM admin_recovery_codes WHERE admin_id=?", (aid,))}
        chk(all(TOTP.hash_recovery(x) in stored for x in codes), "복구 코드는 해시로만 저장")
        chk(not any(x in str(stored) for x in codes), "★ 복구 코드 원문이 DB 에 없음")

        # ── 3. 로그인 관문 (핵심) ─────────────────────────────────
        print("\n[3] 로그인 관문 — 비밀번호만으로는 못 들어간다")
        c2 = Client()
        st, d = c2.call("POST", "/api/login", {"username": USER, "password": PW})
        chk(st == 200 and not d.get("ok") and d.get("need_otp"),
            "비밀번호 맞아도 ok=False, 코드 요구", (st, d))
        st, d = c2.call("GET", "/api/me")
        chk(st in (401, 403), "★★ 대기 상태에서 관리자 API 접근 차단", st)
        st, d = c2.call("GET", "/api/cases")
        chk(st in (401, 403), "★★ 대기 상태에서 사건 조회도 차단", st)
        st, d = c2.call("POST", "/api/login/otp", {"code": "000000"})
        chk(st == 401 and d.get("need_otp"), "틀린 코드 거부", st)
        # 등록 확인에 쓴 코드는 이미 소진됐다 — 다음 구간 코드를 써야 한다.
        # (같은 코드로 시도하면 '이미 사용한 코드'라고 정확히 안내하는지도 함께 본다)
        st, d = c2.call("POST", "/api/login/otp", {"code": TOTP.code_now(secret)})
        chk(st == 401 and "이미 사용" in (d.get("error") or ""),
            "★ 등록에 쓴 코드 재사용 → '틀림'이 아니라 '이미 사용'으로 안내", d.get("error"))
        print("       (다음 코드 대기 31초)")
        time.sleep(31)
        code = TOTP.code_now(secret)
        st, d = c2.call("POST", "/api/login/otp", {"code": code})
        chk(st == 200 and d.get("ok") and d.get("csrf"), "★ 맞는 코드 → 로그인 완료 + CSRF 발급", (st, d.get("error")))
        st, d = c2.call("GET", "/api/me")
        chk(st == 200, "이제 관리자 API 정상 접근")

        # ── 4. 코드 재사용 차단 ───────────────────────────────────
        print("\n[4] 같은 코드 재사용 차단")
        c3 = Client()
        c3.call("POST", "/api/login", {"username": USER, "password": PW})
        st, d = c3.call("POST", "/api/login/otp", {"code": code})
        chk(st == 401, "★★ 방금 쓴 코드는 다시 못 씀(어깨너머·재전송 방어)", (st, d.get("error")))
        st, d = c3.call("GET", "/api/me")
        chk(st in (401, 403), "재사용 실패 후에도 접근 차단 유지", st)

        # ── 5. 복구 코드 ──────────────────────────────────────────
        print("\n[5] 복구 코드 — 폰을 잃어도 들어올 수 있다")
        c4 = Client()
        c4.call("POST", "/api/login", {"username": USER, "password": PW})
        st, d = c4.call("POST", "/api/login/otp", {"code": codes[0]})
        chk(st == 200 and d.get("ok"), "★ 복구 코드로 로그인", (st, d.get("error")))
        chk(d.get("recovery_left") == 7, "남은 장수 안내", d.get("recovery_left"))
        c5 = Client()
        c5.call("POST", "/api/login", {"username": USER, "password": PW})
        st, d = c5.call("POST", "/api/login/otp", {"code": codes[0]})
        chk(st == 401, "★ 쓴 복구 코드는 1회용", st)
        st, d = c5.call("POST", "/api/login/otp", {"code": codes[1].upper().replace("-", "")})
        chk(st == 200, "복구 코드 대소문자·하이픈 무관", st)
        used = conn.execute(
            "SELECT COUNT(*) n FROM admin_recovery_codes WHERE admin_id=? AND used_at IS NOT NULL",
            (aid,)).fetchone()["n"]
        chk(used == 2, "쓴 코드는 삭제가 아니라 사용시각 기록(추적 가능)", used)

        # ── 6. 시도 횟수 제한 ─────────────────────────────────────
        print("\n[6] 무차별 대입 방어")
        c6 = Client()
        c6.call("POST", "/api/login", {"username": USER, "password": PW})
        last = None
        for i in range(6):
            last = c6.call("POST", "/api/login/otp", {"code": f"{i:06d}"})
        chk(last[0] == 429, "★ 코드 5회 실패 → 대기 세션 폐기", last[0])
        st, d = c6.call("GET", "/api/me")
        chk(st in (401, 403), "폐기 후 접근 불가", st)

        # ── 7. 대기 세션 만료 ─────────────────────────────────────
        print("\n[7] 대기 세션 만료")
        # [Windows] 운영 서버가 연 로그 파일을 검증까지 함께 열면 회전이 실패한다 — 자기 파일로.
        os.environ.setdefault("BOKGUON_LOG_FILE",
                              os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "logs", "test.log"))
        import app as A
        chk(A.OTP_PENDING_SEC <= 600, "대기 시간이 10분 이하", A.OTP_PENDING_SEC)
        chk(A.OTP_MAX_TRIES <= 10, "시도 횟수 상한이 합리적", A.OTP_MAX_TRIES)
        chk("/api/login/otp" in A.CSRF_EXEMPT, "OTP 제출은 CSRF 면제(대신 출처 검사)")
        chk(any(r[1].pattern == r"^/api/login/otp$" for r in A.RATE_RULES),
            "★ OTP 경로에 IP 레이트리밋 존재(로그인 반복으로 초기화 못 하게)")

        # ── 8. 외부 IP 정책 판정 ──────────────────────────────────
        print("\n[8] 내부/외부 판정")
        chk(A._is_internal_ip("127.0.0.1") and A._is_internal_ip("192.168.0.5"),
            "루프백·사설망 = 내부")
        chk(not A._is_internal_ip("106.255.82.51"), "★ 공인 IP = 외부")
        chk(not A._is_internal_ip("garbage"), "★ 판독 불가 IP 는 외부로 취급(안전한 쪽)")
        u = dict(conn.execute("SELECT * FROM admins WHERE id=?", (aid,)).fetchone())
        u["totp_enabled"], u["totp_secret"] = 0, None
        chk(A._otp_required(u, ip="127.0.0.1")[0] == "no",
            "미등록 + 내부 → 통과(사무실에서 잠기지 않음)")
        need, why = A._otp_required(u, ip="106.255.82.51")
        chk(need == "block" and "사무실" in why,
            "★★ 미등록 + 외부 → 차단 + 등록 방법 안내(법령 §6④)", (need, why[:40]))
        u["totp_enabled"], u["totp_secret"] = 1, "X" * 32
        chk(A._otp_required(u, ip="106.255.82.51")[0] == "verify",
            "★ 등록 + 외부 → 코드 요구")
        chk(A._otp_required(u, ip=None)[0] in ("verify", "block"),
            "요청 밖에서 판정 불가 시 안전한 쪽(외부)으로", A._otp_required(u, ip=None)[0])

        # ── 9. 해제 ───────────────────────────────────────────────
        print("\n[9] 해제 — 비밀번호 재확인 필수")
        st, d = c2.call("POST", "/api/me/otp/disable", {"password": "틀린비번"})
        chk(st == 401, "★ 세션만 있고 비밀번호 모르면 못 끔", st)
        st, d = c2.call("POST", "/api/me/otp/disable", {"password": PW})
        chk(st == 200, "비밀번호 확인 후 해제", st)
        row = conn.execute("SELECT totp_enabled, totp_secret FROM admins WHERE id=?", (aid,)).fetchone()
        chk(row["totp_enabled"] == 0 and not row["totp_secret"], "비밀키까지 지움")
        left = conn.execute("SELECT COUNT(*) n FROM admin_recovery_codes WHERE admin_id=?",
                            (aid,)).fetchone()["n"]
        chk(left == 0, "복구 코드도 함께 폐기")
        st, d = c2.call("POST", "/api/login", {"username": USER, "password": PW})
        chk(st == 200 and d.get("ok"), "해제 후 비밀번호만으로 로그인(내부)", st)

    finally:
        conn.execute("DELETE FROM admin_recovery_codes WHERE admin_id=?", (aid,))
        conn.execute("DELETE FROM admins WHERE username=?", (USER,))
        conn.execute("DELETE FROM login_attempts WHERE username=?", (USER,))
        conn.commit()
        conn.close()

    print("-" * 70)
    print(f"  통과 {OK} · 실패 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
