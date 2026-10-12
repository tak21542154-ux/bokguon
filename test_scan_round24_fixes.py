# -*- coding: utf-8 -*-
"""24라운드 회귀 — **NULL 과 0 을 헷갈린 자리, 그리고 나가는 문이 없는 상태.**

  ① 같은 대시보드 응답 안에서 '이 사건은 얼마짜리인가' 를 두 기준으로 셌다.
       · 파이프라인·공종별 : `CASE WHEN low_price>0 THEN low_price ELSE est_price END`
                             (확정가 award_amount 를 아예 안 본다)
       · WIP·발주처별·하자 : `COALESCE(award_amount, low_price, est_price)`
     그리고 두 번째 식에는 **NULL/0 혼동**이 있었다. COALESCE 는 NULL 만 건너뛰는데
     `low_price` 의 기본값은 **0**(NULL 이 아니다) 이라, 입찰이 한 건도 안 들어온
     사건은 거기서 멈춰 0원이 됐다.
       실측(운영 DB): 유찰 3건이 0원으로 잡혀 진행중 공사금액이
       2억6,969만 → 2억3,316만 으로 **3,652만원 적게** 나왔다.

  ② 변경견적이 '거절'·'유찰' 에 갇혔다. 나가는 문은 전체재경매 하나뿐인데 그
     라우트가 사건 상태를 ('시공중','완료보고지연')로 제한한다. 사건이 '검수대기' 로
     넘어가면 그 변경건은 영원히 활성으로 남아 **새 증액 요청까지 막는다**.
     철회 라우트의 docstring 이 스스로 "나가는 문이 하나뿐이라 catch-22" 라고 적어 둔
     바로 그 문제가, 한 상태 뒤에 그대로 남아 있었다.

      python test_scan_round24_fixes.py
"""
import ast
import io
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    try:
        return io.open(os.path.join(HERE, rel), encoding="utf-8").read()
    except OSError as e:
        return f"<<읽기실패 {e}>>"


def func_body(src, header):
    i = src.find(header)
    if i < 0:
        return ""
    j = len(src)
    for pat in ("\ndef ", "\n@app."):
        k = src.find(pat, i + len(header))
        if 0 < k < j:
            j = k
    return src[i:j]


def strip_py(t):
    """`#` 주석과 docstring 을 지운다 — 안 그러면 **안전장치 문장 자체**가 잡힌다."""
    t = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', " ", t)
    return "\n".join(ln for ln in t.splitlines() if not ln.strip().startswith("#"))


APP = read("app.py")
_S = strip_py(APP)

print("═" * 70)
print("  24라운드 회귀 — NULL/0 혼동 · 갇힌 변경건")
print("═" * 70)

# ── ① ────────────────────────────────────────────────────────
print("\n[1] '이 사건은 얼마짜리인가' 를 한 곳에서 정한다")
chk(APP.count("CASE_AMOUNT_SQL = (") == 1, "★ 판정 상수가 하나만 있다")
_m = re.search(r"CASE_AMOUNT_SQL = \((.*?)\)\n", APP, re.S)
_expr = (_m.group(1) if _m else "").replace("\n", " ")
chk("NULLIF(award_amount,0)" in _expr,
    "★★ 확정가를 **먼저** 본다(0 이면 없는 것으로)")
chk("NULLIF(low_price,0)" in _expr,
    "★★ low_price 를 NULLIF 로 감싼다",
    "COALESCE 는 NULL 만 건너뛴다. low_price 기본값은 0 이라 NULL 이 아니어서, "
    "입찰 0건 사건이 거기서 멈춰 **0원**이 됐다(실측 3건 · 3,652만원)")
chk(_expr.index("award_amount") < _expr.index("low_price") < _expr.index("est_price"),
    "★ 우선순위가 확정가 → 현재 최저가 → 가견적 이다")

#  ★★ 옛 식이 **한 곳도** 남지 않았다 — 형제를 다시 갈라놓지 않는다
_old = [ln.strip()[:80] for ln in _S.splitlines()
        if "COALESCE(award_amount, low_price, est_price)" in ln
        or "CASE WHEN low_price>0 THEN low_price ELSE est_price END" in ln]
chk(not _old, "★★ 옛 금액 식이 한 곳도 남지 않았다", str(_old))

