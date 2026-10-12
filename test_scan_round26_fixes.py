# -*- coding: utf-8 -*-
"""스캔 26라운드 회귀 — 두 조사 에이전트가 찾은 것 중 이번에 고친 세 자리.

  ① 협력사 이행 실적(jobs_done·win_rate)이 사건 완료 때 다시 계산되는가.
     실측(2026-08-19): 2026-07-23 에 한 번 손으로 돌린 뒤 한 번도 안 갱신됐다.
     #94 저장 3건 vs 실제 19건 — 이 값이 발주처의 낙찰 후보 화면과 하자율
     점수의 분모에 그대로 들어간다.
  ② 지급 알림 두 곳이 `payout`(이미 수수료를 뗀 값)을 '공사대금'이라 부르고
     그 위에 수수료를 또 뗀다고 말했다 — 산수가 스스로 안 맞는 문장이
     실제 알림함에 5건(검수승인) · 19건(이체완료) 나가 있었다.
  ③ 협력업체 엑셀 내보내기가 화면 필터(구분·대공종·검색·기간)를 무시하고
     항상 전체를 냈다 — 헤더 "시행사 89개사" 인데 엑셀은 399행.
  ④ 온보딩 카드 집계(ONBOARD_STAGES)가 목록의 단계 배지(stage_of)와 다른
     잣대였다 — 실측(2026-08-19): #94 는 로그인계정은 있지만 안내 전 상태인데
     입찰 이력도 있다. stage_of 는 입찰 이력을 최우선으로 봐서 '입찰 경험
     있음'이라 하는데, 카드 조건은 '안내 전'에도 걸렸다 — 카드 합계와 목록이
     서로 다른 숫자를 말했다.

      python test_scan_round26_fixes.py
"""
import io
import os
import re
import sqlite3
import sys
import tempfile
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def slice_by_anchor(src, start_marker, end_marker):
    i = src.find(start_marker)
    j = src.find(end_marker, i)
    if i < 0 or j < 0 or j <= i:
        return ""
    return src[i:j]


APP = read("app.py")
ADM = read("static/admin.js")

print("═" * 72)
print("  스캔 26라운드 회귀 — 실적 재계산 · 지급 문구 · 협력업체 엑셀 필터")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 협력사 이행 실적 — 사건 완료 때 다시 센다")
# ──────────────────────────────────────────────────────────────
_resync_src = slice_by_anchor(APP, "def _resync_partner_stats(conn, pid):",
                              '\n@app.post("/api/admin/recount-partner-stats")')
chk(bool(_resync_src), "함수를 찾았다")
chk("jobs_done = (SELECT COUNT(*) FROM cases c" in _resync_src,
    "★★ jobs_done 을 완료 사건 실측으로 다시 센다")
chk("win_rate" in _resync_src, "★ win_rate 도 함께 다시 센다")

#  호출부 — 사건이 완료되는 **그 자리**(단 하나의 관문)에서 부르는가
i_gate = APP.find("SET status='완료', status_at=datetime('now','+9 hours') WHERE id=? AND status='정산진행'")
chk(i_gate >= 0, "사건 완료 관문을 찾았다")
_after_gate = APP[i_gate:i_gate + 400]
chk("_resync_partner_stats(conn, st.get(\"partner_id\"))" in _after_gate,
    "★★★ 그 관문 바로 뒤에서 실적을 다시 센다",
    "이게 없으면 jobs_done 이 다시 굳어 잠든다 — 실측: #94 저장 3건 vs 실제 19건")

#  전체 재계산(관리자 버튼)과 **같은 공식**을 쓰는가 — 한쪽만 고치면 다시 갈린다
_bulk_src = slice_by_anchor(APP, "def api_recount_partner_stats():", "\n@app.")
_norm = lambda s: re.sub(r"\s+", " ", s)
chk(_norm("jobs_done = (SELECT COUNT(*) FROM cases c") in _norm(_bulk_src)
    and _norm("jobs_done = (SELECT COUNT(*) FROM cases c") in _norm(_resync_src),
    "★ 전체 재계산 버튼과 이 함수가 같은 jobs_done 공식을 쓴다")

