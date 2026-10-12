# -*- coding: utf-8 -*-
"""스캔 562라운드 회귀 — 업체 정보수정(api_partner_update, PATCH
   /api/partners/<pid>)의 일반 필드 루프(name/partner_type/ceo/major/category/
   region/address/phone/email/website/license/status/doc_status)가 "본문에 그
   키가 있는가"만 보고 실제로 값이 바뀌었는지는 보지 않아, admin.js
   savePartner() 가 폼 전체를 통째로 재전송하는 관례(라운드240 이 이미 문서화)
   때문에 관리자가 칸 하나만 고쳐 저장해도 나머지 13개 필드까지 전부 "바뀐
   값"인 양 매번 다시 SET 되고, 감사로그(activity_log)도 "#{pid}" 뿐인 채로
   매번 새로 쌓이던 결함.

   이 결함은 561라운드가 형제(api_insurer_update)에서 이미 고친 것과 동일한
   클래스다 — 561라운드 자신의 테스트(test_scan_round561_fixes.py)가 "이
   함수(api_partner_update)는 검증-전 필드루프가 DB 연결·prev 조회보다도
   먼저 실행되는 구조라 같은 가드를 이식하려면 연결 수명을 재구성해야 해서
   위험도가 더 크다"며 다음 라운드로 명시적으로 넘겨 둔 과제.

   조사 결과 — 오케스트레이터가 준 두 구조적 선택지(가) DB 연결을 검증
   루프 앞으로 끌어올리기, 나) 후보값을 모았다가 prev 직후 대조필터링) 중,
   함수 전체를 직접 끝까지 읽은 뒤 (나)를 골랐다. (가)를 골랐다면 검증
   루프 안의 조기반환 6곳(사업자번호·연락처·이메일·홈페이지·상태·구분값
   형식오류) 전부에 conn.rollback()/conn.close() 를 새로 달아야 해 훨씬
   침습적이고, 그 조기반환들이 "DB 연결이 아직 없다"고 가정하는지도 하나씩
   재검증해야 했다. (나)는 검증 루프를 원문 그대로 두고 검증된 후보값만
   pending 딕셔너리에 모은 뒤, 이미 존재하는 prev 조회 직후(라운드493 의
   BEGIN IMMEDIATE 잠금 안)에서 한 번 더 대조 필터링만 끼워 넣으면 됐다.

   ⚠ 이 결함 자리를 감싼 기존 회귀테스트 여러 개가 특정 코드 조각을 "고정
   리터럴"로 검사하고 있어(라운드154/174/240/299/429/466/493), 되돌아가
   하나씩 직접 확인한 뒤에야 손댈 수 있었다:
     · prev 의 SELECT 문("SELECT name, status, address, lat, lng, biz_no…")은
       라운드466 이 통째 블록으로, 라운드154 가 부분일치로 잠가 뒀다 — 그래서
       prev 를 SELECT * 로 넓히는 대신 그 컬럼들을 전부 갖춘 별도 조회(full)를
       prev 조회 바로 다음 줄에 추가했다(같은 BEGIN IMMEDIATE 잠금 안이라
       그 사이 값이 못 바뀐다).
     · email_source 갱신 한 줄(`sets.append("email_source=?"); vals.append(
       "직접입력")`)은 라운드299 가 이 함수 전체 슬라이스 안에 있는지만
       본다 — 위치를 옮기고 "email" in changed_fields 로 게이팅해도 그 줄
       자체는 그대로 남겨 통과한다.
     · api_partner_update() 안의 conn.rollback() 개수(라운드493 이 5로 고정)
       는 "값이 실제로 안 바뀌면" 조기반환이 하나 늘어 6이 된다 — 그
       카운트 자체가 새로 생긴 진짜 안전자산(잠금 해제)이라 5→6 으로
       올리는 게 맞다고 판단해 그 파일도 함께 갱신했다(주석으로 근거 명시).
   위 9개 회귀테스트(154/174/240/299/429/466/79/80/101)를 전부 이 라운드
   수정 뒤 재실행해 0 실패를 직접 확인했다(아래 [6]에 스스로도 이 사실을
   기록해 다음 라운드가 중복 재확인하지 않게 한다).

   이 회귀테스트는 ONLY 안전한 기법만 쓴다 — on-disk app.py 는 조회만 하고,
   "되돌리기" 증명은 옛(대조 없던) 루프 핵심부만 별도 문자열로 재구성해
   exec() 로 인과관계를 실측한다. 그 다음 실제 라이브 라우트(Flask
   test_client)로 관리자 세션을 통해 종단까지 확인한다.

      python test_scan_round562_fixes.py
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
print("  스캔 562라운드 회귀 — 업체 정보수정 일반필드 미변경 재기록·빈 감사로그")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — app.py 가 실제로 고쳐졌는가")
# ------------------------------------------------------------
APP_SRC = read("app.py")
_pu_start = APP_SRC.index("\ndef api_partner_update(pid):")
_pu_end = APP_SRC.index("\ndef ", _pu_start + 10)
PU_SRC = APP_SRC[_pu_start:_pu_end]

chk("pending = {}" in PU_SRC and "pending[f] = v" in PU_SRC,
    "★★★★★ 검증 루프가 이제 결과를 pending 에 모으기만 하고 바로 sets 에 넣지 않는다")
chk('full = one(conn.execute("SELECT * FROM partners WHERE id=?", (pid,)))' in PU_SRC,
    "★★★★★ prev 조회 뒤 전체 컬럼(full)을 한 번 더 읽어 대조 재료로 쓴다")
chk("for f, v in pending.items():" in PU_SRC and "if v == (full[f] or \"\"):" in PU_SRC
    and "continue" in PU_SRC,
    "★★★★★ pending 을 full 과 대조해 실제로 바뀐 값만 sets/vals 에 넣는다")
chk('if "email" in changed_fields:' in PU_SRC,
    "★★★★ email_source 갱신이 이제 '본문에 키가 있는가'가 아니라 '실제로 바뀌었는가'로 걸린다")
chk('sets.append("email_source=?"); vals.append("직접입력")' in PU_SRC,
    "  회귀 방지: 라운드299 의 email_source 갱신 자체는 그대로 남아 있다(위치·조건만 바뀜)")
chk('return jsonify({"ok": True, "unchanged": True})' in PU_SRC,
    "★★★★★ 아무 것도 안 바뀌면 형제(api_insurer_update)와 같은 unchanged:True 를 돌려준다")
chk(PU_SRC.count("conn.rollback()") == 6,
    "★★★ 조기반환이 5(라운드493)에서 6으로 늘었다(새 unchanged 반환의 잠금해제)",
    PU_SRC.count("conn.rollback()"))

# 회귀 방지 — 형제 라운드들이 이미 심어 둔 것들이 그대로 남아 있어야 한다
chk("BEGIN IMMEDIATE" in PU_SRC, "  회귀 방지: 라운드493 의 동시성 잠금이 그대로다")
chk('"SELECT name, status, address, lat, lng' in PU_SRC and ' FROM partners WHERE id=?"' in PU_SRC,
    "  회귀 방지: 라운드466/154 의 prev(좁은 SELECT) 문구가 그대로다")
chk('d[f] not in PARTNER_STATUSES' in PU_SRC, "  회귀 방지: 라운드101 상태 허용목록 검사가 그대로다")
chk('d[f] not in PARTNER_TYPES' in PU_SRC, "  회귀 방지: 라운드174 구분값 허용목록 검사가 그대로다")
#  ⚠⚠ [라운드609] round608이 발견한 새 결함군(RE_PHONE.match()/RE_EMAIL.match()가
#    비문자열 JSON에 TypeError) 스윕으로 d[f]가 _s()로 감싸졌다 — 검사 자체는
#    그대로 있다(리터럴만 바뀜, 검증 취지는 동일).
chk("RE_PHONE.match(_s(d[f]))" in PU_SRC, "  회귀 방지: 라운드484 연락처 형식 검사가 그대로다")
chk("RE_EMAIL.match(_s(d[f]))" in PU_SRC, "  회귀 방지: 라운드80 이메일 형식 검사가 그대로다")
chk('sets += ["lat=NULL", "lng=NULL", "geo_src=NULL"]' in PU_SRC,
    "  회귀 방지: 라운드154 주소변경 시 좌표 초기화가 그대로다")
chk('if changed and _admin_rank() < ROLE_RANK["중간관리자"]:' in PU_SRC,
    "  회귀 방지: 라운드240 등급검사가 changed 기준 그대로다")

# ============================================================
print("\n[2] 되돌리기 — 옛(대조 없는) 루프 핵심부를 그대로 실행하면 실제로")
print("    아무 값도 안 바뀌었는데 SET 대상이 채워지는가 (인과관계 실측)")
# ------------------------------------------------------------
FIELDS = ("name", "partner_type", "ceo", "major", "category", "region", "address",
          "phone", "email", "website", "license", "status", "doc_status")
UNCHANGED_BODY = {
    "name": "R562업체", "partner_type": "시공사", "ceo": "김대표", "major": "방수",
    "category": "방수공사", "region": "서울", "address": "서울시 강남구 테스트로 1",
    "phone": "010-1111-2222", "email": "old562@test.com",
    "website": "http://old562.example.com", "license": "LIC-562",
    "status": "활성", "doc_status": "정상",
}

#  ⚠ 안전 규칙 — on-disk app.py 는 전혀 건드리지 않는다. 옛(대조 없던)
#    루프의 핵심 2줄만 별도 문자열로 재구성해 exec() 로 스크래치
#    네임스페이스에서 돌린다(반환문 없음 — 형식검사·조기반환은 이 결함과
#    무관해 round79/80/101/174 가 이미 별도로 검증했다. round561 의
#    OLD_LOOP_CORE 와 같은 기법).
OLD_LOOP_CORE = (
    "sets, vals = [], []\n"
    "for f in FIELDS:\n"
    "    if f in d:\n"
    "        v = d[f]\n"
    "        sets.append(f + '=?'); vals.append(v)\n"
)
_old_ns = {"d": dict(UNCHANGED_BODY), "FIELDS": FIELDS}
exec(OLD_LOOP_CORE, {}, _old_ns)
chk(_old_ns["sets"] == [f + "=?" for f in FIELDS],
    "★★★★★ 옛 루프(대조 없음)를 그대로 실행하면 값이 하나도 안 바뀌었는데도 "
    "필드 13개 전부가 SET 대상으로 잡힌다(수정 전 실제 증상을 인과관계로 증명)",
    _old_ns["sets"])

#  새(라운드562) 루프 핵심부 — 같은 입력을 넣으면 아무 것도 안 걸린다.
NEW_LOOP_CORE = (
    "pending = {}\n"
    "for f in FIELDS:\n"
    "    if f in d:\n"
    "        pending[f] = d[f]\n"
    "sets, vals, changed_fields = [], [], []\n"
    "for f, v in pending.items():\n"
    "    if v == (full.get(f) or ''):\n"
    "        continue\n"
    "    sets.append(f + '=?'); vals.append(v)\n"
    "    changed_fields.append(f)\n"
)
_new_ns = {"d": dict(UNCHANGED_BODY), "FIELDS": FIELDS, "full": dict(UNCHANGED_BODY)}
exec(NEW_LOOP_CORE, {}, _new_ns)
chk(_new_ns["sets"] == [] and _new_ns["changed_fields"] == [],
    "★★★★★ 새 루프(대조 있음)는 같은 입력(전부 미변경)에 대해 SET 대상이 "
    "0개다(수정 후 실제 동작을 같은 방식으로 인과관계 증명)",
    _new_ns["sets"])
_new_ns2 = {"d": dict(UNCHANGED_BODY, phone="010-9999-0000"), "FIELDS": FIELDS,
            "full": dict(UNCHANGED_BODY)}
exec(NEW_LOOP_CORE, {}, _new_ns2)
chk(_new_ns2["changed_fields"] == ["phone"],
    "  (대조군) phone 하나만 실제로 바꾸면 changed_fields 에 phone 하나만 잡힌다"
    "(과잉차단 아님)", _new_ns2["changed_fields"])

# ============================================================
print("\n[3] 준비 — 스크래치 DB(오늘자 실제 스키마) + 최고관리자 세션")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round562_")
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
             "VALUES('r562admin','x','검증','최고관리자')")
conn.execute(
    "INSERT INTO partners(name,partner_type,ceo,major,category,region,address,phone,"
    "email,website,license,status,doc_status,email_source,created_at) "
    "VALUES(:name,:partner_type,:ceo,:major,:category,:region,:address,:phone,"
    ":email,:website,:license,:status,:doc_status,'수집(테스트-대조군)',:now)",
    dict(UNCHANGED_BODY, now=DB.now()))
conn.commit()
pid = conn.execute("SELECT id FROM partners WHERE name='R562업체'").fetchone()["id"]


def _row():
    return dict(conn.execute("SELECT * FROM partners WHERE id=?", (pid,)).fetchone())


def _log_rows():
    return [r["detail"] for r in conn.execute(
        "SELECT detail FROM activity_log WHERE action='업체 정보수정' "
        "ORDER BY id").fetchall()]


admin_c = A.app.test_client()
_tok = "r562-csrf"
with admin_c.session_transaction() as sess:
    sess["admin"] = "r562admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
    sess["_csrf"] = _tok
_hdr = {"X-CSRF-Token": _tok}

# ============================================================
print("\n[4] 실행 — 실제 라이브 라우트(PATCH /api/partners/<id>)로 폼 전체를")
print("    아무것도 안 고치고 그대로 재전송하면 (admin.js 의 실제 관례)")
# ------------------------------------------------------------
r1 = admin_c.patch(f"/api/partners/{pid}", headers=_hdr, json=dict(UNCHANGED_BODY))
j1 = r1.get_json() or {}
chk(r1.status_code == 200 and j1.get("ok") and j1.get("unchanged") is True,
    "★★★★★ 아무 값도 안 바뀐 전체 재전송은 unchanged:True 를 돌려준다(더 이상 "
    "UPDATE 를 실제로 실행하지 않는다)", j1)
chk(_log_rows() == [],
    "★★★★★ 감사로그(activity_log)에 '업체 정보수정' 행이 단 하나도 안 생겼다"
    "(수정 전이라면 이 자리에서 '#{pid}' 뿐인 빈 로그가 남았을 것)", _log_rows())
chk(_row()["ceo"] == "김대표" and _row()["phone"] == "010-1111-2222",
    "  DB 값 자체도 그대로다(회귀 아님)", _row())
chk(_row()["email_source"] == "수집(테스트-대조군)",
    "★★★★ email 이 안 바뀌었으면 email_source 도 안 건드린다(라운드299 갱신은 "
    "'값이 실제로 바뀔 때만' 이라는 라운드562 원칙과 이제 일치한다 — 수정 전엔 "
    "이 재전송 한 번만으로 email_source 가 '직접입력'으로 덮어써졌다)", _row())

# ============================================================
print("\n[5] 실행 — phone 한 칸만 고치고 나머지는 그대로 재전송하면")
# ------------------------------------------------------------
body2 = dict(UNCHANGED_BODY); body2["phone"] = "010-9999-0000"
r2 = admin_c.patch(f"/api/partners/{pid}", headers=_hdr, json=body2)
j2 = r2.get_json() or {}
chk(r2.status_code == 200 and j2.get("ok") and j2.get("unchanged") is not True,
    "★★★★★ 실제로 값이 바뀌면 unchanged 없이 정상 저장된다", j2)
chk(_row()["phone"] == "010-9999-0000" and _row()["ceo"] == "김대표"
    and _row()["email"] == "old562@test.com",
    "  실제로 바뀐 값(phone)만 반영되고 나머지 필드는 그대로다", _row())
_logs_after_5 = _log_rows()
chk(len(_logs_after_5) == 1 and "phone" in _logs_after_5[-1],
    "★★★★ 감사로그가 이제 '무엇이 바뀌었는지'(phone)를 구체적으로 남긴다"
    "(수정 전이라면 이 문구는 '#{pid}' 뿐이었다)", _logs_after_5)
chk(_row()["email_source"] == "수집(테스트-대조군)",
    "  phone 만 바뀌었을 땐 email_source 도 여전히 안 건드린다", _row()["email_source"])

# ============================================================
print("\n[6] 실행 — email 을 실제로 고치면 email_source 는 여전히 '직접입력'으로 바뀌는가")
print("    (라운드299 의 원래 취지 — 이제는 실제 변경에만 걸리도록 좁혔을 뿐)")
# ------------------------------------------------------------
body3 = dict(UNCHANGED_BODY); body3["phone"] = "010-9999-0000"  # 이미 반영된 현재값 유지
body3["email"] = "fixed562@real-corp.com"
r3 = admin_c.patch(f"/api/partners/{pid}", headers=_hdr, json=body3)
j3 = r3.get_json() or {}
chk(r3.status_code == 200 and j3.get("ok") and j3.get("unchanged") is not True
    and j3.get("changed", True) is not False,
    "실제 이메일 변경 — 라우트가 정상 200을 돌려준다", (r3.status_code, j3))
chk(_row()["email"] == "fixed562@real-corp.com" and _row()["email_source"] == "직접입력",
    "★★★★★ email 이 실제로 바뀌면 email_source 가 '직접입력'으로 갱신된다"
    "(라운드299 의 취지가 라운드562 이후에도 살아 있다)", _row())
_logs_after_6 = _log_rows()
chk(len(_logs_after_6) == 2 and "email" in _logs_after_6[-1],
    "  감사로그에도 email 이 바뀌었다는 사실이 남는다", _logs_after_6)

# ============================================================
print("\n[7] 실행 — 상태변경(활성→경고, 사유 有)과 일반필드(major) 변경이 겹칠 때")
print("    감사로그가 서술형 상태문구 + 바뀐 필드명을 함께 남기는가")
# ------------------------------------------------------------
body4 = dict(UNCHANGED_BODY); body4["phone"] = "010-9999-0000"
body4["email"] = "fixed562@real-corp.com"
body4["major"] = "방수·방청"
body4["status"] = "경고"
body4["status_reason"] = "검증용 사유입니다(5자 이상)"
r4 = admin_c.patch(f"/api/partners/{pid}", headers=_hdr, json=body4)
j4 = r4.get_json() or {}
chk(r4.status_code == 200 and j4.get("ok"),
    "상태+일반필드 동시변경 — 실제 라우트가 200을 돌려준다", (r4.status_code, j4))
chk(_row()["status"] == "경고" and _row()["major"] == "방수·방청",
    "  DB 반영도 정상이다(회귀 아님)", _row())
_last_log = _log_rows()[-1]
chk("상태 활성→경고" in _last_log and "major" in _last_log,
    "★★★★★ 감사로그에 서술형 상태변경 문구와 실제로 바뀐 일반필드명(major)이 "
    "함께 남는다(형제 api_insurer_update, 라운드561 과 같은 상세도)", _last_log)

# ============================================================
print("\n[8] 실행 — 관계없는 키만 있는 요청은(14개 필드 중 아무것도 없음) DB를")
print("    건드리지 않고 조기에 끝나는가 (라운드562가 바꾼 조건문 회귀 확인)")
# ------------------------------------------------------------
_n_logs_before_8 = len(_log_rows())
r5 = admin_c.patch(f"/api/partners/{pid}", headers=_hdr, json={"unknown_key": "x"})
j5 = r5.get_json() or {}
chk(r5.status_code == 200 and j5.get("ok") and j5.get("unchanged") is not True,
    "  무관한 키만 있으면 DB 조회 없이 곧장 {ok:true} 로 끝난다(형식 보존, "
    "unchanged 키는 안 붙는다 — 애초에 아무 후보도 없었다는 뜻)", j5)
chk(len(_log_rows()) == _n_logs_before_8,
    "  이 경로는 감사로그도 전혀 남기지 않는다(수정 전과 동일한 지름길)",
    (len(_log_rows()), _n_logs_before_8))

# ── 정리 ──────────────────────────────────────────────────────
conn.execute("DELETE FROM activity_log WHERE detail LIKE '%R562%' OR detail LIKE ?", (f"#{pid}%",))
conn.execute("DELETE FROM partners WHERE name='R562업체'")
conn.execute("DELETE FROM admins WHERE username='r562admin'")
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
