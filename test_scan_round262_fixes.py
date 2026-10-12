# -*- coding: utf-8 -*-
"""스캔 262라운드 회귀 — notify_popbill.py(문자발송 어댑터) 결함 2건
   (문자발송 어댑터 감사 Agent 조사로 발견, 전부 독립 재검증 후 수정).

  [1] 키 교체가 "새 키로 바꿨다"고 거짓 보고 — popbill SDK 의 PopbillBase 는
      클래스당 인스턴스 하나만 두는 Singleton 이라 생성자 인자를 무시한다.
      pb.MessageService(new_id, new_secret) 를 다시 불러도 프로세스 최초
      생성 시점의 객체를 그대로 돌려주고 내부 키는 안 바뀐다 — 그런데 이
      파일의 캐시는 "sig 가 바뀌면 새로 만든다"고 믿고 있었다. 키 유출로
      급히 교체했는데 프로세스를 재시작하지 않으면, status()(운영 화면)는
      새 키가 "설정됨"이라 정확히 보여주면서도 실제 발송은 계속 옛(유출된)
      키로 나간다. SDK 내부를 억지로 덮어쓰는 대신 "최초 연동 뒤 설정이
      달라졌다"는 사실 자체를 감지해 ready=False 로 막는다(재시작 전까지
      발송 자체를 거부 — 옛 키로 계속 나가는 사고보다 안전).

  [2] 재시도 시 멱등키(RequestNum) 미사용 — sweep_send_notifications 가
      최대 3회 재시도하는데, 1차 시도에서 팝빌은 실제로 접수했지만 응답
      수신 중 네트워크가 끊기면 이 어댑터는 "실패"로 보고하고 다음 스윕이
      같은 알림 행을 requestNum 없이 또 보낸다 — 팝빌은 이를 새 메시지로
      취급해 협력사가 같은 문자를 2~3회 받을 수 있었다. notifications.id
      (재시도해도 안 바뀌는 값)를 RequestNum 으로 실어 보내 팝빌 서버의
      중복접수 거르기가 작동하게 한다.

      python test_scan_round262_fixes.py
"""
import importlib
import io
import os
import sys
import unittest.mock as mock

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


NP_SRC = read("notify_popbill.py")
APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 262라운드 회귀 — 팝빌 키교체 거짓보고·재시도 중복발송 차단")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk('"first_sig": None' in NP_SRC, "★★★★ 서비스 캐시가 최초 연동 시점의 설정을 별도로 기억한다")
chk("def _key_rotated_pending_restart():" in NP_SRC,
    "★★★★ 최초 연동 뒤 설정이 달라졌는지 판정하는 함수가 생겼다")
chk('"key_rotated_pending_restart": rotated' in NP_SRC,
    "★★★★ status() 응답에 이 상태가 노출된다")
chk('not st["ready"]' in NP_SRC and 'st["key_rotated_pending_restart"]' in NP_SRC,
    "★★★★ send() 가 이 상태일 때 발송을 거부한다(SDK 특성상 재시작 전까진 옛 키)")

chk("def send(phone, message, channel=\"문자\", request_id=None):" in NP_SRC,
    "★★★★ send() 가 멱등키(request_id)를 받는다")
i0 = NP_SRC.index("msg_svc, kakao_svc = _services()")
i1 = NP_SRC.index("except pb.PopbillException", i0)
send_body_calls = NP_SRC[i0:i1]
chk(send_body_calls.count("req_num") >= 3,
    "★★★★ SMS·LMS·알림톡 세 발송 경로 전부 RequestNum 을 실어 보낸다"
    "(한 경로만 고치는 형제누락 방지)")

i2 = APP_SRC.index("def sweep_send_notifications(")
i3 = APP_SRC.index("\ndef ", i2 + 10)
sweep_body = APP_SRC[i2:i3]
chk('request_id=n["id"]' in sweep_body,
    "★★★★★ 재시도 스윕이 알림 행의 고유 id 를 멱등키로 실어 보낸다")

# ============================================================
print("\n[2] 실행 — 키교체 감지·거부 + 멱등키 실제 전달 확인")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
try:
    import notify_popbill as CU
    importlib.reload(CU)

    _env_backup = dict(os.environ)
    _BASE = {
        "POPBILL_LINK_ID": "TESTLINK01",
        "POPBILL_SECRET_KEY": "SECRET_ORIGINAL",
        "POPBILL_CORP_NUM": "6568702554",
        "POPBILL_SENDER": "01000000000",
        "POPBILL_TEST": "1",
    }
    try:
        os.environ.update(_BASE)

        #  ── (a) 최초 연동 — 정상 ready, 회전 아님 ──
        st0 = CU.status()
        chk(st0["configured"] and not st0["key_rotated_pending_restart"],
            "STEP 최초 상태는 회전 아님으로 정상 판정된다", st0)
        #  실제 SDK 객체를 한 번 생성시켜 first_sig 를 확정한다(네트워크 호출 없음 —
        #  생성자는 자격만 저장, 실제 통신은 SDK 메서드 호출 시에만 일어난다)
        CU._services()

        #  ── (b) 프로세스를 안 껐는데 시크릿만 교체(실사고 재현) ──
        os.environ["POPBILL_SECRET_KEY"] = "SECRET_ROTATED"
        st1 = CU.status()
        chk(st1["configured"] and st1["key_rotated_pending_restart"] and not st1["ready"],
            "★★★★★ 키만 바뀌면(재시작 안 함) configured=True 인데도 ready=False 로 막는다"
            "(고치기 전엔 여기서 그대로 통과해 옛 키로 발송됐다)", st1)

        ok, detail = CU.send("010-1234-5678", "테스트")
        chk(not ok and "재시작" in detail,
            "★★★★★ send() 도 이 상태에서 명확한 사유로 거부한다(옛 키로 조용히 안 나간다)",
            detail)

        #  ── (c) 대조군 — 프로세스 재시작을 흉내내면(캐시 리셋) 새 키가 정상 인식된다 ──
        importlib.reload(CU)
        st2 = CU.status()
        chk(st2["configured"] and not st2["key_rotated_pending_restart"],
            "STEP 대조군 — 재시작 흉내(모듈 리로드) 후엔 새 키가 정상으로 인식된다"
            "(과잉차단 아님)", st2)

        #  ── (d) 멱등키가 실제로 SDK 호출까지 전달되는지 ──
        fake_msg = mock.MagicMock()
        fake_msg.sendSMS.return_value = "RECEIPT123"
        with mock.patch.object(CU, "_services", return_value=(fake_msg, mock.MagicMock())):
            ok2, detail2 = CU.send("010-1234-5678", "짧은 문자", "문자", request_id=987654)
            chk(ok2, "STEP 멱등키를 실어도 정상 발송 흐름 자체는 그대로 성공한다", detail2)
            call_kwargs = fake_msg.sendSMS.call_args
            chk(call_kwargs is not None and "987654" in str(call_kwargs),
                "★★★★★ request_id=987654 가 실제 SDK 호출 인자에 RequestNum 으로 실린다",
                str(call_kwargs))
    finally:
        os.environ.clear()
        os.environ.update(_env_backup)
        importlib.reload(CU)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드262 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
