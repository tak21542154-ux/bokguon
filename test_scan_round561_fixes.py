# -*- coding: utf-8 -*-
"""스캔 561라운드 회귀 — 보험사 관리자수정(api_insurer_update, PATCH
   /api/insurers/<iid>)의 일반 필드 루프(org_type/manager/dept/phone/email/
   contract_status/status)가 "본문에 그 키가 있는가"만 보고 실제로 값이
   바뀌었는지는 보지 않아, 관리자가 담당자 한 칸만 고쳐 저장해도(화면이
   폼 전체를 통째로 재전송하는 관례 — round240·round154 가 이 함수 자신의
   다른 부작용에서 이미 확인한 그 관례) 나머지 칸까지 전부 "바뀐 값"인 양
   매번 다시 SET 되고, 감사로그(DB.log)도 notes 가 비어 있어 무엇이
   바뀌었는지 못 남긴 채 "정보 수정"이라는 빈 문구만 남기던 결함.

   조사 배경 — 오케스트레이터가 이번 라운드 준 각도("admin-vs-portal case
   UPDATE 필드 정합성")를 따라가다, 사건(cases)에는 대칭되는 보험사측
   일반수정 라우트가 없어(보험사는 severity 등 좁은 전용 라우트만 있다)
   그 각도는 막다른 길이었다. 대신 같은 "관리자수정 vs 자기수정" 비교
   구도를 보험사 엔티티(insurers)에 적용해 직접 조사(하위위임 없음)한
   결과 발견 — round544 는 자기수정(api_insurer_profile_update)에
   `if v == ((prev or {}).get(f) or ""): continue` 가드를 이식했는데, 그
   형제인 관리자수정(api_insurer_update)에는 옮기지 않았다. 결정적으로
   round506 자신의 주석이 이미 "완전한 결백 증명은 아니다 — 필드 루프가
   값이 실제로 바뀌었는지와 무관하게 요청에 그 키가 있으면 무조건 sets에
   넣는 것은 이 함수와 형제 api_partner_update 양쪽에 공통인, 이번
   라운드 범위 밖의 별개 동작이다"라고 미리 밝혀 둔 바로 그 결함이었다
   (api_partner_update 는 검증-전 필드루프가 DB 연결·prev 조회보다도
   먼저 실행되는 구조라 같은 가드를 이식하려면 연결 수명을 재구성해야
   해서 위험도가 더 크다 — 이번 라운드는 구조 변경 없이 안전하게 고칠 수
   있는 api_insurer_update 하나로 범위를 좁혔다. api_partner_update 는
   같은 결함이 남아 있음을 이 테스트 파일에 남겨 다음 라운드로 넘긴다).

   고침(app.py, api_insurer_update) — 형제 자기수정(api_insurer_profile_
   update, round544)과 같은 가드를 그대로 이식했다(이 함수는 이미 r 를
   SELECT * 로 갖고 있어 새 조회가 필요 없었다). status 는 changed
   블록이 이미 "상태 X → Y" 서술형 문구를 notes 에 남기므로, 일반 루프가
   bare "status" 를 중복 기재하지 않게만 가드했다.

   이 회귀테스트는 ONLY 안전한 기법만 쓴다 — on-disk app.py 는 조회만
   하고, "되돌리기" 증명은 옛(대조 없던) 루프의 핵심 3줄만 별도 문자열로
   재구성해 exec()로 인과관계를 실측한다(반환문이 없는 순수 대입문만
   추려 exec 네임스페이스 제약을 피했다 — 형식검사·조기반환은 이 결함과
   무관해 round483/484 가 이미 별도로 검증했다). 그 다음 실제 라이브
   라우트(Flask test_client)로 관리자 세션을 통해 종단까지 확인한다.

      python test_scan_round561_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


print("=" * 72)
print("  스캔 561라운드 회귀 — 보험사 관리자수정 일반필드 미변경 재기록·빈 감사로그")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — app.py 가 실제로 고쳐졌는가")
# ------------------------------------------------------------
APP_SRC = read("app.py")
_iu_start = APP_SRC.index("def api_insurer_update(iid):")
_iu_end = APP_SRC.index("\ndef ", _iu_start + 10)
IU_SRC = APP_SRC[_iu_start:_iu_end]

chk('if v == (r[f] or ""):' in IU_SRC and "\n                continue\n" in IU_SRC,
    "★★★★★ api_insurer_update 루프 안에 형제(자기수정)와 같은 prev 대조 가드가 생겼다")
chk('if f != "status":\n                notes.append(f)' in IU_SRC,
    "★★★★ status 는 changed 블록의 서술형 문구와 중복 기재되지 않는다")
# 회귀 방지 — 형제 라운드들이 이미 심어 둔 것들이 그대로 남아 있어야 한다
chk("BEGIN IMMEDIATE" in IU_SRC, "  회귀 방지: round506 의 동시성 잠금이 그대로다")
chk('d["status"] not in INSURER_STATUSES' in IU_SRC, "  회귀 방지: round136 상태 허용목록 검사가 그대로다")
#  ⚠⚠ [라운드609] round608이 발견한 새 결함군(RE_PHONE.match()/RE_EMAIL.match()가
#    비문자열 JSON에 TypeError) 스윕으로 d[f]가 _s()로 감싸졌다 — 검사 자체는
#    그대로 있다(리터럴만 바뀜, 검증 취지는 동일).
chk("RE_EMAIL.match(_s(d[f]))" in IU_SRC, "  회귀 방지: round483 이메일 형식 검사가 그대로다")
chk("RE_PHONE.match(_s(d[f]))" in IU_SRC, "  회귀 방지: round484 연락처 형식 검사가 그대로다")
chk('notes.append(f"수수료율' in IU_SRC, "  회귀 방지: 수수료율 old→new 서술 로그가 그대로다")

# api_partner_update 는 이번 라운드가 일부러 손대지 않았다 — 같은 결함이
# 남아 있음을 스스로 기록해 다음 라운드가 중복조사하지 않게 한다.
_pu_start = APP_SRC.index("def api_partner_update(pid):")
_pu_end = APP_SRC.index("\ndef ", _pu_start + 10)
PU_SRC = APP_SRC[_pu_start:_pu_end]
chk("if v == (r[f] or \"\"):" not in PU_SRC and "if v == (prev[" not in PU_SRC,
    "  기록: api_partner_update 는 이번 라운드가 일부러 안 건드렸다(같은 결함 존재, 후속 라운드 과제)")

# ============================================================
print("\n[2] 되돌리기 — 옛(대조 없는) 루프 핵심부를 그대로 실행하면 실제로")
print("    아무 값도 안 바뀌었는데 SET 대상이 채워지는가 (인과관계 실측)")
# ------------------------------------------------------------
FIELDS = ("org_type", "manager", "dept", "phone", "email", "contract_status")
UNCHANGED_BODY = {"org_type": "손해보험사", "manager": "김철수", "dept": "보상2팀",
                  "phone": "010-1111-2222", "email": "old@ins.co.kr", "contract_status": "계약중"}

#  ⚠ 안전 규칙 — on-disk app.py 는 전혀 건드리지 않는다. 이 결함의 실제
#    원인이었던 옛(prev 대조가 없던) 루프의 핵심 3줄만 별도 문자열로
#    재구성해 exec() 로 스크래치 네임스페이스에서 돌린다(반환문 없음 —
#    형식검사·조기반환은 무관하므로 뺐다. round560 의 OLD_TAIL_SRC 와
#    같은 기법).
OLD_LOOP_CORE = (
    "sets, vals, notes = [], [], []\n"
    "for f in FIELDS:\n"
    "    if f in d:\n"
    "        v = d[f]\n"
    "        sets.append(f + '=?'); vals.append(v)\n"
)
_old_ns = {"d": dict(UNCHANGED_BODY), "FIELDS": FIELDS}
exec(OLD_LOOP_CORE, {}, _old_ns)
chk(_old_ns["sets"] == [f + "=?" for f in FIELDS],
    "★★★★★ 옛 루프(대조 없음)를 그대로 실행하면 값이 하나도 안 바뀌었는데도 "
    "필드 6개 전부가 SET 대상으로 잡힌다(수정 전 실제 증상을 인과관계로 증명)",
    _old_ns["sets"])
chk(_old_ns["notes"] == [],
    "  (대조군) 옛 루프는 애초에 notes를 채우는 코드조차 없었다 — 감사로그가 "
    "무엇이 바뀌었는지 못 남기는 원인도 같은 자리다",
    _old_ns["notes"])

# ============================================================
print("\n[3] 준비 — 스크래치 DB(오늘자 실제 스키마) + 최고관리자 세션")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round561_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB
DB.init_db()
import app as A

conn = DB.get_db()
conn.execute("INSERT INTO admins(username,password_hash,name,role) "
             "VALUES('r561admin','x','검증','최고관리자')")
conn.execute(
    "INSERT INTO insurers(name,org_type,manager,dept,phone,email,contract_status,status,created_at) "
    "VALUES('R561보험',?,?,?,?,?,?, '활성', ?)",
    (UNCHANGED_BODY["org_type"], UNCHANGED_BODY["manager"], UNCHANGED_BODY["dept"],
     UNCHANGED_BODY["phone"], UNCHANGED_BODY["email"], UNCHANGED_BODY["contract_status"], DB.now()))
conn.commit()
iid = conn.execute("SELECT id FROM insurers WHERE name='R561보험'").fetchone()["id"]


def _row():
    return dict(conn.execute("SELECT * FROM insurers WHERE id=?", (iid,)).fetchone())


def _log_rows():
    return [r["detail"] for r in conn.execute(
        "SELECT detail FROM activity_log WHERE action='보험사 정보 변경' "
        "ORDER BY id").fetchall()]


admin_c = A.app.test_client()
_tok = "r561-csrf"
with admin_c.session_transaction() as sess:
    sess["admin"] = "r561admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
    sess["_csrf"] = _tok

# ============================================================
print("\n[4] 실행 — 실제 라이브 라우트(PATCH /api/insurers/<id>)로 폼 전체를")
print("    아무것도 안 고치고 그대로 재전송하면 (화면의 실제 관례)")
# ------------------------------------------------------------
r1 = admin_c.patch(f"/api/insurers/{iid}", headers={"X-CSRF-Token": _tok}, json=dict(UNCHANGED_BODY))
j1 = r1.get_json() or {}
chk(r1.status_code == 200 and j1.get("ok") and j1.get("unchanged") is True,
    "★★★★★ 아무 값도 안 바뀐 전체 재전송은 unchanged:True 를 돌려준다(더 이상 "
    "UPDATE 를 실제로 실행하지 않는다)", j1)
chk(_log_rows() == [],
    "★★★★★ 감사로그(activity_log)에 '보험사 정보 변경' 행이 단 하나도 안 생겼다"
    "(수정 전이라면 이 자리에서 빈 '정보 수정' 로그가 남았을 것)", _log_rows())
chk(_row()["dept"] == "보상2팀" and _row()["manager"] == "김철수",
    "  DB 값 자체도 그대로다(회귀 아님)", _row())

# ============================================================
print("\n[5] 실행 — manager 한 칸만 고치고 나머지는 그대로 재전송하면")
# ------------------------------------------------------------
body2 = dict(UNCHANGED_BODY); body2["manager"] = "박영희"
r2 = admin_c.patch(f"/api/insurers/{iid}", headers={"X-CSRF-Token": _tok}, json=body2)
j2 = r2.get_json() or {}
chk(r2.status_code == 200 and j2.get("ok") and j2.get("changed") == ["manager"],
    "★★★★★ 실제로 바뀐 필드(manager) 하나만 changed 목록에 담겨 온다"
    "(수정 전이라면 안 바뀐 나머지도 섞이거나 최소한 감사로그가 특정을 못 했다)", j2)
chk(_row()["manager"] == "박영희" and _row()["dept"] == "보상2팀" and _row()["email"] == "old@ins.co.kr",
    "  실제로 바뀐 값만 반영되고 나머지 필드는 그대로다", _row())
_logs_after_5 = _log_rows()
chk(len(_logs_after_5) == 1 and "manager" in _logs_after_5[-1],
    "★★★★ 감사로그가 이제 '무엇이 바뀌었는지'(manager)를 구체적으로 남긴다"
    "(수정 전이라면 이 문구는 빈 '정보 수정'이었다)", _logs_after_5)

# ============================================================
print("\n[6] 정합성 — 형제 자기수정(api_insurer_profile_update)은 지금도")
print("    같은 원칙(안 바뀌면 unchanged)으로 동작하는가")
print("    (계정을 아직 중지하지 않은 지금 확인 — 다음 [7]이 중지시킨다)")
# ------------------------------------------------------------
insurer_c = A.app.test_client()
_itok = "r561-insurer-csrf"
with insurer_c.session_transaction() as sess:
    sess["insurer_id"] = iid; sess["insurer_name"] = "R561보험"; sess["_csrf"] = _itok
r4 = insurer_c.patch("/api/insurer/profile", headers={"X-CSRF-Token": _itok}, json={
    "manager": "박영희", "dept": "보상2팀", "phone": UNCHANGED_BODY["phone"], "email": UNCHANGED_BODY["email"]})
j4 = r4.get_json() or {}
chk(r4.status_code == 200 and j4.get("unchanged") is True,
    "  회귀 방지: 형제(자기수정)는 이번 수정과 무관하게 여전히 unchanged 를 지킨다", j4)

# ============================================================
print("\n[7] 실행 — 상태변경(활성→중지)과 일반필드(dept) 변경이 겹칠 때")
print("    bare 'status' 중복 기재 없이 서술형 문구만 남는가")
# ------------------------------------------------------------
body3 = dict(UNCHANGED_BODY); body3["manager"] = "박영희"  # 이미 반영된 현재값 유지
body3["dept"] = "보상3팀"
body3["status"] = "중지"
body3["status_reason"] = "무등록 확인됨(검증용 사유)"
r3 = admin_c.patch(f"/api/insurers/{iid}", headers={"X-CSRF-Token": _tok}, json=body3)
j3 = r3.get_json() or {}
chk(r3.status_code == 200 and j3.get("ok"),
    "상태+일반필드 동시변경 — 실제 라우트가 200을 돌려준다", (r3.status_code, j3))
chk(j3.get("changed") == ["dept", "상태 활성 → 중지"],
    "★★★★★ changed 목록에 'dept'와 서술형 '상태 활성 → 중지'만 있다 — "
    "bare 'status' 가 중복으로 섞이지 않는다", j3.get("changed"))
chk(_row()["status"] == "중지" and _row()["dept"] == "보상3팀",
    "  DB 반영도 정상이다(회귀 아님)", _row())

# ── 정리 ──────────────────────────────────────────────────────
conn.execute("DELETE FROM activity_log WHERE detail LIKE '%R561보험%' OR detail LIKE '%보상%'")
conn.execute("DELETE FROM insurers WHERE name='R561보험'")
conn.execute("DELETE FROM admins WHERE username='r561admin'")
conn.commit()
conn.close()

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
