# -*- coding: utf-8 -*-
"""스캔 504라운드 회귀 — 입점신청 처리(온보딩) 화면의 두 관련 결함.

(A, 서버) api_application_update()의 반려/서류검토 분기(app.py)가 승인
분기(바로 위, WHERE status<>'승인')와 달리 현재 상태를 전혀 안 보고
무조건 덮어썼다 — 이미 승인되어 협력업체가 생성되고 알림톡까지 나간
신청서를, 동시에 열려 있던 다른 관리자의 구형 모달이 반려로 되돌리면
partner_applications.status만 조용히(200 OK) 뒤집혀 이미 만들어진
활성 업체·이미 발송된 승인 알림과 모순되는 상태가 됐다.

(B, 화면) appAct()(admin.js)의 catch 분기가 형제(leadAct 등, 라운드481·
486·500·501·503이 세운 "catch도 성공 분기와 같이 정리한다" 원칙)를 못
물려받았다 — 그것도 이 함수 자신이 그 형제들의 원조다(라운드89가 여기
먼저 try/catch를 붙였고, 라운드205가 leadAct·defectAct·dispatchSweep에
"형제(appAct)처럼"이라며 옮겨 붙였는데, 정작 원조 자신은 나중에 이
정리 원칙을 못 물려받았다). 여섯 번째 클러스터.
"""
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(c, n, d=""):
    (PASS if c else FAIL).append((n, d))
    print(("  [OK]   " if c else "  [FAIL] ") + n + ("" if c else f"   {d}"))


print("=" * 72)
print("  스캔 504라운드 회귀 — 입점신청 승인후 상태역전 + appAct catch 방치")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
JS_PATH = os.path.join(HERE, "static", "admin.js")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()
JS_SRC = io.open(JS_PATH, encoding="utf-8").read()


def fn_body(src, start_marker):
    i = src.index(start_marker)
    depth = 0
    started = False
    j = i
    while j < len(src):
        ch = src[j]
        if ch == "{":
            depth += 1
            started = True
        elif ch == "}":
            depth -= 1
            if started and depth == 0:
                return src[i:j + 1]
        j += 1
    raise ValueError("no matching close brace")


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 두 지점을 각각 독립적으로 추출(서로 안 겹침)")
# ──────────────────────────────────────────────────────────────
CUR_A = ('''    elif new_status:
        #  ⚠⚠ [라운드504] 형제(바로 위 승인 분기, WHERE status<>'승인')와 달리
        #    이 분기는 현재 상태를 전혀 안 보고 무조건 덮어썼다 — 이미 승인되어
        #    협력업체가 생성되고 알림톡까지 나간 신청서를, 동시에 열려 있던
        #    다른 관리자의 구형 모달이 반려/서류검토로 되돌리면
        #    partner_applications.status만 조용히(200 OK) 뒤집혀 이미 만들어진
        #    활성 업체·이미 발송된 승인 알림과 모순되는 상태가 된다. 승인은
        #    되돌릴 수 있는 동작이 아니므로(업체 생성·알림 발송을 취소하지
        #    않음) 같은 원칙(승인 이후엔 이 화면으로 상태를 못 바꿈)을 적용한다.
        cur = conn.execute(
            "UPDATE partner_applications SET status=? WHERE id=? AND status<>'승인'",
            (new_status, aid))
        if not cur.rowcount:
            conn.rollback(); conn.close()
            return jsonify({"ok": False, "error": "이미 승인된 신청입니다."}), 409
        DB.log(conn, actor(), "입점신청 상태변경", f"#{aid} → {new_status}")
''')
ORIG_A = ('''    elif new_status:
        conn.execute("UPDATE partner_applications SET status=? WHERE id=?", (new_status, aid))
        DB.log(conn, actor(), "입점신청 상태변경", f"#{aid} → {new_status}")
''')
chk(APP_SRC.count(CUR_A) == 1, "블록A(서버 반려/서류검토 가드)가 app.py에 유일하다", APP_SRC.count(CUR_A))
chk("status<>'승인'" not in ORIG_A, "원본 대조 문자열에는 가드가 없다(대조군)")

appact_body = fn_body(JS_SRC, "async function appAct(id, status){")
chk(JS_SRC.count(appact_body) == 1, "appAct() 함수 본문이 소스에 유일하게 추출된다")
NEW_APPACT_CATCH = ("toast(e.message || '처리하지 못했습니다.'); "
                     "closeModal(); refreshBadges(); VIEWS.apps(); return;")
chk(NEW_APPACT_CATCH in appact_body,
    "appAct() catch가 성공 분기와 같은 정리(closeModal·refreshBadges·VIEWS.apps)를 한다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 준비 — 스크래치 DB (이 프로세스 안에서 재사용, 서브프로세스 없음)")
