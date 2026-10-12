# -*- coding: utf-8 -*-
"""스캔 623라운드 회귀 — 캠페인 대상선정(_campaign_recipients, app.py:10076-)의
   major(업종) 검색이 공용 헬퍼 _kw_like_clause()(app.py:1688-)를 안 쓰고 손으로
   LIKE 절을 다시 짜서, 그 헬퍼가 이미 막아 둔 가운뎃점 표기 사각지대를 이 화면
   에서만 다시 겪던 결함.

   round499(다른 표기 사각지대 — dispatch.py candidates())·_kw_like_clause 의
   자기 docstring이 증언하는 실측: 정부 공식 업종 표기('ㆍ' U+318D 아래아, 예:
   "금속ㆍ창호ㆍ지붕ㆍ건축물조립공사업")를 쓰는 실제 협력사가 10곳(id 305~314)
   있는데, 운영자가 흔히 쓰는 '·'(U+00B7)로 검색하면 0건이 나온다 — 결과가
   0건이라 검색이 잘 된 줄 알고 넘어가게 된다. _kw_like_clause 는 이미 이걸
   막아서 name/region/major 조합 검색(app.py:9795·20785 등 7곳)에 전부 쓰이는데,
   `_campaign_recipients()`(마케팅 캠페인 — 문자/알림톡/메일 발송 대상 산출,
   app.py:10102-10109)만 `major LIKE ? ESCAPE '\\\\'` 를 손으로 다시 짜 이
   정규화를 못 받았다 — 코드 자신의 주석("이 파일의 다른 LIKE 검색은 전부 이
   이스케이프를 거친다 — 여기만 예외였다", app.py:10099-10101)이 이 사각지대를
   이미 알고 있었지만 부분적으로만(이스케이프만) 고쳐져 있었다.

   영향: 운영자가 이 10곳을 캠페인 대상으로 좁혀 찾으려 하면(예: major="금속·
   창호") 조용히 0곳이 나와, 있는 대상을 없는 것으로 오판하고 캠페인에서
   빠뜨리게 된다.

   고침: round607 의 _s() 방어(숫자 major 를 보내도 500 대신 안전 처리)는
   그대로 둔 채, 손으로 짠 LIKE 절을 같은 컬럼 조합에 이미 쓰이는 공용
   헬퍼 `_kw_like_clause(_s(f.get("major")), ["major"])` 호출로 교체한다 —
   새 로직 없이 기존 헬퍼 재사용, 트레이드오프 없는 "그냥 고치면 되는 것".

   ⚠ 이 라운드 자신이 신설한 회귀라, round433/434/443(레거시 온디스크
     되돌리기를 안전기법으로 이관하는 작업)과 달리 처음부터 안전기법으로
     쓴다 — app.py 파일은 이 테스트 실행 내내 디스크에 다시 쓰이지 않고,
     서브프로세스도 전혀 안 쓴다. `_campaign_recipients()`는 라우트가 아니라
     평범한 모듈함수라 view_functions 스왑조차 필요 없다 — ast로 현재 본문을
     뽑아 옛 LIKE 절로 치환한 뒤 독립 사본 네임스페이스에 exec, 그 사본의
     함수를 새 코드와 나란히 직접 호출해 비교한다(기법2, round491/499 계열).

       python test_scan_round623_fixes.py
"""
import ast
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


def _ast_fn_src(src, fn_name):
    """ast로 함수의 정확한 경계(decorator 제외, def~마지막 줄)를 뽑는다.
    (round499가 확립한 헬퍼)"""
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            return "".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError(f"함수 {fn_name} 을 못 찾음")


APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

print("=" * 72)
print("  스캔 623라운드 회귀 — 캠페인 major 검색 가운뎃점 표기 사각지대")
print("=" * 72)

print("\n[1] 소스 확인")
FN_BODY = _ast_fn_src(APP_SRC, "_campaign_recipients")
chk('_kw_like_clause(_s(f.get("major")), ["major"])' in FN_BODY,
    "★★★★★ _campaign_recipients() 가 이제 공용 헬퍼 _kw_like_clause 를 쓴다")
chk('where.append("major LIKE ? ESCAPE' not in FN_BODY,
    "  손으로 짠 옛 LIKE 절이 더는 없다")

