# -*- coding: utf-8 -*-
"""스캔 527라운드 회귀 — 1차합의 승인(api_insurer_field_agreement_decision,
app.py:18134)에서 도급 적법성 판정(CP.record_gate) 기록이 실패해도
운영팀에게 전혀 알려지지 않던 결함.

직접 조사(하위위임 없음) — 지시받은 후보 ①(도급 적법성 검사 완전성)을
따라, 담당업체가 확정되는 다섯 자리(경매·보험사/경매·관리자/변경견적수락/
전체재경매/1차합의)에서 CP.record_gate() 호출이 전부 실제로 있는지부터
대조했다(app.py 전수 grep). 다섯 곳 모두 이미 호출은 있었다 — round57·
round521·round522 등이 이미 "형제 몇 곳엔 있는데 여기만 없다"류 결함을
전부 잡아 놓았다. 그래서 "호출이 있는가"가 아니라 "그 호출이 실패하면
어떻게 되는가"로 각도를 옮겼다.

형제 넷(api_insurer_award 4528행·api_co_decision 10727행·
api_co_close_full 10867행·api_case_award 11448행)은 전부 함수 시작에서
conn.execute("BEGIN IMMEDIATE") 로 트랜잭션을 열고, _gate_alert(...,
CP.record_gate(...)) 를 그 **안**에서 예외처리 없이 그대로 부른다 —
안에서 예외가 나면 담당업체 배정 UPDATE 자체가 아직 커밋 전이라 함께
롤백된다(그중 api_case_award 는 명시적으로 `except Exception:
conn.rollback(); raise`, 나머지 셋은 try/except 자체가 아예 없어 예외가
그대로 새어나가 app.py:1236 의 전역 오류핸들러가 _cleanup_conns(rollback=
True) 로 되돌린다). 즉 "계약은 성립했는데 소명 기록만 없다"는 상태 자체가
이 넷에서는 구조적으로 나올 수 없다 — 기록이 실패하면 계약도 함께
없었던 일이 된다.

1차합의 경로(api_insurer_field_agreement_decision, 18134행)만 다르다.
사건 배정(status='시공중', partner_id 확정)은 DP.settle_agreement()
안에서 일어나는데, 그 함수는 **자기 트랜잭션을 스스로 커밋한다**
(dispatch.py:1188 BEGIN IMMEDIATE ~ 1334 conn.commit()) — app.py 쪽은
이 함수를 부르기 전에 별도로 BEGIN IMMEDIATE 를 걸지 않는다(그랬다간
sqlite3 가 "트랜잭션 안에서 트랜잭션 시작 불가" 로 즉시 깨진다). 그 뒤에
_record_outcome·_gate_alert(CP.record_gate(...)) 를 부르는데, 이 호출들은
**settle_agreement() 가 이미 커밋한 뒤**에 실행되고, 게다가
`except Exception: app.logger.exception(...)` 로 감싸여 있다 — 여기서
예외가 나도 이미 성립된 계약은 되돌릴 방법이 없고(되돌릴 대상 자체가
없다, 이미 디스크에 있다), 그 except 는 서버 로그(누구도 상시로 보지
않는다)에만 흔적을 남기고 끝난다. record_gate() 자신의 독스트링
(compliance.py:451)이 이미 "판정을 막는 함수가 아니다"라고 명시하므로
계약을 막지 않는 것 자체는 맞는 설계다 — 문제는 "막지 않되 반드시
알려야 한다"는 이 파일의 다른 원칙(_gate_alert() 의 _log_failed 분기,
3898행, record_gate 자신의 INSERT 가 sqlite3.Error 로 실패했을 때는
이미 운영팀 알림을 준다)이 **그 알림 함수 자신이 호출되기도 전에 예외가
나는 경우**(예: gate()/check_direct_contract() 안의 프로그래밍 버그처럼
sqlite3.Error 가 아닌 예외)에는 적용되지 않는다는 점이다 — 정확히
그런 경우에만 걸리는 이 except 블록이 조용히 로그만 남기고 넘어간다.

영향 — 1차합의로 사건이 배정되는 순간(이 경로는 app.py 18209행 자신의
주석대로 "소액 직접 도급의 본류"라 실사용 빈도가 형제 넷보다 높다)
CP.record_gate() 가 어떤 이유로든(sqlite3.Error 가 아닌 예외 — gate()
내부 버그·related_sum() 예외 등) 실패하면: 계약(시공중 배정)은 정상
성립하고 보험사에게는 200 ok:True 가 돌아가는데, contract_gate_log 에는
그 확정의 소명 스냅샷이 영원히 안 남고, 그 사실을 아무도 모른다(서버
로그 파일 한 줄뿐). 나중에 "왜 등록 없이 이 금액을 직접 도급했는지"를
증명해야 하는 순간(경미한 건설공사 예외의 법적 근거) 그 근거가 아예
없는 상태로 남는다 — 그런데 화면(어드민 콘솔) 어디에도 "이 사건은
소명 기록이 없다"는 표시가 없어 사후에도 발견될 방법이 없었다.

고침 — api_insurer_field_agreement_decision() 의 그 except 블록 안에,
_gate_alert() 가 record_gate 자신의 실패(_log_failed)에 이미 주는 것과
같은 무게의 운영팀 알림(notify(ntype="도급판정", audience_type="admin"))
과 활동로그(DB.log)를 추가했다(기존 함수만 재사용, 새 헬퍼·새 상수
없음). 이 알림 자체가 실패해도 이미 성립된 승인을 실패로 되돌리지
않도록 안쪽에 자기만의 try/except 를 한 겹 더 둔다(이 함수 바깥쪽에도
이미 이 블록을 감싸는 except 가 있으므로, 이중 방어 없이 두면 알림
실패가 그대로 500 으로 샐 수 있었다).

[1] 소스 확인 — 새 블록이 기존 except 안ㆍ[라운드527] 표식 아래ㆍ그
    다음 '낙찰' 알림(승인 분기의 다음 문장) 이전에 정확히 있고, 자기
    자신의 try/except 로 한 번 더 감싸져 있음을 확인. 형제 넷은
    _gate_alert 호출을 감싸는 try/except 가 전혀 없거나(3곳) 있어도
    rollback 후 재던짐(api_case_award)임을 소스에서 대조.
[2] 실행 기반 — 실제 스크래치 DB + 진짜 Flask 테스트클라이언트로 사건
    접수→출동→도착→1차합의 개시→보험사 승인까지 실제로 진행시키되,
    CP.record_gate() 를 이 세션에서만 강제로 예외를 던지게 몽키패치해
    (sqlite3.Error 가 아닌, record_gate 자신의 try/except 가 못 잡는
    종류의 실패를 재현) 승인 자체는 여전히 200/성공하고 사건도 실제로
    '시공중'으로 배정되며 contract_gate_log 는 0건인 채로, notifications
    에 운영팀 대상 '도급판정' 알림이 실제로 1건 쌓이는지 확인.
[3] 되돌림-증명 — app.py 파일 자체는 건드리지 않는다(이 저장소는 git 이
    없고 동시에 다른 세션이 app.py 를 건드릴 수 있는 환경이라 round520
    이후 전 라운드와 같은 원칙). 대신 이 라운드가 새로 부르기 시작한
    바로 그 notify() 호출 한 줄만 런타임에 무력화한다 — A.notify 를
    감싸, ntype='도급판정' 이면서 이 라운드의 문구("1차합의 승인 후
    도급 적법성 판정 기록이 저장되지 않았습니다")를 담은 호출만 조용히
    삼키고 나머지 호출은 전부 진짜 notify 로 그대로 넘긴다 — 이것이
    "이 줄이 없던 이전 상태"와 동일한 효과를 낸다. 같은 시나리오를 새
    사건으로 재실행해 승인 자체(구조)는 그대로 성공하면서 '도급판정'
    알림만 0건으로 돌아가는지 확인(=이 회귀가 실제로 결함을 잡아낼
    능력이 있음을 증명), 그 뒤 A.notify 를 원래 함수로 복원하고 세
    번째 사건으로 다시 1건이 쌓임까지 확인.
[4] 형제 대조 — 같은 CP.record_gate 결함 주입을 형제 경로
    api_insurer_award(보험사 경매 낙찰)에도 그대로 적용해, 그 경로는
    승인 자체가 500 으로 실패하고 사건이 롤백되어 '입찰중'·업체
    미배정 그대로 남는 것을 실측 확인 — "계약은 성립했는데 기록만
    없다"는 상태가 1차합의에서만 가능하고 형제 경로는 구조적으로 그
    상태에 도달할 수 없음을 대조로 증명한다.

    python test_scan_round527_fixes.py
"""
import io
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


