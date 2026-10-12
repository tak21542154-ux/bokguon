# -*- coding: utf-8 -*-
"""스캔 506라운드 회귀 — api_insurer_update()(보험사 정보·상태 변경,
PATCH /api/insurers/<id>)가 형제 api_partner_update()(같은 클래스의
상태확인-수정 패턴, 라운드493이 BEGIN IMMEDIATE 이식)와 달리 트랜잭션
잠금이 **전혀** 없던 결함.

관리자 두 명(또는 재시도)이 같은 보험사를 거의 동시에 '중지'로 바꾸면
둘 다 200을 받아 보험사에게 "보험사상태변경" 알림(웹)이 두 번 나가고
감사로그도 상태변경 문구가 두 번 남았다(최종 status 자체는 '중지'
하나뿐이라 데이터 훼손은 아니지만 알림·감사로그가 중복된다).

round505는 "잠금만으로는 부족하다 — 이미 그 상태인지 재확인도 필요"
라고 했는데, 이 함수는 round505의 DELETE(조건 없이 무조건 UPDATE)와
달리 애초에 매 요청마다 현재값과 대조해 changed 를 계산하는 구조라서,
읽기(SELECT)를 잠금 뒤로 옮기기만 해도 두 번째 요청은 잠금 안에서 이미
바뀐 status 를 보고 changed=False 로 자연히 멈춘다 — 별도 "이미 그
상태입니다" 조건부 UPDATE 를 새로 얹을 필요가 없다.

⚠ 완전한 결백 증명은 아니다 — 필드 루프(org_type/manager/dept/phone/
email/contract_status/status)가 "값이 실제로 바뀌었는지"와 무관하게
요청에 그 키가 있으면 무조건 sets 에 넣는 것은 이 함수와 형제
api_partner_update 양쪽에 공통인, 이번 라운드 범위 밖의 별개 동작이다
(그래서 두 번째 요청도 UPDATE 자체는 한 번 더 실행되고 "정보 수정"
이라는 범용 감사로그 한 줄은 남는다). 이번 수정이 없애는 것은 정확히
round505 와 같은 급의 결함 — **알림 중복**과 **상태변경 감사로그
중복** — 이고, 이는 실측으로 확인된다.

⚠⚠ [라운드621] 되돌림-증명 기법을 옛 세대(app.py를 실제로 디스크에 써넣고
별도 워커 서브프로세스를 두 번 돌린 뒤 복원)에서 round488/507이 확립한
안전패턴으로 이관한다. CUR_FUNC/ORIGINAL_FUNC 는 함수 본문의 일부(차이가
나는 구간)만 캡처한 것이라 — 그대로 exec하면 함수가 return 없이 중간에
끊겨 구문은 통과해도 실제 호출 시 무의미하다 — round499가 정착시킨
ast 기반 전체 함수 추출로 CURRENT_FULL_FUNC 를 뽑고, 그 안에서
CUR_FUNC→ORIGINAL_FUNC 부분 치환만 적용해 완전한 REVERTED_FULL_FUNC 를
만든다. api_insurer_update()는 단일 라우트 핸들러라 이걸 exec로 독립
사본 네임스페이스에 재구성해 A.app.view_functions 딕셔너리 항목만 잠깐
치환한다 — 진짜 app.py 파일은 전혀 안 쓴다. 동시성 재현(threading.Barrier
+ _Probe로 DB.get_db()를 감싸 SELECT 문 도달을 강제)은 옛 워커
(test_scan_round506_worker.py, 삭제됨)의 로직을 그대로 옮긴다.
"""
import ast
import io
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(c, n, d=""):
    (PASS if c else FAIL).append((n, d))
    print(("  [OK]   " if c else "  [FAIL] ") + n + ("" if c else f"   {d}"))


