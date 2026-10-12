# -*- coding: utf-8 -*-
"""스캔 634라운드 회귀(직접조사, 하위위임 없음) — notify()의 반복형 알림
(_REPEATING_NTYPES: 완료승인독촉·낙찰승인독촉·완료보고독촉) 중복접기가
(ntype, audience_type, case_id)만 보고 옛 '안 읽음' 알림을 read_at으로
접었다 — 실제 수신자(insurer_id/partner_id)는 전혀 보지 않았다.

전체재경매 낙찰확정(app.py 약 11729행)은 '시공중'·'완료보고지연' 상태에서
cases.partner_id를 통째로 새 업체로 갈아치우는 정상 절차다(그 함수 자신의
주석: "'시공중'·'완료보고지연'은 완료 보고 전이라 교체가 정상 절차다" —
완료 보고가 올라온 뒤에는 이 UPDATE의 WHERE 절이 막는다). 그 재배정 뒤
같은 사건에 같은 반복형 ntype(예: 완료보고독촉, api_case_remind_report가
유일한 호출부)을 새 업체에게 보내면, 예전 코드는 case_id·ntype·
audience_type만 대조해 **옛 업체가 한 번도 열어 본 적 없는 알림까지
read_at을 채워 읽음으로 만들었다**(아래 [3][4]에서 직접 실행으로 재현·
대조). 협력사 포털의 '내 알림' 배지 수·감사기록이 "본 적 없는데 읽었다"고
거짓말하게 되는, 이번 라운드가 찾아야 했던 '읽음배지·알림중복접기' 결함.

고침(app.py, notify() 딱 한 곳 — 5개 반복형 ntype 전부가 거치는 유일한
합류점): 중복접기 UPDATE의 WHERE 절에 insurer_id·partner_id COALESCE
비교 두 줄을 추가해 **수신자까지 같을 때만** 옛 행을 접는다. 관리자
브로드캐스트(둘 다 NULL)와 같은 수신자에게 반복되는 경우는 기존과
동일하게 동작해 회귀가 없다([3]의 대조군에서 함께 확인).

되돌리기-증명은 round414·490·507·610·615·621·631·632가 확립한 안전패턴
그대로 적용한다 — notify()는 뷰함수가 아니라 app.py 전역에서 이름으로
직접 불리는 평범한 함수라, app.py의 전역(vars(A))을 복사한 네임스페이스에
옛(되돌린) 함수 본문만 exec로 재구성하고, 호출부들이 실제로 참조하는
`A.notify` 모듈 속성 자체를 그 함수 객체로 잠깐 바꿔치기했다가 finally에서
원래 객체로 되돌린다. 진짜 app.py 파일은 이 세션 내내 단 한 바이트도
수정하지 않는다(끝에 소스 바이트 단위로 재확인).
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


print("=" * 72)
print("  스캔 634라운드 회귀 — notify() 반복알림 중복접기가 수신자를 안 본다")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
APP_SRC_BEFORE = io.open(APP_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — notify() 전체를 통째로 추출, 고친 SQL이 정확히 있다")
# ──────────────────────────────────────────────────────────────
START = "def notify(conn, ntype, channel, target, message,"
_END_ANCHOR = 'VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"""'
_s = APP_SRC_BEFORE.find(START)
_a = APP_SRC_BEFORE.find(_END_ANCHOR, _s) if _s > 0 else -1
_e = APP_SRC_BEFORE.find("\n    )\n", _a) if _a > 0 else -1
_e = _e + len("\n    )\n") if _e > 0 else -1
CURRENT_FUNC = APP_SRC_BEFORE[_s:_e] if _s > 0 and _e > _s else ""

chk(bool(CURRENT_FUNC), "notify() 함수 전체를 찾았다")
chk(bool(CURRENT_FUNC) and APP_SRC_BEFORE.count(CURRENT_FUNC) == 1,
    "함수 텍스트가 소스에 유일하다")

