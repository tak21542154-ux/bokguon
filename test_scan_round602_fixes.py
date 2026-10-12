# -*- coding: utf-8 -*-
"""스캔 602라운드 회귀 — 보험사 사건 등록 멱등키 지문 헬퍼 _idem_fingerprint() 의
   address 정제가 형제(_create_case() 안 case_no, 라운드601)와 같은 결함으로
   raw `(d.get("address") or "").strip()` 이라, 보험사 전산이 주소를 **숫자**로
   보내면(우편번호를 주소칸에 그대로 넣는 등, 흔한 연동 실수) AttributeError:
   'int' object has no attribute 'strip' 로 500이 나던 결함.

   조사 배경 — 이번 라운드 지시 각도(2) "_s()의 의도된 적용범위(보험사
   서버-서버 연동) 전체를 정확히 재확인"을 따라 _create_case() 자체(이미
   601에서 case_no까지 전부 _s() 로 통일됨, 클린 재확인)뿐 아니라 그 함수가
   부르는 v1 API 전용 보조 헬퍼까지 훑었다. _idem_fingerprint(d) 는
   api_v1_case_create·api_insurer_case_create 양쪽이 공유하는 멱등키 지문
   계산 헬퍼인데, 바로 옆 줄 est_price 는 이미 `str(d.get("est_price") or "")`
   로 문자열을 강제한 뒤 .strip() 하는데(안전) address 만 그 강제 없이
   `(d.get("address") or "").strip()` 이었다 — _s() 자신의 문서("보험사
   전산이 숫자나 객체를 보내면 (v or "").strip() 이 AttributeError 를 낸다")가
   정확히 지목하는 바로 그 패턴이 같은 헬퍼 안에서 형제 필드와 갈라져 있었다.

   실제 도달 경로 — POST /api/v1/cases 에 Idempotency-Key(헤더 또는 본문의
   idempotency_key/ext_ref)를 실어 보내면, _create_case() 자신은 이미
   _s() 로 address 를 안전하게 저장한 **뒤** _idem_fingerprint(d) 가 다시
   호출되어 지문을 UPDATE 한다(그리고 같은 키로 재시도가 오면 그 앞에서도
   한 번 더 불린다) — 이 두 번째·세 번째 호출이 원본 d(가공 전 raw 값)를
   다시 읽어 그 자리에서 크래시한다. 첫 요청은 사건이 이미 INSERT 된
   (커밋 전) 트랜잭션 도중에 죽으므로 전역 오류핸들러가 롤백은 시키지만
   보험사에게는 성공 대신 500 이 간다 — 접수 자체가 막힌다.
   (운영 로그 bokguon.log.1 에는 이 조합(Idempotency-Key + 숫자 address)의
   실제 사례가 없었다 — 과거 시행된 무작위 결함주입 조사(2026-08-05)가
   그 시점엔 없었던 멱등키 기능의 이 경로까지는 닿지 않았던 것으로 보인다.
   이번 라운드는 그 로그 마이닝이 못 잡은 코드경로를 직접 코드 대조로 찾은
   사례다.)

   고침 — 새 로직 없이, 바로 옆에서 이미 안전한 형제 est_price 의 str()
   강제와 같은 목적의 공용 헬퍼 _s() 를 이 칸에도 그대로 적용
   (app.py, _idem_fingerprint() 안 address 정제 한 줄).

   [1] 소스 확인 — _idem_fingerprint() 안에 raw `(d.get("address") or "").strip()`
       이 더 이상 없고, `_s(d.get("address"))` 로 바뀌었다.
   [2] 실행 — 실제 Flask+DB. POST /api/v1/cases 에 Idempotency-Key 헤더와 함께
       숫자 address 를 보내 500 대신 201 이 오는지 확인. 같은 키로 재시도해도
       200 duplicate 로 살아남는지(=두 번째 호출 지점도 안전한지) 확인.
       같은 키에 **다른** 숫자 address 를 보내면 여전히 지문 불일치로
       409 IDEM_KEY_MISMATCH 가 오는지(=단순히 죽였을 뿐 식별력을 잃지
       않았는지) 확인. 문자열 address 로도 기존 동작 무회귀를 확인한다.
   [3] 되돌리기 — 수정 직전 원문(raw .strip())을 그대로 재구성해 실행하면
       실제로 AttributeError 가 나는지 확인 — 이 테스트가 실제로 회귀를
       잡아낼 능력이 있음을 증명.

       python test_scan_round602_fixes.py
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
print("  스캔 602라운드 회귀 — _idem_fingerprint() address 정제 raw .strip() 결함")
print("=" * 72)

print("\n[1] 소스 확인")
fp_body = _py_fn_body(APP_SRC, "_idem_fingerprint")
chk('(d.get("address") or "").strip()' not in fp_body,
    "★★★★★ _idem_fingerprint() 안에 raw (d.get(\"address\") or \"\").strip() 이 더 이상 없다")
chk('"address": _s(d.get("address"))' in fp_body,
    "★★★★★ address 정제가 형제(_s()) 패턴을 쓴다")

print("\n[2] 실행 — 실서버 경로(Flask test_client + 임시 DB)로 실제 재현")
_tmpdir = tempfile.mkdtemp(prefix="round602_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
os.environ["BOKGUON_OTP_POLICY"] = "off"
sys.path.insert(0, HERE)

RAW_KEY = "bok_live_r602testkey"
client = None
A = None

try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute(
        "INSERT INTO insurers(id,name,status,api_key_hash,api_key_prefix,api_enabled) "
        "VALUES(1,'R602보험',?,?,?,1)",
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
    #  숫자 address + Idempotency-Key — 고치기 전엔 사건 INSERT 뒤
    #  _idem_fingerprint(d) 두 번째 호출(지문 UPDATE)에서 500(AttributeError)이 났다.
    try:
        r = client.post("/api/v1/cases", headers={**HDR, "Idempotency-Key": "R602-KEY-1"}, json={
            "address": 12345,             # ★ 숫자로 보낸다 — 우편번호를 주소칸에 넣는 흔한 실수 재현
            "category": "누수·배관·설비",
            "region": "서울", "est_price": 500000,
        })
        chk(r.status_code == 201,
            "★★★★★ Idempotency-Key와 함께 address 를 숫자로 보내도 500 대신 201 이 온다"
            "(고치기 전엔 AttributeError: 'int' object has no attribute 'strip' 로 500)",
            (r.status_code, r.get_data(as_text=True)[:300]))
        body1 = r.get_json() or {}
        case_no_1 = body1.get("case_no")
    except Exception as e:                                          # noqa: BLE001
        chk(False, "★★★★★ [2-a] 숫자 address + Idempotency-Key 최초 접수 실행", f"{type(e).__name__} {e}")
        case_no_1 = None

    #  같은 키로 재시도 — _idem_fingerprint(d) 의 **첫 번째** 호출 지점
    #  (prev 존재 시 지문 비교)도 같은 raw .strip() 을 썼다 — 이 경로도 안전한지 확인.
    try:
        r2 = client.post("/api/v1/cases", headers={**HDR, "Idempotency-Key": "R602-KEY-1"}, json={
            "address": 12345,
            "category": "누수·배관·설비",
            "region": "서울", "est_price": 500000,
        })
        chk(r2.status_code == 200 and (r2.get_json() or {}).get("duplicate") is True,
            "★★★★★ 같은 키로 재시도해도 500 대신 200 duplicate 로 살아남는다"
            "(_idem_fingerprint 첫 번째 호출 지점도 안전)",
            (r2.status_code, r2.get_data(as_text=True)[:300]))
        chk((r2.get_json() or {}).get("case_no") == case_no_1,
            "STEP 재시도 응답의 case_no 가 최초 접수와 동일하다(진짜 중복판정)",
            (r2.get_json() or {}).get("case_no"))
    except Exception as e:                                          # noqa: BLE001
        chk(False, "★★★★★ [2-b] 같은 키 재시도 실행", f"{type(e).__name__} {e}")

    #  같은 키 + **다른** 숫자 address — 죽이지만 않았을 뿐 식별력을 잃지 않았는지.
    try:
        r3 = client.post("/api/v1/cases", headers={**HDR, "Idempotency-Key": "R602-KEY-1"}, json={
            "address": 99999,             # 최초 접수(12345)와 다른 숫자
            "category": "누수·배관·설비",
            "region": "서울", "est_price": 500000,
        })
        chk(r3.status_code == 409 and (r3.get_json() or {}).get("code") == "IDEM_KEY_MISMATCH",
            "★★★★ 같은 키에 다른 숫자 address 를 보내면 여전히 지문 불일치로 409 가 온다"
            "(단순 무시가 아니라 정상적으로 구분한다)",
            (r3.status_code, r3.get_data(as_text=True)[:300]))
    except Exception as e:                                          # noqa: BLE001
        chk(False, "★★★★ [2-c] 지문 불일치 판정 실행", f"{type(e).__name__} {e}")

    #  문자열 address — 기존 동작 그대로(무회귀).
    try:
        r4 = client.post("/api/v1/cases", headers={**HDR, "Idempotency-Key": "R602-KEY-2"}, json={
            "address": "  서울시 송파구 오금로 233  ",
            "category": "누수·배관·설비",
            "region": "서울", "est_price": 500000,
        })
        chk(r4.status_code == 201, "STEP 문자열 address 는 여전히 201(무회귀)", r4.status_code)
        body4 = r4.get_json() or {}
        chk(body4.get("case_no") is not None and body4.get("case_no") != case_no_1,
            "STEP 문자열 address 접수는 새 사건으로 정상 생성된다", body4.get("case_no"))
    except Exception as e:                                          # noqa: BLE001
        chk(False, "★★★ [2-d] 문자열 address 무회귀 실행", f"{type(e).__name__} {e}")

print("\n[3] 되돌리기 — 수정 직전 원문(raw .strip())을 재구성하면 실제로 재현되는가")
try:
    _PRE602 = '"address": (d.get("address") or "").strip(),'
    chk(_PRE602 not in fp_body,
        "STEP 수정 직전 원문 그대로는 지금 소스에 더 이상 없다")

    ns = {}
    exec(compile(f"def _snip(d):\n    {_PRE602}\n    return address\n"
                 .replace('"address": ', "address = ").replace(",\n", "\n"),
                 "<round602_pre>", "exec"), ns)                     # noqa: S102 -- 우리 소스 재구성
    try:
        ns["_snip"]({"address": 12345})
        chk(False, "★★★★★ 수정 전 코드(재구성)는 숫자 address 에서 AttributeError 가 나야 하는데 안 났다")
    except AttributeError as e:
        chk("strip" in str(e),
            "★★★★★ 수정 전 코드(재구성)는 숫자 address 에서 실제로 AttributeError 를 낸다"
            "(int 객체엔 strip 이 없다) — 이 테스트가 실제로 회귀를 잡아낸다는 증거", str(e))

    # 지금(수정 후) 소스에서 그대로 뽑아 온 문장으로 같은 입력을 돌리면 살아남는다.
    _cur_line = fp_body[fp_body.index('"address": _s('):].split("\n", 1)[0].strip()
    _cur_stmt = "address = " + _cur_line[len('"address": '):].rstrip(",")
    ns2 = {"_s": A._s}
    exec(compile(f"def _snip2(d):\n    {_cur_stmt}\n    return address\n",
                 "<round602_post>", "exec"), ns2)                   # noqa: S102 -- 우리 소스에서 그대로 추출
    got = ns2["_snip2"]({"address": 12345})
    chk(got == "12345",
        "★★★★★ 지금(수정 후) 소스에서 그대로 뽑아 온 문장은 같은 입력에서 예외 없이 "
        "\"12345\" 를 돌려준다 — 인과관계 직접증명", got)
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
