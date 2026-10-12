# -*- coding: utf-8 -*-
"""[기능] 운영자 「오늘 할 일」 — 회귀.

  왜 만들었나 —
    대시보드는 '얼마나 되나' 를 보여 준다. 그런데 첫 주 운영자가 아침에 알아야
    하는 것은 **'지금 무엇을 눌러야 일이 움직이나'** 다. 지금까지는 그걸 알려면
    메뉴 열둘을 돌며 배지를 눈으로 세야 했다.

  이 화면이 지켜야 할 성질 —
    ① **머리 숫자는 '오늘 반드시' 만 센다.** 처음 만들었을 때 전부 더해 603건이
       나왔고, 그중 398건이 '건설업 등록 조사'(일회성 준비 과제)였다.
       603 은 "오늘은 글렀다" 로만 읽혀 아무 판단도 돕지 못한다.
    ② **0건은 아예 안 보여 준다.** 빈 화면이 곧 "오늘은 없다" 다.
    ③ **각 항목은 왜 문제인지 한 줄로 말한다.** 숫자만 있으면 신입은 못 움직인다.
    ④ **배지와 화면이 같은 숫자를 말한다.** 규칙을 두 벌 쓰면 반드시 갈린다.
    ⑤ **실발송 스위치가 항목의 뜻을 바꾼다.** 대기 195건은 켜져 있으면 '곧 나갈
       것', 꺼져 있으면 '영영 안 나갈 것' 이다.

      python test_feature_ops_today.py
"""
import ast
import io
import os
import re
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


def js_func(src, header):
    """중괄호 균형으로 함수를 뜬다 — 글자수로 자르지 않는다."""
    i = src.find(header)
    if i < 0:
        return ""
    depth, j = 0, src.find("{", i)
    if j < 0:
        return ""
    while j < len(src):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
        j += 1
    return src[i:]


APP, ADM = read("app.py"), read("static/admin.js")
AH = read("templates/admin.html")

print("═" * 70)
print("  기능 회귀 — 운영자 「오늘 할 일」")
print("═" * 70)

print("\n[1] 항목이 '무엇을 하나' 를 말한다")
chk('"/api/ops-today"' in APP, "★ API 가 있다")
for name in ("TODAY_BLOCKED", "TODAY_WAITING", "TODAY_AGING", "TODAY_QUEUE"):
    chk(f"{name} = [" in APP, f"★ 성격별 목록이 있다 — {name}")
#  ★ 각 항목이 (라벨, 왜, 갈곳, SQL) 네 짝인지 — '왜' 가 빠지면 숫자만 남는다
_defs = re.findall(r"^(TODAY_(?:BLOCKED|WAITING|AGING))\s*=\s*\[(.*?)^\]",
                   APP, re.S | re.M)
_nowhy = []
for _nm, _blk in _defs:
    for _m in re.finditer(r'\(\s*"([^"]+)",\s*("(?:[^"\\]|\\.)*")', _blk):
        if _m.group(2) in ('""', "''"):
            _nowhy.append(f"{_nm}:{_m.group(1)}")
chk(not _nowhy,
    "★★ 급한 항목은 **왜 문제인지**를 반드시 적는다",
    f"설명이 빈 항목: {_nowhy} — 숫자만 있으면 신입 운영자는 못 움직인다")

print("\n[2] 머리 숫자는 '오늘 반드시' 만 센다")
_t = func_body(APP, "def api_ops_today")
chk('today_n = g_blocked["n"] + g_waiting["n"]' in _t,
    "★★ 막힘 + 상대가 기다림 **둘만** 더한다",
    "전부 더하면 603건이 나왔고(그중 398이 일회성 등록조사) 그 숫자는 "
    "'오늘은 글렀다' 로만 읽힌다")
chk('"total": today_n' in _t, "★ 응답의 total 이 그 숫자다")
chk('"later"' in _t, "★ 나머지는 '봐 둘 것' 으로 따로 준다")
chk("TODAY_PREP" in APP and '"prep": prep' in _t,
    "★ 일회성 준비 과제는 **머리 숫자 밖**에 둔다",
    "등록조사 398건은 오늘의 행동이 아니라 한 번 끝내는 일이다")
