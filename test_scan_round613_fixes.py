# -*- coding: utf-8 -*-
"""스캔 613라운드 회귀 — 자동견적 엔진(repair_estimate.py)의 _validate() 가
inputs 가 dict 가 아니면(정수·실수·bool 등) `k in inputs` 에서
TypeError 로 죽던 결함, 1건.

배경 — RE.estimate(pattern_id, inputs, price_book=None) 은 app.py 두 곳에서
부른다: ① api_field_agreement_open(18909행)은 자기 쪽에서
`isinstance(d.get("inputs"), dict) else {}` 로 이미 막고 있었지만,
② api_repair_estimate(20567행)는 `d.get("inputs") or {}` 뿐이라 None·0·빈값만
막고 정수·실수·bool(True) 같은 "참인 non-dict" 는 그대로 통과시켰다.
그 값이 RE.estimate() → _validate() 안의 `if k in inputs and inputs[k]
is not None:` 에 들어가면 `k in 42` 가 `TypeError: argument of type 'int'
is not iterable` 로 죽는데, EstimateError(ValueError 상속)가 아니라 이
모듈이 아예 안 잡는 예외라 api_repair_estimate 의 `except RE.EstimateError`
를 그대로 통과해 전역 핸들러(app.py err_500)까지 새어 SERVER_ERROR(500)가
됐다 — 이 코드베이스가 라운드601~609에 걸쳐 전역적으로 지켜 온 "클라이언트
입력 오류는 400" 관례를 어기는 자리였다(그 라운드들의 `.strip()` 계열
정규식스윕은 이 자리를 못 잡았다 — 실패 형태가 AttributeError 가 아니라
`k in inputs` 의 TypeError 라서).

실측(수정 전, 스크래치DB+실제 Flask 앱): POST /api/repair-estimate
{"pattern":"guardrail_section","inputs":42} → 500 SERVER_ERROR.
{"inputs":3.14} · {"inputs":true} 도 동일 재현.

고침 — 호출부 두 곳 중 가드 없는 쪽만 patch하는 대신, 실제 합류점인
_validate() 맨 앞에서 `isinstance(inputs, dict)` 를 확인해 아니면
EstimateError 로 정중히 거절한다(다른 호출부·미래의 호출부까지 전부 한
곳에서 방어). 정상 dict 입력·기존 검증 로직(숫자범위·choice·NaN/Inf 등)은
전혀 안 건드림.

[1] 소스 확인 — _validate() 안에 isinstance 가드가 있다.
[2] 실행 — 실제 Flask 앱(스크래치 DB)으로 두 경로 모두 확인:
    RE.estimate() 직접 호출 + api_repair_estimate 라우트 양쪽에서 정수·
    실수·bool·리스트·문자열 inputs 가 이제 EstimateError/400 으로 깔끔히
    막히고, 정상 dict 입력·다른 호출부(api_field_agreement_open)는 회귀
    없이 그대로 동작.
[3] 되돌리기 — _validate() 의 isinstance 가드 두 줄만 exec 로 RE.__dict__
    에서 임시로 걷어내(진짜 repair_estimate.py 파일은 전혀 안 건드림)
    같은 조건이 실제로 TypeError/500 을 재현하는지 확인한 뒤 복원한다.

    python test_scan_round613_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


RE_SRC = read("repair_estimate.py")

print("=" * 72)
print("  스캔 613라운드 회귀 — RE.estimate() inputs 비-dict 입력 시 500")
print("=" * 72)

print("\n[1] 소스 확인")


def _fn_body(src, fn_name):
    """모듈 최상위 함수 하나만 떼어낸다 — '\\ndef '대신 '\\n\\n\\n'(이 코드베이스의
    최상위 함수 사이 관례)으로 끝을 찾아, 데코레이터가 있는 함수가 바로 뒤에
    와도 그 데코레이터까지 삼키지 않는다(round612 gotcha)."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.index("\n\n\n", start + 1)
    return src[start + 1:end]


_validate_body = _fn_body(RE_SRC, "_validate")
GUARD_BLOCK = ('    if not isinstance(inputs, dict):\n'
               '        raise EstimateError("입력값(inputs)은 객체(JSON object) 형식이어야 합니다")\n')
chk(GUARD_BLOCK in _validate_body,
    "★★★★★ _validate() 맨 앞에 isinstance(inputs, dict) 가드가 있다")