print("=" * 72)
print("  스캔 506라운드 회귀 — 보험사 정보수정(PATCH) 동시성 경합")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — api_insurer_update() 함수 전체를 통째로 캡처")
# ──────────────────────────────────────────────────────────────
CUR_FUNC = ('''def api_insurer_update(iid):
    """보험사 정보·계약 요율 변경. 요율 변경은 감사로그에 전/후를 남긴다."""
    d = body()
    conn = DB.get_db()
    #  ⚠⚠ [라운드506] 형제(api_partner_update, 라운드493 — 같은 클래스의 상태확인
    #    -수정 사이)는 이미 BEGIN IMMEDIATE로 잠그는데 이 보험사 정보수정 경로만
    #    잠금이 전혀 없었다 — 관리자 둘(또는 재시도)이 같은 보험사를 거의 동시에
    #    '중지'로 바꾸면 둘 다 200을 받아 "보험사상태변경" 알림·감사로그가
    #    중복됨을 threading.Barrier로 실측 확인. 읽기를 잠금 **뒤**로 옮기면
    #    충분하다 — round505의 DELETE(무조건 UPDATE)와 달리 이 함수는 매번
    #    현재값과 대조해 changed 를 계산하므로, 두 번째 요청은 잠금 안에서 이미
    #    바뀐 status 를 보고 changed=False 로 자연히 멈춘다(별도 "이미 그
    #    상태입니다" 재확인 불필요).
    conn.execute("BEGIN IMMEDIATE")
    r = one(conn.execute("SELECT * FROM insurers WHERE id=?", (iid,)))
    if not r:
        conn.rollback(); conn.close()
        return jsonify({"ok": False, "error": "기관을 찾을 수 없습니다."}), 404

    #  ⚠⚠ [라운드136] status 에 허용목록이 아예 없었다 — 협력사(_partner_update,
    #    라운드101)와 같은 결함: 오타 하나가 로그인 허용집합·강등 관문 어디에도
    #    안 걸리는 죽은 상태값을 만들 수 있었다.
    if "status" in d and d["status"] not in INSURER_STATUSES:
        conn.rollback(); conn.close()
        return jsonify({"ok": False, "error": f"알 수 없는 보험사 상태입니다: {d['status']}"}), 400
    changed = "status" in d and (d.get("status") or "") != (r["status"] or "")
    if changed:
        blocked = _insurer_demote_gate(conn, iid, d.get("status"), d.get("confirm_demote"))
        if blocked:
            conn.rollback(); conn.close()
            return blocked
        #  사유를 남긴다 — 협력사 강등과 같은 이유(당사자가 왜 막혔는지 알아야 한다)
        #  ⚠⚠ [331라운드] 아래 reason 은 여기 길이검사에만 쓰이고 저장·통지(8277·
        #    8288행 부근)는 이 변수를 안 쓰고 d.get("status_reason")을 매번 다시
        #    읽어 길이제한이 적용된 적이 없었다 — 이 변수를 그대로 재사용한다.
        reason = _s(d.get("status_reason"), 300)
        if len(reason) < 5:
            conn.rollback(); conn.close()
            return jsonify({"ok": False, "code": "NEED_REASON",
                            "error": "보험사 상태를 바꾸려면 사유를 5자 이상 적어 주세요."}), 400

    sets, vals, notes = [], [], []
    if "fee_rate_pct" in d:
        bp, err = _parse_fee_pct(d.get("fee_rate_pct"))
        if err:
            conn.rollback(); conn.close(); return jsonify({"ok": False, "error": err}), 400
        if bp is not None and bp != (r["fee_rate_bp"] or 0):
            # 구 REAL 컬럼은 비워 둔다 — 남겨두면 마이그레이션 백필과 값이 어긋난다
            sets += ["fee_rate_bp=?", "fee_rate=NULL"]; vals.append(bp)
            notes.append(f"수수료율 {(r['fee_rate_bp'] or 0)/100:g}% → {bp/100:g}%")
    #  ⚠⚠ [라운드169] 자기수정(api_insurer_profile_update)은 manager/dept/phone/
    #    email 을 전부 [:80] 으로 자르는데 이 관리자 경로엔 길이 제한이 없었다.
    #    contract_status/status 는 화면이 <select> 로만 주는 짧은 고정값(status
    #    는 위에서 별도 허용목록 검증까지 받는다)이라 그대로 둔다.
    _R169_LIMITS = {"org_type": FIELD_LIMITS["org_type"], "manager": 80, "dept": 80,
                    "phone": FIELD_LIMITS["phone"], "email": FIELD_LIMITS["email"]}
    for f in ("org_type", "manager", "dept", "phone", "email", "contract_status", "status"):
        if f in d:
            #  ⚠⚠ [라운드483] 형제(api_insurer_profile_update 3177행·api_partner_
            #    update 8262행 부근)는 전부 이 검사를 쓰는데 이 관리자수정
            #    경로만 없었다 — 형식이 깨진 채로 저장하면, 그 보험사가
            #    마이페이지에서 이메일과 무관한 필드만 고쳐도(화면이 4개
            #    필드를 통째로 재전송) 그 자리에서 비로소 400이 뜬다.
            #  ⚠⚠ [라운드609] round608이 발견한 새 결함군 — d[f] 가 raw라 email/phone을
            #    숫자 등으로 보내면 TypeError로 500. _s() 로 감싼다.
            if f == "email" and d[f] and not RE_EMAIL.match(_s(d[f])):
                conn.rollback(); conn.close()
                return jsonify({"ok": False,
                                "error": f"이메일 형식이 올바르지 않습니다: {_s(d[f])}"}), 400
            #  ⚠⚠ [라운드484] email과 짝인 RE_PHONE 검사가 이 자리엔 없었다.
            if f == "phone" and d[f] and not RE_PHONE.match(_s(d[f])):
                conn.rollback(); conn.close()
                return jsonify({"ok": False,
                                "error": f"연락처 형식이 올바르지 않습니다: {_s(d[f])}"}), 400
            v = _s(d[f], _R169_LIMITS[f]) if f in _R169_LIMITS else d[f]
            #  ⚠⚠ [라운드561] 이 루프는 "본문에 그 키가 있는가"만 보고 무조건
            #    sets/vals 에 넣었다 — 형제 자기수정(api_insurer_profile_update,
            #    라운드544가 이미 고침)은 prev 와 대조해 실제로 바뀔 때만 넣는데
            #    이 관리자수정 경로만 그 대조가 없었다(라운드506 자신의 주석이
            #    "이번 라운드 범위 밖"이라 미리 밝혀 둔 바로 그 결함). 화면도
            #    마이페이지와 같은 관례(칸을 안 건드려도 폼 전체를 통째로
            #    재전송)라, 관리자가 담당자 한 칸만 고쳐도 org_type~contract_status
            #    나머지 칸이 전부 "바뀐 값"인 양 매번 다시 쓰였고, 감사로그도
            #    notes 가 비어 있어 무엇이 바뀌었는지 남기지 못한 채 "정보 수정"
            #    이라는 빈 문구만 남겼다.
            if v == (r[f] or ""):
                continue
            sets.append(f"{f}=?"); vals.append(v)
            if f != "status":
                notes.append(f)
    if changed:
        sets += ["status_reason=?", "status_changed_at=datetime('now','+9 hours')",
                 "status_changed_by=?"]
        vals += [reason, actor()]
        notes.append(f"상태 {r['status']} → {d['status']}")
    if not sets:
        conn.rollback(); conn.close(); return jsonify({"ok": True, "unchanged": True})
    vals.append(iid)''')

