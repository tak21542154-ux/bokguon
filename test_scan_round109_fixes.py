# -*- coding: utf-8 -*-
"""스캔 109라운드 회귀 — 하자 심각도 검증누락, 개인정보파기 증적축소, 보증만료 알림 영구유실.

  [1] 하자 심각도(severity)가 103라운드의 형제 검증(cost_bearer·due_date)에서만
      빠져 있었다 — 정확일치로 소비하는 자리가 4곳(요약카드·정렬 2곳·평점차감)이라
      오타값은 조용히 놓쳐진다.
  [2] manage.py cmd_prune_personal 의 total 이 n3b(알림본문 파기)·n3c(조회링크
      무효화)·n3d(휴지통 실삭제)를 빠뜨려, 이 셋만 지워진 회차는 실제로 파괴적인
      동작(파일 os.remove 포함)을 했는데도 감사로그가 아예 안 남았다. 로그
      문자열도 n4(종료 사건 피해자정보)를 안 실어, n4 만 지워진 회차는 로그는
      남아도 본문이 "전부 0건"이라 실제와 반대로 읽혔다.
  [3] 하자보증 만료 알림이 문턱일(30/7/0) 정확일치였다 — 데스크톱 PC가 그날 하루
      꺼져 있거나 아무도 화면을 안 열면(인라인 스윕도 못 탐) 그 사건의 경보는
      영구 유실됐다(다음 스윕엔 이미 날짜가 지나 다시는 안 걸림).

      python test_scan_round109_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")
MANAGE_SRC = read("manage.py")

print("═" * 72)
print("  스캔 109라운드 회귀 — 하자 심각도 검증누락·개인정보파기 증적축소·보증만료 알림유실")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 다섯 지점 모두 확인")
# ──────────────────────────────────────────────────────────────
dc_body = _py_fn_body(APP_SRC, "api_defect_create")
chk('d["severity"] not in SEVERITY_VALUES' in dc_body,
    "★★★ 하자 접수가 severity 를 검증한다")
du_body = _py_fn_body(APP_SRC, "api_defect_update")
chk('d["severity"] not in SEVERITY_VALUES' in du_body,
    "★★★ 하자 수정도 severity 를 검증한다")

pp_body = _py_fn_body(MANAGE_SRC, "cmd_prune_personal")
chk("total = n1 + n2 + n3 + n3b + n3c + n3d + n4" in pp_body,
    "★★★ total 이 알림본문·조회링크·휴지통실삭제·종료사건 피해자정보를 전부 센다")
chk("종료사건 피해자정보 {n4}" in pp_body,
    "★★ 로그 문자열도 n4 를 싣는다(예전엔 total 에는 있는데 로그엔 없었다)")

sw_body = _py_fn_body(APP_SRC, "sweep_warranty_expiry")
chk("> date(?, ?) AND" in sw_body and "<= date(?, ?)" in sw_body,
    "★★★ 보증만료 조회가 정확일치 대신 최대 7일 되짚는 창을 쓴다(인접 문턱과 안 겹치게 왼쪽 배타)")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[4] 실행 — 실제 시나리오를 돌린다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round109_")
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
    iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R109보험','활성')").lastrowid
    cid1 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,insurer,is_demo) "
        "VALUES('R109-C1','완료','가드레일','서울',?,'R109보험',0)", (iid,)).lastrowid
    conn.commit()

    admin = A.app.test_client()
    _tok = "r109-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    # ── [2] 하자 접수/수정 — severity 검증 ────────────────────────────
    r1 = admin.post("/api/defects", headers=_hdr,
                     json={"case_id": cid1, "title": "누수", "severity": "심각"})
    chk(r1.status_code == 400,
        "★★★ 정의되지 않은 severity('심각')는 접수 자체가 거부된다"
        "(예전엔 그대로 저장돼 요약카드·정렬·평점차감에서 조용히 빠졌다)",
        (r1.status_code, r1.get_json()))
    r1b = admin.post("/api/defects", headers=_hdr,
                      json={"case_id": cid1, "title": "누수", "severity": "중대"})
    chk(r1b.status_code == 200, "STEP 정의된 severity는 정상 접수된다(과잉차단 아님)",
        (r1b.status_code, r1b.get_data(as_text=True)[:200]))
    did = r1b.get_json().get("id") or conn.execute(
        "SELECT id FROM defects WHERE case_id=? ORDER BY id DESC LIMIT 1", (cid1,)).fetchone()["id"]
    r2 = admin.patch(f"/api/defects/{did}", headers=_hdr, json={"severity": "중대 "})
    chk(r2.status_code == 400,
        "★★ 뒤에 공백이 붙은 값처럼 목록에 없는 severity 는 수정에서도 거부된다",
        (r2.status_code, r2.get_json()))

    # ── [3] 개인정보 파기 — 휴지통만 지워져도 증적이 남는다 ────────────────
    _updir = os.environ["BOKGUON_UPLOAD_DIR"]
    _trash = os.path.join(_updir, "_trash", "999")
    os.makedirs(_trash, exist_ok=True)
    _f = os.path.join(_trash, "old.jpg")
    with open(_f, "wb") as fh:
        fh.write(b"x")
    _old_time = (A.datetime.now(A.DB.KST) - timedelta(days=40)).timestamp()
    os.utime(_f, (_old_time, _old_time))
    conn.commit()

    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("manage_r109", os.path.join(HERE, "manage.py"))
    M = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(M)
    rc = M.cmd_prune_personal([])
    chk(rc == 0, "STEP cmd_prune_personal 자체는 정상 종료한다", rc)
    chk(not os.path.exists(_f),
        "STEP 30일 지난 휴지통 파일은 실제로 삭제됐다", os.path.exists(_f))
    conn2 = DB.get_db()
    log_row = conn2.execute(
        "SELECT detail FROM activity_log WHERE action='개인정보 파기' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    conn2.close()
    chk(bool(log_row),
        "★★★ 휴지통 파일만 지워져도 감사로그에 증적이 남는다"
        "(예전엔 total 계산에서 빠져 이 경우 로그가 아예 안 돌았다)",
        log_row)
    if log_row:
        chk("휴지통사진" in log_row["detail"],
            "★★ 로그 본문에 휴지통사진 항목이 실제로 표시된다", dict(log_row))

    # ── [4] 보증만료 알림 — 문턱일을 놓쳐도 다음 스윕에서 뒤늦게라도 나간다 ──
    _missed_wend = (A.datetime.now(A.DB.KST) - timedelta(days=3)).strftime("%Y-%m-%d")
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,completed_at,warranty_months,is_demo) "
        "VALUES('R109-C2','완료','가드레일','서울',?,0,0)", (_missed_wend,)).lastrowid
    conn.commit()
    n_sent = A.sweep_warranty_expiry(conn)
    chk(n_sent >= 1, "STEP 스윕 자체가 최소 1건은 보냈다고 집계한다", n_sent)
    noti = conn.execute(
        "SELECT message FROM notifications WHERE case_id=? AND ntype='보증만료당일'",
        (cid2,)).fetchone()
    chk(bool(noti) and "지연" in (noti["message"] or ""),
        "★★★ 문턱일을 3일 놓친 사건도 뒤늦게 안내 알림을 받는다"
        "(예전엔 정확일치라 그 사건은 영구히 경보를 못 받았다)",
        dict(noti) if noti else None)
    n_sent2 = A.sweep_warranty_expiry(conn)
    noti_count = conn.execute(
        "SELECT COUNT(*) n FROM notifications WHERE case_id=? AND ntype='보증만료당일'",
        (cid2,)).fetchone()["n"]
    chk(noti_count == 1,
        "★★ 같은 사건에 두 번째 스윕이 돌아도 중복 발송되지 않는다(dedup 유지)",
        noti_count)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드109 서버측 준비/실행", f"{type(e).__name__} {e}")
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
