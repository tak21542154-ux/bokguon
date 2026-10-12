# -*- coding: utf-8 -*-
"""스캔 521라운드 회귀 — 전체재경매 낙찰확정(api_co_close_full)에서 피해자
안내가 통째로 빠져 있던 결함.

형제 비교: 사건의 담당업체(cases.partner_id)가 확정/교체되는 경로는 넷이다 —
  ① 보험사가 경매 낙찰을 승인(api_insurer_award, 4520행 부근)
  ② 관리자가 직접 낙찰 확정(api_case_award, 11384행 부근)
  ③ 보험사가 1차합의(현장 실견적)를 승인(api_insurer_field_agreement_decision, 18054행)
  ④ 전체 재경매 낙찰확정(api_co_close_full, 10836행) — 원업체가 증액 변경견적을
     거절하거나 유찰돼 전체 재경매가 열리고, 새 업체가 낙찰돼 cases.partner_id
     자체가 옛 업체에서 새 업체로 **교체**되는 경로.
①·②는 4627행 주석이 명시하는 원칙("피해자 안내는 낙찰 경로와 무관하게
나가야 한다 — 같은 사건인데 누가 승인했느냐에 따라 어떤 피해자는 연락을
받고 어떤 피해자는 아무 소식 없이 모르는 업체가 찾아오게 된다")에 따라
notify_victim() 을 부르고, round515가 ③에도 같은 원칙을 적용했다. 그런데
④는 **담당업체를 통째로 교체하는 경로인데도** 그 원칙이 아직 안 왔다 —
①·②·③보다 오히려 "모르는 업체가 찾아온다"는 위험이 더 직접적으로
들어맞는데(원업체 A 가 온다고 들은 피해자에게 실제로는 새 업체 B 가
찾아간다), 이 경로만 낙찰 상대(승자)·탈락자(notify_bid_losers) 통지는
있으면서 피해자 통지만 빠져 있었다.

round521 수정: notify_bid_losers 호출 다음(=낙찰확정 분기 안쪽, DB.log 이전)에
형제 세 경로와 같은 문구로 notify_victim() 을 추가했다.

[1] 소스 확인 — api_co_close_full() 안에 [라운드521] 표식과 notify_victim()
    호출이 실제로 있고, notify_bid_losers 다음 · 최종 DB.log 이전(낙찰 확정
    분기 안쪽)에 정확히 자리한다.
[2] 실행 — 사건을 '시공중'(원업체 A 배정)으로 앉히고 원업체가 증액을
    거절한 상태를 재현한 뒤, 실제 엔드포인트로 전체재경매 오픈→신규업체 B
    투찰→마감(낙찰확정)까지 실제 Flask 테스트클라이언트로 진행시켜,
    notifications 테이블에 '피해자안내' 행이 실제로 1건 쌓이고 그 문구에
    새로 선정된 업체명이 담기는지 확인.
[3] 되돌림-증명 — app.py 파일 자체는 건드리지 않는다(동시 세션이 app.py를
    같이 건드릴 수 있는 환경이라 전체 소스 스왑은 피한다 — round520과 같은
    원칙). 대신 이 라운드가 새로 부르기 시작한 딱 그 호출(notify_victim)만
    무력화해 같은 인과관계를 증명한다 — round521 이전 코드는 이 함수 안에서
    notify_victim 을 아예 호출하지 않았으므로 효과가 동일하다. 별도 사건으로
    같은 시나리오를 다시 돌려, 낙찰확정 자체(구조)는 그대로 성공하면서
    피해자안내만 0건으로 돌아가는지 대조한다(=이 테스트가 실제로 결함을
    잡아낼 능력이 있는지 증명). 끝나면 원래 함수로 되돌린다.
"""
import io
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 521라운드 회귀 — 전체재경매 낙찰확정 시 피해자 안내 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
_fi = APP_SRC.find("def api_co_close_full(coid):")
_losers_call = APP_SRC.find('notify_bid_losers(conn, (au["id"] if au else None)', _fi)
_mark_start = APP_SRC.find("#  ⚠⚠ [라운드521]", _fi)
_mark_end = APP_SRC.find("    if _inst:", _mark_start)
NEW_BLOCK = APP_SRC[_mark_start:_mark_end] if _fi > 0 and _mark_start > _fi else ""

