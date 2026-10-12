# -*- coding: utf-8 -*-
"""스캔 670라운드 회귀(직접조사, 하위위임 없음) — 피해자 진행조회 화면
   (templates/track.html 을 채우는 app.py track_page())이 사진 없는 사건이
   선착순 출동으로 현장 사진을 확보하는 동안("수배중")에는 cases.
   dispatch_status 값을 전혀 안 보고 cases.status 만 봐서, 이 기간에는
   다른 대기 상태(입찰중·승인대기·유찰)와 달리 피해자에게 내부 상태값
   그대로인 "접수"가 뜨던 결함.

   조사 배경 — '수배중'은 cases.status 값이 아니라 dispatch_status 값이다
   (dispatch.py:51 CS_SEEKING = "수배중", db.py:1169 스키마 주석 "수배중 /
   출동중 / 사진확보 / 수배실패"). 형제 함수 api_map_cases(app.py, 지도
   필터)는 이미 라운드56 에서 똑같은 혼동을 겪고 고쳤다 — 그 함수 자신의
   주석이 "여기서 걸러도 항상 0건이라 지도가 조용히 비었다"는 실측을
   남겼다. 그런데 피해자 진행조회 track_page() 의 두 딕셔너리(smap·
   VICTIM_LABEL)는 여전히 c["status"] 하나만 보고 "수배중" 키를 넣어
   놨다 — 사진 없는 사건이 선착순 출동으로 수배 중인 동안 cases.status 는
   그대로 '접수'라서(dispatch_status 만 '수배중') 이 키는 절대 안 걸렸다.

   실제 영향 — smap 의 "수배중":0 은 "접수":0 과 값이 우연히 같아 무해
   하다(그래서 이번 수정도 smap 자체의 값은 바꾸지 않았다 — 조회 키만
   맞춰도 같은 값이 나와 회귀 위험이 없다). VICTIM_LABEL 은 다른 문구
   ("업체 선정 중")라 실제로 달라진다 — 다른 대기 상태는 전부 "업체 선정
   중"으로 보이는데, 사진 없는 사건이 막 접수돼 인근 업체를 부르는 중일
   때만 내부 상태값 그대로인 "접수"가 보였다.

   고침 — app.py track_page() 의 SELECT 에 dispatch_status 를 추가하고,
     _disp_key = "수배중" if (c["status"]=="접수" and c["dispatch_status"]
                              =="수배중") else c["status"]
   를 새로 계산해 smap.get(_disp_key, 0)·VICTIM_LABEL.get(_disp_key,
   c["status"]) 로 두 조회 모두 이 키를 쓰게 했다. cur_stage 값 자체는
   '접수'·'수배중' 이 둘 다 0 이라 회귀가 없고, victim_status 문구만
   실제로 달라진다.

   회귀테스트(이 파일) —
   [1] 소스 — track_page() 안에 dispatch_status 가 SELECT 에 있고,
       smap·VICTIM_LABEL 조회가 새 _disp_key 를 쓴다(옛 c["status"] 직접
       조회 패턴은 남아 있지 않다). 전제(dispatch.py CS_SEEKING, 형제
       api_map_cases 의 라운드56 수정)도 함께 확인한다.
   [2] 단위 — 실제 파일에서 그대로 잘라낸 _disp_key 대입식 한 줄을 손으로
       다시 타이핑하지 않고 그대로 exec 로 실행해, 네 조합(수배중 상태
       그대로/방금 접수라 아직 출동 없음/도착은 했지만 아직 접수 단계로
       남아 있는 경우/애초에 있을 수 없는 시공중+수배중 조합)에서 계산이
       옳은지 직접 증명한다.
   [3] 종단 — 스크래치 DB + 실제 Flask 라우트(GET /track/<token>) + 지금
       고쳐진 실제 함수로 세 사건 재현: (a) status='접수'+dispatch_status
       ='수배중' → 배지가 "업체 선정 중"(핵심 수정 지점 — 고치기 전엔
       "접수" 뿐이었다), (b) status='접수'+dispatch_status=NULL(방금 접수,
       출동 없음) → 그대로 "접수"(회귀 없음), (c) status='시공중'+
       dispatch_status='수배중'(있을 수 없는 조합, 방어) → "복구 공사
       진행 중"(다른 상태를 절대 안 덮어쓴다).
   [4] 되돌리기 — 실제 파일은 전혀 건드리지 않고, dispatch_status 인지가
       없던 옛 구조(c["status"] 직접 조회)만 exec 로 재구성해 (a)와 같은
       조건을 넣으면 "업체 선정 중" 대신 "접수"가 나오는, 고치기 전 결함이
       실제로 재현됨을 실측한다.

       python test_scan_round670_fixes.py
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
print("  스캔 670라운드 회귀 — track.html 피해자 화면의 '수배중' dispatch_status 미인지")
print("=" * 72)

APP_SRC = read("app.py")
DISPATCH_SRC = read("dispatch.py")

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
FN_SRC = func_src(APP_SRC, "def track_page(token):")
chk(FN_SRC != "", "track_page() 함수를 실제로 찾았다")

chk("track_token, track_issued_at, dispatch_status" in FN_SRC,
    "★★★★★ track_page() 의 SELECT 가 이제 dispatch_status 도 읽는다")
chk('_disp_key = "수배중" if (c["status"] == "접수" and c["dispatch_status"] == "수배중") else c["status"]'
    in FN_SRC,
    "★★★★★ '수배중' 여부를 dispatch_status 로 판정하는 _disp_key 가 있다")
chk("cur_stage = smap.get(_disp_key, 0)" in FN_SRC,
    "★★★★★ 단계표(cur_stage)가 _disp_key 로 조회한다")
chk('victim_status = VICTIM_LABEL.get(_disp_key, c["status"])' in FN_SRC,
    "★★★★★ 상태 배지(victim_status)가 _disp_key 로 조회한다")
chk('smap.get(c["status"], 0)' not in FN_SRC,
    "  옛 결함 패턴(c[\"status\"]로 직접 smap 조회)이 더는 없다")
chk('VICTIM_LABEL.get(c["status"], c["status"])' not in FN_SRC,
    "  옛 결함 패턴(c[\"status\"]로 직접 VICTIM_LABEL 조회)이 더는 없다")

chk('CS_SEEKING = "수배중"' in DISPATCH_SRC,
    "  전제 확인 — dispatch.py 는 여전히 '수배중'을 dispatch_status 값으로 쓴다"
    "(이 결함의 근거)")
MAP_FN = func_src(APP_SRC, "def api_map_cases():")
chk('if st == "수배중":' in MAP_FN and "dispatch_status=?" in MAP_FN,
    "  전제 확인 — 형제 api_map_cases(라운드56)는 이미 dispatch_status 로 가른다"
    "(같은 실수를 이 화면만 반복하고 있었다)")

# ============================================================
print("\n[2] 단위 — 실제 파일에서 그대로 잘라낸 _disp_key 대입식을 직접 실행")
# ------------------------------------------------------------
_line_start = FN_SRC.index('_disp_key = "수배중"')
_line_end = FN_SRC.index("\n", _line_start)
DISP_KEY_LINE = FN_SRC[_line_start:_line_end]
chk(DISP_KEY_LINE.startswith('_disp_key = "수배중" if'),
    "  (전제) 잘라낸 한 줄이 실제로 _disp_key 대입식이다", DISP_KEY_LINE)
#  ⚠ [4]에서 이 줄을 통째로 지우려면 **줄 앞의 들여쓰기와 줄바꿈까지** 같이
#    떼어내야 한다 — 본문(no leading ws)만 지우면 그 앞 8칸 들여쓰기가
#    다음 줄(cur_stage=...) 위에 그대로 얹혀 16칸 들여쓰기가 되어
#    IndentationError 가 난다(실제로 처음엔 이렇게 만들어 재현했다).
_indent_start = FN_SRC.rfind("\n", 0, _line_start) + 1
FULL_DISP_KEY_LINE = FN_SRC[_indent_start:_line_end + 1]

CASES2 = [
    ("접수+수배중 (선착순 출동 중)", {"status": "접수", "dispatch_status": "수배중"}, "수배중"),
    ("접수+NULL (방금 접수, 출동 없음)", {"status": "접수", "dispatch_status": None}, "접수"),
    ("접수+사진확보 (도착은 했지만 사건은 아직 접수 단계)",
     {"status": "접수", "dispatch_status": "사진확보"}, "접수"),
    ("시공중+수배중 (있을 수 없는 조합, 방어)", {"status": "시공중", "dispatch_status": "수배중"}, "시공중"),
]
for label, c, expect in CASES2:
    _ns = {"c": c}
    exec(compile(DISP_KEY_LINE, "<round670_disp_key_line>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    chk(_ns["_disp_key"] == expect,
        f"★★★ {label} → _disp_key == {expect!r}", _ns.get("_disp_key"))

# ============================================================
print("\n[3] 종단 실행 — 실제 Flask 라우트 + 지금 고쳐진 실제 함수")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round670_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB  # noqa: E402
DB.init_db()
import app as A  # noqa: E402

conn = DB.get_db()


def _mk_tracked_case(no, status, dispatch_status=None, **extra):
    token = f"tok{no.replace('-', '').lower()}1234567890"[:40]
    thash = hashlib.sha256(token.encode()).hexdigest()
    cols = dict(case_no=no, insurer="테스트보험사", category="가드레일", region="서울",
                status=status, dispatch_status=dispatch_status,
                est_price=1000000, urgent=0, is_demo=0,
                created_at=DB.now(), track_token=token, track_token_hash=thash,
                track_issued_at=DB.now())
    cols.update(extra)
    names = ",".join(cols.keys())
    qs = ",".join("?" for _ in cols)
    conn.execute(f"INSERT INTO cases({names}) VALUES({qs})", tuple(cols.values()))
    return token


tok_a = _mk_tracked_case("R670-CASE-A", "접수", dispatch_status="수배중")
tok_b = _mk_tracked_case("R670-CASE-B", "접수", dispatch_status=None)
tok_c = _mk_tracked_case("R670-CASE-C", "시공중", dispatch_status="수배중")
conn.commit()
conn.close()

client = A.app.test_client()


def _body(html):
    return html.split('<div class="body">', 1)[1].split('<div class="note">', 1)[0]


resp_a = client.get(f"/track/{tok_a}")
chk(resp_a.status_code == 200, "  (a) GET /track/<token> 이 200을 낸다(접수+수배중)", resp_a.status_code)
body_a = _body(resp_a.get_data(as_text=True))
chk('<span class="badge ">업체 선정 중</span>' in body_a,
    "★★★★★★ (a) 선착순 출동으로 수배 중인 사건은 실제 라우트 응답에서도 "
    "'업체 선정 중'을 보여준다(핵심 수정 지점 — 고치기 전엔 '접수' 뿐이었다)",
    body_a[:300])
chk('<span class="badge ">접수</span>' not in body_a,
    "★★★★★★ (a) 더는 내부 상태값 그대로인 '접수' 배지가 나오지 않는다", body_a[:300])

resp_b = client.get(f"/track/{tok_b}")
chk(resp_b.status_code == 200, "  (b) GET /track/<token> 이 200을 낸다(접수, 출동 없음)", resp_b.status_code)
body_b = _body(resp_b.get_data(as_text=True))
chk('<span class="badge ">접수</span>' in body_b,
    "  (b) 회귀 없음 — 아직 출동이 없는 갓 접수된 사건은 여전히 '접수'가 나온다", body_b[:300])

resp_c = client.get(f"/track/{tok_c}")
chk(resp_c.status_code == 200, "  (c) GET /track/<token> 이 200을 낸다(시공중+수배중 방어조합)", resp_c.status_code)
body_c = _body(resp_c.get_data(as_text=True))
chk('<span class="badge ">복구 공사 진행 중</span>' in body_c,
    "  (c) 회귀 없음 — 이미 시공중인 사건은 방어 조건(status=='접수') 덕에 "
    "dispatch_status 잔존값에 안 흔들리고 그대로 '복구 공사 진행 중'이 나온다", body_c[:300])

# ============================================================
print("\n[4] 되돌리기 — dispatch_status 인지가 없던 옛 구조만 exec 로 재구성"
      "(실제 파일은 무변경)")
# ------------------------------------------------------------
#  ⚠ app.py 는 절대 건드리지 않는다. 함수를 리네임한 사본 안에서만
#    (1) SELECT 에서 dispatch_status 제거 (2) _disp_key 대입 자체를 제거
#    (3) 두 .get() 조회를 옛 c["status"] 직접조회로 되돌린다 — 그 뒤
#    A.app.view_functions["track_page"] 항목만 잠깐 치환한다(round419가
#    정착시킨 기법 — 데코레이터 없는 단일 GET 라우트라 그대로 적용된다).
NEW_SELECT_FRAG = "track_token, track_issued_at, dispatch_status"
OLD_SELECT_FRAG = "track_token, track_issued_at"
NEW_CUR_STAGE = "cur_stage = smap.get(_disp_key, 0)"
OLD_CUR_STAGE = 'cur_stage = smap.get(c["status"], 0)'
NEW_VICTIM_STATUS = 'victim_status = VICTIM_LABEL.get(_disp_key, c["status"])'
OLD_VICTIM_STATUS = 'victim_status = VICTIM_LABEL.get(c["status"], c["status"])'

chk(FN_SRC.count(NEW_SELECT_FRAG) == 1 and FN_SRC.count(NEW_CUR_STAGE) == 1
    and FN_SRC.count(NEW_VICTIM_STATUS) == 1 and FN_SRC.count(FULL_DISP_KEY_LINE) == 1,
    "  (준비) 되돌릴 네 조각이 함수 안에 각각 정확히 한 번씩 있다")

reverted_body = (FN_SRC
    .replace("def track_page(token):", "def _track_page_pre670(token):", 1)
    .replace(FULL_DISP_KEY_LINE, "", 1)
    .replace(NEW_SELECT_FRAG, OLD_SELECT_FRAG, 1)
    .replace(NEW_CUR_STAGE, OLD_CUR_STAGE, 1)
    .replace(NEW_VICTIM_STATUS, OLD_VICTIM_STATUS, 1))
chk("_disp_key" not in reverted_body,
    "  (준비) 되돌린 사본에는 _disp_key 흔적이 전혀 없다(옛 구조 그대로)")
chk("_track_page_pre670" in reverted_body and 'def track_page(token):' not in reverted_body,
    "  (준비) 함수가 이름충돌 없이 리네임됐다")

_ns670 = dict(vars(A))
exec(compile(reverted_body, "<round670_pre670_track_page>", "exec"), _ns670)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
old_track_page_fn = _ns670["_track_page_pre670"]

_orig_view670 = A.app.view_functions["track_page"]
A.app.view_functions["track_page"] = old_track_page_fn
try:
    with A.app.test_client() as c4:
        r_old = c4.get(f"/track/{tok_a}")
finally:
    A.app.view_functions["track_page"] = _orig_view670

chk(A.app.view_functions["track_page"] is _orig_view670,
    "  view_functions가 원래 함수객체로 복원됐다")

body_old = _body(r_old.get_data(as_text=True))
chk('<span class="badge ">접수</span>' in body_old,
    "★★★★★★ (인과관계 실측) dispatch_status 인지가 없던 옛 코드(되돌림, 실제 파일은 "
    "안 건드림)는 똑같은 사건(접수+수배중)에서도 내부 상태값 그대로인 '접수'를 그대로 "
    "보여준다 — 위 [3](a)의 실제(고쳐진) 결과와 정반대", body_old[:300])
chk('<span class="badge ">업체 선정 중</span>' not in body_old,
    "  옛 코드에는 '업체 선정 중'이 아예 안 나온다(그래서 이번 수정이 필요했다)", body_old[:300])

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
