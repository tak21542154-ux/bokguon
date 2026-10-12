# -*- coding: utf-8 -*-
"""스캔 566라운드 회귀 — 협력사 안내표시 일괄(api_partner_invite, POST
   /api/partners/invite)이 배치 전체를 잠그는 형제(api_partner_bulk_credentials,
   라운드494)와 달리 BEGIN IMMEDIATE 가 없어, 겹치는 두 요청이 같은 업체에게
   "계정 안내" 알림톡을 두 번 내보내던 결함.

   조사 각도 — "ids 배열을 받는 관리자 일괄(bulk) 작업이 단건 라우트와 같은
   트랜잭션 규율을 지키는가"를 app.py 전수(grep 'body().get("ids")')로 훑었다.
   네 곳(api_partner_bulk_credentials·api_settlements_paid_bulk·
   api_outbox_send_selected·api_partner_invite) 중 앞의 셋은 이미 배치 전체를
   BEGIN IMMEDIATE 로 잠그거나(정산 일괄확인) 공유 헬퍼(sweep_send_notifications)
   자신이 건별로 원자적인데, api_partner_invite 만 그 방어가 없었다.

   결함(수정 전 app.py, api_partner_invite) — conn = DB.get_db() 뒤 반복문을
   바로 도는데 BEGIN IMMEDIATE 가 없다. 반복 안의 "이미 안내함" 판정
   (if p["invited_at"]:, 라운드250이 추가)은 잠금 없는 평범한 SELECT 라서, 두
   요청(관리자 화면 연타, 또는 겹치는 선택으로 admin 탭 두 개가 동시 제출)이
   같은 업체를 동시에 훑으면 둘 다 커밋 전에 invited_at=NULL 을 읽어 가드를
   나란히 통과한다. notify() 는 단순 INSERT 라 중복 방지 수단이 없어(app.py
   1947행 부근) 그 업체에게 "계정이 준비되었습니다" 알림톡이 실제로 두 번
   나간다. 형제 api_partner_bulk_credentials 는 정확히 같은 성격의 결함을 이미
   라운드494 가 "배치 전체를 하나로 잠가 다른 발급 요청과 겹치는 창을 없앤다"며
   막았는데, 그 잠금이 이 라우트에는 이식되지 않았다.

   영향 범위(과장하지 않는다) — 내부 관리자 전용 화면(@require_role('하위관리자'))
   이라 외부 공격면은 아니다. 다만 실제로 나가는 알림톡 비용이 중복되고,
   업체 쪽에서는 "왜 안내 문자가 두 번 오나" 하는 혼란을 남긴다 — 라운드494가
   이미 같은 무게로 다룬 것과 같은 수준의 실피해(운영 잡음·비용)다.

   고침 — app.py: api_partner_invite() 에서 conn = DB.get_db() 다음,
   live = bool(...) 계산 바로 뒤에 conn.execute("BEGIN IMMEDIATE") 를 추가했다
   (형제 api_partner_bulk_credentials·라운드494 와 정확히 같은 자리·같은 방식 —
   헬퍼가 아니라 호출부에서 배치 전체를 한 번에 잠근다). 안의 SAVEPOINT 중첩
   (라운드430)은 이미 이런 외부 트랜잭션 안에 들어와도 안전하다고 증명된
   패턴(api_partner_bulk_credentials 자신)이라 그대로 둔다.

   테스트 기법 — on-disk app.py 는 조회만 한다. "되돌리기" 증명은 이 세션이
   고치기 **직전** Read 로 확인한 원문(BEGIN IMMEDIATE 없는 버전)을 문자열로
   재구성해 exec() 한 것이며, 실제 파일에는 절대 쓰지 않는다(round543/547/549/
   550/553 과 같은 기법). 동시성 재현은 round494 가 쓴 "DB.get_db() 를 감싸
   특정 SELECT 를 가로채는 Probe"와 round553 이 쓴 threading.Barrier 를 함께
   쓴다 — 두 스레드를 요청 시작점에서 한 번(진입 배리어), 그리고 문제의
   SELECT 직전에서 다시 한 번(전용 배리어, round494 의 고정 time.sleep() 을
   대체 — 이유는 make_delay_probe() 자체 docstring 참고) 서로 기다리게 해
   스레드 스케줄링 운이 아니라 결정론적으로 "같은 순간에 그 SELECT 를
   실행했다"를 만든다. 각 스레드는 Flask test_request_context +
   세션 수동 설정으로 뷰 함수(신버전은 A.api_partner_invite, 구버전은 exec 로
   재구성한 함수)를 직접 호출한다 — HTTP 서버·소켓·서브프로세스 없이 같은
   프로세스 안에서 진행한다. 실제 팝빌 발송(POPBILL.send)은 이 라우트
   어디에서도 호출되지 않는다(notify() 는 'notifications' 표에 상태='발송대기'
   행을 적재만 한다 — 실발송은 별도 스윕이 한다) 이므로 live=True 로 둬도
   외부로 나가는 통신은 없다.

      python test_scan_round566_fixes.py
"""
import io
import os
import sys
import tempfile
import threading

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
print("  스캔 566라운드 회귀 — 협력사 안내표시 일괄(api_partner_invite) BEGIN IMMEDIATE 누락")
print("=" * 72)

