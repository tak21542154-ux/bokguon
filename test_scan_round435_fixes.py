# -*- coding: utf-8 -*-
"""스캔 435라운드 회귀 — 두 각도 모두 결함 없음(클린), 코드 수정 없음.

   정밀조사 Agent(각도1: 사진·문서 서빙 라우트의 소유권(IDOR) 검사, 각도2:
   관리자 자기잠금·최후 최고관리자 보호)가 조사했고, 둘 다 이미 올바르게
   방어돼 있음을 실제 Flask test_client 실행으로 확인했다(이 세션의 다른
   라운드처럼 "결함을 찾아 고쳤다"가 아니라 "이미 맞는 코드를 실측으로
   증명했다"는 점이 다르다).

   [각도1] 사진·문서를 실제로 내보내는 라우트는 앱 전체에서
   `/api/photos/<pid>/file`(app.py:12008-) 하나뿐이고, 그 유일한 인가
   관문 `_photo_visible_to()`(app.py:11414-11497)가 세션의 조직(보험사/
   협력사)이 그 사진이 속한 사건의 실제 당사자인지를 검사한다. 사건
   상세·사진목록·하자사진 라우트도 각각 `insurer_id`/`partner_id` 정확
   일치(`_defect_visible_to()` app.py:14311-14319 포함)로 막는다. 다만
   `test_partner_leak.py`(협력사 쪽, 라이브서버 대상)에 대응하는 **보험사
   쪽 IDOR 회귀 테스트가 이 저장소에 하나도 없었다** — 코드 자체는
   클린이지만 향후 리팩터링을 잡아줄 자동 회귀가 없는 커버리지 공백이었다
   (트레이드오프 없는 "그냥 고치면 되는 것"). 이 테스트가 그 공백을
   메운다 — 단, 무거운 라이브서버(port 8799) 방식이 아니라 이 세션의
   `test_scan_round*.py` 들과 같은 인프로세스 스크래치DB 방식으로 작성해
   `run_all_tests.py --quick` 에 바로 편입되게 했다(비례성 판단).

   [각도2] 관리자 계정 관리(app.py:1624-1751)는 이미 (a) 본인 계정 삭제
   차단(1724-1726), (b) 최후 최고관리자 삭제·강등 차단(1686-1692·1727-
   1731)을 갖추고 있고, 둘 다 `BEGIN IMMEDIATE`(1676·1719)로 확인~변경을
   원자적으로 묶어 두 최고관리자가 서로를 동시에 지우거나 강등해도
   최소 1명은 반드시 생존한다(실스레드 동시성으로 실측). `_account_alive()`
   (518-568)가 매 요청마다 역할을 재조회해 강등이 다음 요청부터 바로
   먹는다(세션 캐시 우회 불가). `admins` 테이블(db.py:137-144)엔애초에
   `is_active` 류 컬럼이 없어 "비활성화" 우회 경로 자체가 존재하지 않는다.

   [3]은 이 테스트에 실제 탐지력이 있는지 증명한다 — 이번 라운드는 버그를
   고친 게 아니라 이미 맞는 코드를 확인했을 뿐이므로, 되돌릴 "옛 코드"가
   없다. 대신 두 방어 중 하나씩을 임시로 무력화해(한 줄만) 이 테스트가
   실제로 잡아내는지(공허한 통과가 아닌지) 확인한 뒤 즉시 원본으로
   복원한다(같은 파일의 다른 라운드가 쓰는 되돌리기 패턴을 "고친 결과
   증명" 대신 "탐지력 증명" 방향으로 적용한 것).

       python test_scan_round435_fixes.py
"""
import io
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(HERE, "app.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

print("=" * 72)
print("  스캔 435라운드 회귀 — 사진/문서 IDOR·관리자 자기잠금 (둘 다 클린 확인)")
print("=" * 72)

_tmpdir = tempfile.mkdtemp(prefix="round435_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB
DB.init_db()
import app as A

PW = "Testpw123!"
conn = DB.get_db()

# ══════════════════════════════════════════════════════════════
#  각도1 픽스처 — 사건 A(보험사I1/업체P1) · 사건 B(보험사I2/업체P2)
# ══════════════════════════════════════════════════════════════
i1 = conn.execute("INSERT INTO insurers(name,login_id,password_hash,status) "
                   "VALUES('I1보험사','r435_ins1',?, '활성')", (DB.hash_pw(PW),)).lastrowid
i2 = conn.execute("INSERT INTO insurers(name,login_id,password_hash,status) "
                   "VALUES('I2보험사','r435_ins2',?, '활성')", (DB.hash_pw(PW),)).lastrowid
p1 = conn.execute("INSERT INTO partners(name,partner_type,status,category,region,"
                   "login_id,password_hash,created_at) "
                   "VALUES('P1업체','시공사','활성','가드레일','서울',"
                   "'r435_par1',?,?)", (DB.hash_pw(PW), DB.now())).lastrowid
p2 = conn.execute("INSERT INTO partners(name,partner_type,status,category,region,"
                   "login_id,password_hash,created_at) "
                   "VALUES('P2업체','시공사','활성','가드레일','서울',"
                   "'r435_par2',?,?)", (DB.hash_pw(PW), DB.now())).lastrowid
case_a = conn.execute(
    "INSERT INTO cases(case_no,status,category,region,address,insurer_id,partner_id,"
    "                  insurer,partner_name,created_at) "
    "VALUES('R435-A','시공중','가드레일','서울','서울 A현장 상세주소 123',?,?,"
    "       'I1보험사','P1업체',?)", (i1, p1, DB.now())).lastrowid
photo_a = conn.execute(
    "INSERT INTO photos(case_id,partner_id,rel_path,orig_name,mime,kind,review_status,"
    "                   uploader,uploader_role,created_at) "
    "VALUES(?,?, 'r435_a.jpg','a.jpg','image/jpeg','시공중','승인','P1업체','협력사',?)",
    (case_a, p1, DB.now())).lastrowid
defect_a = conn.execute(
    "INSERT INTO defects(defect_no,case_id,case_no,insurer_id,partner_id,category,region,"
    "                    title,content,status,created_at) "
    "VALUES('R435-DEF-A',?,'R435-A',?,?,'가드레일','서울','금이 감','상세',"
    "       '접수',?)", (case_a, i1, p1, DB.now())).lastrowid
conn.commit()

_updir = os.environ["BOKGUON_UPLOAD_DIR"]
os.makedirs(_updir, exist_ok=True)
with open(os.path.join(_updir, "r435_a.jpg"), "wb") as f:
    f.write(b"\xff\xd8\xff\xe0FAKEJPEGDATA")


def login_insurer(login_id):
    c = A.app.test_client()
    r = c.post("/api/insurer/login", json={"login_id": login_id, "password": PW})
    assert r.status_code == 200, (login_id, r.status_code, r.get_data(as_text=True))
    return c


def login_partner(login_id):
    c = A.app.test_client()
    r = c.post("/api/partner/login", json={"login_id": login_id, "password": PW})
    assert r.status_code == 200, (login_id, r.status_code, r.get_data(as_text=True))
    return c


ins2 = login_insurer("r435_ins2")   # 사건B 소속 보험사(사건A에는 남)
par2 = login_partner("r435_par2")   # 사건B 소속 업체(사건A에는 남)
ins1 = login_insurer("r435_ins1")   # 사건A 소속(대조군 — 열려야 정상)
par1 = login_partner("r435_par1")   # 사건A 소속(대조군 — 열려야 정상)

print("\n[1] 보험사I2·업체P2(둘 다 사건B 소속) 세션으로 사건A 자원 접근 — 전부 차단돼야 한다")
r = ins2.get(f"/api/insurer/cases/{case_a}/detail")
chk(r.status_code == 404, "★★★ GET /api/insurer/cases/{A}/detail — 타 보험사 차단(404)", r.status_code)
r = ins2.get(f"/api/insurer/cases/{case_a}/bids")
chk(r.status_code == 404, "★★★ GET /api/insurer/cases/{A}/bids — 타 보험사 차단(404)", r.status_code)
r = ins2.get(f"/api/insurer/cases/{case_a}/field-agreement")
chk(r.status_code == 404, "★★★ GET /api/insurer/cases/{A}/field-agreement — 타 보험사 차단(404)", r.status_code)
r = ins2.get(f"/api/cases/{case_a}/photos")
chk(r.status_code in (401, 403), "★★★ GET /api/cases/{A}/photos — 타 보험사 차단", r.status_code)
r = ins2.get(f"/api/photos/{photo_a}/file")
chk(r.status_code in (401, 403, 404), "★★★★★ GET /api/photos/{photoA}/file — 타 보험사 차단(핵심 IDOR 관문)",
    r.status_code)
r = ins2.get(f"/api/defects/{defect_a}/photos")
chk(r.status_code in (401, 403, 404), "★★★ GET /api/defects/{defectA}/photos — 타 보험사 차단", r.status_code)

r = par2.get(f"/api/partner/cases/{case_a}/detail")
chk(r.status_code == 403, "★★★ GET /api/partner/cases/{A}/detail — 타 업체 차단(403)", r.status_code)
r = par2.get(f"/api/cases/{case_a}/photos")
chk(r.status_code in (401, 403), "★★★ GET /api/cases/{A}/photos — 타 업체 차단", r.status_code)
r = par2.get(f"/api/photos/{photo_a}/file")
chk(r.status_code in (401, 403, 404), "★★★★★ GET /api/photos/{photoA}/file — 타 업체 차단(핵심 IDOR 관문)",
    r.status_code)
r = par2.get(f"/api/defects/{defect_a}/photos")
chk(r.status_code in (401, 403, 404), "★★★ GET /api/defects/{defectA}/photos — 타 업체 차단", r.status_code)

print("\n[2] 대조군 — 사건A 소속 보험사I1·업체P1 은 정상적으로 열려야 한다(과잉차단 아님)")
r = ins1.get(f"/api/insurer/cases/{case_a}/detail")
chk(r.status_code == 200, "GET /api/insurer/cases/{A}/detail (보험사I1=소유주)", r.status_code)
r = par1.get(f"/api/partner/cases/{case_a}/detail")
chk(r.status_code == 200, "GET /api/partner/cases/{A}/detail (업체P1=소유주)", r.status_code)
r = par1.get(f"/api/cases/{case_a}/photos")
chk(r.status_code == 200, "GET /api/cases/{A}/photos (업체P1=소유주)", r.status_code)
r = par1.get(f"/api/photos/{photo_a}/file")
chk(r.status_code == 200, "GET /api/photos/{photoA}/file (업체P1=소유주, 실제 바이트 수신)", r.status_code)
r = ins1.get(f"/api/defects/{defect_a}/photos")
chk(r.status_code == 200, "GET /api/defects/{defectA}/photos (보험사I1=소유주)", r.status_code)


# ══════════════════════════════════════════════════════════════
#  각도2 — 관리자 자기잠금 · 최후 최고관리자 보호
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("  각도2 — 관리자 자기잠금 / 최후 최고관리자 보호")
print("=" * 72)


def admin_client(username, role):
    c = A.app.test_client()
    tok = f"csrf-{username}"
    with c.session_transaction() as sess:
        sess["admin"] = username; sess["admin_role"] = role; sess["admin_name"] = "검증"
        sess["_csrf"] = tok
    return c, {"X-CSRF-Token": tok}


def mkadmin(username, role):
    c2 = DB.get_db()
    aid = c2.execute(
        "INSERT INTO admins(username,password_hash,name,role,created_at) "
        "VALUES(?,?,?,?,?)", (username, DB.hash_pw(PW), username, role, DB.now())).lastrowid
    c2.commit(); c2.close()
    return aid


def super_count():
    c2 = DB.get_db()
    n = c2.execute("SELECT COUNT(*) n FROM admins WHERE role='최고관리자'").fetchone()["n"]
    c2.close()
    return n


print("\n[3] 최고관리자가 정확히 1명뿐일 때 — 자기 자신 삭제·강등 둘 다 막혀야 한다")
solo_id = mkadmin("r435_solo1", "최고관리자")
chk(super_count() == 1, "  (사전조건) 최고관리자 정확히 1명", super_count())
solo, solo_hdr = admin_client("r435_solo1", "최고관리자")
r = solo.delete(f"/api/admins/{solo_id}", headers=solo_hdr)
chk(r.status_code == 409, "★★★★★ 유일한 최고관리자의 자기 계정 삭제 차단(409)", (r.status_code, r.get_json()))
r = solo.patch(f"/api/admins/{solo_id}", json={"role": "중간관리자"}, headers=solo_hdr)
chk(r.status_code == 409, "★★★★★ 유일한 최고관리자의 자기 강등 차단(409)", (r.status_code, r.get_json()))
chk(super_count() == 1, "  삭제·강등 시도 후에도 여전히 최고관리자 1명(락아웃 없음)", super_count())

print("\n[4] 최고관리자가 여러 명일 때 — 다른 한 명 삭제/강등은 허용(과잉차단 아님)")
dup_a = mkadmin("r435_dup_a", "최고관리자")
dup_b = mkadmin("r435_dup_b", "최고관리자")
dup_a_c, dup_a_hdr = admin_client("r435_dup_a", "최고관리자")
r = dup_a_c.delete(f"/api/admins/{dup_b}", headers=dup_a_hdr)
chk(r.status_code == 200, "  최고관리자 여러 명 중 1명(타인) 삭제는 허용", (r.status_code, r.get_json()))
dup_c = mkadmin("r435_dup_c", "최고관리자")
r = dup_a_c.patch(f"/api/admins/{dup_c}", json={"role": "하위관리자"}, headers=dup_a_hdr)
chk(r.status_code == 200, "  최고관리자 여러 명 중 1명(타인) 강등은 허용", (r.status_code, r.get_json()))

print("\n[5] 강등된 계정은 세션이 살아있어도 다음 요청부터 즉시 하위 권한으로 취급된다(캐시된 role 문제)")
dup_c_c, dup_c_hdr = admin_client("r435_dup_c", "최고관리자")   # 방금 하위관리자로 강등된 계정
r = dup_c_c.get("/api/admins", headers=dup_c_hdr)
chk(r.status_code == 403, "★★★★★ 강등된 계정이 세션엔 최고관리자로 남아 있어도 서버가 즉시 재확인해 403",
    r.status_code)


def force_exactly_two_supers(keep_a, keep_b):
    """keep_a·keep_b 를 뺀 나머지 최고관리자를 전부 하위관리자로 내려 '진짜 마지막
    둘만 남은' 레이스 조건을 만든다(제3의 최고관리자가 버텨 주면 레이스가 무의미해진다)."""
    c9 = DB.get_db()
    c9.execute("UPDATE admins SET role='하위관리자' WHERE role='최고관리자' AND id NOT IN (?,?)",
               (keep_a, keep_b))
    c9.commit(); c9.close()


def run_mutual(label, action_fn, race_a_name, race_b_name, race_a_id, race_b_id):
    force_exactly_two_supers(race_a_id, race_b_id)
    chk(super_count() == 2, f"  ({label}, 사전조건) 최고관리자 정확히 2명", super_count())
    ca, ha = admin_client(race_a_name, "최고관리자")
    cb, hb = admin_client(race_b_name, "최고관리자")
    results, errs = {}, []

    def worker(key, client, hdr, target_id):
        try:
            results[key] = action_fn(client, hdr, target_id)
        except Exception as e:                                      # noqa: BLE001
            errs.append((key, e))

    t1 = threading.Thread(target=worker, args=("a_on_b", ca, ha, race_b_id))
    t2 = threading.Thread(target=worker, args=("b_on_a", cb, hb, race_a_id))
    t1.start(); t2.start(); t1.join(15); t2.join(15)
    chk(not errs, f"★★★★★ {label} 동시실행 중 예외 없음", errs)
    codes = sorted(v[0] for v in results.values())
    final_n = super_count()
    chk(final_n >= 1,
        f"★★★★★★★★★★ {label} — 동시 상호작용 후에도 최고관리자가 0명으로 전멸하지 않는다(TOCTOU 락아웃 재현 시도)",
        (codes, final_n, results))
    chk(codes == [200, 409] or codes == [409, 409],
        f"  {label} — 정확히 하나만 성공하거나 둘 다 거부", (codes, results))


print("\n[6] 동시성 — 최고관리자 정확히 2명일 때 서로가 서로를 동시에 삭제/강등하면?")
race_a = mkadmin("r435_race_a", "최고관리자")
race_b = mkadmin("r435_race_b", "최고관리자")
run_mutual("상호삭제", lambda c, h, tid: (lambda r: (r.status_code, r.get_json()))(
    c.delete(f"/api/admins/{tid}", headers=h)), "r435_race_a", "r435_race_b", race_a, race_b)

race_c = mkadmin("r435_race_c", "최고관리자")
race_d = mkadmin("r435_race_d", "최고관리자")
run_mutual("상호강등", lambda c, h, tid: (lambda r: (r.status_code, r.get_json()))(
    c.patch(f"/api/admins/{tid}", json={"role": "하위관리자"}, headers=h)),
    "r435_race_c", "r435_race_d", race_c, race_d)

conn.close()

# ============================================================
print("\n[7] 탐지력 증명 — 방어를 하나씩 임시로 무력화하면 위 검사가 실제로 잡아내는가")
# ------------------------------------------------------------
#  이번 라운드는 버그를 고친 게 아니라 이미 맞는 코드를 확인했을 뿐이므로
#  되돌릴 "옛 코드"가 없다 — 대신 한 줄씩 무력화해 이 테스트에 탐지력이
#  있는지(공허한 통과가 아닌지) 증명한 뒤 즉시 원본으로 복원한다.
#  ⚠⚠ [라운드625] 이전 버전은 이 무력화를 실제 app.py 파일에
#    io.open(...,"w").write() 로 디스크에 썼다가 subprocess 로 재현하고
#    finally 에서 복원하는 방식이었다 — 이 세션이 세운 "안전한 인메모리
#    기법"으로 옮긴다. 각도1(_photo_visible_to)은 다른 함수(사진 서빙
#    라우트)가 맨이름으로 부르는 평범한 모듈함수라 기법3(A.__dict__ 에
#    직접 exec), 각도2(api_admin_delete)는 Flask 라우트라 기법1
#    (view_functions 딕셔너리 스왑)을 쓴다 — 이미 위에서 열어 둔 A·DB·
#    ins2·mkadmin·admin_client·super_count·force_exactly_two_supers 를
#    그대로 재사용해 서브프로세스·임시DB 재부팅 없이 이 프로세스 안에서
#    끝낸다(더 빠르고, 디스크를 전혀 안 건드려 결과 오염 가능성 자체가 없다).
NEEDLE_1 = 'if session.get("insurer_id") and c["insurer_id"] == session["insurer_id"]:\n        return True'
BROKEN_1 = 'if session.get("insurer_id"):\n        return True   # [R435 임시무력화]'
NEEDLE_2 = ('    if a["role"] == "최고관리자":\n'
            '        n_super = conn.execute("SELECT COUNT(*) n FROM admins WHERE role=\'최고관리자\'").fetchone()["n"]\n'
            '        if n_super <= 1:\n'
            '            conn.rollback(); conn.close()\n'
            '            return jsonify({"ok": False, "error": "마지막 최고관리자는 삭제할 수 없습니다."}), 409\n')
BROKEN_2 = ''


def _py_fn_body(src, fn_name):
    """함수 본문 텍스트 — 다음 def뿐 아니라 다음 라우트의 @app. 데코레이터가
    먼저 나오면 거기서 자른다(round610/624 정착 기법)."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


try:
    # ── 각도1: _photo_visible_to() — 기법3(맨이름 호출, A.__dict__ 직접 exec) ──
    pvt_body = _py_fn_body(APP_SRC, "_photo_visible_to")
    chk(pvt_body.count(NEEDLE_1) == 1,
        "  (준비) 각도1 무력화 대상 지점이 _photo_visible_to() 안에 유일하게 있다")
    broken_pvt = pvt_body.replace(NEEDLE_1, BROKEN_1)
    assert broken_pvt != pvt_body, "각도1 치환이 실제로 안 먹었다"

    _orig_pvt = A._photo_visible_to
    exec(compile(broken_pvt, "<round435_broken_photo_visible_to>", "exec"), A.__dict__)  # noqa: S102 -- 실소스 그대로 추출, 디스크 미기록
    chk(A._photo_visible_to is not _orig_pvt, "  (준비) A._photo_visible_to가 실제로 바뀌었다")
    try:
        r_broken1 = ins2.get(f"/api/photos/{photo_a}/file")
        chk(r_broken1.status_code == 200,
            "★★★★★ 각도1 무력화 시 타 보험사가 실제로 200(유출)을 받는다"
            "(이 테스트의 [1]번 검사가 이 상태를 잡아낼 수 있다는 증명)", r_broken1.status_code)
    finally:
        A._photo_visible_to = _orig_pvt
    chk(A._photo_visible_to is _orig_pvt, "  (복원) A._photo_visible_to가 원래 함수객체로 복원됐다")
    r_restored1 = ins2.get(f"/api/photos/{photo_a}/file")
    chk(r_restored1.status_code in (401, 403, 404),
        "  복원 후 재확인 — 타 보험사는 다시 차단된다(바꿔치기가 안 샘)", r_restored1.status_code)

    # ── 각도2: api_admin_delete() — 기법1(Flask 라우트, view_functions 스왑) ──
    admdel_body = _py_fn_body(APP_SRC, "api_admin_delete")
    chk(admdel_body.count(NEEDLE_2) == 1,
        "  (준비) 각도2 무력화 대상 지점이 api_admin_delete() 안에 유일하게 있다")
    broken_admdel = admdel_body.replace(NEEDLE_2, BROKEN_2)
    assert broken_admdel != admdel_body, "각도2 치환이 실제로 안 먹었다"
    #  ⚠ 순수 인프로세스 스레드는 이 함수가 너무 빨라(추가 쿼리가 없어진
    #    무력화판이라 더더욱) 승자 스레드가 커밋까지 통째로 끝난 뒤에야
    #    패자 스레드가 시작되기 쉽다 — 그러면 require_role의 _account_alive()가
    #    "내 계정이 이미 지워졌다"며 401을 내 NEEDLE_2 자체를 아예 못 밟고
    #    지나간다(실측: 이 지연 없이 첫 시도에서 {'e_del_f':200,'f_del_e':401}로
    #    허위 통과할 뻔했다). round494의 지연 프로브와 같은 목적으로, 승자가
    #    잠금을 잡은 채 잠깐 머물게 해 패자의 _account_alive() 선확인이 그
    #    사이에 반드시 끝나게(=자기 계정이 아직 살아있는 걸 보게) 만든다.
    broken_admdel = broken_admdel.replace(
        'conn.execute("BEGIN IMMEDIATE")\n',
        'conn.execute("BEGIN IMMEDIATE")\n    import time as _r435_time; _r435_time.sleep(0.3)\n',
        1)

    _ns = dict(vars(A))
    exec(compile(broken_admdel, "<round435_broken_api_admin_delete>", "exec"), _ns)  # noqa: S102 -- 실소스 그대로 추출, 디스크 미기록
    broken_view = A.require_role("최고관리자")(_ns["api_admin_delete"])

    race_e = mkadmin("r435_race_e", "최고관리자")
    race_f = mkadmin("r435_race_f", "최고관리자")
    _orig_view = A.app.view_functions["api_admin_delete"]
    A.app.view_functions["api_admin_delete"] = broken_view
    try:
        force_exactly_two_supers(race_e, race_f)
        chk(super_count() == 2, "  (무력화, 사전조건) 최고관리자 정확히 2명", super_count())
        ce, he = admin_client("r435_race_e", "최고관리자")
        cf, hf = admin_client("r435_race_f", "최고관리자")
        results2, errs2 = {}, []

        def worker2(key, client, hdr, target_id):
            try:
                r = client.delete(f"/api/admins/{target_id}", headers=hdr)
                results2[key] = r.status_code
            except Exception as e:                                  # noqa: BLE001
                errs2.append((key, e))

        t3 = threading.Thread(target=worker2, args=("e_del_f", ce, he, race_f))
        t4 = threading.Thread(target=worker2, args=("f_del_e", cf, hf, race_e))
        t3.start(); t4.start(); t3.join(15); t4.join(15)
        chk(not errs2, "  무력화 동시실행 중 예외 없음", errs2)
        chk(super_count() == 0,
            "★★★★★★★★★★ 각도2 무력화 시 최고관리자가 실제로 0명(완전 락아웃)까지 떨어진다"
            "(이 테스트의 [6]번 검사가 이 상태를 잡아낼 수 있다는 증명)",
            (results2, super_count()))
    finally:
        A.app.view_functions["api_admin_delete"] = _orig_view
    chk(A.app.view_functions["api_admin_delete"] is _orig_view,
        "  (복원) api_admin_delete 라우트가 원래 함수객체로 복원됐다")

    # 복원 후 재확인 — 같은 레이스를 다시 걸어도 최소 1명은 남는지(바꿔치기 안 샘)
    race_g = mkadmin("r435_race_g", "최고관리자")
    race_h = mkadmin("r435_race_h", "최고관리자")
    force_exactly_two_supers(race_g, race_h)
    cg, hg = admin_client("r435_race_g", "최고관리자")
    ch, hh = admin_client("r435_race_h", "최고관리자")
    results3 = {}

    def worker3(key, client, hdr, target_id):
        r = client.delete(f"/api/admins/{target_id}", headers=hdr)
        results3[key] = r.status_code

    t5 = threading.Thread(target=worker3, args=("g_del_h", cg, hg, race_h))
    t6 = threading.Thread(target=worker3, args=("h_del_g", ch, hh, race_g))
    t5.start(); t6.start(); t5.join(15); t6.join(15)
    chk(super_count() >= 1,
        "  복원 후 재확인 — 같은 레이스를 다시 걸어도 최고관리자가 0명이 되지 않는다"
        "(바꿔치기가 안 샘)", (results3, super_count()))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 탐지력 증명 실행", f"{type(e).__name__} {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py는 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
