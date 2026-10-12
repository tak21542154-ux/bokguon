# -*- coding: utf-8 -*-
"""스캔 411라운드 회귀 — open_dispatch() 의 알림 마무리기록(트랜잭션 밖)이
   이 파일의 다른 모든 트랜잭션 블록과 달리 무방비였던 결함 + api_co_offer()
   의 자동 낙찰자 선정에 동점 처리 기준이 없던 결함.

  배경 [1]: open_dispatch()(dispatch.py:288-415)는 본 트랜잭션(DB쓰기, 302-390행,
  이미 try/except/rollback으로 방어)과 "트랜잭션 밖 알림"(392-415행) 2단계
  구조다. notify() 콜백들 자체는 개별 try/except 로 감쌌지만, 그 뒤의 마무리
  기록(DB.log)과 conn.commit() 은 무방비였다 — 락 경합 등으로 이 commit 이
  실패하면 예외가 함수 밖으로 그대로 터지고, notify() 의 INSERT 가 이미 열어
  둔 암시적 트랜잭션(411-413행 자신의 주석이 명시)이 커밋도 롤백도 안 된 채
  커넥션에 남는다. sweep_dispatches()(dispatch.py:719-838)의 호출부(818-825행)
  는 이 예외를 잡긴 하지만 rollback 을 안 해, 다음 대상의 BEGIN IMMEDIATE
  (775행, try 블록 **밖**)가 "cannot start a transaction within a transaction"
  으로 죽는다 — manage.py cmd_sweep() 은 스윕들을 하나의 try 로 묶어서
  (959-1001행) 이게 sweep_send_notifications·sweep_webhook_retries 까지 그
  회차 통째로 건너뛰게 만든다.

  배경 [2]: api_co_offer()(app.py:9808-9862)는 이 코드베이스에서 사람 확인
  없이 자동으로 낙찰자를 정하는 유일한 자리인데(다른 낙찰경로는 전부 사람이
  bid_id 를 직접 골라 보낸다), 최저가 조회(9825-29행)에 `ORDER BY b.amount
  ASC LIMIT 1` 만 있고 동점일 때를 가르는 기준이 없었다.

  고침: [1] 이 파일의 다른 모든 자리처럼 마무리기록+commit 을 try/except/
  rollback 으로 감싸고, sweep_dispatches() 의 재수배 except 에도 rollback 을
  추가(사람이 새로 판단할 위험 없음 — 이미 있는 지역 관례를 그대로 적용).
  [2] ORDER BY 에 `, b.id ASC` 를 더해 먼저 낸 입찰이 동점을 이기게 한다.

      python test_scan_round411_fixes.py
"""
import io
import os
import shutil
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")
DISPATCH_SRC = read("dispatch.py")

print("=" * 72)
print("  스캔 411라운드 회귀 — 출동수배 알림 마무리기록 무방비 + 추가분 낙찰 동점처리")
print("=" * 72)

print("\n[1] 소스 확인")
chk("ORDER BY b.amount ASC, b.id ASC LIMIT 1" in APP_SRC,
    "★★ api_co_offer 의 최저가 조회에 id 동점처리 기준이 생겼다")


def _dispatch_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


_od_body = _dispatch_fn_body(DISPATCH_SRC, "open_dispatch")
chk("try:\n            if sent < len(cands):" in _od_body and "conn.rollback()\n        except Exception:\n            raise"
    not in _od_body,  # 최상단 본트랜잭션의 try(다른 자리)와 안 섞였는지 형태만 대략 확인
    "  open_dispatch 본문에 새 try 블록이 들어갔다(형태 확인)")
chk(_od_body.count("except Exception:") >= 3,
    "★★★★★ open_dispatch 안의 except 블록이 최소 3개(본트랜잭션·개별notify·"
    "마무리기록)로 늘었다", _od_body.count("except Exception:"))

