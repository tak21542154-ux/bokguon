# -*- coding: utf-8 -*-
"""스캔 295라운드 회귀 — 미조사 템플릿 7종 결함 3건, change_password.html·
   track_expired.html·dispatch_report.html·billing_guide.html·login.html·
   partner_login.html·insurer_login.html 을 이 세션 사상 첫 정밀조사한
   정밀조사 Agent가 발견 — billing_guide.html·3개 로그인화면은 실측 결과
   전부 클린.

  ①[심각] track_expired.html 이 사실상 도달 불가능했다. 진행조회 링크
     유효기간(TRACK_LINK_DAYS, 기본 180일)보다 짧은 개인정보 보유기간
     (BOKGUON_VICTIM_KEEP_DAYS, 기본 90일)에 취소·미수선종결·유찰로 끝난
     사건의 cases.track_token 이 NULL 로 지워지는데, track_page() 는
     WHERE track_token=? 로만 그 행을 찾아 토큰이 지워진 순간부터 그 행
     자체를 다시 못 찾았다 — "링크가 만료됐습니다"(410)를 보여줘야 할
     자리에 "페이지를 찾을 수 없습니다"(404)가 영원히 나갔다(실측: 실제로
     manage.py prune-personal 을 돌려 재현). 원문 토큰은 개인정보 파기
     대상이 맞지만(임의 값 자체가 신원을 드러내진 않아도 유효한 캐패시티라
     파기가 맞는 설계), "이 토큰이 예전에 발급된 적이 있는가"는 프라이버시
     정책을 안 늘려도 답할 수 있어야 한다 — 되돌릴 수 없는 일방향
     해시(cases.track_token_hash)를 새로 두어, 발급 시 함께 채우고(파기 때는
     원문만 지우고 해시는 남긴다) track_page() 가 이 해시로 찾은 뒤
     "원문이 이미 없으면 무조건 410"으로 판정하게 했다. 개인정보 보유기간
     자체(BOKGUON_VICTIM_KEEP_DAYS)는 손대지 않았다 — 순수 UX/아키텍처
     수정이지 보유기간 정책 변경이 아니다.
  ② dispatch_report.html(보험사에 넘기는 현장 출동 보고서)의 "산출 근거"
     칸이 field_agreements.engine_basis(estimate() 의 JSON 스냅샷 원문)를
     그대로 찍었다 — 형제 두 곳(api_insurer_field_agreement·합의이력)은
     전부 json.loads() 로 먼저 푸는데 이 보고서만 원문 그대로 내보내
     보험사에게 영어 필드명 섞인 JSON 문자열이 그대로 노출됐다(실측: 실제
     Flask 라우트로 재현 — "direct_cost"·"markup" 등이 그대로 찍힘).
     형제와 같은 파싱을 거쳐 수선 유형·직접공사비·할증·품명별 표·면책조항
     으로 구조화해 보여주도록 수정.
  ③ /change-password·/api/change-password 가 require_partner/require_insurer
     와 달리 _account_alive() 를 안 불러, 퇴출·정지된 협력사·보험사 계정도
     (세션이 살아있는 한 SESSION_REFRESH_EACH_REQUEST 때문에 만료도 안 됨)
     자기 비밀번호를 바꿀 수 있었다(실측: status='퇴출' 협력사로 실제
     비밀번호 변경 성공 — DB 의 password_hash 가 실제로 바뀜). 당장 다른
     보호기능은 전부 막혀 있어 새 권한을 얻진 못하지만, 나중에 계정이
     복구되면 그 사이 세션을 쥔 쪽이 정한 비밀번호가 그대로 살아남는다 —
     다른 보호 라우트와 같은 기준으로 맞췄다.

      python test_scan_round295_fixes.py
"""
import hashlib
import io
import json
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
DR_SRC = read(os.path.join("templates", "dispatch_report.html"))

print("=" * 72)
print("  스캔 295라운드 회귀 — 미조사 템플릿 7종 결함 3건")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk('("cases", "track_token_hash", "TEXT")' in DB_SRC,
    "★★★ db.py 에 track_token_hash 컬럼이 추가됐다")
