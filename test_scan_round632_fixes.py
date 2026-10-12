# -*- coding: utf-8 -*-
"""스캔 632라운드 회귀 — 복합공종 사건의 category 문자열이 제출 순서에 따라
달라져, compliance.related_sum() 의 분할회피(쪼개기) 탐지가 **같은 트레이드
집합을 가진 관련 건을 놓치던** 결함(직접조사, 하위위임 없음).

배경 — compliance.py 는 이 사업의 형사리스크 방어선이다(무등록 건설업,
5년 이하 징역 또는 5천만원 이하 벌금). related_sum() 은 "같은 보험사·같은
공종·같은 지역·최근 30일"인 관련 건을 합산해 쪼개기(대법원 2018도3821)를
잡는데, "같은 공종" 판정은 두 사건이 **둘 다 아직 work_lots 로 안 쪼개졌을
때**(2트랙 사진없는 접수 등 상시 상태, compliance.py 289행 주석) cases.category
문자열의 완전일치로 폴백한다(라운드122). 이 폴백이 왜 문자열을 그대로 쓰는가 —
구분자 ' · ' 가 '유리·샷시·자동문'류 트레이드 이름 내부의 '·'와 헷갈려 잘못
쪼갤 위험이 있어(compliance.py/dispatch.py _case_trades()·app.py case_trades()
세 곳 모두 문서화, 라운드122/round의 반복 경고), 파싱 대신 문자열 자체를
정본으로 삼기로 한 의도적 선택이다.

그런데 이 문자열을 만드는 **유일한 지점**(app.py _create_case, grep으로
재확인 — 이후 어떤 라우트도 cases.category 를 다시 쓰지 않는다)이 그 문자열을
_normalize_categories() 가 "입력 순서 유지"로 돌려준 cats 그대로 이어붙였다
(f"복합({{' · '.join(cats)}})"). 보험사 포털·v1 API 는 categories[] 배열을
호출자가 원하는 순서로 보낼 수 있으므로, **같은 트레이드 집합**이 두 번
다른 순서로 접수되면(체크박스 클릭 순서 차이, 서로 다른 담당자 등 — 공격이
아니라 흔한 우연으로도 발생) category 문자열이 서로 달라지고, related_sum()
의 완전일치 폴백이 두 사건을 "다른 공종"으로 오판해 합산을 건너뛴다.
이 파일 자신의 상단 선언("당사자·동일유형·반복수주가 이 판단에 가장
취약하다")과 "애매하면 합산 쪽으로 기운다"(라운드196이 region 에 이미 적용한
원칙)에 정면으로 어긋난다 — region 쪽만 순서·표기 흔들림에 관대하고 trade
쪽은 순서 하나로 탐지가 통째로 빠진다.

실측(직접 실행, 되돌리기 전) — 같은 두 트레이드(유리·샷시·자동문 · 조경·수목)를
순서만 바꿔 두 번 접수하면 related_sum() 이 서로를 관련건으로 못 보고 0원을
돌려준다. 세 번째로 첫 번째와 **완전히 같은 순서**로 또 접수하면 그 사건은
첫 번째와만 묶이고 두 번째와는 여전히 안 묶인다 — 트레이드 집합이 전부
동일한 세 사건이 문자열 순서라는 우연 때문에 서로 다른 두 그룹으로 조용히
쪼개진다.

고침 — 트레이드 이름을 파싱하는 대신(파싱 자체가 세 _case_trades() 모두가
피하는 위험이다), **유일한 생성 지점**에서 cats 를 정렬해 같은 집합이면
항상 같은 문자열이 나오게 한다(app.py _create_case, cats → sorted(cats)).
_idem_fingerprint()(라운드227 근처, 4292행)가 같은 종류의 문제(제출 순서
차이로 지문이 갈라짐)를 이미 sorted() 로 풀어 둔 것과 동일한 처방이다.
rule_for() 의 복합판정(라운드315, 토큰을 집합으로 재귀판정)은 이미 순서
무관이라 영향 없음(회귀없음 재확인).

검증
  [1] 소스 확인 — _create_case() 안에 join(sorted(cats)) 가 정확히 1번 있다
      (되돌리기에 쓸 지점을 특정할 수 있다).
  [2]~[3] 실행 — 실제 Flask 앱(스크래치 DB) + 실제 v1 API 라우트(POST
      /api/v1/cases, X-API-Key 인증, no_photo:true — _create_case() 는
      work_lots 를 **사진있는 정상경로에서만** 채우고 no_photo 분기는 그
      INSERT 루프 전에 먼저 return 한다, 직접 Read 로 확인·아래 [4]에서
      이 플래그 없이 먼저 시도해 결함이 안 보임을 실측 확인했었다)로 같은
      두 트레이드를 순서만 바꿔 두 번 접수 → (a) 저장된 cases.category
      문자열이 이제 동일함 (b) 실제 compliance.related_sum() 이 서로를
      관련건으로 정확히 합산함 (c) 단일 공종·동일순서 재접수는 기존과
      동일하게 동작함(회귀없음).
  [4]~[5] 되돌리기-증명 — _create_case() 안의 sorted(cats) 토큰 하나만 옛
      코드(cats)로 되돌린 사본을 exec 로 격리 재구성해(round414·610·615·631이
      확립한 안전패턴 그대로 — 이름바꾸기+모듈 속성 직접치환, 실제 파일 미변경)
      옛 코드가 실제로 (a) 순서가 다르면 다른 문자열을 만들고 (b) related_sum()
      합산을 놓치는지를 실행으로 재현한 뒤 finally 에서 원복.
  [6] 원복 확인 — 되돌리기 이후 다시 방어되는가(바꿔치기가 안 샜다).

    python test_scan_round632_fixes.py
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


def _py_fn_body(src, fn_name):
    """함수 본문 — 다음 def뿐 아니라 다음 라우트의 @app. 데코레이터가 먼저
    나오면 거기서 자른다(round610 정착 기법)."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 632라운드 회귀 — 복합공종 category 순서의존이 분할회피탐지를 놓침")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
