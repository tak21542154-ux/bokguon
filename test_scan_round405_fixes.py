# -*- coding: utf-8 -*-
"""스캔 405라운드 회귀 — test_b4_deadline.py 가 sweep_auctions() 의
   전역(DB 전체) 스캔 결과에 의존하던 결함, test_scan_round5_fixes.py
   의 정리(_cleanup)가 사건 하나 실패로 전체가 조용히 취소되던 결함.

  배경: 배터리가 357·359·372·396라운드 총 4번 "2연속 실패 후 3차
  클린" 패턴을 반복했다. 405라운드 디버깅 에이전트가 실제 주입
  재현으로 근본원인을 확정 — sweep_auctions()(app.py:5583)는 호출자의
  사건으로 범위를 좁히지 않고 DB 전체의 '마감지난 진행중' 경매를
  스캔한다(운영에선 의도된 정상 설계). test_b4_deadline.py 는 이
  전역 스캔 결과(scanned==0)가 자기 시나리오에서 항상 0이라고
  가정했는데, 공유 verify.db 에 다른 테스트(test_scan_round5_fixes.py,
  마감시각이 이미 지난 '진행' 상태 경매를 조건 없이 만듦)가 남긴
  고아 행이 하나라도 있으면 그 가정이 깨진다. 그 고아 행이 남는
  경로는 test_scan_round5_fixes.py 의 _cleanup() 이 사건 하나의
  DELETE 실패(락 경합 등)로 전체가 커밋 한 번 없이 통째로 취소되는
  구조였다.

  고침: ① test_b4_deadline.py 의 검사②를 "내 경매가 안 건드려졌다"
  로만 좁히고 "DB 전체에 마감지난 경매가 없다"는 무관한 전역가정을
  뺀다. ② test_scan_round5_fixes.py 의 _cleanup() 을 사건별로 감싸
  하나 실패해도 나머지는 계속 지우고 즉시 커밋하게 한다.

      python test_scan_round405_fixes.py
"""
import io
import os
import secrets
import shutil
import sqlite3 as _real_sqlite3
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


B4_SRC = read("test_b4_deadline.py")
R5_SRC = read("test_scan_round5_fixes.py")
B4_PATH = os.path.join(HERE, "test_b4_deadline.py")

OLD_SNIPPET = (
    '    r = A.sweep_auctions(conn)\n'
    '    chk(r["scanned"] == 0 and st(conn, cid1)["status"] == "입찰중",\n'
    '        "마감 전에는 상태 불변", r)'
)
NEW_SNIPPET = (
    '    r = A.sweep_auctions(conn)\n'
    '    chk(st(conn, cid1)["status"] == "입찰중",\n'
    '        "마감 전에는 상태 불변(내 경매는 그대로)", r)'
)

print("=" * 72)
print("  스캔 405라운드 회귀 — deadline 배터리 플레이크 근본원인 수정")
print("=" * 72)

print("\n[1] 소스 확인")
chk(OLD_SNIPPET not in B4_SRC,
    "★★★★★ test_b4_deadline.py 검사②가 전역 scanned==0 가정을 뺐다")
chk(NEW_SNIPPET in B4_SRC,
    "  검사②가 여전히 '내 경매 상태 불변'은 확인한다")
chk("except sqlite3.Error as e:\n                print(" in R5_SRC,
    "★★★★★ test_scan_round5_fixes.py _cleanup() 이 사건별 try/except를 얻었다")

print("\n[2] 실행 — 고아(다른 사건) 마감지난 경매가 있어도 sweep 이 내 경매엔 무해함을 실측")
_tmpdir = tempfile.mkdtemp(prefix="round405_")
_dbpath = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_DB_PATH"] = _dbpath
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