chk("def _backfill_track_token_hash(conn" in DB_SRC,
    "★★★ 기존 행의 해시를 채우는 백필 함수가 있다")
chk("_backfill_track_token_hash(conn, verbose)" in DB_SRC,
    "★★★ migrate() 가 그 백필 함수를 실제로 부른다")
chk("track_token_hash" in APP_SRC and "hashlib.sha256(token.encode())" in APP_SRC,
    "★★★ issue_track_link()/track_page() 가 해시를 다룬다")
chk('WHERE track_token_hash=? AND COALESCE(is_demo,0)=0' in APP_SRC,
    "★★★ track_page() 가 이제 해시로 찾는다")
chk('c["track_token"] is None or _track_expired' in APP_SRC,
    "★★★ track_page() 가 원문이 이미 없으면(파기됨) 무조건 만료 처리한다")
chk("def _pw_route_dead_account_check" in APP_SRC,
    "★★★ change-password 두 라우트가 쓰는 계정 생존 확인 헬퍼가 있다")
chk("alive, _msg = _pw_route_dead_account_check()" in APP_SRC
    and "alive, msg = _pw_route_dead_account_check()" in APP_SRC,
    "★★★ change_password_page·api_change_password 둘 다 그 헬퍼를 부른다")
chk("basis = json.loads(ag[\"engine_basis\"])" in APP_SRC,
    "★★★ dispatch_report() 가 engine_basis 를 형제와 같은 방식으로 파싱한다")
chk("{% if basis %}" in DR_SRC and "agreement.engine_basis or agreement.engine_pattern" not in DR_SRC,
    "★★★ dispatch_report.html 이 더는 engine_basis 원문을 그대로 안 찍는다")

# ============================================================
print("\n[2] 실행 — track_expired.html: 실제 DB·라우트로 파기-후-만료 재현")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round295_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
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
                 "VALUES('r295admin','x','검증','최고관리자')")

    def _mk_case(no, **extra):
        cols = ["case_no", "status", "is_demo"] + list(extra.keys())
        vals = [no, extra.pop("status", "취소"), 0] + list(extra.values())
        ph = ",".join("?" * len(cols))
        conn.execute(f"INSERT INTO cases({','.join(cols)}) VALUES({ph})", vals)
        return conn.execute("SELECT id FROM cases WHERE case_no=?", (no,)).fetchone()["id"]

    # 2-a: issue_track_link() 가 발급과 동시에 해시를 채우는지
    cid_a = _mk_case("R295-A")
    token_a, _ = A.issue_track_link(conn, cid_a)
    conn.commit()
    row_a = conn.execute("SELECT track_token, track_token_hash FROM cases WHERE id=?", (cid_a,)).fetchone()
    chk(row_a["track_token_hash"] == hashlib.sha256(token_a.encode()).hexdigest(),
        "★★★ issue_track_link() 이 발급 시점에 정확한 해시를 채운다")

    # 2-b: 마이그레이션 백필 — issue_track_link() 를 안 거친(기존 행 흉내) 경우
    cid_b = _mk_case("R295-B")
    old_token = "legacyTokenForBackfillTest01"
    conn.execute("UPDATE cases SET track_token=?, track_issued_at=? WHERE id=?",
                 (old_token, DB.now(), cid_b))
    conn.commit()
    DB._backfill_track_token_hash(conn, verbose=False)
    conn.commit()
    row_b = conn.execute("SELECT track_token_hash FROM cases WHERE id=?", (cid_b,)).fetchone()
    chk(row_b["track_token_hash"] == hashlib.sha256(old_token.encode()).hexdigest(),
        "★★★ 백필 함수가 기존(발급 경로를 안 거친) 행의 해시도 정확히 채운다")

    client = A.app.test_client()

    # 2-c: 핵심 재현 — 파기(원문 NULL, 해시는 유지)된 뒤에도 410 이 나오는가
    conn.execute("UPDATE cases SET track_token=NULL WHERE id=?", (cid_a,))
    conn.commit()
    r_purged = client.get(f"/track/{token_a}")
    chk(r_purged.status_code == 410,
        "★★★ 파기(원문 NULL)된 링크는 404 가 아니라 410(만료)을 돌려준다"
        "(고치기 전엔 해시가 없어 행을 아예 못 찾아 404)", r_purged.status_code)
    chk("조회 기간이 지난 링크" in r_purged.get_data(as_text=True),
        "★★★ 그 410 응답이 실제로 track_expired.html 내용을 담고 있다")

    # 2-d: 회귀 없음 — 아직 살아있는(파기 전) 정상 토큰은 그대로 200
    cid_c = _mk_case("R295-C")
    token_c, _ = A.issue_track_link(conn, cid_c)
    conn.commit()
    r_live = client.get(f"/track/{token_c}")
    chk(r_live.status_code == 200, "정상(파기 전) 토큰은 여전히 200 을 돌려준다(회귀 없음)",
        r_live.status_code)

    # 2-e: 회귀 없음 — 진짜 존재한 적 없는(regex 는 통과하는) 토큰은 여전히 404
    r_fake = client.get("/track/neverIssuedTokenAbc123456")
    chk(r_fake.status_code == 404,
        "★★★ 한 번도 발급된 적 없는 토큰은 여전히 404 다(과잉관용 아님)", r_fake.status_code)

    # 2-f: 회귀 없음 — 아직 파기 안 됐지만 TRACK_LINK_DAYS 를 자연스럽게 넘긴 경우도 410
    cid_d = _mk_case("R295-D")
    token_d, _ = A.issue_track_link(conn, cid_d)
    conn.commit()
    conn.execute("UPDATE cases SET track_issued_at=datetime('now','-200 days') WHERE id=?", (cid_d,))
    conn.commit()
    r_aged = client.get(f"/track/{token_d}")
    chk(r_aged.status_code == 410,
        "★★★ 파기 전이라도 TRACK_LINK_DAYS(기본180일)를 자연히 넘기면 여전히 410"
        "(고치기 전과 동일한 기존 동작 — 회귀 없음)", r_aged.status_code)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드295 [2] track_expired.html 검증", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — dispatch_report.html: 실제 라우트로 JSON 원문 노출 재현")