print("\n[2] 실행 준비 — 스크래치 DB, 관리자 1명")
_tmpdir = tempfile.mkdtemp(prefix="round613_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A
    import repair_estimate as RE

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r613admin','x','검증','최고관리자')")
    conn.commit()
    conn.close()

    def _admin_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["admin"] = "r613admin"
            sess["admin_role"] = "최고관리자"
            sess["_csrf"] = "r613-csrf"
        return c

    BAD_INPUTS = [42, 3.14, True, "그냥문자열", [1, 2, 3]]

    print("\n[3] 실행 — RE.estimate() 직접 호출: 비-dict inputs 전부 EstimateError")
    for bad in BAD_INPUTS:
        try:
            RE.estimate("guardrail_section", bad, price_book={})
            chk(False, f"★★★★★ inputs={bad!r} 가 예외 없이 통과했다(있으면 안 됨)")
        except RE.EstimateError:
            chk(True, f"★★★★★ inputs={bad!r} 는 EstimateError로 깔끔히 거절된다")
        except Exception as e:                                      # noqa: BLE001
            chk(False, f"★★★★★ inputs={bad!r} 가 EstimateError 가 아닌 "
                f"{type(e).__name__} 로 죽었다(수정 전 회귀)", str(e))

    print("\n[4] 실행 — api_repair_estimate 라우트: 비-dict inputs 는 500이 아니라 400")
    c1 = _admin_client()
    for bad in BAD_INPUTS:
        r = c1.post("/api/repair-estimate", json={"pattern": "guardrail_section", "inputs": bad},
                    headers={"X-CSRF-Token": "r613-csrf"})
        chk(r.status_code == 400,
            f"★★★★★ inputs={bad!r} 는 라우트에서도 400(수정 전엔 500 SERVER_ERROR)",
            (r.status_code, r.get_json()))

    print("\n[5] 회귀 없음 — 정상 dict 입력·다른 호출부는 그대로 동작")
    r_ok = c1.post("/api/repair-estimate", json={"pattern": "guardrail_section",
                                                  "inputs": {"L": 8, "s": 4}},
                   headers={"X-CSRF-Token": "r613-csrf"})
    rb_ok = r_ok.get_json() or {}
    chk(r_ok.status_code == 200 and rb_ok.get("ok") is True,
        "  정상 dict 입력은 여전히 200으로 정상 계산된다(회귀없음)", rb_ok)
    est = rb_ok.get("estimate") or {}
    chk(est.get("direct_cost", 0) > 0 and est.get("range_low", 0) <= est.get("range_high", 0),
        "  계산 결과 자체(direct_cost·range_low<=high)는 그대로다(회귀없음)",
        (est.get("direct_cost"), est.get("range_low"), est.get("range_high")))

    try:
        RE.estimate("guardrail_section", {}, price_book={})
        chk(False, "★★★ 빈 dict({})는 L(필수, 기본값 없음) 누락으로 여전히 거절돼야 하는데 통과했다")
    except RE.EstimateError:
        chk(True, "  빈 dict({})는 isinstance 가드는 통과하고(dict라서) 그 다음 "
            "필드별 required 검사에서 정상적으로 EstimateError 로 거절된다(회귀없음)")

    print("\n[6] 되돌리기 — _validate() 가드만 걷어내면 재현되는가(디스크 미기록)")
    #  ⚠ estimate() 가 _validate 를 맨이름(bare name)으로 부르므로(둘 다 이
    #    모듈 자신의 전역), 되돌린 버전을 estimate() 가 실제로 보게 하려면
    #    사본이 아니라 RE.__dict__ 자체(estimate.__globals__ 와 동일 객체)에
    #    걸어야 한다(round416 의 _normalize_categories 와 동일한 이유) —
    #    진짜 repair_estimate.py 파일은 전혀 안 건드리고 finally 에서 원래
    #    함수 객체로 되돌린다.
    reverted_validate_src = _validate_body.replace(GUARD_BLOCK, "")
    chk(reverted_validate_src != _validate_body,
        "  (준비) 되돌리기 텍스트가 실제로 달라졌다")

    _orig_validate = RE._validate
    exec(compile(reverted_validate_src, "<round613_old_validate>", "exec"), RE.__dict__)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    chk(RE._validate is not _orig_validate,
        "  (준비) RE._validate 가 실제로 옛 버전 함수객체로 바뀌었다")
    try:
        raised = None
        try:
            RE.estimate("guardrail_section", 42, price_book={})
        except Exception as e:                                      # noqa: BLE001
            raised = e
        chk(type(raised).__name__ == "TypeError",
            "★★★★★ 가드를 걷어낸 옛 코드는 실제로 TypeError 로 죽는다"
            "(인과관계 직접증명 — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명)",
            f"{type(raised).__name__}: {raised}" if raised else "예외 없음")

        c2 = _admin_client()
        r_broken = c2.post("/api/repair-estimate",
                            json={"pattern": "guardrail_section", "inputs": 42},
                            headers={"X-CSRF-Token": "r613-csrf"})
        chk(r_broken.status_code == 500,
            "★★★★★ 옛 코드로 되돌리면 라우트도 실제로 500 SERVER_ERROR 가 재현된다",
            (r_broken.status_code, r_broken.get_json()))
    finally:
        RE._validate = _orig_validate

    print("\n[7] 원복 확인 — 복원 후에는 다시 400/EstimateError 로 돌아온다")
    raised2 = None
    try:
        RE.estimate("guardrail_section", 42, price_book={})
    except Exception as e:                                          # noqa: BLE001
        raised2 = e
    chk(isinstance(raised2, RE.EstimateError),
        "★★★★ 원복 후에는 다시 EstimateError 로 깔끔히 거절된다(바꿔치기가 안 샜다)",
        f"{type(raised2).__name__}: {raised2}" if raised2 else "예외 없음")
    c3 = _admin_client()
    r_restored = c3.post("/api/repair-estimate",
                          json={"pattern": "guardrail_section", "inputs": 42},
                          headers={"X-CSRF-Token": "r613-csrf"})
    chk(r_restored.status_code == 400,
        "★★★★ 원복 후에는 라우트도 다시 400으로 돌아온다", r_restored.status_code)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

RE_SRC_AFTER = read("repair_estimate.py")
chk(RE_SRC_AFTER == RE_SRC,
    "★★★★★ repair_estimate.py 파일 내용이 시작부터 끝까지 전혀 안 바뀌었다"
    "(RE.__dict__ 함수객체 임시치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
