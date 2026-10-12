# -*- coding: utf-8 -*-
"""스캔 463라운드 회귀 — 출동 직접배정(assign_dispatch, supersede=true) 재시도
시 알림 중복발송 + 거짓 취소통지, 1건.

`assign_dispatch()`(dispatch.py)는 supersede=True 면 무조건 기존 진행중
수배를 취소하고 새로 만든다 — 이 재요청이 처음 요청인지 재시도인지 구분할
방법이 없다. 호출부(`api_dispatch_assign`, app.py)는 그 결과가 성공이면
항상 협력사·보험사에 notify()를 쐈다 — 관리자가 "이미 진행 중" 확인창을
누른 뒤 응답이 늦어 다시 누르거나 네트워크가 재시도하면, 이미 그 업체로
배정된 수배를 스스로 취소했다가 다시 만들어 그 업체에게 "다른 업체로
배정되어 취소되었습니다"(거짓 — 실제로는 자기 자신)와 "배정되었습니다"를
연달아 보낸다(라운드462가 확립한 "duplicate:true 조기반환" 관용구를 이
자리에도 이식).

[1] 소스 확인 — 재시도 조기반환 코드가 실제로 있음.
[2] 실제 Flask 앱으로 되돌림-증명 — api_dispatch_assign()은 단일 라우트
    핸들러라 A.app.view_functions 딕셔너리 항목만 잠깐 치환한다(이 함수
    자신의 현재 소스에서 신설 조기반환 블록만 제거한 사본을 exec로
    재구성, require_role 데코레이터도 다시 입힘) — 진짜 app.py 파일은
    전혀 안 건드린다(round615: 예전엔 디스크에 실제로 써서 전용 서브
    프로세스 워커[test_scan_round463_worker.py]로 재현했다가 복원하는
    방식이었다 — 그 워커 파일은 이제 폐기).
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


print("=" * 72)
print("  스캔 463라운드 회귀 — 직접배정(supersede) 재시도 알림 중복발송")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

OLD_CALL = '''        ok_, msg, did = DP.assign_dispatch(conn, cid, pid, d.get("reason") or "",
                                           by=actor(), supersede=_sup,
                                           on_supersede=_dispatch_supersede_notify(conn))'''

NEW_BLOCK = '''        #  ⚠⚠ [라운드463] assign_dispatch() 자신은 supersede=True 면 무조건 기존
        #    수배를 취소하고 새로 만든다 — 재요청인지 처음 요청인지 구분 못 한다.
        #    관리자가 "이미 진행 중" 확인창을 누른 뒤 응답이 늦어 다시 누르거나
        #    네트워크가 재시도하면, 이미 그 업체로 배정된 수배를 스스로 취소했다가
        #    다시 만들어 그 업체에게 "다른 업체로 배정되어 취소되었습니다"(거짓 —
        #    실제로는 자기 자신)와 "배정되었습니다"를 연달아 보낸다 — 실측(스크래치
        #    DB): 같은 업체로 supersede 재시도 시 알림톡 2회 + 거짓 취소통지 1회.
        #    요청받은 업체가 이미 그 수배를 잡고 있으면 그대로 duplicate 로 반환해
        #    assign_dispatch()도 notify()도 건드리지 않는다 — 다른 업체로 실제
        #    갈아타는 정상 supersede 는 이 조건에 안 걸려 그대로 동작한다.
        if _sup:
            _live_dispatch = one(conn.execute(
                "SELECT id, claimed_partner_id FROM dispatches "
                " WHERE case_id=? AND status IN (?,?)",
                (cid, DP.ST_OPEN, DP.ST_CLAIMED)))
            if _live_dispatch and _live_dispatch.get("claimed_partner_id") == pid:
                return jsonify({"ok": True, "duplicate": True,
                                "dispatch_id": _live_dispatch["id"],
                                "message": "이미 이 업체로 배정되어 있습니다."})
''' + OLD_CALL

chk(NEW_BLOCK in APP_SRC,
    "★★★★★ api_dispatch_assign()에 재시도 조기반환 코드가 있다")
chk(APP_SRC.count(NEW_BLOCK) == 1,
    "되돌림-증명에 쓸 새 블록이 소스에 정확히 1번만 있다(대체 지점 특정 가능)",
    APP_SRC.count(NEW_BLOCK))


def _py_fn_body(src, fn_name):
    """함수 본문 — 다음 def뿐 아니라 다음 라우트의 @app. 데코레이터가 먼저
    나오면 거기서 자른다(round610 정착 기법)."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