ORIGINAL_FUNC = ('''def api_insurer_update(iid):
    """보험사 정보·계약 요율 변경. 요율 변경은 감사로그에 전/후를 남긴다."""
    d = body()
    conn = DB.get_db()
    r = one(conn.execute("SELECT * FROM insurers WHERE id=?", (iid,)))
    if not r:
        conn.close(); return jsonify({"ok": False, "error": "기관을 찾을 수 없습니다."}), 404

    #  ⚠⚠ [라운드136] status 에 허용목록이 아예 없었다 — 협력사(_partner_update,
    #    라운드101)와 같은 결함: 오타 하나가 로그인 허용집합·강등 관문 어디에도
    #    안 걸리는 죽은 상태값을 만들 수 있었다.
    if "status" in d and d["status"] not in INSURER_STATUSES:
        conn.close()
        return jsonify({"ok": False, "error": f"알 수 없는 보험사 상태입니다: {d['status']}"}), 400
    changed = "status" in d and (d.get("status") or "") != (r["status"] or "")
    if changed:
        blocked = _insurer_demote_gate(conn, iid, d.get("status"), d.get("confirm_demote"))
        if blocked:
            conn.close()
            return blocked
        #  사유를 남긴다 — 협력사 강등과 같은 이유(당사자가 왜 막혔는지 알아야 한다)
        #  ⚠⚠ [331라운드] 아래 reason 은 여기 길이검사에만 쓰이고 저장·통지(8277·
        #    8288행 부근)는 이 변수를 안 쓰고 d.get("status_reason")을 매번 다시
        #    읽어 길이제한이 적용된 적이 없었다 — 이 변수를 그대로 재사용한다.
        reason = (d.get("status_reason") or "").strip()[:300]
        if len(reason) < 5:
            conn.close()
            return jsonify({"ok": False, "code": "NEED_REASON",
                            "error": "보험사 상태를 바꾸려면 사유를 5자 이상 적어 주세요."}), 400

    sets, vals, notes = [], [], []
    if "fee_rate_pct" in d:
        bp, err = _parse_fee_pct(d.get("fee_rate_pct"))
        if err:
            conn.close(); return jsonify({"ok": False, "error": err}), 400
        if bp is not None and bp != (r["fee_rate_bp"] or 0):
            # 구 REAL 컬럼은 비워 둔다 — 남겨두면 마이그레이션 백필과 값이 어긋난다
            sets += ["fee_rate_bp=?", "fee_rate=NULL"]; vals.append(bp)
            notes.append(f"수수료율 {(r['fee_rate_bp'] or 0)/100:g}% → {bp/100:g}%")
    #  ⚠⚠ [라운드169] 자기수정(api_insurer_profile_update)은 manager/dept/phone/
    #    email 을 전부 [:80] 으로 자르는데 이 관리자 경로엔 길이 제한이 없었다.
    #    contract_status/status 는 화면이 <select> 로만 주는 짧은 고정값(status
    #    는 위에서 별도 허용목록 검증까지 받는다)이라 그대로 둔다.
    _R169_LIMITS = {"org_type": FIELD_LIMITS["org_type"], "manager": 80, "dept": 80,
                    "phone": FIELD_LIMITS["phone"], "email": FIELD_LIMITS["email"]}
    for f in ("org_type", "manager", "dept", "phone", "email", "contract_status", "status"):
        if f in d:
            #  ⚠⚠ [라운드483] 형제(api_insurer_profile_update 3177행·api_partner_
            #    update 8262행 부근)는 전부 이 검사를 쓰는데 이 관리자수정
            #    경로만 없었다 — 형식이 깨진 채로 저장하면, 그 보험사가
            #    마이페이지에서 이메일과 무관한 필드만 고쳐도(화면이 4개
            #    필드를 통째로 재전송) 그 자리에서 비로소 400이 뜬다.
            if f == "email" and d[f] and not RE_EMAIL.match(d[f]):
                conn.close()
                return jsonify({"ok": False,
                                "error": f"이메일 형식이 올바르지 않습니다: {d[f]}"}), 400
            #  ⚠⚠ [라운드484] email과 짝인 RE_PHONE 검사가 이 자리엔 없었다.
            if f == "phone" and d[f] and not RE_PHONE.match(d[f]):
                conn.close()
                return jsonify({"ok": False,
                                "error": f"연락처 형식이 올바르지 않습니다: {d[f]}"}), 400
            v = _s(d[f], _R169_LIMITS[f]) if f in _R169_LIMITS else d[f]
            sets.append(f"{f}=?"); vals.append(v)
    if changed:
        sets += ["status_reason=?", "status_changed_at=datetime('now','+9 hours')",
                 "status_changed_by=?"]
        vals += [reason, actor()]
        notes.append(f"상태 {r['status']} → {d['status']}")
    if not sets:
        conn.close(); return jsonify({"ok": True, "unchanged": True})
    vals.append(iid)''')