print("=" * 72)
print("  스캔 527라운드 회귀 — 1차합의 도급판정 기록 실패가 조용히 삼켜짐")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ══════════════════════════════════════════════════════════════
APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

FN = "api_insurer_field_agreement_decision"
fn_body = _py_fn_body(APP_SRC, FN)

OLD_EXCEPT = ('except Exception:\n'
              '                app.logger.exception("합의 승인 후 실적·판정 기록 실패 case=%s", cid)')
old_idx = fn_body.find(OLD_EXCEPT)
chk(old_idx != -1, "기존 except 블록(라운드527 이전 코드)이 그대로 있다(회귀 없음)")

chk("[라운드527]" in fn_body, "★★★ 함수 본문 안에 [라운드527] 표식이 있다")
chk(APP_SRC.count("[라운드527]") == 1, "전체 소스에 [라운드527] 표식이 정확히 1번뿐(중복 삽입 아님)")

mark_idx = fn_body.find("[라운드527]")
notify_idx = fn_body.find('notify(conn, "도급판정", "웹", "운영팀",')
dblog_idx = fn_body.find('DB.log(conn, "시스템", "도급판정 기록 실패"')
next_happy_notify_idx = fn_body.find('notify(conn, "낙찰", "알림톡", a.get("partner_name") or "시행사",')