APP_SRC = read("app.py")

# ==================================================================
print("\n[0] 소스 확인 — 고친 지점이 실제로 app.py 에 있는가"
      "(동시편집 세션이 되돌렸다면 여기서부터 정직하게 실패해야 한다)")
# ------------------------------------------------------------------
try:
    import ast as _ast
    chk(_ast.parse(APP_SRC) is not None, "STEP app.py 전체 ast.parse 성공")

    #  ⚠ 이 함수와 다음 @app. 라우트 사이에는 데코레이터 없는 헬퍼 함수·데이터
    #    상수가 여럿 끼어 있어(운영 점검 화면 준비 코드), 범용 헬퍼(_py_fn_body,
    #    "다음 @app." 까지 통째로 삼킴)로 자르면 그 헬퍼들 안의 다른
    #    "BEGIN IMMEDIATE" 까지 같이 잡혀 개수 검사가 왜곡된다 — 이 함수 고유의
    #    반환문을 끝 표식으로 써서 정확히 이 함수만 자른다.
    _start = APP_SRC.index('@app.post("/api/partners/invite")')
    _end_marker = ('"sent": sent, "notify_live": live})\n')
    _end = APP_SRC.index(_end_marker, _start) + len(_end_marker)
    fn_body = APP_SRC[_start:_end]
    chk("def api_partner_invite" in fn_body,
        "STEP api_partner_invite() 함수 본문을 추출했다")
    chk("BEGIN IMMEDIATE" in fn_body,
        "★★★★★ api_partner_invite() 안에 BEGIN IMMEDIATE 가 있다(고치기 전엔 없었다)")
    _i_begin = fn_body.index("BEGIN IMMEDIATE")
    _i_loop = fn_body.index("for pid in ids:")
    chk(_i_begin < _i_loop,
        "STEP BEGIN IMMEDIATE 가 반복문보다 앞에 있다(배치 전체를 한 번에 잠근다)")
    chk('if p["invited_at"]:' in fn_body,
        "  회귀 방지: 라운드250의 '이미 안내함' 가드는 그대로 남아 있다")
    chk('conn.execute("SAVEPOINT invite_notify")' in fn_body,
        "  회귀 방지: 라운드430의 SAVEPOINT(알림 인프라 오류만 국소 롤백)도 그대로다")
    #  ⚠ 이 함수 자신에 붙인 라운드566 설명 주석이 "BEGIN IMMEDIATE"라는 문구를
    #    산문으로도 한 번 언급하므로(코드 자리와 합쳐 문자열 단순 등장 횟수는
    #    2), 실행문(conn.execute("BEGIN IMMEDIATE")) 개수만 정확히 센다.
    chk(fn_body.count('conn.execute("BEGIN IMMEDIATE")') == 1,
        "STEP conn.execute(\"BEGIN IMMEDIATE\") 실행문은 정확히 1곳뿐이다(중복 삽입 아님)")

    # 형제 확인 — 라운드494가 이미 잠근 곳은 이번 수정과 무관하게 그대로인지 대조
    sib_body = _py_fn_body(APP_SRC, "api_partner_bulk_credentials")
    chk(sib_body.count("BEGIN IMMEDIATE") == 1,
        "STEP 형제 api_partner_bulk_credentials() 의 BEGIN IMMEDIATE 는 여전히 1곳"
        "(이번 라운드가 안 건드림)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드566 [0] 소스 확인", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[1] 준비 — 격리 스크래치 DB · 관리자 세션")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round566_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r566-csrf"
A = DB = None

try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('admin566','x','실행계정566','최고관리자')")
    conn0.commit(); conn0.close()
    chk(True, "STEP 스크래치 DB·관리자 계정 준비 완료")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드566 [1] 준비", f"{type(e).__name__} {e}")


def mkpartner(login_id, name, phone="010-2222-3333"):
    c = DB.get_db()
    c.execute(
        "INSERT INTO partners(name, partner_type, login_id, password_hash, ceo, phone, "
        "email, address, region, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (name, "시공사", login_id, "x", "김대표", phone,
         f"{login_id}@test.com", "서울시 강남구", "서울", "활성", DB.now()))
    c.commit()
    pid = c.execute("SELECT id FROM partners WHERE login_id=?", (login_id,)).fetchone()["id"]
    c.close()
    return pid


