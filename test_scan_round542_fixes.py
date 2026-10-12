# -*- coding: utf-8 -*-
"""스캔 542라운드 회귀 — 협력사 온보딩 깔때기(ONBOARD_STAGES)·목록(ONBOARD_COLS)의
   "입찰 경험 있음" 판정이 데모입찰을 실입찰과 함께 세던 결함.

   조사 배경 — 이번 라운드 지시 각도 중 (2) "협력사 등급/평점 계산 로직"을 따라가다
   win_rate 계산(app.py:_resync_partner_stats, 15962·15991행)이 이미
   `COALESCE(b.is_demo,0)=0`으로 데모입찰을 거르는 것을 확인했다. 그런데 같은
   `bids` 표를 "이 업체가 입찰해 본 적이 있는가"로 읽는 자리가 하나 더 있다 —
   협력사 온보딩 화면(/api/partner-onboarding, app.py:19993)의 다섯 단계 중
   마지막 "입찰 경험 있음"(문구 그대로 "실제로 부를 수 있는 업체")과, 그 목록·
   엑셀이 같은 판정에 쓰는 first_bid_at(ONBOARD_COLS) 이다. 직접 조사(하위위임
   없음)해 두 자리 모두 `WHERE partner_id IS NOT NULL`만 걸고 `is_demo`를
   전혀 안 거르는 것을 확인했다 — 형제 win_rate 계산과 정확히 같은 `bids` 표를
   보면서 정작 같은 방어가 없었다.

   실사용 영향 — bids.is_demo는 사건에서 물려받아 채워진다(app.py:5301행 부근
   주석 — "협력사 '누적 제출' 등 화면 여러 곳이 bids.is_demo로 데모를 거른다").
   즉 **실제로 활성인 협력사**가 데모 사건(연습·시연용으로 만든 사건)에 입찰한
   적이 있으면 그 bids 행은 partner_id가 실제 협력사를 가리키면서 is_demo=1이다.
   이 온보딩 화면은 "운영자가 실제로 부를 수 있는 업체가 몇 곳인가"를 보여줘
   공고를 열어도 아무도 안 올 수 있다는 거짓 안심을 깨려고 만든 화면인데
   (파일 상단 19821행 부근 주석), 데모 입찰 1건만 있고 실입찰이 전혀 없는
   업체가 "입찰 경험 있음"(가장 신뢰하는 마지막 단계)으로 잘못 집계되면
   운영자는 실제로는 한 번도 안 불러본 업체를 "이미 검증된 업체"로 믿게 된다.

   고침 — 새 정책·새 헬퍼 없이, 이미 같은 질문("이 업체가 bids에 입찰 이력이
   있는가")을 던지는 형제(app.py:4806행 my_bids_total — 협력사 포털 자신의
   '누적 제출' 카운트)가 쓰는 것과 같은 조건(`COALESCE(is_demo,0)=0`, win_rate와
   달리 voided_at은 거르지 않는다 — 여긴 승률 분모가 아니라 참여 이력을 묻는
   자리라 my_bids_total과 범위를 맞춘다)을 ONBOARD_STAGES의 네 조건과
   ONBOARD_COLS의 first_bid_at 서브쿼리에 그대로 이식했다(app.py:19834-19915).
   두 자리를 함께 고친 이유 — stage_of()/_stage()(목록·엑셀)는 ONBOARD_COLS가
   준 first_bid_at 값을 그대로 읽으므로, ONBOARD_STAGES(카드 집계)만 고치면
   이 파일 자신이 이미 세운 원칙("카드 합계는 목록의 '단계' 배지와 항상
   일치한다", 19829행)이 새로 깨진다.

   app.py 자신에 정의된 모듈 전역(ONBOARD_STAGES·ONBOARD_COLS)을 고쳤다 —
   app.py가 import하는 별도 모듈이 아니다. 이미 떠 있는 프로세스가 있다면
   재시작해야 새 조건이 실제 요청에 반영된다(파이썬은 이미 임포트한 모듈을
   자동으로 다시 읽지 않는다).

   python test_scan_round542_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile

#  ⚠ 윈도 기본 콘솔은 cp949 라 em dash(—) 같은 문자를 print 하면
#    UnicodeEncodeError 로 죽는다 — 형제 테스트(round528·536·537·538·540·541 등)가
#    이미 쓰는 방어를 그대로 옮긴다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 542라운드 회귀 — 협력사 온보딩 '입찰 경험 있음' 판정이")
print("  데모입찰을 실입찰과 함께 세던 결함")
print("=" * 72)

_tmpdir = tempfile.mkdtemp(prefix="round542_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

A = DB = None
pid1 = pid2 = None


def _stage_of_conditions(conn, stages):
    """ONBOARD_STAGES 조건들을 그대로 SQL로 실행해 {label: {partner_id,...}} 로."""
    out = {}
    for label, _why, cond in stages:
        ids = {r[0] for r in conn.execute(
            f"SELECT id FROM partners WHERE status='활성' AND ({cond})")}
        out[label] = ids
    return out


# ==================================================================
print("\n[0] 소스 — 고친 지점이 실제로 app.py 에 있는가"
      "(동시편집 세션이 되돌렸다면 여기서부터 정직하게 실패해야 한다)")
# ------------------------------------------------------------------
_app_src = None
try:
    import ast as _ast
    _app_src = io.open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
    chk(_ast.parse(_app_src) is not None, "STEP app.py 전체 ast.parse 성공")
    _i = _app_src.index("ONBOARD_STAGES = [")
    _j = _app_src.index("\n\n\n", _i)
    _stages_src = _app_src[_i:_j]
    chk(_stages_src.count("COALESCE(is_demo,0)=0") == 4,
        "★★★★★ ONBOARD_STAGES 의 네 조건 모두 bids 서브쿼리에 "
        "COALESCE(is_demo,0)=0 이 있다(고치기 전엔 0개였다)")
    _k = _app_src.index("ONBOARD_COLS = ")
    _l = _app_src.index('"""', _app_src.index('"""', _k) + 3) + 3
    _cols_src = _app_src[_k:_l]
    chk("COALESCE(b.is_demo,0)=0" in _cols_src,
        "★★★★★ ONBOARD_COLS 의 first_bid_at 서브쿼리에도 있다"
        "(고치기 전엔 없었다)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드542 [0] 소스 확인", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[1] 준비 — 스크래치 DB, 활성 협력사 두 곳(둘 다 계정만 있고 "
      "안내·접속·입찰 이력은 아직 없음)")
# ------------------------------------------------------------------
try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    pid1 = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,phone,login_id) "
        "VALUES('R542업체A(데모입찰만)','시행사','활성','가드레일','서울','01099990301','r542pa')"
    ).lastrowid
    pid2 = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,phone,login_id) "
        "VALUES('R542업체B(실입찰)','시행사','활성','가드레일','서울','01099990302','r542pb')"
    ).lastrowid
    conn0.commit()
    conn0.close()
    chk(bool(pid1 and pid2), "STEP 활성 협력사 두 곳 생성", (pid1, pid2))

    conn1 = DB.get_db()
    base = _stage_of_conditions(conn1, A.ONBOARD_STAGES)
    conn1.close()
    chk(pid1 in base["안내 전"] and pid1 not in base["입찰 경험 있음"],
        "STEP 입찰 이력이 전혀 없으면 두 업체 모두 '안내 전'이다(기준선)",
        {k: v for k, v in base.items() if pid1 in v or pid2 in v})
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드542 [1] 준비", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[2] 실행(지금 코드) — 데모 입찰 1건만 있는 업체는 여전히 '안내 전'이다"
      "('입찰 경험 있음'으로 새지 않는다)")
# ------------------------------------------------------------------
try:
    conn2 = DB.get_db()
    conn2.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at,"
        "                 first_bid_at,is_demo) VALUES(9001,?,?,1000000,7,?,?,1)",
        (pid1, "R542업체A(데모입찰만)", DB.now(), DB.now()))
    conn2.commit()
    conn2.close()

    conn3 = DB.get_db()
    after_demo = _stage_of_conditions(conn3, A.ONBOARD_STAGES)
    _total3, _rows3 = A._onboard_rows(conn3, {})
    conn3.close()
    r1 = next(r for r in _rows3 if r["id"] == pid1)

    chk(pid1 in after_demo["안내 전"],
        "★★★★★ 지금 코드: 데모입찰 1건뿐인 업체는 그대로 '안내 전' 카드에 남는다",
        {k: (pid1 in v) for k, v in after_demo.items()})
    chk(pid1 not in after_demo["입찰 경험 있음"],
        "★★★★★ 지금 코드: '입찰 경험 있음' 카드로 새지 않는다(데모 오염 없음)")
    chk(not r1["first_bid_at"],
        "★★★★★ 지금 코드: 목록(ONBOARD_COLS)의 first_bid_at 도 비어 있다"
        "(카드·목록이 같은 말을 한다)", r1["first_bid_at"])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드542 [2] 지금 코드(데모입찰)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[3] 원인 재현 — app.py·run_all_tests.py 는 건드리지 않고, 지금 소스에서 "
      "이번 수정만 문자열로 되돌린 옛 조건으로 같은 데이터를 다시 판정하면")
print("    실제로 데모입찰만으로도 '입찰 경험 있음'이 된다")
# ------------------------------------------------------------------
try:
    old_stages = []
    for label, why, cond in A.ONBOARD_STAGES:
        old_cond = (cond.replace(" AND COALESCE(is_demo,0)=0)", ")")
                    if "COALESCE(is_demo,0)=0" in cond else cond)
        old_stages.append((label, why, old_cond))
    chk(all("is_demo" not in c for _, _, c in old_stages),
        "STEP 재구성된 old_stages 에는 이번 수정이 없다(진짜 '이전 코드')")

    conn4 = DB.get_db()
    old_result = _stage_of_conditions(conn4, old_stages)
    conn4.close()
    chk(pid1 in old_result["입찰 경험 있음"],
        "★★★★★ [재현] 고치기 전 조건: 데모입찰 1건뿐인 업체가 "
        "'입찰 경험 있음'(실제로 부를 수 있는 업체)으로 잘못 집계된다",
        {k: (pid1 in v) for k, v in old_result.items()})
    chk(pid1 not in old_result["안내 전"],
        "STEP [재현] 고치기 전 조건: 같은 업체가 '안내 전' 카드에서는 사라진다"
        "(카드 두 곳이 서로 다른 숫자를 말하게 되는 것과 같은 종류의 사고)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드542 [3] 원인 재현(옛 조건)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[4] 회귀 안전 — 진짜 실입찰이 있으면 지금 코드에서도 정상적으로")
print("    '입찰 경험 있음'으로 분류된다(데모만 거르지, 실입찰까지 숨기지 않는다)")
# ------------------------------------------------------------------
try:
    conn5 = DB.get_db()
    conn5.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at,"
        "                 first_bid_at,is_demo) VALUES(9002,?,?,900000,7,?,?,0)",
        (pid2, "R542업체B(실입찰)", DB.now(), DB.now()))
    conn5.commit()
    conn5.close()

    conn6 = DB.get_db()
    after_real = _stage_of_conditions(conn6, A.ONBOARD_STAGES)
    _total6, _rows6 = A._onboard_rows(conn6, {})
    conn6.close()
    r2 = next(r for r in _rows6 if r["id"] == pid2)

    chk(pid2 in after_real["입찰 경험 있음"],
        "★★★★★ 회귀 안전: 실입찰 1건이면 지금 코드도 '입찰 경험 있음'으로 "
        "정확히 분류한다(과잉교정 없음)", {k: (pid2 in v) for k, v in after_real.items()})
    chk(bool(r2["first_bid_at"]),
        "★★ 회귀 안전: 목록의 first_bid_at 도 채워진다(카드·목록 일치 유지)")
    #  1번 업체는 여전히 데모입찰뿐이므로 이 시점에도 그대로 '안내 전'이어야 한다
    chk(pid1 in after_real["안내 전"] and pid1 not in after_real["입찰 경험 있음"],
        "STEP 회귀 안전: 다른 업체가 실입찰을 넣어도 데모입찰뿐인 업체 "
        "판정은 그대로다(교차오염 없음)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드542 [4] 회귀 안전(실입찰)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[5] 배타성 — 다섯 조건은 여전히 서로 배타적이다"
      "(이 파일 자신의 불변조건, 19829행)")
# ------------------------------------------------------------------
try:
    conn7 = DB.get_db()
    total_active = conn7.execute(
        "SELECT COUNT(*) FROM partners WHERE status='활성'").fetchone()[0]
    final = _stage_of_conditions(conn7, A.ONBOARD_STAGES)
    conn7.close()
    all_ids = [i for ids in final.values() for i in ids]
    chk(len(all_ids) == len(set(all_ids)) == total_active,
        "★★★★ 활성 협력사 전원이 정확히 카드 하나에만 잡힌다(중복·누락 없음)",
        {"total_active": total_active, "union": len(set(all_ids)),
         "sum_of_cards": len(all_ids)})
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드542 [5] 배타성", f"{type(e).__name__} {e}")


# ==================================================================
# 정리
# ------------------------------------------------------------------
os.environ.pop("BOKGUON_DB_PATH", None)
os.environ.pop("BOKGUON_ENV", None)
os.environ.pop("BOKGUON_SEED_DEMO", None)
shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
