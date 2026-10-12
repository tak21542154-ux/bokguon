# -*- coding: utf-8 -*-
"""스캔 396라운드 회귀 — parse_days()(app.py:444)가 공기(공사기간) 입력값으로
   0을 허용하던 결함[경미, 데이터정합성 — 실제 공사가 0일 만에 끝난다는
   물리적으로 불가능한 값이 저장·표시됨].

  배경: 입찰 다속성 점수 조사 Agent가 발견 — parse_days()의 하한이 `0 <= n`
  이라 협력사가 공기란에 0을 적어도 통과했다. 처음엔 "이걸로 점수를 조작할
  수 있다"는 우려로 지목됐으나, _bid_scores()(10496행)를 직접 대조한 결과
  그건 아니었다 — s_days 계산(10511-12행) `d = b.get("days") or 0` 에서
  d=0 은 falsy 라 `(d and fast)` 도 falsy 가 되어 `s_days=0.5`(중립 기본값)
  로 떨어질 뿐, 점수를 인위적으로 올리는 경로는 아니다(조작 우려는 기각).
  다만 "공사가 0일 만에 끝난다"는 물리적으로 무의미한 값 자체는 실제로
  저장·표시(화면엔 '공기 -일'로 깨져 보임)되므로, 데이터 정합성 문제로는
  진짜다 — parse_money() 가 `allow_zero` 옵션으로 "0원이 유효한 경우"를
  명시적으로 구분하는 것과 달리 parse_days() 는 애초에 0이 유효할 이유가
  없다(호출부 2곳 전부 "협력사가 약속하는 공사기간" 용도, 다른 의미로
  쓰이는 자리 없음 — 전체파일 grep 재확인).

  고침: 하한을 0에서 1로 올리고 오류 메시지도 "1~{MAX_DAYS}일"로 맞춘다.

      python test_scan_round396_fixes.py
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
print("  스캔 396라운드 회귀 — parse_days() 가 공기=0을 허용하던 결함")
print("=" * 72)

print("\n[1] 소스 확인")
i0 = APP_SRC.index("def parse_days(value")
i1 = APP_SRC.index("\n\n", i0)
fn_body = APP_SRC[i0:i1]
chk("1 <= n <= MAX_DAYS" in fn_body,
    "★★★★★ parse_days() 하한이 1로 올라갔다")
chk("1~{MAX_DAYS}일" in fn_body,
    "★★★ 오류 메시지도 1~{MAX_DAYS}일로 맞춰졌다")

print("\n[2] 실행 — 실제 MAX_DAYS/parse_days()/josa() 를 그대로 실행(exec 격리)")
i_maxdays = APP_SRC.index("MAX_DAYS = ")
fn_src = APP_SRC[i_maxdays:i1].rstrip()

try:
    ns = {}
    exec(compile(fn_src, "<parse_days>", "exec"), ns)  # noqa: S102 -- 우리 소스, 실제 함수를 그대로 실행
    parse_days = ns["parse_days"]

    n, err = parse_days(0)
    chk(err is not None, "★★★★★ 공기=0은 이제 거부된다(고치기 전엔 통과했다)", (n, err))
    n, err = parse_days(1)
    chk(n == 1 and err is None, "  대조군 — 경계값 1일은 정상 통과(회귀없음)", (n, err))
    n, err = parse_days(365)
    chk(n == 365 and err is None, "  대조군 — 상한 365일은 정상 통과(회귀없음)", (n, err))
    n, err = parse_days(366)
    chk(err is not None, "  대조군 — 366일(상한초과)은 이미 있던 대로 거부(회귀없음)", (n, err))
    n, err = parse_days(-1)
    chk(err is not None, "  대조군 — 음수는 이미 있던 대로 거부(회귀없음)", (n, err))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행(parse_days 격리실행)", f"{type(e).__name__} {e}")

print("\n[3] 실행 — 실제 Flask 서버로 /api/partner/bids 에 days=0 투찰 시도")
_tmpdir = tempfile.mkdtemp(prefix="round396_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    now = DB.now()
    iid = conn.execute(
        "INSERT INTO insurers(name,status,login_id,created_at) "
        "VALUES('R396보험','활성','r396i',?)", (now,)).lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,status,license_status,region,partner_type,created_at) "
        "VALUES('R396업체','활성','확인됨','서울','시행사',?)", (now,)).lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,est_price,is_demo,created_at) "
        "VALUES('R396-A','입찰중','유리','서울',?,3000000,0,?)", (iid, now)).lastrowid
    conn.commit()
    conn.close()

    partner = A.app.test_client()
    with partner.session_transaction() as sess:
        sess["partner_id"] = pid; sess["partner_name"] = "R396업체"
        sess["_csrf"] = "r396-csrf"
    phdr = {"X-CSRF-Token": "r396-csrf"}

    r1 = partner.post("/api/partner/bids",
                       json={"case_id": cid, "amount": 2500000, "days": 0}, headers=phdr)
    j1 = r1.get_json() or {}
    chk(r1.status_code == 400 and not j1.get("ok"),
        "★★★★★ days=0 투찰은 400으로 거부된다(고치기 전엔 그대로 접수됐다)",
        (r1.status_code, j1))

    #  ⚠ 금액을 첫 시도보다 낮게 잡는다 — 되돌리기 상태에서는 days=0 투찰이
    #    그대로 접수돼 진짜 이전 입찰이 되므로, 같은 금액을 또 넣으면 이
    #    대조군이 "공기 검증"과 무관한 "입찰가는 인하만 가능" 규칙에 걸려
    #    오검출된다(실측). 항상 낮은 금액을 써 두 상태(고침 전/후) 모두에서
    #    이 규칙과 무관하게 공기 검증만 독립적으로 확인되게 한다.
    r2 = partner.post("/api/partner/bids",
                       json={"case_id": cid, "amount": 2400000, "days": 5}, headers=phdr)
    j2 = r2.get_json() or {}
    chk(r2.status_code == 200 and j2.get("ok"),
        "  대조군 — days=5(정상값) 투찰은 회귀없이 정상 접수된다", (r2.status_code, j2))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행([3] Flask 라우트 검증)", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
