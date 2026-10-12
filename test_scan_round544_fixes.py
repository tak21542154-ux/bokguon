# -*- coding: utf-8 -*-
"""스캔 544라운드 회귀 — 협력사·보험사 포털 "내 정보 수정"
   (api_partner_profile_update, PATCH /api/partner/profile · app.py:3138 부근 ·
    api_insurer_profile_update, PATCH /api/insurer/profile · app.py:3316 부근)이
   값이 하나도 안 바뀌어도 매번 UPDATE + "협력사/보험사 정보 수정" 감사로그를
   쏘던 결함.

   조사 배경 — 543라운드가 고친 "값이 안 바뀌어도 UPDATE+로그를 쏘는" 패턴을
   이번 라운드 지시가 예시로 들며 "협력사·보험사 포털의 '내 정보 수정' 화면도
   같은 패턴이 있는지" 보라고 했다. 직접 조사(하위위임 없음)한 결과 두 형제
   함수 모두에서 발견 —

     api_partner_profile_update(): ("ceo","phone","email","address","region")
     루프가 `if f in d:`(요청 본문에 그 키가 있는가)만 보고 무조건
     fields/vals/notes에 추가했다. prev 조회는 address·lat·lng만 가져와
     ceo/phone/email/region은 애초에 "이전 값과 비교"할 방법 자체가 없었다.

     api_insurer_profile_update(): prev 조회가 아예 없었다 — manager/dept/
     phone/email 네 필드 전부 "제출됐다"만 보고 무조건 UPDATE+로그.

   실사용 영향(추정이 아니라 프론트 코드로 확인) —
     partner_portal.html의 pSaveProfile()은 저장 버튼을 누르면
     ceo/phone/email/region/address 다섯 칸을 **손 안 댄 칸까지 항상 통째로**
     재전송한다. insurer_portal.html의 mi_save 리스너도 manager/dept/phone/
     email 네 칸을 마찬가지로 항상 통째로 재전송한다. 즉 이 앱을 쓰는
     협력사·보험사 담당자가 마이페이지를 열어 아무것도 고치지 않고 "저장"만
     눌러도 두 라우트 모두 예외 없이 거짓 "정보 수정" 감사로그를 남겼다
     (email 분기는 덤으로 email_source까지 매번 '직접입력'으로 재기록했다 —
     round299가 "본인이 직접 고친" 신호로 쓰려던 그 컬럼이 안 고쳐도 계속
     갱신되는 잡음이 됐다).

   고침 — 새 정책·새 헬퍼 없이, 이 세션이 참조한 형제
   (api_admin_update의 name 분기 · _sub_update_impl, 둘 다 "새값 != 옛값일
   때만 UPDATE+로그")와 똑같은 관례를 그대로 이식했다.
     · api_partner_profile_update: prev SELECT를 ceo/phone/email/address/
       region/lat/lng로 넓히고, 루프 안에서 `if v == ((prev or {}).get(f)
       or ""): continue`를 추가했다(app.py, 위 함수 내부). email_source
       재기록도 "email이 실제로 바뀐 필드 집합(changed)에 있을 때만"으로
       가드했다.
     · api_insurer_profile_update: prev SELECT 자체가 없었으므로 새로
       추가하고, 같은 `if v == ((prev or {}).get(f) or ""): continue`를
       이식했다.
   그 외 검증(RE_PHONE/RE_EMAIL 형식 검사)·biz_no 분기·좌표 초기화 분기·
   반환값·문구는 전혀 안 바꿨다.

   app.py 자신에 정의된 라우트 함수 두 개를 고쳤다 — import하는 별도
   모듈이 아니다. 이미 떠 있는 프로세스가 있다면 재시작해야 새 가드가
   실제 요청에 반영된다(파이썬은 이미 임포트한 모듈을 자동으로 다시
   읽지 않는다).

      python test_scan_round544_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile

#  ⚠ 윈도 기본 콘솔은 cp949 라 em dash(—) 같은 문자를 print 하면
#    UnicodeEncodeError 로 죽는다 — 형제 테스트(round537·541·542·543 등)가
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
print("  스캔 544라운드 회귀 — 협력사·보험사 마이페이지 저장이 무변경이어도")
print("  매번 UPDATE+감사로그를 쏘던 결함")
print("  (api_partner_profile_update · api_insurer_profile_update)")
print("=" * 72)

APP_SRC = read("app.py")

# ==================================================================
print("\n[0] 소스 — 고친 지점이 실제로 app.py 에 있는가"
      "(동시편집 세션이 되돌렸다면 여기서부터 정직하게 실패해야 한다)")
# ------------------------------------------------------------------
try:
    import ast as _ast
    chk(_ast.parse(APP_SRC) is not None, "STEP app.py 전체 ast.parse 성공")

    pp_body = _py_fn_body(APP_SRC, "api_partner_profile_update")
    chk('if v == ((prev or {}).get(f) or ""):' in pp_body,
        "★★★★★ api_partner_profile_update() 루프 안에 이전값 비교 가드가 있다"
        "(고치기 전엔 이 줄이 없었다)")
    chk('SELECT ceo, phone, email, address, region, lat, lng' in pp_body,
        "STEP prev 조회가 비교에 필요한 ceo/phone/email/region까지 넓어졌다"
        "(고치기 전엔 address·lat·lng뿐이었다)")
    chk('if "email" in changed:' in pp_body,
        "★★★★ email_source 재기록도 '실제로 바뀐 필드' 집합(changed)으로 "
        "가드된다(고치기 전엔 `if \"email\" in d:` 였다 — d에 있기만 하면 "
        "무조건 재기록)")
    _i_loop = pp_body.index('for f in ("ceo", "phone", "email", "address", "region"):')
    _i_guard = pp_body.index('if v == ((prev or {}).get(f) or ""):')
    _i_append = pp_body.index('fields.append(f"{f}=?"); vals.append(v); notes.append(f)')
    chk(_i_loop < _i_guard < _i_append,
        "★★★★ 순서가 옳다 — 루프 시작 → 이전값 비교 가드 → fields/notes 추가"
        "(가드가 append보다 먼저다)")
    #  형제 검사(RE_PHONE·RE_EMAIL)·biz_no 분기·좌표 분기는 이번 라운드가
    #  손대지 않았다 — 그대로 남아 있는지 대조(과잉수정 없음).
    chk('if f == "phone" and v and not RE_PHONE.match(v):' in pp_body
        and 'if f == "email" and v and not RE_EMAIL.match(v):' in pp_body,
        "STEP 형제 형식 검사(RE_PHONE·RE_EMAIL)는 무수정으로 그대로 남아 있다")
    chk('if "biz_no" in d:' in pp_body and "PORTAL_FORBIDDEN" in pp_body,
        "STEP biz_no 분기(중간관리자 게이트·write-once 409)도 무수정으로 "
        "그대로 남아 있다(과잉수정 없음)")
    #  ⚠⚠ [라운드606] 이 elif 분기 자체(round154, 좌표 미검색 시 옛 좌표를 지움)는
    #    544가 손대지 않은 그대로지만, 그 안의 address 비교식은 606에서 raw
    #    (d.get("address") or "").strip() → _s(d.get("address"))로 바뀌었다
    #    (형제결함군 — JSON 숫자 address에 AttributeError). elif 분기 구조 자체가
    #    무수정임을 확인하는 이 검사의 취지는 그대로 유지하고, 리터럴만 606
    #    이후의 정확한 소스로 갱신한다(약화 없음 — 여전히 정확히 이 elif가
    #    이 조건으로 존재하는지 본다).
    chk('elif ("address" in d and _s(d.get("address"))' in pp_body,
        "STEP 좌표 초기화 elif 분기(round154 구조 그대로, address 비교식은 "
        "round606이 _s()로 고침)가 남아 있다")

    ip_body = _py_fn_body(APP_SRC, "api_insurer_profile_update")
    chk('SELECT manager, dept, phone, email FROM insurers WHERE id=?' in ip_body,
        "★★★★★ api_insurer_profile_update() 에 prev 조회가 새로 생겼다"
        "(고치기 전엔 이 조회 자체가 아예 없었다)")
    chk('if v == ((prev or {}).get(f) or ""):' in ip_body,
        "★★★★★ api_insurer_profile_update() 에도 같은 이전값 비교 가드가 있다")
    _i_loop2 = ip_body.index('for f in ("manager", "dept", "phone", "email"):')
    _i_guard2 = ip_body.index('if v == ((prev or {}).get(f) or ""):')
    _i_append2 = ip_body.index('fields.append(f"{f}=?"); vals.append(v); notes.append(f)')
    chk(_i_loop2 < _i_guard2 < _i_append2,
        "★★★★ 순서가 옳다 — 루프 시작 → 이전값 비교 가드 → fields/notes 추가")
    chk('if f == "phone" and v and not RE_PHONE.match(v):' in ip_body
        and 'if f == "email" and v and not RE_EMAIL.match(v):' in ip_body,
        "STEP 형제 형식 검사는 무수정으로 그대로 남아 있다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드544 [0] 소스 확인", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[1] 준비 — 스크래치 DB, 협력사 2곳(현재코드용·구코드재현용)"
      " + 보험사 2곳(현재코드용·구코드재현용), 전부 실 값으로 생성")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round544_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r544-csrf"
H = {"X-CSRF-Token": CSRF}
A = DB = None
pid = pid_old = iid = iid_old = None

PARTNER_INIT = {"ceo": "김대표544", "phone": "010-1234-5678",
                "email": "partner544@test.com", "region": "서울",
                "address": "서울시 강남구 테헤란로 1"}
INSURER_INIT = {"manager": "박담당544", "dept": "보상1팀",
                 "phone": "010-9876-5432", "email": "insurer544@test.com"}


def _partner_client(target_pid):
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["partner_id"] = target_pid
        sess["partner_name"] = "협력사544"
        sess["_csrf"] = CSRF
    return c


def _insurer_client(target_iid):
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["insurer_id"] = target_iid
        sess["insurer_name"] = "보험사544"
        sess["_csrf"] = CSRF
    return c


def _log_count(conn, action, actor_like):
    return conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE action=? AND actor LIKE ?",
        (action, actor_like + "%")).fetchone()[0]


try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    cur = conn0.execute(
        "INSERT INTO partners(name, partner_type, login_id, password_hash, ceo, phone, "
        "email, address, region, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        ("테스트협력사544", "시공사", "partner544", "x", PARTNER_INIT["ceo"],
         PARTNER_INIT["phone"], PARTNER_INIT["email"], PARTNER_INIT["address"],
         PARTNER_INIT["region"], "활성", DB.now()))
    pid = cur.lastrowid
    cur_old = conn0.execute(
        "INSERT INTO partners(name, partner_type, login_id, password_hash, ceo, phone, "
        "email, address, region, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        ("테스트협력사544구코드", "시공사", "partner544old", "x", PARTNER_INIT["ceo"],
         PARTNER_INIT["phone"], PARTNER_INIT["email"], PARTNER_INIT["address"],
         PARTNER_INIT["region"], "활성", DB.now()))
    pid_old = cur_old.lastrowid

    cur2 = conn0.execute(
        "INSERT INTO insurers(name, org_type, login_id, password_hash, manager, dept, "
        "phone, email, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        ("테스트보험사544", "손해보험사", "insurer544", "x", INSURER_INIT["manager"],
         INSURER_INIT["dept"], INSURER_INIT["phone"], INSURER_INIT["email"],
         "활성", DB.now()))
    iid = cur2.lastrowid
    cur2_old = conn0.execute(
        "INSERT INTO insurers(name, org_type, login_id, password_hash, manager, dept, "
        "phone, email, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        ("테스트보험사544구코드", "손해보험사", "insurer544old", "x", INSURER_INIT["manager"],
         INSURER_INIT["dept"], INSURER_INIT["phone"], INSURER_INIT["email"],
         "활성", DB.now()))
    iid_old = cur2_old.lastrowid
    conn0.commit(); conn0.close()
    chk(bool(pid and pid_old and iid and iid_old),
        "STEP 협력사 2곳 + 보험사 2곳 시드 생성", (pid, pid_old, iid, iid_old))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드544 [1] 준비", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[2] 실행(진짜 라우트, 지금 코드) — 협력사 마이페이지 저장 버튼이 "
      "실제로 보내는 것과 같은 payload(손 안 댄 칸까지 통째로 재전송)를 그대로 "
      "다시 보내도 거짓 '협력사 정보 수정' 로그가 안 생긴다")
# ------------------------------------------------------------------
try:
    pc = _partner_client(pid)
    r = pc.patch("/api/partner/profile", json=PARTNER_INIT, headers=H)
    rbody = r.get_json() or {}
    chk(r.status_code == 200 and rbody.get("ok") is True,
        "STEP PATCH /api/partner/profile 200·ok:true", (r.status_code, rbody))
    chk(rbody.get("unchanged") is True,
        "★★★★★ 지금 코드: 동일 값 재전송은 unchanged:true 를 돌려준다", rbody)

    conn = DB.get_db()
    n_log = _log_count(conn, "협력사 정보 수정", "협력사544")
    chk(n_log == 0,
        "★★★★★ 지금 코드: 아무것도 안 바뀌었으므로 '협력사 정보 수정' 로그가 "
        "0건이다(고치기 전엔 매번 1건이 났다)", n_log)
    row = conn.execute("SELECT email_source FROM partners WHERE id=?", (pid,)).fetchone()
    chk(row[0] is None,
        "STEP email_source 도 안 건드렸다(이메일 값이 그대로인데 '직접입력'으로 "
        "덮어쓰지 않는다)", row[0])
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드544 [2] 협력사 무변경 재저장", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[3] 회귀 안전 — region 한 칸만 실제로 바뀌면 지금 코드도 정상적으로 "
      "'협력사 정보 수정: region' 로그를 정확히 1건 남긴다(과잉교정 없음)")
# ------------------------------------------------------------------
try:
    pc2 = _partner_client(pid)
    payload3 = dict(PARTNER_INIT, region="경기")
    r2 = pc2.patch("/api/partner/profile", json=payload3, headers=H)
    rbody2 = r2.get_json() or {}
    chk(r2.status_code == 200 and rbody2.get("ok") is True and not rbody2.get("unchanged"),
        "STEP region만 변경 — 200·ok:true·unchanged 아님", rbody2)

    conn = DB.get_db()
    row = conn.execute("SELECT region, ceo, phone, email FROM partners WHERE id=?",
                        (pid,)).fetchone()
    chk(row[0] == "경기", "STEP DB region 실제로 바뀜", row[0])
    chk(row[1] == PARTNER_INIT["ceo"] and row[2] == PARTNER_INIT["phone"]
        and row[3] == PARTNER_INIT["email"],
        "STEP 나머지 필드는 그대로(무변경 필드 오염 없음)", tuple(row))

    detail_row = conn.execute(
        "SELECT detail FROM activity_log WHERE action='협력사 정보 수정' "
        "AND actor LIKE '협력사544%' ORDER BY id DESC LIMIT 1").fetchone()
    chk(bool(detail_row) and detail_row[0] == "region",
        "★★★★ 실제 변경 로그는 정확히 바뀐 필드(region)만 담는다"
        "(ceo·phone·email·address는 안 끼어든다)", detail_row[0] if detail_row else None)
    n_log_total = _log_count(conn, "협력사 정보 수정", "협력사544")
    chk(n_log_total == 1,
        "★★★★ 무변경 재저장([2])까지 합쳐도 로그는 총 1건뿐이다", n_log_total)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드544 [3] 협력사 실변경(region)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[4] 회귀 안전 — 이메일이 실제로 바뀌면 email_source도 '직접입력'으로 "
      "정상 갱신되고, 로그도 정확히 남는다(과잉교정 없음)")
# ------------------------------------------------------------------
try:
    pc3 = _partner_client(pid)
    payload4 = dict(PARTNER_INIT, region="경기", email="new544@test.com")
    r3 = pc3.patch("/api/partner/profile", json=payload4, headers=H)
    rbody3 = r3.get_json() or {}
    chk(r3.status_code == 200 and rbody3.get("ok") is True,
        "STEP email만 변경(region은 [3]이 만든 현재값 '경기' 그대로 재전송) — "
        "200·ok:true", rbody3)
    conn = DB.get_db()
    row = conn.execute("SELECT email, email_source FROM partners WHERE id=?",
                        (pid,)).fetchone()
    chk(row[0] == "new544@test.com" and row[1] == "직접입력",
        "STEP email 갱신 + email_source='직접입력' 정상 반영", tuple(row))
    detail_row4 = conn.execute(
        "SELECT detail FROM activity_log WHERE action='협력사 정보 수정' "
        "AND actor LIKE '협력사544%' ORDER BY id DESC LIMIT 1").fetchone()
    chk(bool(detail_row4) and detail_row4[0] == "email",
        "STEP 이번 로그도 정확히 바뀐 필드(email)만 담는다(region은 [3]에서 "
        "이미 '경기'로 저장돼 있어 이번엔 무변경 — 끼어들지 않는다)",
        detail_row4[0] if detail_row4 else None)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드544 [4] 협력사 이메일 실변경", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[5] 실행(진짜 라우트, 지금 코드) — 보험사 마이페이지도 같은 무변경 "
      "재저장이면 거짓 '보험사 정보 수정' 로그가 안 생긴다")
# ------------------------------------------------------------------
try:
    ic = _insurer_client(iid)
    r5 = ic.patch("/api/insurer/profile", json=INSURER_INIT, headers=H)
    rbody5 = r5.get_json() or {}
    chk(r5.status_code == 200 and rbody5.get("ok") is True and rbody5.get("unchanged") is True,
        "STEP 보험사 동일 값 재전송 — 200·ok:true·unchanged:true", rbody5)

    conn = DB.get_db()
    n_log_i = _log_count(conn, "보험사 정보 수정", "보험사544")
    chk(n_log_i == 0,
        "★★★★★ 지금 코드: 보험사도 무변경 재저장이면 로그 0건"
        "(고치기 전엔 prev 조회 자체가 없어 매번 1건 났다)", n_log_i)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드544 [5] 보험사 무변경 재저장", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[6] 회귀 안전 — 보험사 dept 한 칸만 실제로 바뀌면 정상적으로 1건 로그")
# ------------------------------------------------------------------
try:
    ic2 = _insurer_client(iid)
    payload6 = dict(INSURER_INIT, dept="보상2팀")
    r6 = ic2.patch("/api/insurer/profile", json=payload6, headers=H)
    rbody6 = r6.get_json() or {}
    chk(r6.status_code == 200 and rbody6.get("ok") is True and not rbody6.get("unchanged"),
        "STEP dept만 변경 — 200·ok:true·unchanged 아님", rbody6)
    conn = DB.get_db()
    row = conn.execute("SELECT dept, manager, phone, email FROM insurers WHERE id=?",
                        (iid,)).fetchone()
    chk(row[0] == "보상2팀", "STEP DB dept 실제로 바뀜", row[0])
    chk(row[1] == INSURER_INIT["manager"] and row[2] == INSURER_INIT["phone"]
        and row[3] == INSURER_INIT["email"],
        "STEP 나머지 필드는 그대로", tuple(row))
    detail_row_i = conn.execute(
        "SELECT detail FROM activity_log WHERE action='보험사 정보 수정' "
        "AND actor LIKE '보험사544%' ORDER BY id DESC LIMIT 1").fetchone()
    chk(bool(detail_row_i) and detail_row_i[0] == "dept",
        "★★★★ 실제 변경 로그는 정확히 바뀐 필드(dept)만 담는다",
        detail_row_i[0] if detail_row_i else None)
    n_log_i_total = _log_count(conn, "보험사 정보 수정", "보험사544")
    chk(n_log_i_total == 1, "★★★★ 무변경([5])까지 합쳐도 로그는 총 1건뿐", n_log_i_total)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드544 [6] 보험사 실변경(dept)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[7] 원인 재현 — app.py·run_all_tests.py 는 건드리지 않고, 이번 수정 "
      "직전의 실제 함수 본문을 문자열로 재구성해(exec, round543과 같은 방식) "
      "완전히 손대지 않은 별도 협력사에 같은 '무변경 재전송' 시나리오를 "
      "실행하면 옛 코드는 정말 거짓 로그를 남기는가")
# ------------------------------------------------------------------
#  ⚠ 이 문자열은 이번 수정 **직전** 이 세션이 Read 로 확인한
#    api_partner_profile_update 원문 그대로다 — 이전값 비교 가드가 없는 옛 형태다.
_PRE544_PARTNER_SRC = '''
def _api_partner_profile_update_pre544():
    d = body()
    conn = DB.get_db()
    prev = one(conn.execute("SELECT address, lat, lng FROM partners WHERE id=?",
                            (session["partner_id"],)))
    fields, vals, notes = [], [], []
    for f in ("ceo", "phone", "email", "address", "region"):
        if f in d:
            v = (d.get(f) or "").strip()[:120]
            if f == "phone" and v and not RE_PHONE.match(v):
                conn.close()
                return jsonify({"ok": False, "error": f"연락처 형식이 올바르지 않습니다: {v}"}), 400
            if f == "email" and v and not RE_EMAIL.match(v):
                conn.close()
                return jsonify({"ok": False, "error": f"이메일 형식이 올바르지 않습니다: {v}"}), 400
            fields.append(f"{f}=?"); vals.append(v); notes.append(f)
    if "email" in d:
        fields.append("email_source=?"); vals.append("직접입력")
    if "biz_no" in d:
        if PORTAL_ROLE_RANK.get(_portal_role(), 0) < PORTAL_ROLE_RANK["중간관리자"]:
            conn.close()
            return jsonify({"ok": False, "code": "PORTAL_FORBIDDEN",
                            "error": "사업자번호 등록은 중간관리자 이상만 할 수 있습니다. "
                                     "한 번 등록하면 운영팀을 통해야만 바꿀 수 있습니다."}), 403
        _cur = one(conn.execute("SELECT COALESCE(biz_no,'') AS b FROM partners WHERE id=?",
                                (session["partner_id"],)))
        if (_cur or {}).get("b", "").strip():
            conn.close()
            return jsonify({"ok": False,
                            "error": "사업자번호는 이미 등록되어 있어 여기서 바꿀 수 없습니다. "
                                     "변경이 필요하면 담당자에게 알려 주세요."}), 409
        _bz = re.sub(r"[^0-9]", "", d.get("biz_no") or "")
        if _bz:
            if not valid_biz_no(_bz):
                conn.close()
                return jsonify({"ok": False,
                                "error": "사업자등록번호가 올바르지 않습니다. "
                                         "10자리 숫자를 다시 확인해 주세요."}), 400
            fields.append("biz_no=?"); vals.append(_bz); notes.append("사업자번호")
    lat, lng = _picked_coords(d)
    if lat is not None:
        fields += ["lat=?", "lng=?", "geo_src=?"]
        vals += [lat, lng, "주소검색"]
        notes.append("좌표")
    elif ("address" in d and (d.get("address") or "").strip() != ((prev or {}).get("address") or "")
          and ((prev or {}).get("lat") is not None or (prev or {}).get("lng") is not None)):
        fields += ["lat=NULL", "lng=NULL", "geo_src=NULL"]
        notes.append("주소 변경 — 좌표 초기화")
    if not fields:
        conn.close(); return jsonify({"ok": True, "unchanged": True})
    vals.append(session["partner_id"])
    conn.execute(f"UPDATE partners SET {','.join(fields)} WHERE id=?", vals)
    DB.log(conn, portal_actor(), "협력사 정보 수정", ", ".join(notes))
    conn.commit(); conn.close()
    return jsonify({"ok": True})
'''
try:
    _ns = dict(vars(A))              # app 모듈 네임스페이스 복사(진짜 모듈은 안 건드림)
    exec(compile(_PRE544_PARTNER_SRC, "<round544_partner_pre>", "exec"), _ns)
    _old_partner_update = _ns["_api_partner_profile_update_pre544"]

    with A.app.test_request_context("/api/partner/profile", method="PATCH",
                                     json=PARTNER_INIT):
        from flask import session as _flask_session
        _flask_session["partner_id"] = pid_old
        #  ⚠ [2]~[4]의 "협력사544"와 겹치지 않는 별도 actor를 쓴다 — 같은
        #    이름을 쓰면 activity_log LIKE 조회가 두 시나리오의 로그를 함께
        #    세어 "옛 코드가 정확히 1건만 더 남긴다"는 인과관계를 흐린다.
        _flask_session["partner_name"] = "구코드협력사544"
        resp = _old_partner_update()
    resp_obj = resp[0] if isinstance(resp, tuple) else resp
    chk(resp_obj is not None, "STEP 재구성한 옛 협력사 함수도 정상적으로 응답을 만든다")

    conn = DB.get_db()
    row_old = conn.execute("SELECT ceo FROM partners WHERE id=?", (pid_old,)).fetchone()
    chk(row_old[0] == PARTNER_INIT["ceo"],
        "STEP 옛 코드(재구성)도 값 자체는 그대로 저장한다(겉보기 동작은 지금 "
        "코드와 똑같다 — 그래서 그동안 아무도 눈치 못 챘다)")
    n_old = _log_count(conn, "협력사 정보 수정", "구코드협력사544")
    chk(n_old == 1,
        "★★★★★ 그런데 옛 코드(재구성)는 완전히 손대지 않은 협력사에 값이 "
        "전혀 안 바뀐 payload를 그대로 재전송해도 '협력사 정보 수정' 거짓 "
        "로그를 1건 남긴다 — 지금 코드(위 [2])는 같은 시나리오에서 실제로 "
        "0건이었다. 이 차이가 이 회귀가 실제로 결함을 잡아낼 능력이 있다는 "
        "인과관계 증명이다", n_old)
    detail_old = conn.execute(
        "SELECT detail FROM activity_log WHERE action='협력사 정보 수정' "
        "AND actor LIKE '구코드협력사544%' ORDER BY id DESC LIMIT 1").fetchone()
    chk(bool(detail_old) and detail_old[0] == "ceo, phone, email, address, region",
        "★★★★ 거짓 로그가 다섯 필드 전부를 '바뀌었다'고 우긴다(실제로는 "
        "하나도 안 바뀜) — pSaveProfile()이 항상 통째로 재전송하는 것과 "
        "정확히 같은 다섯 필드", detail_old[0] if detail_old else None)
    row_es = conn.execute("SELECT email_source FROM partners WHERE id=?",
                           (pid_old,)).fetchone()
    chk(row_es[0] == "직접입력",
        "STEP 덤으로 email_source도 무변경인데 매번 재기록됐다(옛 코드의 "
        "두 번째 증상)", row_es[0])
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드544 [7] 원인 재현(옛 협력사 코드)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[8] 원인 재현 — 보험사도 같은 방식(exec 재구성)으로, 완전히 손대지 "
      "않은 별도 보험사에 무변경 재전송을 실행하면 옛 코드는 prev 조회 자체가 "
      "없어 정말 거짓 로그를 남기는가")
# ------------------------------------------------------------------
_PRE544_INSURER_SRC = '''
def _api_insurer_profile_update_pre544():
    d = body()
    conn = DB.get_db()
    fields, vals, notes = [], [], []
    for f in ("manager", "dept", "phone", "email"):
        if f in d:
            v = (d.get(f) or "").strip()[:80]
            if f == "phone" and v and not RE_PHONE.match(v):
                conn.close()
                return jsonify({"ok": False, "error": f"연락처 형식이 올바르지 않습니다: {v}"}), 400
            if f == "email" and v and not RE_EMAIL.match(v):
                conn.close()
                return jsonify({"ok": False, "error": f"이메일 형식이 올바르지 않습니다: {v}"}), 400
            fields.append(f"{f}=?"); vals.append(v); notes.append(f)
    if not fields:
        conn.close(); return jsonify({"ok": True, "unchanged": True})
    vals.append(session["insurer_id"])
    conn.execute(f"UPDATE insurers SET {','.join(fields)} WHERE id=?", vals)
    DB.log(conn, portal_actor(), "보험사 정보 수정", ", ".join(notes))
    conn.commit(); conn.close()
    return jsonify({"ok": True})
'''
try:
    _ns2 = dict(vars(A))
    exec(compile(_PRE544_INSURER_SRC, "<round544_insurer_pre>", "exec"), _ns2)
    _old_insurer_update = _ns2["_api_insurer_profile_update_pre544"]

    with A.app.test_request_context("/api/insurer/profile", method="PATCH",
                                     json=INSURER_INIT):
        from flask import session as _flask_session2
        _flask_session2["insurer_id"] = iid_old
        #  ⚠ [5]~[6]의 "보험사544"와 겹치지 않는 별도 actor를 쓴다(위 협력사
        #    쪽과 같은 이유 — LIKE 조회의 교차 집계를 막는다).
        _flask_session2["insurer_name"] = "구코드보험사544"
        resp_i = _old_insurer_update()
    resp_i_obj = resp_i[0] if isinstance(resp_i, tuple) else resp_i
    chk(resp_i_obj is not None, "STEP 재구성한 옛 보험사 함수도 정상적으로 응답을 만든다")

    conn = DB.get_db()
    n_old_i = _log_count(conn, "보험사 정보 수정", "구코드보험사544")
    chk(n_old_i == 1,
        "★★★★★ 옛 코드(재구성, prev 조회 자체가 없음)는 완전히 손대지 않은 "
        "보험사에 무변경 payload를 재전송해도 '보험사 정보 수정' 거짓 로그를 "
        "1건 남긴다 — 지금 코드(위 [5])는 같은 시나리오에서 0건이었다", n_old_i)
    detail_old_i = conn.execute(
        "SELECT detail FROM activity_log WHERE action='보험사 정보 수정' "
        "AND actor LIKE '구코드보험사544%' ORDER BY id DESC LIMIT 1").fetchone()
    chk(bool(detail_old_i) and detail_old_i[0] == "manager, dept, phone, email",
        "★★★★ 거짓 로그가 네 필드 전부를 '바뀌었다'고 우긴다(실제로는 하나도 "
        "안 바뀜)", detail_old_i[0] if detail_old_i else None)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드544 [8] 원인 재현(옛 보험사 코드)", f"{type(e).__name__} {e}")


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
