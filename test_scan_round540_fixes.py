# -*- coding: utf-8 -*-
"""스캔 540라운드 회귀 — 협력사 "출동 수락"(api_partner_dispatch_claim)에서
   내가 방금 성공시킨 바로 그 수배를 같은 pid 로 다시 두드리면(더블탭·느린
   응답에 대한 프론트 재시도) DP.claim() 은 rowcount=0 이 되어 "이미 다른
   업체가 출동을 맡았습니다"를 그대로 돌려주는데, 그 '다른 업체'는 사실
   나 자신이다.

   조사 배경 — 직전 두 라운드(538·539)가 고친 출동 "직접배정"(api_dispatch_assign,
   round463) 재시도 결함과 같은 계열이다: '기존 상태를 다시 확인 안 하고
   무조건 같은 실패로 떨어뜨리는' 함수가, 재시도(=이미 내가 성공시킨 그
   대상)와 진짜 실패(=남이 이미 가져감)를 구분하지 못한다. 그 형제가 고쳐진
   것을 계기로 이번 라운드 지시 각도 (1) "같은 재시도 취약점이 다른 API에도
   있는지"를 그대로 따라가 '선착순 수락' 경로(claim, dispatch.py:580)에서
   발견했다 — assign_dispatch 가 아니라 claim 이라는 점만 다르다.

   round463 과의 차이 — 그쪽은 부작용(중복 알림톡 2회 + 거짓 취소통지 1회)
   까지 냈지만, 여기는 DP.claim() 자체가 재시도 시 DB 를 아무 것도 안
   바꾸고 실패만 돌려주므로 DB 훼손·중복발송은 없다(현재 코드는 ok=False
   라 호출부의 보험사 notify() 블록에 아예 도달하지 않는다). 대신 **문구
   자체가 거짓**이다 — 실제로는 내가 맡았는데 "남이 맡았다"고 알려준다.
   프론트(templates/partner_portal.html 의 dpClaim, "이건 오류가 아니라
   선착순의 정상 결과다"라는 자기 주석)는 이 문구를 그대로 alert 하므로,
   실제로 배정된 기사가 잘못 알고 현장에 안 갈 수 있다 — 30분 SLA 인
   출동에서는 round463 못지않게 실질적인 위험이다.

   고침 — 새 정책·새 헬퍼 없이, 형제(api_dispatch_assign, round463)가 이미
   쓰는 그 자리(호출 전에 '이미 내가 그 자원을 쥐고 있는가'만 먼저 확인)를
   그대로 옮겼다. app.py:api_partner_dispatch_claim() 맨 앞에서
   dispatches.status='수배됨' AND claimed_partner_id=이 요청의 pid 인지
   보고, 맞으면 DP.claim() 도 아래 보험사 notify() 도 부르지 않고
   duplicate:true 로 조용히 돌려준다(정확히 round463 주석의 "요청받은
   업체가 이미 그 수배를 잡고 있으면 그대로 duplicate 로 반환해
   assign_dispatch()도 notify()도 건드리지 않는다"와 같은 문장이 여기도
   그대로 적용된다). 다른 업체가 이미 잡은 **진짜** 실패는 이 조건에 안
   걸려 그대로 DP.claim() 을 타서 원래 문구를 그대로 받는다 — 회귀 없음
   (test_firstday.py 343행·test_rehearsal.py 243행이 이미 이 경로를
   검증하는 형제 테스트다).

   dispatch.py::claim() 자신은 건드리지 않았다 — 유일한 호출부(app.py 의
   이 라우트) 하나뿐이라(grep 재확인), 그 호출부에서 막는 것이 곧 근본
   수정이다. claim() 의 반환값을 바꿔 ok=True 를 돌려주는 방식은 시도하지
   않았다 — 그러면 호출부가 그대로 흘러 내려가 보험사 notify() 를 재시도
   때마다 또 부르는 **새** 중복발송을 만든다(round463 이 막으려던 바로 그
   부류). 그래서 이번 수정은 dispatch.py 가 아니라 app.py 라우트 자체에
   있다 — app.py 자신에 직접 정의된 함수를 고친 것이라 재기동이 필요하다.

   python test_scan_round540_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile

#  ⚠ 윈도 기본 콘솔은 cp949 라 em dash(—) 같은 문자를 print 하면
#    UnicodeEncodeError 로 죽는다 — 형제 테스트(round528·536·537·538 등)가
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
print("  스캔 540라운드 회귀 — 출동 수락(claim) 재시도가 '내가 맡았다'를")
print("  '남이 맡았다'로 오보하던 결함")
print("=" * 72)

_tmpdir = tempfile.mkdtemp(prefix="round540_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r540-csrf"
H = {"X-CSRF-Token": CSRF}
A = DB = DP = None
client = None
cid = did = did2 = pid_a = pid_b = None


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ==================================================================
print("\n[0] 소스 — 고친 지점이 실제로 app.py 에 있는가"
      "(동시편집 세션이 되돌렸다면 여기서부터 정직하게 실패해야 한다)")
# ------------------------------------------------------------------
try:
    _app_src = io.open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
    import ast as _ast
    chk(_ast.parse(_app_src) is not None, "STEP app.py 전체 ast.parse 성공")
    _claim_body = _py_fn_body(_app_src, "api_partner_dispatch_claim")
    chk('claimed_partner_id") == pid' in _claim_body,
        "★★★★★ api_partner_dispatch_claim() 에 '이미 내가 잡고 있는가' 사전"
        "확인이 있다(고치기 전엔 이 문자열이 이 함수 안에 없었다)")
    chk('"duplicate": True' in _claim_body,
        "STEP duplicate:true 조기 반환 분기가 있다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드540 [0] 소스 확인", f"{type(e).__name__} {e}")

try:
    import db as DB
    DB.init_db()
    import app as A
    import dispatch as DP

    conn0 = DB.get_db()
    iid = conn0.execute(
        "INSERT INTO insurers(name,status) VALUES('R540손해보험','활성')").lastrowid
    pid_a = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,phone,login_id) "
        "VALUES('R540업체A','시공사','활성','가드레일','서울','01099990101','r540pa')").lastrowid
    pid_b = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,phone,login_id) "
        "VALUES('R540업체B','시공사','활성','가드레일','서울','01099990102','r540pb')").lastrowid
    cid = conn0.execute(
        """INSERT INTO cases(case_no,insurer_id,insurer,category,region,address,
                             est_price,low_price,status,intake_type,created_at,is_demo)
           VALUES('R540-1',?,'R540손해보험','가드레일','서울','검증용 주소',0,0,
                  '접수','사진없음',?,0)""",
        (iid, DB.now())).lastrowid
    did = conn0.execute(
        "INSERT INTO dispatches(case_id,round,status,created_at,is_demo) "
        "VALUES(?,1,?,?,0)", (cid, DP.ST_OPEN, DB.now())).lastrowid
    for _pid in (pid_a, pid_b):
        conn0.execute(
            "INSERT INTO dispatch_calls(dispatch_id,partner_id,partner_name,call_order,"
            "                           notified_at,created_at) VALUES(?,?,'',1,?,?)",
            (did, _pid, DB.now(), DB.now()))
    conn0.commit()
    conn0.close()

    client = A.app.test_client()
    chk(True, "STEP 스크래치 DB — 보험사 1곳·협력사 2곳·사건·수배(모집중) 준비",
        os.environ["BOKGUON_DB_PATH"])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드540 실행 준비(DB.init_db·app import)", f"{type(e).__name__} {e}")


def _as_partner(pid_):
    with client.session_transaction() as sess:
        sess.clear()
        sess["partner_id"] = pid_
        sess["_csrf"] = CSRF
    return H


# ==================================================================
print("\n[1] 원인 재확인 — DP.claim() 자체는 같은 pid 의 재시도를 '남이")
print("    맡았다'와 구분 없이 답한다(이번 라운드가 손대지 않은 그대로)")
# ------------------------------------------------------------------
try:
    conn1 = DB.get_db()
    ok1, msg1, due1 = DP.claim(conn1, did, pid_a, "R540업체A")
    chk(ok1, "STEP 1차 DP.claim() 은 정상적으로 성공한다", (ok1, msg1))
    ok2, msg2, due2 = DP.claim(conn1, did, pid_a, "R540업체A")
    chk((not ok2) and ("다른 업체" in (msg2 or "")),
        "★★★★★ 같은 pid 로 다시 불러도 DP.claim() 은 '다른 업체가 맡았다'고 "
        "답한다 — 원인 확인(claim() 자신은 이번 라운드가 건드리지 않았다, "
        "app.py 호출부에서 막는다)", (ok2, msg2))
    conn1.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드540 [1] 원인 재확인", f"{type(e).__name__} {e}")

# 위 [1] 에서 이미 pid_a 가 dispatch `did` 를 실제로 잡았다 — 아래 HTTP
# 레이어 검증은 이 상태(수배됨·claimed_partner_id=pid_a)를 그대로 이어 쓴다.

# ==================================================================
print("\n[2] 실행(진짜 라우트): 같은 협력사가 같은 수배를 다시 수락 요청 —")
print("    이제 duplicate:true 로 조용히 성공 처리된다")
# ------------------------------------------------------------------
try:
    hdr = _as_partner(pid_a)
    r = client.post(f"/api/partner/dispatches/{did}/claim", headers=hdr, json={})
    body = r.get_json() or {}
    chk(r.status_code == 200 and body.get("ok") is True,
        "★★★★★ 재시도가 이제 200·ok:true 다(고치기 전엔 409·'다른 업체가 "
        "맡았다'는 오보)", (r.status_code, body))
    chk(body.get("duplicate") is True, "STEP 응답에 duplicate:true 가 표시된다", body)
    chk("맡고 있습니다" in (body.get("message") or ""),
        "STEP 메시지가 '내가 이미 맡고 있다'는 사실을 정확히 말한다"
        "('다른 업체' 문구가 아니다)", body)
    chk(body.get("case_no") == "R540-1" and body.get("address") is not None,
        "STEP 프론트 alert(dpClaim)가 쓰는 case_no·address 필드가 여전히 "
        "채워진다(성공 응답 모양과 호환 — 화면 무회귀)", body)

    conn_chk = DB.get_db()
    n_notify = conn_chk.execute(
        "SELECT COUNT(*) FROM notifications WHERE ntype='출동배정' AND case_id=?",
        (cid,)).fetchone()[0]
    conn_chk.close()
    chk(n_notify == 0,
        "★★★★★ 보험사 '출동배정' 알림이 이 재시도로 추가되지 않았다"
        "(DP.claim() 도 notify() 도 아예 호출되지 않았다 — 새 중복발송을 "
        "만들지 않는다)", f"{n_notify}건")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드540 [2] 재시도 HTTP 실행", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[3] 회귀 안전 — 다른 협력사(B)가 같은 수배를 노리면 여전히 원래")
print("    문구·409 로 정확히 막힌다(이번 수정이 진짜 실패까지 숨기지 않는가)")
# ------------------------------------------------------------------
try:
    hdr_b = _as_partner(pid_b)
    r = client.post(f"/api/partner/dispatches/{did}/claim", headers=hdr_b, json={})
    body = r.get_json() or {}
    chk(r.status_code == 409 and body.get("ok") is False,
        "STEP 업체 B 는 여전히 409 로 막힌다(선착순 정상 동작 — 무회귀)",
        (r.status_code, body))
    chk("다른 업체" in (body.get("error") or ""),
        "STEP 이번엔 진짜 '다른 업체' 이므로 원래 문구를 그대로 받는다", body)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드540 [3] 회귀 안전(업체 B)", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[4] 회귀 안전 — 아직 아무도 안 잡은 새 수배는 이 지름길이 끼어들지")
print("    않고 그대로 DP.claim() 을 타 정상적으로 최초 수락된다")
# ------------------------------------------------------------------
try:
    conn2 = DB.get_db()
    did2 = conn2.execute(
        "INSERT INTO dispatches(case_id,round,status,created_at,is_demo) "
        "VALUES(?,2,?,?,0)", (cid, DP.ST_OPEN, DB.now())).lastrowid
    conn2.execute(
        "INSERT INTO dispatch_calls(dispatch_id,partner_id,partner_name,call_order,"
        "                           notified_at,created_at) VALUES(?,?,'',1,?,?)",
        (did2, pid_a, DB.now(), DB.now()))
    conn2.commit()
    conn2.close()
    hdr = _as_partner(pid_a)
    r = client.post(f"/api/partner/dispatches/{did2}/claim", headers=hdr, json={})
    body = r.get_json() or {}
    chk(r.status_code == 200 and body.get("ok") is True and not body.get("duplicate"),
        "STEP '모집중' 상태의 새 수배는 지름길 없이 정상 최초 수락으로 "
        "처리된다(duplicate 표시가 안 붙는다)", (r.status_code, body))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드540 [4] 회귀 안전(새 수배 최초 수락)", f"{type(e).__name__} {e}")

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
