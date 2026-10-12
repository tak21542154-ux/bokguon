# -*- coding: utf-8 -*-
"""스캔 415라운드 회귀 — sweep_auctions()(app.py, 무입찰 유찰/원경매 마감 처리)와
   형제 스윕 5종(sweep_no_bid_alert·sweep_report_overdue·sweep_warranty_expiry·
   sweep_approval_overdue·_sweep_award_approval)의 루프 구간에 예외처리가
   전무하던 결함(정밀조사 Agent 발견, 411~414에 이은 5연속째 "형제는 이미
   쓰는 관례를 한 곳만 안 따름" — 이번엔 스윕함수 9종 중 6개가 한꺼번에).

   sweep_auctions() 는 특히 심각했다: 루프 안에서 예외가 나면 finally 가 부르는
   _sweep_release() 가 **자기 자신의 무관한 UPDATE 를 커밋**하면서, 그 순간
   같은 트랜잭션에 열려 있던 실패한 타겟의 미완성 쓰기(예: cases.status='유찰'
   로 이미 바꿔놓은 것)까지 조용히 함께 확정된다 — 감사로그·알림은 하나도
   안 남았는데 상태만 바뀌는 유령 전환. 게다가 예외는 그대로 manage.py::
   cmd_sweep()/main() 까지 뚫고 나가(둘 다 except 없음) 예약 스케줄러
   프로세스를 콘솔 없이 죽여, 그 회차의 나머지 스윕(웹훅 재시도 등, 411·412가
   막 고친 것들 포함)이 통째로 안 돈다.

   고침: sweep_auctions() 는 이미 항목별로 커밋하므로, 형제 sweep_dispatches()
   의 이미 검증된 항목별 try/except/rollback/continue 패턴을 그대로 이식 —
   이전에 이미 커밋된 항목은 그대로 두고, 실패한 항목만 롤백 후 다음 항목으로
   넘어간다(재발생 안 함, 나머지 타겟은 계속 처리됨). 나머지 5개는 함수 끝에
   한 번만 커밋하는 배치형이라 항목별 롤백이 다른 항목의 진행분까지 지워버릴
   위험이 없어 — 대신 루프 구간 전체를 하나로 묶어, 실패 시 배치 전체를
   롤백하고 로그를 남긴 뒤 조용히 종료한다(이 함수들 자신의 SELECT 단계가
   이미 쓰는 "가드하고 실패하면 롤백 후 반환" 패턴을 루프까지 넓힌 것뿐 —
   새 메커니즘 없음. 오늘 실패 시 이미 아무것도 안 커밋되던 것과 최종 결과는
   같고, 차이는 "정체불명 크래시"가 "로그 남기고 깔끔히 반환"으로 바뀌는 것).

       python test_scan_round415_fixes.py
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


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 415라운드 회귀 — sweep_auctions + 형제 5종의 루프 예외처리 부재")
print("=" * 72)

print("\n[1] 소스 확인 — 6개 함수 전부 try/except 로 루프를 감쌌다")


def body_of(fn_name):
    i0 = APP_SRC.index(f"def {fn_name}(")
    i1 = APP_SRC.index("\ndef ", i0 + 1)
    return APP_SRC[i0:i1]


chk('res["errors"] = res.get("errors", 0) + 1' in body_of("sweep_auctions"),
    "★★★★★ sweep_auctions() 가 항목별 try/except 로 errors 카운터를 남긴다")
chk('경매 마감 처리 실패' in body_of("sweep_auctions"),
    "  실패 시 app.logger.exception 으로 남긴다")

for fn, marker in [
    ("sweep_no_bid_alert", "무입찰 경보 처리 실패"),
    ("sweep_report_overdue", "완료보고 지연 점검 실패"),
    ("sweep_warranty_expiry", "보증만료 알림 처리 실패"),
    ("sweep_approval_overdue", "완료승인 독촉 처리 실패"),
    ("_sweep_award_approval", "낙찰승인 독촉 처리 실패"),
]:
    b = body_of(fn)
    chk(marker in b and "except Exception:" in b,
        f"★★★★ {fn}() 가 루프 구간을 try/except 로 감쌌다")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round415_")
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

    def _mk_case_auction(no, insurer_id=None):
        conn.execute(
            "INSERT INTO cases(case_no, status, is_demo, insurer_id) "
            "VALUES(?,'입찰중',0,?)", (no, insurer_id))
        cid = conn.execute("SELECT id FROM cases WHERE case_no=?", (no,)).fetchone()["id"]
        conn.execute(
            "INSERT INTO auctions(case_id, deadline, status) "
            "VALUES(?, datetime('now','-1 hours'), '진행')", (cid,))
        aid = conn.execute("SELECT id FROM auctions WHERE case_id=?", (cid,)).fetchone()["id"]
        return cid, aid

    print("\n[3] 실행 — sweep_auctions(): 실패한 타겟은 롤백, 다른 타겟은 계속 처리")
    cid_a, aid_a = _mk_case_auction("R415-A")
    cid_b, aid_b = _mk_case_auction("R415-B")
    conn.commit()

    _orig_notify = A.notify
    _fail_case = {"id": cid_a}

    def _notify_fail_target(conn_, ntype, channel, target, message, **kw):
        if kw.get("case_id") == _fail_case["id"]:
            raise RuntimeError("★ 시뮬레이션된 notify 실패(타겟A)")
        return _orig_notify(conn_, ntype, channel, target, message, **kw)

    A.notify = _notify_fail_target
    try:
        res = A.sweep_auctions(conn, force=True)
    finally:
        A.notify = _orig_notify

    chk(res.get("errors") == 1, "★★★★★ 타겟A 실패가 errors=1 로 집계됐다(예외가 밖으로 안 샘)", res)
    chk(res.get("failed") == 1, "  타겟B(무입찰 유찰)는 정상적으로 처리됐다(failed=1)", res)

    rowA = conn.execute("SELECT status FROM cases WHERE id=?", (cid_a,)).fetchone()
    rowB = conn.execute("SELECT status FROM cases WHERE id=?", (cid_b,)).fetchone()
    chk(rowA["status"] == "입찰중",
        "★★★★★ 타겟A는 롤백돼 상태가 그대로다(고치기 전엔 '유찰'로 유령 전환됐다)",
        rowA["status"])
    chk(rowB["status"] == "유찰",
        "★★★★ 타겟B는 정상적으로 '유찰'까지 처리됐다(한 타겟의 실패가 다른 타겟을 안 막는다)",
        rowB["status"])
    n_log_a = conn.execute(
        "SELECT COUNT(*) c FROM activity_log WHERE detail LIKE '%R415-A%'").fetchone()["c"]
    chk(n_log_a == 0, "  타겟A는 감사로그도 안 남았다(유령 전환이 아예 없다)", n_log_a)

    print("\n[4] 실행 — sweep_report_overdue(): 실패 시 배치 전체가 조용히 반환된다")
    conn.execute(
        "INSERT INTO cases(case_no, status, is_demo, awarded_at) "
        "VALUES('R415-C','시공중',0,datetime('now','-100 hours'))")
    cid_c = conn.execute("SELECT id FROM cases WHERE case_no='R415-C'").fetchone()["id"]
    conn.commit()

    def _notify_always_fail(*a, **kw):
        raise RuntimeError("★ 시뮬레이션된 notify 실패(report_overdue)")

    A.notify = _notify_always_fail
    try:
        n = A.sweep_report_overdue(conn)
    except Exception as e:                                          # noqa: BLE001
        n = None
        chk(False, "★★★★★ sweep_report_overdue() 가 예외를 안으로 삼켜야 하는데 밖으로 샜다",
            f"{type(e).__name__} {e}")
    else:
        chk(n == 0, "★★★★★ 예외 발생 시 0을 반환하고 조용히 끝난다(밖으로 안 샘)", n)
    finally:
        A.notify = _orig_notify

    rowC = conn.execute("SELECT status FROM cases WHERE id=?", (cid_c,)).fetchone()
    chk(rowC["status"] == "시공중",
        "★★★★ 실패한 배치는 롤백돼 상태가 그대로다(부분 커밋 없음)", rowC["status"])

    print("\n[5] 대조군 — 정상 상황은 회귀 없이 그대로 동작")
    conn.execute("UPDATE cases SET status='시공중' WHERE id=?", (cid_c,))
    conn.commit()
    n2 = A.sweep_report_overdue(conn)
    chk(n2 == 1, "  정상 실행은 여전히 1건 처리한다(회귀없음)", n2)
    rowC2 = conn.execute("SELECT status FROM cases WHERE id=?", (cid_c,)).fetchone()
    chk(rowC2["status"] == "완료보고지연", "  정상 실행은 여전히 상태를 바꾼다(회귀없음)", rowC2["status"])

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[6] 되돌리기 — 옛 코드로 되돌리면 재현되는가(디스크 미기록)")
# ------------------------------------------------------------
#  ⚠⚠ [라운드613] round409~515대 옛 세대 기법(되돌린 전체 app.py 를 실제
#    APP_PATH 에 잠깐 써넣고 서브프로세스로 재현한 뒤 원본을 복원 — 그
#    write→subprocess→write 사이의 창을 다른 세션이 관측하면 충돌한다,
#    round590이 실제로 겪음)을 round411·610이 확립한 안전패턴으로 이관.
#    sweep_auctions·sweep_report_overdue 는 서로 안 부르는 독립 모듈함수라
#    (dispatch.py의 open_dispatch/sweep_dispatches 쌍과 달리) 공유 네임스페이스를
#    맞출 필요 없이, 각자 exec(compile(...))로 자기 전용 사본 네임스페이스에
#    재구성해 직접 호출한다 — 라우트가 아니므로 view_functions 치환도 불필요
#    (진짜 app.py도, 실제 로드된 A 모듈도 전혀 안 건드림).
try:
    #  sweep_auctions 만 되돌리기: try:/except Exception: 블록을 걷어내고
    #  본문을 한 단계 얕게 되돌린다(들여쓰기만 원복 — 재타이핑 없이 텍스트로).
    _body = body_of("sweep_auctions")
    _try_start = _body.index("            try:\n                conn.execute(\"BEGIN IMMEDIATE\")")
    _except_start = _body.index("            except Exception:\n                app.logger.exception(\n"
                                 "                    \"경매 마감 처리 실패")
    _loop_end = _body.index("\n    finally:\n        if not dry_run:", _except_start)
    _inner = _body[_try_start + len("            try:\n"):_except_start]
    _dedented = "\n".join(
        (l[4:] if l.startswith("    ") else l) for l in _inner.split("\n"))
    reverted_auctions_body = _body[:_try_start] + _dedented + _body[_loop_end:]
    chk(reverted_auctions_body != _body, "  (준비) sweep_auctions 되돌리기 텍스트가 실제로 달라졌다")

    conn = DB.get_db()   # [2]~[5]가 이미 닫은 conn 대신 같은 스크래치 DB에 새로 연결
    _orig_notify2 = A.notify
    cid_a2, aid_a2 = _mk_case_auction("R415-REV-A")
    cid_b2, aid_b2 = _mk_case_auction("R415-REV-B")
    conn.commit()

    _ns1 = dict(vars(A))
    exec(compile(reverted_auctions_body, "<round415_old_sweep_auctions>", "exec"), _ns1)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_sweep_auctions = _ns1["sweep_auctions"]

    def _notify_fail_a2(conn_, ntype, channel, target, message, **kw):
        if kw.get("case_id") == cid_a2:
            raise RuntimeError("★ 시뮬레이션된 notify 실패(되돌리기용, 타겟A)")
        return _orig_notify2(conn_, ntype, channel, target, message, **kw)

    _ns1["notify"] = _notify_fail_a2   # 되돌린 함수는 __globals__=_ns1(사본)이라 이 안에서만 가로챈다(A.notify는 안 건드림)

    raised1 = None
    try:
        old_sweep_auctions(conn, force=True)
    except Exception as e:                                          # noqa: BLE001
        raised1 = e
    chk(raised1 is not None,
        "★★★★★ 옛 코드는 예외가 그대로 밖으로 샌다(인과관계 직접증명)",
        f"{type(raised1).__name__}: {raised1}" if raised1 else "예외 없음")

    row_a2 = conn.execute("SELECT status FROM cases WHERE id=?", (cid_a2,)).fetchone()
    chk(row_a2["status"] == "유찰",
        "★★★★★ 옛 코드는 그런데도 타겟A가 '유찰'로 유령 전환돼 있다"
        "(finally 의 _sweep_release 커밋에 편승 — 인과관계 직접증명)", row_a2["status"])

    #  sweep_report_overdue 만 되돌리기
    _body2 = body_of("sweep_report_overdue")
    _try2_start = _body2.index("    try:\n        hours = _setting_int(")
    _except2_start = _body2.index("    except Exception:\n        app.logger.exception(\"완료보고 지연 점검 실패\")")
    _tail2_start = _body2.index("\n    #  ★ **0행이어도", _except2_start)
    _inner2 = _body2[_try2_start + len("    try:\n"):_except2_start]
    _dedented2 = "\n".join(
        (l[4:] if l.startswith("    ") else l) for l in _inner2.split("\n"))
    reverted_report_body = _body2[:_try2_start] + _dedented2 + _body2[_tail2_start:]
    chk(reverted_report_body != _body2, "  (준비) sweep_report_overdue 되돌리기 텍스트가 실제로 달라졌다")

    conn.execute(
        "INSERT INTO cases(case_no, status, is_demo, awarded_at) "
        "VALUES('R415-REV-C','시공중',0,datetime('now','-100 hours'))")
    conn.commit()

    _ns2 = dict(vars(A))
    exec(compile(reverted_report_body, "<round415_old_sweep_report_overdue>", "exec"), _ns2)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_sweep_report_overdue = _ns2["sweep_report_overdue"]

    def _notify_always_fail2(*a, **kw):
        raise RuntimeError("★ 시뮬레이션된 notify 실패(되돌리기용, report_overdue)")

    _ns2["notify"] = _notify_always_fail2

    raised2 = None
    try:
        old_sweep_report_overdue(conn)
    except Exception as e:                                          # noqa: BLE001
        raised2 = e
    chk(raised2 is not None,
        "★★★★★ 옛 코드는 sweep_report_overdue()도 예외가 그대로 밖으로 샌다"
        "(인과관계 직접증명)",
        f"{type(raised2).__name__}: {raised2}" if raised2 else "예외 없음")

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
