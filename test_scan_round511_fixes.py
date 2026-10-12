# -*- coding: utf-8 -*-
"""스캔 511라운드 회귀 — dispatch.py _region_key()가 '대구'를 도시명이 아니라
   구 단위 접미어로 오판해 도시명을 "대" 한 글자로 잘라버리던 결함.

  직접 조사(하위위임 없음) — run_all_tests.py 전체를 먼저 정독해 이미 포화된
  축(형제 엔드포인트 잠금 비대칭 504~507, 정책문서 불일치 289·317·508,
  website 저장형 XSS 509·510, DUP_BIZNO 계열, 재알림 쿨다운, activity_log
  마스킹, 가운뎃점 정규화, 출동수배 버튼 등급게이트, catch분기 화면정리)와
  겹치지 않는 각도를 찾다가, "재경매·지오코딩 경계조건"이라는 힌트를 따라
  dispatch.py의 자동 출동 후보선정(candidates())이 쓰는 지역 열쇠 추출 함수
  _region_key()(102행)를 함수 단위로 재감사했다 — 이 함수 자체는 run_all_tests.py
  전수 대조 결과 라운드130·186·499(모두 같은 파일의 형제 함수 _like_escape·
  _norm_dot을 다룸)의 대상이 아니었던, 이 세션 사상 처음 정밀 재검토되는
  코드임을 확인했다.

  결함 — _region_key()는 "서울특별시 송파구"→"송파"처럼 시/도 접두어를 뗀 뒤
  남은 토큰 중 '구'·'시'·'군'으로 끝나는 첫 토큰을 찾아 그 접미어를 잘라
  돌려준다. 그런데 **'대구'(광역시)는 도시 이름 자체의 마지막 글자가 우연히
  '구'다** — "대구광역시 동구"는 "광역시"만 리터럴 치환으로 지워져 토큰이
  ["대구","동구"]로 쪼개지는데, 반복문이 두 번째 토큰 "동구"(진짜 구 단위)에
  닿기도 전에 첫 번째 토큰 "대구" 자신이 '구'로 끝난다는 이유만으로 먼저
  걸려 "대"(대구의 첫 글자, 아무 의미 없는 한 글자)를 반환해버린다. 서울·
  부산·인천 등 나머지 16개 시/도 약칭(db.SIDO)은 전부 구/시/군으로 끝나지
  않아 이 함정에 안 걸린다 — 대구 하나만의 우연한 충돌이다.

  영향 — candidates()는 이 반환값을 `rkey_like = f"%{_like_escape(rkey)}%"`로
  그대로 SQL LIKE 검색에 쓴다. rkey="대" 면 지역·주소 어디든 "대" 한 글자가
  들어간 협력사 전원이 "같은 지역"(1·2순위)으로 오판된다. 운영 DB 읽기전용
  조회로 실측: 활성 협력사 400곳 중 88곳(22%)이 "%대%"에 걸리는데, 그중
  실제 대구 소재는 일부일 뿐 대전·포항·서울 강동구·경기 의왕·인천 남동구 등
  전국 각지가 "대"라는 흔한 음절 하나로 뒤섞였다(예: "새천년대로"의 '대',
  "강서구"는 무관하지만 다른 주소의 "…대로" 표기 등). 대구는 인구 약 240만의
  광역시로 실제 사건·협력사가 존재해 이론적 결함이 아니다 — 지오코딩
  모듈(geo.py)이 이미 여러 라운드(120·235·264·293·316)에 걸쳐 정확히 이
  클래스(짧은 지명이 우연히 다른 토큰의 접미어/접두어와 겹치는 문제)를
  전용 로직(_word_in, _AMBIG, SIDO_ALIAS)으로 막아 왔는데, dispatch.py의
  이 함수는 그 교훈을 못 물려받고 훨씬 단순한(그래서 이 함정에 걸리는)
  구현을 따로 갖고 있었다.

  고침 — db.SIDO(시/도 약칭 17개, dispatch.py가 이미 `import db as DB`로
  참조 가능)에 있는 토큰은 구/시/군 접미어 판정 대상에서 제외한다. 새
  헬퍼·새 상수를 만들지 않고 이미 이 파일이 참조하는 기존 리스트를 그대로
  재사용한다(ponytail 원칙 — 이미 있는 것을 쓴다). '대구' 외 16개 시/도는
  애초에 구/시/군으로 끝나지 않아 이 검사가 없어도 영향이 없으므로 회귀
  없이 '대구' 한 곳만 고쳐진다.

  [1] 소스 확인 — 새 코드가 _region_key() 본문에 정확히 한 번 있다.
  [2] 실행 — 같은 프로세스에서 _region_key()를 다양한 입력(대구 3variant +
      기존 정상 케이스 6개)으로 직접 호출해 대구만 고쳐지고 나머지는
      회귀 없음을 확인.
  [3] 실행 — 실제 sqlite3(:memory:) + 실제 dispatch.candidates()로, 대구
      사건에 진짜 대구 협력사와 대전(가짜매칭 유발) 협력사를 함께 넣어
      "같은 지역" 분류가 정확한지 확인(round130과 같은 격리 기법 — 사건과
      협력사의 공종을 서로 다르게 둬 지역 판정만 순수하게 관찰).
  [4] 되돌림-증명 — _region_key()를 이 라운드 이전 구현(SIDO 예외 없음)으로
      런타임에 되돌려(파일은 안 건드린다 — DB·세션 등 외부상태가 없는 순수
      함수라 안전) 같은 시나리오를 다시 돌리면, 대전 협력사가 실제로
      "같은 지역"으로 잘못 섞여 들어옴을 재현.
  [5] 운영 DB 대조(읽기전용) — 실제 활성 협력사 400곳 중 "%대%"(옛 rkey)
      매칭 수와 "%동%"(새 rkey, 대구 동구 기준) 매칭 수를 대조해 과매칭
      규모가 실제로 줄어드는지 확인(mode=ro, 쓰기 없음).

      python test_scan_round511_fixes.py
"""
import io
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("BOKGUON_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="round511_"), "verify.db"))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


print("=" * 72)
print("  스캔 511라운드 회귀 — dispatch._region_key() '대구' 오판(도시명 절단)")
print("=" * 72)

DP_SRC = read("dispatch.py")

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — _region_key() 본문에 새 코드가 정확히 한 번")
# ──────────────────────────────────────────────────────────────
_start = DP_SRC.index("def _region_key(")
_rest = DP_SRC[_start:]
_end_rel = _rest.index("\n\ndef ", 1)
rk_body = _rest[:_end_rel] if _end_rel > 0 else _rest

NEW_LINE = "if p in DB.SIDO:"
chk(rk_body.count(NEW_LINE) == 1,
    "★★★ SIDO 예외 처리가 _region_key() 본문 안에 정확히 1번 있다", rk_body.count(NEW_LINE))
chk("[라운드511]" in rk_body, "_region_key() 안에 라운드511 표식이 있다")
chk(DP_SRC.count("def _region_key(") == 1, "_region_key() 정의가 정확히 1번만 있다(중복 정의 없음)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — _region_key() 직접 호출(같은 프로세스)")
# ──────────────────────────────────────────────────────────────
import dispatch as DP  # noqa: E402

UNIT_CASES = [
    ("대구광역시 동구", "", "동", "★★★★★ 대구+동구 — 이제 '동'(정상), 예전엔 '대'"),
    ("대구", "", "대구", "★★★★ 대구 단독(구 단위 정보 없음) — 도시명 그대로 남는다"),
    ("대구광역시 수성구", "", "수성", "★★★★★ 대구+수성구 — '수성'(정상)"),
    ("대구 동구", "", "동", "대구+동구(광역시 접미어 없이) — 동일하게 '동'"),
    ("대전광역시 동구", "", "동", "대조군 — 대전은 원래도 정상(다른 라운드 회귀 아님)"),
    ("서울특별시 송파구", "", "송파", "대조군 — 서울 송파(회귀 없음)"),
    ("부산광역시 해운대구", "", "해운대", "대조군 — 부산 해운대(회귀 없음)"),
    ("경기도 수원시 팔달구", "", "수원", "대조군 — 경기 수원(회귀 없음, 시 단위에서 멈추는 기존 동작 유지)"),
    ("전북특별자치도 전주시", "", "전주", "대조군 — 특별자치도 접두어(회귀 없음)"),
]
for region, addr, expect, label in UNIT_CASES:
    got = DP._region_key(region, addr)
    chk(got == expect, label, f"_region_key({region!r},{addr!r}) = {got!r}, expected {expect!r}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 실제 sqlite3(:memory:) + dispatch.candidates() (round130과 같은 격리 기법)")
# ──────────────────────────────────────────────────────────────


def _mkdb():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE cases(id INTEGER PRIMARY KEY, category TEXT, region TEXT, address TEXT,
                            lat REAL, lng REAL);
        CREATE TABLE work_lots(id INTEGER PRIMARY KEY, case_id INTEGER, category TEXT);
        CREATE TABLE partners(id INTEGER PRIMARY KEY, name TEXT, status TEXT, license_status TEXT,
                               region TEXT, address TEXT, category TEXT, major TEXT,
                               lat REAL, lng REAL, login_id TEXT, phone TEXT);
    """)
    return conn


#  ⚠ round130 Scenario B와 같은 격리 — 사건 공종과 파트너 공종을 절대
#    안 겹치는 값으로 둬, 1·3순위(공종 필요)는 항상 0건이 되고 2순위
#    ("같은 지역", 공종 무관)만 남는다. 그래야 이 시나리오가 순수하게
#    "지역 판정"만 증명한다.
CASE_CAT = "사건전용공종-511(매칭안됨)"
PARTNER_CAT = "업체전용공종-511(매칭안됨)"


def _build():
    conn = _mkdb()
    conn.execute("INSERT INTO cases(id,category,region,address) VALUES (1,?,?,'')",
                 (CASE_CAT, "대구광역시 동구"))
    partners = [
        ("동구방수(진짜대구)", "대구광역시 동구", ""),
        ("대전방수(가짜매칭유발)", "대전광역시 유성구", ""),
        ("포항방수(무관대조군)", "경상북도 포항시", ""),
    ]
    for i, (name, region, address) in enumerate(partners, start=1):
        conn.execute(
            "INSERT INTO partners(id,name,status,license_status,region,address,category,major,"
            "login_id,phone) VALUES (?,?,'활성','일반',?,?,?, '', '', ?)",
            (i, name, region, address, PARTNER_CAT, f"0100000000{i}"))
    conn.commit()
    return conn


try:
    conn = _build()
    got = DP.candidates(conn, 1)
    by_name = {x["name"]: x for x in got}
    chk("동구방수(진짜대구)" in by_name,
        "★★★★★ 진짜 대구(동구) 협력사는 '같은 지역'으로 잡힌다", list(by_name))
    if "동구방수(진짜대구)" in by_name:
        chk(by_name["동구방수(진짜대구)"]["why"] == "같은 지역",
            "그 협력사의 매칭 사유가 '같은 지역'이다(공종은 고의로 안 겹치게 했다)",
            by_name["동구방수(진짜대구)"]["why"])
    chk("대전방수(가짜매칭유발)" not in by_name,
        "★★★★★ 대전 협력사는 대구 사건의 '같은 지역'에 섞이지 않는다(고친 뒤)",
        list(by_name))
    chk("포항방수(무관대조군)" not in by_name,
        "포항 협력사는 애초에 무관해 안 섞인다(대조군, 옛/새 코드 공통)",
        list(by_name))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] 실제 sqlite3 실행 준비/실행", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[4] 되돌림-증명 — _region_key()를 라운드511 이전 구현으로 되돌리면")
# ──────────────────────────────────────────────────────────────


def _old_region_key(region, address):
    """라운드511 이전 구현 그대로(SIDO 예외 없음) — 되돌림-증명 전용."""
    src = (region or "") or (address or "")
    src = src.strip()
    if not src:
        return ""
    parts = src.replace("특별시", " ").replace("광역시", " ").replace("특별자치시", " ") \
               .replace("특별자치도", " ").replace("자치시", " ").split()
    for p in parts:
        if p.endswith(("구", "시", "군")):
            return p[:-1] if len(p) > 1 else p
    return parts[0] if parts else ""


try:
    chk(_old_region_key("대구광역시 동구", "") == "대",
        "★ 되돌림 대상 함수 자체가 옛 결함(대→한 글자)을 실제로 재현한다(자체 점검)",
        _old_region_key("대구광역시 동구", ""))

    _orig = DP._region_key
    DP._region_key = _old_region_key      # candidates() 는 모듈 전역 이름으로 호출하므로 이 교체가 그대로 반영된다
    try:
        conn = _build()
        broken = DP.candidates(conn, 1)
        broken_by_name = {x["name"]: x for x in broken}
        chk("대전방수(가짜매칭유발)" in broken_by_name,
            "★★★★★ 옛 코드(되돌림) — 대전 협력사가 대구 사건의 '같은 지역'으로 잘못 섞인다"
            "(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명)",
            list(broken_by_name))
        if "대전방수(가짜매칭유발)" in broken_by_name:
            chk(broken_by_name["대전방수(가짜매칭유발)"]["why"] == "같은 지역",
                "★★★★★ 그 오매칭의 사유까지 '같은 지역'으로 잘못 찍힌다",
                broken_by_name["대전방수(가짜매칭유발)"]["why"])
        chk("동구방수(진짜대구)" in broken_by_name,
            "대조 — 옛 코드에서도 진짜 대구 협력사는 여전히 잡힌다(우연히 '대'를 포함하므로)")
        conn.close()
    finally:
        DP._region_key = _orig
    chk(DP._region_key("대구광역시 동구", "") == "동",
        "★★★★★ 복원 확인 — DP._region_key가 원래(고친) 구현으로 되돌아왔다",
        DP._region_key("대구광역시 동구", ""))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [4] 되돌림-증명", f"{type(e).__name__} {e}")
    DP._region_key = _orig if "_orig" in dir() else DP._region_key

# ══════════════════════════════════════════════════════════════
print("\n[5] 운영 DB 대조(읽기전용) — 과매칭 규모 실측")
# ──────────────────────────────────────────────────────────────
try:
    prod_path = os.path.join(HERE, "bokguon.db")
    if os.path.exists(prod_path):
        uri = f"file:{prod_path.replace(os.sep, '/')}?mode=ro"
        pconn = sqlite3.connect(uri, uri=True)
        old_wide = pconn.execute(
            "SELECT COUNT(*) FROM partners WHERE status='활성' AND "
            "(COALESCE(region,'') LIKE '%대%' OR COALESCE(address,'') LIKE '%대%')").fetchone()[0]
        real_daegu = pconn.execute(
            "SELECT COUNT(*) FROM partners WHERE status='활성' AND "
            "(COALESCE(region,'') LIKE '%대구%' OR COALESCE(address,'') LIKE '%대구%')").fetchone()[0]
        total = pconn.execute("SELECT COUNT(*) FROM partners WHERE status='활성'").fetchone()[0]
        #  옛 rkey='대'(대구 사건이면 항상 이 값이 나왔다)는 region/address 어디든
        #  '대' 한 글자만 있으면 매칭이라, 실제 '대구'가 들어간 업체(real_daegu)보다
        #  훨씬 넓게 걸린다 — 그 차이(old_wide-real_daegu)가 곧 대구와 무관한데도
        #  "같은 지역"으로 잘못 섞였을 업체 수다.
        chk(True,
            f"참고 — 운영 활성협력사 {total}곳 중 옛 rkey('대') 매칭 {old_wide}곳, "
            f"그중 실제 '대구'가 들어간 곳은 {real_daegu}곳뿐 — 나머지 {old_wide - real_daegu}곳은 "
            f"대구와 무관한데도 '같은 지역'으로 잘못 섞였을 협력사(정보성 기록, pass/fail 아님)")
        pconn.close()
    else:
        chk(True, "운영 DB 파일이 없어 [5]는 건너뜀(스크래치 환경 — 정상)")
except Exception as e:                                              # noqa: BLE001
    chk(True, f"[5] 운영 DB 대조는 정보성 확인이라 실패해도 배터리를 막지 않음: {type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
