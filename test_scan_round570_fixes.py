# -*- coding: utf-8 -*-
"""스캔 570라운드 회귀 — 연락처 개별수정(api_contact_update, PATCH
   /api/contacts/<pid>)의 일반 필드 루프(phone/email/email2/manager/
   contact_note)가 "본문에 그 키가 있는가"만 보고 실제로 값이 바뀌었는지는
   보지 않던 결함 + email_source 강제갱신이 "email이 실제로 바뀌었는가"가
   아니라 "email 키가 본문에 있는가"로 걸려 있던 결함(직접조사, 하위위임 없음).

   조사 배경 — 이 세션이 이미 닫은 "값이 안 바뀌어도 UPDATE+감사로그" 7건
   (api_admin_update·api_partner_profile_update·api_insurer_profile_update·
   api_me_update·api_defect_update·api_insurer_update·api_partner_update)과
   같은 클래스의 미발견 인스턴스를 찾으려고 app.py 전체에서 "for f in ("
   패턴(값 대조 없이 무조건 SET 하는 일반 필드 루프)을 전수(grep)했다.
   9089행(api_insurer_update, 라운드561이 이미 고침)·10452행/10497행
   (api_case_edit, 처음부터 `!= (c[f] or "")` 대조를 갖추고 있어 클린)과
   달리, 9473행 api_contact_update(관리자 콘솔 "연락처 관리" 탭의 개별 수정
   — 협력사 자기 마이페이지가 아니라 관리자가 콜드메일 발송 대상 연락처를
   손보는 별도 화면)만 대조가 전혀 없었다.

   실제 영향 — static/admin.js ctSave()(5482행)는 모달을 열 때 이미 갖고 있던
   phone/manager/email/email2/contact_note **다섯 칸을 전부** 손 안 댄 칸까지
   통째로 재전송한다(형제 savePartner()·round240이 이미 문서화한 것과 같은
   관례). 그 결과:
     ① 담당자 메모(contact_note) 한 줄만 고쳐 저장해도 나머지 4칸이 매번
        "바뀐 값"인 양 다시 SET 되고, "연락처 수정" 감사로그도 실제로는
        아무것도 안 바뀐 phone/email/email2/manager까지 "바뀌었다"고 남겼다.
     ② 더 심각한 부수효과 — email_source 갱신 조건이 `if "email" in d:`
        였다. ctSave()가 email 을 매번 동봉하므로, 담당자가 메모나 연락처만
        고쳐도 email_source 가 매번 '직접입력'으로 강제로 바뀐다. 그런데
        collect_emails.py 로 자동수집된 행은 email_source='수집(홈페이지)'로
        표시되고, clean_collected_emails.py(67행)는 정확히 이 표식이 남아
        있는 행만 정리 대상으로 본다 — 담당자가 이메일은 손도 안 대고 메모만
        고쳐도 그 순간부터 그 행은 "사람이 직접 확인한 주소"로 영구 둔갑해
        다시는 정리 대상에 오르지 않는다. 정확히 이 함수의 형제
        (api_partner_profile_update, 라운드544)가 이미 "email이 실제 값을
        바꿨을 때만(=changed)" 남긴다고 고쳐 둔 바로 그 결함이, 이 관리자
        연락처수정 경로에만 이식되지 않은 채 남아 있었다.

   고침 — app.py:api_contact_update 단일 지점(이 결함의 유일한 발생 지점,
   다른 caller 없음).
     · SELECT 를 name 뿐 아니라 phone/email/email2/manager/contact_note/
       email_opt_out/sms_opt_out 까지 넓혀 대조 재료(p)로 쓴다.
     · 일반 필드 루프에 형제(api_partner_profile_update)와 동일한
       `if v == (p.get(f) or ""): continue` 를 추가하고 실제로 바뀐 필드만
       changed 세트에 담는다.
     · email_source 강제갱신 조건을 `"email" in d` → `"email" in changed`
       로 좁힌다(형제와 동일한 기준).
     · email_opt_out/sms_opt_out 두 불리언도 같은 원칙으로 이전값과 대조해
       실제로 토글될 때만 SET+notes 에 담는다(원래 무조건 SET 이었다).

   이 회귀테스트는 ONLY 안전한 기법만 쓴다 — on-disk app.py 는 조회만 하고,
   "되돌리기" 증명은 옛(대조 없던) 루프 핵심부만 별도 문자열로 재구성해
   exec() 로 인과관계를 실측한다(round562 와 같은 기법). 그 다음 실제
   라이브 라우트(Flask test_client)로 관리자 세션을 통해 종단까지 확인한다.

      python test_scan_round570_fixes.py
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
print("  스캔 570라운드 회귀 — 연락처 개별수정 일반필드 미변경 재기록 + email_source 오갱신")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — app.py 의 api_contact_update 가 실제로 고쳐졌는가")
# ------------------------------------------------------------
APP_SRC = read("app.py")
_cu_start = APP_SRC.index("\ndef api_contact_update(pid):")
_cu_end = APP_SRC.index("\n@app.", _cu_start + 10)
CU_SRC = APP_SRC[_cu_start:_cu_end]

chk('"email_opt_out, sms_opt_out FROM partners WHERE id=?"' in CU_SRC,
    "★★★★★ prev 조회(SELECT)가 phone/email/email2/manager/contact_note/opt_out 까지 넓어졌다")
chk("changed = set()" in CU_SRC,
    "★★★★★ 실제로 바뀐 필드만 담는 changed 세트가 신설됐다")
chk('if v == (p.get(f) or ""):' in CU_SRC and "continue" in CU_SRC,
    "★★★★★ 일반 필드 루프가 이전값과 대조해 실제로 바뀔 때만 sets/notes 에 담는다")
chk('if "email" in changed:' in CU_SRC,
    "★★★★★ email_source 강제갱신이 이제 '본문에 키가 있는가'가 아니라 '실제로 바뀌었는가'로 걸린다")
chk('if "email" in d:' not in CU_SRC,
    "★★★★ 옛 조건(\"email\" in d)이 더 이상 이 함수 안에 없다")
chk('sets.append("email_source=?"); vals.append("직접입력")' in CU_SRC,
    "  회귀 방지: 라운드299 의 email_source 갱신 자체는 그대로 남아 있다(조건만 좁혀짐)")
chk("if nv == (p.get(f) or 0):" in CU_SRC,
    "★★★★ email_opt_out/sms_opt_out 두 불리언도 이전값과 대조해 실제로 바뀔 때만 SET 한다")
chk('return jsonify({"ok": True, "unchanged": True})' in CU_SRC,
    "  회귀 방지: 아무 것도 안 바뀌면 형제들과 같은 unchanged:True 를 그대로 돌려준다")

# 회귀 방지 — 기존 방어들이 그대로 남아 있어야 한다
chk("RE_PHONE.match(v)" in CU_SRC, "  회귀 방지: 라운드484 연락처 형식 검사가 그대로다")
chk("RE_EMAIL.match(v)" in CU_SRC, "  회귀 방지: email·email2 이메일 형식 검사가 그대로다")
chk('sets.append("contact_updated=?")' in CU_SRC, "  회귀 방지: contact_updated 갱신이 그대로다")
chk('DB.log(conn, actor(), "연락처 수정"' in CU_SRC, "  회귀 방지: 감사로그 액션명이 그대로다")

# ============================================================
print("\n[2] 되돌리기 — 옛(대조 없는) 루프 핵심부를 그대로 실행하면 실제로")
print("    아무 값도 안 바뀌었는데 email_source 까지 강제로 덮이는가 (인과관계 실측)")
# ------------------------------------------------------------
FIELDS = ("phone", "email", "email2", "manager", "contact_note")
UNCHANGED_BODY = {
    "phone": "010-1111-2222", "email": "old570@test.com",
    "email2": "old570-2@test.com", "manager": "김담당", "contact_note": "기존 메모",
}

#  ⚠ 안전 규칙 — on-disk app.py 는 전혀 건드리지 않는다. 옛(대조 없던) 루프
#    핵심부만 별도 문자열로 재구성해 exec() 로 스크래치 네임스페이스에서
#    돌린다(round562 의 OLD_LOOP_CORE 와 같은 기법).
OLD_LOOP_CORE = (
    "sets, notes = [], []\n"
    "for f in FIELDS:\n"
    "    if f in d:\n"
    "        v = d[f]\n"
    "        sets.append(f + '=?'); notes.append(f)\n"
    "if 'email' in d:\n"
    "    sets.append('email_source=?')\n"
)
_old_ns = {"d": dict(UNCHANGED_BODY), "FIELDS": FIELDS}
exec(OLD_LOOP_CORE, {}, _old_ns)
chk(_old_ns["sets"] == [f + "=?" for f in FIELDS] + ["email_source=?"],
    "★★★★★ 옛 루프(대조 없음)를 그대로 실행하면 값이 하나도 안 바뀌었는데도 "
    "필드 5개 + email_source 까지 전부 SET 대상으로 잡힌다(수정 전 실제 증상을 "
    "인과관계로 증명)", _old_ns["sets"])

#  새(라운드570) 루프 핵심부 — 같은 입력(전부 미변경)을 넣으면 아무 것도 안 걸린다.
NEW_LOOP_CORE = (
    "sets, notes, changed = [], [], set()\n"
    "for f in FIELDS:\n"
    "    if f in d:\n"
    "        v = d[f]\n"
    "        if v == (p.get(f) or ''):\n"
    "            continue\n"
    "        sets.append(f + '=?'); notes.append(f); changed.add(f)\n"
    "if 'email' in changed:\n"
    "    sets.append('email_source=?')\n"
)
_new_ns = {"d": dict(UNCHANGED_BODY), "FIELDS": FIELDS, "p": dict(UNCHANGED_BODY)}
exec(NEW_LOOP_CORE, {}, _new_ns)
chk(_new_ns["sets"] == [] and _new_ns["changed"] == set(),
    "★★★★★ 새 루프(대조 있음)는 같은 입력(전부 미변경)에 대해 SET 대상이 "
    "0개다(email_source 도 포함해 전혀 안 건드림)", _new_ns["sets"])

#  대조군 — contact_note 하나만 실제로 바뀌어도(email 은 그대로) 옛 루프는
#  여전히 email_source 를 강제로 덮지만, 새 루프는 email 이 실제로 안
#  바뀌었으니 email_source 를 안 건드린다. 바로 이 결함의 핵심 증거다.
_only_note_changed = dict(UNCHANGED_BODY, contact_note="고친 메모")
_old_ns2 = {"d": _only_note_changed, "FIELDS": FIELDS}
exec(OLD_LOOP_CORE, {}, _old_ns2)
chk("email_source=?" in _old_ns2["sets"],
    "★★★★★★ (핵심 증거) 옛 루프는 contact_note 만 바뀌어도 email 은 그대로인데 "
    "email_source 를 강제로 SET 대상에 넣는다", _old_ns2["sets"])

_new_ns2 = {"d": dict(_only_note_changed), "FIELDS": FIELDS, "p": dict(UNCHANGED_BODY)}
exec(NEW_LOOP_CORE, {}, _new_ns2)
chk(_new_ns2["changed"] == {"contact_note"} and "email_source=?" not in _new_ns2["sets"],
    "★★★★★★ (핵심 증거) 새 루프는 같은 입력에서 changed={'contact_note'} 뿐이고 "
    "email_source 는 SET 대상에서 빠진다(이 라운드가 고친 정확한 인과관계)",
    (_new_ns2["changed"], _new_ns2["sets"]))

# ============================================================
print("\n[3] 준비 — 스크래치 DB(오늘자 실제 스키마) + 관리자 세션")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round570_")
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
             "VALUES('r570admin','x','검증','최고관리자')")
conn.execute(
    "INSERT INTO partners(name,partner_type,status,phone,email,email2,manager,"
    "contact_note,email_opt_out,sms_opt_out,email_source,created_at) "
    "VALUES('R570업체','시공사','활성',:phone,:email,:email2,:manager,"
    ":contact_note,0,0,'수집(홈페이지)',:now)",
    dict(UNCHANGED_BODY, now=DB.now()))
conn.commit()
pid = conn.execute("SELECT id FROM partners WHERE name='R570업체'").fetchone()["id"]


def _row():
    return dict(conn.execute("SELECT * FROM partners WHERE id=?", (pid,)).fetchone())


def _log_rows():
    return [r["detail"] for r in conn.execute(
        "SELECT detail FROM activity_log WHERE action='연락처 수정' "
        "ORDER BY id").fetchall()]


admin_c = A.app.test_client()
_tok = "r570-csrf"
with admin_c.session_transaction() as sess:
    sess["admin"] = "r570admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
    sess["_csrf"] = _tok
_hdr = {"X-CSRF-Token": _tok}

# ============================================================
print("\n[4] 실행 — 실제 라이브 라우트(PATCH /api/contacts/<id>)로 admin.js")
print("    ctSave() 와 같이 5칸을 아무것도 안 고치고 그대로 재전송하면")
# ------------------------------------------------------------
r1 = admin_c.patch(f"/api/contacts/{pid}", headers=_hdr,
                    json=dict(UNCHANGED_BODY, email_opt_out=False))
j1 = r1.get_json() or {}
chk(r1.status_code == 200 and j1.get("ok") and j1.get("unchanged") is True,
    "★★★★★ 아무 값도 안 바뀐 전체 재전송은 unchanged:True 를 돌려준다"
    "(더 이상 UPDATE 를 실제로 실행하지 않는다)", j1)
chk(_log_rows() == [],
    "★★★★★ 감사로그(activity_log)에 '연락처 수정' 행이 단 하나도 안 생겼다", _log_rows())
chk(_row()["email_source"] == "수집(홈페이지)",
    "★★★★★ email 이 안 바뀌었으면 email_source 도 안 건드린다(수정 전이었다면 "
    "이 재전송 한 번만으로 '직접입력'으로 덮어써졌을 것)", _row()["email_source"])

# ============================================================
print("\n[5] 실행 — contact_note(메모) 한 칸만 고치고 나머지 4칸은 그대로")
print("    재전송하면 (담당자가 실제로 하는 가장 흔한 동작)")
# ------------------------------------------------------------
body2 = dict(UNCHANGED_BODY, contact_note="고친 메모", email_opt_out=False)
r2 = admin_c.patch(f"/api/contacts/{pid}", headers=_hdr, json=body2)
j2 = r2.get_json() or {}
chk(r2.status_code == 200 and j2.get("ok") and j2.get("unchanged") is not True,
    "실제로 값이 바뀌면 unchanged 없이 정상 저장된다", j2)
chk(_row()["contact_note"] == "고친 메모" and _row()["phone"] == "010-1111-2222"
    and _row()["email"] == "old570@test.com",
    "  실제로 바뀐 값(contact_note)만 반영되고 나머지 필드는 그대로다", _row())
_logs_after_5 = _log_rows()
chk(len(_logs_after_5) == 1 and _logs_after_5[-1].strip().endswith("contact_note")
    and "phone" not in _logs_after_5[-1] and "email" not in _logs_after_5[-1],
    "★★★★★ 감사로그가 실제로 바뀐 필드(contact_note)만 남기고, 안 바뀐 "
    "phone·email·email2·manager 는 끼워 넣지 않는다(수정 전이라면 5개 전부가 "
    "'바뀐 값'인 양 남았을 것)", _logs_after_5)
chk(_row()["email_source"] == "수집(홈페이지)",
    "★★★★★★ (핵심) 메모만 고쳤을 뿐 email 은 그대로인데 email_source 가 여전히 "
    "'수집(홈페이지)'다 — 수정 전이었다면 이 저장 한 번으로 '직접입력'으로 "
    "영구 둔갑해 clean_collected_emails.py 청소 대상에서 영원히 빠졌을 것",
    _row()["email_source"])

# ============================================================
print("\n[6] 실행 — email 을 실제로 고치면 email_source 는 여전히 '직접입력'으로")
print("    바뀌는가 (라운드299 의 원래 취지 — 실제 변경에만 걸리도록 좁혔을 뿐)")
# ------------------------------------------------------------
body3 = dict(UNCHANGED_BODY, contact_note="고친 메모", email="fixed570@real-corp.com",
             email_opt_out=False)
r3 = admin_c.patch(f"/api/contacts/{pid}", headers=_hdr, json=body3)
j3 = r3.get_json() or {}
chk(r3.status_code == 200 and j3.get("ok"),
    "실제 이메일 변경 — 라우트가 정상 200을 돌려준다", (r3.status_code, j3))
chk(_row()["email"] == "fixed570@real-corp.com" and _row()["email_source"] == "직접입력",
    "★★★★★ email 이 실제로 바뀌면 email_source 가 '직접입력'으로 갱신된다"
    "(라운드299 의 취지가 라운드570 이후에도 살아 있다)", _row())
_logs_after_6 = _log_rows()
chk(len(_logs_after_6) == 2 and "email" in _logs_after_6[-1],
    "  감사로그에도 email 이 바뀌었다는 사실이 남는다", _logs_after_6)

# ============================================================
print("\n[7] 실행 — email_opt_out 을 같은 값(False)으로 재전송 vs 실제로 토글")
# ------------------------------------------------------------
_n_logs_before_7 = len(_log_rows())
body4 = dict(UNCHANGED_BODY, contact_note="고친 메모", email="fixed570@real-corp.com",
             email_opt_out=False)
r4 = admin_c.patch(f"/api/contacts/{pid}", headers=_hdr, json=body4)
j4 = r4.get_json() or {}
chk(r4.status_code == 200 and j4.get("ok") and j4.get("unchanged") is True,
    "★★★★ email_opt_out 을 이미 있는 값(False)그대로 재전송하면 unchanged:True",
    j4)
chk(len(_log_rows()) == _n_logs_before_7,
    "  불리언이 그대로면 감사로그도 안 남는다", (len(_log_rows()), _n_logs_before_7))

body5 = dict(body4, email_opt_out=True)
r5 = admin_c.patch(f"/api/contacts/{pid}", headers=_hdr, json=body5)
j5 = r5.get_json() or {}
chk(r5.status_code == 200 and j5.get("ok") and j5.get("unchanged") is not True
    and _row()["email_opt_out"] == 1,
    "★★★★ email_opt_out 을 실제로 토글(False→True)하면 정상 반영된다", (j5, _row()))
_logs_after_7 = _log_rows()
chk(len(_logs_after_7) == _n_logs_before_7 + 1 and "email_opt_out" in _logs_after_7[-1],
    "  실제 토글은 감사로그에 email_opt_out 하나만 남긴다", _logs_after_7)

# ============================================================
print("\n[8] 실행 — 5칸 다 무관한 값(현재값)뿐이고 email 도 없는 요청은 완전히")
print("    조용한 no-op 인가 (email_source 갱신 줄 자체가 실행되지 않아야 한다)")
# ------------------------------------------------------------
_n_logs_before_8 = len(_log_rows())
r6 = admin_c.patch(f"/api/contacts/{pid}", headers=_hdr,
                    json={"manager": _row()["manager"]})
j6 = r6.get_json() or {}
chk(r6.status_code == 200 and j6.get("ok") and j6.get("unchanged") is True,
    "  manager 만 같은 값으로 보내면 unchanged:True(email 키 자체가 없다)", j6)
chk(len(_log_rows()) == _n_logs_before_8 and _row()["email_source"] == "직접입력",
    "  이 경로도 로그·email_source 어느 쪽도 건드리지 않는다", _row())

# ── 정리 ──────────────────────────────────────────────────────
conn.execute("DELETE FROM activity_log WHERE detail LIKE 'R570업체%'")
conn.execute("DELETE FROM partners WHERE name='R570업체'")
conn.execute("DELETE FROM admins WHERE username='r570admin'")
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
