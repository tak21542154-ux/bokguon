# -*- coding: utf-8 -*-
"""스캔 515라운드 회귀 — 1차합의(현장 견적) 보험사 승인 경로에서 피해자
안내가 통째로 빠져 있던 결함(app.py api_insurer_field_agreement_decision).

형제 비교: 사건이 '시공중'으로 배정되는 낙찰 경로는 셋이다 —
  ① 보험사가 경매 낙찰을 승인(api_insurer_award, 4611행 부근)
  ② 관리자가 직접 낙찰 확정(api_award 계열, 11479행 부근)
  ③ 보험사가 1차합의(현장 실견적)를 승인(api_insurer_field_agreement_decision, 18040행)
①·②는 이미 4627행 주석이 명시하는 원칙("피해자 안내는 낙찰 경로와
무관하게 나가야 한다 — 같은 사건인데 누가 승인했느냐에 따라 어떤
피해자는 연락을 받고 어떤 피해자는 아무 소식 없이 모르는 업체가
찾아오게 된다")에 따라 notify_victim() 을 부른다. 그런데 그 원칙을
세운 라운드가 경매(①·②) 두 경로만 고치고 ③(1차합의)은 놓쳤다 —
오히려 ③은 app.py 18097행 자신의 주석대로 "소액 직접 도급의 본류"라
실사용 빈도가 더 높다. 그 결과 1차합의로 배정된 사건의 피해자는
완료보고(11703행)때까지 업체가 정해졌다는 사실조차 통지받지 못했다.

[1] 소스 확인 — api_insurer_field_agreement_decision() 의 승인(approve)
    분기에 [라운드515] 표식과 notify_victim() 호출이 실제로 있음.
[2] 실제 Flask 앱(in-process test_client) 실행 — 사건접수(피해자 연락처
    포함)→출동→도착→1차합의 개시→보험사 승인까지 실제로 진행시켜,
    notifications 테이블에 '피해자안내' 행이 실제로 1건 쌓이고 그 문구에
    선정된 업체명이 담기는지 확인.
[3] 되돌림-증명 — app.py 소스에서 새 notify_victim 블록만 제거한 사본을
    exec 로 재구성(require_portal_role 데코레이터도 다시 입힘)해 A.app.
    view_functions 딕셔너리 항목만 잠깐 치환(실제 app.py 파일은 전혀 안
    건드림) — 같은 시나리오를 다시 돌리면 피해자안내가 0건으로 되돌아
    가는지(=이 테스트가 실제로 결함을 잡아낼 능력이 있는지) 대조. 그 외
    필드(승인 자체의 성공 여부·사건 상태전이)는 그대로임을 함께 확인해
    "피해자 통지 유무"만 갈린다는 것을 보인다.

⚠⚠ [라운드616] 되돌림-증명 기법을 옛 세대(app.py를 실제로 디스크에
  써넣고 새로 만든 워커 스크립트를 서브프로세스로 돌려 재현한 뒤 복원 —
  write→subprocess→write 사이의 창을 다른 세션이 관측하면 충돌한다,
  round590이 실제로 겪음)에서 round488/round414가 확립한 안전패턴으로
  이관한다. api_insurer_field_agreement_decision() 은 단일 라우트
  핸들러라 이 함수 자신의 소스에서 새 블록만 제거한 사본을 exec로
  재구성(require_portal_role 데코레이터도 다시 입힘)해 A.app.
  view_functions 딕셔너리 항목만 잠깐 치환한다 — 진짜 app.py 파일은
  전혀 안 쓴다(예전 워커 test_scan_round515_worker.py 는 매 실행 새로
  스크래치 DB를 만들던 서브프로세스였다 — 이 파일은 더 이상 그걸
  띄우지 않는다). 사건 셋업(출동→도착→1차합의 개시)은 시나리오마다
  독립된 새 보험사·업체·사건으로 반복하므로 서로 오염되지 않는다.
"""
import hashlib
import io
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 515라운드 회귀 — 1차합의 승인 시 피해자 안내 누락")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ══════════════════════════════════════════════════════════════
APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()
APP_HASH_BEFORE = hashlib.sha256(APP_SRC.encode("utf-8")).hexdigest()

_bi = APP_SRC.find("def api_insurer_field_agreement_decision(cid):")
_mark_start = APP_SRC.find("#  ⚠⚠ [라운드515]", _bi)
_mark_end = APP_SRC.find("conn.commit()", _mark_start)
NEW_BLOCK = APP_SRC[_mark_start:_mark_end] if _bi > 0 and _mark_start > _bi else ""

chk(_bi > 0, "api_insurer_field_agreement_decision() 함수를 소스에서 찾았다")
chk(bool(NEW_BLOCK) and "notify_victim(" in NEW_BLOCK,
    "★★★★★ 승인 분기에 [라운드515] notify_victim() 블록이 실제로 있다",
    NEW_BLOCK[:80] if NEW_BLOCK else "블록을 못 뽑음")
