# -*- coding: utf-8 -*-
"""스캔 522라운드 회귀 — 전체재경매 낙찰확정(api_co_close_full)에서 보험사
통지(인앱 + case.awarded 웹훅)가 통째로 빠져 있던 결함.

배경(round521이 남긴 리드): 사건의 담당업체(cases.partner_id)가 확정·교체되는
경로는 넷 — ①보험사 경매낙찰 승인(api_insurer_award, 4523행)·②관리자 직접
낙찰확정(api_case_award, 11397행)·③보험사 1차합의 승인
(api_insurer_field_agreement_decision, 18068행)·④전체재경매 낙찰확정
(api_co_close_full, 10836행). 이 넷 중 담당업체가 통째로 "교체"되는 것은
①·②·④뿐이다(③은 첫 배정). round521은 이 중 ④만 피해자 안내가 빠져 있던
것을 고치면서, "①·②·④가 모두 보내는 case.awarded 웹훅을 ④만 안 보낸다"는
것도 조사 중 확인했지만 그 라운드의 범위 밖으로 남겨 뒀다
(app.py:10836 부근 라운드522 진입 시점 주석 참고).

이번 라운드가 직접 조사(하위위임 없음)로 검증한 것 — 이 리드가 진짜 결함인지:
  · WEBHOOK_EVENTS(app.py:18972)에 정의된 6개 이벤트 중 case.awarded 를
    대체할 다른 이벤트는 없다 — 이 코드베이스에 "변경건 재낙찰"을 위한
    별도 웹훅 이벤트는 아예 존재하지 않는다.
  · api_co_close_full()의 낙찰 분기는 cases.partner_id 를 옛 업체에서 새
    업체로 **통째로 교체**한다(10985행 UPDATE, award_route='경매'로 스탬프) —
    ①·②와 데이터 모델 수준에서 동일한 "새로운 낙찰" 이벤트다.
  · api_case_award(②)는 이 함수와 같은 등급 데코레이터(@require_role
    ("중간관리자"))를 쓰는 가장 가까운 형제인데, insurer_id 가 있을 때만
    (if c.get("insurer_id"):) in-app 통지(notify, audience_type="insurer")
    + deliver_webhook("case.awarded", ..., route="경매") 를 함께 보낸다 — ④만
    똑같이 없었다. 결론: 진짜 결함이며, 다른 경로로 보완되지 않는다.
  · (참고로 원업체가 증액을 그대로 수락하는 api_co_decision 의 수락 분기는
    업체 교체가 없어 이 웹훅 계약의 범위 밖이다 — 별도 문제이며 이번 회귀
    대상이 아니다.)

round522 수정 — api_co_close_full()의 SELECT 를 insurer_id·insurer 까지
확장하고, notify_bid_losers 다음(=round521 블록 바로 앞)에 형제 ②
(api_case_award)와 정확히 같은 모양으로 in-app 통지 + case.awarded 웹훅을
추가했다(새 헬퍼·새 이벤트 없음, 기존 notify()/deliver_webhook() 재사용).

[1] 소스 확인 — [라운드522] 표식·SELECT 확장·notify(audience_type="insurer")·
    deliver_webhook("case.awarded",...) 가 실제로 있고, notify_bid_losers
    다음 · [라운드521] 블록(=피해자 안내) 이전에 정확히 자리한다.
[2] 실행 — 사건을 '시공중'(원업체 A 배정)으로 앉히고 원업체가 증액을 거절한
    상태를 재현한 뒤, 실제 Flask 테스트클라이언트로 전체재경매 오픈→신규업체
    B 투찰→마감(낙찰확정)까지 진행시켜 (a) notifications 테이블에
    audience_type='insurer' 인 '낙찰확정' 알림이 1건 쌓이고 (b)
    webhook_deliveries 테이블에 event='case.awarded' 행이 1건 쌓이며 그
    payload 에 새 업체명·금액·route='경매'가 정확히 담기는지 확인.
[3] 되돌림-증명 — app.py 파일 자체는 건드리지 않는다(동시 세션이 app.py 를
    같이 건드릴 수 있는 환경 — round520·521 과 같은 원칙). 대신 이 라운드가
    새로 부르기 시작한 두 호출(notify/deliver_webhook)만 런타임에 무력화해
    같은 시나리오를 별도 사건으로 재실행 — 낙찰확정 자체(구조: 상태전이·
    담당업체 교체)는 그대로 성공하면서 보험사 통지·웹훅만 0건으로 돌아가는지
    대조한다(=이 테스트가 실제로 결함을 잡아낼 능력이 있는지 증명). 끝나면
    원래 함수로 되돌리고 세 번째 사건으로 복원을 재확인한다.
"""
import io
import json
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
print("  스캔 522라운드 회귀 — 전체재경매 낙찰확정 시 보험사 통지·웹훅 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
_fi = APP_SRC.find("def api_co_close_full(coid):")
_select_ext = APP_SRC.find(
    'SELECT case_no, partner_id, insurer_id, insurer FROM cases WHERE id=?', _fi)
_losers_call = APP_SRC.find('notify_bid_losers(conn, (au["id"] if au else None)', _fi)
#  ⚠ [라운드522] 표식은 이 함수 안에 두 곳(위 SELECT 확장 주석·아래 통지 블록
#    주석)에 있다 — 찾는 대상은 두 번째(통지 블록)이므로 반드시 _losers_call
#    **이후**부터 찾는다(_fi 부터 찾으면 SELECT 쪽 주석이 먼저 걸려 위치
#    단언이 엉뚱하게 실패한다).
_mark_start = APP_SRC.find("#  ⚠⚠ [라운드522]", _losers_call) if _losers_call > 0 else -1
_mark_end = APP_SRC.find("#  ⚠⚠ [라운드521]", _mark_start) if _mark_start > 0 else -1
NEW_BLOCK = APP_SRC[_mark_start:_mark_end] if (_fi > 0 and _mark_start > _fi and _mark_end > 0) else ""

chk(_fi > 0, "api_co_close_full() 함수를 소스에서 찾았다")
chk(_fi > 0 < _select_ext and _fi < _select_ext,
    "★ SELECT 가 insurer_id·insurer 까지 확장됐다(round521 리드)", _select_ext)
chk(bool(NEW_BLOCK) and 'notify(conn, "낙찰확정", "웹"' in NEW_BLOCK
    and 'audience_type="insurer"' in NEW_BLOCK,
    "★★★★★ 낙찰확정 분기에 [라운드522] 보험사 in-app 통지 블록이 실제로 있다",
    NEW_BLOCK[:120] if NEW_BLOCK else "블록을 못 뽑음")
chk(bool(NEW_BLOCK) and 'deliver_webhook(conn, c["insurer_id"], "case.awarded"' in NEW_BLOCK,
    "★★★★★ 같은 블록에 deliver_webhook(\"case.awarded\", ...) 호출이 실제로 있다",
    NEW_BLOCK[:200] if NEW_BLOCK else "블록을 못 뽑음")
chk('if c.get("insurer_id"):' in NEW_BLOCK,
    "insurer_id 없는 사건은 건드리지 않도록 형제(api_case_award)와 같은 가드가 있다")
chk('"route": "경매"' in NEW_BLOCK,
    "route 키가 형제 두 곳(보험사 낙찰·어드민 낙찰)과 같은 값('경매')이다")
chk(0 < _fi < _select_ext < _losers_call < _mark_start < _mark_end,
    "블록 위치가 SELECT확장 다음·notify_bid_losers 다음·"
    "[라운드521]피해자안내 블록 이전이다",
    (_fi, _select_ext, _losers_call, _mark_start, _mark_end))

# ============================================================
print("\n[2] 실행 준비 — 격리 스크래치 DB")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round522_")
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
    #    살아 있는지 본다(_account_alive) — 이 행이 없으면 401 이 난다
    #    (round521 test 와 같은 준비 단계).
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
        sess["_csrf"] = "r522-csrf"
    return c


def _partner_client(pid, name):
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["partner_id"] = pid
        sess["partner_name"] = name
        sess["partner_type"] = "시행사"
        sess["_csrf"] = "r522-csrf"
    return c


H = {"X-CSRF-Token": "r522-csrf"}


def _setup_scenario(conn, tag):
    """사건을 '시공중'(원업체 A 배정, 보험사 연결)으로 앉히고, 원업체가 증액
    변경견적을 거절해 전체 재경매가 필요해진 상태를 그대로 심는다.
    반환 (cid, coid, pid_b, iid)."""
    iid = conn.execute(
        f"INSERT INTO insurers(name,status) VALUES('R522보험{tag}','활성')").lastrowid
    pid_a = conn.execute(
        "INSERT INTO partners(name,partner_type,status,lat,lng) "
        f"VALUES('R522원업체{tag}','시행사','활성',37.5,127.0)").lastrowid
    pid_b = conn.execute(
        "INSERT INTO partners(name,partner_type,status,lat,lng) "
        f"VALUES('R522신규업체{tag}','시행사','활성',37.6,127.1)").lastrowid
    #  사건을 처음부터 '시공중'(원업체 A 배정)으로 직접 앉힌다 — 이 회귀가 보는
    #  것은 "원경매→낙찰"이 아니라 "이미 배정된 사건의 업체가 전체 재경매로
    #  교체될 때 보험사 통지가 나가는가" 이므로, 최초 배정 경로는 검증 대상이 아니다.
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,lat,lng,"
        "victim_name,victim_phone,partner_id,partner_name,award_amount,low_price,"
        "awarded_at,award_route) "
        "VALUES(?,'시공중','가드레일','서울',?,37.5,127.0,?,?,?,?,5000000,5000000,"
        "datetime('now'),'경매')",
        (f"26-522{tag}", iid, f"피해자522{tag}", f"010666{tag}5522", pid_a,
         f"R522원업체{tag}")).lastrowid
    coid = conn.execute(
        "INSERT INTO change_orders(case_id,round,incumbent_partner_id,incumbent_amount,"
        "combined_amount,status,created_at) "
        "VALUES(?,1,?,5000000,6000000,'거절',?)",
        (cid, pid_a, DB.now())).lastrowid
    conn.commit()
    return cid, coid, pid_b, iid


