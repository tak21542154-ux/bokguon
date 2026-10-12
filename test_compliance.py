# -*- coding: utf-8 -*-
"""도급 적법성 관문 검증.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

이 관문이 뚫리면 무등록 건설업(5년 이하 징역 또는 5천만원 이하 벌금)이 열린다.
그래서 '막아야 할 것을 막는가'를 통과 검사보다 먼저·많이 검사한다.
"""
import io
import sys
import secrets

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import db as DB
import compliance as CP

OK = FAIL = 0
MARK = "CMP" + secrets.token_hex(3)


def chk(cond, label, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}   {detail}")


def cleanup(conn):
    conn.execute("DELETE FROM cases WHERE case_no LIKE ?", (MARK + "%",))
    conn.commit()


def mkcase(conn, cat, amount, region="서울 송파구", insurer_id=None, days=0):
    if insurer_id is None:
        insurer_id = conn.execute("SELECT id FROM insurers LIMIT 1").fetchone()["id"]
    cur = conn.execute(
        """INSERT INTO cases(case_no,insurer_id,insurer,category,region,address,
                             est_price,low_price,status,created_at,is_demo)
           VALUES(?,?,?,?,?,?,?,0,'접수',datetime('now','+9 hours',?),0)""",
        (f"{MARK}-{secrets.token_hex(2)}", insurer_id, "검증보험", cat, region,
         "검증", int(amount), f"{days} days"))
    conn.commit()
    return cur.lastrowid


