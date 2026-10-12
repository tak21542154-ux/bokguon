# -*- coding: utf-8 -*-
"""스캔 615라운드 회귀 — 입점신청 상태변경(api_application_update,
PATCH /api/applications/<id>)의 elif 분기(서류검토·반려 등 '승인'이 아닌
상태변경)에 상태값 화이트리스트가 없던 결함, 1건.

형제 셋(LEAD_STATUSES round614·PARTNER_STATUSES round101·INSURER_STATUSES
round136)은 전부 상태값 화이트리스트가 있는데 이 신청서 상태만 없었다 —
round614가 고친 api_lead_update의 형제(같은 PATCH류 상태변경 라우트)를
훑다가 발견. '승인' 분기(`if new_status == "승인":`)는 정확일치 비교라
우연히 안전했지만, 그 다음 `elif new_status:` 분기는 화면(admin.js
appAct, 서류검토·승인·반려 버튼 3개만 보냄)과 무관하게 임의 문자열을
검증 없이 그대로 `UPDATE partner_applications SET status=?`에 태웠다.
잘못 들어간 값은 이 표를 `WHERE status IN ('신규','서류검토')`로 훑는
대기 배지·드릴다운·통계 4곳(app.py 7357·7419·7584·17931행 부근)에서
조용히 사라져, 아무도 결정 안 내린 신청서가 "대기 0건"처럼 보이며
영원히 방치될 수 있었다 — 이 저장소가 반복해서 잡아 온 "화면에서
사라지는" 부류의 결함이다.

고침: APPLICATION_STATUSES=("신규","서류검토","승인","반려") 신설
(LEAD_STATUSES와 동일한 4값 관례) + new_status를 읽은 직후 한 번만
화이트리스트 검사 — 두 분기('승인'·elif) 모두 보호. 새 메커니즘 없음.

[1] 소스 확인.
[2]~[4] 실제 Flask 앱으로 확인 + 되돌림-증명 — api_application_update는
단일 라우트 핸들러라 A.app.view_functions 딕셔너리 항목만 잠깐 치환한다
(이 함수 자신의 현재 소스에서 신설 화이트리스트 검사만 제거한 사본을
exec로 재구성, require_role 데코레이터도 다시 입힘). 진짜 app.py 파일은
전혀 안 쓴다 — 처음부터 이 안전한 기법으로 작성한다(디스크 revert
방식은 애초에 쓰지 않음).
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(HERE, "app.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 615라운드 회귀 — 입점신청 상태변경 화이트리스트 부재")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
chk('APPLICATION_STATUSES = ("신규", "서류검토", "승인", "반려")' in APP_SRC,
    "★★★★★ APPLICATION_STATUSES 화이트리스트가 신설됐다")

NEW_GUARD = '''    new_status = d.get("status")
    if new_status and new_status not in APPLICATION_STATUSES:
        conn.rollback(); conn.close()
        return jsonify({"ok": False, "error": f"알 수 없는 신청 상태입니다: {new_status}"}), 400
    if "note" in d:'''

OLD_GUARD = '''    new_status = d.get("status")
    if "note" in d:'''

chk(NEW_GUARD in APP_SRC, "★★★★★ api_application_update()에 화이트리스트 검사 코드가 있다")
chk(APP_SRC.count(NEW_GUARD) == 1,
    "되돌림-증명에 쓸 새 블록이 소스에 정확히 1번만 있다(대체 지점 특정 가능)",
    APP_SRC.count(NEW_GUARD))


def _py_fn_body(src, fn_name):
    """함수 본문 — 다음 def뿐 아니라 다음 라우트의 @app. 데코레이터가 먼저
    나오면 거기서 자른다(round610 정착 기법)."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


