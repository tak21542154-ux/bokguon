# -*- coding: utf-8 -*-
"""스캔 592라운드 회귀 — 콘솔 알림 읽음처리(POST /api/admin/notifications/read)가
id 를 숫자로 못 바꾸는 값(문자열·객체·배열 등, 극단값 입력)으로 받으면
int(d["id"]) 가 ValueError/TypeError 를 던지는데, 이 함수의 except 는
sqlite3.Error 만 잡아서 그대로 새 나가 500(SERVER_ERROR)이 되던 결함.

  형제(10657행 api_case_update 의 warranty_months, 18037행 api_dispatch_assign
  의 partner_id 등 이 파일 전체가 쓰는 압도적 다수 관례)는 전부 int() 를
  try/except(TypeError,ValueError) 로 감싸 친절한 400 을 돌려주는데 이 자리만
  빠져 있었다(이 파일에서 int(d["something"]) 형태로 직접 캐스팅하는 단 두
  자리 중 유일한 예외). BEGIN IMMEDIATE(쓰기 잠금)를 열기 전에 미리 파싱·
  검증하도록 옮겼다.

  (참고: 예외가 새 나가도 전역 err_500 핸들러(1291행)가 이 요청의 커넥션을
  전부 rollback+close 하므로 쓰기 잠금이 눌러붙지는 않는다 — 실측으로도
  아래 [3]에서 확인. 즉 이번 결함은 잠금 누수가 아니라 "친절한 400 대신
  불필요한 500 + 로그 소음"이라는 견고성 문제다. 그래도 이 파일 자신의
  거의 유일한 예외 지점이라 형제 관례에 맞춘다.)

      python test_scan_round592_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 592라운드 회귀 — 콘솔 알림 읽음처리의 id 파싱이 400 대신 500을 내던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def api_admin_notifications_read(")
i1 = APP_SRC.index("\n\n\n", i0)
fn_body = APP_SRC[i0:i1]
#  ⚠ [라운드652] round652가 이 함수의 except 튜플에 OverflowError를 추가로 얹었다
#    (1e400→float('inf')→int()가 ValueError 아닌 OverflowError를 낸다는 형제 결함,
#    round631과 같은 처방). 이 검사가 확인하려던 것은 "이 except가 TypeError·
#    ValueError를 잡는다"는 사실 자체이지 튜플 원소 개수가 아니므로, 검증 의도는
#    그대로 두고 지금 실제로 있는(더 넓어진) 문자열로만 갱신한다(표준지침 4항).
EXC_TUPLE = "except (TypeError, ValueError, OverflowError):"
chk(EXC_TUPLE in fn_body,
    "★★★★ id 파싱이 이제 TypeError/ValueError(+round652: OverflowError)를 잡는다")
chk(fn_body.index(EXC_TUPLE) < fn_body.index("conn = DB.get_db()"),
    "★★★★ 검증이 BEGIN IMMEDIATE(쓰기 잠금)보다 먼저 — 트랜잭션을 열기 전에 끝난다")
chk('int(d["id"])' in fn_body, "int(d[\"id\"]) 호출 자체는 그대로 남아있다(같은 로직, 자리만 이동)")

# ============================================================
print("\n[2] 준비 — 스크래치 DB + 관리자 세션")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round592_")
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
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r592admin','x','검증','최고관리자')")

    def mk_notif():
        return conn.execute(
            "INSERT INTO notifications(ntype,channel,target,message,status,"
            "audience_type,is_demo,created_at) "
            "VALUES('보안','웹','운영팀','R592 알림','전달됨','admin',0,?)",
            (DB.now(),)).lastrowid

    n1 = mk_notif()
    conn.commit()

    admin_c = A.app.test_client()
    atok = "r592-admin-csrf"
    with admin_c.session_transaction() as sess:
        sess["admin"] = "r592admin"
        sess["admin_role"] = "최고관리자"
        sess["_csrf"] = atok
    ahdr = {"X-CSRF-Token": atok}

    def read_at(nid):
        row = conn.execute("SELECT read_at FROM notifications WHERE id=?", (nid,)).fetchone()
        return row["read_at"] if row else None

    # ============================================================
    print("\n[3] 실행 — 지금 코드: 극단값 id는 500이 아니라 깔끔한 400")
    # ------------------------------------------------------------
    BAD_IDS = ("abc", "12.5", "1e10", [1, 2], {"x": 1}, "9" * 5000)
    for bad in BAD_IDS:
        r = admin_c.post("/api/admin/notifications/read", json={"id": bad}, headers=ahdr)
        label = str(bad)[:40]
        chk(r.status_code == 400,
            f"★★★★★ id={label!r} → 500이 아니라 400", r.status_code)
        j = r.get_json() or {}
        chk(j.get("ok") is False and j.get("code") != "SERVER_ERROR",
            f"  id={label!r} 응답이 전역 err_500(SERVER_ERROR)이 아니라 이 함수 자신의 400", j)

    chk(read_at(n1) is None,
        "★★★ 잘못된 id 요청들이 반복돼도 정상 알림(n1)의 read_at 은 그대로 NULL"
        "(엉뚱한 행에 영향 없음)")

    # 양성대조 — 정수 id는 그대로 동작(과잉차단 아님)
    r_ok = admin_c.post("/api/admin/notifications/read", json={"id": n1}, headers=ahdr)
    chk(r_ok.status_code == 200 and r_ok.get_json().get("ok") is True,
        "양성대조 — 정수 id는 여전히 200/ok", r_ok.get_json())
    chk(read_at(n1) is not None, "  실제로 read_at 이 채워졌다(엔진 자체는 안 죽었다)")

    n2 = mk_notif()
    conn.commit()
    r_ok2 = admin_c.post("/api/admin/notifications/read", json={"id": str(n2)}, headers=ahdr)
    chk(r_ok2.status_code == 200 and r_ok2.get_json().get("ok") is True,
        '양성대조 — 숫자로만 된 문자열 id("5" 등)도 여전히 200/ok(기존 클라이언트 호환)')
    chk(read_at(n2) is not None, "  실제로 read_at 이 채워졌다")

    # 잘못된 값 뒤에도 서버가 계속 정상 응답 — 쓰기 잠금이 눌러붙지 않는다
    n3 = mk_notif()
    conn.commit()
    admin_c.post("/api/admin/notifications/read", json={"id": "broken-again"}, headers=ahdr)
    r_after = admin_c.post("/api/admin/notifications/read", json={"id": n3}, headers=ahdr)
    chk(r_after.status_code == 200 and r_after.get_json().get("ok") is True,
        "★★★ 잘못된 요청 직후에도 다음 정상 요청이 곧바로 200(쓰기 잠금이 안 눌러붙었다)")

    # ============================================================
    print("\n[4] 인과관계 증명 — 되돌린(옛) 버전을 view_functions 에 임시 이식")
    # ------------------------------------------------------------
    #  ⚠ 실제 on-disk app.py 는 절대 건드리지 않는다 — 인메모리 exec() 로 옛
    #    함수 객체만 만들어 A.app.view_functions 에 잠깐 꽂았다가 finally 로
    #    되돌린다(round565 의 test_scan_round565_fixes.py 가 쓴 것과 같은 기법).
    OLD_ROUTE_SRC = '''
def api_admin_notifications_read():
    """읽음 처리 — id 를 주면 1건, 없으면 전체."""
    d = body()
    conn = DB.get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if d.get("id"):
            conn.execute(
                f"UPDATE notifications SET read_at=? WHERE id=? AND {ADMIN_OWN_SQL} "
                " AND read_at IS NULL", (DB.now(), int(d["id"])))
        else:
            conn.execute(
                f"UPDATE notifications SET read_at=? WHERE {ADMIN_OWN_SQL} AND read_at IS NULL",
                (DB.now(),))
        conn.commit()
        return jsonify({"ok": True})
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()
'''
    _ns = {}
    exec(compile(OLD_ROUTE_SRC, "<round592-reverted:api_admin_notifications_read>", "exec"),
         A.__dict__, _ns)
    OLD_RAW_FN = _ns["api_admin_notifications_read"]
    OLD_VIEW = A.require_admin(OLD_RAW_FN)
    NEW_VIEW = A.app.view_functions["api_admin_notifications_read"]   # 원상복구용으로 미리 쥔다

    try:
        A.app.view_functions["api_admin_notifications_read"] = OLD_VIEW
        r_old = admin_c.post("/api/admin/notifications/read", json={"id": "abc"}, headers=ahdr)
        chk(r_old.status_code == 500,
            "★★★★★★ 되돌린(옛) 버전은 실제로 재현된다 — 같은 잘못된 id가 500이 된다",
            (r_old.status_code, r_old.get_json()))
        chk((r_old.get_json() or {}).get("code") == "SERVER_ERROR",
            "  전역 err_500 핸들러가 받은 진짜 미처리 예외다(우리가 만든 400이 아니다)")

        # 옛 버전도 정상 숫자 id는 여전히 문제없이 동작 — 회귀 범위가 정확히
        # "잘못된 id" 하나뿐임을 확인한다(과대진단 아님).
        n4 = mk_notif()
        conn.commit()
        r_old_ok = admin_c.post("/api/admin/notifications/read", json={"id": n4}, headers=ahdr)
        chk(r_old_ok.status_code == 200 and r_old_ok.get_json().get("ok") is True,
            "  옛 버전도 정상 숫자 id는 그대로 200(회귀 범위가 정확히 이 결함 하나)")

        # 옛 버전 밑에서도 잠금이 눌러붙지 않는지(전역 err_500 안전망 확인) —
        # 500 직후 곧바로 이어지는 정상 요청이 지연 없이 성공해야 한다.
        n5 = mk_notif()
        conn.commit()
        admin_c.post("/api/admin/notifications/read", json={"id": "still-bad"}, headers=ahdr)
        r_old_after = admin_c.post("/api/admin/notifications/read", json={"id": n5}, headers=ahdr)
        chk(r_old_after.status_code == 200 and r_old_after.get_json().get("ok") is True,
            "  옛 버전에서도 500 직후 다음 요청이 곧바로 200(전역 err_500 의 rollback+close "
            "안전망 덕분 — 이번 결함이 '잠금 누수'는 아니었음을 확인)")
    finally:
        A.app.view_functions["api_admin_notifications_read"] = NEW_VIEW   # 실험 직후 즉시 원상복구

    # ============================================================
    print("\n[5] 원상복구 확인 — 실제 라이브 라우트로 다시 같은 요청을 보내면 400")
    # ------------------------------------------------------------
    r_fixed = admin_c.post("/api/admin/notifications/read", json={"id": "abc"}, headers=ahdr)
    chk(r_fixed.status_code == 400,
        "★★★★★★ 원상복구한 지금 버전은 같은 입력을 다시 400으로 막는다(500 재발 아님)",
        r_fixed.status_code)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드592 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
