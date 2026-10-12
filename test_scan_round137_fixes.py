# -*- coding: utf-8 -*-
"""스캔 137라운드 회귀 — 2건.

  [1] _DEAD_PARTNER(기존 세션을 즉시 죽이는 목록)에 '심사중'이 빠져 있었다.
      101라운드가 로그인 차단·강등 관문엔 넣었지만 이 목록만 놓쳐, 이미
      로그인해 있던 업체를 '심사중'으로 내려도 세션은 살아 완료보고·하자
      대응을 계속할 수 있었다.
  [2] _sweep_award_approval(낙찰승인 독촉)이 136라운드가 형제 스윕
      (sweep_approval_overdue)에 넣은 '보험사 중지 감지'를 못 받았다 —
      중지된 보험사에게 영원히 독촉만 쌓이고 운영팀은 그 사실을 모른다.

  ⚠ 이번 라운드는 세 번째 후보(dispatch.claim() 이 그 순간 업체 상태를
    재확인하지 않는다)도 처음엔 결함으로 보고 고쳤으나, 되돌렸다 —
    test_scan_round52_fixes.py 가 "퇴출 업체도 claim·arrive 는 그대로
    성공한다"를 **의도된 사전조건**으로 이미 실행 검증해 두고 있었다(실제
    무등록·비활성 재확인은 계약이 성립하는 순간인 settle_agreement/낙찰
    확정 라우트에서 하도록 설계됨 — claim/arrive 는 현장을 보러 가는
    예비 단계일 뿐 계약 성립이 아니다). 회귀를 돌려 그 사실을 확인한 뒤
    dispatch.py 수정을 되돌렸다 — claim() 은 원래대로 둔다.

      python test_scan_round137_fixes.py
"""
import io
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("BOKGUON_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="round137_"), "verify.db"))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 137라운드 회귀 — 심사중 세션생존 · 낙찰승인독촉 중지보험사 미감지")
print("=" * 72)

# ============================================================
print("\n[1] _DEAD_PARTNER — 심사중이 기존 세션도 죽이는가")
# ------------------------------------------------------------
i_dp = APP_SRC.index("_DEAD_PARTNER = (")
dead_partner = eval(APP_SRC[i_dp + len("_DEAD_PARTNER = "):APP_SRC.index(")", i_dp) + 1])  # noqa: S307 -- 우리 소스 튜플 리터럴
chk("심사중" in dead_partner,
    "★★★ _DEAD_PARTNER 에 '심사중'이 들어갔다(기존 세션도 즉시 죽는다)", dead_partner)
chk("경고" not in dead_partner and "활성" not in dead_partner,
    "★ '경고'·'활성'은 여전히 안 들어있다(기존 일은 계속하게 두는 설계는 유지)", dead_partner)

# ============================================================
print("\n[2] 소스 확인 — _sweep_award_approval")
# ------------------------------------------------------------
i_saa = APP_SRC.index("def _sweep_award_approval(conn):")
i_saa_end = APP_SRC.index("\ndef ", i_saa + 1)
saa_body = APP_SRC[i_saa:i_saa_end]
chk("LEFT JOIN insurers i ON i.id = c.insurer_id" in saa_body and "insurer_status" in saa_body,
    "★★★ 낙찰승인독촉 스윕이 보험사 상태를 함께 읽는다")
chk("if sent or insurer_suspended:" in saa_body,
    "★★★ 전부 중지보험사 건이어도(sent=0) 운영팀 알림이 롤백되지 않는다")

# ============================================================
print("\n[3] 실행 — 실제 _sweep_award_approval() 로 중지보험사 재현")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round137_exec_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
try:
    import db as DB
    DB.init_db()
    conn = DB.get_db()

    iid = conn.execute(
        "INSERT INTO insurers(name,org_type,manager,dept,phone,email,fee_rate_bp,status,created_at) "
        "VALUES('테스트보험','손해보험','','','','',900,'중지',datetime('now','+9 hours'))").lastrowid
    conn.execute(
        "INSERT INTO cases(case_no,status,status_at,category,region,insurer,insurer_id,is_demo) "
        "VALUES('R137-TEST','승인대기',datetime('now','+9 hours','-5 days'),'가드레일','서울','테스트보험',?,0)",
        (iid,))
    conn.commit()

    ns = {"rows": lambda cur: [dict(r) for r in cur.fetchall()],
          "one": lambda cur: (lambda r: dict(r) if r else None)(cur.fetchone()),
          "sqlite3": sqlite3,
          "app": type("A", (), {"logger": type("L", (), {"exception": staticmethod(lambda *a, **k: None)})()})(),
          "APPROVAL_REMIND_DAYS": 1, "APPROVAL_REMIND_BATCH": 50,
          "DB": type("DBs", (), {"log": staticmethod(lambda *a, **k: None)})(),
          "notify": None}
    #  ⚠ 진짜 커밋 여부(콜스택 기록이 아니라 실제 DB 잔존)를 보려면 notify() 도
    #    실제로 notifications 테이블에 써야 한다 — 이 함수 자체는 이미 여러
    #    라운드에 걸쳐 검증된 공용 함수라 전체를 다시 옮길 필요는 없고, 이 스윕이
    #    실제로 쓰는 열만 real INSERT 로 남기는 얇은 스텁이면 충분하다.
    _calls = []

    def _notify_stub(conn_, ntype, channel, target, message, audience_type=None,
                      insurer_id=None, partner_id=None, case_id=None, url=None):
        _calls.append(((conn_, ntype, channel, target, message),
                       {"audience_type": audience_type, "insurer_id": insurer_id,
                        "partner_id": partner_id, "case_id": case_id, "url": url}))
        conn_.execute(
            "INSERT INTO notifications(ntype,channel,target,message,audience_type,"
            "insurer_id,partner_id,case_id,url,created_at) VALUES(?,?,?,?,?,?,?,?,?,datetime('now','+9 hours'))",
            (ntype, channel, target, message, audience_type, insurer_id, partner_id, case_id, url))
    ns["notify"] = _notify_stub
    exec(compile(saa_body.rstrip(), "<sweep_award_approval>", "exec"), ns)  # noqa: S102 -- 우리 소스, 실제 함수 실행
    _sweep = ns["_sweep_award_approval"]
    sent = _sweep(conn)
    chk(sent == 0, "★ 중지보험사 건은 insurer 앞 독촉으로 세지 않는다(sent=0)", sent)
    admin_calls = [c for c in _calls if c[1].get("audience_type") == "admin"]
    insurer_calls = [c for c in _calls if c[1].get("audience_type") == "insurer"]
    chk(len(admin_calls) == 1 and len(insurer_calls) == 0,
        "★★★ 중지된 보험사 대신 운영팀에게만 알림이 간다(실측 재현)",
        {"admin": len(admin_calls), "insurer": len(insurer_calls)})
    row = conn.execute(
        "SELECT COUNT(*) n FROM notifications WHERE ntype='낙찰승인독촉_중지보험사'").fetchone()
    chk(row["n"] == 1,
        "★★★ 그 알림이 실제로 커밋돼 DB에 남는다(롤백으로 사라지지 않는다)", dict(row))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드137 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
