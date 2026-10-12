# -*- coding: utf-8 -*-
"""팝빌 연동 점검 — 키를 넣은 뒤 **어디까지 됐고 어디서 막혔는지** 한 번에 본다.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

■ 왜 필요한가
  팝빌 오류는 `[-99004] …` 처럼 숫자 코드로만 온다. 키를 넣고 발송이 안 될 때
  ①연동인증이 틀렸는지 ②회원 가입이 안 됐는지 ③발신번호 등록이 안 됐는지
  ④잔액이 없는지 구분이 안 된다. 그걸 순서대로 확인해 **한국어로** 알려 준다.

■ 무엇을 하는가 (읽기만 — 마지막 단계만 예외)
    1. 키가 다 있는가          .env 확인
    2. 연동인증이 통하는가      checkIsMember
    3. 회원으로 등록돼 있는가   getCorpInfo
    4. 발신번호가 등록됐는가    getSenderNumberList  ← 여기서 가장 많이 막힌다
    5. 잔액이 있는가            getBalance
    6. (--send 일 때만) 실제 1건 발송 + 전송 상태 조회

■ 테스트베드
  POPBILL_TEST=1 이면 팝빌 **테스트베드**에 붙는다 — 과금도 실수신도 없다.
  단, 테스트베드에도 **발신번호는 따로 등록**해야 한다(운영과 별개다).

■ 쓰는 법
    python popbill_check.py                    # 읽기 점검만
    python popbill_check.py --send 01012345678 # 실제 1건 보내 끝까지 확인
"""
import os
import sys
import time
import argparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
import envload
import notify_popbill as NP

OK, FAIL, WARN = "  ✔", "  ✖", "  ▲"


def _load_env():
    """.env 를 읽어 환경변수에 얹는다 — 서버와 같은 값으로 점검하기 위해서.

    ⚠⚠ [라운드272] 예전엔 이 함수가 직접 파싱했는데, 모든 진입점
      (app.py/wsgi.py/serve_waitress.py/manage.py)이 이미 공유하는
      envload.py 와 달리 값의 따옴표를 안 벗겼다 — POPBILL_LINK_ID="ABC"
      처럼 따옴표로 감싼 .env 를 쓰면 이 도구만 따옴표까지 낀 값을 읽어
      "LinkID 가 틀렸습니다"라는 오탐을 낸다(실측). "서버와 같은 값으로
      점검한다"는 이 함수 자신의 목적을 지키려면 서버가 실제로 쓰는 바로
      그 로더를 써야 한다 — 직접 파싱하지 않고 위임한다.
    """
    envload.load_dotenv()


def _mask(s, keep=4):
    s = (s or "").strip()
    return (s[:keep] + "…" + s[-2:]) if len(s) > keep + 2 else ("(비어 있음)" if not s else "…")