chk(APP_SRC.count(CUR_FUNC) == 1, "api_insurer_update() 현재 함수 본문이 소스에 유일하다", APP_SRC.count(CUR_FUNC))
chk("BEGIN IMMEDIATE" not in ORIGINAL_FUNC, "원본 대조 함수에는 잠금이 없다(대조군)")
chk(ORIGINAL_FUNC != CUR_FUNC, "대조군과 현재 코드가 실제로 다르다")


def _ast_fn_src(src, fn_name):
    """함수의 정확한 경계(decorator 제외, def~마지막 줄)를 ast로 뽑는다(round499 정착 기법).
    CUR_FUNC/ORIGINAL_FUNC 는 본문 일부(차이 구간)만 캡처한 것이라, 이걸로
    전체 함수를 뽑아야 exec 가능한 완전한 되돌림 본문을 만들 수 있다."""
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            return "".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError(f"함수 {fn_name} 을 못 찾음")


CURRENT_FULL_FUNC = _ast_fn_src(APP_SRC, "api_insurer_update")
chk(CUR_FUNC in CURRENT_FULL_FUNC, "CUR_FUNC(부분 캡처)가 전체 함수 본문 안에 있다(경계 확인)")
REVERTED_FULL_FUNC = CURRENT_FULL_FUNC.replace(CUR_FUNC, ORIGINAL_FUNC)
assert REVERTED_FULL_FUNC != CURRENT_FULL_FUNC, "되돌림 치환이 실제로 안 먹었다(전체 본문 기준)"

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 준비 — 스크래치 DB + threading.Barrier로 실제 동시 PATCH 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round506_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB                 # noqa: E402
DB.init_db()
import app as A                 # noqa: E402

