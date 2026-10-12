# -*- coding: utf-8 -*-
"""스캔 466라운드 회귀 — round429가 세운 "같은 사업자번호로 활성 협력사
두 곳" 방어의 틈 2곳.

(A2) `api_partner_update()`의 DUP_BIZNO 재확인이 "요청에 biz_no가
실려 있을 때만" 걸려 있었다 — status만 '활성'으로 바꾸는(재승인)
요청은 biz_no를 안 보내도 통과해, 이미 다른 활성 업체와 같은
사업자번호를 가진 채 잠자던 계정을 그대로 활성화할 수 있었다.

(A3) `api_partner_create()`에 형제(`api_application_update`, 7489행)와
달리 `BEGIN IMMEDIATE`가 없었다 — 중복확인 읽기와 INSERT 사이에 다른
요청이 끼어들 수 있는 구조(TOCTOU)였다.

[1] 소스 확인 — 두 수정 코드가 실제로 있음.
[2] A2 — 실제 Flask 앱으로 되돌림-증명(status만 PATCH해도 막히는지,
    옛 코드로 되돌리면 실제로 뚫리는지).
[3] A3 — 스레드가 아니라 **두 연결의 명령 순서를 직접 통제**해
    결정론적으로 재현: BEGIN IMMEDIATE가 없으면 두 연결이 순서대로
    호출돼도(진짜 동시가 아니어도) 중복이 그대로 생기고, 있으면 두
    번째 연결이 첫 연결이 커밋하기 전엔 아예 쓰기잠금을 못 얻어
    시작조차 못 함을 실측 — 스레드 타이밍에 기대지 않는 재현이라
    흔들리지 않는다.
"""
import io
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 466라운드 회귀 — 협력사 사업자번호 중복방지 틈 2곳")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

#  ⚠ 이 수정은 두 자리에 걸쳐 있다(prev 조회+dup검사 자리, 그리고 그 아래
#    rank검사 바로 앞의 옛 changed= 줄을 지운 자리) — 되돌림-증명도 두 자리
#    모두 원래대로 되돌려야 "고쳐지기 전 실제 동작"이 나온다(한쪽만 되돌리면
#    changed 미정의로 NameError만 나서 결함이 아니라 새 버그처럼 보인다).
#  ⚠⚠ [라운드493] 형제(api_application_update·api_partner_create)와 같은
#    BEGIN IMMEDIATE+conn.rollback()이 이 자리 두 조기반환에도 추가됐다 —
#    이 A2 되돌림은 라운드466 자신의 기여(재승인 시에도 검사가 도는 조건)만
#    되돌려야 하므로, 되돌림 전/후 블록 둘 다 그 rollback()은 그대로 남긴다
#    (안 그러면 .replace()가 매칭 실패로 조용히 no-op 되어, "되돌렸다고
#    믿는" 코드가 실제로는 원래대로 남아 대조군이 거짓 통과할 뻔했다 —
#    493 배터리에서 실제로 이 실패를 겪고서 알아냄).
A2_NEW_BLOCK_1 = '''        prev = one(conn.execute(
            "SELECT name, status, address, lat, lng, biz_no FROM partners WHERE id=?", (pid,)))
        if not prev:
            conn.rollback()
            return jsonify({"ok": False, "error": "없는 업체입니다."}), 404
        changed = "status" in d and (d.get("status") or "") != (prev["status"] or "")
        #  ⚠⚠ [429라운드] 형제(api_application_update 승인관문·api_partner_create,
        #    round248/429)는 같은 사업자번호로 활성 업체가 두 개 생기는 걸 막는데,
        #    기존 업체의 사업자번호를 이 화면에서 다른 활성 업체 것과 같은 값으로
        #    바꾸는 경로는 그 검사가 없었다.
        #  ⚠⚠ [라운드466] 위 방어가 "요청에 biz_no가 실려 있을 때만" 걸려 있었다
        #    — status만 '활성'으로 바꾸는(재승인) 요청은 biz_no를 안 보내도
        #    통과해, 이미 다른 활성 업체와 같은 사업자번호를 가진 채 잠자던
        #    계정을 그대로 활성화할 수 있었다(실측: status만 PATCH해 재현). 지금
        #    반영될 사업자번호(요청에 있으면 그 값, 없으면 기존 값)를 기준으로,
        #    "그 값으로 바뀌거나" "그 값을 가진 채 활성으로 바뀔 때" 둘 다 검사.
        _eff_biz = d["biz_no"] if ("biz_no" in d and d["biz_no"]) else prev["biz_no"]
        _biz_touched = "biz_no" in d and d["biz_no"]
        _activating = changed and (d.get("status") or "") == "활성"
        if (_biz_touched or _activating) and _eff_biz:
            _pdup = one(conn.execute(
                "SELECT name FROM partners WHERE biz_no=? AND status='활성' AND id<>?",
                (_eff_biz, pid)))
            if _pdup:
                conn.rollback()
                return jsonify({
                    "ok": False, "code": "DUP_BIZNO",
                    "error": str(Markup(
                        "이미 등록된 업체입니다. (사업자번호 일치: {}) "
                        "중복이 아닌지 확인해 주세요.").format(escape(_pdup["name"])))}), 409'''

