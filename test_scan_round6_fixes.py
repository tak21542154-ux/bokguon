# -*- coding: utf-8 -*-
"""6라운드 스캔 확정 결함 16건의 회귀 검사.

  이 라운드가 본 것 — 약속 vs 코드 · 감사추적 · 되돌린 뒤 잔재 · 3자 시야 · 멱등 · 경계값.

  ⚠ 여기서 잡은 것 중 **가장 위험했던 것**은 코드가 아니라 배포였다.
     AWS 배포 스크립트에 `manage.py sweep` 크론이 없어, 서버를 올려도
     경매 마감·출동 기한·완료보고 독촉·문자 실발송이 통째로 죽은 채 돈다.
     테스트는 전부 통과하는데 현장만 멈춘다 — 그래서 배포 파일까지 검사한다.

  서버가 필요 없다(로그인을 하지 않으므로 레이트리밋과 무관).
"""
import io
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OK = FAIL = 0


def chk(cond, name, got=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}   {got}")


def src(*parts):
    return io.open(os.path.join(HERE, *parts), encoding="utf-8").read()


def _fn_body(source, fn_name):
    start = source.index(f"\ndef {fn_name}(")
    end = source.find("\ndef ", start + 1)
    return source[start:end if end != -1 else None]


def main():
    app_s = src("app.py")
    dsp_s = src("dispatch.py")
    mng_s = src("manage.py")
    cmp_s = src("compliance.py")

    print("[1] 약속 vs 코드 — 배포에 예약 실행이 실제로 걸리는가")
    boot = src("deploy", "bootstrap.sh")
    chk("manage.py sweep" in boot,
        "★ AWS 크론에 예약 실행(sweep)이 있다 — 없으면 마감·출동기한·실발송이 전부 죽는다")
    chk("prune-personal" in boot,
        "★ AWS 크론에 개인정보 파기가 있다 — 처리방침에 공개적으로 약속한 것")
    chk("cli_sweep" in mng_s and "'cli_sweep','auction_sweep'" in mng_s,
        "★ 점검이 cli_sweep 을 본다 (auction_sweep 은 대시보드만 열어도 갱신돼 거짓 초록)")
    chk("prune-personal" in src("deploy", "DEPLOY.md"),
        "운영 명령 목록에 개인정보 파기가 적혀 있다(운영자가 존재를 알 수 있게)")

    print("\n[2] 약속 vs 코드 — 무등록 업체 배제가 실제로 판정에 쓰이는가")
    chk(dsp_s.count("COALESCE(license_status,'미확인') <> '무등록'") == 3,
        "★ 출동 후보 3개 쿼리 모두 무등록을 뺀다",
        dsp_s.count("COALESCE(license_status,'미확인') <> '무등록'"))
    chk('"NO_LICENSE"' in app_s and 'license_status") or "미확인") == "무등록"' in app_s,
        "★ 입찰 라우트가 무등록 업체를 막는다(건산법 §25②)")
    chk("자동 재검증" not in src("templates", "landing.html"),
        "★ 랜딩에서 지킬 수 없는 약속('만료 시 자동 재검증')이 사라졌다 — 만료일 컬럼조차 없다")

    print("\n[3] 되돌린 뒤 잔재 — 사건 취소")
    chk("status IN ('모집중','수배됨')" in app_s and "발주처 사건 취소" in app_s,
        "★ 사건을 취소하면 진행 중인 출동수배도 닫는다")
    chk('"출동취소"' in app_s,
        "★ 이미 출발한 협력사에 취소를 통지한다(헛걸음 방지)")
    #  ⚠ `== 2` 로 못 박지 않는다 — 7라운드에서 직접 배정(assign_dispatch)에도 같은
    #    가드를 넣자 이 검사가 깨졌다. **가드가 늘어난 것을 실패로 읽으면 안 된다.**
    chk(dsp_s.count('cs[0] != "접수" or cs[1] is not None') >= 2,
        "★ 재수배(open_dispatch)·수락(claim)·직접배정(assign_dispatch)이 사건 상태를 본다",
        dsp_s.count('cs[0] != "접수" or cs[1] is not None'))
    chk("NOT IN ('취소','완료','미수선종결')" in app_s,
        "협력사 출동 목록에서 끝난 사건이 사라진다")

    print("\n[4] 되돌린 뒤 잔재 — 낙찰 취소")
    chk("voided_at=datetime" in app_s and "void_reason" in app_s,
        "★ 낙찰 취소가 그 회차 입찰을 무효 처리한다(지우지 않고 표시만 — 이력은 소명 자료)")
    chk(app_s.count("b.voided_at IS NULL") >= 8,
        "★ 낙찰 후보·성립 판정·최저가·목록이 모두 무효 입찰을 제외한다",
        app_s.count("b.voided_at IS NULL"))
    chk("UPDATE cases SET low_price=NULL WHERE id=?" in app_s,
        "★ 낙찰가가 덮어쓴 최저가를 되돌린다(보험사 전산에 취소된 값이 계속 나가지 않게)")
    chk("DELETE FROM est_outcome WHERE case_id=?" in app_s,
        "견적엔진 학습 표본에서 취소된 낙찰을 뺀다(case_id UNIQUE 라 재기록이 무시된다)")

    print("\n[5] 3자 시야 — 같은 사건이 화면마다 다른 말을 하지 않는가")
    chk(app_s.count("fa.field_amount FROM field_agreements") >= 2,
        "★ 절감 기준선이 개산→출동실견적→가견적 2단 폴백으로 통일됐다(목록 vs 상세 불일치)",
        app_s.count("fa.field_amount FROM field_agreements"))
    chk("max(0, est - award)" in app_s,
        "★ 월 정산 명세서에 음수 절감액이 찍히지 않는다")
    #  ⚠⚠ [라운드636] 이 문구 자체가 award_amount 를 곧이곧대로 믿는 자리였다 —
    #    NULL(운영 DB 실측: 사건#19)이면 승률·절감 집계에서 그 사건이 통째로
    #    빠진다. AWARD_CONFIRMED_SQL(award_amount→low_price 순으로 넘어가는
    #    NULLIF 사슬, CASE_AMOUNT_SQL 의 앞 두 단과 동일)로 교체됐다 — 검사
    #    문구도 그 교체를 따라간다(round364 가 이 두 함수를 다룰 때 이미 세운
    #    것과 같은 원칙: 공식이 정당하게 바뀌면 옛 검사 문구도 같이 갱신한다).
    chk(app_s.count("MAX(0, {SAVE_BASE_SQL}-{AWARD_CONFIRMED_SQL})") >= 2,
        "KPI 절감 합계·평균도 음수를 더하지 않는다",
        app_s.count("MAX(0, {SAVE_BASE_SQL}-{AWARD_CONFIRMED_SQL})"))
    chk('"완료보고지연": 2' in app_s and '"미수선종결": 4' in app_s,
        "★ 피해자 진행조회가 '완료보고지연'에서 1단계로 되돌아가지 않는다")
    chk("VICTIM_LABEL" in app_s,
        "피해자에게 내부 용어('완료보고지연')를 그대로 보이지 않는다")
    chk('"미수선종결": 100' in app_s,
        "종결된 사건의 진행율이 15% 로 떨어지지 않는다")
    chk(app_s.count("c.status='입찰중' AND COALESCE(c.is_demo,0)=0") == 3,
        "★ 데모 사건이 협력사 포털 공고에 뜨지 않는다",
        app_s.count("c.status='입찰중' AND COALESCE(c.is_demo,0)=0"))
    chk('int(c["is_demo"] or 0)' in app_s,
        "데모 사건에는 투찰 자체가 막힌다(목록에서 빼는 것만으로는 부족)")

    print("\n[6] 감사 추적 — 누가 했는지 남는가")
    chk("def portal_actor(" in app_s and app_s.count("DB.log(conn, portal_actor(") >= 15,
        "★ 포털 감사로그에 조직명뿐 아니라 담당자 계정이 남는다",
        app_s.count("DB.log(conn, portal_actor("))
    #  ⚠⚠ [라운드226] 예전엔 'session.get("insurer_login") or None' 이 한
    #    줄에 붙어 있어 그 문자열 그대로 찾았는데, 226라운드가 그 사이에
    #    API 키 채널(g.api_insurer) 폴백을 끼워 넣으면서 두 조각이 더는
    #    붙어있지 않다 — 의미(세션 보험사 계정이 접속기록에 반영된다)는
    #    그대로이므로 함수 경계 안에서 두 조각을 따로 확인한다(round210·213
    #    과 같은 종류의 콜라트럴 — 실제 회귀가 아니라 이 테스트만 구식이었다).
    sh_body = _fn_body(app_s, "_security_headers")
    chk('session.get("insurer_login")' in sh_body and "INSERT INTO access_log" in sh_body,
        "접속기록에 보험사 계정이 남는다(종전에는 아무 흔적도 없었다)")
    chk("before.get(k, '(없음)')" in app_s,
        "★ 설정 변경이 '무엇에서 무엇으로'를 남긴다(주석은 그렇게 적혀 있었는데 구현이 없었다)")
    chk('for f in ("cost_bearer", "severity", "resolution", "due_date")' in app_s,
        "하자 귀책 변경이 '정보수정' 한 단어로 끝나지 않는다(귀책은 돈의 방향을 정한다)")

    print("\n[7] 멱등 — 같은 요청을 두 번 보내면")
    chk("Idempotency-Key" in app_s and '"duplicate": True' in app_s,
        "★ 보험사 API 재시도가 사건·경매·정산을 2벌 만들지 않는다")
    chk("def sweep_webhook_retries(" in app_s and "sweep_webhook_retries(conn)" in mng_s,
        "실패한 보험사 웹훅이 재전송된다(종전에는 1회 시도 후 영영 끝)")

    print("\n[8] 경계값 — 0 을 '없음'으로 읽지 않는가")
    chk("NULLIF(award_amount,0), NULLIF(low_price,0)" in cmp_s,
        "★ 분할회피 합산이 확정가 우선이다 — est_price 만 더하면 사진없음 접수 묶음이 전부 0원")

    print("\n[9] 새 DB 에서 실제로 만들어지는가 (스키마)")
    tmp = tempfile.mkdtemp(prefix="bokguon_r6_")
    db = os.path.join(tmp, "r6.db")
    try:
        env = dict(os.environ)
        env.update({"BOKGUON_DB_PATH": db, "BOKGUON_ENV": "dev",
                    "BOKGUON_SEED_DEMO": "0", "PYTHONIOENCODING": "utf-8"})
        for cmd in (["init"], ["migrate"]):
            subprocess.run([sys.executable, "manage.py", *cmd], cwd=HERE, env=env,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        conn = sqlite3.connect(db)
        bcols = {r[1] for r in conn.execute("PRAGMA table_info(bids)")}
        chk({"voided_at", "void_reason"} <= bcols, "bids.voided_at/void_reason 이 생긴다",
            sorted(bcols))
        ccols = {r[1] for r in conn.execute("PRAGMA table_info(cases)")}
        chk("idem_key" in ccols, "cases.idem_key 가 생긴다")
        idx = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        chk("idx_cases_idem" in idx, "★ 멱등 열쇠에 유니크 인덱스가 걸린다(DB 가 중복을 막는다)")

        #  같은 열쇠로 두 번 넣으면 **DB 가** 거절해야 한다
        conn.execute("INSERT INTO insurers(name,login_id,password_hash,created_at) "
                     "VALUES('검증손보','r6ins','x',datetime('now'))")
        iid = conn.execute("SELECT id FROM insurers WHERE login_id='r6ins'").fetchone()[0]
        conn.execute("INSERT INTO cases(case_no,insurer_id,status,idem_key,created_at) "
                     "VALUES('R6-1',?,'접수','K1',datetime('now'))", (iid,))
        dup = False
        try:
            conn.execute("INSERT INTO cases(case_no,insurer_id,status,idem_key,created_at) "
                         "VALUES('R6-2',?,'접수','K1',datetime('now'))", (iid,))
        except sqlite3.IntegrityError:
            dup = True
        chk(dup, "★ 같은 보험사·같은 열쇠의 두 번째 접수를 DB 가 막는다")
        #  열쇠 없는 접수는 여러 건이어도 막히지 않아야 한다(기존 연동 보호)
        free = True
        try:
            conn.execute("INSERT INTO cases(case_no,insurer_id,status,created_at) "
                         "VALUES('R6-3',?,'접수',datetime('now'))", (iid,))
            conn.execute("INSERT INTO cases(case_no,insurer_id,status,created_at) "
                         "VALUES('R6-4',?,'접수',datetime('now'))", (iid,))
        except sqlite3.IntegrityError:
            free = False
        chk(free, "열쇠를 안 보낸 접수는 종전대로 여러 건 들어간다")

        print("\n[10] 분할회피 합산이 실제로 확정가를 더하는가")
        sys.path.insert(0, HERE)
        import compliance as CP
        #  사진없음 접수 2건 — est_price 는 0 이고 낙찰가만 있다
        #  유리 공종 경미기준 1,500만 · 안전선 1,200만(80%). 본건 400만 + 관련 900만
        #  = 1,300만 이라 **합산해야만** 안전선을 넘는다. 고치기 전에는 est_price 가
        #  둘 다 0 이라 관련합이 0 이 되어 이 판정이 아예 실행되지 않았다.
        for no, aw in (("R6-S1", 4_000_000), ("R6-S2", 9_000_000)):
            conn.execute(
                "INSERT INTO cases(case_no,insurer_id,category,region,status,"
                "                  est_price,award_amount,created_at) "
                "VALUES(?,?,'유리','서울 송파구','접수',0,?,datetime('now'))", (no, iid, aw))
        conn.commit()
        base = conn.execute("SELECT id FROM cases WHERE case_no='R6-S1'").fetchone()[0]
        conn.row_factory = sqlite3.Row     # compliance 는 이름으로 컬럼을 읽는다
        total, items = CP.related_sum(conn, base)
        chk(total >= 4_000_000,
            "★ 관련 건 합산이 낙찰가를 더한다(est_price 만 보면 0원이라 판정이 통째로 죽었다)",
            f"합산 {total:,}원 · 관련 {len(items)}건")
        #  그 합산이 실제로 게이트를 움직이는가 — 경미기준(유리 1,500만) 안전선 초과
        g = CP.gate(conn, base, amount=4_000_000)
        chk(not g.get("ok") and "합산" in (g.get("reason") or ""),
            "★ 그 합산이 실제로 분할회피 판정을 띄운다(대법원 2018도3821)",
            f"{g.get('code')} · {(g.get('reason') or '')[:60]}")
        conn.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("-" * 70)
    print(f"  통과 {OK} · 실패 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
