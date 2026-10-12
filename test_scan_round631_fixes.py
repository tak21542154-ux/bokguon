# -*- coding: utf-8 -*-
"""스캔 631라운드 회귀 — AI 자동승인 임계값(ai_auto_threshold) 관련 두 자리가
OverflowError를 못 잡던 결함, 2건(직접조사, 하위위임 없음).

배경 — 라운드485는 "int(float(x))는 x가 'inf'/'-inf'/'1e400'류(float 변환은
성공하지만 그 값을 int로 못 바꿈)일 때 ValueError가 아니라 OverflowError를
낸다"는 함정을 발견해 형제 둘(_setting_int, 4100행 부근·api_settings_set의
RANGES 검증 루프)에 이식했고, 라운드596은 같은 예외의 또 다른 유입구(JSON
본문의 id류)를 흩어진 호출부마다 고치는 대신 전역 예외핸들러(err_500)에서
한 번에 400으로 눌러 두었다. 이 두 라운드 사이에서 정확히 같은 값
(settings.ai_auto_threshold)을 다루는 세 번째·네 번째 자리가 빠져 있었다 —
grep으로 app.py 전체의 "OverflowError" 8곳을 전수 대조해 확인(라운드485·596
자신의 위치만 있고 이 두 함수는 어디에도 없었다).

[A] _ai_threshold(conn) — 자동승인 임계값을 읽는 유일한 헬퍼(호출부 2곳:
    _apply_ai_routing·api_ai_review_stats). docstring 자체가 "설정값이
    있으면 그것을, 없으면 기본 90"이라고 **항상 안전하게 되돌아간다**고
    약속하는데(_setting_int와 똑같은 계약), except가 (sqlite3.Error,
    ValueError)뿐이라 settings.value='inf'면 그대로 OverflowError가 샌다.
    ⚠ 이게 유독 나쁜 이유 — 유일한 실사용 호출부 _apply_ai_routing()은
    사진 업로드가 **이미 커밋된 뒤**(같은 함수 docstring: "분류 UPDATE와
    별도 커넥션으로 짧게 처리") AI 자동승인 여부만 결정하는 후처리인데,
    그 함수 자신의 except가 sqlite3.Error 하나뿐이라(직접 Read로 확인)
    _ai_threshold의 OverflowError를 못 가린다 — 사진은 저장됐는데 업로드
    응답 전체가 400(라운드596 전역핸들러 "입력값이 너무 큽니다")으로
    돌아가, 업로드한 협력사는 자기 사진이 이미 반영됐다는 사실을 알 방법이
    없다. "설정이 깨졌다고 업무가 멈추면 안 된다"는 원칙 위반.
[B] api_ai_threshold_set() (PATCH /api/ai/threshold, 최고관리자 전용) —
    JSON 본문의 threshold가 1e400처럼 과대하면(표준 JSON 문법, 비표준
    Infinity 리터럴이 아님) json 파서가 그대로 float('inf')로 성공 파싱하고
    (실측: json.loads('{"threshold":1e400}') == {'threshold': inf}),
    int(그 값)이 OverflowError를 낸다. 이 라우트 자신의 except가
    (TypeError, ValueError)뿐이라 이 라우트가 공들여 준비한 구체적 안내문
    ("임계값은 0~100 사이 숫자여야 합니다")이 라운드596 전역핸들러의
    범용 문구("입력값이 너무 큽니다"/code=BAD_INPUT)로 가려진다 — 500은
    아니지만(라운드596 덕분) 이 함수 자신의 UX 의도가 무효화된다.

고침 — 두 곳 다 형제(_setting_int·RANGES 루프)와 똑같은 최소 diff:
except 튜플에 OverflowError를 추가([A]는 TypeError도 함께 — r["value"]가
None이 아님만 보장되지 실제 타입까지는 보장 안 되므로 _setting_int과
바이트 단위로 같은 튜플로 맞춤). 새 메커니즘·새 헬퍼 없음.

검증
  [1] 소스 확인 — 두 except 튜플에 OverflowError가 있고, _apply_ai_routing()
      자신의 except는 여전히 sqlite3.Error 하나뿐임(=OverflowError를
      못 가린다는 주장의 구조적 증거)을 직접 대조.
  [2]~[3] 실행 — 실제 Flask 앱(스크래치 DB)으로 (a) settings에 문자 그대로
      'inf'를 심고 _ai_threshold()를 직접 호출해 예외 없이 기본값(90)을
      돌려주는지, (b) PATCH 라우트에 1e400을 실제 HTTP 왕복으로 보내
      "임계값은 0~100 사이 숫자여야 합니다"를 돌려주는지(회귀없음: 정상
      값·범위밖 정상숫자는 그대로 동작).
  [4]~[5] 되돌리기-증명 — 두 함수 다 이 라운드가 고친 except 튜플만
      옛(취약) 튜플로 되돌린 사본을 exec로 격리 재구성해([A]는 모듈
      속성 직접치환, [B]는 view_functions 딕셔너리 항목치환 — round414·
      610·615가 확립한 안전패턴 그대로) 옛 코드가 실제로 OverflowError를
      내거나(A) 전역핸들러의 범용 문구로 가려지는지(B)를 실행으로
      재현한 뒤 finally에서 원복 — 진짜 app.py 파일은 이 과정 전체에서
      단 한 바이트도 안 바뀐다(마지막에 디스크 재확인).

    python test_scan_round631_fixes.py
"""
import io
import json
import os
import sqlite3
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
print("  스캔 631라운드 회귀 — ai_auto_threshold OverflowError 미포착 2건")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
NEW_EXC_A = "except (sqlite3.Error, ValueError, TypeError, OverflowError):"
OLD_EXC_A = "except (sqlite3.Error, ValueError):"
NEW_EXC_B = "except (TypeError, ValueError, OverflowError):"
OLD_EXC_B = "except (TypeError, ValueError):"