A2_OLD_BLOCK_1 = '''        prev = one(conn.execute("SELECT name, status, address, lat, lng FROM partners WHERE id=?", (pid,)))
        if not prev:
            conn.rollback()
            return jsonify({"ok": False, "error": "없는 업체입니다."}), 404
        #  ⚠⚠ [429라운드] 형제(api_application_update 승인관문·api_partner_create,
        #    round248/429)는 같은 사업자번호로 활성 업체가 두 개 생기는 걸 막는데,
        #    기존 업체의 사업자번호를 이 화면에서 다른 활성 업체 것과 같은 값으로
        #    바꾸는 경로는 그 검사가 없었다.
        if "biz_no" in d and d["biz_no"]:
            _pdup = one(conn.execute(
                "SELECT name FROM partners WHERE biz_no=? AND status='활성' AND id<>?",
                (d["biz_no"], pid)))
            if _pdup:
                conn.rollback()
                return jsonify({
                    "ok": False, "code": "DUP_BIZNO",
                    "error": str(Markup(
                        "이미 등록된 업체입니다. (사업자번호 일치: {}) "
                        "중복이 아닌지 확인해 주세요.").format(escape(_pdup["name"])))}), 409'''

A2_NEW_BLOCK_2 = '        if changed and _admin_rank() < ROLE_RANK["중간관리자"]:'
A2_OLD_BLOCK_2 = ('        changed = "status" in d and (d.get("status") or "") != (prev["status"] or "")\n'
                  '        if changed and _admin_rank() < ROLE_RANK["중간관리자"]:')

chk(A2_NEW_BLOCK_1 in APP_SRC, "★★★★★ api_partner_update()가 biz_no까지 미리 읽고 changed를 앞당겨 계산한다")
chk(APP_SRC.count(A2_NEW_BLOCK_2) == 1,
    "되돌림-증명에 쓸 두 번째 지점(rank검사 줄)이 소스에 정확히 1번만 있다")
chk('_activating = changed and (d.get("status") or "") == "활성"' in APP_SRC,
    "★★★★★ 재승인(status→활성) 시에도 DUP_BIZNO를 재확인하는 조건이 있다")

A3_MARK = 'conn.execute("BEGIN IMMEDIATE")\n    if _biz:\n        _pdup = one(conn.execute(\n            "SELECT name FROM partners WHERE biz_no=? AND status=\'활성\'", (_biz,)))'
chk(A3_MARK in APP_SRC, "★★★★★ api_partner_create()가 중복확인 전에 BEGIN IMMEDIATE로 쓰기잠금을 잡는다")