#  ⚠ 여기서는 **strip_py 를 쓰지 않는다.** 그 함수는 삼중따옴표 블록을 지우는데,
#    이 프로젝트의 SQL 이 바로 `f"""…"""` 삼중따옴표다 — 지우면 검사 대상이 사라져
#    4곳을 2곳으로 잘못 센다(실제로 그렇게 헛돌았다). 코드 존재 여부를 보는
#    검사이므로 원문 그대로 센다.
_dash = func_body(APP, "def api_dashboard")
_n_dash = _dash.count("{CASE_AMOUNT_SQL}")
chk(_n_dash >= 4,
    f"★ 대시보드가 그 상수를 쓴다 ({_n_dash}곳)",
    "파이프라인·WIP·발주처별·공종별 네 자리가 같은 규칙을 써야 한 화면이 "
    "같은 말을 한다")
chk(APP.count("{CASE_AMOUNT_SQL}") >= 5,
    f"★ 대시보드 밖(하자 목록)에서도 같은 규칙을 쓴다 "
    f"(총 {APP.count('{CASE_AMOUNT_SQL}')}곳)")

#  ★ SQL 이 실제로 도는가 — 문자열만 보면 오타를 못 잡는다
_db = os.environ.get("BOKGUON_DB_PATH") or os.path.join(HERE, "bokguon.db")
if os.path.exists(_db) and _expr:
    try:
        _c = sqlite3.connect(f"file:{_db}?mode=ro", uri=True)
        #  ⚠ 손으로 따옴표를 떼면 **암묵적 문자열 이어붙이기**에서 반드시 깨진다
        #    (처음에 그렇게 했다가 `near "COALESCE": syntax error` 를 봤다).
        #    파이썬 문법으로 읽는다 — 그게 실제 값이다.
        _sql = ast.literal_eval(f"({_expr})")
        _n = _c.execute(f"SELECT COUNT(*) FROM cases WHERE ({_sql}) IS NULL").fetchone()[0]
        _neg = _c.execute(f"SELECT COUNT(*) FROM cases WHERE ({_sql}) < 0").fetchone()[0]
        _zero = _c.execute(
            f"SELECT COUNT(*) FROM cases WHERE ({_sql})=0 AND COALESCE(est_price,0)>0"
        ).fetchone()[0]
        _c.close()
        chk(_n == 0, f"★ 실제 DB 에서 NULL 이 안 나온다 ({_n}건)")
        chk(_neg == 0, f"★ 음수가 안 나온다 ({_neg}건)")
        chk(_zero == 0,
            f"★★ **가견적이 있는데 0원으로 사라지는 사건이 없다** ({_zero}건)",
            "이게 바로 옛 WIP 식이 3건을 삼키던 자리다")
    except sqlite3.Error as e:
        chk(False, "금액 식 실행", f"{type(e).__name__}: {e}")
else:
    print("  [건너뜀] DB 가 없어 실행 확인은 못 했다 —", _db)

# ── ② ────────────────────────────────────────────────────────
print("\n[2] 막다른 변경건에 나가는 문이 있다")
_wd = func_body(APP, "def api_co_withdraw")
_wdS = strip_py(_wd)
chk("status IN ('실사요청','거절','유찰')" in _wdS,
    "★★ '거절'·'유찰' 에서도 철회할 수 있다",
    "그 두 상태에서 나가는 문은 전체재경매 하나뿐인데, 그 라우트가 사건 상태를 "
    "('시공중','완료보고지연')로 제한한다 — 사건이 '검수대기' 로 넘어가면 "
    "변경건이 영원히 활성으로 남아 새 증액 요청까지 막는다")
for _bad in ("'추가경매중'", "'전체재경매중'"):
    chk(_bad not in _wdS.split("status IN (")[1].split(")")[0] if "status IN (" in _wdS else True,
        f"★ 경매가 열린 상태({_bad})는 받지 않는다",
        "협력사가 이미 투찰했을 수 있다 — 되돌리는 절차가 따로 있다")
chk("유찰 처리로 닫아 주세요" in _wd,
    "★ 막힐 때 **무엇을 해야 하는지** 말한다")
chk("len(reason) < 5" in _wdS,
    "★ 되돌리기 어려운 처리라 사유를 요구한다(감사 근거)")

#  ★ 중복 금지 조건과 짝이 맞는가 — 철회한 건은 '살아 있는 것' 에서 빠져야 한다
chk("'철회'" in _S and _S.count("status NOT IN ('수락확정','최종유찰','낙찰확정','철회')") >= 2,
    "★ 철회된 건은 '진행 중' 으로 세지 않는다(새 증액 요청이 열린다)")

print("")
try:
    ast.parse(APP); _ok, _why = True, ""
except SyntaxError as e:
    _ok, _why = False, f"{e.lineno}행: {e.msg}"
chk(_ok, "app.py 구문", _why)

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
