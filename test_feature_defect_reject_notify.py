# -*- coding: utf-8 -*-
"""[기능] 하자 반려 — 확인창이 약속한 대로 실제로 통지가 나가는가.

  왜 만들었나 (2026-08-19 실측) —
    화면(static/admin.js)의 반려 확인창은 "보험사에 반려 사실이 전달됩니다.
    진행할까요?" 라고 묻는다. 그런데 서버(app.py api_defect_update)에는
    '완료'·'재시공배정'과 달리 '반려' 분기 자체가 없어 **아무 통지도 나가지
    않았다.** 운영자는 확인창을 믿고 "전달됐다" 로 알지만 보험사는 모른다.

  ⚠ Flask 세션·데코레이터를 재구성해 실제 라우트를 태우는 대신, **소스를
    직접 읽어 세 가지를 확인**한다 — 이 결함 자체가 소스 읽기로 잡혔고,
    이 라우트는 세션(admin_role)·DB 원장·notify()·평점 재계산이 얽혀 있어
    가짜 세션을 만드는 것보다 소스 검증이 더 정직하다.
    ① '반려' 분기가 있다 ② 그 안에서 notify() 를 부른다
    ③ 대상이 보험사(insurer)다 — 엉뚱한 대상에게 나가면 화면의 약속과 다르다

      python test_feature_defect_reject_notify.py
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP = read("app.py")
ADM = read("static/admin.js")

print("═" * 70)
print("  기능 회귀 — 하자 반려가 실제로 보험사에 통지되는가")
print("═" * 70)

#  화면이 무엇을 약속하는지 먼저 확인한다 — 여기가 바뀌면 서버도 같이 봐야 한다
_i_confirm = ADM.find("status==='반려'")
_confirm = ADM[_i_confirm:_i_confirm + 200] if _i_confirm >= 0 else ""
chk("보험사에 반려 사실이 전달됩니다" in _confirm,
    "화면 확인창이 '보험사에 전달' 을 약속한다(이 문구가 지금의 계약이다)", _confirm[:80])

#  서버 쪽 — api_defect_update 함수 본문을 통째로 뜬다
_i = APP.find("def api_defect_update(did):")
_j = APP.find("\ndef _defect_visible_to")
FN = APP[_i:_j] if 0 <= _i < _j else ""
chk(bool(FN), "api_defect_update 함수를 찾았다")

_i_st = FN.find('if st == "완료":')
chk(_i_st >= 0, "'완료' 분기를 찾았다(반려 분기의 형제 — 기준점)")

_i_rj = FN.find('if st == "반려":')
chk(_i_rj >= 0, "★★ '반려' 분기가 있다", "이게 없으면 확인창의 약속이 거짓말이 된다")

if _i_rj >= 0:
    #  다음 최상위 st 분기 또는 for 루프 시작까지가 이 분기의 몸통이다
    #  ⚠⚠ [라운드604] round549 가 "for f in (...)" 인라인 루프를 changed_fields
    #    리스트+"for f in changed_fields:" 로 리팩터한 뒤로 옛 마커
    #    "\n    for f in (" 는 이 함수 안 어디에도 없다(-1) — 그래서 이 검사가
    #    조용히 항상 폴백(고정 700자 슬라이스)만 타고 있었다. round604 가 '반려'
    #    분기에 설명 주석을 몇 줄 더 붙이자 notify() 의 audience_type="insurer"
    #    가 700자 밖으로 밀려나 이 검사가 실제로 깨졌다(실측) — 폴백 자체가
    #    이미 깨진 근본원인이었다. 다음 최상위 분기(severity 검증)를 실제
    #    경계로 찾도록 고친다(옛 마커는 혹시 모를 다른 형태 대비 폴백으로 유지).
    _end = FN.find('\n    if "severity" in d', _i_rj)
    if _end < 0:
        _end = FN.find("\n    for f in (", _i_rj)
    _blk = FN[_i_rj:_end] if _end > _i_rj else FN[_i_rj:_i_rj + 700]
    chk("notify(" in _blk,
        "★★ 그 안에서 notify() 를 부른다", _blk[:120])
    chk('audience_type="insurer"' in _blk.replace(" ", ""),
        "★★ 대상이 보험사다(화면의 약속과 일치)", _blk[:160])
    chk("row[\"case_no\"]" in _blk or "row['case_no']" in _blk,
        "★ 메시지에 접수번호가 들어간다(어떤 사건인지 알아야 한다)")
    #  ⚠ '완료' 분기와 같은 notify() 신호(같은 함수 안에서 같은 방식으로) 인지 —
    #    다른 자리(예: 화면 쪽 JS)에서 흉내만 낸 게 아니라 서버 원장에 남는지 확인
    _i_ok = FN.find('if st == "완료":')
    _ok_blk = FN[_i_ok:FN.find('if st == "반려":')]
    chk("notify(conn," in _ok_blk and "notify(conn," in _blk,
        "★ '완료'·'반려' 둘 다 같은 notify(conn, ...) 형태로 남긴다(원장 일관성)")

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
