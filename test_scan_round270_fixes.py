# -*- coding: utf-8 -*-
"""스캔 270라운드 회귀 — 협력사 계정 일괄발급(partner_accounts.py) 결함 2건
   (이 세션에서 사상 첫 주조사, 형제인 app.py api_partner_bulk_credentials가
   라운드199에서 이미 겪고 고친 것과 같은 유형의 결함을 이 CLI 쪽만 안 고친
   채 갖고 있었다 — 정밀조사 Agent가 발견, 독립 재검증 후 수정).

  [1] UPDATE 가 WHERE id=? 뿐이라 재확인이 없었다. 스크립트를 동시에 두 번
      돌리면(응답지연 오인 재실행 등) 두 실행이 같은 업체를 대상으로 각자
      비밀번호를 계산한 뒤, 나중에 커밋한 쪽이 먼저 커밋한 쪽을 **에러 없이
      조용히** 덮어썼다(실측: 스레드 2개로 재현 — 먼저 화면에 찍혀 전화로
      불러줬을 비밀번호가 그 순간 무효가 됨). WHERE 에 재확인
      (AND COALESCE(login_id,'')='')을 걸고 rowcount 로 확정한다.

  [2] main() 의 배치 루프에 항목별 예외처리가 없고 commit() 은 루프 전체가
      끝난 뒤 한 번뿐이었다 — 한 업체 처리 중 예외(대표적으로 UNIQUE 충돌)가
      나면 그 앞에서 이미 "✔ 발급"으로 화면에 찍힌(아직 미커밋인) 업체들까지
      통째로 날아간다. 형제(app.py api_partner_bulk_credentials, 라운드199)의
      SAVEPOINT/ROLLBACK TO SAVEPOINT 패턴을 그대로 옮겨 이 업체 몫만 격리한다.

      python test_scan_round270_fixes.py
"""
import contextlib
import io
import os
import secrets
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []

#  ⚠ db.py 를 불러오기 전에 검증용 DB 경로부터 정한다.
_tmpdir = tempfile.mkdtemp(prefix="round270_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


SRC = read("partner_accounts.py")

print("=" * 72)
print("  스캔 270라운드 회귀 — partner_accounts.py 동시실행 덮어쓰기·배치전멸")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_main = SRC.index("def main():")
main_body = SRC[i_main:]
chk('AND COALESCE(login_id,\'\')=\'\'' in main_body.split("def demo()")[0]
    and "SAVEPOINT partner_acct" in main_body
    and "ROLLBACK TO SAVEPOINT partner_acct" in main_body
    and "cur.rowcount" in main_body,
    "★★★★★ UPDATE 에 재확인 조건 + SAVEPOINT 격리가 모두 들어갔다"
    "(고치기 전엔 WHERE id=? 뿐이고 항목별 예외처리도 없었다)")

# ============================================================
print("\n[2] 실행 준비 — 격리 DB + 대상 업체")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
try:
    import importlib
    import db as DB
    DB.init_db()
    import partner_accounts as PA
    importlib.reload(PA)

    def _mk_partner(name, biz_no):
        conn = DB.get_db()
        pid = conn.execute(
            "INSERT INTO partners(name,partner_type,major,category,region,biz_no,status,"
            "                     created_at) "
            "VALUES(?,'시행사','금속ㆍ창호','금속ㆍ창호ㆍ지붕ㆍ건축물조립공사업','서울',?,'활성',?)",
            (name, biz_no, DB.now())).lastrowid
        conn.commit()
        conn.close()
        return pid

    def _run_main(argv, out, idx):
        """단일 스레드 전용 호출 — sys.stdout 전역 치환으로 출력을 캡처한다."""
        real_argv = sys.argv
        sys.argv = argv
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                PA.main()
        finally:
            sys.argv = real_argv
        out[idx] = buf.getvalue()

    #  ⚠ 동시실행(threading) 검증에는 contextlib.redirect_stdout 을 못 쓴다 —
    #    sys.stdout 은 프로세스 전역이라 두 스레드가 동시에 치환하면 서로
    #    덮어써 출력이 뒤섞인다(실제로 이 방식으로 처음 짰다가 prove 단계에서
    #    발각됨 — 검증 도구 자신의 결함까지 되돌려보기 방법론이 잡아낸 사례).
    #    대신 partner_accounts 모듈 자신의 전역 네임스페이스에 스레드ID로
    #    분기하는 print 하나만 심어, 그 모듈이 부르는 bare print() 만 호출한
    #    스레드 고유의 버퍼로 보낸다(같은 dict 라도 각 스레드는 자기 키만
    #    쓰고 읽으므로 경합이 없다).
    _thread_bufs = {}

    def _dispatching_print(*a, **kw):
        sep, end = kw.get("sep", " "), kw.get("end", "\n")
        text = sep.join(str(x) for x in a) + end
        buf = _thread_bufs.get(threading.get_ident())
        (buf.write if buf is not None else sys.__stdout__.write)(text)

    def _run_main_concurrent(out, idx):
        tid = threading.get_ident()
        _thread_bufs[tid] = io.StringIO()
        try:
            PA.main()
        finally:
            out[idx] = _thread_bufs.pop(tid).getvalue()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드270 [2] 준비", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — 동시 실행 시 같은 업체를 두 번 발급해도 덮어쓰지 않는가")