print("\n[2] 실행 준비 — 스크래치 DB")
_tmpdir = tempfile.mkdtemp(prefix="round623_")
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
    #  실측(round499/_kw_like_clause docstring)과 같은 패턴 — 정부 공식 업종
    #  표기(ㆍ U+318D)를 쓰는 실제 협력사를 재현.
    p_official = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,major,region,"
        "                     phone,email,sms_consent,email_consent,created_at) "
        "VALUES('R623금속창호','시공사','활성','철거','금속ㆍ창호ㆍ지붕ㆍ건축물조립공사업','서울',"
        "       '010-1111-2222','r623a@example.com',1,1,?)", (DB.now(),)).lastrowid
    #  대조군 — 가운뎃점이 전혀 없는 보통 업종 표기(회귀 없음 확인용).
    p_normal = conn.execute(
        "INSERT INTO partners(name,partner_type,status,category,major,region,"
        "                     phone,email,sms_consent,email_consent,created_at) "
        "VALUES('R623도장','시공사','활성','도장','도장공사업','서울',"
        "       '010-3333-4444','r623b@example.com',1,1,?)", (DB.now(),)).lastrowid
    conn.commit()

    print("\n[3] 실행 — 새 코드: 흔한 '·'(U+00B7)로 검색해도 공식표기 업체를 찾는다")
    ok1, nc1, opt1, ncon1 = A._campaign_recipients(conn, {"major": "금속·창호"})
    ids1 = {r["id"] for r in ok1}
    chk(p_official in ids1,
        "★★★★★ major='금속·창호'(흔한 가운뎃점) 검색이 공식표기('ㆍ') 업체를 "
        "찾아낸다(고치기 전엔 0건이었다)", (ids1, nc1, opt1, ncon1))
    chk(p_normal not in ids1,
        "  무관한 대조군(도장업체)은 안 딸려온다(과잉매칭 아님)", ids1)

    ok2, *_ = A._campaign_recipients(conn, {"major": "도장"})
    ids2 = {r["id"] for r in ok2}
    chk(p_normal in ids2 and p_official not in ids2,
        "  일반 검색('도장')은 여전히 정확히 그 업체만 찾는다(회귀 없음)", ids2)

    print("\n[4] 실행 — round607 방어(숫자 major)가 여전히 안전하다")
    try:
        ok3, *_ = A._campaign_recipients(conn, {"major": 12345})
        chk(True, "  major 에 숫자를 보내도 500 대신 안전하게 처리된다"
            "(round607 방어 유지)", len(ok3))
    except Exception as e:                                          # noqa: BLE001
        chk(False, "  major 에 숫자를 보내면 안전하게 처리돼야 한다", f"{type(e).__name__}: {e}")

    # ============================================================
    print("\n[5] 되돌리기 — 옛 코드였다면 결함이 재현되는가"
          " (독립 사본 네임스페이스에 exec, 디스크 미기록·서브프로세스 미사용)")
    # ------------------------------------------------------------
    NEW_BLOCK = ('    if f.get("major"):\n'
                 '        clause, kw_p = _kw_like_clause(_s(f.get("major")), ["major"])\n'
                 '        where.append(clause)\n'
                 '        params.extend(kw_p)\n')
    OLD_BLOCK = ('    if f.get("major"):\n'
                 '        where.append("major LIKE ? ESCAPE \'\\\\\'")\n'
                 '        params.append(f"%{_like_escape(_s(f.get(\'major\')))}%")\n')
    chk(FN_BODY.count(NEW_BLOCK) == 1, "  (준비) 되돌리기 대상이 함수 본문 안에 유일하게 있다")
    REVERTED_BODY = FN_BODY.replace(NEW_BLOCK, OLD_BLOCK)
    chk(REVERTED_BODY != FN_BODY, "  (준비) 되돌린 함수 본문이 실제로 달라졌다")

    _ns = dict(vars(A))
    exec(compile(REVERTED_BODY, "<round623_reverted__campaign_recipients>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_campaign_recipients = _ns["_campaign_recipients"]

    old_ok1, *_ = old_campaign_recipients(conn, {"major": "금속·창호"})
    old_ids1 = {r["id"] for r in old_ok1}
    chk(p_official not in old_ids1,
        "★★★★★ 옛 코드(사본): major='금속·창호' 검색이 공식표기 업체를 "
        "못 찾는다(실제로 0건, 인과관계 직접증명)", old_ids1)

    old_ok2, *_ = old_campaign_recipients(conn, {"major": "도장"})
    old_ids2 = {r["id"] for r in old_ok2}
    chk(p_normal in old_ids2,
        "  옛 코드(사본)도 가운뎃점이 없는 보통 검색은 원래부터 문제없이 찾는다"
        "(이 결함이 major 검색 전체가 아니라 표기 사각지대만의 문제임을 확인)",
        old_ids2)

    #  새 코드(A 모듈의 실제 함수)가 옛 코드 exec로 인해 어떤 영향도 안 받았는지 확인
    ok_after, *_ = A._campaign_recipients(conn, {"major": "금속·창호"})
    chk(p_official in {r["id"] for r in ok_after},
        "  새 코드(A._campaign_recipients, 원본)는 사본 exec와 무관하게 "
        "여전히 정상 동작한다(스와핑 없이 사본만 만들었으므로 당연하지만 확인)",
        {r["id"] for r in ok_after})

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행/되돌리기", f"{type(e).__name__} {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(독립 사본 네임스페이스 exec만 사용 — 디스크에 쓴 적도, 서브프로세스를 띄운 적도 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
