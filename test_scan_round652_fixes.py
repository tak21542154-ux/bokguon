# -*- coding: utf-8 -*-
"""스캔 652라운드 회귀 — app.py 전역에서 "JSON 본문 값을 그대로 int()로 바꾸는" 자리
11곳이 OverflowError(1e400류 → json 파서가 float('inf')로 성공 파싱 → 그 값을
int()로 바꾸는 순간 ValueError가 아니라 OverflowError)를 못 잡던 결함.

배경 — round485는 이 함정(_setting_int)을, round596은 또 다른 유입구(JSON 본문의
id류)를 흩어진 호출부마다 고치는 대신 전역 예외핸들러(err_500, 1315행)에서 한 번에
400(code=BAD_INPUT, "입력값이 너무 큽니다")으로 눌러 두었다. round631은 정확히 같은
값(ai_auto_threshold)을 다루는 두 자리(_ai_threshold·api_ai_threshold_set)가 여전히
빠져 있음을 찾아 고쳤다. round592는 api_admin_notifications_read의 "자릿수만 큰
정수 문자열" 유입구를 막았지만 그 자신의 except 튜플도 OverflowError는 안 잡는다.

직접조사(하위위임 없음) — app.py 전체에서 "except (TypeError, ValueError...)" 계열
튜플이 나오는 30여 곳을 전수 대조했다. 대부분은 안전하다:
  · request.args.get(...) 로 얻은 값(항상 문자열) — int("1e400")은 애초에
    ValueError일 뿐 OverflowError가 아니다(과학표기 파싱은 float()만 한다).
  · int(str(v)...) 처럼 먼저 str()로 감싼 값 — str(float('inf'))=="inf"이고
    int("inf")도 ValueError다.
  · float(d.get("lat"))류 — float()는 inf에서 예외를 안 던지고, 그 뒤 한반도
    범위 확인(33~39.5, 124~132)이 inf·nan을 그대로 걸러낸다(실측 확인, 4257행
    _picked_coords).
남은 11곳만 "JSON 본문 값을 가공 없이 그대로 int()에 넘기고, except 튜플에
OverflowError가 없다"는 조건을 실제로 만족했다(2025-09-14 조사 시점 app.py 기준):

  1. api_create_application   (POST /api/applications, 무인증 공개폼)      staff_count
  2. api_application_create   (POST /api/applications/manual, admin)      staff_count (1의 형제)
  3. api_partner_bulk_credentials (POST /api/partners/bulk-credentials, 최고관리자) ids
  4. api_case_edit            (PATCH /api/cases/<id>, 중간관리자)         warranty_months
  5. api_settlements_paid_bulk(POST /api/settlements/paid-bulk, 중간관리자) ids
  6. _attach_defect_photos    (내부 헬퍼 — 하자 지적사진 첨부)             photo_id
  7. api_outbox_send_selected (POST /api/outbox/send-selected, 중간관리자) ids
  8. api_admin_notifications_read (POST /api/admin/notifications/read, admin) id (round592의 후속 결함)
  9. api_dispatch_assign      (POST /api/cases/<id>/dispatch/assign, 중간관리자) partner_id
 10. api_happy_call_add       (POST /api/cases/<id>/happy-call, 하위관리자) score
 11. api_partner_invite       (POST /api/partners/invite, 하위관리자)      ids

이 중 1번(공개 무인증 폼)은 로그인 없이 인터넷 누구나 트리거할 수 있어 가장 심각하다.
6번(_attach_defect_photos)은 단순 400 대신 "잘못된 사진 1장이 같은 요청의 나머지
정상 사진 첨부까지 통째로 실패시킨다"는 점에서 형제들과 증상이 다르다.

고침 — 11곳 전부 except 튜플에 OverflowError를 추가했다(형제 round485·631·596과
바이트 단위로 같은 처방). 새 메커니즘·새 헬퍼 없음.

검증
 [1] 소스 확인 — 11곳 전부 자기 함수 안에 새 except 튜플이 있다.
 [2] 실행 — 스크래치 DB + 실제 Flask 앱(단일 최고관리자 세션 — require_role은 최소
     등급만 보므로 최고관리자가 하위관리자·중간관리자 라우트도 그대로 통과한다,
     _admin_rank() 실측 확인)으로 11곳 전부에 1e400 계열 값을 실제로 흘려보내
     (a) 500이 아니라 400(또는 정상 200)이고 (b) round596 전역핸들러의 범용 문구
     (code=BAD_INPUT)가 아니라 그 자리 자신의 구체적 동작이 나오는지 확인.
 [3] 회귀없음 — 정상값은 각 자리에서 기존과 동일하게 동작.
 [4] 되돌리기-증명(대표 2곳, round414·565·631이 확립한 안전패턴) —
     api_dispatch_assign(라우트 — view_functions 치환)과 _attach_defect_photos
     (헬퍼 — 모듈 속성 치환)를 옛(취약) except 튜플로 되돌린 사본을 exec로
     격리 재구성해, 실제로 크래시/오작동하는지 실행으로 재현한 뒤 finally로
     즉시 원복한다. 실제 app.py 파일은 이 과정 전체에서 단 한 바이트도 안
     바뀐다(마지막에 디스크 재확인).

    python test_scan_round652_fixes.py
"""
import io
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def _py_fn_body(src, fn_name):
    """함수 본문 — 다음 def뿐 아니라 다음 라우트의 @app. 데코레이터가 먼저
    나오면 거기서 자른다(round610/631이 정착시킨 기법)."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


APP_SRC = read("app.py")
NEW_EXC = "except (TypeError, ValueError, OverflowError):"
NEW_EXC_SCORE = "except (TypeError, ValueError, AssertionError, OverflowError):"

print("=" * 72)
print("  스캔 652라운드 회귀 — int(JSON 본문 값) 11곳의 OverflowError 미포착")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 11곳 전부 자기 함수 안에 새 except 튜플이 있다")
# ──────────────────────────────────────────────────────────────
SITES = [
    ("api_create_application", NEW_EXC, "staff_count(공개폼)"),
    ("api_application_create", NEW_EXC, "staff_count(직접접수)"),
    ("api_partner_bulk_credentials", NEW_EXC, "ids(계정 일괄발급)"),
    ("api_case_edit", NEW_EXC, "warranty_months"),
    ("api_settlements_paid_bulk", NEW_EXC, "ids(정산 일괄확인)"),
    ("_attach_defect_photos", NEW_EXC, "photo_id"),
    ("api_outbox_send_selected", NEW_EXC, "ids(발송 일괄)"),
    ("api_admin_notifications_read", NEW_EXC, "id(알림 읽음)"),
    ("api_dispatch_assign", NEW_EXC, "partner_id"),
    ("api_happy_call_add", NEW_EXC_SCORE, "score"),
    ("api_partner_invite", NEW_EXC, "ids(안내발송)"),
]
_bodies = {}
for fn_name, exc_text, label in SITES:
    body_src = _py_fn_body(APP_SRC, fn_name)
    _bodies[fn_name] = body_src
    chk(exc_text in body_src,
        f"★★★★★ {fn_name}() [{label}] — except 튜플에 OverflowError가 있다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 준비 — 스크래치 DB + 실제 Flask 앱")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round652_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "scratch.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import sqlite3
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('r652admin','x','검증','최고관리자')")
    conn0.execute("INSERT INTO cases(case_no,status,warranty_months,created_at) "
                  "VALUES('R652-CASE-1','완료',24,?)", (DB.now(),))
    case_id = conn0.execute("SELECT id FROM cases WHERE case_no='R652-CASE-1'").fetchone()[0]
    conn0.execute("INSERT INTO photos(case_id,rel_path,created_at) VALUES(?,?,?)",
                  (case_id, "r652/real.jpg", DB.now()))
    real_photo_id = conn0.execute("SELECT id FROM photos WHERE rel_path='r652/real.jpg'").fetchone()[0]
    conn0.execute("INSERT INTO defects(title,case_id,created_at) VALUES('R652 결함',?,?)",
                  (case_id, DB.now()))
    defect_id = conn0.execute("SELECT id FROM defects WHERE title='R652 결함'").fetchone()[0]
    conn0.commit()
    conn0.close()

    #  최고관리자 세션 하나로 11곳 전부 커버 — require_role()은 "최소 등급"만
    #  보므로(_admin_rank() >= need) 최고관리자(3)가 중간관리자(2)·하위관리자(1)
    #  라우트도 그대로 통과한다(app.py 732-748행 실제 로직 확인).
    ATOK = "r652-csrf"
    HDR = {"X-CSRF-Token": ATOK}

    def admin_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["admin"] = "r652admin"; sess["admin_role"] = "최고관리자"; sess["_csrf"] = ATOK
        return c

    def is_generic_overflow_msg(j):
        """round596 전역핸들러(err_500)가 낸 범용 문구인지."""
        return (j or {}).get("code") == "BAD_INPUT"

    # ══════════════════════════════════════════════════════════
    print("\n[3] 실행 — 지금(고쳐진) 코드: 11곳 전부 1e400류에도 500이 아니라")
    print("    그 자리 자신의 구체적 동작으로 안전하게 처리된다")
    # ──────────────────────────────────────────────────────────

    # --- 1) 공개폼 /api/applications — staff_count (무인증) ---
    c_pub = A.app.test_client()
    r1 = c_pub.post("/api/applications", data=(
        '{"company":"복구온R652공개1","phone":"010-1000-0001",'
        '"agree_privacy":true,"staff_count":1e400}'),
        content_type="application/json")
    chk(r1.status_code == 400, "  [1] 공개폼 staff_count=1e400 → 500 아니라 400", r1.status_code)
    j1 = r1.get_json() or {}
    chk(not is_generic_overflow_msg(j1) and "1인 사업자" in (j1.get("error") or ""),
        "★★★★★ [1] 파싱 실패가 None으로 흡수돼 이 라우트 고유의 SOLO 거절문구가 나온다"
        "(전역핸들러 범용문구 아님)", j1)

    # 회귀없음 — 정상 staff_count는 그대로 접수된다
    r1b = c_pub.post("/api/applications", data=(
        '{"company":"복구온R652공개2","phone":"010-1000-0002",'
        '"agree_privacy":true,"staff_count":5}'),
        content_type="application/json")
    chk(r1b.status_code == 200 and (r1b.get_json() or {}).get("ok") is True,
        "  [1] 회귀없음 — 정상 staff_count(5)는 그대로 접수(200/ok)", r1b.get_json())

    # --- 2) 직접접수 /api/applications/manual — staff_count (admin) ---
    ac = admin_client()
    r2 = ac.post("/api/applications/manual", data=(
        '{"company":"복구온R652직접1","major":"누수","staff_count":1e400}'),
        content_type="application/json", headers=HDR)
    chk(r2.status_code == 200 and (r2.get_json() or {}).get("ok") is True,
        "★★★★★ [2] 직접접수 staff_count=1e400 → 크래시 없이 '미입력'으로 흡수돼 "
        "정상 접수(이 폼의 정책: 미입력은 안 막고 승인 때 확인)", r2.get_json())

    # --- 3) 업체 계정 일괄발급 /api/partners/bulk-credentials — ids ---
    r3 = ac.post("/api/partners/bulk-credentials", data='{"ids":[1e400]}',
                 content_type="application/json", headers=HDR)
    chk(r3.status_code == 400, "  [3] ids=[1e400] → 500 아니라 400", r3.status_code)
    j3 = r3.get_json() or {}
    chk(not is_generic_overflow_msg(j3) and "업체 번호" in (j3.get("error") or ""),
        "★★★★★ [3] 이 라우트 고유의 '업체 번호가 올바르지 않습니다' 문구가 나온다", j3)

    # --- 4) 사건 수동수정 PATCH /api/cases/<id> — warranty_months ---
    r4 = ac.patch(f"/api/cases/{case_id}", data='{"warranty_months":1e400}',
                  content_type="application/json", headers=HDR)
    chk(r4.status_code == 400, "  [4] warranty_months=1e400 → 500 아니라 400", r4.status_code)
    j4 = r4.get_json() or {}
    chk(not is_generic_overflow_msg(j4) and "보증 개월" in (j4.get("error") or ""),
        "★★★★★ [4] 이 라우트 고유의 '보증 개월은 숫자여야 합니다' 문구가 나온다", j4)
    # 회귀없음 — 정상 값은 그대로 저장된다
    r4b = ac.patch(f"/api/cases/{case_id}", data='{"warranty_months":36}',
                   content_type="application/json", headers=HDR)
    chk(r4b.status_code == 200 and (r4b.get_json() or {}).get("ok") is True,
        "  [4] 회귀없음 — 정상 warranty_months(36)는 그대로 저장(200/ok)", r4b.get_json())

    # --- 5) 정산 일괄확인 /api/settlements/paid-bulk — ids ---
    r5 = ac.post("/api/settlements/paid-bulk", data='{"ids":[1e400]}',
                 content_type="application/json", headers=HDR)
    chk(r5.status_code == 400, "  [5] ids=[1e400] → 500 아니라 400", r5.status_code)
    j5 = r5.get_json() or {}
    chk(not is_generic_overflow_msg(j5) and "정산 번호" in (j5.get("error") or ""),
        "★★★★★ [5] 이 라우트 고유의 '정산 번호가 올바르지 않습니다' 문구가 나온다", j5)

    # --- 6) _attach_defect_photos — photo_id (직접 함수 호출, 라우트 아님) ---
    conn6 = DB.get_db()
    n_attached = None
    exc6 = None
    try:
        n_attached = A._attach_defect_photos(
            conn6, defect_id, case_id,
            [{"photo_id": float("inf")}, {"photo_id": real_photo_id}], "검증")
        conn6.commit()
    except Exception as e:                                          # noqa: BLE001
        exc6 = e
    finally:
        conn6.close()
    chk(exc6 is None,
        "★★★★★ [6] photo_id=inf 가 섞여도 함수 전체가 죽지 않는다"
        "(수정 전엔 OverflowError로 이 항목 이후 나머지도 전부 유실)", exc6)
    chk(n_attached == 1,
        "  [6] inf 항목은 조용히 건너뛰고, 그 뒤 정상 photo_id는 그대로 붙었다"
        "(n=1)", n_attached)

    # --- 7) 발송 일괄 /api/outbox/send-selected — ids ---
    r7 = ac.post("/api/outbox/send-selected", data='{"ids":[1e400]}',
                 content_type="application/json", headers=HDR)
    chk(r7.status_code == 400, "  [7] ids=[1e400] → 500 아니라 400", r7.status_code)
    j7 = r7.get_json() or {}
    chk(not is_generic_overflow_msg(j7) and "알림 번호" in (j7.get("error") or ""),
        "★★★★★ [7] 이 라우트 고유의 '알림 번호가 올바르지 않습니다' 문구가 나온다", j7)

    # --- 8) 콘솔 알림 읽음처리 /api/admin/notifications/read — id ---
    r8 = ac.post("/api/admin/notifications/read", data='{"id":1e400}',
                 content_type="application/json", headers=HDR)
    chk(r8.status_code == 400, "  [8] id=1e400 → 500 아니라 400", r8.status_code)
    j8 = r8.get_json() or {}
    chk(not is_generic_overflow_msg(j8) and "알림 id" in (j8.get("error") or ""),
        "★★★★★ [8] 이 라우트 고유의 '알림 id는 숫자여야 합니다' 문구가 나온다"
        "(round592가 막았던 '자릿수 큰 문자열' 경로와는 다른, 같은 함수의 "
        "또 다른 유입구)", j8)

    # --- 9) 수배 직접 배정 /api/cases/<id>/dispatch/assign — partner_id ---
    #     (파싱이 DB 조회보다 먼저라 사건이 실존하지 않아도 이 결함은 재현된다)
    r9 = ac.post(f"/api/cases/{case_id}/dispatch/assign",
                 data='{"partner_id":1e400,"reason":"R652 검증"}',
                 content_type="application/json", headers=HDR)
    chk(r9.status_code == 400, "  [9] partner_id=1e400 → 500 아니라 400", r9.status_code)
    j9 = r9.get_json() or {}
    chk(not is_generic_overflow_msg(j9) and "배정할 업체" in (j9.get("error") or ""),
        "★★★★★ [9] 이 라우트 고유의 '배정할 업체를 선택해 주세요' 문구가 나온다", j9)

    # --- 10) 해피콜 /api/cases/<id>/happy-call — score ---
    r10 = ac.post(f"/api/cases/{case_id}/happy-call", data='{"score":1e400}',
                  content_type="application/json", headers=HDR)
    chk(r10.status_code == 400, "  [10] score=1e400 → 500 아니라 400", r10.status_code)
    j10 = r10.get_json() or {}
    chk(not is_generic_overflow_msg(j10) and "점수는 1~5" in (j10.get("error") or ""),
        "★★★★★ [10] 이 라우트 고유의 '점수는 1~5 사이 정수여야 합니다' 문구가 나온다", j10)

    # --- 11) 안내발송 표시 /api/partners/invite — ids ---
    r11 = ac.post("/api/partners/invite", data='{"ids":[1e400]}',
                  content_type="application/json", headers=HDR)
    chk(r11.status_code == 400, "  [11] ids=[1e400] → 500 아니라 400", r11.status_code)
    j11 = r11.get_json() or {}
    chk(not is_generic_overflow_msg(j11) and "업체 번호" in (j11.get("error") or ""),
        "★★★★★ [11] 이 라우트 고유의 '업체 번호가 올바르지 않습니다' 문구가 나온다", j11)

    # ══════════════════════════════════════════════════════════
    print("\n[4] 되돌리기-증명(대표 2곳) — 실제 app.py 파일은 안 건드리고")
    print("    인메모리로만 옛(취약) 코드를 재구성해 진짜로 재현되는지 확인")
    # ──────────────────────────────────────────────────────────

    # [4-A] 라우트 레벨 — api_dispatch_assign (view_functions 치환)
    OLD_DISPATCH_SRC = '''
def api_dispatch_assign(cid):
    d = body()
    try:
        pid = int(d.get("partner_id") or 0)
    except (TypeError, ValueError):
        pid = 0
    if not pid:
        return jsonify({"ok": False, "error": "배정할 업체를 선택해 주세요."}), 400
    return jsonify({"ok": False, "error": "unreachable-in-this-test"}), 500
'''
    _ns9 = {}
    exec(compile(OLD_DISPATCH_SRC, "<round652_old:api_dispatch_assign>", "exec"),
         A.__dict__, _ns9)
    OLD_VIEW9 = A.require_role("중간관리자")(_ns9["api_dispatch_assign"])
    NEW_VIEW9 = A.app.view_functions["api_dispatch_assign"]
    try:
        A.app.view_functions["api_dispatch_assign"] = OLD_VIEW9
        r_old9 = ac.post(f"/api/cases/{case_id}/dispatch/assign",
                         data='{"partner_id":1e400,"reason":"되돌림 재현"}',
                         content_type="application/json", headers=HDR)
        chk(r_old9.status_code == 400,
            "  [4-A] 되돌린 옛 코드도 500은 아니다(round596 전역핸들러는 이 되돌림과 무관)",
            r_old9.status_code)
        chk(is_generic_overflow_msg(r_old9.get_json()),
            "★★★★★★ [4-A] 되돌린 옛 코드는 실제로 이 라우트 고유 문구를 못 내고 "
            "round596 전역핸들러의 범용 문구(BAD_INPUT)로 샌다 — 이 테스트가 진짜 "
            "결함을 잡아낼 능력이 있음을 증명", r_old9.get_json())
    finally:
        A.app.view_functions["api_dispatch_assign"] = NEW_VIEW9

    r_fixed9 = ac.post(f"/api/cases/{case_id}/dispatch/assign",
                       data='{"partner_id":1e400,"reason":"원복 확인"}',
                       content_type="application/json", headers=HDR)
    chk(r_fixed9.status_code == 400
        and not is_generic_overflow_msg(r_fixed9.get_json())
        and "배정할 업체" in (r_fixed9.get_json() or {}).get("error", ""),
        "  [4-A] 원상복구 확인 — 다시 이 라우트 고유의 안내문으로 정상 방어된다",
        r_fixed9.get_json())

    # [4-B] 헬퍼 레벨 — _attach_defect_photos (모듈 속성 직접 치환)
    OLD_ATTACH_SRC = '''
def _attach_defect_photos(conn, defect_id, case_id, photos, actor_name):
    if not photos:
        return 0
    n = 0
    for item in photos[:30]:
        if isinstance(item, dict):
            pid, note = item.get("photo_id"), _s(item.get("note"), 300)
        else:
            pid, note = item, ""
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        if not one(conn.execute("SELECT 1 x FROM photos WHERE id=? AND case_id=?",
                                (pid, case_id))):
            continue
        conn.execute(
            "INSERT OR IGNORE INTO defect_photos(defect_id, photo_id, note, marked_by, created_at) "
            " VALUES(?,?,?,?,?)", (defect_id, pid, note, actor_name, DB.now()))
        n += 1
    return n
'''
    _ns6 = dict(vars(A))
    exec(compile(OLD_ATTACH_SRC, "<round652_old:_attach_defect_photos>", "exec"), _ns6)
    OLD_FN6 = _ns6["_attach_defect_photos"]
    ORIG_FN6 = A._attach_defect_photos
    A._attach_defect_photos = OLD_FN6
    conn6b = DB.get_db()
    exc6_old = None
    try:
        A._attach_defect_photos(conn6b, defect_id, case_id,
                                 [{"photo_id": float("inf")}, {"photo_id": real_photo_id}],
                                 "되돌림검증")
    except Exception as e:                                          # noqa: BLE001
        exc6_old = e
    finally:
        conn6b.close()
        A._attach_defect_photos = ORIG_FN6
    chk(isinstance(exc6_old, OverflowError),
        "★★★★★★ [4-B] 되돌린(옛) _attach_defect_photos는 photo_id=inf에서 실제로 "
        "OverflowError를 그대로 던진다(그 뒤 정상 photo_id까지 통째로 유실) — "
        "이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", exc6_old)

    chk(A._attach_defect_photos is ORIG_FN6, "  [4-B] 원래 함수 객체로 복원됐다")
    conn6c = DB.get_db()
    n_restored = A._attach_defect_photos(
        conn6c, defect_id, case_id,
        [{"photo_id": float("inf")}, {"photo_id": real_photo_id}], "원복검증")
    conn6c.commit(); conn6c.close()
    chk(n_restored == 1,
        "  [4-B] 원복 후 다시 안전하게 동작한다(inf만 건너뛰고 정상 항목은 붙는다)",
        n_restored)

except Exception as e:                                              # noqa: BLE001
    import traceback
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

APP_HASH_AFTER = read("app.py")
chk(APP_HASH_AFTER == APP_SRC,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(모듈 속성 직접치환·view_functions 딕셔너리 항목치환만 사용 — "
    "디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
