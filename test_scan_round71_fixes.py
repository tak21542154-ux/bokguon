# -*- coding: utf-8 -*-
"""스캔 71라운드 회귀 — 사진 업로드 3경로의 사건별 상한 검사 레이스(round70 이월분) +
   AI 자동승인이 사람의 반려를 조용히 덮어쓰는 레이스.

  ① 사건 누적 사진 상한(_case_photo_quota_guard)이 파일 저장 I/O **전** 시점의
     장수만 검사했다 — 검사와 실제 INSERT 사이에 잠금이 없어, 동시 요청 둘 다
     통과한 뒤 둘 다 넣으면 상한을 요청 하나만큼 넘길 수 있었다(디스크가 차면
     SQLite 쓰기 자체가 실패해 서비스 전체가 멈춘다 — 이 상한 자체가 그 방어선).
     세 업로드 경로(협력사 시공사진·피해현장사진·하자사진) 모두 저장 성공 장수
     기준으로 커밋 직전 재검사하도록 고쳤다. BEGIN IMMEDIATE 는 반드시 _warn_exif
     호출 **앞**에 온다(그 안의 notify/DB.log 가 conn 에 직접 쓰므로, 뒤에 걸면
     "이미 트랜잭션이 열려 있다"로 죽는다) — 이 순서 자체를 실측으로 확인한다.
  ② _apply_ai_routing 이 review_status='대기' 조건을 SELECT 시점에 파이썬에서만
     봤다 — 그 사이 관리자가 반려를 끝냈어도 AI 루프가 뒤늦게 '승인'으로 덮어썼다.
     같은 함수 바로 위 형제 UPDATE(kind 분류)와 api_photo_reject 는 이미 WHERE
     절 자체에 조건을 넣고 rowcount 로 확인한다 — 같은 방식으로 맞췄다.

      python test_scan_round71_fixes.py
"""
import contextlib
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


APP_SRC = read("app.py")

print("═" * 72)
print("  스캔 71라운드 회귀 — 사진업로드 3경로 사건상한 레이스 + AI자동승인 덮어쓰기 레이스")
print("═" * 72)


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
site1 = _body(APP_SRC, "api_partner_upload_photos")
_pos_begin1 = site1.find('conn.execute("BEGIN IMMEDIATE")')
_pos_warn1 = site1.find("_warn_exif(conn, cid, staged)")
chk(_pos_begin1 >= 0 and _pos_warn1 >= 0 and _pos_begin1 < _pos_warn1,
    "★★★ ① api_partner_upload_photos — BEGIN IMMEDIATE 가 _warn_exif 보다 앞에 있다")
chk(site1.count("_case_photo_quota_guard(conn, cid,") >= 2,
    "★★ ① api_partner_upload_photos 가 사건상한을 두 번(사전·재확인) 검사한다")

site2 = _body(APP_SRC, "_upload_damage_photos")
_pos_begin2 = site2.find('conn.execute("BEGIN IMMEDIATE")')
_pos_warn2 = site2.find("_warn_exif(conn, cid, staged)")
chk(_pos_begin2 >= 0 and _pos_warn2 >= 0 and _pos_begin2 < _pos_warn2,
    "★★★ ① _upload_damage_photos — BEGIN IMMEDIATE 가 _warn_exif 보다 앞에 있다")
chk(site2.count("_case_photo_quota_guard(conn, cid,") >= 2,
    "★★ ① _upload_damage_photos 가 사건상한을 두 번 검사한다")

site3 = _body(APP_SRC, "api_defect_photos_upload")
_pos_begin3 = site3.find('conn.execute("BEGIN IMMEDIATE")')
_pos_warn3 = site3.find('_warn_exif(conn, df["case_id"]')
chk(_pos_begin3 >= 0 and _pos_warn3 >= 0 and _pos_begin3 < _pos_warn3,
    "★★★ ① api_defect_photos_upload — BEGIN IMMEDIATE 가 _warn_exif 보다 앞에 있다")
