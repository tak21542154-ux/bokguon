# -*- coding: utf-8 -*-
"""스캔 187라운드 회귀 — go-live 미리보기(cmd_go_live, --yes 없음)가 실제 삭제
범위를 과소 보고하던 결함.

  _demo_counts()/extra 는 photos·settlements·defects 세 표만 사건 id 로 세고
  나머지 — dispatches·field_agreements·change_orders·work_lots·bid_events·
  est_outcome·damage_reads·schedule_events·contract_gate_log(모두 ①단계가
  case_id 로 실제로 지운다) 그리고 bids·ai_reviews·defect_photos·dispatch_calls
  (2단계 경로로 실제로 지운다) — 는 실행이 지우는데 미리보기 화면엔 아예
  나타나지 않았다. 게다가 해피콜 전량삭제·로그인시도 전량초기화·협력사
  평판(rating·jobs_done·win_rate) 초기화는 **실행이 끝난 뒤** ok() 로만
  알렸다 — 승인 버튼을 누르기 전에 알아야 할 내용이 사후 보고로만 나온 것이다.

  되돌릴 수 없는 삭제를 사람이 보고 승인 여부를 정하는 화면이 실제보다
  적게 보이면, 이 함수 자신의 docstring이 말하듯 "가장 나쁜 종류의 거짓말"이다.

      python test_scan_round187_fixes.py
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


MANAGE_SRC = read("manage.py")

print("=" * 72)
print("  스캔 187라운드 회귀 — go-live 미리보기의 과소보고")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = MANAGE_SRC.index("def cmd_go_live(argv):")
i1 = MANAGE_SRC.index("\ndef ", i0 + 1)
body = MANAGE_SRC[i0:i1]

chk("for t in CASE_CHILD_TABLES:" in body,
    "★★★★ 미리보기가 CASE_CHILD_TABLES(정리·prune-orphans 와 같은 목록)로 "
    "case_id 자식표를 전부 센다(고치기 전엔 photos·settlements·defects 세 표뿐)")
chk('("photos", "case_id"), ("settlements", "case_id"), ("defects", "case_id")' not in body,
    "★★★★ 옛 3표 하드코딩이 사라졌다")
chk('extra["bids"]' in body and 'extra["ai_reviews"]' in body
    and 'extra["defect_photos"]' in body and 'extra["dispatch_calls"]' in body,
    "★★★ case_id 가 없어 2단계로만 사건에 닿는 표(bids·ai_reviews·"
    "defect_photos·dispatch_calls)도 센다")
chk("not counts and not extra and not accounts" in body,
    "★★★ '정리할 데모 데이터 없음' 조기 반환이 extra 도 함께 본다"
    "(유령 사건만 있는 DB 를 '없음'으로 오판하던 결함)")
chk('_hc = conn.execute("SELECT COUNT(*) n FROM happy_calls")' in body,
    "★★★ 해피콜 전량삭제 건수를 승인 **전에** 미리 알린다"
    "(고치기 전엔 실행 후 ok() 로만 알렸다)")
chk('_la = conn.execute("SELECT COUNT(*) n FROM login_attempts")' in body,
    "★★★ 로그인시도 전량초기화 건수를 승인 전에 미리 알린다")
chk("rating·jobs_done" in body and "win_rate" in body,
    "★★★★ 협력사 평판(rating·jobs_done·win_rate) 초기화를 승인 전 경고문에 명시한다"
    "(고치기 전엔 실행이 끝난 뒤 ok() 로만 알렸다)")

# ============================================================
print("\n[2] 실행 — 표식 없는 유령 사건(데모 발주처 소속인데 is_demo=0)에 딸린 "
      "자식행이 미리보기에 잡히는지 재현")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round187_")
db_path = os.path.join(_tmpdir, "verify.db")
seed_path = os.path.join(_tmpdir, "seed_and_run.py")

SEED_SCRIPT = f'''# -*- coding: utf-8 -*-
import contextlib
import io
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

#  데모 보험사 + "유령" 사건(is_demo=0 인데 데모 보험사 소속 — 표식이 안 붙은 검증사건).
conn.execute(
    "INSERT INTO insurers(id, name, is_demo) VALUES(9001, 'R187데모보험', 1)")
conn.execute(
    "INSERT INTO cases(id, case_no, insurer_id, category, region, status, is_demo, created_at) "
    "VALUES(9001, 'R187-GHOST-001', 9001, '유리', '서울', '접수', 0, ?)", (now,))

#  ①단계가 case_id 로 직접 지우는 자식표 대표 — dispatches(is_demo 컬럼은 있지만
#  이 행엔 안 세웠다 = 표식 경로가 아니라 case_id 경로로만 잡혀야 한다).
conn.execute(
    "INSERT INTO dispatches(id, case_id, status, created_at) VALUES(9001, 9001, '모집중', ?)",
    (now,))
#  is_demo 컬럼이 있는데도 옛 코드에선 하드코딩 3표에 없어 안 잡히던 표.
conn.execute(
    "INSERT INTO schedule_events(id, title, event_date, case_id, created_at) "
    "VALUES(9001, 'R187점검', '2026-08-28', 9001, ?)", (now,))
#  is_demo 컬럼 자체가 없어 DEMO_TABLES 루프로도 절대 못 잡는 표.
conn.execute(
    "INSERT INTO contract_gate_log(id, case_id, case_no, code, ok) "
    "VALUES(9001, 9001, 'R187-GHOST-001', '도급가능', 1)")
#  case_id 가 없어 auctions 를 거쳐야만 사건에 닿는 2단계 표(에이전트가 지목한 대표 사례).
conn.execute(
    "INSERT INTO auctions(id, case_id, status, created_at) VALUES(9001, 9001, '진행', ?)", (now,))
conn.execute(
    "INSERT INTO bids(id, auction_id, partner_name, amount, days, created_at) "
    "VALUES(9001, 9001, 'R187업체', 1000000, 5, ?)", (now,))
#  데모 여부와 무관하게 전량 삭제/초기화되는 표 — 승인 전 공시 대상.
conn.execute(
    "INSERT INTO happy_calls(id, case_id, score, created_at) VALUES(9001, 9001, 5, ?)", (now,))
conn.execute(
    "INSERT INTO login_attempts(id, username, success, created_at) "
    "VALUES(9001, 'r187test', 0, ?)", (now,))
conn.commit()
conn.close()

import manage as M
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = M.cmd_go_live([])
print("===RC===" + str(rc))
print("===OUT_START===")
print(buf.getvalue())
print("===OUT_END===")
'''

with io.open(seed_path, "w", encoding="utf-8") as f:
    f.write(SEED_SCRIPT)

try:
    result = subprocess.run([PY, "-u", seed_path], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=60)
    out = result.stdout
    if result.returncode != 0 and "===OUT_START===" not in out:
        chk(False, "★★★ 라운드187 [2] 준비 스크립트 실행",
            f"exit={result.returncode}\nSTDOUT:\n{out}\nSTDERR:\n{result.stderr}")
    else:
        rc_line = next((l for l in out.splitlines() if l.startswith("===RC===")), "===RC===?")
        preview_rc = rc_line.replace("===RC===", "").strip()
        preview_out = out.split("===OUT_START===", 1)[1].split("===OUT_END===", 1)[0] \
            if "===OUT_START===" in out else ""

        chk(preview_rc == "1",
            "미리보기는 '실행하려면 --yes' 를 요구하며 종료코드 1을 돌려준다"
            "(데이터가 있는데 0으로 '없음'을 찍으면 회귀)", f"rc={preview_rc}")

        for tbl, label in (("dispatches", "① case_id 직접 자식표(is_demo 표식 없이도 "
                                            "case_id 만으로 잡혀야 한다)"),
                            ("schedule_events", "① case_id 직접 자식표(is_demo 컬럼은 있지만 "
                                                 "옛 3표 하드코딩엔 없었다)"),
                            ("contract_gate_log", "① case_id 직접 자식표(is_demo 컬럼 자체가 "
                                                    "없어 DEMO_TABLES 루프로도 못 잡는다)"),
                            ("bids", "2단계(auction_id→case_id) 자식표 — 에이전트가 지목한 "
                                     "대표 과소보고 사례")):
            line = next((l for l in preview_out.splitlines()
                         if l.strip().startswith(f"· {tbl} ") or l.strip().startswith(f"· {tbl}\t")
                         or (tbl in l and "딸림" in l)), None)
            chk(line is not None and "딸림" in (line or ""),
                f"★★★★ 유령 사건에 딸린 {tbl} 1건이 미리보기에 나타난다 — {label}",
                f"찾은 줄: {line!r}\n전체 출력:\n{preview_out}")

        chk("happy_calls" in preview_out and "전량 삭제" in preview_out,
            "★★★ happy_calls 전량삭제 1건이 승인 전 화면에 공시된다")
        chk("login_attempts" in preview_out and "전량 초기화" in preview_out,
            "★★★ login_attempts 전량초기화 1건이 승인 전 화면에 공시된다")
        chk("rating" in preview_out and "win_rate" in preview_out,
            "★★★★ 협력사 평판(rating·win_rate) 초기화가 승인 전 경고문에 나타난다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드187 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