_prep = func_body(APP, "def api_ops_today")
chk('"pct"' in _prep and '"left"' in _prep,
    "★ 준비 과제는 진행률로 — 줄어드는 게 보여야 한다")

print("\n[3] 0건은 안 보여 준다")
_g = func_body(APP, "def _today_group")
chk("if n > 0:" in _g,
    "★★ 0건 항목은 목록에 넣지 않는다",
    "0 이 잔뜩 찍힌 목록은 아무것도 말하지 않는다")
chk('"clear": (today_n == 0' in _t,
    "★ 할 일이 없으면 그렇다고 **말한다**",
    "빈 화면은 고장과 구별되지 않는다")
chk("지금 손댈 일이 없습니다" in ADM, "★ 화면에 그 문장이 있다")

print("\n[4] 배지와 화면이 같은 숫자를 말한다")
_u = func_body(APP, "def _today_urgent_n")
chk("TODAY_BLOCKED + TODAY_WAITING" in _u,
    "★★ 배지가 **화면과 같은 정의**를 쓴다",
    "규칙을 두 벌 쓰면 배지 12 · 화면 9 처럼 갈린다")
chk('"today_urgent": today_urgent' in APP,
    "★ 이미 30초마다 도는 /api/stats 에 실어 보낸다(새 호출을 만들지 않는다)")
chk("setBadge('bdg-today', s.today_urgent)" in ADM,
    "★ 화면이 그 값을 배지에 쓴다")
chk('id="bdg-today"' in AH, "★ 메뉴에 배지 자리가 있다")

print("\n[5] 실발송 상태가 항목의 뜻을 바꾼다")
chk("NOTIFY_ENABLED and POPBILL.ready()" in _t,
    "★ 발송 설정 API 와 **같은 판정식**을 쓴다",
    "두 곳이 다른 답을 내면 화면이 갈린다")
chk("실발송이 꺼져 있어 이 건들은 나가지 않습니다" in _t,
    "★★ 꺼져 있을 때 '곧 나간다' 고 말하지 않는다")
chk("아직 안 읽은 알림" in _t,
    "★ 꺼져 있으면 **전화해야 할 상대**를 센다",
    "문자가 안 나가는 동안에는 포털을 여는 사람만 안다")
_comm = _t[_t.find("if not live:"):]
chk("read_at IS NULL" in _comm,
    "★ '안 읽음' 은 read_at 으로 판정한다")

print("\n[6] 첫 화면이다")
chk("loadView('today')" in ADM and "loadView('dash');" not in ADM,
    "★★ 콘솔을 켜면 오늘 치가 먼저 보인다",
    "열어 봐야 의미가 있는 게 아니라 열자마자 보여야 의미가 있다")
_i_today = AH.find('data-v="today"')
_i_dash = AH.find('data-v="dash"')
chk(0 < _i_today < _i_dash,
    "★ 메뉴에서도 대시보드보다 앞에 있다")

print("\n[7] 한 항목이 깨져도 화면 전체가 죽지 않는다")
chk("except sqlite3.Error" in _g and "app.logger.exception" in _g,
    "★ 실패한 항목은 건너뛰되 **로그에 남긴다**",
    "조용히 0 으로 만들면 '오늘 할 일 없음' 이라는 거짓말이 된다")

print("\n[8] 화면이 서버가 준 것만 그린다")
_v = js_func(ADM, "VIEWS.today = async ()")
chk("d.groups||[]" in _v, "★ 그룹을 서버에서 받는다(화면이 규칙을 다시 쓰지 않는다)")
chk("catch(e)" in _v, "★ 못 불러오면 그 사실을 말한다")
chk("d.prep" in _v, "★ 준비 과제를 따로 그린다")
chk("data-act=\"loadView\"" in _v, "★ 행을 누르면 그 화면으로 간다")

