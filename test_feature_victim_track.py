# -*- coding: utf-8 -*-
"""[기능] 피해자 진행조회 자동 발급 — 회귀.

  왜 만들었나 —
    발급 라우트·공개 조회 페이지·안내 문자가 **이미 다 지어져 있었는데**
    실데이터가 0건이었다. 결함이 아니라 **손이 가야 시작되는 구조**였기 때문이다 —
    운영자가 사건마다 버튼을 눌러야 했고, 하루 수십 건이면 아무도 안 누른다.
    기능이 있는데 안 쓰이면 없는 것과 같다.

  이 기능이 지켜야 할 성질 —
    ① **사건을 만드는 문이 둘이다.** `_create_case`(포털)와 `api_case_create`(어드민)가
       각자 INSERT 를 한다. 자동 발급을 앞쪽에만 걸었더니 어드민 등록 사건은 링크가
       안 생겼다 — **실측으로 잡았다.** 이 파일의 다른 주석도 같은 사고를 적어 뒀다.
    ② **이미 있는 링크를 말없이 갈아치우지 않는다.** 피해자가 받아 둔 문자의 링크가
       조용히 죽으면 그 사람은 '고장' 으로 여기고 전화한다 — 이 기능이 줄이려던
       바로 그 전화다. 재발급은 운영자가 명시적으로 누를 때만(force).
    ③ **연락처를 넣은 뒤에 부른다.** 앞에서 부르면 victim_phone 이 아직 없어
       토큰만 생기고 안내가 아무 데도 안 간다.
    ④ **응답 dict 안에서 DB 를 조회하지 않는다.** conn.close() 뒤라 500 이 난다
       (실제로 그렇게 만들었고 실측으로 잡았다).
    ⑤ **집계는 횟수와 마지막 시각만.** 누가·어디서 봤는지는 모으지 않는다.

      python test_feature_victim_track.py
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


def func_src(src, header):
    """`def name` 부터 **다음 최상위 def/@app.** 까지 — 들여쓰기 0 만 경계로."""
    i = src.find(header)
    if i < 0:
        return ""
    m = re.search(r"\n(?:@app\.|def )", src[i + len(header):])
    return src[i:i + len(header) + m.start()] if m else src[i:]


APP, DBF = read("app.py"), read("db.py")
ADM = read("static/admin.js")
IP = read("templates/insurer_portal.html")

print("═" * 70)
print("  기능 회귀 — 피해자 진행조회 자동 발급")
print("═" * 70)

print("\n[1] 사건을 만드는 **두 문 모두**에 걸려 있다")
chk("def issue_track_link" in APP, "★ 발급이 함수 하나로 모여 있다")
_n = APP.count("issue_track_link(conn, cid)")
chk(_n == 2,
    f"★★ 자동 발급이 **두 경로** 모두에 있다 ({_n}곳)",
    "포털은 _create_case, 어드민은 api_case_create 가 각자 INSERT 한다. "
    "한쪽에만 걸면 그쪽 접수만 링크가 생겨, 어떤 피해자는 받고 어떤 피해자는 못 받는다")
for fn, who in (("def _create_case", "포털 접수"),
                ("def api_case_create", "어드민 등록")):
    _b = func_src(APP, fn)
    chk("issue_track_link(conn, cid)" in _b, f"★ {who} 경로에 있다")
    #  ★ 연락처를 넣은 **뒤**여야 안내가 예약된다
    _iv = _b.find("victim_phone")
    _it = _b.find("issue_track_link(conn, cid)")
    chk(0 < _iv < _it,
        f"★★ {who} — 연락처를 넣은 **뒤**에 부른다",
        "앞에서 부르면 토큰만 생기고 안내가 아무 데도 안 간다")
#  ★ 사진있음/사진없음 **갈래가 갈리기 전**에 부른다(두 갈래 다 걸리게)
#  ⚠ `if no_photo:` 는 함수 안에 두 번 나온다 — 앞의 것은 **가견적 검증** 분기이고
#    갈래를 가르는 것은 뒤의 것이다. 그냥 find() 하면 앞의 것을 집어 멀쩡한 코드가
#    실패로 뜬다(실제로 그랬다). 갈래 분기의 **고유한 주석**으로 자리를 잡는다.
_cc = func_src(APP, "def _create_case")
_split = _cc.find("# 경매·공고 알림 없이, 운영팀이 출동 수배를 열도록 안내한다")
chk(_split > 0, "갈래 분기를 찾았다")
chk(0 < _cc.find("issue_track_link") < _split,
    "★★ 사진있음·사진없음 **갈리기 전**에 부른다",
    f"발급 {_cc.find('issue_track_link')} · 갈래 {_split} — "
    f"갈린 뒤에 걸면 한쪽 접수만 링크가 생긴다")

print("\n[2] 접수를 막지 않는다")
for fn, who in (("def _create_case", "포털"), ("def api_case_create", "어드민")):
    _b = func_src(APP, fn)
    _i = _b.find("issue_track_link(conn, cid)")
    _around = _b[max(0, _i - 200):_i + 200]
    chk("try:" in _around and "except Exception" in _around,
        f"★ {who} — 발급이 실패해도 접수는 된다",
        "안내는 부가 기능이지 접수의 관문이 아니다")
    chk("app.logger.exception" in _around,
        f"★ {who} — 실패를 조용히 삼키지 않고 로그에 남긴다")

print("\n[3] 이미 있는 링크를 말없이 갈아치우지 않는다")
_il = func_src(APP, "def issue_track_link")
chk("if token and not force:" in _il,
    "★★ 이미 있으면 그대로 둔다(force 일 때만 재발급)",
    "피해자가 받아 둔 문자의 링크가 조용히 죽으면 '고장' 으로 여기고 전화한다 — "
    "이 기능이 줄이려던 바로 그 전화다")
_tl = func_src(APP, "def api_track_link")
chk("force=True" in _tl,
    "★ 운영자가 **명시적으로 누르면** 재발급된다")

print("\n[4] 열어 본 사실을 센다 — 그 이상은 모으지 않는다")
chk('("cases", "track_views"' in DBF and '("cases", "track_last_at"' in DBF,
    "★ 집계 칸이 마이그레이션에 있다(운영 DB 를 지우지 않고 올라간다)")
_tp = func_src(APP, "def track_page")
chk("track_views=COALESCE(track_views,0)+1" in _tp,
    "★★ 공개 페이지가 열릴 때마다 센다")
chk("track_last_at=?" in _tp, "★ 마지막 시각도 남긴다")
for bad in ("client_ip", "user_agent", "request.remote_addr"):
    chk(bad not in _tp,
        f"★ 누가·어디서는 세지 않는다 — '{bad}' 없음 (개인정보 최소수집)")
chk("except sqlite3.Error" in _tp and "app.logger.exception" in _tp,
    "★★ 집계가 실패해도 **피해자 화면은 뜬다**",
    "부가 기능이 본 기능을 막으면 안 된다")

print("\n[5] 발주처 지표 — 닫힌 커넥션을 쓰지 않는다")
_st = func_src(APP, "def _insurer_track_stat")
chk("COALESCE(track_views,0) > 0 THEN 1" in _st,
    "★★ '열어 본 건' 은 **사건 수**다(조회수 아님)",
    "'몇 명의 고객이 스스로 확인했나' 가 궁금한 것이지 클릭 수가 아니다")
_di = func_src(APP, "def api_insurer_dashboard")
chk("track_stat = _insurer_track_stat(conn, iid)" in _di,
    "★★ **conn.close() 앞에서** 계산한다",
    "응답 dict 안에서 조회하면 이미 닫힌 커넥션을 써서 500 이 난다 — "
    "실제로 그렇게 만들었고 실측으로 잡았다")
chk(_di.find("track_stat = _insurer_track_stat") < _di.find("conn.close()"),
    "★ 순서가 맞다(계산 → 닫기)")
chk('"track": track_stat' in _di, "★ 응답은 그 변수를 쓴다")
chk("D.track && D.track.issued" in IP,
    "★ 수치가 없으면 카드를 아예 안 그린다(0%는 아무 말도 못 한다)")

print("\n[6] 화면이 '보낸 것' 과 '열어 본 것' 을 구분해 말한다")
chk("아직 열어 보지 않음" in ADM,
    "★★ 어드민 상세가 **열어 봤는지**를 보여 준다",
    "보낸 사실만 알면 '안내했는데 왜 전화가 오나' 를 설명할 수 없다")
chk("피해자 직접 확인" in IP, "★ 발주처 카드 이름이 '보낸 건수' 가 아니다")

print("\n[7] 문자에 금액을 적지 않는다 (철칙 1·2)")
_nv = func_src(APP, "def notify_victim")
for bad in ("amount", "price", "낙찰", "보험금"):
    chk(bad not in _nv, f"★ '{bad}' 없음")
chk("_site_url()" in _nv,
    "★ 절대 주소를 넣는다(상대경로면 문자앱이 열 수 없다)")
chk("_victim_notice()" in _nv,
    "★ 수집 출처·수신거부를 고지한다 (개인정보 보호법 §20)")

print("")
for f in ("app.py", "db.py"):
    try:
        ast.parse(read(f)); _ok, _why = True, ""
    except SyntaxError as e:
        _ok, _why = False, f"{e.lineno}행: {e.msg}"
    chk(_ok, f"{f} 구문", _why)
chk(IP.count("<div") == IP.count("</div>"),
    "insurer_portal div 균형", f"{IP.count('<div')} / {IP.count('</div>')}")

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
