# -*- coding: utf-8 -*-
"""스캔 643라운드 회귀(직접조사, 하위위임 없음) — 피해자 진행조회 화면
   (templates/track.html, GET /track/<token>)이 '취소'된 사건에서도 진행
   단계표를 그대로 보여주며 "지금 한창 진행 중"이라고 오인시키던 결함.

   조사 배경 — app.py:5419 CASE_CLOSED = ("완료", "취소", "미수선종결") 는
   이 셋을 이미 "더 진행되지 않는 사건"으로 한데 묶어 다룬다. 그 정의 바로
   위 주석(5415~5418행) 자체가 "보험사가 취소한 사건이 진행중 건수·진행중
   공사금액에 영원히 남았다"는 실측 사고를 근거로 든다 — 즉 "취소=더 이상
   진행 아님"을 놓치면 실제 사고가 난다는 사실이 이 코드베이스 자신의
   기록에 이미 있다.

   그런데 피해자용 진행조회 화면(track_page(), app.py:20386)은 그 셋 중
   '미수선종결' 하나만 no_repair 플래그로 걸러 전용 안내 카드를 보여주고
   단계표를 건너뛴다. '취소'는 그 필터에 없어 smap.get('취소', 0)=0 으로
   떨어져 그대로 5단계 진행표의 1단계('접수')가 호박색 '현재' 표시로 켜진
   채 렌더된다 — 바로 옆 배지는 VICTIM_LABEL['취소']="접수 취소"를 보여줘,
   한 화면에 "취소되었다"와 "지금 1/5단계, 한창 진행 중이다"가 동시에
   나타난다.

   실제 도달 가능성 — 사건 접수 시점에 진행조회 링크가 **자동으로**
   발급된다(app.py:4445 "★★ 피해자 진행조회 링크를 접수 시점에 자동으로
   만든다" 주석, issue_track_link() 호출이 _create_case() 안에 있음).
   반면 보험사의 사건 취소(api_insurer_case_cancel, app.py:4786)는 status가
   '접수'·'입찰중'일 때만 허용된다(4813행) — 즉 피해자가 이미 링크를 받은
   *뒤에* 사건이 취소되는 순서가 이 기능의 정상 사용 범위 안에 있다. 취소
   사유가 5자 이상 필수(4802행)로 요구될 만큼 실제로 쓰이는 절차이지,
   데모·이론상의 경로가 아니다.

   고침 —
     app.py track_page() render_template 호출에 cancelled=(c["status"]=="취소")
     추가.
     templates/track.html 의 {% if no_repair %}...{% else %}(단계표) 사이에
     {% elif cancelled %} 가지를 넣어, no_repair 카드와 같은 모양·같은 안내
     문구 톤의 전용 카드("이 접수 건은 취소되었습니다")를 보여주고 단계표는
     건너뛴다. smap·VICTIM_LABEL·STAGES 등 기존 계산은 전혀 건드리지 않았다
     (더 이상 취소 사건 렌더링에 안 쓰일 뿐 남겨 둬도 무해하다).

   회귀테스트(이 파일) —
   [1] 소스 — track_page() 함수 슬라이스 안에 새 cancelled= 인자가 있고,
       templates/track.html 에 새 {% elif cancelled %} 가지와 안내 문구가
       정확히 한 번씩 있다. CASE_CLOSED 전제(취소·미수선종결이 여전히 같이
       묶여 있음)도 함께 확인한다(전제 자체가 나중에 바뀌면 이 결함의 근거도
       바뀌므로).
   [2] 단위 — templates/track.html 에서 실제로 쓰이는 if/elif/else 블록
       원문을 파일에서 그대로 잘라내(손으로 다시 타이핑하지 않음) 독립
       Jinja2 템플릿으로 세 가지 실제 상태값(취소·미수선종결·시공중)을
       넣어 렌더 차이를 직접 실행으로 증명한다.
   [3] 종단 — 스크래치 DB + 실제 Flask 라우트(GET /track/<token>) + 지금
       고쳐진 실제 템플릿 파일로 세 사건을 재현: (a) status='취소' → 취소
       안내 카드가 나오고 단계표(class="stage")는 안 나옴, (b) status=
       '미수선종결' → 기존 안내 카드가 그대로 나옴(회귀 없음), (c) status=
       '시공중' → 단계표가 그대로 나옴(정상 진행 중인 사건까지 안내 카드로
       잘못 빠지지 않음).
   [4] 되돌리기 — 실제 파일은 전혀 건드리지 않고, cancelled 가지가 없던
       옛 구조(no_repair/else 둘뿐)만 독립 문자열 템플릿으로 재구성해 (a)와
       같은 실제 값(cur_stage=0, status="접수 취소")을 넣으면 단계표 1단계가
       호박색 '현재'로 켜진 채 "접수 취소" 배지와 함께 나오는, 바로 그
       모순된 화면이 실제로 재현됨을 실측한다.

       python test_scan_round643_fixes.py
"""
import hashlib
import io
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def func_src(src, header):
    """round253이 확립한 함수경계 슬라이스 — header부터 다음 '@app.'나
    최상위 'def ' 직전까지."""
    i = src.find(header)
    if i < 0:
        return ""
    m = re.search(r"\n(?:@app\.|def )", src[i + len(header):])
    return src[i:i + len(header) + m.start()] if m else src[i:]


