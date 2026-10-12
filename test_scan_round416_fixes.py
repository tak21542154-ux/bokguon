# -*- coding: utf-8 -*-
"""스캔 416라운드 회귀 — 사건 등록 3개 경로(관리자 콘솔 api_case_create, 보험사
   포털·v1 API 공용 _create_case/_normalize_categories) 전부 서버가 이미 갖고
   있는 정본 공종 목록(WORK_MAJORS, app.py:14653)을 값 검증에 안 써서, 브라우저
   화면(닫힌 드롭다운)을 거치지 않은 요청이면 임의 문자열을 공종으로 그대로
   저장할 수 있던 결함(정밀조사 Agent 발견 — 각도2: 클라측만 검증). 그 사건은
   표준단가·공종별 매칭에서 조용히 0건 처리되는 데이터 무결성 문제로 이어진다.
   같은 라운드에서 관리자 경로만 지역(region)의 낱자모 오염 필터
   (_has_bare_jamo, 형제 _create_case는 이미 적용 중)도 빠져 있던 걸 발견해
   같이 고쳤다.

   고치는 과정에서 직접 찾아낸 2차 함정: _idem_fingerprint(d) 도 내부에서
   _normalize_categories() 를 부르는데, 그 호출이 두 곳(api_insurer_case_
   create·api_v1_case_create)에서 전부 기존 try/except CaseInputError **밖**에
   있었다 — 그대로 뒀다면 잘못된 공종으로 같은 idem_key 를 재사용하는 요청이
   깔끔한 400 대신 처리되지 않은 예외(500)로 죽고 트랜잭션도 못 닫혔을 것.
   두 함수 모두 BEGIN IMMEDIATE 직후부터 try 를 넓혀 같은 except 가 잡게
   고쳤다.

   기존 테스트 5개(라운드68·141·198·227 + insurer_api_guide.html 예시를
   그대로 쏘는 라운드226)가 전부 축약형 공종("가드레일" 등, 정본은
   "가드레일·방호울타리")을 우연히 쓰고 있어 이 검증이 켜지면 깨졌다 —
   그 값들의 정확한 정체는 각 테스트의 실제 검증 대상과 무관해(라운드227은
   멱등키 지문불일치 검사, 라운드68은 접수번호 레이스, 라운드141은 하위계정
   구분, 라운드198은 재시도 안전장치 검증) 전부 정본 이름으로 갱신했다
   (라운드412·414의 "구식 가정 갱신" 판단기준과 동일 — 신규 검증이 그 테스트가
   실제로 확인하려는 바를 바꾸지 않았다).

       python test_scan_round416_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(HERE, "app.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 416라운드 회귀 — 사건 등록 3경로 공종 화이트리스트 부재")
print("  + 관리자 경로 지역 낱자모 필터 부재 + idem_fingerprint try밖 노출")
print("=" * 72)

print("\n[1] 소스 확인")


def body_of(fn_name):
    i0 = APP_SRC.index(f"def {fn_name}(")
    i1 = APP_SRC.index("\ndef ", i0 + 1)
    return APP_SRC[i0:i1]


chk("bad = [c for c in uniq if c not in WORK_MAJORS]" in body_of("_normalize_categories"),
    "★★★★★ _normalize_categories() 가 WORK_MAJORS 화이트리스트를 대조한다")
chk('if d["category"] not in WORK_MAJORS:' in body_of("api_case_create"),
    "★★★★★ api_case_create() 도 같은 화이트리스트를 대조한다")
chk("_has_bare_jamo(_region_in)" in body_of("api_case_create"),
    "★★★★ api_case_create() 가 형제(_create_case)와 같은 지역 낱자모 필터를 쓴다")

_iic_body = APP_SRC[APP_SRC.index("def api_insurer_case_create"):
                     APP_SRC.index("\ndef ", APP_SRC.index("def api_insurer_case_create") + 1)]
chk(_iic_body.index("try:") < _iic_body.index("if key:") < _iic_body.index("except CaseInputError"),
    "★★★★★ api_insurer_case_create() 의 try 가 idem_key 중복확인 블록까지 감싼다"
    "(_idem_fingerprint 의 CaseInputError 가 새지 않는다)")
_v1_body = APP_SRC[APP_SRC.index("def api_v1_case_create"):
                    APP_SRC.index("\ndef ", APP_SRC.index("def api_v1_case_create") + 1)]
chk(_v1_body.index("try:") < _v1_body.index("if key:") < _v1_body.index("except CaseInputError"),
    "★★★★★ api_v1_case_create() 도 마찬가지로 try 가 넓혀졌다")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round416_")
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
    conn.execute("INSERT INTO insurers(name,status) VALUES('R416보험사','활성')")
    insurer_id = conn.execute("SELECT id FROM insurers WHERE name='R416보험사'").fetchone()["id"]
    conn.execute("INSERT INTO admins(username,password_hash,name,role,created_at) "
                 "VALUES('r416adm', ?, 'R416관리자', '중간관리자', ?)",
                 (DB.hash_pw("R416Adm!2468"), DB.now()))
    RAW_KEY = "bok_live_r416testkey0000000000000000000000000"
    conn.execute(
        "INSERT INTO insurers(name,status,api_enabled,api_key_hash,login_id,password_hash) "
        "VALUES('R416API보험사','활성',1,?,'r416api','x')", (A._hash_api_key(RAW_KEY),))
    conn.commit()

    def _admin_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["admin"] = "r416adm"; sess["admin_role"] = "중간관리자"
            sess["pw_role"] = "admin"; sess["_csrf"] = "r416-csrf"
        return c

    def _insurer_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["insurer_id"] = insurer_id; sess["insurer_login"] = "r416insurer"
            sess["insurer_name"] = "R416보험사"; sess["_csrf"] = "r416-csrf"
        return c

    print("\n[3] 실행 — 관리자 콘솔(api_case_create): 공종 화이트리스트 + 지역 필터")
    c1 = _admin_client()
    r_bad = c1.post("/api/cases", json={
        "case_no": "R416-ADM-BAD", "category": "완전히없는공종", "insurer_id": insurer_id,
        "est_price": "1000000"}, headers={"X-CSRF-Token": "r416-csrf"})
    chk(r_bad.status_code == 400, "★★★★★ 없는 공종은 400으로 거부된다"
        "(고치기 전엔 그대로 저장됐다)", (r_bad.status_code, r_bad.get_json()))

    c2 = _admin_client()
    r_ok = c2.post("/api/cases", json={
        "case_no": "R416-ADM-OK", "category": "가드레일·방호울타리", "insurer_id": insurer_id,
        "est_price": "1000000", "region": "ㅇㄴㅁㄹ서울"}, headers={"X-CSRF-Token": "r416-csrf"})
    chk(r_ok.status_code == 200, "  정상 공종은 그대로 등록된다(회귀없음)",
        (r_ok.status_code, r_ok.get_json()))
    row = conn.execute("SELECT region FROM cases WHERE case_no='R416-ADM-OK'").fetchone()
    chk(row["region"] == "",
        "★★★★ 낱자모 섞인 지역값은 형제(_create_case)처럼 빈 값으로 접힌다"
        "(고치기 전엔 그대로 저장됐다)", row["region"])

    print("\n[4] 실행 — 보험사 포털(_create_case): 공종 화이트리스트")
    c3 = _insurer_client()
    r_ibad = c3.post("/api/insurer/cases", json={"category": "완전히없는공종", "no_photo": True},
                      headers={"X-CSRF-Token": "r416-csrf"})
    chk(r_ibad.status_code == 400, "★★★★★ 포털 경로도 없는 공종은 400으로 거부된다",
        (r_ibad.status_code, r_ibad.get_json()))

    print("\n[5] 실행 — v1 API(_create_case): 공종 화이트리스트 + idem 재사용 시 500 아닌 400")
    api_client = A.app.test_client()
    hdr = {"X-API-Key": RAW_KEY}
    KEY = "r416-idem-key"
    r1 = api_client.post("/api/v1/cases", headers={**hdr, "Idempotency-Key": KEY},
                          json={"category": "유리·샷시·자동문", "address": "서울", "est_price": "500000"})
    chk(r1.status_code == 201, "  정상 공종의 첫 요청은 201로 접수된다(회귀없음)",
        (r1.status_code, r1.get_json()))

    #  ★ 핵심 — 같은 idem_key 를 "잘못된 공종"으로 재사용. _idem_fingerprint(d) 가
    #    _normalize_categories() 를 거치며 CaseInputError 를 던지는 지점이라,
    #    try 를 안 넓혔으면 여기서 500(처리되지 않은 예외)이 났을 자리다.
    r2 = api_client.post("/api/v1/cases", headers={**hdr, "Idempotency-Key": KEY},
                          json={"category": "완전히없는공종", "address": "서울", "est_price": "500000"})
    chk(r2.status_code == 400,
        "★★★★★ 같은 열쇠를 잘못된 공종으로 재사용해도 500이 아니라 깔끔한 400"
        "(try 를 안 넓혔으면 여기서 처리되지 않은 예외로 죽었을 자리)",
        (r2.status_code, r2.get_data(as_text=True)[:300]))

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[6] 되돌리기 — 옛 코드로 되돌리면 재현되는가(디스크 미기록)")
# ------------------------------------------------------------
#  ⚠⚠ [라운드613] round409~515대 옛 세대 기법(되돌린 전체 app.py 를 실제
#    APP_PATH 에 잠깐 써넣고 서브프로세스로 재현한 뒤 원본을 복원 — 그
#    write→subprocess→write 사이의 창을 다른 세션이 관측하면 충돌한다,
#    round590이 실제로 겪음)을 round411·610이 확립한 안전패턴으로 이관.
#    _normalize_categories() 는 라우트가 아니라 _create_case()·
#    api_case_create() 가 맨이름(bare name)으로 부르는 평범한 모듈함수라,
#    그 호출부들(사본이 아니라 실제 로드된 A 모듈 그대로 유지)의 전역조회가
#    되돌린 버전을 보게 하려면 사본 네임스페이스가 아니라 **A.__dict__
#    자체**(A모듈의 진짜 전역이자 _create_case.__globals__ 와 동일 객체)에
#    임시로 걸어야 한다 — 진짜 app.py 파일은 전혀 안 건드리고, finally 에서
#    원래 함수 객체로 되돌린다.
OLD_NORM = '''def _normalize_categories(d):
    """단일 category 또는 여러 categories[] 를 정규화한다."""
    cats = d.get("categories")
    if isinstance(cats, list):
        out = [_s(c) for c in cats if _s(c)]
    else:
        one_cat = _s(d.get("category"))
        out = [one_cat] if one_cat else []
    # 중복 제거(입력 순서 유지)
    seen, uniq = set(), []
    for c in out:
        if c not in seen:
            seen.add(c); uniq.append(c[:60])
    return uniq[:8]     # 한 사건에 공종 8개까지'''

try:
    _norm_body = body_of("_normalize_categories")
    chk(APP_SRC.count(_norm_body) == 1,
        "  (준비) _normalize_categories() 본문이 파일에서 유일하게 식별된다")
    chk(OLD_NORM != _norm_body, "  (준비) 되돌리기 텍스트가 실제로 달라졌다")

    conn = DB.get_db()   # [3]~[5]가 이미 닫은 conn 대신 같은 스크래치 DB에 새로 연결
    _orig_norm = A._normalize_categories
    exec(compile(OLD_NORM, "<round416_old_normalize_categories>", "exec"), A.__dict__)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    chk(A._normalize_categories is not _orig_norm,
        "  (준비) A._normalize_categories 가 실제로 옛 버전 함수객체로 바뀌었다")
    try:
        r_revert = _insurer_client().post(
            "/api/insurer/cases", json={"category": "완전히없는공종", "no_photo": True},
            headers={"X-CSRF-Token": "r416-csrf"})
        chk(r_revert.status_code == 200,
            "★★★★★ 옛 코드는 없는 공종도 200으로 받아준다(인과관계 직접증명)",
            (r_revert.status_code, r_revert.get_json()))
        row_revert = conn.execute(
            "SELECT category FROM cases WHERE insurer_id=? AND category=?",
            (insurer_id, "완전히없는공종")).fetchone()
        chk(row_revert is not None and row_revert["category"] == "완전히없는공종",
            "★★★★★ 옛 코드는 그 값을 그대로 DB에 저장한다(인과관계 직접증명)",
            dict(row_revert) if row_revert else None)
    finally:
        A._normalize_categories = _orig_norm

    #  원복 확인 — 복원 후엔 같은 종류 요청이 다시 400으로 막힌다(바꿔치기가 안 샘)
    r_after = _insurer_client().post(
        "/api/insurer/cases", json={"category": "완전히없는공종2", "no_photo": True},
        headers={"X-CSRF-Token": "r416-csrf"})
    chk(r_after.status_code == 400,
        "★★★★ 원복 후에는 같은 종류 요청이 다시 400으로 막힌다(바꿔치기가 안 샜다)",
        (r_after.status_code, r_after.get_json()))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