print("")
print("\n[+] 마감이 다가오는데 입찰이 0건 — 유찰 전에 뜬다")
#  ⚠ 공고를 여는 순간의 '참여 업체 0곳' 경보는 이미 있었다. 빈틈은 그 뒤였다 —
#    부를 업체는 있었는데 아무도 안 들어온 채 마감만 다가오는 경우. 그대로 두면
#    마감이 돌아 유찰이 되고, 피해자는 아무 일도 없이 이틀을 잃는다.
_i0 = APP.find('_LIVE = "COALESCE(is_demo,0)=0"')
_j0 = APP.find("def _today_urgent_n")
_ns0 = {}
#  ⚠ 이 구간(TODAY_*)이 CASE_OPEN_SQL(모듈 앞쪽에서 정의)을 참조한다(라운드59:
#    종결상태 목록 드리프트를 여기 한 곳으로 통합) — 떼어 온 조각만 실행하면
#    그 이름이 없어 NameError 가 난다. 정의 줄만 실제 소스에서 그대로 가져와
#    먼저 실행한다(값을 여기 다시 손으로 적으면 그게 또 다른 드리프트가 된다).
_co0 = APP.find("CASE_OPEN_SQL = ")
exec(compile(APP[_co0:APP.find("\n", _co0)], "<case_open>", "exec"), _ns0)  # noqa: S102
exec(compile(APP[_i0:_j0], "<today2>", "exec"), _ns0)          # noqa: S102 — 우리 소스다
#  ⚠ 이름을 **정확히** 맞춘다. 부분일치로 집었더니 '입찰이 0건으로 유찰됐습니다'
#    라는 다른 항목이 먼저 잡혀 엉뚱한 것을 검사했다.
_lbl0 = "마감이 다가오는데 입찰이 0건입니다"
_lbl1 = "입찰 마감이 12시간 안에 닥칩니다"
_names_b = [it[0] for it in _ns0["TODAY_BLOCKED"]]
_names_a = [it[0] for it in _ns0["TODAY_AGING"]]
chk(_lbl0 in _names_b, "★★ '입찰 0건' 이 **막힘**(첫 화면)에 있다", _names_b)
chk(_lbl1 in _names_a, "★ '마감 임박' 은 나중에 목록에 있다")
_q0 = next(it[3] for it in _ns0["TODAY_BLOCKED"] if it[0] == _lbl0)
_q1 = next(it[3] for it in _ns0["TODAY_AGING"] if it[0] == _lbl1)
chk("voided_at IS NULL" in _q0,
    "★★ 무효 처리된 입찰은 세지 않는다",
    "재공고로 무효가 된 입찰까지 세면 '입찰 있음' 으로 오판해 급한 건이 목록에서 빠진다")
chk("voided_at IS NULL" in _q1, "★ 마감 임박 쪽도 같은 기준으로 센다")
chk("= 0" in _q0.replace(" ", " ") and "> 0" in _q1,
    "★★ 두 항목이 서로 배타적이다(같은 공고가 두 번 뜨지 않는다)")

