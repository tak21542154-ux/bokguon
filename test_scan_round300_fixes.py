# -*- coding: utf-8 -*-
"""스캔 300라운드 회귀 — ingest_partners.py·partner_accounts.py 결함 3건,
   이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견(스스로 첫 가설을 실측으로
   뒤집고 두 가지 전제(ingest_partners.py 는 자동배포에 안 물려있음·
   WORK_MAJORS 는 major 의 진짜 enum 이 아님)도 함께 바로잡은 보고) —
   동시성(기존 test_scan_round270_fixes.py 가 이미 실측 검증)·아이디 유일성
   백스톱(UNIQUE 제약)·major enum 정확성·status/partner_type 초기값·
   is_demo 격리(partners 엔 그 컬럼 자체가 없음)·평문 비밀번호 로그유출은
   실측 결과 전부 클린.

   ① ingest_partners.norm_name() 이 전각 괄호(（）U+FF08/09)를 반각(())과
      다르게 취급해, "(주)한빛건설"과 "（주）한빛건설"이 서로 다른 중복판정
      키가 됐다 — 다음 리서치 배치에서 이미 있는 회사가 다시 들어갈 수
      있었다(실측: 현재 398개사엔 전각 괄호가 없어 아직 발현 전, 미래
      배치를 겨냥한 결함). 전각→반각 변환을 먼저 거치도록 수정, 실제
      398개사 데이터로 새 충돌이 0건임을 재확인(서로 다른 회사를 잘못
      합치지 않음).
   ② ingest_partners.py 가 partners_seed.json 을 임시파일 경유 없이 바로
      덮어썼다 — 쓰는 도중 끊기면(디스크 꽉 참·Ctrl+C) 파일이 잘린 채
      남고, db.py 의 시드 로더는 json.load() 실패를 조용히 빈 목록으로
      삼켜(실측: 잘린 파일로 새 DB 를 만들면 협력사 0곳으로 조용히 끝남)
      다음 신규 배포가 경고 없이 협력사 전체 없이 뜰 수 있었다. 임시파일에
      다 쓴 뒤 os.replace() 로 원자적으로 바꿔치기하도록 수정.
   ③ partner_accounts.py 의 CSV 저장·감사로그(DB.log)가 전부 배치가
      끝까지 돈 뒤에만 한 번 실행됐다 — 그런데 각 업체의 UPDATE 는
      SAVEPOINT 를 감싸는 바깥 BEGIN 이 없어 RELEASE 순간 이미 개별
      커밋된다(SQLite 특성). 배치 중간에 죽으면(운영자의 Ctrl+C — 이
      파일 자신의 "안전 원칙"이 실제로 벌어지는 일로 이미 인정) 앞쪽
      업체들은 DB 엔 로그인 계정이 실제로 만들어졌는데 그 임시 비밀번호가
      화면·CSV·감사로그 어디에도 안 남아(비밀번호는 해시라 복구 불가)
      로그인이 영원히 불가능한 죽은 계정이 된다(실측: 3번째에서 강제로
      죽이면 앞 2곳이 정확히 이 상태로 남음). CSV·감사로그를 업체 처리
      직후(UPDATE 와 같은 자리)로 옮겨 셋의 시점을 맞췄다.

      python test_scan_round300_fixes.py
"""
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


INGEST_SRC = read("ingest_partners.py")
ACCT_SRC = read("partner_accounts.py")

print("=" * 72)
print("  스캔 300라운드 회귀 — ingest_partners/partner_accounts 결함 3건")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
chk('str.maketrans("（）", "()")' in INGEST_SRC,
    "★★★ norm_name() 이 전각 괄호를 반각으로 먼저 바꾼다")
chk('tmp = SEED + ".tmp"' in INGEST_SRC and "os.replace(tmp, SEED)" in INGEST_SRC,
    "★★★ 시드 저장이 임시파일 경유 원자적 교체로 바뀌었다")
chk('with open(SEED, "w", encoding="utf-8") as f:\n        json.dump(existing' not in INGEST_SRC,
    "★★ 옛 직접 덮어쓰기 코드가 더는 없다(교체 누락 방지)")

#  ⚠ 앵커(\n    if csv_fh:)가 사라진 상태(예: 결함 되돌리기)에서 .index() 를
#    바로 쓰면 예외로 죽어 이 파일의 나머지 검사·[2]~[4] 실행 단계를 통째로
#    막는다(라운드297 에서 겪은 것과 같은 함정) — in 으로 먼저 확인한다.
if "for r in rows:" in ACCT_SRC and "\n    if csv_fh:" in ACCT_SRC:
    _loop_body = ACCT_SRC[ACCT_SRC.index("for r in rows:"):ACCT_SRC.index("\n    if csv_fh:")]
else:
    _loop_body = ""
