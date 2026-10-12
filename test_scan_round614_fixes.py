# -*- coding: utf-8 -*-
"""스캔 614라운드 회귀 — 도입문의 상태변경(api_lead_update, PATCH /api/leads/<id>)
에 존재확인(404)도 status 화이트리스트도 없던 결함, 2건(한 함수, 한 지점).

직접 가장 가까운 형제(api_application_update, app.py:8067행 부근 — 입점신청의
같은 PATCH류 상태변경 라우트)를 대조하며 발견했다: 그 형제는 lid가 없으면
404를 돌려주는데 여기(api_lead_update)만 존재확인이 아예 없어, 없는 lid로
호출해도 `UPDATE ... WHERE id=?`이 조용히 0행 적용된 채 `{"ok":true}`를 그대로
돌려줬다 — 이 저장소가 반복해서 잡아 온 "지웠다는데 안 지워지는" 부류의 거짓
성공이다. status 값도 이 앱의 다른 상태값들(SEVERITY_VALUES·PARTNER_STATUSES·
INSURER_STATUSES, 각각 defects·partners·insurers)과 달리 화이트리스트 대조가
전혀 없어, 화면(admin.js leadDetail)이 실제로 보내는 값 3종(검토중·승인·반려)
밖의 임의 문자열이나 null이 그대로 저장될 수 있었다 — 목록 필터·배지
(F=['전체','신규','검토중','승인','반려'])가 그 값을 인식 못 하고 조용히 놓친다.

고침: LEAD_STATUSES 화이트리스트 신설(기존 SEVERITY_VALUES 관례와 동일한
모양) + 함수 맨 앞에서 lid 존재를 한 번만 확인(상태변경·메모 두 분기 모두
보호) — 새 메커니즘 없음, 이 저장소에 이미 있는 두 관례를 이 자리에도
적용했을 뿐이다.

[1] 소스 확인.
[2]~[3] 실제 Flask 앱으로 확인 + 되돌림-증명 — api_lead_update는 단일 라우트
핸들러라 A.app.view_functions 딕셔너리 항목만 잠깐 치환한다(이 함수 자신의
현재 소스에서 신설 블록만 제거한 사본을 exec로 재구성, require_admin
데코레이터도 다시 입힘). 진짜 app.py 파일은 전혀 안 쓴다 — 처음부터 이
안전한 기법으로 작성한다(디스크 revert 방식은 애초에 쓰지 않음).
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
print("  스캔 614라운드 회귀 — 도입문의 상태변경 존재확인·상태값 화이트리스트 부재")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
chk('LEAD_STATUSES = ("신규", "검토중", "승인", "반려")' in APP_SRC,
    "★★★★★ LEAD_STATUSES 화이트리스트가 신설됐다")

NEW_BLOCK = '''    #  ⚠⚠ [라운드614] 형제(api_application_update, 8067행 부근)는 존재확인(404)을
    #    이미 하는데 여기만 없었다 — 없는 lid로 호출해도 UPDATE가 조용히 0행
    #    적용된 채 {"ok":true}를 그대로 돌려줘 "지웠다는데 안 지워지는" 부류의
    #    거짓 성공이 났다(실제로 아무 것도 안 바뀌어도 성공 응답). status 값도
    #    이 앱의 다른 상태값들(SEVERITY_VALUES·PARTNER_STATUSES·INSURER_STATUSES)
    #    과 달리 화이트리스트 대조가 전혀 없어, 화면이 실제로 보내는 값 3종
    #    (검토중·승인·반려) 밖의 임의 문자열이나 null이 그대로 저장돼 목록
    #    필터·배지(F=['전체','신규','검토중','승인','반려'], admin.js)가 그 값을
    #    인식 못 하고 조용히 놓칠 수 있었다.
    l = one(conn.execute("SELECT id FROM insurer_leads WHERE id=?", (lid,)))
    if not l:
        conn.close(); return jsonify({"ok": False, "error": "문의를 찾을 수 없습니다."}), 404
    if "status" in d:
        if d["status"] not in LEAD_STATUSES:
            conn.close()
            return jsonify({"ok": False,
                            "error": f"상태는 {'/'.join(LEAD_STATUSES)} 중 하나여야 합니다."}), 400
        conn.execute("UPDATE insurer_leads SET status=? WHERE id=?", (d["status"], lid))'''

OLD_CALL = '''    if "status" in d:
        conn.execute("UPDATE insurer_leads SET status=? WHERE id=?", (d["status"], lid))'''

chk(NEW_BLOCK in APP_SRC, "★★★★★ api_lead_update()에 존재확인+화이트리스트 코드가 있다")
chk(APP_SRC.count(NEW_BLOCK) == 1,
    "되돌림-증명에 쓸 새 블록이 소스에 정확히 1번만 있다(대체 지점 특정 가능)",
    APP_SRC.count(NEW_BLOCK))


def _py_fn_body(src, fn_name):
    """함수 본문 — 다음 def뿐 아니라 다음 라우트의 @app. 데코레이터가 먼저
    나오면 거기서 자른다(round610 정착 기법)."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