chk(APP_SRC.count(NEW_BLOCK) == 1 and len(NEW_BLOCK) > 0,
    "되돌림-증명에 쓸 새 블록이 소스에 정확히 1번만 있다(대체 지점 특정 가능)",
    APP_SRC.count(NEW_BLOCK) if NEW_BLOCK else "블록을 못 뽑음")
# 이 블록이 admin 알림(notify 운영팀)과 conn.commit() 사이, 즉 승인(approve) 분기
# 안쪽에 있는지 — 부동의(else) 분기나 함수 바깥에 잘못 걸리지 않았는지 확인.
_admin_notify = APP_SRC.find('notify(conn, "낙찰", "웹", "운영팀",', _bi)
chk(0 < _admin_notify < _mark_start < _mark_end,
    "블록 위치가 admin 알림 다음 · conn.commit() 이전(승인 분기 안쪽)이다")

# 함수 전체(데코레이터 제외, def 줄부터 finally: conn.close() 까지) — 되돌림판 exec용.
_def_pos = APP_SRC.find("\ndef api_insurer_field_agreement_decision(cid):")
_end_anchor = "\n    finally:\n        conn.close()\n"
_fend = APP_SRC.find(_end_anchor, _def_pos)
chk(_def_pos > 0 and _fend > _def_pos, "함수 끝(finally: conn.close())을 찾았다")
FUNC_BODY = APP_SRC[_def_pos:_fend + len(_end_anchor)]
chk(NEW_BLOCK in FUNC_BODY, "새 블록이 추출한 함수 본문 안에 있다(추출 범위 정합성)")

OLD_FUNC_BODY = FUNC_BODY.replace(NEW_BLOCK, "", 1)
assert OLD_FUNC_BODY != FUNC_BODY, "되돌림 치환이 실제로 안 먹었다"
chk("notify_victim(" not in OLD_FUNC_BODY, "되돌림판 함수 본문에는 notify_victim 호출이 없다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 준비 — 스크래치 DB, 시나리오마다 독립된 사건 셋업")
# ══════════════════════════════════════════════════════════════
_tmpdir = tempfile.mkdtemp(prefix="r515_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB                 # noqa: E402
DB.init_db()
import dispatch as DP           # noqa: E402
import app as A                  # noqa: E402

_conn0 = DB.get_db()
_conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                "VALUES('admin515','x','검증','최고관리자')")
_conn0.commit(); _conn0.close()


def _setup_case(tag):
    """새 보험사·업체·사건을 만들어 출동→도착→1차합의 개시까지 실제로
    진행시킨 뒤 (cid, iid, fa_open_status) 를 반환한다."""
    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,status) VALUES(?,?)", (f"R515보험{tag}", "활성")).lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,lat,lng) "
        "VALUES(?,?,?,?,?)", (f"R515업체{tag}", "시행사", "활성", 37.5, 127.0)).lastrowid
    #  ⚠ 피해자 연락처를 반드시 채운다 — notify_victim() 은 victim_phone 이
    #    없으면 조용히 아무 일도 안 하고 리턴한다. 연락처 없이 돌리면
    #    "결함이 있어도 없어도 통지 0건"이라 결함을 구분 못 하게 된다.
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,lat,lng,"
        "victim_name,victim_phone) VALUES(?,?,?,?,?,?,?,?,?)",
        (f"26-515-{tag}", "접수", "가드레일", "서울", iid, 37.5, 127.0,
         f"피해자515{tag}", "01055515515")).lastrowid
    conn.commit()

    did, _called, _sent = DP.open_dispatch(conn, cid)
    conn.commit()
    ok_a, _msg_a, did2 = DP.assign_dispatch(conn, cid, pid, "테스트 직접배정")
    conn.commit()
    use_did = did2 if ok_a else did
    DP.claim(conn, use_did, pid, f"R515업체{tag}")
    conn.commit()
    ok_r, msg_r = DP.arrive(conn, use_did, pid, photo_count=3, field_estimate=900000)
    conn.commit()
    conn.close()
    assert ok_r, f"arrive 준비 실패: {msg_r}"

    admin_c = A.app.test_client()
    with admin_c.session_transaction() as sess:
        sess["admin"] = "admin515"; sess["admin_name"] = "검증"; sess["admin_role"] = "최고관리자"
        sess["_csrf"] = "r515-csrf"
    r_fa = admin_c.post(f"/api/cases/{cid}/field-agreement", json={},
                         headers={"X-CSRF-Token": "r515-csrf"})
    assert r_fa.status_code == 200, f"1차합의 개시 실패: {r_fa.status_code} {r_fa.get_json()}"
    return cid, iid, r_fa.status_code


