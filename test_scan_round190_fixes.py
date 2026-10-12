# -*- coding: utf-8 -*-
"""스캔 190라운드 회귀 — dispatch.py close_no_repair() 가 검토중인 1차 합의
(field_agreements)를 정리하지 않던 결함.

  형제 경로(2차 경매 개시, app.py api_case_open_auction)는 "검토중인 1차 합의를
  여기서 함께 닫는다"며 명시적으로 처리하는데(사건이 다른 절차로 넘어가면
  낡은 합의가 보험사 대기열에 남아 나중에 승인되면 시공사·금액이 통째로
  덮어써지기 때문), 미수선 종결(close_no_repair)만 이 정리가 빠져 있었다.

  실제 위험: 미수선종결은 사건 상태를 벗어나(보험사 대기열 조건 `status='접수'`가
  거짓이 되어) 낡은 합의를 잠시 가릴 뿐이다. 되돌리기(undo-no-repair)가 사건을
  다시 '접수'로 되돌리면 그 낡은 합의가 대기열에 부활하고, 보험사가 그걸 승인하면
  settle_agreement 의 재확인(사건상태·업체상태·면허)이 전부 통과해 낡은 견적
  그대로 낙찰이 확정된다.

      python test_scan_round190_fixes.py
"""
import io
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


DSP_SRC = read("dispatch.py")

print("=" * 72)
print("  스캔 190라운드 회귀 — 미수선종결이 검토중 1차 합의를 안 닫던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = DSP_SRC.index("def close_no_repair(")
i1 = DSP_SRC.index("\ndef ", i0 + 1)
body = DSP_SRC[i0:i1]
chk("UPDATE field_agreements" in body,
    "★★★★ close_no_repair 가 field_agreements 를 건드린다"
    "(고치기 전엔 이 함수 전체에서 field_agreements 참조가 0건이었다)")
#  ⚠ AG_REVIEW/AG_BROKEN 상수 자체는 close_no_repair 와 open_agreement 사이의
#    모듈 전역 블록에 있어(함수 안이 아니다) "다음 def 까지" 로 자르면 항상
#    같이 딸려 온다 — 그 존재 여부로는 이 함수의 수정 여부를 못 가른다.
#    reject_reason 문구는 이 수정이 새로 넣은 리터럴이라 정확하다.
chk("reject_reason='미수선 종결로 자동 종료'" in body,
    "★★★★ 검토중이던 합의를 결렬로 닫으며 사유를 남긴다"
    "(api_case_open_auction 의 2차 경매 개시와 같은 패턴)")

# ============================================================
print("\n[2] 실행 — 도착·실견적 제출 뒤 미수선 종결되면 검토중 합의가 함께 닫히고, "
      "되돌린 뒤에도 보험사 승인 대기열에 다시 뜨지 않는다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round190_")
db_path = os.path.join(_tmpdir, "verify.db")
seed_path = os.path.join(_tmpdir, "seed_and_run.py")

SEED_SCRIPT = f'''# -*- coding: utf-8 -*-
import os
import sys

os.environ["BOKGUON_DB_PATH"] = {db_path!r}
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, {HERE!r})

import db as DB
DB.init_db()
import dispatch as DSP

conn = DB.get_db()
now = DB.now()

conn.execute(
    "INSERT INTO insurers(id, name) VALUES(9201, 'R190보험')")
conn.execute(
    "INSERT INTO partners(id, name, status, license_status, region) "
    "VALUES(9201, 'R190출동업체', '활성', '확인됨', '서울')")
conn.execute(
    "INSERT INTO cases(id, case_no, insurer_id, category, region, status, created_at) "
    "VALUES(9201, 'R190-001', 9201, '유리', '서울', '접수', ?)", (now,))
conn.execute(
    "INSERT INTO dispatches(id, case_id, round, status, claimed_partner_id, "
    "                        claimed_name, field_estimate, arrived_at, created_at) "
    "VALUES(9201, 9201, 1, '도착', 9201, 'R190출동업체', 3000000, ?, ?)", (now, now))
conn.commit()

#  출동 업체의 실견적을 놓고 1차 합의 검토를 연다(open_agreement) — 보험사
#  응답 전(검토중)인 채로 놔둔다.
agid = DSP.open_agreement(conn, 9201, dispatch_id=9201)
assert agid, "1차 합의 생성 실패 — 테스트 준비 오류"

before = conn.execute("SELECT status FROM field_agreements WHERE id=?", (agid,)).fetchone()["status"]

#  현장 확인 결과 수선 불필요로 판명 — 미수선 종결.
ok1, msg1 = DSP.close_no_repair(conn, 9201, 9201, "파손이 경미해 수선 불필요", by="테스트")

after = conn.execute("SELECT status FROM field_agreements WHERE id=?", (agid,)).fetchone()["status"]

#  운영자가 되돌린다(undo-no-repair 의 핵심 UPDATE 를 그대로 재현).
conn.execute(
    "UPDATE cases SET status='접수', award_route=NULL, no_repair_reason=NULL, "
    "                  dispatch_status=NULL WHERE id=9201")
conn.commit()

#  보험사 승인 대기열 쿼리(app.py fa_wait, 3355행)의 핵심 조건을 그대로 재현 —
#  case.status='접수' AND partner_id IS NULL AND f.status='검토중'.
requeued = conn.execute(
    """SELECT COUNT(*) n FROM field_agreements f JOIN cases c ON c.id = f.case_id
        WHERE f.id=? AND f.status='검토중' AND c.status='접수' AND c.partner_id IS NULL""",
    (agid,)).fetchone()["n"]

print("===R===" + repr((before, ok1, msg1, after, requeued)))
'''

with io.open(seed_path, "w", encoding="utf-8") as f:
    f.write(SEED_SCRIPT)

try:
    result = subprocess.run([PY, "-u", seed_path], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=60)
    out = result.stdout
    r_line = next((l for l in out.splitlines() if l.startswith("===R===")), None)
    if not r_line:
        chk(False, "★★★ 라운드190 [2] 준비 스크립트 실행",
            f"exit={result.returncode}\nSTDOUT:\n{out}\nSTDERR:\n{result.stderr}")
    else:
        before, ok1, msg1, after, requeued = eval(r_line[len("===R==="):])

        chk(before == "검토중", "준비: 종결 전엔 1차 합의가 검토중이다", before)
        chk(ok1 is True, "미수선 종결 자체는 정상 성공한다(회귀 없음)", (ok1, msg1))
        chk(after == "결렬",
            "★★★★ 미수선 종결과 동시에 검토중이던 1차 합의가 결렬로 닫힌다"
            "(고치기 전엔 '검토중' 그대로 남았다)", after)
        chk(requeued == 0,
            "★★★★ 사건을 다시 '접수'로 되돌려도 이 낡은 합의는 보험사 승인 "
            "대기열 조건을 더는 만족하지 않는다(고치기 전엔 여기서 부활해 "
            "낡은 견적이 승인 가능한 상태로 재노출됐다)", requeued)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드190 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
