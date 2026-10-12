# -*- coding: utf-8 -*-
"""스캔 528라운드 회귀 — 웹훅 "테스트" 버튼이 데모 발주처의 실제 주소로도
   그대로 나갈 수 있던 결함(deliver_webhook 의 데모 판정이 사건에만 걸려 있었다).

   조사 배경 — deliver_webhook()은 round97 이 이미 "데모는 절대 실제 서버로
   안 나간다"를 지킨 유일한 공유 관문이다. 그런데 그 판정은
   `SELECT is_demo FROM cases WHERE case_no=?` 하나뿐이라 **사건이 실제로
   존재해야만** 걸린다. api_insurer_webhook_test("웹훅 테스트" 버튼, app.py
   9175행)는 사건과 무관하게 발주처 자신의 연동만 확인하는 진단 기능이라
   deliver_webhook 을 case_no="TEST-0000"(실제 cases 행이 아닌 고정 문자열)
   으로 부른다 — 그 결과 위 조회는 항상 빈 값이 되어 사건 쪽 데모 검사가
   구조적으로 절대 못 걸리고, 발주처 자신이 데모(insurers.is_demo=1)여도
   webhook_url·api_enabled 만 채워져 있으면 실제 HTTP POST 가 그대로 나간다.
   운영DB 를 직접 조회해 확인(읽기전용) — 지금 데모 발주처 6곳(id 1~6)은
   전부 webhook_url 이 비어 있어 오늘 당장 새고 있진 않지만, 막는 코드가
   없으니 다음에 누군가 그 칸을 채우는 순간부터 조용히 샌다.

   고침 — deliver_webhook()의 insurers 조회에 is_demo 를 추가해 발주처
   자신이 데모면 사건 유무와 무관하게 enabled 를 끈다(round97 과 같은 함수,
   같은 상태값 '미설정' 재사용 — 새 상태값 없음). api_insurer_webhook_test
   에도 같은 이유(이 함수 자신의 기존 원칙 "안 보내 놓고 보냈다고 하지
   않는다")로 사전 차단(INSURER_IS_DEMO, 409)을 추가해 화면이 조용히
   ok:True 를 받는 대신 명확한 사유를 본다.

      python test_scan_round528_fixes.py
"""
import io
import json as _json
import os
import shutil
import sys
import tempfile

