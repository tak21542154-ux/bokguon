# -*- coding: utf-8 -*-
"""스캔 96라운드 회귀 — settlements 데모표식 미상속·go-live 미리보기 과소집계.

  [F1] bids·dispatches·field_agreements·notifications 는 이미 "자식표 데모
    표식은 사건에서 물려받는다"(_backfill_child_is_demo, db.py)로 보호되는데,
    똑같이 case_id 로 묶이고 자기 is_demo 컬럼도 있는 settlements 만 이 목록에
    없었다. 유일한 생성 지점(api_case_approve)이 is_demo 를 안 채우니 전 행이
    0 — 보험사가 직접 내려받는 정산 명세서(_insurer_statement)가 데모 정산을
    실제 매출로 그대로 보여준다.

  [F2] manage.py 의 cmd_check 는 "DEMO_TABLES 목록만 보면 거짓 초록"이라며
    dispatches·field_agreements 를 추가로 세는데, 바로 옆의 go-live 미리보기
    (_demo_counts)는 그 확장을 못 물려받아 두 화면이 같은 상태를 다르게
    보고한다(실제 삭제 자체는 case_id 기준이라 안전하지만, 승인 전 미리보기
    숫자가 실제보다 적게 나온다).

      python test_scan_round96_fixes.py
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


DB_SRC = read("db.py")
MANAGE_SRC = read("manage.py")

print("═" * 72)
print("  스캔 96라운드 회귀 — settlements 데모표식 미상속·go-live 미리보기 과소집계")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] F1 — 소스: _CHILD_DEMO_SQL 에 settlements 가 추가됐다")
# ──────────────────────────────────────────────────────────────
chk('("settlements",' in DB_SRC and "UPDATE settlements SET is_demo=1" in DB_SRC,
    "★★★ settlements 도 bids·dispatches 등과 같은 방식으로 데모 표식을 물려받는다")

# ══════════════════════════════════════════════════════════════
print("\n[2] F2 — 소스: _demo_counts 가 cmd_check 와 같은 확장 목록을 쓴다")
# ──────────────────────────────────────────────────────────────
counts_body = _py_fn_body(MANAGE_SRC, "_demo_counts")
chk('list(DB.DEMO_TABLES) + ["dispatches", "field_agreements"]' in counts_body,
    "★★★ go-live 미리보기가 cmd_check 와 같은 목록(DEMO_TABLES+출동수배+현장합의)을 쓴다")

# ══════════════════════════════════════════════════════════════
print("\n[3] F1 — 실행: 데모 사건의 정산이 데모로 표시되고, 보험사 명세서에서 빠진다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round96_")
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
    iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R96보험','활성')").lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R96업체','시행사','활성')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,insurer_id,insurer,partner_id,"
        "                  partner_name,award_amount,is_demo) "
        "VALUES('R96-DEMO','검수대기','가드레일','서울',?,'R96보험',?,?,3000000,1)",
        (iid, pid, "R96업체")).lastrowid
    #  ⚠ [라운드102] uploader_role 을 '협력사'로 둔다 — 정산 승인 관문(api_case_approve)
    #    이 102라운드부터 협력사가 올린 시공사진만 증거로 센다. 이 테스트의 목적은
    #    settlements 데모표식 상속이지 사진 출처가 아니라, 그 관문을 통과시킬
    #    "진짜 시공 증거"면 충분하다.
    conn.execute(
        """INSERT INTO photos(case_id,partner_id,uploader,uploader_role,rel_path,orig_name,
                              mime,ext,size,sha256,kind,review_status,created_at)
           VALUES(?,?,'검증','협력사','t/a.jpg','a.jpg','image/jpeg','.jpg',100,'r96sha',
                  '완료','승인',?)""", (cid, pid, DB.now()))
    conn.commit()

    admin = A.app.test_client()
    _tok = "r96-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    r = admin.post(f"/api/cases/{cid}/approve", headers=_hdr)
    chk(r.status_code == 200, "STEP 준비: 검수 승인(정산 생성) 자체는 성공한다",
        f"status={r.status_code} body={r.get_json()}")

    row = conn.execute("SELECT id, is_demo FROM settlements WHERE case_id=?", (cid,)).fetchone()
    chk(row is not None, "STEP 준비: 정산 행이 실제로 생성됐다")
    #  ⚠⚠ [라운드526] 이 자리는 예전엔 "생성 지점 자체는 그대로 둔다 — 백필(서버
    #    기동 시 1회)만 채운다"였다. round526 이 api_case_approve() 의 INSERT
    #    문 자체에 is_demo 를 추가했다(가동 중 실시간 생성도 즉시 정확해야
    #    한다 — round525 가 defects·happy_calls 에 쓴 것과 같은 원칙, db.py 의
    #    round96 주석 자신이 "유일한 생성 지점이 이 컬럼을 아예 안 채운다"고
    #    이미 지목해 뒀던 바로 그 자리). 그래서 이제 생성 "직후"(백필 전)에도
    #    이미 1이다 — 옛 기대값(0)을 그대로 두면 이 회귀가 스스로 "고쳐진 게
    #    아니라 원래 이랬다"고 우기는 꼴이 된다.
    chk(row["is_demo"] == 1,
        "★★★ [라운드526] 생성 직후(백필 전)에도 이미 is_demo=1 이다"
        "(api_case_approve() 의 INSERT 자체가 사건에서 물려받는다 — 더는 백필에만 기대지 않는다)",
        row["is_demo"])

    n = DB._backfill_child_is_demo(conn)
    conn.commit()
    row2 = conn.execute("SELECT is_demo FROM settlements WHERE case_id=?", (cid,)).fetchone()
    chk(row2["is_demo"] == 1,
        "★★★ 백필은 이미 1인 행을 건드리지 않고 그대로 둔다(멱등) — 레거시 행을 "
        "위한 방어망(_backfill_child_is_demo)은 여전히 살아 있다",
        f"n={n} is_demo={row2['is_demo']}")

    insurer_c = A.app.test_client()
    with insurer_c.session_transaction() as sess:
        sess["insurer_id"] = iid; sess["insurer_name"] = "R96보험"
    js = insurer_c.get("/api/insurer/statement").get_json()
    lines = js.get("lines") or js.get("items") or []
    case_nos = [x.get("case_no") for x in lines] if isinstance(lines, list) else []
    chk("R96-DEMO" not in case_nos,
        "★★★ 보험사 자신의 정산 명세서에서 데모 정산이 실제로 빠진다"
        "(예전엔 백필해도 안 빠졌다 — settlements 가 대상 목록에 없었으므로)",
        case_nos)

    # ══════════════════════════════════════════════════════════
    print("\n[4] F2 — 실행: _demo_counts() 를 실제로 호출해 확장 목록이 죽지 않고 동작한다")
    # ──────────────────────────────────────────────────────────
    #  ⚠ [자기검증 강화] F2 는 처음엔 소스 문자열 검사만 있었다 — 그래서 정작
    #    수정 과정에서 "out = {}" 초기화 줄을 통째로 날려 먹은 실수(같은 배터리의
    #    69라운드 테스트가 진짜 cmd_go_live() 를 불렀다가 NameError 로 잡아냄)를
    #    이 파일 자신은 못 잡았다 — 소스에 목표 문자열이 있다고 해서 함수가 실제로
    #    도는 건 아니다. 여기서 직접 호출해 같은 사고를 스스로도 잡는다.
    sys.path.insert(0, os.path.dirname(HERE))
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("manage_r96", os.path.join(HERE, "manage.py"))
    M = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(M)

    conn2 = DB.get_db()
    d_demo = conn2.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R96-DISPATCH','접수','가드레일','서울',1)").lastrowid
    conn2.execute(
        "INSERT INTO dispatches(case_id,status,is_demo) VALUES(?,'모집중',1)", (d_demo,))
    conn2.commit()
    counts = M._demo_counts(conn2)
    conn2.close()
    chk(isinstance(counts, dict), "STEP _demo_counts() 호출 자체가 예외 없이 끝난다(NameError 없음)")
    chk(counts.get("dispatches", 0) >= 1,
        "★★★ go-live 미리보기가 출동수배(dispatches)도 실제로 센다", counts)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드96 서버측 준비/실행", f"{type(e).__name__} {e}")
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