# ══════════════════════════════════════════════════════════════
print("\n[2] A2 — 실제 Flask 앱: 재승인 우회 되돌림-증명")
# ══════════════════════════════════════════════════════════════
#  ⚠⚠ [라운드624] on-disk 되돌리기(파일에 직접 쓰고 서브프로세스 워커로,
#    별도 스크래치 DB 까지 새로 차려 재현)를 인메모리 exec 로 이관 —
#    api_partner_update() 는 @require_admin 데코레이터가 달린 단일 Flask
#    라우트 핸들러라 A.app.view_functions 딕셔너리 항목만 잠깐 치환한다
#    (round417/422 가 정착시킨 기법1). 신설 함수는 _api_partner_update_pre466
#    로 리네임해 사본 이름공간에 exec 한 뒤, 실 모듈의 A.require_admin 으로
#    다시 감싸 인증 동작은 그대로 유지한다. 되돌림 대상은 여전히 두 자리
#    (A2_NEW_BLOCK_1/2 → A2_OLD_BLOCK_1/2) 모두 — 한쪽만 되돌리면 changed
#    미정의로 NameError만 난다는 466 자신의 교훈은 그대로 유효하다. 이제
#    실제 파일은 전혀 안 건드리고, 옛 전용 서브프로세스 워커
#    (test_scan_round466_a2_worker.py)도 더는 필요 없어 삭제했다.
_tmpdir2 = tempfile.mkdtemp(prefix="r466_a2_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir2, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir2, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)


def _py_fn_body(src, fn_name):
    """함수 본문 — 다음 def뿐 아니라 다음 라우트의 @app. 데코레이터가 먼저
    나오면 거기서 자른다(round610 정착 기법)."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


try:
    import db as DB
    DB.init_db()
    import app as A

    BIZ466 = "1112223334"
    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','최고관리자')")
    pid_active = conn.execute(
        "INSERT INTO partners(name,partner_type,status,biz_no,lat,lng) "
        "VALUES('R466기존활성업체','시공사','활성',?,37.5,127.0)", (BIZ466,)).lastrowid
    pid_dormant_fixed = conn.execute(
        "INSERT INTO partners(name,partner_type,status,biz_no,lat,lng) "
        "VALUES('R466잠자던업체A','시공사','심사중',?,37.5,127.0)", (BIZ466,)).lastrowid
    pid_dormant_broken = conn.execute(
        "INSERT INTO partners(name,partner_type,status,biz_no,lat,lng) "
        "VALUES('R466잠자던업체B','시공사','심사중',?,37.5,127.0)", (BIZ466,)).lastrowid
    conn.commit()
    conn.close()

    def _admin_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["admin"] = "admin"
            sess["admin_name"] = "검증"
            sess["admin_role"] = "최고관리자"
            sess["_csrf"] = "r466-csrf"
        return c

    def _reactivate(pid):
        c = _admin_client()
        r = c.patch(f"/api/partners/{pid}",
                    json={"status": "활성", "status_reason": "재승인 테스트용 사유"},
                    headers={"X-CSRF-Token": "r466-csrf"})
        conn2 = DB.get_db()
        n_active = conn2.execute(
            "SELECT COUNT(*) n FROM partners WHERE biz_no=? AND status='활성'",
            (BIZ466,)).fetchone()["n"]
        conn2.close()
        return r, n_active

    r_fixed, n_active_fixed = _reactivate(pid_dormant_fixed)
    body_fixed = r_fixed.get_json()
    chk(r_fixed.status_code == 409 and (body_fixed or {}).get("code") == "DUP_BIZNO",
        "★★★★★ 고쳐진 코드는 status만 보낸 재승인도 DUP_BIZNO(409)로 막는다",
        (r_fixed.status_code, body_fixed))
    chk(n_active_fixed == 1,
        "고쳐진 코드에서는 활성 업체가 여전히 1곳뿐이다", n_active_fixed)

    _body466 = _py_fn_body(APP_SRC, "api_partner_update")
    chk(A2_NEW_BLOCK_1 in _body466 and A2_NEW_BLOCK_2 in _body466,
        "  (준비) api_partner_update() 본문 안에 두 되돌림 지점이 모두 있다")
    _old_body466 = (_body466
                    .replace("def api_partner_update(pid):",
                             "def _api_partner_update_pre466(pid):", 1)
                    .replace(A2_NEW_BLOCK_1, A2_OLD_BLOCK_1, 1)
                    .replace(A2_NEW_BLOCK_2, A2_OLD_BLOCK_2, 1))
    chk("_api_partner_update_pre466" in _old_body466
        and A2_OLD_BLOCK_1 in _old_body466 and A2_OLD_BLOCK_2 in _old_body466,
        "  (준비) 함수 리네임 + 두 지점 되돌리기가 정확히 적용됐다(실제 파일은 안 건드림)")

    _ns466 = dict(vars(A))
    exec(compile(_old_body466, "<round466_pre466_partner_update>", "exec"), _ns466)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_update_fn = A.require_admin(_ns466["_api_partner_update_pre466"])

    _orig_view466 = A.app.view_functions["api_partner_update"]
    A.app.view_functions["api_partner_update"] = old_update_fn
    try:
        r_broken, n_active_broken = _reactivate(pid_dormant_broken)
    finally:
        A.app.view_functions["api_partner_update"] = _orig_view466

    body_broken = r_broken.get_json()
    chk(r_broken.status_code == 200,
        "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림)는 status만 보낸 재승인이 그냥 통과한다(200)",
        (r_broken.status_code, body_broken))
    chk(n_active_broken == 2,
        "★★★★★ 옛 코드(되돌림)는 같은 사업자번호의 활성 업체가 실제로 2곳이 된다"
        " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
        n_active_broken)
    chk(A.app.view_functions["api_partner_update"] is _orig_view466,
        "  view_functions가 원래 함수객체로 복원됐다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2] A2 되돌림-증명 준비/실행", f"{type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] A3 — 명령순서 직접통제로 결정론적 재현 (스레드 타이밍에 안 기댐)")
# ══════════════════════════════════════════════════════════════
_tmpdir = tempfile.mkdtemp(prefix="r466_a3_")


def _fresh_db(name):
    path = os.path.join(_tmpdir, name)
    c = sqlite3.connect(path)
    c.execute("PRAGMA journal_mode = WAL")
    c.execute("""CREATE TABLE partners(id INTEGER PRIMARY KEY AUTOINCREMENT,
                 name TEXT, biz_no TEXT, status TEXT)""")
    c.commit()
    c.close()
    return path


BIZ = "1112223334"

# (구조) 잠금 없이 두 연결의 순서를 직접 통제 — 진짜 동시(threading)가 아니어도
# "확인 두 번, 그다음 삽입 두 번" 순서로만 불러도 중복이 생김을 보여준다.
old_db = _fresh_db("old.db")
connA = sqlite3.connect(old_db); connA.execute("PRAGMA journal_mode = WAL")
connB = sqlite3.connect(old_db); connB.execute("PRAGMA journal_mode = WAL")
rowA = connA.execute("SELECT name FROM partners WHERE biz_no=? AND status='활성'", (BIZ,)).fetchone()
rowB = connB.execute("SELECT name FROM partners WHERE biz_no=? AND status='활성'", (BIZ,)).fetchone()
chk(rowA is None and rowB is None,
    "옛 방식(잠금 없음): 두 연결 다 중복확인 단계에서 '중복 없음'을 본다(경합 창이 열림)")
connA.execute("INSERT INTO partners(name,biz_no,status) VALUES('A상사',?,'활성')", (BIZ,))
connA.commit()
connB.execute("INSERT INTO partners(name,biz_no,status) VALUES('B상사',?,'활성')", (BIZ,))
connB.commit()
n_old = connA.execute("SELECT COUNT(*) FROM partners WHERE biz_no=? AND status='활성'",
                       (BIZ,)).fetchone()[0]
chk(n_old == 2,
    "★★★★★ 옛 방식(BEGIN IMMEDIATE 없음)은 순서만 겹쳐도 활성 중복이 실제로 2건 생긴다",
    n_old)
connA.close(); connB.close()

# (수정) BEGIN IMMEDIATE — 두 번째 연결은 첫 연결이 커밋하기 전엔 쓰기잠금
# 시작조차 못 한다(짧은 busy_timeout으로 대기 대신 즉시 실패시켜 확인).
new_db = _fresh_db("new.db")
connC = sqlite3.connect(new_db); connC.execute("PRAGMA journal_mode = WAL")
connD = sqlite3.connect(new_db); connD.execute("PRAGMA journal_mode = WAL")
connD.execute("PRAGMA busy_timeout = 200")
connC.execute("BEGIN IMMEDIATE")
rowC = connC.execute("SELECT name FROM partners WHERE biz_no=? AND status='활성'", (BIZ,)).fetchone()
chk(rowC is None, "새 방식: 첫 연결이 잠금을 잡고 중복확인 — 아직 없음")
got_lock = True
try:
    connD.execute("BEGIN IMMEDIATE")
except sqlite3.OperationalError:
    got_lock = False
chk(got_lock is False,
    "★★★★★ 새 방식(BEGIN IMMEDIATE): 첫 연결이 커밋 전이면 두 번째 연결은 "
    "쓰기잠금 시작조차 실패한다 — 경합 창 자체가 구조적으로 없다")
connC.execute("INSERT INTO partners(name,biz_no,status) VALUES('C상사',?,'활성')", (BIZ,))
connC.commit()
n_new = connC.execute("SELECT COUNT(*) FROM partners WHERE biz_no=? AND status='활성'",
                       (BIZ,)).fetchone()[0]
chk(n_new == 1, "새 방식은 활성 중복이 안 생긴다(1건)", n_new)
connC.close(); connD.close()

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
