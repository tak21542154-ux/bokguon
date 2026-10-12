# -*- coding: utf-8 -*-
"""스캔 299라운드 회귀 — collect_emails.py·clean_collected_emails.py 짝 도구
   결함 4건, 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 재실행 자체
   멱등성(자기 자신 재실행)·데모격리(partners 테이블엔 is_demo 자체가 없음)·
   입력 신뢰경계(부실 URL·DNS실패가 배치 전체를 안 죽임)는 실측 결과 전부
   클린.

   ①[심각] partners.email 을 바꾸는 실사용 경로가(마이페이지 본인수정·연락처
      수정·엑셀 일괄등록·업체 정보수정 — 조사 에이전트는 앞 두 곳만 짚었으나
      독립검증 중 grep 으로 전수 확인해 두 곳을 추가로 더 찾음, 총 4곳) 전부
      email_source 를 안 건드렸다 — 담당자·업체 스스로 수집된 주소를 실제
      검증된 주소로 고쳐도 email_source 는 '수집(홈페이지)'로 영원히 남아,
      clean_collected_emails.py 가 이 표식 하나만 보고 "수집분이니 안전하게
      지워도 된다"고 오판해 사람이 방금 고친 정상 주소를 삭제했다(실측:
      PATCH 로 고친 직후 그 값이 그대로 삭제 대상 조건에 걸림). db.py 스키마
      주석이 이미 문서화해 둔 세 값("입점신청 / 직접입력 / 수집(홈페이지)")
      중 '직접입력'을 그대로 써서 네 경로 모두 email 이 바뀌면 함께 갱신하게
      고쳤다.
   ②[심각] clean_collected_emails.is_junk() 와 collect_emails.pick_emails()
      가 공유하는 BAD_LOCAL 판정이 `in`(부분열 포함) 검사였다 — local part 가
      흔한 실제 단어(latest·contest 등)이기만 해도 그 안에 test 가 부분열로
      들어 있어 "사람 주소 아님"으로 오판했다(실측: is_junk('latest@…')
      가 실제로 삭제 판정을 냄). 구두점으로 구분된 독립 조각일 때만 맞다고
      보는 공유 헬퍼(_bad_local_word_in)로 통일.
   ③[심각] collect_emails.py 가 이메일을 채울 때마다 email_consent 를
      무조건 0 으로 덮어썼다 — 이 도구가 대상으로 삼는 행(email='')이 신청
      승인 때(마케팅 수신동의 체크, 이메일란은 비워 둠) 이미 email_consent=1
      을 받아 둔 경우, 이 UPDATE 한 번으로 진짜 동의가 조용히 영구히
      사라지고 앱 어디에도 되돌릴 화면이 없었다. 이미 1이면 보존하고 그
      밖(0·NULL)만 0으로 명시하도록 수정.
   ④ 관리자 대시보드 집계(api_contact_summary)의 '수집' 카운트가 표식만
      세어, clean_collected_emails.py 가 방금 지운(email='') 행도 계속
      집계에 남았다(실측: 정리 직후에도 숫자가 안 줄어듦) — 지금 실제로
      이메일이 있는 행만 세도록 조건 추가.

      python test_scan_round299_fixes.py
"""
import http.server
import io
import os
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PASS, FAIL = [], []