_body = _py_fn_body(APP_SRC, "api_lead_update")
chk(NEW_BLOCK in _body, "  api_lead_update() 본문 안에 NEW_BLOCK이 있다")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round614_")
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
                  "VALUES('r614admin','x','검증','최고관리자')")
    lid = conn0.execute(
        "INSERT INTO insurer_leads(company,org_type,name,phone,status,created_at) "
        "VALUES('R614보험사','보험사','검증담당','010-0000-0000','신규',?)",
        (DB.now(),)).lastrowid
    conn0.commit()
    conn0.close()

    def _admin_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["admin"] = "r614admin"; sess["admin_role"] = "최고관리자"
            sess["_csrf"] = "r614-csrf"
        return c

    def _patch(path, **kw):
        return _admin_client().patch(path, headers={"X-CSRF-Token": "r614-csrf"}, **kw)

    def _lead_status():
        c = DB.get_db()
        r = c.execute("SELECT status FROM insurer_leads WHERE id=?", (lid,)).fetchone()
        c.close()
        return r["status"] if r else None

    print("\n[3] 실행 — 현재(고쳐진) 코드")
    r1 = _patch("/api/leads/999999", json={"status": "검토중"})
    chk(r1.status_code == 404,
        "★★★★★ 없는 lid는 404로 거부된다(고치기 전엔 200 거짓성공이었다)", r1.get_json())

    r2 = _patch(f"/api/leads/{lid}", json={"status": "완전히없는상태"})
    chk(r2.status_code == 400,
        "★★★★★ 화면이 안 쓰는 임의 status 문자열은 400으로 거부된다"
        "(고치기 전엔 그대로 저장됐다)", r2.get_json())
    chk(_lead_status() == "신규", "  거부된 값이 실제로 저장 안 됐다(원래값 유지)", _lead_status())

    r3 = _patch(f"/api/leads/{lid}", json={"status": "검토중"})
    chk(r3.status_code == 200 and r3.get_json().get("ok") is True,
        "  화면이 실제로 쓰는 정상값은 그대로 통과한다(회귀없음)", r3.get_json())
    chk(_lead_status() == "검토중", "  정상값이 실제로 반영됐다", _lead_status())

    # ══════════════════════════════════════════════════════════
    print("\n[4] 되돌리기 — api_lead_update만 옛 코드로(실제 파일은 안 건드림)")
    # ────────────────────────────────────────────────────────
    _old_body = (_body
                 .replace("def api_lead_update(lid):", "def _api_lead_update_pre614(lid):", 1)
                 .replace(NEW_BLOCK, OLD_CALL, 1))
    chk(_old_body.count(OLD_CALL) == 1 and "_api_lead_update_pre614" in _old_body,
        "  (준비) 함수 리네임 + 존재확인·화이트리스트 제거가 정확히 적용됐다"
        "(실제 파일은 안 건드림)")

    _ns = dict(vars(A))
    exec(compile(_old_body, "<round614_pre614_lead_update>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_fn = A.require_admin(_ns["_api_lead_update_pre614"])

    _orig_view = A.app.view_functions["api_lead_update"]
    A.app.view_functions["api_lead_update"] = old_fn
    try:
        r_old1 = _patch("/api/leads/999999", json={"status": "검토중"})
        r_old2 = _patch(f"/api/leads/{lid}", json={"status": "완전히없는상태"})
        broken_status = _lead_status()
    finally:
        A.app.view_functions["api_lead_update"] = _orig_view

    chk(r_old1.status_code == 200 and r_old1.get_json().get("ok") is True,
        "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림)는 없는 lid에도 200 거짓성공을 "
        "돌려준다 — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", r_old1.get_json())
    chk(r_old2.status_code == 200 and broken_status == "완전히없는상태",
        "★★★★★ 옛 코드(되돌림)는 임의 status 문자열도 그대로 저장한다"
        " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", broken_status)

    print("\n[5] 원복 확인 — 되돌리기 이후 다시 방어되는가(바꿔치기가 안 샜다)")
    chk(A.app.view_functions["api_lead_update"] is _orig_view,
        "  view_functions가 원래 함수객체로 복원됐다")
    r_restored1 = _patch("/api/leads/999999", json={"status": "검토중"})
    r_restored2 = _patch(f"/api/leads/{lid}", json={"status": "또다른없는상태"})
    chk(r_restored1.status_code == 404 and r_restored2.status_code == 400,
        "★★★★ 원복 후에는 다시 404·400 둘 다 정상 방어된다(바꿔치기가 안 샜다)",
        (r_restored1.status_code, r_restored2.status_code))

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
