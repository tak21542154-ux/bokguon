# -*- coding: utf-8 -*-
"""스캔 690라운드 회귀(직접조사, 하위위임 없음) — 발송 대기함(GET /api/outbox)이
   notifications.is_demo 를 전혀 안 걸러, 데모 알림이 목록·집계에 그대로 섞이던 결함.

  조사각도 — round88(api_calendar)·round254(sweep_auctions)가 "형제 집계는 전부
  COALESCE(is_demo,0)=0 을 거는데 이 자리만 빠졌다"는 같은 결함 클래스를 이미
  두 번 잡은 전례가 있어, app.py 전체 conn.execute() 900건을 is_demo 가진
  9개 자식표(auctions·bids·defects·dispatches·field_agreements·happy_calls·
  notifications·schedule_events·settlements) 기준으로 정적 스캔했다(변수 조립
  SQL은 함수 전체 텍스트에 "is_demo" 존재 여부로 재확인해 오탐 제거 —
  _compute_ops_kpi·api_settlements_summary·api_defects_summary·sweep_auctions
  는 전부 W/WD/WC/live/_live 같은 변수로 이미 조건을 조립하고 있어 클린이었다).

  실측(운영 DB, 읽기전용, 쓰기 전혀 없음) — api_outbox() 만 함수 전체에 is_demo
  가 한 번도 안 나온다. is_demo=1 로 **정상 마킹된** 알림이 67건 있고, 그중
  7건이 지금 이 순간 status='발송대기' 라 이 화면 기본 뷰(전체 27건)에
  실제로 섞여 노출 중이었다(id 1·2·3 등 — db.py 시드 알림, case_id는
  NULL 이지만 _backfill 이 아니라 db.py 자신이 애초에 is_demo=1 로 마킹해
  둔 것으로 실측 확인). notify() 자신의 case_id→is_demo 캐스케이드는
  round525/526 이 이미 실시간 INSERT 경로에서 고쳐 놨고(dispatch.py의
  open_dispatch·open_agreement, notify() 의 case_id 재조회) 2026-08-05
  17:23:32 이후로는 case_id 없는 알림이 단 한 건도 새로 생기지 않았다
  (message 안의 사건번호 패턴으로 역추적 실측) — 즉 그 경로는 이미 클린.
  이번 결함은 **캐스케이드가 아니라 "캐스케이드된 표식을 읽는 쪽"** 이
  빠진, round254 와 정확히 같은 방향(표식은 있는데 조회가 안 본다)의
  새 발생지점이다.

  ⚠ 별도로 확인만 하고 이 라운드에서 손대지 않은 것 — 2026-07-23~08-05
    사이에 생성된 레거시 알림 223건(case_id NULL, 메시지에 사건번호 포함)
    중 8건이 실제 데모 사건(26-80037 등)과 일치하는데 is_demo=0 으로 남아
    있다. 이건 이미 재발하지 않는(8/5 이후 0건) 과거 데이터 오염이라
    코드 결함이 아니라 데이터 정정 대상이고, 운영 DB UPDATE 는 사용자
    승인 없이 하지 않는다(절대 규칙) — 이번 수정(코드 필터 추가)은 이
    8건을 가리지 못한다(is_demo 자체가 틀리게 저장돼 있으므로) — 이
    8건의 목록은 사용자 보고에 별도로 남긴다.

  고침 — api_outbox() 의 목록 쿼리(where)와 집계 쿼리(cw) 양쪽 초기값을
  "1=1" 에서 "COALESCE(is_demo,0)=0" 으로 바꿨다. 새 헬퍼·새 컬럼·새
  정책 없음 — 형제들이 이미 쓰는 것과 완전히 같은 조건문 재사용.

  [1] 소스 확인 — where·cw 두 초기값 모두 is_demo 조건으로 바뀌었고,
      다른 함수(8377행의 where)는 안 건드렸음을 확인.
  [2] 핵심 재현 — 격리 DB에 정상 사건 알림 1건 + 데모 사건 알림 1건을
      만들어 실제 뷰 함수(test_request_context)를 호출, 목록에 정상만
      나오고 집계(stat)에도 데모가 안 섞임을 실측.
  [3] 종단 — status=전체 조회, days=0(기간 무시) 조회 양쪽에서도 데모가
      계속 안 보임을 확인(필터 우회 경로 없음).
  [4] 되돌림-증명 — 고친 where/cw 초기값만 "1=1"로 되돌린 함수 사본을
      인메모리로 만들어(실제 파일 무수정) 같은 시나리오를 돌리면 데모가
      실제로 새어 나옴을 재현(이 테스트가 진짜로 결함을 잡을 능력이
      있음을 증명).
  [5] 인접 안전성 — status 필터·검색어(q) 필터·기간(days) 필터는 회귀
      없이 그대로 작동.

  쓰는 법:
      python test_scan_round690_fixes.py
"""
import io
import os
import re
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
    end = src.find("\n@app.", start + 1)
    return src[start:end if end != -1 else None]


