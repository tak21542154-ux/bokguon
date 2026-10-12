# -*- coding: utf-8 -*-
"""스캔 430라운드 회귀 — api_partner_invite() 의 notify() 호출에 SAVEPOINT
   방어 추가(형제 api_partner_bulk_credentials·round199 와 같은 이유), 1건.

   정밀조사 Agent(각도2: 대량작업 부분실패 처리)가 발견 — 이 앱은 요청당
   커넥션을 추적해 예외 시 전체 롤백하는 전역 안전망(app.py:347-389)이 있어
   "일부만 조용히 커밋되는" 사고는 안 나지만, 그 대가로 "배치 하나가 인프라성
   예외로 전부 취소"되는 가용성 문제가 생긴다. 형제 api_partner_bulk_
   credentials(app.py:7738-, round199)는 이미 SAVEPOINT 로 업체별 실패를
   격리해 나머지 배치를 살리는데, api_partner_invite()(app.py:19277-)만
   notify() 호출에 이 방어가 없어 그 안의 무방비 INSERT(app.py:1837-1843,
   notify() 자신의 다른 두 하위쿼리는 이미 try/except sqlite3.Error 로
   방어돼 있는데 최종 INSERT 만 안 그렇다)가 예외를 던지면 이미 처리된
   다른 업체들의 invited_at 표시까지 전부 취소되고, 호출자는 marked/skipped
   세부 내역 없이 500 만 받았다.

   심각도는 낮음(공격자가 트리거 불가, 데이터 정합성 훼손 없음 — 전역
   안전망이 이미 그건 막아 준다. 순수하게 드문 인프라 장애 시 배치 전체가
   불필요하게 재시도 대상이 되는 가용성 문제) — 트레이드오프 없는 "그냥
   고치면 되는 것"으로 분류, 형제와 완전히 같은 SAVEPOINT 관용구를 그대로
   이식.

       python test_scan_round430_fixes.py
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
print("  스캔 430라운드 회귀 — api_partner_invite() notify() SAVEPOINT 방어")
print("=" * 72)

print("\n[1] 소스 확인")
_i0 = APP_SRC.index("def api_partner_invite():")
_i1 = APP_SRC.index("\n@app.", _i0 + 1)
_inv_body = APP_SRC[_i0:_i1]
chk('conn.execute("SAVEPOINT invite_notify")' in _inv_body,
    "★★★★★ api_partner_invite() 가 notify() 호출을 SAVEPOINT 로 감싼다")
chk('conn.execute("ROLLBACK TO SAVEPOINT invite_notify")' in _inv_body,
    "★★★★ 실패 시 그 업체 몫만 되돌린다")
_i_live = _inv_body.find("if live and")
_i_mark = _inv_body.find("UPDATE partners SET invited_at")
chk(0 < _i_live < _i_mark,
    "  기존 불변조건(발송분기가 표시UPDATE보다 앞) 유지됨"
    "(test_feature_onboarding.py 회귀 방지 확인)")
chk('"계정이 아직 없습니다"' in _inv_body,
    "  기존 skip 메시지 문구 유지됨(test_feature_onboarding.py 회귀 방지 확인)")

print("\n[2] 실행 준비 — 스크래치 DB + 발송 스위치 ON(팝빌은 모의 처리)")
_tmpdir = tempfile.mkdtemp(prefix="round430_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
os.environ["BOKGUON_NOTIFY_ENABLED"] = "1"      # import 시점에 한 번만 읽히므로 import 전에 설정
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A
    A.POPBILL.ready = lambda: True              # 실SDK/키 없이 live=True 만 만든다
    chk(A.NOTIFY_ENABLED is True, "  (준비) NOTIFY_ENABLED 가 실제로 켜졌다")

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','하위관리자')")
    pid1 = conn.execute(
        "INSERT INTO partners(name,login_id,password_hash,status,partner_type,phone) "
        "VALUES('R430성공업체','r430p1','x','활성','시행사','010-1111-2222')").lastrowid
    pid2 = conn.execute(
        "INSERT INTO partners(name,login_id,password_hash,status,partner_type,phone) "
        "VALUES('R430실패업체','r430p2','x','활성','시행사','010-3333-4444')").lastrowid
    conn.commit()

    admin = A.app.test_client()
    _tok = "r430-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "하위관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    hdr = {"X-CSRF-Token": _tok}

    #  ⚠ notify() 를 그대로 두되 특정 대상(target=업체명)일 때만 실패하게
    #    감싼다 — round414 의 "결정론적 프록시로 확률적/드문 결함을 재현" 기법.
    _orig_notify = A.notify

    def _fake_notify(conn, ntype, channel, target, message, **kw):
        if target == "R430실패업체":
            raise RuntimeError("R430 강제 실패(테스트 전용)")
        return _orig_notify(conn, ntype, channel, target, message, **kw)

    A.notify = _fake_notify
    try:
        print("\n[3] 실행 — 두 업체 동시 처리, 한 곳만 notify() 가 예외를 던진다")
        r = admin.post("/api/partners/invite", json={"ids": [pid1, pid2]}, headers=hdr)
        chk(r.status_code == 200,
            "★★★★★ 한 업체의 발송 실패가 전체 요청을 500으로 죽이지 않는다"
            "(고치기 전엔 이 요청 자체가 500 이었다)", (r.status_code, r.get_json()))
        j = r.get_json() or {}
        marked_ids = [m["id"] for m in (j.get("marked") or [])]
        skipped_map = {s["id"]: s.get("why") for s in (j.get("skipped") or [])}
        chk(pid1 in marked_ids, "★★★★ 정상 처리된 업체는 marked 에 남는다", j)
        chk(skipped_map.get(pid2) == "안내 발송 중 오류",
            "★★★★★ 실패한 업체는 정확한 사유와 함께 skipped 에 남는다"
            "(고치기 전엔 이 구분 자체가 응답에 없었다 — 500만 받았다)", j)
    finally:
        A.notify = _orig_notify

    print("\n[4] 실행 — DB 상태로 재확인: 성공 업체는 실제로 표시되고, 실패 업체는 안 됐다")
    row1 = conn.execute("SELECT invited_at FROM partners WHERE id=?", (pid1,)).fetchone()
    row2 = conn.execute("SELECT invited_at FROM partners WHERE id=?", (pid2,)).fetchone()
    chk(row1["invited_at"] is not None,
        "★★★★★ 성공한 업체는 invited_at 이 실제로 찍혔다(부분성공이 보존된다)",
        dict(row1))
    chk(row2["invited_at"] is None,
        "  실패한 업체는 invited_at 이 안 찍혔다(재시도 가능한 상태로 남음)",
        dict(row2))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 되돌리기 — 옛 코드(SAVEPOINT 없음)였다면 둘 다 취소됐는가")
# ------------------------------------------------------------
NEW_BLOCK = '''        if live and (p["phone"] or "").strip() and not p["so"]:
            #  ⚠ 종류 이름은 **탭 표에 있는 것**이어야 한다. 표에 없으면 폴백으로
            #    떨어져 알림과 무관한 화면이 열린다(partner_portal.html NOTI_TAB).
            #  ⚠⚠ [430라운드] 형제(api_partner_bulk_credentials, round199)와 같은
            #    이유로 SAVEPOINT — notify() 가 예외를 던지면(순수 인프라성 원인)
            #    이 요청이 연 커넥션 전체가 전역 안전망(err_500)에 롤백돼, 이미
            #    앞서 처리된 다른 업체들의 invited_at 표시까지 통째로 취소된다.
            conn.execute("SAVEPOINT invite_notify")
            try:
                notify(conn, "계정안내", "알림톡", p["name"],
                       f"{p['name']}님, 복구온 협력사 포털 계정이 준비되었습니다. "
                       f"아이디 {p['login_id']} 로 로그인해 공고를 확인해 주세요.",
                       audience_type="partner", partner_id=pid)
            except Exception:                                    # noqa: BLE001
                conn.execute("ROLLBACK TO SAVEPOINT invite_notify")
                app.logger.exception("협력사 안내 발송 실패: #%s", pid)
                skipped.append({"id": pid, "name": p["name"], "why": "안내 발송 중 오류"})
                continue
            conn.execute("RELEASE SAVEPOINT invite_notify")
            sent += 1'''
OLD_BLOCK = '''        if live and (p["phone"] or "").strip() and not p["so"]:
            #  ⚠ 종류 이름은 **탭 표에 있는 것**이어야 한다. 표에 없으면 폴백으로
            #    떨어져 알림과 무관한 화면이 열린다(partner_portal.html NOTI_TAB).
            notify(conn, "계정안내", "알림톡", p["name"],
                   f"{p['name']}님, 복구온 협력사 포털 계정이 준비되었습니다. "
                   f"아이디 {p['login_id']} 로 로그인해 공고를 확인해 주세요.",
                   audience_type="partner", partner_id=pid)
            sent += 1'''


#  ⚠⚠ [라운드619] on-disk 되돌리기(파일에 직접 쓰고 subprocess)를 인메모리로
#    이관 — api_partner_invite() 는 @require_role 데코레이터가 달린 단일
#    Flask 라우트 핸들러라 A.app.view_functions 딕셔너리 항목만 잠깐
#    치환한다(기법1). 되돌린 함수는 사본 이름공간(dict(vars(A)))에 exec해
#    만들고, 실 모듈의 A.require_role 로 다시 감싸 인증 동작은 그대로
#    유지한다. notify() 실패 모의는 [3]과 같은 결정론적 프록시 기법(round414)
#    을 새 업체 쌍에 다시 건다.


def _ast_fn_src(src, fn_name):
    """ast로 함수의 정확한 경계(decorator 제외, def~마지막 줄)를 뽑는다."""
    import ast
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            return "".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError(f"함수 {fn_name} 을 못 찾음")


try:
    _invite_src = _ast_fn_src(APP_SRC, "api_partner_invite")
    chk(_invite_src.count(NEW_BLOCK) == 1,
        "  (준비) 되돌리기 대상 텍스트가 함수 본문 안에 유일하게 식별된다")
    reverted_invite_src = _invite_src.replace(NEW_BLOCK, OLD_BLOCK)
    chk(reverted_invite_src != _invite_src, "  (준비) 되돌리기 텍스트가 실제로 달라졌다")

    #  ⚠ 위 [4]가 이미 conn.close()를 했다 — 이 섹션은 새 커넥션·새 업체쌍을 쓴다.
    conn2 = DB.get_db()
    pid1b = conn2.execute(
        "INSERT INTO partners(name,login_id,password_hash,status,partner_type,phone) "
        "VALUES('R430성공업체구','r430p1b','x','활성','시행사','010-1111-2222')").lastrowid
    pid2b = conn2.execute(
        "INSERT INTO partners(name,login_id,password_hash,status,partner_type,phone) "
        "VALUES('R430실패업체구','r430p2b','x','활성','시행사','010-3333-4444')").lastrowid
    conn2.commit()

    #  ⚠ _ns 는 vars(A)의 "사본"이라 exec 이후에 A.notify 를 바꿔도 반영이
    #    안 된다 — 되돌린 함수가 bare-name 으로 부르는 notify 자체를 사본
    #    안에서 먼저 가짜로 바꿔치기한 뒤에 exec 해야 한다.
    _ns = dict(vars(A))

    def _fake_notify2(conn, ntype, channel, target, message, **kw):
        if target == "R430실패업체구":
            raise RuntimeError("R430 강제 실패(테스트 전용)")
        return A.notify(conn, ntype, channel, target, message, **kw)

    _ns["notify"] = _fake_notify2
    exec(compile(reverted_invite_src, "<round430_reverted:api_partner_invite>", "exec"), _ns)  # noqa: S102 -- 우리 소스 그대로 추출, 디스크 미기록
    old_invite_fn = A.require_role("하위관리자")(_ns["api_partner_invite"])

    _orig_view = A.app.view_functions["api_partner_invite"]
    A.app.view_functions["api_partner_invite"] = old_invite_fn
    try:
        r_old = admin.post("/api/partners/invite", json={"ids": [pid1b, pid2b]}, headers=hdr)
    finally:
        A.app.view_functions["api_partner_invite"] = _orig_view

    row1b = conn2.execute("SELECT invited_at FROM partners WHERE id=?", (pid1b,)).fetchone()
    chk(r_old.status_code == 500 and row1b["invited_at"] is None,
        "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림)는 한 업체 발송실패로 전체 요청이 "
        "500이 되고, 이미 처리됐어야 할 다른 업체의 표시까지 통째로 취소된다"
        "(인과관계 직접증명)", (r_old.status_code, dict(row1b)))
    chk(A.app.view_functions["api_partner_invite"] is _orig_view,
        "  view_functions가 원래 함수객체로 복원됐다")
    conn2.close()
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