_body = _py_fn_body(APP_SRC, "api_dispatch_assign")
chk(NEW_BLOCK in _body, "  api_dispatch_assign() 본문 안에 NEW_BLOCK이 있다")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round463_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('r463admin','x','검증','최고관리자')")
    iid = conn0.execute("INSERT INTO insurers(name,status) VALUES('R463보험','활성')").lastrowid
    pid = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,lat,lng) "
        "VALUES('R463업체','시행사','활성',37.5,127.0)").lastrowid
    conn0.commit()
    conn0.close()

    def _admin_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["admin"] = "r463admin"; sess["admin_role"] = "최고관리자"
            sess["_csrf"] = "r463-csrf"
        return c

    def _new_case(no):
        c = DB.get_db()
        cid = c.execute(
            "INSERT INTO cases(case_no,status,category,region,insurer_id,lat,lng) "
            "VALUES(?,?,?,?,?,?,?)", (no, "접수", "가드레일", "서울", iid, 37.5, 127.0)).lastrowid
        c.commit(); c.close()
        return cid

    def _scenario(cid):
        """해당 case에 직접배정 1회 → 곧이어 같은 업체로 supersede 재시도, 집계 반환."""
        c = _admin_client()
        r1 = c.post(f"/api/cases/{cid}/dispatch/assign",
                    json={"partner_id": pid, "reason": "전화 확인 후 직접배정 테스트"},
                    headers={"X-CSRF-Token": "r463-csrf"})
        r2 = c.post(f"/api/cases/{cid}/dispatch/assign",
                    json={"partner_id": pid, "reason": "전화 확인 후 직접배정 테스트",
                          "supersede": True},
                    headers={"X-CSRF-Token": "r463-csrf"})
        conn2 = DB.get_db()
        n_assign = conn2.execute(
            "SELECT COUNT(*) n FROM notifications WHERE ntype='출동배정' AND channel='알림톡' "
            " AND case_id=?", (cid,)).fetchone()["n"]
        n_cancel = conn2.execute(
            "SELECT COUNT(*) n FROM notifications WHERE ntype='출동취소' AND case_id=?",
            (cid,)).fetchone()["n"]
        n_disp = conn2.execute(
            "SELECT COUNT(*) n FROM dispatches WHERE case_id=?", (cid,)).fetchone()["n"]
        conn2.close()
        return {"r1": r1.get_json() or {}, "r2": r2.get_json() or {},
                "assign_notify": n_assign, "cancel_notify": n_cancel, "dispatches": n_disp}

    print("\n[3] 실행 — 현재(고쳐진) 코드")
    fixed = _scenario(_new_case("26-463001"))
    chk(fixed["r1"].get("duplicate") is not True,
        "첫 호출(신규 직접배정)은 duplicate 표시 없이 정상 성공", fixed["r1"])
    chk(fixed["r2"].get("duplicate") is True,
        "★★★★★ 같은 업체로 supersede 재시도(2번째 호출)는 duplicate:true로 조용히 성공만 돌려준다",
        fixed["r2"])
    chk(fixed["dispatches"] == 1,
        "★★★★★ 고쳐진 코드는 재시도해도 dispatches가 1행(최초분)만 남는다(취소·재생성 없음)",
        fixed["dispatches"])
    chk(fixed["assign_notify"] == 1,
        "★★★★★ 고쳐진 코드는 두 번 호출해도 출동배정 알림톡이 1건(최초 1회분)만 쌓인다",
        fixed["assign_notify"])
    chk(fixed["cancel_notify"] == 0,
        "★★★★★ 고쳐진 코드는 거짓 출동취소 통지가 전혀 안 나간다",
        fixed["cancel_notify"])

    print("\n[4] 되돌리기 — api_dispatch_assign만 옛 코드로(실제 파일은 안 건드림)")
    _old_body = (_body
                 .replace("def api_dispatch_assign(cid):",
                          "def _api_dispatch_assign_pre463(cid):", 1)
                 .replace(NEW_BLOCK, OLD_CALL, 1))
    chk(_old_body.count(OLD_CALL) == 1 and "_api_dispatch_assign_pre463" in _old_body,
        "  (준비) 함수 리네임 + 조기반환 제거가 정확히 적용됐다(실제 파일은 안 건드림)")

    _ns = dict(vars(A))
    exec(compile(_old_body, "<round463_pre463_dispatch_assign>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_fn = A.require_role("중간관리자")(_ns["_api_dispatch_assign_pre463"])

    _orig_view = A.app.view_functions["api_dispatch_assign"]
    A.app.view_functions["api_dispatch_assign"] = old_fn
    try:
        broken = _scenario(_new_case("26-463002"))
    finally:
        A.app.view_functions["api_dispatch_assign"] = _orig_view

    chk("duplicate" not in broken["r1"] and "duplicate" not in broken["r2"],
        "옛 코드(되돌림)는 duplicate 표시 자체가 없다(구분할 방법이 없었음을 증명)",
        (broken["r1"].get("duplicate"), broken["r2"].get("duplicate")))
    chk(broken["dispatches"] == 2,
        "★★★★★ 옛 코드(되돌림)는 재시도 시 dispatches가 실제로 2행(취소1+재생성1)까지 쌓인다",
        broken["dispatches"])
    chk(broken["assign_notify"] == 2,
        "★★★★★ 옛 코드(되돌림)는 두 번 호출하면 출동배정 알림톡이 실제로 2건 쌓인다"
        " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
        broken["assign_notify"])
    chk(broken["cancel_notify"] == 1,
        "★★★★★ 옛 코드(되돌림)는 같은 업체에게 거짓 출동취소 통지가 실제로 1건 나간다",
        broken["cancel_notify"])

    print("\n[5] 원복 확인 — 되돌리기 이후 다시 방어되는가(바꿔치기가 안 샜다)")
    chk(A.app.view_functions["api_dispatch_assign"] is _orig_view,
        "  view_functions가 원래 함수객체로 복원됐다")
    restored = _scenario(_new_case("26-463003"))
    chk(restored["r2"].get("duplicate") is True and restored["dispatches"] == 1,
        "★★★★ 원복 후에는 다시 duplicate:true 조기반환이 정상 방어된다(바꿔치기가 안 샜다)",
        restored)

except Exception as e:                                              # noqa: BLE001
    chk(False, "[2] 되돌림-증명 준비/실행", f"{type(e).__name__}: {e}")

APP_HASH_AFTER = io.open(APP_PATH, encoding="utf-8").read()
chk(APP_HASH_AFTER == APP_SRC,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(view_functions 딕셔너리 항목 임시치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
