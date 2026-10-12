# -*- coding: utf-8 -*-
"""스캔 601라운드 회귀 — 보험사 사건 등록 공용 헬퍼 _create_case() 의 접수번호
   (case_no) 정제가 형제들(region·address·manager·victim_name·victim_phone·note,
   전부 _s() 사용)과 달리 raw `(d.get("case_no") or "").strip()` 이라, 보험사
   전산이 접수번호를 **숫자**로 보내면 AttributeError: 'int' object has no
   attribute 'strip' 로 500 이 나던 결함.

   조사 배경 — 이번 라운드 지시 각도(4) "정산/입찰 금액 함수들의 경계값(음수·0)"을
   따라 parse_money() 등을 훑었으나 그쪽은 이미 완전히 막혀 있었다(클린). 대신
   운영 로그(bokguon.log, 6.5만 줄)를 실제로 열어 최근 실패 시그니처를 전수
   분류하니 대부분(round527·430·199·538 등)이 그 라운드 자신의 "고의 주입
   결함"(자기 회귀테스트가 되돌리기 증명용으로 일부러 낸 예외)이었다 — 이건
   직접 재현으로 가려냈다(예: "type 'object' is not supported" 249건은 전부
   test_scan_round538_fixes.py 의 _poison_factory() 가 info["size"]=object()
   로 주입한 것, 실제 소스는 이미 정상). 그런데 그 분류 도중 발견한
   `AttributeError: 'int' object has no attribute 'strip'`
   (2026-08-05, POST /api/v1/cases, _normalize_categories 안)은 이미 _s() 로
   고쳐져 있었다 — 단, 그 수정이 **같은 함수의 다른 칸(case_no)까지는 못
   미쳤다.** _s() 자신의 문서("보험사 전산이 숫자나 객체를 보내면 (v or "").
   strip() 이 AttributeError 를 낸다")가 정확히 지목하는 그 패턴이 바로 옆
   줄에 그대로 남아 있었다 — 실측(수정 전 소스 재구성, [3])으로 직접 재현.

   실제 도달 경로 — POST /api/v1/cases(보험사 서버-서버 연동 API, require_api_key)
   와 POST /api/insurer/cases(보험사 포털) 둘 다 공용 헬퍼 _create_case() 를
   부른다. 접수번호를 사내 채번 정수 PK로 관리하는 보험사 시스템이 JSON 본문에
   "case_no": 20260601 처럼 **숫자**로 보내면(문자열 강제 없이 그대로 전송하는
   것은 흔한 연동 실수다) 이 헬퍼가 500 을 낸다 — 접수 자체가 막힌다.

   고침 — 새 로직 없이, 같은 함수 안 형제들이 이미 쓰는 _s(d.get(...), n) 패턴을
   이 칸에도 그대로 적용(app.py, _create_case() 안 case_no 정제 한 줄).

   [1] 소스 확인 — _create_case() 안에 raw `(d.get("case_no") or "").strip()`
       이 더 이상 없고, `_s(d.get("case_no"), 20)` 로 바뀌었다.
   [2] 실행 — 실제 Flask+DB. POST /api/v1/cases 에 case_no 를 정수로 보내
       500 대신 201 이 오고, 저장된 case_no 가 그 정수를 문자열화한 값인지 확인.
       같은 요청을 문자열 case_no 로도 보내 기존 동작 무회귀를 확인한다.
   [3] 되돌리기 — 수정 직전 원문(raw .strip())을 그대로 재구성해 실행하면
       실제로 AttributeError 가 나는지 확인 — 이 테스트가 실제로 회귀를
       잡아낼 능력이 있음을 증명.

       python test_scan_round601_fixes.py
"""
import io
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 601라운드 회귀 — _create_case() 접수번호(case_no) 정제 raw .strip() 결함")
print("=" * 72)

print("\n[1] 소스 확인")
cc_body = _py_fn_body(APP_SRC, "_create_case")
chk('(d.get("case_no") or "").strip()' not in cc_body,
    "★★★★★ _create_case() 안에 raw (d.get(\"case_no\") or \"\").strip() 이 더 이상 없다")
chk('case_no = _s(d.get("case_no"), 20)' in cc_body,
    "★★★★★ case_no 정제가 형제들과 같은 _s(d.get(...), n) 패턴을 쓴다")

