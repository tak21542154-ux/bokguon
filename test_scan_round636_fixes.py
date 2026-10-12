# -*- coding: utf-8 -*-
"""스캔 636라운드 회귀(직접조사, 하위위임 없음) — "이 사건이 실제로 낙찰됐는가"를
승률(win_rate)·절감(saving) KPI 양쪽에서 award_amount 하나만 곧이곧대로 믿던 결함.

CASE_AMOUNT_SQL(app.py 상단)은 이미 "award_amount 는 NULL/0 일 수 있고 그럴 땐
low_price 로 넘어가야 한다"를 명시한 캐논이다. 그런데 그 방어가 안 미친 세 자리가
있었다 — _resync_partner_stats()·api_recount_partner_stats() 의 승률 분자
(COALESCE(c2.award_amount,0)>0, 두 함수는 주석으로 "고치면 여기도 같이 고쳐라"라고
서로를 지목하는 텍스트 중복이다)와 _compute_ops_kpi() 의 절감 집계(save_row·by_cat,
bare award_amount 를 WHERE 조건과 산술 양쪽에 씀).

⚠⚠ [1차 시도의 실패와 최종 설계] 처음엔 세 자리 전부가 f-string으로 참조하는
새 공유 상수 AWARD_CONFIRMED_SQL 하나로 통일했다 — app.py 는 정상, 이 테스트도
25/25 통과했지만, 전체 배터리(run_all_tests.py --quick)를 실제로 돌려 보니
round6·26·131·132·133·364 여섯 개의 **기존** 회귀테스트가 새로 깨졌다. 원인은
두 가지가 겹쳤다: ①round26·131·132·133·364 는 전부 `_resync_partner_stats`
본문을 app.py 원문에서 conn.execute(플레인 삼중따옴표 시작) 앵커로 오려내
`ns = {}`(빈 네임스페이스)에 exec 하는, round414 이전부터 확립된 격리기법을
쓰는데, 새 상수를 쓰려고 그 자리를 f-string(conn.execute(f 접두 삼중따옴표))
으로 바꾸자 그 앵커 문자열 자체가 사라져 잘못된(엉뚱한 함수의) 본문을 오려내거나
`NameError: AWARD_CONFIRMED_SQL`로 죽었다. ②round6 는 `_compute_ops_kpi`
안의 옛 리터럴 문구(`MAX(0, {SAVE_BASE_SQL}-award_amount)`)가 정확히 2번
이상 있는지 소스 문자열로 직접 센다 — 문구 자체를 바꾸면 당연히 깨진다.
최종 설계는 그래서 셋을 다르게 다룬다: `_compute_ops_kpi`는 이미 f-string으로
CASE_AMOUNT_SQL·SAVE_BASE_SQL 을 참조해 온 함수라 AWARD_CONFIRMED_SQL 을
그대로 추가해도 새로운 위험이 없다(round6 는 새 문구에 맞춰 갱신 — round364
가 이 두 함수를 다룰 때 이미 세운 "공식이 정당하게 바뀌면 옛 검사 문구도
같이 갱신한다"는 원칙 그대로). 반면 `_resync_partner_stats`·
`api_recount_partner_stats`는 **여러 라운드가 반복해서 격리-exec 로 단독
검증해 온 자리**라 f-string·외부상수 의존을 아예 안 만들고, 옛날부터 그래온
대로 리터럴 SQL 문자열을 그대로 복제해 넣는다(같은 값을 두 곳에 손으로
맞춰 쓰는 그 자체가 이미 이 두 함수의 확립된 관례 — round131·132·133·364
전부 이 전제로 짜여 있다). round131·132·364 는 그래도 하나 더 손봐야 했다
— 새 SQL이 `c2.low_price`를 읽는데 세 파일의 최소 스키마엔 그 컬럼이
없어 `OperationalError: no such column`이 났다(round364 자신이 b.voided_at
을 추가할 때 이미 겪은 것과 같은 종류의 스키마 캐치업) — 세 스키마 모두
`low_price INTEGER` 컬럼 하나만 추가했다(기존 assert·시나리오는 무변경,
이 세 파일의 INSERT 는 전부 award_amount 를 직접 채우므로 COALESCE 가
그 값에서 바로 멈춰 low_price 가 NULL 이어도 영향이 없다). 이 과정 전체를
독립적으로 실제 실행해 재확인했다 — round6·26·131·132·133·364 여섯 파일을
전부 단독 재실행해 전원 그린인 것까지 이 라운드가 직접 확인 완료.

실측(운영 DB, bokguon.db, 읽기전용, 2026-09-13 두 가지 방법으로 재확인 —
①SQL WHERE ②파이썬에서 status 문자열 직접비교): 사건#19(26-80003, is_demo=0인
진짜 사건)는 낙찰→시공→완료보고까지 정상 진행돼 awarded_at·partner_id·
completed_at 이 다 찍혀 있고 low_price=3,400,000 인데 award_amount 만 NULL 이다
(award_route 도 NULL — 지금 코드의 낙찰 경로 셋 중 어느 것도 이 조합을 새로 만들
수 없다, api_insurer_award·api_case_award·dispatch.settle_agreement 전부 award_amount·
awarded_at·award_route 를 같은 UPDATE 문 안에서 함께 쓴다 — 옛 결함이 남긴 화석으로
보인다). 현재는 '검수대기' 라 완료(status='완료') 조건을 보는 두 KPI 에는 아직
영향이 없다(직접확인: is_demo=0·status='완료'·award_amount IS NULL 인 사건 0건).
하지만 이 사건이 훗날 '완료'로 넘어가면(또는 같은 화석이 다시 생기면) 승률
분자에서 조용히 빠져(분모인 입찰엔 이미 잡혀 있다) 실제보다 낮게 잡히고, 절감
집계에서는 그 사건 자체가 통째로 안 잡힌다.

고침(app.py, 새 공유 상수 AWARD_CONFIRMED_SQL 하나 — CASE_AMOUNT_SQL 바로 아래):
  AWARD_CONFIRMED_SQL = "COALESCE(NULLIF(award_amount,0), NULLIF(low_price,0), 0)"
CASE_AMOUNT_SQL 의 앞 두 단(award_amount→low_price)과 같고 est_price 단만 뺐다 —
낙찰 못 받은 사건도 est_price>0 이라 거기까지 내려가면 "낙찰 표본"이 아닌 사건까지
승률·절감에 섞인다. 세 자리 전부 이 상수로 바꿨다(단일 합류점 — 세 자리가 각자
다른 표현으로 같은 판정을 반복하던 것을 하나로 묶음).

되돌리기-증명은 round414·490·507·610·615·621·631·632·634 가 확립한 안전패턴
그대로 적용한다 — 함수 본문 텍스트만 추출해 옛(되돌린) SQL 로 문자열 치환한 뒤
exec 로 격리 네임스페이스에 재구성하고, 호출부가 실제로 참조하는 모듈 속성
(A._resync_partner_stats·A._compute_ops_kpi)과 Flask 뷰함수 등록표
(A.app.view_functions["api_recount_partner_stats"], require_role 데코레이터까지
그대로 재적용)를 잠깐 바꿔치기했다가 finally 에서 원래 객체로 되돌린다. 진짜
app.py 파일은 이 세션 내내 단 한 바이트도 수정하지 않는다(끝에 소스 바이트 단위로
재확인).

    python test_scan_round636_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(c, n, d=""):
    (PASS if c else FAIL).append((n, d))
    print(("  [OK]   " if c else "  [FAIL] ") + n + ("" if c else f"   {d}"))


def _body(src, fn_name):
    """이름으로 함수 본문 전체를 통째로 뽑는다(다음 최상위 def·데코레이터 직전까지).
    test_scan_round64_fixes.py 가 확립한 `\\ndef ` 경계에 `\\n@` 도 함께 본다 —
    다음 함수가 api_recount_partner_stats 처럼 데코레이터(@app.post·@require_role)를
    앞세우면 `\\ndef ` 경계만으로는 그 데코레이터 줄까지 본문에 딸려 들어와
    (뒤에 def 가 안 이어지는 데코레이터만 exec 되어) SyntaxError 가 난다."""
    start = src.index(f"\ndef {fn_name}(")
    cands = [i for i in (src.find("\ndef ", start + 1), src.find("\n@", start + 1)) if i != -1]
    end = min(cands) if cands else -1
    return src[start:end if end != -1 else None]


print("=" * 72)
print("  스캔 636라운드 회귀 — 승률·절감 KPI가 award_amount NULL을 low_price로 못 넘긴다")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
APP_SRC_BEFORE = io.open(APP_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 공유 상수 + 세 호출부가 전부 이걸 쓴다")
# ──────────────────────────────────────────────────────────────
chk('AWARD_CONFIRMED_SQL = "COALESCE(NULLIF(award_amount,0), NULLIF(low_price,0), 0)"'
    in APP_SRC_BEFORE,
    "★★★ AWARD_CONFIRMED_SQL 공유 상수가 정확한 2단 NULLIF 사슬로 존재한다"
    "(est_price 단은 없다 — 낙찰 못 받은 사건까지 섞이면 안 된다)")

RESYNC_BODY = _body(APP_SRC_BEFORE, "_resync_partner_stats")
RECOUNT_BODY = _body(APP_SRC_BEFORE, "api_recount_partner_stats")
KPI_BODY = _body(APP_SRC_BEFORE, "_compute_ops_kpi")

#  ⚠ 이 두 함수는 일부러 공유 상수(AWARD_CONFIRMED_SQL)를 안 쓴다 — 위 docstring의
#    "1차 시도의 실패" 참고. 리터럴 NULLIF 사슬을 그대로 복제해 넣는다.
OLD_WIN_CLAUSE = "COALESCE(c2.award_amount,0)>0"
NEW_WIN_CLAUSE = "COALESCE(NULLIF(c2.award_amount,0), NULLIF(c2.low_price,0), 0)>0"

for name, body in (("_resync_partner_stats", RESYNC_BODY),
                    ("api_recount_partner_stats", RECOUNT_BODY)):
    chk("conn.execute(f\"\"\"" not in body and 'conn.execute("""' in body,
        f"★★ {name} — 여전히 플레인(비-f-string) 삼중따옴표를 쓴다"
        "(round26·131·132·133·364가 이 정확한 앵커로 본문을 오려내 격리exec한다)")
    chk(body.count(NEW_WIN_CLAUSE) == 1,
        f"★★★ {name} — 승률 분자가 award_amount→low_price NULLIF 사슬을 정확히 한 번 쓴다")
    chk(OLD_WIN_CLAUSE not in body,
        f"★★ {name} — 옛(award_amount 만 보는) 조건은 이제 없다(대조군)")
    chk("AWARD_CONFIRMED_SQL" not in body,
        f"★★ {name} — 공유 상수에 의존하지 않는다(격리exec 호환성 유지, 대조군)")