_body = _py_fn_body(APP_SRC, "api_application_update")
chk(NEW_GUARD in _body, "  api_application_update() 본문 안에 NEW_GUARD가 있다")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round615_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('r615admin','x','검증','최고관리자')")
    conn0.commit()
    conn0.close()

    def _admin_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["admin"] = "r615admin"; sess["admin_role"] = "최고관리자"
            sess["_csrf"] = "r615-csrf"
        return c

    def _patch(path, **kw):
        return _admin_client().patch(path, headers={"X-CSRF-Token": "r615-csrf"}, **kw)

    def _new_app_row(company):
        c = DB.get_db()
        aid = c.execute(
            "INSERT INTO partner_applications(company,major,status,created_at) "
            "VALUES(?,?,?,?)", (company, "가드레일·방호울타리", "신규", DB.now())).lastrowid
        c.commit(); c.close()
        return aid

    def _app_status(aid):
        c = DB.get_db()
        r = c.execute("SELECT status FROM partner_applications WHERE id=?", (aid,)).fetchone()
        c.close()
        return r["status"] if r else None

    print("\n[3] 실행 — 현재(고쳐진) 코드")
    aid1 = _new_app_row("R615업체1")
    r1 = _patch(f"/api/applications/{aid1}", json={"status": "완전히없는상태"})
    chk(r1.status_code == 400,
        "★★★★★ 화면이 안 쓰는 임의 status 문자열은 400으로 거부된다"
        "(고치기 전엔 그대로 저장됐다)", r1.get_json())
    chk(_app_status(aid1) == "신규", "  거부된 값이 실제로 저장 안 됐다(원래값 유지)", _app_status(aid1))

    r2 = _patch(f"/api/applications/{aid1}", json={"status": "서류검토"})
    chk(r2.status_code == 200 and r2.get_json().get("ok") is True,
        "  화면이 실제로 쓰는 정상값은 그대로 통과한다(회귀없음)", r2.get_json())
    chk(_app_status(aid1) == "서류검토", "  정상값이 실제로 반영됐다", _app_status(aid1))

    aid_missing = 999999
    r3 = _patch(f"/api/applications/{aid_missing}", json={"status": "서류검토"})
    chk(r3.status_code == 404, "  없는 aid는 여전히 404로 거부된다(기존 존재확인 회귀없음)",
        r3.get_json())

    # ══════════════════════════════════════════════════════════
    print("\n[4] 되돌리기 — api_application_update만 옛 코드로(실제 파일은 안 건드림)")
    # ────────────────────────────────────────────────────────
    _old_body = (_body
                 .replace("def api_application_update(aid):",
                          "def _api_application_update_pre615(aid):", 1)
                 .replace(NEW_GUARD, OLD_GUARD, 1))
    chk(_old_body.count(OLD_GUARD) == 1 and "_api_application_update_pre615" in _old_body,
        "  (준비) 함수 리네임 + 화이트리스트 검사 제거가 정확히 적용됐다"
        "(실제 파일은 안 건드림)")

    _ns = dict(vars(A))
    exec(compile(_old_body, "<round615_pre615_application_update>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_fn = A.require_role("중간관리자")(_ns["_api_application_update_pre615"])

    _orig_view = A.app.view_functions["api_application_update"]
    A.app.view_functions["api_application_update"] = old_fn
    aid2 = _new_app_row("R615업체2")
    try:
        r_old = _patch(f"/api/applications/{aid2}", json={"status": "완전히없는상태2"})
        broken_status = _app_status(aid2)
    finally:
        A.app.view_functions["api_application_update"] = _orig_view

    chk(r_old.status_code == 200 and r_old.get_json().get("ok") is True,
        "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림)는 임의 status 문자열도 "
        "200 성공으로 그대로 저장한다 — 이 테스트가 진짜 결함을 잡아낼 능력이 "
        "있음을 증명", r_old.get_json())
    chk(broken_status == "완전히없는상태2",
        "★★★★★ 옛 코드(되돌림)는 화이트리스트 밖 문자열을 실제로 DB에 저장한다",
        broken_status)

    print("\n[5] 원복 확인 — 되돌리기 이후 다시 방어되는가(바꿔치기가 안 샜다)")
    chk(A.app.view_functions["api_application_update"] is _orig_view,
        "  view_functions가 원래 함수객체로 복원됐다")
    aid3 = _new_app_row("R615업체3")
    r_restored = _patch(f"/api/applications/{aid3}", json={"status": "또다른없는상태"})
    chk(r_restored.status_code == 400 and _app_status(aid3) == "신규",
        "★★★★ 원복 후에는 다시 400으로 정상 방어된다(바꿔치기가 안 샜다)",
        (r_restored.status_code, _app_status(aid3)))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__}: {e}")

APP_HASH_AFTER = read("app.py")
chk(APP_HASH_AFTER == APP_SRC,
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