chk(_fi > 0, "api_co_close_full() 함수를 소스에서 찾았다")
chk(bool(NEW_BLOCK) and "notify_victim(" in NEW_BLOCK,
    "★★★★★ 낙찰확정 분기에 [라운드521] notify_victim() 블록이 실제로 있다",
    NEW_BLOCK[:80] if NEW_BLOCK else "블록을 못 뽑음")
_dblog_final = APP_SRC.find('DB.log(conn, actor(), "전체 재경매 낙찰",', _fi)
chk(0 < _fi < _losers_call < _mark_start < _mark_end <= _dblog_final,
    "블록 위치가 notify_bid_losers 다음 · 최종 DB.log 이전(낙찰확정 분기 안쪽)이다",
    (_fi, _losers_call, _mark_start, _mark_end, _dblog_final))

# ============================================================
print("\n[2] 실행 준비 — 격리 스크래치 DB")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round521_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
DB = A = None
try:
    import db as DB
    DB.init_db()
    import app as A
    #  ⚠ require_role() 은 세션의 admin 이름으로 admins 표를 다시 조회해
    #    살아 있는지 본다(_account_alive) — 이 행이 없으면 세션에 admin_role 을
    #    아무리 심어도 "계정이 삭제되었습니다"로 401 이 난다(회귀 아님, 이
    #    테스트 자신의 준비 누락이었다).
    _c0 = DB.get_db()
    _c0.execute("INSERT INTO admins(username,password_hash,name,role) "
                "VALUES('admin','x','검증','최고관리자')")
    _c0.commit(); _c0.close()
    chk(True, "스크래치 DB·app 모듈 로드 성공", os.environ["BOKGUON_DB_PATH"])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 준비 실패", f"{type(e).__name__} {e}")


def _admin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "admin"
        sess["admin_name"] = "검증"
        sess["admin_role"] = "최고관리자"
        sess["_csrf"] = "r521-csrf"
    return c


def _partner_client(pid, name):
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["partner_id"] = pid
        sess["partner_name"] = name
        sess["partner_type"] = "시행사"
        sess["_csrf"] = "r521-csrf"
    return c


H = {"X-CSRF-Token": "r521-csrf"}


def _setup_scenario(conn, tag):
    """사건을 '시공중'(원업체 A 배정)으로 앉히고, 원업체가 증액 변경견적을
    거절해 전체 재경매가 필요해진 상태를 그대로 심는다. 반환 (cid, coid, pid_b)."""
    iid = conn.execute(
        f"INSERT INTO insurers(name,status) VALUES('R521보험{tag}','활성')").lastrowid
    pid_a = conn.execute(
        "INSERT INTO partners(name,partner_type,status,lat,lng) "
        f"VALUES('R521원업체{tag}','시행사','활성',37.5,127.0)").lastrowid
    pid_b = conn.execute(
        "INSERT INTO partners(name,partner_type,status,lat,lng) "
        f"VALUES('R521신규업체{tag}','시행사','활성',37.6,127.1)").lastrowid
    #  ⚠ 피해자 연락처를 반드시 채운다 — notify_victim() 은 victim_phone 이
    #    없으면 조용히 아무 일도 안 하고 리턴한다. 연락처 없이 돌리면 "결함이
    #    있어도 없어도 통지 0건"이라 이 테스트가 결함을 구분 못 하게 된다.
    #  ⚠ 사건을 처음부터 '시공중'(원업체 A 배정)으로 직접 앉힌다 — 이 회귀가
    #    보는 것은 "원경매→낙찰"이 아니라 "이미 배정된 사건의 업체가 전체
    #    재경매로 교체될 때" 이므로, 최초 배정 경로 자체는 검증 대상이 아니다.
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,lat,lng,"
        "victim_name,victim_phone,partner_id,partner_name,award_amount,low_price,"
        "awarded_at,award_route) "
        "VALUES(?,'시공중','가드레일','서울',?,37.5,127.0,?,?,?,?,5000000,5000000,"
        "datetime('now'),'경매')",
        (f"26-521{tag}", iid, f"피해자521{tag}", f"010555{tag}5521", pid_a,
         f"R521원업체{tag}")).lastrowid
    coid = conn.execute(
        "INSERT INTO change_orders(case_id,round,incumbent_partner_id,incumbent_amount,"
        "combined_amount,status,created_at) "
        "VALUES(?,1,?,5000000,6000000,'거절',?)",
        (cid, pid_a, DB.now())).lastrowid
    conn.commit()
    return cid, coid, pid_b


