# -*- coding: utf-8 -*-
"""스캔 301라운드 회귀 — notify_popbill.py SMS/LMS 바이트 계산 결함 1건,
   notify_popbill.py·popbill_check.py 를 이 세션 사상 첫 정밀조사한 정밀조사
   Agent가 발견 — 재시도/포기 판정·자격증명 조용한 무발송·popbill_check.py의
   진단이 진짜 API호출인지·데모사건 실발송 격리는 실측 결과 전부 클린
   (기존 test_notify_popbill.py 32/32 재확인 포함). 부수 관찰(POPBILL_TEST
   단독변경 시 키교체 경고 문구가 약간 과장됨)은 실사용 경로 재현이 안 돼
   수정 보류.

   [심각] _euckr_len()·_euckr_cut() 이 이름과 달리 "EUC-KR 바이트"를 실제
   EUC-KR 코덱으로 쟀는데, 이 코덱은 1987년 KS X 1001 완성형 2,350자
   바깥의 한글(예: '뷁')을 2바이트가 아니라 8바이트로 잰다(실측: 현대
   한글 11,172자 중 8,822자·79%가 이 함정에 걸림). 팝빌 공식 문서의 실제
   과금규칙은 "한글·한자·특수문자는 2바이트"로 예외가 없다. 그 결과 흔치
   않은 음절이 든 메시지는 실제론 SMS(90바이트) 로 충분한데 LMS 로 잘못
   과금되거나, LMS 조차 실제 2,000바이트 한도보다 훨씬 일찍 잘려 뒷부분이
   조용히 사라졌다(실측: '뷁'×1000자를 2000바이트로 자르면 250자만 남음
   — 실제 한도라면 1000자 전부 들어감). 기존 회귀(test_notify_popbill.py)
   는 오직 '한'(양쪽 코덱에서 똑같이 2바이트)만 써서 이 결함을 못 잡았다.
   cp949(완성형의 상위호환, 현대 한글 11,172자 전부를 예외 없이 2바이트로
   잼 — 팝빌 규칙과 정확히 일치)로 교체.

      python test_scan_round301_fixes.py
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


NP_SRC = read("notify_popbill.py")

print("=" * 72)
print("  스캔 301라운드 회귀 — notify_popbill.py SMS/LMS 바이트 계산(euc-kr→cp949)")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────


def _section(src, start_marker, end_marker):
    i0 = src.index(start_marker)
    i1 = src.index(end_marker, i0 + len(start_marker))
    return src[i0:i1]


if "\ndef _euckr_len(" in NP_SRC and "\ndef _euckr_cut(" in NP_SRC and "\n# 서비스 객체 캐시" in NP_SRC:
    _FN_SECTION = _section(NP_SRC, "\ndef _euckr_len(", "\n# 서비스 객체 캐시")
else:
    _FN_SECTION = ""
chk(_FN_SECTION.count('encode("cp949"') == 2,
    "★★★ _euckr_len·_euckr_cut 둘 다 cp949 로 잰다(정확히 2곳)",
    _FN_SECTION.count('encode("cp949"'))
chk('encode("euc-kr"' not in _FN_SECTION,
    "★★★ 두 함수 안에 euc-kr 코덱이 더는 안 남아있다(교체 누락 방지)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 진짜 함수로 현대 한글 11,172자 전수 재확인(에이전트 조사와 독립 재현)")
# ──────────────────────────────────────────────────────────────
sys.path.insert(0, HERE)
try:
    import notify_popbill as NP

    chk(NP._euckr_len("한") == 2, "STEP 흔한 음절 '한'은 여전히 2바이트다(전제 확인, 회귀 없음)",
        NP._euckr_len("한"))
    chk(NP._euckr_len("뷁") == 2,
        "★★★ 완성형 밖 음절 '뷁'도 이제 정확히 2바이트로 잡힌다"
        "(고치기 전엔 8바이트 — 90바이트 상한 판정이 4배 어긋났다)",
        NP._euckr_len("뷁"))

    off = [cp for cp in range(0xAC00, 0xD7A4) if NP._euckr_len(chr(cp)) != 2]
    chk(len(off) == 0,
        f"★★★ 현대 한글 11,172자 전수 검사 — 전부 정확히 2바이트다"
        f"(고치기 전엔 8,822자·79%가 어긋났다)", off[:10])

    cut = NP._euckr_cut("뷁" * 1000, NP.LMS_MAX_BYTES)
    chk(len(cut) == 1000,
        "★★★ LMS 실제 한도(2,000바이트)만큼 '뷁' 1000자가 전부 안 잘리고 들어간다"
        "(고치기 전엔 250자에서 잘려 750자·75%가 조용히 사라졌다)", len(cut))
    chk(len(cut.encode("cp949")) <= NP.LMS_MAX_BYTES,
        "★★ 잘린 결과가 실제 바이트 상한을 넘지 않는다(과잉교정 아님)",
        len(cut.encode("cp949")))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드301 [2] 전수 재확인 실측", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 실제 send() 가 이제 정확한 채널로 보내는가(기존 검증 방식과 동일 패턴)")
# ──────────────────────────────────────────────────────────────
try:
    class FakeMsg:
        """test_notify_popbill.py 의 FakeMsg 와 같은 패턴 — 호출 기록만 남긴다."""
        def __init__(self):
            self.calls = []

        def _go(self, kind, args):
            self.calls.append((kind, args))
            return f"R{len(self.calls):04d}"

        def sendSMS(self, *a, **kw):
            return self._go("SMS", a)

        def sendLMS(self, *a, **kw):
            return self._go("LMS", a)

    os.environ.update({
        "POPBILL_LINK_ID": "TESTLINK", "POPBILL_SECRET_KEY": "sk=test",
        "POPBILL_CORP_NUM": "656-87-02554", "POPBILL_SENDER": "02-1234-5678",
        "POPBILL_TEST": "1",
    })
    NP._cache.update(sig=None, msg=None, kakao=None)
    c = NP._cfg()
    fake = FakeMsg()
    NP._cache.update(sig=(c["link_id"], c["secret_key"], c["test"]), msg=fake, kakao=fake)

    #  '뷁' 45자 = 실제로는 90바이트(cp949) = SMS 상한선 그대로.
    #  고치기 전엔 이 문자열이 360바이트(euc-kr, 8×45)로 계산돼 무조건 LMS 로 갔다.
    ok, d = NP.send("01012345678", "뷁" * 45)
    chk(ok and fake.calls[-1][0] == "SMS",
        "★★★ 흔치 않은 음절 45자(실제 90바이트)가 이제 정확히 SMS 로 간다"
        "(고치기 전엔 옛 계산이 360바이트로 부풀려 무조건 LMS 로 갔다)", (ok, d, fake.calls[-1][0]))

    ok2, d2 = NP.send("01012345678", "뷁" * 46)
    chk(ok2 and fake.calls[-1][0] == "LMS",
        "★★ 실제 상한을 진짜로 넘기면(46자=92바이트) 여전히 LMS 로 잘 넘어간다(회귀 없음)",
        (ok2, d2, fake.calls[-1][0]))
finally:
    os.environ.pop("POPBILL_LINK_ID", None)
    os.environ.pop("POPBILL_SECRET_KEY", None)
    os.environ.pop("POPBILL_CORP_NUM", None)
    os.environ.pop("POPBILL_SENDER", None)
    os.environ.pop("POPBILL_TEST", None)
    NP._cache.update(sig=None, msg=None, kakao=None)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
