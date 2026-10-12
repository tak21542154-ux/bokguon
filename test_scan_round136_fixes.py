# -*- coding: utf-8 -*-
"""스캔 136라운드 회귀 — 보험사 계정을 '중지'하면(관리자 화면의 유일한
   비활성 선택지) 로그인이 영구히 막히는데, 공사완료 승인(settlements.
   insurer_approved)·1차합의 승인(field_agreements.status)은 **그 보험사가
   직접 로그인해야만** 넘어간다 — 관리자가 대신 처리할 방법이 없어 진행 중
   정산·합의가 영구히 멈춘다. 협력사 쪽엔 있는 강등 관문(PARTNER_DEMOTED·
   _partner_demote_gate·PARTNER_STATUSES)이 보험사 쪽엔 전혀 없었다.

  수정: 협력사와 같은 방식으로 보험사에도 상태 허용목록(INSURER_STATUSES)·
  강등 관문(_insurer_demote_gate)·사유 기록(status_reason 등, db.py 마이그레이션
  추가)을 두고, 승인대기 스윕(sweep_approval_overdue)은 이미 중지된 보험사
  앞으로는 안 보내고 운영팀에게 직접 알린다.

      python test_scan_round136_fixes.py
"""
import io
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("BOKGUON_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="round136_"), "verify.db"))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")
DB_SRC = read("db.py")

print("=" * 72)
print("  스캔 136라운드 회귀 — 보험사 중지가 정산·1차합의 승인을 영구히 멈추게 하던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk('INSURER_STATUSES = ("활성", "중지")' in APP_SRC,
    "★★★ 보험사 상태 허용목록이 생겼다(협력사 PARTNER_STATUSES 와 같은 방식)")
chk("def _insurer_exit_load(conn, iid):" in APP_SRC and "def _insurer_demote_gate(conn, iid, new_status, confirmed):" in APP_SRC,
    "★★★ 보험사 전용 강등 관문 함수가 생겼다")
chk('("insurers", "status_reason", "TEXT")' in DB_SRC
    and '("insurers", "status_changed_at", "TEXT")' in DB_SRC
    and '("insurers", "status_changed_by", "TEXT")' in DB_SRC,
    "★★★ db.py 마이그레이션에 insurers.status_reason 등 3컬럼이 추가됐다")

i_iu = APP_SRC.index("def api_insurer_update(iid):")
i_iu_end = APP_SRC.index("\ndef ", i_iu + 1)
iu_body = APP_SRC[i_iu:i_iu_end]
chk("_insurer_demote_gate(conn, iid" in iu_body,
    "★★★ api_insurer_update 가 실제로 강등 관문을 부른다")
chk('d["status"] not in INSURER_STATUSES' in iu_body,
    "★★★ api_insurer_update 가 허용되지 않은 상태값을 거부한다")
chk('"code": "NEED_REASON"' in iu_body,
    "★★ 상태를 바꾸려면 사유를 요구한다(협력사와 동일)")

i_sw = APP_SRC.index("def sweep_approval_overdue(conn):")
i_sw_end = APP_SRC.index("\ndef ", i_sw + 1)
sw_body = APP_SRC[i_sw:i_sw_end]
chk("LEFT JOIN insurers i ON i.id = s.insurer_id" in sw_body and 'insurer_status' in sw_body,
    "★★★ 승인독촉 스윕이 보험사 상태를 함께 읽는다")
chk('if out["sent"] or out["insurer_suspended"]:' in sw_body,
    "★★★ 전부 중지보험사 건이어도(sent=0) 운영팀 알림이 롤백되지 않는다"
    "(같은 계열의 '0행이어도 트랜잭션은 열렸다' 결함 재발 방지)")

# ============================================================
print("\n[2] 실행 — 실제 db.init_db() 스키마 + 실제 함수로 재현")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round136_exec_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
try:
    import db as DB
    DB.init_db()
    conn = DB.get_db()

    iid = conn.execute(
        "INSERT INTO insurers(name,org_type,manager,dept,phone,email,fee_rate_bp,status,created_at) "
        "VALUES('테스트보험','손해보험','','','','',900,'활성',datetime('now','+9 hours'))").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,is_demo) "
        "VALUES('R136-TEST','정산진행','가드레일','서울',?,0)", (iid,)).lastrowid
    conn.execute(
        "INSERT INTO settlements(case_id,case_no,insurer,insurer_id,insurer_approved,"
        "transfer_status,void_status,is_demo,created_at) "
        "VALUES(?,?,?,?,0,'대기',NULL,0,datetime('now','+9 hours','-3 days'))",
        (cid, "R136-TEST", "테스트보험", iid))
    conn.commit()

    ns = {"rows": lambda cur: [dict(r) for r in cur.fetchall()],
          "jsonify": lambda d: d,  # Flask 컨텍스트 없이 순수 로직만 검증
          "INSURER_DEMOTED": ("중지",),
          #  ⚠ [437라운드] _insurer_exit_load 가 이제 cases 도 검사하며 이
          #    모듈 전역 상수를 참조한다 — 이 자리는 app.py 전체를 import 하지
          #    않고 함수 소스만 떼어 exec 하므로, app.py 자신의 값(4874행)과
          #    똑같이 여기서도 채워 줘야 한다(안 그러면 NameError).
          "CASE_OPEN_SQL": "status NOT IN ('완료','취소','미수선종결')"}
    #  ⚠ [라운드135 교훈 재적용] 다음 top-level 지점이 def 가 아니라 데코레이터
    #    (@app.get 등)로 시작할 수 있다 — "\ndef " 와 "\n@" 중 먼저 오는 데서 끊는다.
    i_el = APP_SRC.index("def _insurer_exit_load(conn, iid):")
    i_dg = APP_SRC.index("def _insurer_demote_gate(conn, iid, new_status, confirmed):", i_el)
    _cands = [i for i in (APP_SRC.find("\ndef ", i_dg + 1), APP_SRC.find("\n@", i_dg + 1)) if i > 0]
    i_dg_end = min(_cands)
    gate_src = APP_SRC[i_el:i_dg_end].rstrip()
    exec(compile(gate_src, "<insurer_gate>", "exec"), ns)  # noqa: S102 -- 우리 소스, 실제 함수 실행
    _gate = ns["_insurer_demote_gate"]

    blocked = _gate(conn, iid, "중지", False)
    chk(blocked is not None,
        "★★★ 완료승인 대기 정산이 있는 보험사는 확인 없이 중지시킬 수 없다"
        "(실측 재현: 고치기 전엔 이 관문 자체가 없어 무조건 통과했다)")
    allowed = _gate(conn, iid, "중지", True)
    chk(allowed is None,
        "★ confirm_demote=True 로 확인하면(협력사와 동일한 탈출구) 그래도 중지할 수 있다")
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드136 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
