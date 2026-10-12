# -*- coding: utf-8 -*-
"""스캔 423라운드 회귀 — CSV/엑셀 수식삽입(탭 우회) + parse_days() OverflowError
   미스캐치 + api_lead_update() note 미스트립, 3건.

   정밀조사 Agent 발견(각도1: CSV/엑셀 내보내기 수식삽입, 각도2: 입찰 amount/
   days 숫자 경계검증):

   [1] `_xl_safe()`(app.py:13082)·정산CSV 내부 `_csv_safe()`(app.py:12972)
       둘 다 제어문자 필터에서 탭(\t)을 의도적으로 보존하는데, 수식주입 트리거
       판정(`v[:1] in ("=","+","-","@")`)은 그 탭을 고려하지 않는다 — 값이
       "\t=1+1" 처럼 탭으로 시작하면 트리거 문자가 "=" 가 아니라 "\t" 라서
       보호용 `'` 접두가 안 붙는다. 실제 도달 경로: `api_lead_update()`
       (app.py:7266-)의 note 갱신만 형제 자유텍스트 필드들과 달리 `.strip()`
       이 빠져 있어, 탭으로 시작하는 note 가 그대로 저장 → `EXPORT_SECTIONS
       ["leads"]`(app.py:9274, note AS 메모) → `api_export_xlsx()` → `_cell()`
       → `_xl_safe()` 로 흘러간다.
   [2] `parse_days()`(app.py:444)는 `parse_money()`와 달리 문자열화 없이
       `int(value or 0)` 을 직접 적용하는데, JSON 요청 바디의 `Infinity`/
       `-Infinity`(파이썬 표준 json 모듈이 관례적으로 허용하는 리터럴 —
       `flask.json.provider.DefaultJSONProvider` 는 parse_constant 를
       오버라이드하지 않아 그대로 통과)가 `float('inf')` 로 파싱되면
       `int(float('inf'))` 는 `ValueError` 가 아니라 `OverflowError` 를 내고,
       기존 `except (TypeError, ValueError):` 가 이를 못 잡아 그대로 위로
       전파된다(서버 크래시는 아님 — 전역 핸들러가 일반 500으로 감싸지만,
       원래 나가야 할 400+안내메시지 대신 의미 없는 500이 나간다).

   고침: (a) `_xl_safe`/`_csv_safe` 트리거 문자 집합에 "\t" 추가(형제 둘 다),
   (b) `api_lead_update()`의 note 대입에 `.strip()` 추가(형제 필드들과 통일),
   (c) `parse_days()`의 except 튜플에 `OverflowError` 추가. 셋 다 기존 정상
   입력의 반환값을 바꾸지 않는 순수 방어 확장.

       python test_scan_round423_fixes.py
"""
import io
import os
import sys
import tempfile
import textwrap

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
print("  스캔 423라운드 회귀 — 수식주입 탭우회 + parse_days OverflowError")
print("=" * 72)

print("\n[1] 소스 확인")
#  ⚠⚠ [라운드599] 이 자리는 원래 "_xl_safe()·_csv_safe() 둘 다 트리거 집합이
#    같다"(리터럴이 2번 나온다)를 확인했다. round599가 api_settlements_export
#    안의 로컬 _csv_safe() 재구현을 없애고(round221과 같은 근본원인 — 셀
#    정제를 독자 재구현하면서 이번엔 트리거가 아니라 제어문자 보존범위가
#    갈라졌었다) 공유 _xl_safe() 를 직접 쓰게 했으므로, 이 리터럴은 이제
#    _xl_safe() 안에 1번만 있는 게 맞다 — "둘 다 같다"는 원래 취지는 아래
#    _se 델리게이션 확인(같은 객체를 그대로 쓰므로 자동으로 같다)이 이어받는다.
chk(APP_SRC.count('"=", "+", "-", "@", "\\t"') == 1,
    "★★★★★ 트리거 문자 집합 리터럴은 이제 _xl_safe() 안에 1번뿐이다"
    "(round599가 정산CSV의 로컬 사본을 없애 중복 자체가 사라짐)",
    APP_SRC.count('"=", "+", "-", "@", "\\t"'))
