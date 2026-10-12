# -*- coding: utf-8 -*-
"""팝빌 문자·알림톡 발송 어댑터 — 키만 넣으면 켜진다.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

설계 원칙 (repair_estimate 와 동일한 격리 구조):
  · 이 모듈은 db/app 을 import 하지 않는다 — 순수 어댑터. 어떤 알림을 언제
    보낼지는 호출자(app.sweep_send_notifications)가 정하고, 여기는 "이 번호로
    이 내용을" 만 안다.
  · 팝빌 SDK(popbill 패키지)와 API 키가 **둘 다** 있어야만 발송한다. 없으면
    ready()가 False 고, send()는 예외 없이 (False, 사유)를 돌려준다 —
    발송 실패가 업무 흐름(낙찰·정산)을 막는 일은 없다.
  · 시크릿은 절대 밖으로 내보내지 않는다 — status()에도 키 원문은 없다.

연동 절차(요약 — 상세는 deploy/팝빌_연동가이드.md):
  1) 팝빌 가입 후 연동인증 키(LinkID·SecretKey) 발급
  2) 발신번호 사전등록(통신사 심사 1~2일)
  3) .env 에 POPBILL_* 4개 채우고 pip install -r requirements.txt → 재시작
  4) POPBILL_TEST=1(기본)이면 테스트베드 — 과금·실수신 없이 전 구간 점검 가능

알림톡: 카카오 템플릿 승인 후 POPBILL_ATS_TEMPLATE 에 템플릿코드를 넣으면
'알림톡' 채널 건은 알림톡으로, 실패 시 팝빌이 문자로 자동 대체발송(AltSendType=C).
템플릿이 없으면 알림톡 채널 건도 그냥 문자로 나간다 — 그래서 "바로" 된다.
"""
import os
import re

# 필수 4개 — 이게 다 있어야 발송이 켜진다
REQUIRED = ("POPBILL_LINK_ID", "POPBILL_SECRET_KEY", "POPBILL_CORP_NUM", "POPBILL_SENDER")

# SMS 는 90바이트(EUC-KR)까지 — 넘으면 LMS 로 자동 전환. LMS 본문 상한 2,000바이트.
SMS_MAX_BYTES = 90
LMS_MAX_BYTES = 2000
LMS_SUBJECT = "[복구온] 알림"


def _env(key, default=None):
    """빈 문자열은 '설정 안 함'으로 본다 (app.env 와 같은 규칙)."""
    v = os.environ.get(key)
    if v is None or not v.strip():
        return default
    return v.strip()


def _sdk():
    try:
        import popbill
        return popbill
    except ImportError:
        return None


def _cfg():
    return {
        "link_id": _env("POPBILL_LINK_ID"),
        "secret_key": _env("POPBILL_SECRET_KEY"),
        "corp_num": re.sub(r"\D", "", _env("POPBILL_CORP_NUM") or ""),
        "sender": re.sub(r"\D", "", _env("POPBILL_SENDER") or ""),
        "user_id": _env("POPBILL_USER_ID"),
        "test": _env("POPBILL_TEST", "1") == "1",
        "ats_template": _env("POPBILL_ATS_TEMPLATE"),
    }


def status():
    """연동 상태 — 화면에 그대로 보여줄 수 있는 값만 (시크릿 없음)."""
    c = _cfg()
    missing = [k for k in REQUIRED if not _env(k)]
    sdk_ok = _sdk() is not None
    #  ⚠⚠ [라운드262] 키가 바뀌었는데 SDK 싱글턴 때문에 실제로는 안 바뀐
    #    상태 — 이 값을 ready 에 반영해야 "설정 화면은 초록인데 발송은
    #    옛 키로 나간다"는 조용한 불일치가 안 생긴다.
    rotated = _key_rotated_pending_restart()
    return {
        "sdk_installed": sdk_ok,
        "configured": not missing,
        "missing": missing,
        "test_mode": c["test"],
        "sender": c["sender"] or None,
        "ats_template": bool(c["ats_template"]),
        "ready": sdk_ok and not missing and not rotated,
        "key_rotated_pending_restart": rotated,
    }