iid = pid = None
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    now = DB.now()
    iid = conn.execute(
        "INSERT INTO insurers(name,status,login_id,created_at) "
        "VALUES('R405보험','활성','r405i',?)", (now,)).lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,status,license_status,region,partner_type,created_at) "
        "VALUES('R405업체','활성','확인됨','서울','시행사',?)", (now,)).lastrowid

    #  '내' 사건 — 아직 마감 전(미래 deadline)
    mine_cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,est_price,is_demo,created_at) "
        "VALUES(?,'입찰중','유리','서울',?,3000000,0,?)",
        ("R405MINE" + secrets.token_hex(2), iid, now)).lastrowid
    conn.execute(
        "INSERT INTO auctions(case_id,kind,status,deadline,created_at) "
        "VALUES(?,'원경매','진행',datetime('now','+9 hours','+2 hours'),?)",
        (mine_cid, now))

    #  '고아' 사건 — round5류 정리 실패가 남길 법한, 이미 마감 지난 '진행' 경매
    #  (is_demo 미설정 — round5 의 mkcase() 도 is_demo 를 안 넣는다)
    orphan_cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,est_price,created_at) "
        "VALUES(?,'시공중','유리','서울',?,3000000,?)",
        ("R405ORPHAN" + secrets.token_hex(2), iid, now)).lastrowid
    conn.execute(
        "INSERT INTO auctions(case_id,kind,status,deadline,created_at) "
        "VALUES(?,'전체재경매','진행',datetime('now','+9 hours','-1 hours'),?)",
        (orphan_cid, now))
    conn.commit()

    r = A.sweep_auctions(conn)
    chk(r["scanned"] >= 1,
        "  고아 경매가 실제로 전역 스캔에 잡힌다(=옛 assert 였다면 여기서 깨졌을 조건)", r)
    my_status = conn.execute("SELECT status FROM cases WHERE id=?", (mine_cid,)).fetchone()[0]
    chk(my_status == "입찰중",
        "★★★★★ 고아가 스캔·처리되는 동안에도 '내' 경매(아직 마감 전)는 그대로다", my_status)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행([2] sweep_auctions 실측)", f"{type(e).__name__} {e}")

print("\n[3] 실행 — test_b4_deadline.py 를 고아 오염 DB에 대해 통째로 실행")


def _run_b4(b4_path=None):
    #  ⚠ text=True 만 쓰면 이 Windows(cp949 로케일)에서 UTF-8 한글 출력을
    #    디코드하다 subprocess 내부 리더스레드가 죽는다 — 인코딩을 명시한다.
    env = dict(os.environ)
    if b4_path and b4_path != B4_PATH:
        #  ⚠⚠ [라운드627] 스크래치 사본(다른 디렉터리)으로 실행하면
        #    sys.path[0]이 그 스크래치 디렉터리가 되어 스크립트 안의
        #    `import db`/`import app`이 깨진다 — PYTHONPATH 맨 앞에 HERE를
        #    붙여준다(스크래치 디렉터리엔 db.py/app.py가 없으므로 이름
        #    충돌 없이 그대로 HERE의 진짜 db.py/app.py를 찾아간다).
        env["PYTHONPATH"] = HERE + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, b4_path or B4_PATH], cwd=HERE, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)


try:
    r1 = _run_b4()
    chk(r1.returncode == 0,
        "★★★★★ 고아가 있는 DB에서도 test_b4_deadline.py 가 지금은 통과한다",
        (r1.stdout[-800:] + r1.stderr[-400:]))

    print("\n[4] 되돌리기 — 옛 assert(전역 scanned==0)로 되돌리면 같은 오염 DB에서 재현되는가")
    #  ⚠ [3]의 sweep_auctions() 호출 자체가 이미 고아를 처리해(상태가 '진행'을
    #    벗어남) 스스로 청소했다 — 바로 그 자가치유 메커니즘(405 조사가 밝힌
    #    핵심)이다. 되돌린 코드로도 인과관계를 증명하려면 새 고아를 하나 더
    #    심어야 한다(안 그러면 옛 코드조차 오염이 없어 통과해버려 인과관계를
    #    증명하지 못한다 — 실측으로 확인된 함정).
    conn4 = DB.get_db()
    orphan2_cid = conn4.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,est_price,created_at) "
        "VALUES(?,'시공중','유리','서울',?,3000000,?)",
        ("R405ORPHAN2" + secrets.token_hex(2), iid, DB.now())).lastrowid
    conn4.execute(
        "INSERT INTO auctions(case_id,kind,status,deadline,created_at) "
        "VALUES(?,'전체재경매','진행',datetime('now','+9 hours','-1 hours'),?)",
        (orphan2_cid, DB.now()))
    conn4.commit(); conn4.close()

    #  ⚠⚠ [라운드627] 이전 버전은 여기서 실제 살아있는 test_b4_deadline.py
    #    파일에 직접 썼다(io.open(B4_PATH,"w")) — 이 파일은 스캔용 스크래치가
    #    아니라 run_all_tests.py에 독립 등록된 진짜 회귀테스트이자
    #    test_b4_http.py·round254/406/5 가 참조하는 실물 자산이다. _run_b4가
    #    이미 경로 인자를 받게 돼 있으므로, tempfile 스크래치 사본에 되돌린
    #    내용을 써서 그 경로로 서브프로세스를 실행한다(실제 파일은 이
    #    검증 내내 전혀 안 건드린다 — finally 복원이 필요 없어짐).
    if OLD_SNIPPET not in B4_SRC and NEW_SNIPPET in B4_SRC:
        reverted_src = B4_SRC.replace(NEW_SNIPPET, OLD_SNIPPET)
        _scratch_dir = tempfile.mkdtemp(prefix="r405_b4_")
        try:
            _scratch_b4 = os.path.join(_scratch_dir, "test_b4_deadline.py")
            io.open(_scratch_b4, "w", encoding="utf-8", newline="\n").write(reverted_src)
            r2 = _run_b4(b4_path=_scratch_b4)
            chk(r2.returncode != 0,
                "★★★★★ 옛 assert로 되돌리면 같은 오염 DB에서 실제로 실패 재현됨(인과관계 증명)",
                (r2.stdout[-800:] + r2.stderr[-400:]))
        finally:
            shutil.rmtree(_scratch_dir, ignore_errors=True)
        r3 = _run_b4()
        chk(r3.returncode == 0, "  재확인 — 실제(안 건드린) test_b4_deadline.py는 여전히 통과",
            r3.stdout[-400:])
    else:
        chk(False, "★★★★★ 되돌리기 준비 — 스니펫 매칭 실패(수동 확인 필요)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행([3]/[4] test_b4_deadline.py 서브프로세스)", f"{type(e).__name__} {e}")