# ------------------------------------------------------------
try:
    admin = A.app.test_client()
    atok = "r295-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r295admin"; sess["admin_name"] = "검증"
        sess["admin_role"] = "최고관리자"; sess["_csrf"] = atok

    conn = DB.get_db()
    cid_e = conn.execute(
        "INSERT INTO cases(case_no,status,is_demo) VALUES('R295-E','완료',0)"
    ).lastrowid or conn.execute("SELECT id FROM cases WHERE case_no='R295-E'").fetchone()["id"]
    basis_json = json.dumps({
        "name": "누수 배관 교체", "direct_cost": 452000, "markup": [1.15, 1.35],
        "gate": "표준단가 매칭", "engine_ver": "v3",
        "lines": [{"item": "PVC관 교체", "qty": 5, "unit_price": 30000, "amount": 150000}],
        "disclaimer": "실측 전 개산치이며 현장 확인 후 확정됩니다.",
    }, ensure_ascii=False)
    conn.execute(
        "INSERT INTO field_agreements(case_id, engine_basis, engine_pattern, status) "
        "VALUES(?,?,?,?)", (cid_e, basis_json, "누수", "합의"))
    conn.commit()
    conn.close()

    r = admin.get(f"/report/dispatch/{cid_e}")
    html = r.get_data(as_text=True)
    chk(r.status_code == 200, "실제 /report/dispatch/<cid> 응답이 200 이다", r.status_code)
    chk('"direct_cost"' not in html and "&#34;direct_cost&#34;" not in html,
        "★★★ JSON 원문(영어 키)이 더는 그대로 찍히지 않는다"
        "(고치기 전엔 direct_cost 등이 이스케이프된 채 그대로 노출)")
    chk("452,000원" in html or "452000" in html,
        "★★★ 직접공사비가 구조화된 숫자로 표시된다", "452,000 not found" if "452,000원" not in html else "")
    chk("PVC관 교체" in html, "★★★ 품명(lines) 이 표로 렌더링된다")
    chk("실측 전 개산치이며" in html, "★★★ 면책조항(disclaimer)이 렌더링된다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드295 [3] dispatch_report.html 검증", f"{type(e).__name__} {e}")