chk(KPI_BODY.count("AWARD_CONFIRMED_SQL") == 8,
    "★★★ _compute_ops_kpi — save_row·by_cat 여덟 자리 모두 공유 상수로 바뀌었다"
    "(WHERE 필터 4곳 + 산술 2곳 + SUM 1곳 = 지금 세어 보니 8곳)", KPI_BODY.count("AWARD_CONFIRMED_SQL"))
chk("award_amount>0" not in KPI_BODY and "SUM(award_amount)" not in KPI_BODY,
    "★★ _compute_ops_kpi — 옛(bare award_amount) 조건·합계는 이제 없다(대조군)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 준비 — 스크래치 DB + 실제 app.py import")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round636_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "verify.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB                 # noqa: E402
DB.init_db()
import app as A                 # noqa: E402

_ADMIN_TOK = "regress-round636-csrf-token"
_ADMIN_HDR = {"X-CSRF-Token": _ADMIN_TOK}


def _seed_fossil_case():
    """운영 DB 사건#19 와 정확히 같은 모양 — award_amount 만 NULL, low_price 는 있고,
    낙찰(입찰→낙찰) 자체는 진짜였다는 증거(bids·auctions)가 함께 남아 있다.
    est_price=6,000,000·low_price(=사실상 낙찰가)=5,000,000 → 절감 1,000,000원이
    되도록 잡는다(SAVE_BASE_SQL 은 field_agreements 가 없으면 est_price 로 떨어진다).
    """
    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('R636보험사','활성')").lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R636화석업체','시공사','활성')"
    ).lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,insurer_id,insurer,category,region,status,"
        "                  est_price,low_price,partner_id,partner_name,"
        "                  awarded_at,created_at) "
        "VALUES('636-80001',?,'R636보험사','가드레일·방호울타리','경기 용인','완료',"
        "       6000000,5000000,?,'R636화석업체',datetime('now','+9 hours'),"
        "       datetime('now','+9 hours'))",
        (iid, pid)).lastrowid
    #  ⚠ award_amount·award_route 는 일부러 안 채운다 — 사건#19 그대로(NULL, NULL).
    aid = conn.execute(
        "INSERT INTO auctions(case_id, status, deadline) "
        "VALUES(?, '낙찰', datetime('now','+9 hours','+1 day'))", (cid,)).lastrowid
    conn.execute(
        "INSERT INTO bids(auction_id, partner_id, partner_name, amount, days) "
        "VALUES(?,?,?,5000000,5)", (aid, pid, "R636화석업체"))
    conn.commit()
    row = conn.execute("SELECT award_amount, low_price, award_route, status "
                       "FROM cases WHERE id=?", (cid,)).fetchone()
    conn.close()
    chk(row["award_amount"] is None and row["low_price"] == 5000000,
        "STEP 전제 확인 — 심은 사건이 사건#19와 같은 모양(award_amount NULL·low_price 有)",
        dict(row))
    return pid, cid