_seed_n = [0]


def _seed_insurer():
    """옛 워커의 시드 로직 — 매 시나리오(현재/되돌림/원복)마다 독립된
    관리자·보험사를 새로 만들어 세 번의 호출이 서로 간섭하지 않게 한다."""
    _seed_n[0] += 1
    n = _seed_n[0]
    c = DB.get_db()
    c.execute("INSERT INTO admins(username,password_hash,name,role) "
              f"VALUES('a{n}1','x','n1','최고관리자')")
    c.execute("INSERT INTO admins(username,password_hash,name,role) "
              f"VALUES('a{n}2','x','n2','최고관리자')")
    iname = f"D보험{n}"
    iid = c.execute(f"INSERT INTO insurers(name,status) VALUES('{iname}','활성')").lastrowid
    c.commit(); c.close()
    return iid, iname, f"a{n}1", f"a{n}2"


def _run_concurrent_patch(iid, iname, u1, u2):
    """api_insurer_update()의 유일한 읽기지점(SELECT * FROM insurers WHERE id=?)에
    threading.Barrier를 걸어 두 요청이 같은 순간에 그 실행에 도달하도록
    강제한다(옛 워커 test_scan_round506_worker.py의 로직을 그대로 옮김)."""
    cl1 = A.app.test_client()
    cl2 = A.app.test_client()
    with cl1.session_transaction() as s:
        s["admin"] = u1; s["admin_role"] = "최고관리자"; s["_csrf"] = "c1"
    with cl2.session_transaction() as s:
        s["admin"] = u2; s["admin_role"] = "최고관리자"; s["_csrf"] = "c2"

    barrier = threading.Barrier(2, timeout=5)
    hit = {"n": 0}
    hit_lock = threading.Lock()

    class _Probe:
        def __init__(self, real):
            self._real = real

        def execute(self, sql, params=()):
            if sql == "SELECT * FROM insurers WHERE id=?":
                with hit_lock:
                    hit["n"] += 1
                try:
                    barrier.wait()
                except threading.BrokenBarrierError:
                    pass
            return self._real.execute(sql, params)

        def __getattr__(self, name):
            return getattr(self._real, name)

    _real_get_db = DB.get_db

    def _patched():
        return _Probe(_real_get_db())

    results = {}

    def worker(key, cl, hdr):
        r = cl.patch(f"/api/insurers/{iid}",
                     json={"status": "중지", "status_reason": "무등록 확인됨"}, headers=hdr)
        results[key] = (r.status_code, (r.get_json() or {}))

    DB.get_db = _patched
    A.DB.get_db = _patched
    t1 = threading.Thread(target=worker, args=("t1", cl1, {"X-CSRF-Token": "c1"}))
    t2 = threading.Thread(target=worker, args=("t2", cl2, {"X-CSRF-Token": "c2"}))
    t1.start(); t2.start(); t1.join(15); t2.join(15)
    DB.get_db = _real_get_db
    A.DB.get_db = _real_get_db

    conn = A.DB.get_db()
    notif_n = conn.execute(
        "SELECT COUNT(*) n FROM notifications WHERE ntype='보험사상태변경' AND insurer_id=?",
        (iid,)).fetchone()[0]
    #  ⚠ 이 DB는 세 시나리오(현재/되돌림/원복)가 공유한다 — detail LIKE '%상태%'만
    #    걸면 다른 시나리오의 보험사(D보험1/2/3)가 남긴 줄까지 섞여 든다.
    #    이 시나리오 자신의 보험사 이름으로 좁혀야 정확히 이번 호출분만 센다.
    log_n = conn.execute(
        "SELECT COUNT(*) n FROM activity_log WHERE action='보험사 정보 변경' "
        "AND detail LIKE ? AND detail LIKE '%상태%'",
        (f"{iname} —%",)).fetchone()[0]
    final_status = conn.execute("SELECT status FROM insurers WHERE id=?", (iid,)).fetchone()[0]
    conn.close()

    def _rj(v):
        code, body_ = v
        return [code, bool(body_.get("ok")), bool(body_.get("unchanged"))]

    return {
        "barrier_hits": hit["n"],
        "r1": _rj(results.get("t1", (None, {}))),
        "r2": _rj(results.get("t2", (None, {}))),
        "notify_count": notif_n,
        "activity_log_count": log_n,
        "final_status": final_status,
    }