print("=" * 72)
print("  스캔 690라운드 회귀 — 발송 대기함(api_outbox) 데모 알림 미차단")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ══════════════════════════════════════════════════════════════
APP_SRC = io.open(os.path.join(HERE, "app.py"), encoding="utf-8").read()

try:
    fn_body = _py_fn_body(APP_SRC, "api_outbox")
    chk('where, p = ["COALESCE(is_demo,0)=0"], []' in fn_body,
        "★★★★★ 목록 쿼리(where) 초기값이 is_demo 조건으로 바뀌었다")
    chk('cw, cp = (["COALESCE(is_demo,0)=0"], [])' in fn_body,
        "★★★★★ 집계 쿼리(cw) 초기값도 is_demo 조건으로 바뀌었다")
    chk('where, p = ["1=1"], []' not in fn_body,
        "★★★ 예전 무조건 통과값(1=1)은 이 함수에서 사라졌다")
    chk('cw, cp = (["1=1"], [])' not in fn_body,
        "★★★ 집계 쪽 예전 무조건 통과값도 사라졌다")
    # 다른 함수(api_leads 계열, 8377행)의 where 초기값은 이 라운드의
    # 수정 대상이 아니다 — 잘못 건드리지 않았는지 확인.
    other = _py_fn_body(APP_SRC, "api_leads") if "\ndef api_leads(" in APP_SRC else ""
    chk(APP_SRC.count('where, p = ["1=1"], []') == 1,
        "STEP 무관한 다른 함수의 where 초기값(1개)은 손대지 않았다",
        APP_SRC.count('where, p = ["1=1"], []'))
    chk("status=?" in fn_body and 'where.append("status=?")' in fn_body,
        "STEP status 필터 로직은 그대로 유지된다(회귀 없음)")
    chk('julianday(created_at) <= ?' in fn_body,
        "STEP 기간(days) 필터 로직도 그대로 유지된다(회귀 없음)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "[1] 소스 확인", f"{type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[5] 실제 Flask 앱 실행")
# ══════════════════════════════════════════════════════════════
_tmpdir = tempfile.mkdtemp(prefix="round690_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    def _call_outbox(qs=""):
        """관리자 세션이 실린 test_request_context 안에서 뷰 함수를 직접 호출한다
        (round688의 _call 과 같은 기법)."""
        path = "/api/outbox" + (("?" + qs) if qs else "")
        with A.app.test_request_context(path, method="GET"):
            from flask import session as _s
            _s["admin"] = "r690admin"; _s["admin_name"] = "검증"; _s["admin_role"] = "최고관리자"
            resp = A.api_outbox()
        if isinstance(resp, tuple):
            return resp[1], resp[0].get_json()
        return 200, resp.get_json()

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('r690admin','x','검증','최고관리자')")
    #  정상 사건 1건 + 데모 사건 1건, 각각 발송대기 알림 1건씩.
    conn0.execute(
        "INSERT INTO cases(case_no,category,region,address,status,insurer,insurer_id,is_demo,created_at) "
        "VALUES('R690-REAL','가드레일','서울','테스트로 1','접수','테스트보험',1,0,?)", (DB.now(),))
    conn0.execute(
        "INSERT INTO cases(case_no,category,region,address,status,insurer,insurer_id,is_demo,created_at) "
        "VALUES('R690-DEMO','가드레일','서울','테스트로 2','접수','테스트보험',1,1,?)", (DB.now(),))
    real_cid = conn0.execute("SELECT id FROM cases WHERE case_no='R690-REAL'").fetchone()["id"]
    demo_cid = conn0.execute("SELECT id FROM cases WHERE case_no='R690-DEMO'").fetchone()["id"]
    conn0.commit()

    with A.app.test_request_context("/", method="GET"):
        conn1 = DB.get_db()
        A.notify(conn1, "R690테스트", "알림톡", "협력사", "R690-REAL 실사건 알림",
                 audience_type="admin", case_id=real_cid)
        A.notify(conn1, "R690테스트", "알림톡", "협력사", "R690-DEMO 데모사건 알림",
                 audience_type="admin", case_id=demo_cid)
        conn1.commit(); conn1.close()

    # 방금 넣은 두 알림의 is_demo가 notify() 자신에 의해 정확히 갈렸는지 사전 확인
    # (이 테스트 자신의 전제 — 여기가 틀리면 아래 결과는 의미가 없다).
    chk_conn = DB.get_db()
    real_row = chk_conn.execute(
        "SELECT is_demo FROM notifications WHERE message='R690-REAL 실사건 알림'").fetchone()
    demo_row = chk_conn.execute(
        "SELECT is_demo FROM notifications WHERE message='R690-DEMO 데모사건 알림'").fetchone()
    chk_conn.close()
    chk(real_row and real_row["is_demo"] == 0,
        "STEP 사전조건 — 실사건 알림은 notify() 가 is_demo=0으로 저장했다")
    chk(demo_row and demo_row["is_demo"] == 1,
        "STEP 사전조건 — 데모사건 알림은 notify() 가 is_demo=1로 저장했다")

    # ── [2] 핵심 재현 — 기본 뷰(발송대기)에서 데모가 안 보이는가 ──
    code, body = _call_outbox()
    msgs = [it["message"] for it in (body or {}).get("items", [])]
    chk(code == 200, "STEP api_outbox 기본 호출이 200이다", code)
    chk("R690-REAL 실사건 알림" in msgs,
        "★★★★★ 실사건 알림은 발송대기 목록에 나온다(과잉차단 아님)")
    chk("R690-DEMO 데모사건 알림" not in msgs,
        "★★★★★ 데모사건 알림은 발송대기 목록에서 빠진다(핵심 수정 효과)")

    # ── [3] 종단 — 집계(counts)에도 데모가 안 섞이는가 ──
    stat = (body or {}).get("counts", {}) or {}
    total_wait = stat.get("발송대기", 0)
    real_only_count = chk_conn2 = None
    chk_conn2 = DB.get_db()
    real_wait_n = chk_conn2.execute(
        "SELECT COUNT(*) n FROM notifications WHERE status='발송대기' AND COALESCE(is_demo,0)=0"
    ).fetchone()["n"]
    chk_conn2.close()
    chk(total_wait == real_wait_n,
        "★★★★ 집계(stat.발송대기)가 실사건 알림 수와 정확히 같다(데모 안 섞임)",
        f"stat={total_wait} real_only={real_wait_n}")

    # ── [3] 종단 계속 — status=전체, days=0(기간 무시)에서도 데모가 안 보이는가 ──
    code2, body2 = _call_outbox("status=전체&days=0")
    msgs2 = [it["message"] for it in (body2 or {}).get("items", [])]
    chk("R690-REAL 실사건 알림" in msgs2,
        "STEP status=전체&days=0 조회에서도 실사건 알림은 보인다")
    chk("R690-DEMO 데모사건 알림" not in msgs2,
        "★★★★ status=전체&days=0(필터 최대 개방)로도 데모 알림은 여전히 안 보인다"
        "(필터 우회 경로 없음)")

    # ── [5] 인접 안전성 — status/검색어 필터가 여전히 정상 작동 ──
    code3, body3 = _call_outbox("status=발송대기&q=R690-REAL")
    msgs3 = [it["message"] for it in (body3 or {}).get("items", [])]
    chk(msgs3 == ["R690-REAL 실사건 알림"],
        "STEP 검색어(q) 필터는 회귀 없이 그대로 동작한다", msgs3)

    # ══════════════════════════════════════════════════════════
    print("\n[4] 되돌리기-증명 — 실제 파일은 절대 건드리지 않는다")
    # ══════════════════════════════════════════════════════════
    # api_outbox() 소스를 파일에서 그대로 잘라내, where/cw 초기값만
    # 옛 값("1=1")으로 되돌린 사본을 인메모리 exec 로 만든다.
    OLD_FN_SRC = fn_body
    reverted_src = OLD_FN_SRC.replace(
        'where, p = ["COALESCE(is_demo,0)=0"], []', 'where, p = ["1=1"], []'
    ).replace(
        'cw, cp = (["COALESCE(is_demo,0)=0"], [])', 'cw, cp = (["1=1"], [])'
    )
    chk(reverted_src != OLD_FN_SRC,
        "STEP 되돌림 사본이 실제로 옛 값을 담고 있다(치환이 걸렸다)")

    ns = dict(vars(A))  # app 모듈의 전역 네임스페이스를 그대로 빌린다(round680 관례)
    exec(compile(reverted_src, "<api_outbox_reverted>", "exec"), ns)  # noqa: S102
    reverted_outbox = ns["api_outbox"]

    with A.app.test_request_context("/api/outbox", method="GET"):
        from flask import session as _s
        _s["admin"] = "r690admin"; _s["admin_name"] = "검증"; _s["admin_role"] = "최고관리자"
        rr = reverted_outbox()
    rcode, rbody = (rr[1], rr[0].get_json()) if isinstance(rr, tuple) else (200, rr.get_json())
    rmsgs = [it["message"] for it in (rbody or {}).get("items", [])]
    chk("R690-DEMO 데모사건 알림" in rmsgs,
        "★★★★★ 되돌린(옛) 코드로는 데모 알림이 실제로 목록에 샌다"
        "(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명)")

    # 원본 파일이 이 과정에서 전혀 안 바뀌었음을 마지막에 재확인.
    APP_SRC_AFTER = io.open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
    chk(APP_SRC_AFTER == APP_SRC,
        "STEP 되돌리기-증명 이후에도 실제 app.py 파일은 바이트 단위로 무변경이다")

except Exception as e:                                              # noqa: BLE001
    import traceback
    traceback.print_exc()
    chk(False, "[2]~[5] 실제 Flask 앱 실행", f"{type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("실패 항목:")
    for name, detail in FAIL:
        print(f"  · {name}")
        if detail:
            print(f"    {detail}")
sys.exit(1 if FAIL else 0)
