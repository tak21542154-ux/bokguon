# -*- coding: utf-8 -*-
"""스캔 489라운드 회귀 — 주소검색(addr_search.search / /api/address/search)에
검색어 길이 하한(2자)만 있고 상한이 없던 결함. 로그인한 저신뢰 계정(협력사
포함)이 수만 자짜리 q 를 보내면 그대로 urllib.parse.quote() 를 거쳐 외부
(비공식 무인증 카카오 엔드포인트)로 그 크기 그대로 전달됐다(실측: 한글
5만자 → 450,076바이트 URL). 같은 성격의 자유입력(주소)은 이미
FIELD_LIMITS["address"]·_create_case() 양쪽 모두 200자로 자르는 관례가
있어, 그 200을 그대로 재사용해 상한을 걸었다.

두 지점을 고쳤다 — ①addr_search.search() 자신(실시간 라우트와
geocode_fill.py 배치 양쪽의 유일한 공용 관문) ②app.py 의 라우트 자신
(사용자에게 "결과 없음"이 아니라 "너무 깁니다"라는 원인 메시지를 보여주기
위한 사용자경험 계층, 보안 경계는 아님 — ①이 이미 막는다). 두 블록 모두
단일 삽입(사이에 원본코드가 끼어있지 않음)이라 라운드488과 달리 통짜
제거로 되돌릴 수 있다.

[라운드624] on-disk 되돌리기(두 파일에 직접 쓰고, 매번 새로 생성하는 전용
서브프로세스 워커 스크립트 test_scan_round489_worker.py로 재현)를 인메모리로
이관. ① addr_search.search()는 자신의 demo() 자가점검에서만 바레네임으로
불리고(그마저 __main__ 가드 안, import 시엔 실행 안 됨) 그 외엔 전부
`ADDR.search(...)` 형태로만 불려 실제로는 기법2에 가깝지만, app.py쪽에서도
같은 모듈 객체(`import addr_search as ADDR`)를 그대로 참조하므로 가장
안전한 길은 기법3 그대로 — exec()로 되돌린 본문을 addr_search 모듈의
진짜 __dict__ 에 직접 심어 `ADDR.search` 자체를 잠깐 갈아 끼우고, 저장해 둔
원래 함수객체로 복원한다. ② api_address_search()는 데코레이터가 아예 없는
(인증은 함수 안에서 _mixed_actor_guard() 로 처리) 단일 Flask 라우트라
view_functions 딕셔너리 항목만 스왑한다(기법1). 실제 파일은 전혀 안
건드리고, 워커 스크립트도 더는 필요 없어 삭제했다.
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(c, n, d=""):
    (PASS if c else FAIL).append((n, d))
    print(("  [OK]   " if c else "  [FAIL] ") + n + ("" if c else f"   {d}"))


print("=" * 72)
print("  스캔 489라운드 회귀 — 주소검색 q 길이 상한 누락")
print("=" * 72)

ADDR_PATH = os.path.join(HERE, "addr_search.py")
APP_PATH = os.path.join(HERE, "app.py")
ADDR_SRC = io.open(ADDR_PATH, encoding="utf-8").read()
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 두 지점 모두 유일하게 존재하는지")
# ──────────────────────────────────────────────────────────────
_a = ADDR_SRC.find('    #  ⚠⚠ [라운드489]')
_b = ADDR_SRC.find('        return []\n', _a)
_b = _b + len('        return []\n') if _b > 0 else -1
BLOCK_ADDR = ADDR_SRC[_a:_b] if _a > 0 and _b > _a else ""
ORIG_ADDR = '    if len(q) < 2:\n        return []\n'

chk(bool(BLOCK_ADDR) and "len(q) > 200" in BLOCK_ADDR, "① addr_search.search()의 상한검사를 찾았다")
chk(ADDR_SRC.count(BLOCK_ADDR) == 1, "① 블록이 소스에 유일하다", ADDR_SRC.count(BLOCK_ADDR) if BLOCK_ADDR else 0)

_c = APP_SRC.find('    #  ⚠⚠ [라운드489]')
_marker = '                        "hint": "검색어가 너무 깁니다. (200자 이내)"})\n'
_d = APP_SRC.find(_marker, _c)
_d = _d + len(_marker) if _d > 0 else -1
BLOCK_APP = APP_SRC[_c:_d] if _c > 0 and _d > _c else ""

chk(bool(BLOCK_APP) and "len(q) > 200" in BLOCK_APP, "② app.py 라우트의 상한검사를 찾았다")
chk(APP_SRC.count(BLOCK_APP) == 1, "② 블록이 소스에 유일하다", APP_SRC.count(BLOCK_APP) if BLOCK_APP else 0)

# ══════════════════════════════════════════════════════════════
print("\n[2] 인메모리 실행(서브프로세스 없음) — addr_search 직접 + Flask 라우트")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="r489_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "v.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "u")
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
    # ── ① addr_search.search() 자신 — 실제 함수 + 되돌림-증명 (모킹 정리까지 완결) ──
    import addr_search as ADDR
    _orig_search_fn = ADDR.search
    calls = []
    ADDR._key = lambda: ""
    ADDR._open_map = lambda q: (calls.append(q) or [])

    addr_over_result = ADDR.search("가" * 201)
    addr_over_called = len(calls)
    calls.clear()
    ADDR.search("정상주소")
    addr_ok_called = len(calls)

    chk(addr_over_result == [], "★ addr_search.search(): 201자는 빈 목록", addr_over_result)
    chk(addr_over_called == 0,
        "★★★★★ 새 코드: 201자는 _open_map()을 아예 호출하지 않는다(외부로 안 나간다)",
        addr_over_called)
    chk(addr_ok_called == 1, "정상 검색어는 그대로 _open_map()까지 도달한다", addr_ok_called)

    _body_search = _py_fn_body(ADDR_SRC, "search")
    chk(BLOCK_ADDR in _body_search, "  (준비) search() 본문 안에 BLOCK_ADDR이 있다")
    _old_body_search = _body_search.replace(BLOCK_ADDR, ORIG_ADDR, 1)
    chk(ORIG_ADDR in _old_body_search and BLOCK_ADDR not in _old_body_search,
        "  (준비) 상한검사 제거가 정확히 적용됐다(실제 파일은 안 건드림)")

    exec(compile(_old_body_search, "<round489_pre489_addr_search>", "exec"), vars(ADDR))  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록·모듈의 진짜 __dict__에 직접(기법3)
    try:
        calls.clear()
        over_old_result = ADDR.search("가" * 201)
        over_old_called = len(calls)
    finally:
        ADDR.search = _orig_search_fn
    chk(over_old_called == 1,
        "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림): 201자가 그대로 _open_map()까지 "
        "도달한다 — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
        (over_old_result, over_old_called))
    chk(ADDR.search is _orig_search_fn, "  addr_search.search가 원래 함수객체로 복원됐다")

    # ── ② app.py 라우트 자신 — 실제 Flask 앱 + 되돌림-증명 ──
    import db as DB
    DB.init_db()
    c = DB.get_db()
    c.execute("INSERT INTO admins(username,password_hash,name,role) "
              "VALUES('b','x','n','최고관리자')")
    c.commit()
    c.close()

    import app as A
    _MOCK_HIT = [{"road": "MOCK", "jibun": "MOCK", "zipcode": "", "building": "",
                  "region": "", "lat": 1.0, "lng": 1.0}]
    A.ADDR.search = lambda q: list(_MOCK_HIT)
    A.ADDR.provider = lambda: "TEST"
    cl = A.app.test_client()
    with cl.session_transaction() as s:
        s["admin"] = "b"; s["admin_role"] = "최고관리자"; s["_csrf"] = "x"

    r_long = cl.get("/api/address/search?q=" + ("나" * 201))
    j_long = r_long.get_json()
    r_ok = cl.get("/api/address/search?q=정상주소")
    j_ok = r_ok.get_json()

    chk((j_long or {}).get("items") == [], "★ 라우트: 201자는 items가 빈 배열", j_long)
    chk("너무 깁니다" in ((j_long or {}).get("hint") or ""),
        "★★★★★ 새 코드: 라우트가 '너무 깁니다' 원인 메시지를 준다", j_long)
    chk(len((j_ok or {}).get("items") or []) == 1,
        "정상 검색어는 그대로 결과(모킹된 1건)가 온다", j_ok)

    _body_route = _py_fn_body(APP_SRC, "api_address_search")
    chk(BLOCK_APP in _body_route, "  (준비) api_address_search() 본문 안에 BLOCK_APP이 있다")
    _old_body_route = (_body_route
                        .replace("def api_address_search():",
                                 "def _api_address_search_pre489():", 1)
                        .replace(BLOCK_APP, "", 1))
    chk("_api_address_search_pre489" in _old_body_route and BLOCK_APP not in _old_body_route,
        "  (준비) 함수 리네임 + 상한검사 제거가 정확히 적용됐다(실제 파일은 안 건드림)")

    _ns489 = dict(vars(A))
    exec(compile(_old_body_route, "<round489_pre489_address_search>", "exec"), _ns489)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_route_fn = _ns489["_api_address_search_pre489"]  # 데코레이터가 없는 라우트라 그대로 쓴다

    _orig_view489 = A.app.view_functions["api_address_search"]
    A.app.view_functions["api_address_search"] = old_route_fn
    try:
        r_old_route = cl.get("/api/address/search?q=" + ("나" * 201))
    finally:
        A.app.view_functions["api_address_search"] = _orig_view489
    j_old_route = r_old_route.get_json()
    chk(len((j_old_route or {}).get("items") or []) == 1,
        "★★★★★ 옛 코드(되돌림): 라우트도 201자를 그대로 검색에 넘겨 결과가 온다(모킹된 1건)",
        j_old_route)
    chk(A.app.view_functions["api_address_search"] is _orig_view489,
        "  view_functions가 원래 함수객체로 복원됐다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2] 실행/되돌림-증명", f"{type(e).__name__}: {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
