# -*- coding: utf-8 -*-
"""스캔 541라운드 회귀 — 협력사 "출동 수락"(dispatch.py::claim())이 rowcount=0을
   전부 "이미 다른 업체가 출동을 맡았습니다"로 답하던 결함. 그런데 rowcount=0은
   '지금 모집중이 아니다'는 뜻일 뿐, 실제 원인은 셋으로 갈린다 —
     ① 진짜로 다른 업체가 먼저 잡음(ST_CLAIMED) → 이 문구가 사실 그대로.
     ② 아무도 못 잡은 채 제한시간이 지나 스윕(sweep_dispatches)이 ST_FAILED로
        마감함 → "다른 업체가 맡았다"는 거짓이다. 아무도 안 갔다.
     ③ 운영자가 직접배정(assign_dispatch, supersede)으로 이 수배를 걷어가
        ST_CANCELED로 닫음 → 역시 "다른 업체가 맡았다"는 이 상황의 진짜 이유가
        아니다(선착순 경쟁에서 진 게 아니라 운영자가 걷어간 것).

   조사 배경 — 이번 라운드 지시 각도 (1) "협력사가 이미 마감된(취소된/거절된)
   출동을 뒤늦게 수락 시도하면 문구가 정확한가"를 그대로 따라간 결과다. 직전
   두 라운드(539·540)가 다룬 "재시도가 이미 내가 성공시킨 것을 또 두드리는"
   계열(같은 업체가 같은 자원을 다시 두드림)과는 뿌리가 다르다 — 여기는
   **애초에 그 수배를 못 잡은(또는 아예 안 잡힌 채 끝난) 협력사**가 뒤늦게
   눌렀을 때 원인과 무관하게 같은 오답을 주는 문제다. claim()의 case-종료
   분기(607행 부근, "이 건은 종료돼 출동이 필요 없습니다")는 이미 '진짜 이유를
   그대로 말한다'는 원칙을 쓰고 있었는데, 그 몇 줄 아래의 CAS 실패 분기만 그
   원칙을 안 따르고 있었다 — 같은 함수 안의 형제 분기 스타일을 그대로 이식한다.

   실사용 영향 — 프론트(templates/partner_portal.html:903 dpClaim)는 서버가 준
   error 문구를 그대로 alert()한다(자기 주석: "이미 다른 업체가 맡았습니다는
   오류가 아니라 선착순의 정상 결과다" — 그런데 실제로는 시간초과·운영자
   개입일 수도 있다는 것은 그 주석도 몰랐다). 알림을 늦게 확인했거나 화면이
   잠깐 멈춰 있던 협력사는 "시간이 지났다"·"운영자가 다른 곳에 맡겼다"를
   알아야 다음 행동(대기/문의)을 정할 수 있는데, 지금은 전부 "남이 이미
   맡았다"로 뭉뚱그려져 원인을 알 길이 없다.

   고침 — 새 정책·새 헬퍼 없이, 같은 함수(claim) 안에 이미 있는 스타일(현재
   상태를 실제로 읽어 정확한 사유를 말한다)을 CAS 실패 분기에도 적용했다.
   dispatch.py::claim() 안에서 BEGIN IMMEDIATE 직후 읽은 d["status"](이
   트랜잭션이 쥔 RESERVED 락 때문에 이후로도 바뀔 수 없다)를 CAS 실패 시
   재사용해 ST_FAILED·ST_CANCELED 두 상태만 갈라 정확한 문구를 준다.
   ST_ARRIVED·ST_CLAIMED(다른 업체)는 "남이 맡았다"가 사실 그대로이므로
   기존 문구를 그대로 둔다(회귀 없음) — dispatch.py:623-639.

   dispatch.py는 app.py가 import하는 모듈이다(app.py 자신에 정의된 함수는
   손대지 않았다) — app.py의 유일한 호출부(api_partner_dispatch_claim,
   app.py:17892)는 ok/msg를 그대로 jsonify({"error": msg})로 반환하므로
   호출 계약(반환 튜플 모양)은 전혀 안 바뀌었다. 그래도 프로세스가 이미 떠
   있다면 재시작해야 새 문구가 실제 요청에 반영된다(파이썬은 이미 임포트한
   모듈을 자동으로 다시 읽지 않는다).

   python test_scan_round541_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile

#  ⚠ 윈도 기본 콘솔은 cp949 라 em dash(—) 같은 문자를 print 하면
#    UnicodeEncodeError 로 죽는다 — 형제 테스트(round528·536·537·538·540 등)가
#    이미 쓰는 방어를 그대로 옮긴다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 541라운드 회귀 — 출동 수락(claim)이 '시간초과'·'운영자가 걷어감'도")
print("  전부 '다른 업체가 맡았다'로 오보하던 결함")
print("=" * 72)

_tmpdir = tempfile.mkdtemp(prefix="round541_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r541-csrf"
H = {"X-CSRF-Token": CSRF}
A = DB = DP = None
client = None
cid = pid_a = pid_b = None
claim_OLD = None


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ==================================================================
print("\n[0] 소스 — 고친 지점이 실제로 dispatch.py 에 있는가"
      "(동시편집 세션이 되돌렸다면 여기서부터 정직하게 실패해야 한다)")
# ------------------------------------------------------------------
_dispatch_src = None
try:
    _dispatch_src = io.open(os.path.join(HERE, "dispatch.py"), encoding="utf-8").read()
    import ast as _ast
    chk(_ast.parse(_dispatch_src) is not None, "STEP dispatch.py 전체 ast.parse 성공")
    _app_src_chk = io.open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
    chk(_ast.parse(_app_src_chk) is not None, "STEP app.py 전체 ast.parse 성공(무수정 확인용)")
    _claim_body = _py_fn_body(_dispatch_src, "claim")
    chk('d["status"] == ST_FAILED' in _claim_body,
        "★★★★★ claim() 에 ST_FAILED 분기가 있다(고치기 전엔 없었다)")
    chk('d["status"] == ST_CANCELED' in _claim_body,
        "★★★★★ claim() 에 ST_CANCELED 분기가 있다(고치기 전엔 없었다)")
    chk('"이 수배는 응답 시간이 지나 이미 마감되었습니다."' in _claim_body,
        "STEP 시간초과 전용 문구가 있다")
    chk('"이 수배는 취소되었습니다. 현장으로 가지 마세요."' in _claim_body,
        "STEP 취소 전용 문구가 있다")
    chk('"이미 다른 업체가 출동을 맡았습니다"' in _claim_body,
        "STEP 원래 문구(진짜 실패용)도 그대로 남아 있다(회귀 없음 — 삭제 아님)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드541 [0] 소스 확인", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[1] 원인 재현 — 고치기 전 claim() 을 문자열로 재구성해 실행하면"
      "(app.py·run_all_tests.py 는 절대 건드리지 않는다) 실제로 두 상태 모두")
print("    거짓 문구를 낸다")
# ------------------------------------------------------------------
try:
    import db as DB
    DB.init_db()
    import app as A
    import dispatch as DP

    #  ⚠ old_fn_src 는 지금 파일의 실제 텍스트에서 '고친 부분'만 원래 한 줄로
    #    되돌려 만든다(손으로 옛 코드를 다시 타이핑하지 않는다 — 오타 위험).
    #    두 앵커 문자열(if not cur.rowcount: ↔ 원래 fallback 문구)은 이번
    #    수정 전후 공통으로 존재하므로 이 재구성이 항상 유효하다.
    _fn_src = _py_fn_body(_dispatch_src, "claim")
    _start = _fn_src.index("if not cur.rowcount:")
    _end_marker = 'return False, "이미 다른 업체가 출동을 맡았습니다", None'
    _end = _fn_src.index(_end_marker, _start) + len(_end_marker)
    _old_block = ('if not cur.rowcount:\n'
                  '            conn.rollback()\n'
                  '            return False, "이미 다른 업체가 출동을 맡았습니다", None')
    old_fn_src = _fn_src[:_start] + _old_block + _fn_src[_end:]
    chk('d["status"] == ST_FAILED' not in old_fn_src,
        "STEP 재구성된 old_fn_src 에는 이번 수정이 없다(진짜 '이전 코드')")

    _ns = dict(vars(DP))
    exec(compile(old_fn_src, "<round541_old_claim>", "exec"), _ns)  # noqa: S102
    claim_OLD = _ns["claim"]

    conn0 = DB.get_db()
    iid = conn0.execute(
        "INSERT INTO insurers(name,status) VALUES('R541손해보험','활성')").lastrowid
    pid_a = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,phone,login_id) "
        "VALUES('R541업체A','시공사','활성','가드레일','서울','01099990201','r541pa')").lastrowid
    pid_b = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,phone,login_id) "
        "VALUES('R541업체B','시공사','활성','가드레일','서울','01099990202','r541pb')").lastrowid
    cid = conn0.execute(
        """INSERT INTO cases(case_no,insurer_id,insurer,category,region,address,
                             est_price,low_price,status,intake_type,created_at,is_demo)
           VALUES('R541-1',?,'R541손해보험','가드레일','서울','검증용 주소',0,0,
                  '접수','사진없음',?,0)""",
        (iid, DB.now())).lastrowid
    conn0.commit()
    conn0.close()
    chk(True, "STEP 스크래치 DB — 보험사 1곳·협력사 2곳·사건(접수·미배정) 준비",
        os.environ["BOKGUON_DB_PATH"])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드541 실행 준비(old_fn_src 재구성·DB.init_db·app import)",
        f"{type(e).__name__} {e}")


def _mk_dispatch(status, fail_reason=""):
    """상태가 이미 최종 확정된(모집중이 아닌) 수배 한 건 + pid_a 앞으로 온 콜 기록.

    ⚠ case 는 여전히 '접수'·미배정으로 둔다 — claim() 초반의 '사건이 이미
      끝났는가' 분기(cs 검사)가 먼저 걸려 이번에 검증하려는 CAS 실패 분기까지
      못 가는 일이 없게 하기 위해서다(딴 갈래로 새는 거짓양성 방지).
    """
    conn = DB.get_db()
    did = conn.execute(
        "INSERT INTO dispatches(case_id,round,status,fail_reason,created_at,is_demo) "
        "VALUES(?,1,?,?,?,0)", (cid, status, fail_reason, DB.now())).lastrowid
    conn.execute(
        "INSERT INTO dispatch_calls(dispatch_id,partner_id,partner_name,call_order,"
        "                           notified_at,created_at) VALUES(?,?,'',1,?,?)",
        (did, pid_a, DB.now(), DB.now()))
    conn.commit()
    conn.close()
    return did


try:
    did_failed_old = _mk_dispatch(DP.ST_FAILED, "아무도 수락하지 않음")
    conn1 = DB.get_db()
    ok, msg, due = claim_OLD(conn1, did_failed_old, pid_a, "R541업체A")
    conn1.close()
    chk((not ok) and msg == "이미 다른 업체가 출동을 맡았습니다",
        "★★★★★ [재현] 고치기 전 코드: 시간초과(ST_FAILED)로 아무도 못 간 건도 "
        "'다른 업체가 맡았다'는 거짓 문구를 낸다", (ok, msg))

    did_canceled_old = _mk_dispatch(DP.ST_CANCELED, "운영자 직접 배정으로 종료 — 테스트")
    conn2 = DB.get_db()
    ok, msg, due = claim_OLD(conn2, did_canceled_old, pid_a, "R541업체A")
    conn2.close()
    chk((not ok) and msg == "이미 다른 업체가 출동을 맡았습니다",
        "★★★★★ [재현] 고치기 전 코드: 운영자가 걷어간(ST_CANCELED) 건도 "
        "'다른 업체가 맡았다'는 거짓 문구를 낸다", (ok, msg))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드541 [1] 원인 재현(옛 코드)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[2] 실행(지금 코드, dispatch.py::claim() 직접 호출) — 두 상태 모두")
print("    정확한 사유로 갈라진다")
# ------------------------------------------------------------------
try:
    did_failed_new = _mk_dispatch(DP.ST_FAILED, "제한시간 내 미도착")
    conn3 = DB.get_db()
    ok, msg, due = DP.claim(conn3, did_failed_new, pid_a, "R541업체A")
    conn3.close()
    chk((not ok) and msg == "이 수배는 응답 시간이 지나 이미 마감되었습니다.",
        "★★★★★ 지금 코드: 시간초과 건은 '응답 시간이 지나 마감' 문구를 정확히 "
        "준다('다른 업체' 오보가 사라졌다)", (ok, msg))

    did_canceled_new = _mk_dispatch(DP.ST_CANCELED, "운영자 직접 배정으로 종료 — 테스트")
    conn4 = DB.get_db()
    ok, msg, due = DP.claim(conn4, did_canceled_new, pid_a, "R541업체A")
    conn4.close()
    chk((not ok) and msg == "이 수배는 취소되었습니다. 현장으로 가지 마세요.",
        "★★★★★ 지금 코드: 운영자가 걷어간 건은 '취소되었다' 문구를 정확히 "
        "준다('다른 업체' 오보가 사라졌다)", (ok, msg))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드541 [2] 지금 코드 직접 호출", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[3] 회귀 안전 — 진짜로 다른 업체가 먼저 잡은 경우(ST_CLAIMED)는")
print("    이번 수정 이후에도 원래 문구를 그대로 받는다(숨기지 않는다)")
# ------------------------------------------------------------------
try:
    conn5 = DB.get_db()
    did_genuine = conn5.execute(
        "INSERT INTO dispatches(case_id,round,status,claimed_partner_id,claimed_name,"
        "                       claimed_at,due_at,created_at,is_demo) "
        "VALUES(?,1,?,?,?,?,?,?,0)",
        (cid, DP.ST_CLAIMED, pid_b, "R541업체B", DB.now(), DB.now(), DB.now())).lastrowid
    for _pid, _resp in ((pid_a, None), (pid_b, "수락")):
        conn5.execute(
            "INSERT INTO dispatch_calls(dispatch_id,partner_id,partner_name,call_order,"
            "                           response,notified_at,created_at) VALUES(?,?,'',1,?,?,?)",
            (did_genuine, _pid, _resp, DB.now(), DB.now()))
    conn5.commit()
    conn5.close()

    conn6 = DB.get_db()
    ok, msg, due = DP.claim(conn6, did_genuine, pid_a, "R541업체A")
    conn6.close()
    chk((not ok) and msg == "이미 다른 업체가 출동을 맡았습니다",
        "STEP 진짜 '다른 업체가 이미 잡음' 상황은 여전히 원래 문구 그대로"
        "(이번 수정이 진짜 실패까지 숨기지 않는다 — 회귀 없음)", (ok, msg))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드541 [3] 회귀 안전(진짜 다른 업체)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[4] 실행(진짜 라우트, HTTP) — 시간초과 건을 실제 API로 눌러도")
print("    같은 정확한 문구가 그대로 화면까지 간다")
# ------------------------------------------------------------------
try:
    did_failed_http = _mk_dispatch(DP.ST_FAILED, "아무도 수락하지 않음")
    client = A.app.test_client()
    with client.session_transaction() as sess:
        sess.clear()
        sess["partner_id"] = pid_a
        sess["_csrf"] = CSRF
    r = client.post(f"/api/partner/dispatches/{did_failed_http}/claim", headers=H, json={})
    body = r.get_json() or {}
    chk(r.status_code == 409 and body.get("ok") is False,
        "STEP HTTP 409·ok:false", (r.status_code, body))
    chk(body.get("error") == "이 수배는 응답 시간이 지나 이미 마감되었습니다.",
        "★★★★★ HTTP 응답의 error 필드가 정확한 문구다(프론트 dpClaim이 이 값을 "
        "그대로 alert 한다 — partner_portal.html:910)", body)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드541 [4] 실행(HTTP)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[5] 회귀 안전 — 정상 최초 수락(모집중 상태)은 이번 수정과 무관하게")
print("    그대로 성공한다")
# ------------------------------------------------------------------
try:
    conn7 = DB.get_db()
    did_open = conn7.execute(
        "INSERT INTO dispatches(case_id,round,status,created_at,is_demo) "
        "VALUES(?,1,?,?,0)", (cid, DP.ST_OPEN, DB.now())).lastrowid
    conn7.execute(
        "INSERT INTO dispatch_calls(dispatch_id,partner_id,partner_name,call_order,"
        "                           notified_at,created_at) VALUES(?,?,'',1,?,?)",
        (did_open, pid_a, DB.now(), DB.now()))
    conn7.commit()
    conn7.close()

    conn8 = DB.get_db()
    ok, msg, due = DP.claim(conn8, did_open, pid_a, "R541업체A")
    conn8.close()
    chk(ok and due, "STEP 모집중 수배는 여전히 정상적으로 최초 수락된다(무회귀)",
        (ok, msg, due))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드541 [5] 회귀 안전(정상 최초 수락)", f"{type(e).__name__} {e}")


# ==================================================================
# 정리
# ------------------------------------------------------------------
os.environ.pop("BOKGUON_DB_PATH", None)
os.environ.pop("BOKGUON_ENV", None)
os.environ.pop("BOKGUON_SEED_DEMO", None)
shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
