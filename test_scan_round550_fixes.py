# -*- coding: utf-8 -*-
"""스캔 550라운드 회귀 — 보험사 API 키 폐기(DELETE /api/insurers/<id>/apikey)가
   인바운드 API 키만 지우고 아웃바운드 웹훅 서명키(webhook_secret)는 그대로
   남겨 두던 결함.

   조사 배경 — 오케스트레이터가 이미 닫힌 각도로 명시한 CSV/엑셀 내보내기(수식
   주입·인코딩), 관리자 대시보드 집계(0건·NULL·동률), 경매 마감 스윕 대 투찰
   경쟁조건, 사진/파일 삭제와 고아파일, 페이지네이션, 협력사 온보딩 서류검증,
   보험사 일괄작업을 전부 직접 조사(하위위임 없음)했으나 전부 클린이었다
   (CSV: _csv_safe/_xl_safe 전 지점 확인, 대시보드: COALESCE/pct() 헬퍼로 이미
   방어, 경매 마감: BEGIN IMMEDIATE + 재조회로 TOCTOU 없음, 사진삭제: 휴지통+
   자식행 정리까지 이미 처리, 온보딩엑셀: 화면과 같은 조회함수 공유, 일괄작업:
   CAS+행별 skip 사유로 이미 방어). 기계적 전수조사로 두 가지도 추가 확인 —
   ① POST/PATCH/DELETE 라우트 중 SELECT+쓰기를 하면서 BEGIN IMMEDIATE가 없는
   곳 0건(AST로 app.py 전체 145개 라우트 스캔 — 처음 짠 스캐너는
   ast.unparse(decorator)가 "@" 접두어 없이 "app.post(...)" 형태로 단순화됨을
   놓쳐 전 함수가 걸러지는 죽은 스캔이었음을 자체 재검토로 발견, 접두어 없이
   다시 매칭해 21개 후보로 교정). ② GET 라우트 중 쓰기 SQL을 내부에 직접 담은
   곳 0건(CSRF는 GET을 검사하지 않으므로 이 클래스가 있었다면 GET 하나로
   트리거되는 CSRF 구멍이었을 것). 교정된 ①의 21개 후보 중 하나(api_application_
   create, 입점신청 직접접수)는 업체명·사업자번호 중복확인이 잠금 없이 read-then-
   write라 이론적으로는 동시 접수 시 중복 대기건이 생길 수 있어 보이나, 그
   중복이 실제 활성업체 중복으로 이어지는 최종 관문(api_application_update의
   DUP_BIZNO 검사)은 round248/429/493이 이미 BEGIN IMMEDIATE로 막아 둬 피해가
   "대기 신청서 중복"에 그친다 — 이번 라운드는 이 항목을 고치지 않고 다음
   라운드 조사거리로만 남긴다(범위 확장 방지, 아래 최종 보고 참고).

   두 전수조사 정리 뒤, 보험사 API 연동 관리(app.py:9091-9312, 지금까지 어느
   라운드도 전담 조사한 적이 없는 구역)를 직접 읽다가 발견.

   결함 — api_insurer_apikey_revoke()(수정 전 app.py:9115-9126)의 UPDATE는
   api_key_hash·api_key_prefix·api_enabled 세 컬럼만 지우고 webhook_secret은
   손대지 않았다. 그런데 형제 두 곳 api_insurer_apikey_issue()·
   api_insurer_webhook_set()은 둘 다 `r.get("webhook_secret") or (새로 생성)`
   식이라 — 이미 값이 있으면 그 값을 그대로 재사용한다(이건 그 자체로는 버그가
   아니라 admin.js insWhSave의 안내문 "주소를 다시 저장해도 같은 값입니다"가
   명시하는 의도된 동작이다 — 웹훅 주소만 고칠 때 발주처 쪽 서명검증 설정까지
   매번 다시 알려줄 필요는 없다). 문제는 "폐기" 라우트다. 이 버튼의 확인창은
   "API 키를 폐기합니다. 보험사 전산 연동이 즉시 끊깁니다"라고, 재발급 확인창은
   "새 API 키를 발급합니다. 기존 키는 즉시 무효가 되어 보험사 전산 연동이
   끊깁니다"라고 — 둘 다 "지금 있는 자격증명을 통째로 끊는다"는 같은 강도로
   안내하는데, 실제로는 api_key_hash만 새로 나가고 webhook_secret은 폐기
   이전 값 그대로 되살아났다. 키 유출을 의심해 폐기를 누른 상황이면 그 유출
   경로가 webhook_secret까지 함께 노출했을 수 있는데, 재발급 후에도 그 옛
   서명키가 계속 유효해 위조 서명 웹훅을 보험사 쪽이 정상으로 오인할 창이
   남는다.

   지금 당장 새는 것은 아니다 — deliver_webhook()·sweep_webhook_retries()·
   api_insurer_webhook_test() 세 발송 경로 전부 secret을 읽기 **전에**
   api_enabled=0을 먼저 보고 걸러(app.py:2217-2218·6677·9299), 폐기 직후엔
   secret 값과 무관하게 아무 것도 안 나간다 — 이 사실을 세 함수 전부 실제
   호출해 확인했다(아래 [1]). 위험은 "폐기 후 재발급"으로 연동을 다시 켜는
   바로 그 시점에만 열린다.

   고침 — 새 정책·헬퍼 없이, revoke의 UPDATE에 webhook_secret=NULL 한 컬럼만
   더했다. NULL로 비워 두면 다음 발급·웹훅 저장 때 두 형제의 `or` 분기가
   자연히 새 시크릿을 만든다.

   ⚠ 1차 시도는 DB.log 문구에 "웹훅 서명키도 함께 무효화"를 조건부로
   덧붙이려 했으나(연동한 적 없는 보험사를 폐기할 때 없는 사실을 지어내지
   않기 위한 조건부였다), 이 세션이 직접 돌린 --quick 배터리가 그 즉시
   test_scan_round327_fixes.py를 깨뜨림을 잡아냈다 — 그 회귀는 "형제 함수
   (폐기·토글)는 회귀 없이 기관명만 남긴다"고 이미 못박아 정확히
   `revoke_log["detail"] == "R327테스트보험"`(기관명 exact-match)를 검사하고
   있었다(그 라운드의 위협모델은 감사로그가 API 키 조각 등 민감정보를 새로
   흘리지 않는 것 — 이번에 덧붙이려던 문구 자체는 민감정보가 아니었지만,
   같은 exact-match 계약을 깨는 것은 같다). 로그 문구는 손대지 않고 DB 컬럼
   (webhook_secret=NULL)만 고쳐 그 기존 검증된 계약을 그대로 지킨다 — 감사
   메시지의 부가 정보보다 이미 테스트로 고정된 계약을 우선한다.

      python test_scan_round550_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile

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
    end = src.find("\n@app.", start + 1)
    return src[start:end if end != -1 else None]


print("=" * 72)
print("  스캔 550라운드 회귀 — 보험사 API 키 폐기가 웹훅 서명키를 안 지우던 결함")
print("=" * 72)

APP_SRC = read("app.py")

# ==================================================================
print("\n[0] 소스 — 고친 지점이 실제로 app.py 에 있는가"
      "(동시편집 세션이 되돌렸다면 여기서부터 정직하게 실패해야 한다)")
# ------------------------------------------------------------------
try:
    import ast as _ast
    chk(_ast.parse(APP_SRC) is not None, "STEP app.py 전체 ast.parse 성공")

    rv_body = _py_fn_body(APP_SRC, "api_insurer_apikey_revoke")
    chk("webhook_secret=NULL" in rv_body,
        "★★★★★ api_insurer_apikey_revoke() 의 UPDATE 에 webhook_secret=NULL 이 있다"
        "(고치기 전엔 이 토큰이 없었다)")
    _i_update = rv_body.index("UPDATE insurers SET")
    _i_secret = rv_body.index("webhook_secret=NULL")
    chk(_i_update < _i_secret, "STEP webhook_secret=NULL 이 UPDATE 문 안에 있다(딴 자리 아님)")
    chk('DB.log(conn, actor(), "API 키 폐기", r["name"])' in rv_body,
        "★★★ 감사로그 문구는 형제(발급·토글)와 같은 형식(기관명만) 그대로다 — "
        "round327(test_scan_round327_fixes.py)이 이미 이 exact-match 계약을 "
        "고정해 뒀다(1차 시도로 조건부 문구를 붙였다가 그 계약을 깨뜨렸음을 "
        "이 세션이 --quick 배터리로 직접 잡아내고 되돌렸다 — 위 docstring 참고)")
    chk('SELECT name FROM insurers WHERE id=?", (iid,)))' in rv_body,
        "STEP SELECT 도 형제와 같은 최소 컬럼(name)만 읽는다"
        "(webhook_secret 을 굳이 함께 안 읽음 — 로그 조건 분기 자체가 없어졌으므로)")

    # 형제 두 곳은 이번 라운드가 손대지 않았다 — 그대로인지 대조(과잉수정 없음).
    issue_body = _py_fn_body(APP_SRC, "api_insurer_apikey_issue")
    chk('secret = r.get("webhook_secret") or ("whsec_" + secrets.token_urlsafe(24))' in issue_body,
        "STEP 형제 api_insurer_apikey_issue() 의 '있으면 재사용' 로직은 그대로다"
        "(이번 수정은 여기가 아니라 revoke 쪽에서 NULL 을 만들어 자연히 새로 "
        "생성되게 한다 — 이 함수 자신은 안 건드림)")
    wh_body = _py_fn_body(APP_SRC, "api_insurer_webhook_set")
    chk('secret = r.get("webhook_secret") or ("whsec_" + secrets.token_urlsafe(24))' in wh_body,
        "STEP 형제 api_insurer_webhook_set() 도 그대로다(웹훅주소 재저장 시 "
        "서명키 유지는 admin.js 가 명시하는 의도된 동작 — 손대지 않음)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드550 [0] 소스 확인", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[1] 사전확인 — 세 발송 경로 전부 api_enabled=0 이면 secret 을 읽기도 "
      "전에 걸러낸다(그래서 폐기 직후엔 secret 값과 무관하게 안전하다는 "
      "본문 주석의 주장을 실제로 검증)")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round550_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r550-csrf"
H = {"X-CSRF-Token": CSRF}
A = DB = None


def _admin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "admin550"
        sess["admin_name"] = "실행계정550"
        sess["admin_role"] = "최고관리자"
        sess["_csrf"] = CSRF
    return c


try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('admin550','x','실행계정550','최고관리자')")
    #  api_enabled=0 인 보험사(방금 폐기됐다고 가정) — secret 은 아직 살아있다.
    iid0 = conn0.execute(
        "INSERT INTO insurers(name,org_type,status,api_enabled,webhook_url,webhook_secret) "
        "VALUES('R550사전확인','손해보험','활성',0,'https://8.8.8.8/hook','whsec_pre_secret')"
    ).lastrowid
    conn0.commit(); conn0.close()

    sent_via = {"count": 0}

    def _fake_send(delivery_id, url, secret, payload_str, count_attempt=True):
        sent_via["count"] += 1
        return None
    _real_send = A._webhook_send
    A._webhook_send = _fake_send
    try:
        conn = DB.get_db()
        did = A.deliver_webhook(conn, iid0, "case.awarded", "R550-X", {"a": 1})
        conn.commit()
        st = A.one(conn.execute("SELECT status FROM webhook_deliveries WHERE id=?", (did,)))
        chk(st["status"] == "미설정",
            "STEP deliver_webhook() — api_enabled=0 이면 secret 을 쓸 일도 없이 "
            "'미설정'으로 접는다(전송 큐에 안 올림)", st["status"])
        n_before = sent_via["count"]
        n = A.sweep_webhook_retries(conn)
        chk(n == 0 and sent_via["count"] == n_before,
            "STEP sweep_webhook_retries() — WHERE 절 자체가 api_enabled=1 을 "
            "요구해 이 보험사 행은 애초에 대상에 안 잡힌다", (n, sent_via["count"]))
        conn.close()

        admin_c = _admin_client()
        r = admin_c.post(f"/api/insurers/{iid0}/webhook-test", headers=H)
        rbody = r.get_json() or {}
        chk(r.status_code == 409 and rbody.get("code") == "API_DISABLED",
            "STEP api_insurer_webhook_test() — api_enabled=0 이면 secret 을 "
            "쓰기 전에 409 API_DISABLED 로 막는다", (r.status_code, rbody))
    finally:
        A._webhook_send = _real_send
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드550 [1] 사전확인(세 발송경로 게이트)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[2] 실행(진짜 라우트, 지금 코드) — 웹훅까지 이미 설정된 보험사를 "
      "폐기하면 webhook_secret 도 함께 NULL 이 되고, 감사로그는 회귀 없이 "
      "형제(발급·토글)와 같은 형식(기관명만)이다")
# ------------------------------------------------------------------
iid_a = None
try:
    conn0 = DB.get_db()
    #  ⚠ api_key_hash 는 UNIQUE 인덱스가 있다 — 라운드마다 값이 겹치지 않게 접두어를 둔다.
    iid_a = conn0.execute(
        "INSERT INTO insurers(name,org_type,status,api_key_hash,api_key_prefix,"
        "api_key_created,api_enabled,webhook_url,webhook_secret) "
        "VALUES('R550업체A','손해보험','활성','r550_hash_a','bok_live_r550a',?,1,"
        "'https://8.8.8.8/hook','whsec_should_die_a')", (DB.now(),)).lastrowid
    conn0.commit(); conn0.close()
    chk(bool(iid_a), "STEP (준비) 키·웹훅이 이미 설정된 보험사 A 생성", iid_a)

    admin_c = _admin_client()
    r = admin_c.delete(f"/api/insurers/{iid_a}/apikey", headers=H)
    rbody = r.get_json() or {}
    chk(r.status_code == 200 and rbody.get("ok") is True,
        "STEP DELETE /api/insurers/<id>/apikey 가 200·ok:true 를 돌려준다",
        (r.status_code, rbody))

    conn = DB.get_db()
    row_a = A.one(conn.execute(
        "SELECT api_key_hash, api_key_prefix, api_enabled, webhook_secret, webhook_url "
        "  FROM insurers WHERE id=?", (iid_a,)))
    chk(row_a["api_key_hash"] is None and row_a["api_key_prefix"] is None
        and row_a["api_enabled"] == 0,
        "STEP 회귀 없음 — 인바운드 API 키 세 컬럼은 예전처럼 여전히 지워진다",
        dict(row_a))
    chk(row_a["webhook_secret"] is None,
        "★★★★★ 지금 코드: 웹훅 서명키도 함께 NULL 이 됐다"
        "(고치기 전엔 'whsec_should_die_a' 가 그대로 남아 있었다)", row_a["webhook_secret"])
    chk(row_a["webhook_url"] == "https://8.8.8.8/hook",
        "STEP 웹훅 '주소'는 안 건드린다(비밀키만 지운다 — 발주처가 다시 알려줄 "
        "필요 없는 정보까지 지우면 재연동이 번거로워진다)", row_a["webhook_url"])

    log_row = A.one(conn.execute(
        "SELECT detail FROM activity_log WHERE action='API 키 폐기' "
        "AND detail LIKE 'R550업체A%' ORDER BY id DESC LIMIT 1"))
    chk(bool(log_row) and log_row["detail"] == "R550업체A",
        "★★★★ 감사로그는 round327 이 고정한 형제(발급·토글)와 같은 형식 "
        "그대로다(기관명만, exact-match) — webhook_secret 이 실제로 NULL 이 "
        "됐다는 사실은 위 DB 상태 확인만으로 충분히 증명되고, 로그 문구는 "
        "이미 검증된 다른 라운드의 계약을 깨지 않는다",
        log_row["detail"] if log_row else None)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드550 [2] 지금 코드(웹훅 설정된 보험사 폐기)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[3] 회귀 안전 — 애초에 웹훅을 설정한 적 없는(webhook_secret NULL) "
      "보험사를 폐기해도 정상 동작한다(과잉교정 없음)")
# ------------------------------------------------------------------
try:
    conn0 = DB.get_db()
    iid_b = conn0.execute(
        "INSERT INTO insurers(name,org_type,status,api_key_hash,api_key_prefix,"
        "api_key_created,api_enabled) "
        "VALUES('R550업체B','손해보험','활성','r550_hash_b','bok_live_r550b',?,1)",
        (DB.now(),)).lastrowid
    conn0.commit(); conn0.close()

    admin_c2 = _admin_client()
    r2 = admin_c2.delete(f"/api/insurers/{iid_b}/apikey", headers=H)
    rbody2 = r2.get_json() or {}
    chk(r2.status_code == 200 and rbody2.get("ok") is True,
        "STEP 웹훅 미설정 보험사도 폐기가 정상적으로 200 을 돌려준다",
        (r2.status_code, rbody2))

    conn = DB.get_db()
    row_b = A.one(conn.execute(
        "SELECT api_key_hash, webhook_secret FROM insurers WHERE id=?", (iid_b,)))
    chk(row_b["api_key_hash"] is None and row_b["webhook_secret"] is None,
        "STEP DB 상태는 정상(둘 다 NULL, 원래도 NULL 이던 값이 계속 NULL)",
        dict(row_b))
    log_row2 = A.one(conn.execute(
        "SELECT detail FROM activity_log WHERE action='API 키 폐기' "
        "AND detail LIKE 'R550업체B%' ORDER BY id DESC LIMIT 1"))
    chk(bool(log_row2) and log_row2["detail"] == "R550업체B",
        "STEP 회귀 안전: 이 경우도 로그는 형제와 같은 형식(기관명만) 그대로다",
        log_row2["detail"] if log_row2 else None)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드550 [3] 회귀 안전(웹훅 미설정 보험사)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[4] 인과관계 증명 — 폐기 뒤 재발급하면 지금 코드는 완전히 새 시크릿을 "
      "내고, 옛 값은 다시 살아나지 않는다(실사용 시나리오 끝까지)")
# ------------------------------------------------------------------
try:
    admin_c3 = _admin_client()
    r3 = admin_c3.post(f"/api/insurers/{iid_a}/apikey", headers=H)
    rbody3 = r3.get_json() or {}
    chk(r3.status_code == 200 and bool(rbody3.get("webhook_secret")),
        "STEP 폐기 뒤 재발급(POST /apikey)이 정상적으로 새 webhook_secret 을 응답에 담는다",
        (r3.status_code, rbody3))
    new_secret = rbody3.get("webhook_secret")
    chk(new_secret != "whsec_should_die_a",
        "★★★★★ 재발급된 서명키가 폐기 전 옛 값과 다르다(되살아나지 않는다) "
        "— 고치기 전이었다면 revoke 가 NULL 로 못 만들어 이 값이 옛 그대로였을 것",
        new_secret)

    conn = DB.get_db()
    row_a2 = A.one(conn.execute(
        "SELECT webhook_secret, api_key_hash, api_enabled FROM insurers WHERE id=?", (iid_a,)))
    chk(row_a2["webhook_secret"] == new_secret and row_a2["api_key_hash"] is not None
        and row_a2["api_enabled"] == 1,
        "STEP DB 에도 새 시크릿·새 키·재활성화가 일관되게 반영됐다", dict(row_a2))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드550 [4] 인과관계 증명(폐기→재발급)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[5] 원인 재현 — app.py·run_all_tests.py 는 건드리지 않고, 이번 "
      "수정 직전의 실제 함수 본문을 문자열로 재구성해(exec, round543·547·549와 "
      "같은 방식) 같은 시나리오를 실행하면 정말 webhook_secret 이 안 지워지는가")
# ------------------------------------------------------------------
#  ⚠ 이 문자열은 이번 수정 **직전**(즉 애초의 결함 상태 — DB.log 조건부 문구를 "
#    붙이기 전의 순수 원본) 이 세션이 Read 로 확인한 api_insurer_apikey_revoke
#    원문 그대로다(로직·순서 100% 동일, docstring만 없음).
_PRE550_SRC = '''
def _api_insurer_apikey_revoke_pre550(iid):
    conn = DB.get_db()
    r = one(conn.execute("SELECT name FROM insurers WHERE id=?", (iid,)))
    if not r:
        conn.close(); return jsonify({"ok": False, "error": "기관을 찾을 수 없습니다."}), 404
    conn.execute(
        "UPDATE insurers SET api_key_hash=NULL, api_key_prefix=NULL, api_enabled=0 WHERE id=?", (iid,))
    DB.log(conn, actor(), "API 키 폐기", r["name"])
    conn.commit(); conn.close()
    return jsonify({"ok": True})
'''
try:
    conn0 = DB.get_db()
    iid_c = conn0.execute(
        "INSERT INTO insurers(name,org_type,status,api_key_hash,api_key_prefix,"
        "api_key_created,api_enabled,webhook_url,webhook_secret) "
        "VALUES('R550업체C','손해보험','활성','r550_hash_c','bok_live_r550c',?,1,"
        "'https://8.8.8.8/hook','whsec_should_die_c')", (DB.now(),)).lastrowid
    conn0.commit(); conn0.close()

    _ns = dict(vars(A))              # app 모듈 네임스페이스 복사(진짜 모듈은 안 건드림)
    exec(compile(_PRE550_SRC, "<round550_pre_reconstructed>", "exec"), _ns)
    _old_revoke = _ns["_api_insurer_apikey_revoke_pre550"]

    with A.app.test_request_context(f"/api/insurers/{iid_c}/apikey", method="DELETE"):
        from flask import session as _flask_session
        _flask_session["admin"] = "admin550"
        _flask_session["admin_name"] = "실행계정550"
        _flask_session["admin_role"] = "최고관리자"
        resp = _old_revoke(iid_c)
    resp_obj = resp[0] if isinstance(resp, tuple) else resp
    chk(resp_obj is not None, "STEP 재구성한 옛 함수도 정상적으로 응답을 만든다")

    conn = DB.get_db()
    row_c = A.one(conn.execute(
        "SELECT api_key_hash, api_key_prefix, api_enabled, webhook_secret "
        "  FROM insurers WHERE id=?", (iid_c,)))
    chk(row_c["api_key_hash"] is None and row_c["api_key_prefix"] is None
        and row_c["api_enabled"] == 0,
        "STEP 옛 코드(재구성)도 인바운드 키 세 컬럼은 똑같이 지운다"
        "(겉보기 동작은 지금 코드와 같아 보인다 — 그래서 그동안 아무도 눈치 못 챘다)",
        dict(row_c))
    chk(row_c["webhook_secret"] == "whsec_should_die_c",
        "★★★★★ 그런데 옛 코드(재구성)는 webhook_secret 을 전혀 안 지운다 — "
        "지금 코드(위 [2])는 같은 시나리오에서 실제로 NULL 이었다. 이 차이가 "
        "이 회귀가 결함을 실제로 잡아낼 능력이 있다는 인과관계 증명이다",
        row_c["webhook_secret"])
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드550 [5] 원인 재현(옛 코드)", f"{type(e).__name__} {e}")


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