chk(-1 < old_idx < mark_idx < notify_idx < dblog_idx < next_happy_notify_idx,
    "★★★★★ 새 블록이 옛 except 다음ㆍ[라운드527] 표식 다음ㆍ그다음 '낙찰' 알림"
    "(승인 분기의 다음 문장) 이전, 정확한 위치에 있다",
    (old_idx, mark_idx, notify_idx, dblog_idx, next_happy_notify_idx))

new_block = fn_body[old_idx:next_happy_notify_idx] if -1 < old_idx < next_happy_notify_idx else ""
chk(new_block.count("except Exception:") == 2,
    "★★★ 새 블록은 바깥 except(기존, 승인을 막지 않음) + 안쪽 except(신설, "
    "알림 실패가 또 새지 않게) 두 겹으로 감싸져 있다",
    new_block.count("except Exception:") if new_block else "블록을 못 뽑음")
chk("도급 적법성 판정 기록이" in new_block and "1차합의 승인 후" in new_block,
    "새 알림 문구에 '1차합의 승인 후 ... 판정 기록이' 가 실제로 담겨 있다")

# ── 형제 비교(순수 소스) ────────────────────────────────────────
for name in ("api_insurer_award", "api_co_decision", "api_co_close_full"):
    b = _py_fn_body(APP_SRC, name)
    chk(b.count("except") == 0,
        f"형제 경로 {name}() 는 try/except 가 전혀 없다 — CP.record_gate 가 예외를 "
        f"던지면 이 함수 전체(아직 커밋 전인 BEGIN IMMEDIATE 트랜잭션)가 그대로 "
        f"새어나가 전역 오류핸들러(1236행)가 롤백한다. 1차합의처럼 '이미 커밋된 "
        f"뒤라 못 되돌리는' 상황 자체가 이 셋에는 구조적으로 없다",
        b.count("except"))

