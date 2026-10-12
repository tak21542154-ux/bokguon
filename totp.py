# -*- coding: utf-8 -*-
"""일회용 비밀번호(TOTP) — 외부 접속용 2단계 인증.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

**왜 필요한가 (선택 기능이 아니다)**
개인정보 안전성 확보조치 기준 제6조 제4항 — 개인정보취급자가 정보통신망을 통해
**외부에서** 개인정보처리시스템에 접속하려는 경우 인증서·보안토큰·**일회용
비밀번호** 등 안전한 인증수단 또는 안전한 접속수단(VPN·전용선)을 적용해야 한다.
복구온 콘솔에는 피해자 연락처·협력사 계좌가 있고, 이제 인터넷에 열린다.
비밀번호 하나로는 이 조항을 충족하지 못한다.

RFC 6238(TOTP) / RFC 4226(HOTP) 구현. 표준 라이브러리만 쓴다.
구글 인증기(Google Authenticator)·MS Authenticator·카카오 등 어떤 앱과도 호환.

**이 모듈은 db/app 을 import 하지 않는다** — 순수 계산. 저장·정책은 호출자 몫.
"""
import re
import hmac
import time
import base64
import struct
import hashlib
import secrets

DIGITS = 6
PERIOD = 30          # 코드 유효 30초
DRIFT = 1            # 앞뒤 1구간(±30초)까지 허용 — 폰 시계 오차 대비
ISSUER = "복구온"


def new_secret():
    """새 비밀키(base32 32자) — 사용자 폰에 등록할 값."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _code_at(secret, counter):
    try:
        key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    except (ValueError, TypeError):
        return None
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    num = struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF
    return str(num % (10 ** DIGITS)).zfill(DIGITS)


def code_now(secret, at=None):
    """현재 코드 — 검증용이 아니라 자체 점검·테스트용."""
    return _code_at(secret, int((at if at is not None else time.time()) // PERIOD))


def verify(secret, code, last_counter=None, at=None):
    """코드 검증. 반환 (ok, counter, reason).

    · ±DRIFT 구간까지 허용(폰 시계 오차).
    · **재사용 차단**: last_counter 를 주면 그 값 이하의 구간은 거부한다.
      같은 코드를 두 번 쓰지 못하게 하는 것(어깨 훔쳐보기·중간자 재전송 방어).
      호출자는 성공 시 돌려받은 counter 를 저장해 다음 검증에 넘겨야 한다.

    reason 은 "ok" / "used"(맞지만 이미 쓴 코드) / "bad"(틀림) / "form"(형식 오류).
    ⚠ 'used' 를 'bad' 와 뭉뚱그리면 안 된다 — 등록 직후 같은 30초 안에 로그인한
      사용자가 "코드가 맞지 않습니다"를 보고 앱·시계를 의심하며 헤맨다.
      실제로는 30초만 기다리면 되는 상황이므로 그대로 알려 준다.
    """
    code = re.sub(r"\D", "", code or "")
    if len(code) != DIGITS or not secret:
        return False, None, "form"
    now = int((at if at is not None else time.time()) // PERIOD)
    used = False
    for d in range(-DRIFT, DRIFT + 1):
        c = now + d
        exp = _code_at(secret, c)
        if not exp or not hmac.compare_digest(exp, code):
            continue
        if last_counter is not None and c <= last_counter:
            used = True                   # 맞는 코드지만 이미 쓴 구간
            continue
        return True, c, "ok"
    return False, None, ("used" if used else "bad")


def provisioning_uri(secret, account, issuer=ISSUER):
    """폰 앱에 등록할 otpauth:// URI (QR 로 만들 원본)."""
    from urllib.parse import quote
    label = quote(f"{issuer}:{account}", safe="")
    return (f"otpauth://totp/{label}?secret={secret}"
            f"&issuer={quote(issuer, safe='')}&algorithm=SHA1"
            f"&digits={DIGITS}&period={PERIOD}")


# ── 복구 코드 ─────────────────────────────────────────────────
#  폰을 잃으면 영구 잠금이다. 그래서 1회용 복구 코드를 함께 발급한다.
#  원문은 발급 순간에만 보여주고, DB 에는 해시만 남긴다(비밀번호와 같은 원칙).
RECOVERY_COUNT = 8


def new_recovery_codes(n=RECOVERY_COUNT):
    """사람이 받아 적을 수 있는 형태(xxxx-xxxx-xxxx-xxxx)로 n개."""
    #  ⚠⚠ [라운드269] 예전엔 4바이트(32비트, 43억 조합)였다 — hash_recovery()가
    #    솔트 없는 단일라운드 SHA256 이라(비밀번호 해시와 달리 이 정도로는
    #    브루트포스를 못 늦춘다), 실측으로 12코어 163초 만에 전체공간이
    #    뚫렸다(DB 유출 시나리오에서). hash_recovery() 는 길이에 무관하게
    #    그대로 동작하므로(정규화 후 해시할 뿐) 입력 길이만 늘리면 된다 —
    #    8바이트(64비트)면 같은 방법으로도 사실상 뚫을 수 없어진다.
    out = []
    for _ in range(n):
        raw = secrets.token_hex(8)          # 16 hex = 64비트
        out.append("-".join(raw[i:i + 4] for i in range(0, len(raw), 4)))
    return out


def hash_recovery(code):
    """복구 코드 해시 — 대소문자·하이픈 차이를 흡수한다."""
    norm = re.sub(r"[^0-9a-z]", "", (code or "").lower())
    return hashlib.sha256(("bokguon-recovery$" + norm).encode("utf-8")).hexdigest()


def qr_svg(uri, box=6):
    """otpauth URI 를 SVG QR 로. qrcode 패키지가 없으면 None(수동 입력으로 폴백).

    SVG 를 쓰는 이유: 서버에 Pillow 가 없어도 되고, CSP 아래에서 img 로 인라인
    삽입하지 않고 문서에 그대로 넣을 수 있다.
    """
    try:
        import qrcode
    except ImportError:
        return None
    try:
        q = qrcode.QRCode(border=2, box_size=box,
                          error_correction=qrcode.constants.ERROR_CORRECT_M)
        q.add_data(uri)
        q.make(fit=True)
        m = q.get_matrix()
    except Exception:
        return None
    n = len(m)
    side = n * box
    rects = []
    for y, row in enumerate(m):
        x = 0
        while x < n:
            if row[x]:
                run = 1
                while x + run < n and row[x + run]:
                    run += 1
                rects.append(f'<rect x="{x * box}" y="{y * box}" '
                             f'width="{run * box}" height="{box}"/>')
                x += run
            else:
                x += 1
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{side}" height="{side}" '
            f'viewBox="0 0 {side} {side}" shape-rendering="crispEdges">'
            f'<rect width="{side}" height="{side}" fill="#fff"/>'
            f'<g fill="#111">{"".join(rects)}</g></svg>')