def _run_flow(cid, coid, pid_b, name_b):
    """전체재경매 오픈→신규업체 B 투찰→마감(낙찰확정)까지 실제 엔드포인트로 진행.
    반환 dict(open/bid/close 응답, 사건·변경견적 사후 상태, 피해자안내 건수)."""
    admin_c = _admin_client()
    r_open = admin_c.post(f"/api/change-orders/{coid}/full-reauction", json={}, headers=H)

    conn = DB.get_db()
    au = conn.execute(
        "SELECT id FROM auctions WHERE change_order_id=? AND kind='전체재경매' "
        "ORDER BY id DESC LIMIT 1", (coid,)).fetchone()
    conn.close()
    au_id = au["id"] if au else None

    r_bid = None
    if au_id:
        partner_b_c = _partner_client(pid_b, name_b)
        r_bid = partner_b_c.post("/api/partner/reauction-bids",
                                  json={"auction_id": au_id, "amount": 4500000, "days": 5},
                                  headers=H)

    conn = DB.get_db()
    bid = conn.execute(
        "SELECT id FROM bids WHERE auction_id=? AND partner_id=? "
        "ORDER BY id DESC LIMIT 1", (au_id, pid_b)).fetchone() if au_id else None
    conn.close()
    bid_id = bid["id"] if bid else None

    r_close = None
    if bid_id:
        r_close = admin_c.post(f"/api/change-orders/{coid}/close-full",
                                json={"bid_id": bid_id, "force": True,
                                      "insurer_instruction": "관리자 유선지시 확인완료"},
                                headers=H)

    conn = DB.get_db()
    case_after = conn.execute(
        "SELECT status, partner_id, partner_name FROM cases WHERE id=?", (cid,)).fetchone()
    victim_rows = conn.execute(
        "SELECT ntype, channel, message FROM notifications "
        " WHERE case_id=? AND ntype='피해자안내'", (cid,)).fetchall()
    conn.close()

    return {
        "open_status": r_open.status_code,
        "bid_status": r_bid.status_code if r_bid else None,
        "bid_body": r_bid.get_json() if r_bid else None,
        "close_status": r_close.status_code if r_close else None,
        "close_body": r_close.get_json() if r_close else None,
        "case_after": dict(case_after) if case_after else None,
        "victim_notify_count": len(victim_rows),
        "victim_notify_rows": [dict(r) for r in victim_rows],
    }


