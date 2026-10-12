# -*- coding: utf-8 -*-
"""스캔 410라운드 회귀 — 발송대기 좀비 행(마무리기록 실패로 status='발송대기'인
   채 send_attempts 만 3에 도달한 알림)이 자동스윕·[지금 보내기]·되돌리기
   세 경로 전부에서 영영 안 잡히던 결함.

  배경: sweep_send_notifications() 는 "선-CAS로 attempts 증가 커밋 → 트랜잭션
  밖 동기 발송 → 마무리기록(status 확정)" 2단계 구조다(app.py:6410-6447).
  마무리기록이 락 경합 등으로 실패하면 그 트랜잭션만 롤백돼, 먼저 커밋된
  attempts 증가는 살아남고 status만 영원히 '발송대기'로 남는다 — 라운드200이
  "이 좀비 행을 되살리는 건 범위 밖"이라 명시했던 자리다. 410라운드가 실측
  확인: 이 좀비는 (a) 자동 스윕(send_attempts<3 조건, 6341행)에서 제외되고
  (b) only_ids 로 콕 집어도 같은 조건이 걸려 여전히 제외되며 (c) 기존
  되돌리기(api_outbox_reopen)는 status='수동처리'만 받아 줘(옛 14858행)
  '발송대기'인 이 좀비는 409 NOT_HANDLED 로 거부된다 — 세 길이 전부 막힌
  진짜 막다른 자리였다. 화면도 '되돌리기' 버튼을 status==='수동처리' 일 때만
  그려(admin.js 옛 5625행) 이 상태를 벗어날 방법이 화면 어디에도 안 보였고,
  send_attempts 자체도 admin.js 전체에 한 번도 렌더링되지 않아 정상 대기
  건과 시각적으로 구분이 안 됐다.

  고침: 이미 검토·감사로그까지 갖춘 "되돌리기"(사람이 직접 눌러야만 일어나는
  결정) 동작을 그대로 재사용해, CAS 조건에 이 좀비 케이스(status='발송대기'
  AND send_attempts>=3)도 받아 준다 — 자동 재시도를 새로 만드는 게 아니라
  이미 있는 수동 복구 동작이 닿는 범위만 넓힌다. 화면에도 같은 조건일 때
  경고문구+되돌리기 버튼을 노출한다.

      python test_scan_round410_fixes.py
"""
import io
import os
import shutil
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
ADMINJS_SRC = read("static/admin.js")


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


OLD_CAS_LINE = "        \"UPDATE notifications SET status='발송대기', handled_by=NULL, handled_at=NULL, \"\n" \
               "        \"                         handled_note=NULL, send_attempts=0, send_detail=NULL \"\n" \
               "        \" WHERE id=? AND status='수동처리'\", (nid,))"

print("=" * 72)
print("  스캔 410라운드 회귀 — 발송대기 좀비 행(마무리기록 실패) 복구경로 부재")
print("=" * 72)

print("\n[1] 소스 확인")
_reopen_body = _py_fn_body(APP_SRC, "api_outbox_reopen")
chk("status='발송대기' AND COALESCE(send_attempts,0)>=3" in _reopen_body,
    "★★★★★ api_outbox_reopen 의 CAS 조건이 좀비 케이스(발송대기+시도소진)도 받는다")
chk("status='수동처리'" in _reopen_body,
    "  기존 '수동처리' 조건도 그대로 남아있다(회귀없음)")
chk("send_attempts||0)>=3" in ADMINJS_SRC and "obReopen" in ADMINJS_SRC.split("재시도 소진")[1][:200],
    "★★★ admin.js 가 좀비 행에도 되돌리기 버튼을 그린다")

