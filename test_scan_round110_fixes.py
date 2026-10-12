# -*- coding: utf-8 -*-
"""스캔 110라운드 회귀 — 휴지통 mtime 유예기간 무력화, 2차경매 배치분류 재도달 뒷문.

  [1] 사진을 지우면 파일은 uploads/_trash 로 옮겨질 뿐 지우지 않는다(30일 유예).
      그런데 os.replace/shutil.move 는 원본 파일의 mtime 을 그대로 보존한다 —
      prune-personal 의 파기 판정이 mtime 기준이라, 업로드 후 30일이 지난
      사진은 지운 순간 바로 다음 파기에 걸린다(유예기간 사실상 0일). 세
      생산자(app.py _photo_to_trash, manage.py cmd_prune_orphans/cmd_go_live)
      모두 같은 결함이었다.
  [2] 107라운드는 "2차 경매 배치 자동분류는 낙찰 전에만 오므로 안전하다"고
      전제하고 수동분류 라우트만 고쳤다. 그런데 낙찰취소(partner_id·awarded_at
      을 NULL 로 되돌림) 뒤 to-dispatch(같은 NULL 조건만 봄)를 타면 '접수'로
      되돌아와 이 배치 경로에 재도달한다 — 그 전제가 틀렸다. award_canceled_at
      (낙찰취소가 세팅하고 아무도 지우지 않는 영구 표식)을 가드에 추가한다.

      python test_scan_round110_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")
MNG_SRC = read("manage.py")

print("═" * 72)
print("  스캔 110라운드 회귀 — 휴지통 mtime 유예무력화·2차경매 배치분류 재도달")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 네 지점 모두 확인")
# ──────────────────────────────────────────────────────────────
trash_body = _py_fn_body(APP_SRC, "_photo_to_trash")
chk("os.replace(src, dst)" in trash_body and "os.utime(dst, None)" in trash_body,
    "★★★ app.py _photo_to_trash 가 이동 뒤 mtime 을 지금 시각으로 찍는다")

orphan_body = _py_fn_body(MNG_SRC, "cmd_prune_orphans")
chk("shutil.move(_src, _dst)" in orphan_body and "os.utime(_dst, None)" in orphan_body,
    "★★★ manage.py cmd_prune_orphans 도 이동 뒤 mtime 을 찍는다")

golive_body = _py_fn_body(MNG_SRC, "cmd_go_live")
chk("shutil.move(_src, _dst)" in golive_body and "os.utime(_dst, None)" in golive_body,
    "★★★ manage.py cmd_go_live 도 이동 뒤 mtime 을 찍는다")

oa_body = _py_fn_body(APP_SRC, "api_case_open_auction")
chk('c.get("awarded_at") or c.get("partner_id") or c.get("award_canceled_at")' in oa_body,
    "★★★ 2차 경매 배치분류 가드가 award_canceled_at 도 함께 본다")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[4] 실행 — 실제 시나리오를 돌린다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round110_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
os.environ.setdefault("BOKGUON_BACKUP_DIR", os.path.join(_tmpdir, "backups"))
sys.path.insert(0, HERE)

OLD_TS = time.time() - 200 * 86400  # 200일 전 — 30일 파기 문턱을 한참 넘는다


def _mkfile(rel):
    _abs = os.path.join(os.environ["BOKGUON_UPLOAD_DIR"], *rel.split("/"))
    os.makedirs(os.path.dirname(_abs), exist_ok=True)
    with open(_abs, "wb") as f:
        f.write(b"fake-jpeg-bytes-round110")
    os.utime(_abs, (OLD_TS, OLD_TS))
    return _abs


def _fresh(path, slack=120):
    return os.path.isfile(path) and (time.time() - os.path.getmtime(path)) < slack


try:
    import db as DB
    DB.init_db()
    import app as A
    import manage as M

    # ── [2] _photo_to_trash(app.py) — 이동 즉시 mtime 이 지금 시각이다 ──
    _rel_a = "2026/01/round110-a.jpg"
    _abs_a = _mkfile(_rel_a)
    chk(abs(os.path.getmtime(_abs_a) - OLD_TS) < 2, "STEP 원본 파일이 실제로 200일 전으로 백데이트됐다")
    A._photo_to_trash(_rel_a)
    _trash_dir = os.path.join(os.environ["BOKGUON_UPLOAD_DIR"], "_trash")
    _found_a = [f for f in os.listdir(_trash_dir)] if os.path.isdir(_trash_dir) else []
    _match_a = [f for f in _found_a if f.endswith("_round110-a.jpg")]
    chk(len(_match_a) == 1, "STEP _photo_to_trash 가 파일을 휴지통으로 옮겼다", _found_a)
    if _match_a:
        _dst_a = os.path.join(_trash_dir, _match_a[0])
        chk(_fresh(_dst_a),
            "★★★ 휴지통으로 옮긴 직후 mtime 이 '지금'이다(예전엔 200일 전 그대로라 "
            "다음 파기 스윕에 바로 걸렸다)",
            f"age_sec={time.time() - os.path.getmtime(_dst_a):.0f}")

    # ── [3] cmd_prune_orphans(manage.py) — 고아 사진도 이동 즉시 mtime 이 지금이다 ──
    _rel_b = "2026/01/round110-b.jpg"
    _abs_b = _mkfile(_rel_b)
    conn = DB.get_db()
    conn.execute(
        "INSERT INTO photos(case_id,rel_path,orig_name,mime,ext,size,sha256,kind,created_at) "
        "VALUES(888801, ?, 'b.jpg','image/jpeg','jpg',1,'r110sha_b',NULL, ?)",
        (_rel_b, DB.now()))
    conn.commit(); conn.close()

    buf = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(buf):
        M.cmd_prune_orphans(["--yes"])
    _dst_b = os.path.join(os.environ["BOKGUON_UPLOAD_DIR"], "_trash",
                           *_rel_b.split("/"))
    chk(os.path.isfile(_dst_b), "STEP cmd_prune_orphans 가 고아 사진 파일을 휴지통으로 옮겼다",
        buf.getvalue()[-300:])
    if os.path.isfile(_dst_b):
        chk(_fresh(_dst_b),
            "★★★ cmd_prune_orphans 로 옮긴 파일도 mtime 이 '지금'이다",
            f"age_sec={time.time() - os.path.getmtime(_dst_b):.0f}")

    # ── [4] cmd_go_live(manage.py) — 데모 사진 정리도 이동 즉시 mtime 이 지금이다 ──
    _rel_c = "2026/01/round110-c.jpg"
    _abs_c = _mkfile(_rel_c)
    conn = DB.get_db()
    cid_demo = conn.execute(
        "INSERT INTO cases(case_no, is_demo, status) VALUES('R110-DEMO-01', 1, '완료')"
    ).lastrowid
    conn.execute(
        "INSERT INTO photos(case_id, rel_path) VALUES(?, ?)", (cid_demo, _rel_c))
    conn.commit(); conn.close()

    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        M.cmd_go_live(["--yes"])
    _dst_c = os.path.join(os.environ["BOKGUON_UPLOAD_DIR"], "_trash",
                           *_rel_c.split("/"))
    chk(os.path.isfile(_dst_c), "STEP cmd_go_live 가 데모 사진 파일을 휴지통으로 옮겼다",
        buf2.getvalue()[-300:])
    if os.path.isfile(_dst_c):
        chk(_fresh(_dst_c),
            "★★★ cmd_go_live 로 옮긴 파일도 mtime 이 '지금'이다",
            f"age_sec={time.time() - os.path.getmtime(_dst_c):.0f}")

    # ── [5] 2차 경매 배치분류 — 낙찰취소 이력이 있으면 재도달해도 막힌다 ──
    #  ⚠ 위 [4]cmd_go_live 는 DEMO_ACCOUNTS(admins/username='admin')를 지운다 —
    #    여기서 쓸 관리자 계정은 그 목록과 겹치지 않는 이름으로 새로 만든다.
    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r110admin','x','검증','중간관리자')")
    conn.commit()
    admin = A.app.test_client()
    _tok = "r110-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r110admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    # 낙찰취소(→to-dispatch)로 '접수'까지 되돌아왔지만 award_canceled_at 은 남아있는 사건
    cid_v = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,award_canceled_at,is_demo) "
        "VALUES('R110-C1','접수','가드레일','서울',?,0)", (DB.now(),)).lastrowid
    pid_v = conn.execute(
        "INSERT INTO photos(case_id,partner_id,uploader,uploader_role,rel_path,orig_name,"
        "                   mime,ext,size,sha256,kind,review_status,created_at) "
        "VALUES(?,NULL,'출동업체','협력사','v.jpg','v.jpg','image/jpeg','jpg',1,'r110sha_v',"
        "       NULL,'승인',?)", (cid_v, DB.now())).lastrowid
    conn.commit()

    r1 = admin.post(f"/api/cases/{cid_v}/open-auction", headers=_hdr,
                     json={"est_basis": "출동 업체 실측 견적 기준"})
    chk(r1.status_code == 409 and r1.get_json().get("code") == "UNCLASSIFIED",
        "★★★ 낙찰취소 이력이 남은 사건은 재도달해도 미분류 사진을 일괄분류하지 않는다"
        "(예전엔 그대로 통과 — 직전 시공사 영수증이 경쟁사에 열렸다)",
        (r1.status_code, r1.get_json()))
    row_v = conn.execute("SELECT kind FROM photos WHERE id=?", (pid_v,)).fetchone()
    chk(row_v["kind"] is None, "STEP 막힌 요청은 실제로 분류를 안 바꿨다", dict(row_v))

    # 낙찰 이력이 전혀 없는 사건은 여전히 정상적으로 자동분류된다(과잉차단 아님)
    cid_ok = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R110-C2','접수','가드레일','서울',0)").lastrowid
    pid_ok = conn.execute(
        "INSERT INTO photos(case_id,partner_id,uploader,uploader_role,rel_path,orig_name,"
        "                   mime,ext,size,sha256,kind,review_status,created_at) "
        "VALUES(?,NULL,'출동업체','협력사','o.jpg','o.jpg','image/jpeg','jpg',1,'r110sha_o',"
        "       NULL,'승인',?)", (cid_ok, DB.now())).lastrowid
    conn.commit()

    r2 = admin.post(f"/api/cases/{cid_ok}/open-auction", headers=_hdr,
                     json={"est_basis": "출동 업체 실측 견적 기준"})
    chk(r2.status_code == 200,
        "STEP 낙찰 이력이 없는 사건은 여전히 정상적으로 2차 경매가 열린다(과잉차단 아님)",
        (r2.status_code, r2.get_data(as_text=True)[:200]))
    row_ok = conn.execute("SELECT kind FROM photos WHERE id=?", (pid_ok,)).fetchone()
    chk(row_ok["kind"] == "착공전",
        "STEP 그 사진은 실제로 자동 분류됐다(가드가 정당한 경로까지 막지 않는다)",
        dict(row_ok))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드110 서버측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    os.environ.pop("BOKGUON_BACKUP_DIR", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