#  ⚠⚠ [라운드299] db.py 는 이 값을 **import 시점**에 검사해 운영 DB 를
#    가리키면 SystemExit 한다(db.py:32-44, 파일명이 test_ 로 시작하고 경로가
#    운영 bokguon.db 와 같을 때만). collect_emails.py 가 자신도 모르게
#    db 를 딸려 들여오므로, 뒤쪽 절([2]) 에서야 collect_emails 를 처음
#    import 하면 그 시점엔 이미 db 모듈이 (환경변수 없이) 먼저 로드돼 있을
#    수 있다 — 반드시 다른 어떤 db 연관 import 보다도 먼저 여기서 지정한다
#    (실측: 순서를 안 지켰을 때 정확히 이 SystemExit 로 전체가 죽는 것을
#    확인).
_tmpdir0 = tempfile.mkdtemp(prefix="round299_setup_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir0, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir0, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
import db as DB                                                     # noqa: E402
DB.init_db()
import app as A                                                      # noqa: E402


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")
COLLECT_SRC = read("collect_emails.py")
CLEAN_SRC = read("clean_collected_emails.py")

print("=" * 72)
print("  스캔 299라운드 회귀 — 이메일수집 짝도구 email_source 미갱신·오탐·동의파괴")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — email_source 를 새로 갱신하는 4개 자리")
# ──────────────────────────────────────────────────────────────


def _section(src, start_marker, end_marker):
    i0 = src.index(start_marker)
    i1 = src.index(end_marker, i0 + len(start_marker))
    return src[i0:i1]


PROFILE_UPDATE = _section(APP_SRC, "\ndef api_partner_profile_update():", "\n\n\ndef ")
CONTACT_UPDATE = _section(APP_SRC, "\ndef api_contact_update(pid):", "\n\n\n@app.post")
CONTACT_IMPORT = _section(APP_SRC, "\ndef api_contact_import():", "\n\n\n@app.")
PARTNER_UPDATE = _section(APP_SRC, "\ndef api_partner_update(pid):", "\n\n\n@app.")

chk('sets.append("email_source=?"); vals.append("직접입력")' in CONTACT_UPDATE,
    "★★★ api_contact_update(연락처 수정) 가 email_source 를 갱신한다")
chk('fields.append("email_source=?"); vals.append("직접입력")' in PROFILE_UPDATE,
    "★★★ api_partner_profile_update(본인 마이페이지) 가 email_source 를 갱신한다")
chk('sets.append("email_source=?"); vals.append("직접입력")' in CONTACT_IMPORT,
    "★★★ api_contact_import(엑셀 일괄등록) 가 email_source 를 갱신한다")
chk('sets.append("email_source=?"); vals.append("직접입력")' in PARTNER_UPDATE,
    "★★★ api_partner_update(업체 정보수정) 가 email_source 를 갱신한다"
    "(조사 에이전트가 못 짚었던 네 번째 자리 — grep 전수확인으로 추가 발견)")
chk(CONTACT_IMPORT.count('vals.append("직접입력")') == 1,
    "★★ 엑셀 일괄등록은 이메일 열이 실제로 반영됐을 때만 email_source 를 바꾼다"
    "(형식오류로 건너뛴 셀까지 갱신하면 안 됨)")

print("\n[1b] 소스 확인 — BAD_LOCAL 판정 공유 헬퍼 + 동의보존 + 대시보드 집계")
chk(COLLECT_SRC.count("def _bad_local_word_in(") == 1,
    "★★★ _bad_local_word_in() 공유 헬퍼가 collect_emails.py 에 정확히 한 번 정의된다")
chk("_bad_local_word_in(local, BAD_LOCAL)" in COLLECT_SRC,
    "★★ collect_emails.pick_emails() 가 공유 헬퍼를 쓴다")
chk("from collect_emails import BAD_DOMAIN, BAD_LOCAL, PLATFORM_HOSTS, _bad_local_word_in" in CLEAN_SRC,
    "★★★ clean_collected_emails.py 가 공유 헬퍼를 들여온다")
chk("_bad_local_word_in(local, BAD_LOCAL)" in CLEAN_SRC,
    "★★★ clean_collected_emails.is_junk() 가 공유 헬퍼를 쓴다(고치기 전엔 `in` 부분열 검사)")
chk("email_consent=CASE WHEN email_consent=1 THEN 1 ELSE 0 END" in COLLECT_SRC,
    "★★★ collect_emails.py 가 이미 있는 동의(1)를 더는 무조건 0으로 안 덮어쓴다")
chk("AND TRIM(COALESCE(email,''))<>'' THEN 1 ELSE 0 END) col" in APP_SRC,
    "★★ api_contact_summary 의 '수집' 집계가 표식만이 아니라 실제 이메일 존재도 본다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — _bad_local_word_in 이 실제 문자열에 대해 정확히 판정하는가")
# ──────────────────────────────────────────────────────────────
try:
    import collect_emails as CE

    chk(CE._bad_local_word_in("latest", CE.BAD_LOCAL) is None,
        "★★★ 'latest' 는 더 이상 오탐되지 않는다(고치기 전엔 'test' 부분열로 걸림)")
    chk(CE._bad_local_word_in("contest", CE.BAD_LOCAL) is None,
        "★★ 'contest' 도 오탐되지 않는다")
    chk(CE._bad_local_word_in("test", CE.BAD_LOCAL) == "test",
        "★★★ 순수 'test' 는 여전히 정확히 잡는다(과소교정 아님, 회귀 없음)",
        CE._bad_local_word_in("test", CE.BAD_LOCAL))
    chk(CE._bad_local_word_in("no-reply", CE.BAD_LOCAL) is not None,
        "★★ 구두점으로 구분된 'no-reply' 는 여전히 잡는다", None)
    chk(CE._bad_local_word_in("test.account", CE.BAD_LOCAL) is not None,
        "★★ 'test.account' 처럼 점으로 구분돼도 잡는다", None)
    chk(CE._bad_local_word_in("info", CE.BAD_LOCAL) is None,
        "★ BAD_LOCAL 에 없는 정상 단어는 그대로 통과한다(회귀 없음)", None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드299 [2] _bad_local_word_in 실측", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 4개 실사용 경로가 실제로 email_source 를 갱신하는가(격리 DB, 실제 라우트)")
# ──────────────────────────────────────────────────────────────
try:
    client = A.app.test_client()
    _tok = "regress-round299-csrf-token"
    _hdr = {"X-CSRF-Token": _tok}

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin299','x','검증','최고관리자')")

    def mk_partner(mark):
        return conn.execute(
            "INSERT INTO partners(name,partner_type,status,email,email_source) "
            "VALUES(?,'시공사','활성','old@collected.invalid','수집(홈페이지)')",
            (f"R299-{mark}",)).lastrowid

    p_contact = mk_partner("연락처수정")
    p_import = mk_partner("엑셀등록")
    p_general = mk_partner("업체정보수정")
    conn.commit()

    with client.session_transaction() as sess:
        sess["admin"] = "admin299"; sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = _tok

    # ── (1) 연락처 전용 수정 화면 ──
    r1 = client.patch(f"/api/contacts/{p_contact}", json={"email": "fixed1@real-corp.com"}, headers=_hdr)
    chk(r1.status_code == 200, "STEP 연락처 수정 API 호출 성공", r1.status_code)
    row1 = A.one(DB.get_db().execute("SELECT email, email_source FROM partners WHERE id=?", (p_contact,)))
    chk(row1["email"] == "fixed1@real-corp.com" and row1["email_source"] == "직접입력",
        "★★★ 연락처 수정 뒤 email_source 가 '직접입력'으로 바뀐다", dict(row1))

    # ── (2) 엑셀 일괄등록 ──
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["업체명", "이메일"])
    ws.append([f"R299-엑셀등록", "fixed2@real-corp.com"])
    xbuf = io.BytesIO()
    wb.save(xbuf)
    xbuf.seek(0)
    r2 = client.post("/api/contacts/import", data={"file": (xbuf, "test.xlsx")},
                      content_type="multipart/form-data", headers=_hdr)
    chk(r2.status_code == 200 and r2.get_json().get("updated") == 1,
        "STEP 엑셀 일괄등록 API 호출 성공(1건 갱신)", (r2.status_code, r2.get_json()))
    row2 = A.one(DB.get_db().execute("SELECT email, email_source FROM partners WHERE id=?", (p_import,)))
    chk(row2["email"] == "fixed2@real-corp.com" and row2["email_source"] == "직접입력",
        "★★★ 엑셀 일괄등록 뒤 email_source 가 '직접입력'으로 바뀐다", dict(row2))

    # ── (3) 업체 정보수정(일반) ──
    r3 = client.patch(f"/api/partners/{p_general}", json={"email": "fixed3@real-corp.com"}, headers=_hdr)
    chk(r3.status_code == 200, "STEP 업체 정보수정 API 호출 성공", r3.status_code)
    row3 = A.one(DB.get_db().execute("SELECT email, email_source FROM partners WHERE id=?", (p_general,)))
    chk(row3["email"] == "fixed3@real-corp.com" and row3["email_source"] == "직접입력",
        "★★★ 업체 정보수정 뒤 email_source 가 '직접입력'으로 바뀐다(네 번째 자리)", dict(row3))

    # ── (4) 협력사 본인 마이페이지 ──
    p_self = conn.execute(
        "INSERT INTO partners(name,partner_type,status,email,email_source,login_id,password_hash) "
        "VALUES('R299-본인수정','시공사','활성','old@collected.invalid','수집(홈페이지)','r299self','x')"
    ).lastrowid
    conn.commit()
    with client.session_transaction() as sess2:
        sess2.clear(); sess2["partner_id"] = p_self; sess2["portal_role"] = "최고관리자"; sess2["_csrf"] = _tok
    r4 = client.patch("/api/partner/profile", json={"email": "fixed4@real-corp.com"}, headers=_hdr)
    chk(r4.status_code == 200, "STEP 본인 마이페이지 수정 API 호출 성공", r4.status_code)
    row4 = A.one(DB.get_db().execute("SELECT email, email_source FROM partners WHERE id=?", (p_self,)))
    chk(row4["email"] == "fixed4@real-corp.com" and row4["email_source"] == "직접입력",
        "★★★ 본인 마이페이지 수정 뒤 email_source 가 '직접입력'으로 바뀐다", dict(row4))

    #  ⚠ 위에서 협력사 세션으로 바꿔치기했으니, 아래 admin 전용 API(대시보드
    #    집계)를 계속 쓰려면 admin 세션으로 되돌려 놓는다.
    with client.session_transaction() as sess3:
        sess3.clear()
        sess3["admin"] = "admin299"; sess3["admin_role"] = "최고관리자"
        sess3["admin_name"] = "검증"; sess3["_csrf"] = _tok

    # ── clean_collected_emails.py 의 실제 WHERE 조건이 이제 이 네 행을 안 잡는가 ──
    conn2 = DB.get_db()
    still_collected = conn2.execute(
        "SELECT COUNT(*) FROM partners WHERE email_source='수집(홈페이지)' "
        "  AND id IN (?,?,?,?)", (p_contact, p_import, p_general, p_self)).fetchone()[0]
    chk(still_collected == 0,
        "★★★ 네 행 모두 clean_collected_emails.py 의 삭제대상 조건에서 빠졌다"
        "(고치기 전엔 전부 그대로 걸려 사람이 고친 주소가 삭제될 수 있었다)",
        still_collected)

    # ══════════════════════════════════════════════════════════
    print("\n[4] 실행 — api_contact_summary 가 실제로 삭제 뒤 숫자를 줄이는가")
    # ──────────────────────────────────────────────────────────
    p_stale = conn.execute(
        "INSERT INTO partners(name,partner_type,status,email,email_source) "
        "VALUES('R299-집계용','시공사','활성','stale@collected.invalid','수집(홈페이지)')"
    ).lastrowid
    conn.commit()
    r5 = client.get("/api/contacts/summary", headers=_hdr)
    before_col = next(s["collected"] for s in r5.get_json()["summary"] if s["type"] == "시공사")
    conn3 = DB.get_db()
    conn3.execute("UPDATE partners SET email='' WHERE id=?", (p_stale,))  # clean_collected_emails.py 와 같은 동작
    conn3.commit()
    r6 = client.get("/api/contacts/summary", headers=_hdr)
    after_col = next(s["collected"] for s in r6.get_json()["summary"] if s["type"] == "시공사")
    chk(after_col == before_col - 1,
        "★★★ 이메일을 지운 만큼 '수집' 집계가 실제로 줄어든다"
        "(고치기 전엔 표식만 셌으므로 안 줄었다)", (before_col, after_col))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드299 [3][4] 실측", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[5] 실행 — collect_emails.py 가 실제로 기존 동의(1)를 보존하는가"
      "(로컬 가짜 서버 + 실제 CLI 서브프로세스)")