#  ⚠ 윈도 기본 콘솔은 cp949 라 em dash(—) 같은 문자를 print 하면
#    UnicodeEncodeError 로 죽는다(round518·519가 이 저장소 전체에서 이미
#    잡아낸 결함군과 같은 원인) — 형제 테스트(예: test_scan_round527_fixes.py)
#    가 이미 쓰는 방어를 그대로 옮긴다.
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


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 528라운드 회귀 — 웹훅 테스트 버튼의 데모발주처 실전송 차단")
print("=" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ==================================================================
print("\n[1] 소스: deliver_webhook·api_insurer_webhook_test 둘 다 "
      "insurers.is_demo 를 직접 본다")
# ------------------------------------------------------------------
dw_body = _py_fn_body(APP_SRC, "deliver_webhook")
chk("api_enabled, status, is_demo " in dw_body,
    "★★★ deliver_webhook 의 insurers 조회가 is_demo 컬럼도 함께 읽는다")
chk('(ins or {}).get("is_demo")' in dw_body,
    "★★★ 조회한 발주처 자신의 is_demo 를 직접 확인한다(사건 조회와 별개)")
# 두 개의 "enabled = False" 가 있어야 한다 — round97(사건 기준) + round528(발주처 기준)
chk(dw_body.count("enabled = False") >= 2,
    "★★ 사건 기준 차단(round97)과 발주처 기준 차단(round528)이 둘 다 남아 있다"
    "(하나가 다른 하나를 지운 게 아님)", dw_body.count("enabled = False"))

wt_body = _py_fn_body(APP_SRC, "api_insurer_webhook_test")
chk("status, is_demo FROM insurers" in wt_body,
    "★★ api_insurer_webhook_test 도 조회에 is_demo 를 포함한다")
chk('"code": "INSURER_IS_DEMO"' in wt_body,
    "★★★ 데모 발주처면 명확한 코드로 사전 차단한다(조용한 ok:True 아님)")
# 순서: is_demo 검사가 실제 deliver_webhook 호출보다 앞에 있어야 한다
chk(wt_body.index("INSURER_IS_DEMO") < wt_body.index("deliver_webhook(conn, iid"),
    "STEP is_demo 차단이 실제 발송 호출보다 먼저 온다(늦게 걸리면 이미 늦음)")

# ==================================================================
# 실행 준비 — 이 프로세스 안에서 계속 쓸 공유 상태
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round528_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r528-csrf"
A = None
DB = None
_real_webhook_send = None
_sent = []          # _webhook_send 가 실제로 불렸는지 기록(실네트워크 없이 확인)
demo_iid = real_iid = None
admin_c = None


def _admin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "admin"
        sess["admin_name"] = "검증"
        sess["admin_role"] = "최고관리자"
        sess["_csrf"] = CSRF
    return c


# ==================================================================
print("\n[2] 실행: deliver_webhook() 자체 — 발주처가 데모면 사건이 "
      "없어도(case_no 가 가짜여도) '미설정'으로 막힌다")
# ------------------------------------------------------------------
try:
    import db as DB
    DB.init_db()
    import app as A

    #  실네트워크를 안 태운다 — 이 회귀가 보려는 건 "큐에 올렸는가"(status 컬럼)
    #  뿐이고, 실제 HTTP 왕복 자체는 형제 테스트(round84·157)가 이미 검증한다.
    _real_webhook_send = A._webhook_send
    A._webhook_send = lambda *a, **k: _sent.append(a)

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('admin','x','검증','최고관리자')")
    demo_iid = conn0.execute(
        "INSERT INTO insurers(name,status,webhook_url,webhook_secret,api_enabled,is_demo) "
        "VALUES('R528데모보험','활성','https://demo-insurer.example.com/hook','sec',1,1)"
    ).lastrowid
    real_iid = conn0.execute(
        "INSERT INTO insurers(name,status,webhook_url,webhook_secret,api_enabled,is_demo) "
        "VALUES('R528실보험','활성','https://real-insurer.example.com/hook','sec',1,0)"
    ).lastrowid
    conn0.commit()
    conn0.close()

    conn = DB.get_db()
    with A.app.test_request_context():
        # case_no 는 둘 다 실제 cases 행이 없는 값이다 — api_insurer_webhook_test
        # 가 쓰는 "TEST-0000" 과 같은 조건(사건 쪽 검사는 절대 못 걸림)을 그대로 재현.
        did_demo = A.deliver_webhook(conn, demo_iid, "ping", "R528-NOCASE-DEMO",
                                     {"message": "test"})
        conn.commit()
        did_real = A.deliver_webhook(conn, real_iid, "ping", "R528-NOCASE-REAL",
                                     {"message": "test"})
        conn.commit()

    row_demo = conn.execute(
        "SELECT status, target_url FROM webhook_deliveries WHERE id=?", (did_demo,)).fetchone()
    row_real = conn.execute(
        "SELECT status, target_url FROM webhook_deliveries WHERE id=?", (did_real,)).fetchone()
    conn.close()

    chk(row_demo["status"] == "미설정",
        "★★★★★ 데모 발주처는 사건이 없어도(case_no 가 가짜라도) '미설정'으로 "
        "막힌다(발주처 자신의 is_demo 가 관문 역할)", dict(row_demo))
    chk(row_real["status"] == "대기",
        "★★ 실제(비데모) 발주처는 그대로 '대기'로 정상 큐잉된다(과잉차단 아님)",
        dict(row_real))
    chk(row_demo["target_url"] == "https://demo-insurer.example.com/hook",
        "STEP 배송 이력 행 자체는 남는다(감사 목적 — 실제 발송만 막힘)",
        row_demo["target_url"])

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드528 [2] 서버측 준비/실행", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[3] 실행: 실제 라우트(api_insurer_webhook_test) — 데모 발주처는 "
      "409/INSURER_IS_DEMO 로 막히고 배송 이력조차 새로 안 생긴다")
# ------------------------------------------------------------------
try:
    conn = DB.get_db()
    before_demo = conn.execute(
        "SELECT COUNT(*) n FROM webhook_deliveries WHERE insurer_id=?", (demo_iid,)
    ).fetchone()["n"]
    before_real = conn.execute(
        "SELECT COUNT(*) n FROM webhook_deliveries WHERE insurer_id=?", (real_iid,)
    ).fetchone()["n"]
    conn.close()

    admin_c = _admin_client()
    r_demo = admin_c.post(f"/api/insurers/{demo_iid}/webhook-test",
                          headers={"X-CSRF-Token": CSRF})
    r_real = admin_c.post(f"/api/insurers/{real_iid}/webhook-test",
                          headers={"X-CSRF-Token": CSRF})

    j_demo = r_demo.get_json()
    j_real = r_real.get_json()
    chk(r_demo.status_code == 409 and j_demo.get("ok") is False
        and j_demo.get("code") == "INSURER_IS_DEMO",
        "★★★★★ 데모 발주처 테스트 버튼은 409/INSURER_IS_DEMO 로 명확히 막힌다"
        "(고치기 전엔 200/ok:True 였다 — 실제로 나간 줄 알고 넘어갔다)",
        (r_demo.status_code, j_demo))
    chk(r_real.status_code == 200 and j_real.get("ok") is True,
        "★★ 실제 발주처 테스트 버튼은 그대로 정상 동작한다(과잉차단 아님)",
        (r_real.status_code, j_real))

    conn = DB.get_db()
    after_demo = conn.execute(
        "SELECT COUNT(*) n FROM webhook_deliveries WHERE insurer_id=?", (demo_iid,)
    ).fetchone()["n"]
    after_real = conn.execute(
        "SELECT COUNT(*) n FROM webhook_deliveries WHERE insurer_id=?", (real_iid,)
    ).fetchone()["n"]
    conn.close()

    chk(after_demo == before_demo,
        "★★★ 데모 발주처는 사전 차단돼 deliver_webhook 자체가 안 불려 배송 "
        "이력이 새로 안 생긴다(라우트가 아예 진입을 막음)",
        (before_demo, after_demo))
    chk(after_real == before_real + 1,
        "STEP 실제 발주처는 배송 이력이 1건 새로 생긴다(정상 흐름 그대로)",
        (before_real, after_real))
    # _sent 는 [2]부터 누적된다 — 실제(비데모) 발주처 몫(정상)이 섞여 있는 게
    # 맞다. 확인할 것은 "데모 발주처의 webhook_url 로는 단 한 번도 안 불렸다"이다.
    demo_url = "https://demo-insurer.example.com/hook"
    sent_to_demo = [s for s in _sent if len(s) > 1 and s[1] == demo_url]
    chk(sent_to_demo == [],
        "★★★★★ _webhook_send()(실제 네트워크 전송 함수)가 데모 발주처의 "
        "webhook_url 로는 단 한 번도 안 불렸다 — teardown 큐잉조차 데모 "
        "발주처에겐 아예 발생하지 않음(실제 발주처 몫은 정상적으로 남아 있음)",
        (sent_to_demo, _sent))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드528 [3] 라우트 실행", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[4] 되돌리기 — 발주처 기준 검사를 빼면(수정 전 코드 재구성) "
      "실제로 새는가(인과관계 직접증명)")