# ============================================================
print("\n[4] 실행 — change-password: 퇴출 계정 우회 차단 + 정상계정 회귀없음")
# ------------------------------------------------------------
try:
    conn = DB.get_db()
    conn.execute(
        "INSERT INTO partners(name, login_id, password_hash, status, partner_type) "
        "VALUES('R295퇴출업체','r295dead','%s','퇴출','시공사')" % DB.hash_pw("oldpw1234"))
    dead_pid = conn.execute("SELECT id FROM partners WHERE login_id='r295dead'").fetchone()["id"]
    conn.execute(
        "INSERT INTO partners(name, login_id, password_hash, status, partner_type) "
        "VALUES('R295정상업체','r295alive','%s','활성','시공사')" % DB.hash_pw("oldpw1234"))
    alive_pid = conn.execute("SELECT id FROM partners WHERE login_id='r295alive'").fetchone()["id"]
    conn.commit()
    conn.close()

    def _partner_session(pid, login_id, name):
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["partner_id"] = pid; sess["partner_login"] = login_id
            sess["partner_name"] = name; sess["partner_type"] = "시공사"
            sess["pw_role"] = "partner"; sess["_csrf"] = "r295-csrf"
        return c

    #  ⚠ /change-password(GET) 은 퇴출 계정이면 session.clear() 까지 한다(의도된
    #    동작) — 같은 클라이언트로 이어서 POST 하면 세션이 이미 비어 CSRF 부터
    #    걸린다. 페이지 검사와 API 검사는 각자 새 세션으로 독립되게 확인한다.
    dead_c1 = _partner_session(dead_pid, "r295dead", "R295퇴출업체")
    r_page = dead_c1.get("/change-password", follow_redirects=False)
    chk(r_page.status_code in (301, 302, 303, 307, 308),
        "★★★ 퇴출 계정은 /change-password 페이지에서 즉시 리다이렉트된다"
        "(고치기 전엔 200 으로 폼이 그대로 열렸다)", r_page.status_code)

    dead_c2 = _partner_session(dead_pid, "r295dead", "R295퇴출업체")
    r_api = dead_c2.post("/api/change-password", json={"current": "oldpw1234", "new": "NewPw56789!"},
                          headers={"X-CSRF-Token": "r295-csrf"})
    chk(r_api.status_code == 401,
        "★★★ 퇴출 계정은 /api/change-password 가 401 을 돌려준다"
        "(고치기 전엔 200 으로 실제 비밀번호가 바뀌었다)", (r_api.status_code, r_api.get_json()))

    conn = DB.get_db()
    hash_after = conn.execute("SELECT password_hash FROM partners WHERE id=?", (dead_pid,)).fetchone()["password_hash"]
    chk(DB.verify_pw("oldpw1234", hash_after),
        "★★★ 퇴출 계정의 비밀번호는 실제로 안 바뀌었다(DB 직접 확인)")
    conn.close()

    # 회귀 없음 — 정상('활성') 협력사는 여전히 비밀번호를 바꿀 수 있다
    alive_c = _partner_session(alive_pid, "r295alive", "R295정상업체")
    r_ok = alive_c.post("/api/change-password", json={"current": "oldpw1234", "new": "NewPw56789!"},
                         headers={"X-CSRF-Token": "r295-csrf"})
    chk(r_ok.status_code == 200 and (r_ok.get_json() or {}).get("ok") is True,
        "정상('활성') 협력사는 여전히 비밀번호를 바꿀 수 있다(회귀 없음)",
        (r_ok.status_code, r_ok.get_json()))
    conn = DB.get_db()
    hash_alive = conn.execute("SELECT password_hash FROM partners WHERE id=?", (alive_pid,)).fetchone()["password_hash"]
    chk(DB.verify_pw("NewPw56789!", hash_alive),
        "정상 협력사의 비밀번호가 실제로 새 값으로 바뀌었다(회귀 없음)")
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드295 [4] change-password 검증", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