NEW_SQL_CALL = (
    '            conn.execute(\n'
    '                "UPDATE notifications SET read_at=? "\n'
    '                " WHERE ntype=? AND read_at IS NULL "\n'
    '                "   AND COALESCE(audience_type,\'\')=COALESCE(?,\'\') "\n'
    '                "   AND COALESCE(case_id,0)=COALESCE(?,0) "\n'
    '                "   AND COALESCE(insurer_id,0)=COALESCE(?,0) "\n'
    '                "   AND COALESCE(partner_id,0)=COALESCE(?,0)",\n'
    '                (DB.now(), ntype, audience_type, case_id, insurer_id, partner_id))\n'
)
OLD_SQL_CALL = (
    '            conn.execute(\n'
    '                "UPDATE notifications SET read_at=? "\n'
    '                " WHERE ntype=? AND read_at IS NULL "\n'
    '                "   AND COALESCE(audience_type,\'\')=COALESCE(?,\'\') "\n'
    '                "   AND COALESCE(case_id,0)=COALESCE(?,0)",\n'
    '                (DB.now(), ntype, audience_type, case_id))\n'
)

chk(CURRENT_FUNC.count(NEW_SQL_CALL) == 1,
    "① 고친 SQL(insurer_id·partner_id 대조 포함)이 정확히 한 번 있다")
chk(OLD_SQL_CALL not in CURRENT_FUNC,
    "② 옛(수신자를 안 보는) SQL은 지금 소스에 없다(대조군)")

ORIGINAL_FUNC = CURRENT_FUNC.replace(NEW_SQL_CALL, OLD_SQL_CALL, 1)
chk(ORIGINAL_FUNC != CURRENT_FUNC and OLD_SQL_CALL in ORIGINAL_FUNC,
    "③ 되돌린 사본이 실제로 옛 SQL을 담고 있다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 준비 — 스크래치 DB + 실제 app.py import")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round634_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "verify.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB                 # noqa: E402
DB.init_db()
import app as A                 # noqa: E402

_n = [0]


def _seed_reassignment_case():
    """실제 흐름을 흉내낸다 — 사건이 시공사A에게 낙찰된 뒤(status='시공중')
    전체재경매로 시공사B에게 재배정된다. app.py의 실제 재배정 UPDATE(약
    11729행)가 허용하는 상태('시공중'/'완료보고지연') 그대로 사용한다."""
    _n[0] += 1
    k = _n[0]
    conn = DB.get_db()
    pidA = conn.execute(f"INSERT INTO partners(name) VALUES('R634A{k}')").lastrowid
    pidB = conn.execute(f"INSERT INTO partners(name) VALUES('R634B{k}')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,partner_id,partner_name,created_at) "
        f"VALUES('R634-{k}','시공중',?,'R634A{k}',?)", (pidA, DB.now())).lastrowid
    conn.commit()
    return conn, cid, pidA, pidB


def _run_scenario(notify_fn):
    """1차: 시공사A에게 완료보고독촉 → 재배정(cases.partner_id 통째 교체) →
    2차: 같은 사건·같은 ntype으로 시공사B에게 다시 독촉.
    반환: A 앞 알림 행이 부당하게 '읽음'이 됐는지 + 실제 포털 배지 수치."""
    conn, cid, pidA, pidB = _seed_reassignment_case()
    notify_fn(conn, "완료보고독촉", "알림톡", "R634A", "1차 독촉",
              audience_type="partner", partner_id=pidA, case_id=cid, url="/app/partner")
    conn.commit()
    #  실제 재배정 경로와 같은 모양: cases.partner_id를 통째로 새 업체로
    conn.execute("UPDATE cases SET partner_id=? WHERE id=?", (pidB, cid))
    conn.commit()
    notify_fn(conn, "완료보고독촉", "알림톡", "R634B", "2차 독촉(재배정 후)",
              audience_type="partner", partner_id=pidB, case_id=cid, url="/app/partner")
    conn.commit()
    rowA = conn.execute(
        "SELECT read_at FROM notifications WHERE ntype='완료보고독촉' AND partner_id=?",
        (pidA,)).fetchone()
    rowB = conn.execute(
        "SELECT read_at FROM notifications WHERE ntype='완료보고독촉' AND partner_id=?",
        (pidB,)).fetchone()
    conn.close()
    return {"a_wrongly_read": rowA["read_at"] is not None, "b_read_at": rowB["read_at"],
            "pidA": pidA, "pidB": pidB}