body_a = _py_fn_body(APP_SRC, "_ai_threshold")
body_b = _py_fn_body(APP_SRC, "api_ai_threshold_set")
body_routing = _py_fn_body(APP_SRC, "_apply_ai_routing")

chk(NEW_EXC_A in body_a, "★★★★★ _ai_threshold()의 except 튜플에 OverflowError가 있다")
chk(body_a.count(NEW_EXC_A) == 1, "  되돌림-증명에 쓸 지점이 정확히 1번만 있다(특정 가능)")
chk(NEW_EXC_B in body_b, "★★★★★ api_ai_threshold_set()의 except 튜플에 OverflowError가 있다")
chk(body_b.count(NEW_EXC_B) == 1, "  되돌림-증명에 쓸 지점이 정확히 1번만 있다(특정 가능)")
chk("except sqlite3.Error:" in body_routing and "OverflowError" not in body_routing,
    "★★★★ _apply_ai_routing() 자신의 except는 여전히 sqlite3.Error 하나뿐이다 "
    "— _ai_threshold()가 OverflowError를 못 가리면 이 함수도 못 가린다는 "
    "구조적 근거(수정 범위 밖 — _setting_int·round596처럼 발생지점에서 막는다)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 준비 — 스크래치 DB + 실제 Flask 앱")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round631_")
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

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('r631admin','x','검증','최고관리자')")
    conn0.commit()
    conn0.close()

    def _admin_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["admin"] = "r631admin"; sess["admin_role"] = "최고관리자"
            sess["_csrf"] = "r631-csrf"
        return c

    def _patch_threshold(raw_body):
        return _admin_client().patch(
            "/api/ai/threshold", data=raw_body, content_type="application/json",
            headers={"X-CSRF-Token": "r631-csrf"})

    def _set_setting(key, value):
        c = DB.get_db()
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))
        c.commit(); c.close()

    # ══════════════════════════════════════════════════════════
    print("\n[3] 실행 — 현재(고쳐진) 코드")
    # ──────────────────────────────────────────────────────────
    # [3-A] _ai_threshold() 직접 호출 — settings에 손상값 'inf'가 있어도 안전해야 한다
    _set_setting("ai_auto_threshold", "inf")
    conn_a = DB.get_db()
    try:
        th_fixed = A._ai_threshold(conn_a)
        exc_fixed = None
    except Exception as e:                                          # noqa: BLE001
        th_fixed, exc_fixed = None, e
    finally:
        conn_a.close()
    chk(exc_fixed is None,
        "★★★★★ settings.ai_auto_threshold='inf'여도 _ai_threshold()가 "
        "예외 없이 끝난다(수정 전엔 OverflowError)", exc_fixed)
    chk(th_fixed == A.AI_AUTO_THRESHOLD_DEFAULT,
        "  손상값은 무시하고 기본값(90)으로 안전하게 되돌아간다", th_fixed)

    # 정상값은 그대로 존중한다(과잉수정 아님 — 회귀없음)
    _set_setting("ai_auto_threshold", "77")
    conn_a2 = DB.get_db()
    th_normal = A._ai_threshold(conn_a2)
    conn_a2.close()
    chk(th_normal == 77, "  정상 설정값(77)은 그대로 읽힌다(회귀없음)", th_normal)

    # [3-B] PATCH /api/ai/threshold 실제 HTTP 왕복 — 1e400은 표준 JSON이지만
    #   파싱되면 float('inf')가 되어 int()에서 OverflowError를 낸다(직접 확인:
    #   json.loads('{"threshold":1e400}') == {'threshold': inf}).
    r_overflow = _patch_threshold('{"threshold": 1e400}')
    chk(r_overflow.status_code == 400,
        "  과대 threshold(1e400)는 400으로 거부된다(500 아님 — round596 안전망)",
        r_overflow.status_code)
    chk((r_overflow.get_json() or {}).get("error") == "임계값은 0~100 사이 숫자여야 합니다.",
        "★★★★★ 이 라우트 자신의 구체적 안내문이 나온다"
        "(수정 전엔 round596 전역핸들러의 범용 문구로 가려짐)",
        r_overflow.get_json())

    # 회귀없음 확인 — 정상 범위값·범위밖 정상숫자·비숫자 문자열은 기존과 동일
    r_ok = _patch_threshold('{"threshold": 85}')
    chk(r_ok.status_code == 200 and r_ok.get_json().get("ok") is True,
        "  정상 범위 값(85)은 그대로 통과한다(회귀없음)", r_ok.get_json())
    r_range = _patch_threshold('{"threshold": 10}')
    chk(r_range.status_code == 400
        and "50~100" in (r_range.get_json() or {}).get("error", ""),
        "  범위밖 정상숫자(10)는 기존과 같은 범위 오류문구로 거부된다(회귀없음)",
        r_range.get_json())
    r_bad = _patch_threshold('{"threshold": "abc"}')
    chk(r_bad.status_code == 400,
        "  숫자가 아닌 문자열은 기존과 같이 400으로 거부된다(회귀없음)",
        r_bad.get_json())

    # ══════════════════════════════════════════════════════════
    print("\n[4] 되돌리기 — _ai_threshold()만 옛 코드로(실제 파일은 안 건드림)")
    # ──────────────────────────────────────────────────────────
    _old_body_a = (body_a
                   .replace("def _ai_threshold(conn):",
                            "def _ai_threshold_pre631(conn):", 1)
                   .replace(NEW_EXC_A, OLD_EXC_A, 1))
    chk(_old_body_a.count(OLD_EXC_A) == 1 and "_ai_threshold_pre631" in _old_body_a,
        "  (준비) 함수 리네임 + except 튜플 축소가 정확히 적용됐다(실제 파일 미변경)")

    _ns_a = dict(vars(A))
    exec(compile(_old_body_a, "<round631_pre631_ai_threshold>", "exec"), _ns_a)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_fn_a = _ns_a["_ai_threshold_pre631"]

    _orig_ai_threshold = A._ai_threshold
    A._ai_threshold = old_fn_a
    _set_setting("ai_auto_threshold", "inf")
    conn_b = DB.get_db()
    try:
        th_broken = A._ai_threshold(conn_b)
        exc_broken = None
    except Exception as e:                                          # noqa: BLE001
        th_broken, exc_broken = None, e
    finally:
        conn_b.close()
        A._ai_threshold = _orig_ai_threshold

    chk(isinstance(exc_broken, OverflowError),
        "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림)는 settings.ai_auto_threshold="
        "'inf'에서 실제로 OverflowError를 그대로 던진다 — 이 테스트가 진짜 결함을 "
        "잡아낼 능력이 있음을 증명", exc_broken)

    print("\n[5] 원복 확인 — 되돌리기 이후 다시 방어되는가(바꿔치기가 안 샜다)")
    chk(A._ai_threshold is _orig_ai_threshold, "  A._ai_threshold가 원래 함수객체로 복원됐다")
    conn_c = DB.get_db()
    th_restored = A._ai_threshold(conn_c)          # settings는 여전히 'inf'
    conn_c.close()
    chk(th_restored == A.AI_AUTO_THRESHOLD_DEFAULT,
        "★★★★ 원복 후에는 다시 안전하게 기본값을 돌려준다(바꿔치기가 안 샜다)",
        th_restored)

    # ══════════════════════════════════════════════════════════
    print("\n[6] 되돌리기 — api_ai_threshold_set()만 옛 코드로(실제 파일은 안 건드림)")
    # ──────────────────────────────────────────────────────────
    _old_body_b = (body_b
                   .replace("def api_ai_threshold_set():",
                            "def _api_ai_threshold_set_pre631():", 1)
                   .replace(NEW_EXC_B, OLD_EXC_B, 1))
    chk(_old_body_b.count(OLD_EXC_B) == 1 and "_api_ai_threshold_set_pre631" in _old_body_b,
        "  (준비) 함수 리네임 + except 튜플 축소가 정확히 적용됐다(실제 파일 미변경)")

    _ns_b = dict(vars(A))
    exec(compile(_old_body_b, "<round631_pre631_ai_threshold_set>", "exec"), _ns_b)  # noqa: S102 -- 디스크 미기록
    old_fn_b = A.require_role("최고관리자")(_ns_b["_api_ai_threshold_set_pre631"])

    _orig_view = A.app.view_functions["api_ai_threshold_set"]
    A.app.view_functions["api_ai_threshold_set"] = old_fn_b
    try:
        r_old = _patch_threshold('{"threshold": 1e400}')
    finally:
        A.app.view_functions["api_ai_threshold_set"] = _orig_view

    chk(r_old.status_code == 400,
        "  옛 코드도 500은 아니다(round596 전역핸들러는 이 되돌림과 무관하게 그대로 살아있음)",
        r_old.status_code)
    chk((r_old.get_json() or {}).get("error") != "임계값은 0~100 사이 숫자여야 합니다.",
        "★★★★★ 옛 코드(되돌림)는 이 라우트만의 구체적 안내문을 못 내고 "
        "round596 전역핸들러의 범용 문구로 대체된다 — 이 테스트가 [B]도 "
        "잡아낼 능력이 있음을 증명", r_old.get_json())
    chk((r_old.get_json() or {}).get("code") == "BAD_INPUT",
        "  실제로 round596 전역핸들러(code=BAD_INPUT)까지 새어나갔다", r_old.get_json())

    print("\n[7] 원복 확인 — 되돌리기 이후 다시 방어되는가(바꿔치기가 안 샜다)")
    chk(A.app.view_functions["api_ai_threshold_set"] is _orig_view,
        "  view_functions가 원래 함수객체로 복원됐다")
    r_restored = _patch_threshold('{"threshold": 1e400}')
    chk(r_restored.status_code == 400
        and (r_restored.get_json() or {}).get("error") == "임계값은 0~100 사이 숫자여야 합니다.",
        "★★★★ 원복 후에는 다시 이 라우트 고유의 안내문으로 정상 방어된다"
        "(바꿔치기가 안 샜다)", r_restored.get_json())

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__}: {e}")

APP_HASH_AFTER = read("app.py")
chk(APP_HASH_AFTER == APP_SRC,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(모듈 속성 직접치환·view_functions 딕셔너리 항목치환만 사용 — "
    "디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