def _call_with_session(fn, payload):
    """fn 을 관리자 세션이 실린 test_request_context 안에서 호출하고 (status, json) 을 돌려준다."""
    with A.app.test_request_context("/api/partners/invite", method="POST", json=payload):
        from flask import session as _s
        _s["admin"] = "admin566"
        _s["admin_name"] = "실행계정566"
        _s["admin_role"] = "최고관리자"
        _s["_csrf"] = CSRF
        resp = fn()
    if isinstance(resp, tuple):
        resp_obj, code = resp[0], resp[1]
    else:
        resp_obj, code = resp, 200
    return code, resp_obj.get_json()


# ── 실발송 게이트만 True 로(실제 외부 통신은 없다 — notify() 는 로컬 INSERT 뿐) ──
_orig_notify_enabled = A.NOTIFY_ENABLED if A else None
_orig_popbill_ready = A.POPBILL.ready if A else None
if A:
    A.NOTIFY_ENABLED = True
    A.POPBILL.ready = lambda: True


# ==================================================================
print("\n[2] 순차 회귀 안전 — 동시성이 없을 때는 지금까지와 똑같이 동작하는가")
# ------------------------------------------------------------------
try:
    p_seq = mkpartner("r566seq", "R566순차업체")
    code1, body1 = _call_with_session(A.api_partner_invite, {"ids": [p_seq]})
    chk(code1 == 200 and body1.get("ok") is True and len(body1.get("marked") or []) == 1,
        "STEP 첫 안내표시는 정상적으로 200·marked 1곳", (code1, body1))
    chk(body1.get("sent") == 1,
        "STEP 첫 안내표시는 실제로 1건 발송(기록)했다(live=True·번호 있음·수신거부 아님)", body1)

    code2, body2 = _call_with_session(A.api_partner_invite, {"ids": [p_seq]})
    skipped2 = body2.get("skipped") or []
    chk(code2 == 200 and len(skipped2) == 1 and skipped2[0].get("why") == "이미 안내함",
        "STEP 같은 업체를 순차로 다시 요청하면 '이미 안내함'으로 건너뛴다(회귀 없음)",
        (code2, body2))

    n_notif_seq = DB.get_db().execute(
        "SELECT COUNT(*) c FROM notifications WHERE partner_id=? AND ntype='계정안내'",
        (p_seq,)).fetchone()["c"]
    chk(n_notif_seq == 1,
        "STEP 순차 상황에서는 '계정안내' 알림이 정확히 1건만 쌓인다", n_notif_seq)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드566 [2] 순차 회귀 안전", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[3]+[4] 실제 동시요청 — 지금 코드는 정확히 한 번만 보내는가, "
      "옛 코드(재구성)는 정말 두 번 보내 버리는가")
