# -*- coding: utf-8 -*-
"""스캔 107라운드 회귀 — 낙찰취소 재입찰 사진노출 뒷문, 도급판정 기록실패 침묵.

  [1] (여러 라운드째 미뤄뒀던 결함) 낙찰취소 후 재공고된 사건은 지금 다시
      입찰 중이면 _is_biddable=True 다. 그 상태에서 관리자가 사진 수동분류
      (api_photo_set_kind)로 아무 사진이나 시공사진 종류(착공전 등)로 바꾸면
      _photo_visible_to 가 즉시 현재 입찰자 전원에게 그 사진을 연다 — 직전
      시공사의 영수증이면 상호·낙찰가가 경쟁사에 노출된다(철칙4). 배치 자동
      분류 경로는 이미 이 위험을 막는데 이 수동분류 라우트만 뒷문이었다.
      하드블록이 아니라 확인 플래그로 통과시킨다(정당한 재분류까지 막지 않기 위해).
  [2] record_gate() 가 감사로그 INSERT 실패를 res["_log_failed"] 로 표시하는데
      _gate_alert() 는 ok=True 면 그 표시를 보기도 전에 반환해, "왜 직접
      도급했는지"의 유일한 소명 스냅샷이 안 남은 사실 자체가 조용히 사라졌다.

      python test_scan_round107_fixes.py
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


APP_SRC = read("app.py")
ADMINJS_SRC = read("static/admin.js")

print("═" * 72)
print("  스캔 107라운드 회귀 — 낙찰취소 재입찰 사진노출 뒷문·도급판정 기록실패 침묵")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 세 지점 모두 확인")
# ──────────────────────────────────────────────────────────────
pk_body = _py_fn_body(APP_SRC, "api_photo_set_kind")
chk('SELECT award_canceled_at FROM cases WHERE id=?' in pk_body,
    "★★★ api_photo_set_kind 가 낙찰취소 이력을 본다")
chk('code": "PHOTO_REBID_EXPOSE"' in pk_body and 'not d.get("confirm_expose")' in pk_body,
    "★★★ 확인 플래그 없이는 위험할 때 막는다(하드블록 아님)")

chk("e.code === 'PHOTO_REBID_EXPOSE'" in ADMINJS_SRC and "confirm_expose: true" in ADMINJS_SRC,
    "★★ 화면이 그 코드를 받아 확인 후 재시도한다")

ga_body = _py_fn_body(APP_SRC, "_gate_alert")
chk('if res and res.get("_log_failed"):' in ga_body,
    "★★★ _gate_alert 가 ok 판정과 무관하게 기록실패부터 본다")
_ga_lines = ga_body.splitlines()
_i_logfail = next(i for i, l in enumerate(_ga_lines) if '"_log_failed"' in l)
_i_okret = next(i for i, l in enumerate(_ga_lines) if 'res.get("ok")' in l and "return" in _ga_lines[i + 1])
chk(_i_logfail < _i_okret,
    "★★ 기록실패 확인이 ok 조기반환보다 앞에 있다(순서가 안 바뀌면 무의미)")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[3] 실행 — 실제 시나리오를 돌린다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round107_")
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

    # ── [2] 낙찰취소 후 재입찰 중 사건 — 시공사진 재분류가 확인 없이는 막힌다 ──
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,award_canceled_at,is_demo) "
        "VALUES('R107-C1','입찰중','가드레일','서울',?,0)", (DB.now(),)).lastrowid
    conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,deadline,created_at) "
        "VALUES(?,NULL,'원경매',0,'진행',0,0,0,?,?)",
        (cid, "9999-12-31 23:59:59", DB.now())).lastrowid
    pid_photo = conn.execute(
        "INSERT INTO photos(case_id,partner_id,uploader,uploader_role,rel_path,orig_name,"
        "                   mime,ext,size,sha256,kind,review_status,created_at) "
        "VALUES(?,NULL,'전직시공사','협력사','r.jpg','r.jpg','image/jpeg','jpg',1,'r107sha',"
        "       '영수증','승인',?)", (cid, DB.now())).lastrowid
    conn.commit()

    admin = A.app.test_client()
    _tok = "r107-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    r1 = admin.post(f"/api/photos/{pid_photo}/kind", headers=_hdr, json={"kind": "착공전"})
    chk(r1.status_code == 409 and r1.get_json().get("code") == "PHOTO_REBID_EXPOSE",
        "★★★ 확인 없이는 낙찰취소·재입찰 중 사건의 사진을 시공사진으로 못 바꾼다"
        "(예전엔 그대로 통과 — 직전 시공사 영수증이 경쟁사에 열렸다)",
        (r1.status_code, r1.get_json()))

    row_unchanged = conn.execute("SELECT kind FROM photos WHERE id=?", (pid_photo,)).fetchone()
    chk(row_unchanged["kind"] == "영수증", "STEP 막힌 요청은 실제로 분류를 안 바꿨다", dict(row_unchanged))

    r2 = admin.post(f"/api/photos/{pid_photo}/kind", headers=_hdr,
                     json={"kind": "착공전", "confirm_expose": True})
    chk(r2.status_code == 200, "STEP 확인 플래그를 실으면 정상적으로 통과한다(막다른 길 아님)",
        (r2.status_code, r2.get_data(as_text=True)[:200]))

    # 위험하지 않은 경우(낙찰취소 이력 없음)는 그대로 자유롭게 분류된다 — 과잉차단 아님.
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R107-C2','입찰중','가드레일','서울',0)").lastrowid
    pid_photo2 = conn.execute(
        "INSERT INTO photos(case_id,partner_id,uploader,uploader_role,rel_path,orig_name,"
        "                   mime,ext,size,sha256,kind,review_status,created_at) "
        "VALUES(?,NULL,'보험사','보험사','d.jpg','d.jpg','image/jpeg','jpg',1,'r107sha2',"
        "       '기타','승인',?)", (cid2, DB.now())).lastrowid
    conn.commit()
    r3 = admin.post(f"/api/photos/{pid_photo2}/kind", headers=_hdr, json={"kind": "착공전"})
    chk(r3.status_code == 200,
        "STEP 낙찰취소 이력이 없는 사건은 확인 없이도 정상 분류된다(과잉차단 아님)",
        (r3.status_code, r3.get_data(as_text=True)[:200]))

    # ── [3] 도급판정 기록실패 — ok=True 여도 알림·로그가 남는다 ────────────
    with A.app.test_request_context():
        A._gate_alert(conn, cid, "R107-C1", {"ok": True, "_log_failed": True, "code": "가능"},
                      "낙찰")
        conn.commit()
    log_row = conn.execute(
        "SELECT detail FROM activity_log WHERE action='도급판정 기록 실패' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    chk(bool(log_row) and "R107-C1" in (log_row["detail"] or ""),
        "★★★ ok=True 인 판정도 기록실패면 감사로그에 남는다(예전엔 완전히 조용했다)",
        dict(log_row) if log_row else None)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드107 서버측 준비/실행", f"{type(e).__name__} {e}")
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