_se_i0 = APP_SRC.index("\ndef api_settlements_export(")
_se_i1 = APP_SRC.find("\ndef ", _se_i0 + 1)
_se_body = APP_SRC[_se_i0:_se_i1 if _se_i1 != -1 else None]
chk("_xl_safe(x) for x in" in _se_body and "def _csv_safe" not in _se_body,
    "★★★★★ api_settlements_export() 가 로컬 사본 없이 _xl_safe() 를 직접 써서"
    " 같은 탭우회 방어를 상속한다(round599)")
#  ⚠⚠ [라운드616] round616이 이 두 자리를 별개 이유(비문자열 JSON 안전성,
#    round601~609 형제결함군)로 _s(d["note"], 500)로 다시 감쌌다 — .strip()
#    자체는 _s() 안에 그대로 있으므로(app.py:1507) 이 라운드(423)가 지키려는
#    불변("탭이 strip()으로 제거된다")은 여전히 참이다. 리터럴만 갱신한다.
chk(APP_SRC.count('_s(d["note"], 500)') == 2,
    "★★★★ api_lead_update()·api_application_update() 둘 다(형제 전수) note 갱신에"
    " .strip() 이 포함된 _s()가 적용됐다(round118 자신의 주석이 이미 이 둘을 형제로 명시)",
    APP_SRC.count('_s(d["note"], 500)'))
_i0 = APP_SRC.index("def parse_days(value")
_i1 = APP_SRC.index("\n\n", _i0)
_days_body = APP_SRC[_i0:_i1]
chk("except (TypeError, ValueError, OverflowError):" in _days_body,
    "★★★★★ parse_days() 가 이제 OverflowError 도 잡는다")

print("\n[2] 실행 — _xl_safe()/_csv_safe() 실제 소스를 그대로 실행(exec 격리)")
try:
    _xi0 = APP_SRC.index("def _xl_safe(v):")
    _xi1 = APP_SRC.index("\ndef ", _xi0 + 1)
    ns_xl = {}
    exec(compile(APP_SRC[_xi0:_xi1], "<_xl_safe>", "exec"), ns_xl)  # noqa: S102 -- 우리 소스
    _xl_safe = ns_xl["_xl_safe"]

    chk(_xl_safe("\t=1+1")[:1] == "'",
        "★★★★★ 탭으로 시작하는 수식주입 값이 이제 방어된다(_xl_safe)", _xl_safe("\t=1+1"))
    chk(_xl_safe("=1+1") == "'=1+1", "  대조군 — 기존 방어(= 로 시작)는 그대로(회귀없음)", _xl_safe("=1+1"))
    chk(_xl_safe("+1+1") == "'+1+1", "  대조군 — 기존 방어(+ 로 시작)는 그대로(회귀없음)", _xl_safe("+1+1"))
    chk(_xl_safe("hello\t세계") == "hello\t세계",
        "  대조군 — 중간의 탭·일반 문자열은 안 바뀐다(회귀없음)", _xl_safe("hello\t세계"))
    chk(_xl_safe(123) == 123, "  대조군 — 문자열이 아니면 그대로 통과(회귀없음)", _xl_safe(123))

    #  ⚠⚠ [라운드599] 여기서 api_settlements_export 안의 로컬 _csv_safe() 를
    #    따로 추출해 같은 탭방어를 다시 확인했었다 — round599가 그 로컬
    #    사본을 없애고(위 [1]의 _se_body 확인 참조) 공유 _xl_safe() 를 직접
    #    쓰게 했으므로, 같은 객체(방금 위에서 이미 탭방어를 확인한 바로 그
    #    _xl_safe)를 그대로 부르는지만 확인하면 충분하다 — 별도 exec 추출은
    #    이제 대상이 없어 항상 ValueError 가 난다.
    chk("_xl_safe(x) for x in" in _se_body,
        "★★★★★ 정산CSV(api_settlements_export)가 방금 검증한 _xl_safe() 를 "
        "그대로 써서 탭우회 방어를 상속한다(round599, 별도 사본 없음)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ _xl_safe 격리실행 / 정산CSV 델리게이션 확인", f"{type(e).__name__} {e}")

