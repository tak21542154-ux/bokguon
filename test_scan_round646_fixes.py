# -*- coding: utf-8 -*-
"""스캔 646라운드 회귀(직접조사, 하위위임 없음) — dispatch.py의 _setting_int()가
   범위 밖 저장값을 app.py의 동명 형제 함수와 다르게 처리하던 결함.

   조사 배경 — settings 정수값을 읽는 헬퍼 _setting_int(conn, key, default, lo, hi)
   는 순환 임포트를 피하려고 app.py(4112행)와 dispatch.py(78행) 두 곳에 각자
   존재한다. 이 저장소는 이런 "형제 함수"를 이미 두 번 명시적으로 다뤘다 —
   _like_escape()·_norm_dot()는 둘 다 "app.py 의 동명 함수와 반드시 같은 규칙을
   유지한다"는 주석을 달고 실제로 바이트 단위로 동일한 몸통을 유지해 왔다.
   그런데 _setting_int()에는 그런 동기화 주석이 전혀 없었고, 실제로 동작이
   갈라져 있었다:

     · app.py 판(4112행) — 저장값이 [lo,hi] 범위 밖이면 조용히 default 로
       되돌린다("범위 밖은 전부 기본값으로 되돌린다", 함수 자신의 독스트링).
       파싱도 int(float(x))라 "30.0"류 문자열도 허용한다. round485 가 이미
       'inf' 같은 값의 OverflowError까지 막아 놨다.
     · dispatch.py 판(78행, 이번 라운드 이전) — 범위 밖 값을
       max(lo, min(hi, v))로 **경계값에 밀어 넣었다**(clamp). 파싱도
       int(str(x))라 "30.0" 같은 문자열은 ValueError로 조용히 default 로
       떨어졌다(우연히 안 죽었을 뿐 app.py 와 다른 결과).

   dispatch.py 판에는 round 태그가 단 하나도 없었다 — 이 저장소가 스스로
   세운 "형제 함수 동기화" 관례(round75가 세운 stTag 동기화, round499가
   _norm_dot 에 붙인 것과 같은 부류)의 적용 대상에서 이 함수만 지금까지
   빠져 있었다는 뜻이다.

   지금 유일한 저장 경로(api_settings_set, RANGES={"dispatch_minutes":(5,240),
   "dispatch_fanout":(1,200), "dispatch_max_round":(1,10)})는 저장 시점에
   이미 이 폭을 강제하므로 정상 화면 조작으로는 재현되지 않는다 — 하지만
   그 검증을 거치지 않는 경로(수기 DB 수정, 스키마 마이그레이션, 훗날 새
   저장 경로가 이 검증 없이 추가되는 경우)로 값이 깨지면, 이 함수 혼자
   형제(app.py 판)와 다른 결과를 낸다: dispatch_minutes 가 999로 깨지면
   app.py 스타일은 안전한 기본값 30분으로 되돌아가는데, dispatch.py는
   경계값 240분(4시간)을 실제 출동 제한시간으로 그대로 써 버린다 — 아무도
   설정한 적 없는 값이 조용히 운영값이 된다.

   고침 — dispatch.py:_setting_int() 를 app.py 판과 동일한 계약(범위 밖은
   default, int(float(x)) 파싱, OverflowError 포함 예외 처리)으로 맞추고,
   두 함수가 반드시 같이 가야 한다는 동기화 주석을 남긴다.

   회귀테스트(이 파일) —
   [1] 소스 — dispatch.py 의 _setting_int() 몸통에 옛 clamp 표현
       (max(lo, min(hi, v)))이 더는 없고, "범위 밖은 전부 기본값" 계약이
       독스트링에 명시됐는지 확인한다.
   [2] 단위 — 실제 dispatch 모듈을 스크래치 DB로 임포트해 settings 테이블에
       범위 밖 값(dispatch_minutes=999)을 직접 넣고 dispatch.dispatch_minutes()
       를 실제로 호출 — 결과가 경계값(240)이 아니라 기본값(30)임을 실측한다.
       "30.0" 같은 소수점 문자열도 app.py 판처럼 파싱되는지 함께 확인한다.
   [3] 되돌리기 — 실제 파일은 건드리지 않고, [1]에서 읽은 (지금 고친)
       dispatch.py 소스 문자열 안에서 _setting_int() 함수 하나만 옛 버전으로
       치환한 독립 네임스페이스를 만들어, 그 옛 버전이 실제로 999 를
       240(경계값)으로 클램프함을 재현 실측한다(이 테스트가 실제로 회귀를
       잡아낼 힘이 있음을 증명).
   [4] 형제일치 — app.py 의 _setting_int() 도 같은 스크래치 DB·같은 깨진
       입력으로 실제 호출해, 이제 dispatch.py 판과 app.py 판이 같은 default
       복귀 결과를 낸다는 것(형제 동기화가 실제로 성립함)을 실측한다.

       python test_scan_round646_fixes.py
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


def func_src(src, header, end_marker="\n\n\n"):
    """header(예: 'def _setting_int(')부터 다음 최상위 빈 줄 둘까지 — 이 저장소
    함수들은 전부 그 사이에 몸통이 끝난다(들여쓰기 0인 다음 def 앞)."""
    i = src.find(header)
    if i < 0:
        return ""
    j = src.find(end_marker, i)
    return src[i:j] if j >= 0 else src[i:i + 2000]


print("=" * 72)
print("  스캔 646라운드 회귀 — dispatch.py _setting_int() clamp vs default 불일치")
print("=" * 72)

DISPATCH_SRC = read("dispatch.py")
APP_SRC = read("app.py")

# ============================================================
print("\n[1] 소스 확인 — dispatch.py _setting_int() 몸통에서 옛 clamp 표현 제거 확인")
# ------------------------------------------------------------
NEW_FN = func_src(DISPATCH_SRC, "def _setting_int(conn, key, default, lo, hi):")
chk(bool(NEW_FN), "  dispatch.py 에서 _setting_int() 정의를 찾았다", f"len={len(NEW_FN)}")
chk("return max(lo, min(hi, v))" not in NEW_FN,
    "★★★★★ dispatch.py _setting_int() 의 실행문에 옛 clamp 표현"
    "(return max(lo, min(hi, v)))이 더는 없다(주석 속 인용은 별개)")
chk("int(float(r[0]))" in NEW_FN,
    "  dispatch.py _setting_int() 가 app.py 판과 같은 int(float(x)) 파싱을 쓴다")
chk("if lo <= v <= hi:" in NEW_FN and "return default" in NEW_FN,
    "★★★★★ dispatch.py _setting_int() 가 '범위 밖이면 default' 계약을 실제로 담고 있다")
chk("OverflowError" in NEW_FN,
    "  dispatch.py _setting_int() 가 round485 급 OverflowError 방어도 함께 갖췄다")
chk("app.py 의 동명 함수" in NEW_FN or "app.py의 동명 함수" in NEW_FN,
    "  형제 동기화 주석이 실제로 붙었다(다음 라운드가 다시 놓치지 않도록)")

APP_FN = func_src(APP_SRC, "def _setting_int(conn, key, default, lo, hi):")
chk(bool(APP_FN), "  (전제) app.py 에도 여전히 _setting_int() 가 있다 — 대조군 성립",
    f"len={len(APP_FN)}")

# ============================================================
print("\n[2] 단위 — 스크래치 DB에 범위 밖 값을 직접 넣고 실제 dispatch 모듈로 호출")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round646_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "verify.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB  # noqa: E402
DB.init_db()
import dispatch as DP  # noqa: E402

conn = DB.get_db()


def set_raw(key, value):
    conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))
    conn.commit()


# 정상 상태(설정 없음) — 여전히 기본값이어야 한다(회귀 없음 확인)
conn.execute("DELETE FROM settings WHERE key IN "
             "('dispatch_minutes','dispatch_fanout','dispatch_max_round')")
conn.commit()
chk(DP.dispatch_minutes(conn) == 30,
    "  (회귀 없음) 설정이 아예 없으면 여전히 기본값 30분", DP.dispatch_minutes(conn))
chk(DP.dispatch_fanout(conn) == 20,
    "  (회귀 없음) 설정이 아예 없으면 여전히 기본값 20곳", DP.dispatch_fanout(conn))

# api_settings_set 의 RANGES 검증을 거치지 않고(수기 DB 수정을 흉내) 범위 밖 값을 직접 넣는다
set_raw("dispatch_minutes", "999")     # 유효범위 5~240 밖
chk(DP.dispatch_minutes(conn) == 30,
    "★★★★★ dispatch_minutes 저장값이 999(범위 5~240 밖)면 경계값 240이 아니라 "
    "기본값 30을 돌려준다", DP.dispatch_minutes(conn))

set_raw("dispatch_fanout", "0")        # 유효범위 1~200 밖(하한 미달)
chk(DP.dispatch_fanout(conn) == 20,
    "★★★★★ dispatch_fanout 저장값이 0(범위 1~200 밖)이면 경계값 1이 아니라 "
    "기본값 20을 돌려준다", DP.dispatch_fanout(conn))

set_raw("dispatch_max_round", "50")    # 유효범위 1~10 밖
chk(DP.dispatch_max_round(conn) == 3,
    "★★★★★ dispatch_max_round 저장값이 50(범위 1~10 밖)이면 경계값 10이 아니라 "
    "기본값 3을 돌려준다", DP.dispatch_max_round(conn))

# app.py 판처럼 "30.0" 같은 소수점 문자열도 파싱돼야 한다
set_raw("dispatch_minutes", "45.0")
chk(DP.dispatch_minutes(conn) == 45,
    "  dispatch_minutes 저장값이 '45.0'(소수점 문자열)이어도 45로 정상 파싱된다"
    "(app.py 판과 같은 int(float(x)) 파싱)", DP.dispatch_minutes(conn))

# 정상 범위 안 값은 그대로 통과해야 한다(회귀 없음)
set_raw("dispatch_minutes", "60")
chk(DP.dispatch_minutes(conn) == 60,
    "  (회귀 없음) 범위 안 값(60)은 그대로 60을 돌려준다", DP.dispatch_minutes(conn))

conn.execute("DELETE FROM settings WHERE key IN "
             "('dispatch_minutes','dispatch_fanout','dispatch_max_round')")
conn.commit()

# ============================================================
print("\n[3] 되돌리기 — 실제 파일은 무변경, 메모리 안에서만 옛 clamp 버전을 재구성해 재현")
# ------------------------------------------------------------
OLD_FN_BODY = (
    "def _setting_int(conn, key, default, lo, hi):\n"
    "    try:\n"
    "        r = conn.execute(\"SELECT value FROM settings WHERE key=?\", (key,)).fetchone()\n"
    "        v = int(str(r[0]).strip()) if r and str(r[0]).strip() else default\n"
    "    except (sqlite3.Error, TypeError, ValueError):\n"
    "        return default\n"
    "    return max(lo, min(hi, v))\n"
)
chk("max(lo, min(hi, v))" in OLD_FN_BODY,
    "  (전제) 되돌린 소스 문자열이 실제로 옛 clamp 표현을 담고 있다(실제 파일은 안 건드림)")

import sqlite3  # noqa: E402
_ns = {"sqlite3": sqlite3}
exec(compile(OLD_FN_BODY, "<round646-reverted:_setting_int>", "exec"), _ns)
old_setting_int = _ns["_setting_int"]

set_raw("dispatch_minutes", "999")
old_result = old_setting_int(conn, "dispatch_minutes", 30, 5, 240)
chk(old_result == 240,
    "★★★★★★ (인과관계 실측) 되돌린 옛 코드는 999를 경계값 240으로 클램프한다 "
    "— 지금 코드(위 [2], 결과=30)와 정반대 = 이번 수정이 실제로 이 불일치를 없앤 것",
    f"옛 코드 결과={old_result}")

new_result = DP._setting_int(conn, "dispatch_minutes", 30, 5, 240)
chk(new_result == 30 and old_result != new_result,
    "  지금 코드(DP._setting_int, 실제 파일)는 같은 입력에 30을 돌려준다"
    "(옛 코드=240 과 실제로 다르다)", f"new={new_result} old={old_result}")

conn.execute("DELETE FROM settings WHERE key = 'dispatch_minutes'")
conn.commit()

# ============================================================
print("\n[4] 형제일치 — app.py 의 _setting_int() 도 같은 깨진 입력에 같은 결과를 내는지 실측")
# ------------------------------------------------------------
import app as A  # noqa: E402

set_raw("dispatch_minutes", "999")
app_result = A._setting_int(conn, "dispatch_minutes", 30, 5, 240)
dispatch_result = DP._setting_int(conn, "dispatch_minutes", 30, 5, 240)
chk(app_result == dispatch_result == 30,
    "★★★★★★ app.py._setting_int() 와 dispatch.py._setting_int() 가 이제 같은 "
    "깨진 입력(999, 범위 5~240 밖)에 완전히 같은 결과(30)를 낸다(형제 동기화 성립)",
    f"app={app_result} dispatch={dispatch_result}")

conn.execute("DELETE FROM settings WHERE key = 'dispatch_minutes'")
conn.commit()
conn.close()

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