def ready():
    return _sdk() is not None and not [k for k in REQUIRED if not _env(k)]


def normalize_phone(raw):
    """휴대전화 번호만 통과 — 문자·알림톡은 휴대폰으로만 닿는다."""
    d = re.sub(r"\D", "", raw or "")
    if d.startswith("8210"):          # +82 10 → 010
        d = "0" + d[2:]
    if d.startswith("01") and 10 <= len(d) <= 11:
        return d
    return None


def mask_phone(digits):
    d = re.sub(r"\D", "", digits or "")
    return f"{d[:3]}****{d[-4:]}" if len(d) >= 8 else "****"


#  ⚠⚠ [라운드301] "EUC-KR 바이트 기준"이라는 이름과 달리 실제로는 euc-kr
#    코덱으로 재던 것부터가 결함이었다 — 팝빌 공식 문서(SMS API)가 명시하는
#    규칙은 "한글·한자·특수문자는 2바이트"인데, euc-kr 코덱은 1987년
#    KS X 1001 완성형 2,350자에 없는 한글(예: '뷁')을 2바이트가 아니라
#    8바이트로 잰다(실측: 현대 한글 11,172자 중 8,822자·79%가 여기 걸림).
#    그 결과 흔치 않은 음절이 든 메시지는 실제론 SMS 로 충분한데 LMS 로
#    잘못 청구되거나(90바이트 문턱 오판), LMS 자체도 실제 2,000바이트
#    한도보다 훨씬 일찍 잘려 뒷부분이 조용히 사라졌다(실측: '뷁'×1000자를
#    2000바이트로 자르면 250자만 남음 — 실제 한도라면 1000자 전부 들어감).
#    cp949 는 완성형 코드페이지의 상위호환으로, 현대 한글 11,172자 전부를
#    예외 없이 2바이트로 잰다(실측 재확인) — 팝빌의 실제 규칙과 정확히
#    일치한다. errors="replace" 는 이모지 등 그 밖의 예외적 문자를 위해
#    그대로 남겨 둔다.
def _euckr_len(text):
    return len((text or "").encode("cp949", errors="replace"))


def _euckr_cut(text, limit):
    """CP949 바이트 기준으로 자른다 — 글자 중간이 잘리지 않게 한 글자씩."""
    out, used = [], 0
    for ch in text or "":
        n = len(ch.encode("cp949", errors="replace"))
        if used + n > limit:
            break
        out.append(ch)
        used += n
    return "".join(out)


# 서비스 객체 캐시 — 설정이 바뀌면(키 교체) 다시 만든다
#  ⚠⚠ [라운드262] "다시 만든다"는 이 파일만의 생각이다 — popbill SDK 의
#    PopbillBase 는 클래스당 인스턴스 하나만 두는 Singleton 이라(내부적으로
#    생성자 인자를 무시한다), pb.MessageService(new_id, new_secret) 를 다시
#    불러도 **프로세스 최초 생성 시점의 객체를 그대로 돌려주고 내부 키는
#    안 바뀐다**(실측: 두 번째 호출 뒤에도 물리적으로 같은 객체, 첫 키
#    그대로 인증). 그래서 sig 가 바뀌면 새로 만든다는 이 캐시는 실질적
#    효과가 없다 — 키 유출로 급히 교체했는데 프로세스를 재시작하지 않으면
#    화면(status())은 새 키가 "설정됨"이라 정확히 보여주면서도 실제 발송은
#    계속 옛(유출된) 키로 나간다. SDK 내부의 name-mangled private 속성을
#    억지로 덮어써 우회하는 건 SDK 버전이 바뀌면 조용히 깨지는 더 위험한
#    수라, 대신 "최초 생성 이후 설정이 달라졌다"는 사실 자체를 first_sig 로
#    기억해 두고 status()/send() 가 그 사실을 소리 내어 막는다.
_cache = {"sig": None, "msg": None, "kakao": None, "first_sig": None}