print("\n[3] 실행 — parse_days() 실제 소스를 그대로 실행(exec 격리)")
try:
    _mi0 = APP_SRC.index("MAX_DAYS = ")
    fn_src = APP_SRC[_mi0:_i1].rstrip()
    ns_days = {}
    exec(compile(fn_src, "<parse_days>", "exec"), ns_days)  # noqa: S102 -- 우리 소스
    parse_days = ns_days["parse_days"]

    n, err = parse_days(float("inf"))
    chk(err is not None,
        "★★★★★ 공기=Infinity 가 이제 크래시 대신 정상 400 에러로 처리된다", (n, err))
    n, err = parse_days(float("-inf"))
    chk(err is not None,
        "★★★★★ 공기=-Infinity 도 이제 크래시 대신 정상 400 에러로 처리된다", (n, err))
    # 대조군 — round396 이 이미 고정한 경계값 동작은 그대로다(회귀없음)
    n, err = parse_days(0)
    chk(err is not None, "  대조군 — 공기=0 은 이미 있던 대로 거부(회귀없음)", (n, err))
    n, err = parse_days(1)
    chk(n == 1 and err is None, "  대조군 — 경계값 1일은 정상 통과(회귀없음)", (n, err))
    n, err = parse_days(365)
    chk(n == 365 and err is None, "  대조군 — 상한 365일은 정상 통과(회귀없음)", (n, err))
    n, err = parse_days(366)
    chk(err is not None, "  대조군 — 366일(상한초과)은 이미 있던 대로 거부(회귀없음)", (n, err))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ parse_days 격리실행", f"{type(e).__name__} {e}")

print("\n[4] 실행 — api_lead_update() 실제 Flask+DB, 탭포함 note 가 이제 strip 된다")
_tmpdir = tempfile.mkdtemp(prefix="round423_")
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
                 "VALUES('admin','x','검증','중간관리자')")
    conn.execute("INSERT INTO insurer_leads(company,status) VALUES('R423테스트','신규')")
    lid = conn.execute("SELECT id FROM insurer_leads WHERE company='R423테스트'").fetchone()["id"]
    conn.execute("INSERT INTO partner_applications(company,status) VALUES('R423신청테스트','신규')")
    aid = conn.execute(
        "SELECT id FROM partner_applications WHERE company='R423신청테스트'").fetchone()["id"]
    conn.commit()

    admin = A.app.test_client()
    _tok = "r423-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    hdr = {"X-CSRF-Token": _tok}

    r = admin.patch(f"/api/leads/{lid}", headers=hdr, json={"note": "\t=1+1"})
    chk(r.status_code == 200, "  200 응답(회귀없음)", r.status_code)
    stored = conn.execute("SELECT note FROM insurer_leads WHERE id=?", (lid,)).fetchone()["note"]
    chk(stored == "=1+1",
        "★★★★★ 탭이 strip() 으로 제거돼 저장된다(고치기 전엔 탭이 그대로 남았다)", repr(stored))

    r2 = admin.patch(f"/api/applications/{aid}", headers=hdr, json={"note": "\t=1+1"})
    chk(r2.status_code == 200, "  200 응답(회귀없음, 형제 api_application_update)", r2.status_code)
    stored2 = conn.execute(
        "SELECT note FROM partner_applications WHERE id=?", (aid,)).fetchone()["note"]
    chk(stored2 == "=1+1",
        "★★★★★ 형제 api_application_update() 도 탭이 strip() 으로 제거돼 저장된다"
        "(round118 자신의 주석이 이미 형제로 명시했는데 이번 라운드에서 처음 확인된 사각지대)",
        repr(stored2))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행(api_lead_update/api_application_update)", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 되돌리기 — 옛 _xl_safe/_csv_safe 였다면 탭우회가 실제로 안 막혔는가")
