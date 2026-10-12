# -*- coding: utf-8 -*-
"""스캔 263라운드 회귀 — manage.py(운영 CLI) 안전장치 결함 2건
   (운영 CLI 감사 Agent 조사로 발견, 독립 재검증 후 수정).

  [1] 되돌리기 어려운 4개 명령(go-live·restore·prune-personal·prune-orphans)
      전부 실행 화면 어디에도 "지금 어느 DB 파일에 적용되는지"가 안 보였다.
      db.py 의 유일한 운영DB 안전장치(_ENTRY 가 "test_"로 시작할 때만 발동)는
      manage.py 를 구조적으로 검사 대상에서 제외한다 — BOKGUON_DB_PATH 를 안
      정하면 조용히 실제 운영 파일(bokguon.db)에 연결되는데 확인 화면엔 표시가
      없었다. show_db_target() 을 만들어 네 명령 모두에 붙였다.

      ⚠ 참고(별도 조치 필요, 이 라운드는 미조치): prune-personal 만 형제
      (go-live·prune-orphans)와 반대로 "플래그 없으면 즉시 삭제"가 기본인데,
      deploy/windows_setup.ps1(주간 예약작업)·deploy/bootstrap.sh(cron) 둘 다
      플래그 없이 이 명령을 부른다 — 기본값을 뒤집으면 매주 도는 개인정보
      보호법 §21·§30 이행 예약이 조용히 빈 작업이 된다. 실행기준은 그대로
      두고, 어느 쪽으로 도는지만 화면·--help 에서 절대 헷갈릴 수 없게 했다.

  [2] go-live 의 데모 사건 자식행 정리 루프에서 dispatch_calls 삭제만
      except: pass 로 실패를 조용히 삼켰다 — 바로 아래 형제 루프(dispatches·
      field_agreements 등)는 실패를 _dead 리스트에 모아 warn() 으로 알리는데
      이 표만 빠져 있었다. 스키마가 바뀌어 이 DELETE 가 깨져도 화면은 "삭제
      완료"만 보여주고 지워진 데모 사건을 가리키는 고아 행이 남을 수 있었다.

      python test_scan_round263_fixes.py
"""
import io
import json
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
print("  스캔 263라운드 회귀 — 운영CLI DB표시 누락·go-live 고아행 침묵실패")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk("def show_db_target():" in MANAGE_SRC,
    "★★★★ 대상 DB 를 보여주는 공용 함수가 생겼다")
chk(MANAGE_SRC.count("show_db_target()") >= 5,  # 정의 1 + 호출 4곳
    "★★★★★ go-live·restore·prune-personal·prune-orphans 네 곳 모두에서 부른다",
    MANAGE_SRC.count("show_db_target()"))

i0 = MANAGE_SRC.index("def cmd_prune_personal(")
i1 = MANAGE_SRC.index("\ndef ", i0 + 10)
pp_body = MANAGE_SRC[i0:i1]
chk("show_db_target()" in pp_body, "STEP prune-personal 자신도 대상 DB 를 보여준다")
chk("플래그 없이 실행" in pp_body and "if not dry:" in pp_body,
    "★★★ 확인 없이 즉시 삭제되는 경우 명확한 경고가 뜬다")

chk("⚠ 위와 반대로 기본이 **즉시 삭제**다" in MANAGE_SRC,
    "★★★ --help 요약이 prune-personal 의 기본값이 형제와 반대임을 명시한다")

i2 = MANAGE_SRC.index('for _t in ("dispatch_calls",):')
i3 = MANAGE_SRC.index("\n            #  ⚠ 목록에서 뺀 셋", i2)
dc_body = MANAGE_SRC[i2:i3]
chk("_dead.append(_t)" in dc_body and "except sqlite3.Error:\n                    pass" not in dc_body,
    "★★★★★ dispatch_calls 삭제 실패도 이제 _dead 에 쌓여 조용히 안 삼켜진다")

# ============================================================
print("\n[2] 실행 — 실제 서브프로세스로 대상DB 표시 + 고아행 정리실패 알림 재현")
# ============================================================
_tmpdir = tempfile.mkdtemp(prefix="round263_")
db_path = os.path.join(_tmpdir, "verify.db")
run_path = os.path.join(_tmpdir, "run_golive.py")

RUN_SCRIPT = f'''# -*- coding: utf-8 -*-
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

#  데모 사건 하나 + 그 사건의 출동수배 하나 — go-live 의 ①단계(자식행 정리)가
#  실제로 dispatch_calls DELETE 를 시도하는 지점까지 도달하게 한다.
cid = conn.execute(
    "INSERT INTO cases(case_no,category,region,address,status,is_demo,created_at) "
    "VALUES('R263-DEMO','가드레일·방호울타리','서울','검증용','접수',1,?)", (now,)).lastrowid
did = conn.execute(
    "INSERT INTO dispatches(case_id,round,status,created_at) VALUES(?,1,'모집중',?)",
    (cid, now)).lastrowid
conn.commit()

#  dispatch_calls 자체를 지워 그 표를 겨눈 DELETE 가 반드시 실패하게 만든다
#  (스키마가 바뀌어 이 DELETE 가 깨지는 실제 상황을 가장 단순하게 재현하는 방법).
conn.execute("DROP TABLE dispatch_calls")
conn.commit()
conn.close()

import contextlib, io as _io
import manage as M
buf = _io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = M.cmd_go_live(["--yes"])
out = buf.getvalue()
print("===RC===" + str(rc))
print("===OUT_START===")
print(out)
print("===OUT_END===")
'''

try:
    with io.open(run_path, "w", encoding="utf-8") as f:
        f.write(RUN_SCRIPT)
    r = subprocess.run([sys.executable, "-u", run_path], capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=60, cwd=HERE)
    chk(r.returncode == 0, "STEP 스크립트가 예외 없이 끝났다(정리 실패가 크래시로 번지지 않는다)",
        r.stdout[-1500:] + "\n" + r.stderr[-1500:] if r.returncode else "")
    out = r.stdout
    if "===OUT_START===" in out:
        body = out.split("===OUT_START===", 1)[1].split("===OUT_END===", 1)[0]
        chk("대상 DB:" in body and db_path in body,
            "★★★★★ 실행 화면에 실제 대상 DB 경로가 그대로 찍힌다"
            "(고치기 전엔 이 줄 자체가 없었다)", body[:300])
        chk("정리하지 못한 표" in body and "dispatch_calls" in body,
            "★★★★★ dispatch_calls 삭제 실패가 화면에 명확히 보고된다"
            "(고치기 전엔 조용히 삼켜져 '삭제 완료'만 보였다)", body)
    else:
        chk(False, "★★★ 실행 출력 구간을 못 찾음", out[-1000:])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드263 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