print("=" * 72)
print("  스캔 643라운드 회귀 — track.html '취소' 사건 진행표 오표시 결함")
print("=" * 72)

APP_SRC = read("app.py")
TPL_SRC = read("templates/track.html")

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
FN_SRC = func_src(APP_SRC, "def track_page(token):")
chk(FN_SRC != "", "track_page() 함수를 실제로 찾았다")
chk('cancelled=(c["status"] == "취소")' in FN_SRC,
    "★★★★★ track_page() 가 render_template 에 cancelled=(...=='취소') 를 넘긴다",
    FN_SRC[-260:] if FN_SRC else "")

chk(TPL_SRC.count("{% elif cancelled %}") == 1,
    "★★★★★ templates/track.html 에 새 {% elif cancelled %} 가지가 정확히 한 번 있다")
chk(TPL_SRC.count("이 접수 건은 취소되었습니다") == 1,
    "★★★★★ 취소 전용 안내 문구가 정확히 한 번 있다")
# no_repair 가지는 이번 수정으로 건드리지 않았어야 한다
chk(TPL_SRC.count("현장 확인 결과, 수선하지 않는 것으로 정리되었습니다.") == 1,
    "  (회귀 없음) 기존 no_repair 안내 문구는 그대로 한 번 있다")

chk('CASE_CLOSED = ("완료", "취소", "미수선종결")' in APP_SRC,
    "  전제 확인 — CASE_CLOSED 가 여전히 '취소'·'미수선종결'을 같이 묶고 있다"
    "(이 결함의 근거)")

# ============================================================
print("\n[2] 단위 — 실제 파일에서 그대로 잘라낸 if/elif/else 블록을 직접 렌더")
# ------------------------------------------------------------
_start = TPL_SRC.index("{% if no_repair %}")
_end = TPL_SRC.index('<div class="grid">')
REAL_BLOCK = TPL_SRC[_start:_end]
chk("{% elif cancelled %}" in REAL_BLOCK and "{% else %}" in REAL_BLOCK,
    "  (전제) 잘라낸 구간에 세 가지(if/elif/else)가 모두 들어 있다")

from jinja2 import Environment  # noqa: E402
env = Environment()
real_tpl = env.from_string(REAL_BLOCK)

# 실제 route가 넘기는 것과 같은 조합 3가지 — smap/VICTIM_LABEL(app.py)이
# '취소'·'미수선종결'·'시공중'에 대해 실제로 내는 값 그대로.
SCEN = [
    ("취소",    dict(no_repair=False, cancelled=True,  cur_stage=0, status="접수 취소",
                     stages=["접수", "업체 선정", "복구 공사", "검수", "완료"])),
    ("미수선종결", dict(no_repair=True,  cancelled=False, cur_stage=4, status="수선하지 않음",
                     stages=["접수", "업체 선정", "복구 공사", "검수", "완료"])),
    ("시공중",   dict(no_repair=False, cancelled=False, cur_stage=2, status="복구 공사 진행 중",
                     stages=["접수", "업체 선정", "복구 공사", "검수", "완료"])),
]
for label, ctx in SCEN:
    out = real_tpl.render(**ctx)
    has_stage = 'class="stage"' in out
    has_cancel_card = "이 접수 건은 취소되었습니다" in out
    has_norepair_card = "수선하지 않는 것으로 정리" in out
    if label == "취소":
        chk(not has_stage and has_cancel_card and not has_norepair_card,
            f"★★★★★★ status='{label}' → 단계표 없이 취소 안내 카드만 나온다",
            out)
    elif label == "미수선종결":
        chk(not has_stage and has_norepair_card and not has_cancel_card,
            f"  (회귀 없음) status='{label}' → 기존 미수선종결 카드가 그대로 나온다",
            out)
    else:
        chk(has_stage and not has_cancel_card and not has_norepair_card,
            f"  (회귀 없음) status='{label}' → 정상 진행 사건은 여전히 단계표가 나온다",
            out)

# ============================================================
print("\n[3] 종단 실행 — 실제 Flask 라우트 + 지금 고쳐진 실제 템플릿 파일")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round643_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB  # noqa: E402
DB.init_db()
import app as A  # noqa: E402

conn = DB.get_db()