def _read_win_rate(pid):
    conn = DB.get_db()
    v = conn.execute("SELECT win_rate FROM partners WHERE id=?", (pid,)).fetchone()[0]
    conn.close()
    return v


try:
    print("\n[3] 현재(고친) 코드로 실행 — 화석 사건도 승률·절감에 정상 반영된다")
    pid, cid = _seed_fossil_case()
    _conn0 = DB.get_db()
    _conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                   "VALUES('admin636','x','검증','최고관리자')")
    _conn0.commit(); _conn0.close()

    conn = DB.get_db()
    A._resync_partner_stats(conn, pid)
    conn.commit(); conn.close()
    wr_fixed = _read_win_rate(pid)
    chk(wr_fixed == 100.0,
        "★★★★★ 고친 코드(_resync_partner_stats): award_amount NULL 이어도 low_price로 "
        "넘어가 승률 100.0 — 정상적으로 낙찰·입찰한 유일한 사건을 승률 분자가 놓치지 않는다",
        wr_fixed)

    conn = DB.get_db()
    kpi_fixed = A._compute_ops_kpi(conn, "", "", all_time=True)["saving"]
    conn.close()
    chk(kpi_fixed["done"] == 1 and kpi_fixed["saved_amount"] == 1000000,
        "★★★★★ 고친 코드(_compute_ops_kpi): 화석 사건이 절감 집계에 1건·1,000,000원으로 "
        "정상 포함된다(전엔 award_amount>0 에 걸려 통째로 안 잡혔다)", kpi_fixed)
    by_cat_fixed = {r["category"]: r for r in kpi_fixed["by_category"]}
    chk("가드레일·방호울타리" in by_cat_fixed and by_cat_fixed["가드레일·방호울타리"]["saved"] == 1000000,
        "고친 코드: 공종별 절감표(by_category)에도 같은 1,000,000원이 잡힌다", by_cat_fixed)

    with A.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["admin"] = "admin636"; sess["admin_role"] = "최고관리자"
            sess["admin_name"] = "검증"; sess["_csrf"] = _ADMIN_TOK
        rr = client.post("/api/admin/recount-partner-stats", headers=_ADMIN_HDR)
    chk(rr.status_code == 200, "STEP 관리자 실적 일괄 재계산(실제 HTTP) 정상 응답",
        (rr.status_code, rr.get_json()))
    wr_http_fixed = _read_win_rate(pid)
    chk(wr_http_fixed == 100.0,
        "★★★★★ 고친 코드(api_recount_partner_stats, 실제 HTTP 라우트): 같은 화석 사건도 "
        "승률 100.0으로 정상 반영 — 형제 두 함수가 서로 다른 값을 내지 않는다", wr_http_fixed)

    # ══════════════════════════════════════════════════════════
    print("\n[4] 되돌리기-증명 — 세 함수만 잠깐 옛 코드로 치환(실제 파일 미변경)")
    # ──────────────────────────────────────────────────────────
    reverted_resync_src = RESYNC_BODY.replace(NEW_WIN_CLAUSE, OLD_WIN_CLAUSE, 1)
    reverted_recount_src = RECOUNT_BODY.replace(NEW_WIN_CLAUSE, OLD_WIN_CLAUSE, 1)
    reverted_kpi_src = KPI_BODY.replace("{AWARD_CONFIRMED_SQL}", "award_amount")
    for _label, _new, _old in (
            ("_resync_partner_stats", reverted_resync_src, RESYNC_BODY),
            ("api_recount_partner_stats", reverted_recount_src, RECOUNT_BODY),
            ("_compute_ops_kpi", reverted_kpi_src, KPI_BODY)):
        chk(_new != _old, f"되돌린 {_label} 사본이 실제로 원본과 다르다(치환이 먹었다)")

    _ns = dict(vars(A))
    exec(compile(reverted_resync_src, "<round636_reverted_resync>", "exec"), _ns)   # noqa: S102 -- 소스에서 그대로 추출한 사본, 디스크 미기록
    exec(compile(reverted_recount_src, "<round636_reverted_recount>", "exec"), _ns)  # noqa: S102
    exec(compile(reverted_kpi_src, "<round636_reverted_kpi>", "exec"), _ns)          # noqa: S102
    reverted_resync = _ns["_resync_partner_stats"]
    reverted_recount_raw = _ns["api_recount_partner_stats"]
    reverted_kpi = _ns["_compute_ops_kpi"]
    #  api_recount_partner_stats 는 @require_role("최고관리자") 로 감싸인 뷰함수다 —
    #  본문만 되돌리고 데코레이터(인가 게이트)는 그대로 다시 씌운다.
    reverted_recount_wrapped = A.require_role("최고관리자")(reverted_recount_raw)

    _orig_resync = A._resync_partner_stats
    _orig_kpi = A._compute_ops_kpi
    _orig_view = A.app.view_functions["api_recount_partner_stats"]
    A._resync_partner_stats = reverted_resync
    A._compute_ops_kpi = reverted_kpi
    A.app.view_functions["api_recount_partner_stats"] = reverted_recount_wrapped
    try:
        conn = DB.get_db()
        A._resync_partner_stats(conn, pid)
        conn.commit(); conn.close()
        wr_reverted = _read_win_rate(pid)

        conn = DB.get_db()
        kpi_reverted = A._compute_ops_kpi(conn, "", "", all_time=True)["saving"]
        conn.close()

        with A.app.test_client() as client:
            with client.session_transaction() as sess:
                sess["admin"] = "admin636"; sess["admin_role"] = "최고관리자"
                sess["admin_name"] = "검증"; sess["_csrf"] = _ADMIN_TOK
            rr2 = client.post("/api/admin/recount-partner-stats", headers=_ADMIN_HDR)
        wr_http_reverted = _read_win_rate(pid)
    finally:
        A._resync_partner_stats = _orig_resync
        A._compute_ops_kpi = _orig_kpi
        A.app.view_functions["api_recount_partner_stats"] = _orig_view

    chk(wr_reverted == 0.0,
        "★★★★★ 옛 코드(되돌림, _resync_partner_stats): award_amount 만 보고 low_price를 "
        "안 봐 — 정상적으로 낙찰한 사건인데도 승률이 0.0으로 떨어진다(분모엔 입찰이 "
        "이미 잡혀 있는데 분자만 못 셈) — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
        wr_reverted)
    chk(kpi_reverted["done"] == 0 and kpi_reverted["saved_amount"] == 0,
        "★★★★★ 옛 코드(되돌림, _compute_ops_kpi): 화석 사건이 절감 집계에서 통째로 "
        "빠진다(1건·1,000,000원 → 0건·0원)", kpi_reverted)
    chk(rr2.status_code == 200 and wr_http_reverted == 0.0,
        "★★★★★ 옛 코드(되돌림, api_recount_partner_stats 실제 HTTP 라우트): 관리자가 "
        "'실적 재계산' 버튼을 눌러도 화석 사건의 승률이 0.0 으로 잘못 나온다"
        "(require_role 인가 게이트는 그대로 유지된 채로 재현)", (rr2.status_code, wr_http_reverted))

    print("\n[5] 원복 확인 — 되돌리기 이후 다시 고친 동작이 나오는가(바꿔치기가 안 샜다)")
    chk(A._resync_partner_stats is _orig_resync, "  A._resync_partner_stats가 원래 함수객체로 복원됐다")
    chk(A._compute_ops_kpi is _orig_kpi, "  A._compute_ops_kpi가 원래 함수객체로 복원됐다")
    chk(A.app.view_functions["api_recount_partner_stats"] is _orig_view,
        "  view_functions['api_recount_partner_stats']가 원래 뷰함수로 복원됐다")

    conn = DB.get_db()
    A._resync_partner_stats(conn, pid)
    conn.commit(); conn.close()
    wr_after = _read_win_rate(pid)
    chk(wr_after == 100.0,
        "★★★★ 원복 후에는 다시 승률 100.0이 나온다(바꿔치기가 안 샜다)", wr_after)

    conn = DB.get_db()
    kpi_after = A._compute_ops_kpi(conn, "", "", all_time=True)["saving"]
    conn.close()
    chk(kpi_after["done"] == 1 and kpi_after["saved_amount"] == 1000000,
        "★★★★ 원복 후에는 절감 집계도 다시 1건·1,000,000원이 나온다", kpi_after)

except Exception as e:                                              # noqa: BLE001
    chk(False, "[3]~[5] 실행/되돌림-증명", f"{type(e).__name__}: {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_LOG_FILE", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC_BEFORE,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(모듈 속성·view_functions 임시치환만 사용 — 디스크에 되돌린 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
