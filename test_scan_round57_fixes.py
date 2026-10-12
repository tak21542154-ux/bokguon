# -*- coding: utf-8 -*-
"""스캔 57라운드 회귀 — 도급 적법성 관문 누락 2곳(HIGH) + 판정기준 컬럼 불일치(HIGH)
   + 개산 엔진 NaN 크래시(LOW).

  조사 에이전트가 실측(격리 DB + 대조군)으로 증명한 결함:

  ① api_co_decision(변경견적 원업체 수락)·api_co_close_full(전체재경매 낙찰) —
     계약금액을 바꾸는 자리 5곳 중 이 둘만 도급 적법성 판정 스냅샷
     (contract_gate_log)을 안 남겼다. 형제 셋(경매 낙찰 2곳·1차합의)은 이미
     남긴다. 이 두 경로로 금액이 올라도 소명 기록엔 옛(낮은) 낙찰가만 남고
     운영팀에 경고도 안 갔다.
  ② compliance.gate() 의 기본 판정 금액이 est_price(가견적)였다 — 관련 건
     합산(related_sum)은 이미 "확정가 우선"으로 고쳐져 있는데 정작 gate() 는
     안 고쳐졌다. 사진 없이 접수된 사건(est_price 상시 NULL)은 판정금액이
     항상 0원이 되어, 어떤 계약금액이든 화면(admin.js 의 caseGate())이
     무조건 '도급가능' 초록 배지를 띄웠다.
  ③ 표준단가 개산 엔진이 NaN 입력을 min/max 검사 통과시켜(IEEE 754: NaN 과의
     비교는 항상 거짓) 나중에 round() 에서 500 으로 죽었다.

      python test_scan_round57_fixes.py
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
DISPATCH_SRC = read("dispatch.py")
CP_SRC = read("compliance.py")
RE_SRC = read("repair_estimate.py")

print("═" * 72)
print("  스캔 57라운드 회귀 — 도급 적법성 관문 누락 2곳 + 판정기준 불일치 + NaN 크래시")
print("═" * 72)


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
n_award_sites = APP_SRC.count("award_amount=?") + DISPATCH_SRC.count("award_amount=?")
chk(n_award_sites == 5, "계약금액을 바꾸는 UPDATE 가 정확히 5곳이다(전제 확인)", n_award_sites)
#  ⚠ "_gate_alert(" 는 def 줄 자신도 매치한다(def _gate_alert(conn, ...): 도
#    같은 부분문자열을 담고 있다) — def 줄 하나를 빼고 실제 호출만 센다.
n_gate_alerts = APP_SRC.count("_gate_alert(") - APP_SRC.count("def _gate_alert(")
chk(n_gate_alerts == 5,
    "★★★ 도급 적법성 스냅샷 호출이 5곳 전부와 맞다(고치기 전엔 3곳뿐이었다)",
    n_gate_alerts)

decision_body = _body(APP_SRC, "api_co_decision")
chk('CP.record_gate(conn, co["case_id"], "변경견적", portal_actor(),' in decision_body,
    "★★★ ① api_co_decision — 도급 적법성 스냅샷을 남긴다")
close_full_body = _body(APP_SRC, "api_co_close_full")
chk('CP.record_gate(conn, co["case_id"], "전체재경매", actor(),' in close_full_body,
    "★★★ ① api_co_close_full — 도급 적법성 스냅샷을 남긴다")

gate_body = _body(CP_SRC, "gate")
chk('c["award_amount"] or c["low_price"] or c["est_price"] or 0' in gate_body,
    "★★★ ② gate() 가 related_sum() 과 같은 '확정가 우선' 식을 쓴다")

validate_body = _body(RE_SRC, "_validate")
chk("math.isfinite(val)" in validate_body,
    "★ ③ 개산 입력 검증이 NaN/inf 를 거부한다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 서버(test_client)로 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round57_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

_seq = [0]


def _no(prefix):
    _seq[0] += 1
    return f"{prefix}{_seq[0]:04d}"


try:
    import db as DB
    DB.init_db()
    import app as A
    import compliance as CP

    client = A.app.test_client()
    _tok = "regress-round57-csrf-token"
    _hdr = {"X-CSRF-Token": _tok}
    CATEGORY = "누수·배관·설비"   # kind=special, 기준 15,000,000 / 안전선 12,000,000

    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('검증보험사57','활성')").lastrowid
    p_incumbent = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('원업체57','시공사','활성')"
    ).lastrowid
    p_rival = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('경쟁사57','시행사','활성')"
    ).lastrowid
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                "VALUES('admin57','x','검증','중간관리자')")
    conn.commit(); conn.close()

    def _admin_sess(sess):
        sess["admin"] = "admin57"; sess["admin_role"] = "중간관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = _tok

    def _rival_sess(sess):
        sess["partner_id"] = p_rival; sess["_csrf"] = _tok

    def _n_gate_rows(cid):
        c = DB.get_db()
        n = c.execute("SELECT COUNT(*) FROM contract_gate_log WHERE case_id=?",
                      (cid,)).fetchone()[0]
        c.close()
        return n

    def _n_gate_alerts():
        c = DB.get_db()
        n = c.execute("SELECT COUNT(*) FROM notifications WHERE ntype='도급판정'").fetchone()[0]
        c.close()
        return n

    # ── ①-A api_co_decision — 초과 금액을 원업체가 수락 ──
    conn = DB.get_db()
    cid1 = conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,partner_id,partner_name,"
        "                  award_amount,category,region) "
        "VALUES(?,'시공중',?,?,?,?,3000000,?,'서울')",
        (_no("57C-"), "검증보험사57", iid, p_incumbent, "원업체57", CATEGORY)).lastrowid
    #  ⚠ 라운드55 관문(_insurer_ack_ok) 전제조건 — 발주처가 이 금액을 '확인'해야
    #    수락 자체가 통과한다. 이 라운드가 보려는 건 그 뒤 단계(도급 적법성)이므로
    #    발주처 확인은 이미 끝난 상태로 심는다.
    coid1 = conn.execute(
        "INSERT INTO change_orders(case_id,round,status,incumbent_partner_id,incumbent_amount,"
        "                          combined_amount,add_low,add_partner_id,"
        "                          insurer_ack,insurer_ack_amount) "
        "VALUES(?,1,'원업체제안',?,3000000,20000000,17000000,?,'확인',20000000)",
        (cid1, p_incumbent, p_rival)).lastrowid
    conn.commit(); conn.close()
    before1 = _n_gate_rows(cid1)
    alerts_before1 = _n_gate_alerts()

    with client.session_transaction() as sess:
        sess["partner_id"] = p_incumbent; sess["_csrf"] = _tok
    r1 = client.post(f"/api/change-orders/{coid1}/decision", json={"accept": True}, headers=_hdr)
    chk(r1.status_code == 200, "STEP① 원업체가 초과 합산가(20,000,000원)를 수락", (r1.status_code, r1.get_json()))

    after1 = _n_gate_rows(cid1)
    chk(after1 == before1 + 1,
        "★★★ ① 수락 즉시 도급 적법성 스냅샷이 1건 새로 남는다(고치기 전엔 0)", (before1, after1))
    conn = DB.get_db()
    last_gate1 = dict(conn.execute(
        "SELECT code, ok, amount FROM contract_gate_log WHERE case_id=? "
        "ORDER BY id DESC LIMIT 1", (cid1,)).fetchone())
    conn.close()
    chk(last_gate1["amount"] == 20000000 and last_gate1["ok"] == 0,
        "★★★ ① 스냅샷 금액이 옛 낙찰가가 아니라 실제 확정된 합산가(20,000,000)다"
        "(안전선 12,000,000 초과 → ok=0 이어야 함)", last_gate1)
    chk(_n_gate_alerts() == alerts_before1 + 1,
        "★★ ① 기준 초과라 운영팀 '도급판정' 경고 알림도 실제로 갔다", None)

    # 대조군 — 기준 이내 금액은 스냅샷은 남되(ok=1) 경고 알림은 안 간다
    conn = DB.get_db()
    cid1b = conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,partner_id,partner_name,"
        "                  award_amount,category,region) "
        "VALUES(?,'시공중',?,?,?,?,2000000,?,'서울')",
        (_no("57C-"), "검증보험사57", iid, p_incumbent, "원업체57", CATEGORY)).lastrowid
    coid1b = conn.execute(
        "INSERT INTO change_orders(case_id,round,status,incumbent_partner_id,incumbent_amount,"
        "                          combined_amount,add_low,add_partner_id,"
        "                          insurer_ack,insurer_ack_amount) "
        "VALUES(?,1,'원업체제안',?,2000000,3000000,1000000,?,'확인',3000000)",
        (cid1b, p_incumbent, p_rival)).lastrowid
    conn.commit(); conn.close()
    alerts_before1b = _n_gate_alerts()
    with client.session_transaction() as sess:
        sess["partner_id"] = p_incumbent; sess["_csrf"] = _tok
    r1b = client.post(f"/api/change-orders/{coid1b}/decision", json={"accept": True}, headers=_hdr)
    chk(r1b.status_code == 200, "대조군 — 기준 이내 합산가는 그대로 수락된다", r1b.status_code)
    conn = DB.get_db()
    last_gate1b = dict(conn.execute(
        "SELECT ok FROM contract_gate_log WHERE case_id=? ORDER BY id DESC LIMIT 1",
        (cid1b,)).fetchone())
    conn.close()
    chk(last_gate1b["ok"] == 1, "★ 대조군 — 기준 이내는 ok=1 로 스냅샷된다", last_gate1b)
    chk(_n_gate_alerts() == alerts_before1b,
        "★ 대조군 — 기준 이내는 경고 알림이 추가로 안 간다(과잉알림 아님)", None)

    # ── ①-B api_co_close_full — 초과 금액으로 전체재경매 낙찰 ──
    conn = DB.get_db()
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,partner_id,partner_name,"
        "                  award_amount,category,region) "
        "VALUES(?,'시공중',?,?,?,?,3000000,?,'서울')",
        (_no("57C-"), "검증보험사57", iid, p_incumbent, "원업체57", CATEGORY)).lastrowid
    coid2 = conn.execute(
        "INSERT INTO change_orders(case_id,round,status,incumbent_partner_id,incumbent_amount) "
        "VALUES(?,2,'전체재경매중',?,3000000)", (cid2, p_incumbent)).lastrowid
    auid2 = conn.execute(
        "INSERT INTO auctions(case_id,status,change_order_id,kind) "
        "VALUES(?,'진행',?,'전체재경매')", (cid2, coid2)).lastrowid
    bid2 = conn.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount) VALUES(?,?,?,20000000)",
        (auid2, p_rival, "경쟁사57")).lastrowid
    conn.commit(); conn.close()
    before2 = _n_gate_rows(cid2)

    with client.session_transaction() as sess:
        _admin_sess(sess)
    r2 = client.post(f"/api/change-orders/{coid2}/close-full",
                     json={"bid_id": bid2, "force": True,
                           "insurer_instruction": "2026-08-25 유선 지시 — 증액 진행"},
                     headers=_hdr)
    chk(r2.status_code == 200, "STEP① 전체재경매 초과 금액(20,000,000원)으로 낙찰 확정",
        (r2.status_code, r2.get_json()))
    after2 = _n_gate_rows(cid2)
    chk(after2 == before2 + 1,
        "★★★ ① close-full 도 낙찰 즉시 도급 적법성 스냅샷을 남긴다(고치기 전엔 0)",
        (before2, after2))
    conn = DB.get_db()
    last_gate2 = dict(conn.execute(
        "SELECT code, ok, amount FROM contract_gate_log WHERE case_id=? "
        "ORDER BY id DESC LIMIT 1", (cid2,)).fetchone())
    conn.close()
    chk(last_gate2["amount"] == 20000000 and last_gate2["ok"] == 0,
        "★★★ ① 스냅샷 금액이 실제 낙찰가(20,000,000)이고 초과 판정이다", last_gate2)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 실행 — ② 판정기준(est_price vs 확정가) 재현")
    # ──────────────────────────────────────────────────────────
    #  2트랙(사진 없이 접수) — est_price 는 늘 비어 있고 실제 계약금액은 award_amount 에만 있다
    conn = DB.get_db()
    cid3 = conn.execute(
        "INSERT INTO cases(case_no,status,est_price,award_amount,category,region) "
        "VALUES(?,'시공중',NULL,?,?,'서울')", (_no("57T-"), 20000000, CATEGORY)).lastrowid
    conn.commit(); conn.close()

    conn = DB.get_db()
    res_direct = CP.gate(conn, cid3)   # amount 인자 없이 — 화면(admin.js caseGate)과 같은 호출
    conn.close()
    chk(res_direct["ok"] is False,
        "★★★ ② est_price 가 비어 있어도(2트랙) 실제 계약금액(2천만원)으로 올바르게 막는다"
        "(고치기 전엔 판정금액이 0원이 되어 무조건 통과)", res_direct)

    with client.session_transaction() as sess:
        _admin_sess(sess)
    r3 = client.get(f"/api/cases/{cid3}/contract-gate")   # amount 파라미터 없음 — 화면과 동일
    d3 = r3.get_json()
    chk(d3.get("gate", {}).get("ok") is False,
        "★★★ ② HTTP 로도(화면이 실제로 부르는 그대로) 올바르게 막힌다"
        "(고치기 전엔 화면에 무조건 초록 '도급가능'이 떴다)", d3)

    # ══════════════════════════════════════════════════════════
    print("\n[4] 실행 — ③ NaN 입력 크래시 재현")
    # ──────────────────────────────────────────────────────────
    r4 = client.post("/api/repair-estimate",
                     json={"pattern": "guardrail_section", "inputs": {"L": "nan", "s": 4}},
                     headers=_hdr)
    chk(r4.status_code == 400,
        "★★★ ③ NaN 입력이 500 크래시 대신 400 으로 정중히 거부된다", (r4.status_code, r4.get_json()))

    r4b = client.post("/api/repair-estimate",
                      json={"pattern": "guardrail_section", "inputs": {"L": 10, "s": 4}},
                      headers=_hdr)
    chk(r4b.status_code == 200, "★ 대조군 — 정상 숫자 입력은 그대로 계산된다(과잉차단 아님)",
        (r4b.status_code, r4b.get_json()))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드57 실측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
