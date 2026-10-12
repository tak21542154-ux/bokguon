# -*- coding: utf-8 -*-
"""스캔 209라운드 회귀 — go-live(cmd_go_live)가 데모 원계정(협력사·보험사)의
로그인 수단만 지우고, 그 밑에 만들어진 하위계정(portal_users)은 손도 안 대던
결함.

  하위계정은 원계정과 완전히 별개인 자기 login_id·password_hash 를 갖는다
  (app.py _sub_create_impl). 인증 시(_portal_authenticate) 하위계정은 자기
  비밀번호로만 검증되고, 원계정의 login_id/password_hash 가 NULL인지는 절대
  보지 않는다 — 원계정 status 만 본다. 그런데 go-live 는 원계정 login_id·
  password_hash 만 NULL 로 지우고 status 는 그대로 '활성'으로 둔다(회사
  정보는 남긴다는 설계). 그래서 누군가 데모 계정(login_id='partner' 등,
  고정 비밀번호로 문서화돼 있다)으로 미리 로그인해 하위계정을 만들어 두면,
  go-live 뒤에도 그 하위계정은 원계정과 무관하게 영구히 로그인 가능한 채로
  남는다 — "데모 흔적 제거"를 약속하는 명령이 지속형 백도어를 하나도 못
  지우는 셈이다.

  (실측: 2026-08-29 현재 운영 DB portal_users 는 0행 — 아직 이 경로로
  하위계정이 만들어진 적은 없다. go-live 자체도 아직 실행된 적이 없어 지금이
  정확히 이 구멍을 막아야 할 시점이다.)

  go-live 실행 단계에서 원계정 login_id 가 아직 살아있는 순간(=지우기 직전)
  그 조직의 하위계정을 먼저 지우도록 고쳤고, 미리보기(--yes 없이)에도 몇 개나
  지워질지 승인 전에 보여 주게 했다(이 파일 docstring 의 "미리보기와 실행이
  같은 술어를 써야 한다" 원칙 — 187라운드가 이미 세운 원칙을 하위계정에도
  적용).

      python test_scan_round209_fixes.py
"""
import io
import os
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


MANAGE_SRC = read("manage.py")