def _services():
    c = _cfg()
    sig = (c["link_id"], c["secret_key"], c["test"])
    if _cache["sig"] != sig:
        pb = _sdk()
        if pb is None:
            return None, None
        msg = pb.MessageService(c["link_id"], c["secret_key"])
        msg.IsTest = c["test"]
        kakao = pb.KakaoService(c["link_id"], c["secret_key"])
        kakao.IsTest = c["test"]
        _cache.update(sig=sig, msg=msg, kakao=kakao)
        if _cache["first_sig"] is None:
            _cache["first_sig"] = sig
    return _cache["msg"], _cache["kakao"]


def _key_rotated_pending_restart():
    """이 프로세스가 최초로 연동한 뒤 설정이 달라졌는가 — 그렇다면 SDK
    싱글턴 특성상 재시작 전까지는 그 변경이 실제로 적용되지 않는다."""
    if _cache["first_sig"] is None:
        return False
    c = _cfg()
    return (c["link_id"], c["secret_key"], c["test"]) != _cache["first_sig"]


def send(phone, message, channel="문자", request_id=None):
    """1건 발송. 반환 (ok, detail) — **어떤 경우에도 예외를 던지지 않는다.**

    channel '알림톡' + 템플릿 설정 시 알림톡(실패 시 문자 자동대체),
    그 외 전부 문자(90바이트 이하 SMS / 초과 LMS).

    request_id: 팝빌 RequestNum(전송요청번호) — 같은 값으로 다시 보내면
      팝빌 서버가 같은 요청으로 인식해 중복발송을 막는다(멱등키).
      ⚠⚠ [라운드262] 재시도는 이 함수가 아니라 호출자(app.sweep_send_
      notifications)가 한다 — 1차 시도에서 팝빌은 실제로 접수했는데
      응답 수신 중 네트워크가 끊기면 이 함수는 "실패"를 반환하고, 다음
      스윕이 같은 알림 행을 다시 이 함수로 보낸다. 이 값 없이는 팝빌이
      매번 새 메시지로 취급해 협력사가 같은 문자를 2~3회 받을 수 있었다.
      호출자가 안 넘기면(기본 None) 예전과 동일하게 동작한다(단발성
      테스트발송 등, 재시도 대상이 아닌 호출은 그대로 둔다).
    """
    st = status()
    if not st["ready"]:
        if st["key_rotated_pending_restart"]:
            why = "연동 키가 서버 시작 뒤에 바뀌었으나, SDK 특성상 서버를 재시작해야 실제로 적용됩니다(재시작 전까지 발송을 막습니다)"
        elif not st["sdk_installed"]:
            why = "SDK 미설치(pip install popbill)"
        else:
            why = "미설정: " + ", ".join(st["missing"])
        return False, f"팝빌 연동 안 됨 — {why}"
    to = normalize_phone(phone)
    if not to:
        return False, "휴대전화 번호가 아님"
    c = _cfg()
    body = (message or "").strip()
    if not body:
        return False, "보낼 내용이 없음"
    pb = _sdk()
    try:
        msg_svc, kakao_svc = _services()
        req_num = str(request_id) if request_id is not None else None
        if channel == "알림톡" and c["ats_template"]:
            alt = _euckr_cut(body, LMS_MAX_BYTES)
            receipt = kakao_svc.sendATS(
                c["corp_num"], c["ats_template"], c["sender"],
                body, alt, "C", "", to, "", c["user_id"], req_num)
            kind = "알림톡"
        elif _euckr_len(body) <= SMS_MAX_BYTES:
            receipt = msg_svc.sendSMS(
                c["corp_num"], c["sender"], to, "", body, "",
                False, c["user_id"], None, req_num)
            kind = "문자(SMS)"
        else:
            receipt = msg_svc.sendLMS(
                c["corp_num"], c["sender"], to, "", LMS_SUBJECT,
                _euckr_cut(body, LMS_MAX_BYTES), "", False, c["user_id"], None, req_num)
            kind = "문자(LMS)"
        mode = "테스트베드" if c["test"] else "운영"
        return True, f"팝빌 {kind} 접수 {receipt} → {mask_phone(to)} ({mode})"
    except pb.PopbillException as ex:
        return False, f"팝빌 오류 [{ex.code}] {ex.message}"
    except Exception as ex:                       # 네트워크 단절 등 — 흐름을 막지 않는다
        return False, f"발송 실패: {type(ex).__name__}: {ex}"
