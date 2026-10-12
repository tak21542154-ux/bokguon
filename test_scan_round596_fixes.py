# -*- coding: utf-8 -*-
"""스캔 596라운드 회귀 — round595가 고친 것과 같은 근본원인(sqlite3가 자기
INTEGER 컬럼의 실제 상한 — 부호있는 8바이트, 2**63-1 — 을 넘는 파이썬 int를
바인딩하려 하면 OverflowError를 던지는데, 그 값이 전역 예외핸들러까지 올라가
500 SERVER_ERROR가 된다)를 **세 번째 유입구**에서 확인해 고쳤다.

round595는 이 결함을 URL 경로(<int:...> 라우트 변환기, 120곳)와 쿼리스트링
(insurer_id, 2곳)에서 고쳤다. 그런데 이 파일 전체가 JSON 본문의 id류 값을
받을 때 쓰는 관례 — `try: x = int(d.get(...)) except (TypeError, ValueError):
...` — 는 자릿수만 비정상으로 큰 순수 숫자 문자열("9"*40)에는 안 걸린다
(파이썬 int()는 자릿수 제한이 없어 ValueError가 안 난다. round592가 고친
"숫자로 안 바뀌는 값"과는 다른 입력 모양이다). 실측(api_admin_notifications_
read에 body={"id": "9"*40}): UPDATE ... WHERE id=? 바인딩에서 OverflowError가
나 500이 됐다 — 같은 관례를 쓰는 이 파일의 다른 호출부(예: api_dispatch_assign
의 partner_id)도 전부 같은 값이다(직접 확인, 최소 2곳).

이 관례가 이 파일 전체에 수십 곳 흩어져 있어(_attach_defect_photos의
photo_id, api_defect_photos_upload의 fix_for 등) 호출부마다 고치는 대신,
이 예외가 최종적으로 모이는 단 하나의 지점 — 전역 예외핸들러 err_500 —
에서 OverflowError만 골라 클라이언트 입력 오류(400)로 돌린다. 이미 있던
커넥션 정리(_cleanup_conns)·로깅 파이프라인은 그대로 재사용하고(회귀
없음), 사용자에게 보이는 상태코드·메시지만 분기한다.

[1] 소스 확인 — err_500 안에 OverflowError 분기가 있고, HTTPException 판정
    보다 뒤·커넥션 정리(_cleanup_conns)보다 앞에 와서 그 정리를 그대로
    통과한다(정리 로직을 새로 만들지 않는다).
[2] 실제 Flask 앱 — 서로 다른 두 라우트(api_admin_notifications_read의
    본문 id, api_dispatch_assign의 본문 partner_id)에서 자릿수만 큰 값이
    500이 아니라 400으로 응답한다(핵심 재현 — 단일 지점 수정이 서로 다른
    호출부에도 함께 적용됨을 확인).
[3] 되돌림-증명 — Flask의 등록된 예외핸들러(app.error_handler_spec)를
    OverflowError 분기가 빠진 옛 버전으로 메모리에서만 잠깐 바꿔치기해
    (디스크 무수정) 같은 요청이 실제로 500 SERVER_ERROR로 되돌아감을
    확인한 뒤 원복 — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명한다.
[4] 잠금 미유출 확인 — BEGIN IMMEDIATE 를 이미 연 상태에서 OverflowError가
    나도(overflow 경로 진입 전에 쓰기 잠금을 잡는 라우트) 커넥션 정리가
    여전히 돌아 잠금이 안 새는지, 곧바로 이어지는 정상 쓰기가 busy_timeout
    (8초)을 기다리지 않고 즉시 성공하는지로 확인한다.
[5] 회귀 없음 — (a) 정상 id·존재하지 않는 보통 id는 여전히 기존 그대로
    동작한다(과잉 변경 아님). (b) round592가 고친 "숫자가 아닌 값"은
    여전히 각 라우트 자신의 400(다른 문구)을 그대로 낸다(이 전역 분기가
    끼어들지 않는다 — ValueError 지, OverflowError 가 아니므로). (c) 이
    결함과 무관한 예외(예: KeyError)는 여전히 500 SERVER_ERROR로 응답한다
    (과잉 일반화 아님 — OverflowError 하나만 골라 낸다).

    python test_scan_round596_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 596라운드 회귀 — JSON 본문 id가 자릿수만 비정상으로 크면 500 (세 번째 유입구)")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
APP_SRC = io.open(os.path.join(HERE, "app.py"), encoding="utf-8").read()

i_errhandler = APP_SRC.index("@app.errorhandler(Exception)")
i_fn = APP_SRC.index("def err_500(e):")
i_httpexc = APP_SRC.index("isinstance(e, HTTPException)", i_fn)
i_overflow_calc = APP_SRC.index("is_overflow = isinstance(e, OverflowError)", i_fn)
i_cleanup = APP_SRC.index("_cleanup_conns(rollback=True)", i_fn)
i_branch = APP_SRC.index("if is_overflow:", i_fn)
i_fn_end = APP_SRC.index("\n\n\n", i_fn)
FN_SRC = APP_SRC[i_fn:i_fn_end]

chk(i_errhandler < i_fn, "STEP err_500이 @app.errorhandler(Exception)에 등록돼 있다")
chk(i_httpexc < i_overflow_calc,
    "★★★★★ HTTPException 통과 판정 뒤에 OverflowError 판정이 온다"
    "(404/403 등 정상 HTTP 예외는 그대로 각자 핸들러로 넘어간다 — 회귀 없음)")
chk(i_overflow_calc < i_cleanup,
    "★★★★★ OverflowError 판정이 커넥션 정리(_cleanup_conns)보다 앞에 있다 — "
    "판정 자체는 부작용이 없어 순서를 바꿔도 안전하지만, 정리 로직은 "
    "OverflowError 경로도 반드시 통과해야 한다(아래 STEP과 함께 확인)")
chk(i_cleanup < i_branch,
    "★★★★★ 커넥션 정리가 상태코드 분기보다 먼저 실행된다 — OverflowError 응답도 "
    "기존 500 응답과 똑같이 _cleanup_conns(rollback=True)를 거친다"
    "(새 정리 로직을 만들지 않고 기존 파이프라인을 재사용 — 잠금 유출 방지 회귀 없음)")
chk('"code": "BAD_INPUT"' in FN_SRC and "), 400" in FN_SRC,
    "★★★★★ OverflowError 분기가 400(클라이언트 입력 오류)으로 응답한다")
chk("app.logger.error(" in FN_SRC.split("if is_overflow:")[0],
    "STEP OverflowError도 여전히 로그(ref 포함)에 남는다 — 사용자에게만 안 보일 뿐 "
    "운영팀 진단 능력은 그대로 유지된다")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[5] 실제 Flask 앱 실행")
# ══════════════════════════════════════════════════════════════
_tmpdir = tempfile.mkdtemp(prefix="round596_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    HUGE = int("9" * 40)          # 자릿수만 비정상으로 큰 값 — sqlite 상한을 한참 넘는다

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r596admin','x','검증','최고관리자')")
    real_cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,address,created_at) "
        "VALUES('R596-CASE-01','접수','누수·배관·설비','서울','서울 어딘가',datetime('now'))"
    ).lastrowid
    conn.commit()
    conn.close()

    admin = A.app.test_client()
    with admin.session_transaction() as sess:
        sess["admin"] = "r596admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = "r596token"
    HDR = {"X-CSRF-Token": "r596token"}

    # ── [2] 핵심 재현 — 서로 다른 두 호출부(본문 id) 모두 huge 값에 400을 준다 ──
    r_notif = admin.post("/api/admin/notifications/read", json={"id": str(HUGE)}, headers=HDR)
    chk(r_notif.status_code == 400 and (r_notif.get_json() or {}).get("code") == "BAD_INPUT",
        "★★★★★ api_admin_notifications_read — 본문 id가 자릿수만 커도 "
        "500이 아니라 400(BAD_INPUT)", (r_notif.status_code, r_notif.get_json()))

    r_notif_num = admin.post("/api/admin/notifications/read", json={"id": HUGE}, headers=HDR)
    chk(r_notif_num.status_code == 400,
        "STEP 같은 값을 JSON 숫자(문자열이 아니라)로 보내도 동일하게 400",
        r_notif_num.status_code)

    r_dispatch = admin.post(f"/api/cases/{real_cid}/dispatch/assign",
                             json={"partner_id": HUGE, "reason": "회귀테스트용 배정 사유"},
                             headers=HDR)
    chk(r_dispatch.status_code == 400 and (r_dispatch.get_json() or {}).get("code") == "BAD_INPUT",
        "★★★★★ api_dispatch_assign — 서로 무관한 두 번째 호출부(partner_id)도 "
        "같은 한 지점 수정으로 함께 방어됨(500이 아니라 400)",
        (r_dispatch.status_code, r_dispatch.get_json()))

    # ── [3] 되돌림-증명 — 등록된 예외핸들러를 옛 버전으로 메모리에서만 바꿔친다 ──
    def _old_err_500(e):
        """OverflowError 분기가 없던 수정 전 err_500 — 크래시 지점만 재현하는 최소 대역."""
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e
        try:
            A._cleanup_conns(rollback=True)
        except Exception:
            pass
        import secrets as _secrets
        ref = _secrets.token_hex(4)
        return A.jsonify({"ok": False, "error": "처리 중 오류", "code": "SERVER_ERROR",
                          "ref": ref}), 500

    _spec = A.app.error_handler_spec[None][None]
    _orig_handler = _spec[Exception]
    _spec[Exception] = _old_err_500
    try:
        r_old = admin.post("/api/admin/notifications/read", json={"id": str(HUGE)}, headers=HDR)
        chk(r_old.status_code == 500 and (r_old.get_json() or {}).get("code") == "SERVER_ERROR",
            "★★★★★ 새 분기를 빼면 huge id가 실제로 500 SERVER_ERROR로 되돌아간다"
            "(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명 — OverflowError가 "
            "UPDATE ... WHERE id=? 바인딩에서 실제로 발생)", r_old.get_json())
    finally:
        _spec[Exception] = _orig_handler   # 원복 — 디스크 파일은 애초에 건드리지 않았다

    r_restored = admin.post("/api/admin/notifications/read", json={"id": str(HUGE)}, headers=HDR)
    chk(r_restored.status_code == 400,
        "STEP 원복 후에는 다시 400으로 돌아온다(테스트가 전역 상태를 오염시키지 않음)",
        r_restored.status_code)

    # ── [4] 잠금 미유출 확인 — overflow 경로 뒤 곧바로 정상 쓰기가 즉시 성공한다 ──
    #  api_admin_notifications_read는 int(d["id"])를 검사한 **뒤** BEGIN IMMEDIATE를
    #  연다 — 즉 이 라우트 자신은 잠금을 잡기 전에 걸린다. 그래서 잠금이 실제로
    #  걸린 채 OverflowError가 나는 경로(assign_dispatch가 BEGIN IMMEDIATE 안에서
    #  partner 조회를 먼저 한다)로 다시 확인한다 — 두 번째 배정 시도가 8초
    #  (BUSY_TIMEOUT) 대기 없이 바로 응답하면 잠금이 안 새 것이다.
    t0 = time.time()
    r_after = admin.post(f"/api/cases/{real_cid}/dispatch/assign",
                          json={"partner_id": HUGE, "reason": "잠금 확인용 두 번째 시도"},
                          headers=HDR)
    dt = time.time() - t0
    chk(r_after.status_code == 400 and dt < 2.0,
        f"★★★★★ overflow 경로 직후 같은 라우트를 다시 두드려도 busy_timeout(8초) "
        f"대기 없이 즉시 응답한다({dt:.3f}초) — 쓰기 잠금이 안 샜다", dt)

    # ── [5] 회귀 없음 ──
    r_real = admin.post("/api/admin/notifications/read", json={"id": 999999}, headers=HDR)
    chk(r_real.status_code == 200 and (r_real.get_json() or {}).get("ok") is True,
        "★★★ 존재하지 않는 보통 크기 id는 여전히 그대로 200(정상 no-op)", r_real.get_json())

    r_nonnum = admin.post("/api/admin/notifications/read", json={"id": "abc"}, headers=HDR)
    chk(r_nonnum.status_code == 400
        and (r_nonnum.get_json() or {}).get("error") == "알림 id는 숫자여야 합니다.",
        "★★★★★ round592가 고친 '숫자가 아닌 값'은 여전히 라우트 자신의 400(다른 "
        "문구)을 그대로 낸다 — 이 전역 분기가 끼어들지 않는다(ValueError지 "
        "OverflowError가 아니므로)", r_nonnum.get_json())

    def _boom():
        raise KeyError("이 결함과 무관한 예외")
    _orig_view = A.app.view_functions.get("api_csrf")
    A.app.view_functions["api_csrf"] = _boom
    try:
        r_unrelated = admin.get("/api/csrf")
        chk(r_unrelated.status_code == 500
            and (r_unrelated.get_json() or {}).get("code") == "SERVER_ERROR",
            "★★★★★ 이 결함과 무관한 예외(KeyError)는 여전히 500 SERVER_ERROR — "
            "OverflowError 하나만 골라 냄(과잉 일반화 아님)", r_unrelated.get_json())
    finally:
        A.app.view_functions["api_csrf"] = _orig_view

    r_view_restored = admin.get("/api/csrf")
    chk(r_view_restored.status_code == 200,
        "STEP 뷰 함수 원복 후 정상 200(테스트가 전역 상태를 오염시키지 않음)",
        r_view_restored.status_code)

except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]~[5] 실제 앱 재현 준비/실행", f"{type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