#  ── 실제로 세어 본다 ────────────────────────────────────────
import sqlite3 as _sq2                                     # noqa: E402
import tempfile as _tf2                                    # noqa: E402
import shutil as _sh2                                      # noqa: E402
_td2 = _tf2.mkdtemp(prefix="zerobid_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_td2, "zb.db")
sys.path.insert(0, HERE)
try:
    import db as _db2
    #  ⚠ db 는 **import 시점에** DB_PATH 를 읽는다. 앞 블록이 먼저 import 했으면
    #    환경변수만 바꿔도 옛 경로를 그대로 쓴다 — 모듈 값을 직접 갈아 준다.
    _db2.DB_PATH = os.environ["BOKGUON_DB_PATH"]
    _db2.init_db()
    _c2 = _sq2.connect(os.environ["BOKGUON_DB_PATH"])

    def _mk(tag, n, voided=False):
        cid = _c2.execute(
            "INSERT INTO cases (case_no,category,region,status,is_demo,created_at) "
            " VALUES (?,?,?,?,0,datetime('now','+9 hours'))",
            (f"ZB-{tag}", "가드레일", "서울", "공고중")).lastrowid
        aid = _c2.execute(
            "INSERT INTO auctions (case_id,status,deadline) "
            " VALUES (?,'진행',datetime('now','+9 hours','+6 hours'))", (cid,)).lastrowid
        for k in range(n):
            _c2.execute(
                "INSERT INTO bids (auction_id,partner_name,amount,created_at,voided_at) "
                " VALUES (?,?,?,datetime('now','+9 hours'),?)",
                (aid, "검증", 100000 + k, "2026-01-01" if voided else None))

    _mk("none", 0); _mk("has", 2); _mk("void", 2, voided=True)
    _n0 = _c2.execute(_q0).fetchone()[0]
    _n1 = _c2.execute(_q1).fetchone()[0]
    _c2.close()
    chk(_n0 == 2, "★★ 무입찰 1건 + 전부무효 1건 = 2건으로 잡힌다", _n0)
    chk(_n1 == 1, "★★ 마감 임박에는 입찰 있는 1건만 잡힌다", _n1)
except Exception as _e:                                    # noqa: BLE001
    chk(False, "★★ 입찰 0건 판정 실측", f"{type(_e).__name__} {_e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    _sh2.rmtree(_td2, ignore_errors=True)

print("\n[+] 지급 검수 — 입금 전 건은 검수 대상이 아니다")
#  왜 (2026-08-19 실측) —
#    "지급 검수가 밀려 있습니다" 항목이 review_status='대기' 만 보고
#    insurer_paid(입금 여부)를 안 물었다. 그런데 대시보드 배지(지급_검수대기)와
#    자동 리마인드(sweep_review_reminders)는 **둘 다** insurer_paid='입금완료' 를
#    요구한다 — "두 사람이 확인해야 이체가 열립니다" 라는 설명 자체가 이체 전
#    마지막 관문이라는 뜻인데, 입금 자체가 안 된 건까지 그 관문에 걸린 것처럼
#    셌다. 실측: 그때 review_status='대기' 19건이 **전부** insurer_paid='대기' 였다
#    — 즉 "밀린 검수"가 0건인데 화면은 19건이라 말했다. 바로 아래 있는
#    「발주처 입금이 확인되지 않았습니다」와 같은 19건을 두 번 보여 준 것이기도 하다.
_qpay = next(it[3] for it in _ns0["TODAY_QUEUE"] if it[0] == "지급 검수가 밀려 있습니다")
chk("insurer_paid='입금완료'" in _qpay.replace(" ", ""),
    "★★ 입금완료 건만 '지급 검수' 로 센다", _qpay)
_td3 = _tf2.mkdtemp(prefix="payrev_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_td3, "pr.db")
try:
    _db2.DB_PATH = os.environ["BOKGUON_DB_PATH"]
    _db2.init_db()
    _c3 = _sq2.connect(os.environ["BOKGUON_DB_PATH"])
    _c3.execute(
        "INSERT INTO cases (case_no,category,region,status,is_demo,created_at) "
        " VALUES ('PR-1','가드레일','서울','완료',0,datetime('now','+9 hours'))")
    _c3.execute(
        "INSERT INTO settlements (case_id,review_status,insurer_paid,is_demo,created_at) "
        " VALUES (1,'대기','대기',0,datetime('now','+9 hours'))")
    chk(_c3.execute(_qpay).fetchone()[0] == 0,
        "★★ 입금 전이면 '지급 검수' 대기열에 없다(0건)",
        "이게 19로 나오면 되살아난 것이다 — 아무것도 못 누르는 항목을 다시 밀린 일처럼 보여준다")
    _c3.execute(
        "INSERT INTO settlements (case_id,review_status,insurer_paid,is_demo,created_at) "
        " VALUES (1,'대기','입금완료',0,datetime('now','+9 hours'))")
    chk(_c3.execute(_qpay).fetchone()[0] == 1,
        "★ 입금완료 건은 그대로 잡힌다 (과잉 차단이 아니다)")
    _c3.close()
except Exception as _e:                                    # noqa: BLE001
    chk(False, "★★ 지급 검수 전제조건 실측", f"{type(_e).__name__} {_e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    _sh2.rmtree(_td3, ignore_errors=True)

_rn = func_body(APP, "def api_case_renotify")
chk(bool(_rn), "★ 다시 알리기 라우트가 있다")
chk("이미 마감된 공고입니다" in _rn,
    "★★ 마감된 공고에는 다시 알리지 않는다",
    "들어와도 투찰이 막혀 업체는 헛걸음을 하고 우리를 못 믿게 된다")
chk("-30 minutes" in _rn, "★★ 30분 안 재발송을 막는다(알림이 소음이 되면 아예 꺼 버린다)")
#  ⚠ 주석·docstring 을 지우고 본다. 안 지우면 **"특정 업체를 부르지 않는다" 는
#    안전장치 문구 자체**가 금칙어로 걸린다 — 이 프로젝트에서 네 번째 겪는 실수다.
_rn_code = re.sub(r'"""[\s\S]*?"""', " ", _rn)
_rn_code = "\n".join(l for l in _rn_code.splitlines() if not l.strip().startswith("#"))
chk("partner_id=" not in _rn_code,
    "★ 특정 업체를 지목하지 않는다(철칙 7)",
    "알림은 전체 협력사에게만 나가야 한다")
chk('audience_type="all-partner"' in _rn_code, "★ 대상이 협력사 전체다")
chk("award" not in _rn_code.lower(), "★ 낙찰을 정하지 않는다(철칙 5)")
chk("UPDATE" not in _rn_code.upper() or "amount" not in _rn_code,
    "★ 금액을 바꾸지 않는다(철칙 1)")
chk('DB.log(conn, actor(), "공고 재알림"' in _rn, "★ 감사 로그에 남는다")
chk(len(re.findall(r"ACT\.caseRenotify\s*=", ADM)) == 1, "★ 화면 핸들러가 한 번 등록된다")
chk('data-act="caseRenotify"' in ADM, "★ 버튼이 있다")

print("\n[+] 깨진 항목을 **숨기지 않는다**")
#  ⚠ 예전엔 `except sqlite3.Error: continue` 로 건너뛰어, 깨진 항목이 화면에서
#    통째로 사라졌다. 0건도 아니고 아예 없는 항목이 되어 '그런 일이 없다' 와
#    '못 셌다' 가 구분되지 않았다. 실제로 그 상태로 운영에 배포됐다.
#    여기서는 **일부러 깨진 질의를 넣어** 그 사실이 항목으로 올라오는지 본다.
import sqlite3 as _sq                                     # noqa: E402
_g_src = APP[APP.find("def _today_group"):APP.find("@app.get(\"/api/ops-today\")")]
_ns2 = {"sqlite3": _sq,
        "app": type("A", (), {"logger": type("L", (), {"exception": staticmethod(
            lambda *a, **k: None)})()})()}
try:
    exec(compile(_g_src, "<group>", "exec"), _ns2)         # noqa: S102 — 우리 소스다
    _c2 = _sq.connect(":memory:")
    _c2.execute("CREATE TABLE cases (id INTEGER, status TEXT)")
    _c2.execute("INSERT INTO cases VALUES (1,'접수')")
    _defs = [("멀쩡한 항목", "설명", "#cases", "SELECT COUNT(*) FROM cases"),
             ("깨진 항목", "설명", "#cases", "SELECT COUNT(*) FROM cases WHERE nosuchcol=1")]
    _res = _ns2["_today_group"](_c2, _defs, "k", "제목", "red")
    _c2.close()
    _labels = [i["label"] for i in _res["items"]]
    chk("깨진 항목" in _labels, "★★ 셀 수 없는 항목이 목록에서 사라지지 않는다",
        f"올라온 항목: {_labels}")
    _bi = next((i for i in _res["items"] if i["label"] == "깨진 항목"), {})
    chk(_bi.get("broken") is True, "★ 깨졌다는 표시가 붙는다", _bi)
    chk(_bi.get("n") is None, "★★ 0 으로 위장하지 않는다(건수가 없음으로 온다)", _bi.get("n"))
    chk("0이 아닐 수 있습니다" in (_bi.get("why") or ""),
        "★ 실제 건수가 0이 아닐 수 있다고 말한다")
    chk(_res["n"] == 1, "★ 합계에는 셀 수 있었던 것만 넣는다", _res["n"])
    chk(_res.get("broken") == 1, "★ 몇 개가 깨졌는지 함께 준다", _res.get("broken"))
    chk(_labels[0] == "깨진 항목", "★ 깨진 항목을 위에 올린다(눈에 띄어야 고친다)", _labels)
except Exception as _e:                                    # noqa: BLE001
    chk(False, "★★ 깨진 항목 처리 검사", f"{type(_e).__name__} {_e}")

_tc_js = js_func(ADM, "function todayCard")
chk("it.broken" in _tc_js, "★ 화면이 깨진 항목을 다르게 그린다")
chk("집계 실패" in _tc_js, "★★ 화면에 '집계 실패' 라고 쓴다")

print("\n[+] 모든 항목의 질의가 **실제 스키마에서 돈다**")
#  ⚠⚠ 이 검사가 없어서 결함이 운영까지 갔다.
#     `change_orders` 에 `is_demo` 를 붙였는데 그 컬럼은 **cases 에만** 있다.
#     화면 코드가 `except sqlite3.Error` 로 그 오류를 삼키기 때문에
#     항목이 0건으로 뜨는 것도 아니고 **아예 사라졌다** — 눈으로는 알 수 없다.
#     위쪽 검사들은 전부 소스 **문자열**만 봤다. 그래서 전부 통과했다.
#     문자열이 맞는 것과 질의가 도는 것은 다르다 — 이제 진짜로 실행해 본다.
import sqlite3                                            # noqa: E402
import tempfile                                           # noqa: E402

_tmpdir = tempfile.mkdtemp(prefix="today_sql_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "schema_probe.db")
sys.path.insert(0, HERE)
_qerr, _qn = [], 0
try:
    import db as _db
    _db.DB_PATH = os.environ["BOKGUON_DB_PATH"]           # 같은 이유로 직접 갈아 준다
    _db.init_db()
    #  app.py 를 import 하지 않는다(최상위 DB.init_db() 가 돈다) — 정의 구간만 떼어 실행
    _i = APP.find('_LIVE = "COALESCE(is_demo,0)=0"')
    _j = APP.find("def _today_urgent_n")
    _ns = {}
    #  ⚠ CASE_OPEN_SQL 참조 추가(라운드59) — 정의 줄만 먼저 떼어 실행해 둔다.
    _co1 = APP.find("CASE_OPEN_SQL = ")
    exec(compile(APP[_co1:APP.find("\n", _co1)], "<case_open>", "exec"), _ns)  # noqa: S102
    exec(compile(APP[_i:_j], "<today-defs>", "exec"), _ns)  # noqa: S102 — 우리 소스다
    _c = sqlite3.connect(os.environ["BOKGUON_DB_PATH"])
    for _g in ("TODAY_BLOCKED", "TODAY_WAITING", "TODAY_AGING",
               "TODAY_QUEUE", "TODAY_PREP"):
        for _it in _ns[_g]:
            for _sql in _it[3:]:          # PREP 는 질의가 둘이다(남은 것 / 전체)
                _qn += 1
                try:
                    _c.execute(_sql).fetchone()
                except sqlite3.Error as _e:
                    _qerr.append(f"[{_g}] {_it[0]} → {_e}")
    _c.close()
except Exception as _e:                                   # noqa: BLE001
    _qerr.append(f"검사 자체가 실패: {type(_e).__name__} {_e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    import shutil                                         # noqa: E402
    shutil.rmtree(_tmpdir, ignore_errors=True)

chk(_qn >= 18, f"질의를 {_qn}개 뽑아 실행했다",
    "0개면 정의 구간 앵커가 어긋난 것이다 — 아무것도 검사하지 않는다")
chk(not _qerr, "★★ 모든 질의가 실제 스키마에서 돈다", " / ".join(_qerr[:3]))

print("")
try:
    ast.parse(APP); _ok, _why = True, ""
except SyntaxError as e:
    _ok, _why = False, f"{e.lineno}행: {e.msg}"
chk(_ok, "app.py 구문", _why)
chk(AH.count("<div") == AH.count("</div>"),
    "admin.html div 균형", f"{AH.count('<div')} / {AH.count('</div>')}")

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