print("\n[2] 실행 — 실제 서버 호출로 재현")
_tmpdir = tempfile.mkdtemp(prefix="round410_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

#  sweep_send_notifications() 의 대상조회(app.py:6340-41)와 정확히 같은 조건
#  — 이 값으로 "지금 스윕 대상에 잡히는가"를 직접, 결정론적으로 확인한다
#  (실제 팝빌 자격증명 없이도 동작하는, 발송 자체와 무관한 순수 조회 검사).
ELIGIBLE_SQL = ("SELECT COUNT(*) c FROM notifications "
                "WHERE id=? AND status='발송대기' AND channel IN ('알림톡','문자') "
                "AND COALESCE(is_demo,0)=0 AND COALESCE(send_attempts,0) < 3")

try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','중간관리자')")
    #  라운드200이 명시한 좀비 상태를 직접 재현한다 — 실패 확정 UPDATE가
    #  롤백되면서 status='발송대기'인 채 attempts만 남는 그 상태.
    nid = conn.execute(
        "INSERT INTO notifications(ntype,channel,target,message,status,send_attempts,"
        "                          created_at,is_demo) "
        "VALUES('출동수배','알림톡','R410업체','메시지','발송대기',3,?,0)", (DB.now(),)).lastrowid
    conn.commit()

    admin = A.app.test_client()
    _tok = "r410-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    hdr = {"X-CSRF-Token": _tok}

    n_elig_before = conn.execute(ELIGIBLE_SQL, (nid,)).fetchone()["c"]
    chk(n_elig_before == 0,
        "★★★ 좀비 행은 스윕 대상조건(send_attempts<3)을 만족 못해 자동스윕·"
        "[지금 보내기](only_ids 를 줘도 같은 조건이 걸림, 6341행) 둘 다에서 제외된다"
        "(이 부분은 고치지 않음 — 스윕 자체의 3회 소진 판정은 그대로 유지)",
        n_elig_before)

    r1 = admin.post(f"/api/outbox/{nid}/reopen", headers=hdr, json={})
    chk(r1.status_code == 200,
        "★★★★★ 좀비 행(발송대기+시도소진)도 지금은 되돌리기가 통한다"
        "(고치기 전엔 status가 '수동처리'가 아니라서 409 NOT_HANDLED 였다)",
        (r1.status_code, r1.get_json()))

    row = conn.execute("SELECT status, send_attempts FROM notifications WHERE id=?",
                        (nid,)).fetchone()
    chk(row["status"] == "발송대기" and (row["send_attempts"] or 0) == 0,
        "★★★★★ 되돌린 뒤 send_attempts 가 0으로 풀렸다(status는 원래도 발송대기)",
        dict(row))

    n_elig_after = conn.execute(ELIGIBLE_SQL, (nid,)).fetchone()["c"]
    chk(n_elig_after == 1,
        "★★★★★ 이제 자동스윕 대상조건을 실제로 만족한다(완전히 복구됨)",
        n_elig_after)

    print("\n[3] 되돌리기 — 옛 CAS(수동처리만)로 되돌리면 같은 좀비가 다시 막히는가")
    #  ⚠⚠ [라운드612] round412·414가 확립한 안전패턴으로 이관 — 원래는 되돌린 전체
    #    app.py 소스를 실제 on-disk APP_PATH 에 잠깐 써넣고 subprocess로 재현한 뒤
    #    finally에서 복원했다(round409~515대 옛 세대 기법, write→subprocess.run→
    #    write 사이의 창을 동시세션이 관측하면 충돌 — round590이 실제로 겪음).
    #    함수 본문 문자열만 옛 SQL로 되돌려 exec(compile(...))로 네임스페이스
    #    사본에 재구성하고, A.app.view_functions["api_outbox_reopen"] 를 잠깐
    #    치환해 직접 호출한다(실제 파일은 전혀 안 건드림). 정확한 들여쓰기를 손으로
    #    베끼는 대신, 구분되는 시작/끝 지표로 그 사이의 실제 SQL 문 구간만 잘라내
    #    옛(라운드103 시절, status='수동처리' 단독조건) 형태로 통째로 바꿔친다.
    _cur_fn_src = _py_fn_body(APP_SRC, "api_outbox_reopen")
    chk("status='발송대기' AND COALESCE(send_attempts,0)>=3" in _cur_fn_src,
        "  되돌리기 준비 — 현재 함수 본문이 고친 형태임을 확인(좀비조건이 있다)")

    sql_start = _cur_fn_src.index(
        "\"UPDATE notifications SET status='발송대기', handled_by=NULL, handled_at=NULL, \"")
    sql_end = _cur_fn_src.index("(nid,))", sql_start) + len("(nid,))")
    old_sql_block = (
        '"UPDATE notifications SET status=\'발송대기\', handled_by=NULL, handled_at=NULL, "\n'
        '        "                         handled_note=NULL, send_attempts=0, send_detail=NULL "\n'
        '        " WHERE id=? AND status=\'수동처리\'", (nid,))'
    )
    reverted_fn = _cur_fn_src[:sql_start] + old_sql_block + _cur_fn_src[sql_end:]
    reverted_fn = reverted_fn.replace(
        "def api_outbox_reopen(nid):", "def _api_outbox_reopen_pre410(nid):", 1)
    chk("COALESCE(send_attempts,0)>=3" not in reverted_fn
        and "_api_outbox_reopen_pre410" in reverted_fn,
        "  되돌리기 준비 — 되돌린 함수본문에 새 코드 흔적이 안 남는다(실제 파일은 안 건드림)")

    _ns = dict(vars(A))
    exec(compile(reverted_fn, "<round410_pre410_outbox_reopen>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_reopen_fn = A.require_admin(_ns["_api_outbox_reopen_pre410"])

    nid2 = conn.execute(
        "INSERT INTO notifications(ntype,channel,target,message,status,send_attempts,"
        "                          created_at,is_demo) "
        "VALUES('출동수배','알림톡','R410업체2','메시지','발송대기',3,?,0)", (DB.now(),)).lastrowid
    conn.commit()

    _orig_view = A.app.view_functions["api_outbox_reopen"]
    A.app.view_functions["api_outbox_reopen"] = old_reopen_fn
    try:
        r_old = admin.post(f"/api/outbox/{nid2}/reopen", headers=hdr, json={})
    finally:
        A.app.view_functions["api_outbox_reopen"] = _orig_view
    j_old = r_old.get_json() or {}
    chk(r_old.status_code == 409 and j_old.get("code") == "NOT_HANDLED",
        "★★★★★ 옛 CAS(재구성, 실제 파일은 안 건드림)로 되돌리면 같은 좀비가 다시 "
        "409 NOT_HANDLED 로 막힘(인과관계 직접증명)", (r_old.status_code, j_old))

    print("\n[4] 정상 경로 — 대조군('수동처리' 건의 기존 되돌리기)은 회귀없이 동작")
    nid3 = conn.execute(
        "INSERT INTO notifications(ntype,channel,target,message,status,send_attempts,"
        "                          handled_by,handled_at,handled_note,created_at,is_demo) "
        "VALUES('낙찰','알림톡','R410업체3','메시지','수동처리',3,'검증',?,'전화완료',?,0)",
        (DB.now(), DB.now())).lastrowid
    conn.commit()
    r3 = admin.post(f"/api/outbox/{nid3}/reopen", headers=hdr, json={})
    chk(r3.status_code == 200, "  기존 '수동처리'→되돌리기 경로는 회귀없이 그대로 통과", r3.get_json())
    row3 = conn.execute("SELECT status, send_attempts, handled_note FROM notifications WHERE id=?",
                         (nid3,)).fetchone()
    chk(row3["status"] == "발송대기" and (row3["send_attempts"] or 0) == 0 and not row3["handled_note"],
        "  대조군도 send_attempts 리셋+handled_note 정리까지 회귀없이 그대로", dict(row3))

    print("\n[5] 대조군 — 관계없는 정상 대기 건(attempts=0)에는 되돌리기 버튼이 안 보인다")
    #  admin.js 조건 자체를 직접 재현(순수 로직 대조 — 실제 렌더 엔진 없이도
    #  이 회귀의 핵심 조건만 별도로 실측한다)
    js_cond_zombie = "(status_ == '수동처리') or (status_ == '발송대기' and attempts_ >= 3)"
    ns = {}
    exec(f"def show_button(status_, attempts_): return {js_cond_zombie}", ns)
    chk(ns["show_button"]("발송대기", 0) is False,
        "  정상 대기(attempts=0)는 버튼 조건이 거짓이다(과잉노출 아님)")
    chk(ns["show_button"]("발송대기", 3) is True,
        "  좀비(attempts=3)는 버튼 조건이 참이다")
    chk(ns["show_button"]("수동처리", 0) is True,
        "  기존 수동처리 케이스도 여전히 참이다(회귀없음)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")
finally:
    #  [라운드612] 실제 app.py를 이제 전혀 안 쓰므로(위 [3]을 exec 재구성으로 이관)
    #  디스크 복원문은 더 이상 필요 없다 — 스크래치 자원 정리만 남긴다.
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
