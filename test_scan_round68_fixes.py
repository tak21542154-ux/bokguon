# -*- coding: utf-8 -*-
"""스캔 68라운드 회귀 — 사건/보험사 등록 레이스 2곳 + 데모시드 naive datetime 3곳 +
   일정삭제 권한등급 불일치(HIGH) + 백업 문서 오기(MEDIUM).

  조사 에이전트가 짚고 이번 라운드에서 직접 코드를 읽어 재확인한 결함:

  ① api_case_create(관리자 수동 등록) — 중복 접수번호 검사(SELECT)와 INSERT 사이에
     잠금이 없었다. cases.case_no 는 UNIQUE 제약이라 동시요청 둘 다 검사를 통과하면
     두 번째 INSERT 가 sqlite3.IntegrityError 로 **처리되지 않은 예외(500)** 를 낸다.
     형제 경로(_create_case, 보험사 포털 api_insurer_case_create/API api_v1_case_create)는
     이미 BEGIN IMMEDIATE 로 검사~INSERT 를 한 트랜잭션에 묶어 두 번째 요청이 깔끔한
     400 을 받는다 — 이 경로만 옛 코드였다.
  ② api_insurer_create 도 같은 결함이다. insurers.name 은 **UNIQUE 제약조차 없어서**
     레이스가 나면 크래시도 없이 같은 기관명 행이 조용히 2개 생긴다(더 위험한 실패
     방식 — 아무도 알아채지 못한다).
  ③ db.py seed() 의 naive datetime.now() 3곳(cases.completed_at, defects.created_at,
     defects.due_date) — 67라운드에서 app.py·manage.py 5곳은 전부 KST 로 고쳤는데
     데모 시드 데이터 생성 부분만 남아 있었다(직접 실행에 영향은 없고 화면 표시만
     서버 시간대가 KST 아니면 최대 9시간 밀린다).
  ④ api_schedule_event_del 이 하위관리자였다 — ROLE_RANK 정책 주석(460행)이 명시하는
     "하위관리자 = 조회 + 접수/등록 보조 — **승인·정산·삭제는 제외**" 를 위반한다.
     다른 역할기반 삭제 라우트 8개(메모·공지·사진·업체·보험사API키·표준단가·BOQ·
     관리자계정)는 전부 중간관리자 이상이다.
  ⑤ DEPLOY.md 가 `일일백업.bat` 와 `windows_setup.ps1` 를 "어느 쪽을 쓰든 상관없다"고
     설명했지만 실제로는 시공 사진(uploads/) 백업이 windows_setup.ps1(robocopy 예약
     작업)에만 있고 일일백업.bat(DB백업·개인정보파기·접속기록파기·자가점검 4단계뿐)
     에는 없다 — 이 설명만 믿고 일일백업.bat 를 쓰면 사진(하자·분쟁 증빙)이 조용히
     백업되지 않는다.

      python test_scan_round68_fixes.py
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


APP_SRC = read("app.py")
DB_SRC = read("db.py")
DEPLOY_SRC = read(os.path.join("deploy", "DEPLOY.md"))

print("═" * 72)
print("  스캔 68라운드 회귀 — 사건/보험사 등록 레이스 2곳 + 데모시드 KST 3곳 + 삭제권한 + 백업문서")
print("═" * 72)


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
case_body = _body(APP_SRC, "api_case_create")
chk('conn.execute("BEGIN IMMEDIATE")' in case_body,
    "★★★ ① api_case_create 가 중복검사 전에 BEGIN IMMEDIATE 로 잠근다")
chk(case_body.count("conn.rollback(); conn.close()") >= 3,
    "★★ ① 조기 반환 경로들이 rollback 후 close 한다(최소 3곳)",
    f"실제 {case_body.count('conn.rollback(); conn.close()')}곳")

ins_body = _body(APP_SRC, "api_insurer_create")
chk('conn.execute("BEGIN IMMEDIATE")' in ins_body,
    "★★ ② api_insurer_create 가 중복검사 전에 BEGIN IMMEDIATE 로 잠근다")
chk("conn.rollback(); conn.close()" in ins_body,
    "★★ ② 중복 기관명 조기반환도 rollback 후 close 한다")

seed_body = _body(DB_SRC, "seed")
chk(seed_body.count("datetime.now(KST)") >= 3,
    "★ ③ db.py seed() 의 naive datetime.now() 3곳이 KST 기준이다",
    f"실제 {seed_body.count('datetime.now(KST)')}곳")

_sched_start = APP_SRC.index('@app.delete("/api/schedule-events/')
_sched_end = APP_SRC.index("def api_schedule_event_del")
sched_del_head = APP_SRC[_sched_start:_sched_end]
chk('@require_role("중간관리자")' in sched_del_head,
    "★★ ④ api_schedule_event_del 이 중간관리자 이상으로 격상됐다"
    "(다른 삭제 라우트 8개와 동일)")

chk("사진 백업이 아예 없다" in DEPLOY_SRC,
    "★ ⑤ DEPLOY.md 콜아웃이 일일백업.bat 의 사진백업 누락을 명시한다")
chk("만 예외로 빠져 있다" in DEPLOY_SRC,
    "★ ⑤ DEPLOY.md 알려진 한계 표가 일일백업.bat 를 예외로 짚는다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 서버 호출로 레이스·권한 재현(round59 _RaceProxy 기법)")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round68_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import sqlite3 as _sqlite3
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','최고관리자')")
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('junior','x','검증하위','하위관리자')")
    ins_id = conn.execute(
        "INSERT INTO insurers(name,org_type,status,created_at) "
        "VALUES('레이스검증보험','손해보험','활성',?)", (DB.now(),)).lastrowid
    conn.commit()
    conn.close()

    client = A.app.test_client()
    _tok = "regress-round68-csrf-token"
    with client.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    class _RaceProxy:
        """conn.execute(trigger) 를 처음 만나는 순간 fx() 를 한 번 실행한다.
        실 스레딩 없이 '체크 통과 직후 남이 새치기' 를 결정론적으로 재현(round59 기법)."""
        def __init__(self, real, trigger, fx):
            self._real, self._trig, self._fx, self._fired = real, trigger, fx, False

        def execute(self, sql, *a, **kw):
            if not self._fired and sql.strip() == self._trig:
                self._fired = True
                self._fx()
            return self._real.execute(sql, *a, **kw)

        def __getattr__(self, name):
            return getattr(self._real, name)

    def _inject(sql, params):
        def _fx():
            c2 = _sqlite3.connect(os.environ["BOKGUON_DB_PATH"], timeout=5)
            c2.execute(sql, params)
            c2.commit(); c2.close()
        return _fx

    _real_get_db = DB.get_db

    # ── ① api_case_create 레이스 ──────────────────────────────────
    def _patched_1():
        return _RaceProxy(_real_get_db(), "BEGIN IMMEDIATE", _inject(
            "INSERT INTO cases(case_no,insurer,insurer_id,category,status,est_price,"
            "low_price,manager,created_at,status_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("RACE-CASE-01", "레이스검증보험", ins_id, "가드레일·방호울타리", "입찰중", 1000000, 0,
             "자동", DB.now(), DB.now())))
    DB.get_db = _patched_1
    try:
        r1 = client.post("/api/cases", json={
            "case_no": "RACE-CASE-01", "category": "가드레일·방호울타리",
            "insurer_id": ins_id, "est_price": "1000000"}, headers=_hdr)
    finally:
        DB.get_db = _real_get_db
    body1 = r1.get_json() or {}
    chk(r1.status_code == 400 and not body1.get("ok")
        and "이미 존재하는 접수번호" in (body1.get("error") or ""),
        "★★★ ① 동시 접수(다른 연결이 먼저 커밋)에도 깔끔한 400 을 받는다"
        "(고치기 전엔 UNIQUE 제약에 걸려 처리되지 않은 예외로 죽었다)",
        f"status={r1.status_code} body={body1}")
    _c = DB.get_db()
    n1 = _c.execute("SELECT COUNT(*) c FROM cases WHERE case_no=?",
                     ("RACE-CASE-01",)).fetchone()["c"]
    _c.close()
    chk(n1 == 1, "★★ ① 레이스 뒤에도 같은 접수번호 행이 정확히 1개다(중복 생성 없음)", n1)

    # ── ② api_insurer_create 레이스 ────────────────────────────────
    def _patched_2():
        return _RaceProxy(_real_get_db(), "BEGIN IMMEDIATE", _inject(
            "INSERT INTO insurers(name,org_type,status,created_at) VALUES(?,?,?,?)",
            ("레이스보험사02", "손해보험", "활성", DB.now())))
    DB.get_db = _patched_2
    try:
        r2 = client.post("/api/insurers", json={"name": "레이스보험사02"}, headers=_hdr)
    finally:
        DB.get_db = _real_get_db
    body2 = r2.get_json() or {}
    chk(r2.status_code == 400 and not body2.get("ok")
        and "이미 등록된 기관명" in (body2.get("error") or ""),
        "★★ ② 동시 등록(다른 연결이 먼저 커밋)에도 깔끔한 400 을 받는다"
        "(고치기 전엔 UNIQUE 제약이 없어 같은 이름 행이 조용히 2개 생겼다)",
        f"status={r2.status_code} body={body2}")
    _c = DB.get_db()
    n2 = _c.execute("SELECT COUNT(*) c FROM insurers WHERE name=?",
                     ("레이스보험사02",)).fetchone()["c"]
    _c.close()
    chk(n2 == 1, "★★ ② 레이스 뒤에도 같은 기관명 행이 정확히 1개다(중복 생성 없음)", n2)

    # ── ④ api_schedule_event_del 권한 ──────────────────────────────
    _c = DB.get_db()
    eid = _c.execute(
        "INSERT INTO schedule_events(title,event_date,created_by,created_at) "
        "VALUES('삭제검증','2026-09-01','admin',?)", (DB.now(),)).lastrowid
    _c.commit(); _c.close()

    client_jr = A.app.test_client()
    _tok_jr = "regress-round68-jr-csrf"
    with client_jr.session_transaction() as sess:
        sess["admin"] = "junior"; sess["admin_role"] = "하위관리자"; sess["admin_name"] = "검증하위"
        sess["_csrf"] = _tok_jr
    r4 = client_jr.delete(f"/api/schedule-events/{eid}", headers={"X-CSRF-Token": _tok_jr})
    chk(r4.status_code == 403,
        "★★ ④ 하위관리자는 일정 삭제가 403 으로 막힌다"
        "(고치기 전엔 하위관리자도 삭제를 통과시켰다)", r4.status_code)
    _c = DB.get_db()
    still = _c.execute("SELECT 1 FROM schedule_events WHERE id=?", (eid,)).fetchone()
    _c.close()
    chk(still is not None, "★ ④ 막힌 뒤 실제로 그 일정이 지워지지 않고 남아 있다", still)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 실행 — db.py seed() 의 KST 3곳(가짜 시각으로 tz 인자 여부 구분, round67 기법)")
    # ──────────────────────────────────────────────────────────
    from datetime import datetime as _real_datetime, timedelta as _td

    DB.init_db(force=True, seed_demo=False)

    class _FakeDT:
        @staticmethod
        def now(tz=None):
            if tz is None:
                return _real_datetime.now() + _td(days=9999)
            return _real_datetime.now(tz)
        strptime = staticmethod(_real_datetime.strptime)

    conn6 = DB.get_db()
    _real_db_dt = DB.datetime
    DB.datetime = _FakeDT
    try:
        DB.seed(conn6)
    finally:
        DB.datetime = _real_db_dt
    conn6.commit()

    _future_year = str((_real_datetime.now() + _td(days=9999)).year)
    completed_far = conn6.execute(
        "SELECT COUNT(*) c FROM cases WHERE completed_at LIKE ?",
        (f"{_future_year}%",)).fetchone()["c"]
    defect_created_far = conn6.execute(
        "SELECT COUNT(*) c FROM defects WHERE created_at LIKE ?",
        (f"{_future_year}%",)).fetchone()["c"]
    defect_due_far = conn6.execute(
        "SELECT COUNT(*) c FROM defects WHERE due_date LIKE ?",
        (f"{_future_year}%",)).fetchone()["c"]
    conn6.close()

    chk(completed_far == 0,
        "★ ③ seed() 의 cases.completed_at 이 tz 인자 있는 datetime.now(KST) 를 쓴다"
        "(naive 로 불렀다면 9999일 뒤 미래 연도가 찍혔을 것)", completed_far)
    chk(defect_created_far == 0,
        "★ ③ seed() 의 defects.created_at 이 KST 기준이다", defect_created_far)
    chk(defect_due_far == 0,
        "★ ③ seed() 의 defects.due_date 가 KST 기준이다", defect_due_far)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드68 실측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
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
