# -*- coding: utf-8 -*-
"""팝빌 발송 어댑터 + 실발송 스위프 검증 (네트워크 없음 — 가짜 팝빌 주입).

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

가장 위험한 실패 두 가지를 최우선으로 검사한다:
  ① 미설정 상태에서 발송 시도가 예외를 던져 업무 흐름(낙찰·정산)을 깨는 것
  ② 같은 알림이 두 번 나가거나, 데모 데이터·엉뚱한 번호로 실문자가 나가는 것
"""
import io
import os
import sys
import secrets

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import notify_popbill as NP

OK = FAIL = 0
MARK = "NPB" + secrets.token_hex(3)


def chk(cond, label, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}   {detail}")


def clear_env():
    for k in list(os.environ):
        if k.startswith("POPBILL_"):
            del os.environ[k]
    NP._cache.update(sig=None, msg=None, kakao=None)


def set_env(**extra):
    os.environ.update({
        "POPBILL_LINK_ID": "TESTLINK", "POPBILL_SECRET_KEY": "sk=test",
        "POPBILL_CORP_NUM": "656-87-02554", "POPBILL_SENDER": "02-1234-5678",
        "POPBILL_TEST": "1",
    }, **extra)


class FakeMsg:
    """팝빌 MessageService 흉내 — 호출 기록만 남긴다."""
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def _go(self, kind, args):
        self.calls.append((kind, args))
        if self.fail:
            raise self.fail
        return f"R{len(self.calls):04d}"

    def sendSMS(self, *a, **kw):
        return self._go("SMS", a)

    def sendLMS(self, *a, **kw):
        return self._go("LMS", a)


class FakeKakao(FakeMsg):
    def sendATS(self, *a, **kw):
        return self._go("ATS", a)


def inject(msg=None, kakao=None):
    """가짜 서비스를 캐시에 심는다 — _services() 가 그대로 돌려주게."""
    c = NP._cfg()
    NP._cache.update(sig=(c["link_id"], c["secret_key"], c["test"]),
                     msg=msg or FakeMsg(), kakao=kakao or FakeKakao())
    return NP._cache["msg"], NP._cache["kakao"]