print("=" * 72)
print("  스캔 209라운드 회귀 — go-live 가 데모 원계정 밑 하위계정을 안 지우던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = MANAGE_SRC.index("def cmd_go_live(argv):")
i1 = MANAGE_SRC.index("\ndef ", i0 + 1)
body = MANAGE_SRC[i0:i1]

chk('n_sub_preview += conn.execute(' in body,
    "★★★★ 미리보기가 딸린 하위계정 수를 승인 전에 센다")
#  ⚠ [라운드210] 원래는 "DELETE ... org_id IN (SELECT id FROM {table} ...)"
#    서브쿼리로 매번 login_id 로 다시 찾았다 — insurers 는 DEMO_TABLES 에도
#    있어 ②단계가 그 행을 먼저 지워 버리면 이 서브쿼리가 항상 0건이 되는
#    결함이 있었다(라운드210이 실측·수정). 지금은 트랜잭션 맨 앞에서 미리
#    잡아 둔 id(_demo_org_ids)를 쓴다 — 아래는 그 새 패턴을 확인한다.
_has_sub_delete = "DELETE FROM portal_users WHERE org_type=? AND org_id=?" in body
chk(_has_sub_delete, "★★★★ 실행 단계가 원계정과 함께 하위계정도 지운다"
    "(미리 잡아 둔 id 로 — login_id 재조회 아님)")
_has_early_capture = "_demo_org_ids = {}" in body and '_demo_org_ids[(_table, _nm)] = _row["id"]' in body
chk(_has_early_capture,
    "★★★★★ 핵심 — 조직 id 를 ②단계(DEMO_TABLES 일괄삭제)보다 먼저 잡아 둔다"
    "(고치기 전엔 ③단계에서 login_id 로 다시 찾았는데, insurers 는 ②가 그 "
    "행을 이미 지워 버려 하위계정 정리가 조용히 0건으로 무력화됐다)")
if _has_early_capture and _has_sub_delete:
    _i_capture = body.index("_demo_org_ids = {}")
    _i_bulk_delete = body.index('for t in DB.DEMO_TABLES:')
    _i_use = body.index("DELETE FROM portal_users WHERE org_type=? AND org_id=?")
    chk(_i_capture < _i_bulk_delete < _i_use,
        "★★★★★ 순서 확인 — id 를 잡아 두는 코드가 DEMO_TABLES 일괄삭제보다 "
        "먼저 실행되고, 하위계정 삭제는 그 뒤(미리 잡아 둔 id 사용)에 온다")
else:
    chk(False, "★★★ (건너뜀) 위 둘 중 하나가 없어 순서를 확인할 수 없음")

# ============================================================
print("\n[2] 실행 — 실제 DB(subprocess)로 미리보기·실행 둘 다 재현")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round209_")
#  ⚠ 미리보기·실행 두 서브프로세스가 **서로 다른** DB 파일을 써야 한다 —
#    같은 파일을 재사용하면 두 번째 시드가 첫 번째가 이미 넣은
#    login_id='partner' 와 UNIQUE 충돌을 낸다.
db_path_preview = os.path.join(_tmpdir, "preview.db")
db_path_run = os.path.join(_tmpdir, "run.db")
seed_path = os.path.join(_tmpdir, "seed_and_preview.py")
run_path = os.path.join(_tmpdir, "run_golive.py")


def make_seed(db_path):
    return f'''# -*- coding: utf-8 -*-
import os
import sys
os.environ["BOKGUON_DB_PATH"] = {db_path!r}
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, {HERE!r})

import db as DB
DB.init_db()
conn = DB.get_db()
now = DB.now()

#  실제 시드와 동일한 데모 원계정(login_id="partner"/"insurer") + 그 밑에
#  미리 만들어 둔 하위계정(portal_users) — "누군가 go-live 전에 데모 계정으로
#  로그인해 하위계정을 만들어 뒀다"는 시나리오 그대로.
pid = conn.execute(
    "INSERT INTO partners(name,partner_type,login_id,password_hash,status,created_at) "
    "VALUES('R209협력사','시공사','partner','x','활성',?)", (now,)).lastrowid
#  ⚠ is_demo=1 로 심는다 — 운영DB 의 데모 보험사 6곳 전부 실제로 이 값이다
#    (라운드210이 실측 확인). is_demo=0 으로 심으면 go-live ②단계(DEMO_TABLES
#    일괄삭제, insurers 포함)가 이 행을 안 건드려 라운드210이 고친 "②가 행을
#    먼저 지워 하위계정 정리가 무력화되는" 경로 자체가 재현되지 않는다.
iid = conn.execute(
    "INSERT INTO insurers(name,login_id,password_hash,status,is_demo,created_at) "
    "VALUES('R209보험사','insurer','x','활성',1,?)", (now,)).lastrowid
conn.execute(
    "INSERT INTO portal_users(org_type,org_id,login_id,password_hash,name,role,status,"
    "                          must_change_pw,created_at) "
    "VALUES('partner',?,'r209sub_p','x','R209하위(협력사)','중간관리자','활성',0,?)",
    (pid, now))
conn.execute(
    "INSERT INTO portal_users(org_type,org_id,login_id,password_hash,name,role,status,"
    "                          must_change_pw,created_at) "
    "VALUES('insurer',?,'r209sub_i','x','R209하위(보험사)','중간관리자','활성',0,?)",
    (iid, now))
conn.commit()
conn.close()
print(f"SEEDED pid={{pid}} iid={{iid}}")
'''

PREVIEW_SCRIPT = make_seed(db_path_preview) + '''
import contextlib, io as _io
import manage as M
buf = _io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = M.cmd_go_live([])
print("===RC===" + str(rc))
print("===OUT_START===")
print(buf.getvalue())
print("===OUT_END===")
'''

RUN_SCRIPT = make_seed(db_path_run) + '''
import manage as M
rc = M.cmd_go_live(["--yes"])
print("===RC===" + str(rc))

conn = DB.get_db()
p = dict(conn.execute("SELECT login_id, password_hash, status FROM partners WHERE id=?", (pid,)).fetchone())
#  ⚠ is_demo=1 인 보험사는 go-live ②단계(DEMO_TABLES 일괄삭제)가 행 자체를
#  통째로 지운다 — partners 와 달리 "크리덴셜만 NULL" 이 아니라 행이 아예
#  없어지는 게 정상(실제 운영DB 의 데모 보험사 6곳이 실제로 이렇게 처리됨).
i_row = conn.execute("SELECT login_id, password_hash, status FROM insurers WHERE id=?", (iid,)).fetchone()
i = dict(i_row) if i_row else None
sub_p = conn.execute("SELECT COUNT(*) n FROM portal_users WHERE login_id='r209sub_p'").fetchone()["n"]
sub_i = conn.execute("SELECT COUNT(*) n FROM portal_users WHERE login_id='r209sub_i'").fetchone()["n"]
import json
print("===RESULT===" + json.dumps({"partner": p, "insurer": i, "sub_p": sub_p, "sub_i": sub_i}))
'''

try:
    with io.open(seed_path, "w", encoding="utf-8") as f:
        f.write(PREVIEW_SCRIPT)
    r1 = subprocess.run([sys.executable, "-u", seed_path], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=60, cwd=HERE)
    chk(r1.returncode == 0, "STEP 미리보기 스크립트가 예외 없이 끝났다", r1.stderr[-800:] if r1.returncode else "")
    out1 = r1.stdout
    chk("딸린 하위계정(portal_users)" in out1 and "2개" in out1,
        "★★★★★ 핵심 — 미리보기(--yes 없음)가 '딸린 하위계정 2개'를 승인 전에 "
        "보여준다(고치기 전엔 이 줄 자체가 없어 하위계정 존재를 알 길이 없었다)",
        out1)

    with io.open(run_path, "w", encoding="utf-8") as f:
        f.write(RUN_SCRIPT)
    r2 = subprocess.run([sys.executable, "-u", run_path], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=60, cwd=HERE)
    chk(r2.returncode == 0, "STEP 실행(--yes) 스크립트가 예외 없이 끝났다",
        r2.stdout[-1500:] + "\n" + r2.stderr[-1500:] if r2.returncode else "")
    out2 = r2.stdout
    if "===RESULT===" in out2:
        import json as _json
        result = _json.loads(out2.split("===RESULT===", 1)[1].strip().splitlines()[0])
        chk(result["partner"]["login_id"] is None and result["partner"]["password_hash"] is None
            and result["partner"]["status"] == "활성",
            "★ (회귀 아님) 원계정(협력사) 로그인 수단은 그대로 지워지고 회사 정보(status)는 유지된다",
            result["partner"])
        chk(result["insurer"] is None,
            "★ (회귀 아님) is_demo=1 보험사는 go-live ②단계가 행 자체를 통째로 "
            "지운다(협력사와 달리 — 실제 운영DB 데모 보험사 6곳과 동일한 처리)",
            result["insurer"])
        chk(result["sub_p"] == 0,
            "★★★★★ 핵심 — 협력사 하위계정이 go-live 실행으로 함께 지워졌다"
            "(고치기 전엔 원계정만 지워지고 이 하위계정은 영구히 살아남았다)",
            result["sub_p"])
        chk(result["sub_i"] == 0,
            "★★★★★ 핵심 — 보험사 하위계정도 go-live 실행으로 함께 지워졌다",
            result["sub_i"])
    else:
        chk(False, "★★★ 실행 결과(JSON) 를 못 찾음", out2[-1000:])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드209 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