print("\n[2] 실행 — 실서버 경로(Flask test_client + 임시 DB)로 실제 재현")
_tmpdir = tempfile.mkdtemp(prefix="round601_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
os.environ["BOKGUON_OTP_POLICY"] = "off"
sys.path.insert(0, HERE)

RAW_KEY = "bok_live_r601testkey"
client = None
A = None

try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute(
        "INSERT INTO insurers(id,name,status,api_key_hash,api_key_prefix,api_enabled) "
        "VALUES(1,'R601보험',?,?,?,1)",
        ("활성", A._hash_api_key(RAW_KEY), RAW_KEY[:16]))
    conn.commit()
    conn.close()

    client = A.app.test_client()
    HDR = {"X-API-Key": RAW_KEY}

    chk(True, "STEP 스크래치 DB·app 모듈 로드 성공 — API 연동 보험사 1건 준비",
        os.environ["BOKGUON_DB_PATH"])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 실행 준비(DB.init_db·app import)", f"{type(e).__name__} {e}")

if client is not None:
    #  숫자 case_no — 고치기 전엔 여기서 500(AttributeError)이 났다.
    try:
        r = client.post("/api/v1/cases", headers=HDR, json={
            "case_no": 20260601,          # ★ 숫자로 보낸다 — 보험사 전산의 흔한 실수 재현
            "category": "누수·배관·설비",
            "region": "서울", "est_price": 500000,
        })
        chk(r.status_code == 201,
            "★★★★★ case_no 를 정수로 보내도 500 대신 201 이 온다"
            "(고치기 전엔 AttributeError: 'int' object has no attribute 'strip' 로 500)",
            (r.status_code, r.get_data(as_text=True)[:300]))
        body = r.get_json() or {}
        chk(body.get("case_no") == "20260601",
            "★★★★ 저장된 접수번호가 보낸 정수를 문자열화한 값(\"20260601\")이다"
            "(_s() 가 str() 강제 후 정제한다)", body.get("case_no"))
    except Exception as e:                                          # noqa: BLE001
        chk(False, "★★★★★ [2-a] 숫자 case_no 실행", f"{type(e).__name__} {e}")

    #  문자열 case_no — 기존 동작 그대로(무회귀).
    try:
        r2 = client.post("/api/v1/cases", headers=HDR, json={
            "case_no": "  R601-STR-01  ",
            "category": "누수·배관·설비",
            "region": "서울", "est_price": 500000,
        })
        chk(r2.status_code == 201, "STEP 문자열 case_no 는 여전히 201", r2.status_code)
        body2 = r2.get_json() or {}
        chk(body2.get("case_no") == "R601-STR-01",
            "STEP 문자열 case_no 는 앞뒤 공백만 제거되어 그대로 저장된다(무회귀)",
            body2.get("case_no"))
    except Exception as e:                                          # noqa: BLE001
        chk(False, "★★★ [2-b] 문자열 case_no 무회귀 실행", f"{type(e).__name__} {e}")

    #  20자 초과 case_no — 형제 필드들과 같은 길이 상한이 여전히 걸리는지.
    try:
        r3 = client.post("/api/v1/cases", headers=HDR, json={
            "case_no": 123456789012345678901234,   # 24자리 숫자 — 20자 상한 초과
            "category": "누수·배관·설비",
            "region": "서울", "est_price": 500000,
        })
        chk(r3.status_code == 201, "STEP 20자 초과 숫자 case_no 도 500 없이 처리", r3.status_code)
        body3 = r3.get_json() or {}
        chk(bool(body3.get("case_no")) and len(body3.get("case_no", "")) == 20,
            "★★★ 20자 상한이 숫자 입력에도 그대로 적용된다(폭주 문자열 저장 방지)",
            body3.get("case_no"))
    except Exception as e:                                          # noqa: BLE001
        chk(False, "★★★ [2-c] 20자 초과 숫자 case_no 실행", f"{type(e).__name__} {e}")

print("\n[3] 되돌리기 — 수정 직전 원문(raw .strip())을 재구성하면 실제로 재현되는가")
try:
    _PRE601 = 'case_no = (d.get("case_no") or "").strip()[:20]'
    chk(_PRE601 not in cc_body,
        "STEP 수정 직전 원문 그대로는 지금 소스에 더 이상 없다")

    ns = {}
    exec(compile(f"def _snip(d):\n    {_PRE601}\n    return case_no\n",
                 "<round601_pre>", "exec"), ns)                     # noqa: S102 -- 우리 소스 재구성
    try:
        ns["_snip"]({"case_no": 20260601})
        chk(False, "★★★★★ 수정 전 코드(재구성)는 숫자 case_no 에서 AttributeError 가 나야 하는데 안 났다")
    except AttributeError as e:
        chk("strip" in str(e),
            "★★★★★ 수정 전 코드(재구성)는 숫자 case_no 에서 실제로 AttributeError 를 낸다"
            "(int 객체엔 strip 이 없다) — 이 테스트가 실제로 회귀를 잡아낸다는 증거", str(e))

    # 지금(수정 후) 소스에서 그대로 뽑아 온 문장으로 같은 입력을 돌리면 살아남는다.
    _cur_line = cc_body[cc_body.index("case_no = _s("):].split("\n", 1)[0].strip()
    ns2 = {"_s": A._s}
    exec(compile(f"def _snip2(d):\n    {_cur_line}\n    return case_no\n",
                 "<round601_post>", "exec"), ns2)                   # noqa: S102 -- 우리 소스에서 그대로 추출
    got = ns2["_snip2"]({"case_no": 20260601})
    chk(got == "20260601",
        "★★★★★ 지금(수정 후) 소스에서 그대로 뽑아 온 문장은 같은 입력에서 예외 없이 "
        "\"20260601\" 을 돌려준다 — 인과관계 직접증명", got)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ [3] 되돌림-증명 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