chk(site3.count("_case_photo_quota_guard(conn, _cid_for_limit,") >= 2,
    "★★ ① api_defect_photos_upload 가 사건상한을 두 번 검사한다")

routing_body = _body(APP_SRC, "_apply_ai_routing")
chk("WHERE id=? AND review_status='대기'" in routing_body,
    "★★★ ② _apply_ai_routing 의 UPDATE 가 WHERE 절 자체에서 review_status 를 확인한다")
chk("cur.rowcount" in routing_body,
    "★★ ② rowcount 로 '누가 먼저 손댔는지' 를 확인한다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 서버 호출로 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round71_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
#  ⚠ 레이스 재현을 값싸게 하려고 사건당 상한을 낮게 잡는다 — photo_ai.py 는
#    모듈 임포트 시점에 이 값을 한 번 읽으므로 import 보다 먼저 설정해야 한다.
os.environ["BOKGUON_MAX_PHOTOS_PER_CASE"] = "3"
sys.path.insert(0, HERE)

try:
    import sqlite3 as _sqlite3
    import db as DB
    DB.init_db()
    import app as A
    import photo_ai as PH

    chk(PH.MAX_FILES_PER_CASE == 3,
        "STEP 테스트용 사건당 상한(3)이 실제로 반영됐다", PH.MAX_FILES_PER_CASE)

    def _jpeg_bytes():
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (4, 4), (200, 30, 30)).save(buf, format="JPEG")
        return buf.getvalue()

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','최고관리자')")
    conn.execute("INSERT INTO partners(name,partner_type,status,login_id,password_hash) "
                 "VALUES('라운드71검증업체','시공사','활성','p71','x')")
    pid = conn.execute("SELECT id FROM partners WHERE login_id='p71'").fetchone()["id"]

    def _new_case(no, status="시공중", ptype_partner=True):
        cid = conn.execute(
            "INSERT INTO cases(case_no,status,partner_id,category,region) VALUES(?,?,?,?,?)",
            (no, status, (pid if ptype_partner else None), "가드레일", "서울")).lastrowid
        conn.commit()
        return cid

    conn.commit()

    client = A.app.test_client()
    _tok = "regress-round71-csrf"
    with client.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    client_p = A.app.test_client()
    _tok_p = "regress-round71-p-csrf"
    with client_p.session_transaction() as sess:
        sess["partner_id"] = pid; sess["partner_name"] = "라운드71검증업체"; sess["_csrf"] = _tok_p
    _hdr_p = {"X-CSRF-Token": _tok_p}

    # ── ② _apply_ai_routing — SELECT 와 UPDATE 사이에 실제로 반려가 끼어드는
    #    레이스를 재현한다. '반려 상태를 미리 깔아 놓고 부른다'로는 옛 코드도
    #    통과한다(파이썬 조건이 그 SELECT 시점 값은 정확히 보므로) — 진짜 결함은
    #    "그 사이"에 있으므로 SELECT 이후·UPDATE 이전 그 순간에 주입해야 한다.
    _cid_ai = _new_case("R71-AI-01")
    _prow = conn.execute(
        """INSERT INTO photos(case_id,rel_path,mime,ext,size,sha256,ai_kind,ai_confidence,
                              review_status,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (_cid_ai, "dummy.jpg", "image/jpeg", "jpg", 100, "deadbeef", "착공전", 99,
         "대기", DB.now())).lastrowid
    conn.commit()

    class _InjectRejectProxy:
        def __init__(self, real, trigger, fx):
            self._real, self._trig, self._fx, self._fired = real, trigger, fx, False

        def execute(self, sql, *a, **kw):
            if not self._fired and sql.strip().startswith(self._trig):
                self._fired = True
                self._fx()
            return self._real.execute(sql, *a, **kw)

        def __getattr__(self, name):
            return getattr(self._real, name)

    def _inject_reject():
        c2 = DB.get_db()
        c2.execute("UPDATE photos SET review_status='반려', reject_reason=? WHERE id=?",
                   ("사진이 흐림(레이스 주입)", _prow))
        c2.commit(); c2.close()

    _real_get_db2 = A.DB.get_db

    def _patched_get_db2():
        #  트리거는 '승인' UPDATE 문 자체 — SELECT 는 그대로 통과시키고, 그
        #  UPDATE 가 나가려는 바로 그 순간에 다른 연결이 먼저 반려로 바꾼다.
        return _InjectRejectProxy(
            _real_get_db2(),
            "UPDATE photos SET review_status='승인', reviewed_by=?, reviewed_at=?",
            _inject_reject)
    A.DB.get_db = _patched_get_db2
    try:
        _outcome = A._apply_ai_routing(_prow)
    finally:
        A.DB.get_db = _real_get_db2

    chk(_outcome == "human",
        "★★★ ② 이미 반려된 사진에는 AI 자동승인이 관여하지 않는다"
        "(고치기 전엔 review_status 확인이 SELECT 시점 파이썬 조건이라, 그 사이 끼어든"
        " 반려를 못 보고 무조건 덮어써 'auto' 가 됐다)", _outcome)
    _status_after = conn.execute(
        "SELECT review_status, reject_reason FROM photos WHERE id=?", (_prow,)).fetchone()
    chk(_status_after["review_status"] == "반려"
        and _status_after["reject_reason"] == "사진이 흐림(레이스 주입)",
        "★★★ ② 동시에 끼어든 반려 상태·사유가 승인으로 덮어써지지 않고 그대로 보존된다",
        dict(_status_after))

    # ── ① 강제 _warn_exif — BEGIN IMMEDIATE 가 뒤에 있었다면 여기서 크래시났을 것 ──
    def _force_warn_exif(conn2, case_id, staged):
        A.notify(conn2, "위치정보", "웹", "운영팀", "강제 EXIF 경고(라운드71 회귀테스트)",
                 audience_type="admin", case_id=(case_id or None), url="/admin#cases")
        A.DB.log(conn2, A.actor(), "EXIF 제거 실패", f"사건 #{case_id} · 테스트")

    _real_warn_exif = A._warn_exif

    def _with_forced_exif(fn):
        A._warn_exif = _force_warn_exif
        try:
            return fn()
        finally:
            A._warn_exif = _real_warn_exif

    # 협력사 시공사진
    _cid_w1 = _new_case("R71-WARN-01")
    r_w1 = _with_forced_exif(lambda: client_p.post(
        f"/api/partner/cases/{_cid_w1}/photos",
        data={"photos": (io.BytesIO(_jpeg_bytes()), "a.jpg")},
        headers=_hdr_p, content_type="multipart/form-data"))
    chk(r_w1.status_code == 200 and (r_w1.get_json() or {}).get("ok"),
        "★★★ ① 협력사 업로드 — _warn_exif 가 실제로 쓰기를 해도 트랜잭션 중첩 없이 성공한다",
        f"status={r_w1.status_code} body={r_w1.get_json()}")

    # 운영자 — 피해현장사진(_upload_damage_photos 공용 경로)
    _cid_w2 = _new_case("R71-WARN-02", status="접수", ptype_partner=False)
    r_w2 = _with_forced_exif(lambda: client.post(
        f"/api/cases/{_cid_w2}/photos/damage",
        data={"photos": (io.BytesIO(_jpeg_bytes()), "b.jpg")},
        headers=_hdr, content_type="multipart/form-data"))
    chk(r_w2.status_code == 200 and (r_w2.get_json() or {}).get("ok"),
        "★★★ ① 피해현장사진 업로드 — _warn_exif 가 써도 트랜잭션 중첩 없이 성공한다",
        f"status={r_w2.status_code} body={r_w2.get_json()}")

    # 하자 사진
    _cid_w3 = _new_case("R71-WARN-03", status="완료", ptype_partner=False)
    _did_w3 = conn.execute(
        "INSERT INTO defects(case_id,title,status,created_at) VALUES(?,?,?,?)",
        (_cid_w3, "지주 유격", "접수", DB.now())).lastrowid
    conn.commit()
    r_w3 = _with_forced_exif(lambda: client.post(
        f"/api/defects/{_did_w3}/photos",
        data={"photos": (io.BytesIO(_jpeg_bytes()), "c.jpg")},
        headers=_hdr, content_type="multipart/form-data"))
    chk(r_w3.status_code == 200 and (r_w3.get_json() or {}).get("ok"),
        "★★★ ① 하자사진 업로드 — _warn_exif 가 써도 트랜잭션 중첩 없이 성공한다",
        f"status={r_w3.status_code} body={r_w3.get_json()}")

    # ── ① 실제 레이스 재현(협력사 시공사진 경로) — round59/68 식 _RaceProxy ──
    class _RaceProxy:
        def __init__(self, real, trigger, fx):
            self._real, self._trig, self._fx, self._fired = real, trigger, fx, False

        def execute(self, sql, *a, **kw):
            if not self._fired and sql.strip() == self._trig:
                self._fired = True
                self._fx()
            return self._real.execute(sql, *a, **kw)

        def __getattr__(self, name):
            return getattr(self._real, name)

    _cid_race = _new_case("R71-RACE-01")

    def _inject_over_cap():
        c2 = _sqlite3.connect(os.environ["BOKGUON_DB_PATH"], timeout=5)
        for i in range(3):  # 상한(3)까지 다른 연결이 먼저 채운다
            c2.execute(
                "INSERT INTO photos(case_id,rel_path,mime,ext,size,sha256,review_status,created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (_cid_race, f"race-{i}.jpg", "image/jpeg", "jpg", 10, f"sha-race-{i}", "대기", DB.now()))
        c2.commit(); c2.close()

    _real_get_db = A.DB.get_db

    def _patched_get_db():
        return _RaceProxy(_real_get_db(), "BEGIN IMMEDIATE", _inject_over_cap)
    A.DB.get_db = _patched_get_db
    try:
        r_race = client_p.post(
            f"/api/partner/cases/{_cid_race}/photos",
            data={"photos": (io.BytesIO(_jpeg_bytes()), "race.jpg")},
            headers=_hdr_p, content_type="multipart/form-data")
    finally:
        A.DB.get_db = _real_get_db

    body_race = r_race.get_json() or {}
    chk(r_race.status_code == 409 and body_race.get("code") == "CASE_FILE_LIMIT",
        "★★★ ① 동시 업로드(다른 연결이 먼저 상한을 채움)에도 깔끔한 409 를 받는다"
        "(고치기 전엔 검사를 통과한 뒤 그대로 저장돼 상한을 넘겼다)",
        f"status={r_race.status_code} body={body_race}")

    _c = DB.get_db()
    _n_photos = _c.execute("SELECT COUNT(*) n FROM photos WHERE case_id=?",
                            (_cid_race,)).fetchone()["n"]
    _c.close()
    chk(_n_photos == 3,
        "★★★ ① 레이스 뒤에도 사건 사진 수가 정확히 상한(3)이다(초과분 없음)", _n_photos)

    _uploads_root = os.environ["BOKGUON_UPLOAD_DIR"]
    _orphans = []
    _case_dir = os.path.join(_uploads_root, str(_cid_race))
    if os.path.isdir(_case_dir):
        _orphans = [f for f in os.listdir(_case_dir) if f not in
                    {f"race-{i}.jpg" for i in range(3)}]
    chk(not _orphans,
        "★★ ① 거부된 업로드의 저장 파일이 디스크에 고아로 남지 않았다(정리됨)", _orphans)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드71 실측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    os.environ.pop("BOKGUON_MAX_PHOTOS_PER_CASE", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