def _mk_tracked_case(no, status, **extra):
    token = f"tok{no.replace('-', '').lower()}1234567890"[:40]
    thash = hashlib.sha256(token.encode()).hexdigest()
    cols = dict(case_no=no, insurer="테스트보험사", category="가드레일", region="서울",
                status=status, est_price=1000000, urgent=0, is_demo=0,
                created_at=DB.now(), track_token=token, track_token_hash=thash,
                track_issued_at=DB.now())
    cols.update(extra)
    names = ",".join(cols.keys())
    qs = ",".join("?" for _ in cols)
    conn.execute(f"INSERT INTO cases({names}) VALUES({qs})", tuple(cols.values()))
    return token


tok_a = _mk_tracked_case("R643-CASE-A", "취소")
tok_b = _mk_tracked_case("R643-CASE-B", "미수선종결")
tok_c = _mk_tracked_case("R643-CASE-C", "시공중")
conn.commit()
conn.close()

client = A.app.test_client()


def _body(html):
    return html.split('<div class="body">', 1)[1].split('<div class="note">', 1)[0]


resp_a = client.get(f"/track/{tok_a}")
chk(resp_a.status_code == 200, "  (a) GET /track/<token> 이 200을 낸다(취소 사건)", resp_a.status_code)
body_a = _body(resp_a.get_data(as_text=True))
chk("이 접수 건은 취소되었습니다" in body_a,
    "★★★★★★ (a) 취소된 사건은 실제 라우트 응답에도 취소 안내 카드가 나온다", body_a[:200])
chk('class="stage"' not in body_a,
    "★★★★★★ (a) 취소된 사건은 더 이상 5단계 진행표를 보여주지 않는다"
    "(핵심 결함 재현 지점 — 옛 코드라면 여기 stage 가 있었을 것)", body_a[:200])

resp_b = client.get(f"/track/{tok_b}")
chk(resp_b.status_code == 200, "  (b) GET /track/<token> 이 200을 낸다(미수선종결 사건)", resp_b.status_code)
body_b = _body(resp_b.get_data(as_text=True))
chk("현장 확인 결과, 수선하지 않는 것으로 정리되었습니다." in body_b,
    "  (b) 회귀 없음 — 미수선종결 사건은 기존 안내 카드가 그대로 나온다", body_b[:200])
chk('class="stage"' not in body_b, "  (b) 회귀 없음 — 미수선종결 사건은 단계표를 안 보여준다(기존 동작)")

resp_c = client.get(f"/track/{tok_c}")
chk(resp_c.status_code == 200, "  (c) GET /track/<token> 이 200을 낸다(시공중 사건)", resp_c.status_code)
body_c = _body(resp_c.get_data(as_text=True))
chk('class="stage"' in body_c,
    "  (c) 회귀 없음 — 정상 진행 중인 사건은 여전히 단계표가 나온다", body_c[:200])
chk("취소되었습니다" not in body_c and "수선하지 않는 것으로" not in body_c,
    "  (c) 회귀 없음 — 정상 진행 사건이 취소·미수선종결 카드로 잘못 빠지지 않는다")

# ============================================================
print("\n[4] 되돌리기 — cancelled 가지가 없던 옛 구조만 독립 템플릿으로 재구성"
      "(실제 파일은 무변경)")
# ------------------------------------------------------------
#  ⚠ templates/track.html 은 절대 건드리지 않는다. [2]에서 잘라낸 실제 블록에서
#    {% elif cancelled %} 가지 전체만 제거해(if/else 두 가지만 남김) 이번
#    라운드 이전 구조를 재구성한다 — 손으로 새로 타이핑하지 않고 실제 원문을
#    그대로 잘라 붙인다.
_elif_start = REAL_BLOCK.index("{% elif cancelled %}")
_else_start = REAL_BLOCK.index("{% else %}")
OLD_BLOCK = REAL_BLOCK[:_elif_start] + REAL_BLOCK[_else_start:]
chk("cancelled" not in OLD_BLOCK,
    "  (전제) 되돌린 블록에는 cancelled 가지 흔적이 전혀 없다")

old_tpl = env.from_string(OLD_BLOCK)
# (a)와 완전히 같은 실제 값 — smap.get('취소',0)=0, VICTIM_LABEL['취소']='접수 취소'
old_out = old_tpl.render(no_repair=False, cur_stage=0, status="접수 취소",
                          stages=["접수", "업체 선정", "복구 공사", "검수", "완료"])
old_has_stage = 'class="stage"' in old_out
old_stage1_current = '"st cur"' in old_out
old_has_cancel_badge = "접수 취소" in old_out
chk(old_has_stage and old_stage1_current and old_has_cancel_badge,
    "★★★★★★ (인과관계 실측) cancelled 가지가 없던 옛 구조라면, 취소된 사건에서도 "
    "1단계가 호박색 '현재'로 켜진 진행표가 '접수 취소' 배지와 함께 그대로 나왔다 "
    "— 위 [3](a)의 실제(고쳐진) 결과와 정반대", old_out)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
