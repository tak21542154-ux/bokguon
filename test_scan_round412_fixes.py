# -*- coding: utf-8 -*-
"""스캔 412라운드 회귀 — sweep_webhook_retries() 의 재시도상한 종결처리가
   status='실패'로 굳은 경우만 다루고, write-back 실패로 status='대기'에
   영구 박제되는 경로는 전혀 다루지 않던 결함.

  배경: _webhook_send()(app.py:1984-2019)는 네트워크 시도 후 결과를 **별도
  커넥션**(c2 = DB.get_db())으로 쓰는데, 그 write-back(c2.execute/commit)이
  실패하면 2018-19행의 bare except가 로그 한 줄 없이 통째로 삼킨다. 모든
  웹훅은 deliver_webhook()(2103행)에서 처음엔 반드시 status='대기'로
  INSERT되므로, 이 write-back이 매 시도마다 실패하면 status가 '대기'에
  박제된 채 attempts만(sweep_webhook_retries 자신의 선-기록 CAS, 6206-18행,
  이건 _webhook_send 호출과 별개라 write-back 실패와 무관하게 정상 진행)
  오른다. 종결처리(옛 6238·6242행)는 `status == "실패"` 만 보므로 이 경우
  절대 '포기'로 안 굳고, 감사로그도 운영팀 알림도 안 남고, due 조회의
  attempts<max_attempts 조건에서 조용히 영구 제외된다 — 그리고 webhook_
  deliveries 를 되돌리는 수동 복구 라우트도 이 앱에 전혀 없다(app.py 전체
  grep 확인, insurers/apikey/webhook/webhook-test 라우트 어디에도 없음).

  같은 함수 안에서 이미 두 번(6197·6210행) 쓰인 `status IN ('실패','대기')`
  관례를 종결처리에도 그대로 적용하면 되는, 새 정책판단이 필요 없는 결함
  (411라운드와 같은 클래스 — "형제는 다 하는데 한 곳만 빠짐").

  고침: ① 종결처리 조건을 status IN ('실패','대기')로 넓힘. ② _webhook_send()
  의 write-back 실패를 최소한 로그는 남기도록 함(진단 가능성 개선, 위험 없음).

      python test_scan_round412_fixes.py
"""
import io
import os
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

print("=" * 72)
print("  스캔 412라운드 회귀 — 웹훅 재시도상한 종결처리가 '대기' 박제를 놓치던 결함")
print("=" * 72)

print("\n[1] 소스 확인")
i_sw = APP_SRC.index("def sweep_webhook_retries(")
i_sw_end = APP_SRC.index("\ndef ", i_sw + 1)
sw_body = APP_SRC[i_sw:i_sw_end]
chk('d2["status"] in ("실패", "대기")' in sw_body,
    "★★★★★ sweep_webhook_retries 의 종결처리가 이제 '대기'도 함께 본다")
chk("status='포기' WHERE id=? \"\n                        \"AND status IN ('실패','대기')" in sw_body
    or "AND status IN ('실패','대기')" in sw_body,
    "★★★★★ UPDATE 조건도 같이 넓어졌다")
chk(sw_body.count("status IN ('실패','대기')") >= 3,
    "  이 함수 안의 status IN ('실패','대기') 관례가 이제 3곳(사전정리·CAS·"
    "종결처리) 모두에 일관되게 적용됐다", sw_body.count("status IN ('실패','대기')"))
chk('app.logger.exception("웹훅 write-back 실패 delivery=%s", delivery_id)' in APP_SRC,
    "  _webhook_send() 의 write-back 실패도 이제 로그가 남는다")

