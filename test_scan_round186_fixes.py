# -*- coding: utf-8 -*-
"""스캔 186라운드 회귀 — 입찰 채점(_bid_scores)의 지역 점수가 이 파일 자신의
norm_regions()/region_matches() 를 안 거치고 앞토큰 문자열 포함 여부로
직접 판정하던 결함.

  norm_regions() 는 정확히 이 문제(실측: 활성 협력사 149가지 표기 — '경기'
  27·'경기도' 18 등) 때문에 만들어졌는데, 정작 배차·온보딩·캠페인 세 곳만
  거치고 입찰 채점만 자기만의 판정을 새로 짰다. 실측(운영DB): 긴 표기
  ('충청남도' 등)로 적은 협력사 39곳이 짧은 표기 사건에서 부당히 감점됐고,
  대구 협력사 11곳은 '부산 해운대구' 사건과 문자열이 겹친다는 이유만으로
  완전 일치(1.0)를 받았다 — 실제로는 전혀 다른 도(道)다. 이 점수는 보험사
  낙찰화면에 그대로 노출된다(복구온은 낙찰가 정률 수수료라 순위를 매기거나
  추천하지 않고 항목별 참고값만 보여준다 — 그래서 이 항목이 틀리면 그게
  이 화면에서 유일하게 사용자에게 영향을 주는 지점이다).

      python test_scan_round186_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 186라운드 회귀 — 입찰채점 지역점수의 표기 불일치 오판정")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def _bid_scores(conn, case_row, bids):")
i1 = APP_SRC.index("\ndef ", i0 + 1)
body = APP_SRC[i0:i1]
chk("_cn, _pn = norm_regions(creg), norm_regions(preg)" in body,
    "★★★ 지역 채점이 norm_regions() 로 양쪽을 정규화한다"
    "(고치기 전엔 앞토큰이 서로의 원문에 들어있는지로 직접 판정했다)")
chk("set(_cn) & set(_pn)" in body,
    "★★★ 정규화된 지역 집합의 교집합으로 판정한다(다지역 표기도 정확히 처리)")
chk("creg.split()[0] in preg" not in body,
    "★★★★ 옛 판정식(앞토큰 원문포함 여부)이 완전히 사라졌다")

# ============================================================
print("\n[2] 실행 — 실제 협력사 표기로 재현된 세 시나리오")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round186_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()

    def region_component(case_region, partner_region):
        case_row = {"region": case_region}
        bids = [{"amount": 1000000, "days": 10, "rating": None,
                 "p_region": partner_region}]
        scored = A._bid_scores(conn, case_row, bids)
        return scored[0]["score_parts"]["지역"]

    # ① 같은 도(道)를 긴 표기로 적은 협력사 — 부당 감점되면 안 된다
    v1 = region_component("충남", "충청남도")
    chk(v1 == 10.0,
        "★★★★ '충남' 사건에 '충청남도' 협력사는 지역점수 만점(10.0)을 받는다"
        "(고치기 전엔 4.0 — 같은 도인데 표기만 다르다고 부당 감점됐다)", v1)

    # ② 해운대구(부산) 사건에 대구 협력사가 완전일치로 뜨면 안 된다
    v2 = region_component("부산 해운대구", "대구")
    chk(v2 == 4.0,
        "★★★★ '부산 해운대구' 사건에 '대구' 협력사는 지역점수 4.0(불일치)을 받는다"
        "(고치기 전엔 10.0 — '대구'가 '해운대구' 안에 있다는 이유만으로 완전일치였다)",
        v2)

    # ③ 정상 매칭은 여전히 만점(회귀 없음 확인)
    v3 = region_component("서울", "서울")
    chk(v3 == 10.0, "같은 표기의 정상 매칭은 여전히 만점", v3)

    # ④ 둘 다 지역으로 못 읽는 값(전국·충청권)은 중립값(5.0)이어야 한다
    #    (norm_regions() 자신의 원칙 — 추측하지 않는다)
    v4 = region_component("전국", "충청권")
    chk(v4 == 5.0,
        "★★★ 정규화가 안 되는 표기끼리는 중립값(5.0)으로 남는다"
        "(추측해서 맞다·틀리다로 단정하지 않는다)", v4)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드186 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