def _run_same_recipient_scenario(notify_fn):
    """대조군 — 같은 수신자에게 반복되면 여전히 최신 한 건만 안읽음으로
    남아야 한다(이번 수정이 원래 의도한 접기 기능 자체를 깨지 않았는지)."""
    conn, cid, pidA, _pidB = _seed_reassignment_case()
    notify_fn(conn, "완료보고독촉", "알림톡", "R634A", "1차 독촉",
              audience_type="partner", partner_id=pidA, case_id=cid, url="/app/partner")
    conn.commit()
    notify_fn(conn, "완료보고독촉", "알림톡", "R634A", "2차 독촉(같은 수신자)",
              audience_type="partner", partner_id=pidA, case_id=cid, url="/app/partner")
    conn.commit()
    rows = conn.execute(
        "SELECT read_at FROM notifications WHERE ntype='완료보고독촉' AND partner_id=? "
        "ORDER BY id", (pidA,)).fetchall()
    conn.close()
    return [r["read_at"] for r in rows]


def _partner_unread_badge(pid):
    """실제 포털 벨 API(GET /api/partner/notifications)가 내려주는 미읽음
    배지 수치 — DB 행이 아니라 사용자가 실제로 보는 값을 확인한다."""
    cl = A.app.test_client()
    with cl.session_transaction() as s:
        s["partner_id"] = pid
    r = cl.get("/api/partner/notifications")
    return r.get_json()["unread"]


try:
    print("\n[3] 현재(고친) 코드로 실행 — 수신자가 다르면 옛 알림을 건드리지 않는다")
    out_fixed = _run_scenario(A.notify)
    chk(out_fixed["a_wrongly_read"] is False,
        "★★★★★ 고친 코드: 재배정 후 새 알림을 보내도 옛 수신자(A)의 안읽음은 그대로다",
        out_fixed)
    chk(out_fixed["b_read_at"] is None,
        "새 수신자(B)의 알림은 정상적으로 안읽음 상태로 생성된다", out_fixed)
    badge_a_fixed = _partner_unread_badge(out_fixed["pidA"])
    chk(badge_a_fixed == 1,
        "★★★★ 포털 배지(실제 HTTP): 고친 코드에서는 A의 미읽음 배지가 여전히 1이다",
        badge_a_fixed)

    same_fixed = _run_same_recipient_scenario(A.notify)
    chk(len(same_fixed) == 2 and same_fixed[0] is not None and same_fixed[1] is None,
        "회귀없음: 같은 수신자에게 반복되면 여전히 최신 한 건만 안읽음으로 남는다"
        "(중복접기 기능 자체는 유지)", same_fixed)

    # ══════════════════════════════════════════════════════════
    print("\n[4] 되돌리기-증명 — A.notify 속성만 잠깐 옛 함수로 치환(실제 파일 미변경)")
    # ──────────────────────────────────────────────────────────
    assert CURRENT_FUNC and OLD_SQL_CALL in ORIGINAL_FUNC, "되돌릴 사본을 준비하지 못했다"
    _ns = dict(vars(A))
    exec(compile(ORIGINAL_FUNC, "<round634_reverted_notify>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출한 사본, 디스크 미기록
    reverted_notify = _ns["notify"]

    _orig_notify = A.notify
    A.notify = reverted_notify
    try:
        out_reverted = _run_scenario(A.notify)
        badge_a_reverted = _partner_unread_badge(out_reverted["pidA"])
    finally:
        A.notify = _orig_notify

    chk(out_reverted["a_wrongly_read"] is True,
        "★★★★★ 옛 코드(되돌림): 재배정 후 새 알림을 보내면 옛 수신자(A)의 안읽음이 "
        "본 적도 없는데 '읽음'으로 찍힌다 — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
        out_reverted)
    chk(badge_a_reverted == 0,
        "★★★★★ 옛 코드(되돌림): 포털 배지(실제 HTTP)에서도 A의 미읽음이 부당하게 0으로 "
        "떨어진다 — 사용자가 실제로 보는 값에도 결함이 그대로 드러난다", badge_a_reverted)

    print("\n[5] 원복 확인 — 되돌리기 이후 다시 고친 동작이 나오는가(바꿔치기가 안 샜다)")
    chk(A.notify is _orig_notify, "  A.notify가 원래 함수객체로 복원됐다")
    out_after = _run_scenario(A.notify)
    chk(out_after["a_wrongly_read"] is False,
        "★★★★ 원복 후에는 다시 옛 수신자의 안읽음이 보호된다(바꿔치기가 안 샜다)", out_after)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[3]~[5] 실행/되돌림-증명", f"{type(e).__name__}: {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC_BEFORE,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(A.notify 속성 임시치환만 사용 — 디스크에 되돌린 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
