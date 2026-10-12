# -*- coding: utf-8 -*-
"""현장 출동 수배 검증.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

이 기능의 가장 위험한 실패는 **두 업체가 동시에 수락해 둘 다 출동하는 것**(헛걸음)과
**한 업체가 맡고 안 갔는데 사건이 영원히 멈추는 것**이다. 그 둘을 최우선으로 검사한다.
"""
import io
import sys
import time
import threading
import secrets

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import db as DB
import dispatch as DP

OK = FAIL = 0
MARK = "DSP" + secrets.token_hex(3)


def chk(cond, label, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}   {detail}")


def cleanup(conn):
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM cases WHERE case_no LIKE ?", (MARK + "%",))]
    for cid in ids:
        conn.execute("DELETE FROM dispatch_calls WHERE dispatch_id IN "
                     "(SELECT id FROM dispatches WHERE case_id=?)", (cid,))
        conn.execute("DELETE FROM dispatches WHERE case_id=?", (cid,))
        conn.execute("DELETE FROM field_agreements WHERE case_id=?", (cid,))
        conn.execute("DELETE FROM cases WHERE id=?", (cid,))
    conn.execute("DELETE FROM partners WHERE name LIKE ?", (MARK + "%",))
    conn.commit()


def mkcase(conn, cat="가드레일·방호울타리", region="서울 송파구"):
    #  ⚠ [라운드172] is_demo=0 이어야 한다 — 이 파일은 출동 **기계학**(동시성·
    #    상태전이·알림집계)을 검사하지, 데모 격리를 검사하지 않는다. dispatches
    #    는 open_dispatch() 에서 cases.is_demo 를 그대로 물려받는데, 여기를 1로
    #    두면 172라운드에서 새로 막은 claim/decline/arrive/close_no_repair 의
    #    데모 차단에 이 테스트 자신의 정상 호출까지 걸린다.
    iid = conn.execute("SELECT id FROM insurers LIMIT 1").fetchone()["id"]
    cur = conn.execute(
        """INSERT INTO cases(case_no,insurer_id,insurer,category,region,address,
                             est_price,low_price,status,intake_type,created_at,is_demo)
           VALUES(?,?,?,?,?,?,0,0,'접수','사진없음',?,0)""",
        (f"{MARK}-{secrets.token_hex(2)}", iid, "검증보험", cat, region,
         "검증용 주소", DB.now()))
    conn.commit()
    return cur.lastrowid


