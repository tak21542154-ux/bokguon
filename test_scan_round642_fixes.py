# -*- coding: utf-8 -*-
"""스캔 642라운드 회귀(직접조사, 하위위임 없음) — templates/dispatch_report.html
   "2-1. 호출 이력" 요약문의 "가장 가까운 업체" 계산이 거리 0.0km 를
   "없음"으로 걸러내던 결함.

   조사 배경 — dispatch_calls.dist_km 는 dispatch.py:447 에서
   `round(dkm, 1)` 로 저장된다. 협력사가 사고 현장에서 50m 이내(대형
   단지·산업단지 등에서 드물지 않다)이면 반올림 결과가 정확히 0.0 이 된다.
   그런데 dispatch_report.html:111(수정 전)의
     {% set near = calls|selectattr('dist_km')|map(attribute='dist_km')|list %}
   은 Jinja2 selectattr() 에 테스트를 안 주면 **진리값 검사**로 동작한다
   (공식 문서: "If no test is specified, the attribute's value will be
   evaluated as a boolean" — 실측: Template("{{ [{'d':0.0}]|selectattr('d')
   |list }}").render() == "[]"). 즉 dist_km=0.0 인 호출은 목록에서
   통째로 사라진다 — 바로 세 줄 뒤(122행, 표의 개별 행)는
   `{% if k.dist_km is not none %}` 로 0 과 None 을 정확히 구분하는데,
   요약문만 그 원칙을 놓치고 있었다. 같은 파일 195행 자신의 주석
   ("0 은 '무보증'이라는 유효한 값이다 — or 는 0 도 걸러 24로 둔갑시킨다")이
   바로 이 부류의 함정을 이미 경계하고 있었다 — 그런데 몇 줄 위
   selectattr() 자리에는 적용되지 않은 채 남아 있었다.

   실제 영향 — 이 보고서는 보험사에 그대로 넘기는 "소명을 위한 전체
   기록"이다(107행 자신의 문구). 호출 중 하나가 0.0km(가장 가까운 곳)면:
     · 다른 호출도 있으면 → 실제로는 0.0km 가 최솟값인데 그보다 먼 값을
       "가장 가까운 업체" 거리로 잘못 표시한다.
     · 호출이 그 한 건뿐이면 → 거리를 알면서도 "거리 미상"으로 표시한다
       (0.0 이 selectattr 에서 전부 걸러져 near 가 빈 리스트가 됨).
   운영 DB(bokguon.db, 읽기전용 SELECT)를 직접 조회한 결과 현재
   dispatch_calls.dist_km=0.0 인 행은 0건(전체 74건 중)이었다 — 아직
   실제로 드러나지는 않았지만, round(dkm,1) 특성상 반경 50m 이내
   협력사가 생기면 즉시 재현되는 잠재 결함이다.

   고침(templates/dispatch_report.html, 111행→116행) —
   `selectattr('dist_km')` 를 `selectattr('dist_km', 'ne', none)` 로
   바꿔 None 만 제외하고 0.0 은 그대로 남긴다(122행이 이미 쓰는 것과
   같은 구분 원칙을 요약문에도 적용). 판정 로직 한 줄만 바꿨고 새 필드·
   새 컬럼은 만들지 않았다. 5줄짜리 설명 주석{# #}을 함께 남겼다
   (렌더링에는 영향 없음 — 아래 [3]에서 실측 확인).

   회귀테스트(이 파일) —
   [1] 소스: 고친 표현이 실제 파일에 있고 옛 표현(테스트 없는 단독
       selectattr('dist_km'))은 더는 없음을 확인. templates/ 전체에서
       테스트 없는 selectattr 이 이곳 말고 더 없는지도 전수 확인(형제
       사각지대 감사).
   [2] 단위 — Jinja2 자체 동작으로 옛 표현과 새 표현의 차이를 직접
       실행해 증명(소스 문자열 비교가 아니라 실제 템플릿 렌더 결과).
       옛 표현은 [0.0]→빈 리스트, [0.0,3.2]→[3.2](0.0 누락)를 내고,
       새 표현은 [0.0]→[0.0], [0.0,3.2]→[0.0,3.2]를 낸다.
   [3] 종단 — 스크래치 DB + 실제 Flask 라우트(GET /report/dispatch/<cid>)
       + 지금 고쳐진 실제 템플릿 파일로 세 시나리오를 재현: (a) 0.0km
       호출 1건뿐 → "0.0km"가 나오고 "거리 미상"이 안 나옴, (b) 0.0km +
       3.2km 혼재 → 최솟값 "0.0km"가 나오고 "가장 가까운 업체" 요약
       자리에 "3.2km"가 나오지 않음, (c) 전부 좌표 없음(dist_km=None) →
       회귀 없이 여전히 "거리 미상"이 나옴.
   [4] 되돌리기 — 실제 파일은 전혀 건드리지 않고, 옛 표현만 독립된
       Jinja2 Environment 문자열 템플릿으로 재구성해 [3](a)와 같은
       calls 데이터를 넣으면 "거리 미상"이 나옴을 실측 — 인과관계 직접
       증명.

       python test_scan_round642_fixes.py
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


print("=" * 72)
print("  스캔 642라운드 회귀 — dispatch_report '가장 가까운 업체' 0km 누락 결함")
print("=" * 72)

TPL_PATH = os.path.join(HERE, "templates", "dispatch_report.html")
TPL_SRC = read("templates/dispatch_report.html")

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
FIXED = "calls|selectattr('dist_km', 'ne', none)|map(attribute='dist_km')|list"
OLD_BUGGY = "calls|selectattr('dist_km')|map(attribute='dist_km')|list"
chk(TPL_SRC.count(FIXED) == 1,
    "★★★★★ 고친 표현(selectattr('dist_km', 'ne', none))이 정확히 한 곳에 있다")
chk(OLD_BUGGY not in TPL_SRC,
    "★★★★★ 옛(버그) 표현이 더는 파일에 없다")

# 형제 사각지대 감사 — templates/ 전체에서 테스트 없는 selectattr(단일 인자)이
# 이 파일 말고 더 없는지 확인한다. equalto 등 명시적 테스트가 있는 자리는 제외.
# ⚠ Jinja 주석({# #}, 이번 수정 자체가 옛 표현을 설명하려고 그 문자열을 그대로
#   인용해 남겼다)은 먼저 지운다 — 실행되지 않는 산문까지 "위험한 실코드"로
#   오탐하면 감사 자체가 무의미해진다.
import re as _re  # noqa: E402
_TPL_DIR = os.path.join(HERE, "templates")
_bare_selectattr_hits = []
for _fn in os.listdir(_TPL_DIR):
    if not _fn.endswith(".html"):
        continue
    _src = io.open(os.path.join(_TPL_DIR, _fn), encoding="utf-8").read()
    _src = _re.sub(r"\{#.*?#\}", "", _src, flags=_re.DOTALL)
    for _m in _re.finditer(r"selectattr\(([^)]*)\)", _src):
        _args = _m.group(1)
        # 인자가 단 하나(따옴표로 감싼 속성명 하나)뿐이면 진리값 검사(버그 소지) —
        # 콤마가 있으면(테스트명 지정) 안전하다.
        if "," not in _args:
            _bare_selectattr_hits.append((_fn, _m.group(0)))
chk(_bare_selectattr_hits == [],
    "★★★★ templates/ 전수 — 테스트 없는 단독 selectattr()가 이제 하나도 없다"
    "(같은 부류의 falsy-zero 함정이 다른 곳에 남아 있지 않음)",
    _bare_selectattr_hits)

# ============================================================
print("\n[2] 단위 — Jinja2 실제 렌더로 옛/새 표현의 차이를 직접 증명")
# ------------------------------------------------------------
from jinja2 import Environment  # noqa: E402

env = Environment()
old_tpl = env.from_string(
    "{{ (calls|selectattr('dist_km')|map(attribute='dist_km')|list) }}")
new_tpl = env.from_string(
    "{{ (calls|selectattr('dist_km', 'ne', none)|map(attribute='dist_km')|list) }}")

cases = [
    ([{"dist_km": 0.0}], "[]", "[0.0]"),
    ([{"dist_km": 0.0}, {"dist_km": 3.2}], "[3.2]", "[0.0, 3.2]"),
    ([{"dist_km": None}, {"dist_km": 2.5}], "[2.5]", "[2.5]"),
    ([{"dist_km": None}], "[]", "[]"),
    ([], "[]", "[]"),
]
for calls, want_old, want_new in cases:
    got_old = old_tpl.render(calls=calls)
    got_new = new_tpl.render(calls=calls)
    chk(got_old == want_old,
        f"  (전제) 옛 표현이 실측대로 결함을 재현한다 — calls={calls}",
        f"got={got_old!r} want={want_old!r}")
    chk(got_new == want_new,
        f"★★★★★ 새 표현이 0.0 을 잃지 않고 올바르게 남긴다 — calls={calls}",
        f"got={got_new!r} want={want_new!r}")

# ============================================================
print("\n[3] 종단 실행 — 실제 Flask 라우트 + 지금 고쳐진 실제 템플릿 파일")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round642_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB  # noqa: E402
DB.init_db()
import app as A  # noqa: E402

conn = DB.get_db()
conn.execute("INSERT INTO admins(username,password_hash,name,role) "
             "VALUES('r642admin','x','검증','최고관리자')")


def _mk_case(no):
    conn.execute(
        "INSERT INTO cases(case_no, insurer, category, region, status, est_price, "
        "urgent, is_demo, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (no, "테스트보험사", "가드레일", "서울", "완료", 2000000, 0, 0, DB.now()))
    return conn.execute("SELECT id FROM cases WHERE case_no=?", (no,)).fetchone()["id"]


def _mk_dispatch(cid, rn=1):
    cur = conn.execute(
        "INSERT INTO dispatches(case_id, round, status, created_at) VALUES(?,?,?,?)",
        (cid, rn, "모집중", DB.now()))
    return cur.lastrowid


def _mk_call(did, pid, name, dist_km, order):
    conn.execute(
        "INSERT INTO dispatch_calls(dispatch_id, partner_id, partner_name, dist_km, "
        "call_order, notified_at, created_at) VALUES(?,?,?,?,?,?,?)",
        (did, pid, name, dist_km, order, DB.now(), DB.now()))


# (a) 호출이 0.0km 하나뿐 — 옛 코드라면 "거리 미상"으로 잘못 표시됐을 사례
cid_a = _mk_case("R642-CASE-A")
did_a = _mk_dispatch(cid_a)
_mk_call(did_a, 9001, "바로옆업체", 0.0, 1)

# (b) 0.0km + 3.2km 혼재 — 옛 코드라면 0.0을 놓치고 "3.2km"를 최솟값으로 오표시
cid_b = _mk_case("R642-CASE-B")
did_b = _mk_dispatch(cid_b)
_mk_call(did_b, 9002, "가까운업체", 0.0, 1)
_mk_call(did_b, 9003, "먼업체", 3.2, 2)

# (c) 전부 좌표 없음(dist_km=None) — 회귀 없이 "거리 미상"이 나와야 한다
cid_c = _mk_case("R642-CASE-C")
did_c = _mk_dispatch(cid_c)
_mk_call(did_c, 9004, "좌표없는업체", None, 1)

conn.commit()
conn.close()

client = A.app.test_client()
with client.session_transaction() as sess:
    sess["admin"] = "r642admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"


def _near_snippet(html):
    i = html.index("가장 가까운 업체")
    return html[i:i + 140]


resp_a = client.get(f"/report/dispatch/{cid_a}")
chk(resp_a.status_code == 200, "  (a) GET dispatch_report 가 200을 낸다", resp_a.status_code)
snip_a = _near_snippet(resp_a.get_data(as_text=True))
chk("0.0km" in snip_a,
    "★★★★★★ (a) 호출이 0.0km 하나뿐이어도 '가장 가까운 업체'에 0.0km가 나온다",
    snip_a)
chk("거리 미상" not in snip_a,
    "★★★★★★ (a) 더는 '거리 미상'으로 오표시되지 않는다(핵심 결함 재현 지점)",
    snip_a)

resp_b = client.get(f"/report/dispatch/{cid_b}")
chk(resp_b.status_code == 200, "  (b) GET dispatch_report 가 200을 낸다", resp_b.status_code)
snip_b = _near_snippet(resp_b.get_data(as_text=True))
chk("0.0km" in snip_b,
    "★★★★★★ (b) 0.0km + 3.2km 혼재 시 최솟값 0.0km가 '가장 가까운 업체'에 나온다",
    snip_b)
chk("3.2km" not in snip_b,
    "★★★★★★ (b) 실제 최솟값이 아닌 3.2km가 요약 자리에 나오지 않는다(옛 코드였다면 "
    "여기 3.2km가 나왔을 것)",
    snip_b)

resp_c = client.get(f"/report/dispatch/{cid_c}")
chk(resp_c.status_code == 200, "  (c) GET dispatch_report 가 200을 낸다", resp_c.status_code)
snip_c = _near_snippet(resp_c.get_data(as_text=True))
chk("거리 미상" in snip_c,
    "  (c) 회귀 없음 — 좌표 없는 호출만 있으면 여전히 '거리 미상'이 나온다", snip_c)

# ============================================================
print("\n[4] 되돌리기 — 옛 표현만 독립 템플릿으로 재구성(실제 파일은 무변경)")
# ------------------------------------------------------------
#  ⚠ templates/dispatch_report.html 은 절대 건드리지 않는다. [1]에서 이미 확인한
#    옛(버그) 표현 문자열을 그대로 독립된 Jinja2 문자열 템플릿에 넣어, [3](a)와
#    똑같은 calls 데이터(0.0km 하나뿐)를 먹였을 때 "거리 미상"이 나오는지만 본다.
_old_full = env.from_string(
    "가장 가까운 업체 "
    "{% set near = calls|selectattr('dist_km')|map(attribute='dist_km')|list %}"
    "{% if near %}{{ '%.1f'|format(near|min) }}km{% else %}거리 미상{% endif %}")
_old_out_a = _old_full.render(calls=[{"dist_km": 0.0}])
chk(_old_out_a == "가장 가까운 업체 거리 미상",
    "★★★★★★ (인과관계 실측) 옛 표현 그대로라면 (a) 시나리오에서 '거리 미상'이 "
    "나왔다 — 위 [3](a)의 실제(고쳐진) 결과와 정반대", _old_out_a)
_old_out_b = _old_full.render(calls=[{"dist_km": 0.0}, {"dist_km": 3.2}])
chk(_old_out_b == "가장 가까운 업체 3.2km",
    "★★★★★★ (인과관계 실측) 옛 표현 그대로라면 (b) 시나리오에서 '3.2km'를 최솟값"
    "으로 오표시했다 — 위 [3](b)의 실제(고쳐진) 결과와 다르다", _old_out_b)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
