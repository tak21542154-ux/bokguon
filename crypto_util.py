# -*- coding: utf-8 -*-
"""민감정보 암호화 유틸 (AES-GCM AEAD).

근거: 「개인정보의 안전성 확보조치 기준」(개인정보보호위원회 고시 제2025-9호, 2025.10.31. 시행)
      제7조 제2항 — 신용카드번호·계좌번호는 암호화하여 저장해야 함.

설계 원칙
 - 암호화 키는 소스코드·DB에 두지 않고 환경변수(BOKGUON_ENC_KEY)로 주입한다.
 - AES-256-GCM(AEAD)으로 기밀성 + 무결성을 함께 보장한다.
 - 검색이 필요한 경우 암호문으로는 조회가 불가하므로 HMAC 블라인드 인덱스를 별도 사용한다.
"""
import io
import os
import sys
import base64
import hmac
import hashlib
import logging

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

#  ⚠ 윈도 기본 콘솔은 cp949 라 '—' 같은 문자를 print 하면(아래 __main__ 의
#    자체 점검 데모 마지막 줄) UnicodeEncodeError 로 죽는다. 이 파일은
#    app.py 가 import 하지만
#    (repair_estimate.py 의 방어가 그 경로에서만 우연히 이 파일도 구제한다)
#    "python crypto_util.py" 로 단독 실행하면 그 우연한 구제가 없어 그대로
#    죽는다(실측). 형제 점검 도구(check_tx_paths.py 등)가 이미 쓰는 방어를
#    그대로 옮긴다(round519).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

_log = logging.getLogger(__name__)

_ENV_KEY = "BOKGUON_ENC_KEY"
_ENV_IDX = "BOKGUON_INDEX_KEY"
_NONCE_BYTES = 12


class KeyMissingError(RuntimeError):
    pass


def _load_key(env_name, dev_fallback):
    raw = os.environ.get(env_name)
    if raw:
        try:
            key = base64.urlsafe_b64decode(raw)
        except Exception:
            key = raw.encode()
        if len(key) not in (16, 24, 32):
            #  ⚠ [라운드313] 이 길이검사는 "문자 개수"만 보므로, base64 문자열의
            #    길이는 그대로 두고 중간 한 글자만 다른 유효 base64 문자로 바뀐
            #    손상(복붙 중 커서가 밀려 겹쳐쓰기 등)은 구조적으로 못 잡는다 —
            #    디코드 후 바이트 길이가 정상 키와 완전히 같기 때문이다. 이 계층
            #    에서는 원리적으로 막을 수 없고, 실제 방어선은 manage.py check 의
            #    "계좌번호 암호화키 복호화 왕복 확인"(실제 저장된 암호문을 지금
            #    키로 열어보는 내용 기반 검증)이다 — 단, 계좌가 하나도 없는 신규
            #    배포 직후에는 그 검증 자체가 건너뛰어진다(경고만, 실패 아님).
            #    키를 새로 넣거나 바꿀 때마다 계좌가 하나라도 들어간 뒤 다시
            #    manage.py check 를 돌려 확인하는 것이 유일하게 확실한 방법.
            #  ⚠⚠ [라운드261] "키가 없다"는 아래(41-44행)에서 이미 막는데(운영은
            #    예외, 개발은 경고), "키는 있는데 형식이 틀렸다"는 여기서 완전히
            #    침묵한 채 SHA256 파생키로 넘어갔다 — 키 로테이션 중 .env 에
            #    붙여넣다 따옴표·개행·부분복사로 형식이 깨지면 이 파생키로 계속
            #    저장되는데 아무 신호가 없다. 나중에 값을 "제대로" 고치면 그
            #    순간부터 그 사이 저장된 값이 전부 안 열리는데, 형제(83행,
            #    라운드120)는 복호화 실패는 이미 로그를 남기지만 그 근본 원인
            #    (키 형식)에는 신호가 없어 증상만 한참 뒤에 사후로 남았다.
            _log.warning(
                "%s 형식이 올바르지 않습니다(디코드 후 %d바이트, 16/24/32바이트여야 "
                "함) — SHA256 파생키로 대체합니다. 값 자체는 로그에 남기지 않습니다.",
                env_name, len(key))
            key = hashlib.sha256(key).digest()
        return key
    if os.environ.get("BOKGUON_ENV", "dev").lower() == "prod":
        raise KeyMissingError(
            f"운영 모드에서는 {env_name} 환경변수가 필수입니다. "
            f"`python manage.py gen-keys` 로 생성해 .env 에 넣으세요.")
    # 개발 편의용 고정 키 — 운영에서는 절대 사용 금지.
    # 이 키로 암호화된 값은 소스만 있으면 누구나 복호화할 수 있으므로,
    # 개발 중에도 눈에 띄도록 매번 경고를 남긴다(운영 착각 방지).
    #  ⚠⚠ [라운드313] 예전엔 warnings 모듈을 썼다 — 그 모듈의 기본 필터는
    #    (메시지·카테고리·호출지점) 조합을 프로세스 생애 동안 기억해 **콜사이트당
    #    딱 1번만** 출력하고 그 뒤로는 영구 침묵한다. 이 함수를 같은 줄에서 반복
    #    호출하는 실사용 경로(app.py 의 계좌 저장 라우트가 encrypt() 와
    #    blind_index() 를 한 줄에서 부름)에서는, 키가 완전히 빠진 상태로 떠 있어도
    #    **최초 1건만** 뜨고 그 뒤 협력사 수백 곳이 등록되는 내내 조용히 개발용
    #    고정키로 계속 암호화된다 — 바로 위 주석의 "매번"이 실제로는 거짓이었다.
    #    이 파일의 다른 두 경고(47행 라운드261, 95행 라운드120)는 이미
    #    _log.warning() 을 쓰는데(로깅은 이런 자동 중복제거가 없어 호출마다
    #    확실히 남는다) 이 자리만 안 따라갔다 — 통일한다.
    _log.warning(
        "[복구온] %s 미설정 — 공개된 개발용 고정 키로 암호화합니다. "
        "운영 배포 전 반드시 .env 를 설정하세요.", env_name)
    return hashlib.sha256(dev_fallback.encode()).digest()