print("\n[2] 실행 — write-back이 매번 조용히 실패하는 시나리오를 실제로 재현")
_tmpdir = tempfile.mkdtemp(prefix="round412_")
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
    iid = conn.execute(
        "INSERT INTO insurers(name,status,webhook_url,webhook_secret,api_enabled) "
        "VALUES('R412보험','활성','https://real-insurer.example.com/hook','sec',1)").lastrowid
    conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
        "VALUES('R412-ZOMBIE','완료','가드레일','서울',?,0)", (iid,))
    conn.commit()

    def _fake_send_writeback_always_fails(delivery_id, url, secret, payload_str, count_attempt=True):
        #  _webhook_send() 의 결과 write-back(별도 커넥션 c2)이 매번 조용히
        #  실패하는 것과 정확히 같은 효과 — 아무 것도 쓰지 않는다. sweep_
        #  webhook_retries() 자신의 선-기록 CAS(6206-18행)는 이 함수 호출
        #  '이전'에 이미 attempts 를 올려 두므로, 여기서 아무 것도 안 써도
        #  attempts 증가 자체는 write-back 실패와 무관하게 정상 진행된다
        #  (실제 버그의 핵심 — attempts 는 늘어도 status 만 안 바뀜).
        pass

    real_send = A._webhook_send
    A._webhook_send = _fake_send_writeback_always_fails
    with A.app.test_request_context():
        did = A.deliver_webhook(conn, iid, "case.completed", "R412-ZOMBIE", {"amount": 5000000})
        conn.commit()
    row0 = conn.execute("SELECT status FROM webhook_deliveries WHERE id=?", (did,)).fetchone()
    chk(row0["status"] == "대기",
        "  (사전조건) deliver_webhook 직후 status가 '대기'로 시작한다(정상)", dict(row0))
    #  ⚠ due 조회(6185-88행)의 '대기' 분기는 delivered_at 이 아니라 created_at
    #    기준 10분 경과를 요구한다(막 생긴 대기를 너무 빨리 재시도하지 않으려는
    #    의도) — 처음엔 delivered_at 만 되돌렸다가 due 대상에 전혀 안 잡혀
    #    attempts=0 그대로인 것을 실측으로 발견, created_at 도 함께 되돌림.
    conn.execute("UPDATE webhook_deliveries SET created_at=datetime('now','-1 hour'), "
                 "delivered_at=datetime('now','-1 hour') WHERE id=?", (did,))
    conn.commit()

    rounds = 0
    while True:
        n = A.sweep_webhook_retries(conn, limit=10, max_attempts=5)
        rounds += 1
        if n == 0 or rounds > 20:
            break
        conn.execute("UPDATE webhook_deliveries SET delivered_at=datetime('now','-1 hour') "
                     "WHERE id=?", (did,))
        conn.commit()

    row = conn.execute("SELECT attempts, status FROM webhook_deliveries WHERE id=?", (did,)).fetchone()
    chk(row["attempts"] == 5,
        "★ (사전조건) write-back이 매번 실패해도 attempts는 정상적으로 5까지 "
        "오른다(선-기록 CAS는 write-back과 무관)", dict(row))
    chk(row["status"] == "포기",
        "★★★★★ 5회 소진 뒤 status가 이제 '포기'로 명시적으로 굳는다"
        "(고치기 전엔 '대기'에 영구 박제되고 다음 스윕에서도 조용히 제외됐다)",
        dict(row))

    noti = conn.execute(
        "SELECT message FROM notifications "
        "WHERE ntype='웹훅발송포기' AND message LIKE '%R412-ZOMBIE%'").fetchone()
    chk(noti is not None,
        "★★★★★ 운영팀 알림도 실제로 생성된다(고치기 전엔 이 케이스에서 "
        "notifications 행이 전혀 안 남았다)", noti)

    log = conn.execute(
        "SELECT detail FROM activity_log WHERE action='웹훅 재전송 포기' "
        "AND detail LIKE '%R412-ZOMBIE%'").fetchone()
    chk(log is not None,
        "★★★★★ activity_log 에도 포기 사실이 감사기록으로 남는다"
        "(고치기 전엔 이 케이스에서 전혀 안 남았다)", log)

    n_more = A.sweep_webhook_retries(conn, limit=10, max_attempts=5)
    chk(n_more == 0, "  포기 뒤에는 스윕이 이 건을 더는 집지 않는다(무한재발사 아님)", n_more)

    print("\n[3] 되돌리기 — 옛 조건(status=='실패'만)으로 되돌리면 같은 시나리오가 재현되는가")
    #  ⚠ [라운드611] 디스크의 진짜 app.py 는 이제 전혀 건드리지 않는다(이 저장소는
    #    git이 없어 동시세션이 상시전제 — 여기서 실제 app.py를 잠깐이라도 다른
    #    내용으로 덮어쓰면 그 창(subprocess.run 이 도는 수백ms)에 다른 세션이
    #    같은 파일을 읽거나 저장하면 충돌한다). round604~610이 확립한 "공용헬퍼
    #    재바인딩" 패턴(A.app.view_functions[...] 임시치환과 같은 발상)을 플라스크
    #    라우트가 아닌 일반 함수에 적용한다 — [1]에서 이미 뽑아 둔 함수 본문
    #    문자열(sw_body)만 옛 조건으로 되돌려 exec(compile(...))로 재구성하고,
    #    globals 를 A.__dict__ 로 줘서 이 재구성 함수가 실제 앱과 완전히 같은
    #    rows/one/_webhook_send/app/DB/notify 를 그대로 보게 한다(subprocess도
    #    불필요 — 같은 프로세스·같은 conn으로 바로 호출).
    OLD_CHECK = 'if d2 and d2["status"] == "실패":'
    NEW_CHECK = 'if d2 and d2["status"] in ("실패", "대기"):'
    chk(NEW_CHECK in sw_body and OLD_CHECK not in sw_body,
        "  되돌리기 준비 — 현재 함수 본문이 고친 형태임을 확인")
    i0 = sw_body.index('"UPDATE webhook_deliveries SET status=\'포기\' WHERE id=? "')
    i1 = sw_body.index("(r[\"id\"],))", i0) + len("(r[\"id\"],))")
    new_update_block = sw_body[i0:i1]
    reverted_body = sw_body.replace(NEW_CHECK, OLD_CHECK)
    reverted_body = reverted_body.replace(
        new_update_block,
        "\"UPDATE webhook_deliveries SET status='포기' WHERE id=? AND status='실패'\",\n"
        "                        (r[\"id\"],))")
    chk(reverted_body != sw_body and OLD_CHECK in reverted_body
        and "AND status='실패'\"," in reverted_body,
        "  되돌린 함수본문 문자열이 실제로 옛 조건을 담고 있다(치환 확인)")

    _ns = {}
    exec(compile(reverted_body, "<round412_old_sweep_webhook_retries>", "exec"),
         A.__dict__, _ns)                      # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_sweep_webhook_retries = _ns["sweep_webhook_retries"]

    iid2 = conn.execute(
        "INSERT INTO insurers(name,status,webhook_url,webhook_secret,api_enabled) "
        "VALUES('R412보험구판','활성','https://real-insurer2.example.com/hook','sec',1)").lastrowid
    conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
        "VALUES('R412-ZOMBIE2','완료','가드레일','서울',?,0)", (iid2,))
    conn.commit()
    with A.app.test_request_context():
        did2 = A.deliver_webhook(conn, iid2, "case.completed", "R412-ZOMBIE2", {"amount": 1})
        conn.commit()
    conn.execute("UPDATE webhook_deliveries SET created_at=datetime('now','-1 hour'), "
                 "delivered_at=datetime('now','-1 hour') WHERE id=?", (did2,))
    conn.commit()
    rounds2 = 0
    while True:
        n2 = old_sweep_webhook_retries(conn, limit=10, max_attempts=5)
        rounds2 += 1
        if n2 == 0 or rounds2 > 20:
            break
        conn.execute("UPDATE webhook_deliveries SET delivered_at=datetime('now','-1 hour') "
                     "WHERE id=?", (did2,))
        conn.commit()
    row2 = conn.execute(
        "SELECT attempts, status FROM webhook_deliveries WHERE id=?", (did2,)).fetchone()
    chk(row2["attempts"] == 5 and row2["status"] == "대기",
        "★★★★★ 옛 조건으로 재구성하면 같은 시나리오에서 attempts=5인데도 "
        "status가 '대기'에 그대로 박제됨(인과관계 직접증명 — 디스크의 진짜 "
        "app.py는 전혀 안 건드림)", dict(row2))

    A._webhook_send = real_send
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