_sd_body = _dispatch_fn_body(DISPATCH_SRC, "sweep_dispatches")
_except_block = _sd_body[_sd_body.index("except Exception:\n                    #  ⚠⚠ [라운드182]"):]
chk("conn.rollback()\n                    _log.exception(\"자동 재수배 실패" in _except_block,
    "★★★★★ sweep_dispatches 의 재수배 except 가 rollback 을 먼저 부른다")

print("\n[2] 실행 — 결정론적 프록시로 '알림 마무리기록 commit만' 정확히 실패시킨다")
#  ⚠ 진짜 파일락 경합(별도 커넥션이 BEGIN IMMEDIATE 로 잠금)으로 재현을 먼저
#    시도했으나, 그 잠금이 sweep_dispatches() 호출 내내 계속 걸려 있어 두
#    번째 대상의 만료phase 자체(775행, 이 결함과 무관한 자리)까지 "database
#    is locked" 로 실패해 오히려 무엇을 재현 중인지 흐려졌다(실측으로 확인 후
#    방향 수정 — 자기 결론도 재검증하라는 이 세션의 원칙 그대로 적용). 대신
#    conn 을 감싸는 얇은 프록시로 "정확히 3번째 commit() 호출"(대상1의 만료
#    phase→open_dispatch 본트랜잭션→**알림 마무리기록**, 그 뒤로는 그대로
#    진짜 commit)만 실패시켜, 타이밍에 기대지 않고 결정론적으로 정확히 이
#    결함이 다루는 자리 하나만 겨냥한다.
_tmpdir = tempfile.mkdtemp(prefix="round411_")
_dbpath = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_DB_PATH"] = _dbpath
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)


def _setup_two_overdue(connA, iid, pid, mark):
    def mkcase(n):
        cur = connA.execute(
            "INSERT INTO cases(case_no,insurer_id,insurer,category,region,address,"
            "                  est_price,low_price,status,intake_type,created_at,is_demo) "
            "VALUES(?,?,?,?,?,?,0,0,'접수','사진없음',?,0)",
            (f"{mark}-{n}", iid, "검증보험", "가드레일·방호울타리", "서울 송파구",
             "서울 송파구 오금로", DB.now()))
        return cur.lastrowid

    cid1, cid2 = mkcase(1), mkcase(2)
    did1 = connA.execute(
        "INSERT INTO dispatches(case_id,round,status,claimed_partner_id,claimed_name,"
        "                       claimed_at,due_at,created_at) "
        "VALUES(?,1,'수배됨',?,?,?,?,?)",
        (cid1, pid, f"{mark}업체", DB.now(), "2000-01-01 00:00:00", DB.now())).lastrowid
    did2 = connA.execute(
        "INSERT INTO dispatches(case_id,round,status,claimed_partner_id,claimed_name,"
        "                       claimed_at,due_at,created_at) "
        "VALUES(?,1,'수배됨',?,?,?,?,?)",
        (cid2, pid, f"{mark}업체", DB.now(), "2000-01-01 00:00:00", DB.now())).lastrowid
    connA.commit()
    return cid1, did1, cid2, did2


class _FailNthCommit:
    """conn 을 감싸 지정한 순번의 commit() 호출 하나만 진짜로는 안 부르고
       예외를 낸다 — 그 순간까지의 쓰기가 롤백도 커밋도 안 된 채 실제로
       남는 상태를 결정론적으로 재현한다(타이밍 경쟁 없음)."""
    def __init__(self, real, fail_at_call):
        self._real, self._n, self._fail_at = real, 0, fail_at_call
        self.failed_once = False

    def commit(self):
        self._n += 1
        if self._n == self._fail_at:
            self.failed_once = True
            raise sqlite3.OperationalError("simulated: database is locked")
        return self._real.commit()

    def __getattr__(self, name):
        return getattr(self._real, name)