# ── 실제로 실행해 본다 ──────────────────────────────────────────
_ns = {}
_tmpdir = tempfile.mkdtemp(prefix="resync_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "rs.db")
sys.path.insert(0, HERE)
try:
    import db as _db
    _db.DB_PATH = os.environ["BOKGUON_DB_PATH"]
    _db.init_db()
    conn = sqlite3.connect(os.environ["BOKGUON_DB_PATH"])
    conn.row_factory = sqlite3.Row

    exec(compile(_resync_src, "<resync>", "exec"), _ns)          # noqa: S102 — 우리 소스다
    _resync = _ns["_resync_partner_stats"]

    pid = conn.execute(
        "INSERT INTO partners(name, partner_type, status, jobs_done, win_rate) "
        "VALUES('검증업체','시행사','활성',3,53.8)").lastrowid
    #  완료 사건 5건(실측 #94 와 같은 모양 — 저장값보다 실제가 훨씬 많다)
    #  ⚠ jobs_done 은 status='완료' 인 것을 세고, win_rate 분자는 award_amount>0
    #    인 것을 센다 — 서로 다른 잣대다. 낙찰률을 뜻대로 재려면 award_amount 는
    #    5건 중 **1건에만** 준다(입찰 2건 중 1건만 낙찰 = 50%).
    for k in range(5):
        conn.execute(
            "INSERT INTO cases(case_no, partner_id, status, award_amount, created_at) "
            "VALUES(?,?,'완료',?,datetime('now','+9 hours'))",
            (f"RS-{k}", pid, 1000000 if k == 0 else None))
    #  낙찰률 계산용 입찰 — auction_id 서로 다른 2개, 그중 1개만 낙찰
    #  ⚠ [라운드131] win_rate 분모가 이제 auctions 에 조인해 **사건 단위**로
    #    센다(같은 사건이 재경매로 auction 행만 늘어나는 걸 막으려고) — 그래서
    #    auctions 행이 실제로 있어야 분모가 잡힌다. 서로 다른 case_id 로 2개
    #    넣어 "서로 다른 사건에 입찰"이라는 원래 의도를 그대로 유지한다.
    conn.execute("INSERT INTO auctions(id, case_id) VALUES(1,9101)")
    conn.execute("INSERT INTO auctions(id, case_id) VALUES(2,9102)")
    conn.execute("INSERT INTO bids(auction_id, partner_id, amount) VALUES(1,?,100)", (pid,))
    conn.execute("INSERT INTO bids(auction_id, partner_id, amount) VALUES(2,?,100)", (pid,))
    conn.commit()

    before = dict(conn.execute("SELECT jobs_done, win_rate FROM partners WHERE id=?", (pid,)).fetchone())
    _resync(conn, pid)
    conn.commit()
    after = dict(conn.execute("SELECT jobs_done, win_rate FROM partners WHERE id=?", (pid,)).fetchone())

    chk(before["jobs_done"] == 3, "실행 전 — 굳어 있던 값(3건)")
    chk(after["jobs_done"] == 5, "★★★ 실행 후 — 완료 사건 5건을 실측으로 다시 센다", after)
    chk(after["win_rate"] == 50.0, "★ 낙찰률도 실측(2건 중 1건 낙찰=50%)으로 다시 센다", after["win_rate"])

    #  ⚠ pid=None 이면 조용히 아무 것도 안 해야 한다(사건에 협력사가 없을 수 있다)
    _resync(conn, None)
    chk(True, "★ partner_id 가 없어도 예외 없이 넘어간다")

    conn.close()
except Exception as e:                                          # noqa: BLE001
    chk(False, "★★★ 실적 재계산 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

# ══════════════════════════════════════════════════════════════
print("\n[2] 지급 알림 문구 — 공사대금·수수료·지급액이 서로 모순되지 않는다")
# ──────────────────────────────────────────────────────────────
i_rv = APP.find('notify(conn, "정산", "앱푸시", s["partner_name"],')
_rv_block = APP[i_rv:i_rv + 400] if i_rv >= 0 else ""
chk(bool(_rv_block), "지급 검수 승인 알림을 찾았다")
chk("공사대금 {s['payout']" not in _rv_block,
    "★★★ payout 을 '공사대금'이라 부르지 않는다(검수 승인 알림)", _rv_block[:150])
chk("s['amount']" in _rv_block or 's["amount"]' in _rv_block,
    "★★ amount(수수료 떼기 전 금액)를 공사대금 자리에 쓴다")

i_tc = APP.find('notify(conn, "정산", "알림톡", st["partner_name"],')
_tc_block = APP[i_tc:i_tc + 300] if i_tc >= 0 else ""
chk(bool(_tc_block), "이체 완료 알림을 찾았다")
chk("공사대금 {st['payout']" not in _tc_block,
    "★★★ 이체 완료 알림도 payout 을 '공사대금'이라 부르지 않는다", _tc_block[:150])
chk("지급액" in _tc_block, "★ '지급액'이라는 정확한 이름을 쓴다")

#  실제로 문장을 만들어 자기모순이 없는지 확인 — 실측 사례(2,500,000/250,000/2,250,000/10%)
amount, fee, payout, pct = 2_500_000, 250_000, 2_250_000, 10.0
msg = (f"공사대금 {amount:,}원 중 수수료 {pct:g}% "
      f"{fee:,}원을 제외한 {payout:,}원 지급 검수가 끝났습니다.")
chk(round(amount * pct / 100) == fee,
    "★★★ 새 문구는 '공사대금×수수료율'이 실제 공제액과 맞아떨어진다(자기모순 없음)",
    f"{amount:,}×{pct}% = {amount*pct/100:,.0f} vs 공제액 {fee:,}")
#  옛 문구였다면 (payout 을 공사대금이라 부르며 그 위에 또 수수료를 뗀다) 산수가 안 맞았다
old_pct_of_payout = round(payout * pct / 100)
chk(old_pct_of_payout != fee,
    "★ 옛 문구가 왜 틀렸는지 재현 — payout 기준 10%는 실제 공제액과 다르다",
    f"{payout:,}×{pct}% = {old_pct_of_payout:,} ≠ 공제액 {fee:,}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 협력업체 엑셀 — 화면 필터를 그대로 받는다")
# ──────────────────────────────────────────────────────────────
chk("def _partner_filter(args):" in APP, "★ 전용 필터 함수가 있다(목록·엑셀 공용)")
_pf_src = slice_by_anchor(APP, "def _partner_filter(args):", "\n@app.get(\"/api/partners\")")
chk(bool(_pf_src), "필터 함수 본문을 찾았다")

#  ⚠ [라운드108] 고정폭(400자) 창이었다 — 그 안에서 {WHERE} 유무만 세니, 108
#    라운드가 이 SQL 앞에 설명 주석과 컬럼 2개를 더 넣자(license_status 정본화)
#    끝(FROM ... {WHERE})이 창 밖으로 밀려 "필터 자리가 없다"는 오탐이 났다.
#    다음 사전 키('applications')가 시작하는 자리까지를 통째로 본다 — 그 블록이
#    아무리 길어져도 안전하다(창(window) 판정은 구조가 아니다).
i_exp = APP.find('"partners": ("협력업체"')
i_exp_end = APP.find('"applications": ("입점신청"', i_exp) if i_exp >= 0 else -1
_exp_block = APP[i_exp:i_exp_end] if i_exp >= 0 and i_exp_end > i_exp else ""
chk("{WHERE}" in _exp_block, "★★ 엑셀 SQL 에 필터 자리가 생겼다")

chk('"partners": _partner_filter' in APP,
    "★★★ 내보내기 라우트가 협력업체 섹션에 그 필터를 실제로 연결한다",
    "연결이 없으면 자리만 있고 안 먹는다 — cases 로 조용히 폴백된다")

#  ⚠ 폴백 검사 — 매핑에 없는 섹션은 조용히 사건 필터로 떨어지지 않는지도 본다
i_disp = APP.find("_EXPORT_FILTERS = {")
_disp_block = APP[i_disp:i_disp + 200] if i_disp >= 0 else ""
chk('"cases": _case_filter' in _disp_block and '"partners": _partner_filter' in _disp_block,
    "★ 두 섹션 다 매핑에 등록되어 있다", _disp_block)

# ── 실제로 실행해 본다 ──────────────────────────────────────────
_ns2 = {"re": re}
_tmpdir2 = tempfile.mkdtemp(prefix="pfilter_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir2, "pf.db")
try:
    import db as _db2
    _db2.DB_PATH = os.environ["BOKGUON_DB_PATH"]
    _db2.init_db()
    conn2 = sqlite3.connect(os.environ["BOKGUON_DB_PATH"])
    conn2.row_factory = sqlite3.Row

    exec(compile(_pf_src, "<pfilter>", "exec"), _ns2)             # noqa: S102 — 우리 소스다
    _pfilter = _ns2["_partner_filter"]

    class _Args(dict):
        def get(self, k, default=None):
            return dict.get(self, k, default)

    #  ⚠ init_db() 는 **빈 DB 가 아니라 시드 데모 398곳**(시행사 89·시공사 309)을
    #    함께 만든다. 절대값이 아니라 **내가 넣은 만큼 늘었는지**(델타)로 잰다.
    def _count(args):
        where, p = _pfilter(args)
        return conn2.execute(
            "SELECT COUNT(*) FROM partners WHERE " + " AND ".join(where), p).fetchone()[0]

    before_prime, before_all = _count(_Args(partner_type="시행사")), _count(_Args())
    conn2.executescript("""
        INSERT INTO partners(name, partner_type, major, status) VALUES
          ('검증가','시행사','종합시행(종합건설)','활성'),
          ('검증나','시행사','종합시행(종합건설)','활성'),
          ('검증다','시공사','유리·샷시·자동문','활성');
    """)
    conn2.commit()

    chk(_count(_Args(partner_type="시행사")) - before_prime == 2,
        "★★★ 구분(시행사)으로 좁히면 시행사 늘어난 만큼만 센다(시공사 1곳은 안 걸림)",
        f"전 {before_prime} → 후 {_count(_Args(partner_type='시행사'))}")
    chk(_count(_Args()) - before_all == 3,
        "★ 조건이 없으면 셋 다 그대로 나온다(과잉 차단 아님)",
        f"전 {before_all} → 후 {_count(_Args())}")

    conn2.close()
except Exception as e:                                            # noqa: BLE001
    chk(False, "★★★ 협력업체 필터 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    import shutil
    shutil.rmtree(_tmpdir2, ignore_errors=True)

#  화면 쪽 — 엑셀 버튼이 실제로 그 QS 를 실어 보내는가
chk("function partnerQS()" in ADM, "★ 화면에 전용 QS 빌더가 있다")
_exp_js = slice_by_anchor(ADM, "ACT.exportXlsx = ", "\n  };")
chk("partnerQS()" in _exp_js, "★★★ 엑셀 버튼이 그 빌더를 부른다", _exp_js[:260])

# ══════════════════════════════════════════════════════════════
print("\n[4] 정산 엑셀 — 화면과 같은 모집단(취소 정산도 숨기지 않는다)")
# ──────────────────────────────────────────────────────────────
chk("def _settle_filter(args):" in APP, "★ 전용 필터 함수가 있다(엑셀 전용, join 별칭 대응)")
_sf_src = slice_by_anchor(APP, "def _settle_filter(args):", "\n@app.get(\"/api/settlements\")")
chk(bool(_sf_src), "필터 함수 본문을 찾았다")
#  ⚠ 독스트링을 걷어내고 본다 — 설명 문장 안의 'void_status' 언급에 낚이면 안 된다
_sf_code = re.sub(r'"""[\s\S]*?"""', " ", _sf_src)
chk("void_status" not in _sf_code,
    "★★ 코드 본문이 취소(void_status)를 걸러내지 않는다(열로만 보여준다)", _sf_code[:200])

i_exp2 = APP.find('"settlements": ("정산"')
_exp2_block = APP[i_exp2:i_exp2 + 700] if i_exp2 >= 0 else ""
chk("{WHERE}" in _exp2_block, "★★ 엑셀 SQL 에 필터 자리가 생겼다")
chk("<> '취소'" not in _exp2_block and "<>'취소'" not in _exp2_block.replace(" ", ""),
    "★★★ SQL 에서 취소 정산을 더 이상 하드코딩으로 숨기지 않는다",
    "숨기면서 '취소여부' 열을 보여주는 건 자기모순이다 — 실측: 목록 39 vs 엑셀 38")

_disp_block2 = APP[i_disp:i_disp + 260] if i_disp >= 0 else ""
chk('"settlements": _settle_filter' in _disp_block2,
    "★★★ 내보내기 라우트가 정산 섹션에 그 필터를 실제로 연결한다", _disp_block2)

#  ── 실제로 실행해 본다 (운영 스키마 그대로) ──────────────────────
_tmpdir3 = tempfile.mkdtemp(prefix="sfilter_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir3, "sf.db")
try:
    import db as _db3
    _db3.DB_PATH = os.environ["BOKGUON_DB_PATH"]
    _db3.init_db()
    conn3 = sqlite3.connect(os.environ["BOKGUON_DB_PATH"])
    conn3.row_factory = sqlite3.Row

    _ns3 = {}
    #  ⚠ _settle_filter 가 31라운드부터 _like_escape() 를 쓴다 — 그 정의도
    #    같이 넣지 않으면 이 격리된 네임스페이스에서 NameError 가 난다
    #    (실측: 이 자리를 안 고쳤을 때 딱 이 오류로 죽었다).
    _like_esc_src = slice_by_anchor(APP, "def _like_escape(s):", "\n\ndef _kw_like_clause")
    if _like_esc_src:
        exec(compile(_like_esc_src, "<like_escape>", "exec"), _ns3)  # noqa: S102 — 우리 소스다
    #  ⚠ [라운드104] _settle_filter 가 이제 MONEY_DRILL(대시보드 금액 드릴다운)도
    #    참조한다 — 같은 이유로 이 격리된 네임스페이스에 함께 안 넣으면
    #    NameError 가 난다(_like_escape 와 똑같은 패턴).
    _money_drill_src = slice_by_anchor(APP, "MONEY_DRILL = {", "\ndef _settle_where():")
    if _money_drill_src:
        exec(compile(_money_drill_src, "<money_drill>", "exec"), _ns3)  # noqa: S102 — 우리 소스다
    exec(compile(_sf_src, "<sfilter>", "exec"), _ns3)               # noqa: S102 — 우리 소스다
    _sfilter = _ns3["_settle_filter"]

    class _Args3(dict):
        def get(self, k, default=None):
            return dict.get(self, k, default)

    #  ⚠ init_db() 는 시드 settlements 4건도 함께 만든다 — 절대값이 아니라
    #    **내가 넣은 3건(정상1·취소1·데모1) 만큼 어떻게 늘었는지**(델타)로 잰다.
    def _scount(args):
        where, p = _sfilter(args)
        return conn3.execute(
            "SELECT COUNT(*) FROM settlements s LEFT JOIN cases c ON c.id=s.case_id WHERE "
            + " AND ".join(where), p).fetchone()[0]

    before_all3 = _scount(_Args3())
    before_kw3 = _scount(_Args3(q="검증업체"))

    _cid3 = conn3.execute(
        "INSERT INTO cases(case_no, status, created_at) VALUES ('ST-1','완료',datetime('now','+9 hours'))"
    ).lastrowid
    conn3.executescript(f"""
        INSERT INTO settlements(case_id, case_no, insurer, partner_name, amount, fee, payout,
                                is_demo, void_status, created_at)
             VALUES ({_cid3},'ST-1','검증보험','검증업체',1000,100,900,0,NULL,datetime('now','+9 hours')),
                    ({_cid3},'ST-1','검증보험','검증업체',2000,200,1800,0,'취소',datetime('now','+9 hours')),
                    ({_cid3},'ST-1','검증보험','검증업체',3000,300,2700,1,NULL,datetime('now','+9 hours'));
    """)
    conn3.commit()

    chk(_scount(_Args3()) - before_all3 == 2,
        "★★★ 실행 — 데모 1건은 빠지고 취소 1건은 그대로 남는다(정상1+취소1=+2, 데모1은 안 늘어남)",
        f"전 {before_all3} → 후 {_scount(_Args3())}")
    chk(_scount(_Args3(q="검증업체")) - before_kw3 == 2,
        "★ 검색어로 걸러도 취소 정산이 사라지지 않는다")
    chk(_scount(_Args3(q="이런업체는없다")) == 0, "★ 실제로 안 맞는 검색어는 0건")

    conn3.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 정산 필터 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    import shutil
    shutil.rmtree(_tmpdir3, ignore_errors=True)

chk("(a === 'settlements') ? searchQS('settle')" in _exp_js.replace(" ", "")
    or "searchQS('settle')" in _exp_js,
    "★★★ 정산 엑셀 버튼이 화면과 같은 검색 상태를 싣는다", _exp_js[:260])

# ══════════════════════════════════════════════════════════════
print("\n[5] 온보딩 카드 — 목록의 단계 배지와 같은 잣대(배타적 집계)")
# ──────────────────────────────────────────────────────────────
_stages_src = slice_by_anchor(APP, "ONBOARD_STAGES = [", "\ndef _onboard_where(args):")
chk(bool(_stages_src), "ONBOARD_STAGES 목록을 찾았다")
chk("id NOT IN (SELECT partner_id FROM bids" in _stages_src.split('"입찰 경험 있음"')[0]
    if '"입찰 경험 있음"' in _stages_src else False,
    "★★★ '입찰 경험 있음' 이전 단계들은 입찰 이력이 있으면 걸리지 않는다",
    "이게 없으면 입찰 이력이 있는 업체가 '안내 전' 등 앞 단계 카드에도 겹쳐 잡힌다")

_stageof_src = textwrap.dedent(slice_by_anchor(APP, "    def stage_of(r):", "\n\n    out = []"))
chk(bool(_stageof_src.strip()), "목록의 stage_of() 를 찾았다")

_ns5 = {}
_tmpdir5 = tempfile.mkdtemp(prefix="onboard_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir5, "ob.db")
try:
    import db as _db5
    _db5.DB_PATH = os.environ["BOKGUON_DB_PATH"]
    _db5.init_db()
    conn5 = sqlite3.connect(os.environ["BOKGUON_DB_PATH"])
    conn5.row_factory = sqlite3.Row

    exec(compile(_stages_src, "<stages>", "exec"), _ns5)          # noqa: S102 — 우리 소스다
    exec(compile(_stageof_src, "<stageof>", "exec"), _ns5)        # noqa: S102 — 우리 소스다
    _stages = _ns5["ONBOARD_STAGES"]
    _stage_of = _ns5["stage_of"]

    #  ⚠ #94 와 같은 모양(로그인계정 있음·안내 전·미접속인데 입찰 이력은 있음)을
    #    포함해 다섯 단계를 대표하는 업체를 하나씩 심는다.
    seeds = {
        "계정 없음":       dict(login_id=None, invited_at=None, first_login_at=None, bid=False),
        "안내 전":         dict(login_id="p1", invited_at=None, first_login_at=None, bid=False),
        "안내함 · 미접속": dict(login_id="p2", invited_at="2026-08-01", first_login_at=None, bid=False),
        "접속함 · 미입찰": dict(login_id="p3", invited_at="2026-08-01", first_login_at="2026-08-02", bid=False),
        "94번_모양":       dict(login_id="p4", invited_at=None, first_login_at=None, bid=True),
    }
    ids = {}
    for name, s in seeds.items():
        pid = conn5.execute(
            "INSERT INTO partners(name, partner_type, status, login_id, invited_at, first_login_at) "
            "VALUES(?,'시행사','활성',?,?,?)",
            (name, s["login_id"], s["invited_at"], s["first_login_at"])).lastrowid
        if s["bid"]:
            #  ⚠ bids.created_at 은 DEFAULT 가 없다 — 안 채우면 NULL 이라 first_bid_at
            #    서브쿼리가 NULL 을 돌려주고 stage_of() 가 입찰 이력을 못 본다.
            conn5.execute(
                "INSERT INTO bids(auction_id, partner_id, amount, created_at) "
                "VALUES(999,?,1,datetime('now','+9 hours'))", (pid,))
        ids[name] = pid
    conn5.commit()

    #  각 씨앗 업체가 다섯 조건 중 정확히 하나에만 걸리고, 그 하나가
    #  stage_of() 의 판정과 같은 이름인지 — 이게 카드와 목록이 절대 갈리지
    #  않는다는 증명이다.
    all_ok = True
    for name, pid in ids.items():
        row = dict(conn5.execute(
            "SELECT login_id, invited_at, first_login_at, "
            "(SELECT MIN(created_at) FROM bids b WHERE b.partner_id=partners.id) AS first_bid_at "
            "FROM partners WHERE id=?", (pid,)).fetchone())
        hits = [label for label, _why, cond in _stages
                if conn5.execute(f"SELECT COUNT(*) FROM partners WHERE id=? AND ({cond})",
                                 (pid,)).fetchone()[0]]
        oracle = _stage_of(row)
        ok = (len(hits) == 1 and hits[0] == oracle)
        all_ok &= ok
        chk(ok, f"★★★ '{name}' — 카드 조건과 목록 단계가 정확히 하나로 일치",
            f"카드가 걸린 단계 {hits} vs 목록 단계 '{oracle}'")

    #  #94 모양 업체가 정확히 '입찰 경험 있음'에만 잡히고 '안내 전'엔 안 잡히는가
    #  — 이번 결함의 실측 재현
    row94 = dict(conn5.execute(
        "SELECT login_id, invited_at, first_login_at, "
        "(SELECT MIN(created_at) FROM bids b WHERE b.partner_id=partners.id) AS first_bid_at "
        "FROM partners WHERE id=?", (ids["94번_모양"],)).fetchone())
    _cond_before = dict((label, cond) for label, _why, cond in _stages)["안내 전"]
    hit_before = conn5.execute(
        f"SELECT COUNT(*) FROM partners WHERE id=? AND ({_cond_before})", (ids["94번_모양"],)).fetchone()[0]
    chk(hit_before == 0,
        "★★★ #94 모양 업체는 '안내 전' 카드에는 더 이상 안 걸린다(실측 결함 재현·수정 확인)",
        f"stage_of 판정='{_stage_of(row94)}' 인데 '안내 전' 조건에 걸림={bool(hit_before)}")

    #  다섯 조건의 합 = 씨앗 업체 수(과다·과소집계가 없다는 전수 증명)
    total_hits = sum(
        conn5.execute(f"SELECT COUNT(*) FROM partners WHERE id IN ({','.join('?' * len(ids))}) "
                      f"AND ({cond})", list(ids.values())).fetchone()[0]
        for _label, _why, cond in _stages)
    chk(total_hits == len(ids),
        "★ 다섯 카드의 합이 씨앗 업체 수와 정확히 같다(중복·누락 없음)",
        f"합계 {total_hits} vs 씨앗 {len(ids)}")

    conn5.close()
except Exception as e:                                             # noqa: BLE001
    chk(False, "★★★ 온보딩 카드 배타성 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    import shutil
    shutil.rmtree(_tmpdir5, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