def main():
    ap = argparse.ArgumentParser(description="팝빌 연동 점검")
    ap.add_argument("--send", metavar="휴대전화",
                    help="실제로 1건 보내 끝까지 확인 (테스트베드면 과금·실수신 없음)")
    a = ap.parse_args()

    _load_env()
    st = NP.status()
    cfg_test = st["test_mode"]
    print("=" * 66)
    print(f"  팝빌 연동 점검 — {'테스트베드' if cfg_test else '★ 운영(실발송·과금)'}")
    print("=" * 66)
    #  ⚠⚠ [라운드272] 이 도구는 매번 새 프로세스로 뜨므로 라운드262가 막은
    #    "키 교체 후 재시작 전"(notify_popbill._cache 가 옛 키를 든 채
    #    살아있는) 상태를 이 프로세스 자신은 절대 겪을 수 없다 — 그래서
    #    이 점검이 전부 ✔ 로 끝나도, 그건 "이 프로세스 기준으로는 문제
    #    없다"는 뜻일 뿐 이미 떠 있는 운영 서버(app.py)가 재시작됐다는
    #    보장이 아니다(실측: 두 프로세스를 나란히 흉내내 재현 — 이 도구는
    #    100% 성공으로 나오는 바로 그 순간 운영 서버는 라운드262 가드로
    #    발송을 계속 거부하고 있을 수 있었다). 이 도구 자신의 진단만으론
    #    알 수 없는 사실이라 매번 알린다.
    print("  ⚠ 이 결과는 방금 새로 시작한 이 점검 프로세스 기준입니다.")
    print("    키를 교체했다면 이미 떠 있는 운영 서버(app.py)도 반드시")
    print("    재시작하세요 — 여기서 전부 ✔ 가 나와도, 운영 서버가 재시작")
    print("    전이면 실제 발송은 계속 거부되고 있을 수 있습니다.")

    # ── 1. 키 ────────────────────────────────────────────────
    print("\n[1] 키 설정")
    if not st["sdk_installed"]:
        print(FAIL, "popbill SDK 가 없습니다 →  pip install popbill")
        return 1
    print(OK, "popbill SDK 설치됨")
    if st["missing"]:
        print(FAIL, "아직 안 채운 값: " + ", ".join(st["missing"]))
        print("      .env 에 넣고 다시 실행하세요. 값을 받는 곳은")
        print("      deploy/팝빌_연동가이드.md 에 적어 두었습니다.")
        return 1
    c = NP._cfg()
    print(OK, f"LinkID {_mask(c['link_id'])} · SecretKey {_mask(c['secret_key'])}")
    print(OK, f"사업자번호 {c['corp_num']} · 발신번호 {c['sender']}")
    if not st["ats_template"]:
        print(WARN, "알림톡 템플릿(POPBILL_ATS_TEMPLATE)이 없습니다 — "
                    "알림톡 건도 **문자로** 나갑니다(정상 동작).")

    pb = NP._sdk()
    svc, _ = NP._services()

    def step(no, title, fn):
        print(f"\n[{no}] {title}")
        try:
            return True, fn()
        except pb.PopbillException as ex:
            print(FAIL, f"팝빌 오류 [{ex.code}] {ex.message}")
            print("      " + _hint(ex.code))
            return False, None
        except Exception as ex:                       # 네트워크 등
            print(FAIL, f"{type(ex).__name__}: {ex}")
            return False, None

    # ── 2. 연동인증 ─────────────────────────────────────────
    #  SDK 시그니처는 checkIsMember(CorpNum) — LinkID 는 서비스 생성 때 이미 들어갔다.
    #  (문서 예제만 보고 인자를 하나 더 넘겼다가 TypeError 로 확인했다)
    ok2, joined = step(2, "연동인증(LinkID·SecretKey)",
                       lambda: svc.checkIsMember(c["corp_num"]))
    if not ok2:
        return 1
    print(OK, "연동인증이 통과했습니다.")

    # ── 3. 회원 등록 ────────────────────────────────────────
    if not joined:
        print(FAIL, f"사업자번호 {c['corp_num']} 가 이 연동사업자의 회원으로 "
                    f"등록돼 있지 않습니다.")
        print("      팝빌 사이트에서 회원 가입(또는 연동회원 등록)을 먼저 하세요.")
        return 1
    ok3, info = step(3, "회원 정보", lambda: svc.getCorpInfo(c["corp_num"]))
    if ok3 and info:
        print(OK, f"{getattr(info, 'corpName', '(상호 미상)')} · "
                  f"대표 {getattr(info, 'ceoname', '-')}")

    # ── 4. 발신번호 ─────────────────────────────────────────
    ok4, lst = step(4, "발신번호 등록 상태",
                    lambda: svc.getSenderNumberList(c["corp_num"]))
    if ok4:
        nums = {NP.normalize_phone(getattr(x, "number", "")) or
                str(getattr(x, "number", "")).replace("-", ""): x for x in (lst or [])}
        mine = NP.normalize_phone(c["sender"]) or c["sender"]
        if not nums:
            print(FAIL, "등록된 발신번호가 없습니다.")
            print("      ⚠ 테스트베드에도 발신번호를 **따로** 등록해야 합니다.")
            print("      팝빌 콘솔 > 문자 > 발신번호 관리 에서 등록하세요"
                  "(통신사 심사 1~2일).")
        elif mine in nums:
            print(OK, f"발신번호 {c['sender']} 등록 확인")
        else:
            print(FAIL, f"발신번호 {c['sender']} 가 등록 목록에 없습니다.")
            print("      등록된 번호: " + ", ".join(list(nums)[:5]))
            print("      .env 의 POPBILL_SENDER 를 등록된 번호로 맞추거나, "
                  "그 번호를 등록하세요.")

    # ── 5. 잔액 ────────────────────────────────────────────
    ok5, bal = step(5, "잔액", lambda: svc.getBalance(c["corp_num"]))
    if ok5:
        if cfg_test:
            print(OK, f"테스트베드 잔액 {bal} (테스트베드는 과금되지 않습니다)")
        elif float(bal or 0) <= 0:
            print(FAIL, f"잔액 {bal} — 운영 모드인데 충전이 없어 발송이 실패합니다.")
        else:
            print(OK, f"잔액 {bal}")

    # ── 6. 실제 발송 ───────────────────────────────────────
    if not a.send:
        print("\n" + "-" * 66)
        print("  읽기 점검 끝. 실제로 보내 보려면:")
        print("    python popbill_check.py --send 010XXXXXXXX")
        return 0

    print(f"\n[6] 실제 발송 → {NP.mask_phone(NP.normalize_phone(a.send) or '')}")
    if not cfg_test:
        print(WARN, "★ 운영 모드입니다 — 실제로 문자가 나가고 과금됩니다.")
    body = "[복구온] 연동 점검 문자입니다. 이 문자가 보이면 문자 발송이 정상입니다."
    sent, detail = NP.send(a.send, body, channel="문자")
    print((OK if sent else FAIL), detail)
    if not sent:
        return 1
    #  접수번호로 전송 상태까지 확인한다 — '접수됐다'와 '도착했다'는 다르다
    rcpt = detail.split("접수")[-1].split("→")[0].strip()
    if rcpt:
        time.sleep(3)
        try:
            res = svc.getMessages(c["corp_num"], rcpt)
            for m in (res or [])[:3]:
                print(OK, f"전송 상태 {getattr(m,'stateCode','?')} · "
                          f"{getattr(m,'result','')} {getattr(m,'resultCode','')}")
        except Exception as ex:
            print(WARN, f"상태 조회는 실패했지만 접수는 됐습니다 ({ex})")
    return 0


