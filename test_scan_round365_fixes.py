# -*- coding: utf-8 -*-
"""스캔 365라운드 회귀 — app.py:_bid_weights()(입찰 다속성 점수의 가중치
   로더)가 설정값에 무한대 문자열('inf')이 들어오면 그 값을 그대로 받아들여
   전체 가중치를 NaN 으로 오염시키던 결함[경미, 방어적 정합성 — 현재 이
   설정키(bid_w_price 등 5개)는 /api/settings 의 SETTABLE(19905행)에 아예
   없어 정상 화면으로는 설정 불가능하고 DB에도 값이 없다(실측 확인) —
   그래도 이 함수 자신의 독스트링("설정값이 있으면 그것을... 합이 1이
   되도록 정규화")이 언젠가 admin이 이 값을 바꿀 수 있게 될 것을 전제하고
   있어, 그날을 위해 지금 고쳐 둔다].

  ⚠ 조사 Agent가 위협모델을 정확히 실측으로 확인한 사례 — "SQL 직접
    접근만 위험"이라고 스스로 한계를 밝혔다(과장 없음, 8번째 관찰
    '파급범위과장'류가 아님). 다만 그 정도 접근권한(DB 파일 직접 쓰기)이면
    이 값 하나 고치는 것보다 훨씬 큰일(award_amount 직접조작 등)을 이미
    할 수 있어 보안결함이라기보다 **입력 파싱의 정합성 결함**으로 분류한다.

  근본원인: Python 의 `float()` 는 "inf"/"Infinity"/"-inf" 문자열을 관용적
  으로 그대로 파싱한다(표준 라이브러리 동작, 실수 아님). 10488행의 기존
  검사 `v >= 0` 는 음수만 걸렀지 `float('inf') >= 0` 은 True 라 통과시켰다
  — 그 뒤 정규화(`total = sum(w.values())`, `v/total`)에서 다른 유효한
  키들은 `finite/inf=0.0` 으로 죽고, inf 를 받은 그 키 자신은 `inf/inf=nan`
  이 된다(IEEE754 정의상 부정형). 이 nan 은 `_bid_scores()`(10496행)의
  `parts` 합산에 그대로 번져 입찰 점수 전체를 nan 으로 만들고, Flask
  jsonify 는 기본설정(allow_nan=True, 커스텀 JSON provider 없음— 확인함)
  이라 그 nan 이 스펙 밖의 bare `NaN` 토큰으로 그대로 HTTP 응답에 실린다
  (브라우저 표준 JSON.parse 는 이를 파싱 못 해 전체 입찰목록 로딩이 깨질
  수 있다 — 조사 Agent가 말한 "'nan' 텍스트 노출"보다 더 심할 수 있는
  경로이나, 이번 수정은 원인(파싱)을 막아 이 경로 자체가 발생하지 않게
  하므로 실제 jsonify 직렬화까지 확인할 필요는 없다). 음수·비수치(예:
  'nan' 문자열 자체, `float('nan') >= 0` 이 이미 False)·`-inf`(마찬가지로
  `>= 0` 이 False)는 고치기 전에도 이미 안전했다 — 이번에 새로 막은 것은
  **양의 무한대뿐**이다.

  고침: `math` 모듈을 새로 import 하고, 10488행의 조건에
  `and math.isfinite(v)` 를 추가 — 무한대·NaN 을 모두 배제한다(NaN 은
  기존 `>=0` 검사가 이미 걸렀지만 의도를 명시적으로 드러내 다음 사람이
  또 헷갈리지 않도록 함수 하나로 통일).

      python test_scan_round365_fixes.py
"""
import io
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 365라운드 회귀 — 가중치 설정에 'inf' 가 들어오면 NaN 으로 오염되던 결함")
print("=" * 72)

print("\n[0] 전제 재확인 — 이 설정키는 정말 정상화면으로 설정 불가능한가")
chk('"bid_w_' not in APP_SRC[APP_SRC.index("SETTABLE = set(RANGES)"):
                             APP_SRC.index("SETTABLE = set(RANGES)") + 300],
    "★★★ SETTABLE 목록(19905행 부근)에 bid_w_* 키가 없다 — /api/settings 로 설정 불가")