def _run_scenario(connA, mark, fail_at_call, sweep_fn=None):
    """대상 2건짜리 sweep_dispatches() 를 3번째 commit()만 실패시켜 돌린다.
       sweep_fn 을 안 주면 지금(고친) DP.sweep_dispatches 를 쓰고, [3]에서는
       exec 로 재구성한 옛 버전을 넘겨 같은 시나리오를 그대로 재사용한다."""
    def real_notify(partner_id, dispatch_id, case_id):
        #  실제 _dispatch_notify() 처럼 같은 커넥션에 진짜 쓰기를 남겨,
        #  그 뒤 마무리기록 commit 이 실패하면 이 쓰기가 롤백 안 된 채
        #  커넥션에 남는 실제 시나리오를 정확히 재현한다.
        connA.execute("UPDATE job_locks SET last_note='r411-probe' WHERE name='dispatch_sweep'")

    cid1, did1, cid2, did2 = _setup_two_overdue(connA, iid, pid, mark)
    proxy = _FailNthCommit(connA, fail_at_call=fail_at_call)
    raised = None
    fn = sweep_fn or DP.sweep_dispatches
    try:
        fn(proxy, force=True, notify=real_notify)
    except Exception as e:                                          # noqa: BLE001
        raised = e
    return cid1, cid2, proxy, raised