def _hint(code):
    """팝빌 오류 코드 → 사람 말."""
    c = str(code)
    #  ⚠ 실제 코드는 9자리다(-99004021 등). 앞자리로 갈래를 나눈 뒤 정확한 것만 덧붙인다.
    #    (문서에 적힌 5자리로만 표를 만들었다가 하나도 안 맞는 것을 실행으로 확인했다)
    #  ⚠⚠ [라운드658] -99004022/-99004023 는 실제로 "생성할 링크아이디정보/서비스
    #    목록이 입력되지 않았습니다"였다(연동사업자가 신규 LinkID 를 발급할 때 쓰는
    #    관리자용 API 오류) — 이 도구를 쓰는 일반 연동사업자의 checkIsMember 등에서는
    #    나올 수 없는데도 "SecretKey 가 틀렸다"는 그럴듯하지만 근거 없는 안내를 하고
    #    있었다(공식 linkhub-sdk/popbill.exception 저장소 990_linkhub.csv 대조로 확인
    #    — 실제 서명불일치 코드는 -99010007 "권한요청 정보의 서명이 일치하지
    #    않습니다"였다). 지어낸 두 값을 지우고 진짜 코드로 교체 — "정확한 것만
    #    덧붙인다"는 이 함수 자신의 원칙을 지킨다.
    exact = {
        "-99004021": "LinkID 가 틀렸습니다 — 팝빌 > 연동관리 > 연동인증 관리 의 값을 그대로 넣으세요.",
        "-99010007": "연동인증 서명이 맞지 않습니다 — SecretKey 를 다시 확인하세요.",
    }
    if c in exact:
        return exact[c]
    if c.startswith("-99004"):
        return ("연동인증(LinkID·SecretKey)이 맞지 않습니다. "
                "테스트베드용/운영용 키가 뒤바뀌지 않았는지도 보세요.")
    if c.startswith("-99005") or c.startswith("-99"):
        return "연동인증 계열 오류입니다 — LinkID·SecretKey 와 테스트/운영 설정을 확인하세요."
    if c.startswith("-1000"):
        return "회원 정보 오류입니다 — 사업자번호(숫자 10자리)와 팝빌 가입 여부를 확인하세요."
    #  ⚠⚠ [라운드658] 원래는 "-100 으로 시작하거나 '1004' 를 포함하면"이었다 — 실제
    #    발신번호 오류(예: "등록되지 않은 발신번호입니다")는 전부 "-15001" 대역에
    #    있고 "1004" 를 포함하는 코드는 하나도 없다(공식 문서 전수 대조로 확인,
    #    즉 옛 조건은 진짜 발신번호 오류를 단 하나도 못 잡았다). 같은 "-15001"
    #    대역에는 수신거부(080)번호 관리 오류(-15001001~008, 015)도 섞여 있어
    #    prefix 만으로는 부정확하므로, 발신번호 자체를 가리키는 코드만 정확히
    #    골라 쓴다(-15001004 는 "삭제할 수신거부번호가 입력되지 않았습니다"로
    #    발신번호와 무관 — 옛 조건은 이걸 오탐으로 잡고 있었다).
    if c in ("-15001009", "-15001010", "-15001011",
             "-15001012", "-15001013", "-15001014"):
        return "발신번호가 등록·승인되지 않았습니다(테스트베드도 별도 등록 필요)."
    return "팝빌 오류 코드입니다 — deploy/팝빌_연동가이드.md 를 참고하세요."


def demo():
    """python popbill_check.py --self-check 없이도 안전하게 도는지 확인용."""
    #  실제로 받은 코드로 검사한다 — 문서에 적힌 5자리가 아니라 9자리가 온다
    assert "LinkID" in _hint("-99004021"), _hint("-99004021")
    assert "연동인증" in _hint("-99004999")
    assert "연동인증" in _hint("-99010007")  # [라운드658] 실제 서명불일치 코드
    #  [라운드658] "-1004"(가짜 합성코드) 대신 실제 발신번호 미등록 코드로 교체
    assert "발신번호" in _hint("-15001014")
    assert _mask("abcdefghij") .startswith("abcd")
    assert _mask("") == "(비어 있음)"
    print("자체 점검 통과")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        demo()
    else:
        sys.exit(main())
