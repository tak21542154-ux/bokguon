# -*- coding: utf-8 -*-
"""스캔 189라운드 회귀 — 두 결함.

  ① dispatch.py assign_dispatch(): 이미 한 업체가 도착해 사진을 확보한 사건
    (cases.dispatch_status=CS_PHOTO)에도 운영자가 다른 업체를 직접배정할 수
    있었다. open_dispatch() 는 152라운드에 이 조건을 막았는데(같은 이유:
    arrive() 가 first_partner_id 를 조건 없이 덮어쓰고, dispatch_id 없이 여는
    open_agreement() 는 가장 최근 도착 수배를 자동 선택한다), 직접배정 경로만
    빠져 있었다 — "선착순 한 곳만"이 이 경로에서만 뒤집혔다.

  ② static/form.js CONSENT_SPEC.insurer.items: 실제로 수집·저장되고
    (apply_insurer.html의 org_type, app.py insurer_leads.org_type) 공식
    개인정보처리방침(legal_docs.py)도 "필수" 항목으로 명시한 "기관 유형"이
    동의 고지 요약표에서 빠져 있었다 — 고지가 실제 수집 범위보다 적었다.

      python test_scan_round189_fixes.py
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
FORM_SRC = read("static/form.js")
LEGAL_SRC = read("legal_docs.py")
HTML_SRC = read("templates/apply_insurer.html")

print("=" * 72)
print("  스캔 189라운드 회귀 — 직접배정의 CS_PHOTO 가드 누락 · 동의고지 항목 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = DSP_SRC.index("def assign_dispatch(")
i1 = DSP_SRC.index("\ndef ", i0 + 1)
assign_body = DSP_SRC[i0:i1]
chk("SELECT status, partner_id, case_no, dispatch_status FROM cases" in assign_body,
    "★★★★ assign_dispatch 가 dispatch_status 도 함께 조회한다"
    "(open_dispatch·arrive 는 이미 하는데 직접배정만 안 했다)")
chk("cs[3] == CS_PHOTO" in assign_body,
    "★★★★ 이미 사진이 확보된 사건(CS_PHOTO)에는 직접배정을 막는다"
    "(open_dispatch 313행과 같은 조건)")

chk("기관 유형" in FORM_SRC.split("CONSENT_SPEC")[1].split("partner:")[0],
    "★★★ CONSENT_SPEC.insurer.items 에 '기관 유형'이 포함된다"
    "(실제 수집·저장되고 공식 방침도 필수로 명시하는데 동의 고지에만 없었다)")
chk('name="org_type"' in HTML_SRC, "(참고) apply_insurer.html 이 실제로 org_type 을 받는다 — 죽은 필드 아님")
chk("기관 유형" in LEGAL_SRC, "(참고) 공식 개인정보처리방침도 '기관 유형'을 필수 항목으로 명시한다")

# ============================================================
print("\n[2] 실행 — ① 이미 도착한 사건에 제3업체를 직접배정하면 거부되고, "
      "정상 사건(사진확보 전)에는 여전히 배정된다")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round189_")
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
    "INSERT INTO partners(id, name, status, license_status, region) "
    "VALUES(9101, 'R189먼저도착', '활성', '확인됨', '서울')")
conn.execute(
    "INSERT INTO partners(id, name, status, license_status, region) "
    "VALUES(9102, 'R189나중배정', '활성', '확인됨', '서울')")

#  ① 이미 9101 이 도착해 사진을 확보한 사건 — cases.status/partner_id 는 1차 합의
#  승인 전까지 그대로라 '접수'/NULL 인 채로, dispatch_status 만 CS_PHOTO 다.
conn.execute(
    "INSERT INTO cases(id, case_no, category, region, status, dispatch_status, "
    "                   first_partner_id, first_photo_at, created_at) "
    "VALUES(9101, 'R189-001', '유리', '서울', '접수', '사진확보', 9101, ?, ?)", (now, now))
conn.execute(
    "INSERT INTO dispatches(id, case_id, round, status, claimed_partner_id, "
    "                        claimed_name, arrived_at, created_at) "
    "VALUES(9101, 9101, 1, '도착', 9101, 'R189먼저도착', ?, ?)", (now, now))

#  ② 아직 아무도 도착하지 않은 정상 사건 — 회귀 없음 확인용.
conn.execute(
    "INSERT INTO cases(id, case_no, category, region, status, created_at) "
    "VALUES(9102, 'R189-002', '유리', '서울', '접수', ?)", (now,))
conn.commit()

ok1, msg1, did1 = DSP.assign_dispatch(conn, 9101, 9102, "현장 확인 결과 재배정 시도", by="tester")
after1 = conn.execute("SELECT first_partner_id, dispatch_status FROM cases WHERE id=9101").fetchone()
n_disp_after1 = conn.execute("SELECT COUNT(*) n FROM dispatches WHERE case_id=9101").fetchone()["n"]

ok2, msg2, did2 = DSP.assign_dispatch(conn, 9102, 9102, "야간이라 직접 배정", by="tester")

print("===R1===" + repr((ok1, msg1, did1, after1["first_partner_id"], after1["dispatch_status"], n_disp_after1)))
print("===R2===" + repr((ok2, msg2)))
'''

with io.open(seed_path, "w", encoding="utf-8") as f:
    f.write(SEED_SCRIPT)

try:
    result = subprocess.run([PY, "-u", seed_path], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=60)
    out = result.stdout
    r1_line = next((l for l in out.splitlines() if l.startswith("===R1===")), None)
    r2_line = next((l for l in out.splitlines() if l.startswith("===R2===")), None)
    if not r1_line or not r2_line:
        chk(False, "★★★ 라운드189 [2] 준비 스크립트 실행",
            f"exit={result.returncode}\nSTDOUT:\n{out}\nSTDERR:\n{result.stderr}")
    else:
        ok1, msg1, did1, fpid_after, dstat_after, n_disp_after1 = eval(r1_line[len("===R1==="):])
        ok2, msg2 = eval(r2_line[len("===R2==="):])

        chk(ok1 is False,
            "★★★★ 이미 도착·사진확보된 사건(9101)에 제3업체(9102) 직접배정이 거부된다"
            "(고치기 전엔 성공했다)", (ok1, msg1))
        chk(fpid_after == 9101,
            "★★★★ 거부된 뒤에도 first_partner_id 는 먼저 도착한 9101 그대로다"
            "(고치기 전엔 arrive() 가 나중 업체로 덮어써 open_agreement 가 엉뚱한 "
            "업체 견적을 골랐다)", fpid_after)
        chk(dstat_after == "사진확보",
            "★★★ 거부된 뒤에도 dispatch_status 는 그대로 '사진확보'다", dstat_after)
        chk(n_disp_after1 == 1,
            "★★★ 거부되면 새 dispatches 행이 생기지 않는다(기존 1건 그대로)", n_disp_after1)

        chk(ok2 is True,
            "아직 아무도 도착하지 않은 정상 사건(9102)에는 여전히 직접배정이 된다"
            "(회귀 없음 — 이 함수의 원래 존재 이유)", (ok2, msg2))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드189 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
