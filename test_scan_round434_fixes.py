# -*- coding: utf-8 -*-
"""스캔 434라운드 회귀 — 사진 검수 승인 재호출 시 알림·감사로그 중복 +
   반려취소(unreject)의 확인~갱신 사이 경합 미방어, 2건.

   정밀조사 Agent(각도1: 사진 검수 워크플로 권한·상태전이)가 발견 —

   [1] api_photos_approve()(app.py:12316-)는 이번에 새로 승인된 장수
       (approved, UPDATE rowcount)가 0이어도 notify()·DB.log() 를 무조건
       실행했다 — 형제 api_photo_reject()는 이미 rowcount==0 이면 409로
       끝내 통지·로그 없이 종료하는데(반려된 사진 재반려 방지), 승인 쪽만
       재클릭·새로고침 후 재요청·2관리자 동시진행 시마다 협력사에게 중복
       알림톡이 나가고 감사로그에 "(이번 0장)" 줄이 계속 쌓였다.

   [2] api_photo_unreject()(app.py:12495-)는 BEGIN IMMEDIATE 도, UPDATE 의
       상태조건(WHERE review_status=...)도 없어(단순 WHERE id=?), 확인
       (review_status!='반려' 체크)과 갱신 사이가 잠기지 않은 TOCTOU였다.
       형제 api_photo_reject()는 이미 BEGIN IMMEDIATE + "WHERE id=? AND
       review_status<>'반려'"의 rowcount 가드로 이 문제를 올바르게 막고
       있다 — 같은 파일 안에 정답 패턴이 이미 있었다.

   고침: (a) approve 의 notify/log 를 `if approved:` 로 감싼다(형제 reject
   와 같은 "실제로 뭔가 바뀌었을 때만" 원칙). (b) unreject 에 형제와 동일한
   BEGIN IMMEDIATE + rowcount 가드를 추가한다. 둘 다 트레이드오프 없는
   "그냥 고치면 되는 것", 응답 계약은 그대로 유지.

   ⚠⚠ [라운드623] 되돌림-증명 기법을 옛 세대(app.py를 실제로 디스크에
      써넣고 서브프로세스를 새로 띄워 확인한 뒤 원본을 다시 디스크에 써
      복원)에서 round491/499가 확립한 기법1+2(ast로 함수 경계를 뽑아
      치환한 뒤 독립 사본 네임스페이스에 exec, view_functions 딕셔너리
      항목만 스왑)로 이관한다. 두 함수(api_photos_approve·api_photo_
      unreject)는 서로 안 부르고 다른 함수도 이 둘을 맨이름으로 안 불러
      (둘 다 라우트로만 호출됨) 각각 독립적으로 스왑할 수 있다 — 그룹
      네임스페이스(기법4)까지는 필요 없다. app.py는 이 테스트 실행
      내내 디스크에 다시 쓰이지 않고, 서브프로세스도 전혀 안 쓴다.
      같은 스크래치 DB를 공유하므로 절대 카운트 대신 호출 전후 델타로
      비교한다(원래 서브프로세스가 매번 완전히 새 DB로 0부터 세던 것과
      같은 판정력).

       python test_scan_round434_fixes.py
"""
import ast
import io
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(HERE, "app.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def _ast_fn_src(src, fn_name):
    """ast로 함수의 정확한 경계(decorator 제외, def~마지막 줄)를 뽑는다.
    (round499가 확립한 헬퍼)"""
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            return "".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError(f"함수 {fn_name} 을 못 찾음")


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 434라운드 회귀 — 사진검수 승인재호출 중복 + 반려취소 경합")
print("=" * 72)

print("\n[1] 소스 확인")
_i0 = APP_SRC.index("def api_photos_approve(cid):")
_i1 = APP_SRC.index("\n@app.", _i0 + 1)
_pa_body = APP_SRC[_i0:_i1]
chk("if approved:" in _pa_body,
    "★★★★★ api_photos_approve() 가 새로 승인된 장수(approved)==0 이면 "
    "notify/DB.log 를 건너뛴다")

_u0 = APP_SRC.index("def api_photo_unreject(pid):")
_u1 = APP_SRC.index("\n@app.", _u0 + 1)
_un_body = APP_SRC[_u0:_u1]
chk('conn.execute("BEGIN IMMEDIATE")' in _un_body,
    "★★★★★ api_photo_unreject() 가 이제 BEGIN IMMEDIATE 로 쓰기잠금을 잡는다")
chk("WHERE id=? AND review_status='반려'" in _un_body,
    "★★★★★ UPDATE 가 현재 상태(review_status='반려')까지 조건에 넣는다"
    "(형제 api_photo_reject 와 같은 rowcount 가드)")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round434_")
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
                 "VALUES('admin','x','검증','중간관리자')")
    iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R434보험사','활성')").lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,created_at) "
        "VALUES('R434업체','시공사','활성','가드레일','서울',?)", (DB.now(),)).lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,partner_id,created_at) "
        "VALUES('R434-CASE','시공중','가드레일','서울',?,?,?)", (iid, pid, DB.now())).lastrowid
    photo_id = conn.execute(
        "INSERT INTO photos(case_id,partner_id,rel_path,kind,review_status,uploader_role,"
        "                   created_at) "
        "VALUES(?,?,'r434.jpg','시공중','대기','협력사',?)", (cid, pid, DB.now())).lastrowid
    conn.commit()

    admin = A.app.test_client()
    _tok = "r434-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    hdr = {"X-CSRF-Token": _tok}

    def _notif_count():
        c = DB.get_db()
        n = c.execute(
            "SELECT COUNT(*) n FROM notifications WHERE ntype='사진검수'").fetchone()["n"]
        c.close()
        return n

    def _log_count(action):
        c = DB.get_db()
        n = c.execute(
            "SELECT COUNT(*) n FROM activity_log WHERE action=?", (action,)).fetchone()["n"]
        c.close()
        return n

    print("\n[3] 실행 — approve 재호출: 새로 승인된 장수가 0이면 통지·로그가 안 늘어난다")
    r1 = admin.post(f"/api/cases/{cid}/photos/approve", headers=hdr)
    chk(r1.status_code == 200 and r1.get_json().get("approved") == 1,
        "  첫 승인은 정상 처리된다(사진 1장)", r1.get_json())
    n1 = _notif_count(); l1 = _log_count("사진 검수 승인")
    chk(n1 == 1 and l1 == 1, "  (사전조건) 첫 승인으로 알림 1건·로그 1건이 생겼다", (n1, l1))

    r2 = admin.post(f"/api/cases/{cid}/photos/approve", headers=hdr)
    chk(r2.status_code == 200 and r2.get_json().get("approved") == 1,
        "  재호출도 200으로 응답한다(이미 승인된 장수는 그대로 보고, 과잉차단 아님)",
        r2.get_json())
    n2 = _notif_count(); l2 = _log_count("사진 검수 승인")
    chk(n2 == n1,
        "★★★★★ 재호출로는 알림톡이 추가로 안 나간다"
        "(고치기 전엔 재호출마다 협력사에게 중복 알림톡이 나갔다)", (n1, n2))
    chk(l2 == l1,
        "★★★★★ 재호출로는 감사로그도 추가로 안 쌓인다"
        "(고치기 전엔 '(이번 0장)' 줄이 재호출마다 쌓였다)", (l1, l2))

    print("\n[4] 실행 — unreject 동시경합: 실제 두 스레드가 같은 사진을 동시에 반려취소한다")
    conn.execute("UPDATE photos SET review_status='반려', reject_reason='테스트' WHERE id=?",
                 (photo_id,))
    conn.commit()

    results = {}
    errs = []

    def _worker(key):
        try:
            c = A.app.test_client()
            with c.session_transaction() as sess:
                sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"
                sess["admin_name"] = "검증"; sess["_csrf"] = _tok
            r = c.post(f"/api/photos/{photo_id}/unreject", headers=hdr)
            results[key] = (r.status_code, r.get_json())
        except Exception as e:                                     # noqa: BLE001
            errs.append(e)

    t1 = threading.Thread(target=_worker, args=("t1",))
    t2 = threading.Thread(target=_worker, args=("t2",))
    t1.start(); t2.start()
    t1.join(10); t2.join(10)

    chk(not errs, "★★★★★ 동시 반려취소 중 스레드에서 예외 없음(회귀없음)", errs)
    codes = sorted(v[0] for v in results.values())
    chk(codes == [200, 409],
        "★★★★★ 둘 중 정확히 하나만 성공(200)하고 나머지는 409로 거부된다"
        "(고치기 전엔 둘 다 200으로 성공할 수 있었다)", results)
    _log_n = _log_count("사진 반려 취소")
    chk(_log_n == 1,
        "★★★★★ 감사로그도 정확히 1건만 남는다(고치기 전엔 2건이 남을 수 있었다)",
        _log_n)

    # ============================================================
    print("\n[5] 되돌리기 — 옛 코드였다면 두 결함 다 재현되는가"
          " (뷰함수 딕셔너리 스왑 2건, 디스크 미기록·서브프로세스 미사용)")
    # ------------------------------------------------------------
    NEW_APPROVE_TAIL = '''    if approved:
        notify(conn, "사진검수", "알림톡", c["partner_name"],
               f"{c['case_no']} 시공 사진 {approved_total}장이 검수 승인되었습니다.",
               audience_type="partner", partner_id=c["partner_id"], case_id=cid,
               url="/app/partner")
        DB.log(conn, actor(), "사진 검수 승인", f"{c['case_no']} 승인 {approved_total}장 (이번 {approved}장)")
    conn.commit(); conn.close()
    return jsonify({"ok": True, "approved": approved_total})'''
    OLD_APPROVE_TAIL = '''    notify(conn, "사진검수", "알림톡", c["partner_name"],
           f"{c['case_no']} 시공 사진 {approved_total}장이 검수 승인되었습니다.",
           audience_type="partner", partner_id=c["partner_id"], case_id=cid,
           url="/app/partner")
    DB.log(conn, actor(), "사진 검수 승인", f"{c['case_no']} 승인 {approved_total}장 (이번 {approved}장)")
    conn.commit(); conn.close()
    return jsonify({"ok": True, "approved": approved_total})'''

    NEW_UNREJECT_TAIL = '''    conn.execute("BEGIN IMMEDIATE")
    p = one(conn.execute("SELECT * FROM photos WHERE id=?", (pid,)))
    if not p:
        conn.rollback(); conn.close()
        return jsonify({"ok": False, "error": "사진을 찾을 수 없습니다."}), 404
    if p["review_status"] != "반려":
        conn.rollback(); conn.close()
        return jsonify({"ok": False, "error": "반려된 사진이 아닙니다."}), 409
    cur = conn.execute(
        "UPDATE photos SET review_status='대기', reject_reason=NULL "
        "WHERE id=? AND review_status='반려'", (pid,))
    if not cur.rowcount:
        conn.rollback(); conn.close()
        return jsonify({"ok": False, "error": "반려된 사진이 아닙니다."}), 409
    DB.log(conn, actor(), "사진 반려 취소", f"#{pid}")
    conn.commit(); conn.close()
    return jsonify({"ok": True})'''
    #  ⚠ [437라운드] 배리어로 스레드 시작만 맞춰도 실측 배터리에서 들쭉날쭉함이
    #    나왔다 — 옛 코드의 무방비 구간 자체를 잠깐 늘려(check 와 update 사이
    #    0.2초) 실제 겹침을 강제한다. 이 지연은 되돌리기증명 전용 임시 사본
    #    함수에만 들어가고 실제 운영 코드에는 전혀 영향이 없다.
    OLD_UNREJECT_TAIL = '''    p = one(conn.execute("SELECT * FROM photos WHERE id=?", (pid,)))
    if not p:
        conn.close(); return jsonify({"ok": False, "error": "사진을 찾을 수 없습니다."}), 404
    if p["review_status"] != "반려":
        conn.close(); return jsonify({"ok": False, "error": "반려된 사진이 아닙니다."}), 409
    import time as _r437_time; _r437_time.sleep(0.2)
    conn.execute("UPDATE photos SET review_status='대기', reject_reason=NULL WHERE id=?", (pid,))
    DB.log(conn, actor(), "사진 반려 취소", f"#{pid}")
    conn.commit(); conn.close()
    return jsonify({"ok": True})'''

    # (a) api_photos_approve — 기법1+2
    APPROVE_BODY = _ast_fn_src(APP_SRC, "api_photos_approve")
    chk(APPROVE_BODY.count(NEW_APPROVE_TAIL) == 1,
        "  (준비) approve 되돌리기 대상이 함수 본문 안에 유일하게 있다")
    REVERTED_APPROVE = APPROVE_BODY.replace(NEW_APPROVE_TAIL, OLD_APPROVE_TAIL)
    chk(REVERTED_APPROVE != APPROVE_BODY, "  (준비) 되돌린 approve 본문이 실제로 달라졌다")
    _ns1 = dict(vars(A))
    exec(compile(REVERTED_APPROVE, "<round434_reverted_api_photos_approve>", "exec"), _ns1)  # noqa: S102
    old_approve = A.require_role("중간관리자")(_ns1["api_photos_approve"])
    _orig_approve_view = A.app.view_functions["api_photos_approve"]

    # (b) api_photo_unreject — 기법1+2
    UNREJECT_BODY = _ast_fn_src(APP_SRC, "api_photo_unreject")
    chk(UNREJECT_BODY.count(NEW_UNREJECT_TAIL) == 1,
        "  (준비) unreject 되돌리기 대상이 함수 본문 안에 유일하게 있다")
    REVERTED_UNREJECT = UNREJECT_BODY.replace(NEW_UNREJECT_TAIL, OLD_UNREJECT_TAIL)
    chk(REVERTED_UNREJECT != UNREJECT_BODY, "  (준비) 되돌린 unreject 본문이 실제로 달라졌다")
    _ns2 = dict(vars(A))
    exec(compile(REVERTED_UNREJECT, "<round434_reverted_api_photo_unreject>", "exec"), _ns2)  # noqa: S102
    old_unreject = A.require_role("중간관리자")(_ns2["api_photo_unreject"])
    _orig_unreject_view = A.app.view_functions["api_photo_unreject"]

    A.app.view_functions["api_photos_approve"] = old_approve
    A.app.view_functions["api_photo_unreject"] = old_unreject
    try:
        #  독립된 새 사건/사진으로 시나리오를 만들어 위 [3][4]의 판정과 섞이지
        #  않게 한다(같은 스크래치 DB를 공유하므로 절대 카운트 대신 호출
        #  전후 델타로 비교 — 원래 서브프로세스가 0부터 세던 것과 같은 판정력).
        cid2 = conn.execute(
            "INSERT INTO cases(case_no,status,category,region,insurer_id,partner_id,created_at) "
            "VALUES('R434-CASE-OLD','시공중','가드레일','서울',?,?,?)",
            (iid, pid, DB.now())).lastrowid
        conn.execute(
            "INSERT INTO photos(case_id,partner_id,rel_path,kind,review_status,uploader_role,"
            "                   created_at) "
            "VALUES(?,?,'r434_old.jpg','시공중','대기','협력사',?)",
            (cid2, pid, DB.now()))
        conn.commit()

        n_before = _notif_count(); l_before = _log_count("사진 검수 승인")
        r_old1 = admin.post(f"/api/cases/{cid2}/photos/approve", headers=hdr)
        chk(r_old1.status_code == 200 and r_old1.get_json().get("approved") == 1,
            "  (구코드) 첫 승인은 정상 처리된다(사진 1장)", r_old1.get_json())
        n_mid = _notif_count(); l_mid = _log_count("사진 검수 승인")
        chk(n_mid == n_before + 1 and l_mid == l_before + 1,
            "  (구코드, 사전조건) 첫 승인으로 알림·로그가 +1 늘었다", (n_before, n_mid, l_before, l_mid))

        r_old2 = admin.post(f"/api/cases/{cid2}/photos/approve", headers=hdr)
        chk(r_old2.status_code == 200,
            "  (구코드) 재호출도 200으로 응답한다", r_old2.get_json())
        n_after = _notif_count(); l_after = _log_count("사진 검수 승인")
        chk(n_after == n_mid + 1,
            "★★★★★ 옛 코드(뷰함수 스왑)는 재호출마다 알림이 실제로 또 나간다"
            "(인과관계 직접증명)", (n_mid, n_after))
        chk(l_after == l_mid + 1,
            "★★★★★ 옛 코드(뷰함수 스왑)는 재호출마다 감사로그도 또 쌓인다"
            "(인과관계 직접증명)", (l_mid, l_after))

        photo3_id = conn.execute(
            "INSERT INTO photos(case_id,partner_id,rel_path,kind,review_status,reject_reason,"
            "                   uploader_role,created_at) "
            "VALUES(?,?,'r434_old2.jpg','시공중','반려','테스트','협력사',?)",
            (cid2, pid, DB.now())).lastrowid
        conn.commit()
        l0 = _log_count("사진 반려 취소")

        old_results = {}
        old_errs = []

        def _old_worker(key):
            try:
                c = A.app.test_client()
                with c.session_transaction() as sess:
                    sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"
                    sess["admin_name"] = "검증"; sess["_csrf"] = _tok
                r = c.post(f"/api/photos/{photo3_id}/unreject", headers=hdr)
                old_results[key] = r.status_code
            except Exception as e:                                 # noqa: BLE001
                old_errs.append(e)

        ot1 = threading.Thread(target=_old_worker, args=("t1",))
        ot2 = threading.Thread(target=_old_worker, args=("t2",))
        ot1.start(); ot2.start()
        ot1.join(10); ot2.join(10)

        chk(not old_errs, "  (구코드) 동시 반려취소 중 스레드에서 예외 없음", old_errs)
        chk(sorted(old_results.values()) == [200, 200],
            "★★★★★ 옛 코드(뷰함수 스왑): 동시 반려취소 둘 다 200으로 성공한다"
            "(인과관계 직접증명)", old_results)
        l_final = _log_count("사진 반려 취소")
        chk(l_final == l0 + 2,
            "★★★★★ 옛 코드(뷰함수 스왑): 감사로그가 2건 늘어난다(중복기록, "
            "인과관계 직접증명)", (l0, l_final))
    finally:
        A.app.view_functions["api_photos_approve"] = _orig_approve_view
        A.app.view_functions["api_photo_unreject"] = _orig_unreject_view

    chk(A.app.view_functions["api_photos_approve"] is _orig_approve_view,
        "  api_photos_approve view_functions가 원래 함수객체로 복원됐다")
    chk(A.app.view_functions["api_photo_unreject"] is _orig_unreject_view,
        "  api_photo_unreject view_functions가 원래 함수객체로 복원됐다")

    #  원복 후 재확인 — 스왑이 안 샜는지(다시 새 코드처럼 재호출 시 알림이 안 느는지).
    #  cid/photo_id 는 [4]에서 이미 '반려'→(스레드 하나가) '대기'로 바뀌어 있어
    #  재사용하면 이번 approve가 "진짜 새 승인"이 되어 판정이 흐려진다 — 완전히
    #  새 사건/사진으로 "첫 승인(진짜 변화)→재호출(진짜 무변화)" 순서를 그대로 재현한다.
    cid_final = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,partner_id,created_at) "
        "VALUES('R434-CASE-FINAL','시공중','가드레일','서울',?,?,?)",
        (iid, pid, DB.now())).lastrowid
    conn.execute(
        "INSERT INTO photos(case_id,partner_id,rel_path,kind,review_status,uploader_role,"
        "                   created_at) "
        "VALUES(?,?,'r434_final.jpg','시공중','대기','협력사',?)",
        (cid_final, pid, DB.now()))
    conn.commit()
    r_chk1 = admin.post(f"/api/cases/{cid_final}/photos/approve", headers=hdr)
    chk(r_chk1.status_code == 200 and r_chk1.get_json().get("approved") == 1,
        "  원복 후 첫 승인(진짜 변화) 200", r_chk1.get_json())
    n_chk1 = _notif_count()
    r_chk2 = admin.post(f"/api/cases/{cid_final}/photos/approve", headers=hdr)
    chk(r_chk2.status_code == 200, "  원복 후 approve 재호출 200", r_chk2.status_code)
    n_chk2 = _notif_count()
    chk(n_chk2 == n_chk1,
        "★★★★ 원복 후에는 다시 재호출(진짜 무변화)로 알림이 안 늘어난다"
        "(바꿔치기가 안 샜다)", (n_chk1, n_chk2))

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행/되돌리기", f"{type(e).__name__} {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