chk('DB.log(conn, "정비도구", "협력사 계정 발급"' in _loop_body,
    "★★★ 감사로그가 업체 처리 루프 **안**으로 들어왔다(고치기 전엔 루프 밖)")
chk(_loop_body.count("conn.commit()") >= 1,
    "★★ 루프 안에서 즉시 커밋한다(업체 하나 몫만이라도 확실히 남김)")
chk("csv_writer.writerow(row_out)" in _loop_body and "csv_fh.flush()" in _loop_body,
    "★★★ CSV 도 업체 처리 즉시 한 줄씩 쓰고 flush 한다(고치기 전엔 배치 끝에 한 번)")
chk("if a.out and made and not a.dry:\n        with open(a.out" not in ACCT_SRC,
    "★★ 배치 끝에서 다시 통째로 쓰던 옛 코드가 없다(중복기록 방지)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — norm_name 이 전각/반각 괄호를 실제로 같게 본다(진짜 함수 호출)")
# ──────────────────────────────────────────────────────────────
sys.path.insert(0, HERE)
try:
    import ingest_partners as IP

    chk(IP.norm_name("(주)한빛건설") == IP.norm_name("（주）한빛건설"),
        "★★★ '(주)'와 '（주）'가 이제 같은 중복판정 키를 낸다"
        "(고치기 전엔 서로 달라 같은 회사가 두 번 들어갈 수 있었다)",
        (IP.norm_name("(주)한빛건설"), IP.norm_name("（주）한빛건설")))
    chk(IP.norm_name("삼성물산(주)") == IP.norm_name("삼성물산（주）"),
        "★★ 접미사 위치에서도 동일하게 맞는다", None)

    # 실제 398개사 데이터로 이 정규화가 서로 다른 회사를 잘못 합치지 않는지 재확인
    seed_path = os.path.join(HERE, "data", "partners_seed.json")
    with io.open(seed_path, encoding="utf-8") as f:
        real_companies = json.load(f)
    keys = [IP.norm_name(p.get("name")) for p in real_companies]
    chk(len(keys) == len(set(keys)),
        f"★★★ 실제 {len(keys)}개사 데이터에서 새 정규화로 새 충돌이 0건이다"
        "(서로 다른 진짜 회사를 잘못 합치지 않음, 회귀 없음)",
        len(keys) - len(set(keys)))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드300 [2] norm_name 실측", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 시드 저장이 실제로 원자적인가(쓰기 중단을 실제로 흉내냄)")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round300_")
try:
    fake_seed = os.path.join(_tmpdir, "partners_seed.json")
    original_content = [{"name": "기존업체A", "partner_type": "시공사", "major": "누수·배관·설비"}]
    io.open(fake_seed, "w", encoding="utf-8").write(json.dumps(original_content, ensure_ascii=False))

    journal = os.path.join(_tmpdir, "journal.jsonl")
    io.open(journal, "w", encoding="utf-8").write(json.dumps({
        "type": "result",
        "result": {"companies": [
            {"name": "신규업체B", "partner_type": "시공사", "major": "누수·배관·설비",
             "source_url": "http://example-src.invalid/b"},
        ]},
    }, ensure_ascii=False) + "\n")

    orig_seed_attr = IP.SEED
    orig_dump = json.dump
    try:
        IP.SEED = fake_seed

        def _boom(*a, **kw):
            raise RuntimeError("강제 중단(쓰기 도중 프로세스가 죽는 상황 흉내)")
        json.dump = _boom
        try:
            old_argv = sys.argv
            sys.argv = ["ingest_partners.py", journal]
            try:
                IP.main()
            except RuntimeError:
                pass
            finally:
                sys.argv = old_argv
        finally:
            json.dump = orig_dump

        chk(not os.path.exists(fake_seed + ".tmp"),
            "★ 강제 중단 뒤 임시파일이 남지 않는다(있어도 무해하지만 청결)",
            os.path.exists(fake_seed + ".tmp"))
        with io.open(fake_seed, encoding="utf-8") as f:
            after_crash = json.load(f)
        chk(after_crash == original_content,
            "★★★ 쓰기 도중 강제로 끊겨도 원본 시드 파일이 손상되지 않고 그대로 남는다"
            "(고치기 전엔 이 자리에서 파일이 잘린 채 남아, 다음 배포가 협력사 0곳으로 조용히 끝났다)",
            after_crash)
    finally:
        IP.SEED = orig_seed_attr
        json.dump = orig_dump
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드300 [3] 원자적 쓰기 실측", f"{type(e).__name__} {e}")
finally:
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

# ══════════════════════════════════════════════════════════════
print("\n[4] 실행 — partner_accounts.py 가 배치 중단에도 처리분을 놓치지 않는가"
      "(격리 DB, 실제 서브프로세스, 강제 중단 흉내)")
