# -*- coding: utf-8 -*-
"""스캔 537라운드 회귀 — 관리자 계정 삭제(api_admin_delete, DELETE /api/admins/<id>)가
   그 계정의 2단계 인증 복구코드(admin_recovery_codes)를 지우지 않고 고아로
   남기던 결함.

   조사 배경 — 이번 라운드 지시 각도 (5) "관리자가 사건을 삭제(진짜 삭제)하면
   자식 레코드가 고아로 남는지 CASCADE 되는지"를 이 저장소에 그대로 적용해 봤다.
   cases 자체는 하드 삭제 라우트가 없다(grep 재확인 — "DELETE FROM cases"가
   app.py 어디에도 없음). 그런데 admins 는 실제로 물리 DELETE 되는 계정
   테이블이었다(api_admin_delete, app.py:1763) — 같은 질문(부모를 지우면
   자식이 고아로 남는가)을 이 테이블에 적용해 봤다.

   admin_recovery_codes(admin_id INTEGER NOT NULL, ...) 는 REFERENCES 절이
   없고(db.py:570 스키마 실측) sqlite3 기본 연결도 PRAGMA foreign_keys 를
   켜지 않으므로, admins 행을 지워도 admin_recovery_codes 행은 DB 엔진
   차원에서 전혀 정리되지 않는다 — 애플리케이션 코드가 직접 지워야 한다.

   그런데 바로 그 정리를 이미 하는 형제가 같은 파일에 있었다: 2단계 인증을
   "해제"만 하고 계정은 그대로 두는 api_otp_disable(app.py, 수정 전 2850행)은
   `DELETE FROM admin_recovery_codes WHERE admin_id=?` 을 이미 부르고 있다.
   계정을 통째로 영구 삭제하는(해제보다 훨씬 강한 조작) api_admin_delete 만
   그 정리가 빠져 있었다 — 약한 조작(해제)은 청소하면서 강한 조작(삭제)은
   안 하는 비대칭.

   실측(운영 DB, 읽기전용 조회) — 지금 admin_recovery_codes 는 0행(2FA를
   실제로 켠 적이 없다)이라 아직 고아 행이 쌓이진 않았지만, 코드 경로 자체는
   그대로 있었다(admins.id 는 AUTOINCREMENT라 재사용되지 않으므로 재악용
   경로는 없다 — 순수 데이터 정리 누락).

   고침 — 형제(api_otp_disable)와 정확히 같은 한 줄
   `conn.execute("DELETE FROM admin_recovery_codes WHERE admin_id=?", (aid,))`
   을 admins 삭제 직전에 추가했다(app.py:1790). 새 정책·새 헬퍼 없음.

      python test_scan_round537_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile

#  ⚠ 윈도 기본 콘솔은 cp949 라 em dash(—) 같은 문자를 print 하면
#    UnicodeEncodeError 로 죽는다 — 형제 테스트(round528·536 등)가 이미 쓰는
#    방어를 그대로 옮긴다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 537라운드 회귀 — 관리자 계정 삭제의 복구코드 고아행")
print("=" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ==================================================================
print("\n[1] 소스: api_admin_delete() 가 이제 admin_recovery_codes 도 함께 지운다 "
      "(형제 api_otp_disable() 와 같은 관례)")
# ------------------------------------------------------------------
import ast as _ast
chk(_ast.parse(APP_SRC) is not None, "STEP app.py 전체 ast.parse 성공")

ad_body = _py_fn_body(APP_SRC, "api_admin_delete")
chk('DELETE FROM admin_recovery_codes WHERE admin_id=?' in ad_body,
    "★★★★★ api_admin_delete() 본문이 이제 admin_recovery_codes 를 지운다"
    "(고치기 전엔 이 문자열이 이 함수 안에 없었다)")
chk('DELETE FROM admins WHERE id=?' in ad_body,
    "STEP admins 자신을 지우는 원래 문장은 그대로 남아 있다")
_rc_idx = ad_body.index('DELETE FROM admin_recovery_codes WHERE admin_id=?')
_ad_idx = ad_body.index('DELETE FROM admins WHERE id=?')
chk(_rc_idx < _ad_idx,
    "STEP 자식(복구코드) 삭제가 부모(admins) 삭제보다 먼저 실행된다"
    "(자식 먼저 정리하는 순서)")
chk(ad_body.index("conn.commit()") > _ad_idx,
    "STEP 두 DELETE 모두 같은 commit() 이전 — 한 트랜잭션으로 묶인다")

#  형제 api_otp_disable() 은 이번 라운드가 손대지 않았다 — 이미 하던 정리가
#  그대로 살아 있는지 대조한다(이번 수정이 베낀 원본).
od_body = _py_fn_body(APP_SRC, "api_otp_disable")
chk('DELETE FROM admin_recovery_codes WHERE admin_id=?' in od_body,
    "★★★ 형제 api_otp_disable() 의 기존 정리는 이번 라운드가 손대지 않고 "
    "그대로 남아 있다(이식 원본)")

# ==================================================================
# 실행 준비
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round537_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r537-csrf"
H = {"X-CSRF-Token": CSRF}
A = None
DB = None


def _admin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "admin"
        sess["admin_name"] = "검증"
        sess["admin_role"] = "최고관리자"
        sess["_csrf"] = CSRF
    return c


def _mk_admin(conn, username, role, name="검증대상"):
    cur = conn.execute(
        "INSERT INTO admins(username,password_hash,name,role) VALUES(?,?,?,?)",
        (username, "x", name, role))
    return cur.lastrowid


def _mk_recovery_codes(conn, admin_id, n=2):
    for i in range(n):
        conn.execute(
            "INSERT INTO admin_recovery_codes(admin_id, code_hash, created_at) "
            "VALUES(?,?,datetime('now'))",
            (admin_id, f"hash-{admin_id}-{i}"))


def _recovery_count(conn, admin_id):
    return conn.execute(
        "SELECT COUNT(*) FROM admin_recovery_codes WHERE admin_id=?",
        (admin_id,)).fetchone()[0]


def _admin_exists(conn, admin_id):
    return conn.execute(
        "SELECT COUNT(*) FROM admins WHERE id=?", (admin_id,)).fetchone()[0] > 0


try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    _mk_admin(conn0, "admin", "최고관리자", "실행계정")
    target_id = _mk_admin(conn0, "target", "중간관리자")
    _mk_recovery_codes(conn0, target_id, 2)
    conn0.commit(); conn0.close()
    chk(True, "스크래치 DB·app 모듈 로드 성공 — 관리자 2명(actor·target) 준비",
        os.environ["BOKGUON_DB_PATH"])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드537 실행 준비(DB.init_db·app import)", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[2] 실행(진짜 라우트): DELETE /api/admins/<id> 가 계정과 함께 "
      "복구코드도 지운다")
# ------------------------------------------------------------------
try:
    conn = DB.get_db()
    chk(_recovery_count(conn, target_id) == 2,
        "STEP 준비 확인 — target 계정에 복구코드 2건이 미리 심어져 있다")
    conn.close()

    admin_c = _admin_client()
    r = admin_c.delete(f"/api/admins/{target_id}", headers=H)
    body = r.get_json() or {}
    chk(r.status_code == 200 and body.get("ok") is True,
        "★★★★ DELETE /api/admins/<id> 가 200·ok:true 를 돌려준다",
        (r.status_code, body))

    conn = DB.get_db()
    chk(not _admin_exists(conn, target_id),
        "STEP admins 행이 실제로 사라졌다(원래 동작 그대로)")
    chk(_recovery_count(conn, target_id) == 0,
        "★★★★★ 지금 코드는 admin_recovery_codes 도 함께 사라진다"
        "(고치기 전엔 여기 2건이 계정 삭제 뒤에도 그대로 남았다)")
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드537 [2] 실제 라우트 실행", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[3] 되돌리기 — admin_recovery_codes 정리 줄을 빼면(수정 전 코드 "
      "재구성) 정말 고아행이 남는가(인과관계 직접증명)")
# ------------------------------------------------------------------
#  ⚠ app.py 자체는 건드리지 않는다 — 동시에 다른 세션이 같은 파일을 건드릴
#    수 있는 환경(round520 이후 표준 관례). 되돌림-증명은 이 라운드가
#    고치기 **직전**의 실제 api_admin_delete 본문(수정 직전 이 세션이 Read 로
#    확인한 원문 그대로)을 테스트 안에서만 문자열로 재구성해 같은 시나리오에
#    직접 실행한다. 데코레이터(@app.delete·@require_role)는 라우팅·인가
#    검증용이라 이 재구성에서는 걷어내고 몸통 로직만 검증한다(round536과
#    같은 방식) — 대신 실제 Flask 요청·앱 컨텍스트(test_request_context) 위에서
#    돌려 session·jsonify 등 실제 의존 객체를 그대로 쓴다.
_PRE537_SRC = '''
def _api_admin_delete_pre537(aid):
    conn = DB.get_db()
    conn.execute("BEGIN IMMEDIATE")
    a = one(conn.execute("SELECT * FROM admins WHERE id=?", (aid,)))
    if not a:
        conn.rollback(); conn.close()
        return jsonify({"ok": False, "error": "계정을 찾을 수 없습니다."}), 404
    if a["username"] == session.get("admin"):
        conn.rollback(); conn.close()
        return jsonify({"ok": False, "error": "본인 계정은 삭제할 수 없습니다."}), 409
    if a["role"] == "최고관리자":
        n_super = conn.execute("SELECT COUNT(*) n FROM admins WHERE role='최고관리자'").fetchone()["n"]
        if n_super <= 1:
            conn.rollback(); conn.close()
            return jsonify({"ok": False, "error": "마지막 최고관리자는 삭제할 수 없습니다."}), 409
    conn.execute("DELETE FROM admins WHERE id=?", (aid,))
    DB.log(conn, actor(), "관리자 계정 삭제", f"{a['username']} ({a['role']})")
    conn.commit(); conn.close()
    return jsonify({"ok": True})
'''
try:
    conn0 = DB.get_db()
    target2_id = _mk_admin(conn0, "target2", "중간관리자")
    _mk_recovery_codes(conn0, target2_id, 3)
    conn0.commit(); conn0.close()

    _ns = dict(vars(A))             # app 모듈 네임스페이스 복사(진짜 모듈은 안 건드림)
    exec(compile(_PRE537_SRC, "<round537_pre_reconstructed>", "exec"), _ns)
    _old_delete = _ns["_api_admin_delete_pre537"]

    with A.app.test_request_context("/api/admins/%d" % target2_id, method="DELETE"):
        from flask import session as _flask_session
        _flask_session["admin"] = "admin"
        _flask_session["admin_name"] = "검증"
        _flask_session["admin_role"] = "최고관리자"
        resp = _old_delete(target2_id)
    #  jsonify 응답은 (Response, status) 튜플로 온다(원본과 동일한 반환 형태)
    resp_obj = resp[0] if isinstance(resp, tuple) else resp
    chk(resp_obj is not None,
        "STEP 재구성한 옛 함수도 정상적으로 응답을 만든다(실행 자체는 성공)")

    conn = DB.get_db()
    chk(not _admin_exists(conn, target2_id),
        "STEP 옛 코드(재구성)도 admins 행은 그대로 지운다(겉보기 동작은 "
        "지금 코드와 똑같다 — 그래서 그동안 아무도 눈치 못 챘다)")
    chk(_recovery_count(conn, target2_id) == 3,
        "★★★★★ 그런데 옛 코드(재구성)는 admin_recovery_codes 3건을 고아로 "
        "그대로 남긴다 — 지금 코드(위 [2])는 같은 시나리오에서 실제로 0건으로 "
        "지웠다. 이 차이가 이 회귀가 실제로 결함을 잡아낼 능력이 있다는 "
        "인과관계 증명이다", _recovery_count(conn, target2_id))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드537 [3] 되돌림-증명", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[4] 실행: 최고관리자를 삭제하는 경로도(최후 1인 보호를 피해가며) "
      "같은 정리가 적용된다")
# ------------------------------------------------------------------
try:
    conn0 = DB.get_db()
    #  최고관리자가 이미 하나 있으므로("admin"), 하나 더 만들어야 "마지막
    #  최고관리자는 삭제할 수 없습니다" 관문에 걸리지 않고 삭제를 검증할 수 있다.
    target3_id = _mk_admin(conn0, "target3", "최고관리자")
    _mk_recovery_codes(conn0, target3_id, 1)
    conn0.commit(); conn0.close()

    admin_c = _admin_client()
    r = admin_c.delete(f"/api/admins/{target3_id}", headers=H)
    body = r.get_json() or {}
    chk(r.status_code == 200 and body.get("ok") is True,
        "STEP 두 번째 최고관리자 삭제도 정상 처리된다(최후 1인 보호에 안 걸림)",
        (r.status_code, body))
    conn = DB.get_db()
    chk(_recovery_count(conn, target3_id) == 0,
        "★★★ 최고관리자 등급 삭제 경로에서도 복구코드가 함께 지워진다"
        "(등급별로 다른 코드경로가 아니라 같은 함수 한 곳이라 당연하지만 "
        "실측으로 재확인)")
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드537 [4] 최고관리자 삭제 경로", f"{type(e).__name__} {e}")

# ==================================================================
# 정리
# ------------------------------------------------------------------
os.environ.pop("BOKGUON_DB_PATH", None)
os.environ.pop("BOKGUON_UPLOAD_DIR", None)
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
