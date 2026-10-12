# -*- coding: utf-8 -*-
"""스캔 329라운드 회귀 — dispatch.py candidates() 가 순위 확장 여부를
   "도달 가능한 후보 수"가 아니라 "찾은 후보 총수"로 판단하던 결함[심각],
   이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견(320~328라운드가 이어온
   app.py 재구성·감사밀도 기법이 소진되자 다른 대형 모듈로 전환 — repair_
   estimate.py 의 _validate/estimate, crypto_util.py 의 mask_account 도
   함께 점검했으나 결함 없음을 확인, 정당한 결과).

   candidates()(156행)는 1순위(같은 지역+공종일치, 최대 500건 fetch) →
   2순위(같은 지역, 253행) → 3순위(공종일치, 264행) 순으로 후보를 넓혀
   가는데, 2·3순위 진입 조건이 `len(out) < lim`(찾은 **총원수**)이었다.
   `_add()`(215행)는 계정도 휴대전화도 없는 "도달 불가"(_reachable(),
   188행 — 실측: 활성 파트너 399곳 중 계정1·휴대전화68뿐, ~17%) 업체까지
   전부 out 에 담는다 — `_reachable()` 자신의 독스트링이 이미 "빼는 게
   아니라 뒤로 미는 것"이라고 명시하는데도, "충분히 찾았는가" 판단
   자체는 이 도달가능성을 전혀 안 본다. 그래서 인구밀집 지역·흔한
   공종처럼 1순위 모집단이 lim(기본 20, dispatch_fanout 설정) 이상이면
   — 그중 도달 가능이 2~3곳뿐이어도 — 2·3순위는 아예 안 열리고, 더
   넓은 지역·전국 공종일치에 있을 도달 가능 후보는 조회조차 안 된 채
   도달불가 업체로 채워진 목록이 반환된다. 277행의 "도달가능 우선
   정렬"은 이미 모은 후보 안의 순서만 고칠 뿐 "더 찾아볼지" 판단은
   못 고친다. 253·264행의 `len(out)`을 실제 도달 가능 후보 수로
   교체 — 같은 함수 안 "총원수 vs 도달가능 우선 정렬"이라는 서로 다른
   두 관심사가 한쪽만 고쳐진, 형제가 함수가 아니라 같은 함수 안의
   서로 다른 두 단계인 사례.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_scratch = tempfile.mkdtemp(prefix="bokguon_r329_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_scratch, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"

PASS = FAIL = 0
FAILED = []


def chk(cond, msg, detail=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {msg}")
    else:
        FAIL += 1
        FAILED.append(msg)
        print(f"  [FAIL] {msg}" + (f"   {detail}" if detail else ""))


print("=" * 74)
print("  스캔 329라운드 회귀 — dispatch 후보확장 판단이 도달가능성을 무시")
print("=" * 74)

import db as DB  # noqa: E402
DB.init_db(seed_demo=False)
import dispatch as DP  # noqa: E402

print("\n[1] 준비 — 같은 지역·같은 공종 도달불가 25곳(1순위 모집단이 lim=20을 넘김) +")
print("           같은 지역·다른 공종 도달가능 1곳(2순위에만 걸림)")
conn = DB.get_db()
conn.execute("BEGIN IMMEDIATE")
now = DB.now()
REGION = "서울특별시 송파구"
TRADE = "유리·샷시·자동문"
OTHER_TRADE = "누수·배관·설비"

cur = conn.execute(
    "INSERT INTO cases(case_no,insurer,category,region,address,status,is_demo,created_at,status_at)"
    " VALUES(?,?,?,?,?,?,0,?,?)",
    ("29-R329", "테스트보험", TRADE, REGION, REGION + " 오금로", "정산대기", now, now))
case_id = cur.lastrowid

for i in range(25):
    conn.execute(
        "INSERT INTO partners(name, category, region, address, phone, login_id, status, created_at)"
        " VALUES(?,?,?,?,?,NULL,'활성',?)",
        (f"R329무응답업체{i}", TRADE, REGION, REGION, "02-000-0000", now))

conn.execute(
    "INSERT INTO partners(name, category, region, address, phone, login_id, status, created_at)"
    " VALUES(?,?,?,?,?,NULL,'활성',?)",
    ("R329응답가능업체", OTHER_TRADE, REGION, REGION, "010-1234-5678", now))
conn.commit()

print("\n[2] 실행 — 실제 candidates() 를 그대로 호출한다(lim=20 기본값)")
result = DP.candidates(conn, case_id, limit=20)
chk(len(result) > 0, "  후보가 비어있지 않다(기본 동작)", len(result))

reachable_in_result = [r for r in result if r["reachable"]]
chk(len(reachable_in_result) >= 1,
    "★★★★★ 도달 가능한 업체(같은 지역·다른 공종, 2순위에만 걸림)가 "
    "결과에 실제로 포함된다(고치기 전엔 1순위만으로 lim 이 차서 2순위가 "
    "아예 안 열려 0건이었다)", len(reachable_in_result))
if reachable_in_result:
    chk(reachable_in_result[0]["id"] == result[0]["id"],
        "  도달 가능한 업체가 도달불가 업체들보다 앞자리에 정렬된다(277행 원래 기능 회귀없음)")

print("\n[3] 실행 — 대조군: 모집단이 lim 보다 작으면(정상 케이스) 기존과 동일하게 전부 나온다")
#  ⚠ [1]의 TRADE 와 겹치면 3순위("공종 일치, 지역 무관")가 [1]에서 심어 둔
#    25곳까지 전부 끌어와 대조군이 오염된다 — 완전히 다른 공종을 쓴다.
CONTROL_TRADE = "도장·방수"
conn.execute("BEGIN IMMEDIATE")
cur2 = conn.execute(
    "INSERT INTO cases(case_no,insurer,category,region,address,status,is_demo,created_at,status_at)"
    " VALUES(?,?,?,?,?,?,0,?,?)",
    ("29-R329B", "테스트보험", CONTROL_TRADE, "부산광역시 해운대구", "부산 해운대구", "정산대기", now, now))
case_id2 = cur2.lastrowid
conn.execute(
    "INSERT INTO partners(name, category, region, address, phone, login_id, status, created_at)"
    " VALUES(?,?,?,?,?,NULL,'활성',?)",
    ("R329B업체1", CONTROL_TRADE, "부산광역시 해운대구", "부산", "010-1111-1111", now))
conn.commit()
result2 = DP.candidates(conn, case_id2, limit=20)
chk(len(result2) == 1,
    "  작은 모집단(1곳뿐)에서는 회귀 없이 그 1곳이 그대로 반환된다", len(result2))

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