def main():
    conn = DB.get_db()
    cleanup(conn)
    print("=" * 72)
    print("  도급 적법성 관문 검증 — 경미한 건설공사 예외")
    print("=" * 72)

    # ── 1. 금액 기준 ─────────────────────────────────────────
    print("\n[1] 경미 기준 금액 (전문 1천5백만원 · 종합 5천만원)")
    r = CP.check_direct_contract("누수·배관·설비", 2_000_000)
    chk(r["ok"] and r["code"] == CP.OK_DIRECT, "전문공사 200만원 → 도급가능", r["code"])
    chk(r["limit"] == CP.LIMIT_SPECIAL, "  전문 기준 1천5백만원 적용", r["limit"])

    r = CP.check_direct_contract("누수·배관·설비", 14_000_000)
    chk(not r["ok"] and r["code"] == CP.NO_AMOUNT,
        "★ 전문 1,400만원 → 차단(기준 1,500만이지만 안전선 1,200만 초과)", r["code"])

    r = CP.check_direct_contract("누수·배관·설비", 11_000_000)
    chk(r["ok"], "전문 1,100만원 → 안전선 이내라 통과", r["code"])

    r = CP.check_direct_contract("종합 원상복구", 30_000_000)
    chk(r["ok"] and r["limit"] == CP.LIMIT_GENERAL, "종합 3천만원 → 도급가능", r["code"])
    r = CP.check_direct_contract("종합 원상복구", 45_000_000)
    chk(not r["ok"], "★ 종합 4,500만원 → 차단(안전선 4천만 초과)", r["code"])

    # ── 2. ★ 배제 업종 — 금액과 무관 ─────────────────────────
    print("\n[2] ★ 경미 예외 배제 업종 (금액 무관 차단)")
    for cat in ("가드레일·방호울타리", "교통안전시설", "지붕·판넬·캐노피"):
        r = CP.check_direct_contract(cat, 1_000_000)   # 100만원짜리라도
        chk(not r["ok"] and r["code"] == CP.NO_TRADE,
            f"★ {cat} 100만원 → 배제업종으로 차단", r["code"])

    # ── 3. ★ 타법 소관 — 건산법 기준 적용 금지 ───────────────
    print("\n[3] ★ 다른 법률 소관 공종")
    for cat, law in (("간판·전기·가로등", CP.LAW_ELECTRIC),
                     ("셔터·차단기·게이트", CP.LAW_ELECTRIC)):
        r = CP.check_direct_contract(cat, 500_000)
        chk(not r["ok"] and r["code"] == CP.NO_LAW,
            f"★ {cat} → 타법소관으로 차단", r["code"])
        chk(r["law"] == law, f"  소관 법률 표시({law})", r["law"])

    # ── 4. 판정 불가 ─────────────────────────────────────────
    print("\n[4] 업종 미확정")
    r = CP.check_direct_contract("", 1_000_000)
    chk(not r["ok"] and r["code"] == CP.NO_UNKNOWN, "★ 공종 없으면 통과시키지 않음", r["code"])
    r = CP.check_direct_contract("듣도보도못한공종", 1_000_000)
    chk(not r["ok"], "★ 모르는 공종도 통과시키지 않음(미확인을 안전으로 취급 안 함)", r["code"])

    # ── 5. ★ 분할 회피 방지 (대법원 2018도3821) ──────────────
    print("\n[5] ★ 같은 공사 쪼개기 — 합산 판단")
    r = CP.check_direct_contract("누수·배관·설비", 5_000_000, related_amount=9_000_000)
    chk(not r["ok"] and r["code"] == CP.NO_SPLIT,
        "★ 단건 500만은 되지만 관련건 합산 1,400만 → 차단", r["code"])
    chk("2018도3821" in r["reason"], "  판례 근거가 사유에 표시됨")
    r = CP.check_direct_contract("누수·배관·설비", 3_000_000, related_amount=2_000_000)
    chk(r["ok"], "합산해도 안전선 이내면 통과", r["code"])

    # DB 연동 합산
    print("\n[5-2] DB 연동 — 같은 보험사·공종·지역·최근 30일 합산")
    iid = conn.execute("SELECT id FROM insurers LIMIT 1").fetchone()["id"]
    c1 = mkcase(conn, "누수·배관·설비", 6_000_000, insurer_id=iid)
    c2 = mkcase(conn, "누수·배관·설비", 7_000_000, insurer_id=iid)
    total, lst = CP.related_sum(conn, c1)
    chk(total >= 7_000_000, "★ 관련 건 금액이 합산됨", f"{total:,}원 · {len(lst)}건")
    g = CP.gate(conn, c1)
    chk(not g["ok"] and g["code"] == CP.NO_SPLIT,
        "★ 관문이 분할 의심으로 차단", g["code"])
    chk(g["related_cases"], "  어떤 건들이 합산됐는지 함께 반환")
    chk(g["fallback"] and "중개" in g["fallback"], "  막힌 건의 대안(중개)이 안내됨", g["fallback"])

    # 다른 지역이면 합산되지 않는다
    c3 = mkcase(conn, "누수·배관·설비", 7_000_000, region="부산 해운대구", insurer_id=iid)
    t3, _ = CP.related_sum(conn, c3)
    chk(t3 == 0, "지역이 다르면 합산하지 않음", t3)

    # ── 6. ★ 하수급인 자격 (건산법 §25②) ────────────────────
    print("\n[6] ★ 하수급인 건설업 등록 확인")
    #  ⚠ [라운드106] check_subcontractor 가 license(자유텍스트) 대신
    #    license_status(조사확정값)를 보게 바뀌었다 — 픽스처도 그 컬럼으로 맞춘다.
    r = CP.check_subcontractor({"name": "무등록시공", "license_status": "무등록"})
    chk(not r["ok"], "★ 무등록 확인된 업체에 하도급 차단", r["code"])
    chk("제25조" in r["reason"], "  근거 조문이 사유에 표시됨")
    r = CP.check_subcontractor({"name": "미확인시공", "license_status": "미확인"})
    chk(not r["ok"], "★ 아직 조사 안 된 업체도 통과시키지 않는다(안전 기본값)", r["code"])
    r = CP.check_subcontractor({"name": "정상시공", "license_status": "등록확인", "license_no": "실내건축공사업 제1234호"})
    chk(r["ok"], "등록 확인된 업체는 통과", r["code"])

    # 실제 협력사로 확인
    p = conn.execute("SELECT * FROM partners WHERE status='활성' LIMIT 1").fetchone()
    if p:
        r = CP.check_subcontractor(p)
        chk(isinstance(r["ok"], bool), f"  실제 협력사 판정 동작({r['code']})")

    # ── 7. 사업 현실 — 200만원 주력 구간이 통과하는가 ────────
    print("\n[7] 사업 현실 점검 — 200만원 이하 주력 구간")
    passable = []
    for cat in CP.WORK_RULES:
        if cat == "기타":
            continue
        rr = CP.check_direct_contract(cat, 2_000_000)
        if rr["ok"]:
            passable.append(cat)
    chk(len(passable) >= 4, f"200만원 건으로 도급 가능한 공종 {len(passable)}개", passable)
    print(f"       도급가능: {', '.join(passable)}")
    blocked = [c for c in CP.WORK_RULES
               if c != "기타" and not CP.check_direct_contract(c, 2_000_000)["ok"]]
    print(f"       중개필요: {', '.join(blocked)}")
    chk(True, f"  (중개로 돌릴 공종 {len(blocked)}개 — 사업에서 빠지는 게 아니라 구조만 다름)")

    # ── 8. ★ 복합공종 — 배제업종이 등록 순서 뒤에 있어도 새지 않는가 ──
    #   실측(2026-08-20): check_direct_contract('유리·샷시·자동문·교통안전시설', ...) 가
    #   부분일치를 WORK_RULES 등록 순서로만 찾아, 배제업종(교통안전시설)보다 먼저 등록된
    #   특별공사(유리·샷시·자동문)로 오분류돼 도급가능이 나갔다 — '애매하면 도급 불가'
    #   원칙과 정면으로 어긋났다. 등록 순서를 바꿔도(양쪽 방향) 항상 배제 쪽이 이겨야 한다.
    print("\n[8] ★ 복합공종 — 배제업종이 섞이면 순서와 무관하게 차단")
    r = CP.check_direct_contract("유리·샷시·자동문·교통안전시설", 5_000_000)
    chk(not r["ok"] and r["code"] == CP.NO_TRADE,
        "★★★ 특별공사+배제업종 복합 → 배제업종이 이긴다(실측 결함 재현·수정 확인)", r["code"])
    r = CP.check_direct_contract("교통안전시설·유리·샷시·자동문", 5_000_000)
    chk(not r["ok"] and r["code"] == CP.NO_TRADE,
        "★★ 배제업종이 문자열 앞에 와도 결과가 같다(순서 의존 아님)", r["code"])
    r = CP.check_direct_contract("누수·배관·설비·간판·전기·가로등", 500_000)
    chk(not r["ok"] and r["code"] == CP.NO_LAW,
        "★ 특별공사+타법소관 복합도 타법소관(차단)이 이긴다", r["code"])
    # 회귀 방지 — 배제업종이 없는 정상 복합공종은 여전히 통과한다
    r = CP.check_direct_contract("유리·샷시·자동문·누수·배관·설비", 5_000_000)
    chk(r["ok"] and r["code"] == CP.OK_DIRECT,
        "배제업종 없는 특별공사 조합은 그대로 도급가능(과잉 차단 아님)", r["code"])

    cleanup(conn)
    conn.close()
    print("-" * 72)
    print(f"  통과 {OK} · 실패 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