try:
    import db as DB
    DB.init_db()
    import dispatch as DP

    connA = DB.get_db()
    iid = connA.execute("INSERT INTO insurers(name) VALUES('검증보험')").lastrowid
    pid = connA.execute(
        "INSERT INTO partners(name,status,region,address,category,phone,created_at) "
        "VALUES('R411업체','활성','서울 송파구','서울 송파구 오금로','가드레일·방호울타리','01011112222',?)",
        (DB.now(),)).lastrowid
    connA.commit()

    cid1, cid2, proxy1, raised1 = _run_scenario(connA, "R411", fail_at_call=3)

    chk(proxy1.failed_once,
        "  준비 확인 — 의도한 3번째 commit(대상1의 알림 마무리기록)이 실제로 실패했다")
    chk(raised1 is None,
        "★★★★★ 대상1의 마무리기록이 실패해도 sweep_dispatches() 는 이제 "
        "예외 없이 정상 반환한다(고치기 전엔 대상2의 BEGIN IMMEDIATE가 "
        "'transaction within a transaction'으로 죽어 함수 밖까지 샜다)",
        f"{type(raised1).__name__}: {raised1}" if raised1 else "정상")

    n_new = connA.execute(
        "SELECT COUNT(*) c FROM dispatches WHERE case_id IN (?,?) AND round=2",
        (cid1, cid2)).fetchone()["c"]
    chk(n_new == 2,
        "★★★★★ 대상1의 재수배가 실패했어도 대상2는 정상적으로 재수배(round=2)"
        "가 열렸다(대상1 실패가 대상2를 막지 않았다)", n_new)

    print("\n[3] 되돌리기 — 옛 코드(마무리기록 무방비)로 되돌리면 같은 조건에서 재현되는가")
    #  ⚠⚠ [라운드612] round412·414가 확립한 안전패턴으로 이관 — 원래는 되돌린 전체
    #    dispatch.py 소스를 실제 on-disk DISPATCH_PATH 에 잠깐 써넣고 importlib.
    #    reload(DP) 로 재현한 뒤 finally 에서 복원+재reload 했다(round409~515대
    #    옛 세대 기법 — write→reload→...→write→reload 사이의 창을 다른 세션이
    #    관측하면 충돌한다, round590이 실제로 겪음). open_dispatch·sweep_dispatches
    #    두 함수 본문만 문자열로 옛 형태로 되돌려 exec(compile(...))로 **같은**
    #    네임스페이스 사본(_ns)에 순서대로 재구성한다 — sweep_dispatches 재구성본이
    #    내부에서 bare-name 으로 참조하는 open_dispatch 도 이 _ns 안의 되돌린
    #    버전을 보게 된다(전역 lookup 은 함수의 __globals__=_ns 기준). 이 함수는
    #    (Flask 라우트와 달리) 모듈 함수라 view_functions 치환도 필요 없다 —
    #    _run_scenario() 에 재구성한 함수를 직접 넘겨서 부른다(실제 dispatch.py
    #    파일도, 실제 로드된 DP 모듈도 전혀 안 건드림). 두 수정이 서로 독립적으로도
    #    캐스케이드를 막으므로(주석대로) 옛 버그 재현엔 반드시 둘 다 되돌려야 한다.
    _od_cur = _dispatch_fn_body(DISPATCH_SRC, "open_dispatch")
    NEW_TAIL_START = "        try:\n            if sent < len(cands):"
    OLD_TAIL = (
        "        if sent < len(cands):\n"
        "            DB.log(conn, \"시스템\", \"출동수배 알림 실패\",\n"
        "                   f\"수배 {did} · {cs[2]} · {len(cands)}개사 중 {sent}건만 발송\"\n"
        "                   + (\" — 아무에게도 못 갔습니다. 직접 배정이 필요합니다.\"\n"
        "                      if not sent else \"\"))\n"
        "        conn.commit()\n"
        "    return did, len(cands), sent"
    )
    chk(NEW_TAIL_START in _od_cur,
        "  되돌리기 준비 — open_dispatch 현재 본문이 고친 형태(새 try)를 담고 있다")
    _new_start = _od_cur.index(NEW_TAIL_START)
    _new_end = _od_cur.index("    return did, len(cands), sent") + len("    return did, len(cands), sent")
    reverted_od = _od_cur[:_new_start] + OLD_TAIL + _od_cur[_new_end:]
    chk("except Exception:\n            conn.rollback()\n            raise\n    return did"
        not in reverted_od,
        "  되돌리기 준비 — 되돌린 open_dispatch 본문에 새 코드 흔적이 안 남는다"
        "(실제 파일은 안 건드림)")

    #  ⚠ 두 수정은 서로 독립적으로도 이 캐스케이드를 막는다(sweep_dispatches
    #    쪽 rollback 하나만 있어도 커넥션은 정리된다) — 옛 버그를 실제로
    #    재현하려면 open_dispatch 쪽뿐 아니라 이 rollback 도 함께 없애야
    #    한다(처음엔 하나만 되돌렸다가 재현이 안 돼 직접 확인 후 수정함).
    _sd_cur2 = _dispatch_fn_body(DISPATCH_SRC, "sweep_dispatches")
    reverted_sd = _sd_cur2.replace(
        "                    conn.rollback()\n"
        "                    _log.exception(\"자동 재수배 실패 case=%s\", t[\"case_id\"])",
        "                    _log.exception(\"자동 재수배 실패 case=%s\", t[\"case_id\"])")
    #  ⚠⚠ [라운드558] 이 표식이 "자동 재수배 실패" 메시지 없이 들여쓰기+
    #    자리표만으로 되어 있었다 — 라운드558이 바로 옆 회차소진 처리기에도
    #    (raise 대신) rollback+_log.exception 을 추가하면서, 같은 루프 안
    #    같은 깊이의 그 자리도 우연히 같은 모양("                    conn.
    #    rollback()\n                    _log.exception")이 되어 이 표식이
    #    엉뚱하게 걸렸다(이 파일이 지우는 대상은 942행 재수배 처리기 하나
    #    뿐인데, 회차소진 처리기의 다른 메시지가 남아 있어도 이 체크가 실패로
    #    오판했다). 위 .replace() 처럼 메시지("자동 재수배 실패")까지
    #    포함해 정확히 그 한 자리만 가리키게 좁힌다 — 라운드558 자체를
    #    되돌리는 게 아니라, 이 파일이 원래 지우려던 것(재수배 처리기의
    #    round182·411 수정)만 지워졌는지 확인하는 것이 이 체크의 목적이다.
    chk("                    conn.rollback()\n                    _log.exception(\"자동 재수배 실패"
        not in reverted_sd,
        "  되돌리기 준비 — 되돌린 sweep_dispatches 본문에 새 코드 흔적이 안 남는다"
        "(실제 파일은 안 건드림)")

    _ns = dict(vars(DP))
    exec(compile(reverted_od, "<round411_pre411_open_dispatch>", "exec"), _ns)      # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    exec(compile(reverted_sd, "<round411_pre411_sweep_dispatches>", "exec"), _ns)   # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_sweep_dispatches = _ns["sweep_dispatches"]

    cid3, cid4, proxy2, raised2 = _run_scenario(connA, "R411B", fail_at_call=3,
                                                 sweep_fn=old_sweep_dispatches)
    chk(proxy2.failed_once,
        "  되돌린 코드에서도 의도한 3번째 commit이 실제로 실패했다(같은 전제조건)")
    chk(raised2 is not None and "transaction" in str(raised2).lower(),
        "★★★★★ 옛 코드(재구성, 실제 파일은 안 건드림)로 되돌리면 같은 조건에서 실제로 "
        "예외가 밖으로 샌다(인과관계 직접증명 — 커밋 안 된 쓰기가 커넥션에 남아 대상2의 "
        "BEGIN IMMEDIATE 를 깨뜨림)",
        f"{type(raised2).__name__}: {raised2}" if raised2 else "예외 없음")

    print("\n[4] 실행 — api_co_offer 동점처리(직접 SQL 대조 — 라우트는 회귀에 걸리는")
    print("     사전조건(추가경매중 change_order 등)이 많아 조회 로직만 정밀 검증)")
    cid_co = connA.execute(
        "INSERT INTO cases(case_no,insurer_id,insurer,category,region,address,"
        "                  est_price,low_price,status,is_demo,created_at) "
        "VALUES('R411-CO',?,?,?,?,?,0,0,'시공중',0,?)",
        (iid, "검증보험", "가드레일·방호울타리", "서울", "서울", DB.now())).lastrowid
    aid = connA.execute(
        "INSERT INTO auctions(case_id,kind,status,created_at) "
        "VALUES(?,'추가분','마감',?)", (cid_co, DB.now())).lastrowid
    pid_a = connA.execute(
        "INSERT INTO partners(name,status) VALUES('R411동점A','활성')").lastrowid
    pid_b = connA.execute(
        "INSERT INTO partners(name,status) VALUES('R411동점B','활성')").lastrowid
    #  일부러 "나중에 넣은(id 가 더 큰)" 쪽을 같은 금액으로 함께 넣는다 —
    #  ORDER BY amount 만으로는 어느 쪽이 이길지 보장이 없다.
    bid_b = connA.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,300000,5,?)", (aid, pid_b, "R411동점B", DB.now())).lastrowid
    bid_a = connA.execute(
        "INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at) "
        "VALUES(?,?,?,300000,5,?)", (aid, pid_a, "R411동점A", DB.now())).lastrowid
    connA.commit()
    chk(bid_a > bid_b,
        "  대조군 준비 — A가 나중에(더 큰 id로) 들어갔다(그런데도 A가 먼저 낸 "
        "쪽이 아니라 B가 먼저 낸 쪽이다, id 오름차순=먼저 낸 순)", (bid_a, bid_b))
    winner = connA.execute(
        "SELECT b.partner_id, b.partner_name FROM bids b "
        "JOIN partners p ON p.id = b.partner_id "
        "WHERE b.auction_id=? AND b.voided_at IS NULL AND COALESCE(p.status,'활성')='활성' "
        "ORDER BY b.amount ASC, b.id ASC LIMIT 1", (aid,)).fetchone()
    chk(winner["partner_id"] == pid_b,
        "★★★★★ 동점이면 먼저 낸 입찰(id가 작은 쪽, B)이 결정론적으로 이긴다"
        "(고치기 전엔 ORDER BY amount 만이라 어느 쪽이 나올지 보장이 없었다)",
        dict(winner))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")
finally:
    #  [라운드612] 실제 dispatch.py를 이제 전혀 안 쓰므로(위 [3]을 exec 재구성으로
    #  이관) 디스크 복원문·importlib.reload 모두 더 이상 필요 없다.
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    os.environ.pop("BOKGUON_SQLITE_BUSY_MS", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
