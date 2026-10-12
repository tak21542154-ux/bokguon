# -*- coding: utf-8 -*-
"""스캔 103라운드 회귀 — 재개상한 오염·발송대기 되돌리기 미완성·하자 PATCH 검증누락.

  [1] 원경매 재개 상한(MAX_REOPEN=3)이 extend_count 를 읽었는데, 이 컬럼은
      낙찰취소 재공고(api_case_cancel_award) 등 이 라우트 밖의 사건도 함께
      올린다. 운영자가 재개 버튼을 두 번밖에 안 눌렀어도 그 전에 낙찰취소가
      한 번 있었으면 세 번째 클릭에서 조기에 상한에 걸려, 되돌릴 수 없는
      오프라인 종결로 내몰렸다. api_case_reopen 전용 reopen_count 로 분리한다.
  [2] '수동처리'로 닫힌 발송건을 되돌리는 api_outbox_reopen 이 status 만
      되돌리고 send_attempts 는 그대로 둬, 원래 '실패'(3회 실패)였던 건은
      되돌려도 자동 스윕·[지금 보내기] 둘 다 다시 걸러내 영영 안 나갔다 —
      이 라우트 자신의 docstring 이 막으려던 바로 그 증상이 재현됐다.
  [3] 하자 PATCH 가 cost_bearer(정확일치로 평점차감에 쓰임)·due_date(date()
      비교로 기한초과 집계에 쓰임)를 검증 없이 저장해, 오타 하나가 평점차감을
      조용히 무효화하거나 그 하자를 기한초과 경보에서 통째로 사라지게 했다.

      python test_scan_round103_fixes.py
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
DB_SRC = read("db.py")
ADMINJS_SRC = read("static/admin.js")

print("═" * 72)
print("  스캔 103라운드 회귀 — 재개상한 오염·발송대기 되돌리기 미완성·하자PATCH 검증누락")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 세 지점 모두 확인")
# ──────────────────────────────────────────────────────────────
chk('("auctions", "reopen_count", "INTEGER DEFAULT 0")' in DB_SRC,
    "★★★ auctions 에 재개 전용 reopen_count 컬럼이 추가됐다")
reopen_body = _py_fn_body(APP_SRC, "api_case_reopen")
chk('au["reopen_count"]' in reopen_body,
    "★★★ api_case_reopen 의 상한판정이 extend_count 대신 reopen_count 를 읽는다")
chk("reopen_count=reopen_count+1" in reopen_body and "WHERE id=? AND reopen_count=?" in reopen_body,
    "★★ CAS 잠금도 reopen_count 로 건다")
chk("r.reopen_count" in ADMINJS_SRC,
    "★ admin.js 토스트도 새 필드명을 읽는다")

outbox_body = _py_fn_body(APP_SRC, "api_outbox_reopen")
chk("send_attempts=0" in outbox_body,
    "★★★ api_outbox_reopen 이 send_attempts 도 함께 지운다")

defect_body = _py_fn_body(APP_SRC, "api_defect_update")
chk('d["cost_bearer"] not in ("시행사", "보험사", "협의필요")' in defect_body,
    "★★★ api_defect_update 가 cost_bearer 를 검증한다(시행사/보험사/협의필요 3값)")
chk('re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}", d["due_date"])' in defect_body,
    "★★★ api_defect_update 가 due_date 형식을 검증한다")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[4] 실행 — 세 시나리오를 실제로 돌린다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round103_")
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
    admin = A.app.test_client()
    _tok = "r103-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    # ── [2] 재개 상한 — 낙찰취소가 소진한 extend_count 와 무관하게 3번 통과한다 ──
    cid1 = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R103-C1','유찰','가드레일','서울',0)").lastrowid
    conn.execute(
        "INSERT INTO auctions(case_id,change_order_id,kind,round,status,low_price,"
        "                     bid_count,extend_count,reopen_count,deadline,created_at) "
        # extend_count=1 은 "낙찰취소 재공고가 이미 한 번 올려놓은" 상태를 흉내낸다.
        "VALUES(?,NULL,'원경매',0,'마감',0,0,1,0,?,?)", (cid1, DB.now(), DB.now())).lastrowid
    conn.commit()

    ok_count = 0
    for i in range(3):
        r = admin.post(f"/api/cases/{cid1}/reopen", headers=_hdr, json={})
        if r.status_code == 200:
            ok_count += 1
            conn.execute("UPDATE cases SET status='유찰', partner_id=NULL WHERE id=?", (cid1,))
            conn.commit()
    chk(ok_count == 3,
        "★★★ 낙찰취소로 extend_count 가 이미 1이었어도 재개 버튼은 정확히 3번 통과한다"
        "(예전엔 extend_count 기준이라 2번째에서 상한(3)에 조기 도달했다)",
        ok_count)
    r_over = admin.post(f"/api/cases/{cid1}/reopen", headers=_hdr, json={})
    chk(r_over.status_code == 409 and r_over.get_json().get("code") == "MAX_EXTEND",
        "STEP 진짜 4번째는 정상적으로 상한에 걸린다(상한 자체가 없어진 게 아니다)",
        (r_over.status_code, r_over.get_json()))

    # ── [3] 발송대기 되돌리기 — send_attempts 까지 풀려 다시 스윕에 잡힌다 ──────
    nid = conn.execute(
        "INSERT INTO notifications(ntype,channel,target,message,status,send_attempts,"
        "                          send_detail,created_at) "
        "VALUES('낙찰','알림톡','R103업체','메시지','실패',3,'3회 실패',?)", (DB.now(),)).lastrowid
    conn.commit()
    r1 = admin.post(f"/api/outbox/{nid}/handled", headers=_hdr, json={"note": "전화로 대신 안내"})
    chk(r1.status_code == 200, "STEP 수동처리 자체는 성공한다", (r1.status_code, r1.get_data(as_text=True)[:200]))
    r2 = admin.post(f"/api/outbox/{nid}/reopen", headers=_hdr, json={})
    chk(r2.status_code == 200, "STEP 되돌리기 자체는 성공한다", (r2.status_code, r2.get_data(as_text=True)[:200]))
    row = conn.execute(
        "SELECT status, send_attempts FROM notifications WHERE id=?", (nid,)).fetchone()
    chk(row["status"] == "발송대기" and (row["send_attempts"] or 0) == 0,
        "★★★ 되돌린 뒤 send_attempts 도 0으로 풀려 자동 스윕이 다시 이 건을 집을 수 있다"
        "(예전엔 3에 그대로 묶여 status만 바뀌어도 영영 안 나갔다)",
        dict(row))

    # ── [4] 하자 PATCH — cost_bearer·due_date 형식오류를 막는다 ────────────
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('R103업체','시행사','활성')").lastrowid
    did = conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,title,status,cost_bearer,"
        "                    partner_id,created_at) "
        "VALUES('R103-DF1',0,'R103-C1','문틀 하자','접수중','시행사',?,?)",
        (pid, DB.now())).lastrowid
    conn.commit()

    r3 = admin.patch(f"/api/defects/{did}", headers=_hdr, json={"cost_bearer": "제3의값"})
    chk(r3.status_code == 400,
        "★★★ 정의되지 않은 cost_bearer 는 저장이 거부된다(예전엔 그대로 기록돼 평점차감이 무효화됐다)",
        (r3.status_code, r3.get_json()))
    r4 = admin.patch(f"/api/defects/{did}", headers=_hdr, json={"due_date": "2026/09/15"})
    chk(r4.status_code == 400,
        "★★★ 형식이 다른 due_date 는 저장이 거부된다(예전엔 그대로 기록돼 기한초과 집계에서 사라졌다)",
        (r4.status_code, r4.get_json()))
    r5 = admin.patch(f"/api/defects/{did}", headers=_hdr, json={"due_date": "2026-13-45"})
    chk(r5.status_code == 400,
        "★★ 구조는 맞지만 존재하지 않는 날짜도 거부된다",
        (r5.status_code, r5.get_json()))
    r6 = admin.patch(f"/api/defects/{did}", headers=_hdr,
                      json={"cost_bearer": "협의필요", "due_date": "2026-09-15"})
    chk(r6.status_code == 200,
        "STEP 정상 값이면 그대로 통과한다(과잉차단 아님)",
        (r6.status_code, r6.get_data(as_text=True)[:200]))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드103 서버측 준비/실행", f"{type(e).__name__} {e}")
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