def _run_flow(cid, coid, pid_b, iid, name_b):
    """전체재경매 오픈→신규업체 B 투찰→마감(낙찰확정)까지 실제 엔드포인트로 진행.
    반환 dict(응답들, 사건 사후 상태, 보험사 통지·웹훅 건수/내용)."""
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
    insurer_notify_rows = conn.execute(
        "SELECT ntype, channel, message, insurer_id FROM notifications "
        " WHERE case_id=? AND audience_type='insurer' AND ntype='낙찰확정'", (cid,)).fetchall()
    wh_rows = conn.execute(
        "SELECT insurer_id, event, case_no, payload, status FROM webhook_deliveries "
        " WHERE case_no=(SELECT case_no FROM cases WHERE id=?) AND event='case.awarded'",
        (cid,)).fetchall()
    conn.close()

    return {
        "open_status": r_open.status_code,
        "bid_status": r_bid.status_code if r_bid else None,
        "bid_body": r_bid.get_json() if r_bid else None,
        "close_status": r_close.status_code if r_close else None,
        "close_body": r_close.get_json() if r_close else None,
        "case_after": dict(case_after) if case_after else None,
        "insurer_notify_count": len(insurer_notify_rows),
        "insurer_notify_rows": [dict(r) for r in insurer_notify_rows],
        "webhook_count": len(wh_rows),
        "webhook_rows": [dict(r) for r in wh_rows],
        "iid": iid,
    }