chk(io.open(B4_PATH, encoding="utf-8").read() == B4_SRC,
    "★★★★★ test_b4_deadline.py는 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일)")

print("\n[5] 실행 — test_scan_round5_fixes.py _cleanup() 의 사건별 격리(가짜 락경합 주입)")
try:
    conn2 = DB.get_db()
    now2 = DB.now()
    case_a = conn2.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,est_price,created_at) "
        "VALUES(?,'시공중','유리','서울',?,1000000,?)", ("R405CLA", iid, now2)).lastrowid
    case_b = conn2.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,est_price,created_at) "
        "VALUES(?,'시공중','유리','서울',?,1000000,?)", ("R405CLB", iid, now2)).lastrowid
    conn2.commit()
    conn2.close()

    #  _cleanup 함수 소스만 추출해 exec 격리 실행 — case_a 의 DELETE FROM bids
    #  만 '락 경합'을 흉내내 실패시키는 가짜 sqlite3 로 갈아끼운다.
    i0 = R5_SRC.index("def _cleanup():")
    i1 = R5_SRC.index("\n\n\n", i0)
    cleanup_src = R5_SRC[i0:i1]

    class _FakeConn:
        def __init__(self, real, fail_id):
            self._c, self._fail_id, self.fail_triggered = real, str(fail_id), False

        def execute(self, sql, params=()):
            if "DELETE FROM bids" in sql and params and str(params[0]) == self._fail_id:
                self.fail_triggered = True
                raise _real_sqlite3.OperationalError("database is locked (simulated)")
            return self._c.execute(sql, params)

        def commit(self):
            self._c.commit()

        def close(self):
            self._c.close()

    class _FakeSqlite3:
        Error = _real_sqlite3.Error
        OperationalError = _real_sqlite3.OperationalError

        def __init__(self, fail_id):
            self._fail_id = fail_id
            self.made = []

        def connect(self, path):
            proxy = _FakeConn(_real_sqlite3.connect(path), self._fail_id)
            self.made.append(proxy)
            return proxy

    fake_sqlite3 = _FakeSqlite3(fail_id=case_a)
    ns = {"sqlite3": fake_sqlite3, "DBP": _dbpath, "cleanup": [case_a, case_b],
          "print": print, "sys": sys}
    exec(compile(cleanup_src, "<r5_cleanup>", "exec"), ns)  # noqa: S102 -- 우리 소스, 실제 함수를 그대로 실행
    ns["_cleanup"]()

    chk(bool(fake_sqlite3.made) and fake_sqlite3.made[0].fail_triggered,
        "  가짜 락경합이 실제로 case_a 의 DELETE FROM bids 에서 발동했다")
    conn3 = DB.get_db()
    b_left = conn3.execute("SELECT COUNT(*) c FROM cases WHERE id=?", (case_b,)).fetchone()["c"]
    a_left = conn3.execute("SELECT COUNT(*) c FROM cases WHERE id=?", (case_a,)).fetchone()["c"]
    conn3.close()
    chk(b_left == 0,
        "★★★★★ case_a 의 DELETE가 실패해도 case_b 는 정상적으로 지워진다(사건별 격리)",
        f"case_b 남은 행={b_left}")
    chk(a_left == 1,
        "  case_a 는 실패했으니 그대로 남아있다(부분실패가 조용히 삼켜지지 않고 case_a 만 스킵)",
        a_left)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행([5] round5 cleanup 격리 실측)", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
