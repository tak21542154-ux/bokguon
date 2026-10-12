# -*- coding: utf-8 -*-
"""스캔 546라운드 회귀 — 운영자 "내 계정"(마이페이지) 이름 저장(api_me_update,
   PATCH /api/me · app.py:1839 부근)이 이름이 하나도 안 바뀌어도 매번
   UPDATE+"내 정보 수정" 감사로그를 쏘던 결함.

   조사 배경 — 지시받은 신선한 각도들(카운트다운 반올림 전수확장·금액
   부동소수점·동시접속 오류메시지·예약취소 큐·알림채널 캐시)을 직접
   조사(하위위임 없음)했으나 전부 이미 안전했거나(카운트다운은 545가 마지막
   구멍을 막았고 VAT_RATE=10 이 하드코딩이라 부동소수점 반올림 불일치가
   수학적으로 발생 불가능·캠페인 취소는 507이 이미 이중클릭 가드 완비·
   알림 채널 on/off 설정 자체가 이 앱에 없음), 그러다 543·544 라운드가 이미
   고친 "값이 안 바뀌어도 UPDATE+로그를 쏘는" 패턴의 형제를 이 세션이
   직접 다시 훑다가 app.py:1839 api_me_update() 에서 발견 — 이 함수는
   543(api_admin_update 의 name 분기)·544(api_partner_profile_update ·
   api_insurer_profile_update) 가 정확히 같은 결함을 고치며 근거로 든
   "형제들" 목록에 들지 못한 **네 번째 형제**다: 543/544 는 "관리자가 다른
   계정을 고치는 자리"(api_admin_update)와 "협력사·보험사가 자기 마이페이지를
   고치는 자리" 둘을 훑었지만, "관리자가 **자기 자신**의 마이페이지를 고치는
   자리"(api_me_update, api_partner_profile_update·api_insurer_profile_update의
   직접 대응짝)는 그 훑기에서 빠져 있었다.

   실제 결함(수정 전) —
     conn = DB.get_db()
     conn.execute("UPDATE admins SET name=? WHERE username=?", (name, session.get("admin")))
     DB.log(conn, actor(), "내 정보 수정", f"이름 → {name}")
   새 이름이 옛 이름과 같은지 비교하는 코드가 전혀 없어, 제출된 이름이
   무엇이든 무조건 UPDATE 하고 로그를 남겼다.

   실사용 영향(추정이 아니라 프론트 코드로 확인) — admin.js 의 myAccount()
   (2961행)가 "내 계정" 모달을 열 때 #my_name 입력칸을 현재 이름
   (me.name, 2966행)으로 미리 채운다. saveMyName()(3072행)은 "이름 저장"
   버튼(비밀번호 변경과 별개의 독립 버튼, 2967행)을 누르면 그 입력칸 값을
   그대로 PATCH /api/me 로 보낸다 — 즉 운영자가 "내 계정" 모달을 열어
   아무것도 고치지 않고 "이름 저장"만 눌러도(비밀번호만 바꾸려다 실수로,
   또는 그냥 확인차) 예외 없이 거짓 "내 정보 수정: 이름 → 홍길동" 로그가
   남았다. 이 로그는 543 라운드가 지목한 _ADMIN_ACCOUNT_ACTIONS(민감 5행위)
   에는 안 속하지만, 감사로그 화면(전체 활동 로그)에는 그대로 노출돼
   "이 계정이 이름을 몇 번이나 바꿨는가"를 볼 때 실제로 없었던 변경을
   있었다고 우기는 잡음이 된다 — 543 이 지적한 것과 같은 성격의 신뢰 훼손이다.

   고침 — 새 정책·새 헬퍼 없이, 형제(api_admin_update 의 name 분기 1787행 ·
   api_partner_profile_update 3170행 · api_insurer_profile_update 3343행 ·
   _sub_update_impl 3390행)가 전부 쓰는 관례("새값 != 옛값일 때만 UPDATE+로그")를
   그대로 이식했다. api_me_update 는 이미 로드된 행이 없으므로(다른 세
   형제와 달리 자기 자신을 아이디로 조회할 뿐 앞선 SELECT * 가 없었다) 이름만
   담은 좁은 SELECT 를 하나 추가했다(app.py, `cur = one(conn.execute("SELECT
   name FROM admins WHERE username=?", ...))`) — 그 외 검증(빈 이름 400)·
   반환값·session 갱신·문구는 전혀 안 바꿨다.

   app.py 자신에 정의된 라우트 함수(api_me_update)를 고쳤다 — app.py 가
   import 하는 별도 .py 모듈이 아니다. 이미 떠 있는 프로세스가 있다면
   재시작해야 새 가드가 실제 요청에 반영된다(파이썬은 이미 임포트한 모듈을
   자동으로 다시 읽지 않는다).

      python test_scan_round546_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile

#  ⚠ 윈도 기본 콘솔은 cp949 라 em dash(—) 같은 문자를 print 하면
#    UnicodeEncodeError 로 죽는다 — 형제 테스트(round543·544·545 등)가
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
print("  스캔 546라운드 회귀 — 운영자 '내 계정' 이름 저장이 무변경이어도")
print("  매번 UPDATE+감사로그를 쏘던 결함 (api_me_update, PATCH /api/me)")
print("=" * 72)

APP_SRC = read("app.py")

# ==================================================================
print("\n[0] 소스 — 고친 지점이 실제로 app.py 에 있는가"
      "(동시편집 세션이 되돌렸다면 여기서부터 정직하게 실패해야 한다)")
# ------------------------------------------------------------------
try:
    import ast as _ast
    chk(_ast.parse(APP_SRC) is not None, "STEP app.py 전체 ast.parse 성공")

    me_body = _py_fn_body(APP_SRC, "api_me_update")
    chk('SELECT name FROM admins WHERE username=?' in me_body,
        "★★★★★ api_me_update() 에 이전 이름을 조회하는 SELECT 가 새로 생겼다"
        "(고치기 전엔 이 조회 자체가 아예 없었다)")
    chk('if name != ((cur or {}).get("name") or ""):' in me_body,
        "★★★★★ api_me_update() 에 이전값 비교 가드가 있다"
        "(고치기 전엔 이 줄이 없었다)")
    _i_select = me_body.index('SELECT name FROM admins WHERE username=?')
    _i_guard = me_body.index('if name != ((cur or {}).get("name") or ""):')
    _i_update = me_body.index('UPDATE admins SET name=?')
    _i_log = me_body.index('DB.log(conn, actor(), "내 정보 수정"')
    chk(_i_select < _i_guard < _i_update < _i_log,
        "★★★★ 순서가 옳다 — 이전이름 SELECT → 가드 → UPDATE → 로그"
        "(가드가 UPDATE·로그보다 먼저다)")
    #  그 외 로직(빈 이름 400·session 갱신·반환값)은 이번 라운드가 손대지
    #  않았다 — 그대로 남아 있는지 대조(과잉수정 없음).
    chk('이름은 비울 수 없습니다' in me_body,
        "STEP 형제(빈 이름 400 검증)는 이번 라운드가 손대지 않고 그대로다")
    chk('session["admin_name"] = name' in me_body,
        "STEP session 갱신 줄도 무수정으로 그대로 남아 있다(과잉수정 없음)")
    chk('return jsonify({"ok": True, "name": name})' in me_body,
        "STEP 반환값 형태도 무수정 그대로다({'unchanged':true} 류의 새 응답 "
        "필드를 추가하지 않았다 — 이 함수의 가장 가까운 형제인 "
        "api_admin_update 의 name 분기도 그런 필드를 안 돌려준다)")

    #  형제 셋(543·544가 고친 자리)도 이번 라운드가 훼손하지 않았는지 대조.
    au_body = _py_fn_body(APP_SRC, "api_admin_update")
    chk('if new_name != (a["name"] or ""):' in au_body,
        "STEP 형제 api_admin_update() 의 543 가드는 무수정으로 그대로다")
    pp_body = _py_fn_body(APP_SRC, "api_partner_profile_update")
    chk('if v == ((prev or {}).get(f) or ""):' in pp_body,
        "STEP 형제 api_partner_profile_update() 의 544 가드는 무수정으로 그대로다")
    ip_body = _py_fn_body(APP_SRC, "api_insurer_profile_update")
    chk('if v == ((prev or {}).get(f) or ""):' in ip_body,
        "STEP 형제 api_insurer_profile_update() 의 544 가드는 무수정으로 그대로다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드546 [0] 소스 확인", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[1] 준비 — 스크래치 DB, 관리자 3명(무변경재저장용·실변경용·"
      "구코드재현용)")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round546_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r546-csrf"
H = {"X-CSRF-Token": CSRF}
A = DB = None
NAME_A, NAME_C, NAME_B = "김철수546", "박영희546", "이민수546"


def _admin_client(username, admin_name):
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = username
        sess["admin_name"] = admin_name
        sess["admin_role"] = "하위관리자"
        sess["_csrf"] = CSRF
    return c


def _mk_admin(conn, username, name):
    cur = conn.execute(
        "INSERT INTO admins(username,password_hash,name,role) VALUES(?,?,?,?)",
        (username, "x", name, "하위관리자"))
    return cur.lastrowid


def _log_count(conn, action, admin_name_like):
    return conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE action=? AND actor LIKE ?",
        (action, admin_name_like + "%")).fetchone()[0]


try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    _mk_admin(conn0, "me546a", NAME_A)
    _mk_admin(conn0, "me546c", NAME_C)
    _mk_admin(conn0, "me546b", NAME_B)
    conn0.commit(); conn0.close()
    chk(True, "STEP 관리자 3명(me546a/c/b) 생성")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드546 [1] 준비", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[2] 실행(진짜 라우트, 지금 코드) — '내 계정' 모달이 실제로 보내는 "
      "것과 같은 payload(현재 이름 그대로, myAccount() 가 #my_name 을 미리 "
      "채우는 것과 같은 값)를 '이름 저장'으로 재전송해도 거짓 '내 정보 수정' "
      "로그가 안 생긴다")
# ------------------------------------------------------------------
try:
    ac = _admin_client("me546a", NAME_A)
    r = ac.patch("/api/me", json={"name": NAME_A}, headers=H)
    rbody = r.get_json() or {}
    chk(r.status_code == 200 and rbody.get("ok") is True and rbody.get("name") == NAME_A,
        "STEP PATCH /api/me 200·ok:true·name 그대로", (r.status_code, rbody))

    conn = DB.get_db()
    row_a = conn.execute("SELECT name FROM admins WHERE username=?", ("me546a",)).fetchone()
    chk(row_a[0] == NAME_A, "STEP DB 이름은 그대로다(같은 값 재저장)", row_a[0])
    n_log_a = _log_count(conn, "내 정보 수정", NAME_A)
    chk(n_log_a == 0,
        "★★★★★ 지금 코드: 이름이 안 바뀌었으므로 '내 정보 수정' 로그가 "
        "0건이다(고치기 전엔 매번 1건이 났다)", n_log_a)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드546 [2] 지금 코드(무변경 재저장)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[3] 회귀 안전 — 이름이 진짜로 바뀌면 지금 코드도 정상적으로 "
      "'내 정보 수정: 이름 → 새이름' 로그를 정확히 1건 남긴다(과잉교정 없음)")
# ------------------------------------------------------------------
try:
    cc = _admin_client("me546c", NAME_C)
    new_name_c = NAME_C + "-개명"
    r2 = cc.patch("/api/me", json={"name": new_name_c}, headers=H)
    rbody2 = r2.get_json() or {}
    chk(r2.status_code == 200 and rbody2.get("ok") is True and rbody2.get("name") == new_name_c,
        "STEP PATCH /api/me 성공(이름 실제 변경)", (r2.status_code, rbody2))

    conn = DB.get_db()
    row_c = conn.execute("SELECT name FROM admins WHERE username=?", ("me546c",)).fetchone()
    chk(row_c[0] == new_name_c, "STEP DB 이름이 실제로 바뀌었다", row_c[0])
    n_log_c = _log_count(conn, "내 정보 수정", NAME_C)
    chk(n_log_c == 1,
        "★★★★ 회귀 안전: 진짜 이름 변경은 지금 코드에서도 정확히 1건 로그로 "
        "남는다(0건으로 과잉교정되지 않았다)", n_log_c)
    detail_row = conn.execute(
        "SELECT detail FROM activity_log WHERE action='내 정보 수정' "
        "AND actor LIKE ? ORDER BY id DESC LIMIT 1", (NAME_C + "%",)).fetchone()
    chk(bool(detail_row) and detail_row[0] == f"이름 → {new_name_c}",
        "STEP 로그 문구에 실제 새 이름이 정확히 담겨 있다",
        detail_row[0] if detail_row else None)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드546 [3] 회귀 안전(진짜 이름 변경)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[4] 원인 재현 — app.py·run_all_tests.py 는 건드리지 않고, 이번 "
      "수정 직전의 실제 함수 본문을 문자열로 재구성해(exec, round543·544와 "
      "같은 방식) 완전히 손대지 않은 별도 관리자에게 같은 '무변경 재전송' "
      "시나리오를 실행하면 옛 코드는 정말 거짓 로그를 남기는가")
# ------------------------------------------------------------------
#  ⚠ 이 문자열은 이번 수정 **직전** 이 세션이 Read 로 확인한 api_me_update
#    원문 그대로다(1839~1852행) — 이전값 비교 가드가 없는 옛 형태다.
_PRE546_SRC = '''
def _api_me_update_pre546():
    d = body()
    name = (d.get("name") or "").strip()[:40]
    if not name:
        return jsonify({"ok": False, "error": "이름은 비울 수 없습니다."}), 400
    conn = DB.get_db()
    conn.execute("UPDATE admins SET name=? WHERE username=?", (name, session.get("admin")))
    DB.log(conn, actor(), "내 정보 수정", f"이름 → {name}")
    conn.commit(); conn.close()
    session["admin_name"] = name
    return jsonify({"ok": True, "name": name})
'''
try:
    _ns = dict(vars(A))              # app 모듈 네임스페이스 복사(진짜 모듈은 안 건드림)
    exec(compile(_PRE546_SRC, "<round546_pre_reconstructed>", "exec"), _ns)
    _old_update = _ns["_api_me_update_pre546"]

    with A.app.test_request_context("/api/me", method="PATCH", json={"name": NAME_B}):
        from flask import session as _flask_session
        _flask_session["admin"] = "me546b"
        _flask_session["admin_name"] = NAME_B
        _flask_session["admin_role"] = "하위관리자"
        resp = _old_update()
    resp_obj = resp[0] if isinstance(resp, tuple) else resp
    chk(resp_obj is not None, "STEP 재구성한 옛 함수도 정상적으로 응답을 만든다")

    conn = DB.get_db()
    row_b = conn.execute("SELECT name FROM admins WHERE username=?", ("me546b",)).fetchone()
    chk(row_b[0] == NAME_B,
        "STEP 옛 코드(재구성)도 값 자체는 그대로 저장한다(겉보기 동작은 지금 "
        "코드와 똑같다 — 그래서 그동안 아무도 눈치 못 챘다)")
    n_old = _log_count(conn, "내 정보 수정", NAME_B)
    chk(n_old == 1,
        "★★★★★ 그런데 옛 코드(재구성)는 완전히 손대지 않은 관리자에게 "
        "이름이 전혀 안 바뀐 payload를 그대로 재전송해도 '내 정보 수정: "
        f"이름 → {NAME_B}' 거짓 로그를 1건 남긴다 — 지금 코드(위 [2])는 같은 "
        "시나리오에서 실제로 0건이었다. 이 차이가 이 회귀가 실제로 결함을 "
        "잡아낼 능력이 있다는 인과관계 증명이다", n_old)
    detail_old = conn.execute(
        "SELECT detail FROM activity_log WHERE action='내 정보 수정' "
        "AND actor LIKE ? ORDER BY id DESC LIMIT 1", (NAME_B + "%",)).fetchone()
    chk(bool(detail_old) and detail_old[0] == f"이름 → {NAME_B}",
        "STEP 거짓 로그의 old·new 가 문자 그대로 똑같다(진짜 '무변경 오탐')",
        detail_old[0] if detail_old else None)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드546 [4] 원인 재현(옛 코드)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[5] 교차오염 없음 — [2]~[4] 세 관리자의 로그 집계가 서로 섞이지 "
      "않았다(actor 문자열로 정확히 분리됨)")
# ------------------------------------------------------------------
try:
    conn = DB.get_db()
    total = conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE action='내 정보 수정'").fetchone()[0]
    chk(total == 2,
        "★★★ 전체 '내 정보 수정' 로그는 정확히 2건([3]의 진짜 변경 1건 + "
        "[4]의 옛 코드 재현 1건 — [2]의 무변경 재저장은 0건이었다)", total)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드546 [5] 교차오염 없음", f"{type(e).__name__} {e}")


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