def main():
    print("=" * 70)
    print("  팝빌 발송 어댑터 검증")
    print("=" * 70)

    # ── 1. 미설정 안전성 (가장 중요) ─────────────────────────────
    print("\n[1] 미설정 상태 — 예외 없이 조용히 꺼져 있는가")
    clear_env()
    st = NP.status()
    chk(st["sdk_installed"], "SDK 설치 감지(popbill 패키지)")
    chk(not st["configured"] and len(st["missing"]) == 4, "필수 4개 전부 누락으로 보고", st["missing"])
    chk(not st["ready"] and not NP.ready(), "ready=False")
    ok, detail = NP.send("01012345678", "테스트")
    chk(ok is False and "연동 안 됨" in detail, "★ 미설정 send → 예외 없이 (False, 사유)", detail)
    set_env()
    st2 = NP.status()
    chk("sk=test" not in str(st2) and "TESTLINK" not in str(st2),
        "★ status() 출력에 시크릿·키 원문 없음", st2)
    clear_env()
    os.environ.pop("BOKGUON_NOTIFY_ENABLED", None)

    # ── 2. 번호 정규화 ────────────────────────────────────────────
    print("\n[2] 휴대전화 번호 정규화")
    chk(NP.normalize_phone("010-1234-5678") == "01012345678", "하이픈 제거")
    chk(NP.normalize_phone("+82 10-1234-5678") == "01012345678", "+82 → 0")
    chk(NP.normalize_phone("02-1234-5678") is None, "★ 유선번호 거절(문자는 휴대폰만)")
    chk(NP.normalize_phone("") is None and NP.normalize_phone(None) is None, "빈 값 거절")
    chk(NP.mask_phone("01012345678") == "010****5678", "마스킹", NP.mask_phone("01012345678"))

    # ── 3. SMS/LMS 자동 분기 (EUC-KR 90바이트) ────────────────────
    print("\n[3] 바이트 기준 SMS/LMS 분기")
    set_env()
    msg, _ = inject()
    ok, d = NP.send("01012345678", "한" * 45)          # 90바이트 = SMS 상한
    chk(ok and msg.calls[-1][0] == "SMS", "90바이트 → SMS", d)
    ok, d = NP.send("01012345678", "한" * 46)          # 92바이트 → LMS
    chk(ok and msg.calls[-1][0] == "LMS", "★ 90바이트 초과 → LMS 자동 전환", d)
    a = msg.calls[-1][1]
    chk(a[0] == "6568702554" and a[1] == "0212345678", "사업자·발신번호 숫자만 전달", a[:2])
    chk("테스트베드" in d, "테스트베드 모드가 결과에 표시", d)
    long = NP._euckr_cut("한" * 2000, NP.LMS_MAX_BYTES)
    chk(len(long.encode("euc-kr")) <= 2000, "LMS 2,000바이트 절단(글자 중간 안 끊김)")

    # ── 4. 알림톡 경로 + 오류 처리 ────────────────────────────────
    print("\n[4] 알림톡 경로·오류 처리")
    set_env(POPBILL_ATS_TEMPLATE="TPL0001")
    msg, kakao = inject()
    ok, d = NP.send("01012345678", "낙찰 안내", "알림톡")
    chk(ok and kakao.calls[-1][0] == "ATS", "템플릿 있으면 알림톡(ATS)", d)
    chk(kakao.calls[-1][1][5] == "C", "★ 알림톡 실패 시 문자 자동대체(AltSendType=C)")
    del os.environ["POPBILL_ATS_TEMPLATE"]
    ok, d = NP.send("01012345678", "낙찰 안내", "알림톡")
    chk(ok and msg.calls[-1][0] == "SMS", "★ 템플릿 없으면 알림톡 채널도 문자로(그래서 '바로' 됨)", d)
    import popbill as PB
    inject(msg=FakeMsg(fail=PB.PopbillException(-12000009, "잔액 부족")))
    ok, d = NP.send("01012345678", "테스트")
    chk(ok is False and "[-12000009]" in d and "잔액" in d, "팝빌 오류 → (False, 코드+사유)", d)
    inject(msg=FakeMsg(fail=OSError("연결 끊김")))
    ok, d = NP.send("01012345678", "테스트")
    chk(ok is False and "OSError" in d, "★ 네트워크 예외도 삼켜서 (False, 사유)", d)

    # ── 5. 실발송 스위프 (app 통합) ───────────────────────────────
    print("\n[5] sweep_send_notifications — 도달/실패/차단")
    clear_env()
    import db as DB
    # [Windows] 운영 서버가 연 로그 파일을 검증까지 함께 열면 회전이 실패한다 — 자기 파일로.
    os.environ.setdefault("BOKGUON_LOG_FILE",
                          os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "logs", "test.log"))
    import app as A
    conn = DB.get_db()
    conn.execute("DELETE FROM notifications WHERE ntype LIKE ?", (MARK + "%",))
    conn.execute("DELETE FROM partners WHERE name=?", (MARK,))
    conn.commit()
    pid = conn.execute(
        "INSERT INTO partners(name, phone, created_at) VALUES(?, '010-7777-0001', ?)",
        (MARK, DB.now())).lastrowid

    #  MINE — 이 검증이 만든 알림 id 만 모은다. 스위프에 이 목록을 넘겨
    #  운영 중 새로 생긴 진짜 알림이 가짜 발송에 휩쓸리지 않게 한다.
    MINE = []

    def put(ntype, channel, partner_id=None, demo=0, attempts=0):
        rid = conn.execute(
            """INSERT INTO notifications(ntype, channel, target, message, status,
                   partner_id, is_demo, send_attempts, created_at)
               VALUES(?,?,?,?, '발송대기', ?,?,?,?)""",
            (MARK + ntype, channel, "검증", "발송 검증 메시지", partner_id, demo, attempts, DB.now())
        ).lastrowid
        MINE.append(rid)     # 뒤늦게 만든 행도 빠지지 않는다
        return rid
    n_ok = put("낙찰", "알림톡", pid)
    n_nophone = put("정산", "문자")            # 수신처 없음
    n_web = put("공지", "웹", pid)              # 웹 채널 — 발송 대상 아님
    n_demo = put("데모", "문자", pid, demo=1)   # 데모 — 절대 발송 금지
    n_last = put("보안", "문자", pid, attempts=2)  # 이번이 3번째 시도
    conn.commit()

    # ⚠ 예전에는 "기존 발송대기 건을 잠시 보류로 빼두는" 방식이었다. 그런데 서버는
    #   검증이 도는 동안에도 계속 돌면서 **새 알림을 만든다.** 보류는 그 순간의 스냅샷일
    #   뿐이라, 그 몇 초 사이에 생긴 진짜 알림이 가짜 발송에 휩쓸려 '도달'로 찍혔다
    #   (실제로 낙찰취소 알림 1건을 그렇게 잃었다 — 팝빌을 켜도 영영 안 나간다).
    #   이제 **내가 만든 행 id 만** 스위프 대상으로 넘긴다. 스냅샷이 아니라 화이트리스트다.
    sweep = lambda: A.sweep_send_notifications(conn, only_ids=list(MINE))

    # (a) 꺼져 있으면 아무것도 안 바뀐다
    res = sweep()
    st1 = {r["id"]: r["status"] for r in conn.execute(
        "SELECT id,status FROM notifications WHERE ntype LIKE ?", (MARK + "%",))}
    chk(not res["enabled"] and all(v == "발송대기" for v in st1.values()),
        "★ 미설정이면 전 건 발송대기 유지(기존 동작 불변)", res)

    # (b) 켜고 성공 — 가짜 send 주입
    sent_log = []
    real_ready, real_send, real_notify_on = NP.ready, NP.send, A.NOTIFY_ENABLED
    try:
        NP.ready = lambda: True
        A.NOTIFY_ENABLED = True
        NP.send = lambda ph, m, ch="문자", **_: (sent_log.append((ph, ch)) or (True, f"가짜접수 → {NP.mask_phone(ph)}"))
        res = sweep()
        g = lambda i: dict(conn.execute(
            "SELECT status, send_attempts, sent_at, send_detail FROM notifications WHERE id=?", (i,)).fetchone())
        chk(res["sent"] == 2 and res["failed"] == 1,
            "발송 2(낙찰·보안) · 실패 1(번호 없음)", res)
        r1 = g(n_ok)
        chk(r1["status"] == "도달" and r1["sent_at"] and "가짜접수" in r1["send_detail"],
            "★ 협력사 번호로 발송 → 도달 + 시각·상세 기록", r1)
        chk(sent_log and sent_log[0][0] == "01077770001", "협력사 전화 정규화되어 전달", sent_log[:1])
        chk(g(n_nophone)["status"] == "실패" and "없음" in g(n_nophone)["send_detail"],
            "★ 번호 없음 → 즉시 실패(재시도 낭비 없음)")
        chk(g(n_web)["status"] == "발송대기", "웹 채널은 손대지 않음")
        chk(g(n_demo)["status"] == "발송대기" and g(n_demo)["send_attempts"] == 0
            and len(sent_log) == 2,
            "★★ 데모 데이터는 절대 발송 안 됨", g(n_demo))
        # (c) 재실행 — 이미 도달한 건은 다시 안 나간다(이중발송 차단)
        before = len(sent_log)
        res2 = sweep()
        chk(res2["sent"] == 0 and len(sent_log) == before, "★ 재실행해도 이중발송 0건", res2)
        # (d) 오래된 건은 자동 발송하지 않는다(연동 첫날 몰아치기 방지)
        n_old = put("옛건", "문자", pid)
        conn.execute("UPDATE notifications SET created_at=datetime('now','+9 hours','-3 days') WHERE id=?",
                     (n_old,))
        conn.commit()
        #  ⚠ 나이 제한은 **자동 스윕에만** 건다. 여기서 sweep() 은 only_ids 로 부르므로
        #    (= 사람이 골라 보내는 경로) 오래돼도 나간다 — 그게 맞는 동작이다.
        #    자동 스윕 쪽을 봐야 하므로 only_ids 없이 한 번 돌린다.
        A.sweep_send_notifications(conn)
        chk(g(n_old)["status"] == "발송대기",
            "★ 자동 스윕은 48시간 지난 건을 보내지 않는다(연동 첫날 몰아치기 방지)", g(n_old))
        #  ★ 그런데 사람이 발송대기함에서 골라 누르면 나가야 한다 —
        #    예전에는 이 경로도 나이에 막혀 **어떤 방법으로도 못 보내는 건**이 됐다.
        A.sweep_send_notifications(conn, only_ids=[n_old])
        chk(g(n_old)["status"] == "도달",
            "★ 사람이 고른 건은 오래돼도 보낼 수 있다(영구 미발송 해소)", g(n_old))
        # (e) 실패 3회 → 실패 확정
        n_fail = put("실패건", "문자", pid)
        conn.commit()
        NP.send = lambda ph, m, ch="문자", **_: (False, "팝빌 오류 [-1] 검증용")
        for _ in range(3):
            sweep()
        rf = g(n_fail)
        chk(rf["status"] == "실패" and rf["send_attempts"] == 3, "★ 3회 실패 → 실패 확정", rf)
        res3 = sweep()
        chk(res3["failed"] == 0, "실패 확정 건은 더 안 건드림", res3)
    finally:
        NP.ready, NP.send, A.NOTIFY_ENABLED = real_ready, real_send, real_notify_on
        conn.execute("DELETE FROM notifications WHERE ntype LIKE ?", (MARK + "%",))
        conn.execute("DELETE FROM partners WHERE id=?", (pid,))
        conn.commit()
        conn.close()

    print("-" * 70)
    print(f"  통과 {OK} · 실패 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