# ============================================================
print("\n[2] 실행 — 전체재경매 낙찰확정 시 보험사 통지·웹훅 적재 확인 (현재 코드)")
# ------------------------------------------------------------
if DB and A:
    try:
        conn = DB.get_db()
        cid, coid, pid_b, iid = _setup_scenario(conn, "a")
        conn.close()

        fixed = _run_flow(cid, coid, pid_b, iid, "R522신규업체a")
        chk(fixed["open_status"] == 200, "전체재경매 오픈(관리자) 200", fixed["open_status"])
        chk(fixed["bid_status"] == 200, "신규업체 재경매 투찰 200", fixed["bid_body"])
        chk(fixed["close_status"] == 200 and (fixed["close_body"] or {}).get("ok") is True,
            "낙찰확정(마감) 자체는 200으로 성공한다", fixed["close_body"])
        chk(fixed["case_after"]["status"] == "시공중"
            and fixed["case_after"]["partner_name"] == "R522신규업체a",
            "사건 담당업체가 원업체(A)에서 신규업체(B)로 실제 교체된다",
            fixed["case_after"])

        chk(fixed["insurer_notify_count"] == 1,
            "★★★★★ 보험사 in-app 통지(audience_type=insurer, ntype=낙찰확정) 1건이 실제로 쌓인다",
            fixed["insurer_notify_count"])
        _nrows = fixed["insurer_notify_rows"]
        _nmsg = _nrows[0]["message"] if _nrows else ""
        chk("R522신규업체a" in _nmsg and "4,500,000" in _nmsg,
            "★★★★★ 보험사 통지 문구에 새 업체명·낙찰금액이 실제로 담긴다", _nmsg)
        chk(bool(_nrows) and _nrows[0]["insurer_id"] == iid,
            "보험사 통지가 이 사건의 실제 insurer_id 로 간다", _nrows)

        chk(fixed["webhook_count"] == 1,
            "★★★★★ case.awarded 웹훅(webhook_deliveries) 1건이 실제로 쌓인다",
            fixed["webhook_count"])
        _wrows = fixed["webhook_rows"]
        _wpayload = json.loads(_wrows[0]["payload"])["data"] if _wrows else {}
        chk(bool(_wrows) and _wrows[0]["insurer_id"] == iid,
            "웹훅이 이 사건의 실제 insurer_id 로 기록된다", _wrows)
        chk(_wpayload.get("partner_name") == "R522신규업체a"
            and _wpayload.get("amount") == 4500000
            and _wpayload.get("status") == "시공중"
            and _wpayload.get("route") == "경매",
            "★★★★★ 웹훅 payload 가 형제 두 경로와 같은 키·같은 값을 담는다"
            "(partner_name/amount/status/route)", _wpayload)
    except Exception as e:                                          # noqa: BLE001
        chk(False, "★★★ [2] 실행", f"{type(e).__name__} {e}")
