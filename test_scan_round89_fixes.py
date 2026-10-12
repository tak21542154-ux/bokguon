# -*- coding: utf-8 -*-
"""스캔 89라운드 회귀 — 하자 귀책(cost_bearer) 조정 화면 입구 부재.

  api_defect_update(서버)는 cost_bearer 를 완전히 지원한다 — 필드 반영,
  이의(dispute) 검토완료 처리, 알림, 평점 재계산까지 전부 되어 있다(61라운드).
  그런데 admin.js 의 하자 상세 모달은 협력사 이의에 "비용 부담을 조정하거나…"
  라고 담당자에게 지시만 하고, 정작 그 값을 보낼 셀렉트박스가 화면에 아예
  없었다 — defectAct() 는 항상 {status, resolution} 만 보냈다. 서버 기능은
  멀쩡한데 화면에 입구가 없어 담당자가 절대 귀책을 못 바꾸는 상태였다.

  부수 결함: 서버가 상태-불변(status===row.status) 이면 다른 필드도 안 보고
  조용히 끝내므로, "이미 확인중인 하자에서 귀책만 고치기" 케이스는 status 를
  아예 안 보내야 한다 — 화면도 함께 고친다.

      python test_scan_round89_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


ADMIN_JS = read(os.path.join("static", "admin.js"))

print("═" * 72)
print("  스캔 89라운드 회귀 — 하자 귀책(cost_bearer) 조정 화면 입구 부재")
print("═" * 72)


def _js_fn_body(src, header):
    start = src.index(header)
    depth = 0
    i = src.index("{", start)
    j = i
    while True:
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
        j += 1


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스: defectDetail 모달에 귀책 셀렉트박스가 있다")
# ──────────────────────────────────────────────────────────────
detail_fn = _js_fn_body(ADMIN_JS, "function defectDetail(id){")
chk('id="d_cb"' in detail_fn, "★★★ 귀책(cost_bearer) 셀렉트박스(#d_cb)가 모달에 있다")
chk('value="시행사"' in detail_fn and 'value="협의필요"' in detail_fn,
    "STEP 두 유효값(시행사/협의필요)이 옵션으로 있다")
chk("d.cost_bearer==='시행사'?'selected'" in detail_fn.replace(" ", ""),
    "STEP 현재 값이 기본 선택으로 반영된다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 소스: defectAct 가 바뀐 경우에만 cost_bearer 를 보내고,")
print("          상태-불변이면 status 를 생략해 서버 지름길을 피한다")
# ──────────────────────────────────────────────────────────────
act_fn = _js_fn_body(ADMIN_JS, "async function defectAct(id, status){")
chk("cb !== d.cost_bearer" in act_fn,
    "★★★ cost_bearer 는 실제로 바뀐 경우에만 요청에 포함된다")
chk("if (!unchanged) body.status = status;" in act_fn or "if(!unchanged)body.status=status;"
    in act_fn.replace(" ", ""),
    "★★ 상태가 안 바뀌면 status 자체를 안 보낸다(서버의 '이미 그 상태' 지름길 회피)")
chk("status === d.status" in act_fn.replace(" ", " ").replace("status===d.status", "status === d.status")
    or "status===d.status" in act_fn.replace(" ", ""),
    "STEP 상태-불변 판정이 현재 하자의 실제 status 와 비교한다")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행: cost_bearer 단독 PATCH(상태 없음)로도 이의가 정상 처리된다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round89_")
_dbpath = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_DB_PATH"] = _dbpath
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','중간관리자')")
    iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R89보험','활성')").lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R89업체','시행사','활성')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,partner_id,partner_name) "
        "VALUES('R89-1','완료',?,?,?,?,?)",
        ("가드레일", "서울", iid, pid, "R89업체")).lastrowid
    did = conn.execute(
        """INSERT INTO defects(defect_no,case_id,case_no,insurer,insurer_id,partner_id,partner_name,
                               category,region,title,status,due_date,cost_bearer,warranty_ok,
                               dispute_reason,disputed_at,created_at)
           VALUES('D26-9001',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (cid, "R89-1", "R89보험", iid, pid, "R89업체", "가드레일", "서울",
         "난간 도색 벗겨짐", "확인중", "2027-01-01", "시행사", 1,
         "저희 시공 전부터 있던 하자입니다", DB.now(), DB.now())).lastrowid
    conn.commit(); conn.close()

    admin = A.app.test_client()
    _tok = "r89-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok, "Content-Type": "application/json"}

    # JS 가 이제 만들어 보내는 것과 같은 모양의 요청 — status 없이 cost_bearer 만.
    r = admin.patch(f"/api/defects/{did}",
                     json={"resolution": "사진 대조 결과 협력사 시공 전 기존 하자로 확인됨",
                           "cost_bearer": "협의필요"}, headers=_hdr)
    chk(r.status_code == 200, "★★★ status 없이 cost_bearer 만 보내도 정상 처리된다(200)",
        f"status={r.status_code} body={r.get_json()}")

    c = DB.get_db()
    row = c.execute("SELECT * FROM defects WHERE id=?", (did,)).fetchone()
    chk(row["cost_bearer"] == "협의필요",
        "★★★ 귀책이 실제로 '협의필요'로 반영된다(예전엔 화면에 보낼 방법이 없었다)",
        row["cost_bearer"])
    chk(row["status"] == "확인중",
        "★★ status 를 안 보냈으므로 상태는 그대로 '확인중'이다(엉뚱하게 바뀌지 않음)",
        row["status"])
    chk(bool(row["dispute_resolved_at"]),
        "★★★ 귀책을 정한 순간 이의(dispute)가 '검토완료'로 처리된다", row["dispute_resolved_at"])
    c.close()

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드89 서버측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
