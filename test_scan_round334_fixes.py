# -*- coding: utf-8 -*-
"""스캔 334라운드 회귀 — 협력업체 입점신청 동의고지·공식 개인정보처리방침이
   실제로 수집·저장하는 3개 필드(업체 구분·세부 취급 품목·대표 외 상시 인력 수)를
   빠뜨리고 있던 결함[중간], round334 배경조사 Agent가 발견 — 189·191·192라운드가
   이미 세 번 반복해서 겪은 것과 정확히 같은 실패모드(form.js 자신의 52행 주석
   "수집 항목은 실제 서버가 저장하는 컬럼과 일치해야 한다"를 어김)의 네 번째
   재발, 이번엔 한 라운드가 동시에 3개 필드를 놓쳤다는 점이 다르다.

   실제 수집·저장 경로를 독립검증(app.py 직접 대조):
   ① partner_type(업체 구분) — templates/apply_partner.html:21-24 필수 select
     (시행사/시공사) → app.py:5395 PARTNER_TYPES 화이트리스트 → 5397-5406
     INSERT INTO partner_applications.
   ② category(세부 취급 품목·특징) — templates/apply_partner.html:49 선택 입력
     → app.py FIELD_LIMITS["category"] 로 길이제한 → 같은 INSERT.
   ③ staff_count(대표 외 상시 인력 수) — templates/apply_partner.html:62-64
     필수 숫자 입력(288라운드가 서버측 진짜 방어선으로 확정) → app.py:5364
     파싱, 5375 에서 1명 미만이면 거부(1인사업자 정책) → 같은 INSERT.

   세 필드 다 legal_docs.py 제2조 표의 "협력업체 입점 신청" 행과
   static/form.js 의 CONSENT_SPEC.partner.items 어디에도 없었다 — 신청자가
   동의 화면에서 이 3가지를 수집한다는 사실을 한 번도 못 봤다(개인정보
   보호법 §15①1·§22·§30). partner_type·staff_count 는 폼에서 required 라
   필수 항목으로, category 는 선택 입력이라 선택 항목으로 추가.

   검증 방식은 191·192라운드와 동일하게 순수 소스텍스트 대조(이 결함
   자체가 코드 로직이 아니라 두 문서 사이의 서술 불일치이므로 real-execution
   대신 정적 검사가 적절 — 238·314라운드류와 같은 검증한계, legal_docs.py
   쪽은 app.py 의 /legal/privacy 가 그 문자열을 그대로 실시간 렌더링하므로
   재기동만 하면 즉시 반영되고 별도 빌드는 불필요, docs/ 정적사본은
   build_pages.py 재실행으로 별도 동기화).
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


FORM_SRC = read("static/form.js")
LEGAL_SRC = read("legal_docs.py")
HTML_SRC = read("templates/apply_partner.html")
APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 334라운드 회귀 — 입점신청 동의고지 3개 필드(업체구분·품목·인력수) 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — 동의고지·처리방침에 3개 필드가 실제로 추가됐다")
# ------------------------------------------------------------
i_partner = FORM_SRC.index("partner: {")
partner_block = FORM_SRC[i_partner:FORM_SRC.index("}", FORM_SRC.index("period:", i_partner))]
chk("업체 구분" in partner_block,
    "★★★★ CONSENT_SPEC.partner.items 에 '업체 구분'이 포함된다"
    "(실제로는 required select 로 신청 접수 즉시 수집되는데 동의고지엔 없었다)")
chk("세부 취급 품목" in partner_block,
    "★★★ CONSENT_SPEC.partner.items 에 '세부 취급 품목'이 포함된다")
chk("대표 외 상시 인력 수" in partner_block,
    "★★★★ CONSENT_SPEC.partner.items 에 '대표 외 상시 인력 수'가 포함된다"
    "(288라운드가 서버측 진짜 방어선으로 확정한 필수 필드인데 동의고지엔 없었다)")

_row_apply = LEGAL_SRC[LEGAL_SRC.index('협력업체 입점 신청'):
                        LEGAL_SRC.index("</tr>", LEGAL_SRC.index("면허·보험 보유 여부"))]
chk("업체 구분" in _row_apply and "대표 외 상시 인력 수" in _row_apply,
    "★★★★ 공식 개인정보처리방침 '협력업체 입점 신청' 필수 항목 행에 "
    "'업체 구분'·'대표 외 상시 인력 수'가 포함된다", _row_apply)
chk("세부 취급 품목" in _row_apply,
    "★★★ 같은 행의 선택 항목에 '세부 취급 품목'이 포함된다", _row_apply)

#  (대조군) 다른 행에는 안 번짐 — 보험사 도입문의·계정등록 행이 이 3개로
#  오염되지 않았는지 확인(엉뚱한 자리에 잘못 붙이는 사고 방지).
_row_insurer = LEGAL_SRC[LEGAL_SRC.index("보험사 도입 문의"):LEGAL_SRC.index("문의 내용")]
chk("업체 구분" not in _row_insurer and "대표 외 상시 인력 수" not in _row_insurer,
    "★★★ (대조군) '보험사 도입 문의' 행은 회귀 없이 그대로다(엉뚱한 행에 안 번짐)")

print("\n[2] 참고 — 실제로 이 3개 필드가 수집·저장되는 경로(회귀 아님, 사전조건 재확인)")
chk('id="partner_type"' in HTML_SRC and 'id="staff_count"' in HTML_SRC
    and 'id="category"' in HTML_SRC,
    "(참고) apply_partner.html 이 실제로 세 필드를 입력받는다 — 죽은 필드 아님")
chk('PARTNER_TYPES = ("시행사", "시공사")' in APP_SRC,
    "(참고) partner_type 이 화이트리스트로 검증된다(177라운드 배관)")
chk('FIELD_LIMITS["category"]' in APP_SRC,
    "(참고) category 가 길이제한을 받는 실제 저장 필드다")
chk("staff_n is None or staff_n < 1" in APP_SRC,
    "(참고) staff_count 가 서버측 진짜 방어선(288라운드)으로 검증되는 필수 필드다")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