def _decide(cid, iid, tag):
    insurer_c = A.app.test_client()
    with insurer_c.session_transaction() as sess:
        sess["insurer_id"] = iid; sess["insurer_name"] = f"R515보험{tag}"; sess["_csrf"] = "r515-csrf"
    r_decide = insurer_c.post(f"/api/insurer/cases/{cid}/field-agreement/decision",
                               json={"approve": True},
                               headers={"X-CSRF-Token": "r515-csrf"})
    conn2 = DB.get_db()
    victim_rows = conn2.execute(
        "SELECT ntype, channel, message FROM notifications "
        " WHERE case_id=? AND ntype='피해자안내'", (cid,)).fetchall()
    case_status = conn2.execute("SELECT status, partner_name FROM cases WHERE id=?",
                                 (cid,)).fetchone()
    conn2.close()
    return {
        "decide_status": r_decide.status_code, "decide_body": r_decide.get_json(),
        "case_after": dict(case_status) if case_status else None,
        "victim_notify_count": len(victim_rows),
        "victim_notify_rows": [dict(r) for r in victim_rows],
    }


try:
    print("\n[3] 실행 — 현재(고쳐진) 코드로 1차합의 승인")
    cid1, iid1, fa_status1 = _setup_case("A")
    fixed = _decide(cid1, iid1, "A")
    chk(fa_status1 == 200, "1차합의 개시(관리자) 200", fa_status1)
    chk(fixed["decide_status"] == 200 and (fixed["decide_body"] or {}).get("ok") is True,
        "보험사 승인 자체는 200으로 성공한다", fixed["decide_body"])
    chk((fixed["case_after"] or {}).get("status") == "시공중"
        and (fixed["case_after"] or {}).get("partner_name") == "R515업체A",
        "승인 후 사건이 '시공중'으로 배정된다", fixed["case_after"])
    chk(fixed["victim_notify_count"] == 1,
        "★★★★★ 피해자안내(notifications.ntype='피해자안내') 1건이 실제로 쌓인다",
        fixed["victim_notify_count"])
    _msg = fixed["victim_notify_rows"][0]["message"] if fixed["victim_notify_rows"] else ""
    chk("R515업체A" in _msg and "선정되었습니다" in _msg,
        "★★★★★ 피해자 안내 문구에 선정된 업체명이 실제로 담긴다", _msg)

    # ══════════════════════════════════════════════════════════
    print("\n[4] 되돌림-증명 — view_functions 딕셔너리 항목만 잠깐 치환(실제 파일은 안 건드림)")
    # ──────────────────────────────────────────────────────────
    _ns = dict(vars(A))
    exec(compile(OLD_FUNC_BODY, "<round515_reverted_field_agreement_decision>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_fn = A.require_portal_role("insurer", "중간관리자")(_ns["api_insurer_field_agreement_decision"])

    _orig_view = A.app.view_functions["api_insurer_field_agreement_decision"]
    A.app.view_functions["api_insurer_field_agreement_decision"] = old_fn
    try:
        cid2, iid2, fa_status2 = _setup_case("B")
        broken = _decide(cid2, iid2, "B")
    finally:
        A.app.view_functions["api_insurer_field_agreement_decision"] = _orig_view

    chk(fa_status2 == 200, "옛 코드(되돌림)도 1차합의 개시 자체는 그대로 성공한다", fa_status2)
    chk(broken["decide_status"] == 200 and (broken["decide_body"] or {}).get("ok") is True,
        "옛 코드(되돌림)도 승인 자체는 그대로 성공한다(구조는 안 바뀐다)",
        broken["decide_body"])
    chk((broken["case_after"] or {}).get("status") == "시공중",
        "옛 코드(되돌림)도 사건 배정 자체는 그대로 된다", broken["case_after"])
    chk(broken["victim_notify_count"] == 0,
        "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림)는 피해자안내가 0건이다"
        " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
        broken["victim_notify_count"])

    print("\n[5] 원복 확인 — 되돌리기 이후 다시 정상 동작하는가(바꿔치기가 안 샜다)")
    chk(A.app.view_functions["api_insurer_field_agreement_decision"] is _orig_view,
        "  view_functions가 원래 함수객체로 복원됐다")
    cid3, iid3, fa_status3 = _setup_case("C")
    restored = _decide(cid3, iid3, "C")
    chk(restored["victim_notify_count"] == 1,
        "★★★★ 원복 후에는 다시 피해자안내가 나간다(바꿔치기가 안 샜다)",
        restored["victim_notify_count"])

except Exception as e:                                              # noqa: BLE001
    chk(False, "[3]+[4] 백엔드 실행/되돌림-증명", f"{type(e).__name__}: {e}")

APP_HASH_AFTER = hashlib.sha256(io.open(APP_PATH, encoding="utf-8").read().encode("utf-8")).hexdigest()
chk(APP_HASH_AFTER == APP_HASH_BEFORE,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(view_functions 딕셔너리 항목 임시치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