# ------------------------------------------------------------
try:
    mark = "R270A-" + secrets.token_hex(3)
    pid = _mk_partner(f"{mark}-동시성테스트", "1112223333")

    #  두 스레드가 각자 pick()→make_login_id()→gen_pw() 까지 마친 뒤(둘 다
    #  아직 미커밋이라 서로 이 업체가 "비어있다"고 본 상태) 동시에 UPDATE 를
    #  치도록, gen_pw() 호출 시점에 배리어를 건다 — 실제 동시실행의 핵심
    #  경합구간(둘 다 대상으로 확정한 뒤 저장을 다투는 순간)을 그대로 재현.
    barrier = threading.Barrier(2, timeout=10)
    _orig_gen_pw = PA.gen_pw

    def _synced_gen_pw(n=12):
        pw = _orig_gen_pw(n)
        barrier.wait()
        return pw

    real_argv = sys.argv
    results = [None, None]
    #  ⚠ 아래 패치(PA.print·PA.gen_pw·sys.argv)는 전부 finally 로 반드시
    #    되돌린다 — 여기서 예외가 나 복구를 건너뛰면, 이후 [4]절이 단일
    #    스레드용 _run_main(redirect_stdout)을 쓰는데 PA.print 가 여전히
    #    스레드ID로 분기하는 함수로 남아 있어(당시 스레드가 이미 없어 버퍼를
    #    못 찾음) 캡처가 조용히 비게 된다 — 검증도구 자신의 상태누수를 막는다.
    PA.gen_pw = _synced_gen_pw
    PA.print = _dispatching_print
    sys.argv = ["partner_accounts.py", "--ids", str(pid)]     # 두 스레드가 공유 — 값은 동일하므로 안전
    try:
        t1 = threading.Thread(target=_run_main_concurrent, args=(results, 0))
        t2 = threading.Thread(target=_run_main_concurrent, args=(results, 1))
        t1.start(); t2.start()
        t1.join(timeout=30); t2.join(timeout=30)
    finally:
        sys.argv = real_argv
        del PA.print
        PA.gen_pw = _orig_gen_pw

    chk(t1.is_alive() is False and t2.is_alive() is False,
        "STEP 두 실행 모두 정상 종료됨(교착 없음)")

    won = [r for r in results if r and "✔ " in r]
    lost = [r for r in results if r and "방금 다른 실행이 먼저 발급함" in r]
    chk(len(won) == 1, "★★★★★ 정확히 한쪽만 발급에 성공한다(둘 다 성공하면 덮어쓰기 재발)",
        results)
    chk(len(lost) == 1,
        "★★★★★ 진 쪽은 조용히 실패하지 않고 '다른 실행이 먼저 발급함'을 스스로 안다"
        "(고치기 전엔 진 쪽도 ✔ 로 찍혀 자신이 성공한 줄 알았다)", results)

    #  화면에 찍힌 아이디·비밀번호가 실제로 DB 에 유효하게 저장돼 있는가
    #  (승자의 값 == 저장된 값, 승자가 아닌 값으로는 로그인 불가여야 함).
    import re as _re
    m = _re.search(r"✔ .+?\[.{0,4}\]\s+(\S+)\s+(\S+)", won[0])
    win_lid, win_pw = m.group(1), m.group(2)
    conn = DB.get_db()
    row = conn.execute("SELECT login_id, password_hash FROM partners WHERE id=?",
                       (pid,)).fetchone()
    conn.close()
    chk(row["login_id"] == win_lid,
        "STEP DB 에 저장된 아이디가 승자가 화면에서 본 아이디와 정확히 같다")
    chk(DB.verify_pw(win_pw, row["password_hash"]),
        "★★★★★ 승자가 화면에서 본 비밀번호로 실제 로그인 검증이 통과한다"
        "(승자 값이 나중에 덮이지 않았다는 최종 증거)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드270 [3] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[4] 실행 — 배치 중 한 업체 처리에서 예외가 나도 나머지가 살아남는가")
# ------------------------------------------------------------
try:
    mark2 = "R270B-" + secrets.token_hex(3)
    ids = [_mk_partner(f"{mark2}-{i}", f"999888{7770+i}") for i in range(3)]

    _orig_hash_pw = DB.hash_pw
    _calls = []

    def _flaky_hash_pw(pw):
        _calls.append(pw)
        if len(_calls) == 2:
            raise RuntimeError("SIMULATED-HASH-FAIL-R270")
        return _orig_hash_pw(pw)

    DB.hash_pw = _flaky_hash_pw
    out = {}
    _run_main(["partner_accounts.py", "--ids", ",".join(str(i) for i in ids)], out, 0)
    DB.hash_pw = _orig_hash_pw

    printed = out[0]
    chk("Traceback" not in printed,
        "★★★★★ 한 업체가 실패해도 배치 전체가 죽지 않는다"
        "(고치기 전엔 여기서 스크립트 전체가 예외로 죽었다)")
    chk("발급 실패" in printed, "STEP 실패한 업체가 콘솔에 명확히 보인다")
    chk(printed.count("✔ ") == 2,
        "★★★★★ 실패한 1곳을 뺀 나머지 2곳은 성공으로 찍힌다(고치기 전엔 이마저 0곳)",
        printed)

    conn = DB.get_db()
    saved = conn.execute(
        "SELECT COUNT(*) n FROM partners WHERE id IN ({}) AND COALESCE(login_id,'')<>''"
        .format(",".join("?" * len(ids))), ids).fetchone()["n"]
    conn.close()
    chk(saved == 2,
        "★★★★★ 화면에 성공으로 찍힌 2곳이 실제로 DB 에도 저장돼 있다"
        "(고치기 전엔 단일 commit 구조상 이마저 0곳으로 날아갔을 것)", saved)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드270 [4] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