def encrypt(plaintext: str) -> str:
    """평문 → 'v1:base64(nonce+ciphertext)'."""
    if plaintext is None or plaintext == "":
        return ""
    key = _load_key(_ENV_KEY, "bokguon-dev-enc-key-do-not-use-in-prod")
    nonce = os.urandom(_NONCE_BYTES)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return "v1:" + base64.urlsafe_b64encode(nonce + ct).decode()


def decrypt(token: str) -> str:
    """'v1:...' → 평문. 실패 시 빈 문자열."""
    if not token:
        return ""
    if not token.startswith("v1:"):
        return token  # 평문 레거시 데이터 호환
    try:
        key = _load_key(_ENV_KEY, "bokguon-dev-enc-key-do-not-use-in-prod")
        raw = base64.urlsafe_b64decode(token[3:])
        nonce, ct = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
        return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
    except Exception as e:
        #  ⚠⚠ [라운드120] 예전엔 여기서 전부 조용히 "" 로 삼켰다 — 키가 교체되는데
        #    기존 암호문 재암호화 마이그레이션이 빠지면, 호출부 6곳(app.py) 전부가
        #    "협력사가 계좌를 안 넣었다"로 보이게 된다. 원인 진단에 로그가 전혀
        #    안 남아 담당자가 암호화 키 문제를 의심할 방법이 없었다 — 반환값(빈 문자열)
        #    자체는 그대로 두되(호출부 6곳의 기존 분기를 안 건드린다), 실패했다는
        #    사실만 남긴다. 암호문·키는 절대 로그에 넣지 않는다.
        _log.warning("복호화 실패 — 빈 문자열로 대체 (%s: %s)", type(e).__name__, e)
        return ""


def blind_index(value: str) -> str:
    """검색용 HMAC 인덱스 (암호문은 검색 불가하므로 별도 컬럼에 저장)."""
    if not value:
        return ""
    key = _load_key(_ENV_IDX, "bokguon-dev-index-key-do-not-use-in-prod")
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def mask_account(acct: str) -> str:
    """화면 표시용 마스킹 — 뒤 4자리만 노출."""
    if not acct:
        return ""
    digits = "".join(ch for ch in acct if ch.isdigit())
    if len(digits) <= 4:
        return "*" * len(digits)
    return "*" * (len(digits) - 4) + digits[-4:]


def mask_name(name: str) -> str:
    """화면 표시용 마스킹 — 첫 글자만 노출(라운드496)."""
    if not name:
        return ""
    return name[0] + "*" * (len(name) - 1) if len(name) > 1 else "*"


if __name__ == "__main__":
    sample = "110-234-567890"
    tok = encrypt(sample)
    print("평문   :", sample)
    print("암호문 :", tok)
    print("복호화 :", decrypt(tok))
    print("마스킹 :", mask_account(sample))
    print("인덱스 :", blind_index(sample)[:24], "...")
    assert decrypt(tok) == sample
    print("\n검증 통과 — 암호화/복호화 정상")
