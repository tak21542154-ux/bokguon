# -*- coding: utf-8 -*-
"""스캔 543라운드 회귀 — 관리자 계정 수정(api_admin_update, PATCH /api/admins/<id>)의
   "이름" 분기가 이름이 실제로 안 바뀌어도 매번 UPDATE+"관리자 이름 변경" 감사로그를
   남기던 결함.

   조사 배경 — 지시받은 각도 (1) "새 비밀번호가 기존과 같은 값이어도 '변경 완료'
   감사로그가 실제 변경 없이 남는지"를 그대로 좇았다. /api/change-password
   (app.py:1368) 자체는 이미 `if current == new: return 400`으로 막고 있어
   깨끗했다(감사로그 이전에 거부). 그런데 같은 "값이 같아도 변경으로 취급"
   질문을 이 앱의 다른 "정보 수정" 라우트들에 넓혀 대조하다가 api_admin_update
   (app.py:1748, 관리자 등급·이름·비밀번호를 한 번에 다루는 라우트) 안에서
   **같은 함수 안의 두 형제 분기가 서로 다른 기준을 쓰는 것**을 발견했다 —
   role 분기(1759행)는 `d["role"] != a["role"]`를 확인한 뒤에만 UPDATE+로그를
   쏘는데, 바로 아래 name 분기(수정 전 1771~1774행)는 `d.get("name")`이 있고
   비어있지만 않으면 새 값이 옛 이름과 같아도 매번 UPDATE 하고
   "관리자 이름 변경: 홍길동→홍길동" 식으로 로그를 남겼다.

   더 결정적인 형제 증거 — _sub_update_impl(app.py:3375, 보험사·협력사
   하위계정 수정)의 자기 자신 주석(3384~3389행)이 바로 이 라운드421 결함을
   가리킨다: "값이 같아도 매번 UPDATE+로그를 쏘던 것도, 실제로 바뀐 필드만
   반영하도록 형제와 같은 기준으로 맞춘다" — 그 "형제"로 api_admin_update를
   직접 지목하며 고쳤다. 그런데 정작 그 "형제" 자신의 name 분기는 이 기준을
   충족하지 못하고 있었다 — 라운드421이 참조한 기준점 자체에 구멍이 있었던
   셈이다.

   실사용 영향(추정이 아니라 프론트 코드로 확인) — 관리자 목록의 편집 모달
   (static/admin.js: adminForm, 2906행)은 이름 입력칸을 항상 현재 이름으로
   미리 채워 둔다. 저장 버튼(saveAdmin, 2940행)은 등급만 바꾸는 경우에도
   `{name: $('#ad_name').value.trim(), role: ...}`를 매번 그대로 보낸다 —
   즉 **등급만 바꾸는 모든 저장이 예외 없이** 이름 필드도 함께 보내 이 거짓
   "이름 변경" 항목을 만든다. "관리자 이름 변경"은 _ADMIN_ACCOUNT_ACTIONS
   (17300행 부근)에 속해 최고관리자만 볼 수 있게 특별히 가리는 5개 민감
   행위 중 하나인데(하위 등급 관리자가 다른 관리자 계정의 이름·등급
   변경이력을 못 보게 하려는 장치), 그 신뢰를 지키라고 있는 로그 자체가
   실제로 없었던 변경을 있었다고 우겨 감사 기록의 정확성을 해쳤다.

   고침 — 새 정책·새 헬퍼 없이, 바로 위 role 분기와 _sub_update_impl이 이미
   쓰는 관례(`if 새값 != 옛값:` 로 감싸고서야 UPDATE+로그)를 name 분기에도
   그대로 이식했다(app.py:1787, `if new_name != (a["name"] or ""):`). 이
   가드 안으로 UPDATE·DB.log 두 줄을 한 단 들여쓰기만 했을 뿐 그 외 로직·
   문구·반환값은 전혀 안 바꿨다.

   app.py 자신에 정의된 라우트 함수(api_admin_update)를 고쳤다 — app.py가
   import하는 별도 모듈이 아니다. 이미 떠 있는 프로세스가 있다면 재시작해야
   새 가드가 실제 요청에 반영된다(파이썬은 이미 임포트한 모듈을 자동으로
   다시 읽지 않는다).

      python test_scan_round543_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile

#  ⚠ 윈도 기본 콘솔은 cp949 라 em dash(—) 같은 문자를 print 하면
#    UnicodeEncodeError 로 죽는다 — 형제 테스트(round537·541·542 등)가
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


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


print("=" * 72)
print("  스캔 543라운드 회귀 — 관리자 계정 수정의 '이름 변경' 감사로그가")
print("  실제 변경 없이도 남던 결함 (api_admin_update)")
print("=" * 72)

APP_SRC = read("app.py")

# ==================================================================
print("\n[0] 소스 — 고친 지점이 실제로 app.py 에 있는가"
      "(동시편집 세션이 되돌렸다면 여기서부터 정직하게 실패해야 한다)")
# ------------------------------------------------------------------
try:
    import ast as _ast
    chk(_ast.parse(APP_SRC) is not None, "STEP app.py 전체 ast.parse 성공")

    au_body = _py_fn_body(APP_SRC, "api_admin_update")
    chk('if new_name != (a["name"] or ""):' in au_body,
        "★★★★★ api_admin_update() 의 name 분기에 새 가드가 있다"
        "(고치기 전엔 이 줄이 없었다)")
    #  ⚠⚠ [라운드609] round601~608 형제결함군 — new_name 계산이 raw
    #    (d["name"] or "").strip()[:40] 였다(숫자 등을 보내면 AttributeError로
    #    500). _s(d["name"], 40) 로 바뀌며 이 리터럴도 함께 바뀌었다 — 검증
    #    취지(순서: 계산→가드→UPDATE→로그)는 그대로, 리터럴만 지금 코드에 맞춘다.
    _i_new = au_body.index('new_name = _s(d["name"]')
    _i_guard = au_body.index('if new_name != (a["name"] or ""):')
    _i_update = au_body.index('UPDATE admins SET name=?')
    _i_log = au_body.index('DB.log(conn, actor(), "관리자 이름 변경"')
    chk(_i_new < _i_guard < _i_update < _i_log,
        "★★★★ 순서가 옳다 — new_name 계산 → 가드 → UPDATE → 로그"
        "(가드가 UPDATE·로그보다 먼저다)")
    #  형제(role 분기)는 이번 라운드가 손대지 않았다 — 그대로 남아 있는지 대조.
    chk('if "role" in d and d["role"] in ADMIN_ROLES and d["role"] != a["role"]:' in au_body,
        "STEP 형제 role 분기(이미 값이 다를 때만 UPDATE+로그)는 이번 라운드가 "
        "손대지 않고 원래 그대로다(이식 원본)")
    chk('DB.log(conn, actor(), "관리자 비밀번호 재발급"' in au_body,
        "STEP reset_pw 분기도 무관하게 그대로 남아 있다(과잉수정 없음)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드543 [0] 소스 확인", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[1] 준비 — 스크래치 DB, 실행계정(최고관리자) + 대상 관리자 4명")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round543_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r543-csrf"
H = {"X-CSRF-Token": CSRF}
A = DB = None
tid_a = tid_b = tid_c = tid_d = None


def _admin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "admin543"
        sess["admin_name"] = "실행계정543"
        sess["admin_role"] = "최고관리자"
        sess["_csrf"] = CSRF
    return c


def _mk_admin(conn, username, role, name):
    cur = conn.execute(
        "INSERT INTO admins(username,password_hash,name,role) VALUES(?,?,?,?)",
        (username, "x", name, role))
    return cur.lastrowid


def _log_count(conn, action, username_like):
    return conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE action=? AND detail LIKE ?",
        (action, username_like + "%")).fetchone()[0]


try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    _mk_admin(conn0, "admin543", "최고관리자", "실행계정543")
    tid_a = _mk_admin(conn0, "target543a", "중간관리자", "김철수543")
    tid_b = _mk_admin(conn0, "target543b", "중간관리자", "박영희543")
    tid_c = _mk_admin(conn0, "target543c", "하위관리자", "이민수543")
    tid_d = _mk_admin(conn0, "target543d", "하위관리자", "최성훈543")
    conn0.commit(); conn0.close()
    chk(bool(tid_a and tid_b and tid_c and tid_d),
        "STEP 실행계정 + 대상 관리자 4명 생성", (tid_a, tid_b, tid_c, tid_d))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드543 [1] 준비", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[2] 실행(진짜 라우트, 지금 코드) — 등급만 바꾸면서 이름칸엔 "
      "옛 이름을 그대로 되돌려 보내도(편집 모달의 실제 동작) 거짓 "
      "'관리자 이름 변경' 로그가 안 생긴다")
# ------------------------------------------------------------------
try:
    admin_c = _admin_client()
    r = admin_c.patch(f"/api/admins/{tid_a}",
                       json={"name": "김철수543", "role": "하위관리자"}, headers=H)
    rbody = r.get_json() or {}
    chk(r.status_code == 200 and rbody.get("ok") is True,
        "STEP PATCH /api/admins/<id> 가 200·ok:true 를 돌려준다", (r.status_code, rbody))

    conn = DB.get_db()
    row_a = conn.execute("SELECT role, name FROM admins WHERE id=?", (tid_a,)).fetchone()
    chk(row_a[0] == "하위관리자", "STEP 등급은 실제로 하위관리자로 바뀌었다", row_a[0])
    chk(row_a[1] == "김철수543", "STEP 이름 값 자체는 그대로다(같은 값 재저장)")

    n_name_log = _log_count(conn, "관리자 이름 변경", "target543a")
    chk(n_name_log == 0,
        "★★★★★ 지금 코드: 이름이 안 바뀌었으므로 '관리자 이름 변경' 로그가 "
        "0건이다(고치기 전엔 여기서 1건이 났다)", n_name_log)
    n_role_log = _log_count(conn, "관리자 등급 변경", "target543a")
    chk(n_role_log == 1,
        "STEP 등급 변경 로그는 정상적으로 1건 남는다(회귀 없음 — role 분기 무관)",
        n_role_log)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드543 [2] 지금 코드(등급만 변경)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[3] 원인 재현 — app.py·run_all_tests.py 는 건드리지 않고, 이번 "
      "수정 직전의 실제 함수 본문을 문자열로 재구성해(exec, round537과 같은 "
      "방식) 같은 시나리오를 실행하면 정말 거짓 로그가 남는가")
# ------------------------------------------------------------------
#  ⚠ 이 문자열은 이번 수정 **직전** 이 세션이 Read 로 확인한 api_admin_update
#    원문 그대로다(1748~1802행) — name 분기만 가드 없는 옛 형태다.
_PRE543_SRC = '''
def _api_admin_update_pre543(aid):
    d = body()
    conn = DB.get_db()
    conn.execute("BEGIN IMMEDIATE")
    a = one(conn.execute("SELECT * FROM admins WHERE id=?", (aid,)))
    if not a:
        conn.rollback(); conn.close()
        return jsonify({"ok": False, "error": "계정을 찾을 수 없습니다."}), 404

    result = {"ok": True}
    if "role" in d and d["role"] in ADMIN_ROLES and d["role"] != a["role"]:
        if a["role"] == "최고관리자" and d["role"] != "최고관리자":
            n_super = conn.execute(
                "SELECT COUNT(*) n FROM admins WHERE role='최고관리자'").fetchone()["n"]
            if n_super <= 1:
                conn.rollback(); conn.close()
                return jsonify({"ok": False,
                                "error": "마지막 최고관리자는 등급을 낮출 수 없습니다."}), 409
        conn.execute("UPDATE admins SET role=? WHERE id=?", (d["role"], aid))
        DB.log(conn, actor(), "관리자 등급 변경", f"{a['username']} {a['role']}→{d['role']}")
    if "name" in d and (d.get("name") or "").strip():
        new_name = (d["name"] or "").strip()[:40]
        conn.execute("UPDATE admins SET name=? WHERE id=?", (new_name, aid))
        DB.log(conn, actor(), "관리자 이름 변경", f"{a['username']} {a['name']}→{new_name}")
    if d.get("reset_pw"):
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
        while True:
            temp_pw = "".join(secrets.choice(alphabet) for _ in range(12))
            if (any(c.isupper() for c in temp_pw) and any(c.islower() for c in temp_pw)
                    and any(c.isdigit() for c in temp_pw)):
                break
        conn.execute("UPDATE admins SET password_hash=?, must_change_pw=1 WHERE id=?",
                     (DB.hash_pw(temp_pw), aid))
        DB.log(conn, actor(), "관리자 비밀번호 재발급", a["username"])
        result["temp_password"] = temp_pw
    conn.commit(); conn.close()
    return jsonify(result)
'''
try:
    _ns = dict(vars(A))              # app 모듈 네임스페이스 복사(진짜 모듈은 안 건드림)
    exec(compile(_PRE543_SRC, "<round543_pre_reconstructed>", "exec"), _ns)
    _old_update = _ns["_api_admin_update_pre543"]

    with A.app.test_request_context(f"/api/admins/{tid_b}", method="PATCH",
                                     json={"name": "박영희543", "role": "하위관리자"}):
        from flask import session as _flask_session
        _flask_session["admin"] = "admin543"
        _flask_session["admin_name"] = "실행계정543"
        _flask_session["admin_role"] = "최고관리자"
        resp = _old_update(tid_b)
    resp_obj = resp[0] if isinstance(resp, tuple) else resp
    chk(resp_obj is not None, "STEP 재구성한 옛 함수도 정상적으로 응답을 만든다")

    conn = DB.get_db()
    row_b = conn.execute("SELECT role FROM admins WHERE id=?", (tid_b,)).fetchone()
    chk(row_b[0] == "하위관리자",
        "STEP 옛 코드(재구성)도 등급은 그대로 바꾼다(겉보기 동작은 지금 코드와 "
        "똑같다 — 그래서 그동안 아무도 눈치 못 챘다)")
    n_old = _log_count(conn, "관리자 이름 변경", "target543b")
    chk(n_old == 1,
        "★★★★★ 그런데 옛 코드(재구성)는 이름이 전혀 안 바뀌었는데도 "
        "'관리자 이름 변경: 박영희543→박영희543' 거짓 로그를 1건 남긴다 "
        "— 지금 코드(위 [2])는 같은 시나리오에서 실제로 0건이었다. 이 차이가 "
        "이 회귀가 실제로 결함을 잡아낼 능력이 있다는 인과관계 증명이다", n_old)
    row_b_detail = conn.execute(
        "SELECT detail FROM activity_log WHERE action='관리자 이름 변경' "
        "AND detail LIKE 'target543b%'").fetchone()
    if row_b_detail:
        before, _, after = row_b_detail[0].partition("→")
        chk(before.strip().endswith("박영희543") and after.strip() == "박영희543",
            "STEP 거짓 로그의 old·new 가 문자 그대로 똑같다(진짜 '무변경 오탐')",
            row_b_detail[0])
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드543 [3] 원인 재현(옛 코드)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[4] 회귀 안전 — 이름이 진짜로 바뀌면 지금 코드도 정상적으로 "
      "'관리자 이름 변경' 로그를 정확한 old→new 로 남긴다(과잉교정 없음)")
# ------------------------------------------------------------------
try:
    admin_c2 = _admin_client()
    r2 = admin_c2.patch(f"/api/admins/{tid_c}",
                         json={"name": "이민수543-개명", "role": "하위관리자"}, headers=H)
    rbody2 = r2.get_json() or {}
    chk(r2.status_code == 200 and rbody2.get("ok") is True,
        "STEP PATCH 성공(이름 실제 변경 + 등급은 무변경)", (r2.status_code, rbody2))

    conn = DB.get_db()
    row_c = conn.execute("SELECT name FROM admins WHERE id=?", (tid_c,)).fetchone()
    chk(row_c[0] == "이민수543-개명", "STEP DB 의 이름이 실제로 바뀌었다", row_c[0])

    n_new = _log_count(conn, "관리자 이름 변경", "target543c")
    chk(n_new == 1,
        "★★★★ 회귀 안전: 진짜 이름 변경은 지금 코드에서도 정확히 1건 로그로 "
        "남는다(0건으로 과잉교정되지 않았다)", n_new)
    detail_row = conn.execute(
        "SELECT detail FROM activity_log WHERE action='관리자 이름 변경' "
        "AND detail LIKE 'target543c%'").fetchone()
    chk(bool(detail_row) and "이민수543" in detail_row[0] and "이민수543-개명" in detail_row[0],
        "STEP 로그 문구에 실제 old→new 가 정확히 담겨 있다", detail_row[0] if detail_row else None)
    n_role_log_c = _log_count(conn, "관리자 등급 변경", "target543c")
    chk(n_role_log_c == 0,
        "STEP 등급은 안 바뀌었으니 '관리자 등급 변경' 로그는 0건이다(교차오염 없음)",
        n_role_log_c)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드543 [4] 회귀 안전(진짜 이름 변경)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[5] 회귀 안전 — 이름·등급 둘 다 무변경으로 재저장하면 지금 코드는 "
      "아무 감사로그도 남기지 않는다(완전 무변경 no-op)")
# ------------------------------------------------------------------
try:
    admin_c3 = _admin_client()
    r3 = admin_c3.patch(f"/api/admins/{tid_d}",
                         json={"name": "최성훈543", "role": "하위관리자"}, headers=H)
    rbody3 = r3.get_json() or {}
    chk(r3.status_code == 200 and rbody3.get("ok") is True,
        "STEP 완전 무변경 재저장도 200·ok:true(에러 없이 조용히 통과)",
        (r3.status_code, rbody3))

    conn = DB.get_db()
    n_name_d = _log_count(conn, "관리자 이름 변경", "target543d")
    n_role_d = _log_count(conn, "관리자 등급 변경", "target543d")
    chk(n_name_d == 0 and n_role_d == 0,
        "★★★★ 완전 무변경이면 '이름 변경'·'등급 변경' 로그 모두 0건이다",
        {"name_log": n_name_d, "role_log": n_role_d})
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드543 [5] 회귀 안전(완전 무변경)", f"{type(e).__name__} {e}")


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