# ──────────────────────────────────────────────────────────────
#  ⚠⚠ [라운드625] 이전 버전은 별도 워커 스크립트(test_scan_round504_worker.py)를
#    서브프로세스로 띄우고, [3]의 되돌림-증명은 실제 app.py 파일에
#    io.open(...,"w").write(reverted_app) 로 디스크에 썼다가 finally 에서
#    복원하는 방식이었다 — api_application_update()는 평범한 Flask 라우트라
#    기법1(view_functions 딕셔너리 스왑)로 옮긴다. 워커 스크립트가 하던 일
#    (관리자+신청서 준비 → 승인 PATCH → 반려 PATCH → DB 확인)을 이 프로세스
#    안에서 A.app.test_client() 로 그대로 반복해, 서브프로세스·디스크 쓰기
#    없이 끝낸다.
_tmpdir = tempfile.mkdtemp(prefix="round504_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
import db as DB
DB.init_db()
import app as A

_ac = DB.get_db()
_ac.execute("INSERT OR IGNORE INTO admins(username,password_hash,name,role) "
            "VALUES('r504admin','x','n1','최고관리자')")
_ac.commit(); _ac.close()


def _run_scenario(tag):
    """관리자+신청서 준비 → 승인 PATCH → 반려 PATCH(경합 재현) → DB 확인.
    매번 새 신청서 행을 만들어(회사명에 tag를 넣어) 재사용 스크래치DB 안에서도
    이전 호출과 절대 안 섞인다 — 활성 업체 수는 실행마다 누적되므로, 이번
    실행이 만든 '그 업체' 하나의 status만 짚어서 본다(전역 카운트 대신)."""
    c = DB.get_db()
    aid = c.execute(
        "INSERT INTO partner_applications(company,phone,status) VALUES(?,?,'서류검토')",
        (f"R504상사{tag}", "010-1234-5678")).lastrowid
    c.commit(); c.close()

    cl = A.app.test_client()
    with cl.session_transaction() as s:
        s["admin"] = "r504admin"; s["admin_role"] = "최고관리자"; s["_csrf"] = "c1"
    r1 = cl.patch(f"/api/applications/{aid}", json={"status": "승인"},
                  headers={"X-CSRF-Token": "c1"})
    # 다른(구형) 관리자 세션이 이미 승인된 신청서를 반려로 되돌리려 시도.
    r2 = cl.patch(f"/api/applications/{aid}", json={"status": "반려"},
                  headers={"X-CSRF-Token": "c1"})
    resp2 = r2.get_json() or {}

    conn = DB.get_db()
    row = dict(conn.execute(
        "SELECT status, partner_id FROM partner_applications WHERE id=?", (aid,)).fetchone())
    pid = row["partner_id"]
    partner_status = None
    if pid:
        prow = conn.execute("SELECT status FROM partners WHERE id=?", (pid,)).fetchone()
        partner_status = prow["status"] if prow else None
    conn.close()
    return {"approve_status": r1.status_code, "reject_status": r2.status_code,
            "reject_error": resp2.get("error"), "final_app_status": row["status"],
            "partner_created": pid is not None, "partner_status": partner_status}


def _py_fn_body(src, fn_name):
    """함수 본문 텍스트 — 다음 def뿐 아니라 다음 라우트의 @app. 데코레이터가
    먼저 나오면 거기서 자른다(round610/624 정착 기법)."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


try:
    out = _run_scenario("A")
    chk(out["approve_status"] == 200 and out["partner_created"],
        "STEP 첫 승인은 정상 성공해 협력업체가 생성된다", out)
    chk(out["reject_status"] == 409 and out["reject_error"] == "이미 승인된 신청입니다.",
        "★★★★★ 새 코드: 이미 승인된 신청서를 반려로 되돌리려 하면 409로 막힌다", out)
    chk(out["final_app_status"] == "승인",
        "★★★★★ 새 코드: 신청서 상태가 승인 그대로 유지된다(반려로 안 뒤집힘)", out)
    chk(out["partner_status"] == "활성",
        "★★★★ 새 코드: 이번에 생성된 업체는 여전히 활성(방치되지 않음)", out)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 되돌림-증명 — view_functions 스왑(기법1)으로 서버 가드를 무력화하면 재현되는가")
    # ──────────────────────────────────────────────────────────
    admu_body = _py_fn_body(APP_SRC, "api_application_update")
    chk(admu_body.count(CUR_A) == 1,
        "  (준비) 되돌림 대상 블록이 api_application_update() 안에 유일하게 있다")
    broken_body = admu_body.replace(CUR_A, ORIG_A)
    assert broken_body != admu_body, "되돌림 치환이 실제로 안 먹었다"

    _ns = dict(vars(A))
    exec(compile(broken_body, "<round504_broken_api_application_update>", "exec"), _ns)  # noqa: S102 -- 실소스 그대로 추출, 디스크 미기록
    broken_view = A.require_role("중간관리자")(_ns["api_application_update"])

    _orig_view = A.app.view_functions["api_application_update"]
    A.app.view_functions["api_application_update"] = broken_view
    try:
        out2 = _run_scenario("B")
        chk(out2["reject_status"] == 200,
            "옛 코드(되돌림): 이미 승인된 신청서에 대한 반려 요청이 그냥 200으로 통과된다", out2)
        chk(out2["final_app_status"] == "반려",
            "★★★★★ 옛 코드(되돌림): 신청서 상태가 실제로 반려로 뒤집힌다 — 이미 만들어진 "
            "활성 업체·발송된 승인 알림과 모순되는 상태가 실측으로 재현됨(이 테스트가 진짜 "
            "결함을 잡아낼 능력이 있음을 증명)", out2)
        chk(out2["partner_status"] == "활성",
            "대조군: 그런데도 이미 만들어진 업체는 그대로 활성 상태로 남아 방치된다"
            "(신청서만 반려·업체는 활성인 모순 상태)", out2)
    finally:
        A.app.view_functions["api_application_update"] = _orig_view
    chk(A.app.view_functions["api_application_update"] is _orig_view,
        "  (복원) api_application_update 라우트가 원래 함수객체로 복원됐다")

    out3 = _run_scenario("C")
    chk(out3["reject_status"] == 409 and out3["final_app_status"] == "승인",
        "  복원 후 재확인 — 다시 409로 막히고 상태도 승인 그대로 유지된다(바꿔치기가 안 샘)", out3)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] 실행/되돌림-증명", f"{type(e).__name__}: {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py는 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일)")

# ══════════════════════════════════════════════════════════════
print("\n[4] 실제 Node 실행 — appAct() catch가 진짜 화면을 정리하는지")
# ──────────────────────────────────────────────────────────────
HARNESS_HEAD = r"""
const calls = [];
global.toast = (m) => calls.push('toast:' + String(m).slice(0,20));
global.closeModal = () => calls.push('closeModal');
global.refreshBadges = () => calls.push('refreshBadges');
global.VIEWS = { apps: () => calls.push('VIEWS.apps') };
global.document = { getElementById: () => null };
global.$ = (s) => null;
let SHOULD_FAIL = process.env.R504_FAIL === '1';
global.api = async () => {
  if (SHOULD_FAIL) { throw new Error('이미 승인된 신청입니다.'); }
  return {};
};
"""
TAIL = "(async()=>{ await appAct(1, '반려'); console.log(JSON.stringify(calls)); })();"


def run_node(body, fail):
    src = HARNESS_HEAD + "\n" + body + "\n" + TAIL
    path = os.path.join(HERE, "_r504_node_tmp.js")
    io.open(path, "w", encoding="utf-8").write(src)
    env = dict(os.environ)
    env["R504_FAIL"] = "1" if fail else "0"
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True,
                            encoding="utf-8", timeout=20, env=env)
        if r.returncode != 0:
            raise RuntimeError(f"node 실행 실패: {r.stdout}\n{r.stderr}")
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


try:
    js_ok = run_node(appact_body, fail=False)
    chk("closeModal" in js_ok and "VIEWS.apps" in js_ok,
        "appAct() 정상 처리 시 모달을 닫고 목록을 새로고침한다(대조군)", js_ok)
    js_fail = run_node(appact_body, fail=True)
    chk("closeModal" in js_fail and "refreshBadges" in js_fail and "VIEWS.apps" in js_fail,
        "★★★★★ 새 코드: appAct() 서버 오류(409 등)에도 모달을 닫고 목록을 새로고침한다",
        js_fail)

    OLD_APPACT_CATCH = "catch(e){ toast(e.message || '처리하지 못했습니다.'); return; }"
    reverted_js = appact_body.replace(
        "catch(e){\n    //  ⚠⚠ [라운드504] 형제(leadAct 등, 라운드481·486·500·501·503) 참조 —\n"
        "    //    catch도 성공 분기(바로 아래)와 같이 정리한다. 이 함수(appAct)는\n"
        "    //    실은 그 형제들의 원조다(라운드89가 여기 먼저 try/catch를 붙였고,\n"
        "    //    라운드205가 leadAct·defectAct·dispatchSweep에 \"형제(appAct)처럼\"\n"
        "    //    옮겼다) — 정작 원조 자신은 나중에 이 정리 원칙을 못 물려받았다.\n"
        "    //    다른 관리자가 먼저 승인해 이미 협력업체가 생성된 신청서를 이\n"
        "    //    모달이 계속 낡은 상태로 보여주면 반려를 눌러 상태를 뒤집으려 들 수\n"
        "    //    있다(서버는 이제 이걸 409로 막지만, 화면은 그래도 새로고침해야 한다).\n"
        f"    {NEW_APPACT_CATCH}\n  }}",
        OLD_APPACT_CATCH)
    assert reverted_js != appact_body, "appAct 되돌림 치환이 실제로 안 먹었다"
    js_old_fail = run_node(reverted_js, fail=True)
    chk("closeModal" not in js_old_fail and "VIEWS.apps" not in js_old_fail,
        "★★★★★ 옛 코드(되돌림): appAct() 서버 오류 시 toast만 뜨고 모달·목록은 방치된다 — "
        "이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", js_old_fail)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[4] Node 실행/되돌림-증명", f"{type(e).__name__}: {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