def main():
    conn = DB.get_db()
    cleanup(conn)
    print("=" * 70)
    print("  현장 출동 수배 검증")
    print("=" * 70)

    # ── 1. 수배 개시 ──────────────────────────────────────────
    print("\n[1] 수배 개시 — 인근 업체 동시 알림")
    cid = mkcase(conn)
    did, cnt, _ = DP.open_dispatch(conn, cid)
    chk(did and cnt > 0, f"수배가 열리고 {cnt}개사에 알림", f"did={did} cnt={cnt}")
    v = DP.dispatch_view(conn, did)
    chk(v["status"] == DP.ST_OPEN, "상태가 '모집중'", v["status"])
    chk(len(v["calls"]) == cnt, "부른 업체 수와 기록이 일치", f"{len(v['calls'])}/{cnt}")
    st = conn.execute("SELECT dispatch_status FROM cases WHERE id=?", (cid,)).fetchone()[0]
    chk(st == DP.CS_SEEKING, "사건이 '수배중'", st)

    # 중복 개시 방지
    did2, cnt2, _ = DP.open_dispatch(conn, cid)
    chk(did2 == did and cnt2 == 0, "★ 살아있는 수배가 있으면 새로 열지 않음(중복 출동 방지)")

    # ── 1-b. ★ 알림이 한 건도 안 나갔을 때 그 사실이 남는가 ────────────
    #   예전에는 콜백 예외를 삼중으로 삼켜, 협력사에 콜이 0건 나갔는데도
    #   감사로그엔 "N개사 동시 알림", 화면엔 called=N 이 찍혔다.
    #   아무도 안 오는데 운영자는 수배가 열린 줄 알고 기다린다 → 사건이 조용히 멈춘다.
    print("\n[1-b] 알림 전멸이 감지되는가")
    cid_n = mkcase(conn)
    boom = lambda pid, did_, cid_: (_ for _ in ()).throw(RuntimeError("발송 장애 재현"))
    d_n, c_n, s_n = DP.open_dispatch(conn, cid_n, notify=boom)
    chk(c_n > 0 and s_n == 0, "★ 전부 실패하면 sent=0 으로 보고", f"called={c_n} sent={s_n}")
    #  ⚠ [라운드95] detail 은 이제 case_id(숫자 PK)가 아니라 case_no 문자열을
    #    쓴다 — 사건 이력 리포트·정산 상세가 case_no 로 LIKE 검색하기 때문이다
    #    (95라운드에서 dispatch.py 전체를 이 형식으로 통일했다). 이 테스트가
    #    옛 형식("사건 {id}")을 그대로 검색해, 고쳐진 뒤에도 여전히 통과하던
    #    옛 결함을 "정상"으로 오판하고 있었다 — case_no 로 맞춘다.
    case_no_n = conn.execute("SELECT case_no FROM cases WHERE id=?", (cid_n,)).fetchone()[0]
    lg = conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE action='출동수배 알림 실패' "
        "  AND detail LIKE ?", (f"%{case_no_n}%",)).fetchone()[0]
    chk(lg == 1, "★ 알림 실패가 감사로그에 남음(예전엔 로그조차 없었다)", f"{lg}건")
    n_sent = conn.execute(
        "SELECT COUNT(*) FROM notifications WHERE ntype='출동수배' AND case_id=?",
        (cid_n,)).fetchone()[0]
    chk(n_sent == 0, "실패했으니 알림 행도 0건", f"{n_sent}건")

    # 일부만 실패해도 숫자가 맞는가 — '불렀다'와 '닿았다'는 다른 값이다
    cid_p = mkcase(conn)
    seen = []

    def half(pid, did_, cid_):
        seen.append(pid)
        if len(seen) % 2 == 0:
            raise RuntimeError("절반 실패 재현")
    d_p, c_p, s_p = DP.open_dispatch(conn, cid_p, notify=half)
    chk(c_p > 0 and s_p == c_p - (c_p // 2),
        "★ 부분 실패 시 sent 가 실제 성공 수와 일치", f"called={c_p} sent={s_p}")

    # ── 2. ★ 선착순 동시성 — 가장 중요 ────────────────────────
    print("\n[2] ★ 선착순 — 동시에 눌러도 한 곳만 성공하는가")
    calls = v["calls"]
    if len(calls) < 2:
        print("  [건너뜀] 후보 업체가 2곳 미만")
    else:
        winners, errors = [], []
        barrier = threading.Barrier(min(5, len(calls)))

        def race(pid, pname):
            c = DB.get_db()
            try:
                barrier.wait(timeout=5)
                ok, msg, due = DP.claim(c, did, pid, pname)
                if ok:
                    winners.append(pid)
            except Exception as ex:
                errors.append(repr(ex))
            finally:
                c.close()

        ths = [threading.Thread(target=race, args=(c["partner_id"], c["partner_name"]))
               for c in calls[:5]]
        for t in ths:
            t.start()
        for t in ths:
            t.join(timeout=15)

        chk(len(winners) == 1,
            f"★ 동시 {len(ths)}곳이 수락해도 정확히 1곳만 성공", f"성공 {len(winners)}건")
        chk(not errors, "  경합 중 예외 없음", errors[:2])
        d = conn.execute("SELECT status, claimed_partner_id, due_at FROM dispatches WHERE id=?",
                         (did,)).fetchone()
        chk(d["status"] == DP.ST_CLAIMED, "상태가 '수배됨'", d["status"])
        chk(d["claimed_partner_id"] == winners[0] if winners else False,
            "잡은 업체가 기록됨")
        chk(bool(d["due_at"]), "도착 기한이 설정됨", d["due_at"])
        # 나머지는 '마감'
        left = conn.execute(
            "SELECT COUNT(*) FROM dispatch_calls WHERE dispatch_id=? AND response IS NULL",
            (did,)).fetchone()[0]
        chk(left == 0, "나머지 업체 알림이 모두 '마감'으로 닫힘", f"미응답 {left}건")

    # 대상이 아닌 업체는 못 잡는다
    outsider = conn.execute(
        """SELECT id, name FROM partners WHERE status='활성'
            AND id NOT IN (SELECT partner_id FROM dispatch_calls WHERE dispatch_id=?)
            LIMIT 1""", (did,)).fetchone()
    if outsider:
        ok, msg, _ = DP.claim(conn, did, outsider["id"], outsider["name"])
        chk(not ok, "★ 알림을 안 받은 업체는 가로챌 수 없음", msg)

    # ── 3. 도착 보고 ──────────────────────────────────────────
    print("\n[3] 도착 보고 — 사진이 있어야 인정")
    d = conn.execute("SELECT claimed_partner_id FROM dispatches WHERE id=?", (did,)).fetchone()
    pid = d["claimed_partner_id"]
    if pid:
        ok, msg = DP.arrive(conn, did, pid, photo_count=0)
        chk(not ok, "★ 사진 0장이면 도착으로 인정 안 함", msg)
        ok, msg = DP.arrive(conn, did, pid, photo_count=3, field_estimate=850000)
        chk(ok, "사진 3장 + 실견적으로 도착 처리", msg)
        row = conn.execute(
            "SELECT status, photo_count, field_estimate, arrived_at FROM dispatches WHERE id=?",
            (did,)).fetchone()
        chk(row["status"] == DP.ST_ARRIVED, "상태가 '도착'", row["status"])
        chk(row["photo_count"] == 3 and row["field_estimate"] == 850000, "사진 수·실견적 저장")
        cs = conn.execute(
            "SELECT dispatch_status, first_partner_id, first_photo_at FROM cases WHERE id=?",
            (cid,)).fetchone()
        chk(cs["dispatch_status"] == DP.CS_PHOTO, "사건이 '사진확보'", cs["dispatch_status"])
        chk(cs["first_partner_id"] == pid, "★ 최초 출동업체가 사건에 기록됨(경매 우선권 근거)")
        chk(bool(cs["first_photo_at"]), "최초 사진 시각 기록")
        # 이미 도착한 건은 다시 도착 처리되지 않는다
        ok, msg = DP.arrive(conn, did, pid, photo_count=2)
        chk(not ok, "이미 도착한 수배는 재처리 안 됨", msg)

    # ── 4. ★ 제한시간 초과 → 재수배 ───────────────────────────
    print("\n[4] ★ 30분 내 미도착 → 자동 실패 + 다음 회차 재수배")
    cid2 = mkcase(conn)
    did3, cnt3, _ = DP.open_dispatch(conn, cid2)
    v3 = DP.dispatch_view(conn, did3)
    if v3["calls"]:
        p = v3["calls"][0]
        ok, _, _ = DP.claim(conn, did3, p["partner_id"], p["partner_name"])
        chk(ok, "한 업체가 출동을 맡음")
        # 기한을 과거로 돌린다(시간을 기다리지 않고 재현)
        conn.execute("UPDATE dispatches SET due_at=datetime('now','+9 hours','-1 minutes') "
                     "WHERE id=?", (did3,))
        conn.commit()
        before = conn.execute("SELECT COUNT(*) FROM dispatches WHERE case_id=?", (cid2,)).fetchone()[0]
        r = DP.sweep_dispatches(conn, force=True)
        chk(r["expired"] >= 1, "★ 기한 지난 수배가 실패 처리됨", r)
        st3 = conn.execute("SELECT status, fail_reason FROM dispatches WHERE id=?",
                           (did3,)).fetchone()
        chk(st3["status"] == DP.ST_FAILED, "상태가 '실패'", st3["status"])
        after = conn.execute("SELECT COUNT(*) FROM dispatches WHERE case_id=?", (cid2,)).fetchone()[0]
        chk(after > before, "★ 다음 회차 수배가 자동으로 열림(사건이 멈추지 않음)",
            f"{before}→{after}")
        # 같은 업체를 다시 부르지 않는다
        newd = conn.execute(
            "SELECT id FROM dispatches WHERE case_id=? ORDER BY id DESC LIMIT 1", (cid2,)).fetchone()[0]
        again = conn.execute(
            "SELECT COUNT(*) FROM dispatch_calls WHERE dispatch_id=? AND partner_id=?",
            (newd, p["partner_id"])).fetchone()[0]
        chk(again == 0, "★ 직전에 안 간 업체는 다시 부르지 않음")

    # ── 5. 생존 신호 ──────────────────────────────────────────
    print("\n[5] 점검 생존 신호")
    conn.execute("UPDATE job_locks SET last_run_at=NULL WHERE name='dispatch_sweep'")
    conn.execute("UPDATE dispatches SET due_at=datetime('now','+9 hours','+48 hours') "
                 "WHERE status=?", (DP.ST_CLAIMED,))
    conn.commit()
    DP.sweep_dispatches(conn, force=True)
    last = conn.execute(
        "SELECT last_run_at FROM job_locks WHERE name='dispatch_sweep'").fetchone()[0]
    chk(bool(last), "★ 대상 0건이어도 last_run_at 갱신(배지가 상시 빨강이 되지 않게)", last)

    # ── 6. 후보 선정 ──────────────────────────────────────────
    print("\n[6] 인근 업체 후보 선정")
    cid3 = mkcase(conn, cat="유리·샷시·자동문", region="부산 해운대구")
    cands = DP.candidates(conn, cid3, limit=10)
    chk(isinstance(cands, list), "후보 목록을 반환")
    if cands:
        chk(all("why" in c and c["why"] for c in cands), "각 후보에 선정 이유가 붙음")
        chk(len({c["id"] for c in cands}) == len(cands), "후보에 중복 없음")
    chk(DP._region_key("서울특별시 송파구", "") == "송파", "지역 열쇠 추출(송파)",
        DP._region_key("서울특별시 송파구", ""))
    chk(DP._region_key("", "경기도 성남시 분당구") in ("성남", "분당"), "주소로도 지역 추출",
        DP._region_key("", "경기도 성남시 분당구"))

    # ── 6.5 1차 합의 → 성사 / 결렬 ────────────────────────────
    print("\n[6.5] 1차 합의")
    # 합의 성사 경로
    cid4 = mkcase(conn)
    d4, n4, _ = DP.open_dispatch(conn, cid4)
    v4 = DP.dispatch_view(conn, d4)
    if v4["calls"]:
        p4 = v4["calls"][0]
        DP.claim(conn, d4, p4["partner_id"], p4["partner_name"])
        DP.arrive(conn, d4, p4["partner_id"], photo_count=4, field_estimate=920000)
        aid = DP.open_agreement(conn, cid4, engine_low=850000, engine_high=1050000,
                                our_staff="검증담당", insurer_staff="보상담당")
        chk(bool(aid), "합의 검토가 열림", aid)
        a = DP.agreement_view(conn, cid4)
        chk(a["field_amount"] == 920000, "출동 업체 실견적이 기록됨", a["field_amount"])
        chk(a["engine_low"] == 850000 and a["engine_high"] == 1050000,
            "표준단가 개산 구간이 근거로 함께 남음")
        chk(a["engine_basis"] is None and a["engine_at"] is None,
            "근거를 안 넘기면 '근거 없음'으로 남는다(빈 값 위장 안 함)")
        chk(a["status"] == DP.AG_REVIEW, "상태가 '검토중'(보험사 승인 대기)", a["status"])

        # ★ 법률 철칙 — 운영자 단독으로는 확정할 수 없다
        ok, msg = DP.settle_agreement(conn, aid, agreed=True, amount=900000,
                                      note="운영자 단독 시도", actor="검증담당")
        chk(not ok, "★★ 운영자 단독 승인 차단(금액을 정하는 주체는 보험사)", msg[:46])
        a = DP.agreement_view(conn, cid4)
        chk(a["status"] == DP.AG_REVIEW, "  차단 후에도 상태는 '검토중' 유지", a["status"])

        # 보험사 계정 승인 — 금액은 실견적으로 고정된다(요청 금액은 무시)
        approver = {"org_id": 1, "user_id": None, "name": "보상팀장", "role": "중간관리자"}
        ok, msg = DP.settle_agreement(conn, aid, agreed=True, amount=1, note="승인",
                                      actor="보상팀장", approver=approver)
        chk(ok, "★ 보험사 계정 승인으로 확정", msg)
        a = DP.agreement_view(conn, cid4)
        chk(a["status"] == DP.AG_DONE, "상태가 '합의'", a["status"])
        chk(a["agreed_amount"] == 920000,
            "★★ 금액은 실견적 고정 — 요청값(1원) 무시", a["agreed_amount"])
        chk(a["approver_name"] == "보상팀장" and a["approver_org_id"] == 1,
            "★ 승인자 계정이 기록됨(자유입력 아님)", f"{a['approver_name']}/{a['approver_role']}")
        chk(bool(a["approved_at"]), "승인 시각 기록", a["approved_at"])
        cs4 = conn.execute(
            "SELECT status, partner_id, award_amount, award_route FROM cases WHERE id=?",
            (cid4,)).fetchone()
        chk(cs4["award_route"] == "1차합의", "★ 사건이 '1차합의' 경로로 표시(경매 건과 통계 분리)",
            cs4["award_route"])
        chk(cs4["status"] == "시공중" and cs4["partner_id"] == p4["partner_id"]
            and cs4["award_amount"] == 920000,
            "★★ 승인이 사건 배정까지 닫는다(예전엔 업체·금액·상태가 빈칸)",
            f"{cs4['status']} · 업체 {cs4['partner_id']} · {cs4['award_amount']:,}원")
        # 중복 처리 방지
        ok, msg = DP.settle_agreement(conn, aid, agreed=False, note="재시도")
        chk(not ok, "★ 이미 처리된 합의는 재처리 안 됨", msg)

    # 결렬 경로 — 사진은 남아 2차 경매 근거가 된다
    cid5 = mkcase(conn)
    d5, n5, _ = DP.open_dispatch(conn, cid5)
    v5 = DP.dispatch_view(conn, d5)
    if v5["calls"]:
        p5 = v5["calls"][0]
        DP.claim(conn, d5, p5["partner_id"], p5["partner_name"])
        DP.arrive(conn, d5, p5["partner_id"], photo_count=5, field_estimate=1800000)
        aid5 = DP.open_agreement(conn, cid5, engine_low=800000, engine_high=1000000)
        ok, msg = DP.settle_agreement(conn, aid5, agreed=False, note="표준 대비 과다", actor="검증담당")
        chk(ok, "결렬 처리", msg)
        chk("경매" in msg, "  결렬 안내에 2차 경매가 언급됨", msg)
        route5 = conn.execute("SELECT award_route FROM cases WHERE id=?", (cid5,)).fetchone()[0]
        chk(route5 == "경매", "사건이 '경매' 경로로 전환", route5)
        cs5 = conn.execute(
            "SELECT first_partner_id, dispatch_status FROM cases WHERE id=?", (cid5,)).fetchone()
        chk(cs5["first_partner_id"] == p5["partner_id"] and cs5["dispatch_status"] == DP.CS_PHOTO,
            "★ 결렬돼도 최초 사진·출동업체 기록은 남음(2차 경매의 근거)")

    # ── 6.6b 개산 근거 스냅샷 — 단가가 개정돼도 그때 기준으로 재현 가능해야 한다
    print("\n[6.6b] 개산 근거 스냅샷 저장")
    import json as _json
    import repair_estimate as _RE
    cid5b = mkcase(conn)
    d5b, _, _ = DP.open_dispatch(conn, cid5b)
    v5b = DP.dispatch_view(conn, d5b)
    if v5b["calls"]:
        p5b = v5b["calls"][0]
        DP.claim(conn, d5b, p5b["partner_id"], p5b["partner_name"])
        DP.arrive(conn, d5b, p5b["partner_id"], photo_count=3, field_estimate=1200000)
        _in = {"L": 8, "s": 2}
        r = _RE.estimate("guardrail_section", _in)
        aidb = DP.open_agreement(
            conn, cid5b, engine_low=r["range_low"], engine_high=r["range_high"],
            basis={"pattern": "guardrail_section",
                   "inputs": _json.dumps(_in, ensure_ascii=False),
                   "basis": _json.dumps(r, ensure_ascii=False),
                   "ver": r.get("engine_ver")})
        ab = DP.agreement_view(conn, cid5b)
        chk(ab["engine_pattern"] == "guardrail_section", "수선패턴이 기록됨", ab["engine_pattern"])
        chk(ab["engine_ver"] == _RE.ENGINE_VER, "엔진 버전이 기록됨", ab["engine_ver"])
        chk(bool(ab["engine_at"]), "계산 시각이 기록됨", ab["engine_at"])
        snap = _json.loads(ab["engine_basis"] or "{}")
        chk(snap.get("direct_cost", 0) > 0, "직접공사비가 스냅샷에 남음", snap.get("direct_cost"))
        chk(len(snap.get("lines") or []) > 0, "★ 단가 내역(줄별)까지 남아 재현 가능",
            f"{len(snap.get('lines') or [])}줄")
        chk(_json.loads(ab["engine_inputs"] or "{}").get("L") == 8, "입력값이 남음")

    # ── 6.7 ★ 미수선 종결 ─────────────────────────────────────
    print("\n[6.7] ★ 미수선 종결 — 현장에서 공사 없이 끝나는 경우")
    cid6 = mkcase(conn)
    d6, n6, _ = DP.open_dispatch(conn, cid6)
    v6 = DP.dispatch_view(conn, d6)
    if v6["calls"]:
        p6 = v6["calls"][0]
        DP.claim(conn, d6, p6["partner_id"], p6["partner_name"])
        # 목록에 없는 사유는 거절
        ok, msg = DP.close_no_repair(conn, d6, p6["partner_id"], reason="그냥")
        chk(not ok, "★ 목록에 없는 사유는 거절(제각각 기재 방지)", msg)
        # '기타'는 설명 필수
        ok, msg = DP.close_no_repair(conn, d6, p6["partner_id"], reason="기타", note="")
        chk(not ok, "★ '기타'는 현장 설명 없으면 거절", msg)
        # 정상 종결
        ok, msg = DP.close_no_repair(conn, d6, p6["partner_id"],
                                     reason="피해자가 수선을 원치 않음",
                                     note="피해자가 직접 처리하겠다고 함", by="현장김")
        chk(ok, "미수선 종결 처리", msg)
        row = conn.execute(
            """SELECT status, outcome, no_repair_reason, no_repair_note, no_repair_by,
                      no_repair_at, arrived_at FROM dispatches WHERE id=?""", (d6,)).fetchone()
        chk(row["outcome"] == DP.OUT_NO_REPAIR, "결과가 '미수선종결'", row["outcome"])
        chk(row["no_repair_reason"] == "피해자가 수선을 원치 않음", "사유 저장")
        chk(row["no_repair_by"] == "현장김", "확인한 사람 저장", row["no_repair_by"])
        chk(bool(row["no_repair_at"]) and bool(row["arrived_at"]), "시각 기록(도착시각도 채움)")
        cs6 = conn.execute(
            "SELECT status, no_repair_reason, award_route FROM cases WHERE id=?", (cid6,)).fetchone()
        chk(cs6["status"] == "미수선종결", "★ 사건이 '미수선종결'로 (경매 안 열림)", cs6["status"])
        chk(cs6["award_route"] == "미수선", "  경로가 '미수선'(경매·1차합의와 통계 분리)")
        chk(cs6["no_repair_reason"] == "피해자가 수선을 원치 않음", "  사건에도 사유가 보임")
        # 남이 종결할 수 없다
        other = conn.execute(
            "SELECT id FROM partners WHERE status='활성' AND id<>? LIMIT 1",
            (p6["partner_id"],)).fetchone()
        if other:
            ok, msg = DP.close_no_repair(conn, d6, other["id"], reason="파손이 경미해 수선 불필요")
            chk(not ok, "★ 출동을 맡지 않은 업체는 종결 불가", msg)
        chk(len(DP.NO_REPAIR_REASONS) >= 5, "사유 목록이 제공됨", len(DP.NO_REPAIR_REASONS))

    # 정상 도착 건은 '수선진행'으로 표시된다
    if pid:
        o = conn.execute("SELECT outcome FROM dispatches WHERE id=?", (did,)).fetchone()[0]
        chk(o == DP.OUT_REPAIR, "정상 도착 건은 '수선진행'으로 구분", o)

    # ── 6-2. 응답할 수 있는 곳을 먼저 부르는가 ─────────────────
    #  30분 선착순이다. 문자도 앱도 안 닿는 업체가 '가깝다'는 이유로 앞자리를
    #  차지하면 그 시간이 그냥 흘러간다(실데이터에서 활성 399곳 중 계정 1곳뿐이었다).
    #  ⚠ 빼는 것이 아니라 **뒤로 미는 것**이다 — 부를 곳이 없으면 그들도 부른다.
    print("\n[6-2] 응답 가능한 곳 우선 호출")
    conn.execute("INSERT INTO partners(name,partner_type,major,region,address,status,"
                 " lat,lng,geo_src,phone) VALUES(?,'시행사','가드레일·방호울타리',"
                 " '서울 송파구','서울 송파구 올림픽로 300','활성',37.5137,127.1043,"
                 " '주소검색','02-000-0000')", (MARK + "가까움_못받음",))
    conn.execute("INSERT INTO partners(name,partner_type,major,region,address,status,"
                 " lat,lng,geo_src,phone) VALUES(?,'시행사','가드레일·방호울타리',"
                 " '서울 강남구','서울 강남구','활성',37.5172,127.0473,"
                 " '주소검색','010-1234-5678')", (MARK + "멀지만_받음",))
    conn.commit()
    cid2 = mkcase(conn)
    mine = [x for x in DP.candidates(conn, cid2, limit=40)
            if (x["name"] or "").startswith(MARK)]
    chk(len(mine) == 2, "검사용 업체 2곳이 후보에 들어옴", len(mine))
    if len(mine) == 2:
        chk(mine[0]["reachable"] and not mine[1]["reachable"],
            "★★ 가까워도 못 받는 곳보다, 멀어도 받을 수 있는 곳을 먼저 부른다",
            [(x["name"][-6:], round(x["dist_km"] or -1, 1), x["reachable"]) for x in mine])
        chk(mine[0]["dist_km"] > mine[1]["dist_km"],
            "★ 그 판단이 거리보다 우선한다(순위·거리 순서는 그대로 보존)",
            f"{mine[0]['dist_km']:.1f} vs {mine[1]['dist_km']:.1f}")

    # ── 7. 설정값 경계 ────────────────────────────────────────
    print("\n[7] 설정값")
    chk(5 <= DP.dispatch_minutes(conn) <= 240, "제한시간이 범위 안", DP.dispatch_minutes(conn))
    chk(DP.dispatch_max_round(conn) >= 1, "최대 회차 ≥ 1", DP.dispatch_max_round(conn))

    #  ── 복합 공종 사건도 수배 대상이 잡히는가 ──────────────────
    #   ⚠ 복합 사건의 `cases.category` 는 '복합(A · B)' 라는 **표시용 문자열**이라
    #     `major LIKE %복합(…)%` 로는 **아무도 안 걸린다**. 실측으로 운영에서
    #     수배 대상 0곳이었다(쪼개면 72곳). 공고는 열리는데 아무도 안 불린다.
    #   ⚠ 문자열을 구분자로 쪼개지 않는다 — ' · ' 가 공종 이름 안의 '·' 와
    #     헷갈린다(유리·샷시·자동문). 실제 공종은 work_lots 에 행으로 있다.
    import io as _io
    import os as _os
    _src = _io.open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "app.py"),
                    encoding="utf-8").read()
    _i = _src.find("def case_trades")
    _j = _src.find("PARTNER_ID_RESERVED = (")
    chk(_i > 0 and _j > _i, "★ case_trades() 가 있다")
    _ns = {"rows": lambda cur: [dict(r) for r in cur]}
    exec(compile(_src[_i:_j], "<ct>", "exec"), _ns)          # noqa: S102 — 우리 소스다
    _ct = _ns["case_trades"]

    _cid = conn.execute(
        "INSERT INTO cases (case_no,category,region,status,is_demo,created_at) "
        " VALUES ('DPCOMP','복합(유리·샷시·자동문 · 지붕·판넬·캐노피)','서울','공고중',1,"
        "         datetime('now','+9 hours'))").lastrowid
    for _t in ("유리·샷시·자동문", "지붕·판넬·캐노피"):
        conn.execute("INSERT INTO work_lots (case_id, category) VALUES (?,?)", (_cid, _t))
    conn.commit()
    _got = _ct(conn, _cid, "복합(유리·샷시·자동문 · 지붕·판넬·캐노피)")
    chk(_got == ["유리·샷시·자동문", "지붕·판넬·캐노피"],
        "★★ 복합 사건은 work_lots 의 공종 목록을 준다", _got)

    _cid2 = conn.execute(
        "INSERT INTO cases (case_no,category,region,status,is_demo,created_at) "
        " VALUES ('DPONE','가드레일·방호울타리','서울','공고중',1,"
        "         datetime('now','+9 hours'))").lastrowid
    conn.commit()
    chk(_ct(conn, _cid2, "가드레일·방호울타리") == ["가드레일·방호울타리"],
        "★ 단일 공종 사건은 그대로 한 개")
    chk(_ct(conn, _cid2, "복합(가나 · 다라)") == [],
        "★★ work_lots 가 없는 복합은 **빈 목록**을 준다",
        "슬쩍 '전체' 로 넘어가면 엉뚱한 공종 업체까지 불려 나온다")

    #  라우트가 그 함수를 쓰는가 — 문자열 그대로 LIKE 하던 옛 코드가 남으면 안 된다
    chk("case_trades(conn, cid, cat)" in _src, "★ 수배 대상 선정이 그 함수를 쓴다")
    chk('params += [f"%{cat}%", f"%{cat}%"]' not in _src,
        "★★ 옛 코드(표시용 문자열로 LIKE)가 남아 있지 않다")

    #  ── dispatch.py 의 실제 자동 수배 경로도 같은 방식을 쓰는가 ──────────
    #    ⚠⚠ 바로 위 case_trades() 는 app.py 안의 함수고, 위 검사는 app.py 의
    #      *다른* 라우트(업체 직접검색)가 그걸 쓰는지만 봤다. **실제 자동 출동
    #      수배는 이 파일(dispatch.py)의 candidates() 를 통해 실행되는데, 그
    #      경로는 case_trades 도 work_lots 도 전혀 참조하지 않았다** —
    #      실측(2026-08-19): 복합 사건의 자동 수배 후보가 **0곳**이었다
    #      (work_lots 로 쪼개면 72곳). 공고는 열리는데 아무도 안 불린다.
    #      여기서는 app.py 가 아니라 **dispatch.py 를 직접 실행**해 확인한다.
    _dp_src = _io.open(
        _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "dispatch.py"),
        encoding="utf-8").read()
    chk("work_lots" in _dp_src, "★★ dispatch.py 자체가 work_lots 를 참조한다(자동 수배 경로)")
    chk(hasattr(DP, "_case_trades"), "★ dispatch.py 에 자체 공종 목록 함수가 있다")

    #  ⚠ [329라운드] 전화·계정이 둘 다 없으면(도달불가) candidates() 가 더 넓은
    #    순위까지 정당하게 더 찾아보게 되면서(reachable 기준으로 확장 여부를
    #    판단하도록 고쳐짐), 오래 누적된 verify.db 의 다른 도달가능 후보들에
    #    밀려 상위 limit 안에 안 들 수 있다 — 이 검사의 취지(공종 분리 매칭
    #    자체가 되는가)와 무관한 우연한 실패라 실제로 연락 가능하게 만든다.
    conn.execute(
        "INSERT INTO partners (name, partner_type, major, category, region, phone, status) "
        " VALUES (?,'시공사','유리·샷시·자동문','유리·샷시·자동문','서울','010-9000-0000','활성')",
        (f"{MARK}-복합업체",))
    conn.commit()
    _cands = DP.candidates(conn, _cid, limit=10)
    chk(any(x["name"] == f"{MARK}-복합업체" for x in _cands),
        "★★★ dispatch.py 의 실제 자동 수배가 복합 사건 후보를 잡는다",
        f"후보 {[x['name'] for x in _cands][:5]}")

    conn.execute("DELETE FROM work_lots WHERE case_id=?", (_cid,))
    conn.execute("DELETE FROM cases WHERE id IN (?,?)", (_cid, _cid2))
    conn.commit()

    cleanup(conn)
    conn.close()
    print("-" * 70)
    print(f"  통과 {OK} · 실패 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
