# -*- coding: utf-8 -*-
"""17라운드 회귀 — **형제 경로가 서로 다른 말을 하는** 자리들.

  이번 판의 공통 주제는 하나다: 같은 일을 하는 자리가 여러 곳인데
  한 곳만 빠져 있었다.
    · 낙찰 확정 3경로 중 2곳만 탈락자에게 결과를 알렸다
    · KST 문자열을 파싱하는 8곳 중 2곳만 +09:00 을 빼먹었다
    · 관문 판정 3경로 중 1곳만 사람을 남겼다
    · 목록 API 7곳이 검색을 거는데 2곳은 조건을 통째로 버렸다
    · 상단 카드를 서버 집계로 옮긴 전례가 있는데 두 화면이 안 옮겨졌다
    · 검증이 DB 는 갈라 놓고 사진 폴더는 안 갈라놨다

  형제가 여럿일 때는 **전수로 세는 검사**를 쓴다. 한 곳만 보면 또 놓친다.

      python test_scan_round17_fixes.py
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
    """`def name(` 부터 **다음 최상위 def/@app 까지** — 창을 글자수로 자르지 않는다.

    ⚠ 예전에 4000자 창으로 잘랐다가, 함수 끝에 있는 진짜 호출을 못 보고
      '없다'고 보고한 적이 있다. 길이는 함수마다 다르다.
    """
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
    return "\n".join(ln for ln in t.splitlines() if not ln.strip().startswith("#"))


def strip_js(t):
    #  ⚠ `accept="image/*"` 같은 문자열이 가짜 블록주석을 열어 5만자를 먹은 적이 있다.
    #    앞이 식별자·따옴표면 주석 시작으로 보지 않는다.
    t = re.sub(r"(?<![A-Za-z0-9_\"'])/\*.*?\*/", " ", t, flags=re.S)
    return "\n".join(ln for ln in t.splitlines() if not ln.strip().startswith("//"))


APP = read("app.py")
ADM = read("static/admin.js")
PAR = read("templates/partner_portal.html")
MAN = read("manage.py")
RUN = read("run_all_tests.py")

print("═" * 70)
print("  17라운드 회귀 — 형제 경로가 같은 말을 하는가")
print("═" * 70)

# ── [1] 낙찰 결과 통지 ────────────────────────────────────────────
print("\n[1] 낙찰이 확정되면 떨어진 곳도 결과를 듣는다")
_calls = [m.start() for m in re.finditer(r"notify_bid_losers\(conn", strip_py(APP))]
chk(len(_calls) >= 3,
    f"★ 낙찰 확정 경로 전부가 탈락자에게 알린다 (호출 {len(_calls)}곳)",
    "원경매 자동마감·관리자 낙찰은 부르는데 '전체 재경매 낙찰'만 빠져 있었다. "
    "바로 윗줄에서 경매를 '낙찰'로 닫으므로 탈락 업체 화면에서는 그 공고가 "
    "아무 말 없이 사라진다 — 결과도 못 듣고 사라지는 셈이다")
_seg = strip_py(APP[APP.find("재경매낙찰"):APP.find("재경매낙찰") + 1200])
chk("notify_bid_losers" in _seg,
    "★ 전체 재경매 낙찰 경로에 그 호출이 있다")
chk("b[\"amount\"]" not in read("app.py")[
    APP.find("def notify_bid_losers"):APP.find("def notify_bid_losers") + 1200],
    "탈락 통지에 금액이 실리지 않는다(철칙 — 경쟁가 비공개)")

# ── [2] KST 파싱 전수 ─────────────────────────────────────────────
print("\n[2] KST 문자열을 로컬시각으로 읽는 곳이 하나도 없다")
for lbl, src in (("admin.js", ADM), ("partner_portal.html", PAR),
                 ("insurer_portal.html", read("templates/insurer_portal.html"))):
    hits = re.findall(r"[^\n]*replace\(' ','T'\)[^\n]*", src)
    bad = [h.strip() for h in hits if "+09:00" not in h]
    chk(not bad,
        f"★ {lbl} — KST 파싱 {len(hits)}곳 전부 +09:00 명시",
        "오프셋을 빼면 브라우저 로컬 시각으로 읽힌다. 관리자 PC 가 UTC 면 "
        "기한 점검이 9시간 넘게 죽어 있어도 '정상' 초록이 뜨고, 협력사 폰이 "
        "어긋나 있으면 이미 지난 출동 기한이 '540분 남음' 으로 보인다. "
        + (f"빠진 곳: {bad[0][:70]}" if bad else ""))

# ── [3] 관문 판정에 사람이 남는가 ─────────────────────────────────
print("\n[3] 도급 적법성 판정에 '누가' 남는다")
_gates = re.findall(r"CP\.record_gate\(conn[^\n]*", strip_py(APP))
_noman = [g for g in _gates if "actor()" not in g]
chk(not _noman,
    f"★ 관문 판정 {len(_gates)}곳 전부 사람을 남긴다",
    "contract_gate_log 는 '그때 이 금액·이 표로 직접 도급이 가능하다고 판정했다'는 "
    "법적 소명 스냅샷이다. 같은 요청의 활동로그는 조직(로그인아이디)까지 남기는데 "
    "정작 근거가 되는 쪽이 조직명뿐이었다. " + (f"빠진 곳: {_noman[0][:70]}" if _noman else ""))

# ── [4] 목록 API 가 검색 조건을 버리지 않는다 ─────────────────────
print("\n[4] 화면이 보낸 검색 조건을 서버가 읽는다")
for js_key, header, label in (
        ("photos", "def api_photos_queue", "AI 사진 검수"),
        ("changeorders", "def api_change_orders", "변경 견적")):
    sends = f"searchQS('{js_key}')" in ADM
    body = strip_py(func_body(APP, header))
    chk(sends and "search_filters(" in body,
        f"★ {label} — 검색·공종·기간을 실제로 건다",
        "화면은 조건을 보내는데 서버가 통째로 버렸다. 조건을 조용히 버리는 것은 "
        "결과가 안 나오는 것보다 나쁘다 — 운영자는 '검색했더니 이 결과'라고 믿는다")
    chk("WHERE" in body or "_w" in body,
        f"{label} — 만든 조건을 SQL 에 실제로 붙인다")

# ── [5] 돈·건수는 서버 집계에서 온다 ──────────────────────────────
print("\n[5] 상한 걸린 목록으로 합계·건수를 다시 만들지 않는다")
_S = strip_js(ADM)
chk("/api/settlements/summary?" in _S,
    "★ 드릴다운 합계를 서버에 물어본다",
    "종전에는 LIMIT 1000 목록을 화면에서 다시 더했다. 정산이 1000건을 넘는 순간, "
    "화면이 스스로 '대시보드 카드와 같은 조건이므로 위 합계가 그 숫자와 같아야 "
    "합니다' 라고 써 둔 바로 그 자리에서 숫자가 갈린다(잘렸다는 표시도 없다)")
chk("data.reduce((a,s)=>a+(s[md.sum_col]||0),0)" not in _S,
    "★ 드릴다운 카드에 목록 재합산이 남아 있지 않다")
chk("/api/defects/summary" in _S and "/api/defects/summary" in APP,
    "★ 하자 카드도 서버 집계를 쓴다",
    "대시보드 배지는 COUNT(*) 전수인데 화면 카드는 LIMIT 1000 목록 길이였다. "
    "정렬이 '중대 먼저'라 잘려 나가는 쪽이 경미·오래된 건으로 편향된다")
_ds = strip_py(func_body(APP, "def api_defects_summary"))
chk("status NOT IN ('완료','반려')" in _ds,
    "★ 하자 집계가 대시보드 배지와 같은 술어를 쓴다",
    "한쪽만 조건을 바꾸면 다시 갈라진다")
chk("_settle_where" in APP and APP.count("def _settle_where") == 1,
    "★ 정산 목록과 합계가 같은 조건 조립을 공유한다",
    "'한 글자도 다르면 안 된다' 고 주석으로 적어 두는 대신 코드로 묶는다")
_sm = strip_py(func_body(APP, "def api_settlements_summary"))
chk('if (request.args.get("money") or "").strip():' in _sm,
    "★ 드릴다운 합계는 금액 구분이 있을 때만 낸다",
    "money 없이도 채우면 그 값은 '취소분 포함 전체'(같은 응답의 n 은 취소 제외)라, "
    "한 응답 안에서 같은 뜻으로 보이는 두 숫자가 서로 다른 모집단을 말한다 "
    "(실측: drill.n=39 vs n=38)")
chk(_sm.count("400") >= 1,
    "★ 알 수 없는 금액 구분을 목록과 같이 400 으로 막는다",
    "조용히 null 을 돌려주면 화면이 옛 방식(목록 재합산)으로 되돌아간다 — "
    "고쳐 놓은 결함이 조건 하나로 되살아나는 문")

# ── [6] 검증이 운영 사진 폴더를 건드리지 않는다 ───────────────────
print("\n[6] 검증과 운영이 파일까지 갈라져 있다")
chk("BOKGUON_UPLOAD_DIR" in RUN,
    "★ 러너가 검증용 사진 폴더를 세운다",
    "DB 는 BOKGUON_DB_PATH 로 막아 놓고 uploads 는 안 막아서, 검증이 올린 사진이 "
    "운영 uploads/ 에 쌓였다(실측 파일 673개 · 운영 DB 에 없는 사건 id 폴더 59개). "
    "매일 03:20 백업(robocopy /E)은 지우지 않아 백업본에 영구히 남는다")
_i = RUN.find("BOKGUON_UPLOAD_DIR")
_j = RUN.find("BOKGUON_DB_PATH", _i)
chk(0 < _i < _j,
    "★ 사진 폴더를 DB 가드보다 먼저 세운다",
    "photo_ai 는 import 되는 순간 UPLOAD_ROOT 를 굳힌다 — 늦게 세우면 안 먹는다")

print("\n[7] 빈 값을 '설정 안 함'으로 본다")
chk(MAN.count('os.environ.get("BOKGUON_UPLOAD_DIR", os.path.join(HERE, "uploads"))') == 0,
    "★ manage.py 에 옛 방식(빈 값이 그대로 새는)이 남아 있지 않다",
    ".env.example 은 `BOKGUON_UPLOAD_DIR=` (값 없음)으로 배포되고 배포절차가 이 파일을 "
    "복사하라고 한다. 빈 값이면 get(키,기본값)이 기본값이 아니라 빈 문자열을 준다 → "
    "휴지통 경로가 '_trash'(실행 디렉터리)가 되어 존재하지 않고, isdir 이 False 라 "
    "루프를 안 돌아 **경고도 없이 0건으로 성공한다**. 삭제한 사진이 영구히 남는다")
chk(MAN.count("def _upload_root") == 1 and MAN.count("_upload_root()") >= 3,
    "★ 업로드 루트를 한 곳에서 정하고 전부 그걸 쓴다")
chk('(os.environ.get("BOKGUON_UPLOAD_DIR") or "").strip()' in MAN,
    "★ photo_ai 와 같은 관용구로 막는다(쓰는 쪽·지우는 쪽이 같은 답을 낸다)")
chk("_orphan_photo_files" in MAN and "def cmd_check" in MAN,
    "★ 점검이 디스크 고아 사진을 보고한다",
    "DB 행 고아(prune-orphans)는 이미 보는데 반대 방향은 아무도 안 봤다")

# ── 구문 ──────────────────────────────────────────────────────────
print("")
for f in ("app.py", "manage.py", "dispatch.py", "run_all_tests.py"):
    try:
        ast.parse(read(f)); ok, why = True, ""
    except SyntaxError as e:
        ok, why = False, f"{e.lineno}행: {e.msg}"
    chk(ok, f"{f} 구문", why)

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