# ------------------------------------------------------------------
def make_delay_probe(match_sql_substr, n=2):
    """DB.get_db() 가 돌려주는 커넥션을 감싸, 지정한 SQL 이 실행되기 **직전**에
    n개 스레드를 서로 기다리게 한다(전용 threading.Barrier) — round494 의 고정
    time.sleep() 지연을 한 단계 더 결정론적으로 강화한 변형이다.

    ⚠ 처음엔 round494 그대로 "SELECT 직전에 고정 0.3초씩 잔다"로 짰는데, 실측해
      보니 재현이 안 됐다(둘 다 정직하게 하나만 marked 로 끝남 — 옛 코드인데도
      직렬화된 것처럼 보였다). 원인 — 두 스레드가 **같은 고정 시간**만큼만 자면,
      깨어나는 시각도 나란히 비슷해서 스레드 A가 먼저 깨어나 SELECT 이후
      나머지(알림 INSERT·UPDATE·commit, 전부 지연 없음)를 눈 깜짝할 사이에 끝내
      버리면, 스레드 B가 깨어나 SELECT 를 실행하는 시점엔 A가 이미 커밋을
      끝낸 뒤였다 — "동시에 잠들었다"가 "동시에 그 SELECT 를 실행했다"를
      보장하지 않았다. 전용 배리어를 쓰면 n개 스레드 **전부가 이 SELECT 직전에
      도착해야만** 그 다음으로 넘어가므로, 실행 자체가 진짜로 같은 순간에
      일어난다 — 그 뒤 어느 쪽이 커밋을 먼저 끝내든, 이미 둘 다 상대의 커밋
      전 값을 읽은 뒤다. 실제 앱 코드는 전혀 건드리지 않는다(연결 래퍼만 테스트
      프로세스 메모리 안에서 교체).
    """
    hit = {"n": 0}
    lock = threading.Lock()
    barrier = threading.Barrier(n)

    class _Probe:
        def __init__(self, real):
            self._real = real

        def execute(self, sql, params=()):
            if match_sql_substr in sql:
                with lock:
                    hit["n"] += 1
                try:
                    barrier.wait(timeout=5)
                except threading.BrokenBarrierError:
                    pass          # 상대 스레드가 이미 예외로 죽었으면 혼자라도 진행한다
            return self._real.execute(sql, params)

        def __getattr__(self, name):
            return getattr(self._real, name)

    return _Probe, hit