b_admin = _py_fn_body(APP_SRC, "api_case_award")
chk("except Exception:\n        conn.rollback()\n        raise" in b_admin,
    "형제 경로 api_case_award() 는 예외 시 rollback 후 다시 던진다"
    "(확정 자체가 통째로 취소되어 되돌아간다)")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[4] 실행 기반 — 실제 Flask 앱 + 스크래치 DB")
# ══════════════════════════════════════════════════════════════
_tmpdir = tempfile.mkdtemp(prefix="round527_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r527-csrf"


def _admin_client(A):
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "admin"
        sess["admin_name"] = "검증"
        sess["admin_role"] = "최고관리자"
        sess["_csrf"] = CSRF
    return c


def _insurer_client(A, iid, name):
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["insurer_id"] = iid
        sess["insurer_name"] = name
        sess["_csrf"] = CSRF
    return c


def _settle_via_field_agreement(A, DP, DB, iid, case_no, partner_name):
    """사건접수→출동→도착→1차합의개시까지 실제로 진행시키고, 보험사 승인
    엔드포인트를 호출해 그 응답과 사건 최종 상태를 돌려준다."""
    conn = DB.get_db()
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,lat,lng) "
        "VALUES(?,'시행사','활성',37.5,127.0)", (partner_name,)).lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,lat,lng) "
        "VALUES(?,'접수','가드레일','서울',?,37.5,127.0)", (case_no, iid)).lastrowid
    conn.commit()

    did, _called, _sent = DP.open_dispatch(conn, cid)
    conn.commit()
    ok_a, _msg_a, did2 = DP.assign_dispatch(conn, cid, pid, "테스트 직접배정")
    conn.commit()
    use_did = did2 if ok_a else did
    DP.claim(conn, use_did, pid, partner_name)
    conn.commit()
    ok_r, msg_r = DP.arrive(conn, use_did, pid, photo_count=3, field_estimate=1000000)
    conn.commit()
    if not ok_r:
        raise RuntimeError(f"arrive 준비 실패: {msg_r}")
    conn.close()

    admin_c = _admin_client(A)
    r_fa = admin_c.post(f"/api/cases/{cid}/field-agreement", json={},
                         headers={"X-CSRF-Token": CSRF})
    if r_fa.status_code != 200:
        raise RuntimeError(f"1차합의 개시 실패: {r_fa.status_code} {r_fa.get_json()}")

    insurer_c = _insurer_client(A, iid, "R527보험")
    r_decide = insurer_c.post(f"/api/insurer/cases/{cid}/field-agreement/decision",
                               json={"approve": True},
                               headers={"X-CSRF-Token": CSRF})
    return cid, pid, r_decide