chk("import math" in APP_SRC, "★ app.py 최상단에 import math 가 추가됐다")

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index("def _bid_weights(conn):")
i1 = APP_SRC.index("\ndef _bid_scores(", i0)
fn_body = APP_SRC[i0:i1]
chk("math.isfinite(v)" in fn_body,
    "★★★★★ _bid_weights() 가 math.isfinite() 로 무한대·NaN 을 배제한다")

# ============================================================
print("\n[2] 실행 — 실제 _bid_weights()/BID_WEIGHT_DEFAULT 를 그대로 실행(exec 격리)")
# ------------------------------------------------------------
i_default = APP_SRC.index("BID_WEIGHT_DEFAULT = {")
fn_src = APP_SRC[i_default:i1].rstrip()


def _mkdb():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);")
    return conn


def _one(cur):
    r = cur.fetchone()
    return dict(r) if r else None


try:
    ns = {"sqlite3": sqlite3, "math": __import__("math"), "one": _one}
    exec(compile(fn_src, "<bid_weights>", "exec"), ns)  # noqa: S102 -- 우리 소스, 실제 함수를 그대로 실행
    _weights = ns["_bid_weights"]
    DEFAULT = ns["BID_WEIGHT_DEFAULT"]

    #  실측 재현 — bid_w_price 에 문자 그대로 'inf' 가 박히면(재현 경위:
    #  SQL 직접 접근, 조사 Agent가 확인) 정규화 전체가 오염돼야 한다(고치기 전)
    conn = _mkdb()
    conn.execute("INSERT INTO settings(key,value) VALUES ('bid_w_price','inf')")
    conn.commit()
    w = _weights(conn)
    chk(all(not (w[k] != w[k]) for k in w),  # v!=v ⇔ NaN (표준 관용구, math 모듈 불필요)
        "★★★★★ 'inf' 가 들어와도 어떤 가중치도 NaN이 되면 안 된다"
        "(고치기 전엔 price=inf/inf=nan, 나머지는 finite/inf=0.0 으로 전부 오염됐다)",
        w)
    chk(abs(sum(w.values()) - 1.0) < 1e-9,
        "★★★ 가중치 합은 여전히 1.0 이어야 한다('inf' 는 무시되고 기본값들만으로 정규화)", w)
    chk(w == DEFAULT,
        "★★ 무효값 하나만 있고 나머지 4개는 미설정이므로 결과가 정확히 BID_WEIGHT_DEFAULT 와 같아야 한다"
        "(기본값 5개의 합이 이미 1.00 이라 정규화해도 그대로)", (w, DEFAULT))
    conn.close()

    #  회귀 없음 — 정상적인 유효 override(합 안 맞아도 정규화는 여전히 동작)
    conn = _mkdb()
    conn.execute("INSERT INTO settings(key,value) VALUES ('bid_w_price','0.9')")
    conn.commit()
    w2 = _weights(conn)
    expect_total = 0.9 + 0.15 + 0.15 + 0.10 + 0.10
    chk(abs(w2["price"] - 0.9 / expect_total) < 1e-9,
        "★ 회귀없음 — 유효한 override(0.9)는 여전히 정상적으로 받아들여져 비율대로 정규화된다", w2)

    #  이미 안전했던 것 재확인 — 음수·NaN 문자열·-inf 는 고치기 전에도 이미 걸렸다(대조군)
    for bad, label in (("-5", "음수"), ("nan", "NaN 문자열"), ("-inf", "음의 무한대")):
        conn = _mkdb()
        conn.execute("INSERT INTO settings(key,value) VALUES ('bid_w_price',?)", (bad,))
        conn.commit()
        w3 = _weights(conn)
        chk(w3 == DEFAULT, f"  대조군 — {label}('{bad}')은 이번 수정 전에도 이미 기본값으로 안전하게 무시됐다", w3)
        conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행(_bid_weights 격리실행)", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