# ------------------------------------------------------------
try:
    old_xl_src = APP_SRC[_xi0:_xi1].replace(
        '"=", "+", "-", "@", "\\t"', '"=", "+", "-", "@"')
    chk(old_xl_src != APP_SRC[_xi0:_xi1], "  (준비) 옛 _xl_safe 소스가 실제로 달라졌다")
    ns_old = {}
    exec(compile(old_xl_src, "<old_xl_safe>", "exec"), ns_old)  # noqa: S102
    old_xl_safe = ns_old["_xl_safe"]
    chk(old_xl_safe("\t=1+1") == "\t=1+1",
        "★★★★★ 옛 코드는 탭으로 시작하는 값을 방어하지 못했다(인과관계 직접증명)",
        old_xl_safe("\t=1+1"))

    #  ⚠⚠ [라운드599] api_settlements_export 안의 로컬 _csv_safe() 사본 자체가
    #    없어졌다(위 [2] 참고 — 이제 공유 _xl_safe() 를 직접 쓴다) — 그래서
    #    현재 소스에서 다시 추출해 되돌릴 대상이 없다. 이 자리의 원래 취지
    #    ("이 함수가 한때 탭우회에 취약했다")는, round423 당시 실제로 존재
    #    했던 모양(트리거 집합에서 탭만 뺀 버전 — 제어문자 보존 범위는 그때도
    #    지금 _xl_safe 와 같았다, round599 조사로 재확인됨)을 그대로 재현해
    #    증명한다.
    old_csv_block = (
        "def _csv_safe(v):\n"
        "    if not isinstance(v, str):\n"
        "        return v\n"
        "    v = \"\".join(ch for ch in v if ch == \"\\t\" or ch >= \" \")\n"
        "    return (\"'\" + v) if v[:1] in (\"=\", \"+\", \"-\", \"@\") else v\n"
    )
    ns_old2 = {}
    exec(compile(old_csv_block, "<old_csv_safe_round423_shape>", "exec"), ns_old2)  # noqa: S102
    old_csv_safe = ns_old2["_csv_safe"]
    chk(old_csv_safe("\t=1+1") == "\t=1+1",
        "★★★★★ 이 함수가 round423 이전에 실제로 갖고 있던 모양도 마찬가지로 "
        "탭우회를 막지 못했다(인과관계 직접증명 — round599 이후로는 이 사본 "
        "자체가 없어져 도달 경로 자체가 사라졌다)",
        old_csv_safe("\t=1+1"))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기(_xl_safe/_csv_safe) 실행", f"{type(e).__name__} {e}")

print("\n[6] 되돌리기 — 옛 parse_days 였다면 Infinity 입력이 실제로 크래시했는가")
try:
    old_days_src = fn_src.replace(
        "except (TypeError, ValueError, OverflowError):", "except (TypeError, ValueError):")
    chk(old_days_src != fn_src, "  (준비) 옛 parse_days 소스가 실제로 달라졌다")
    ns_old3 = {}
    exec(compile(old_days_src, "<old_parse_days>", "exec"), ns_old3)  # noqa: S102
    old_parse_days = ns_old3["parse_days"]
    _raised = None
    try:
        old_parse_days(float("inf"))
    except Exception as e2:                                         # noqa: BLE001
        _raised = e2
    chk(isinstance(_raised, OverflowError),
        "★★★★★ 옛 코드는 공기=Infinity 에서 실제로 OverflowError 로 죽었다"
        "(인과관계 직접증명 — 고쳐진 지금은 [3]에서 정상 400으로 처리됨)",
        f"{type(_raised).__name__ if _raised else None}")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기(parse_days) 실행", f"{type(e).__name__} {e}")

print("\n[7] 되돌리기 — 옛 api_lead_update/api_application_update(strip 없음) 였다면"
      " 탭이 DB에 그대로 남았는가")
#  ⚠⚠ [라운드616] 되돌림-증명 기법을 옛 세대(app.py를 실제로 디스크에 써넣고
#    새 서브프로세스를 돌려 재현한 뒤 복원 — write→subprocess→write 사이의
#    창을 다른 세션이 관측하면 충돌한다, round590이 실제로 겪음)에서
#    round488/414/515/610이 확립한 안전패턴으로 이관한다. 두 함수 모두 단일
#    라우트 핸들러라 각자 소스에서 note 대입 한 줄만 "strip 없음"으로 되돌린
#    사본을 exec로 재구성(데코레이터도 다시 입힘)해 A.app.view_functions
#    딕셔너리 항목만 잠깐 치환한다 — 진짜 app.py 파일은 전혀 안 쓴다. [4]가
#    이미 만든 admin/lid/aid 픽스처를 그대로 재사용(새 DB·새 서브프로세스 없음).


