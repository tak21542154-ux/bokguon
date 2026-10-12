# -*- coding: utf-8 -*-
"""스캔 191라운드 회귀 — 협력업체 입점신청의 "사업장 주소(위치정보 포함)"가
개인정보 동의고지·공식 처리방침 어디에도 신청 시점 수집 항목으로 없던 결함.

  apply_partner.html 은 실제로 주소를 입력받고(AddrPick) 정밀좌표까지 함께
  제출하며, api_create_application(app.py)이 이를 신청 접수 즉시
  partner_applications.address/lat/lng 에 저장한다(155라운드에 일부러 추가한
  배관 — "접수 단계부터" 좌표를 받겠다는 명시적 설계). 그런데 동의고지
  (form.js CONSENT_SPEC.partner)와 공식 개인정보처리방침(legal_docs.py)은
  둘 다 "사업장 주소"를 "협력업체 계정 등록(입점 승인 후)" 단계의 항목으로만
  적어 두고 있었다 — 승인 여부와 무관하게 신청 그 자체로 이미 수집되는데,
  신청자는 동의 화면에서 그 사실을 한 번도 못 본다.

      python test_scan_round191_fixes.py
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
print("  스캔 191라운드 회귀 — 협력업체 입점신청 동의고지의 '사업장 주소' 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
# partner 가 insurer 뒤에 오므로(54-64행 구조) partner: 이후 첫 '}' 까지를 본다
i_partner = FORM_SRC.index("partner: {")
partner_block = FORM_SRC[i_partner:FORM_SRC.index("}", FORM_SRC.index("period:", i_partner))]
chk("사업장 주소" in partner_block,
    "★★★★ CONSENT_SPEC.partner.items 에 '사업장 주소(위치정보 포함)'이 포함된다"
    "(실제로는 신청 접수 즉시 좌표까지 수집·저장되는데 동의고지에만 없었다)")

_row_apply = LEGAL_SRC[LEGAL_SRC.index('협력업체 입점 신청'):LEGAL_SRC.index("</tr>",
                        LEGAL_SRC.index("면허·보험 보유 여부"))]
chk("사업장 주소" in _row_apply,
    "★★★ 공식 개인정보처리방침의 '협력업체 입점 신청' 필수 항목 행에도 "
    "'사업장 주소'가 포함된다")

_row_account = LEGAL_SRC[LEGAL_SRC.index("협력업체 계정 등록"):
                          LEGAL_SRC.index("정산 계좌 정보")]
chk("사업장 주소" not in _row_account,
    "★★★★ '협력업체 계정 등록(입점 승인 후)' 행에서는 '사업장 주소'가 빠졌다"
    "(승인 후에 비로소 수집된다는 잘못된 서술이 사라졌다 — 실제로는 신청 때 "
    "이미 수집되고 승인 시 그대로 복사될 뿐이다)")

chk('id="address"' in HTML_SRC and "AddrPick" in HTML_SRC,
    "(참고) apply_partner.html 이 실제로 주소+좌표를 입력받아 제출한다 — 죽은 필드 아님")
chk("_picked_coords(d)" in APP_SRC and "INSERT INTO partner_applications" in APP_SRC,
    "(참고) api_create_application 이 신청 접수 즉시 좌표를 저장한다(155라운드 배관)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