try:
    iid1, iname1, u11, u12 = _seed_insurer()
    out = _run_concurrent_patch(iid1, iname1, u11, u12)
    chk(out["barrier_hits"] >= 1, "두 요청 중 적어도 하나는 실제로 그 지점에 도달했다(경합 시도 자체는 성립)", out)
    chk(out["r1"][0] == 200 and out["r2"][0] == 200, "새 코드: 두 요청 다 200을 받는다(회귀 아님, 에러로 막는 게 목적이 아니다)", out)
    chk(out["notify_count"] == 1,
        "★★★★★ 새 코드: 보험사에게 '보험사상태변경' 알림이 정확히 1번만 나간다(중복 통지 없음)", out)
    chk(out["activity_log_count"] == 1,
        "★★★★★ 새 코드: '상태' 변경을 언급하는 감사로그도 정확히 1건만 남는다(중복 없음)", out)
    chk(out["final_status"] == "중지", "최종 상태는 정상적으로 '중지'이다(회귀 아님)", out)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 되돌림-증명 — view_functions 딕셔너리 항목만 잠깐 치환(실제 파일은 안 건드림)")
    # ──────────────────────────────────────────────────────────
    _ns = dict(vars(A))
    exec(compile(REVERTED_FULL_FUNC, "<round506_reverted_insurer_update>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_fn = A.require_role("최고관리자")(_ns["api_insurer_update"])

    _orig_view = A.app.view_functions["api_insurer_update"]
    A.app.view_functions["api_insurer_update"] = old_fn
    try:
        iid2, iname2, u21, u22 = _seed_insurer()
        out2 = _run_concurrent_patch(iid2, iname2, u21, u22)
    finally:
        A.app.view_functions["api_insurer_update"] = _orig_view

    chk(out2["notify_count"] == 2,
        "★★★★★ 옛 코드(되돌림): 보험사에게 알림이 실제로 2번 나간다 — "
        "이 테스트가 진짜 결함(중복 통지·중복 감사로그)을 잡아낼 능력이 있음을 증명", out2)
    chk(out2["activity_log_count"] == 2,
        "★★★★★ 옛 코드(되돌림): '상태' 변경 감사로그도 실제로 2건 생긴다", out2)
    chk(out2["final_status"] == "중지", "옛 코드도 최종 상태 자체는 '중지'다(데이터 훼손은 아님, 부작용만 중복)", out2)

    print("\n[4] 원복 확인 — 되돌리기 이후 다시 잠기는가(바꿔치기가 안 샜다)")
    chk(A.app.view_functions["api_insurer_update"] is _orig_view,
        "  view_functions가 원래 함수객체로 복원됐다")
    iid3, iname3, u31, u32 = _seed_insurer()
    out3 = _run_concurrent_patch(iid3, iname3, u31, u32)
    chk(out3["notify_count"] == 1,
        "★★★★ 원복 후에는 다시 알림이 1번만 나간다(바꿔치기가 안 샜다)", out3)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] 실행/되돌림-증명", f"{type(e).__name__}: {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(view_functions 딕셔너리 항목 임시치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