# ============================================================
print("\n[2] 실행 — 전체재경매 낙찰확정 시 피해자안내 적재 확인 (현재 코드)")
# ------------------------------------------------------------
if DB and A:
    try:
        conn = DB.get_db()
        cid, coid, pid_b = _setup_scenario(conn, "a")
        conn.close()

        fixed = _run_flow(cid, coid, pid_b, "R521신규업체a")
        chk(fixed["open_status"] == 200, "전체재경매 오픈(관리자) 200", fixed["open_status"])
        chk(fixed["bid_status"] == 200, "신규업체 재경매 투찰 200", fixed["bid_body"])
        chk(fixed["close_status"] == 200 and (fixed["close_body"] or {}).get("ok") is True,
            "낙찰확정(마감) 자체는 200으로 성공한다", fixed["close_body"])
        chk(fixed["case_after"]["status"] == "시공중"
            and fixed["case_after"]["partner_name"] == "R521신규업체a",
            "★ 사건 담당업체가 원업체(A)에서 신규업체(B)로 실제 교체된다",
            fixed["case_after"])
        chk(fixed["victim_notify_count"] == 1,
            "★★★★★ 피해자안내(notifications.ntype='피해자안내') 1건이 실제로 쌓인다",
            fixed["victim_notify_count"])
        _rows = fixed["victim_notify_rows"]
        _msg = _rows[0]["message"] if _rows else ""
        chk("R521신규업체a" in _msg and "선정되었습니다" in _msg,
            "★★★★★ 피해자 안내 문구에 새로 선정된 업체명이 실제로 담긴다",
            _msg)
    except Exception as e:                                          # noqa: BLE001
        chk(False, "★★★ [2] 실행", f"{type(e).__name__} {e}")
else:
    chk(False, "[2] 건너뜀 — 준비 단계 실패")

# ============================================================
print("\n[3] 되돌림-증명 — notify_victim 호출을 무력화하면(round521 이전 상태와 "
      "동일한 효과) 낙찰확정 구조는 그대로 성공하면서 피해자안내만 0건이 된다")
# ------------------------------------------------------------
if DB and A:
    try:
        conn = DB.get_db()
        cid2, coid2, pid_b2 = _setup_scenario(conn, "b")
        conn.close()

        #  코드를 되돌리는 대신(동시 세션이 app.py 를 함께 건드릴 수 있는 환경이라
        #  전체 소스 스왑은 피한다), 이 라운드가 새로 부르기 시작한 딱 그 호출만
        #  무력화해 같은 인과관계를 증명한다 — round521 이전 코드는 이 함수 안에서
        #  notify_victim 을 아예 호출하지 않았으므로 효과가 동일하다(round520과
        #  같은 원칙, DB.is_legacy_hash 대신 notify_victim 을 누른다).
        _real_notify_victim = A.notify_victim
        A.notify_victim = lambda *a, **k: None
        try:
            broken = _run_flow(cid2, coid2, pid_b2, "R521신규업체b")
        finally:
            A.notify_victim = _real_notify_victim

        chk(broken["close_status"] == 200 and (broken["close_body"] or {}).get("ok") is True,
            "무력화 상태에서도 낙찰확정 자체는 그대로 성공한다(구조는 안 바뀐다)",
            broken["close_body"])
        chk(broken["case_after"]["status"] == "시공중"
            and broken["case_after"]["partner_name"] == "R521신규업체b",
            "무력화 상태에서도 담당업체 교체 자체는 그대로 된다", broken["case_after"])
        chk(broken["victim_notify_count"] == 0,
            "★★★★★ 무력화 상태(=round521 이전 상태)는 피해자안내가 0건이다"
            " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
            broken["victim_notify_count"])

        # 복원이 실제로 원 함수로 되돌아갔는지 — 세 번째 사건으로 재확인.
        conn = DB.get_db()
        cid3, coid3, pid_b3 = _setup_scenario(conn, "c")
        conn.close()
        restored_run = _run_flow(cid3, coid3, pid_b3, "R521신규업체c")
        chk(restored_run["victim_notify_count"] == 1,
            "★★★★★ 무력화 해제 후 재실행하면 피해자안내가 다시 1건 쌓인다"
            "(A.notify_victim 이 원 함수로 정확히 복원됐다)",
            restored_run["victim_notify_count"])
    except Exception as e:                                          # noqa: BLE001
        chk(False, "★★★ [3] 되돌림-증명", f"{type(e).__name__} {e}")
else:
    chk(False, "[3] 건너뜀 — 준비 단계 실패")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