# ------------------------------------------------------------------
#  ⚠ app.py 자체는 건드리지 않는다 — 동시에 다른 세션이 같은 파일을 고칠 수
#    있는 환경(round520 이후 이 저장소의 표준 관례)이라, 되돌림-증명은 옛
#    코드를 이 테스트 **안에서만** 문자열로 재구성해 같은 시나리오에 직접
#    실행한다. 아래는 이 라운드가 고치기 **직전**의 실제 deliver_webhook
#    본문(수정 직전 이 세션이 Read 로 확인한 원문)에서 insurers.is_demo
#    관련 두 줄(SELECT 의 is_demo 컬럼·그 값을 보는 if)만 뺀 것이다 —
#    round97 이 지킨 사건 기준 차단은 그대로 남겨, "이번 라운드가 새로
#    추가한 조건 하나"만 없앤 상태를 정확히 재현한다.
try:
    def _deliver_webhook_pre528(conn, insurer_id, event, case_no, payload):
        """round528 이전 deliver_webhook() 재구성(발주처 자신의 is_demo 미검사)."""
        ins = A.one(conn.execute(
            "SELECT webhook_url, webhook_secret, api_enabled, status "
            "  FROM insurers WHERE id=?", (insurer_id,)))
        url = (ins or {}).get("webhook_url") or ""
        enabled = (bool((ins or {}).get("api_enabled"))
                   and (ins or {}).get("status") == "활성")
        # round97 방어(사건 기준)는 그대로 유지 — 이번 라운드가 지운 게 아니므로.
        if (A.one(conn.execute(
                "SELECT is_demo FROM cases WHERE case_no=?", (case_no,))) or {}).get("is_demo"):
            enabled = False
        body_obj = {"event": event, "case_no": case_no, "occurred_at": DB.now(), "data": payload}
        payload_str = _json.dumps(body_obj, ensure_ascii=False)
        status = "대기" if (url and enabled) else "미설정"
        cur = conn.execute(
            """INSERT INTO webhook_deliveries(insurer_id,event,case_no,payload,target_url,status,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (insurer_id, event, case_no, payload_str, url, status, DB.now()))
        return cur.lastrowid, url, enabled

    conn = DB.get_db()
    # 사건도 실제 존재하지 않는 case_no 로 부른다 — 웹훅 테스트 버튼과 정확히
    # 같은 조건("TEST-0000" 류)에서 옛 코드가 실제로 무엇을 했는지 재현한다.
    did_old, url_old, enabled_old = _deliver_webhook_pre528(
        conn, demo_iid, "ping", "R528-NOCASE-OLD", {"message": "test"})
    conn.commit()
    row_old = conn.execute(
        "SELECT status FROM webhook_deliveries WHERE id=?", (did_old,)).fetchone()
    conn.close()

    chk(enabled_old is True,
        "★★★★★ 옛 코드(발주처 is_demo 미검사)라면 이 데모 발주처를 그대로 "
        "'발송 가능'으로 판정한다(고치기 전엔 이랬다 — 인과관계 확인)",
        enabled_old)
    chk(row_old["status"] == "대기",
        "★★★★★ 옛 코드라면 사건이 없는데도(case_no 가 가짜인데도) 데모 "
        "발주처의 실제 webhook_url 이 그대로 '대기'(발송 큐)로 잡힌다 — "
        "지금 코드(위 [2])는 같은 입력에서 '미설정'이었다", dict(row_old))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드528 [4] 되돌림-증명", f"{type(e).__name__} {e}")

# ==================================================================
# 정리 — 어디서 실패했든 반드시 실행한다
# ------------------------------------------------------------------
try:
    if A is not None and _real_webhook_send is not None:
        A._webhook_send = _real_webhook_send
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
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