def _fn_body(src, fn_name):
    """round488/610이 확립한 추출 — 다음 def뿐 아니라 다음 라우트의 @app.
    데코레이터가 먼저 나오면 거기서 자른다."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


try:
    lu_body2 = _fn_body(APP_SRC, "api_lead_update")
    au_body2 = _fn_body(APP_SRC, "api_application_update")
    chk(lu_body2.count('_s(d["note"], 500)') == 1,
        "  (준비) 되돌리기 대상 텍스트(lead)가 유일하게 식별된다")
    chk(au_body2.count('_s(d["note"], 500)') == 1,
        "  (준비) 되돌리기 대상 텍스트(application)가 유일하게 식별된다")
    #  "strip 없음" 상태로 되돌린다 — round423이 지키려는 불변(strip 유무)만
    #  바꾸고, round616의 관심사(비문자열 안전성)는 이 축과 무관하므로 그대로 둔다.
    old_lu_body = lu_body2.replace('_s(d["note"], 500)', '(d["note"] or "")[:500]', 1)
    old_au_body = au_body2.replace('_s(d["note"], 500)', '(d["note"] or "")[:500]', 1)
    chk(old_lu_body != lu_body2 and old_au_body != au_body2,
        "  (준비) 되돌리기 텍스트가 실제로 달라졌다")

    _ns_lu = dict(vars(A))
    exec(compile(old_lu_body, "<round423_reverted_lead_update>", "exec"), _ns_lu)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_lead_fn = A.require_admin(_ns_lu["api_lead_update"])

    _ns_au = dict(vars(A))
    exec(compile(old_au_body, "<round423_reverted_application_update>", "exec"), _ns_au)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_app_fn = A.require_role("중간관리자")(_ns_au["api_application_update"])

    _orig_lu_view = A.app.view_functions["api_lead_update"]
    _orig_au_view = A.app.view_functions["api_application_update"]
    A.app.view_functions["api_lead_update"] = old_lead_fn
    A.app.view_functions["api_application_update"] = old_app_fn
    try:
        #  ⚠ [4]가 이미 자기 conn을 close() 했다 — 새 커넥션으로 읽는다.
        _conn7 = DB.get_db()
        r3 = admin.patch(f"/api/leads/{lid}", headers=hdr, json={"note": "\t=1+1"})
        stored3 = _conn7.execute(
            "SELECT note FROM insurer_leads WHERE id=?", (lid,)).fetchone()["note"]
        r4 = admin.patch(f"/api/applications/{aid}", headers=hdr, json={"note": "\t=1+1"})
        stored4 = _conn7.execute(
            "SELECT note FROM partner_applications WHERE id=?", (aid,)).fetchone()["note"]
        _conn7.close()
    finally:
        A.app.view_functions["api_lead_update"] = _orig_lu_view
        A.app.view_functions["api_application_update"] = _orig_au_view

    chk(r3.status_code == 200 and stored3 == "\t=1+1",
        "★★★★★ 옛 코드(strip 없음, 실제 파일은 안 건드림)는 탭이 포함된 lead "
        "note 를 그대로 저장한다(인과관계 직접증명)", (r3.status_code, repr(stored3)))
    chk(r4.status_code == 200 and stored4 == "\t=1+1",
        "★★★★★ 옛 코드(strip 없음, 실제 파일은 안 건드림)는 형제 application "
        "note 도 탭이 그대로 저장된다(인과관계 직접증명)", (r4.status_code, repr(stored4)))

    chk(A.app.view_functions["api_lead_update"] is _orig_lu_view
        and A.app.view_functions["api_application_update"] is _orig_au_view,
        "  view_functions가 원래 함수객체로 복원됐다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기(api_lead_update/api_application_update) 실행",
        f"{type(e).__name__} {e}")

APP_HASH_AFTER = io.open(APP_PATH, encoding="utf-8").read()
chk(APP_HASH_AFTER == APP_SRC,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(view_functions 딕셔너리 항목 임시치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