# ──────────────────────────────────────────────────────────────
_tmpdir2 = tempfile.mkdtemp(prefix="round299_collect_")


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            "<html><body>대표문의: r299fixture@localtest.invalid</body></html>".encode("utf-8"))

    def log_message(self, *a):
        pass


try:
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()

    _dbpath = os.path.join(_tmpdir2, "verify.db")
    _env = dict(os.environ)
    _env["BOKGUON_DB_PATH"] = _dbpath
    _env["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir2, "uploads")
    _env["BOKGUON_ENV"] = "dev"
    _env["BOKGUON_SEED_DEMO"] = "0"
    #  [라운드517] collect_emails.py 가 이제 127.0.0.1 등 내부 주소로의 접속을
    #  SSRF 방어로 막는다 — 이 서브프로세스는 그 방어를 시험하는 게 아니라
    #  동의 보존 로직을 시험하므로, 이 테스트 전용 로컬 서버만 예외 허용한다.
    _env["BOKGUON_COLLECT_ALLOW_LOCAL"] = "1"

    import db as DB2
    DB2.DB_PATH = _dbpath
    DB2.init_db()
    conn = DB2.get_db()
    p_consented = conn.execute(
        "INSERT INTO partners(name,partner_type,status,website,email,email_consent) "
        "VALUES('R299-동의보유','시공사','활성',?, '', 1)",
        (f"http://127.0.0.1:{port}/",)).lastrowid
    conn.commit()
    conn.close()

    r = subprocess.run([PY, "-u", "collect_emails.py", "--limit", "5"], cwd=HERE, env=_env,
                        capture_output=True, text=True, encoding="utf-8", timeout=60)
    chk(r.returncode == 0, "STEP collect_emails.py 실제 서브프로세스 실행 성공",
        (r.returncode, (r.stdout + r.stderr)[-800:]))

    import sqlite3
    conn = sqlite3.connect(_dbpath)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT email, email_consent, email_source FROM partners WHERE id=?",
                        (p_consented,)).fetchone()
    conn.close()
    chk(row["email"] == "r299fixture@localtest.invalid",
        "STEP 실제 로컬 서버에서 이메일을 정상적으로 찾아 저장했다(전제 확인)", dict(row))
    chk(row["email_consent"] == 1,
        "★★★ 이미 있던 동의(1)가 수집 후에도 그대로 보존된다"
        "(고치기 전엔 이 UPDATE 한 번으로 무조건 0이 됐다)", row["email_consent"])
finally:
    try:
        server.shutdown()
    except Exception:
        pass
    for k in ("BOKGUON_DB_PATH", "BOKGUON_UPLOAD_DIR", "BOKGUON_ENV", "BOKGUON_SEED_DEMO"):
        os.environ.pop(k, None)
    import shutil
    shutil.rmtree(_tmpdir2, ignore_errors=True)
    shutil.rmtree(_tmpdir0, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