# ──────────────────────────────────────────────────────────────
_tmpdir2 = tempfile.mkdtemp(prefix="round300_acct_")
try:
    _dbpath = os.path.join(_tmpdir2, "verify.db")
    #  ⚠ db 모듈은 이 프로세스에서 아직 한 번도 안 불려 왔더라도, import 시점
    #    가드(db.py:32-44)가 os.environ 을 그 순간 읽는다 — 실제 os.environ
    #    을 먼저 채워야지, 서브프로세스용 _env 딕셔너리만 만들어 두면 이
    #    프로세스 자신의 import db 는 여전히 기본(운영) 경로를 본다(라운드299
    #    에서 겪은 것과 같은 함정).
    os.environ["BOKGUON_DB_PATH"] = _dbpath
    os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir2, "uploads")
    os.environ["BOKGUON_ENV"] = "dev"
    os.environ["BOKGUON_SEED_DEMO"] = "0"
    _env = dict(os.environ)

    import db as DB2
    DB2.DB_PATH = _dbpath
    DB2.init_db()
    conn = DB2.get_db()
    for i in range(3):
        conn.execute(
            "INSERT INTO partners(name,partner_type,status,biz_no,region,major,rating,jobs_done) "
            "VALUES(?,'시행사','활성',?,'서울','누수·배관·설비',0,0)",
            (f"R300-업체{i}", f"111-11-{100000+i}"))
    conn.commit()
    conn.close()

    #  ⚠ 실제 partner_accounts.py 를 그대로 서브프로세스로 돌리되, 3번째
    #    업체의 make_login_id() 를 강제로 실패시켜 배치 중단을 실측 재현한다
    #    (수정자체는 안 건드리고, sitecustomize 류 몽키패치를 별도 러너로 주입).
    runner = os.path.join(_tmpdir2, "run_crash.py")
    io.open(runner, "w", encoding="utf-8").write(
        "import sys; sys.path.insert(0, r'" + HERE + "')\n"
        "import partner_accounts as PA\n"
        "_orig = PA.make_login_id\n"
        "_calls = [0]\n"
        "def _patched(conn, row, taken):\n"
        "    _calls[0] += 1\n"
        "    if _calls[0] == 3:\n"
        "        raise RuntimeError('강제중단(3번째 업체에서 실행이 끊기는 상황 흉내)')\n"
        "    return _orig(conn, row, taken)\n"
        "PA.make_login_id = _patched\n"
        "sys.argv = ['partner_accounts.py', '--type', '전체', '--limit', '3', "
        "'--out', r'" + os.path.join(_tmpdir2, "out.csv") + "']\n"
        "PA.main()\n"
    )
    r = subprocess.run([PY, "-u", runner], cwd=HERE, env=_env,
                        capture_output=True, text=True, encoding="utf-8", timeout=30)
    chk(r.returncode != 0,
        "STEP 3번째 업체에서 실제로 강제 중단됐다(전제 확인 — RuntimeError 로 죽음)",
        (r.returncode, (r.stdout + r.stderr)[-500:]))

    import sqlite3
    conn = sqlite3.connect(_dbpath)
    conn.row_factory = sqlite3.Row
    issued = conn.execute(
        "SELECT COUNT(*) FROM partners WHERE COALESCE(login_id,'')<>''").fetchone()[0]
    logs = conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE action='협력사 계정 발급'").fetchone()[0]
    conn.close()
    chk(issued == 2,
        "STEP 실제로 앞의 2곳은 DB 에 로그인 계정이 durably 발급돼 있다(전제 확인)",
        issued)
    chk(logs == 2,
        "★★★ 감사로그(activity_log)에 발급된 2곳이 각각 남아 있다"
        "(고치기 전엔 배치가 안 끝나 감사로그가 0건이었다)", logs)

    outcsv = os.path.join(_tmpdir2, "out.csv")
    chk(os.path.exists(outcsv), "STEP CSV 파일 자체가 만들어졌다(고치기 전엔 배치 끝에만 생겨 아예 없었다)",
        os.path.exists(outcsv))
    if os.path.exists(outcsv):
        csv_lines = [ln for ln in io.open(outcsv, encoding="utf-8-sig").read().splitlines() if ln.strip()]
        chk(len(csv_lines) == 3,  # 헤더 1 + 데이터 2행
            "★★★ CSV 에 헤더+발급된 2곳(총 3줄)이 정확히 들어 있다"
            "(고치기 전엔 배치 미완료로 파일 자체가 없어 임시 비밀번호가 영원히 사라졌다)",
            csv_lines)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드300 [4] partner_accounts.py 배치중단 실측", f"{type(e).__name__} {e}")
finally:
    for k in ("BOKGUON_DB_PATH", "BOKGUON_UPLOAD_DIR", "BOKGUON_ENV", "BOKGUON_SEED_DEMO"):
        os.environ.pop(k, None)
    import shutil
    shutil.rmtree(_tmpdir2, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
