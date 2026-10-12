# -*- coding: utf-8 -*-
"""스캔 421라운드 회귀 — _sub_update_impl()(app.py:3220-, 협력사·보험사 포털
   하위계정의 권한·상태·이름 변경 공용함수)의 DB.log 가 로그인아이디만 남기고
   "무엇이 바뀌었는지"(등급·상태의 이전값→새값)는 전혀 안 남겨, 형제 3곳
   (api_admin_update·api_partner_update·api_insurer_update — 전부 old→new 를
   명시)과 다른 관례를 쓰던 결함(정밀조사 Agent 발견 — 각도2: 고위험 작업
   감사로그 커버리지). require_portal_owner 로 이미 조직 최고관리자만 호출
   가능해 공격표면은 아니지만, 감사로그의 목적(정당한 권한자의 행위도 사후에
   설명 가능해야 함) 자체가 훼손된다.

   같은 수정으로 부수적 개선: 값이 실제로 안 바뀌어도 매번 UPDATE+로그를
   쏘던 것도, 형제와 같은 기준(실제 변경분만 반영)으로 맞췄다 — 새 조회
   불필요(row 에 이미 이전 값이 로드돼 있음), 새 정책 없음.

       python test_scan_round421_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(HERE, "app.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 421라운드 회귀 — 하위계정 변경 로그에 old→new 정보 누락")
print("=" * 72)

print("\n[1] 소스 확인")
_i0 = APP_SRC.index("def _sub_update_impl(")
_i1 = APP_SRC.index("\ndef ", _i0 + 1)
_body = APP_SRC[_i0:_i1]
chk('changes.append(f"등급 {row[' in _body,
    "★★★★★ _sub_update_impl() 이 등급 변경을 old→new 로 남긴다")
chk('changes.append(f"상태 {row[' in _body,
    "★★★★ 상태 변경도 old→new 로 남긴다")
chk('and d["role"] != row["role"]' in _body,
    "  실제로 값이 바뀔 때만 UPDATE 대상에 넣는다(형제와 같은 기준)")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round421_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO partners(name, login_id, password_hash, status, partner_type) "
                 "VALUES('R421원청사','r421org', ?, '활성','시공사')", (DB.hash_pw("orgpw123456"),))
    org_pid = conn.execute("SELECT id FROM partners WHERE login_id='r421org'").fetchone()["id"]
    conn.execute(
        "INSERT INTO portal_users(org_type,org_id,login_id,password_hash,name,role,status,"
        "must_change_pw,created_at) VALUES('partner',?,?,?,?,?,?,0,?)",
        (org_pid, "r421sub", DB.hash_pw("x"), "김대리", "하위관리자", "활성", DB.now()))
    sub_id = conn.execute("SELECT id FROM portal_users WHERE login_id='r421sub'").fetchone()["id"]
    conn.commit()

    def _owner_client():
        #  ⚠ require_portal_owner 는 portal_sub_id 가 없어야(=조직 최고관리자)
        #    통과한다 — 하위계정 세션이 아니라 원계정 세션으로 호출한다.
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["partner_id"] = org_pid; sess["partner_login"] = "r421org"
            sess["partner_name"] = "R421원청사"; sess["partner_type"] = "시공사"
            sess["pw_role"] = "partner"; sess["_csrf"] = "r421-csrf"
        return c

    print("\n[3] 실행 — 등급+상태 동시 변경 시 로그에 old→new 가 남는다")
    c1 = _owner_client()
    r1 = c1.patch(f"/api/partner/subaccounts/{sub_id}",
                  json={"role": "중간관리자", "status": "정지"},
                  headers={"X-CSRF-Token": "r421-csrf"})
    chk(r1.status_code == 200, "  변경 요청은 200으로 처리된다(회귀없음)",
        (r1.status_code, r1.get_json()))
    row_after = conn.execute("SELECT role, status FROM portal_users WHERE id=?",
                              (sub_id,)).fetchone()
    chk(row_after["role"] == "중간관리자" and row_after["status"] == "정지",
        "  실제로 DB 값이 바뀌었다(회귀없음)", dict(row_after))
    log = conn.execute(
        "SELECT detail FROM activity_log WHERE action='하위계정 변경' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    chk(log is not None and "등급 하위관리자→중간관리자" in log["detail"],
        "★★★★★ 감사로그에 등급 변경의 이전값→새값이 남는다"
        "(고치기 전엔 로그인아이디만 남았다)", log["detail"] if log else None)
    chk(log is not None and "상태 활성→정지" in log["detail"],
        "★★★★★ 감사로그에 상태 변경의 이전값→새값도 함께 남는다",
        log["detail"] if log else None)

    print("\n[4] 실행 — 이미 같은 값으로 재요청하면 unchanged, 로그 노이즈 없음")
    _n_logs_before = conn.execute(
        "SELECT COUNT(*) c FROM activity_log WHERE action='하위계정 변경'").fetchone()["c"]
    c2 = _owner_client()
    r2 = c2.patch(f"/api/partner/subaccounts/{sub_id}",
                  json={"role": "중간관리자", "status": "정지"},
                  headers={"X-CSRF-Token": "r421-csrf"})
    chk(r2.status_code == 200 and r2.get_json().get("unchanged") is True,
        "★★★ 실제 변경이 없으면 unchanged:true 를 돌려준다(형제와 같은 기준)",
        r2.get_json())
    _n_logs_after = conn.execute(
        "SELECT COUNT(*) c FROM activity_log WHERE action='하위계정 변경'").fetchone()["c"]
    chk(_n_logs_after == _n_logs_before,
        "  변경이 없으면 새 감사로그도 안 남는다(고치기 전엔 매번 로그가 쌓였다)",
        (_n_logs_before, _n_logs_after))

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 되돌리기 — 옛 코드로 되돌리면 old→new 정보가 사라지는가")
# ------------------------------------------------------------
#  ⚠⚠ [라운드619] on-disk 되돌리기(파일에 직접 쓰고 subprocess)를 인메모리로
#    이관 — _sub_update_impl() 은 라우트가 아니라 두 얇은 라우트 래퍼
#    (api_insurer_subaccount_update·api_partner_subaccount_update, app.py
#    3739·3769행 부근)가 "바로 이름으로" 부르는 평범한 모듈함수다.
#    view_functions 치환(기법1)은 래퍼 자신을 안 바꾸니 소용없고, 실 모듈
#    딕셔너리(vars(A) — 사본이 아니라 그 자체)에 되돌린 함수를 직접 exec해
#    이름을 갈아치워야(기법3) 두 래퍼가 호출할 때 바뀐 버전을 찾는다.

OLD_BLOCK = '''    sets, vals = [], []
    if d.get("role") in ("중간관리자", "하위관리자"):
        sets.append("role=?"); vals.append(d["role"])
    if d.get("status") in ("활성", "정지"):
        sets.append("status=?"); vals.append(d["status"])
    if d.get("name") is not None:
        sets.append("name=?"); vals.append((d.get("name") or "").strip()[:40])
    if not sets:
        conn.rollback(); conn.close(); return jsonify({"ok": True, "unchanged": True})
    vals.append(uid)
    conn.execute(f"UPDATE portal_users SET {','.join(sets)} WHERE id=?", vals)
    who = session.get("insurer_name") if kind == "insurer" else session.get("partner_name")
    DB.log(conn, who, "하위계정 변경", f"{row['login_id']}")'''

try:
    _new_body = APP_SRC[APP_SRC.index("def _sub_update_impl("):
                         APP_SRC.index("\ndef ", APP_SRC.index("def _sub_update_impl(") + 1)]
    _start_marker = '    sets, vals, changes = [], [], []'
    _end_marker = 'DB.log(conn, who, "하위계정 변경", f"{row[\'login_id\']} (" + ", ".join(changes) + ")")'
    _s = _new_body.index(_start_marker)
    _e = _new_body.index(_end_marker) + len(_end_marker)
    new_segment = _new_body[_s:_e]
    chk(APP_SRC.count(new_segment) == 1, "  (준비) 되돌리기 대상 텍스트가 유일하게 식별된다")
    reverted_fn_src = _new_body.replace(new_segment, OLD_BLOCK)
    chk(reverted_fn_src != _new_body, "  (준비) 되돌리기 텍스트가 실제로 달라졌다")

    #  vars(A)는 사본이 아니라 실 모듈 딕셔너리 그 자체 — 여기 exec하면 두
    #  라우트 래퍼가 바라보는 전역에서 바로 이 이름이 바뀐다(기법3).
    _real_ns = vars(A)
    _orig_fn = _real_ns["_sub_update_impl"]
    exec(compile(reverted_fn_src, "<round421_reverted:_sub_update_impl>", "exec"), _real_ns)  # noqa: S102 -- 우리 소스 그대로 추출, 디스크 미기록
    try:
        conn2 = DB.get_db()
        conn2.execute("INSERT INTO partners(name, login_id, password_hash, status, partner_type) "
                      "VALUES('R421원청사구','r421orgold', ?, '활성','시공사')",
                      (DB.hash_pw("orgpw123456"),))
        org_pid2 = conn2.execute(
            "SELECT id FROM partners WHERE login_id='r421orgold'").fetchone()["id"]
        conn2.execute(
            "INSERT INTO portal_users(org_type,org_id,login_id,password_hash,name,role,status,"
            "must_change_pw,created_at) VALUES('partner',?,?,?,?,?,?,0,?)",
            (org_pid2, "r421subold", DB.hash_pw("x"), "김대리", "하위관리자", "활성", DB.now()))
        sub_id2 = conn2.execute(
            "SELECT id FROM portal_users WHERE login_id='r421subold'").fetchone()["id"]
        conn2.commit()

        c_old = A.app.test_client()
        with c_old.session_transaction() as sess:
            sess["partner_id"] = org_pid2; sess["partner_login"] = "r421orgold"
            sess["partner_name"] = "R421원청사구"; sess["partner_type"] = "시공사"
            sess["pw_role"] = "partner"; sess["_csrf"] = "r421-old-csrf"
        r_old = c_old.patch(f"/api/partner/subaccounts/{sub_id2}",
                             json={"role": "중간관리자", "status": "정지"},
                             headers={"X-CSRF-Token": "r421-old-csrf"})
        chk(r_old.status_code == 200, "  (되돌린 코드도) 요청 자체는 200으로 처리된다",
            r_old.status_code)
        log_old = conn2.execute(
            "SELECT detail FROM activity_log WHERE action='하위계정 변경' "
            "ORDER BY id DESC LIMIT 1").fetchone()
        chk(log_old is not None and "등급" not in log_old["detail"],
            "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림)는 감사로그에 등급/상태 변경 "
            "정보가 전혀 안 남는다(인과관계 직접증명 — 로그인아이디만 남음)",
            log_old["detail"] if log_old else None)
        conn2.close()
    finally:
        _real_ns["_sub_update_impl"] = _orig_fn
    chk(A._sub_update_impl is _orig_fn, "  _sub_update_impl 이 원래 함수객체로 복원됐다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기 실행", f"{type(e).__name__} {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py는 이 되돌림-증명 내내 디스크에서 전혀 건드려지지 않았다")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