def _race(fn, pid, n=2):
    barrier = threading.Barrier(n)
    results = [None] * n

    def _worker(idx):
        try:
            barrier.wait(timeout=5)
            results[idx] = _call_with_session(fn, {"ids": [pid]})
        except Exception as e:                                      # noqa: BLE001
            results[idx] = ("EXC", f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    return results


_MATCH = "COALESCE(sms_opt_out,0) so"     # api_partner_invite 안에서 유일하게 등장하는 표현(app.py 전수 확인)
_real_get_db = DB.get_db

try:
    # ── [3] 지금 코드(실제 함수, 실제 라우트가 그대로 참조하는 그 객체) ──
    p_new = mkpartner("r566race_new", "R566동시요청업체(신버전)")
    _Probe, hit_new = make_delay_probe(_MATCH)
    try:
        DB.get_db = lambda: _Probe(_real_get_db())
        res_new = _race(A.api_partner_invite, p_new, 2)
    finally:
        DB.get_db = _real_get_db

    chk(hit_new["n"] == 2,
        "STEP 지금 코드: 두 요청 모두 문제의 SELECT 지점까지 동시 도달했다"
        "(지연 프로브를 실제로 밟았다)", hit_new)
    chk(all(isinstance(r, tuple) and r[0] != "EXC" for r in res_new),
        "STEP 지금 코드: 두 요청 모두 예외 없이 응답했다", res_new)
    codes_new = sorted(str(r[0]) for r in res_new)
    chk(codes_new == ["200", "200"],
        "STEP 지금 코드: 이 라우트는 실패해도 200이다(marked/skipped 목록으로 구분) — "
        "둘 다 200으로 응답했다", res_new)

    n_marked_new = sum(len((r[1].get("marked") or [])) for r in res_new)
    n_notif_new = _real_get_db().execute(
        "SELECT COUNT(*) c FROM notifications WHERE partner_id=? AND ntype='계정안내'",
        (p_new,)).fetchone()["c"]
    chk(n_marked_new == 1,
        "★★★★★ 지금 코드: 동시에 부딪힌 두 요청 중 정확히 하나만 marked(표시)됐다 "
        "(BEGIN IMMEDIATE 가 배치를 직렬화해, 나중 요청은 상대가 막 커밋한 invited_at 을 "
        "보고 스스로 '이미 안내함'으로 건너뛴다)", res_new)
    chk(n_notif_new == 1,
        "★★★★★ 지금 코드: '계정안내' 알림톡이 정확히 1건만 기록된다"
        "(옛 코드는 바로 아래 [4]에서 2건이 생김을 실측한다)", n_notif_new)

    # ══════════════════════════════════════════════════════════
    print("\n[4] 되돌리기 증명 — 옛(BEGIN IMMEDIATE 없는) 버전을 문자열로 재구성해 exec()")
    # ──────────────────────────────────────────────────────────
    #  ⚠ on-disk app.py 는 절대 건드리지 않는다. 이 세션이 고치기 **직전** Read 로
    #    확인한 원문 그대로를 옮긴 것이다.
    _PRE566_SRC = '''
def _api_partner_invite_pre566():
    ids = body().get("ids") or []
    if not isinstance(ids, list) or not ids:
        return jsonify({"ok": False, "error": "업체를 하나 이상 골라 주세요."}), 400
    try:
        ids = [int(x) for x in ids][:300]
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "업체 번호가 올바르지 않습니다."}), 400

    conn = DB.get_db()
    live = bool(NOTIFY_ENABLED and POPBILL.ready())
    marked, skipped, sent = [], [], 0
    for pid in ids:
        p = one(conn.execute(
            "SELECT id, name, login_id, phone, invited_at, COALESCE(sms_opt_out,0) so "
            "  FROM partners WHERE id=?", (pid,)))
        if not p:
            skipped.append({"id": pid, "name": f"#{pid}", "why": "업체를 찾을 수 없습니다"})
            continue
        if not (p["login_id"] or ""):
            skipped.append({"id": pid, "name": p["name"], "why": "계정이 아직 없습니다"})
            continue
        if p["invited_at"]:
            skipped.append({"id": pid, "name": p["name"], "why": "이미 안내함"})
            continue
        if live and (p["phone"] or "").strip() and not p["so"]:
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
            sent += 1
        conn.execute("UPDATE partners SET invited_at=? WHERE id=?", (DB.now(), pid))
        marked.append({"id": pid, "name": p["name"], "login_id": p["login_id"]})
    DB.log(conn, actor(), "협력사 안내 표시",
           f"{len(marked)}곳 표시 · 실발송 {sent}건 · 건너뜀 {len(skipped)}곳")
    conn.commit(); conn.close()
    return jsonify({"ok": True, "marked": marked, "skipped": skipped,
                    "sent": sent, "notify_live": live})
'''
    chk("BEGIN IMMEDIATE" not in _PRE566_SRC, "STEP 재구성한 옛 원문에는 BEGIN IMMEDIATE가 없다(대조군)")
    _ns = dict(vars(A))          # app 모듈 네임스페이스 복사(진짜 모듈은 안 건드림)
    exec(compile(_PRE566_SRC, "<round566_pre_reconstructed>", "exec"), _ns)
    old_fn = _ns["_api_partner_invite_pre566"]

    p_old = mkpartner("r566race_old", "R566구코드동시요청업체")
    _Probe2, hit_old = make_delay_probe(_MATCH)
    try:
        DB.get_db = lambda: _Probe2(_real_get_db())
        res_old = _race(old_fn, p_old, 2)
    finally:
        DB.get_db = _real_get_db

    chk(hit_old["n"] == 2,
        "STEP 옛 코드: 두 요청 모두 문제의 SELECT 지점까지 동시 도달했다", hit_old)
    chk(all(isinstance(r, tuple) and r[0] != "EXC" for r in res_old),
        "STEP 옛 코드: 두 요청 모두 예외 없이 응답했다(둘 다 '성공'처럼 보인다는 것 자체가 결함이다)",
        res_old)

    n_marked_old = sum(len((r[1].get("marked") or [])) for r in res_old)
    n_notif_old = _real_get_db().execute(
        "SELECT COUNT(*) c FROM notifications WHERE partner_id=? AND ntype='계정안내'",
        (p_old,)).fetchone()["c"]
    chk(n_marked_old == 2,
        "★★★★★ 옛 코드(재구성): 동시에 부딪힌 두 요청이 **둘 다** marked(표시)됐다고 "
        "응답한다(지금 코드는 위 [3]에서 정확히 1이었다)", res_old)
    chk(n_notif_old == 2,
        "★★★★★ 옛 코드(재구성): 동시요청 뒤 '계정안내' 알림톡이 실제로 2건 생긴다"
        "(지금 코드는 위 [3]에서 1건이었다) — 결함이 실재했음을 실측으로 증명"
        "(이 차이가 이 회귀테스트가 결함을 잡아낼 능력이 있다는 인과관계 증명이다)", n_notif_old)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드566 [3]+[4] 동시요청 실행/원인재현", f"{type(e).__name__}: {e}")
finally:
    DB.get_db = _real_get_db
    if A:
        A.NOTIFY_ENABLED = _orig_notify_enabled
        A.POPBILL.ready = _orig_popbill_ready
    chk(DB.get_db is _real_get_db, "STEP DB.get_db 원상복구 완료(다른 테스트 오염 방지)")


# ==================================================================
# 정리
# ------------------------------------------------------------------
os.environ.pop("BOKGUON_DB_PATH", None)
os.environ.pop("BOKGUON_UPLOAD_DIR", None)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
