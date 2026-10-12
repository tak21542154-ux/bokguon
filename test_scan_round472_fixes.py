# -*- coding: utf-8 -*-
"""스캔 472라운드 회귀 — 두 각도 모두 클린으로 확인, 코드 수정 없음. 수정이
   없었던 라운드지만, 잡아낸 경계 자체가 앞으로도 지켜져야 할 값이라 판단해
   예외적으로 이 조사를 영구 회귀로 편입한다(사용자 요청으로 신설).

  ① 알림 목록·읽음처리 조직간 IDOR — api_insurer_notifications(16503행)·
     api_insurer_notifications_read(16521행)·api_partner_notifications
     (16537행)·api_partner_notifications_read(16555행) 전부 session
     ["insurer_id"]/["partner_id"] 로만 조직을 식별하고 request.args·요청
     본문의 조직id 는 전혀 안 읽음을 소스로 확인 + 실제 Flask test_client
     재현(20개 검사)으로 확인. 교차조직 목록조회(쿼리파라미터 조작)·교차조직
     읽음처리(다른 조직 notification id 지정) 둘 다 실제로 막힌다 — 읽음
     처리는 UPDATE 의 WHERE 절에 세션의 조직id 조건이 같이 붙어 있어,
     응답은 {"ok": true} 지만 DB 에는 실제로 반영되지 않는 조용한 no-op
     이다. 하위계정(portal_users)도 세션의 조직id 가 원계정 id 로 잡히므로
     같은 경계를 자동으로 물려받는다.

  ② 메모 작성자 위조·삭제 권한경계 — api_memo_create(1469행)의 author
     컬럼은 요청 본문이 아니라 서버함수 actor() 로만 채워짐(요청에 가짜
     author 를 넣어도 완전히 무시), api_memo_delete(1513행)는 @require_role
     ("중간관리자") 등급게이트일 뿐 작성자 일치 검사가 아님을 실제 재현
     (16개 검사)으로 확인. 두 관리자의 표시이름(admins.name)이 완전히
     같아도(예: 둘 다 "김철수") actor() 가 로그인id 접미사를 붙이므로
     (라운드170) memos.author 는 서로 다르게 남는다 — 이 방어가 DB.log()
     감사로그뿐 아니라 memos.author 경로에도 실제로 작동한다. 하위관리자는
     자기가 쓴 메모든 남이 쓴 메모든(최고관리자 포함) 삭제 시도 시 전부
     403, 중간관리자는 작성자 등급과 무관하게(최고관리자가 쓴 메모도)
     삭제할 수 있다 — 이 코드베이스 전역의 "등급기반 권한, 작성자기반
     아님" 원칙과 일치, 신규결함 아님.

  ⚠ 두 각도 다 코드 수정이 없는 순수 클린 확인이라, 다른 스캔라운드
    파일들과 달리 "옛 코드로 되돌려 탐지력을 증명" 하는 절이 없다 — 되돌릴
    옛 코드 자체가 없다. 대신 경계마다 양성대조(자기 조직·자기 등급으로는
    실제로 성공)와 음성대조(경계를 넘으면 응답조차 다르거나, 응답은
    성공해도 DB 는 그대로)를 함께 확인해, 전부 통과만 하는 헛테스트가
    아님을 스스로 증명한다.

  ⚠ 기존 라운드와 안 겹침(run_all_tests.py 전체 정독 + 키워드 grep 대조
    완료) — 라운드339는 admin.js 처리버튼의 등급표시 UI 누락만(서버는
    이미 정확 — 이 조사가 같은 서버 로직을 실제 HTTP 재현으로 한 번 더
    확인한 것뿐), 라운드441은 보험사·협력사 defects 목록의 SELECT *
    스키마드리프트만(같은 "관리자 전용 필드 노출" 조사 중 부수발견이었을
    뿐 memos·notifications 자체는 안 건드림), 라운드170/325는 admin 계정
    자체의 개명을 통한 감사로그 행위자 위조만(메모 삭제의 등급/작성자
    경계나 알림 IDOR 는 다룬 적 없음) — 전부 다른 질문.

      python test_scan_round472_fixes.py
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


APP_SRC = io.open(APP_PATH, encoding="utf-8").read()


def _slice_func(def_sig):
    """def_sig(예: 'def api_memo_delete(mid):')로 시작해 다음 최상위
    구성요소(@app. 라우트 또는 최상위 def) 직전까지 잘라낸다.

    바로 다음 블록이 항상 라우트인 건 아니다 — api_memo_delete 바로 뒤는
    평범한 헬퍼 _norm_dot 이다. '\\n@app.' 만 찾으면 그런 헬퍼들까지 통째로
    잘려 들어와 뒤쪽 무관한 코드의 우연한 문자열 일치로 검사가 틀어질 수
    있다.
    """
    i0 = APP_SRC.index(def_sig)
    ends = []
    for marker in ("\n@app.", "\ndef "):
        try:
            ends.append(APP_SRC.index(marker, i0 + len(def_sig)))
        except ValueError:
            pass
    return APP_SRC[i0:min(ends)] if ends else APP_SRC[i0:]


print("=" * 72)
print("  스캔 472라운드 회귀 — 알림 조직간 IDOR · 메모 작성자위조/삭제권한경계(둘 다 클린)")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — 알림 4개 라우트가 전부 세션으로만 조직을 식별한다")
# ============================================================
insurer_list_body = _slice_func("def api_insurer_notifications():")
chk('session["insurer_id"]' in insurer_list_body,
    "api_insurer_notifications() 가 session[insurer_id] 로 조직을 식별한다")
chk("request.args" not in insurer_list_body,
    "★★★★★ api_insurer_notifications() 는 request.args 를 전혀 안 읽는다"
    "(쿼리파라미터로 다른 조직을 지정할 길이 없다)")

insurer_read_body = _slice_func("def api_insurer_notifications_read():")
chk("WHERE id=? AND insurer_id=?" in insurer_read_body,
    "★★★★★ 읽음처리 UPDATE 의 WHERE 절에 세션 조직id 조건이 같이 붙어 있다"
    "(요청이 지정한 notification id 와 무관하게 내 조직 것만 바뀐다)")

partner_list_body = _slice_func("def api_partner_notifications():")
chk('session["partner_id"]' in partner_list_body,
    "api_partner_notifications() 도 session[partner_id] 로 조직을 식별한다")
chk("request.args" not in partner_list_body,
    "★★★★★ api_partner_notifications() 도 request.args 를 전혀 안 읽는다")

partner_read_body = _slice_func("def api_partner_notifications_read():")
chk("WHERE id=? AND partner_id=?" in partner_read_body,
    "★★★★★ 협력사 읽음처리도 WHERE 절에 세션 조직id 조건이 같이 붙어 있다")

# ============================================================
print("\n[2] 소스 확인 — 메모 작성자는 actor() 전용, 삭제는 등급게이트일 뿐 작성자 무관")
# ============================================================
memo_create_body = _slice_func("def api_memo_create():")
chk("actor(), DB.now()))" in memo_create_body,
    "★★★★★ api_memo_create() 의 INSERT 가 author 자리에 actor() 를 직접 쓴다")
chk('d.get("author")' not in memo_create_body,
    "★★★★★ 요청 본문의 author 필드는 어디서도 읽지 않는다(위조해도 무시됨)")

chk('@require_role("중간관리자")\ndef api_memo_delete' in APP_SRC,
    "api_memo_delete() 는 require_role(중간관리자) 등급게이트다")
memo_delete_body = _slice_func("def api_memo_delete(mid):")
chk("author" not in memo_delete_body,
    "★★★★★ 삭제 로직 어디에도 작성자 일치 검사가 없다(등급만 본다)")

chk('@require_admin\ndef api_memo_update' in APP_SRC,
    "(사전조건, 라운드339 기확인) api_memo_update() 는 require_admin — 등급 무관")

# ============================================================
print("\n[3] 실행 준비 — 스크래치 DB, 보험사·협력사 2곳씩+하위계정, 알림 4건, 관리자 3계정")
# ============================================================
_tmpdir = tempfile.mkdtemp(prefix="round472_")
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
    pw = DB.hash_pw("Testpw123!")

    ins_a = conn.execute(
        "INSERT INTO insurers(name,login_id,password_hash,status) "
        "VALUES('R472보험사A','r472ins_a',?,'활성')", (pw,)).lastrowid
    ins_b = conn.execute(
        "INSERT INTO insurers(name,login_id,password_hash,status) "
        "VALUES('R472보험사B','r472ins_b',?,'활성')", (pw,)).lastrowid
    par_a = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,login_id,password_hash,created_at) "
        "VALUES('R472업체A','시공사','활성','가드레일','서울','r472par_a',?,?)", (pw, DB.now())).lastrowid
    par_b = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,login_id,password_hash,created_at) "
        "VALUES('R472업체B','시공사','활성','가드레일','서울','r472par_b',?,?)", (pw, DB.now())).lastrowid
    conn.execute(
        "INSERT INTO portal_users(org_type,org_id,login_id,password_hash,name,role,status,must_change_pw,created_at) "
        "VALUES('insurer',?,'r472sub',?,'하위계정','하위관리자','활성',0,?)", (ins_a, pw, DB.now()))

    n_ins_a = conn.execute(
        "INSERT INTO notifications(ntype,audience_type,insurer_id,message,created_at) "
        "VALUES('공지','insurer',?,'A사 알림',?)", (ins_a, DB.now())).lastrowid
    n_ins_b = conn.execute(
        "INSERT INTO notifications(ntype,audience_type,insurer_id,message,created_at) "
        "VALUES('공지','insurer',?,'B사 알림',?)", (ins_b, DB.now())).lastrowid
    n_par_a = conn.execute(
        "INSERT INTO notifications(ntype,audience_type,partner_id,message,created_at) "
        "VALUES('공지','partner',?,'A업체 알림',?)", (par_a, DB.now())).lastrowid
    n_par_b = conn.execute(
        "INSERT INTO notifications(ntype,audience_type,partner_id,message,created_at) "
        "VALUES('공지','partner',?,'B업체 알림',?)", (par_b, DB.now())).lastrowid

    #  표시이름이 완전히 같은 최고관리자·하위관리자(둘 다 "김철수") — actor() 접미사 구분 검증용
    conn.execute("INSERT INTO admins(username,password_hash,name,role,created_at) "
                 "VALUES('r472top',?,'김철수','최고관리자',?)", (pw, DB.now()))
    conn.execute("INSERT INTO admins(username,password_hash,name,role,created_at) "
                 "VALUES('r472low',?,'김철수','하위관리자',?)", (pw, DB.now()))
    conn.execute("INSERT INTO admins(username,password_hash,name,role,created_at) "
                 "VALUES('r472mid',?,'박영희','중간관리자',?)", (pw, DB.now()))
    conn.commit()

    def _login(kind, login_id):
        c = A.app.test_client()
        r = c.post(f"/api/{kind}/login", json={"login_id": login_id, "password": "Testpw123!"})
        assert r.status_code == 200, r.get_data(as_text=True)
        return c, r.get_json()["csrf"]

    ins_a_c, ins_a_csrf = _login("insurer", "r472ins_a")
    par_a_c, par_a_csrf = _login("partner", "r472par_a")
    sub_c, _sub_csrf = _login("insurer", "r472sub")

    def _admin_client(username, role, name):
        c = A.app.test_client()
        with c.session_transaction() as s:
            s["admin"] = username
            s["admin_role"] = role
            s["admin_name"] = name
            s["_csrf"] = "r472csrf"
        return c

    top_c = _admin_client("r472top", "최고관리자", "김철수")
    low_c = _admin_client("r472low", "하위관리자", "김철수")
    mid_c = _admin_client("r472mid", "중간관리자", "박영희")
    ADM_HDR = {"X-CSRF-Token": "r472csrf"}

    print("\n[4] 실행 — 알림 목록조회: 쿼리파라미터로 다른 조직을 지정해도 무시된다")
    r = ins_a_c.get(f"/api/insurer/notifications?insurer_id={ins_b}&id={n_ins_b}")
    chk(r.status_code == 200, "GET /api/insurer/notifications 200", r.status_code)
    ids = [n["id"] for n in r.get_json()["notifications"]]
    chk(n_ins_a in ids, "내 조직(A) 알림은 보인다")
    chk(n_ins_b not in ids,
        "★★★★★ 쿼리파라미터로 B사 id 를 지정해도 B사 알림은 안 보인다(IDOR 아님)")

    r = par_a_c.get(f"/api/partner/notifications?partner_id={par_b}&id={n_par_b}")
    ids2 = [n["id"] for n in r.get_json()["notifications"]]
    chk(n_par_a in ids2, "협력사 쪽도 동일 — 내 업체(A) 알림은 보인다")
    chk(n_par_b not in ids2,
        "★★★★★ 쿼리파라미터로 B업체 id 를 지정해도 B업체 알림은 안 보인다(IDOR 아님)")

    print("\n[5] 실행 — 알림 읽음처리: 타 조직 id 지정은 응답만 성공, DB는 안 바뀐다(조용한 no-op)")
    r = ins_a_c.post("/api/insurer/notifications/read", json={"id": n_ins_b},
                      headers={"X-CSRF-Token": ins_a_csrf})
    chk(r.status_code == 200 and r.get_json().get("ok") is True,
        "POST 읽음처리(B사 알림 id 지정)는 응답상 ok:true 다")
    row = conn.execute("SELECT read_at FROM notifications WHERE id=?", (n_ins_b,)).fetchone()
    chk(row["read_at"] is None,
        "★★★★★ 그런데 실제 DB 의 B사 알림 read_at 은 여전히 NULL 이다"
        "(응답은 성공처럼 보여도 실제로는 아무 일도 안 일어난 조용한 차단)")

    ins_a_c.post("/api/insurer/notifications/read", json={"id": n_ins_a},
                 headers={"X-CSRF-Token": ins_a_csrf})
    row2 = conn.execute("SELECT read_at FROM notifications WHERE id=?", (n_ins_a,)).fetchone()
    chk(row2["read_at"] is not None,
        "양성대조 — 내 조직(A) 알림은 실제로 읽음처리된다(엔진 자체가 죽은 게 아니다)")

    r = par_a_c.post("/api/partner/notifications/read", json={"id": n_par_b},
                      headers={"X-CSRF-Token": par_a_csrf})
    rowp = conn.execute("SELECT read_at FROM notifications WHERE id=?", (n_par_b,)).fetchone()
    chk(r.get_json().get("ok") is True,
        "협력사 쪽도 동일 — B업체 알림 읽음처리 요청 자체는 ok:true")
    chk(rowp["read_at"] is None,
        "★★★★★ 그런데 B업체 알림의 DB read_at 은 그대로 NULL(조용한 차단)")

    par_a_c.post("/api/partner/notifications/read", json={"id": n_par_a},
                 headers={"X-CSRF-Token": par_a_csrf})
    rowp2 = conn.execute("SELECT read_at FROM notifications WHERE id=?", (n_par_a,)).fetchone()
    chk(rowp2["read_at"] is not None, "양성대조 — 내 업체(A) 알림은 실제로 읽음처리된다")

    print("\n[6] 실행 — 하위계정(portal_users) 테넌시: 원계정과 동일 경계를 물려받는다")
    r = sub_c.get("/api/insurer/notifications")
    sub_ids = [n["id"] for n in r.get_json()["notifications"]]
    chk(n_ins_a in sub_ids and n_ins_b not in sub_ids,
        "A사 하위계정도 A사 알림만 보이고 B사 알림은 안 보인다")

    print("\n[7] 실행 — 메모 작성: 위조 author 는 무시되고, 동명이인은 actor() 로 구분된다")
    r = top_c.post("/api/memos",
                    json={"target_type": "case", "target_id": None, "body": "R472 최고관리자 메모",
                          "author": "완전위조 대표"},
                    headers=ADM_HDR)
    chk(r.status_code == 200 and r.get_json().get("ok") is True, "최고관리자(r472top) 메모 작성 성공")
    mid_top = r.get_json()["id"]
    row_top = conn.execute("SELECT author FROM memos WHERE id=?", (mid_top,)).fetchone()
    chk(row_top["author"] == "김철수(r472top)",
        "★★★★★ author 컬럼은 요청의 위조값이 아니라 actor() 값(김철수(r472top))이다",
        row_top["author"])

    r2 = low_c.post("/api/memos",
                     json={"target_type": "case", "target_id": None, "body": "R472 하위관리자 메모"},
                     headers=ADM_HDR)
    chk(r2.status_code == 200, "하위관리자(r472low)도 메모는 작성할 수 있다(require_admin, 등급무관)")
    mid_low = r2.get_json()["id"]
    row_low = conn.execute("SELECT author FROM memos WHERE id=?", (mid_low,)).fetchone()
    chk(row_low["author"] == "김철수(r472low)" and row_low["author"] != row_top["author"],
        "★★★★★ 표시이름이 완전히 같은(둘 다 '김철수') 두 관리자가 actor() 접미사로 실제로"
        " 구분된다(라운드170 방어가 memos.author 경로에도 작동)", row_low["author"])

    print("\n[8] 실행 — 메모 삭제: 등급게이트일 뿐 작성자 일치는 안 본다")
    r3 = low_c.delete(f"/api/memos/{mid_top}", headers=ADM_HDR)
    chk(r3.status_code == 403,
        "★★★★★ 하위관리자는 남(최고관리자)이 쓴 메모 삭제 시도 시 403")
    r4 = low_c.delete(f"/api/memos/{mid_low}", headers=ADM_HDR)
    chk(r4.status_code == 403,
        "★★★★★ 하위관리자는 자기가 쓴 메모조차 삭제 못 한다(작성자 무관 — 순수 등급게이트라는 증거)")
    still = conn.execute("SELECT COUNT(*) c FROM memos WHERE id IN (?,?)",
                          (mid_top, mid_low)).fetchone()["c"]
    chk(still == 2, "두 403 시도 모두 실제로 삭제되지 않았다(DB에 그대로 남아 있다)")

    r5 = mid_c.delete(f"/api/memos/{mid_top}", headers=ADM_HDR)
    chk(r5.status_code == 200 and r5.get_json().get("ok") is True,
        "★★★★★ 중간관리자는 자기보다 등급이 높은(최고관리자) 사람이 쓴 메모도 삭제할 수 있다"
        "(등급기반 권한 — 작성자기반이 아니라는 이 코드베이스 전역 원칙과 일치)")
    gone = conn.execute("SELECT COUNT(*) c FROM memos WHERE id=?", (mid_top,)).fetchone()["c"]
    chk(gone == 0, "실제로 DB에서 삭제됐다")

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