NEW_SNIPPET = "join(sorted(cats))"
OLD_SNIPPET = "join(cats)"

body_cc = _py_fn_body(APP_SRC, "_create_case")
chk(NEW_SNIPPET in body_cc, "★★★★★ _create_case()가 cats를 정렬한 뒤 이어붙인다")
chk(body_cc.count(NEW_SNIPPET) == 1,
    "  되돌리기-증명에 쓸 지점이 정확히 1번만 있다(특정 가능)")
chk(APP_SRC.count(NEW_SNIPPET) == 1,
    "  app.py 전체에서도 이 조합이 여기 1곳뿐이다(다른 생성 경로 없음)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 준비 — 스크래치 DB + 실제 Flask 앱 + v1 API 보험사")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round632_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "scratch.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A
    import compliance as CP

    #  ⚠ 되돌리기 절(아래 [4])은 **다른 보험사**를 쓴다 — related_sum() 은
    #    insurer_id 도 같아야 합산 대상으로 보므로, [3]에서 이미 "고쳐진 코드"로
    #    만들어 둔 사건들(사건집합이 같아 전부 같은 정렬문자열로 수렴한다 —
    #    그것 자체가 이 수정이 의도한 정상 동작이다)이 [4]의 "옛 코드" 비교를
    #    오염시키지 않게 한다(같은 보험사를 썼다면 [3]의 사건들이 우연히 섞여
    #    되돌린 코드조차 '합산됨'으로 잘못 보일 뻔했다 — 직접 실행해 확인).
    RAW_KEY = "bok_live_r632testkey0000000000000000000000000"
    RAW_KEY2 = "bok_live_r632testkey0000000000000000000000001"
    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,status,api_enabled,api_key_hash,login_id,password_hash) "
        "VALUES(?,?,1,?,?,?)",
        ("R632보험사", "활성", A._hash_api_key(RAW_KEY), "r632insurer", "x")).lastrowid
    iid2 = conn.execute(
        "INSERT INTO insurers(name,status,api_enabled,api_key_hash,login_id,password_hash) "
        "VALUES(?,?,1,?,?,?)",
        ("R632보험사B", "활성", A._hash_api_key(RAW_KEY2), "r632insurer2", "x")).lastrowid
    conn.commit()
    conn.close()

    client = A.app.test_client()
    hdr = {"X-API-Key": RAW_KEY}
    hdr2 = {"X-API-Key": RAW_KEY2}
    CAT_A, CAT_B = "유리·샷시·자동문", "조경·수목"     # 둘 다 WORK_MAJORS·WORK_RULES 정식 등재

    def _post_case(cats_order, amount, headers=None):
        #  ⚠ no_photo:true 로 보낸다 — _create_case() 는 work_lots 를 **사진있는
        #    정상경로에서만** 채운다(no_photo 분기는 4456행에서 그 INSERT 루프
        #    전에 먼저 return 한다, 직접 Read 로 확인). related_sum() 의 문자열
        #    폴백은 정확히 "둘 다 아직 work_lots 가 없을 때"만 타므로, 이 플래그
        #    없이 보내면(work_lots 가 즉시 채워짐) 이 결함의 실제 유입 경로를
        #    비켜가 되돌려도 차이가 안 보인다(직접 실행으로 먼저 확인·아래 참고).
        r = client.post("/api/v1/cases", headers=(headers or hdr),
                         json={"categories": cats_order, "region": "서울 송파구",
                               "address": "서울시 송파구 오금로", "est_price": str(amount),
                               "no_photo": True})
        return r

    def _category_of(cid):
        c = DB.get_db()
        row = c.execute("SELECT category FROM cases WHERE id=?", (cid,)).fetchone()
        c.close()
        return row["category"] if row else None

    # ══════════════════════════════════════════════════════════
    print("\n[3] 실행 — 현재(고쳐진) 코드: 같은 트레이드 집합, 순서만 다르게 접수")
    # ──────────────────────────────────────────────────────────
    r1 = _post_case([CAT_A, CAT_B], 7_000_000)
    r2 = _post_case([CAT_B, CAT_A], 7_000_000)
    chk(r1.status_code == 201 and r2.status_code == 201,
        "STEP 두 접수 모두 정상 처리된다(과잉차단 아님)",
        (r1.status_code, r2.status_code))
    id1, id2 = r1.get_json()["id"], r2.get_json()["id"]
    cat1, cat2 = _category_of(id1), _category_of(id2)
    chk(cat1 == cat2 and cat1 is not None,
        "★★★★★ 순서만 다르게 보내도 저장된 category 문자열이 이제 동일하다"
        "(수정 전엔 '복합(유리·샷시·자동문 · 조경·수목)' vs "
        "'복합(조경·수목 · 유리·샷시·자동문)'로 서로 달랐다)",
        (cat1, cat2))

    conn = DB.get_db()
    total_fixed, related_fixed = CP.related_sum(conn, id1)
    conn.close()
    related_ids_fixed = {r["id"] for r in related_fixed}
    chk(id2 in related_ids_fixed and total_fixed >= 7_000_000,
        "★★★★★ compliance.related_sum() 이 순서만 다른 관련 건을 실제로 "
        "합산한다(수정 전엔 0원 — 분할회피 탐지가 통째로 빠졌었다)",
        (total_fixed, related_ids_fixed))

    # 회귀없음 — 단일 공종(비복합)·완전히 같은 순서 재접수는 기존과 동일
    r_single = _post_case([CAT_A], 500_000)
    chk(r_single.status_code == 201 and _category_of(r_single.get_json()["id"]) == CAT_A,
        "  단일 공종 사건은 그대로 원문(정렬 대상 아님) — 회귀없음",
        _category_of(r_single.get_json()["id"]))
    r3 = _post_case([CAT_A, CAT_B], 7_000_000)     # 첫 번째와 완전히 같은 순서
    cat3 = _category_of(r3.get_json()["id"])
    chk(cat3 == cat1, "  완전히 같은 순서로 또 접수해도 여전히 같은 문자열(회귀없음)", (cat1, cat3))

    # ══════════════════════════════════════════════════════════
    print("\n[4] 되돌리기 — _create_case()만 옛 코드로(실제 파일은 안 건드림)")
    # ──────────────────────────────────────────────────────────
    _old_body = (body_cc
                 .replace("def _create_case(conn, iid, iname, d, source, actor_name=None):",
                          "def _create_case_pre632(conn, iid, iname, d, source, actor_name=None):", 1)
                 .replace(NEW_SNIPPET, OLD_SNIPPET, 1))
    chk(_old_body.count(OLD_SNIPPET) >= 1 and "_create_case_pre632" in _old_body
        and NEW_SNIPPET not in _old_body,
        "  (준비) 함수 리네임 + join(cats) 축소가 정확히 적용됐다(실제 파일 미변경)")

    _ns = dict(vars(A))
    exec(compile(_old_body, "<round632_pre632_create_case>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_fn = _ns["_create_case_pre632"]

    _orig_create_case = A._create_case
    A._create_case = old_fn
    try:
        rb1 = _post_case([CAT_A, CAT_B], 7_000_000, headers=hdr2)
        rb2 = _post_case([CAT_B, CAT_A], 7_000_000, headers=hdr2)
        chk(rb1.status_code == 201 and rb2.status_code == 201,
            "  옛 코드로도 두 접수 자체는 여전히 성공한다(비교 대상 확보)",
            (rb1.status_code, rb2.status_code))
        bid1, bid2 = rb1.get_json()["id"], rb2.get_json()["id"]
        bcat1, bcat2 = _category_of(bid1), _category_of(bid2)
        chk(bcat1 != bcat2,
            "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림)는 순서가 다르면 실제로 "
            "다른 category 문자열을 저장한다 — 이 테스트가 진짜 결함을 잡아낼 "
            "능력이 있음을 증명", (bcat1, bcat2))

        conn = DB.get_db()
        total_broken, related_broken = CP.related_sum(conn, bid1)
        conn.close()
        related_ids_broken = {r["id"] for r in related_broken}
        chk(bid2 not in related_ids_broken,
            "★★★★★ 옛 코드에서는 related_sum() 이 순서만 다른 관련 건을 놓친다"
            "(분할회피 탐지 공백을 실행으로 재현)",
            (total_broken, related_ids_broken))
    finally:
        A._create_case = _orig_create_case

    # ══════════════════════════════════════════════════════════
    print("\n[5] 원복 확인 — 되돌리기 이후 다시 방어되는가(바꿔치기가 안 샜다)")
    # ──────────────────────────────────────────────────────────
    chk(A._create_case is _orig_create_case, "  A._create_case가 원래 함수객체로 복원됐다")
    r4 = _post_case([CAT_A, CAT_B], 7_000_000)
    r5 = _post_case([CAT_B, CAT_A], 7_000_000)
    chk(r4.status_code == 201 and r5.status_code == 201, "  원복 후 접수 정상")
    cat4, cat5 = _category_of(r4.get_json()["id"]), _category_of(r5.get_json()["id"])
    chk(cat4 == cat5 == cat1,
        "★★★★ 원복 후에는 다시 순서 무관하게 같은 문자열을 저장한다(바꿔치기가 안 샜다)",
        (cat1, cat4, cat5))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__}: {e}")

APP_HASH_AFTER = read("app.py")
chk(APP_HASH_AFTER == APP_SRC,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(모듈 속성 직접치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