try:
    import db as DB
    DB.init_db()
    import dispatch as DP
    import compliance as CP
    import app as A

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('admin','x','검증','최고관리자')")
    iid = conn0.execute(
        "INSERT INTO insurers(name,status) VALUES('R527보험','활성')").lastrowid
    conn0.commit()
    conn0.close()

    _real_record_gate = CP.record_gate
    _real_notify = A.notify

    def _broken_record_gate(conn, case_id, route, actor, amount=None, override_reason=None):
        #  sqlite3.Error 가 아닌 예외 — record_gate 자신의 try/except(compliance.py:486,
        #  sqlite3.Error 만 잡음)가 못 잡는 종류의 실패(예: gate() 내부 버그)를 재현한다.
        raise RuntimeError("simulated gate bug (round527 test)")

    CP.record_gate = _broken_record_gate

    # ── [2] 새 코드 — 기록이 실패해도 승인은 성공하고, 운영팀 알림이 뜬다 ──
    print("\n[2] 실행 — 도급판정 기록 실패 시에도 승인은 성공하고 운영팀 알림이 남는다")
    cid_a, pid_a, r_decide_a = _settle_via_field_agreement(
        A, DP, DB, iid, "26-527001", "R527업체A")

    chk(r_decide_a.status_code == 200 and (r_decide_a.get_json() or {}).get("ok") is True,
        "★★★★★ CP.record_gate 가 깨져도 1차합의 승인 자체는 200/성공한다"
        "(record_gate 는 '막는 함수가 아니다' — 회귀 없음)", r_decide_a.get_json())

    conn1 = DB.get_db()
    case_a = conn1.execute(
        "SELECT status, partner_name FROM cases WHERE id=?", (cid_a,)).fetchone()
    gate_a_n = conn1.execute(
        "SELECT COUNT(*) FROM contract_gate_log WHERE case_id=?", (cid_a,)).fetchone()[0]
    admin_notify_a = conn1.execute(
        "SELECT message FROM notifications WHERE case_id=? AND ntype='도급판정' "
        "  AND audience_type='admin'", (cid_a,)).fetchall()
    actlog_a = conn1.execute(
        "SELECT detail FROM activity_log WHERE action='도급판정 기록 실패' "
        "  AND detail LIKE ?", (f"%26-527001%",)).fetchall()
    conn1.close()

    chk(case_a["status"] == "시공중" and case_a["partner_name"] == "R527업체A",
        "★★★★★ 사건은 실제로 '시공중'으로 배정된다(계약은 이미 성립했다)", dict(case_a))
    chk(gate_a_n == 0,
        "  도급 적법성 판정 스냅샷(contract_gate_log)은 실제로 0건이다"
        "(record_gate 가 깨졌으니 당연 — 이 자체는 결함이 아니다)", gate_a_n)
    chk(len(admin_notify_a) == 1,
        "★★★★★ [신규] 운영팀 대상 '도급판정' 알림이 실제로 1건 쌓인다"
        "(라운드527 이전에는 0건이었다 — 아래 [3]에서 대조 증명)", len(admin_notify_a))
    chk(bool(admin_notify_a) and "26-527001" in admin_notify_a[0]["message"]
        and "1차합의" in admin_notify_a[0]["message"],
        "  알림 문구에 사건번호·'1차합의'가 실제로 담긴다",
        admin_notify_a[0]["message"] if admin_notify_a else "")
    chk(len(actlog_a) == 1, "  활동로그(activity_log)에도 '도급판정 기록 실패' 1건이 남는다",
        len(actlog_a))

    # ── [3] 되돌림-증명 — 이 라운드가 새로 부르기 시작한 알림 호출만 무력화 ──
    print("\n[3] 되돌림-증명 — 신설 알림 호출만 런타임에 무력화(app.py 파일은 안 건드림)")

    def _notify_suppress_new_call(conn, ntype, channel, target, message, **kw):
        if ntype == "도급판정" and "1차합의 승인 후 도급 적법성 판정 기록이" in (message or ""):
            return None      # 이 라운드가 새로 부르기 시작한 그 호출만 없던 일로 만든다
        return _real_notify(conn, ntype, channel, target, message, **kw)

    A.notify = _notify_suppress_new_call
    try:
        cid_b, pid_b, r_decide_b = _settle_via_field_agreement(
            A, DP, DB, iid, "26-527002", "R527업체B")

        chk(r_decide_b.status_code == 200 and (r_decide_b.get_json() or {}).get("ok") is True,
            "옛 코드(무력화)도 승인 자체는 그대로 성공한다(구조는 안 바뀐다)",
            r_decide_b.get_json())
        conn2 = DB.get_db()
        case_b = conn2.execute(
            "SELECT status FROM cases WHERE id=?", (cid_b,)).fetchone()
        admin_notify_b = conn2.execute(
            "SELECT COUNT(*) FROM notifications WHERE case_id=? AND ntype='도급판정' "
            "  AND audience_type='admin'", (cid_b,)).fetchone()[0]
        conn2.close()
        chk(case_b["status"] == "시공중", "옛 코드(무력화)도 사건 배정 자체는 그대로 된다",
            dict(case_b))
        chk(admin_notify_b == 0,
            "★★★★★ 옛 코드(무력화)는 운영팀 알림이 0건이다 — 이 회귀가 실제로 "
            "결함(조용한 실패)을 잡아낼 능력이 있음을 증명", admin_notify_b)
    finally:
        A.notify = _real_notify

    # ── [3-복원확인] 세 번째 사건으로 다시 1건이 쌓이는지 재확인 ──
    cid_c, pid_c, r_decide_c = _settle_via_field_agreement(
        A, DP, DB, iid, "26-527003", "R527업체C")
    conn2b = DB.get_db()
    admin_notify_c = conn2b.execute(
        "SELECT COUNT(*) FROM notifications WHERE case_id=? AND ntype='도급판정' "
        "  AND audience_type='admin'", (cid_c,)).fetchone()[0]
    conn2b.close()
    chk(r_decide_c.status_code == 200 and admin_notify_c == 1,
        "★★★★★ A.notify 복원 후 세 번째 사건은 다시 알림 1건이 쌓인다"
        "(방금 전 0건이 진짜 무력화 때문이었지 다른 상태 오염이 아니었음을 확인)",
        (r_decide_c.status_code, admin_notify_c))

    # ── [4] 형제 대조 — 경매(보험사) 낙찰은 같은 결함 주입에도 롤백된다 ──
    print("\n[4] 형제 대조 — api_insurer_award(보험사 경매 낙찰)는 확정 자체가 롤백된다")
    conn3 = DB.get_db()
    pid_d = conn3.execute(
        "INSERT INTO partners(name,partner_type,status,lat,lng) "
        "VALUES('R527경매업체','시행사','활성',37.5,127.0)").lastrowid
    cid_d = conn3.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,lat,lng) "
        "VALUES('26-527004','입찰중','가드레일','서울',?,37.5,127.0)", (iid,)).lastrowid
    aid_d = conn3.execute(
        "INSERT INTO auctions(case_id,status,deadline,created_at,low_price,bid_count) "
        "VALUES(?,'진행',?,?,0,1)", (cid_d, "2099-01-01 00:00:00", DB.now())).lastrowid
    bid_d = conn3.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,?,?,?)", (aid_d, pid_d, "R527경매업체", 1000000, 5, DB.now())).lastrowid
    conn3.commit()
    conn3.close()

    insurer_c2 = _insurer_client(A, iid, "R527보험")
    r_award = insurer_c2.post(f"/api/insurer/cases/{cid_d}/award",
                               json={"bid_id": bid_d},
                               headers={"X-CSRF-Token": CSRF})
    chk(r_award.status_code == 500,
        "★★★★★ 형제 경로(경매)는 같은 CP.record_gate 결함 주입 시 500 으로 실패한다"
        "(1차합의처럼 '기록만 없이 200'이 아니다)", r_award.status_code)

    conn4 = DB.get_db()
    case_d = conn4.execute(
        "SELECT status, partner_id FROM cases WHERE id=?", (cid_d,)).fetchone()
    gate_d_n = conn4.execute(
        "SELECT COUNT(*) FROM contract_gate_log WHERE case_id=?", (cid_d,)).fetchone()[0]
    conn4.close()
    chk(case_d["status"] == "입찰중" and case_d["partner_id"] is None,
        "★★★★★ 형제 경로는 롤백되어 사건이 여전히 '입찰중'·업체 미배정 그대로다 — "
        "'계약은 성립했는데 기록만 없다'는 상태가 이 경로에는 구조적으로 없음을 실측 증명",
        dict(case_d))
    chk(gate_d_n == 0, "  (참고) 롤백됐으니 도급판정 기록도 0건 — 계약 자체가 없다",
        gate_d_n)

    CP.record_gate = _real_record_gate

except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]~[4] 실행/되돌림-증명/형제 대조", f"{type(e).__name__}: {e}")
    try:
        import compliance as _CP
        if "_real_record_gate" in dir():
            _CP.record_gate = _real_record_gate
    except Exception:
        pass
finally:
    try:
        if "_real_notify" in dir() and "A" in dir():
            A.notify = _real_notify
    except Exception:
        pass

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