else:
    chk(False, "[2] 건너뜀 — 준비 단계 실패")

# ============================================================
print("\n[3] 되돌림-증명 — notify/deliver_webhook 호출을 무력화하면(round522 이전 "
      "상태와 동일한 효과) 낙찰확정 구조는 그대로 성공하면서 보험사 통지·웹훅만 0건이 된다")
# ------------------------------------------------------------
if DB and A:
    try:
        conn = DB.get_db()
        cid2, coid2, pid_b2, iid2 = _setup_scenario(conn, "b")
        conn.close()

        #  코드를 되돌리는 대신(동시 세션이 app.py 를 함께 건드릴 수 있는 환경이라
        #  전체 소스 스왑은 피한다 — round520·521 과 같은 원칙), 이 라운드가 새로
        #  부르기 시작한 두 호출만 무력화해 같은 인과관계를 증명한다. notify() 는
        #  이 요청 안에서 다른 목적(낙찰자·탈락자·피해자 통지)으로도 불리지만,
        #  이 broken 실행에서는 그 부수 통지들의 건수를 검사하지 않으므로
        #  전부 무력화해도 아래 단언의 타당성에는 영향이 없다.
        _real_notify = A.notify
        _real_deliver_webhook = A.deliver_webhook
        A.notify = lambda *a, **k: None
        A.deliver_webhook = lambda *a, **k: None
        try:
            broken = _run_flow(cid2, coid2, pid_b2, iid2, "R522신규업체b")
        finally:
            A.notify = _real_notify
            A.deliver_webhook = _real_deliver_webhook

        chk(broken["close_status"] == 200 and (broken["close_body"] or {}).get("ok") is True,
            "무력화 상태에서도 낙찰확정 자체는 그대로 성공한다(구조는 안 바뀐다)",
            broken["close_body"])
        chk(broken["case_after"]["status"] == "시공중"
            and broken["case_after"]["partner_name"] == "R522신규업체b",
            "무력화 상태에서도 담당업체 교체 자체는 그대로 된다", broken["case_after"])
        chk(broken["insurer_notify_count"] == 0,
            "★★★★★ 무력화 상태(=round522 이전 상태)는 보험사 in-app 통지가 0건이다"
            " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
            broken["insurer_notify_count"])
        chk(broken["webhook_count"] == 0,
            "★★★★★ 무력화 상태(=round522 이전 상태)는 case.awarded 웹훅이 0건이다",
            broken["webhook_count"])

        # 복원이 실제로 원 함수로 되돌아갔는지 — 세 번째 사건으로 재확인.
        conn = DB.get_db()
        cid3, coid3, pid_b3, iid3 = _setup_scenario(conn, "c")
        conn.close()
        restored_run = _run_flow(cid3, coid3, pid_b3, iid3, "R522신규업체c")
        chk(restored_run["insurer_notify_count"] == 1 and restored_run["webhook_count"] == 1,
            "★★★★★ 무력화 해제 후 재실행하면 통지·웹훅이 다시 1건씩 쌓인다"
            "(A.notify/A.deliver_webhook 이 원 함수로 정확히 복원됐다)",
            (restored_run["insurer_notify_count"], restored_run["webhook_count"]))
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
